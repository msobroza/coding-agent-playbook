"""``playbook eval --run --all --record OUT --carry-from RELEASES_DIR`` (spec D1).

Driven through ``cli.main`` with the ``fake`` runner, whose ``run_sample`` is
replaced by a canned passing result (``tests.cli.test_eval_record_carry``), so
no harness CLI and no judge run. The releases directory is built from a real
record, renamed to another release and target and trimmed to one sample.
"""

from __future__ import annotations

import argparse
import json
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.cli import main
from coding_agent_playbook.commands._eval_record_flags import carry_from_path
from coding_agent_playbook.evals.model_pins import RecordRefusedError
from tests.cli.test_eval_record_carry import _carry, _load, _record, _RunLog, consumer
from tests.edition_fixtures import SAMPLE_ID

if TYPE_CHECKING:
    from pathlib import Path

__all__ = ["consumer"]  # the fixture, imported so pytest finds it here


def _release_file(base: Path, root: Path, *, release: str, target: str, keep: str) -> Path:
    """``base`` rewritten as ``root/<release>/metrics/<target>.json`` holding only ``keep``."""
    data: dict[str, Any] = _load(base)
    data["release"] = release
    data["target"]["name"] = target
    data["samples"] = {keep: data["samples"][keep]}
    path = root / release / "metrics" / f"{target}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def _one_head_sample(base: Path) -> str:
    """A sample of ``base`` that is not the edition-pinned one, whose control always reruns."""
    ids: list[str] = sorted(_load(base)["samples"])
    return next(sample_id for sample_id in ids if sample_id != SAMPLE_ID)


def _base_and_releases(consumer: Path, log: _RunLog) -> tuple[Path, Path, str]:
    rc, base = _record(consumer, "base")
    assert rc == 0
    keep = _one_head_sample(base)
    releases = consumer / "releases"
    _release_file(base, releases, release="9.9.2", target="opus", keep=keep)
    log.calls.clear()
    return base, releases, keep


def test_carry_from_a_directory_carries_from_any_release(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _RunLog(monkeypatch)
    _base, releases, keep = _base_and_releases(consumer, log)
    capsys.readouterr()

    rc, out = _carry(consumer, "next", releases)
    assert rc == 0
    data = _load(out)
    assert data["summary"]["carried"] == 1
    assert data["samples"][keep]["measured_in"]["release"] == "9.9.2"
    assert keep not in log.heads()
    assert "  carried from 9.9.2 (opus): 1" in capsys.readouterr().out


def test_carry_from_a_file_is_unchanged(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _RunLog(monkeypatch)
    rc, base = _record(consumer, "base")
    assert rc == 0
    log.calls.clear()
    capsys.readouterr()

    rc, out = _carry(consumer, "next", base)
    assert rc == 0
    assert log.heads() == set()
    baseline, carried = _load(base), _load(out)
    assert set(carried["samples"]) == set(baseline["samples"])
    assert (carried["summary"]["rerun"], carried["summary"]["carried"]) == (
        0,
        len(baseline["samples"]),
    )
    printed = capsys.readouterr().out
    assert f"carry plan: 0 rerun, {len(baseline['samples'])} carried" in printed
    assert "carried from" not in printed


def test_the_record_output_inside_the_directory_is_not_indexed(
    consumer: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    log = _RunLog(monkeypatch)
    base, releases, keep = _base_and_releases(consumer, log)
    out = releases / "9.9.3" / "metrics" / "fake-pinned.json"
    stale = _load(base) | {"release": "9.9.3"}
    out.parent.mkdir(parents=True)
    out.write_text(json.dumps(stale), encoding="utf-8")
    capsys.readouterr()

    rc = _eval(consumer, out, releases)
    assert rc == 0
    data = _load(out)
    assert data["summary"]["carried"] == 1
    assert data["samples"][keep]["measured_in"]["release"] == "9.9.2"
    assert "9.9.3 (fake-pinned)" not in capsys.readouterr().out


def _eval(repo: Path, out: Path, carry_from: Path) -> int:
    argv = ["eval", "--run", "--all", "--repo-root", str(repo), "--record", str(out)]
    return main([*argv, "--target", "fake-pinned", "--carry-from", str(carry_from)])


def test_carry_from_a_directory_still_needs_all(tmp_path: Path) -> None:
    args = argparse.Namespace(carry_from=str(tmp_path), all_samples=False)
    with pytest.raises(RecordRefusedError, match="--carry-from needs --all"):
        carry_from_path(args)
