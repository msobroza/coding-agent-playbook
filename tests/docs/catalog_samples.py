"""A small hand-built catalog snapshot shared by the docs-site tests.

It holds one of everything the pages render: a core skill with a declared section,
an "Other" section and a reference; a plugin with a capability and an always rule;
a prompt in both sets; hooks in two known families and one new family.
"""

from __future__ import annotations

from catalog_snapshot import (
    CatalogSnapshot,
    HookEntry,
    PluginEntry,
    PromptEntry,
    ReferenceEntry,
    RuleEntry,
    SectionEntry,
    SkillEntry,
)

SAMPLE_TREE_URL = "https://example.test/tree/main/"

_TESTING = SkillEntry(
    id="python-testing",
    description="Guides how tests are written.",
    source_path="catalog/core/skills/python-testing",
    use_when="writing tests",
    files="Test files",
    sections=(
        SectionEntry(
            title="Mocking",
            impact="CRITICAL",
            summary="Double only what you do not own.",
            open_when="A test replaces a collaborator.",
            rules=(RuleEntry("fakes", "Prefer fakes", "Use a | named fake."),),
        ),
        SectionEntry("Other", "", "", "", (RuleEntry("x", "X rule", "Says x.", "acme.rules"),)),
    ),
    references=(ReferenceEntry("references/doubles.md", "Choosing a double."),),
)

_PLUGIN = PluginEntry(
    layer="coding_agent_playbook.plugins.demo_skills",
    name="demo",
    description="Plan and test (Demo skills).",
    credit="Vendored from Demo (MIT).",
    source_path="catalog/plugins/demo_skills",
    skills=(
        SkillEntry(
            "grill",
            "Interview the user.",
            "catalog/plugins/demo_skills/skills/grill",
            capabilities=("clarify",),
        ),
    ),
    always_rules=(RuleEntry("tracker", "Tracker", "Track tickets."),),
)

SAMPLE_SNAPSHOT = CatalogSnapshot(
    core_skills=(_TESTING,),
    always_rules=(RuleEntry("project-context", "Project context", "Read the glossary."),),
    plugins=(_PLUGIN,),
    prompts=(PromptEntry("review", "Review", "review", "Review the change."),),
    hooks=(
        HookEntry("zz-new", "New", "A new family.", "zeta", ("stop",), "opt-in", ("opencode",)),
        HookEntry("log", "Log", "Log decisions.", "audit", ("stop",), "default", ("claude_code",)),
        HookEntry(
            "guard",
            "Guard",
            "Guard the lockfile.",
            "protect",
            ("pre_tool_use", "stop"),
            "default",
            ("claude_code", "opencode"),
        ),
    ),
)
