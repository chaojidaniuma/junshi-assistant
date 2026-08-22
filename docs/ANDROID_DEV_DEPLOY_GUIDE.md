# 军师助手 Android 版 · 开发到部署上线全流程指南

> 面向小白：每一步都写清楚做什么、怎么做、遇到问题怎么办。全程可以让AI代写代码，你只负责复制粘贴和点按钮。

---

## 第一阶段：环境搭建（1天）

### 1.1 安装 Android Studio

**这是写安卓代码的工具，必须装。**

1. 打开官网：https://developer.android.com/studio
2. 点击 "Download Android Studio"（下载最新版，目前是 Hedgehog / Iguana 或更新）
3. 运行安装包，一路 Next，注意：
   - 安装路径不要有中文和空格（比如 `D:\Android\Android Studio`，不要装在 `C:\Program Files`）
   - 勾选 "Android Virtual Device"（模拟器，可选但建议装）
4. 安装完成后启动 Android Studio
5. 第一次启动会下载 SDK，等它下完（可能需要10-30分钟，看网速）
6. 弹出 "Welcome to Android Studio" 就说明装好了

**遇到问题**：
- 下载慢 → 百度搜 "Android Studio 国内镜像"，配置国内镜像源
- 安装失败 → 确认电脑有至少 8GB 内存、10GB 可用空间

### 1.2 配置 JDK

Android Studio 自带 JDK（叫 JBR），不需要单独装。确认一下：

1. Android Studio → File → Settings → Build, Execution, Deployment → Build Tools → Gradle
2. 看 "Gradle JDK" 选的是不是 "Embedded JDK"（版本 17 或更高）
3. 如果不是，选 Embedded JDK，点 Apply

### 1.3 安装手机驱动（可选，用真机调试时需要）

- 小米/红米：装 "小米手机助手"
- 华为/荣耀：装 "华为手机助手"
- OPPO/vivo：装对应品牌的手机助手
- 谷歌/三星：一般 Windows 自动识别

**也可以不用真机，用模拟器调试**（Android Studio 自带模拟器）。

### 1.4 注册开发者账号（上架时需要，可以先不弄）

| 商店 | 网址 | 费用 | 审核时间 |
|---|---|---|---|
| 小米应用商店 | https://dev.mi.com | 免费（需企业/个人认证） | 1-3天 |
| 华为应用市场 | https://developer.huawei.com | 免费 | 1-3天 |
| OPPO 开放平台 | https://open.oppomobile.com | 免费 | 1-3天 |
| vivo 开发者平台 | https://dev.vivo.com.cn | 免费 | 1-3天 |
| 应用宝（腾讯） | https://open.tencent.com | 免费 | 1-3天 |
| Google Play | https://play.google.com/console | $25 一次性 | 1-7天 |

**建议**：先上架小米和应用宝，用户量大，审核快。个人开发者需要实名认证（身份证+手机号）。

---

## 第二阶段：创建项目（半天）

### 2.1 新建项目

1. 打开 Android Studio → 点 "New Project"
2. 选 "Empty Activity"（不是 Empty Compose Activity，因为我们要手动配 Compose）
   - **或者**选 "Empty Activity" 里带 Compose 的模板（新版 Android Studio 有 "Empty Activity" with Compose）
3. 配置：
   - **Name**：`JunshiKeyboard`（应用名，上架时显示"军师助手"）
   - **Package name**：`com.junshi.keyboard`（这个很重要，上架后不能改！）
   - **Save location**：选一个没有中文和空格的路径，比如 `D:\Projects\junshi-keyboard`
   - **Language**：`Kotlin`
   - **Minimum SDK**：`API 26: Android 8.0 (Oreo)`
   - **Build configuration language**：`Kotlin DSL`
4. 点 Finish，等待 Gradle 同步（第一次会下载很多东西，等5-10分钟）

### 2.2 确认项目能跑

1. 等 Gradle 同步完（底部进度条消失）
2. 点顶部工具栏的绿色三角 ▶（Run 'app'）
3. 选一个模拟器（没有就点 Device Manager → Create Device → 选 Pixel 6 → 选系统镜像 → 完成）
4. 等模拟器启动，APP 安装并打开，显示 "Hello World" 就说明项目没问题

