"""The sides of ``playbook eval --compare``: a git ref, ``head`` or ``edition:<tag>`` (#281 ticket 14).

- A **git ref** (``origin/main``, ``HEAD``) is checked out as a detached ``git
  worktree`` and graded through that checkout's own engine and text, with
  ``--edition head`` when that engine takes the flag, so a pinned sample grades
  the ref's text and not its frozen edition (:func:`takes_edition_head`).
- ``head`` is the current text in place: the repository itself, uncommitted
  edits included, with ``--edition head`` so a pinned sample grades it too.
- ``edition:<tag>`` is release ``<tag>``'s graded set, built on the fly from the
  tag's manifest into the comparison's work directory
  (``release.edition_build``, the copy ``freeze`` makes; nothing is committed),
  and graded in place with ``--edition-dir``.

:func:`prepare_side` turns a side into a :class:`PreparedSide`: where its runs
happen and the flags each run gets (``evals.run.comparison_runner`` runs them).
"""

from __future__ import annotations

import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final, Literal, Protocol

from coding_agent_playbook.evals.run.git_env import without_repo_location
from coding_agent_playbook.exit_two import ExitTwoError
from coding_agent_playbook.release.edition import EditionError, load_edition
from coding_agent_playbook.release.edition_build import EditionBuildError, build_edition
from coding_agent_playbook.release.versions import is_release_tag

if TYPE_CHECKING:
    from collections.abc import Iterator
    from contextlib import AbstractContextManager
    from pathlib import Path

    from coding_agent_playbook.release.edition import Edition

#: The side that grades the current text in place.
HEAD_SIDE: Final = "head"
#: ``edition:<tag>``: the side that grades release ``<tag>``'s graded set.
EDITION_PREFIX: Final = "edition:"
#: The ``playbook eval --run`` flag that grades an edition built at a directory.
EDITION_DIR_FLAG: Final = "--edition-dir"
#: The module an engine that takes ``--edition head`` ships (#318); older engines lack both.
_EDITION_HEAD_MODULE: Final = ("src", "coding_agent_playbook", "evals", "graded_source.py")
#: Bound on one ``git worktree`` call (it touches only the local repository).
_GIT_TIMEOUT_S: Final = 120.0

type SideKind = Literal["ref", "head", "edition"]


class ComparisonError(ExitTwoError):
    """A side could not be prepared or a sample does not render on it; the CLI exits 2."""


@dataclass(frozen=True)
class ComparisonSide:
    """One side of a comparison: ``ref``, a git ref, ``head`` or ``edition:<tag>``.

    Example::

        >>> ComparisonSide("origin/main").label
        'origin/main'
        >>> ComparisonSide("edition:v0.1.0").label
        'edition v0.1.0'
    """

    ref: str

    @classmethod
    def parse(cls, text: str) -> ComparisonSide:
        """The side ``text`` names; :class:`ComparisonError` for an ``edition:`` without a release tag.

        Example::

            >>> ComparisonSide.parse("edition:main")
            Traceback (most recent call last):
            ...
            coding_agent_playbook.evals.run.comparison_sides.ComparisonError: ...
        """
        side = cls(text)
        if side.kind == "edition" and not is_release_tag(side.tag):
            raise ComparisonError(
                f"--compare {text!r}: an edition side is edition:<release tag>, "
                f"for example edition:v0.1.0; got tag {side.tag!r}"
            )
        return side

    @property
    def kind(self) -> SideKind:
        """``edition`` for ``edition:<tag>``, ``head`` for ``head``, else ``ref``."""
        if self.ref.startswith(EDITION_PREFIX):
            return "edition"
        return "head" if self.ref == HEAD_SIDE else "ref"

    @property
    def tag(self) -> str:
        """The edition's release tag (``""`` for a side that is not an edition)."""
        return self.ref.removeprefix(EDITION_PREFIX) if self.kind == "edition" else ""

    @property
    def label(self) -> str:
        """The side's name in the table: ``<ref>`` or ``edition <tag>``."""
        if self.kind == "edition":
            return f"edition {self.tag}"
        return self.ref


@dataclass(frozen=True)
class PreparedSide:
    """A side ready to run: ``name`` (base or head), where its runs happen and their flags.

    ``edition`` is the loaded edition of an ``edition:<tag>`` side, else ``None``.
    """

    name: str
    side: ComparisonSide
    checkout: Path
    flags: tuple[str, ...]
    edition: Edition | None = None


