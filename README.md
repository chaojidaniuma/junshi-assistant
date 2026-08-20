# 军师助手 · Junshi Assistant

> 基于情绪价值主基调与知识库判断的 AI 回复助手：每个对象独立风格档案、多候选回复系统判最优、花钱/见面承诺人工确认、异地感知、桌面 GUI + 可打包 EXE。

## 功能

- **知识库驱动回复判断**：内置 [goutoujunshi](https://github.com/powerycy/goutoujunshi)（MIT）关系心理学知识库（`kb/`，43 篇），每次生成按信号检索相关知识片段注入 prompt
- **多候选回复**：一次生成 3 条不同风格回复，模型自评最优（⭐推荐）；确认模式可手动挑选
- **每个对象独立风格档案**：从 ChatLab 聊天数据提炼「你对 TA 的说话方式」，切换对象自动换风格
- **情绪价值主基调**：不引导花钱；涉及花钱/见面承诺的回复必须人工确认（任何模式都拦截）
- **异地感知**：配置城市优先；未配置时从聊天数据规则分析 + LLM 语境分析自动判断
- **三种模式**：dry 只生成 / 自动发送（系统推荐条）/ 确认后发送（弹窗手动选择）
- **发送可靠性**：自定义发送流程（Enter + 按钮兜底 + 重试）；失败自动恢复待确认可重发
- **防误发**：会话锚定 + 内容确认，绝不误发群聊
- **桌面 GUI**：单实例、鼠标保护、待确认面板、设置中心（LLM/知识库/城市可插拔）、使用说明

## 快速开始

```bash
pip install "git+https://github.com/zhengheng077/wxauto4.git"
cp config.example.json config.json   # 填写 API Key 与目标对象

python ui/gui.py          # 桌面版
python main.py --dry      # CLI 只生成
python main.py            # CLI 全自动
```

打包 EXE：`scripts\build.bat`（或手动）：

```bash
pip install pyinstaller
pyinstaller --noconfirm --onefile --windowed --name junshi-assistant \
  --collect-all wxauto4 --add-data "kb;kb" ui\gui.py
# 复制 config.json 与 data/ 到 exe 同级目录
```

## 架构

```
goutou/                核心引擎（平台无关）
├── signals.py         信号检测（离线规则）
├── kb.py              知识库检索（kb/ 目录，可替换，GOUTOU_KB_DIR 可指自定义）
├── approval.py        需确认检测 + 异地判断（安全边界）
├── prompts.py         system prompt 组装
├── config.py          配置管理（LLM 端点/Key/知识库/城市 可插拔）
└── engine.py          编排 + LLM 调用（OpenAI 兼容，可换任意服务）
adapters/              平台适配层（微信 wxauto4；同接口可换其他 IM）
ui/gui.py              tkinter 桌面 GUI
kb/                    关系心理学知识库（MIT，见 kb/KB-LICENSE）
main.py                CLI 入口
```

分层原则：**引擎不依赖平台，平台可替换，知识库可更换，LLM 可插拔**。

## 配置（config.example.json）

| 键 | 说明 |
|---|---|
| `target.name` | 回复对象（微信备注名） |
| `llm.base_url / api_key / model` | OpenAI 兼容端点（默认 DeepSeek；支持任意兼容服务） |
| `kb.dir` | 知识库目录（留空 = 内置） |
| `location.me / location.her` | 两人城市（异地判断最准，留空自动分析） |
| `monitor.*` | 轮询间隔 / 冷却 / 频率上限 |

API Key 优先级：`llm.api_key` > 环境变量 `DEEPSEEK_API_KEY` > `~/.dsh/.credentials.yaml`。

## 开源与合规

- 本仓库代码：MIT（LICENSE）
- 内置知识库：MIT，Copyright (c) 2026 powerycy（kb/KB-LICENSE，上游 [powerycy/goutoujunshi](https://github.com/powerycy/goutoujunshi)）
- 微信适配基于 wxauto4（UI 自动化，非注入非解密）：[zhengheng077/wxauto4](https://github.com/zhengheng077/wxauto4)
- **风险声明**：微信自动回复违反微信服务条款，存在封号风险；程序内置频率上限缓解；请仅用于合法合规的个人场景，商用前自行评估合规性

## 相关

- 知识库上游：[powerycy/goutoujunshi](https://github.com/powerycy/goutoujunshi)
- 微信适配：[zhengheng077/wxauto4](https://github.com/zhengheng077/wxauto4)
