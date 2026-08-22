# 军师助手 · 多端上架架构方案

> 核心结论先说：**纯自动回复微信在任何官方应用商店都上不了架**。但"军师建议 + 一键复制/键盘填入"模式可以全平台上架，且开发成本最低。下面分平台详细说。

---

## 一、各平台技术可行性与上架难度

### 1.1 技术路线总览

| 技术路线 | 原理 | 安卓 (国内商店) | Google Play | iOS App Store | 鸿蒙 AppGallery |
|---|---|---|---|---|---|
| **无障碍服务自动回复** | AccessibilityService 监听微信界面 + 模拟点击发送 | ⚠️ 可能但高风险 | ❌ 绝对不行 | ❌ 无此API | ⚠️ 可能但高风险 |
| **ADB 控制手机** | 电脑通过 USB/WiFi ADB 截图+点击+输入 | ❌ 需电脑，非独立APP | ❌ | ❌ | ❌ |
| **AI 自定义键盘** | 键盘扩展在输入框上方提供建议，用户点选填入 | ✅ 可上架 | ✅ 可上架 | ✅ 可上架 | ✅ 可上架 |
| **军师建议 + 复制粘贴** | 用户粘贴她的消息 → APP生成建议 → 一键复制 | ✅ 可上架 | ✅ 可上架 | ✅ 可上架 | ✅ 可上架 |
| **通知栏快捷回复** | 监听微信通知 → 通知栏显示建议 → 点选回复 | ⚠️ 有限制 | ❌ | ❌ 限制极大 | ⚠️ |
| **Xposed/LSPosed Hook** | Root 后 hook 微信进程 | ❌ 需Root | ❌ | ❌ | ❌ |

### 1.2 为什么无障碍服务上不了架

- **Google Play**：2023 年起政策要求无障碍服务**只能用于帮助残障人士**，2023Q2 因滥用下架的应用同比激增 417%。Android 14 阻止侧载应用启用无障碍服务，Android 17（2026）在高级保护模式下完全封锁非辅助类应用的无障碍 API ["https://www.appsrethink.com/blog/android-accessibility-service-guide/","https://anonhaven.com/en/news/android-17-accessibility-api-restriction/"]
- **国内安卓商店**：华为/小米/OPPO/vivo 对无障碍服务也有专项审核，WorkTool 这类企业微信机器人能过是因为走企业场景 + 特殊备案，个人恋爱助手类大概率被拒
- **iOS**：根本没有跨应用无障碍服务 API，沙盒机制决定了不可能
- **鸿蒙 NEXT**：有 AccessibilityExtensionAbility，但审核政策与安卓类似，且不兼容安卓 APK，需用 ArkTS 重写

### 1.3 推荐路线：军师建议模式（全平台可上架）

```
她发消息 → 用户复制/分享到军师APP → 军师生成3条建议 → 用户选一条复制 → 粘贴发送
```

**这个模式的优势**：
- 所有应用商店 100% 可上架（不涉及跨应用自动化）
- 开发成本最低（一套 Flutter/React Native 搞定三端）
- 用户仍然省力（复制 → 选建议 → 复制 → 粘贴，4 步 vs 自己想回复）
- 没有封号风险（不是自动发送，是用户手动发的）
- 后续可以叠加 AI 键盘（在微信里直接点建议填入），体验进一步提升

---

