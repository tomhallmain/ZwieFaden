"""Unit tests for diff.llm_analyzer -- prompt building and response parsing.

Never talks to a real Ollama server: extensions.llm.LLM.generate_response is
monkeypatched everywhere a network call would otherwise happen (the root
conftest also blocks urlopen outright as a safety net).
"""

from diff.diff_engine import DiffEngine
from diff.llm_analyzer import DiffLLMAnalyzer
from extensions.llm import LLM, LLMResponseException, LLMResult


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


def _diff_matrix(files_content):
    engine = DiffEngine()
    for i, content in enumerate(files_content):
        engine.add_file(f"file{i}.py", content=content)
    return engine.compare_all_files()


def _file_metadata(names):
    return [
        {
            "filename": name,
            "filepath": name,
            "directory_context": ".",
            "modification_time": "2026-01-01 00:00:00",
            "size": 1,
            "line_count": 1,
        }
        for name in names
    ]


def test_detect_identical_files_groups_matching_content():
    analyzer = DiffLLMAnalyzer()
    groups = analyzer._detect_identical_files(["same", "same", "different"])

    assert groups[0] == {0, 1}
    assert groups[1] == {0, 1}
    assert groups[2] == {2}


def test_get_unique_file_indices_keeps_one_representative_per_group():
    analyzer = DiffLLMAnalyzer()
    unique = analyzer._get_unique_file_indices(["same", "same", "different"])

    assert unique == [0, 2]


def test_extract_recommendation_finds_1_based_file_reference():
    analyzer = DiffLLMAnalyzer()
    recommendation = analyzer._extract_recommendation("File 2 is the most up to date.", num_files=3)

    assert recommendation["recommended_file_index"] == 1  # 1-based "File 2" -> index 1


def test_extract_recommendation_returns_none_index_when_nothing_matches():
    analyzer = DiffLLMAnalyzer()
    recommendation = analyzer._extract_recommendation("No file reference here.", num_files=3)

    assert recommendation["recommended_file_index"] is None


def test_extract_code_prefers_largest_code_block():
    analyzer = DiffLLMAnalyzer()
    response = (
        "Explanation.\n```python\nsmall\n```\n"
        "More text.\n```python\ndef bigger():\n    pass\n```"
    )

    code = analyzer._extract_code(response)

    assert "def bigger" in code
    assert "small" not in code


def test_extract_code_falls_back_to_whole_response_without_code_blocks():
    analyzer = DiffLLMAnalyzer()
    response = "Just plain prose, no code fences."

    assert analyzer._extract_code(response) == response


def test_analyze_versions_returns_recommendation_on_success(monkeypatch):
    analyzer = DiffLLMAnalyzer()
    monkeypatch.setattr(
        LLM, "generate_response",
        lambda self, query, **kwargs: _fake_llm_result("File 1 is best."),
    )

    files_content = ["version one", "version two"]
    file_metadata = _file_metadata(["a.py", "b.py"])
    diff_matrix = _diff_matrix(files_content)

    result = analyzer.analyze_versions(files_content, file_metadata, diff_matrix, target_context="a cli tool")

    assert "error" not in result
    assert result["recommendation"]["recommended_file_index"] == 0
    assert "File 1 is best." in result["analysis"]


def test_analyze_versions_returns_error_dict_on_llm_failure(monkeypatch):
    analyzer = DiffLLMAnalyzer()

    def _raise(self, query, **kwargs):
        raise LLMResponseException("ollama unreachable")

    monkeypatch.setattr(LLM, "generate_response", _raise)

    files_content = ["version one", "version two"]
    file_metadata = _file_metadata(["a.py", "b.py"])
    diff_matrix = _diff_matrix(files_content)

    result = analyzer.analyze_versions(files_content, file_metadata, diff_matrix)

    assert result["error"] == "ollama unreachable"
    assert result["analysis"] is None


def test_generate_merged_version_extracts_code_block(monkeypatch):
    analyzer = DiffLLMAnalyzer()
    monkeypatch.setattr(
        LLM, "generate_response",
        lambda self, query, **kwargs: _fake_llm_result(
            "Here you go:\n```python\ndef merged():\n    pass\n```"
        ),
    )

    files_content = ["version one"]
    file_metadata = _file_metadata(["a.py"])

    result = analyzer.generate_merged_version(files_content, file_metadata, [], target_context="a cli tool")

    assert "def merged" in result["code"]


def test_generate_merged_version_returns_error_dict_on_llm_failure(monkeypatch):
    analyzer = DiffLLMAnalyzer()

    def _raise(self, query, **kwargs):
        raise LLMResponseException("ollama unreachable")

    monkeypatch.setattr(LLM, "generate_response", _raise)

    result = analyzer.generate_merged_version(["v1"], _file_metadata(["a.py"]), [], target_context="ctx")

    assert result["error"] == "ollama unreachable"
    assert result["code"] is None
