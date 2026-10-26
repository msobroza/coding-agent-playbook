"""What ``playbook eval --record`` refuses: a target or judge whose model can move (ticket 07).

Release metrics compare one release with the previous one, so the models must
stay fixed between them. A **moving alias** is a model name the harness resolves
to whatever model is current: Claude Code's ``opus``, ``sonnet``, ``haiku``,
``opusplan``, ``best`` and ``default`` (with or without a ``[1m]`` suffix or a
``provider/`` prefix), and any name ending in ``latest`` (``-latest``,
``:latest``). Everything else is taken as pinned, since the model is sent to the
harness exactly as written.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from coding_agent_playbook.evals.targets import EvalTarget

#: Claude Code's model aliases, each resolved by the CLI to the current model of its family.
MOVING_ALIASES: Final = frozenset({"default", "best", "opus", "sonnet", "haiku", "opusplan"})
#: A ``[1m]``-style option suffix Claude Code accepts after a model or an alias.
_OPTION_SUFFIX: Final = re.compile(r"\[[^\]]*\]$")
#: ``-latest``, ``:latest``, ``.latest`` or a bare ``latest`` at the end of a name.
_LATEST: Final = re.compile(r"(?:^|[-:._/@])latest$")


class RecordRefusedError(ExitTwoError):
    """``--record`` cannot run as asked (unpinned models, bad flags); ``playbook`` exits 2.

    Example::

        >>> str(RecordRefusedError("x"))
        'x'
    """


def is_moving_alias(model: str) -> bool:
    """Whether ``model`` names whatever model is current rather than one fixed model.

    Example::

        >>> is_moving_alias("opus"), is_moving_alias("claude-opus-5-5")
        (True, False)
        >>> is_moving_alias("anthropic/claude-sonnet-latest"), is_moving_alias("sonnet[1m]")
        (True, True)
    """
    name = _OPTION_SUFFIX.sub("", model.strip()).lower()
    if _LATEST.search(name):
        return True
    return name.rsplit("/", 1)[-1] in MOVING_ALIASES


def check_recordable(target: EvalTarget, *, judge_model: str | None, uses_judge: bool) -> None:
    """Raise :class:`RecordRefusedError` unless every model of the run is pinned.

    The target needs an explicit model that is not a moving alias, and so does
    its ``small_model`` when set; when the run uses a judge, ``[evals.judge] model`` must be set and pinned too.

    Example::

        >>> check_recordable(EvalTarget("t", "fake", "m-1"), judge_model=None, uses_judge=False)
    """
    if target.model is None:
        raise RecordRefusedError(
            f"--record needs a target with an explicit model; target {target.name!r} "
            f"(harness {target.harness!r}) runs the harness default. Set "
            "[evals.targets.<name>] model, or pass --target <harness>:<model>"
        )
    if is_moving_alias(target.model):
        raise RecordRefusedError(
            f"--record refuses target {target.name!r}: model {target.model!r} is a moving "
            "alias, so the next release could grade another model; name a pinned model id, "
            "for example claude-opus-5-5"
        )
    if target.small_model is not None and is_moving_alias(target.small_model):
        raise RecordRefusedError(
            f"--record refuses target {target.name!r}: small_model {target.small_model!r} is "
            "a moving alias, so the next release could run another background model; name a "
            "pinned model id, for example claude-haiku-4-5"
        )
    if uses_judge:
        _check_judge_model(judge_model)


def _check_judge_model(judge_model: str | None) -> None:
    if judge_model is None:
        raise RecordRefusedError(
            "--record with --judge needs a pinned judge model; set [evals.judge] model, "
            'for example model = "claude-opus-5-5"'
        )
    if is_moving_alias(judge_model):
        raise RecordRefusedError(
            f"--record refuses [evals.judge] model {judge_model!r}: it is a moving alias; "
            "name a pinned model id, for example claude-opus-5-5"
        )
