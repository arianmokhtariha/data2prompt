"""Regenerate assets/report.svg — the README's TUI report preview.

Renders the real ``UIHandler.print_final_report()`` through a recording
Rich console and exports the result as SVG, so the preview is pixel-faithful
to the actual product. Run from anywhere:

    python assets/generators/make_report_svg.py
"""
from __future__ import annotations

import io
import sys
from pathlib import Path
from typing import Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from rich.console import Console
from rich.terminal_theme import TerminalTheme

from data2prompt.budget import BudgetAdjustment, BudgetReport
from data2prompt.parsers import FileSummary
from data2prompt.ui import UIHandler

# BLACKSITE-flavored terminal theme: near-black bg, warm yellow, hot white.
BLACKSITE = TerminalTheme(
    (12, 12, 14),        # background
    (224, 224, 224),     # foreground
    [                    # normal ANSI 0-7
        (20, 20, 24),        # black  (chip text on yellow)
        (255, 59, 87),       # red
        (92, 214, 133),      # green
        (255, 200, 87),      # yellow (warn channel)
        (98, 114, 164),      # blue
        (255, 121, 198),     # magenta
        (139, 233, 253),     # cyan
        (224, 224, 224),     # white
    ],
    [                    # bright ANSI 8-15
        (94, 94, 102),
        (255, 99, 122),
        (128, 255, 170),
        (255, 214, 120),
        (128, 144, 200),
        (255, 156, 214),
        (170, 240, 255),
        (255, 255, 255),
    ],
)


def build_summaries() -> List[FileSummary]:
    """A representative data-science project: realistic names, types, sizes."""
    rows: List[tuple[str, str, int, str]] = [
        # heavy hitters
        ("data/transactions_2024.csv", "CSV", 12380, "Sampled"),
        ("notebooks/churn_feature_eda.ipynb", "Notebook", 8214, "Cleaned"),
        ("warehouse/analytics.db", "SQLite (9 tables)", 7952, "Sampled"),
        ("notebooks/model_training.ipynb", "Notebook", 6480, "Cleaned"),
        ("data/customers.xlsx", "Excel (5 sheets)", 5830, "Extracted"),
        ("notebooks/cohort_analysis.ipynb", "Notebook", 5390, "Cleaned"),
        ("data/sessions_raw.csv", "CSV", 4820, "Sampled"),
        ("notebooks/feature_store.ipynb", "Notebook", 4120, "Cleaned"),
        ("notebooks/ab_test_eval.ipynb", "Notebook", 3260, "Cleaned"),
        ("data/marketing_spend.csv", "CSV", 3140, "Sampled"),
        # rest of the CSVs
        ("data/support_tickets.csv", "CSV", 2260, "Sampled"),
        ("data/plans.csv", "CSV", 1710, "Sampled"),
        ("data/regions.csv", "CSV", 1240, "Sampled"),
        ("data/promo_codes.csv", "CSV", 980, "Sampled"),
        ("data/holidays.csv", "CSV", 760, "Sampled"),
        ("data/churn_labels.csv", "CSV", 610, "Sampled"),
        ("data/segments.csv", "CSV", 420, "Sampled"),
        ("data/currencies.csv", "CSV", 310, "Sampled"),
        ("data/countries.csv", "CSV", 240, "Sampled"),
        # remaining notebook / excel
        ("notebooks/report_final.ipynb", "Notebook", 2210, "Cleaned"),
        ("data/kpi_dashboard.xlsm", "Excel (2 sheets)", 2140, "Extracted"),
        # SQL
        ("sql/build_features.sql", "SQL", 1480, "Parsed"),
        ("sql/cohorts.sql", "SQL", 920, "Parsed"),
        ("sql/retention.sql", "SQL", 610, "Parsed"),
        ("sql/backfill.sql", "SQL", 380, "Parsed"),
        # python
        ("src/features/engineering.py", "py", 640, "Read"),
        ("src/models/train.py", "py", 580, "Read"),
        ("src/models/evaluate.py", "py", 520, "Read"),
        ("src/pipeline/ingest.py", "py", 470, "Read"),
        ("src/pipeline/validate.py", "py", 410, "Read"),
        ("src/utils/io.py", "py", 380, "Read"),
        ("src/utils/metrics.py", "py", 340, "Read"),
        ("src/config.py", "py", 310, "Read"),
        ("src/cli.py", "py", 280, "Read"),
        ("tests/test_features.py", "py", 250, "Read"),
        ("tests/test_train.py", "py", 220, "Read"),
        ("tests/test_ingest.py", "py", 190, "Read"),
        ("tests/conftest.py", "py", 160, "Read"),
        ("scripts/export_model.py", "py", 140, "Read"),
        ("scripts/refresh_data.py", "py", 120, "Read"),
        # docs / config
        ("README.md", "md", 880, "Read"),
        ("docs/data_dictionary.md", "md", 420, "Read"),
        ("docs/runbook.md", "md", 260, "Read"),
        ("configs/model.yaml", "yaml", 240, "Read"),
        ("configs/pipeline.yaml", "yaml", 180, "Read"),
        ("pyproject.toml", "toml", 90, "Read"),
        # flagged
        ("logs/train_run.log", "log", 1830, "Truncated"),
        ("data/events_stream.jsonl", "jsonl", 1420, "Truncated"),
        ("logs/grid_search.log", "log", 990, "Truncated"),
        ("assets/model_diagram.png", "Binary (.png)", 0, "Skipped (Binary)"),
        ("models/churn_xgb.pkl", "Binary (.pkl)", 0, "Skipped (Binary)"),
        (".env", "Env", 0, "Redacted"),
    ]
    return [
        {"name": n, "type": t, "tokens": tok, "status": s}
        for n, t, tok, s in rows
    ]


def main() -> None:
    handler = UIHandler()
    handler.console = Console(
        file=io.StringIO(), width=120, record=True, force_terminal=True
    )

    summaries = build_summaries()
    stats: Dict[str, int] = {
        "file_count": len(summaries),
        "csv_count": 12,
        "notebook_count": 6,
        "sql_count": 4,
        "excel_count": 2,
        "excel_sheets_count": 7,
        "sqlite_count": 1,
        "db_tables_count": 9,
        "truncated_count": 3,
        "binary_count": 2,
        "env_count": 1,
    }
    report = BudgetReport(
        requested_tokens=120_000,
        adjustments=[
            BudgetAdjustment(
                parameter="csv-sample-size",
                requested="15",
                adjusted="8",
                scope="15 tabular data file(s) re-sampled",
            ),
            BudgetAdjustment(
                parameter="max-lines",
                requested="40",
                adjusted="20",
                scope="6 notebook(s) output-trimmed",
            ),
        ],
        omitted=[],
    )

    handler.print_final_report(
        processed_files_info=summaries,
        output_path="PROMPT.md",
        file_size_kb=377.4,
        total_tokens=96_420,
        stats=stats,
        method="o200k_base",
        elapsed_seconds=3.4,
        budget_report=report,
    )

    svg = handler.console.export_svg(title="data2prompt", theme=BLACKSITE)
    out = PROJECT_ROOT / "assets" / "report.svg"
    out.write_text(svg, encoding="utf-8")
    print(f"wrote {out} ({len(svg):,} chars)")


if __name__ == "__main__":
    main()
