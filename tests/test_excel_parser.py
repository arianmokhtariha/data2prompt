"""Tests for process_excel / ExcelParser.

Covers the contracts that were previously broken or untested:
- one TableIR per sheet, with names and 1-based sheet numbers
- sampling beyond max_rows, with original row order restored
- max_sheets truncation note
- schema_only mode
- visual-element detection via the xlsx zip archive (openpyxl's read-only
  mode never parses drawings, so the old worksheet-attribute check was dead)
- legacy .xls without the optional xlrd engine → actionable note, not a
  generic error dump
"""

import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import openpyxl

from data2prompt.parsers import (
    ExcelParser,
    _xlsx_has_visuals,
    process_excel,
    registry,
)


def _make_config(
    csv_sample_size: int = 15,
    max_sheets: int = 10,
    seed: int = 42,
    stats_summary: bool = True,
    schema_only: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        csv_sample_size=csv_sample_size,
        max_sheets=max_sheets,
        seed=seed,
        stats_summary=stats_summary,
        schema_only=schema_only,
    )


def _write_workbook(path: Path, sheets: dict) -> None:
    """Write an .xlsx with one sheet per {name: list-of-rows} entry.

    The first row of each sheet is treated as the header by pandas.
    """
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, rows in sheets.items():
        ws = wb.create_sheet(title=name)
        for row in rows:
            ws.append(row)
    wb.save(path)


def _inject_fake_image(xlsx_path: Path) -> None:
    """Append a fake media entry to the xlsx archive to simulate an embedded
    image. Extra archive members are ignored by openpyxl/pandas readers."""
    with zipfile.ZipFile(xlsx_path, "a") as archive:
        archive.writestr("xl/media/image1.png", b"\x89PNG fake")


# ---------------------------------------------------------------------------
# Basic multi-sheet extraction
# ---------------------------------------------------------------------------

def test_process_excel_one_table_per_sheet(tmp_path: Path) -> None:
    path = tmp_path / "book.xlsx"
    _write_workbook(path, {
        "Sales": [["id", "amount"], [1, 10.0], [2, 20.0]],
        "Costs": [["id", "cost"], [1, 5.0]],
    })

    tables = process_excel(path, display_path="book.xlsx")

    assert [t.name for t in tables] == ["Sales", "Costs"]
    assert [t.sheet_number for t in tables] == [1, 2]
    assert list(tables[0].df.columns) == ["id", "amount"]
    assert len(tables[1].df) == 1


def test_process_excel_sampling_preserves_sheet_order(tmp_path: Path) -> None:
    path = tmp_path / "big.xlsx"
    rows = [["id", "value"]] + [[i, f"v{i}"] for i in range(100)]
    _write_workbook(path, {"Data": rows})

    tables = process_excel(path, max_rows=10, seed=42)

    df = tables[0].df
    assert len(df) == 10
    ids = df["id"].tolist()
    assert ids == sorted(ids), "sampled rows are not in original sheet order"
    assert tables[0].header_note is not None and "Sample" in tables[0].header_note
    assert tables[0].footer_note is not None and "Sheet truncated" in tables[0].footer_note


def test_process_excel_max_sheets_truncation_note(tmp_path: Path) -> None:
    path = tmp_path / "many.xlsx"
    _write_workbook(path, {
        f"S{i}": [["col"], [i]] for i in range(1, 5)
    })

    tables = process_excel(path, max_sheets=2)

    assert len(tables) == 2
    assert "Workbook truncated" in (tables[-1].footer_note or "")


def test_xlsm_routes_to_excel_parser_and_reads_correctly(tmp_path: Path) -> None:
    """.xlsm (macro-enabled Excel) is the same OOXML zip container as .xlsx
    and needs no extra dependency — it must be registered to ExcelParser
    rather than falling through to the binary-detecting DefaultParser."""
    path = tmp_path / "book.xlsm"
    _write_workbook(path, {"Sales": [["id", "amount"], [1, 10.0], [2, 20.0]]})

    assert isinstance(registry.get_parser(".xlsm"), ExcelParser)

    tables = process_excel(path, display_path="book.xlsm")
    assert tables[0].name == "Sales"
    assert list(tables[0].df.columns) == ["id", "amount"]

    result = ExcelParser().parse(path, _make_config())
    assert result.status == "Extracted"
    assert result.stats_update == {"excel_count": 1, "excel_sheets_count": 1}


