import os
import sys
import warnings

# Suppress known noisy warnings globally for a cleaner TUI experience
# We do this before importing pandas to ensure the filters are in place
warnings.filterwarnings("ignore", category=UserWarning, module="openpyxl")

import pandas as pd
# Now that pandas is imported, we can reference its error types
warnings.filterwarnings("ignore", category=pd.errors.DtypeWarning)
from pathlib import Path
from typing import Dict, Any, List, Set
from .cli import setup_cli, Config
from .parsers import registry, ParserResult
from .utils import ProjectScanner, count_tokens, get_dynamic_wrapper
from .ui import ui
from .constants import (
    GENERATION_FLAG,
    SYSTEM_INSTRUCTIONS,
    TAG_PROJECT_STRUCTURE,
    TAG_FILE_REPOSITORY,
    TAG_FILE,
    TAG_CONTENT
)

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

def run_packager():
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
    total_steps = 1 + len(all_files) + 1

    # Initialize UI and start process
    ui.on_start("[cyan]Starting process...[/cyan]", total=total_steps)

    # 1. Build the Header with Metadata
    md_content = [
        f"<!-- {GENERATION_FLAG} -->",
        f"# Project Context: {project_path.name}",
        SYSTEM_INSTRUCTIONS,
        f"> Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n",
        ""  # Blank line for spacing
    ]
    
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
        # 1. Generating project tree
        handler.on_progress("[cyan]Generating project tree...[/cyan]")
        md_content.append("## Project Structure")
        md_content.append(f"<{TAG_PROJECT_STRUCTURE}>")
        md_content.append("```text")
        tree_text = scanner.generate_tree()
        md_content.append(tree_text)
        md_content.append("```")
        md_content.append(f"</{TAG_PROJECT_STRUCTURE}>\n---\n")
        handler.on_progress("[cyan]Generating project tree...[/cyan]", advance=1)

        # 2. Processing files
        md_content.append("## File Repository")
        md_content.append(f"<{TAG_FILE_REPOSITORY}>")
        
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

            # File Header with Metadata
            # We use a custom anchor to ensure the TOC works reliably
            anchor_name = f"file-{str(relative_path).lower().replace(' ', '-').replace('.', '').replace('/', '').replace('\\', '')}"
            md_content.append(f'### <a name="{anchor_name}"></a>📄 File: `{relative_path}`')
            md_content.append(f"> **Metadata:** Type: `{result.type}` | Tokens: `{result.tokens}` | Status: `{result.status}`")
            
            # XML Wrapping with Dynamic Backticks
            wrapper = get_dynamic_wrapper(result.content)
            lang = ext[1:] if ext and ext != '.md' else 'markdown' if ext == '.md' else 'text'
            
            md_content.append(f'<{TAG_FILE} path="{relative_path}">')
            md_content.append(f"<{TAG_CONTENT}>")
            md_content.append(f"{wrapper}{lang}\n{result.content}\n{wrapper}")
            md_content.append(f"</{TAG_CONTENT}>")
            md_content.append(f"</{TAG_FILE}>")
            
            # Update stats
            for key, value in result.stats_update.items():
                stats[key] += value
            
            processed_files_info.append({
                "name": str(relative_path),
                "type": result.type,
                "tokens": result.tokens,
                "status": result.status
            })
            
            md_content.append("\n---\n")
            handler.on_progress(f"[cyan]{action}[/cyan] [bold]{file_path.name}[/bold] [cyan]...[/cyan]", advance=1)

        md_content.append(f"</{TAG_FILE_REPOSITORY}>")

        # 3. Compiling project context
        handler.on_progress("[cyan]Compiling project context...[/cyan]")
        # Calculate tokens before final save
        full_content_temp = "\n".join(md_content)
        total_tokens, method = count_tokens(full_content_temp)
        
        # Insert token count into the header (after generated on line)
        method_label = "o200k_base" if method == "o200k_base" else "regex_fallback" if method == "regex_fallback" else "word_count"
        md_content.insert(4, f"> Tokens: {total_tokens} (est. via {method_label})")
        
        # Generate Summary Table (TOC)
        summary_table = ["## Summary Table", "| File | Type | Tokens | Status |", "| :--- | :--- | :--- | :--- |"]
        for info in processed_files_info:
            # Create a markdown anchor from the file path
            # Markdown anchors for headers: lowercase, spaces to hyphens, remove special chars
            anchor = info['name'].lower().replace(' ', '-').replace('.', '').replace('/', '').replace('\\', '')
            # The actual header format is "### 📄 File: `path`"
            # Rich/Markdown usually handles this by stripping the emoji and backticks
            # Let's use a more direct approach for the anchor
            safe_anchor = f"file-{anchor}"
            # We'll need to update the header to include this anchor
            summary_table.append(f"| [{info['name']}](#{safe_anchor}) | {info['type']} | {info['tokens']} | {info['status']} |")
        
        md_content.insert(5, "\n".join(summary_table))
        md_content.insert(6, "\n---\n")

        with open(config.output, 'w', encoding='utf-8') as f:
            f.write("\n".join(md_content))
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
    run_packager()
