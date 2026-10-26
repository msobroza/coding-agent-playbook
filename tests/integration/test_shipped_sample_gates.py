"""Gate proofs: every shipped eval sample's ``[gate]`` discriminates (CI).

A deterministic gate is only worth shipping if it *fails* on the untouched
fixture and on known-wrong answers, and *passes* on a correct answer; a gate
that passes on ``setup/`` proves nothing, and one that rejects a correct answer
sinks every real run. Each sample therefore ships a ``solution/`` next to ``setup/``:

* an **edit** sample mirrors ``setup/`` paths with the files a correct agent would
  create or change; they are overlaid onto the materialized scratch repo;
* a **review-only** sample carries ``solution/transcript.md`` holding a correct
  answer (its gate grades the answer via ``answer_matches``);
* ``solution/negatives/`` holds known-wrong attempts, never part of the reference
  overlay: ``<case>.md`` is a wrong review answer graded on the pristine tree, and
  ``<case>/`` is a wrong edit overlay (``setup/`` paths, plus an optional
  ``<case>/transcript.md`` answer).

For every shipped sample with a ``solution/`` this module asserts, deterministic-only
(no judge, ``fail_fast=True`` like the runner), that the gate is ``False`` on the
pristine materialization with an empty answer, ``False`` for every negative, and
``True`` with the reference solution applied. An empty answer fails any answer
pattern, so only negatives prove a review gate tells a correct answer from a
wrong one: every review-only sample must ship at least one. Samples that predate the
convention are frozen in :data:`LEGACY_SAMPLES_WITHOUT_SOLUTION`: the list may only
shrink.

Per-leaf discrimination is deliberately not asserted: guard leaves
(``file_unchanged``, ``file_forbidden``) legitimately hold on both sides, so an
"every leaf flips" rule would need per-sample exemptions. A negative that misses
exactly one requirement is the lower-maintenance proof that the leaf still bites.

The harness is also proven on synthetic samples under ``tmp_path``, so it stays
tested whatever the shipped content is. ``materialize`` copies only ``setup/``
and the loader/validator read only ``sample.toml`` + ``setup/``, so ``solution/``
never leaks into a run; the last tests pin that.
"""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.catalog.layers import ENGINE_PACKAGE
from coding_agent_playbook.evals.run.harness_runner import capture, materialize
from coding_agent_playbook.evals.run.scoring import score
from coding_agent_playbook.evals.task_registry import (
    TaskRegistry,
    load_layer_samples,
    load_task_sample,
)
from coding_agent_playbook.evals.validator import validate_samples
from coding_agent_playbook.grading.types import CheckResult
from tests._catalog import CORE_ROOT, bundled_eval_sample_roots

if TYPE_CHECKING:
    from collections.abc import Callable

    from coding_agent_playbook.evals.sample import EvalSample

pytestmark = pytest.mark.catalog

_SAMPLES_ROOT = CORE_ROOT / "eval_samples"
_SOLUTION_DIR = "solution"
#: ``solution/negatives/`` holds known-wrong attempts; the reference overlay skips it.
_NEGATIVES_DIR = "negatives"
#: A negative given as a single file is a wrong review answer, ``<case>.md``.
_ANSWER_SUFFIX = ".md"
#: Only the *top-level* ``transcript.md`` of an answer tree is the answer; a nested
#: file of that name is ordinary fixture content and is overlaid like any other.
_TRANSCRIPT = Path("transcript.md")

