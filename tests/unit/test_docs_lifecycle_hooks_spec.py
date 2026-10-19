"""Docs-consistency guard: SPEC.md v0.20 documents the lifecycle-hooks model (prK §J).

Track K11 applies the §J SPEC amendment rows. These tests cover the model,
config and architecture rows: the version bump, the non-goals, the facts the
glossary used to carry (CONTEXT.md is the only glossary now; they live in §6.6.7
and §10.6.2), the architecture and layouts, the canonical ``Hook`` types, the
``[hooks]`` / ``[guardrails]`` / ``[metrics]`` tables, the renderer formats, the overlay merge
policies, the open questions and the storage seams. Each test takes the names it
expects from the landed code (dataclass fields, ``BUILTIN_FORMATS``, the merge
key policies, the manifest kinds), so adding a key or a field without
documenting it fails here. Prose-only: they read markdown and introspect
dataclasses; they never run engine behaviour.
"""

from __future__ import annotations

import dataclasses
import re
import typing
from pathlib import Path

import pytest

from coding_agent_playbook._member_reference import MemberReference
from coding_agent_playbook.config.tables.hooks import (
    COMMIT_CONVENTION_TABLE,
    GuardrailsConfig,
    HooksConfig,
)
from coding_agent_playbook.evaluators.types import MetricConfig
from coding_agent_playbook.harness.manifest import ArtifactKind, ManifestEntry
from coding_agent_playbook.hook_policy import (
    DEGRADED_EVENTS,
    HOOK_EVENTS,
    HOOK_SUPPORT,
    TOOL_CLASS_NAMES,
    KeyPolicy,
)
from coding_agent_playbook.renderer import BUILTIN_FORMATS
from coding_agent_playbook.types import (
    Hook,
    HookFrontmatter,
    HookHandler,
    HookMatcher,
    PromptFrontmatter,
    RuleFrontmatter,
    Skill,
)

_ROOT = Path(__file__).resolve().parents[2]
_SPEC = _ROOT / "SPEC.md"
_SRC = _ROOT / "src" / "coding_agent_playbook"
_CATALOG = _ROOT / "catalog"
_HEADER_VERSION = re.compile(r"^\| Version \| (\d+\.\d+) \(draft\) \|$", re.MULTILINE)

#: Config fields whose TOML spelling is a (sub-)table, not a ``key`` of the table.
_HOOKS_SPELLING = {
    "per_hook": "[hooks.<hook-id>]",
    "commit_convention": f"[hooks.{COMMIT_CONVENTION_TABLE}]",
}
_METRICS_SPELLING = {
    "thresholds": "[metrics.thresholds.<metric>]",
    "regression": "[metrics.regression.<metric>]",
    "weights": "[metrics.weights]",
    "ruff_families": "[metrics.ruff_violations] families",
    "ruff_config": "[metrics.ruff_violations] config",
    "ruff_preview": "[metrics.ruff_violations] preview",
}

#: Classes whose ``@dataclass`` listing §6.6.2 must keep field-for-field with the code.
_LISTED_CLASSES = (
    RuleFrontmatter,
    PromptFrontmatter,
    Skill,
    MemberReference,
    HookMatcher,
    HookHandler,
    HookFrontmatter,
    Hook,
)

#: §I's "new" invariants, as the §4.3 recap words them (CLAUDE.md is local-only, OQ-5).
_HOOK_INVARIANTS = (
    "`dispatch` exits 0 or 10",
    "a raw 2 is never a deny",
    "`settings.local.json` is never written",
    "Hooks are git-only in v1",
    "`.local.toml` never carries policy",
    "absent `[hooks]` table",
    "`deny | ask | context | none`",
)

