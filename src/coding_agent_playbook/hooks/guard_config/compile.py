"""Compile ``guard_config.json``, the hook runtime's only configuration, from what sync owns.

``playbook sync`` compiles it whenever ``[hooks] enabled`` and a hook-capable adapter is
on (specs/prK-lifecycle-hooks.md §C.0, §D.8): sync, not an adapter, because an
OpenCode-only repo needs it too and the OpenCode adapter may not write under ``.claude/``.
Sync hands over a :class:`GuardConfigRequest` holding only what sync computes; each
input kept in a repository file is read from ``repo_root`` (``_repo_inputs``,
specs/prT-package-layout.md 9 AC.2.3), the real repo in every mode, so ``sync --check``
writes the same bytes into its scratch dir. The document is the envelope the runtime
parses itself, every on hook as ``ResolvedHook.to_json()`` with the config sync derives
for it (the repo layout, the toolchain hints, the quality family, the commit cutover,
skill-nudge's globs), the §D.4 deadlines and the §E.0.5 pack tables, one ``_tables_*``
module each. Its bytes are canonical (sorted keys, compact, ASCII, one trailing newline),
so their digest is the sha256 the lockfile records (§D.8.1). It is committed and
byte-compared on every machine, so nothing here may read the machine: no absolute path,
no ``sys.prefix``, no ``$HOME`` (§D.8.3); tool and interpreter paths are pins under the
git dir (``hook_runtime.config.pin``). The script copies are sync's (``sync._hook_scripts``).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook.artifacts.path_classes import FIXTURE_GLOBS
from coding_agent_playbook.generated_output.output_io import write_output_bytes
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.hook_runtime.config.schema import (
    CONTROL_PLANE,
    GUARD_CONFIG_REL,
    GUARD_CONFIG_SCHEMA_VERSION,
    HOOKS_OUTPUT_DIR,
    LOCKFILE_REL,
)
from coding_agent_playbook.hook_runtime.dispatch.routing import (
    ASYNC_AUDIT_MODE,
    ASYNC_EVENT,
    handler_route,
)
from coding_agent_playbook.hook_runtime.judges.notebook_check import NOTEBOOK_MAX_BYTES
from coding_agent_playbook.hook_runtime.shell.wrappers import DEFAULT_RUNNER_WRAPPERS
from coding_agent_playbook.hooks.guard_config._repo_inputs import RepoInputs, read_repo_inputs
from coding_agent_playbook.hooks.guard_config._tables_allowlists import (
    allowlists_table,
    network_table,
)
from coding_agent_playbook.hooks.guard_config._tables_detect import applicability_table, facts_table
from coding_agent_playbook.hooks.guard_config._tables_prompts import (
    prompt_scopes,
    with_prompt_scopes,
)
from coding_agent_playbook.hooks.guard_config._tables_protect import protected_table
from coding_agent_playbook.hooks.guard_config._tables_quality import (
    QUALITY_HOOK_ID,
    quality_hook_config,
)
from coding_agent_playbook.hooks.guard_config._tables_ruff import ruff_table
from coding_agent_playbook.hooks.guard_config._tables_secrets import secret_tables
from coding_agent_playbook.hooks.guard_config._tables_skills import (
    SKILL_NUDGE_HOOK_ID,
    skill_glob_rows,
)
from coding_agent_playbook.hooks.guard_config._tables_stop_gate import stop_gate_table
from coding_agent_playbook.hooks.guard_config._tables_toolchain import (
    derived_hook_config,
    with_derived_config,
)
from coding_agent_playbook.hooks.guard_config._tables_verify import bake_layout, prompts_table
from coding_agent_playbook.hooks.guard_config.inputs import DetectInputs, ProtectInputs
from coding_agent_playbook.hooks.registrations.launcher import LAUNCHER_PATH
from coding_agent_playbook.hooks.registrations.opencode import OPENCODE_SHIM_PATH
from coding_agent_playbook.hooks.registrations.plan import resolved_deadlines_ms
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.artifacts.rule import Rule
    from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

__all__ = [
    "HOOK_ARTIFACTS",
    "SYNC_OUTPUT_LOCATIONS",
    "CompiledGuardConfig",
    "GuardConfigRequest",
    "compile_guard_config",
    "serialize_guard_config",
]

#: guard_config.json plus the copied hook scripts; joins the adapters' ``output_locations``
#: in the leftover policy, so disabling hooks deletes these pristine outputs too.
SYNC_OUTPUT_LOCATIONS: Final[tuple[str, ...]] = (HOOKS_OUTPUT_DIR,)
#: The guardrail files only the user may change (runtime glob grammar): the
#: sync-level outputs, the Claude launcher dir and the OpenCode shim (§E.1).
HOOK_ARTIFACTS: Final[tuple[str, ...]] = (
    HOOKS_OUTPUT_DIR,
    f"{LAUNCHER_PATH.rsplit('/', 1)[0]}/",
    OPENCODE_SHIM_PATH,
)

#: The hook whose push scan reads ``[hooks.commit_convention] cutover_date`` (§F.4.2).
COMMIT_CONVENTION_HOOK_ID: Final = "commit-message-convention"
#: The hooks whose presence switches the local logs on (§D.6.2, specs/prK-hook-pack.md §E.5).
_DECISION_LOG_HOOK: Final = "guard-decision-log"
_AUDIT_LOG_HOOK: Final = "local-audit-log"

#: Engine path classes (runtime glob grammar); ``generated`` comes from the adapters.
#: The control-plane files are the runtime's own rows (it owns the contract, GC-D4).
_PATH_CLASSES: Final[Mapping[str, tuple[str, ...]]] = {
    "canonical": ("playbook/",),
    "control_plane": (
        *CONTROL_PLANE["settings"],
        *CONTROL_PLANE["config"],
        *CONTROL_PLANE["local_config"],
        LOCKFILE_REL,
        HOOKS_OUTPUT_DIR,
    ),
    "detector_input": (
        "pyproject.toml",
        "uv.lock",
        "poetry.lock",
        "requirements.txt",
        "requirements.in",
        ".pre-commit-config.yaml",
    ),
    "eval_fixture": FIXTURE_GLOBS,
    "notebook": ("*.ipynb",),
    "py": ("*.py",),
    "test": ("tests/", "test_*.py", "*_test.py", "conftest.py"),
}


@dataclass(frozen=True, slots=True, kw_only=True)
class GuardConfigRequest:
    """What sync owns and hands the writer; every other input is read from ``repo_root``.

    ``repo_root`` is the real repository in every mode: ``sync --check`` writes into
    a scratch directory but reads the repo's own pyproject, ruff config, pre-commit
    config and committed config. ``generated`` holds the adapters' ``output_locations``,
    ``protected`` the written set, scan dirs and layer packages, ``detect`` the facts
    and applicability rows; ``rules`` and ``prompts`` are this sync's rendered,
    ``applies_if``-filtered artifacts.

    Example: ``GuardConfigRequest(repo_root=repo, hooks=hooks.resolved,
    hooks_config=hooks.config, guardrails=hooks.guardrails, engine_version="0.2.0")``.
    """

    repo_root: Path
    hooks: Sequence[ResolvedHook]
    hooks_config: HooksConfig
    guardrails: GuardrailsConfig
    engine_version: str
    generated: Sequence[str] = ()
    protected: ProtectInputs = field(default_factory=ProtectInputs)
    detect: DetectInputs = field(default_factory=DetectInputs)
    prompts: Sequence[Prompt] = ()
    rules: Sequence[Rule] = ()


@dataclass(frozen=True, slots=True)
class CompiledGuardConfig:
    """The guard_config.json document and its canonical bytes (``serialize_guard_config``)."""

    document: Mapping[str, Any]
    data: bytes

    def write(self, out_root: Path) -> Path:
        """Write ``data`` to ``<out_root>/<GUARD_CONFIG_REL>`` (bytes, never CRLF); return the path.

        Example: ``compile_guard_config(request).write(scratch_root)``.
        """
        path = out_root / GUARD_CONFIG_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        write_output_bytes(path, self.data)
        return path


def compile_guard_config(request: GuardConfigRequest) -> CompiledGuardConfig:
    """Read the repo inputs, build every table, serialize canonically. Writes nothing.

    An unreadable repo input gives its reader's default (GC-D5); a template or
    policy error was raised earlier, by sync's render and hook resolution.

    Example: ``compile_guard_config(request).write(out_root)``.
    """
    repo = read_repo_inputs(request.repo_root, request.detect.facts)
    document = {
        **_envelope(request),
        "hooks": _hook_records(request, repo),
        **_pack_tables(request, repo),
    }
    return CompiledGuardConfig(document, serialize_guard_config(document))


def serialize_guard_config(document: Mapping[str, Any]) -> bytes:
    """Canonical bytes: sorted keys, no whitespace, ASCII escapes, one trailing newline (§D.8.1).

    Example::

        >>> serialize_guard_config({"b": 1, "a": "é"})
        b'{"a":"\\\\u00e9","b":1}\\n'
    """
    text = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{text}\n".encode("ascii")


def _envelope(request: GuardConfigRequest) -> dict[str, Any]:
    """The keys ``hook_runtime.config.guard_config`` parses itself (§D.8.2); the runtime
    cannot read ``[hooks]``, so ``allow_code_from`` and ``state_ttl_days`` join them."""
    cfg = request.hooks_config
    return {
        "schema_version": GUARD_CONFIG_SCHEMA_VERSION,
        "engine_version": request.engine_version,
        "deadlines_ms": resolved_deadlines_ms(request.hooks),
        "unattended_ask": cfg.unattended_ask,
        "logging": _logging(request.hooks),
        "shell": {
            "wrapper_prefixes": list(cfg.wrapper_prefixes),
            "runner_wrappers": list(DEFAULT_RUNNER_WRAPPERS),
        },
        "path_classes": _path_classes(request.generated),
        "secret_path_globs": _unique([*SECRET_PATH_GLOBS, *request.guardrails.secrets.extra_globs]),
        "allow_code_from": sorted(set(cfg.allow_code_from)),
        "state_ttl_days": cfg.state_ttl_days,
    }


def _hook_records(request: GuardConfigRequest, repo: RepoInputs) -> dict[str, Any]:
    """Each on hook's record with the config sync derives for it merged into its handlers."""
    cutover = request.hooks_config.commit_convention.cutover_date or ""
    derived = {
        **derived_hook_config(repo.toolchain),
        QUALITY_HOOK_ID: quality_hook_config(repo.quality, repo.ruff),
        COMMIT_CONVENTION_HOOK_ID: {"cutover_date": cutover},
        SKILL_NUDGE_HOOK_ID: {"skills": [dict(row) for row in skill_glob_rows(request.rules)]},
    }
    scopes = prompt_scopes(request.prompts)
    return {
        hook.id: bake_layout(
            with_derived_config(with_prompt_scopes(hook.to_json(), scopes), derived), repo.layout
        )
        for hook in request.hooks
    }


