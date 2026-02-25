import os
import json
import pandas as pd
import sys
from pathlib import Path
import argparse


def setup_cli():
    parser = argparse.ArgumentParser(
        description="📊 Data2Prompt: High-tech prompt packaging for Data Scientists."
    )
    
    # Output settings
    parser.add_argument('-o', '--output', default='PROMPT.md', 
                        help='Name of the generated markdown file (default: PROMPT.md)')
    
    # CSV sampling settings
    parser.add_argument('-s', '--sample-size', type=int, default=70, 
                        help='Number of random rows to sample from CSVs (default: 70)')
    parser.add_argument('--seed', type=int, default=42, 
                        help='Random seed for consistent CSV sampling (default: 42)')
    
    # Notebook settings
    parser.add_argument('--max-lines', type=int, default=55, 
                        help='Max lines of text output to keep per notebook cell (default: 55)')
    
    # Exclusions
    parser.add_argument('--ignore-folders', nargs='+', 
                        default=['.git', '__pycache__', 'venv', '.vscode', '.ipynb_checkpoints'],
                        help='Folders to skip entirely')
    
    return parser.parse_args()


print("🚀 Script is starting...")
def print_header():
    header = """
    ==============================================
        📊 DATA PROJECT -> LLM PROMPT PACKAGER 📊
    ==============================================
    """
    print(header)

def get_status_msg(file_path, file_count):
    sys.stdout.write(f"\r[#{file_count}] Processing: {file_path[:50]}...".ljust(70))
    sys.stdout.flush()

def generate_tree(startpath):
    tree = []
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in IGNORE_FOLDERS]
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * level
        tree.append(f"{indent}📂 {os.path.basename(root)}/")
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            tree.append(f"{sub_indent}📄 {f}")
    return "\n".join(tree)

def process_csv(file_path):
    try:
        df = pd.read_csv(file_path)
        if len(df) > CSV_SAMPLE_SIZE:
            df = df.sample(CSV_SAMPLE_SIZE)
        return f"#### [Sample - Random {CSV_SAMPLE_SIZE} rows]\n" + df.to_markdown(index=False)
    except Exception as e:
        return f"Error reading CSV: {e}"

def process_notebook(file_path):
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            nb = json.load(f)
        output_md = []
        
        # Added enumeration to track cell numbers
        for i, cell in enumerate(nb.get('cells', []), 1):
            cell_type = cell['cell_type'].upper()
            
            # Create a clear, readable header for the LLM
            output_md.append(f"### Cell {i} [{cell_type}]")
            
            if cell['cell_type'] == 'markdown':
                output_md.append("".join(cell['source']))
            
            elif cell['cell_type'] == 'code':
                code = "".join(cell['source'])
                output_md.append(f"```python\n{code}\n```")
                
                for out in cell.get('outputs', []):
                    if out.get('output_type') == 'stream':
                        text = "".join(out.get('text', []))
                        if text.count('\n') < MAX_NOTEBOOK_TEXT_LINES:
                            output_md.append(f"> **Cell {i} Output:**\n> {text.strip()}")
                    
                    elif out.get('output_type') in ['execute_result', 'display_data']:
                        data = out.get('data', {})
                        if 'text/plain' in data:
                            content = "".join(data['text/plain'])
                            if "base64" not in content and content.count('\n') < MAX_NOTEBOOK_TEXT_LINES:
                                output_md.append(f"> **Cell {i} Data Preview:**\n> {content.strip()}")
                                
            output_md.append("\n---\n") # Visual separator between cells
            
        return "\n\n".join(output_md)
    except Exception as e:
        return f"Error processing notebook: {e}"

def run_packager():
    args = setup_cli() # Get settings from terminal
    
    print_header()
    project_path = os.getcwd()
    
    # Internal counters for the stats table
    stats = {"files": 0, "csvs": 0, "notebooks": 0}
    
    # 1. Build the Header with Metadata
    md_content = [
        f"# 📊 Project Context: {os.path.basename(project_path)}",
        f"> Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"> Settings: Sample Size={args.sample_size}, Line Limit={args.max_lines}\n"
    ]

    project_path = os.getcwd()
    md_content = [f"# Project Context: {os.path.basename(project_path)}\n"]
    
    print("Step 1: 🌳 Generating project tree structure...")
    md_content.append("## Project Structure")
    md_content.append("```text")
    tree_text = generate_tree(project_path)
    md_content.append(tree_text)
    md_content.append("```\n---\n")
    
    print("Step 2: 🛠 Processing file contents...")
    file_count = 0
    csv_count = 0
    notebook_count = 0

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in IGNORE_FOLDERS]
        for file in files:
            if file == OUTPUT_FILE or file == sys.argv[0]:
                continue
                
            file_path = Path(root) / file
            relative_path = file_path.relative_to(project_path)
            ext = file_path.suffix.lower()
            
            file_count += 1
            get_status_msg(str(relative_path), file_count)

            md_content.append(f"## FILE: {relative_path}")
            
            if ext in SKIP_CONTENT_EXTENSIONS:
                md_content.append(f"*Note: Binary/Heavy file ({ext}). Content skipped for brevity.*\n")
            elif ext == '.csv':
                md_content.append(process_csv(file_path))
                csv_count += 1
            elif ext == '.ipynb':
                md_content.append(process_notebook(file_path))
                notebook_count += 1
            else:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        md_content.append(f"```{ext[1:] if ext else 'text'}\n{f.read()}\n```")
                except:
                    md_content.append("*Could not read file.*")
            
            md_content.append("\n---\n")

    print(f"\n\nStep 3: 💾 Saving to {OUTPUT_FILE}...")
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_content))

    # Final File Size Check
    file_size_kb = os.path.getsize(args.output) / 1024
    
    print("\n" + "="*46)
    print(f"✅ DONE! Created: {args.output} ({file_size_kb:.1f} KB)")
    print(f"📂 Total Files Processed: {file_count}")
    print(f"📊 CSVs Sampled:         {csv_count}")
    print(f"📓 Notebooks Cleaned:    {notebook_count}")
    
    if file_size_kb > 2000:
        print("⚠️  WARNING: File is over 2MB. This might be too large for some context windows.")
        print("💡 Suggestion: Reduce --sample-size or --max-lines.")
    print("="*46)

if __name__ == "__main__":
    run_packager()