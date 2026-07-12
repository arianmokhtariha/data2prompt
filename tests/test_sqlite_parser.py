"""Tests for process_sqlite / SQLiteParser.

Covers the contracts that make the SQLite parser trustworthy:
- one TableIR per table/view, tables first then views, each alphabetical
- CREATE-statement DDL (with index definitions) captured per table
- declared SQLite column types override pandas-inferred dtypes
- the full COUNT(*) is captured BEFORE sampling and cited in the notice
- large tables degrade to a head sample + DDL-only structure (no misleading
  full-dataset stats)
- schema_only drops rows but keeps schema + DDL
- max_tables truncation note
- identifier quoting keeps hostile table names safe (injection guard)
- a .db that is not actually SQLite is skipped, not crashed
"""

import sqlite3
from pathlib import Path
from types import SimpleNamespace

from data2prompt.parsers import SQLiteParser, process_sqlite


def _make_config(
    csv_sample_size: int = 15,
    max_tables: int = 25,
    seed: int = 42,
    stats_summary: bool = True,
    schema_only: bool = False,
) -> SimpleNamespace:
    return SimpleNamespace(
        csv_sample_size=csv_sample_size,
        max_tables=max_tables,
        seed=seed,
        stats_summary=stats_summary,
        schema_only=schema_only,
    )


def _build_db(path: Path) -> None:
    """A small database: two tables (one with FK + index), one view."""
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE regions (id INTEGER PRIMARY KEY, name TEXT NOT NULL)")
    con.execute(
        "CREATE TABLE customers ("
        "id INTEGER PRIMARY KEY, email TEXT NOT NULL UNIQUE, "
        "score REAL, region_id INTEGER REFERENCES regions(id))"
    )
    con.execute("CREATE INDEX idx_cust_region ON customers(region_id)")
    con.execute("CREATE VIEW active AS SELECT id, email FROM customers")
    con.executemany("INSERT INTO regions(name) VALUES (?)", [("EU",), ("US",)])
    con.executemany(
        "INSERT INTO customers(email, score, region_id) VALUES (?, ?, ?)",
        [(f"user{i}@ex.com", float(i), (i % 2) + 1) for i in range(50)],
    )
    con.commit()
    con.close()


# ---------------------------------------------------------------------------
# Table discovery & ordering
# ---------------------------------------------------------------------------

