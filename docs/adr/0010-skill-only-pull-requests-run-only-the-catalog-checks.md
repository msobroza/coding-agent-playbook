---
status: accepted
---

# Skill-only pull requests run only the catalog checks

A pull request whose changes are all skill content (`catalog/core/skills/**`, `catalog/core/ATTRIBUTIONS.md`, `tests/core_skills/**`, `tests/core_skill_pins/**`) runs `pytest -m catalog --no-cov` in the `test` jobs instead of the whole suite: the **skill lane**. Every other pull request, every push to `main` and every pull request labelled `ci:full` runs the **full lane**, the whole suite with the 80% coverage floor. The full suite had grown to about 40 minutes, and an edit-a-skill probe (new prose in a skill's index, a reference and a member rule, plus a new member rule) changed the result of no test outside the `catalog` marker, while the marked tests caught the new rule in four places. So the marker is the gate for skill content, the same subset the `catalog-checks` pre-commit hook runs.

## Considered Options

- **Workflow-level `paths` filters.** A skipped workflow never reports, so the checks `main` requires (`test (3.12)`, `test (3.13)`, `playbook-ci`, `wheel-smoke`) would stay pending; the lane is chosen inside the `test` job instead.
- **A merge queue that runs the full suite before merging.** Not available on a user-owned repository.
- **Test selection by recorded file access (testmon style).** Every sync reads the whole catalog, so it would select nearly every test.
- **Narrowing to the edited skill with `-k <skill-id>`.** Three of the four probe failures were catalog-wide checks whose names carry no skill id.

## Consequences

- A skill-lane pull request can merge green and turn `main` red: revert it first, then fix on a new pull request.
- The lane is only as sound as the marker, so a guard test fails when a test module that imports a skill helper lacks the `catalog` marker. Its exemption list names, with a reason, the few slow sync tests that read core skill ids only to adapt to whatever core ships; an exemption that no longer applies fails the guard too.
- Any other changed path (docs, specs, engine code, the lane selector itself) selects the full lane. Bundled plugin skills and the rest of `catalog/` join the skill lane only after a probe of their own.
