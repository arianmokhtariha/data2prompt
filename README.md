<p align="center">
  <img src="https://raw.githubusercontent.com/arianmokhtariha/data2prompt/main/assets/banner.svg" alt="data2prompt — animated terminal banner" width="960">
</p>

<p align="center">
  <a href="https://pypi.org/project/data2prompt/"><img src="https://img.shields.io/pypi/v/data2prompt.svg?color=ff3b57&label=PyPI" alt="PyPI version"></a>
  <a href="https://pypi.org/project/data2prompt/"><img src="https://img.shields.io/pypi/dm/data2prompt.svg?color=informational&label=downloads" alt="PyPI downloads"></a>
  <a href="https://github.com/arianmokhtariha/data2prompt/actions/workflows/tests.yml"><img src="https://github.com/arianmokhtariha/data2prompt/actions/workflows/tests.yml/badge.svg" alt="Tests"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python 3.10+"></a>
  <a href="https://github.com/arianmokhtariha/data2prompt/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="MIT License"></a>
  <a href="https://github.com/arianmokhtariha/data2prompt/stargazers"><img src="https://img.shields.io/github/stars/arianmokhtariha/data2prompt?color=eda100&label=stars" alt="GitHub stars"></a>
</p>

<p align="center">
  <sub><b>Native parsers, not just kept-as-text:</b></sub><br>
  <img src="https://raw.githubusercontent.com/arianmokhtariha/data2prompt/main/assets/filetypes.svg" alt="Supported file types: .csv; .xlsx .xls .xlsm; .db .sqlite .sqlite3; .parquet .feather .arrow; .sql; .ipynb; .env" width="820">
</p>

<p align="center">
  <b>Token-aware codebase packing for data-heavy projects.</b><br>
  One command turns a project full of CSVs, notebooks, Excel workbooks and SQLite
  databases into a single, structured, LLM-ready document — sampled, profiled,
  redacted, and fitted to your context window.
</p>

---

Generic repo-to-prompt tools choke on data projects: they either skip your data
files or dump them raw, burning 90% of the context window on rows the model never
needed. **data2prompt** understands the *shape* of data work — it samples tables,
extracts schemas and per-column statistics, cleans notebooks, queries databases,
and discloses every intervention to the model in a uniform notice grammar, so the
LLM knows exactly what it is looking at and what was left out.

<p align="center">
  <img src="https://raw.githubusercontent.com/arianmokhtariha/data2prompt/main/assets/report.svg" alt="The data2prompt final report: token gauge, budget adjustments, per-type composition chart, attention badges, and the heaviest files" width="960">
</p>

## 📉 Why

The same data-heavy project, packed by three tools with default settings:

<p align="center">
  <img src="https://raw.githubusercontent.com/arianmokhtariha/data2prompt/main/assets/comparison.svg" alt="Output size comparison — repomix 22,085 KB, code2prompt 9,304 KB, data2prompt 241 KB; data2prompt is 80–85% more token-efficient" width="960">
</p>

That gap is 80–85% fewer tokens spent on the same project — and the reduction
is *representation*, not truncation. Every table still contributes its full
schema, per-column statistics computed on the complete dataset, and a seeded
random sample of real rows. The model loses row noise, not information.

## 🚀 Quick Start

```bash
# Recommended: install as a global CLI tool
pipx install data2prompt

# Or into an active virtual environment
pip install data2prompt
```

Run it from your project root:

```bash
data2prompt                    # → PROMPT.md (markdown, default settings)
data2prompt -b 100k -c        # fit the output into 100k tokens, copy to clipboard
data2prompt -f xml --schema-only   # XML format, schemas only, zero data rows
```

<details>
<summary><b>Parquet / Feather / Arrow support</b> (optional extra)</summary>

