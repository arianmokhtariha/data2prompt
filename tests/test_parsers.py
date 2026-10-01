import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import List, Optional

import pandas as pd
import pytest

from data2prompt.constants import NOTEBOOK_NOTICE_LIST_LIMIT
from data2prompt.utils import count_tokens
from data2prompt.parsers import (
    CSVParser,
    NotebookParser,
    process_sql,
    process_csv,
    process_notebook,
    build_table_schema,
    render_schema_block,
    is_env_file,
    process_env,
    EnvParser,
    truncate_long_lines,
    enforce_table_limit,
    flatten_ir,
    fit_table_rows,
    render_table_text,
    NotebookCellIR,
    TableIR,
)

def test_process_sql_handles_multi_row_inserts():
    """
    Test that multi-row INSERT statements (starting with ,) are correctly 
    identified as data and sampled, rather than being treated as generic lines.
    """
    sql_content = """
CREATE TABLE `table1` (
  `id` int(11) NOT NULL
);

INSERT INTO `table1` VALUES (1)
, (2)
, (3)
, (4)
, (5);

CREATE TABLE `table2` (
  `id` int(11) NOT NULL
);
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as temp_sql:
        temp_sql.write(sql_content)
        temp_sql_path = temp_sql.name
    
    try:
        # Use a small sample size and small max_lines to trigger the bug
        # If the rows starting with ',' are not recognized as data, 
        # they will count towards max_lines.
        result = process_sql(temp_sql_path, sample_size=2, max_lines=5)
        
        # 1. Table 2 schema should be preserved even if max_lines is low
        assert "CREATE TABLE `table2`" in result
        
        # 2. Data should be truncated according to sample_size
        assert "[Table data truncated" in result
        assert ", (1)" in result or "VALUES (1)" in result
        assert ", (3)" not in result
        
    finally:
        if os.path.exists(temp_sql_path):
            os.remove(temp_sql_path)

def test_process_sql_preserves_full_schema():
    """
    Test that the entire CREATE TABLE block is preserved regardless of max_lines.
    """
    sql_content = """
-- Some comments at the top
-- More comments
-- Even more comments
CREATE TABLE `large_table` (
  `col1` int,
  `col2` int,
  `col3` int,
  `col4` int,
  `col5` int,
  `col6` int
) ENGINE=InnoDB;

INSERT INTO `large_table` VALUES (1,2,3,4,5,6);
"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.sql', delete=False) as temp_sql:
        temp_sql.write(sql_content)
        temp_sql_path = temp_sql.name
        
    try:
        # Set max_lines very low (e.g., 2)
        # The comments might be truncated, but the CREATE TABLE block must remain intact.
        result = process_sql(temp_sql_path, sample_size=10, max_lines=2)
        
        assert "CREATE TABLE `large_table`" in result
        assert "`col6` int" in result
        assert ") ENGINE=InnoDB;" in result
        assert "INSERT INTO `large_table`" in result

    finally:
        if os.path.exists(temp_sql_path):
            os.remove(temp_sql_path)


def test_build_table_schema_uses_full_df():
    """Missing counts and dtypes must be computed on the full, unsampled df."""
    df = pd.DataFrame({
        "a": [1, 2, 3, 4],
        "b": [None, "x", "y", None],
    })
    schema = build_table_schema(df, include_describe=True)

    assert schema.row_count == 4
    assert schema.col_count == 2

    by_name = {c.name: c for c in schema.columns}
    assert by_name["a"].missing == 0
    assert by_name["b"].missing == 2
    assert by_name["b"].missing_pct == 50.0
    assert "int" in by_name["a"].dtype
    assert schema.describe_df is not None


def test_build_table_schema_without_describe():
    df = pd.DataFrame({"x": [1, 2, 3]})
    schema = build_table_schema(df, include_describe=False)
    assert schema.describe_df is None
    assert schema.row_count == 3


def test_build_table_schema_duplicate_column_names_does_not_crash():
    """A DataFrame with duplicate column labels must not crash schema
    computation. This is unreachable from CSV/Excel (pandas auto-dedupes
    those readers' headers) but is a real Arrow/Parquet/Feather edge case:
    Arrow schemas permit duplicate field names, and df[name] on a duplicate
    pandas label returns a DataFrame instead of a Series, so int(<Series>)
    used to raise TypeError inside the per-column loop."""
    df = pd.DataFrame([[1, 4.0], [2, None], [3, 6.0]])
    df.columns = ["a", "a"]
    schema = build_table_schema(df, include_describe=True)

    assert [c.name for c in schema.columns] == ["a", "a"]
    # Each duplicate-named column keeps its own, positionally-correct stats
    # rather than both collapsing onto whichever one a name lookup finds.
    assert schema.columns[0].missing == 0
    assert schema.columns[1].missing == 1

    # render_schema_block must not crash either, and must keep both
    # same-named columns' describe() rows distinct.
    result = render_schema_block(schema, show_missing=True, show_describe=True)
    a_lines = [l for l in result.splitlines() if l.startswith("| a |")]
    assert len(a_lines) == 2
    assert a_lines != [a_lines[0], a_lines[0]]  # the two rows are not identical


