# Visible SuperARIS layouts

`--preset` selects role/harness options. Only `main` starts by default; repeat
`--only-role` for the roles needed now. Role, CLI harness and model are distinct:
`main` can run the Claude Code (`claude`) harness with the user's configured
model; that does not prove the backend is a Claude model. A local DeepSeek
configuration is not a SuperARIS default. `writer` uses `agy` with the chosen
Gemini or other configured model.

For example, `--preset cc-codex --only-role main --only-role engineer` selects
a compact pair. `--preset cc-codex-agy --only-role main --only-role writer`
selects a writing pair; add `--only-role engineer` when fact checking is needed.
Use distinct assignments and exclusive write scopes from the launch reference.

For a newly created owner, the launcher creates workspace `SuperARIS <project>`
and tab `SuperARIS · Workbench`. A compact pair places the collaborator on the right;
a new three-role paper workbench places the engineer above the writer there:

```text
Compact: own SuperARIS workspace
+-------------------+----------------------+
| main              | engineer (optional)  |
| Codex or CC       | Codex harness        |
+-------------------+----------------------+

Paper: own SuperARIS workspace / SuperARIS · Workbench
+-------------------+----------------------+
| main: CC harness  | engineer: Codex       |
| goal/integration  | facts/compile         |
|                   +----------------------+
|                   | writer: AGY/Gemini    |
|                   | substantive drafting |
+-------------------+----------------------+
```

This automatic layout applies only to newly created workbench panes. It does
not rename or rearrange adopted owners. Roles still activate lazily; a preset
alone never opens every role. Fresh reviewers and temporary MCP workers retain
their original channels. On a narrow screen, move an owned collaborator to a
separate tab using official Herdr controls.

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
