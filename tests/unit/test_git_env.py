"""Unit tests for :mod:`coding_agent_playbook.git_env`."""

from __future__ import annotations

from coding_agent_playbook.git_env import REPO_LOCATION_GIT_VARS, without_repo_location

#: What git exports to a hook in a linked worktree, and what pins a repo's storage.
_HOOK_EXPORTED = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_COMMON_DIR",
    "GIT_NAMESPACE",
    "GIT_PREFIX",
}


def test_every_repo_locating_variable_is_dropped() -> None:
    assert _HOOK_EXPORTED <= REPO_LOCATION_GIT_VARS
    environ = {name: "/caller/.git" for name in REPO_LOCATION_GIT_VARS}

    assert without_repo_location(environ) == {}


def test_config_identity_and_path_pass_through_unchanged() -> None:
    kept = {
        "PATH": "/bin",
        "HOME": "/home/dev",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CEILING_DIRECTORIES": "/tmp",
        "GIT_AUTHOR_NAME": "dev",
    }
    environ = {**kept, "GIT_DIR": "/caller/.git", "GIT_INDEX_FILE": "/caller/.git/index"}

    assert without_repo_location(environ) == kept
    assert environ["GIT_DIR"] == "/caller/.git"  # the input is not mutated
