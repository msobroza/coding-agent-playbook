---
status: accepted
---

# Sync rewrites document-layout paths to the repo's configured layout

Consumer repos keep their specs, plans, decision records and research in a document layout with defaults (`docs/specs/`, `docs/plans/`, `docs/adr/`, ...), but some repos already use other directories, and frameworks shipped by organizations use their own paths. A `[layout]` table in the committed config sets any directory of the layout. Every framework keeps writing the default paths in its text; when a repo's layout differs, `sync` rewrites exactly those default path prefixes, plus the prefixes a framework declares as `layout_aliases` in its metadata, in the synced files of core, bundled plugins and overlays, before they are hashed into the lockfile. `validate` lists every rewrite per file. A repo that sets nothing gets byte-identical output.

## Considered Options

- **Fixed names only** (ADR 0006 as first written). Simple and deterministic, but a repo with an existing `specs/` directory, this engine included, has to move its files, and another framework cannot join without editing its text.
- **Template placeholders such as `{{ layout.specs }}` in plugin text.** Skill files are copied as written, so the engine would have to render vendored text as Jinja: the sources would stop reading as plain Markdown, and upstream text that contains `{{` would be misread.

## Consequences

- Only path prefixes are rewritten; file name patterns (`YYYY-MM-DD-<slug>.md`, `NNNN-slug.md`) stay fixed, so the rewrite never touches prose that merely mentions a document.
- The always rule that states the layout renders the configured paths through Jinja, and the layout guard hook reads the same table, so the three always agree.
