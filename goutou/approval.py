# -*- coding: utf-8 -*-
"""安全与边界：需确认检测（花钱/见面承诺）+ 异地判断。"""

# 花钱承诺 / 见面承诺关键词（命中 → 回复需人工确认）
APPROVAL_MONEY_KEYWORDS = [
    "给你买", "请你吃", "给你点", "转账", "发红包", "给你打钱", "请你喝",
    "给你订", "送你", "给你寄", "给你送", "给你带", "给你付", "红包",
]
APPROVAL_MEET_KEYWORDS = [
    "我去找你", "来找你", "过来找你", "见面", "当面", "去找你", "接你",
    "给你送过去", "带给你", "给你拿过去", "过去找你", "我去接",
]
NEEDS_APPROVAL_PREFIX = "【需确认】"

# 城市词典（异地判断用）
CITY_DICT = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安",
    "南京", "苏州", "郑州", "长沙", "东莞", "佛山", "合肥", "昆明", "青岛",
    "济南", "大连", "厦门", "福州", "哈尔滨", "沈阳", "石家庄", "太原",
    "南昌", "南宁", "贵阳", "兰州", "乌鲁木齐", "呼和浩特", "银川", "西宁",
    "拉萨", "海口", "三亚", "临沂", "无锡", "常州", "徐州", "温州", "宁波",
    "绍兴", "嘉兴", "珠海", "中山", "惠州", "泉州", "烟台", "潍坊", "洛阳",
]


def detect_needs_approval(reply: str) -> bool:
    """本地规则检测：回复是否涉及花钱/见面承诺（需人工确认）。"""
    for kw in APPROVAL_MONEY_KEYWORDS + APPROVAL_MEET_KEYWORDS:
        if kw in reply:
            return True
    return False


def detect_distance(history: list[dict[str, str]], me_city: str = "", her_city: str = "") -> str:
    """判断两人是否异地。返回 '同城' / '异地' / '未知'。

    优先用配置的城市；未配置时扫描聊天记录中的城市词，
    出现 ≥2 个不同城市或出现「异地」字样 → 异地倾向。
    """
    me_city = (me_city or "").strip()
    her_city = (her_city or "").strip()
    if me_city and her_city:
        return "同城" if me_city == her_city else "异地"

    # 关键词直判
    text_all = "\n".join(item.get("text", "") for item in history[-60:])
    if "异地" in text_all or "我们俩异地" in text_all:
        return "异地"
    if "同城" in text_all:
        return "同城"

    # 城市词统计（含「我在/在…上学上班」模式识别）
    cities = [c for c in CITY_DICT if c in text_all]
    if len(cities) >= 2:
        return "异地"
    return "未知"


DISTANCE_ANALYZE_PROMPT = """根据以下情侣聊天记录样本，判断两人是否异地恋。

判断依据：
- 两人所在城市不同 / 长期分居两地 / 见面需要计划长途行程 / 提到"我去找你""放暑假见面""视频聊天代替见面" → 异地
- 都在同一城市 / 日常可随时见面 / 提到"下班来接我""周末约饭" → 同城
- 信息不足，无法判断 → 未知

只输出一个词：异地 或 同城 或 未知，不要任何其他文字。"""


def analyze_distance_with_llm(sample_text: str, api_key: str, base_url: str, model: str) -> str:
    """LLM 语境分析异地状态（规则分析无结果时的增强手段）。"""
    from .engine import call_openai_compatible
    messages = [
        {"role": "system", "content": DISTANCE_ANALYZE_PROMPT},
        {"role": "user", "content": f"聊天记录样本（最近）：\n{sample_text[:8000]}"},
    ]
    r = call_openai_compatible(api_key, messages, base_url=base_url, model=model,
                               temperature=0.1, timeout=30, max_tokens=10)
    r = (r or "").strip()
    if "异地" in r:
        return "异地"
    if "同城" in r:
        return "同城"
    return "未知"


def analyze_distance_from_chatlab(target_name: str, cli: str = "chatlab",
                                  session: str = "") -> str | None:
    """自动异地分析：从 ChatLab 全量聊天数据推断（未配置城市时的自动识别）。

    返回 '同城' / '异地' / '未知'；ChatLab 不可用时返回 None。
    """
    import json
    import re
    import subprocess

    try:
        # 定位会话
        if not session:
            try:
                out = subprocess.run([cli, "sessions", "list", "--format", "json"],
                                     capture_output=True, text=True, encoding="utf-8", timeout=60)
            except FileNotFoundError:
                cli = "chatlab.cmd"
                out = subprocess.run([cli, "sessions", "list", "--format", "json"],
                                     capture_output=True, text=True, encoding="utf-8", timeout=60)
            if out.returncode != 0:
                raise RuntimeError("sessions list 失败")
            for item in json.loads(out.stdout).get("data", {}).get("items", []):
                if item.get("name") == target_name:
                    session = item.get("id")
                    break
        if not session:
            return None

        # 拉最近对话（agent 格式；加大 token 预算避免截断，覆盖更多消息）
        cmd = [cli, "messages", "between", "--member", "1", "--member", "2",
               "--session", session, "--limit", "500", "--max-tokens", "20000",
               "--format", "agent"]
        try:
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=90)
        except FileNotFoundError:
            cli = "chatlab.cmd"
            cmd[0] = cli
            out = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", timeout=90)
        if out.returncode != 0:
            return None
        text = json.loads(out.stdout).get("data", {}).get("text", "")

        # 提取消息正文 → 城市词分析
        msgs = []
        for line in text.splitlines():
            m = re.match(r"\[#?\d+[-\d]*\] \d{1,2}:\d{2}(?::\d{2})? .+?: (.*)", line.strip())
            if m:
                content = m.group(1).strip()
                if content and not content.startswith(("[", "../images")):
                    msgs.append(content)

        # 归属识别：「我」的城市 vs 「她」的城市
        text_all = "\n".join(msgs)
        found = [c for c in CITY_DICT if c in text_all]
        # 模式：我在XX / 在XX上学|上班|工作 / 回XX
        pattern_cities = []
        for c in CITY_DICT:
            if re.search(rf"(?:我在|我在市|在|回|去|到|来|住){c}(?:市|上学|上班|工作|读书|那边)?", text_all):
                pattern_cities.append(c)
        cities = list(dict.fromkeys(found + pattern_cities))
        if len(cities) >= 2:
            return "异地"
        if "异地" in text_all:
            return "异地"
        if cities:
            return "未知"  # 只有一个城市线索，无法确定归属
        return "未知"
    except Exception:
        return None
