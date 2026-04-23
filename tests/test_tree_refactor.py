import os
from pathlib import Path
from src.data2prompt.utils import ProjectScanner

def test_flat_tree():
    # Create a temporary structure for testing
    test_dir = Path("temp_test_project")
    test_dir.mkdir(exist_ok=True)
    (test_dir / "subdir").mkdir(exist_ok=True)
    (test_dir / "file1.txt").touch()
    (test_dir / "subdir" / "file2.py").touch()
    (test_dir / ".gitignore").touch()

    scanner = ProjectScanner(
        project_path=test_dir,
        ignore_folders={".git"},
        ignore_files=set(),
        output_file="PROMPT.md"
    )

    tree = scanner.generate_tree()
    print("Generated Flat Tree:")
    print(tree)

    # Cleanup
    import shutil
    shutil.rmtree(test_dir)

if __name__ == "__main__":
    test_flat_tree()
