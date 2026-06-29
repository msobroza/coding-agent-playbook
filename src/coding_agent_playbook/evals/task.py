"""Eval-task data types (SPEC §15.2) — the C7 ``[gate]``/``[rubric]``/``[verdict]`` schema.

These are the canonical Python representations of ``eval_tasks/<id>/task.toml``.
The loader (:mod:`coding_agent_playbook.evals.loader`) parses the TOML; the
validator (:mod:`coding_agent_playbook.evals.validator`) enforces structural
correctness by trial-compiling the blocks; the runner
(:mod:`coding_agent_playbook.evals.runner`) materializes + scores the task.

**C7 cutover.** The old fused ``[expected]``/``[metrics]``/``[rubric]`` blocks (each
a typed dataclass) are gone. A task now declares its evaluation as up to four raw
blocks the C6 compiler turns into a per-trial structure:

* ``[gate]`` — ``{"bind": <handle table>, "expr": <bool expr | None>}``. The
  deterministic layer (file predicates, metric thresholds, composed gates). Every
  handle is a boolean :class:`~coding_agent_playbook.evaluators.check.Check`.
* ``[rubric]`` — same shape; the judged layer (a ``rubric`` group of weighted
  ``JudgeCheck``\\ s, thresholded to a boolean).
* ``[verdict].trial`` — a boolean expression over ``gate``/``rubric`` (default
  ``"gate and rubric"``) deriving the per-trial verdict from the two layers.
* ``[aggregate]`` — ``{"bind": <table>, "expr": <str | None>}``. Parsed but **not
  executed** in C7 (single-trial); the C8 multi-trial layer consumes it.

``run_tests``/``strict`` are no longer authored — they are *inferred*: a task runs
tests iff it references an execution metric, and ``strict`` defaults ``False``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from coding_agent_playbook.evals._compile import CompiledTask


@dataclass
class TaskSetup:
    """Mock-detector facts + files in the ``setup/`` subdirectory.

    ``files`` lists the entries under ``<task_dir>/setup/`` (relative paths);
    the runner walks ``setup/`` itself and copies into the scratch repo, so
    this list is documentation that the validator can cross-check.
    """

    files: list[Path] = field(default_factory=list)
    project_kind: str = "python-unknown"
    python_version: str = "3.12"
    frameworks: list[str] = field(default_factory=list)
    extra_facts: dict[str, Any] = field(default_factory=dict)


@dataclass
class TaskInvocation:
    """What the user "types" after the slash command at task runtime."""

    prompt_args: str = ""
    input_variables: dict[str, str] = field(default_factory=dict)


@dataclass
class Layer:
    """One ``[gate]`` / ``[rubric]`` / ``[aggregate]`` block: a bind table + an expr.

    ``bind`` is the raw ``[<layer>.bind]`` handle table (one entry per handle, the
    value a binding the C5 :func:`~coding_agent_playbook.evals._handles.build_handles`
    factory turns into a :class:`~coding_agent_playbook.evaluators.check.Check`).
    ``expr`` is the optional boolean/aggregate expression over those handle names
    (``None`` defaults to the sole handle's name for a single-handle layer).
    """

    bind: dict[str, dict[str, Any]] = field(default_factory=dict)
    expr: str | None = None


#: The default ``[verdict].trial`` expression: both layers must pass.
_DEFAULT_VERDICT = "gate and rubric"


@dataclass
class EvalTask:
    """A single eval task. Mirrors the on-disk ``eval_tasks/<id>/task.toml``.

    ``source_path`` is the ``task.toml`` path (the parent directory holds
    ``setup/`` etc.). ``source_package`` is the importable package name
    (``"coding_agent_playbook"``, an overlay package, or ``"<repo-local>"``)
    so ``playbook eval --show`` and overlay collision reports can attribute the
    task back to its layer.

    ``gate``/``rubric``/``aggregate`` are the parsed :class:`Layer` blocks (``None``
    when absent); ``verdict`` is the ``[verdict].trial`` expression. A task must
    carry at least one of ``[gate]`` / ``[rubric]`` (enforced at compile time).
    """

    id: str
    prompt_id: str
    description: str
    source_path: Path
    source_package: str
    version: int = 1
    setup: TaskSetup = field(default_factory=TaskSetup)
    invocation: TaskInvocation = field(default_factory=TaskInvocation)
    gate: Layer | None = None
    rubric: Layer | None = None
    verdict: str = _DEFAULT_VERDICT
    aggregate: Layer | None = None

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        source_path: Path,
        source_package: str,
    ) -> EvalTask:
        """Parse a TOML-shaped dict (from ``tomllib.load``) into an EvalTask.

        Required top-level fields: ``id``, ``prompt_id``, ``description``.
        Optional top-level: ``version``.
        Optional sections: ``[setup]``, ``[invocation]``, ``[gate]``, ``[rubric]``,
        ``[verdict]``, ``[aggregate]``.

        Only the *structural* shape is enforced here (each block is a table; the
        bind/expr split is well-formed). Semantic correctness — unknown check ids,
        malformed handle bindings, expression identifiers ⊄ bind keys, rubric
        weight-sum, verdict idents ⊄ present layers — is the compiler's job and is
        surfaced by the validator via :func:`compile_eval_task`.

        Raises :exc:`ValueError` with a descriptive message on missing or
        malformed required fields. The loader catches these and wraps them
        with the task.toml path for jump-to-file ergonomics.
        """
        task_id = _require_str(data, "id")
        prompt_id = _require_str(data, "prompt_id")
        description = _require_str(data, "description")
        version = data.get("version", 1)
        if not isinstance(version, int) or isinstance(version, bool):
            raise ValueError(f"field 'version' must be int, got {type(version).__name__}")

        setup = _parse_setup(data.get("setup", {}))
        invocation = _parse_invocation(data.get("invocation", {}))
        gate = _parse_layer(data["gate"], block="gate") if "gate" in data else None
        rubric = _parse_layer(data["rubric"], block="rubric") if "rubric" in data else None
        aggregate = (
            _parse_layer(data["aggregate"], block="aggregate") if "aggregate" in data else None
        )
        verdict = _parse_verdict(data.get("verdict", {}))

        return cls(
            id=task_id,
            prompt_id=prompt_id,
            description=description,
            source_path=source_path,
            source_package=source_package,
            version=version,
            setup=setup,
            invocation=invocation,
            gate=gate,
            rubric=rubric,
            verdict=verdict,
            aggregate=aggregate,
        )

    def compiled(self) -> CompiledTask:
        """Compile this task's blocks into a :class:`CompiledTask` (single-trial).

        A thin wrapper over :func:`compile_eval_task`.
        """
        return compile_eval_task(self)


def compile_eval_task(task: EvalTask) -> CompiledTask:
    """Compile ``task``'s ``[gate]``/``[rubric]``/``[verdict]`` into a :class:`CompiledTask`.

    Delegates to :func:`coding_agent_playbook.evals._compile.compile_task` with the
    task's gate/rubric bind tables + exprs and the verdict trial expression. The
    returned :class:`~coding_agent_playbook.evals._compile.CompiledTask` carries the
    per-trial :class:`~coding_agent_playbook.evaluators.rubric.Rubric` (the gate +
    rubric layer checks) and the parsed verdict AST.

    Raises :exc:`ValueError` (incl. :exc:`~coding_agent_playbook.evals._expr.ExprError`)
    /:exc:`KeyError` on any structural fault the compiler catches: no layer present,
    unknown check id/metric/gate-ref/rubric-ref, malformed binding, an expression
    identifier ⊄ its bind keys, a rubric weight-sum ≠ 1.0, or a verdict identifier
    naming an absent layer. The validator turns these into validation errors.

    The compiler is imported lazily so the ``task`` module stays import-light; the
    ``_compile`` module imports only from ``evaluators`` (never back from ``task``),
    so this is acyclic regardless.
    """
    from coding_agent_playbook.evals._compile import compile_task

    return compile_task(
        gate_bind=task.gate.bind if task.gate is not None else None,
        gate_expr=task.gate.expr if task.gate is not None else None,
        rubric_bind=task.rubric.bind if task.rubric is not None else None,
        rubric_expr=task.rubric.expr if task.rubric is not None else None,
        verdict_trial=task.verdict,
        name=task.id,
    )


def _require_str(data: dict[str, Any], key: str) -> str:
    if key not in data:
        raise ValueError(f"missing required field: {key!r}")
    value = data[key]
    if not isinstance(value, str):
        raise ValueError(f"field {key!r} must be str, got {type(value).__name__}")
    return value


def _parse_setup(raw: Any) -> TaskSetup:
    if not isinstance(raw, dict):
        raise ValueError(f"[setup] must be a table, got {type(raw).__name__}")
    files = [Path(p) for p in raw.get("files", [])]
    project_kind = raw.get("project_kind", "python-unknown")
    python_version = raw.get("python_version", "3.12")
    frameworks = list(raw.get("frameworks", []))
    # Anything outside the typed slots is preserved in extra_facts so overlays
    # can mock new detector keys without changing this dataclass.
    known = {"files", "project_kind", "python_version", "frameworks"}
    extra_facts = {k: v for k, v in raw.items() if k not in known}
    if not isinstance(project_kind, str):
        raise ValueError(f"[setup].project_kind must be str, got {type(project_kind).__name__}")
    if not isinstance(python_version, str):
        raise ValueError(f"[setup].python_version must be str, got {type(python_version).__name__}")
    return TaskSetup(
        files=files,
        project_kind=project_kind,
        python_version=python_version,
        frameworks=frameworks,
        extra_facts=extra_facts,
    )


def _parse_invocation(raw: Any) -> TaskInvocation:
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
    return TaskInvocation(prompt_args=prompt_args, input_variables=input_variables)


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


def _parse_verdict(raw: Any) -> str:
    """Parse the ``[verdict]`` block into the trial expression string.

    ``[verdict].trial`` defaults to ``"gate and rubric"`` when the block (or its
    ``trial`` key) is absent. Only the type is enforced here; the compiler checks
    that the expression's identifiers name present layers.
    """
    if not isinstance(raw, dict):
        raise ValueError(f"[verdict] must be a table, got {type(raw).__name__}")
    trial = raw.get("trial", _DEFAULT_VERDICT)
    if not isinstance(trial, str):
        raise ValueError(f"[verdict].trial must be str, got {type(trial).__name__}")
    return trial


__all__ = [
    "EvalTask",
    "Layer",
    "TaskInvocation",
    "TaskSetup",
    "compile_eval_task",
]
