# -*- coding: utf-8 -*-
"""云端建议服务测试（用假 Provider 验证信号/知识/范例/审批/记忆串联）。

注意：网络/真实 LLM 不在此测试内（避免消耗 token 与用例不稳定）。
"""
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from junshi_harness.config import Config  # noqa: E402
from cloud.suggest import SuggestService, extract_style  # noqa: E402


class FakeProvider:
    def __init__(self):
        self.calls = 0
        self.last_messages = None
        self.model = "fake-model"

    def chat(self, messages, temperature=0.85, max_tokens=300, timeout=30):
        self.calls += 1
        self.last_messages = messages
        return '{"variants": ["别不吃饭啊", "怎么了宝宝", "欠着，见面还"], "best": 0}'


def make_cfg(tmp):
    cfg_file = Path(tmp) / "config.json"
    cfg_file.write_text(json.dumps({
        "target": {"name": "宝宝"},
        "llm": {"api_key": "test-key"},
    }, ensure_ascii=False), encoding="utf-8")
    return Config(cfg_file)


class _StubService(SuggestService):
    """替换 provider 为 FakeProvider 以便离线测试。"""

    def __init__(self, cfg):
        super().__init__(cfg)
        self.provider = FakeProvider()


def test_suggest_pipeline():
    with tempfile.TemporaryDirectory() as td:
        svc = _StubService(make_cfg(td))
        r = svc.suggest("宝宝", "今天好累啊，不想吃饭了",
                        history=[{"role": "her", "text": "今天好累啊"}],
                        memory_lines=["她最近加班多，常喊累"])
        assert r["variants"] == ["别不吃饭啊", "怎么了宝宝", "欠着，见面还"]
        assert r["best"] == 0
        assert "sad" in r["signals"], f"应识别低落信号，实际 {r['signals']}"
        assert "她最近加班多" in r["memory_block"]
        assert r["approval_reason"] == ""  # 该回复无花钱/见面
        assert r["distance"] in ("同城", "异地", "未知")
        # prompt 应含铁律 + 去AI味 + 知识参考 + 记忆
        sysp = svc.provider.last_messages[0]["content"]
        for seg in ("铁律", "去AI味规则", "知识参考"):
            assert seg in sysp, f"prompt 缺 {seg}"
    print("[PASS] suggest 流水线（信号/记忆/范例/知识/审批）")


def test_suggest_approval_flag():
    with tempfile.TemporaryDirectory() as td:
        svc = _StubService(make_cfg(td))
        # 强行让 FakeProvider 返回花钱内容
        svc.provider.chat = lambda m, temperature=0.85, max_tokens=300, timeout=30: (
            '{"variants": ["周末我请你吃大餐", "哈哈", "嗯嗯"], "best": 0}')
        r = svc.suggest("宝宝", "好想吃火锅", history=[{"role": "her", "text": "好想吃火锅"}],
                        me_city="北京", her_city="北京")
        assert r["needs_approval"] is True, "花钱承诺应被拦截"
        assert r["approval_reason"] != ""
    print("[PASS] suggest 审批拦截（花钱承诺标红）")


def test_suggest_no_result_fallback():
    with tempfile.TemporaryDirectory() as td:
        svc = _StubService(make_cfg(td))
        svc.provider.chat = lambda m, temperature=0.85, max_tokens=300, timeout=30: "乱码文本 没有JSON"
        r = svc.suggest("宝宝", "在吗")
        assert isinstance(r["variants"], list) and len(r["variants"]) == 3
    print("[PASS] suggest 无 JSON 兜底")


def test_signals_detect():
    from junshi_domain.signals import build_signal_block, detect_signals
    sigs = detect_signals("我好累啊委屈死了")
    assert "sad" in sigs
    assert "求关注" in build_signal_block(sigs)
    print("[PASS] signals 检测")


def main():
    test_suggest_pipeline()
    test_suggest_approval_flag()
    test_suggest_no_result_fallback()
    test_signals_detect()
    print("\nALL CLOUD TESTS PASSED")


if __name__ == "__main__":
    main()
