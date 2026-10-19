"""Group-C invariants over the find-injected-vuln-* fixtures (spec §9.2).

- needle-leak: each fixture's prompt_args contains none of its CVE's banned
  tokens -- the shared v2 framing vocabulary plus, per fixture, its CVE id,
  CWE id(s), sink API symbol, and flaw-class words (§5.2);
- the shared CC BY ATTRIBUTIONS.md exists and carries the license URL,
  author credit, DOI, arXiv id, and the required change indication (§4.2);
- each fixture runs hermetically under the fake runner with a StubJudge;
- the deterministic CWE-class gate (`answer_matches`) accepts a correct answer,
  rejects a wrong-class one, and short-circuits the judge when it rejects.

These are review-only tasks: the agent must not edit, so it is graded on its
*answer* (the transcript). The stand-in answers live in `ccv_answers.py`.
"""

from __future__ import annotations

import re
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evals.loader import load_eval_task_from_dir
from coding_agent_playbook.evals.run.harness_runner import capture, materialize
from coding_agent_playbook.evals.run.scoring import score
from tests._catalog import CORE_ROOT
from tests.integration.ccv_answers import CORRECT_ANSWER, WRONG_CLASS_ANSWER

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = pytest.mark.catalog

_TASKS_ROOT = CORE_ROOT / "eval_tasks"

# Per-fixture banned tokens: CVE id, CWE id (both forms), sink API symbol(s), and
# flaw-class words (spec §5.2). The v2 framing bans below are shared across all
# fixtures.
_FRAMING_BANS = (
    "commit",
    "commits",
    "multiple",
    "multi-commit",
    "gradually",
    "over time",
    "across",
    "benign",
    "static analysis",
    "sast",
    "per-commit",
    "scanner",
    "individually",
)
_PER_FIXTURE_BANS: dict[str, tuple[str, ...]] = {
    "find-injected-vuln-modoboa-cmdi": (
        "cve-2026-27602",
        "cwe-78",
        "78",
        "exec_cmd",
        "command injection",
        "shell=true",
        "subprocess",
        "jobs.py",
        "sysutils.py",
        "mailbox",
    ),
    "find-injected-vuln-ormar-sqli": (
        "cve-2026-26198",
        "cwe-89",
        "89",
        "sql injection",
        "sql",
        "queries.py",
        "db.py",
    ),
    "find-injected-vuln-changedetection-ssrf": (
        "cve-2026-27696",
        "cwe-918",
        "918",
        "ssrf",
        "requests.get",
        "fetch.py",
        "watch.py",
    ),
    "find-injected-vuln-langroid-codeinj": (
        "cve-2025-46724",
        "cwe-94",
        "94",
        "code injection",
        "eval",
        "exec",
        "tools.py",
        "runner.py",
    ),
    "find-injected-vuln-pytorch-deserial": (
        "cve-2025-32434",
        "cwe-502",
        "502",
        "deserialization",
        "pickle",
        "torch.load",
        "loader.py",
        "registry.py",
    ),
    "find-injected-vuln-changedetection-pathtraversal": (
        "cve-2026-29065",
        "cwe-22",
        "22",
        "path traversal",
        "traversal",
        "storage.py",
        "views.py",
    ),
    "find-injected-vuln-authlib-sigbypass": (
        "cve-2026-27962",
        "cwe-347",
        "347",
        "signature bypass",
        "alg=none",
        "jwt_verify.py",
        "auth.py",
    ),
    "find-injected-vuln-graphiti-queryinj": (
        "cve-2026-32247",
        "cwe-943",
        "943",
        "query injection",
        "cypher",
        "graph.py",
        "search.py",
    ),
    "find-injected-vuln-pydash-massassign": (
        "cve-2025-58367",
        "cwe-915",
        "915",
        "mass assignment",
        "set_",
        "merge.py",
        "model.py",
    ),
    "find-injected-vuln-aiplatform-xss": (
        "cve-2026-2472",
        "cwe-79",
        "79",
        "xss",
        "cross-site scripting",
        "render.py",
        "page.py",
    ),
}

_FIXTURE_IDS = sorted(_PER_FIXTURE_BANS)


