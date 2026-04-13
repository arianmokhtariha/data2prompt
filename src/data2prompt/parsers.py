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
    DEFAULT_SEED,
    DEFAULT_LINE_LENGTH_THRESHOLD,
    DEFAULT_TRUNCATED_LINE_LENGTH,
    DEFAULT_TABLE_CHAR_LIMIT,
    DEFAULT_TABLE_TRUNCATED_SIZE
)

def enforce_table_limit(text: str, limit: int, truncate_to: int) -> str:
    """
    Checks if a table's string representation exceeds a character limit.
    If it does, truncates it and appends a warning.

    Args:
        text: The table string (markdown or SQL).
        limit: Max characters allowed.
        truncate_to: Characters to keep if limit is exceeded.

    Returns:
        str: The potentially truncated string.
    """
    if len(text) <= limit:
        return text

    truncated = text[:truncate_to]
    warning = f"\n\n-- [Table truncated: Total size exceeded {limit} characters. Showing first {truncate_to} characters to save context] --"
    return truncated + warning


def truncate_long_lines(text: str, threshold: int, truncate_to: int) -> str:
    """
    Truncates lines in a text string that exceed a certain character threshold.
    
    Args:
        text: The input text to process.
        threshold: The maximum allowed length for a single line.
        truncate_to: The length to truncate long lines to.
        
    Returns:
        str: The processed text with long lines truncated and flagged.
    """
    if not text:
        return text
        
    lines = text.splitlines()
    processed_lines = []
    for line in lines:
        if len(line) > threshold:
            truncated = line[:truncate_to]
            processed_lines.append(f"{truncated} ... -- [Line truncated: showing first {truncate_to} characters] --")
        else:
            processed_lines.append(line)
    
    # Preserve trailing newline if it existed
    result = "\n".join(processed_lines)
    if text.endswith("\n") and not result.endswith("\n"):
        result += "\n"
    return result


def process_csv(
    file_path: Union[str, Path],
    sample_size: int = DEFAULT_CSV_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    table_limit: int = DEFAULT_TABLE_CHAR_LIMIT,
    table_truncate: int = DEFAULT_TABLE_TRUNCATED_SIZE
) -> str:
    try:
        df = pd.read_csv(file_path, low_memory=False)
        if len(df) > sample_size:
            df = df.sample(sample_size, random_state=seed)
            footer = f"\n\n-- [CSV truncated: Showing random {sample_size} rows to save context] --"
        else:
            footer = ""
        
        markdown_content = (
            f"#### [Sample - Random {sample_size} rows]\n"
            + df.to_markdown(index=False)
            + footer
        )
        
        return enforce_table_limit(markdown_content, table_limit, table_truncate)
    except pd.errors.EmptyDataError:
        return "*Note: CSV file is empty.*"
    except Exception as e:
        return f"Error reading CSV: {e}"


