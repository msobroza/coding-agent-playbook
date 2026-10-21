"""``playbook forge pr …``, ``ref view``, ``label …`` and ``auth status``: a GitHub and a GitLab case each.

Fake ``gh`` / ``glab`` on ``PATH`` (``tests/cli/forge_fakes``) record argv and
stdin and answer with canned JSON (spec prF §6.3, §15). ``pr create`` never
pushes: the fixture repo has ``refs/remotes/origin/<branch>`` unless a test
says otherwise.
"""

from __future__ import annotations

import json
import subprocess
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.cli.forge_fakes import ForgeEnv

GITHUB_URL: Final = "git@github.com:acme/app.git"
GITLAB_URL: Final = "git@gitlab.com:acme/app.git"

GH_PULL: Final = {
    "number": 5,
    "url": "https://github.com/acme/app/pull/5",
    "title": "Add X",
    "body": "Adds X.",
    "state": "MERGED",
    "labels": [{"name": "feature"}],
    "assignees": [{"login": "max"}],
    "author": {"login": "ann"},
    "createdAt": "2026-10-01T10:00:00Z",
    "updatedAt": "2026-10-02T10:00:00Z",
    "isDraft": True,
    "baseRefName": "main",
    "headRefName": "feat/x",
}
GL_PULL: Final = {
    "iid": 5,
    "web_url": "https://gitlab.com/acme/app/-/merge_requests/5",
    "title": "Add X",
    "description": "Adds X.",
    "state": "merged",
    "labels": ["feature"],
    "assignees": [{"username": "max"}],
    "author": {"id": 2, "username": "ann"},
    "created_at": "2026-10-01T10:00:00Z",
    "updated_at": "2026-10-02T10:00:00Z",
    "draft": True,
    "target_branch": "main",
    "source_branch": "feat/x",
}
PULL: Final = {
    "number": 5,
    "title": "Add X",
    "body": "Adds X.",
    "state": "merged",
    "labels": ["feature"],
    "assignees": ["max"],
    "author": "ann",
    "created_at": "2026-10-01T10:00:00Z",
    "updated_at": "2026-10-02T10:00:00Z",
    "confidential": False,
    "draft": True,
    "base": "main",
    "head": "feat/x",
}


def _forge(repo: Path, *words: str) -> int:
    return main(["forge", "-C", str(repo), *words])


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, timeout=30)


def _out(capsys: pytest.CaptureFixture[str]) -> Any:
    return json.loads(capsys.readouterr().out)


