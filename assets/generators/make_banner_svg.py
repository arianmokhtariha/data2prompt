"""Generate the animated README banner: a font-independent SVG that
re-creates the TUI glitch sweep (cipher churn -> resolve edge -> white
flash -> crimson gradient settle -> teletype run line).

The wordmark and the cipher static are rendered as <rect> grids parsed
from the real BANNER block glyphs, so no font is ever required and the
mark is pixel-identical on every platform. Animation is SMIL with an
end-state fallback: if SMIL is unsupported the settled wordmark shows.
"""
from __future__ import annotations

import argparse
import math
import random
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import PROJECT_ROOT, read_version  # noqa: E402

# The real wordmark from src/data2prompt/constants.py (BANNER).
BANNER: List[str] = [
    "█▀▀▄ ▄▀▀▄ ▀▀█▀▀ ▄▀▀▄ ▀▀▀█ █▀▀▄ █▀▀▄ ▄▀▀▄ █▄ ▄█ █▀▀▄ ▀▀█▀▀",
    "█  █ █▀▀█   █   █▀▀█  ▄▄▀ █▄▄▀ █▄▄▀ █  █ █ ▀ █ █▄▄▀   █  ",
    "█▄▄▀ ▀  ▀   █   ▀  ▀ █▄▄▄ █    █ ▀▄ ▀▄▄▀ █   █ █      █  ",
]
GRADIENT = ("#ff6b7f", "#ff3b57", "#c9203c")   # UI_BANNER_GRADIENT
CIPHER_GLYPHS = "░▒▓▌▐▄▀"                       # UI_CIPHER_GLYPHS

# The teletype run-info line, kept as one editable constant instead of being
# buried inside type_line() — this is the one thing a re-run most likely
# wants to change (demo target/format/output/file-count).
DEMO_RUN_INFO: List[Tuple[str, str]] = [
    ("TARGET", "customer-churn"),
    ("FORMAT", "markdown"),
    ("OUT", "PROMPT.md"),
    ("FILES", "52"),
]

# Geometry
CW, CH = 12.0, 21.0                 # char cell
COLS = len(BANNER[0])
MARK_W, MARK_H = COLS * CW, len(BANNER) * CH
SVG_W, SVG_H = 960.0, 232.0
X0 = (SVG_W - MARK_W) / 2.0
Y0 = 42.0
BLEED = 0.55                         # overdraw to kill antialiasing seams

# Timeline (seconds within a DUR-second run). The whole sweep plays ONCE per
# page load (repeatCount="1" fill="freeze" below) — only the terminal
# cursor's own blink loops indefinitely afterward, like a live prompt.
DUR = 12.0
T_SWEEP_START, T_SWEEP_END = 1.2, 3.0
T_FLASH_A, T_FLASH_B, T_FLASH_C = 3.0, 3.07, 3.38
T_TYPE_START, T_TYPE_END = 3.6, 5.2
CURSOR_BLINK_DUR = 1.1               # seconds; loops forever, by design

# SMIL attrs for the once-through timeline animations vs. the one loop that
# is intentionally allowed to keep repeating (the cursor blink).
PLAY_ONCE = 'repeatCount="1" fill="freeze"'
LOOP_FOREVER = 'repeatCount="indefinite"'


def kt(t: float) -> str:
    return f"{t / DUR:.4f}"


def cell_rects(ch: str, x: float, y: float) -> List[Tuple[float, float, float, float, float]]:
    """Map one glyph to (x, y, w, h, fill-opacity) sub-rects of its cell."""
    full_w, half_w = CW + BLEED, CW / 2 + BLEED
    full_h, half_h = CH + BLEED, CH / 2 + BLEED
    if ch == "█":
        return [(x, y, full_w, full_h, 1.0)]
    if ch == "▀":
        return [(x, y, full_w, half_h, 1.0)]
    if ch == "▄":
        return [(x, y + CH / 2, full_w, half_h, 1.0)]
    if ch == "▌":
        return [(x, y, half_w, full_h, 1.0)]
    if ch == "▐":
        return [(x + CW / 2, y, half_w, full_h, 1.0)]
    if ch == "░":
        return [(x, y, full_w, full_h, 0.20)]
    if ch == "▒":
        return [(x, y, full_w, full_h, 0.42)]
    if ch == "▓":
        return [(x, y, full_w, full_h, 0.66)]
    return []


