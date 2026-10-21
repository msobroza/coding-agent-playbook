"""``playbook forge issue …`` and ``label …``: one GitHub and one GitLab case per operation (spec prF §6.3).

Fake ``gh`` / ``glab`` on ``PATH`` record argv and stdin and answer with
canned JSON (``tests/cli/forge_fakes``); each row checks the forge CLI call
and what ``playbook forge`` prints: one JSON vocabulary for reads, the URL for
writes.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING, Final

import pytest

from coding_agent_playbook.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from tests.cli.forge_fakes import ForgeEnv

GITHUB_URL: Final = "git@github.com:acme/app.git"
GITLAB_URL: Final = "git@gitlab.com:acme/app.git"

GH_ISSUE: Final = {
    "number": 3,
    "url": "https://github.com/acme/app/issues/3",
    "title": "Crash on start",
    "body": "It crashes.",
    "state": "OPEN",
    "labels": [{"id": "LA_1", "name": "bug", "color": "d73a4a", "description": ""}],
    "assignees": [{"id": "U_1", "login": "max", "name": "Max"}],
    "author": {"id": "U_2", "login": "ann", "name": "Ann", "is_bot": False},
    "createdAt": "2026-10-01T10:00:00Z",
    "updatedAt": "2026-10-02T10:00:00Z",
}
GL_ISSUE: Final = {
    "id": 9001,
    "iid": 3,
    "project_id": 77,
    "web_url": "https://gitlab.com/acme/app/-/issues/3",
    "title": "Crash on start",
    "description": "It crashes.",
    "state": "opened",
    "labels": ["bug"],
    "assignees": [{"id": 1, "username": "max", "name": "Max"}],
    "author": {"id": 2, "username": "ann", "name": "Ann"},
    "created_at": "2026-10-01T10:00:00.000Z",
    "updated_at": "2026-10-02T10:00:00.000Z",
    "confidential": True,
}
#: The issue both forges print, in the one vocabulary (spec §6.3 rules).
ISSUE: Final = {
    "number": 3,
    "url": "",
    "title": "Crash on start",
    "body": "It crashes.",
    "state": "open",
    "labels": ["bug"],
    "assignees": ["max"],
    "author": "ann",
    "created_at": "",
    "updated_at": "",
    "confidential": False,
}


def _forge(repo: Path, *words: str) -> int:
    return main(["forge", "-C", str(repo), *words])


def _expected(**changes: object) -> dict[str, object]:
    return {**ISSUE, **changes}


def test_issue_view_on_github(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("gh", "issue", "view", json_out=GH_ISSUE)
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "view", "3") == 0

    call = forge_env.last("gh")
    assert call.argv[:3] == ("issue", "view", "3")
    assert call.argv[3] == "--json"
    assert set(call.argv[4].split(",")) >= {"number", "url", "title", "body", "state"}
    assert call.env["GH_HOST"] == "github.com"
    assert json.loads(capsys.readouterr().out) == _expected(
        url="https://github.com/acme/app/issues/3",
        created_at="2026-10-01T10:00:00Z",
        updated_at="2026-10-02T10:00:00Z",
    )


def test_issue_view_on_gitlab(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "issue", "view", json_out=GL_ISSUE)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "view", "3") == 0

    call = forge_env.last("glab")
    assert call.argv == ("issue", "view", "3", "-F", "json")
    assert call.env["GITLAB_HOST"] == "https://gitlab.com"
    assert json.loads(capsys.readouterr().out) == _expected(
        url="https://gitlab.com/acme/app/-/issues/3",
        created_at="2026-10-01T10:00:00.000Z",
        updated_at="2026-10-02T10:00:00.000Z",
        confidential=True,
    )


def test_issue_view_with_comments_on_github(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    comment = {
        "id": "IC_kwDO",
        "author": {"login": "bob"},
        "body": "Same here.",
        "createdAt": "2026-10-03T10:00:00Z",
        "url": "https://github.com/acme/app/issues/3#issuecomment-9911",
    }
    forge_env.reply("gh", "issue", "view", json_out={**GH_ISSUE, "comments": [comment]})
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "view", "3", "--comments") == 0

    assert "comments" in forge_env.last("gh").argv[4].split(",")
    assert json.loads(capsys.readouterr().out)["comments"] == [
        {
            "id": 9911,
            "author": "bob",
            "body": "Same here.",
            "created_at": "2026-10-03T10:00:00Z",
            "path": None,
        }
    ]


def test_issue_view_with_comments_on_gitlab_reads_every_page_without_system_notes(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    note = {"id": 11, "body": "Same here.", "author": {"username": "bob"}, "system": False}
    system = {"id": 12, "body": "changed the description", "author": {}, "system": True}
    page_two = {**note, "id": 13, "body": "Still."}
    forge_env.reply("glab", "issue", "view", json_out=GL_ISSUE)
    forge_env.reply(
        "glab", "api", stdout=json.dumps([note, system]) + "\n" + json.dumps([page_two]) + "\n"
    )
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "view", "3", "--comments") == 0

    assert forge_env.last("glab").argv == (
        "api",
        "--paginate",
        "projects/:fullpath/issues/3/notes?sort=asc&order_by=created_at&per_page=100",
    )
    comments = json.loads(capsys.readouterr().out)["comments"]
    assert [(c["id"], c["body"]) for c in comments] == [(11, "Same here."), (13, "Still.")]


def test_issue_create_on_github_sends_the_body_on_stdin(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("gh", "issue", "create", stdout="https://github.com/acme/app/issues/7\n")
    repo = forge_repo(GITHUB_URL)

    code = _forge(
        repo, "issue", "create", "--title", "Add X", "--body", "/close\nWhy.",
        "--label", "a", "--label", "b", "--assignee", "@me", "--parent", "2", "--blocked-by", "4,5",
    )  # fmt: skip

    assert code == 0
    call = forge_env.last("gh")
    assert call.argv == (
        "issue", "create", "--title", "Add X", "--body-file", "-", "--label", "a",
        "--label", "b", "--assignee", "@me", "--parent", "2", "--blocked-by", "4,5",
    )  # fmt: skip
    assert call.stdin == "/close\nWhy."
    assert capsys.readouterr().out == "https://github.com/acme/app/issues/7\n"


def test_issue_create_on_gitlab_neutralises_quick_actions_and_never_puts_the_body_on_argv(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "issue", "create", stdout="https://gitlab.com/acme/app/-/issues/7\n")
    repo = forge_repo(GITLAB_URL)

    code = _forge(
        repo, "--json", "issue", "create", "--title", "Add X", "--body", "/close\nWhy.\n/label ~x",
        "--label", "a", "--assignee", "@me", "--confidential",
    )  # fmt: skip

    assert code == 0
    call = forge_env.last("glab")
    assert call.argv == (
        "issue", "create", "--title", "Add X", "--description-file", "-", "--label", "a",
        "--assignee", "@me", "--confidential", "--yes",
    )  # fmt: skip
    assert call.stdin == " /close\nWhy.\n /label ~x"
    assert json.loads(capsys.readouterr().out) == {"url": "https://gitlab.com/acme/app/-/issues/7"}


def test_issue_create_reads_the_body_from_a_file(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, tmp_path: Path
) -> None:
    body = tmp_path / "body.md"
    body.write_text("From a file.\n", encoding="utf-8")
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "create", "--title", "X", "--body-file", str(body)) == 0

    assert forge_env.last("gh").stdin == "From a file.\n"


def test_issue_create_reads_the_body_from_stdin(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("From stdin.\n"))
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "create", "--title", "X", "--body-file", "-") == 0

    assert forge_env.last("glab").stdin == "From stdin.\n"


def test_issue_create_confidential_exits_3_on_github(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "create", "--title", "X", "--confidential") == 3

    assert "`issue create --confidential` is not available on github" in capsys.readouterr().err
    assert forge_env.calls("gh") == []


def test_issue_create_parent_exits_3_on_gitlab(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "create", "--title", "X", "--parent", "2") == 3

    assert forge_env.calls("glab") == []


def test_issue_create_blocked_by_on_gitlab_links_each_blocker_once_the_issue_exists(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://gitlab.com/acme/app/-/issues/7"
    forge_env.reply(
        "glab", "api", "projects/:fullpath/issues/4", json_out={"iid": 4, "weight": None}
    )
    forge_env.reply("glab", "api", "projects/:fullpath", json_out={"id": 77}, once=True)
    forge_env.reply("glab", "issue", "create", stdout=f"{url}\n")
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "create", "--title", "X", "--blocked-by", "#4, 5") == 0

    argvs = [a for a in forge_env.argvs("glab") if a[0] in {"issue", "api"}]
    assert argvs[1][-1] == "--yes" and "--linked-issues" not in argvs[1]
    assert [a[3] for a in argvs if a[1:3] == ("--method", "POST")] == [
        "projects/:fullpath/issues/7/links",
        "projects/:fullpath/issues/7/links",
    ]
    assert [a[-3] for a in argvs if a[1:3] == ("--method", "POST")] == [
        "target_issue_iid=4",
        "target_issue_iid=5",
    ]
    assert capsys.readouterr().out == f"{url}\n"


def test_a_failed_blocker_link_after_create_exits_1_naming_the_new_issue(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://gitlab.com/acme/app/-/issues/7"
    forge_env.reply("glab", "api", "projects/:fullpath/issues/4", json_out={"iid": 4, "weight": 1})
    forge_env.reply("glab", "api", "projects/:fullpath", json_out={"id": 77}, once=True)
    forge_env.reply("glab", "api", "--method", stderr="glab: 404 Not found (HTTP 404)\n", code=1)
    forge_env.reply("glab", "issue", "create", stdout=f"{url}\n")
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "create", "--title", "X", "--blocked-by", "4") == 1

    assert f"created {url}, but linking it as blocked by #4 failed" in capsys.readouterr().err


def test_issue_create_blocked_by_exits_3_before_creating_on_a_gitlab_plan_without_links(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "api", "projects/:fullpath/issues/4", json_out={"iid": 4})
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "create", "--title", "X", "--blocked-by", "4") == 3

    assert "blocking links need GitLab Premium" in capsys.readouterr().err
    assert not [a for a in forge_env.argvs("glab") if a[:2] == ("issue", "create")]


@pytest.mark.parametrize(
    ("url", "argv", "out"),
    [
        (
            GITHUB_URL,
            ("issue", "list", "--json", "number,url,title,body,state,labels,assignees,author,"
             "createdAt,updatedAt", "--state", "closed", "--assignee", "max",
             "--limit", "5", "--search", "crash no:label"),
            GH_ISSUE,
        ),
        (
            GITLAB_URL,
            ("issue", "list", "-O", "json", "--closed", "--label", "None", "--assignee", "max",
             "--search", "crash", "--page", "1", "--per-page", "5"),
            GL_ISSUE,
        ),
    ],
)  # fmt: skip
def test_issue_list(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    argv: tuple[str, ...],
    out: dict[str, object],
) -> None:
    cli = "gh" if url == GITHUB_URL else "glab"
    forge_env.reply(cli, "issue", "list", json_out=[out])
    repo = forge_repo(url)

    code = _forge(
        repo, "issue", "list", "--state", "closed", "--no-label", "--assignee", "max",
        "--limit", "5", "--search", "crash",
    )  # fmt: skip

    assert code == 0
    assert forge_env.last(cli).argv == argv
    (listed,) = json.loads(capsys.readouterr().out)
    assert (listed["number"], listed["state"], listed["labels"]) == (3, "open", ["bug"])


def test_issue_list_labels_are_repeated_on_github_and_joined_on_gitlab(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    forge_env.reply("glab", "issue", "list", json_out=[])
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "list", "--label", "a", "--label", "b") == 0

    assert forge_env.last("glab").argv == (
        "issue", "list", "-O", "json", "--label", "a,b", "--page", "1", "--per-page", "30",
    )  # fmt: skip


def test_issue_list_on_gitlab_reads_pages_up_to_the_limit(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    page = [{**GL_ISSUE, "iid": n} for n in range(100)]
    forge_env.reply("glab", "issue", "list", json_out=page, once=True)
    forge_env.reply("glab", "issue", "list", json_out=page, once=True)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "list", "--limit", "150") == 0

    assert [a[-4:] for a in forge_env.argvs("glab") if a[:2] == ("issue", "list")] == [
        ("--page", "1", "--per-page", "100"),
        ("--page", "2", "--per-page", "100"),
    ]
    assert len(json.loads(capsys.readouterr().out)) == 150


def test_issue_comment_on_github(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    url = "https://github.com/acme/app/issues/3#issuecomment-1"
    forge_env.reply("gh", "issue", "comment", stdout=f"{url}\n")
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "comment", "3", "--body", "Looks good.") == 0

    call = forge_env.last("gh")
    assert (call.argv, call.stdin) == (("issue", "comment", "3", "--body-file", "-"), "Looks good.")
    assert capsys.readouterr().out == f"{url}\n"


def test_issue_comment_on_gitlab_posts_a_note_through_the_api_from_stdin(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "api", json_out={"id": 55, "body": "x"})
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "comment", "3", "--body", "/close now") == 0

    call = forge_env.last("glab")
    assert call.argv == (
        "api", "--method", "POST", "projects/:fullpath/issues/3/notes", "-F", "body=@-",
    )  # fmt: skip
    assert call.stdin == " /close now"
    assert capsys.readouterr().out == "https://gitlab.com/acme/app/-/issues/3#note_55\n"


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [
        (GITHUB_URL, "gh", ("issue", "edit", "3", "--add-label", "a,b", "--remove-label", "c")),
        (GITLAB_URL, "glab", ("issue", "update", "3", "--label", "a,b", "--unlabel", "c")),
    ],
)
def test_issue_label(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "issue", "label", "3", "--add", "a,b", "--remove", "c") == 0

    assert forge_env.last(cli).argv == argv
    assert capsys.readouterr().out.strip().endswith("/issues/3")


@pytest.mark.parametrize(
    ("url", "cli", "argv"),
    [
        (GITHUB_URL, "gh", ("issue", "edit", "3", "--add-assignee", "@me")),
        (GITLAB_URL, "glab", ("issue", "update", "3", "--assignee", "+@me")),
    ],
)
def test_issue_assign(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    cli: str,
    argv: tuple[str, ...],
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "issue", "assign", "3", "--add", "@me") == 0

    assert forge_env.last(cli).argv == argv


@pytest.mark.parametrize(
    ("url", "cli", "argv", "stdin"),
    [
        (GITHUB_URL, "gh", ("issue", "edit", "3", "--title", "New", "--body-file", "-"), "/x"),
        (
            GITLAB_URL,
            "glab",
            ("issue", "update", "3", "--title", "New", "--description-file", "-"),
            " /x",
        ),
    ],
)
def test_issue_edit(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    url: str,
    cli: str,
    argv: tuple[str, ...],
    stdin: str,
) -> None:
    repo = forge_repo(url)

    assert _forge(repo, "issue", "edit", "3", "--title", "New", "--body", "/x") == 0

    call = forge_env.last(cli)
    assert (call.argv, call.stdin) == (argv, stdin)


def test_issue_close_on_github_is_one_call(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITHUB_URL)

    code = _forge(repo, "issue", "close", "3", "--comment", "Dup.", "--reason", "not-planned")

    assert code == 0
    assert forge_env.argvs("gh") == [
        ("issue", "close", "3", "--comment", "Dup.", "--reason", "not planned")
    ]


def test_issue_close_on_gitlab_posts_the_note_then_closes(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "api", json_out={"id": 56})
    repo = forge_repo(GITLAB_URL)

    code = _forge(repo, "issue", "close", "3", "--comment", "Dup.", "--reason", "not-planned")

    assert code == 0
    calls = [c for c in forge_env.calls("glab") if c.argv[:2] != ("config", "get")]
    assert [c.argv[:4] for c in calls] == [
        ("api", "--method", "POST", "projects/:fullpath/issues/3/notes"),
        ("issue", "close", "3"),
    ]
    assert calls[0].stdin == "Dup.\n\nClosed as not planned."
    assert capsys.readouterr().out == "https://gitlab.com/acme/app/-/issues/3\n"


def test_issue_close_on_gitlab_without_a_comment_only_closes(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "close", "3") == 0

    assert forge_env.argvs("glab")[-1] == ("issue", "close", "3")
    assert not [a for a in forge_env.argvs("glab") if a[:1] == ("api",)]


def test_a_failed_close_after_the_note_exits_1_naming_the_posted_note(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    forge_env.reply("glab", "api", json_out={"id": 57})
    forge_env.reply("glab", "issue", "close", stderr="ERROR: 500 boom\n", code=1)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "close", "3", "--comment", "Done.") == 1

    err = capsys.readouterr().err
    assert err.startswith("ERROR: 500 boom\n")
    assert "posted the note https://gitlab.com/acme/app/-/issues/3#note_57" in err


def test_issue_link_child_on_github_and_exit_3_on_gitlab(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "link-child", "2", "7") == 0

    assert forge_env.last("gh").argv == ("issue", "edit", "2", "--add-sub-issue", "7")


def test_issue_link_child_exits_3_on_gitlab(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "link-child", "2", "7") == 3

    assert forge_env.calls("glab", versions=True) == []


def test_issue_children_on_github(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    node = {"id": "I_1", "number": 7, "title": "Part", "url": "https://x/7", "state": "OPEN"}
    forge_env.reply(
        "gh", "issue", "view", json_out={"subIssues": {"nodes": [node], "totalCount": 1}}
    )
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "children", "2") == 0

    assert forge_env.last("gh").argv == ("issue", "view", "2", "--json", "subIssues")
    assert json.loads(capsys.readouterr().out) == [
        {"number": 7, "url": "https://x/7", "title": "Part", "state": "open"}
    ]


def test_issue_block_on_github(forge_repo: Callable[..., Path], forge_env: ForgeEnv) -> None:
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "block", "7", "4") == 0

    assert forge_env.last("gh").argv == ("issue", "edit", "7", "--add-blocked-by", "4")


def test_issue_block_on_gitlab_adds_a_blocking_link(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv
) -> None:
    forge_env.reply("glab", "api", "projects/:fullpath", json_out={"id": 77})
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "block", "7", "4") == 0

    assert forge_env.last("glab").argv == (
        "api", "--method", "POST", "projects/:fullpath/issues/7/links", "-f", "target_project_id=77",
        "-f", "target_issue_iid=4", "-f", "link_type=is_blocked_by",
    )  # fmt: skip


@pytest.mark.parametrize(
    "stderr",
    [
        "glab: Blocked issues not available for current license (HTTP 403)\n",
        "glab: link_type does not have a valid value (HTTP 400)\n",
    ],
)
def test_issue_block_exits_3_on_a_gitlab_plan_without_blocking_links(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    stderr: str,
) -> None:
    forge_env.reply("glab", "api", "projects/:fullpath", json_out={"id": 77})
    forge_env.reply("glab", "api", "--method", stderr=stderr, code=1)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "block", "7", "4") == 3

    assert "blocking links need GitLab Premium" in capsys.readouterr().err


def test_issue_blockers_on_github(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    node = {"id": "I_1", "number": 4, "title": "First", "url": "https://x/4", "state": "CLOSED"}
    forge_env.reply("gh", "issue", "view", json_out={"blockedBy": {"nodes": [node]}})
    repo = forge_repo(GITHUB_URL)

    assert _forge(repo, "issue", "blockers", "7") == 0

    assert forge_env.last("gh").argv == ("issue", "view", "7", "--json", "blockedBy")
    assert json.loads(capsys.readouterr().out)[0]["state"] == "closed"


@pytest.mark.parametrize(("issue", "code"), [({"iid": 7, "weight": 2}, 0), ({"iid": 7}, 3)])
def test_issue_blockers_on_gitlab_without_links_reads_the_plan(
    forge_repo: Callable[..., Path],
    forge_env: ForgeEnv,
    capsys: pytest.CaptureFixture[str],
    issue: dict[str, object],
    code: int,
) -> None:
    forge_env.reply("glab", "api", "projects/:fullpath/issues/7/links", json_out=[])
    forge_env.reply("glab", "api", "projects/:fullpath/issues/7", json_out=issue)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "blockers", "7") == code

    out = capsys.readouterr().out
    assert (json.loads(out) if code == 0 else out) == ([] if code == 0 else "")


def test_issue_blockers_on_gitlab_keeps_the_is_blocked_by_links(
    forge_repo: Callable[..., Path], forge_env: ForgeEnv, capsys: pytest.CaptureFixture[str]
) -> None:
    links = [
        {"iid": 4, "web_url": "https://x/4", "title": "First", "state": "opened",
         "link_type": "is_blocked_by"},
        {"iid": 5, "web_url": "https://x/5", "title": "Other", "state": "opened",
         "link_type": "relates_to"},
    ]  # fmt: skip
    forge_env.reply("glab", "api", json_out=links)
    repo = forge_repo(GITLAB_URL)

    assert _forge(repo, "issue", "blockers", "7") == 0

    assert forge_env.last("glab").argv == ("api", "projects/:fullpath/issues/7/links")
    assert json.loads(capsys.readouterr().out) == [
        {"number": 4, "url": "https://x/4", "title": "First", "state": "open"}
    ]
