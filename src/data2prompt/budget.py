"""Token budget targeting for --budget.

``fit_to_budget()`` is the entry point. Given a first-pass parse of every
file, it tightens data-cap parameters one ladder step at a time, verifying
the real rendered token count (via ``output.py`` + ``utils.count_tokens``)
after every step, until the document fits inside the requested budget — or
omits the token-heaviest remaining files as a last resort. No parser logic
lives here: each step calls back into the caller's ``reparse`` function
(``main.process_target_file``) with a ``dataclasses.replace()``-modified
config, so parsers.py never needs to know a budget exists.
"""

from dataclasses import dataclass, replace
from pathlib import Path
from typing import (
    Callable,
    Dict,
    FrozenSet,
    List,
    Optional,
    Set,
    Tuple,
    TYPE_CHECKING,
)

if TYPE_CHECKING:
    from data2prompt.cli import Config

from data2prompt.constants import (
    BUDGET_MIN_CSV_SAMPLE,
    BUDGET_MIN_NOTEBOOK_LINES,
    BUDGET_MIN_SQL_MAX_LINES,
    BUDGET_MIN_SQL_SAMPLE,
    BUDGET_TEXT_FILE_SIZE_KB,
    BUDGET_TOKEN_MARGIN,
)
from data2prompt.output import get_generator
from data2prompt.parsers import FileData, FileSummary, ParserResult, is_env_file
from data2prompt.utils import count_tokens

# Extension groups the ladder steps target. A file's group is decided by its
# lowercase suffix; re-parsing a file that comes back unchanged is harmless,
# so selection by extension is sufficient (no per-parser bookkeeping needed).
EXTS_TABULAR = frozenset(
    {".csv", ".xlsx", ".xls", ".xlsm", ".parquet", ".feather", ".arrow",
     ".db", ".sqlite", ".sqlite3"}
)
EXTS_SQL = frozenset({".sql"})
EXTS_NOTEBOOK = frozenset({".ipynb"})


@dataclass
class FileRecord:
    """One scanned file's first-pass parse result, re-parseable in place."""
    absolute_path: Path
    relative_path: str          # str(relative) exactly as main.py builds it
    result: ParserResult


@dataclass(frozen=True)
class BudgetAdjustment:
    """One data-cap parameter change made to fit the budget."""
    parameter: str              # CLI-flag spelling, e.g. "csv-sample-size"
    requested: str               # value before the budget pass, rendered
    adjusted: str                 # final value after the pass, rendered
    scope: str                   # e.g. "6 tabular data file(s) re-sampled"


@dataclass
class BudgetReport:
    """Everything the document and the TUI report about a budget run."""
    requested_tokens: int
    adjustments: List[BudgetAdjustment]
    omitted: List[Tuple[str, int]]   # (forward-slash path, est. tokens)


@dataclass
class BudgetOutcome:
    """Final result of a budget-fitting pass, ready for main.py to consume."""
    fits: bool
    final_output: Optional[str]      # rendered text with placeholders; None
    total_tokens: int                # count of the last attempt
    method: str                      # token-count method of the last attempt
    report: BudgetReport
    files_data: List[FileData]       # final files_data (omitted files gone)
    stats: Dict[str, int]            # rebuilt stats for the final document
    summaries: List[FileSummary]     # final TUI rows (omitted files kept)
    config: 'Config'                 # the adjusted config used to render


@dataclass
class _AttemptResult:
    """One rendered-and-counted attempt at fitting the budget."""
    text: str
    tokens: int
    method: str
    files_data: List[FileData]
    stats: Dict[str, int]
    summaries: List[FileSummary]
    report: BudgetReport


