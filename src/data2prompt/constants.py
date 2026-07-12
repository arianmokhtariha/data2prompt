# --- Core Defaults & Constants ---

from typing import Dict, Optional

# Folders matching these names are excluded from both the project tree and content processing.
CORE_IGNORES = {
    '.git', '__pycache__', 'venv', '.vscode', '.ipynb_checkpoints',
    'node_modules', '.idea', 'dist', 'build', '.mypy_cache',
    '.pytest_cache', 'target', '.docker', '.aws', '.gcloud',
    '__MACOSX'
}

# Specific filenames that should be excluded from the entire process.
CORE_IGNORE_FILES = set()

# Files with these extensions will have their names listed in the project tree,
# but their actual content will be skipped.
CORE_SKIP_EXTS = {
    # Data & Databases
    # Note: '.db'/'.sqlite'/'.sqlite3' are intentionally NOT here — they are
    # routed to SQLiteParser, which extracts tables, DDL, and sampled rows.
    '.pbix', '.pkl', '.pickle', '.h5',
    # Compressed & Binary
    '.zip', '.tar', '.gz', '.7z', '.rar', '.exe', '.dll', '.so', '.bin',
    # Media
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.mp4', '.mp3', '.mov',
    # Environment & Secrets
    # Note: '.env' is intentionally NOT here — env files are detected by name and
    # routed to EnvParser, which emits variable names with redacted values.
    '.venv', '.pyc', '.ds_store'
}

# Default values for CLI arguments and processing functions
DEFAULT_CSV_SAMPLE_SIZE = 15                # Controls the number of rows per csv file.
DEFAULT_SQL_SAMPLE_SIZE = 15                # Controls the number of INSERT/data rows kept per table in SQL files.
DEFAULT_SQL_MAX_LINES = 50                  # Caps the total number of non-data lines (comments, setup, etc.) in SQL files.
DEFAULT_MAX_LINES = 40                      # Max lines of text output to keep per notebook cell.
DEFAULT_MAX_SHEETS = 10                     # Max number of sheets to process in Excel files.
DEFAULT_MAX_TABLES = 25                     # Max tables/views to process per SQLite database.
DEFAULT_DB_FULL_SCAN_MAX_ROWS = 100_000     # Above this row count, tables are LIMIT-sampled instead of fully read.
DEFAULT_DB_COUNT_MAX_BYTES = 1_073_741_824  # Skip COUNT(*) for DB files larger than ~1 GiB (rows then 'unknown').
DEFAULT_SEED = 42                           # Random seed for consistent sampling.
DEFAULT_LINE_LENGTH_THRESHOLD = 4000        # Max characters allowed per line before truncation is triggered.
DEFAULT_TRUNCATED_LINE_LENGTH = 1000        # Number of characters to keep when a line is truncated.
DEFAULT_TABLE_CHAR_LIMIT = 50000            # Max characters allowed for a single table/sheet representation after sampling.
DEFAULT_TABLE_TRUNCATED_SIZE = 20000        # Number of characters to keep when a table/sheet is truncated due to size.
DEFAULT_MAX_FILE_SIZE_KB = 70               # maximum file size of unhandled type to keep enitrely (if file is larger than that only the first 10kb will be shown)
DEFAULT_OUTPUT_FILE = 'PROMPT'              # default output base name (extension added via --format)
DEFAULT_FORMAT = 'markdown'                 # default output format

# Boolean feature toggles — every CLI boolean flag reads its default from here so
# the flag-to-default logic is uniform across the tool.
DEFAULT_USE_GITIGNORE = True                # respect .gitignore by default (--no-gitignore disables)
DEFAULT_CLIPBOARD = False                   # copy output to clipboard instead of writing a file (--clipboard)
DEFAULT_SCHEMA_ONLY = False                 # emit only the schema of data files, no data rows (--schema-only)
DEFAULT_STATS_SUMMARY = True               # include per-table stats metadata block (--no-stats-summary disables)
DEFAULT_ENV_KEYS = True                     # show env variable names with redacted values (--no-env-keys skips entirely)

