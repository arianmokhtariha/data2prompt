"""
Structural and token-placeholder tests for the output generators.

Covers the metadata token contract ({{TOTAL_TOKENS}} / {{TOKEN_METHOD}}
placeholders resolved by the main.py substitution step), the File Index
(status vocabulary, Omitted entries, forward-slash path keys), the
document-level stats summary, and the end-of-codebase anchor.
"""

from pathlib import Path
from typing import List, Tuple
from types import SimpleNamespace

import pandas as pd
import pytest

from data2prompt.output import (
    MarkdownGenerator,
    OutputGenerator,
    XMLGenerator,
    get_generator,
)
from data2prompt.utils import count_tokens
from data2prompt.parsers import NotebookCellIR, TableIR, build_table_schema

# main.py builds each file dict with these keys; only path/content are read by
# the generators for plain-string content, but we mirror the full shape.
FilesData = List[dict]


def _sample_files() -> FilesData:
    """A single plain-text source file, enough to exercise the else branch."""
    return [
        {
            "path": "src/app.py",
            "content": "print('hello world')\n",
            "type": "py",
            "tokens": 0,
            "status": "Read",
        }
    ]


def _render(generator: OutputGenerator) -> str:
    """Render a minimal project with the given generator (config defaults to None)."""
    # tree_text is a flat list of real relative paths (the ProjectScanner
    # contract) — any non-matching line would surface as an Omitted index row.
    return generator.generate(
        project_name="demo",
        tree_text="src/app.py",
        files_data=_sample_files(),
        stats={},
    )


def _render_and_substitute(generator: OutputGenerator) -> Tuple[str, int, str]:
    """Render, then replay the main.py count-and-substitute step."""
    output = _render(generator)
    total_tokens, method = count_tokens(output)
    output = output.replace("{{TOTAL_TOKENS}}", str(total_tokens))
    output = output.replace("{{TOKEN_METHOD}}", method)
    return output, total_tokens, method


def test_markdown_generate_emits_token_placeholders() -> None:
    """MarkdownGenerator must emit the raw placeholders, not a pre-computed count."""
    output = _render(MarkdownGenerator())
    assert "{{TOTAL_TOKENS}}" in output
    assert "{{TOKEN_METHOD}}" in output
    assert "> Tokens: {{TOTAL_TOKENS}} (est. via {{TOKEN_METHOD}})" in output


def test_xml_generate_emits_token_placeholders() -> None:
    """XMLGenerator must emit the raw placeholders, not a pre-computed count."""
    output = _render(XMLGenerator())
    assert "{{TOTAL_TOKENS}}" in output
    assert "{{TOKEN_METHOD}}" in output
    assert (
        '<total_tokens method="{{TOKEN_METHOD}}">{{TOTAL_TOKENS}}</total_tokens>'
        in output
    )


def test_markdown_substitution_resolves_placeholders() -> None:
    """After substitution no placeholder remains and a positive count is embedded."""
    output, total_tokens, method = _render_and_substitute(MarkdownGenerator())
    assert "{{TOTAL_TOKENS}}" not in output
    assert "{{TOKEN_METHOD}}" not in output
    assert total_tokens > 0
    assert f"> Tokens: {total_tokens} (est. via {method})" in output


def test_xml_substitution_resolves_placeholders() -> None:
    """After substitution no placeholder remains and a positive count is embedded."""
    output, total_tokens, method = _render_and_substitute(XMLGenerator())
    assert "{{TOTAL_TOKENS}}" not in output
    assert "{{TOKEN_METHOD}}" not in output
    assert total_tokens > 0
    assert (
        f'<total_tokens method="{method}">{total_tokens}</total_tokens>' in output
    )


def test_generate_rejects_legacy_token_kwargs() -> None:
    """The total_tokens/token_method params are gone; passing them must error."""
    with pytest.raises(TypeError):
        MarkdownGenerator().generate(
            project_name="demo",
            tree_text="demo/",
            files_data=_sample_files(),
            stats={},
            total_tokens=5,
            token_method="o200k_base",
        )


# ---------------------------------------------------------------------------
# Notebook IR rendering
# ---------------------------------------------------------------------------

def _notebook_files() -> FilesData:
    cells = [
        NotebookCellIR(number=1, type="code", source="x = 42", outputs="42"),
        NotebookCellIR(number=2, type="markdown", source="# Section", outputs=None),
    ]
    return [{"path": "analysis.ipynb", "content": cells, "type": "Notebook", "tokens": 10, "status": "Cleaned"}]