## 二、整体架构：云端核心 + 多端薄客户端

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────────────┐
│                        客户端层（三端）                           │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │  Android APP │  │   iOS APP    │  │   鸿蒙 APP (ArkTS)   │   │
│  │  (Flutter)   │  │  (Flutter)   │  │   (原生 ArkUI)       │   │
│  │              │  │              │  │                      │   │
│  │ • 消息输入    │  │ • 消息输入    │  │ • 消息输入            │   │
│  │ • 建议展示    │  │ • 建议展示    │  │ • 建议展示            │   │
│  │ • 一键复制    │  │ • 一键复制    │  │ • 一键复制            │   │
│  │ • AI键盘扩展  │  │ • AI键盘扩展  │  │ • (鸿蒙输入法扩展)    │   │
│  │ • 风格管理    │  │ • 风格管理    │  │ • 风格管理            │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                      │               │
└─────────┼─────────────────┼──────────────────────┼───────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌──────────────────────────────────────────────────────────────────┐
│                     API 网关（HTTPS + WebSocket）                │
│              鉴权 / 限流 / 多端同步 / 推送通知                     │
└──────────────────────────────┬───────────────────────────────────┘
                               │
          ┌────────────────────┼────────────────────┐
          ▼                    ▼                    ▼
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│  军师核心引擎    │  │  用户数据服务    │  │  风格/知识库服务  │
│  (Python)       │  │  (PostgreSQL)   │  │  (对象存储)      │
│                 │  │                 │  │                 │
│ • Thread/Turn   │  │ • 用户账号      │  │ • 风格档案       │
│ • 信号检测       │  │ • 关系记忆      │  │ • 知识库版本     │
│ • 知识库检索     │  │ • 聊天历史      │  │ • fewshot索引    │
│ • 多候选生成     │  │ • 审批记录      │  │                 │
│ • 审批引擎       │  │ • 设备绑定      │  │                 │
│ • 上下文压缩     │  │                 │  │                 │
│ • LLM Provider  │  │                 │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

### 2.2 为什么用云端核心而不是端侧推理

| 维度 | 端侧推理（本地跑LLM） | 云端核心（API调用） |
|---|---|---|
| 模型质量 | 手机端只能跑 7B 以下模型，质量差 | 可以用 DeepSeek-V3 / Qwen-Max 等顶级模型 |
| 知识库 | 43篇知识库塞手机里占空间，检索慢 | 云端检索，毫秒级 |
| 多端同步 | 每端各自维护数据，无法同步 | 一套数据，手机/平板/电脑通用 |
| 风格档案 | 每端单独提取 | 一次提取，全端共用 |
| 开发成本 | 三端各实现一套引擎 | 一套 Python 核心，三端只做 UI |
| 离线可用 | 可以 | 不行（但恋爱回复不需要离线） |

**结论：云端核心 + 薄客户端是最优解。** 你现有的 Python harness 代码几乎可以直接搬到云端。

### 2.3 你现有代码的复用

```
你本地已有的（重构后）                    →  云端部署
─────────────────────                       ──────────
junshi_harness/  (Thread/Turn/Item/...)  →  核心引擎服务
junshi_domain/   (signals/kb/fewshot/...) →  核心引擎服务
providers/       (OpenAI兼容调用)          →  核心引擎服务
adapters/        (微信wxauto)             →  弃用（云端不连微信）
interfaces/web/  (FastAPI)                →  API 网关（改造）
data/junshi.db   (SQLite)                 →  迁移到 PostgreSQL
```

**改动量**：把 `adapters/wechat_wxauto.py` 的发送通道去掉，换成"返回建议给客户端"。其余 90% 的代码可以直接复用。

---

## 三、分平台详细设计

### 3.1 Android 端（Flutter + 国内商店 + Google Play）

#### 技术栈
- **框架**：Flutter（一套代码同时出 Android 和 iOS）
- **包名**：`com.junshi.assistant`
- **最低版本**：Android 8.0（API 26），覆盖 95%+ 设备

#### 核心功能模块

```
lib/
├── main.dart
├── api/                    # 云端 API 客户端
│   ├── junshi_api.dart     # 生成建议/审批/记忆同步
│   └── ws_client.dart      # WebSocket 实时推送
├── models/                 # 数据模型
│   ├── thread.dart         # 关系会话
│   ├── turn.dart           # 一轮回复
│   ├── suggestion.dart     # 建议候选
│   └── style_profile.dart  # 风格档案
├── screens/
│   ├── home_screen.dart    # 首页：最近会话 + 快速输入
│   ├── chat_screen.dart    # 军师对话页：粘贴消息→看建议
│   ├── style_screen.dart   # 风格档案管理
│   ├── memory_screen.dart  # 关系记忆查看/编辑
│   └── settings_screen.dart
├── widgets/
│   ├── suggestion_card.dart   # 建议卡片（3条候选+复制按钮）
│   ├── message_bubble.dart    # 消息气泡
│   └── signal_tag.dart        # 信号标签（sad/angry/coquetry）
├── services/
│   ├── share_handler.dart  # 接收微信分享的文本
│   ├── clipboard.dart      # 一键复制
│   └── keyboard_service.dart  # AI 键盘扩展（可选进阶）
└── utils/
```

