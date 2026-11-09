"""Integration test for the Project Compare tab: the real ProjectComparator
running in its actual QThread worker, wired the way ProjectCompareTab uses
it, plus the handoff into DiffModeWidget's Diff View tab."""

from modes.diff_mode import DiffModeWidget
from modes.project_compare_widget import ProjectCompareTab
from utils.translations import _


def test_start_comparison_populates_tree_and_summary(qtbot, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "same.txt").write_text("same\n")
    (project_b / "same.txt").write_text("same\n")
    (project_a / "changed.txt").write_text("v1\n")
    (project_b / "changed.txt").write_text("v2\n")
    (project_a / "only_a.txt").write_text("only a\n")

    opened_pairs = []
    tab = ProjectCompareTab(lambda a, b: opened_pairs.append((a, b)))
    qtbot.addWidget(tab)

    tab.project_a_input.setText(str(project_a))
    tab.project_b_input.setText(str(project_b))
    tab.start_comparison()
    qtbot.waitUntil(lambda: tab.worker is None, timeout=5000)

    assert tab.summary_label.text() == _(
        "{0} identical, {1} different, {2} only in Project A, {3} only in Project B."
    ).format(1, 1, 1, 0)
    assert tab.result_tree.topLevelItemCount() == 4  # always all 4 categories


def test_global_exclusions_are_applied_by_the_worker_thread(qtbot, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "keep.py").write_text("v1\n")
    (project_b / "keep.py").write_text("v2\n")
    (project_a / "ignored.tmp").write_text("v1\n")
    (project_b / "ignored.tmp").write_text("v2\n")

    tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(tab)

    tab.global_exclusion_input.setText("*.tmp")
    tab._add_global_exclusion()

    tab.project_a_input.setText(str(project_a))
    tab.project_b_input.setText(str(project_b))
    tab.start_comparison()
    qtbot.waitUntil(lambda: tab.worker is None, timeout=5000)

    different_group = tab.result_tree.topLevelItem(0)  # "Different"
    entries = [different_group.child(i).text(0) for i in range(different_group.childCount())]
    assert entries == ["keep.py"]


def test_unchecking_respect_gitignore_surfaces_gitignored_differences(qtbot, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / ".gitignore").write_text("secret.env\n")
    (project_b / ".gitignore").write_text("secret.env\n")
    (project_a / "secret.env").write_text("A=1\n")
    (project_b / "secret.env").write_text("A=2\n")

    tab = ProjectCompareTab(lambda a, b: None)
    qtbot.addWidget(tab)
    tab.project_a_input.setText(str(project_a))
    tab.project_b_input.setText(str(project_b))

    # Respected by default: the gitignored file never shows up.
    tab.start_comparison()
    qtbot.waitUntil(lambda: tab.worker is None, timeout=5000)
    different_group = tab.result_tree.topLevelItem(0)
    assert different_group.childCount() == 0

    # Toggled off: the same file now surfaces as a difference.
    tab.respect_gitignore_checkbox.setChecked(False)
    tab.start_comparison()
    qtbot.waitUntil(lambda: tab.worker is None, timeout=5000)
    different_group = tab.result_tree.topLevelItem(0)
    entries = [different_group.child(i).text(0) for i in range(different_group.childCount())]
    assert entries == ["secret.env"]


def test_double_clicking_a_different_entry_invokes_callback(qtbot, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "changed.txt").write_text("v1\n")
    (project_b / "changed.txt").write_text("v2\n")

    opened_pairs = []
    tab = ProjectCompareTab(lambda a, b: opened_pairs.append((a, b)))
    qtbot.addWidget(tab)

    tab.project_a_input.setText(str(project_a))
    tab.project_b_input.setText(str(project_b))
    tab.start_comparison()
    qtbot.waitUntil(lambda: tab.worker is None, timeout=5000)

    different_group = tab.result_tree.topLevelItem(0)  # "Different" is added first
    assert different_group.childCount() == 1
    entry_item = different_group.child(0)

    tab._on_item_double_clicked(entry_item, 0)

    assert opened_pairs == [(str(project_a / "changed.txt"), str(project_b / "changed.txt"))]


def test_opening_a_binary_pair_shows_warning_instead_of_callback(qtbot, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "image.bin").write_bytes(b"\x00\x01v1")
    (project_b / "image.bin").write_bytes(b"\x00\x01v2")

    opened_pairs = []
    tab = ProjectCompareTab(lambda a, b: opened_pairs.append((a, b)))
    qtbot.addWidget(tab)

    tab.project_a_input.setText(str(project_a))
    tab.project_b_input.setText(str(project_b))
    tab.start_comparison()
    qtbot.waitUntil(lambda: tab.worker is None, timeout=5000)

    different_group = tab.result_tree.topLevelItem(0)
    entry_item = different_group.child(0)
    tab._on_item_double_clicked(entry_item, 0)  # binary warning is auto-answered (see root conftest)

    assert opened_pairs == []


def test_project_compare_tab_hands_off_to_diff_view(qtbot, tmp_path):
    project_a = tmp_path / "a"
    project_b = tmp_path / "b"
    project_a.mkdir()
    project_b.mkdir()
    (project_a / "changed.txt").write_text("v1\n")
    (project_b / "changed.txt").write_text("v2\n")

    widget = DiffModeWidget()
    qtbot.addWidget(widget)

    compare_tab = widget.project_compare_tab
    compare_tab.project_a_input.setText(str(project_a))
    compare_tab.project_b_input.setText(str(project_b))
    compare_tab.start_comparison()
    qtbot.waitUntil(lambda: compare_tab.worker is None, timeout=5000)

    different_group = compare_tab.result_tree.topLevelItem(0)
    entry_item = different_group.child(0)
    compare_tab._on_item_double_clicked(entry_item, 0)

    assert widget.tabs.currentIndex() == widget.diff_view_tab_index
    assert sorted(widget.diff_engine.get_file_names()) == sorted(
        [str(project_a / "changed.txt"), str(project_b / "changed.txt")]
    )
