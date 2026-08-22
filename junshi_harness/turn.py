# -*- coding: utf-8 -*-
"""Turn 执行器：从触发到回复的完整状态机（干净版）。

Turn 状态机：
    running ──► waiting_approval ──► completed / rejected
         │
         ├──► completed            （自动发送成功 / 空回复放弃）
         ├──► aborted_retry        （可重试失败：生成抖动，非终态）
         └──► failed               （终态：连续 N 次失败，放弃）

去重契约（runtime 依赖）：
    终态   = {completed, failed, rejected}          → 消息已消费，不再处理
    非终态 = {running, waiting_approval, aborted_retry} → 允许再次触发

每一步发射结构化 Item；send 通过注入回调完成（执行器不持有 adapter）。
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Protocol

from junshi_domain import humanize as humanize_mod
from junshi_domain import kb as kb_mod
from junshi_domain import prompts as prompts_mod
from junshi_domain.fewshot import retrieve_fewshot
from junshi_domain.signals import build_signal_block, detect_signals
from .approval import ApprovalEngine, ApprovalLevel
from .config import Config
from .context import ContextManager
from .event_bus import EventBus
from .item import (Item, TYPE_APPROVAL_REQUESTED, TYPE_CONTEXT_BUILT,
                   TYPE_ERROR, TYPE_FEWSHOT_LOADED, TYPE_HER_MESSAGE,
                   TYPE_KB_RETRIEVED, TYPE_MESSAGE_SENT, TYPE_REPLY_PREVIEW,
                   TYPE_SEND_FAILED, TYPE_SIGNAL_DETECTED,
                   TYPE_VARIANT_GENERATED)
from .policy import Policy
from .store import Store
from .thread import ThreadManager

# 终态集合：runtime 用它做消息去重（处理过就不再触发）
TERMINAL_STATUSES = ("completed", "failed", "rejected")


class ProviderLike(Protocol):
    """LLM Provider 最小接口（结构化类型，无需继承）。"""

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.85,
             max_tokens: int = 300, timeout: int = 30) -> str: ...


SendFn = Callable[[str], None]


def trigger_hash(text: str) -> str:
    return hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:16]


class TurnExecutor:
    def __init__(self, cfg: Config, store: Store, bus: EventBus,
                 threads: ThreadManager, contexts: ContextManager,
                 approval: ApprovalEngine, policy: Policy):
        self.cfg = cfg
        self.store = store
        self.bus = bus
        self.threads = threads
        self.contexts = contexts
        self.approval = approval
        self.policy = policy
        self._provider: ProviderLike | None = None
        self._should_stop: Callable[[], bool] | None = None
        self._send_fn: SendFn | None = None

    def bind_provider(self, provider: ProviderLike) -> None:
        self._provider = provider

    def bind_sender(self, send_fn: SendFn) -> None:
        """绑定真实发送通道（adapter.send）。审批通过后由 approve() 使用。"""
        self._send_fn = send_fn

    def bind_provider(self, provider: ProviderLike) -> None:
        self._provider = provider

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------
    def execute(self, thread: dict, text: str, history: list[dict],
                distance: str | None = None,
                send_fn: SendFn | None = None,
                should_stop: Callable[[], bool] | None = None) -> dict[str, Any]:
        """执行一轮，返回：
        {"turn_id", "status", "variants", "best", "reply",
         "decision", "signals", "sent": bool}
        生成失败且未达放弃阈值时抛出原异常（runtime 捕获后下轮重试）。
        should_stop: 发送前门控（停止监听时取消发送，消息留待重试）。
        """
        self._should_stop = should_stop
        thash = trigger_hash(text)
        turn_id = self.store.create_turn(thread["id"], thash, text)

        # 单一 emit 实例：发布到总线 + 落库（同一份 Item）
        def emit(itype: str, data: dict) -> None:
            item = Item(type=itype, data=data, turn_id=turn_id,
                        thread_id=thread["id"])
            self.bus.publish(item)
            try:
                self.store.add_item(item)
            except Exception:
                pass  # 落库失败不阻断流程

        emit(TYPE_HER_MESSAGE, {"text": text})

        result: dict[str, Any] = {"turn_id": turn_id, "status": "running",
                                  "variants": [], "best": 0, "reply": "",
                                  "decision": None, "signals": [], "sent": False}
        try:
            self._run(thread, turn_id, text, history, distance, emit,
                      thash, send_fn, result)
        except Exception as e:
            give_up = self.policy.note_gen_fail(thash)
            if give_up:
                self.store.set_turn_status(turn_id, "failed", str(e))
                result["status"] = "failed"
                emit(TYPE_ERROR, {"error": str(e), "gave_up": True})
                return result
            # 可重试：标 aborted_retry（非终态），异常继续抛给 runtime 记日志
            self.store.set_turn_status(turn_id, "aborted_retry", str(e))
            emit(TYPE_ERROR, {"error": str(e), "retry": True})
            raise

        self.policy.clear_gen_fail(thash)
        self.policy.clear_abort(thash)
        return result

    # ------------------------------------------------------------------
    # 内部流水线
    # ------------------------------------------------------------------
    def _run(self, thread: dict, turn_id: str, text: str, history: list[dict],
             distance: str | None, emit, thash: str,
             send_fn: SendFn | None, result: dict[str, Any]) -> None:
        cfg_ov = thread.get("config_override") or {}
        llm = self.cfg.llm(cfg_ov)
        if self._provider is None:
            from providers.openai_compat import OpenAICompatProvider
            self.bind_provider(OpenAICompatProvider(
                api_key=llm["api_key"], base_url=llm["base_url"],
                model=llm["model"],
                max_retries=int(llm.get("max_retries", 2))))
        assert self._provider is not None

        # ---- 1. pre-turn：信号 + 知识 + 范例 + 上下文 ----
        signals = detect_signals(text)
        result["signals"] = signals
        emit(TYPE_SIGNAL_DETECTED, {"signals": signals})

        kb_text = kb_mod.retrieve(signals)
        emit(TYPE_KB_RETRIEVED, {"chars": len(kb_text),
                                 "files": kb_mod.used_kb_files(signals)})

        fs_cfg = self.cfg.fewshot(cfg_ov)
        fewshot: list[str] = []
        if fs_cfg.get("enabled"):
            fewshot = retrieve_fewshot(text, thread["target_name"],
                                       int(fs_cfg.get("k", 3)))
        if fewshot:
            emit(TYPE_FEWSHOT_LOADED, {"count": len(fewshot)})

        ctx = self.contexts.build_context(thread, history)
        emit(TYPE_CONTEXT_BUILT, {"recent": len(ctx.recent_messages),
                                  "memory_chars": len(ctx.memory_block)})

        # ---- 2. prompt + LLM 多候选 ----
        system_prompt = prompts_mod.build_system_prompt(
            target_name=thread["target_name"], distance=distance,
            kb_text=kb_text, fewshot=fewshot,
            target_profile=(self.cfg.load().get("target") or {}).get("profile"),
        )
        n = 3
        user = prompts_mod.VARIANTS_TEMPLATE.format(
            history=prompts_mod.format_history(ctx.recent_messages),
            memory=ctx.memory_block or "（暂无）",
            latest=text.strip(),
            signal_block=build_signal_block(signals),
            n=n)
        raw = self._provider.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user}],
            temperature=float(llm.get("temperature", 0.85)),
            max_tokens=600,
            timeout=int(llm.get("timeout_seconds", 30)))
        variants, best = self._parse_variants(raw, n)
        result["variants"], result["best"] = variants, best
        emit(TYPE_VARIANT_GENERATED, {"variants": variants, "best": best})

        # 空回复保护：全部为空 → 放弃（终态 completed，不发送）
        reply = variants[best] if best < len(variants) else ""
        result["reply"] = reply
        if not any(v.strip() for v in variants):
            self.store.set_turn_status(turn_id, "completed", "空回复放弃")
            result["status"] = "completed"
            return

        # 可选二次去味 pass
        hz = self.cfg.humanize(cfg_ov)
        if hz.get("enabled") and hz.get("mode") == "pass":
            variants = [humanize_mod.humanize_reply(self._provider, v)
                        for v in variants]
            reply = variants[best] if best < len(variants) else ""
            result["variants"], result["reply"] = variants, reply

        # ---- 3. 审批检查 + 回复模式 ----
        decision = self.approval.check(reply, distance=distance)
        result["decision"] = {"level": decision.level.value,
                              "rule": decision.rule_id,
                              "reason": decision.reason}
        mode = self.cfg.monitor(cfg_ov).get("reply_mode", "confirm")

        # confirm 模式：所有回复一律转人工；MANUAL 规则命中照旧
        if mode == "confirm" or decision.level == ApprovalLevel.MANUAL:
            rule_id = decision.rule_id or ("manual_confirm" if mode == "confirm" else "")
            reason = decision.reason or ("确认模式：等待人工选择后发送"
                                         if mode == "confirm" else "需人工确认")
            aid = self.store.create_approval(turn_id, rule_id,
                                             reply, variants, best)
            self.store.set_turn_status(turn_id, "waiting_approval")
            result["status"] = "waiting_approval"
            emit(TYPE_APPROVAL_REQUESTED, {
                "approval_id": aid, "rule": rule_id,
                "reason": reason, "reply": reply,
                "variants": variants, "best": best})
            return

        # preview 模式：只生成不发送，前端展示候选供复制
        if mode == "preview":
            emit(TYPE_REPLY_PREVIEW, {"variants": variants, "best": best})
            self.store.set_turn_status(turn_id, "completed", "preview")
            result["status"] = "completed"
            return

        # auto 模式 → 发送前停止门控（停止监听立即取消，消息下轮重试）
        if self._should_stop and self._should_stop():
            self.store.set_turn_status(turn_id, "aborted_retry",
                                       "停止监听，取消发送")
            result["status"] = "aborted_retry"
            emit(TYPE_ERROR, {"error": "已停止监听，取消发送（消息将重试）",
                              "retry": True})
            return
        self._do_send(turn_id, reply, send_fn, emit, result)

    # ------------------------------------------------------------------
    def _do_send(self, turn_id: str, reply: str, send_fn: SendFn | None,
                 emit, result: dict[str, Any]) -> None:
        if send_fn is None:
            # 无发送通道（dry）：视为完成但不发送
            self.store.set_turn_status(turn_id, "completed", "dry")
            result["status"] = "completed"
            return
        try:
            send_fn(reply)
        except Exception as e:
            emit(TYPE_SEND_FAILED, {"error": str(e)})
            # 发送失败转待确认（人工重发兜底，不丢回复）
            aid = self.store.create_approval(turn_id, "send_failed",
                                             reply, result["variants"],
                                             result["best"])
            self.store.set_turn_status(turn_id, "waiting_approval")
            result["status"] = "waiting_approval"
            result["sent"] = False
            emit(TYPE_APPROVAL_REQUESTED, {
                "approval_id": aid, "rule": "send_failed",
                "reason": f"自动发送失败：{e}", "reply": reply,
                "variants": result["variants"], "best": result["best"]})
            return
        self.policy.note_sent()
        self.store.set_turn_status(turn_id, "completed")
        result["status"] = "completed"
        result["sent"] = True
        emit(TYPE_MESSAGE_SENT, {"text": reply})

    # ------------------------------------------------------------------
    # 审批决策（web 层调用）
    # ------------------------------------------------------------------
    def approve(self, approval_id: str,
                variant_index: int | None = None) -> dict[str, Any]:
        """批准待确认回复（可指定候选）：真实发送，成功才完结 Turn。"""
        pending = {a["id"]: a for a in self.store.pending_approvals()}
        ap = pending.get(approval_id)
        if not ap:
            raise ValueError("审批不存在或已处理")
        if self._send_fn is None:
            raise RuntimeError("发送通道未绑定（适配器不可用）")
        variants: list[str] = ap["variants"]
        best = int(ap["best"])
        idx = best if variant_index is None else int(variant_index)
        reply = variants[idx] if 0 <= idx < len(variants) and variants[idx].strip() \
            else ap["reply"]
        turn_id = ap["turn_id"]
        thread_id = ap.get("thread_id")

        def emit(itype: str, data: dict) -> None:
            item = Item(type=itype, data=data, turn_id=turn_id,
                        thread_id=thread_id)
            self.bus.publish(item)
            try:
                self.store.add_item(item)
            except Exception:
                pass

        # 真实发送；失败 → 保持待确认可重试（不丢回复）
        try:
            self._send_fn(reply)
        except Exception as e:
            emit(TYPE_SEND_FAILED, {"error": f"批准后发送失败：{e}"})
            return {"status": "waiting_approval", "sent": False,
                    "error": f"发送失败：{e}（仍待确认，可重试）"}

        emit(TYPE_MESSAGE_SENT, {"text": reply})
        self.store.decide_approval(approval_id, "approved")
        self.store.set_turn_status(turn_id, "completed")
        self.policy.note_sent()
        return {"status": "completed", "sent": True, "reply": reply}

    def reject(self, approval_id: str) -> dict[str, Any]:
        """拒绝待确认回复：Turn 终结为 rejected，不再发送。"""
        pending = {a["id"]: a for a in self.store.pending_approvals()}
        ap = pending.get(approval_id)
        if not ap:
            raise ValueError("审批不存在或已处理")
        turn_id = ap["turn_id"]
        self.store.decide_approval(approval_id, "rejected")
        self.store.set_turn_status(turn_id, "rejected", "人工拒绝")
        return {"status": "rejected"}

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_variants(raw: str, n: int) -> tuple[list[str], int]:
        from providers.openai_compat import extract_json_object
        data = extract_json_object(raw)
        variants: list[str] = []
        best = 0
        if data:
            rv = data.get("variants") or []
            if isinstance(rv, list) and rv:
                variants = [humanize_mod.clean_reply(str(v)) for v in rv][:n]
                try:
                    best = int(data.get("best") or 0)
                except (TypeError, ValueError):
                    best = 0
        if not variants:  # 按行兜底
            for line in raw.strip().splitlines():
                line = line.strip().lstrip("0123456789.、 ")
                if line and not line.startswith(("{", "}", '"',
                                                 "variants", "best")):
                    variants.append(humanize_mod.clean_reply(line))
                if len(variants) >= n:
                    break
        if not variants:
            variants = [""] * n
        variants += [""] * (n - len(variants))
        best = max(0, min(best, n - 1))
        return variants, best
