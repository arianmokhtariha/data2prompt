# Output Generation

The `data2prompt` project supports multiple output formats to ensure compatibility with various LLM context window requirements. The generation logic is implemented using the **Strategy Pattern**, allowing for easy extension to new formats.

## OutputGenerator Strategy

The `OutputGenerator` (defined in [`src/data2prompt/output.py`](src/data2prompt/output.py)) is an abstract base class that defines the interface for all output generation strategies.

```python
class OutputGenerator(ABC):
    @abstractmethod
    def generate(self, ...) -> str:
        pass
```

## Supported Formats

The project currently supports two primary output formats:

### 1. Markdown (`MarkdownGenerator`)
Generates a structured Markdown document, ideal for human readability and LLM context windows that prefer Markdown formatting. It includes:
- Project metadata and generation timestamp.
- Directory structure in a code block.
- File contents, with appropriate language-specific code blocks.
- Special handling for Jupyter Notebooks and tabular data (CSV/Excel).

### 2. XML (`XMLGenerator`)
Generates a structured XML document, ideal for LLM context windows that benefit from explicit tagging and hierarchical data representation. It includes:
- Project metadata within `<metadata>` tags.
- Directory structure within `<directory_structure>` tags.
- File contents within `<file>` tags, with nested tags for structured data (e.g., `<cell>`, `<sheet>`).

## Dynamic Wrapping

To ensure that file contents are clearly delimited within the generated output, the project uses a dynamic wrapping mechanism (via `get_dynamic_wrapper` in [`src/data2prompt/utils.py`](src/data2prompt/utils.py)). This automatically selects appropriate code block delimiters based on the content, preventing issues with nested code blocks.
