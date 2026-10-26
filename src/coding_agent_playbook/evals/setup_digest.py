"""The setup digest of a release metrics file: everything outside the samples that decides scores (#329 ticket 04).

A release metrics file records ``setup_digest`` with its parts (:class:`SetupParts`),
so a later record can tell whether its setup matches a baseline file's and, when
it does not, name the part that differs (:func:`differing_setup_parts`). The
parts are the target (harness, harness version, model, endpoint fingerprint,
small model), the run settings (runs, judge model, judge samples, the judge
CLI's version, fail-fast), isolation, and :func:`scoring_digest`.

The scoring digest hashes the engine's scoring code: the modules
:data:`SCORING_MODULES` lists (checks, rubric compiler, scoring, runners and the
grading kernel) and the LLM judge's grading prompt. Every module under
:data:`SCORING_PACKAGES` is either listed or exempted in :data:`SCORING_EXEMPT`
with the reason it decides no score; a test fails on any other
(:func:`unlisted_scoring_modules`), so new scoring code cannot fall outside the
digest silently. Rendering code needs no part: the inputs digest hashes the
rendered text.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.judge import GRADING_PROMPT
from coding_agent_playbook.lockfile.canonical_json import canonical_json

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: The engine package's directory, which the module names below are relative to.
_ENGINE_ROOT: Final = Path(__file__).resolve().parents[1]

#: The packages whose every module is listed or exempted, relative to the engine package.
SCORING_PACKAGES: Final = ("evals.checks", "evals.compile", "evals.run", "grading")

#: The modules whose source decides a score, relative to the engine package.
SCORING_MODULES: Final = (
    # Eval-only checks and the rubric compiler.
    "evals.checks.aggregate",
    "evals.checks.answer",
    "evals.checks.files",
    "evals.compile._expr",
    "evals.compile._handles",
    "evals.compile.compiler",
    "evals.compile.gate_registry",
    "evals.compile.rubric_registry",
    # Scoring and the runners: how the agent runs, what it is given and how its output is read.
    "evals.run.agent_env",
    "evals.run.claude_code_output",
    "evals.run.claude_code_route",
    "evals.run.claude_code_runner",
    "evals.run.cli_argv",
    "evals.run.fake_runner",
    "evals.run.git_env",
    "evals.run.harness_runner",
    "evals.run.opencode_output",
    "evals.run.opencode_route",
    "evals.run.opencode_runner",
    "evals.run.scoring",
    "evals.run.secret_redaction",
    # The grading kernel and its metrics.
    "grading.baseline_git",
    "grading.check",
    "grading.check_registry",
    "grading.compose",
    "grading.execution_checks",
    "grading.execution_metrics.coverage",
    "grading.execution_metrics.coverage_xml",
    "grading.execution_metrics.diff_coverage",
    "grading.execution_metrics.git_diff",
    "grading.execution_metrics.junit",
    "grading.execution_metrics.project",
    "grading.execution_metrics.test_pass",
    "grading.judge_metric",
    "grading.judged",
    "grading.measuring",
    "grading.metric",
    "grading.normalizer",
    "grading.parse",
    "grading.paths",
    "grading.rubric",
    "grading.scheduler",
    "grading.scope",
    "grading.static_metrics.cbo",
    "grading.static_metrics.cyclomatic",
    "grading.static_metrics.dit",
    "grading.static_metrics.docstring_example",
    "grading.static_metrics.file_sloc",
    "grading.static_metrics.lcom4",
    "grading.static_metrics.maintainability",
    "grading.static_metrics.ruff_violations",
    "grading.static_metrics.wmc",
    "grading.tool_runner",
    "grading.types",
)

_DOCSTRING_ONLY: Final = "a docstring only: the package is deliberately empty"

#: Modules under :data:`SCORING_PACKAGES` that decide no score, with the reason.
SCORING_EXEMPT: Final[Mapping[str, str]] = {
    "evals.checks.__init__": _DOCSTRING_ONLY,
    "evals.compile.__init__": _DOCSTRING_ONLY,
    "evals.run.__init__": _DOCSTRING_ONLY,
    "evals.run.comparison_runner": "runs `eval --compare`, never a record",
    "evals.run.comparison_sides": "prepares the sides of `eval --compare`, never a record",
    "evals.run.harness_version": "its probe's result is the harness_version part itself",
    "grading.__init__": _DOCSTRING_ONLY,
    "grading.execution_metrics.__init__": _DOCSTRING_ONLY,
    "grading.static_metrics.__init__": _DOCSTRING_ONLY,
}


@dataclass(frozen=True)
class SetupParts:
    """The named parts of a record's setup; :attr:`digest` hashes them all.

    ``judge_samples`` and ``judge_version`` are ``None`` without a judge;
    ``endpoint_fingerprint`` is the endpoint's URL fingerprint, never the URL.

    Example::

        >>> parts = SetupParts("fake", None, "m", None, None, 1, None, None, None, True, True, "d")
        >>> parts.as_dict()["runs"]
        1
    """

    harness: str
    harness_version: str | None
    model: str | None
    endpoint_fingerprint: str | None
    small_model: str | None
    runs: int
    judge_model: str | None
    judge_samples: int | None
    judge_version: str | None
    fail_fast: bool
    isolated: bool | None
    scoring_digest: str

    def as_dict(self) -> dict[str, object]:
        """The parts by name, in field order, as the metrics file records them."""
        return dataclasses.asdict(self)

    @property
    def digest(self) -> str:
        """The sha256 hex digest of every part (the file's ``setup_digest``)."""
        return _sha256(canonical_json(self.as_dict()))


def differing_setup_parts(
    baseline: Mapping[str, object], current: Mapping[str, object]
) -> tuple[str, ...]:
    """The sorted names of the parts whose values differ between two recorded setups.

    A part missing on one side differs, so a baseline recorded without parts
    (``{}``) differs in every part of ``current``.

    Example::

        >>> differing_setup_parts({"runs": 3, "isolated": True}, {"runs": 5, "isolated": True})
        ('runs',)
    """
    names = set(baseline) | set(current)
    return tuple(sorted(name for name in names if not _same_part(baseline, current, name)))


def _same_part(baseline: Mapping[str, object], current: Mapping[str, object], name: str) -> bool:
    """Both sides record ``name`` with equal values (a part recorded as ``null`` is not missing)."""
    return name in baseline and name in current and baseline[name] == current[name]


def scoring_digest(
    root: Path = _ENGINE_ROOT,
    *,
    modules: Sequence[str] = SCORING_MODULES,
    judge_prompt: str = GRADING_PROMPT,
) -> str:
    """The sha256 hex digest of the scoring ``modules``' source under ``root`` and ``judge_prompt``.

    Line endings are normalized, so a checkout's newline style never moves it.
    A listed module without a file raises ``FileNotFoundError`` naming it.

    Example::

        >>> len(scoring_digest())
        64
    """
    sources = {module: _sha256(_source(root, module)) for module in modules}
    payload = {"modules": sources, "judge_prompt": _sha256(judge_prompt.encode("utf-8"))}
    return _sha256(canonical_json(payload))


def unlisted_scoring_modules(
    root: Path = _ENGINE_ROOT,
    *,
    packages: Sequence[str] = SCORING_PACKAGES,
    modules: Sequence[str] = SCORING_MODULES,
    exempt: Mapping[str, str] = SCORING_EXEMPT,
) -> tuple[str, ...]:
    """The sorted modules under ``packages`` that are neither in ``modules`` nor ``exempt``.

    A package's ``__init__.py`` is named ``<package>.__init__``.

    Example::

        >>> unlisted_scoring_modules()
        ()
    """
    known = set(modules) | set(exempt)
    found = {
        _module_name(root, path) for package in packages for path in _python_files(root, package)
    }
    return tuple(sorted(found - known))


def _python_files(root: Path, package: str) -> list[Path]:
    return sorted((root / package.replace(".", "/")).rglob("*.py"))


def _module_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _source(root: Path, module: str) -> bytes:
    path = root / (module.replace(".", "/") + ".py")
    if not path.is_file():
        raise FileNotFoundError(f"scoring module {module!r} has no file at {path}")
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
