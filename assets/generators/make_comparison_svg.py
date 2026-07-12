"""Generate the output-size comparison as a clean educational chart.

Deliberately NOT in the TUI theme: sans-serif type, a plain zero-based
horizontal bar chart, visible axis and gridlines. Form: magnitude
comparison. data2prompt is the single emphasis mark (validated blue);
competitors are de-emphasis gray. Both light and dark are *selected* modes
of the same chart via a `prefers-color-scheme` media query baked into the
SVG itself — GitHub renders this as a standalone document, so it follows
the viewer's OS/browser theme automatically, light or dark.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))
from shared import (  # noqa: E402
    ACCENT_DARK, ACCENT_LIGHT, AXIS_DARK, AXIS_LIGHT, BORDER_DARK,
    BORDER_LIGHT, GRID_DARK, GRID_LIGHT, INK_DARK, INK_LIGHT, MUTED_DARK,
    MUTED_LIGHT, NEUTRAL_DARK, NEUTRAL_LIGHT, PROJECT_ROOT, SURFACE_DARK,
    SURFACE_LIGHT,
)

W, H = 960.0, 420.0
FONT = "-apple-system,'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"

PLOT_X = 190.0
PLOT_R = 80.0
PLOT_W = W - PLOT_X - PLOT_R
X_MAX = 24_000

ROWS: List[Tuple[str, int, bool]] = [
    ("repomix", 22_085, False),
    ("code2prompt", 9_304, False),
    ("data2prompt", 241, True),
]

BAR_H = 34.0
ROW_GAP = 62.0
PLOT_Y = 148.0


def x_of(kb: float) -> float:
    return PLOT_X + PLOT_W * kb / X_MAX


def bar_path(x0: float, y: float, w: float, h: float, r: float) -> str:
    """Left-flat, right-rounded bar (rounded data end only, per spec)."""
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
    )

    # Theme: CSS custom properties, selected (not auto-flipped) per mode.
    parts.append(f'''<style>
  .viz {{
    --surface: {SURFACE_LIGHT}; --ink: {INK_LIGHT}; --muted: {MUTED_LIGHT};
    --grid: {GRID_LIGHT}; --axis: {AXIS_LIGHT}; --border: {BORDER_LIGHT};
    --neutral: {NEUTRAL_LIGHT}; --accent: {ACCENT_LIGHT};
    --accent-soft: {ACCENT_LIGHT}33; --badge-bg: {ACCENT_LIGHT}1a;
    --row-band: #00000005;
  }}
  @media (prefers-color-scheme: dark) {{
    .viz {{
      --surface: {SURFACE_DARK}; --ink: {INK_DARK}; --muted: {MUTED_DARK};
      --grid: {GRID_DARK}; --axis: {AXIS_DARK}; --border: {BORDER_DARK};
      --neutral: {NEUTRAL_DARK}; --accent: {ACCENT_DARK};
      --accent-soft: {ACCENT_DARK}3d; --badge-bg: {ACCENT_DARK}26;
      --row-band: #ffffff06;
    }}
  }}
  text {{ font-family: {FONT}; fill: var(--ink); }}
  .muted {{ fill: var(--muted); }}
  .card {{ fill: var(--surface); stroke: var(--border); }}
  .grid {{ stroke: var(--grid); }}
  .axis {{ stroke: var(--axis); }}
  .neutral-bar {{ fill: var(--neutral); }}
  .badge-bg {{ fill: var(--badge-bg); }}
  .badge-text {{ fill: var(--accent); font-weight: 600; }}
</style>
<defs>
  <linearGradient id="accentFill" x1="0" y1="0" x2="1" y2="0">
    <stop offset="0" stop-color="{ACCENT_LIGHT}" class="grad0"/>
    <stop offset="1" stop-color="{ACCENT_LIGHT}" class="grad1"/>
  </linearGradient>
  <filter id="barShadow" x="-20%" y="-60%" width="140%" height="240%">
    <feDropShadow dx="0" dy="1.5" stdDeviation="2" flood-color="{ACCENT_LIGHT}" flood-opacity="0.35"/>
  </filter>
</defs>
<style>
  #accentFill .grad0 {{ stop-color: {ACCENT_LIGHT}; }}
  #accentFill .grad1 {{ stop-color: {ACCENT_LIGHT}cc; }}
  #barShadow feDropShadow {{ flood-color: {ACCENT_LIGHT}; }}
  @media (prefers-color-scheme: dark) {{
    #accentFill .grad0 {{ stop-color: {ACCENT_DARK}; }}
    #accentFill .grad1 {{ stop-color: {ACCENT_DARK}cc; }}
    #barShadow feDropShadow {{ flood-color: {ACCENT_DARK}; flood-opacity: 0.55; }}
  }}
</style>
<g class="viz">
<rect x="0.5" y="0.5" width="{W - 1:.0f}" height="{H - 1:.0f}" rx="14" class="card"/>
'''
    )

    # Eyebrow + title + subtitle
    parts.append(
        f'<text x="40" y="46" font-size="11.5" font-weight="700" '
        f'letter-spacing="0.14em" class="muted">OUTPUT SIZE</text>'
        f'<text x="40" y="76" font-size="21" font-weight="600">'
        'Same project, three tools, one command each</text>'
        f'<text x="40" y="102" font-size="13.5" class="muted">a data-heavy '
        'analytics project &#183; each tool&#8217;s default settings &#183; '
        'lower is better</text>'
    )

    # Gridlines + tick labels every 6,000 KB
    plot_bottom = PLOT_Y + len(ROWS) * ROW_GAP - (ROW_GAP - BAR_H) + 14
    for kb in range(0, X_MAX + 1, 6_000):
        gx = x_of(kb)
        cls = "axis" if kb == 0 else "grid"
        parts.append(
            f'<line x1="{gx:.1f}" y1="{PLOT_Y - 20:.1f}" x2="{gx:.1f}" '
            f'y2="{plot_bottom:.1f}" class="{cls}" stroke-width="1"/>'
            f'<text x="{gx:.1f}" y="{plot_bottom + 22:.1f}" font-size="11.5" '
            f'class="muted" text-anchor="middle">{kb:,}</text>'
        )
    parts.append(
        f'<text x="{PLOT_X + PLOT_W / 2:.1f}" y="{plot_bottom + 46:.1f}" '
        f'font-size="12" class="muted" text-anchor="middle">output size (KB)'
        '</text>'
    )

    # Row bands (subtle zebra striping for polish, not decoration-for-its-own-sake)
    band_y = PLOT_Y - (ROW_GAP - BAR_H) / 2
    for i in range(len(ROWS)):
        parts.append(
            f'<rect x="{PLOT_X - 14:.1f}" y="{band_y + i * ROW_GAP:.1f}" '
            f'width="{PLOT_W + PLOT_R - 4:.1f}" height="{ROW_GAP:.1f}" '
            f'fill="var(--row-band)"/>'
        )

    # Bars with direct labels
    y = PLOT_Y
    for label, kb, emphasis in ROWS:
        weight = "600" if emphasis else "400"
        w = max(PLOT_W * kb / X_MAX, 3.0)
        swatch_fill = 'url(#accentFill)' if emphasis else 'var(--neutral)'
        bar_cls = "" if emphasis else ' class="neutral-bar"'
        shadow = ' filter="url(#barShadow)"' if emphasis else ""
        parts.append(
            f'<rect x="26" y="{y + BAR_H / 2 - 5:.1f}" width="10" height="10" '
            f'rx="3" fill="{swatch_fill}"/>'
            f'<text x="{PLOT_X - 14:.1f}" y="{y + BAR_H / 2 + 4.5:.1f}" '
            f'font-size="14.5" font-weight="{weight}" '
            f'text-anchor="end">{label}</text>'
        )
        fill_attr = f'fill="{swatch_fill}"' if emphasis else ""
        parts.append(
            f'<path d="{bar_path(PLOT_X, y, w, BAR_H, 5.0)}" {fill_attr}'
            f'{bar_cls}{shadow}/>'
        )
        parts.append(
            f'<text x="{PLOT_X + w + 10:.1f}" y="{y + BAR_H / 2 + 4.5:.1f}" '
            f'font-size="14" font-weight="700">{kb:,} <tspan '
            f'font-size="11.5" font-weight="500" class="muted">KB</tspan>'
            '</text>'
        )
        if emphasis:
            badge_text = (
                "80–85% more token-efficient — schema, column "
                "stats and row samples all intact"
            )
            badge_x = PLOT_X + w + 10 + 78
            badge_cy = y + BAR_H / 2
            badge_w = len(badge_text) * 6.5 + 28
            parts.append(
                f'<rect x="{badge_x:.1f}" y="{badge_cy - 12:.1f}" '
                f'width="{badge_w:.1f}" height="24" rx="12" class="badge-bg"/>'
                f'<text x="{badge_x + 14:.1f}" y="{badge_cy + 4.5:.1f}" '
                f'font-size="12.5" class="badge-text">{badge_text}</text>'
            )
        y += ROW_GAP

    parts.append("</g></svg>")
    return "".join(parts)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out", type=Path, default=PROJECT_ROOT / "assets" / "comparison.svg",
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