def test_pr_create_on_github_names_the_head_branch_and_never_pushes(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("gh", "pr", "create", stdout="https://github.com/acme/app/pull/6\n")
    repo = forge_repo(GITHUB_URL, branch="feat/x")

    code = _forge(
        repo, "pr", "create", "--title", "Add X [skip ci]", "--body", "Adds X.", "--base",
        "main", "--draft",
    )  # fmt: skip

    assert code == 0
    call = forge_env.last("gh")
    assert call.argv == (
        "pr", "create", "--head", "feat/x", "--title", "Add X [skip ci]", "--body-file", "-",
        "--base", "main", "--draft",
    )  # fmt: skip
    assert call.stdin == "Adds X."
    assert capsys.readouterr().out == "https://github.com/acme/app/pull/6\n"


def test_pr_create_on_gitlab_opens_a_merge_request_without_fill_or_push(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply(
        "glab", "mr", "create", stdout="https://gitlab.com/acme/app/-/merge_requests/6\n"
    )
    repo = forge_repo(GITLAB_URL, branch="feat/x")

    code = _forge(
        repo, "pr", "create", "--title", "Add X", "--body", "/merge\nok", "--base", "main"
    )

    assert code == 0
    call = forge_env.last("glab")
    assert call.argv == (
        "mr", "create", "--source-branch", "feat/x", "--title", "Add X", "--description-file",
        "-", "--target-branch", "main", "--push=false", "--yes",
    )  # fmt: skip
    assert "--fill" not in call.argv and "-f" not in call.argv
    assert call.stdin == " /merge\nok"
    assert capsys.readouterr().out == "https://gitlab.com/acme/app/-/merge_requests/6\n"


def test_pr_create_uses_the_branch_name_on_the_push_remote(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITHUB_URL, branch="local", pushed=False)
    _git(repo, "update-ref", "refs/remotes/origin/remote-name", "HEAD")
    _git(repo, "config", "branch.local.remote", "origin")
    _git(repo, "config", "branch.local.merge", "refs/heads/remote-name")
    _git(repo, "config", "push.default", "upstream")

    assert _forge(repo, "pr", "create", "--title", "X") == 0

    assert forge_env.last("gh").argv[:4] == ("pr", "create", "--head", "remote-name")


@pytest.mark.parametrize(("url", "cli"), [(GITHUB_URL, "gh"), (GITLAB_URL, "glab")])
def test_pr_create_exits_2_when_the_branch_is_not_on_the_remote(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
) -> None:
    repo = forge_repo(url, branch="feat/x", pushed=False)

    assert _forge(repo, "pr", "create", "--title", "X") == 2

    assert "push the branch first (`git push -u origin feat/x`)" in capsys.readouterr().err
    assert forge_env.calls(cli) == []


def test_pr_create_exits_2_on_a_detached_head(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo(GITHUB_URL)
    _git(repo, "checkout", "-q", "--detach")

    assert _forge(repo, "pr", "create", "--title", "X") == 2

    assert "detached HEAD: run `git checkout -b <name>`" in capsys.readouterr().err
    assert forge_env.calls("gh") == []


@pytest.mark.parametrize(
    "title", ["Add X [skip ci]", "[CI SKIP] x", "x [Skip Pipeline]", "[no ci]"]
)
def test_pr_create_refuses_a_skip_ci_title_on_gitlab(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    title: str,
) -> None:
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "create", "--title", title) == 1

    assert "skips the pipeline" in capsys.readouterr().err
    assert forge_env.calls("glab") == [c for c in forge_env.calls("glab") if c.argv[0] == "config"]


@pytest.mark.parametrize(
    ("url", "cli", "reply", "argv", "url_out"),
    [
        (
            GITHUB_URL,
            "gh",
            GH_PULL,
            ("pr", "view", "5", "--json", "number,url,title,body,state,labels,assignees,author,"
             "createdAt,updatedAt,isDraft,baseRefName,headRefName"),
            "https://github.com/acme/app/pull/5",
        ),
        (
            GITLAB_URL,
            "glab",
            GL_PULL,
            ("mr", "view", "5", "-F", "json"),
            "https://gitlab.com/acme/app/-/merge_requests/5",
        ),
    ],
)  # fmt: skip
def test_pr_view(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
    reply: dict[str, object],
    argv: tuple[str, ...],
    url_out: str,
) -> None:
    forge_env.reply(cli, argv[0], "view", json_out=reply)
    repo = forge_repo(url)

    assert _forge(repo, "pr", "view", "5") == 0

    assert forge_env.last(cli).argv == argv
    assert _out(capsys) == {**PULL, "url": url_out}


def test_pr_view_with_comments_on_github_adds_the_review_comments(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    talk = {"author": {"login": "bob"}, "body": "Nice.", "createdAt": "t1",
            "url": "https://github.com/acme/app/pull/5#issuecomment-71"}  # fmt: skip
    review = {"id": 72, "user": {"login": "eve"}, "body": "Rename this.", "created_at": "t2",
              "path": "src/x.py"}  # fmt: skip
    forge_env.reply("gh", "pr", "view", json_out={**GH_PULL, "comments": [talk]})
    forge_env.reply("gh", "api", json_out=[review])
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "pr", "view", "5", "--comments") == 0

    assert forge_env.last("gh").argv == (
        "api", "--paginate", "repos/{owner}/{repo}/pulls/5/comments",
    )  # fmt: skip
    comments = _out(capsys)["comments"]
    assert comments == [
        {"id": 71, "author": "bob", "body": "Nice.", "created_at": "t1", "path": None},
        {"id": 72, "author": "eve", "body": "Rename this.", "created_at": "t2", "path": "src/x.py"},
    ]


def test_pr_view_with_comments_on_gitlab_reads_the_notes(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    note = {"id": 81, "body": "Rename this.", "author": {"username": "eve"}, "created_at": "t",
            "system": False, "position": {"new_path": "src/x.py"}}  # fmt: skip
    forge_env.reply("glab", "mr", "view", json_out=GL_PULL)
    forge_env.reply("glab", "api", json_out=[note])
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "view", "5", "--comments") == 0

    assert forge_env.last("glab").argv[2].startswith("projects/:fullpath/merge_requests/5/notes?")
    assert _out(capsys)["comments"] == [
        {"id": 81, "author": "eve", "body": "Rename this.", "created_at": "t", "path": "src/x.py"}
    ]


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [
        (GITHUB_URL, "gh", ("pr", "list", "--json", "number,url,title,body,state,labels,assignees,"
                            "author,createdAt,updatedAt,isDraft,baseRefName,headRefName",
                            "--state", "merged", "--label", "feature")),
        (GITLAB_URL, "glab", ("mr", "list", "-F", "json", "--merged", "--label", "feature")),
    ],
)  # fmt: skip
def test_pr_list(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    forge_env.reply(cli, argv[0], "list", json_out=[GH_PULL if cli == "gh" else GL_PULL])
    repo = forge_repo(url)

    assert _forge(repo, "pr", "list", "--state", "merged", "--label", "feature") == 0

    assert forge_env.last(cli).argv == argv
    assert [pull["number"] for pull in _out(capsys)] == [5]


def test_pr_list_external_on_github_keeps_outside_authors_with_their_association(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    def rest(number: int, association: str) -> dict[str, object]:
        return {"number": number, "html_url": f"https://x/{number}", "title": "t", "state": "open",
                "user": {"login": f"u{number}"}, "author_association": association, "labels": [],
                "draft": False, "base": {"ref": "main"}, "head": {"ref": "b"}}  # fmt: skip

    forge_env.reply(
        "gh", "api", json_out=[rest(1, "MEMBER"), rest(2, "CONTRIBUTOR"), rest(3, "NONE")]
    )
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "pr", "list", "--external") == 0

    assert forge_env.last("gh").argv == (
        "api", "--paginate", "repos/{owner}/{repo}/pulls?state=open&per_page=100",
    )  # fmt: skip
    listed = _out(capsys)
    assert [(p["number"], p["author_association"]) for p in listed] == [
        (2, "CONTRIBUTOR"),
        (3, "NONE"),
    ]


def test_pr_list_external_on_gitlab_looks_each_author_up_once(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    member = {**GL_PULL, "iid": 1, "author": {"id": 10, "username": "in"}}
    outsider = {**GL_PULL, "iid": 2, "author": {"id": 20, "username": "out"}}
    again = {**outsider, "iid": 3}
    forge_env.reply("glab", "mr", "list", json_out=[member, outsider, again])
    forge_env.reply("glab", "api", "projects/:fullpath/members/all/10", json_out={"id": 10})
    forge_env.reply(
        "glab", "api", "projects/:fullpath/members/all/20", stderr="glab: 404 Not Found (HTTP 404)\n",
        code=1,
    )  # fmt: skip
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "list", "--external") == 0

    lookups = [a for a in forge_env.argvs("glab") if a[:1] == ("api",)]
    assert lookups == [
        ("api", "projects/:fullpath/members/all/10"),
        ("api", "projects/:fullpath/members/all/20"),
    ]
    listed = _out(capsys)
    assert [p["number"] for p in listed] == [2, 3]
    assert all("author_association" not in p for p in listed)


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [
        (GITHUB_URL, "gh", ("pr", "diff", "5", "--color", "never")),
        (GITLAB_URL, "glab", ("mr", "diff", "5", "--color", "never", "--raw")),
    ],
)
def test_pr_diff_prints_the_diff_as_is(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    forge_env.reply(cli, argv[0], "diff", stdout="diff --git a/x b/x\n+y\n")
    repo = forge_repo(url)

    assert _forge(repo, "pr", "diff", "5") == 0

    assert forge_env.last(cli).argv == argv
    assert capsys.readouterr().out == "diff --git a/x b/x\n+y\n"


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [(GITHUB_URL, "gh", ("pr", "checkout", "5")), (GITLAB_URL, "glab", ("mr", "checkout", "5"))],
)
def test_pr_checkout(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "pr", "checkout", "5") == 0

    assert forge_env.last(cli).argv == argv


def test_pr_comment_on_github(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://github.com/acme/app/pull/5#issuecomment-9"
    forge_env.reply("gh", "pr", "comment", stdout=f"{url}\n")
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "pr", "comment", "5", "--body", "LGTM") == 0

    call = forge_env.last("gh")
    assert (call.argv, call.stdin) == (("pr", "comment", "5", "--body-file", "-"), "LGTM")
    assert capsys.readouterr().out == f"{url}\n"


def test_pr_comment_on_gitlab_uses_mr_note_create_on_stdin(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://gitlab.com/acme/app/-/merge_requests/5#note_91"
    forge_env.reply("glab", "mr", "note", stdout=f"{url}\n")
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "comment", "5", "--body", "/approve\nLGTM") == 0

    call = forge_env.last("glab")
    assert call.argv == ("mr", "note", "create", "5", "--resolvable=false")
    assert call.stdin == " /approve\nLGTM"
    assert capsys.readouterr().out == f"{url}\n"


def test_pr_comment_reply_on_github_posts_to_the_review_thread(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("gh", "api", json_out={"id": 99, "html_url": "https://x/5#discussion_r99"})
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "pr", "comment", "5", "--reply-to", "72", "--body", "Done.") == 0

    call = forge_env.last("gh")
    assert call.argv == (
        "api", "--method", "POST", "repos/{owner}/{repo}/pulls/5/comments/72/replies", "-F",
        "body=@-",
    )  # fmt: skip
    assert call.stdin == "Done."
    assert capsys.readouterr().out == "https://x/5#discussion_r99\n"


def test_pr_comment_reply_on_gitlab_posts_into_the_note_discussion(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    discussions = [{"id": "d1", "notes": [{"id": 80}]}, {"id": "d2", "notes": [{"id": 81}]}]
    forge_env.reply("glab", "api", "--paginate", json_out=discussions)
    forge_env.reply("glab", "api", "--method", json_out={"id": 95})
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "comment", "5", "--reply-to", "81", "--body", "/x Done.") == 0

    call = forge_env.last("glab")
    assert call.argv == (
        "api", "--method", "POST", "projects/:fullpath/merge_requests/5/discussions/d2/notes",
        "-F", "body=@-",
    )  # fmt: skip
    assert call.stdin == " /x Done."
    assert capsys.readouterr().out == "https://gitlab.com/acme/app/-/merge_requests/5#note_95\n"


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [
        (GITHUB_URL, "gh", ("pr", "edit", "5", "--add-label", "a", "--remove-label", "b")),
        (GITLAB_URL, "glab", ("mr", "update", "5", "--label", "a", "--unlabel", "b")),
    ],
)
def test_pr_label(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "pr", "label", "5", "--add", "a", "--remove", "b") == 0

    assert forge_env.last(cli).argv == argv


