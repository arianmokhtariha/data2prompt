"""Shared configuration for the assets/generators/*.py scripts.

Single source of truth for values every generator needs so they never drift
out of sync with each other or with the package itself: the repo root, the
version string (read live from ``pyproject.toml`` instead of being hardcoded
into each SVG), and the chart chrome / categorical theme tokens the dataviz
skill's validated reference palette defines for light and dark GitHub
rendering.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
REPO_SLUG = "arianmokhtariha/data2prompt"

_VERSION_RE = re.compile(r'(?m)^version\s*=\s*"([^"]+)"')


def read_version(project_root: Path = PROJECT_ROOT) -> str:
    """Read the package version straight from ``pyproject.toml``.

    Keeps every generated asset (banner run-info line, etc.) pinned to the
    real release version instead of a copy-pasted literal that goes stale.
    """
    text = (project_root / "pyproject.toml").read_text(encoding="utf-8")
    match = _VERSION_RE.search(text)
    if match is None:
        raise ValueError("version not found in pyproject.toml")
    return match.group(1)


def raw_asset_url(name: str, ref: str = "main") -> str:
    """Absolute raw.githubusercontent.com URL for an assets/<name> file."""
    return f"https://raw.githubusercontent.com/{REPO_SLUG}/{ref}/assets/{name}"


# --- Chart chrome & ink --------------------------------------------------
# dataviz skill's validated reference palette. Both modes are *selected*
# (their own steps against each surface), not an automatic light->dark flip.
SURFACE_LIGHT, SURFACE_DARK = "#fcfcfb", "#1a1a19"
INK_LIGHT, INK_DARK = "#0b0b0b", "#ffffff"
MUTED_LIGHT, MUTED_DARK = "#52514e", "#c3c2b7"
AXIS_LIGHT, AXIS_DARK = "#898781", "#898781"
GRID_LIGHT, GRID_DARK = "#e1e0d9", "#2c2c2a"
BASELINE_LIGHT, BASELINE_DARK = "#c3c2b7", "#383835"
BORDER_LIGHT, BORDER_DARK = "rgba(11,11,11,0.10)", "rgba(255,255,255,0.10)"

# Categorical theme — fixed slot order (the CVD-safety mechanism, never
# cycled). Validated as a set: worst adjacent CVD ΔE 24.2 light / 10.3 dark.
CATEGORICAL_LIGHT: List[str] = [
    "#2a78d6", "#1baf7a", "#eda100", "#008300",
    "#4a3aa7", "#e34948", "#e87ba4", "#eb6834",
]
CATEGORICAL_DARK: List[str] = [
    "#3987e5", "#199e70", "#c98500", "#008300",
    "#9085e9", "#e66767", "#d55181", "#d95926",
]

# Emphasis / de-emphasis pair for the comparison chart — validated via
# scripts/validate_palette.js against both surfaces (contrast >= 3:1,
# CVD-separated; the neutral gray intentionally fails the chroma-floor
# check, which is expected for a genuinely achromatic de-emphasis color).
ACCENT_LIGHT, ACCENT_DARK = CATEGORICAL_LIGHT[0], CATEGORICAL_DARK[0]
NEUTRAL_LIGHT, NEUTRAL_DARK = "#7f8894", "#7c8591"
