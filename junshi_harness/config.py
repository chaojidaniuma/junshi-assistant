# -*- coding: utf-8 -*-
"""配置管理：JSON 格式（兼容旧 config.json），实例化传递（无全局单例）。

- 深合并默认值；mtime 缓存避免每轮读盘
- Thread 级 config_override 覆盖全局（多对象不同策略）
"""
from __future__ import annotations

import copy
import json
import os
import sys
from pathlib import Path

if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent.parent  # goutoujuns22/

DEFAULTS: dict = {
    "target": {"name": "", "wxid": "", "profile": []},
    "me": {"name": "", "wxid": ""},
    "chatlab": {"session": "", "cli": "chatlab"},
    "llm": {
        "model": "deepseek-chat",
        "base_url": "https://api.deepseek.com/chat/completions",
        "temperature": 0.85,
        "timeout_seconds": 30,
        "max_retries": 2,
        "api_key": "",
    },
    "kb": {"dir": ""},
    "location": {"me": "", "her": ""},
    "monitor": {
        "poll_interval_seconds": 3.0,
        "history_window": 20,
        "min_interval_between_replies_seconds": 60,
        "max_replies_per_hour": 30,
        "switch_debounce_seconds": 5,
        "gen_fail_give_up": 3,
        "reply_mode": "confirm",  # auto=自动发送 / confirm=确认后发送 / preview=仅预览
    },
    "fewshot": {"enabled": True, "k": 3, "method": "keyword"},
    "humanize": {"enabled": True, "mode": "prompt"},
    "approval": {
        "money_level": "manual",
        "meet_same_city_level": "suggest",
        "meet_distance_level": "manual",
        "night_send_level": "suggest",
        "quiet_hours": [23, 6],
    },
    "paths": {"db_file": "data/junshi.db", "log_dir": "logs"},
}


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


class Config:
    """实例化配置：从 config.json 加载 + 深合并默认值 + mtime 缓存。"""

    def __init__(self, path: str | Path | None = None):
        self.path = Path(path or os.environ.get(
            "JUNSHI_CONFIG", str(ROOT / "config.json")))
        self._cache: dict = {"mtime_ns": None, "data": None}

    def load(self) -> dict:
        try:
            mtime = self.path.stat().st_mtime_ns if self.path.exists() else None
        except OSError:
            mtime = None
        if self._cache["data"] is not None and self._cache["mtime_ns"] == mtime:
            return copy.deepcopy(self._cache["data"])
        if self.path.exists():
            try:
                user = json.loads(self.path.read_text(encoding="utf-8"))
                merged = _deep_merge(DEFAULTS, user)
            except (json.JSONDecodeError, OSError):
                merged = copy.deepcopy(DEFAULTS)
        else:
            merged = copy.deepcopy(DEFAULTS)
        self._cache = {"mtime_ns": mtime, "data": copy.deepcopy(merged)}
        return merged

    def save(self, cfg: dict) -> Path:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)
        self._cache = {"mtime_ns": None, "data": None}
        return self.path

    # ---- 分区读取（带线程级覆盖）----
    def llm(self, override: dict | None = None) -> dict:
        cfg = _deep_merge(self.load(), override or {})
        llm = cfg["llm"]
        key = (llm.get("api_key") or "").strip()
        if not key:
            key = (os.environ.get("DEEPSEEK_API_KEY") or "").strip()
        if not key:
            key = _read_dsh_credentials()
        return {**llm, "api_key": key}

    def monitor(self, override: dict | None = None) -> dict:
        cfg = _deep_merge(self.load(), override or {})
        return cfg["monitor"]

    def fewshot(self, override: dict | None = None) -> dict:
        cfg = _deep_merge(self.load(), override or {})
        return cfg["fewshot"]

    def humanize(self, override: dict | None = None) -> dict:
        cfg = _deep_merge(self.load(), override or {})
        return cfg["humanize"]

    def approval_cfg(self, override: dict | None = None) -> dict:
        cfg = _deep_merge(self.load(), override or {})
        return cfg["approval"]

    @property
    def db_path(self) -> Path:
        p = self.load()["paths"]["db_file"]
        path = Path(p)
        return path if path.is_absolute() else ROOT / p


def _read_dsh_credentials() -> str:
    for p in [Path.home() / ".dsh" / ".credentials.yaml",
              Path.home() / ".dsh" / ".credentials.yml"]:
        try:
            for line in p.read_text(encoding="utf-8").splitlines():
                if line.startswith("DEEPSEEK_API_KEY:"):
                    k = line.split(":", 1)[1].strip().strip('"').strip("'")
                    if k:
                        return k
        except OSError:
            continue
    return ""
