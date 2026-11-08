# Launch the installed SuperARIS product

Use the installed `superaris` console command. With the same environment's
interpreter, `python -m superaris` is equivalent; replace the command prefix in
examples rather than putting a multiword shell command into an executable-path
variable. Do not locate the product under `$ARIS_REPO/tools/` or require
`~/.aris/repo`. Those legacy helper pointers are not product installation.

## Source and requirements

The runtime requires Python ≥3.10 on macOS, Linux or native Windows, Herdr
and the selected native CLIs. On Windows use Windows Terminal / PowerShell;
Herdr supplies ConPTY panes, and SuperARIS uses kernel file locks, raw NDJSON
named pipes and a detached receiver. Confirmed startup can install missing
Herdr with its official PowerShell installer. Chooser screens and cancellation
do not install dependencies or fetch ARIS. Use their own model/login configuration; detecting
an executable does not verify authentication or model access. No model probes,
credentials requests, global skills installation or model/MCP rewrites are needed.

The package bundles this project-agent resource. Other ARIS skills, catalogs,
shared references and helpers come from public MIT-licensed ARIS commit
`2901234ad2954cd2388ced8d3aed2ed9de42803a`, fetched lazily only when confirmed
startup or context preparation needs it. The cache is
`$XDG_CACHE_HOME/superaris/aris/<commit>`, falling back to
`~/.cache/superaris/aris/<commit>`. Help, plan and canceled chooser flows do not
fetch it. Use an explicit complete ARIS checkout with:

```bash
SUPERARIS_ARIS_REPO=/path/to/aris superaris
superaris start /path/to/project --aris-repo /path/to/aris --plan
```

In PowerShell, assign `$env:SUPERARIS_ARIS_REPO = "C:\Research Tools\aris"`
before running `superaris`, or pass `--aris-repo "C:\Research Tools\aris"`.
Quote paths containing spaces or CJK characters. Bash environment-assignment
syntax above is for Unix shells. Upstream skills may still need Bash, GPU,
SSH, LaTeX or other tools; inspect their requirements separately and use a
suitable host or WSL when needed. Product startup is not proof that every
ARIS helper is Windows-compatible.

A bound project's `aris_repo` retains the chosen source for later context.
Ambient `ARIS_REPO` is for canonical ARIS helpers, not product source discovery.
When executing such a helper, use the chosen checkout's host-correct resolver
and actual canonical helper root in that same invocation. Never replace the
product's own executable with an assumed ARIS `tools/aris` wrapper. Source
updates require an explicit checkout or a future product pin change.

## Start and resume

Run `superaris` (or `superaris start` without a project) in an interactive
terminal. First choose 简体中文 / English, then project, available client
combination, models per role, layout and optional task. Review the summary and
launch, edit or cancel. New directories are created only after confirmation;
new empty tasks wait for the user. EOF/noninteractive input does not auto-start.
UI language controls product text/new labels, not paper/task output or native
client UI. It saves on confirmation; existing bound labels are preserved.

A bound project first offers its original owner/session/models/roles/tasks.
Omitted explicit parameters preserve existing inputs; `--clear-recovery`
explicitly clears recovery. Native trust/login stays human-operated. Startup
can continue while Herdr stays open once the user clears a native wait. Keep
original owners, writing scopes and unknown delivery state; do not resend an
uncertain initial prompt. A changed owner requires explicit reconciliation.

Every new preset starts `main`, `engineer` and `writer`: `codex` maps all
three to Codex; `cc-codex` uses CC / Codex / CC; `cc-codex-agy` uses
CC / Codex / AGY. Role, harness and model are separate; CC does not imply a
particular provider. Collaborators read their own context and wait for main.
Ordinary reentry retains recorded or pending membership. Repeat `--only-role`
to explicitly select a subset, as in this two-role example:

```bash
superaris start /path/to/project --session research-demo --preset cc-codex --only-role main --only-role engineer --write-scope main=notes --write-scope engineer=outputs/engineer --role-task 'engineer=Analyze existing results into outputs/engineer' --task 'Coordinate the existing project task' --plan
```

Use `--skill NAME` repeatedly for pipeline/workflow/individual selections,
`--model ROLE=MODEL` for new-role requests and `--name TEXT` for new readable
workbench titles. Actual model identity comes from native results. Scopes are
ownership instructions, not an OS sandbox. Adopted owners retain their topology;
new-only layouts are described in [layouts.md](layouts.md).

## Context and continuity

```bash
superaris context /path/to/project --role main --skill research-pipeline
superaris context /path/to/project --role engineer --skill analyze-results
```

`context` adds skills to the binding's original source/task/recovery/scope and
catalog closure. Optional `--task` describes only that preparation. It sends no
input and leaves live binding, assignment, delivery and unknown state unchanged.
A file-only role can request preparation from its main owner. Read actual
selected `SKILL.md` resources before executing them, not catalog summaries alone.

Role-local role/navigation/recovery files and exact `skill_index` point to
host-correct material. `.aris/workbench/RECOVERY.md` points to original project
records and the binding; `context/ROLE/LATEST_PREPARED.md` locates preparation,
not delivery, active assignment or acceptance. Native project instruction
pointers retain user text (Codex AGENTS/override precedence, CC CLAUDE, AGY
GEMINI). Current sessions must explicitly reread them; no permanent model
memory is promised. Keep original owners, wiki/task records, pauses and budgets.

For registered results, explicit memory events and delivery resolution, read
[receipts.md](receipts.md); for cooperation read
[coordination.md](coordination.md). The receiver survives detach/no-attach while
bound to the original main; it stops on owner ending/changing, server loss or
explicit stop. No global restarter or replacement owner is created. Never run
legacy and independent receiver versions on the same active project.
