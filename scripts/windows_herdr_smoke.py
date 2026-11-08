"""No-model native Herdr smoke using only a fresh test-owned named session.

Run after installing the official Windows distribution (including ConPTY DLLs):
  python scripts/windows_herdr_smoke.py --herdr-bin PATH --output evidence.json
Sources: https://herdr.dev/tui/docs/cli-reference/ and /socket-api/.
No user session is attached, modified, stopped, or deleted.
"""
from __future__ import annotations

import argparse
import base64
import json
import os
from pathlib import Path
import subprocess
import shutil
import tempfile
import time
import uuid

from superaris.client import Herdr, verify_owner
from superaris.platform import detached_process_options, command_line
from superaris.transport import windows_pipe_name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--herdr-bin", default="herdr")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if os.name != "nt":
        parser.error("This smoke must run on native Windows; no emulated success is reported")
    session = "superaris-smoke-" + uuid.uuid4().hex
    client = Herdr(session, args.herdr_bin)
    evidence = {"session": session, "platform": os.name, "models_called": False,
                "sources": ["https://herdr.dev/tui/docs/cli-reference/",
                            "https://herdr.dev/tui/docs/socket-api/"]}
    server = None
    temporary = tempfile.TemporaryDirectory(prefix="superaris smoke 中文 ")
    try:
        evidence["version"] = subprocess.run([args.herdr_bin, "--version"], check=True,
            capture_output=True, text=True, encoding="utf-8", timeout=20).stdout.strip()
        # Record the actual binary's supported protocol, rather than assuming
        # the Windows release equals a previously tested macOS version.
        evidence["schema"] = json.loads(client.run("api", "schema", "--json"))
        root = Path(temporary.name)
        with (root / "server.log").open("ab") as output:
            server = subprocess.Popen([args.herdr_bin, "--session", session, "server"],
                stdin=subprocess.DEVNULL, stdout=output, stderr=output,
                **detached_process_options())
        deadline = time.monotonic() + 30
        while True:
            try:
                client.snapshot()
                break
            except Exception:
                if server.poll() is not None or time.monotonic() >= deadline:
                    raise RuntimeError((root / "server.log").read_text(errors="replace"))
                time.sleep(.2)
        workspace = client.json("workspace", "create", "--cwd", str(root),
                                "--label", "SuperARIS no-model smoke", "--no-focus")
        pane = workspace["root_pane"]["pane_id"]
        evidence["workspace"] = workspace
        evidence["endpoint"] = client.socket_path()
        evidence["native_pipe"] = windows_pipe_name(evidence["endpoint"])
        assert client.request("ping", {})["type"] == "pong"
        # A synthetic Node entry exercises real Windows process-info without
        # installing/authenticating or invoking any model CLI.
        node = shutil.which("node")
        if not node:
            raise RuntimeError("The no-model identity smoke requires Node from the runner")
        synthetic = root / "codex.js"
        synthetic.write_text("console.log('SUPERARIS_NO_MODEL_READY'); setInterval(()=>{},1000);", encoding="utf-8")
        encoded = base64.b64encode(command_line([node, str(synthetic)]).encode("utf-16-le")).decode("ascii")
        evidence["synthetic_launch"] = client.run("pane", "run", pane,
            "powershell.exe -NoProfile -EncodedCommand " + encoded)
        deadline = time.monotonic() + 20
        while True:
            info = client.json("pane", "process-info", "--pane", pane)["process_info"]
            if any("codex.js" in str(p.get("argv")) for p in info.get("foreground_processes", [])):
                break
            if time.monotonic() >= deadline:
                raise RuntimeError("Synthetic Node entry missing from actual process-info: " + json.dumps(info))
            time.sleep(.2)
        evidence["process_info"] = info
        client.request("pane.report_agent", {"pane_id": pane, "source": "custom:superaris-smoke",
            "agent": "codex", "state": "working", "message": "synthetic Node entry; no model"})
        live = verify_owner(client, {"pane_id": pane, "harness": "codex"}, root.resolve())
        evidence["verified_synthetic_owner"] = live
        assert live["pid"]
        evidence["pane"] = client.request("pane.get", {"pane_id": pane})
        stream = client.events([{"type": "pane.agent_status_changed", "pane_id": pane}], timeout=3)
        try:
            evidence["subscription_ack"] = next(stream)
            client.request("pane.report_agent", {"pane_id": pane, "source": "custom:superaris-smoke",
                "agent": "codex", "state": "idle", "message": "synthetic work complete; no model"})
            evidence["native_event"] = next(stream)
            assert pane in json.dumps(evidence["native_event"])
        finally:
            stream.close()
        evidence["snapshot"] = client.snapshot()
        evidence["status"] = "passed"
    except BaseException as exc:
        evidence["status"] = "failed"
        evidence["error"] = repr(exc)
        if "pane" in locals():
            try:
                evidence["failure_pane"] = client.run("pane", "read", pane, "--source", "recent", "--lines", "30")
            except Exception as diagnostic:
                evidence["failure_pane_error"] = repr(diagnostic)
        raise
    finally:
        if server is not None:
            try:
                # Every mutating command retains our generated explicit selector.
                evidence["cleanup"] = client.run("server", "stop", timeout=15)
                server.wait(timeout=15)
            except Exception as exc:
                evidence["cleanup_error"] = repr(exc)
                if server.poll() is None:
                    server.terminate()
                    server.wait(timeout=10)
        # Preserve original result even if Windows still releases a ConPTY
        # handle after server.stop; this directory belongs only to this runner.
        try:
            temporary.cleanup()
        except OSError as exc:
            evidence["temporary_cleanup_error"] = repr(exc)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": evidence["status"], "session": session,
                      "evidence": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
