# Installation

`data2prompt` is published on PyPI as [`data2prompt`](https://pypi.org/project/data2prompt/)
and exposes a single console script, `data2prompt`, wired to
`data2prompt.main:main` in `pyproject.toml`. Because it is a normal PyPI package
with a console-script entry point, any Python installer that supports isolated
tool environments (`uv`, `pipx`) can install it without extra packaging work.

## Prerequisites

- **Python**: 3.10 or higher (`requires-python = ">=3.10"`).
- **An installer**: one of `uv`, `pipx`, or `pip`. Only `pip` ships with Python.

## Installing from PyPI

`data2prompt` is a CLI tool rather than a library, so the recommended installs
put it in its own isolated environment instead of into a project's site-packages.

```bash
# No install: fetch into uv's cache and run in one step
uvx data2prompt

# Isolated global install, via uv
uv tool install data2prompt

# Isolated global install, via pipx
pipx install data2prompt

# Into an already-active virtual environment
pip install data2prompt
```

Notes on each:

- **`uvx`** ([uv docs](https://docs.astral.sh/uv/)) resolves and caches the
  package on first use, then runs the console script from an ephemeral
  environment. Nothing is added to `PATH` and nothing persists beyond uv's cache,
  which makes it the lowest-friction way to try the tool or to run it
  occasionally in a project directory.
- **`uv tool install`** and **`pipx install`** do the same job: each creates a
  dedicated virtual environment and places a `data2prompt` shim on `PATH`. They
  differ in setup friction. uv's standalone installer places `uv` itself in the
  same directory it later uses for tool shims (`uv tool dir --bin`, typically
  `~/.local/bin`), so that entry is usually on `PATH` before the first tool is
  installed; `uv tool update-shell` exists for the cases where it is not, and uv
  warns when that applies. pipx is normally installed with `pip`, which puts the
  pipx executable somewhere other than pipx's shim directory, so `pipx ensurepath`
  is generally required once on a fresh install. Either way the shims are
  per-user, not machine-wide, and a new shell is needed to pick up a `PATH` change.
- **`pip install`** installs into whatever environment is currently active. This
  is appropriate when adding `data2prompt` to an existing project environment,
  but it puts the tool's dependencies (`pandas`, `rich`, `tiktoken`, and others)
  alongside the project's own.

## Optional: columnar formats

`ArrowParser` handles `.parquet`, `.feather`, and `.arrow`, and requires
`pyarrow`. It is declared as the `parquet` optional dependency rather than a core
one, so it is not installed by default:

```bash
uvx --from "data2prompt[parquet]" data2prompt   # no install
uv tool install "data2prompt[parquet]"          # uv global install
pipx install "data2prompt[parquet]"             # fresh pipx install
pipx inject data2prompt pyarrow                 # add to an existing pipx install
pip install "data2prompt[parquet]"              # pip equivalent
```

When `pyarrow` is absent, columnar files are not silently dropped. `ArrowParser`
checks for the import first and degrades to a
`-- [Skipped: <name> requires pyarrow, ...] --` notice, listing the file in the
File Index with the status `Skipped (No pyarrow)` (see [parsers.md](parsers.md)).

## Installing from source

The commands are the same on Windows, Linux, and macOS.

```bash
git clone https://github.com/arianmokhtariha/data2prompt.git
cd data2prompt
```

Then pick one:

```bash
pip install .                      # into the active environment
pip install -e .                   # editable, into the active environment
pipx install --editable .          # editable, isolated, on PATH
uv tool install --editable .       # editable, isolated, on PATH
```

## Developer setup

```bash
git clone https://github.com/arianmokhtariha/data2prompt.git
cd data2prompt

python -m venv venv
.\venv\Scripts\activate            # Windows
source venv/bin/activate           # macOS/Linux

pip install -e .[dev]
pytest
```

The `dev` extra adds `pytest`. To work on the columnar parsers as well, install
both extras: `pip install -e ".[dev,parquet]"`.

## Dependencies

Core dependencies, all declared in `pyproject.toml`:

| Package | Minimum | Used for |
| :--- | :--- | :--- |
| `pandas` | 2.0.0 | Tabular parsing, profiling, and sampling |
| `openpyxl` | 3.1.0 | Excel workbook reading |
| `tabulate` | 0.9.0 | Rendering schema and sample tables |
| `rich` | 13.0.0 | Terminal UI, progress bar, and final report |
| `tiktoken` | 0.7.0 | BPE tokenization for token counting |
| `regex` | 2024.0.0 | Pattern support, and the fallback token counter |
| `pathspec` | 0.12.0 | Gitignore-style pattern matching during the scan |

Optional extras:

| Extra | Package | Used for |
| :--- | :--- | :--- |
| `parquet` | `pyarrow>=14.0.0` | `.parquet`, `.feather`, and `.arrow` support |
| `dev` | `pytest>=8.0.0` | Running the test suite |

SQLite support uses the standard library's `sqlite3` module and needs no
dependency. Token counting reads a BPE file bundled with the package
(`data2prompt/encodings/*.tiktoken`, shipped via `tool.setuptools.package-data`),
so no encoding is ever downloaded at runtime. See [utils.md](utils.md).
