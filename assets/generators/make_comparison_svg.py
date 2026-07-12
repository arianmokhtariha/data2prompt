"""Generate the output-size comparison as a clean educational chart.

Deliberately NOT in the TUI theme: light surface, sans-serif type, visible
axis with gridlines. Form: magnitude comparison, horizontal bars, zero-based
axis. data2prompt is the single emphasis mark (validated blue); competitors
are de-emphasis gray. Identity is carried by direct row labels.
"""
from __future__ import annotations

from pathlib import Path
from typing import List

W, H = 960.0, 400.0
FONT = ("-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif")

INK = "#1f2430"          # primary text
MUTED = "#667085"        # secondary text
GRID = "#eef0f3"
AXIS = "#d5d9df"
NEUTRAL = "#7f8894"      # de-emphasis bars (contrast >= 3:1, validated)
ACCENT = "#2a78d6"       # emphasis bar (palette slot 1, validated)
SURFACE = "#ffffff"

PLOT_X = 190.0
PLOT_R = 80.0
PLOT_W = W - PLOT_X - PLOT_R
X_MAX = 24_000

ROWS = [
    ("repomix", 22_085, False),
    ("code2prompt", 9_304, False),
    ("data2prompt", 241, True),
]

BAR_H = 30.0
ROW_GAP = 58.0
PLOT_Y = 128.0


def x_of(kb: float) -> float:
    return PLOT_X + PLOT_W * kb / X_MAX


def bar_path(x0: float, y: float, w: float, h: float, r: float) -> str:
    """Left-flat, right-rounded bar (rounded data end only)."""
    r = min(r, w / 2, h / 2)
    return (
        f'M {x0:.1f} {y:.1f} h {w - r:.1f} q {r:.1f} 0 {r:.1f} {r:.1f} '
        f'v {h - 2 * r:.1f} q 0 {r:.1f} {-r:.1f} {r:.1f} h {-(w - r):.1f} Z'
    )


def build() -> str:
    parts: List[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" '
        f'width="{W:.0f}" height="{H:.0f}" role="img" aria-label="Output size '
        'comparison: repomix 22,085 KB, code2prompt 9,304 KB, data2prompt '
        '241 KB. data2prompt is 80 to 85 percent more token-efficient.">'
        '<title>Packed output size: same project, three tools</title>'
        f'<style>text{{font-family:{FONT};}}</style>'
        f'<rect x="0.5" y="0.5" width="{W - 1:.0f}" height="{H - 1:.0f}" '
        f'rx="10" fill="{SURFACE}" stroke="#e2e5ea"/>'
    )

    # Title + subtitle
    parts.append(
        f'<text x="40" y="52" font-size="19" font-weight="600" fill="{INK}">'
        'Packed output size &#8212; same project, three tools</text>'
        f'<text x="40" y="78" font-size="13.5" fill="{MUTED}">a data-heavy '
        'analytics project, packed with each tool&#8217;s default settings '
        '&#183; lower is better</text>'
    )

    # Gridlines + tick labels every 6,000 KB
    plot_bottom = PLOT_Y + len(ROWS) * ROW_GAP - (ROW_GAP - BAR_H) + 12
    for kb in range(0, X_MAX + 1, 6_000):
        gx = x_of(kb)
        stroke = AXIS if kb == 0 else GRID
        parts.append(
            f'<line x1="{gx:.1f}" y1="{PLOT_Y - 14:.1f}" x2="{gx:.1f}" '
            f'y2="{plot_bottom:.1f}" stroke="{stroke}" stroke-width="1"/>'
            f'<text x="{gx:.1f}" y="{plot_bottom + 20:.1f}" font-size="11.5" '
            f'fill="{MUTED}" text-anchor="middle">{kb:,}</text>'
        )
    parts.append(
        f'<text x="{PLOT_X + PLOT_W / 2:.1f}" y="{plot_bottom + 44:.1f}" '
        f'font-size="12" fill="{MUTED}" text-anchor="middle">output size (KB)'
        '</text>'
    )

    # Bars with direct labels
    y = PLOT_Y
    for label, kb, emphasis in ROWS:
        fill = ACCENT if emphasis else NEUTRAL
        weight = "600" if emphasis else "400"
        w = max(PLOT_W * kb / X_MAX, 3.0)
        parts.append(
            f'<text x="{PLOT_X - 14:.1f}" y="{y + BAR_H / 2 + 4.5:.1f}" '
            f'font-size="14" font-weight="{weight}" fill="{INK}" '
            f'text-anchor="end">{label}</text>'
        )
        parts.append(
            f'<path d="{bar_path(PLOT_X, y, w, BAR_H, 4.0)}" fill="{fill}"/>'
        )
        parts.append(
            f'<text x="{PLOT_X + w + 10:.1f}" y="{y + BAR_H / 2 + 4.5:.1f}" '
            f'font-size="13.5" font-weight="600" fill="{INK}">{kb:,} KB</text>'
        )
        if emphasis:
            note_y = y + BAR_H / 2 + 4.5
            note_x = PLOT_X + w + 10 + 76
            parts.append(
                f'<text x="{note_x:.1f}" y="{note_y:.1f}" font-size="12.5" '
                f'fill="{MUTED}">&#8212;&#160; 80&#8211;85% more '
                'token-efficient, with schema, column stats and row samples '
                'intact</text>'
            )
        y += ROW_GAP

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    out = Path(__file__).resolve().parents[1] / "comparison.svg"
    svg = build()
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({len(svg):,} chars)")


if __name__ == "__main__":
    main()
