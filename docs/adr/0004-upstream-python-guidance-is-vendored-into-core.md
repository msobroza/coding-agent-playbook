---
status: accepted
---

# Upstream Python guidance is vendored into core, not distilled

Core's Python guidance came from two MIT-licensed sources (the python-best-practices agent skills and the python-clean-architecture plugin), but only as ideas restated in fresh text: core held 28 short rules, and the design and architecture material sat in the opt-in `python_design` plugin. We now copy the upstream text into core and adapt it: engine frontmatter, one topic per rule file, the repo's toolchain, no URLs, and every point where an engine decision disagrees rewritten to that decision (engine decisions win over python-best-practices, which wins over python-clean-architecture). The copied examples and depth are what made the sources useful, and fresh rewrites kept losing them. `python_design` is removed and its content folds into three new core skills (`web-application`, `design-patterns`, `python-architecture`). Each source's MIT notice travels as a byte-identical license file in the `references/` of every skill holding its text, and `catalog/core/ATTRIBUTIONS.md` maps every upstream file to the core files it became, or to DROP with a reason.

## Considered Options

- **Keep distilling.** No license text in consumer repos and no upstream wording to police, but every rule is rewritten from scratch, and the examples, the part agents learn most from, are lost.
- **Vendor into a bundled plugin, as for superpowers and mattpocock_skills.** Plugins stay byte-faithful to upstream and are opt-in, so they could not carry the engine's own decisions, and most consumers would never see the guidance.

## Consequences

- The fresh-text policy of `specs/prS-skills-context.md` (D7, D8, the word-shingle check) no longer applies to core. The tests that enforced it change: upstream names stay banned outside `ATTRIBUTIONS.md` and the license files, and the literal-token bans on dropped recommendations (`hatchling`, `--install-types`, piping a download into a shell, and others) stay as the check that the adaptation happened.
- A re-pin is a reviewed PR: diff the two upstream commits and replay the mapping and change list in `ATTRIBUTIONS.md`.
- Continue receives core rules without their license file. The gap is the same one accepted for the vendored plugins, and the README says so.

Amended by D50 of specs/prU-core-python-skills.md: a source's license decides its form. Openly licensed sources are vendored and adapted with their license file (python-best-practices and python-clean-architecture, MIT; the Domino agent example, Apache-2.0); sources without an open license (the Domino 6.2 user documentation, the matforge documentation article, Akita's "Clean Code para Agentes de IA") are distilled: fresh text, credited by name only.
