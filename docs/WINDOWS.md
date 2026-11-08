# Native Windows setup

SuperARIS supports a native Windows Terminal / PowerShell installation with
Python 3.10+, Herdr and the native CLIs chosen for the team. WSL is optional
for workflows that need a Linux environment. The same three-role presets,
per-role model choices and project recovery records apply.

## Install and open

Install Python with the Windows `py` launcher available. For installation from
the repository, also install Git and make it available on PATH. In PowerShell:

```powershell
py -m pip install --user pipx
py -m pipx ensurepath
```

Open a new terminal so PATH changes take effect, then run:

```powershell
pipx install "git+https://github.com/wanshuiyin/SuperARIS.git"
superaris
```

A downloaded local wheel does not need Git:

```powershell
pipx install "C:\Downloads\superaris-0.1.0-py3-none-any.whl"
superaris
```

The wheel installs the product; first use of ARIS resources still needs network
access unless a complete local ARIS checkout is selected. For an offline pipx
installation, its build/runtime dependencies must also be locally available.

Choose language, project, team and models, review the summary, then confirm.
Language/project selection, `--help`, `--plan` and cancellation do not install
Herdr or fetch ARIS. On confirmed startup, missing Herdr can be installed using
the [official PowerShell installer](https://herdr.dev/tui/docs/install/).
You may instead install it yourself:

```powershell
powershell -ExecutionPolicy Bypass -c "irm https://herdr.dev/install.ps1 | iex"
```

The installer uses the stable channel by default. When using the manual Windows
zip, keep its extracted directory together: `herdr.exe` needs the accompanying
ConPTY runtime. Reopen the terminal if PATH has changed.

Install the selected `codex`, `claude` and/or `agy` CLI using that vendor's native
Windows instructions, then complete its own login and model configuration.
SuperARIS does not approve login/trust prompts or rewrite model/MCP settings.
Finding the executable confirms only that it is available on PATH.

## Paths, source selection and recovery

Use quoted Windows paths, including paths with spaces or Chinese characters:

```powershell
superaris start "C:\Research\我的项目" --preset codex --plan
$env:SUPERARIS_ARIS_REPO = "C:\Research Tools\aris"
superaris
```

The environment variable is optional; by default SuperARIS obtains its pinned
ARIS source when needed. A local source must be a complete checkout, including
skills, host mirrors, catalogs and canonical helpers. See
[source selection and cache locations](DEPENDENCIES.md).

Rerun `superaris` and select the same bound project to recover its original
team and pending choices. Keep the original owner and unknown delivery state;
an uncertain prompt is not automatically resent. Native login or trust waits
must be cleared in the relevant CLI. Closing the attached workbench leaves the
receiver and original running team available. Receiver continuation depends on
the original owner and server remaining alive; rebooting or stopping that server
is different from detaching. Do not run a legacy receiver and the installed
product's receiver against the same active project.

## Support and verification scope

The product's platform boundary uses Windows kernel file locks, raw
newline-delimited JSON over Herdr named pipes, and a detached receiver subprocess.
It preserves single-listener ownership and delivery/recovery rules. Herdr's
[Windows support documentation](https://herdr.dev/tui/docs/windows-beta/)
describes native ConPTY panes and PowerShell attach; its
[socket API documentation](https://herdr.dev/tui/docs/socket-api/) defines the
transport. These upstream capabilities do not by themselves validate SuperARIS.

Validation has distinct layers: product unit tests with synthetic transport;
Windows runner installation, process/lock/pipe and recovery checks; an isolated
real-Herdr smoke test without a model; and interactive native CLI experience.
A passing layer establishes only its exercised paths. The Windows CI run and
its logs are the evidence for automated checks; this guide does not claim a
complete interactive three-client/model run or paid-model validation.

ARIS skills retain their own dependencies. A skill may require Bash, Unix tools,
SSH, Docker, GPU software, LaTeX or a particular remote host. Read that skill's
requirements before execution; use a suitable host or WSL for those workflows.
Native product support does not mean every upstream skill or helper has been
ported to Windows. Herdr also documents platform-specific terminal and live-cwd
limitations; retain identity verification when those observations are incomplete.
