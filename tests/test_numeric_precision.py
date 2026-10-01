"""Numeric precision caps: float rounding with a significance guard.

Float statistics round to ``--stats-decimals`` and float sample values to
``--data-decimals``; small magnitudes keep at least four significant digits;
every non-float value renders untouched. One helper (``format_float``) owns the
rule, the cell formatter applies it to floats only, both generators and the
token estimate share it, and the preamble states the configured caps.
"""

import sys
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import List
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

import data2prompt.parsers as parsers
from data2prompt.cli import setup_cli
from data2prompt.output import MarkdownGenerator, OutputGenerator, XMLGenerator
from data2prompt.parsers import (
    CSVParser,
    TableIR,
    _tabular_status,
    flatten_ir,
    render_sample_table,
)
from data2prompt.utils import count_tokens

GENERATORS: List[OutputGenerator] = [MarkdownGenerator(), XMLGenerator()]

_LONG_VALUE = 97.68560353337905
_SMALL_VALUE = 0.0000123456


# ---------------------------------------------------------------------------
# The rounding helper
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    ("value", "decimals", "expected"),
    [
        (97.68560353337905, 6, "97.685604"),
        (0.5303300858899106, 4, "0.5303"),
        (102479.81746031746, 4, "102479.8175"),
        (0.0000123456, 4, "1.235e-05"),     # significance guard, not 0.0
        (-0.0000123456, 4, "-1.235e-05"),
        (-97.68560353337905, 4, "-97.6856"),
        (2.0, 4, "2.0"),                    # no trailing zeros added
        (0.0, 4, "0.0"),                    # no log10(0)
        (1e300, 4, "1e+300"),               # huge magnitude is left alone
        (1.5e-300, 4, "1.5e-300"),
        (float("inf"), 4, "inf"),
        (float("-inf"), 4, "-inf"),
        (97.68560353337905, 17, "97.68560353337905"),  # large cap: full float64
        (97.68560353337905, 0, "98.0"),     # cap applies to values >= 1
        (3.14159, 2, "3.14"),               # the guard never weakens the cap
        (1.0, 0, "1.0"),
        (0.99996, 4, "1.0"),                # rounds up across the 1 boundary
        (0.00034, 2, "0.00034"),            # guard: 4 significant digits
        (-0.00034, 2, "-0.00034"),
        (2.5, 0, "2.0"),                    # ties round half to even
    ],
)
def test_format_float_applies_cap_and_significance_guard(
    value: float, decimals: int, expected: str
) -> None:
    assert parsers.format_float(value, decimals) == expected


# ---------------------------------------------------------------------------
# Which values are rounded
# ---------------------------------------------------------------------------

def test_only_float_values_are_rounded() -> None:
    """Integers, bools, datetimes, timedeltas, strings (numeric-looking text
    included), bytes and Decimal keep their exact text; floats of every
    flavor (float64, float32, pandas nullable Float64) are rounded."""
    df = pd.DataFrame({
        "i": [123456789012345678],
        "b": [True],
        "when": [datetime(2024, 1, 2, 3, 4, 5, 678901)],
        "span": [timedelta(seconds=1.23456789)],
        "text": ["3.14159265358979"],
        "raw": [b"1.23456789"],
        "dec": [Decimal("1.23456789012")],
        "f64": [_LONG_VALUE],
        "f32": np.array([0.1], dtype="float32"),
        "nullable": pd.array([_LONG_VALUE], dtype="Float64"),
    })
    row = render_sample_table(df, data_decimals=4).split("\n")[2]
    cells = [cell.strip() for cell in row.strip("|").split("|")]
    assert cells == [
        "123456789012345678",
        "True",
        "2024-01-02 03:04:05.678901",
        "0 days 00:00:01.234568",
        "3.14159265358979",
        "b'1.23456789'",
        "1.23456789012",
        "97.6856",
        "0.1",
        "97.6856",
    ]


def test_float32_keeps_its_shortest_form_under_a_large_cap() -> None:
    """A float32 0.1 widened to float64 is 0.10000000149011612; the cap must
    not resurrect those digits."""
    df = pd.DataFrame({"f32": np.array([0.1], dtype="float32")})
    assert render_sample_table(df, data_decimals=17).split("\n")[2] == "| 0.1 |"


def test_missing_float_stays_an_empty_cell() -> None:
    df = pd.DataFrame({"x": [1.5, np.nan], "n": pd.array([None, 2.5], "Float64")})
    rows = render_sample_table(df, data_decimals=2).split("\n")[2:]
    assert rows == ["| 1.5 | |", "| | 2.5 |"]


# ---------------------------------------------------------------------------
# End to end: process_csv, both generators, the estimate, the flags
# ---------------------------------------------------------------------------

