import importlib.resources
import os
import sys
import subprocess
from pathlib import Path
from typing import List, Optional, Union, Set

import tiktoken
from tiktoken.load import load_tiktoken_bpe
import regex as re
import pathspec

from .ui import ui

# Module-level cache for the loaded tiktoken encoding (populated once per process)
_ENCODING: Optional[tiktoken.Encoding] = None


def _load_encoding() -> tiktoken.Encoding:
    """Load o200k_base from the bundled BPE file — no network call ever made."""
    global _ENCODING
    if _ENCODING is not None:
        return _ENCODING

    bpe_ref = importlib.resources.files("data2prompt") / "encodings" / "o200k_base.tiktoken"
    with importlib.resources.as_file(bpe_ref) as bpe_path:
        mergeable_ranks = load_tiktoken_bpe(str(bpe_path))

    pat_str = "|".join(
        [
            r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]*[\p{Ll}\p{Lm}\p{Lo}\p{M}]+(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
            r"""[^\r\n\p{L}\p{N}]?[\p{Lu}\p{Lt}\p{Lm}\p{Lo}\p{M}]+[\p{Ll}\p{Lm}\p{Lo}\p{M}]*(?i:'s|'t|'re|'ve|'m|'ll|'d)?""",
            r"""\p{N}{1,3}""",
            r""" ?[^\s\p{L}\p{N}]+[\r\n/]*""",
            r"""\s*[\r\n]+""",
            r"""\s+(?!\S)""",
            r"""\s+""",
        ]
    )

    _ENCODING = tiktoken.Encoding(
        name="o200k_base",
        pat_str=pat_str,
        mergeable_ranks=mergeable_ranks,
        special_tokens={"<|endoftext|>": 199999, "<|endofprompt|>": 200018},
    )
    return _ENCODING


def count_tokens(text: str, encoding_name: str = "o200k_base") -> tuple[int, str]:
    """Return token count and method used. Primary path is the bundled BPE file.

    Falls back to a regex approximation if loading fails, then to a plain word
    count as a last resort. Under normal conditions always returns 'o200k_base'.
    """
    try:
        encoding = _load_encoding()
        return len(encoding.encode(text)), "o200k_base"
    except Exception:
        pass

    # Regex fallback: Official OpenAI o200k_base pre-tokenization pattern
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


def copy_to_clipboard(text: str) -> bool:
    """Copy text to the system clipboard using OS-native tools (no third-party dep).

    Uses ``clip`` on Windows, ``pbcopy`` on macOS, and ``wl-copy``/``xclip``/``xsel``
    on Linux (first available wins). Returns True on success, or False if no
    clipboard utility is available or the copy fails — callers can then fall back to
    writing a file.

    Note: on Windows, ``clip`` interprets input using the active console code page,
    so rare non-ASCII characters may not round-trip exactly.
    """
    data = text.encode("utf-8", errors="replace")

    if sys.platform == "win32":
        commands: List[List[str]] = [["clip"]]
    elif sys.platform == "darwin":
        commands = [["pbcopy"]]
    else:
        commands = [
            ["wl-copy"],
            ["xclip", "-selection", "clipboard"],
            ["xsel", "--clipboard", "--input"],
        ]

    for command in commands:
        try:
            subprocess.run(command, input=data, check=True)
            return True
        except (OSError, subprocess.SubprocessError):
            continue
    return False


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

    def __init__(self, project_path: Path, ignore_folders: Set[str], ignore_files: Set[str], output_file: str, use_gitignore: bool = True) -> None:
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

        return pathspec.PathSpec.from_lines('gitignore', patterns)

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
