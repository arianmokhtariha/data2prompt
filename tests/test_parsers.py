import os
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pandas as pd

from src.data2prompt.parsers import (
    process_sql,
    process_csv,
    build_table_schema,
    render_schema_block,
    is_env_file,
    process_env,
    EnvParser,
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
