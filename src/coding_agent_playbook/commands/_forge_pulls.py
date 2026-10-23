"""The ``pr …`` forge operations on GitHub (``gh pr``) and GitLab (``glab mr``) (spec prF §6.3).

One handler per operation, each taking an :class:`~._forge_op.Op`. ``pr
create`` never pushes (Q43): the branch must already be on the push remote,
else exit 2 with the ``git push -u`` step, and ``glab mr create`` runs without
``--fill`` (which pushes even with ``--push=false``). On GitLab a title with a
skip-CI marker is refused for ``pr create`` and ``pr edit`` (Q55), and every
body goes on stdin with its quick actions neutralised (Q40).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.commands import _forge_shape as shape
from coding_agent_playbook.commands._forge_issues import gitlab_notes
from coding_agent_playbook.commands._forge_op import (
    Outcome,
    created,
    items,
    printed,
    url_in,
    written,
)
from coding_agent_playbook.commands._forge_stop import ForgeStop, detached_head, not_pushed
from coding_agent_playbook.forge.operations import OPERATIONS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.commands._forge_op import Op
    from coding_agent_playbook.commands._forge_repo import ForgeRemote

__all__ = ["PULL_HANDLERS", "pull_source", "pull_url"]

_MR: Final = "merge_requests"
#: ``pr close --comment`` posts its note as ``pr comment`` does.
_PR_COMMENT: Final = next(operation for operation in OPERATIONS if operation.name == "pr comment")
#: ``pr list --state`` (a catalogue choice): the ``glab mr list`` flags of each state.
_GLAB_STATE_FLAGS: Final = {
    "open": (),
    "closed": ("--closed",),
    "merged": ("--merged",),
    "all": ("--all",),
}
#: The author associations of people inside a GitHub repository (``--external`` drops them).
_INSIDERS: Final = frozenset({"OWNER", "MEMBER", "COLLABORATOR"})
_GH_CHECK_FIELDS: Final = "name,state,bucket,link,workflow"
#: What ``gh pr checks`` and ``glab ci get --merge-request`` print when there is nothing to report.
_NO_CHECKS: Final = "no checks reported"
_NO_PIPELINE: Final = "no pipeline found"


def pull_url(op: Op, number: str) -> str:
    """The web URL of pull request ``number`` on the push remote's forge."""
    return op.web_url(_MR if op.gitlab else "pull", number)


def pull_source(remote: ForgeRemote) -> str:
    """The pull request's source: the current branch's name on the push remote.

    ``pr create`` never pushes (Q43): exit 2 on a detached ``HEAD`` and when the
    branch is not on the push remote, before any forge CLI call.
    """
    if remote.branch is None:
        raise detached_head("pr create")
    branch = remote.pushed_branch()
    if branch is None:
        raise not_pushed(remote.remote, remote.branch)
    return branch


def _create(op: Op) -> Outcome:
    call = op.call
    title = call.value("--title")
    if title is None:
        raise ForgeStop(1, "give --title")
    branch = pull_source(op.remote)
    body = op.body(call.body or "")
    base = call.value("--base")
    if op.gitlab:
        _refuse_skip_ci(op, title)
        argv = ["mr", "create", "--source-branch", branch, "--title", title]
        argv += ["--description-file", "-"]
        if base is not None:
            argv.extend(("--target-branch", base))
        if "--draft" in call.flags:
            argv.append("--draft")
        argv += ["--push=false", "--yes"]
    else:
        argv = ["pr", "create", "--head", branch, "--title", title, "--body-file", "-"]
        if base is not None:
            argv.extend(("--base", base))
        if "--draft" in call.flags:
            argv.append("--draft")
    return created(op, op.run(argv, body=body))


def _view(op: Op) -> Outcome:
    number = op.call.positional("n")
    comments = "--comments" in op.call.flags
    if op.gitlab:
        pull = shape.gitlab_pull(op.json(["mr", "view", number, "-F", "json"]))
        if comments:
            pull["comments"] = gitlab_notes(op, _MR, number)
        return printed(pull)
    fields = shape.GH_PULL_FIELDS + (",comments" if comments else "")
    item = op.json(["pr", "view", number, "--json", fields])
    pull = shape.github_pull(item)
    if comments:
        review = op.pages(
            ["api", "--paginate", f"repos/{{owner}}/{{repo}}/pulls/{number}/comments"]
        )
        pull["comments"] = [
            *(shape.github_comment(c) for c in item.get("comments") or ()),
            *(shape.github_review_comment(c) for c in review),
        ]
    return printed(pull)


