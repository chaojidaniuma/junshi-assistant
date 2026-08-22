# -*- coding: utf-8 -*-
"""harness 核心测试：Store / 审批引擎 / 策略 / TurnExecutor 全链路。"""
import json
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from junshi_harness.approval import ApprovalEngine, ApprovalLevel  # noqa: E402
from junshi_harness.config import Config                           # noqa: E402
from junshi_harness.context import ContextManager                  # noqa: E402
from junshi_harness.event_bus import EventBus                      # noqa: E402
from junshi_harness.policy import Policy                           # noqa: E402
from junshi_harness.store import Store                             # noqa: E402
from junshi_harness.thread import ThreadManager                    # noqa: E402
from junshi_harness.turn import TERMINAL_STATUSES, TurnExecutor, trigger_hash  # noqa: E402


class FakeProvider:
    def __init__(self, reply=None, fail_times=0):
        self.reply = reply or '{"variants": ["在呢", "咋啦", "说吧"], "best": 1}'
        self.fail_times = fail_times
        self.calls = 0
        self.last_messages = None

    def chat(self, messages, temperature=0.85, max_tokens=300, timeout=30):
        self.calls += 1
        self.last_messages = messages
        if self.calls <= self.fail_times:
            raise RuntimeError("模拟生成失败")
        return self.reply


def make_stack(tmp, provider=None, monitor_cfg=None, approval_cfg=None):
    cfg_file = Path(tmp) / "config.json"
    cfg_file.write_text(json.dumps({
        "target": {"name": "测试对象"},
        "llm": {"api_key": "test-key"},
        **({"monitor": monitor_cfg} if monitor_cfg else {}),
        **({"approval": approval_cfg} if approval_cfg else {}),
    }, ensure_ascii=False), encoding="utf-8")
    cfg = Config(cfg_file)
    bus = EventBus()
    store = Store(Path(tmp) / "junshi.db")
    threads = ThreadManager(store)
    policy = Policy(cfg.monitor())
    engine = ApprovalEngine(cfg.approval_cfg())
    contexts = ContextManager(threads)
    executor = TurnExecutor(cfg, store, bus, threads, contexts, engine, policy)
    if provider:
        executor.bind_provider(provider)
    return cfg, bus, store, threads, policy, engine, executor


def collect(bus, types=None):
    out = []

    def cb(item):
        if types is None or item.type in types:
            out.append(item.type)
    bus.subscribe(cb)
    return out


def test_store_thread_and_turn():
    with tempfile.TemporaryDirectory() as td:
        _, _, store, threads, *_ = make_stack(td)
        t = threads.ensure_thread("宝宝")
        t2 = threads.ensure_thread("宝宝")  # 幂等
        assert t["id"] == t2["id"], "同对象应复用 Thread"
        assert threads.get(t["id"])["target_name"] == "宝宝"

        h = trigger_hash("你好")
        tid = store.create_turn(t["id"], h, "你好")
        assert store.find_turn_by_hash(t["id"], h, list(TERMINAL_STATUSES)) is None
        store.set_turn_status(tid, "completed")
        assert store.find_turn_by_hash(t["id"], h, list(TERMINAL_STATUSES))
        # 非 hash 不串
        assert store.find_turn_by_hash(t["id"], "other", list(TERMINAL_STATUSES)) is None
        # items 落库有序
        from junshi_harness.item import Item
        for i in range(3):
            store.add_item(Item(type="log", data={"n": i}, turn_id=tid,
                                thread_id=t["id"]))
        seqs = [it.seq for it in store.turn_items(tid)]
        assert seqs == [1, 2, 3], f"seq 应递增，实际 {seqs}"
    print("[PASS] Store: Thread 复用 / Turn 去重 / Item 有序")


