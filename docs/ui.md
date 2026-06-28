# User Interface (UI)

The `data2prompt` project utilizes a sophisticated Terminal User Interface (TUI) built with the [`rich`](https://github.com/Textualize/rich) library to provide real-time feedback and a professional, tech-focused experience. All UI logic is encapsulated in the [`UIHandler`](../src/data2prompt/ui.py#L34) class.

## UIHandler Class

The [`UIHandler`](../src/data2prompt/ui.py#L34) class in [`src/data2prompt/ui.py`](../src/data2prompt/ui.py) serves as the central point for all terminal output. It encapsulates Rich-based display components, formatting, and progress tracking.

### Core Responsibilities

| Responsibility | Description |
|:---|:---|
| **Event Handling** | Processes lifecycle events: `on_start`, `on_progress` |
| **Progress Tracking** | Manages real-time progress bars during file scanning and processing |
| **Visual Components** | Renders panels, tables, spinners, and ASCII art headers |
| **Final Report** | Prints success panel and full scan list table to the terminal |
| **Error Display** | Shows formatted error and warning messages with hacker aesthetic |

### Event Handlers

The [`UIHandler`](../src/data2prompt/ui.py#L34) provides two lifecycle event handler methods that integrate with the main processing flow:

```python
def on_start(self, description: str, total: int) -> None:
    """Event handler for process start."""
    self.print_header()
```

```python
def on_progress(self, description: str, advance: int = 0) -> None:
    """Event handler for progress updates."""
    if self._progress and self._task_id is not None:
        self._progress.update(self._task_id, description=description)
        if advance > 0:
            self._progress.advance(self._task_id, advance)
```

Errors and warnings are surfaced directly through the
[`print_error()`](../src/data2prompt/ui.py) and
[`print_warning()`](../src/data2prompt/ui.py) display methods (and the
[`print_warning_panel()`](../src/data2prompt/ui.py) panel variant), not via
dedicated event handlers.

## UI Components

### Matrix Startup Animation

The [`print_header()`](../src/data2prompt/ui.py#L73) method displays an ASCII art banner with a Matrix-style decryption animation:

```mermaid
graph LR
    A[Start] --> B[Generate Matrix Frame]
    B --> C{Running?}
    C -->|Yes| D[Update Live Display]
    D --> B
    C -->|No| E[Final Reveal]
    E --> F[Neon Green Banner]
```

**Animation Parameters** (from [`constants.py`](../src/data2prompt/constants.py#L76)):
- `MATRIX_DARK_GREEN = (0, 150, 0)` - Initial frame color
- `MATRIX_NEON_GREEN = (0, 255, 0)` - Final reveal color
- `STARTUP_ANIMATION_DURATION = 0.9` - Animation duration in seconds
- `ANIMATION_FRAME_DELAY = 0.03` - Frame delay in seconds

The [`_generate_matrix_frame()`](../src/data2prompt/ui.py#L63) method generates random binary/hex characters for each frame:
```python
def _generate_matrix_frame(self, width: int, height: int) -> Text:
    """Generates a single frame of random binary/hex characters."""
    chars = "0123456789ABCDEF"
    lines = []
    for _ in range(height):
        line = "".join(random.choice(chars) if random.random() > 0.5 else str(random.randint(0, 1)) for _ in range(width))
        lines.append(line)
    return Text("\n".join(lines), style=Style(color=Color.from_rgb(*MATRIX_DARK_GREEN), dim=True))
```

### Progress Bar

The [`progress_bar()`](../src/data2prompt/ui.py#L98) context manager provides a stable, two-line hacker-style progress bar:

```python
@contextmanager
def progress_bar(self, description: str, total: int) -> Generator[Any, None, None]:
    """Context manager for showing a stable, two-line hacker-style progress bar."""
    progress = Progress(
        TextColumn("[bold green][[/bold green]"),
        BarColumn(bar_width=None, style="dim green", complete_style="bold green", finished_style="bold green"),
        TextColumn("[bold green]][/bold green]"),
        TaskProgressColumn(style="bold yellow"),
        console=self.console,
    )
```

**Components:**
- `TextColumn` - Opening/closing brackets with green styling
- `BarColumn` - Visual progress bar with dim/complete/finished styles
- `TaskProgressColumn` - Percentage display in yellow
- `Spinner` - "dots12" tech-focused spinner animation

## Final Report

The [`print_final_report()`](../src/data2prompt/ui.py#L129) method displays the comprehensive scan summary with two main sections:

### Success Panel

A styled panel showing compilation statistics:
- Output destination (file path, or `(clipboard)` when `--clipboard` is used) and size
- Total token count and method used
- File type counts (CSV, Notebook, SQL, Excel)
- Truncation and skip counts, including `ENV_REDACTED` (count of `.env` files redacted)

### Summary Table

A Rich table displaying processed files with columns:
- `FILE_NAME` - Basename of the file
- `TYPE` - File type/extension category
- `TOKENS` - Token count (right-aligned, yellow)
- `STATUS` - Processing status with color coding:
  - **Green**: Read, Sampled, Cleaned, Parsed, Extracted
  - **Yellow**: Truncated, Skipped (Binary), Skipped (Exclusion), Schema Only, Redacted, Skipped (Env)
  - **Red**: Error states

## Error and Warning Display

### Warning Panel

The [`print_warning_panel()`](../src/data2prompt/ui.py#L340) displays a styled warning panel:

```python
def print_warning_panel(self, message: str) -> None:
    """Displays a warning message in a hacker-style panel."""
    self.console.print(Panel(
        message,
        border_style="bold yellow",
        title="[bold yellow]SYSTEM_WARNING[/bold yellow]"
    ))
```

### Inline Warning/Error

The [`print_warning()`](../src/data2prompt/ui.py#L348) and [`print_error()`](../src/data2prompt/ui.py#L352) methods provide inline messages:

```python
def print_warning(self, message: str) -> None:
    """Displays a simple warning message with a hacker aesthetic."""
    self.console.print(f"[bold yellow]![/bold yellow] [yellow]WARN: {message}[/yellow]")

def print_error(self, message: str) -> None:
    """Displays an error message with a hacker aesthetic."""
    self.console.print(f"[bold red]![/bold red] [red]ERR_CRITICAL: {message}[/red]")
```

## Integration with Main Processing

The [`UIHandler`](../src/data2prompt/ui.py#L34) integrates with [`main.py`](../src/data2prompt/main.py#L43) through event handlers:

```python
# From main.py
with ui.progress_bar("[cyan]Starting process...[/cyan]", total=total_steps) as handler:
    handler.on_progress("[cyan]Generating project tree...[/cyan]")
    tree_text = scanner.generate_tree()
    handler.on_progress("[cyan]Generating project tree...[/cyan]", advance=1)
    # ... file processing loop
```

## Global Instance

A global [`ui`](../src/data2prompt/ui.py#L357) instance is exported for use throughout the application:

```python
# Global UI instance
ui = UIHandler()
```

## Constants Used

| Constant | Value | Purpose |
|:---|:---|:---|
| `MATRIX_DARK_GREEN` | `(0, 150, 0)` | Matrix animation frame color |
| `MATRIX_NEON_GREEN` | `(0, 255, 0)` | Final banner color |
| `STARTUP_ANIMATION_DURATION` | `0.9` | Animation duration (seconds) |
| `ANIMATION_FRAME_DELAY` | `0.03` | Frame delay (seconds) |
| `ASCII_ART` | list | Application banner lines |
