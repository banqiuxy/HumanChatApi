# -*- coding: utf-8 -*-
"""
后台管理处理（admin_routes.py）
后端 WebUI：由后端读取 HTML 模板文件，注入数据后返回完整页面
（纯标准库实现，模板占位符替换，无任何第三方依赖）。

实现：
- GET  /admin              首页数据看板（统计 + 服务模式 + 待处理卡片 + 已回复卡片）
- GET  /admin/chat         会话详情回复页（用户消息完整显示 + 上下文合并折叠按钮）
- GET  /admin/ctx          提示词与上下文列表页（每条一行，默认折叠）
- GET  /admin/msg          单条消息详情页（默认折叠，点击展开）
- POST /admin/submit       后台提交人工回复（唤醒请求线程，会话保留）
- POST /admin/close        后台手动关闭会话（唯一删除途径）
- POST /admin/set_mode     切换服务模式（人工回复 / 自动回复）
- GET  /admin/api/status   首页统计接口（仅用于前端自动刷新）
"""
import html
import json
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import parse_qs

from . import utils
from .session_manager import session_manager

# 模板目录（相对本文件）
_TEMPLATE_DIR = Path(__file__).resolve().parent / "webui"


# ----------------------------------------------------------------------
# 模板读取与渲染辅助
# ----------------------------------------------------------------------
def _read_template(name: str) -> str:
    path = _TEMPLATE_DIR / name
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _render(template: str, **kwargs: str) -> str:
    """用占位符 __NAME__ 替换模板内容（后端渲染）。"""
    for key, value in kwargs.items():
        template = template.replace("__" + key.upper() + "__", str(value))
    return template


def _esc(s: Any) -> str:
    """HTML 转义（防止 XSS / 破坏页面结构）。"""
    return html.escape(str(s), quote=True)


def _session_card(s) -> Dict[str, str]:
    """提取会话在卡片列表中的展示字段。"""
    return {
        "sid": _esc(s.sid),
        "time": _esc(s.time),
        "preview": _esc(utils.extract_first_text(s.raw_messages)),
        "has_image": "true" if s.has_image else "",
        "reply": _esc(s.reply or ""),
    }


def _render_cards(sessions: List) -> str:
    """后端渲染会话卡片 HTML。"""
    parts = []
    for s in sessions:
        card = _session_card(s)
        badge = '<span class="badge">🖼 含图片</span>' if card["has_image"] else ""
        reply_html = ""
        if card["reply"]:
            reply_html = f'<div class="reply-preview">💬 {card["reply"]}</div>'
        parts.append(
            f'<div class="card" onclick="location.href=\'/admin/chat?sid={card["sid"]}\'">'
            f'<div class="top"><span class="sid">{card["sid"]}</span>'
            f'<span class="time">{card["time"]}</span></div>'
            f'<div class="preview">{card["preview"]}</div>{badge}{reply_html}</div>'
        )
    if not parts:
        return '<div class="empty">暂无会话</div>'
    return "".join(parts)


def _render_blocks(msg: Dict[str, Any]) -> str:
    """渲染单条消息的内容块（文本 + 图片），音视频已被清洗不会出现。"""
    blocks = []
    for b in msg.get("content", []):
        if not isinstance(b, dict):
            continue
        btype = b.get("type", "")
        if btype == "text" and b.get("text"):
            blocks.append(f'<div class="block text">{_esc(b["text"])}</div>')
        elif btype == "image_url":
            img = b.get("image_url")
            url = ""
            if isinstance(img, str):
                url = img
            elif isinstance(img, dict):
                url = img.get("url", "") or ""
            if url:
                kind = "(base64 内嵌)" if url.startswith("data:") else "(网络图片)"
                blocks.append(
                    f'<div class="block img"><div class="img-meta">🖼 图片 {kind}</div>'
                    f'<img src="{_esc(url)}" alt="image" style="max-width:100%" '
                    f'onerror="this.outerHTML=\'<p style=color:#ff5b5b>⚠ 图片加载失败</p>\'"></div>'
                )
    if not blocks:
        blocks.append('<div class="block text" style="color:#8b93a3">（无可见内容）</div>')
    return "".join(blocks)


def _msg_summary(msg: Dict[str, Any]) -> str:
    """提取消息摘要（首条文本前 30 字）。"""
    text = ""
    for b in msg.get("content", []):
        if isinstance(b, dict) and b.get("type") == "text" and b.get("text"):
            text = b["text"].strip()
            break
    if text:
        return text[:30] + ("..." if len(text) > 30 else "")
    if utils.check_has_image([msg]):
        return "[含图片]"
    return "[无内容]"


