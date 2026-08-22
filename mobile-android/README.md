# 狗头助手 · Android AI 键盘

基于开源 [Replies_AI](https://github.com/Jayakrishnan-manoj/Replies_AI) 键盘改造，接入军师助手云端。

核心变化（相对原版）：
- **去无障碍服务**：原版靠无障碍服务读聊天消息（上架会被拒）。改成**剪贴板监听**——复制她的消息即可生成建议。
- **接军师云端**：不再直连 OpenAI，改为调用项目 `cloud/` 的 `/api/generate`（背后是信号检测 + 关系知识库 + 真人范例 + 风格 + 审批拦截）。
- **键盘面板**：顶部显示信号标签与审批提示，3 条候选点一下填入输入框。

## 使用流程（小白）

1. 手机安装 `狗头助手.apk`（Debug 版自测，或发布到蒲公英）
2. 设置 → 系统 → 输入法 → 启用「狗头助手」，设为默认
3. 微信里复制她的一句话 → 切到狗头助手键盘 → 点任一情绪按钮 / 军师按钮
4. 键盘顶部出 3 条建议，点一条直接填入

## 对接云端

默认连 AWS 测试服务器 `http://43.196.94.43:8000`（`Constants.BASE_URL`）。测试期允许 HTTP 明文（`network_security_config.xml`）。正式上线换 HTTPS 域名后改 `Constants.BASE_URL` 并移除明文配置。

## 构建

```bash
# 需要 Android Studio（JDK 17+ / AGP 8.5）
./gradlew assembleDebug
# 产物：app/build/outputs/apk/debug/app-debug.apk
```

或将 `dist/狗头助手.exe` 布局的本项目根目录下的 `cloud/` 部署到服务器后，改 `Constants.BASE_URL` 指向你的域名。

## 说明

- 键盘的 QWERTY 布局、按键重复、大小写、符号切换等沿用原版（`KeyboardService`）。
- 原版的情感按钮（Happy/Sad/Angry…）保留外观，点击全部触发「生成军师建议」。
- 风格档案 / 关系记忆 etc. 在云端 `cloud/` 维护（v1.1 接入记忆卡片）。
