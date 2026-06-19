import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from src.data2prompt.utils import count_tokens, is_binary, load_ignore_file, copy_to_clipboard

def test_count_tokens():
    # A simple string should return a deterministic token count
    text = "Hello, world! This is a test."
    tokens, method = count_tokens(text)
    assert isinstance(tokens, int)
    assert tokens > 0
    assert isinstance(method, str)

def test_is_binary():
    with tempfile.NamedTemporaryFile(delete=False) as temp_bin:
        # Write a null byte to simulate a binary file
        temp_bin.write(b"Some text \x00 more text")
        temp_bin_path = temp_bin.name

    with tempfile.NamedTemporaryFile(mode='w', delete=False) as temp_text:
        # Write normal text
        temp_text.write("Just a normal text file.")
        temp_text_path = temp_text.name

    try:
        assert is_binary(temp_bin_path) is True
        assert is_binary(temp_text_path) is False
    finally:
        if os.path.exists(temp_bin_path):
            os.remove(temp_bin_path)
        if os.path.exists(temp_text_path):
            os.remove(temp_text_path)

def test_load_ignore_file():
    with tempfile.TemporaryDirectory() as temp_dir:
        ignore_path = Path(temp_dir) / ".data2promptignore"
        with open(ignore_path, "w") as f:
            f.write("# A comment\n")
            f.write("node_modules/\n")
            f.write("\n")
            f.write("secrets.json\n")
        
        ignores = load_ignore_file(temp_dir)
        assert "node_modules/" in ignores  # Slash should be preserved for pathspec
        assert "secrets.json" in ignores
        assert len(ignores) == 2


def test_copy_to_clipboard_success():
    # Mock subprocess so we never touch the real system clipboard.
    with patch("src.data2prompt.utils.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok = copy_to_clipboard("hello world")

        assert ok is True
        assert mock_run.called
        # Text is passed as UTF-8 encoded bytes via stdin.
        _, kwargs = mock_run.call_args
        assert kwargs["input"] == b"hello world"


def test_copy_to_clipboard_no_tool_returns_false():
    # A missing clipboard utility (FileNotFoundError) must be handled gracefully.
    with patch("src.data2prompt.utils.subprocess.run", side_effect=FileNotFoundError):
        assert copy_to_clipboard("data") is False