def _render_history(history: List[Dict[str, Any]], sid: str) -> str:
    """
    后端渲染会话历史（文本 + 图片）。
    折叠规则：
    - 用户当前发过来的消息（最后一条 user 消息）：默认完整显示（文本 + 图片）
    - 其他所有消息（系统提示词、之前发送的、助手回复等）：【合并成一个大按钮】，
      「提示词和上下文已折叠，点我查看」，点击跳转上下文列表页
      （/admin/ctx?sid=），列表页每条默认折叠，点击进入详情页再展开内容
    """
    # 找出最后一条用户消息（即用户当前发过来的内容）
    last_user_index = -1
    for i, msg in enumerate(history):
        if msg.get("role") == "user":
            last_user_index = i

    # 是否存在其他消息（需要折叠的上下文）
    has_context = any(i != last_user_index for i in range(len(history)))

    parts = []
    for i, msg in enumerate(history):
        role = msg.get("role", "user")
        is_current_user = (i == last_user_index and role == "user")
        role_map = {"user": ("用户", "user"), "assistant": ("助手", "assistant"), "system": ("系统", "system")}
        label, cls = role_map.get(role, (role, "system"))

        if is_current_user:
            # 用户当前发过来的消息：完整显示（文本 + 图片）
            parts.append(
                f'<div class="msg"><span class="role {cls}">{label}</span>'
                f'{_render_blocks(msg)}</div>'
            )

    # 所有其他消息合并成一个按钮
    if has_context:
        parts.append(
            f'<div class="ctx-folded clickable" '
            f'onclick="location.href=\'/admin/ctx?sid={_esc(sid)}\'">'
            f'🔒 提示词和上下文已折叠，点我查看'
            f'</div>'
        )

    if not parts:
        return '<div class="empty">该会话没有可见消息</div>'
    return "".join(parts)


# ----------------------------------------------------------------------
# 路由处理函数（返回 (status, body_bytes, content_type)）
# ----------------------------------------------------------------------
def admin_index() -> Tuple[int, bytes, str]:
    """GET /admin 首页：后端渲染统计 + 服务模式 + 待处理 + 已回复。"""
    waiting = session_manager.all_waiting()
    completed = session_manager.all_completed()
    auto = session_manager.is_auto_reply()
    if auto:
        mode_label = "自动回复"
        mode_cls = "auto"
        toggle_btn = '<button class="btn-mode" id="btnMode" data-mode="auto">开启人工回复</button>'
    else:
        mode_label = "人工回复"
        mode_cls = "manual"
        toggle_btn = '<button class="btn-mode" id="btnMode" data-mode="manual">开启自动回复</button>'
    template = _read_template("admin_index.html")
    page = _render(
        template,
        waiting_count=str(session_manager.waiting_count()),
        completed_count=str(session_manager.completed_count()),
        today_count=str(session_manager.today_count()),
        uptime=utils.format_duration(session_manager.uptime_seconds()),
        mode_label=mode_label,
        mode_cls=mode_cls,
        toggle_btn=toggle_btn,
        waiting_cards=_render_cards(waiting),
        completed_cards=_render_cards(completed),
    )
    return 200, page.encode("utf-8"), "text/html; charset=utf-8"


def admin_chat(sid: str) -> Tuple[int, bytes, str]:
    """GET /admin/chat 会话详情：后端渲染完整历史 + 回复表单。"""
    session = session_manager.get(sid)
    if session is None:
        page = ("<h3 style='color:#ff5b5b;text-align:center;margin-top:80px'>"
                "会话不存在或已被关闭</h3>"
                "<p style='text-align:center'><a href='/admin'>返回首页</a></p>")
        return 404, page.encode("utf-8"), "text/html; charset=utf-8"

    template = _read_template("admin_chat.html")
    if session.status == "waiting":
        status_badge = '<span class="status-badge waiting">⏳ 等待回复</span>'
        replied_note = ""
        reply_form = (
            '<div class="reply"><h3>💬 人工回复</h3>'
            '<textarea id="replyBox" placeholder="输入你的回答……"></textarea>'
            '<div class="actions">'
            '<button class="btn-submit" id="btnSubmit">提交回复</button>'
            '<span class="hint">提交后客户端将收到此回复；会话会保留在后台，直到你手动关闭。</span>'
            '</div></div>'
        )
    else:
        status_badge = '<span class="status-badge completed">✅ 已回复（会话保留中）</span>'
        replied_note = ('<div class="replied-note">本会话已完成回复，仍保留在后台供回看。'
                        '如需删除请点击下方「关闭会话」。</div>')
        reply_form = ""

    page = _render(
        template,
        sid=_esc(sid),
        status_badge=status_badge,
        replied_note=replied_note,
        history=_render_history(session.history, sid),
        reply_form=reply_form,
    )
    return 200, page.encode("utf-8"), "text/html; charset=utf-8"