def test_markdown_renders_notebook_cell_headers() -> None:
    """Each cell produces a '### Cell N (type)' header."""
    output = MarkdownGenerator().generate(
        project_name="demo",
        tree_text="analysis.ipynb",
        files_data=_notebook_files(),
        stats={},
    )
    assert "### Cell 1 (code)" in output
    assert "### Cell 2 (markdown)" in output


def test_markdown_renders_notebook_cell_source_and_outputs() -> None:
    """Cell source and outputs both appear in the rendered Markdown."""
    output = MarkdownGenerator().generate(
        project_name="demo",
        tree_text="analysis.ipynb",
        files_data=_notebook_files(),
        stats={},
    )
    # Scope to the Files section: the preamble also mentions the literal
    # `**Outputs:**` marker when documenting the reading conventions.
    files_section = output.split("# Files", 1)[1]
    assert "x = 42" in files_section
    assert "**Outputs:**" in files_section
    assert "42" in files_section


def test_markdown_notebook_cell_without_outputs_omits_outputs_block() -> None:
    """A cell with outputs=None must not emit an Outputs section."""
    output = MarkdownGenerator().generate(
        project_name="demo",
        tree_text="analysis.ipynb",
        files_data=_notebook_files(),
        stats={},
    )
    # Cell 2 is markdown with no outputs — only Cell 1 may emit an Outputs
    # block. Count within the Files section only: the preamble legitimately
    # contains the literal `**Outputs:**` marker in its reading conventions.
    files_section = output.split("# Files", 1)[1]
    assert files_section.count("**Outputs:**") == 1


def test_xml_renders_notebook_cells() -> None:
    """XMLGenerator wraps each cell in a <cell> tag with correct attributes."""
    output = XMLGenerator().generate(
        project_name="demo",
        tree_text="analysis.ipynb",
        files_data=_notebook_files(),
        stats={},
    )
    # Scope past the preamble: it mentions the literal <cell and <outputs>
    # markers when documenting the reading conventions.
    body = output.split("</purpose>", 1)[1]
    assert '<cell' in body
    assert 'type="code"' in body
    assert 'x = 42' in body
    assert '<outputs>' in body


# ---------------------------------------------------------------------------
# Table IR rendering — schema and data
# ---------------------------------------------------------------------------

def _table_files(
    schema_only: bool = False,
    stats_summary: bool = True,
) -> tuple[FilesData, SimpleNamespace]:
    df = pd.DataFrame({"name": ["alice", "bob"], "score": [1.0, 2.0]})
    schema = build_table_schema(df, include_describe=stats_summary)
    table = TableIR(name="scores.csv", df=df, schema=schema)
    files = [{"path": "scores.csv", "content": [table], "type": "CSV", "tokens": 0, "status": "Sampled"}]
    cfg = SimpleNamespace(
        table_limit=50_000,
        table_truncate=20_000,
        stats_summary=stats_summary,
        schema_only=schema_only,
    )
    return files, cfg


def test_markdown_renders_table_schema_block() -> None:
    """With stats_summary=True the Schema block appears above the data rows."""
    files, cfg = _table_files(stats_summary=True)
    output = MarkdownGenerator().generate(
        project_name="demo", tree_text="scores.csv",
        files_data=files, stats={}, config=cfg,
    )
    assert "**Schema**" in output
    assert "name" in output
    assert "score" in output


def test_markdown_schema_only_drops_data_rows() -> None:
    """With schema_only=True the actual data values must not appear in output."""
    files, cfg = _table_files(schema_only=True, stats_summary=False)
    output = MarkdownGenerator().generate(
        project_name="demo", tree_text="scores.csv",
        files_data=files, stats={}, config=cfg,
    )
    assert "alice" not in output
    assert "bob" not in output
    assert "**Schema**" in output


def test_xml_renders_table_schema_block() -> None:
    """XMLGenerator wraps the schema block in <schema> tags."""
    files, cfg = _table_files(stats_summary=True)
    output = XMLGenerator().generate(
        project_name="demo", tree_text="scores.csv",
        files_data=files, stats={}, config=cfg,
    )
    # Scope past the preamble: it mentions the literal <schema> marker.
    body = output.split("</purpose>", 1)[1]
    assert "<schema>" in body
    assert "name" in body


