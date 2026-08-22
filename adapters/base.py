# -*- coding: utf-8 -*-
"""ChatAdapter 抽象基类：平台可替换（微信 / 企微 / Telegram…）。"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ChatAdapter(ABC):
    """平台适配接口。所有与 IM 客户端交互的能力收敛于此。"""

    target_name: str

    @abstractmethod
    def current_chat_name(self) -> str:
        """主窗口当前打开的会话名。"""

    @abstractmethod
    def list_sessions(self) -> list[str]:
        """可见会话名列表。"""

    @abstractmethod
    def switch_to(self, name: str | None = None) -> bool:
        """切到指定会话（缺省 = 目标会话）。成功 True。"""

    @abstractmethod
    def get_session_info(self, name: str | None = None) -> dict:
        """{"exists": bool, "unread": int, "last_line": str}（单次爬取）。"""

    @abstractmethod
    def get_all_messages(self, window: int = 20) -> list[dict[str, str]]:
        """最近消息 → [{"role": "me"|"her", "text": str}]。"""

    @abstractmethod
    def send(self, text: str) -> None:
        """发送文本到当前会话；失败抛异常。"""

    def recover_ui(self) -> None:  # 可选
        """客户端卡死恢复（可选实现）。"""
