"""``scripts/release.py tag``: the git and forge side of tagging a merged release (#281 ticket 11).

The decisions (which commit, refuse or tag) are ``coding_agent_playbook.release.tagging``;
this module only gathers their inputs and runs the outcome:

1. fetch ``origin`` with its tags; the tip is ``--tested-commit`` (the CI tag
   job's ``$GITHUB_SHA``) or ``origin/main``;
2. a tip whose ``[project]`` version is not a final ``X.Y.Z`` has nothing to tag;
3. walk ``git log --first-parent <tip> -- pyproject.toml`` back to the commit
   that introduced the version: the release commit, never HEAD;
4. a tag already at that commit is a no-op, one elsewhere a refusal;
5. the CI job tags only its own commit (a later push's run leaves an older
   release commit to that commit's run); by hand the ``test`` jobs of the
   release commit's CI run must be green, read through ``gh``: ``playbook forge``
   has no per-commit CI operation, and the tag job exists only in GitHub Actions;
6. the commit's parent must be the base in its ``catalog/releases/<v>/manifest.toml``;
7. ``git tag --annotate`` on that commit and ``git push origin refs/tags/vX``,
   never ``-f``: a release tag is immutable.
"""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Final, Protocol

from coding_agent_playbook.release.manifest import (
    MANIFEST_FILENAME,
    ManifestError,
    ReleaseManifest,
    parse_manifest,
    release_dir,
)
from coding_agent_playbook.release.tagging import (
    Revision,
    TagAction,
    TagRefusal,
    TagState,
    check_base,
    check_tests_passed,
    find_release_commit,
    parse_jobs,
    tag_action,
    taggable,
)
from coding_agent_playbook.release.versions import release_tag

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

REMOTE: Final = "origin"
MAIN_BRANCH: Final = "main"
#: The workflow whose push run holds the release commit's ``test`` jobs.
CI_WORKFLOW: Final = "ci.yml"
_PYPROJECT: Final = "pyproject.toml"
_CATALOG: Final = "catalog"
_PEELED: Final = "^{}"


class _Done(Protocol):
    @property
    def returncode(self) -> int: ...
    @property
    def stdout(self) -> str: ...


class TagTools(Protocol):
    """What tagging needs of ``release.Tools``: run a command, or run it and fail loudly."""

    def run(self, argv: Sequence[str]) -> _Done: ...
    def checked(self, argv: Sequence[str]) -> str: ...
    def git(self, *args: str) -> str: ...


def tag_release(tools: TagTools, *, tested_commit: str | None) -> str:
    """Tag the release on ``origin/main`` (or ``tested_commit``); returns what it did.

    Raises :class:`TagRefusal` when the tag must not be created.
    """
    tools.git("fetch", "--tags", REMOTE)
    tip = tested_commit or tools.git("rev-parse", "--verify", f"{REMOTE}/{MAIN_BRANCH}^{{commit}}")
    tip = tip.strip()
    version = _version_at(tools, tip)
    if version is None or not taggable(version):
        return f"nothing to tag: [project] version {version} at {tip} is not a final release"
    tag = release_tag(version)
    commit = find_release_commit(version, _revisions(tools, tip))
    action = tag_action(version, commit, _tag_state(tools, tag))
    if action is TagAction.NONE:
        return f"{tag} already points at {commit}: nothing to do"
    if tested_commit is not None and commit != tip:
        return (
            f"release commit {commit} of {tag} is not this run's commit {tip}: "
            "its own CI run tags it (or run `scripts/release.py tag`)"
        )
    if tested_commit is None:
        check_tests_passed(commit, parse_jobs(_ci_jobs(tools, commit)))
    check_base(version, commit, _parent(tools, commit), _manifest_at(tools, commit, version))
    if action is TagAction.CREATE:
        tools.git("tag", "--annotate", "--message", f"Release {tag}", tag, commit)
    tools.git("push", REMOTE, f"refs/tags/{tag}:refs/tags/{tag}")
    return f"tagged {tag} at {commit}"


def _version_at(tools: TagTools, commit: str) -> str | None:
    done = tools.run(["git", "show", f"{commit}:{_PYPROJECT}"])
    if done.returncode != 0:
        return None
    try:
        return str(tomllib.loads(done.stdout)["project"]["version"])
    except (tomllib.TOMLDecodeError, KeyError, TypeError):
        return None


def _revisions(tools: TagTools, tip: str) -> Iterator[Revision]:
    """The first-parent commits that touched ``pyproject.toml``, newest first, read lazily."""
    log = tools.git("log", "--first-parent", "--format=%H", tip, "--", _PYPROJECT)
    for commit in log.split():
        yield Revision(commit, _version_at(tools, commit))


def _tag_state(tools: TagTools, tag: str) -> TagState:
    ref = f"refs/tags/{tag}"
    remote = _remote_target(tools.git("ls-remote", "--tags", REMOTE, ref), ref)
    local = tools.run(["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"])
    if local.returncode != 0:
        return TagState(remote=remote, local=None)
    kind = tools.git("cat-file", "-t", ref).strip()
    return TagState(remote=remote, local=local.stdout.strip(), local_annotated=kind == "tag")


def _remote_target(listing: str, ref: str) -> str | None:
    """The commit ``ref`` names in ``git ls-remote`` output: the peeled line wins."""
    targets: dict[str, str] = {}
    for line in listing.splitlines():
        sha, _, name = line.partition("\t")
        targets[name.strip()] = sha.strip()
    return targets.get(f"{ref}{_PEELED}") or targets.get(ref)


def _ci_jobs(tools: TagTools, commit: str) -> str:
    listing = ["gh", "run", "list", "--commit", commit, "--workflow", CI_WORKFLOW]
    newest = ["--event", "push", "--limit", "1", "--json", "databaseId", "--jq", ".[].databaseId"]
    runs = tools.checked([*listing, *newest]).split()
    if not runs:
        raise TagRefusal(f"no {CI_WORKFLOW} push run on {commit} yet: wait for CI, then re-run")
    return tools.checked(["gh", "run", "view", runs[0], "--json", "jobs"])


def _parent(tools: TagTools, commit: str) -> str:
    done = tools.run(["git", "rev-parse", "--verify", f"{commit}^1"])
    if done.returncode != 0:
        raise TagRefusal(f"release commit {commit} has no parent")
    return done.stdout.strip()


def _manifest_at(tools: TagTools, commit: str, version: str) -> ReleaseManifest:
    path = (release_dir(Path(_CATALOG), version) / MANIFEST_FILENAME).as_posix()
    done = tools.run(["git", "show", f"{commit}:{path}"])
    if done.returncode != 0:
        raise TagRefusal(f"release commit {commit} has no {path}: it is not a prepared release")
    try:
        return parse_manifest(done.stdout)
    except ManifestError as exc:
        raise TagRefusal(f"{commit}:{path}: {exc}") from exc