def test_xml_schema_only_drops_data_rows() -> None:
    """XMLGenerator schema_only: data cell values absent, schema present."""
    files, cfg = _table_files(schema_only=True, stats_summary=False)
    output = XMLGenerator().generate(
        project_name="demo", tree_text="scores.csv",
        files_data=files, stats={}, config=cfg,
    )
    assert "alice" not in output
    assert "bob" not in output
    # Scope past the preamble: it mentions the literal <schema> marker.
    assert "<schema>" in output.split("</purpose>", 1)[1]


# ---------------------------------------------------------------------------
# XML attribute safety — user data must never break tag structure
# ---------------------------------------------------------------------------

def test_xml_sheet_name_with_quotes_and_angle_brackets_is_quoted() -> None:
    """A sheet named `Q1 "final" <rev>` must be attribute-escaped, otherwise the
    raw quote terminates the attribute and the tag structure collapses."""
    df = pd.DataFrame({"x": [1]})
    table = TableIR(
        name='Q1 "final" <rev>',
        df=df,
        sheet_number=1,
        file_path="book.xlsx",
    )
    files = [{"path": "book.xlsx", "content": [table], "type": "Excel", "tokens": 0, "status": "Extracted"}]
    cfg = SimpleNamespace(
        table_limit=50_000, table_truncate=20_000,
        stats_summary=False, schema_only=False,
    )

    output = XMLGenerator().generate(
        project_name="demo", tree_text="book.xlsx",
        files_data=files, stats={}, config=cfg,
    )

    # The raw, unescaped attribute must not appear...
    assert '<sheet name="Q1 "final" <rev>"' not in output
    # ...and the quoteattr form must: values containing double quotes are
    # single-quoted, and angle brackets are entity-escaped.
    assert "name='Q1 \"final\" &lt;rev&gt;'" in output


def test_xml_file_path_with_ampersand_is_quoted() -> None:
    """Paths containing & (e.g. 'R&D/data.csv') must be escaped in attributes."""
    files = [{
        "path": "R&D/report.txt",
        "content": "quarterly numbers",
        "type": "text",
        "tokens": 0,
        "status": "Read",
    }]
    output = XMLGenerator().generate(
        project_name="demo", tree_text="R&D/report.txt",
        files_data=files, stats={},
    )
    assert 'path="R&amp;D' in output


# ---------------------------------------------------------------------------
# File Index — status vocabulary, Omitted entries, path keys
# ---------------------------------------------------------------------------

def _status_files() -> FilesData:
    """One file per raw status that must map onto the index vocabulary."""
    raw = [
        ("src/app.py", "py", "Read"),
        ("data/sales.csv", "CSV", "Sampled"),
        ("blob.bin", "Binary (.bin)", "Skipped (Binary)"),
        ("logo.png", "Excluded (.png)", "Skipped (Exclusion)"),
        (".env", "Env", "Redacted"),
    ]
    return [
        {"path": p, "content": "x", "type": t, "tokens": 0, "status": s}
        for p, t, s in raw
    ]


def test_markdown_file_index_maps_statuses() -> None:
    """Raw parser statuses render as the controlled index vocabulary."""
    files = _status_files()
    tree = "\n".join(f["path"] for f in files)
    output = MarkdownGenerator().generate(
        project_name="demo", tree_text=tree, files_data=files, stats={},
    )
    assert "# File Index" in output
    assert "# Directory Structure" not in output
    assert "| src/app.py | py | Full |" in output
    assert "| data/sales.csv | CSV | Sampled |" in output
    assert "| blob.bin | Binary (.bin) | Binary Skipped |" in output
    assert "| logo.png | Excluded (.png) | Excluded |" in output
    assert "| .env | Env | Redacted |" in output


def test_index_lists_tree_only_files_as_omitted() -> None:
    """A tree path with no rendered section must appear as Omitted — and only
    in the index, never as a content section."""
    files = _sample_files()
    tree = "old/PROMPT.md\nsrc/app.py"

    md = MarkdownGenerator().generate(
        project_name="demo", tree_text=tree, files_data=files, stats={},
    )
    assert "| old/PROMPT.md | - | Omitted |" in md
    assert "## File: old/PROMPT.md" not in md

    xml = XMLGenerator().generate(
        project_name="demo", tree_text=tree, files_data=files, stats={},
    )
    assert '<entry path="old/PROMPT.md" type="-" status="Omitted"/>' in xml
    assert '<file path="old/PROMPT.md"' not in xml


