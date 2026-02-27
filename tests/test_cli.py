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