class CheckoutFactory(Protocol):
    """Checks ``ref`` out at ``dest`` for a ``with`` block (``git_worktree_checkout`` in prod)."""

    def __call__(self, ref: str, dest: Path) -> AbstractContextManager[Path]: ...


class EditionBuilder(Protocol):
    """Builds edition ``tag`` under the catalog directory ``dest``; returns its root."""

    def __call__(self, tag: str, dest: Path) -> Path: ...


@dataclass(frozen=True)
class SideSources:
    """Where sides come from: the repository, how to check a ref out and how to build an edition."""

    repo_root: Path
    checkout_ref: CheckoutFactory
    build_edition: EditionBuilder


@contextmanager
def prepare_side(
    sources: SideSources, side: ComparisonSide, name: str, work_dir: Path
) -> Iterator[PreparedSide]:
    """Prepare ``side`` as ``name`` for a ``with`` block; a git checkout is removed afterwards.

    Example::

        >>> with prepare_side(sources, ComparisonSide("head"), "head", work) as ready:  # doctest: +SKIP
        ...     ready.flags
        ('--edition', 'head')
    """
    if side.kind == "ref":
        with sources.checkout_ref(side.ref, work_dir / "checkouts" / name) as checkout:
            yield PreparedSide(name, side, checkout, _ref_flags(checkout))
        return
    if side.kind == "head":
        yield PreparedSide(name, side, sources.repo_root, ("--edition", HEAD_SIDE))
        return
    root = sources.build_edition(side.tag, work_dir / f"edition-{name}")
    try:
        edition = load_edition(root)
    except EditionError as exc:
        raise ComparisonError(f"--compare {side.ref}: {exc}") from exc
    yield PreparedSide(name, side, sources.repo_root, (EDITION_DIR_FLAG, str(root)), edition)


def _ref_flags(checkout: Path) -> tuple[str, ...]:
    """A git-ref side's flags: ``--edition head`` when its engine takes it, else none."""
    return ("--edition", HEAD_SIDE) if takes_edition_head(checkout) else ()


def takes_edition_head(checkout: Path) -> bool:
    """Whether the engine that grades ``checkout`` takes ``--edition head``.

    A checkout without ``src/coding_agent_playbook`` is graded by this engine,
    which does; a checkout with an engine does when it ships the pinned-sample
    module (``evals/graded_source.py``, added with the flag). An older engine
    has no pinned samples, so it grades its own text without the flag.

    Example::

        >>> takes_edition_head(Path("/checkout/without/an/engine"))  # doctest: +SKIP
        True
    """
    engine = checkout.joinpath(*_EDITION_HEAD_MODULE[:2])
    return not engine.is_dir() or checkout.joinpath(*_EDITION_HEAD_MODULE).is_file()


def git_edition_builder(repo_root: Path) -> EditionBuilder:
    """An edition builder reading ``repo_root``'s tags (``release.edition_build``).

    Example::

        >>> git_edition_builder(repo)("v0.1.0", work / "edition-base")  # doctest: +SKIP
        PosixPath('.../edition-base/editions/v0.1.0')
    """

    def build(tag: str, dest: Path) -> Path:
        try:
            return build_edition(repo_root, tag, dest)
        except EditionBuildError as exc:
            raise ComparisonError(f"--compare edition:{tag}: {exc}") from exc

    return build


def git_worktree_checkout(repo_root: Path) -> CheckoutFactory:
    """A checkout factory adding a detached ``git worktree`` of ``repo_root`` per ref.

    The worktree is removed when the ``with`` block ends, even on an error.

    Example::

        >>> with git_worktree_checkout(repo)("origin/main", dest) as path:  # doctest: +SKIP
        ...     (path / "README.md").exists()
        True
    """

    @contextmanager
    def checkout(ref: str, dest: Path) -> Iterator[Path]:
        dest.parent.mkdir(parents=True, exist_ok=True)
        _git(repo_root, "worktree", "add", "--detach", str(dest), ref)
        try:
            yield dest
        finally:
            _git(repo_root, "worktree", "remove", "--force", str(dest))

    return checkout


def _git(repo_root: Path, *args: str) -> None:
    try:
        subprocess.run(
            ["git", "-C", str(repo_root), *args],
            env=without_repo_location(os.environ),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
            check=True,
        )
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", None) or str(exc)
        raise ComparisonError(f"git {' '.join(args)} failed in {repo_root}: {detail}") from exc
