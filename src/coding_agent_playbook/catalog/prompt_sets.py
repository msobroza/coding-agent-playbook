"""Prompt sets: versions of a layer's prompts under the same names (D76, ADR 0008).

A layer's ``prompts/`` holds the v1 set; ``prompts/v2/`` holds the v2 set, one
file per v1 prompt, matched by prompt id (its *twin*, CONTEXT.md). The committed
config key ``prompts`` (``Config.prompt_set``) picks the set a sync renders. A v2
prompt replaces its v1 twin's text only; a prompt with no twin keeps its v1 text,
so the listing's prompt names never change. ``playbook validate`` reports a missing
twin (``validation.prompts.check_prompt_set_twins``), and eval samples keep grading
v1 unless a run asks for another set (``evals.prompting.render_prompt``).

A leaf module: no engine imports, so ``config`` and ``evals`` can read it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final, Literal, TypeGuard, get_args

if TYPE_CHECKING:
    from pathlib import Path

#: A prompt set's name: the closed set of values of the ``prompts`` key.
PromptSet = Literal["v1", "v2"]

#: Every prompt set, in order; each one after the first lives in ``prompts/<name>/``.
PROMPT_SETS: Final[tuple[PromptSet, ...]] = get_args(PromptSet)

#: The set a repo renders without a ``prompts`` key, and the one eval samples grade.
DEFAULT_PROMPT_SET: Final[PromptSet] = "v1"

#: The sets after v1, each in its own ``prompts/<name>/`` directory.
LATER_PROMPT_SETS: Final[tuple[PromptSet, ...]] = tuple(
    name for name in PROMPT_SETS if name != DEFAULT_PROMPT_SET
)


def is_prompt_set(value: object) -> TypeGuard[PromptSet]:
    """True when ``value`` names a prompt set, compared exactly.

    Example::

        >>> is_prompt_set("v2"), is_prompt_set("V2"), is_prompt_set("v3")
        (True, False, False)
    """
    return value in PROMPT_SETS


def require_prompt_set(value: object) -> PromptSet:
    """``value`` as a :data:`PromptSet`; a :class:`ValueError` naming the sets otherwise.

    The guard of every entry point that takes a set from a caller, so a bad value
    fails loudly instead of rendering v1 or reading ``prompts/<value>/``.

    Example::

        >>> require_prompt_set("v3")
        Traceback (most recent call last):
        ...
        ValueError: unknown prompt set 'v3'; expected one of 'v1', 'v2'
    """
    if is_prompt_set(value):
        return value
    expected = ", ".join(repr(name) for name in PROMPT_SETS)
    raise ValueError(f"unknown prompt set {value!r}; expected one of {expected}")


def prompt_set_dirs(prompts_root: Path) -> tuple[Path, ...]:
    """The ``prompts/<set>/`` directories of :data:`LATER_PROMPT_SETS`, present or not.

    The v1 walk of ``prompts_root`` skips them, so a v2 prompt never renders as
    a second prompt of the same id.

    Example::

        >>> prompt_set_dirs(Path("catalog/core/prompts"))
        (PosixPath('catalog/core/prompts/v2'),)
    """
    return tuple(prompts_root / name for name in LATER_PROMPT_SETS)


def prompt_set_dir(prompts_root: Path, prompt_set: PromptSet) -> Path:
    """Where ``prompt_set``'s prompts live: ``prompts_root`` for v1, else ``prompts/<set>/``.

    Example::

        >>> prompt_set_dir(Path("prompts"), "v2").as_posix()
        'prompts/v2'
    """
    require_prompt_set(prompt_set)
    return prompts_root if prompt_set == DEFAULT_PROMPT_SET else prompts_root / prompt_set


__all__ = [
    "DEFAULT_PROMPT_SET",
    "LATER_PROMPT_SETS",
    "PROMPT_SETS",
    "PromptSet",
    "is_prompt_set",
    "prompt_set_dir",
    "prompt_set_dirs",
    "require_prompt_set",
]
