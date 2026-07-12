import pandas as pd
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Type, TYPE_CHECKING
from pathlib import Path
from xml.sax.saxutils import quoteattr

if TYPE_CHECKING:
    from data2prompt.cli import Config
    # Imported only for type hints — a runtime import would cycle, since
    # budget.py imports this module for get_generator().
    from data2prompt.budget import BudgetReport

from data2prompt.constants import (
    TAG_FILES,
    TAG_FILE,
    TAG_CONTENT,
    TAG_FILE_INDEX,
    TAG_INDEX_ENTRY,
    TAG_END_OF_CODEBASE,
    TAG_BUDGET_REPORT,
    TAG_ADJUSTMENT,
    TAG_OMITTED_FILE,
    INCLUSION_STATUS_MAP,
    STATS_SUMMARY_LABELS,
    SYSTEM_INSTRUCTIONS_MARKDOWN,
    SYSTEM_INSTRUCTIONS_XML,
    GENERATION_FLAG
)
from data2prompt.utils import get_dynamic_wrapper
from data2prompt.parsers import (
    NotebookCellIR,
    TableIR,
    FileData,
    enforce_table_limit,
    render_schema_block,
)


@dataclass(frozen=True)
class IndexEntry:
    """One File Index row: the canonical path key plus type and status."""
    path: str
    type: str
    status: str


def _display_path(rel_path: str) -> str:
    """Project-relative path with forward slashes.

    This string is the canonical path key: identical in the File Index, the
    Markdown ``## File:`` headers, and the XML ``path`` attributes, so an LLM
    can cross-reference sections by exact match.
    """
    return Path(rel_path).as_posix()


def resolve_inclusion_status(status: str) -> str:
    """Map a raw parser status onto the controlled File Index vocabulary.

    Unmapped ``Skipped (...)`` variants collapse to ``Skipped``; anything else
    unknown passes through verbatim, so a future status never breaks a run.
    """
    mapped = INCLUSION_STATUS_MAP.get(status)
    if mapped is not None:
        return mapped
    if status.startswith("Skipped"):
        return "Skipped"
    return status


def build_file_index(
    tree_text: str,
    files_data: List[FileData],
) -> List[IndexEntry]:
    """Build the File Index from rendered files plus tree-only leftovers.

    Rendered files come first, in document order (index order matches the
    order of the file sections). Paths present in the tree but not rendered
    (e.g. previously generated outputs) are appended as ``Omitted`` so every
    scanned file is accounted for.
    """
    entries: List[IndexEntry] = []
    rendered_paths = set()
    for file_info in files_data:
        path = _display_path(file_info['path'])
        rendered_paths.add(path)
        entries.append(IndexEntry(
            path=path,
            type=file_info['type'],
            status=resolve_inclusion_status(file_info['status']),
        ))
    leftovers = sorted(
        line.strip()
        for line in tree_text.splitlines()
        if line.strip() and line.strip() not in rendered_paths
    )
    entries.extend(
        IndexEntry(path=path, type="-", status="Omitted") for path in leftovers
    )
    return entries


def summarize_stats(
    stats: Dict[str, int],
    file_total: int,
) -> List[Tuple[str, int]]:
    """(label, count) pairs for the content summary.

    Order follows ``STATS_SUMMARY_LABELS``. ``Total files`` is always present
    (falling back to ``file_total`` when the stat is missing or zero); other
    zero counts are dropped to save tokens.
    """
    pairs: List[Tuple[str, int]] = []
    for key, label in STATS_SUMMARY_LABELS.items():
        if key == "file_count":
            pairs.append((label, stats.get(key) or file_total))
            continue
        count = stats.get(key, 0)
        if count:
            pairs.append((label, count))
    return pairs


def _end_recap(project_name: str, indexed_count: int) -> str:
    """One-sentence closing recap shared by both output formats."""
    return (
        f"This concludes the data2prompt snapshot of {project_name}. The File "
        f"Index above lists all {indexed_count} files; content marked sampled, "
        "truncated, or omitted is not fully included in this document."
    )


def _md_cell(text: str) -> str:
    """Escape pipes so a value can sit inside a Markdown table cell."""
    return text.replace("|", "\\|")