def mark_layer(fill_per_row: Tuple[str, str, str], opacity_attr: str = "") -> str:
    """The wordmark as merged rects, one fill per row."""
    out: List[str] = []
    for r, line in enumerate(BANNER):
        fill = fill_per_row[r]
        y = Y0 + r * CH
        c = 0
        while c < COLS:
            ch = line[c]
            if ch == " ":
                c += 1
                continue
            run = 1
            while c + run < COLS and line[c + run] == ch:
                run += 1
            x = X0 + c * CW
            for rx, ry, rw, rh, op in cell_rects(ch, x, y):
                w = rw + (run - 1) * CW
                op_s = f' fill-opacity="{op}"' if op < 1 else ""
                out.append(
                    f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{w:.1f}" '
                    f'height="{rh:.1f}" fill="{fill}"{op_s}/>'
                )
            c += run
    return f'<g{opacity_attr}>' + "".join(out) + "</g>"


def churn_variant(seed: int) -> str:
    """One frame of cipher static: silhouette preserved, glyphs random."""
    rng = random.Random(seed)
    out: List[str] = []
    for r, line in enumerate(BANNER):
        y = Y0 + r * CH
        for c, ch in enumerate(line):
            if ch == " ":
                continue
            glyph = rng.choice(CIPHER_GLYPHS)
            x = X0 + c * CW
            for rx, ry, rw, rh, op in cell_rects(glyph, x, y):
                op_s = f' fill-opacity="{op:.2f}"' if op < 1 else ""
                out.append(
                    f'<rect x="{rx:.1f}" y="{ry:.1f}" width="{rw:.1f}" '
                    f'height="{rh:.1f}" fill="#5a5a64"{op_s}/>'
                )
    return "".join(out)


def churn_layers() -> str:
    """Three churn frames cycling via discrete opacity animation.

    The cipher static is only ever visible through the ``#cipher`` clip,
    which fully closes at T_SWEEP_END — so the flicker only needs to cover
    ``0..T_SWEEP_END``, not loop forever. Bounded + frozen like every other
    part of the once-through timeline.
    """
    frames = []
    cycles = [("1;0;0", 1), ("0;1;0", 0), ("0;0;1", 0)]
    repeats = math.ceil(T_SWEEP_END / 0.5) + 1
    for i, (values, base) in enumerate(cycles):
        frames.append(
            f'<g opacity="{base}">'
            f'<animate attributeName="opacity" calcMode="discrete" '
            f'values="{values}" keyTimes="0;0.34;0.67" dur="0.5s" '
            f'repeatCount="{repeats}" fill="freeze"/>'
            + churn_variant(101 + i * 37)
            + "</g>"
        )
    return "".join(frames)


def type_line() -> Tuple[str, float, float, float]:
    """The teletype run-info line. Returns (svg, x_start, x_end, y)."""
    fs = 14.0
    adv = fs * 0.62
    y = Y0 + MARK_H + 66.0
    gap_item = 3.2 * adv
    tick_w, tick_h, tick_gap = 9.0, 9.5, 7.0

    items = DEMO_RUN_INFO
    total = 0.0
    for label, value in items:
        total += tick_w + tick_gap + (len(label) + 1 + len(value)) * adv
    total += gap_item * (len(items) - 1)
    x = (SVG_W - total) / 2.0
    x_start = x

    parts: List[str] = []
    for i, (label, value) in enumerate(items):
        ty = y - tick_h + 1.5
        parts.append(
            f'<path d="M {x + 2.2:.1f} {ty:.1f} h {tick_w:.1f} '
            f'l -2.2 {tick_h:.1f} h {-tick_w:.1f} Z" fill="#ff3b57"/>'
        )
        x += tick_w + tick_gap
        lw = len(label) * adv
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" textLength="{lw:.1f}" '
            f'lengthAdjust="spacingAndGlyphs" class="mono chrome">{label}</text>'
        )
        x += lw + adv
        vw = len(value) * adv
        parts.append(
            f'<text x="{x:.1f}" y="{y:.1f}" textLength="{vw:.1f}" '
            f'lengthAdjust="spacingAndGlyphs" class="mono data">{value}</text>'
        )
        x += vw
        if i < len(items) - 1:
            x += gap_item
    return "".join(parts), x_start, x, y