**遇到问题**：
- Gradle 同步失败 → 看底部 Build 窗口的报错，复制报错信息问AI
- 模拟器启动慢 → 第一次启动要2-5分钟，正常
- 报错 "SDK location not found" → File → Project Structure → SDK Location 选对路径

### 2.3 配置项目结构

按照需求文档 `docs/ANDROID_KEYBOARD_REQUIREMENTS.md` 第三章的目录树，创建所有包和空文件：

1. 在 `app/src/main/java/com/junshi/keyboard/` 下右键 → New → Package，依次创建：
   - `di`
   - `data.local.dao`
   - `data.local.entity`
   - `data.remote.dto.request`
   - `data.remote.dto.response`
   - `data.repository`
   - `domain.model`
   - `domain.usecase`
   - `keyboard.ui`
   - `ui.theme`
   - `ui.navigation`
   - `ui.screens.home`
   - `ui.screens.chat`
   - `ui.screens.style`
   - `ui.screens.history`
   - `ui.screens.settings`
   - `ui.screens.setup`
   - `ui.screens.login`
   - `ui.components`
   - `util`
   - `worker`

2. 每个包里先创建空的 Kotlin 文件（文件名和需求文档一致），比如：
   - `di/AppModule.kt`
   - `data/remote/JunshiApiService.kt`
   - `keyboard/JunshiImeService.kt`
   - 等等

**这一步可以让AI做**：把需求文档第三章的目录树发给AI，说"帮我生成所有空文件的创建脚本"。

---

## 第三阶段：开发（4-6周，按模块顺序来）

### 开发原则

- **一次只做一个模块**，做完一个测一个，不要同时写一堆
- **每个模块写完先编译通过**（点 Build → Make Project，不报错再写下一个）
- **善用AI**：把需求文档里对应模块的部分复制给AI，让它写代码
- **代码写完先跑起来看效果**，不要等全部写完再测

### 3.1 第一周：基础框架 + 网络层

#### Day 1-2：配置依赖

把以下依赖加到 `app/build.gradle.kts` 的 `dependencies` 里：

```kotlin
// Compose
implementation(platform("androidx.compose:compose-bom:2024.02.00"))
implementation("androidx.compose.ui:ui")
implementation("androidx.compose.ui:ui-graphics")
implementation("androidx.compose.ui:ui-tooling-preview")
implementation("androidx.compose.material3:material3")
debugImplementation("androidx.compose.ui:ui-tooling")

// 网络
implementation("com.squareup.retrofit2:retrofit:2.9.0")
implementation("com.squareup.retrofit2:converter-gson:2.9.0")
implementation("com.squareup.okhttp3:okhttp:4.12.0")
implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")

// 协程
implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

// Room
implementation("androidx.room:room-runtime:2.6.1")
kapt("androidx.room:room-compiler:2.6.1")
implementation("androidx.room:room-ktx:2.6.1")

// Hilt 依赖注入
implementation("com.google.dagger:hilt-android:2.50")
kapt("com.google.dagger:hilt-android-compiler:2.50")

// ViewModel
implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0")
implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.7.0")
implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")

// 导航
implementation("androidx.navigation:navigation-compose:2.7.7")

// DataStore（存设置和Token）
implementation("androidx.datastore:datastore-preferences:1.0.0")
```

还要在 `plugins` 里加：
```kotlin
id("com.google.devtools.ksp") // 或 kapt
id("com.google.dagger.hilt.android")
```

**这一步让AI做**：把上面的依赖发给AI，说"帮我配置 build.gradle.kts，用最新稳定版"。

#### Day 3-4：数据模型 + API 层

让AI写以下文件（把需求文档 4.5 节的 DTO 定义发给AI）：
1. `domain/model/` 下的所有数据类（Thread、Turn、Suggestion、StyleProfile、User、Settings）
2. `data/remote/dto/` 下的请求和响应 DTO
3. `data/remote/JunshiApiService.kt`（Retrofit 接口）
4. `data/remote/RetrofitClient.kt`（Retrofit 实例，带日志拦截器）

**写完后**：Build → Make Project，确认不报错。

#### Day 5：Repository 层 + UseCase 层

