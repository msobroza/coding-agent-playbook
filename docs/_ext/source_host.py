"""Where the docs site links source files: the repository a build runs in, and its forge.

The site may be built by GitHub Actions, by GitLab CI or from any checkout, so a
source link must point at the repository of the build, never at a hard-coded one.
:func:`source_host_from_env` finds it, first match wins:

1. ``PLAYBOOK_DOCS_REPO_URL``, an override, with ``PLAYBOOK_DOCS_FORGE``
   (``github`` or ``gitlab``) when the host name does not tell the forge;
2. GitLab CI's ``CI_PROJECT_URL`` and ``CI_DEFAULT_BRANCH``;
3. GitHub Actions' ``GITHUB_SERVER_URL`` and ``GITHUB_REPOSITORY``;
4. the checkout's ``origin`` remote, when its forge is known.

With none of them the site has no source links: it shows repository paths as
text. ``PLAYBOOK_DOCS_BRANCH`` changes the branch the links point to. The forge
decides the link shape, GitHub's ``/blob/main/`` or GitLab's ``/-/blob/main/``,
and comes from the engine's own :func:`forge_for_host`, so a self-managed GitLab
is recognised the way ``playbook forge`` recognises it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal

from coding_agent_playbook.forge.hosts import forge_for_host, remote_host

if TYPE_CHECKING:
    from collections.abc import Mapping

type ForgeName = Literal["github", "gitlab"]

DEFAULT_BRANCH: Final = "main"

#: ``scheme://[user[:password]@]host[:port]/path`` of an http(s) or ssh remote.
_URL_REMOTE: Final = re.compile(r"^(?P<scheme>[a-z+]+)://(?:[^@/]*@)?(?P<host>[^/]+)/(?P<path>.+)$")
#: git's scp-like ``[user@]host:path`` remote.
_SCP_REMOTE: Final = re.compile(r"^(?:[^@/:]+@)?(?P<host>[^:/]+):(?P<path>[^/].*)$")


@dataclass(frozen=True)
class SourceHost:
    """A repository's web address, its forge and the branch the site links to.

    Example: ``SourceHost("https://gitlab.acme.com/tools/playbook", "gitlab").blob_url``
    -> ``"https://gitlab.acme.com/tools/playbook/-/blob/main/"``.
    """

    repo_url: str
    forge: ForgeName
    branch: str = DEFAULT_BRANCH

    @property
    def blob_url(self) -> str:
        """The prefix of a link to a file; the file's repo path follows it."""
        return self._link_prefix("blob")

    @property
    def tree_url(self) -> str:
        """The prefix of a link to a directory; the directory's repo path follows it."""
        return self._link_prefix("tree")

    @property
    def label(self) -> str:
        """The forge's name as the sidebar shows it: ``GitHub`` or ``GitLab``."""
        return "GitLab" if self.forge == "gitlab" else "GitHub"

    def _link_prefix(self, kind: str) -> str:
        # GitLab puts "-/" between the project and its routes (/-/blob/, /-/tree/).
        separator = "-/" if self.forge == "gitlab" else ""
        return f"{self.repo_url}/{separator}{kind}/{self.branch}/"


def source_host_from_env(
    env: Mapping[str, str], origin_url: str | None = None
) -> SourceHost | None:
    """The repository the build runs in, from ``env`` then ``origin_url``; ``None``: unknown.

    Raises ``ValueError`` naming the variable when an override cannot be used.

    Example: ``source_host_from_env({"GITLAB_CI": "true", "CI_PROJECT_URL": url}).forge``
    -> ``"gitlab"``.
    """
    branch = env.get("PLAYBOOK_DOCS_BRANCH") or None
    override = env.get("PLAYBOOK_DOCS_REPO_URL", "").strip()
    if override:
        url = _web_url(override, "PLAYBOOK_DOCS_REPO_URL")
        return SourceHost(url, _override_forge(url, env), branch or DEFAULT_BRANCH)
    if env.get("GITLAB_CI") and env.get("CI_PROJECT_URL"):
        default = env.get("CI_DEFAULT_BRANCH") or DEFAULT_BRANCH
        repo_url = _web_url(env["CI_PROJECT_URL"], "CI_PROJECT_URL")
        return SourceHost(repo_url, "gitlab", branch or default)
    if env.get("GITHUB_ACTIONS") and env.get("GITHUB_REPOSITORY"):
        server = env.get("GITHUB_SERVER_URL") or "https://github.com"
        repo_url = _web_url(f"{server}/{env['GITHUB_REPOSITORY']}", "GITHUB_SERVER_URL")
        return SourceHost(repo_url, "github", branch or DEFAULT_BRANCH)
    return _origin_host(origin_url, env, branch or DEFAULT_BRANCH)


def _origin_host(origin_url: str | None, env: Mapping[str, str], branch: str) -> SourceHost | None:
    """The ``origin`` remote as a web address, when it is one and its forge is known."""
    repo_url = web_url_of_remote(origin_url) if origin_url else None
    remote = remote_host(origin_url) if origin_url else None
    found = forge_for_host(remote.host, {}, env) if remote else None
    forge = _forge_name(found.forge.name) if found else None
    if repo_url is None or forge is None:
        return None
    return SourceHost(repo_url, forge, branch)


def web_url_of_remote(url: str) -> str | None:
    """The web address of a git remote in any of git's forms; ``None`` for a local path.

    Credentials are dropped. An ssh remote's port is dropped too: it is not the
    web server's.

    Example: ``web_url_of_remote("git@gitlab.acme.com:tools/app.git")``
    -> ``"https://gitlab.acme.com/tools/app"``.
    """
    text = url.strip()
    match = _URL_REMOTE.match(text)
    if match is not None:
        scheme, host = match["scheme"], match["host"]
        if scheme not in ("http", "https"):
            scheme, host = "https", host.split(":")[0]
        return _web_url(f"{scheme}://{host}/{match['path']}", "origin")
    scp = _SCP_REMOTE.match(text)
    if scp is None or len(scp["host"]) == 1:  # a Windows drive (C:\repo) is no host
        return None
    return _web_url(f"https://{scp['host']}/{scp['path']}", "origin")


def _web_url(url: str, variable: str) -> str:
    """``url`` without a trailing slash or ``.git``; it must be an http(s) address."""
    if not url.startswith(("https://", "http://")):
        raise ValueError(
            f"{variable}={url!r}: expected the repository's web address, "
            "such as https://gitlab.example.com/group/project"
        )
    return url.rstrip("/").removesuffix(".git")


def _override_forge(url: str, env: Mapping[str, str]) -> ForgeName:
    """``PLAYBOOK_DOCS_FORGE``, else the forge the engine maps the URL's host to."""
    named = env.get("PLAYBOOK_DOCS_FORGE", "").strip().lower()
    if named:
        forge = _forge_name(named)
        if forge is None:
            raise ValueError(f"PLAYBOOK_DOCS_FORGE={named!r}: expected 'github' or 'gitlab'")
        return forge
    remote = remote_host(url)
    found = forge_for_host(remote.host, {}, env) if remote else None
    forge = _forge_name(found.forge.name) if found else None
    if forge is None:
        raise ValueError(
            f"PLAYBOOK_DOCS_REPO_URL={url!r}: cannot tell its forge from the host name; "
            "set PLAYBOOK_DOCS_FORGE to 'github' or 'gitlab'"
        )
    return forge


def _forge_name(name: str) -> ForgeName | None:
    if name == "github":
        return "github"
    if name == "gitlab":
        return "gitlab"
    return None
