"""Release tagging decisions: which commit gets ``vX``, and when tagging refuses (#281 ticket 11).

Merging the release pull request is the release; a tag names exactly that
commit. Both the CI tag job and ``scripts/release.py tag`` gather the facts
through git (and, by hand, the forge CLI) and let these pure functions decide:

- :func:`find_release_commit`: the first-parent commit that introduced the
  ``[project]`` version, never HEAD, so a pull request merged after the release
  never slips into its tag;
- :func:`check_base`: that commit's parent must be the base ``prepare`` recorded
  in the release's manifest, else main moved under the release pull request;
- :func:`check_tests_passed`: the CI test jobs on that commit all succeeded;
- :func:`tag_action`: tags are never moved: a tag already at the commit is a
  no-op (or only a push), one elsewhere is a refusal.
"""

from __future__ import annotations

import enum
import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.release.versions import is_release_tag, release_tag

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from coding_agent_playbook.release.manifest import ReleaseManifest

__all__ = [
    "TEST_JOB",
    "JobResult",
    "Revision",
    "TagAction",
    "TagRefusal",
    "TagState",
    "check_base",
    "check_tests_passed",
    "find_release_commit",
    "parse_jobs",
    "tag_action",
    "taggable",
]

#: The ci.yml job whose success a tag needs; matrix runs are named ``test (<python>)``.
TEST_JOB: Final = "test"
_SUCCESS: Final = "success"
_COMPLETED: Final = "completed"


class TagRefusal(Exception):
    """Tagging must not happen; the message says why and what to do."""


@dataclass(frozen=True)
class Revision:
    """A first-parent commit that touched ``pyproject.toml``, with the version it sets.

    ``version`` is ``None`` when the file is missing or unreadable at that commit.
    """

    commit: str
    version: str | None


@dataclass(frozen=True)
class JobResult:
    """One CI job of a workflow run, as the forge reports it."""

    name: str
    status: str
    conclusion: str


@dataclass(frozen=True)
class TagState:
    """Where tag ``vX`` already points: on the remote, locally, and whether the local one is annotated.

    ``remote`` and ``local`` are the peeled commits, or ``None`` when absent.
    """

    remote: str | None
    local: str | None
    local_annotated: bool = True


class TagAction(enum.Enum):
    """What tagging does once every check passed."""

    CREATE = "create"  # create the annotated tag, then push it
    PUSH = "push"  # the annotated tag exists locally at the commit: push it only
    NONE = "none"  # the remote tag already points at the commit


def taggable(version: str) -> bool:
    """Whether ``version`` is a final ``X.Y.Z`` release (a pre-release is never tagged).

    Example::

        >>> taggable("9.9.9"), taggable("9.9.9a0")
        (True, False)
    """
    return is_release_tag(release_tag(version))


def find_release_commit(version: str, revisions: Iterable[Revision]) -> str:
    """The oldest commit of the leading run of ``revisions`` that set ``version``.

    ``revisions`` is newest first and is read lazily: the walk stops at the first
    commit with another (or no) version. Raises :class:`TagRefusal` when no
    revision sets ``version`` or the version never changed in the history.

    Example::

        >>> find_release_commit("9.9.9", [Revision("b", "9.9.9"), Revision("a", "9.9.8")])
        'b'
    """
    found: str | None = None
    for revision in revisions:
        if revision.version != version:
            if found is None:
                break
            return found
        found = revision.commit
    if found is None:
        raise TagRefusal(f"no first-parent commit sets [project] version {version}")
    raise TagRefusal(
        f"[project] version {version} never changed in the first-parent history: "
        "no release commit to tag"
    )


def check_base(version: str, commit: str, parent: str, manifest: ReleaseManifest) -> None:
    """Refuse unless ``manifest`` is release ``version``'s and ``parent`` is its recorded base.

    Example::

        >>> from coding_agent_playbook.release.manifest import ReleaseManifest
        >>> check_base("9.9.9", "c0", "ba5e", ReleaseManifest("9.9.9", "ba5e", (), ()))
    """
    if manifest.version != version:
        raise TagRefusal(
            f"the manifest in release commit {commit} records version {manifest.version}, "
            f"not {version}"
        )
    if parent != manifest.base:
        raise TagRefusal(
            f"release commit {commit} has parent {parent}, but prepare recorded the base "
            f"{manifest.base}: main moved under the release pull request; re-run prepare"
        )


def parse_jobs(text: str) -> list[JobResult]:
    """The jobs in ``text``, the ``{"jobs": [{name, status, conclusion}, ...]}`` JSON of a run.

    Example::

        >>> parse_jobs('{"jobs": [{"name": "test", "status": "completed", "conclusion": "success"}]}')
        [JobResult(name='test', status='completed', conclusion='success')]
    """
    try:
        data = json.loads(text)
        return [
            JobResult(str(job["name"]), str(job["status"]), str(job.get("conclusion") or ""))
            for job in data["jobs"]
        ]
    except (ValueError, TypeError, KeyError) as exc:
        raise TagRefusal(
            f"unreadable CI jobs {text[:200]!r}; expected "
            '{"jobs": [{"name": …, "status": …, "conclusion": …}]}'
        ) from exc


def check_tests_passed(commit: str, jobs: Sequence[JobResult]) -> None:
    """Refuse unless every ``test`` job (matrix entries included) completed with success.

    Example::

        >>> check_tests_passed("c0", [JobResult("test (3.12)", "completed", "success")])
    """
    tests = [job for job in jobs if _is_test_job(job.name)]
    if not tests:
        raise TagRefusal(f"the CI run on {commit} has no {TEST_JOB} job: wait for CI, then re-run")
    unfinished = [job for job in tests if job.status != _COMPLETED or job.conclusion != _SUCCESS]
    if unfinished:
        detail = ", ".join(
            f"{job.name} {job.status} {job.conclusion}".strip() for job in unfinished
        )
        raise TagRefusal(f"CI on {commit} is not green: {detail}")


def _is_test_job(name: str) -> bool:
    return name == TEST_JOB or name.startswith(f"{TEST_JOB} (")


def tag_action(version: str, commit: str, state: TagState) -> TagAction:
    """What to do with tag ``v<version>`` for release ``commit``; never moves a tag.

    Example::

        >>> tag_action("9.9.9", "c0", TagState(remote="c0", local=None))
        <TagAction.NONE: 'none'>
    """
    tag = release_tag(version)
    if state.remote is not None:
        if state.remote != commit:
            raise TagRefusal(
                f"tag {tag} already points at {state.remote}, not the release commit {commit}: "
                "a release tag is never moved"
            )
        return TagAction.NONE
    if state.local is None:
        return TagAction.CREATE
    if state.local != commit:
        raise TagRefusal(
            f"local tag {tag} points at {state.local}, not the release commit {commit}: "
            f"delete it by hand (`git tag -d {tag}`) and re-run"
        )
    if not state.local_annotated:
        raise TagRefusal(
            f"local tag {tag} is lightweight: delete it (`git tag -d {tag}`) and re-run, "
            "release tags are annotated"
        )
    return TagAction.PUSH