def test_process_csv_schema_only_drops_rows_keeps_schema():
    csv_content = "id,name\n1,alice\n2,bob\n3,carol\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
        tmp.write(csv_content)
        path = tmp.name

    try:
        tables = process_csv(path, sample_size=2, schema_only=True)
        assert len(tables) == 1
        table = tables[0]

        # No data rows are emitted in schema-only mode.
        assert table.df.empty

        # Schema is computed on the FULL df (3 rows), not the sample size.
        assert table.schema is not None
        assert table.schema.row_count == 3
        assert {c.name for c in table.schema.columns} == {"id", "name"}
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_sql_schema_only_keeps_schema_drops_data():
    sql_content = """
CREATE TABLE users (
  id int,
  email varchar(255)
);

INSERT INTO users VALUES (1, 'a@example.com')
, (2, 'b@example.com')
, (3, 'c@example.com');
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as tmp:
        tmp.write(sql_content)
        path = tmp.name

    try:
        result = process_sql(path, schema_only=True)

        # Schema is preserved.
        assert "CREATE TABLE users" in result
        assert "email varchar(255)" in result

        # Actual data values must be dropped, with a note in their place.
        assert "a@example.com" not in result
        assert "data row(s) omitted" in result
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_sql_sample_size_zero_does_not_raise():
    """process_sql with sample_size=0 must return valid output, not an error string."""
    sql_content = (
        "CREATE TABLE t (id int);\n"
        "INSERT INTO t VALUES (1)\n"
        ", (2)\n"
        ", (3)\n"
        ", (4)\n"
        ", (5)\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as tmp:
        tmp.write(sql_content)
        path = tmp.name

    try:
        result = process_sql(path, sample_size=0)
        assert not result.startswith("⚠️"), f"Got error string: {result}"
        assert "CREATE TABLE t" in result
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_sql_sample_size_one_keeps_only_first_row():
    """With sample_size=1, only the first INSERT/data row per table is kept."""
    sql_content = (
        "CREATE TABLE t (id int);\n"
        "INSERT INTO t VALUES (1)\n"
        ", (2)\n"
        ", (3)\n"
        ", (4)\n"
        ", (5)\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as tmp:
        tmp.write(sql_content)
        path = tmp.name

    try:
        result = process_sql(path, sample_size=1)
        assert not result.startswith("⚠️"), f"Got error string: {result}"
        # The first INSERT line must appear; no extra data rows should be sampled.
        assert "INSERT INTO t VALUES (1)" in result
        assert "Table data truncated" in result
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_sql_sample_larger_than_buffer_returns_all_rows():
    """When sample_size > number of buffered rows the else-branch returns all rows intact."""
    sql_content = (
        "CREATE TABLE t (id int);\n"
        "INSERT INTO t VALUES (1)\n"
        ", (2)\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as tmp:
        tmp.write(sql_content)
        path = tmp.name

    try:
        result = process_sql(path, sample_size=100)
        assert not result.startswith("⚠️"), f"Got error string: {result}"
        assert "(1)" in result
        assert "(2)" in result
        # No truncation footer should appear when the buffer fits within sample_size.
        assert "Table data truncated" not in result
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_render_schema_block_merged_table():
    """When show_describe=True, schema and describe stats appear in one unified table."""
    df = pd.DataFrame({
        "score": [1.0, 2.0, 3.0],
        "label": ["a", "b", "a"],
    })
    schema = build_table_schema(df, include_describe=True)
    result = render_schema_block(schema, show_missing=True, show_describe=True)

    # No separate summary statistics section.
    assert "**Summary statistics**" not in result

    # Stat column headers are in the same header row as column/dtype.
    header_line = [l for l in result.splitlines() if l.startswith("| column")][0]
    assert "dtype" in header_line
    assert "missing" in header_line
    assert "count" in header_line
    assert "mean" in header_line

    # Numeric column: mean is present, unique/top/freq are empty.
    score_line = [l for l in result.splitlines() if l.startswith("| score")][0]
    assert "| score |" in score_line
    assert "2.0" in score_line  # mean of [1, 2, 3]

    # String column: top is present, mean is empty.
    label_line = [l for l in result.splitlines() if l.startswith("| label")][0]
    assert "| label |" in label_line
    assert "a" in label_line  # most frequent value


def test_render_schema_block_no_describe_fallback():
    """When show_describe=False, only column/dtype columns are rendered."""
    df = pd.DataFrame({"x": [1, 2, 3]})
    schema = build_table_schema(df, include_describe=False)
    result = render_schema_block(schema, show_missing=False, show_describe=False)

    assert "| column | dtype |" in result
    assert "count" not in result
    assert "**Summary statistics**" not in result


def test_render_schema_block_nan_becomes_empty_string():
    """NaN cells in the merged table must render as empty strings, not 'nan'."""
    df = pd.DataFrame({
        "num": [1.0, 2.0, 3.0],
        "cat": ["x", "y", "x"],
    })
    schema = build_table_schema(df, include_describe=True)
    result = render_schema_block(schema, show_missing=True, show_describe=True)

    assert "nan" not in result.lower()


def test_is_env_file():
    assert is_env_file(".env") is True
    assert is_env_file(".env.local") is True
    assert is_env_file(".env.production") is True
    assert is_env_file("prod.env") is True
    # Intentionally excluded:
    assert is_env_file(".envrc") is False
    assert is_env_file("config.py") is False


def test_process_env_redacts_every_value():
    env_content = (
        "# a comment line\n"
        "\n"
        "DATABASE_URL=postgres://user:secret@host/db\n"
        "export API_KEY=super-secret-value\n"
        "PLAIN=value\n"
        "not_a_var_line\n"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
        tmp.write(env_content)
        path = tmp.name

    try:
        out = process_env(path)

        # Variable names are present, with redacted values.
        assert "DATABASE_URL=<redacted>" in out
        assert "API_KEY=<redacted>" in out
        assert "PLAIN=<redacted>" in out

        # No secret value may ever leak.
        assert "secret" not in out
        assert "super-secret-value" not in out
        assert "postgres://" not in out
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_env_parser_respects_no_env_keys():
    env_content = "API_KEY=super-secret-value\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
        tmp.write(env_content)
        path = tmp.name

    try:
        # --no-env-keys -> skip entirely, no names, no values.
        skip_cfg = SimpleNamespace(env_keys=False)
        skipped = EnvParser().parse(Path(path), skip_cfg)
        assert skipped.status == "Skipped (Env)"
        assert "super-secret-value" not in skipped.content
        assert skipped.stats_update == {"env_count": 1}

        # Default -> names listed, values redacted.
        keys_cfg = SimpleNamespace(env_keys=True)
        redacted = EnvParser().parse(Path(path), keys_cfg)
        assert redacted.status == "Redacted"
        assert "API_KEY=<redacted>" in redacted.content
        assert "super-secret-value" not in redacted.content
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_missing_source_key_does_not_abort():
    """A cell without 'source' must not trigger the global error cell (number=0)."""
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "source": ["print('hello')"],
                "outputs": [],
                "execution_count": None,
            },
            {
                # 'source' key deliberately absent
                "cell_type": "code",
                "outputs": [],
                "execution_count": None,
            },
        ],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ipynb", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(nb, tmp)
        path = tmp.name

    try:
        cells, _ = process_notebook(path)
        # Both cells must be returned; the global error cell has number=0.
        assert len(cells) == 2
        assert all(c.number != 0 for c in cells)
        assert "print('hello')" in cells[0].source
        # Malformed cell degrades to empty source rather than aborting.
        assert cells[1].source == ""
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_empty_cells_list_does_not_render_as_bare_list():
    """A valid but genuinely empty notebook ("cells": []) must not return an
    empty list: output.py's NotebookCellIR branch requires a non-empty list
    to take that rendering path, and an empty one would silently fall
    through to rendering the bare Python repr "[]" with no explanation."""
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": []}
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ipynb", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(nb, tmp)
        path = tmp.name

    try:
        cells, _ = process_notebook(path)
        assert len(cells) == 1
        assert "no cells" in cells[0].source
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_error_output_captured():
    """An 'error' output type must appear in the cell's outputs with a clear marker."""
    nb = {
        "nbformat": 4,
        "nbformat_minor": 5,
        "metadata": {},
        "cells": [
            {
                "cell_type": "code",
                "source": ["raise ValueError('boom')"],
                "outputs": [
                    {
                        "output_type": "error",
                        "ename": "ValueError",
                        "evalue": "boom",
                        "traceback": [
                            "Traceback (most recent call last):",
                            "  File \"<ipython>\", line 1, in <module>",
                            "ValueError: boom",
                        ],
                    }
                ],
                "execution_count": 1,
            }
        ],
    }
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".ipynb", delete=False, encoding="utf-8"
    ) as tmp:
        json.dump(nb, tmp)
        path = tmp.name

    try:
        cells, _ = process_notebook(path)
        assert len(cells) == 1
        assert cells[0].outputs is not None
        assert "Error output" in cells[0].outputs
        assert "ValueError: boom" in cells[0].outputs
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# truncate_long_lines
# ---------------------------------------------------------------------------

