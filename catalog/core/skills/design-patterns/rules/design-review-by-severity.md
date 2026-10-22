---
id: design-review-by-severity
name: Design review by severity
description: "Review a module's design in a fixed scan order, back every finding with evidence you read, and rank findings by severity."
version: 1
scope: scoped
globs:
  - "**/*.py"
section: smells
priority: 60
tags: [python, design, review]
---

# Design review by severity

## Description

A design review reads before it judges and ranks what it finds. Read every in-scope file and the callers of each hotspot; skip generated, vendored and migration code. Every finding cites evidence you read: `file:line` and what the code does there. Flag problems in both directions: missing structure (a 200-line function) and unearned structure (a Protocol or factory with one implementation and no test seam). Leave deliberate idioms alone: documented extension points, framework base classes, overrides that ignore `self`, exception hierarchies. Where the project has a consistent convention, follow it and say so.

Scan in this order, because fixing the data first makes many later smells disappear: data shapes; functions and signatures; classes and cohesion; coupling and construction; idioms; and only then patterns, to add or to remove.

| Severity | Meaning | Typical findings |
| --- | --- | --- |
| correctness | Wrong results or hidden failures | a shared mutable default, a swallowed exception, float money, `lru_cache` on a method |
| design | The next change gets expensive or risky | low cohesion, hard-wired I/O collaborator, isinstance ladder, long parameter list |
| clarity | Slows readers without blocking change | vague or type-suffixed names, namespace class, asymmetric names |
| restraint | Structure that costs more than it returns | single-implementation Protocol, factory with one product |

## Bad Example

```text
detect_smells.py found:
- method-could-be-function
- long-parameter-list
- type-in-name
- mutable-default-argument
Consider refactoring these.
```

## Good Example

```text
Design review: src/irrigation (14 files read)
correctness 1 | design 2 | clarity 1 | restraint 0

mutable-default-argument, src/irrigation/schedule.py:42, correctness
Evidence: plan_zones(zones=[]) appends to its default, so each call sees earlier zones.
Why: shared state between calls; the second schedule of a run waters the first one's zones.
Fix: default to None and build a new list inside.
  before: def plan_zones(zones: list[Zone] = []) -> Schedule:
  after:  def plan_zones(zones: list[Zone] | None = None) -> Schedule:

Considered and kept: format_label (schedule.py:88) ignores self but overrides Report.
Suggested order: the correctness fix first, then the parameter object that unblocks the rest.
```

## Notes

- Severity here ranks one finding; it is not a section's Impact, which ranks how much harm ignoring a whole section's rules does.
- Within a severity, put the widest blast radius first (most callers, most shared state). Report correctness findings even when only design was asked about.
- Open with the scope and a count per severity; then one entry per finding with the smell id, `file:line`, severity, evidence, why it matters in this code, and the lightest fix as a minimal before/after. Close with "Considered and kept" (rejected hits and refactors, each with its reason) and "Suggested order" (correctness first, then fixes that unblock others; name the ones that need characterization tests first).
- Stay read-only and do not stop to ask: report the findings, and change code only when asked.
- Run `detect_smells.py` and `lcom4_clusters.py` from this skill's `scripts/` when they are present. They print candidates, not verdicts: open the code at every hit, confirm it, and list dismissed hits under "Considered and kept". Without them, apply the same heuristics by reading.
- If the code is in good shape, say so plainly; never pad a report with invented findings.
- The quick-pass checklist, every smell with its owning rule, the ruff code for a smell that keeps recurring, and before/after code for common fixes: see quality-checklist.md, smell-catalog.md, lint-guardrails.md and refactoring-moves.md.
