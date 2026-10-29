"""The setup digest of a release metrics file: everything outside the samples that decides scores (#329 ticket 04).

A release metrics file records ``setup_digest`` with its parts (:class:`SetupParts`),
so a later record can tell whether its setup matches a baseline file's and, when
it does not, name the part that differs (:func:`differing_setup_parts`). The
parts are the target (harness, harness version, model, endpoint fingerprint,
small model), the run settings (runs, judge model, judge endpoint fingerprint,
judge samples, the judge CLI's version, fail-fast), isolation, and
:func:`scoring_digest`. A harness or judge version whose probe failed is
:data:`UNKNOWN_VERSION`, which never matches (:func:`setups_match`).

The scoring digest hashes the engine's scoring code: the modules
:data:`SCORING_MODULES` lists (checks, rubric compiler, scoring, runners, the
grading kernel and, outside those packages, the LLM judge, the sample model and
the release metrics fold) and the LLM judge's grading prompt. Every module under
:data:`SCORING_PACKAGES`, and every top-level ``evals`` module
(:data:`SCORING_TOP_LEVEL`), is either listed or exempted in
:data:`SCORING_EXEMPT` with the reason it decides no score; a test fails on any
other (:func:`unlisted_scoring_modules`), so new scoring code cannot fall
outside the digest silently. Rendering code needs no part: the inputs digest
hashes the rendered text.
"""

from __future__ import annotations

import dataclasses
import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from coding_agent_playbook.evals.judge import GRADING_PROMPT
from coding_agent_playbook.evals.release_metrics_schema import JUDGE_REASONING_EFFORT_PART
from coding_agent_playbook.lockfile.canonical_json import canonical_json

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

#: The engine package's directory, which the module names below are relative to.
_ENGINE_ROOT: Final = Path(__file__).resolve().parents[1]

#: The packages whose every module is listed or exempted, relative to the engine package.
SCORING_PACKAGES: Final = ("evals.checks", "evals.compile", "evals.run", "grading")

#: The packages whose own modules (not their subpackages) are listed or exempted.
SCORING_TOP_LEVEL: Final = ("evals",)

#: The listed modules outside :data:`SCORING_PACKAGES`, so a test can tell them from a typo.
SCORING_MODULES_OUTSIDE_PACKAGES: Final = (
    "evals.api_judge",
    "evals.judge",
    "evals.release_metrics",
    "evals.sample",
)

#: The version part of a CLI whose ``--version`` probe failed. Equality cannot
#: prove that harness or judge unchanged, so this value never matches (ADR 0013:
#: the version is compared strictly); no CLI at all stays ``None``.
UNKNOWN_VERSION: Final = "unknown"

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
    "grading.static_metrics.cognitive",
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
    # Score-deciding modules outside SCORING_PACKAGES: the LLM judge on the CLI and
    # over an OpenAI API (prompt, answer parsing, sample averaging, retries), the sample
    # model (default verdict) and the release metrics fold (each entry's passes, mean
    # score and stdev).
    *SCORING_MODULES_OUTSIDE_PACKAGES,
)

_DOCSTRING_ONLY: Final = "a docstring only: the package is deliberately empty"
_CONFIG: Final = "reads config; the target and judge settings it yields are setup parts"
_AFTER_SCORING: Final = "reads or checks recorded files after their scores are decided"

