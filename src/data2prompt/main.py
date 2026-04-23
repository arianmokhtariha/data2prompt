import warnings

# Suppress known noisy warnings globally for a cleaner TUI experience
# We do this before importing pandas to ensure the filters are in place
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import pandas as pd
# Now that pandas is imported, we can reference its error types
warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)
from pathlib import Path
from typing import Set
from .cli import setup_cli, Config
from .parsers import registry, ParserResult, flatten_ir
from .utils import ProjectScanner, count_tokens, check_connectivity
from .ui import ui
from .output import get_generator

def get_ui_action(ext: str, skip_exts: Set[str]) -> str:
    """Determines the UI action string based on file extension."""
    if ext in skip_exts: return "Skipping"
    elif ext == '.csv': return "Sampling"
    elif ext == '.ipynb': return "Cleaning"
    elif ext == '.sql': return "Parsing"
    elif ext in ['.xlsx', '.xls']: return "Extracting"
    return "Reading"

def process_target_file(file_path: Path, config: Config) -> ParserResult:
    """Handles a single file and returns its content, tokens, and metadata."""
    ext = file_path.suffix.lower()
    
    if ext in config.skip_exts:
        return ParserResult(
            content=f"*Note: Binary/Heavy file ({ext}). Content skipped for brevity.*\n",
            tokens=0,
            type=f"Binary ({ext})",
            status="Skipped (Binary)",
            stats_update={"binary_count": 1}
        )
    
    parser = registry.get_parser(ext)
    return parser.parse(file_path, config)

def main():
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
        output_file=config.output
    )
    
    # Collect all files first to set progress bar total
    all_files = scanner.scan()
    total_steps = 1 + 1 + len(all_files) + 1

    # Initialize UI and start process
    ui.on_start("[cyan]Starting process...[/cyan]", total=total_steps)

    stats = {
        "file_count": 0,
        "csv_count": 0,
        "notebook_count": 0,
        "sql_count": 0,
        "excel_count": 0,
        "excel_sheets_count": 0,
        "truncated_count": 0,
        "binary_count": 0
    }
    
    # For the summary table
    processed_files_info = []

    with ui.progress_bar("[cyan]Starting process...[/cyan]", total=total_steps) as handler:
        # 1. Checking connectivity
        handler.on_progress("[cyan]Checking online connectivity...[/cyan]")
        is_online = check_connectivity()
        status_msg = "[green]Online[/green]" if is_online else "[yellow]Offline (using fallback)[/yellow]"
        handler.on_progress(f"[cyan]Checking online connectivity... {status_msg}[/cyan]", advance=1)

        # 2. Generating project tree
        handler.on_progress("[cyan]Generating project tree...[/cyan]")
        tree_text = scanner.generate_tree()
        handler.on_progress("[cyan]Generating project tree...[/cyan]", advance=1)

        # 2. Processing files
        files_data = []
        
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
        
        # We need a temporary token count for the final report
        # The generator will handle the final string construction
        # We use flatten_ir to convert structured content to strings for token counting
        temp_content = "\n".join([flatten_ir(f["content"]) for f in files_data]) + tree_text
        total_tokens, method = count_tokens(temp_content)
        
        generator = get_generator(config.format)
        final_output = generator.generate(
            project_name=project_path.name,
            tree_text=tree_text,
            files_data=files_data,
            stats=stats,
            total_tokens=total_tokens,
            token_method=method,
            config=config
        )

        with open(config.output, 'w', encoding='utf-8') as f:
            f.write(final_output)
        handler.on_progress("[cyan]Compiling project context...[/cyan]", advance=1)

    # Final File Size Check
    file_size_kb = Path(config.output).stat().st_size / 1024
    
    # Display Final Report (Interactive Summary + Success Panel)
    ui.print_final_report(processed_files_info, config.output, file_size_kb, total_tokens, stats, method)
    
    if file_size_kb > 2000:
        ui.print_warning_panel(
            "[bold yellow]WARNING:[/bold yellow] File is over 2MB. This might be too large for some context windows.\n"
            "[bold cyan]Suggestion:[/bold cyan] Reduce --csv-sample-size, --sql-sample-size or --max-lines."
        )

if __name__ == "__main__":
    main()

# Alias for backward compatibility with stale entry point scripts
run_packager = main
