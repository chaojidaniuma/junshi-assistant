# 军师助手 · junshi-assistant

> 基于 Codex Harness（Thread → Turn → Item）理念的微信 AI 回复 Agent 运行时。
> v2 全新架构：有记忆、会思考、可审批、可扩展 —— 微信自动回复只是第一个应用场景。

## 架构

```
junshi_harness/      Agent 运行时核心
├── item.py          Item：原子事件（her_message/signal_detected/variant_generated/...）
├── turn.py          Turn 执行器：信号→知识→范例→生成→审批→发送 状态机
├── thread.py        Thread：一个对象一个会话（多对象并行的基石）
├── store.py         SQLite 持久化（threads/turns/items/memory/approvals）
├── event_bus.py     类型安全事件总线（WebSocket 直推结构化 Item）
├── approval.py      分级审批引擎（auto/suggest/manual + 规则优先级 + 可注入时钟）
├── policy.py        执行策略（限流/防抖/失败重试上限）
├── context.py       上下文管理器（滑动窗口 + 关系记忆注入）
└── config.py        配置（JSON，深合并默认值，实例化传递无全局单例）

junshi_domain/       领域纯函数
├── signals.py       情绪信号检测（离线规则）
├── kb.py            关系心理学知识库检索（kb/references，MIT）
├── fewshot.py       真人范例召回（bigram 轻量算法，零依赖）
├── style.py         风格档案加载与格式化
├── distance.py      异地判断（配置城市→关键词→城市词统计）
├── humanize.py      去AI味（prompt 规则 + 可选二次重写 pass）
└── prompts.py       System prompt 组装

providers/           LLM 提供方（base 抽象 + OpenAI 兼容实现：重试/SSE 流式回退/JSON 提取）
adapters/            平台适配（ChatAdapter 抽象基类 + 微信 wxauto4 实现）
interfaces/web/      FastAPI REST + WebSocket + 自包含前端（毛玻璃 UI，无需 npm build）
runtime.py           MonitorRuntime：轮询循环 → Turn 触发器
run_web.py           Web 入口 → http://127.0.0.1:8766
run_cli.py           CLI 入口（与 Web 共用同一 harness 栈）
kb/                  关系心理学知识库（MIT，来自 powerycy/goutoujunshi）
docs/REDESIGN.md     v1 → v2 重设计方案（Codex Harness 理念映射）
tests/               16 项测试（harness 核心 11 + 领域层 5）
```

## 三种回复模式（顶栏切换，即时生效）

| 模式 | 行为 |
|---|---|
| **自动回复** | 正常自动发送；花钱承诺 / 异地见面 / 深夜时段等风险回复仍会被拦截到「待确认」（安全网） |
| **确认后回复**（默认） | 每条候选都进入「待确认」，由你选择一条批准发送或拒绝 |
| **仅预览** | 只生成候选供复制，绝不发送 |

## 快速开始

```bash
pip install -r requirements.txt
copy config.example.json config.json    # 填写 target.name 与 llm.api_key

python run_web.py                       # Web 界面
python run_cli.py                       # CLI 模式
python tests/test_harness.py            # 测试
python tests/test_domain.py
```

## 核心语义

- **消息可靠性**：终态 Turn（completed/failed/rejected）的消息不再处理；失败（aborted_retry）/处理中自动重试；启动恢复中断的 Turn —— 崩溃不丢消息、不重复回复
- **媒体消息**：语音/图片/表情占位符只作时间线提示，不触发回复、不污染 LLM 上下文
- **审批即数据**：所有待确认与决策持久化在 SQLite approvals 表，可回溯
- **可观测**：每轮的信号检测/知识检索/范例召回聚合为一行摘要；过程日志独立抽屉

## 开源与合规

- 本仓库代码：MIT（LICENSE）
- 内置知识库：MIT，Copyright (c) 2026 powerycy（kb/KB-LICENSE，上游 [powerycy/goutoujunshi](https://github.com/powerycy/goutoujunshi)）
- 微信适配基于 wxauto4（UI 自动化）：[zhengheng077/wxauto4](https://github.com/zhengheng077/wxauto4)
- **风险声明**：微信自动回复违反微信服务条款，存在封号风险；请仅用于合法合规的个人场景
