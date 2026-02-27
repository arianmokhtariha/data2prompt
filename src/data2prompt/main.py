import os
import sys
import pandas as pd
from pathlib import Path
from .cli import setup_cli
from .parsers import process_csv, process_notebook, process_sql, process_excel
from .utils import is_binary, generate_tree, count_tokens, load_ignore_file
from .ui import ui
from .constants import GENERATION_FLAG

def run_packager():
    """
    The main entry point for the Data2Prompt CLI.
    Orchestrates the argument parsing, file discovery, content processing, and Markdown generation.
    """
    args = setup_cli() # Retrieve user settings from the terminal
    
    ui.print_header()
    project_path = os.getcwd()

    # Load project-specific ignores from .data2promptignore
    project_ignores = load_ignore_file(project_path)
    
    # Merge project-specific ignores into the existing ignore lists
    # We treat these as both folder and file ignores for maximum coverage
    args.ignore_folders = list(set(args.ignore_folders) | set(project_ignores))
    args.ignore_files = list(set(args.ignore_files) | set(project_ignores))
    
    # 1. Build the Header with Metadata
    md_content = [
        f"<!-- {GENERATION_FLAG} -->",
        f"# 📊 Project Context: {os.path.basename(project_path)}",
        f"> This document provides a structured context of the project's codebase and data schema.",
        f"> It is optimized for LLMs to understand the project structure, file contents, and data formats efficiently.\n",
        f"> Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"> Settings: CSV Sample={args.csv_sample_size}, SQL Sample={args.sql_sample_size}, Line Limit={args.max_lines}, Seed={args.seed}\n"
    ]
    
    with ui.status("Generating project tree structure..."):
        md_content.append("## Project Structure")
        md_content.append("```text")
        tree_text = generate_tree(project_path, args.ignore_folders, args.ignore_files)
        md_content.append(tree_text)
        md_content.append("```\n---\n")
    
    ui.print_step(2, "🛠 Analyzing and Extracting Project Data...")
    
    # Collect all files first to set progress bar total
    all_files = []
    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in args.ignore_folders]
        for file in files:
            if file == args.output or file == os.path.basename(sys.argv[0]) or file in args.ignore_files:
                continue
            all_files.append(Path(root) / file)

    file_count = 0
    csv_count = 0
    notebook_count = 0
    sql_count = 0
    excel_count = 0
    excel_sheets_count = 0
    
    # For the summary table
    processed_files_info = []

    with ui.progress_bar("[cyan]Processing files...", total=len(all_files)) as (progress, task):
        for file_path in all_files:
            relative_path = file_path.relative_to(project_path)
            ext = file_path.suffix.lower()
            file_count += 1
            
            # Determine action for progress bar
            action = "Processing"
            if ext in args.skip_exts: action = "Skipping"
            elif ext == '.csv': action = "Sampling CSV"
            elif ext == '.ipynb': action = "Cleaning Notebook"
            elif ext == '.sql': action = "Parsing SQL"
            elif ext in ['.xlsx', '.xls']: action = "Extracting Excel"
            elif ext == '.md': action = "Reading Markdown"
            else: action = "Reading File"

            progress.update(task, description=f"[cyan]{action}: [bold]{relative_path}[/bold]")
            
            md_content.append(f"## FILE: {relative_path}")
            
            status_str = "Read"
            tokens_in_file = 0
            file_type = ext if ext else "text"

            if ext in args.skip_exts:
                content = f"*Note: Binary/Heavy file ({ext}). Content skipped for brevity.*\n"
                md_content.append(content)
                status_str = "Skipped (Binary)"
                file_type = f"Binary ({ext})"
            elif ext == '.csv':
                content = process_csv(file_path, args.csv_sample_size, args.seed)
                md_content.append(content)
                csv_count += 1
                tokens_in_file = count_tokens(content)
                file_type = "CSV"
                status_str = "Sampled"
            elif ext == '.ipynb':
                content = process_notebook(file_path, args.max_lines)
                md_content.append(content)
                notebook_count += 1
                tokens_in_file = count_tokens(content)
                file_type = "Notebook"
                status_str = "Cleaned"
            elif ext == '.sql':
                content = process_sql(file_path, args.sql_sample_size, args.sql_max_lines)
                md_content.append(content)
                sql_count += 1
                tokens_in_file = count_tokens(content)
                file_type = "SQL"
                status_str = "Parsed"
            elif ext in ['.xlsx', '.xls']:
                excel_md, sheet_count = process_excel(file_path, args.csv_sample_size, args.max_sheets)
                md_content.append(excel_md)
                excel_count += 1
                excel_sheets_count += sheet_count
                tokens_in_file = count_tokens(excel_md)
                file_type = f"Excel ({sheet_count} sheets)"
                status_str = "Extracted"
            elif ext == '.md':
                # Check if the markdown file was generated by this tool to avoid self-recursion
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        if GENERATION_FLAG in f.read(100): # Check first 100 chars for efficiency
                            progress.advance(task)
                            continue
                except:
                    pass
                
                # If not generated by us, treat as normal text file
                file_size_kb = os.path.getsize(file_path) / 1024
                try:
                    if file_size_kb > args.max_file_size:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            header_content = f.read(10 * 1024)
                            content = f"```markdown\n{header_content}\n```"
                            md_content.append(content)
                            md_content.append(f"\n-- [File truncated: Showing first 10KB because it exceeds the size limit ({args.max_file_size}KB) to save context] --\n")
                            tokens_in_file = count_tokens(content)
                            status_str = "Truncated"
                    else:
                        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                            file_text = f.read()
                            content = f"```markdown\n{file_text}\n```"
                            md_content.append(content)
                            tokens_in_file = count_tokens(content)
                except Exception:
                    md_content.append("*Could not read file.*")
                    status_str = "Error"
            else:
                # The New Safety Net: Check for binary content
                if is_binary(file_path):
                    md_content.append(f"*Note: Binary content detected in {ext if ext else 'unknown'} file. Content skipped.*")
                    status_str = "Skipped (Binary)"
                else:
                    file_size_kb = os.path.getsize(file_path) / 1024
                    try:
                        if file_size_kb > args.max_file_size:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                header_content = f.read(10 * 1024)
                                content = f"```{ext[1:] if ext else 'text'}\n{header_content}\n```"
                                md_content.append(content)
                                md_content.append(f"\n-- [File truncated: Showing first 10KB because it exceeds the size limit ({args.max_file_size}KB) to save context] --\n")
                                tokens_in_file = count_tokens(content)
                                status_str = "Truncated"
                        else:
                            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                                file_text = f.read()
                                content = f"```{ext[1:] if ext else 'text'}\n{file_text}\n```"
                                md_content.append(content)
                                tokens_in_file = count_tokens(content)
                    except Exception:
                        md_content.append("*Could not read file.*")
                        status_str = "Error"
            
            processed_files_info.append({
                "name": str(relative_path),
                "type": file_type,
                "tokens": tokens_in_file,
                "status": status_str
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
    file_size_kb = os.path.getsize(args.output) / 1024
    
    # Display Summary Table
    ui.print_summary_table(processed_files_info)

    # Final Success Panel
    stats = {
        "file_count": file_count,
        "csv_count": csv_count,
        "notebook_count": notebook_count,
        "sql_count": sql_count,
        "excel_count": excel_count,
        "excel_sheets_count": excel_sheets_count
    }
    ui.print_success_panel(args.output, file_size_kb, total_tokens, stats)
    
    if file_size_kb > 2000:
        ui.print_warning_panel(
            "⚠️  [bold yellow]WARNING:[/bold yellow] File is over 2MB. This might be too large for some context windows.\n"
            "💡 [bold cyan]Suggestion:[/bold cyan] Reduce --csv-sample-size, --sql-sample-size or --max-lines."
        )

if __name__ == "__main__":
    run_packager()
