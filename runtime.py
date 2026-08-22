# -*- coding: utf-8 -*-
"""MonitorRuntime：轮询循环 → Turn 触发器。

替代旧 main.py 上帝模块。职责单一：
    每个周期 → 空闲门控 → 切回目标 → 读历史 → 识别新消息（按终态 Turn 去重）
    → 为每条新消息调用 TurnExecutor.execute()

关键语义：
- 只有终态 Turn（completed/failed/rejected）的消息不再处理；
  aborted_retry / 无记录的消息会重试 —— 崩溃不丢消息
- 启动时 abort 遗留 running Turn，让中断消息下轮重试
"""
from __future__ import annotations

import re
import threading
import time

from adapters.base import ChatAdapter
from junshi_domain.distance import detect_distance
from junshi_harness.approval import ApprovalEngine
from junshi_harness.config import Config
from junshi_harness.context import ContextManager
from junshi_harness.event_bus import EventBus
from junshi_harness.item import Item, TYPE_HER_MEDIA, TYPE_LOG
from junshi_harness.item import TYPE_MEMORY_UPDATED
from junshi_harness.policy import Policy
from junshi_harness.store import Store
from junshi_harness.thread import ThreadManager
from junshi_harness.turn import TERMINAL_STATUSES, TurnExecutor, trigger_hash

_MEDIA_EXACT = {"[图片]", "[表情]", "[动画表情]", "[语音]", "[视频]",
                "[文件]", "[名片]", "[位置]", "[链接]", "图片"}
_MEDIA_PREFIX_RE = re.compile(r"^(语音|voice|视频|video|动画表情)", re.I)


def _is_emoticon_only(text: str) -> bool:
    """纯表情/媒体占位符：不触发回复（wxauto 会输出 `语音2"` 这类文本）。"""
    t = (text or "").strip()
    # 去掉包裹引号（含弯引号）再判断，避免 `语音2"` 漏网
    s = t.strip("\"'“”").strip()
    if not s or s == "图片":
        return True
    if s in _MEDIA_EXACT:
        return True
    if _MEDIA_PREFIX_RE.match(s) and len(s) <= 12:
        return True
    if t.startswith("[") and t.endswith("]"):
        return True
    if "动画表情" in s or s.startswith("表情"):
        return len(t) <= 12
    return False


