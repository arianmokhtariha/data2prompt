import tempfile
from pathlib import Path

from src.data2prompt.utils import ProjectScanner


def _scanner(project_path: Path, use_gitignore: bool = True) -> ProjectScanner:
    return ProjectScanner(
        project_path=project_path,
        ignore_folders={".git"},
        ignore_files=set(),
        output_file="PROMPT.md",
        use_gitignore=use_gitignore,
    )


def _files(scanner: ProjectScanner, root: Path) -> set[str]:
    """Return POSIX-relative paths for platform-independent assertions."""
    return {f.relative_to(root).as_posix() for f in scanner.scan()}


def test_root_gitignore_applies_to_entire_tree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gitignore").write_text("*.log\n")
        (root / "app.py").write_text("code")
        (root / "app.log").write_text("log")
        (root / "sub").mkdir()
        (root / "sub" / "sub.log").write_text("sub log")

        files = _files(_scanner(root), root)
        assert "app.py" in files
        assert "app.log" not in files
        assert "sub/sub.log" not in files


def test_subdir_gitignore_scoped_to_its_directory() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sub").mkdir()
        (root / "sub" / ".gitignore").write_text("*.log\n")
        (root / "sub" / "sub.log").write_text("log")
        (root / "root.log").write_text("log")

        files = _files(_scanner(root), root)
        assert "root.log" in files
        assert "sub/sub.log" not in files


def test_subdir_gitignore_does_not_affect_sibling_dirs() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a").mkdir()
        (root / "b").mkdir()
        (root / "a" / ".gitignore").write_text("*.log\n")
        (root / "a" / "a.log").write_text("log")
        (root / "b" / "b.log").write_text("log")

        files = _files(_scanner(root), root)
        assert "a/a.log" not in files
        assert "b/b.log" in files


def test_nested_gitignore_at_deep_path() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        deep = root / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (deep / ".gitignore").write_text("secret.txt\n")
        (deep / "secret.txt").write_text("secret")
        (deep / "public.txt").write_text("public")
        (root / "secret.txt").write_text("root secret")

        files = _files(_scanner(root), root)
        assert "secret.txt" in files
        assert "a/b/c/public.txt" in files
        assert "a/b/c/secret.txt" not in files


def test_no_gitignore_flag_disables_all_gitignore_loading() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gitignore").write_text("*.log\n")
        (root / "sub").mkdir()
        (root / "sub" / ".gitignore").write_text("*.tmp\n")
        (root / "app.log").write_text("log")
        (root / "sub" / "file.tmp").write_text("tmp")

        files = _files(_scanner(root, use_gitignore=False), root)
        assert "app.log" in files
        assert "sub/file.tmp" in files


def test_gitignore_applies_recursively_within_its_subtree() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "sub" / "deep").mkdir(parents=True)
        (root / "sub" / ".gitignore").write_text("*.csv\n")
        (root / "sub" / "data.csv").write_text("csv")
        (root / "sub" / "deep" / "nested.csv").write_text("csv")
        (root / "top.csv").write_text("csv")

        files = _files(_scanner(root), root)
        assert "top.csv" in files
        assert "sub/data.csv" not in files
        assert "sub/deep/nested.csv" not in files