让AI写：
1. `data/repository/JunshiRepository.kt`（协调 API 和本地缓存）
2. `domain/usecase/GenerateSuggestionsUseCase.kt`
3. `domain/usecase/AuthUseCase.kt`

### 3.2 第二周：键盘服务（核心！）

这是最难也最重要的部分，花一整周做。

#### Day 1-2：键盘服务基础框架

让AI写（把需求文档 4.1 节发给AI）：
1. `keyboard/JunshiImeService.kt`（继承 InputMethodService，基础框架）
2. `res/xml/method.xml`（键盘元数据）
3. `AndroidManifest.xml` 里声明键盘服务（参考需求文档 4.1.5）
4. `keyboard/ui/KeyboardRootView.kt`（键盘根视图，先用简单的 LinearLayout）

**测试键盘是否启用**：
1. 运行APP到手机/模拟器
2. 手机设置 → 系统 → 语言和输入法 → 虚拟键盘 → 管理键盘 → 开启"军师助手键盘"
3. 打开微信，点输入框，下拉通知栏 → 更改键盘 → 选"军师助手键盘"
4. 能看到你的键盘（哪怕是空白的）就说明服务注册成功了

#### Day 3-4：建议横条 UI

让AI写：
1. `keyboard/ui/SuggestionBar.kt`（3个建议气泡的横向布局）
2. `keyboard/ui/CandidateChip.kt`（单个气泡，带文字、点击事件）
3. `keyboard/ui/KeyboardTopBar.kt`（顶栏：标题+刷新+设置+切换键盘）
4. 把这些组合到 `KeyboardRootView.kt`

**测试**：在键盘里写死3个假建议，看能不能显示，点了有没有反应。

#### Day 5：剪贴板监听 + 填入输入框

让AI写：
1. `keyboard/ClipboardMonitor.kt`（参考需求文档 4.2）
2. `keyboard/InputConnectionHelper.kt`（参考需求文档 4.3）
3. 在 `JunshiImeService` 里集成：
   - 键盘启动时开始监听剪贴板
   - 检测到新文本 → 调用API生成建议 → 更新建议横条
   - 点击建议气泡 → 调用 `commitText()` 填入输入框

**测试**：
1. 复制一段文字
2. 打开微信输入框，切换到军师键盘
3. 看键盘是否自动显示了建议（此时还是假数据，先测流程）
4. 点一个建议，看输入框里有没有出现文字

### 3.3 第三周：API 对接 + 主APP界面

#### Day 1-2：对接真实 API

1. 先确保云端 API 能访问（本地开发用 `http://10.0.2.2:8000`，这是模拟器访问电脑本地的地址）
2. 让AI把 `GenerateSuggestionsUseCase` 和 API 对接起来
3. 键盘里检测到剪贴板文本 → 调用真实 API → 显示真实建议
4. 加加载状态（`LoadingView.kt`）和错误处理（`ErrorView.kt`）

**测试**：复制"今天好累啊不想吃饭"，切到军师键盘，看能不能生成真实建议。

#### Day 3-5：主APP界面

让AI按顺序写：
1. `ui/screens/login/LoginScreen.kt`（手机号+验证码登录，先做假登录）
2. `ui/screens/setup/SetupScreen.kt`（首次引导：启用键盘）
3. `ui/screens/home/HomeScreen.kt`（首页：当前对象+快速操作+键盘状态）
4. `ui/screens/chat/ChatScreen.kt`（对话页：粘贴消息→生成→复制）
5. `ui/screens/settings/SettingsScreen.kt`（设置页）
6. `ui/navigation/AppNavigation.kt`（把这些页面串起来）

**每个页面写完都跑一下看效果**。

### 3.4 第四周：本地存储 + 历史记录

#### Day 1-2：Room 数据库

让AI写：
1. `data/local/entity/` 下的 Entity（参考需求文档 4.5.1）
2. `data/local/dao/` 下的 DAO
3. `data/local/AppDatabase.kt`
4. 在 Repository 里加入本地缓存逻辑

#### Day 3-4：历史记录页

让AI写：
1. `ui/screens/history/HistoryScreen.kt`（列表展示历史记录）
2. `ui/screens/history/HistoryViewModel.kt`
3. 每次生成建议后自动存到本地数据库

