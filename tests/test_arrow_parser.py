"""Tests for ArrowParser — .parquet, .feather, and .arrow support.

Covers:
- Happy path: all three formats are read, sampled, and produce a valid TableIR.
- schema_only mode: data rows are dropped, schema is populated from pyarrow types.
- Missing-dependency path: when pyarrow is not importable, the parser returns a
  descriptive note with status "Skipped (No pyarrow)" and no stats update.
"""

import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from typing import List
from unittest.mock import patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Skip the entire module if pyarrow is not installed.  The happy-path and
# schema-only tests need it to write fixture files; only the missing-dep test
# can run without it.
# ---------------------------------------------------------------------------
pyarrow = pytest.importorskip("pyarrow", reason="pyarrow not installed")
import pyarrow as pa
import pyarrow.feather as pf
import pyarrow.parquet as pq

from data2prompt.parsers import ArrowParser, process_arrow_file


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_config(
    csv_sample_size: int = 15,
    seed: int = 42,
    stats_summary: bool = True,
    schema_only: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        csv_sample_size=csv_sample_size,
        seed=seed,
        stats_summary=stats_summary,
        schema_only=schema_only,
    )


def _sample_table() -> pa.Table:
    """Return a small pyarrow Table with mixed types for fixture use."""
    return pa.table({
        "id": pa.array([1, 2, 3, 4, 5], type=pa.int32()),
        "name": pa.array(["alice", "bob", "carol", "dave", "eve"], type=pa.string()),
        "score": pa.array([1.1, 2.2, 3.3, 4.4, 5.5], type=pa.float64()),
    })


def _large_table(n: int = 30) -> pa.Table:
    """Return a table with enough rows to trigger sampling."""
    return pa.table({
        "x": pa.array(list(range(n)), type=pa.int64()),
        "y": pa.array([float(i) * 0.5 for i in range(n)], type=pa.float32()),
    })


# ---------------------------------------------------------------------------
# Fixtures — one temp file per format
# ---------------------------------------------------------------------------

@pytest.fixture()
def parquet_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.parquet"
    pq.write_table(_sample_table(), path)
    return path


@pytest.fixture()
def feather_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.feather"
    pf.write_feather(_sample_table(), path)
    return path


@pytest.fixture()
def arrow_file(tmp_path: Path) -> Path:
    path = tmp_path / "data.arrow"
    with pa.ipc.new_file(path, _sample_table().schema) as writer:
        writer.write_table(_sample_table())
    return path


# ---------------------------------------------------------------------------
# Happy path — all three formats
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["parquet", "feather", "arrow"])
def test_happy_path_returns_one_table_ir(fmt: str, parquet_file: Path, feather_file: Path, arrow_file: Path) -> None:
    """Each format produces exactly one TableIR with the expected shape."""
    file_map = {"parquet": parquet_file, "feather": feather_file, "arrow": arrow_file}
    path = file_map[fmt]
    config = _make_config()

    result = ArrowParser().parse(path, config)

    assert result.status == "Sampled"
    assert result.type == fmt.upper()
    assert isinstance(result.content, list)
    assert len(result.content) == 1

    table_ir = result.content[0]
    assert not table_ir.df.empty
    assert list(table_ir.df.columns) == ["id", "name", "score"]


@pytest.mark.parametrize("fmt", ["parquet", "feather", "arrow"])
def test_happy_path_stats_update(fmt: str, parquet_file: Path, feather_file: Path, arrow_file: Path) -> None:
    """stats_update carries the correct per-format key."""
    file_map = {"parquet": parquet_file, "feather": feather_file, "arrow": arrow_file}
    path = file_map[fmt]
    config = _make_config()

    result = ArrowParser().parse(path, config)

    assert result.stats_update == {f"{fmt}_count": 1}


@pytest.mark.parametrize("fmt", ["parquet", "feather", "arrow"])
def test_happy_path_pyarrow_dtypes_in_schema(fmt: str, parquet_file: Path, feather_file: Path, arrow_file: Path) -> None:
    """ColumnSchema.dtype must reflect the native pyarrow type, not pandas-inferred."""
    file_map = {"parquet": parquet_file, "feather": feather_file, "arrow": arrow_file}
    path = file_map[fmt]
    config = _make_config(stats_summary=True)

    result = ArrowParser().parse(path, config)
    schema = result.content[0].schema

    assert schema is not None
    by_name = {c.name: c for c in schema.columns}

    # "id" was written as int32 — pyarrow reports it as "int32", not pandas "int32" either
    # but the key test is that it is NOT the pandas alias (which could differ).
    assert "int32" in by_name["id"].dtype
    assert "double" in by_name["score"].dtype or "float64" in by_name["score"].dtype


