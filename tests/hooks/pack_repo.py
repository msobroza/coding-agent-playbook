"""A synced repository with engine pack hooks on, for the §E hook tests (specs/prK-hook-pack.md §E.0.7).

:class:`PackRepo` writes what ``playbook sync`` would for the hooks under test:
the engine's own ``HOOK.md`` resolved through the real effective view, a
``guard_config.json`` from the real ``render_guard_config`` (so the §E.0.5
tables are the rendered ones), and the lockfile entry vouching for it. Tests
then drive the exact dispatch pipeline through ``simulate.run`` with golden
payloads relocated into the repository.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import coding_agent_playbook
from coding_agent_playbook.adapters.agents_md_adapter import AgentsMdAdapter
from coding_agent_playbook.adapters.claude_code_adapter import ClaudeCodeAdapter
from coding_agent_playbook.adapters.continue_adapter import ContinueAdapter
from coding_agent_playbook.adapters.opencode_adapter import OpenCodeAdapter
from coding_agent_playbook.guard_config import (
    GuardConfigInputs,
    ProtectedRow,
    ProtectInputs,
    adapter_output_dirs,
    render_guard_config,
    serialize_guard_config,
)
from coding_agent_playbook.hook_policy import RegistryCatalog, resolve_effective_hooks
from coding_agent_playbook.hook_runtime.config import GUARD_CONFIG_REL
from coding_agent_playbook.hook_runtime.event import EventName, Harness
from coding_agent_playbook.hook_runtime.simulate import SimulateArgs, run
from coding_agent_playbook.hooks_config import GuardrailsConfig, HooksConfig
from coding_agent_playbook.types import Hook
from tests.hook_payloads import PROJECT_DIR, HookPayloadCase
from tests.hook_runtime.guard_repo import GuardRepo

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from coding_agent_playbook.detector import Facts
    from coding_agent_playbook.hook_policy import ResolvedHook
    from coding_agent_playbook.hook_runtime.deps import RuntimeDeps
    from coding_agent_playbook.hook_runtime.simulate import SimulateReport

ENGINE_PACKAGE = "coding_agent_playbook"
ENGINE_HOOKS = Path(coding_agent_playbook.__file__).resolve().parent / "resources" / "hooks"
#: Every enabled adapter of the fixture consumer.
ADAPTERS = ("claude_code", "continue", "opencode", "agents_md")


def engine_hook_paths() -> dict[str, Path]:
    """Every engine ``HOOK.md`` by hook id (its directory name)."""
    return {path.parent.name: path for path in sorted(ENGINE_HOOKS.rglob("HOOK.md"))}


def engine_hook(hook_id: str) -> Hook:
    """The engine's shipped definition of ``hook_id``."""
    return Hook.from_markdown(engine_hook_paths()[hook_id], ENGINE_PACKAGE)


def resolve_engine_hooks(
    hook_ids: Iterable[str], root: Path, *, per_hook: Mapping[str, dict[str, Any]] | None = None
) -> list[ResolvedHook]:
    """The engine hooks ``hook_ids`` through the real effective view, ``[hooks]`` on."""
    view = resolve_effective_hooks(
        [engine_hook(hook_id) for hook_id in hook_ids],
        [],
        HooksConfig(enabled=True, tiers=("default", "opt-in"), per_hook=dict(per_hook or {})),
        GuardrailsConfig(),
        cast("Facts", {}),
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
    ) -> bytes:
        """Render ``guard_config.json`` for the engine hooks ``hook_ids``; vouch for it in the lock.

        The decision log is switched on (guard-decision-log would, K9), so a test
        can read what the dispatch recorded, e.g. that canary lines are tagged.
        """
        hooks = resolve_engine_hooks(hook_ids, self.root, per_hook=per_hook)
        protect = ProtectInputs(rows, fixture_output_dirs(self.root), packages)
        inputs = GuardConfigInputs(
            hooks=hooks,
            hooks_config=HooksConfig(enabled=True),
            guardrails=GuardrailsConfig(),
            engine_version="0.1.0a0",
            protected=protect,
        )
        document = render_guard_config(inputs)
        document["logging"]["decisions"] = True
        data = serialize_guard_config(document)
        path = self.root / GUARD_CONFIG_REL
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.write_lock(hashlib.sha256(data).hexdigest())
        return data

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
    ) -> SimulateReport:
        """Run ``payload`` through ``playbook-hook simulate`` against this repository."""
        args = SimulateArgs(
            event=event, harness=harness, repo=str(self.root), env=tuple((env or {}).items())
        )
        return run(args, payload, deps=deps)

    def tool_payload(self, tool: str, tool_input: Mapping[str, Any], **fields: Any) -> bytes:
        """A Claude-shaped ``pre_tool_use`` payload for ``tool`` with ``tool_input``."""
        body = json.loads(self.payload(EventName.PRE_TOOL_USE))
        body.update(tool_name=tool, tool_input=dict(tool_input), tool_use_id="toolu_ggo")
        body.update(fields)
        return json.dumps(body).encode("utf-8")


def rows_of(*rows: tuple[str, str, str, str]) -> list[ProtectedRow]:
    """``ProtectedRow``s from ``(path, kind, artifact_id, source)`` tuples."""
    return [
        ProtectedRow(path, kind, artifact_id, source) for path, kind, artifact_id, source in rows
    ]


def with_scope(row: ProtectedRow, scope: str, sha256: str) -> ProtectedRow:
    """``row`` as a scoped (managed JSON element) row."""
    return dataclasses.replace(row, scope=scope, sha256=sha256)