def test_approval_engine():
    import datetime as _dt
    day = lambda: _dt.datetime(2026, 1, 1, 14, 0)   # 白天 14:00
    night = lambda: _dt.datetime(2026, 1, 1, 23, 30)  # 深夜

    eng = ApprovalEngine({}, now_fn=day)
    d = eng.check("周末我请你吃大餐", distance="同城")
    assert d.level == ApprovalLevel.MANUAL and d.rule_id == "money_promise"
    d = eng.check("我去找你玩", distance="异地")
    assert d.level == ApprovalLevel.MANUAL, "异地见面必须 manual"
    d = eng.check("改天见面聊啊", distance="同城")
    assert d.level == ApprovalLevel.SUGGEST, "同城见面默认 suggest"
    d = eng.check("哈哈哈笑死我了", distance="同城")
    assert d.level == ApprovalLevel.AUTO, f"白天普通回复应 AUTO，实际 {d}"

    # 深夜时段 → suggest
    night_eng = ApprovalEngine({}, now_fn=night)
    d = night_eng.check("哈哈哈笑死我了")
    assert d.rule_id == "night_send" and not d.blocked, "深夜默认 suggest 不阻塞"

    # 分级可配置：同城见面也 manual
    strict = ApprovalEngine({"meet_same_city_level": "manual"}, now_fn=day)
    assert strict.check("来接你下班", distance="同城").blocked
    print("[PASS] ApprovalEngine: 关键词分级 + 异地更严 + 深夜规则")


def test_policy_rate_limit():
    p = Policy({"min_interval_between_replies_seconds": 60,
                "max_replies_per_hour": 2})
    ok, _ = p.can_send()
    assert ok
    p.note_sent()
    ok, reason = p.can_send()
    assert not ok and "冷却" in reason
    # 切回防抖
    assert p.allow_switch()
    assert not p.allow_switch()
    # 生成失败计数
    assert not p.note_gen_fail("x") and not p.note_gen_fail("x")
    assert p.note_gen_fail("x"), "第 3 次应达放弃阈值"
    print("[PASS] Policy: 冷却 / 防抖 / 失败阈值")


def test_turn_executor_full_flow():
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider()
        _, bus, _, threads, policy, _, ex = make_stack(
            td, provider=provider, monitor_cfg={"reply_mode": "auto"})
        seen_types = []
        bus.subscribe(lambda it: seen_types.append(it.type))
        thread = threads.ensure_thread("宝宝")
        history = [{"role": "me", "text": "早"}, {"role": "her", "text": "睡了吗"}]

        sent = []
        result = ex.execute(thread, "睡了吗", history,
                            distance="同城", send_fn=sent.append)

        assert result["status"] == "completed", result
        assert result["sent"] is True and sent == ["咋啦"], \
            f"应发送 best 候选，sent={sent}"
        assert result["best"] == 1
        # Item 流顺序合理
        assert seen_types[:4] == ["her_message", "signal_detected",
                                  "kb_retrieved", "context_built"], seen_types[:4]
        assert "variant_generated" in seen_types and "message_sent" in seen_types
        # prompt 含风格段与记忆段
        sys_prompt = provider.last_messages[0]["content"]
        assert "铁律" in sys_prompt and "去AI味规则" in sys_prompt
        user_prompt = provider.last_messages[1]["content"]
        assert "睡了吗" in user_prompt and "关系记忆" in user_prompt
    print("[PASS] TurnExecutor: 全链路（信号→知识→生成→发送→Item 流）")


def test_turn_approval_flow():
    with tempfile.TemporaryDirectory() as td:
        # 回复含花钱关键词 → manual
        provider = FakeProvider(reply='{"variants": ["给你买奶茶", "嗯嗯"], "best": 0}')
        _, bus, store, threads, _, _, ex = make_stack(td, provider=provider)
        thread = threads.ensure_thread("宝宝")

        result = ex.execute(thread, "好想喝奶茶", [], send_fn=lambda s: (_ for _ in ()).throw(
            AssertionError("manual 时不应自动发送")))
        assert result["status"] == "waiting_approval"
        pend = store.pending_approvals()
        assert len(pend) == 1 and pend[0]["rule_id"] == "money_promise"

        # 批准第 1 条候选 → 真实调用绑定通道发送
        events = []
        bus.subscribe(lambda it: events.append(it.type))
        sent_box = []
        ex.bind_sender(sent_box.append)
        r = ex.approve(pend[0]["id"])
        assert r["sent"] is True and sent_box == ["给你买奶茶"]
        assert store.pending_approvals() == []
        assert store.get_turn(pend[0]["turn_id"])["status"] == "completed"
        assert "message_sent" in events

        # 拒绝流（见 test_turn_reject_flow）
    print("[PASS] TurnExecutor: manual 审批 → approve 发送 / 终态正确")