#: Modules under :data:`SCORING_PACKAGES` or directly in :data:`SCORING_TOP_LEVEL`
#: that decide no score, with the reason.
SCORING_EXEMPT: Final[Mapping[str, str]] = {
    "evals.__init__": _DOCSTRING_ONLY,
    "evals.answers_store": "stores answers; evals.rejudge decides the scores",
    "evals.comparison": "summarizes `eval --compare` runs and flags regressions, never a score",
    "evals.config_shapes": _CONFIG,
    "evals.edition_checks": "offline pin and edition checks, never a run",
    "evals.edition_pins": "writes pins at release time; the sample digest covers the pin line",
    "evals.endpoint_config": _CONFIG,
    "evals.endpoints": "reaches an endpoint; the endpoint fingerprint parts name its server",
    "evals.graded_source": "picks the graded text: the inputs digest hashes its render",
    "evals.loader": "reads sample.toml into evals.sample, which is listed",
    "evals.model_pins": "refuses a moving model before a run; the model parts record it",
    "evals.prompting": "rendering: the inputs digest hashes the rendered text",
    "evals.record_isolation": "refuses a missing credential; the isolated part records isolation",
    "evals.record_checkpoint": "saves finished entries; reuses one only on the same setup digest",
    "evals.registry": "looks runners and judges up; the harness part names the runner",
    "evals.release_carry": "picks the samples that rerun and copies recorded entries as they are",
    "evals.release_metrics_schema": _AFTER_SCORING,
    "evals.release_regression": _AFTER_SCORING,
    "evals.release_regression_format": _AFTER_SCORING,
    "evals.report_format": "renders a report for people, never a recorded score",
    "evals.result_index": "finds committed entries to carry; decides no score",
    "evals.sample_digest": "the sample and inputs digests, recorded per entry",
    "evals.setup_digest": "this module: the digest itself, never a score",
    "evals.target_config": _CONFIG,
    "evals.targets": "names the target; its fields are setup parts",
    "evals.task_registry": "finds and groups samples; the sample digest covers each one",
    "evals.token_usage": "token counts and cost, never a score",
    "evals.validator": "commit-time sample checks, never a run",
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
    ``endpoint_fingerprint`` is the endpoint's URL fingerprint, never the URL,
    and ``judge_endpoint_fingerprint`` the judge endpoint's, ``None`` without a
    judge or when the judge has no endpoint. A version is :data:`UNKNOWN_VERSION`
    when its CLI's probe failed.

    Example::

        >>> parts = SetupParts("fake", None, "m", None, None, 1, None, None, None, None, True, True, "d")
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
    judge_endpoint_fingerprint: str | None
    judge_samples: int | None
    judge_version: str | None
    fail_fast: bool
    isolated: bool | None
    scoring_digest: str
    #: ``[evals.judge] reasoning_effort``; ``None`` leaves the part out, so a setup
    #: without one keeps the digest it had before the part existed.
    judge_reasoning_effort: str | None = None

    def as_dict(self) -> dict[str, object]:
        """The parts by name, in field order, as the metrics file records them."""
        parts = dataclasses.asdict(self)
        if parts[JUDGE_REASONING_EFFORT_PART] is None:
            del parts[JUDGE_REASONING_EFFORT_PART]
        return parts

    @property
    def digest(self) -> str:
        """The sha256 hex digest of every part (the file's ``setup_digest``).

        Equal digests do not prove two setups match, since both may record
        :data:`UNKNOWN_VERSION`: decide a carry with :func:`setups_match`.
        """
        return _sha256(canonical_json(self.as_dict()))


def differing_setup_parts(
    baseline: Mapping[str, object], current: Mapping[str, object]
) -> tuple[str, ...]:
    """The sorted names of the parts whose values differ between two recorded setups.

    A part missing on one side differs, so a baseline recorded without parts
    (``{}``) differs in every part of ``current``. A part recorded as
    :data:`UNKNOWN_VERSION` always differs, since a failed probe proves nothing.

    Example::

        >>> differing_setup_parts({"runs": 3, "isolated": True}, {"runs": 5, "isolated": True})
        ('runs',)
    """
    names = set(baseline) | set(current)
    return tuple(sorted(name for name in names if not _same_part(baseline, current, name)))


def setups_match(baseline: Mapping[str, object], current: Mapping[str, object]) -> bool:
    """Whether no part differs between two recorded setups (:func:`differing_setup_parts`).

    Decide a carry with this, not with ``setup_digest`` equality: two setups
    that both record :data:`UNKNOWN_VERSION` have equal digests yet do not match.

    Example::

        >>> setups_match({"runs": 3}, {"runs": 3}), setups_match({"runs": 3}, {"runs": 5})
        (True, False)
    """
    return not differing_setup_parts(baseline, current)


def _same_part(baseline: Mapping[str, object], current: Mapping[str, object], name: str) -> bool:
    """Both sides record ``name`` with equal, known values (a ``null`` part is not missing)."""
    if name not in baseline or name not in current:
        return False
    return baseline[name] == current[name] and baseline[name] != UNKNOWN_VERSION


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
    top_level: Sequence[str] = SCORING_TOP_LEVEL,
    modules: Sequence[str] = SCORING_MODULES,
    exempt: Mapping[str, str] = SCORING_EXEMPT,
) -> tuple[str, ...]:
    """The sorted modules found that are neither in ``modules`` nor ``exempt``.

    It scans every module under ``packages``, recursively, and the modules
    directly in each ``top_level`` package, not its subpackages. A package's
    ``__init__.py`` is named ``<package>.__init__``.

    Example::

        >>> unlisted_scoring_modules()
        ()
    """
    known = set(modules) | set(exempt)
    found = {
        _module_name(root, path) for package in packages for path in _python_files(root, package)
    }
    found |= {
        _module_name(root, path)
        for package in top_level
        for path in _python_files(root, package, recursive=False)
    }
    return tuple(sorted(found - known))


def _python_files(root: Path, package: str, *, recursive: bool = True) -> list[Path]:
    directory = root / package.replace(".", "/")
    return sorted(directory.rglob("*.py") if recursive else directory.glob("*.py"))


def _module_name(root: Path, path: Path) -> str:
    return ".".join(path.relative_to(root).with_suffix("").parts)


def _source(root: Path, module: str) -> bytes:
    path = root / (module.replace(".", "/") + ".py")
    if not path.is_file():
        raise FileNotFoundError(f"scoring module {module!r} has no file at {path}")
    return path.read_bytes().replace(b"\r\n", b"\n")


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
