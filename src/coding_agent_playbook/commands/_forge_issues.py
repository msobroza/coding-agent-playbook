"""The ``issue …`` forge operations on GitHub (``gh``) and GitLab (``glab``) (spec prF §6.3).

One handler per operation, each taking an :class:`~._forge_op.Op` and
returning what ``playbook forge`` prints: the issue in the one JSON vocabulary
(``_forge_shape``) for a read, the URL of the issue or comment for a write.
Every body sent to GitLab goes on stdin with its quick actions neutralised;
``glab issue note`` reads no stdin, so a GitLab comment is posted through
``glab api`` with the body read from stdin (spec §16).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.commands import _forge_shape as shape
from coding_agent_playbook.commands._forge_op import created, items, printed, url_in, written
from coding_agent_playbook.commands._forge_stop import ForgeStop, unsupported

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.commands._forge_cli import Done
    from coding_agent_playbook.commands._forge_op import Op, Outcome

__all__ = ["ISSUE_HANDLERS", "gitlab_note", "gitlab_notes"]

#: ``issue list`` without ``--limit`` lists as many issues as ``gh issue list`` does.
_DEFAULT_LIMIT: Final = 30
#: GitLab notes, oldest first, every page.
_NOTES_QUERY: Final = "sort=asc&order_by=created_at&per_page=100"
#: ``issue list --state`` (a catalogue choice): the ``glab issue list`` flags of each state.
_GLAB_STATE_FLAGS: Final = {"open": (), "closed": ("--closed",), "all": ("--all",)}
#: ``issue close --reason``: gh's own reason, and the closing line a GitLab note carries.
_GH_REASONS: Final = {
    "completed": "completed",
    "not-planned": "not planned",
    "duplicate": "duplicate",
}
_CLOSING_LINES: Final = {
    "completed": "Closed as completed.",
    "not-planned": "Closed as not planned.",
    "duplicate": "Closed as a duplicate.",
}


def gitlab_notes(op: Op, kind: str, number: str) -> list[dict[str, Any]]:
    """The user notes (system notes dropped) of GitLab issue or merge request ``number``.

    ``kind`` is ``issues`` or ``merge_requests``; every page is read.
    """
    path = f"projects/:fullpath/{kind}/{number}/notes?{_NOTES_QUERY}"
    return [
        shape.gitlab_note(note)
        for note in op.pages(["api", "--paginate", path])
        if isinstance(note, dict) and not note.get("system")
    ]


def gitlab_note(op: Op, kind: str, number: str, body: str) -> str:
    """Post ``body`` (neutralised) as a note on GitLab ``kind`` ``number``; the note's URL.

    The body goes on stdin (``-F body=@-``), never on argv (Q36).
    """
    path = f"projects/:fullpath/{kind}/{number}/notes"
    note = op.json(["api", "--method", "POST", path, "-F", "body=@-"], body=op.body(body))
    note_id = note.get("id") if isinstance(note, dict) else None
    return f"{op.web_url(kind, number)}#note_{note_id}"


def _view(op: Op) -> Outcome:
    number = op.call.positional("n")
    comments = "--comments" in op.call.flags
    if op.gitlab:
        issue = shape.gitlab_issue(op.json(["issue", "view", number, "-F", "json"]))
        if comments:
            issue["comments"] = gitlab_notes(op, "issues", number)
        return printed(issue)
    fields = shape.GH_ISSUE_FIELDS + (",comments" if comments else "")
    item = op.json(["issue", "view", number, "--json", fields])
    issue = shape.github_issue(item)
    if comments:
        issue["comments"] = [shape.github_comment(c) for c in item.get("comments") or ()]
    return printed(issue)


def _list(op: Op) -> Outcome:
    call = op.call
    state = call.value("--state") or "open"
    search = call.value("--search")
    if op.gitlab:
        words = ["issue", "list", "-O", "json", *_GLAB_STATE_FLAGS[state]]
        labels = ["None"] if "--no-label" in call.flags else list(call.values("--label"))
        if labels:
            words.extend(("--label", ",".join(labels)))
        if (assignee := call.value("--assignee")) is not None:
            words.extend(("--assignee", assignee))
        if search is not None:
            words.extend(("--search", search))
        found = op.listed(words, _limit(call.value("--limit")))
        return printed([shape.gitlab_issue(item) for item in found])
    words = ["issue", "list", "--json", shape.GH_ISSUE_FIELDS, "--state", state]
    for label in call.values("--label"):
        words.extend(("--label", label))
    for option in ("--assignee", "--limit"):
        if (value := call.value(option)) is not None:
            words.extend((option, value))
    if "--no-label" in call.flags:
        search = f"{search} no:label" if search else "no:label"
    if search is not None:
        words.extend(("--search", search))
    return printed([shape.github_issue(item) for item in items(op.json(words))])


def _comment(op: Op) -> Outcome:
    number = op.call.positional("n")
    body = _required_body(op)
    if op.gitlab:
        return written(op, gitlab_note(op, "issues", number, body))
    done = op.run(["issue", "comment", number, "--body-file", "-"], body=body)
    return written(op, url_in(done.stdout) or op.web_url("issues", number))


def _label(op: Op) -> Outcome:
    if not op.call.options:
        raise ForgeStop(1, "give --add and/or --remove")
    return _edit_issue(op, op.argv())


def _assign(op: Op) -> Outcome:
    if op.gitlab:
        number = op.call.positional("n")
        user = op.call.value("--add")
        if user is None:
            raise ForgeStop(1, "give --add <user>")
        return _edit_issue(op, ["issue", "update", number, "--assignee", f"+{user}"])
    if op.call.value("--add") is None:
        raise ForgeStop(1, "give --add <user>")
    return _edit_issue(op, op.argv())


def _edit(op: Op) -> Outcome:
    if op.call.value("--title") is None and op.call.body is None:
        raise ForgeStop(1, "give --title and/or --body / --body-file")
    return _edit_issue(op, op.argv(), body=op.body())


def _edit_issue(op: Op, argv: list[str], *, body: str | None = None) -> Outcome:
    number = op.call.positional("n")
    done = op.run(argv, body=body)
    return written(op, url_in(done.stdout) or op.web_url("issues", number))


def _close(op: Op) -> Outcome:
    call = op.call
    number = call.positional("n")
    comment, reason = call.value("--comment"), call.value("--reason")
    if not op.gitlab:
        argv = ["issue", "close", number]
        if comment is not None:
            argv.extend(("--comment", comment))
        if reason is not None:
            argv.extend(("--reason", _GH_REASONS[reason]))
        done = op.run(argv)
        return written(op, url_in(done.stdout + done.stderr) or op.web_url("issues", number))
    note_url = None
    if comment is not None or reason is not None:
        lines = [text for text in (comment, _CLOSING_LINES.get(reason or "")) if text]
        note_url = gitlab_note(op, "issues", number, "\n\n".join(lines))
    done = op.run(["issue", "close", number], check=False)
    if done.code != 0:
        stop = op.cli.failure(done)
        if note_url is not None and stop.code == 1:
            message = f"posted the note {note_url}, but closing issue #{number} failed"
            raise ForgeStop(1, message, passthrough=done.stderr)
        raise stop
    return written(op, op.web_url("issues", number))


def _link_child(op: Op) -> Outcome:
    parent, child = op.call.positional("parent"), op.call.positional("child")
    done = op.run(["issue", "edit", parent, "--add-sub-issue", child])
    return written(op, url_in(done.stdout) or op.web_url("issues", parent))


def _children(op: Op) -> Outcome:
    parent = op.call.positional("parent")
    return printed(_linked(op.json(["issue", "view", parent, "--json", "subIssues"]), "subIssues"))


def _block(op: Op) -> Outcome:
    child, blocker = op.call.positional("child"), op.call.positional("blocker")
    if not op.gitlab:
        done = op.run(["issue", "edit", child, "--add-blocked-by", blocker])
        return written(op, url_in(done.stdout) or op.web_url("issues", child))
    done = _gitlab_link(op, _gitlab_project_id(op), child, blocker)
    if done.code != 0:
        if _plan_lacks_blocking(done):
            raise unsupported(op.call.name, op.remote.forge, _PREMIUM)
        raise op.cli.failure(done)
    return written(op, op.web_url("issues", child))


def _gitlab_project_id(op: Op) -> str:
    """The numeric id of the project ``glab`` resolves (the links API wants a target project)."""
    project = op.json(["api", "projects/:fullpath"])
    return str(project.get("id")) if isinstance(project, dict) else ""


def _gitlab_link(op: Op, project_id: str, child: str, blocker: str) -> Done:
    """Link GitLab issue ``child`` as blocked by ``blocker`` (same project); the unchecked call."""
    path = f"projects/:fullpath/issues/{child}/links"
    argv = ["api", "--method", "POST", path, "-f", f"target_project_id={project_id}"]
    argv += ["-f", f"target_issue_iid={blocker}", "-f", "link_type=is_blocked_by"]
    return op.run(argv, check=False)


def _blockers(op: Op) -> Outcome:
    number = op.call.positional("n")
    if not op.gitlab:
        return printed(
            _linked(op.json(["issue", "view", number, "--json", "blockedBy"]), "blockedBy")
        )
    blockers = [
        shape.linked_issue(link, forge="gitlab")
        for link in op.pages(["api", f"projects/:fullpath/issues/{number}/links"])
        if isinstance(link, dict) and link.get("link_type") == "is_blocked_by"
    ]
    if not blockers and not _gitlab_has_blocking(op, number):
        raise unsupported(op.call.name, op.remote.forge, _PREMIUM)
    return printed(blockers)


def _create(op: Op) -> Outcome:
    call = op.call
    title = call.value("--title")
    if title is None:
        raise ForgeStop(1, "give --title")
    body = op.body(call.body or "")
    if not op.gitlab:
        argv = ["issue", "create", "--title", title, "--body-file", "-"]
        argv += _repeated(call.values("--label"), "--label")
        if (assignee := call.value("--assignee")) is not None:
            argv.extend(("--assignee", assignee))
        for option in ("--parent", "--blocked-by"):
            if numbers := _numbers(call.value(option)):
                argv.extend((option, ",".join(numbers)))
        return created(op, op.run(argv, body=body))
    blockers = _numbers(call.value("--blocked-by"))
    if blockers and not _gitlab_has_blocking(op, blockers[0]):
        raise unsupported(f"{call.name} --blocked-by", op.remote.forge, _PREMIUM)
    argv = ["issue", "create", "--title", title, "--description-file", "-"]
    argv += _repeated(call.values("--label"), "--label")
    if (assignee := call.value("--assignee")) is not None:
        argv.extend(("--assignee", assignee))
    if "--confidential" in call.flags:
        argv.append("--confidential")
    done = op.run([*argv, "--yes"], body=body)
    if not blockers:
        return created(op, done)
    # links go in one by one after the issue exists, so a failed link still names the issue
    # (glab's own --linked-issues prints no URL when a link fails, and an agent would retry)
    url = url_in(done.stdout)
    if url is None:
        raise ForgeStop(
            1, "`glab issue create` printed no URL: link the blockers with `issue block`"
        )
    child, project_id = url.rstrip("/").rpartition("/")[2], _gitlab_project_id(op)
    for blocker in blockers:
        linked = _gitlab_link(op, project_id, child, blocker)
        if linked.code != 0:
            stop = op.cli.failure(linked)
            message = f"created {url}, but linking it as blocked by #{blocker} failed"
            raise ForgeStop(stop.code, message, passthrough=linked.stderr)
    return written(op, url)


def _limit(text: str | None) -> int:
    """``issue list --limit``: a positive count, 30 by default (``gh issue list``'s default)."""
    if text is None:
        return _DEFAULT_LIMIT
    if not text.isdigit() or int(text) < 1:
        raise ForgeStop(1, f"--limit must be a positive number, got {text!r}")
    return int(text)


def _linked(item: Any, field: str) -> list[dict[str, Any]]:
    """The issues of a ``gh issue view --json`` connection field (``{"nodes": [...]}``)."""
    connection = item.get(field) if isinstance(item, dict) else None
    nodes = connection.get("nodes") if isinstance(connection, dict) else connection
    return [shape.linked_issue(node, forge="github") for node in items(nodes)]


def _required_body(op: Op) -> str:
    if op.call.body is None:
        raise ForgeStop(1, "give --body or --body-file")
    return op.call.body


def _repeated(values: tuple[str, ...], option: str) -> list[str]:
    words: list[str] = []
    for value in values:
        words.extend((option, value))
    return words


def _numbers(text: str | None) -> list[str]:
    return [part.strip().lstrip("#") for part in (text or "").split(",") if part.strip()]


_PREMIUM: Final = "blocking links need GitLab Premium or Ultimate"


def _gitlab_has_blocking(op: Op, number: str) -> bool:
    """Whether the project's plan has blocking issue links, read from issue ``number``.

    GitLab exposes an issue's ``weight`` only where the licensed feature tier
    that also holds blocking links is available (Premium), so its presence in
    the raw REST issue is the signal; ``glab issue view`` re-encodes the issue
    and always prints ``weight``, so the issue is read with ``glab api``.
    """
    issue = op.json(["api", f"projects/:fullpath/issues/{number}"])
    return isinstance(issue, dict) and "weight" in issue


def _plan_lacks_blocking(done: Done) -> bool:
    """Whether a failed link call failed for want of the plan (EE 403, or CE's 400 on ``link_type``)."""
    output = done.stdout + done.stderr
    return "not available for current license" in output or (
        "HTTP 400" in output and "link_type" in output
    )


ISSUE_HANDLERS: Final[Mapping[str, Callable[[Op], Outcome]]] = {
    "issue create": _create,
    "issue view": _view,
    "issue list": _list,
    "issue comment": _comment,
    "issue label": _label,
    "issue close": _close,
    "issue assign": _assign,
    "issue edit": _edit,
    "issue link-child": _link_child,
    "issue children": _children,
    "issue block": _block,
    "issue blockers": _blockers,
}