def test_turn_reject_flow():
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider(reply='{"variants": ["发红包给你"], "best": 0}')
        _, _, store, threads, _, _, ex = make_stack(td, provider=provider)
        thread = threads.ensure_thread("宝宝")
        result = ex.execute(thread, "过节了耶", [])
        assert result["status"] == "waiting_approval"
        aid = store.pending_approvals()[0]["id"]
        r = ex.reject(aid)
        assert r["status"] == "rejected"
        assert store.pending_approvals() == []
        assert store.get_turn(result["turn_id"])["status"] == "rejected"
        # 拒绝是终态 → 同 hash 消息不再触发
        done = store.find_turn_by_hash(thread["id"], trigger_hash("过节了耶"),
                                       list(TERMINAL_STATUSES))
        assert done is not None
    print("[PASS] TurnExecutor: reject 终态 + 消息不再重触发")


def test_gen_fail_retry_semantics():
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider(fail_times=10)
        _, _, store, threads, policy, _, ex = make_stack(
            td, provider=provider,
            monitor_cfg={"gen_fail_give_up": 3})
        thread = threads.ensure_thread("宝宝")

        # 第 1 次：抛异常 + aborted_retry（非终态 → 下轮可重试）
        try:
            ex.execute(thread, "在吗", [])
            raise AssertionError("应抛异常")
        except RuntimeError:
            pass
        turn = store.find_turn_by_hash(thread["id"], trigger_hash("在吗"))
        assert turn is not None
        # aborted_retry 不在终态集合里
        done = store.find_turn_by_hash(thread["id"], trigger_hash("在吗"),
                                       list(TERMINAL_STATUSES))
        assert done is None or done["status"] not in TERMINAL_STATUSES, \
            "aborted_retry 不应阻断重试"

        # 连续失败到阈值 → failed 终态
        statuses = []
        for i in range(2):
            try:
                ex.execute(thread, "在吗", [])
            except RuntimeError:
                pass
        row = store.find_turn_by_hash(thread["id"], trigger_hash("在吗"),
                                      list(TERMINAL_STATUSES))
        assert row is not None and row["status"] == "failed", \
            "连续失败达上限应落 failed 终态"
    print("[PASS] TurnExecutor: 生成失败先重试后放弃（不丢消息）")


def test_empty_reply_gives_up():
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider(reply='{"variants": ["", "", ""], "best": 0}')
        _, _, store, threads, _, _, ex = make_stack(td, provider=provider)
        thread = threads.ensure_thread("宝宝")
        result = ex.execute(thread, "哦", [], send_fn=lambda s: None)
        assert result["status"] == "completed" and not result["sent"]
        turn = store.get_turn(result["turn_id"])
        assert turn["status"] == "completed" and "空回复" in (turn["error"] or "")
    print("[PASS] TurnExecutor: 空回复保护")


def test_config_deep_merge():
    with tempfile.TemporaryDirectory() as td:
        cfg, *_ = make_stack(td, monitor_cfg={"min_interval_between_replies_seconds": 5})
        m = cfg.monitor()
        assert m["min_interval_between_replies_seconds"] == 5
        assert m["poll_interval_seconds"] == 3.0, "未配置字段应取默认值"
        fs = cfg.fewshot()
        assert fs["enabled"] is True and fs["k"] == 3
        ap = cfg.approval_cfg()
        assert ap["money_level"] == "manual"
        llm = cfg.llm()
        assert llm["api_key"] == "test-key"
    print("[PASS] Config: 深合并 + 分区读取")


