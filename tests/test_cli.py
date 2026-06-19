import sys
from unittest.mock import patch
from src.data2prompt.cli import setup_cli

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
