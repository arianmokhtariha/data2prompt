import warnings

# Suppress known noisy warnings globally for a cleaner TUI experience
# We do this before importing pandas to ensure the filters are in place
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import pandas as pd
# Now that pandas is imported, we can reference its error types
warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)
from pathlib import Path
from typing import List, Set
from .cli import setup_cli, Config
from .parsers import (
    registry,
    ParserResult,
    FileData,
    FileSummary,
    is_env_file,
    env_parser,
)
from .utils import ProjectScanner, count_tokens, copy_to_clipboard
from .ui import ui
from .output import get_generator

def get_ui_action(ext: str, skip_exts: Set[str]) -> str:
    """Determines the UI action string based on file extension."""
    if ext in skip_exts: return "Skipping"
    elif ext == '.csv': return "Sampling"
    elif ext in ['.parquet', '.feather', '.arrow']: return "Sampling"
    elif ext == '.ipynb': return "Cleaning"
    elif ext == '.sql': return "Parsing"
    elif ext in ['.xlsx', '.xls']: return "Extracting"
    return "Reading"

def process_target_file(file_path: Path, config: Config) -> ParserResult:
    """Handles a single file and returns its content, tokens, and metadata."""
    ext = file_path.suffix.lower()

    # Env files are detected by name (a bare '.env' has no suffix) and routed to a
    # dedicated parser that redacts values instead of leaking the whole file.
    if is_env_file(file_path.name):
        return env_parser.parse(file_path, config)

    if ext in config.skip_exts:
        return ParserResult(
            content=f"*Note: Content skipped for ({ext}) file based on exclusion rules.*\n",
            tokens=0,
            type=f"Excluded ({ext})",
            status="Skipped (Exclusion)",
            stats_update={"excluded_count": 1}
        )

    parser = registry.get_parser(ext)
    return parser.parse(file_path, config)

def main() -> None:
    """
    The main entry point for the Data2Prompt CLI.
    Orchestrates the argument parsing, file discovery, content processing, and Markdown generation.
    """
    config = setup_cli() # Retrieve user settings from the terminal
    
    project_path = Path.cwd()
    scanner = ProjectScanner(
        project_path=project_path,
        ignore_folders=config.ignore_folders,
        ignore_files=config.ignore_files,
        output_file=config.output,
        use_gitignore=config.use_gitignore
    )
    
    # Collect all files first to set progress bar total
    all_files = scanner.scan()
    total_steps = 1 + len(all_files) + 1

    # Initialize UI and start process
    ui.on_start("[cyan]Starting process...[/cyan]", total=total_steps)

    stats = {
        "file_count": 0,
        "csv_count": 0,
        "notebook_count": 0,
        "sql_count": 0,
        "excel_count": 0,
        "excel_sheets_count": 0,
        "parquet_count": 0,
        "feather_count": 0,
        "arrow_count": 0,
        "truncated_count": 0,
        "binary_count": 0,
        "excluded_count": 0,
        "env_count": 0
    }
    
    # For the summary table
    processed_files_info: List[FileSummary] = []

    with ui.progress_bar("[cyan]Starting process...[/cyan]", total=total_steps) as handler:
        # 1. Generating project tree
        handler.on_progress("[cyan]Generating project tree...[/cyan]")
        tree_text = scanner.generate_tree()
        handler.on_progress("[cyan]Generating project tree...[/cyan]", advance=1)

        # 2. Processing files
        files_data: List[FileData] = []

        for file_path in all_files:
            relative_path = file_path.relative_to(project_path)
            ext = file_path.suffix.lower()
            stats["file_count"] += 1
            
            # Determine action for progress bar - show only filename
            action = get_ui_action(ext, config.skip_exts)
            handler.on_progress(f"[cyan]{action}[/cyan] [bold]{file_path.name}[/bold] [cyan]...[/cyan]")
            
            result = process_target_file(file_path, config)
            if result.skip_file:
                handler.on_progress(f"[cyan]{action}[/cyan] [bold]{file_path.name}[/bold] [cyan]...[/cyan]", advance=1)
                continue

            # Collect file data for the generator
            files_data.append({
                "path": str(relative_path),
                "content": result.content,
                "type": result.type,
                "tokens": result.tokens,
                "status": result.status
            })
            
            # Update stats
            for key, value in result.stats_update.items():
                stats[key] += value
            
            processed_files_info.append({
                "name": str(relative_path),
                "type": result.type,
                "tokens": result.tokens,
                "status": result.status
            })
            
            handler.on_progress(f"[cyan]{action}[/cyan] [bold]{file_path.name}[/bold] [cyan]...[/cyan]", advance=1)

        # 3. Compiling project context
        handler.on_progress("[cyan]Compiling project context...[/cyan]")

        generator = get_generator(config.format)
        final_output = generator.generate(
            project_name=project_path.name,
            tree_text=tree_text,
            files_data=files_data,
            stats=stats,
            config=config
        )

        # Count on the full rendered output so the reported total includes the
        # structural scaffolding (tags, headers, fences, metadata, system prompt).
        # Count once on the placeholder string and substitute; inserting the digits
        # shifts the true count by a token or two, which the metadata labels an estimate.
        total_tokens, method = count_tokens(final_output)
        final_output = final_output.replace("{{TOTAL_TOKENS}}", str(total_tokens))
        final_output = final_output.replace("{{TOKEN_METHOD}}", method)

        # Output destination: clipboard (if requested and available) or a file.
        clipboard_failed = False
        if config.clipboard and copy_to_clipboard(final_output):
            output_destination = "(clipboard)"
            file_size_kb = len(final_output.encode('utf-8')) / 1024
        else:
            # Either a normal file run, or a clipboard run with no utility available.
            clipboard_failed = config.clipboard
            with open(config.output, 'w', encoding='utf-8') as f:
                f.write(final_output)
            output_destination = config.output
            file_size_kb = Path(config.output).stat().st_size / 1024
        handler.on_progress("[cyan]Compiling project context...[/cyan]", advance=1)

    if clipboard_failed:
        ui.print_warning_panel(
            "[bold yellow]WARNING:[/bold yellow] No clipboard utility was available.\n"
            f"[bold cyan]Fallback:[/bold cyan] Output written to {config.output} instead."
        )

    # Display Final Report (Interactive Summary + Success Panel)
    ui.print_final_report(processed_files_info, output_destination, file_size_kb, total_tokens, stats, method)

    if any(info.get("status") == "Skipped (No pyarrow)" for info in processed_files_info):
        ui.print_warning_panel(
            "[bold yellow]WARNING:[/bold yellow] One or more Parquet / Feather / Arrow files "
            "were skipped because [bold]pyarrow[/bold] is not installed.\n"
            "[bold cyan]For pip users:[/bold cyan] pip install pyarrow\n"
            "[bold cyan]For pipx users:[/bold cyan] pipx inject data2prompt pyarrow"
        )

    if file_size_kb > 2000:
        ui.print_warning_panel(
            "[bold yellow]WARNING:[/bold yellow] File is over 2MB. This might be too large for some context windows.\n"
            "[bold cyan]Suggestion:[/bold cyan] Reduce --csv-sample-size, --sql-sample-size or --max-lines."
        )

if __name__ == "__main__":
    main()
