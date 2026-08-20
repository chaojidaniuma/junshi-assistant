# -*- coding: utf-8 -*-
"""回复风格提取器：从 ChatLab 聊天数据提炼「我的回复风格」档案。

流程：
1. chatlab messages between --member 1 --member 2 拉最近对话（agent 格式）
2. 只取「我」发出的消息（me 角色）作为风格样本
3. DeepSeek 分析：风格特征 / 口头禅 / 语气 / 话题模式 / 相处动态 / 风格示例
4. 输出结构化 JSON → data/style_profile.json → 引擎动态注入 system prompt

用法：python style_profile.py            # 提取并保存
      python style_profile.py --show     # 只显示当前档案
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

# 冻结（EXE）模式下以 exe 所在目录为根
if getattr(sys, "frozen", False):
    ROOT = Path(sys.executable).resolve().parent
else:
    ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from goutou.engine import call_openai_compatible, load_api_key  # noqa: E402

CONFIG = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
PROFILE_PATH = ROOT / "data" / "style_profile.json"

ANALYZE_PROMPT = """你是对话风格分析师。下面是一段恋爱聊天记录中「我」发出的全部消息（按时间顺序）。

请提炼「我」的回复风格，输出严格的 JSON（不要 markdown 代码块，不要多余文字）：

{{
  "style_features": ["风格特征1", "风格特征2", ...最多6条，每条一句话，聚焦：语气、长度、结构、主动/被动、关怀方式"],
  "catchphrases": ["口头禅/高频表达，如'孩子'，最多8个"],
  "tone": "一句话总结整体语气（如：嘴硬心软，调侃式照顾，话少但行动多）",
  "humor_style": "一句话总结调侃/幽默方式（如何互损、接梗、自嘲）",
  "care_style": "一句话总结关心表达方式（如何表达在意：行动/语言/承诺，给具体例子）",
  "reply_patterns": ["典型回复模式1", "模式2", ...最多5条，如：先接情绪再给行动/用自嘲化解对方焦虑"],
  "topics_affinity": {{"最爱聊": ["王者", "吃的"], "他主动发起": ["请客", "陪玩"], "回避话题": []}},
  "style_examples": ["3条最能代表我风格的回复示例（尽量原文或近原文）"]
}}

规则：
- 只基于提供的消息原文，不脑补
- 「我」的消息可能包含语音转文字（[语音转文字] 前缀），照常分析
- 忽略系统消息、表情包占位符（[表情包] [动画表情]）、图片路径
"""


def safe_filename(name: str) -> str:
    """对象名 → 安全文件名（去除 Windows 非法字符）。"""
    import re as _re
    return _re.sub(r'[\\/:*?"<>|\r\n]', "_", name).strip() or "default"


def profile_path_for(target_name: str | None = None) -> Path:
    """风格档案路径：指定对象 → data/style_profiles/<对象>.json；否则默认 data/style_profile.json。"""
    if target_name:
        return ROOT / "data" / "style_profiles" / f"{safe_filename(target_name)}.json"
    return PROFILE_PATH


def find_chatlab_session(cli: str, target_name: str) -> str | None:
    """在 ChatLab 会话列表里按名称找目标会话，返回 session id 或 None。"""
    cmd = [cli, "sessions", "list", "--format", "json"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             timeout=60).stdout
    except FileNotFoundError:
        cmd[0] = "chatlab.cmd"
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             timeout=60).stdout
    try:
        data = json.loads(out)
        items = data.get("data", {}).get("items", [])
    except json.JSONDecodeError as e:
        print(f"ChatLab 会话列表解析失败: {e}")
        return None
    for item in items:
        if item.get("name") == target_name:
            return item.get("id")
    return None


def fetch_my_messages(limit: int = 60, target_name: str | None = None,
                      session: str | None = None) -> list[str]:
    """从 ChatLab 拉最近对话，返回「我」发的消息列表。

    target_name 指定对象时：自动定位该对象的 ChatLab 会话（同名匹配），
    并从该会话提取「我」的消息。未指定时用 config 默认会话。
    """
    cli = CONFIG["chatlab"]["cli"]

    if target_name:
        found = find_chatlab_session(cli, target_name)
        if not found:
            print(f"ChatLab 中没有「{target_name}」的会话，请先导入该对象的聊天数据。")
            return []
        session = found
        print(f"使用 ChatLab 会话: {target_name} ({found})")
    elif session is None:
        session = CONFIG["chatlab"]["session"]

    # 确定「我」和对方的 member id：先尝试只读 SQL 拿 wxid 精确匹配，失败回退名字匹配
    me_id = her_id = None
    sql_out = None
    cmd = [cli, "sql", "SELECT id, platform_id, account_name FROM member", "--format", "json"]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
        sql_out = r.stdout if r.returncode == 0 else None
    except FileNotFoundError:
        cmd[0] = "chatlab.cmd"
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=60)
        sql_out = r.stdout if r.returncode == 0 else None

    my_wxid = CONFIG["me"]["wxid"]
    my_name = CONFIG["me"]["name"]
    if sql_out:
        try:
            for row in json.loads(sql_out).get("data", {}).get("rows", []):
                pid = str(row.get("platform_id") or "")
                mid = str(row.get("id"))
                if pid == my_wxid:
                    me_id = mid
                elif mid != me_id:
                    her_id = mid
        except (json.JSONDecodeError, AttributeError):
            pass

    if not me_id or not her_id:
        # 回退：members list 按名字匹配
        cmd = [cli, "members", "list", "--session", session, "--format", "json"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                 timeout=60).stdout
        except FileNotFoundError:
            cmd[0] = "chatlab.cmd"
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                 timeout=60).stdout
        try:
            members = json.loads(out).get("data", {}).get("items", [])
            for m in members:
                if m.get("name") == my_name:
                    me_id = str(m.get("id"))
                else:
                    her_id = str(m.get("id"))
        except (json.JSONDecodeError, AttributeError):
            pass
    if not me_id or not her_id:
        print(f"无法确认会话 {session} 的成员映射，请检查 ChatLab 数据。")
        return []

    cmd = [cli, "messages", "between", "--member", me_id, "--member", her_id,
           "--session", session, "--limit", "500", "--format", "agent"]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             timeout=90).stdout
    except FileNotFoundError:
        cmd[0] = "chatlab.cmd"
        out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                             timeout=90).stdout

    try:
        data = json.loads(out)
        text = data.get("data", {}).get("text", "")
    except json.JSONDecodeError as e:
        print(f"ChatLab 输出解析失败: {e}")
        print(out[:500])
        return []

    # 从成员列表确认「我」的名字（该会话中 wxid 匹配 config 的即是我）
    me_name = CONFIG["me"]["name"]
    my_msgs: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("["):
            continue
        m = re.match(r"\[#?\d+[-\d]*\] (\d{1,2}:\d{2}(?::\d{2})?) (.+?): (.*)", line)
        if not m:
            continue
        _, name, content = m.groups()
        if name != me_name:
            continue
        content = content.strip()
        if not content or content.startswith(("[", "../images")):
            continue
        # 去掉语音转文字前缀标记，保留正文
        content = re.sub(r"^\[语音转文字\]\s*", "", content)
        if content:
            my_msgs.append(content)
    return my_msgs[-limit:]


def extract_profile(my_msgs: list[str], model: str) -> dict:
    """调用 DeepSeek 提炼风格档案。"""
    if not my_msgs:
        raise RuntimeError("没有可用的「我」的消息样本")
    sample = "\n".join(f"{i+1}. {m}" for i, m in enumerate(my_msgs))
    user = f"以下是我发出的消息（共 {len(my_msgs)} 条，最近）:\n\n{sample}\n\n请按规则输出 JSON。"
    api_key = load_api_key()
    messages = [
        {"role": "system", "content": ANALYZE_PROMPT},
        {"role": "user", "content": user},
    ]
    raw = call_openai_compatible(api_key, messages, model=model, temperature=0.4,
                                 timeout=120, max_tokens=1500)
    # 提取 JSON（容忍 markdown 代码块包裹）
    text = raw.strip()
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise RuntimeError(f"模型输出不是 JSON: {text[:200]}")
    profile = json.loads(m.group(0))
    return profile


def save_profile(profile: dict, target_name: str | None = None) -> Path:
    path = profile_path_for(target_name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"target": target_name,
                    "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "profile": profile},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_profile(target_name: str | None = None) -> dict | None:
    """读取风格档案（profile 部分）。指定对象时读该对象档案；不存在回退默认档案。返回 None 表示都没有。"""
    if target_name:
        path = profile_path_for(target_name)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                return data.get("profile")
            except (json.JSONDecodeError, OSError):
                pass
    if not PROFILE_PATH.exists():
        return None
    try:
        data = json.loads(PROFILE_PATH.read_text(encoding="utf-8"))
        return data.get("profile")
    except (json.JSONDecodeError, OSError):
        return None


def list_profiles() -> list[str]:
    """列出已有风格档案对应的对象名（含默认）。"""
    names = []
    if PROFILE_PATH.exists():
        names.append("默认")
    profiles_dir = ROOT / "data" / "style_profiles"
    if profiles_dir.exists():
        for f in profiles_dir.glob("*.json"):
            names.append(f.stem)
    return names


def main() -> None:
    parser = argparse.ArgumentParser(description="提取回复风格档案")
    parser.add_argument("--show", action="store_true", help="只显示当前档案")
    parser.add_argument("--samples", type=int, default=60, help="样本条数")
    parser.add_argument("--target", type=str, default=None, help="对象名（自动定位其 ChatLab 会话并按对象保存）")
    args = parser.parse_args()

    if args.show:
        profile = load_profile(args.target)
        if not profile:
            print(f"还没有「{args.target or '默认'}」的风格档案，先运行: python style_profile.py --target 对象名")
            return
        print(json.dumps(profile, ensure_ascii=False, indent=2))
        return

    print(f"从 ChatLab 拉取聊天数据…（对象: {args.target or '默认'}）")
    my_msgs = fetch_my_messages(args.samples, target_name=args.target)
    print(f"提取到「我」的消息 {len(my_msgs)} 条")
    if not my_msgs:
        sys.exit(1)

    print("DeepSeek 分析回复风格…")
    profile = extract_profile(my_msgs, model=CONFIG["llm"]["model"])
    path = save_profile(profile, target_name=args.target)
    print(f"\n✅ 风格档案已保存: {path}")
    print(json.dumps(profile, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
