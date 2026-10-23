"""``forge.hosts``: a remote URL's host, and the host's forge through spec prF §5.2."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.forge.dialects import GITHUB, GITLAB
from coding_agent_playbook.forge.hosts import (
    ForgeHost,
    HostEntry,
    RemoteHost,
    forge_for_host,
    host_entry,
    remote_host,
)

if TYPE_CHECKING:
    from coding_agent_playbook.forge.dialects import Forge


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("git@github.com:acme/app.git", RemoteHost("github.com", ssh=True)),
        ("ssh://git@gitlab.acme.com:2222/group/app.git", RemoteHost("gitlab.acme.com", ssh=True)),
        (
            "https://oauth2:glpat-secret@GitLab.Acme.com:8443/group/app.git",
            RemoteHost("gitlab.acme.com", ssh=False),
        ),
    ],
)
def test_remote_host_reads_the_three_url_forms(url: str, expected: RemoteHost) -> None:
    assert remote_host(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("gitlab.acme.com:group/app.git", RemoteHost("gitlab.acme.com", ssh=True)),
        ("git+ssh://git@github.com/acme/app", RemoteHost("github.com", ssh=True)),
        ("ssh+git://github.com/acme/app", RemoteHost("github.com", ssh=True)),
        ("git://git.acme.com/app.git", RemoteHost("git.acme.com", ssh=False)),
        ("http://token@git.acme.com./app.git", RemoteHost("git.acme.com", ssh=False)),
        ("ssh://git@[2001:db8::1]:22/app.git", RemoteHost("2001:db8::1", ssh=True)),
        ("git@[2001:db8::1]:app.git", RemoteHost("2001:db8::1", ssh=True)),
        ("https://us:p@ss@github.com/a/b\n", RemoteHost("github.com", ssh=False)),
        ("u@c:repo.git", RemoteHost("c", ssh=True)),
    ],
)
def test_remote_host_reads_the_other_git_url_forms(url: str, expected: RemoteHost) -> None:
    assert remote_host(url) == expected


@pytest.mark.parametrize(
    "url",
    ["", "/srv/git/app.git", "./app", "../a:b", "file:///srv/app.git", "C:\\repo", "C:/repo"],
)
def test_remote_host_is_none_for_a_local_path(url: str) -> None:
    assert remote_host(url) is None


@pytest.mark.parametrize("url", ["https:///path", "ssh://git@/app", "git@:app"])
def test_remote_host_is_none_without_a_host(url: str) -> None:
    assert remote_host(url) is None


def test_remote_host_never_keeps_the_userinfo() -> None:
    found = remote_host("https://oauth2:glpat-xxxxxxxxxxxxxxxxxxxx@gitlab.com/g/app.git")

    assert found is not None
    assert "glpat" not in repr(found)
    assert "oauth2" not in repr(found)


#: No ``[forge] hosts`` table and no forge host env vars.
_NO_HOSTS: dict[str, object] = {}
_NO_ENV: dict[str, str] = {}


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("github.com", ForgeHost(GITHUB, "github.com", "github.com", "exact")),
        ("GitLab.com.", ForgeHost(GITLAB, "gitlab.com", "gitlab.com", "exact")),
    ],
)
def test_the_public_hosts_map_exactly(host: str, expected: ForgeHost) -> None:
    assert forge_for_host(host, _NO_HOSTS, _NO_ENV) == expected


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("github.acme.com", ForgeHost(GITHUB, "github.acme.com", "github.acme.com", "name")),
        ("ssh.github.com", ForgeHost(GITHUB, "ssh.github.com", "ssh.github.com", "name")),
        ("altssh.gitlab.com", ForgeHost(GITLAB, "altssh.gitlab.com", "altssh.gitlab.com", "name")),
        ("MyGitLab.corp", ForgeHost(GITLAB, "mygitlab.corp", "mygitlab.corp", "name")),
    ],
)
def test_a_host_name_holding_the_forge_name_maps_to_it(host: str, expected: ForgeHost) -> None:
    assert forge_for_host(host, _NO_HOSTS, _NO_ENV) == expected


def test_a_host_name_holding_both_forge_names_is_unknown() -> None:
    assert forge_for_host("github-to-gitlab.acme.com", _NO_HOSTS, _NO_ENV) is None


@pytest.mark.parametrize("host", ["git.acme.com", "bitbucket.org", "", "  "])
def test_an_unmatched_host_is_an_unknown_forge(host: str) -> None:
    assert forge_for_host(host, _NO_HOSTS, _NO_ENV) is None


@pytest.mark.parametrize(
    ("env", "expected"),
    [
        ({"GH_HOST": "ghe.acme.com"}, GITHUB),
        ({"GH_HOST": "https://GHE.acme.com/"}, GITHUB),
        ({"GITLAB_HOST": "https://ghe.acme.com"}, GITLAB),
        ({"GITLAB_URI": "https://ci:tok@ghe.acme.com:8443/api/v4"}, GITLAB),
        ({"GL_HOST": "ghe.acme.com:443"}, GITLAB),
    ],
)
def test_a_host_equal_to_a_forge_host_env_var_maps_to_that_forge(
    env: dict[str, str], expected: Forge
) -> None:
    assert forge_for_host("ghe.acme.com", _NO_HOSTS, env) == ForgeHost(
        expected, "ghe.acme.com", "ghe.acme.com", "env"
    )


@pytest.mark.parametrize(
    "env",
    [
        {"GH_HOST": "other.acme.com"},
        {"GITLAB_HOST": ""},
        {"GITLAB_API_HOST": "ghe.acme.com"},
        {"GH_HOST": "ghe.acme.com.evil.test"},
        {"GH_HOST": "ghe.acme.com", "GITLAB_HOST": "ghe.acme.com"},
    ],
)
def test_no_forge_host_env_var_names_the_host(env: dict[str, str]) -> None:
    assert forge_for_host("ghe.acme.com", _NO_HOSTS, env) is None


def test_the_host_name_rule_comes_before_the_env_rule() -> None:
    found = forge_for_host("gitlab.acme.com", _NO_HOSTS, {"GH_HOST": "gitlab.acme.com"})

    assert found == ForgeHost(GITLAB, "gitlab.acme.com", "gitlab.acme.com", "name")


#: The spec's own example (§5.4).
_ACME_HOSTS: dict[str, object] = {
    "git.acme.com": "gitlab",
    "ssh.acme.com": {"forge": "gitlab", "api_host": "gitlab.acme.com"},
    "Code.Acme.com": {"forge": "github"},
}


@pytest.mark.parametrize(
    ("host", "expected"),
    [
        ("git.acme.com", ForgeHost(GITLAB, "git.acme.com", "git.acme.com", "table")),
        ("ssh.acme.com", ForgeHost(GITLAB, "ssh.acme.com", "gitlab.acme.com", "table")),
        ("code.acme.com", ForgeHost(GITHUB, "code.acme.com", "code.acme.com", "table")),
    ],
)
def test_a_forge_hosts_entry_maps_its_host(host: str, expected: ForgeHost) -> None:
    assert forge_for_host(host, _ACME_HOSTS, _NO_ENV) == expected


def test_a_forge_hosts_entry_comes_first() -> None:
    hosts: dict[str, object] = {"github.acme.com": "gitlab"}
    env = {"GH_HOST": "github.acme.com"}

    found = forge_for_host("github.acme.com", hosts, env)

    assert found == ForgeHost(GITLAB, "github.acme.com", "github.acme.com", "table")


def test_an_api_host_keeps_its_port_and_is_lower_cased() -> None:
    hosts: dict[str, object] = {
        "ssh.acme.com": {"forge": "gitlab", "api_host": "GitLab.acme.com:8443"}
    }

    found = forge_for_host("ssh.acme.com", hosts, _NO_ENV)

    assert found is not None
    assert found.api_host == "gitlab.acme.com:8443"


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("github", HostEntry(GITHUB, None)),
        ({"forge": "gitlab"}, HostEntry(GITLAB, None)),
        ({"forge": "gitlab", "api_host": "gitlab.acme.com"}, HostEntry(GITLAB, "gitlab.acme.com")),
        (
            {"forge": "gitlab", "api_host": "[2001:db8::1]:8443"},
            HostEntry(GITLAB, "[2001:db8::1]:8443"),
        ),
    ],
)
def test_host_entry_reads_a_string_or_a_table(value: object, expected: HostEntry) -> None:
    assert host_entry(value) == expected


@pytest.mark.parametrize(
    ("value", "message"),
    [
        ("bitbucket", "'bitbucket' is not a forge"),
        ("GitHub", "'GitHub' is not a forge"),
        (3, "a forge name or a table"),
        ({"api_host": "gitlab.acme.com"}, "needs forge"),
        ({"forge": "gitlab", "token": "x"}, "unknown key 'token'"),
        ({"forge": 1}, "'forge' must be a string"),
        ({"forge": "gitlab", "api_host": ""}, "api_host"),
        ({"forge": "gitlab", "api_host": "https://gitlab.acme.com"}, "api_host"),
        ({"forge": "gitlab", "api_host": "gitlab.acme.com/api"}, "api_host"),
        ({"forge": "gitlab", "api_host": "u@gitlab.acme.com"}, "api_host"),
    ],
)
def test_host_entry_rejects_a_malformed_value(value: object, message: str) -> None:
    with pytest.raises(ValueError, match=message):
        host_entry(value)


def test_a_malformed_entry_fails_only_its_own_host() -> None:
    hosts: dict[str, object] = {"git.acme.com": "gitlub", "code.acme.com": "github"}

    assert forge_for_host("code.acme.com", hosts, _NO_ENV) is not None
    with pytest.raises(ValueError, match="'gitlub' is not a forge"):
        forge_for_host("git.acme.com", hosts, _NO_ENV)


def test_a_rejected_api_host_is_not_echoed() -> None:
    value = {"forge": "gitlab", "api_host": "https://ci:glpat-xxxxxxxxxxxxxxxxxxxx@gitlab.acme.com"}

    with pytest.raises(ValueError, match="api_host") as raised:
        host_entry(value)

    assert "glpat" not in str(raised.value)


def test_a_forge_hosts_key_is_a_host_name_not_a_url() -> None:
    hosts: dict[str, object] = {"https://git.acme.com/": "gitlab", "GIT.ACME.COM.": "github"}

    found = forge_for_host("git.acme.com", hosts, _NO_ENV)

    assert found == ForgeHost(GITHUB, "git.acme.com", "git.acme.com", "table")
