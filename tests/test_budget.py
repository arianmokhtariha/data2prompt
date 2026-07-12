"""
Tests for the --budget token-budget-targeting feature.

Covers the CLI wiring (-b/--budget parsing), the fit_to_budget() ladder
algorithm in isolation (fake reparse callables so no pandas/real files are
needed), the Budget Report rendering in both output formats, and two
end-to-end main._run() regressions guarding bugs found during review:
adjustments recorded *before* the verifying render (not after, which would
make the returned report lag the true final config by one ladder step), and
placeholder substitution on a successful --budget run's written file.
"""

import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, Dict, List
from unittest.mock import patch

import pytest

from data2prompt.budget import (
    EXTS_TABULAR,
    BudgetAdjustment,
    BudgetReport,
    FileRecord,
    _select_by_ext,
    _select_text_group,
    fit_to_budget,
)
from data2prompt.cli import Config, setup_cli
from data2prompt.constants import BUDGET_MIN_CSV_SAMPLE
from data2prompt.main import _run
from data2prompt.output import MarkdownGenerator, XMLGenerator, get_generator
from data2prompt.parsers import ParserResult
from data2prompt.ui import status_severity
from data2prompt.utils import count_tokens


# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------

def _config(
    csv_sample_size: int = 40,
    output_format: str = "markdown",
) -> Config:
    """A fully-populated Config; only the fields budget tests vary are
    exposed as parameters."""
    return Config(
        output="PROMPT.md",
        format=output_format,
        csv_sample_size=csv_sample_size,
        seed=42,
        sql_sample_size=15,
        sql_max_lines=50,
        max_lines=50,
        max_sheets=10,
        max_tables=25,
        line_length_threshold=300,
        truncated_line_length=200,
        table_limit=50_000,
        table_truncate=20_000,
    )


def _unexpected_reparse(path: Path, cfg: Config) -> ParserResult:
    """A reparse callable that fails the test if the ladder ever calls it.

    Used in scenarios (plain .txt records, default max_file_size=0) where no
    ladder step should touch the record at all — if this fires, either the
    test's premise is wrong or a ladder step regressed to affect extensions
    it should not.
    """
    raise AssertionError(
        f"unexpected reparse call for {path} with csv_sample_size="
        f"{cfg.csv_sample_size} — no ladder step should have touched this "
        "record"
    )


def _scaling_reparse(
    words_per_sample: int = 20,
) -> Callable[[Path, Config], ParserResult]:
    """A fake reparse whose output token count scales with csv_sample_size —
    stands in for real CSV sampling so ladder tests don't need pandas or
    files on disk."""
    def _reparse(path: Path, cfg: Config) -> ParserResult:
        words = max(1, cfg.csv_sample_size) * words_per_sample
        return ParserResult(
            content="value " * words,
            tokens=0,
            type="CSV",
            status="Sampled",
            stats_update={"csv_count": 1},
        )
    return _reparse


def _render_tokens(records: List[FileRecord], config: Config, tree_text: str) -> int:
    """Render records with the real generator/tokenizer and return the true
    token count — self-calibrates test budgets instead of hardcoding
    tiktoken-specific magic numbers."""
    files_data = [
        {
            "path": r.relative_path,
            "content": r.result.content,
            "type": r.result.type,
            "tokens": r.result.tokens,
            "status": r.result.status,
        }
        for r in records
    ]
    report = BudgetReport(requested_tokens=0, adjustments=[], omitted=[])
    text = get_generator(config.format).generate(
        project_name="demo",
        tree_text=tree_text,
        files_data=files_data,
        stats={"file_count": len(records)},
        config=config,
        budget_report=report,
    )
    tokens, _ = count_tokens(text)
    return tokens


# ---------------------------------------------------------------------------
# CLI wiring: -b/--budget parsing (via setup_cli, not the private type
# function in isolation — this proves the argparse flag actually reaches
# Config.budget, not just that the parser function works alone)
# ---------------------------------------------------------------------------

def test_setup_cli_budget_default_is_none() -> None:
    with patch.object(sys, "argv", ["data2prompt"]):
        cfg = setup_cli()
        assert cfg.budget is None


def test_setup_cli_budget_accepts_plain_integer() -> None:
    with patch.object(sys, "argv", ["data2prompt", "--budget", "50000"]):
        cfg = setup_cli()
        assert cfg.budget == 50_000


