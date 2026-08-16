"""UI-level tests for DiffModeWidget: file list manipulation and diff
display, driven through the same widget methods a button click would call."""

from diff.diff_engine import DiffType
from modes.diff_mode import DiffModeWidget


def _add_files(widget, tmp_path, contents):
    """Populate the diff engine/list the way add_file() would after a
    successful QFileDialog pick (which can't be driven headlessly)."""
    paths = []
    for i, content in enumerate(contents):
        path = tmp_path / f"file{i}.txt"
        path.write_text(content)
        widget._add_file_to_engine_and_list(str(path))
        paths.append(str(path))
    widget.update_file_combos()
    widget.update_base_file_combo()
    return paths


def test_added_files_appear_in_list_and_combos(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)

    paths = _add_files(widget, tmp_path, ["one\n", "two\n"])

    assert widget.file_list_widget.count() == 2
    assert widget.file_a_combo.count() == 2
    assert widget.file_b_combo.count() == 2
    assert widget.diff_engine.get_file_names() == paths


def test_whitespace_checkbox_toggles_diff_output(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    _add_files(widget, tmp_path, ["line\n", "line \n"])  # trailing-space-only diff

    widget.highlight_whitespace_checkbox.setChecked(True)
    assert any(d.line_type != DiffType.EQUAL for d in widget.current_diff_lines)

    widget.highlight_whitespace_checkbox.setChecked(False)
    assert all(d.line_type == DiffType.EQUAL for d in widget.current_diff_lines)


def test_remove_selected_files_updates_engine_and_list(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    paths = _add_files(widget, tmp_path, ["one\n", "two\n", "three\n"])

    widget.file_list_widget.item(1).setSelected(True)
    widget.remove_selected_files()

    assert widget.file_list_widget.count() == 2
    remaining_paths = [
        widget.file_list_widget.item(i).toolTip() for i in range(widget.file_list_widget.count())
    ]
    assert paths[1] not in remaining_paths
    assert widget.diff_engine.get_file_names() == [paths[0], paths[2]]


def test_move_selected_file_up_reorders_grouping(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    paths = _add_files(widget, tmp_path, ["one\n", "two\n"])

    widget.file_list_widget.item(1).setSelected(True)
    widget.move_selected_files_up()

    assert widget.diff_engine.get_file_names() == [paths[1], paths[0]]


def test_clear_files_empties_engine_and_widgets(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    _add_files(widget, tmp_path, ["one\n"])

    widget.clear_files()  # confirmation dialog is auto-answered Yes (see root conftest)

    assert widget.file_list_widget.count() == 0
    assert widget.diff_engine.get_file_count() == 0


def test_save_and_load_grouping_history_round_trip(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    paths = _add_files(widget, tmp_path, ["one\n", "two\n"])

    widget.save_current_grouping_to_history()
    # index 0 is the "Select saved grouping..." placeholder; one real entry follows.
    assert widget.grouping_history_combo.count() == 2

    widget.clear_files()  # dialog auto-answered Yes (see root conftest)
    assert widget.diff_engine.get_file_count() == 0

    widget.grouping_history_combo.setCurrentIndex(1)
    widget.load_selected_grouping()  # dialog auto-answered Yes (see root conftest)

    # _cache_file_grouping_history stores paths sorted, not in original add order.
    assert widget.diff_engine.get_file_names() == sorted(paths)


def test_file_grouping_tab_groups_by_content_hash(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    _add_files(widget, tmp_path, ["same content\n", "same content\n", "different\n"])

    widget.update_file_groups()

    assert widget.grouping_tree.topLevelItemCount() == 2  # one duplicate pair, one unique
    group_sizes = sorted(
        widget.grouping_tree.topLevelItem(i).childCount()
        for i in range(widget.grouping_tree.topLevelItemCount())
    )
    assert group_sizes == [1, 2]
    assert "1 duplicate(s) detected." in widget.grouping_info_label.text()


def test_grouping_display_label_uses_directory_context_for_duplicate_basenames(qtbot, tmp_path):
    widget = DiffModeWidget()
    qtbot.addWidget(widget)

    path_a = tmp_path / "projA" / "config.py"
    path_b = tmp_path / "projB" / "config.py"

    short_label, full_label = widget._build_grouping_display_labels([str(path_a), str(path_b)])

    assert short_label.startswith("config.py (")
    assert "projA" in short_label
    assert "projB" in short_label
    assert "projA" in full_label
    assert "projB" in full_label


def test_save_generated_code_writes_selected_file(qtbot, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    widget.generated_code.setPlainText("def merged():\n    pass\n")

    save_path = tmp_path / "merged.py"
    monkeypatch.setattr(
        QFileDialog, "getSaveFileName", staticmethod(lambda *a, **k: (str(save_path), ""))
    )

    widget.save_generated_code()

    assert save_path.read_text() == "def merged():\n    pass\n"


def test_refresh_files_reloads_changed_content_and_drops_missing(qtbot, tmp_path):
    file_a = tmp_path / "a.txt"
    file_a.write_text("v1\n")
    file_b = tmp_path / "b.txt"
    file_b.write_text("v1\n")

    widget = DiffModeWidget()
    qtbot.addWidget(widget)
    widget._add_file_to_engine_and_list(str(file_a))
    widget._add_file_to_engine_and_list(str(file_b))
    widget.update_file_combos()
    widget.update_base_file_combo()

    file_a.write_text("v2\n")  # changed on disk after being added
    file_b.unlink()  # removed on disk

    widget.refresh_files()  # missing-file warning is auto-answered (see root conftest)

    assert widget.diff_engine.get_file_names() == [str(file_a)]
    assert widget.diff_engine.get_file_content(0) == "v2\n"
