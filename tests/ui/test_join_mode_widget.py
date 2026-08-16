"""UI-level tests for JoinModeWidget: view toggling, sorting, and unconfirmed
grouping actions, driven through the same widget methods a button click or
combo change would call."""

from join.join import UnconfirmedGrouping
from modes.join_mode import JoinModeWidget, SortBy


def test_toggle_view_mode_switches_visible_listbox(qtbot):
    widget = JoinModeWidget()
    qtbot.addWidget(widget)

    assert widget.u_listbox.isHidden()
    assert not widget.g_listbox.isHidden()
    assert widget.unconfirmed_list_mode is False

    widget.toggle_view_mode()

    assert not widget.u_listbox.isHidden()
    assert widget.g_listbox.isHidden()
    assert widget.unconfirmed_list_mode is True


def test_sort_combo_alphanumeric_orders_groupings(qtbot):
    widget = JoinModeWidget()
    qtbot.addWidget(widget)
    widget.groupings = {"zebra": object(), "alpha": object()}

    widget.sort_combo.setCurrentText(SortBy.ALPHANUMERIC.name)

    items = [widget.g_listbox.item(i).text() for i in range(widget.g_listbox.count())]
    assert items == ["alpha", "zebra"]


def test_merge_similars_moves_entry_from_unconfirmed_to_confirmed(qtbot):
    widget = JoinModeWidget()
    qtbot.addWidget(widget)

    unconfirmed = UnconfirmedGrouping("line one", ["a.txt"], "line two", ["b.txt"], 1)
    grouping_key = unconfirmed.display_value()
    widget.unconfirmed_groupings[grouping_key] = unconfirmed
    widget.u_listbox.addItem(grouping_key)
    widget.u_listbox.item(0).setSelected(True)

    widget.merge_similars()  # success dialog is auto-answered (see root conftest)

    assert grouping_key not in widget.unconfirmed_groupings
    assert widget.g_listbox.count() == 1
    assert widget.groupings["line one"].files == ["a.txt", "b.txt"]


def test_remove_selected_deletes_unconfirmed_grouping(qtbot):
    widget = JoinModeWidget()
    qtbot.addWidget(widget)

    unconfirmed = UnconfirmedGrouping("line one", ["a.txt"], "line two", ["b.txt"], 1)
    grouping_key = unconfirmed.display_value()
    widget.unconfirmed_groupings[grouping_key] = unconfirmed
    widget.join.maybe_groupings = [unconfirmed]
    widget.u_listbox.addItem(grouping_key)
    widget.u_listbox.item(0).setSelected(True)

    widget.remove_selected()  # "all processed" dialog is auto-answered (see root conftest)

    assert grouping_key not in widget.unconfirmed_groupings
    assert widget.join.maybe_groupings == []


def test_reset_data_clears_files_and_groupings(qtbot, tmp_path):
    file_a = tmp_path / "a.txt"
    file_a.write_text("line\n")

    widget = JoinModeWidget()
    qtbot.addWidget(widget)
    widget.file_list = [str(file_a)]
    widget.update_file_list_display()
    widget.groupings = {"line": object()}
    widget.g_listbox.addItem("line")
    widget.unconfirmed_groupings = {"stray": object()}
    widget.u_listbox.addItem("stray")

    widget.reset_data()  # confirmation dialog is auto-answered Yes (see root conftest)

    assert widget.file_list == []
    assert widget.groupings == {}
    assert widget.unconfirmed_groupings == {}
    assert widget.file_list_widget.count() == 0
    assert widget.g_listbox.count() == 0
    assert widget.u_listbox.count() == 0