def test_setup_cli_budget_accepts_k_suffix() -> None:
    with patch.object(sys, "argv", ["data2prompt", "-b", "100k"]):
        cfg = setup_cli()
        assert cfg.budget == 100_000


def test_setup_cli_budget_accepts_m_suffix_with_decimal() -> None:
    with patch.object(sys, "argv", ["data2prompt", "--budget", "1.5m"]):
        cfg = setup_cli()
        assert cfg.budget == 1_500_000


def test_setup_cli_budget_accepts_commas_and_underscores() -> None:
    with patch.object(sys, "argv", ["data2prompt", "--budget", "10_000"]):
        assert setup_cli().budget == 10_000
    with patch.object(sys, "argv", ["data2prompt", "--budget", "10,000"]):
        assert setup_cli().budget == 10_000


def test_setup_cli_budget_rejects_zero() -> None:
    with patch.object(sys, "argv", ["data2prompt", "--budget", "0"]):
        with pytest.raises(SystemExit) as exc_info:
            setup_cli()
        assert exc_info.value.code == 2


def test_setup_cli_budget_rejects_garbage() -> None:
    with patch.object(sys, "argv", ["data2prompt", "--budget", "not-a-number"]):
        with pytest.raises(SystemExit) as exc_info:
            setup_cli()
        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# fit_to_budget: fits without any ladder step
# ---------------------------------------------------------------------------

def test_fits_without_adjustment_when_budget_is_generous() -> None:
    """A budget far larger than the natural document size needs no ladder
    steps — and the returned token count must be the real count of the
    exact text returned (ground truth, not an estimate)."""
    record = FileRecord(
        absolute_path=Path("notes.txt"),
        relative_path="notes.txt",
        result=ParserResult(
            content="hello world\n" * 20, tokens=0, type="txt", status="Read"
        ),
    )
    outcome = fit_to_budget(
        budget=1_000_000,
        config=_config(),
        records=[record],
        scanned_file_count=1,
        tree_text="notes.txt",
        project_name="demo",
        reparse=_unexpected_reparse,
    )

    assert outcome.fits
    assert outcome.report.adjustments == []
    assert outcome.report.omitted == []
    assert outcome.final_output is not None
    assert "No parameter adjustments were needed" in outcome.final_output
    # fit_to_budget itself never substitutes the placeholders — that is
    # main.py's job, done once after the final count is known.
    assert "{{TOTAL_TOKENS}}" in outcome.final_output
    real_tokens, _ = count_tokens(outcome.final_output)
    assert real_tokens == outcome.total_tokens


# ---------------------------------------------------------------------------
# Regression: BudgetAdjustment must be recorded *before* the verifying
# render, not after. If recorded after, the report returned for the final
# (fitting) attempt reflects the *previous* ladder iteration's value — or
# is missing the parameter entirely when only one iteration was needed.
# ---------------------------------------------------------------------------

def test_halving_step_adjustment_recorded_before_render_regression() -> None:
    reparse = _scaling_reparse(words_per_sample=20)
    path = Path("data/big.csv")

    floor_record = FileRecord(
        absolute_path=path,
        relative_path="data/big.csv",
        result=reparse(path, _config(csv_sample_size=BUDGET_MIN_CSV_SAMPLE)),
    )
    # A budget only the floor state can satisfy, with slack to cover the
    # extra tokens the report's own adjustments-table row adds once one
    # adjustment is recorded (the calibration render has zero adjustments).
    budget = (
        _render_tokens(
            [floor_record], _config(csv_sample_size=BUDGET_MIN_CSV_SAMPLE),
            "data/big.csv",
        )
        + 500
    )

    large_record = FileRecord(
        absolute_path=path,
        relative_path="data/big.csv",
        result=reparse(path, _config(csv_sample_size=200)),
    )

    outcome = fit_to_budget(
        budget=budget,
        config=_config(csv_sample_size=200),
        records=[large_record],
        scanned_file_count=1,
        tree_text="data/big.csv",
        project_name="demo",
        reparse=reparse,
    )

    assert outcome.fits, "expected the halving ladder to reach a fitting state"
    adjustment = next(
        (a for a in outcome.report.adjustments if a.parameter == "csv-sample-size"),
        None,
    )
    assert adjustment is not None, (
        "csv-sample-size adjustment missing from the returned report — if "
        "BudgetAdjustment is recorded after (not before) the verifying "
        "render, a step that fits on its final iteration can report no "
        "adjustment at all"
    )
    assert int(adjustment.adjusted) == outcome.config.csv_sample_size, (
        f"report says adjusted={adjustment.adjusted!r} but the config "
        f"actually used to render is csv_sample_size="
        f"{outcome.config.csv_sample_size} — the report lags the true "
        "final config by one ladder iteration"
    )
    assert "csv-sample-size" in outcome.final_output