#### Day 5：风格管理页

让AI写：
1. `ui/screens/style/StyleScreen.kt`
2. `ui/screens/style/StyleViewModel.kt`
3. 粘贴聊天记录提取风格（调用云端API）

### 3.5 第五周：打磨 + 测试

- 深色模式适配
- 各种屏幕尺寸适配
- 错误场景测试（没网、API挂了、Token过期）
- 键盘在不同APP里的表现（微信、QQ、短信、备忘录）
- 内存泄漏检查（用 Android Studio 的 Profiler）
- 性能优化（键盘启动速度、建议生成速度）

### 3.6 第六周：准备上架

- 隐私政策页面（必须有！）
- 用户协议页面
- 应用图标（找设计师或用AI生成，需要各种尺寸）
- 应用截图（5张以上，展示核心功能）
- 应用描述（100字简介 + 详细描述）
- 关键词（恋爱助手、AI回复、键盘、聊天助手等）
- 测试完整流程，确保没有 crash

---

## 第四阶段：打包签名（半天）

### 4.1 生成签名密钥

APP 上架必须签名，这是你的应用身份，**密钥文件一定要备份好，丢了就再也更新不了这个APP了**。

1. Android Studio → Build → Generate Signed App Bundle / APK
2. 选 "APK"（先打APK测试，上架用 AAB）
3. 点 "Create new..."（创建新密钥）
4. 填写：
   - **Key store path**：选一个安全的位置，比如 `D:\Projects\junshi-keystore\junshi.jks`
   - **Password**：设一个密码，记下来！
   - **Alias**：`junshi`
   - **Validity (years)**：`25`
   - **First and Last Name**：你的名字
   - 其他可以不填
5. 点 OK → 记住密码 → Next
6. 选 "release" → 勾选 "V1 (Jar Signature)" 和 "V2 (Full APK Signature)"
7. 点 Finish
8. 生成的 APK 在 `app/release/app-release.apk`

**重要**：把 `junshi.jks` 文件和密码备份到至少两个地方（U盘+云盘），丢了这个APP就废了。

### 4.2 配置自动签名（可选，方便以后打包）

在 `app/build.gradle.kts` 里加：

```kotlin
android {
    signingConfigs {
        create("release") {
            storeFile = file("D:/Projects/junshi-keystore/junshi.jks")
            storePassword = "你的密码"
            keyAlias = "junshi"
            keyPassword = "你的密码"
        }
    }
    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
            isMinifyEnabled = true  // 开启混淆
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
}
```

**注意**：密码不要提交到 Git！可以放在 `local.properties` 里，然后从 build.gradle 读取。

### 4.3 生成 AAB（上架用）

现在应用商店推荐用 AAB 格式（Android App Bundle），比 APK 小。

1. Build → Generate Signed App Bundle / APK
2. 选 "Android App Bundle"
3. 用刚才的密钥签名
4. 生成的 AAB 在 `app/release/app-release.aab`

---

## 第五阶段：上架应用商店（1-2周审核）

### 5.1 通用准备材料

每个商店都需要这些，先准备好：

| 材料 | 说明 | 怎么弄 |
|---|---|---|
| 软件著作权 | 大部分国内商店需要 | 百度搜"软件著作权申请"，找代理约300-500元，2-4周下证 |
| 隐私政策 | 必须有网页版 | 用AI生成，挂到你的服务器或 GitHub Pages |
| 用户协议 | 必须有 | 同上 |
| 应用图标 | 512x512 PNG，圆角 | 用AI生成或找设计师 |
| 应用截图 | 至少5张，1080x1920 | 模拟器里截图，展示核心功能 |
| 应用简介 | 一句话描述 | "恋爱军师AI键盘，帮你想回复" |
| 详细描述 | 300-800字 | 介绍功能、使用方法 |
| 关键词 | 5-10个 | 恋爱助手、AI回复、智能键盘、聊天助手 |
| 开发者实名认证 | 身份证+手机号+银行卡 | 各商店后台提交 |

### 5.2 小米应用商店上架流程

