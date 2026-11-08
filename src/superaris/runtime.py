"""Project-owned native sessions and generated launch records."""
from __future__ import annotations

from pathlib import Path
import os
import re
import shutil
import subprocess

from .client import Herdr, HerdrError, foreground, verify_owner
from .context import prepare_context
from .delivery import deliver
from .state import directory, launch_lock, read, write
from .dependencies import resolve_aris_repo


def binding(project: Path) -> dict:
    return read(directory(project) / "launch.json", {})


def save_binding(project: Path, value: dict) -> None:
    write(directory(project) / "launch.json", value)


def verify_caller(client: Herdr, pane: str | None, native: str | None) -> None:
    if not pane:
        return  # Explicit user-invoked launcher is not an agent claiming a managed pane.
    record = client.json("pane", "get", pane)["pane"]
    live = foreground(client.json("pane", "process-info", "--pane", pane)["process_info"])
    if Path(live["cwd"]) != Path.cwd().resolve():
        raise HerdrError("Caller effective cwd differs from the invoking directory; verify the explicit pane association")
    actual = (record.get("agent_session") or {}).get("value")
    if native and actual and native != actual:
        raise HerdrError("Caller native session mismatch")
    if not live.get("pid"):
        raise HerdrError("No caller foreground process evidence; inspect the explicit pane")


def _native_args(kind: str, project: Path, prompt: str | None, model: str | None) -> list[str]:
    args = []
    if model:
        args += ["--model", model]
    if kind == "codex":
        args += ["--cd", str(project)]
    elif kind == "agy" and prompt:
        args += ["--prompt-interactive", prompt]
        return args
    return args + ([prompt] if prompt else [])


def _agent_name(project: Path, role: str, agents: list[dict]) -> str:
    stem = re.sub(r"[^a-z0-9_-]", "-", project.name.lower()).strip("-") or "project"
    base = f"superaris-{role[:8]}-{stem[:10]}"[:30]
    names = {agent.get("name") for agent in agents}
    for number in range(100):
        name = base if number == 0 else f"{base[:28]}-{number}"
        if name not in names:
            return name
    raise HerdrError("No free live agent name; inspect the selected session")


