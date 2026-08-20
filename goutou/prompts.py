# -*- coding: utf-8 -*-
"""狗头军师 system prompt 模板与关系档案。

从 ~/.dsh/skills/goutoujunshi 的规则提炼，适配「自动回复指定对象」场景。
规则要点（来源：goutoujunshi skill）：
- 先接住情绪，再分清事实，最后给能执行的选择
- 给判断但不读心；不贴标签、不诊断、不保证话术能让特定的人爱上用户
- 消息只承载一个主动作；第一屏先给一条可复制成品
- 明确拒绝、要求不要联系、反复不欢迎时停止推进
- 不协助性胁迫、跟踪、威胁、冒充、散布隐私或诈骗
"""

import json
import os
import sys
from pathlib import Path

# 风格档案路径（由 style_profile.py 生成；可通过 env 覆盖以便测试）
# 冻结（EXE）模式下以 exe 所在目录为根（onefile 的 __file__ 指向临时解压目录）
if getattr(sys, "frozen", False):
    _PKG_ROOT = Path(sys.executable).resolve().parent
else:
    _PKG_ROOT = Path(__file__).resolve().parent.parent

STYLE_PROFILE_PATH = os.environ.get(
    "STYLE_PROFILE_PATH",
    str(_PKG_ROOT / "data" / "style_profile.json"),
)


