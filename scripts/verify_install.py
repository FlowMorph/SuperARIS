"""Exercise an actual wheel in a new HOME/venv, without native agent calls.

The final context check downloads the fixed public ARIS source. It executes
only reviewer-route resolution, never a model, Herdr server or research task.
"""
from pathlib import Path
import json
import os
import subprocess
import sys
import tempfile
import time
import venv


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python scripts/verify_install.py path/to/wheel.whl")
    import glob
    matches = glob.glob(sys.argv[1])
    if len(matches) != 1:
        raise SystemExit("Expected exactly one wheel")
    wheel = Path(matches[0]).resolve()
    with tempfile.TemporaryDirectory(prefix="superaris-clean-") as temporary:
        root = Path(temporary).resolve()
        home = root / "home"
        home.mkdir()
        environment = {key: value for key, value in os.environ.items()
                       if key not in {"ARIS_REPO", "SUPERARIS_ARIS_REPO", "PYTHONPATH", "PYTHONHOME", "CODEX_HOME"}}
        environment.update(HOME=str(home), USERPROFILE=str(home), PYTHONUTF8="1", XDG_CACHE_HOME=str(root / "cache"),
                           PIP_CONFIG_FILE=os.devnull, PIP_DISABLE_PIP_VERSION_CHECK="1",
                           PIP_NO_CACHE_DIR="1", PYTHONNOUSERSITE="1")
        installation = root / "venv"
        venv.EnvBuilder(with_pip=True).create(installation)
        scripts = installation / ("Scripts" if os.name == "nt" else "bin")
        python = scripts / ("python.exe" if os.name == "nt" else "python")
        environment["PATH"] = str(scripts) + os.pathsep + os.defpath

        def run(*arguments):
            result = subprocess.run([str(python), *arguments], cwd=home, env=environment,
                                    capture_output=True, text=True, encoding="utf-8", timeout=180)
            if result.returncode:
                raise RuntimeError(result.stdout + result.stderr)
            return result.stdout

        run("-m", "pip", "install", "--no-index", "--no-deps", str(wheel))
        module = Path(run("-c", "import superaris; print(superaris.__file__)").strip())
        assert module.is_relative_to(installation), module
        assert "context" in run("-m", "superaris", "--help")
        project = root / "project with spaces"
        project.mkdir()
        plan = json.loads(run("-m", "superaris", "start", str(project), "--plan"))
        assert not plan["will_mutate"] and not (project / ".aris").exists()
        assert not (root / "cache").exists()

        # Windows exercises the installed console entry's wizard logic with
        # bounded input; Unix additionally verifies an actual PTY below.
        if os.name == "nt":
            wizard_output = run("-c", "import builtins,sys; from importlib.metadata import entry_points; "
                "sys.stdin.isatty=lambda:True; sys.stdout.isatty=lambda:True; "
                "answers=iter(['2','q']); builtins.input=lambda prompt='':(print(prompt),next(answers))[1]; "
                "next(iter(entry_points(group='console_scripts',name='superaris'))).load()()")
            assert "Project directory" in wizard_output
            sent_cancel = True
        else:
            import pty
            import select
            # Use the installed console entry, not an editable/source wrapper.
            child, master = pty.fork()
            if child == 0:
                os.chdir(home)
                os.execve(str(installation / "bin/superaris"), ["superaris"], environment)
            output = b""
            sent_language = sent_cancel = False
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                if select.select([master], [], [], 0.05)[0]:
                    try:
                        output += os.read(master, 65536)
                    except OSError:
                        pass
                if not sent_language and b"Choose language [1]" in output:
                    os.write(master, b"2\n")
                    sent_language = True
                if not sent_cancel and b"Project directory" in output:
                    os.write(master, b"q\n")
                    sent_cancel = True
                done, status = os.waitpid(child, os.WNOHANG)
                if done:
                    assert os.waitstatus_to_exitcode(status) == 0
                    break
            else:
                os.kill(child, 15)
                os.waitpid(child, 0)
                raise RuntimeError("Installed wizard did not cancel: " + output.decode(errors="replace"))
            os.close(master)
        assert sent_cancel and not (root / "cache").exists()
        assert list(home.iterdir()) == [], list(home.iterdir())

        # Minimal recorded role: preparation makes no Herdr/native requests.
        binding = project / ".aris/workbench/launch.json"
        binding.parent.mkdir(parents=True)
        binding.write_text(json.dumps({"roles": {"engineer": {
            "harness": "codex", "delivery": {"phase": "unknown"},
            "inputs": {"task": "Keep the original assignment.",
                       "skills": [], "write_scope": str(project / "outputs/engineer")}}}}))
        before = binding.read_bytes()
        prepared = json.loads(run("-m", "superaris", "context", str(project), "--role", "engineer",
                                  "--skill", "research-refine-pipeline"))
        assert binding.read_bytes() == before
        for name in ("project-agent", "research-refine-pipeline", "research-refine", "experiment-plan"):
            assert Path(prepared["skill_index"][name]).is_file()
        child_skill = Path(prepared["skill_index"]["research-refine"])
        assert "../../shared-references/output-versioning.md" in child_skill.read_text(encoding="utf-8")
        assert (child_skill.parent / "../../shared-references/output-versioning.md").resolve().is_file()
        aris = Path(run("-c", "from superaris.dependencies import resolve_aris_repo; print(resolve_aris_repo())").strip())
        assert aris.is_relative_to(root / "cache")
        routed = json.loads(run(str(aris / "tools/reviewer_route.py"), "--project", str(project), "--host", "codex"))
        print(json.dumps({"installed_module": str(module), "wheel": wheel.name,
                          "help_plan_and_cancel_no_fetch": True, "workflow_child_shared_reference": True,
                          "canonical_helper": str(aris / "tools/reviewer_route.py"),
                          "route": routed, "binding_unchanged": True,
                          "native_or_model_calls": 0, "wizard_check": "installed logic/input" if os.name == "nt" else "actual PTY"}, indent=2))


if __name__ == "__main__":
    main()