#: Engine modules §5.1 must show (each must exist, so the layout cannot name a ghost).
_ENGINE_PATHS = (
    "hook_runtime/",
    "hook_policy/",
    "hook_registrations/",
    "security/",
    "guard_config.py",
    "config/tables/hooks.py",
    "generated_output/sentinel.py",
    "detector/pep503.py",
    "gate_scan.py",
    "templates/hook_shims/",
)
#: Catalog paths §5.1 must show, under ``catalog/`` (SPEC v0.19: content left the package).
_CATALOG_PATHS = ("core/hooks/",)
_CONSUMER_PATHS = (
    "playbook/hooks/",
    ".coding-agent-playbook/hooks/",
    ".claude/hooks/playbook/launch.sh",
    ".opencode/plugins/playbook-hooks.js",
)


def _spec_text() -> str:
    return _SPEC.read_text(encoding="utf-8")


def _spec_section(start_heading: str, end_heading: str) -> str:
    """The SPEC text from ``start_heading`` up to the first ``end_heading`` after it."""
    text = _spec_text()
    start = text.index(start_heading)
    return text[start : text.index(end_heading, start + len(start_heading))]


def _class_listing(section: str, cls: type) -> str:
    """The ``class <name>`` block of a SPEC code listing, up to the next class or fence."""
    start = section.index(f"class {cls.__name__}:")
    ends = [section.find(mark, start + 1) for mark in ("\nclass ", "\n@dataclass", "```")]
    return section[start : min(end for end in ends if end != -1)]


def _field_names(cls: type) -> list[str]:
    return [spec.name for spec in dataclasses.fields(cls)]


def test_spec_footer_matches_header_version() -> None:
    text = _spec_text()
    match = _HEADER_VERSION.search(text)
    assert match is not None, "SPEC header has no '| Version | X.Y (draft) |' row"
    version = match.group(1)
    assert f"*End of SPEC.md v{version}.*" in text
    assert f"\n### v{version} (" in text


def test_spec_top_changelog_bullet_is_the_header_version() -> None:
    # The version race the skills-first spec warns about (P1-10): a release opened in the
    # header and the appendix but not in the top changelog leaves readers on the old entry.
    header = _HEADER_VERSION.search(_spec_text())
    assert header is not None, "SPEC header has no '| Version | X.Y (draft) |' row"
    top = _spec_section("**Changelog**", "## 1. Context")
    newest = re.search(r"^- \*\*(\d+\.\d+)\*\* —", top, re.MULTILINE)
    assert newest is not None, "SPEC top changelog has no '- **X.Y** —' bullet"
    assert newest.group(1) == header.group(1), (
        f"top bullet {newest.group(1)}, header {header.group(1)}"
    )


def test_spec_top_changelog_has_v0_20_bullet() -> None:
    top = _spec_section("**Changelog**", "## 1. Context")
    assert "- **0.20** —" in top
    assert top.index("- **0.20** —") < top.index("- **0.19** —") < top.index("- **0.18** —")


def test_spec_non_goals_allow_exactly_one_generated_opencode_plugin() -> None:
    assert "No OpenCode plugins (`.opencode/plugin/`)" not in _spec_text()
    non_goals = _spec_section("### 2.2 v1 non-goals", "### 2.3 v2+ aspirations")
    assert "`.opencode/plugins/playbook-hooks.js`" in non_goals
    aspirations = _spec_section("### 2.3 v2+ aspirations", "## 3. Glossary")
    bullets = [line for line in aspirations.splitlines() if line.startswith("- ")]
    assert not [line for line in bullets if "plugin" in line.lower()]


def test_hook_kind_and_generated_plugin_are_documented_outside_the_glossary() -> None:
    # CONTEXT.md is the only glossary (SPEC §3 is a pointer), so the two facts the old
    # glossary entries carried must live in the sections that own them.
    hooks = _spec_section("#### 6.6.7 Hooks", "## 7. Configuration files")
    assert "fourth emitted canonical kind" in hooks
    plugin = _spec_section("#### 10.6.2", "#### 10.6.3")
    assert "`.opencode/plugins/playbook-hooks.js`" in plugin
    assert "exactly one file" in plugin


@pytest.mark.parametrize(
    "stale",
    ["v1 does not generate plugins", "The canonical artifact model has no hook artifact"],
)
def test_spec_carries_no_stale_hook_claim(stale: str) -> None:
    assert stale not in _spec_text()