def test_truncate_long_lines_short_lines_pass_through() -> None:
    text = "short line\nanother short line\n"
    assert truncate_long_lines(text, threshold=100, truncate_to=50) == text


def test_truncate_long_lines_truncates_and_annotates() -> None:
    long_line = "A" * 200
    result = truncate_long_lines(long_line + "\n", threshold=100, truncate_to=50)
    first_line = result.splitlines()[0]
    assert first_line.startswith("A" * 50)
    assert "Line truncated" in first_line


def test_truncate_long_lines_only_long_lines_affected() -> None:
    text = "short\n" + "X" * 600 + "\nshort again\n"
    result = truncate_long_lines(text, threshold=100, truncate_to=50)
    lines = result.splitlines()
    assert lines[0] == "short"
    assert lines[1].startswith("X" * 50)
    assert "Line truncated" in lines[1]
    assert lines[2] == "short again"


def test_truncate_long_lines_preserves_trailing_newline() -> None:
    text = "normal line\n"
    result = truncate_long_lines(text, threshold=100, truncate_to=50)
    assert result.endswith("\n")


def test_truncate_long_lines_empty_string() -> None:
    assert truncate_long_lines("", threshold=100, truncate_to=50) == ""


# ---------------------------------------------------------------------------
# enforce_table_limit
# ---------------------------------------------------------------------------

def test_enforce_table_limit_within_limit_unchanged() -> None:
    text = "small table"
    assert enforce_table_limit(text, limit=1000, truncate_to=500) == text


def test_enforce_table_limit_at_exact_limit_unchanged() -> None:
    text = "A" * 1000
    assert enforce_table_limit(text, limit=1000, truncate_to=500) == text


# ---------------------------------------------------------------------------
# process_csv — normal (non-schema-only) path
# ---------------------------------------------------------------------------

def test_process_csv_samples_when_over_limit() -> None:
    rows = "\n".join([f"{i},val{i}" for i in range(100)])
    csv_content = "id,value\n" + rows + "\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        tables = process_csv(path, sample_size=10, seed=42)
        assert len(tables) == 1
        table = tables[0]
        assert len(table.df) == 10
        assert table.header_note is not None and "Sample" in table.header_note
        # The header note alone carries the sampling fact; no duplicate footer.
        assert table.footer_note is None
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_csv_sample_notes_include_total_rows() -> None:
    """Sample notes must ground the LLM with the full-dataset row count —
    'random 10 of 100 rows' — so a sample is never mistaken for the data."""
    rows = "\n".join([f"{i},val{i}" for i in range(100)])
    csv_content = "id,value\n" + rows + "\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        tables = process_csv(path, sample_size=10, seed=42)
        table = tables[0]
        assert table.header_note == "-- [Sample: random 10 of 100 rows] --"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_tool_notices_use_bracket_grammar() -> None:
    """Every tool-inserted notice must use the `-- [...] --` grammar the
    system instructions document; a `*Note:` star-note would silently break
    that contract for the LLM."""
    # Env skip note (--no-env-keys)
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
        tmp.write("API_KEY=secret\n")
        env_path = tmp.name
    try:
        skip_cfg = SimpleNamespace(env_keys=False)
        skipped = EnvParser().parse(Path(env_path), skip_cfg)
        assert skipped.content.startswith("-- [")
        assert "*Note" not in skipped.content
    finally:
        if os.path.exists(env_path):
            os.remove(env_path)

    # Malformed-notebook note
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as tmp:
        tmp.write("{not valid json")
        nb_path = tmp.name
    try:
        cells, _ = process_notebook(nb_path)
        assert cells[0].source.startswith("-- [")
        assert "*Error" not in cells[0].source
    finally:
        if os.path.exists(nb_path):
            os.remove(nb_path)


