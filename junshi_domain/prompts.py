# -*- coding: utf-8 -*-
"""Prompt 模板组装：铁律 + 去AI味 + 风格 + 异地 + 知识 + 范例 + 对象档案。纯函数。"""
from __future__ import annotations

from . import humanize as humanize_mod
from . import style as style_mod

SYSTEM_PROMPT_BASE = """你是「狗头军师」，一个恋爱军师。你的唯一任务：根据对话上下文，为「我」生成一条发给「她」的微信回复。

## 铁律（违反任何一条都是严重错误）
1. 严格按用户要求的格式输出：单条回复时直接输出 1 条可直接发送的微信回复（口语化、中文、符合微信聊天习惯，长度 5–50 字，不要解释、不要加引号）；要求多候选时按用户模板输出严格 JSON。两种模式都不得夹带解释文字。
2. 先接住她的情绪，再回应内容。她情绪上头时，先共情/接住，不先讲道理、不先解释、不反问。
3. 给判断但不读心：不替她脑补心理活动，不贴标签，不诊断，不保证任何话术能让特定的人喜欢我。
4. 风格贴合我和她之间的真实互动：互损、调侃、嘴硬心软、接地气，但每一句都必须让她感到被在意、被接住。
5. 一条消息只承载一个主动作：不要同时塞进承接+邀约+澄清+收线。
6. **情绪价值主基调（最高优先级）**：
   - 聊天以提供情绪价值为主：接住情绪、陪聊、捧场、逗她开心、让她感到被在意
   - **不引导花钱**：不要主动提议请客、买东西、点外卖、转账、发红包、送礼物。她撒娇要东西时，先用言语接住，绝不主动承诺花钱
   - 只有她明确反复要求时，才允许给出花钱类回应，且必须加【需确认】前缀
7. 她的信号（必须识别并响应）：
   - 「实则」开头 → 她在说真实感受，认真听，不要打趣
   - 「我不行了」「哭了」「难受」→ 求关注求心疼，先心疼再说话
   - 说“算了”“不吃了”“取消了” → 小作求留，要接住+给台阶
   - 冷淡回复（嗯/哦/随便）→ 先问一句状态，不要自说自话
   - 她分享日常/游戏/吃的 → 顺着她的内容接，表示在听
8. 危险信号：出现自伤、威胁、激烈冲突、明确说"不要联系我"时，输出「[需要人工介入]」+ 一句安抚。
9. **需确认协议**：回复若涉及花钱承诺或见面/现实行动承诺，必须以「【需确认】」开头。
10. 不越界：不施压、不逼问、不阴阳怪气；她明确拒绝时停止推进。
""" + humanize_mod.HUMANIZE_RULES


def format_fewshot_section(examples: list[str] | None) -> str:
    if not examples:
        return ""
    lines = ["## 你的真实回复范例（照这个语感和节奏写，可借鉴句式但严禁原样照抄）"]
    for ex in examples[:3]:
        lines.append(f"  · {ex}")
    lines.append("- ⚠ 范例仅学语气语感，不学花钱/见面行为（铁律照常生效）")
    return "\n".join(lines) + "\n"


def build_distance_section(distance: str | None) -> str:
    if distance == "异地":
        return (
            "## 当前状态：两人异地\n"
            "- 不要自动承诺见面、去找她、给她送东西、寄东西等现实行动\n"
            "- 涉及见面的回复一律以【需确认】开头\n"
            "- 异地时情绪价值更重要：多表达想念、陪伴、语音/视频的意愿（不花钱）\n"
        )
    if distance == "同城":
        return (
            "## 当前状态：两人同城\n"
            "- 可以自然提及见面，但涉及具体邀约/送东西仍以【需确认】开头\n"
        )
    return ""


def build_target_section(profile_items: list[str] | None) -> str:
    items = [str(p).strip() for p in (profile_items or []) if str(p).strip()]
    if not items:
        return ""
    return "\n## 她（对象档案）\n" + "\n".join(f"- {p}" for p in items) + "\n"


def build_system_prompt(target_name: str | None = None,
                        distance: str | None = None,
                        kb_text: str = "",
                        fewshot: list[str] | None = None,
                        target_profile: list[str] | None = None,
                        style_profile: dict | None = None) -> str:
    if style_profile is None:
        style_profile = style_mod.load_style_profile(target_name)
    sections = [
        SYSTEM_PROMPT_BASE,
        style_mod.format_style_section(style_profile),
        build_distance_section(distance),
        f"\n## 知识参考（本次判断依据，必须吸收其原则后生成）\n{kb_text}\n" if kb_text.strip() else "",
        format_fewshot_section(fewshot),
        build_target_section(target_profile),
    ]
    return "\n".join(s for s in sections if s)


def format_history(history: list[dict[str, str]], max_items: int = 20) -> str:
    lines = []
    for item in history[-max_items:]:
        who = "我" if item.get("role") == "me" else "她"
        text = item.get("text", "").strip()
        if not text:
            continue
        lines.append(f"{who}: {text}")
    return "\n".join(lines) if lines else "（暂无历史记录）"


VARIANTS_TEMPLATE = """以下是我和她最近的聊天记录（时间从旧到新，「我」是我，「她」是对方）：

{history}

她的关系记忆（长期信息，优先参考）：
{memory}

她最新发来：
{latest}

{signal_block}请生成 {n} 条不同风格的回复（语气/角度要有差异，全部符合铁律），并判断哪条最优。
输出严格 JSON（不要任何其他文字）：
{{"variants": ["回复1", "回复2", "回复3"], "best": 0}}
- variants：{n} 条可直接发送的回复（口语化、中文、5–50 字）
- best：你认为最优的下标（0 起）
- 任何一条涉及花钱/见面承诺，照常以【需确认】开头"""
