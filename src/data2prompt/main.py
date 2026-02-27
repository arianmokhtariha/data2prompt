import os
import sys
import pandas as pd
from pathlib import Path
from typing import Dict, Any
from .cli import setup_cli
from .parsers import process_csv, process_notebook, process_sql, process_excel
from .utils import is_binary, generate_tree, count_tokens, load_ignore_file
from .ui import ui
from .constants import GENERATION_FLAG

def get_ui_action(ext: str, skip_exts: list[str]) -> str:
    """Determines the UI action string based on file extension."""
    if ext in skip_exts: return "Skipping"
    elif ext == '.csv': return "Sampling CSV"
    elif ext == '.ipynb': return "Cleaning Notebook"
    elif ext == '.sql': return "Parsing SQL"
    elif ext in ['.xlsx', '.xls']: return "Extracting Excel"
    elif ext == '.md': return "Reading Markdown"
    return "Reading File"

def process_target_file(file_path: Path, args: Any) -> Dict[str, Any]:
    """Handles a single file and returns its content, tokens, and metadata."""
    ext = file_path.suffix.lower()
    result = {
        "content": "",
        "tokens": 0,
        "type": ext if ext else "text",
        "status": "Read",
        "stats_update": {},
        "skip_file": False
    }

    if ext in args.skip_exts:
        result["content"] = f"*Note: Binary/Heavy file ({ext}). Content skipped for brevity.*\n"
        result["status"] = "Skipped (Binary)"
        result["type"] = f"Binary ({ext})"
    elif ext == '.csv':
        content = process_csv(file_path, args.csv_sample_size, args.seed)
        result["content"] = content
        result["stats_update"]["csv_count"] = 1
        result["tokens"] = count_tokens(content)
        result["type"] = "CSV"
        result["status"] = "Sampled"
    elif ext == '.ipynb':
        content = process_notebook(file_path, args.max_lines)
        result["content"] = content
        result["stats_update"]["notebook_count"] = 1
        result["tokens"] = count_tokens(content)
        result["type"] = "Notebook"
        result["status"] = "Cleaned"
    elif ext == '.sql':
        content = process_sql(file_path, args.sql_sample_size, args.sql_max_lines)
        result["content"] = content
        result["stats_update"]["sql_count"] = 1
        result["tokens"] = count_tokens(content)
        result["type"] = "SQL"
        result["status"] = "Parsed"
    elif ext in ['.xlsx', '.xls']:
        excel_md, sheet_count = process_excel(file_path, args.csv_sample_size, args.max_sheets)
        result["content"] = excel_md
        result["stats_update"]["excel_count"] = 1
        result["stats_update"]["excel_sheets_count"] = sheet_count
        result["tokens"] = count_tokens(excel_md)
        result["type"] = f"Excel ({sheet_count} sheets)"
        result["status"] = "Extracted"
    elif ext == '.md':
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if GENERATION_FLAG in f.read(100):
                    result["skip_file"] = True
                    return result
        except:
            pass

    # Fallback for .md and other text files
    if not result["content"] and not result["skip_file"]:
        if is_binary(file_path):
            result["content"] = f"*Note: Binary content detected in {ext if ext else 'unknown'} file. Content skipped.*"
            result["status"] = "Skipped (Binary)"
        else:
            file_size_kb = file_path.stat().st_size / 1024
            try:
                lang = ext[1:] if ext and ext != '.md' else 'markdown' if ext == '.md' else 'text'
                if file_size_kb > args.max_file_size:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        header_content = f.read(10 * 1024)
                        result["content"] = f"```{lang}\n{header_content}\n```"
                        result["content"] += f"\n-- [File truncated: Showing first 10KB because it exceeds the size limit ({args.max_file_size}KB) to save context] --\n"
                        result["tokens"] = count_tokens(result["content"])
                        result["status"] = "Truncated"
                else:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        file_text = f.read()
                        result["content"] = f"```{lang}\n{file_text}\n```"
                        result["tokens"] = count_tokens(result["content"])
            except Exception:
                result["content"] = "*Could not read file.*"
                result["status"] = "Error"

    return result