def admin_msg(sid: str, idx: str) -> Tuple[int, bytes, str]:
    """
    GET /admin/msg?sid=xxx&idx=n 单条消息详情页。
    默认折叠显示，点击展开才显示完整内容（文本 + 图片）。
    """
    session = session_manager.get(sid)
    if session is None:
        return 404, b"session not found", "text/plain"
    try:
        index = int(idx)
    except (TypeError, ValueError):
        return 404, b"bad index", "text/plain"
    history = session.history
    if index < 0 or index >= len(history):
        return 404, b"index out of range", "text/plain"

    msg = history[index]
    role = msg.get("role", "user")
    role_map = {"user": ("用户", "user"), "assistant": ("助手", "assistant"), "system": ("系统", "system")}
    label, cls = role_map.get(role, (role, "system"))

    template = _read_template("admin_msg.html")
    page = _render(
        template,
        sid=_esc(sid),
        idx=str(index),
        total=str(len(history)),
        role_label=label,
        role_cls=cls,
        content=_render_blocks(msg),
    )
    return 200, page.encode("utf-8"), "text/html; charset=utf-8"


def admin_ctx(sid: str) -> Tuple[int, bytes, str]:
    """
    GET /admin/ctx?sid=xxx 上下文列表页。
    展示除用户当前消息外的所有消息，每条一行（默认折叠，不显示内容），
    点击某条进入详情页（/admin/msg?sid=&idx=），详情页默认折叠、点击展开。
    """
    session = session_manager.get(sid)
    if session is None:
        return 404, b"session not found", "text/plain"
    history = session.history

    # 找出最后一条用户消息（即用户当前发过来的内容，不在列表页展示）
    last_user_index = -1
    for i, msg in enumerate(history):
        if msg.get("role") == "user":
            last_user_index = i

    rows = []
    for i, msg in enumerate(history):
        if i == last_user_index and msg.get("role") == "user":
            continue  # 跳过用户当前消息
        role = msg.get("role", "user")
        role_map = {"user": ("用户", "user"), "assistant": ("助手", "assistant"), "system": ("系统", "system")}
        label, cls = role_map.get(role, (role, "system"))
        rows.append(
            f'<div class="msg folded clickable" '
            f'onclick="location.href=\'/admin/msg?sid={_esc(sid)}&idx={i}\'">'
            f'<span class="role {cls}">{label}</span>'
            f'<span class="fold-hint">▸ 已折叠，点击查看</span>'
            f'<span class="fold-arrow">→</span>'
            f'</div>'
        )
    if not rows:
        return 404, b"no context", "text/plain"

    template = _read_template("admin_ctx.html")
    page = _render(
        template,
        sid=_esc(sid),
        total=str(len(rows)),
        rows="".join(rows),
    )
    return 200, page.encode("utf-8"), "text/html; charset=utf-8"


def admin_submit(form: Dict[str, List[str]]) -> Tuple[int, bytes, str]:
    """POST /admin/submit 提交人工回复：唤醒请求线程，会话保留。"""
    sid = (form.get("sid") or [""])[0]
    reply_content = (form.get("reply_content") or [""])[0]
    if not reply_content.strip():
        result = {"ok": False, "error": "回复内容不能为空"}
    else:
        ok = session_manager.submit_reply(sid, reply_content)
        result = {"ok": ok} if ok else {"ok": False, "error": "会话不存在或已经被回复"}
    body = json.dumps(result, ensure_ascii=False)
    return 200, body.encode("utf-8"), "application/json"


def admin_close(form: Dict[str, List[str]]) -> Tuple[int, bytes, str]:
    """POST /admin/close 手动关闭会话：唯一删除途径。"""
    sid = (form.get("sid") or [""])[0]
    ok = session_manager.close_session(sid)
    result = {"ok": ok} if ok else {"ok": False, "error": "会话不存在或已经被关闭"}
    body = json.dumps(result, ensure_ascii=False)
    return 200, body.encode("utf-8"), "application/json"


def admin_status() -> Tuple[int, bytes, str]:
    """GET /admin/api/status 首页统计（供前端自动刷新）。"""
    waiting = session_manager.all_waiting()
    completed = session_manager.all_completed()
    result = {
        "mode": "auto" if session_manager.is_auto_reply() else "manual",
        "waiting": session_manager.waiting_count(),
        "completed": session_manager.completed_count(),
        "today": session_manager.today_count(),
        "uptime": utils.format_duration(session_manager.uptime_seconds()),
        "waiting_sessions": [_session_card(s) for s in waiting],
        "completed_sessions": [_session_card(s) for s in completed],
    }
    body = json.dumps(result, ensure_ascii=False)
    return 200, body.encode("utf-8"), "application/json"


def admin_set_mode(form: Dict[str, List[str]]) -> Tuple[int, bytes, str]:
    """POST /admin/set_mode 切换服务模式：mode=manual(人工回复) / mode=auto(自动回复)。"""
    mode = (form.get("mode") or [""])[0]
    if mode == "auto":
        enabled = True
    elif mode == "manual":
        enabled = False
    else:
        result = {"ok": False, "error": "mode 参数必须是 manual 或 auto"}
        body = json.dumps(result, ensure_ascii=False)
        return 200, body.encode("utf-8"), "application/json"
    current = session_manager.set_auto_reply(enabled)
    result = {"ok": True, "mode": "auto" if current else "manual"}
    body = json.dumps(result, ensure_ascii=False)
    return 200, body.encode("utf-8"), "application/json"