Columnar formats need [pyarrow](https://arrow.apache.org/docs/python/), which is
not bundled by default:

```bash
pipx install "data2prompt[parquet]"     # fresh install
pipx inject data2prompt pyarrow          # already installed via pipx
pip install "data2prompt[parquet]"      # pip equivalent
```

Without pyarrow these files still appear in the output with an inline note
explaining why they were skipped.
</details>

<details>
<summary><b>Install from source</b></summary>

```bash
git clone https://github.com/arianmokhtariha/data2prompt.git
cd data2prompt
pip install -e .
```
</details>

## 🔍 What Happens to Your Files

Every file type gets a strategy, not a dump:

| File type | Strategy | What the LLM sees |
| :--- | :--- | :--- |
| `.csv` | Seeded random sampling | Column schema, full-dataset stats, N sampled rows |
| `.parquet` `.feather` `.arrow` | Same, via pyarrow | Schema + stats + sample — identical treatment to CSV |
| `.xlsx` `.xls` `.xlsm` | Per-sheet extraction | Each sheet as its own schema + stats + sample section |
| `.db` `.sqlite` `.sqlite3` | Read-only stdlib `sqlite3` | Per-table `CREATE TABLE` DDL (keys, FKs, indexes) + stats + sampled rows |
| `.sql` | Statement-aware parsing | Schema statements kept intact, `INSERT` floods capped |
| `.ipynb` | Cell-level cleaning | Code, markdown and text outputs — base64 images and HTML dumps stripped |
| `.env` | Name-only redaction | `KEY=<redacted>` — variable names, never values |
| Binary files | Null-byte detection | Skipped, listed in the file index |
| Everything else | Size-aware reading | Full text, or first 10 KB past `--max-file-size` |

Two details make the samples trustworthy:

- **Statistics are computed on the full dataset, not the sample.** Dtypes,
  missing counts/percentages, and a `describe()` summary are extracted before
  sampling, so the model sees true data quality even from 15 rows.
- **Every intervention is disclosed.** Sampling, truncation, redaction, and
  skips all surface as uniform `-- [...] --` notices inside the document — the
  model is never left guessing why content looks incomplete.

## 🎛️ Fit Any Context Window: `--budget`

State the outcome you want instead of tuning knobs:

```bash
data2prompt --budget 100k
```

`--budget` runs a **de-escalation ladder** — halve CSV/SQL sample sizes, trim
notebook outputs, drop the stats blocks, switch to schema-only, and, as a last
resort, omit the heaviest remaining files — re-rendering and re-counting the
*actual* document after every step until it fits. No estimates: the number that
is checked is the number you ship.

- Accepts `50000`, `100k`, `1.5m` — commas and underscores welcome.
- A **budget report** is embedded in the document and shown in the terminal
  report: every parameter change and every omitted file, stated explicitly.
- If the budget is infeasible even at the ladder's floor, **nothing is written**
  and the process exits non-zero with the minimum achievable count — you will
  never silently receive an over-budget file.

## ✨ Features

What sets data2prompt apart from a generic repo-to-text dumper isn't any one
flag — it's that the whole pipeline is built around two rules: **never
silently lie about what the model is seeing**, and **never guess when the
real number can be measured**. Those two rules are why `--budget` re-renders
and re-counts instead of estimating, why every reduction gets a `-- [...] --`
notice instead of vanishing quietly, and why the same command on the same
project produces byte-identical output a year later.

- **Offline, exact token counting** — a bundled `o200k_base` BPE (tiktoken)
  counts the fully rendered document, scaffolding included. No network call,
  ever; a pure-regex fallback keeps counts flowing where the encoding cannot load.
- **Two output formats, one contract** — `markdown` (default) and `xml` for
  stronger structural anchoring in long contexts. Both formats are logically
  identical and governed by a written [output contract](docs/output-contract.md).
- **Context-aware system preamble** — the generated document opens with reading
  instructions for the LLM that adapt to the run: notebook conventions are only
  explained if notebooks were actually scanned, and likewise for Excel, SQLite,
  tabular schemas, and env files.
- **Deterministic by default** — `--seed 42` means the exact same rows get
  sampled on every run. Regenerate a prompt for a diff, a reproducible eval,
  or a bug report and get the identical document back, not a new random draw.
- **Fails loud, never truncates silently** — if `--budget` is infeasible even
  at the ladder's floor, **nothing is written**. You get a non-zero exit and
  the minimum achievable token count — never a file that quietly blew past
  what you asked for.
- **Secret-safe by design** — `.env` values never reach the output; long lines
  are truncated to neutralize prompt-injection padding; binary content is
  detected and excluded.
- **Scan hygiene** — respects `.gitignore` and `.data2promptignore`, ships
  hardened core ignore lists (`.git`, `node_modules`, caches), and skips its own
  previously generated outputs automatically.
- **Straight to clipboard** — `--clipboard` pipes the result to your OS
  clipboard via native tools (`clip`/`pbcopy`/`xclip`/`wl-copy`) with a file
  fallback.
- **A terminal UI that earns its place** — an animated glitch-sweep banner, a
  transient progress bar, and a final report with a token gauge against a 200K
  context window, a per-type composition chart, attention badges, and the
  heaviest files each with a token-share bar. Animations disable themselves on
  non-interactive output, and every quantity in the report doubles as a
  proportional bar.

## ⌨️ CLI Reference

The flags you will actually reach for:

| Flag | Default | Purpose |
| :--- | :--- | :--- |
| `-o`, `--output` | `PROMPT` | Base name of the generated file |
| `-f`, `--format` | `markdown` | Output format: `markdown` or `xml` |
| `-b`, `--budget` | off | Target token budget (`50000`, `100k`, `1.5m`) |
| `-c`, `--clipboard` | off | Copy to clipboard instead of writing a file |
| `-s`, `--csv-sample-size` | `15` | Rows sampled per tabular file |
| `--seed` | `42` | Sampling seed — identical output across runs |
| `--schema-only` | off | Schemas and dtypes only, zero data rows |
| `--max-lines` | `40` | Output lines kept per notebook cell |
| `--max-sheets` | `10` | Sheets processed per Excel workbook |
| `--max-tables` | `25` | Tables processed per SQLite database |
| `--max-file-size` | `70` | KB threshold before plain files are head-truncated |
| `--no-stats-summary` | stats on | Drop the per-table stats block |
| `--no-env-keys` | redact | Skip `.env` files entirely instead of redacting |
| `--no-gitignore` | respect | Ignore `.gitignore` rules while scanning |
| `--ignore-folders` / `--ignore-files` / `--skip-exts` | — | Additional exclusions, merged with the core ignore sets |

Full reference with validation rules and edge cases: [docs/cli.md](docs/cli.md)

## 🏗️ Architecture

Small, single-responsibility modules under an orchestration layer — parsing,
output generation, scanning, token budgeting, and UI never bleed into each other:

```mermaid
graph LR
    CLI[cli.py] --> Main[main.py]
    Main -->|Registry| Parsers[parsers.py]
    Main -->|Strategy| Output[output.py]
    Main -->|Scan + tokens| Utils[utils.py]
    Main -->|Feedback| UI[ui.py]
    Main -->|--budget| Budget[budget.py]
    Budget --> Output
```

- A **parser registry** maps extensions to specialized parsers; new file types
  plug in without touching the pipeline.
- An **output strategy** keeps markdown and XML generation interchangeable and
  contract-bound.
- Fully typed (PEP 484), stdlib-first, with per-file error containment — one
  corrupt file degrades to an inline error note, never a crashed run.

Every module has a matching deep-dive document:

| | |
| :--- | :--- |
| [Architecture](docs/architecture.md) | Module layout, data flow, design patterns |
| [Parsers](docs/parsers.md) | Per-format strategies and the tool-notice grammar |
| [Budget](docs/budget.md) | The `--budget` de-escalation ladder, end to end |
| [Output](docs/output.md) · [Output Contract](docs/output-contract.md) | Document structure and the markdown/XML parity rules |
| [CLI](docs/cli.md) · [UI](docs/ui.md) · [Installation](docs/installation.md) | Flags, the terminal interface, setup |

## 🛠️ Development

```bash
pip install -e .[dev]
pytest
```

Contributions are welcome — new file-type parsers are the highest-leverage place
to start (the registry makes them self-contained). Open an issue first for
anything that changes the generated document, and read
[docs/output-contract.md](docs/output-contract.md) before touching output code.

---

<p align="center"><i>If data2prompt saved you time and tokens, a ⭐ helps other data people find it.</i></p>