def test_sampling_is_applied_when_rows_exceed_sample_size(tmp_path: Path) -> None:
    """When the file has more rows than csv_sample_size, a sample is taken."""
    path = tmp_path / "large.parquet"
    pq.write_table(_large_table(30), path)
    config = _make_config(csv_sample_size=10)

    result = ArrowParser().parse(path, config)

    table_ir = result.content[0]
    assert len(table_ir.df) == 10
    assert table_ir.header_note is not None
    assert "Sample" in table_ir.header_note
    assert table_ir.footer_note is not None
    assert "PARQUET truncated" in table_ir.footer_note


def test_duplicate_field_names_do_not_crash(tmp_path: Path) -> None:
    """Arrow schemas (unlike pandas DataFrames from CSV/Excel) permit duplicate
    field names. .to_pandas() carries the duplicate straight through, so this
    must render the file instead of collapsing it to a read-error note."""
    path = tmp_path / "dup.feather"
    table = pa.table({
        "a": pa.array([1, 2, 3], type=pa.int64()),
        "b": pa.array([4.0, None, 6.0], type=pa.float64()),
    })
    table = table.append_column("a", pa.array([7, 8, 9], type=pa.int64()))
    pf.write_feather(table, path)
    config = _make_config(stats_summary=True)

    result = ArrowParser().parse(path, config)

    assert result.status == "Sampled"
    table_ir = result.content[0]
    assert table_ir.footer_note is None
    assert list(table_ir.df.columns) == ["a", "b", "a"]
    assert table_ir.schema is not None
    assert [c.name for c in table_ir.schema.columns] == ["a", "b", "a"]
    # Positionally-correct pyarrow dtypes for both same-named columns.
    assert table_ir.schema.columns[0].dtype == "int64"
    assert table_ir.schema.columns[2].dtype == "int64"


def test_no_sampling_when_rows_within_limit(tmp_path: Path) -> None:
    """When the file has fewer rows than sample_size, the full table is returned."""
    path = tmp_path / "small.parquet"
    pq.write_table(_sample_table(), path)  # 5 rows
    config = _make_config(csv_sample_size=15)

    result = ArrowParser().parse(path, config)

    table_ir = result.content[0]
    assert len(table_ir.df) == 5
    assert table_ir.header_note is None
    assert table_ir.footer_note is None


# ---------------------------------------------------------------------------
# schema_only mode
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("fmt", ["parquet", "feather", "arrow"])
def test_schema_only_drops_data_rows(fmt: str, parquet_file: Path, feather_file: Path, arrow_file: Path) -> None:
    """schema_only mode returns an empty DataFrame with a populated schema."""
    file_map = {"parquet": parquet_file, "feather": feather_file, "arrow": arrow_file}
    path = file_map[fmt]
    config = _make_config(schema_only=True)

    result = ArrowParser().parse(path, config)

    assert result.status == "Schema Only"
    table_ir = result.content[0]
    assert table_ir.df.empty
    assert table_ir.schema is not None
    # Schema is computed on the FULL file (5 rows), not the sample.
    assert table_ir.schema.row_count == 5
    assert {c.name for c in table_ir.schema.columns} == {"id", "name", "score"}


@pytest.mark.parametrize("fmt", ["parquet", "feather", "arrow"])
def test_schema_only_preserves_pyarrow_dtypes(fmt: str, parquet_file: Path, feather_file: Path, arrow_file: Path) -> None:
    """schema_only mode must still report pyarrow-exact dtype strings."""
    file_map = {"parquet": parquet_file, "feather": feather_file, "arrow": arrow_file}
    path = file_map[fmt]
    config = _make_config(schema_only=True)

    result = ArrowParser().parse(path, config)
    schema = result.content[0].schema

    by_name = {c.name: c for c in schema.columns}
    assert "int32" in by_name["id"].dtype


# ---------------------------------------------------------------------------
# Missing-dependency path (pyarrow not installed)
# ---------------------------------------------------------------------------

def test_missing_pyarrow_returns_skip_note(tmp_path: Path) -> None:
    """When pyarrow cannot be imported, the file appears in output with a note."""
    # Write a real parquet file so the path exists; the parser should never read it.
    path = tmp_path / "data.parquet"
    pq.write_table(_sample_table(), path)
    config = _make_config()

    # Setting a module's sys.modules entry to None makes `import` raise
    # ImportError — the documented way to simulate a missing dependency.
    with patch.dict(sys.modules, {"pyarrow": None}):
        result = ArrowParser().parse(path, config)

    assert result.status == "Skipped (No pyarrow)"
    assert result.skip_file is False            # file still appears in output
    assert "pyarrow" in result.content          # inline note mentions the reason
    assert result.stats_update == {}             # no count incremented


def test_missing_pyarrow_tokens_are_nonzero(tmp_path: Path) -> None:
    """The skip note must carry a token count so the summary table is accurate."""
    path = tmp_path / "data.feather"
    pf.write_feather(_sample_table(), path)
    config = _make_config()

    with patch.dict(sys.modules, {"pyarrow": None}):
        result = ArrowParser().parse(path, config)

    assert result.tokens > 0
