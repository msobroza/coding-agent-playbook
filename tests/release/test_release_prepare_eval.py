"""``scripts/release.py prepare --eval``: release metrics per target, blocked on regressions.

Spec #281 ticket 15. ``FakeReleaseHost`` stands for git, commitizen, the forge
and the checkout's engine: its ``eval --record`` writes a hand-written metrics
file (``tests.evals.release_metrics_files``) for the target it is asked for, as
the engine's fake runner would. The previous release's files are hand-written
too, so no test starts a process or makes a paid run.
"""

from __future__ import annotations

import json
import sys
import tempfile
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.release.manifest import (
    ManifestEntry,
    ReleaseManifest,
    release_dir,
    render_manifest,
)
from release import PREPARE_EVAL_TIMEOUT_SECONDS, main, prepare
from release_eval import RECORD_TIMEOUT_SECONDS
from tests.evals.release_metrics_files import metrics_file, sample_entry
from tests.release.release_fakes import BASE, FakeReleaseHost

if TYPE_CHECKING:
    from pathlib import Path

_OLD, _NEW = "9.9.8", "9.9.9"
_OPUS, _CODER = "claude-opus", "coder"
_EVALS = f"""
[evals]
release = ["{_OPUS}", "{_CODER}"]

[evals.targets.{_OPUS}]
harness = "claude_code"
model = "claude-opus-5-5"

[evals.targets.{_CODER}]
harness = "opencode"
model = "my-org/coder-32b"

[evals.judge]
model = "claude-opus-5-5"
"""


def _manifest(version: str, base: str, other_digest: str) -> ReleaseManifest:
    def entry(artifact_id: str, digest: str) -> ManifestEntry:
        path = f"catalog/core/prompts/{artifact_id}.md"
        return ManifestEntry("coding_agent_playbook", "prompt", artifact_id, path, digest)

    graded = entry("review", "g1")
    return ReleaseManifest(version, base, (graded,), (graded, entry("refactor", other_digest)))


def _metrics_dir(checkout: Path, version: str) -> Path:
    return release_dir(checkout / "catalog", version) / "metrics"


def _checkout(
    tmp_path: Path, *, evals: str = _EVALS, previous: dict[str, Any] | None = None
) -> Path:
    """A checkout released at ``_OLD`` (with ``previous`` metrics files by target)."""
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{_OLD}"\n', encoding="utf-8"
    )
    (checkout / CONFIG_FILENAME).write_text(evals, encoding="utf-8")
    old = release_dir(checkout / "catalog", _OLD)
    old.mkdir(parents=True)
    (old / "manifest.toml").write_text(render_manifest(_manifest(_OLD, "0ld", "o1")), "utf-8")
    for target, data in (previous or {}).items():
        _metrics_dir(checkout, _OLD).mkdir(exist_ok=True)
        (_metrics_dir(checkout, _OLD) / f"{target}.json").write_text(json.dumps(data), "utf-8")
    return checkout


def _recorded(target: str, mean: float, **extra: Any) -> dict[str, Any]:
    """What the checkout's engine records: its own version, the base commit."""
    samples = {"review/a": sample_entry(mean), "review/b": sample_entry(0.9)}
    return metrics_file("0.0.0+local", samples, target=target, commit=BASE, **extra)


def _previous(target: str, mean: float = 0.9) -> dict[str, Any]:
    samples = {"review/a": sample_entry(mean), "review/b": sample_entry(0.9)}
    return metrics_file(_OLD, samples, target=target)


def _host(fail_on: str | None = None, **recordings: dict[str, Any]) -> FakeReleaseHost:
    named = {name.replace("_", "-"): data for name, data in recordings.items()}
    return FakeReleaseHost(
        tags=[f"v{_OLD}"], cz_next={(): (0, f"{_NEW}\n")}, recordings=named, fail_on=fail_on
    )


