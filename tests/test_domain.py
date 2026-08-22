# -*- coding: utf-8 -*-
"""领域层测试：信号 / 范例 / 清洗 / prompt 组装 / Provider 端点规范化。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from junshi_domain import prompts, humanize                    # noqa: E402
from junshi_domain.fewshot import (build_index, load_index,    # noqa: E402
                                   parse_chatlab_pairs,
                                   retrieve_fewshot)
from junshi_domain.signals import build_signal_block, detect_signals  # noqa: E402
from providers.openai_compat import (extract_json_object,      # noqa: E402
                                     is_stream_required_error,
                                     normalize_base_url, parse_sse_content)


def test_signals():
    assert "sad" in detect_signals("我今天好累啊不想动了")
    assert "shizhe" in detect_signals("实则我那天挺难过的")
    assert detect_signals("哈哈哈哈") == []
    block = build_signal_block(["sad"])
    assert "求关注" in block
    assert build_signal_block([]) == ""
    print("[PASS] signals: 规则检测 + 提示块")


def test_clean_reply():
    assert humanize.clean_reply('"你好呀"') == "你好呀"
    assert humanize.clean_reply("回复：在呢") == "在呢"
    assert humanize.clean_reply("  直接发：走起 ") == "走起"
    print("[PASS] humanize: clean_reply")


def test_fewshot(tmp=None):
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        import junshi_domain.fewshot as fs_mod
        original = fs_mod.INDEX_DIR
        from pathlib import Path as _P
        fs_mod.INDEX_DIR = _P(td) / "fewshot"
        try:
            pairs = [{"her": "你在干嘛", "me": "刚下班"},
                     {"her": "心情不好", "me": "咋了宝"}]
            build_index("宝宝", pairs)
            loaded = load_index("宝宝")
            assert len(loaded) == 2
            got = retrieve_fewshot("干嘛去了", "宝宝", k=1)
            assert got == ["刚下班"]
            assert retrieve_fewshot("完全无关内容xyz", "宝宝") == []
            assert retrieve_fewshot("啥", "不存在") == []

            text = "[10:01] 宝宝: 你吃了吗\n[10:02] 我: 吃了\n[10:03] 宝宝: 哦\n"
            parsed = parse_chatlab_pairs(text, "我", "宝宝")
            assert len(parsed) >= 1 and parsed[0]["me"] == "吃了"
        finally:
            fs_mod.INDEX_DIR = original
    print("[PASS] fewshot: 建库/召回/解析")


def test_prompts():
    sp = prompts.build_system_prompt(target_name="宝宝", distance="异地",
                                     kb_text="知识片段",
                                     fewshot=["刚下班"],
                                     target_profile=["她爱打游戏"])
    for seg in ("铁律", "去AI味规则", "我的风格", "两人异地",
                "知识参考", "真实回复范例", "对象档案"):
        assert seg in sp, f"缺少段落: {seg}"
    hist = prompts.format_history([{"role": "her", "text": "嗯"}])
    assert "她: 嗯" in hist
    print("[PASS] prompts: 全段落组装")


def test_provider_utils():
    assert normalize_base_url("https://x.com") == "https://x.com/v1/chat/completions"
    assert normalize_base_url("https://x.com/v1") == "https://x.com/v1/chat/completions"
    assert normalize_base_url("https://x.com/v1/chat/completions").endswith(
        "/v1/chat/completions")
    assert is_stream_required_error("current user api does not support http call")
    sse = ['data: {"choices":[{"delta":{"content":"你"}}]}'.encode(),
           'data: {"choices":[{"delta":{"content":"好"}}]}'.encode(),
           b"data: [DONE]"]
    assert parse_sse_content(sse) == "你好"
    obj = extract_json_object('```json\n{"variants":["a"],"best":0}\n```')
    assert obj == {"variants": ["a"], "best": 0}
    print("[PASS] provider: URL 规范化 / SSE / JSON 提取")


def main():
    test_signals()
    test_clean_reply()
    test_fewshot()
    test_prompts()
    test_provider_utils()
    print("\nALL DOMAIN TESTS PASSED")


if __name__ == "__main__":
    main()
