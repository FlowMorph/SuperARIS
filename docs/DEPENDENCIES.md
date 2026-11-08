# Dependencies and source selection

SuperARIS v0.1.0 requires Python ≥3.10 on macOS/Linux. Its runtime uses Unix
`fcntl` locks and PTYs; Windows runtime support is not provided. Herdr carries
visible sessions. Install/login to the native CLIs selected for your team using
their own instructions. Executable detection is not an authentication or model
probe. Missing Herdr follows the launcher's existing Homebrew installation path
where available; otherwise the reported dependency must be installed separately.

## ARIS is a separate source dependency

SuperARIS bundles its Claude Code/Codex project-agent resources. ARIS supplies
research skills, shared references, catalogs and canonical helpers. The default
public source is [Auto-claude-code-research-in-sleep](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep)
at MIT-licensed commit
[`2901234ad2954cd2388ced8d3aed2ed9de42803a`](https://github.com/wanshuiyin/Auto-claude-code-research-in-sleep/tree/2901234ad2954cd2388ced8d3aed2ed9de42803a).

When confirmed startup or context preparation needs that source, the product
lazily downloads it to `$XDG_CACHE_HOME/superaris/aris/<commit>` or
`~/.cache/superaris/aris/<commit>` when XDG_CACHE_HOME is unset. Help, offline
plans, chooser screens and cancellation do not fetch ARIS. No model is called
by source acquisition. Network failure is reported rather than silently using
an unrelated checkout.

Use an explicit full ARIS checkout to work offline or retain a chosen version:

```bash
SUPERARIS_ARIS_REPO=/path/to/aris superaris
superaris start /path/to/project --aris-repo /path/to/aris --plan
superaris context /path/to/project --role main --aris-repo /path/to/aris --skill experiment-plan
```

The checkout must contain canonical `skills/`, host mirrors, `docs/` and `tools/`.
SuperARIS does not modify an explicit checkout to inject its bundled resource.
A bound project records `aris_repo` so future preparation preserves its selected
source. Existing host-correct skill customizations retain their source
precedence and provenance; the original project files remain authoritative.

Ambient `ARIS_REPO` is a canonical-helper variable, not an implicit SuperARIS
source selector. Likewise `~/.aris/repo`, the old adaptation tree and globally
installed skills are not prerequisites for the independent product. Use
`SUPERARIS_ARIS_REPO` or `--aris-repo` for product source selection. When a skill
needs a canonical ARIS helper, follow its host-correct resolver against the
selected checkout and set the actual helper root in that same shell invocation.
Do not derive a SuperARIS executable from `$ARIS_REPO/tools/`.

## Updates

The preview's default ARIS pin does not track mutable upstream main. A later
SuperARIS version can update that pin. To choose another source now, explicitly
provide a valid checkout and preserve the project's existing owner, contracts,
budgets and pending work. Updating source does not mean current sessions have
read it; prepare the required context and explicitly read the selected skill.
No global skills, model settings or MCP configuration are rewritten.

Use `superaris` from the installed environment, or `python -m superaris` with
that environment's interpreter. Do not start a new-version receiver for a project
while a receiver from a legacy launcher is still active. The original local
launcher is not automatically replaced by installing this independent package.