#### 关键交互流程

**流程 A：粘贴模式（核心）**
```
1. 用户在微信里长按她的消息 → 复制
2. 下拉通知栏 → 点"军师助手"快捷入口（或直接打开APP）
3. APP 自动检测剪贴板 → 识别到她的消息 → 一键"生成建议"
4. 3条建议卡片展示，每条带"复制"按钮
5. 用户点复制 → 切回微信 → 长按输入框 → 粘贴 → 发送
```

**流程 B：分享模式（更顺）**
```
1. 用户在微信里长按她的消息 → 分享 → 选"军师助手"
2. APP 直接收到消息文本 → 自动生成建议
3. 选一条 → 点"复制并切回微信" → 自动跳转微信
```

**流程 C：AI 键盘模式（进阶，可选）**
```
1. 用户在微信输入框激活 → 切换到"军师键盘"
2. 键盘上方横条显示："检测到她的消息：好累啊不想吃了"
   （需要用户先复制她的消息，键盘读取剪贴板）
3. 键盘显示3个建议气泡 → 点一个 → 自动填入输入框
4. 用户自己按发送
```

#### 上架注意事项
- **国内商店（华为/小米/OPPO/vivo/应用宝）**：正常上架，隐私政策声明"读取剪贴板用于快速输入消息"，不需要无障碍权限
- **Google Play**：同样可上架，注意隐私政策要符合 GDPR
- **不需要任何敏感权限**：网络 + 剪贴板 + 通知（可选），这是最干净的权限组合

### 3.2 iOS 端（Flutter + App Store）

#### 技术栈
- **框架**：Flutter（与 Android 共用 90% 代码）
- **最低版本**：iOS 14.0
- **自定义键盘**：Swift 原生写 Keyboard Extension（Flutter 不支持键盘扩展，需少量原生代码）

#### 与 Android 的差异

| 功能 | Android | iOS | 原因 |
|---|---|---|---|
| 读取剪贴板 | ✅ 自动检测 | ⚠️ 需用户触发 | iOS 14+ 读取剪贴板会弹提示，不能静默读 |
| 分享扩展 | ✅ 标准分享 | ✅ Share Extension | iOS 需单独写 Share Extension |
| 通知栏快捷入口 | ✅ 自定义 | ✅ Widget | iOS 用小组件做快捷入口 |
| AI 键盘扩展 | ✅ 输入法API | ✅ Keyboard Extension | 都支持，但 iOS 键盘需 Full Access 才能联网 |
| 后台运行 | ⚠️ 有限制 | ❌ 严格限制 | iOS 不能后台监控微信 |

#### iOS 专属模块

```
ios/
├── Runner/
│   ├── AppDelegate.swift
│   ├── Info.plist
│   └── ...
├── ShareExtension/          # 分享扩展：从微信分享文本到军师
│   ├── ShareViewController.swift
│   └── Info.plist
├── JunshiKeyboard/          # 自定义键盘扩展
│   ├── KeyboardViewController.swift
│   ├── KeyboardView.swift
│   └── Info.plist
└── WidgetExtension/         # 锁屏/桌面小组件：快捷粘贴生成
    ├── JunshiWidget.swift
    └── Info.plist
```

#### iOS 上架注意事项
- **App Store 审核 4.0（设计）**：键盘扩展必须提供切换回系统键盘的按钮
- **审核 5.1（隐私）**：键盘扩展请求 Full Access 必须说明用途（"用于联网获取AI回复建议"）
- **审核 2.5（软件要求）**：不能有"自动发送"功能，必须用户手动点发送
- **分享扩展**：必须在 15 秒内完成处理，否则系统会杀掉

### 3.3 鸿蒙端（ArkTS + 华为应用市场）

#### 技术栈
- **框架**：ArkTS + ArkUI（鸿蒙 NEXT 不兼容安卓，必须原生开发）
- **API 版本**：HarmonyOS NEXT API 12+
- **复用**：UI 需重写，但调用同一套云端 API

#### 为什么鸿蒙不能用 Flutter

- HarmonyOS NEXT 是纯血鸿蒙，不再兼容 Android APK
- Flutter 目前不支持鸿蒙（2025 年有社区版，但不稳定）
- 鸿蒙有自己的输入法框架（InputMethodExtensionAbility）和分享能力

