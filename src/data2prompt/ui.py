import time
from contextlib import contextmanager
from dataclasses import dataclass
from typing import (
    Dict,
    Generator,
    List,
    Literal,
    Optional,
    Tuple,
    TYPE_CHECKING,
)

from rich import box
from rich.console import (
    Console,
    ConsoleOptions,
    Group,
    RenderableType,
    RenderResult,
)
from rich.live import Live
from rich.markup import escape
from rich.measure import Measurement
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from data2prompt import __version__
from data2prompt.constants import (
    BANNER,
    CONTEXT_WINDOW_REFERENCE,
    REPORT_BAR_CELL_WIDTH,
    REPORT_CHART_WIDTH,
    REPORT_COMPOSITION_ROWS,
    REPORT_GAUGE_WIDTH,
    REPORT_SPARK_WIDTH,
    REPORT_TOP_FILES,
    UI_ACCENT,
    UI_BANNER_GRADIENT,
    UI_CHROME,
    UI_CHROME_BRIGHT,
    UI_CIPHER_GLYPHS,
    UI_DATA,
    UI_DATA_BOLD,
    UI_ERROR,
    UI_FLASH_FRAMES,
    UI_FRAME_DELAY,
    UI_HEADING,
    UI_REVEAL_DURATION,
    UI_SECTION_MARKER,
    UI_WARN,
    UI_WARN_CHIP,
)

if TYPE_CHECKING:
    # Imported only for type hints — a runtime import would create a
    # utils → ui → parsers → utils cycle.
    from data2prompt.parsers import FileSummary


Severity = Literal["ok", "warn", "error"]

# Parser statuses grouped by report severity. Anything not listed here is
# rendered as an error — see status_severity().
_OK_STATUSES = frozenset({"Read", "Sampled", "Cleaned", "Parsed", "Extracted"})
_WARN_STATUSES = frozenset({
    "Truncated",
    "Skipped (Binary)",
    "Skipped (Exclusion)",
    "Schema Only",
    "Redacted",
    "Skipped (Env)",
    "Skipped (No pyarrow)",
})

# Attention section of the final report: (stats key, badge label).
_ATTENTION_SPECS: Tuple[Tuple[str, str], ...] = (
    ("truncated_count", "truncated"),
    ("binary_count", "binary skipped"),
    ("excluded_count", "excluded"),
    ("env_count", "env redacted"),
)

# Leading edge of the banner reveal sweep, brightest block first.
_REVEAL_EDGE = "█▓▒"

# Fixed field widths keep the progress line stable while filenames change.
_ACTION_WIDTH = 10
_TARGET_WIDTH = 34

# The narrowest track (in columns) a report bar will advertise to the layout,
# however tight its table column gets.
_MIN_BAR_WIDTH = 8


def status_severity(status: str) -> Severity:
    """Maps a parser status to its report severity channel.

    Unknown statuses deliberately fall through to "error" so a new parser
    status can never render as silently fine.
    """
    if status in _OK_STATUSES:
        return "ok"
    if status in _WARN_STATUSES:
        return "warn"
    return "error"


def select_report_rows(
    files: List["FileSummary"], top_n: int
) -> Tuple[List["FileSummary"], int]:
    """Selects the rows the final report shows: the ``top_n`` token-heaviest
    files plus every flagged (non-"ok") file beyond them.

    Returns the rows (heaviest first, flagged extras appended) and the count
    of files left unlisted. The input list is not mutated.
    """
    by_weight = sorted(
        files, key=lambda info: info.get("tokens", 0), reverse=True
    )
    heaviest = by_weight[:top_n]
    flagged_extras = [
        info
        for info in by_weight[top_n:]
        if status_severity(info.get("status", "Unknown")) != "ok"
    ]
    rows = heaviest + flagged_extras
    return rows, len(files) - len(rows)


def bar_cells(value: int, max_value: int, cells: int) -> int:
    """Number of filled cells for a proportional bar of ``cells`` width.

    Zero-safe: a non-positive ``max_value`` (e.g. a run where every file was
    skipped) yields an empty bar instead of a division error. Any positive
    value fills at least one cell so small files never look like nothing.
    """
    if max_value <= 0 or value <= 0:
        return 0
    return max(1, min(cells, round(cells * value / max_value)))