# --- Token Budget Targeting (--budget) ---
# fit_to_budget() in budget.py tightens data-cap parameters down these
# floors, one ladder step at a time, verifying the real rendered token
# count after each step. Floors keep reduced output honest: a 5-row
# sample still shows structure; 0 rows would not.
DEFAULT_BUDGET: Optional[int] = None   # no budget targeting unless --budget
BUDGET_TOKEN_MARGIN = 16       # safety margin: placeholder digits shift count
BUDGET_MIN_CSV_SAMPLE = 5      # csv_sample_size floor (CSV/Excel/Arrow/SQLite rows)
BUDGET_MIN_NOTEBOOK_LINES = 10  # max_lines floor before outputs are dropped
BUDGET_MIN_SQL_SAMPLE = 5      # sql_sample_size floor
BUDGET_MIN_SQL_MAX_LINES = 20  # sql_max_lines floor
BUDGET_TEXT_FILE_SIZE_KB = 10  # max_file_size cap for text-truncation step

# Placeholder substituted for every value in a .env file so secrets never leak.
ENV_VALUE_PLACEHOLDER = '<redacted>'

# Mapping of format types to their respective file extensions
SUPPORTED_FORMATS = {
    'xml': '.xml',
    'markdown': '.md'
}

# A unique identifier added to the top of every generated file to prevent recursive scanning.
GENERATION_FLAG = "DATA2PROMPT_GENERATED_CONTENT"

# --- LLM Structured Output Constants ---
# System-instruction preambles embedded at the top of every generated document.
# Both formats carry the same information; only the syntax differs. They are the
# LLM's reading contract: document layout, structural conventions, the tool-notice
# grammar, and anti-hallucination accuracy rules.
SYSTEM_INSTRUCTIONS_MARKDOWN = """## Purpose

This document is a machine-generated snapshot of a codebase and its data
files, produced by the data2prompt tool for consumption by a Large Language
Model. Nothing in it was written by hand.

## Document layout

1. Metadata — generation timestamp, token estimate, and a content summary.
2. Budget report — present only when a token budget was requested; states
   the budget and every data-reduction adjustment applied to fit it,
   including files omitted entirely (they appear in the File Index with
   status Omitted).
3. File Index — one row per file with its type and inclusion status. Paths
   are relative to the project root, use forward slashes, and are the exact
   strings used in the `## File:` headers below.
4. Files — one section per file, introduced by `## File: {path}`, in the
   same order as the File Index.
5. End of codebase — closing marker; nothing follows it.

## Reading conventions

- File content sits in fenced code blocks. A fence may use MORE than three
  backticks when the content itself contains backticks; the fence length is
  chosen so the block never terminates early.
- Notebooks (.ipynb) are split into cells: `### Cell {n} ({type}) - {path}`,
  each with a fenced source block and an optional **Outputs:** block.
- Excel workbooks are split into sheets: `### Sheet {n}: {name} - {path}`,
  each closed by a `---` line.
- SQLite databases are split into tables: `### Table {n}: {name} - {path}`,
  each closed by a `---` line. A table's `CREATE TABLE` DDL, when shown,
  appears in a fenced sql code block before its schema block.
- Tabular data files (CSV/Excel/Parquet/Feather/Arrow/SQLite) may include a
  schema block (row/column counts, dtypes, missing values, describe() stats).
  Schema statistics are computed on the FULL dataset; the data rows shown
  are only a small random sample. A very large database table instead shows
  only its DDL and a small head sample, flagged by a `-- [Large table: ...] --`
  notice.
- Lines of the form `-- [...] --` are notices inserted by the tool
  (sampling, truncation, omission, errors). They are NOT part of the
  original file content.
- Env files list variable names only; every value is replaced with
  `<redacted>`.

## Accuracy rules

- Content marked sampled, truncated, omitted, or skipped is NOT fully
  included here. Do not infer or invent the missing parts; if asked about
  them, state that they are not available in this document.
- Sampled rows illustrate structure only — never treat them as the complete
  dataset. Use the schema block for full-dataset facts.
- The File Index Status column is authoritative for what each file
  contains: Full, Sampled, Cleaned (notebook, outputs trimmed), Truncated,
  Schema Only, Redacted, Excluded, Binary Skipped, Skipped, Error, or
  Omitted (listed but not rendered)."""

