"""
Routing tests for process_target_file in main.py.

These tests confirm the security invariant: all .env-family filenames reach
EnvParser (status "Redacted") and can never fall through to the skip_exts
path (status "Skipped (Exclusion)"), regardless of what skip_exts contains.
"""

import tempfile
from pathlib import Path
from types import SimpleNamespace

from data2prompt.main import process_target_file
from data2prompt.constants import CORE_SKIP_EXTS


def _env_cfg(**overrides: object) -> SimpleNamespace:
    """Minimal config stub sufficient for process_target_file env routing."""
    base = SimpleNamespace(skip_exts=set(CORE_SKIP_EXTS), env_keys=True)
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


def _write_env_file(directory: str, name: str) -> Path:
    """Write a named env file inside *directory* and return its Path."""
    path = Path(directory) / name
    path.write_text("API_KEY=secret\nDB_PASS=hunter2\n", encoding="utf-8")
    return path


def test_bare_dot_env_routes_to_env_parser() -> None:
    """A bare .env file must route to EnvParser (status 'Redacted'), not to skip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = _write_env_file(tmpdir, ".env")
        result = process_target_file(env_file, _env_cfg())

        assert result.type == "Env"
        assert result.status == "Redacted", f"Expected 'Redacted', got '{result.status}'"
        assert result.status != "Skipped (Exclusion)"
        assert result.stats_update == {"env_count": 1}


def test_config_env_routes_to_env_parser() -> None:
    """config.env (suffix-style) must route to EnvParser, not to skip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = _write_env_file(tmpdir, "config.env")
        result = process_target_file(env_file, _env_cfg())

        assert result.type == "Env"
        assert result.status == "Redacted", f"Expected 'Redacted', got '{result.status}'"
        assert result.status != "Skipped (Exclusion)"
        assert result.stats_update == {"env_count": 1}


def test_env_local_routes_to_env_parser() -> None:
    """.env.local (dotted variant) must route to EnvParser, not to skip."""
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = _write_env_file(tmpdir, ".env.local")
        result = process_target_file(env_file, _env_cfg())

        assert result.type == "Env"
        assert result.status == "Redacted", f"Expected 'Redacted', got '{result.status}'"
        assert result.status != "Skipped (Exclusion)"
        assert result.stats_update == {"env_count": 1}


def test_exclusion_note_uses_bracket_grammar() -> None:
    """The skip_exts placeholder must use the `-- [...] --` notice grammar the
    system instructions document, so the LLM can recognize it as tool-inserted."""
    with tempfile.TemporaryDirectory() as tmpdir:
        png = Path(tmpdir) / "logo.png"
        png.write_bytes(b"\x89PNG fake")
        result = process_target_file(png, _env_cfg())

        assert result.status == "Skipped (Exclusion)"
        assert result.content.startswith("-- [")
        assert "*Note" not in result.content


def test_config_env_routes_to_env_parser_even_when_ext_in_skip_exts() -> None:
    """Name-based routing wins even if '.env' is explicitly injected into skip_exts.

    config.env has suffix '.env'.  If the skip_exts check ran first and '.env'
    appeared in skip_exts, the file would be silently excluded as a binary/skip.
    This test guards that regression: is_env_file must always run before the
    extension skip check, so secrets are never silently swallowed.
    """
    poison_skip_exts = set(CORE_SKIP_EXTS) | {".env"}
    with tempfile.TemporaryDirectory() as tmpdir:
        env_file = _write_env_file(tmpdir, "config.env")
        result = process_target_file(env_file, _env_cfg(skip_exts=poison_skip_exts))

        assert result.type == "Env", (
            f"Name-based routing lost to skip_exts — type was '{result.type}'"
        )
        assert result.status == "Redacted", (
            f"Name-based routing lost to skip_exts — got '{result.status}' instead of 'Redacted'"
        )
        assert result.status != "Skipped (Exclusion)"
