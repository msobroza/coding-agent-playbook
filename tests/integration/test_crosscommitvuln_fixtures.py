"""Group-C invariants over the find-injected-vuln-* fixtures (spec §9.2).

- needle-leak: each fixture's prompt_args contains none of its CVE's banned
  tokens -- the shared v2 framing vocabulary plus, per fixture, its CVE id,
  CWE id(s), sink API symbol, and flaw-class words (§5.2);
- the shared CC BY ATTRIBUTIONS.md exists and carries the license URL,
  author credit, DOI, arXiv id, and the required change indication (§4.2);
- each fixture runs hermetically under the fake runner with a StubJudge.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest

from coding_agent_playbook.evals.judge import StubJudge
from coding_agent_playbook.evals.loader import load_eval_task_from_dir
from coding_agent_playbook.evals.runner import capture, materialize
from coding_agent_playbook.evals.scoring import score

_TASKS_ROOT = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "coding_agent_playbook"
    / "resources"
    / "eval_tasks"
)

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

    monkeypatch.setattr("coding_agent_playbook.evals.runner.subprocess.run", _stub_run)
    monkeypatch.setattr("coding_agent_playbook.evals.runner.shutil.which", lambda _b: "/fake/uv")


def _task(fixture_id: str) -> Any:
    return load_eval_task_from_dir(_TASKS_ROOT / fixture_id, source_package="coding_agent_playbook")


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
    candidate = capture(baseline.repo_root, baseline, "transcript")
    report = score(task, baseline, candidate, judge=StubJudge(default=0.9))
    gate = next(c for c in report.checks if c.check_id == "gate")
    rubric = next(c for c in report.checks if c.check_id == "rubric")
    assert gate.passed is True  # review-only gate: no-op fake runner => unchanged
    assert rubric.status == "run"
    assert rubric.passed is True  # composite 0.9 >= 0.5 fail floor
