"""The ``[evals]`` table of the consumer config: named Eval targets, endpoints, the default and the judge.

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
    price = { input = 3.0, output = 15.0 }  # optional, USD per million tokens

    [evals.targets.internal-claude]
    harness = "claude_code"
    endpoint = "internal"       # an [evals.endpoints.<name>] block
    model = "internal-opus"     # required on an endpoint
    small_model = "internal-haiku"  # optional, defaults to model

    [evals.judge]
    model = "claude-opus-5-5"
    samples = 3
    endpoint = "internal"       # optional
    reasoning_effort = "high"   # optional, an openai-* judge endpoint only

``[evals.endpoints]`` is read by ``evals.endpoint_config``. A committed target or
judge may name only a committed endpoint. Claude Code speaks only the Anthropic
Messages API, so a Claude Code target on another API is refused; the LLM judge
drives Claude Code on an ``anthropic`` endpoint and grades straight over HTTPS on
an ``openai-responses`` or ``openai-chat`` one (``evals.api_judge``).

Every mistake is a :class:`~coding_agent_playbook.config.schema.ConfigError`
naming the file, the key, the value and the expected shape.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.config.files import CONFIG_FILENAME, CONFIG_LOCAL_FILENAME, ConfigFiles
from coding_agent_playbook.config.schema import ConfigError
from coding_agent_playbook.evals.config_shapes import (
    optional_count,
    optional_text,
    refuse_unknown_keys,
    table,
    text,
)
from coding_agent_playbook.evals.endpoint_config import parse_endpoints
from coding_agent_playbook.evals.endpoints import API_ANTHROPIC, REASONING_EFFORTS
from coding_agent_playbook.evals.targets import (
    EvalSettings,
    EvalTarget,
    JudgeSettings,
    TargetError,
    lookup_target,
)
from coding_agent_playbook.evals.token_usage import TokenPrice

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from coding_agent_playbook.evals.endpoints import Endpoint

#: The keys of one ``[evals.targets.<name>]`` table.
_TARGET_KEYS: Final = frozenset(
    {"harness", "model", "runs", "label", "price", "endpoint", "small_model"}
)
#: The keys of a target's ``price`` table: USD per million tokens, both required.
_PRICE_KEYS: Final = frozenset({"input", "output"})
#: The keys of ``[evals]`` in the committed file.
_COMMITTED_KEYS: Final = frozenset({"default", "release", "targets", "judge", "endpoints"})
#: The keys of ``[evals]`` in the local file: no ``release`` (release metrics are the team's).
_LOCAL_KEYS: Final = frozenset({"default", "targets", "judge", "endpoints"})
#: The keys of ``[evals.judge]``.
_JUDGE_KEYS: Final = frozenset({"model", "samples", "endpoint", "reasoning_effort"})
#: A target name: no ``:``, which would read as the ``<harness>:<model>`` shorthand.
_TARGET_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
#: The harness that speaks only the Anthropic Messages API.
_CLAUDE_CODE: Final = "claude_code"
_OPENCODE_HINT: Final = 'use harness = "opencode" for this endpoint'


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
    local ``[evals.judge]`` keys override committed ones. A committed target or
    judge sees the committed endpoints only, each with any token part the local
    file adds.

    Example::

        >>> parse_eval_settings({"targets": {"o": {"harness": "opencode"}}}, {}).targets["o"].harness
        'opencode'
    """
    committed_table = _evals_table(committed, CONFIG_FILENAME, _COMMITTED_KEYS)
    local_table = _evals_table(local, CONFIG_LOCAL_FILENAME, _LOCAL_KEYS)
    committed_names, endpoints = parse_endpoints(committed_table, local_table)
    committed_endpoints = {name: endpoints[name] for name in committed_names}
    committed_targets = _targets(committed_table, CONFIG_FILENAME, committed_endpoints)
    local_targets = _targets(local_table, CONFIG_LOCAL_FILENAME, endpoints)
    _refuse_redefined(committed_targets, local_targets)
    settings = EvalSettings(
        targets={**committed_targets, **local_targets},
        committed_default=_default(committed_table, CONFIG_FILENAME),
        local_default=_default(local_table, CONFIG_LOCAL_FILENAME),
        release=_release(committed_table, committed_targets),
        judge=_judge(committed_table, local_table, committed_endpoints, endpoints),
    )
    _check_defaults(settings, committed_targets)
    return settings


