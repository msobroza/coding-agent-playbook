---
status: accepted
---

# Member rules live in their skill's `rules/` directory, grouped into sections

ADR 0001 kept scoped rules in `<layer>/rules/` and joined each one to its skill through `skill:`, rendering it as `references/<id>.md`. With core growing from 26 scoped rules to about 140 across eight skills, we move every core scoped rule into the skill that owns it (`skills/<skill>/rules/<id>.md`): the directory now sets membership, the rendered skill gets the same `rules/` directory in every harness tree (agent_harness included), and `references/` is left to free-form documents with no gate and no priority. ADR 0001's decision itself stands, since rules stay the unit of guidance with their id, gate, globs and lint codes, and each still has exactly one owner. Rules from another layer (an overlay, a bundled plugin, a consumer repo) still join a skill through `skill:`, so the option ADR 0001 rejected, listing members on the skill, stays rejected. Each skill also declares ordered sections with an impact (CRITICAL, HIGH, MEDIUM, LOW). Its index lists active rules under their section, and a rule's priority is its section's impact band plus its rank inside the section.

## Considered Options

- **Keep `<layer>/rules/` plus `skill:`.** It works, but a skill's content is spread over two trees, and with 140 rules nobody can see what a skill holds by opening its folder.
- **Move the source files but keep rendering `references/<id>.md`.** It is cheaper, but rules and free-form documents get mixed in one directory, and the catalog and the rendered tree stop matching.

## Consequences

- Validation gains deterministic checks: a rule's file name equals its id; duplicate ids in one layer fail; an unknown frontmatter key is an error naming the file; `scope`, `priority` (0-99) and `section:` are checked; a rule inside `skills/x/rules/` may not name another skill; a core scoped rule outside a skill's `rules/` fails.
- The "Covers" clause in a skill's description names its active sections instead of its rules, so it no longer truncates as skills grow.
- The next sync removes the old `references/<id>.md` copies from consumer repos, which the lockfile already handles.

Amended by D47, D48 and D58 of specs/prU-core-python-skills.md: each section also declares an open-when line, and `SKILL.md` renders a fixed "How to use this skill" paragraph, the section index with those lines, and a references-and-examples list, so navigation is generated rather than hand-written. A reference or an `examples/` project may carry a gate; when it fails, the file is neither listed nor written.