def test_xlsm_visual_detection_uses_same_zip_probe(tmp_path: Path) -> None:
    path = tmp_path / "dashboard.xlsm"
    _write_workbook(path, {"Data": [["col"], [1]]})
    _inject_fake_image(path)

    tables = process_excel(path)

    assert "visual elements" in (tables[0].header_note or "")


def test_process_excel_max_sheets_zero_still_emits_a_notice(tmp_path: Path) -> None:
    """max_sheets=0 hits the truncation branch before any TableIR exists to
    attach the note to. It must not silently return an empty list — output.py
    renders TableIR lists specially, and an empty list would fall through
    to its plain-string fallback and print a bare "[]" with no explanation."""
    path = tmp_path / "many2.xlsx"
    _write_workbook(path, {"Sales": [["id"], [1]], "Costs": [["id"], [2]]})

    tables = process_excel(path, max_sheets=0)

    assert len(tables) == 1
    assert "Workbook truncated" in (tables[0].footer_note or "")
    assert tables[0].df.empty


def test_process_excel_schema_only_drops_rows_keeps_schema(tmp_path: Path) -> None:
    path = tmp_path / "schema.xlsx"
    _write_workbook(path, {"Data": [["id", "name"], [1, "alice"], [2, "bob"]]})

    tables = process_excel(path, schema_only=True)

    table = tables[0]
    assert table.df.empty
    assert table.schema is not None
    assert table.schema.row_count == 2
    assert {c.name for c in table.schema.columns} == {"id", "name"}


# ---------------------------------------------------------------------------
# Visual-element detection (zip-archive based)
# ---------------------------------------------------------------------------

def test_xlsx_has_visuals_detects_media_entry(tmp_path: Path) -> None:
    path = tmp_path / "visuals.xlsx"
    _write_workbook(path, {"Data": [["col"], [1]]})
    assert _xlsx_has_visuals(path) is False

    _inject_fake_image(path)
    assert _xlsx_has_visuals(path) is True


def test_xlsx_has_visuals_on_non_zip_returns_false(tmp_path: Path) -> None:
    path = tmp_path / "corrupt.xlsx"
    path.write_bytes(b"this is not a zip archive")
    assert _xlsx_has_visuals(path) is False


def test_process_excel_emits_visual_note_once_on_first_sheet(tmp_path: Path) -> None:
    path = tmp_path / "dashboard.xlsx"
    _write_workbook(path, {
        "First": [["col"], [1]],
        "Second": [["col"], [2]],
    })
    _inject_fake_image(path)

    tables = process_excel(path)

    assert "visual elements" in (tables[0].header_note or "")
    assert "visual elements" not in (tables[1].header_note or "")


# ---------------------------------------------------------------------------
# Legacy .xls without the optional xlrd engine
# ---------------------------------------------------------------------------

def test_xls_without_xlrd_yields_actionable_note(tmp_path: Path) -> None:
    """pandas raises ImportError for .xls when xlrd is missing; the parser must
    surface an install hint instead of a stack-trace error note."""
    path = tmp_path / "legacy.xls"
    path.write_bytes(b"\xd0\xcf\x11\xe0 fake BIFF header")

    with patch(
        "data2prompt.parsers.pd.ExcelFile",
        side_effect=ImportError("Missing optional dependency 'xlrd'"),
    ):
        tables = process_excel(path)

    assert len(tables) == 1
    assert tables[0].df.empty
    note = tables[0].footer_note or ""
    assert "xlrd" in note
    assert "pip install xlrd" in note


# ---------------------------------------------------------------------------
# ExcelParser wiring
# ---------------------------------------------------------------------------

def test_excel_parser_stats_and_status(tmp_path: Path) -> None:
    path = tmp_path / "wired.xlsx"
    _write_workbook(path, {
        "A": [["x"], [1]],
        "B": [["y"], [2]],
    })

    result = ExcelParser().parse(path, _make_config())

    assert result.status == "Extracted"
    assert result.type == "Excel (2 sheets)"
    assert result.stats_update == {"excel_count": 1, "excel_sheets_count": 2}
    assert result.tokens > 0
