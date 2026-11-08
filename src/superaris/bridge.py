"""Bounded foreground receipt bridge for one explicitly bound project.

Native events wake local reconciliation; they never establish task acceptance.
No daemon or model polling is involved, and all input uses draft-safe delivery.
Inspect unknown sends, then use ``aris resolve-delivery PROJECT --handle ID
--resolution received|not-delivered --evidence EXISTING_FILE``; never clear them
by retrying input blindly.
"""
from __future__ import annotations

import math
from pathlib import Path
import time

from .client import Herdr, HerdrError, verify_owner
from .delivery import deliver
from .runtime import binding
from .state import directory, read, write


def _pending_signals(project: Path, client: Herdr) -> list[dict]:
    # tasks may land independently of the transport. Resolve only at use time.
    from .tasks import pending_signals
    signals = pending_signals(project, client)
    for name, role in binding(project).get("roles", {}).items():
        delivery = role.get("delivery", {})
        context = role.get("context", {})
        packet = context.get("packet")
        if (role.get("automation_owned") and delivery.get("phase") == "visible_notice"
                and not delivery.get("receipt", {}).get("revoke_automation") and packet and context.get("prompt")):
            signals.append({"id": f"context-{name}-{Path(packet).parent.name}",
                            "reason": "context awaiting safe input", "prompt": context["prompt"],
                            "owner_role": name, "context_role": name, "packet": packet})
    return signals


def _mark_notified(project: Path, signal: dict, receipt: dict) -> None:
    if "observed" in signal:
        from .tasks import mark_notified
        mark_notified(project, signal, receipt)


def _signal_current(project: Path, signal: dict) -> bool:
    """Cached notices cannot outlive their original task or context packet."""
    if signal.get("context_role"):
        role = binding(project).get("roles", {}).get(signal["context_role"], {})
        return (role.get("context", {}).get("packet") == signal.get("packet")
                and role.get("delivery", {}).get("phase") in {"visible_notice", "prepared"})
    if "observed" in signal:
        from .tasks import handle_path
        return bool(read(handle_path(project, str(signal["id"])), {}).get("active"))
    return True


def _event_type(event: dict) -> str | None:
    """Read native stream envelopes, including the terminal events_lost error."""
    if event.get("code") == "events_lost":
        return "events_lost"
    for key in ("result", "event", "params", "error", "data"):
        value = event.get(key)
        if isinstance(value, dict):
            found = _event_type(value)
            if found:
                return found
    for key in ("type", "event", "method"):
        value = event.get(key)
        if value in ("pane.agent_status_changed", "pane_agent_status_changed"):
            return "pane.agent_status_changed"
        if value == "events_lost":
            return value
    return None


