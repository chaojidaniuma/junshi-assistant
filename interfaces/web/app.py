# -*- coding: utf-8 -*-
"""Web 接入层：FastAPI REST + WebSocket。

只依赖 harness API（Store/EventBus/MonitorRuntime），不 import 任何旧模块。
WebSocket 直接推送结构化 Item —— 前端不再解析日志字符串。
"""
from __future__ import annotations

import asyncio
import json
import threading
import urllib.request
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from junshi_harness.config import Config
from junshi_harness.event_bus import EventBus
from junshi_harness.item import Item
from junshi_harness.store import Store
from runtime import MonitorRuntime

ROOT = Path(__file__).resolve().parent.parent.parent  # goutoujuns22/
INDEX_HTML = Path(__file__).resolve().parent / "index.html"

# ---------------- AI 服务商预设（OpenAI 兼容） ----------------
LLM_PRESETS: dict[str, dict] = {
    "deepseek": {
        "label": "DeepSeek（深度求索）",
        "base_url": "https://api.deepseek.com/v1",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "needs_key": True,
        "key_url": "https://platform.deepseek.com/api_keys",
    },
    "dashscope": {
        "label": "阿里百炼（通义千问）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-flash", "qwen-turbo",
                   "qwen3-max", "qwen-plus-latest"],
        "needs_key": True,
        "key_url": "https://bailian.console.aliyun.com/",
    },
    "openrouter": {
        "label": "OpenRouter（聚合全球模型）",
        "base_url": "https://openrouter.ai/api/v1",
        "models": ["deepseek/deepseek-chat", "anthropic/claude-3.5-sonnet",
                   "google/gemini-2.0-flash-001"],
        "needs_key": True,
        "key_url": "https://openrouter.ai/keys",
    },
    "siliconflow": {
        "label": "硅基流动 SiliconFlow",
        "base_url": "https://api.siliconflow.cn/v1",
        "models": ["deepseek-ai/DeepSeek-V3", "Qwen/Qwen2.5-72B-Instruct"],
        "needs_key": True,
        "key_url": "https://cloud.siliconflow.cn/account/ak",
    },
    "moonshot": {
        "label": "月之暗面 Kimi",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-latest"],
        "needs_key": True,
        "key_url": "https://platform.moonshot.cn/console/api-keys",
    },
    "ollama": {
        "label": "Ollama（本地模型，免 Key）",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen2.5:7b", "llama3.1:8b"],
        "needs_key": False,
        "key_url": "",
    },
    "custom": {
        "label": "自定义（任意 OpenAI 兼容服务）",
        "base_url": "",
        "models": [],
        "needs_key": True,
        "key_url": "",
    },
}


def _mask_key(key: str) -> str:
    if not key:
        return ""
    if len(key) <= 8:
        return "•" * len(key)
    return key[:4] + "•" * (len(key) - 8) + key[-4:]


def _models_url(base_url: str) -> str:
    """任意写法的 base_url → /models 列表地址。"""
    u = (base_url or "").strip().rstrip("/")
    if u.endswith("/chat/completions"):
        u = u[: -len("/chat/completions")]
    return u + "/models"