def _materialize(
    records: List[FileRecord],
    omitted_paths: Set[str],
    scanned_file_count: int,
) -> Tuple[List[FileData], Dict[str, int], List[FileSummary]]:
    """Rebuild files_data/stats/summaries from records for one attempt.

    Rebuilding from scratch every attempt (instead of mutating running
    totals) is what prevents double-counting stats across re-parses.
    Omitted records are dropped from ``files_data`` but kept in
    ``summaries`` with 0 tokens and an ``"Omitted (Budget)"`` status, so the
    TUI composition chart never counts content that is not in the document.
    """
    files_data: List[FileData] = []
    stats: Dict[str, int] = {"file_count": scanned_file_count}
    summaries: List[FileSummary] = []

    for record in records:
        if record.relative_path in omitted_paths:
            summaries.append({
                "name": record.relative_path,
                "type": record.result.type,
                "tokens": 0,
                "status": "Omitted (Budget)",
            })
            continue

        result = record.result
        files_data.append({
            "path": record.relative_path,
            "content": result.content,
            "type": result.type,
            "tokens": result.tokens,
            "status": result.status,
        })
        for key, value in result.stats_update.items():
            stats[key] = stats.get(key, 0) + value
        summaries.append({
            "name": record.relative_path,
            "type": result.type,
            "tokens": result.tokens,
            "status": result.status,
        })

    if omitted_paths:
        stats["budget_omitted_count"] = len(omitted_paths)

    return files_data, stats, summaries


def _select_by_ext(
    records: List[FileRecord],
    omitted: Set[str],
    exts: FrozenSet[str],
) -> List[FileRecord]:
    """Included (not-yet-omitted) records whose suffix is in ``exts``."""
    return [
        record
        for record in records
        if record.relative_path not in omitted
        and record.absolute_path.suffix.lower() in exts
    ]


def _select_text_group(
    records: List[FileRecord],
    omitted: Set[str],
    config: 'Config',
) -> List[FileRecord]:
    """Included records the DefaultParser would handle ("text group").

    Excludes tabular/SQL/notebook extensions (they have their own steps),
    ``config.skip_exts`` (content is already dropped), and env files (their
    values are already redacted, not size-truncated).
    """
    non_default = EXTS_TABULAR | EXTS_SQL | EXTS_NOTEBOOK
    return [
        record
        for record in records
        if record.relative_path not in omitted
        and record.absolute_path.suffix.lower() not in non_default
        and record.absolute_path.suffix.lower() not in config.skip_exts
        and not is_env_file(record.absolute_path.name)
    ]


def _reparse_records(
    affected: List[FileRecord],
    config: 'Config',
    reparse: Callable[[Path, 'Config'], ParserResult],
) -> None:
    """Re-parse each affected record in place with the adjusted config."""
    for record in affected:
        record.result = reparse(record.absolute_path, config)


