# Command Line Interface (CLI)

The `data2prompt` CLI provides a flexible and powerful interface for packaging codebases into token-aware representations optimized for Large Language Model context windows. Built on Python's `argparse`, it follows the **Modular Functional Orchestration (MFO)** pattern where argument definition and merging logic reside in this module.

## Architecture Overview

```mermaid
graph LR
    CLI[cli.py] -->|Defines Args| Main[main.py]
    Constants[constants.py] -->|Provides Defaults| CLI
    CLI -->|Returns Config| Main
```

The CLI module serves as the **entry point** for user configuration, responsible for:
- Defining all command-line arguments with type validation
- Merging user inputs with core constants (Safe-by-Default philosophy)
- Returning a type-safe `Config` Data Transfer Object (DTO) to the orchestration layer

## The `Config` Data Transfer Object

The [`Config`](../src/data2prompt/cli.py#L27) dataclass encapsulates all application settings:

```python
@dataclass
class Config:
    """Data Transfer Object for application configuration."""
    output: str                          # Final output filename with extension
    format: str                          # Output format: 'xml' or 'markdown'
    csv_sample_size: int                 # Rows to sample from CSV files
    seed: int                            # Random seed for reproducible sampling
    sql_sample_size: int                 # INSERT statements to keep in SQL
    sql_max_lines: int                   # Max non-data lines in SQL files
    max_lines: int                       # Max lines per notebook cell
    max_sheets: int                      # Excel sheets to process
    max_tables: int                      # SQLite tables/views per database
    line_length_threshold: int           # Chars per line before truncation
    truncated_line_length: int           # Truncation target length
    table_limit: int                     # Max chars per table after sampling
    table_truncate: int                  # Truncation target for tables
    ignore_folders: Set[str]             # Folders to exclude
    ignore_files: Set[str]               # Specific files to exclude
    max_file_size: int                   # Max file size (KB) for full read
    skip_exts: Set[str]                  # File extensions to skip content
    use_gitignore: bool                  # Whether to respect .gitignore
    clipboard: bool                      # Copy output to clipboard instead of a file
    schema_only: bool                    # Emit only data-file schemas (no rows)
    stats_summary: bool                  # Include the per-table stats metadata block
    env_keys: bool                       # List .env variable names (redacted values)
    budget: Optional[int]                # Target token budget for --budget (None = off)
```

## CLI Arguments Reference

### General

| Argument | Type | Description |
|:---------|:----:|:------------|
| `--version` | `flag` | Print `data2prompt <version>` and exit. The version is read from package metadata via `importlib.metadata` (exposed as `data2prompt.__version__`). |

### Output Configuration

| Argument | Short | Type | Default | Description |
|:---------|:-----:|:----:|:--------:|:------------|
| `--output` | `-o` | `str` | `PROMPT` | Base name of the generated output file. The appropriate extension (`.md` or `.xml`) is appended automatically based on the format. |
| `--format` | `-f` | `str` | `markdown` | Output format. Valid values: `xml`, `markdown`. |

### Budget Settings

| Argument | Short | Type | Default | Description |
|:---------|:-----:|:----:|:-------:|:------------|
| `--budget` | `-b` | `_token_budget` | `None` (`DEFAULT_BUDGET`) | Target token budget for the generated output (e.g. `50000`, `100k`, `1m`). Data-cap parameters are tightened automatically, one [de-escalation ladder step](budget.md) at a time, until the output fits; if it still cannot fit once every parameter is at its floor and every reducible file has been omitted, **no output is written** and the process exits with code 1. |

`--budget` is off (`None`) unless passed — a run without it behaves exactly
like a pre-`--budget` run: `fit_to_budget()` in
[`budget.py`](budget.md) is never called, and no per-file bookkeeping for it
is allocated. See [`budget.md`](budget.md) for the full ladder, the fit test,
and the infeasible-outcome contract.

### CSV Sampling Settings

| Argument | Short | Type | Default | Description |
|:---------|:----:|:------:|:----:|:------------|
| `--csv-sample-size` | `-s` | `int` | `15` | Number of random rows to sample from each CSV file. Used for token-efficient representation of large data files. |
| `--seed` | None | `int` | `42` |Random seed for reproducible CSV sampling. Ensures consistent output across runs. |

### SQL Parsing Settings

| Argument | Type | Default | Description |
|:---------|:----:|:--------|:------------|
| `--sql-sample-size` | `int` | `15` | Maximum number of INSERT statements to retain per table in SQL files. |
| `--sql-max-lines` | `int` | `50` | Maximum number of non-data lines and non-schema lines(ALTER, comments, etc.) to include from SQL files. |

### Notebook Settings

| Argument | Type | Default | Description |
|:---------|:----:|:--------|:------------|
| `--max-lines` | `int` | `40` | Maximum lines of text output to retain per Jupyter notebook cell. Long outputs are truncated to preserve token budget. |

### Excel Settings

| Argument | Type | Default | Description |
|:---------|:----:|:--------|:------------|
| `--max-sheets` | `int` | `10` | Maximum number of sheets to process in Excel files. Sheets beyond this limit are skipped. |

### SQLite Settings

| Argument | Type | Default | Description |
|:---------|:----:|:--------|:------------|
| `--max-tables` | `int` | `25` | Maximum number of tables/views to process per SQLite database (`.db`/`.sqlite`/`.sqlite3`). Tables beyond this limit are noted (`-- [Database truncated ...] --`) and skipped. |

### Line Truncation Settings

| Argument | Type | Default | Description |
|:---------|:----:|:--------|:------------|
| `--line-length-threshold` | `int` | `4000` | Maximum characters allowed per line before truncation is triggered. Lines exceeding this are truncated to `truncated-line-length`. |
| `--truncated-line-length` | `int` | `1000` | Number of characters to retain when a line exceeds the threshold. |

### Table Truncation Settings

| Argument | Type | Default | Description |
|:---------|:----:|:--------|:------------|
| `--table-limit` | `int` | `50000` | Maximum characters allowed for a single table or sheet representation after sampling. Tables exceeding this are truncated. |
| `--table-truncate` | `int` | `20000` | Number of characters to retain when a table/sheet exceeds the limit. |

### Exclusion Settings

| Argument | Type | Default | Description |
|:---------|:----:|:--------|:------------|
| `--ignore-folders` | `List[str]` | `[]` | Additional folder names to exclude from scanning. Core folders (`.git`, `__pycache__`, etc.) are always included. |
| `--ignore-files` | `List[str]` | `[]` | Additional specific filenames to exclude. Core ignores are always applied. |
| `--max-file-size` | `int` | `70` | Maximum file size in KB for unhandled file types to read entirely. Files larger than this only have their first 10KB included. |
| `--skip-exts` | `List[str]` | `[]` | Additional file extensions to skip content processing (content is still listed in tree). |
| `--no-gitignore` | `flag` | `True` | When specified, disables automatic `.gitignore` detection and filtering. Default sourced from [`DEFAULT_USE_GITIGNORE`](../src/data2prompt/constants.py). |

### Output Destination

| Argument | Short | Type | Default | Description |
|:---------|:-----:|:----:|:-------:|:------------|
| `--clipboard` | `-c` | `flag` | `False` | Copy the generated output directly to the system clipboard instead of writing a file. Uses OS-native tools (`clip`/`pbcopy`/`xclip`/`xsel`/`wl-copy`). If no clipboard utility is available, falls back to writing the output file and warns. |

### Data Representation Settings

| Argument | Type | Default | Description |
|:---------|:----:|:-------:|:------------|
| `--schema-only` | `flag` | `False` | Emit only the schema (column names + dtypes) of data files (CSV/Excel), omitting all data rows. SQL files keep `CREATE TABLE`/schema statements and drop `INSERT` data. Non-data files (code, notebooks, text) are unaffected. Schema metadata is computed on the **full** DataFrame. |
| `--no-stats-summary` | `flag` | `True` | When specified, disables the per-table stats metadata block (dtypes, missing count/%, and a `describe()` summary). The block is **on by default** and computed on the **full** DataFrame. Scope note: this flag gates only the *per-table* block — the document-level scaffolding (the `> Contents:` / `<stats/>` summary, the File Index, and the end-of-codebase anchor) is unconditional (see [output.md](output.md)). |

### Secrets Handling

| Argument | Type | Default | Description |
|:---------|:----:|:-------:|:------------|
| `--no-env-keys` | `flag` | `True` | When specified, skips `.env` files entirely. By default (`env_keys` true), `.env` files are detected by name and rendered as variable names with redacted values (`KEY=<redacted>`) — values are never emitted. |

All boolean flags above read their defaults from `constants.py`
(`DEFAULT_CLIPBOARD`, `DEFAULT_SCHEMA_ONLY`, `DEFAULT_STATS_SUMMARY`,
`DEFAULT_ENV_KEYS`, `DEFAULT_USE_GITIGNORE`) for uniform flag-to-default logic.

## Argument Merging Logic

The CLI implements a **Safe-by-Default** philosophy through intelligent argument merging. This is the critical logic in [`setup_cli()`](../src/data2prompt/cli.py#L119):

```python
# Combine user's terminal input with CORE constants
# This ensures essential items like '.git' or binary extensions are always respected

ignore_folders=set(args.ignore_folders) | CORE_IGNORES,
ignore_files=set(args.ignore_files) | CORE_IGNORE_FILES,
skip_exts=set(args.skip_exts) | CORE_SKIP_EXTS,
```

### Merging Behavior

| Config Field | User Input | Core Constants | Final Value |
|:-------------|:-----------|:---------------|:------------|
| `ignore_folders` | User-provided folders | [`CORE_IGNORES`](../src/data2prompt/constants.py#L4) | Union of both |
| `ignore_files` | User-provided files | [`CORE_IGNORE_FILES`](../src/data2prompt/constants.py#L12) | Union of both |
| `skip_exts` | User-provided extensions | [`CORE_SKIP_EXTS`](../src/data2prompt/constants.py#L16) | Union of both |

### Output Naming Logic

The output filename is constructed by appending the format-specific extension:

```python
extension = SUPPORTED_FORMATS.get(args.format, SUPPORTED_FORMATS.get(DEFAULT_FORMAT))
final_output_name = f"{args.output}{extension}"
```

**Examples:**
- `--output my_project --format markdown` → `my_project.md`
- `--output analysis --format xml` → `analysis.xml`
- Default (no arguments) → `PROMPT.md`

## Integration with Constants

The CLI imports defaults from [`src/data2prompt/constants.py`](../src/data2prompt/constants.py#L1):

```python
from data2prompt import __version__            # for --version
from data2prompt.constants import (
    CORE_IGNORES,           # Default folder ignores
    CORE_IGNORE_FILES,      # Default file ignores
    CORE_SKIP_EXTS,         # Default extension ignores
    DEFAULT_CSV_SAMPLE_SIZE,
    DEFAULT_SQL_SAMPLE_SIZE,
    DEFAULT_SQL_MAX_LINES,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_SHEETS,
    DEFAULT_MAX_TABLES,
    DEFAULT_SEED,
    DEFAULT_LINE_LENGTH_THRESHOLD,
    DEFAULT_TRUNCATED_LINE_LENGTH,
    DEFAULT_TABLE_CHAR_LIMIT,
    DEFAULT_TABLE_TRUNCATED_SIZE,
    DEFAULT_MAX_FILE_SIZE_KB,
    DEFAULT_OUTPUT_FILE,
    DEFAULT_FORMAT,
    DEFAULT_USE_GITIGNORE,
    DEFAULT_CLIPBOARD,
    DEFAULT_SCHEMA_ONLY,
    DEFAULT_STATS_SUMMARY,
    DEFAULT_ENV_KEYS,
    DEFAULT_BUDGET,
    SUPPORTED_FORMATS
)
```

### Core Ignore Sets

These sets are defined in [`constants.py`](../src/data2prompt/constants.py#L4) and always applied:

**[`CORE_IGNORES`](../src/data2prompt/constants.py#L4)** - Folder names excluded from tree and content:
```python
{'.git', '__pycache__', 'venv', '.vscode', '.ipynb_checkpoints',
 'node_modules', '.idea', 'dist', 'build', '.mypy_cache',
 '.pytest_cache', 'target', '.docker', '.aws', '.gcloud', '__MACOSX'}
```

**[`CORE_SKIP_EXTS`](../src/data2prompt/constants.py#L16)** - Extensions skipped (name listed, content excluded):
```python
# Data & Databases
# ('.db'/'.sqlite'/'.sqlite3' are NOT here — handled by SQLiteParser;
#  '.parquet'/'.feather'/'.arrow' are NOT here — handled by ArrowParser)
'.pbix', '.pkl', '.pickle', '.h5',
# Compressed & Binary
'.zip', '.tar', '.gz', '.7z', '.rar', '.exe', '.dll', '.so', '.bin',
# Media
'.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.mp4', '.mp3', '.mov',
# Environment & Secrets ('.env' is NOT here — handled by EnvParser, see parsers.md)
'.venv', '.pyc', '.ds_store'
```

## Integration with Main Module

The [`setup_cli()`](../src/data2prompt/cli.py#L48) function is called from [`main.py`](../src/data2prompt/main.py#L48):

```python
# In main.py
from data2prompt.cli import setup_cli, Config

def main():
    config = setup_cli()  # Retrieve user settings from the terminal
    # ... pass config to scanner, parsers, output generator
```

The `Config` object is then passed to:
- [`ProjectScanner`](../src/data2prompt/utils.py) - For file discovery with exclusion rules
- Parser registry - For format-specific content processing
- Output generator - For generating the final prompt file

## Usage Examples

### Basic Usage

```bash
# Generate default output (PROMPT.md) in current directory
data2prompt
```

### Custom Output

```bash
# Specify output filename and format
data2prompt --output my_project_context --format markdown
data2prompt -o analysis_results -f xml
```

### Sampling Configuration

```bash
# Increase CSV sampling for detailed data representation
data2prompt --csv-sample-size 200 --seed 12345

# Limit SQL file processing
data2prompt --sql-sample-size 10 --sql-max-lines 30
```

### Exclusion Patterns

```bash
# Add custom exclusions (core exclusions always apply)
data2prompt --ignore-folders venv .pytest_cache --ignore-files secret.json
data2prompt --skip-exts .log .tmp

# Disable .gitignore processing
data2prompt --no-gitignore
```

### Combined Configuration

```bash
# Full-featured example
data2prompt \
    --output comprehensive_analysis \
    --format markdown \
    --csv-sample-size 200 \
    --seed 42 \
    --sql-sample-size 15 \
    --sql-max-lines 50 \
    --max-lines 40 \
    --max-sheets 10 \
    --line-length-threshold 4000 \
    --truncated-line-length 1000 \
    --table-limit 50000 \
    --table-truncate 20000 \
    --ignore-folders venv .pytest_cache \
    --ignore-files .env \
    --max-file-size 70 \
    --skip-exts .log .tmp
```

## Edge Cases and Validation

### Argument Validation

Numeric arguments use two custom `argparse` types defined in
[`cli.py`](../src/data2prompt/cli.py):

- `_non_negative_int` (≥ 0): all counts and sizes — `--csv-sample-size`,
  `--sql-sample-size`, `--sql-max-lines`, `--max-lines`, `--max-sheets`,
  `--max-tables`, `--truncated-line-length`, `--table-truncate`,
  `--max-file-size`
- `_positive_int` (≥ 1): thresholds that would be nonsensical at zero —
  `--line-length-threshold`, `--table-limit`
- `_token_budget` (≥ 1): `--budget`. Accepts plain integers (`50000`),
  thousands with a `k` suffix (`100k`), and millions with an `m` suffix
  (`1m`, `1.5m`); case-insensitive, and commas/underscores are stripped
  before parsing (`50,000` and `50_000` both work). The suffix is stripped,
  the remainder parsed as `float`, then multiplied (`1_000` for `k`,
  `1_000_000` for `m`) and truncated to `int`. Non-numeric input raises
  `argparse.ArgumentTypeError` with an example-bearing message; a parsed
  value `< 1` raises with `"must be >= 1 token, got {parsed}"`. Both
  rejections exit with code 2, same as the other custom types.

Invalid values are rejected at parse time with exit code 2, so they can never
surface later as cryptic pandas/random errors inside the parsers. `--seed`
remains a plain `int` (any value is a valid seed).

| Edge Case | Behavior |
|:----------|:---------|
| Output name with extension | Extension is appended anyway, resulting in `file.md.xml` |
| Empty `--ignore-folders` | Uses only `CORE_IGNORES` |
| Invalid format choice | `argparse` rejects with error: `invalid choice: 'pdf' (choose from 'xml', 'markdown')` |
| Negative sample sizes | Rejected at parse time (`argparse` error, exit code 2) |
| Zero sample size | Accepted — emits headers/schema with no data rows |
| Non-existent folders in `--ignore-folders` | Silently ignored during scanning |
| `--skip-exts .PNG` (any case) | Lowercased before merging with `CORE_SKIP_EXTS`, so it still matches — every extension check in the pipeline reads `file_path.suffix.lower()`, and an un-lowercased entry would silently never match |
| `--budget` below the document's reachable floor | Not a CLI error — `fit_to_budget()` runs the full ladder and still exceeds the budget: **infeasible**. No output file is written, no clipboard copy happens, a themed failure panel is printed, and the process exits with code 1. See [`budget.md`](budget.md#outcomes-fits-vs-infeasible). |

### Known Behaviors

1. **Extension Appending**: The CLI always appends the format extension, even if the user provides their own:
   ```bash
   data2prompt -o test.md -f xml  # Results in: test.md.xml
   ```

2. **Set Merging**: User-provided exclusions are merged with core exclusions using set union (`|`), ensuring core ignores are never bypassed. `--skip-exts` values are additionally lowercased before the merge (`ignore_folders`/`ignore_files` are not — they go through `pathspec`'s gitignore-style matching, which is intentionally case-sensitive, mirroring real `.gitignore` behavior).

3. **Token-Aware Defaults**: Default values are tuned for typical token budgets (e.g., 15 CSV rows ≈ 600 tokens with tiktoken).

## Testing

The CLI merging logic is validated by [`tests/test_cli.py`](tests/test_cli.py#L1):

```python
def test_setup_cli_merges_defaults():
    # User input should be present
    assert "custom_folder" in args.ignore_folders
    assert ".foo" in args.skip_exts
    
    # CORE defaults must STILL be present (Safe-by-Default)
    assert ".git" in args.ignore_folders
    assert ".exe" in args.skip_exts
```

## See Also

- [`src/data2prompt/main.py`](../src/data2prompt/main.py#L1) - Orchestration layer that consumes `Config`

- [`docs/budget.md`](budget.md) - The `--budget` de-escalation ladder that consumes `Config.budget`

- [`src/data2prompt/constants.py`](../src/data2prompt/constants.py#L1) - Core constants and default values

- [`docs/architecture.md`](docs/architecture.md#L1) - System architecture overview
