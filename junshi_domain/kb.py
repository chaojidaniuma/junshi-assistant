# -*- coding: utf-8 -*-
"""知识库检索：按信号路由知识文件，提取片段注入 prompt。

默认复用仓库根的 kb/references（goutoujuns22 的上一级），
可用 env JUNSHI_KB_DIR 或 config.kb.dir 覆盖。
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    _ROOT = Path(__file__).resolve().parent.parent  # goutoujuns22/

_DEFAULT_KB = _ROOT / "kb" / "references"  # 仓库根的知识库
KB_ROOT = Path(os.environ.get("JUNSHI_KB_DIR", str(_DEFAULT_KB)))

SIGNAL_KB_MAP: dict[str, list[str]] = {
    "sad":      ["practical/为他人提供情绪价值：温暖且有效的回应指南.md"],
    "shizhe":   ["practical/为他人提供情绪价值：温暖且有效的回应指南.md"],
    "angry":    ["practical/万能吵架技巧：理性冲突处理指南.md",
                 "knowledge/07-沟通冲突与修复.md"],
    "coquetry": ["practical/聊天化被动为主动：引导互动的实用指南.md",
                 "practical/巧妙接话技巧：让沟通更流畅的实用指南.md"],
    "cold":     ["practical/化解尴尬：轻松救场的实用指南.md"],
    "food":     ["practical/废话文学回复指南：轻松应对各类场景.md"],
    "game":     ["practical/巧妙接话技巧：让沟通更流畅的实用指南.md"],
    "family":   ["knowledge/11-婚姻家庭与生命周期.md"],
    "help":     ["practical/托人办事的高效话术指南.md"],
    "plan":     ["practical/主动表达、第一次见面与自然接触.md"],
}
DEFAULT_KB_FILES = ["practical/为他人提供情绪价值：温暖且有效的回应指南.md"]
DEFAULT_FRAGMENT_CHARS = 1500
DEFAULT_TOTAL_CHARS = 3200

_CACHE: dict[tuple, str] = {}
_CACHE_MAX = 64


def set_kb_dir(path: str | Path) -> None:
    global KB_ROOT
    KB_ROOT = Path(path)
    os.environ["JUNSHI_KB_DIR"] = str(KB_ROOT)
    _CACHE.clear()


def used_kb_files(signals: list[str]) -> list[str]:
    files: list[str] = []
    for sig in signals:
        for rel in SIGNAL_KB_MAP.get(sig, []):
            if rel not in files:
                files.append(rel)
    if not files:
        files = list(DEFAULT_KB_FILES)
    return files[:3]


def _resolve(rel: str) -> Path | None:
    p = KB_ROOT / rel
    if p.exists():
        return p
    stem = Path(rel).stem
    parent = p.parent
    if parent.exists():
        matches = [f for f in parent.glob(f"{stem}*") if f.is_file()]
        if matches:
            return matches[0]
    return None


def _strip_markdown(text: str) -> str:
    text = re.sub(r"```mindmap|```|```yaml|```json", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    return text


def retrieve(signals: list[str], total_chars: int = DEFAULT_TOTAL_CHARS,
             fragment_chars: int = DEFAULT_FRAGMENT_CHARS) -> str:
    key = tuple(signals)
    if key in _CACHE:
        return _CACHE[key]
    files = used_kb_files(signals)
    budget = total_chars
    parts: list[str] = []
    for rel in files[:3]:
        if budget <= 0:
            break
        p = _resolve(rel)
        if p is None:
            continue
        try:
            raw = p.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        frag = _strip_markdown(raw).strip()[:min(fragment_chars, budget)].strip()
        if frag:
            parts.append(f"【知识：{p.stem}】\n{frag}")
            budget -= len(frag)
    joined = "\n\n".join(parts)
    if joined:
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.clear()
        _CACHE[key] = joined
    return joined