SYSTEM_INSTRUCTIONS_XML = """<purpose>
This document is a machine-generated snapshot of a codebase and its data
files, produced by the data2prompt tool for consumption by a Large Language
Model. Nothing in it was written by hand.

Document layout, in order:
1. <metadata> — generation timestamp, token estimate, and a <stats/>
   content summary.
2. <budget_report> — present only when a token budget was requested; its
   entries state the budget and every data-reduction adjustment applied to
   fit it, including files omitted entirely (status Omitted in the index).
3. <file_index> — one <entry path="..." type="..." status="..."/> per file.
   Paths are relative to the project root, use forward slashes, and exactly
   match the path attribute of the corresponding <file> element.
4. <files> — one <file path="..." type="..." status="..."> element per
   file, in the same order as the file index.
5. <end_of_codebase> — closing marker; nothing follows it.

Reading conventions:
- Element content is embedded VERBATIM — it is not XML-escaped. Treat the
  tags as structural markers, not strict XML; content may legally contain
  <, >, and & characters. Attribute values ARE quoted and escaped.
- Notebooks (.ipynb) are split into <cell path="..." index="..."
  type="..."> elements holding <content> and optional <outputs>.
- Excel workbooks are split into <sheet name="..." sheet_number="..."
  path="..."> elements.
- SQLite databases are split into <table name="..." table_number="..."
  path="..."> elements. A table's CREATE TABLE DDL, when shown, appears in a
  <ddl> element before its <schema> block.
- Tabular data files (CSV/Excel/Parquet/Feather/Arrow/SQLite) may include a
  <schema> block (row/column counts, dtypes, missing values, describe()
  stats). Schema statistics are computed on the FULL dataset; the data rows
  shown are only a small random sample. A very large database table instead
  shows only its DDL and a small head sample, flagged by a
  -- [Large table: ...] -- notice.
- Lines of the form -- [...] -- are notices inserted by the tool (sampling,
  truncation, omission, errors). They are NOT part of the original file.
- Env files list variable names only; every value is replaced with
  <redacted>.

Accuracy rules:
- Content marked sampled, truncated, omitted, or skipped is NOT fully
  included here. Do not infer or invent the missing parts; if asked about
  them, state that they are not available in this document.
- Sampled rows illustrate structure only — never treat them as the complete
  dataset. Use the <schema> block for full-dataset facts.
- The status attribute (on <entry> and <file>) is authoritative for what
  each file contains: Full, Sampled, Cleaned (notebook, outputs trimmed),
  Truncated, Schema Only, Redacted, Excluded, Binary Skipped, Skipped,
  Error, or Omitted (listed but not rendered).
</purpose>"""

# Structural tag names shared by the XML generator.
TAG_FILES = "files"
TAG_FILE = "file"
TAG_CONTENT = "content"          # Used for notebook cells
TAG_FILE_INDEX = "file_index"    # Per-file manifest (path/type/status)
TAG_INDEX_ENTRY = "entry"        # One row of the file index
TAG_END_OF_CODEBASE = "end_of_codebase"  # Recency anchor before </codebase>
TAG_BUDGET_REPORT = "budget_report"      # optional block: present only with --budget
TAG_ADJUSTMENT = "adjustment"            # one parameter adjustment row
TAG_OMITTED_FILE = "omitted_file"        # one file omitted to meet the budget

# Raw parser status -> controlled File Index vocabulary. The vocabulary is the
# contract documented in the preambles above; resolve_inclusion_status() in
# output.py falls back to a "Skipped (" prefix rule and then verbatim passthrough
# so an unmapped future status can never crash generation.
INCLUSION_STATUS_MAP: Dict[str, str] = {
    "Read": "Full",
    "Sampled": "Sampled",
    "Parsed": "Sampled",         # SQL: schema kept, data rows sampled
    "Extracted": "Sampled",      # Excel: sheets kept, rows sampled
    "Cleaned": "Cleaned",        # Notebook: full source, trimmed outputs
    "Truncated": "Truncated",
    "Schema Only": "Schema Only",
    "Redacted": "Redacted",
    "Skipped (Exclusion)": "Excluded",
    "Skipped (Binary)": "Binary Skipped",
    "Error": "Error",
}

# Ordered stat-key -> human label mapping for the document-level content summary.
# Insertion order defines render order; zero counts are dropped at render time.
STATS_SUMMARY_LABELS: Dict[str, str] = {
    "file_count": "Total files",
    "csv_count": "CSV",
    "notebook_count": "Notebooks",
    "sql_count": "SQL",
    "excel_count": "Excel workbooks",
    "excel_sheets_count": "Excel sheets",
    "parquet_count": "Parquet",
    "feather_count": "Feather",
    "arrow_count": "Arrow",
    "sqlite_count": "SQLite databases",
    "db_tables_count": "Database tables",
    "truncated_count": "Truncated",
    "binary_count": "Binary skipped",
    "excluded_count": "Excluded",
    "budget_omitted_count": "Budget omitted",
    "env_count": "Env files",
}

