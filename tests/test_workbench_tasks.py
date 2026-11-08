"""Durable workbench signals point to original evidence without accepting it."""

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from superaris import tasks


ROOT = Path(__file__).resolve().parents[1]
from tests.support import CLI
ARIS = CLI


def invoke(command, project, *options):
    return subprocess.run(
        [*ARIS, command, str(project), *map(str, options)],
        capture_output=True, text=True, timeout=20, check=False,
    )


@pytest.fixture
def project(tmp_path):
    project = tmp_path / "project"
    metadata = project / ".aris" / "workbench"
    metadata.mkdir(parents=True)
    (metadata / "launch.json").write_text(json.dumps({
        "project": str(project), "session": "isolated-test",
        "roles": {"main": {"pane_id": "w1:p1", "harness": "codex"}},
    }))
    (project / "CURRENT.md").write_text("Human task record; acceptance is still pending.\n")
    return project


def watch(project, *options, query="original worker status job-7"):
    result = invoke(
        "watch", project, "--id", "analysis", "--record", "CURRENT.md",
        "--deliverable", "result.txt", "--wait-for", "actual author output",
        "--query", query, "--next", "Read the output and apply the original reviewer gate.",
        *options,
    )
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def report(project, outcome="completed", message="Author output is ready."):
    result = invoke("report", project, "--id", "analysis", "--outcome", outcome, "--message", message)
    assert result.returncode == 0, result.stderr
    return json.loads(result.stdout)


def test_fresh_process_recovers_pending_report_and_actual_deliverable(project):
    watch(project)
    assert tasks.pending_signals(project) == []
    (project / "result.txt").write_text("Author artifact, still awaiting its existing gate.\n")
    reported = report(project)
    # Re-import through another process to exercise recovery from durable state.
    result = subprocess.run(
        [sys.executable, "-c",
         "import json,sys; from pathlib import Path; from superaris.tasks import pending_signals; "
         "print(json.dumps(pending_signals(Path(sys.argv[1]))))", str(project)],
        cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
    )
    assert result.returncode == 0, result.stderr
    signal, = json.loads(result.stdout)
    assert signal["observed"]["reports_seen"] == [reported["report"]]
    assert str(project / "result.txt") in signal["observed"]["paths"]
    assert str(project / "CURRENT.md") in signal["prompt"]
    assert reported["acceptance"] == "not_evaluated"
    assert json.loads(Path(reported["report"]).read_text())["acceptance"] == "not_evaluated"
    assert (project / "CURRENT.md").read_text() == "Human task record; acceptance is still pending.\n"


def test_notification_dedup_retains_reports_and_detects_later_reply(project):
    watch(project)
    first = report(project)
    original_bytes = Path(first["report"]).read_bytes()
    signal, = tasks.pending_signals(project)
    # Reading pending evidence is not delivery and does not consume it.
    assert tasks.pending_signals(project) == [signal]
    tasks.mark_notified(project, signal, {"delivery": "visible_notice"})
    assert tasks.pending_signals(project) == []
    second = report(project, "reply", "Additional explanation after the owner's question.")
    signal, = tasks.pending_signals(project)
    assert signal["observed"]["reports_seen"] == [first["report"], second["report"]]
    assert Path(first["report"]).read_bytes() == original_bytes
    assert Path(second["report"]).is_file()
    duplicate = invoke(
        "watch", project, "--id", "analysis", "--wait-for", "something else",
        "--query", "replacement", "--next", "replacement",
    )
    assert duplicate.returncode != 0
    assert "already registered" in duplicate.stderr
    assert Path(first["report"]).read_bytes() == original_bytes
    assert tasks.pending_signals(project) == [signal]


def test_human_changes_to_registered_original_file_renotify_after_mark(project):
    watch(project, "--watch-file", "CURRENT.md")
    current = project / "CURRENT.md"
    current.write_text("Human updated the original task and added a precise next step.\n")
    signal, = tasks.pending_signals(project)
    assert str(current) in signal["prompt"]
    assert signal["observed"]["reports_seen"] == []
    tasks.mark_notified(project, signal, {"delivery": "visible_notice"})
    assert tasks.pending_signals(project) == []
    current.write_text("Human made a second, independent task correction; reread it.\n")
    second, = tasks.pending_signals(project)
    assert second["observed"]["paths"][str(current)] != signal["observed"]["paths"][str(current)]
    assert current.read_text() == "Human made a second, independent task correction; reread it.\n"


