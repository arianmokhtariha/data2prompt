import json
import pandas as pd

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

def process_sql(file_path, sample_size, max_lines):
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        processed_lines = []
        table_row_count = 0
        is_truncated = False
        
        for line in lines:
            line_upper = line.upper()
            
            # 1. Detect New Table (Reset Counter)
            if "CREATE TABLE" in line_upper or "BEGIN TABLE" in line_upper:
                table_row_count = 0
                is_truncated = False
                processed_lines.append(line)
                continue

            # 2. Handle Inserts and Data Rows (Sample per table)
            is_insert = "INSERT INTO" in line_upper
            is_data_row = line.strip().startswith("(")
            
            if is_insert or is_data_row:
                if table_row_count < sample_size:
                    processed_lines.append(line)
                    table_row_count += 1
                elif not is_truncated:
                    processed_lines.append("-- ... [Table data truncated for brevity] ...\n")
                    is_truncated = True
                continue
            
            # 3. Keep other schema keywords
            schema_keywords = ["ALTER ", "CONSTRAINT ", "VIEW ", "DROP ", "INDEX ", "TABLE "]
            if any(kw in line_upper for kw in schema_keywords):
                processed_lines.append(line)
                continue
                
            # 4. Keep other lines (comments, setup) up to the max_lines limit
            if len(processed_lines) < max_lines:
                processed_lines.append(line)
        
        return "```sql\n" + "".join(processed_lines) + "\n```"
    except Exception as e:
        return f"⚠️ Error reading SQL: {e}"
