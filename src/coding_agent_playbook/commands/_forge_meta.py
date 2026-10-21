"""Labels, references and the login: the forge operations beyond one issue or pull request (spec prF §6.3).

- ``label list`` / ``label create``: a label is ``name``, ``color`` (six hex
  digits, no ``#``) and ``description`` on both forges;
- ``ref view <ref>``: ``#n`` / ``n`` is the pull request, else the issue, on
  GitHub; on GitLab ``#n`` / ``n`` is the issue and ``!n`` the merge request;
  a URL is read by its path, in its repository (``-R``), and only on the push
  remote's host, which the guards judged (Q31). The result carries ``kind``;
- ``auth status``: whether the forge CLI is logged in to the API host, from its
  exit code; never ``-t`` (the token is never printed or read).
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.commands import _forge_shape as shape
from coding_agent_playbook.commands._forge_op import printed, written
from coding_agent_playbook.commands._forge_stop import ForgeStop, logged_out

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from coding_agent_playbook.commands._forge_op import Op, Outcome

__all__ = ["META_HANDLERS"]

_HEX_COLOR: Final = re.compile(r"^#?([0-9A-Fa-f]{6})$")
#: ``<repo>/pull/<n>`` or ``<repo>/issues/<n>`` (GitHub), ``<repo>/-/merge_requests/<n>``,
#: ``/-/issues/<n>`` or ``/-/work_items/<n>`` (GitLab).
_URL_REF: Final = re.compile(
    r"^https?://(?:[^/@]*@)?(?P<host>[^/:?#]+)(?::\d+)?/(?P<repo>.+?)/(?:-/)?"
    r"(?P<kind>pull|pulls|merge_requests|issues|work_items)/(?P<n>\d+)(?:[/?#].*)?$"
)
_SHORT_REF: Final = re.compile(r"^([#!]?)(\d+)$")
_PULL_KINDS: Final = frozenset({"pull", "pulls", "merge_requests"})


def _label_list(op: Op) -> Outcome:
    if op.gitlab:
        items = op.listed(["label", "list", "-F", "json"], None)
    else:
        items = op.json(["label", "list", "--json", "name,color,description", "--limit", "1000"])
    return printed([_label(item) for item in items or () if isinstance(item, dict)])


def _label(item: Mapping[str, Any]) -> dict[str, str]:
    return {
        "name": str(item.get("name", "")),
        "color": str(item.get("color") or "").lstrip("#").lower(),
        "description": str(item.get("description") or ""),
    }


def _label_create(op: Op) -> Outcome:
    call = op.call
    name = call.positional("name")
    color = call.value("--color")
    if color is not None and _HEX_COLOR.match(color) is None:
        raise ForgeStop(1, "--color must be six hex digits, like d73a4a")
    argv = ["label", "create"] + (["--name", name] if op.gitlab else [name])
    if color is not None:
        bare = color.lstrip("#").lower()
        argv.extend(("--color", f"#{bare}" if op.gitlab else bare))
    if (description := call.value("--description")) is not None:
        argv.extend(("--description", description))
    op.run(argv)
    return written(op, f"{op.repo_url()}{'/-/labels' if op.gitlab else '/labels'}")


def _ref_view(op: Op) -> Outcome:
    ref = op.call.positional("ref").strip()
    url = _URL_REF.match(ref)
    if url is not None:
        host = url.group("host").lower()
        if host not in {op.remote.host, op.remote.api_host}:
            raise ForgeStop(1, f"the reference is on {host}, not on this repo's forge host")
        kind = "pull_request" if url.group("kind") in _PULL_KINDS else "issue"
        return printed(_fetched(op, kind, url.group("n"), repo=url.group("repo")))
    short = _SHORT_REF.match(ref)
    if short is None:
        raise ForgeStop(1, f"cannot read the reference {ref!r}: give #n, !n, n or a URL")
    sigil, number = short.groups()
    if op.gitlab:
        return printed(_fetched(op, "pull_request" if sigil == "!" else "issue", number))
    if sigil == "!":
        return printed(_fetched(op, "pull_request", number))
    argv = ["pr", "view", number, "--json", shape.GH_PULL_FIELDS]
    done = op.run(argv, check=False)
    if done.code == 0:
        pages = op.cli.pages(done, argv)
        return printed({"kind": "pull_request", **shape.github_pull(pages[0] if pages else {})})
    if op.cli.logged_out(done):
        raise op.cli.failure(done)
    return printed(_fetched(op, "issue", number))


def _fetched(op: Op, kind: str, number: str, *, repo: str | None = None) -> dict[str, Any]:
    """Issue or pull request ``number`` (of ``repo``, a path on the same host, when given)."""
    other = ["-R", repo] if repo is not None else []
    if op.gitlab:
        noun, read = (
            ("mr", shape.gitlab_pull) if kind == "pull_request" else ("issue", shape.gitlab_issue)
        )
        return {"kind": kind, **read(op.json([noun, "view", number, "-F", "json", *other]))}
    if kind == "pull_request":
        item = op.json(["pr", "view", number, "--json", shape.GH_PULL_FIELDS, *other])
        return {"kind": kind, **shape.github_pull(item)}
    item = op.json(["issue", "view", number, "--json", shape.GH_ISSUE_FIELDS, *other])
    return {"kind": kind, **shape.github_issue(item)}


def _auth_status(op: Op) -> Outcome:
    host = op.remote.api_host
    # gh: --active, so a stale second account on the host does not fail the check
    argv = ["auth", "status", "--hostname", host] + ([] if op.gitlab else ["--active"])
    done = op.run(argv, check=False)
    if done.code != 0 and op.gitlab:
        # glab reports a host it has no config entry for as not logged in, even with a
        # token in the environment; one API call tells (the token is never read here)
        probe = op.run(["api", "--hostname", host, "user"], check=False)
        if probe.code != 0 and not op.cli.logged_out(probe):
            raise op.cli.failure(probe)  # the forge did not answer: exit 1, not a login step
        done = probe
    if done.code != 0:
        stop = logged_out(op.remote.forge, host, op.cli.caller_env)
        raise ForgeStop(2, stop.message, passthrough=done.stderr)
    return printed({"forge": op.remote.forge.name, "host": host, "logged_in": True})


META_HANDLERS: Final[Mapping[str, Callable[[Op], Outcome]]] = {
    "label list": _label_list,
    "label create": _label_create,
    "ref view": _ref_view,
    "auth status": _auth_status,
}