def test_original_query_is_literal_pointer_and_never_executed(project, monkeypatch):
    marker = project / "query-must-not-run"
    query = f"touch '{marker}'; $(touch '{marker}')"
    watch(project, query=query)
    report(project)

    def forbidden(*args, **kwargs):
        pytest.fail("reconciling a stored query must not execute a subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    signal, = tasks.pending_signals(project)
    assert query in signal["prompt"]
    assert not marker.exists()


def test_acknowledgement_requires_actual_receipt_and_preserves_report(project):
    watch(project)
    reported = report(project)
    missing = invoke("acknowledge", project, "--id", "analysis", "--evidence", "missing.md")
    assert missing.returncode != 0
    assert tasks.pending_signals(project)
    receipt = project / "receipt.md"
    receipt.write_text("Checked the actual file; the original review remains pending.\n")
    result = invoke("acknowledge", project, "--id", "analysis", "--evidence", "receipt.md")
    assert result.returncode == 0, result.stderr
    handle = json.loads(result.stdout)
    assert handle["active"] is False
    assert handle["receipt"] == str(receipt)
    assert tasks.pending_signals(project) == []
    assert Path(reported["report"]).is_file()
    assert json.loads(Path(reported["report"]).read_text())["acceptance"] == "not_evaluated"


def test_memory_append_keeps_current_human_content_and_rejects_stale_read(project):
    memory = project / "CURRENT.md"
    stale_mtime = memory.stat().st_mtime_ns
    human_text = memory.read_text() + "Human correction made after the agent read the file.\n"
    memory.write_text(human_text)
    os.utime(memory, ns=(stale_mtime + 1_000_000_000, stale_mtime + 1_000_000_000))
    options = ["--file", "CURRENT.md", "--kind", "decision", "--scope", "project",
               "--source", "receipt.md", "--text", "Retain the verified result for the next step."]
    result = invoke("remember", project, *options, "--expected-mtime-ns", stale_mtime)
    assert result.returncode != 0
    assert "changed since read" in result.stderr
    assert memory.read_text() == human_text
    current_mtime = memory.stat().st_mtime_ns
    result = invoke("remember", project, *options, "--expected-mtime-ns", current_mtime)
    assert result.returncode == 0, result.stderr
    assert memory.read_text().startswith(human_text)
    assert memory.read_text().count("Retain the verified result for the next step.") == 1
    assert json.loads(result.stdout)["file"] == str(memory)


def test_memory_does_not_create_implicit_new_ledger(project):
    result = invoke(
        "remember", project, "--file", "new-ledger.md", "--kind", "handoff",
        "--scope", "project", "--source", "CURRENT.md", "--text", "A handoff.",
    )
    assert result.returncode != 0
    assert "existing authoritative memory file" in result.stderr
    assert not (project / "new-ledger.md").exists()


@pytest.mark.parametrize("command,options", [
    ("watch", ["--id", "outside", "--deliverable", "../outside.txt", "--wait-for", "output", "--query", "status", "--next", "review"]),
    ("acknowledge", ["--id", "analysis", "--evidence", "../outside.txt"]),
    ("remember", ["--file", "../outside.txt", "--kind", "correction", "--scope", "project", "--source", "human", "--text", "unsafe append"]),
])
def test_task_and_memory_paths_cannot_escape_project(project, command, options):
    outside = project.parent / "outside.txt"
    outside.write_text("Unrelated file must remain unchanged.\n")
    result = invoke(command, project, *options)
    assert result.returncode != 0
    assert "outside selected project" in result.stderr.lower()
    assert "Traceback" not in result.stderr
    assert outside.read_text() == "Unrelated file must remain unchanged.\n"


def test_registered_file_symlink_cannot_target_unrelated_project(project):
    outside = project.parent / "outside.txt"
    outside.write_text("Other owner data.\n")
    (project / "linked.txt").symlink_to(outside)
    result = invoke(
        "watch", project, "--id", "outside", "--watch-file", "linked.txt",
        "--wait-for", "data", "--query", "status", "--next", "review",
    )
    assert result.returncode != 0
    assert "outside selected project" in result.stderr.lower()
    assert not (project / ".aris" / "workbench" / "handles" / "outside.json").exists()


class WorkerClient:
    """Exercise real owner verification with a controllable observed worker."""

    def __init__(self, project, status="idle"):
        self.project = project
        self.status = status
        self.pid = 2345

    def json(self, *args):
        if args == ("agent", "get", "w1:p2"):
            return {"agent": {"pane_id": "w1:p2", "agent": "codex", "agent_status": self.status}}
        assert args == ("pane", "process-info", "--pane", "w1:p2")
        return {"process_info": {"pane_id": "w1:p2", "foreground_processes": [{
            "argv": ["codex", "--cd", str(self.project)], "cwd": str(self.project.parent), "pid": self.pid,
        }]}}


def register_worker(project, status="idle"):
    launch = project / ".aris/workbench/launch.json"
    binding = json.loads(launch.read_text())
    binding["roles"]["engineer"] = {"pane_id": "w1:p2", "harness": "codex", "pid": 2345}
    launch.write_text(json.dumps(binding))
    watch(project, "--worker-role", "engineer")
    return WorkerClient(project, status)


def test_initial_idle_is_persisted_baseline_then_working_to_idle_signals_once(project):
    client = register_worker(project)
    assert tasks.pending_signals(project, client) == []
    handle = tasks.handle_path(project, "analysis")
    assert json.loads(handle.read_text())["last_worker_status"] == "idle"
    # A new client represents re-entry; the baseline is not in the old object.
    client = WorkerClient(project)
    assert tasks.pending_signals(project, client) == []
    client.status = "working"
    assert tasks.pending_signals(project, client) == []
    assert json.loads(handle.read_text())["last_worker_status"] == "working"
    client.status = "idle"
    signal, = tasks.pending_signals(project, client)
    assert signal["observed"]["last_worker_status"] == "idle"
    assert signal["observed"]["reports_seen"] == []
    assert "not acceptance" in signal["prompt"]
    tasks.mark_notified(project, signal, {"delivery": "visible_notice"})
    assert tasks.pending_signals(project, WorkerClient(project)) == []


@pytest.mark.parametrize("condition", ["blocked", "unknown", "changed-owner"])
def test_initial_worker_problem_signals_inspection_once(project, condition):
    client = register_worker(project, condition if condition != "changed-owner" else "idle")
    if condition == "changed-owner":
        client.pid += 1
    signal, = tasks.pending_signals(project, client)
    observed = signal["observed"]["last_worker_status"]
    if condition == "changed-owner":
        assert "owner changed" in observed
        assert "inspect" in signal["prompt"]
    else:
        assert observed == condition
    tasks.mark_notified(project, signal, {"delivery": "visible_notice"})
    assert tasks.pending_signals(project, client) == []