class WebApp:
    """组装 Config/Store/Bus/Runtime，暴露 FastAPI 应用。"""

    def __init__(self, cfg: Config | None = None):
        self.cfg = cfg or Config()
        self.bus = EventBus(history_max=1000)
        self.store = Store(self.cfg.db_path)
        self.runtime: MonitorRuntime | None = None
        self._ws_clients: list[WebSocket] = []
        self._ws_lock = threading.Lock()
        self._unsub = None
        self.app = self._build()

    # ------------------------------------------------------------------
    def _ensure_runtime(self) -> MonitorRuntime:
        if self.runtime is not None:
            # target 可能改过：同步 adapter 目标名
            new_target = self.cfg.load()["target"]["name"]
            if new_target and self.runtime.adapter.target_name != new_target:
                self.runtime.adapter.target_name = new_target
            return self.runtime
        target = self.cfg.load()["target"]["name"]
        if not target:
            raise RuntimeError("请先在「设置」里填写回复对象")
        from adapters.wechat_wxauto import WeChatAdapter
        adapter = WeChatAdapter(target_name=target,
                                log=lambda m: self.bus.publish(
                                    Item(type="log", data={"msg": m})))
        try:
            adapter.install_mouse_guard()
        except Exception:
            pass
        self.runtime = MonitorRuntime(self.cfg, self.store, self.bus, adapter)
        return self.runtime

    def _broadcast(self, item: Item) -> None:
        payload = json.dumps(item.to_dict(), ensure_ascii=False)
        with self._ws_lock:
            clients = list(self._ws_clients)
        for ws in clients:
            try:
                loop = getattr(ws, "_junshi_loop", None)
                if loop and loop.is_running():
                    asyncio.run_coroutine_threadsafe(
                        ws.send_text(payload), loop)
            except Exception:
                pass

    # ------------------------------------------------------------------
    def _build(self) -> FastAPI:
        app = FastAPI(title="junshi-assistant v2")

        @app.on_event("startup")
        async def _startup():
            self._unsub = self.bus.subscribe(self._broadcast)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            return INDEX_HTML.read_text(encoding="utf-8")

        @app.get("/api/status")
        async def status():
            import datetime as _dt
            midnight = _dt.datetime.combine(_dt.date.today(),
                                            _dt.time.min).timestamp()
            try:
                with self.store._conn() as conn:
                    replies_today = conn.execute(
                        "SELECT COUNT(*) FROM turns WHERE status='completed' "
                        "AND completed_at>=?", (midnight,)).fetchone()[0]
            except Exception:
                replies_today = 0
            return {
                "running": bool(self.runtime and self.runtime.running),
                "target": self.cfg.load()["target"]["name"],
                "reply_mode": self.cfg.monitor().get("reply_mode", "confirm"),
                "threads": self.store.list_threads(),
                "pending_approvals": len(self.store.pending_approvals()),
                "has_key": bool(self.cfg.llm()["api_key"]),
                "replies_today": replies_today,
            }

        @app.post("/api/mode")
        async def set_reply_mode(body: dict):
            mode = body.get("mode")
            if mode not in ("auto", "confirm", "preview"):
                return JSONResponse({"error": "mode 必须是 auto/confirm/preview"},
                                    status_code=400)
            cfg = self.cfg.load()
            cfg.setdefault("monitor", {})["reply_mode"] = mode
            self.cfg.save(cfg)
            return {"ok": True, "mode": mode}

        @app.post("/api/start")
        async def start():
            try:
                rt = self._ensure_runtime()
                if not rt.running:
                    rt.start()
                return {"ok": True}
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

        @app.post("/api/stop")
        async def stop():
            if self.runtime:
                self.runtime.stop()
            return {"ok": True}

        @app.get("/api/events/recent")
        async def recent_events(limit: int = 100):
            return {"items": self.bus.recent(limit)}

        # ---- 待确认 ----
        @app.get("/api/approvals/pending")
        async def pending_approvals():
            return {"approvals": self.store.pending_approvals()}

        @app.post("/api/approvals/{approval_id}/decide")
        async def decide(approval_id: str, body: dict):
            decision = body.get("decision")  # approved / rejected
            variant_index = body.get("variant_index")
            if decision not in ("approved", "rejected"):
                return JSONResponse({"error": "decision 必须是 approved/rejected"},
                                    status_code=400)
            try:
                ex = self._ensure_runtime().executor
            except Exception as e:
                return JSONResponse({"error": f"监听不可用：{e}"}, status_code=400)
            try:
                if decision == "approved":
                    result = ex.approve(approval_id, variant_index)
                else:
                    result = ex.reject(approval_id)
                return {"ok": True, **result}
            except Exception as e:
                return JSONResponse({"error": str(e)}, status_code=400)

        # ---- 设置 ----
        @app.get("/api/providers")
        async def providers():
            return {"presets": LLM_PRESETS}

        def _resolve_key(api_key: str) -> str:
            """掩码/空值 → 用已保存的真实 Key。"""
            k = (api_key or "").strip()
            if ("•" in k) or not k:
                return self.cfg.llm()["api_key"]
            return k

        @app.get("/api/config")
        async def get_config():
            cfg = self.cfg.load()
            llm = cfg.get("llm", {})
            real_key = self.cfg.llm()["api_key"]
            llm["api_key"] = _mask_key(real_key)   # 掩码显示，不回传明文
            llm["has_key"] = bool(real_key)
            return cfg

        @app.post("/api/config")
        async def set_config(body: dict):
            current = self.cfg.load()
            incoming = dict(body or {})
            incoming_key = (incoming.get("llm") or {}).get("api_key", "")
            # 掩码回传 / 空值 → 保留旧 Key
            if ("•" in incoming_key) or incoming_key.strip() == "":
                incoming.setdefault("llm", {})["api_key"] = \
                    current.get("llm", {}).get("api_key", "")
            merged = {**current, **incoming}
            self.cfg.save(merged)
            return {"ok": True}

        @app.get("/api/llm/models")
        async def llm_models(base_url: str = "", api_key: str = ""):
            from providers.openai_compat import normalize_base_url
            url = _models_url(normalize_base_url(base_url))
            key = _resolve_key(api_key)

            def _fetch() -> list[str]:
                req = urllib.request.Request(url)
                if key:
                    req.add_header("Authorization", f"Bearer {key}")
                with urllib.request.urlopen(req, timeout=12) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                return sorted({m.get("id") for m in data.get("data", [])
                               if m.get("id")})

            try:
                ids = await asyncio.wait_for(
                    asyncio.to_thread(_fetch), timeout=15)
                return {"ok": True, "models": ids}
            except Exception as e:
                return JSONResponse({"ok": False, "error": str(e)},
                                    status_code=200)

        @app.post("/api/llm/test")
        async def llm_test(body: dict):
            from providers.openai_compat import OpenAICompatProvider
            base_url = body.get("base_url") or ""
            model = body.get("model") or ""
            api_key = _resolve_key(body.get("api_key") or "")

            def _call() -> str:
                p = OpenAICompatProvider(api_key=api_key, base_url=base_url,
                                         model=model, max_retries=0)
                return p.chat([{"role": "user", "content": "只回复两个字：成功"}],
                              temperature=0, max_tokens=10, timeout=20)

            try:
                sample = await asyncio.wait_for(asyncio.to_thread(_call),
                                                timeout=30)
                return {"ok": True, "sample": sample[:40]}
            except Exception as e:
                return {"ok": False, "error": str(e)}

        # ---- 记忆 ----
        @app.get("/api/memory/{thread_id}")
        async def get_memory(thread_id: str):
            return {"memory": self.store.get_memory(thread_id)}

        @app.delete("/api/memory/item/{memory_id}")
        async def del_memory(memory_id: str):
            self.store.delete_memory(memory_id)
            return {"ok": True}

        @app.websocket("/ws")
        async def ws_endpoint(ws: WebSocket):
            await ws.accept()
            ws._junshi_loop = asyncio.get_running_loop()
            with self._ws_lock:
                self._ws_clients.append(ws)
            try:
                await ws.send_text(json.dumps(
                    {"type": "snapshot", "data": {"items": self.bus.recent(80)}},
                    ensure_ascii=False))
                while True:
                    await ws.receive_text()  # 保活；客户端消息忽略
            except WebSocketDisconnect:
                pass
            finally:
                with self._ws_lock:
                    if ws in self._ws_clients:
                        self._ws_clients.remove(ws)

        return app


def create_app() -> FastAPI:
    return WebApp().app


if __name__ == "__main__":
    import uvicorn
    print("军师助手 v2 (goutoujuns22) → http://127.0.0.1:8766")
    uvicorn.run(create_app(), host="127.0.0.1", port=8766, log_level="warning")