def start(plan: dict, args, *, stop_event=None) -> dict:
    project = Path(plan["project"])
    client = Herdr(plan["session"], args.herdr_bin)
    with launch_lock(project):
        old = binding(project)
        if old and old["session"] != plan["session"]:
            raise ValueError(f"Project already bound to session {old['session']!r}; use that explicit session")
        aris_repo = resolve_aris_repo(getattr(args, "aris_repo", None) or os.environ.get("SUPERARIS_ARIS_REPO") or old.get("aris_repo"))
        client.ensure(directory(project) / "server.log", install=not args.no_install)
        verify_caller(client, args.caller_pane, args.caller_native_session)
        current = old or {"project": str(project), "session": plan["session"], "roles": {}, "preset": plan["preset"]}
        current["aris_repo"] = str(aris_repo)
        if args.owner and "main" not in current["roles"]:
            agent = client.json("agent", "get", args.owner)["agent"]
            candidate = {"pane_id": agent["pane_id"], "harness": agent["agent"],
                         "automation_owned": False, "created": False}
            current["roles"]["main"] = verify_owner(client, candidate, project)
            save_binding(project, current)
        if not current["roles"].get("main"):
            # Discover a single existing project owner by process/cwd, never by label alone.
            candidates = []
            for agent in client.snapshot().get("agents", []):
                try:
                    candidate = verify_owner(client, {"pane_id": agent["pane_id"], "harness": agent["agent"],
                                                      "automation_owned": False, "created": False}, project)
                except HerdrError:
                    continue
                candidates.append(candidate)
            if len(candidates) > 1:
                raise ValueError("Several live agents share this project; select the owner with --owner")
            if candidates:
                current["roles"]["main"] = candidates[0]
                save_binding(project, current)
        actions = []
        explicit_tasks = {value.split("=", 1)[0] for value in args.role_task}
        explicit_scopes = {value.split("=", 1)[0] for value in args.write_scope}
        selected_roles = [dict(item) for item in plan["roles"]]
        if current["roles"].get("main") and not any(item["role"] == "main" and item["active"] for item in selected_roles):
            selected_roles = [item for item in selected_roles if item["role"] != "main"]
            selected_roles.insert(0, {"role": "main", "harness": current["roles"]["main"]["harness"],
                                     "active": True, "model": None, "task": plan["task"], "write_scope": str(project)})
        for item in selected_roles:
            previous = current["roles"].get(item["role"], {}).get("inputs", {})
            if item["role"] not in explicit_tasks and (item["role"] != "main" or args.task is None):
                item["task"] = previous.get("task", item["task"])
            if item["role"] not in explicit_scopes:
                item["write_scope"] = previous.get("write_scope", item["write_scope"])
            item["skills"] = args.skill or previous.get("skills", plan["skills"])
            item["recovery"] = [] if args.clear_recovery else args.recovery or previous.get("recovery", [])
        # An inactive existing writer still owns its recorded scope. Only an
        # explicit handoff can release it; another preset is not a handoff.
        occupied = {name: {"role": name, "write_scope": record.get("inputs", {}).get("write_scope", str(project))}
                    for name, record in current["roles"].items() if name != "main"}
        occupied.update({item["role"]: item for item in selected_roles if item["active"] and item["role"] != "main"})
        collaborator_scopes = list(occupied.values())
        for item in plan["roles"]:
            if not Path(item["write_scope"]).is_relative_to(project):
                raise ValueError("Role write scope must be inside the selected project")
        for index, item in enumerate(collaborator_scopes):
            for other in collaborator_scopes[index + 1:]:
                first, second = Path(item["write_scope"]), Path(other["write_scope"])
                if first.is_relative_to(second) or second.is_relative_to(first):
                    raise ValueError("Collaborator write scopes overlap; assign disjoint directories or worktrees")
        for selected in selected_roles:
            if stop_event is not None and stop_event.is_set():
                actions.append({"action": "startup_paused"})
                break
            if not selected["active"]:
                continue
            role, kind = selected["role"], selected["harness"]
            existing = current["roles"].get(role)
            inputs = {"task": selected["task"], "skills": selected["skills"], "recovery": selected["recovery"],
                      "write_scope": selected["write_scope"]}
            if role == "main" and collaborator_scopes:
                inputs["excluded_scopes"] = [item["write_scope"] for item in collaborator_scopes]
            if existing:
                live = verify_owner(client, existing, project)
                current["roles"][role] = live
                if existing.get("delivery", {}).get("phase") in {"attempting", "unknown"}:
                    actions.append({"role": role, "action": "pending_unknown", "delivery": existing["delivery"]})
                    current["roles"][role] = live
                    continue
                if existing.get("inputs") != inputs:
                    context = prepare_context(project, role, live["harness"], selected["task"], selected["skills"],
                                              selected["recovery"], aris_repo, [selected["write_scope"]])
                    _exclude_writers(context, role, collaborator_scopes)
                    live.update(context=context, inputs=inputs, pending_context=context["packet"],
                                delivery={"phase": "prepared", "packet": context["packet"]})
                    current["roles"][role] = live
                    save_binding(project, current)
                    delivery = _submit_context(client, project, current, role)
                    actions.append({"role": role, "action": "context_updated", "packet": context["packet"], **delivery})
                else:
                    if live.get("delivery", {}).get("phase") == "prepared" or (
                            live.get("bootstrap_pending") and live.get("delivery", {}).get("phase") == "visible_notice"):
                        initial = bool(live.pop("bootstrap_pending", False))
                        save_binding(project, current)
                        delivery = _submit_context(client, project, current, role, initial=initial)
                        actions.append({"role": role, "action": "context_delivery", **delivery})
                    else:
                        actions.append({"role": role, "action": "reused", "pane_id": existing["pane_id"],
                                        "pending_context": existing.get("pending_context"), "delivery": existing.get("delivery")})
                current["roles"][role] = live
                continue
            if not shutil.which(kind):
                if role == "main":
                    raise ValueError(f"Selected main harness is missing: {kind}; complete its native installation/login")
                actions.append({"role": role, "action": "unavailable", "reason": f"missing {kind} CLI"})
                continue
            Path(selected["write_scope"]).mkdir(parents=True, exist_ok=True)
            context = prepare_context(project, role, kind, selected["task"], selected["skills"],
                                      selected["recovery"], aris_repo, [selected["write_scope"]])
            _exclude_writers(context, role, collaborator_scopes)
            ui_language = current.get("ui_language")
            if ui_language in {"zh", "en"}:
                from .ui import tr
                role_title = tr({"main": "主会话", "engineer": "工程", "writer": "写作"}.get(role, role), lang=ui_language)
                workbench_title = tr("工作台", lang=ui_language)
            else:
                role_title, workbench_title = role, "Workbench"
            if "workspace_id" not in current:
                display_name = f"SuperARIS · {args.name}" if getattr(args, "name", None) else f"SuperARIS {project.name}"
                created = client.json("workspace", "create", "--cwd", str(project), "--label", display_name,
                                      "--env", f"ARIS_REPO={aris_repo}", "--no-focus")
                current["workspace_id"] = created["workspace"]["workspace_id"]
                tab = created["tab"]["tab_id"]
                current["tab_id"] = tab
                client.json("tab", "rename", tab, f"SuperARIS · {workbench_title}")
                pane = created["root_pane"]["pane_id"]
            else:
                anchor = next(iter(current["roles"].values()), None)
                if anchor and anchor.get("created"):
                    # A new team gets a left owner and a right collaborator
                    # column. Keep an adopted user's original topology intact.
                    engineer = current["roles"].get("engineer")
                    below_engineer = role == "writer" and engineer and engineer.get("created")
                    split_from = engineer["pane_id"] if below_engineer else anchor["pane_id"]
                    direction = "down" if below_engineer else "right"
                    created = client.json("pane", "split", split_from, "--direction", direction, "--cwd", str(project), "--no-focus")
                    pane = created["pane"]["pane_id"]
                else:
                    created = client.json("tab", "create", "--workspace", current["workspace_id"], "--cwd", str(project), "--label", f"SuperARIS · {role_title}", "--no-focus")
                    pane = created["root_pane"]["pane_id"]
            harness_label = {"claude": "Claude Code", "codex": "Codex", "agy": "Antigravity"}[kind]
            client.json("pane", "rename", pane, f"{role_title} · {harness_label}")
            name = _agent_name(project, role, client.snapshot().get("agents", []))
            record = {"pane_id": pane, "harness": kind, "name": name, "created": True,
                      "automation_owned": args.automation_owned, "context": context,
                      "requested_model": selected["model"], "status": "starting", "inputs": inputs,
                      "bootstrap_pending": kind == "codex",
                      "pending_context": context["packet"], "delivery": {"phase": "prepared", "packet": context["packet"]}}
            current["roles"][role] = record
            save_binding(project, current)  # Retain delivery target before starting; never duplicate after timeout.
            try:
                if kind != "codex":
                    record["delivery"]["phase"] = "attempting"
                    save_binding(project, current)
                client.json("agent", "start", name, "--kind", kind, "--pane", pane, "--timeout", "120000", "--",
                            *_native_args(kind, project, None if kind == "codex" else context["prompt"], selected["model"]), timeout=125)
                current["roles"][role] = verify_owner(client, record, project)
                if kind == "codex":
                    # Separate startup readiness from a potentially long first task.
                    # The brand-new pane has no earlier user input; still inspect its surface.
                    current["roles"][role]["bootstrap_pending"] = False
                    save_binding(project, current)
                    if stop_event is not None and stop_event.is_set():
                        current["roles"][role]["bootstrap_pending"] = True
                        save_binding(project, current)
                        continue
                    submitted = _submit_context(client, project, current, role, initial=True)
                    current["roles"][role]["initial_delivery"] = submitted
                else:
                    current["roles"][role]["delivery"]["phase"] = "submitted"
            except HerdrError:
                # The CLI may already have launched. Preserve the target and report the real failure.
                if current["roles"][role]["delivery"]["phase"] == "attempting":
                    current["roles"][role]["delivery"]["phase"] = "unknown"
                save_binding(project, current)
                raise
            save_binding(project, current)
            actions.append({"role": role, "action": "started", "pane_id": pane, "packet": context["packet"]})
        save_binding(project, current)
    return {"mode": "running", "project": str(project), "session": client.session,
            "actions": actions, "roles": current["roles"], "acceptance": "not_evaluated"}


