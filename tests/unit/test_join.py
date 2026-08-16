"""Unit tests for join.join -- pure grouping/clustering logic, no Qt involved."""

from join.join import (
    Grouping,
    JoinMulti,
    UnconfirmedGrouping,
    format_percent,
    invert_dict,
    longest_common_substring,
    string_distance,
)


def _write(tmp_path, name, lines):
    path = tmp_path / name
    path.write_text("\n".join(lines) + "\n")
    return str(path)


def test_format_percent():
    assert format_percent(0.5, 1) == "50.0%"
    assert format_percent(1, 0) == "100%"


def test_string_distance_identical_strings_is_zero():
    assert string_distance("abc", "abc") == 0


def test_string_distance_counts_edits():
    assert string_distance("kitten", "sitting") == 3


def test_longest_common_substring():
    assert longest_common_substring("modlist_skyrim", "modlist_daggerfall") == "modlist_"


def test_invert_dict_groups_keys_by_value():
    result = invert_dict({"a": 1, "b": 2, "c": 1})
    assert sorted(result[1]) == ["a", "c"]
    assert result[2] == ["b"]


def test_process_files_groups_lines_across_files_case_insensitively(tmp_path):
    file_a = _write(tmp_path, "a.txt", ["Shared Line", "Only In A"])
    file_b = _write(tmp_path, "b.txt", ["shared line", "Only In B"])

    join = JoinMulti([file_a, file_b])
    join.process_files()

    assert join.line_files["shared line"] == ["a.txt", "b.txt"]
    assert join.line_files["only in a"] == ["a.txt"]


def test_sort_and_set_groupings_separates_grouped_and_ungrouped(tmp_path):
    file_a = _write(tmp_path, "a.txt", ["shared", "unique a"])
    file_b = _write(tmp_path, "b.txt", ["shared", "unique b"])

    join = JoinMulti([file_a, file_b])
    join.process_files()
    join.sort_and_set_groupings()

    assert "shared" in join.groupings
    assert isinstance(join.groupings["shared"], Grouping)
    assert join.groupings["shared"].files == ["a.txt", "b.txt"]
    assert join.ungrouped["unique a"] == "a.txt"
    assert join.ungrouped["unique b"] == "b.txt"


def test_set_name_uses_longest_common_substring(tmp_path):
    file_a = _write(tmp_path, "modlist_skyrim.txt", ["x"])
    file_b = _write(tmp_path, "modlist_daggerfall.txt", ["y"])

    join = JoinMulti([file_a, file_b])
    join.set_name()

    assert join.name == "modlist"


def test_set_name_falls_back_to_unnamed_with_no_common_substring(tmp_path):
    file_a = _write(tmp_path, "abc.txt", ["x"])
    file_b = _write(tmp_path, "xyz.txt", ["y"])

    join = JoinMulti([file_a, file_b])
    join.set_name()

    assert join.name == "UNNAMED"


def test_grouping_merge_tracks_source_names():
    grouping = Grouping("primary", ["a.txt"])
    assert not grouping.is_merged()

    grouping.merge(["b.txt"], "secondary")

    assert grouping.is_merged()
    assert "b.txt" in grouping.files
    assert grouping.other_names["b.txt"] == "secondary"


def test_merge_similars_combines_two_ungrouped_lines(tmp_path):
    file_a = _write(tmp_path, "a.txt", ["file alpha", "close match one"])
    file_b = _write(tmp_path, "b.txt", ["file beta", "close match two"])

    join = JoinMulti([file_a, file_b])
    join.process_files()
    join.sort_and_set_groupings()

    unconfirmed = UnconfirmedGrouping(
        "close match one", ["a.txt"], "close match two", ["b.txt"], string_distance=1
    )
    merged = join.merge_similars(unconfirmed)

    assert set(merged.files) == {"a.txt", "b.txt"}
    assert merged.name in join.groupings
    assert join.groupings[merged.name] is merged
    # merge_similars only ever updates self.groupings -- it does not clean up
    # self.ungrouped for the lines it just merged, so both original entries
    # are still present there.
    assert join.ungrouped["close match one"] == "a.txt"
    assert join.ungrouped["close match two"] == "b.txt"


