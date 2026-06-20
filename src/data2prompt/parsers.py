import json
import random
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Union, Dict, Protocol, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .cli import Config

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
    DEFAULT_TABLE_TRUNCATED_SIZE,
    ENV_VALUE_PLACEHOLDER
)

@dataclass
class NotebookCellIR:
    """Intermediate representation for a Jupyter Notebook cell."""
    number: int
    type: str  # 'code' or 'markdown'
    source: str
    outputs: Optional[str] = None

@dataclass
class ColumnSchema:
    """Per-column metadata computed on the full (unsampled) DataFrame."""
    name: str
    dtype: str
    missing: int
    missing_pct: float

@dataclass
class TableSchema:
    """Structural and statistical metadata for a table, computed on the full df.

    Both the ``--schema-only`` mode and the stats-summary block read from this.
    ``describe_df`` is only populated when a statistics summary is requested.
    """
    row_count: int
    col_count: int
    columns: List[ColumnSchema]
    describe_df: Optional[pd.DataFrame] = None

@dataclass
class TableIR:
    """Intermediate representation for tabular data (CSV, Excel)."""
    name: str
    df: pd.DataFrame
    header_note: Optional[str] = None
    footer_note: Optional[str] = None
    visual_warning: bool = False
    sheet_number: Optional[int] = None
    file_path: Optional[str] = None
    schema: Optional[TableSchema] = None

@dataclass
class ParserResult:
    """Standardized output for all parsers."""
    content: Union[str, List[NotebookCellIR], List[TableIR]]
    tokens: int
    type: str
    status: str
    stats_update: Dict[str, int] = field(default_factory=dict)
    skip_file: bool = False


def build_table_schema(df: pd.DataFrame, include_describe: bool) -> TableSchema:
    """Compute column metadata for a table from its full (unsampled) DataFrame.

    Args:
        df: The complete DataFrame, before any row sampling.
        include_describe: Whether to attach a ``describe()`` summary.

    Returns:
        TableSchema: Row/column counts, per-column dtype and missing stats, and
        (optionally) a transposed ``describe()`` summary.
    """
    row_count = int(len(df))
    columns: List[ColumnSchema] = []
    for name in df.columns:
        missing = int(df[name].isna().sum())
        missing_pct = round(missing / row_count * 100, 2) if row_count else 0.0
        columns.append(ColumnSchema(
            name=str(name),
            dtype=str(df[name].dtype),
            missing=missing,
            missing_pct=missing_pct,
        ))

    describe_df: Optional[pd.DataFrame] = None
    if include_describe and not df.empty:
        try:
            describe_df = df.describe(include="all").transpose()
        except Exception:
            describe_df = None

    return TableSchema(
        row_count=row_count,
        col_count=int(df.shape[1]),
        columns=columns,
        describe_df=describe_df,
    )


def render_schema_block(
    schema: TableSchema,
    *,
    show_missing: bool,
    show_describe: bool,
) -> str:
    """Render a table's schema metadata as a Markdown snippet.

    Single source of truth used both for token estimation and by the output
    generators. ``show_missing`` adds missing count/percentage columns;
    ``show_describe`` merges describe() stats as additional columns in the
    same table rather than as a separate section.
    """
    lines: List[str] = [
        f"**Schema** — {schema.row_count:,} rows × {schema.col_count} columns",
        "",
    ]

    if show_describe and schema.describe_df is not None:
        desc = schema.describe_df
        stat_cols = list(desc.columns)

        header = ["column", "dtype"]
        if show_missing:
            header += ["missing", "missing %"]
        header += stat_cols

        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join(["---"] * len(header)) + "|")

        for col in schema.columns:
            row: List[str] = [col.name, col.dtype]
            if show_missing:
                row += [str(col.missing), str(col.missing_pct)]
            if col.name in desc.index:
                for stat in stat_cols:
                    val = desc.loc[col.name, stat]
                    row.append("" if pd.isna(val) else str(val))
            else:
                row += [""] * len(stat_cols)
            lines.append("| " + " | ".join(row) + " |")

    else:
        if show_missing:
            lines.append("| column | dtype | missing | missing % |")
            lines.append("|---|---|---|---|")
        else:
            lines.append("| column | dtype |")
            lines.append("|---|---|")

        for col in schema.columns:
            if show_missing:
                lines.append(
                    f"| {col.name} | {col.dtype} | {col.missing} | {col.missing_pct} |"
                )
            else:
                lines.append(f"| {col.name} | {col.dtype} |")

    return "\n".join(lines)


