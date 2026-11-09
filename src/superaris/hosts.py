"""The two supported workbenches; selection never starts or installs a host."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

HOSTS = ("herdr", "orca")


def selected_host(bound: dict, requested: str | None = None) -> str:
    original = bound.get("host", "herdr") if bound else None
    if original and original not in HOSTS:
        raise ValueError(f"Unknown recorded workbench: {original}; inspect the original binding")
    if requested and original and requested != original:
        raise ValueError(f"This project belongs to {original}; resume its original team instead of switching to {requested}")
    return original or requested or "herdr"


def discover_orca(explicit: str | None = None) -> dict:
    """Find the official bundled launcher without changing PATH/settings.

    Orca's bundled-cli-launcher-path.ts defines resources/bin/orca on macOS,
    resources/bin/orca.exe on Windows, and orca-ide on Linux (GNOME owns orca).
    CLI availability is deliberately separate from runtime/login readiness.
    """
    if explicit:
        candidate = shutil.which(explicit) or (str(Path(explicit).expanduser()) if Path(explicit).expanduser().is_file() else None)
        return {"cli": str(Path(candidate).resolve()) if candidate else None, "app": None, "source": "explicit", "requested": explicit}
    command = shutil.which("orca-ide" if sys.platform.startswith("linux") else "orca")
    if command:
        return {"cli": str(Path(command).resolve()), "app": None, "source": "PATH"}
    configured = os.environ.get("ORCA_CLI_INSTALL_PATH")
    if configured and Path(configured).is_file():
        return {"cli": str(Path(configured).resolve()), "app": None, "source": "official-install-override"}
    app = None
    launchers = []
    if sys.platform == "darwin":
        for root in (Path("/Applications"), Path.home() / "Applications"):
            bundle = root / "Orca.app"
            if bundle.is_dir():
                app = str(bundle)
                launchers.append(bundle / "Contents/Resources/bin/orca")
    elif os.name == "nt":
        for root in (Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData/Local")) / "Programs",
                     Path(os.environ.get("ProgramFiles", "C:/Program Files"))):
            bundle = root / "Orca"
            if bundle.is_dir():
                app = str(bundle)
                launchers.append(bundle / "resources/bin/orca.exe")
    for launcher in launchers:
        if launcher.is_file():
            return {"cli": str(launcher), "app": app, "source": "bundled"}
    return {"cli": None, "app": app, "source": "app-without-cli" if app else "missing"}


def orca_missing_action(found: dict) -> str:
    if found.get("app"):
        return "Open Orca → Settings → General → Orca CLI to register its command, then resume this project."
    return "Install Orca from https://www.onorca.dev/download, open it, then resume this project."


def client_for_binding(bound: dict, project: Path, binary: str = "herdr", *, orca_bin: str | None = None, herdr_factory=None):
    if selected_host(bound) == "orca":
        from .orca import Orca
        return Orca(project, orca_bin or bound.get("orca_bin"), bound)
    if herdr_factory is None:
        from .client import Herdr
        herdr_factory = Herdr
    return herdr_factory(bound["session"], binary)


def identity_present(role: dict) -> bool:
    if role.get("host") == "orca":
        return bool(role.get("pane_id") and role.get("runtime_id") and role.get("process_incarnation"))
    return bool(role.get("pid"))
