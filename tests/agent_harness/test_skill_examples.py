"""A skill's ``examples/`` survives the harness round trip (prU D48, D58).

``examples/`` is a synced skill directory like ``scripts/`` and ``references/``:
the ``agent_harness`` adapter byte-copies it into ``skills/<id>/examples/``, and
importing the harness back (with or without the sidecar manifest) writes it to
the canonical ``skills/<id>/examples/`` again, nested directories included. The
harness tree is no dot-directory, so ``skills/conftest.py`` keeps a consumer's
pytest out of the examples. A file a failed ``applies_if`` withholds is written
by neither skill writer, under ``scripts/`` as under ``examples/``.
"""

from __future__ import annotations

import dataclasses
import os
import shutil
import subprocess
import sys
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.agent_harness.adapter import AgentHarnessAdapter
from coding_agent_playbook.agent_harness.importer import import_harness, write_import
from coding_agent_playbook.agent_harness.manifest import read_manifest
from coding_agent_playbook.artifacts.skill import Skill

if TYPE_CHECKING:
    from pathlib import Path

#: Example-relative path -> bytes of the pricing-app example's files.
_EXAMPLE_FILES: Final = {
    "pricing-app/pyproject.toml": b'[project]\nname = "pricing-app"\n',
    "pricing-app/app/main.py": b"def price() -> int:\n    return 1\n",
    "pricing-app/tests/test_price.py": b"import pricing_only_dep\n\n\ndef test_price():\n    pass\n",
}


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root``, by root-relative POSIX path."""
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in root.rglob("*")
        if path.is_file()
    }


def _write(root: Path, files: dict[str, bytes]) -> Path:
    for relative, data in files.items():
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_bytes(data)
    return root


def _skill(tmp_path: Path, **fields: object) -> Skill:
    """The ``pricing`` skill whose ``examples/`` holds the pricing-app example."""
    skill = Skill(
        frontmatter={"id": "pricing", "name": "pricing", "description": "Pricing conventions."},
        body="# Pricing\n",
        scripts_dir=None,
        references_dir=None,
        source_package="test",
        examples_dir=_write(tmp_path / "src_examples", _EXAMPLE_FILES),
    )
    return dataclasses.replace(skill, **fields)  # type: ignore[arg-type]


def _emit(tmp_path: Path, skill: Skill | None = None) -> Path:
    """Emit a harness holding ``skill`` (by default the pricing skill with its example)."""
    harness = tmp_path / "harness"
    harness.mkdir()
    adapter = AgentHarnessAdapter()
    adapter.write_skill(skill if skill is not None else _skill(tmp_path), harness)
    adapter.finalize(harness)
    return harness


def test_agent_harness_copies_a_skill_examples_dir(tmp_path: Path) -> None:
    harness = _emit(tmp_path)

    assert _tree(harness / "skills" / "pricing" / "examples") == _EXAMPLE_FILES


@pytest.mark.parametrize("sidecar", [True, False], ids=["lossless", "best-effort"])
def test_harness_import_writes_the_examples_dir_back(tmp_path: Path, sidecar: bool) -> None:
    harness = _emit(tmp_path)
    if not sidecar:
        shutil.rmtree(harness / ".playbook")

    write_import(import_harness(harness), tmp_path / "playbook")

    imported = tmp_path / "playbook" / "skills"
    assert _tree(imported / "pricing" / "examples") == _EXAMPLE_FILES
    assert not (imported / "conftest.py").exists()


def _consumer_pytest(repo: Path) -> subprocess.CompletedProcess[str]:
    """Run a consumer's plain ``pytest`` (no testpaths) at ``repo``, plugins off."""
    (repo / "pytest.ini").write_text("[pytest]\n", encoding="utf-8")
    _write(repo, {"tests/test_consumer.py": b"def test_consumer():\n    pass\n"})
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", str(repo)],
        cwd=repo,
        capture_output=True,
        text=True,
        check=False,
        env={**os.environ, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
        timeout=120,
    )


def test_a_consumer_pytest_run_never_collects_a_harness_example(tmp_path: Path) -> None:
    """D48: the example's test imports a dependency only its own environment has."""
    harness = _emit(tmp_path)
    assert (harness / "skills" / "conftest.py").is_file()

    run = _consumer_pytest(harness)

    assert run.returncode == 0, run.stdout + run.stderr
    assert "1 passed" in run.stdout and "pricing_only_dep" not in run.stdout


def test_without_an_example_the_harness_writes_no_conftest(tmp_path: Path) -> None:
    harness = _emit(tmp_path, _skill(tmp_path, examples_dir=None))

    assert not (harness / "skills" / "conftest.py").exists()


def test_the_conftest_is_stale_once_no_example_is_left(tmp_path: Path) -> None:
    """It sits outside every skill dir and carries the sentinel, so the stale scan settles it."""
    harness = _emit(tmp_path)

    stale = AgentHarnessAdapter().stale_outputs(set(), harness)

    assert harness / "skills" / "conftest.py" in stale


def test_the_harness_does_not_write_a_withheld_script(tmp_path: Path) -> None:
    """D48, D58: the harness copies scripts/ through published_skill_files, like SkillWriter."""
    scripts = _write(tmp_path / "src_scripts", {"kept.py": b"x = 1\n", "gated.py": b"y = 2\n"})
    skill = _skill(tmp_path, scripts_dir=scripts, withheld_paths=("scripts/gated.py",))

    harness = _emit(tmp_path, skill)

    assert _tree(harness / "skills" / "pricing" / "scripts") == {"kept.py": b"x = 1\n"}
    manifest = read_manifest(harness)
    assert manifest is not None
    [entry] = [e for e in manifest.entries if e.kind == "skill"]
    assert [script.path for script in entry.scripts] == ["skills/pricing/scripts/kept.py"]
