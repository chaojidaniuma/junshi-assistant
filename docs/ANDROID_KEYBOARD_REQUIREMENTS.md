# 军师助手 · Android AI键盘版 项目需求文档

> 版本：v1.0
> 定位：恋爱军师 AI 键盘——在微信/任何输入框里，键盘上方显示军师建议，点一下自动填入，用户自己按发送。
> 目标用户：想让AI帮忙想回复但不想被发现用了AI的人。

---

## 一、产品概述

### 1.1 核心场景

```
用户在微信和她聊天
    ↓
她发了一条消息："今天好累啊，不想吃饭了"
    ↓
用户复制她的消息（或键盘自动检测剪贴板）
    ↓
用户激活微信输入框 → 切换到"军师键盘"
    ↓
键盘上方横条显示："检测到消息：今天好累啊，不想吃饭了"
    ↓
键盘显示 3 个建议气泡：
  ① "别不吃饭啊，饿坏了我找谁算账"  ⭐推荐
  ② "怎么了宝宝，跟我说说"
  ③ "欠着，见面请你吃好的"
    ↓
用户点一个建议 → 自动填入微信输入框
    ↓
用户自己按发送
```

### 1.2 为什么是键盘模式

- **可上架**：自定义键盘是 Android 官方标准 API（InputMethodService），所有应用商店认可
- **体验顺**：不用切出微信，在聊天界面里直接完成"看建议→选建议→填入"
- **不封号**：不自动发送，用户手动按发送，微信检测不到异常
- **全应用通用**：不止微信，QQ、短信、小红书评论、任何输入框都能用

### 1.3 与"建议APP模式"的区别

| 维度 | 纯APP模式 | AI键盘模式（本项目） |
|---|---|---|
| 使用位置 | 独立APP里 | 微信/QQ等输入框上方 |
| 操作步骤 | 复制→切APP→生成→复制→切回微信→粘贴 | 复制→切键盘→点建议→发送 |
| 是否需要切出微信 | 是 | 否 |
| 开发难度 | 低 | 中（需写 InputMethodService） |
| 上架风险 | 无 | 无（标准API） |

---

## 二、技术选型

### 2.1 开发框架

| 组件 | 选型 | 理由 |
|---|---|---|
| **主框架** | Kotlin + Jetpack Compose | Android 官方推荐，AI 生成代码质量高，资料多 |
| **键盘服务** | 原生 InputMethodService（Kotlin） | 键盘扩展必须用原生，Compose 不能直接跑在键盘里 |
| **键盘内 UI** | Compose（嵌入 InputMethodService） | 可以用 ComposeView 嵌入，键盘 UI 用 Compose 写 |
| **网络请求** | Retrofit + OkHttp + Kotlin Coroutines | 标准方案，AI 最熟悉 |
| **JSON 解析** | Kotlin Serialization 或 Gson | 选 Gson，AI 写起来更简单 |
| **本地存储** | Room（SQLite） | 存历史记录、风格档案缓存、设置 |
| **依赖注入** | Hilt | 标准方案 |
| **异步** | Kotlin Coroutines + Flow | 标准方案 |
| **最低 SDK** | API 26（Android 8.0） | 覆盖 95%+ 设备 |
| **目标 SDK** | API 34（Android 14） | 上架要求 |
| **构建工具** | Gradle（Kotlin DSL） | 标准 |

### 2.2 为什么不用 Flutter

- Flutter 不能直接写 Android 自定义键盘（InputMethodService）
- 键盘扩展必须用原生 Android 代码
- 既然键盘必须原生，整个项目用原生 Kotlin 反而更简单，不用处理 Flutter 和原生的桥接

---

## 三、项目结构

### 3.1 完整目录树

