# 📊 Data2Prompt

> **Turn your messy Data Science workspaces into clean, LLM-ready context.**

Data2Prompt is a blazing-fast CLI tool designed specifically for Data Analysts and Scientists. Unlike standard code-packagers, it intelligently parses Jupyter Notebooks, selectively samples heavy CSVs, and strips out token-wasting binary bloat, generating a perfectly structured Markdown file optimized for AI context windows (Claude, GPT-4o, Gemini).

## ✨ Features
* **🧠 Smart Jupyter Parsing:** Extracts code, markdown, and text outputs while stripping out heavy Base64 images and raw HTML tables.
* **🔪 CSV Sampling:** Automatically samples large datasets to give LLMs a "taste" of your data schema without forgetting the main distribution.
* **🌳 Project Tree Mapping:** Generates a visual folder structure so the LLM understands your workspace architecture.
* **🛡️ Binary Safe:** Automatically ignores `.pbix`, `.db`, `.zip`, and other heavy files.

## 🚀 Quick Start

**Installation:**
```bash
git clone [https://github.com/arianmokhtariha/data2prompt.git](https://github.com/arianmokhtariha/data2prompt.git)
cd data2prompt
pip install .