"""Hooks in the agent_harness tree (specs/prK-lifecycle-hooks.md §C.6).

The harness has no lifecycle-event concept, so a hook travels as an opaque
``.playbook/hooks/<id>/`` sidecar (canonical frontmatter, the un-rendered body,
byte-copied scripts) recorded in the manifest as kind ``hook``, while clients
see only its advisory as ``rules/30-guardrail-<id>.md``, which is presentation
and never a manifest entry.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from coding_agent_playbook._sentinel import sentinel_line
from coding_agent_playbook.adapters.agent_harness_adapter import AgentHarnessAdapter
from coding_agent_playbook.artifacts.frontmatter import split_frontmatter
from coding_agent_playbook.artifacts.hook_frontmatter import HookFrontmatter
from coding_agent_playbook.artifacts.rule import Rule, RuleFrontmatter
from coding_agent_playbook.harness.manifest import ScriptEntry, read_manifest
from tests.hook_samples import resolved_from_disk

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from coding_agent_playbook.hooks.resolution.resolved import ResolvedHook

_SIDECAR = ".playbook/hooks/guard-x"
_GUARDRAIL = "rules/30-guardrail-guard-x.md"


def _emit(out: Path, hooks: Sequence[ResolvedHook], rules: Sequence[Rule] = ()) -> list[Path]:
    adapter = AgentHarnessAdapter()
    for rule in rules:
        adapter.write_rule(rule, out)
    assert all(adapter.write_hook(hook, out) == [] for hook in hooks)  # buffered
    return adapter.finalize(out)


def _rule() -> Rule:
    fm = RuleFrontmatter(id="style", name="Style", description="House style", scope="always")
    return Rule(fm, "Use types.\n", "Use types.\n", False, None, "test")


def test_hook_sidecar_and_scripts_with_exec_bits(tmp_path: Path) -> None:
    hook = resolved_from_disk(tmp_path / "src", body="Advice {{ x }}.\n", templated=True)
    out = tmp_path / "out"

    written = _emit(out, [hook])

    sidecar = out / _SIDECAR / "HOOK.md"
    assert sidecar in written
    data, body = split_frontmatter(sidecar.read_text("utf-8"))
    assert HookFrontmatter.from_mapping(data, where="sidecar") == hook.definition.frontmatter  # type: ignore[union-attr]
    assert body == f"{sentinel_line('html')}\n\nAdvice {{{{ x }}}}.\n"  # sentinel, un-rendered body
    script = out / _SIDECAR / "scripts" / "check.sh"
    assert script.read_bytes() == b"#!/bin/sh\nexit 0\n"
    if os.name == "posix":
        assert script.stat().st_mode & stat.S_IXUSR
    manifest = read_manifest(out)
    assert manifest is not None
    entry = manifest.index_by_path()[f"{_SIDECAR}/HOOK.md"]
    assert (entry.kind, entry.id, entry.name, entry.is_templated) == (
        "hook",
        "guard-x",
        "Guard X",
        True,
    )
    assert entry.body == "Advice {{ x }}.\n"
    assert entry.hook_frontmatter == hook.definition.frontmatter.to_mapping()  # type: ignore[union-attr]
    assert sorted(entry.scripts, key=lambda s: s.path) == [
        ScriptEntry(f"{_SIDECAR}/scripts/check.sh", executable=True),
        ScriptEntry(f"{_SIDECAR}/scripts/lib/data.txt", executable=False),
    ]


def test_guardrail_rule_listed_in_harness_md_not_in_manifest(tmp_path: Path) -> None:
    hook = resolved_from_disk(tmp_path / "src")
    out = tmp_path / "out"

    written = _emit(out, [hook], rules=[_rule()])

    guardrail = out / _GUARDRAIL
    assert guardrail in written
    data, body = split_frontmatter(guardrail.read_text("utf-8"))
    assert data == {"description": "Deny x."}
    assert body.startswith(
        f"{sentinel_line('html')}\n\nAdvice.\n\n*Enforced by lifecycle hooks on:"
    )
    harness_md = (out / "HARNESS.md").read_text("utf-8")
    assert f"- `{_GUARDRAIL}` — Deny x." in harness_md
    # One list, by (priority, id): the guardrail (30) before the rule (50).
    assert harness_md.index(_GUARDRAIL) < harness_md.index("rules/50-style.md")
    manifest = read_manifest(out)
    assert manifest is not None
    assert _GUARDRAIL not in manifest.index_by_path()
    assert [e.kind for e in manifest.entries] == ["rule", "hook"]


@pytest.mark.parametrize("variant", ["blank_body", "advisory_off"])
def test_sidecar_without_advisory_writes_no_guardrail(tmp_path: Path, variant: str) -> None:
    hook = (
        resolved_from_disk(tmp_path / "src", body="")
        if variant == "blank_body"
        else resolved_from_disk(tmp_path / "src", advisory=False)
    )
    out = tmp_path / "out"

    written = _emit(out, [hook])

    assert out / _SIDECAR / "HOOK.md" in written
    assert not (out / "rules").exists()
    assert "rules/" not in (out / "HARNESS.md").read_text("utf-8")


def test_hooks_only_repo_still_emits_the_tree(tmp_path: Path) -> None:
    out = tmp_path / "out"

    written = _emit(out, [resolved_from_disk(tmp_path / "src")])

    assert out / "HARNESS.md" in written
    assert (out / ".playbook" / "manifest.toml").is_file()


def test_playbook_hooks_dir_cleanup(tmp_path: Path) -> None:
    out = tmp_path / "out"
    _emit(out, [resolved_from_disk(tmp_path / "src")], rules=[_rule()])
    adapter = AgentHarnessAdapter()
    adapter.write_rule(_rule(), out)
    written = {path.resolve() for path in adapter.finalize(out)}

    stale = adapter.stale_outputs(written, out)

    assert sorted(stale) == sorted([out / _SIDECAR / "HOOK.md", out / _GUARDRAIL])
    # Copied scripts carry no sentinel: the lockfile leftover policy settles them.
    assert (out / _SIDECAR / "scripts" / "check.sh").is_file()
