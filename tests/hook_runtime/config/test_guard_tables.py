"""The typed reads of ``guard_config.json``'s pack tables (specs/prT-package-layout.md §8 B.6).

``GuardTables`` is the reader side of the contract the sync writer renders: the
round trip runs the real writer through ``PackRepo`` and reads every table back
through ``load_guard_config``. A missing or malformed table reads as its default
and never raises; the Stop gate's rows keep the rules the four stage-row loops
applied, tightened only on rows sync never writes. An AST walk keeps every
pack-table read of the hook runtime behind the accessors.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Final

import pytest

import coding_agent_playbook.hook_runtime as hook_runtime_package
from coding_agent_playbook.hook_runtime.config.guard_config import (
    GuardConfig,
    load_guard_config,
    parse_guard_config,
)
from coding_agent_playbook.hook_runtime.config.guard_tables import (
    GuardTables,
    ProtectedTable,
    RuffTable,
    SecretPattern,
    StageRecord,
    StopGate,
    VerifyCommand,
)
from coding_agent_playbook.hook_runtime.stop.coordinator import GatePolicy
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs
from coding_agent_playbook.security.trust import sha256_of_json
from tests.engine_modules import engine_module
from tests.hook_runtime.guard_repo import canonical
from tests.hook_runtime.handlers.pack_repo import (
    PackRepo,
    engine_prompts,
    install_fixture_overlay,
    precommit_config,
    rows_of,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    type Read = Callable[[GuardTables], object]

pytestmark = pytest.mark.catalog

_GLOB_EXEMPT: Final = MappingProxyType({"*token*": ("*token*.py",)})
_DEFAULT_GATE: Final = StopGate(
    budget_s=3.0,
    max_blocks=2,
    stage_rows=(),
    stages=(),
    verify_commands=(),
    claim_patterns=(),
)
_NO_RUFF: Final = RuffTable(
    project_select=(), project_ignore=(), safe_fix_select=(), safe_fix_ignore=()
)
_NO_PROTECTED: Final = ProtectedTable(
    hook_artifacts=(), resource_roots=(), artifact_ids=frozenset()
)
#: Each accessor with the value it reads from a ``guard_config.json`` holding no pack table.
_DEFAULTS: Final[list[Any]] = [
    pytest.param(lambda t: t.stop_gate(), _DEFAULT_GATE, id="stop_gate"),
    pytest.param(lambda t: t.prompt_output_contract("review"), (), id="prompt_output_contract"),
    pytest.param(lambda t: t.prompts_with_output_contract(), (), id="prompts_with_contract"),
    pytest.param(lambda t: t.notebook_max_bytes(7), 7, id="notebook_max_bytes"),
    pytest.param(lambda t: t.eval_fixture_globs(["a/**"]), ("a/**",), id="eval_fixture_globs"),
    pytest.param(lambda t: t.protected(), _NO_PROTECTED, id="protected"),
    pytest.param(lambda t: t.precommit_hook_ids(), (), id="precommit_hook_ids"),
    pytest.param(lambda t: t.auto_sync(), False, id="auto_sync"),
    pytest.param(lambda t: t.facts(), None, id="facts"),
    pytest.param(lambda t: t.applicability(), (), id="applicability"),
    pytest.param(lambda t: t.network_mode(), None, id="network_mode"),
    pytest.param(lambda t: t.ruff(), _NO_RUFF, id="ruff"),
    pytest.param(lambda t: t.secret_path_exempt([".env.example"]), (".env.example",), id="exempt"),
    pytest.param(lambda t: t.secret_glob_exempt(_GLOB_EXEMPT), _GLOB_EXEMPT, id="glob_exempt"),
    pytest.param(lambda t: t.secret_patterns(), (), id="secret_patterns"),
]

_ROUND_TRIP_HOOKS: Final = (
    "stop-ci-parity-gate",
    "stop-drift-and-orphan-gate",
    "coverage-diff-gate",
    "secret-content-guard",
    "network-egress-guard",
)
_ROUND_TRIP_CONFIG: Final[dict[str, dict[str, Any]]] = {
    "stop-ci-parity-gate": {"stages": ["tests"], "max_blocks": 3, "budget_s": 7.5},
    "secret-content-guard": {
        "extra_patterns": [{"id": "acme", "regex": "ACME-[0-9]{8}", "label": "Acme token"}]
    },
}
_ROUND_TRIP_DETECT: Final = DetectInputs(
    facts={"dev_tools": {"ruff", "pytest"}, "dev_dependencies": {"pytest-cov": ">=5"}}
)
_RUFF_SELECTION: Final = '[tool.ruff.lint]\nselect = ["E", "I", "UP"]\nignore = ["UP007"]\n'


@pytest.fixture
def synced(tmp_path: Path, make_package: Callable[..., str]) -> tuple[GuardTables, dict[str, Any]]:
    """What sync renders with every pack table filled, and those tables read back."""
    regulated = install_fixture_overlay(make_package, "regulated", "playbook_rules_regulated")
    repo = PackRepo.create(tmp_path)
    repo.write("pyproject.toml", _RUFF_SELECTION)
    repo.write(".pre-commit-config.yaml", precommit_config("playbook-validate", "playbook-metrics"))
    data = repo.install_pack(
        _ROUND_TRIP_HOOKS,
        rows=rows_of(
            ("AGENTS.md", "composite", "", ""), (".claude/rules/x.md", "rule", "tdd", "p")
        ),
        packages=("coding_agent_playbook", "acme_rules"),
        per_hook=_ROUND_TRIP_CONFIG,
        auto_sync=True,
        detect=_ROUND_TRIP_DETECT,
        prompts=engine_prompts(),
        overlays=(regulated,),
    )
    cfg = load_guard_config(repo.repo, None, platform="linux", home=None)
    assert isinstance(cfg, GuardConfig), cfg
    document: dict[str, Any] = json.loads(data)
    return cfg.tables, document


@pytest.mark.catalog
def test_accessors_read_what_sync_renders(synced: tuple[GuardTables, dict[str, Any]]) -> None:
    tables, document = synced

    gate = tables.stop_gate()

    assert (gate.budget_s, gate.max_blocks) == (7.5, 3)
    assert gate.stage_rows == tuple(document["stop_gate"]["stages"])
    assert gate.claim_patterns == tuple(document["stop_gate"]["claim_patterns"])
    assert gate.verify_commands == (
        VerifyCommand(id="lint", argv=("ruff", "check")),
        VerifyCommand(id="format", argv=("ruff", "format")),
        VerifyCommand(id="tests", argv=("pytest",)),
    )
    lint = StageRecord(
        name="lint",
        owner="stop-ci-parity-gate",
        tool="ruff",
        args=("check", "--output-format=json", "."),
        timeout_s=3.0,
    )
    assert lint in gate.stages
    assert {stage.name for stage in gate.stages} == {
        "drift",
        "lint",
        "verify-claim",
        "tests",
        "coverage",
    }


@pytest.mark.catalog
def test_every_other_pack_table_reads_what_sync_renders(
    synced: tuple[GuardTables, dict[str, Any]],
) -> None:
    tables, document = synced

    review = document["prompts"]["review-core"]["output_contract"]
    assert tables.prompt_output_contract("review-core") == tuple(review)
    contracted = set(tables.prompts_with_output_contract())
    assert {"review-core", "security-review-core", "find-injected-vulnerability"} <= contracted
    # ADR 0011: the harnesses' own /review and /security-review are not playbook prompts.
    assert not {"review", "security-review"} & contracted
    assert "explain" not in tables.prompts_with_output_contract()  # its contract is empty
    assert tables.notebook_max_bytes(1) == 5 * 1024 * 1024
    assert tables.eval_fixture_globs(()) == ("**/eval_samples/*/setup/**",)
    assert tables.protected() == ProtectedTable(
        hook_artifacts=(
            ".coding-agent-playbook/hooks/",
            ".claude/hooks/playbook/",
            ".opencode/plugins/playbook-hooks.js",
        ),
        resource_roots=("pkg:coding_agent_playbook/resources", "pkg:acme_rules/resources"),
        artifact_ids=frozenset({"tdd"}),
    )
    assert tables.precommit_hook_ids() == ("playbook-metrics", "playbook-validate")
    assert tables.auto_sync() is True
    assert tables.facts() == document["facts"]
    assert tables.applicability() == tuple(document["applicability"])
    assert tables.network_mode() == "enforce"


@pytest.mark.catalog
def test_ruff_and_secret_tables_read_what_sync_renders(
    synced: tuple[GuardTables, dict[str, Any]],
) -> None:
    tables, document = synced

    assert tables.ruff() == RuffTable(
        project_select=("E", "I", "UP"),
        project_ignore=("UP007",),
        safe_fix_select=("I", "UP"),
        safe_fix_ignore=("UP007",),
    )
    assert tables.secret_path_exempt(()) == tuple(document["secret_path_exempt"])
    assert tables.secret_glob_exempt({}) == {
        glob: tuple(exempt) for glob, exempt in document["secret_glob_exempt"].items()
    }
    assert tables.secret_patterns() == (
        SecretPattern(id="acme", regex="ACME-[0-9]{8}", label="Acme token"),
    )


@pytest.mark.parametrize(("read", "expected"), _DEFAULTS)
def test_a_missing_table_reads_as_its_default(read: Read, expected: object) -> None:
    assert read(GuardTables({})) == expected


@pytest.mark.parametrize(
    ("table", "raw", "read", "expected"),
    [
        ("stop_gate", ["not", "a table"], lambda t: t.stop_gate(), _DEFAULT_GATE),
        (
            "stop_gate",
            {"stages": "x", "verify_commands": {"id": "x"}, "max_blocks": "3", "budget_s": "7"},
            lambda t: t.stop_gate(),
            _DEFAULT_GATE,
        ),
        ("prompts", {"review": ["(?i)ok"]}, lambda t: t.prompt_output_contract("review"), ()),
        ("prompts", ["review"], lambda t: t.prompts_with_output_contract(), ()),
        ("notebooks", {"max_bytes": True}, lambda t: t.notebook_max_bytes(7), 7),
        ("notebooks", {"max_bytes": 0}, lambda t: t.notebook_max_bytes(7), 7),
        ("notebooks", 5, lambda t: t.notebook_max_bytes(7), 7),
        (
            "eval",
            {"fixture_globs": ["a/**", 3]},
            lambda t: t.eval_fixture_globs(["d/**"]),
            ("d/**",),
        ),
        ("eval", {"fixture_globs": "a/**"}, lambda t: t.eval_fixture_globs(["d/**"]), ("d/**",)),
        ("protected", [".claude/"], lambda t: t.protected(), _NO_PROTECTED),
        ("precommit", {"playbook_hook_ids": "playbook-x"}, lambda t: t.precommit_hook_ids(), ()),
        ("auto_sync", "true", lambda t: t.auto_sync(), False),
        ("auto_sync", 1, lambda t: t.auto_sync(), False),
        ("facts", ["torch"], lambda t: t.facts(), None),
        ("applicability", {"id": "r"}, lambda t: t.applicability(), ()),
        ("network", {"mode": 5}, lambda t: t.network_mode(), None),
        ("network", "enforce", lambda t: t.network_mode(), None),
        ("ruff", "E", lambda t: t.ruff(), _NO_RUFF),
        ("secret_path_exempt", "x", lambda t: t.secret_path_exempt(["d"]), ("d",)),
        ("secret_glob_exempt", ["x"], lambda t: t.secret_glob_exempt(_GLOB_EXEMPT), _GLOB_EXEMPT),
        ("secret_rules", {"extra_patterns": "x"}, lambda t: t.secret_patterns(), ()),
    ],
)
def test_a_malformed_table_reads_as_its_default(
    table: str, raw: object, read: Read, expected: object
) -> None:
    assert read(GuardTables({table: raw})) == expected


@pytest.mark.parametrize(
    ("table", "raw", "read", "expected"),
    [
        (
            "prompts",
            {"review": {"output_contract": [3, "", "(?i)ok"]}, "x": {"output_contract": [""]}},
            lambda t: (t.prompt_output_contract("review"), t.prompts_with_output_contract()),
            (("(?i)ok",), ("review",)),
        ),
        ("eval", {"fixture_globs": []}, lambda t: t.eval_fixture_globs(["d/**"]), ()),
        (
            "protected",
            {
                "hook_artifacts": "abc",
                "resource_roots": [3, "pkg:p/resources"],
                "entries": [{"artifact_id": 5}, {"artifact_id": ""}, "x", {"artifact_id": "a"}],
            },
            lambda t: t.protected(),
            ProtectedTable(
                hook_artifacts=(), resource_roots=("pkg:p/resources",), artifact_ids=frozenset("a")
            ),
        ),
        (
            "precommit",
            {"playbook_hook_ids": [1, "", "playbook-x"]},
            lambda t: t.precommit_hook_ids(),
            ("playbook-x",),
        ),
        ("applicability", [1, {"id": "r"}, "x"], lambda t: t.applicability(), ({"id": "r"},)),
        (
            "ruff",
            {"project_select": "E", "safe_fix_select": ["I", 3]},
            lambda t: t.ruff(),
            RuffTable(
                project_select=(), project_ignore=(), safe_fix_select=("I",), safe_fix_ignore=()
            ),
        ),
        ("secret_path_exempt", [1, "", "e"], lambda t: t.secret_path_exempt(["d"]), ("e",)),
        (
            "secret_glob_exempt",
            {"*k*": "x", "*j*": ["*j*.py", 3, ""]},
            lambda t: t.secret_glob_exempt(_GLOB_EXEMPT),
            {"*k*": (), "*j*": ("*j*.py",)},
        ),
        (
            "secret_rules",
            {
                "extra_patterns": [
                    {"id": "a"},
                    {"id": 3, "regex": "x"},
                    "b",
                    {"id": "b", "regex": "y", "label": 7},
                    {"id": "c", "regex": "z", "label": ""},
                ]
            },
            lambda t: t.secret_patterns(),
            (
                SecretPattern(id="b", regex="y", label="b"),
                SecretPattern(id="c", regex="z", label="c"),
            ),
        ),
    ],
)
def test_items_of_the_wrong_type_are_skipped(
    table: str, raw: object, read: Read, expected: object
) -> None:
    assert read(GuardTables({table: raw})) == expected


def _gate(**table: object) -> StopGate:
    return GuardTables({"stop_gate": table}).stop_gate()


def test_stage_records_skip_rows_without_a_str_name() -> None:
    rows = [
        {"tool": "ruff"},
        {"name": 3},
        "lint",
        {"name": "lint", "owner": 7, "tool": "", "args": "x"},
    ]

    assert _gate(stages=rows).stages == (
        StageRecord(name="lint", owner=None, tool=None, args=None, timeout_s=None),
    )


def test_stage_args_are_the_str_of_each_listed_arg() -> None:
    rows = [{"name": "tests", "tool": "project_python", "args": ["-m", "pytest", 3]}]

    assert _gate(stages=rows).stages[0].args == ("-m", "pytest", "3")


@pytest.mark.parametrize(
    ("timeout_s", "expected"),
    [(True, None), (False, None), (0, None), (-1.5, None), ("5", None), (5, 5.0), (0.5, 0.5)],
)
def test_a_bool_is_never_a_timeout(timeout_s: object, expected: float | None) -> None:
    assert _gate(stages=[{"name": "lint", "timeout_s": timeout_s}]).stages[0].timeout_s == expected


def test_verify_commands_need_an_id_and_a_list_argv() -> None:
    rows = [
        {"id": "lint", "argv": ["ruff", "check"]},
        {"id": "", "argv": ["pytest"]},
        {"id": 7, "argv": ["pytest"]},
        {"id": "tests", "argv": "pytest -q"},
        {"argv": ["mypy"]},
        ["custom-1", ["mypy"]],
        {"id": "typecheck", "argv": ["mypy", 3]},
    ]

    assert _gate(verify_commands=rows).verify_commands == (
        VerifyCommand(id="lint", argv=("ruff", "check")),
        VerifyCommand(id="typecheck", argv=("mypy", "3")),
    )


def test_claim_patterns_keep_only_strings() -> None:
    assert _gate(claim_patterns=["(?i)done", 3, None]).claim_patterns == ("(?i)done",)


@pytest.mark.parametrize(
    ("max_blocks", "expected"), [(99, 8), (0, 1), (-4, 1), (5, 5), (True, 2), (2.5, 2), (None, 2)]
)
def test_max_blocks_is_clamped_into_its_range(max_blocks: object, expected: int) -> None:
    assert _gate(max_blocks=max_blocks).max_blocks == expected


@pytest.mark.parametrize(
    ("budget_s", "expected"),
    [(0, 3.0), (-2, 3.0), (True, 3.0), ("9", 3.0), (None, 3.0), (9, 9.0), (1.5, 1.5)],
)
def test_budget_defaults_when_not_positive(budget_s: object, expected: float) -> None:
    assert _gate(budget_s=budget_s).budget_s == expected


def test_gate_policy_from_gate_hashes_the_rows_verbatim() -> None:
    rows: list[object] = [{"name": "lint", "timeout_s": True}, {"tool": "ruff"}, "odd"]
    gate = _gate(stages=rows, max_blocks=4, budget_s=6)

    policy = GatePolicy.from_gate(gate)

    assert policy.stages_sha256() == sha256_of_json(rows)
    assert (policy.budget_s, policy.max_blocks, policy.stages) == (6.0, 4, tuple(rows))


def test_tables_stay_a_read_only_mapping() -> None:
    document = {"schema_version": 1, "hooks": {}, "stop_gate": {"max_blocks": 4}, "x": [1]}
    cfg = parse_guard_config(canonical(document))
    assert isinstance(cfg, GuardConfig)

    assert cfg.tables.get("x") == [1]
    assert cfg.tables.get("missing") is None
    assert cfg.tables["stop_gate"] == {"max_blocks": 4}
    assert dict(cfg.tables) == {"stop_gate": {"max_blocks": 4}, "x": [1]}  # no runtime key
    assert len(cfg.tables) == 2
    assert repr(GuardTables({"x": [1]})) == "GuardTables({'x': [1]})"
    with pytest.raises(TypeError):
        cfg.tables["x"] = []  # type: ignore[index]


#: Modules that still read a pack table by string: the ``ruff`` table and one ``stop_gate``
#: read, left for the writer side (specs/prT-package-layout.md §8 B.13).
_RAW_READS_LEFT: Final = frozenset(
    {
        engine_module("coding_agent_playbook.hook_runtime.handlers.feedback.ruff_feedback"),
        engine_module("coding_agent_playbook.hook_runtime.handlers.feedback._ruff_buckets"),
    }
)


def test_pack_tables_are_read_only_through_guard_tables() -> None:
    reads = list(_raw_table_reads())

    assert sorted(where for module, where in reads if module not in _RAW_READS_LEFT) == []
    assert {module for module, _ in reads} >= _RAW_READS_LEFT  # the list only shrinks


def _raw_table_reads() -> Iterator[tuple[str, str]]:
    """``(module, "path:line")`` of every ``.tables.get(`` and ``.tables[`` in the hook runtime."""
    root = Path(hook_runtime_package.__file__).parent
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        module = ".".join((hook_runtime_package.__name__, *rel.with_suffix("").parts))
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if _reads_a_table(node):
                yield module.removesuffix(".__init__"), f"{rel}:{getattr(node, 'lineno', 0)}"


def _reads_a_table(node: ast.AST) -> bool:
    if isinstance(node, ast.Subscript):
        return _is_tables(node.value)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        return node.func.attr == "get" and _is_tables(node.func.value)
    return False


def _is_tables(node: ast.expr) -> bool:
    return isinstance(node, ast.Attribute) and node.attr == "tables"