@pytest.mark.parametrize("token", ["resolve_effective_hooks", "write_hook", "guard_config.json"])
def test_architecture_names_the_hook_pipeline(token: str) -> None:
    architecture = _spec_section("## 4. Architecture overview", "### 4.3 Key design choices")
    assert token in architecture
    assert "playbook-hook" in architecture


@pytest.mark.parametrize("phrase", _HOOK_INVARIANTS)
def test_design_recap_carries_hook_invariants(phrase: str) -> None:
    recap = _spec_section("### 4.3 Key design choices", "## 5. Repository layout")
    assert phrase in recap


@pytest.mark.parametrize(
    ("root", "path"),
    [*((_SRC, path) for path in _ENGINE_PATHS), *((_CATALOG, path) for path in _CATALOG_PATHS)],
)
def test_engine_layout_shows_every_hook_module(root: Path, path: str) -> None:
    assert (root / path.rstrip("/")).exists(), f"{path} is not in {root}"
    layout = _spec_section("### 5.1 The engine repo", "### 5.2 An overlay repo")
    # The layout is a tree: each entry shows its last path segment only.
    entry = Path(path).name + ("/" if path.endswith("/") else "")
    assert f"── {entry}" in layout


@pytest.mark.parametrize("path", _CONSUMER_PATHS)
def test_consumer_layout_shows_every_hook_output(path: str) -> None:
    layout = _spec_section("### 5.3 A consumer repo after", "## 6. Canonical artifact model")
    assert f"`{path}" in layout


def test_consumer_layout_gives_users_every_other_opencode_plugin() -> None:
    layout = _spec_section("### 5.3 A consumer repo after", "## 6. Canonical artifact model")
    assert "every other file under `.opencode/plugin/` or `.opencode/plugins/`" in layout


def test_section_6_2_documents_prompt_write_scope_and_output_contract() -> None:
    prompts = _spec_section("### 6.2 Prompts", "### 6.3 Skills")
    assert "write_scope:" in prompts
    assert "output_contract:" in prompts


@pytest.mark.parametrize("cls", _LISTED_CLASSES, ids=lambda c: c.__name__)
def test_section_6_6_documents_every_hook_frontmatter_field(cls: type) -> None:
    section = _spec_section("### 6.6 Canonical types", "## 7. Configuration files")
    listing = _class_listing(section, cls)
    missing = [name for name in _field_names(cls) if f"    {name}: " not in listing]
    assert not missing, f"SPEC §6.6.2 {cls.__name__} lacks {missing}"
    assert "HookSchemaError" in section
    assert "Hook.from_dict(hook.to_dict())" in section


def _event_row(section: str, event: str) -> list[str]:
    """The cells of the §6.6.7 event-table row of ``event``."""
    rows = [line for line in section.splitlines() if line.startswith(f"| `{event}` |")]
    assert len(rows) == 1, f"SPEC §6.6.7 needs exactly one row for {event!r}, found {rows}"
    return [cell.strip() for cell in rows[0].strip("|").split("|")]


@pytest.mark.parametrize("event", sorted(HOOK_EVENTS))
def test_section_6_6_7_event_table_matches_the_code(event: str) -> None:
    hooks = _spec_section("#### 6.6.7 Hooks", "## 7. Configuration files")
    _, claude, opencode, decisions, *_ = _event_row(hooks, event)
    spec = HOOK_EVENTS[event]
    assert claude == f"`{spec.claude_name}`"
    assert set(re.findall(r"`(\w+)`", decisions)) == set(spec.decisions)
    assert (opencode == "—") == (event not in HOOK_SUPPORT["opencode"])
    assert opencode.startswith("degraded") == (event in DEGRADED_EVENTS["opencode"])


def test_section_6_6_7_lists_every_tool_class() -> None:
    hooks = _spec_section("#### 6.6.7 Hooks", "## 7. Configuration files")
    missing = [name for name in TOOL_CLASS_NAMES if f"`{name}`" not in hooks]
    assert not missing, f"SPEC §6.6.7 lacks tool classes {missing}"


