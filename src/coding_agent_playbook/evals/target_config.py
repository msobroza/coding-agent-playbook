"""The ``[evals]`` table of the consumer config: named Eval targets, the default and the judge.

``Config`` does not own ``[evals]`` (it rides along in ``extra_tables``); this
module reads it from both files, like ``metrics_gate.config`` reads ``[metrics]``.
The committed file names the team's targets, its ``default`` and the ``release``
list; the local file may add targets, change the default and override
``[evals.judge]`` keys, so one engineer's choices never land in a commit::

    [evals]
    default = "claude-opus"
    release = ["claude-opus"]

    [evals.targets.claude-opus]
    harness = "claude_code"
    model = "claude-opus-5-5"   # sent unchanged
    runs = 3                    # optional
    label = "Claude Opus"       # optional, display only

    [evals.judge]
    model = "claude-opus-5-5"
    samples = 3

Every mistake is a :class:`~coding_agent_playbook.config.schema.ConfigError`
naming the file, the key, the value and the expected shape.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME, ConfigFiles
from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.evals.targets import (
    EvalSettings,
    EvalTarget,
    JudgeSettings,
    TargetError,
    lookup_target,
)

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

#: The keys of one ``[evals.targets.<name>]`` table (ticket 06 adds the endpoint keys).
_TARGET_KEYS: Final = frozenset({"harness", "model", "runs", "label"})
#: The keys of ``[evals]`` in the committed file.
_COMMITTED_KEYS: Final = frozenset({"default", "release", "targets", "judge"})
#: The keys of ``[evals]`` in the local file: no ``release`` (release metrics are the team's).
_LOCAL_KEYS: Final = frozenset({"default", "targets", "judge"})
#: The keys of ``[evals.judge]``.
_JUDGE_KEYS: Final = frozenset({"model", "samples"})
#: A target name: no ``:``, which would read as the ``<harness>:<model>`` shorthand.
_TARGET_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")


def load_eval_settings(repo_root: Path) -> EvalSettings:
    """The checked ``[evals]`` settings of ``repo_root``'s two config files.

    Either file may be absent (no file, no table: the zero-config defaults).

    Example::

        >>> load_eval_settings(Path("/no/such/repo")).targets
        {}
    """
    files = ConfigFiles(repo_root)
    committed = files.committed_table("evals")
    local = files.local_overrides().get("evals", {})
    return parse_eval_settings(committed, local)


def parse_eval_settings(committed: object, local: object) -> EvalSettings:
    """Check and merge the committed and the local ``[evals]`` tables.

    Local targets are added to the committed ones (redefining a committed name is
    an error); each file's ``default`` is kept apart for the resolution order;
    local ``[evals.judge]`` keys override committed ones.

    Example::

        >>> parse_eval_settings({"targets": {"o": {"harness": "opencode"}}}, {}).targets["o"].harness
        'opencode'
    """
    committed_table = _evals_table(committed, CONFIG_FILENAME, _COMMITTED_KEYS)
    local_table = _evals_table(local, CONFIG_LOCAL_FILENAME, _LOCAL_KEYS)
    committed_targets = _targets(committed_table, CONFIG_FILENAME)
    local_targets = _targets(local_table, CONFIG_LOCAL_FILENAME)
    _refuse_redefined(committed_targets, local_targets)
    settings = EvalSettings(
        targets={**committed_targets, **local_targets},
        committed_default=_default(committed_table, CONFIG_FILENAME),
        local_default=_default(local_table, CONFIG_LOCAL_FILENAME),
        release=_release(committed_table, committed_targets),
        judge=_judge(committed_table, local_table),
    )
    _check_defaults(settings, committed_targets)
    return settings


def _evals_table(value: object, source: str, allowed: frozenset[str]) -> Mapping[str, object]:
    """``value`` as an ``[evals]`` table with only ``allowed`` keys, else ``ConfigError``."""
    table = _table(value, source, "[evals]")
    _refuse_unknown_keys(table, source, "[evals]", allowed)
    return table


def _table(value: object, source: str, label: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise ConfigError(f"{source}: {label} must be a table, got {value!r}")
    return value


def _refuse_unknown_keys(
    table: Mapping[str, object], source: str, label: str, allowed: frozenset[str]
) -> None:
    unknown = sorted(set(table) - allowed)
    if unknown:
        raise ConfigError(
            f"{source}: {label} has unknown key(s) {unknown}; expected only {sorted(allowed)}"
        )


def _targets(table: Mapping[str, object], source: str) -> dict[str, EvalTarget]:
    """Each ``[evals.targets.<name>]`` of one file, checked, as an :class:`EvalTarget`."""
    targets = _table(table.get("targets", {}), source, "[evals.targets]")
    return {name: _target(name, spec, source) for name, spec in targets.items()}


def _target(name: str, value: object, source: str) -> EvalTarget:
    label = f"[evals.targets.{name}]"
    if not _TARGET_NAME.fullmatch(name):
        raise ConfigError(
            f"{source}: {label}: a target name is letters, digits, '.', '_' or '-' "
            f"(no ':', which reads as <harness>:<model>), got {name!r}"
        )
    spec = _table(value, source, label)
    _refuse_unknown_keys(spec, source, label, _TARGET_KEYS)
    if "harness" not in spec:
        raise ConfigError(f'{source}: {label} needs harness = "<runner name>", e.g. "claude_code"')
    return EvalTarget(
        name=name,
        harness=_text(spec, "harness", source, label),
        model=_optional_text(spec, "model", source, label),
        runs=_optional_count(spec, "runs", source, label),
        label=_optional_text(spec, "label", source, label),
        source=source,
    )


def _text(table: Mapping[str, object], key: str, source: str, label: str) -> str:
    value = table[key]
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{source}: {label} {key} must be a non-empty string, got {value!r}")
    return value


def _optional_text(table: Mapping[str, object], key: str, source: str, label: str) -> str | None:
    return _text(table, key, source, label) if key in table else None


def _optional_count(table: Mapping[str, object], key: str, source: str, label: str) -> int | None:
    if key not in table:
        return None
    value = table[key]
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ConfigError(f"{source}: {label} {key} must be an integer >= 1, got {value!r}")
    return value


def _refuse_redefined(committed: Mapping[str, EvalTarget], local: Mapping[str, EvalTarget]) -> None:
    clash = sorted(set(committed) & set(local))
    if clash:
        raise ConfigError(
            f"{CONFIG_LOCAL_FILENAME}: [evals.targets] redefines {clash}, already defined in "
            f"{CONFIG_FILENAME}; give the local target another name"
        )


def _default(table: Mapping[str, object], source: str) -> str | None:
    return _optional_text(table, "default", source, "[evals]")


def _release(table: Mapping[str, object], targets: Mapping[str, EvalTarget]) -> tuple[str, ...]:
    """The committed ``release`` list: names of committed targets only."""
    value = table.get("release", [])
    if not isinstance(value, list) or not all(isinstance(name, str) for name in value):
        raise ConfigError(
            f"{CONFIG_FILENAME}: [evals] release must be a list of target names, got {value!r}"
        )
    unknown = [name for name in value if name not in targets]
    if unknown:
        raise ConfigError(
            f"{CONFIG_FILENAME}: [evals] release names unknown target(s) {unknown}; "
            f"targets defined in {CONFIG_FILENAME}: {sorted(targets)}"
        )
    return tuple(value)


def _judge(committed: Mapping[str, object], local: Mapping[str, object]) -> JudgeSettings:
    """``[evals.judge]``: the committed keys, each overridden by the local file's."""
    settings = JudgeSettings()
    for table, source in ((committed, CONFIG_FILENAME), (local, CONFIG_LOCAL_FILENAME)):
        judge = _table(table.get("judge", {}), source, "[evals.judge]")
        _refuse_unknown_keys(judge, source, "[evals.judge]", _JUDGE_KEYS)
        if "model" in judge:
            settings = replace(settings, model=_text(judge, "model", source, "[evals.judge]"))
        if "samples" in judge:
            samples = _optional_count(judge, "samples", source, "[evals.judge]")
            settings = replace(settings, samples=samples)
    return settings


def _check_defaults(settings: EvalSettings, committed_targets: Mapping[str, EvalTarget]) -> None:
    """Each ``default`` must name a target it can see: the committed one, a committed target."""
    committed_only = replace(settings, targets=committed_targets)
    checks = (
        (committed_only, settings.committed_default, CONFIG_FILENAME),
        (settings, settings.local_default, CONFIG_LOCAL_FILENAME),
    )
    for visible, default, source in checks:
        if default is None:
            continue
        try:
            lookup_target(visible, default, source=f"{source} [evals] default")
        except TargetError as exc:
            raise ConfigError(str(exc)) from exc
