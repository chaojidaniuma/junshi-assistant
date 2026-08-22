# 军师助手 v1.0 重设计方案

> 基于 Codex Harness（openai/codex，Apache-2.0，2026-08-19 开源）的 Agent 运行时理念，对现有 v0.5.3 架构进行系统性重构。

---

## 一、现状诊断：为什么现在用着难受

### 1.1 架构层面的硬伤

| 问题 | 具体表现 | 后果 |
|---|---|---|
| **main.py 是上帝模块** | 22KB，轮询循环 + 状态管理 + 锚定确认 + 重试计数 + 消息处理 + 限流全塞在一起 | 改一个功能要在 500 行里找位置，加新逻辑必然引入回归 |
| **全局可变状态泛滥** | `CURRENT_TARGET`、`CONFIG`、`_last_switch_ts`、`_GEN_FAIL_COUNT`、`_ABORT_COUNT`、`_last_seen_line` 全是模块级 global | 线程不安全、无法测试、重启即丢失、多目标并行不可能 |
| **Web 层反向依赖 CLI** | `web/app.py` 里 `import main as core`，直接调用 `core.process_new_messages()`、`core.State`、`core.CONFIG` | Web 和 CLI 强耦合，CLI 改一行 Web 就崩，无法独立部署 |
| **没有真正的 Agent 循环** | 每条消息 = 一次 `generate_variants()` 调用，无工具调用、无多步推理、无上下文压缩 | 复杂场景（她连发 5 条、情绪转折、需要回忆之前约定）处理能力为零 |
| **LLM 调用是裸 urllib** | `call_openai_compatible()` 手写 HTTP，无重试、无流式、无 token 计数、无结构化输出解析 | 前端看不到生成进度，JSON 解析靠正则兜底，错误处理靠 except 吞掉 |
| **状态管理是 ad-hoc JSON** | `State` 类把去重指纹、待确认列表、限流计数、seed 标记全塞一个 `state.json` | 并发写冲突、无法查询历史、pending 条目靠 `(ts, msg)` 元组定位，脆弱 |
| **审批机制是关键词匹配** | `detect_needs_approval()` 扫 20 个关键词，命中就进 pending | 误判率高（"我给你带了个口信"也命中），无法配置审批策略，无法区分"花钱"和"见面"的不同审批等级 |

### 1.2 体验层面的痛点

- **切换目标要重建整个 adapter**：`web/app.py` 里检测到 `CURRENT_TARGET` 变化就 `WeChatAdapter()` 重新 new，旧连接直接丢弃
- **无法同时监控多个对象**：全局单例 `CURRENT_TARGET` 决定了只能一对一
- **生成过程黑盒**：用户点了启动之后只能等日志刷出来，不知道 LLM 正在想什么、卡在哪一步
- **历史上下文固定 20 条**：长对话中早期的关键约定（"她说过周末要考试"）会被挤出窗口
- **风格档案是静态 JSON**：提取一次就不变，无法根据近期对话动态调整风格
- **错误恢复靠全局计数器**：`_GEN_FAIL_COUNT[fp]` 连续 3 次放弃，但计数器在内存里，重启就清零，同一条消息会无限重试

---

## 二、Codex Harness 的核心设计理念（可迁移部分）

Codex Harness 开源的不是"一个聊天机器人"，而是一套 **Agent 运行时基础设施**。核心抽象：

```
Thread（会话）→ Turn（单轮交互）→ Item（原子事件）
```

| Harness 概念 | 本质 | 对军师助手的映射 |
|---|---|---|
| **Thread** | 一次完整对话会话，可 fork/resume，持久化存储 | 与某个对象的完整关系会话（含历史、风格档案、关系记忆） |
| **Turn** | 从用户输入到 Agent 完成的一轮，含流式 Item 序列 | 她发来一条消息 → 军师完整处理一轮（信号→知识→生成→审批→发送） |
| **Item** | Turn 内的原子事件：消息、推理、工具调用、工具结果、审批请求 | `her_message` / `signal_detected` / `kb_retrieved` / `llm_reasoning` / `variant_generated` / `approval_requested` / `message_sent` / `error` |
| **Tool Runtime** | Agent 可调用的工具，结果回灌循环 | `read_messages` / `send_message` / `switch_session` / `detect_signals` / `retrieve_kb` / `analyze_distance` / `extract_style` |
| **Approval Policy** | auto / manual / suggest，可按操作类型分级 | 普通回复 auto；花钱承诺 manual；见面承诺 manual（异地时更严格）；可配置 |
| **Context Compaction** | 长对话自动压缩，保留推理摘要 | 关系记忆压缩：她的偏好、近期约定、情绪模式，而非原始 20 条消息 |
| **Retained Reasoning** | Agent 跨轮保留的内部推理笔记 | 军师的"作战笔记"：她最近的情绪趋势、哪些回复有效、即将到来的事件 |
| **Hooks** | 生命周期钩子：pre_turn / post_turn / on_tool / on_approval | 生成前注入信号+知识，生成后人味化+审批检测，发送前锚定校验 |
| **Skills** | 可复用的能力模块，按需加载 | 风格档案 Skill、知识库 Skill、fewshot 范例 Skill、异地分析 Skill |
| **ExecPolicy** | 执行策略与权限控制 | 发送频率限制、时段限制、防误发守卫、单对象并发限制 |
| **Thread Store** | 持久化会话存储 | SQLite 替代 state.json，支持查询、回溯、多会话 |
| **Model Provider** | 模型提供方抽象层 | 现有 OpenAI 兼容调用升级为标准 provider，支持流式、重试、fallback |

