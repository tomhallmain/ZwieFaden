"""Integration tests for MainWindow's "remember last used mode" behavior --
app.py's actual described feature (see README.md), backed by app_info_cache.
Not a test of app_info_cache's mechanics in isolation."""

from app import MainWindow
from utils.constants import AppMode


def test_default_mode_is_diff_when_nothing_cached(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.stacked_widget.currentIndex() == int(AppMode.DIFF)
    assert window.diff_mode_btn.isChecked()
    assert not window.join_mode_btn.isChecked()


def test_switching_mode_persists_across_new_window_instances(qtbot):
    first_window = MainWindow()
    qtbot.addWidget(first_window)

    first_window.switch_mode(AppMode.JOIN)
    assert first_window.stacked_widget.currentIndex() == int(AppMode.JOIN)

    # Simulate the app restarting: a fresh MainWindow should pick up the
    # mode cached by switch_mode() above via the isolated app_info_cache.
    second_window = MainWindow()
    qtbot.addWidget(second_window)

    assert second_window.stacked_widget.currentIndex() == int(AppMode.JOIN)
    assert second_window.join_mode_btn.isChecked()
    assert not second_window.diff_mode_btn.isChecked()