class MonitorRuntime:
    def __init__(self, cfg: Config, store: Store, bus: EventBus,
                 adapter: ChatAdapter):
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.adapter = adapter

        self.threads = ThreadManager(store)
        self.policy = Policy(cfg.monitor())
        self.approval = ApprovalEngine(cfg.approval_cfg())
        self.contexts = ContextManager(self.threads,
                                       window=int(cfg.monitor().get("history_window", 20)))
        self.executor = TurnExecutor(cfg, store, bus, self.threads,
                                     self.contexts, self.approval, self.policy)
        # 绑定真实发送通道 → 审批批准后才能真正发出
        self.executor.bind_sender(adapter.send)
        self._seen_media: set[str] = set()  # 媒体占位去重（只提示一次）

        mon = cfg.monitor()
        self.poll_interval = float(mon.get("poll_interval_seconds", 3))
        self.history_window = int(mon.get("history_window", 20))

        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._last_seen_line = ""
        self._fail_counts: dict[str, int] = {}  # hash → 连续异常次数（进程内）

    # ------------------------------------------------------------------
    def log(self, msg: str) -> None:
        self.bus.publish(Item(type=TYPE_LOG, data={"msg": msg}))

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        # 崩溃恢复：遗留 running turn 标记为可重试
        n = self._abort_stale()
        if n:
            self.log(f"恢复：{n} 个中断的 Turn 将重试")
        self._thread = threading.Thread(target=self._loop, daemon=True,
                                        name="junshi-monitor")
        self._thread.start()
        self.log("监听已启动")

    def _abort_stale(self) -> int:
        with self.store._lock, self.store._conn() as conn:
            cur = conn.execute(
                "UPDATE turns SET status='aborted_retry', error='restart' "
                "WHERE status='running'")
            return cur.rowcount

    def stop(self) -> None:
        self._stop.set()
        self.log("监听已停止")

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    # ------------------------------------------------------------------
    def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.poll_once()
            except Exception as e:
                self.log(f"轮询异常: {e}")
            self._stop.wait(self.poll_interval)

    def poll_once(self) -> None:
        if self._stop.is_set():
            return
        target = self.cfg.load()["target"]["name"]
        if not target:
            return
        thread = self.threads.ensure_thread(target)
        info = self.adapter.get_session_info(target)
        if not info.get("exists"):
            return  # 目标不在可见列表且当前不在她会话

        # 空闲门控：无未读且列表末行未变 → 跳过昂贵的全量读聊天
        unread = int(info.get("unread") or 0)
        last_line = info.get("last_line") or ""
        if unread <= 0 and last_line == self._last_seen_line:
            return
        self._last_seen_line = last_line

        if self._stop.is_set():
            return

        # 未读 > 0 且当前不在她会话 → 切回（防抖）
        if unread > 0 and self.adapter.current_chat_name() != target:
            if not self.policy.allow_switch():
                return
            if not self.adapter.switch_to(target):
                self.log("切回目标会话失败，本轮跳过")
                return
            time.sleep(0.4)

        if self._stop.is_set():
            return

        history = self.adapter.get_all_messages(self.history_window)
        if not history:
            return
        distance = detect_distance(history,
                                   me_city=self.cfg.load()["location"]["me"],
                                   her_city=self.cfg.load()["location"]["her"])

        new_msgs = []
        for item in history:
            if item.get("role") != "her":
                continue
            text = str(item.get("text", "") or "").strip()
            if _is_emoticon_only(text):
                # 媒体占位（语音/图片/表情包）→ 不触发回复，但时间线提示一次
                h = trigger_hash(text)
                if h not in self._seen_media:
                    self._seen_media.add(h)
                    if len(self._seen_media) > 200:
                        self._seen_media.clear()
                    self.bus.publish(Item(type=TYPE_HER_MEDIA,
                                          data={"text": text[:16]}))
                continue
            h = trigger_hash(text)
            done = self.store.find_turn_by_hash(
                thread["id"], h, statuses=list(TERMINAL_STATUSES))
            in_flight = self.store.find_turn_by_hash(
                thread["id"], h, statuses=["running", "waiting_approval"])
            if done or in_flight:
                continue
            new_msgs.append(text)
        if not new_msgs:
            return

        for text in new_msgs[-3:]:  # 单周期最多处理 3 条，防积压风暴
            if self._stop.is_set():
                break
            h = trigger_hash(text)
            try:
                result = self.executor.execute(
                    thread, text, history, distance=distance,
                    send_fn=self.adapter.send,
                    should_stop=self._stop.is_set)
                self._fail_counts.pop(h, None)
                if result["status"] == "completed" and result.get("sent"):
                    self._note_memory(thread, text, result)
                elif result["status"] == "failed":
                    self.log(f"消息连续失败放弃: {text[:24]}")
            except Exception as e:
                fails = self._fail_counts.get(h, 0) + 1
                self._fail_counts[h] = fails
                self.log(f"Turn 异常（{fails} 次）: {e} — 下轮重试")

    def _note_memory(self, thread: dict, trigger_text: str, result: dict) -> None:
        """轻量记忆更新：有效回复 + 情绪趋势。"""
        tid = thread["id"]
        turn_id = result["turn_id"]
        try:
            self.threads.update_memory(tid, "effective",
                                       trigger_text[:24],
                                       result["reply"][:60], turn_id)
            moods = [s for s in result.get("signals", []) if s in ("sad", "angry")]
            if moods:
                self.threads.update_memory(tid, "mood",
                                           time.strftime("%m-%d %H:%M"),
                                           f"{','.join(moods)}:{trigger_text[:30]}",
                                           turn_id)
            self.bus.publish(Item(type=TYPE_MEMORY_UPDATED,
                                  data={"turn_id": turn_id},
                                  thread_id=tid, turn_id=turn_id))
        except Exception:
            pass