def test_paths_render_with_forward_slashes() -> None:
    """An OS-native relative path (backslashes on Windows) must render with
    forward slashes in the index, the file header, and the XML path attribute
    — one exact key. main.py passes str(Path), so the input is OS-native."""
    files = [{
        "path": str(Path("src") / "pkg" / "app.py"),
        "content": "x = 1",
        "type": "py",
        "tokens": 0,
        "status": "Read",
    }]
    tree = "src/pkg/app.py"

    md = MarkdownGenerator().generate(
        project_name="demo", tree_text=tree, files_data=files, stats={},
    )
    assert "## File: src/pkg/app.py" in md
    assert "| src/pkg/app.py | py | Full |" in md
    assert "src\\pkg" not in md

    xml = XMLGenerator().generate(
        project_name="demo", tree_text=tree, files_data=files, stats={},
    )
    assert '<file path="src/pkg/app.py"' in xml
    assert '<entry path="src/pkg/app.py"' in xml
    # No stray Omitted row: the normalized path must match the tree line.
    assert 'status="Omitted"' not in xml


def test_xml_file_tag_carries_type_and_status() -> None:
    """<file> elements expose quoted type/status attributes with the resolved
    vocabulary, even when the path needs entity escaping."""
    files = [{
        "path": "R&D/report.txt",
        "content": "quarterly numbers",
        "type": "txt",
        "tokens": 0,
        "status": "Read",
    }]
    output = XMLGenerator().generate(
        project_name="demo", tree_text="R&D/report.txt",
        files_data=files, stats={},
    )
    assert '<file path="R&amp;D/report.txt" type="txt" status="Full">' in output


# ---------------------------------------------------------------------------
# Metadata stats summary and end-of-codebase anchor
# ---------------------------------------------------------------------------

def test_metadata_stats_renders_only_nonzero_counts() -> None:
    """Zero counts are dropped; Total files always renders."""
    stats = {"file_count": 3, "csv_count": 2, "sql_count": 0, "binary_count": 1}

    md = MarkdownGenerator().generate(
        project_name="demo", tree_text="src/app.py",
        files_data=_sample_files(), stats=stats,
    )
    assert "> Contents: Total files: 3 | CSV: 2 | Binary skipped: 1" in md
    assert "SQL:" not in md  # zero count must not render anywhere

    xml = XMLGenerator().generate(
        project_name="demo", tree_text="src/app.py",
        files_data=_sample_files(), stats=stats,
    )
    assert '<stats total_files="3" csv="2" binary_skipped="1"/>' in xml


def test_metadata_total_files_falls_back_to_rendered_count() -> None:
    """With an empty stats dict (programmatic callers) Total files still
    renders, derived from the number of rendered files."""
    md = _render(MarkdownGenerator())
    assert "> Contents: Total files: 1" in md


def test_end_anchor_is_final_section() -> None:
    """Both formats must end on the explicit end-of-codebase anchor."""
    md = _render(MarkdownGenerator())
    assert "# End of codebase: demo" in md
    assert md.rstrip().endswith(
        "content marked sampled, truncated, or omitted is not fully included "
        "in this document."
    )

    xml = _render(XMLGenerator())
    tail = [line for line in xml.splitlines() if line.strip()][-2:]
    assert tail == ["</end_of_codebase>", "</codebase>"]
    assert "<end_of_codebase>" in xml


def test_prose_line_and_malformed_heading_gone() -> None:
    """The stray prose line and the old malformed heading must not resurface."""
    for generator in (MarkdownGenerator(), XMLGenerator()):
        output = _render(generator)
        assert "This section contains the contents" not in output
    md = _render(MarkdownGenerator())
    assert "## Purpose" in md
    assert "## purpose:" not in md


# ---------------------------------------------------------------------------
# get_generator — strict format dispatch
# ---------------------------------------------------------------------------

def test_get_generator_returns_correct_strategies() -> None:
    assert isinstance(get_generator("markdown"), MarkdownGenerator)
    assert isinstance(get_generator("XML"), XMLGenerator)  # case-insensitive


def test_get_generator_rejects_unknown_format() -> None:
    """An unknown format must fail loudly, not silently fall back to XML."""
    with pytest.raises(ValueError, match="Unsupported output format"):
        get_generator("pdf")
