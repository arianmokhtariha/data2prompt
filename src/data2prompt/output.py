import os
import pandas as pd
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, TYPE_CHECKING
from pathlib import Path
from xml.sax.saxutils import escape, quoteattr

if TYPE_CHECKING:
    from .cli import Config

from .constants import (
    TAG_DIRECTORY_STRUCTURE,
    TAG_FILES,
    TAG_FILE,
    TAG_CONTENT,
    SYSTEM_INSTRUCTIONS_MARKDOWN,
    SYSTEM_INSTRUCTIONS_XML,
    GENERATION_FLAG
)
from .utils import get_dynamic_wrapper
from .parsers import (
    NotebookCellIR,
    TableIR,
    FileData,
    enforce_table_limit,
    render_schema_block,
)

class OutputGenerator(ABC):
    @abstractmethod
    def generate(self,
                 project_name: str,
                 tree_text: str,
                 files_data: List[FileData],
                 stats: Dict[str, int],
                 config: Optional['Config'] = None) -> str:
        pass

class MarkdownGenerator(OutputGenerator):
    def generate(self,
                 project_name: str,
                 tree_text: str,
                 files_data: List[FileData],
                 stats: Dict[str, int],
                 config: Optional['Config'] = None) -> str:

        timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')

        # Independent table flags: stats block (#4) and schema-only data drop (#3).
        stats_summary = bool(config and config.stats_summary)
        schema_only = bool(config and config.schema_only)
        render_block = stats_summary or schema_only
        render_data = not schema_only

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
            "",
            "# Directory Structure",
            "```text",
            tree_text,
            "```",
            "",
            "# Files",
            "",
            "This section contains the contents of the repository's files.",
            ""
        ]
        
        for file_info in files_data:
            rel_path = file_info['path']
            # Normalize path to match directory structure (always use backslashes)
            display_path = rel_path.replace(os.sep, '\\')
            content = file_info['content']
            ext = Path(rel_path).suffix.lower()
            
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
                # Render Table IR (CSV/Excel)
                for table in content:
                    # Handle Excel Sheet Metadata
                    if table.sheet_number is not None:
                        lines.append(f"### Sheet {table.sheet_number}: {table.name} - {table.file_path}")

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
                lang = ext[1:] if ext and ext != '.md' else 'markdown' if ext == '.md' else 'text'
                lines.append(f"{wrapper}{lang}")
                lines.append(str_content)
                lines.append(wrapper)
            
            lines.append("")
            
        return "\n".join(lines)

class XMLGenerator(OutputGenerator):
    def generate(self,
                 project_name: str,
                 tree_text: str,
                 files_data: List[FileData],
                 stats: Dict[str, int],
                 config: Optional['Config'] = None) -> str:

        timestamp = pd.Timestamp.now().strftime('%Y-%m-%d %H:%M')

        # Independent table flags: stats block (#4) and schema-only data drop (#3).
        stats_summary = bool(config and config.stats_summary)
        schema_only = bool(config and config.schema_only)
        render_block = stats_summary or schema_only
        render_data = not schema_only

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
            "</metadata>",
            "",
            f"<{TAG_DIRECTORY_STRUCTURE}>",
            escape(tree_text),
            f"</{TAG_DIRECTORY_STRUCTURE}>",
            "",
            f"<{TAG_FILES}>",
            "This section contains the contents of the repository's files.",
            ""
        ]
        
        for file_info in files_data:
            rel_path = file_info['path']
            # Normalize path to match directory structure (always use backslashes)
            display_path = rel_path.replace(os.sep, '\\')
            content = file_info['content']
            
            lines.append(f'<{TAG_FILE} path="{display_path}">')
            
            if isinstance(content, list) and content and isinstance(content[0], NotebookCellIR):
                # Render Notebook IR to XML
                for cell in content:
                    lines.append(f'    <cell path="{display_path}" index="{cell.number}" type="{cell.type}">')
                    lines.append(f'        <{TAG_CONTENT}>')
                    lines.append(escape(cell.source))
                    lines.append(f'        </{TAG_CONTENT}>')
                    if cell.outputs:
                        lines.append('        <outputs>')
                        lines.append(escape(cell.outputs))
                        lines.append('        </outputs>')
                    lines.append('    </cell>')
            
            elif isinstance(content, list) and content and isinstance(content[0], TableIR):
                # Render Table IR to XML
                for table in content:
                    # Handle Excel Sheet Metadata
                    if table.sheet_number is not None:
                        lines.append(f'<sheet name="{table.name}" sheet_number="{table.sheet_number}" path="{table.file_path}">')

                    # Schema / stats metadata block (computed on the full df)
                    if render_block and table.schema is not None:
                        lines.append('<schema>')
                        lines.append(escape(render_schema_block(
                            table.schema,
                            show_missing=stats_summary,
                            show_describe=stats_summary,
                        )))
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

                    lines.append(escape(table_text))

                    # Close Sheet block if applicable
                    if table.sheet_number is not None:
                        lines.append('</sheet>')
            
            else:
                # Standard files or fallback string content
                lines.append(str(content))
            
            lines.append(f"</{TAG_FILE}>")
            lines.append("")
            
        lines.append(f"</{TAG_FILES}>")
        lines.append("</codebase>")
        
        return "\n".join(lines)

def get_generator(format_type: str) -> OutputGenerator:
    if format_type.lower() == 'markdown':
        return MarkdownGenerator()
    return XMLGenerator()
