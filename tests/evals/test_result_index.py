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
    data = metrics_file(release, samples, target=target, commit=f"c{release.split('.')[1]}")
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
    _write(tmp_path, "0.2.0", {"t/a": sample_entry(0.5, inputs="in-a")})
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.9, inputs="in-a-old")})
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.carried["t/a"]["measured_in"] == {"release": "0.2.0", "commit": "c2"}
    assert plan.sources["t/a"] == "0.2.0 (opus)"
    assert plan.rerun == {}


def test_the_newest_release_wins(tmp_path: Path) -> None:
    _write(tmp_path, "0.10.0", {"t/a": sample_entry(0.9, inputs="in-a")})
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.5, inputs="in-a")})
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.sources["t/a"] == "0.10.0 (opus)"
    assert plan.carried["t/a"]["mean_score"] == 0.9


def test_the_targets_own_file_wins_within_a_release(tmp_path: Path) -> None:
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.1, inputs="in-a")}, target="alpha")
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.9, inputs="in-a")}, target="opus")
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.sources["t/a"] == "0.3.0 (opus)"
    assert plan.carried["t/a"]["mean_score"] == 0.9


def test_another_target_name_with_the_same_setup_is_reused(tmp_path: Path) -> None:
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.4, inputs="in-a")}, target="alpha")
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.sources["t/a"] == "0.3.0 (alpha)"
    assert plan.carried["t/a"]["mean_score"] == 0.4


def test_a_file_with_another_setup_is_skipped(tmp_path: Path) -> None:
    other = _SETUP | {"harness_version": "2.1.299"}
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=other)
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.full_rerun_reason is not None
    assert "harness_version" in plan.full_rerun_reason
    assert plan.reruns("t/a")
    assert plan.carried == {}


def test_files_without_digests_or_invalid_are_skipped_and_named(tmp_path: Path) -> None:
    no_setup = _write(tmp_path, "0.2.0", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=None)
    no_inputs = _write(tmp_path, "0.2.0", {"t/a": sample_entry(0.4)}, target="beta")
    invalid = tmp_path / "0.3.0" / "metrics" / "opus.json"
    invalid.parent.mkdir(parents=True)
    invalid.write_text(json.dumps({"schema_version": 1}), encoding="utf-8")
    broken = tmp_path / "0.3.0" / "metrics" / "zeta.json"
    broken.write_text("{not json", encoding="utf-8")
    index = ReleaseIndex.load(tmp_path)
    assert index.files == ()
    by_path = {line.split(": ", 1)[0]: line.split(": ", 1)[1] for line in index.skipped}
    assert "setup digest" in by_path[str(no_setup)]
    assert "inputs digest" in by_path[str(no_inputs)]
    assert "release: missing" in by_path[str(invalid)]
    assert "cannot read" in by_path[str(broken)]


def test_the_full_rerun_reason_lists_three_skips_then_counts_the_rest(tmp_path: Path) -> None:
    for minor in range(5):
        _write(tmp_path, f"0.{minor}.0", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=None)
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.full_rerun_reason is not None
    assert plan.full_rerun_reason.count("setup digest") == 3
    assert plan.full_rerun_reason.endswith("and 2 more")


def test_unknown_version_never_matches(tmp_path: Path) -> None:
    unknown = _SETUP | {"harness_version": UNKNOWN_VERSION}
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.4, inputs="in-a")}, setup=unknown)
    plan = _plan(tmp_path, {"t/a": "in-a"}, setup=unknown)
    assert plan.carried == {}
    assert plan.reruns("t/a")


def test_measured_in_survives_a_second_carry(tmp_path: Path) -> None:
    first = carried_entry(sample_entry(0.4, inputs="in-a"), release="0.1.0", commit="c1")
    _write(tmp_path, "0.3.0", {"t/a": first})
    plan = _plan(tmp_path, {"t/a": "in-a"})
    assert plan.carried["t/a"]["measured_in"] == {"release": "0.1.0", "commit": "c1"}
    assert plan.sources["t/a"] == "0.3.0 (opus)"


def test_exclude_leaves_out_the_record_output(tmp_path: Path) -> None:
    out = _write(tmp_path, "0.4.0", {"t/a": sample_entry(0.4, inputs="in-a")})
    index = ReleaseIndex.load(tmp_path, exclude=out)
    assert index.files == ()
    assert index.skipped == ()


def test_a_new_sample_and_a_changed_digest_have_their_reasons(tmp_path: Path) -> None:
    _write(tmp_path, "0.3.0", {"t/a": sample_entry(0.4, inputs="in-a")})
    plan = _plan(tmp_path, {"t/a": "in-a-2", "t/new": "in-n"})
    assert "inputs digest changed" in plan.rerun["t/a"]
    assert "new sample" in plan.rerun["t/new"]
    assert plan.carried == {}


def test_reported_model_comes_from_the_newest_source(tmp_path: Path) -> None:
    _write(tmp_path, "0.2.0", {"t/a": sample_entry(0.4, inputs="in-a")}, reported_model="old")
    _write(tmp_path, "0.3.0", {"t/b": sample_entry(0.4, inputs="in-b")}, reported_model="new")
    _write(tmp_path, "0.4.0", {"t/c": sample_entry(0.4, inputs="x")}, reported_model="unused")
    plan = _plan(tmp_path, {"t/a": "in-a", "t/b": "in-b", "t/c": "in-c"})
    assert set(plan.carried) == {"t/a", "t/b"}
    assert plan.reported_model == "new"
