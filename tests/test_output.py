"""
Token-placeholder tests for the output generators.

These tests confirm the metadata token contract: generate() emits the literal
{{TOTAL_TOKENS}} / {{TOKEN_METHOD}} placeholders (it no longer receives a
pre-computed count), and the main.py substitution step (count_tokens + two
str.replace calls) resolves them to a real count + method with nothing left over.
"""

from typing import List, Tuple

import pytest

from data2prompt.output import MarkdownGenerator, OutputGenerator, XMLGenerator
from data2prompt.utils import count_tokens

# main.py builds each file dict with these keys; only path/content are read by
# the generators for plain-string content, but we mirror the full shape.
FilesData = List[dict]


def _sample_files() -> FilesData:
    """A single plain-text source file, enough to exercise the else branch."""
    return [
        {
            "path": "src/app.py",
            "content": "print('hello world')\n",
            "type": "Code",
            "tokens": 0,
            "status": "OK",
        }
    ]


def _render(generator: OutputGenerator) -> str:
    """Render a minimal project with the given generator (config defaults to None)."""
    return generator.generate(
        project_name="demo",
        tree_text="demo/\n  src/\n    app.py",
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
