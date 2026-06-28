import os
import random
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, List, Optional, TYPE_CHECKING

from rich.color import Color
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    TaskProgressColumn,
    TextColumn,
)
from rich.spinner import Spinner
from rich.style import Style
from rich.table import Table
from rich.text import Text

from data2prompt.constants import (
    ANIMATION_FRAME_DELAY,
    MATRIX_DARK_GREEN,
    MATRIX_NEON_GREEN,
    STARTUP_ANIMATION_DURATION,
    ASCII_ART,
)

if TYPE_CHECKING:
    # Imported only for type hints — a runtime import would create a
    # utils → ui → parsers → utils cycle.
    from data2prompt.parsers import FileSummary


class UIHandler:
    """
    Handles all Terminal User Interface (TUI) logic for Data2Prompt.
    Encapsulates Rich-based display components, formatting, and progress tracking.
    """
    def __init__(self) -> None:
        self.console = Console()
        self._progress: Optional[Progress] = None
        self._task_id: Any = None

    def on_start(self, description: str, total: int) -> None:
        """Event handler for process start."""
        self.print_header()

    def on_progress(self, description: str, advance: int = 0) -> None:
        """Event handler for progress updates."""
        if self._progress and self._task_id is not None:
            self._progress.update(self._task_id, description=description)
            if advance > 0:
                self._progress.advance(self._task_id, advance)

    def _generate_matrix_frame(self, width: int, height: int) -> Text:
        """Generates a single frame of random binary/hex characters."""
        chars = "0123456789ABCDEF"
        lines = []
        for _ in range(height):
            line = "".join(random.choice(chars) if random.random() > 0.5 else str(random.randint(0, 1)) for _ in range(width))
            lines.append(line)
        
        return Text("\n".join(lines), style=Style(color=Color.from_rgb(*MATRIX_DARK_GREEN), dim=True))

    def print_header(self) -> None:
        """Displays the application header with a Matrix decryption animation."""
        max_width = max(len(line) for line in ASCII_ART)
        height = len(ASCII_ART)
        
        start_time = time.time()
        with Live(self._generate_matrix_frame(max_width, height), refresh_per_second=20, console=self.console) as live:
            while time.time() - start_time < STARTUP_ANIMATION_DURATION:
                live.update(self._generate_matrix_frame(max_width, height))
                time.sleep(ANIMATION_FRAME_DELAY)
            
            # Final reveal with solid neon green
            final_text = Text("\n".join(ASCII_ART), style=Style(color=Color.from_rgb(*MATRIX_NEON_GREEN), bold=True))
            
            live.update(final_text)
        

    @contextmanager
    def progress_bar(
        self, description: str, total: int
    ) -> Generator[Any, None, None]:
        """Context manager for showing a stable, two-line hacker-style progress bar."""
        progress = Progress(
            TextColumn("[bold green][[/bold green]"),
            BarColumn(bar_width=None, style="dim green", complete_style="bold green", finished_style="bold green"),
            TextColumn("[bold green]][/bold green]"),
            TaskProgressColumn(style="bold yellow"),
            console=self.console,
        )
        task = progress.add_task(description, total=total)
        spinner = Spinner("dots12", style="bold green")

        self._progress = progress
        self._task_id = task

        class ProgressGroup:
            def __rich_console__(self, console: Console, options: Any) -> Generator[Any, None, None]:
                curr_task = progress.tasks[0]
                header_grid = Table.grid(padding=(0, 1))
                header_grid.add_row(spinner, Text.from_markup(curr_task.description))
                yield Group(header_grid, progress)

        try:
            with Live(ProgressGroup(), console=self.console, transient=True, refresh_per_second=20):
                yield self
        finally:
            self._progress = None
            self._task_id = None

    def print_final_report(
        self,
        processed_files_info: List["FileSummary"],
        output_path: str,
        file_size_kb: float,
        total_tokens: int,
        stats: Dict[str, int],
        method: str = "o200k_base",
    ) -> None:
        """Displays the final report including the success panel and an interactive summary table."""
        # Sort files by tokens in descending order (Heaviest first)
        processed_files_info.sort(key=lambda x: x.get("tokens", 0), reverse=True)

        # 1. Build the Summary Table
        table = Table(
            show_header=True,
            header_style="bold green",
            border_style="dim green",
            box=None,
            padding=(0, 2),
            collapse_padding=True,
            pad_edge=False
        )
        table.add_column("FILE_NAME", style="green", no_wrap=True)
        table.add_column("TYPE", style="green")
        table.add_column("TOKENS", justify="right", style="bold yellow")
        table.add_column("STATUS", style="bold")

        for info in processed_files_info:
            status = info.get("status", "Unknown")
            status_color = "bold green" if status in ["Read", "Sampled", "Cleaned", "Parsed", "Extracted"] else \
                           "bold yellow" if status in ["Truncated", "Skipped (Binary)", "Skipped (Exclusion)", "Schema Only", "Redacted", "Skipped (Env)", "Skipped (No pyarrow)"] else "bold red"

            table.add_row(
                os.path.basename(info.get("name", "Unknown")),
                info.get("type", "Unknown"),
                f"{info.get('tokens', 0):,}",
                f"[{status_color}]{status}[/{status_color}]"
            )

        # 2. Build the Success Panel
        stats_grid = Table.grid(padding=(0, 1))
        stats_grid.add_row("[green]>[/green]", f"TOTAL_FILES: [bold green]{stats.get('file_count', 0)}[/bold green]")

        if stats.get("csv_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"CSV_SAMPLED: [bold green]{stats.get('csv_count', 0)}[/bold green]")

        if stats.get("notebook_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"IPYNB_CLEAN: [bold green]{stats.get('notebook_count', 0)}[/bold green]")

        if stats.get("sql_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"SQL_PARSED:  [bold green]{stats.get('sql_count', 0)}[/bold green]")

        if stats.get("excel_count", 0) > 0:
            stats_grid.add_row(
                "[green]>[/green]",
                f"XLSX_HANDLED: [bold green]{stats.get('excel_count', 0)}[/bold green] ({stats.get('excel_sheets_count', 0)} sheets)",
            )

        if stats.get("parquet_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"PARQUET_SAMPLED: [bold green]{stats.get('parquet_count', 0)}[/bold green]")

        if stats.get("feather_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"FEATHER_SAMPLED: [bold green]{stats.get('feather_count', 0)}[/bold green]")

        if stats.get("arrow_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"ARROW_SAMPLED:   [bold green]{stats.get('arrow_count', 0)}[/bold green]")

        if stats.get("truncated_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"TRUNCATED:    [bold yellow]{stats.get('truncated_count', 0)}[/bold yellow]")

        if stats.get("binary_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"BINARY_SKIP:  [bold yellow]{stats.get('binary_count', 0)}[/bold yellow]")

        if stats.get("excluded_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"EXCLUDED_SKIP:[bold yellow]{stats.get('excluded_count', 0)}[/bold yellow]")

        if stats.get("env_count", 0) > 0:
            stats_grid.add_row("[green]>[/green]", f"ENV_REDACTED: [bold yellow]{stats.get('env_count', 0)}[/bold yellow]")

        method_label = method.upper()
        success_panel = Panel(
            Group(
                f"[bold green]COMPILATION COMPLETE[/bold green]",
                f"PATH: [bold white]{output_path}[/bold white] ({file_size_kb:.1f} KB)",
                f"LOAD: [bold yellow]{total_tokens:,}[/bold yellow] TOKENS (via {method_label})",
                "",
                stats_grid
            ),
            border_style="bold green",
            title="[bold green]SCAN SUMMARY[/bold green]"
                            )

        # 3. Print both panels unconditionally — same behaviour on all platforms
        self.console.print(success_panel)
        self.console.print(Panel(table, border_style="bold green", title="[bold green]SCAN LIST[/bold green]", padding=(0, 1)))

    def print_warning_panel(self, message: str) -> None:
        """Displays a warning message in a hacker-style panel."""
        self.console.print(Panel(
            message,
            border_style="bold yellow",
            title="[bold yellow]SYSTEM_WARNING[/bold yellow]"
        ))

    def print_warning(self, message: str) -> None:
        """Displays a simple warning message with a hacker aesthetic."""
        self.console.print(f"[bold yellow]![/bold yellow] [yellow]WARN: {message}[/yellow]")

    def print_error(self, message: str) -> None:
        """Displays an error message with a hacker aesthetic."""
        self.console.print(f"[bold red]![/bold red] [red]ERR_CRITICAL: {message}[/red]")

# Global UI instance
ui = UIHandler()