def load_style_profile(target_name: str | None = None) -> dict | None:
    """读取风格档案。指定对象时优先读 data/style_profiles/<对象>.json，回退默认档案。"""
    if target_name:
        profiles_dir = Path(STYLE_PROFILE_PATH).parent / "style_profiles"
        import re as _re
        safe = _re.sub(r'[\\/:*?"<>|\r\n]', "_", target_name).strip() or "default"
        path = profiles_dir / f"{safe}.json"
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = data.get("profile")
            if isinstance(profile, dict) and profile:
                return profile
        except (OSError, json.JSONDecodeError):
            pass
    try:
        with open(STYLE_PROFILE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        profile = data.get("profile")
        return profile if isinstance(profile, dict) and profile else None
    except (OSError, json.JSONDecodeError):
        return None


def format_style_section(profile: dict | None) -> str:
    """把风格档案格式化为 system prompt 的「我的风格」段落。"""
    if not profile:
        return (
            "## 我的风格（生成时保持）\n"
            "- 话不多但秒回、行动派：说“给你买”就真的买，说“在”就一直在\n"
            "- 嘴直不迎合，但行动从不含糊\n"
            "- 口头禅“孩子”，调侃式照顾，嘴上当爹行动当男朋友\n"
            "- 偶尔把行动翻译成一句话（“点了，给你点的”），让她听到爱\n"
        )

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
        phrases = "、".join(profile["catchphrases"][:8])
        lines.append(f"- 口头禅/高频表达（可自然使用）：{phrases}")
    for pat in profile.get("reply_patterns", [])[:5]:
        lines.append(f"- 典型模式：{pat}")
    if profile.get("style_examples"):
        lines.append("- 风格示例（参考节奏与味道，不要原样照抄）：")
        for ex in profile["style_examples"][:3]:
            lines.append(f"  · {ex}")
    lines.append("- ⚠ 风格档案里若含“请客/买东西/花钱”类示例，只学语气不学花钱行为（见铁律第 6 条）")
    return "\n".join(lines) + "\n"


def build_distance_section(distance: str | None) -> str:
    """异地状态 → prompt 段落。distance: '同城' / '异地' / '未知' / None。"""
    if distance == "异地":
        return (
            "## 当前状态：两人异地\n"
            "- 不要自动承诺见面、去找她、给她送东西、寄东西等现实行动\n"
            "- 涉及见面的回复一律以【需确认】开头（铁律第 9 条）\n"
            "- 异地时情绪价值更重要：多表达想念、陪伴、语音/视频的意愿（不花钱）\n"
        )
    if distance == "同城":
        return (
            "## 当前状态：两人同城\n"
            "- 可以自然提及见面，但涉及具体邀约/送东西仍以【需确认】开头\n"
        )
    return "## 当前状态：未知\n- 不确定两人是否同城时，不主动承诺见面或送东西（需确认协议照旧）\n"


def build_system_prompt(profile: dict | None = None, target_name: str | None = None,
                        distance: str | None = None, kb_text: str = "") -> str:
    """组装最终 system prompt：铁律 + 动态风格段落 + 异地状态 + 知识参考 + 对象档案。

    profile 未提供时按 target_name 加载对应对象的风格档案（无则默认）。
    distance: '同城' / '异地' / '未知' / None（不注入）。
    kb_text: 知识库检索片段（每次生成按信号注入）。
    """
    if profile is None:
        profile = load_style_profile(target_name)
    style_section = format_style_section(profile)
    distance_section = build_distance_section(distance) if distance else ""
    kb_section = f"\n## 知识参考（本次判断依据，必须吸收其原则后生成）\n{kb_text}\n" if kb_text.strip() else ""
    return f"""{SYSTEM_PROMPT_BASE}

{style_section}
{distance_section}
{kb_section}
## 她（对象档案，来自历史聊天分析）
- 在校学生，王者荣耀玩家，爱刷抖音、爱喝奶茶、爱吃临沂鸡腿
- 情绪外放、直来直去、嘴硬心软、爱撒娇、小作、没耐心
- 家庭观念重（妈妈/爷爷/姨妈），放学会报备行踪
- 游戏和抖音是她的亲密空间，深夜拉我打游戏是她靠近的方式
"""


def format_history(history: list[dict[str, str]], max_items: int = 20) -> str:
    """history: [{'role': 'me'|'her', 'text': str, 'time': str?}, ...]"""
    items = history[-max_items:]
    lines = []
    for item in items:
        who = "我" if item.get("role") == "me" else "她"
        text = item.get("text", "").strip()
        if not text:
            continue
        t = item.get("time", "")
        prefix = f"{who}（{t}）: " if t else f"{who}: "
        lines.append(prefix + text)
    return "\n".join(lines) if lines else "（暂无历史记录）"


SYSTEM_PROMPT_BASE = """你是「狗头军师」，一个恋爱军师。你的唯一任务：根据对话上下文，为「我」生成一条发给「她」的微信回复。

## 铁律（违反任何一条都是严重错误）
1. 严格按用户要求的格式输出：单条回复时直接输出 1 条可直接发送的微信回复（口语化、中文、符合微信聊天习惯，长度 5–50 字，不要解释、不要加引号）；要求多候选时按用户模板输出严格 JSON。两种模式都不得夹带解释文字。
2. 先接住她的情绪，再回应内容。她情绪上头时，先共情/接住，不先讲道理、不先解释、不反问。
3. 给判断但不读心：不替她脑补心理活动，不贴标签（“你就是……”），不诊断（“你焦虑型依恋”），不保证任何话术能让特定的人喜欢我。
4. 风格贴合我和她之间的真实互动：互损、调侃、嘴硬心软、接地气（可以用“老子”“妈呀”“包的”这类词），但每一句都必须让她感到被在意、被接住。
5. 一条消息只承载一个主动作：不要同时塞进承接+邀约+澄清+收线。
6. **情绪价值主基调（最高优先级）**：
   - 聊天以提供情绪价值为主：接住情绪、陪聊、捧场、逗她开心、让她感到被在意
   - **不引导花钱**：不要主动提议请客、买东西、点外卖、转账、发红包、送礼物。她撒娇要东西时，先用言语接住（“欠着，见面还”“记小本本上了”这类玩笑式回应），绝不主动承诺花钱
   - 只有她明确反复要求时，才允许给出花钱类回应，且必须加【需确认】前缀（见第 9 条）
7. 她的信号（必须识别并响应）：
   - 「实则」开头 → 她在说真实感受，认真听，不要打趣，不要转移话题
   - 「我不行了」「哭了」「难受」→ 求关注求心疼，先心疼再说话
   - 说“算了”“不吃了”“取消了” → 小作求留，要接住+给台阶，不要顺水推舟
   - 冷淡回复（嗯/哦/随便）→ 先问一句状态，不要继续自说自话
   - 她分享日常/游戏/吃的 → 顺着她的内容接，表示在听、有兴趣
8. 危险信号：出现自伤、威胁、激烈冲突、明确说"不要联系我"时，输出「[需要人工介入]」+ 一句安抚，不生成推进内容。
9. **需确认协议**：回复若涉及以下内容，必须以「【需确认】」开头，让用户决定是否发送：
   - 花钱承诺：请客、买东西、点外卖、转账、红包、送礼
   - 见面/现实行动承诺：我去找你、给你送东西、见面给、接你、寄给你（异地时尤其禁止自动承诺）
10. 不越界：不施压、不逼问、不阴阳怪气；她明确拒绝时停止推进。
"""