def test_pr_close_on_github(forge_repo: Callable[..., Path], forge_env: ForgeEnv) -> None:
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "pr", "close", "5", "--comment", "Superseded.") == 0

    assert forge_env.argvs("gh") == [("pr", "close", "5", "--comment", "Superseded.")]


def test_pr_close_on_gitlab_posts_the_note_then_closes(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "close", "5", "--comment", "Superseded.") == 0

    calls = [c for c in forge_env.calls("glab") if c.argv[0] != "config"]
    assert [c.argv for c in calls] == [
        ("mr", "note", "create", "5", "--resolvable=false"),
        ("mr", "close", "5"),
    ]
    assert calls[0].stdin == "Superseded."


def test_a_failed_pr_close_after_the_note_exits_1_naming_the_note(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://gitlab.com/acme/app/-/merge_requests/5#note_96"
    forge_env.reply("glab", "mr", "note", stdout=f"{url}\n")
    forge_env.reply("glab", "mr", "close", stderr="ERROR: 409\n", code=1)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "close", "5", "--comment", "Superseded.") == 1

    assert f"posted the note {url}" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [
        (GITHUB_URL, "gh", ("pr", "ready", "5")),
        (GITLAB_URL, "glab", ("mr", "update", "5", "--ready")),
    ],
)
def test_pr_ready(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "pr", "ready", "5") == 0

    assert forge_env.last(cli).argv == argv


