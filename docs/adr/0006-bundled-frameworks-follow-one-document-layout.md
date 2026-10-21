---
status: accepted
---

# Bundled frameworks follow one document layout, even where that edits vendored text

The two bundled spec-driven frameworks wrote their documents to different places (superpowers under `docs/superpowers/specs` and `docs/superpowers/plans`, mattpocock_skills under `.scratch/<slug>/`), so switching framework moved a repo's specs and plans. Consumer repos now use one fixed layout whatever the framework: `CONTEXT.md`, `docs/adr/`, `docs/architecture.md`, `docs/specs/`, `docs/plans/`, `docs/research/`, `docs/agents/`, with `.scratch/` left for throwaway prototypes only. We edit both frameworks' path strings to that layout and record the edits in each plugin's ATTRIBUTIONS change list, so superpowers is no longer byte-faithful for its paths (ADR 0003 described it as shipped unchanged). A core always rule states the layout, and a guard hook blocks specs or plans written to known other locations, which also covers an organization's own framework whose text the engine does not ship.

## Considered Options

- **Keep the vendored text byte-faithful and rely on the always rule plus the guard hook.** The agent would read one path in the skill and another in the rule, and only learn the right one when the hook blocked its first write.
- **Make the layout configurable.** The engine copies skill files as written, so per-repo paths would need templated plugin text, and agents would meet different names in different repos.

## Consequences

- A re-pin of either framework replays the path edits along with the other entries of its change list.
- The engine repo keeps its own `specs/` and `SPEC.md` for now; moving it to the layout is a separate change.

Amended by ADR 0007: the layout is configurable through a `[layout]` table, and sync rewrites the default path prefixes (and each framework's declared aliases) to the repo's configured directories. The "Make the layout configurable" option rejected above is taken in that form, which needs no templated plugin text.
