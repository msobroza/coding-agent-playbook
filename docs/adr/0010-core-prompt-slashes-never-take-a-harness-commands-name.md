---
status: accepted
---

# Core prompt slashes never take a harness command's name

The core review prompt's slash, `review`, was also a harness command: Claude Code's alias of its own `/code-review`, and the `/review` that OpenCode and Codex ship. In a synced repo the project command replaced the harness's review on OpenCode, and on Claude Code the hooks treated a typed `/review` as the playbook prompt, so the read-only guard and the output contract fired on the harness's own review. We decide that no core prompt's slash equals a harness command, aliases included, of a harness the engine writes for (Claude Code, OpenCode, Codex). A core prompt whose name collides takes the `-core` suffix: `review` becomes `review-core`, and `security-review`, which replaced Claude Code's own `/security-review`, becomes `security-review-core`. Their ids stay `review` and `security-review`, so eval samples, prompt comparisons and overrides by id are unchanged, and the old names get no alias. A catalog test holds each harness's reserved names (harness commands, their aliases and the skills a harness ships) and checks them against core prompt slashes and the skill ids of core and the bundled plugins; a collision in vendored content is fixed by renaming the vendored skill's id and recording it in its attributions. The prompt-frontmatter rule names the reserved names for repo-local authors. Twins keep their v1 prompt's slash, so the rename edits the v1 frontmatter during the pilot: the freeze of ADR 0008 covers the graded text (the body, `includes_rules`, and the existing eval samples with their gates), not the slash; new eval samples may be appended to both twins' `eval_samples`, because they grade v1 and v2 alike.

## Considered Options

- **A `playbook validate` check over every layer.** It would drift with each harness release and start failing consumers' syncs; the catalog test protects what the engine ships.
- **Keep `/review` as an alias of `review-core`.** The engine has no alias mechanism, and the alias would go on shadowing the harness's review.
- **Wait for the pilot to end.** Until then every synced repo would keep hiding the harness's review and misfiring its hooks.
