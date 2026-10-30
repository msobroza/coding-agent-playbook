"""The consumer wheel never ships a release's answers files (ADR 0014).

``catalog/releases/<v>/answers/*.jsonl.gz`` holds about 1 MB per target per
release. Only the engine's release flow reads them, from a checkout, so the
wheel drops them. Hatch's ``force-include`` ignores ``exclude``, so the catalog
reaches the wheel through a ``sources`` mapping instead, where ``exclude``
applies. The CI wheel-smoke parity step compares the wheel's ``_catalog/`` with
``git ls-files catalog``, so it must drop the same paths from the tracked set.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
ANSWERS_GLOB = "catalog/releases/*/answers"
PARITY_STEP = "The wheel's _catalog/ equals the tracked catalog/ tree"


def _wheel_target() -> dict[str, Any]:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    target: dict[str, Any] = data["tool"]["hatch"]["build"]["targets"]["wheel"]
    return target


def _parity_script() -> str:
    workflow = yaml.safe_load((ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8"))
    steps = [s for job in workflow["jobs"].values() for s in job.get("steps", [])]
    step = next((s for s in steps if s.get("name") == PARITY_STEP), None)
    assert step is not None, f"no CI step named {PARITY_STEP!r}"
    return str(step["run"])


def test_the_wheel_excludes_answers_files() -> None:
    target = _wheel_target()

    assert ANSWERS_GLOB in target["exclude"], target.get("exclude")
    assert target["sources"]["catalog"] == "coding_agent_playbook/_catalog"
    assert "catalog" in target["only-include"], target.get("only-include")
    # Editable installs refuse a prefix-adding mapping without explicit dirs.
    assert target["dev-mode-dirs"] == ["src"], target.get("dev-mode-dirs")


def test_the_catalog_is_not_force_included() -> None:
    # force-include would bypass the exclude above and ship every answers file.
    forced = _wheel_target().get("force-include", {})

    assert "catalog" not in forced, forced


def test_the_parity_step_drops_tracked_answers_files() -> None:
    script = _parity_script()

    assert 'fnmatch.fnmatch(path, "releases/*/answers/*")' in script, script
