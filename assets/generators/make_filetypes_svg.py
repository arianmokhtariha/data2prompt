"""Generate assets/filetypes.svg — the "supported files" chip strip.

One chip per specialized parser actually registered in the parser registry
(src/data2prompt/parsers.py registry.register(...) calls) — this lists
exactly what gets bespoke treatment (sampling, schema extraction, per-sheet
splitting, redaction), not every extension the tool can merely read as text.
Each chip carries a small hand-drawn glyph instead of a plain extension
string, and the whole strip is dark/light selected via a
`prefers-color-scheme` media query so it sits natively in GitHub's own page
chrome (Primer's light/dark neutral tokens), matching whichever theme the
viewer's browser is in — same technique as make_comparison_svg.py.

Wraps to a second row automatically if the chips don't fit MAX_ROW_W.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable, Dict, List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import CATEGORICAL_DARK, CATEGORICAL_LIGHT, PROJECT_ROOT  # noqa: E402

# GitHub Primer neutral tokens — this strip sits directly on the page (no
# card), so it targets GitHub's actual chrome rather than the chart-surface
# tokens make_comparison_svg.py uses for its own standalone card.
CHIP_BG_LIGHT, CHIP_BG_DARK = "#f6f8fa", "#161b22"
CHIP_BORDER_LIGHT, CHIP_BORDER_DARK = "#d0d7de", "#30363d"
INK_LIGHT, INK_DARK = "#1f2328", "#e6edf3"

FONT = "-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"

# One chip per parser registered in parsers.py — label shows every
# extension that parser's registry.register() call actually claims.
Chip = Tuple[str, str, str]  # (label, tooltip, icon_kind)
CHIPS: List[Chip] = [
    (".csv", "CSV — seeded random sampling", "grid"),
    (".xlsx  ·  .xls  ·  .xlsm", "Excel — per-sheet extraction", "grid_fold"),
    (".db  ·  .sqlite  ·  .sqlite3", "SQLite — read-only DDL + sampled rows", "cylinder"),
    (".parquet  ·  .feather  ·  .arrow", "Columnar — schema + stats + sample", "layers"),
    (".sql", "Statement-aware parsing", "query"),
    (".ipynb", "Cell-level cleaning", "brackets"),
    (".env", "Name-only redaction", "lock"),
]

ICON_BOX = 16.0
CHIP_H = 36.0
PAD_L, PAD_R = 12.0, 16.0
GAP_ICON_TEXT = 9.0
CHIP_GAP = 10.0
ROW_GAP = 12.0
MAX_ROW_W = 900.0
CHAR_W = 7.35  # estimated advance for 13.5px/weight 600 sans-serif


def icon_grid(x: float, y: float, color: str) -> str:
    b = ICON_BOX
    return (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{b:.1f}" height="{b:.1f}" '
        f'rx="2.4" fill="none" stroke="{color}" stroke-width="1.4"/>'
        f'<line x1="{x + b / 3:.1f}" y1="{y:.1f}" x2="{x + b / 3:.1f}" '
        f'y2="{y + b:.1f}" stroke="{color}" stroke-width="1.1"/>'
        f'<line x1="{x + 2 * b / 3:.1f}" y1="{y:.1f}" '
        f'x2="{x + 2 * b / 3:.1f}" y2="{y + b:.1f}" stroke="{color}" '
        f'stroke-width="1.1"/>'
        f'<line x1="{x:.1f}" y1="{y + b / 2:.1f}" x2="{x + b:.1f}" '
        f'y2="{y + b / 2:.1f}" stroke="{color}" stroke-width="1.1"/>'
    )


def icon_grid_fold(x: float, y: float, color: str) -> str:
    b = ICON_BOX
    fold = (
        f'<path d="M {x + b - 5:.1f} {y:.1f} L {x + b:.1f} {y:.1f} '
        f'L {x + b:.1f} {y + 5:.1f} Z" fill="{color}" opacity="0.85"/>'
    )
    return icon_grid(x, y, color) + fold


def icon_cylinder(x: float, y: float, color: str) -> str:
    b = ICON_BOX
    cx, rx, ry = x + b / 2, b * 0.4, b * 0.16
    top_y, bot_y = y + ry + 1, y + b - ry - 1
    return (
        f'<path d="M {cx - rx:.1f} {top_y:.1f} '
        f'A {rx:.1f} {ry:.1f} 0 0 1 {cx + rx:.1f} {top_y:.1f} '
        f'L {cx + rx:.1f} {bot_y:.1f} '
        f'A {rx:.1f} {ry:.1f} 0 0 1 {cx - rx:.1f} {bot_y:.1f} Z" '
        f'fill="none" stroke="{color}" stroke-width="1.4"/>'
        f'<ellipse cx="{cx:.1f}" cy="{top_y:.1f}" rx="{rx:.1f}" '
        f'ry="{ry:.1f}" fill="none" stroke="{color}" stroke-width="1.4"/>'
        f'<path d="M {cx - rx:.1f} {(top_y + bot_y) / 2:.1f} '
        f'A {rx:.1f} {ry:.1f} 0 0 0 {cx + rx:.1f} {(top_y + bot_y) / 2:.1f}" '
        f'fill="none" stroke="{color}" stroke-width="1.1" opacity="0.7"/>'
    )


def icon_layers(x: float, y: float, color: str) -> str:
    b = ICON_BOX
    bar_h = b * 0.22
    gaps = [0.06, 0.39, 0.72]
    ops = [1.0, 0.72, 0.48]
    parts = []
    for gy, op in zip(gaps, ops):
        parts.append(
            f'<rect x="{x + 1:.1f}" y="{y + b * gy:.1f}" width="{b - 2:.1f}" '
            f'height="{bar_h:.1f}" rx="1.6" fill="{color}" opacity="{op}"/>'
        )
    return "".join(parts)


def icon_query(x: float, y: float, color: str) -> str:
    b = ICON_BOX
    return (
        f'<line x1="{x + 1.5:.1f}" y1="{y + 3.4:.1f}" x2="{x + 8.6:.1f}" '
        f'y2="{y + 3.4:.1f}" stroke="{color}" stroke-width="1.3" '
        f'stroke-linecap="round"/>'
        f'<line x1="{x + 1.5:.1f}" y1="{y + 6.6:.1f}" x2="{x + 6.6:.1f}" '
        f'y2="{y + 6.6:.1f}" stroke="{color}" stroke-width="1.3" '
        f'stroke-linecap="round"/>'
        f'<circle cx="{x + b * 0.62:.1f}" cy="{y + b * 0.62:.1f}" r="3.5" '
        f'fill="none" stroke="{color}" stroke-width="1.4"/>'
        f'<line x1="{x + b * 0.62 + 2.4:.1f}" y1="{y + b * 0.62 + 2.4:.1f}" '
        f'x2="{x + b - 1:.1f}" y2="{y + b - 1:.1f}" stroke="{color}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
    )


def icon_brackets(x: float, y: float, color: str) -> str:
    b = ICON_BOX
    return (
        f'<path d="M {x + 5.5:.1f} {y + 1.5:.1f} '
        f'Q {x + 1.5:.1f} {y + 1.5:.1f} {x + 1.5:.1f} {y + 5.5:.1f} '
        f'L {x + 1.5:.1f} {y + b - 5.5:.1f} '
        f'Q {x + 1.5:.1f} {y + b - 1.5:.1f} {x + 5.5:.1f} {y + b - 1.5:.1f}" '
        f'fill="none" stroke="{color}" stroke-width="1.6" '
        f'stroke-linecap="round"/>'
        f'<path d="M {x + b - 5.5:.1f} {y + 1.5:.1f} '
        f'Q {x + b - 1.5:.1f} {y + 1.5:.1f} {x + b - 1.5:.1f} {y + 5.5:.1f} '
        f'L {x + b - 1.5:.1f} {y + b - 5.5:.1f} '
        f'Q {x + b - 1.5:.1f} {y + b - 1.5:.1f} {x + b - 5.5:.1f} '
        f'{y + b - 1.5:.1f}" fill="none" stroke="{color}" '
        f'stroke-width="1.6" stroke-linecap="round"/>'
    )


def icon_lock(x: float, y: float, color: str) -> str:
    b = ICON_BOX
    return (
        f'<rect x="{x + 3:.1f}" y="{y + 7.2:.1f}" width="{b - 6:.1f}" '
        f'height="{b - 8.2:.1f}" rx="1.6" fill="none" stroke="{color}" '
        f'stroke-width="1.4"/>'
        f'<path d="M {x + 5:.1f} {y + 7.2:.1f} L {x + 5:.1f} {y + 4.8:.1f} '
        f'A 3 3 0 0 1 {x + b - 5:.1f} {y + 4.8:.1f} L {x + b - 5:.1f} '
        f'{y + 7.2:.1f}" fill="none" stroke="{color}" stroke-width="1.4"/>'
        f'<circle cx="{x + b / 2:.1f}" cy="{y + 11:.1f}" r="1.15" '
        f'fill="{color}"/>'
    )


ICONS: Dict[str, Callable[[float, float, str], str]] = {
    "grid": icon_grid,
    "grid_fold": icon_grid_fold,
    "cylinder": icon_cylinder,
    "layers": icon_layers,
    "query": icon_query,
    "brackets": icon_brackets,
    "lock": icon_lock,
}


def chip_width(label: str) -> float:
    return PAD_L + ICON_BOX + GAP_ICON_TEXT + len(label) * CHAR_W + PAD_R


def layout_rows(chips: List[Chip]) -> List[List[Tuple[Chip, float]]]:
    """Greedy-wrap chips into rows no wider than MAX_ROW_W."""
    rows: List[List[Tuple[Chip, float]]] = [[]]
    row_w = 0.0
    for chip in chips:
        w = chip_width(chip[0])
        projected = row_w + (CHIP_GAP if rows[-1] else 0) + w
        if rows[-1] and projected > MAX_ROW_W:
            rows.append([])
            row_w = 0.0
        rows[-1].append((chip, w))
        row_w += (CHIP_GAP if len(rows[-1]) > 1 else 0) + w
    return rows


def build() -> str:
    rows = layout_rows(CHIPS)
    row_widths = [
        sum(w for _, w in row) + CHIP_GAP * (len(row) - 1) for row in rows
    ]
    content_w = max(row_widths)
    content_h = len(rows) * CHIP_H + (len(rows) - 1) * ROW_GAP
    pad = 4.0
    svg_w, svg_h = content_w + 2 * pad, content_h + 2 * pad

    body: List[str] = []
    y = pad
    for row, row_w in zip(rows, row_widths):
        x = pad + (content_w - row_w) / 2
        for i, (chip, w) in enumerate(row):
            label, tooltip, icon_kind = chip
            idx = CHIPS.index(chip)
            color_l = CATEGORICAL_LIGHT[idx % len(CATEGORICAL_LIGHT)]
            color_d = CATEGORICAL_DARK[idx % len(CATEGORICAL_DARK)]
            icon_x, icon_y = x + PAD_L, y + (CHIP_H - ICON_BOX) / 2
            text_x = icon_x + ICON_BOX + GAP_ICON_TEXT
            text_y = y + CHIP_H / 2 + 4.7
            body.append(
                f'<g class="chip"><title>{tooltip}</title>'
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" '
                f'height="{CHIP_H:.1f}" rx="{CHIP_H / 2:.1f}" class="pill"/>'
                f'<g class="icon-l" style="--ic:{color_l}">'
                f'{ICONS[icon_kind](icon_x, icon_y, "currentColor")}</g>'
                f'<g class="icon-d" style="--ic:{color_d}">'
                f'{ICONS[icon_kind](icon_x, icon_y, "currentColor")}</g>'
                f'<text x="{text_x:.1f}" y="{text_y:.1f}" font-size="13.5" '
                f'font-weight="600" class="label">{label}</text>'
                f'</g>'
            )
            x += w + CHIP_GAP
        y += CHIP_H + ROW_GAP

    aria = "Supported file types: " + "; ".join(c[0] for c in CHIPS)
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {svg_w:.1f} {svg_h:.1f}" width="{svg_w:.0f}" height="{svg_h:.0f}" role="img" aria-label="{aria}">
<title>Supported file types — one native parser each</title>
<style>
  .chip {{ }}
  text {{ font-family: {FONT}; }}
  .label {{ fill: {INK_LIGHT}; }}
  .pill {{ fill: {CHIP_BG_LIGHT}; stroke: {CHIP_BORDER_LIGHT}; stroke-width: 1; }}
  .icon-d {{ display: none; }}
  .icon-l, .icon-d {{ color: var(--ic); }}
  @media (prefers-color-scheme: dark) {{
    .label {{ fill: {INK_DARK}; }}
    .pill {{ fill: {CHIP_BG_DARK}; stroke: {CHIP_BORDER_DARK}; }}
    .icon-l {{ display: none; }}
    .icon-d {{ display: inline; }}
  }}
</style>
{"".join(body)}
</svg>'''
    return svg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=PROJECT_ROOT / "assets" / "filetypes.svg",
        help="output path for the generated SVG",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    svg = build()
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out} ({len(svg):,} chars)")


if __name__ == "__main__":
    main()