### Harness 最关键的一句话

> **"Your application owns product context, business rules, and tools; Codex app-server provides the agent loop."**

翻译到军师助手：**你拥有微信适配、关系知识库、风格档案、审批规则；Harness 提供 Agent 循环、状态管理、流式输出、上下文压缩、审批框架。**

---

## 三、新架构总览

### 3.1 分层架构

```
┌─────────────────────────────────────────────────────────────────┐
│                        接入层 (Interfaces)                       │
│  ┌──────────┐  ┌──────────────┐  ┌───────────┐  ┌───────────┐  │
│  │ Web UI   │  │ CLI (codex   │  │ 桌面托盘  │  │  API 服务 │  │
│  │ (React)  │  │ exec 风格)   │  │ (可选)    │  │ (可选)    │  │
│  └────┬─────┘  └──────┬───────┘  └─────┬─────┘  └─────┬─────┘  │
│       │               │                │              │        │
│       └───────────────┴────────────────┴──────────────┘        │
│                              │                                  │
│                    ┌─────────▼──────────┐                       │
│                    │  Harness API 层    │                       │
│                    │  (Thread/Turn/     │                       │
│                    │   Item/Approval)   │                       │
│                    └─────────┬──────────┘                       │
├──────────────────────────────┼──────────────────────────────────┤
│                              │                                  │
│                    ┌─────────▼──────────┐                       │
│                    │   Agent 循环核心   │                       │
│                    │  (junshi-harness)  │                       │
│                    │                    │                       │
│                    │  • Turn 调度器     │                       │
│                    │  • 上下文管理器    │                       │
│                    │  • 工具路由器      │                       │
│                    │  • 审批引擎        │                       │
│                    │  • 钩子系统        │                       │
│                    │  • 流式事件总线    │                       │
│                    └─────────┬──────────┘                       │
│                              │                                  │
├──────────────────────────────┼──────────────────────────────────┤
│                              │                                  │
│           ┌──────────────────┼──────────────────┐               │
│           │                  │                  │               │
│  ┌────────▼───────┐  ┌──────▼───────┐  ┌───────▼──────┐        │
│  │  领域工具层     │  │  技能层      │  │  模型提供方   │        │
│  │  (Tools)       │  │  (Skills)    │  │  (Providers)  │        │
│  │                │  │              │  │               │        │
│  │ • read_chat    │  │ • style_skill│  │ • openai_compat│       │
│  │ • send_reply   │  │ • kb_skill   │  │ • deepseek    │        │
│  │ • switch_chat  │  │ • fewshot_   │  │ • dashscope   │        │
│  │ • list_chats   │  │   skill      │  │ • ollama      │        │
│  │ • detect_      │  │ • distance_  │  │ • (可扩展)    │        │
│  │   signals      │  │   skill      │  │               │        │
│  │ • retrieve_kb  │  │              │  │               │        │
│  │ • humanize     │  │              │  │               │        │
│  └────────┬───────┘  └──────────────┘  └──────────────┘        │
│           │                                                     │
├───────────┼─────────────────────────────────────────────────────┤
│           │                                                     │
│  ┌────────▼───────┐  ┌──────────────┐  ┌──────────────────┐    │
│  │  平台适配层     │  │  持久化层    │  │  配置与策略层     │    │
│  │  (Adapters)    │  │  (Store)     │  │  (Config/Policy) │    │
│  │                │  │              │  │                  │    │
│  │ • wechat_      │  │ • SQLite     │  │ • config.toml    │    │
│  │   wxauto       │  │   (threads/  │  │ • approval_      │    │
│  │ • (可扩展:     │  │    turns/    │  │   profiles       │    │
│  │   企微/Telegram)│  │    items/    │  │ • rate_limits    │    │
│  │                │  │    memory)   │  │ • send_windows   │    │
│  └────────────────┘  └──────────────┘  └──────────────────┘    │
└─────────────────────────────────────────────────────────────────┘
```

### 3.2 目录结构（重构后）