```
junshi-keyboard-android/
├── app/
│   ├── build.gradle.kts              # 模块构建配置
│   ├── proguard-rules.pro            # 混淆规则
│   └── src/
│       └── main/
│           ├── AndroidManifest.xml   # 清单文件（声明键盘服务、权限）
│           ├── java/com/junshi/keyboard/
│           │   ├── JunshiApp.kt                # Application 类
│           │   ├── di/                          # 依赖注入模块
│           │   │   ├── AppModule.kt             # 全局依赖提供
│           │   │   └── NetworkModule.kt         # 网络相关依赖
│           │   ├── data/                        # 数据层
│           │   │   ├── local/                   # 本地存储
│           │   │   │   ├── AppDatabase.kt       # Room 数据库
│           │   │   │   ├── dao/
│           │   │   │   │   ├── HistoryDao.kt    # 历史记录 DAO
│           │   │   │   │   ├── StyleDao.kt      # 风格档案 DAO
│           │   │   │   │   └── SettingsDao.kt   # 设置 DAO
│           │   │   │   └── entity/
│           │   │   │       ├── HistoryEntity.kt # 历史记录表
│           │   │   │       ├── StyleEntity.kt   # 风格档案表
│           │   │   │       └── SettingsEntity.kt
│           │   │   ├── remote/                  # 远程 API
│           │   │   │   ├── JunshiApiService.kt  # API 接口定义（Retrofit）
│           │   │   │   ├── dto/                 # 数据传输对象
│           │   │   │   │   ├── request/
│           │   │   │   │   │   ├── GenerateRequest.kt
│           │   │   │   │   │   ├── FeedbackRequest.kt
│           │   │   │   │   │   └── AuthRequest.kt
│           │   │   │   │   └── response/
│           │   │   │   │       ├── GenerateResponse.kt
│           │   │   │   │       ├── ThreadResponse.kt
│           │   │   │   │       ├── StyleResponse.kt
│           │   │   │   │       └── ApiResponse.kt
│           │   │   │   └── RetrofitClient.kt    # Retrofit 实例
│           │   │   └── repository/              # 仓库层（协调本地+远程）
│           │   │       ├── JunshiRepository.kt  # 主仓库
│           │   │       ├── AuthRepository.kt    # 认证仓库
│           │   │       └── StyleRepository.kt   # 风格仓库
│           │   ├── domain/                      # 领域层（纯逻辑，无Android依赖）
│           │   │   ├── model/
│           │   │   │   ├── Thread.kt            # 关系会话
│           │   │   │   ├── Turn.kt              # 一轮回复
│           │   │   │   ├── Suggestion.kt        # 建议候选
│           │   │   │   ├── StyleProfile.kt      # 风格档案
│           │   │   │   ├── User.kt              # 用户
│           │   │   │   └── Settings.kt          # 设置
│           │   │   └── usecase/
│           │   │       ├── GenerateSuggestionsUseCase.kt   # 生成建议
│           │   │       ├── GetHistoryUseCase.kt           # 获取历史
│           │   │       ├── SaveFeedbackUseCase.kt         # 保存反馈
│           │   │       ├── ExtractStyleUseCase.kt         # 提取风格
│           │   │       └── AuthUseCase.kt                 # 登录注册
│           │   ├── keyboard/                    # 键盘服务（核心）
│           │   │   ├── JunshiImeService.kt      # 输入法服务（继承 InputMethodService）
│           │   │   ├── KeyboardController.kt    # 键盘逻辑控制
│           │   │   ├── ClipboardMonitor.kt      # 剪贴板监听
│           │   │   ├── InputConnectionHelper.kt # 输入框操作封装
│           │   │   └── ui/
│           │   │       ├── KeyboardRootView.kt  # 键盘根视图
│           │   │       ├── SuggestionBar.kt     # 建议横条（3个气泡）
│           │   │       ├── CandidateChip.kt     # 单个建议气泡
│           │   │       ├── LoadingView.kt       # 加载中动画
│           │   │       ├── ErrorView.kt         # 错误提示
│           │   │       ├── KeyboardTopBar.kt    # 键盘顶栏（标题+设置按钮）
│           │   │       └── NumericKeyboard.kt   # 数字键盘（备用）
│           │   ├── ui/                          # 主APP界面
│           │   │   ├── theme/
│           │   │   │   ├── Color.kt
│           │   │   │   ├── Theme.kt
│           │   │   │   └── Type.kt
│           │   │   ├── navigation/
│           │   │   │   └── AppNavigation.kt     # 导航图
│           │   │   ├── screens/
│           │   │   │   ├── home/
│           │   │   │   │   ├── HomeScreen.kt    # 首页
│           │   │   │   │   └── HomeViewModel.kt
│           │   │   │   ├── chat/
│           │   │   │   │   ├── ChatScreen.kt    # 军师对话页（粘贴生成）
│           │   │   │   │   └── ChatViewModel.kt
│           │   │   │   ├── style/
│           │   │   │   │   ├── StyleScreen.kt   # 风格管理
│           │   │   │   │   └── StyleViewModel.kt
│           │   │   │   ├── history/
│           │   │   │   │   ├── HistoryScreen.kt # 历史记录
│           │   │   │   │   └── HistoryViewModel.kt
│           │   │   │   ├── settings/
│           │   │   │   │   ├── SettingsScreen.kt
│           │   │   │   │   └── SettingsViewModel.kt
│           │   │   │   ├── setup/
│           │   │   │   │   ├── SetupScreen.kt   # 首次引导（启用键盘）
│           │   │   │   │   └── SetupViewModel.kt
│           │   │   │   └── login/
│           │   │   │       ├── LoginScreen.kt
│           │   │   │       └── LoginViewModel.kt
│           │   │   └── components/
│           │   │       ├── SuggestionCard.kt    # 建议卡片（APP内用）
│           │   │       ├── MessageBubble.kt     # 消息气泡
│           │   │       ├── SignalTag.kt         # 信号标签
│           │   │       └── CommonWidgets.kt     # 通用组件
│           │   ├── util/
│           │   │   ├── Constants.kt             # 常量
│           │   │   ├── Extensions.kt            # 扩展函数
│           │   │   ├── ClipboardUtil.kt         # 剪贴板工具
│           │   │   └── NetworkUtil.kt           # 网络状态
│           │   └── worker/
│           │       └── SyncWorker.kt            # 后台同步（可选）
│           └── res/
│               ├── values/
│               │   ├── strings.xml
│               │   ├── colors.xml
│               │   └── themes.xml
│               ├── drawable/
│               │   ├── ic_launcher_foreground.xml
│               │   ├── ic_keyboard.xml
│               │   ├── ic_copy.xml
│               │   ├── ic_settings.xml
│               │   └── ic_refresh.xml
│               ├── mipmap-*/                   # 应用图标
│               └── xml/
│                   ├── method.xml              # 键盘元数据（重要！）
│                   └── backup_rules.xml
├── gradle/
│   ├── libs.versions.toml                     # 版本目录（推荐）
│   └── wrapper/
├── build.gradle.kts                           # 根构建配置
├── settings.gradle.kts
├── gradle.properties
├── gradlew
├── gradlew.bat
└── README.md
```

