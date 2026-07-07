"""
Tests for DefaultParser — the fallback parser for all text files.

Covers the four branching paths in order of evaluation:
  1. Generated-output detection (GENERATION_FLAG in first 100 bytes → skip_file=True)
  2. Binary detection (null byte → Skipped (Binary))
  3. Large-file truncation (exceeds max_file_size → first 10 KB only)
  4. Normal read (full content, long-line truncation applied)
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from data2prompt.parsers import DefaultParser
from data2prompt.constants import GENERATION_FLAG


def _cfg(**overrides: object) -> SimpleNamespace:
    """Minimal Config stub for DefaultParser."""
    base = SimpleNamespace(
        max_file_size=100,          # KB
        line_length_threshold=500,
        truncated_line_length=100,
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ---------------------------------------------------------------------------
# 1. Generated-output detection
# ---------------------------------------------------------------------------

def test_default_parser_skips_generated_output_file() -> None:
    """A file whose first 100 bytes contain GENERATION_FLAG must be skipped entirely."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(f"<!-- {GENERATION_FLAG} -->\nrest of content here\n")
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg())
        assert result.status == "Skipped (Generated)"
        assert result.skip_file is True
        assert result.tokens == 0
    finally:
        path.unlink()


def test_default_parser_does_not_skip_file_without_flag() -> None:
    """A normal file must NOT be skipped regardless of its extension."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".md", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write("# Normal markdown document\nNo generation flag here.\n")
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg())
        assert result.skip_file is False
        assert result.status != "Skipped (Generated)"
    finally:
        path.unlink()


# ---------------------------------------------------------------------------
# 2. Binary detection
# ---------------------------------------------------------------------------

def test_default_parser_skips_binary_file() -> None:
    """A file containing a null byte must produce Skipped (Binary) with a note."""
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(b"some text \x00 more text")
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg())
        assert result.status == "Skipped (Binary)"
        assert "Binary" in result.content
        assert result.stats_update == {"binary_count": 1}
        assert result.tokens == 0
    finally:
        path.unlink()


# ---------------------------------------------------------------------------
# 3. Large-file truncation
# ---------------------------------------------------------------------------

def test_default_parser_truncates_file_exceeding_max_size() -> None:
    """Files larger than max_file_size KB are shown first 10 KB only."""
    # 100 KB of text — well above the 50 KB limit we set.
    large_content = "A" * (100 * 1024)
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(large_content)
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg(max_file_size=50))
        assert result.status == "Truncated"
        assert "File truncated" in result.content
        assert result.stats_update == {"truncated_count": 1}
        assert result.tokens > 0
    finally:
        path.unlink()


def test_default_parser_reads_file_at_exact_limit_fully() -> None:
    """A file whose size exactly equals max_file_size is NOT truncated."""
    # Write exactly 1 KB (1024 bytes).
    content = "B" * 1024
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(content)
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg(max_file_size=1))
        # file_size_kb == 1 and max_file_size == 1 → condition is >, not >=, so no truncation.
        assert result.status == "Read"
        assert "File truncated" not in result.content
    finally:
        path.unlink()


# ---------------------------------------------------------------------------
# 4. Normal read
# ---------------------------------------------------------------------------

def test_default_parser_reads_normal_text_file() -> None:
    """A small text file is read in full, status is 'Read', tokens > 0."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".py", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write("def hello():\n    return 'world'\n")
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg())
        assert result.status == "Read"
        assert "hello" in result.content
        assert result.tokens > 0
        assert result.stats_update == {}
    finally:
        path.unlink()


def test_default_parser_applies_long_line_truncation() -> None:
    """Lines exceeding line_length_threshold are truncated and annotated."""
    long_line = "X" * 600  # exceeds threshold of 500
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(long_line + "\n")
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(
            path,
            _cfg(line_length_threshold=500, truncated_line_length=100),
        )
        assert result.status == "Read"
        assert "Line truncated" in result.content
        # Exactly 100 X's kept, then the annotation.
        assert result.content.startswith("X" * 100)
    finally:
        path.unlink()


def test_default_parser_type_uses_extension() -> None:
    """The ParserResult type field reflects the file extension (without the dot)."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write("key: value\n")
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg())
        assert result.type == "yaml"
    finally:
        path.unlink()


def test_default_parser_no_extension_type_is_text() -> None:
    """Files without an extension get type='text'."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write("plain content\n")
        path = Path(tmp.name)
    try:
        result = DefaultParser().parse(path, _cfg())
        assert result.type == "text"
    finally:
        path.unlink()
