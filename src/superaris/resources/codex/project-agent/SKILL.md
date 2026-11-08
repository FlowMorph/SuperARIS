---
name: project-agent
description: Start or continue a Herdr-backed ARIS project agent with existing project memory, bounded role delegation and evidence-based follow-up. Use for a persistent project owner or Herdr workbench; ordinary one-off skills remain directly usable.
---

# Project Agent

Use these bundled instructions to maintain the requested project's continuity
with ARIS pipelines, workflows or individual skills. Their original contracts
still govern. Product commands use installed `superaris` or `python -m superaris`;
this does not require globally installing the skill or an ARIS product wrapper.

Read the project's `AGENTS.md`, current status and recovery entrypoint
first. Restore active work and its real owner before making new assignments;
reading this skill does not designate you as coordinator or resume paused work.

For startup, role presets and helper resolution, read
[references/launch.md](references/launch.md). Before Herdr scheduling, verify
the actual environment: `HERDR_ENV=1` is one signal, but backend shell calls may
lack it. In that case use an explicit user-confirmed session/pane association
and official API verification of the caller's native session/process and cwd.
Fully read `herdr --skill`, then check local `herdr --help` and the relevant
command group's help. An explicitly user-invoked launcher can bootstrap the
named project/session. Otherwise, without verified association, prepare startup
instructions or do ordinary file work. Never synthesize the marker or take over
the user's focused pane.

For delegation, writing roles, project memory, receipt handling or recovery,
read [references/coordination.md](references/coordination.md). Use native
callbacks when available, otherwise the project-limited runtime bridge; inspect
real outputs and continue the next authorized step. Protect human input and
reconcile lost events before repeating operations. For the executable
start → watch → report → receiver → acknowledge chain and explicit memory events,
read [references/receipts.md](references/receipts.md).

Load the selected host-correct ARIS skills and their required references in each
executing role. Files being present or discoverable does not prove the role
actually read them or has the required capabilities. Retain existing MCP routes,
reviewer freshness, writer ownership, acceptance and budget boundaries. Do not
substitute persistent panes for every temporary worker or independent reviewer.
