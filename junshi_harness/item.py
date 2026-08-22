# -*- coding: utf-8 -*-
"""Item：Turn 内的原子事件（消息/推理/工具调用/审批/错误）。

借鉴 Codex Harness 的 Thread → Turn → Item 三级抽象：
前端不再解析日志字符串，直接消费结构化 Item 流。
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any

# Item 类型常量（前端按类型渲染）
TYPE_HER_MESSAGE = "her_message"
TYPE_HER_MEDIA = "her_media"                  # 语音/图片/表情占位（不触发回复）
TYPE_SIGNAL_DETECTED = "signal_detected"
TYPE_KB_RETRIEVED = "kb_retrieved"
TYPE_FEWSHOT_LOADED = "fewshot_loaded"
TYPE_CONTEXT_BUILT = "context_built"
TYPE_LLM_REASONING = "llm_reasoning"          # 流式 delta
TYPE_VARIANT_GENERATED = "variant_generated"
TYPE_APPROVAL_REQUESTED = "approval_requested"
TYPE_APPROVAL_DECIDED = "approval_decided"
TYPE_MESSAGE_SENT = "message_sent"
TYPE_SEND_FAILED = "send_failed"
TYPE_REPLY_PREVIEW = "reply_preview"          # 仅预览模式的候选（可复制）
TYPE_MEMORY_UPDATED = "memory_updated"
TYPE_ERROR = "error"
TYPE_LOG = "log"


@dataclass
class Item:
    type: str
    data: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    turn_id: str | None = None
    thread_id: str | None = None
    seq: int = 0
    ts: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_row(cls, row) -> "Item":
        import json
        return cls(
            type=row["type"],
            data=json.loads(row["data"] or "{}"),
            id=row["id"],
            turn_id=row["turn_id"],
            thread_id=row["thread_id"],
            seq=row["seq"],
            ts=row["created_at"],
        )
