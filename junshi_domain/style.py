# -*- coding: utf-8 -*-
"""风格档案：加载与 prompt 段落格式化。

档案路径：data/style_profiles/<对象>.json（每对象一份），回退 data/style_profile.json。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    _PKG_ROOT = Path(sys.executable).resolve().parent
else:
    _PKG_ROOT = Path(__file__).resolve().parent.parent  # goutoujuns22/

PROFILE_DIR = _PKG_ROOT / "data" / "style_profiles"
DEFAULT_PROFILE_PATH = _PKG_ROOT / "data" / "style_profile.json"  # 默认档案

DEFAULT_STYLE_SECTION = (
    "## 我的风格（生成时保持）\n"
    "- 话不多但秒回、行动派：说“给你买”就真的买，说“在”就一直在\n"
    "- 嘴直不迎合，但行动从不含糊\n"
    "- 口头禅“孩子”，调侃式照顾，嘴上当爹行动当男朋友\n"
    "- 偶尔把行动翻译成一句话（“点了，给你点的”），让她听到爱\n"
)


def safe_filename(name: str) -> str:
    return re.sub(r'[\\/:*?"<>|\r\n]', "_", name or "").strip() or "default"


def load_style_profile(target_name: str | None = None) -> dict | None:
    if target_name:
        path = PROFILE_DIR / f"{safe_filename(target_name)}.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            profile = data.get("profile")
            if isinstance(profile, dict) and profile:
                return profile
        except (OSError, json.JSONDecodeError):
            pass
    try:
        data = json.loads(DEFAULT_PROFILE_PATH.read_text(encoding="utf-8"))
        profile = data.get("profile")
        return profile if isinstance(profile, dict) and profile else None
    except (OSError, json.JSONDecodeError):
        return None


def format_style_section(profile: dict | None) -> str:
    if not profile:
        return DEFAULT_STYLE_SECTION
    lines = ["## 我的风格（来自真实聊天记录分析，必须严格模仿）"]
    if profile.get("tone"):
        lines.append(f"- 整体语气：{profile['tone']}")
    if profile.get("humor_style"):
        lines.append(f"- 调侃方式：{profile['humor_style']}")
    if profile.get("care_style"):
        lines.append(f"- 关心表达：{profile['care_style']}")
    for feat in profile.get("style_features", [])[:6]:
        lines.append(f"- {feat}")
    if profile.get("catchphrases"):
        lines.append(f"- 口头禅/高频表达（可自然使用）：{'、'.join(profile['catchphrases'][:8])}")
    for pat in profile.get("reply_patterns", [])[:5]:
        lines.append(f"- 典型模式：{pat}")
    if profile.get("style_examples"):
        lines.append("- 风格示例（参考节奏与味道，不要原样照抄）：")
        for ex in profile["style_examples"][:3]:
            lines.append(f"  · {ex}")
    lines.append("- ⚠ 风格档案里若含“请客/买东西/花钱”类示例，只学语气不学花钱行为")
    return "\n".join(lines) + "\n"
