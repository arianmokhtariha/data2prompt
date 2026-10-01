import json
import random
import sqlite3
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import (
    List, Union, Dict, Protocol, Optional, Sequence, Set, TypedDict, TYPE_CHECKING
)

if TYPE_CHECKING:
    from data2prompt.cli import Config

import pandas as pd

from data2prompt.constants import (
    DEFAULT_CSV_SAMPLE_SIZE,
    DEFAULT_SQL_SAMPLE_SIZE,
    DEFAULT_SQL_MAX_LINES,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_SHEETS,
    DEFAULT_MAX_TABLES,
    DEFAULT_DB_FULL_SCAN_MAX_ROWS,
    DEFAULT_DB_COUNT_MAX_BYTES,
    DEFAULT_SEED,
    DEFAULT_LINE_LENGTH_THRESHOLD,
    DEFAULT_TRUNCATED_LINE_LENGTH,
    DEFAULT_TABLE_CHAR_LIMIT,
    DEFAULT_TABLE_TRUNCATED_SIZE,
    ENV_VALUE_PLACEHOLDER,
    GENERATION_FLAG,
    TABLE_CELL_NEWLINE_MARKER,
)
from data2prompt.utils import count_tokens, is_binary

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
    """Intermediate representation for tabular data (CSV, Excel, SQLite)."""
    name: str
    df: pd.DataFrame
    header_note: Optional[str] = None
    footer_note: Optional[str] = None
    sheet_number: Optional[int] = None
    file_path: Optional[str] = None
    schema: Optional[TableSchema] = None
    # Word used for the sub-section heading when ``sheet_number`` is set
    # ("Sheet" for Excel, "Table" for SQLite). Also drives the XML element tag.
    section_label: str = "Sheet"
    # Raw CREATE-statement DDL (SQLite); rendered like the schema block.
    ddl: Optional[str] = None

# The three shapes a parser can emit: raw text, notebook cells, or tables.
ParserContent = Union[str, List[NotebookCellIR], List[TableIR]]

@dataclass
class ParserResult:
    """Standardized output for all parsers."""
    content: ParserContent
    tokens: int
    type: str
    status: str
    stats_update: Dict[str, int] = field(default_factory=dict)
    skip_file: bool = False


class FileData(TypedDict):
    """A processed file handed from the orchestrator to an output generator."""
    path: str
    content: ParserContent
    type: str
    tokens: int
    status: str