def test_process_csv_no_sampling_when_under_limit() -> None:
    csv_content = "id,value\n1,a\n2,b\n3,c\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        tables = process_csv(path, sample_size=100)
        assert len(tables) == 1
        table = tables[0]
        assert len(table.df) == 3
        assert table.header_note is None
        assert table.footer_note is None
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_csv_empty_file_returns_footer_note() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
        tmp.write("")
        path = tmp.name
    try:
        tables = process_csv(path)
        assert len(tables) == 1
        assert tables[0].df.empty
        assert tables[0].footer_note is not None
        assert "empty" in tables[0].footer_note.lower()
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# process_notebook — output types
# ---------------------------------------------------------------------------

def test_process_notebook_stream_output_captured() -> None:
    nb = {
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [{
            "cell_type": "code",
            "source": ["print('hello')"],
            "outputs": [{"output_type": "stream", "name": "stdout", "text": ["hello\n"]}],
            "execution_count": 1,
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False, encoding="utf-8") as tmp:
        json.dump(nb, tmp)
        path = tmp.name
    try:
        cells, _ = process_notebook(path)
        assert cells[0].outputs is not None
        assert "hello" in cells[0].outputs
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_execute_result_captured() -> None:
    nb = {
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [{
            "cell_type": "code",
            "source": ["1 + 1"],
            "outputs": [{
                "output_type": "execute_result",
                "metadata": {},
                "data": {"text/plain": ["2"]},
                "execution_count": 1,
            }],
            "execution_count": 1,
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False, encoding="utf-8") as tmp:
        json.dump(nb, tmp)
        path = tmp.name
    try:
        cells, _ = process_notebook(path)
        assert cells[0].outputs is not None
        assert "2" in cells[0].outputs
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_base64_display_data_skipped() -> None:
    """display_data whose text/plain contains 'base64' is dropped, but the
    cell still says an output was omitted (never a silent drop)."""
    nb = {
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [{
            "cell_type": "code",
            "source": ["show_image()"],
            "outputs": [{
                "output_type": "display_data",
                "metadata": {},
                "data": {"text/plain": ["<base64 encoded image data>"], "image/png": "abc123"},
            }],
            "execution_count": 1,
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False, encoding="utf-8") as tmp:
        json.dump(nb, tmp)
        path = tmp.name
    try:
        cells, _ = process_notebook(path)
        assert cells[0].outputs == "-- [Output omitted: text/plain, image/png] --"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_stream_output_truncated_at_max_lines() -> None:
    """Stream output beyond max_lines is cut with a truncation marker."""
    output_lines = [f"line {i}\n" for i in range(20)]
    nb = {
        "nbformat": 4, "nbformat_minor": 5, "metadata": {},
        "cells": [{
            "cell_type": "code",
            "source": ["run_loop()"],
            "outputs": [{"output_type": "stream", "name": "stdout", "text": output_lines}],
            "execution_count": 1,
        }],
    }
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False, encoding="utf-8") as tmp:
        json.dump(nb, tmp)
        path = tmp.name
    try:
        cells, _ = process_notebook(path, max_lines=5)
        assert cells[0].outputs is not None
        assert "Output truncated" in cells[0].outputs
        kept_lines = [l for l in cells[0].outputs.split("\n") if l.startswith("line")]
        assert len(kept_lines) == 5
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_malformed_json_returns_error_cell() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False, encoding="utf-8") as tmp:
        tmp.write("{ this is not valid json }")
        path = tmp.name
    try:
        cells, _ = process_notebook(path)
        assert len(cells) == 1
        assert cells[0].number == 0
        assert "Malformed" in cells[0].source or "Invalid" in cells[0].source
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# flatten_ir
# ---------------------------------------------------------------------------

def test_flatten_ir_string_content() -> None:
    assert flatten_ir("hello world") == "hello world"


def test_flatten_ir_empty_list() -> None:
    assert flatten_ir([]) == ""


def test_flatten_ir_notebook_cells_joins_source_and_outputs() -> None:
    cells = [
        NotebookCellIR(number=1, type="code", source="x = 1", outputs="1"),
        NotebookCellIR(number=2, type="markdown", source="# Header", outputs=None),
    ]
    result = flatten_ir(cells)
    assert "x = 1" in result
    assert "1" in result
    assert "# Header" in result


def test_flatten_ir_table_normal_includes_data_rows() -> None:
    df = pd.DataFrame({"col": ["alpha", "beta"]})
    result = flatten_ir([TableIR(name="t.csv", df=df)])
    assert "alpha" in result
    assert "beta" in result


def test_flatten_ir_table_schema_only_drops_data_rows() -> None:
    df = pd.DataFrame({"col": ["SENTINEL_A", "SENTINEL_B"]})
    schema = build_table_schema(df, include_describe=False)
    result = flatten_ir([TableIR(name="t.csv", df=df, schema=schema)], schema_only=True)
    assert "**Schema**" in result
    assert "SENTINEL_A" not in result
    assert "SENTINEL_B" not in result


def test_flatten_ir_table_stats_summary_includes_schema() -> None:
    df = pd.DataFrame({"score": [1.0, 2.0, 3.0]})
    schema = build_table_schema(df, include_describe=True)
    result = flatten_ir([TableIR(name="t.csv", df=df, schema=schema)], stats_summary=True)
    assert "**Schema**" in result
    assert "score" in result


# ---------------------------------------------------------------------------
# process_env — edge cases
# ---------------------------------------------------------------------------

def test_process_env_skips_non_identifier_keys() -> None:
    env_content = "123INVALID=secret\nVALID_KEY=other_secret\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
        tmp.write(env_content)
        path = tmp.name
    try:
        out = process_env(path)
        assert "VALID_KEY=<redacted>" in out
        assert "123INVALID" not in out
        assert "secret" not in out
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_env_empty_file_returns_header_only() -> None:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
        tmp.write("")
        path = tmp.name
    try:
        out = process_env(path)
        assert out == "# Environment variables (names only, values redacted)"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_env_line_without_equals_is_skipped() -> None:
    env_content = "NOTAVAR\nVALID=value\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".env", delete=False) as tmp:
        tmp.write(env_content)
        path = tmp.name
    try:
        out = process_env(path)
        assert "NOTAVAR" not in out
        assert "VALID=<redacted>" in out
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# process_sql — omitted non-data lines must be announced
# ---------------------------------------------------------------------------

def test_process_sql_announces_omitted_non_data_lines() -> None:
    """Non-data lines beyond --sql-max-lines must leave an omission marker,
    not vanish silently — an LLM can't reason about content it doesn't know
    was removed."""
    comments = "\n".join(f"-- comment number {i}" for i in range(10))
    sql_content = comments + "\nCREATE TABLE t (id int);\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as tmp:
        tmp.write(sql_content)
        path = tmp.name
    try:
        result = process_sql(path, max_lines=3)
        assert "non-data line(s) omitted" in result
        assert "--sql-max-lines" in result
        # The schema itself must still be intact.
        assert "CREATE TABLE t" in result
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_sql_no_omission_marker_when_under_limit() -> None:
    sql_content = "-- one comment\nCREATE TABLE t (id int);\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sql", delete=False) as tmp:
        tmp.write(sql_content)
        path = tmp.name
    try:
        result = process_sql(path, max_lines=50)
        assert "non-data line(s) omitted" not in result
    finally:
        if os.path.exists(path):
            os.remove(path)


# ---------------------------------------------------------------------------
# process_csv — sampled rows keep original file order
# ---------------------------------------------------------------------------

def test_process_csv_sample_preserves_original_row_order() -> None:
    """The random sample must be re-sorted by original position so the excerpt
    reads like the file (time series stay chronological, ids stay ascending)."""
    rows = "\n".join(f"{i},val{i}" for i in range(200))
    csv_content = "id,value\n" + rows + "\n"
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
        tmp.write(csv_content)
        path = tmp.name
    try:
        tables = process_csv(path, sample_size=20, seed=42)
        ids = tables[0].df["id"].tolist()
        assert ids == sorted(ids), "sampled rows are not in original file order"
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_csv_floats_keep_the_digits_written_in_the_file(
    tmp_path: Path,
) -> None:
    """pandas' default C float parser is off by 1 ulp on many values
    (97.68560353337905 reads back as ...904), so a sample row would show a
    digit that is not in the source file."""
    csv_path = tmp_path / "readings.csv"
    csv_path.write_text(
        "v\n97.68560353337905\n13.436424411240122\n", encoding="utf-8"
    )

    table = process_csv(csv_path, sample_size=10)[0]

    assert [repr(v) for v in table.df["v"]] == [
        "97.68560353337905",
        "13.436424411240122",
    ]


def _write_sql(tmp_path: Path, body: str) -> Path:
    """Write a one-table SQL dump and return its path."""
    path = tmp_path / "dump.sql"
    path.write_text("CREATE TABLE t (id int);\n" + body, encoding="utf-8")
    return path


def _shown_tuples(result: str) -> list[str]:
    """Return the row-tuple lines kept in the processed SQL output."""
    return [ln for ln in result.splitlines() if ln.lstrip(", ").startswith("(")]


def test_process_sql_bare_header_with_exactly_sample_size_rows_keeps_all(
    tmp_path: Path,
) -> None:
    """The header line is not a row, so 3 rows fit a sample size of 3."""
    path = _write_sql(
        tmp_path, "INSERT INTO t VALUES\n" + "".join(f"({i}),\n" for i in range(3))
    )

    result = process_sql(path, sample_size=3)

    assert len(_shown_tuples(result)) == 3
    assert "Table data truncated" not in result


def test_process_sql_bare_header_samples_exactly_sample_size_rows(
    tmp_path: Path,
) -> None:
    """A bare header plus 6 rows at size 3 shows the header and 3 rows."""
    path = _write_sql(
        tmp_path, "INSERT INTO t VALUES\n" + "".join(f"({i}),\n" for i in range(6))
    )

    result = process_sql(path, sample_size=3)

    assert "INSERT INTO t VALUES\n" in result
    assert len(_shown_tuples(result)) == 3
    assert "Showing random 3 of 6 rows" in result


def test_process_sql_second_bare_header_is_kept_and_never_sampled_as_row(
    tmp_path: Path,
) -> None:
    """Two bare headers in one buffer: both survive and neither is counted."""
    body = (
        "INSERT INTO t VALUES\n"
        + "".join(f"({i}),\n" for i in range(4))
        + "INSERT INTO t VALUES\n"
        + "".join(f"({i}),\n" for i in range(4, 8))
    )
    path = _write_sql(tmp_path, body)

    for seed in range(20):
        result = process_sql(path, sample_size=2, seed=seed)
        assert result.count("INSERT INTO t VALUES\n") == 2
        assert len(_shown_tuples(result)) == 2
        assert "Showing random 2 of 8 rows" in result


def test_process_sql_one_insert_per_row_lines_are_sampled_normally(
    tmp_path: Path,
) -> None:
    """Each full INSERT line is a data row; none is a header."""
    path = _write_sql(
        tmp_path, "".join(f"INSERT INTO t VALUES ({i});\n" for i in range(10))
    )

    result = process_sql(path, sample_size=4)

    assert result.count("INSERT INTO t VALUES (") == 4
    assert "INSERT INTO t VALUES (0);" in result  # line 0 is always kept
    assert "Showing random 4 of 10 rows" in result


def test_process_sql_inline_first_tuple_header_is_kept_and_counted(
    tmp_path: Path,
) -> None:
    """A header carrying the first tuple is a data row that counts as shown."""
    path = _write_sql(
        tmp_path,
        "INSERT INTO t VALUES (1)\n" + "".join(f", ({i})\n" for i in range(2, 7)),
    )

    result = process_sql(path, sample_size=3)

    assert "INSERT INTO t VALUES (1)" in result
    assert len(_shown_tuples(result)) == 2  # ", (n)" lines; (1) is on the header
    assert "Showing random 3 of 6 rows" in result


def test_process_sql_sample_size_zero_with_row_opener_reports_one_shown(
    tmp_path: Path,
) -> None:
    """Line 0 is always kept, so the notice reports the truth: 1 row shown."""
    path = _write_sql(
        tmp_path,
        "INSERT INTO t VALUES (1)\n" + "".join(f", ({i})\n" for i in range(2, 6)),
    )

    result = process_sql(path, sample_size=0)

    assert "Showing random 1 of 5 rows" in result


def test_process_sql_schema_only_counts_data_rows_not_headers(
    tmp_path: Path,
) -> None:
    """The omitted-row note excludes bare INSERT ... VALUES header lines."""
    body = (
        "INSERT INTO t VALUES\n"
        + "".join(f"({i}),\n" for i in range(4))
        + "INSERT INTO t VALUES\n"
        + "".join(f"({i}),\n" for i in range(4, 8))
    )
    path = _write_sql(tmp_path, body)

    result = process_sql(path, schema_only=True)

    assert "8 data row(s) omitted: schema-only" in result


# ---------------------------------------------------------------------------
# Honest inclusion status — CSVParser / NotebookParser derive the File Index
# status from what the parse actually did, never from a constant.
# ---------------------------------------------------------------------------

def _status_config(
    csv_sample_size: int = 15,
    schema_only: bool = False,
    max_lines: int = 40,
    table_limit: int = 50_000,
    table_truncate: int = 20_000,
) -> SimpleNamespace:
    return SimpleNamespace(
        csv_sample_size=csv_sample_size,
        seed=42,
        stats_summary=True,
        schema_only=schema_only,
        max_lines=max_lines,
        line_length_threshold=4000,
        truncated_line_length=1000,
        table_limit=table_limit,
        table_truncate=table_truncate,
    )


_CP1252_CSV = b"name,city\nJos\xe9,S\xe3o Paulo\n"


@pytest.mark.parametrize(
    ("payload", "schema_only", "expected_status"),
    [
        # cp1252 bytes the utf-8 reader rejects: the body is only an error note.
        (_CP1252_CSV, False, "Error"),
        # A failed read is not a schema either, even under --schema-only.
        (_CP1252_CSV, True, "Error"),
        # Every row shown: nothing was sampled, so the file is Full.
        (b"id,v\n1,a\n2,b\n3,c\n", False, "Read"),
        (b"id,v\n" + b"".join(b"%d,x\n" % i for i in range(20)), False, "Sampled"),
        (b"id,v\n1,a\n", True, "Schema Only"),
    ],
    ids=["unreadable", "unreadable-schema-only", "all-rows", "sampled", "schema"],
)
def test_csv_parser_status_follows_parse_outcome(
    tmp_path: Path, payload: bytes, schema_only: bool, expected_status: str
) -> None:
    path = tmp_path / "data.csv"
    path.write_bytes(payload)

    result = CSVParser().parse(path, _status_config(schema_only=schema_only))

    assert result.status == expected_status


def _write_notebook(path: Path, cells: List[dict]) -> None:
    nb = {"nbformat": 4, "nbformat_minor": 5, "metadata": {}, "cells": cells}
    path.write_text(json.dumps(nb), encoding="utf-8")


def _code_cell(
    source: str, execution_count: Optional[int], outputs: Optional[list] = None
) -> dict:
    return {
        "cell_type": "code",
        "execution_count": execution_count,
        "metadata": {},
        "source": [source],
        "outputs": outputs or [],
    }


@pytest.mark.parametrize(
    ("outputs", "expected_status"),
    [
        # Short text output kept verbatim: nothing trimmed, so Full.
        ([{"output_type": "stream", "name": "stdout", "text": ["ok\n"]}], "Read"),
        # Output clipped at max_lines.
        (
            [{"output_type": "stream", "name": "stdout",
              "text": [f"line {i}\n" for i in range(60)]}],
            "Cleaned",
        ),
        # A figure: the image is stripped, only its text/plain label is kept.
        (
            [{"output_type": "display_data", "metadata": {},
              "data": {"text/plain": ["<Figure>"], "image/png": "iVBORw0K"}}],
            "Cleaned",
        ),
    ],
    ids=["untouched", "lines-clipped", "image-stripped"],
)
def test_notebook_parser_status_is_cleaned_only_when_trimmed(
    tmp_path: Path, outputs: list, expected_status: str
) -> None:
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell("run()", 1, outputs)])

    result = NotebookParser().parse(path, _status_config())

    assert result.status == expected_status


def test_notebook_parser_long_source_line_marks_cleaned(tmp_path: Path) -> None:
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell("x = '" + "a" * 5000 + "'", 1)])

    result = NotebookParser().parse(path, _status_config())

    assert result.status == "Cleaned"


