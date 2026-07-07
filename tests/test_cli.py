import sys
from unittest.mock import patch

import pytest

from data2prompt import __version__
from data2prompt.cli import setup_cli

def test_setup_cli_merges_defaults():
    # Simulate running the CLI with specific arguments
    test_args = ["data2prompt", "--ignore-folders", "custom_folder", "--skip-exts", ".foo"]
    
    with patch.object(sys, 'argv', test_args):
        args = setup_cli()
        
        # 1. User input should be present
        assert "custom_folder" in args.ignore_folders
        assert ".foo" in args.skip_exts
        
        # 2. CORE defaults must STILL be present (The Safe-by-Default feature)
        # These are defined in src/data2prompt/constants.py
        assert ".git" in args.ignore_folders
        assert ".exe" in args.skip_exts

def test_setup_cli_output_naming():
    # Test default naming
    with patch.object(sys, 'argv', ["data2prompt"]):
        args = setup_cli()
        assert args.output == "PROMPT.md"

    # Test custom naming with default format
    with patch.object(sys, 'argv', ["data2prompt", "-o", "my_prompt"]):
        args = setup_cli()
        assert args.output == "my_prompt.md"

    # Test custom naming with markdown format
    with patch.object(sys, 'argv', ["data2prompt", "-o", "my_prompt", "-f", "markdown"]):
        args = setup_cli()
        assert args.output == "my_prompt.md"

    # Test edge case: output name with extension
    with patch.object(sys, 'argv', ["data2prompt", "-o", "test.md", "-f", "xml"]):
        args = setup_cli()
        assert args.output == "test.md.xml"

def test_setup_cli_boolean_flag_defaults():
    # All boolean toggles should fall back to their constant-backed defaults.
    with patch.object(sys, 'argv', ["data2prompt"]):
        cfg = setup_cli()
        assert cfg.use_gitignore is True
        assert cfg.clipboard is False
        assert cfg.schema_only is False
        assert cfg.stats_summary is True
        assert cfg.env_keys is True

def test_setup_cli_boolean_flags_toggle():
    test_args = [
        "data2prompt", "-c", "--schema-only",
        "--no-stats-summary", "--no-env-keys", "--no-gitignore",
    ]
    with patch.object(sys, 'argv', test_args):
        cfg = setup_cli()
        assert cfg.clipboard is True
        assert cfg.schema_only is True
        assert cfg.stats_summary is False
        assert cfg.env_keys is False
        assert cfg.use_gitignore is False


def test_setup_cli_rejects_negative_sample_size():
    """Negative sizes must be rejected at parse time (exit code 2), not
    surface later as cryptic pandas errors inside every CSV parser call."""
    with patch.object(sys, 'argv', ["data2prompt", "-s", "-5"]):
        with pytest.raises(SystemExit) as exc_info:
            setup_cli()
        assert exc_info.value.code == 2


def test_setup_cli_rejects_zero_line_length_threshold():
    """A zero threshold would truncate every line of every file."""
    with patch.object(sys, 'argv', ["data2prompt", "--line-length-threshold", "0"]):
        with pytest.raises(SystemExit) as exc_info:
            setup_cli()
        assert exc_info.value.code == 2


def test_setup_cli_accepts_zero_sample_size():
    """Zero is a legitimate sample size (headers-only tables)."""
    with patch.object(sys, 'argv', ["data2prompt", "-s", "0"]):
        cfg = setup_cli()
        assert cfg.csv_sample_size == 0


def test_version_flag_prints_version_and_exits_cleanly(capsys):
    with patch.object(sys, 'argv', ["data2prompt", "--version"]):
        with pytest.raises(SystemExit) as exc_info:
            setup_cli()
        assert exc_info.value.code == 0
    captured = capsys.readouterr()
    assert __version__ in captured.out
