# SuperARIS

SuperARIS — Your personal research agent with ARIS, powered by a team of agents.

[简体中文](README_CN.md) · **v0.1.0 preview** · [Interactive walkthrough](https://wanshuiyin.github.io/SuperARIS/)

Discuss a research goal with your main agent. Let it organize engineering,
writing and review, inspect the actual results, take over when you want, and
continue the same project next time.

SuperARIS brings [ARIS](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
research workflows into visible, persistent [Herdr](https://herdr.dev) sessions.
Your main agent retains the direction, authorization and acceptance criteria.
Start with one owner and add collaborators when the task needs them. Existing
MCP workers, asynchronous jobs and fresh reviewers keep their own execution paths.

1. **Discuss the goal.** Choose a project and tell the main agent what you want
   to investigate or produce. An empty task leaves the workbench waiting for you.
2. **Organize the work.** Run a complete ARIS pipeline, one workflow or an
   individual skill. Assign engineering, writing and checking to suitable roles
   with separate writing areas; preserve independent review.
3. **See results and take over.** Inspect files, checks and reviewer replies.
   Registered results reach the owner; a completion signal prompts verification.
   Native sessions stay visible and human input stays human-owned by default.
4. **Continue later.** Reopen the project, recover its original owner and current
   records, then continue the next authorized step.

## Install and open

Requires **Python ≥3.10 on macOS or Linux**, Herdr, and the native CLIs you choose
(`codex`, `claude`, `agy`). Configure model access/login in those native tools.
CLI detection does not verify login or model availability. No model credentials
are requested by the SuperARIS wizard.

Install from this Git repository with [pipx](https://pipx.pypa.io):

```bash
pipx install 'git+https://github.com/wanshuiyin/SuperARIS.git'
superaris
```

This preview is not published to PyPI. To install a locally built wheel instead:

```bash
python3 -m pip install --no-index --no-deps /path/to/superaris-0.1.0-py3-none-any.whl
python3 -m superaris
```

For a checkout installation in an isolated environment:

```bash
git clone https://github.com/wanshuiyin/SuperARIS.git
cd SuperARIS
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/superaris
```

The first screen offers **简体中文 / English**, followed by project, clients,
models per role, layout and an optional task. Review the summary and launch,
go back or cancel. New project directories are created only after confirmation.
From a bound project directory, the first screen defaults to its saved UI
language (still adjustable), then offers the original workbench and owner. Native
login or trust prompts remain for you to handle; startup can continue while Herdr is open.

The package bundles its own project-agent resources. When a confirmed launch or
`context` preparation needs ARIS, SuperARIS lazily acquires a fixed public ARIS
revision into `$XDG_CACHE_HOME/superaris/aris/<commit>` or
`~/.cache/superaris/aris/<commit>` when XDG_CACHE_HOME is unset. A bound project
retains its chosen `aris_repo` for future context preparation. Help, plans,
wizard choices and cancellation do not fetch it. To use an existing ARIS checkout explicitly:

```bash
SUPERARIS_ARIS_REPO=/path/to/aris superaris
```

See [dependencies and updates](docs/DEPENDENCIES.md) for the pin, cache and
source precedence. No global skills installation or model/MCP rewrite is needed.

## Choose your team

| Option | Visible roles |
|---|---|
| Codex | A Codex project owner |
| CC + Codex | Claude Code owner and Codex engineering |
| CC + Codex + AGY | Above, with an Antigravity writing role |

Roles, CLI harnesses and models are separate. Claude Code can use the user's
configured provider; no DeepSeek or Claude model is imposed. Gemini can do
substantive drafting while Codex establishes facts and checks the result.
Temporary workers and fresh reviewers can continue through the original MCPs.

```text
+-------------------+----------------------+
| main owner        | engineer / Codex     |
| goal/integration  +----------------------+
|                   | writer / AGY         |
+-------------------+----------------------+
```

This layout applies to newly created workbenches. Adopted owners retain their
existing labels and layout; collaborators activate only when selected.

For optional inspection, `superaris receiver PROJECT --action status` shows the
receiver and `superaris reconcile PROJECT` checks registered results.
`superaris context PROJECT --role ROLE --skill NAME` prepares additional skill
material; it does not dispatch work. Normal use can stay in conversation with
the main agent. See the guides below for details.

## Preview boundaries

The receiver follows registered results for one project and its original main
identity. Detaching Herdr leaves it active; the main ending/changing, server
unavailability or an explicit stop ends it. It does not recreate agents around
the clock. Human-owned inputs get notices; CC/AGY follow-up is notice-based.
Dedicated Codex automation has a best-effort input guard, not atomic protection
against concurrent human typing.

Memory uses original project records and explicit correction/decision/delivery
updates. This preview has no cross-project personal hub, automatic preference
learning, permanent model memory or fourth discussion role. UI language does
not set paper/task language or translate native clients. Project scope,
reviewer freshness, budgets, paused Goals and publication permissions remain
those of the original task.

A local legacy launcher may still point to a previous adaptation checkout.
Test the independent install in an isolated environment first; do not run two
receiver versions against the same active project.

## Guides

- [Workbench, roles and human handoff](docs/WORKBENCH.md)
- [Skills, context and recovery](docs/PROJECT_CONTEXT.md)
- [Registered results and explicit memory](docs/RESULTS_AND_MEMORY.md)
- [ARIS source, dependencies and updates](docs/DEPENDENCIES.md)

SuperARIS builds on ARIS and Herdr; see [LICENSE](LICENSE) and [NOTICE](NOTICE)
for licensing and attribution.