def _pack_tables(request: GuardConfigRequest, repo: RepoInputs) -> dict[str, Any]:
    """The pack keys the runtime reads through ``GuardConfig.tables`` (§E.0.5)."""
    hooks, facts = request.hooks, request.detect.facts
    return {
        "sentinel": SENTINEL,
        "protected": protected_table(request.protected, HOOK_ARTIFACTS),
        "control_plane": {key: list(rows) for key, rows in CONTROL_PLANE.items()},
        "precommit": {"playbook_hook_ids": sorted(set(repo.precommit_ids))},
        "facts": facts_table(facts),
        "applicability": applicability_table(request.detect.applicability),
        "eval": {"fixture_globs": list(FIXTURE_GLOBS)},
        "auto_sync": request.hooks_config.auto_sync,
        "stop_gate": stop_gate_table(hooks, facts),
        "prompts": prompts_table(request.prompts),
        "ruff": ruff_table(repo.ruff),
        "notebooks": {"max_bytes": NOTEBOOK_MAX_BYTES},
        **secret_tables(hooks, request.guardrails),
        "allowlists": allowlists_table(hooks),
        "network": network_table(hooks),
    }


def _logging(hooks: Sequence[ResolvedHook]) -> dict[str, Any]:
    """``logging``: which local logs are on, and whether an async audit route is rendered.

    ``audit_mode = "async"`` tells the synchronous ``post_tool_use`` dispatch to
    skip the async-routed handlers, which the one async registration runs (OQ-19).
    """
    on = {hook.id for hook in hooks}
    routed_async = any(
        handler_route(ASYNC_EVENT, kind=handler.kind, name=handler.name, decisions=hook.decisions)
        == "async"
        for hook in hooks
        if (handler := hook.handlers.get(ASYNC_EVENT)) is not None
    )
    return {
        "decisions": _DECISION_LOG_HOOK in on,
        "audit": _AUDIT_LOG_HOOK in on,
        "audit_mode": ASYNC_AUDIT_MODE if routed_async else "",
    }


def _path_classes(generated: Iterable[str]) -> dict[str, list[str]]:
    classes = {name: list(globs) for name, globs in _PATH_CLASSES.items()}
    classes["generated"] = sorted({*generated, *SYNC_OUTPUT_LOCATIONS})
    return classes


def _unique(items: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(items))
