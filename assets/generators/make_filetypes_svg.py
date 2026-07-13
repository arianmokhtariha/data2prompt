"""Generate assets/filetypes.svg — the "native parsers" terminal strip.

One slim dark bar in the banner's terminal aesthetic: a red marker plus a
muted ``NATIVE PARSERS`` label on the left, then every file extension the
parser registry claims (src/data2prompt/parsers.py registry.register(...)
calls), rendered in bold monospace and color-coded per parser family like a
modern terminal file listing. Groups are separated by dim middots and carry
a ``<title>`` tooltip naming what the parser actually does. The card is
dark on both GitHub themes — same surface as banner.svg — so the strip
reads as the tool's own status line directly under the badge row.

Text spacing is ``textLength``-locked at the same 0.62 em advance the
banner generator uses, so layout cannot drift across platform mono fonts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import PROJECT_ROOT  # noqa: E402

# --- canvas & card --------------------------------------------------------
W, H = 960.0, 52.0
CARD_BG, CARD_BORDER = "#0b0b0e", "#26262c"

# --- type ------------------------------------------------------------------
FONT = (
    "'Cascadia Code','Fira Code','JetBrains Mono',Consolas,"
    "'DejaVu Sans Mono',Menlo,monospace"
)
FONT_SIZE = 13.0
CHAR_W = FONT_SIZE * 0.62  # mono advance; same ratio banner.svg locks to
BASELINE = 31.0

# --- inks ------------------------------------------------------------------
LABEL_INK = "#73737e"
MARKER_RED = "#ff3b57"
SEP_INK = "#3d3d46"

# --- layout ----------------------------------------------------------------
PAD_L, PAD_R = 26.0, 26.0
MARKER_W, MARKER_GAP = 9.0, 4.8
LABEL = "NATIVE PARSERS"
LABEL_GAP = 26.0  # label -> first group
TOKEN_GAP = 7.0  # between extensions inside one group
SEP_HALF = 11.0  # group -> middot -> group, each side
SEP_CY, SEP_R = 27.0, 1.7

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


def text_el(x: float, token: str, css: str) -> str:
    """One textLength-locked mono text element at the shared baseline."""
    return (
        f'<text x="{x:.1f}" y="{BASELINE:.0f}" '
        f'textLength="{len(token) * CHAR_W:.1f}" '
        f'lengthAdjust="spacingAndGlyphs" class="{css}">{token}</text>'
    )


def build() -> str:
    body: List[str] = []

    marker_top = BASELINE - 8.0
    body.append(
        f'<path d="M {PAD_L:.1f} {marker_top:.1f} h {MARKER_W:.1f} '
        f'l -2.2 9.5 h -{MARKER_W:.1f} Z" fill="{MARKER_RED}"/>'
    )
    label_x = PAD_L + MARKER_W + MARKER_GAP
    body.append(text_el(label_x, LABEL, "mono chrome"))

    x = label_x + len(LABEL) * CHAR_W + LABEL_GAP
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
            parts.append(text_el(x, token, f"mono ext {css}"))
            x += len(token) * CHAR_W
        body.append(f"<g><title>{tooltip}</title>{''.join(parts)}</g>")

    if x + PAD_R > W:
        raise ValueError(f"strip overflows canvas: content ends at {x:.1f}")

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
  .ext {{ font-weight: bold; }}
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
