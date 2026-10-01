"""Sample-table rendering, row-safe table truncation, and the stable prefix.

The table text (notices + sample rows) is rendered by one shared helper, so
both generators emit it identically and ``flatten_ir`` counts the same text
the document carries. These tests pin the contracts that helper exists for:
values render faithfully (no fake columns, split rows, ``nan`` or rounding),
an oversized table is cut at a row boundary with its notices intact, and the
run-varying timestamp sits in the end anchor, not in the document prefix.
"""

import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import List

import numpy as np
import pandas as pd
import pytest

from data2prompt.output import MarkdownGenerator, OutputGenerator, XMLGenerator
from data2prompt.parsers import (
    TableIR,
    build_table_schema,
    enforce_table_limit,
    flatten_ir,
    process_sql,
    render_sample_table,
    render_schema_block,
)

GENERATORS: List[OutputGenerator] = [MarkdownGenerator(), XMLGenerator()]

# One row per defect of the old tabulate rendering: a '|' that added fake
# columns, embedded newlines (LF and CRLF) that split a row, a missing value
# that printed as 'nan', and floats that floatfmt="g" rounded to 6 digits.
# float32 guards the fix itself: widened to a Python float, 0.1 would print
# as 0.10000000149011612.
_TRICKY_DF = pd.DataFrame({
    "id": [1, 2, 3],
    "note": ["a | b | c", "line1\r\nline2\nline3", np.nan],
    "score": [102479.81746, np.nan, 1.23456789],
    "ratio": np.array([0.1, 0.25, np.nan], dtype="float32"),
})
_TRICKY_TABLE_TEXT = "\n".join([
    "| id | note | score | ratio |",
    "|---|---|---|---|",
    "| 1 | a \\| b \\| c | 102479.81746 | 0.1 |",
    "| 2 | line1↵line2↵line3 | | 0.25 |",
    "| 3 | | 1.23456789 | |",
])


def _config(
    table_limit: int = 50_000, table_truncate: int = 20_000
) -> SimpleNamespace:
    return SimpleNamespace(
        table_limit=table_limit,
        table_truncate=table_truncate,
        stats_summary=False,
        schema_only=False,
        env_keys=True,
    )


def _render_table(
    generator: OutputGenerator, table: TableIR, config: SimpleNamespace
) -> str:
    """Render one CSV file holding ``table``; return the part after the preamble."""
    output = generator.generate(
        project_name="demo",
        tree_text="data/t.csv",
        files_data=[{
            "path": "data/t.csv",
            "content": [table],
            "type": "CSV",
            "tokens": 0,
            "status": "Sampled",
        }],
        stats={"csv_count": 1},
        config=config,
    )
    # Preamble-collision rule: scope past the preamble before asserting.
    if isinstance(generator, MarkdownGenerator):
        return output.split("# Files", 1)[1]
    return output.split("</purpose>", 1)[1]


# ---------------------------------------------------------------------------
# Item 3: faithful sample rows, identical in both formats and in the estimate
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
def test_sample_rows_render_faithfully(generator: OutputGenerator) -> None:
    """Pipes escaped, newlines marked, missing values empty, floats unrounded,
    and no alignment padding, in both formats."""
    table = TableIR(name="t.csv", df=_TRICKY_DF)
    body = _render_table(generator, table, _config())
    assert _TRICKY_TABLE_TEXT in body


def test_flatten_ir_counts_the_rendered_table_text() -> None:
    """The per-file token estimate must count the same table text the
    generators emit, not a differently formatted stand-in."""
    flattened = flatten_ir([TableIR(name="t.csv", df=_TRICKY_DF)])
    assert _TRICKY_TABLE_TEXT in flattened


def test_empty_and_blank_strings_are_distinct_from_missing() -> None:
    """The preamble says an empty cell is a missing value, so an empty or
    whitespace-only STRING must render differently from NaN, in sample rows
    and in the schema block's describe() `top` value alike."""
    df = pd.DataFrame({"s": ["", "   ", np.nan, "x"], "t": ["", "", "", ""]})
    sample = render_sample_table(df).split("\n")
    assert sample[2:] == [
        '| "" | "" |',
        '| "   " | "" |',
        '| | "" |',
        '| x | "" |',
    ]

    schema = build_table_schema(df, include_describe=True)
    block = render_schema_block(schema, show_missing=True, show_describe=True)
    t_row = next(line for line in block.split("\n") if line.startswith("| t |"))
    assert '| "" |' in t_row  # top of the all-empty column is "", not missing