def flatten_ir(
    content: Union[str, List[NotebookCellIR], List[TableIR]],
    *,
    schema_only: bool = False,
    stats_summary: bool = False,
) -> str:
    """
    Flattens the Intermediate Representation (IR) into a string for token counting.
    This provides a rough estimate of the final output size.

    ``schema_only`` and ``stats_summary`` mirror the rendering decisions in
    ``output.py`` so the token estimate tracks the real output: the schema block is
    included when either flag is set, and data rows are dropped under ``schema_only``.
    """
    if isinstance(content, str):
        return content

    if not content:
        return ""

    if isinstance(content[0], NotebookCellIR):
        parts = []
        for cell in content:
            parts.append(cell.source)
            if cell.outputs:
                parts.append(cell.outputs)
        return "\n".join(parts)

    if isinstance(content[0], TableIR):
        parts = []
        for table in content:
            # Include sheet metadata in estimation if present
            if table.sheet_number is not None:
                parts.append(f"Sheet {table.sheet_number}: {table.name} - {table.file_path}")

            if (stats_summary or schema_only) and table.schema is not None:
                parts.append(render_schema_block(
                    table.schema,
                    show_missing=stats_summary,
                    show_describe=stats_summary,
                ))

            # Use a simple string representation for token estimation
            if table.header_note:
                parts.append(table.header_note)
            if not schema_only and not table.df.empty:
                parts.append(table.df.to_string(index=False))
            if table.footer_note:
                parts.append(table.footer_note)
        return "\n".join(parts)

    return ""

class BaseParser(Protocol):
    """Interface for all file parsers."""
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        ...

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
            processed_lines.append(f"{truncated}  -- [Line truncated: showing first {truncate_to} characters] --")
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
    table_truncate: int = DEFAULT_TABLE_TRUNCATED_SIZE,
    stats_summary: bool = True,
    schema_only: bool = False
) -> List[TableIR]:
    try:
        df = pd.read_csv(file_path, low_memory=False)

        # Column metadata is always computed on the FULL df, before sampling.
        schema = None
        if stats_summary or schema_only:
            schema = build_table_schema(df, include_describe=stats_summary)

        if schema_only:
            return [TableIR(
                name=Path(file_path).name,
                df=pd.DataFrame(),
                header_note="-- [Schema only - data rows omitted] --",
                schema=schema
            )]

        header_note = None
        footer_note = None

        if len(df) > sample_size:
            df = df.sample(sample_size, random_state=seed)
            header_note = f"-- [Sample - Random {sample_size} rows] --"
            footer_note = f"-- [CSV truncated: Showing random {sample_size} rows to save context] --"

        return [TableIR(
            name=Path(file_path).name,
            df=df,
            header_note=header_note,
            footer_note=footer_note,
            schema=schema
        )]
    except pd.errors.EmptyDataError:
        return [TableIR(name=Path(file_path).name, df=pd.DataFrame(), footer_note="-- [Note: CSV file is empty] --")]
    except Exception as e:
        return [TableIR(name=Path(file_path).name, df=pd.DataFrame(), footer_note=f"-- [Error reading CSV: {e}] --")]


def process_notebook(
    file_path: Union[str, Path],
    max_lines: int = DEFAULT_MAX_LINES,
    line_threshold: int = DEFAULT_LINE_LENGTH_THRESHOLD,
    truncate_to: int = DEFAULT_TRUNCATED_LINE_LENGTH
) -> List[NotebookCellIR]:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            nb = json.load(f)
        
        cells_ir = []
        
        for i, cell in enumerate(nb.get('cells', []), 1):
            cell_type = cell['cell_type'].lower()
            source = "".join(cell['source'])
            source = truncate_long_lines(source, line_threshold, truncate_to)
            
            cell_outputs = None
            if cell_type == 'code':
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
                                int_lines = content.strip().split('\n')
                                if len(int_lines) > max_lines:
                                    outputs.append('\n'.join(int_lines[:max_lines]) + f"\n-- [Data preview truncated: Showing first {max_lines} lines] --")
                                else:
                                    outputs.append(content.strip())
                
                if outputs:
                    cell_outputs = "\n---\n".join(outputs)
            
            cells_ir.append(NotebookCellIR(
                number=i,
                type=cell_type,
                source=source,
                outputs=cell_outputs
            ))
            
        return cells_ir
    except json.JSONDecodeError:
        return [NotebookCellIR(number=0, type="markdown", source="*Error: Malformed Jupyter Notebook (Invalid JSON).*")]
    except Exception as e:
        return [NotebookCellIR(number=0, type="markdown", source=f"Error processing notebook: {e}")]


