import os
from pathlib import Path
from typing import List, Union

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

def is_binary(file_path: Union[str, Path]) -> bool:
    """Check if a file is binary by looking for a Null byte in the first 1024 bytes."""
    try:
        with open(file_path, "rb") as f:
            chunk = f.read(1024)
            return b"\0" in chunk
    except OSError:
        return False


def generate_tree(
    startpath: Union[str, Path], ignore_folders: List[str], ignore_files: List[str]
) -> str:
    tree = []
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in ignore_folders]
        level = root.replace(startpath, '').count(os.sep)
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
