# Parsers

The `data2prompt` project uses a modular parsing system to handle various file types, ensuring that data is extracted, sampled, and formatted appropriately for LLM context windows.

## Parser Architecture

The system relies on a `ParserRegistry` to map file extensions to specialized parser classes. All parsers implement the `BaseParser` protocol, ensuring a consistent interface.

### ParserRegistry
The `ParserRegistry` (defined in [`src/data2prompt/parsers.py`](src/data2prompt/parsers.py)) manages the mapping between file extensions and their corresponding parser implementations.

### BaseParser Protocol
All parsers must implement the `parse` method, which takes a `file_path` and a `Config` object, and returns a `ParserResult`.

```python
class BaseParser(Protocol):
    def parse(self, file_path: Path, config: 'Config') -> ParserResult:
        ...
```

## Intermediate Representation (IR)

To handle structured data (like Jupyter Notebooks and tabular data) consistently, the project uses Intermediate Representations (IR):

- **`NotebookCellIR`**: Represents a single cell in a Jupyter Notebook, including its type (code/markdown), source, and outputs.
- **`TableIR`**: Represents tabular data (CSV, Excel), including the DataFrame, header/footer notes, and metadata.

These IRs are flattened into strings for token counting and final output generation using the `flatten_ir` function.

## Parser Implementations

| Parser | Supported Extensions | Description |
| :--- | :--- | :--- |
| `CSVParser` | `.csv` | Samples rows to fit context limits. |
| `NotebookParser` | `.ipynb` | Cleans and truncates notebook cells and outputs. |
| `SQLParser` | `.sql` | Parses SQL files, sampling table data while preserving schema. |
| `ExcelParser` | `.xlsx`, `.xls` | Extracts data from sheets, detecting visual elements. |
| `DefaultParser` | All others | Fallback for text files, handles binary detection and size truncation. |