```
junshi-assistant/
├── junshi_harness/          # ← 核心：Agent 运行时（从 Codex Harness 理念提炼）
│   ├── __init__.py
│   ├── thread.py            # Thread 会话抽象：创建/恢复/fork/持久化
│   ├── turn.py              # Turn 单轮：状态机 + 流式 Item 发射
│   ├── item.py              # Item 定义：消息/推理/工具调用/审批/错误
│   ├── agent_loop.py        # Agent 循环核心：规划→工具调用→观察→输出
│   ├── context.py           # 上下文管理器：压缩/摘要/记忆窗口/retained reasoning
│   ├── tools.py             # 工具注册与路由（装饰器模式）
│   ├── approval.py          # 审批引擎：策略匹配 + 人工审批队列
│   ├── hooks.py             # 生命周期钩子：pre_turn/post_turn/on_tool/on_approval
│   ├── skills.py            # Skill 加载与注入
│   ├── event_bus.py         # 流式事件总线（替代现在的 BUS + log 字符串解析）
│   ├── store.py             # 持久化抽象（SQLite 实现）
│   ├── policy.py            # 执行策略：限流/时段/防误发/并发
│   └── errors.py            # 统一错误类型与重试策略
│
├── junshi_domain/           # ← 领域层：军师的业务逻辑（纯函数，无状态）
│   ├── __init__.py
│   ├── signals.py           # 信号检测（从 goutou/signals.py 迁移，纯函数）
│   ├── kb.py                # 知识库检索（从 goutou/kb.py 迁移）
│   ├── fewshot.py           # 范例召回（从 goutou/fewshot.py 迁移）
│   ├── style.py             # 风格档案管理（从 goutou/prompts.py + style_profile.py 合并）
│   ├── distance.py          # 异地分析（从 goutou/approval.py 拆分）
│   ├── humanize.py          # 去AI味（从 goutou/engine.py 拆分）
│   └── prompts.py           # Prompt 模板组装（纯函数，输入参数输出字符串）
│
├── junshi_tools/            # ← 工具层：Agent 可调用的工具实现
│   ├── __init__.py
│   ├── chat_tools.py        # read_messages / send_reply / switch_session / list_sessions
│   ├── analysis_tools.py    # detect_signals / retrieve_kb / analyze_distance / humanize
│   └── memory_tools.py      # recall_memory / save_memory / update_relationship_notes
│
├── adapters/                # ← 平台适配层（保持现有，但接口标准化）
│   ├── base.py              # ChatAdapter 抽象基类（定义标准接口）
│   └── wechat_wxauto.py     # 微信实现（从现有重构，实现 base 接口）
│
├── providers/               # ← 模型提供方（从 engine.py 拆分）
│   ├── __init__.py
│   ├── base.py              # LLMProvider 抽象：chat/stream/structured_output
│   └── openai_compat.py     # OpenAI 兼容实现（含重试/流式/超时）
│
├── interfaces/              # ← 接入层
│   ├── web/                 # Web UI（从 web/ 迁移，只依赖 harness API，不 import main）
│   │   ├── app.py           # FastAPI：REST + WebSocket，调用 harness API
│   │   └── frontend/        # React 前端
│   └── cli.py               # CLI 入口（从 main.py 精简，只做参数解析 + 调用 harness）
│
├── skills/                  # ← 可加载技能（从 kb/ + data/style_profiles/ 重构）
│   ├── relationship_kb/     # 关系心理学知识库 Skill
│   ├── style_profiles/      # 风格档案 Skill（每对象一个）
│   └── fewshot_indexes/     # 范例索引 Skill
│
├── data/                    # ← 运行时数据
│   ├── junshi.db            # SQLite：threads/turns/items/memory
│   ├── config.toml          # 配置（从 config.json 升级）
│   └── logs/
│
├── tests/                   # ← 测试
│   ├── test_harness/        # harness 核心测试
│   ├── test_domain/         # 领域逻辑测试
│   └── test_tools/          # 工具测试
│
└── docs/
    └── REDESIGN.md          # 本文档
```

---

## 四、核心模块详细设计

### 4.1 Thread（会话）

**替代现在的什么**：`CURRENT_TARGET` 全局变量 + `State` 类 + `data/state.json`

```python
# junshi_harness/thread.py
@dataclass
class Thread:
    id: str                     # UUID，持久化
    target_name: str            # 回复对象（如 "宝宝（7.05）"）
    target_meta: dict           # 对象档案：城市/偏好/关系阶段
    created_at: datetime
    updated_at: datetime
    status: str                 # active / paused / archived
    memory: RelationshipMemory  # 关系记忆（压缩后的上下文）
    style_profile_id: str       # 关联的风格档案
    config_override: dict       # 该对象的配置覆盖（如审批策略、限流）

class ThreadManager:
    def create(target_name, **kwargs) -> Thread
    def get(thread_id) -> Thread
    def list(status=None) -> list[Thread]
    def pause(thread_id)
    def resume(thread_id)
    def fork(thread_id) -> Thread   # 分叉：用于"如果当时这么回会怎样"的模拟
```

**关键改进**：
- 一个 Thread = 一个对象，天然支持多对象并行监控
- Thread 有自己的配置覆盖，不同对象可以用不同模型/审批策略/限流
- `RelationshipMemory` 是结构化的关系记忆，不是原始消息堆

### 4.2 Turn（单轮交互）

**替代现在的什么**：`process_new_messages()` 函数（250 行的巨型函数）

```python
# junshi_harness/turn.py
class TurnStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"

@dataclass
class Turn:
    id: str
    thread_id: str
    trigger: dict               # 触发源：{type: "incoming_message", content: "...", meta: {...}}
    status: TurnStatus
    items: list[Item]           # 本轮产生的所有原子事件
    created_at: datetime
    completed_at: datetime | None
    error: str | None

class TurnExecutor:
    """Turn 状态机：接收触发 → 发射 Item → 调用工具 → 等待审批 → 完成"""
    
    async def execute(self, turn: Turn, context: TurnContext) -> Turn:
        # 1. pre_turn hooks（信号检测、知识检索、风格注入）
        # 2. Agent 循环：规划 → 工具调用 → 观察 → 生成回复
        # 3. 审批检查：命中策略 → 暂停等待人工
        # 4. post_turn hooks（人味化、发送前校验）
        # 5. 执行发送（或等待审批后发送）
        # 6. 更新记忆
```

