"""Tests for the ``is_secret_path`` mechanics (specs/prK-lifecycle-hooks.md §P7).

The catalog itself is pinned in ``test_patterns.py``; these tests cover how the
predicate reads a path: path-like inputs, ``~`` expansion, the default home,
lexical normalization, and that it never touches the filesystem.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath
from typing import Any

import pytest

from coding_agent_playbook.security.paths import DEFAULT_PATH_POLICY, PathPolicy, is_secret_path

_HOME = "/home/dev"


def test_accepts_path_like_inputs() -> None:
    assert is_secret_path(PurePosixPath("deploy/.env"), home=_HOME, platform="linux") is True
    assert is_secret_path(PurePosixPath("src/app.py"), home=_HOME, platform="linux") is False


def test_accepts_a_path_like_home() -> None:
    home = PurePosixPath(_HOME)
    assert is_secret_path(f"{_HOME}/.aws/config", home=home, platform="linux") is True


def test_expands_a_leading_tilde_against_home() -> None:
    assert is_secret_path("~/.kube/config", home=_HOME, platform="linux") is True
    assert is_secret_path("~/notes/config", home=_HOME, platform="linux") is False


def test_bare_tilde_is_classified_as_the_home_path_itself() -> None:
    assert is_secret_path("~", home=_HOME, platform="linux") is False
    # A home whose own name is secret proves "~" was expanded, not matched literally.
    assert is_secret_path("~", home="/srv/.env", platform="linux") is True


def test_home_is_a_required_keyword() -> None:
    """P7 contract ``is_secret_path(path, *, home)``: no implicit ``$HOME`` default,
    so every caller states whose home anchors the ``~/`` globs."""
    with pytest.raises(TypeError, match="home"):
        is_secret_path("/home/alt/.docker/config.json", platform="linux")  # type: ignore[call-arg]
    assert is_secret_path("/home/alt/.docker/config.json", home="/home/alt") is True
    assert is_secret_path(f"{_HOME}/.docker/config.json", home="/home/alt") is False


def test_home_at_filesystem_root_anchors_every_absolute_path() -> None:
    assert is_secret_path("/.ssh/config", home="/", platform="linux") is True


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        (f"{_HOME}/project/../.aws/config", True),
        (f"{_HOME}/./.ssh/config", True),
        ("notes/.env/../readme.md", False),
        ("deploy//.env", True),
    ],
)
def test_normalizes_lexically(path: str, expected: bool) -> None:
    assert is_secret_path(path, home=_HOME, platform="linux") is expected


def test_classifies_without_touching_the_filesystem(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    secret = tmp_path / ".env"
    secret.write_text("TOKEN=hunter2\n", encoding="utf-8")

    def _forbidden(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("is_secret_path touched the filesystem")

    for name in ("open", "read_text", "read_bytes", "stat", "exists", "resolve"):
        monkeypatch.setattr(Path, name, _forbidden)

    assert is_secret_path(secret, home=_HOME, platform="linux") is True


# --- PathPolicy (specs/prK-hook-pack.md §E.4) ------------------------------------------------

_FIXTURE_ALLOW = ("tests/fixtures/**",)


@pytest.mark.parametrize(
    ("key", "platform", "nlink", "expected"),
    [
        (".env", "linux", 1, "deny"),
        (".ENV", "darwin", 1, "deny"),
        (".env.example", "linux", 1, None),
        ("src/auth/credentials.py", "linux", 1, None),
        ("config/credentials.json", "linux", 1, "deny"),
        (".env.credentials.py", "linux", 1, "deny"),  # a scoped exemption spares only its glob
        (f"{_HOME}/.aws/credentials", "linux", 1, "deny"),
        ("tests/fixtures/app/.env", "linux", 1, None),
        ("tests/fixtures-other/.env", "linux", 1, "deny"),
        ("notes.txt", "linux", 2, "unknown"),  # a hard link is the handler's call, not a match
        (".env", "linux", 3, "deny"),
        ("notes.txt", "linux", 1, None),
    ],
)
def test_path_policy_classify(key: str, platform: str, nlink: int, expected: str | None) -> None:
    policy = PathPolicy().extended(allow=_FIXTURE_ALLOW)

    assert policy.classify(key, nlink=nlink, home=_HOME, platform=platform) == expected


def test_path_policy_mode_ask_returns_ask_for_a_match() -> None:
    policy = PathPolicy(mode="ask")

    assert policy.classify("deploy/.env", nlink=1, home=_HOME, platform="linux") == "ask"


def test_extended_policy_appends_deny_globs_and_keeps_the_catalog() -> None:
    policy = PathPolicy().extended(deny=("*.secret", "config/prod/*.yaml"))

    assert policy.matches("vault/db.secret", home=_HOME, platform="linux")
    assert policy.matches("config/prod/db.yaml", home=_HOME, platform="linux")
    assert not policy.matches("config/prod/sub/db.yaml", home=_HOME, platform="linux")
    assert policy.matches(".env", home=_HOME, platform="linux")
    assert policy.deny[: len(PathPolicy().deny)] == PathPolicy().deny


def test_anchored_double_star_crosses_directories_but_star_does_not() -> None:
    policy = PathPolicy(deny=("data/**/*.key.txt", "creds/*"), allow=())

    assert policy.matches("data/a/b/x.key.txt", home=_HOME, platform="linux")
    assert policy.matches("data/x.key.txt", home=_HOME, platform="linux")
    assert policy.matches("creds/one", home=_HOME, platform="linux")
    assert not policy.matches("creds/one/two", home=_HOME, platform="linux")
    assert not policy.matches("other/data/x.key.txt", home=_HOME, platform="linux")


def test_home_directory_itself_is_not_matched_by_a_trailing_double_star() -> None:
    assert not is_secret_path(f"{_HOME}/.aws", home=_HOME, platform="linux")
    assert is_secret_path(f"{_HOME}/.aws/sso/cache/token.json", home=_HOME, platform="linux")


def test_is_secret_path_is_the_default_policy() -> None:
    for path in (".env", "src/credentials.py", f"{_HOME}/.ssh/id_rsa", "README.md"):
        assert is_secret_path(path, home=_HOME, platform="linux") is DEFAULT_PATH_POLICY.matches(
            path, home=_HOME, platform="linux"
        )