def test_notebook_parser_malformed_notebook_is_error(tmp_path: Path) -> None:
    path = tmp_path / "nb.ipynb"
    path.write_text("{ not json", encoding="utf-8")

    result = NotebookParser().parse(path, _status_config())

    assert result.status == "Error"


# ---------------------------------------------------------------------------
# Notebooks — ANSI noise and execution-state forensics
# ---------------------------------------------------------------------------

def test_process_notebook_strips_ansi_from_traceback(tmp_path: Path) -> None:
    """IPython stores colored tracebacks; the escape codes are token noise."""
    error = {
        "output_type": "error",
        "ename": "ValueError",
        "evalue": "bad",
        "traceback": [
            "\u001b[1;31mValueError\u001b[0m                Traceback",
            "\u001b[1;31mValueError\u001b[0m: bad",
        ],
    }
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell("f()", 1, [error])])

    cells, _ = process_notebook(path)

    outputs = cells[-1].outputs or ""
    assert "\x1b" not in outputs
    assert "[1;31m" not in outputs
    assert "ValueError: bad" in outputs


def test_process_notebook_reports_execution_state(tmp_path: Path) -> None:
    """Out-of-order run + a never-run cell + missing counts + an error: one
    compact file-level notice, cell numbers throughout (matching the
    `Cell {n}` headers), counts only in the clause labeled as counts. No
    pseudo-cell carries it."""
    error = {"output_type": "error", "ename": "ValueError", "evalue": "x",
             "traceback": ["ValueError: x"]}
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [
        {"cell_type": "markdown", "metadata": {}, "source": ["# EDA"]},
        _code_cell("import pandas as pd", 1),
        _code_cell("df.mean()", 5, [error]),
        _code_cell("df.shape", 2),
        _code_cell("df.merge(other)", None),
    ])

    cells, notice = process_notebook(path)

    assert notice == (
        "-- [Execution state: cells ran in order 2,4,3; cell 5 never run; "
        "execution counts 3-4 missing (hidden state possible); "
        "first error in cell 3: ValueError] --"
    )
    assert [c.number for c in cells] == [1, 2, 3, 4, 5]