def test_has_unconfirmed_groupings():
    join = JoinMulti([])
    assert not join.has_unconfirmed_groupings()
    join.maybe_groupings.append(object())
    assert join.has_unconfirmed_groupings()


def test_store_and_get_stored_or_new_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(JoinMulti, "STORE_LOCATION", str(tmp_path / "store.pkl"))

    original = JoinMulti(["a.txt", "b.txt"])
    original.set_name()
    original.store()

    restored = JoinMulti.get_stored_or_new()

    assert restored.restored is True
    assert restored.file_paths == ["a.txt", "b.txt"]
    assert restored.name == original.name


def test_get_stored_or_new_without_store_returns_fresh_instance(tmp_path, monkeypatch):
    monkeypatch.setattr(JoinMulti, "STORE_LOCATION", str(tmp_path / "missing.pkl"))

    result = JoinMulti.get_stored_or_new()

    assert result.restored is False
    assert result.file_paths == []


def test_remove_store_deletes_file_and_returns_fresh_instance(tmp_path, monkeypatch):
    store_path = tmp_path / "store.pkl"
    monkeypatch.setattr(JoinMulti, "STORE_LOCATION", str(store_path))

    JoinMulti(["a.txt"]).store()
    assert store_path.exists()

    result = JoinMulti.remove_store()

    assert not store_path.exists()
    assert result.file_paths == []


def test_find_similars_flags_close_lines_from_different_files(tmp_path):
    file_a = _write(tmp_path, "a.txt", ["only in a"])
    file_b = _write(tmp_path, "b.txt", ["only in b"])

    join = JoinMulti([file_a, file_b])
    join.process_files()
    join.sort_and_set_groupings()
    join.find_similars()

    assert join.has_unconfirmed_groupings()
    pair = join.maybe_groupings[0]
    assert {pair.l0, pair.l1} == {"only in a", "only in b"}
    assert pair.string_distance == 1


def test_find_similars_skips_lines_that_already_share_a_file(tmp_path):
    # Two textually-close lines that both live in the same single file should
    # never be proposed as a cross-file match, no matter how similar they are.
    file_a = _write(tmp_path, "a.txt", ["close match one", "close match two"])

    join = JoinMulti([file_a])
    join.process_files()
    join.sort_and_set_groupings()
    join.find_similars()

    assert join.maybe_groupings == []


def test_find_common_uniques_flags_mutually_exclusive_lines(tmp_path):
    file_a = _write(tmp_path, "a.txt", ["left phrase"])
    file_b = _write(tmp_path, "b.txt", ["left phrase"])
    file_c = _write(tmp_path, "c.txt", ["right phrase"])
    file_d = _write(tmp_path, "d.txt", ["right phrase"])

    join = JoinMulti([file_a, file_b, file_c, file_d])
    join.process_files()

    # Lower files_threshold from its default of 3 so these 2-file lines qualify.
    pairs = join.find_common_uniques(files_threshold=1)

    assert ("left phrase", "right phrase") in pairs
    intersection, exclusiveness_proportion, all_files_proportion = pairs[("left phrase", "right phrase")]
    assert intersection == set()
    assert exclusiveness_proportion == 0.0
    assert all_files_proportion == 1.0


def test_find_common_uniques_ignores_lines_below_files_threshold(tmp_path):
    file_a = _write(tmp_path, "a.txt", ["rare line"])
    file_b = _write(tmp_path, "b.txt", ["also rare"])

    join = JoinMulti([file_a, file_b])
    join.process_files()

    # Default files_threshold=3 requires >3 files; neither line qualifies.
    pairs = join.find_common_uniques()

    assert pairs == {}
