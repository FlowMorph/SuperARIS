"""Bilingual terminal entry; collect choices before using the existing launcher."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
import shutil
import unicodedata

from .platform import WINDOWS
from . import ui
from .ui import tr


class Cancelled(Exception):
    pass


class Back(Exception):
    pass


@dataclass
class Selection:
    arguments: list[str]
    create_project: bool
    resume_existing: bool = False
    ui_language: str = "zh"


LABELS = {"codex": "Codex", "claude": "Claude Code（CC）", "agy": "Antigravity（AGY）"}
ROLES = {"main": "主会话：统筹、恢复与验收", "engineer": "工程：实现与事实核查", "writer": "写作：正文与解释"}
COMBINATIONS = [
    ("仅 Codex（三角色）", "codex", [("main", "codex"), ("engineer", "codex"), ("writer", "codex")]),
    ("CC + Codex（三角色）", "cc-codex", [("main", "claude"), ("engineer", "codex"), ("writer", "claude")]),
    ("CC + Codex + AGY（三角色）", "cc-codex-agy", [("main", "claude"), ("engineer", "codex"), ("writer", "agy")]),
]


def default_project(cwd: Path | None = None, home: Path | None = None) -> Path:
    cwd = (cwd or Path.cwd()).resolve()
    home = (home or Path.home()).resolve()
    return home / "Desktop/superaris-project" if cwd in (home, Path(cwd.anchor)) else cwd


def ask(prompt: str, default: str = "", *, back: bool = True) -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}{tr('：')}").strip()
    if answer.lower() in {"q", "quit", "退出", "取消"}:
        raise Cancelled
    if back and answer.lower() in {"b", "返回"}:
        raise Back
    return answer or default


def choose(prompt: str, options: list[str], default: int = 1) -> int:
    for number, label in enumerate(options, 1):
        print(f"  {number}. {label}")
    while True:
        value = ask(prompt, str(default))
        if value.isdecimal() and 1 <= int(value) <= len(options):
            return int(value)
        print(tr("请输入上面的选项编号；b 返回项目选择，q 取消。"))


def capabilities() -> dict[str, str | None]:
    from .hosts import discover_orca
    available = {kind: shutil.which(kind) for kind in ("herdr", "codex", "claude", "agy", "brew")}
    found = discover_orca()
    available.update(orca=found.get("cli"), orca_app=found.get("app"))
    return available


def select_workbench(available: dict, previous: str | None = None) -> str:
    """Choose only for a new project; discovery never probes a running host."""
    if available.get("herdr") and available.get("orca"):
        return ("herdr", "orca")[choose(tr("工作台宿主"), [tr("Herdr（推荐）"), "Orca"],
                                        2 if previous == "orca" else 1) - 1]
    if available.get("orca"):
        return "orca"
    if not available.get("herdr") and available.get("orca_app"):
        # The installed app needs command registration, not a different host.
        return "orca"
    # Preserve Herdr's working installation path when neither CLI was found.
    return "herdr"


def recovery_capabilities(available: dict, bound: dict) -> dict:
    """Resolve the original executable using files only, never native status."""
    from .hosts import discover_orca
    pending = bound.get("pending_start") or {}
    explicit = bound.get("orca_bin") or pending.get("orca_bin")
    if not explicit:
        arguments = pending.get("arguments", [])
        if isinstance(arguments, list):
            for index, argument in enumerate(arguments):
                if argument == "--orca-bin" and index + 1 < len(arguments):
                    explicit = arguments[index + 1]
                    break
                if isinstance(argument, str) and argument.startswith("--orca-bin="):
                    explicit = argument.partition("=")[2]
                    break
    if not explicit:
        return available
    found = discover_orca(explicit)
    return {**available, "orca": found.get("cli"), "orca_recorded": explicit}


def show_capabilities(available: dict) -> None:
    print(tr("\n本机客户端命令："))
    for kind in ("codex", "claude", "agy"):
        print(f"  {tr(LABELS[kind])}{tr('：')}{tr('已找到' if available[kind] else '未找到')}")
    print(tr("登录与模型设置由各自客户端处理；CC 使用你的已有配置。"))


def dependency_summary(available: dict, host: str = "herdr") -> bool:
    if host == "orca":
        if available.get("orca"):
            print(tr("Orca：已找到 CLI；启动时核对原生服务，沿用你的模型与登录配置。"))
            return True
        if available.get("orca_recorded"):
            print(tr("原项目 Orca CLI 入口不可用：{path}。请核对原入口，或用 --orca-bin 明确指定可用 CLI 后继续。",
                     path=available["orca_recorded"]))
        elif available.get("orca_app"):
            print(tr("Orca 应用已安装；请打开 Settings → General → Orca CLI 注册命令，再继续这个项目。"))
        else:
            print(tr("Orca CLI 未找到；请从 https://www.onorca.dev/download 安装并打开 Orca，再继续这个项目。"))
        return False
    if host != "herdr":
        raise ValueError(f"Unknown workbench: {host}")
    if available["herdr"]:
        print(tr("Herdr：已找到，复用现有服务；需要时建立所选项目工作台。"))
        return True
    if WINDOWS:
        print(tr("Herdr：未找到；确认启动后会使用官方 Windows 安装器。"))
        return True
    if available["brew"]:
        print(tr("Herdr：未找到；选择启动后会经现有 Homebrew 安装（brew install herdr）。"))
        return True
    print(tr("Herdr：未找到，也未找到 Homebrew。请先安装 Herdr TUI 后重试："))
    print(tr("https://herdr.dev/tui/docs/install/ （本次不会启动模型或创建项目）"))
    return False


def select_model(role: str, kind: str, previous: str | None) -> str | None:
    print(tr("\n{role} / {client} — 模型", role=ui.role_label(role), client=tr(LABELS[kind])))
    examples = {"codex": "gpt-6.1-sol", "agy": "gemini-4-argon-high"}
    example = examples.get(kind)
    options = [tr("沿用已有设置"), tr("手动输入模型 ID")]
    if example:
        title = "GPT-6.1 Sol" if kind == "codex" else "Gemini 4 Argon High"
        options.append(tr("{title}（可选型号）", title=title))
    default = 3 if previous and previous == example else 2 if previous else 1
    choice = choose(tr("模型选择"), options, default)
    if choice == 1:
        return None
    if choice == 3:
        return example
    while True:
        model = ask(tr("模型 ID"), previous or "")
        if model:
            return model
        print(tr("请输入原生 CLI 支持的模型 ID，或 b 返回项目选择。"))


def _preview_pad(text: str, width: int) -> str:
    cells = sum(2 if unicodedata.east_asian_width(char) in {"W", "F"} else 1 for char in text)
    return text + " " * max(0, width - cells)


def layout(roles: list[tuple[str, str]]) -> None:
    print(tr("\n分工与布局预览："))
    clients = {role: {"claude": "CC", "codex": "Codex", "agy": "AGY"}[kind] for role, kind in roles}
    main = tr("主会话") + " / " + clients.get("main", "")
    engineer = tr("工程") + " / " + clients.get("engineer", "")
    writer = tr("写作") + " / " + clients.get("writer", "")
    if len(roles) == 3:
        print("┌────────────────────┬──────────────────────┐")
        print(f"│ {_preview_pad(main, 19)}│ {_preview_pad(engineer, 21)}│")
        print("│                    ├──────────────────────┤")
        print(f"│                    │ {_preview_pad(writer, 21)}│")
        print("└────────────────────┴──────────────────────┘")
    elif len(roles) == 2:
        print("┌────────────────────┬──────────────────────┐")
        print(f"│ {_preview_pad(main, 19)}│ {_preview_pad(engineer, 21)}│")
        print("└────────────────────┴──────────────────────┘")
    else:
        print("┌───────────────────────────────────────────┐")
        print(f"│ {_preview_pad(main, 42)}│")
        print("└───────────────────────────────────────────┘")


def session_name(project: Path) -> str:
    slug = re.sub(r"[^a-z0-9_-]", "-", project.name.lower()).strip("-_") or "project"
    return f"superaris-{slug[:32]}"


def run() -> Selection | None:
    """No Herdr requests, model probes or filesystem writes during selection."""
    from .runtime import binding
    from .hosts import selected_host
    try:
        preferred = binding(Path.cwd().resolve()).get("ui_language", "zh")
    except (OSError, ValueError):
        preferred = "zh"
    default_language = "2" if preferred == "en" else "1"
    print("\nSuperARIS · 界面语言 / Interface language")
    print("  1. 简体中文\n  2. English")
    while True:
        value = input(f"请选择语言 / Choose language [{default_language}]: ").strip().lower() or default_language
        if value in {"q", "quit", "退出", "取消"}:
            ui.set_language("en" if preferred == "en" else "zh")
            raise Cancelled
        if value in {"1", "zh", "简体中文", "2", "en", "english"}:
            ui.set_language("zh" if value in {"1", "zh", "简体中文"} else "en")
            break
        print("请输入 1 或 2，q 取消。 / Enter 1 or 2; q cancels.")
    print(tr("\nSuperARIS · 中文启动向导"))
    print(tr("逐步选择项目、客户端和模型，再预览启动。b 返回项目选择，q 随时取消。"))
    print(tr("当前位置：{path}", path=Path.cwd()))
    selected_path = default_project()
    if selected_path != Path.cwd().resolve():
        print(tr("当前位置是 Home 或文件系统根；建议使用独立项目目录，避免把整个目录作为写域。"))
    combo = 1
    models = {}
    name = ""
    task = ""
    previous_project = None
    host_choices = {}
    while True:
        try:
            print(tr("\n[1/4] 选择项目"))
            raw = ask(tr("项目目录（可输入新目录，含空格无需引号）"), str(selected_path), back=False)
            if raw in {"b", "返回"}:
                continue
            if len(raw) > 1 and raw[0] == raw[-1] and raw[0] in "\"'":
                raw = raw[1:-1]
            project = Path(raw).expanduser().resolve()
            if project.exists() and not project.is_dir():
                print(tr("这个路径是文件，请选择一个项目目录。"))
                continue
            selected_path = project
            if previous_project != project:
                name = project.name
                task = ""
                previous_project = project
            available = capabilities()
            old = binding(project) if project.is_dir() else {}
            if old:
                host = selected_host(old)
                if host == "orca":
                    available = recovery_capabilities(available, old)
                pending = old.get("pending_start")
                if not old.get("session") or (not old.get("roles", {}).get("main") and not pending):
                    print(tr("已有工作台记录不完整；请核对原项目记录，不会另建 owner。"))
                    continue
                print(tr("\n发现已有工作台：{name}（保留原负责人、模型、任务和布局）", name=project.name))
                if pending:
                    print(tr("上次启动尚未完成，将继续原先选择的角色；已启动角色不重复派工。"))
                    records = {item["role"]: item for item in pending["roles"]}
                else:
                    records = old["roles"]
                for role, record in records.items():
                    model = record.get("model") if pending else tr("原模型保持")
                    print(f"  {ui.role_label(role)} / {tr(LABELS.get(record['harness'], record['harness']))} / {model or tr('沿用已有设置')}")
                action = choose(tr("如何继续"), [tr("继续原工作台"), tr("更换项目"), tr("取消")])
                if action == 2:
                    continue
                if action == 3:
                    return None
                print(tr("\n[4/4] 恢复摘要"))
                print(tr("项目：{project}\n操作：继续原负责人和未完事项；保留任务、模型与现有窗口。", project=project))
                print(tr("宿主：{host}", host="Orca" if host == "orca" else "Herdr"))
                ready = dependency_summary(available, host)
                action = choose(tr("请选择"), [tr("启动（继续原工作台）"), tr("返回修改"), tr("取消")])
                if action == 2:
                    continue
                if action == 3 or not ready:
                    return None
                if pending:
                    arguments = pending["arguments"]
                    if not isinstance(arguments, list) or arguments[:2] != ["start", str(project)]:
                        raise ValueError(tr("待完成启动记录与当前项目不符"))
                    return Selection(arguments, False, ui_language=ui.language)
                arguments = ["start", str(project), "--session", old["session"]]
                if host == "orca":
                    arguments += ["--host", "orca"]
                return Selection(arguments, False, True, ui.language)

            host = select_workbench(available, host_choices.get(project))
            host_choices[project] = host
            if host == "orca" and not available.get("orca"):
                dependency_summary(available, host)
                return None
            print(tr("\n[2/4] 客户端组合与模型"))
            show_capabilities(available)
            options = []
            usable = []
            for label, _, roles in COMBINATIONS:
                missing = [tr(LABELS[kind]) for kind in dict.fromkeys(kind for _, kind in roles) if not available[kind]]
                usable.append(not missing)
                options.append(tr(label) + (tr("（缺少 {missing}，暂不可用）", missing=(", " if ui.language == "en" else "、").join(missing)) if missing else ""))
            if not any(usable):
                print(tr("当前组合均需要 Codex。请先安装缺失客户端并完成其原生登录，再运行 superaris。"))
                return None
            default = combo if usable[combo - 1] else usable.index(True) + 1
            while True:
                combo = choose(tr("客户端组合"), options, default)
                if usable[combo - 1]:
                    break
                print(tr("请先安装该组合缺少的客户端并完成原生登录，或选择本机可用组合。"))
            _, preset, roles = COMBINATIONS[combo - 1]
            chosen = {}
            for role, kind in roles:
                value = select_model(role, kind, models.get((role, kind)))
                models[(role, kind)] = value
                chosen[role] = value
            print(tr("\n[3/4] 分工与工作台"))
            layout(roles)
            name = ask(tr("工作台名称"), name)
            if task:
                print(tr("当前填写的任务：{task}", task=task))
                task_action = choose(tr("任务安排"), [tr("保留当前任务"), tr("重新填写"), tr("清空，进入后再给任务")])
                if task_action == 3:
                    task = ""
                elif task_action == 2:
                    task = ask(tr("新的任务（留空则进入后再给任务）"))
            else:
                task = ask(tr("本次任务（留空则进入后再给任务）"))
            print(tr("\n[4/4] 启动摘要"))
            print(tr("项目：{project}{created}", project=project, created=tr("（启动时创建）") if not project.exists() else ""))
            print(tr("工作台：SuperARIS · {name}", name=name))
            print(tr("宿主：{host}", host="Orca" if host == "orca" else "Herdr"))
            for role, kind in roles:
                scope = tr("项目统筹与验收（协作者目录除外）") if role == "main" else tr("{scope}（独占）", scope=f"outputs/{role}")
                print(f"  {ui.role_label(role)} / {tr(LABELS[kind])} / {chosen[role] or tr('沿用 CLI 配置')} → {scope}")
            print(tr("任务：{task}", task=task or tr("暂不安排，进入后再告诉主会话")))
            print(tr("将打开所选工作台，加载项目与 ARIS 技能，并接收协作者后续结果。"))
            if any(kind in {"claude", "agy"} for _, kind in roles):
                print(tr("CC/AGY 收到后续结果时会提示你查看。"))
            ready = dependency_summary(available, host)
            action = choose(tr("请选择"), [tr("启动"), tr("返回修改"), tr("取消")])
            if action == 2:
                continue
            if action == 3 or not ready:
                return None
            arguments = ["start", str(project), "--session", session_name(project), "--preset", preset, "--name", name]
            if host == "orca":
                arguments += ["--host", "orca"]
            waiting = "Read this project's role packet and selected ARIS skills, then wait for the user's concrete task. Do not start a research pipeline, workflow, model delegation or Goal."
            collaborator_waiting = "Read this project's role packet and selected ARIS skills, then wait for the main owner's scoped assignment. Do not execute the main task or edit project artifacts yet."
            arguments += ["--task", task or waiting]
            for role, _ in roles:
                arguments += ["--only-role", role]
                if chosen[role]:
                    arguments += ["--model", f"{role}={chosen[role]}"]
                if role != "main":
                    arguments += ["--write-scope", f"{role}=outputs/{role}", "--role-task", f"{role}={collaborator_waiting}"]
            return Selection(arguments, not project.exists(), ui_language=ui.language)
        except Back:
            print(tr("\n返回项目选择；此前未启动会话或写入项目。"))
        except (OSError, ValueError) as exc:
            print(tr("无法读取这个项目：{error}。请重新选择，或 q 取消。", error=exc))


def _blocked(project: Path, binary: str) -> tuple[object, list[tuple[str, dict]]]:
    from .client import Herdr, HerdrError, read_screen, verify_owner
    from .delivery import codex_input
    from .hosts import client_for_binding
    from .runtime import binding, save_binding
    from .state import launch_lock
    with launch_lock(project):
        current = binding(project)
        client = client_for_binding(current, project, binary, herdr_factory=Herdr)
        waiting = []
        for role, record in current.get("roles", {}).items():
            if not record.get("created"):
                continue
            try:
                live = verify_owner(client, record, project)
            except HerdrError:
                if current.get("host") == "orca":
                    raise
                continue
            # Pin the observed native process before handing the user the TUI.
            # A replaced process must not be accepted merely for sharing cwd.
            current["roles"][role] = live
            live.pop("startup_wait", None)
            if live["status"] == "blocked":
                live["startup_wait"] = "native_prompt"
            if (live["harness"] == "agy" or live.get("bootstrap_pending")
                    or current.get("host") == "orca" and live["status"] == "blocked"):
                view = read_screen(client, live["pane_id"])
                if live["harness"] == "agy" and all(value in view for value in (
                        "Do you trust the contents of this project?", "Yes, I trust this folder", "No, exit")):
                    live["startup_wait"] = "directory_trust"
                elif live.get("bootstrap_pending") and (
                        live["status"] not in {"idle", "done"} or codex_input(view) is None):
                    live["startup_wait"] = "input_not_ready"
            if live.get("startup_wait"):
                waiting.append((role, live))
        save_binding(project, current)
    return client, waiting


def _launch_orca(plan: dict, args) -> dict | None:
    """Orca's UI opener returns immediately; continue only on explicit readback."""
    from .client import HerdrError
    from .hosts import identity_present
    from .runtime import binding, save_binding, start
    from .receiver import ensure_receiver, stop as stop_receiver
    from .state import directory, launch_lock, write

    ui.set_language(getattr(args, "ui_language", ui.language))
    project = Path(plan["project"])
    print(tr("\n正在准备项目、ARIS 技能与所选角色…"), flush=True)
    with launch_lock(project):
        current = binding(project) or {"project": str(project), "session": plan["session"],
                                       "preset": plan["preset"], "host": "orca", "roles": {}}
        if getattr(args, "orca_bin", None):
            # A pending explicit launcher may be outside PATH. The first
            # read-only blocked check must use that same confirmed entry.
            current["orca_bin"] = args.orca_bin
        if not current.get("pending_start") and not args.wizard_resume_existing:
            current["pending_start"] = {"arguments": args.wizard_arguments,
                                        "roles": [role for role in plan["roles"] if role["active"]]}
        save_binding(project, current)
    args.wizard_attached = False

    def receive():
        if not identity_present(binding(project).get("roles", {}).get("main", {})):
            return None
        return stop_receiver(project) if args.no_receiver else ensure_receiver(project, args.herdr_bin)

    try:
        while True:
            client, waiting = _blocked(project, args.herdr_bin)
            if not waiting:
                try:
                    result = start(plan, args)
                except HerdrError as exc:
                    write(directory(project) / "startup-error.json", {"error": str(exc)})
                    client, waiting = _blocked(project, args.herdr_bin)
                    if not waiting:
                        raise
                else:
                    client, waiting = _blocked(project, args.herdr_bin)
                    if not waiting:
                        missing = [role["role"] for role in plan["roles"]
                                   if role["active"] and role["role"] not in result["roles"]]
                        if missing:
                            raise RuntimeError(tr("仍需准备角色：{roles}。原选择已保留，请安装相应客户端后继续。",
                                                  roles=", ".join(ui.role_label(role) for role in missing)))
                        result["receiver"] = receive()
                        completed(project)
                        return result
            receive()
            # _blocked verified the original handle and read its current screen.
            # Opening a GUI is not a detach or a successful prompt submission.
            client.open_ui(waiting[0][1]["pane_id"])
            args.wizard_attached = True
            print(tr("请在 Orca 中自行处理原生提示；处理后回到这里选择继续，原会话和选择保持不变。"), flush=True)
            try:
                action = choose(tr("如何继续"), [tr("已处理原生提示，继续"), tr("结束向导，保留当前会话")])
            except (Cancelled, Back, EOFError, KeyboardInterrupt):
                return None
            if action == 2:
                return None
            # No retry is made until a fresh original-owner/screen check above.
    except (OSError, ValueError, RuntimeError) as exc:
        write(directory(project) / "startup-error.json", {"error": str(exc)})
        raise