def test_section_6_4_documents_has_dev_dependency() -> None:
    predicate = _spec_section("### 6.4 The `applies_if` predicate", "### 6.5 Eval tasks")
    assert "has_dev_dependency" in predicate


@pytest.mark.parametrize("name", _field_names(HooksConfig))
def test_section_7_documents_every_hooks_config_key(name: str) -> None:
    config = _spec_section("## 7. Configuration files", "## 8. Detector subsystem")
    assert f"| `{_HOOKS_SPELLING.get(name, name)}` |" in config


def test_section_7_documents_every_guardrails_domain() -> None:
    config = _spec_section("## 7. Configuration files", "## 8. Detector subsystem")
    defaults = GuardrailsConfig()
    rows = [
        f"{domain}.{key}"
        for domain in _field_names(GuardrailsConfig)
        if domain != "explicit"
        for key in _field_names(type(getattr(defaults, domain)))
    ]
    missing = [row for row in rows if f"| `{row}` |" not in config]
    assert not missing, f"SPEC §7 lacks [guardrails] rows {missing}"


@pytest.mark.parametrize("name", _field_names(MetricConfig))
def test_section_7_documents_every_metrics_key(name: str) -> None:
    config = _spec_section("## 7. Configuration files", "## 8. Detector subsystem")
    assert f"| `{_METRICS_SPELLING.get(name, name)}` |" in config


def test_section_7_documents_commit_convention_cutover_and_local_toml_exclusion() -> None:
    config = _spec_section("## 7. Configuration files", "## 8. Detector subsystem")
    assert 'cutover_date = "' in config
    local = _spec_section("### 7.2 `.coding-agent-playbook.local.toml`", "### 7.3")
    for table in ("`[hooks]`", "`[guardrails]`", "`[metrics]`", "`[hooks.commit_convention]`"):
        assert table in local
    assert "ignored" in local


@pytest.mark.parametrize("fmt", sorted(BUILTIN_FORMATS))
def test_section_9_7_lists_every_builtin_format(fmt: str) -> None:
    formats = _spec_section("### 9.7 Format-specific post-processing", "## 10. Adapter subsystem")
    assert f"| `{fmt}` |" in formats


def test_section_9_7_documents_claude_command_write_scope_frontmatter() -> None:
    formats = _spec_section("### 9.7 Format-specific post-processing", "## 10. Adapter subsystem")
    assert "disallowed-tools: Edit Write NotebookEdit" in formats


@pytest.mark.parametrize("policy", typing.get_args(KeyPolicy))
def test_section_11_documents_hook_merge_policies(policy: str) -> None:
    overlays = _spec_section("## 11. Overlay system", "## 12. CLI contract")
    assert f"`{policy}`" in overlays
    assert "`mandatory`" in overlays


def test_section_19_marks_q8_resolved() -> None:
    questions = _spec_section("## 19. Open questions", "## 20. Storage sources")
    lines = {line.split(".", 1)[0]: line for line in questions.splitlines() if line[:1].isdigit()}
    assert "Resolved in v0.20" in lines["8"]
    assert "Partially answered in v0.20" in lines["1"]


def test_section_20_documents_list_hooks_and_manifest_hook_kind() -> None:
    interfaces = _spec_section("### 20.2 The two interfaces", "### 20.3 What v1 ships")
    assert "def list_hooks(self) -> list[Hook]:" in interfaces
    sidecar = _spec_section("### 20.10 The `.playbook/manifest.toml`", "### 20.11")
    assert "hook" in typing.get_args(ArtifactKind)
    assert 'kind = "hook"' in sidecar
    manifest_fields = _field_names(ManifestEntry)
    for name in ("hook_frontmatter", "lint_codes", "write_scope", "output_contract"):
        assert name in manifest_fields
        assert f"`{name}`" in sidecar


@pytest.mark.parametrize("track", ["Pa", "Pb", *(f"K{n}" for n in range(1, 12))])
def test_implementation_recap_lists_every_prk_track(track: str) -> None:
    recap = _spec_section("## Implementation order (recap)", "*End of SPEC.md")
    assert f"| {track} |" in recap
