# 📊 Data2Prompt

> **Turn your messy Data Science workspaces into clean, LLM-ready context.**

Data2Prompt is a blazing-fast CLI tool designed specifically for Data Analysts and Scientists. Unlike standard code-packagers, it intelligently parses Jupyter Notebooks, selectively samples heavy CSVs, and strips out token-wasting binary bloat, generating a perfectly structured Markdown file optimized for AI context windows (Claude, GPT-4o, Gemini).

## ✨ Features
* **🧠 Smart Jupyter Parsing:** Extracts code, markdown, and text outputs while stripping out heavy Base64 images and raw HTML tables.
* **🔪 Multi-Format Sampling:** Intelligent sampling for CSV, SQL, and Excel files to preserve schema context while staying within token limits.
* **🌳 Project Tree Mapping:** Generates a visual folder structure so the LLM understands your workspace architecture.
* **🛡️ Defensive Processing:** Automatically detects binary files via Null-byte checks and truncates oversized text files to prevent context-window poisoning.
* **📊 Token-Aware Output:** Real-time token estimation using `tiktoken` (`o200k_base`) to ensure generated prompts fit your target LLM.
* **⚙️ Professional CLI:** Robust argument handling with support for custom ignore patterns via `.data2promptignore`.

## 🚀 Quick Start

**Installation:**
```bash
git clone https://github.com/arianmokhtariha/data2prompt.git
cd data2prompt
pip install .
```

## 🛠️ Developer Setup
Want to contribute or run the tests locally? Install the package with developer dependencies:

```bash
git clone https://github.com/arianmokhtariha/data2prompt.git
cd data2prompt
pip install -e .[dev]
```

Run the test suite:
```bash
pytest
```

## 🏗️ Engineering Standards
This repository is built with production-grade software engineering principles:
* **Strict Type Hinting (PEP 484):** Fully typed function signatures across the CLI, Parsers, and UI layers.
* **Separation of Concerns:** Modular architecture separating the Orchestrator (`main.py`), Parsers (`parsers.py`), and TUI (`ui.py`).
* **Defensive Programming:** Memory-safe file reading with size-based truncation and Null-byte binary detection to prevent context-window poisoning.
* **Automated Testing:** Core logic and CLI argument merging are validated via `pytest`.
* **Continuous Integration:** GitHub Actions automatically verify codebase integrity on every push.