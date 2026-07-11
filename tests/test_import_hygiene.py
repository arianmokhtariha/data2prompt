"""
Import-hygiene tests.

After hoisting ``from .utils import count_tokens, is_binary`` to the top of
``parsers.py``, importing any single module must still succeed in a clean
interpreter — i.e. there is no import-order cycle
(``parsers -> utils -> ui -> parsers``). Each module is imported *first* in its
own fresh subprocess, so the result does not depend on whatever pytest happened
to import earlier in the session.

``PYTHONPATH`` is pointed at ``src/`` so the package resolves whether or not it
is currently installed (editable or otherwise).
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = REPO_ROOT / "src"

# Every top-level module, each imported first in isolation.
MODULES = [
    "data2prompt.parsers",
    "data2prompt.utils",
    "data2prompt.ui",
    "data2prompt.output",
    "data2prompt.budget",
    "data2prompt.cli",
    "data2prompt.main",
]


@pytest.mark.parametrize("module", MODULES)
def test_module_imports_cleanly(module: str) -> None:
    """Importing ``module`` first in a fresh interpreter raises no cycle."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = str(SRC_DIR) + (os.pathsep + existing if existing else "")

    result = subprocess.run(
        [sys.executable, "-c", f"import {module}"],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(REPO_ROOT),
    )

    assert result.returncode == 0, f"importing {module} failed:\n{result.stderr}"


if __name__ == "__main__":
    for mod in MODULES:
        test_module_imports_cleanly(mod)
        print(f"OK: import {mod}")
