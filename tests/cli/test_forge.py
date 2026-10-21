"""``playbook forge``: forge detection, the child environment and exit codes 0 / 1 / 2 / 3.

Every test runs the real command against a real git repo with fake ``gh``,
``glab`` and ``ssh`` on ``PATH`` (spec prF §5, §6.2, §15; ``tests/cli/forge_fakes``).
The per-operation rows are in ``test_forge_issues.py`` and ``test_forge_pulls.py``.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.cli.forge_fakes import ForgeEnv


def _forge(repo: Path, *words: str) -> int:
    return main(["forge", "-C", str(repo), *words])


def test_which_names_the_forge_of_the_push_remote(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("git@github.com:acme/app.git")

    assert _forge(repo, "which") == 0

    assert json.loads(capsys.readouterr().out) == {
        "forge": "github",
        "cli": "gh",
        "host": "github.com",
        "api_host": "github.com",
        "repo": "acme/app",
        "remote": "origin",
    }
    assert forge_env.calls("gh") == forge_env.calls("glab") == []


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=30)


def _which(repo: Path, capsys: pytest.CaptureFixture[str]) -> dict[str, str]:
    assert _forge(repo, "which") == 0
    return dict(json.loads(capsys.readouterr().out))


@pytest.mark.parametrize(
    ("config", "remote"),
    [
        ((), "origin"),
        ((("branch.main.remote", "up"),), "up"),
        ((("branch.main.remote", "up"), ("remote.pushDefault", "fork")), "fork"),
        (
            (
                ("branch.main.remote", "up"),
                ("remote.pushDefault", "fork"),
                ("branch.main.pushRemote", "mine"),
            ),
            "mine",
        ),
        ((("branch.main.remote", "."),), "origin"),
    ],
)
def test_the_push_remote_follows_the_branch_then_push_default_then_origin(
    forge_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    config: tuple[tuple[str, str], ...],
    remote: str,
) -> None:
    repo = forge_repo("https://gitlab.com/acme/origin.git")
    for name in ("up", "fork", "mine"):
        _git(repo, "remote", "add", name, f"https://gitlab.com/acme/{name}.git")
    for key, value in config:
        _git(repo, "config", key, value)

    which = _which(repo, capsys)

    assert (which["remote"], which["repo"]) == (remote, f"acme/{remote}")


@pytest.mark.parametrize(("push_default", "remote"), [(None, "origin"), ("fork", "fork")])
def test_a_detached_head_uses_push_default_then_origin(
    forge_repo: Callable[..., Path],
    capsys: pytest.CaptureFixture[str],
    push_default: str | None,
    remote: str,
) -> None:
    repo = forge_repo("git@github.com:acme/origin.git")
    _git(repo, "remote", "add", "fork", "git@github.com:me/fork.git")
    _git(repo, "config", "branch.main.pushRemote", "fork")
    if push_default is not None:
        _git(repo, "config", "remote.pushDefault", push_default)
    _git(repo, "checkout", "-q", "--detach")

    assert _which(repo, capsys)["remote"] == remote


def test_the_push_url_comes_before_the_url(
    forge_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("https://example.org/acme/app.git")
    _git(repo, "remote", "set-url", "--push", "origin", "https://gitlab.com/acme/app.git")

    which = _which(repo, capsys)

    assert (which["forge"], which["host"]) == ("gitlab", "gitlab.com")


def test_an_insteadof_rewrite_is_read_only_when_the_raw_host_does_not_map(
    forge_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("work:acme/app.git")
    _git(repo, "config", "url.https://gitlab.com/.pushInsteadOf", "work:")

    which = _which(repo, capsys)

    assert (which["forge"], which["host"], which["repo"]) == ("gitlab", "gitlab.com", "acme/app")


def test_an_ssh_alias_resolves_through_ssh_g(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("ssh", "-G", "work", stdout="user git\nhostname altssh.gitlab.com\nport 443\n")
    repo = forge_repo("work:acme/app.git")

    which = _which(repo, capsys)

    assert (which["forge"], which["host"], which["api_host"]) == (
        "gitlab",
        "gitlab.com",
        "gitlab.com",
    )
    assert forge_env.argvs("ssh") == [("-G", "work")]


def test_a_forge_hosts_entry_maps_a_host_and_names_its_api_host(
    forge_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    config = (
        '[forge]\nhosts = { "ssh.acme.com" = { forge = "gitlab", api_host = "gitlab.acme.com" } }\n'
    )
    repo = forge_repo("ssh://git@ssh.acme.com:2222/platform/app.git", config=config)

    which = _which(repo, capsys)

    assert which == {
        "forge": "gitlab",
        "cli": "glab",
        "host": "ssh.acme.com",
        "api_host": "gitlab.acme.com",
        "repo": "platform/app",
        "remote": "origin",
    }


def test_a_host_named_by_a_forge_host_variable_maps_to_that_forge(
    forge_repo: Callable[..., Path],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("GH_HOST", "https://code.acme.com/")
    repo = forge_repo("https://ci:secret@code.acme.com/acme/app.git")

    assert _which(repo, capsys)["forge"] == "github"


def test_an_unknown_host_exits_2_naming_the_host_never_the_url(
    forge_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("https://ci:s3cret-token@git.acme.com/acme/app.git")

    assert _forge(repo, "which") == 2

    err = capsys.readouterr().err
    assert "unknown forge for host `git.acme.com`" in err
    assert "[forge] hosts" in err
    assert "s3cret-token" not in err


def test_a_malformed_forge_table_exits_2(
    forge_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo(
        "https://git.acme.com/acme/app.git", config='[forge]\nhosts = { "x" = "svn" }\n'
    )

    assert _forge(repo, "which") == 2

    assert "'svn' is not a forge" in capsys.readouterr().err


def test_a_push_remote_without_a_url_exits_2(
    forge_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("https://github.com/acme/app.git")
    _git(repo, "config", "branch.main.pushRemote", "gone")

    assert _forge(repo, "which") == 2

    assert "no remote `gone`" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("domino", "hint"),
    [(None, "pass `-C <path>`"), ("p-123", "`/mnt/code` in a git-based project")],
)
def test_outside_a_work_tree_exits_2_with_a_domino_aware_hint(
    tmp_path: Path,
    forge_env: ForgeEnv,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    domino: str | None,
    hint: str,
) -> None:
    if domino is not None:
        monkeypatch.setenv("DOMINO_PROJECT_ID", domino)
    outside = tmp_path / "outside"
    outside.mkdir()

    assert _forge(outside, "which") == 2

    err = capsys.readouterr().err
    assert err.startswith("error: not in a git work tree") and hint in err


_GH_ISSUE = {"number": 3, "url": "https://x/3", "title": "t", "state": "OPEN"}
_GL_ISSUE = {"iid": 3, "web_url": "https://x/3", "title": "t", "state": "opened"}
_QUIET = {
    "GH_PROMPT_DISABLED": "1",
    "GLAB_NO_PROMPT": "true",
    "GH_NO_UPDATE_NOTIFIER": "1",
    "GH_NO_EXTENSION_UPDATE_NOTIFIER": "1",
    "GH_TELEMETRY": "false",
    "DO_NOT_TRACK": "1",
    "GLAB_CHECK_UPDATE": "false",
    "GLAB_SEND_TELEMETRY": "false",
}


@pytest.mark.parametrize(
    ("url", "config", "cli", "told"),
    [
        ("git@github.com:acme/app.git", None, "gh", {"GH_HOST": "github.com"}),
        ("https://gitlab.com/acme/app.git", None, "glab", {"GITLAB_HOST": "https://gitlab.com"}),
        (
            "git@ssh.acme.com:acme/app.git",
            '[forge]\nhosts = { "ssh.acme.com" = { forge = "gitlab", api_host = "gl.acme.com" } }\n',
            "glab",
            {"GITLAB_HOST": "https://gl.acme.com", "GITLAB_API_HOST": "gl.acme.com"},
        ),
    ],
)
def test_every_call_tells_the_cli_its_host_and_turns_prompts_and_telemetry_off(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    config: str | None,
    cli: str,
    told: dict[str, str],
) -> None:
    forge_env.reply(cli, "issue", "view", json_out=_GH_ISSUE if cli == "gh" else _GL_ISSUE)
    repo = forge_repo(url, config=config)

    assert _forge(repo, "issue", "view", "3") == 0

    calls = forge_env.calls(cli, versions=True)
    assert [c.argv[:2] for c in calls if c.argv[:1] != ("config",)] == [
        ("--version",),
        ("issue", "view"),
    ]
    for call in calls:
        if call.argv[:1] == ("config",):  # glab config get reads GITLAB_API_HOST first
            assert call.env == {**_QUIET, "GITLAB_HOST": told["GITLAB_HOST"]}
        else:
            assert call.env == {**_QUIET, **told}, call.argv


@pytest.mark.parametrize(
    ("cli", "url"), [("gh", "git@github.com:a/b.git"), ("glab", "git@gitlab.com:a/b.git")]
)
def test_the_cli_version_is_checked_once_per_call(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, cli: str, url: str
) -> None:
    forge_env.reply(cli, "issue", "view", json_out=_GH_ISSUE if cli == "gh" else _GL_ISSUE)
    repo = forge_repo(url)

    assert _forge(repo, "issue", "view", "3") == 0

    versions = [c for c in forge_env.calls(cli, versions=True) if c.argv == ("--version",)]
    assert len(versions) == 1


@pytest.mark.parametrize(
    ("domino", "hint"),
    [(None, "install `glab` 1.115.0 or later"), ("p-1", "compute environment's Dockerfile")],
)
def test_a_missing_cli_exits_2_with_the_install_step(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    domino: str | None,
    hint: str,
) -> None:
    if domino is not None:
        monkeypatch.setenv("DOMINO_PROJECT_ID", domino)
    forge_env.remove("glab")
    repo = forge_repo("git@gitlab.com:acme/app.git")

    assert _forge(repo, "issue", "view", "3") == 2

    err = capsys.readouterr().err
    assert "`glab` is not installed" in err and hint in err


@pytest.mark.parametrize(
    ("cli", "url", "version", "shown"),
    [
        (
            "gh",
            "git@github.com:a/b.git",
            "gh version 2.65.0 (2025-01-06)\n",
            "is 2.65.0, older than 2.94.0",
        ),
        (
            "glab",
            "git@gitlab.com:a/b.git",
            "glab 1.114.9 (abc)\n",
            "is 1.114.9, older than 1.115.0",
        ),
        ("glab", "git@gitlab.com:a/b.git", "something\n", "reports no version"),
    ],
)
def test_a_cli_below_the_minimum_exits_2_before_any_call(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    cli: str,
    url: str,
    version: str,
    shown: str,
) -> None:
    forge_env.reply(cli, "--version", stdout=version)
    repo = forge_repo(url)

    assert _forge(repo, "issue", "view", "3") == 2

    assert shown in capsys.readouterr().err
    assert forge_env.calls(cli) == []


@pytest.mark.parametrize(
    ("cli", "url", "code", "stderr", "hint"),
    [
        (
            "gh",
            "git@github.com:a/b.git",
            4,
            "To get started with GitHub CLI, please run:  gh auth login\n",
            "run `gh auth login --hostname github.com` or set `GH_TOKEN`",
        ),
        (
            "glab",
            "git@gitlab.com:a/b.git",
            1,
            "ERROR: 401 Unauthorized\n",
            "run `glab auth login --hostname gitlab.com` or set `GITLAB_TOKEN`",
        ),
    ],
)
def test_a_cli_without_a_login_exits_2_with_the_login_step(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    cli: str,
    url: str,
    code: int,
    stderr: str,
    hint: str,
) -> None:
    forge_env.reply(cli, "issue", "view", stderr=stderr, code=code)
    repo = forge_repo(url)

    assert _forge(repo, "issue", "view", "3") == 2

    err = capsys.readouterr().err
    assert err.startswith(stderr) and hint in err


def test_on_domino_the_login_step_is_a_user_environment_variable(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setenv("DOMINO_PROJECT_ID", "p-1")
    forge_env.reply("glab", "issue", "view", stderr="401 Unauthorized\n", code=1)
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "view", "3") == 2

    assert (
        "add `GITLAB_TOKEN` under Account Settings → User environment variables and start a "
        "new workspace"
    ) in capsys.readouterr().err


def test_a_failed_cli_call_exits_1_with_its_stderr_unchanged(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("gh", "issue", "view", stderr="GraphQL: Could not resolve issue (3)\n", code=1)
    repo = forge_repo("git@github.com:a/b.git")

    assert _forge(repo, "issue", "view", "3") == 1

    assert capsys.readouterr().err == "GraphQL: Could not resolve issue (3)\n"


@pytest.mark.parametrize(
    ("variable", "configured", "shown"),
    [
        ("gl.other.com", "", "GITLAB_API_HOST names gl.other.com"),
        ("", "api.other.com", "names api.other.com"),
    ],
)
def test_a_gitlab_api_host_naming_another_host_exits_2(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    variable: str,
    configured: str,
    shown: str,
) -> None:
    if variable:
        monkeypatch.setenv("GITLAB_API_HOST", variable)
    forge_env.reply("glab", "config", "get", "api_host", stdout=f"{configured}\n")
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "view", "3") == 2

    assert shown in capsys.readouterr().err
    assert forge_env.argvs("glab") in ([], [("config", "get", "api_host", "--host", "gitlab.com")])


def test_a_gitlab_api_host_naming_the_same_host_is_fine(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITLAB_API_HOST", "https://GitLab.com:443/")
    forge_env.reply("glab", "config", "get", "api_host", stdout="gitlab.com\n")
    forge_env.reply("glab", "issue", "view", json_out=_GL_ISSUE)
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "view", "3") == 0


def test_an_operation_the_forge_lacks_exits_3_before_any_call(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "children", "3") == 3

    assert capsys.readouterr().err.startswith("unsupported: `issue children`")
    assert forge_env.calls("glab", versions=True) == []


@pytest.mark.parametrize(
    "words",
    [
        ("issue", "delete", "3"),
        ("issue", "view"),
        ("issue", "view", "3", "4"),
        ("issue", "view", "3", "--nope"),
        ("issue", "close", "3", "--reason", "wontfix"),
        ("issue", "comment", "3", "--body", "a", "--body-file", "-"),
        ("pr", "list", "--state"),
    ],
)
def test_a_usage_error_exits_1_before_any_call(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    words: tuple[str, ...],
) -> None:
    repo = forge_repo("git@github.com:a/b.git")

    assert _forge(repo, *words) == 1

    assert capsys.readouterr().err.startswith("error: ")
    assert forge_env.calls() == []


def test_no_operation_lists_the_operations(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["forge"]) == 0

    out = capsys.readouterr().out
    assert "playbook forge issue create" in out and "playbook forge auth status" in out


def test_help_after_an_operation_prints_its_usage(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["forge", "pr", "view", "--help"]) == 0

    assert capsys.readouterr().out == "playbook forge pr view <n> [--comments]\n"


def test_a_number_given_as_hash_n_reaches_the_cli_as_n(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    forge_env.reply("glab", "issue", "view", json_out=_GL_ISSUE)
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "view", "#3") == 0

    assert forge_env.last("glab").argv[:3] == ("issue", "view", "3")


def test_a_push_remote_on_a_local_path_exits_2(
    forge_repo: Callable[..., Path], capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("/srv/git/app.git")

    assert _forge(repo, "which") == 2

    assert "the push remote `origin` is a local path" in capsys.readouterr().err


def test_output_that_is_not_json_exits_1(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "api", stdout="<html>proxy error</html>\n")
    forge_env.reply("glab", "issue", "view", json_out=_GL_ISSUE)
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "view", "3", "--comments") == 1

    assert "printed no JSON" in capsys.readouterr().err


def test_an_unknown_state_is_a_usage_error(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "list", "--state", "merged") == 1

    assert "--state must be one of open, closed, all" in capsys.readouterr().err


def test_the_cli_never_sees_a_repo_override_or_the_old_prompt_switch(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GH_REPO", "evil.example/o/r")
    monkeypatch.setenv("GITLAB_REPO", "evil.example/o/r")
    monkeypatch.setenv("NO_PROMPT", "false")
    forge_env.reply("glab", "issue", "view", json_out=_GL_ISSUE)
    repo = forge_repo("git@gitlab.com:a/b.git")

    assert _forge(repo, "issue", "view", "3") == 0

    env = forge_env.last("glab").env
    assert not {"GH_REPO", "GITLAB_REPO", "NO_PROMPT"} & set(env)