def bar_glyphs(filled: int, cells: int, cell_width: int) -> Tuple[str, str]:
    """Plain-text halves of a bar track: (filled part, empty part).

    Every cell occupies exactly ``cell_width`` columns — one glyph followed
    by blank columns — so ``cell_width`` is the bar's density control: 1
    packs a cell into every column, larger values space the cells out
    without changing the track length (always ``cells * cell_width``
    columns). A non-positive width clamps to 1 instead of crashing the
    report over a misconfigured constant.
    """
    span = max(1, cell_width)
    filled_cell = "▰" + " " * (span - 1)
    empty_cell = "▱" + " " * (span - 1)
    return filled_cell * filled, empty_cell * (cells - filled)


def summarize_composition(
    files: List["FileSummary"], max_rows: int
) -> List[Tuple[str, int, int]]:
    """Groups the prompt's content by file type for the COMPOSITION chart.

    Returns ``(type label, file count, token sum)`` rows sorted
    heaviest-first. Zero-token files are dropped — they contributed nothing
    to the prompt and belong to ATTENTION, not COMPOSITION. Parenthetical
    qualifiers are stripped ("Excel (3 sheets)" → "Excel") so per-file
    variants of the same type group together. Types beyond ``max_rows`` are
    folded into a final "other" row so the chart never sprawls.
    """
    counts: Dict[str, int] = {}
    tokens: Dict[str, int] = {}
    for info in files:
        file_tokens = info.get("tokens", 0)
        if file_tokens <= 0:
            continue
        label = info.get("type", "Unknown").split(" (")[0]
        counts[label] = counts.get(label, 0) + 1
        tokens[label] = tokens.get(label, 0) + file_tokens
    rows = sorted(
        ((label, counts[label], tokens[label]) for label in tokens),
        key=lambda row: row[2],
        reverse=True,
    )
    if len(rows) > max_rows:
        head, tail = rows[: max_rows - 1], rows[max_rows - 1:]
        other = (
            "other",
            sum(count for _, count, _ in tail),
            sum(row_tokens for _, _, row_tokens in tail),
        )
        rows = head + [other]
    return rows


def cipher_mask(line: str, frame: int, row: int) -> str:
    """Deterministic cipher churn for the banner's unresolved columns.

    Every non-space character maps to a block glyph from ``UI_CIPHER_GLYPHS``
    chosen by a fixed spatial hash of frame, row, and column — no randomness,
    so every animation frame is reproducible. XOR of prime products (not a
    plain sum) so the frame term cannot degenerate to a constant modulo the
    glyph count. Spaces stay spaces, preserving the wordmark silhouette
    mid-animation.
    """
    glyphs = UI_CIPHER_GLYPHS
    return "".join(
        glyphs[
            ((frame * 73856093) ^ (row * 19349663) ^ (col * 83492791))
            % len(glyphs)
        ]
        if ch != " "
        else " "
        for col, ch in enumerate(line)
    )


def spaced_caps(title: str) -> str:
    """Letter-spaces a section title for the report headers.

    Single space between letters, double space between words:
    ``"HEAVIEST PAYLOADS"`` → ``"H E A V I E S T  P A Y L O A D S"``.
    """
    return "  ".join(" ".join(word) for word in title.split(" "))


