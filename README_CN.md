[![SuperARIS — Your personal research agent with ARIS (Auto Research In Sleep), powered by a team of agents.](assets/superaris-banner.png)](https://wanshuiyin.github.io/SuperARIS/)

**SuperARIS — Your personal research agent with ARIS (Auto Research In Sleep, ~20k stars), powered by a team of agents.**

**你的个人科研 Agent，基于 ARIS，由一支常驻 Agent 团队协作推进。**

[![Homepage](https://img.shields.io/badge/Homepage-Live%20demo-0969da?style=flat)](https://wanshuiyin.github.io/SuperARIS/) [![Quick Start](https://img.shields.io/badge/Quick%20Start-Herdr%20%2B%20Orca-2da44e?style=flat)](#快速开始) [![使用文档](https://img.shields.io/badge/Guides-Docs-0d9488?style=flat)](#使用文档) [![Preview v0.1.0](https://img.shields.io/badge/Preview-v0.1.0-6e7781?style=flat)](pyproject.toml) [![English](https://img.shields.io/badge/Language-English-8250df?style=flat)](README.md)<br>[![Built on ARIS](https://img.shields.io/badge/Built%20on-ARIS-455299?style=flat)](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) [![Cite ARIS](https://img.shields.io/badge/Cite%20ARIS-BibTeX-556b52?style=flat)](#cite-aris) [![MIT License](https://img.shields.io/badge/License-MIT-555555?style=flat)](LICENSE) [![加入共享社区](https://img.shields.io/badge/Join%20Community-ARIS-07a65a?style=flat)](#community)

[![看看团队怎样推进研究 — 中文动图预览](assets/demo-zh.gif)](https://wanshuiyin.github.io/SuperARIS/media/demo-zh.mp4)

**[▶ 播放完整 1080p 中文演示 · 约21秒](https://wanshuiyin.github.io/SuperARIS/media/demo-zh.mp4)**

*动图预览，点击播放高清完整版。示例项目与数据。*

**Orca 多模型团队：**[主页交互版](https://wanshuiyin.github.io/SuperARIS/?host=orca&lang=zh#workbench) · [中文视频](https://wanshuiyin.github.io/SuperARIS/media/orca-multi-demo-zh.mp4) · [English video](https://wanshuiyin.github.io/SuperARIS/media/orca-multi-demo-en.mp4)。保留[单模型团队（3 个 Codex Agent）](https://wanshuiyin.github.io/SuperARIS/orca-demo/?team=codex&lang=zh)及其[中文](https://wanshuiyin.github.io/SuperARIS/media/orca-demo-zh.mp4)/[英文](https://wanshuiyin.github.io/SuperARIS/media/orca-demo-en.mp4)原视频。

## 快速开始

准备好 Python 3.10+、Git 和 [pipx](https://pipx.pypa.io/stable/installation/)，以及已配置模型访问的所选 Agent CLI（`codex`、`claude`、`agy`）。安装一次，再打开向导：

```bash
pipx install "git+https://github.com/wanshuiyin/SuperARIS.git"
superaris
```

依次选择语言、项目、工作台、团队和模型；已安装的 Herdr 或 Orca 会直接复用。

也可以进入新项目目录，明确选择一种工作台启动：

| 工作台 | 在当前项目启动 | 安装与使用指南 |
|---|---|---|
| **Herdr（默认）** | `superaris start . --host herdr` | [工作台与启动](docs/WORKBENCH.md) · [Windows](docs/WINDOWS.md) |
| **Orca（可选）** | `superaris start . --host orca` | [Orca 安装与使用](docs/ORCA.md) |

使用 Orca 前，先安装并打开[官方应用](https://www.onorca.dev/)；若 CLI 不可用，在 **Settings → General → Orca CLI** 注册命令。已有项目重入时保留原工作台与团队。[更多安装方式 ↓](#安装与启动)

和你的个人 Agent 讨论科研目标，让它组织团队、分配工作、核验成果，并跟进下一步。想深入讨论一个想法、共同修改一段正文，或亲自接手时，直接进入相应成员的会话。

SuperARIS 基于 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)（Auto Research In Sleep，约 2 万 GitHub stars），为每个角色提供所需的科研流程与项目上下文。团队围绕同一个项目持续协作，分工清楚，研究记录随项目保存，明天回来还能接着做。

## 一个个人 Agent，一支持续协作的团队

主 Agent 把握研究方向、组织分工并回收成果。Codex 可以实现实验与核查证据，Gemini 可以共同讨论立意、组织论证并主写论文正文。每个成员都有自己的常驻会话，你可以直接与它共创，让讨论接着已有上下文继续。

新团队统一有主 Agent、工程与写作三个角色：可选全部 Codex、Claude Code 主控/写作配 Codex 工程，或 Claude Code / Codex / Antigravity。每个角色仍可选择自己的模型；临时 MCP worker 和需要全新上下文的独立 reviewer 继续在后台协作。

## 每个成员都能使用 ARIS

各角色拿到自己的任务、工作范围、ARIS 导航和所需技能，在执行时读取相应流程。你可以让主 Agent 推进完整科研 pipeline，把一段 workflow 委派给协作者，也可以只调用一个 skill 处理眼前的问题。

| 你想做什么 | ARIS 入口 |
|---|---|
| 从研究方向推进到论文 | [research-pipeline](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/research-pipeline/SKILL.md) |
| 寻找、筛选并验证研究想法 | [idea-discovery](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/idea-discovery/SKILL.md) |
| 实现实验计划并收集结果 | [experiment-bridge](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/experiment-bridge/SKILL.md) |
| 迭代审阅、修订和复核 | [auto-review-loop](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/auto-review-loop/SKILL.md) |
| 将核验过的成果写成论文 | [paper-writing](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/skills/paper-writing/SKILL.md) |

这些流程使用你已配置的工具，并保留 ARIS 原有的审阅和验收要求。[技能与项目上下文 →](docs/PROJECT_CONTEXT.md)

## 主动跟进工作

项目运行期间，SuperARIS 跟踪已登记的任务、结果文件和交付报告。原主会话仍在运行时，关闭工作台窗口也不打断跟进。主 Agent 根据这些更新收回完成的工作、核对证据，再推进下一项已授权步骤。

人工掌控的会话通过通知收件；专门交给自动化的 Codex 会话可以自动接收后续提示。[收件与工作接续 →](docs/RESULTS_AND_MEMORY.md)

[![SuperARIS 主动协作机制：常驻团队与 MCP 交付，经 receiver 通知原主 Agent 验收与推进，并记录项目进度以供恢复。](assets/proactive-mechanism-zh.png)](assets/proactive-mechanism-zh.png)

*主动协作、验收与项目记录的接续机制。点击查看原图。*

## 长期项目记忆

目标、决定、纠正、结果和下一步，保存在项目原有的笔记与 research wiki 中。Agent 随工作更新这些记录，恢复时重新读回。研究上下文跨天、跨会话留在项目里，你也可以直接查看和修改这些文件。

原团队仍在运行时，重新打开即可继续对话；换一个新会话，也能从项目恢复入口接上已有工作。[上下文与恢复 →](docs/PROJECT_CONTEXT.md)

[![SuperARIS 项目记忆：今天的团队随工作更新项目文件，后续会话读回这些记录并核对当前任务与实际产物。](assets/project-memory-zh.png)](assets/project-memory-zh.png)

*项目文件承接跨天、跨会话的研究进度。点击查看原图。*

## 安装与启动

需要 Python 3.10+、macOS / Linux / Windows、[Herdr](https://herdr.dev)（默认）或[可选的 Orca Terminal v1 工作台](docs/ORCA.md)，以及配置好模型访问的所选原生 CLI（`codex`、`claude`、`agy`）。

```bash
pipx install 'git+https://github.com/wanshuiyin/SuperARIS.git'
superaris
```

选择界面语言、项目、团队和模型，确认后进入工作台。可以直接给主 Agent 一个任务，也可以先打开团队，再讨论要做什么。界面语言与论文、任务语言分别选择。

| 团队组合 | 主 Agent | 工程 | 写作 |
|---|---|---|---|
| Codex | Codex | Codex | Codex |
| Claude Code + Codex | Claude Code | Codex | Claude Code |
| Claude Code + Codex + Antigravity | Claude Code | Codex | Antigravity |

新工作台采用相同的三窗格布局；已有团队和待完成启动保持原选择，`--only-role` 可明确选择子集。

SuperARIS 在需要时获取固定版本的 ARIS 资源；已有 ARIS 源码和定制技能可按文档选择来源。[依赖与更新 →](docs/DEPENDENCIES.md)

<details>
<summary>其它安装方式与已有 ARIS 源码</summary>

安装本地 wheel（也适用于离线安装）：

```bash
python3 -m pip install --no-index --no-deps /path/to/superaris-0.1.0-py3-none-any.whl
python3 -m superaris
```

在独立环境中从源码安装：

```bash
git clone https://github.com/wanshuiyin/SuperARIS.git
cd SuperARIS
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/superaris
```

明确选择已有 ARIS 源码：

```bash
SUPERARIS_ARIS_REPO=/path/to/aris superaris
```

帮助、计划预览和向导取消不会获取 ARIS。固定版本、本地缓存与已有 receiver 的兼容说明见[依赖与来源](docs/DEPENDENCIES.md)。

</details>

## Windows

原生 Windows Terminal / PowerShell 路径需要 Python 3.10+ 与 Git：

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
# ensurepath 后重新打开终端。
pipx install "git+https://github.com/wanshuiyin/SuperARIS.git"
superaris
```

确认启动后，可通过官方 Windows 安装器补装缺失的 Herdr。原生 CLI 的登录与信任由你交互完成；本地 wheel 安装无需 Git。[Windows 安装、恢复与支持范围 →](docs/WINDOWS.md)

## 使用文档

- [可选本地用量检测](docs/USAGE.md)：`superaris usage PROJECT --by-role --json`

- [Windows 安装与支持范围](docs/WINDOWS.md)
- [工作台、角色与人工接手](docs/WORKBENCH.md)
- [技能、上下文与恢复](docs/PROJECT_CONTEXT.md)
- [主动跟进与项目记忆](docs/RESULTS_AND_MEMORY.md)
- [ARIS 来源、依赖与更新](docs/DEPENDENCIES.md)

<a id="community"></a>

## 社区

SuperARIS 与 [ARIS 科研社区](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/blob/main/README_CN.md#community)共用同一个微信交流群，交流 Agent 协作与 AI 科研工作流。下方二维码直接引用 ARIS 上游维护的原图。

<img src="https://raw.githubusercontent.com/wanshuiyin/Auto-claude-code-research-in-sleep/main/docs/wechat_group.jpg" alt="ARIS 共享科研交流群微信二维码" width="300">

## Cite ARIS

SuperARIS 基于 ARIS 的科研流程、审阅机制与项目知识积累。如果这些能力帮助了你的研究，请引用 [ARIS 技术报告](https://arxiv.org/abs/2605.03042)：

```bibtex
@article{yang2026aris,
  title={ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration},
  author={Yang, Ruofeng and Li, Yongcan and Li, Shuai},
  journal={arXiv preprint arXiv:2605.03042},
  year={2026}
}
```

感谢 [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep) 提供科研底座，[Herdr](https://herdr.dev) 提供常驻原生会话。SuperARIS 使用 [MIT 许可](LICENSE)，源码归属见 [NOTICE](NOTICE)。