def test_stats_not_double_counted_across_multiple_ladder_attempts() -> None:
    """_materialize() rebuilds stats from scratch every attempt; if it
    instead accumulated across attempts, a multi-iteration ladder step would
    inflate stats by the number of attempts it took to converge."""
    reparse = _scaling_reparse(words_per_sample=20)
    path_a, path_b = Path("data/a.csv"), Path("data/b.csv")
    tree = "data/a.csv\ndata/b.csv"

    floor_cfg = _config(csv_sample_size=BUDGET_MIN_CSV_SAMPLE)
    floor_records = [
        FileRecord(path_a, "data/a.csv", reparse(path_a, floor_cfg)),
        FileRecord(path_b, "data/b.csv", reparse(path_b, floor_cfg)),
    ]
    budget = _render_tokens(floor_records, floor_cfg, tree) + 500

    large_cfg = _config(csv_sample_size=200)
    records = [
        FileRecord(path_a, "data/a.csv", reparse(path_a, large_cfg)),
        FileRecord(path_b, "data/b.csv", reparse(path_b, large_cfg)),
    ]

    outcome = fit_to_budget(
        budget=budget,
        config=large_cfg,
        records=records,
        scanned_file_count=2,
        tree_text=tree,
        project_name="demo",
        reparse=reparse,
    )

    assert outcome.fits
    assert outcome.stats["csv_count"] == 2, (
        f"expected exactly 2 (one per included file), got "
        f"{outcome.stats['csv_count']} — stats must be rebuilt from scratch "
        "each attempt, not accumulated across ladder iterations"
    )


# ---------------------------------------------------------------------------
# Extension classification: a .db must ride the tabular ladder steps
# (re-sample / stats-off / schema-only), never the text-truncation step —
# byte-truncating a rendered multi-table database would be meaningless.
# ---------------------------------------------------------------------------

def test_budget_classifies_sqlite_as_tabular_not_text() -> None:
    record = FileRecord(
        absolute_path=Path("data/app.db"),
        relative_path="data/app.db",
        result=ParserResult(
            content=[], tokens=100, type="SQLite (2 tables)", status="Sampled",
        ),
    )
    records = [record]

    assert ".db" in EXTS_TABULAR
    # Steps 1/6/7 select tabular files (csv-sample-size, stats-summary, schema-only).
    assert _select_by_ext(records, set(), EXTS_TABULAR) == [record]
    # Step 8 (text truncation to first N KB) must never touch a database file.
    assert _select_text_group(records, set(), _config()) == []


# ---------------------------------------------------------------------------
# Omission phase (step 9): last resort, heaviest-first, no re-parsing
# ---------------------------------------------------------------------------

def test_omission_phase_drops_heaviest_files_first() -> None:
    light_content, heavy_content = "w " * 100, "w " * 4000
    light = FileRecord(
        absolute_path=Path("light.txt"), relative_path="light.txt",
        result=ParserResult(
            content=light_content, tokens=count_tokens(light_content)[0],
            type="txt", status="Read",
        ),
    )
    medium = FileRecord(
        absolute_path=Path("medium.txt"), relative_path="medium.txt",
        result=ParserResult(
            content=light_content, tokens=count_tokens(light_content)[0],
            type="txt", status="Read",
        ),
    )
    heavy = FileRecord(
        absolute_path=Path("heavy.txt"), relative_path="heavy.txt",
        result=ParserResult(
            content=heavy_content, tokens=count_tokens(heavy_content)[0],
            type="txt", status="Read",
        ),
    )
    tree = "light.txt\nmedium.txt\nheavy.txt"
    # Only light+medium need to fit; max_file_size defaults to 0 so step 8
    # never touches .txt files, and there is no tabular/sql/notebook ext
    # here, so the ladder falls straight through to omission.
    budget = _render_tokens([light, medium], _config(), tree) + 500

    outcome = fit_to_budget(
        budget=budget,
        config=_config(),
        records=[light, medium, heavy],
        scanned_file_count=3,
        tree_text=tree,
        project_name="demo",
        reparse=_unexpected_reparse,
    )

    assert outcome.fits
    assert [p for p, _ in outcome.report.omitted] == ["heavy.txt"]
    assert outcome.stats.get("budget_omitted_count") == 1

    remaining_paths = {f["path"] for f in outcome.files_data}
    assert remaining_paths == {"light.txt", "medium.txt"}

    omitted_summary = next(s for s in outcome.summaries if s["name"] == "heavy.txt")
    assert omitted_summary["status"] == "Omitted (Budget)"
    assert omitted_summary["tokens"] == 0

    # The rendered document's File Index must reflect the omission too.
    assert outcome.final_output is not None
    assert "| heavy.txt | - | Omitted |" in outcome.final_output


