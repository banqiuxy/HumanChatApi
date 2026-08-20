# -*- coding: utf-8 -*-
"""
工具函数模块（utils.py）
提供 sid 生成、时间戳、图片检测、文本预览、时长格式化等通用辅助函数。
"""
import datetime
import time
import uuid
from typing import Any, Dict, List


def build_sid(prefix: str = "hc-") -> str:
    """生成唯一会话 ID。"""
    return prefix + uuid.uuid4().hex[:16]


def build_response_id(prefix: str = "human-chat-") -> str:
    """生成 OpenAI 响应 id。"""
    return prefix + uuid.uuid4().hex[:12]


def now_str() -> str:
    """格式化当前时间，如 2024-01-01 12:30:45。"""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def today_str() -> str:
    """当前自然日，如 2024-01-01。"""
    return datetime.date.today().strftime("%Y-%m-%d")


def format_duration(seconds: float) -> str:
    """将秒数格式化为人类可读的运行时长。"""
    seconds = int(seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}小时{m}分"
    if m:
        return f"{m}分{s}秒"
    return f"{s}秒"


def extract_first_text(raw_messages: List[Dict[str, Any]]) -> str:
    """提取会话首条文本作为卡片预览。"""
    for msg in raw_messages:
        for block in msg.get("content", []):
            if block.get("type") == "text" and block.get("text"):
                text = block["text"].strip()
                if text:
                    return text[:40] + ("..." if len(text) > 40 else "")
    return "[仅图片消息]"


def check_has_image(raw_messages: List[Dict[str, Any]]) -> bool:
    """判断会话中是否包含图片。"""
    for msg in raw_messages:
        for block in msg.get("content", []):
            if isinstance(block, dict) and block.get("type") == "image_url":
                return True
    return False


def current_timestamp() -> int:
    """当前 Unix 时间戳（秒）。"""
    return int(time.time())