# -*- coding: utf-8 -*-
"""狗头军师引擎：信号检测 + 知识库检索 + prompt 组装 + DeepSeek 调用 + 清洗。

分层（面向开源/可替换）：
- signals   : 信号检测（离线规则）
- kb        : 知识库检索（可替换知识库目录，见 kb/KB-LICENSE）
- style     : 风格档案（每个对象一份）
- approval  : 需确认检测 + 异地判断（安全边界）
- prompts   : system prompt 组装
- 本模块     : 编排 + LLM 调用（OpenAI 兼容接口）
"""

from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any

from .approval import NEEDS_APPROVAL_PREFIX, detect_needs_approval
from .kb import retrieve
from .prompts import build_system_prompt, format_history
from .signals import build_signal_block, detect_signals

DEFAULT_URL = "https://api.deepseek.com/chat/completions"
DEFAULT_MODEL = "deepseek-chat"


def call_openai_compatible(api_key: str, messages: list[dict[str, str]],
                           base_url: str = DEFAULT_URL, model: str = DEFAULT_MODEL,
                           temperature: float = 0.85, timeout: int = 30,
                           max_tokens: int = 300) -> str:
    """调用 OpenAI 兼容 chat API（默认 DeepSeek；可换任意兼容服务 = 商业化可插拔）。"""
    body = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        base_url,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", errors="replace")[:300]
        raise RuntimeError(f"LLM API HTTP {e.code}: {detail}") from e
    except Exception as e:
        raise RuntimeError(f"LLM API 调用失败: {e}") from e

    try:
        return payload["choices"][0]["message"]["content"].strip()
    except (KeyError, IndexError, TypeError) as e:
        raise RuntimeError(f"LLM API 响应格式异常: {json.dumps(payload, ensure_ascii=False)[:300]}") from e


def clean_reply(text: str) -> str:
    """清洗生成结果：去引号、去解释性前后缀，保留可发送正文。"""
    t = text.strip()
    # 去掉包裹引号
    if len(t) >= 2 and t[0] in "\"'“" and t[-1] in "\"'”":
        t = t[1:-1].strip()
    # 去掉可能的 "回复：/发送：" 前缀
    t = re.sub(r"^(回复|发送|发这条|直接发)[:：]\s*", "", t)
    return t.strip()


def generate_reply(api_key: str, history: list[dict[str, str]], latest: str,
                   model: str | None = None, base_url: str | None = None,
                   target_name: str | None = None,
                   distance: str | None = None,
                   profile: dict | None = None) -> dict[str, Any]:
    """完整链路：信号 → 知识库 → 风格/异地 → prompt → LLM → 清洗 → 需确认标记。

    未显式传 model/base_url 时从 config.json 读取（LLM 可插拔：改设置即换模型）。
    返回: {'reply', 'signals', 'model', 'elapsed_ms', 'needs_approval', 'distance', 'kb_files'}
    """
    from .config import get_llm_settings
    llm = get_llm_settings()
    model = model or llm["model"]
    base_url = base_url or llm["base_url"]
    temperature = llm["temperature"]
    timeout = llm["timeout_seconds"]
    if not api_key:
        api_key = llm["api_key"]

    signals = detect_signals(latest)
    kb_text = retrieve(signals)  # 知识库检索（每次生成都过一遍知识判断）
    system_prompt = build_system_prompt(
        profile=profile, target_name=target_name, distance=distance, kb_text=kb_text,
    )
    user = USER_TEMPLATE.format(
        history=format_history(history),
        latest=latest.strip(),
        signal_block=build_signal_block(signals),
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]
    t0 = time.monotonic()
    raw = call_openai_compatible(api_key, messages, base_url=base_url, model=model,
                                 temperature=temperature, timeout=timeout)
    elapsed = int((time.monotonic() - t0) * 1000)
    reply = clean_reply(raw)
    needs_approval = reply.startswith(NEEDS_APPROVAL_PREFIX) or detect_needs_approval(reply)
    return {
        "reply": reply,
        "raw": raw,
        "signals": signals,
        "model": model,
        "elapsed_ms": elapsed,
        "needs_approval": needs_approval,
        "distance": distance,
        "kb_files": _used_kb_files(signals),
    }


def _used_kb_files(signals: list[str]) -> list[str]:
    from .kb import SIGNAL_KB_MAP, DEFAULT_KB_FILES
    files: list[str] = []
    for sig in signals:
        for rel in SIGNAL_KB_MAP.get(sig, []):
            if rel not in files:
                files.append(rel)
    if not files:
        files = list(DEFAULT_KB_FILES)
    return files[:3]