def test_omission_uses_forward_slash_paths() -> None:
    """main.py builds relative_path via str(Path(...)), which is
    backslash-separated on Windows — the report's omitted paths must still
    be forward-slash (Path.as_posix()), matching the File Index convention."""
    light_content, heavy_content = "w " * 100, "w " * 4000
    heavy = FileRecord(
        absolute_path=Path("data") / "heavy.txt",
        relative_path="data\\heavy.txt",
        result=ParserResult(
            content=heavy_content, tokens=count_tokens(heavy_content)[0],
            type="txt", status="Read",
        ),
    )
    light = FileRecord(
        absolute_path=Path("light.txt"), relative_path="light.txt",
        result=ParserResult(
            content=light_content, tokens=count_tokens(light_content)[0],
            type="txt", status="Read",
        ),
    )
    tree = "light.txt\ndata/heavy.txt"
    budget = _render_tokens([light], _config(), tree) + 500

    outcome = fit_to_budget(
        budget=budget,
        config=_config(),
        records=[light, heavy],
        scanned_file_count=2,
        tree_text=tree,
        project_name="demo",
        reparse=_unexpected_reparse,
    )

    assert outcome.fits
    omitted_paths = [p for p, _ in outcome.report.omitted]
    assert omitted_paths == ["data/heavy.txt"]
    assert "data\\heavy.txt" not in omitted_paths


def test_infeasible_budget_returns_no_final_output() -> None:
    """A budget so small even an empty document overshoots it must report
    fits=False and never hand back a final_output for main.py to write."""
    record = FileRecord(
        absolute_path=Path("only.txt"), relative_path="only.txt",
        result=ParserResult(content="w " * 50, tokens=0, type="txt", status="Read"),
    )
    outcome = fit_to_budget(
        budget=1,
        config=_config(),
        records=[record],
        scanned_file_count=1,
        tree_text="only.txt",
        project_name="demo",
        reparse=_unexpected_reparse,
    )

    assert outcome.fits is False
    assert outcome.final_output is None
    assert outcome.report.omitted


# ---------------------------------------------------------------------------
# Budget Report rendering — Markdown/XML format parity
# ---------------------------------------------------------------------------

FilesData = List[Dict[str, object]]


def _one_file_files_data() -> FilesData:
    return [{"path": "a.py", "content": "x", "type": "py", "tokens": 0, "status": "Read"}]


def test_markdown_budget_block_renders_adjustments_and_omitted_tables() -> None:
    report = BudgetReport(
        requested_tokens=50_000,
        adjustments=[
            BudgetAdjustment(
                parameter="csv-sample-size", requested="40", adjusted="5",
                scope="3 tabular data file(s) re-sampled",
            )
        ],
        omitted=[("data/huge.parquet", 12_345)],
    )
    output = MarkdownGenerator().generate(
        project_name="demo", tree_text="a.py",
        files_data=_one_file_files_data(), stats={}, budget_report=report,
    )
    assert "# Budget Report" in output
    body = output.split("# Budget Report", 1)[1]
    assert "Requested budget: 50,000 tokens." in body
    assert "| csv-sample-size | 40 | 5 | 3 tabular data file(s) re-sampled |" in body
    assert "| data/huge.parquet | 12,345 |" in body


def test_markdown_budget_block_no_adjustments_message() -> None:
    report = BudgetReport(requested_tokens=50_000, adjustments=[], omitted=[])
    output = MarkdownGenerator().generate(
        project_name="demo", tree_text="a.py",
        files_data=_one_file_files_data(), stats={}, budget_report=report,
    )
    body = output.split("# Budget Report", 1)[1]
    assert "No parameter adjustments were needed" in body
    assert "|---|---|---|---|" not in body


