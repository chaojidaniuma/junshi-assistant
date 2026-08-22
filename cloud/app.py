# -*- coding: utf-8 -*-
"""军师助手 云端 API。

服务手机 AI 键盘等客户端。复用 junshi_harness 的 Thread/Store 做对象与记忆，
复用 junshi_domain + providers 做建议生成。

安全：本文件是最小可服务版本，重点在 /api/v1/suggest 等建议接口，
认证与额度用轻量 UID 头占位（完整 JWT/支付在 v1.2 接入）。
"""
from __future__ import annotations

import sqlite3
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from junshi_harness.config import Config
from junshi_harness.store import Store
from junshi_harness.thread import ThreadManager

from .suggest import SuggestService, extract_style

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / "data" / "cloud.db"

cfg = Config()
store = Store(DB_PATH)
threads = ThreadManager(store)
suggestor = SuggestService(cfg)

app = FastAPI(title="军师助手 云端 API", version="0.1.0")


# ---------------- 请求/响应模型 ----------------
class SuggestRequest(BaseModel):
    object_name: str = Field(..., description="关系对象名（如：宝宝）")
    latest: str = Field(..., description="她最新的一条消息")
    history: list[dict[str, str]] = Field(default_factory=list)
    me_city: str = ""
    her_city: str = ""
    user_id: str = "anon"


class SuggestResponse(BaseModel):
    signals: list[str]
    signal_block: str
    distance: str
    memory_block: str
    variants: list[str]
    best: int
    needs_approval: bool
    approval_reason: str
    elapsed_ms: int
    model: str


class SignalsRequest(BaseModel):
    text: str


class MemoryUpsert(BaseModel):
    category: str = "note"
    key: str
    value: str


class StyleRequest(BaseModel):
    lines: list[str]


# ---------------- 建议（核心） ----------------
@app.post("/api/v1/suggest", response_model=SuggestResponse)
def suggest(req: SuggestRequest):
    # 按对象建/取 Thread，只用于记忆存储
    thread = threads.ensure_thread(req.object_name)
    mem_rows = threads.get_memory(thread["id"])
    memory_lines = [f"{m['key']}: {m['value']}" for m in mem_rows]
    try:
        result = suggestor.suggest(
            object_name=req.object_name, latest=req.latest,
            history=req.history, me_city=req.me_city, her_city=req.her_city,
            memory_lines=memory_lines)
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)
    return result


@app.post("/api/v1/signals/detect")
def signals(req: SignalsRequest):
    from junshi_domain.signals import detect_signals, build_signal_block
    sigs = detect_signals(req.text)
    return {"signals": sigs, "signal_block": build_signal_block(sigs)}


# ---------------- 记忆 ----------------
class MemoryList(BaseModel):
    memory: list[dict]


@app.get("/api/v1/threads/{object_name}/memory")
def get_memory(object_name: str):
    thread = threads.ensure_thread(object_name)
    return MemoryList(memory=threads.get_memory(thread["id"]))


@app.post("/api/v1/threads/{object_name}/memory")
def add_memory(object_name: str, req: MemoryUpsert):
    thread = threads.ensure_thread(object_name)
    threads.update_memory(thread["id"], req.category, req.key, req.value)
    return {"ok": True}


@app.delete("/api/v1/threads/{object_name}/memory/{memory_id}")
def del_memory(object_name: str, memory_id: str):
    store.delete_memory(memory_id)
    return {"ok": True}


# ---------------- 风格 ----------------
@app.post("/api/v1/style/extract")
def style_extract(req: StyleRequest):
    try:
        profile = extract_style([l for l in req.lines if l.strip()])
        return {"ok": True, "profile": profile}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=502)


@app.get("/api/v1/health")
def health():
    return {"ok": True, "service": "junshi-cloud", "time": time.time()}