def fit_to_budget(
    budget: int,
    config: 'Config',
    records: List[FileRecord],
    scanned_file_count: int,
    tree_text: str,
    project_name: str,
    reparse: Callable[[Path, 'Config'], ParserResult],
    on_progress: Optional[Callable[[str, str], None]] = None,
) -> BudgetOutcome:
    """Tighten data-cap parameters until the rendered document fits budget.

    Renders and counts the full document (with its Budget Report block)
    after every change, so the verified count always matches the real
    output — an attempt fits when ``tokens <= budget - BUDGET_TOKEN_MARGIN``,
    the margin covering the later ``{{TOTAL_TOKENS}}``/``{{TOKEN_METHOD}}``
    digit substitution in main.py.

    Applies a fixed ladder in order: halve csv-sample-size, max-lines,
    sql-sample-size, and sql-max-lines down to their floors; then drop
    notebook outputs entirely, turn off the stats-summary block, switch to
    schema-only, and cap unhandled text files to 10KB; finally, as a last
    resort, omit the token-heaviest remaining files. Each step is skipped
    if it has no affected records or is already at/below its floor. Returns
    a ``BudgetOutcome``: ``fits=True`` with the rendered output, or
    ``fits=False`` (``final_output=None``) if the fully reduced document
    still exceeds the budget.
    """
    generator = get_generator(config.format)
    threshold = budget - BUDGET_TOKEN_MARGIN
    omitted: Set[str] = set()
    omitted_list: List[Tuple[str, int]] = []
    adjustments: Dict[str, BudgetAdjustment] = {}
    current = config

    def _attempt(cfg: 'Config') -> _AttemptResult:
        """Materialize, render, and count one full-document attempt."""
        files_data, stats, summaries = _materialize(
            records, omitted, scanned_file_count
        )
        report = BudgetReport(
            requested_tokens=budget,
            adjustments=list(adjustments.values()),
            omitted=list(omitted_list),
        )
        text = generator.generate(
            project_name=project_name,
            tree_text=tree_text,
            files_data=files_data,
            stats=stats,
            config=cfg,
            budget_report=report,
        )
        tokens, method = count_tokens(text)
        if on_progress is not None:
            on_progress("Budgeting", f"{tokens:,} / {budget:,} tokens")
        return _AttemptResult(
            text, tokens, method, files_data, stats, summaries, report
        )

    result = _attempt(current)

    def _over_budget() -> bool:
        return result.tokens > threshold

    def _halving_step(
        field_name: str,
        floor: int,
        affected: List[FileRecord],
        parameter: str,
        scope: Callable[[int], str],
    ) -> None:
        """Halve ``field_name`` toward ``floor`` while over budget.

        Re-parses ``affected`` after each halving and re-renders/re-counts
        the whole document. Records one ``BudgetAdjustment`` if the value
        actually changed and at least one record was re-parsed.
        """
        nonlocal current, result
        if not affected or not _over_budget():
            return
        requested_value = getattr(current, field_name)
        value = requested_value
        while _over_budget() and value > floor:
            value = max(floor, value // 2)
            current = replace(current, **{field_name: value})
            # Recorded before rendering: the attempt's Budget Report (and so
            # the verified token count) must already carry this adjustment.
            adjustments[parameter] = BudgetAdjustment(
                parameter=parameter,
                requested=str(requested_value),
                adjusted=str(value),
                scope=scope(len(affected)),
            )
            if on_progress is not None:
                on_progress("Fitting", f"{parameter} -> {value}")
            _reparse_records(affected, current, reparse)
            result = _attempt(current)

    # Steps 1-4: halving loops, tabular -> notebook -> SQL sample -> SQL cap.
    _halving_step(
        "csv_sample_size",
        BUDGET_MIN_CSV_SAMPLE,
        _select_by_ext(records, omitted, EXTS_TABULAR),
        "csv-sample-size",
        lambda n: f"{n} tabular data file(s) re-sampled",
    )
    _halving_step(
        "max_lines",
        BUDGET_MIN_NOTEBOOK_LINES,
        _select_by_ext(records, omitted, EXTS_NOTEBOOK),
        "max-lines",
        lambda n: f"{n} notebook(s) output-trimmed",
    )
    _halving_step(
        "sql_sample_size",
        BUDGET_MIN_SQL_SAMPLE,
        _select_by_ext(records, omitted, EXTS_SQL),
        "sql-sample-size",
        lambda n: f"{n} SQL file(s) re-sampled",
    )
    _halving_step(
        "sql_max_lines",
        BUDGET_MIN_SQL_MAX_LINES,
        _select_by_ext(records, omitted, EXTS_SQL),
        "sql-max-lines",
        lambda n: f"{n} SQL file(s) re-capped",
    )

    # Step 5: drop notebook outputs entirely (max-lines -> 0). Merges into
    # the "max-lines" adjustment from step 2 if that one already ran.
    if _over_budget() and current.max_lines > 0:
        notebooks = _select_by_ext(records, omitted, EXTS_NOTEBOOK)
        if notebooks:
            existing = adjustments.get("max-lines")
            requested_value = (
                existing.requested
                if existing is not None
                else str(current.max_lines)
            )
            current = replace(current, max_lines=0)
            adjustments["max-lines"] = BudgetAdjustment(
                parameter="max-lines",
                requested=requested_value,
                adjusted="0",
                scope=(
                    "notebook outputs dropped from "
                    f"{len(notebooks)} notebook(s)"
                ),
            )
            if on_progress is not None:
                on_progress("Fitting", "max-lines -> 0")
            _reparse_records(notebooks, current, reparse)
            result = _attempt(current)

    # Step 6: drop the per-table describe/missing stats block.
    if _over_budget() and current.stats_summary:
        tabular = _select_by_ext(records, omitted, EXTS_TABULAR)
        if tabular:
            current = replace(current, stats_summary=False)
            adjustments["stats-summary"] = BudgetAdjustment(
                parameter="stats-summary",
                requested="on",
                adjusted="off",
                scope=(
                    "describe/missing stats dropped from "
                    f"{len(tabular)} tabular data file(s)"
                ),
            )
            if on_progress is not None:
                on_progress("Fitting", "stats-summary -> off")
            _reparse_records(tabular, current, reparse)
            result = _attempt(current)

    # Step 7: schema-only — drop data rows, keep schema/columns.
    if _over_budget() and not current.schema_only:
        schema_group = _select_by_ext(
            records, omitted, EXTS_TABULAR | EXTS_SQL
        )
        if schema_group:
            current = replace(current, schema_only=True)
            adjustments["schema-only"] = BudgetAdjustment(
                parameter="schema-only",
                requested="off",
                adjusted="on",
                scope=(
                    f"{len(schema_group)} data file(s) reduced to "
                    "schema only"
                ),
            )
            if on_progress is not None:
                on_progress("Fitting", "schema-only -> on")
            _reparse_records(schema_group, current, reparse)
            result = _attempt(current)

    # Step 8: cap unhandled text files to their first 10KB. DefaultParser's
    # head read is fixed at 10KB, so a lower threshold gains nothing.
    if _over_budget() and current.max_file_size > BUDGET_TEXT_FILE_SIZE_KB:
        text_group = _select_text_group(records, omitted, current)
        if text_group:
            requested_value = current.max_file_size
            current = replace(current, max_file_size=BUDGET_TEXT_FILE_SIZE_KB)
            if on_progress is not None:
                on_progress(
                    "Fitting", f"max-file-size -> {BUDGET_TEXT_FILE_SIZE_KB}"
                )
            _reparse_records(text_group, current, reparse)
            truncated = sum(
                1 for record in text_group
                if record.result.status == "Truncated"
            )
            adjustments["max-file-size"] = BudgetAdjustment(
                parameter="max-file-size",
                requested=str(requested_value),
                adjusted=str(BUDGET_TEXT_FILE_SIZE_KB),
                scope=f"{truncated} text file(s) truncated to their first 10KB",
            )
            result = _attempt(current)

    # Step 9: omission phase — last resort, no re-parsing. Sort remaining
    # included records heaviest-first (ties broken on path for determinism)
    # and drop the front of the list until the overshoot is covered.
    while _over_budget():
        included = [r for r in records if r.relative_path not in omitted]
        if not included:
            break
        included.sort(key=lambda r: (-r.result.tokens, r.relative_path))
        overshoot = result.tokens - threshold
        taken = 0
        for record in included:
            omitted.add(record.relative_path)
            omitted_list.append(
                (record.relative_path.replace("\\", "/"), record.result.tokens)
            )
            taken += record.result.tokens
            if taken >= overshoot:
                break
        result = _attempt(current)

    if result.tokens <= threshold:
        return BudgetOutcome(
            fits=True,
            final_output=result.text,
            total_tokens=result.tokens,
            method=result.method,
            report=result.report,
            files_data=result.files_data,
            stats=result.stats,
            summaries=result.summaries,
            config=current,
        )

    return BudgetOutcome(
        fits=False,
        final_output=None,
        total_tokens=result.tokens,
        method=result.method,
        report=result.report,
        files_data=result.files_data,
        stats=result.stats,
        summaries=result.summaries,
        config=current,
    )