def test_xml_budget_block_renders_adjustment_and_omitted_elements() -> None:
    report = BudgetReport(
        requested_tokens=50_000,
        adjustments=[
            BudgetAdjustment(
                parameter="csv-sample-size", requested="40", adjusted="5",
                scope="3 tabular data file(s) re-sampled",
            )
        ],
        omitted=[("data/huge.parquet", 12_345)],
    )
    output = XMLGenerator().generate(
        project_name="demo", tree_text="a.py",
        files_data=_one_file_files_data(), stats={}, budget_report=report,
    )
    # Scope past the preamble: it literally mentions <budget_report>.
    body = output.split("</purpose>", 1)[1]
    assert '<budget_report requested_tokens="50000">' in body
    assert (
        '<adjustment parameter="csv-sample-size" requested="40" adjusted="5" '
        'scope="3 tabular data file(s) re-sampled"/>' in body
    )
    assert '<omitted_file path="data/huge.parquet" estimated_tokens="12345"/>' in body


def test_xml_budget_block_self_closes_when_empty() -> None:
    report = BudgetReport(requested_tokens=50_000, adjustments=[], omitted=[])
    output = XMLGenerator().generate(
        project_name="demo", tree_text="a.py",
        files_data=_one_file_files_data(), stats={}, budget_report=report,
    )
    body = output.split("</purpose>", 1)[1]
    assert '<budget_report requested_tokens="50000"/>' in body
    assert '<budget_report requested_tokens="50000">' not in body


def test_budget_block_absent_without_budget_report() -> None:
    """budget_report=None (the default, used by every non---budget run)
    must not emit any budget markup — the feature costs nothing when unused."""
    md = MarkdownGenerator().generate(
        project_name="demo", tree_text="a.py",
        files_data=_one_file_files_data(), stats={},
    )
    assert "# Budget Report" not in md

    xml = XMLGenerator().generate(
        project_name="demo", tree_text="a.py",
        files_data=_one_file_files_data(), stats={},
    )
    assert "<budget_report" not in xml.split("</purpose>", 1)[1]


def test_xml_omitted_file_path_with_ampersand_is_escaped() -> None:
    """An omitted file's path is a real repo path and could contain XML
    special characters (e.g. 'R&D/big.csv') — must be escaped, not raw."""
    report = BudgetReport(
        requested_tokens=100, adjustments=[], omitted=[("data/R&D/big.csv", 5000)],
    )
    output = XMLGenerator().generate(
        project_name="demo", tree_text="a.py",
        files_data=_one_file_files_data(), stats={}, budget_report=report,
    )
    body = output.split("</purpose>", 1)[1]
    assert 'path="data/R&amp;D/big.csv"' in body
    assert 'path="data/R&D/big.csv"' not in body


# ---------------------------------------------------------------------------
# UI severity mapping
# ---------------------------------------------------------------------------

def test_omitted_budget_status_is_warn_severity() -> None:
    assert status_severity("Omitted (Budget)") == "warn"


# ---------------------------------------------------------------------------
# End-to-end main._run() regressions
# ---------------------------------------------------------------------------

def test_run_budget_fits_substitutes_placeholders_in_written_file() -> None:
    """Regression: a successful --budget run must substitute
    {{TOTAL_TOKENS}}/{{TOKEN_METHOD}} in the written file exactly like the
    budget-less path does, not leave the literal placeholders behind."""
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "notes.txt").write_text("hello world\n" * 20, encoding="utf-8")
        os.chdir(tmp)
        try:
            with patch.object(
                sys, "argv",
                ["data2prompt", "-o", "OUT", "-f", "markdown", "--budget", "200000"],
            ):
                _run()
            output_text = (Path(tmp) / "OUT.md").read_text(encoding="utf-8")
        finally:
            os.chdir(original_cwd)

    assert "{{TOTAL_TOKENS}}" not in output_text
    assert "{{TOKEN_METHOD}}" not in output_text
    assert "> Tokens: {{TOTAL_TOKENS}}" not in output_text


def test_run_infeasible_budget_exits_nonzero_and_writes_no_file() -> None:
    original_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "notes.txt").write_text("hello world\n" * 20, encoding="utf-8")
        os.chdir(tmp)
        try:
            with patch.object(sys, "argv", ["data2prompt", "-o", "OUT", "--budget", "1"]):
                with pytest.raises(SystemExit) as exc_info:
                    _run()
            output_exists = (Path(tmp) / "OUT.md").exists()
        finally:
            os.chdir(original_cwd)

    assert exc_info.value.code == 1
    assert not output_exists
