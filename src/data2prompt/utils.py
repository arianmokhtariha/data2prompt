import base64
import importlib.resources
import os
import subprocess
import sys
from pathlib import Path
from typing import List, Optional, Tuple, Union, Set

import pathspec
import regex as re
import tiktoken

from data2prompt.ui import ui

# Module-level cache for the loaded tiktoken encoding (populated once per process)
_ENCODING: Optional[tiktoken.Encoding] = None

# Set after the first fallback warning so it is printed at most once per process.
_FALLBACK_WARNED: bool = False


def _load_encoding() -> tiktoken.Encoding:
    """Load o200k_base from the bundled BPE file — no network call ever made."""
    global _ENCODING
    if _ENCODING is not None:
        return _ENCODING

    # Parsed here instead of via tiktoken.load.load_tiktoken_bpe: that helper
    # copies the file into a temp cache and, on tiktoken < 0.9, requires the
    # optional blobfile package even for local paths — a silent-fallback trap.
    bpe_ref = importlib.resources.files("data2prompt") / "encodings" / "o200k_base.tiktoken"
    mergeable_ranks = {
        base64.b64decode(token): int(rank)
        for token, rank in (
            line.split() for line in bpe_ref.read_bytes().splitlines() if line
        )
    }

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


def count_tokens(text: str) -> Tuple[int, str]:
    """Return token count and method used. Primary path is the bundled BPE file.

    Falls back to a regex approximation if loading fails, then to a plain word
    count as a last resort. Under normal conditions always returns 'o200k_base'.
    """
    global _FALLBACK_WARNED
    try:
        encoding = _load_encoding()
        # disallowed_special=() so content containing special-token strings
        # (e.g. a literal "<|endoftext|>" in a scanned file) counts as plain
        # text instead of raising — which is also how an LLM API treats it.
        return len(encoding.encode(text, disallowed_special=())), "o200k_base"
    except Exception as exc:
        if not _FALLBACK_WARNED:
            _FALLBACK_WARNED = True
            ui.print_warning(
                f"Accurate token counting unavailable ({exc!r}) — "
                "using a regex approximation instead."
            )

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
    """
    if sys.platform == "win32":
        # clip.exe detects UTF-16 LE via its BOM; plain UTF-8 would be decoded
        # with the legacy console code page and garble non-ASCII characters.
        data = text.encode("utf-16", errors="replace")
        commands: List[List[str]] = [["clip"]]
    elif sys.platform == "darwin":
        data = text.encode("utf-8", errors="replace")
        commands = [["pbcopy"]]
    else:
        data = text.encode("utf-8", errors="replace")
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
        # Full path so '-o out/PROMPT' excludes exactly that file, not every
        # file that happens to share its basename somewhere in the tree.
        self._output_path = project_path / output_file
        self.use_gitignore = use_gitignore
        self.spec = self._build_spec()
        # Initialized empty first: _load_all_gitignores prunes with _is_ignored,
        # which consults this list while it is being built (top-down walk, so
        # parent specs are always registered before their subtrees are visited).
        self._gitignore_specs: List[Tuple[Path, pathspec.PathSpec]] = []
        if self.use_gitignore:
            self._gitignore_specs = self._load_all_gitignores()

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

        return pathspec.PathSpec.from_lines('gitignore', patterns)

    def _load_all_gitignores(self) -> List[Tuple[Path, pathspec.PathSpec]]:
        """Walk the project tree and collect a per-directory PathSpec for every
        .gitignore found. Prunes ignored directories (and .git) so gitignores
        inside excluded trees are neither collected nor walked."""
        specs = self._gitignore_specs
        for root, dirs, files in os.walk(self.project_path):
            root_path = Path(root)
            if '.gitignore' in files:
                patterns = load_ignore_file(root_path, '.gitignore')
                if patterns:
                    specs.append((root_path, pathspec.PathSpec.from_lines('gitignore', patterns)))
            dirs[:] = [
                d for d in dirs
                if d != '.git' and not self._is_ignored(root_path / d, is_dir=True)
            ]
        return specs

    def _is_ignored_by_gitignore(self, path: Path, is_dir: bool = False) -> bool:
        """Check path against every per-directory gitignore spec whose base
        directory is an ancestor of path. Matches relative to each base dir."""
        for base_dir, spec in self._gitignore_specs:
            try:
                rel = path.relative_to(base_dir)
            except ValueError:
                continue
            rel_str = str(rel)
            if spec.match_file(rel_str):
                return True
            if is_dir and spec.match_file(rel_str + os.sep):
                return True
        return False

    def _is_ignored(self, path: Path, is_dir: bool = False) -> bool:
        """Checks if a given path should be ignored based on the compiled spec and special cases.

        ``is_dir`` must be True when ``path`` is a directory: directory-only
        patterns like ``venv/`` never match a bare name, so directories are
        additionally matched with a trailing separator.
        """
        try:
            rel_path = path.relative_to(self.project_path)
        except ValueError:
            return False

        rel_str = str(rel_path)
        if rel_str == '.':
            return False

        # Check against pathspec (CLI patterns + .data2promptignore)
        if self.spec.match_file(rel_str):
            return True
        if is_dir and self.spec.match_file(rel_str + os.sep):
            return True

        # Check per-directory gitignore specs
        if self._is_ignored_by_gitignore(path, is_dir=is_dir):
            return True

        # Never re-ingest our own output file. Older outputs under other names
        # are caught downstream by the GENERATION_FLAG check in DefaultParser.
        if path == self._output_path:
            return True

        return False

    def scan(self) -> List[Path]:
        """Discovers all files in the project path, respecting ignore rules.

        Directories and files are visited in sorted order so the output is
        deterministic across platforms and file systems.
        """
        all_files: List[Path] = []
        for root, dirs, files in os.walk(self.project_path):
            root_path = Path(root)

            # Prune directories in-place (sorted) to avoid unnecessary walking
            dirs[:] = sorted(
                d for d in dirs if not self._is_ignored(root_path / d, is_dir=True)
            )

            for file in sorted(files):
                file_path = root_path / file
                if not self._is_ignored(file_path):
                    all_files.append(file_path)
        return all_files

    def generate_tree(self, files: Optional[List[Path]] = None) -> str:
        """Generates a flat, sorted list of files in the project structure.

        Accepts the result of a previous :meth:`scan` to avoid walking the
        tree twice; falls back to scanning when no list is given.

        Paths use forward slashes on every platform: they are the canonical
        keys the output File Index and file headers must match exactly, and
        forward slashes are what LLMs read most reliably.
        """
        if files is None:
            files = self.scan()
        tree = [f.relative_to(self.project_path).as_posix() for f in files]
        return "\n".join(sorted(tree))

def load_ignore_file(directory: Union[str, Path], filename: str = '.data2promptignore') -> List[str]:
    """
    Looks for an ignore file in the given directory.
    Returns a list of patterns to ignore, excluding comments and empty lines.
    """
    ignore_path = Path(directory) / filename
    ignore_list: List[str] = []

    if ignore_path.exists():
        try:
            with ignore_path.open('r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith('#'):
                        continue
                    ignore_list.append(line)
        except OSError as e:
            ui.print_warning(f"Could not read {filename}: {e}")

    return ignore_list
