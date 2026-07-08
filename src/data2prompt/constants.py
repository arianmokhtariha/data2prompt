# --- Core Defaults & Constants ---

from typing import Dict

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
    '.pbix', '.db', '.sqlite', '.sqlite3', '.pkl', '.pickle', '.h5',
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
2. File Index — one row per file with its type and inclusion status. Paths
   are relative to the project root, use forward slashes, and are the exact
   strings used in the `## File:` headers below.
3. Files — one section per file, introduced by `## File: {path}`, in the
   same order as the File Index.
4. End of codebase — closing marker; nothing follows it.

## Reading conventions

- File content sits in fenced code blocks. A fence may use MORE than three
  backticks when the content itself contains backticks; the fence length is
  chosen so the block never terminates early.
- Notebooks (.ipynb) are split into cells: `### Cell {n} ({type}) - {path}`,
  each with a fenced source block and an optional **Outputs:** block.
- Excel workbooks are split into sheets: `### Sheet {n}: {name} - {path}`,
  each closed by a `---` line.
- Tabular data files (CSV/Excel/Parquet/Feather/Arrow) may include a schema
  block (row/column counts, dtypes, missing values, describe() stats).
  Schema statistics are computed on the FULL dataset; the data rows shown
  are only a small random sample.
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
2. <file_index> — one <entry path="..." type="..." status="..."/> per file.
   Paths are relative to the project root, use forward slashes, and exactly
   match the path attribute of the corresponding <file> element.
3. <files> — one <file path="..." type="..." status="..."> element per
   file, in the same order as the file index.
4. <end_of_codebase> — closing marker; nothing follows it.

Reading conventions:
- Element content is embedded VERBATIM — it is not XML-escaped. Treat the
  tags as structural markers, not strict XML; content may legally contain
  <, >, and & characters. Attribute values ARE quoted and escaped.
- Notebooks (.ipynb) are split into <cell path="..." index="..."
  type="..."> elements holding <content> and optional <outputs>.
- Excel workbooks are split into <sheet name="..." sheet_number="..."
  path="..."> elements.
- Tabular data files (CSV/Excel/Parquet/Feather/Arrow) may include a
  <schema> block (row/column counts, dtypes, missing values, describe()
  stats). Schema statistics are computed on the FULL dataset; the data rows
  shown are only a small random sample.
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
    "truncated_count": "Truncated",
    "binary_count": "Binary skipped",
    "excluded_count": "Excluded",
    "env_count": "Env files",
}

# --- UI & Aesthetic Constants ---
MATRIX_DARK_GREEN = (0, 150, 0)
MATRIX_NEON_GREEN = (0, 255, 0)
STARTUP_ANIMATION_DURATION = 0.9
ANIMATION_FRAME_DELAY = 0.03

# ASCII Art for the application header
ASCII_ART =  [
"                                                                                                                   ",
"  ██╗      ██████╗   █████╗  ████████╗  █████╗  ██████╗  ██████╗  ██████╗   ██████╗  ███╗   ███╗ ██████╗  ████████╗",
"  ╚██╗     ██╔══██╗ ██╔══██╗ ╚══██╔══╝ ██╔══██╗ ╚════██╗ ██╔══██╗ ██╔══██╗ ██╔═══██╗ ████╗ ████║ ██╔══██╗ ╚══██╔══╝",
"   ╚██╗    ██║  ██║ ███████║    ██║    ███████║  █████╔╝ ██████╔╝ ██████╔╝ ██║   ██║ ██╔████╔██║ ██████╔╝    ██║   ",
"   ██╔╝    ██║  ██║ ██╔══██║    ██║    ██╔══██║ ██╔═══╝  ██╔═══╝  ██╔══██╗ ██║   ██║ ██║╚██╔╝██║ ██╔═══╝     ██║   ",
"  ██╔╝     ██████╔╝ ██║  ██║    ██║    ██║  ██║ ███████╗ ██║      ██║  ██║ ╚██████╔╝ ██║ ╚═╝ ██║ ██║         ██║   ",
"  ╚═╝      ╚═════╝  ╚═╝  ╚═╝    ╚═╝    ╚═╝  ╚═╝ ╚══════╝ ╚═╝      ╚═╝  ╚═╝  ╚═════╝  ╚═╝     ╚═╝ ╚═╝         ╚═╝   "
    ]