def _exclude_writers(context: dict, role: str, others: list[dict]) -> None:
    if role == "main" and others:
        with Path(context["packet"]).open("a") as packet:
            packet.write("\n## Other active writers (excluded from your write scope)\n\n")
            for other in others:
                packet.write(f"- {other['role']} exclusively owns `{other['write_scope']}`. Delegate or obtain handoff before writing there.\n")


def _submit_context(client, project, current, role, initial=False):
    record = current["roles"][role]
    record["delivery"]["phase"] = "attempting"
    save_binding(project, current)
    try:
        receipt = deliver(client, project, {**record, "automation_owned": True, "_initial_bootstrap": True} if initial else record,
                          record["context"]["prompt"])
    except (HerdrError, OSError) as exc:
        record["delivery"].update(phase="unknown", error=str(exc))
        save_binding(project, current)
        raise
    record["delivery"].update(phase=receipt["delivery"], receipt=receipt)
    if receipt.get("revoke_automation"):
        record["automation_owned"] = False
        record["bootstrap_pending"] = False
    elif initial and receipt["delivery"] == "visible_notice":
        record["bootstrap_pending"] = True
    save_binding(project, current)
    return receipt


def control(project: Path, role: str, mode: str, binary: str) -> dict:
    with launch_lock(project):
        current = binding(project)
        if role not in current.get("roles", {}):
            raise ValueError("Unknown project role")
        record = verify_owner(Herdr(current["session"], binary), current["roles"][role], project)
        record["automation_owned"] = mode == "automation"
        if mode == "human":
            record["bootstrap_pending"] = False
        current["roles"][role] = record
        save_binding(project, current)
        return {"role": role, "mode": mode, "pane_id": record["pane_id"]}