### 3.2 分层架构说明

```
┌─────────────────────────────────────────┐
│  UI 层（Compose Screen + Keyboard View）│  ← 用户看到的界面
├─────────────────────────────────────────┤
│  ViewModel 层                           │  ← 界面逻辑、状态管理
├─────────────────────────────────────────┤
│  UseCase 层（domain/usecase）           │  ← 业务逻辑（生成建议、保存反馈）
├─────────────────────────────────────────┤
│  Repository 层（data/repository）       │  ← 协调本地缓存和远程API
├─────────────────────────────────────────┤
│  Data 层                                │
│  ├── Remote（Retrofit API）             │  ← 云端请求
│  └── Local（Room 数据库）               │  ← 本地缓存
└─────────────────────────────────────────┘
```

**依赖方向**：UI → ViewModel → UseCase → Repository → Data（单向依赖，好维护）

---

## 四、核心模块详细需求

### 4.1 键盘服务（JunshiImeService）—— 最核心

这是整个项目的灵魂，必须用原生 `InputMethodService`。

#### 4.1.1 功能清单

| 功能 | 说明 | 优先级 |
|---|---|---|
| 显示建议横条 | 键盘上方显示3个建议气泡，点击填入输入框 | P0 |
| 剪贴板自动检测 | 检测到剪贴板有新文本，自动生成建议 | P0 |
| 手动输入触发 | 用户在键盘输入框里打字，按"军师"按钮生成建议 | P0 |
| 加载状态 | 生成中显示加载动画 | P0 |
| 错误处理 | 网络失败/API错误显示错误提示+重试按钮 | P0 |
| 刷新建议 | 不满意可以点刷新重新生成 | P1 |
| 复制建议 | 长按建议气泡复制到剪贴板（不填入） | P1 |
| 切换键盘 | 键盘上有"切换输入法"按钮 | P0 |
| 设置入口 | 键盘顶栏有设置按钮，打开主APP设置页 | P1 |
| 数字/符号键盘 | 基础输入功能（不能只有建议，还要能打字） | P1 |
| 候选词历史 | 最近用过的建议快速访问 | P2 |

#### 4.1.2 键盘布局

