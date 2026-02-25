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
    parser.add_argument('-s', '--csv-sample-size', type=int, default=70,
                        help='Number of random rows to sample from CSVs (default: 70)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for consistent CSV sampling (default: 42)')
    
    # SQL sampling settings
    parser.add_argument('--sql-sample-size', type=int, default=70,
                        help='Number of INSERT statements to keep in SQL files (default: 70)')
    
    # Notebook settings
    parser.add_argument('--max-lines', type=int, default=55,
                        help='Max lines of text output to keep per notebook cell (default: 55)')
    
    # Exclusions
    parser.add_argument('--ignore-folders', nargs='+',
                        default=['.git', '__pycache__', 'venv', '.vscode', '.ipynb_checkpoints'],
                        help='Folders to skip entirely')
    
    # file formats to ignore 
    parser.add_argument('--skip-exts', nargs='+',
                        default=['.pbix', '.db', '.sqlite', '.zip', '.png', '.jpg', '.jpeg', '.pdf', '.pkl', '.parquet', '.exe'],
                        help='File extensions to skip content for (binary/heavy files)')
    
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

def generate_tree(startpath, ignore_folders):
    tree = []
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in ignore_folders]
        level = root.replace(startpath, '').count(os.sep)
        indent = ' ' * 4 * level
        tree.append(f"{indent}📂 {os.path.basename(root)}/")
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            tree.append(f"{sub_indent}📄 {f}")
    return "\n".join(tree)

def process_csv(file_path, sample_size, seed=42):
    try:
        df = pd.read_csv(file_path)
        if len(df) > sample_size:
            df = df.sample(sample_size, random_state=seed)
        return f"#### [Sample - Random {sample_size} rows]\n" + df.to_markdown(index=False)
    except Exception as e:
        return f"Error reading CSV: {e}"
    
def process_notebook(file_path, max_lines):
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
                        if text.count('\n') < max_lines:
                            output_md.append(f"> **Cell {i} Output:**\n> {text.strip()}")
                    
                    elif out.get('output_type') in ['execute_result', 'display_data']:
                        data = out.get('data', {})
                        if 'text/plain' in data:
                            content = "".join(data['text/plain'])
                            if "base64" not in content and content.count('\n') < max_lines:
                                output_md.append(f"> **Cell {i} Data Preview:**\n> {content.strip()}")
                                
            output_md.append("\n---\n") # Visual separator between cells
            
        return "\n\n".join(output_md)
    except Exception as e:
        return f"Error processing notebook: {e}"

def process_sql(file_path, max_lines, max_inserts):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        processed_lines = []
        insert_count = 0
        
        for line in lines:
            # Keep schema definitions always
            if any(keyword in line.upper() for keyword in ["CREATE", "ALTER", "TABLE", "CONSTRAINT", "VIEW"]):
                processed_lines.append(line)
            # Sample the Inserts
            elif "INSERT INTO" in line.upper():
                if insert_count < max_inserts:
                    processed_lines.append(line)
                    insert_count += 1
                elif insert_count == max_inserts:
                    processed_lines.append("-- ... [Additional INSERT statements truncated for brevity] ...\n")
                    insert_count += 1
            # Keep short comments or small setup lines
            elif len(processed_lines) < max_lines:
                processed_lines.append(line)
        
        return "```sql\n" + "".join(processed_lines) + "\n```"
    except Exception as e:
        return f"⚠️ Error reading SQL: {e}"

def run_packager():
    args = setup_cli() # Get settings from terminal
    
    print_header()
    project_path = os.getcwd()
    
    # 1. Build the Header with Metadata
    md_content = [
        f"# 📊 Project Context: {os.path.basename(project_path)}",
        f"> Generated on: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')}",
        f"> Settings: CSV Sample={args.csv_sample_size}, SQL Sample={args.sql_sample_size}, Line Limit={args.max_lines}, Seed={args.seed}\n"
    ]
    
    print("Step 1: 🌳 Generating project tree structure...")
    md_content.append("## Project Structure")
    md_content.append("```text")
    tree_text = generate_tree(project_path, args.ignore_folders)
    md_content.append(tree_text)
    md_content.append("```\n---\n")
    
    print("Step 2: 🛠 Processing file contents...")
    file_count = 0
    csv_count = 0
    notebook_count = 0
    sql_count = 0

    for root, dirs, files in os.walk(project_path):
        dirs[:] = [d for d in dirs if d not in args.ignore_folders]
        for file in files:
            # Skip the output file itself and the script file
            if file == args.output or file == os.path.basename(sys.argv[0]):
                continue
                
            file_path = Path(root) / file
            relative_path = file_path.relative_to(project_path)
            ext = file_path.suffix.lower()
            
            file_count += 1
            get_status_msg(str(relative_path), file_count)
            
            md_content.append(f"## FILE: {relative_path}")
            
            if ext in args.skip_exts:
                md_content.append(f"*Note: Binary/Heavy file ({ext}). Content skipped for brevity.*\n")
            elif ext == '.csv':
                md_content.append(process_csv(file_path, args.csv_sample_size, args.seed))
                csv_count += 1
            elif ext == '.ipynb':
                md_content.append(process_notebook(file_path, args.max_lines))
                notebook_count += 1
            elif ext == '.sql':
                md_content.append(process_sql(file_path, args.max_lines, args.sql_sample_size))
                sql_count += 1
            else:
                try:
                    with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                        md_content.append(f"```{ext[1:] if ext else 'text'}\n{f.read()}\n```")
                except:
                    md_content.append("*Could not read file.*")
            
            md_content.append("\n---\n")

    print(f"\n\nStep 3: 💾 Saving to {args.output}...")
    with open(args.output, 'w', encoding='utf-8') as f:
        f.write("\n".join(md_content))

    # Final File Size Check
    file_size_kb = os.path.getsize(args.output) / 1024
    
    print("\n" + "="*46)
    print(f"✅ DONE! Created: {args.output} ({file_size_kb:.1f} KB)")
    print(f"📂 Total Files Processed: {file_count}")
    print(f"📊 CSVs Sampled:         {csv_count}")
    print(f"📓 Notebooks Cleaned:    {notebook_count}")
    print(f"🗄️ SQL Scripts Parsed:   {sql_count}")
    
    if file_size_kb > 2000:
        print("⚠️  WARNING: File is over 2MB. This might be too large for some context windows.")
        print("💡 Suggestion: Reduce --csv-sample-size, --sql-sample-size or --max-lines.")
    print("="*46)

if __name__ == "__main__":
    run_packager()