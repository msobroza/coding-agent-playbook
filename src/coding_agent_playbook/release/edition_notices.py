"""The license and attribution files an edition's frozen text needs (#281 ticket 13 follow-up).

Core's vendored rules carry MIT-licensed upstream text (ADR 0004). Each core
skill that holds a source's text ships that source's notice as
``catalog/core/skills/<skill>/references/LICENSE.<source>``, and
``catalog/core/ATTRIBUTIONS.md`` credits every vendored or distilled file. An
edition that copies such a rule must carry the same notices, so ``freeze``
copies them from the tag next to the graded files and records them in the
digests file as ``notice`` artifacts (``release.edition_digests``).

:func:`notice_paths` decides which notices one graded set needs from the tag's
tree alone (``TreeLister``): the root ``ATTRIBUTIONS.md`` whenever the tag has
it, plus every ``references/LICENSE*`` file of each skill a graded file
belongs to.
"""

from __future__ import annotations

from pathlib import PurePosixPath
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.catalog.roots import CHECKOUT_CATALOG_DIRNAME

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

__all__ = ["ATTRIBUTIONS_PATH", "TreeLister", "notice_paths"]

#: ``(commit, repo dir)`` to the repo paths of the files directly in it; ``[]`` when none.
type TreeLister = Callable[[str, str], list[str]]

_CORE_DIR: Final = f"{CHECKOUT_CATALOG_DIRNAME}/core"
#: The one home of the engine layer's credits (ADR 0004).
ATTRIBUTIONS_PATH: Final = f"{_CORE_DIR}/ATTRIBUTIONS.md"
_SKILLS_DIRNAME: Final = "skills"
_REFERENCES_DIRNAME: Final = "references"
_LICENSE_PREFIX: Final = "LICENSE"
#: ``catalog/core/skills/<skill>/...``: the parts up to and including the skill name.
_SKILL_PARTS: Final = 4


def notice_paths(graded_paths: Iterable[str], commit: str, list_tree: TreeLister) -> list[str]:
    """The repo paths of the notices the graded files at ``commit`` need, sorted.

    Example::

        >>> notice_paths(["catalog/core/skills/python-coding/rules/typing.md"], sha, lister)  # doctest: +SKIP
        ['catalog/core/ATTRIBUTIONS.md', 'catalog/core/skills/python-coding/references/LICENSE.python-best-practices']
    """
    skills = sorted({skill for path in graded_paths if (skill := _skill_of(path))})
    found = [ATTRIBUTIONS_PATH] if ATTRIBUTIONS_PATH in list_tree(commit, _CORE_DIR) else []
    for skill in skills:
        references = f"{_CORE_DIR}/{_SKILLS_DIRNAME}/{skill}/{_REFERENCES_DIRNAME}"
        found += [p for p in list_tree(commit, references) if _is_license(p)]
    return sorted(set(found))


def _skill_of(repo_path: str) -> str | None:
    """``<skill>`` for a path under ``catalog/core/skills/<skill>/``, else ``None``."""
    parts = PurePosixPath(repo_path).parts
    core = PurePosixPath(_CORE_DIR).parts
    if len(parts) > _SKILL_PARTS and parts[:2] == core and parts[2] == _SKILLS_DIRNAME:
        return parts[3]
    return None


def _is_license(repo_path: str) -> bool:
    return PurePosixPath(repo_path).name.startswith(_LICENSE_PREFIX)
