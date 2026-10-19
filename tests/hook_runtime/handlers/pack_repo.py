"""A synced repository with engine pack hooks on, for the §E hook tests (specs/prK-hook-pack.md §E.0.7).

:class:`PackRepo` writes what ``playbook sync`` would for the hooks under test:
the engine's own ``HOOK.md`` resolved through the real effective view, a
``guard_config.json`` from the real ``render_guard_config`` (so the §E.0.5
tables are the rendered ones), and the lockfile entry vouching for it. Tests
then drive the exact dispatch pipeline through ``simulate.run`` with golden
payloads relocated into the repository.

An overlay layer is optional: :func:`install_fixture_overlay` turns the data
under ``tests/fixtures/overlays/<name>/`` into an importable overlay package,
and ``overlays=`` merges its same-id definitions over the engine's through the
real §A.6 layer merge (specs/prK-hook-pack.md §E.5: overlay activation).
"""

from __future__ import annotations

import dataclasses
import hashlib
import importlib
import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from coding_agent_playbook._guard_config_quality import read_quality_lint
from coding_agent_playbook._guard_config_ruff import read_project_ruff_selection
from coding_agent_playbook._guard_config_skills import skill_glob_rows
from coding_agent_playbook._guard_config_toolchain import read_toolchain_inputs
from coding_agent_playbook.adapters.agents_md import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code.adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_ import ContinueAdapter
from coding_agent_playbook.adapters.opencode import OpenCodeAdapter
from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.config.files import FileSystemStateSource
from coding_agent_playbook.config.tables.hooks import GuardrailsConfig, HooksConfig
from coding_agent_playbook.guard_config import (
    DetectInputs,
    GuardConfigInputs,
    ProtectedRow,
    ProtectInputs,
    adapter_output_dirs,
    render_guard_config,
    repo_layout,
    serialize_guard_config,
)
from coding_agent_playbook.hook_policy import RegistryCatalog, resolve_effective_hooks
from coding_agent_playbook.hook_policy.merge import merge_hook_layers
from coding_agent_playbook.hook_runtime.config import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.simulate import SimulateArgs, run
from coding_agent_playbook.lockfile.model import LockEntry, Lockfile, compute_hash
from tests._catalog import CORE_ROOT
from tests.hook_payloads import PROJECT_DIR, HookPayloadCase
from tests.hook_runtime.guard_repo import GuardRepo

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from coding_agent_playbook.detector.facts import Facts
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport
    from tests.hook_runtime.fakes import FakeProc

ENGINE_PACKAGE = "coding_agent_playbook"
ENGINE_HOOKS = CORE_ROOT / "hooks"
#: Data-only overlay trees (``<name>/resources/hooks/...``), copied into a package per test.
# A13 moved this file one directory level deeper, into tests/hook_runtime/handlers/,
# so parents[2] (was .parent.parent) is still tests/.
FIXTURE_OVERLAYS = Path(__file__).resolve().parents[2] / "fixtures" / "overlays"
#: Every enabled adapter of the fixture consumer.
ADAPTERS = ("claude_code", "continue", "opencode", "agents_md")
#: The fixture engine version and sync time :meth:`PackRepo.lock_outputs` records.
ENGINE_VERSION = "0.1.0a0"
RENDERED_AT = "2026-10-14T10:00:00Z"


def engine_hook_paths() -> dict[str, Path]:
    """Every engine ``HOOK.md`` by hook id (its directory name)."""
    return {path.parent.name: path for path in sorted(ENGINE_HOOKS.rglob("HOOK.md"))}


def engine_hook(hook_id: str) -> Hook:
    """The engine's shipped definition of ``hook_id``."""
    return Hook.from_markdown(engine_hook_paths()[hook_id], ENGINE_PACKAGE)