def resolve_delivery(project: Path, args) -> dict:
    from .tasks import local
    evidence = local(project, args.evidence)
    if not evidence.is_file():
        raise ValueError("Inspect actual input/receipt and provide its existing evidence file")
    with launch_lock(project):
        if args.handle:
            path = directory(project) / "bridge.json"
            state = read(path, {})
            attempt = state.get("attempts", {}).pop(args.handle, None)
            if not attempt:
                raise ValueError("No unknown bridge delivery for this handle")
            state.setdefault("resolutions", []).append({**attempt, "resolution": args.resolution, "evidence": str(evidence)})
            if args.resolution == "received":
                state.setdefault("delivered", {})[args.handle] = {"signal": attempt["signal"], "pane_id": attempt["pane_id"], "delivery": "visible_notice"}
                if "observed" in attempt["signal"]:
                    from .tasks import handle_path
                    pointer = handle_path(project, attempt["signal"]["id"])
                    handle = read(pointer)
                    if handle:
                        handle.update(attempt["signal"]["observed"], last_delivery={"delivery": "received", "evidence": str(evidence)})
                        write(pointer, handle)
            write(path, state)
            return {"handle": args.handle, "resolution": args.resolution, "evidence": str(evidence)}
        current = binding(project)
        role = current.get("roles", {}).get(args.role)
        if not role or not role.get("delivery"):
            raise ValueError("No role context delivery to resolve")
        role["delivery"].update(phase="received" if args.resolution == "received" else "prepared", evidence=str(evidence))
        if args.resolution == "received":
            role["pending_context"] = None
        save_binding(project, current)
        return role["delivery"]


def attach(project: Path, binary: str = "herdr") -> int:
    info = binding(project)
    if not info:
        raise ValueError("No workbench binding for this project")
    # Receiving was established independently by start(). Detaching this TUI
    # does not stop the original owner, worker or project receiver component.
    return subprocess.call([binary, "--session", info["session"]])
