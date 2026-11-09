"""UI-level tests for ProjectCompareTab: directory selection caching and
open-pair button state, without running the comparison worker thread."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFileDialog, QTreeWidgetItem

from modes.project_compare_widget import ProjectCompareTab
from utils.app_info_cache import app_info_cache


def test_choosing_a_directory_caches_it_for_next_instance(qtbot, tmp_path, monkeypatch):
    project_a = tmp_path / "a"
    project_a.mkdir()

    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", staticmethod(lambda *a, **k: str(project_a))
    )

    tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(tab)
    tab._choose_directory(tab.project_a_input)

    assert tab.project_a_input.text() == str(project_a)
    assert app_info_cache.get(ProjectCompareTab.PROJECT_A_CACHE_KEY, "") == str(project_a)

    # A fresh tab instance should pick up the cached directory.
    other_tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(other_tab)
    assert other_tab.project_a_input.text() == str(project_a)


def test_open_pair_button_enabled_only_for_different_category(qtbot):
    tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(tab)

    different_group = QTreeWidgetItem(tab.result_tree, ["Different (1)"])
    different_item = QTreeWidgetItem(different_group, ["changed.txt"])
    different_item.setData(0, Qt.UserRole, ("different", "changed.txt"))

    identical_group = QTreeWidgetItem(tab.result_tree, ["Identical (1)"])
    identical_item = QTreeWidgetItem(identical_group, ["same.txt"])
    identical_item.setData(0, Qt.UserRole, ("identical", "same.txt"))

    different_item.setSelected(True)
    tab._update_open_pair_button_state()
    assert tab.open_pair_button.isEnabled()

    different_item.setSelected(False)
    identical_item.setSelected(True)
    tab._update_open_pair_button_state()
    assert not tab.open_pair_button.isEnabled()


def test_start_comparison_warns_when_directories_missing(qtbot):
    tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(tab)

    tab.start_comparison()  # warning dialog is auto-answered (see root conftest)

    assert tab.worker is None


def test_global_exclusion_add_remove_and_persist_round_trip(qtbot):
    tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(tab)

    tab.global_exclusion_input.setText("*.tmp")
    tab._add_global_exclusion()

    assert tab._current_global_exclusions() == ["*.tmp"]
    assert app_info_cache.get(ProjectCompareTab.GLOBAL_EXCLUSIONS_CACHE_KEY, []) == ["*.tmp"]
    assert tab.global_exclusion_input.text() == ""  # input is cleared after adding

    # A trailing slash is normalized away, matching .gitignore directory patterns.
    tab.global_exclusion_input.setText("build/")
    tab._add_global_exclusion()
    assert tab._current_global_exclusions() == ["*.tmp", "build"]

    # Adding the same pattern again is a no-op, not a duplicate.
    tab.global_exclusion_input.setText("*.tmp")
    tab._add_global_exclusion()
    assert tab._current_global_exclusions() == ["*.tmp", "build"]

    # A fresh tab instance should pick up the cached exclusions.
    other_tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(other_tab)
    assert other_tab._current_global_exclusions() == ["*.tmp", "build"]

    other_tab.global_exclusions_list.item(0).setSelected(True)
    other_tab._remove_selected_global_exclusions()

    assert other_tab._current_global_exclusions() == ["build"]
    assert app_info_cache.get(ProjectCompareTab.GLOBAL_EXCLUSIONS_CACHE_KEY, []) == ["build"]


def test_respect_gitignore_defaults_on_and_persists_when_toggled_off(qtbot):
    tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(tab)

    assert tab.respect_gitignore_checkbox.isChecked()
    assert app_info_cache.get(ProjectCompareTab.RESPECT_GITIGNORE_CACHE_KEY, True) is True

    tab.respect_gitignore_checkbox.setChecked(False)

    assert app_info_cache.get(ProjectCompareTab.RESPECT_GITIGNORE_CACHE_KEY, True) is False

    # A fresh tab instance should pick up the cached (off) state.
    other_tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(other_tab)
    assert not other_tab.respect_gitignore_checkbox.isChecked()