def test_reply_modes_and_stop_gate():
    # confirm 模式：普通回复也进待确认
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider()
        _, _, store, threads, _, _, ex = make_stack(
            td, provider=provider, monitor_cfg={"reply_mode": "confirm"})
        thread = threads.ensure_thread("宝宝")
        r = ex.execute(thread, "睡了吗", [],
                       send_fn=lambda s: (_ for _ in ()).throw(
                           AssertionError("confirm 不应自动发送")))
        assert r["status"] == "waiting_approval", r
        ap = store.pending_approvals()[0]
        assert ap["rule_id"] == "manual_confirm"

    # preview 模式：只出候选不发送，发 reply_preview 事件
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider()
        _, bus, store, threads, _, _, ex = make_stack(
            td, provider=provider, monitor_cfg={"reply_mode": "preview"})
        thread = threads.ensure_thread("宝宝")
        types = []
        bus.subscribe(lambda it: types.append(it.type))
        sent = []
        r = ex.execute(thread, "睡了吗", [], send_fn=sent.append)
        assert r["status"] == "completed" and not sent
        assert "reply_preview" in types

    # auto + 停止门控 → aborted_retry、不发送、可重试
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider()
        _, _, store, threads, _, _, ex = make_stack(
            td, provider=provider, monitor_cfg={"reply_mode": "auto"})
        thread = threads.ensure_thread("宝宝")
        sent = []
        r = ex.execute(thread, "睡了吗", [], send_fn=sent.append,
                       should_stop=lambda: True)
        assert r["status"] == "aborted_retry", f"应返回可重试状态，实际 {r['status']}"
        assert not sent, "停止后不应发送"
        done = store.find_turn_by_hash(thread["id"], trigger_hash("睡了吗"),
                                       list(TERMINAL_STATUSES))
        assert done is None or done["status"] not in TERMINAL_STATUSES, \
            "停止中断的消息应可重试"
    print("[PASS] 三档回复模式 + 停止门控")


def test_approve_actually_sends():
    """批准必须真实调用发送通道；失败保持待确认可重试。"""
    with tempfile.TemporaryDirectory() as td:
        provider = FakeProvider(reply='{"variants": ["给你买奶茶", "嗯嗯"], "best": 0}')
        _, bus, store, threads, _, _, ex = make_stack(td, provider=provider)
        sent_box = []
        ex.bind_sender(sent_box.append)   # 绑定真实通道
        thread = threads.ensure_thread("宝宝")
        r = ex.execute(thread, "好想喝奶茶", [])  # money 关键词 → manual
        assert r["status"] == "waiting_approval"
        aid = store.pending_approvals()[0]["id"]
        res = ex.approve(aid, 1)  # 选第 2 条候选
        assert res["sent"] is True and sent_box == ["嗯嗯"]
        assert store.pending_approvals() == []
        assert store.get_turn(r["turn_id"])["status"] == "completed"

        # 发送失败 → 保持待确认（可重试），审批未消费
        def boom(s):
            raise RuntimeError("微信窗口被占用")
        ex2_provider = FakeProvider(reply='{"variants": ["转账给你"], "best": 0}')
        _, _, store2, th2, _, _, ex2 = make_stack(td, provider=ex2_provider)
        # 复用同一 db 会撞 —— 单独目录
    with tempfile.TemporaryDirectory() as td2:
        provider = FakeProvider(reply='{"variants": ["转账给你"], "best": 0}')
        _, _, store, threads, _, _, ex = make_stack(td2, provider=provider)

        def boom(s):
            raise RuntimeError("微信窗口被占用")
        ex.bind_sender(boom)
        thread = threads.ensure_thread("宝宝")
        r = ex.execute(thread, "过节啦", [])
        aid = store.pending_approvals()[0]["id"]
        res = ex.approve(aid)
        assert res["sent"] is False and "仍待确认" in res.get("error", "")
        assert len(store.pending_approvals()) == 1, "发送失败应保留待确认"
    print("[PASS] approve 真实发送 / 失败保级可重试")


def main():
    test_store_thread_and_turn()
    test_approval_engine()
    test_policy_rate_limit()
    test_turn_executor_full_flow()
    test_turn_approval_flow()
    test_turn_reject_flow()
    test_gen_fail_retry_semantics()
    test_empty_reply_gives_up()
    test_config_deep_merge()
    test_reply_modes_and_stop_gate()
    test_approve_actually_sends()
    print("\nALL HARNESS TESTS PASSED")


if __name__ == "__main__":
    main()