#: Shipped before the solution/ convention (frozen 2026-10-14). Never add to it.
LEGACY_SAMPLES_WITHOUT_SOLUTION = frozenset(
    {
        "explain/pure-function",
        "find-injected-vulnerability/aiplatform-xss",
        "find-injected-vulnerability/authlib-sigbypass",
        "find-injected-vulnerability/changedetection-pathtraversal",
        "find-injected-vulnerability/changedetection-ssrf",
        "find-injected-vulnerability/graphiti-queryinj",
        "find-injected-vulnerability/langroid-codeinj",
        "find-injected-vulnerability/modoboa-cmdi",
        "find-injected-vulnerability/ormar-sqli",
        "find-injected-vulnerability/pydash-massassign",
        "find-injected-vulnerability/pytorch-deserial",
        "generate-tests/async-code",
        "generate-tests/edge-cases",
        "generate-tests/happy-path",
        "refactor/extract-helper",
        "refactor/rename-for-clarity",
        "review/spot-the-bug",
        "review/style-only-no-changes-needed",
        "security-review/already-safe",
        "security-review/pickle-load",
    }
)


@pytest.fixture
def stub_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hermetic ``uv sync``: ``materialize`` syncs any ``setup/pyproject.toml``.

    CI must stay air-gapped (and may lack ``uv`` on PATH inside pytest), so ``uv``
    invocations short-circuit to success; git calls pass through unchanged. Same
    stub as ``test_shipped_eval_samples_c7.py``.
    """
    real_run = subprocess.run

    def _fake_uv_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.subprocess.run", _fake_uv_run
    )
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.shutil.which", lambda _binary: "/fake/uv"
    )


# --------------------------------------------------------------------------- #
# The proof harness
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Attempt:
    """A simulated agent outcome: a tree overlaid onto ``setup/`` (if any) and its answer.

    Example: ``Attempt.from_tree(sample_dir / "solution")``; ``NO_OP`` edits nothing
    and answers ``""``.
    """

    overlay: Path | None = None
    transcript: str = ""

    @classmethod
    def from_tree(cls, tree: Path) -> Attempt:
        """Overlay ``tree``; its top-level ``transcript.md`` (if any) is the answer."""
        return cls(tree, solution_transcript(tree))


NO_OP = Attempt()


def overlay_files(tree: Path) -> list[Path]:
    """The relative paths :func:`overlay_solution` copies out of ``tree``.

    Everything except the top-level ``transcript.md`` (the answer, not a tree edit)
    and the top-level ``negatives/`` (known-wrong attempts, graded on their own).
    Example: ``overlay_files(sample_dir / "solution") == [Path("tests/test_x.py")]``.
    """
    rels = (p.relative_to(tree) for p in tree.rglob("*") if p.is_file())
    return sorted(r for r in rels if r != _TRANSCRIPT and r.parts[0] != _NEGATIVES_DIR)


def overlay_solution(tree: Path, scratch: Path) -> None:
    """Copy every :func:`overlay_files` entry of ``tree`` onto ``scratch``.

    Example: ``overlay_solution(sample_dir / "solution", baseline.repo_root)``.
    """
    for rel in overlay_files(tree):
        (scratch / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(tree / rel, scratch / rel)


def solution_transcript(tree: Path) -> str:
    """The answer in ``tree/transcript.md``, or ``""`` when the tree carries none."""
    path = tree / _TRANSCRIPT
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def is_review_only(solution_dir: Path) -> bool:
    """True when the reference solution is an answer alone, with no tree edits."""
    return (solution_dir / _TRANSCRIPT).is_file() and not overlay_files(solution_dir)


def negative_paths(solution_dir: Path) -> list[Path]:
    """Every entry of ``solution_dir/negatives/`` (dotfiles aside), sorted."""
    root = solution_dir / _NEGATIVES_DIR
    if not root.is_dir():
        return []
    return sorted(p for p in root.iterdir() if not p.name.startswith("."))


def negative_attempt(path: Path) -> Attempt:
    """Read one ``solution/negatives/`` entry as the wrong attempt it encodes.

    Example: ``negative_attempt(neg_dir / "no-cycle.md").transcript``.
    """
    if path.is_dir():
        return Attempt.from_tree(path)
    if path.suffix == _ANSWER_SUFFIX:
        return Attempt(transcript=path.read_text(encoding="utf-8"))
    raise ValueError(
        f"unexpected negative {path}: expected <case>{_ANSWER_SUFFIX} (a wrong review "
        "answer) or a <case>/ directory (a wrong edit overlay mirroring setup/ paths)"
    )


def gate_result(sample: EvalSample, workdir: Path, attempt: Attempt = NO_OP) -> CheckResult:
    """Materialize ``sample`` under ``workdir``, apply ``attempt``, grade the gate.

    Deterministic-only (no judge) with the runner's ``fail_fast=True``.
    Example: ``gate_result(sample, tmp_path, Attempt.from_tree(solution_dir)).passed``.
    """
    baseline = materialize(sample, workdir / "scratch")
    if attempt.overlay is not None:
        overlay_solution(attempt.overlay, baseline.repo_root)
    candidate = capture(baseline.repo_root, baseline, attempt.transcript)
    report = score(sample, baseline, candidate, judge=None, fail_fast=True)
    return next(c for c in report.checks if c.check_id == "gate")


def describe(result: CheckResult) -> str:
    """One line per gate leaf (``id: passed/status``), for failure messages."""
    leaves = [s for s in result.subresults if isinstance(s, CheckResult)]
    if not leaves:
        return f"{result.check_id}: passed={result.passed} status={result.status} {result.detail}"
    return "\n".join(describe(leaf) for leaf in leaves)


# --------------------------------------------------------------------------- #
# Shipped samples
# --------------------------------------------------------------------------- #


def _shipped_sample_dirs() -> list[Path]:
    """Core's eval samples, then every bundled plugin's (eval samples are per layer)."""
    return [
        sample.source_path.parent
        for root in bundled_eval_sample_roots()
        for sample in load_layer_samples(root, _layer_package(root))
    ]


def _layer_package(samples_root: Path) -> str:
    """Core's samples load as the engine's, as the artifact source loads them.

    Only the engine's samples may pin an edition (``evals.sample``), so loading
    core as ``"core"`` would refuse the first pinned sample (#281 ticket 13).
    """
    return ENGINE_PACKAGE if samples_root == _SAMPLES_ROOT else samples_root.parent.name


def _sample_id(sample_dir: Path) -> str:
    """The id of the sample at ``.../eval_samples/<task>/<name>``: ``<task>/<name>``."""
    return f"{sample_dir.parent.name}/{sample_dir.name}"


# Fail collection loudly: an empty or mis-pointed root would turn every gate proof
# below into a silent "empty parameter set" skip.
assert _shipped_sample_dirs(), f"no shipped eval samples found under {_SAMPLES_ROOT}"


def _solved_sample_dirs() -> list[Path]:
    return [d for d in _shipped_sample_dirs() if (d / _SOLUTION_DIR).is_dir()]


def _shipped_negatives() -> list[tuple[Path, Path]]:
    return [(d, neg) for d in _solved_sample_dirs() for neg in negative_paths(d / _SOLUTION_DIR)]


def _load(sample_dir: Path, package: str = ENGINE_PACKAGE) -> EvalSample:
    return load_task_sample(sample_dir, source_package=package)


def test_core_samples_are_collected_as_the_engines_so_a_pinned_one_loads() -> None:
    assert _layer_package(_SAMPLES_ROOT) == ENGINE_PACKAGE


@pytest.mark.parametrize("sample_dir", _solved_sample_dirs(), ids=_sample_id)
def test_shipped_gate_fails_on_pristine_setup(
    sample_dir: Path, tmp_path: Path, stub_uv_sync: None
) -> None:
    gate = gate_result(_load(sample_dir), tmp_path)
    assert gate.passed is False, (
        f"{sample_dir.name}: the gate passes on the untouched setup/ with an empty answer, "
        f"so it cannot tell a correct agent from a no-op:\n{describe(gate)}"
    )


@pytest.mark.parametrize("sample_dir", _solved_sample_dirs(), ids=_sample_id)
def test_shipped_gate_passes_with_reference_solution(
    sample_dir: Path, tmp_path: Path, stub_uv_sync: None
) -> None:
    gate = gate_result(_load(sample_dir), tmp_path, Attempt.from_tree(sample_dir / _SOLUTION_DIR))
    assert gate.status == "run" and gate.passed is True, (
        f"{sample_dir.name}: the gate rejects the reference solution/ "
        f"(fix the gate or the solution):\n{describe(gate)}"
    )


@pytest.mark.parametrize(("sample_dir", "negative"), _shipped_negatives(), ids=lambda p: p.name)
def test_shipped_gate_rejects_every_negative(
    sample_dir: Path, negative: Path, tmp_path: Path, stub_uv_sync: None
) -> None:
    gate = gate_result(_load(sample_dir), tmp_path, negative_attempt(negative))
    assert gate.passed is False, (
        f"{sample_dir.name}: the gate accepts the known-wrong {negative.name}, so a leaf "
        f"is vacuous or too lenient:\n{describe(gate)}"
    )


def test_every_new_sample_ships_a_solution() -> None:
    missing = sorted(
        _sample_id(d)
        for d in _shipped_sample_dirs()
        if _sample_id(d) not in LEGACY_SAMPLES_WITHOUT_SOLUTION and not (d / _SOLUTION_DIR).is_dir()
    )
    assert missing == [], (
        f"eval samples without a solution/ gate proof: {missing}. Add solution/ (edited files "
        "mirroring setup/ paths, or solution/transcript.md for a review-only sample)."
    )


def test_every_review_only_sample_ships_a_negative() -> None:
    missing = sorted(
        _sample_id(d)
        for d in _solved_sample_dirs()
        if is_review_only(d / _SOLUTION_DIR) and not negative_paths(d / _SOLUTION_DIR)
    )
    assert missing == [], (
        f"review-only samples without solution/negatives/: {missing}. An empty answer fails "
        "any answer pattern, so only a well-formed wrong answer "
        "(solution/negatives/<case>.md) proves the gate rejects a wrong review."
    )


def test_legacy_list_has_no_stale_entries() -> None:
    shipped = {_sample_id(d): d for d in _shipped_sample_dirs()}
    gone = sorted(LEGACY_SAMPLES_WITHOUT_SOLUTION - shipped.keys())
    solved = sorted(
        t
        for t in LEGACY_SAMPLES_WITHOUT_SOLUTION & shipped.keys()
        if (shipped[t] / _SOLUTION_DIR).is_dir()
    )
    assert gone == [], f"LEGACY_SAMPLES_WITHOUT_SOLUTION names removed samples: {gone}"
    assert solved == [], (
        f"these legacy samples now ship solution/; drop them from the list: {solved}"
    )


# --------------------------------------------------------------------------- #
# The harness on synthetic samples (independent of shipped content)
# --------------------------------------------------------------------------- #

_RUBRIC_AND_VERDICT = """
[rubric]
expr = "quality"

[rubric.bind]
quality = { fail = 0.5, rubric = [ { judge = "The change is correct.", weight = 1.0 } ] }

[verdict]
trial = "gate and rubric"
"""

_EDIT_TOML = (
    r"""
id = "synthetic-prompt/synthetic-edit"
description = "Add a loud greeting and a test for it."

[setup]
files = ["app/greet.py"]
project_kind = "python-application"

[gate]
expr = "defines_loud and has_test"

[gate.bind]
defines_loud = { check = "file_contains", path = "app/greet.py", pattern = 'def greet_loudly\(' }
has_test = { check = "file_exists", path = "tests/test_greet.py" }
"""
    + _RUBRIC_AND_VERDICT
)

_REVIEW_TOML = (
    r"""
id = "synthetic-prompt/synthetic-review"
description = "Name the injection class without editing anything."

[setup]
files = ["app/db.py"]
project_kind = "library"

[gate]
expr = "db_untouched and names_class"

[gate.bind]
db_untouched = { check = "file_unchanged", path = "app/db.py" }
names_class = { check = "answer_matches", pattern = '(?i)sql\s*injection|cwe[-\s]?89\b' }
"""
    + _RUBRIC_AND_VERDICT
)

_PYPROJECT = '[project]\nname = "synthetic-fixture"\nversion = "9.9.9"\ndependencies = ["pytest"]\n'
_GREET = 'def greet(name: str) -> str:\n    return f"hi {name}"\n'
_LOUD = _GREET + "\n\ndef greet_loudly(name: str) -> str:\n    return greet(name).upper()\n"
_DB = (
    'def find(conn, name):\n    return conn.execute("SELECT * FROM t WHERE n = \'" + name + "\'")\n'
)
_DB_FIXED = (
    'def find(conn, name):\n    return conn.execute("SELECT * FROM t WHERE n = ?", (name,))\n'
)
_SQLI_ANSWER = "app/db.py concatenates `name` into SQL: SQL injection.\n"


def write_tree(root: Path, files: dict[str, str]) -> None:
    """Write ``{relative path: text}`` under ``root``, creating parent dirs."""
    for rel, text in files.items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(text, encoding="utf-8")


def _edit_sample(root: Path) -> Path:
    sample_dir = root / "synthetic-prompt" / "synthetic-edit"
    write_tree(
        sample_dir,
        {
            "sample.toml": _EDIT_TOML,
            "setup/pyproject.toml": _PYPROJECT,
            "setup/app/greet.py": _GREET,
            "solution/app/greet.py": _LOUD,
            "solution/tests/test_greet.py": "def test_loud() -> None:\n    assert True\n",
            # Wrong overlay: the test exists but the function is only a TODO.
            "solution/negatives/todo-only/app/greet.py": _GREET + "\n# TODO: loud greeting\n",
            "solution/negatives/todo-only/tests/test_greet.py": "def test_todo() -> None: ...\n",
            # Wrong attempt that edits nothing and only claims success.
            "solution/negatives/claims-done/transcript.md": "Added greet_loudly and a test.\n",
        },
    )
    return sample_dir


def _review_sample(root: Path) -> Path:
    sample_dir = root / "synthetic-prompt" / "synthetic-review"
    write_tree(
        sample_dir,
        {
            "sample.toml": _REVIEW_TOML,
            "setup/app/db.py": _DB,
            "solution/transcript.md": _SQLI_ANSWER,
            # A well-formed review that names the wrong class.
            "solution/negatives/wrong-class.md": "app/db.py renders `name` unescaped: XSS.\n",
            # The right class, but the agent edited the file it was told to review.
            "solution/negatives/edits-the-code/app/db.py": _DB_FIXED,
            "solution/negatives/edits-the-code/transcript.md": _SQLI_ANSWER,
        },
    )
    return sample_dir


def test_harness_edit_sample_pristine_fails_solution_passes(
    tmp_path: Path, stub_uv_sync: None
) -> None:
    sample_dir = _edit_sample(tmp_path / "samples")
    sample = _load(sample_dir, "tests")

    assert gate_result(sample, tmp_path / "pristine").passed is False
    solved = gate_result(sample, tmp_path / "solved", Attempt.from_tree(sample_dir / _SOLUTION_DIR))
    assert solved.status == "run" and solved.passed is True, describe(solved)


def test_harness_review_sample_grades_the_transcript(tmp_path: Path, stub_uv_sync: None) -> None:
    sample_dir = _review_sample(tmp_path / "samples")
    sample = _load(sample_dir, "tests")

    assert gate_result(sample, tmp_path / "pristine").passed is False
    solved = gate_result(sample, tmp_path / "solved", Attempt.from_tree(sample_dir / _SOLUTION_DIR))
    assert solved.status == "run" and solved.passed is True, describe(solved)


@pytest.mark.parametrize(
    ("make_sample", "case", "failing_leaf"),
    [
        (_edit_sample, "todo-only", "file_contains:app/greet.py"),
        (_edit_sample, "claims-done", "file_exists:tests/test_greet.py"),
        (_review_sample, "wrong-class.md", "answer_matches:"),
        (_review_sample, "edits-the-code", "file_unchanged:app/db.py"),
    ],
)
def test_harness_rejects_each_negative_on_its_leaf(
    make_sample: Callable[[Path], Path],
    case: str,
    failing_leaf: str,
    tmp_path: Path,
    stub_uv_sync: None,
) -> None:
    sample_dir = make_sample(tmp_path / "samples")
    negative = sample_dir / _SOLUTION_DIR / _NEGATIVES_DIR / case
    gate = gate_result(_load(sample_dir, "tests"), tmp_path / "neg", negative_attempt(negative))

    assert gate.passed is False
    # The failure message names the leaf that rejected the attempt.
    lines = describe(gate).splitlines()
    assert any(ln.startswith(failing_leaf) and "passed=False" in ln for ln in lines), lines


def test_harness_collects_negatives_of_both_shapes(tmp_path: Path) -> None:
    solution = _review_sample(tmp_path / "samples") / _SOLUTION_DIR
    (solution / _NEGATIVES_DIR / ".DS_Store").write_text("", encoding="utf-8")

    negatives = negative_paths(solution)

    assert [p.name for p in negatives] == ["edits-the-code", "wrong-class.md"]
    overlay_case, answer_case = (negative_attempt(p) for p in negatives)
    assert overlay_case == Attempt(negatives[0], _SQLI_ANSWER)
    assert answer_case == Attempt(None, "app/db.py renders `name` unescaped: XSS.\n")
    assert negative_paths(tmp_path / "missing") == []


def test_negative_attempt_rejects_an_unknown_shape(tmp_path: Path) -> None:
    stray = tmp_path / "notes.txt"
    stray.write_text("why these fail", encoding="utf-8")
    with pytest.raises(ValueError, match=r"notes\.txt.*<case>\.md"):
        negative_attempt(stray)


def test_overlay_skips_the_answer_and_negatives(tmp_path: Path) -> None:
    solution = tmp_path / "solution"
    write_tree(
        solution,
        {
            "transcript.md": "answer",
            "docs/transcript.md": "fixture",
            "a.py": "x",
            "negatives/wrong.md": "wrong answer",
            "negatives/case/a.py": "wrong edit",
            "pkg/negatives/n.py": "fixture",
        },
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    overlay_solution(solution, scratch)

    copied = sorted(p.relative_to(scratch).as_posix() for p in scratch.rglob("*") if p.is_file())
    assert copied == ["a.py", "docs/transcript.md", "pkg/negatives/n.py"]
    assert (scratch / "a.py").read_text(encoding="utf-8") == "x"
    assert solution_transcript(solution) == "answer"
    assert solution_transcript(tmp_path / "missing") == ""


def test_is_review_only_ignores_negatives(tmp_path: Path) -> None:
    root = tmp_path / "samples"
    assert is_review_only(_review_sample(root) / _SOLUTION_DIR) is True
    assert is_review_only(_edit_sample(root) / _SOLUTION_DIR) is False


def test_materialize_ignores_solution(tmp_path: Path, stub_uv_sync: None) -> None:
    sample_dir = _edit_sample(tmp_path / "samples")
    baseline = materialize(_load(sample_dir, "tests"), tmp_path / "scratch")

    for tree in (baseline.repo_root, baseline.setup_snapshot):
        assert not (tree / _SOLUTION_DIR).exists()
        assert not (tree / "tests" / "test_greet.py").exists()
        assert (tree / "app" / "greet.py").read_text(encoding="utf-8") == _GREET


def test_loader_and_validator_ignore_solution(tmp_path: Path) -> None:
    root = tmp_path / "samples"
    _edit_sample(root)
    _review_sample(root)

    samples = load_layer_samples(root, "tests")
    assert [s.id for s in samples] == [
        "synthetic-prompt/synthetic-edit",
        "synthetic-prompt/synthetic-review",
    ]
    _, task_errors = TaskRegistry.collect(samples, ["synthetic-prompt"])
    errors = validate_samples(samples)
    assert task_errors == []
    assert errors == [], "\n".join(f"{e.path}: {e.message}" for e in errors)
