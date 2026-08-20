# -*- coding: utf-8 -*-
"""
OpenAI 兼容接口处理（api_routes.py）
纯标准库实现，供 http.server 路由分发调用，返回 (status, body_bytes, content_type)。

实现：
- POST /v1/chat/completions  人工接管对话接口（阻塞等待人工回复）
- GET  /v1/models            标准模型探测接口

会话生命周期：
  请求进入 → 创建会话(waiting) → 请求线程阻塞等待 →
  管理员后台回复（event.set 唤醒）→ 返回标准响应，
  会话【保留】在后台（completed），直到手动关闭。
"""
import json
import threading
from typing import Any, Dict, Tuple

from . import utils
from .message_filter import MessageFilter
from .session_manager import session_manager

# 探测接口返回的模拟模型列表（V1.0 固定）
MODELS = [
    {
        "id": "humanchat-v1-flash",
        "object": "model",
        "created": 1750000000,
        "owned_by": "humanchatapi",
    }
]

# 自动回复模式下的固定回复内容（不进入人工队列，一律回复此文本）
AUTO_REPLY_TEXT = "我暂时不在线，请等待我上线后再使用吧"


def _build_sse(resp_id: str, created: int, model: str, content: str) -> str:
    """
    构建 OpenAI 兼容的 SSE 流式响应文本（text/event-stream）。
    一次性推完：内容块 + 结束块 + [DONE]。
    """
    chunk1 = {
        "id": resp_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": content},
                "finish_reason": None,
            }
        ],
    }
    chunk2 = {
        "id": resp_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    parts = [
        "data: " + json.dumps(chunk1, ensure_ascii=False) + "\n\n",
        "data: " + json.dumps(chunk2, ensure_ascii=False) + "\n\n",
        "data: [DONE]\n\n",
    ]
    return "".join(parts)


def _build_json(resp_id: str, created: int, model: str, content: str) -> str:
    """构建 OpenAI 兼容的完整 JSON 响应文本。"""
    resp = {
        "id": resp_id,
        "object": "chat.completion",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {"role": "assistant", "content": content},
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
        },
    }
    return json.dumps(resp, ensure_ascii=False)


def list_models() -> Tuple[int, bytes, str]:
    """GET /v1/models 标准模型探测接口。"""
    body = json.dumps({"object": "list", "data": MODELS}, ensure_ascii=False)
    return 200, body.encode("utf-8"), "application/json"


def chat_completions(raw_body: bytes) -> Tuple[int, bytes, str]:
    """
    POST /v1/chat/completions
    请求线程创建会话后阻塞等待（threading.Event），
    管理员后台回复后 event.set 唤醒，返回标准 OpenAI 响应。

    兼容流式：客户端请求 stream=true 时返回 SSE（text/event-stream），
    否则返回完整 JSON。
    """
    try:
        payload: Dict[str, Any] = json.loads(raw_body.decode("utf-8"))
    except Exception:
        err = json.dumps({"error": {"message": "Invalid JSON body"}}, ensure_ascii=False)
        return 400, err.encode("utf-8"), "application/json"

    stream = bool(payload.get("stream", False))

    # 0. 自动回复模式：不管客户端请求发过来什么，一律固定回复，
    #    不进入人工会话队列
    if session_manager.is_auto_reply():
        session_manager.bump_request()
        resp_id = utils.build_response_id()
        created = utils.current_timestamp()
        model = payload.get("model", "humanchat-v1-flash")
        if stream:
            sse = _build_sse(resp_id, created, model, AUTO_REPLY_TEXT)
            return 200, sse.encode("utf-8"), "text/event-stream"
        body = _build_json(resp_id, created, model, AUTO_REPLY_TEXT)
        return 200, body.encode("utf-8"), "application/json"

    # 1. 顶层清洗：删除 tools / function_call / tool_choice
    payload = MessageFilter.clean_request(payload)

    # 2. 解析并清洗 messages（剔除 video/audio，仅保留 text/image_url）
    raw_messages = MessageFilter.process_messages(payload.get("messages", []))

    # 3. 判断是否含图片
    does_have_image = utils.check_has_image(raw_messages)

    # 4. 请求统计
    session_manager.bump_request()

    # 5. 创建会话（waiting），请求线程阻塞等待人工回复
    session = session_manager.create(raw_messages, does_have_image)

    # 6. 阻塞等待：管理员提交回复后 event.set() 唤醒
    session.event.wait()

    # 7. 组装标准 OpenAI 响应（兼容 stream）
    resp_id = utils.build_response_id()
    created = utils.current_timestamp()
    model = payload.get("model", "humanchat-v1-flash")
    reply = session.reply or ""
    if stream:
        sse = _build_sse(resp_id, created, model, reply)
        return 200, sse.encode("utf-8"), "text/event-stream"
    body = _build_json(resp_id, created, model, reply)
    # 8. 注意：会话【不删除】，保留在后台（completed），
    #    由管理员在后台手动关闭后才从内存移除。
    return 200, body.encode("utf-8"), "application/json"