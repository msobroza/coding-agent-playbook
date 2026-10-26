"""Eval targets: which harness, and which model, an eval run drives (spec #281).

An Eval target is a named harness + model pair. The consumer config's ``[evals]``
table names them once (``evals.target_config`` reads it); a run picks one with
``playbook eval --target <name>`` or the ``<harness>:<model>`` shorthand. The
model is sent to the harness exactly as written: no alias table, no rewriting.

The resolution order is :func:`resolve_target`'s: ``--target``, then the
``PLAYBOOK_EVAL_TARGET`` environment variable, then the local file's ``default``,
then the committed file's, then today's behaviour, :data:`BUILTIN_TARGET`
(Claude Code on its own default model, recorded as ``default``).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME
from coding_agent_playbook.exit_two import ExitTwoError

if TYPE_CHECKING:
    from collections.abc import Mapping

    from coding_agent_playbook.evals.endpoints import Endpoint

#: The environment variable that picks a target when ``--target`` is absent.
TARGET_ENV_VAR: Final = "PLAYBOOK_EVAL_TARGET"

#: Separates the harness from the model in the ``<harness>:<model>`` shorthand.
#: Split on the first one only: model ids may contain colons themselves.
SHORTHAND_SEPARATOR: Final = ":"

#: Where a target comes from, as ``playbook eval --targets`` prints it.
BUILTIN_SOURCE: Final = "built-in"


class TargetError(ExitTwoError):
    """A target name or shorthand that names no target; ``playbook`` exits 2.

    Example::

        >>> str(TargetError("unknown eval target 'x'"))
        "unknown eval target 'x'"
    """


@dataclass(frozen=True)
class EvalTarget:
    """One harness + model pair an eval run can drive.

    ``harness`` is a runner name from the ``coding_agent_playbook.runners`` group
    (``claude_code``, ``opencode``, ``fake``); ``model`` is sent to it unchanged,
    ``None`` leaving the harness on its own default. ``runs`` and ``label`` are
    optional (``label`` is display only). ``source`` says where the target is
    defined: a config file name, ``--target``, ``--runner``, the environment
    variable or :data:`BUILTIN_SOURCE`. ``endpoint`` is the custom endpoint the
    harness reaches (``None``: the harness's own settings and login), and
    ``small_model`` the background model sent there (``None``: ``model``).

    Example::

        >>> EvalTarget("claude-opus", "claude_code", "claude-opus-5-5").display_model
        'claude-opus-5-5'
    """

    name: str
    harness: str
    model: str | None = None
    runs: int | None = None
    label: str | None = None
    source: str = BUILTIN_SOURCE
    endpoint: Endpoint | None = None
    small_model: str | None = None

    @property
    def display_model(self) -> str:
        """The model as printed: the id, or ``(harness default)`` when none is set.

        Example::

            >>> BUILTIN_TARGET.display_model
            '(harness default)'
        """
        return self.model if self.model is not None else "(harness default)"


#: Today's behaviour when nothing picks a target: Claude Code on its default model.
BUILTIN_TARGET: Final = EvalTarget(name="default", harness="claude_code")


@dataclass(frozen=True)
class JudgeSettings:
    """``[evals.judge]``: the LLM judge's model and judge samples, for every target.

    ``None`` keeps today's behaviour (the judge CLI's default model; one judge
    sample unless ``--judge-samples`` says otherwise; the CLI's own settings and
    login, unless ``endpoint`` names a custom endpoint).

    Example::

        >>> JudgeSettings().samples is None
        True
    """

    model: str | None = None
    samples: int | None = None
    endpoint: Endpoint | None = None


@dataclass(frozen=True)
class EvalSettings:
    """The ``[evals]`` table of both config files, checked and merged.

    ``targets`` holds every named target, committed and local (each knows its
    file); ``committed_default`` / ``local_default`` are each file's ``default``
    (a name or a shorthand); ``release`` is the committed list of target names
    release metrics run on.

    Example::

        >>> EvalSettings().targets
        {}
    """

    targets: Mapping[str, EvalTarget] = field(default_factory=dict)
    committed_default: str | None = None
    local_default: str | None = None
    release: tuple[str, ...] = ()
    judge: JudgeSettings = field(default_factory=JudgeSettings)


def lookup_target(settings: EvalSettings, spec: str, *, source: str) -> EvalTarget:
    """The target ``spec`` names: a configured name, else a ``<harness>:<model>`` shorthand.

    ``source`` (``--target``, the variable or a file) is named in the error and
    recorded on a shorthand target. A name that matches nothing raises
    :class:`TargetError` listing the configured names.

    Example::

        >>> lookup_target(EvalSettings(), "opencode:my-org/coder", source="--target").model
        'my-org/coder'
    """
    configured = settings.targets.get(spec)
    if configured is not None:
        return configured
    if SHORTHAND_SEPARATOR not in spec:
        names = ", ".join(sorted(settings.targets)) or "(none configured)"
        raise TargetError(
            f"unknown eval target {spec!r} (from {source}); configured targets: {names}; "
            "or pass <harness>:<model>, for example claude_code:claude-opus-5-5"
        )
    harness, model = spec.split(SHORTHAND_SEPARATOR, 1)
    if not harness or not model:
        raise TargetError(
            f"eval target {spec!r} (from {source}) must be <harness>:<model> with both "
            "parts non-empty, for example opencode:my-org/coder-32b"
        )
    return EvalTarget(name=spec, harness=harness, model=model, source=source)


def target_selection(
    settings: EvalSettings, *, cli_value: str | None, env: Mapping[str, str]
) -> tuple[str, str] | None:
    """The ``(spec, source)`` of the first source that names a target, ``None`` if none does.

    The order is ``--target`` (``cli_value``), :data:`TARGET_ENV_VAR` in ``env``
    (an empty value counts as unset), the local file's ``default``, then the
    committed file's. ``playbook eval --targets`` prints it as the default.

    Example::

        >>> target_selection(EvalSettings(), cli_value=None, env={TARGET_ENV_VAR: "x"})
        ('x', 'PLAYBOOK_EVAL_TARGET')
    """
    candidates = (
        (cli_value, "--target"),
        (env.get(TARGET_ENV_VAR) or None, TARGET_ENV_VAR),
        (settings.local_default, f"{CONFIG_LOCAL_FILENAME} [evals] default"),
        (settings.committed_default, f"{CONFIG_FILENAME} [evals] default"),
    )
    return next(((spec, source) for spec, source in candidates if spec is not None), None)


def resolve_target(
    settings: EvalSettings, *, cli_value: str | None, env: Mapping[str, str]
) -> EvalTarget:
    """The target a run drives: :func:`target_selection`'s, else :data:`BUILTIN_TARGET`.

    Raises :class:`TargetError` when the selected spec names no target.

    Example::

        >>> resolve_target(EvalSettings(), cli_value=None, env={}).name
        'default'
    """
    selected = target_selection(settings, cli_value=cli_value, env=env)
    if selected is None:
        return BUILTIN_TARGET
    spec, source = selected
    return lookup_target(settings, spec, source=source)


def runner_alias_target(runner: str) -> EvalTarget:
    """The target ``--runner <name>`` stands for: that harness, no model (its CLI default).

    Example::

        >>> runner_alias_target("fake").source
        '--runner'
    """
    return EvalTarget(name=runner, harness=runner, source="--runner")
