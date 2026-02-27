import argparse
from argparse import Namespace

from .constants import (
    CORE_IGNORES,
    CORE_IGNORE_FILES,
    CORE_SKIP_EXTS,
    DEFAULT_CSV_SAMPLE_SIZE,
    DEFAULT_SQL_SAMPLE_SIZE,
    DEFAULT_SQL_MAX_LINES,
    DEFAULT_MAX_LINES,
    DEFAULT_MAX_SHEETS,
    DEFAULT_SEED,
    DEFAULT_MAX_FILE_SIZE_KB,
    DEFAULT_OUTPUT_FILE
)

def setup_cli() -> Namespace:
    """Configures the Command Line Interface (CLI) for the tool.

    Defines all available flags and their help descriptions.

    Returns:
        argparse.Namespace: An object containing the merged user and core configurations.
    """
    parser = argparse.ArgumentParser(
        description="📊 Data2Prompt: High-tech prompt packaging for Data Scientists."
    )
    
    # Output settings
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_FILE,
                        help=f'Name of the generated markdown file (default: {DEFAULT_OUTPUT_FILE})')
    
    # CSV sampling settings
    parser.add_argument('-s', '--csv-sample-size', type=int, default=DEFAULT_CSV_SAMPLE_SIZE,
                        help=f'Number of random rows to sample from CSVs (default: {DEFAULT_CSV_SAMPLE_SIZE})')
    parser.add_argument('--seed', type=int, default=DEFAULT_SEED,
                        help=f'Random seed for consistent CSV sampling (default: {DEFAULT_SEED})')
    
    # SQL sampling settings
    parser.add_argument('--sql-sample-size', type=int, default=DEFAULT_SQL_SAMPLE_SIZE,
                        help=f'Number of INSERT statements to keep in SQL files (default: {DEFAULT_SQL_SAMPLE_SIZE})')
    
    parser.add_argument('--sql-max-lines', type=int, default=DEFAULT_SQL_MAX_LINES,
                        help=f'Max non-data lines to keep in SQL files (default: {DEFAULT_SQL_MAX_LINES})')
    
    # Notebook settings
    parser.add_argument('--max-lines', type=int, default=DEFAULT_MAX_LINES,
                        help=f'Max lines of text output to keep per notebook cell (default: {DEFAULT_MAX_LINES})')
    
    # Excel settings
    parser.add_argument('--max-sheets', type=int, default=DEFAULT_MAX_SHEETS,
                        help=f'Max number of sheets to process in Excel files (default: {DEFAULT_MAX_SHEETS})')
    
    # Exclusions
    parser.add_argument('--ignore-folders', nargs='+', default=[],
                        help='Additional folders to skip entirely')
    
    parser.add_argument('--ignore-files', nargs='+', default=[],
                        help='Additional files to skip entirely')
    
    parser.add_argument('--max-file-size', type=int, default=DEFAULT_MAX_FILE_SIZE_KB,
                        help=f'Max file size in KB to read entirely (default: {DEFAULT_MAX_FILE_SIZE_KB}KB)')
    
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