#### 核心模块

```
entry/src/main/ets/
├── entryability/
│   └── EntryAbility.ets
├── pages/
│   ├── Home.ets             # 首页
│   ├── Chat.ets             # 军师对话
│   ├── Style.ets            # 风格管理
│   └── Settings.ets         # 设置
├── components/
│   ├── SuggestionCard.ets   # 建议卡片
│   ├── MessageBubble.ets    # 消息气泡
│   └── SignalTag.ets        # 信号标签
├── services/
│   ├── JunshiApi.ets        # 云端 API 客户端
│   ├── Clipboard.ets        # 剪贴板
│   └── ShareHandler.ets     # 分享接收
├── model/
│   ├── Thread.ets
│   ├── Turn.ets
│   └── Suggestion.ets
└── common/
    └── constants.ets
```

#### 鸿蒙专属能力
- **元服务（原子化服务）**：可以做成免安装的元服务，用户从服务中心直接拉起，体验更轻
- **跨端流转**：手机上复制消息，平板上接着生成建议（分布式能力）
- **输入法扩展**：`InputMethodExtensionAbility`，类似安卓的自定义键盘

#### 鸿蒙上架注意事项
- 必须完成**应用核准（备案）**才能上架
- 隐私政策需在华为开发者后台备案
- 不允许热更新（eval / 动态加载代码）
- 无障碍服务同样受限，不要碰

### 3.4 三端功能对比

| 功能 | Android | iOS | 鸿蒙 |
|---|---|---|---|
| 粘贴消息生成建议 | ✅ | ✅ | ✅ |
| 分享消息到APP | ✅ | ✅ | ✅ |
| 一键复制建议 | ✅ | ✅ | ✅ |
| 自动读取剪贴板 | ✅ | ⚠️ 需触发 | ✅ |
| AI 键盘扩展 | ✅ | ✅ | ✅ |
| 通知栏快捷入口 | ✅ | ✅ Widget | ✅ |
| 后台自动监控微信 | ❌ 上架版不做 | ❌ | ❌ |
| 自动发送 | ❌ 上架版不做 | ❌ | ❌ |
| 关系记忆同步 | ✅ | ✅ | ✅ |
| 风格档案管理 | ✅ | ✅ | ✅ |
| 多对象管理 | ✅ | ✅ | ✅ |

---

## 四、云端核心设计

### 4.1 API 设计

```
POST   /api/v1/threads                  # 创建关系会话（对象）
GET    /api/v1/threads                  # 会话列表
GET    /api/v1/threads/{id}             # 会话详情
PATCH  /api/v1/threads/{id}             # 更新会话（城市/风格/配置）

POST   /api/v1/threads/{id}/turns       # 触发一轮回复（传入她的消息）
                                       # 返回：3条建议 + 信号 + 审批状态
GET    /api/v1/threads/{id}/turns       # 历史回复记录
GET    /api/v1/turns/{id}               # 单轮详情

POST   /api/v1/turns/{id}/feedback      # 用户反馈：选了哪条/修改了什么/效果如何
POST   /api/v1/turns/{id}/approve       # 审批通过（花钱/见面承诺类）
POST   /api/v1/turns/{id}/reject        # 审批拒绝

GET    /api/v1/threads/{id}/memory      # 关系记忆
PATCH  /api/v1/memory/{id}              # 编辑记忆
DELETE /api/v1/memory/{id}              # 删除记忆

GET    /api/v1/style-profiles           # 风格档案列表
POST   /api/v1/style-profiles/extract   # 从聊天记录提取风格（粘贴文本）
GET    /api/v1/style-profiles/{id}      # 档案详情
PUT    /api/v1/style-profiles/{id}      # 更新档案

POST   /api/v1/auth/register            # 注册
POST   /api/v1/auth/login               # 登录
POST   /api/v1/auth/device              # 设备绑定
```

### 4.2 核心引擎改造（从本地到云端）

你现有的 `TurnExecutor.execute()` 基本不用改，只需要把发送通道去掉：

