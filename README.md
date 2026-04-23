# 📊 Data2Prompt

> **High-performance codebase-to-prompt orchestration for Data Science workflows and data-heavy projects.**

data2prompt is a CLI tool designed to bridge the gap between local data-heavy projects and Large Language Model (LLM) context windows. Unlike generic code-packagers, it provides an intelligent,optimized output for LLM attention mechanism, token-aware representation of a project's structure and content, specifically optimized for data-heavy environments.

## 📝 Important Note
* **Data2prompt** is not designed for pure and large **code-heavy** projects.
* **Data2prompt** is specially designed to handle codebases with fair amount of data files like **.csv**   **.sql**   **.xlsx**  **.ipynb** without exlpoding the context window.

## ✨ Core Features

*   **Smart Jupyter Parsing**: Intelligently extracts code, markdown, and text outputs from [`.ipynb`](docs/parsers.md) files while stripping heavy Base64 images and raw HTML to preserve context.
*   **Multi-Format Sampling**: Advanced sampling strategies for [CSV, SQL, and Excel](docs/parsers.md) files to preserve schema and data context which reduces the data size significantly while extracting the needed context for llm.
*   **Aggressive truncations**: To preserve context, long lines are truncated to neutralize line injections and avoid exploding the context windows, if a tabular data was still to large after sampling it will get truncated to a certain amount, also if a raw text file of unhandled type was too large it will get truncated to a certain amount. 
*   **Defensive Processing**: Automatic binary detection (Null-byte checks), size-based truncation, and line-length capping to prevent context-window poisoning.
*   **Optimized LLM attention**: the default output format is xml with xml style tags to enhance LLM anchoring for complex analysis and large context windows
*   **Token-Aware Output**: Real-time token estimation using `tiktoken` (`o200k_base`) to ensure prompts fit target LLMs (Claude 3.5, GPT-4o, Gemini 1.5) and advanced offline token counting via `regex`.
*   **Professional TUI**: A high-fidelity terminal interface built with `Rich`, featuring a Matrix-style startup animation and interactive, scrollable reports on Windows.
*   **Dynamic Markdown Wrapping**: Uses intelligent backtick depth to ensure robust nesting of code blocks in the final output.

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

```bash
# Clone the repository
git clone https://github.com/arianmokhtariha/data2prompt.git
cd data2prompt

# Install normally
pip install .

# Install in editable mode
pip install -e .

# Its Recommended to use pipx instead of pip for easier venv handling
```

### Usage

Run `data2prompt` in your project root to generate a structured prompt:

```bash
# Basic usage (defaults to XML output)
data2prompt

# Custom output with Markdown format and specific sampling
data2prompt --output my_analysis --format markdown --csv-sample-size 50 --ignore-folders venv .pytest_cache
```

### CLI Arguments

| Argument | Description | Default |
| :--- | :--- | :--- |
| `-o`, `--output` | Base name of the generated file | `PROMPT` |
| `-f`, `--format` | Output format (`xml` or `markdown`) | `xml` |
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

---
*Built with precision for the modern AI-assisted development workflow.*
