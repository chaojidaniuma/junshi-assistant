# -*- coding: utf-8 -*-
"""审批引擎：规则化分级审批（AUTO/SUGGEST/MANUAL），替代关键词匹配 + pending JSON。

- 规则带优先级，首条命中即生效
- 决策持久化到 store.approvals，可回溯
"""
from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass
from enum import Enum
from typing import Callable


class ApprovalLevel(str, Enum):
    AUTO = "auto"
    SUGGEST = "suggest"
    MANUAL = "manual"


@dataclass
class ApprovalDecision:
    level: ApprovalLevel
    rule_id: str
    reason: str

    @property
    def blocked(self) -> bool:
        return self.level == ApprovalLevel.MANUAL


MONEY_KEYWORDS = [
    "给你买", "请你吃", "给你点", "转账", "发红包", "给你打钱", "请你喝",
    "给你订", "送你", "给你寄", "给你送", "红包",
]
MEET_KEYWORDS = [
    "我去找你", "来找你", "过来找你", "见面", "当面", "去找你", "接你",
    "给你送过去", "带给你", "给你拿过去", "过去找你", "我去接",
]


@dataclass
class ApprovalRule:
    id: str
    name: str
    match: Callable[[str], bool]
    level: ApprovalLevel
    reason_template: str
    priority: int = 0

    def evaluate(self, reply: str) -> ApprovalDecision | None:
        if not self.match(reply):
            return None
        return ApprovalDecision(level=self.level, rule_id=self.id,
                                reason=self.reason_template)


def _kw_match(keywords: list[str]) -> Callable[[str], bool]:
    def match(reply: str) -> bool:
        return any(kw in reply for kw in keywords)
    return match


class ApprovalEngine:
    def __init__(self, cfg: dict | None = None, now_fn=None):
        """now_fn: 可注入时钟（测试用），缺省取本地时间。"""
        self._now = now_fn or _dt.datetime.now
        c = cfg or {}
        money = ApprovalLevel(c.get("money_level", "manual"))
        meet_same = ApprovalLevel(c.get("meet_same_city_level", "suggest"))
        meet_dist = ApprovalLevel(c.get("meet_distance_level", "manual"))
        night = ApprovalLevel(c.get("night_send_level", "suggest"))
        quiet: list[int] = c.get("quiet_hours", [23, 6])

        self.rules: list[ApprovalRule] = [
            ApprovalRule(
                id="money_promise", name="花钱承诺",
                match=_kw_match(MONEY_KEYWORDS), level=money,
                reason_template="回复涉及花钱承诺，需人工确认", priority=100),
            ApprovalRule(
                id="meet_long_distance", name="异地见面承诺",
                match=lambda r: False,  # 由 check() 动态注入 distance 后重写
                level=meet_dist,
                reason_template="异地状态下涉及见面承诺，需人工确认", priority=95),
            ApprovalRule(
                id="night_send", name="深夜发送",
                match=lambda r: self._in_quiet_hours(quiet), level=night,
                reason_template="深夜时段自动发送，建议确认", priority=50),
        ]
        # 同城/通用见面规则按 distance 分级：异地 manual 已在上面，
        # 这里放通用兜底（同城 suggest）
        self.meet_rule_same = ApprovalRule(
            id="meet_promise", name="见面承诺",
            match=_kw_match(MEET_KEYWORDS), level=meet_same,
            reason_template="回复涉及见面邀约，建议确认", priority=90)
        self.distance = "未知"

    def _in_quiet_hours(self, quiet: list[int]) -> bool:
        try:
            start, end = int(quiet[0]), int(quiet[1])
        except (ValueError, IndexError):
            return False
        h = self._now().hour
        if start <= end:
            return start <= h < end
        return h >= start or h < end  # 跨午夜

    def check(self, reply: str, distance: str | None = None) -> ApprovalDecision:
        """按优先级评估全部规则，返回首个命中决策；无命中 → AUTO。"""
        if distance:
            self.distance = distance
        candidates: list[ApprovalDecision] = []
        for rule in self.rules:
            if rule.id == "meet_long_distance":
                # 异地 + 见面关键词才触发（动态匹配）
                if self.distance == "异地":
                    hit = rule.match(reply) or any(kw in reply for kw in MEET_KEYWORDS)
                    if hit:
                        d = ApprovalDecision(level=rule.level, rule_id=rule.id,
                                             reason=rule.reason_template)
                        candidates.append(d)
                continue
            d = rule.evaluate(reply)
            if d:
                candidates.append(d)
        # 见面通用规则（同城/未知时生效）
        if any(kw in reply for kw in MEET_KEYWORDS):
            if self.distance == "异地":
                pass  # 已被 meet_long_distance 覆盖
            else:
                d = ApprovalDecision(level=self.meet_rule_same.level,
                                     rule_id=self.meet_rule_same.id,
                                     reason=self.meet_rule_same.reason_template)
                candidates.append(d)
        if not candidates:
            return ApprovalDecision(level=ApprovalLevel.AUTO, rule_id="",
                                    reason="无风险")
        # 首个 MANUAL 优先；否则取最高优先级
        manuals = [c for c in candidates if c.blocked]
        if manuals:
            return manuals[0]
        return candidates[0]