**Turn 的 Item 流示例**（前端可以实时展示每一步）：

```
Item(type=her_message,       data={text: "我今天好累啊", ts: ...})
Item(type=signal_detected,   data={signals: ["sad", "coquetry"]})
Item(type=kb_retrieved,      data={files: ["为他人提供情绪价值..."], chars: 1200})
Item(type=style_loaded,      data={profile: "宝宝（7.05）", tone: "嘴硬心软"})
Item(type=llm_reasoning,     data={delta: "她在求关注，先心疼..."})  ← 流式
Item(type=variant_generated, data={variants: ["...", "...", "..."], best: 1})
Item(type=approval_check,    data={needs_approval: false, reason: "无花钱/见面承诺"})
Item(type=humanize_applied,  data={original: "...", humanized: "..."})
Item(type=message_sent,      data={text: "...", status: "ok"})
Item(type=memory_updated,    data={note: "她今天工作累，情绪低落"})
```

**这直接解决了"生成过程黑盒"的问题**——前端不再只能等最终结果，而是可以展示军师的"思考过程"。

### 4.3 Agent 循环（核心改进）

**现在的模式**（单轮、无工具）：
```
收到消息 → detect_signals() → retrieve_kb() → retrieve_fewshot() 
→ build_prompt() → LLM 一次调用 → clean_reply() → 审批检测 → 发送
```

**新模式**（Agent 循环、工具调用、多步推理）：
```
收到消息 → [Agent 循环开始]
  │
  ├─ 思考：分析她的消息 + 关系记忆 + 近期上下文
  ├─ 调用工具 detect_signals(text) → 得到信号
  ├─ 调用工具 retrieve_kb(signals) → 得到知识片段
  ├─ 调用工具 recall_memory(thread_id, query="她最近的情绪状态") → 得到记忆
  ├─ 思考：综合以上信息，决定回复策略
  ├─ （可选）调用工具 humanize(draft) → 人味化
  ├─ 生成最终回复
  └─ 输出回复
[Agent 循环结束]
→ 审批引擎检查 → 通过/拦截
→ 发送工具执行
→ 记忆更新
```

**为什么这更好**：
1. **Agent 可以自主决定调用哪些工具**，而不是硬编码的流水线。比如她问"你还记得我上周说的考试吗？"，Agent 会主动调用 `recall_memory` 而不是只看最近 20 条消息
2. **多步推理**：复杂场景（她连发多条、情绪转折、涉及之前的约定）可以多轮思考
3. **可扩展**：加新能力 = 加新工具，不需要改主循环
4. **可观测**：每一步都是 Item，前端可展示，日志可查询

### 4.4 上下文管理器（Context Compaction + Retained Reasoning）

**替代现在的什么**：`history_window=20` 硬编码 + `format_history()` 简单拼接

```python
# junshi_harness/context.py
@dataclass
class TurnContext:
    thread: Thread
    recent_messages: list[Message]      # 最近 N 条原始消息（滑动窗口）
    compressed_summary: str             # 早期对话的压缩摘要
    retained_reasoning: str             # Agent 跨轮保留的内部推理笔记
    relationship_memory: RelationshipMemory  # 结构化关系记忆

@dataclass
class RelationshipMemory:
    her_preferences: list[str]          # 她的喜好（从对话中提取）
    upcoming_events: list[dict]         # 即将到来的事件（考试/生日/约会）
    mood_trends: list[dict]             # 近期情绪趋势
    effective_replies: list[dict]       # 哪些回复有效（她积极回应的）
    inside_jokes: list[str]             # 只有你们懂的梗
    unresolved_topics: list[str]        # 没聊完的话题
    last_updated: datetime

class ContextManager:
    def build_context(thread, incoming_message) -> TurnContext
    def compact(thread) -> None         # 触发压缩：旧消息 → summary
    def update_memory(thread, turn) -> None  # 从完成的 Turn 中提取记忆更新
```

**压缩策略**（借鉴 Codex Harness 的 context compaction，实测 3 倍效果提升、6 倍 token 减少）：
- 最近 10 条消息：原文保留
- 10-50 条：LLM 压缩为摘要（"她最近在准备期末考试，压力大，经常说累"）
- 50 条以前：结构化记忆（偏好、事件、梗）
- Retained reasoning：Agent 自己写的"作战笔记"，每轮结束时更新

**这直接解决了"长对话中早期约定被挤出窗口"的问题。**

### 4.5 工具层（Tools）

**替代现在的什么**：硬编码的函数调用链