1. 打开 https://dev.mi.com → 注册开发者 → 实名认证（个人/企业）
2. 管理中心 → 应用分发 → 创建应用 → 填应用信息
3. 上传 AAB/APK
4. 填应用信息：名称、简介、描述、分类（选"社交"或"工具"）
5. 上传图标、截图
6. 填隐私政策URL、用户协议URL
7. 提交审核
8. 等1-3天，审核通过后自动上架

**审核注意**：
- 键盘类应用可能被要求说明为什么需要输入法权限
- 隐私政策要写清楚收集什么数据
- 不要提"微信自动回复"，要说"AI输入助手"、"智能回复建议"

### 5.3 应用宝（腾讯）上架流程

1. 打开 https://open.tencent.com → 注册 → 实名认证
2. 管理中心 → 创建应用 → 移动应用 → Android
3. 上传 APK
4. 填信息（同上）
5. 提交审核
6. 应用宝审核较快，通常1-2天

### 5.4 华为应用市场上架流程

1. 打开 https://developer.huawei.com → 注册 → 实名认证
2. AppGallery Connect → 我的应用 → 创建应用
3. 上传 APK/AAB
4. 填信息
5. 华为审核较严，可能需要软著
6. 提交后1-3天

### 5.5 OPPO / vivo 上架流程

和小米类似，各自的开发者平台注册、上传、填信息、提交审核。

### 5.6 Google Play 上架流程（可选，面向海外）

1. 打开 https://play.google.com/console → 注册开发者账号（$25一次性）
2. 创建应用 → 填信息
3. 上传 AAB
4. Google Play 审核最严，需要：
   - 数据安全表单（收集什么数据）
   - 内容评级
   - 目标受众
5. 审核1-7天
6. **注意**：键盘类应用在 Google Play 可以上架，但要说明 Full Access 的用途

### 5.7 被拒了怎么办

常见被拒原因和解决：

| 被拒原因 | 解决方法 |
|---|---|
| 隐私政策不完整 | 用AI重新生成更详细的隐私政策，包含数据收集、使用、存储、删除说明 |
| 功能描述不符 | 不要写"自动回复微信"，写"AI输入建议键盘" |
| 申请了不必要的权限 | 检查 AndroidManifest，删掉没用的权限 |
| 存在崩溃 | 用真机多测，特别是低端机 |
| 图标/截图不符合规范 | 按商店要求的尺寸重新做 |
| 需要软著 | 申请软件著作权（找代理） |

---

## 第六阶段：云端 API 部署（1-2天）

### 6.1 服务器选择

| 方案 | 价格 | 适合 |
|---|---|---|
| 阿里云轻量应用服务器 | 60-100元/月（2核2G） | 起步，用户少 |
| 腾讯云轻量服务器 | 60-100元/月 | 同上 |
| 阿里云函数计算 | 按调用量付费，免费额度大 | 流量不稳定时 |
| Railway / Render | 免费额度 + 付费 | 个人项目，不想运维 |

**建议起步用阿里云轻量服务器**，2核2G足够初期用。

### 6.2 部署步骤

1. 买服务器（选 Ubuntu 22.04）
2. 安装 Python 3.10+、pip、nginx
3. 把你的 Python 项目（junshi_harness + junshi_domain + providers）上传到服务器
4. 安装依赖：`pip install -r requirements.txt`
5. 安装 PostgreSQL（或先用 SQLite 起步）
6. 用 Uvicorn 启动 FastAPI：`uvicorn main:app --host 0.0.0.0 --port 8000`
7. 配置 Nginx 反向代理 + HTTPS（用 Let's Encrypt 免费证书）
8. 用 systemd 管理进程（开机自启、崩溃重启）

**这一步可以让AI写详细脚本**：把你的服务器信息和项目结构发给AI，说"帮我写一个部署脚本和nginx配置"。

### 6.3 域名和 HTTPS

- 买一个域名（阿里云/腾讯云，约50元/年）
- 备案（国内服务器必须备案，约1-2周）
- 用 Let's Encrypt 申请免费 HTTPS 证书
- APP 里的 Base URL 改成 `https://api.你的域名.com/`

### 6.4 云端核心改造

你现有的 Python 代码需要做以下改造（参考之前的架构方案）：