def install_fixture_overlay(make_package: Callable[..., str], name: str, package: str) -> str:
    """Copy ``tests/fixtures/overlays/<name>/resources`` into importable package ``package``.

    ``make_package`` is the root conftest fixture; the package lives for one test.
    Returns ``package``.
    """
    make_package(package, resources=True)
    shutil.copytree(FIXTURE_OVERLAYS / name / "resources", _resources(package), dirs_exist_ok=True)
    return package


def overlay_hook_paths(package: str) -> dict[str, Path]:
    """Every ``HOOK.md`` overlay ``package`` ships, by hook id (its directory name)."""
    root = _resources(package) / "hooks"
    return {path.parent.name: path for path in sorted(root.rglob("HOOK.md"))}


def layered_hook(hook_id: str, overlays: Sequence[str] = ()) -> Hook:
    """The engine's ``hook_id`` with each overlay's same-id definition merged over it (§A.6).

    Raises ``ValueError`` naming the first layer violation (H2/H14/H15).
    """
    definitions = [engine_hook(hook_id)]
    for package in overlays:
        path = overlay_hook_paths(package).get(hook_id)
        if path is not None:
            definitions.append(Hook.from_markdown(path, package))
    merged, violations = merge_hook_layers(definitions, schemas=RegistryCatalog())
    if violations:
        raise ValueError(f"overlay merge of {hook_id!r} refused: {violations[0].message}")
    return merged


def _resources(package: str) -> Path:
    module_file = importlib.import_module(package).__file__
    assert module_file is not None
    return Path(module_file).parent / "resources"


def engine_prompts() -> list[Prompt]:
    """Every engine prompt as shipped (frontmatter as authored, body unrendered)."""
    root = CORE_ROOT / "prompts"
    paths = sorted(p for p in root.iterdir() if p.name.endswith((".md", ".md.j2")))
    return [Prompt.from_markdown(path, ENGINE_PACKAGE) for path in paths]


def engine_rules() -> list[Rule]:
    """Every engine rule as shipped (the linked rules of the §E.3 lint hooks among them)."""
    root = ENGINE_HOOKS.parent / "rules"
    paths = sorted(p for p in root.rglob("*") if p.name.endswith((".md", ".md.j2")))
    return [Rule.from_markdown(path, ENGINE_PACKAGE) for path in paths]


def resolve_engine_hooks(
    hook_ids: Iterable[str],
    root: Path,
    *,
    per_hook: Mapping[str, dict[str, Any]] | None = None,
    rules: Sequence[Rule] = (),
    facts: Mapping[str, Any] | None = None,
    overlays: Sequence[str] = (),
) -> list[ResolvedHook]:
    """The engine hooks ``hook_ids`` through the real effective view, ``[hooks]`` on.

    ``rules`` are the merged rules a ``linked_rule`` resolves against (its
    ``applies_if`` gate and ``lint_codes``), ``facts`` the detector facts,
    ``overlays`` the overlay packages layered over the engine (:func:`layered_hook`).
    """
    view = resolve_effective_hooks(
        [layered_hook(hook_id, overlays) for hook_id in hook_ids],
        list(rules),
        HooksConfig(enabled=True, tiers=("default", "opt-in"), per_hook=dict(per_hook or {})),
        GuardrailsConfig(),
        cast("Facts", dict(facts or {})),
        root,
        adapters_enabled=["claude_code", "opencode"],
        handlers=RegistryCatalog(),
    )
    return list(view.resolved)


def fixture_output_dirs(root: Path) -> list[str]:
    """The scan dirs of the four fixture adapters, as sync renders them."""
    adapters = {
        "claude_code": ClaudeCodeAdapter(),
        "continue": ContinueAdapter(),
        "opencode": OpenCodeAdapter(),
        "agents_md": AgentsMdAdapter(),
    }
    return adapter_output_dirs(adapters, root)