```python
# junshi_tools/chat_tools.py
from junshi_harness.tools import tool

@tool(
    name="read_messages",
    description="读取当前会话的最近消息历史",
    parameters={"limit": {"type": "integer", "description": "读取条数", "default": 20}}
)
async def read_messages(adapter, limit: int = 20) -> list[dict]:
    return adapter.get_all_messages(limit)

@tool(
    name="send_reply",
    description="发送回复到当前会话。发送前会自动校验锚定状态。",
    parameters={"text": {"type": "string", "description": "要发送的文本"}}
)
async def send_reply(adapter, text: str) -> dict:
    # 内部包含锚定校验 + 发送 + 重试
    ...

@tool(
    name="switch_session",
    description="切换到指定会话",
    parameters={"name": {"type": "string"}}
)
async def switch_session(adapter, name: str) -> bool:
    ...

# junshi_tools/analysis_tools.py
@tool(name="detect_signals", description="检测消息中的情绪信号")
async def detect_signals(text: str) -> list[str]: ...

@tool(name="retrieve_kb", description="根据信号检索关系心理学知识库")
async def retrieve_kb(signals: list[str]) -> str: ...

@tool(name="humanize", description="将文本改写为更自然的微信聊天语气")
async def humanize(text: str) -> str: ...

@tool(name="recall_memory", description="从关系记忆中检索相关信息")
async def recall_memory(thread_id: str, query: str) -> str: ...

@tool(name="save_memory", description="保存一条关系记忆")
async def save_memory(thread_id: str, key: str, value: str) -> None: ...
```

**工具的执行策略**（借鉴 Codex 的 execpolicy）：
- `read_messages` / `detect_signals` / `retrieve_kb` / `humanize` / `recall_memory`：**auto**（自动执行，无风险）
- `send_reply`：**conditional**（需通过审批引擎检查）
- `switch_session`：**manual**（切换会话有风险，需确认）
- `save_memory`：**auto**（但有频率限制，防止 Agent 乱写）

### 4.6 审批引擎（Approval）

**替代现在的什么**：`detect_needs_approval()` 关键词匹配 + `pending` JSON 数组

```python
# junshi_harness/approval.py
class ApprovalLevel(Enum):
    AUTO = "auto"          # 自动放行
    SUGGEST = "suggest"    # 建议但不阻塞（前端高亮提示）
    MANUAL = "manual"      # 必须人工确认

@dataclass
class ApprovalRule:
    id: str
    name: str
    match: Callable[[TurnContext, str], bool]  # 匹配函数
    level: ApprovalLevel
    reason_template: str
    priority: int

class ApprovalEngine:
    def __init__(self, rules: list[ApprovalRule]):
        self.rules = sorted(rules, key=lambda r: r.priority, reverse=True)
    
    def check(self, context: TurnContext, reply: str) -> ApprovalDecision:
        for rule in self.rules:
            if rule.match(context, reply):
                return ApprovalDecision(
                    level=rule.level,
                    rule_id=rule.id,
                    reason=rule.reason_template.format(...)
                )
        return ApprovalDecision(level=ApprovalLevel.AUTO, reason="无风险")

# 内置规则示例
APPROVAL_RULES = [
    ApprovalRule(
        id="money_promise",
        name="花钱承诺",
        match=lambda ctx, r: any(kw in r for kw in ["给你买", "请你吃", "转账", "发红包"]),
        level=ApprovalLevel.MANUAL,
        reason_template="回复涉及花钱承诺（{matched}），需人工确认",
        priority=100,
    ),
    ApprovalRule(
        id="meet_promise_long_distance",
        name="异地见面承诺",
        match=lambda ctx, r: ctx.thread.target_meta.get("distance") == "异地" 
                             and any(kw in r for kw in ["我去找你", "过来找你", "接你"]),
        level=ApprovalLevel.MANUAL,
        reason_template="异地状态下涉及见面承诺，需人工确认",
        priority=95,
    ),
    ApprovalRule(
        id="meet_promise_same_city",
        name="同城见面承诺",
        match=lambda ctx, r: any(kw in r for kw in ["我去找你", "见面", "接你"]),
        level=ApprovalLevel.SUGGEST,
        reason_template="同城见面邀约，建议确认",
        priority=90,
    ),
    ApprovalRule(
        id="night_send",
        name="深夜发送",
        match=lambda ctx, r: datetime.now().hour >= 23 or datetime.now().hour < 6,
        level=ApprovalLevel.SUGGEST,
        reason_template="深夜时段发送，建议确认是否合适",
        priority=50,
    ),
]
```

**审批队列**（替代 pending JSON）：
- 审批请求是 Turn 的一个状态（`WAITING_APPROVAL`），不是独立的数据结构
- 前端通过 WebSocket 收到 `approval_requested` Item，展示审批界面
- 人工批准/拒绝后，Turn 继续执行或终止
- 所有审批决策持久化到 SQLite，可回溯

### 4.7 事件总线（Event Bus）

**替代现在的什么**：`BUS` 类 + `log()` 字符串解析（`msg.startswith("收到她的消息")` 这种脆弱判断）

```python
# junshi_harness/event_bus.py
class EventBus:
    """类型安全的事件总线，替代字符串日志解析"""
    
    def publish(self, event: Item):
        for subscriber in self.subscribers:
            subscriber(event)
    
    def subscribe(self, event_type: str | None = None) -> Generator:
        # 支持按类型订阅，前端 WebSocket 只订阅需要的事件
        ...

# 前端收到的是结构化 JSON，不再需要解析日志字符串
# {"type": "her_message", "data": {"text": "...", "ts": "..."}}
# {"type": "variant_generated", "data": {"variants": [...], "best": 1}}
# {"type": "approval_requested", "data": {"rule": "money_promise", "reply": "..."}}
```