```
┌─────────────────────────────────────────────┐
│ 🔍 军师助手        [刷新] [设置] [⌨切换]   │  ← KeyboardTopBar
├─────────────────────────────────────────────┤
│ 检测到：今天好累啊不想吃饭                    │  ← 检测到的消息（可编辑）
│                                             │
│ ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│ │别不吃饭啊│ │怎么了宝宝│ │欠着见面请│  ⭐    │  ← SuggestionBar（3个气泡）
│ │饿坏了我…│ │跟我说说 │ │你吃好的  │        │
│ └─────────┘ └─────────┘ └─────────┘        │
│                                             │
│ [重新生成]  [复制全部]                       │  ← 操作按钮
├─────────────────────────────────────────────┤
│  Q W E R T Y U I O P                        │
│   A S D F G H J K L                         │  ← 基础键盘（可选，或用系统键盘）
│    Z X C V B N M                            │
│  [123] [空格] [发送]                         │
└─────────────────────────────────────────────┘
```

#### 4.1.3 JunshiImeService 代码结构提示

```kotlin
// 这是给AI的代码结构提示，AI照着写
class JunshiImeService : InputMethodService() {
    
    private lateinit var keyboardRoot: KeyboardRootView
    private lateinit var controller: KeyboardController
    private lateinit var clipboardMonitor: ClipboardMonitor
    
    override fun onCreate() {
        super.onCreate()
        // 初始化依赖注入、控制器、剪贴板监听
    }
    
    override fun onCreateInputView(): View {
        // 创建键盘根视图，返回 ComposeView 或 自定义View
        // 这是键盘显示的入口
    }
    
    override fun onStartInputView(info: EditorInfo?, restarting: Boolean) {
        // 输入框激活时调用
        // 检查剪贴板有没有新文本 → 自动生成建议
    }
    
    override fun onFinishInput() {
        // 输入框失焦时调用
        // 清理状态
    }
    
    // 关键方法：把文本填入输入框
    private fun commitText(text: String) {
        currentInputConnection?.commitText(text, 1)
    }
}
```

#### 4.1.4 method.xml（键盘元数据，必须正确）

```xml
<?xml version="1.0" encoding="utf-8"?>
<input-method xmlns:android="http://schemas.android.com/apk/res/android"
    android:settingsActivity="com.junshi.keyboard.ui.settings.SettingsActivity"
    android:isDefault="false"
    android:supportsSwitchingToNextInputMethod="true">
    <subtype
        android:label="中文"
        android:imeSubtypeLocale="zh_CN"
        android:imeSubtypeMode="keyboard" />
</input-method>
```

#### 4.1.5 AndroidManifest.xml 键盘服务声明

```xml
<service
    android:name=".keyboard.JunshiImeService"
    android:label="军师助手键盘"
    android:permission="android.permission.BIND_INPUT_METHOD"
    android:exported="true">
    <intent-filter>
        <action android:name="android.view.InputMethod" />
    </intent-filter>
    <meta-data
        android:name="android.view.im"
        android:resource="@xml/method" />
</service>
```

### 4.2 剪贴板监听（ClipboardMonitor）

#### 功能
- 监听系统剪贴板变化
- 当用户复制了新文本，通知键盘服务
- 去重：同一段文本不重复生成
- 过滤：太短的文本（<2字）不触发，太长的文本（>500字）提示用户编辑

#### 代码结构提示

```kotlin
class ClipboardMonitor(context: Context) {
    private val clipboardManager = context.getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
    private val processedHashes = mutableSetOf<String>()
    
    fun start(listener: (String) -> Unit) {
        clipboardManager.addPrimaryClipChangedListener {
            val text = clipboardManager.primaryClip?.getItemAt(0)?.text?.toString()
            if (text != null && text.length in 2..500) {
                val hash = text.hashCode().toString()
                if (hash !in processedHashes) {
                    processedHashes.add(hash)
                    listener(text)
                }
            }
        }
    }
    
    fun stop() { /* 移除监听 */ }
}
```

### 4.3 输入框操作（InputConnectionHelper）

封装 `InputConnection` 操作，方便键盘调用。