def launch(plan: dict, args) -> dict | None:
    """One startup worker progresses while the foreground TUI remains attached."""
    import threading
    from .client import HerdrError, notify
    from .hosts import client_for_binding, identity_present, selected_host
    from .runtime import attach, binding, save_binding, start
    from .receiver import ensure_receiver, stop as stop_receiver
    from .state import directory, launch_lock, write
    if selected_host(binding(Path(plan["project"])), plan.get("host")) == "orca":
        return _launch_orca(plan, args)
    ui.set_language(getattr(args, "ui_language", ui.language))
    project = Path(plan["project"])
    print(tr("\n正在准备项目、ARIS 技能与所选角色…"), flush=True)
    with launch_lock(project):
        current = binding(project) or {"project": str(project), "session": plan["session"],
                                       "preset": plan["preset"], "roles": {}}
        if not current.get("pending_start") and not args.wizard_resume_existing:
            current["pending_start"] = {"arguments": args.wizard_arguments,
                                        "roles": [role for role in plan["roles"] if role["active"]]}
            save_binding(project, current)
    stop_event, settled, show_ui, detached = threading.Event(), threading.Event(), threading.Event(), threading.Event()
    args.wizard_attached = False
    outcome = {}
    notified = set()

    def ensure_receiving():
        current = binding(project)
        if not identity_present(current.get("roles", {}).get("main", {})):
            return None
        return stop_receiver(project) if args.no_receiver else ensure_receiver(project, args.herdr_bin)

    def advance():
        try:
            while not stop_event.is_set():
                client, waiting = _blocked(project, args.herdr_bin)
                if waiting:
                    outcome["waiting"] = waiting
                    show_ui.set()
                    ensure_receiving()
                    if detached.is_set():
                        # The user may have resolved the native prompt while
                        # receiver setup was in flight. Decide from a fresh
                        # owner/UI check, not the pre-attach observation.
                        _, waiting = _blocked(project, args.herdr_bin)
                        if waiting:
                            break
                        continue
                    for role, record in waiting:
                        key = (role, record.get("startup_wait"))
                        if key not in notified:
                            notify(client, tr("SuperARIS 启动准备"),
                                   tr("请查看 {role} 窗格；原生提示由你处理，其他角色会继续准备。", role=ui.role_label(role)))
                            notified.add(key)
                    stop_event.wait(0.5)
                    continue
                try:
                    result = start(plan, args, stop_event=stop_event)
                except HerdrError as exc:
                    write(directory(project) / "startup-error.json", {"error": str(exc)})
                    _, waiting = _blocked(project, args.herdr_bin)
                    if not waiting:
                        raise
                    outcome["waiting"] = waiting
                    show_ui.set()
                    continue
                ensure_receiving()
                if stop_event.is_set():
                    break
                _, waiting = _blocked(project, args.herdr_bin)
                if waiting:
                    outcome["waiting"] = waiting
                    show_ui.set()
                    continue
                missing = [item["role"] for item in plan["roles"] if item["active"] and item["role"] not in result["roles"]]
                if missing:
                    raise RuntimeError(tr("仍需准备角色：{roles}。原选择已保留，请安装相应客户端后继续。", roles=", ".join(ui.role_label(role) for role in missing)))
                result["receiver"] = ensure_receiving()
                completed(project)
                outcome["result"] = result
                break
        except (OSError, ValueError, RuntimeError) as exc:
            outcome["error"] = exc
            write(directory(project) / "startup-error.json", {"error": str(exc)})
            try:
                from .client import Herdr
                client = client_for_binding(binding(project), project, args.herdr_bin, herdr_factory=Herdr)
                notify(client, tr("SuperARIS 启动未完成"),
                       tr("原会话和选择已保留。退出客户端后可查看启动错误并继续处理。"))
            except (OSError, ValueError, RuntimeError):
                pass
        finally:
            settled.set()
            show_ui.set()

    worker = threading.Thread(target=advance, name="superaris-startup")
    worker.start()
    attached = False
    normal_detach = False
    try:
        show_ui.wait()
        if not settled.is_set():
            waiting = outcome.get("waiting", [])
            print(tr("\n正在进入项目工作台；请自行处理原生提示。启动会在界面保持打开时继续。"), flush=True)
            if waiting:
                from .client import Herdr, verify_owner
                client = client_for_binding(binding(project), project, args.herdr_bin, herdr_factory=Herdr)
                target = verify_owner(client, waiting[0][1], project)
                client.json("agent", "focus", target["pane_id"])
            attached = True
            args.wizard_attached = True
            attach(project, args.herdr_bin)
            normal_detach = True
            detached.set()
    finally:
        if not normal_detach and not settled.is_set():
            stop_event.set()
        # No second start executor is left behind. In-flight native startup is
        # bounded by the existing timeout; runtime checks stop between roles.
        worker.join()
    if "error" in outcome:
        raise outcome["error"]
    if attached and "result" not in outcome:
        try:
            action = choose(tr("客户端仍在等待"), [tr("返回工作台处理"), tr("结束向导，保留当前会话")])
        except (Cancelled, Back, EOFError, KeyboardInterrupt):
            return None
        if action == 1:
            return launch(plan, args)
    return outcome.get("result")


def completed(project: Path) -> None:
    from .runtime import binding, save_binding
    from .state import launch_lock
    with launch_lock(project):
        current = binding(project)
        current.pop("pending_start", None)
        save_binding(project, current)
