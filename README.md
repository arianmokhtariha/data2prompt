<p align="center">
  <img src="assets/banner.png" alt="Data2Prompt Banner" width="800">
</p>

<p align="center">
  <a href="https://pypi.org/project/data2prompt/"><img src="https://img.shields.io/pypi/v/data2prompt.svg" alt="PyPI version"></a>
  <a href="https://github.com/arianmokhtariha/data2prompt/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://github.com/arianmokhtariha/data2prompt"><img src="https://img.shields.io/badge/status-active-brightgreen.svg" alt="Status"></a>
</p>


> **High-performance codebase-to-prompt orchestration for Data Science workflows and data-heavy projects.**

data2prompt is a CLI tool designed to bridge the gap between local data-heavy projects and Large Language Model (LLM) context windows. Unlike generic code-packagers, it provides an intelligent,optimized output for LLM attention mechanism, token-aware representation of a project's structure and content.

## 📝 Important Note
**Data2prompt** is purpose-built for **data-heavy projects** (`.csv`, `.sql`, `.xlsx`, `.ipynb`), not large pure-code repositories. It intelligently samples and truncates data files to prevent context window explosion while preserving semantic structure.


## 🎯 Why Data2Prompt?
Generic code-to-prompt tools choke on data files—they either skip them entirely or dump raw CSVs that waste 90% of your context window. Data2Prompt solves this with intelligent sampling, schema extraction, and LLM-optimized formatting specifically designed for data science workflows.

<p align="center">
  <img src="assets/data2prompt-comparison.png" alt="Data2Prompt Comparison" width="1200">
</p>


## ✨ Core Features

*   **Smart Jupyter Parsing**: Intelligently extracts code, markdown, and text outputs from [`.ipynb`](docs/parsers.md) files while stripping heavy Base64 images and raw HTML to preserve context.
*   **Multi-Format Sampling**: Advanced sampling strategies for [CSV, SQL, and Excel](docs/parsers.md) files to preserve schema and data context which reduces the data size significantly while extracting the needed context for llm.
*   **Aggressive truncations**: To preserve context, long lines are truncated to neutralize line injections and avoid exploding the context windows, if a tabular data was still to large after sampling it will get truncated to a certain amount, also if a raw text file of unhandled type was too large it will get truncated to a certain amount. 
*   **Defensive Processing**: Automatic binary detection (Null-byte checks), Checks if a file is binary by looking for a Null byte in the first 1024 bytes.
*   **Optimized LLM attention**: The default output format is markdown with well structured schema and another option is xml output with xml style tags to enhance LLM anchoring for complex analysis and large context windows
*   **Token-Aware Output**: Real-time token estimation using `tiktoken` (`o200k_base`) to ensure prompts fit target LLMs (Claude 3.5, GPT-4o, Gemini 1.5) and advanced offline token counting via `regex`.
*   **Professional TUI**: A high-fidelity terminal interface built with `Rich`, featuring a Matrix-style startup animation and interactive, scrollable reports on Windows.
*   **Dynamic Markdown Wrapping**: Uses intelligent backtick depth to ensure robust nesting of code blocks in the final output.
*   **Gitignore aware**: Respects the .gitignore rules by default and you can turn this feature off with cli argument(--no-gitignore) if needed.

## 🏗️ Architecture & Engineering Standards

This project is a portfolio-grade implementation of the **Modular Functional Orchestration (MFO)** pattern, reflecting senior-level engineering maturity:

*   **Registry & Strategy Patterns**: Uses a `ParserRegistry` for extensible file handling and an `OutputGenerator` strategy for multiple formats (Markdown, XML).
*   **Centralized Configuration**: All core logic, magic numbers, and default ignore lists reside in [`src/data2prompt/constants.py`](src/data2prompt/constants.py).
*   **Strict Type Hinting**: Fully typed function signatures (PEP 484) across all modules.
*   **UI Encapsulation**: All terminal feedback is handled by a dedicated `UIHandler`, ensuring a clean separation between logic and presentation.

For a deep dive into the system design, see the [Architecture Documentation](docs/architecture.md).

## 🚀 Quick Start

### Installation

Ensure you have Python 3.10+ installed.

**Recommended — using pipx (installs as a global CLI tool):**

Don't have pipx? Install it first:
```bash
pip install pipx
pipx ensurepath
```

Then install data2prompt:
```bash
pipx install data2prompt
```

**Alternative — using pip (requires an active virtual environment):**
```bash
pip install data2prompt
```

**Update to the latest version:**
```bash
# with pipx
pipx upgrade data2prompt

# with pip
pip install --upgrade data2prompt
```

### Install from the source

```bash
# Clone the repository
git clone https://github.com/arianmokhtariha/data2prompt.git
cd data2prompt

# Install normally
pip install .

# Or Install in editable mode
pip install -e .
```

### Usage

Run `data2prompt` in your project root to generate a structured prompt:

```bash
# Basic usage (defaults to markdown output)
data2prompt

# Custom output with xml format and specific sampling
data2prompt --output my_analysis --format xml --csv-sample-size 50 --ignore-folders venv .pytest_cache
```

### CLI Arguments

| Argument | Description | Default |
| :--- | :--- | :--- |
| `-o`, `--output` | Base name of the generated file | `PROMPT` |
| `-f`, `--format` | Output format (`xml` or `markdown`) | `markdown` |
| `-s`, `--csv-sample-size` | Number of random rows to sample from CSVs | `15` |
| `--max-lines` | Max lines of text output per notebook cell | `40` |
| `--max-file-size` | Max file size in KB to read entirely | `70` |

See the [CLI Reference](docs/cli.md) for a full list of arguments.

## 📚 Documentation

Explore the detailed documentation for more information:

*   [**Architecture**](docs/architecture.md): MFO pattern and module flow.
*   [**CLI Reference**](docs/cli.md): Detailed argument descriptions and usage.
*   [**Parsers**](docs/parsers.md): How different file types are handled.
*   [**Output Formats**](docs/output.md): Details on Markdown and XML generation.
*   [**User Interface**](docs/ui.md): Features of the high-tech TUI.
*   [**Installation**](docs/installation.md): Comprehensive setup guide.

## 🛠️ Developer Setup

To contribute or run tests:

```bash
pip install -e .[dev]
pytest
```

## 🌟 Show Your Support

If Data2Prompt saves you token costs or speeds up your workflow, consider:
- ⭐ Starring the repo
- 🐛 Reporting issues or suggesting features
- 🔀 Contributing parsers for new file types

---
*Built with precision for the modern AI-assisted development workflow.*
