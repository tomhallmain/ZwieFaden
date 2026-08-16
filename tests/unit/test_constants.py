"""Unit tests for utils.constants.AppMode.get() -- the lookup MainWindow
uses to resolve a cached last-mode value back into an AppMode on startup."""

from utils.constants import AppMode


def test_get_resolves_int_value():
    assert AppMode.get(0) == AppMode.JOIN
    assert AppMode.get(1) == AppMode.DIFF


def test_get_resolves_name_string():
    assert AppMode.get("JOIN") == AppMode.JOIN
    assert AppMode.get("DIFF") == AppMode.DIFF


def test_get_falls_back_to_diff_by_default_on_invalid_value():
    assert AppMode.get(99) == AppMode.DIFF
    assert AppMode.get("NOT_A_MODE") == AppMode.DIFF


def test_get_falls_back_to_explicit_default_on_invalid_value():
    assert AppMode.get(99, default=AppMode.JOIN) == AppMode.JOIN
