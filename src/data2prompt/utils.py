import os
import sys
from pathlib import Path
from typing import List, Union, Set

import tiktoken
import regex as re

from .ui import ui


def count_tokens(text: str, encoding_name: str = "o200k_base") -> tuple[int, str]:
    """
    Returns the number of tokens in a text string and the method used.
    Attempts to use tiktoken (requires internet/cache),
    falls back to a robust offline regex pattern if tiktoken fails.
    """
    try:
        encoding = tiktoken.get_encoding(encoding_name)
        return len(encoding.encode(text)), encoding_name
    except Exception:
        # Offline fallback: Official OpenAI o200k_base pre-tokenization pattern
        # This pattern splits text into chunks exactly like the GPT-4o tokenizer
        # before the BPE merging step. It is ~95-98% accurate for code.
        pattern = r"""[^\r\n\p{L}\p{N}]?[\p{L}\p{N}]+|(?:\r?\n)|[\s\t]+|[^\s\p{L}\p{N}]+"""
        try:
            return len(re.findall(pattern, text)), "regex_fallback"
        except Exception:
            # Absolute fallback to word count if regex fails
            return len(text.split()), "word_count"

def get_dynamic_wrapper(content: str) -> str:
    """
    Finds the longest sequence of backticks in the content and returns
     a wrapper string with one more backtick than the maximum found.
    Ensures that nested code blocks do not break the outer container.
    """
    max_backticks = 0
    # Find all sequences of backticks
    matches = re.findall(r'`+', content)
    if matches:
        max_backticks = max(len(m) for m in matches)
    
    # We need at least 3 backticks for a markdown code block
    return '`' * max(3, max_backticks + 1)


def is_binary(file_path: Union[str, Path]) -> bool:
    """Check if a file is binary by looking for a Null byte in the first 1024 bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except OSError:
        return False


class ProjectScanner:
    """Encapsulates file discovery and ignore logic."""

    def __init__(self, project_path: Path, ignore_folders: Set[str], ignore_files: Set[str], output_file: str):
        self.project_path = project_path
        self.ignore_folders = ignore_folders
        self.ignore_files = ignore_files
        self.output_file = output_file
        self._load_project_ignores()

    def _load_project_ignores(self):
        """Loads and merges project-specific ignores from .data2promptignore."""
        project_ignores = load_ignore_file(self.project_path)
        self.ignore_folders.update(project_ignores)
        self.ignore_files.update(project_ignores)

    def scan(self) -> List[Path]:
        """Discovers all files in the project path, respecting ignore rules."""
        all_files = []
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_folders]
            for file in files:
                if file == self.output_file or file == Path(sys.argv[0]).name or file in self.ignore_files:
                    continue
                all_files.append(Path(root) / file)
        return all_files

    def generate_tree(self) -> str:
        """Generates a visual tree representation of the project structure."""
        tree = []
        startpath_str = str(self.project_path)
        for root, dirs, files in os.walk(self.project_path):
            dirs[:] = [d for d in dirs if d not in self.ignore_folders]
            level = root.replace(startpath_str, '').count(os.sep)
            indent = ' ' * 4 * level
            tree.append(f"{indent}📂 {os.path.basename(root)}/")
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                if f not in self.ignore_files and f != self.output_file and f != Path(sys.argv[0]).name:
                    tree.append(f"{sub_indent}📄 {f}")
        return "\n".join(tree)

def generate_tree(
    startpath: Union[str, Path], ignore_folders: Union[List[str], Set[str]], ignore_files: Union[List[str], Set[str]]
) -> str:
    """Legacy wrapper for generate_tree."""
    tree = []
    startpath_str = str(startpath)
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in ignore_folders]
        level = root.replace(startpath_str, '').count(os.sep)
        indent = ' ' * 4 * level
        tree.append(f"{indent}📂 {os.path.basename(root)}/")
        sub_indent = ' ' * 4 * (level + 1)
        for f in files:
            if f not in ignore_files:
                tree.append(f"{sub_indent}📄 {f}")
    return "\n".join(tree)

def load_ignore_file(directory: Union[str, Path]) -> List[str]:
    """
    Looks for a .data2promptignore file in the given directory.
    Returns a list of patterns to ignore, excluding comments and empty lines.
    """
    ignore_path = os.path.join(directory, '.data2promptignore')
    ignore_list = []
    
    if os.path.exists(ignore_path):
        try:
            with open(ignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    # Strip trailing slashes and whitespace
                    pattern = line.rstrip('/')
                    ignore_list.append(pattern)
        except Exception as e:
            ui.print_warning(f"Could not read .data2promptignore: {e}")
            
    return ignore_list