def _evals_table(value: object, source: str, allowed: frozenset[str]) -> Mapping[str, object]:
    """``value`` as an ``[evals]`` table with only ``allowed`` keys, else ``ConfigError``."""
    evals = table(value, source, "[evals]")
    refuse_unknown_keys(evals, source, "[evals]", allowed)
    return evals


def _targets(
    evals: Mapping[str, object], source: str, endpoints: Mapping[str, Endpoint]
) -> dict[str, EvalTarget]:
    """Each ``[evals.targets.<name>]`` of one file, checked, as an :class:`EvalTarget`."""
    targets = table(evals.get("targets", {}), source, "[evals.targets]")
    return {name: _target(name, spec, source, endpoints) for name, spec in targets.items()}


def _target(name: str, value: object, source: str, endpoints: Mapping[str, Endpoint]) -> EvalTarget:
    label = f"[evals.targets.{name}]"
    if not _TARGET_NAME.fullmatch(name):
        raise ConfigError(
            f"{source}: {label}: a target name is letters, digits, '.', '_' or '-' "
            f"(no ':', which reads as <harness>:<model>), got {name!r}"
        )
    spec = table(value, source, label)
    refuse_unknown_keys(spec, source, label, _TARGET_KEYS)
    if "harness" not in spec:
        raise ConfigError(f'{source}: {label} needs harness = "<runner name>", e.g. "claude_code"')
    target = EvalTarget(
        name=name,
        harness=text(spec, "harness", source, label),
        model=optional_text(spec, "model", source, label),
        runs=optional_count(spec, "runs", source, label),
        label=optional_text(spec, "label", source, label),
        source=source,
        endpoint=_endpoint_ref(spec, source, label, endpoints),
        small_model=optional_text(spec, "small_model", source, label),
        price=_price(spec, source, label),
    )
    _check_target_endpoint(target, source, label)
    return target


def _price(spec: Mapping[str, object], source: str, label: str) -> TokenPrice | None:
    """A target's optional ``price = { input = <usd>, output = <usd> }`` per million tokens."""
    if "price" not in spec:
        return None
    price = table(spec["price"], source, f"{label} price")
    if set(price) != _PRICE_KEYS:
        raise ConfigError(
            f"{source}: {label} price must have exactly the keys {sorted(_PRICE_KEYS)} "
            f"(USD per million tokens), got {sorted(price)}"
        )
    return TokenPrice(
        input_per_million=_usd(price, "input", source, label),
        output_per_million=_usd(price, "output", source, label),
    )


def _usd(price: Mapping[str, object], key: str, source: str, label: str) -> float:
    value = price[key]
    if isinstance(value, bool) or not isinstance(value, int | float) or value < 0:
        raise ConfigError(
            f"{source}: {label} price.{key} must be a number >= 0 (USD per million tokens), "
            f"got {value!r}"
        )
    return float(value)


def _endpoint_ref(
    spec: Mapping[str, object], source: str, label: str, endpoints: Mapping[str, Endpoint]
) -> Endpoint | None:
    """The endpoint ``spec["endpoint"]`` names among those ``source`` may see, else ``None``."""
    name = optional_text(spec, "endpoint", source, label)
    if name is None:
        return None
    endpoint = endpoints.get(name)
    if endpoint is None:
        visible = sorted(endpoints) or "(none)"
        raise ConfigError(
            f"{source}: {label} endpoint {name!r} is not declared; endpoints {source} "
            f"can name: {visible}"
        )
    return endpoint


