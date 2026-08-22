# -*- coding: utf-8 -*-
"""执行策略：限流 / 时段 / 并发防护（ExecPolicy 理念的落地）。

实例持有运行时计数（进程内），重启即重置 —— 与持久化的 Turn 记录互补。
"""
from __future__ import annotations

import time


class Policy:
    def __init__(self, monitor_cfg: dict | None = None):
        cfg = monitor_cfg or {}
        self.min_interval = float(cfg.get("min_interval_between_replies_seconds", 60))
        self.max_per_hour = int(cfg.get("max_replies_per_hour", 30))
        self.switch_debounce = float(cfg.get("switch_debounce_seconds", 5))
        self.gen_fail_give_up = int(cfg.get("gen_fail_give_up", 3))

        self._last_reply_ts: float = 0.0
        self._reply_times: list[float] = []
        self._last_switch_ts: float = 0.0
        self._gen_fail: dict[str, int] = {}   # trigger_hash → 连续失败次数
        self._abort_count: dict[str, int] = {}  # trigger_hash → 锚定中断次数

    # ---- 发送限流 ----
    def can_send(self) -> tuple[bool, str]:
        now = time.time()
        if now - self._last_reply_ts < self.min_interval:
            remain = int(self.min_interval - (now - self._last_reply_ts))
            return False, f"冷却中（还差 {remain}s）"
        hour_ago = now - 3600
        self._reply_times = [t for t in self._reply_times if t > hour_ago]
        if len(self._reply_times) >= self.max_per_hour:
            return False, f"已达每小时上限（{self.max_per_hour} 条）"
        return True, ""

    def note_sent(self) -> None:
        now = time.time()
        self._last_reply_ts = now
        self._reply_times.append(now)

    # ---- 切回防抖 ----
    def allow_switch(self) -> bool:
        now = time.time()
        if now - self._last_switch_ts < self.switch_debounce:
            return False
        self._last_switch_ts = now
        return True

    # ---- 生成失败重试 ----
    def note_gen_fail(self, trigger_hash: str) -> bool:
        """记录一次生成失败。返回是否已达到放弃阈值。"""
        n = self._gen_fail.get(trigger_hash, 0) + 1
        self._gen_fail[trigger_hash] = n
        return n >= self.gen_fail_give_up

    def clear_gen_fail(self, trigger_hash: str) -> None:
        self._gen_fail.pop(trigger_hash, None)

    # ---- 锚定中断保护 ----
    def note_abort(self, trigger_hash: str) -> bool:
        """锚定/切回中断一轮。连续 3 轮仍不过 → 放弃（防死循环）。"""
        n = self._abort_count.get(trigger_hash, 0) + 1
        self._abort_count[trigger_hash] = n
        return n >= 3

    def clear_abort(self, trigger_hash: str) -> None:
        self._abort_count.pop(trigger_hash, None)
