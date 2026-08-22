# -*- coding: utf-8 -*-
"""真人范例召回：(她的话 → 我的回复) 配对库 + 轻量 bigram 召回。零依赖。"""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent      # exe 同级存数据
else:
    ROOT = Path(__file__).resolve().parent.parent
INDEX_DIR = ROOT / "data" / "fewshot"


def _bigrams(text: str) -> set[str]:
    text = re.sub(r"\s+", "", text or "")
    return set(text[i:i + 2] for i in range(len(text) - 1)) if len(text) > 1 else set(text)


def _safe(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n]', "_", name or "default").strip() or "default"


def build_index(target_name: str, pairs: list[dict]) -> Path:
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    path = INDEX_DIR / f"{_safe(target_name)}.json"
    path.write_text(json.dumps(
        {"target": target_name,
         "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
         "pairs": pairs}, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_index(target_name: str) -> list | None:
    path = INDEX_DIR / f"{_safe(target_name)}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("pairs", [])
    except (OSError, json.JSONDecodeError):
        return None


def retrieve_fewshot(latest: str, target_name: str | None, k: int = 3) -> list[str]:
    """返回 top-k 条「我的真实回复」。索引缺失/无命中 → []。"""
    pairs = load_index(target_name) if target_name else None
    if not pairs:
        return []
    q = _bigrams(latest)
    if not q:
        return []
    scored = []
    for p in pairs:
        her = p.get("her") or ""
        me = p.get("me") or ""
        if her and me:
            overlap = len(q & _bigrams(her))
            if overlap > 0:
                scored.append((overlap, me))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [m for _, m in scored[:k] if m]


def parse_chatlab_pairs(text: str, my_name: str, her_name: str) -> list[dict]:
    """从 ChatLab agent 格式文本解析 (her, me) 配对。"""
    line_re = re.compile(r"\[\d{1,2}:\d{2}(?::\d{2})?\]\s*(.+?):\s*(.*)")
    pairs: list[dict] = []
    lines = [ln.strip() for ln in text.splitlines()]

    def parse_at(idx: int):
        m = line_re.match(lines[idx])
        if not m:
            return None
        who, content = m.group(1).strip(), m.group(2).strip()
        if not content or content.startswith(("[", "../images")):
            return None
        return who, content

    i = 0
    while i < len(lines):
        parsed = parse_at(i)
        if not parsed:
            i += 1
            continue
        who, content = parsed
        if who != her_name:
            i += 1
            continue
        her_msgs = [content]
        j = i + 1
        while j < len(lines):
            nxt = parse_at(j)
            if nxt is None:
                j += 1
                continue
            break
        if nxt and nxt[0] == her_name:
            i = j
            continue
        if nxt and nxt[0] == my_name:
            pairs.append({"her": "\n".join(her_msgs), "me": nxt[1]})
            i = j + 1
            continue
        i = j
    return pairs


def build_index_from_chatlab_text(target_name: str, chatlab_text: str,
                                  my_name: str = "我") -> int:
    """从 ChatLab 文本建库（她的名字默认用 target 本身）。返回配对数。"""
    pairs = parse_chatlab_pairs(chatlab_text, my_name, target_name)
    build_index(target_name, pairs)
    return len(pairs)
