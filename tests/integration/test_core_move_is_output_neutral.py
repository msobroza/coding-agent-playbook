"""prU L0-07: moving the core-layer scoped rules into their skills changes no synced byte.

Temporary, until L0-15 gives the moved rules sections and priorities (it then
deletes this module and its digest list, F-02). The reference probe's synced
core-skill files (each adapter's ``skills/<core skill>/SKILL.md`` and
``rules/**``), its Continue rules and its ``AGENTS.md`` must hash to the
digests committed in ``tests/fixtures/core_move_probe_digests.json``, which
were taken from the probe synced before the move.

A later ticket that changes this output on purpose (a rendering change, a new
rule in core) updates the digest list: the failure message lists every path whose
digest differs, with its new digest.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Final

import pytest

from tests._catalog import REPO_ROOT, core_skill_ids

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

DIGESTS_PATH: Final = REPO_ROOT / "tests" / "fixtures" / "core_move_probe_digests.json"
#: The adapter skill roots the reference probe writes (claude_code, opencode, shared_skills).
_SKILL_ROOTS: Final = (".claude/skills", ".opencode/skills", ".agents/skills")


def _compared_files(repo: Path) -> list[Path]:
    """The synced files the move could change: core skills, Continue rules, ``AGENTS.md``."""
    files = [repo / "AGENTS.md", *(repo / ".continue" / "rules").rglob("*")]
    for root in _SKILL_ROOTS:
        for skill_id in core_skill_ids():
            skill_dir = repo / root / skill_id
            files.extend([skill_dir / "SKILL.md", *(skill_dir / "rules").rglob("*")])
    return sorted(path for path in files if path.is_file())


def probe_digests(repo: Path) -> dict[str, str]:
    """Repo-relative POSIX path -> sha256 of each compared file of a synced probe.

    Example: ``probe_digests(reference_probe_repo)["AGENTS.md"]`` -> ``"65f0eab4..."``.
    """
    return {
        path.relative_to(repo).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in _compared_files(repo)
    }


def test_reference_probe_output_matches_the_pre_move_digests(reference_probe_repo: Path) -> None:
    expected: dict[str, str] = json.loads(DIGESTS_PATH.read_text(encoding="utf-8"))
    actual = probe_digests(reference_probe_repo)

    assert sorted(actual) == sorted(expected), (
        f"synced files differ: missing {sorted(set(expected) - set(actual))}, "
        f"new {sorted(set(actual) - set(expected))}"
    )
    changed = {path: digest for path, digest in actual.items() if expected[path] != digest}
    assert not changed, f"synced bytes changed; new digests: {json.dumps(changed, indent=1)}"
