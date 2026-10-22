---
id: code-legibility
name: Code legibility
description: Eight language-neutral principles that keep code easy to read and safe to change, each pointing to the skill rule with the detail.
version: 1
scope: always
priority: 5
tags: [always, style]
---

Each line names the skill and rule that hold the detail.

- Keep units small: functions of about 4-20 lines, files under about 500 (`python-coding` -> `python-small-units`).
- Give each module one reason to change, so a concern is edited in one place (`design-patterns` -> `design-single-responsibility`).
- Keep nesting shallow, about two levels: return early, one level of abstraction per function (`python-coding` -> `python-early-return`).
- Raise errors that carry the offending value and the expected shape (`python-coding` -> `python-error-messages-with-context`).
- Use distinctive, searchable names: a search should find mostly that concept (`python-coding` -> `python-meaningful-names`).
- Give each piece of logic one home: a change to a duplicate fixes one copy and misses the rest (`design-patterns` -> `design-dry-yagni-kiss`).
- Keep the tree predictable: follow the framework's conventions and the repo's one layout axis (layer-first or feature-first), never both (`python-architecture` -> `arch-predictable-project-tree`).
- Write F.I.R.S.T unit tests (fast, independent, repeatable, self-validating, timely), run headless by one documented command (`python-testing` -> `pytest-first-properties`).
