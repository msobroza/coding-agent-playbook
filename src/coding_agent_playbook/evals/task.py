"""Eval-task data types (SPEC §15.2). Tier 0 — authoring-side only.

These are the canonical Python representations of ``eval_tasks/<id>/task.toml``.
The loader (:mod:`coding_agent_playbook.evals.loader`) parses the TOML; the
validator (:mod:`coding_agent_playbook.evals.validator`) enforces structural
correctness. The runner that executes tasks against an agent ships in v2;
see SPEC §15.3 for the placeholder ABCs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# Tolerance for the rubric-weights sum check (SPEC §15.2 fifth rule).
_WEIGHT_SUM_TOLERANCE = 1e-3


@dataclass
class TaskSetup:
    """Mock-detector facts + files in the ``setup/`` subdirectory.

    ``files`` lists the entries under ``<task_dir>/setup/`` (relative paths);
    the v2 runner walks ``setup/`` itself and copies into the scratch repo, so
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
class ExpectedOutcome:
    """Programmatic checks the runner (v2) will execute against agent output.

    All sub-lists are ANDed: every entry must hold for the task to pass.
    ``files_must_contain`` entries are ``{"path": <str>, "pattern": <regex>}``.
    """

    files_created: list[str] = field(default_factory=list)
    files_must_contain: list[dict[str, str]] = field(default_factory=list)
    files_unchanged: list[str] = field(default_factory=list)
    files_forbidden: list[str] = field(default_factory=list)


@dataclass
class Rubric:
    """Human-readable criteria for manual or LLM-as-judge (Tier 2) grading.

    ``weights`` is optional: if present it must have the same length as
    ``criteria`` and sum to ``1.0`` (within :data:`_WEIGHT_SUM_TOLERANCE`).
    If absent the runner treats weighting as uniform.
    """

    criteria: list[str] = field(default_factory=list)
    weights: list[float] | None = None


@dataclass
class EvalTask:
    """A single eval task. Mirrors the on-disk ``eval_tasks/<id>/task.toml``.

    ``source_path`` is the ``task.toml`` path (the parent directory holds
    ``setup/`` etc.). ``source_package`` is the importable package name
    (``"coding_agent_playbook"``, an overlay package, or ``"<repo-local>"``)
    so ``playbook eval --show`` and overlay collision reports can attribute the
    task back to its layer.
    """

    id: str
    prompt_id: str
    description: str
    source_path: Path
    source_package: str
    version: int = 1
    setup: TaskSetup = field(default_factory=TaskSetup)
    invocation: TaskInvocation = field(default_factory=TaskInvocation)
    expected: ExpectedOutcome | None = None
    rubric: Rubric | None = None

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
        Optional sections: ``[setup]``, ``[invocation]``, ``[expected]``, ``[rubric]``.

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
        expected = _parse_expected(data["expected"]) if "expected" in data else None
        rubric = _parse_rubric(data["rubric"]) if "rubric" in data else None

        return cls(
            id=task_id,
            prompt_id=prompt_id,
            description=description,
            source_path=source_path,
            source_package=source_package,
            version=version,
            setup=setup,
            invocation=invocation,
            expected=expected,
            rubric=rubric,
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


def _parse_expected(raw: Any) -> ExpectedOutcome:
    if not isinstance(raw, dict):
        raise ValueError(f"[expected] must be a table, got {type(raw).__name__}")
    files_must_contain_raw = raw.get("files_must_contain", [])
    if not isinstance(files_must_contain_raw, list):
        raise ValueError(
            f"[expected].files_must_contain must be a list, got "
            f"{type(files_must_contain_raw).__name__}"
        )
    files_must_contain: list[dict[str, str]] = []
    for index, entry in enumerate(files_must_contain_raw):
        if not isinstance(entry, dict):
            raise ValueError(
                f"[expected].files_must_contain[{index}] must be a table, "
                f"got {type(entry).__name__}"
            )
        if "path" not in entry or "pattern" not in entry:
            raise ValueError(
                f"[expected].files_must_contain[{index}] must have 'path' and 'pattern'"
            )
        path = entry["path"]
        pattern = entry["pattern"]
        if not isinstance(path, str) or not isinstance(pattern, str):
            raise ValueError(
                f"[expected].files_must_contain[{index}] 'path' and 'pattern' must be strings"
            )
        files_must_contain.append({"path": path, "pattern": pattern})
    return ExpectedOutcome(
        files_created=list(raw.get("files_created", [])),
        files_must_contain=files_must_contain,
        files_unchanged=list(raw.get("files_unchanged", [])),
        files_forbidden=list(raw.get("files_forbidden", [])),
    )


def _parse_rubric(raw: Any) -> Rubric:
    if not isinstance(raw, dict):
        raise ValueError(f"[rubric] must be a table, got {type(raw).__name__}")
    criteria_raw = raw.get("criteria", [])
    if not isinstance(criteria_raw, list) or not all(isinstance(c, str) for c in criteria_raw):
        raise ValueError("[rubric].criteria must be a list of strings")
    criteria: list[str] = list(criteria_raw)
    weights_raw = raw.get("weights")
    weights: list[float] | None
    if weights_raw is None:
        weights = None
    else:
        if not isinstance(weights_raw, list) or not all(
            isinstance(w, (int, float)) and not isinstance(w, bool) for w in weights_raw
        ):
            raise ValueError("[rubric].weights must be a list of numbers")
        if len(weights_raw) != len(criteria):
            raise ValueError(
                f"[rubric].weights length {len(weights_raw)} does not match "
                f"criteria length {len(criteria)}"
            )
        total = float(sum(weights_raw))
        if abs(total - 1.0) > _WEIGHT_SUM_TOLERANCE:
            raise ValueError(
                f"[rubric].weights must sum to 1.0 (±{_WEIGHT_SUM_TOLERANCE}), got {total}"
            )
        weights = [float(w) for w in weights_raw]
    return Rubric(criteria=criteria, weights=weights)
