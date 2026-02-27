from contextlib import contextmanager
from typing import Any, Dict, Generator, List

from rich.console import Console, Group
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskProgressColumn,
    TextColumn,
)
from rich.table import Table


class UIHandler:
    """
    Handles all Terminal User Interface (TUI) logic for Data2Prompt.
    Encapsulates Rich-based display components, formatting, and progress tracking.
    """
    def __init__(self) -> None:
        self.console = Console()

    def print_header(self) -> None:
        """Displays the application header."""
        header = "📊 DATA PROJECT -> LLM PROMPT PACKAGER 📊"
        self.console.print(Panel(header, style="bold blue", expand=False))

    def print_step(self, step_num: int, message: str) -> None:
        """Displays a formatted step message."""
        self.console.print(f"\n[bold blue]Step {step_num}: {message}[/bold blue]")

    @contextmanager
    def status(self, message: str) -> Generator[Any, None, None]:
        """Context manager for showing a status spinner."""
        with self.console.status(f"[bold green]{message}"):
            yield

    @contextmanager
    def progress_bar(
        self, description: str, total: int
    ) -> Generator[Any, None, None]:
        """Context manager for showing a progress bar."""
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=self.console,
        ) as progress:
            task = progress.add_task(description, total=total)
            yield progress, task

    def print_summary_table(self, processed_files_info: List[Dict[str, Any]]) -> None:
        """Displays a summary table of all processed files."""
        table = Table(title="Processing Summary", show_header=True, header_style="bold magenta")
        table.add_column("File Name", style="cyan")
        table.add_column("Type", style="green")
        table.add_column("Tokens", justify="right", style="yellow")
        table.add_column("Status", style="bold")

        for info in processed_files_info:
            status = info.get("status", "Unknown")
            status_color = "green" if status in ["Read", "Sampled", "Cleaned", "Parsed", "Extracted"] else \
                           "yellow" if status in ["Truncated", "Skipped (Binary)"] else "red"
            
            table.add_row(
                info.get("name", "Unknown"),
                info.get("type", "Unknown"),
                f"{info.get('tokens', 0):,}",
                f"[{status_color}]{status}[/{status_color}]"
            )
        self.console.print(table)

    def print_success_panel(
        self,
        output_path: str,
        file_size_kb: float,
        total_tokens: int,
        stats: Dict[str, int],
    ) -> None:
        """Displays the final success panel with project statistics."""
        stats_grid = Table.grid(padding=(0, 1))
        stats_grid.add_row("📂", f"Total Files: [bold]{stats.get('file_count', 0)}[/bold]")
        stats_grid.add_row("📊", f"CSVs Sampled: [bold]{stats.get('csv_count', 0)}[/bold]")
        stats_grid.add_row("📓", f"Notebooks Cleaned: [bold]{stats.get('notebook_count', 0)}[/bold]")
        stats_grid.add_row("💾", f"SQL Scripts Parsed: [bold]{stats.get('sql_count', 0)}[/bold]")
        stats_grid.add_row("📈", f"Excel Files Handled: [bold]{stats.get('excel_count', 0)}[/bold] ({stats.get('excel_sheets_count', 0)} sheets)")

        success_panel = Panel(
            Group(
                f"✅ [bold green]DONE![/bold green] Created: [bold]{output_path}[/bold] ({file_size_kb:.1f} KB)",
                f"Tokens: [bold yellow]{total_tokens:,}[/bold yellow] (est. via o200k_base)",
                "",
                stats_grid
            ),
            border_style="green",
            title="Success"
        )
        self.console.print(success_panel)

    def print_warning_panel(self, message: str) -> None:
        """Displays a warning message in a panel."""
        self.console.print(Panel(message, border_style="yellow"))

    def print_warning(self, message: str) -> None:
        """Displays a simple warning message."""
        self.console.print(f"[yellow]⚠️  Warning: {message}[/yellow]")

    def print_error(self, message: str) -> None:
        """Displays an error message."""
        self.console.print(f"[red]❌ Error: {message}[/red]")

# Global UI instance
ui = UIHandler()
