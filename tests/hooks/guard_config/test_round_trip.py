"""The compiled ``guard_config.json``, read back by the hook runtime (specs/prT-package-layout.md 9 AC.2.6).

The writer and the runtime meet only in the written file. These tests compile on a
repository holding every input file the writer reads, with every engine hook on (the
fixture overlay activates the three overlay-tier ones), write the result where sync
does and vouch for its sha256 in the lockfile. The runtime then loads it the way the
dispatcher does: ``load_guard_config`` trusts it, and each pack table reads back
through its typed accessor (``GuardTables``) as the request and the repository imply.
"""

from __future__ import annotations

import hashlib
from typing import TYPE_CHECKING, Any, Final

import pytest

from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.hook_runtime.config.guard_config import GuardConfig, load_guard_config
from coding_agent_playbook.hook_runtime.config.guard_tables import ProtectedTable, RuffTable
from coding_agent_playbook.hook_runtime.config.schema import SUPPORTED_SCHEMA_VERSIONS
from coding_agent_playbook.hooks.guard_config.compile import (
    CompiledGuardConfig,
    GuardConfigRequest,
    compile_guard_config,
)
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs, ProtectInputs
from coding_agent_playbook.security.patterns import SECRET_GLOB_EXEMPT, SECRET_PATH_EXEMPT
from tests.hook_runtime.guard_repo import GuardRepo
from tests.hook_runtime.handlers.pack_repo import (
    engine_hook_paths,
    engine_prompts,
    engine_rules,
    install_fixture_overlay,
    precommit_config,
    resolve_engine_hooks,
    rows_of,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

pytestmark = pytest.mark.catalog

#: Facts that pass every engine hook's gate (pytest-cov: coverage-diff-gate; the
#: Python version: typing-lint-feedback's linked rule).
_FACTS: Final[dict[str, Any]] = {
    "package_manager": "uv",
    "python_version": "3.12",
    "has_notebooks": True,
    "frameworks": {"pytest": ">=8", "fastapi": ">=0.110"},
    "ml_stack": {"torch": ">=2"},
    "dependencies": {"fastapi": ">=0.110", "torch": ">=2"},
    "dev_dependencies": {"pytest": ">=8", "pytest-cov": ">=5", "ruff": ">=0.6"},
    "dev_tools": {"mypy", "pytest", "ruff"},
}
_PYPROJECT: Final = '[tool.ruff.lint]\nselect = ["E", "I", "UP"]\nignore = ["UP007"]\n'
_PRECOMMIT: Final = precommit_config("playbook-validate", "playbook-metrics", "ruff")

type CompiledRepo = tuple[GuardRepo, CompiledGuardConfig]


@pytest.fixture
def compiled_repo(tmp_path: Path, make_package: Callable[..., str]) -> CompiledRepo:
    """Every engine hook compiled on a repo with the writer's input files, written and locked."""
    regulated = install_fixture_overlay(make_package, "regulated", "playbook_rules_regulated")
    repo = GuardRepo.create(tmp_path)
    (repo.root / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (repo.root / ".pre-commit-config.yaml").write_text(_PRECOMMIT, encoding="utf-8")
    rules = engine_rules()
    request = GuardConfigRequest(
        repo_root=repo.root,
        hooks=resolve_engine_hooks(
            engine_hook_paths(), repo.root, rules=rules, facts=_FACTS, overlays=(regulated,)
        ),
        hooks_config=HooksConfig(enabled=True, auto_sync=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
        protected=ProtectInputs(
            rows_of(("AGENTS.md", "composite", "", ""), (".claude/rules/x.md", "rule", "tdd", "p")),
            (),
            ("coding_agent_playbook", "acme_rules"),
        ),
        detect=DetectInputs(facts=_FACTS),
        prompts=engine_prompts(),
        rules=rules,
    )
    written = compile_guard_config(request)
    written.write(repo.root)
    repo.write_lock(hashlib.sha256(written.data).hexdigest())
    return repo, written


@pytest.mark.catalog
def test_compiled_config_loads_and_every_table_reads_typed(compiled_repo: CompiledRepo) -> None:
    repo, written = compiled_repo

    cfg = load_guard_config(repo.repo, None, platform="linux", home=None)

    assert isinstance(cfg, GuardConfig), cfg
    assert sorted(cfg.hooks) == sorted(engine_hook_paths())  # every engine hook is on
    tables = cfg.tables
    assert tables.ruff() == RuffTable(
        project_select=("E", "I", "UP"),
        project_ignore=("UP007",),
        safe_fix_select=("I", "UP"),
        safe_fix_ignore=("UP007",),
    )
    assert tables.precommit_hook_ids() == ("playbook-metrics", "playbook-validate")
    assert tables.protected() == ProtectedTable(
        hook_artifacts=(
            ".coding-agent-playbook/hooks/",
            ".claude/hooks/playbook/",
            ".opencode/plugins/playbook-hooks.js",
        ),
        resource_roots=("pkg:coding_agent_playbook/resources", "pkg:acme_rules/resources"),
        artifact_ids=frozenset({"tdd"}),
    )
    gate = tables.stop_gate()
    assert gate.stage_rows == tuple(written.document["stop_gate"]["stages"])
    assert {"drift", "lint", "verify-claim", "coverage"} <= {stage.name for stage in gate.stages}
    assert [command.id for command in gate.verify_commands] == [
        "lint",
        "format",
        "typecheck",
        "tests",
    ]
    assert (gate.budget_s, gate.max_blocks) == (3.0, 2)
    assert {"review-core", "find-injected-vulnerability"} <= set(
        tables.prompts_with_output_contract()
    )
    assert tables.prompt_output_contract("review-core")  # the engine review prompt has one
    assert (tables.auto_sync(), tables.network_mode()) == (True, "enforce")
    facts = tables.facts()
    assert facts is not None and (facts["package_manager"], facts["has_notebooks"]) == ("uv", True)
    assert tables.applicability() == ()  # the request carries no applicability rows
    assert tables.notebook_max_bytes(1) == 5 * 1024 * 1024
    assert tables.eval_fixture_globs(()) == ("**/eval_samples/*/setup/**",)
    assert tables.secret_path_exempt(()) == SECRET_PATH_EXEMPT  # no [guardrails] allow_paths
    assert tables.secret_glob_exempt({}) == SECRET_GLOB_EXEMPT


def test_written_schema_version_is_supported_by_the_runtime(tmp_path: Path) -> None:
    request = GuardConfigRequest(
        repo_root=tmp_path,
        hooks=(),
        hooks_config=HooksConfig(enabled=True),
        guardrails=GuardrailsConfig(),
        engine_version="0.2.0",
    )

    version = compile_guard_config(request).document["schema_version"]

    assert SUPPORTED_SCHEMA_VERSIONS[0] <= version <= SUPPORTED_SCHEMA_VERSIONS[1]
