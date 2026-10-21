"""Prompt sets: versions of a layer's prompts under the same names (D76, ADR 0008).

A layer's ``prompts/`` holds the v1 set; ``prompts/v2/`` holds the v2 set, one
file per v1 prompt, matched by prompt id (its *twin*). The committed config key
``prompts`` (``Config.prompt_set``) picks the set a sync renders. A v2 prompt
replaces its v1 twin's text only; a prompt with no twin keeps its v1 text, so the
listing's prompt names never change. ``playbook validate`` reports a missing twin
(``validation.prompts.check_prompt_set_twins``), and eval samples keep grading v1
unless a run asks for another set (``evals.prompting.render_prompt``).

A leaf module: no engine imports, so ``config`` and ``evals`` can read it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from pathlib import Path

#: The set a repo renders without a ``prompts`` key, and the one eval samples grade.
DEFAULT_PROMPT_SET: Final = "v1"

#: Every prompt set, in order; each one after the first lives in ``prompts/<name>/``.
PROMPT_SETS: Final = (DEFAULT_PROMPT_SET, "v2")


def prompt_set_dirs(prompts_root: Path) -> tuple[Path, ...]:
    """The ``prompts/<set>/`` directories of the sets after v1, present or not.

    The v1 walk of ``prompts_root`` skips them, so a v2 prompt never renders as
    a second prompt of the same id.

    Example::

        >>> prompt_set_dirs(Path("catalog/core/prompts"))  # doctest: +SKIP
        (PosixPath('catalog/core/prompts/v2'),)
    """
    return tuple(prompts_root / name for name in PROMPT_SETS[1:])


def prompt_set_dir(prompts_root: Path, prompt_set: str) -> Path:
    """Where ``prompt_set``'s prompts live: ``prompts_root`` for v1, else ``prompts/<set>/``.

    Example::

        >>> prompt_set_dir(Path("prompts"), "v2").as_posix()  # doctest: +SKIP
        'prompts/v2'
    """
    return prompts_root if prompt_set == DEFAULT_PROMPT_SET else prompts_root / prompt_set


__all__ = ["DEFAULT_PROMPT_SET", "PROMPT_SETS", "prompt_set_dir", "prompt_set_dirs"]
