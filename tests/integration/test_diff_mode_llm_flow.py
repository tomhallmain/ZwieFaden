"""Integration test for DiffModeWidget's LLM Analysis flow: real DiffEngine +
DiffLLMAnalyzer + the widget's actual QThread worker, wired together the way
the app uses them. Only extensions.llm.LLM.generate_response is mocked, so
this exercises real prompt-building, real cross-thread signal delivery, and
real app_info_cache persistence of the request/response history."""

from extensions.llm import LLM, LLMResult
from modes.diff_mode import DiffModeWidget
from utils.app_info_cache import app_info_cache


def _fake_llm_result(response_text):
    return LLMResult(
        response=response_text,
        context=None,
        context_provided=False,
        created_at="",
        done=True,
        done_reason="stop",
        total_duration=0,
        load_duration=0,
        prompt_eval_count=0,
        prompt_eval_duration=0,
        eval_count=0,
        eval_duration=0,
    )


def test_run_llm_analysis_populates_results_and_caches_history(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        LLM, "generate_response",
        lambda self, query, **kwargs: _fake_llm_result("File 1 is the most up-to-date version."),
    )

    widget = DiffModeWidget()
    qtbot.addWidget(widget)

    file_a = tmp_path / "a.py"
    file_a.write_text("def foo():\n    pass\n")
    file_b = tmp_path / "b.py"
    file_b.write_text("def foo():\n    return 1\n")

    # Bypass QFileDialog (can't be driven headlessly) and populate the diff
    # engine the way add_file() would after a successful file pick.
    widget._add_file_to_engine_and_list(str(file_a))
    widget._add_file_to_engine_and_list(str(file_b))
    widget.update_file_combos()
    widget.update_base_file_combo()

    widget.run_llm_analysis()
    qtbot.waitUntil(lambda: widget.llm_analysis_worker is None, timeout=5000)

    assert widget.analysis_status_label.text() == "✅ Complete"
    assert "up-to-date" in widget.analysis_results.toPlainText()

    history = app_info_cache.get("diff_mode_llm_history", {})
    assert len(history) == 1
    entry = next(iter(history.values()))
    assert entry["request_type"] == "analysis"
    assert entry["file_paths"] == [str(file_a), str(file_b)]


def test_run_llm_analysis_surfaces_llm_failure(qtbot, tmp_path, monkeypatch):
    from extensions.llm import LLMResponseException

    def _raise(self, query, **kwargs):
        raise LLMResponseException("ollama unreachable")

    monkeypatch.setattr(LLM, "generate_response", _raise)

    widget = DiffModeWidget()
    qtbot.addWidget(widget)

    file_a = tmp_path / "a.py"
    file_a.write_text("one\n")
    file_b = tmp_path / "b.py"
    file_b.write_text("two\n")
    widget._add_file_to_engine_and_list(str(file_a))
    widget._add_file_to_engine_and_list(str(file_b))
    widget.update_file_combos()
    widget.update_base_file_combo()

    widget.run_llm_analysis()
    qtbot.waitUntil(lambda: widget.llm_analysis_worker is None, timeout=5000)

    assert widget.analysis_status_label.text() == "❌ Error"
    assert "ollama unreachable" in widget.analysis_results.toPlainText()


def test_generate_merged_version_populates_code_and_caches_history(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        LLM, "generate_response",
        lambda self, query, **kwargs: _fake_llm_result(
            "Here you go:\n```python\ndef merged():\n    pass\n```"
        ),
    )

    widget = DiffModeWidget()
    qtbot.addWidget(widget)

    file_a = tmp_path / "a.py"
    file_a.write_text("def foo():\n    pass\n")
    widget._add_file_to_engine_and_list(str(file_a))
    widget.update_file_combos()
    widget.update_base_file_combo()
    widget.target_context_input.setPlainText("a cli tool")

    widget.generate_merged_version()
    qtbot.waitUntil(lambda: widget.llm_generation_worker is None, timeout=5000)

    assert widget.code_status_label.text() == "✅ Complete"
    assert "def merged" in widget.generated_code.toPlainText()

    history = app_info_cache.get("diff_mode_llm_history", {})
    assert len(history) == 1
    entry = next(iter(history.values()))
    assert entry["request_type"] == "generation"


def test_request_history_restore_and_delete(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        LLM, "generate_response",
        lambda self, query, **kwargs: _fake_llm_result("File 1 is the most up-to-date version."),
    )

    widget = DiffModeWidget()
    qtbot.addWidget(widget)

    file_a = tmp_path / "a.py"
    file_a.write_text("def foo():\n    pass\n")
    file_b = tmp_path / "b.py"
    file_b.write_text("def foo():\n    return 1\n")
    widget._add_file_to_engine_and_list(str(file_a))
    widget._add_file_to_engine_and_list(str(file_b))
    widget.update_file_combos()
    widget.update_base_file_combo()

    widget.run_llm_analysis()
    qtbot.waitUntil(lambda: widget.llm_analysis_worker is None, timeout=5000)

    widget.update_request_history()
    assert widget.history_list_widget.count() == 1

    # Clear the current files, then restore the cached request from history.
    widget.clear_files()  # dialog auto-answered Yes (see root conftest)
    assert widget.diff_engine.get_file_count() == 0

    entry_item = widget.history_list_widget.item(0)
    entry_item.setSelected(True)
    widget.restore_history_entry(entry_item)  # confirmation dialog auto-answered Yes

    assert sorted(widget.diff_engine.get_file_names()) == sorted([str(file_a), str(file_b)])
    assert widget.analysis_status_label.text() == "✅ Complete (cached)"

    widget.delete_selected_history_entry()  # confirmation dialog auto-answered Yes

    assert app_info_cache.get("diff_mode_llm_history", {}) == {}