```kotlin
class InputConnectionHelper(private val inputConnection: InputConnection?) {
    
    // 把文本填入输入框（替换选中内容或在光标处插入）
    fun commitText(text: String) {
        inputConnection?.commitText(text, 1)
    }
    
    // 先清空输入框再填入
    fun replaceAll(text: String) {
        inputConnection?.selectAll()
        inputConnection?.commitText(text, 1)
    }
    
    // 获取输入框当前内容
    fun getCurrentText(): String {
        return inputConnection?.getTextBeforeCursor(1000, 0)?.toString() ?: ""
    }
    
    // 发送（相当于按回车，部分APP支持）
    fun sendEnter() {
        inputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_ENTER))
        inputConnection?.sendKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_ENTER))
    }
}
```

### 4.4 主APP界面

#### 4.4.1 首页（HomeScreen）

- 显示当前选中的关系对象（"宝宝"）
- 快速操作：粘贴消息生成、查看历史、管理风格
- 键盘启用状态检测（没启用键盘时引导去设置）
- 今日回复统计

#### 4.4.2 军师对话页（ChatScreen）

- 输入框：粘贴或输入她的消息
- 生成按钮：调用API生成3条建议
- 建议卡片：每条带复制按钮、"用这条"按钮（填入剪贴板）
- 历史记录：显示之前的对话

#### 4.4.3 风格管理页（StyleScreen）

- 当前风格档案展示
- 从聊天记录提取风格（粘贴30条以上"我"发的消息）
- 手动编辑风格参数（语气、口头禅、关心方式）
- 风格档案切换（多对象）

#### 4.4.4 历史记录页（HistoryScreen）

- 按时间倒序显示所有生成记录
- 每条显示：她的消息 → 生成的3条建议 → 选了哪条
- 可筛选（按对象、按日期）
- 点击可查看详情

#### 4.4.5 设置页（SettingsScreen）

- 账号信息（登录/退出）
- API 配置（自定义云端地址，高级用户）
- 回复模式（自动填入/复制到剪贴板）
- 生成设置（候选数量、温度）
- 关于、隐私政策、用户协议

#### 4.4.6 首次引导页（SetupScreen）

第一次打开APP时显示，引导用户：
1. 登录/注册
2. 选择或创建关系对象
3. 启用军师键盘（跳转到系统输入法设置）
4. 完成，可以使用了

### 4.5 数据层

#### 4.5.1 Room 数据库表

**HistoryEntity（历史记录）**
```kotlin
@Entity(tableName = "history")
data class HistoryEntity(
    @PrimaryKey val id: String,           // UUID
    val threadId: String,                 // 关系会话ID
    val triggerText: String,              // 她的消息
    val suggestions: String,              // JSON: 3条建议
    val bestIndex: Int,                   // 推荐哪条
    val signals: String,                  // JSON: 检测到的信号
    val chosenIndex: Int?,                // 用户选了哪条
    val editedText: String?,              // 用户修改后的文本
    val createdAt: Long                   // 时间戳
)
```

**StyleEntity（风格档案）**
```kotlin
@Entity(tableName = "style_profiles")
data class StyleEntity(
    @PrimaryKey val id: String,
    val targetName: String,               // 对象名
    val profileJson: String,              // 风格数据JSON
    val updatedAt: Long
)
```

**SettingsEntity（设置）**
```kotlin
@Entity(tableName = "settings")
data class SettingsEntity(
    @PrimaryKey val key: String,
    val value: String
)
```

#### 4.5.2 API 接口（Retrofit）

```kotlin
interface JunshiApiService {
    
    // 生成建议
    @POST("api/v1/threads/{threadId}/turns")
    suspend fun generateSuggestions(
        @Path("threadId") threadId: String,
        @Body request: GenerateRequest
    ): GenerateResponse
    
    // 获取会话列表
    @GET("api/v1/threads")
    suspend fun getThreads(): ApiResponse<List<ThreadResponse>>
    
    // 创建会话
    @POST("api/v1/threads")
    suspend fun createThread(@Body request: CreateThreadRequest): ThreadResponse
    
    // 提交反馈
    @POST("api/v1/turns/{turnId}/feedback")
    suspend fun submitFeedback(
        @Path("turnId") turnId: String,
        @Body request: FeedbackRequest
    ): ApiResponse<Unit>
    
    // 提取风格
    @POST("api/v1/style-profiles/extract")
    suspend fun extractStyle(@Body request: ExtractStyleRequest): StyleResponse
    
    // 登录
    @POST("api/v1/auth/login")
    suspend fun login(@Body request: LoginRequest): AuthResponse
    
    // 注册
    @POST("api/v1/auth/register")
    suspend fun register(@Body request: RegisterRequest): AuthResponse
}
```