def _budget_block_markdown(report: 'BudgetReport') -> List[str]:
    """Render the Budget Report section as Markdown lines.

    Emitted between the metadata block and the File Index only when a
    token budget was requested. Mirrors ``_budget_block_xml`` so both
    formats carry the same information (format parity).
    """
    lines = [
        "# Budget Report",
        "",
        f"Requested budget: {report.requested_tokens:,} tokens.",
        "",
    ]

    if report.adjustments:
        lines.append(
            "Data-cap parameters tightened to fit the budget (the Tokens "
            "line above is the final count):"
        )
        lines.append("")
        lines.append("| Parameter | Requested | Adjusted | Scope |")
        lines.append("|---|---|---|---|")
        for adjustment in report.adjustments:
            lines.append(
                f"| {_md_cell(adjustment.parameter)} "
                f"| {_md_cell(adjustment.requested)} "
                f"| {_md_cell(adjustment.adjusted)} "
                f"| {_md_cell(adjustment.scope)} |"
            )
    else:
        lines.append(
            "No parameter adjustments were needed - the document fit as "
            "generated."
        )
    lines.append("")

    if report.omitted:
        lines.append(
            "Files omitted entirely to meet the budget (status Omitted in "
            "the File Index):"
        )
        lines.append("")
        lines.append("| Path | Est. tokens |")
        lines.append("|---|---|")
        for path, tokens in report.omitted:
            lines.append(f"| {_md_cell(path)} | {tokens:,} |")
        lines.append("")

    return lines


def _budget_block_xml(report: 'BudgetReport') -> List[str]:
    """Render the Budget Report section as XML lines.

    Emitted between ``</metadata>`` and ``<file_index>`` only when a token
    budget was requested. Mirrors ``_budget_block_markdown`` so both
    formats carry the same information (format parity). Numeric attributes
    are plain digits (no thousands separators inside XML attributes).
    """
    if not report.adjustments and not report.omitted:
        return [
            f'<{TAG_BUDGET_REPORT} '
            f'requested_tokens="{report.requested_tokens}"/>'
        ]

    lines = [
        f'<{TAG_BUDGET_REPORT} requested_tokens="{report.requested_tokens}">'
    ]
    for adjustment in report.adjustments:
        lines.append(
            f'    <{TAG_ADJUSTMENT} '
            f'parameter={quoteattr(adjustment.parameter)} '
            f'requested={quoteattr(adjustment.requested)} '
            f'adjusted={quoteattr(adjustment.adjusted)} '
            f'scope={quoteattr(adjustment.scope)}/>'
        )
    for path, tokens in report.omitted:
        lines.append(
            f'    <{TAG_OMITTED_FILE} path={quoteattr(path)} '
            f'estimated_tokens="{tokens}"/>'
        )
    lines.append(f'</{TAG_BUDGET_REPORT}>')
    return lines


class OutputGenerator(ABC):
    @abstractmethod
    def generate(self,
                 project_name: str,
                 tree_text: str,
                 files_data: List[FileData],
                 stats: Dict[str, int],
                 config: Optional['Config'] = None,
                 budget_report: Optional['BudgetReport'] = None) -> str:
        pass

