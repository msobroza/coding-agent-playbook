"""``playbook eval --run`` on a pinned core sample grades its frozen edition (#281 ticket 09).

The engine is pointed at a copy of the catalog (a checkout layout, ``src/<pkg>``
next to ``catalog/``) holding one extra core sample, ``review/pinned``, pinned to
a fixture edition. Hermetic: only the ``fake`` runner runs.
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.catalog import roots as catalog_roots
from coding_agent_playbook.catalog.digest import artifact_digest
from coding_agent_playbook.cli.parser import build_parser
from coding_agent_playbook.commands import eval as _eval
from coding_agent_playbook.evals.prompting import render_prompt
from coding_agent_playbook.evals.run import harness_runner
from coding_agent_playbook.release.edition import load_edition
from tests._catalog import REPO_ROOT
from tests.edition_fixtures import (
    FROZEN_PROMPT_BODY,
    FROZEN_RULE_BODY,
    OVERRIDE_RULE_BODY,
    SAMPLE_ID,
    TAG,
    freeze_fixture_edition,
    write_local_rule_override,
    write_sample,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_PINNED_NOTE = f"graded edition {TAG} (frozen; overrides ignored)"


@pytest.fixture
def engine_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A copy of the engine catalog with ``review/pinned`` pinned to a frozen fixture edition."""
    catalog = tmp_path / "engine" / "catalog"
    shutil.copytree(REPO_ROOT / "catalog", catalog)
    monkeypatch.setattr(
        catalog_roots, "_PACKAGE_DIR", tmp_path / "engine" / "src" / "coding_agent_playbook"
    )
    write_sample(catalog / "core", edition=TAG)
    freeze_fixture_edition(catalog)
    return catalog


@pytest.fixture
def rendered(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Every prompt text the runner renders."""
    texts: list[str] = []

    def _spy(sample: Any, **kwargs: Any) -> str:
        texts.append(render_prompt(sample, **kwargs))
        return texts[-1]

    monkeypatch.setattr(harness_runner, "render_prompt", _spy)
    return texts


def _run(repo: Path, *flags: str) -> int:
    args = build_parser().parse_args(
        ["eval", SAMPLE_ID, "--run", "--runner", "fake", "--repo-root", str(repo), *flags]
    )
    return _eval.run(args)


def _consumer(tmp_path: Path, make_synthetic_repo: Callable[..., Path]) -> Path:
    (tmp_path / "consumer").mkdir()
    return make_synthetic_repo(tmp_path / "consumer")


def test_a_pinned_run_grades_the_edition_and_says_so(
    tmp_path: Path,
    engine_catalog: Path,
    make_synthetic_repo: Callable[..., Path],
    rendered: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(_consumer(tmp_path, make_synthetic_repo)) == 0

    footer = capsys.readouterr().out.splitlines()[-1]
    assert footer.startswith(f"  sample: {SAMPLE_ID} via fake")
    assert footer.endswith(_PINNED_NOTE)
    (text,) = rendered
    assert text.startswith(FROZEN_PROMPT_BODY)


def test_a_pinned_run_ignores_a_local_override(
    tmp_path: Path,
    engine_catalog: Path,
    make_synthetic_repo: Callable[..., Path],
    rendered: list[str],
) -> None:
    write_local_rule_override(engine_catalog)

    _run(_consumer(tmp_path, make_synthetic_repo))

    (text,) = rendered
    assert FROZEN_RULE_BODY.strip() in text
    assert OVERRIDE_RULE_BODY.strip() not in text


def test_edition_head_grades_the_current_text(
    tmp_path: Path,
    engine_catalog: Path,
    make_synthetic_repo: Callable[..., Path],
    rendered: list[str],
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert _run(_consumer(tmp_path, make_synthetic_repo), "--edition", "head") == 0

    footer = capsys.readouterr().out.splitlines()[-1]
    assert footer.endswith("graded head")
    (text,) = rendered
    assert FROZEN_PROMPT_BODY.strip() not in text


def test_the_json_report_records_the_graded_source(
    tmp_path: Path,
    engine_catalog: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    _run(_consumer(tmp_path, make_synthetic_repo), "--format", "json")

    graded = json.loads(capsys.readouterr().out)["graded"]
    edition = load_edition(engine_catalog / "editions" / TAG)
    assert graded["source"] == TAG
    assert graded["prompt_digest"] == artifact_digest(edition.prompt("review"))
    assert set(graded) == {"source", "prompt_digest", "sample_digest", "engine_version"}


def test_a_pin_to_a_missing_edition_cannot_be_scored(
    tmp_path: Path,
    engine_catalog: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    shutil.rmtree(engine_catalog / "editions")

    assert _run(_consumer(tmp_path, make_synthetic_repo)) == 2

    assert "no edition" in capsys.readouterr().err
