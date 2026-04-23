import sys
from unittest.mock import patch
from src.data2prompt.cli import setup_cli

def test_default_output_naming():
    """Verifies that the default output is PROMPT.xml"""
    test_args = ["data2prompt"]
    with patch.object(sys, 'argv', test_args):
        config = setup_cli()
        assert config.output == "PROMPT.xml"
        assert config.format == "xml"

def test_markdown_format_naming():
    """Verifies that --format markdown results in PROMPT.md"""
    test_args = ["data2prompt", "--format", "markdown"]
    with patch.object(sys, 'argv', test_args):
        config = setup_cli()
        assert config.output == "PROMPT.md"
        assert config.format == "markdown"

def test_custom_output_with_xml():
    """Verifies that --output test results in test.xml"""
    test_args = ["data2prompt", "--output", "test"]
    with patch.object(sys, 'argv', test_args):
        config = setup_cli()
        assert config.output == "test.xml"

def test_custom_output_with_markdown():
    """Verifies that --output test --format markdown results in test.md"""
    test_args = ["data2prompt", "--output", "test", "--format", "markdown"]
    with patch.object(sys, 'argv', test_args):
        config = setup_cli()
        assert config.output == "test.md"

def test_edge_case_output_with_extension():
    """Verifies that --output test.md --format xml results in test.md.xml"""
    test_args = ["data2prompt", "--output", "test.md", "--format", "xml"]
    with patch.object(sys, 'argv', test_args):
        config = setup_cli()
        assert config.output == "test.md.xml"
        assert config.format == "xml"

def test_edge_case_output_with_extension_markdown():
    """Verifies that --output test.xml --format markdown results in test.xml.md"""
    test_args = ["data2prompt", "--output", "test.xml", "--format", "markdown"]
    with patch.object(sys, 'argv', test_args):
        config = setup_cli()
        assert config.output == "test.xml.md"
        assert config.format == "markdown"
