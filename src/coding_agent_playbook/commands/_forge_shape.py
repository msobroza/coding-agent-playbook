"""One JSON vocabulary for what ``gh`` and ``glab`` print (spec prF §6.3 rules, Q20).

Pure functions from a forge CLI's JSON to the shapes ``playbook forge`` prints:
an issue or pull request is ``number``, ``url``, ``title``, ``body``, ``state``
(``open`` / ``closed`` / ``merged``), ``labels`` (names), ``assignees`` (logins),
``author`` (login), ``created_at``, ``updated_at``, ``confidential`` (always
``false`` on GitHub), and for a pull request ``draft``, ``base`` and ``head``;
a comment is ``id``, ``author``, ``body``, ``created_at`` and ``path`` (the
file of a comment on the diff, else ``null``). Each reader takes what
``gh … --json`` / ``gh api`` (GitHub) or ``glab … -F json`` / ``glab api``
(GitLab) prints.
"""

from __future__ import annotations

import re
from typing import Any, Final

__all__ = [
    "GH_ISSUE_FIELDS",
    "GH_PULL_FIELDS",
    "github_check",
    "github_comment",
    "github_issue",
    "github_pull",
    "github_rest_pull",
    "github_review_comment",
    "gitlab_issue",
    "gitlab_job",
    "gitlab_note",
    "gitlab_pull",
    "linked_issue",
]

#: The ``gh issue view/list --json`` fields an issue needs.
GH_ISSUE_FIELDS: Final = "number,url,title,body,state,labels,assignees,author,createdAt,updatedAt"
#: The ``gh pr view/list --json`` fields a pull request needs.
GH_PULL_FIELDS: Final = f"{GH_ISSUE_FIELDS},isDraft,baseRefName,headRefName"
_COMMENT_ID: Final = re.compile(r"#(?:issuecomment|discussion_r)-(\d+)$")
_STATES: Final = {"opened": "open", "open": "open", "closed": "closed", "merged": "merged"}

type Shape = dict[str, Any]


def github_issue(item: Any) -> Shape:
    """A ``gh issue view/list --json`` issue."""
    return {
        "number": item.get("number"),
        "url": item.get("url", ""),
        "title": item.get("title", ""),
        "body": item.get("body") or "",
        "state": _state(item.get("state")),
        "labels": [label.get("name", "") for label in item.get("labels") or ()],
        "assignees": [user.get("login", "") for user in item.get("assignees") or ()],
        "author": _login(item.get("author")),
        "created_at": item.get("createdAt", ""),
        "updated_at": item.get("updatedAt", ""),
        "confidential": False,
    }


def github_pull(item: Any) -> Shape:
    """A ``gh pr view/list --json`` pull request."""
    return {
        **github_issue(item),
        "draft": bool(item.get("isDraft")),
        "base": item.get("baseRefName", ""),
        "head": item.get("headRefName", ""),
    }


def github_rest_pull(item: Any) -> Shape:
    """A pull request as ``gh api repos/{owner}/{repo}/pulls`` prints it (REST)."""
    state = "merged" if item.get("merged_at") else _state(item.get("state"))
    return {
        "number": item.get("number"),
        "url": item.get("html_url", ""),
        "title": item.get("title", ""),
        "body": item.get("body") or "",
        "state": state,
        "labels": [label.get("name", "") for label in item.get("labels") or ()],
        "assignees": [user.get("login", "") for user in item.get("assignees") or ()],
        "author": (item.get("user") or {}).get("login", ""),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "confidential": False,
        "draft": bool(item.get("draft")),
        "base": (item.get("base") or {}).get("ref", ""),
        "head": (item.get("head") or {}).get("ref", ""),
    }


def github_comment(item: Any) -> Shape:
    """A comment of ``gh issue/pr view --json comments``; its id is the REST id in its URL."""
    match = _COMMENT_ID.search(item.get("url") or "")
    return {
        "id": int(match.group(1)) if match is not None else item.get("id"),
        "author": _login(item.get("author")),
        "body": item.get("body") or "",
        "created_at": item.get("createdAt", ""),
        "path": None,
    }


