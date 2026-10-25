---
status: accepted
---

# Consumers always get the current text, and eval samples pin frozen editions

The playbook had no version anyone could rely on: an integer `version:` on every artifact that nothing read and that was bumped in a handful of edits, a package stuck at `0.1.0a0` with no git tags, and two prompt sets chosen per repo (ADR 0008) behind a closed `v1`/`v2` choice. We replace all of it with one scheme. The package (engine and catalog) has one SemVer, tagged `vX.Y.Z`, and the git tag is the only distribution channel. A consumer repo always renders the **current text** of the release it installed; there is no per-repo edition or prompt-set choice, so the `prompts` key goes and v2 becomes the current text. An **edition** is a frozen copy of the **graded set** (the graded prompts plus the rules they include) as one release shipped it. It lives only in the engine, under `catalog/editions/<tag>/`, and only while a **pin** needs it: a pinned eval sample grades its edition, so scores stay comparable while authors keep improving the current text. This supersedes ADR 0008.

Releases are prepared by a maintainer script as a pull request (version, manifest of the graded set with digests, per-release notes, optional release metrics under `catalog/releases/<version>/`); merging it is the release, and CI tags that exact commit. commitizen computes the version from Conventional Commit titles: a change in what the agent is told to do is a `feat`, a typo-level text fix or engine fix is a `fix`, and a removed id or format break carries `!`. **Release metrics** score every eval sample per harness and model target and compare them with the previous release, so a guidance regression blocks the release unless it is accepted with a stored reason.

## Considered Options

- **Keep per-artifact `version:` fields and bump them by hand.** Six of 175 content edits bumped one, parallel worktree lanes collide on them, and nothing reads them; a computed content digest per artifact replaces the field.
- **Keep prompt sets chosen per repo.** A consumer's agents could see two versions of the same guidance, every author maintains two copies of a prompt, and a layer without `prompts/v2/` silently keeps v1 text.
- **Freeze the graded text by convention during the eval pilot.** Graded v1 text changed during the freeze anyway, and reports did not record which text they graded.
- **Ship editions to consumers.** Consumers would choose between near-duplicates again; editions exist to keep eval scores comparable, which only the engine needs.

## Consequences

- Authors edit only the current text. `catalog/editions/` and `catalog/releases/` are written only by the release script, sit outside every layer root, are skipped by ruff, and CI fails when an edition differs from its tag's blobs.
- A pin freezes the whole experiment (edition text, `sample.toml`, `setup/` and the rendered prompt's digest), so an engine change that alters a pinned sample's rendered prompt fails CI until the sample is unfrozen and frozen again.
- Only `freeze vX` creates an edition and pins the graded core samples, and only `unfreeze` removes them; releases never create or delete editions. v1 becomes edition `v0.1.0`.
- A pull request that changes shipped rules, prompts, skills or hooks must be titled `feat` or `fix`, or carry `!`, so guidance changes always bump the release.
- Change communication moves to the per-release notes shipped in the package; MIGRATION.md stays as history and no CHANGELOG.md is added.
