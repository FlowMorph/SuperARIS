# Workbench and human handoff

Run `superaris` in an interactive terminal; `superaris start` without a project
opens the same wizard. Noninteractive input/EOF exits or displays usage without
starting a model. The wizard selects UI language, project, available clients,
models, layout and optional task before confirmation. A new empty task waits.
UI language changes product text and new readable labels, not paper/task
language, native client UI or skill bodies. It is saved on confirmed startup
in the existing project binding; cancellation does not save a new preference.

When run from a bound project, the initial language default uses that binding;
from elsewhere it defaults to Chinese, with an explicit first-screen choice.
Existing projects offer continuation of their original owner, session, models,
roles and tasks. Existing labels/layout stay intact. Startup continues while
Herdr is attached after you handle actual native login/trust prompts. It never
answers them for you or blindly resends an unknown initial task.

## Explicit commands

`start PROJECT --plan` previews without starting native processes. A preset
selects available roles; explicit commands start only `main` unless selected:

```bash
superaris start /path/to/project --session research-demo --preset cc-codex --only-role main --only-role engineer --write-scope main=notes --write-scope engineer=outputs/engineer --role-task 'engineer=Implement the assigned stage in outputs/engineer' --task 'Coordinate the existing project task' --plan
```

Use real existing project paths. Remove `--plan` when ready to launch. Repeat
`--skill NAME` for selected ARIS work; a workflow may bring its catalog-defined
children. `--model ROLE=MODEL` requests models only for new sessions. `--name`
sets a readable new-workbench title. Missing optional clients are unavailable,
not proof of a fully running team. Role scopes are instructions, not OS sandboxes.

For paper work, a CC owner can organize the goal, Codex can verify facts and
compile, and an AGY/Gemini role can draft substantively. Writing and fresh review
remain different responsibilities. No requirement routes every MCP job into a
pane. New three-role workbenches place the owner left, engineer upper right and
writer lower right; adopted owner topology is preserved.

## Input ownership

Human-owned roles receive visible notices by default. `start --automation-owned`
marks new dedicated roles only; it never elevates an adopted owner. Only the
verified Codex input surface supports automatic follow-up submission in this
preview. The guard is best effort; it is not atomic against concurrent typing.
CC/AGY follow-up remains notice-based.

```bash
superaris control /path/to/project --role main --mode human
# After clearing human drafts and dedicating the role to automation:
superaris control /path/to/project --role main --mode automation
```

An observed draft revokes automation until explicitly re-enabled. Actual readback
resolves uncertain delivery, without repeated prompts or automatic resend:

```bash
superaris resolve-delivery /path/to/project --role main --resolution received --evidence notes/RECEIPT.md
```

Use `--resolution not-delivered` only after inspection confirms non-delivery.
For an uncertain bridge signal use `--handle ID` instead of the role. The evidence
file must exist in the project. Submitted context remains pending until explicit
received evidence; delivery does not establish scientific acceptance.

On reconnect, omitted task/skills/recovery/scope preserve the original inputs;
`--clear-recovery` explicitly empties recovery inputs. Main identity changes
require an ownership decision, not automatic takeover. Do not run competing
launchers against the same project or submit an existing human draft.
