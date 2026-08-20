# -*- coding: utf-8 -*-
"""集中配置管理：读取/保存 config.json，LLM 设置解析（可插拔端点 + API Key）。

优先级（API Key）：config.json 的 llm.api_key → 环境变量 DEEPSEEK_API_KEY
→ ~/.dsh/.credentials.yaml
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent

CONFIG_PATH = Path(os.environ.get("GOUTOU_CONFIG", str(ROOT / "config.json")))

DEFAULTS: dict = {
    "target": {"name": "", "wxid": "", "remark": ""},
    "me": {"name": "", "wxid": ""},
    "chatlab": {"session": "", "cli": "chatlab"},
    "llm": {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/chat/completions",
        "temperature": 0.85,
        "timeout_seconds": 30,
        "api_key": "",
    },
    "kb": {"dir": ""},
    "location": {"me": "", "her": ""},
    "monitor": {
        "poll_interval_seconds": 3,
        "history_window": 20,
        "cooldown_seconds": 45,
        "min_interval_between_replies_seconds": 60,
        "max_replies_per_hour": 30,
        "only_text_messages": True,
        "confirm_before_send": False,
        "ignore_keywords": ["[图片]", "[表情]", "[语音]", "[文件]", "[视频]"],
    },
    "paths": {"state_file": "data/state.json", "log_dir": "logs"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config() -> dict:
    """读取 config.json，与默认值合并（缺字段自动补全）。"""
    if CONFIG_PATH.exists():
        try:
            user = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return _deep_merge(DEFAULTS, user)
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads(json.dumps(DEFAULTS))


def save_config(cfg: dict) -> Path:
    """写回 config.json（原子写）。"""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(CONFIG_PATH)
    return CONFIG_PATH


def get_llm_settings() -> dict:
    """返回 LLM 设置（含解析后的 api_key）。"""
    cfg = load_config()
    llm = cfg.get("llm", {})
    return {
        "model": llm.get("model") or DEFAULTS["llm"]["model"],
        "base_url": llm.get("base_url") or DEFAULTS["llm"]["base_url"],
        "temperature": float(llm.get("temperature") or DEFAULTS["llm"]["temperature"]),
        "timeout_seconds": int(llm.get("timeout_seconds") or DEFAULTS["llm"]["timeout_seconds"]),
        "api_key": resolve_api_key(llm.get("api_key") or ""),
    }


def resolve_api_key(configured: str = "") -> str:
    """API Key 解析：config 显式配置 > 环境变量 > DSH credentials 文件。"""
    if configured.strip():
        return configured.strip()
    env_key = os.environ.get("DEEPSEEK_API_KEY")
    if env_key:
        return env_key.strip()
    for p in [Path.home() / ".dsh" / ".credentials.yaml",
              Path.home() / ".dsh" / ".credentials.yml"]:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEEPSEEK_API_KEY:"):
                    key = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if key:
                        return key
        except OSError:
            continue
    return ""
