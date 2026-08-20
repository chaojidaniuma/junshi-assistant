# -*- coding: utf-8 -*-
"""知识库检索器：按信号/主题从 kb/ 知识库提取相关片段，注入生成 prompt。

知识库来源：github.com/powerycy/goutoujunshi（MIT，见 kb/KB-LICENSE）。
设计：
- 信号 → 知识文件映射（主题路由）
- 片段提取：标题 + mindmap 核心块 + 正文开头，按字符预算截断
- 无命中信号时用默认文件
"""

from __future__ import annotations

import os
import re
import sys
from pathlib import Path

# 知识库根目录：env 优先（可自定义知识库 = 商业化可插拔点）；
# frozen（PyInstaller onefile）时数据在 sys._MEIPASS 解压目录；否则为源码 kb/
if getattr(sys, "frozen", False):
    _ROOT = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
else:
    _ROOT = Path(__file__).resolve().parent.parent

KB_ROOT = Path(os.environ.get("GOUTOU_KB_DIR", str(_ROOT / "kb" / "references")))


def set_kb_dir(path: str | Path) -> None:
    """运行时切换知识库目录（GUI 设置里一键更换）。"""
    global KB_ROOT
    KB_ROOT = Path(path)
    os.environ["GOUTOU_KB_DIR"] = str(KB_ROOT)


def get_kb_dir() -> Path:
    return KB_ROOT

# 信号 → 知识文件（practical 优先，knowledge 按需；文件路径相对 KB_ROOT）
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
    "approval": ["practical/高情商拒绝他人：体面护边界的实用指南.md"],
}

DEFAULT_KB_FILES = ["practical/为他人提供情绪价值：温暖且有效的回应指南.md"]

# 片段预算（字符）
DEFAULT_FRAGMENT_CHARS = 1500
DEFAULT_TOTAL_CHARS = 3200


def _kb_root() -> Path:
    return KB_ROOT


def resolve_kb_path(rel: str) -> Path | None:
    """解析知识文件路径（带容错：去掉全角冒号后缀匹配）。"""
    p = _kb_root() / rel
    if p.exists():
        return p
    # 容错：文件名可能含全角冒号，尝试用 glob 前缀匹配
    stem = Path(rel).stem
    parent = p.parent
    if parent.exists():
        matches = [f for f in parent.glob(f"{stem}*") if f.is_file()]
        if matches:
            return matches[0]
    return None


def _strip_markdown(text: str) -> str:
    """去掉 markdown 围栏/图片，保留正文。"""
    text = re.sub(r"```mindmap|```|```yaml|```json", "", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    return text


def extract_fragment(rel: str, max_chars: int = DEFAULT_FRAGMENT_CHARS) -> str | None:
    """提取单个知识文件的片段：标题 + 正文前 max_chars 字符。"""
    p = resolve_kb_path(rel)
    if p is None:
        return None
    try:
        raw = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    text = _strip_markdown(raw).strip()
    # 取开头（标题 + 开头内容通常包含核心框架与示例）
    frag = text[:max_chars].strip()
    return f"【知识：{p.stem}】\n{frag}"


def retrieve(signals: list[str], total_chars: int = DEFAULT_TOTAL_CHARS,
             fragment_chars: int = DEFAULT_FRAGMENT_CHARS) -> str:
    """按信号检索知识片段，拼接为 prompt 段落。"""
    files: list[str] = []
    for sig in signals:
        for rel in SIGNAL_KB_MAP.get(sig, []):
            if rel not in files:
                files.append(rel)
    if not files:
        files = list(DEFAULT_KB_FILES)

    budget = total_chars
    parts: list[str] = []
    for rel in files[:3]:  # 最多 3 份
        if budget <= 0:
            break
        frag = extract_fragment(rel, min(fragment_chars, budget))
        if frag:
            parts.append(frag)
            budget -= len(frag)
    if not parts:
        return ""
    return "\n\n".join(parts)


def list_kb_files() -> list[str]:
    """列出知识库文件（调试用）。"""
    root = _kb_root()
    if not root.exists():
        return []
    return [str(p.relative_to(root)).replace("\\", "/")
            for p in root.rglob("*.md")]
