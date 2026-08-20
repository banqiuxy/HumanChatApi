# -*- coding: utf-8 -*-
"""
消息清洗模块（message_filter.py）
递归遍历 messages，剔除 video/audio/tools 相关字段，仅保留 text/image_url。
V1.0 功能边界：禁止音视频、禁止 ToolCall/FunctionCall。
"""
from typing import Any, Dict, List


class MessageFilter:
    """消息清洗规则。"""

    # 需要被整体删除的内容区块类型
    DROP_CONTENT_TYPES = frozenset({"video", "audio"})
    # 保留的内容区块类型
    KEEP_CONTENT_TYPES = frozenset({"text", "image_url"})
    # 需要从请求顶层删除的工具相关字段
    DROP_TOP_FIELDS = ("tools", "function_call", "tool_choice")

    @staticmethod
    def clean_content(content: Any) -> List[Dict[str, Any]]:
        """
        清洗单个 message 的 content。

        - content 为字符串：原样保留为唯一文本项
        - content 为数组：丢弃 video/audio 类型，保留 text/image_url
        - content 为 None：返回空
        """
        if content is None:
            return []

        cleaned: List[Dict[str, Any]] = []
        if isinstance(content, str):
            cleaned.append({"type": "text", "text": content})
            return cleaned

        if isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                block_type = block.get("type", "")
                if block_type in MessageFilter.DROP_CONTENT_TYPES:
                    # 视频/音频区块直接丢弃
                    continue
                if block_type in MessageFilter.KEEP_CONTENT_TYPES:
                    # 仅保留文本与图片
                    cleaned.append(block)
            return cleaned

        return cleaned

    @staticmethod
    def clean_message(msg: Dict[str, Any]) -> Dict[str, Any]:
        """清洗单条 message（role + content），剔除内嵌的工具字段。"""
        role = msg.get("role", "user")
        cleaned = {
            "role": role,
            "content": MessageFilter.clean_content(msg.get("content")),
        }
        # 防御：剔除 message 内部可能嵌套的 tool 相关字段
        for field in ("tool_calls", "function_call"):
            cleaned.pop(field, None)
        return cleaned

    @staticmethod
    def clean_request(payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        清洗顶层请求：删除 tools / function_call / tool_choice 等工具字段。
        返回清洗后的新字典（不改动原对象）。
        """
        payload = dict(payload)
        for field in MessageFilter.DROP_TOP_FIELDS:
            payload.pop(field, None)
        return payload

    @staticmethod
    def process_messages(messages: List[Any]) -> List[Dict[str, Any]]:
        """
        处理整个 messages 列表，返回清洗后的 raw_messages。
        跳过非字典元素，跳过清洗后完全为空的内容。
        """
        raw_messages: List[Dict[str, Any]] = []
        for msg in messages:
            if not isinstance(msg, dict):
                continue
            cleaned = MessageFilter.clean_message(msg)
            if cleaned["content"] or cleaned["role"] in ("assistant", "system"):
                raw_messages.append(cleaned)
        return raw_messages