@pytest.mark.parametrize(
    ("url", "cli", "argv", "stdin"),
    [
        (GITHUB_URL, "gh", ("pr", "edit", "5", "--title", "T", "--body-file", "-"), "/b"),
        (
            GITLAB_URL,
            "glab",
            ("mr", "update", "5", "--title", "T", "--description-file", "-"),
            " /b",
        ),
    ],
)
def test_pr_edit(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    cli: str,
    argv: tuple[str, ...],
    stdin: str,
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "pr", "edit", "5", "--title", "T", "--body", "/b") == 0

    call = forge_env.last(cli)
    assert (call.argv, call.stdin) == (argv, stdin)


def test_pr_edit_refuses_a_skip_ci_title_on_gitlab(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "edit", "5", "--title", "x [skip ci]") == 1

    assert not [c for c in forge_env.calls("glab") if c.argv[0] == "mr"]


def test_pr_checks_on_github_reads_each_bucket(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    checks = [
        {"name": "test", "state": "SUCCESS", "bucket": "pass", "link": "https://x/1"},
        {"name": "lint", "state": "IN_PROGRESS", "bucket": "pending", "link": "https://x/2"},
        {"name": "docs", "state": "FAILURE", "bucket": "fail", "link": "https://x/3"},
        {"name": "skip", "state": "NEUTRAL", "bucket": "skipping", "link": ""},
    ]
    forge_env.reply("gh", "pr", "checks", json_out=checks)
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "pr", "checks", "5") == 0

    assert forge_env.last("gh").argv == (
        "pr", "checks", "5", "--json", "name,state,bucket,link,workflow",
    )  # fmt: skip
    assert _out(capsys) == [
        {"name": "test", "state": "pass", "url": "https://x/1"},
        {"name": "lint", "state": "pending", "url": "https://x/2"},
        {"name": "docs", "state": "fail", "url": "https://x/3"},
        {"name": "skip", "state": "skipped", "url": ""},
    ]