def test_process_sqlite_one_tableir_per_table_tables_before_views(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _build_db(db)

    tables = process_sqlite(db, display_path="app.db")

    # Tables first (alphabetical), then views (alphabetical).
    assert [t.name for t in tables] == ["customers", "regions", "active"]
    assert [t.sheet_number for t in tables] == [1, 2, 3]
    assert all(t.section_label == "Table" for t in tables)
    assert all(t.file_path == "app.db" for t in tables)


def test_process_sqlite_captures_ddl_with_indexes(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _build_db(db)

    tables = {t.name: t for t in process_sqlite(db, display_path="app.db")}

    ddl = tables["customers"].ddl or ""
    assert "CREATE TABLE customers" in ddl
    assert "REFERENCES regions(id)" in ddl          # foreign key preserved
    assert "CREATE INDEX idx_cust_region" in ddl    # index attached to its table


def test_process_sqlite_declared_types_override_pandas(tmp_path: Path) -> None:
    """The schema must show declared SQLite types (INTEGER/TEXT/REAL), not the
    pandas-inferred int64/object/float64."""
    db = tmp_path / "app.db"
    _build_db(db)

    customers = next(t for t in process_sqlite(db) if t.name == "customers")
    dtypes = {c.name: c.dtype for c in customers.schema.columns}

    assert dtypes["id"] == "INTEGER"
    assert dtypes["email"] == "TEXT"
    assert dtypes["score"] == "REAL"


# ---------------------------------------------------------------------------
# Honesty: counts captured before sampling; large tables degrade
# ---------------------------------------------------------------------------

def test_process_sqlite_counts_full_rows_before_sampling(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _build_db(db)

    customers = next(t for t in process_sqlite(db, sample_size=15) if t.name == "customers")

    assert len(customers.df) == 15
    assert customers.schema.row_count == 50               # full count, not sample
    assert "random 15 of 50 rows" in (customers.header_note or "")
    assert "Table truncated" in (customers.footer_note or "")
    # sort_index restores insertion order so the sample reads coherently
    ids = customers.df["id"].tolist()
    assert ids == sorted(ids)


def test_process_sqlite_large_table_degrades_to_head_sample(tmp_path: Path) -> None:
    """Above the full-scan threshold: head sample, DDL-only structure, and an
    honest notice — never sample-derived stats masquerading as full truth."""
    db = tmp_path / "app.db"
    _build_db(db)

    customers = next(
        t for t in process_sqlite(db, sample_size=5, full_scan_max_rows=10)
        if t.name == "customers"
    )

    assert len(customers.df) == 5
    assert customers.schema is None                       # no misleading stats block
    assert customers.ddl is not None                      # structure still available
    assert "first 5 of 50 rows" in (customers.header_note or "")
    assert "full-scan stats omitted" in (customers.footer_note or "")


# ---------------------------------------------------------------------------
# schema_only, truncation, and hostile identifiers
# ---------------------------------------------------------------------------

def test_process_sqlite_schema_only_drops_rows_keeps_schema(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _build_db(db)

    customers = next(
        t for t in process_sqlite(db, schema_only=True) if t.name == "customers"
    )

    assert customers.df.empty
    assert customers.schema is not None
    assert customers.schema.row_count == 50
    assert customers.ddl is not None
    assert "Schema only" in (customers.header_note or "")


def test_process_sqlite_max_tables_truncation_note(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _build_db(db)

    tables = process_sqlite(db, max_tables=2)

    assert len(tables) == 2
    assert "Database truncated" in (tables[-1].footer_note or "")


def test_process_sqlite_quotes_hostile_identifier(tmp_path: Path) -> None:
    """A table name containing a double quote must be handled safely, not
    produce a SQL error (identifier-quoting / injection guard)."""
    db = tmp_path / "weird.db"
    con = sqlite3.connect(db)
    con.execute('CREATE TABLE "odd""name" (x INTEGER)')
    con.execute('INSERT INTO "odd""name"(x) VALUES (1), (2)')
    con.commit()
    con.close()

    tables = process_sqlite(db)

    assert len(tables) == 1
    assert tables[0].name == 'odd"name'
    assert tables[0].schema.row_count == 2
    assert tables[0].footer_note is None or "Error" not in tables[0].footer_note


def test_process_sqlite_empty_database_notes_no_tables(tmp_path: Path) -> None:
    db = tmp_path / "empty.db"
    con = sqlite3.connect(db)
    con.commit()  # create a valid but empty SQLite file
    con.close()

    tables = process_sqlite(db)

    assert len(tables) == 1
    assert "no user tables" in (tables[0].footer_note or "")


# ---------------------------------------------------------------------------
# SQLiteParser wiring & the non-SQLite sniff guard
# ---------------------------------------------------------------------------

def test_sqlite_parser_stats_and_status(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _build_db(db)

    result = SQLiteParser().parse(db, _make_config())

    assert result.status == "Sampled"
    assert result.type == "SQLite (3 tables)"
    assert result.stats_update == {"sqlite_count": 1, "db_tables_count": 3}
    assert result.tokens > 0


def test_sqlite_parser_schema_only_status(tmp_path: Path) -> None:
    db = tmp_path / "app.db"
    _build_db(db)

    result = SQLiteParser().parse(db, _make_config(schema_only=True))

    assert result.status == "Schema Only"
    assert all(t.df.empty for t in result.content)


def test_sqlite_parser_sniff_rejects_non_sqlite(tmp_path: Path) -> None:
    """A .db file that is not a SQLite database is skipped with a binary status,
    not opened (which would raise) and not silently treated as valid."""
    db = tmp_path / "notreally.db"
    db.write_bytes(b"this is definitely not a sqlite database" + b"\x00" * 32)

    result = SQLiteParser().parse(db, _make_config())

    assert result.status == "Skipped (Binary)"
    assert result.stats_update == {"binary_count": 1}
    assert "not a SQLite database" in result.content
