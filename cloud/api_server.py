# -*- coding: utf-8 -*-
"""军师助手 · 测试上线服务（AWS EC2 部署用）。

对接文档《零成本测试上线方案》：端口 8000，接口形态按文档 §5：
    POST /api/generate   her_message → replies[3] + signal + reasoning
    GET  /api/quota      user_id → used/limit/remaining/is_vip
    GET  /health

不同点：replies 不是占位假回复，而是走真实 SuggestService
（信号检测 / 知识库 / 真人范例 / 风格 / 审批拦截）。

模型默认：硅基流动免费 Qwen2.5-7B；可用环境变量覆盖。
"""
from __future__ import annotations

import os
import time
from collections import defaultdict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from .suggest import SuggestService

DAILY_LIMIT = int(os.environ.get("JUNSHI_DAILY_LIMIT", "10"))

# ---------------- 模型配置（环境变量优先） ----------------
def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def build_suggestor() -> SuggestService:
    # 硅基流动（免费）：优先
    if _env("SILICONFLOW_API_KEY"):
        return SuggestService(
            base_url=_env("SILICONFLOW_BASE_URL",
                          "https://api.siliconflow.cn/v1"),
            api_key=_env("SILICONFLOW_API_KEY"),
            model=_env("SILICONFLOW_MODEL", "Qwen/Qwen2.5-7B-Instruct"))
    # 备用：DeepSeek
    if _env("DEEPSEEK_API_KEY"):
        return SuggestService(
            base_url=_env("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1"),
            api_key=_env("DEEPSEEK_API_KEY"),
            model=_env("DEEPSEEK_MODEL", "deepseek-chat"))
    # 最后回退：本机 config.json（供本地开发测试）
    return SuggestService()


# 内存额度计数（文档 §5：测试阶段用内存字典代替 Redis）
_daily_usage: dict[str, int] = defaultdict(int)

app = FastAPI(title="军师助手 测试服务", version="0.1.0")
suggestor = build_suggestor()


class GenerateRequest(BaseModel):
    her_message: str
    your_style: str | None = None          # 预留，后续用于风格覆盖
    relationship_memory: str | None = None  # 预留
    mode: str = "normal"                    # normal/sweet/cold/funny（预留）
    user_id: str = "default"


class GenerateResponse(BaseModel):
    replies: list[str]
    signal: str | None = None
    reasoning: str | None = None


def _signal_text(signals: list[str]) -> str:
    if not signals:
        return ""
    names = {"shizhe": "她在说真心话", "sad": "她在求关注/求心疼",
             "coquetry": "她在撒娇", "angry": "她可能在闹情绪",
             "cold": "她有点冷淡", "food": "她在说吃的",
             "game": "她在说游戏", "family": "她在说家里的事",
             "help": "她在求助", "plan": "她在聊计划"}
    return "、".join(names.get(s, s) for s in signals)


@app.post("/api/generate", response_model=GenerateResponse)
async def generate(req: GenerateRequest):
    if _daily_usage[req.user_id] >= DAILY_LIMIT:
        raise HTTPException(status_code=402, detail="今日免费次数已用完，请明天再来或开通会员")
    _daily_usage[req.user_id] += 1

    # 解析 her_message 中可能内嵌的信号前缀（键盘可传 "共情:Sad:文本"）
    text = req.her_message.strip()
    memory_lines = []
    if req.relationship_memory:
        memory_lines = [l.strip() for l in req.relationship_memory.splitlines() if l.strip()]

    try:
        r = suggestor.suggest(
            object_name=_env("OBJECT_NAME", "对象"),
            latest=text,
            history=[],
            memory_lines=memory_lines)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"生成失败：{e}")

    return GenerateResponse(
        replies=[v for v in r["variants"] if v.strip()] or ["（生成失败，请重试）"],
        signal=r["signal_block"] and _signal_text(r["signals"]) or None,
        reasoning=r["approval_reason"] or
                 (f"检测到信号：{_signal_text(r['signals'])}" if r["signals"] else None),
    )


@app.get("/api/quota")
def get_quota(user_id: str = "default"):
    used = _daily_usage[user_id]
    return {
        "user_id": user_id,
        "used_today": used,
        "daily_limit": DAILY_LIMIT,
        "remaining": max(0, DAILY_LIMIT - used),
        "is_vip": False,
    }


@app.get("/health")
def health():
    return {"status": "healthy", "model": suggestor.provider.model}


@app.get("/")
def root():
    return {"name": "军师助手 API", "version": "0.1.0", "docs": "/docs"}