def test_execution_notice_orders_cells_not_counts(tmp_path: Path) -> None:
    """Cell 2 ran first (count 1), then cell 3, then cell 1 (count 3): the
    order is cell numbers `2,3,1`, never the raw counts `3,1,2`."""
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [
        _code_cell("c", 3), _code_cell("a", 1), _code_cell("b", 2),
    ])

    _, notice = process_notebook(path)

    assert notice == "-- [Execution state: cells ran in order 2-3,1] --"


def test_process_notebook_execution_state_collapses_ranges(
    tmp_path: Path,
) -> None:
    """Long in-order stretches collapse to ranges so the notice stays short."""
    counts = [1, 2, 3, 7, 8, 4, 5, 6]
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell(f"x{c}", c) for c in counts])

    _, notice = process_notebook(path)

    assert notice == "-- [Execution state: cells ran in order 1-3,6-8,4-5] --"


def test_execution_notice_lists_are_capped(tmp_path: Path) -> None:
    """A 100-cell notebook must not produce a 800-character notice: each list
    stops at NOTEBOOK_NOTICE_LIST_LIMIT items and says how many were cut."""
    # Alternating pattern: every other cell never run, plus swapped pairs so
    # the run order has many separate runs.
    cells = []
    for i in range(1, 101):
        if i % 2 == 0:
            cells.append(_code_cell(f"x{i}", None))
        else:
            cells.append(_code_cell(f"x{i}", 101 - i))
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, cells)

    _, notice = process_notebook(path)

    assert notice is not None
    assert len(notice) < 400
    limit = NOTEBOOK_NOTICE_LIST_LIMIT
    assert notice.count("…(+") >= 2
    # 50 never-run cells make 50 single-cell runs: limit shown, rest counted.
    assert f"…(+{50 - limit} more) never run" in notice


