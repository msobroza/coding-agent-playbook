"""The sync-level ``guard_config.json`` and copied hook scripts (specs/prK-lifecycle-hooks.md §C.0, §D.8).

``playbook sync`` (not an adapter: an OpenCode-only repo needs it too, and the
OpenCode adapter may not write under ``.claude/``) writes two kinds of runtime
output under :data:`HOOKS_OUTPUT_DIR` whenever ``[hooks] enabled`` and a
hook-capable adapter is on:

- ``guard_config.json``, the dispatcher's only configuration: the envelope, every
  on hook as ``ResolvedHook.to_json()``, the §D.4 deadlines and the K3 runtime
  tables. Canonical bytes (sorted keys, compact, ASCII, one trailing newline),
  so its digest is the sha256 of the file the lockfile records (§D.8.1);
- byte copies (``shutil.copy2``, exec bits kept) of each external handler's
  ``scripts/``, which the hook's argv names repo-relatively.

Both are committed and byte-compared by ``sync --check`` on every machine, so
nothing here may read the machine: no absolute path, no ``sys.prefix``, no
``$HOME`` (§D.8.3). Absolute tool and interpreter paths are pins under the git
dir instead (``hook_runtime.config.pin``). The §E.0.5 pack tables land with K5: the
``sentinel`` and ``protected`` tables are built by ``_guard_config_protect``;
``control_plane`` is the runtime's own engine constant and ``precommit`` the
playbook hook ids of the repo's ``.pre-commit-config.yaml``, scanned with the
runtime's regex so control-plane-guard and sync never disagree; ``facts`` and
``applicability`` (resync-on-detector-input-change) come from
``_guard_config_detect``, ``eval`` is the fixture-glob engine constant and
``auto_sync`` mirrors ``[hooks] auto_sync``. ``stop_gate`` (K6) is the Stop
coordinator's table from ``hook_registrations.stop_gate``: its stage records,
budget and verify commands, also machine-independent; ``prompts`` and the
tests-with-source-nudge layout come from ``_guard_config_verify``. ``ruff`` (K7) is the
repo's own ruff selection and the safe-fix rules the post-edit pipeline may
apply (``_guard_config_ruff``); the pinned ruff's version-specific facts live
in ``machine.json`` instead. toolchain-missing-hint's install hint and
pytest-conventions-feedback's asyncio flag are derived from the repo's
pyproject into those hooks' config (``_guard_config_toolchain``), and the
quality companion's codes and ``--config`` thresholds from the committed
``[metrics.ruff_violations]`` into clean-code-metrics-nonregression's
(``_guard_config_quality``, §F.2.2); ``[hooks.commit_convention] cutover_date``
into commit-message-convention's (§F.4.2: one source for the push scan and the
``playbook ci`` step); skill-nudge's per-skill globs from the rendered member
rules (``_guard_config_skills``, specs/prS-skills-context.md 8.5.2).
``notebooks.max_bytes`` is the engine's parse cap for a notebook (a larger
one is reported unparsed), shared by the notebook-reading hooks. The K8
secret tables (``secret_path_exempt``, ``secret_glob_exempt``,
``secret_rules``) come from ``_guard_config_secrets``: the exemptions beside
``secret_path_globs`` and the content ruleset with its overlay patterns; the
``allowlists`` table (dependency allowlist, required index, egress hosts) and
the ``network`` table (network-egress-guard's mode, for the briefing) from
``_guard_config_allowlists``.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Final

from coding_agent_playbook._guard_config_allowlists import allowlists_table, network_table
from coding_agent_playbook._guard_config_detect import (
    DetectInputs,
    applicability_rows,
    applicability_table,
    facts_table,
)
from coding_agent_playbook._guard_config_prompts import prompt_scopes, with_prompt_scopes
from coding_agent_playbook._guard_config_protect import (
    ProtectedRow,
    ProtectInputs,
    adapter_output_dirs,
    protected_rows,
    protected_table,
    resolve_resource_roots,
    resource_root_ids,
)
from coding_agent_playbook._guard_config_quality import (
    QUALITY_HOOK_ID,
    QualityLint,
    quality_hook_config,
)
from coding_agent_playbook._guard_config_ruff import RuffSelection, ruff_table
from coding_agent_playbook._guard_config_secrets import secret_tables
from coding_agent_playbook._guard_config_skills import SKILL_NUDGE_HOOK_ID
from coding_agent_playbook._guard_config_toolchain import (
    ToolchainInputs,
    derived_hook_config,
    with_derived_config,
)
from coding_agent_playbook._guard_config_verify import (
    RepoLayout,
    bake_layout,
    prompts_table,
    repo_layout,
)
from coding_agent_playbook.adapters._skill_sources import copyable_skill_files
from coding_agent_playbook.generated_output.output_io import copy_output, write_output_bytes
from coding_agent_playbook.generated_output.sentinel import SENTINEL
from coding_agent_playbook.hook_policy import HOOK_SCRIPTS_DIR
from coding_agent_playbook.hook_registrations import (
    LAUNCHER_PATH,
    OPENCODE_SHIM_PATH,
    resolved_deadlines_ms,
    stop_gate_table,
)
from coding_agent_playbook.hook_runtime.config.guard_config import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.handlers._control_plane_paths import CONTROL_PLANE
from coding_agent_playbook.hook_runtime.handlers._control_plane_text import (
    playbook_precommit_ids,
)
from coding_agent_playbook.hook_runtime.handlers._eval_paths import FIXTURE_GLOBS
from coding_agent_playbook.hook_runtime.judges.notebook_check import NOTEBOOK_MAX_BYTES
from coding_agent_playbook.hook_runtime.routing import ASYNC_AUDIT_MODE, ASYNC_EVENT, handler_route
from coding_agent_playbook.hook_runtime.shell.wrappers import DEFAULT_RUNNER_WRAPPERS
from coding_agent_playbook.security.patterns import SECRET_PATH_GLOBS

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence
    from pathlib import Path

    from coding_agent_playbook._guard_config_skills import SkillGlobRow
    from coding_agent_playbook.artifacts.prompt import Prompt
    from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
    from coding_agent_playbook.hook_policy import ResolvedHook

__all__ = [
    "GUARD_CONFIG_PATH",
    "GUARD_CONFIG_SCHEMA",
    "HOOKS_OUTPUT_DIR",
    "HOOK_ARTIFACTS",
    "SYNC_OUTPUT_LOCATIONS",
    "CopiedScripts",
    "DetectInputs",
    "GuardConfigInputs",
    "ProtectInputs",
    "ProtectedRow",
    "RepoLayout",
    "RuffSelection",
    "adapter_output_dirs",
    "applicability_rows",
    "copy_hook_scripts",
    "precommit_hook_ids",
    "protected_rows",
    "render_guard_config",
    "repo_layout",
    "resolve_resource_roots",
    "resource_root_ids",
    "serialize_guard_config",
    "write_guard_config",
]

#: The one repo-relative path, shared with the runtime that reads it.
GUARD_CONFIG_PATH: Final = GUARD_CONFIG_REL
#: ``hook_runtime.config.guard_config.SUPPORTED_SCHEMA_VERSIONS`` must include it.
GUARD_CONFIG_SCHEMA: Final = 1
#: guard_config.json plus the copied scripts; protected as a whole tree (§E.1).
HOOKS_OUTPUT_DIR: Final = ".coding-agent-playbook/hooks/"
#: Joins the adapters' ``output_locations`` in the leftover policy, so disabling
#: hooks deletes the pristine sync-level outputs (no adapter declares them).
SYNC_OUTPUT_LOCATIONS: Final[tuple[str, ...]] = (HOOKS_OUTPUT_DIR,)
#: The guardrail files only the user may change (runtime glob grammar): the
#: sync-level outputs, the Claude launcher dir and the OpenCode shim (§E.1).
HOOK_ARTIFACTS: Final[tuple[str, ...]] = (
    HOOKS_OUTPUT_DIR,
    f"{LAUNCHER_PATH.rsplit('/', 1)[0]}/",
    OPENCODE_SHIM_PATH,
)

#: The pre-commit config whose playbook hook ids control-plane-guard keeps (§E.1).
PRECOMMIT_CONFIG: Final = ".pre-commit-config.yaml"
#: Pre-commit configs are small; a larger one is not scanned.
_PRECOMMIT_MAX_BYTES: Final = 1024 * 1024

#: The hook whose push scan reads ``[hooks.commit_convention] cutover_date`` (§F.4.2).
COMMIT_CONVENTION_HOOK_ID: Final = "commit-message-convention"
#: The hooks whose presence switches the local logs on (§D.6.2, specs/prK-hook-pack.md §E.5).
_DECISION_LOG_HOOK: Final = "guard-decision-log"
_AUDIT_LOG_HOOK: Final = "local-audit-log"

#: Engine path classes (runtime glob grammar); ``generated`` comes from the adapters.
_PATH_CLASSES: Final[Mapping[str, tuple[str, ...]]] = {
    "canonical": ("playbook/",),
    "control_plane": (
        ".claude/settings.json",
        ".claude/settings.local.json",
        ".coding-agent-playbook.toml",
        ".coding-agent-playbook.local.toml",
        ".coding-agent-playbook.lock",
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


@dataclass(frozen=True)
class GuardConfigInputs:
    """Everything ``guard_config.json`` is rendered from; all of it machine-independent.

    ``generated`` holds the enabled adapters' ``output_locations``;
    ``protected`` the written set, scan dirs and layer packages;
    ``precommit_ids`` the repo's playbook pre-commit hook ids, ``detect``
    the detector facts and applicability rows (§E.0.5); ``prompts`` the
    rendered prompts: the ``prompts`` table of output contracts (§E.2) and,
    from their ``write_scope``, prompt-write-scope-guard's ``scopes`` (§E.3);
    ``layout`` the source and test roots baked into tests-with-source-nudge's
    config (§E.2); ``ruff`` the repo's ruff selection
    (``read_project_ruff_selection``); ``toolchain`` the hook config derived
    from its pyproject (``read_toolchain_inputs``: the install hint, pytest's
    asyncio marks); ``quality`` the committed ``[metrics.ruff_violations]``
    (``read_quality_lint``); ``skill_globs`` skill-nudge's table, one
    ``{"id", "globs"}`` row per skill (``skill_glob_rows`` of the rendered rules).

    Example::

        GuardConfigInputs(hooks, hooks_cfg, guardrails, "0.2.0", generated=("AGENTS.md",))
    """

    hooks: Sequence[ResolvedHook]
    hooks_config: HooksConfig
    guardrails: GuardrailsConfig
    engine_version: str
    generated: Sequence[str] = ()
    protected: ProtectInputs = field(default_factory=ProtectInputs)
    precommit_ids: Sequence[str] = ()
    detect: DetectInputs = field(default_factory=DetectInputs)
    prompts: Sequence[Prompt] = ()
    layout: RepoLayout = field(default_factory=RepoLayout)
    ruff: RuffSelection = field(default_factory=RuffSelection)
    toolchain: ToolchainInputs = field(default_factory=ToolchainInputs)
    quality: QualityLint = field(default_factory=QualityLint)
    # SkillGlobRow, not spec 8.5.2's Mapping[str, Any]: mypy then checks the
    # {"id", "globs"} shape the skill-nudge runtime parses.
    skill_globs: Sequence[SkillGlobRow] = ()


@dataclass(frozen=True)
class CopiedScripts:
    """The script copies of one external-handler hook, in sorted source order."""

    hook: ResolvedHook
    paths: tuple[Path, ...]


def render_guard_config(inputs: GuardConfigInputs) -> dict[str, Any]:
    """The ``guard_config.json`` document (§D.8.2): envelope, hooks, deadlines, K3/K5 tables.

    ``allow_code_from`` and ``state_ttl_days`` are the runtime keys beyond the
    §D.8.2 table that ``hook_runtime.config.guard_config`` reads (it cannot read ``[hooks]``);
    ``sentinel``, ``protected``, ``control_plane``, ``precommit``, ``facts``,
    ``applicability``, ``eval``, ``auto_sync``, ``stop_gate``, ``prompts``,
    ``ruff``, ``notebooks``, the §E.4 secret tables, ``allowlists`` and ``network`` are
    pack keys (``GuardConfig.tables``).

    Example::

        >>> render_guard_config(GuardConfigInputs([], HooksConfig(enabled=True),
        ...     GuardrailsConfig(), "0.2.0"))["hooks"]  # doctest: +SKIP
        {}
    """
    cfg = inputs.hooks_config
    scopes = prompt_scopes(inputs.prompts)
    derived = {
        **derived_hook_config(inputs.toolchain),
        QUALITY_HOOK_ID: quality_hook_config(inputs.quality, inputs.ruff),
        COMMIT_CONVENTION_HOOK_ID: {"cutover_date": cfg.commit_convention.cutover_date or ""},
        SKILL_NUDGE_HOOK_ID: {"skills": [dict(row) for row in inputs.skill_globs]},
    }
    return {
        "schema_version": GUARD_CONFIG_SCHEMA,
        "engine_version": inputs.engine_version,
        "hooks": {
            hook.id: bake_layout(
                with_derived_config(with_prompt_scopes(hook.to_json(), scopes), derived),
                inputs.layout,
            )
            for hook in inputs.hooks
        },
        "deadlines_ms": resolved_deadlines_ms(inputs.hooks),
        "unattended_ask": cfg.unattended_ask,
        "logging": _logging(inputs.hooks),
        "shell": {
            "wrapper_prefixes": list(cfg.wrapper_prefixes),
            "runner_wrappers": list(DEFAULT_RUNNER_WRAPPERS),
        },
        "path_classes": _path_classes(inputs.generated),
        "secret_path_globs": _unique([*SECRET_PATH_GLOBS, *inputs.guardrails.secrets.extra_globs]),
        "allow_code_from": sorted(set(cfg.allow_code_from)),
        "state_ttl_days": cfg.state_ttl_days,
        "sentinel": SENTINEL,
        "protected": protected_table(inputs.protected, HOOK_ARTIFACTS),
        "control_plane": {key: list(rows) for key, rows in CONTROL_PLANE.items()},
        "precommit": {"playbook_hook_ids": sorted(set(inputs.precommit_ids))},
        "facts": facts_table(inputs.detect.facts),
        "applicability": applicability_table(inputs.detect.applicability),
        "eval": {"fixture_globs": list(FIXTURE_GLOBS)},
        "auto_sync": cfg.auto_sync,
        "stop_gate": stop_gate_table(inputs.hooks, inputs.detect.facts),
        "prompts": prompts_table(inputs.prompts),
        "ruff": ruff_table(inputs.ruff),
        "notebooks": {"max_bytes": NOTEBOOK_MAX_BYTES},
        **secret_tables(inputs.hooks, inputs.guardrails),
        "allowlists": allowlists_table(inputs.hooks),
        "network": network_table(inputs.hooks),
    }


def precommit_hook_ids(repo_root: Path) -> list[str]:
    """The playbook hook ids of ``<repo_root>/.pre-commit-config.yaml`` (``[]`` without one).

    The runtime's own regex, never ``yaml``: control-plane-guard denies the
    removal of exactly these ids.

    Example::

        >>> precommit_hook_ids(Path("/no/such/repo"))
        []
    """
    try:
        with (repo_root / PRECOMMIT_CONFIG).open("rb") as handle:
            data = handle.read(_PRECOMMIT_MAX_BYTES + 1)
    except OSError:
        return []
    if len(data) > _PRECOMMIT_MAX_BYTES:
        return []
    return playbook_precommit_ids(data.decode("utf-8", errors="replace"))


def serialize_guard_config(cfg: Mapping[str, Any]) -> bytes:
    """Canonical bytes: sorted keys, no whitespace, ASCII escapes, one trailing newline (§D.8.1).

    Example::

        >>> serialize_guard_config({"b": 1, "a": "é"})
        b'{"a":"\\\\u00e9","b":1}\\n'
    """
    text = json.dumps(cfg, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return f"{text}\n".encode("ascii")


def write_guard_config(out_root: Path, cfg: Mapping[str, Any]) -> Path:
    """Write ``cfg``'s canonical bytes to ``<out_root>/<GUARD_CONFIG_PATH>``; return the path.

    Bytes, not text, so Windows never turns the newline into CRLF.

    Example: ``write_guard_config(repo_root, render_guard_config(inputs))``.
    """
    path = out_root / GUARD_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    write_output_bytes(path, serialize_guard_config(cfg))
    return path


def copy_hook_scripts(hooks: Iterable[ResolvedHook], out_root: Path) -> list[CopiedScripts]:
    """Byte-copy each external handler's ``scripts/`` to ``<HOOK_SCRIPTS_DIR>/<id>/``, by hook id.

    Copies are ``shutil.copy2`` (bytes and mode, so the exec bit survives),
    never symlinks. A secret path or a link leaving the hook directory is never
    copied, only warned about (the skills rule, SPEC §17.3). Hooks with only
    builtin handlers have nothing to copy.

    Example::

        for copy in copy_hook_scripts(hooks, repo_root):
            recorder.record(copy.paths, Provenance(kind="hook", artifact_id=copy.hook.id))
    """
    copies: list[CopiedScripts] = []
    for hook in sorted(hooks, key=lambda h: h.id):
        scripts = None if hook.definition is None else hook.definition.scripts_dir
        if scripts is None or not _runs_a_script(hook):
            continue
        dst_root = out_root / HOOK_SCRIPTS_DIR / hook.id
        paths = tuple(
            _copy(src, dst_root / src.relative_to(scripts))
            for src in copyable_skill_files(scripts, dst_root)
        )
        copies.append(CopiedScripts(hook, paths))
    return copies


def _copy(src: Path, dst: Path) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    return copy_output(src, dst)


def _runs_a_script(hook: ResolvedHook) -> bool:
    return any(handler.kind == "external" for handler in hook.handlers.values())


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