```python
# 现在（本地版）
result = executor.execute(thread, text, history, distance=distance,
                          send_fn=self.adapter.send)  # ← 这个去掉

# 云端版
result = executor.execute(thread, text, history, distance=distance,
                          send_fn=None)  # ← 不发送，只返回建议
# result 里有 variants / best / signals / decision
# 通过 API 返回给客户端，由用户选择和发送
```

### 4.3 数据模型（PostgreSQL）

```sql
-- 用户
CREATE TABLE users (
    id UUID PRIMARY KEY,
    phone TEXT UNIQUE,           -- 手机号登录
    created_at TIMESTAMP,
    vip_expire_at TIMESTAMP      -- 付费会员到期时间
);

-- 设备（多端同步）
CREATE TABLE devices (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    platform TEXT,               -- android / ios / harmonyos
    device_name TEXT,
    last_active TIMESTAMP
);

-- 关系会话（对应你本地的 Thread）
CREATE TABLE threads (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    target_name TEXT,            -- 对象名
    target_meta JSONB,           -- 城市/关系阶段/偏好
    style_profile_id UUID,
    config_override JSONB,       -- 该对象的配置覆盖
    status TEXT DEFAULT 'active',
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- 一轮回复（对应你本地的 Turn）
CREATE TABLE turns (
    id UUID PRIMARY KEY,
    thread_id UUID REFERENCES threads(id),
    trigger_text TEXT,           -- 她的消息
    trigger_hash TEXT,           -- 去重哈希
    status TEXT,                 -- completed / waiting_approval / failed
    variants JSONB,              -- 3条建议
    best_index INT,
    signals TEXT[],              -- 检测到的信号
    decision JSONB,              -- 审批决策
    chosen_index INT,            -- 用户选了哪条
    edited_reply TEXT,           -- 用户修改后的文本
    feedback TEXT,               -- 效果反馈
    created_at TIMESTAMP,
    completed_at TIMESTAMP
);

-- 关系记忆
CREATE TABLE memory (
    id UUID PRIMARY KEY,
    thread_id UUID REFERENCES threads(id),
    category TEXT,               -- preference / event / mood / joke / unresolved
    key TEXT,
    value TEXT,
    source_turn_id UUID,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

-- 风格档案
CREATE TABLE style_profiles (
    id UUID PRIMARY KEY,
    user_id UUID REFERENCES users(id),
    target_name TEXT,
    profile JSONB,               -- 风格数据（tone/catchphrases/...）
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### 4.4 部署方案

| 组件 | 推荐方案 | 成本估算 |
|---|---|---|
| API 服务 | FastAPI + Uvicorn，Docker 部署 | 阿里云/腾讯云 2核4G ≈ 60元/月 |
| 数据库 | PostgreSQL（云数据库或自建） | 云数据库 ≈ 50元/月，自建免费 |
| LLM 调用 | DeepSeek / 阿里百炼（按 token 计费） | 每用户每天约 0.1-0.3 元 |
| 对象存储 | 阿里云 OSS（存知识库/风格档案） | ≈ 5元/月 |
| 推送通知 | 个推 / 极光（可选） | ≈ 0-30元/月 |
| **合计** | | **≈ 120元/月起** |

---

## 五、开发优先级与路线图

### Phase 1：MVP（4-6 周）—— 先跑通一个端

**目标**：Android APP + 云端核心，核心功能可用。

1. **云端**（2周）：
   - 把现有 Python harness 部署为 API 服务
   - PostgreSQL 替代 SQLite
   - 用户注册/登录（手机号验证码）
   - 核心 API：创建会话 / 生成建议 / 历史记录

2. **Android APP**（2-3周）：
   - Flutter 项目搭建
   - 首页 + 军师对话页（粘贴消息 → 看建议 → 复制）
   - 风格档案管理页
   - 关系记忆页
   - 分享扩展（从微信分享文本到APP）

3. **联调测试**（1周）：
   - 端到端流程测试
   - 国内商店上架准备（隐私政策、软著）

**交付**：Android APP 上架应用宝/小米/华为，核心功能可用。

### Phase 2：iOS 端（3-4 周）

1. Flutter 代码复用，适配 iOS 差异
2. Share Extension（分享扩展）
3. Widget（锁屏快捷入口）
4. App Store 上架

### Phase 3：AI 键盘扩展（3-4 周）

1. Android 自定义键盘
2. iOS Keyboard Extension（Swift 原生）
3. 键盘内调用云端 API 显示建议
4. 点选建议自动填入输入框

### Phase 4：鸿蒙端（4-6 周）

1. ArkTS 原生开发（UI 需重写）
2. 调用同一套云端 API
3. 华为应用市场上架
4. 元服务版本（可选）

### Phase 5：增值功能（持续）

- **付费会员**：高级模型 / 无限建议 / 多对象 / 风格深度分析
- **效果反馈优化**：用户选了哪条、她回复的情绪如何 → 自动优化 future 建议
- **关系报告**：每周生成关系状态报告（她的情绪趋势、沟通建议）
- **社区分享**：风格档案分享、话术模板市场

---

## 六、关键决策建议

### 6.1 先做哪个端？

**强烈建议先做 Android**：
- Flutter 一套代码后续出 iOS，开发效率最高
- 国内安卓商店审核相对宽松，上架快
- 安卓用户是恋爱助手类 APP 的主力人群
- 可以先验证产品模式，再投入 iOS/鸿蒙

### 6.2 要不要做自动发送？

**上架版本绝对不要做自动发送。** 原因：
1. 所有商店都禁止跨应用自动化
2. 微信封号风险（自动发送是微信重点打击的）
3. 恋爱场景下，"她发现你用AI自动回复"的后果比"回复慢一点"严重得多

**可以做的折中**：
- "一键复制并切回微信"——用户点一下，APP 复制建议 + 自动打开微信，用户只需要粘贴+发送
- AI 键盘模式——在微信里点建议就填入输入框，用户按发送
- 这两种方式都让用户只需要 1-2 次操作，但所有商店都认可

### 6.3 本地版（电脑 wxauto）还要不要？

**要保留，但定位变成"高级用户的进阶模式"**：
- 普通用户用手机 APP（建议模式）
- 进阶用户可以用电脑版（全自动模式，需要自己承担风险）
- 电脑版的数据和手机版通过云端同步
- 电脑版不上架，走 GitHub 开源 + 官网下载

### 6.4 多端互通怎么做？

**核心是云端账号体系**：
- 用户注册账号后，所有数据（会话/记忆/风格/历史）存在云端
- 手机、平板、电脑登录同一账号，数据实时同步
- WebSocket 推送：手机上生成的建议，电脑上也能看到
- 设备管理：可以查看哪些设备登录了，远程下线

---

## 七、风险与应对

| 风险 | 概率 | 影响 | 应对 |
|---|---|---|---|
| 应用商店审核拒绝 | 中 | 高 | 严格不碰无障碍/自动发送，隐私政策完善，提前准备软著 |
| 微信更新导致分享/剪贴板失效 | 低 | 中 | 核心功能不依赖微信内部，只靠系统分享和剪贴板 |
| LLM 成本超预期 | 中 | 中 | 设置每日免费额度，超出引导付费；缓存常见问题建议 |
| 用户隐私顾虑（聊天内容上传云端） | 高 | 高 | 端到端加密说明、本地模式选项、明确隐私政策、可删除数据 |
| 鸿蒙开发成本超预期 | 中 | 中 | 鸿蒙放最后，先验证 Android/iOS 市场再投入 |
| 竞品抄袭 | 高 | 中 | 核心壁垒是知识库质量 + 风格提取算法 + 用户数据，快速迭代 |

---

## 八、总结

| 维度 | 方案 |
|---|---|
| **上架策略** | 军师建议模式（粘贴→生成→复制→发送），全平台可上架 |
| **技术架构** | 云端 Python 核心（复用现有代码）+ Flutter 双端 + ArkTS 鸿蒙端 |
| **开发顺序** | Android → iOS → AI键盘 → 鸿蒙 |
| **首版周期** | 4-6 周出 Android MVP |
| **月成本** | ≈ 120 元起（服务器+数据库+LLM） |
| **自动发送** | 上架版不做，电脑版保留为进阶模式 |
| **核心壁垒** | 关系心理学知识库 + 个性化风格提取 + 关系记忆系统 |

**一句话**：别想着在手机上做全自动微信回复，商店不让、微信封号、用户也怕。做"军师建议 + 一键复制"，既能上架、又安全、还让用户有掌控感——这才是恋爱军师该有的定位：**帮你想，不替你发。**
