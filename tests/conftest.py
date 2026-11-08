"""Isolate HOME and supply a complete synthetic ARIS dependency to unit tests."""
import atexit
import os
from pathlib import Path
import shutil
import tempfile

from tests.support import make_aris_repo

_sandbox = Path(tempfile.mkdtemp(prefix="superaris-tests-"))
_home = _sandbox / "home"
_home.mkdir()
os.environ["HOME"] = str(_home)
os.environ["USERPROFILE"] = str(_home)
os.environ["XDG_CACHE_HOME"] = str(_sandbox / "cache")
os.environ["SUPERARIS_ARIS_REPO"] = str(make_aris_repo(_sandbox / "aris"))
os.environ.pop("ARIS_REPO", None)
os.environ.pop("PYTHONPATH", None)
atexit.register(shutil.rmtree, _sandbox, ignore_errors=True)