@pytest.fixture
def stub_uv_sync(monkeypatch: pytest.MonkeyPatch) -> None:
    real_run = subprocess.run

    def _stub_run(args: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if args and args[0] == "uv":
            return subprocess.CompletedProcess(args, 0, "", "")
        return real_run(args, **kwargs)

    monkeypatch.setattr("coding_agent_playbook.evals.run.harness_runner.subprocess.run", _stub_run)
    monkeypatch.setattr(
        "coding_agent_playbook.evals.run.harness_runner.shutil.which", lambda _b: "/fake/uv"
    )


def _task(fixture_id: str) -> Any:
    return load_eval_task_from_dir(_TASKS_ROOT / fixture_id, source_package="coding_agent_playbook")


def _class_gate_pattern(fixture_id: str) -> str:
    """The raw ``names_class`` regex a fixture authors in its ``[gate.bind]``."""
    binding = _task(fixture_id).gate.bind["names_class"]
    assert binding["check"] == "answer_matches", binding
    return str(binding["pattern"])


@pytest.mark.parametrize("fixture_id", _FIXTURE_IDS)
def test_prompt_args_leak_no_needle(fixture_id: str) -> None:
    query = _task(fixture_id).invocation.prompt_args.lower()
    banned = _PER_FIXTURE_BANS[fixture_id] + _FRAMING_BANS
    offenders = [tok for tok in banned if tok in query]
    assert offenders == [], f"{fixture_id}: banned token(s) leaked into query: {offenders}"


def test_attributions_file_present() -> None:
    attributions = (_TASKS_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    assert "creativecommons.org/licenses/by/4.0" in attributions
    assert "Arunabh Majumdar" in attributions
    assert "10.5281/zenodo.19338596" in attributions
    assert "arXiv:2604.21917" in attributions
    # CC BY 4.0 §3(a) change indication: annotations transformed, patterns
    # paraphrased -- mirrors the pydocs-side NOTICE pin.
    lowered = attributions.lower()
    assert "transformed" in lowered and "paraphrases" in lowered


@pytest.mark.parametrize("fixture_id", _FIXTURE_IDS)
def test_fixture_runs_hermetically(fixture_id: str, tmp_path: Path, stub_uv_sync: None) -> None:
    task = _task(fixture_id)
    baseline = materialize(task, tmp_path / "scratch")
    candidate = capture(baseline.repo_root, baseline, CORRECT_ANSWER[fixture_id])
    report = score(task, baseline, candidate, judge=StubJudge(default=0.9))
    gate = next(c for c in report.checks if c.check_id == "gate")
    rubric = next(c for c in report.checks if c.check_id == "rubric")
    # Review-only gate: the no-op fake runner leaves the files unchanged, and the
    # answer names the right CWE class.
    assert gate.passed is True
    assert rubric.status == "run"
    assert rubric.passed is True  # composite 0.9 >= 0.5 fail floor


# --------------------------------------------------------------------------- #
# The deterministic CWE-class gate (`answer_matches`)
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("fixture_id", _FIXTURE_IDS)
def test_wrong_class_answer_loses_the_gate(
    fixture_id: str, tmp_path: Path, stub_uv_sync: None
) -> None:
    """An answer naming the wrong vulnerability class fails the deterministic gate.

    The counterpart to :func:`test_fixture_runs_hermetically`: same untouched
    files, only the answer differs — so this isolates the class gate from the
    ``file_unchanged`` handles.
    """
    task = _task(fixture_id)
    baseline = materialize(task, tmp_path / "scratch")
    candidate = capture(baseline.repo_root, baseline, WRONG_CLASS_ANSWER)

    report = score(task, baseline, candidate, judge=StubJudge(default=0.9))

    gate = next(c for c in report.checks if c.check_id == "gate")
    assert gate.passed is False
    assert report.passed is False  # the verdict is "gate and rubric"


@pytest.mark.parametrize("fixture_id", _FIXTURE_IDS)
def test_wrong_class_answer_never_reaches_the_judge(
    fixture_id: str, tmp_path: Path, stub_uv_sync: None
) -> None:
    """A lost class gate short-circuits the JUDGED tier — a wrong answer costs 0 tokens.

    ``fail_fast=True`` is what the runner (and ``playbook eval --run``) pass, so
    this exercises the real cost-saving path rather than a synthetic one.
    """
    task = _task(fixture_id)
    baseline = materialize(task, tmp_path / "scratch")
    candidate = capture(baseline.repo_root, baseline, WRONG_CLASS_ANSWER)

    judge = StubJudge(default=0.9)
    score(task, baseline, candidate, judge=judge, fail_fast=True)

    assert judge.calls == []


@pytest.mark.parametrize("fixture_id", _FIXTURE_IDS)
def test_correct_class_answer_does_reach_the_judge(
    fixture_id: str, tmp_path: Path, stub_uv_sync: None
) -> None:
    """Control for the short-circuit test: a passing gate still invokes the judge.

    Without this, the ``judge.calls == []`` assertion above would also hold if the
    judge had simply never been wired up.
    """
    task = _task(fixture_id)
    baseline = materialize(task, tmp_path / "scratch")
    candidate = capture(baseline.repo_root, baseline, CORRECT_ANSWER[fixture_id])

    judge = StubJudge(default=0.9)
    score(task, baseline, candidate, judge=judge, fail_fast=True)

    assert judge.calls != []


@pytest.mark.parametrize("fixture_id", _FIXTURE_IDS)
def test_class_gate_rejects_every_other_fixtures_answer(fixture_id: str) -> None:
    """No fixture's class gate accepts another fixture's (correct) answer.

    The gates are deliberately lenient, and leniency is exactly what can go too
    far — a bare ``cwe[-\\s]?94`` prefix-matches ``CWE-943``, so the code-injection
    gate would accept a query-injection answer. This pins the whole 10x10 matrix
    rather than each pattern in isolation, since that is where such a collision
    shows up.
    """
    pattern = _class_gate_pattern(fixture_id)
    accepted = [
        other
        for other in _FIXTURE_IDS
        if other != fixture_id and re.search(pattern, CORRECT_ANSWER[other])
    ]
    assert accepted == [], (
        f"{fixture_id}: gate /{pattern}/ also accepts the answer(s) for {accepted}"
    )


@pytest.mark.parametrize("fixture_id", _FIXTURE_IDS)
def test_judge_grades_the_answer_not_an_empty_diff(
    fixture_id: str, tmp_path: Path, stub_uv_sync: None
) -> None:
    """The judged artifact is the agent's answer — these tasks produce no diff."""
    task = _task(fixture_id)
    baseline = materialize(task, tmp_path / "scratch")
    answer = CORRECT_ANSWER[fixture_id]
    candidate = capture(baseline.repo_root, baseline, answer)

    judge = StubJudge(default=0.9)
    score(task, baseline, candidate, judge=judge)

    assert candidate.diff.strip() == ""  # review-only: nothing was edited
    _criterion, artifact, _n = judge.calls[0]
    assert str(artifact) == answer
