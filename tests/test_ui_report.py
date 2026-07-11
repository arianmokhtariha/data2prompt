"""
Contract tests for the pure report helpers in ui.py.

status_severity guards the fail-loud contract: any status the UI does not
recognize must surface as "error", never as silently fine. select_report_rows
guards the compact-report contract: a flagged file can never be hidden by the
top-N cut, the hidden count must be exact, and the caller's list must never
be mutated (the same list is reused by main.py after the report is printed).
bar_cells guards the report's proportional bars against the all-skipped run
(max of zero) and against small files rendering as nothing. bar_glyphs
guards the bar track itself: every cell must span exactly the configured
density width, or tracks would misalign across table rows.
summarize_composition guards the COMPOSITION chart: type variants must merge,
zero-token files must stay out, and overflow types must fold into an exact
"other" row.
cipher_mask guards the banner animation: frames must be deterministic (no
unseeded randomness can creep back in) and the wordmark silhouette must
survive the churn. spaced_caps guards the section headers' word gap.
"""

from data2prompt.parsers import FileSummary
from data2prompt.ui import (
    bar_cells,
    bar_glyphs,
    cipher_mask,
    select_report_rows,
    spaced_caps,
    status_severity,
    summarize_composition,
)


def _file(
    name: str,
    tokens: int,
    status: str = "Read",
    file_type: str = "Text",
) -> FileSummary:
    """Builds a minimal FileSummary row for report-selection tests."""
    return {
        "name": name, "type": file_type, "tokens": tokens, "status": status
    }


def test_unknown_status_is_error() -> None:
    """A status the UI has never seen must render as an error, not pass as
    fine — this is what surfaces a new parser status that was never wired
    into the severity sets."""
    assert status_severity("Some Future Status") == "error"
    assert status_severity("") == "error"


def test_known_statuses_map_to_expected_severity() -> None:
    """Every status the parsers emit today must land in its severity channel;
    a miscategorized status would color the report wrong and mislead the
    user about what happened."""
    for status in ("Read", "Sampled", "Cleaned", "Parsed", "Extracted"):
        assert status_severity(status) == "ok", status
    for status in (
        "Truncated",
        "Skipped (Binary)",
        "Skipped (Exclusion)",
        "Schema Only",
        "Redacted",
        "Skipped (Env)",
        "Skipped (No pyarrow)",
    ):
        assert status_severity(status) == "warn", status
    assert status_severity("Error") == "error"


def test_flagged_file_outside_top_n_is_still_shown() -> None:
    """A redacted env file with 0 tokens sits far below the top-N cut, but
    hiding it would conceal a security-relevant action from the user."""
    files = [_file(f"module_{i}.py", 1000 - i) for i in range(12)]
    files.append(_file(".env", 0, status="Redacted"))

    rows, hidden = select_report_rows(files, top_n=10)
    names = [row["name"] for row in rows]

    assert ".env" in names
    # 13 files total: 10 heaviest + 1 flagged shown, 2 clean files hidden.
    assert len(rows) == 11
    assert hidden == 2


def test_hidden_count_is_zero_when_everything_fits() -> None:
    files = [_file("a.py", 10), _file("b.py", 20)]
    rows, hidden = select_report_rows(files, top_n=10)
    assert len(rows) == 2
    assert hidden == 0


def test_rows_are_ordered_heaviest_first() -> None:
    files = [_file("small.py", 5), _file("big.py", 500), _file("mid.py", 50)]
    rows, _ = select_report_rows(files, top_n=10)
    assert [row["name"] for row in rows] == ["big.py", "mid.py", "small.py"]


def test_input_list_is_not_mutated() -> None:
    """main.py keeps using processed_files_info after the report; the old
    implementation sorted the caller's list in place."""
    files = [_file("a.py", 1), _file("b.py", 99), _file("c.py", 50)]
    snapshot = [dict(row) for row in files]

    select_report_rows(files, top_n=2)

    assert files == snapshot


def test_bar_is_zero_safe_when_everything_was_skipped() -> None:
    """A run where every file is flagged with 0 tokens gives the payload
    table a max of zero — the bar must render empty, not divide by zero."""
    assert bar_cells(0, 0, 8) == 0
    assert bar_cells(5, 0, 8) == 0


def test_tiny_nonzero_value_still_fills_one_cell() -> None:
    """A small file next to a huge one would round to an empty bar and look
    like missing data; any positive value must show at least one cell."""
    assert bar_cells(1, 100_000, 10) == 1


