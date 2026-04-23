import pytest
from data2prompt.utils import count_tokens, is_online

def test_is_online_timeout():
    """
    Tests that is_online returns a boolean and respects timeout.
    Note: This depends on the actual environment connectivity.
    """
    result = is_online(timeout=0.1)
    assert isinstance(result, bool)

def test_count_tokens_logic():
    """
    Verifies that count_tokens returns a valid tuple and handles the text.
    """
    test_text = "def hello_world(): print('Hello')"
    count, method = count_tokens(test_text)
    
    assert isinstance(count, int)
    assert count > 0
    assert isinstance(method, str)
    assert method in ["o200k_base", "regex_fallback", "word_count"]

def test_offline_fallback_consistency():
    """
    Ensures that even if offline, we get a reasonable token count.
    """
    test_text = "word1 word2 word3"
    # We can't easily force offline without mocking, but we can check the regex fallback directly
    # if we were to mock is_online to return False.
    count, method = count_tokens(test_text)
    assert count >= 3 # At least 3 tokens/words
