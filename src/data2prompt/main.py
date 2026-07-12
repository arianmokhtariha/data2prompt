import warnings

# Suppress known noisy warnings globally for a cleaner TUI experience
# We do this before importing pandas to ensure the filters are in place
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import pandas as pd
# Now that pandas is imported, we can reference its error types
warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)
import time
from pathlib import Path
from typing import List, Optional, Set
from data2prompt.cli import setup_cli, Config
from data2prompt.parsers import (
    registry,
    ParserResult,
    FileData,
    FileSummary,
    is_env_file,
    env_parser,
)
from data2prompt.utils import ProjectScanner, count_tokens, copy_to_clipboard
from data2prompt.ui import ui
from data2prompt.output import get_generator
from data2prompt.budget import fit_to_budget, FileRecord, BudgetOutcome

def get_ui_action(file_name: str, ext: str, skip_exts: Set[str]) -> str:
    """Determines the UI action string based on file name and extension."""
    if is_env_file(file_name): return "Redacting"
    elif ext in skip_exts: return "Skipping"
    elif ext == '.csv': return "Sampling"
    elif ext in ['.parquet', '.feather', '.arrow']: return "Sampling"
    elif ext == '.ipynb': return "Cleaning"
    elif ext == '.sql': return "Parsing"
    elif ext in ['.xlsx', '.xls']: return "Extracting"
    elif ext in ['.db', '.sqlite', '.sqlite3']: return "Querying"
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
            content=(
                f"-- [Content skipped: ({ext}) files are excluded "
                "by exclusion rules] --\n"
            ),
            tokens=0,
            type=f"Excluded ({ext})",
            status="Skipped (Exclusion)",
            stats_update={"excluded_count": 1}
        )

    parser = registry.get_parser(ext)
    return parser.parse(file_path, config)

def _run() -> None:
    """
    Orchestrates the argument parsing, file discovery, content processing,
    and output generation. Wrapped by :func:`main` for top-level error handling.
    """
    started = time.perf_counter()
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
    ui.on_start(
        project_name=project_path.name,
        format_name=config.format,
        output_label="(clipboard)" if config.clipboard else config.output,
        total_files=len(all_files),
    )

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
        "sqlite_count": 0,
        "db_tables_count": 0,
        "truncated_count": 0,
        "binary_count": 0,
        "excluded_count": 0,
        "env_count": 0
    }
    
    # For the summary table
    processed_files_info: List[FileSummary] = []

    with ui.progress_bar("Initializing", total=total_steps) as handler:
        # 1. Generating project tree (reuses the scan — no second walk)
        handler.on_progress("Indexing", "project tree")
        tree_text = scanner.generate_tree(all_files)
        handler.on_progress(advance=1)

        # 2. Processing files
        files_data: List[FileData] = []
        # Only populated when --budget is set; fit_to_budget() re-parses
        # from these in place, so a budget-less run pays nothing for this.
        records: List[FileRecord] = []

        for file_path in all_files:
            relative_path = file_path.relative_to(project_path)
            ext = file_path.suffix.lower()
            stats["file_count"] += 1

            # Determine action for progress bar - show only filename
            action = get_ui_action(file_path.name, ext, config.skip_exts)
            handler.on_progress(action, file_path.name)

            result = process_target_file(file_path, config)
            if result.skip_file:
                handler.on_progress(advance=1)
                continue

            # Collect file data for the generator
            files_data.append({
                "path": str(relative_path),
                "content": result.content,
                "type": result.type,
                "tokens": result.tokens,
                "status": result.status
            })

            if config.budget is not None:
                records.append(FileRecord(
                    absolute_path=file_path,
                    relative_path=str(relative_path),
                    result=result,
                ))

            # Update stats — .get() so a parser introducing a new stat key
            # can never crash the whole run with a KeyError.
            for key, value in result.stats_update.items():
                stats[key] = stats.get(key, 0) + value
            
            processed_files_info.append({
                "name": str(relative_path),
                "type": result.type,
                "tokens": result.tokens,
                "status": result.status
            })
            
            handler.on_progress(advance=1)

        # 3. Compiling project context
        handler.on_progress("Compiling", config.output)

        outcome: Optional[BudgetOutcome] = None
        if config.budget is not None:
            # Re-parses only the files each ladder step affects, re-renders
            # the whole document, and re-counts, until it fits config.budget
            # (or the reduction floor is reached — see budget.py).
            outcome = fit_to_budget(
                budget=config.budget,
                config=config,
                records=records,
                scanned_file_count=stats["file_count"],
                tree_text=tree_text,
                project_name=project_path.name,
                reparse=process_target_file,
                on_progress=handler.on_progress,
            )
            if outcome.fits:
                total_tokens, method = outcome.total_tokens, outcome.method
                files_data = outcome.files_data
                stats = outcome.stats
                processed_files_info = outcome.summaries
                # fit_to_budget counted the placeholder string; substitute
                # the real values exactly like the budget-less path below.
                final_output = outcome.final_output
                final_output = final_output.replace(
                    "{{TOTAL_TOKENS}}", str(total_tokens)
                )
                final_output = final_output.replace("{{TOKEN_METHOD}}", method)
        else:
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
        # Skipped entirely when the budget could not be met — nothing is
        # written and nothing is copied for an infeasible run.
        clipboard_failed = False
        if outcome is None or outcome.fits:
            if config.clipboard and copy_to_clipboard(final_output):
                output_destination = "(clipboard)"
                file_size_kb = len(final_output.encode('utf-8')) / 1024
            else:
                # Either a normal file run, or a clipboard run with no utility available.
                clipboard_failed = config.clipboard
                output_path = Path(config.output)
                output_path.write_text(final_output, encoding='utf-8')
                output_destination = config.output
                file_size_kb = output_path.stat().st_size / 1024
        handler.on_progress(advance=1)

    elapsed_seconds = time.perf_counter() - started

    if outcome is not None and not outcome.fits:
        ui.print_budget_failure(
            requested=outcome.report.requested_tokens,
            minimum_tokens=outcome.total_tokens,
            report=outcome.report,
        )
        raise SystemExit(1)

    if clipboard_failed:
        ui.print_warning_panel(
            "No clipboard utility was available.\n"
            f"[bold]Fallback:[/bold] output written to {config.output} instead."
        )

    # Display Final Report (Interactive Summary + Success Panel)
    ui.print_final_report(
        processed_files_info,
        output_destination,
        file_size_kb,
        total_tokens,
        stats,
        method,
        elapsed_seconds,
        budget_report=outcome.report if outcome is not None else None,
    )

    if any(info.get("status") == "Skipped (No pyarrow)" for info in processed_files_info):
        ui.print_warning_panel(
            "One or more Parquet / Feather / Arrow files were skipped because "
            "[bold]pyarrow[/bold] is not installed.\n"
            "[bold]For pip users:[/bold] pip install pyarrow\n"
            "[bold]For pipx users:[/bold] pipx inject data2prompt pyarrow"
        )

    if file_size_kb > 2000:
        ui.print_warning_panel(
            "Output is over 2MB. This might be too large for some context windows.\n"
            "[bold]Suggestion:[/bold] reduce --csv-sample-size, --sql-sample-size "
            "or --max-lines."
        )

def main() -> None:
    """The main entry point for the Data2Prompt CLI (console script target).

    Wraps :func:`_run` so predictable failures (unwritable output, interrupt)
    exit with a clean message and a proper exit code instead of a traceback.
    """
    try:
        _run()
    except KeyboardInterrupt:
        ui.print_error("Interrupted by user.")
        raise SystemExit(130)
    except OSError as e:
        ui.print_error(f"File system error: {e}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