def github_review_comment(item: Any) -> Shape:
    """A pull request review comment as ``gh api …/pulls/<n>/comments`` prints it (REST)."""
    return {
        "id": item.get("id"),
        "author": (item.get("user") or {}).get("login", ""),
        "body": item.get("body") or "",
        "created_at": item.get("created_at", ""),
        "path": item.get("path"),
    }


def github_check(item: Any) -> Shape:
    """One check of ``gh pr checks --json``."""
    return {
        "name": item.get("name", ""),
        "state": _check_state(item.get("bucket") or item.get("state")),
        "url": item.get("link") or "",
    }


def gitlab_issue(item: Any) -> Shape:
    """A ``glab issue view/list -F json`` issue (GitLab's REST issue)."""
    return {
        "number": item.get("iid"),
        "url": item.get("web_url", ""),
        "title": item.get("title", ""),
        "body": item.get("description") or "",
        "state": _state(item.get("state")),
        "labels": [_label_name(label) for label in item.get("labels") or ()],
        "assignees": [user.get("username", "") for user in item.get("assignees") or ()],
        "author": (item.get("author") or {}).get("username", ""),
        "created_at": item.get("created_at", ""),
        "updated_at": item.get("updated_at", ""),
        "confidential": bool(item.get("confidential")),
    }


def gitlab_pull(item: Any) -> Shape:
    """A ``glab mr view/list -F json`` merge request, as a pull request."""
    return {
        **gitlab_issue(item),
        "confidential": False,
        "draft": bool(item.get("draft") or item.get("work_in_progress")),
        "base": item.get("target_branch", ""),
        "head": item.get("source_branch", ""),
    }


def gitlab_note(item: Any) -> Shape:
    """A GitLab note (``glab api …/notes``), as a comment."""
    position = item.get("position") or {}
    return {
        "id": item.get("id"),
        "author": (item.get("author") or {}).get("username", ""),
        "body": item.get("body") or "",
        "created_at": item.get("created_at", ""),
        "path": position.get("new_path") or position.get("old_path") or None,
    }


def gitlab_job(item: Any) -> Shape:
    """One job of a GitLab pipeline (``glab ci get … -F json`` ``jobs``), as a check.

    A failed job that may fail (``allow_failure``) is ``skipped``, as GitHub files
    a neutral check.
    """
    status = item.get("status")
    if status == "failed" and item.get("allow_failure"):
        status = "skipped"
    return {
        "name": item.get("name", ""),
        "state": _check_state(status),
        "url": item.get("web_url") or "",
    }


def linked_issue(item: Any, *, forge: str) -> Shape:
    """A sub-issue or blocking issue: ``number``, ``url``, ``title``, ``state``."""
    if forge == "gitlab":
        return {
            "number": item.get("iid"),
            "url": item.get("web_url", ""),
            "title": item.get("title", ""),
            "state": _state(item.get("state")),
        }
    return {
        "number": item.get("number"),
        "url": item.get("url") or item.get("html_url", ""),
        "title": item.get("title", ""),
        "state": _state(item.get("state")),
    }


def _state(value: object) -> str:
    text = str(value or "").lower()
    return _STATES.get(text, "closed" if text == "locked" else text)


#: ``gh pr checks`` buckets and GitLab job statuses, folded into one check vocabulary.
_CHECK_STATES: Final = {
    "pass": "pass",
    "success": "pass",
    "fail": "fail",
    "failed": "fail",
    "cancel": "cancelled",
    "canceled": "cancelled",
    "cancelled": "cancelled",
    "skipping": "skipped",
    "skipped": "skipped",
    "manual": "skipped",
}


def _check_state(value: object) -> str:
    text = str(value or "").lower()
    return _CHECK_STATES.get(text, "pending")


def _login(user: object) -> str:
    return str(user.get("login", "")) if isinstance(user, dict) else ""


def _label_name(label: object) -> str:
    return str(label.get("name", "")) if isinstance(label, dict) else str(label)
