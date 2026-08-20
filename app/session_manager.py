# -*- coding: utf-8 -*-
"""
会话管理模块（session_manager.py）
内存会话：创建、存储、查询、关闭会话。

【重要】会话持久化规则（V1.0）：
- 客户端发起请求 → 创建会话，状态 waiting，阻塞等待人工回复
- 管理员提交回复 → 唤醒客户端请求线程，回复内容追加进会话历史，
  会话【不删除】、保留在后台（状态 completed），供回看完整上下文
- 只有管理员在后台【手动关闭会话】，会话才从内存中删除
- 服务重启 → 全部清空（内存存储）

纯标准库实现：threading.Lock 保证并发安全，threading.Event 阻塞/唤醒请求线程。
"""
import threading
from typing import Any, Dict, List, Optional

from . import utils
from .models import Session


class SessionManager:
    """内存会话管理器（单次持久化，手动关闭才删除）。"""

    def __init__(self) -> None:
        self._sessions: Dict[str, Session] = {}
        self._lock = threading.Lock()
        # 服务模式：False=人工回复 / True=自动回复（默认自动回复）
        self._auto_reply = True
        # 运行统计
        self._today = utils.today_str()
        self._today_count = 0
        self._start_time = utils.current_timestamp()

    # ------------------------------------------------------------------
    # 服务模式（人工回复 / 自动回复）
    # ------------------------------------------------------------------
    def set_auto_reply(self, enabled: bool) -> bool:
        """设置自动回复模式开关，返回当前模式（True=自动）。"""
        with self._lock:
            self._auto_reply = bool(enabled)
            return self._auto_reply

    def is_auto_reply(self) -> bool:
        """当前是否为自动回复模式。"""
        with self._lock:
            return self._auto_reply

    # ------------------------------------------------------------------
    # 统计
    # ------------------------------------------------------------------
    def _rollover_if_needed(self) -> None:
        today = utils.today_str()
        if today != self._today:
            self._today = today
            self._today_count = 0

    def bump_request(self) -> None:
        with self._lock:
            self._rollover_if_needed()
            self._today_count += 1

    def today_count(self) -> int:
        with self._lock:
            self._rollover_if_needed()
            return self._today_count

    def uptime_seconds(self) -> float:
        return utils.current_timestamp() - self._start_time

    # ------------------------------------------------------------------
    # 会话 CRUD
    # ------------------------------------------------------------------
    def create(self, raw_messages: List[Dict[str, Any]], has_image: bool) -> Session:
        """创建新会话（状态 waiting），返回会话对象。"""
        session = Session(
            sid=utils.build_sid(),
            time=utils.now_str(),
            raw_messages=raw_messages,
            history=list(raw_messages),      # 完整对话历史（含人工回复，持久保留）
            has_image=has_image,
            event=threading.Event(),
        )
        with self._lock:
            self._sessions[session.sid] = session
        return session

    def get(self, sid: str) -> Optional[Session]:
        return self._sessions.get(sid)

    def all_waiting(self) -> List[Session]:
        """返回所有等待人工回复的会话（waiting），按时间倒序。"""
        with self._lock:
            waiting = [s for s in self._sessions.values() if s.status == "waiting"]
            waiting.sort(key=lambda s: s.time, reverse=True)
            return waiting

    def all_completed(self) -> List[Session]:
        """返回所有已回复、仍保留在后台的会话（completed），按时间倒序。"""
        with self._lock:
            completed = [s for s in self._sessions.values() if s.status == "completed"]
            completed.sort(key=lambda s: s.time, reverse=True)
            return completed

    def waiting_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.status == "waiting")

    def completed_count(self) -> int:
        return sum(1 for s in self._sessions.values() if s.status == "completed")

    def submit_reply(self, sid: str, reply_content: str) -> bool:
        """
        提交人工回复：
        - 唤醒阻塞中的客户端请求线程（event.set）
        - 将 assistant 回复追加进会话历史（持久保留）
        - 会话状态置为 completed，【不删除】，等待管理员手动关闭
        返回是否成功。
        """
        session = self.get(sid)
        if session is None:
            return False
        with self._lock:
            if session.replied:
                return False
            session.reply = reply_content
            session.replied = True
            session.status = "completed"
            # 人工回复追加进完整历史，后台可回看
            session.history.append(
                {"role": "assistant", "content": [{"type": "text", "text": reply_content}]}
            )
            session.event.set()          # 唤醒阻塞的请求线程
        return True

    def close_session(self, sid: str) -> bool:
        """
        管理员手动关闭会话（唯一删除途径）。
        关闭后会话从内存中移除。
        """
        with self._lock:
            if sid not in self._sessions:
                return False
            self._sessions.pop(sid, None)
        return True


# 全局会话管理器单例
session_manager = SessionManager()