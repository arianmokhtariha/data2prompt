import argparse

# --- Constants & Core Defaults ---
# These constants define the baseline behavior of the tool.
# User-provided arguments in the terminal will be merged with these defaults
# to ensure essential files and folders are always handled correctly.

# Folders matching these names are excluded from both the project tree and content processing.
# This includes version control, environment folders, and common IDE settings.
CORE_IGNORES = {
    '.git', '__pycache__', 'venv', '.vscode', '.ipynb_checkpoints',
    'node_modules', '.idea', 'dist', 'build', '.mypy_cache',
    '.pytest_cache', 'target', '.docker', '.aws', '.gcloud'
}

# Specific filenames that should be excluded from the entire process (tree and content).
# By default, this is empty to allow maximum flexibility, but can be populated with CORE defaults if needed.
CORE_IGNORE_FILES = set()

# Files with these extensions will have their names listed in the project tree,
# but their actual content will be skipped to avoid bloating the prompt with binary or heavy data.
CORE_SKIP_EXTS = {
    # Data & Databases
    '.pbix', '.db', '.sqlite', '.sqlite3', '.parquet', '.pkl', '.pickle', '.feather', '.h5',
    # Compressed & Binary
    '.zip', '.tar', '.gz', '.7z', '.rar', '.exe', '.dll', '.so', '.bin',
    # Media
    '.png', '.jpg', '.jpeg', '.gif', '.svg', '.pdf', '.mp4', '.mp3', '.mov',
    # Environment & Secrets
    '.env', '.venv', '.pyc', '.ds_store'
}

def setup_cli():
    """
    Configures the Command Line Interface (CLI) for the tool.
    Defines all available flags and their help descriptions.
    """
    parser = argparse.ArgumentParser(
        description="📊 Data2Prompt: High-tech prompt packaging for Data Scientists."
    )
    
    # Output settings
    parser.add_argument('-o', '--output', default='PROMPT.md',
                        help='Name of the generated markdown file (default: PROMPT.md)')
    
    # CSV sampling settings
    parser.add_argument('-s', '--csv-sample-size', type=int, default=70,
                        help='Number of random rows to sample from CSVs (default: 70)')
    parser.add_argument('--seed', type=int, default=42,
                        help='Random seed for consistent CSV sampling (default: 42)')
    
    # SQL sampling settings
    parser.add_argument('--sql-sample-size', type=int, default=70,
                        help='Number of INSERT statements to keep in SQL files (default: 70)')
    
    # Notebook settings
    parser.add_argument('--max-lines', type=int, default=55,
                        help='Max lines of text output to keep per notebook cell (default: 55)')
    
    # Exclusions
    parser.add_argument('--ignore-folders', nargs='+', default=[],
                        help='Additional folders to skip entirely')
    
    parser.add_argument('--ignore-files', nargs='+', default=[],
                        help='Additional files to skip entirely')
    
    parser.add_argument('--max-file-size', type=int, default=200,
                        help='Max file size in KB to read entirely (default: 200KB)')
    
    # file formats to ignore
    parser.add_argument('--skip-exts', nargs='+', default=[],
                        help='Additional file extensions to skip content for')
    
    args = parser.parse_args()
    
    # --- Argument Merging Logic ---
    # We combine the user's terminal input with our CORE constants.
    # This ensures that even if a user provides custom ignores, essential items
    # like '.git' or binary extensions are still respected.
    args.ignore_folders = list(set(args.ignore_folders) | CORE_IGNORES)
    args.ignore_files = list(set(args.ignore_files) | CORE_IGNORE_FILES)
    args.skip_exts = list(set(args.skip_exts) | CORE_SKIP_EXTS)
    
    return args