### 4.8 持久化层（Store）

**替代现在的什么**：`data/state.json`（一个 JSON 文件塞所有东西）

```sql
-- SQLite schema
CREATE TABLE threads (
    id TEXT PRIMARY KEY,
    target_name TEXT NOT NULL,
    target_meta TEXT,           -- JSON
    status TEXT DEFAULT 'active',
    style_profile_id TEXT,
    config_override TEXT,       -- JSON
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE turns (
    id TEXT PRIMARY KEY,
    thread_id TEXT REFERENCES threads(id),
    trigger TEXT,               -- JSON: 触发源
    status TEXT,
    error TEXT,
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

CREATE TABLE items (
    id TEXT PRIMARY KEY,
    turn_id TEXT REFERENCES turns(id),
    type TEXT NOT NULL,         -- her_message / signal_detected / variant_generated / ...
    data TEXT,                  -- JSON
    seq INTEGER,                -- 顺序
    created_at TIMESTAMP
);

CREATE TABLE memory (
    id TEXT PRIMARY KEY,
    thread_id TEXT REFERENCES threads(id),
    category TEXT,              -- preference / event / mood / joke / unresolved
    key TEXT,
    value TEXT,
    source_turn_id TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE TABLE approvals (
    id TEXT PRIMARY KEY,
    turn_id TEXT REFERENCES turns(id),
    rule_id TEXT,
    decision TEXT,              -- approved / rejected / pending
    decided_at TIMESTAMP,
    decided_by TEXT             -- human / auto
);
```

**好处**：
- 可以查询"和宝宝的所有历史回复"、"哪些审批被拒绝了"、"她最近的情绪趋势"
- 并发安全（SQLite 事务）
- 不再有 `(ts, msg)` 元组定位 pending 这种脆弱方式

### 4.9 模型提供方（Provider）

**替代现在的什么**：`call_openai_compatible()` 裸 urllib 函数

```python
# providers/base.py
class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages, **kwargs) -> str: ...
    
    @abstractmethod
    async def stream(self, messages, **kwargs) -> AsyncIterator[str]: ...
    
    @abstractmethod
    async def structured_output(self, messages, schema, **kwargs) -> dict: ...

# providers/openai_compat.py
class OpenAICompatProvider(LLMProvider):
    def __init__(self, base_url, api_key, model, **kwargs):
        self.client = AsyncOpenAI(base_url=base_url, api_key=api_key)  # 用官方 SDK
        self.model = model
    
    async def chat(self, messages, **kwargs):
        response = await self.client.chat.completions.create(
            model=self.model, messages=messages, **kwargs
        )
        return response.choices[0].message.content
    
    async def stream(self, messages, **kwargs):
        stream = await self.client.chat.completions.create(
            model=self.model, messages=messages, stream=True, **kwargs
        )
        async for chunk in stream:
            if chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    
    async def structured_output(self, messages, schema, **kwargs):
        # 用 response_format={ "type": "json_object" } 或 function calling
        ...
```

**改进**：
- 用 `openai` 官方 SDK（异步），替代手写 urllib
- 原生支持流式输出 → 前端可以展示打字机效果
- 原生支持结构化输出 → `generate_variants` 不再需要正则解析 JSON
- 内置重试（`tenacity` 或 SDK 自带）
- 支持多 provider fallback（主模型挂了自动切备用）

---

## 五、一次完整回复的新流程

```
她发消息 "我今天好累啊，不想吃饭了"
        │
        ▼
┌─────────────────────────────────────────────┐
│ 1. Adapter 层检测到新消息                    │
│    → 创建 Turn(status=PENDING)              │
│    → 发射 Item: her_message                 │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 2. ContextManager 构建上下文                 │
│    • 加载 Thread（宝宝）的关系记忆            │
│    • 最近 10 条消息原文                      │
│    • 压缩摘要 + retained reasoning           │
│    → 发射 Item: context_built               │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 3. pre_turn hooks 执行                      │
│    • detect_signals → ["sad", "coquetry"]   │
│    • retrieve_kb → 情绪价值回应指南片段      │
│    • load_style → 嘴硬心软风格档案           │
│    → 发射 Item: signal_detected             │
│    → 发射 Item: kb_retrieved                │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 4. Agent 循环（核心）                        │
│    LLM: "她在求关注，说不想吃饭是小作求留。   │
│          记忆里她最近加班多，累是常态。       │
│          应该先心疼，再用嘴硬方式哄。"        │
│    → 发射 Item: llm_reasoning (流式)        │
│                                                │
│    LLM 调用工具 humanize("先别饿坏了，        │
│          多少吃点，不然我心疼" )              │
│    → 发射 Item: tool_call (humanize)        │
│    → 发射 Item: tool_result                  │
│                                                │
│    LLM 输出最终回复: "别不吃饭啊，            │
│          饿坏了我找谁算账去"                   │
│    → 发射 Item: reply_generated             │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 5. 审批引擎检查                              │
│    money_promise: 未命中                     │
│    meet_promise: 未命中                      │
│    night_send: 未命中（现在 20:00）          │
│    → AUTO 通过                              │
│    → 发射 Item: approval_passed             │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 6. post_turn hooks                          │
│    • 锚定校验（确认当前会话是她）             │
│    • 频率限制检查                            │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 7. 执行发送                                  │
│    工具 send_reply → adapter.send()         │
│    → 发射 Item: message_sent                │
└──────────────────┬──────────────────────────┘
                   ▼
┌─────────────────────────────────────────────┐
│ 8. 记忆更新                                  │
│    ContextManager 从 Turn 中提取：           │
│    • mood_trends: 她今天累，情绪低落          │
│    • effective_reply: "别不吃饭啊..."        │
│      （等她下条消息验证是否有效）             │
│    → 发射 Item: memory_updated              │
│    → Turn status = COMPLETED                │
└─────────────────────────────────────────────┘
```

