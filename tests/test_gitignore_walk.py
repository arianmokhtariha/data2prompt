import tempfile
from pathlib import Path

from data2prompt.utils import ProjectScanner


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


# ---------------------------------------------------------------------------
# Directory-pattern matching and walk pruning
# ---------------------------------------------------------------------------

def test_ignore_folders_excludes_directory_contents() -> None:
    """Folder ignores compile to dir-only patterns ('venv/'); files inside the
    folder must be excluded even though pathspec dir-only patterns never match
    a bare directory name without its trailing slash."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "venv" / "lib").mkdir(parents=True)
        (root / "venv" / "lib" / "module.py").write_text("code")
        (root / "app.py").write_text("code")

        scanner = ProjectScanner(
            project_path=root,
            ignore_folders={".git", "venv"},
            ignore_files=set(),
            output_file="PROMPT.md",
            use_gitignore=False,
        )
        files = {f.relative_to(root).as_posix() for f in scanner.scan()}
        assert "app.py" in files
        assert "venv/lib/module.py" not in files


def test_gitignore_dir_only_pattern_excludes_directory() -> None:
    """A gitignore pattern with a trailing slash ('build/') must exclude the
    directory's entire subtree — this requires matching directories with a
    trailing separator, not just their bare names."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".gitignore").write_text("build/\n")
        (root / "build" / "out").mkdir(parents=True)
        (root / "build" / "out" / "artifact.txt").write_text("bin")
        (root / "main.py").write_text("code")

        files = _files(_scanner(root), root)
        assert "main.py" in files
        assert "build/out/artifact.txt" not in files


def test_gitignores_inside_ignored_dirs_are_not_collected() -> None:
    """The init-time gitignore walk must prune ignored directories: a
    node_modules tree with hundreds of package-level .gitignore files must
    contribute zero specs (and zero wasted I/O)."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "node_modules" / "pkg").mkdir(parents=True)
        (root / "node_modules" / "pkg" / ".gitignore").write_text("*.js\n")
        (root / "src").mkdir()
        (root / "src" / ".gitignore").write_text("*.log\n")

        scanner = ProjectScanner(
            project_path=root,
            ignore_folders={".git", "node_modules"},
            ignore_files=set(),
            output_file="PROMPT.md",
            use_gitignore=True,
        )
        spec_dirs = {base.relative_to(root).as_posix() for base, _ in scanner._gitignore_specs}
        assert "src" in spec_dirs
        assert all(not d.startswith("node_modules") for d in spec_dirs)


def test_generate_tree_accepts_scan_results() -> None:
    """generate_tree(files) must render exactly the scanned files — main.py
    passes the scan result so the tree and the content can never diverge."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "a.py").write_text("a")
        (root / "sub").mkdir()
        (root / "sub" / "b.csv").write_text("b")

        scanner = _scanner(root, use_gitignore=False)
        files = scanner.scan()
        tree = scanner.generate_tree(files)

        # Forward slashes on every platform — the tree strings are the
        # canonical path keys the output File Index must match exactly.
        expected = sorted(f.relative_to(root).as_posix() for f in files)
        assert tree.splitlines() == expected


# ---------------------------------------------------------------------------
# Output-file self-exclusion
# ---------------------------------------------------------------------------

def test_output_file_in_subdirectory_is_excluded() -> None:
    """'-o out/PROMPT' style outputs must be excluded at their real location."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "out").mkdir()
        (root / "out" / "PROMPT.md").write_text("generated")
        (root / "app.py").write_text("code")

        scanner = ProjectScanner(
            project_path=root,
            ignore_folders={".git"},
            ignore_files=set(),
            output_file="out/PROMPT.md",
            use_gitignore=False,
        )
        files = {f.relative_to(root).as_posix() for f in scanner.scan()}
        assert "app.py" in files
        assert "out/PROMPT.md" not in files


def test_same_basename_elsewhere_is_not_excluded() -> None:
    """A user file that merely shares the output file's basename must survive.
    The old name-based rule silently dropped every 'PROMPT.md' in the tree."""
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / "docs").mkdir()
        (root / "docs" / "PROMPT.md").write_text("# user's own doc, not generated")
        (root / "PROMPT.md").write_text("generated output")

        scanner = ProjectScanner(
            project_path=root,
            ignore_folders={".git"},
            ignore_files=set(),
            output_file="PROMPT.md",
            use_gitignore=False,
        )
        files = {f.relative_to(root).as_posix() for f in scanner.scan()}
        assert "PROMPT.md" not in files
        assert "docs/PROMPT.md" in files