def _list(op: Op) -> Outcome:
    call = op.call
    state = call.value("--state") or "open"
    label = call.value("--label")
    external = "--external" in call.flags
    if op.gitlab:
        argv = ["mr", "list", "-F", "json", *_GLAB_STATE_FLAGS[state]]
        if label is not None:
            argv.extend(("--label", label))
        found = items(op.json(argv))
        if external:
            found = _gitlab_external(op, found)
        return printed([shape.gitlab_pull(item) for item in found])
    if external:
        return printed(_github_external(op, state, label))
    argv = ["pr", "list", "--json", shape.GH_PULL_FIELDS, "--state", state]
    if label is not None:
        argv.extend(("--label", label))
    return printed([shape.github_pull(item) for item in items(op.json(argv))])


def _github_external(op: Op, state: str, label: str | None) -> list[dict[str, Any]]:
    """Pull requests by people outside the repository, with their ``author_association``."""
    rest_state = {"open": "open", "closed": "closed", "merged": "closed"}.get(state, "all")
    path = f"repos/{{owner}}/{{repo}}/pulls?state={rest_state}&per_page=100"
    found = []
    for item in op.pages(["api", "--paginate", path]):
        if not isinstance(item, dict) or item.get("author_association") in _INSIDERS:
            continue
        pull = shape.github_rest_pull(item)
        if (state == "merged" and pull["state"] != "merged") or (
            state == "closed" and pull["state"] != "closed"
        ):
            continue
        if label is not None and label not in pull["labels"]:
            continue
        found.append({**pull, "author_association": item.get("author_association", "")})
    return found


def _gitlab_external(op: Op, items: list[Any]) -> list[Any]:
    """The merge requests whose author is no member of the project: one lookup per author."""
    members: dict[object, bool] = {}
    kept = []
    for item in items:
        author = (item.get("author") or {}) if isinstance(item, dict) else {}
        user_id = author.get("id")
        if user_id not in members:
            done = op.run(["api", f"projects/:fullpath/members/all/{user_id}"], check=False)
            if done.code != 0 and not _not_found(done.stdout + done.stderr):
                raise op.cli.failure(done)
            members[user_id] = done.code == 0
        if not members[user_id]:
            kept.append(item)
    return kept


def _diff(op: Op) -> Outcome:
    """The diff as the CLI prints it (``glab mr diff --raw``: with ``diff --git`` headers)."""
    return Outcome(stdout=op.run(op.argv()).stdout)


def _checkout(op: Op) -> Outcome:
    done = op.run(op.argv())
    return Outcome(stdout=done.stdout, stderr=done.stderr)


def _comment(op: Op) -> Outcome:
    call = op.call
    number = call.positional("n")
    if call.body is None:
        raise ForgeStop(1, "give --body or --body-file")
    reply_to = call.value("--reply-to")
    if op.gitlab:
        if reply_to is not None:
            return written(op, _gitlab_reply(op, number, reply_to))
        return written(op, _gitlab_mr_note(op, number, call.body))
    if reply_to is not None:
        path = f"repos/{{owner}}/{{repo}}/pulls/{number}/comments/{reply_to}/replies"
        reply = op.json(["api", "--method", "POST", path, "-F", "body=@-"], body=call.body)
        url = reply.get("html_url") if isinstance(reply, dict) else None
        return written(op, str(url or pull_url(op, number)))
    done = op.run(["pr", "comment", number, "--body-file", "-"], body=call.body)
    return written(op, url_in(done.stdout) or pull_url(op, number))


def _gitlab_mr_note(op: Op, number: str, body: str) -> str:
    """Post ``body`` as a note on merge request ``number`` with ``glab mr note create`` (stdin)."""
    # the `pr comment` row's words: glab opens a resolvable thread without --resolvable=false
    note = _PR_COMMENT.translation(op.remote.forge)
    if note is None:  # pragma: no cover - every forge runs `pr comment`
        raise ForgeStop(3, "this forge has no pull request comments")
    done = op.run([*note.argv, number, *note.fixed], body=op.body(body))
    return url_in(done.stdout) or pull_url(op, number)