def test_pr_checks_on_gitlab_reads_the_jobs_of_the_merge_request_pipeline(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    jobs = [
        {"name": "test", "status": "success", "web_url": "https://x/j1"},
        {"name": "deploy", "status": "manual", "web_url": "https://x/j2"},
        {"name": "lint", "status": "failed", "web_url": "https://x/j3"},
        {"name": "flaky", "status": "failed", "allow_failure": True, "web_url": "https://x/j4"},
        {"name": "build", "status": "running", "web_url": "https://x/j5"},
    ]
    forge_env.reply("glab", "ci", "get", json_out={"id": 300, "status": "running", "jobs": jobs})
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "pr", "checks", "5") == 0

    assert forge_env.last("glab").argv == ("ci", "get", "--merge-request", "5", "-F", "json")
    assert [(c["name"], c["state"]) for c in _out(capsys)] == [
        ("test", "pass"),
        ("deploy", "skipped"),
        ("lint", "fail"),
        ("flaky", "skipped"),
        ("build", "pending"),
    ]


@pytest.mark.parametrize(
    ("url", "cli", "argv", "stderr"),
    [
        (GITHUB_URL, "gh", ("pr", "checks"), "no checks reported on the 'feat/x' branch\n"),
        (GITLAB_URL, "glab", ("ci", "get"), "no pipeline found for merge request !5\n"),
    ],
)
def test_pr_checks_without_any_is_an_empty_list(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
    argv: tuple[str, ...],
    stderr: str,
) -> None:
    forge_env.reply(cli, *argv, stderr=stderr, code=1)
    repo = forge_repo(url)

    assert _forge(repo, "pr", "checks", "5") == 0

    assert _out(capsys) == []