def _fetch_chatlab_sample(target_name: str, cli: str = "chatlab",
                          session: str = "", limit: int = 200) -> str:
    """从 ChatLab 拉取聊天样本文本（异地/风格分析用）。失败返回空串。"""
    import json
    import re
    import subprocess

    try:
        if not session:
            try:
                out = subprocess.run([cli, "sessions", "list", "--format", "json"],
                                     capture_output=True, text=True, encoding="utf-8", timeout=60)
            except FileNotFoundError:
                cli = "chatlab.cmd"
                out = subprocess.run([cli, "sessions", "list", "--format", "json"],
                                     capture_output=True, text=True, encoding="utf-8", timeout=60)
            if out.returncode != 0:
                return ""
            for item in json.loads(out.stdout).get("data", {}).get("items", []):
                if item.get("name") == target_name:
                    session = item.get("id")
                    break
        if not session:
            return ""
        cmd = [cli, "messages", "between", "--member", "1", "--member", "2",
               "--session", session, "--limit", str(limit), "--max-tokens", "20000",
               "--format", "agent"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=90)
        except FileNotFoundError:
            cli = "chatlab.cmd"
            cmd[0] = cli
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=90)
        if out.returncode != 0:
            return ""
        text = json.loads(out.stdout).get("data", {}).get("text", "")
        lines = []
        for line in text.splitlines():
            m = re.match(r"\[#?\d+[-\d]*\] (\d{1,2}:\d{2}(?::\d{2})?) (.+?): (.*)", line.strip())
            if m:
                t, who, content = m.groups()
                content = content.strip()
                if content and not content.startswith(("[", "../images")):
                    lines.append(f"[{t}] {who}: {content}")
        return "\n".join(lines[-limit:])
    except Exception:
        return ""


USER_TEMPLATE = """以下是我和她最近的聊天记录（时间从旧到新，「我」是我，「她」是对方）：

{history}

她最新发来：
{latest}

{signal_block}请只生成 1 条我现在可以发给她的微信回复（不要解释，不要引号，不要多余内容）。"""

VARIANTS_TEMPLATE = """以下是我和她最近的聊天记录（时间从旧到新，「我」是我，「她」是对方）：

{history}

她最新发来：
{latest}

{signal_block}请生成 {n} 条不同风格的回复（语气/角度要有差异，全部符合铁律），并判断哪条最优。
输出严格 JSON（不要任何其他文字）：
{{"variants": ["回复1", "回复2", "回复3"], "best": 0}}
- variants：{n} 条可直接发送的回复（口语化、中文、5–50 字）
- best：你认为最优的下标（0 起）——最优 = 最符合铁律 + 最能接住她的情绪 + 最有你们的风格
- 任何一条涉及花钱/见面承诺，照常以【需确认】开头"""


def generate_variants(api_key: str, history: list[dict[str, str]], latest: str,
                      n: int = 3, target_name: str | None = None,
                      distance: str | None = None) -> dict[str, Any]:
    """多候选生成：LLM 一次输出 n 条 + 自评最优（系统判断）。

    返回: {'variants': [..n 条..], 'best': int, 'needs_approval': [..n..],
           'signals': [...], 'model': str, 'elapsed_ms': int}
    """
    from .config import get_llm_settings
    llm = get_llm_settings()
    model = llm["model"]
    base_url = llm["base_url"]
    temperature = llm["temperature"]
    timeout = llm["timeout_seconds"]
    if not api_key:
        api_key = llm["api_key"]

    signals = detect_signals(latest)
    kb_text = retrieve(signals)
    system_prompt = build_system_prompt(target_name=target_name, distance=distance, kb_text=kb_text)
    user = VARIANTS_TEMPLATE.format(
        history=format_history(history),
        latest=latest.strip(),
        signal_block=build_signal_block(signals),
        n=n,
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user},
    ]
    t0 = time.monotonic()
    raw = call_openai_compatible(api_key, messages, base_url=base_url, model=model,
                                 temperature=temperature, timeout=timeout, max_tokens=600)
    elapsed = int((time.monotonic() - t0) * 1000)

    # 解析 JSON（容忍 markdown 围栏）
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    variants: list[str] = []
    best = 0
    m = re.search(r"\{[\s\S]*\}", text)
    if m:
        try:
            data = json.loads(m.group(0))
            raw_variants = data.get("variants") or []
            if isinstance(raw_variants, list) and raw_variants:
                variants = [clean_reply(str(v)) for v in raw_variants][:n]
                best = int(data.get("best") or 0)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    # 兜底：按行拆分
    if not variants:
        for line in text.splitlines():
            line = line.strip().lstrip("0123456789.、 ")
            if line and not line.startswith(("{", "}", '"', "variants", "best")):
                variants.append(clean_reply(line))
            if len(variants) >= n:
                break
    if not variants:
        variants = [""] * n
    variants = variants + [""] * (n - len(variants))
    best = max(0, min(best, n - 1))
    needs = [detect_needs_approval(v) or v.startswith(NEEDS_APPROVAL_PREFIX) for v in variants]
    return {
        "variants": variants,
        "best": best,
        "needs_approval": needs,
        "signals": signals,
        "model": model,
        "elapsed_ms": elapsed,
        "distance": distance,
    }


def load_api_key(path: str | None = None) -> str:
    """读取 API Key：优先 config.json 的 llm.api_key，其次环境变量 / credentials 文件。"""
    from .config import get_llm_settings
    key = get_llm_settings()["api_key"]
    if key:
        return key
    raise RuntimeError("未找到 API Key（可在 GUI 设置或 config.json 的 llm.api_key 配置，"
                       "或设环境变量 DEEPSEEK_API_KEY）")
