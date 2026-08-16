"""Unit tests for diff.project_compare -- pure directory-scan/matching logic,
no Qt involved."""

import os

from diff.project_compare import ProjectComparator, load_gitignore_patterns


def test_scan_excludes_default_ignore_list(tmp_path):
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text("print('hi')\n")
    (project / ".git").mkdir()
    (project / ".git" / "config").write_text("git stuff\n")
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "main.cpython-312.pyc").write_bytes(b"\x00\x01")
    (project / "venv").mkdir()
    (project / "venv" / "pyvenv.cfg").write_text("x\n")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "pkg.js").write_text("x\n")

    entries = ProjectComparator().scan(str(project))

    assert set(entries.keys()) == {"src/main.py"}


def test_scan_excludes_additional_default_categories(tmp_path):
    # VCS metadata (beyond .git), build output, IDE settings, OS cruft, and
    # a standalone *.pyc outside __pycache__ -- all part of the default
    # ignore list, not something the user has to opt into.
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    (project / "src" / "main.py").write_text("print('hi')\n")

    (project / ".svn").mkdir()
    (project / ".svn" / "entries").write_text("x\n")
    (project / ".hg").mkdir()
    (project / ".hg" / "dirstate").write_text("x\n")
    (project / "dist").mkdir()
    (project / "dist" / "bundle.js").write_text("x\n")
    (project / "build").mkdir()
    (project / "build" / "output.txt").write_text("x\n")
    (project / ".idea").mkdir()
    (project / ".idea" / "workspace.xml").write_text("x\n")
    (project / ".vscode").mkdir()
    (project / ".vscode" / "settings.json").write_text("x\n")
    (project / ".DS_Store").write_text("x\n")
    (project / "stray.pyc").write_bytes(b"\x00\x01")

    entries = ProjectComparator().scan(str(project))

    assert set(entries.keys()) == {"src/main.py"}


def test_scan_can_ignore_gitignore_patterns_while_keeping_default_list(tmp_path):
    # respect_gitignore=False must skip only the .gitignore-sourced patterns
    # -- the hardcoded default list and any extra_ignore_patterns still apply.
    project = tmp_path / "project"
    project.mkdir()
    (project / "keep.py").write_text("keep\n")
    (project / "wanted.log").write_text("log\n")
    (project / "excluded.tmp").write_text("tmp\n")
    (project / ".gitignore").write_text("*.log\n")
    (project / "__pycache__").mkdir()
    (project / "__pycache__" / "x.pyc").write_bytes(b"\x00\x01")

    entries = ProjectComparator(
        extra_ignore_patterns=["*.tmp"], respect_gitignore=False
    ).scan(str(project))

    assert set(entries.keys()) == {"keep.py", "wanted.log", ".gitignore"}


def test_scan_honors_gitignore_name_pattern(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "keep.py").write_text("keep\n")
    (project / "ignored.log").write_text("log\n")
    (project / ".gitignore").write_text("*.log\n")

    entries = ProjectComparator().scan(str(project))

    assert "keep.py" in entries
    assert "ignored.log" not in entries


def test_scan_honors_extra_ignore_patterns(tmp_path):
    # Covers the global exclusion list (ProjectCompareTab), which is passed
    # through to ProjectComparator as extra_ignore_patterns -- independent
    # of any single project's own .gitignore.
    project = tmp_path / "project"
    project.mkdir()
    (project / "keep.py").write_text("keep\n")
    (project / "notes.tmp").write_text("scratch\n")

    entries = ProjectComparator(extra_ignore_patterns=["*.tmp"]).scan(str(project))

    assert "keep.py" in entries
    assert "notes.tmp" not in entries


def test_scan_honors_gitignore_directory_pattern(tmp_path):
    project = tmp_path / "project"
    (project / "build").mkdir(parents=True)
    (project / "build" / "output.txt").write_text("built\n")
    (project / "src").mkdir()
    (project / "src" / "main.py").write_text("main\n")
    (project / ".gitignore").write_text("build/\n")

    entries = ProjectComparator().scan(str(project))

    assert "src/main.py" in entries
    assert not any(path.startswith("build/") for path in entries)


