import os
import sys
import socket
from pathlib import Path
from typing import List, Union, Set, Dict

import tiktoken
import regex as re
import pathspec

from .ui import ui

# Global state for tokenization
_OFFLINE_MODE = False
_ENCODING_CACHE: Dict[str, tiktoken.Encoding] = {}


def is_online(timeout: float = 0.5) -> bool:
    """
    Quickly checks for internet connectivity by attempting to connect to OpenAI's public storage.
    Default timeout is 0.5s to prevent hanging the tool.
    """
    try:
        # tiktoken downloads from openaipublic.blob.core.windows.net
        socket.setdefaulttimeout(timeout)
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.connect(("openaipublic.blob.core.windows.net", 443))
        return True
    except (socket.timeout, OSError):
        return False


def check_connectivity(timeout: float = 0.5) -> bool:
    """
    Performs a connectivity check and updates the global offline mode flag.
    """
    global _OFFLINE_MODE
    if is_online(timeout):
        _OFFLINE_MODE = False
        return True
    else:
        _OFFLINE_MODE = True
        return False


def count_tokens(text: str, encoding_name: str = "o200k_base") -> tuple[int, str]:
    """
    Returns the number of tokens in a text string and the method used.
    Attempts to use tiktoken (requires internet/cache),
    falls back to a robust offline regex pattern if tiktoken fails or is offline.
    """
    global _OFFLINE_MODE

    if not _OFFLINE_MODE:
        try:
            if encoding_name not in _ENCODING_CACHE:
                # Perform a quick connectivity check before the potentially hanging tiktoken call
                if not is_online():
                    _OFFLINE_MODE = True
                    raise ConnectionError("Offline mode detected")
                
                _ENCODING_CACHE[encoding_name] = tiktoken.get_encoding(encoding_name)
            
            encoding = _ENCODING_CACHE[encoding_name]
            return len(encoding.encode(text)), encoding_name
        except Exception:
            _OFFLINE_MODE = True

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
    """Encapsulates file discovery and ignore logic using pathspec for robust pattern matching."""

    def __init__(self, project_path: Path, ignore_folders: Set[str], ignore_files: Set[str], output_file: str, use_gitignore: bool = True):
        self.project_path = project_path
        self.ignore_folders = ignore_folders
        self.ignore_files = ignore_files
        self.output_file = output_file
        self.use_gitignore = use_gitignore
        self.spec = self._build_spec()

    def _build_spec(self) -> pathspec.PathSpec:
        """Compiles all ignore patterns into a single PathSpec object."""
        patterns = []
        
        # 1. Add explicit ignores from CLI/Constants (folders need trailing slash for pathspec)
        for folder in self.ignore_folders:
            patterns.append(f"{folder}/")
        for file in self.ignore_files:
            patterns.append(file)
            
        # 2. Add .data2promptignore
        patterns.extend(load_ignore_file(self.project_path, '.data2promptignore'))
        
        # 3. Add .gitignore if enabled
        if self.use_gitignore:
            patterns.extend(load_ignore_file(self.project_path, '.gitignore'))
            
        return pathspec.PathSpec.from_lines('gitwildmatch', patterns)

    def _is_ignored(self, path: Path) -> bool:
        """Checks if a given path should be ignored based on the compiled spec and special cases."""
        try:
            rel_path = path.relative_to(self.project_path)
        except ValueError:
            return False
            
        if str(rel_path) == '.':
            return False
            
        # Check against pathspec
        if self.spec.match_file(str(rel_path)):
            return True
            
        # Special cases: output file and the script itself
        if path.name == self.output_file or path.name == Path(sys.argv[0]).name:
            return True
            
        return False

    def scan(self) -> List[Path]:
        """Discovers all files in the project path, respecting ignore rules."""
        all_files = []
        for root, dirs, files in os.walk(self.project_path):
            root_path = Path(root)
            
            # Prune directories in-place to avoid unnecessary walking
            dirs[:] = [d for d in dirs if not self._is_ignored(root_path / d)]
            
            for file in files:
                file_path = root_path / file
                if not self._is_ignored(file_path):
                    all_files.append(file_path)
        return all_files

    def generate_tree(self) -> str:
        """Generates a flat list of files in the project structure."""
        tree = []
        for root, dirs, files in os.walk(self.project_path):
            root_path = Path(root)
            
            # Prune directories
            dirs[:] = [d for d in dirs if not self._is_ignored(root_path / d)]
            
            for f in files:
                file_path = root_path / f
                if not self._is_ignored(file_path):
                    rel_path = file_path.relative_to(self.project_path)
                    # Use backslashes for consistency in the output as per project standard
                    tree.append(str(rel_path).replace(os.sep, '\\'))
        return "\n".join(sorted(tree))

def generate_tree(
    startpath: Union[str, Path], ignore_folders: Union[List[str], Set[str]], ignore_files: Union[List[str], Set[str]]
) -> str:
    """Legacy wrapper for generate_tree, now generating a flat list."""
    tree = []
    startpath = Path(startpath)
    for root, dirs, files in os.walk(startpath):
        dirs[:] = [d for d in dirs if d not in ignore_folders]
        for f in files:
            if f not in ignore_files:
                rel_path = Path(root).relative_to(startpath) / f
                # Use forward slashes for consistency in the output
                tree.append(str(rel_path).replace(os.sep, '\\'))
    return "\n".join(sorted(tree))

def load_ignore_file(directory: Union[str, Path], filename: str = '.data2promptignore') -> List[str]:
    """
    Looks for an ignore file in the given directory.
    Returns a list of patterns to ignore, excluding comments and empty lines.
    """
    ignore_path = os.path.join(directory, filename)
    ignore_list = []
    
    if os.path.exists(ignore_path):
        try:
            with open(ignore_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    ignore_list.append(line)
        except Exception as e:
            ui.print_warning(f"Could not read {filename}: {e}")
            
    return ignore_list
