# -*- coding: utf-8 -*-
"""军师建议服务：键盘核心，复用 junshi_domain + providers。

键盘不需要 wxauto 自动发送，只需要"复制她的消息 → 3 条建议 + 信号 + 记忆 + 审批"。
本服务把域层纯函数串成一条可测试的流水线，供 cloud API 调用。
"""
from __future__ import annotations

import re
from typing import Any

from junshi_domain import humanize as humanize_mod
from junshi_domain import kb as kb_mod
from junshi_domain import prompts as prompts_mod
from junshi_domain import style as style_mod
from junshi_domain.distance import detect_distance
from junshi_domain.fewshot import retrieve_fewshot
from junshi_domain.signals import build_signal_block, detect_signals
from junshi_harness.approval import ApprovalEngine
from junshi_harness.config import Config
from providers.openai_compat import OpenAICompatProvider


class SuggestService:
    """一次生成 3 条的建议流水线（无状态，可单测）。"""

    def __init__(self, cfg: Config | None = None, *,
                 base_url: str | None = None, api_key: str | None = None,
                 model: str | None = None, approval_cfg: dict | None = None):
        llm = (cfg or Config()).llm() if cfg else {}
        self.provider = OpenAICompatProvider(
            api_key=api_key or llm.get("api_key", ""),
            base_url=base_url or llm.get("base_url", ""),
            model=model or llm.get("model", "deepseek-chat"),
            max_retries=2)
        self.approval = ApprovalEngine(approval_cfg or (cfg.approval_cfg() if cfg else {}))
        self._temperature = 0.85
        self._timeout = 30

    def _load_memory(self, memory_lines: list[str]) -> str:
        """把对象记忆条目合成 prompt 段落。memory_lines: ["key: value", ...]"""
        if not memory_lines:
            return "（暂无）"
        return "\n".join(f"- {m}" for m in memory_lines[:12])

    def suggest(self, object_name: str, latest: str,
                history: list[dict[str, str]] | None = None,
                me_city: str = "", her_city: str = "",
                memory_lines: list[str] | None = None,
                n: int = 3) -> dict[str, Any]:
        """核心入口。返回:
        {signals, signal_block, distance, memory_block, variants, best,
         needs_approval, reason, elapsed_ms, model}
        """
        import time
        history = history or []
        t0 = time.monotonic()
        latest = (latest or "").strip()

        signals = detect_signals(latest)
        distance = detect_distance(history, me_city, her_city)
        kb_text = kb_mod.retrieve(signals)
        fewshot = retrieve_fewshot(latest, object_name, k=3)
        memory_block = self._load_memory(memory_lines or [])

        system_prompt = prompts_mod.build_system_prompt(
            target_name=object_name, distance=distance, kb_text=kb_text,
            fewshot=fewshot)
        user = prompts_mod.VARIANTS_TEMPLATE.format(
            history=prompts_mod.format_history(history),
            memory=memory_block,
            latest=latest,
            signal_block=build_signal_block(signals),
            n=n)
        raw = self.provider.chat(
            [{"role": "system", "content": system_prompt},
             {"role": "user", "content": user}],
            temperature=self._temperature,
            max_tokens=600,
            timeout=self._timeout)
        variants, best = self._parse_variants(raw, n)

        # 审批拦截：花钱/见面等风险标红
        needs = [self.approval.check(v, distance=distance) for v in variants]
        has_approval = any(d.blocked for d in needs)
        reason = next((d.reason for d in needs if d.blocked), "")

        return {
            "signals": signals,
            "signal_block": build_signal_block(signals),
            "distance": distance,
            "memory_block": memory_block,
            "variants": variants,
            "best": best,
            "needs_approval": has_approval,
            "approval_reason": reason,
            "elapsed_ms": int((time.monotonic() - t0) * 1000),
            "model": self.provider.model,
        }

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
        if not variants:
            for line in raw.strip().splitlines():
                line = line.strip().lstrip("0123456789.、 ")
                if line and not line.startswith(("{", "}", '"', "variants", "best")):
                    variants.append(humanize_mod.clean_reply(line))
                if len(variants) >= n:
                    break
        if not variants:
            variants = [""] * n
        variants += [""] * (n - len(variants))
        best = max(0, min(best, n - 1))
        return variants, best


# ---- 从聊天记录提取风格（粘贴分析，不依赖 ChatLab）----
def extract_style(text_lines: list[str]) -> dict:
    """用 LLM 从用户粘贴的聊天记录提炼风格档案。返回 style_profile dict。"""
    import json
    from providers.openai_compat import extract_json_object

    sample = "\n".join(text_lines)[:6000]
    system = (
        "你是语言风格分析师。从下面的微信聊天记录中提炼「我」的说话风格。\n"
        "输出严格 JSON（不要其他文字）：\n"
        '{"tone": "整体语气", "humor_style": "调侃方式", '
        '"care_style": "关心表达", "style_features": ["特点1","特点2"], '
        '"catchphrases": ["口头禅1","口头禅2"]}\n'
        "只输出 JSON。")
    cfg = Config()
    llm = cfg.llm()
    p = OpenAICompatProvider(api_key=llm["api_key"], base_url=llm["base_url"],
                             model=llm["model"], max_retries=0)
    raw = p.chat([{"role": "system", "content": system},
                  {"role": "user", "content": sample}],
                 temperature=0.3, max_tokens=400, timeout=30)
    data = extract_json_object(raw) or {}
    # 规范化字段
    for k in ("style_features", "catchphrases"):
        if isinstance(data.get(k), list):
            data[k] = [str(x) for x in data[k] if str(x).strip()][:8]
    return {k: v for k, v in data.items() if v}
