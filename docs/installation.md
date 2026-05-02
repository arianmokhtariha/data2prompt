# Installation

`data2prompt` is a high-performance Python utility designed to bridge the gap between local codebases and Large Language Model context windows.

## Prerequisites

- **Python**: Version 3.10 or higher is required.
- **Package Manager**: `pip` (included with Python).

## User Installation

To install `data2prompt` directly from the source repository:

### Windows
1.  Clone the repository:
    ```bash
    git clone https://github.com/arianmokhtariha/data2prompt.git
    cd data2prompt
    ```

2.  Install the package:
    ```bash
    # Normal installation
    pip install .

    # Or install in editable mode for more control
    pip install -e .
    
    # Use pipx instead of pip for better virtual environment handling 
    ```

### Linux/macOS
1.  Clone the repository:
    ```bash
    git clone https://github.com/arianmokhtariha/data2prompt.git
    cd data2prompt
    ```

2.  Install using `pipx` for easier virtual environment handling:
    ```bash
    pipx install -e .
    ```

## Developer Setup

For developers contributing to the project, follow these steps to set up the development environment:

1.  Clone the repository:
    ```bash
    git clone https://github.com/arianmokhtariha/data2prompt.git
    cd data2prompt
    ```

2.  Create a virtual environment (recommended):
    ```bash
    python -m venv venv
    # On Windows:
    .\venv\Scripts\activate
    # On macOS/Linux:
    source venv/bin/activate
    ```

3.  Install dependencies and development tools:
    ```bash
    pip install -e .[dev]
    ```

4.  Run tests to verify the installation:
    ```bash
    pytest
    ```

## Dependencies

`data2prompt` relies on the following core libraries:

- `pandas`: Data manipulation and analysis.
- `openpyxl`: Excel file support.
- `tabulate`: Table formatting.
- `rich`: Terminal UI components.
- `tiktoken`: Tokenization for LLM context management.
- `regex`: Advanced regular expression support and offline tokenization.
