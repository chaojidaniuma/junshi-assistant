# -*- coding: utf-8 -*-
"""dry-run 验证脚本：从 ChatLab 拉最近对话 → 狗头军师引擎生成回复 → 打印。

不连接微信、不发送任何消息。用法：
    python dryrun.py                 # 用 ChatLab 最近对话验证
    python dryrun.py "自定义消息"     # 用指定文本作为「她最新发来」验证
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from goutou.engine import generate_reply, load_api_key

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))


def fetch_chatlab_history(limit: int = 12) -> list[dict[str, str]]:
    """从 ChatLab 拉最近对话（agent 格式文本，解析为历史条目）。"""
    session = CONFIG["chatlab"]["session"]
    cli = CONFIG["chatlab"]["cli"]
    cmd = [cli, "messages", "between", "--member", "1", "--member", "2",
           "--since", "2026-08-19", "--limit", "50", "--format", "agent"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             timeout=60).stdout
    except FileNotFoundError:
        # 尝试 chatlab.cmd（Windows PowerShell 策略绕过）
        cmd[0] = "chatlab.cmd"
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             timeout=60).stdout

    data = json.loads(out)
    text = data.get("data", {}).get("text", "")
    history: list[dict[str, str]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("["):
            continue
        # 格式: [#1234] 21:45:01 宝宝（7.05）: 内容
        m = __import__("re").match(r"\[#?\d+[-\d]*\] (\d{1,2}:\d{2}(?::\d{2})?) (.+?): (.*)", line)
        if not m:
            continue
        time_str, name, content = m.groups()
        if not content or content.startswith(("[", "../images")):
            continue
        is_me = name == CONFIG["me"]["name"]
        history.append({"role": "me" if is_me else "her", "text": content, "time": time_str})
    return history[-limit:]


def main() -> None:
    custom = " ".join(sys.argv[1:]).strip()
    if custom:
        # 模拟「她最新发来」，历史用 ChatLab
        history = fetch_chatlab_history(10)
        latest = custom
        print(f"--- 模拟她发来: {latest} ---")
    else:
        history = fetch_chatlab_history(12)
        if not history:
            print("ChatLab 没有拉到历史，请先确认数据已导入。")
            return
        latest = history[-1]["text"]
        history = history[:-1]
        print(f"--- 用 ChatLab 最后一条模拟: {latest} ---")

    print(f"--- 历史 {len(history)} 条（最近 5 条）---")
    for item in history[-5:]:
        who = "我" if item["role"] == "me" else "她"
        print(f"  {who}: {item['text'][:50]}")

    api_key = load_api_key()
    result = generate_reply(api_key, history, latest, model=CONFIG["llm"]["model"])
    print(f"\n信号: {result['signals'] or '无'}")
    print(f"耗时: {result['elapsed_ms']}ms")
    print("\n=== 生成回复 ===")
    print(result["reply"])
    print("=================")


if __name__ == "__main__":
    main()
