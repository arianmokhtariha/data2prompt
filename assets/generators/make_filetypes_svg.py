"""Generate assets/filetypes.svg — the "native parsers" terminal strip.

A two-row dark card in the banner's terminal aesthetic: a red marker plus
the ``NATIVE PARSERS`` label sit on their own header row, then every file
extension the parser registry claims (src/data2prompt/parsers.py
registry.register(...) calls) is rendered on the row below, in bold
monospace and color-coded per parser family like a modern terminal file
listing. Groups are separated by dim middots and carry a ``<title>``
tooltip naming what the parser actually does. The card is dark on both
GitHub themes — same surface as banner.svg — so the strip reads as the
tool's own status line directly under the badge row.

Splitting the label onto its own row (instead of sharing one cramped line
with all thirteen extensions) is what buys the room for a materially
bigger font: cramming both onto one 960-wide line caps the type size at
~13px before tokens overflow the canvas, while giving the extension row
the full width lets it run at 16px with headroom to spare. Text spacing
is ``textLength``-locked at the same 0.62 em advance the banner generator
uses, so layout cannot drift across platform mono fonts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import PROJECT_ROOT  # noqa: E402

# --- canvas & card --------------------------------------------------------
W, H = 960.0, 88.0
CARD_BG, CARD_BORDER = "#0b0b0e", "#26262c"

# --- type ------------------------------------------------------------------
FONT = (
    "'Cascadia Code','Fira Code','JetBrains Mono',Consolas,"
    "'DejaVu Sans Mono',Menlo,monospace"
)
FONT_SIZE = 16.0
CHAR_W = FONT_SIZE * 0.62  # mono advance; same ratio banner.svg locks to

# --- inks ------------------------------------------------------------------
LABEL_INK = "#8a8a94"
MARKER_RED = "#ff3b57"
SEP_INK = "#3d3d46"

# --- layout ----------------------------------------------------------------
PAD_L, PAD_R = 26.0, 26.0
MARKER_W, MARKER_GAP = 11.0, 6.0
LABEL = "NATIVE PARSERS"
BASELINE1 = 34.0  # header row: marker + label
BASELINE2 = 64.0  # listing row: extensions
TOKEN_GAP = 7.0  # between extensions inside one group
SEP_HALF = 12.0  # group -> middot -> group, each side
SEP_CY, SEP_R = BASELINE2 - 4.0, 2.0

# One group per parser registered in parsers.py — tokens list every
# extension that parser's registry.register() call actually claims.
Group = Tuple[str, str, str, List[str]]  # (css class, color, tooltip, tokens)
GROUPS: List[Group] = [
    ("csv", "#6cb6ff", "CSV — seeded random sampling", [".csv"]),
    ("xls", "#56d4a0", "Excel — per-sheet extraction",
     [".xlsx", ".xls", ".xlsm"]),
    ("sqlt", "#e8b64c", "SQLite — read-only schema + sampled rows",
     [".db", ".sqlite", ".sqlite3"]),
    ("col", "#4dd0c4", "Columnar — schema, stats and sample",
     [".parquet", ".feather", ".arrow"]),
    ("sql", "#b39df8", "SQL — statement-aware parsing", [".sql"]),
    ("nb", "#ff9e64", "Notebooks — cell-level cleaning", [".ipynb"]),
    ("env", "#ef87b8", "Secrets — name-only redaction", [".env"]),
]


def text_el(x: float, y: float, token: str, css: str) -> str:
    """One textLength-locked mono text element at the given baseline."""
    return (
        f'<text x="{x:.1f}" y="{y:.0f}" '
        f'textLength="{len(token) * CHAR_W:.1f}" '
        f'lengthAdjust="spacingAndGlyphs" class="{css}">{token}</text>'
    )


def build() -> str:
    body: List[str] = []

    # --- row 1: marker + label -------------------------------------------
    marker_top = BASELINE1 - 9.85
    body.append(
        f'<path d="M {PAD_L:.1f} {marker_top:.1f} h {MARKER_W:.1f} '
        f'l -2.7 11.7 h -{MARKER_W:.1f} Z" fill="{MARKER_RED}"/>'
    )
    label_x = PAD_L + MARKER_W + MARKER_GAP
    body.append(text_el(label_x, BASELINE1, LABEL, "mono chrome label"))
    if label_x + len(LABEL) * CHAR_W + PAD_R > W:
        raise ValueError("header row overflows canvas")

    # --- row 2: extension groups ------------------------------------------
    x = PAD_L
    for i, (css, _color, tooltip, tokens) in enumerate(GROUPS):
        if i > 0:
            body.append(
                f'<circle cx="{x + SEP_HALF:.1f}" cy="{SEP_CY:.0f}" '
                f'r="{SEP_R}" fill="{SEP_INK}"/>'
            )
            x += 2 * SEP_HALF
        parts: List[str] = []
        for j, token in enumerate(tokens):
            if j > 0:
                x += TOKEN_GAP
            parts.append(text_el(x, BASELINE2, token, f"mono ext {css}"))
            x += len(token) * CHAR_W
        body.append(f"<g><title>{tooltip}</title>{''.join(parts)}</g>")

    if x + PAD_R > W:
        raise ValueError(f"listing row overflows canvas: content ends at {x:.1f}")

    color_rules = "\n".join(
        f"  .{css} {{ fill: {color}; }}" for css, color, _, _ in GROUPS
    )
    all_tokens = [t for _, _, _, tokens in GROUPS for t in tokens]
    aria = "Native parsers: " + ", ".join(all_tokens)

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}" role="img" aria-label="{aria}">
<title>Native parsers — one dedicated parser per file family</title>
<style>
  .mono {{ font-family: {FONT}; font-size: {FONT_SIZE:.0f}px; }}
  .chrome {{ fill: {LABEL_INK}; }}
  .label {{ font-weight: 700; letter-spacing: 0.5px; }}
  .ext {{ font-weight: 800; }}
{color_rules}
</style>
<defs>
  <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">
    <rect width="4" height="1" fill="#ffffff" opacity="0.022"/>
  </pattern>
</defs>

<rect x="0.5" y="0.5" width="{W - 1:.0f}" height="{H - 1:.0f}" rx="11" fill="{CARD_BG}" stroke="{CARD_BORDER}"/>

{"".join(body)}

<rect x="1" y="1" width="{W - 2:.0f}" height="{H - 2:.0f}" rx="11" fill="url(#scan)"/>
</svg>
'''


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