class FileSummary(TypedDict):
    """A processed file's row in the final summary table rendered by the UI."""
    name: str
    type: str
    tokens: int
    status: str


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
    # Positional access (.iloc), not df[name]: pandas allows duplicate column
    # labels (most commonly reached via a pyarrow Table with duplicate field
    # names converted with .to_pandas(), which pandas' own CSV/Excel readers
    # would otherwise have auto-deduplicated). df[name] on a duplicate label
    # returns a DataFrame instead of a Series, and int(<Series>.sum()) raises.
    for i, name in enumerate(df.columns):
        series = df.iloc[:, i]
        missing = int(series.isna().sum())
        missing_pct = round(missing / row_count * 100, 2) if row_count else 0.0
        columns.append(ColumnSchema(
            name=str(name),
            dtype=str(series.dtype),
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


def _escape_table_cell(text: str) -> str:
    """Make ``text`` safe for one Markdown table cell.

    Line breaks become ``TABLE_CELL_NEWLINE_MARKER`` so the value stays on its
    row, and ``|`` is escaped so it cannot open a fake column.
    """
    single_line = text.replace("\r\n", "\n").replace("\r", "\n")
    single_line = single_line.replace("\n", TABLE_CELL_NEWLINE_MARKER)
    return single_line.replace("|", "\\|")


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

        # Positional pairing with desc's rows (not desc.loc[col.name]):
        # describe() preserves column order even for duplicate-named
        # columns, where a name-based lookup would be ambiguous — pandas
        # returns every matching row instead of the one that lines up with
        # this column, and pd.isna() on that multi-row result raises.
        for i, col in enumerate(schema.columns):
            row: List[str] = [_escape_table_cell(col.name), col.dtype]
            if show_missing:
                row += [str(col.missing), str(col.missing_pct)]
            if i < len(desc.index):
                stats_row = desc.iloc[i]
                for stat in stat_cols:
                    val = stats_row[stat]
                    row.append(_format_cell(val))
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
            name = _escape_table_cell(col.name)
            if show_missing:
                lines.append(
                    f"| {name} | {col.dtype} | {col.missing} | {col.missing_pct} |"
                )
            else:
                lines.append(f"| {name} | {col.dtype} |")

    return "\n".join(lines)


# A rendered sample table opens with a header row and a separator row.
_SAMPLE_TABLE_HEADER_LINES = 2


def _format_cell(value: object) -> str:
    """Render one table cell faithfully; only a missing value is left empty.

    ``str()`` gives a float's shortest round-trip form, so values are never
    rounded. An empty or whitespace-only string is quoted (``""``, ``"  "``)
    so it cannot be mistaken for a missing value.
    """
    if pd.api.types.is_scalar(value) and pd.isna(value):
        return ""
    text = str(value)
    if not text.strip():
        return f'"{_escape_table_cell(text)}"'
    return _escape_table_cell(text)


def _join_row(cells: Sequence[str]) -> str:
    """Join cells into one Markdown table row; an empty cell is a single space."""
    return "|" + "|".join(f" {cell} " if cell else " " for cell in cells) + "|"


def render_sample_table(df: pd.DataFrame) -> str:
    """Render sample rows as a compact Markdown table, one line per row.

    No alignment padding: it costs tokens and tells a model nothing. Cell
    conventions (empty = missing, quoted blanks, the newline marker) are
    taught in the tabular preamble bullet.
    """
    header = [_escape_table_cell(str(name)) for name in df.columns]
    lines = [
        _join_row(header),
        "|" + "|".join(["---"] * len(header)) + "|",
    ]
    # Iterate each column's own array, not itertuples(): itertuples widens
    # float32 to a Python float, so 0.1 would print as 0.10000000149011612.
    # Positional access keeps duplicate column labels apart.
    columns = [df.iloc[:, i].array for i in range(df.shape[1])]
    for row in zip(*columns):
        lines.append(_join_row([_format_cell(value) for value in row]))
    return "\n".join(lines)


def render_table_text(
    table: TableIR,
    *,
    include_rows: bool,
    table_limit: Optional[int] = None,
    table_truncate: Optional[int] = None,
) -> str:
    """Render a table's notes and sample rows: header note, rows, footer note.

    Single source of truth used both for token estimation (``flatten_ir``)
    and by the output generators. ``include_rows`` is False under
    ``--schema-only``. When ``table_limit`` and ``table_truncate`` are given,
    the character cap applies to the sample rows alone and cuts at a row
    boundary, so neither note can be cut off.
    """
    parts: List[str] = []
    if table.header_note:
        parts.append(table.header_note)
    if include_rows and not table.df.empty:
        rows_text = render_sample_table(table.df)
        if table_limit is not None and table_truncate is not None:
            rows_text = enforce_table_limit(
                rows_text,
                table_limit,
                table_truncate,
                header_lines=_SAMPLE_TABLE_HEADER_LINES,
            )
        parts.append(rows_text)
    if table.footer_note:
        parts.append(table.footer_note)
    return "\n".join(parts)


def flatten_ir(
    content: ParserContent,
    *,
    schema_only: bool = False,
    stats_summary: bool = False,
    table_limit: Optional[int] = None,
    table_truncate: Optional[int] = None,
) -> str:
    """
    Flattens the Intermediate Representation (IR) into a string for token counting.
    This provides a rough estimate of the final output size.

    ``schema_only`` and ``stats_summary`` mirror the rendering decisions in
    ``output.py`` so the token estimate tracks the real output: the schema block is
    included when either flag is set, and data rows are dropped under ``schema_only``.
    ``table_limit``/``table_truncate`` apply the same sample-row cap as the
    generators, so the estimate counts the text the document carries.
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
            # Include sub-section metadata in estimation if present
            if table.sheet_number is not None:
                parts.append(
                    f"{table.section_label} {table.sheet_number}: "
                    f"{table.name} - {table.file_path}"
                )

            # DDL (SQLite CREATE statements) is gated like the schema block.
            if (stats_summary or schema_only) and table.ddl:
                parts.append(table.ddl)

            if (stats_summary or schema_only) and table.schema is not None:
                parts.append(render_schema_block(
                    table.schema,
                    show_missing=stats_summary,
                    show_describe=stats_summary,
                ))

            # The same notes + rows text the generators emit.
            table_text = render_table_text(
                table,
                include_rows=not schema_only,
                table_limit=table_limit,
                table_truncate=table_truncate,
            )
            if table_text:
                parts.append(table_text)
        return "\n".join(parts)

    return ""

class BaseParser(Protocol):
    """Interface for all file parsers."""
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        ...

def enforce_table_limit(
    text: str,
    limit: int,
    truncate_to: int,
    *,
    header_lines: int = 0,
    noun: str = "row",
) -> str:
    """Cap an oversized block of table rows at the last row that fits.

    Rows are lines (Markdown table rows, or raw SQL data lines), so no row is
    ever cut in half. When ``text`` exceeds ``limit`` characters, the first
    ``header_lines`` lines (a Markdown header and separator) are always kept,
    then whole rows while the kept text stays within ``truncate_to``
    characters, then a notice citing kept and total rows. Nothing cut means
    no notice. ``noun`` names what the lines are (``"line"`` for raw SQL,
    whose lines include non-row text such as an ``INSERT`` header).
    """
    if len(text) <= limit:
        return text

    lines = text.rstrip("\n").split("\n")
    header, rows = lines[:header_lines], lines[header_lines:]
    kept_length = len("\n".join(header))
    kept_count = 0
    for row in rows:
        kept_length += len(row) + 1  # +1 for the joining newline
        if kept_length > truncate_to:
            break
        kept_count += 1

    if kept_count == len(rows):
        return text

    plural = noun if len(rows) == 1 else f"{noun}s"
    notice = (
        f"-- [Table truncated: showing first {kept_count:,} of "
        f"{len(rows):,} {plural}; the table exceeded {limit:,} characters] --"
    )
    return "\n".join(header + rows[:kept_count] + [notice])


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


def _sanitize_error(e: Exception, file_path: Path) -> str:
    """Replace the absolute file path in an error message with a cwd-relative path."""
    err_str = str(e)
    abs_str = str(file_path).replace("\\", "/")
    try:
        rel_str = str(file_path.relative_to(Path.cwd())).replace("\\", "/")
    except ValueError:
        rel_str = file_path.name
    return err_str.replace(str(file_path), rel_str).replace(abs_str, rel_str)


def process_csv(
    file_path: Union[str, Path],
    sample_size: int = DEFAULT_CSV_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    stats_summary: bool = True,
    schema_only: bool = False
) -> List[TableIR]:
    try:
        # round_trip: the default C float parser is off by 1 ulp on many
        # values, which would show digits that are not in the source file.
        df = pd.read_csv(file_path, low_memory=False, float_precision="round_trip")

        # Column metadata is always computed on the FULL df, before sampling.
        schema = None
        if stats_summary or schema_only:
            schema = build_table_schema(df, include_describe=stats_summary)

        if schema_only:
            return [TableIR(
                name=Path(file_path).name,
                df=pd.DataFrame(),
                header_note="-- [Schema only: data rows omitted] --",
                schema=schema
            )]

        header_note = None
        total_rows = len(df)

        if total_rows > sample_size:
            # sort_index restores file order so the sample reads naturally.
            df = df.sample(sample_size, random_state=seed).sort_index()
            header_note = f"-- [Sample: random {sample_size} of {total_rows:,} rows] --"

        return [TableIR(
            name=Path(file_path).name,
            df=df,
            header_note=header_note,
            schema=schema
        )]
    except pd.errors.EmptyDataError:
        return [TableIR(name=Path(file_path).name, df=pd.DataFrame(), footer_note="-- [Note: CSV file is empty] --")]
    except Exception as e:
        fp = Path(file_path)
        return [TableIR(name=fp.name, df=pd.DataFrame(), footer_note=f"-- [Error reading CSV: {_sanitize_error(e, fp)}] --")]


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
            cell_type = cell.get('cell_type', 'code').lower()
            source = "".join(cell.get('source', []) or [])
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

                    elif out.get('output_type') == 'error':
                        tb_text = "\n".join(out.get('traceback', []))
                        tb_text = truncate_long_lines(tb_text, line_threshold, truncate_to)
                        tb_lines = tb_text.strip().split('\n')
                        if len(tb_lines) > max_lines:
                            outputs.append("-- [Error output] --\n" + '\n'.join(tb_lines[:max_lines]) + f"\n-- [Output truncated: Showing first {max_lines} lines] --")
                        else:
                            outputs.append("-- [Error output] --\n" + tb_text.strip())

                if outputs:
                    cell_outputs = "\n---\n".join(outputs)
            
            cells_ir.append(NotebookCellIR(
                number=i,
                type=cell_type,
                source=source,
                outputs=cell_outputs
            ))

        if not cells_ir:
            # A valid but genuinely empty notebook ("cells": []) must not
            # return an empty list: output.py's NotebookCellIR branch
            # requires a non-empty list, and an empty one would silently
            # fall through to rendering the bare Python repr "[]".
            return [NotebookCellIR(
                number=0,
                type="markdown",
                source="-- [Note: notebook contains no cells] --",
            )]

        return cells_ir
    except json.JSONDecodeError:
        return [NotebookCellIR(
            number=0,
            type="markdown",
            source="-- [Error: Malformed Jupyter Notebook (Invalid JSON)] --",
        )]
    except Exception as e:
        return [NotebookCellIR(
            number=0,
            type="markdown",
            source=(
                "-- [Error processing notebook: "
                f"{_sanitize_error(e, Path(file_path))}] --"
            ),
        )]


def _is_bare_insert_header(line: str) -> bool:
    """Whether a buffered SQL line is an ``INSERT ... VALUES`` header with no row."""
    return line.strip().upper().endswith("VALUES")


def _data_row_indices(buffer: List[str]) -> List[int]:
    """Return the indices of buffered SQL lines that hold data rows.

    A bare ``INSERT ... VALUES`` header is statement structure, not a row;
    every other buffered line (including a one-row ``INSERT``) is a row.
    """
    return [
        index for index, line in enumerate(buffer)
        if not _is_bare_insert_header(line)
    ]


def _choose_lines_to_keep(
    buffer: List[str],
    row_indices: List[int],
    sample_size: int,
    rng: random.Random,
) -> Set[int]:
    """Pick the buffer lines to show when there are more rows than the sample.

    Keeps every bare header and line 0 (so the statement keeps its opener),
    then fills up to ``sample_size`` shown rows with a seeded random sample.
    """
    keep = {
        index for index, line in enumerate(buffer)
        if _is_bare_insert_header(line)
    }
    keep.add(0)

    shown_rows = 1 if 0 in row_indices else 0
    candidates = [index for index in row_indices if index != 0]
    slots = max(0, min(sample_size - shown_rows, len(candidates)))
    keep.update(rng.sample(candidates, slots))
    return keep


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
        omitted_non_data_count: int = 0
        rng = random.Random(seed)

        def flush_buffer() -> None:
            if not table_data_buffer:
                return

            row_indices = _data_row_indices(table_data_buffer)

            # Schema-only: drop the buffered data rows, leaving just a note.
            if schema_only:
                processed_lines.append(
                    f"-- [{len(row_indices)} data row(s) omitted: schema-only] --\n"
                )
                table_data_buffer.clear()
                return

            if len(row_indices) > sample_size:
                keep = _choose_lines_to_keep(
                    table_data_buffer, row_indices, sample_size, rng
                )
                sampled_text = "".join(
                    line for index, line in enumerate(table_data_buffer)
                    if index in keep
                )

                # Apply secondary truncation if the sampled block is still too large
                sampled_text = enforce_table_limit(
                    sampled_text, table_limit, table_truncate, noun="line"
                )

                processed_lines.append(sampled_text)
                if not sampled_text.endswith("\n"):
                    processed_lines.append("\n")
                shown_rows = len(keep.intersection(row_indices))
                processed_lines.append(
                    f"-- [Table data truncated: Showing random {shown_rows:,} of "
                    f"{len(row_indices):,} rows to save context] --\n"
                )
            else:
                data_text = "".join(table_data_buffer)
                data_text = enforce_table_limit(
                    data_text, table_limit, table_truncate, noun="line"
                )
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
            elif line_stripped:
                # Over the cap: count dropped (non-blank) lines so the reader
                # is told content was omitted instead of it vanishing silently.
                omitted_non_data_count += 1

        # Final flush for the last table
        flush_buffer()

        if omitted_non_data_count:
            processed_lines.append(
                f"\n-- [{omitted_non_data_count} non-data line(s) omitted: "
                f"exceeded the {max_lines}-line limit (--sql-max-lines)] --\n"
            )

        return "".join(processed_lines)
    except Exception as e:
        return f"-- [Error reading SQL: {_sanitize_error(e, Path(file_path))}] --"

def _xlsx_has_visuals(file_path: Union[str, Path]) -> bool:
    """Cheaply detect embedded images/charts in an .xlsx/.xlsm workbook.

    Both extensions are the same OOXML zip container; images live under
    ``xl/media/`` and charts under ``xl/charts/``. Inspecting the archive
    listing avoids loading the workbook and works where openpyxl's read-only
    mode never parses drawings.
    """
    try:
        with zipfile.ZipFile(file_path) as archive:
            return any(
                name.startswith(("xl/media/", "xl/charts/"))
                for name in archive.namelist()
            )
    except (zipfile.BadZipFile, OSError):
        return False


def process_excel(
    file_path: Union[str, Path],
    display_path: str = "",
    max_rows: int = DEFAULT_CSV_SAMPLE_SIZE,
    max_sheets: int = DEFAULT_MAX_SHEETS,
    seed: int = DEFAULT_SEED,
    stats_summary: bool = True,
    schema_only: bool = False
) -> List[TableIR]:
    fp = Path(file_path)
    ext = fp.suffix.lower()
    has_visuals = ext in (".xlsx", ".xlsm") and _xlsx_has_visuals(file_path)

    # A single pd.ExcelFile parses the workbook once for all sheets (the old
    # per-sheet pd.read_excel re-opened the file for every sheet) and its
    # context manager guarantees the handle is released even on error paths.
    try:
        excel_file = pd.ExcelFile(file_path)
    except ImportError:
        # pandas imports the format's engine lazily; legacy .xls needs xlrd.
        return [TableIR(
            name=fp.name,
            df=pd.DataFrame(),
            footer_note=(
                f"-- [Skipped: reading legacy {ext} files requires the "
                "optional 'xlrd' package (pip install xlrd)] --"
            ),
        )]
    except Exception as e:
        return [TableIR(
            name=fp.name,
            df=pd.DataFrame(),
            footer_note=f"-- [Error reading Excel: {_sanitize_error(e, fp)}] --",
        )]

    tables_ir: List[TableIR] = []
    with excel_file:
        for i, sheet_name in enumerate(excel_file.sheet_names, 1):
            if i > max_sheets:
                if tables_ir:
                    tables_ir[-1].footer_note = (
                        (tables_ir[-1].footer_note or "")
                        + f"\n-- [Workbook truncated: Only first {max_sheets} sheets processed] --"
                    )
                else:
                    # max_sheets == 0: no TableIR exists yet to attach the
                    # note to. Emit a standalone placeholder instead of
                    # returning an empty list — output.py's TableIR branch
                    # requires a non-empty content list, and an empty one
                    # would silently fall through to rendering `str([])`.
                    tables_ir.append(TableIR(
                        name=fp.name,
                        df=pd.DataFrame(),
                        footer_note=(
                            f"-- [Workbook truncated: Only first {max_sheets} "
                            "sheets processed] --"
                        ),
                    ))
                break

            try:
                df = excel_file.parse(sheet_name)
                # Each header notice is its own line, joined below.
                header_notes: List[str] = []
                footer_note = None

                # Drawings are stored at workbook level in the archive, so the
                # note is emitted once, on the first sheet.
                if has_visuals and i == 1:
                    header_notes.append(
                        "-- [Note: Workbook contains visual elements "
                        "(images/charts); they are not extracted] --"
                    )

                # Column metadata is always computed on the FULL sheet, before sampling.
                schema = None
                if stats_summary or schema_only:
                    schema = build_table_schema(df, include_describe=stats_summary)

                if schema_only:
                    header_notes.append("-- [Schema only: data rows omitted] --")
                    tables_ir.append(TableIR(
                        name=str(sheet_name),
                        df=pd.DataFrame(),
                        header_note="\n".join(header_notes),
                        sheet_number=i,
                        file_path=display_path,
                        schema=schema
                    ))
                    continue

                if df.empty:
                    footer_note = f"-- [Note: Sheet '{sheet_name}' appears to be a visual dashboard or empty. No tabular data extracted] --"
                else:
                    # Sampling (The Safety Guard); sort_index restores sheet order.
                    total_rows = len(df)
                    if total_rows > max_rows:
                        df = df.sample(n=max_rows, random_state=seed).sort_index()
                        header_notes.append(
                            f"-- [Sample: random {max_rows} of {total_rows:,} rows] --"
                        )

                tables_ir.append(TableIR(
                    name=str(sheet_name),
                    df=df,
                    header_note="\n".join(header_notes) or None,
                    footer_note=footer_note,
                    sheet_number=i,
                    file_path=display_path,
                    schema=schema
                ))

            except Exception as e:
                tables_ir.append(TableIR(
                    name=str(sheet_name),
                    df=pd.DataFrame(),
                    footer_note=f"-- [Error reading sheet data: {_sanitize_error(e, fp)}] --",
                    sheet_number=i,
                    file_path=display_path
                ))

    return tables_ir

# --- Parser Implementations ---

class CSVParser:
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        content = process_csv(
            file_path,
            config.csv_sample_size,
            config.seed,
            config.stats_summary,
            config.schema_only
        )
        tokens, _ = count_tokens(flatten_ir(
            content,
            schema_only=config.schema_only,
            stats_summary=config.stats_summary,
            table_limit=config.table_limit,
            table_truncate=config.table_truncate,
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
        # Project-relative path with forward slashes — must match the File
        # Index / file-header path keys emitted by the output generators.
        try:
            display_path = file_path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            display_path = file_path.as_posix()

        content = process_excel(
            file_path,
            display_path,
            config.csv_sample_size,
            config.max_sheets,
            config.seed,
            config.stats_summary,
            config.schema_only
        )
        sheet_count = len(content)
        tokens, _ = count_tokens(flatten_ir(
            content,
            schema_only=config.schema_only,
            stats_summary=config.stats_summary,
            table_limit=config.table_limit,
            table_truncate=config.table_truncate,
        ))
        return ParserResult(
            content=content,
            tokens=tokens,
            type=f"Excel ({sheet_count} sheets)",
            status="Schema Only" if config.schema_only else "Extracted",
            stats_update={"excel_count": 1, "excel_sheets_count": sheet_count}
        )

def process_arrow_file(
    file_path: Union[str, Path],
    ext: str,
    sample_size: int = DEFAULT_CSV_SAMPLE_SIZE,
    seed: int = DEFAULT_SEED,
    stats_summary: bool = True,
    schema_only: bool = False,
) -> List[TableIR]:
    """Read a .parquet, .feather, or .arrow file and return a sampled TableIR list.

    Uses the file's native pyarrow schema for exact dtype names rather than
    pandas-inferred types. Callers must confirm pyarrow is importable first.
    """
    try:
        import pyarrow as pa
        import pyarrow.feather as pf
        import pyarrow.parquet as pq

        fp = Path(file_path)
        if ext == ".parquet":
            table = pq.read_table(fp)
        elif ext == ".feather":
            table = pf.read_table(fp)
        else:  # .arrow — IPC file format; fall back to stream format
            try:
                table = pa.ipc.open_file(fp).read_all()
            except Exception:
                table = pa.ipc.open_stream(fp).read_all()

        # Exact pyarrow dtype strings, e.g. "int64", "utf8", "timestamp[us, tz=UTC]".
        # Positional, not name-keyed: unlike a pandas DataFrame, an Arrow
        # schema permits duplicate field names, and a name-keyed dict would
        # silently collapse two same-named columns onto one dtype string.
        dtype_by_position: List[str] = [str(f.type) for f in table.schema]

        df = table.to_pandas()

        schema = None
        if stats_summary or schema_only:
            schema = build_table_schema(df, include_describe=stats_summary)
            # Replace pandas-inferred dtypes with the native pyarrow types
            for i, col in enumerate(schema.columns):
                if i < len(dtype_by_position):
                    col.dtype = dtype_by_position[i]

        if schema_only:
            return [TableIR(
                name=fp.name,
                df=pd.DataFrame(),
                header_note="-- [Schema only: data rows omitted] --",
                schema=schema,
            )]

        header_note = None
        total_rows = len(df)

        if total_rows > sample_size:
            # sort_index restores file order so the sample reads naturally.
            df = df.sample(sample_size, random_state=seed).sort_index()
            header_note = f"-- [Sample: random {sample_size} of {total_rows:,} rows] --"

        return [TableIR(
            name=fp.name,
            df=df,
            header_note=header_note,
            schema=schema,
        )]

    except Exception as e:
        fp = Path(file_path)
        cleaned = _sanitize_error(e, fp).rsplit(": ", 1)[-1].strip()
        return [TableIR(
            name=fp.name,
            df=pd.DataFrame(),
            footer_note=f"-- [Error reading {ext[1:].upper()} file: {cleaned}] --",
        )]


_ARROW_STAT_KEYS: Dict[str, str] = {
    ".parquet": "parquet_count",
    ".feather": "feather_count",
    ".arrow": "arrow_count",
}


class ArrowParser:
    """Parser for .parquet, .feather, and .arrow files. Requires the pyarrow package."""

    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        ext = file_path.suffix.lower()
        type_name = ext[1:].upper()
        stat_key = _ARROW_STAT_KEYS[ext]

        try:
            import pyarrow  # noqa: F401
        except ImportError:
            note = (
                f"-- [Skipped: {file_path.name} requires pyarrow, "
                "which is not installed] --\n"
            )
            tokens, _ = count_tokens(note)
            return ParserResult(
                content=note,
                tokens=tokens,
                type=type_name,
                status="Skipped (No pyarrow)",
                stats_update={},
            )

        content = process_arrow_file(
            file_path,
            ext,
            config.csv_sample_size,
            config.seed,
            config.stats_summary,
            config.schema_only,
        )
        tokens, _ = count_tokens(flatten_ir(
            content,
            schema_only=config.schema_only,
            stats_summary=config.stats_summary,
            table_limit=config.table_limit,
            table_truncate=config.table_truncate,
        ))
        return ParserResult(
            content=content,
            tokens=tokens,
            type=type_name,
            status="Schema Only" if config.schema_only else "Sampled",
            stats_update={stat_key: 1},
        )


class DefaultParser:
    """Fallback parser for text files."""
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        ext = file_path.suffix.lower()

        if is_binary(file_path):
            return ParserResult(
                content=(
                    f"-- [Binary content detected ({ext if ext else 'unknown'}): "
                    "content not included] --"
                ),
                tokens=0,
                type=f"Binary ({ext})",
                status="Skipped (Binary)",
                stats_update={"binary_count": 1}
            )

        # Skip previously generated outputs (the flag sits in the first line).
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                if GENERATION_FLAG in f.read(100):
                    return ParserResult(content="", tokens=0, type="Skipped", status="Skipped (Generated)", skip_file=True)
        except OSError:
            pass

        try:
            # stat() shares the try/except below deliberately: a file that
            # vanished or became unreadable between scan and parse (a locked
            # file, a permission change, a network-drive hiccup) must degrade
            # to this one file's Error status, not propagate an OSError out
            # of process_target_file and abort the entire run.
            file_size_kb = file_path.stat().st_size / 1024
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
            return ParserResult(
                content="-- [Error: could not read file] --",
                tokens=0,
                type="Error",
                status="Error",
            )


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
        lines.append(f"-- [Error reading .env file: {_sanitize_error(e, Path(file_path))}] --")
    return "\n".join(lines)


class EnvParser:
    """Parser for environment files: lists variable names with redacted values."""
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        if not config.env_keys:
            return ParserResult(
                content=(
                    "-- [Env file skipped (--no-env-keys): "
                    "content not included] --\n"
                ),
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


# --- SQLite Database Parsing ---

SQLITE_MAGIC = b"SQLite format 3\x00"


def _is_sqlite_file(file_path: Path) -> bool:
    """Return True if the file begins with the SQLite format-3 magic header.

    A ``.db`` file is not guaranteed to be SQLite (it may be some other binary
    store), so sniff the 16-byte header before opening it as a database.
    """
    try:
        with open(file_path, "rb") as handle:
            return handle.read(16) == SQLITE_MAGIC
    except OSError:
        return False


def _quote_identifier(name: str) -> str:
    """Quote a SQL identifier so table/view names with spaces, keywords, or
    embedded quotes are used safely (identifiers cannot be parameterized)."""
    return '"' + name.replace('"', '""') + '"'


def _sqlite_table_ddl(
    connection: sqlite3.Connection,
    name: str,
    create_sql: Optional[str],
) -> Optional[str]:
    """Return a table's CREATE statement plus its index definitions, if any."""
    statements: List[str] = []
    if create_sql:
        statements.append(create_sql.strip() + ";")
    try:
        cursor = connection.execute(
            "SELECT sql FROM sqlite_master "
            "WHERE type = 'index' AND tbl_name = ? AND sql IS NOT NULL "
            "ORDER BY name",
            (name,),
        )
        for (index_sql,) in cursor.fetchall():
            statements.append(index_sql.strip() + ";")
    except sqlite3.Error:
        pass
    return "\n".join(statements) if statements else None


def _sqlite_declared_types(
    connection: sqlite3.Connection, name: str
) -> Dict[str, str]:
    """Map column name -> declared SQLite type via PRAGMA table_info."""
    types: Dict[str, str] = {}
    try:
        cursor = connection.execute(
            f"PRAGMA table_info({_quote_identifier(name)})"
        )
        for row in cursor.fetchall():
            # row: (cid, name, type, notnull, dflt_value, pk)
            col_name = str(row[1])
            col_type = str(row[2] or "").strip()
            types[col_name] = col_type or "unknown"
    except sqlite3.Error:
        pass
    return types


def _sqlite_row_count(
    connection: sqlite3.Connection, name: str, count_allowed: bool
) -> Optional[int]:
    """True row count via COUNT(*), or None when unknown/too large to count."""
    if not count_allowed:
        return None
    try:
        cursor = connection.execute(
            f"SELECT COUNT(*) FROM {_quote_identifier(name)}"
        )
        return int(cursor.fetchone()[0])
    except sqlite3.Error:
        return None


def _apply_declared_types(
    schema: TableSchema, declared_types: Dict[str, str]
) -> None:
    """Override pandas-inferred dtypes with declared SQLite column types."""
    for col in schema.columns:
        declared = declared_types.get(col.name)
        if declared:
            col.dtype = declared


def _process_sqlite_table(
    connection: sqlite3.Connection,
    name: str,
    create_sql: Optional[str],
    display_path: str,
    index: int,
    sample_size: int,
    seed: int,
    stats_summary: bool,
    schema_only: bool,
    count_allowed: bool,
    full_scan_max_rows: int,
) -> TableIR:
    """Build one TableIR for a single SQLite table or view.

    Small tables (row count at or below ``full_scan_max_rows``) are read in
    full so ``missing``/``describe`` stats are exact and the sample is random —
    exactly like the CSV path. Larger tables are sampled with ``LIMIT`` and
    expose structure only through their DDL, so sample-derived stats never
    masquerade as full-dataset truth.
    """
    quoted = _quote_identifier(name)
    ddl = _sqlite_table_ddl(connection, name, create_sql)
    declared_types = _sqlite_declared_types(connection, name)
    row_count = _sqlite_row_count(connection, name, count_allowed)
    count_str = f"{row_count:,}" if row_count is not None else "unknown (large)"
    is_large = row_count is None or row_count > full_scan_max_rows

    base = dict(
        name=name,
        sheet_number=index,
        file_path=display_path,
        section_label="Table",
        ddl=ddl,
    )

    # --- Schema-only: no data rows are shown ---
    if schema_only:
        if is_large:
            return TableIR(
                df=pd.DataFrame(),
                header_note=f"-- [Schema only: {count_str} rows, data omitted] --",
                schema=None,
                **base,
            )
        full_df = pd.read_sql_query(f"SELECT * FROM {quoted}", connection)
        schema = build_table_schema(full_df, include_describe=stats_summary)
        _apply_declared_types(schema, declared_types)
        return TableIR(
            df=pd.DataFrame(),
            header_note="-- [Schema only: data rows omitted] --",
            schema=schema,
            **base,
        )

    # --- Large table: LIMIT head sample; structure comes from the DDL only ---
    if is_large:
        sample_df = pd.read_sql_query(
            f"SELECT * FROM {quoted} LIMIT {int(sample_size)}", connection
        )
        shown = len(sample_df)
        return TableIR(
            df=sample_df,
            header_note=f"-- [Sample: first {shown} of {count_str} rows] --",
            footer_note="-- [Large table: full-scan stats omitted] --",
            schema=None,
            **base,
        )

    # --- Small table: full read, exact stats, random sample ---
    full_df = pd.read_sql_query(f"SELECT * FROM {quoted}", connection)
    schema = None
    if stats_summary:
        schema = build_table_schema(full_df, include_describe=stats_summary)
        _apply_declared_types(schema, declared_types)

    total_rows = len(full_df)
    header_note = None
    df = full_df
    if total_rows > sample_size:
        # sort_index restores natural order so the sample reads coherently.
        df = full_df.sample(n=sample_size, random_state=seed).sort_index()
        header_note = f"-- [Sample: random {sample_size} of {total_rows:,} rows] --"
    return TableIR(
        df=df,
        header_note=header_note,
        schema=schema,
        **base,
    )


def process_sqlite(
    file_path: Union[str, Path],
    display_path: str = "",
    sample_size: int = DEFAULT_CSV_SAMPLE_SIZE,
    max_tables: int = DEFAULT_MAX_TABLES,
    seed: int = DEFAULT_SEED,
    stats_summary: bool = True,
    schema_only: bool = False,
    full_scan_max_rows: int = DEFAULT_DB_FULL_SCAN_MAX_ROWS,
) -> List[TableIR]:
    """Read a SQLite database and return one TableIR per table/view.

    Mirrors the Excel path: each table/view becomes a numbered sub-section
    carrying its CREATE-statement DDL, a schema/stats block, and a row sample.
    Tables/views are ordered (tables first, then views, each alphabetical) and
    capped at ``max_tables``.
    """
    fp = Path(file_path)

    # A very large database file could make COUNT(*) itself expensive; gate it
    # on file size so pathological DBs stay fast (rows then reported as unknown).
    try:
        count_allowed = fp.stat().st_size <= DEFAULT_DB_COUNT_MAX_BYTES
    except OSError:
        count_allowed = True

    try:
        connection = sqlite3.connect(f"file:{fp.as_posix()}?mode=ro", uri=True)
    except sqlite3.Error as e:
        return [TableIR(
            name=fp.name,
            df=pd.DataFrame(),
            footer_note=f"-- [Error reading DB: {_sanitize_error(e, fp)}] --",
        )]

    tables_ir: List[TableIR] = []
    try:
        # A file can pass the 16-byte magic-header sniff yet still be
        # corrupted (a truncated download, a partial write, a bad backup) —
        # sqlite3.Error is not an OSError subclass, so an uncaught one here
        # would skip both this function's own error handling *and* main()'s
        # top-level `except OSError`, crashing the whole run over one file.
        try:
            connection.execute("PRAGMA query_only = ON")
            master = connection.execute(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' "
                "ORDER BY type = 'view', name"
            ).fetchall()
        except sqlite3.Error as e:
            return [TableIR(
                name=fp.name,
                df=pd.DataFrame(),
                footer_note=f"-- [Error reading DB: {_sanitize_error(e, fp)}] --",
            )]

        if not master:
            return [TableIR(
                name=fp.name,
                df=pd.DataFrame(),
                footer_note="-- [Note: database contains no user tables] --",
            )]

        for i, (table_name, create_sql) in enumerate(master, 1):
            if i > max_tables:
                if tables_ir:
                    tables_ir[-1].footer_note = (
                        (tables_ir[-1].footer_note or "")
                        + f"\n-- [Database truncated: Only first {max_tables} "
                        "tables processed] --"
                    )
                else:
                    # max_tables == 0: no TableIR exists yet to attach the
                    # note to. Emit a standalone placeholder instead of
                    # returning an empty list — output.py's TableIR branch
                    # requires a non-empty content list, and an empty one
                    # would silently fall through to rendering `str([])`.
                    tables_ir.append(TableIR(
                        name=fp.name,
                        df=pd.DataFrame(),
                        footer_note=(
                            f"-- [Database truncated: Only first {max_tables} "
                            "tables processed] --"
                        ),
                    ))
                break

            try:
                tables_ir.append(_process_sqlite_table(
                    connection=connection,
                    name=str(table_name),
                    create_sql=create_sql,
                    display_path=display_path,
                    index=i,
                    sample_size=sample_size,
                    seed=seed,
                    stats_summary=stats_summary,
                    schema_only=schema_only,
                    count_allowed=count_allowed,
                    full_scan_max_rows=full_scan_max_rows,
                ))
            except Exception as e:
                tables_ir.append(TableIR(
                    name=str(table_name),
                    df=pd.DataFrame(),
                    footer_note=(
                        f"-- [Error reading table data: "
                        f"{_sanitize_error(e, fp)}] --"
                    ),
                    sheet_number=i,
                    file_path=display_path,
                    section_label="Table",
                ))
    finally:
        connection.close()

    return tables_ir


class SQLiteParser:
    """Parser for .db/.sqlite/.sqlite3 SQLite databases (stdlib sqlite3)."""

    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        # Project-relative, forward-slashed path — must match the File Index and
        # the per-table sub-section path keys emitted by the output generators.
        try:
            display_path = file_path.relative_to(Path.cwd()).as_posix()
        except ValueError:
            display_path = file_path.as_posix()

        # A .db file is not necessarily SQLite; sniff the magic header first.
        if not _is_sqlite_file(file_path):
            note = (
                f"-- [Skipped: {file_path.name} is not a SQLite database "
                "(header check failed)] --\n"
            )
            tokens, _ = count_tokens(note)
            return ParserResult(
                content=note,
                tokens=tokens,
                type="SQLite",
                status="Skipped (Binary)",
                stats_update={"binary_count": 1},
            )

        content = process_sqlite(
            file_path,
            display_path,
            config.csv_sample_size,
            config.max_tables,
            config.seed,
            config.stats_summary,
            config.schema_only,
        )
        table_count = len(content)
        tokens, _ = count_tokens(flatten_ir(
            content,
            schema_only=config.schema_only,
            stats_summary=config.stats_summary,
            table_limit=config.table_limit,
            table_truncate=config.table_truncate,
        ))
        return ParserResult(
            content=content,
            tokens=tokens,
            type=f"SQLite ({table_count} tables)",
            status="Schema Only" if config.schema_only else "Sampled",
            stats_update={"sqlite_count": 1, "db_tables_count": table_count},
        )


class ParserRegistry:
    """Handles file-to-parser mapping."""
    def __init__(self) -> None:
        self._parsers: Dict[str, BaseParser] = {}
        self._default_parser = DefaultParser()

    def register(self, extensions: List[str], parser: BaseParser) -> None:
        for ext in extensions:
            self._parsers[ext.lower()] = parser

    def get_parser(self, extension: str) -> BaseParser:
        return self._parsers.get(extension.lower(), self._default_parser)

# Global registry instance
registry = ParserRegistry()
registry.register(['.csv'], CSVParser())
registry.register(['.ipynb'], NotebookParser())
registry.register(['.sql'], SQLParser())
registry.register(['.xlsx', '.xls', '.xlsm'], ExcelParser())
registry.register(['.parquet', '.feather', '.arrow'], ArrowParser())
registry.register(['.db', '.sqlite', '.sqlite3'], SQLiteParser())

# Env files are dispatched by name (not extension) in main.process_target_file,
# because a bare '.env' has no suffix. This shared instance handles all variants.
env_parser = EnvParser()
