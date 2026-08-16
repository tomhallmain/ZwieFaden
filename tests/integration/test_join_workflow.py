"""Integration test for JoinModeWidget's join analysis flow: the real
JoinMulti engine running in its actual QThread worker, wired the way the
app uses it (JoinWorker -> JoinMulti -> Grouping/UnconfirmedGrouping)."""

from modes.join_mode import JoinModeWidget


def test_do_join_populates_confirmed_grouping_from_real_files(qtbot, tmp_path):
    file_a = tmp_path / "modlist_a.txt"
    file_a.write_text("Shared Entry\nOnly In A\n")
    file_b = tmp_path / "modlist_b.txt"
    file_b.write_text("shared entry\nOnly In B\n")

    widget = JoinModeWidget()
    qtbot.addWidget(widget)

    # Bypass QFileDialog (can't be driven headlessly) and populate the file
    # list the way add_file() would after a successful multi-file pick.
    widget.file_list = [str(file_a), str(file_b)]

    widget.do_join()
    qtbot.waitUntil(lambda: widget.g_listbox.count() > 0, timeout=5000)

    # JoinWorker uses clean_filename() as the file_path_op, which strips the
    # "modlist_" prefix and ".txt" suffix from each basename.
    assert "shared entry" in widget.groupings
    assert widget.groupings["shared entry"].files == ["a", "b"]