class MarkdownGenerator(OutputGenerator):
    def generate(self,
                 project_name: str,
                 tree_text: str,
                 files_data: List[FileData],
                 stats: Dict[str, int],
                 config: Optional['Config'] = None,
                 budget_report: Optional['BudgetReport'] = None) -> str:

        timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')

        # Independent table flags: stats block (#4) and schema-only data drop (#3).
        stats_summary = bool(config and config.stats_summary)
        schema_only = bool(config and config.schema_only)
        render_block = stats_summary or schema_only
        render_data = not schema_only

        index_entries = build_file_index(tree_text, files_data)
        stat_pairs = summarize_stats(stats, len(files_data))
        contents_line = " | ".join(f"{label}: {count}" for label, count in stat_pairs)

        lines = [
            f"<!-- {GENERATION_FLAG} -->",
            "",
            f"# codebase: {project_name}",
            "",
            SYSTEM_INSTRUCTIONS_MARKDOWN,
            "",
            f"> Generated on: {timestamp}",
            # Placeholders substituted by main.py once the full output is counted.
            "> Tokens: {{TOTAL_TOKENS}} (est. via {{TOKEN_METHOD}})",
            f"> Contents: {contents_line}",
            "",
        ]
        if budget_report is not None:
            lines.extend(_budget_block_markdown(budget_report))
        lines.extend([
            "# File Index",
            "",
            "| Path | Type | Status |",
            "|---|---|---|",
        ])
        for entry in index_entries:
            lines.append(
                f"| {_md_cell(entry.path)} | {_md_cell(entry.type)} "
                f"| {_md_cell(entry.status)} |"
            )
        lines.extend(["", "# Files", ""])

        for file_info in files_data:
            rel_path = file_info['path']
            content = file_info['content']
            ext = Path(rel_path).suffix.lower()
            # Canonical forward-slash path — exact match with the File Index.
            display_path = _display_path(rel_path)

            lines.append(f"## File: {display_path}")

            if isinstance(content, list) and content and isinstance(content[0], NotebookCellIR):
                # Render Notebook IR
                for cell in content:
                    lines.append(f"### Cell {cell.number} ({cell.type}) - {display_path}")
                    wrapper = get_dynamic_wrapper(cell.source)
                    lang = 'python' if cell.type == 'code' else 'markdown'
                    lines.append(f"{wrapper}{lang}")
                    lines.append(cell.source)
                    lines.append(wrapper)

                    if cell.outputs:
                        lines.append("\n**Outputs:**")
                        lines.append("```text")
                        lines.append(cell.outputs)
                        lines.append("```")
                    lines.append("")

            elif isinstance(content, list) and content and isinstance(content[0], TableIR):
                # Render Table IR (CSV/Excel/SQLite)
                for table in content:
                    # Sub-section heading (Excel sheets, SQLite tables)
                    if table.sheet_number is not None:
                        lines.append(
                            f"### {table.section_label} {table.sheet_number}: "
                            f"{table.name} - {table.file_path}"
                        )

                    # DDL (SQLite CREATE statements) — gated like the schema block.
                    if render_block and table.ddl:
                        lines.append("```sql")
                        lines.append(table.ddl)
                        lines.append("```")
                        lines.append("")

                    # Schema / stats metadata block (computed on the full df)
                    if render_block and table.schema is not None:
                        lines.append(render_schema_block(
                            table.schema,
                            show_missing=stats_summary,
                            show_describe=stats_summary,
                        ))
                        lines.append("")

                    table_parts = []
                    if table.header_note:
                        table_parts.append(table.header_note)

                    if render_data and not table.df.empty:
                        table_parts.append(table.df.to_markdown(index=False))

                    if table.footer_note:
                        table_parts.append(table.footer_note)

                    table_text = "\n".join(table_parts)
                    if config:
                        table_text = enforce_table_limit(table_text, config.table_limit, config.table_truncate)

                    lines.append(table_text)

                    # Close Sheet block if applicable
                    if table.sheet_number is not None:
                        lines.append("---")

                    lines.append("")

            else:
                # Standard files or fallback string content
                str_content = str(content)
                wrapper = get_dynamic_wrapper(str_content)
                if ext == '.md':
                    lang = 'markdown'
                elif ext:
                    lang = ext[1:]
                else:
                    lang = 'text'
                lines.append(f"{wrapper}{lang}")
                lines.append(str_content)
                lines.append(wrapper)

            lines.append("")

        # Recency anchor: an explicit terminal section so the model knows the
        # document is complete and nothing was cut off mid-file.
        lines.append(f"# End of codebase: {project_name}")
        lines.append("")
        lines.append(_end_recap(project_name, len(index_entries)))

        return "\n".join(lines)

