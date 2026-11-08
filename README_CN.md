# SuperARIS

SuperARIS — Your personal research agent with ARIS, powered by a team of agents.

[English](README.md) · **v0.1.0 预览版** · [交互演示首页](https://wanshuiyin.github.io/SuperARIS/)

和主 Agent 讨论科研目标，让它组织工程、写作与独立审阅；查看实际成果，
随时人工接手，下次回到同一项目继续。

SuperARIS 用 [Herdr](https://herdr.dev) 承载可见、常驻的原生会话，用
[ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 提供科研技能与工作流。
主 Agent 负责方向、授权和验收；从一个 owner 开始，按任务需要增加协作者。
原有 MCP worker、异步作业和 fresh reviewer 继续沿用各自协议。

1. **讨论目标。** 选项目，告诉主 Agent 要研究或交付什么；不填任务就等待用户。
2. **组织工作。** 可用完整 pipeline、workflow 或单个 skill；工程、写作、核查各有独占写域，独立审阅保持 fresh。
3. **查看成果、人工接手。** 收件后读实际文件、检查与 reviewer 回复；完成状态提示验收，不替代验收。会话可见，人工输入默认由人工掌控。
4. **下次继续。** 重新打开项目，恢复原 owner 和现有记录，推进下一项已授权工作。

## 安装与启动

需要 **Python ≥3.10、macOS 或 Linux**、Herdr，以及选用的原生 CLI
（`codex`、`claude`、`agy`）。在原生工具里配置模型与登录；检测到 CLI
不代表已登录或模型可用。SuperARIS 向导不索取模型密钥。

用 [pipx](https://pipx.pypa.io) 从本仓库安装：

```bash
pipx install 'git+https://github.com/wanshuiyin/SuperARIS.git'
superaris
```

预览版尚未发布到 PyPI。本地构建的 wheel 也可安装：

```bash
python3 -m pip install --no-index --no-deps /path/to/superaris-0.1.0-py3-none-any.whl
python3 -m superaris
```

或在克隆目录的隔离环境安装：

```bash
git clone https://github.com/wanshuiyin/SuperARIS.git
cd SuperARIS
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/superaris
```

第一屏选 **简体中文 / English**，再选项目、客户端组合、各角色模型、布局与可选任务。
查看摘要后启动、返回修改或取消；确认启动前不创建新项目目录。从已绑定项目目录启动时，第一屏默认保存的界面语言（仍可调整），
随后优先恢复原工作台和 owner。
原生登录/信任提示由用户处理；Herdr 保持打开时，启动流程也能继续准备其余角色。

包内自带 project-agent 资源。确认启动或准备 `context` 需要 ARIS 时，才按固定公共提交
下载到 `$XDG_CACHE_HOME/superaris/aris/<commit>`，未设 XDG_CACHE_HOME 时使用
`~/.cache/superaris/aris/<commit>`。已绑定项目保留所选 `aris_repo` 供后续上下文准备；
help、plan、向导选择和取消不下载。已有 ARIS checkout 可明确指定：

```bash
SUPERARIS_ARIS_REPO=/path/to/aris superaris
```

来源版本、缓存与更新见[依赖说明](docs/DEPENDENCIES.md)。不要求全局安装 skills，
不改写用户模型或 MCP 配置。

## 选择团队

| 组合 | 可见角色 |
|---|---|
| Codex | Codex 项目 owner |
| CC + Codex | Claude Code owner 与 Codex 工程 |
| CC + Codex + AGY | 上述角色，再加 Antigravity 写作 |

角色、CLI harness 与实际模型分别判断；CC 沿用用户配置，不固定 DeepSeek 或 Claude 模型。
Gemini 可实质主写，Codex 定事实并核查；临时作者和独立 reviewer 保留原 MCP 通道。

```text
+-------------------+----------------------+
| main owner        | engineer / Codex     |
| 目标/集成         +----------------------+
|                   | writer / AGY         |
+-------------------+----------------------+
```

布局只用于新工作台，已有 owner 不改名、不重排；协作者按选择启用。

需要查看时，可用 `superaris receiver PROJECT --action status` 查询收件进程，
`superaris reconcile PROJECT` 检查已登记结果。`superaris context PROJECT --role ROLE --skill NAME`
只准备补充技能材料，不派发任务。日常使用仍可直接和主 Agent 对话；细节见下方文档。

## 预览范围

收件进程绑定单项目及原 main，detach 后继续；原 main 结束/变化、Herdr 服务不可用或明确停止时退出，
不做全天候重建。人工掌控的输入只发通知，CC/AGY 后续跟进保持 notice；专属 Codex 自动化
采用尽力输入检查，不保证与人工并发打字的原子隔离。

记忆沿用原项目记录及明确纠正、决定、交付等事件；没有跨项目个人中心、自动学习偏好、
永久模型记忆或第四讨论角色。界面语言不设定论文/任务语言，也不翻译原生客户端。
原任务的写域、fresh review、预算、暂停 Goal 与发布授权继续生效。

旧本地入口可能仍指向适配树。先在隔离环境试独立发行版；不要对同一活跃项目同时运行两版 receiver。

## 文档

- [工作台、角色与人工接手](docs/WORKBENCH.md)
- [技能、上下文与恢复](docs/PROJECT_CONTEXT.md)
- [收件与明确记忆事件](docs/RESULTS_AND_MEMORY.md)
- [ARIS 依赖与更新](docs/DEPENDENCIES.md)

来源归属和许可见 [LICENSE](LICENSE) 与 [NOTICE](NOTICE)。
