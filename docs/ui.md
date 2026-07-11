# User Interface (UI)

The `data2prompt` Terminal User Interface is built with the
[`rich`](https://github.com/Textualize/rich) library and themed after the
**BLACKSITE** palette — a near-monochrome, forensic-console look: bright white
for data, dim gray for chrome, a crimson accent for structure (deepened into a
three-shade gradient on the wordmark), yellow reserved for warnings, and
reverse-red reserved for errors. All UI logic is
encapsulated in the [`UIHandler`](../src/data2prompt/ui.py) class; the
orchestration layer never emits markup of its own.

## Design Principles

1. **Color = meaning.** Every color is a semantic channel (see the table
   below). Nothing decorative is bright, so the eye lands on information.
2. **The report is the product.** The progress bar is transient and clears
   itself; warnings and the final report own the screen at the end.
3. **Compact over complete.** The final report shows the token-heaviest files
   and *every* flagged file — never hundreds of unremarkable rows.
4. **Numbers get a visual.** Every important quantity is doubled by a
   proportional `▰▱` bar — the token gauge, the composition chart, the
   per-file spark bars. The gauge and composition bars are scaled against
   their **total**, so the fill literally reads as the percentage printed
   next to it (one cell = 2% at the full 50-column track). Every bar draws
   itself to exactly the width its row grants it — a bar is never
   ellipsis-truncated by the layout.
5. **Sections are ticked.** Section titles render as an accent `▰▰` tick
   followed by letter-spaced bold-white caps and a dim rule
   (`▰▰ C O M P O S I T I O N ───`). Reverse-video is reserved exclusively
   for the warning and error channels — an inverted chip always means
   "look here".
6. **Fail loud.** A parser status the UI does not recognize renders in the
   error channel, never as silently fine.

### Semantic Color Channels

Defined in [`constants.py`](../src/data2prompt/constants.py) (UI section):

| Constant | Value | Channel |
|:---|:---|:---|
| `UI_ACCENT` | `#ff3b57` (crimson) | wordmark, markers, bar fill |
| `UI_CHROME` | `grey35` | rules, labels, footnotes, bar tracks |
| `UI_CHROME_BRIGHT` | `grey58` | panel borders, secondary labels, ok-statuses |
| `UI_DATA` / `UI_DATA_BOLD` | `white` / `bold white` | paths, names, headline numbers |
| `UI_WARN` | `yellow` | attention items, warn statuses, warnings |
| `UI_ERROR` | `bold white on red3` | error statuses, fatal messages |
| `UI_HEADING` | `bold white` | section/panel titles (after the accent `▰▰` tick) |
| `UI_WARN_CHIP` | `bold black on yellow` | attention count badges |

## UIHandler Class

The [`UIHandler`](../src/data2prompt/ui.py) class serves as the central point
for all terminal output.

### Core Responsibilities

| Responsibility | Description |
|:---|:---|
| **Event Handling** | Processes lifecycle events: `on_start`, `on_progress` |
| **Progress Tracking** | Manages the transient single-line progress bar |
| **Visual Components** | Renders the banner glitch sweep, panels, tables, gauges |
| **Final Report** | Prints the "TRANSMISSION COMPLETE" report panel |
| **Error Display** | Themed warning panels and inline warn/error lines |

### Event Handlers

```python
def on_start(
    self,
    project_name: str,
    format_name: str,
    output_label: str,
    total_files: int,
) -> None:
    """Event handler for process start: renders the themed header."""
```

`main.py` passes the project directory name, the output format, the output
label (`"(clipboard)"` when `--clipboard` is active, otherwise the output
filename), and the number of discovered files — so the header can state what
is about to happen before any work starts.

```python
def on_progress(
    self, action: str = "", target: str = "", advance: int = 0
) -> None:
```

`on_progress` takes **plain strings** — an action verb ("Sampling") and a
target (usually a filename). All markup and theming is applied inside the
UI layer via `_format_task()`, which pads both fields to fixed widths
(`_ACTION_WIDTH` / `_TARGET_WIDTH`) so the progress line never jitters, and
escapes the target so bracket characters in filenames cannot break markup.
Calling it with only `advance=1` advances the bar without changing the
description.

Errors and warnings are surfaced directly through the
[`print_error()`](../src/data2prompt/ui.py), [`print_warning()`](../src/data2prompt/ui.py),
and [`print_warning_panel()`](../src/data2prompt/ui.py) display methods, not
via dedicated event handlers.

## UI Components

### Startup Header — Glitch Sweep

`print_header()` renders the compact wordmark (`BANNER` in `constants.py`,
under 80 columns) with a **glitch sweep** in three beats:

1. **Cipher churn.** Unresolved columns render as dim block-glyph static
   (`UI_CIPHER_GLYPHS`) that changes every frame — restrained redaction
   noise, deliberately no letters or symbols. The wordmark's silhouette is
   preserved: spaces stay spaces.
2. **Resolve edge.** A hot edge (`█▓▒`, white-tipped) sweeps left-to-right
   over `UI_REVEAL_DURATION` seconds at `UI_FRAME_DELAY` per frame; behind
   it the glyphs settle into the wordmark's crimson gradient
   (`UI_BANNER_GRADIENT`, one shade per row, hot top → deep bottom).
3. **Flash settle.** When the sweep completes, the whole wordmark flashes
   hot white for `UI_FLASH_FRAMES` frames (~40 ms), then settles into the
   final gradient.

Two guards keep this well-behaved:

- **TTY guard**: the sweep (and the teletype line below) runs only when
  `console.is_terminal` is true. Piped or CI output gets an instant static
  gradient render — no animation frames ever reach a non-interactive stream.
- Every frame is produced by `_banner_frame(revealed_cols, frame)`, a pure
  function of the reveal position and frame index; the churn comes from
  `cipher_mask()`, a deterministic spatial hash. There is still no
  randomness anywhere in the animation.

After the wordmark, the header prints a dim version line (no tagline — the
user installed the tool and knows what it does) and a run-info line revealed
with a one-pass teletype cursor (`▮`, via `_type_line()`):

```
▰ TARGET my-project   ▰ FORMAT markdown   ▰ OUT PROMPT.md   ▰ FILES 128
```

### Progress Bar

The [`progress_bar()`](../src/data2prompt/ui.py) context manager shows a
single-line, information-dense bar and yields the handler:

```
⠹ Sampling   sales_data.csv   ━━━━━━╺━━━ 42/130 32% 0:00:03
```

Columns: `SpinnerColumn` (crimson dots) · task description (accent action +
white target, fixed width) · `BarColumn` (gray track, crimson fill) ·
`MofNCompleteColumn` · `TaskProgressColumn` · `TimeElapsedColumn`. The
`Progress` is created with `transient=True`, so it erases itself when the
context exits and the final report owns the screen.

## Final Report

`print_final_report()` renders one square-cornered panel (bright-gray
border, vertical padding for breathing room). The panel title and every
section title are **ticked headers** — an accent `▰▰` marker plus the
letter-spaced title (`spaced_caps()`), produced by `_section_header()`,
each preceded by a blank spacer line so sections are unmistakable at a
glance. (Bars are shortened here for page width — the gauge and composition
tracks cap at 50 columns, one cell = 2%.)

`print_final_report()` accepts a trailing, optional
`budget_report: Optional['BudgetReport'] = None` parameter. `main.py` passes
`outcome.report if outcome is not None else None`, so it is only non-`None`
on a `--budget` run that actually reached the report (an infeasible run never
gets here — it exits via `print_budget_failure()` first, see
[Budget Failure Panel](#budget-failure-panel)). `BudgetReport` is imported
under `TYPE_CHECKING` only, alongside `FileSummary` — a runtime import would
create a `budget → parsers → utils → ui` cycle (same rationale as the
existing `FileSummary` import, see [Global Instance](#global-instance)).

```
┌ ▰▰ T R A N S M I S S I O N  C O M P L E T E ────────────────────┐
│                                                                  │
│  OUTPUT  PROMPT.md · 412.3 KB                                    │
│  TOKENS  96,420 (o200k_base)  ▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱ 48% of 200K   │
│  TIME    3.2s · 128 files                                        │
│                                                                  │
│  ▰▰ C O M P O S I T I O N ───────────────────────────────────────│
│  TYPE               FILES  SHARE                  TOKENS      %  │
│  Notebook              ×6  ▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱   41,210    46%  │
│  CSV                  ×12  ▰▰▰▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱   24,830    28%  │
│  Excel · 7 sheets      ×2  ▰▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱   14,210    16%  │
│  other                 ×9  ▰▰▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱    9,140    10%  │
│                                                                  │
│  ▰▰ A T T E N T I O N ───────────────────────────────────────────│
│  ▓4▓ truncated    ▓2▓ binary skipped    ▓1▓ env redacted         │
│                                                                  │
│  ▰▰ H E A V I E S T  P A Y L O A D S ────────────────────────────│
│        FILE          TYPE      STATUS   TOKENS                   │
│  0x01  data/big.csv  CSV       Sampled  12,400  ▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰▰ │
│  0x02  nb/eda.ipynb  Notebook  Cleaned   8,210  ▰▰▰▰▰▰▰▰▰▰▱▱▱▱▱▱ │
│        · · · flagged · · ·                                       │
│  0x0B  logo.png      Binary    Skipped       0  ▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱▱ │
│  + 118 more · full index inside PROMPT.md                        │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

(`▓…▓` marks the reverse-yellow attention badges — with the section titles
no longer inverted, reverse-video appears only in the warning and error
channels.)

Section by section:

- **Summary grid** — output destination (file path, or `(clipboard)` when
  `--clipboard` is used) with human-readable size (`_format_size()`: KB below
  1 MB, MB above), the token count and encoding method with a **token
  gauge** (`_token_gauge()`: a `▰▱` track of `total_tokens` against
  `CONTEXT_WINDOW_REFERENCE` = 200 000, capped at `REPORT_GAUGE_WIDTH` = 50
  columns — one cell = 2% of the window at the cap; the gauge turns yellow
  at ≥ 85% of the window and red past 100%; the whole line is a one-row
  grid so the gauge sizes itself between the count and the trailing
  percentage label), and the elapsed wall-clock time (measured in
  `main.py`) with the total file count.
- **BUDGET** *(only when `--budget` was requested)* — see
  [Budget Section](#budget-section-only-when---budget-was-requested) below.
- **COMPOSITION** — a per-type token-share **bar chart** built by
  `_composition_chart()` from the actual per-file summaries (not the flat
  stat counters), under a dim header row (`TYPE FILES SHARE TOKENS %`):
  type label · file count (`×N`) · a bar capped at `REPORT_CHART_WIDTH` =
  50 columns and **scaled to the total of all rows**, so the fill visually
  equals the percent column (one cell = 2% at the cap) · token sum ·
  percent of all file tokens.
  Row selection is the pure `summarize_composition()` (below). The Excel
  row is annotated with the total sheet count from `stats`. Falls back to
  a dim "nothing tokenized" note if no file contributed tokens.
- **ATTENTION** — badge-counted items from `_attention_line()` driven by the
  `_ATTENTION_SPECS` table (truncated, binary skipped, excluded, env
  redacted). Each count renders as a reverse-yellow chip (`UI_WARN_CHIP`)
  followed by its label. The section is omitted entirely on a clean run.
- **HEAVIEST PAYLOADS** — the compact file table (see below), with a dim hex
  gutter (`0x01`, `0x02`, …), the file's **relative path** (ellipsized past
  44 cells), type, status, right-aligned token count, and a **spark bar**
  capped at `REPORT_SPARK_WIDTH` = 16 columns, scaled to the heaviest listed
  file, so relative weight is visible without reading the numbers (a
  deliberately different scale from COMPOSITION: sparks compare files, not
  percentages). Statuses are colored by severity: ok → bright gray, warn →
  yellow, error → reverse-red.
- **Footer** — `+ N more · full index inside <output>` when rows were
  omitted, pointing at the File Index inside the generated document.

Every bar is a `_CellBar` — a small frozen-dataclass renderable that
delegates sizing to Rich itself: it advertises its width range (floor
`_MIN_BAR_WIDTH` = 8, ceiling its `REPORT_*_WIDTH` cap) through
`__rich_measure__`, then draws to exactly the width its table column was
actually granted. That makes truncation structurally impossible — however
long the neighboring path, type, or status strings get, the bar shrinks
instead of overflowing into an ellipsis. Inside the track,
`REPORT_BAR_CELL_WIDTH` sets the **cell density**: columns occupied per
cell (1 = a cell in every column, the default contiguous look; 2 spaces
cells one blank column apart with half as many cells), independent of the
track's on-screen length.

### Budget Section (only when `--budget` was requested)

When `print_final_report()` receives a non-`None` `budget_report`, two things
change in the report above:

1. The TOKENS row's gauge is built with `budget=budget_report.
   requested_tokens` instead of the default reference — see
   [Budget-Scaled Token Gauge](#budget-scaled-token-gauge) below.
2. A **BUDGET** section is inserted right after the summary grid, *before*
   COMPOSITION:

```
│  ▰▰ B U D G E T ──────────────────────────────────────────────────│
│  requested 50,000 · final 47,820 (96% of budget)                  │
│  ▰ csv-sample-size   15 → 5  6 tabular data file(s) re-sampled     │
│  ▰ schema-only   off → on  9 data file(s) reduced to schema only   │
│  − data/big.csv · ~12,400 tokens omitted                          │
```

Rendered by `_budget_lines(self, report, total_tokens) -> RenderableType`,
under the `_section_header("BUDGET")` ticked header:

- **Headline**: `"requested "` (chrome) + `{requested:,}` (bold white) +
  `" · final {total:,} ({pct}% of budget)"` (bright chrome), where
  `pct = round(100 * total_tokens / report.requested_tokens)`.
- **One line per adjustment**: an accent `"▰ "` marker, the parameter name
  (`UI_DATA`), then `"{requested} → {adjusted}"` (`UI_DATA_BOLD`), then the
  scope string (`UI_CHROME`) — the exact wording documented in
  [budget.md § The De-escalation Ladder](budget.md#the-de-escalation-ladder).
- **One line per omitted file**: the whole line renders in the **warn**
  channel (`UI_WARN`) — content removal is warn-level information — as
  `"− {path} · ~{tokens:,} tokens omitted"`.
- **Nothing changed**: if `report.adjustments` and `report.omitted` are both
  empty (the first, unmodified-config attempt already fit), a single dim
  chrome line renders instead: `"fit within budget — no parameter
  adjustments needed"`.

#### Budget-Scaled Token Gauge

```python
def _token_gauge(
    self, total_tokens: int, method: str, budget: Optional[int] = None
) -> Table:
```

`_token_gauge()` gained an optional `budget` parameter. When given, the
gauge's reference denominator becomes `budget` instead of
`CONTEXT_WINDOW_REFERENCE`, and the trailing label reads `" {pct}% of
{budget:,} budget"` instead of `" {pct}% of {window_label} window"` — same
color thresholds (yellow at ≥ 85%, red past 100%) and same `_CellBar`
sizing behavior, just against a different denominator.
`print_final_report()` passes `budget=budget_report.requested_tokens` only
when a `budget_report` was given; otherwise the gauge behaves exactly as
before.

### Budget Failure Panel

```python
def print_budget_failure(
    self, requested: int, minimum_tokens: int, report: 'BudgetReport'
) -> None:
```

Called by `main.py` in place of `print_final_report()` when
`outcome.fits` is `False` — the fully de-escalated document still exceeds
the budget, so nothing was written or copied
(see [budget.md § Outcomes](budget.md#outcomes-fits-vs-infeasible)). Renders
a square-cornered `Panel` (`box.SQUARE`, `border_style="red3"`) titled
`" ■ BUDGET INFEASIBLE "` in the reverse `UI_ERROR` style, left-aligned. Body
(plain `Text`, no markup — paths and scope strings are never trusted as
markup input):

- `"Requested budget   {requested:,} tokens"`
- `"Minimum achievable  {minimum_tokens:,} tokens"` (the number in
  `UI_DATA_BOLD`)
- a chrome line: `"even with every data cap at its floor"`, extended with
  `" and all {len(report.omitted)} file(s) omitted"` only when at least one
  file was omitted — the panel never claims omissions happened if none did
- one dim chrome line per adjustment that was tried:
  `"{parameter} {requested} → {adjusted}"` — **only the count** of omitted
  files appears above; individual omitted paths are never listed here (a
  failed run can have omitted hundreds of files, and the panel stays
  compact by design, same philosophy as `select_report_rows()`'s
  flagged-file cap in the success report)
- a final `UI_WARN` line: `"No output was produced."`

### Report and Animation Logic (pure helpers)

Seven module-level pure functions carry the report's and the animation's
logic contracts and are covered by
[`tests/test_ui_report.py`](../tests/test_ui_report.py):

```python
def status_severity(status: str) -> Literal["ok", "warn", "error"]: ...
def select_report_rows(
    files: List[FileSummary], top_n: int
) -> Tuple[List[FileSummary], int]: ...
def bar_cells(value: int, max_value: int, cells: int) -> int: ...
def bar_glyphs(filled: int, cells: int, cell_width: int) -> Tuple[str, str]: ...
def summarize_composition(
    files: List[FileSummary], max_rows: int
) -> List[Tuple[str, int, int]]: ...
def cipher_mask(line: str, frame: int, row: int) -> str: ...
def spaced_caps(title: str) -> str: ...
```

- `status_severity()` maps a parser status onto the ok/warn/error channels
  using the `_OK_STATUSES` / `_WARN_STATUSES` sets. **Unknown statuses return
  `"error"`** so a future parser status can never render as silently fine.
  `_WARN_STATUSES` includes `"Omitted (Budget)"` (added alongside `Redacted`,
  `Skipped (Env)`, `Skipped (No pyarrow)`) — a `--budget` run's omitted files
  render as a yellow warn status in the HEAVIEST PAYLOADS table, never as the
  red unknown-status error channel.
- `select_report_rows()` returns the `REPORT_TOP_FILES` (10) token-heaviest
  files plus **every** flagged (non-ok) file beyond them — a redacted `.env`
  with 0 tokens is always listed — together with the count of hidden files.
  It sorts a copy; the caller's list is **not mutated**. In the rendered
  table, flagged extras appear below a dim `· · · flagged · · ·` divider.
- `bar_cells()` computes the filled-cell count for every proportional bar.
  It is **zero-safe** (a run where every file was skipped gives a max of 0 —
  the bar renders empty instead of dividing by zero) and guarantees any
  positive value fills **at least one cell**, so small files never look like
  missing data. Values beyond the reference clamp at full width.
- `bar_glyphs()` renders a track's cells as text — `(filled part, empty
  part)`, each cell exactly `cell_width` columns (glyph + blank columns) so
  tracks stay aligned across table rows at every density. A non-positive
  width clamps to 1 instead of crashing the report.
- `summarize_composition()` groups per-file tokens by type for the chart:
  zero-token files are dropped (they belong to ATTENTION), parenthetical
  type variants merge (`"Excel (3 sheets)"` → `"Excel"`), rows sort
  heaviest-first, and types beyond `REPORT_COMPOSITION_ROWS` (6) fold into
  an exact `"other"` row so the chart never sprawls or understates totals.
- `cipher_mask()` produces the banner churn **deterministically**: an XOR
  spatial hash of prime products of frame, row, and column picks each
  glyph. XOR rather than a plain sum, so the frame term can never
  degenerate to a constant modulo the glyph count and freeze the churn.
  Spaces map to spaces, so the wordmark silhouette survives every frame.
- `spaced_caps()` letter-spaces section titles with a double space between
  words, so multi-word titles (`"HEAVIEST PAYLOADS"`) never fuse into one.

## Error and Warning Display

### Warning Panel

```python
def print_warning_panel(self, message: str) -> None:
```

A square yellow-bordered panel whose title is a reverse-yellow `▲ WARNING`
chip. The message may contain Rich markup (callers in `main.py` use `[bold]`
for emphasis), so it is rendered unescaped.

### Inline Warning/Error

```python
def print_warning(self, message: str) -> None:   # ▲ WARN <message>
def print_error(self, message: str) -> None:     #  ERROR  <message>
```

Both treat the message as plain text and escape it, so file paths containing
bracket characters cannot break the markup. `print_error` renders its label
in the reverse-red `UI_ERROR` channel.

## Integration with Main Processing

```python
# From main.py
ui.on_start(
    project_name=project_path.name,
    format_name=config.format,
    output_label="(clipboard)" if config.clipboard else config.output,
    total_files=len(all_files),
)

with ui.progress_bar("Initializing", total=total_steps) as handler:
    handler.on_progress("Indexing", "project tree")
    tree_text = scanner.generate_tree(all_files)
    handler.on_progress(advance=1)
    # ... per file: handler.on_progress(action, file_path.name)
```

`main.py` measures elapsed time with `time.perf_counter()` and passes it as
the final `elapsed_seconds` argument of `print_final_report()`.

On a `--budget` run, `main.py` calls `fit_to_budget()` (see
[budget.md](budget.md)) after the per-file loop. If the result is infeasible,
`main.py` calls `ui.print_budget_failure(...)` instead of
`ui.print_final_report(...)` and raises `SystemExit(1)` — the success report
is never printed on that path. If it fits, `print_final_report()` is called
as usual with `budget_report=outcome.report`.

## Global Instance

A global [`ui`](../src/data2prompt/ui.py) instance is exported for use
throughout the application:

```python
# Global UI instance
ui = UIHandler()
```

The `FileSummary` type is imported under `TYPE_CHECKING` only — a runtime
import would create a `utils → ui → parsers → utils` cycle (guarded by
`tests/test_import_hygiene.py`). `BudgetReport` (from
[`budget.py`](budget.md)) is imported the same way, for the same reason: a
runtime import would create a `budget → parsers → utils → ui` cycle, since
`budget.py` already imports `parsers.py` and `utils.py` at runtime.

## Constants Used

| Constant | Value | Purpose |
|:---|:---|:---|
| `UI_ACCENT` … `UI_WARN_CHIP` | see table above | semantic color channels |
| `UI_SECTION_MARKER` | `"▰▰"` | accent tick before section/panel titles |
| `UI_REVEAL_DURATION` | `0.5` | banner sweep duration (seconds) |
| `UI_FRAME_DELAY` | `0.02` | animation frame delay (seconds) |
| `UI_FLASH_FRAMES` | `2` | white flash frames before the gradient settles |
| `UI_CIPHER_GLYPHS` | `"░▒▓▌▐▄▀"` | block static churned ahead of the reveal edge |
| `UI_BANNER_GRADIENT` | 3 crimson hexes | per-row wordmark gradient, hot top → deep bottom |
| `REPORT_TOP_FILES` | `10` | heaviest files listed in the report |
| `REPORT_COMPOSITION_ROWS` | `6` | file-type rows in the composition chart |
| `REPORT_GAUGE_WIDTH` | `50` | token-gauge track cap in columns (1 cell = 2%) |
| `REPORT_CHART_WIDTH` | `50` | composition track cap in columns (1 cell = 2%) |
| `REPORT_SPARK_WIDTH` | `16` | payload spark-bar track cap in columns |
| `REPORT_BAR_CELL_WIDTH` | `1` | bar cell density: columns per cell |
| `CONTEXT_WINDOW_REFERENCE` | `200_000` | token-gauge reference window |
| `BANNER` | list | compact wordmark (< 80 columns) |
