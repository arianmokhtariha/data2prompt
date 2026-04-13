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
from typing import Dict, Any
from .cli import setup_cli
from .parsers import process_csv, process_notebook, process_sql, process_excel
from .utils import is_binary, generate_tree, count_tokens, load_ignore_file, get_dynamic_wrapper
from .ui import ui
from .constants import (
    GENERATION_FLAG,
    SYSTEM_INSTRUCTIONS,
    TAG_PROJECT_STRUCTURE,
    TAG_FILE_REPOSITORY,
    TAG_FILE,
    TAG_CONTENT
)

def get_ui_action(ext: str, skip_exts: list[str]) -> str:
    """Determines the UI action string based on file extension."""
    if ext in skip_exts: return "Skipping"
    elif ext == '.csv': return "Sampling"
    elif ext == '.ipynb': return "Cleaning"
    elif ext == '.sql': return "Parsing"
    elif ext in ['.xlsx', '.xls']: return "Extracting"
    elif ext == '.md': return "Reading"
    return "Reading"

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
        result["stats_update"]["binary_count"] = 1
    elif ext == '.csv':
        content = process_csv(
            file_path,
            args.csv_sample_size,
            args.seed,
            args.table_limit,
            args.table_truncate
        )
        result["content"] = content
        result["stats_update"]["csv_count"] = 1
        tokens, _ = count_tokens(content)
        result["tokens"] = tokens
        result["type"] = "CSV"
        result["status"] = "Sampled"
    elif ext == '.ipynb':
        content = process_notebook(
            file_path,
            args.max_lines,
            args.line_length_threshold,
            args.truncated_line_length
        )
        result["content"] = content
        result["stats_update"]["notebook_count"] = 1
        tokens, _ = count_tokens(content)
        result["tokens"] = tokens
        result["type"] = "Notebook"
        result["status"] = "Cleaned"
    elif ext == '.sql':
        content = process_sql(
            file_path,
            args.sql_sample_size,
            args.sql_max_lines,
            args.seed,
            args.line_length_threshold,
            args.truncated_line_length,
            args.table_limit,
            args.table_truncate
        )
        result["content"] = content
        result["stats_update"]["sql_count"] = 1
        tokens, _ = count_tokens(content)
        result["tokens"] = tokens
        result["type"] = "SQL"
        result["status"] = "Parsed"
    elif ext in ['.xlsx', '.xls']:
        excel_md, sheet_count = process_excel(
            file_path,
            args.csv_sample_size,
            args.max_sheets,
            args.seed,
            args.table_limit,
            args.table_truncate
        )
        result["content"] = excel_md
        result["stats_update"]["excel_count"] = 1
        result["stats_update"]["excel_sheets_count"] = sheet_count
        tokens, _ = count_tokens(excel_md)
        result["tokens"] = tokens
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
            result["stats_update"]["binary_count"] = 1
        else:
            file_size_kb = file_path.stat().st_size / 1024
            try:
                lang = ext[1:] if ext and ext != '.md' else 'markdown' if ext == '.md' else 'text'
                if file_size_kb > args.max_file_size:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        header_content = f.read(10 * 1024)
                        result["content"] = header_content
                        result["content"] += f"\n-- [File truncated: Showing first 10KB because it exceeds the size limit ({args.max_file_size}KB) to save context] --\n"
                        tokens, _ = count_tokens(result["content"])
                        result["tokens"] = tokens
                        result["status"] = "Truncated"
                        result["stats_update"]["truncated_count"] = 1
                else:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        file_text = f.read()
                        result["content"] = file_text
                        tokens, _ = count_tokens(result["content"])
                        result["tokens"] = tokens
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
        f"# Project Context: {project_path.name}",
        SYSTEM_INSTRUCTIONS,
        f"> Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}\n",
        ""  # Blank line for spacing
    ]
    
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
        "excel_sheets_count": 0,
        "truncated_count": 0,
        "binary_count": 0
    }
    
    # For the summary table
    processed_files_info = []

    # Total steps: 1 (Tree) + N (Files) + 1 (Compiling)
    total_steps = 1 + len(all_files) + 1
    
    with ui.progress_bar("[cyan]Starting process...[/cyan]", total=total_steps) as (progress, task):
        # 1. Generating project tree
        progress.update(task, description="[cyan]Generating project tree...[/cyan]")
        md_content.append("## Project Structure")
        md_content.append(f"<{TAG_PROJECT_STRUCTURE}>")
        md_content.append("```text")
        tree_text = generate_tree(str(project_path), args.ignore_folders, args.ignore_files)
        md_content.append(tree_text)
        md_content.append("```")
        md_content.append(f"</{TAG_PROJECT_STRUCTURE}>\n---\n")
        progress.advance(task)

        # 2. Processing files
        md_content.append("## File Repository")
        md_content.append(f"<{TAG_FILE_REPOSITORY}>")
        
        for file_path in all_files:
            relative_path = file_path.relative_to(project_path)
            ext = file_path.suffix.lower()
            stats["file_count"] += 1
            
            # Determine action for progress bar - show only filename
            action = get_ui_action(ext, args.skip_exts)
            progress.update(task, description=f"[cyan]{action}[/cyan] [bold]{file_path.name}[/bold] [cyan]...[/cyan]")
            
            result = process_target_file(file_path, args)
            if result.get("skip_file"):
                progress.advance(task)
                continue

            # File Header with Metadata
            # We use a custom anchor to ensure the TOC works reliably
            anchor_name = f"file-{str(relative_path).lower().replace(' ', '-').replace('.', '').replace('/', '').replace('\\', '')}"
            md_content.append(f'### <a name="{anchor_name}"></a>📄 File: `{relative_path}`')
            md_content.append(f"> **Metadata:** Type: `{result['type']}` | Tokens: `{result['tokens']}` | Status: `{result['status']}`")
            
            # XML Wrapping with Dynamic Backticks
            wrapper = get_dynamic_wrapper(result["content"])
            lang = ext[1:] if ext and ext != '.md' else 'markdown' if ext == '.md' else 'text'
            
            md_content.append(f'<{TAG_FILE} path="{relative_path}">')
            md_content.append(f"<{TAG_CONTENT}>")
            md_content.append(f"{wrapper}{lang}\n{result['content']}\n{wrapper}")
            md_content.append(f"</{TAG_CONTENT}>")
            md_content.append(f"</{TAG_FILE}>")
            
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

        md_content.append(f"</{TAG_FILE_REPOSITORY}>")

        # 3. Compiling project context
        progress.update(task, description="[cyan]Compiling project context...[/cyan]")
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

        with open(args.output, 'w', encoding='utf-8') as f:
            f.write("\n".join(md_content))
        progress.advance(task)

    # Final File Size Check
    file_size_kb = Path(args.output).stat().st_size / 1024
    
    # Display Final Report (Interactive Summary + Success Panel)
    ui.print_final_report(processed_files_info, args.output, file_size_kb, total_tokens, stats, method)
    
    if file_size_kb > 2000:
        ui.print_warning_panel(
            "[bold yellow]WARNING:[/bold yellow] File is over 2MB. This might be too large for some context windows.\n"
            "[bold cyan]Suggestion:[/bold cyan] Reduce --csv-sample-size, --sql-sample-size or --max-lines."
        )

if __name__ == "__main__":
    run_packager()
