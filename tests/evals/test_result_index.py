"""The result index: which committed release entry each sample of a record carries (spec D1).

Release directories are hand-written under ``tmp_path`` with
``release_metrics_files``, so each choice of source can be checked on its own.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from coding_agent_playbook.evals.release_carry import carried_entry
from coding_agent_playbook.evals.result_index import ReleaseIndex
from coding_agent_playbook.evals.setup_digest import UNKNOWN_VERSION, SetupParts
from tests.evals.release_metrics_files import metrics_file, sample_entry

if TYPE_CHECKING:
    from pathlib import Path

_SETUP: dict[str, object] = SetupParts(
    "claude_code",
    "2.1.300",
    "claude-opus-5-5",
    None,
    None,
    3,
    None,
    None,
    None,
    None,
    True,
    True,
    "s1",
).as_dict()


def _write(
    root: Path,
    release: str,
    samples: dict[str, dict[str, Any]],
    *,
    target: str = "opus",
    setup: dict[str, object] | None = _SETUP,
    reported_model: str = "claude-opus-5-5",
) -> Path:
    data = metrics_file(release, samples, target=target, commit=f"c{release.split('.')[2]}")
    data["target"]["reported_model"] = reported_model
    if setup is not None:
        data |= {"setup_digest": "d1", "setup": dict(setup)}
    path = root / release / "metrics" / f"{target}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _plan(root: Path, inputs: dict[str, str], *, setup: dict[str, object] = _SETUP) -> Any:
    return ReleaseIndex.load(root).plan(target_name="opus", setup=setup, inputs=inputs)


def test_a_sample_found_in_an_older_release_is_carried_from_it(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.2", {"t/a": sample_entry(0.5, inputs="in-a")})
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.9, inputs="in-a-old")})
    plan = _plan(tmp_path, {"t/a": "in-a"})
    measured = {"release": "9.9.2", "commit": "c2", "target": "opus"}
    assert plan.carried["t/a"]["measured_in"] == measured
    assert plan.sources["t/a"] == "9.9.2 (opus)"
    assert plan.rerun == {}


def test_the_newest_release_wins(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.10", {"t/a": sample_entry(0.9, inputs="in-a")})
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.5, inputs="in-a")})
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.sources["t/a"] == "9.9.10 (opus)"
    assert plan.carried["t/a"]["mean_score"] == 0.9


def test_the_targets_own_file_wins_within_a_release(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.1, inputs="in-a")}, target="alpha")
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.9, inputs="in-a")}, target="opus")
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.sources["t/a"] == "9.9.3 (opus)"
    assert plan.carried["t/a"]["mean_score"] == 0.9


def test_another_target_name_with_the_same_setup_is_reused(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.4, inputs="in-a")}, target="alpha")
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.sources["t/a"] == "9.9.3 (alpha)"
    assert plan.carried["t/a"]["mean_score"] == 0.4
    assert plan.carried["t/a"]["measured_in"]["target"] == "alpha"


def test_a_file_with_another_setup_is_skipped(tmp_path: Path) -> None:
    other = _SETUP | {"harness_version": "2.1.299"}
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=other)
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.full_rerun_reason is not None
    assert "harness_version" in plan.full_rerun_reason
    assert plan.reruns("t/a")
    assert plan.carried == {}


def test_files_without_digests_or_invalid_are_skipped_and_named(tmp_path: Path) -> None:
    no_setup = _write(tmp_path, "9.9.2", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=None)
    invalid = tmp_path / "9.9.3" / "metrics" / "opus.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    broken = tmp_path / "9.9.3" / "metrics" / "zeta.json"
    broken.write_text("{not json", encoding="utf-8")
    index = ReleaseIndex.load(tmp_path)
    assert index.files == ()
    by_path = {line.split(": ", 1)[0]: line.split(": ", 1)[1] for line in index.skipped}
    assert set(by_path) == {str(no_setup), str(invalid), str(broken)}
    assert "setup digest" in by_path[str(no_setup)]
    assert "release: missing" in by_path[str(invalid)]
    assert "cannot read" in by_path[str(broken)]


def test_entries_without_an_inputs_digest_are_left_out_not_their_file(tmp_path: Path) -> None:
    samples = {"t/old": sample_entry(0.4), "t/b": sample_entry(0.8, inputs="in-b")}
    path = _write(tmp_path, "9.9.3", samples)
    index = ReleaseIndex.load(tmp_path)
    assert [indexed.path for indexed in index.files] == [path]
    assert index.skipped == ()
    plan = index.plan(target_name="opus", setup=_SETUP, inputs={"t/old": "x", "t/b": "in-b"})
    assert "new sample" in plan.rerun["t/old"]
    assert plan.sources == {"t/b": "9.9.3 (opus)"}


def test_a_file_whose_entries_all_lack_an_inputs_digest_holds_nothing(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.4)})
    index = ReleaseIndex.load(tmp_path)
    assert index.skipped == ()
    plan = index.plan(target_name="opus", setup=_SETUP, inputs={"t/a": "in-a"})
    assert plan.full_rerun_reason is None
    assert "new sample" in plan.rerun["t/a"]
    assert plan.carried == {}


def test_the_full_rerun_reason_lists_three_skips_then_counts_the_rest(tmp_path: Path) -> None:
    for minor in range(5):
        _write(tmp_path, f"9.9.{minor}", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=None)
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.full_rerun_reason is not None
    assert plan.full_rerun_reason.count("setup digest") == 3
    assert plan.full_rerun_reason.endswith("and 2 more")


def test_unknown_version_never_matches(tmp_path: Path) -> None:
    unknown = _SETUP | {"harness_version": UNKNOWN_VERSION}
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=unknown)
    plan = _plan(tmp_path, {"t/a": "in-a"}, setup=unknown)
    assert plan.carried == {}
    assert plan.reruns("t/a")


def test_measured_in_survives_a_second_carry(tmp_path: Path) -> None:
    first = carried_entry(sample_entry(0.4, inputs="in-a"), release="9.9.1", commit="c1")
    _write(tmp_path, "9.9.3", {"t/a": first})
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.carried["t/a"]["measured_in"] == {"release": "9.9.1", "commit": "c1"}
    assert plan.sources["t/a"] == "9.9.3 (opus)"


def test_exclude_leaves_out_the_record_output(tmp_path: Path) -> None:
    out = _write(tmp_path, "9.9.4", {"t/a": sample_entry(0.4, inputs="in-a")})
    index = ReleaseIndex.load(tmp_path, exclude=out)
    assert index.files == ()
    assert index.skipped == ()


def test_a_new_sample_and_a_changed_digest_have_their_reasons(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.4, inputs="in-a")})
    plan = _plan(tmp_path, {"t/a": "in-a-2", "t/new": "in-n"})
    assert "inputs digest changed" in plan.rerun["t/a"]
    assert "new sample" in plan.rerun["t/new"]
    assert plan.carried == {}


def test_reported_model_comes_from_the_newest_source(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.2", {"t/a": sample_entry(0.4, inputs="in-a")}, reported_model="old")
    _write(tmp_path, "9.9.3", {"t/b": sample_entry(0.4, inputs="in-b")}, reported_model="new")
    _write(tmp_path, "9.9.4", {"t/c": sample_entry(0.4, inputs="x")}, reported_model="unused")
    plan = _plan(tmp_path, {"t/a": "in-a", "t/b": "in-b", "t/c": "in-c"})
    assert set(plan.carried) == {"t/a", "t/b"}
    assert plan.reported_model == "new"


#: This record's setup when it has a judge; the stored files differ from it in the judge only.
_JUDGED: dict[str, object] = _SETUP | {"judge_model": "judge-new", "judge_samples": 2}
_OLD_JUDGE: dict[str, object] = _JUDGED | {"judge_model": "judge-old"}


def test_a_judge_only_difference_plans_a_rejudge(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.2", {"t/a": sample_entry(0.5, inputs="in-a")}, setup=_OLD_JUDGE)
    plan = _plan(tmp_path, {"t/a": "in-a"}, setup=_JUDGED)
    assert plan.full_rerun_reason is None
    assert (plan.rerun, plan.carried) == ({}, {})
    source = plan.rejudge["t/a"]
    assert (source.release, source.commit, source.target) == ("9.9.2", "c2", "opus")
    assert source.entry["mean_score"] == 0.5
    assert source.judge["judge_model"] == "judge-old"
    assert source.measured_in == {"release": "9.9.2", "commit": "c2", "target": "opus"}


def test_a_full_match_wins_over_a_rejudge(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.3", {"t/a": sample_entry(0.9, inputs="in-a")}, setup=_OLD_JUDGE)
    _write(tmp_path, "9.9.2", {"t/a": sample_entry(0.5, inputs="in-a")}, setup=_JUDGED)
    plan = _plan(tmp_path, {"t/a": "in-a"}, setup=_JUDGED)
    assert plan.rejudge == {}
    assert plan.sources["t/a"] == "9.9.2 (opus)"
    assert plan.carried["t/a"]["mean_score"] == 0.5


def test_a_non_judge_difference_still_reruns(tmp_path: Path) -> None:
    other = _OLD_JUDGE | {"harness_version": "2.1.299"}
    _write(tmp_path, "9.9.2", {"t/a": sample_entry(0.5, inputs="in-a")}, setup=other)
    plan = _plan(tmp_path, {"t/a": "in-a"}, setup=_JUDGED)
    assert plan.full_rerun_reason is not None
    assert plan.reruns("t/a")
    assert plan.rejudge == {}


def test_a_record_without_a_judge_never_rejudges(tmp_path: Path) -> None:
    _write(tmp_path, "9.9.2", {"t/a": sample_entry(0.5, inputs="in-a")}, setup=_OLD_JUDGE)
    plan = _plan(tmp_path, {"t/a": "in-a"}, setup=_JUDGED | {"judge_model": None})
    assert plan.full_rerun_reason is not None
    assert plan.rejudge == {}


def test_a_rejudge_of_a_carried_entry_keeps_where_it_was_measured(tmp_path: Path) -> None:
    measured = {"release": "9.9.1", "commit": "c1", "target": "alpha"}
    entry = sample_entry(0.5, inputs="in-a") | {"measured_in": measured}
    _write(tmp_path, "9.9.2", {"t/a": entry}, setup=_OLD_JUDGE)
    plan = _plan(tmp_path, {"t/a": "in-a", "t/b": "in-b"}, setup=_JUDGED)
    assert plan.rejudge["t/a"].measured_in == measured
    assert "new sample" in plan.rerun["t/b"]
