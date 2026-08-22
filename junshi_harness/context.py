# -*- coding: utf-8 -*-
"""上下文管理器：滑动窗口 + 结构化记忆 + 压缩摘要（预留）。

Phase 1 实现：最近 N 条原文 + 关系记忆注入。
Phase 2 预留：LLM 压缩摘要、retained reasoning。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .thread import ThreadManager


@dataclass
class TurnContext:
    recent_messages: list[dict] = field(default_factory=list)
    compressed_summary: str = ""
    retained_reasoning: str = ""
    memory_block: str = ""


class ContextManager:
    def __init__(self, threads: ThreadManager, window: int = 20):
        self.threads = threads
        self.window = window

    def build_context(self, thread: dict, history: list[dict]) -> TurnContext:
        mem = self.threads.get_memory(thread["id"])
        return TurnContext(
            recent_messages=history[-self.window:],
            memory_block=ThreadManager.memory_summary(mem),
        )
