"""Tests for ``playbook check`` (PR 10 Task 5)."""

from __future__ import annotations

import argparse
import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import check as _check
from coding_agent_playbook.commands import sync as _sync

if TYPE_CHECKING:
    from pathlib import Path


def _ns(repo: Path, **kwargs: object) -> argparse.Namespace:
    base: dict[str, object] = {"repo_root": str(repo), "refresh": False}
    base.update(kwargs)
    return argparse.Namespace(**base)


def test_check_prints_all_sections(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(
        tmp_path,
        rules=[("rule-a", "Body a\n")],
        prompts=[("refactor", {"slash": "refactor"})],
    )
    rc = _check.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    assert "=== Environment ===" in out
    assert "=== Detected ===" in out
    assert "=== Artifacts ===" in out
    assert "=== Drift ===" in out
    # SPEC §12.4: applicable artifacts use the unicode tick marker.
    assert "[✓]" in out


def test_check_artifact_section_marks_applies_if(tmp_path, make_synthetic_repo, capsys):
    """A rule with applies_if not matching the facts should show as not-applicable."""
    repo = make_synthetic_repo(tmp_path)
    # Inject a rule with a predicate the facts can't satisfy.
    rules_dir = repo / "playbook" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "scoped.md").write_text(
        "---\n"
        "id: scoped\n"
        "name: Scoped Rule\n"
        "description: Only for repos with Hadoop\n"
        "scope: scoped\n"
        "priority: 50\n"
        "applies_if:\n"
        "  has_framework:\n"
        "    - some-framework-that-isnt-installed\n"
        "---\n"
        "Body\n",
        encoding="utf-8",
    )
    rc = _check.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    # The rule should appear with the not-applicable marker.
    assert "scoped" in out
    assert "[✗]" in out
    # Skip reason mirrors SPEC §12.4: the failing predicate key is surfaced.
    assert "skipped: applies_if has_framework=" in out
    assert "some-framework-that-isnt-installed" in out


def test_check_drift_section_reports_drift(tmp_path, make_synthetic_repo, capsys):
    repo = make_synthetic_repo(tmp_path, rules=[("x", "Body\n")])
    sync_args = argparse.Namespace(repo_root=str(repo), check=False)
    _sync.run(sync_args)
    # Mutate AGENTS.md so its hash no longer matches the lockfile entry.
    (repo / "AGENTS.md").write_text("MUTATED\n", encoding="utf-8")
    capsys.readouterr()
    rc = _check.run(_ns(repo))
    assert rc == 0
    out = capsys.readouterr().out
    assert "hash mismatch" in out
    assert "AGENTS.md" in out


def test_check_refresh_updates_detector_cache(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path)
    # Update pyproject after the config was written — the cache should pick
    # up the new dependency once refresh runs.
    (repo / "pyproject.toml").write_text(
        '[project]\nname="x"\nrequires-python=">=3.12"\ndependencies=["fastapi"]\n'
    )
    rc = _check.run(_ns(repo, refresh=True))
    assert rc == 0
    with (repo / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    # fastapi should appear in either dependencies or frameworks after refresh.
    cache = data.get("detector_cache", {})
    assert "fastapi" in (cache.get("dependencies") or {}) or "fastapi" in (
        cache.get("frameworks") or {}
    )


_COMMITTED_WITH_TABLES = """\
schema_version = 1
adapters_enabled = ["continue"]

[project]
name = "synthetic"
kind = "python-library"

[engine]
version = "0.1.0a0"

[user_choices]
docstring_style = "numpy"

[hooks.some-hook]
enabled = false
timeout = 2.5

[links]
allowed_domains = ["agentharnesses.io"]

[metrics.regression.coverage]
max_worsening = 0.5

[metrics.weights]
x = 1.0
"""


def test_refresh_preserves_tables_and_never_persists_local_overrides(tmp_path, make_synthetic_repo):
    repo = make_synthetic_repo(tmp_path, config_text=_COMMITTED_WITH_TABLES)
    (repo / ".coding-agent-playbook.local.toml").write_text(
        '[user_choices]\npersonal = "mine"\n\n[metrics]\nmode = "absolute"\n'
    )
    assert _check.run(_ns(repo, refresh=True)) == 0
    with (repo / ".coding-agent-playbook.toml").open("rb") as f:
        data = tomllib.load(f)
    committed = tomllib.loads(_COMMITTED_WITH_TABLES)
    for key in ("hooks", "links", "metrics", "user_choices"):
        assert data[key] == committed[key], key
    assert "python_version" in data["detector_cache"]