@dataclass(frozen=True)
class _CellBar:
    """A proportional ▰▱ bar that draws itself to exactly the width its
    container grants it.

    Sizing is delegated to Rich: the bar advertises its width range through
    ``__rich_measure__`` (never wider than ``max_width``) and then renders
    to whatever its table column was actually given — so it can never
    overflow a row and be ellipsis-truncated, whatever the other columns
    hold. Cell density inside the track is REPORT_BAR_CELL_WIDTH.
    """

    value: int
    max_value: int
    max_width: int
    fill_style: str = UI_ACCENT

    def _track(self, available: int) -> int:
        """Track width in columns for the space the container offers."""
        return max(1, min(self.max_width, available))

    def __rich_measure__(
        self, console: Console, options: ConsoleOptions
    ) -> Measurement:
        track = self._track(options.max_width)
        return Measurement(min(_MIN_BAR_WIDTH, track), track)

    def __rich_console__(
        self, console: Console, options: ConsoleOptions
    ) -> RenderResult:
        track = self._track(options.max_width)
        cells = max(1, track // max(1, REPORT_BAR_CELL_WIDTH))
        filled = bar_cells(self.value, self.max_value, cells)
        filled_part, empty_part = bar_glyphs(
            filled, cells, REPORT_BAR_CELL_WIDTH
        )
        bar = Text(no_wrap=True, overflow="crop", end="")
        bar.append(filled_part, style=self.fill_style)
        bar.append(empty_part, style=UI_CHROME)
        yield bar


class UIHandler:
    """
    Handles all Terminal User Interface (TUI) logic for Data2Prompt.
    Encapsulates Rich-based display components, formatting, and progress
    tracking, themed after the BLACKSITE palette (white data, gray chrome,
    crimson accents).
    """

    def __init__(self) -> None:
        self.console = Console()
        self._progress: Optional[Progress] = None
        self._task_id: Optional[TaskID] = None

    # ------------------------------------------------------------- lifecycle

    def on_start(
        self,
        project_name: str,
        format_name: str,
        output_label: str,
        total_files: int,
    ) -> None:
        """Event handler for process start: renders the themed header."""
        self.print_header(project_name, format_name, output_label, total_files)

    def on_progress(
        self, action: str = "", target: str = "", advance: int = 0
    ) -> None:
        """Event handler for progress updates.

        Takes plain strings; all markup and theming is applied here so the
        orchestration layer stays presentation-free.
        """
        if self._progress is None or self._task_id is None:
            return
        if action or target:
            self._progress.update(
                self._task_id, description=self._format_task(action, target)
            )
        if advance > 0:
            self._progress.advance(self._task_id, advance)

    # ---------------------------------------------------------------- header

    def _banner_frame(
        self, revealed_cols: int, frame: int = 0, flash: bool = False
    ) -> Text:
        """One frame of the glitch sweep: columns left of the edge show the
        wordmark in its per-row gradient, the edge shows hot resolving blocks
        (white-tipped), and the rest churns as deterministic cipher static.
        ``flash`` renders the fully revealed wordmark hot white for the
        settle glint."""
        edge_len = len(_REVEAL_EDGE)
        lines: List[Text] = []
        for row, line in enumerate(BANNER):
            row_color = UI_BANNER_GRADIENT[row % len(UI_BANNER_GRADIENT)]
            row_style = "bold white" if flash else f"bold {row_color}"
            text = Text()
            text.append(line[:revealed_cols], style=row_style)
            edge_source = line[revealed_cols:revealed_cols + edge_len]
            for i, ch in enumerate(edge_source):
                text.append(
                    _REVEAL_EDGE[i] if ch != " " else " ",
                    style="bold white" if i == 0 else UI_ACCENT,
                )
            rest = line[revealed_cols + edge_len:]
            text.append(cipher_mask(rest, frame, row), style=UI_CHROME)
            lines.append(text)
        return Text("\n").join(lines)

    def _type_line(self, line: Text, duration: float) -> None:
        """Reveals a line with a one-pass teletype cursor sweep (TTY only)."""
        if not self.console.is_terminal:
            self.console.print(line)
            return
        total_chars = len(line.plain)
        frames = max(1, round(duration / UI_FRAME_DELAY))
        with Live(Text(""), console=self.console, refresh_per_second=50) as live:
            for frame in range(1, frames + 1):
                partial = line.copy()
                partial.truncate(round(total_chars * frame / frames))
                if frame < frames:
                    partial.append("▮", style=UI_ACCENT)
                live.update(partial)
                time.sleep(UI_FRAME_DELAY)

    def print_header(
        self,
        project_name: str,
        format_name: str,
        output_label: str,
        total_files: int,
    ) -> None:
        """Displays the wordmark — via the glitch sweep on real terminals,
        instantly otherwise — plus the version and a run-info line
        describing what is about to happen."""
        banner_width = max(len(line) for line in BANNER)
        if self.console.is_terminal:
            frames = max(1, round(UI_REVEAL_DURATION / UI_FRAME_DELAY))
            with Live(
                self._banner_frame(0),
                console=self.console,
                refresh_per_second=50,
            ) as live:
                for frame in range(1, frames + 1):
                    revealed = round(banner_width * frame / frames)
                    live.update(self._banner_frame(revealed, frame))
                    time.sleep(UI_FRAME_DELAY)
                for _ in range(UI_FLASH_FRAMES):
                    live.update(self._banner_frame(banner_width, flash=True))
                    time.sleep(UI_FRAME_DELAY)
                live.update(self._banner_frame(banner_width))
        else:
            self.console.print(self._banner_frame(banner_width))

        self.console.print(Text(f"v{__version__}", style=UI_CHROME))

        info = Text()
        run_facts = (
            ("TARGET", project_name),
            ("FORMAT", format_name),
            ("OUT", output_label),
            ("FILES", str(total_files)),
        )
        for label, value in run_facts:
            info.append("▰ ", style=UI_ACCENT)
            info.append(f"{label} ", style=UI_CHROME)
            info.append(value, style=UI_DATA_BOLD)
            info.append("   ")
        self._type_line(info, duration=0.25)
        self.console.print()

    # -------------------------------------------------------------- progress

    def _format_task(self, action: str, target: str) -> str:
        """Formats a progress description with fixed-width fields so the bar
        does not jitter as filenames change length."""
        action_part = f"{action:<{_ACTION_WIDTH}}"[:_ACTION_WIDTH]
        if len(target) > _TARGET_WIDTH:
            target = target[: _TARGET_WIDTH - 1] + "…"
        target_part = f"{target:<{_TARGET_WIDTH}}"
        return (
            f"[{UI_ACCENT}]{escape(action_part)}[/] "
            f"[{UI_DATA_BOLD}]{escape(target_part)}[/]"
        )

    @contextmanager
    def progress_bar(
        self, description: str, total: int
    ) -> Generator["UIHandler", None, None]:
        """Context manager showing the themed single-line progress bar:
        spinner · action + target · bar · M/N · percentage · elapsed time.
        Transient — it clears itself so the final report owns the screen."""
        progress = Progress(
            SpinnerColumn(spinner_name="dots", style=UI_ACCENT),
            TextColumn("{task.description}"),
            BarColumn(
                bar_width=24,
                style=UI_CHROME,
                complete_style=UI_ACCENT,
                finished_style=UI_ACCENT,
            ),
            MofNCompleteColumn(),
            TaskProgressColumn(),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
        )
        task = progress.add_task(
            self._format_task(description, ""), total=total
        )
        self._progress = progress
        self._task_id = task
        try:
            with progress:
                yield self
        finally:
            self._progress = None
            self._task_id = None

    # ---------------------------------------------------------- final report

    @staticmethod
    def _format_size(size_kb: float) -> str:
        """Human-readable size: KB below one megabyte, MB above."""
        if size_kb >= 1024:
            return f"{size_kb / 1024:.2f} MB"
        return f"{size_kb:.1f} KB"

    def _section_header(self, title: str) -> Group:
        """A section divider: a spacer line, then an accent ▰▰ tick, the
        letter-spaced title, and a dim rule running to the panel edge."""
        heading = Text()
        heading.append(f"{UI_SECTION_MARKER} ", style=UI_ACCENT)
        heading.append(spaced_caps(title), style=UI_HEADING)
        return Group(
            Text(""),
            Rule(
                title=heading,
                characters="─",
                style=UI_CHROME,
                align="left",
            ),
        )

    def _token_gauge(self, total_tokens: int, method: str) -> Table:
        """The TOKENS line: count, tokenizer, and a gauge of the count
        against the reference context window (one cell = 2% at the full
        50-column track); nearing the window turns it yellow, overflowing
        turns it red. The gauge draws itself to whatever width the row
        grants it, so the line never truncates."""
        ratio = total_tokens / CONTEXT_WINDOW_REFERENCE
        if ratio > 1.0:
            level_style = "bold red"
        elif ratio >= 0.85:
            level_style = UI_WARN
        else:
            level_style = UI_ACCENT
        window_label = f"{CONTEXT_WINDOW_REFERENCE // 1000}K"

        prefix = Text()
        prefix.append(f"{total_tokens:,}", style=UI_DATA_BOLD)
        prefix.append(f" ({method})  ", style=UI_CHROME)
        suffix = Text(
            f" {round(ratio * 100)}% of {window_label} window",
            style=UI_CHROME_BRIGHT if ratio < 0.85 else level_style,
        )

        line = Table.grid()
        line.add_column(no_wrap=True)
        line.add_column()
        line.add_column(no_wrap=True)
        line.add_row(
            prefix,
            _CellBar(
                total_tokens,
                CONTEXT_WINDOW_REFERENCE,
                REPORT_GAUGE_WIDTH,
                level_style,
            ),
            suffix,
        )
        return line

    def _composition_chart(
        self, files: List["FileSummary"], stats: Dict[str, int]
    ) -> RenderableType:
        """A per-type token-share bar chart of what made it into the prompt:
        type · file count · share bar · tokens · percent of the prompt's
        file tokens. Bars are scaled to the total, so the fill visually
        equals the percent column (one cell = 2% at full width)."""
        rows = summarize_composition(files, REPORT_COMPOSITION_ROWS)
        if not rows:
            return Text(
                "nothing tokenized — every file was skipped or empty",
                style=UI_CHROME,
            )
        total = sum(row_tokens for _, _, row_tokens in rows)
        chart = Table(
            box=None,
            show_header=True,
            header_style=UI_CHROME,
            padding=(0, 1),
            pad_edge=False,
        )
        chart.add_column("TYPE", no_wrap=True)
        chart.add_column(
            "FILES", justify="right", style=UI_CHROME_BRIGHT, no_wrap=True
        )
        chart.add_column("SHARE", no_wrap=True)
        chart.add_column(
            "TOKENS", justify="right", style=UI_DATA_BOLD, no_wrap=True
        )
        chart.add_column(
            "%", justify="right", style=UI_CHROME_BRIGHT, no_wrap=True
        )
        for label, count, row_tokens in rows:
            name = Text(
                label, style=UI_CHROME if label == "other" else UI_DATA
            )
            if label == "Excel" and stats.get("excel_sheets_count", 0) > 0:
                name.append(
                    f" · {stats['excel_sheets_count']} sheets", style=UI_CHROME
                )
            chart.add_row(
                name,
                f"×{count}",
                _CellBar(row_tokens, total, REPORT_CHART_WIDTH),
                f"{row_tokens:,}",
                f"{round(100 * row_tokens / total)}%",
            )
        return chart

    def _attention_line(self, stats: Dict[str, int]) -> Optional[Text]:
        """One line of badge-count items that deserve a second look, or
        None on a clean run (the section is omitted entirely)."""
        parts: List[Text] = []
        for key, label in _ATTENTION_SPECS:
            count = stats.get(key, 0)
            if count <= 0:
                continue
            part = Text()
            part.append(f" {count} ", style=UI_WARN_CHIP)
            part.append(f" {label}", style=UI_WARN)
            parts.append(part)
        if not parts:
            return None
        return Text("    ").join(parts)

    def print_final_report(
        self,
        processed_files_info: List["FileSummary"],
        output_path: str,
        file_size_kb: float,
        total_tokens: int,
        stats: Dict[str, int],
        method: str = "o200k_base",
        elapsed_seconds: float = 0.0,
    ) -> None:
        """Displays the final report panel: run summary, composition,
        attention items, and the heaviest / flagged files."""
        summary = Table.grid(padding=(0, 2))
        summary.add_column(style=UI_CHROME, no_wrap=True)
        summary.add_column()

        output_line = Text()
        output_line.append(output_path, style=UI_DATA_BOLD)
        output_line.append(
            f" · {self._format_size(file_size_kb)}", style=UI_CHROME_BRIGHT
        )
        summary.add_row("OUTPUT", output_line)

        summary.add_row("TOKENS", self._token_gauge(total_tokens, method))

        time_line = Text()
        time_line.append(f"{elapsed_seconds:.1f}s", style=UI_DATA_BOLD)
        time_line.append(" · ", style=UI_CHROME)
        time_line.append(str(stats.get("file_count", 0)), style=UI_DATA_BOLD)
        time_line.append(" files", style=UI_CHROME_BRIGHT)
        summary.add_row("TIME", time_line)

        sections: List[RenderableType] = [
            summary,
            self._section_header("COMPOSITION"),
            self._composition_chart(processed_files_info, stats),
        ]

        attention = self._attention_line(stats)
        if attention is not None:
            sections.extend([self._section_header("ATTENTION"), attention])

        rows, hidden = select_report_rows(
            processed_files_info, REPORT_TOP_FILES
        )
        if rows:
            table = Table(
                show_header=True,
                header_style=UI_CHROME,
                box=None,
                padding=(0, 2),
                collapse_padding=True,
                pad_edge=False,
            )
            table.add_column("", style=UI_CHROME, no_wrap=True)
            table.add_column(
                "FILE", no_wrap=True, overflow="ellipsis", max_width=44
            )
            table.add_column("TYPE", style=UI_CHROME_BRIGHT, no_wrap=True)
            table.add_column("STATUS", no_wrap=True)
            table.add_column(
                "TOKENS", justify="right", style=UI_DATA_BOLD, no_wrap=True
            )
            table.add_column("", no_wrap=True)

            status_styles: Dict[Severity, str] = {
                "ok": UI_CHROME_BRIGHT,
                "warn": UI_WARN,
                "error": UI_ERROR,
            }
            # Spark bars are scaled to the heaviest listed file so relative
            # weight is visible without reading the numbers.
            heaviest_tokens = rows[0].get("tokens", 0)
            top_section = min(REPORT_TOP_FILES, len(processed_files_info))
            for index, info in enumerate(rows):
                if index == top_section:
                    table.add_row(
                        "",
                        Text("· · · flagged · · ·", style=UI_CHROME),
                        "",
                        "",
                        "",
                        "",
                    )
                status = info.get("status", "Unknown")
                table.add_row(
                    f"0x{index + 1:02X}",
                    Text(info.get("name", "Unknown"), style=UI_DATA),
                    info.get("type", "Unknown"),
                    Text(status, style=status_styles[status_severity(status)]),
                    f"{info.get('tokens', 0):,}",
                    _CellBar(
                        info.get("tokens", 0),
                        heaviest_tokens,
                        REPORT_SPARK_WIDTH,
                    ),
                )
            sections.extend(
                [self._section_header("HEAVIEST PAYLOADS"), table]
            )

        if hidden > 0:
            footer = Text()
            footer.append(f"+ {hidden} more", style=UI_CHROME_BRIGHT)
            if output_path == "(clipboard)":
                footer.append(
                    " · full file index included in the copied output",
                    style=UI_CHROME,
                )
            else:
                footer.append(
                    f" · full index inside {output_path}", style=UI_CHROME
                )
            sections.append(footer)

        panel_title = Text(" ")
        panel_title.append(f"{UI_SECTION_MARKER} ", style=UI_ACCENT)
        panel_title.append(
            spaced_caps("TRANSMISSION COMPLETE"), style=UI_HEADING
        )
        panel_title.append(" ")
        self.console.print(
            Panel(
                Group(*sections),
                box=box.SQUARE,
                border_style=UI_CHROME_BRIGHT,
                title=panel_title,
                title_align="left",
                padding=(1, 2),
            )
        )

    # ------------------------------------------------------ warnings, errors

    def print_warning_panel(self, message: str) -> None:
        """Displays a warning message in a themed panel. The message may
        contain Rich markup, so it is rendered unescaped."""
        self.console.print(
            Panel(
                message,
                box=box.SQUARE,
                border_style=UI_WARN,
                title=Text(" ▲ WARNING ", style=UI_WARN_CHIP),
                title_align="left",
            )
        )

    def print_warning(self, message: str) -> None:
        """Displays an inline warning; the message is treated as plain text."""
        self.console.print(
            f"[bold {UI_WARN}]▲ WARN[/] [{UI_WARN}]{escape(message)}[/]"
        )

    def print_error(self, message: str) -> None:
        """Displays an inline error; the message is treated as plain text."""
        self.console.print(
            f"[{UI_ERROR}] ERROR [/] [bold red]{escape(message)}[/]"
        )


# Global UI instance
ui = UIHandler()
