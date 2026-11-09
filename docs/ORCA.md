# Orca workbench (Terminal v1)

SuperARIS can use [Orca](https://www.onorca.dev/) as an optional workbench for its main, engineer and writer roles. Herdr remains the default, and existing Herdr projects keep their original team and recovery behavior. Orca Terminal v1 uses native terminal sessions with the same ARIS navigation, skills, project files and MCP configuration. The three presets remain `codex` (Codex / Codex / Codex), `cc-codex` (Claude Code / Codex / Claude Code), and `cc-codex-agy` (Claude Code / Codex / Antigravity).

Install and open the official Orca application, then run `superaris`. For a new project, the chooser detects available workbenches; it preselects the available one when only one is found, or offers a choice with Herdr recommended when both are available. SuperARIS first looks for the official CLI on PATH and can also find the bundled launcher in standard macOS and Windows app locations. If the app is present but its CLI is unavailable, use **Orca → Settings → General → Orca CLI** to register the command. On Linux the official command is `orca-ide`, avoiding the unrelated screen-reader command named `orca`. Native agent login and trust prompts remain in their own terminals; detecting a CLI does not establish model access.

| Action | Command |
|---|---|
| Open the project/workbench chooser | `superaris` |
| Inspect a new Orca project plan | `superaris start "/path/to/project" --host orca --plan` |
| Start the default three-role team in Orca | `superaris start "/path/to/project" --host orca` |
| Choose another existing preset | `superaris start "/path/to/project" --host orca --preset cc-codex-agy` |
| Supply a known official CLI launcher | `superaris start "/path/to/project" --host orca --orca-bin "/path/to/official/launcher"` |
| Resume the same project and original team | `superaris start "/path/to/project"` |
| Inspect the project's receiver | `superaris receiver "/path/to/project" --action status` |

`python -m superaris` with the installed environment's interpreter is equivalent to the `superaris` prefix above. Quote paths containing spaces or Chinese characters. A project's recorded workbench is retained on reentry; older bindings without a host field remain Herdr. Selecting another host does not migrate an existing team.

The original main agent coordinates work through the same [registered results and file-memory flow](RESULTS_AND_MEMORY.md): register a task, receive the worker's report and actual files, check the existing acceptance criteria, then continue the next authorized step. Personal preferences and project memory remain in their original files; independent MCP reviewers keep their original isolation and acceptance requirements. A delivery receipt alone does not establish that a role read its packet or completed the task. Human drafts and permission prompts must be resolved in the native terminal; uncertain delivery is inspected before resending. Closing the Orca window and ending its runtime are different events: the receiver stays tied to the original main identity and reachable runtime, and its status is the recovery check.

Native validation used official Orca **1.4.254 on macOS** and an isolated local headless runtime. Three persistent Codex roles read ARIS; the original main dispatched engineering work, received reports, independently checked the files, assigned writing, verified the result and updated existing project memory. Same-project reentry reused all three original terminal identities. A separate Claude Code / Codex / Antigravity startup retained the original partial owner and exposed native informational/trust waits without answering them. Automated tests cover host selection, partial recovery, receipt uncertainty, drafts and real receiver subprocesses against simulated transport. Native Orca Windows/Linux sessions and GUI window closure were not tested in that headless exercise; remote environments and Structured Chat are outside this terminal integration. See [Windows support](WINDOWS.md) for the separately tested product platform scope.