def _gitlab_reply(op: Op, number: str, note_id: str) -> str:
    """Reply to note ``note_id`` inside its discussion on merge request ``number`` (Q22)."""
    path = f"projects/:fullpath/{_MR}/{number}/discussions?per_page=100"
    for discussion in op.pages(["api", "--paginate", path]):
        notes = discussion.get("notes") or () if isinstance(discussion, dict) else ()
        if any(str(note.get("id")) == note_id for note in notes if isinstance(note, dict)):
            path = f"projects/:fullpath/{_MR}/{number}/discussions/{discussion.get('id')}/notes"
            argv = ["api", "--method", "POST", path, "-F", "body=@-"]
            reply = op.json(argv, body=op.body())
            reply_id = reply.get("id") if isinstance(reply, dict) else None
            return f"{pull_url(op, number)}#note_{reply_id}"
    raise ForgeStop(1, f"no comment {note_id} on pull request #{number}")


def _label(op: Op) -> Outcome:
    if not op.call.options:
        raise ForgeStop(1, "give --add and/or --remove")
    return _change(op, op.argv())


def _close(op: Op) -> Outcome:
    number = op.call.positional("n")
    comment = op.call.value("--comment")
    if not op.gitlab:
        argv = ["pr", "close", number]
        if comment is not None:
            argv.extend(("--comment", comment))
        op.run(argv)
        return written(op, pull_url(op, number))
    note_url = _gitlab_mr_note(op, number, comment) if comment is not None else None
    done = op.run(["mr", "close", number], check=False)
    if done.code != 0:
        stop = op.cli.failure(done)
        if note_url is not None and stop.code == 1:
            message = f"posted the note {note_url}, but closing pull request #{number} failed"
            raise ForgeStop(1, message, passthrough=done.stderr)
        raise stop
    return written(op, pull_url(op, number))


def _ready(op: Op) -> Outcome:
    return _change(op, op.argv())


def _edit(op: Op) -> Outcome:
    title = op.call.value("--title")
    if title is None and op.call.body is None:
        raise ForgeStop(1, "give --title and/or --body / --body-file")
    if op.gitlab and title is not None:
        _refuse_skip_ci(op, title)
    return _change(op, op.argv(), body=op.body())


def _change(op: Op, argv: list[str], *, body: str | None = None) -> Outcome:
    number = op.call.positional("n")
    done = op.run(argv, body=body)
    return written(op, url_in(done.stdout) or pull_url(op, number))


def _checks(op: Op) -> Outcome:
    """The pull request's checks: ``gh pr checks``, or the jobs of its pipeline on GitLab.

    A pull request without checks or pipeline is an empty list, not an error.
    """
    number = op.call.positional("n")
    if op.gitlab:
        argv = ["ci", "get", "--merge-request", number, "-F", "json"]
        done = op.run(argv, check=False)
        if done.code != 0 and _NO_PIPELINE in done.stderr:
            return printed([])
        if done.code != 0:
            raise op.cli.failure(done)
        pipeline: Any = next(iter(op.cli.pages(done, argv)), {})
        jobs = pipeline.get("jobs") or () if isinstance(pipeline, dict) else ()
        return printed([shape.gitlab_job(job) for job in jobs])
    argv = ["pr", "checks", number, "--json", _GH_CHECK_FIELDS]
    done = op.run(argv, check=False)
    if done.code != 0 and _NO_CHECKS in done.stderr:
        return printed([])
    if done.code != 0:
        raise op.cli.failure(done)
    return printed([shape.github_check(check) for check in op.cli.pages(done, argv)])


def _refuse_skip_ci(op: Op, title: str) -> None:
    """Exit 1 for a GitLab title holding a skip-CI marker: the pipeline would not run (Q55)."""
    lowered = title.lower()
    for marker in op.remote.forge.skip_ci_markers:
        if marker in lowered:
            raise ForgeStop(1, f"the title holds {marker}, which skips the pipeline; drop it")


def _not_found(output: str) -> bool:
    return "404" in output or "not found" in output.lower()


PULL_HANDLERS: Final[Mapping[str, Callable[[Op], Outcome]]] = {
    "pr create": _create,
    "pr view": _view,
    "pr list": _list,
    "pr diff": _diff,
    "pr checkout": _checkout,
    "pr comment": _comment,
    "pr label": _label,
    "pr close": _close,
    "pr ready": _ready,
    "pr edit": _edit,
    "pr checks": _checks,
}
