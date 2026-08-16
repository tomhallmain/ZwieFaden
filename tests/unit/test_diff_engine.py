"""Unit tests for diff.diff_engine -- pure diff computation, no Qt involved.
Files are written under pytest's own tmp_path fixture, not real user data."""

import pytest

from diff.diff_engine import DiffEngine, DiffType, FileMetadata


def _make_file(tmp_path, name, content):
    path = tmp_path / name
    path.write_text(content)
    return str(path)


def test_add_file_from_disk_reads_metadata(tmp_path):
    engine = DiffEngine()
    path = _make_file(tmp_path, "a.py", "line one\nline two\n")
    engine.add_file(path)

    assert engine.get_file_count() == 1
    assert engine.get_file_names() == [path]
    assert engine.metadata[0].line_count == 2
    assert engine.metadata[0].filename == "a.py"


def test_add_file_from_content_skips_disk_read():
    engine = DiffEngine()
    engine.add_file("virtual/file.py", content="a\nb")

    assert engine.get_file_count() == 1
    assert engine.get_file_content(0) == "a\nb\n"  # trailing newline is appended


def test_compare_two_files_reports_insert_delete_equal(tmp_path):
    engine = DiffEngine()
    engine.add_file(_make_file(tmp_path, "a.txt", "common\nold\n"))
    engine.add_file(_make_file(tmp_path, "b.txt", "common\nnew\n"))

    diff_lines = engine.compare_two_files(0, 1)
    types = {d.line_type for d in diff_lines}
    assert DiffType.EQUAL in types
    assert DiffType.DELETE in types
    assert DiffType.INSERT in types


def test_compare_two_files_out_of_range_raises():
    engine = DiffEngine()
    engine.add_file("only.txt", content="x")
    with pytest.raises(IndexError):
        engine.compare_two_files(0, 1)


def test_whitespace_only_diffs_hidden_when_highlighting_disabled(tmp_path):
    engine = DiffEngine()
    engine.add_file(_make_file(tmp_path, "a.txt", "line\n"))
    engine.add_file(_make_file(tmp_path, "b.txt", "line \n"))  # trailing space only

    with_highlight = engine.compare_two_files(0, 1, highlight_whitespace_only_diffs=True)
    without_highlight = engine.compare_two_files(0, 1, highlight_whitespace_only_diffs=False)

    assert any(d.line_type != DiffType.EQUAL for d in with_highlight)
    assert all(d.line_type == DiffType.EQUAL for d in without_highlight)


def test_get_unified_diff_contains_filenames_and_changed_lines(tmp_path):
    engine = DiffEngine()
    a = _make_file(tmp_path, "a.txt", "one\n")
    b = _make_file(tmp_path, "b.txt", "two\n")
    engine.add_file(a)
    engine.add_file(b)

    unified = engine.get_unified_diff(0, 1)
    assert a in unified
    assert b in unified
    assert "-one" in unified
    assert "+two" in unified


def test_get_html_diff_returns_html_table(tmp_path):
    engine = DiffEngine()
    engine.add_file(_make_file(tmp_path, "a.txt", "one\n"))
    engine.add_file(_make_file(tmp_path, "b.txt", "two\n"))

    html = engine.get_html_diff(0, 1)
    assert "<table" in html.lower()


def test_compare_all_files_statistics(tmp_path):
    engine = DiffEngine()
    engine.add_file(_make_file(tmp_path, "a.txt", "same\nold\n"))
    engine.add_file(_make_file(tmp_path, "b.txt", "same\nnew\n"))
    engine.add_file(_make_file(tmp_path, "c.txt", "same\nold\n"))

    results = engine.compare_all_files()
    assert len(results) == 3  # 3 files -> 3 pairs

    a_vs_c = next(r for r in results if r["file_a_index"] == 0 and r["file_b_index"] == 2)
    assert a_vs_c["statistics"]["total_changes"] == 0
    assert a_vs_c["statistics"]["similarity_ratio"] == 1.0


def test_clear_files_resets_state(tmp_path):
    engine = DiffEngine()
    engine.add_file(_make_file(tmp_path, "a.txt", "x\n"))
    engine.clear_files()

    assert engine.get_file_count() == 0
    assert engine.get_file_names() == []


def test_get_diff_matrix_summary_requires_two_files():
    engine = DiffEngine()
    engine.add_file("only.txt", content="x")
    assert engine.get_diff_matrix_summary() == "Not enough files to generate diff matrix."


def test_get_diff_matrix_summary_includes_filenames(tmp_path):
    engine = DiffEngine()
    engine.add_file(_make_file(tmp_path, "a.txt", "x\n"))
    engine.add_file(_make_file(tmp_path, "b.txt", "y\n"))

    summary = engine.get_diff_matrix_summary()
    assert "a.txt" in summary
    assert "b.txt" in summary


def test_file_metadata_from_file(tmp_path):
    path = _make_file(tmp_path, "meta.txt", "one\ntwo\nthree\n")
    metadata = FileMetadata.from_file(path)

    assert metadata.line_count == 3
    assert metadata.filename == "meta.txt"

    as_dict = metadata.to_dict()
    assert as_dict["filename"] == "meta.txt"
    assert as_dict["line_count"] == 3