def test_execution_notice_more_tail_counts_hidden_cells(tmp_path: Path) -> None:
    """`(+N more)` counts hidden cells, not collapsed runs: one hidden run of
    three cells must read +3, never +1."""
    limit = NOTEBOOK_NOTICE_LIST_LIMIT
    # One ran cell, then (limit + 1) never-run groups of 3 cells split by
    # single ran cells so each group stays a separate run.
    cells = [_code_cell("ran", 1)]
    for group in range(limit + 1):
        cells.extend(_code_cell(f"g{group}_{i}", None) for i in range(3))
        cells.append(_code_cell(f"sep{group}", group + 2))
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, cells)

    _, notice = process_notebook(path)

    assert notice is not None
    assert "…(+3 more) never run" in notice


def test_execution_notice_flags_duplicate_execution_counts(
    tmp_path: Path,
) -> None:
    """Two cells sharing one count cannot be a clean run (a restored or
    hand-edited notebook): equal neighbours count as out of order."""
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell("a", 1), _code_cell("b", 1)])

    _, notice = process_notebook(path)

    assert notice is not None
    assert "cells ran in order" in notice


@pytest.mark.parametrize(
    "output",
    [
        {"output_type": "execute_result", "execution_count": 1, "metadata": {},
         "data": {"text/plain": ["\x1b[1;32mvalue\x1b[0m"]}},
        {"output_type": "display_data", "metadata": {},
         "data": {"text/plain": ["\x1b[1;32mvalue\x1b[0m"]}},
    ],
    ids=["execute_result", "display_data"],
)
def test_ansi_is_stripped_from_rich_text_outputs(
    tmp_path: Path, output: dict
) -> None:
    path = _single_output_notebook(tmp_path, output)

    cells, _ = process_notebook(path)

    assert "\x1b" not in (cells[0].outputs or "")
    assert "value" in (cells[0].outputs or "")


@pytest.mark.parametrize(
    "counts",
    [[1, 2, 3], [None, None]],
    ids=["clean-top-to-bottom-run", "never-executed"],
)
def test_process_notebook_no_execution_notice_when_unremarkable(
    tmp_path: Path, counts: List[Optional[int]]
) -> None:
    """A clean run, or a notebook saved without executing (outputs cleared),
    carries no hidden state: no notice, no extra tokens."""
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell("pass", c) for c in counts])

    cells, notice = process_notebook(path)

    assert notice is None
    assert all(c.number != 0 for c in cells)


