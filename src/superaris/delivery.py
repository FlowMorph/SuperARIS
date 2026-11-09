"""Conservative input delivery: human panes receive a visible notice by default."""
from pathlib import Path
import re

from .client import Herdr, HerdrError, verify_owner, read_screen, send_prompt, notify


def codex_input(text: str) -> str | None:
    clean = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    prompts = [line.strip()[1:].strip() for line in clean.splitlines() if line.lstrip().startswith("›")]
    return prompts[-1] if prompts else None


def empty_codex_input(text: str) -> bool:
    """Only the actual empty Codex placeholder tested by this adapter is eligible."""
    return codex_input(text) in {"", "Ask Codex to do anything"}


def deliver(client: Herdr, project: Path, role: dict, prompt: str) -> dict:
    live = verify_owner(client, role, project)
    from .runtime import binding
    latest = binding(project).get("roles", {})
    persisted = next((record for record in latest.values() if record.get("pane_id") == live["pane_id"]), None)
    # Honor a handoff that happened after the receiver's earlier snapshot.
    automation = role.get("automation_owned") and (role.get("_initial_bootstrap") or persisted is None or persisted.get("automation_owned"))
    revoke = False
    if automation and live["harness"] == "codex" and live["status"] in {"idle", "done"}:
        view = read_screen(client, live["pane_id"])
        if empty_codex_input(view):
            # Recheck the occupant/status after reading. This is a dedicated automation
            # session, not a guarantee against a human concurrently typing after the read.
            second = verify_owner(client, live, project)
            if second["status"] in {"idle", "done"}:
                native_receipt = send_prompt(client, second["pane_id"], prompt)
                receipt = {"delivery": "submitted", "pane_id": second["pane_id"], "acceptance": "not_evaluated"}
                if getattr(client, "host", None) == "orca":
                    receipt["native_receipt"] = native_receipt
                return receipt
        else:
            # A startup splash without a composer is not a human draft.
            # Wait for the known input surface; never type into the splash.
            revoke = codex_input(view) is not None
    ui_language = binding(project).get("ui_language")
    if ui_language in {"zh", "en"}:
        from .ui import tr
        title = tr("ARIS 工作包已准备", lang=ui_language)
    else:
        title = "ARIS work packet ready"
    # Only the notification chrome follows UI language. Its original packet
    # body and native delivery/unknown semantics stay unchanged.
    notice = notify(client, title, prompt)
    receipt = {"delivery": "visible_notice", "pane_id": live["pane_id"],
            "revoke_automation": revoke,
            "reason": "Human-owned input, active/unknown state, or an unverified input surface; no keys sent",
            "acceptance": "not_evaluated"}
    if getattr(client, "host", None) == "orca":
        receipt["notice"] = notice
    return receipt
