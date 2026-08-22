# -*- coding: utf-8 -*-
"""去AI味：prompt 规则（方案A，零成本）+ 可选二次重写 pass（方案B）。"""

HUMANIZE_RULES = """
## 去AI味规则（最高优先级，与铁律同级）
- 禁用"首先/其次/最后/综上所述/总的来说/简而言之/值得注意的是/毋庸置疑/不得不说"等连接词与总结腔
- 禁止整齐的排比句式、过度对称的项目符号、标准化的"既...又.../不仅...而且..."结构
- 句子长短错落，允许口语化停顿、犹豫、自我反驳、句中反转、语气词（啊/呢/吧/嘛/哈）
- 用词具体、接地气，禁止空洞形容词与"赋能/抓手/闭环/落地/赛道"式套话
- 不要写"作为AI/作为一个助手"等自指句
- 回复要像微信真人聊天：碎片化、不完整、带情绪温度、甚至有点不着边际但接得住
"""

HUMANIZE_PASS_PROMPT = (
    "你是去AI味重写器。把输入改成像微信真人聊天的语感：\n"
    "1. 删掉「首先/其次/综上所述/值得注意的是」等连接词与总结腔\n"
    "2. 打破整齐排比；句子长短错落，可加语气词（啊/呢/吧/嘛/哈）\n"
    "3. 用词具体接地气，禁用「赋能/抓手/闭环/落地」等套话\n"
    "4. 允许口语化停顿、犹豫、自我反驳\n"
    "5. 输出仅一条可直接发送的微信回复（5-50字，无引号、无解释）\n"
    "6. 保留原意与情绪温度，只改表达"
)


def clean_reply(text: str) -> str:
    """清洗生成结果：去引号、去解释性前缀。"""
    t = text.strip()
    if len(t) >= 2 and t[0] in "\"'“" and t[-1] in "\"'”":
        t = t[1:-1].strip()
    import re
    t = re.sub(r"^(回复|发送|发这条|直接发)[:：]\s*", "", t)
    return t.strip()


def humanize_reply(provider, text: str) -> str:
    """二次去味 pass。provider 调用失败 → 返回原文（优雅降级）。"""
    messages = [
        {"role": "system", "content": HUMANIZE_PASS_PROMPT},
        {"role": "user", "content": text},
    ]
    try:
        out = provider.chat(messages, temperature=0.3, max_tokens=120, timeout=20)
        return clean_reply(out) or text
    except Exception:
        return text