def _run(checkout: Path, host: FakeReleaseHost, *flags: str) -> int:
    def snapshot(base: str) -> ReleaseManifest:
        return _manifest("0", base, "o2")

    argv = ["prepare-checkout", "--base", BASE, "--eval", *flags]
    return main(argv, cwd=checkout, runner=host, snapshot=snapshot)


def _stored(checkout: Path, target: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads(
        (_metrics_dir(checkout, _NEW) / f"{target}.json").read_text("utf-8")
    )
    return data


@pytest.fixture(autouse=True)
def _temp_in_tmp_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Every temporary directory (the kept metrics among them) lands under ``tmp_path``."""
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp))
    return temp


def _kept(temp: Path) -> list[Path]:
    return sorted(temp.glob("playbook-release-metrics-*/*.json"))


# --------------------------------------------------------------------------- #
# Recording
# --------------------------------------------------------------------------- #


def test_every_release_target_is_recorded_by_the_checkouts_engine(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    host = _host(claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 0

    assert host.recorded_targets() == [_OPUS, _CODER]
    command = next(c for c in host.commands if "--record" in c)
    out = _metrics_dir(checkout, _NEW) / f"{_OPUS}.json"
    assert command == [
        sys.executable,
        "-m",
        "coding_agent_playbook.cli",
        "eval",
        "--run",
        "--all",
        "--repo-root",
        str(checkout),
        "--target",
        _OPUS,
        "--record",
        str(out),
        "--judge",
        "llm",
    ]
    assert host.timeouts[host.commands.index(command)] == RECORD_TIMEOUT_SECONDS
    # Recorded before the release files and the version bump, on the base's catalog.
    assert host.commands.index(command) < next(
        i for i, c in enumerate(host.commands) if "--version-files-only" in c
    )


def test_each_file_names_the_release_and_lands_in_the_release_commit(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    host = _host(claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 0

    stored = _stored(checkout, _OPUS)
    assert (stored["release"], stored["commit"]) == (_NEW, BASE)
    assert stored["target"]["name"] == _OPUS
    assert host.ran("add", "--all", "--", "pyproject.toml", f"catalog/releases/{_NEW}")
    assert host.ran("pr", "create", "--base", "main", "--title", f"chore(release): v{_NEW}")


def test_no_judge_model_records_without_a_judge(tmp_path: Path) -> None:
    evals = _EVALS.replace('[evals.judge]\nmodel = "claude-opus-5-5"\n', "")
    host = _host(claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(_checkout(tmp_path, evals=evals), host) == 0

    assert not host.ran("--judge")


def test_without_previous_files_nothing_is_compared(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    host = _host(claude_opus=_recorded(_OPUS, 0.1), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 0

    assert _stored(checkout, _OPUS)["previous"] is None
    (body,) = host.bodies
    assert body.startswith(f"# Release {_NEW}\n")
    assert f"- `{_OPUS}`: 2 samples (full run), pass rate 1.0, mean score 0.9; no" in body


def test_the_comparison_is_stored_and_summarised_in_the_pull_request(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path, previous={_OPUS: _previous(_OPUS, mean=0.7)})
    host = _host(claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 0

    stored = _stored(checkout, _OPUS)
    assert stored["previous"] == _OLD
    assert stored["samples"]["review/a"]["vs_previous"]["status"] == "improvement"
    assert stored["summary"]["improvements"] == 1
    (body,) = host.bodies
    assert f"vs {_OLD}: 0 regressions (0 accepted), 1 improvements" in body
    assert "## Release metrics" in body


def test_the_pull_request_says_how_many_samples_were_rerun_and_carried(tmp_path: Path) -> None:
    # #329 ticket 06: a carried entry is not compared, so it never blocks.
    carried = sample_entry(0.5) | {"measured_in": {"release": _OLD, "commit": "0ld"}}
    recorded = _recorded(_OPUS, 0.9)
    recorded["samples"]["review/b"] = carried
    recorded["summary"] |= {"rerun": 1, "carried": 1}
    checkout = _checkout(tmp_path, previous={_OPUS: _previous(_OPUS)})
    host = _host(claude_opus=recorded, coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 0

    stored = _stored(checkout, _OPUS)
    assert stored["samples"]["review/b"]["vs_previous"]["status"] == "carried"
    assert (stored["summary"]["rerun"], stored["summary"]["carried"]) == (1, 1)
    (body,) = host.bodies
    assert f"- `{_OPUS}`: 2 samples (changed-only: 1 rerun, 1 carried), pass rate" in body
    assert f"- `{_CODER}`: 2 samples (full run), pass rate" in body


def _carry_from(host: FakeReleaseHost, target: str) -> str | None:
    """The ``--carry-from`` path the record command of ``target`` received, if any."""
    command = next(c for c in host.commands if "--record" in c and target in c)
    return command[command.index("--carry-from") + 1] if "--carry-from" in command else None


def test_a_target_with_a_previous_file_records_changed_only_from_it(tmp_path: Path) -> None:
    # #329 ticket 07: changed-only is the default; a target without a previous file runs full.
    checkout = _checkout(tmp_path, previous={_OPUS: _previous(_OPUS)})
    host = _host(claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 0

    assert _carry_from(host, _OPUS) == str(_metrics_dir(checkout, _OLD) / f"{_OPUS}.json")
    assert _carry_from(host, _CODER) is None


def test_full_records_every_target_without_a_baseline(tmp_path: Path) -> None:
    previous = {_OPUS: _previous(_OPUS), _CODER: _previous(_CODER)}
    checkout = _checkout(tmp_path, previous=previous)
    host = _host(claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host, "--full") == 0

    assert (_carry_from(host, _OPUS), _carry_from(host, _CODER)) == (None, None)
    (body,) = host.bodies
    assert f"- `{_OPUS}`: 2 samples (full run), pass rate" in body
    # The full run is still compared with the previous release's file.
    assert _stored(checkout, _OPUS)["previous"] == _OLD


def test_the_first_release_records_every_target_in_full(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path)
    host = FakeReleaseHost(
        recordings={_OPUS: _recorded(_OPUS, 0.9), _CODER: _recorded(_CODER, 0.9)}
    )

    argv = ["prepare-checkout", "--base", BASE, "--version", _NEW, "--eval"]
    assert main(argv, cwd=checkout, runner=host, snapshot=lambda b: _manifest("0", b, "o2")) == 0

    assert (_carry_from(host, _OPUS), _carry_from(host, _CODER)) == (None, None)


# --------------------------------------------------------------------------- #
# Regressions
# --------------------------------------------------------------------------- #


def test_an_unaccepted_regression_refuses_the_pull_request_and_keeps_the_files(
    tmp_path: Path, _temp_in_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = _checkout(tmp_path, previous={_OPUS: _previous(_OPUS)})
    host = _host(claude_opus=_recorded(_OPUS, 0.5), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 1

    captured = capsys.readouterr()
    assert f"unaccepted regressions on target(s) {_OPUS}" in captured.err
    assert "REGRESSION: mean score drops 0.400" in captured.out
    assert not host.ran("push")
    assert not host.ran("pr", "create")
    assert not host.ran("--version-files-only")
    kept = _kept(_temp_in_tmp_path)
    assert sorted(path.name for path in kept) == sorted([f"{_OPUS}.json", f"{_CODER}.json"])
    assert f"--reuse-metrics {kept[0].parent}" in captured.err


@pytest.mark.parametrize("step", ["push", "pr create", "--version-files-only"])
def test_a_refusal_while_publishing_keeps_the_recorded_files(
    step: str, tmp_path: Path, _temp_in_tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression (PR #323 review): the branch is discarded, the paid recordings are not."""
    host = _host(step, claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(_checkout(tmp_path), host) == 1

    captured = capsys.readouterr()
    assert f"{step} failed" in captured.err
    kept = _kept(_temp_in_tmp_path)
    assert sorted(path.name for path in kept) == sorted([f"{_OPUS}.json", f"{_CODER}.json"])
    assert f"--reuse-metrics {kept[0].parent}" in captured.err


def test_an_accepted_regression_stores_its_reason_and_opens_the_pull_request(
    tmp_path: Path,
) -> None:
    previous = {_OPUS: _previous(_OPUS), _CODER: _previous(_CODER)}
    checkout = _checkout(tmp_path, previous=previous)
    host = _host(claude_opus=_recorded(_OPUS, 0.5), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host, "--accept", "review/a=the rubric is stricter") == 0

    stored = _stored(checkout, _OPUS)
    vs_previous = stored["samples"]["review/a"]["vs_previous"]
    assert (vs_previous["status"], vs_previous["accepted"]) == (
        "regression",
        "the rubric is stricter",
    )
    assert stored["summary"]["accepted_regressions"] == 1
    # The other target did not regress, so it stores no acceptance.
    assert "accepted" not in _stored(checkout, _CODER)["samples"]["review/a"]["vs_previous"]
    assert host.ran("pr", "create")


def test_accepting_a_sample_that_regressed_nowhere_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    checkout = _checkout(tmp_path, previous={_OPUS: _previous(_OPUS)})
    host = _host(claude_opus=_recorded(_OPUS, 0.9), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host, "--accept", "review/b=typo") == 1

    assert "--accept names 'review/b', which regressed on no release target" in (
        capsys.readouterr().err
    )
    assert not host.ran("pr", "create")


def test_a_control_that_drifted_is_noted_in_the_pull_request(tmp_path: Path) -> None:
    def with_control(data: dict[str, Any], mean: float) -> dict[str, Any]:
        return data | {"controls": {"review/a": sample_entry(mean, graded="v9.9.7")}}

    previous = {_OPUS: with_control(_previous(_OPUS), 0.9)}
    checkout = _checkout(tmp_path, previous=previous)
    host = _host(claude_opus=with_control(_recorded(_OPUS, 0.9), 0.5), coder=_recorded(_CODER, 0.9))

    assert _run(checkout, host) == 0

    (body,) = host.bodies
    assert "note: control 'review/a' on frozen edition v9.9.7 moved" in body


# --------------------------------------------------------------------------- #
# Reusing kept files
# --------------------------------------------------------------------------- #


def _kept_dir(tmp_path: Path, **files: dict[str, Any]) -> Path:
    kept = tmp_path / "kept"
    kept.mkdir()
    for name, data in files.items():
        (kept / f"{name.replace('_', '-')}.json").write_text(json.dumps(data), "utf-8")
    return kept


def test_reuse_metrics_skips_recording_a_target_kept_on_the_same_base(tmp_path: Path) -> None:
    checkout = _checkout(tmp_path, previous={_OPUS: _previous(_OPUS)})
    kept = _kept_dir(tmp_path, claude_opus=_recorded(_OPUS, 0.5))
    host = _host(coder=_recorded(_CODER, 0.9))

    flags = ("--reuse-metrics", str(kept), "--accept", "review/a=stricter rubric")
    assert _run(checkout, host, *flags) == 0

    assert host.recorded_targets() == [_CODER]
    assert _stored(checkout, _OPUS)["samples"]["review/a"]["vs_previous"]["accepted"] == (
        "stricter rubric"
    )


def test_a_reused_file_with_carried_entries_says_changed_only(tmp_path: Path) -> None:
    # The kept file was recorded changed-only by the refused run, whatever this run asks.
    reused = _recorded(_OPUS, 0.9)
    reused["samples"]["review/b"] |= {"measured_in": {"release": _OLD, "commit": "0ld"}}
    kept = _kept_dir(tmp_path, claude_opus=reused)
    host = _host(coder=_recorded(_CODER, 0.9))

    assert _run(_checkout(tmp_path), host, "--full", "--reuse-metrics", str(kept)) == 0

    assert host.recorded_targets() == [_CODER]
    (body,) = host.bodies
    assert f"- `{_OPUS}`: 2 samples (changed-only: 1 rerun, 1 carried), pass rate" in body
    assert f"- `{_CODER}`: 2 samples (full run), pass rate" in body


def test_reuse_metrics_refuses_a_file_recorded_on_another_commit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    stale = _recorded(_OPUS, 0.9) | {"commit": "0ther"}
    kept = _kept_dir(tmp_path, claude_opus=stale)

    assert _run(_checkout(tmp_path), _host(), "--reuse-metrics", str(kept)) == 1

    assert "was recorded on commit 0ther, not on the base" in capsys.readouterr().err


# --------------------------------------------------------------------------- #
# Refusals before any paid run
# --------------------------------------------------------------------------- #


def test_no_release_targets_is_refused_before_the_release_branch(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host()

    assert _run(_checkout(tmp_path, evals=""), host) == 1

    assert f"[evals] release list of {CONFIG_FILENAME} names no target" in (capsys.readouterr().err)
    assert not host.ran("switch", "--force-create")
    assert host.recorded_targets() == []


@pytest.mark.parametrize("command", ["prepare", "prepare-checkout"])
def test_full_without_eval_is_a_usage_error(
    command: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host()
    base = ["--base", BASE] if command == "prepare-checkout" else []

    with pytest.raises(SystemExit) as exited:
        main([command, *base, "--full"], cwd=tmp_path, runner=host)

    assert exited.value.code == 2
    assert "--full belongs to --eval" in capsys.readouterr().err
    assert host.commands == []


@pytest.mark.parametrize(
    ("flags", "message"),
    [
        (("--accept", "review/a=x"), "belong to --eval"),
        (("--eval", "--accept", "review/a"), "--accept expects SAMPLE=REASON"),
    ],
)
def test_misused_eval_flags_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], flags: tuple[str, ...], message: str
) -> None:
    host = _host()

    assert main(["prepare", *flags], cwd=tmp_path, runner=host) == 1

    assert message in capsys.readouterr().err
    assert host.commands == []


def test_a_failed_recording_names_the_target_and_opens_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    host = _host(claude_opus=_recorded(_OPUS, 0.9))  # no recording for `coder`

    assert _run(_checkout(tmp_path), host) == 1

    err = capsys.readouterr().err
    assert f"recording target {_CODER!r} exited 2" in err
    assert "the recorded metrics are kept in" in err
    assert not host.ran("pr", "create")


# --------------------------------------------------------------------------- #
# The outer step
# --------------------------------------------------------------------------- #


def test_prepare_passes_the_eval_flags_on_with_a_long_timeout(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    host = FakeReleaseHost()
    flags = ["--eval", "--accept", "review/a=stricter rubric"]

    assert (
        prepare(tmp_path, version=None, eval_flags=flags, runner=host, make_scratch=lambda: scratch)
        == 0
    )

    inner = next(c for c in host.commands if "prepare-checkout" in c)
    assert inner[-3:] == flags
    assert host.timeouts[host.commands.index(inner)] == PREPARE_EVAL_TIMEOUT_SECONDS


def test_prepare_without_eval_keeps_the_default_timeout(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    host = FakeReleaseHost()

    assert prepare(tmp_path, version=None, runner=host, make_scratch=lambda: scratch) == 0

    inner = next(c for c in host.commands if "prepare-checkout" in c)
    assert "--eval" not in inner
    assert host.timeouts[host.commands.index(inner)] is None


def test_prepare_passes_full_on_to_the_checkout(tmp_path: Path) -> None:
    host = FakeReleaseHost()

    assert main(["prepare", "--eval", "--full"], cwd=tmp_path, runner=host) == 0

    inner = next(c for c in host.commands if "prepare-checkout" in c)
    assert inner[-2:] == ["--eval", "--full"]