@dataclass
class PackRepo(GuardRepo):
    """A :class:`GuardRepo` whose ``guard_config.json`` holds real engine pack hooks."""

    @classmethod
    def create(cls, tmp_path: Path) -> PackRepo:
        base = GuardRepo.create(tmp_path)
        return cls(base.root)

    def write(self, rel: str, text: str = "x\n") -> Path:
        """Write ``rel`` (parents created) and return its path."""
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def install_pack(
        self,
        hook_ids: Sequence[str],
        *,
        rows: Sequence[ProtectedRow] = (),
        packages: Sequence[str] = (ENGINE_PACKAGE,),
        per_hook: Mapping[str, dict[str, Any]] | None = None,
        auto_sync: bool = False,
        detect: DetectInputs | None = None,
        prompts: Sequence[Prompt] = (),
        precommit_ids: Sequence[str] = (),
        wrapper_prefixes: Sequence[str] = (),
        rules: Sequence[Rule] = (),
        extra_tables: Mapping[str, Any] | None = None,
        handler_config: Mapping[str, Mapping[str, Any]] | None = None,
        overlays: Sequence[str] = (),
    ) -> bytes:
        """Render ``guard_config.json`` for the engine hooks ``hook_ids``; vouch for it in the lock.

        The decision log is switched on (guard-decision-log would, K9), so a test
        can read what the dispatch recorded, e.g. that canary lines are tagged.
        ``auto_sync`` is ``[hooks] auto_sync``; ``detect`` the facts and rows
        (its facts also resolve ``applies_if`` and a linked rule's ``lint_codes``);
        ``prompts`` the rendered prompts (the ``prompts`` table and their
        ``write_scope``, §E.2/§E.3); ``precommit_ids`` the repo's playbook
        pre-commit ids; ``wrapper_prefixes`` ``[hooks] wrapper_prefixes``;
        ``rules`` the rules a ``linked_rule`` names, and the rendered rules whose
        member globs become skill-nudge's ``skills`` table. The layout (source and test
        roots), the ``ruff`` table, the toolchain inputs and the committed
        ``[metrics.ruff_violations]`` are read from the repository, as sync does; ``extra_tables`` replace top-level tables
        (e.g. a ``stop_gate`` with a typecheck stage). ``handler_config`` sets
        keys of a hook's rendered handler configs outright, as a repo-local
        override would (no strictest merge: e.g. stop-diff-sweep's ``mode = warn``).
        ``overlays`` are overlay packages layered over the engine definitions
        (an overlay-tier hook is on only when one of them activates it).
        """
        detect = detect or DetectInputs()
        hooks = resolve_engine_hooks(
            hook_ids,
            self.root,
            per_hook=per_hook,
            rules=rules,
            facts=detect.facts,
            overlays=overlays,
        )
        protect = ProtectInputs(rows, fixture_output_dirs(self.root), packages)
        inputs = GuardConfigInputs(
            hooks=hooks,
            hooks_config=HooksConfig(
                enabled=True, auto_sync=auto_sync, wrapper_prefixes=tuple(wrapper_prefixes)
            ),
            guardrails=GuardrailsConfig(),
            engine_version="0.1.0a0",
            protected=protect,
            detect=detect,
            prompts=prompts,
            precommit_ids=precommit_ids,
            layout=repo_layout(self.root),
            ruff=read_project_ruff_selection(self.root),
            toolchain=read_toolchain_inputs(self.root, detect.facts),
            quality=read_quality_lint(self.root),
            skill_globs=skill_glob_rows(rules),
        )
        document = render_guard_config(inputs)
        document.update(extra_tables or {})
        for hook_id, keys in (handler_config or {}).items():
            for handler in document["hooks"][hook_id]["handlers"].values():
                handler["config"].update(keys)
        document["logging"]["decisions"] = True
        data = serialize_guard_config(document)
        path = self.root / GUARD_CONFIG_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.write_lock(hashlib.sha256(data).hexdigest())
        return data

    def lock_outputs(
        self,
        *rels: str,
        engine_version: str = ENGINE_VERSION,
        rendered_at: str = RENDERED_AT,
        extra: Sequence[LockEntry] = (),
    ) -> Lockfile:
        """Write the full lockfile sync would: each ``rels`` file as it is now, plus ``extra``.

        ``guard_config.json`` is always recorded (it vouches for the config), so
        call this after :meth:`install_pack`.
        """
        entries = [_pristine(self.root, rel) for rel in (*rels, GUARD_CONFIG_REL)]
        lockfile = Lockfile(2, engine_version, rendered_at, entries=[*entries, *extra])
        FileSystemStateSource(repo_root=self.root).save_lockfile(lockfile)
        return lockfile

    def relocate(self, case: HookPayloadCase) -> bytes:
        """``case``'s payload with the fixture project dir replaced by this repository."""
        text = case.raw.decode("utf-8").replace(PROJECT_DIR, str(self.root))
        return text.encode("utf-8")

    def simulate(
        self,
        payload: bytes,
        deps: RuntimeDeps,
        *,
        harness: Harness = Harness.CLAUDE_CODE,
        env: Mapping[str, str] | None = None,
        event: EventName = EventName.PRE_TOOL_USE,
        state: Path | None = None,
        asynchronous: bool = False,
    ) -> SimulateReport:
        """Run ``payload`` through ``playbook-hook simulate`` against this repository.

        ``state`` keeps session state across calls (``--state``, created when
        missing); without it every simulation starts from an ephemeral root.
        ``asynchronous`` is ``--async``: OQ-19's ``post_tool_use`` dispatch.
        """
        if state is not None:
            state.mkdir(parents=True, exist_ok=True)
        args = SimulateArgs(
            event=event,
            harness=harness,
            repo=str(self.root),
            env=tuple((env or {}).items()),
            state=None if state is None else str(state),
            asynchronous=asynchronous,
        )
        return run(args, payload, deps=deps)

    def tool_payload(
        self,
        tool: str,
        tool_input: Mapping[str, Any],
        *,
        event: EventName = EventName.PRE_TOOL_USE,
        **fields: Any,
    ) -> bytes:
        """A Claude-shaped ``event`` payload for ``tool`` with ``tool_input``.

        A ``post_tool_use`` payload carries a successful ``tool_response``.
        """
        body = json.loads(self.payload(event))
        body.update(tool_name=tool, tool_input=dict(tool_input), tool_use_id="toolu_ggo")
        if event is EventName.POST_TOOL_USE:
            body["tool_response"] = {"success": True}
        body.update(fields)
        return json.dumps(body).encode("utf-8")


