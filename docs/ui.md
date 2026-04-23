# User Interface (UI)

The `data2prompt` project utilizes a sophisticated Terminal User Interface (TUI) built with the [`rich`](https://github.com/Textualize/rich) library to provide real-time feedback and a professional, tech-focused experience.

## UIHandler

All terminal interactions are encapsulated within the `UIHandler` class in [`src/data2prompt/ui.py`](src/data2prompt/ui.py). This ensures a consistent aesthetic and centralized control over terminal output.

### Key Features

- **Matrix Startup Animation**: A tech-focused decryption animation using random binary/hex characters and gradient colors.
- **Stable Progress Tracking**: A two-line, hacker-style progress bar that provides real-time feedback during file scanning and processing.
- **Interactive Summary Table**: On Windows, the final report includes an interactive, scrollable table of processed files, allowing users to navigate through large scan results.
- **Visual Feedback**: Styled panels, spinners, and color-coded status indicators for errors, warnings, and success messages.

## Interactive Loop (Windows)

The interactive summary table uses `msvcrt` for non-blocking input handling on Windows.

- **Alternate Buffer**: The TUI uses `Live(screen=True)` to render the interactive summary in the terminal's alternate buffer, preventing layout fragmentation and "ghosting" during terminal resizes.
- **Dynamic Viewport**: The viewport height is calculated dynamically based on the current terminal size, ensuring the scan list fits within the available space.
- **History Preservation**: A `finally` block ensures that the final state of the scan summary is printed to the standard buffer upon exit, preserving it in the terminal history.

## Static Fallback

For non-Windows environments or non-TTY terminals, the TUI provides a static fallback that prints the final report and scan list directly to the standard output, ensuring compatibility across different platforms.
