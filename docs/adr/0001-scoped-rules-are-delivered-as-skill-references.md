---
status: accepted
---

# Scoped rules are delivered as skill references; rules stay the unit of guidance

Every scoped rule used to be loaded in full on every turn: Claude Code's rules file and the shared AGENTS.md both carried all of them, about 9k–11.5k tokens in a typical Python repo. We now keep only always rules in always-loaded context. Each scoped rule names the one skill that owns its topic (`skill:` in its frontmatter), and the engine renders it as a reference inside that skill, with a generated index. Rules keep their id, gate, globs and lint codes, so hook links, lint feedback, prompt rule lists and Continue's per-rule files work unchanged. A skill is still a single kind of content: its references can be hand-written files, rendered member rules, or both.

## Considered Options

- **Rewrite scoped rules as hand-written skills.** This loses per-rule gating, Jinja and lint codes, breaks seven places that key on rule ids (hook links, lint feedback, prompt rule lists, the eval prompt renderer, guard-config rows, the agent_harness manifest), and drops Continue's glob-attached rules.
- **Use each harness's native path scoping** (`.claude/rules` with `paths:`). This saves almost nothing in Python repos, where most scoped rules match `**/*.py`, and OpenCode and Codex have no path scoping at all.
- **Declare membership on the skill** (`rules: [...]`). Then an overlay or a consumer repo can add a rule to a core skill only by overriding the whole skill file, and the same rule could end up owned by two skills.

## Consequences

- A skill's presence depends on detector facts: it is written only when at least one member rule passes its gate. Its description gains an engine-written "Covers …" clause naming only the active members.
- Loading a skill is the model's choice. Three things push it toward the right skill: the "where guidance lives" lines in always-loaded context, prompts that name the skills and references they need, and hooks (lint feedback that names the skill, plus the skill nudge).

Amended by ADR 0005: member rules now live in, and render to, their skill's `rules/` directory, grouped into sections; `references/` holds only free-form documents.
