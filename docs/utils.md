# Utilities Module (`src/data2prompt/utils.py`)

The utilities module provides generic helper functions used throughout the data2prompt project. It handles tokenization with offline fallbacks, file system operations, ignore pattern management, and defensive content detection.

## Module Architecture

```python
# Global state for tokenization (module-level, not class-based)
_ENCODING: Optional[tiktoken.Encoding] = None  # populated once per process

# Key functions
_load_encoding()     # Load bundled BPE file; cached after first call
count_tokens()       # Primary token counting with fallbacks
get_dynamic_wrapper()# Markdown code block safety
copy_to_clipboard()  # OS-native clipboard copy (no third-party dep)
is_binary()          # Binary file detection

# Classes
ProjectScanner       # File discovery with ignore logic

# Standalone utilities
load_ignore_file()   # Ignore file parser
```

---

## Tokenization System

The tokenization system provides accurate token counting using a bundled BPE file,
with a regex approximation as a safety-net fallback.

### Global State

| Variable | Type | Purpose |
|----------|------|---------|
| `_ENCODING` | `Optional[tiktoken.Encoding]` | Cached encoding instance; `None` until first use, then held for the lifetime of the process |

### Loading the Encoding

#### `_load_encoding() -> tiktoken.Encoding`

Loads the o200k_base encoding from the bundled BPE file. Returns the cached instance
on every call after the first — the file is parsed only once per process.

```python
encoding = _load_encoding()  # Fast after first call
```

**Implementation Details:**
- Uses `importlib.resources.files("data2prompt") / "encodings" / "o200k_base.tiktoken"`
  to locate the file shipped inside the package — works for both editable installs and
  installed wheels.
- Calls `tiktoken.load.load_tiktoken_bpe(str(path))` against the local path, which
  reads the file directly without any network access.
- Constructs a `tiktoken.Encoding` with the exact parameters from `o200k_base`:
  `pat_str` (the GPT-4o pre-tokenization regex), `mergeable_ranks` (from the BPE
  file), and `special_tokens` (`<|endoftext|>: 199999`, `<|endofprompt|>: 200018`).
- Caches the result in `_ENCODING` for all subsequent calls.

**Why this matters:** tiktoken's default `get_encoding()` fetches the BPE file from
the network on first use. Loading from a bundled local file eliminates that dependency
entirely.

---

### Token Counting

#### `count_tokens(text: str) -> Tuple[int, str]`

Returns the number of tokens in a text string and the method used. (A former
`encoding_name` parameter was removed — it was never read; the encoding is
always the bundled o200k_base.)

```python
token_count, method = count_tokens("def hello(): return 'world'")
# Returns: (6, "o200k_base") under normal conditions
```

**Algorithm:**

```
┌─────────────────────────────────────────────────────┐
│ 1. Bundled tiktoken (primary path)                  │
│    └─ Call _load_encoding() → tiktoken.Encoding     │
│    └─ encoding.encode(text) → token list            │
│    └─ Return (len, "o200k_base")                    │
│    └─ On any exception → fall through               │
│                                                     │
│ 2. Regex Fallback (safety net only)                 │
│    └─ pattern = r"""[^\r\n\p{L}\p{N}]?... """       │
│    └─ re.findall(pattern, text)                     │
│    └─ Return (len, "regex_fallback")                │
│    └─ On any exception → fall through               │
│                                                     │
│ 3. Word Count (absolute last resort)                │
│    └─ len(text.split())                             │
│    └─ Return (count, "word_count")                  │
└─────────────────────────────────────────────────────┘
```

**Return Values:**

| Scenario | Token Count | Method |
|----------|-------------|--------|
| Normal (bundled BPE loaded) | Accurate count | `"o200k_base"` |
| BPE load failed | ~95-98% accurate | `"regex_fallback"` |
| Regex also fails | Approximate | `"word_count"` |

**The Regex Pattern Explained:**

