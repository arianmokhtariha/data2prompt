import importlib.resources
from unittest.mock import patch

import pytest

from data2prompt.utils import count_tokens


def test_bundled_encoding_file_exists() -> None:
    """The bundled BPE file must exist and be at least 1MB."""
    ref = importlib.resources.files("data2prompt") / "encodings" / "o200k_base.tiktoken"
    with importlib.resources.as_file(ref) as path:
        assert path.exists(), f"BPE file not found at {path}"
        assert path.stat().st_size > 1_000_000, (
            f"BPE file is suspiciously small ({path.stat().st_size} bytes)"
        )


def test_count_tokens_uses_bundled_encoding() -> None:
    """count_tokens must load from the bundled BPE file and return method 'o200k_base'."""
    _, method = count_tokens("some sample text for tokenization testing")
    assert method == "o200k_base"


def test_count_tokens_hello_world() -> None:
    """'Hello world' encodes to exactly 2 tokens with o200k_base."""
    count, method = count_tokens("Hello world")
    assert method == "o200k_base"
    assert count == 2


def test_count_tokens_fallback_on_load_error() -> None:
    """When _load_encoding raises, count_tokens must fall back to regex_fallback."""
    with patch("data2prompt.utils._load_encoding", side_effect=RuntimeError("simulated failure")):
        count, method = count_tokens("word1 word2 word3")
    assert method == "regex_fallback"
    assert count >= 3