def test_schema_block_escapes_pipes_in_names_and_values() -> None:
    """A '|' in a column name or a describe() value (e.g. `top`) must not add
    columns to the schema table: every row keeps the header's cell count."""
    df = pd.DataFrame({"a|b": ["x | y", "x | y", "z"]})
    schema = build_table_schema(df, include_describe=True)

    block = render_schema_block(schema, show_missing=True, show_describe=True)

    table_rows = [line for line in block.split("\n") if line.startswith("|")]
    unescaped_pipes = [len(re.findall(r"(?<!\\)\|", row)) for row in table_rows]
    assert len(set(unescaped_pipes)) == 1
    assert "| a\\|b |" in block
    assert "x \\| y" in block


# ---------------------------------------------------------------------------
# Item 7: row-safe truncation that keeps both notices
# ---------------------------------------------------------------------------

_ROW = re.compile(r"^\| \d+ \| x{100} \|$")
_TRUNCATED = re.compile(r"^-- \[Table truncated: showing first (\d+) of 50 rows; ")


@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
def test_oversized_table_is_cut_at_a_row_boundary(
    generator: OutputGenerator,
) -> None:
    """The cap applies to the rendered rows only: every kept row is whole,
    the notice cites kept/total rows, and header and footer notes survive."""
    header_note = "-- [Sample: random 50 of 900 rows] --"
    footer_note = "-- [Note: footer sentinel] --"
    table = TableIR(
        name="t.csv",
        df=pd.DataFrame({"id": range(50), "text": ["x" * 100] * 50}),
        header_note=header_note,
        footer_note=footer_note,
    )

    lines = _render_table(generator, table, _config(1_000, 500)).split("\n")

    start = lines.index(header_note)
    assert lines[start + 1:start + 3] == ["| id | text |", "|---|---|"]
    notice_at = next(i for i, line in enumerate(lines) if _TRUNCATED.match(line))
    rows = lines[start + 3:notice_at]
    assert rows and all(_ROW.match(row) for row in rows)
    assert int(_TRUNCATED.match(lines[notice_at]).group(1)) == len(rows)
    assert len("\n".join(lines[start + 1:notice_at])) <= 500
    assert lines[notice_at + 1] == footer_note


def test_enforce_table_limit_cuts_raw_rows_at_a_line_boundary() -> None:
    """The SQL path caps raw INSERT lines: no line may be cut mid-row."""
    rows = [f"INSERT INTO t VALUES ({i}, 'value {i}');" for i in range(100)]
    text = "".join(f"{row}\n" for row in rows)

    result = enforce_table_limit(text, limit=1_000, truncate_to=500)

    *kept, notice = result.split("\n")
    assert kept == rows[:len(kept)]
    assert len("\n".join(kept)) <= 500
    assert notice.startswith(
        f"-- [Table truncated: showing first {len(kept)} of 100 rows"
    )


# ---------------------------------------------------------------------------
# Item 13: the timestamp lives in the end anchor, keeping the prefix stable
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("generator", "anchor", "stamp"),
    [
        (MarkdownGenerator(), "# End of codebase: demo", "> Generated on: "),
        (XMLGenerator(), "<end_of_codebase>", "<generated_on>"),
    ],
    ids=["markdown", "xml"],
)
def test_generation_timestamp_is_in_the_end_anchor(
    generator: OutputGenerator, anchor: str, stamp: str
) -> None:
    """Nothing run-varying may precede the end anchor, or a regenerated
    prompt for an unchanged project never hits a provider prompt cache."""
    output = generator.generate(
        project_name="demo",
        tree_text="src/app.py",
        files_data=[{
            "path": "src/app.py",
            "content": "print('hi')\n",
            "type": "py",
            "tokens": 0,
            "status": "Read",
        }],
        stats={},
    )
    prefix, end_section = output.rsplit(anchor, 1)
    assert stamp not in prefix
    assert re.search(re.escape(stamp) + r"\d{4}-\d\d-\d\d \d\d:\d\d", end_section)


def test_per_file_estimate_applies_the_table_cap() -> None:
    """flatten_ir feeds the terminal ranking and the --budget omission order,
    so it must count the capped text the document carries, not the full table."""
    table = TableIR(
        name="t.csv",
        df=pd.DataFrame({"id": range(50), "text": ["x" * 100] * 50}),
    )
    uncapped = flatten_ir([table])
    capped = flatten_ir([table], table_limit=1_000, table_truncate=500)

    assert "Table truncated" not in uncapped
    assert "Table truncated" in capped
    assert len(capped) < len(uncapped) / 2


# ---------------------------------------------------------------------------
# Truncation notice: truthful, grammatical, and only when something was cut
# ---------------------------------------------------------------------------