def run_packager():
    """
    The main entry point for the Data2Prompt CLI.
    Orchestrates the argument parsing, file discovery, content processing, and Markdown generation.
    """
    args = setup_cli() # Retrieve user settings from the terminal
    
    ui.print_header()
    project_path = Path.cwd()

    # Load project-specific ignores from .data2promptignore
    project_ignores = load_ignore_file(str(project_path))
    
    # Merge project-specific ignores into the existing ignore lists
    # We treat these as both folder and file ignores for maximum coverage
    args.ignore_folders = list(set(args.ignore_folders) | set(project_ignores))
    args.ignore_files = list(set(args.ignore_files) | set(project_ignores))
    
    # 1. Build the Header with Metadata
    md_content = [
        f"<!-- {GENERATION_FLAG} -->",
        f"# 📊 Project Context: {project_path.name}",
        f"> This document provides a structured context of the project's codebase and data schema.",
        f"> It is optimized for LLMs to understand the project structure, file contents, and data formats efficiently.\n",
        f"> Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"> Settings: CSV Sample={args.csv_sample_size}, SQL Sample={args.sql_sample_size}, Line Limit={args.max_lines}, Seed={args.seed}\n"
    ]
    
    with ui.status("Generating project tree structure..."):
        md_content.append("## Project Structure")
        md_content.append("```text")
        tree_text = generate_tree(str(project_path), args.ignore_folders, args.ignore_files)
        md_content.append(tree_text)
        md_content.append("```\n---\n")
    
    ui.print_step(2, "🛠 Analyzing and Extracting Project Data...")
    
    # Collect all files first to set progress bar total
    all_files = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in args.ignore_folders]
        for file in files:
            if file == args.output or file == Path(sys.argv[0]).name or file in args.ignore_files:
                continue
            all_files.append(Path(root) / file)

    stats = {
        "file_count": 0,
        "csv_count": 0,
        "notebook_count": 0,
        "sql_count": 0,
        "excel_count": 0,
        "excel_sheets_count": 0
    }
    
    # For the summary table
    processed_files_info = []

    with ui.progress_bar("[cyan]Processing files...", total=len(all_files)) as (progress, task):
        for file_path in all_files:
            relative_path = file_path.relative_to(project_path)
            ext = file_path.suffix.lower()
            stats["file_count"] += 1
            
            # Determine action for progress bar
            action = get_ui_action(ext, args.skip_exts)
            progress.update(task, description=f"[cyan]{action}: [bold]{relative_path}[/bold]")
            
            result = process_target_file(file_path, args)
            if result.get("skip_file"):
                progress.advance(task)
                continue

            md_content.append(f"## FILE: {relative_path}")
            md_content.append(result["content"])
            
            # Update stats
            for key, value in result["stats_update"].items():
                stats[key] += value
            
            processed_files_info.append({
                "name": str(relative_path),
                "type": result["type"],
                "tokens": result["tokens"],
                "status": result["status"]
            })
            
            md_content.append("\n---\n")
            progress.advance(task)

    ui.print_step(3, f"💾 Saving to {args.output}...")
    
    # Calculate tokens before final save
    full_content_temp = "\n".join(md_content)
    total_tokens = count_tokens(full_content_temp)
    
    # Insert token count into the header (after settings line)
    md_content.insert(6, f"> Tokens: {total_tokens} (est. via o200k_base)\n")
    
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_content))

    # Final File Size Check
    file_size_kb = Path(args.output).stat().st_size / 1024
    
    # Display Summary Table
    ui.print_summary_table(processed_files_info)

    # Final Success Panel
    ui.print_success_panel(args.output, file_size_kb, total_tokens, stats)
    
    if file_size_kb > 2000:
        ui.print_warning_panel(
            "⚠️  [bold yellow]WARNING:[/bold yellow] File is over 2MB. This might be too large for some context windows.\n"
            "💡 [bold cyan]Suggestion:[/bold cyan] Reduce --csv-sample-size, --sql-sample-size or --max-lines."
        )

if __name__ == "__main__":
    run_packager()
