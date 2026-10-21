"""Malformed rule frontmatter is a finding naming the file, never a traceback (prU D21).

``playbook validate`` collects every rule load error (an unknown or missing key,
no ``---`` fence, a non-mapping frontmatter) and every shape error (``scope``,
``priority``, ``section``) as ``FAIL <path>: ...`` lines; sync, check and render
stop on a load error with ``error: <path>: <problem>`` and exit 2.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

_ALLOWED = (
    "allowed keys: id, name, description, scope, version, globs, applies_if, "
    "priority, tags, lint_codes, skill, section"
)


def _write_rule(repo: Path, name: str, extra_yaml: str, *, scope: str = "always") -> Path:
    path = repo / "playbook" / "rules" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {name}\nname: R\ndescription: d\nscope: {scope}\n{extra_yaml}---\nBody\n",
        encoding="utf-8",
    )
    return path


def _validate(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, list[str], str]:
    rc = main(["validate", "--repo-root", str(repo)])
    captured = capsys.readouterr()
    fails = [line for line in captured.out.splitlines() if line.startswith("FAIL ")]
    return rc, fails, captured.err


def test_validate_reports_an_unknown_key_naming_the_file_and_allowed_keys(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = _write_rule(repo, "x", "impact: HIGH\n")

    rc, fails, err = _validate(repo, capsys)

    assert rc == 1
    assert fails == [f"FAIL {rule}: unknown frontmatter key 'impact'; {_ALLOWED}"]
    assert "Traceback" not in err


def test_validate_reports_every_malformed_rule_file(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    first = _write_rule(repo, "a", "impact: HIGH\n")
    second = repo / "playbook" / "rules" / "b.md"
    second.write_text("no fence\n", encoding="utf-8")

    rc, fails, _ = _validate(repo, capsys)

    assert rc == 1
    assert [line.split(": ")[0] for line in fails] == [f"FAIL {first}", f"FAIL {second}"]


@pytest.mark.parametrize("command", [["sync"], ["check"], ["render", "x"]])
def test_commands_exit_two_with_an_error_line_naming_the_file(
    command: list[str],
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = _write_rule(repo, "x", "impact: HIGH\n")

    rc = main([*command, "--repo-root", str(repo)])
    err = capsys.readouterr().err

    assert rc == 2
    assert f"error: {rule}: unknown frontmatter key 'impact'" in err
    assert "Traceback" not in err


@pytest.mark.parametrize(
    ("extra_yaml", "scope", "message"),
    [
        ("", "Scoped", "scope: expected 'always' or 'scoped', got 'Scoped'"),
        ("priority: high\n", "always", "priority: expected an int in 0-99, got 'high'"),
        ("priority: true\n", "always", "priority: expected an int in 0-99, got True"),
        ("priority: -1\n", "always", "priority: expected an int in 0-99, got -1"),
        ("priority: 100\n", "always", "priority: expected an int in 0-99, got 100"),
        (
            "section: Error Handling\n",
            "always",
            "section: expected a kebab-case string (e.g. 'error-handling'), got 'Error Handling'",
        ),
    ],
)
def test_validate_reports_a_bad_shape_naming_the_value(
    extra_yaml: str,
    scope: str,
    message: str,
    tmp_path: Path,
    make_synthetic_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = _write_rule(repo, "x", extra_yaml, scope=scope)

    rc, fails, err = _validate(repo, capsys)

    assert rc == 1
    assert f"FAIL {rule}: {message}" in fails
    assert "Traceback" not in err


def test_validate_accepts_a_section_and_the_priority_bounds(
    tmp_path: Path, make_synthetic_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    _write_rule(repo, "low", "priority: 0\nsection: error-handling\n")
    _write_rule(repo, "high", "priority: 99\n")

    rc, fails, _ = _validate(repo, capsys)

    assert (rc, fails) == (0, [])
