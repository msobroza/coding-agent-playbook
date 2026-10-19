"""sensitive-data-read-guard: raw data and notebook outputs stay unread (specs/prK-hook-pack.md §E.5).

The engine ships the guard inert (``tier: overlay``, ``mode: off``); every
behavior test activates it through the regulated fixture overlay (``mode:
ask``, the §E.5 deny and allow globs, a 64 KiB CSV sample limit), layered over
the engine definition by the real §A.6 merge. Each call is a real
``playbook-hook simulate pre_tool_use``. The guard is path-based: a ``json.load``
spy proves an oversized notebook is never parsed.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, Final, cast

import pytest

from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.hook_policy import RegistryCatalog, resolve_effective_hooks
from coding_agent_playbook.hook_runtime.decision import Decision
from coding_agent_playbook.hook_runtime.event import Harness
from coding_agent_playbook.hook_runtime.registry import load_builtin
from tests.hook_payloads import load_hook_payload
from tests.hooks.pack_repo import engine_hook

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hooks.pack_repo import PackRepo

    type Deps = Callable[..., RuntimeDeps]

pytestmark = pytest.mark.catalog

HOOK_ID: Final = "sensitive-data-read-guard"
BIG_NOTEBOOK_BYTES: Final = 300 * 1024 * 1024
CSV_CAP: Final = 64 * 1024


def _notebook(*, outputs: bool) -> str:
    cell: dict[str, Any] = {"cell_type": "code", "id": "c1", "source": "df.head()"}
    cell["outputs"] = [{"output_type": "stream", "text": "id,name\n1,Ada\n"}] if outputs else []
    return json.dumps({"cells": [cell], "nbformat": 4, "nbformat_minor": 5})


@pytest.fixture
def repo(pack_repo: PackRepo, regulated_overlay: str) -> PackRepo:
    """The overlay-activated guard over a tree with raw, fixture and notebook data."""
    pack_repo.write("data/raw/customers.csv", "id,name\n1,Ada\n")
    pack_repo.write("data/fixtures/x.csv", "id,name\n")
    pack_repo.write("data/synthetic/big.csv", "x" * (CSV_CAP + 1))
    pack_repo.write("reports/big.csv", "x" * (CSV_CAP + 1))
    pack_repo.write("reports/small.csv", "id\n")
    pack_repo.write("exports/q3.xlsx", "PK")
    pack_repo.write("warehouse/app.db", "SQLite format 3")
    pack_repo.write("notebooks/clean.ipynb", _notebook(outputs=False))
    pack_repo.write("notebooks/eda.ipynb", _notebook(outputs=True))
    pack_repo.write("src/app.py", "x = 1\n")
    big = pack_repo.root / "notebooks" / "big.ipynb"
    with big.open("wb") as handle:
        handle.truncate(BIG_NOTEBOOK_BYTES)  # sparse: stat says 300 MB, no disk used
    pack_repo.install_pack([HOOK_ID], overlays=(regulated_overlay,))
    return pack_repo


def _read(repo: PackRepo, deps: Deps, rel: str) -> SimulateReport:
    return repo.simulate(repo.tool_payload("Read", {"file_path": str(repo.root / rel)}), deps())


def _tool(repo: PackRepo, deps: Deps, tool: str, tool_input: dict[str, Any]) -> SimulateReport:
    return repo.simulate(repo.tool_payload(tool, tool_input), deps())


def _bash(repo: PackRepo, deps: Deps, command: str) -> SimulateReport:
    return _tool(repo, deps, "Bash", {"command": command})


def _golden(repo: PackRepo, deps: Deps, harness: str, case: str) -> SimulateReport:
    """Simulate golden ``case``; its decision, reason and wire output must match."""
    golden = load_hook_payload(harness, "pre_tool_use", case)
    report = repo.simulate(repo.relocate(golden), deps(), harness=Harness(harness))
    expected = golden.expected["result"]
    combined = report.trace.combined
    assert (combined.decision.value, combined.reason) == (
        expected["decision"],
        expected.get("reason", ""),
    )
    assert report.trace.wire == golden.wire()
    return report


def _decision(report: SimulateReport) -> Decision:
    return report.trace.combined.decision


def _rule(report: SimulateReport) -> str:
    return report.trace.combined.outcomes[0].rule_id


@pytest.mark.parametrize("harness", ["claude_code", "opencode"])
def test_read_raw_customers_csv_asks(repo: PackRepo, deps: Deps, harness: str) -> None:
    """An ask on Claude; OpenCode cannot ask, so the same verdict is denied there."""
    report = _golden(repo, deps, harness, "sdr_read_raw_csv")

    assert _rule(report) == "raw_data"


@pytest.mark.parametrize("harness", ["claude_code", "opencode"])
def test_fixture_csv_allowed(repo: PackRepo, deps: Deps, harness: str) -> None:
    _golden(repo, deps, harness, "sdr_read_fixture_csv")


def test_300mb_notebook_asks_without_json_load(
    repo: PackRepo, deps: Deps, monkeypatch: pytest.MonkeyPatch
) -> None:
    loads: list[object] = []

    def spy(*args: object, **kwargs: object) -> object:
        loads.append(args)
        raise AssertionError("an oversized notebook was parsed")

    monkeypatch.setattr(json, "load", spy)

    report = _golden(repo, deps, "claude_code", "sdr_read_big_notebook")

    assert _rule(report) == "notebook_size"
    assert loads == []


def test_notebook_with_outputs_asks(repo: PackRepo, deps: Deps) -> None:
    with_outputs = _read(repo, deps, "notebooks/eda.ipynb")
    clean = _read(repo, deps, "notebooks/clean.ipynb")
    edit = {"notebook_path": str(repo.root / "notebooks/eda.ipynb"), "new_source": "x = 1"}
    edited = _tool(repo, deps, "NotebookEdit", edit)

    assert (_decision(with_outputs), _rule(with_outputs)) == (Decision.ASK, "notebook_outputs")
    assert with_outputs.trace.combined.reason == (
        '"notebooks/eda.ipynb" keeps cell outputs, which may embed customer rows.\n'
        "Read it with outputs stripped, or confirm with the user."
    )
    assert _decision(clean) is Decision.NONE
    assert _decision(edited) is Decision.NONE  # editing a cell shows no outputs


@pytest.mark.parametrize(
    ("rel", "expected", "rule"),
    [
        ("data/raw/customers.csv", Decision.ASK, "raw_data"),
        ("exports/q3.xlsx", Decision.ASK, "raw_data"),
        ("warehouse/app.db", Decision.ASK, "raw_data"),
        ("data/raw/not-there.parquet", Decision.ASK, "raw_data"),  # path-based: no stat needed
        ("reports/big.csv", Decision.ASK, "csv_size"),
        ("reports/small.csv", Decision.NONE, ""),
        ("data/synthetic/big.csv", Decision.NONE, ""),  # allow_globs exempt the size rule too
        ("tests/data/sample.parquet", Decision.NONE, ""),
        ("src/app.py", Decision.NONE, ""),
    ],
)
def test_read_rows(repo: PackRepo, deps: Deps, rel: str, expected: Decision, rule: str) -> None:
    report = _read(repo, deps, rel)

    assert _decision(report) is expected
    assert (_rule(report) if report.trace.combined.outcomes else "") == rule


def test_csv_reason_gives_size_and_limit(repo: PackRepo, deps: Deps) -> None:
    report = _read(repo, deps, "reports/big.csv")

    assert report.trace.combined.reason == (
        f'"reports/big.csv" is a {CSV_CAP + 1}-byte CSV, over the {CSV_CAP}-byte sample '
        "limit: it may hold customer records.\n"
        "Work from a fixture or synthetic sample instead, or confirm with the user."
    )


@pytest.mark.parametrize(
    ("tool", "tool_input", "expected"),
    [
        ("Grep", {"pattern": "Ada", "path": "data/raw"}, Decision.ASK),
        ("Grep", {"pattern": "Ada", "glob": "*.parquet"}, Decision.ASK),
        ("Glob", {"pattern": "data/raw/**/*.csv"}, Decision.ASK),
        ("Grep", {"pattern": "Ada", "path": "src"}, Decision.NONE),
        ("Glob", {"pattern": "**/*.py"}, Decision.NONE),
    ],
)
def test_search_tools(
    repo: PackRepo, deps: Deps, tool: str, tool_input: dict[str, Any], expected: Decision
) -> None:
    assert _decision(_tool(repo, deps, tool, tool_input)) is expected


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("cat data/raw/customers.csv", Decision.ASK),
        ("head -n 5 data/raw/customers.csv | cut -d, -f1", Decision.ASK),
        ("awk -F, '{print $1}' < data/raw/customers.csv", Decision.ASK),
        ("cat data/raw/*.csv", Decision.ASK),  # a glob the shell expands
        ("cd data && tail raw/*.csv", Decision.ASK),  # judged from the segment's cwd
        ("sqlite3 warehouse/app.db 'select * from customers'", Decision.ASK),
        ("duckdb -c \"select * from 'exports/q3.xlsx'\"", Decision.ASK),
        ("python -c \"import pandas as pd; pd.read_csv('data/raw/customers.csv')\"", Decision.ASK),
        ("cat notebooks/eda.ipynb", Decision.ASK),
        ("cat data/fixtures/x.csv", Decision.NONE),
        ("grep -r Ada src", Decision.NONE),  # not a data reader
        ("echo data/raw/customers.csv", Decision.NONE),
        ("cat README.md", Decision.NONE),
    ],
)
def test_bash_readers(repo: PackRepo, deps: Deps, command: str, expected: Decision) -> None:
    assert _decision(_bash(repo, deps, command)) is expected


def test_bash_cat_of_raw_data_asks(repo: PackRepo, deps: Deps) -> None:
    report = _bash(repo, deps, "cd data && cat raw/customers.csv")

    assert (_decision(report), _rule(report)) == (Decision.ASK, "raw_data")
    assert report.trace.combined.reason == (
        '"data/raw/customers.csv" is raw data under this repository\'s data policy.\n'
        "Work from a fixture or synthetic sample instead, or confirm with the user."
    )


def test_enforce_mode_denies(pack_repo: PackRepo, regulated_overlay: str, deps: Deps) -> None:
    pack_repo.write("data/raw/customers.csv", "id\n")
    pack_repo.install_pack(
        [HOOK_ID], overlays=(regulated_overlay,), handler_config={HOOK_ID: {"mode": "enforce"}}
    )

    raw = _read(pack_repo, deps, "data/raw/customers.csv")
    bash = _bash(pack_repo, deps, "cat data/raw/customers.csv")

    assert [_decision(r) for r in (raw, bash)] == [Decision.DENY, Decision.DENY]
    assert raw.trace.combined.reason == (
        'Blocked: "data/raw/customers.csv" is raw data under this repository\'s data policy.\n'
        "Work from a fixture or synthetic sample instead."
    )


def test_mode_off_is_inert(pack_repo: PackRepo, regulated_overlay: str, deps: Deps) -> None:
    pack_repo.install_pack(
        [HOOK_ID], overlays=(regulated_overlay,), handler_config={HOOK_ID: {"mode": "off"}}
    )

    assert _decision(_read(pack_repo, deps, "data/raw/customers.csv")) is Decision.NONE


def test_engine_default_is_not_rendered(tmp_path: Path) -> None:
    """Shipped inert: no tier or enable list switches it on without an overlay (K-11)."""
    hooks_cfg = HooksConfig(enabled=True, tiers=("default", "opt-in"), enable=(HOOK_ID,))

    view = resolve_effective_hooks(
        [engine_hook(HOOK_ID)],
        [],
        hooks_cfg,
        GuardrailsConfig(),
        cast("Facts", {}),
        tmp_path,
        adapters_enabled=["claude_code"],
        handlers=RegistryCatalog(),
    )

    assert view.resolved == []
    fm = engine_hook(HOOK_ID).frontmatter
    assert (fm.tier, fm.enabled, fm.applies_if) == ("overlay", True, {})  # no applies_if
    assert fm.handler_for("pre_tool_use").config == {
        "mode": "off",
        "deny_globs": [],
        "allow_globs": [],
        "csv_max_sample_bytes": CSV_CAP,
    }


def test_declares_relaxing_keys() -> None:
    """Exemptions and the size threshold loosen the guard: a mandatory hook ignores the consumer's."""
    schema = load_builtin("sensitive_read_guard").config_schema

    assert schema["deny_globs"].policy == "extend"
    assert {key for key, spec in schema.items() if spec.policy == "relax"} == {
        "allow_globs",
        "csv_max_sample_bytes",
    }
    assert schema["mode"].policy == "strictest"
