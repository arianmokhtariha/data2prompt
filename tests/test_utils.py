import os
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
from data2prompt.utils import is_binary, load_ignore_file, copy_to_clipboard, get_dynamic_wrapper

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


def test_copy_to_clipboard_success_posix_uses_utf8():
    # Mock subprocess so we never touch the real system clipboard.
    with patch("data2prompt.utils.sys.platform", "linux"), \
         patch("data2prompt.utils.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok = copy_to_clipboard("hello world")

        assert ok is True
        assert mock_run.called
        # Text is passed as UTF-8 encoded bytes via stdin.
        _, kwargs = mock_run.call_args
        assert kwargs["input"] == b"hello world"


def test_copy_to_clipboard_windows_uses_utf16_bom():
    """On Windows the payload must be UTF-16 with BOM: clip.exe autodetects the
    BOM, whereas UTF-8 would be decoded with the legacy console code page and
    garble any non-ASCII character (e.g. accented column names in a CSV)."""
    with patch("data2prompt.utils.sys.platform", "win32"), \
         patch("data2prompt.utils.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        ok = copy_to_clipboard("naïve café")

        assert ok is True
        _, kwargs = mock_run.call_args
        payload = kwargs["input"]
        assert payload.startswith(b"\xff\xfe")  # UTF-16 LE BOM
        assert payload == "naïve café".encode("utf-16")


def test_copy_to_clipboard_no_tool_returns_false():
    # A missing clipboard utility (FileNotFoundError) must be handled gracefully.
    with patch("data2prompt.utils.subprocess.run", side_effect=FileNotFoundError):
        assert copy_to_clipboard("data") is False


# ---------------------------------------------------------------------------
# get_dynamic_wrapper
# ---------------------------------------------------------------------------

def test_get_dynamic_wrapper_plain_text_returns_triple_backticks() -> None:
    """Content without any backticks gets the minimum 3-backtick fence."""
    assert get_dynamic_wrapper("hello world") == "```"


def test_get_dynamic_wrapper_with_triple_backticks_returns_four() -> None:
    """Content containing a ``` fence must get a 4-backtick outer fence."""
    content = "before\n```python\ncode\n```\nafter"
    assert get_dynamic_wrapper(content) == "````"


def test_get_dynamic_wrapper_with_five_backticks_returns_six() -> None:
    """Outer fence is always one longer than the longest run in the content."""
    content = "`````` five backtick run"
    result = get_dynamic_wrapper(content)
    assert result == "`" * 7


def test_get_dynamic_wrapper_double_backticks_still_uses_minimum() -> None:
    """Two-backtick inline code doesn't exceed the minimum: max(3, 2+1) == 3."""
    content = "use `backtick` and ``double``"
    assert get_dynamic_wrapper(content) == "```"


def test_get_dynamic_wrapper_empty_string_returns_triple() -> None:
    assert get_dynamic_wrapper("") == "```"
