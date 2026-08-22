# -*- coding: utf-8 -*-
"""异地判断：配置城市优先 → 关键词 → 城市词统计。从 goutou/approval.py 拆分。"""

CITY_DICT = [
    "北京", "上海", "广州", "深圳", "杭州", "成都", "重庆", "武汉", "西安",
    "南京", "苏州", "郑州", "长沙", "东莞", "佛山", "合肥", "昆明", "青岛",
    "济南", "大连", "厦门", "福州", "哈尔滨", "沈阳", "石家庄", "太原",
    "南昌", "南宁", "贵阳", "兰州", "乌鲁木齐", "呼和浩特", "银川", "西宁",
    "拉萨", "海口", "三亚", "临沂", "无锡", "常州", "徐州", "温州", "宁波",
    "绍兴", "嘉兴", "珠海", "中山", "惠州", "泉州", "烟台", "潍坊", "洛阳",
]


def detect_distance(history: list[dict[str, str]], me_city: str = "",
                    her_city: str = "") -> str:
    """返回 '同城' / '异地' / '未知'。"""
    me_city = (me_city or "").strip()
    her_city = (her_city or "").strip()
    if me_city and her_city:
        return "同城" if me_city == her_city else "异地"

    text_all = "\n".join(item.get("text", "") for item in history[-60:])
    if "异地" in text_all or "我们俩异地" in text_all:
        return "异地"
    if "同城" in text_all:
        return "同城"
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


def analyze_distance_with_llm(sample_text: str, provider) -> str:
    """LLM 语境分析异地状态（provider: LLMProvider）。"""
    messages = [
        {"role": "system", "content": DISTANCE_ANALYZE_PROMPT},
        {"role": "user", "content": f"聊天记录样本（最近）：\n{sample_text[:8000]}"},
    ]
    r = provider.chat(messages, temperature=0.1, max_tokens=10, timeout=30)
    r = (r or "").strip()
    if "异地" in r:
        return "异地"
    if "同城" in r:
        return "同城"
    return "未知"
