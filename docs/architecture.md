# 架构文档

## 分层总览

```
┌─────────────────────────────────────────────┐
│ ui/          桌面 GUI（tkinter，单实例）      │
│ main.py      CLI 入口                        │
├─────────────────────────────────────────────┤
│ adapters/    平台适配层（微信/未来其他 IM）   │
│   wechat_wxauto.py  wxauto4 封装            │
├─────────────────────────────────────────────┤
│ goutou/      核心引擎（平台无关）            │
│   engine.py      编排：信号→知识→prompt→LLM  │
│   signals.py     信号检测（离线规则）        │
│   kb.py          知识库检索                  │
│   approval.py    需确认检测 + 异地判断       │
│   prompts.py     system prompt 组装         │
│   style.py       风格档案（计划拆分）        │
├─────────────────────────────────────────────┤
│ kb/          关系心理学知识库（MIT）         │
│ data/        风格档案 / 状态 / 日志（用户数据）│
└─────────────────────────────────────────────┘
```

## 数据流（一次回复）

```
微信新消息
  → platform.adapter.get_new_messages()        # 增量读取
  → 锚定确认（列表最后一条 + 内容比对，防误发）
  → goutou.signals.detect_signals()            # 信号：实则/撒娇/生气/冷淡…
  → goutou.kb.retrieve(signals)                # 知识库检索（主题路由）
  → goutou.prompts.build_system_prompt()       # 铁律 + 风格 + 异地 + 知识片段
  → goutou.engine.call_openai_compatible()     # LLM 生成（OpenAI 兼容）
  → clean + 需确认检测（花钱/见面词）
  → 需确认 ? 转 pending（人工确认） : 按模式发送
```

## 可替换点（商业化/定制基础）

| 层 | 替换方式 |
|---|---|
| LLM | 改 `llm.base_url` 为任意 OpenAI 兼容端点；模型任意 |
| 知识库 | 替换 `kb/references` 内容，或设置 `GOUTOU_KB_DIR` 环境变量 |
| 平台 | 实现 `adapters.wechat_wxauto.WeChatAdapter` 同款接口（list_sessions/switch_to/get_new_messages/send…） |
| 风格档案 | `data/style_profiles/<对象>.json`，或修改 `goutou/prompts.py` 的档案格式 |
| 信号/边界 | `goutou/signals.py`、`goutou/approval.py` 的词典 |

## 数据与隐私

- `data/` 下的风格档案与状态均为本地文件
- 聊天内容只用于：窗口内实时读取、生成时的上下文（最近 20 条）、风格提取（ChatLab 数据）
- 不保存完整聊天记录到磁盘