def listen(project: Path, binary: str = "herdr", duration: float | None = 300, interval: float = 5,
           stop_event=None) -> dict:
    """Only one foreground/attached receiver may deliver for this project."""
    import fcntl
    project = Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    root = directory(project)
    root.mkdir(parents=True, exist_ok=True)
    with (root / "listen.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("Another receiver owns this project; stop or reuse that receiver before listening again") from exc
        try:
            return _listen(project, binary, duration, interval, stop_event)
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def _listen(project: Path, binary: str, duration: float | None, interval: float, stop_event) -> dict:
    """Listen during this foreground invocation and reconcile registered signals.

    Idle socket reads expire at interval boundaries so local artifact/task
    updates are checked even when Herdr produces no native events. A successful
    visible notice counts as delivery, never scientific acceptance.
    """
    project = Path(project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError(f"Project directory does not exist: {project}")
    if duration is None and stop_event is None:
        raise ValueError("A receiver without a duration requires the attached client's stop event")
    if duration is not None and (not math.isfinite(duration) or duration < 0) or not math.isfinite(interval) or interval <= 0:
        raise ValueError("duration must be finite and nonnegative; interval must be finite and positive")
    bound = binding(project)
    if not bound.get("session") or not bound.get("roles", {}).get("main"):
        raise ValueError("No bound main owner for this project; start or bind the project first")
    client = Herdr(bound["session"], binary)
    state_path = directory(project) / "bridge.json"
    state = read(state_path, {"delivered": {}})
    delivered = state.setdefault("delivered", {})
    attempts = state.setdefault("attempts", {})
    deferred = state.setdefault("deferred", {})
    deadline = math.inf if duration is None else time.monotonic() + duration
    result = {"project": str(project), "session": bound["session"], "reason": "duration_elapsed",
              "deliveries": [], "events": 0, "reconciliations": 0, "reconnects": 0}

    def stopped() -> bool:
        if stop_event is not None and stop_event.is_set():
            result["reason"] = "stopped"
            return True
        return False

    def reconcile() -> list[dict]:
        nonlocal bound
        current = binding(project)
        if current.get("session") != client.session:
            raise HerdrError("Project binding changed; listener stopped without transferring ownership")
        roles = current.get("roles", {})
        if not roles.get("main"):
            raise HerdrError("Project no longer has a main owner")
        snapshot = client.snapshot()
        panes = {agent.get("pane_id") for agent in snapshot.get("agents", [])}
        if roles["main"].get("pane_id") not in panes:
            raise HerdrError("Bound main owner is absent from the current server snapshot")
        verify_owner(client, roles["main"], project)
        bound = current
        result["reconciliations"] += 1
        subscriptions = []
        for name, role in roles.items():
            if role.get("pane_id") not in panes:
                continue
            if name != "main":
                try:
                    verify_owner(client, role, project)
                except HerdrError:
                    continue
            subscriptions.append({"type": "pane.agent_status_changed", "pane_id": role["pane_id"]})
        return subscriptions

    def check_signals() -> bool:
        nonlocal bound
        changed = False
        for identifier, signal in list(deferred.items()):
            owner = bound["roles"].get(signal.get("owner_role") or "main", {})
            if not owner.get("automation_owned") or owner.get("harness") != "codex" or not _signal_current(project, signal):
                del deferred[identifier]
                changed = True
        if changed:
            write(state_path, state)
        signals = dict(deferred)
        signals.update({str(signal["id"]): signal for signal in _pending_signals(project, client)})
        for signal_id, signal in signals.items():
            if stopped():
                return False
            if not _signal_current(project, signal):
                if deferred.pop(signal_id, None) is not None:
                    write(state_path, state)
                continue
            if signal_id in attempts:
                result.update(reason="unknown_requires_inspection", pending_unknown=signal_id,
                              attempt=attempts[signal_id],
                              error="An earlier delivery outcome is unknown. Inspect the actual owner input/receipt before explicitly clearing this attempt; no input was resent.")
                return False
            role_name = signal.get("owner_role") or "main"
            role = bound["roles"].get(role_name)
            if role is None:
                # An explicit unbound owner must not silently become main.
                result.setdefault("pending", []).append({"id": signal_id, "reason": f"Unbound owner role: {role_name}"})
                continue
            previous = delivered.get(signal_id, {})
            automation = role.get("automation_owned") and role.get("harness") == "codex"
            if signal.get("context_role") and not previous and automation:
                # Runtime has already displayed this context's notice.
                previous = {"signal": signal, "pane_id": role["pane_id"], "delivery": "visible_notice"}
                delivered[signal_id] = previous
                deferred[signal_id] = signal
                write(state_path, state)
            if previous.get("signal") == signal and previous.get("pane_id") == role["pane_id"]:
                # Also recover a crash/failure between successful bridge persistence
                # and updating the original transport handle's observed fields.
                _mark_notified(project, signal, {"delivery": previous["delivery"], "pane_id": previous["pane_id"]})
                if signal_id not in deferred or not automation:
                    continue
                if verify_owner(client, role, project)["status"] not in {"idle", "done"}:
                    continue
            # Re-read original state immediately before initiating delivery;
            # fresh signals can also become obsolete during reconciliation.
            if not _signal_current(project, signal):
                if deferred.pop(signal_id, None) is not None:
                    write(state_path, state)
                continue
            attempts[signal_id] = {"signal": dict(signal), "pane_id": role["pane_id"], "status": "attempted"}
            write(state_path, state)
            try:
                receipt = deliver(client, project, role, signal["prompt"])
            except (HerdrError, OSError) as exc:
                # Unknown send outcomes require reconciliation, never an automatic
                # second input submission in this invocation.
                attempts[signal_id].update(status="unknown", error=str(exc))
                write(state_path, state)
                result.update(reason="unknown_requires_inspection", error=str(exc), pending_unknown=signal_id)
                return False
            if receipt.get("delivery") not in {"submitted", "visible_notice"}:
                attempts[signal_id].update(status="unknown", receipt=receipt)
                write(state_path, state)
                result.update(reason="unknown_requires_inspection", pending_unknown=signal_id)
                return False
            if receipt.get("revoke_automation"):
                from .runtime import control
                control(project, role_name, "human", binary)
                bound = binding(project)
                role = bound["roles"][role_name]
                automation = False
                for identifier, item in list(deferred.items()):
                    if (item.get("owner_role") or "main") == role_name:
                        del deferred[identifier]
            if receipt["delivery"] == "visible_notice" and automation:
                deferred[signal_id] = dict(signal)
            else:
                deferred.pop(signal_id, None)
            delivered[signal_id] = {"signal": dict(signal), "pane_id": role["pane_id"],
                                    "delivery": receipt["delivery"]}
            del attempts[signal_id]
            write(state_path, state)
            if signal.get("context_role") and receipt["delivery"] == "submitted":
                from .runtime import save_binding
                from .state import launch_lock
                with launch_lock(project):
                    current = binding(project)
                    record = current.get("roles", {}).get(signal["context_role"], {})
                    if record.get("pane_id") == role["pane_id"] and record.get("context", {}).get("packet") == signal["packet"]:
                        record.setdefault("delivery", {}).update(phase="submitted", receipt=receipt)
                        save_binding(project, current)
                        bound = current
            _mark_notified(project, signal, receipt)
            result["deliveries"].append({"id": signal_id, **receipt})
        return True

    first = True
    while first or time.monotonic() < deadline:
        first = False
        if stopped():
            break
        try:
            subscriptions = reconcile()
        except (HerdrError, OSError) as exc:
            result.update(reason="owner_or_server_unavailable", error=str(exc))
            break
        if not check_signals():
            break
        if stopped():
            break
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        stream = client.events(subscriptions, timeout=min(interval, remaining))
        reconnect = False
        try:
            for event in stream:
                if stopped():
                    return result
                event_type = _event_type(event)
                if event_type == "events_lost":
                    reconnect = True
                    break
                if time.monotonic() >= deadline:
                    break
                if event_type == "pane.agent_status_changed":
                    result["events"] += 1
                    reconcile()
                    if not check_signals():
                        return result
                if time.monotonic() >= deadline:
                    break
        except (HerdrError, OSError, ValueError) as exc:
            # Includes events_lost surfaced as HerdrError by the raw client.
            reconnect = True
            result["last_transport_error"] = str(exc)
        finally:
            close = getattr(stream, "close", None)
            if close is not None:
                close()
        if stopped():
            break
        if reconnect:
            result["reconnects"] += 1
            try:
                reconcile()
            except (HerdrError, OSError) as exc:
                result.update(reason="owner_or_server_unavailable", error=str(exc))
                break
            # Back off disconnected streams without starting a model or daemon.
            delay = max(0, min(interval, deadline - time.monotonic()))
            if stop_event is None:
                time.sleep(delay)
            else:
                stop_event.wait(delay)
                if stopped():
                    break
    return result
