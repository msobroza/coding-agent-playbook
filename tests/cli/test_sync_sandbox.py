"""A template the Jinja sandbox rejects aborts ``playbook sync`` cleanly (prK §P1).

Every template a sync executes — rule bodies, prompt bodies and the rules a
prompt inlines through ``includes_rules`` — runs before the first adapter
write, so a sandbox violation exits 1 naming the source file repo-relative,
with nothing written and no traceback. ``playbook render`` reports it the same
way.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.commands import render as _render
from coding_agent_playbook.commands import sync as _sync
from tests.fakes import FakeGitClient

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]

_ESCAPE_BODY = '{{ lipsum.__globals__["os"].__name__ }}\n'


def _write_templated_rule(repo: Path, rule_id: str, body: str) -> Path:
    """Write a repo-local ``.md.j2`` rule (rendered through Jinja) and return its path."""
    target = repo / "playbook" / "rules" / f"{rule_id}.md.j2"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"---\nid: {rule_id}\nname: Templated\ndescription: d\nscope: always\npriority: 50\n"
        f"---\n{body}",
        encoding="utf-8",
    )
    return target


def _tree_snapshot(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (repo-relative posix path -> bytes)."""
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def _assert_reported(err: str, rel: str, tmp_path: Path) -> None:
    assert f"error: {rel}:" in err
    assert "unsafe" in err  # jinja2's SecurityError detail is surfaced
    assert str(tmp_path) not in err  # named repo-relative, never by absolute path
    assert "Traceback" not in err


def test_sync_fails_loudly_on_sandbox_violation(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path, rules=[("benign", "Benign body.\n")])
    _write_templated_rule(repo, "escape", _ESCAPE_BODY)
    before = _tree_snapshot(repo)
    rc = _sync.execute(repo, git=FakeGitClient())
    assert rc == 1
    err = capsys.readouterr().err
    _assert_reported(err, "playbook/rules/escape.md.j2", tmp_path)
    assert "no files were written" in err
    assert _tree_snapshot(repo) == before  # nothing written, no lockfile, no .gitignore


@pytest.mark.parametrize("mode", [{"check": True}, {"check_staged": True}])
def test_sync_check_modes_fail_loudly_on_sandbox_violation(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
    mode: dict[str, bool],
) -> None:
    """The check modes read inputs in place: the error names the repo file."""
    repo = make_synthetic_repo(tmp_path)
    assert _sync.execute(repo, git=FakeGitClient()) == 0
    _write_templated_rule(repo, "escape", _ESCAPE_BODY)
    before = _tree_snapshot(repo)
    capsys.readouterr()
    rc = _sync.execute(
        repo,
        git=FakeGitClient(staged=["AGENTS.md"]),
        check=mode.get("check", False),
        check_staged=mode.get("check_staged", False),
    )
    assert rc == 1
    err = capsys.readouterr().err
    _assert_reported(err, "playbook/rules/escape.md.j2", tmp_path)
    assert "playbook-sync-check-" not in err  # never the deleted scratch path
    assert _tree_snapshot(repo) == before


def test_sandbox_violation_in_included_rule_aborts_before_any_write(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Regression: a rule whose escape fires only in the ``includes_rules`` render
    (facts-only context, inside an adapter's ``write_prompt``) crashed sync with a
    raw ``SecurityError`` after AGENTS.md and four commands were already written."""
    repo = make_synthetic_repo(
        tmp_path, prompts=[("tidy", {"body": "Tidy up.\n", "includes_rules": ["gated"]})]
    )
    _write_templated_rule(
        repo,
        "gated",
        "{% if project_name is not defined %}"
        '{{ lipsum.__globals__["os"].__name__ }}{% endif %}ok\n',
    )
    before = _tree_snapshot(repo)
    rc = _sync.execute(repo, git=FakeGitClient())
    assert rc == 1
    _assert_reported(capsys.readouterr().err, "playbook/rules/gated.md.j2", tmp_path)
    assert _tree_snapshot(repo) == before


def test_render_reports_sandbox_violation(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """``playbook render <prompt>`` renders every applicable rule: one escaping rule
    exits 1 naming its file instead of an uncaught traceback."""
    repo = make_synthetic_repo(tmp_path, prompts=[("tidy", {"body": "Tidy up.\n"})])
    _write_templated_rule(repo, "escape", _ESCAPE_BODY)
    args = argparse.Namespace(
        repo_root=str(repo), id="tidy", format=None, show_source=False, show_rules=False
    )
    assert _render.run(args) == 1
    err = capsys.readouterr().err
    _assert_reported(err, "playbook/rules/escape.md.j2", tmp_path)
    assert "playbook render aborted." in err
