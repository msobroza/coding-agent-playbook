"""``playbook sync`` renders the prompt set the ``prompts`` key selects (D76; prU L0-24).

A synthetic consumer repo ships a repo-local prompt in ``playbook/prompts/`` and its
v2 twin in ``playbook/prompts/v2/``. ``prompts = "v2"`` changes the rendered text
only; without the key every output is byte-identical to a repo with no v2 set.
"""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from coding_agent_playbook.commands import sync as sync_cmd
from coding_agent_playbook.commands import validate as validate_cmd
from tests.conftest import _DEFAULT_CONFIG, _write_prompt

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    import pytest

    SyntheticRepoFactory = Callable[..., Path]

_V1_BODY = "Tidy up the code, version one.\n"
_V2_BODY = "Tidy up the code, version two: load the python-coding skill first.\n"

#: Inputs of the sync, not its outputs: left out of the output snapshot.
_INPUTS = ("playbook", "pyproject.toml", ".coding-agent-playbook.toml")


def _ns(repo: Path) -> argparse.Namespace:
    return argparse.Namespace(repo_root=str(repo), check=False)


def _repo(
    root: Path,
    make_synthetic_repo: SyntheticRepoFactory,
    *,
    prompts_line: str = "",
    with_v2: bool = True,
) -> Path:
    root.mkdir()
    repo = make_synthetic_repo(
        root,
        config_text=prompts_line + _DEFAULT_CONFIG,
        prompts=[("tidy-up", {"slash": "tidy-up", "body": _V1_BODY})],
    )
    if with_v2:
        _write_prompt(
            repo / "playbook" / "prompts" / "v2" / "tidy-up.md",
            "tidy-up",
            slash="tidy-up",
            body=_V2_BODY,
        )
    return repo


def _outputs(repo: Path) -> dict[str, bytes]:
    """Every file sync wrote, by repo-relative path; the lockfile without its timestamp."""
    return {
        path.relative_to(repo).as_posix(): _without_timestamp(path.read_bytes())
        for path in sorted(repo.rglob("*"))
        if path.is_file() and path.relative_to(repo).parts[0] not in _INPUTS
    }


def _without_timestamp(content: bytes) -> bytes:
    """``content`` minus the lockfile's ``rendered_at`` line, the one per-run value."""
    return b"".join(
        line for line in content.splitlines(keepends=True) if not line.startswith(b"rendered_at =")
    )


def test_prompts_v2_renders_v2_text_under_the_same_command_names(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    v1 = _repo(tmp_path / "v1", make_synthetic_repo)
    v2 = _repo(tmp_path / "v2", make_synthetic_repo, prompts_line='prompts = "v2"\n')

    assert sync_cmd.run(_ns(v1)) == 0
    assert sync_cmd.run(_ns(v2)) == 0

    v1_outputs, v2_outputs = _outputs(v1), _outputs(v2)
    assert sorted(v2_outputs) == sorted(v1_outputs)
    for command in (".claude/commands/tidy-up.md", ".opencode/command/tidy-up.md"):
        assert "version two" in v2_outputs[command].decode("utf-8")
        assert "version one" not in v2_outputs[command].decode("utf-8")
        assert "version one" in v1_outputs[command].decode("utf-8")


def test_without_a_prompts_key_every_output_is_byte_identical_to_a_repo_without_v2(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory
) -> None:
    with_v2 = _repo(tmp_path / "with", make_synthetic_repo)
    without_v2 = _repo(tmp_path / "without", make_synthetic_repo, with_v2=False)
    pinned_v1 = _repo(tmp_path / "pinned", make_synthetic_repo, prompts_line='prompts = "v1"\n')

    for repo in (with_v2, without_v2, pinned_v1):
        assert sync_cmd.run(_ns(repo)) == 0

    assert _outputs(with_v2) == _outputs(without_v2)
    assert _outputs(pinned_v1) == _outputs(without_v2)


def test_validate_refuses_a_v2_prompt_without_a_v1_twin(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = _repo(tmp_path / "orphan", make_synthetic_repo)
    orphan = repo / "playbook" / "prompts" / "v2" / "orphan.md"
    _write_prompt(orphan, "orphan", slash="orphan")

    assert validate_cmd.run(argparse.Namespace(repo_root=str(repo))) == 1
    assert f"{orphan}: v2 prompt 'orphan' has no v1 twin" in capsys.readouterr().out


def test_validate_checks_the_unrendered_v2_set_like_the_rendered_one(
    tmp_path: Path, make_synthetic_repo: SyntheticRepoFactory, capsys: pytest.CaptureFixture[str]
) -> None:
    """Under the default v1 the v2 twins are not rendered, yet a broken one still fails."""
    repo = _repo(tmp_path / "broken", make_synthetic_repo, with_v2=False)
    twin = repo / "playbook" / "prompts" / "v2" / "tidy-up.md"
    twin.parent.mkdir(parents=True)
    twin.write_text(
        "---\nid: tidy-up\nname: Tidy Up\ndescription: A repo-local prompt\nslash: tidy-up\n"
        "output_contract: ['(']\n---\n{{ rule('pytest') }}\n",
        encoding="utf-8",
    )

    assert validate_cmd.run(argparse.Namespace(repo_root=str(repo))) == 1
    out = capsys.readouterr().out
    assert f'{twin}: body calls {{{{ rule("pytest") }}}}' in out
    assert f"{twin}: output_contract pattern '('" in out
    assert "validation failed with 2 error(s)" in out