# ---------------------------------------------------------------------------
# Table character cap vs. inclusion status (one source of truth)
# ---------------------------------------------------------------------------

def _wide_csv(rows: int, cell_chars: int) -> bytes:
    body = "".join(f"{i}," + "x" * cell_chars + "\n" for i in range(rows))
    return ("id,blob\n" + body).encode("utf-8")


@pytest.mark.parametrize(
    ("table_limit", "table_truncate", "expected_status", "expect_notice"),
    [
        # 8 rows x 9,000 chars blow the cap: the body is cut, so not Full.
        (50_000, 20_000, "Sampled", True),
        # Cap far above the text: every row shown, Full.
        (500_000, 200_000, "Read", False),
        # Over the limit but the kept-size budget still holds every row: no
        # cut happens, so the file stays Full.
        (1_000, 10_000_000, "Read", False),
    ],
    ids=["cut-at-render", "fits", "over-limit-but-nothing-cut"],
)
def test_csv_status_agrees_with_render_time_table_cap(
    tmp_path: Path,
    table_limit: int,
    table_truncate: int,
    expected_status: str,
    expect_notice: bool,
) -> None:
    """The cap is applied when rendering, after the parser has decided the
    status; the status must still match what the document body shows."""
    path = tmp_path / "wide.csv"
    path.write_bytes(_wide_csv(rows=8, cell_chars=9_000))
    config = _status_config(table_limit=table_limit, table_truncate=table_truncate)

    result = CSVParser().parse(path, config)
    body = render_table_text(
        result.content[0],
        include_rows=True,
        table_limit=table_limit,
        table_truncate=table_truncate,
    )

    assert result.status == expected_status
    assert ("Table truncated" in body) is expect_notice


def test_fit_table_rows_is_what_enforce_table_limit_cuts_with() -> None:
    """enforce_table_limit and the status check share one row-fit helper, so
    the kept count it reports is exactly what the rendered text keeps."""
    text = "\n".join(["| h |", "|---|"] + [f"| {'y' * 40} |" for _ in range(10)])

    header, rows, kept = fit_table_rows(text, 200, 150, 2)
    cut = enforce_table_limit(text, 200, 150, header_lines=2)

    assert 0 < kept < len(rows) == 10
    assert cut.split("\n")[: 2 + kept] == header + rows[:kept]
    assert f"showing first {kept} of 10 rows" in cut


# ---------------------------------------------------------------------------
# Notebook outputs dropped without a text form leave a notice
# ---------------------------------------------------------------------------

def _single_output_notebook(tmp_path: Path, output: dict) -> Path:
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell("show()", 1, [output])])
    return path


def test_image_only_output_leaves_an_omitted_notice(tmp_path: Path) -> None:
    """An image/HTML-only output used to vanish: no Outputs block at all, yet
    the status said Cleaned. The cell now names what was left out."""
    path = _single_output_notebook(tmp_path, {
        "output_type": "display_data", "metadata": {},
        "data": {"image/png": "iVBORw0K", "text/html": ["<img>"]},
    })

    cells, _ = process_notebook(path)

    assert cells[0].outputs == "-- [Output omitted: image/png, text/html] --"
    assert cells[0].trimmed is True


def test_dropping_redundant_rich_data_beside_text_needs_no_notice(
    tmp_path: Path,
) -> None:
    """text/plain was kept, so nothing the reader could use is missing."""
    path = _single_output_notebook(tmp_path, {
        "output_type": "execute_result", "metadata": {}, "execution_count": 1,
        "data": {"text/plain": ["   a  b"], "text/html": ["<table>"]},
    })

    cells, _ = process_notebook(path)

    assert cells[0].outputs == "a  b"
    assert cells[0].trimmed is True


def test_output_with_empty_data_is_not_reported_as_omitted(
    tmp_path: Path,
) -> None:
    path = _single_output_notebook(tmp_path, {
        "output_type": "display_data", "metadata": {}, "data": {},
    })

    cells, _ = process_notebook(path)

    assert cells[0].outputs is None
    assert cells[0].trimmed is False


# ---------------------------------------------------------------------------
# ANSI coverage (ECMA-48 CSI + OSC)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "noisy",
    [
        "\x1b[?25lhidden cursor\x1b[?25h",
        "\x1b[38;5;208morange\x1b[0m",
        "\x1b[2K\x1b[1Gredraw",
        "\x1b]0;window title\x07shown",
        "\x1b]8;;http://example.com\x1b\\shown\x1b]8;;\x1b\\",
    ],
    ids=["private-mode", "256-color", "erase-line", "osc-bel", "osc-hyperlink"],
)
def test_ansi_stripping_covers_csi_and_osc(tmp_path: Path, noisy: str) -> None:
    path = _single_output_notebook(tmp_path, {
        "output_type": "stream", "name": "stdout", "text": [noisy],
    })

    cells, _ = process_notebook(path)

    assert "\x1b" not in (cells[0].outputs or "")
    assert cells[0].trimmed is False  # stripping alone is not trimming


def test_text_without_escape_is_never_treated_as_ansi(tmp_path: Path) -> None:
    """Every pattern requires ESC: a literal `[1;31m` or `]0;x` stays."""
    path = _single_output_notebook(tmp_path, {
        "output_type": "stream", "name": "stdout",
        "text": ["arr[1;31m] and ]0;x"],
    })

    cells, _ = process_notebook(path)

    assert cells[0].outputs == "arr[1;31m] and ]0;x"


def test_notebook_token_estimate_includes_the_file_note(tmp_path: Path) -> None:
    """The note is printed in the document, so the per-file count (which the
    budget ladder trusts) must include it."""
    path = tmp_path / "nb.ipynb"
    _write_notebook(path, [_code_cell("b", 2), _code_cell("a", 1)])

    result = NotebookParser().parse(path, _status_config())

    assert result.file_note is not None
    cells_only, _ = count_tokens(flatten_ir(result.content))
    assert result.tokens > cells_only