def _config(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = dict(
        csv_sample_size=15,
        seed=42,
        stats_summary=True,
        schema_only=False,
        table_limit=50_000,
        table_truncate=20_000,
        stats_decimals=4,
        data_decimals=6,
        env_keys=True,
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _render(
    generator: OutputGenerator, tmp_path: Path, config: SimpleNamespace
) -> str:
    """Parse a one-column float CSV and render the whole document."""
    csv = tmp_path / "t.csv"
    csv.write_text(f"x\n{_SMALL_VALUE!r}\n{_LONG_VALUE!r}\n0.5\n")
    result = CSVParser().parse(csv, config)  # type: ignore[arg-type]
    return generator.generate(
        project_name="demo",
        tree_text="t.csv",
        files_data=[{
            "path": "t.csv",
            "content": result.content,
            "type": "CSV",
            "tokens": result.tokens,
            "status": "Sampled",
        }],
        stats={"csv_count": 1},
        config=config,  # type: ignore[arg-type]
    )


@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
def test_sample_row_and_statistic_use_their_own_caps(
    generator: OutputGenerator, tmp_path: Path
) -> None:
    output = _render(generator, tmp_path, _config())
    assert _LONG_VALUE.__repr__() not in output
    # Sample row: data cap (6). Stats max: stats cap (4).
    assert "| 97.685604 |" in output
    stats_row = next(line for line in output.split("\n") if line.startswith("| x |"))
    assert "| 97.6856 |" in stats_row
    assert "97.685604" not in stats_row
    # The significance guard keeps the tiny value in both places.
    assert "| 1.235e-05 |" in output


@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
def test_caps_change_the_output(
    generator: OutputGenerator, tmp_path: Path
) -> None:
    precise = _render(generator, tmp_path, _config(data_decimals=17))
    assert f"| {_LONG_VALUE!r} |" in precise
    precise_stats = next(
        line for line in precise.split("\n") if line.startswith("| x |")
    )
    assert "| 32.7285 |" in precise_stats
    coarse = _render(
        generator, tmp_path, _config(stats_decimals=0, data_decimals=0)
    )
    coarse_stats = next(
        line for line in coarse.split("\n") if line.startswith("| x |")
    )
    # At 0 decimals values >= 1 are rounded to whole numbers.
    assert "| 33.0 |" in coarse_stats
    assert "| 98.0 |" in coarse


@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
def test_token_estimate_counts_the_rounded_text(
    generator: OutputGenerator, tmp_path: Path
) -> None:
    """flatten_ir must use the same caps as the generators: every line it
    produces appears in the rendered document, and different caps give
    different (smaller) estimates."""
    csv = tmp_path / "t.csv"
    csv.write_text(f"x\n{_SMALL_VALUE!r}\n{_LONG_VALUE!r}\n0.5\n")
    config = _config(stats_decimals=2, data_decimals=3)
    result = CSVParser().parse(csv, config)  # type: ignore[arg-type]
    flattened = flatten_ir(
        result.content, stats_summary=True, stats_decimals=2, data_decimals=3
    )
    output = _render(generator, tmp_path, config)
    for line in flattened.split("\n"):
        assert line in output
    assert result.tokens == count_tokens(flattened)[0]
    full = flatten_ir(
        result.content, stats_summary=True, stats_decimals=17, data_decimals=17
    )
    assert result.tokens < count_tokens(full)[0]


def test_status_sees_the_rounded_row_width() -> None:
    """Whether the table cap cuts rows depends on the rendered width, which
    depends on the data cap: rows that fit rounded must not report Sampled."""
    rng = np.random.default_rng(0)
    table = TableIR(name="t.csv", df=pd.DataFrame({"x": rng.random(200) * 100}))
    short = len(render_sample_table(table.df, data_decimals=2))
    full = len(render_sample_table(table.df, data_decimals=17))
    assert short < full
    limit = (short + full) // 2
    assert _tabular_status([table], False, "Sampled", limit, limit, 2) == "Read"
    assert _tabular_status([table], False, "Sampled", limit, limit, 17) == "Sampled"


# ---------------------------------------------------------------------------
# The flags
# ---------------------------------------------------------------------------

def test_decimal_flags_default_and_override() -> None:
    with patch.object(sys, "argv", ["data2prompt"]):
        cfg = setup_cli()
    assert (cfg.stats_decimals, cfg.data_decimals) == (4, 6)
    argv = ["data2prompt", "--stats-decimals", "2", "--data-decimals", "17"]
    with patch.object(sys, "argv", argv):
        cfg = setup_cli()
    assert (cfg.stats_decimals, cfg.data_decimals) == (2, 17)
    with patch.object(sys, "argv", ["data2prompt", "--data-decimals", "0"]):
        assert setup_cli().data_decimals == 0


@pytest.mark.parametrize("flag", ["--stats-decimals", "--data-decimals"])
@pytest.mark.parametrize("bad", ["-1", "two"])
def test_decimal_flags_reject_invalid_values(flag: str, bad: str) -> None:
    with patch.object(sys, "argv", ["data2prompt", flag, bad]):
        with pytest.raises(SystemExit) as exc_info:
            setup_cli()
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# The preamble states the configured caps
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
def test_preamble_states_the_configured_caps(
    generator: OutputGenerator, tmp_path: Path
) -> None:
    output = _render(
        generator, tmp_path, _config(stats_decimals=3, data_decimals=9)
    )
    end = "</purpose>" if isinstance(generator, XMLGenerator) else "# File Index"
    preamble = " ".join(output.split(end)[0].split())
    assert (
        "Floats are rounded: data values to at most 9 decimals, statistics "
        "to at most 3 (values below 1 keep at least 4 "
        "significant digits)."
    ) in preamble
    assert "{DATA_DECIMALS}" not in output
    assert "{STATS_DECIMALS}" not in output
    assert "{SIGNIFICANT_DIGITS}" not in output


@pytest.mark.parametrize("generator", GENERATORS, ids=["markdown", "xml"])
def test_preamble_omits_the_sentence_when_no_cells_are_rendered(
    generator: OutputGenerator, tmp_path: Path
) -> None:
    config = _config(schema_only=True, stats_summary=False)
    output = _render(generator, tmp_path, config)
    assert "Floats are rounded" not in output