def test_no_truncation_notice_when_nothing_was_cut() -> None:
    """truncate_to >= limit keeps every row; a 'showing first 10 of 10 rows'
    notice would claim a cut that never happened."""
    text = "\n".join(f"row {i}" for i in range(10))
    assert enforce_table_limit(text, limit=20, truncate_to=1_000) == text


def test_truncation_notice_grammar_and_separators() -> None:
    """Counts use thousands separators, a single over-long row reads
    '0 of 1 row', and raw SQL lines are called lines, not rows."""
    many = "\n".join(f"row {i}" for i in range(1_500))
    notice = enforce_table_limit(many, limit=100, truncate_to=50).split("\n")[-1]
    assert " of 1,500 rows;" in notice

    single = enforce_table_limit("x" * 300, limit=100, truncate_to=50)
    assert "showing first 0 of 1 row;" in single

    lines = enforce_table_limit(many, limit=100, truncate_to=50, noun="line")
    assert " of 1,500 lines;" in lines.split("\n")[-1]


def test_sql_truncation_notice_counts_lines_not_rows(tmp_path: Path) -> None:
    """A multi-row INSERT's header line is not a data row, so the notice
    must count lines instead of overclaiming rows."""
    rows = ",\n".join(f"({i}, '{'v' * 40}')" for i in range(30))
    sql = tmp_path / "dump.sql"
    sql.write_text(f"INSERT INTO t VALUES\n{rows};\n", encoding="utf-8")

    result = process_sql(sql, sample_size=100, table_limit=300, table_truncate=150)

    assert re.search(r"showing first \d+ of 31 lines;", result)
    assert " rows;" not in result


def _py_file(path: str, content: str) -> dict:
    return {"path": path, "content": content, "type": "py", "tokens": 0,
            "status": "Read"}


@pytest.mark.parametrize(
    ("generator", "last_file_marker"),
    [(MarkdownGenerator(), "## File: z.py"), (XMLGenerator(), '<file path="z.py"')],
    ids=["markdown", "xml"],
)
def test_one_line_edit_keeps_everything_before_that_file_identical(
    generator: OutputGenerator, last_file_marker: str
) -> None:
    """The token total changes on any edit, so it must sit in the end anchor:
    placed after the preamble it would end the cacheable prefix there."""
    def render(last_line: str) -> str:
        return generator.generate(
            project_name="demo",
            tree_text="a.py\nz.py",
            files_data=[_py_file("a.py", "x = 1\n"), _py_file("z.py", last_line)],
            stats={},
        )

    old, new = render("y = 1\n"), render("y = 2\n")
    shared = len(os.path.commonprefix([old, new]))
    assert shared >= old.index(last_file_marker)
    assert "{{TOTAL_TOKENS}}" not in old[:shared]


@pytest.mark.parametrize(
    ("generator", "anchor", "stamp"),
    [
        (MarkdownGenerator(), "# End of codebase: demo", "> Tokens: "),
        (XMLGenerator(), "<end_of_codebase>", "<total_tokens "),
    ],
    ids=["markdown", "xml"],
)
def test_token_total_is_in_the_end_anchor(
    generator: OutputGenerator, anchor: str, stamp: str
) -> None:
    output = generator.generate(
        project_name="demo", tree_text="a.py", files_data=[_py_file("a.py", "x\n")],
        stats={},
    )
    prefix, end_section = output.rsplit(anchor, 1)
    assert stamp not in prefix
    assert stamp in end_section
    assert "{{TOTAL_TOKENS}}" in end_section


# ---------------------------------------------------------------------------
# The cell-convention bullet appears only when its content does
# ---------------------------------------------------------------------------

_CELL_BULLET = "is a missing value"


@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
@pytest.mark.parametrize(
    ("df", "schema_only", "expected"),
    [
        (pd.DataFrame({"a": [1]}), False, True),
        (pd.DataFrame({"a": [1]}), True, False),
        (pd.DataFrame(), False, False),
    ],
    ids=["sample-rows", "schema-only", "no-rows"],
)
def test_cell_convention_bullet_follows_rendered_sample_rows(
    generator: OutputGenerator, df: pd.DataFrame, schema_only: bool, expected: bool
) -> None:
    config = _config()
    config.schema_only = schema_only
    output = generator.generate(
        project_name="demo",
        tree_text="data/t.csv",
        files_data=[{
            "path": "data/t.csv",
            "content": [TableIR(name="t.csv", df=df)],
            "type": "CSV",
            "tokens": 0,
            "status": "Sampled",
        }],
        stats={"csv_count": 1},
        config=config,
    )
    end_of_preamble = "</purpose>" if "<purpose>" in output else "# File Index"
    preamble = output.split(end_of_preamble)[0]
    assert (_CELL_BULLET in preamble) is expected
