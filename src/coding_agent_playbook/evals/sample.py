"""Eval-sample data types (SPEC §15.2) — the ``[gate]``/``[rubric]``/``[verdict]``/``[aggregate]`` schema.

These are the canonical Python representations of ``eval_samples/<prompt>/<name>/sample.toml``.
The loader (:mod:`coding_agent_playbook.evals.loader`) parses the TOML; the
validator (:mod:`coding_agent_playbook.evals.validator`) enforces structural
correctness by trial-compiling the blocks; the runner
(:mod:`coding_agent_playbook.evals.run.harness_runner`) materializes + scores the sample.

There is **no** ``[expected]``/``[metrics]``/``[rubric]`` triple — a sample declares
its evaluation as up to four raw blocks the compiler
(:mod:`coding_agent_playbook.evals.compile.compiler`) turns into a per-trial structure:

* ``[gate]`` — ``{"bind": <handle table>, "expr": <bool expr | None>}``. The
  deterministic layer (file predicates, metric thresholds, composed gates). Every
  handle is a boolean :class:`~coding_agent_playbook.grading.check.Check`.
* ``[rubric]`` — same shape; the judged llm-judge layer (a ``rubric`` group of
  weighted ``JudgeCheck``\\ s, thresholded to a boolean).
* ``[verdict].trial`` — a boolean expression over ``gate``/``rubric`` (default
  ``"gate and rubric"``) deriving the per-trial verdict from the two layers.
* ``[aggregate]`` — ``{"bind": <table>, "expr": <str | None>}``. The optional
  across-trial reliability layer (``pass@k`` / ``pass^k``); omitting it runs a
  single trial. The runner runs ``N = max(k)`` trials and the aggregate composes
  them.

``run_tests``/``strict`` are no longer authored — they are *inferred*: a sample runs
tests iff it references an execution metric, and ``strict`` defaults ``False``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, Literal

from coding_agent_playbook.artifacts.retired_keys import retired_key_problem
from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE

if TYPE_CHECKING:
    from coding_agent_playbook.evals.compile.compiler import CompiledSample

#: Tolerance for the weighted-verdict ``weights`` sum check (parity with the
#: rubric-group sum rule in :mod:`coding_agent_playbook.evals.compile._handles`).
_WEIGHT_SUM_TOLERANCE = 1e-3

#: Every top-level key ``sample.toml`` may carry, in authoring order. Any other
#: key is an error (#285): a misspelled key would otherwise be dropped silently
#: and the sample would grade something its author did not ask for.
SAMPLE_TOP_KEYS: Final = (
    "id",
    "description",
    "edition",
    "setup",
    "invocation",
    "gate",
    "rubric",
    "verdict",
    "aggregate",
)

#: Keys ``sample.toml`` no longer carries, with what replaced them (#302): the
#: task directory a sample lives in names the prompt it grades.
_MOVED_SAMPLE_KEYS: Final[dict[str, str]] = {
    "prompt_id": (
        "the task directory names the prompt a sample grades: keep the sample at "
        "eval_samples/<prompt>/<name>/sample.toml and delete the 'prompt_id' line"
    ),
}


#: A release tag, the name of an edition directory (``v0.1.0``, ``v1.2.0rc1``).
_EDITION_TAG: Final = re.compile(r"v[0-9][0-9A-Za-z.+-]*")


@dataclass
class SampleSetup:
    """Mock-detector facts + files in the ``setup/`` subdirectory.

    ``files`` lists the entries under ``<sample_dir>/setup/`` (relative paths);
    the runner walks ``setup/`` itself and copies into the scratch repo, so
    this list is documentation that the validator can cross-check.

    ``frameworks`` and ``python_version`` are no longer authored here — the
    runner installs the fixture's dependencies via ``uv sync`` on
    ``setup/pyproject.toml`` (which is the single source of truth for the
    project's Python version and packages), and the detector reads the same
    file directly from the materialized scratch tree.

    ``project_kind`` and the ``extra_facts`` (e.g. ``ml_stack``, so an ML-gated
    prompt can be evaluated without installing torch) override the detected
    facts when the runner renders the prompt (``evals/prompting.py``).
    """

    files: list[Path] = field(default_factory=list)
    project_kind: str = "python-unknown"
    extra_facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class SampleInvocation:
    """What the user "types" after the slash command at sample runtime."""

    prompt_args: str = ""
    input_variables: dict[str, str] = field(default_factory=dict)


@dataclass
class Layer:
    """One ``[gate]`` / ``[rubric]`` / ``[aggregate]`` block: a bind table + an expr.

    ``bind`` is the raw ``[<layer>.bind]`` handle table (one entry per handle, the
    value a binding the :func:`~coding_agent_playbook.evals.compile._handles.build_handles`
    factory turns into a :class:`~coding_agent_playbook.grading.check.Check`).
    ``expr`` is the optional boolean/aggregate expression over those handle names
    (``None`` defaults to the sole handle's name for a single-handle layer).
    """

    bind: dict[str, dict[str, Any]] = field(default_factory=dict)
    expr: str | None = None


#: The default ``[verdict].trial`` expression: both layers must pass.
_DEFAULT_VERDICT = "gate and rubric"


@dataclass(frozen=True)
class Verdict:
    """Parsed ``[verdict]`` block: a boolean ``trial`` expr OR a weighted composite.

    Mutually exclusive: a sample authors **either** the boolean form
    (``trial = "gate and rubric"``, the legacy and default mode) **or** the
    weighted-composite form (``weights = {gate = 0.4, rubric = 0.6}, fail = 0.7``);
    setting both is a :exc:`ValueError`. In the boolean form ``trial`` is the
    expression string and ``weights`` / ``fail`` / ``warn`` are ``None``; in the
    weighted form ``weights`` is non-empty and sums to ``1.0`` (±1e-3), ``fail``
    is a ``0-1`` cutoff on the composite, ``warn`` is optional, and ``trial`` is
    ``None``.
    """

    mode: Literal["boolean", "weighted"]
    trial: str | None = None
    weights: dict[str, float] | None = None
    fail: float | None = None
    warn: float | None = None


@dataclass
class EvalSample:
    """A single eval sample. Mirrors the on-disk ``eval_samples/<prompt>/<name>/sample.toml``.

    ``prompt_id`` is the prompt the sample grades, named by the task directory
    the sample lives in (``sample.toml`` does not carry it); ``id`` is
    ``<prompt>/<name>``.

    ``source_path`` is the ``sample.toml`` path (the parent directory holds
    ``setup/`` etc.). ``source_package`` is the importable package name
    (``"coding_agent_playbook"``, an overlay package, or ``"<repo-local>"``)
    so ``playbook eval --show`` and overlay collision reports can attribute the
    sample back to its layer.

    ``gate``/``rubric``/``aggregate`` are the parsed :class:`Layer` blocks (``None``
    when absent); ``verdict`` is the parsed :class:`Verdict` (the boolean
    ``trial`` expression - the default - or the weighted-composite
    ``weights`` / ``fail`` form). A sample must carry at least one of
    ``[gate]`` / ``[rubric]`` (enforced at compile time).
    """

    id: str
    prompt_id: str
    description: str
    source_path: Path
    source_package: str
    setup: SampleSetup = field(default_factory=SampleSetup)
    invocation: SampleInvocation = field(default_factory=SampleInvocation)
    gate: Layer | None = None
    rubric: Layer | None = None
    verdict: Verdict = field(
        default_factory=lambda: Verdict(mode="boolean", trial=_DEFAULT_VERDICT)
    )
    aggregate: Layer | None = None
    edition: str | None = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        prompt_id: str,
        source_path: Path,
        source_package: str,
    ) -> EvalSample:
        """Parse a TOML-shaped dict (from ``tomllib.load``) into an EvalSample.

        ``prompt_id`` comes from the sample's task directory, never from the TOML.
        Required top-level fields: ``id``, ``description``.
        Any other top-level key (:data:`SAMPLE_TOP_KEYS`) is an error naming it.
        Optional sections: ``[setup]``, ``[invocation]``, ``[gate]``, ``[rubric]``,
        ``[verdict]``, ``[aggregate]``.

        Only the *structural* shape is enforced here (each block is a table; the
        bind/expr split is well-formed). Semantic correctness — unknown check ids,
        malformed handle bindings, expression identifiers ⊄ bind keys, rubric
        weight-sum, verdict idents ⊄ present layers — is the compiler's job and is
        surfaced by the validator via :func:`compile_eval_sample`.

        Raises :exc:`ValueError` with a descriptive message on missing or
        malformed required fields. The loader catches these and wraps them
        with the sample.toml path for jump-to-file ergonomics.
        """
        _reject_unknown_top_keys(data)
        sample_id = _require_str(data, "id")
        description = _require_str(data, "description")

        setup = _parse_setup(data.get("setup", {}))
        invocation = _parse_invocation(data.get("invocation", {}))
        gate = _parse_layer(data["gate"], block="gate") if "gate" in data else None
        rubric = _parse_layer(data["rubric"], block="rubric") if "rubric" in data else None
        aggregate = (
            _parse_layer(data["aggregate"], block="aggregate") if "aggregate" in data else None
        )
        verdict = _parse_verdict(data.get("verdict", {}))
        edition = _parse_edition(data.get("edition"), source_package=source_package)

        return cls(
            id=sample_id,
            prompt_id=prompt_id,
            description=description,
            source_path=source_path,
            source_package=source_package,
            setup=setup,
            invocation=invocation,
            gate=gate,
            rubric=rubric,
            verdict=verdict,
            aggregate=aggregate,
            edition=edition,
        )

    def compiled(self) -> CompiledSample:
        """Compile this sample's blocks into a :class:`CompiledSample` (single-trial).

        A thin wrapper over :func:`compile_eval_sample`.
        """
        return compile_eval_sample(self)


def compile_eval_sample(sample: EvalSample) -> CompiledSample:
    """Compile ``sample``'s ``[gate]``/``[rubric]``/``[verdict]`` into a :class:`CompiledSample`.

    Delegates to :func:`coding_agent_playbook.evals.compile.compiler.compile_sample` with the
    sample's gate/rubric/aggregate bind tables + exprs and the verdict trial
    expression. The returned
    :class:`~coding_agent_playbook.evals.compile.compiler.CompiledSample` carries the
    per-trial :class:`~coding_agent_playbook.grading.rubric.Rubric` (the gate +
    rubric layer checks), the parsed verdict AST, and the compiled ``[aggregate]``
    layer + ``trials_needed`` (``None``/``1`` when no ``[aggregate]`` block).

    Raises :exc:`ValueError` (incl. :exc:`~coding_agent_playbook.evals.compile._expr.ExprError`)
    /:exc:`KeyError` on any structural fault the compiler catches: no layer present,
    unknown check id/metric/gate-ref/rubric-ref, malformed binding, an expression
    identifier ⊄ its bind keys, a rubric weight-sum ≠ 1.0, or a verdict identifier
    naming an absent layer. The validator turns these into validation errors.

    The compiler is imported lazily so the ``sample`` module stays import-light; the
    ``compile.compiler`` module imports only from ``grading`` (never back from ``sample``),
    so this is acyclic regardless.
    """
    from coding_agent_playbook.evals.compile.compiler import compile_sample

    return compile_sample(
        gate_bind=sample.gate.bind if sample.gate is not None else None,
        gate_expr=sample.gate.expr if sample.gate is not None else None,
        rubric_bind=sample.rubric.bind if sample.rubric is not None else None,
        rubric_expr=sample.rubric.expr if sample.rubric is not None else None,
        verdict_trial=sample.verdict.trial,
        verdict_weights=sample.verdict.weights,
        verdict_fail=sample.verdict.fail,
        verdict_warn=sample.verdict.warn,
        aggregate_bind=sample.aggregate.bind if sample.aggregate is not None else None,
        aggregate_expr=sample.aggregate.expr if sample.aggregate is not None else None,
        name=sample.id,
    )


def _reject_unknown_top_keys(data: dict[str, Any]) -> None:
    """Raise ``ValueError`` naming the first top-level key outside :data:`SAMPLE_TOP_KEYS`.

    A retired key (``version``) or a moved one (``prompt_id``) names its
    replacement instead of the list.

    Example::

        >>> _reject_unknown_top_keys({"id": "x", "editon": "v0.1.0"})
        Traceback (most recent call last):
        ValueError: unknown top-level key 'editon'; allowed keys: id, description, ...
    """
    for key in data:
        if key in SAMPLE_TOP_KEYS:
            continue
        retired = retired_key_problem(key)
        if retired is not None:
            raise ValueError(retired)
        moved = _MOVED_SAMPLE_KEYS.get(str(key))
        if moved is not None:
            raise ValueError(f"unknown top-level key {key!r}: {moved}")
        allowed = ", ".join(SAMPLE_TOP_KEYS)
        raise ValueError(f"unknown top-level key {key!r}; allowed keys: {allowed}")


def _parse_edition(raw: Any, *, source_package: str) -> str | None:
    """The pinned edition's tag, ``None`` when unpinned; only a core sample may pin one.

    Editions exist for the engine's layer only (ADR 0012), so an overlay,
    bundled plugin or repo-local sample carrying the key is an error.

    Example::

        >>> _parse_edition("v0.1.0", source_package="coding_agent_playbook")
        'v0.1.0'
    """
    if raw is None:
        return None
    if not isinstance(raw, str) or _EDITION_TAG.fullmatch(raw) is None:
        raise ValueError(f"'edition' must be a release tag such as \"v0.1.0\", got {raw!r}")
    if source_package != ENGINE_PACKAGE:
        raise ValueError(
            f"'edition' pins a sample to a frozen edition of the engine's graded set, and "
            f"only core samples (catalog/core/eval_samples/) may carry it; this sample "
            f"belongs to {source_package!r}: delete the 'edition' line"
        )
    return raw


def _require_str(data: dict[str, Any], key: str) -> str:
    if key not in data:
        raise ValueError(f"missing required field: {key!r}")
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"field {key!r} must be str, got {type(value).__name__}")
    return value


def _parse_setup(raw: Any) -> SampleSetup:
    """Parse a ``[setup]`` block into a :class:`SampleSetup`.

    Authored keys: ``files`` (list of relpaths under ``<sample_dir>/setup/``),
    ``project_kind`` (mock detector fact), plus any extra detector-fact keys
    (preserved in ``extra_facts``). ``frameworks`` / ``python_version`` are
    not authored here any more — the runner installs deps from
    ``setup/pyproject.toml`` via ``uv sync`` and the detector reads that file
    directly. A stale copy is tolerated (it lands in ``extra_facts``), but the
    prompt renderer lets it override the detected value, so delete it.

    A mocked ``ml_stack`` must be a list of names or a table of
    ``name = "version-spec"``: the prompt renderer gates rules on it, and any
    other shape would only fail later, at ``--run``.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"[setup] must be a table, got {type(raw).__name__}")
    files = [Path(p) for p in raw.get("files", [])]
    project_kind = raw.get("project_kind", "python-unknown")
    # Anything outside the typed slots is preserved in extra_facts so overlays
    # can mock new detector keys without changing this dataclass.
    known = {"files", "project_kind"}
    extra_facts = {k: v for k, v in raw.items() if k not in known}
    if not isinstance(project_kind, str):
        raise ValueError(f"[setup].project_kind must be str, got {type(project_kind).__name__}")
    if "ml_stack" in extra_facts:
        _check_name_collection("ml_stack", extra_facts["ml_stack"])
    return SampleSetup(
        files=files,
        project_kind=project_kind,
        extra_facts=extra_facts,
    )


def _check_name_collection(key: str, value: Any) -> None:
    """Raise unless ``value`` is a list of names or a ``{name: version-spec}`` table."""
    if isinstance(value, list) and all(isinstance(name, str) for name in value):
        return
    if isinstance(value, dict) and all(
        isinstance(name, str) and isinstance(spec, str) for name, spec in value.items()
    ):
        return
    raise ValueError(
        f'[setup].{key} must be a list of names (e.g. ["torch"]) or a table of '
        f'name = "version-spec", got {value!r} ({type(value).__name__})'
    )


def _parse_invocation(raw: Any) -> SampleInvocation:
    if not isinstance(raw, dict):
        raise ValueError(f"[invocation] must be a table, got {type(raw).__name__}")
    prompt_args = raw.get("prompt_args", "")
    if not isinstance(prompt_args, str):
        raise ValueError(f"[invocation].prompt_args must be str, got {type(prompt_args).__name__}")
    input_variables_raw = raw.get("input_variables", {})
    if not isinstance(input_variables_raw, dict):
        raise ValueError(
            f"[invocation].input_variables must be a table, got "
            f"{type(input_variables_raw).__name__}"
        )
    input_variables: dict[str, str] = {}
    for key, value in input_variables_raw.items():
        if not isinstance(value, str):
            raise ValueError(
                f"[invocation].input_variables[{key!r}] must be str, got {type(value).__name__}"
            )
        input_variables[str(key)] = value
    return SampleInvocation(prompt_args=prompt_args, input_variables=input_variables)


def _parse_layer(raw: Any, *, block: str) -> Layer:
    """Parse a ``[gate]`` / ``[rubric]`` / ``[aggregate]`` block into a :class:`Layer`.

    The block is a table with a ``bind`` sub-table (one entry per handle) and an
    optional ``expr`` string. Only the structural shape is enforced (``bind`` is a
    table of tables; ``expr`` is a string when present) — the handle bindings and
    the expression are validated by the compiler.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"[{block}] must be a table, got {type(raw).__name__}")

    bind_raw = raw.get("bind", {})
    if not isinstance(bind_raw, dict):
        raise ValueError(f"[{block}.bind] must be a table, got {type(bind_raw).__name__}")
    bind: dict[str, dict[str, Any]] = {}
    for name, binding in bind_raw.items():
        if not isinstance(binding, dict):
            raise ValueError(f"[{block}.bind.{name}] must be a table, got {type(binding).__name__}")
        bind[str(name)] = binding

    expr_raw = raw.get("expr")
    if expr_raw is not None and not isinstance(expr_raw, str):
        raise ValueError(f"[{block}].expr must be str, got {type(expr_raw).__name__}")

    return Layer(bind=bind, expr=expr_raw)


def _parse_verdict(raw: Any) -> Verdict:
    """Parse the ``[verdict]`` block into a :class:`Verdict` (boolean or weighted).

    Two mutually-exclusive forms:

    * **Boolean** (the legacy/default): ``trial = "<expr>"`` over the layer names
      (default ``"gate and rubric"`` when ``raw`` is empty or only ``trial`` is
      present). ``weights`` / ``fail`` / ``warn`` must be absent.
    * **Weighted** (C10): ``weights = {gate = …, rubric = …}, fail = 0.7``
      (``warn`` optional). ``weights`` must be a non-empty ``{str: number}`` dict
      summing to ``1.0`` (±1e-3); ``fail`` (and ``warn``) must be ``0-1``
      floats; ``trial`` must be absent.

    Authoring both ``trial`` and ``weights`` is a :exc:`ValueError`. Only
    structural shape is enforced here - the compiler validates that ``weights``
    keys name *present* layers.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"[verdict] must be a table, got {type(raw).__name__}")

    has_trial = "trial" in raw
    has_weights = "weights" in raw
    if has_trial and has_weights:
        raise ValueError("[verdict] cannot set both 'trial' and 'weights'")

    if has_weights:
        return _parse_weighted_verdict(raw)
    # Boolean form (default / explicit `trial = …`).
    trial = raw.get("trial", _DEFAULT_VERDICT)
    if not isinstance(trial, str):
        raise ValueError(f"[verdict].trial must be str, got {type(trial).__name__}")
    return Verdict(mode="boolean", trial=trial)