def _pristine(root: Path, rel: str) -> LockEntry:
    data = (root / rel).read_bytes()
    return LockEntry(rel, compute_hash(data), len(data))


def rows_of(*rows: tuple[str, str, str, str]) -> list[ProtectedRow]:
    """``ProtectedRow``s from ``(path, kind, artifact_id, source)`` tuples."""
    return [
        ProtectedRow(path, kind, artifact_id, source) for path, kind, artifact_id, source in rows
    ]


def with_scope(row: ProtectedRow, scope: str, sha256: str) -> ProtectedRow:
    """``row`` as a scoped (managed JSON element) row."""
    return dataclasses.replace(row, scope=scope, sha256=sha256)


#: The argv prefix of a ``playbook`` child process after the interpreter.
PLAYBOOK_CHILD = ("-I", "-m", "coding_agent_playbook.cli")


def playbook_child(subcommand: str) -> Callable[[tuple[str, ...]], bool]:
    """A ``FakeProc`` matcher for ``<python> -I -m coding_agent_playbook.cli <subcommand> ...``."""

    def match(argv: tuple[str, ...]) -> bool:
        return argv[1:4] == PLAYBOOK_CHILD and argv[4:5] == (subcommand,)

    return match


def playbook_calls(proc: FakeProc) -> list[tuple[str, ...]]:
    """The ``playbook`` arguments of every child ``proc`` ran, in order."""
    return [call.argv[4:] for call in proc.calls if call.argv[1:4] == PLAYBOOK_CHILD]
