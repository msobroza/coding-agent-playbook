"""Which repository the docs site links source files to (docs/_ext/source_host.py)."""

from __future__ import annotations

import pytest

from source_host import SourceHost, source_host_from_env, web_url_of_remote

_GITLAB = "https://gitlab.acme.test/tools/coding-agent-playbook"


def test_without_a_build_environment_or_origin_there_is_no_source_host() -> None:
    assert source_host_from_env({}) is None


def test_a_github_host_links_with_github_routes() -> None:
    host = SourceHost("https://github.acme.test/t/p", "github")

    assert host.blob_url == "https://github.acme.test/t/p/blob/main/"
    assert host.tree_url == "https://github.acme.test/t/p/tree/main/"
    assert host.label == "GitHub"


@pytest.mark.parametrize(
    ("origin", "expected"),
    [
        ("git@gitlab.acme.test:tools/coding-agent-playbook.git", SourceHost(_GITLAB, "gitlab")),
        (
            "ssh://git@gitlab.acme.test:2222/tools/coding-agent-playbook.git",
            SourceHost(_GITLAB, "gitlab"),
        ),
        (
            "https://ci:token@gitlab.acme.test/tools/coding-agent-playbook.git",
            SourceHost(_GITLAB, "gitlab"),
        ),
        (
            "https://github.com/acme/playbook",
            SourceHost("https://github.com/acme/playbook", "github"),
        ),
        # A host whose forge the engine cannot tell, and a local path: no source links.
        ("git@code.acme.test:tools/p.git", None),
        ("/srv/git/coding-agent-playbook", None),
    ],
)
def test_the_origin_remote_names_the_repository_when_ci_does_not(
    origin: str, expected: SourceHost | None
) -> None:
    assert source_host_from_env({}, origin) == expected


def test_ci_variables_win_over_the_origin_remote() -> None:
    env = {"GITLAB_CI": "true", "CI_PROJECT_URL": _GITLAB}

    host = source_host_from_env(env, "https://github.com/acme/playbook")

    assert host == SourceHost(_GITLAB, "gitlab")


@pytest.mark.parametrize(
    ("remote", "web"),
    [
        ("git@gitlab.acme.test:tools/app.git", "https://gitlab.acme.test/tools/app"),
        ("http://gitlab.acme.test:8080/tools/app", "http://gitlab.acme.test:8080/tools/app"),
        ("C:\\repos\\app", None),
    ],
)
def test_web_url_of_remote(remote: str, web: str | None) -> None:
    assert web_url_of_remote(remote) == web


def test_gitlab_ci_links_to_its_project_and_default_branch_with_gitlab_routes() -> None:
    env = {"GITLAB_CI": "true", "CI_PROJECT_URL": _GITLAB, "CI_DEFAULT_BRANCH": "master"}

    host = source_host_from_env(env)

    assert host is not None
    assert host.blob_url == f"{_GITLAB}/-/blob/master/"
    assert host.tree_url == f"{_GITLAB}/-/tree/master/"
    assert host.label == "GitLab"


def test_github_actions_links_to_the_repository_of_the_run() -> None:
    env = {
        "GITHUB_ACTIONS": "true",
        "GITHUB_SERVER_URL": "https://github.acme.test",
        "GITHUB_REPOSITORY": "tools/coding-agent-playbook",
    }

    host = source_host_from_env(env)

    assert host == SourceHost("https://github.acme.test/tools/coding-agent-playbook", "github")


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        # The engine's forge mapping: a host name holding "gitlab" is GitLab.
        ({"PLAYBOOK_DOCS_REPO_URL": f"{_GITLAB}.git/"}, SourceHost(_GITLAB, "gitlab")),
        # A host the name does not tell: the forge host variable glab reads names it.
        (
            {
                "PLAYBOOK_DOCS_REPO_URL": "https://code.acme.test/t/p",
                "GITLAB_HOST": "code.acme.test",
            },
            SourceHost("https://code.acme.test/t/p", "gitlab"),
        ),
        (
            {
                "PLAYBOOK_DOCS_REPO_URL": "https://code.acme.test/t/p",
                "PLAYBOOK_DOCS_FORGE": "GitLab",
            },
            SourceHost("https://code.acme.test/t/p", "gitlab"),
        ),
        # The override wins over the CI's own variables, and the branch can change.
        (
            {
                "PLAYBOOK_DOCS_REPO_URL": "https://github.com/me/fork",
                "PLAYBOOK_DOCS_BRANCH": "docs",
                "GITLAB_CI": "true",
                "CI_PROJECT_URL": _GITLAB,
            },
            SourceHost("https://github.com/me/fork", "github", "docs"),
        ),
    ],
)
def test_an_override_names_the_repository_and_its_forge(
    env: dict[str, str], expected: SourceHost
) -> None:
    assert source_host_from_env(env) == expected


@pytest.mark.parametrize(
    ("env", "names"),
    [
        ({"PLAYBOOK_DOCS_REPO_URL": "git@gitlab.acme.test:t/p.git"}, "PLAYBOOK_DOCS_REPO_URL"),
        ({"PLAYBOOK_DOCS_REPO_URL": "https://code.acme.test/t/p"}, "PLAYBOOK_DOCS_FORGE"),
        (
            {"PLAYBOOK_DOCS_REPO_URL": _GITLAB, "PLAYBOOK_DOCS_FORGE": "bitbucket"},
            "PLAYBOOK_DOCS_FORGE='bitbucket'",
        ),
    ],
)
def test_an_unusable_override_is_refused_with_the_variable_to_fix(
    env: dict[str, str], names: str
) -> None:
    with pytest.raises(ValueError, match=names):
        source_host_from_env(env)