def process_sql(
    file_path: Union[str, Path],
    sample_size: int = DEFAULT_SQL_SAMPLE_SIZE,
    max_lines: int = DEFAULT_SQL_MAX_LINES,
    seed: int = DEFAULT_SEED,
    line_threshold: int = DEFAULT_LINE_LENGTH_THRESHOLD,
    truncate_to: int = DEFAULT_TRUNCATED_LINE_LENGTH,
    table_limit: int = DEFAULT_TABLE_CHAR_LIMIT,
    table_truncate: int = DEFAULT_TABLE_TRUNCATED_SIZE,
    schema_only: bool = False
) -> str:
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()

        processed_lines = []
        table_data_buffer: List[str] = []
        in_create_block = False
        non_data_line_count: int = 0
        rng = random.Random(seed)

        def flush_buffer():
            if not table_data_buffer:
                return

            # Schema-only: drop the buffered data rows, leaving just a note.
            if schema_only:
                processed_lines.append(
                    f"-- [{len(table_data_buffer)} data row(s) omitted: schema-only] --\n"
                )
                table_data_buffer.clear()
                return

            if len(table_data_buffer) > sample_size:
                # Always keep the first line (usually the INSERT header)
                first_line = table_data_buffer[0]
                
                # Sample from the rest of the buffer, clamping to a valid range.
                n_extra = max(0, min(sample_size - 1, len(table_data_buffer) - 1))
                rest_indices = sorted(rng.sample(range(1, len(table_data_buffer)), n_extra))
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
            elif non_data_line_count < max_lines:
                flush_buffer() # Ensure data is flushed before adding more non-data lines
                processed_lines.append(line)
                non_data_line_count += 1
        
        # Final flush for the last table
        flush_buffer()
        
        return "".join(processed_lines)
    except Exception as e:
        return f"⚠️ Error reading SQL: {e}"

def process_excel(
    file_path: Union[str, Path],
    display_path: str = "",
    max_rows: int = DEFAULT_CSV_SAMPLE_SIZE,
    max_sheets: int = DEFAULT_MAX_SHEETS,
    seed: int = DEFAULT_SEED,
    table_limit: int = DEFAULT_TABLE_CHAR_LIMIT,
    table_truncate: int = DEFAULT_TABLE_TRUNCATED_SIZE,
    stats_summary: bool = True,
    schema_only: bool = False
) -> List[TableIR]:
    try:
        # 1. Sheet Discovery & Visual Element Check using openpyxl
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", UserWarning)
            wb = openpyxl.load_workbook(file_path, data_only=True, read_only=True)
        sheet_names = wb.sheetnames
        
        tables_ir = []
        processed_sheets = 0
        
        for i, sheet_name in enumerate(sheet_names, 1):
            if processed_sheets >= max_sheets:
                # Add a dummy table to represent truncation if needed,
                # or handle it in the generator. Let's add a note to the last table or a special entry.
                if tables_ir:
                    tables_ir[-1].footer_note = (tables_ir[-1].footer_note or "") + f"\n-- [Workbook truncated: Only first {max_sheets} sheets processed] --"
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
                header_note = None
                footer_note = None

                if has_visuals:
                    header_note = "-- [Note: Visual elements (images/charts) detected in this sheet] --"

                # Column metadata is always computed on the FULL sheet, before sampling.
                schema = None
                if stats_summary or schema_only:
                    schema = build_table_schema(df, include_describe=stats_summary)

                if schema_only:
                    header_note = (header_note or "") + "-- [Schema only - data rows omitted] --"
                    tables_ir.append(TableIR(
                        name=sheet_name,
                        df=pd.DataFrame(),
                        header_note=header_note,
                        visual_warning=has_visuals,
                        sheet_number=i,
                        file_path=display_path,
                        schema=schema
                    ))
                    continue

                if df.empty:
                    footer_note = f"-- [Note: Sheet '{sheet_name}' appears to be a visual dashboard or empty. No tabular data extracted] --"
                else:
                    # 3. Sampling (The Safety Guard)
                    if len(df) > max_rows:
                        df = df.sample(n=max_rows, random_state=seed)
                        footer_note = (footer_note or "") + f"-- [Sheet truncated: Showing random {max_rows} rows to save context] --"
                        header_note = (header_note or "") + f"-- [Sample - Random {max_rows} rows] --"

                tables_ir.append(TableIR(
                    name=sheet_name,
                    df=df,
                    header_note=header_note,
                    footer_note=footer_note,
                    visual_warning=has_visuals,
                    sheet_number=i,
                    file_path=display_path,
                    schema=schema
                ))

            except Exception as e:
                tables_ir.append(TableIR(
                    name=sheet_name,
                    df=pd.DataFrame(),
                    footer_note=f"-- [Error reading sheet data: {e}] --",
                    sheet_number=i,
                    file_path=display_path
                ))
            
        wb.close()
        return tables_ir
    except Exception as e:
        return [TableIR(name="Error", df=pd.DataFrame(), footer_note=f"-- [Error reading Excel: {e}] --")]

