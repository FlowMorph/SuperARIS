# Visible SuperARIS layouts

New workbenches default to three responsibilities: `main`, `engineer` and
`writer`, with the same left-owner / right-stacked-collaborators layout.
Role, CLI harness and model remain distinct:

| Preset | main | engineer | writer |
|---|---|---|---|
| `codex` | Codex | Codex | Codex |
| `cc-codex` | Claude Code | Codex | Claude Code |
| `cc-codex-agy` | Claude Code | Codex | Antigravity |

Each role uses its selected native model. A Claude Code harness does not imply
a particular provider; a local DeepSeek configuration is not a product default.
Collaborators read their own ARIS context and wait for a scoped assignment;
they do not execute the main task in parallel by default. Give them distinct
assignments and exclusive write scopes as described in the launch reference.

For a newly created owner, the launcher creates workspace `SuperARIS <project>`
and tab `SuperARIS · Workbench` (new labels follow the UI language):

```text
Default: own SuperARIS workspace / SuperARIS · Workbench
+-------------------+----------------------+
| main              | engineer             |
| goal/integration  | implementation/checks|
|                   +----------------------+
|                   | writer               |
|                   | prose/explanation    |
+-------------------+----------------------+
```

Use explicit `--only-role` to select a smaller team, for example
`--preset cc-codex --only-role main --only-role engineer` for a compact pair,
or `--only-role main` for one owner. Existing teams and unfinished startup
selections retain their recorded membership on ordinary reentry; these new
defaults do not migrate them.

This automatic layout applies only to newly created workbench panes. It does
not rename or rearrange adopted owners. Fresh reviewers and temporary MCP
workers retain their original channels. On a narrow screen, move an owned
collaborator to a separate tab using official Herdr controls.

An adopted owner preserves its original labels and pane topology. The first new
collaborator receives a separate SuperARIS runtime workspace; later collaborators
use separate tabs there rather than splitting the existing human owner's pane:

```text
Existing user workspace                 Own new SuperARIS workspace
+------------------------+              +-------------------------+
| original owner/layout  |              | tab: engineer           |
| unchanged              |              | tab: writer (on demand) |
+------------------------+              +-------------------------+
```

For manual tab organization, inspect `herdr pane move --help` and use only real
IDs belonging to this project's own new workbench. The installed CLI supports:

```bash
herdr --session research-demo pane move PANE_IN_OWN_WORKBENCH --new-tab --workspace OWN_WORKSPACE_ID --tab-label Engineering --no-focus
```

Replace both placeholders with verified IDs. `--tab TAB_ID` targets an existing
tab; `--target-pane ID --split right` or `--split down` places a pane beside a
verified target. Apply optional controls only when requested to your own new
workbench, never the user's existing workspaces, unrelated sessions or another
task's panes. These are command examples, not executed layout changes. No layout
configuration framework or batch script is required.
