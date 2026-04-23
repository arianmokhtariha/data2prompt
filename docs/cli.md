# Command Line Interface (CLI)

The `data2prompt` CLI is designed for flexibility and control, allowing users to customize how their project is packaged for LLM context windows.

## Configuration Management

The CLI uses a `Config` Data Transfer Object (DTO) to manage application settings. User inputs from the terminal are merged with core constants defined in [`src/data2prompt/constants.py`](src/data2prompt/constants.py), ensuring that essential ignore rules (e.g., `.git`, binary files) are always respected.

## CLI Arguments

| Argument | Description | Default |
| :--- | :--- | :--- |
| `-o`, `--output` | Base name of the generated file | `PROMPT` |
| `-f`, `--format` | Output format (`xml` or `markdown`) | `xml` |
| `-s`, `--csv-sample-size` | Number of random rows to sample from CSVs | `15` |
| `--seed` | Random seed for consistent sampling | `42` |
| `--sql-sample-size` | Number of INSERT statements to keep in SQL files | `15` |
| `--sql-max-lines` | Max non-data lines to keep in SQL files | `50` |
| `--max-lines` | Max lines of text output per notebook cell | `40` |
| `--max-sheets` | Max number of sheets to process in Excel files | `10` |
| `--line-length-threshold` | Max characters per line before truncation | `4000` |
| `--truncated-line-length` | Length to truncate long lines to | `1000` |
| `--table-limit` | Max characters for a single table after sampling | `50000` |
| `--table-truncate` | Length to truncate large tables to | `20000` |
| `--ignore-folders` | Additional folders to skip | `[]` |
| `--ignore-files` | Additional files to skip | `[]` |
| `--max-file-size` | Max file size in KB to read entirely | `70` |
| `--skip-exts` | Additional file extensions to skip | `[]` |

## Usage Example

```bash
data2prompt --output my_project_context --format markdown --csv-sample-size 200 --ignore-folders venv .pytest_cache
```
