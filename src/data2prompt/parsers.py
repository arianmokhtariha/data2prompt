import json
import random
import warnings
from pathlib import Path
from typing import List, Tuple, Union

import openpyxl
import pandas as pd

from .constants import (
    DEFAULT_CSV_SAMPLE_SIZE,
    DEFAULT_SQL_SAMPLE_SIZE,
    DEFAULT_SQL_MAX_LINES,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_SHEETS,
    DEFAULT_SEED
)

def process_csv(
    file_path: Union[str, Path],
    sample_size: int = DEFAULT_CSV_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
) -> str:
    try:
        df = pd.read_csv(file_path, low_memory=False)
        if len(df) > sample_size:
            df = df.sample(sample_size, random_state=seed)
            footer = f"\n\n-- [CSV truncated: Showing random {sample_size} rows to save context] --"
        else:
            footer = ""
        return (
            f"#### [Sample - Random {sample_size} rows]\n"
            + df.to_markdown(index=False)
            + footer
        )
    except pd.errors.EmptyDataError:
        return "*Note: CSV file is empty.*"
    except Exception as e:
        return f"Error reading CSV: {e}"


def process_notebook(
    file_path: Union[str, Path], max_lines: int = DEFAULT_MAX_LINES
) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
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
                        lines = text.strip().split('\n')
                        if len(lines) > max_lines:
                            truncated_text = '\n'.join(lines[:max_lines])
                            output_md.append(f"> **Cell {i} Output:**\n> {truncated_text}\n> -- [Output truncated: Showing first {max_lines} lines to save context] --")
                        else:
                            output_md.append(f"> **Cell {i} Output:**\n> {text.strip()}")
                    
                    elif out.get('output_type') in ['execute_result', 'display_data']:
                        data = out.get('data', {})
                        if 'text/plain' in data:
                            content = "".join(data['text/plain'])
                            if "base64" not in content:
                                lines = content.strip().split('\n')
                                if len(lines) > max_lines:
                                    truncated_content = '\n'.join(lines[:max_lines])
                                    output_md.append(f"> **Cell {i} Data Preview:**\n> {truncated_content}\n> -- [Data preview truncated: Showing first {max_lines} lines to save context] --")
                                else:
                                    output_md.append(f"> **Cell {i} Data Preview:**\n> {content.strip()}")
                                
            output_md.append("\n---\n") # Visual separator between cells
            
        return "\n\n".join(output_md)
    except json.JSONDecodeError:
        return "*Error: Malformed Jupyter Notebook (Invalid JSON).*"
    except Exception as e:
        return f"Error processing notebook: {e}"


def process_sql(
    file_path: Union[str, Path],
    sample_size: int = DEFAULT_SQL_SAMPLE_SIZE,
    max_lines: int = DEFAULT_SQL_MAX_LINES,
    seed: int = DEFAULT_SEED,
) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
        
        processed_lines = []
        table_data_buffer: List[str] = []
        in_create_block = False
        rng = random.Random(seed)

        def flush_buffer():
            if not table_data_buffer:
                return
            
            if len(table_data_buffer) > sample_size:
                # Randomly sample indices to maintain relative order
                indices = sorted(rng.sample(range(len(table_data_buffer)), sample_size))
                for idx in indices:
                    processed_lines.append(table_data_buffer[idx])
                processed_lines.append(f"-- [Table data truncated: Showing random {sample_size} rows to save context] --\n")
            else:
                processed_lines.extend(table_data_buffer)
            table_data_buffer.clear()

        for line in lines:
            line_upper = line.upper()
            line_stripped = line.strip()
            
            # 1. Detect New Table (Flush Buffer & Start Block)
            if "CREATE TABLE" in line_upper or "BEGIN TABLE" in line_upper:
                flush_buffer()
                in_create_block = True
                processed_lines.append(line)
                continue

            # 2. Handle Inserts and Data Rows (Buffer per table)
            is_insert = "INSERT INTO" in line_upper
            is_data_row = line_stripped.startswith("(") or line_stripped.startswith(", (")
            
            if is_insert or is_data_row:
                in_create_block = False # Data rows mean we are out of the CREATE block
                table_data_buffer.append(line)
                continue
            
            # 3. Keep other schema keywords (Flush Buffer first)
            schema_keywords = ["ALTER ", "CONSTRAINT ", "VIEW ", "DROP ", "INDEX ", "TABLE "]
            if any(kw in line_upper for kw in schema_keywords):
                flush_buffer()
                in_create_block = False
                processed_lines.append(line)
                continue
            
            # 4. End of CREATE block detection (closing parenthesis at start of line)
            if in_create_block and line_stripped.startswith(")") and (line_stripped.endswith(";") or "ENGINE" in line_upper):
                processed_lines.append(line)
                in_create_block = False
                continue

            # 5. Keep lines if inside CREATE block OR under max_lines limit
            if in_create_block:
                processed_lines.append(line)
            elif len(processed_lines) < max_lines:
                flush_buffer() # Ensure data is flushed before adding more non-data lines
                processed_lines.append(line)
        
        # Final flush for the last table
        flush_buffer()
        
        return "```sql\n" + "".join(processed_lines) + "\n```"
    except Exception as e:
        return f"⚠️ Error reading SQL: {e}"

def process_excel(
    file_path: Union[str, Path],
    max_rows: int = DEFAULT_CSV_SAMPLE_SIZE,
    max_sheets: int = DEFAULT_MAX_SHEETS,
    seed: int = DEFAULT_SEED,
) -> Tuple[str, int]:
    try:
        # 1. Sheet Discovery & Visual Element Check using openpyxl
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        sheet_names = wb.sheetnames
        
        output_md = []
        processed_sheets = 0
        
        for sheet_name in sheet_names:
            if processed_sheets >= max_sheets:
                output_md.append(f"\n-- [Workbook truncated: Only first {max_sheets} sheets processed] --\n")
                break
            
            processed_sheets += 1
            sheet = wb[sheet_name]
            
            # Check for visual elements
            has_visuals = False
            try:
                if hasattr(sheet, '_images') and len(sheet._images) > 0:
                    has_visuals = True
                if hasattr(sheet, 'charts') and len(sheet.charts) > 0:
                    has_visuals = True
            except:
                pass

            # 2. Data Extraction using pandas
            try:
                df = pd.read_excel(file_path, sheet_name=sheet_name)
                
                output_md.append(f"### Sheet: {sheet_name}")
                
                if has_visuals:
                    output_md.append("*Note: Visual elements (images/charts) detected in this sheet.*")

                if df.empty:
                    output_md.append(f"*Note: Sheet '{sheet_name}' appears to be a visual dashboard or empty. No tabular data extracted.*")
                else:
                    # 3. Sampling (The Safety Guard)
                    if len(df) > max_rows:
                        df = df.sample(n=max_rows, random_state=seed)
                        footer = f"\n\n-- [Sheet truncated: Showing random {max_rows} rows to save context] --"
                        header = f"#### [Sample - Random {max_rows} rows]\n"
                    else:
                        footer = ""
                        header = ""
                    
                    markdown_data = df.to_markdown(index=False)
                    output_md.append(header + markdown_data)
                    if footer:
                        output_md.append(footer)
            except Exception as e:
                output_md.append(f"### Sheet: {sheet_name}")
                output_md.append(f"⚠️ Error reading sheet data: {e}")
            
            output_md.append("\n---\n")
            
        wb.close()
        return "\n".join(output_md), processed_sheets
    except Exception as e:
        return f"⚠️ Error reading Excel: {e}", 0
