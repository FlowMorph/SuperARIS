# Registered results and explicit memory events

Use the installed product command as described in [launch.md](launch.md). All commands below target the
same existing project. `notes/WORK.md` and `notes/PROGRESS.md` illustrate its
existing task and memory records; use the real paths rather than creating a
second ledger. The original record is a preferred pointer, never parsed as a
task database. Transport handle IDs identify one waiting item, not a scientific
state machine.

## A complete receiving chain

New workbenches default to `main`, `engineer` and `writer`. The example below
explicitly selects an owner and one collaborator with distinct assignments and
disjoint write directories by repeating `--only-role`.
Without a `--role-task`, a collaborator reads context and waits for a scoped
assignment. `--write-scope` supplies an ownership instruction, not an OS sandbox.

```bash
superaris start /path/to/project --session research-demo --preset cc-codex --only-role main --only-role engineer --write-scope main=notes --write-scope engineer=outputs/engineer --skill analyze-results --task 'Coordinate the existing notes/WORK.md task and verify the result' --role-task 'engineer=Wait until the owner registers demo-check; analyze the existing results, write outputs/engineer/RESULT.md, then report through the registered handle' --no-attach

superaris watch /path/to/project --id demo-check --owner-role main --worker-role engineer --record notes/WORK.md --deliverable outputs/engineer/RESULT.md --watch-file notes/WORK.md --wait-for 'Result file and worker report' --query 'engineer role; outputs/engineer/RESULT.md; original worker continuation handle' --next 'Read the result, run the original acceptance check and update notes/WORK.md within its existing authority'

# The worker runs this after writing its actual output.
superaris report /path/to/project --id demo-check --outcome completed --message 'Result written to outputs/engineer/RESULT.md; inspect the file and original checks'

# Verify the project-bound receiver; it survives UI detach/no-attach.
superaris receiver /path/to/project --action status
```

Startup ensures a receiver subprocess bound to this project and its original
main identity, including with `--no-attach`. Detaching the UI or exiting the
launcher leaves that receiver active. It connects to real Herdr events and
reconciles registered files/reports without polling an idle model. It stops if
the expected main ends/changes, the Herdr server becomes unavailable, or the
owner explicitly stops it. It does not rebuild a server, follow a replacement
main, create panes or install a global permanent daemon.

```bash
superaris receiver /path/to/project --action status
superaris receiver /path/to/project --action stop
# Explicitly re-enable after stopping/disabling and verifying the owner:
superaris receiver /path/to/project --action start
```

`start --no-receiver` disables/stops receiving and persists that choice;
`receiver --action start` explicitly re-enables it. `listen` remains a bounded
foreground diagnostic; its single-receiver lock refuses a second listener when
the managed receiver is active. Native callbacks can supply the same receipts
where available. Receiving transport remains separate from original acceptance,
Goal Pulse and the human/automation handoff.
Before dispatching deferred work, re-read the original task and current files;
a stale cached prompt must not override changed ownership, authorization or
newer evidence. Unknown delivery still requires readback resolution, and a
human draft still revokes automation.

`--query` is a display-only pointer to the original worker/MCP query entry;
it is never shell-executed and defines no generic MCP job/status API. Keep the
original MCP job/thread protocol, session continuation and reviewer freshness.
`--deliverable` and `--watch-file` can be repeated. Their paths and `--record`
stay inside the selected project. A record must already exist. Omit
`--worker-role` for a result owned by an original external worker whose query
handle remains in the record.

`report` also supports `failed`, `blocked` and `reply`. Every report is a signal
with acceptance unevaluated. Inspect real files, command outcomes and completed
reviewer replies before acting. The default human-owned role receives a visible
notice; it does not automatically execute the next step. `--automation-owned`
is an explicit startup option for dedicated automation roles. The Codex delivery
surface check is a best-effort guard, not atomic protection against concurrent
human typing; keep humans out of dedicated automation panes. An uncertain or
human-owned input state remains notice-only. Do not count notification as an
executed follow-up or acceptance.

After disconnects or lost events, inspect the original handles/files and use:

```bash
superaris reconcile /path/to/project

# Only when the original evidence shows this wait has ended:
superaris acknowledge /path/to/project --id demo-check --evidence notes/WORK.md
```

`reconcile` performs one receiving pass; `acknowledge` closes only the transport
wait and points to an existing evidence file. Neither declares scientific PASS.
Keep the handle open while more evidence is expected. Do not blindly replay a
write or paid model call after an uncertain delivery.

## Hand off input and resolve uncertain delivery

```bash
# Persist an explicit input-ownership handoff for a verified role.
superaris control /path/to/project --role main --mode human
# Only after human drafts are absent and the role is dedicated to automation:
superaris control /path/to/project --role main --mode automation

# After actual readback, point to its existing evidence file:
superaris resolve-delivery /path/to/project --role main --resolution received --evidence notes/RECEIPT.md
# For an uncertain bridge delivery, use --handle demo-check instead of --role.
```

`start --automation-owned` applies only to new roles; it never elevates an
adopted owner. Observing a draft revokes automation. Clear/read back the input
and explicitly opt back in with `control` before automatic delivery can resume.
The surface guard is not atomic protection against concurrent typing.

A submitted context remains `pending_context` until an explicit `received`
resolution references actual readback evidence. For confirmed non-delivery use
`--resolution not-delivered`; inspect first, then choose the next authorized
operation. Unknown delivery does not trigger automatic resend or repeated
confirmation requests. Resolve the uncertainty from actual state. Receipt of a
context is separate from acceptance under the original scientific gate.

## Append an explicit event to existing memory

The authorized owner can write the existing source directly or use:

```bash
superaris remember /path/to/project --file notes/PROGRESS.md --kind delivery --scope 'existing results task' --source outputs/engineer/RESULT.md --text 'Verified result using the original check; next action is recorded in notes/WORK.md'
```

`remember` appends the supplied event to an existing authoritative project file;
it does not infer preferences, inspect evidence for truth or update a wiki graph
automatically. Kinds are `correction`, `decision`, `delivery`, `failure` and
`handoff`. Supply `--expected-mtime-ns` from the owner's most recent file read
when protecting against intervening edits; a mismatch requires rereading before
appending. Keep personal preferences, project facts and task status in their
existing domains. Neither receipts nor memory commands resume Goals, expand
budgets, publish or merge.