---

## 六、与现有代码的映射关系

| 现有文件/模块 | 去向 | 处理方式 |
|---|---|---|
| `main.py` (22KB) | `interfaces/cli.py` + `junshi_harness/` | 拆解：CLI 参数解析 → cli.py；轮询逻辑 → TurnExecutor；状态管理 → Thread/Store |
| `goutou/engine.py` | `providers/openai_compat.py` + `junshi_domain/prompts.py` | 拆分：LLM 调用 → provider；prompt 组装 → domain；编排逻辑 → harness |
| `goutou/signals.py` | `junshi_domain/signals.py` | 直接迁移（纯函数，无需改） |
| `goutou/kb.py` | `junshi_domain/kb.py` + `skills/relationship_kb/` | 检索逻辑 → domain；知识库数据 → skill |
| `goutou/fewshot.py` | `junshi_domain/fewshot.py` + `skills/fewshot_indexes/` | 同上 |
| `goutou/approval.py` | `junshi_harness/approval.py` + `junshi_domain/distance.py` | 审批逻辑升级为引擎；异地分析拆到 domain |
| `goutou/prompts.py` | `junshi_domain/prompts.py` + `junshi_domain/style.py` | 风格档案管理独立出来 |
| `goutou/config.py` | `junshi_harness/config.py`（升级为 TOML + 环境变量 + 线程级覆盖） | 重写，去掉全局单例 |
| `adapters/wechat_wxauto.py` | `adapters/wechat_wxauto.py` + `adapters/base.py` | 增加抽象基类，现有实现适配接口 |
| `web/app.py` (32KB) | `interfaces/web/app.py` | 重写：不再 import main，只调用 harness API |
| `style_profile.py` | `junshi_domain/style.py` + `junshi_tools/` | 提取逻辑 → domain；作为工具暴露给 Agent |
| `data/state.json` | `data/junshi.db` (SQLite) | 迁移脚本自动转换 |
| `config.json` | `data/config.toml` | 迁移脚本自动转换 |
| `kb/references/` | `skills/relationship_kb/` | 移动，作为 Skill 加载 |
| `data/style_profiles/` | `skills/style_profiles/` | 移动，作为 Skill 加载 |
| `data/fewshot/` | `skills/fewshot_indexes/` | 移动，作为 Skill 加载 |

---

## 七、迁移路线图（分四期，可渐进式）

### Phase 1：基础设施（1-2 周）—— 不改变功能，只换底座

**目标**：把现有功能跑在新 harness 上，用户感知不到变化，但架构已经是新的。

1. 搭建 `junshi_harness/` 骨架：Thread/Turn/Item/EventBus/Store
2. 实现 SQLite 持久化，写迁移脚本把 `state.json` 转成 `junshi.db`
3. 实现 `OpenAICompatProvider`（用 openai SDK，替代裸 urllib）
4. 把 `goutou/` 下的纯函数迁移到 `junshi_domain/`
5. 实现第一个 Turn 执行器：**硬编码流水线模式**（和现在逻辑完全一致，但走 Turn/Item 框架）
6. 重写 `interfaces/web/app.py`：调用 harness API，通过 EventBus 推送结构化事件
7. 前端适配新的事件格式（不再解析日志字符串）

**交付标准**：功能和 v0.5.3 完全一致，但代码结构是新的。可以 A/B 对比。

### Phase 2：Agent 化（2-3 周）—— 核心能力升级

**目标**：从硬编码流水线升级为真正的 Agent 循环。

1. 实现工具注册系统：把现有功能封装为 `@tool`
2. 实现 Agent 循环：LLM 可以自主调用工具
3. 实现上下文管理器：滑动窗口 + 压缩摘要
4. 实现审批引擎：规则化，替代关键词匹配
5. 实现钩子系统：pre_turn / post_turn
6. 前端升级：展示 Agent 思考过程（流式 Item）、审批界面

**交付标准**：Agent 可以自主调用工具，复杂场景处理能力提升。前端可以看到"军师在想什么"。

### Phase 3：记忆与多对象（2 周）—— 体验质变

**目标**：关系记忆 + 多对象并行。

1. 实现 `RelationshipMemory` 结构化记忆
2. 实现记忆提取：每轮 Turn 结束后自动更新记忆
3. 实现 `recall_memory` / `save_memory` 工具
4. 实现多 Thread 并行监控（每个对象一个 Thread，独立 Turn 队列）
5. 前端多对象管理界面：创建/切换/暂停对象
6. 配置覆盖：每个对象可以有独立的模型/审批/限流设置

