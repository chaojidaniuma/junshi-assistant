# -*- coding: utf-8 -*-
"""Thread：与某个对象的完整关系会话。替代全局 CURRENT_TARGET + State。

一个 Thread = 一个对象，天然支持多对象并行；带配置覆盖。
"""
from __future__ import annotations

import time

from .store import Store


class ThreadManager:
    def __init__(self, store: Store):
        self.store = store

    def ensure_thread(self, target_name: str,
                      target_meta: dict | None = None,
                      config_override: dict | None = None) -> dict:
        """按对象名取活跃 Thread，不存在则创建。"""
        t = self.store.find_thread_by_target(target_name)
        if t:
            if target_meta or config_override:
                t["target_meta"] = {**t.get("target_meta", {}), **(target_meta or {})}
                t["config_override"] = {**t.get("config_override", {}), **(config_override or {})}
                self.store.upsert_thread(t)
            return t
        new = {"id": None, "target_name": target_name,
               "target_meta": target_meta or {}, "status": "active",
               "config_override": config_override or {}, "created_at": time.time()}
        new["id"] = self.store.upsert_thread(new)
        return new

    def get(self, thread_id: str) -> dict | None:
        return self.store.get_thread(thread_id)

    def list(self) -> list[dict]:
        return self.store.list_threads()

    def set_status(self, thread_id: str, status: str) -> None:
        t = self.store.get_thread(thread_id)
        if t:
            t["status"] = status
            self.store.upsert_thread(t)

    def update_memory(self, thread_id: str, category: str, key: str,
                      value: str, turn_id: str | None = None) -> None:
        self.store.set_memory(thread_id, category, key, value, turn_id)

    def get_memory(self, thread_id: str, category: str | None = None) -> list[dict]:
        return self.store.get_memory(thread_id, category)

    @staticmethod
    def memory_summary(memory_rows: list[dict], max_chars: int = 600) -> str:
        """把记忆行压缩为 prompt 段落（按类别分组）。"""
        if not memory_rows:
            return "（暂无）"
        by_cat: dict[str, list[str]] = {}
        for r in memory_rows[:30]:
            by_cat.setdefault(r["category"], []).append(f"{r['key']}: {r['value']}")
        labels = {"mood": "近期情绪", "preference": "她的喜好",
                  "event": "近期事件/约定", "effective": "有效的回复",
                  "note": "备注"}
        lines = []
        budget = max_chars
        for cat, items in by_cat.items():
            label = labels.get(cat, cat)
            block = f"- {label}：" + "；".join(items[:5])
            if len(block) > budget:
                break
            lines.append(block)
            budget -= len(block)
        return "\n".join(lines) if lines else "（暂无）"