```regex
[^\r\n\p{L}\p{N}]?[\p{L}\p{N}]+   # Letters/numbers with optional prefix
|                               # OR
(?:\r?\n)                        # Newlines (CRLF or LF)
|                               # OR
[\s\t]+                         # Whitespace sequences
|                               # OR
[^\s\p{L}\p{N}]+                # Punctuation/symbols
```

This pattern implements the pre-tokenization step of the GPT-4o tokenizer (o200k_base) before BPE merging.

**Usage in Other Modules:**
- [`parsers.py`](../src/data2prompt/parsers.py#L1): Used to calculate prompt density and truncate large files
- [`main.py`](../src/data2prompt/main.py#L1): Used for total token estimation in summary output

---

## Dynamic Wrapping Algorithm

#### `get_dynamic_wrapper(content: str) -> str`

Finds the longest sequence of backticks in content and returns a wrapper with one more backtick.

```python
wrapper = get_dynamic_wrapper("Here's some `inline` code and ```block``` code")
# wrapper = "````"  (4 backticks, because max found was 3)

# Usage:
# output = f"{wrapper}\n{content}\n{wrapper}"
```

**Algorithm:**

```
1. Find all backtick sequences in content using regex r'`+'
2. Determine maximum length (max_backticks)
3. Return at least 3 backticks, or max_backticks + 1
4. If no backticks found, return "```" (standard markdown)
```

**Why This Matters:**

When embedding code in markdown, using standard triple backticks (` ``` `) can break if the content itself contains triple backticks. By detecting the maximum nesting and incrementing, we ensure the code block never terminates prematurely.

| Content Contains | Returns |
|------------------|---------|
| No backticks | ` ``` ` (3) |
| Single backticks `` ` `` | ` `` ` (3) |
| Double backticks `` ` ` `` | ` ``` ` (4) |
| Triple backticks `` ` ` ` `` | ` ```` ` (5) |

**Usage in [`output.py`](../src/data2prompt/output.py#L1):** Used to safely embed file contents in markdown output.

---

## Clipboard Output

#### `copy_to_clipboard(text: str) -> bool`

Copies text to the system clipboard using OS-native command-line tools, with **no
third-party dependency**.

```python
if copy_to_clipboard(final_output):
    ...  # copied successfully
else:
    ...  # no clipboard tool available — fall back to writing a file
```

**Implementation Details:**
- Selects the tool by platform: `clip` (Windows), `pbcopy` (macOS), and the first
  available of `wl-copy` / `xclip` / `xsel` (Linux).
- Feeds the text via `subprocess.run(..., input=..., check=True)`.
- **Encoding is platform-specific:** UTF-16 (with BOM) on Windows — `clip.exe`
  autodetects the BOM, so non-ASCII characters round-trip correctly, where UTF-8
  would be decoded with the legacy console code page and garbled — and UTF-8
  everywhere else. Both use `errors="replace"`.
- Returns `True` on success; `False` on any failure (`OSError` for a missing tool,
  `subprocess.SubprocessError` for a non-zero exit).

**Consumed by:** [`main.py`](../src/data2prompt/main.py#L1) for the `-c`/`--clipboard`
flag. When it returns `False`, `main.py` falls back to writing the output file and warns.

---

## Binary Detection

#### `is_binary(file_path: Union[str, Path]) -> bool`

Checks if a file is binary by looking for a null byte in the first 1024 bytes.

```python
if is_binary(file_path):
    skip_file()  # Don't attempt to parse as text
```

**Implementation:**

```python
def is_binary(file_path):
    with open(file_path, "rb") as f:
        chunk = f.read(1024)
        return b"\0" in chunk
```

**Characteristics:**
- Only reads first 1024 bytes (memory-efficient for large files)
- Returns `False` on `OSError` (assumes text if unreadable)
- Uses null byte (`\0`) detection, the standard Unix heuristic

**Usage in [`parsers.py`](../src/data2prompt/parsers.py#L1):** Prevents attempting to parse binary files as text, which would corrupt output and token counts.

---

## ProjectScanner Class

The `ProjectScanner` class encapsulates file discovery and ignore logic using `pathspec` for robust gitignore-style pattern matching.

### Class Overview

```python
scanner = ProjectScanner(
    project_path=Path("."),
    ignore_folders={".git", "__pycache__", "node_modules"},
    ignore_files={".DS_Store", "*.pyc"},
    output_file="output.md",
    use_gitignore=True
)
files = scanner.scan()
tree = scanner.generate_tree()
```

### Constructor

#### `__init__(project_path: Path, ignore_folders: Set[str], ignore_files: Set[str], output_file: str, use_gitignore: bool = True)`

| Parameter | Type | Description |
|-----------|------|-------------|
| `project_path` | `Path` | Root directory to scan |
| `ignore_folders` | `Set[str]` | Folder names to ignore (e.g., `".git"`) |
| `ignore_files` | `Set[str]` | Filenames/patterns to ignore (e.g., `"*.pyc"`) |
| `output_file` | `str` | Name of output file to auto-ignore |
| `use_gitignore` | `bool` | Whether to read `.gitignore` files (default `True`) |

**Instance attributes:**

| Attribute | Type | Description |
|-----------|------|-------------|
| `spec` | `pathspec.PathSpec` | Compiled spec for CLI patterns and `.data2promptignore` |
| `_gitignore_specs` | `List[Tuple[Path, pathspec.PathSpec]]` | Per-directory specs, one per `.gitignore` found in the tree |
| `_output_path` | `Path` | `project_path / output_file` — the exact location of the output file, used for precise self-exclusion |

**Initialization Process:**
1. Stores all parameters as instance attributes; precomputes `_output_path`
2. Calls `_build_spec()` to compile CLI patterns and `.data2promptignore` into `self.spec`
3. Initializes `_gitignore_specs` to an empty list, then (if `use_gitignore=True`)
   calls `_load_all_gitignores()` to walk the project tree and populate it — one
   `PathSpec` per `.gitignore` found, paired with its containing directory. The
   empty-list-first order matters: the collection walk prunes with `_is_ignored()`,
   which reads `_gitignore_specs` while it is being built (the walk is top-down,
   so parent specs are always registered before their subtrees are visited).

### Internal Methods

#### `_build_spec() -> pathspec.PathSpec`

Compiles CLI-level and project-level ignore patterns into a single `PathSpec`.
`.gitignore` patterns are **not** included here; they are handled by `_load_all_gitignores()`.

**Pattern Sources (in priority order):**
1. Explicit `ignore_folders` (appended with `/` for directory matching)
2. Explicit `ignore_files` (exact filenames)
3. `.data2promptignore` patterns (project-specific)

```python
def _build_spec(self):
    patterns = []
    for folder in self.ignore_folders:
        patterns.append(f"{folder}/")
    for file in self.ignore_files:
        patterns.append(file)
    patterns.extend(load_ignore_file(self.project_path, '.data2promptignore'))
    return pathspec.PathSpec.from_lines('gitignore', patterns)
```

#### `_load_all_gitignores() -> List[Tuple[Path, pathspec.PathSpec]]`

Walks the project tree once at init time and collects a `PathSpec` for every
`.gitignore` found, paired with the directory that contains it.

```python
def _load_all_gitignores(self):
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
```

**Behavior:**
- Prunes `.git` **and every ignored directory** during the walk, so `.gitignore`
  files inside `venv/`, `node_modules/`, etc. are neither collected nor walked
  (previously only `.git` was skipped, making init O(full tree) on large projects)
- A `.gitignore` with no effective patterns (empty or comments only) produces no spec entry
- Runs once at construction; result is stored in `self._gitignore_specs`

#### `_is_ignored_by_gitignore(path: Path, is_dir: bool = False) -> bool`

Checks a path against every per-directory gitignore spec. For each spec, the path is
matched **relative to the spec's base directory**, so patterns are correctly scoped.
When `is_dir=True` the path is additionally matched with a trailing separator, so
directory-only patterns (`build/`) match the directory itself and allow pruning.

```python
def _is_ignored_by_gitignore(self, path: Path, is_dir: bool = False) -> bool:
    for base_dir, spec in self._gitignore_specs:
        try:
            rel = path.relative_to(base_dir)
        except ValueError:
            continue  # spec's base is not an ancestor of this path
        rel_str = str(rel)
        if spec.match_file(rel_str):
            return True
        if is_dir and spec.match_file(rel_str + os.sep):
            return True
    return False
```

**Scoping rule:** A `.gitignore` at `src/` with pattern `*.log` will match
`src/app.log` and `src/deep/app.log`, but will not match `app.log` at the project
root. This matches real git behavior.

**Known limitation:** Cross-file negations are not supported. If a parent `.gitignore`
ignores `*.log` and a child `.gitignore` contains `!important.log`, the file remains
ignored. Negations work correctly within a single `.gitignore` file (handled by
`pathspec`), but not across files. This limitation is shared by most similar tools.

#### `_is_ignored(path: Path, is_dir: bool = False) -> bool`

Checks if a given path should be ignored based on all rules.

```python
def _is_ignored(self, path: Path, is_dir: bool = False) -> bool:
    rel_path = path.relative_to(self.project_path)
    rel_str = str(rel_path)

    if self.spec.match_file(rel_str):                   # CLI + .data2promptignore
        return True
    if is_dir and self.spec.match_file(rel_str + os.sep):
        return True
    if self._is_ignored_by_gitignore(path, is_dir=is_dir):  # per-dir gitignores
        return True
    if path == self._output_path:                       # our own output file
        return True
    return False
```

**Why `is_dir` exists:** `_build_spec()` compiles folder ignores as directory-only
patterns (`venv/`), and pathspec's dir-only patterns never match a bare name
without its trailing slash. Before this flag, `_is_ignored("venv")` returned
`False`, so pruning silently failed and the walk descended into every ignored
tree (files were still filtered afterwards — correctness held, performance didn't).

**Output-file exclusion is by path, not name:** the scanner excludes exactly
`project_path / output_file`, so `-o out/PROMPT` is excluded at its real location
and a *user's own* file that merely shares the basename survives. Older generated
outputs under other names are still caught downstream by the `GENERATION_FLAG`
check in `DefaultParser`. (A former rule that excluded any file matching
`Path(sys.argv[0]).name` was removed: when invoked as `python .../main.py` it
silently dropped every `main.py` in the scanned project.)

**Edge Cases Handled:**
- `ValueError` when path is not relative to project (returns `False`)
- Empty string path check (returns `False` for project root itself)

### Public Methods

#### `scan() -> List[Path]`

Discovers all files in the project path, respecting ignore rules.

```python
files = scanner.scan()
for file_path in files:
    process(file_path)
```

**Algorithm:**
1. `os.walk()` traverses directory tree
2. **In-place pruning**: `dirs[:] = sorted(...)` removes ignored dirs from walk
   (checked with `is_dir=True` so directory-only patterns match)
3. Files are visited in sorted order and checked individually with `_is_ignored()`
4. Returns list of `Path` objects — deterministic across platforms/filesystems

**Why In-Place Pruning Matters:**
Using `dirs[:] = ...` modifies the list in-place, which changes `os.walk()`'s behavior to skip those directories entirely. This is more efficient than checking and skipping during iteration.

#### `generate_tree(files: Optional[List[Path]] = None) -> str`

Generates a flat list of files in the project structure. Accepts the result of a
previous `scan()` so the tree and the processed content are derived from the
**same walk** (this is what `main.py` does — the tree can never diverge from the
files actually rendered, and the tree is no longer a second full-tree walk).
Falls back to calling `scan()` itself when no list is given.

```python
files = scanner.scan()
tree = scanner.generate_tree(files)
print(tree)
# Output:
# README.md
# src\data2prompt\main.py
# src\data2prompt\utils.py
```

**Characteristics:**
- Returns backslash-separated paths for Windows consistency
- Sorted alphabetically for deterministic output
- Ignores directories in output (only files)

---

## Standalone Utility Functions

### `load_ignore_file(directory: Union[str, Path], filename: str = '.data2promptignore') -> List[str]`

Loads and parses ignore patterns from a file.

```python
patterns = load_ignore_file(".", ".gitignore")
# Returns: ["*.pyc", "__pycache__/", ".vscode/"]
```

**File Format:**
```
# Comments are ignored
*.pyc              # File pattern
__pycache__/       # Directory pattern (trailing slash)
.git/              # Directory pattern
```

**Implementation:**

```python
def load_ignore_file(directory, filename):
    ignore_path = Path(directory) / filename
    ignore_list: List[str] = []

    if ignore_path.exists():
        with ignore_path.open('r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                ignore_list.append(line)

    return ignore_list
```

**Error Handling:**
- Wraps the read in try-except (`OSError`)
- Prints warning via `ui.print_warning()` if file cannot be read
- Returns empty list on any error (fail-safe)

---

## Usage Examples

### Complete Token Counting Workflow

```python
from data2prompt.utils import count_tokens

# Count tokens — the bundled BPE file is loaded on first call, cached for the rest
code = '''
def process_data(df: pd.DataFrame) -> Dict[str, Any]:
    """Process a DataFrame and return statistics."""
    return {
        "rows": len(df),
        "columns": len(df.columns),
        "dtypes": df.dtypes.to_dict()
    }
'''

token_count, method = count_tokens(code)
print(f"Tokens: {token_count} (method: {method})")
# Output: Tokens: 53 (method: o200k_base)
```

### Safely Wrapping Content in Markdown

````python
from data2prompt.utils import get_dynamic_wrapper

content = """
```python
def example():
    print("Hello")
```
"""

wrapper = get_dynamic_wrapper(content)
safe_output = f"{wrapper}\n{content}\n{wrapper}"
# Output uses 4 backticks: ````\n{content}\n````
````

### Using ProjectScanner

```python
from pathlib import Path
from data2prompt.utils import ProjectScanner

scanner = ProjectScanner(
    project_path=Path("."),
    ignore_folders={".git", "node_modules", "__pycache__", ".venv"},
    ignore_files={".DS_Store", "*.pyc", "*.log"},
    output_file="context.md",
    use_gitignore=True
)

# Discover all files
all_files = scanner.scan()
print(f"Found {len(all_files)} files")

# Generate tree representation
tree = scanner.generate_tree()
print(tree)
```

### Checking File Types

```python
from pathlib import Path
from data2prompt.utils import is_binary

files = [Path("image.png"), Path("readme.md"), Path("data.csv")]

for f in files:
    if is_binary(f):
        print(f"{f.name}: BINARY (skip)")
    else:
        print(f"{f.name}: TEXT (parse)")
```

---

## Error Handling

All functions in `utils.py` follow defensive programming principles:

| Function | Error Behavior | Return Value |
|----------|---------------|--------------|
| `_load_encoding()` | Any exception | Propagates to caller |
| `count_tokens()` | BPE load fails → regex; regex fails → word count | Falls back to next method |
| `is_binary()` | OSError reading file | `False` |
| `load_ignore_file()` | Exception reading file | Empty list + warning |
| `ProjectScanner.scan()` | OSError | Continues, skips file |

---

## Constants Used

The module itself imports no configuration constants. The ignore sets it receives
(`CORE_IGNORES`, `CORE_IGNORE_FILES` from [`constants.py`](../src/data2prompt/constants.py#L1))
are merged into the `Config` by `cli.py` and passed in through the
`ProjectScanner` constructor by `main.py`.