def process_notebook(
    file_path: Union[str, Path],
    max_lines: int = DEFAULT_MAX_LINES,
    line_threshold: int = DEFAULT_LINE_LENGTH_THRESHOLD,
    truncate_to: int = DEFAULT_TRUNCATED_LINE_LENGTH
) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        output_md = []
        
        # Added enumeration to track cell numbers
        for i, cell in enumerate(nb.get('cells', []), 1):
            cell_type = cell['cell_type'].lower()
            output_md.append(f'<notebook_cell index="{i}" type="{cell_type}">')
            
            if cell['cell_type'] == 'markdown':
                content = "".join(cell['source'])
                content = truncate_long_lines(content, line_threshold, truncate_to)
                output_md.append("<cell_markdown>")
                output_md.append(content)
                output_md.append("</cell_markdown>")
            
            elif cell['cell_type'] == 'code':
                code = "".join(cell['source'])
                code = truncate_long_lines(code, line_threshold, truncate_to)
                output_md.append("<cell_code>")
                output_md.append(code)
                output_md.append("</cell_code>")
                
                outputs = []
                for out in cell.get('outputs', []):
                    if out.get('output_type') == 'stream':
                        text = "".join(out.get('text', []))
                        text = truncate_long_lines(text, line_threshold, truncate_to)
                        lines = text.strip().split('\n')
                        if len(lines) > max_lines:
                            outputs.append('\n'.join(lines[:max_lines]) + f"\n-- [Output truncated: Showing first {max_lines} lines] --")
                        else:
                            outputs.append(text.strip())
                    
                    elif out.get('output_type') in ['execute_result', 'display_data']:
                        data = out.get('data', {})
                        if 'text/plain' in data:
                            content = "".join(data['text/plain'])
                            if "base64" not in content:
                                content = truncate_long_lines(content, line_threshold, truncate_to)
                                lines = content.strip().split('\n')
                                if len(lines) > max_lines:
                                    outputs.append('\n'.join(lines[:max_lines]) + f"\n-- [Data preview truncated: Showing first {max_lines} lines] --")
                                else:
                                    outputs.append(content.strip())
                
                if outputs:
                    output_md.append("<cell_output>")
                    output_md.append("\n---\n".join(outputs))
                    output_md.append("</cell_output>")
                                
            output_md.append(f"</notebook_cell>")
            
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
    line_threshold: int = DEFAULT_LINE_LENGTH_THRESHOLD,
    truncate_to: int = DEFAULT_TRUNCATED_LINE_LENGTH,
    table_limit: int = DEFAULT_TABLE_CHAR_LIMIT,
    table_truncate: int = DEFAULT_TABLE_TRUNCATED_SIZE
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
                # Always keep the first line (usually the INSERT header)
                first_line = table_data_buffer[0]
                
                # Sample from the rest of the buffer
                # We need sample_size - 1 more rows
                rest_indices = sorted(rng.sample(range(1, len(table_data_buffer)), sample_size - 1))
                sampled_rows = [first_line] + [table_data_buffer[idx] for idx in rest_indices]
                sampled_text = "".join(sampled_rows)
                
                # Apply secondary truncation if the sampled block is still too large
                sampled_text = enforce_table_limit(sampled_text, table_limit, table_truncate)
                
                processed_lines.append(sampled_text)
                if not sampled_text.endswith("\n"):
                    processed_lines.append("\n")
                processed_lines.append(f"-- [Table data truncated: Showing random {sample_size} rows to save context] --\n")
            else:
                data_text = "".join(table_data_buffer)
                data_text = enforce_table_limit(data_text, table_limit, table_truncate)
                processed_lines.append(data_text)
                if not data_text.endswith("\n"):
                    processed_lines.append("\n")
            table_data_buffer.clear()

        for line in lines:
            # Apply line-level truncation using the modular helper
            line = truncate_long_lines(line, line_threshold, truncate_to)
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
        
        return "".join(processed_lines)
    except Exception as e:
        return f"⚠️ Error reading SQL: {e}"

def process_excel(
    file_path: Union[str, Path],
    max_rows: int = DEFAULT_CSV_SAMPLE_SIZE,
    max_sheets: int = DEFAULT_MAX_SHEETS,
    seed: int = DEFAULT_SEED,
    table_limit: int = DEFAULT_TABLE_CHAR_LIMIT,
    table_truncate: int = DEFAULT_TABLE_TRUNCATED_SIZE
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
                    sheet_content = header + markdown_data + footer
                    output_md.append(enforce_table_limit(sheet_content, table_limit, table_truncate))
            except Exception as e:
                output_md.append(f"### Sheet: {sheet_name}")
                output_md.append(f"⚠️ Error reading sheet data: {e}")
            
            output_md.append("\n---\n")
            
        wb.close()
        return "\n".join(output_md), processed_sheets
    except Exception as e:
        return f"⚠️ Error reading Excel: {e}", 0