def _parse_weighted_verdict(raw: dict[str, Any]) -> Verdict:
    """Parse the weighted-composite form of ``[verdict]`` into a :class:`Verdict`.

    Enforces: ``weights`` is a non-empty ``{str: number}`` dict, the values sum
    to ``1.0`` within ``_WEIGHT_SUM_TOLERANCE``; ``fail`` is required and is a
    ``0-1`` float; ``warn`` is optional and a ``0-1`` float. Compile-time
    validates that the keys are a subset of the present layers.
    """
    weights_raw = raw["weights"]
    if not isinstance(weights_raw, dict):
        raise ValueError(f"[verdict].weights must be a table, got {type(weights_raw).__name__}")
    if not weights_raw:
        raise ValueError("[verdict].weights must be non-empty")
    weights: dict[str, float] = {}
    for key, value in weights_raw.items():
        if not isinstance(key, str):
            raise ValueError(f"[verdict].weights keys must be str, got {type(key).__name__}")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError(
                f"[verdict].weights[{key!r}] must be a number, got {type(value).__name__}"
            )
        weights[key] = float(value)

    total = sum(weights.values())
    if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
        raise ValueError(
            f"[verdict].weights must sum to 1.0 (got {total!r}; tolerance ±{_WEIGHT_SUM_TOLERANCE})"
        )

    if "fail" not in raw:
        raise ValueError("[verdict] weighted form requires 'fail'")
    fail = _parse_zero_one(raw["fail"], field_name="[verdict].fail")

    warn: float | None = None
    if "warn" in raw:
        warn = _parse_zero_one(raw["warn"], field_name="[verdict].warn")

    return Verdict(mode="weighted", weights=weights, fail=fail, warn=warn)


def _parse_zero_one(value: Any, *, field_name: str) -> float:
    """Coerce ``value`` to a ``0-1`` float (raises :exc:`ValueError` otherwise)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number, got {type(value).__name__}")
    out = float(value)
    if not (0.0 <= out <= 1.0):
        raise ValueError(f"{field_name} must be in [0.0, 1.0], got {out!r}")
    return out


__all__ = [
    "EvalSample",
    "Layer",
    "SampleInvocation",
    "SampleSetup",
    "Verdict",
    "compile_eval_sample",
]