def _check_target_endpoint(target: EvalTarget, source: str, label: str) -> None:
    """An endpoint target needs a model, and Claude Code an ``anthropic`` endpoint."""
    if target.endpoint is None:
        if target.small_model is not None:
            raise ConfigError(f"{source}: {label} small_model needs an endpoint")
        return
    if target.model is None:
        raise ConfigError(
            f"{source}: {label} needs model = the id endpoint {target.endpoint.name!r} serves"
        )
    if target.harness == _CLAUDE_CODE:
        _require_anthropic(target.endpoint, source, label, "Claude Code")


def _require_anthropic(endpoint: Endpoint, source: str, label: str, who: str) -> None:
    if endpoint.api != API_ANTHROPIC:
        raise ConfigError(
            f"{source}: {label} {who} speaks only api = {API_ANTHROPIC!r}, but endpoint "
            f"{endpoint.name!r} has api = {endpoint.api!r}; {_OPENCODE_HINT}"
        )


def _refuse_redefined(committed: Mapping[str, EvalTarget], local: Mapping[str, EvalTarget]) -> None:
    clash = sorted(set(committed) & set(local))
    if clash:
        raise ConfigError(
            f"{CONFIG_LOCAL_FILENAME}: [evals.targets] redefines {clash}, already defined in "
            f"{CONFIG_FILENAME}; give the local target another name"
        )


def _default(evals: Mapping[str, object], source: str) -> str | None:
    return optional_text(evals, "default", source, "[evals]")


def _release(evals: Mapping[str, object], targets: Mapping[str, EvalTarget]) -> tuple[str, ...]:
    """The committed ``release`` list: names of committed targets only."""
    value = evals.get("release", [])
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


def _judge(
    committed: Mapping[str, object],
    local: Mapping[str, object],
    committed_endpoints: Mapping[str, Endpoint],
    endpoints: Mapping[str, Endpoint],
) -> JudgeSettings:
    """``[evals.judge]``: the committed keys, each overridden by the local file's."""
    label = "[evals.judge]"
    settings = JudgeSettings()
    layers = (
        (committed, CONFIG_FILENAME, committed_endpoints),
        (local, CONFIG_LOCAL_FILENAME, endpoints),
    )
    for evals, source, visible in layers:
        judge = table(evals.get("judge", {}), source, label)
        refuse_unknown_keys(judge, source, label, _JUDGE_KEYS)
        if "model" in judge:
            settings = replace(settings, model=text(judge, "model", source, label))
        if "samples" in judge:
            settings = replace(settings, samples=optional_count(judge, "samples", source, label))
        if "endpoint" in judge:
            endpoint = _endpoint_ref(judge, source, label, visible)
            settings = replace(settings, endpoint=endpoint)
        if "reasoning_effort" in judge:
            effort = _reasoning_effort(judge, source, label)
            settings = replace(settings, reasoning_effort=effort)
    _check_judge_endpoint(settings)
    return settings


def _reasoning_effort(judge: Mapping[str, object], source: str, label: str) -> str:
    """``reasoning_effort``: one of :data:`REASONING_EFFORTS`."""
    effort = text(judge, "reasoning_effort", source, label)
    if effort not in REASONING_EFFORTS:
        raise ConfigError(
            f"{source}: {label} reasoning_effort = {effort!r}, expected one of "
            f"{', '.join(REASONING_EFFORTS)}"
        )
    return effort


def _check_judge_endpoint(settings: JudgeSettings) -> None:
    """A judge on an endpoint needs an explicit model: the id the endpoint serves.

    Any API is fine: the LLM judge drives Claude Code on an ``anthropic`` endpoint
    and grades over HTTPS on an ``openai-*`` one.
    """
    endpoint = settings.endpoint
    label = "[evals.judge]"
    if settings.reasoning_effort is not None and (
        endpoint is None or endpoint.api == API_ANTHROPIC
    ):
        raise ConfigError(
            f"{label} reasoning_effort = {settings.reasoning_effort!r} is sent only by the judge "
            "on an openai-responses or openai-chat endpoint; set endpoint to one or remove it"
        )
    if endpoint is None:
        return
    if settings.model is None:
        raise ConfigError(
            f"{endpoint.source}: {label} needs model = the id endpoint {endpoint.name!r} serves"
        )


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
