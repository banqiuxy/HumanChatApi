# -*- coding: utf-8 -*-
"""
数据模型模块（models.py）
纯标准库实现：使用 dataclass 定义数据结构，零第三方依赖。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Message:
    """单条消息（宽松结构，兼容 OpenAI 各类客户端）。"""
    role: str = "user"
    content: Any = None          # str | list[dict]
    name: Optional[str] = None


@dataclass
class ChatCompletionRequest:
    """OpenAI 兼容对话请求。"""
    model: Optional[str] = None
    messages: List[Any] = field(default_factory=list)
    stream: bool = False
    temperature: Optional[float] = None
    top_p: Optional[float] = None


@dataclass
class ChatCompletionResponse:
    """OpenAI 兼容对话响应。"""
    id: str
    object: str = "chat.completion"
    created: int = 0
    model: str = ""
    choices: List[Dict[str, Any]] = field(default_factory=list)
    usage: Dict[str, int] = field(default_factory=lambda: {
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
    })


@dataclass
class ModelInfo:
    """模型列表中单个模型项。"""
    id: str
    object: str = "model"
    created: int = 1750000000
    owned_by: str = "humanchatapi"


@dataclass
class Session:
    """
    内存会话结构（PRD 六、数据结构设计）：
        sid          唯一会话ID字符串
        time         请求时间戳
        raw_messages 清洗后的文本+图片上下文数组（本次请求）
        history      完整对话历史（含人工回复，持久保留）
        has_image    当前会话是否包含图片
        reply        人工回复，等待状态为 None
        status       waiting=等待回复 / completed=已回复(保留)
        event        threading.Event，用于阻塞/唤醒请求线程
        replied      是否已回复
    """
    sid: str
    time: str
    raw_messages: List[Dict[str, Any]]
    has_image: bool
    reply: Optional[str] = None
    status: str = "waiting"
    event: Any = None
    replied: bool = False
    history: List[Dict[str, Any]] = field(default_factory=list)