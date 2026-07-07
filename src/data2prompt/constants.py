# --- Core Defaults & Constants ---

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
# Refactored System Instructions (Repomix Style)
SYSTEM_INSTRUCTIONS_MARKDOWN = """## purpose: \nThis document is a structured representation of a codebase and data schema. It is designed to be consumed by a Large Language Model.
The output is organized into sections:
1. Directory Structure: List of all files in this project.
2. Files: The content of each file, clearly labeled with its path using '## File: {path}' headers.
For all standard files, content is wrapped in markdown code blocks using dynamic backtick depth to ensure robust nesting.
For notebooks, individual cells are clearly labeled with cell numbers, types, and their respective file paths.
For Excel files, individual sheets are clearly labeled with sheet names, numbers, and their respective file paths."""

SYSTEM_INSTRUCTIONS_XML = """<purpose>\nThis document is a structured representation of a codebase and data schema. It is designed to be consumed by a Large Language Model.
The output is organized into XML tags:
1. <directory_structure>: List of all files in this project.
2. <files>: Contains the repository's files.
3. <file>: Represents a single file with a 'path' attribute.
4. <cell>: Used within notebooks to encapsulate individual cells, featuring 'path', 'number', and 'type' attributes.
5. <sheet>: Used within Excel files to encapsulate individual sheets, featuring 'name', 'number', and 'path' attributes.
File contents are embedded verbatim (not XML-escaped); treat the tags as structural markers rather than strict XML.\n</purpose>"""

# Updated Tags
TAG_DIRECTORY_STRUCTURE = "directory_structure"
TAG_FILES = "files"
TAG_FILE = "file"
TAG_CONTENT = "content" # Used for notebook cells

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