**交付标准**：可以同时监控多个对象，军师能记住"她上周说过要考试"这种长期信息。

### Phase 4：高级特性（持续迭代）

- **Thread fork**：模拟"如果当时这么回会怎样"，不实际发送
- **Skill 市场**：风格档案/知识库可以分享导入
- **效果反馈**：她的回复情绪 → 自动标记哪些回复有效 → 优化 future 回复
- **定时任务**："每天晚上 10 点提醒她睡觉"（通过 cron + Turn 触发）
- **多平台**：企业微信/Telegram adapter（只需要实现 `ChatAdapter` 接口）
- **Codex Harness 集成**：如果需要，可以直接用 Codex SDK 的 app-server 作为 harness 后端，自己的代码只做 domain/tools/UI

---

## 八、关键设计决策说明

### 8.1 为什么不直接用 Codex Harness 的代码？

Codex Harness 是 Rust 核心（codex-rs）+ TypeScript SDK，你的项目是 Python。直接嵌入需要：
- 起一个 Rust 子进程（app-server），通过 JSON-RPC 通信
- Python 侧写 SDK 客户端
- 工具/审批/记忆都要通过协议暴露

**建议**：Phase 1-3 用 Python 实现 harness 理念（轻量、可控、和现有代码无缝），Phase 4 评估是否需要切换到真正的 Codex app-server。如果你的核心场景就是微信自动回复，Python 实现的 harness 完全够用，且维护成本低。

### 8.2 为什么用 SQLite 而不是继续用 JSON？

- 你的 `state.json` 已经在承担"数据库"的角色（pending 列表、去重指纹、限流计数）
- 多对象并行后，JSON 文件的并发写会成为瓶颈
- 需要查询历史（"上周三给她发了什么"），JSON 全量扫描不现实
- SQLite 是 Python 标准库，零依赖，单文件，和 JSON 一样"便携"

### 8.3 为什么审批要做成规则引擎而不是关键词匹配？

- 现在的关键词匹配误判率高（"我给你带了个口信"也命中"给你带"）
- 规则引擎可以结合上下文（异地时见面承诺更严格）
- 可以配置不同对象的审批策略（对老板严格，对兄弟宽松）
- 审批决策可追溯（存在 approvals 表）

### 8.4 为什么要 Agent 循环而不是固定流水线？

固定流水线的问题是**所有消息都走完全相同的步骤**，不管需不需要：
- 她发"嗯"（冷淡信号）→ 不需要检索知识库，但还是检索了
- 她问"你还记得我上周说的考试吗"→ 需要回忆，但流水线只看最近 20 条
- 她发"哈哈哈哈"→ 不需要生成 3 条候选，但还是生成了

Agent 循环让 LLM 自己决定"这一步需要做什么"，更灵活，也更省 token。

---

## 九、风险与注意事项

1. **微信 UI 自动化的脆弱性不变**：wxauto4 依赖微信客户端 UI 结构，微信更新可能 break。这是 adapter 层的问题，新架构下 adapter 隔离得更好，修复影响面更小。
2. **Agent 循环的 token 成本**：多步推理 + 工具调用会增加 token 消耗。可以通过设置 `max_tool_calls_per_turn`（如最多 3 次）和上下文压缩来控制。
3. **记忆提取的准确性**：LLM 从对话中提取记忆可能有误。建议初期只提取高置信度的信息，且允许用户在前端编辑/删除记忆。
4. **渐进式迁移的兼容性**：Phase 1 结束时必须保证新旧系统行为一致，建议写一套集成测试（用固定的聊天记录 fixture，对比输出）。
5. **配置迁移**：`config.json` → `config.toml` 需要写迁移脚本，且保留旧格式读取能力至少一个版本。

---

## 十、总结

| 维度 | 现在 (v0.5.3) | 重构后 (v1.0) |
|---|---|---|
| 核心抽象 | 全局变量 + 巨型函数 | Thread → Turn → Item |
| Agent 能力 | 单次 LLM 调用，固定流水线 | Agent 循环，工具调用，多步推理 |
| 上下文 | 最近 20 条原文 | 滑动窗口 + 压缩摘要 + 结构化记忆 |
| 审批 | 关键词匹配 + JSON pending | 规则引擎 + Turn 状态 + 可追溯 |
| 状态 | state.json 单文件 | SQLite，支持查询/并发/多对象 |
| 多对象 | 全局单例，不支持 | Thread 级隔离，天然支持并行 |
| 可观测性 | 日志字符串解析 | 结构化 Item 流，前端实时展示 |
| LLM 调用 | 裸 urllib，无流式 | 官方 SDK，流式/重试/结构化输出 |
| 扩展性 | 加功能 = 改 main.py | 加功能 = 加工具/加规则/加 Skill |
| 测试性 | 几乎无法单元测试 | 每层都是纯函数/接口，可测试 |

**一句话**：现在的架构是"一个轮询脚本加了个 Web 界面"，重构后是"一个有记忆、会思考、可审批、能扩展的 Agent 运行时，微信回复只是它的第一个应用场景"。
