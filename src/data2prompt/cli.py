import argparse
from dataclasses import dataclass, field
from typing import Set


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
    SUPPORTED_FORMATS
)

@dataclass
class Config:
    """Data Transfer Object for application configuration."""
    output: str
    format: str
    csv_sample_size: int
    seed: int
    sql_sample_size: int
    sql_max_lines: int
    max_lines: int
    max_sheets: int
    line_length_threshold: int
    truncated_line_length: int
    table_limit: int
    table_truncate: int
    ignore_folders: Set[str] = field(default_factory=set)
    ignore_files: Set[str] = field(default_factory=set)
    max_file_size: int = 0
    skip_exts: Set[str] = field(default_factory=set)
    use_gitignore: bool = True
    clipboard: bool = False
    schema_only: bool = False
    stats_summary: bool = True
    env_keys: bool = True

def setup_cli() -> Config:
    """Configures the Command Line Interface (CLI) for the tool.

    Defines all available flags and their help descriptions.

    Returns:
        Config: A type-safe configuration object.
    """
    parser = argparse.ArgumentParser(
        description="📊 Data2Prompt: High-tech prompt packaging for Data Scientists."
    )
    
    # Output settings
    parser.add_argument('-o', '--output', default=DEFAULT_OUTPUT_FILE,
                        help=f'Base name of the generated file (default: {DEFAULT_OUTPUT_FILE})')
    
    parser.add_argument('-f', '--format', choices=list(SUPPORTED_FORMATS.keys()), default=DEFAULT_FORMAT,
                        help=f'Output format: xml or markdown (default: {DEFAULT_FORMAT})')
    
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
    
    # Line Truncation settings
    parser.add_argument('--line-length-threshold', type=int, default=DEFAULT_LINE_LENGTH_THRESHOLD,
                        help=f'Max characters per line before truncation (default: {DEFAULT_LINE_LENGTH_THRESHOLD})')
    parser.add_argument('--truncated-line-length', type=int, default=DEFAULT_TRUNCATED_LINE_LENGTH,
                        help=f'Length to truncate long lines to (default: {DEFAULT_TRUNCATED_LINE_LENGTH})')

    # Table Truncation settings
    parser.add_argument('--table-limit', type=int, default=DEFAULT_TABLE_CHAR_LIMIT,
                        help=f'Max characters for a single table/sheet after sampling (default: {DEFAULT_TABLE_CHAR_LIMIT})')
    parser.add_argument('--table-truncate', type=int, default=DEFAULT_TABLE_TRUNCATED_SIZE,
                        help=f'Length to truncate large tables to (default: {DEFAULT_TABLE_TRUNCATED_SIZE})')

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
    
    parser.add_argument('--no-gitignore', action='store_false', dest='use_gitignore',
                        default=DEFAULT_USE_GITIGNORE,
                        help='Disable automatic .gitignore detection and filtering')

    # Output destination
    parser.add_argument('-c', '--clipboard', action='store_true', dest='clipboard',
                        default=DEFAULT_CLIPBOARD,
                        help='Copy the generated output to the system clipboard instead of writing a file')

    # Data representation toggles
    parser.add_argument('--schema-only', action='store_true', dest='schema_only',
                        default=DEFAULT_SCHEMA_ONLY,
                        help='Emit only the schema (columns and dtypes) of data files, omitting data rows')
    parser.add_argument('--no-stats-summary', action='store_false', dest='stats_summary',
                        default=DEFAULT_STATS_SUMMARY,
                        help='Disable the per-table stats metadata block (dtypes, missing counts/%%, describe summary)')

    # Secrets handling
    parser.add_argument('--no-env-keys', action='store_false', dest='env_keys',
                        default=DEFAULT_ENV_KEYS,
                        help='Skip .env files entirely instead of listing their variable names with redacted values')

    args = parser.parse_args()
    
    # --- Argument Merging Logic ---
    # We combine the user's terminal input with our CORE constants.
    # This ensures that even if a user provides custom ignores, essential items
    # like '.git' or binary extensions are still respected.
    
    # Combine base name with format-specific extension
    extension = SUPPORTED_FORMATS.get(args.format, SUPPORTED_FORMATS.get(DEFAULT_FORMAT))
    final_output_name = f"{args.output}{extension}"

    return Config(
        output=final_output_name,
        format=args.format,
        csv_sample_size=args.csv_sample_size,
        seed=args.seed,
        sql_sample_size=args.sql_sample_size,
        sql_max_lines=args.sql_max_lines,
        max_lines=args.max_lines,
        max_sheets=args.max_sheets,
        line_length_threshold=args.line_length_threshold,
        truncated_line_length=args.truncated_line_length,
        table_limit=args.table_limit,
        table_truncate=args.table_truncate,
        ignore_folders=set(args.ignore_folders) | CORE_IGNORES,
        ignore_files=set(args.ignore_files) | CORE_IGNORE_FILES,
        max_file_size=args.max_file_size,
        skip_exts=set(args.skip_exts) | CORE_SKIP_EXTS,
        use_gitignore=args.use_gitignore,
        clipboard=args.clipboard,
        schema_only=args.schema_only,
        stats_summary=args.stats_summary,
        env_keys=args.env_keys
    )