def test_scan_honors_anchored_gitignore_pattern(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "config.py").write_text("root config\n")
    (project / "sub").mkdir()
    (project / "sub" / "config.py").write_text("sub config\n")
    (project / ".gitignore").write_text("/config.py\n")

    entries = ProjectComparator().scan(str(project))

    assert "config.py" not in entries
    assert "sub/config.py" in entries


def test_scan_does_not_follow_symlinked_files(tmp_path, monkeypatch):
    # os.symlink requires elevated privileges on some platforms (notably
    # Windows without developer mode), so the skip is verified by faking
    # os.path.islink rather than creating a real symlink.
    project = tmp_path / "project"
    project.mkdir()
    (project / "real.txt").write_text("real\n")
    link_path = project / "link.txt"
    link_path.write_text("placeholder\n")

    original_islink = os.path.islink

    def fake_islink(path):
        if os.path.abspath(str(path)) == os.path.abspath(str(link_path)):
            return True
        return original_islink(path)

    monkeypatch.setattr(os.path, "islink", fake_islink)

    entries = ProjectComparator().scan(str(project))

    assert "real.txt" in entries
    assert "link.txt" not in entries


def test_scan_does_not_descend_into_symlinked_directories(tmp_path, monkeypatch):
    project = tmp_path / "project"
    project.mkdir()
    (project / "real_dir").mkdir()
    (project / "real_dir" / "file.txt").write_text("real\n")
    linked_dir = project / "linked_dir"
    linked_dir.mkdir()
    (linked_dir / "file.txt").write_text("via symlink\n")

    original_islink = os.path.islink

    def fake_islink(path):
        if os.path.abspath(str(path)) == os.path.abspath(str(linked_dir)):
            return True
        return original_islink(path)

    monkeypatch.setattr(os.path, "islink", fake_islink)

    entries = ProjectComparator().scan(str(project))

    assert "real_dir/file.txt" in entries
    assert not any(path.startswith("linked_dir/") for path in entries)


def test_scan_flags_binary_files_via_null_byte_heuristic(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "text.txt").write_text("just text\n")
    (project / "binary.dat").write_bytes(b"\x00\x01\x02binary")

    entries = ProjectComparator().scan(str(project))

    assert entries["text.txt"].is_binary is False
    assert entries["binary.dat"].is_binary is True


def test_compare_categorizes_files_correctly(tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()

    (project_a / "same.txt").write_text("identical content\n")
    (project_b / "same.txt").write_text("identical content\n")

    (project_a / "changed.txt").write_text("version a\n")
    (project_b / "changed.txt").write_text("version b\n")

    (project_a / "only_a.txt").write_text("only in a\n")
    (project_b / "only_b.txt").write_text("only in b\n")

    result = ProjectComparator().compare(str(project_a), str(project_b))

    assert result.identical == ["same.txt"]
    assert result.different == ["changed.txt"]
    assert result.only_in_a == ["only_a.txt"]
    assert result.only_in_b == ["only_b.txt"]


def test_get_absolute_paths_returns_pair_for_shared_file(tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "shared.txt").write_text("a\n")
    (project_b / "shared.txt").write_text("b\n")

    result = ProjectComparator().compare(str(project_a), str(project_b))
    paths = result.get_absolute_paths("shared.txt")

    assert paths == (str(project_a / "shared.txt"), str(project_b / "shared.txt"))


def test_get_absolute_paths_returns_none_for_missing_relative_path(tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()

    result = ProjectComparator().compare(str(project_a), str(project_b))

    assert result.get_absolute_paths("nonexistent.txt") is None


def test_load_gitignore_patterns_skips_comments_and_blank_lines(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / ".gitignore").write_text("# comment\n\n*.log\nbuild/\n")

    patterns = load_gitignore_patterns(str(project))

    assert patterns == ["*.log", "build"]


def test_load_gitignore_patterns_returns_empty_list_without_gitignore(tmp_path):
    project = tmp_path / "project"
    project.mkdir()

    assert load_gitignore_patterns(str(project)) == []