def test_bar_clamps_when_value_exceeds_reference() -> None:
    """An over-budget token gauge (tokens > context window) must cap at the
    bar width instead of overflowing the report layout."""
    assert bar_cells(300_000, 200_000, 10) == 10


def test_bar_glyphs_track_length_is_exact_at_every_density() -> None:
    """Every cell must occupy exactly cell_width columns. A ragged cell
    would misalign the bar tracks across table rows and break the
    cells-as-percentage reading; at density 1 the track must stay the
    contiguous ▰▱ run the report is designed around."""
    assert bar_glyphs(3, 5, 1) == ("▰▰▰", "▱▱")
    filled, empty = bar_glyphs(2, 4, 3)
    assert filled == "▰  ▰  "
    assert empty == "▱  ▱  "
    assert len(filled) + len(empty) == 4 * 3


def test_bar_glyphs_clamps_nonpositive_cell_width() -> None:
    """A misconfigured REPORT_BAR_CELL_WIDTH of 0 must degrade to density 1,
    not crash the final report with a negative string multiply."""
    assert bar_glyphs(1, 2, 0) == ("▰", "▱")


def test_composition_merges_parenthetical_type_variants() -> None:
    """Excel parse results embed the sheet count in the type string, so two
    workbooks arrive as different types; the chart must show one Excel row."""
    files = [
        _file("a.xlsx", 100, file_type="Excel (3 sheets)"),
        _file("b.xlsx", 50, file_type="Excel (5 sheets)"),
    ]
    rows = summarize_composition(files, max_rows=6)
    assert rows == [("Excel", 2, 150)]


def test_composition_drops_zero_token_files() -> None:
    """Skipped/excluded files contribute nothing to the prompt; showing
    them in COMPOSITION would misstate what the output contains."""
    files = [
        _file("data.csv", 200, file_type="CSV"),
        _file("logo.png", 0, "Skipped (Exclusion)", "Excluded (.png)"),
    ]
    rows = summarize_composition(files, max_rows=6)
    assert rows == [("CSV", 1, 200)]


def test_cipher_mask_preserves_silhouette_and_length() -> None:
    """A cipher glyph rendered over a space would distort the wordmark
    silhouette mid-animation; every space must stay a space and the line
    must never change length (a drift would shift the reveal edge)."""
    line = "█▀▀▄ ▄▀▀▄  ▀▀█▀▀"
    masked = cipher_mask(line, frame=3, row=1)

    assert len(masked) == len(line)
    for original, churned in zip(line, masked):
        if original == " ":
            assert churned == " "
        else:
            assert churned != " "


def test_cipher_mask_is_deterministic_but_churns_across_frames() -> None:
    """Animation frames must be pure functions of their inputs — identical
    inputs give identical output (reproducible frames, no hidden RNG) — but
    advancing frames must actually change the glyphs. This catches the
    degenerate-mix bug: a frame multiplier that is a multiple of the glyph
    count contributes nothing modulo it, freezing the churn into a static
    texture."""
    line = "█▄▄▀ ▀  ▀"
    assert (
        cipher_mask(line, frame=5, row=2) == cipher_mask(line, frame=5, row=2)
    )
    masks = {cipher_mask(line, frame=frame, row=2) for frame in range(8)}
    assert len(masks) > 1


def test_spaced_caps_keeps_word_gap() -> None:
    """A naive single join would fuse 'HEAVIEST PAYLOADS' into one word;
    words must stay separated by a double space so multi-word titles
    remain readable."""
    assert spaced_caps("HEAVIEST PAYLOADS") == (
        "H E A V I E S T  P A Y L O A D S"
    )
    assert spaced_caps("ATTENTION") == "A T T E N T I O N"


def test_composition_folds_overflow_into_other() -> None:
    """With more types than chart rows, the tail must fold into an exact
    "other" row — dropping it would silently understate the token total."""
    files = [
        _file(f"f{i}.x", 800 - i * 100, file_type=f"Type{i}") for i in range(8)
    ]
    rows = summarize_composition(files, max_rows=6)

    assert len(rows) == 6
    assert [tokens for _, _, tokens in rows[:-1]] == [800, 700, 600, 500, 400]
    # Types 5, 6, 7 fold together: 300 + 200 + 100 tokens across 3 files.
    assert rows[-1] == ("other", 3, 600)