# --- Parser Implementations ---

class CSVParser:
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        from .utils import count_tokens
        content = process_csv(
            file_path,
            config.csv_sample_size,
            config.seed,
            config.table_limit,
            config.table_truncate,
            config.stats_summary,
            config.schema_only
        )
        tokens, _ = count_tokens(flatten_ir(
            content,
            schema_only=config.schema_only,
            stats_summary=config.stats_summary
        ))
        return ParserResult(
            content=content,
            tokens=tokens,
            type="CSV",
            status="Schema Only" if config.schema_only else "Sampled",
            stats_update={"csv_count": 1}
        )

class NotebookParser:
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        from .utils import count_tokens
        content = process_notebook(
            file_path,
            config.max_lines,
            config.line_length_threshold,
            config.truncated_line_length
        )
        tokens, _ = count_tokens(flatten_ir(content))
        return ParserResult(
            content=content,
            tokens=tokens,
            type="Notebook",
            status="Cleaned",
            stats_update={"notebook_count": 1}
        )

class SQLParser:
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        from .utils import count_tokens
        content = process_sql(
            file_path,
            config.sql_sample_size,
            config.sql_max_lines,
            config.seed,
            config.line_length_threshold,
            config.truncated_line_length,
            config.table_limit,
            config.table_truncate,
            config.schema_only
        )
        tokens, _ = count_tokens(content)
        return ParserResult(
            content=content,
            tokens=tokens,
            type="SQL",
            status="Schema Only" if config.schema_only else "Parsed",
            stats_update={"sql_count": 1}
        )

class ExcelParser:
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        from .utils import count_tokens
        import os
        # Get path relative to project root
        try:
            display_path = str(file_path.relative_to(Path.cwd())).replace(os.sep, '\\')
        except ValueError:
            display_path = str(file_path).replace(os.sep, '\\')
            
        content = process_excel(
            file_path,
            display_path,
            config.csv_sample_size,
            config.max_sheets,
            config.seed,
            config.table_limit,
            config.table_truncate,
            config.stats_summary,
            config.schema_only
        )
        sheet_count = len(content)
        tokens, _ = count_tokens(flatten_ir(
            content,
            schema_only=config.schema_only,
            stats_summary=config.stats_summary
        ))
        return ParserResult(
            content=content,
            tokens=tokens,
            type=f"Excel ({sheet_count} sheets)",
            status="Schema Only" if config.schema_only else "Extracted",
            stats_update={"excel_count": 1, "excel_sheets_count": sheet_count}
        )

