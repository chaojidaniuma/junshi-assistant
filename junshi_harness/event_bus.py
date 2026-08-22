# -*- coding: utf-8 -*-
"""流式事件总线：类型安全的 pub/sub，替代字符串日志解析。

- publish(item)：所有订阅者收到 Item（结构化，含类型与数据）
- subscribe(event_types=None)：按类型过滤订阅（None = 全部）
- Web 层把 Item 直接序列化为 JSON 推给 WebSocket
"""
from __future__ import annotations

import threading
from collections import deque
from typing import Callable, Iterable

from .item import Item


class EventBus:
    def __init__(self, history_max: int = 500):
        self._subs: list[tuple[set[str] | None, Callable[[Item], None]]] = []
        self._lock = threading.Lock()
        self._history: deque[dict] = deque(maxlen=history_max)

    def publish(self, item: Item) -> None:
        with self._lock:
            self._history.append(item.to_dict())
            subs = list(self._subs)
        for types, cb in subs:
            try:
                if types is None or item.type in types:
                    cb(item)
            except Exception:
                pass  # 单个订阅者异常不阻断总线

    def subscribe(self, callback: Callable[[Item], None],
                  event_types: Iterable[str] | None = None) -> Callable[[], None]:
        types = set(event_types) if event_types is not None else None
        entry = (types, callback)
        with self._lock:
            self._subs.append(entry)

        def _unsubscribe():
            with self._lock:
                if entry in self._subs:
                    self._subs.remove(entry)
        return _unsubscribe

    def recent(self, limit: int = 100) -> list[dict]:
        with self._lock:
            return list(self._history)[-limit:]
