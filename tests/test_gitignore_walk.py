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


# ---------------------------------------------------------------------------
# generate_tree — contract tests
# ---------------------------------------------------------------------------

def test_generate_tree_includes_all_discovered_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.py").write_text("code")
        (root / "b.csv").write_text("data")
        (root / "sub").mkdir()
        (root / "sub" / "c.txt").write_text("text")

        tree = _scanner(root, use_gitignore=False).generate_tree()

        assert "a.py" in tree
        assert "b.csv" in tree
        assert "c.txt" in tree


def test_generate_tree_excludes_gitignored_files() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gitignore").write_text("*.log\n")
        (root / "code.py").write_text("code")
        (root / "debug.log").write_text("log")

        tree = _scanner(root).generate_tree()

        assert "code.py" in tree
        assert "debug.log" not in tree


def test_generate_tree_is_sorted() -> None:
    """generate_tree returns paths in sorted order so diffs are stable."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "z_last.py").write_text("z")
        (root / "a_first.py").write_text("a")
        (root / "m_middle.py").write_text("m")

        tree = _scanner(root, use_gitignore=False).generate_tree()
        lines = tree.splitlines()

        assert lines == sorted(lines)


def test_generate_tree_excludes_output_file() -> None:
    """The configured output file must not appear in the tree."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "PROMPT.md").write_text("output")
        (root / "source.py").write_text("code")

        scanner = ProjectScanner(
            project_path=root,
            ignore_folders={".git"},
            ignore_files=set(),
            output_file="PROMPT.md",
            use_gitignore=False,
        )
        tree = scanner.generate_tree()

        assert "source.py" in tree
        assert "PROMPT.md" not in tree
