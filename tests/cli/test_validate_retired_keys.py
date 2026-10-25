"""Retired bookkeeping keys are refused, naming the file and what replaced them (#281, #285).

Rules, prompts, hooks and eval samples no longer carry ``version:`` (the engine
computes a content digest), and prompts no longer list ``eval_samples:`` (a
prompt's samples are the ones whose ``prompt_id`` names it). ``sample.toml``
rejects any unknown top-level key, so a misspelled key cannot pass silently.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    SyntheticRepoFactory = Callable[..., Path]
    HookFactory = Callable[..., Path]

_DIGEST_HINT = "the engine now computes a content digest"
_SAMPLES_HINT = "a prompt's eval samples are the samples whose prompt_id names it"

_SAMPLE_TOML = """\
id = "{prompt}-case"
prompt_id = "{prompt}"
description = "d"
{extra}
[setup]
files = []

[invocation]
prompt_args = ""

[gate]
expr = "ok"

[gate.bind]
ok = {{ check = "file_exists", path = "x.py" }}

[verdict]
trial = "gate"
"""


def _validate(repo: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    rc = main(["validate", "--repo-root", str(repo)])
    captured = capsys.readouterr()
    return rc, captured.out + captured.err


def _write_prompt(repo: Path, prompt_id: str, extra_yaml: str = "") -> Path:
    path = repo / "playbook" / "prompts" / f"{prompt_id}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"---\nid: {prompt_id}\nname: P\ndescription: d\nslash: {prompt_id}\n{extra_yaml}---\nB\n",
        encoding="utf-8",
    )
    return path


def _write_sample(repo: Path, prompt_id: str, extra_toml: str) -> Path:
    path = repo / "playbook" / "eval_samples" / f"{prompt_id}-case" / "sample.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_SAMPLE_TOML.format(prompt=prompt_id, extra=extra_toml), encoding="utf-8")
    return path


def test_a_rule_with_version_fails_naming_the_file_and_the_digest(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    rule = repo / "playbook" / "rules" / "x.md"
    rule.parent.mkdir(parents=True)
    rule.write_text(
        "---\nid: x\nname: X\ndescription: d\nscope: always\nversion: 1\n---\nB\n",
        encoding="utf-8",
    )

    rc, output = _validate(repo, capsys)

    assert rc == 1
    assert f"FAIL {rule}: retired key 'version': {_DIGEST_HINT}" in output


@pytest.mark.parametrize(
    ("extra_yaml", "key", "hint"),
    [
        ("version: 1\n", "version", _DIGEST_HINT),
        ("eval_samples:\n  - p-case\n", "eval_samples", _SAMPLES_HINT),
    ],
)
def test_a_prompt_with_a_retired_key_fails_naming_the_file_and_the_replacement(
    extra_yaml: str,
    key: str,
    hint: str,
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    prompt = _write_prompt(repo, "p", extra_yaml)

    rc, output = _validate(repo, capsys)

    assert rc == 2
    assert f"error: {prompt}: retired key {key!r}: {hint}" in output
    assert "Traceback" not in output


def test_a_prompt_with_an_unknown_key_fails_listing_the_allowed_keys(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    prompt = _write_prompt(repo, "p", "impact: HIGH\n")

    rc, output = _validate(repo, capsys)

    assert rc == 2
    assert f"error: {prompt}: unknown frontmatter key 'impact'; allowed keys: id," in output


def test_a_hook_with_version_fails_naming_the_file_and_the_digest(
    tmp_path: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    make_hook: HookFactory,
    capsys: pytest.CaptureFixture[str],
) -> None:
    repo = make_synthetic_repo(tmp_path)
    hook = make_hook(repo / "playbook" / "hooks", "guard-x", version=1)

    rc, output = _validate(repo, capsys)

    assert rc == 1
    assert str(hook.parent) in output or str(hook) in output
    assert f"retired key 'version': {_DIGEST_HINT}" in output


def test_a_sample_with_version_fails_naming_the_file_and_the_digest(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    _write_prompt(repo, "p")
    sample = _write_sample(repo, "p", "version = 1\n")

    rc, output = _validate(repo, capsys)

    assert rc == 1
    assert f"FAIL {sample}: {sample}: retired key 'version': {_DIGEST_HINT}" in output


def test_a_sample_with_an_unknown_top_level_key_fails_naming_the_key(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    _write_prompt(repo, "p")
    sample = _write_sample(repo, "p", 'editon = "v0.1.0"\n')

    rc, output = _validate(repo, capsys)

    assert rc == 1
    assert f"FAIL {sample}: {sample}: unknown top-level key 'editon'; allowed keys: id," in output


def test_a_prompt_whose_sample_names_it_validates_without_a_list(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = make_synthetic_repo(tmp_path)
    _write_prompt(repo, "p")
    _write_sample(repo, "p", "")

    rc, output = _validate(repo, capsys)

    assert rc == 0, output
