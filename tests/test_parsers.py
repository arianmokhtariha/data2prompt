import json
import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.data2prompt.parsers import (
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
        cells = process_notebook(path)
        # Both cells must be returned; the global error cell has number=0.
        assert len(cells) == 2
        assert all(c.number != 0 for c in cells)
        assert "print('hello')" in cells[0].source
        # Malformed cell degrades to empty source rather than aborting.
        assert cells[1].source == ""
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
        cells = process_notebook(path)
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


def test_enforce_table_limit_truncates_and_appends_warning() -> None:
    text = "X" * 2000
    result = enforce_table_limit(text, limit=1000, truncate_to=500)
    assert result.startswith("X" * 500)
    assert "Table truncated" in result
    assert "1000 characters" in result


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
        assert table.footer_note is not None and "CSV truncated" in table.footer_note
    finally:
        if os.path.exists(path):
            os.remove(path)


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
        cells = process_notebook(path)
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
        cells = process_notebook(path)
        assert cells[0].outputs is not None
        assert "2" in cells[0].outputs
    finally:
        if os.path.exists(path):
            os.remove(path)


def test_process_notebook_base64_display_data_skipped() -> None:
    """display_data whose text/plain contains 'base64' must be silently dropped."""
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
        cells = process_notebook(path)
        assert cells[0].outputs is None
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
        cells = process_notebook(path, max_lines=5)
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
        cells = process_notebook(path)
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
