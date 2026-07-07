"""Shared pytest configuration.

Puts ``src/`` at the front of ``sys.path`` so every test imports the package as
``data2prompt.*`` — the same root the installed console script uses. Previously
some tests imported ``src.data2prompt.*`` (via the implicit ``src`` namespace
package), which loads a *second* copy of every module: dataclasses defined twice,
``isinstance`` checks failing across the boundary, and module-level state
(parser registry, encoding cache) duplicated. One import root removes that
entire class of bug.
"""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
