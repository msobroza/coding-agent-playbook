"""The user-local trust store (specs/prK-lifecycle-hooks.md §B.4).

``TrustStore`` takes its path, clock and git-common-dir resolver as parameters,
so no test reads the developer's real store or environment. The one real-git
test runs under ``hermetic_git_env``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from coding_agent_playbook.security.trust import (
    ExecutionApproval,
    HandlerApproval,
    TrustStore,
    TrustStoreError,
    default_trust_store_path,
    git_common_dir,
    repo_key,
    sha256_of_json,
)
from tests.import_probe import new_modules_after

_HOME = Path("/home/dev")
_WANTED = HandlerApproval(
    source="acme_rules", launcher="python", args_sha256="a" * 64, script_sha256="b" * 64
)
_POSIX_ONLY = pytest.mark.skipif(sys.platform == "win32", reason="POSIX modes and ownership")


def _store(tmp_path: Path, *, repo: Path | None = None, now: float = 0.0) -> TrustStore:
    """A store under ``tmp_path/state`` for a repo at ``tmp_path/repo`` (no git)."""
    repo_root = repo if repo is not None else tmp_path / "repo"
    repo_root.mkdir(exist_ok=True)
    return TrustStore(
        tmp_path / "state" / "coding-agent-playbook" / "trust.json",
        repo_root=repo_root,
        now=lambda: now,
        git_common_dir=lambda _root: None,
    )


# --- default_trust_store_path -----------------------------------------------------


def test_default_path_uses_xdg_state_home() -> None:
    path = default_trust_store_path(
        environ={"XDG_STATE_HOME": "/xdg/state"}, platform="linux", home=_HOME
    )
    assert path == Path("/xdg/state/coding-agent-playbook/trust.json")


def test_default_path_falls_back_to_local_state() -> None:
    path = default_trust_store_path(environ={}, platform="darwin", home=_HOME)
    assert path == _HOME / ".local" / "state" / "coding-agent-playbook" / "trust.json"


def test_default_path_ignores_a_relative_xdg_state_home() -> None:
    # The XDG spec: a relative value is invalid and must be ignored.
    path = default_trust_store_path(
        environ={"XDG_STATE_HOME": "state"}, platform="linux", home=_HOME
    )
    assert path == _HOME / ".local" / "state" / "coding-agent-playbook" / "trust.json"


def test_default_path_windows_localappdata() -> None:
    path = default_trust_store_path(
        environ={"LOCALAPPDATA": "/win/Local", "XDG_STATE_HOME": "/xdg"},
        platform="win32",
        home=_HOME,
    )
    assert path == Path("/win/Local/coding-agent-playbook/trust.json")


def test_default_path_windows_without_localappdata_uses_the_profile() -> None:
    path = default_trust_store_path(environ={}, platform="win32", home=_HOME)
    assert path == _HOME / "AppData" / "Local" / "coding-agent-playbook" / "trust.json"


# --- file system hygiene ------------------------------------------------------------


@_POSIX_ONLY
def test_store_dir_0700_and_file_0600(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.approve_handler("guard-x", _WANTED)

    assert stat.S_IMODE(store.path.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(store.path.stat().st_mode) == 0o600


def test_atomic_write_leaves_no_temp_file(tmp_path: Path) -> None:
    store = _store(tmp_path)

    store.approve_handler("guard-x", _WANTED)
    store.approve_execution("c" * 64)

    assert sorted(p.name for p in store.path.parent.iterdir()) == ["trust.json"]


def test_store_inside_repo_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()

    with pytest.raises(TrustStoreError, match="inside the repository") as caught:
        TrustStore(repo / ".state" / "trust.json", repo_root=repo, git_common_dir=lambda _r: None)

    assert str(repo / ".state" / "trust.json") in str(caught.value)


def test_store_reached_through_a_link_into_the_repo_is_refused(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "approvals").mkdir(parents=True)
    link = tmp_path / "state-link"
    link.symlink_to(repo / "approvals", target_is_directory=True)

    with pytest.raises(TrustStoreError, match="inside the repository"):
        TrustStore(link / "trust.json", repo_root=repo, git_common_dir=lambda _r: None)


# --- repo_key -----------------------------------------------------------------------


def test_repo_key_outside_git_uses_realpath(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(repo, target_is_directory=True)
    expected = hashlib.sha256(os.fsencode(os.path.realpath(repo))).hexdigest()

    assert repo_key(repo, common_dir=lambda _r: None) == expected
    assert repo_key(alias, common_dir=lambda _r: None) == expected


def test_git_common_dir_of_a_plain_checkout_is_its_dot_git(tmp_path: Path) -> None:
    (tmp_path / "repo" / ".git").mkdir(parents=True)
    (tmp_path / "repo" / "src").mkdir()

    assert git_common_dir(tmp_path / "repo") == (tmp_path / "repo" / ".git").resolve()
    assert git_common_dir(tmp_path / "repo" / "src") == (tmp_path / "repo" / ".git").resolve()


def test_git_common_dir_follows_a_gitdir_file_and_its_commondir(tmp_path: Path) -> None:
    common = tmp_path / "main" / ".git"
    worktree_git_dir = common / "worktrees" / "feature"
    worktree_git_dir.mkdir(parents=True)
    (worktree_git_dir / "commondir").write_text("../..\n", encoding="utf-8")
    worktree = tmp_path / "feature"
    worktree.mkdir()
    (worktree / ".git").write_text(f"gitdir: {worktree_git_dir}\n", encoding="utf-8")

    assert git_common_dir(worktree) == common.resolve()


def test_git_common_dir_outside_git_is_none(tmp_path: Path) -> None:
    assert git_common_dir(tmp_path) is None


@pytest.mark.skipif(shutil.which("git") is None, reason="git not on PATH")
@pytest.mark.usefixtures("hermetic_git_env")
def test_repo_key_shared_across_worktrees(tmp_path: Path) -> None:
    main = tmp_path / "main"
    main.mkdir()
    for args in (
        ("init", "-q"),
        ("commit", "-q", "--allow-empty", "-m", "init"),
        ("worktree", "add", "-q", str(tmp_path / "feature")),
    ):
        subprocess.run(["git", *args], cwd=main, check=True, capture_output=True, timeout=30)
    rev_parse = subprocess.run(
        ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
        cwd=tmp_path / "feature",
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    expected = hashlib.sha256(os.fsencode(os.path.realpath(rev_parse.stdout.strip()))).hexdigest()

    assert repo_key(main) == expected
    assert repo_key(tmp_path / "feature") == expected


# --- approvals ----------------------------------------------------------------------


def test_handler_approval_round_trips_through_a_fresh_store(tmp_path: Path) -> None:
    approved = _store(tmp_path, now=86400.0).approve_handler("guard-x", _WANTED)

    reopened = _store(tmp_path)

    assert approved.approved_at == "1970-01-02T00:00:00Z"
    assert reopened.handler("guard-x") == approved
    assert reopened.allows_handler("guard-x", _WANTED)


@pytest.mark.parametrize(
    "changed",
    [
        HandlerApproval("other_overlay", "python", "a" * 64, "b" * 64),
        HandlerApproval("acme_rules", "bash", "a" * 64, "b" * 64),
        HandlerApproval("acme_rules", "python", "f" * 64, "b" * 64),
        HandlerApproval("acme_rules", "python", "a" * 64, "f" * 64),
    ],
    ids=["source", "launcher", "args", "script"],
)
def test_handler_approval_invalidated_by_source_launcher_args_or_script_change(
    tmp_path: Path, changed: HandlerApproval
) -> None:
    store = _store(tmp_path)
    store.approve_handler("guard-x", _WANTED)

    assert not store.allows_handler("guard-x", changed)
    assert not store.allows_handler("guard-y", _WANTED)


def test_approval_time_never_counts_as_a_change(tmp_path: Path) -> None:
    store = _store(tmp_path, now=1.0)
    store.approve_handler("guard-x", _WANTED)

    later = HandlerApproval(**{**_WANTED.__dict__, "approved_at": "2030-01-01T00:00:00Z"})

    assert store.allows_handler("guard-x", later)


def test_execution_approval_keyed_on_stages_sha256(tmp_path: Path) -> None:
    store = _store(tmp_path)
    assert store.execution() is None
    stages = sha256_of_json([{"name": "tests", "tool": "pytest", "args": ["-q"]}])

    approved = store.approve_execution(stages)

    assert approved == ExecutionApproval(stages, "1970-01-01T00:00:00Z")
    assert store.allows_execution(stages)
    assert not store.allows_execution(sha256_of_json([{"name": "tests", "args": ["-x"]}]))


def test_approvals_are_per_repository(tmp_path: Path) -> None:
    _store(tmp_path, repo=tmp_path / "one").approve_handler("guard-x", _WANTED)

    other = _store(tmp_path, repo=tmp_path / "two")

    assert other.handler("guard-x") is None
    assert not other.allows_handler("guard-x", _WANTED)


def test_approving_keeps_other_repositories_records(tmp_path: Path) -> None:
    _store(tmp_path, repo=tmp_path / "one").approve_handler("guard-x", _WANTED)
    _store(tmp_path, repo=tmp_path / "two").approve_execution("c" * 64)

    assert _store(tmp_path, repo=tmp_path / "one").allows_handler("guard-x", _WANTED)


def test_store_is_a_versioned_json_document_keyed_by_repo(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.approve_handler("guard-x", _WANTED)

    document = json.loads(store.path.read_text(encoding="utf-8"))

    assert document["schema_version"] == 1
    assert document["repos"][store.repo_key]["handlers"]["guard-x"] == {
        "source": "acme_rules",
        "launcher": "python",
        "args_sha256": "a" * 64,
        "script_sha256": "b" * 64,
        "approved_at": "1970-01-01T00:00:00Z",
    }


def _corrupt_json(path: Path) -> None:
    path.write_text("{not json", encoding="utf-8")


def _future_schema(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**document, "schema_version": 99}), encoding="utf-8")


def _wrong_record_types(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    for record in document["repos"].values():
        record["handlers"]["guard-x"]["script_sha256"] = 7
        record["execution"]["stages_sha256"] = None
    path.write_text(json.dumps(document), encoding="utf-8")


def _tables_mistyped(path: Path) -> None:
    document = json.loads(path.read_text(encoding="utf-8"))
    for record in document["repos"].values():
        record["handlers"] = ["guard-x"]
        record["execution"] = "c" * 64
    path.write_text(json.dumps(document), encoding="utf-8")


def _group_writable(path: Path) -> None:
    path.chmod(0o620)


def _swapped_for_a_link(path: Path) -> None:
    real = path.with_name("elsewhere.json")
    path.rename(real)
    path.symlink_to(real)


@pytest.mark.parametrize(
    "spoil",
    [
        _corrupt_json,
        _future_schema,
        _wrong_record_types,
        _tables_mistyped,
        pytest.param(_group_writable, marks=_POSIX_ONLY),
        pytest.param(_swapped_for_a_link, marks=_POSIX_ONLY),
    ],
)
def test_unreadable_store_grants_nothing(tmp_path: Path, spoil: object) -> None:
    store = _store(tmp_path)
    store.approve_handler("guard-x", _WANTED)
    store.approve_execution("c" * 64)
    assert callable(spoil)

    spoil(store.path)

    assert store.handler("guard-x") is None
    assert not store.allows_handler("guard-x", _WANTED)
    assert not store.allows_execution("c" * 64)


def test_unreadable_store_is_never_overwritten(tmp_path: Path) -> None:
    store = _store(tmp_path)
    store.path.parent.mkdir(parents=True)
    _corrupt_json(store.path)

    with pytest.raises(TrustStoreError, match="cannot be read") as caught:
        store.approve_handler("guard-x", _WANTED)

    assert str(store.path) in str(caught.value)
    assert store.path.read_text(encoding="utf-8") == "{not json"


def test_missing_store_grants_nothing(tmp_path: Path) -> None:
    store = _store(tmp_path)

    assert store.handler("guard-x") is None
    assert store.execution() is None
    assert not store.path.exists()


def test_sha256_of_json_ignores_key_order() -> None:
    assert sha256_of_json({"a": 1, "b": [2]}) == sha256_of_json({"b": [2], "a": 1})
    assert sha256_of_json(["x", "y"]) != sha256_of_json(["y", "x"])


def test_trust_module_is_import_light() -> None:
    # On the dispatcher allow-list (§D.1): the stdlib only, and no yaml, jinja2 or tomllib.
    loaded = new_modules_after("import coding_agent_playbook.security.trust")

    foreign = [
        name
        for name in loaded
        if not name.startswith("coding_agent_playbook.security")
        and name.split(".")[0] not in sys.stdlib_module_names
    ]
    assert foreign == []
    assert not {"yaml", "jinja2", "tomllib"} & {name.split(".")[0] for name in loaded}
    assert "coding_agent_playbook.security.trust" in loaded