def test_ref_view_on_github_reads_a_pull_request_first(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("gh", "pr", "view", json_out=GH_PULL)
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "ref", "view", "#5") == 0

    assert _out(capsys)["kind"] == "pull_request"


def test_ref_view_on_github_falls_back_to_the_issue(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("gh", "pr", "view", stderr="no pull requests found\n", code=1)
    forge_env.reply("gh", "issue", "view", json_out={"number": 3, "state": "OPEN"})
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "ref", "view", "3") == 0

    assert [a[:3] for a in forge_env.argvs("gh")] == [("pr", "view", "3"), ("issue", "view", "3")]
    shown = _out(capsys)
    assert (shown["kind"], shown["number"]) == ("issue", 3)


@pytest.mark.parametrize(
    ("url", "ref", "argv", "kind"),
    [
        (GITLAB_URL, "#3", ("issue", "view", "3", "-F", "json"), "issue"),
        (GITLAB_URL, "3", ("issue", "view", "3", "-F", "json"), "issue"),
        (GITLAB_URL, "!5", ("mr", "view", "5", "-F", "json"), "pull_request"),
        (
            GITLAB_URL,
            "https://gitlab.com/acme/sub/app/-/merge_requests/5#note_1",
            ("mr", "view", "5", "-F", "json", "-R", "acme/sub/app"),
            "pull_request",
        ),
        (
            GITHUB_URL,
            "https://github.com/other/lib/issues/3",
            ("issue", "view", "3", "--json", "number,url,title,body,state,labels,assignees,author,"
             "createdAt,updatedAt", "-R", "other/lib"),
            "issue",
        ),
    ],
)  # fmt: skip
def test_ref_view_reads_short_references_and_urls(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    ref: str,
    argv: tuple[str, ...],
    kind: str,
) -> None:
    cli = "gh" if url == GITHUB_URL else "glab"
    forge_env.reply(cli, argv[0], "view", json_out=GH_PULL if cli == "gh" else GL_PULL)
    repo = forge_repo(url)

    assert _forge(repo, "ref", "view", ref) == 0

    assert forge_env.last(cli).argv == argv
    assert _out(capsys)["kind"] == kind


