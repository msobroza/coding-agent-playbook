# Attributions

This file is the only place in the shipped resources that credits outside
sources for the engine's own rules, references, scripts and prompts. Artifact
bodies carry no attribution. Attributions for the `find-injected-vuln-*` eval
fixtures live in `eval_samples/ATTRIBUTIONS.md`.

Core's Python guidance is vendored from the two MIT-licensed sources below: the
upstream text is copied and adapted (engine frontmatter, one topic per rule
file, the repository's own toolchain, no URLs, and every point where an engine
decision disagrees rewritten to that decision). Each table records, per core
skill, which core files every upstream file became and what changed, or `DROP`
with the reason it was left out. A file listed as distilled reuses ideas only,
with no upstream text, and is credited here by name.

Each core skill that holds a source's text ships that source's license notice,
byte-identical, as `references/LICENSE.<source>` (for example
`references/LICENSE.python-best-practices`). The Continue adapter writes no
skill directories, so its output carries no license copy.

Core paths in the tables are relative to the skill directory
(`catalog/core/skills/<skill>/`); a path ending in `/` covers every file under
that directory. Files the engine wrote with no upstream text are listed per
skill under "Engine-written files" at the end.

The code-legibility always rule (the eight principles it names, each pointing
at the skill rule that holds its detail) distills ideas from Akita, "Clean Code
para Agentes de IA" (2026-04-20), as reformulated by the engine's owner; it is
credited by name only. No sentences or examples from the article are copied;
the ideas are restated in the engine's own words as general clean-code
principles.

The domino-apps skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the
Domino Data Lab 6.2 user and admin documentation, which carries no open
license; it is credited by name only and not vendored. No sentences or
examples from the documentation are copied, its unsafe example settings are
not reproduced, and the facts are restated in the engine's own words. The
`domino-docs` section below records, per documentation page, the files that
use its facts or why it was dropped; a distilled source has no pin and no
license copy.

## python-best-practices

Source: the "python-best-practices" agent skills by Ludo Technologies LLC, tag v0.8.0.
Commit: `fa0d3f58afb8bf56c028bb559e0e7bc1538e079a`
License: MIT License. Copyright (c) 2026 Ludo Technologies LLC.

Its impact ratings inform each rule's section and priority. Ideas from it also
shaped the python-error-handling, python-typing, python-docstrings,
python-dependency-injection, python-data-shapes, python-idioms and pytest rules.

### design-patterns

| Upstream file | Core files | Changes |
| --- | --- | --- |

### ml-data

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/ml-vectorization.md.j2`
- `rules/ml-data-transforms.md.j2`
- `rules/ml-dtypes-and-typing.md.j2`
- `rules/ml-reproducibility-and-testing.md.j2`

### python-coding

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/python-performance-idioms.md`
- `rules/python-async.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-error-handling.md`
- `rules/python-typing.md.j2`
- `rules/python-docstrings.md`
- `rules/python-dependency-injection.md`
- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/pydantic-boundaries.md`

### python-testing

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/pytest-test-doubles.md`
- `rules/pytest-fixtures.md`
- `rules/pytest.md.j2`

### python-tooling

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/python-static-checks.md`
- `rules/pytest-configuration.md`
- `rules/python-uv-workflow.md`

### web-application

| Upstream file | Core files | Changes |
| --- | --- | --- |

## python-clean-architecture

Source: the "python-clean-architecture" Claude Code plugin by MKToronto, 16 commits after version 0.8.1.
Commit: `9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce`
License: MIT License. Copyright (c) 2025 MKToronto.
The plugin describes its concepts as inspired by Arjan Codes' courses.

Ideas from it also shaped the python-house-style always rule and the
review-architecture, make-testable, characterize, review and refactor prompts.

### design-patterns

| Upstream file | Core files | Changes |
| --- | --- | --- |

### ml-data

| Upstream file | Core files | Changes |
| --- | --- | --- |

### python-architecture

| Upstream file | Core files | Changes |
| --- | --- | --- |

### python-coding

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/python-dependency-injection.md`
- `rules/python-pure-core.md`
- `rules/python-data-shapes.md`
- `rules/python-idioms.md`
- `rules/python-classes-and-protocols.md`
- `rules/python-context-managers.md`
- `rules/python-retries-and-timeouts.md`
- `rules/python-typing.md.j2`
- `rules/python-error-handling.md`

