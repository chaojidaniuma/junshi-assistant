# -*- coding: utf-8 -*-
"""OpenAI 兼容 Provider（零依赖 urllib 实现）。

- 端点规范化：裸域名 / /v1 / 完整路径 三种写法
- 仅流式模型自动 SSE 重试（百炼 Qwen3 开源版等）
- 可重试错误（429/5xx/网络）指数退避重试
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request

from junshi_harness.errors import ProviderError

DEFAULT_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"

_STREAM_REQUIRED_MARKERS = (
    "does not support http call",
    "only support stream mode",
    "please enable the stream parameter",
)


def normalize_base_url(url: str) -> str:
    u = (url or "").strip().rstrip("/")
    if not u:
        return u
    if u.endswith("/chat/completions"):
        return u
    if re.search(r"/v\d+$", u):
        return u + "/chat/completions"
    return u + "/v1/chat/completions"


def is_stream_required_error(err_text: str) -> bool:
    t = err_text.lower()
    return any(m in t for m in _STREAM_REQUIRED_MARKERS)


def parse_sse_content(lines) -> str:
    """聚合 OpenAI 兼容 SSE 流的 delta.content。"""
    parts: list[str] = []
    for raw in lines:
        line = raw.decode("utf-8", errors="replace").strip() if isinstance(raw, bytes) else str(raw).strip()
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            if data == "[DONE]":
                break
            continue
        try:
            chunk = json.loads(data)
        except json.JSONDecodeError:
            continue
        try:
            delta = chunk["choices"][0].get("delta") or {}
            if delta.get("content"):
                parts.append(delta["content"])
        except (KeyError, IndexError, TypeError, AttributeError):
            continue
    return "".join(parts)


class OpenAICompatProvider:
    name = "openai_compat"

    def __init__(self, api_key: str, base_url: str = DEFAULT_URL,
                 model: str = DEFAULT_MODEL, max_retries: int = 2):
        self.api_key = api_key
        self.base_url = base_url or DEFAULT_URL
        self.model = model or DEFAULT_MODEL
        self.max_retries = max_retries

    def _request(self, body: dict, timeout: int) -> str:
        url = normalize_base_url(self.base_url)
        req = urllib.request.Request(
            url, data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"},
            method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
            try:
                return payload["choices"][0]["message"]["content"].strip()
            except (KeyError, IndexError, TypeError) as e:
                raise ProviderError(
                    f"响应格式异常: {json.dumps(payload, ensure_ascii=False)[:300]}") from e
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", errors="replace")[:300]
            err = ProviderError(f"HTTP {e.code}: {detail}", status=e.code)
            if is_stream_required_error(detail):
                body["stream"] = True
                req2 = urllib.request.Request(
                    url, data=json.dumps(body).encode("utf-8"),
                    headers={"Content-Type": "application/json",
                             "Authorization": f"Bearer {self.api_key}"},
                    method="POST")
                with urllib.request.urlopen(req2, timeout=timeout) as resp:
                    content = parse_sse_content(resp)
                if content:
                    return content
                raise RuntimeError(
                    f"模型 {self.model} 仅支持流式输出，流式重试未返回内容") from err
            raise err from e
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"调用失败: {e}") from e

    def chat(self, messages: list[dict[str, str]], temperature: float = 0.85,
             max_tokens: int = 300, timeout: int = 30) -> str:
        body = {"model": self.model, "messages": messages,
                "temperature": temperature, "max_tokens": max_tokens, "stream": False}
        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return self._request(body, timeout)
            except ProviderError as e:
                last_err = e
                if not e.retryable or attempt >= self.max_retries:
                    raise
                time.sleep(min(2 ** attempt, 4))
        raise last_err  # pragma: no cover


def extract_json_object(text: str) -> dict | None:
    """从 LLM 输出提取 JSON 对象（容忍 markdown 围栏）。"""
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    m = re.search(r"\{[\s\S]*\}", t)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        return None
