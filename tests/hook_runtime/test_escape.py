"""Kill switches, escape hatches and pragmas (specs/prK-lifecycle-hooks.md §D.7, §B.2).

Hatches come only from the hook process environment, with exact values, and
a hatch that a Claude settings file sets with the same value is ignored: an
agent can edit a settings ``env`` block, but a deliberate human override
belongs in the launching shell. Pragmas count only when already committed.
``PLAYBOOK_HOOK_WRAPPER_PREFIXES`` is read the same way; an entry that would hide
a guarded command is refused (``wrapper_policy``) and reported, never applied.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from coding_agent_playbook.hook_runtime.escape import (
    ALLOW_GENERATED_EDIT_VAR,
    GATE_VAR,
    HOOKS_DISABLE_VAR,
    HOOKS_VAR,
    SETTINGS_MAX_BYTES,
    WRAPPER_PREFIXES_VAR,
    EscapeHatches,
    pragma_at_head,
    read_escape_hatches,
    settings_files,
)
from coding_agent_playbook.hook_runtime.event import RepoInfo
from coding_agent_playbook.hook_runtime.git import GitTimeout
from tests.hook_runtime.fakes import FakeGit

_PROXIES = ("proxy", "proxy run")


def _no_settings() -> tuple[Path, ...]:
    return ()


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({HOOKS_VAR: "off"}, EscapeHatches(hooks_off=True)),
        ({HOOKS_VAR: "OFF"}, EscapeHatches()),
        ({HOOKS_VAR: " off"}, EscapeHatches()),
        ({HOOKS_VAR: "0"}, EscapeHatches()),
        ({GATE_VAR: "off"}, EscapeHatches(gate_off=True)),
        ({GATE_VAR: "false"}, EscapeHatches()),
        ({ALLOW_GENERATED_EDIT_VAR: "1"}, EscapeHatches(allow_generated_edit=True)),
        ({ALLOW_GENERATED_EDIT_VAR: "true"}, EscapeHatches()),
        ({ALLOW_GENERATED_EDIT_VAR: "yes"}, EscapeHatches()),
        ({HOOKS_DISABLE_VAR: "a, b,,c "}, EscapeHatches(disabled_ids=frozenset({"a", "b", "c"}))),
        ({HOOKS_DISABLE_VAR: " , "}, EscapeHatches()),
        ({"PLAYBOOK_OTHER": "off"}, EscapeHatches()),
        ({WRAPPER_PREFIXES_VAR: "proxy, proxy  run"}, EscapeHatches(wrapper_prefixes=_PROXIES)),
        ({WRAPPER_PREFIXES_VAR: " , "}, EscapeHatches()),
        (
            {WRAPPER_PREFIXES_VAR: "git,proxy,proxy run,sudo"},
            EscapeHatches(wrapper_prefixes=_PROXIES, rejected_wrappers=("git", "sudo")),
        ),
        ({WRAPPER_PREFIXES_VAR: "rm"}, EscapeHatches(rejected_wrappers=("rm",))),
    ],
)
def test_hatches_require_exact_values(env: dict[str, str], expected: EscapeHatches) -> None:
    assert read_escape_hatches(env, settings_files=_no_settings) == expected


def test_used_names_every_hatch_in_effect_for_the_decision_log() -> None:
    env = {
        HOOKS_VAR: "off",
        GATE_VAR: "off",
        HOOKS_DISABLE_VAR: "x",
        ALLOW_GENERATED_EDIT_VAR: "1",
        WRAPPER_PREFIXES_VAR: "proxy",
    }

    hatches = read_escape_hatches(env, settings_files=_no_settings)

    assert hatches.used == (
        ALLOW_GENERATED_EDIT_VAR,
        GATE_VAR,
        HOOKS_VAR,
        HOOKS_DISABLE_VAR,
        WRAPPER_PREFIXES_VAR,
    )
    assert EscapeHatches().used == ()


def test_disable_never_skips_a_mandatory_hook() -> None:
    hatches = read_escape_hatches({HOOKS_DISABLE_VAR: "guard,quality"}, settings_files=_no_settings)

    assert hatches.skips("quality", mandatory=False)
    assert not hatches.skips("guard", mandatory=True)
    assert not hatches.skips("other", mandatory=False)


def test_settings_are_read_only_when_a_hatch_is_present() -> None:
    def explode() -> tuple[Path, ...]:
        raise AssertionError("settings files read on the hot path")

    assert read_escape_hatches({"PATH": "/bin"}, settings_files=explode) == EscapeHatches()


def _write_settings(path: Path, document: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def test_hatch_defined_in_settings_env_is_ignored_and_reported(tmp_path: Path) -> None:
    settings = _write_settings(
        tmp_path / ".claude" / "settings.json",
        {"env": {GATE_VAR: "off", HOOKS_DISABLE_VAR: "x", "OTHER": 1}},
    )
    env = {GATE_VAR: "off", HOOKS_DISABLE_VAR: "y", HOOKS_VAR: "off"}

    hatches = read_escape_hatches(env, settings_files=lambda: (settings,))

    assert not hatches.gate_off  # same value as the settings file: ignored
    assert hatches.via_settings_env == (GATE_VAR,)
    assert hatches.disabled_ids == frozenset({"y"})  # a different value is the shell's own
    assert hatches.hooks_off


@pytest.mark.parametrize("content", ["{not json", "[1]", '{"env": [1]}', '{"env": {"X": 1}}'])
def test_unreadable_settings_files_are_skipped(tmp_path: Path, content: str) -> None:
    broken = tmp_path / "settings.json"
    broken.write_text(content, encoding="utf-8")

    hatches = read_escape_hatches(
        {GATE_VAR: "off"}, settings_files=lambda: (broken, tmp_path / "absent.json")
    )

    assert hatches.gate_off and hatches.via_settings_env == ()


def test_settings_files_cover_project_local_main_checkout_and_user(tmp_path: Path) -> None:
    main = tmp_path / "main"
    feat = tmp_path / "feat"
    repo = RepoInfo(
        worktree_root=str(feat),
        git_dir=str(main / ".git" / "worktrees" / "feat"),
        common_dir=str(main / ".git"),
        is_linked_worktree=True,
        sibling_roots=(str(main),),
    )

    files = settings_files(
        repo, project_dir=str(feat), env={"CLAUDE_CONFIG_DIR": "/cfg"}, home="/home/dev"
    )

    assert files == (
        feat / ".claude" / "settings.json",
        feat / ".claude" / "settings.local.json",
        main / ".claude" / "settings.local.json",
        Path("/cfg") / "settings.json",
    )
    default_user = settings_files(None, project_dir=str(feat), env={}, home="/home/dev")
    assert default_user[-1] == Path("/home/dev/.claude/settings.json")
    assert len(default_user) == 3


def test_settings_local_of_the_main_checkout_ignores_a_hatch(tmp_path: Path) -> None:
    main = tmp_path / "main"
    _write_settings(main / ".claude" / "settings.local.json", {"env": {HOOKS_VAR: "off"}})
    repo = RepoInfo(
        worktree_root=str(tmp_path / "feat"),
        git_dir=str(main / ".git" / "worktrees" / "feat"),
        common_dir=str(main / ".git"),
        is_linked_worktree=True,
    )
    home = str(tmp_path / "home")

    hatches = read_escape_hatches(
        {HOOKS_VAR: "off"},
        settings_files=lambda: settings_files(
            repo, project_dir=repo.worktree_root, env={}, home=home
        ),
    )

    assert not hatches.hooks_off and hatches.via_settings_env == (HOOKS_VAR,)


def test_pragma_honored_only_when_present_at_head() -> None:
    git = FakeGit(head_blobs={"src/a.py": b"import os\nTOKEN = x  # playbook: allow-secret\n"})
    line = "    TOKEN = x  # playbook: allow-secret   "

    assert pragma_at_head(git, "src/a.py", line)
    assert not pragma_at_head(git, "src/a.py", "NEW = y  # playbook: allow-secret")
    assert not pragma_at_head(git, "src/new.py", line)  # absent at HEAD: not honored
    assert not pragma_at_head(git, "src/a.py", "   ")
    assert [call[0] for call in git.calls] == ["cat_head", "cat_head", "cat_head"]


def test_pragma_check_timeout_reaches_the_failure_policy() -> None:
    git = FakeGit(errors={"cat_head": GitTimeout("git cat-file exceeded its 2.0 s timeout")})

    with pytest.raises(GitTimeout):
        pragma_at_head(git, "a.py", "x  # playbook: allow-secret")


def test_an_oversized_settings_file_ignores_every_present_hatch(tmp_path: Path) -> None:
    # Claude still applies the env of a huge settings file, so skipping it
    # would let padding smuggle a hatch through: fail safe instead.
    huge = tmp_path / "settings.json"
    huge.write_bytes(b'{"pad": "' + b"x" * SETTINGS_MAX_BYTES + b'"}')

    hatches = read_escape_hatches(
        {GATE_VAR: "off", HOOKS_VAR: "off"}, settings_files=lambda: (huge,)
    )

    assert not hatches.gate_off and not hatches.hooks_off
    assert hatches.via_settings_env == (GATE_VAR, HOOKS_VAR)


def test_a_wrapper_declared_in_settings_env_is_ignored_like_a_hatch(tmp_path: Path) -> None:
    settings = _write_settings(
        tmp_path / ".claude" / "settings.local.json", {"env": {WRAPPER_PREFIXES_VAR: "proxy"}}
    )

    same = read_escape_hatches({WRAPPER_PREFIXES_VAR: "proxy"}, settings_files=lambda: (settings,))
    own = read_escape_hatches({WRAPPER_PREFIXES_VAR: "rewrap"}, settings_files=lambda: (settings,))

    assert same.wrapper_prefixes == () and same.via_settings_env == (WRAPPER_PREFIXES_VAR,)
    assert own.wrapper_prefixes == ("rewrap",) and own.via_settings_env == ()


def test_only_refused_wrappers_never_read_the_settings_files() -> None:
    def explode() -> tuple[Path, ...]:
        raise AssertionError("settings files read although nothing takes effect")

    hatches = read_escape_hatches({WRAPPER_PREFIXES_VAR: "git"}, settings_files=explode)

    assert hatches == EscapeHatches(rejected_wrappers=("git",))
    assert hatches.used == ()