### python-testing

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/pytest.md.j2`

### python-tooling

| Upstream file | Core files | Changes |
| --- | --- | --- |

### web-application

| Upstream file | Core files | Changes |
| --- | --- | --- |

Distilled (credited by name only, no vendored text):

- `rules/fastapi-app-wiring.md`
- `rules/fastapi-error-boundaries.md`

## domino-docs

Source: the Domino Data Lab 6.2 user and admin documentation, cited by page id.
Form: distilled (credited by name only, not vendored; no open license).

Each row names the files that restate a page's facts in the engine's own
words; those files stay under "Engine-written files". Pages a later lane
uses gain its files in their row.

### domino-apps

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `user_guide/9d3c12` | `SKILL.md`, `rules/domino-app-external-persistence.md` | Facts restated: the launch contract; stopping an App deletes its pod and every unsaved file change. |
| `user_guide/b99d5d` | `SKILL.md`, `rules/domino-app-external-persistence.md`, `rules/domino-app-concurrent-writes.md` | Facts restated: Apps never save file changes, so durable data goes to a Dataset, a database or an object store; Domino does not serialize writes across viewers. |
| `admin_guide/71d6ad` | `SKILL.md`, `rules/domino-app-concurrent-writes.md` | Facts restated: the default proxy limits; autoscaled replicas share one volume for code and temporary files. |
| `user_guide/e3ec27` | `rules/domino-app-external-persistence.md` | Fact restated: project files are writable inside an App but never saved. |
| `user_guide/b04682` | `rules/domino-app-concurrent-writes.md` | Fact restated: replicas share one disk, so concurrent writes to one file can corrupt it. |
| `user_guide/f46bdc` | `rules/domino-app-replica-state.md`, `rules/domino-app-shiny.md` | Facts restated: autoscaled replicas, session affinity and its secure-flag requirement, small pods for Shiny. |
| `user_guide/a29497` | `rules/domino-app-external-persistence.md`, `rules/domino-app-replica-state.md`, `rules/domino-app-dash.md`, `rules/domino-app-flask.md`, `rules/domino-app-shiny.md` | Facts restated: Apps never sync file changes; the Flask and Dash development servers are single-threaded; one R Shiny process computes for one session at a time (the Python consequence is the engine's inference). Not used: the stale claim that Apps never scale horizontally and the worked sizing arithmetic. |
| `user_guide/de2589` | `rules/domino-app-dash.md` | Facts restated: Dash's two path prefixes, the prefix variable read for the browser side, a one-line launch script. Not reproduced: the environment and publish click-paths and the debug-on run line (unsafe). |
| `user_guide/a537c2` | `rules/domino-app-dash.md`, `rules/domino-app-streamlit.md`, `rules/domino-app-shiny.md` | Facts restated: Streamlit's launch flags; Shiny serves 0.0.0.0:8888. Not reproduced: the Dash stub that omits the browser-side prefix and runs with debug on, and the R Shiny runApp lines (unsafe / R-only). |
| `user_guide/2039f2` | `rules/domino-app-flask.md` | Facts restated: the WSGI middleware that sets the mount point and scheme; the package layout. Not reproduced: the debug-on launch script, the DFS layout tree and the publish click-path. |
| `user_guide/cb9195` | `rules/domino-app-flask.md` | Fact restated: the prefix comes from DOMINO_RUN_HOST_PATH, not a request header. Not reproduced (unsafe): the basic identity launch script (debug on, no port). |
| `user_guide/2c3a33` | `rules/domino-app-streamlit.md` | Facts restated: Streamlit's 8501 default; a launch script that writes the server settings and is executable. Not reproduced (unsafe): CORS and XSRF protection off, usage statistics on, unpinned installs; the dead example-repo pointer and model names are dropped. |
| `user_guide/9b11ea` | `rules/domino-app-static-site.md` | Fact restated: a standard-library HTTP server on 8888 can serve static pages from a Python launch file. Not reproduced: the example serving the whole working directory (unsafe). |
| `user_guide/71635d` | DROP | Section landing page: one-line pointers to child pages, nothing actionable. |
| `user_guide/e92082` | DROP | R-only Shiny walkthrough; its 0.0.0.0:8888 fact is restated from a537c2. |
| `user_guide/5aedde` | DROP | Agent deployment, tracing and runs belong to the domino-agents skill. |
| `user_guide/d95a3c` | DROP | Reserved project files are detector markers and domino-jobs results material, not App guidance. |
| `user_guide/ccaee6` | DROP | The Git-based /mnt layout is domino-jobs' shared basics. |
| `support_kb/docs-lifecycle` | DROP | Docs lifecycle and the client compatibility matrix: provenance facts, not rule text. |

## Engine-written files

Files written for the engine with no upstream text, per core skill. A file
that comes to hold vendored text moves from here into its source's table.

### design-patterns

### domino-agents

### domino-apps

- `SKILL.md`
- `rules/domino-app-external-persistence.md`
- `rules/domino-app-concurrent-writes.md`
- `rules/domino-app-replica-state.md`
- `rules/domino-app-dash.md`
- `rules/domino-app-flask.md`
- `rules/domino-app-streamlit.md`
- `rules/domino-app-shiny.md`
- `rules/domino-app-static-site.md`

### domino-jobs

### ml-data

- `SKILL.md`
- `rules/ml-serialization-security.md.j2`

### playbook-creator

### playbook-guardrails

- `SKILL.md`

### python-architecture

### python-coding

- `SKILL.md`

### python-documentation

### python-testing

- `SKILL.md`

### python-tooling

- `SKILL.md`

### web-application

- `SKILL.md`