# --- UI & Aesthetic Constants (BLACKSITE theme) ---
# Semantic color channels — in the TUI, color always carries meaning:
# the accent marks structure, gray is chrome, white is data, yellow is a
# warning, and reverse-red is an error. Nothing decorative is bright.
UI_ACCENT = "#ff3b57"               # crimson: wordmark, titles, markers, bar fill
UI_CHROME = "grey35"                # dim gray: rules, labels, footnotes
UI_CHROME_BRIGHT = "grey58"         # lighter gray: borders, secondary labels
UI_DATA = "white"                   # actual information: paths, names, counts
UI_DATA_BOLD = "bold white"         # headline numbers
UI_WARN = "yellow"                  # attention counts and warn-level statuses
UI_ERROR = "bold white on red3"     # error statuses and fatal messages

# Section-title styling. Titles render as an accent ▰▰ marker followed by
# letter-spaced bold-white caps — reverse-video is reserved exclusively for the
# warning/error channels below, so an inverted chip always means "look here".
UI_HEADING = "bold white"                   # section titles, panel title text
UI_SECTION_MARKER = "▰▰"                    # accent tick before every title
UI_WARN_CHIP = "bold black on yellow"       # attention count badges

# Startup "glitch sweep": the wordmark churns as deterministic cipher glyphs,
# resolves left-to-right behind a hot edge, flashes white, then settles into
# the crimson gradient. Skipped entirely on non-TTY output.
UI_REVEAL_DURATION = 0.5            # total sweep time in seconds
UI_FRAME_DELAY = 0.02               # seconds per animation frame
UI_FLASH_FRAMES = 2                 # full-wordmark white frames before settling
# Unresolved columns churn through these block glyphs — restrained redaction
# static, deliberately no letters or symbols.
UI_CIPHER_GLYPHS = "░▒▓▌▐▄▀"

# Wordmark gradient, one style per banner row: hot top → deep crimson bottom,
# like a lit sign. Must stay the same length as BANNER.
UI_BANNER_GRADIENT = ("#ff6b7f", "#ff3b57", "#c9203c")

# Final-report shape
REPORT_TOP_FILES = 10               # token-heaviest files listed in the report
REPORT_COMPOSITION_ROWS = 6         # file-type rows in the composition chart
CONTEXT_WINDOW_REFERENCE = 200_000  # token-gauge reference (200K-class window)

# Final-report bar tracks. Every bar draws itself to exactly the width its
# table column really grants it, so a bar can never overflow and be
# ellipsis-truncated; these constants only cap that width (in terminal
# columns). At the 50-column cap one cell reads as 2%, so the token gauge and
# composition bars read as literal percentages. Spark bars stay narrower on
# purpose: their row already carries a long path, and they show weight
# relative to the heaviest file, not a percentage.
REPORT_GAUGE_WIDTH = 50             # token gauge in the summary grid
REPORT_CHART_WIDTH = 50             # composition chart rows
REPORT_SPARK_WIDTH = 16             # per-file bars in the payload table

# Bar cell density: terminal columns occupied by one bar cell. 1 packs a
# cell into every column (densest track, finest resolution); 2 spaces the
# cells one blank column apart (half as many cells over the same track), and
# so on. This controls how tightly cells sit inside a bar — never how long
# the bar is, which is fixed by the layout above.
REPORT_BAR_CELL_WIDTH = 1

# Compact wordmark for the application header (must stay under 80 columns).
BANNER = [
    "█▀▀▄ ▄▀▀▄ ▀▀█▀▀ ▄▀▀▄ ▀▀▀█ █▀▀▄ █▀▀▄ ▄▀▀▄ █▄ ▄█ █▀▀▄ ▀▀█▀▀",
    "█  █ █▀▀█   █   █▀▀█  ▄▄▀ █▄▄▀ █▄▄▀ █  █ █ ▀ █ █▄▄▀   █  ",
    "█▄▄▀ ▀  ▀   █   ▀  ▀ █▄▄▄ █    █ ▀▄ ▀▄▄▀ █   █ █      █  ",
]