#### 4.5.3 DTO 定义

**GenerateRequest**
```kotlin
data class GenerateRequest(
    val text: String,              // 她的消息
    val history: List<MessageDTO> = emptyList(),  // 最近聊天历史（可选）
    val mode: String = "keyboard"  // keyboard / app
)
```

**GenerateResponse**
```kotlin
data class GenerateResponse(
    val turnId: String,
    val variants: List<String>,     // 3条建议
    val best: Int,                  // 推荐下标
    val signals: List<String>,      // 检测到的信号
    val needsApproval: Boolean,     // 是否涉及花钱/见面
    val approvalReason: String?
)
```

---

## 五、API 对接规范

### 5.1 基础配置

- **Base URL**：`https://api.junshi-assistant.com/`（开发时用 `http://10.0.2.2:8000/` 访问电脑本地）
- **认证方式**：Bearer Token（登录后获取，存在 SharedPreferences）
- **请求格式**：JSON
- **响应格式**：JSON

### 5.2 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": { ... }
}
```

- `code = 0` 表示成功
- `code != 0` 表示失败，`message` 是错误信息

### 5.3 错误码

| code | 含义 | 处理方式 |
|---|---|---|
| 0 | 成功 | 正常处理 |
| 401 | 未登录/Token过期 | 跳登录页 |
| 402 | 免费额度用完 | 引导付费 |
| 429 | 请求太频繁 | 提示稍后重试 |
| 500 | 服务器错误 | 提示重试 |

---

## 六、非功能需求

### 6.1 性能

- 键盘启动时间 < 500ms
- 建议生成到显示 < 3秒（取决于网络和LLM）
- 键盘内存占用 < 100MB
- APP冷启动 < 1秒

### 6.2 兼容性

- 最低 Android 8.0（API 26）
- 目标 Android 14（API 34）
- 适配主流分辨率（1080p / 2K / 折叠屏）
- 深色模式 / 浅色模式

### 6.3 隐私安全

- 聊天内容传输用 HTTPS
- 本地数据库加密（Room + SQLCipher，可选）
- 隐私政策明确说明数据用途
- 提供"清除所有数据"功能
- 不收集用户输入的完整聊天记录（只存生成的建议和她的消息用于历史回看）

### 6.4 权限

只申请必要权限：

```xml
<uses-permission android:name="android.permission.INTERNET" />
<uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
<!-- 键盘服务不需要额外权限，BIND_INPUT_METHOD 是系统权限 -->
```

**不需要**：无障碍、读取短信、读取通讯录、后台定位等敏感权限。

---

## 七、版本规划

### v1.0（MVP，4-6周）

- [ ] 键盘服务：显示建议、点击填入、剪贴板检测
- [ ] 主APP：登录、首页、对话页、设置页
- [ ] 云端API对接：生成建议、历史记录
- [ ] 首次引导：启用键盘
- [ ] 基础键盘：QWERTY布局（能正常打字）

### v1.1（2周）

- [ ] 风格管理：提取风格、手动编辑
- [ ] 历史记录页
- [ ] 多对象管理
- [ ] 刷新建议、复制建议

### v1.2（2周）

- [ ] 关系记忆展示
- [ ] 效果反馈（选了哪条/修改了什么）
- [ ] 深色模式优化
- [ ] 性能优化

### v2.0（持续）

- [ ] 付费会员系统
- [ ] 高级模型选择
- [ ] 社区风格分享
- [ ] iOS 版本

---

## 八、给AI的开发指令

当你让AI写代码时，用以下指令模板：

```
请基于以下需求文档，使用 Kotlin + Jetpack Compose 实现 [模块名]。
要求：
1. 严格遵循项目结构 docs/ANDROID_KEYBOARD_REQUIREMENTS.md 中的目录
2. 使用 Hilt 依赖注入
3. 使用 Retrofit + Coroutines 进行网络请求
4. 使用 Room 进行本地存储
5. 代码要有注释，关键逻辑写明原因
6. 错误处理要完善，不能 crash
7. 遵循 Material Design 3 设计规范

具体需求：[粘贴该模块的详细需求]
```

**关键提示**：每次只让AI写一个模块（如"先写键盘服务"），不要一次让它写整个项目，否则代码质量会下降。