def build(version: str) -> str:
    reveal_times = f"0;{kt(T_SWEEP_START)};{kt(T_SWEEP_END)};1"
    edge_x0, edge_x1 = X0, X0 + MARK_W

    type_svg, tx0, tx1, ty = type_line()
    type_times = f"0;{kt(T_TYPE_START)};{kt(T_TYPE_END)};1"

    version_y = Y0 + MARK_H + 34.0

    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {SVG_W:.0f} {SVG_H:.0f}" width="{SVG_W:.0f}" height="{SVG_H:.0f}" role="img" aria-label="data2prompt">
<title>data2prompt</title>
<style>
  .mono {{ font-family: 'Cascadia Code','Fira Code','JetBrains Mono',Consolas,'DejaVu Sans Mono',Menlo,monospace; font-size: 14px; }}
  .chrome {{ fill: #73737e; }}
  .data {{ fill: #ececf0; font-weight: bold; }}
  .ver {{ fill: #62626c; font-size: 12.5px; letter-spacing: 0.35em; }}
</style>
<defs>
  <clipPath id="reveal">
    <rect x="{X0:.1f}" y="{Y0 - 4:.1f}" width="{MARK_W:.1f}" height="{MARK_H + 8:.1f}">
      <animate attributeName="width" values="0;0;{MARK_W:.1f};{MARK_W:.1f}" keyTimes="{reveal_times}" dur="{DUR:.0f}s" {PLAY_ONCE}/>
    </rect>
  </clipPath>
  <clipPath id="cipher">
    <rect x="{edge_x1:.1f}" y="{Y0 - 4:.1f}" width="{MARK_W:.1f}" height="{MARK_H + 8:.1f}">
      <animate attributeName="x" values="{edge_x0:.1f};{edge_x0:.1f};{edge_x1:.1f};{edge_x1:.1f}" keyTimes="{reveal_times}" dur="{DUR:.0f}s" {PLAY_ONCE}/>
    </rect>
  </clipPath>
  <clipPath id="typeclip">
    <rect x="{tx0 - 4:.1f}" y="{ty - 16:.1f}" width="{tx1 - tx0 + 12:.1f}" height="24">
      <animate attributeName="width" values="0;0;{tx1 - tx0 + 12:.1f};{tx1 - tx0 + 12:.1f}" keyTimes="{type_times}" dur="{DUR:.0f}s" {PLAY_ONCE}/>
    </rect>
  </clipPath>
  <linearGradient id="edgeglow" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="#ff3b57" stop-opacity="0"/>
    <stop offset="0.62" stop-color="#ff3b57" stop-opacity="0.5"/>
    <stop offset="0.9" stop-color="#ff8093" stop-opacity="0.85"/>
    <stop offset="1" stop-color="#ffffff" stop-opacity="0.95"/>
  </linearGradient>
  <radialGradient id="halo" cx="0.5" cy="0.5" r="0.5">
    <stop offset="0" stop-color="#ff3b57" stop-opacity="0.14"/>
    <stop offset="1" stop-color="#ff3b57" stop-opacity="0"/>
  </radialGradient>
  <pattern id="scan" width="4" height="4" patternUnits="userSpaceOnUse">
    <rect width="4" height="1" fill="#ffffff" opacity="0.022"/>
  </pattern>
</defs>

<rect x="0.5" y="0.5" width="{SVG_W - 1:.0f}" height="{SVG_H - 1:.0f}" rx="12" fill="#0b0b0e" stroke="#26262c"/>
<ellipse cx="{SVG_W / 2:.0f}" cy="{Y0 + MARK_H / 2:.0f}" rx="400" ry="72" fill="url(#halo)"/>

<!-- cipher churn: hidden right-to-left as the sweep resolves -->
<g clip-path="url(#cipher)">{churn_layers()}</g>

<!-- settled wordmark: revealed left-to-right behind the edge -->
<g clip-path="url(#reveal)">{mark_layer(GRADIENT)}</g>

<!-- resolve edge -->
<g opacity="0">
  <animate attributeName="opacity" calcMode="discrete" values="0;1;0" keyTimes="0;{kt(T_SWEEP_START)};{kt(T_SWEEP_END + 0.04)}" dur="{DUR:.0f}s" {PLAY_ONCE}/>
  <rect x="-30" y="{Y0 - 6:.1f}" width="30" height="{MARK_H + 12:.1f}" fill="url(#edgeglow)">
    <animateTransform attributeName="transform" type="translate" values="{edge_x0:.1f} 0;{edge_x0:.1f} 0;{edge_x1 + 30:.1f} 0;{edge_x1 + 30:.1f} 0" keyTimes="{reveal_times}" dur="{DUR:.0f}s" {PLAY_ONCE}/>
  </rect>
</g>

<!-- white flash on settle -->
{mark_layer(("#ffffff", "#ffffff", "#ffffff"), ' opacity="0"')[:-4]}<animate attributeName="opacity" values="0;0;1;0;0" keyTimes="0;{kt(T_FLASH_A)};{kt(T_FLASH_B)};{kt(T_FLASH_C)};1" dur="{DUR:.0f}s" {PLAY_ONCE}/></g>

<!-- version line -->
<text x="{SVG_W / 2:.0f}" y="{version_y:.1f}" text-anchor="middle" class="mono ver">v{version}</text>

<!-- teletype run line -->
<g clip-path="url(#typeclip)">{type_svg}</g>
<g opacity="0">
  <animate attributeName="opacity" calcMode="discrete" values="0;1" keyTimes="0;{kt(T_TYPE_START)}" dur="{DUR:.0f}s" {PLAY_ONCE}/>
  <rect x="0" y="{ty - 12:.1f}" width="8" height="15" fill="#ff3b57">
    <animate attributeName="x" values="{tx0:.1f};{tx0:.1f};{tx1 + 5:.1f};{tx1 + 5:.1f}" keyTimes="{type_times}" dur="{DUR:.0f}s" {PLAY_ONCE}/>
    <!-- cursor blink: intentionally the one animation allowed to loop
         forever, like a live prompt sitting after the typed line -->
    <animate attributeName="opacity" calcMode="discrete" values="1;0" keyTimes="0;0.55" dur="{CURSOR_BLINK_DUR}s" {LOOP_FOREVER}/>
  </rect>
</g>

<rect x="1" y="1" width="{SVG_W - 2:.0f}" height="{SVG_H - 2:.0f}" rx="12" fill="url(#scan)"/>
</svg>'''
    return svg


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=PROJECT_ROOT / "assets" / "banner.svg",
        help="output path for the generated SVG",
    )
    parser.add_argument(
        "--version", dest="version", default=None,
        help="override the version shown in the run-info line "
             "(default: read live from pyproject.toml)",
    )
    return parser.parse_args()


def main() -> None:
    for line in BANNER:
        assert len(line) == COLS, f"row width {len(line)} != {COLS}"
    args = parse_args()
    version = args.version or read_version()
    svg = build(version)
    args.out.write_text(svg, encoding="utf-8")
    print(f"wrote {args.out} ({len(svg):,} chars)")


if __name__ == "__main__":
    main()
