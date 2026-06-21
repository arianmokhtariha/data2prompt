"""
Table-limit enforcement tests.

``process_csv`` and ``process_excel`` no longer accept ``table_limit`` /
``table_truncate``. Those parameters were threaded in from the parser classes but
never used: the character-limit truncation for CSV/Excel tables happens in the
output layer (``enforce_table_limit`` inside the generators), not in the parser.

These tests prove both halves of that claim:
1. the output layer still truncates an oversized table, and
2. the dead parameters are actually gone from the two functions.
"""

import inspect
from types import SimpleNamespace

import pandas as pd

from data2prompt.output import MarkdownGenerator
from data2prompt.parsers import TableIR, process_csv, process_excel


def _oversized_table_ir() -> TableIR:
    """A TableIR whose markdown rendering far exceeds a small char limit."""
    df = pd.DataFrame({"col": ["x" * 100 for _ in range(50)]})
    return TableIR(name="big.csv", df=df)


def test_output_layer_still_enforces_table_limit() -> None:
    """MarkdownGenerator truncates an oversized table via enforce_table_limit."""
    cfg = SimpleNamespace(
        table_limit=1000,
        table_truncate=500,
        stats_summary=False,
        schema_only=False,
    )
    files_data = [
        {
            "path": "data/big.csv",
            "content": [_oversized_table_ir()],
            "type": "CSV",
            "tokens": 0,
            "status": "Sampled",
        }
    ]

    result = MarkdownGenerator().generate(
        project_name="demo",
        tree_text="data/big.csv",
        files_data=files_data,
        stats={},
        config=cfg,
    )

    assert "[Table truncated: Total size exceeded 1000 characters" in result


def test_process_csv_dropped_table_params() -> None:
    """The dead table_limit/table_truncate params are gone from process_csv."""
    params = inspect.signature(process_csv).parameters
    assert "table_limit" not in params
    assert "table_truncate" not in params


def test_process_excel_dropped_table_params() -> None:
    """The dead table_limit/table_truncate params are gone from process_excel."""
    params = inspect.signature(process_excel).parameters
    assert "table_limit" not in params
    assert "table_truncate" not in params


if __name__ == "__main__":
    test_output_layer_still_enforces_table_limit()
    test_process_csv_dropped_table_params()
    test_process_excel_dropped_table_params()
    print("OK: table-limit enforcement tests passed")