1. 把 `adapters/wechat_wxauto.py` 去掉（云端不连微信）
2. `TurnExecutor.execute()` 的 `send_fn` 传 `None`，只返回建议
3. 加用户认证（JWT Token）
4. SQLite 改 PostgreSQL
5. 加 API 限流（防止滥用）
6. 写 API 文档（用 FastAPI 自带的 Swagger）

**这部分你之前的架构方案里已经写了，让AI照着改就行。**

---

## 第七阶段：运营和迭代（持续）

### 7.1 上线后第一周

- 每天看崩溃报告（各商店后台都有）
- 收集用户反馈（应用商店评论、QQ群）
- 修复紧急 bug
- 观察哪些功能用户用得多

### 7.2 迭代节奏

- 小版本（bug修复）：随时发
- 中版本（新功能）：2-4周一个
- 大版本（架构升级）：2-3个月一个

### 7.3 变现（可选）

- 免费额度：每天10次生成
- 会员：无限生成 + 高级模型 + 多对象 + 风格深度分析，约15-30元/月
- 接入微信支付/支付宝（需要企业资质，个人可以用第三方支付代理）

---

## 附录A：常用AI指令模板

### 让AI写一个新模块

```
我在开发一个Android AI键盘应用，项目结构见附件。
请帮我实现 [模块名]，要求：
1. 使用 Kotlin + Jetpack Compose
2. 遵循 MVVM 架构
3. 用 Hilt 依赖注入
4. 用 Retrofit 做网络请求
5. 用 Room 做本地存储
6. 完整的错误处理
7. 代码加中文注释

模块需求：[粘贴需求文档里对应模块的部分]

请输出完整的文件内容，每个文件标明路径。
```

### 让AI修bug

```
我的Android项目报错了，错误信息如下：
[粘贴完整的报错信息，包括红色的全部内容]

相关代码：
[粘贴报错的那个文件的代码]

请帮我分析原因并给出修复后的完整代码。
```

### 让AI解释代码

```
请用小白能听懂的话解释下面这段Android代码在干什么：
[粘贴代码]
```

---

## 附录B：常见问题

### Q: 我完全不会编程，真的能做出来吗？
A: 能。你只需要会：复制粘贴、点按钮、把报错信息发给AI。所有代码都让AI写，你负责组装和测试。关键是一次只让AI做一个小模块，不要贪多。

### Q: 开发过程中最容易卡在哪？
A: ① Gradle 依赖版本冲突（让AI用最新稳定版）② 键盘服务注册不成功（检查 AndroidManifest 和 method.xml）③ 模拟器访问不了电脑本地API（用 10.0.2.2 而不是 localhost）

### Q: 上架被拒了怎么办？
A: 看被拒原因，90%是隐私政策和权限问题。把被拒原因发给AI，让它帮你改。改完重新提交，一般都能过。

### Q: 云端API不会部署怎么办？
A: 先用免费的 Railway（https://railway.app），把GitHub项目连上去，点几下就部署好了，不需要自己买服务器。等用户多了再搬阿里云。

### Q: 软著是什么？必须要吗？
A: 软件著作权，证明这个APP是你开发的。华为、OPPO等商店强制要求，小米和应用宝个人开发者可以不要但建议有。找代理300-500元，2-4周下证。

### Q: 键盘在微信里用不了怎么办？
A: 先确认：①设置里启用了军师键盘 ②微信输入框激活后切换到了军师键盘 ③键盘有显示（哪怕空白）。如果键盘显示但点了没反应，检查 InputConnectionHelper 的 commitText 方法。

---

## 时间线总览

| 阶段 | 时间 | 产出 |
|---|---|---|
| 环境搭建 | 1天 | Android Studio 能跑 Hello World |
| 创建项目 | 半天 | 项目骨架 + 空文件 |
| 开发 | 4-6周 | 可运行的APP |
| 打包签名 | 半天 | 签名APK/AAB |
| 云端部署 | 1-2天 | 线上API |
| 上架审核 | 1-2周 | 应用商店上架 |
| **合计** | **6-8周** | **上线的产品** |

**记住**：不要追求完美，先做一个能跑的 MVP 上架，再慢慢迭代。第一个版本只要能"复制消息→切键盘→看到建议→点一下填入"就够了。