@pytest.mark.parametrize(
    ("url", "cli", "argv", "reply"),
    [
        (
            GITHUB_URL,
            "gh",
            ("label", "list", "--json", "name,color,description", "--limit", "1000"),
            [{"name": "bug", "color": "D73A4A", "description": "Broken"}],
        ),
        (
            GITLAB_URL,
            "glab",
            ("label", "list", "-F", "json", "--page", "1", "--per-page", "100"),
            [{"id": 1, "name": "bug", "color": "#d73a4a", "description": "Broken"}],
        ),
    ],
)
def test_label_list(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
    argv: tuple[str, ...],
    reply: list[dict[str, object]],
) -> None:
    forge_env.reply(cli, "label", "list", json_out=reply)
    repo = forge_repo(url)

    assert _forge(repo, "label", "list") == 0

    assert forge_env.last(cli).argv == argv
    assert _out(capsys) == [{"name": "bug", "color": "d73a4a", "description": "Broken"}]


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [
        (
            GITHUB_URL,
            "gh",
            ("label", "create", "ready", "--color", "0e8a16", "--description", "Go"),
        ),
        (
            GITLAB_URL,
            "glab",
            ("label", "create", "--name", "ready", "--color", "#0e8a16", "--description", "Go"),
        ),
    ],
)
def test_label_create(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    repo = forge_repo(url)

    code = _forge(repo, "label", "create", "ready", "--color", "#0E8A16", "--description", "Go")

    assert code == 0
    assert forge_env.last(cli).argv == argv


@pytest.mark.parametrize(
    ("url", "cli", "host"), [(GITHUB_URL, "gh", "github.com"), (GITLAB_URL, "glab", "gitlab.com")]
)
def test_auth_status(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
    host: str,
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "auth", "status") == 0

    active = ("--active",) if cli == "gh" else ()
    assert forge_env.last(cli).argv == ("auth", "status", "--hostname", host, *active)
    assert "-t" not in forge_env.last(cli).argv
    assert _out(capsys) == {"forge": url and ("github" if cli == "gh" else "gitlab"), "host": host,
                            "logged_in": True}  # fmt: skip


@pytest.mark.parametrize(("url", "cli"), [(GITHUB_URL, "gh"), (GITLAB_URL, "glab")])
def test_auth_status_logged_out_exits_2_with_the_login_step(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
) -> None:
    forge_env.reply(cli, "auth", "status", stderr="not logged in\n", code=1)
    forge_env.reply(cli, "api", stderr="401 Unauthorized\n", code=1)
    repo = forge_repo(url)

    assert _forge(repo, "auth", "status") == 2

    assert f"run `{cli} auth login --hostname" in capsys.readouterr().err


def test_auth_status_on_gitlab_counts_a_working_environment_token(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    forge_env.reply("glab", "auth", "status", stderr="has not been authenticated\n", code=1)
    forge_env.reply("glab", "api", "--hostname", json_out={"username": "max"})
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "auth", "status") == 0

    assert forge_env.last("glab").argv == ("api", "--hostname", "gitlab.com", "user")


def test_auth_status_on_gitlab_exits_1_when_the_forge_does_not_answer(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "auth", "status", stderr="has not been authenticated\n", code=1)
    forge_env.reply("glab", "api", stderr="dial tcp: lookup gitlab.com: no such host\n", code=1)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "auth", "status") == 1

    assert capsys.readouterr().err == "dial tcp: lookup gitlab.com: no such host\n"


def test_pr_create_reads_a_template_path_as_its_body_file(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITLAB_URL)
    template = repo / ".gitlab" / "merge_request_templates" / "Default.md"
    template.parent.mkdir(parents=True)
    template.write_text("## Why\n/assign me\n", encoding="utf-8")

    assert _forge(repo, "pr", "create", "--title", "X", "--template", str(template)) == 0

    call = forge_env.last("glab")
    assert "--template" not in call.argv
    assert call.stdin == "## Why\n /assign me\n"


def test_a_template_and_a_body_together_exit_1(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "pr", "create", "--title", "X", "--body", "b", "--template", "t.md") == 1

    assert "give one of --body, --template" in capsys.readouterr().err


def test_ref_view_refuses_a_url_on_another_host(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "ref", "view", "https://gitlab.example.org/a/b/-/issues/3") == 1

    assert "the reference is on gitlab.example.org" in capsys.readouterr().err
    assert not [c for c in forge_env.calls("glab") if c.argv[0] == "issue"]
