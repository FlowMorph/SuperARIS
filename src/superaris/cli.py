"""Command interface; --plan is offline and does not write project state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

PRESETS = {
    "codex": {"main": "codex", "engineer": "codex", "writer": "codex"},
    "cc-codex": {"main": "claude", "engineer": "codex", "writer": "claude"},
    "cc-codex-agy": {"main": "claude", "engineer": "codex", "writer": "agy"},
}


class _ArgumentParser(argparse.ArgumentParser):
    def parse_args(self, args=None, namespace=None):
        raw = list(sys.argv[1:] if args is None else args)
        parsed = super().parse_args(raw, namespace)
        if parsed.command == "start" and parsed.project is not None:
            if getattr(parsed, "orca_bin", None) and any(separator in parsed.orca_bin for separator in ("/", "\\")):
                # Resolve explicit paths in the invoking cwd, before execution
                # changes to the project or pending startup is resumed elsewhere.
                parsed.orca_bin = str(Path(parsed.orca_bin).expanduser().resolve())
            # Recovery can be opened from another cwd. Keep the wizard's
            # canonical prefix and serialize the parsed options unchanged.
            canonical = ["start", str(parsed.project.expanduser().resolve())]
            for action in self.start_parser._actions:
                if not action.option_strings:
                    continue
                value = getattr(parsed, action.dest, None)
                if value is None or value is False:
                    continue
                flag = action.option_strings[-1]
                if value is True:
                    canonical.append(flag)
                else:
                    for item in value if isinstance(value, list) else [value]:
                        canonical.extend([flag, str(item)])
            parsed.start_arguments = canonical
        return parsed


def assignments(values: list[str]) -> dict[str, str]:
    result = {}
    for value in values:
        key, sep, item = value.partition("=")
        if not sep or not key.strip() or not item.strip():
            raise ValueError(f"expected ROLE=VALUE, got {value!r}")
        result[key] = item
    return result


def make_plan(args: argparse.Namespace) -> dict:
    project = args.project.expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"project directory does not exist: {project}")
    from .state import directory, read
    current = read(directory(project) / "launch.json", {})
    from .hosts import selected_host
    host = selected_host(current, getattr(args, "host", None))
    pending = current.get("pending_start", {})
    remembered = ({item["role"]: item for item in pending.get("roles", [])}
                  if pending else current.get("roles", {}))
    preset = args.preset or current.get("preset", "codex")
    # New defaults do not migrate an existing or unfinished team. An explicit
    # role selection (or a different preset) is the existing opt-in expansion.
    retain_team = bool(remembered) and not args.role and args.only_role is None and (
        args.preset is None or args.preset == current.get("preset"))
    roles = ({role: record["harness"] for role, record in remembered.items()}
             if retain_team else {**PRESETS[preset], **assignments(args.role)})
    inherited = remembered if retain_team else {}
    models = {role: record.get("model", record.get("requested_model"))
              for role, record in inherited.items()}
    models.update(assignments(args.model))
    role_tasks = assignments(args.role_task)
    scopes = assignments(args.write_scope)
    selected = args.only_role if args.only_role is not None else list(roles)
    if (set(selected) | models.keys() | role_tasks.keys() | scopes.keys()) - roles.keys():
        raise ValueError("role/model selection names a role outside the preset or --role entries")
    if any(kind not in {"codex", "claude", "agy"} for kind in roles.values()):
        raise ValueError("supported harnesses: codex, claude, agy")
    return {
        "mode": "plan", "project": str(project), "session": args.session, "host": host,
        "preset": preset, "task": args.task or inherited.get("main", {}).get("task") or inherited.get("main", {}).get("inputs", {}).get("task") or "Recover this project and continue only its already authorized work.",
        "skills": args.skill or ["project-agent"],
        "roles": [{"role": role, "harness": kind, "model": models.get(role),
                   "task": role_tasks.get(role, (args.task if role == "main" else None)
                       or inherited.get(role, {}).get("task") or inherited.get(role, {}).get("inputs", {}).get("task")
                       or ("Recover this project and continue only its already authorized work." if role == "main" else
                           "Read your context and wait for the main owner's scoped assignment. Do not execute the main task or edit project artifacts yet.")),
                   "write_scope": str((project / scopes.get(role,
                       inherited.get(role, {}).get("write_scope") or inherited.get(role, {}).get("inputs", {}).get("write_scope")
                       or ("." if role == "main" else f".aris/workbench/outputs/{role}"))).resolve()),
                   "active": role in selected} for role, kind in roles.items()],
        "will_mutate": False,
    }


def parser(prog: str = "superaris") -> argparse.ArgumentParser:
    p = _ArgumentParser(prog=prog, description="SuperARIS project workbench: native owners, ARIS skills and existing MCP collaboration.",
                                epilog="交互启动 / Interactive: superaris (or superaris start). 脚本用法 / Scripts: superaris start PROJECT [options].")
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("start", help="start or reconnect the selected project owners")
    p.start_parser = s
    s.add_argument("project", type=Path, nargs="?")
    s.add_argument("--name", help="readable new workbench name; existing owners are not renamed")
    s.add_argument("--plan", action="store_true", help="offline preview; no writes or processes")
    s.add_argument("--session", default="aris", help="explicit local Herdr session (default: aris)")
    s.add_argument("--host", choices=("herdr", "orca"), help="new-project workbench; existing projects keep their original host")
    s.add_argument("--orca-bin", help="explicit official Orca CLI launcher; otherwise discover the installed app")
    s.add_argument("--owner", help="explicit existing main agent name/pane to adopt after verification")
    s.add_argument("--preset", choices=PRESETS, help="new-team mapping (default: codex); reconnect preserves the recorded team")
    s.add_argument("--role", action="append", default=[], metavar="ROLE=HARNESS")
    s.add_argument("--only-role", action="append", choices=None, help="activate only the listed roles; new teams default to main, engineer and writer")
    s.add_argument("--model", action="append", default=[], metavar="ROLE=MODEL")
    s.add_argument("--skill", action="append", default=[])
    s.add_argument("--aris-repo", type=Path, help="explicit canonical ARIS checkout; otherwise use the pinned product cache")
    s.add_argument("--recovery", action="append", default=[])
    s.add_argument("--clear-recovery", action="store_true", help="explicitly clear retained recovery inputs")
    s.add_argument("--task", help="explicit new task; omitted on reconnect preserves the existing task")
    s.add_argument("--role-task", action="append", default=[], metavar="ROLE=TEXT", help="distinct assignment for a collaborator; otherwise it waits for main")
    s.add_argument("--write-scope", action="append", default=[], metavar="ROLE=PATH", help="owned role output area inside the project")
    s.add_argument("--no-attach", action="store_true", help="leave UI focus unchanged and print launch result")
    s.add_argument("--no-receiver", action="store_true", help="explicitly stop/disable project receiving until receiver start")
    s.add_argument("--no-install", action="store_true", help="report missing Herdr instead of installing")
    s.add_argument("--herdr-bin", default="herdr")
    s.add_argument("--caller-pane", help="explicit user-confirmed caller pane if verifying a managed caller")
    s.add_argument("--caller-native-session", help="known caller native session, never guessed from history")
    s.add_argument("--automation-owned", action="store_true", help="new roles are dedicated to automation; default human-input-safe notices")
    context = sub.add_parser("context", help="prepare local role navigation/skills without sending input or changing its task")
    context.add_argument("project", type=Path)
    context.add_argument("--role", required=True)
    context.add_argument("--skill", action="append", default=[])
    context.add_argument("--task", help="task for this preparation only; the current owner assignment remains unchanged")
    context.add_argument("--aris-repo", type=Path, help="canonical ARIS checkout for this preparation")
    usage = sub.add_parser("usage", help="本地只读用量 / read-only local usage")
    usage.add_argument("project", type=Path)
    usage.add_argument("--by-role", action="store_true", help="按绑定角色展示 / group by bound role")
    usage.add_argument("--json", action="store_true", help="结构化输出 / structured output")
    usage.add_argument("--hours", type=float, default=24, help="回看小时数 / lookback hours (24)")
    usage.add_argument("--since", help="带时区的起始ISO时间 / ISO start with timezone")
    usage.add_argument("--until", help="带时区的结束ISO时间 / ISO end with timezone")
    usage.add_argument("--claude-root", type=Path, help="Claude projects日志目录 / Claude projects log root")
    usage.add_argument("--codex-root", type=Path, help="Codex sessions日志目录 / Codex sessions log root")
    usage.add_argument("--lang", choices=["zh", "en"], help="输出语言 / output language")
    for command in ("listen", "reconcile", "watch", "report", "acknowledge", "remember", "control", "resolve-delivery", "receiver"):
        item = sub.add_parser(command)
        item.add_argument("project", type=Path)
        item.add_argument("--herdr-bin", default="herdr")
        if command in {"listen", "reconcile"}:
            if command == "listen":
                item.add_argument("--duration", type=float, default=3600, help="foreground connection lifetime in seconds")
                item.add_argument("--interval", type=float, default=5, help="local registered-file reconciliation interval")
        elif command == "watch":
            item.add_argument("--id", required=True)
            item.add_argument("--owner-role", default="main")
            item.add_argument("--worker-role")
            item.add_argument("--record", help="existing original task record, never parsed as a database")
            item.add_argument("--deliverable", action="append", default=[])
            item.add_argument("--watch-file", action="append", default=[])
            item.add_argument("--wait-for", required=True)
            item.add_argument("--query", required=True, help="original protocol/status entry, displayed to owner; never shell-executed")
            item.add_argument("--next", required=True, help="next already authorized step, subject to original gates")
        elif command == "report":
            item.add_argument("--id", required=True)
            item.add_argument("--outcome", choices=["completed", "failed", "blocked", "reply"], required=True)
            item.add_argument("--message", required=True)
        elif command == "acknowledge":
            item.add_argument("--id", required=True)
            item.add_argument("--evidence", required=True)
        elif command == "receiver":
            item.add_argument("--action", choices=["status", "start", "stop", "run"], default="status")
            item.add_argument("--generation", help=argparse.SUPPRESS)
        elif command == "control":
            item.add_argument("--role", default="main")
            item.add_argument("--mode", choices=["human", "automation"], required=True)
        elif command == "resolve-delivery":
            item.add_argument("--role", default="main")
            item.add_argument("--handle", help="bridge handle ID instead of role context delivery")
            item.add_argument("--resolution", choices=["received", "not-delivered"], required=True)
            item.add_argument("--evidence", required=True, help="existing readback/receipt file after actual inspection")
        else:
            item.add_argument("--file", required=True, help="existing authoritative memory file")
            item.add_argument("--kind", choices=["correction", "decision", "delivery", "failure", "handoff"], required=True)
            item.add_argument("--scope", required=True)
            item.add_argument("--source", required=True)
            item.add_argument("--text", required=True)
            item.add_argument("--expected-mtime-ns", type=int)
    return p


def prepare_role_context(project: Path, args: argparse.Namespace) -> dict:
    """Reuse the launcher resolver while leaving live assignment/delivery intact."""
    from .context import prepare_context
    from .state import directory, launch_lock, read
    from .runtime import _exclude_writers
    from .dependencies import resolve_aris_repo
    with launch_lock(project):
        binding = read(directory(project) / "launch.json", {})
        record = binding.get("roles", {}).get(args.role)
        if not record:
            raise ValueError(f"No recorded owner for role {args.role!r}; start or explicitly adopt that role first")
        inputs = record.get("inputs", {})
        skills = list(dict.fromkeys([*inputs.get("skills", []), *args.skill]))
        scope = inputs.get("write_scope")
        import os
        aris_repo = resolve_aris_repo(getattr(args, "aris_repo", None) or os.environ.get("SUPERARIS_ARIS_REPO") or binding.get("aris_repo"))
        result = prepare_context(project, args.role, record["harness"],
                                 args.task if args.task is not None else inputs.get("task", "Read project context and wait for the owner's scoped assignment."),
                                 skills, inputs.get("recovery", []), repo=aris_repo,
                                 write_scope=[scope] if scope else [])
        others = [{"role": role, "write_scope": other["inputs"]["write_scope"]}
                  for role, other in binding.get("roles", {}).items()
                  if role != "main" and other.get("inputs", {}).get("write_scope")]
        _exclude_writers(result, args.role, others)
    return {"mode": "prepared", "role": args.role, "delivered": False,
            "assignment_changed": False, **result}


def main(argv: list[str] | None = None, *, prog: str = "superaris") -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    command_parser = parser(prog)
    interactive = prog == "superaris" and raw in ([], ["start"])
    if interactive:
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print("SuperARIS 向导需要交互终端；未启动任何会话。\n"
                  "The SuperARIS wizard requires an interactive terminal; no sessions were started.\n"
                  "脚本用法 / Scripts: superaris start PROJECT [options].")
            command_parser.print_help()
            return 0
        from .wizard import Cancelled, run
        from .ui import tr
        try:
            selection = run()
            if selection is None:
                print(tr("已取消启动，未创建工作台。"))
                return 0
        except (Cancelled, EOFError, KeyboardInterrupt):
            print("\n" + tr("已取消启动，未创建工作台。"))
            return 0
        args = command_parser.parse_args(selection.arguments)
        args.wizard_arguments = selection.arguments
        args.wizard_resume_existing = selection.resume_existing
        args.ui_language = selection.ui_language
        if selection.create_project:
            try:
                args.project.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                print(tr("无法创建项目目录：{error}", error=exc), file=sys.stderr)
                return 1
    else:
        args = command_parser.parse_args(raw)
        if args.command == "start" and args.project is None:
            command_parser.error("start requires PROJECT; run bare superaris in an interactive terminal for the wizard")
    try:
        if args.command != "start":
            project = args.project.expanduser().resolve()
            if not project.is_dir():
                raise ValueError("Selected project directory does not exist")
            if args.command == "usage":
                import math
                from .usage import collect, render
                from .usage_logs import timestamp
                start, end = timestamp(args.since), timestamp(args.until)
                if args.since is not None and start is None or args.until is not None and end is None:
                    raise ValueError("时间必须为带时区的ISO格式 / timestamps require ISO format and timezone")
                if not math.isfinite(args.hours) or args.hours <= 0:
                    raise ValueError("hours须为正有限数 / hours must be positive and finite")
                result = collect(project, claude_root=args.claude_root, codex_root=args.codex_root,
                                 since=start, until=end, hours=args.hours)
                if args.json:
                    if not args.by_role:
                        result.pop("roles")
                    print(json.dumps(result, ensure_ascii=False, indent=2))
                else:
                    language = args.lang or result["ui_language"]
                    print(render(result, by_role=args.by_role, lang=language))
                return 0
            from . import tasks
            if args.command == "context":
                result = prepare_role_context(project, args)
            elif args.command == "receiver":
                from .receiver import ensure_receiver, run, status, stop
                if args.action == "start":
                    result = ensure_receiver(project, args.herdr_bin, enable=True)
                elif args.action == "stop":
                    result = stop(project)
                elif args.action == "run":
                    if not args.generation:
                        raise ValueError("Internal receiver run requires its prepared generation")
                    result = run(project, args.generation, args.herdr_bin)
                else:
                    result = status(project)
            elif args.command == "watch":
                result = tasks.register(project, args)
            elif args.command == "report":
                result = tasks.report(project, args.id, args.outcome, args.message)
            elif args.command == "acknowledge":
                result = tasks.acknowledge(project, args.id, args.evidence)
            elif args.command == "remember":
                result = tasks.remember(project, args)
            elif args.command in {"control", "resolve-delivery"}:
                from .runtime import control, resolve_delivery
                result = control(project, args.role, args.mode, args.herdr_bin) if args.command == "control" else resolve_delivery(project, args)
            else:
                from .bridge import listen
                result = listen(project, binary=args.herdr_bin,
                                duration=args.duration if args.command == "listen" else 0,
                                interval=args.interval if args.command == "listen" else 5)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0
        plan = make_plan(args)
        if not args.plan:
            from .runtime import start
            if interactive:
                from .wizard import launch
                from .state import launch_lock
                from .runtime import binding, save_binding
                # Save only the confirmed UI choice in the existing record.
                # The selection phase and cancellation never write preferences.
                with launch_lock(Path(plan["project"])):
                    current = binding(Path(plan["project"])) or {
                        "project": plan["project"], "session": plan["session"],
                        "preset": plan["preset"], "roles": {}, "host": plan["host"],
                    }
                    current["ui_language"] = args.ui_language
                    save_binding(Path(plan["project"]), current)
                try:
                    plan = launch(plan, args)
                except (KeyboardInterrupt, EOFError):
                    plan = None
                if plan is None:
                    print(tr("已保留当前工作台。下次在 superaris 中选择这个项目即可继续。"))
                    return 0
            else:
                plan = start(plan, args)
            from .receiver import ensure_receiver, stop
            project = Path(plan["project"])
            if not interactive:
                plan["receiver"] = stop(project) if args.no_receiver else ensure_receiver(project, args.herdr_bin)
            if interactive and "receiver" not in plan:
                from .wizard import completed
                plan["receiver"] = stop(project) if args.no_receiver else ensure_receiver(project, args.herdr_bin)
                completed(project)
        if interactive:
            print("\n" + tr("工作台已准备：{project}\n已启动的角色保持原任务。", project=plan["project"]), flush=True)
        else:
            print(json.dumps(plan, ensure_ascii=False, indent=2))
        if not args.plan and not args.no_attach and not getattr(args, "wizard_attached", False):
            from .runtime import attach
            return attach(Path(plan["project"]), args.herdr_bin)
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        message = str(exc)
        if interactive:
            try:
                data = json.loads(message)
                message = data.get("error", data).get("message", message)
            except (ValueError, AttributeError):
                pass
            print(tr("暂时无法启动工作台：{error}", error=message), file=sys.stderr)
        else:
            print(f"error: {message}", file=sys.stderr)
        return 1