class XMLGenerator(OutputGenerator):
    def generate(self,
                 project_name: str,
                 tree_text: str,
                 files_data: List[FileData],
                 stats: Dict[str, int],
                 config: Optional['Config'] = None,
                 budget_report: Optional['BudgetReport'] = None) -> str:

        timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')

        # Independent table flags: stats block (#4) and schema-only data drop (#3).
        stats_summary = bool(config and config.stats_summary)
        schema_only = bool(config and config.schema_only)
        render_block = stats_summary or schema_only
        render_data = not schema_only

        index_entries = build_file_index(tree_text, files_data)
        stat_pairs = summarize_stats(stats, len(files_data))
        stats_attrs = " ".join(
            f'{label.lower().replace(" ", "_")}="{count}"'
            for label, count in stat_pairs
        )

        lines = [
            f"<!-- {GENERATION_FLAG} -->",
            "",
            f'<codebase name={quoteattr(project_name)}>',
            "",
            SYSTEM_INSTRUCTIONS_XML,
            "",
            "<metadata>",
            f"    <generated_on>{timestamp}</generated_on>",
            # Placeholders substituted by main.py once the full output is counted.
            '    <total_tokens method="{{TOKEN_METHOD}}">{{TOTAL_TOKENS}}</total_tokens>',
            f"    <stats {stats_attrs}/>",
            "</metadata>",
            "",
        ]
        if budget_report is not None:
            lines.extend(_budget_block_xml(budget_report))
            lines.append("")
        lines.append(f"<{TAG_FILE_INDEX}>")
        for entry in index_entries:
            lines.append(
                f'    <{TAG_INDEX_ENTRY} path={quoteattr(entry.path)} '
                f'type={quoteattr(entry.type)} '
                f'status={quoteattr(entry.status)}/>'
            )
        lines.extend([
            f"</{TAG_FILE_INDEX}>",
            "",
            f"<{TAG_FILES}>",
            ""
        ])

        for file_info in files_data:
            rel_path = file_info['path']
            content = file_info['content']
            # Canonical forward-slash path — exact match with the file index.
            display_path = _display_path(rel_path)

            # Attribute values come from user data (paths, sheet names) — quoteattr
            # keeps a name like `Q1 "final" <rev>` from breaking the tag structure.
            # status carries the resolved vocabulary so it cross-references the
            # file index exactly.
            lines.append(
                f'<{TAG_FILE} path={quoteattr(display_path)} '
                f'type={quoteattr(file_info["type"])} '
                f'status={quoteattr(resolve_inclusion_status(file_info["status"]))}>'
            )

            if isinstance(content, list) and content and isinstance(content[0], NotebookCellIR):
                # Render Notebook IR to XML
                for cell in content:
                    lines.append(
                        f'    <cell path={quoteattr(display_path)} '
                        f'index="{cell.number}" type={quoteattr(cell.type)}>'
                    )
                    lines.append(f'        <{TAG_CONTENT}>')
                    lines.append(cell.source)
                    lines.append(f'        </{TAG_CONTENT}>')
                    if cell.outputs:
                        lines.append('        <outputs>')
                        lines.append(cell.outputs)
                        lines.append('        </outputs>')
                    lines.append('    </cell>')

            elif isinstance(content, list) and content and isinstance(content[0], TableIR):
                # Render Table IR to XML
                for table in content:
                    # Sub-section element (Excel <sheet>, SQLite <table>)
                    tag = table.section_label.lower()
                    if table.sheet_number is not None:
                        lines.append(
                            f'<{tag} name={quoteattr(table.name)} '
                            f'{tag}_number="{table.sheet_number}" '
                            f'path={quoteattr(table.file_path or "")}>'
                        )

                    # DDL (SQLite CREATE statements) — gated like the schema block.
                    if render_block and table.ddl:
                        lines.append('<ddl>')
                        lines.append(table.ddl)
                        lines.append('</ddl>')

                    # Schema / stats metadata block (computed on the full df)
                    if render_block and table.schema is not None:
                        lines.append('<schema>')
                        lines.append(render_schema_block(
                            table.schema,
                            show_missing=stats_summary,
                            show_describe=stats_summary,
                        ))
                        lines.append('</schema>')

                    table_parts = []
                    if table.header_note:
                        table_parts.append(table.header_note)

                    if render_data and not table.df.empty:
                        table_parts.append(table.df.to_markdown(index=False))

                    if table.footer_note:
                        table_parts.append(table.footer_note)

                    table_text = "\n".join(table_parts)
                    if config:
                        table_text = enforce_table_limit(table_text, config.table_limit, config.table_truncate)

                    lines.append(table_text)

                    # Close the sub-section element if applicable
                    if table.sheet_number is not None:
                        lines.append(f'</{tag}>')

            else:
                # Standard files or fallback string content
                lines.append(str(content))

            lines.append(f"</{TAG_FILE}>")
            lines.append("")

        lines.append(f"</{TAG_FILES}>")
        lines.append("")
        # Recency anchor: an explicit terminal element so the model knows the
        # document is complete and nothing was cut off mid-file.
        lines.append(f"<{TAG_END_OF_CODEBASE}>")
        lines.append(_end_recap(project_name, len(index_entries)))
        lines.append(f"</{TAG_END_OF_CODEBASE}>")
        lines.append("</codebase>")

        return "\n".join(lines)

# Explicit strategy mapping — get_generator refuses unknown formats instead of
# silently defaulting, so a wiring mistake fails loudly at the source.
_GENERATORS: Dict[str, Type[OutputGenerator]] = {
    'markdown': MarkdownGenerator,
    'xml': XMLGenerator,
}


def get_generator(format_type: str) -> OutputGenerator:
    """Return the output strategy for ``format_type`` ('markdown' or 'xml')."""
    generator_cls = _GENERATORS.get(format_type.lower())
    if generator_cls is None:
        supported = ", ".join(sorted(_GENERATORS))
        raise ValueError(
            f"Unsupported output format: {format_type!r} (supported: {supported})"
        )
    return generator_cls()