class DefaultParser:
    """Fallback parser for text files."""
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        from .utils import count_tokens, is_binary
        from .constants import GENERATION_FLAG
        
        ext = file_path.suffix.lower()
        
        # Check for generation flag in all text files
        if not is_binary(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    if GENERATION_FLAG in f.read(100):
                        return ParserResult(content="", tokens=0, type="Skipped", status="Skipped (Generated)", skip_file=True)
            except:
                pass

        if is_binary(file_path):
            return ParserResult(
                content=f"*Note: Binary content detected in {ext if ext else 'unknown'} file. Content skipped.*",
                tokens=0,
                type=f"Binary ({ext})",
                status="Skipped (Binary)",
                stats_update={"binary_count": 1}
            )
        
        file_size_kb = file_path.stat().st_size / 1024
        try:
            if file_size_kb > config.max_file_size:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    header_content = f.read(10 * 1024)
                    content = header_content + f"\n-- [File truncated: Showing first 10KB because it exceeds the size limit ({config.max_file_size}KB) to save context] --\n"
                    tokens, _ = count_tokens(content)
                    return ParserResult(
                        content=content,
                        tokens=tokens,
                        type=ext[1:] if ext else "text",
                        status="Truncated",
                        stats_update={"truncated_count": 1}
                    )
            else:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    content = truncate_long_lines(content, config.line_length_threshold, config.truncated_line_length)
                    tokens, _ = count_tokens(content)
                    return ParserResult(
                        content=content,
                        tokens=tokens,
                        type=ext[1:] if ext else "text",
                        status="Read"
                    )
        except Exception:
            return ParserResult(content="*Could not read file.*", tokens=0, type="Error", status="Error")


def is_env_file(name: str) -> bool:
    """Return True if a filename denotes an environment-variable file.

    Matches ``.env``, dotted variants like ``.env.local`` / ``.env.production``,
    and suffixed variants like ``prod.env``. Intentionally excludes ``.envrc``.
    """
    return name == ".env" or name.startswith(".env.") or name.endswith(".env")


def process_env(
    file_path: Union[str, Path],
    placeholder: str = ENV_VALUE_PLACEHOLDER,
) -> str:
    """Extract variable names from a .env file, redacting every value.

    Comments and blank lines are dropped, and an ``export`` prefix is stripped.
    Only lines of the form ``KEY=...`` with an identifier-like key are emitted, as
    ``KEY=<placeholder>``. No value from the file is ever included in the output.
    """
    lines = ["# Environment variables (names only, values redacted)"]
    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue
                if line.lower().startswith("export "):
                    line = line[len("export "):].strip()
                if "=" not in line:
                    continue
                key = line.split("=", 1)[0].strip()
                if key.isidentifier():
                    lines.append(f"{key}={placeholder}")
    except Exception as e:
        lines.append(f"-- [Error reading .env file: {e}] --")
    return "\n".join(lines)


class EnvParser:
    """Parser for environment files: lists variable names with redacted values."""
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        from .utils import count_tokens

        if not config.env_keys:
            return ParserResult(
                content="*Note: .env file content skipped (--no-env-keys).*\n",
                tokens=0,
                type="Env",
                status="Skipped (Env)",
                stats_update={"env_count": 1}
            )

        content = process_env(file_path)
        tokens, _ = count_tokens(content)
        return ParserResult(
            content=content,
            tokens=tokens,
            type="Env",
            status="Redacted",
            stats_update={"env_count": 1}
        )


class ParserRegistry:
    """Handles file-to-parser mapping."""
    def __init__(self):
        self._parsers: Dict[str, BaseParser] = {}
        self._default_parser = DefaultParser()

    def register(self, extensions: List[str], parser: BaseParser):
        for ext in extensions:
            self._parsers[ext.lower()] = parser

    def get_parser(self, extension: str) -> BaseParser:
        return self._parsers.get(extension.lower(), self._default_parser)

# Global registry instance
registry = ParserRegistry()
registry.register(['.csv'], CSVParser())
registry.register(['.ipynb'], NotebookParser())
registry.register(['.sql'], SQLParser())
registry.register(['.xlsx', '.xls'], ExcelParser())

# Env files are dispatched by name (not extension) in main.process_target_file,
# because a bare '.env' has no suffix. This shared instance handles all variants.
env_parser = EnvParser()
