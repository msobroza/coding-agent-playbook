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
| `user_guide/9d3c12` | `SKILL.md`, `rules/domino-app-publish-from-commit.md`, `rules/domino-app-deployment-record.md` | Facts restated: the launch contract; launch file, environment, hardware tier and code branch define an App, each App pinning its own environment version and tier. |
| `user_guide/6a2215` | `SKILL.md` | Facts restated in the Quick Reference: the injected headers and DOMINO_RUN_HOST_PATH. |
| `user_guide/b99d5d` | `SKILL.md`, `rules/domino-app-proxy-limits.md`, `rules/domino-app-logging.md` | Facts restated: runtime file writes do not persist; large data and durable outputs such as logs belong in Datasets, databases or object storage. |
| `admin_guide/71d6ad` | `SKILL.md`, `rules/domino-app-proxy-limits.md` | Facts restated: the run pod proxy's 300 s connect and read timeouts and the 25 MiB body-size default, all admin-configurable (the body cap applying to Apps is marked as inferred). |
| `user_guide/a29497` | `rules/domino-app-production-server.md` | Facts restated: the Flask and Dash built-in server is single-threaded and not meant for more than about ten concurrent users; serve with gunicorn workers. Not reproduced: the debug-on launch scripts (unsafe). Not used: the stale claim that Apps never scale horizontally and the sizing arithmetic. |
| `user_guide/aec000` | `rules/domino-app-external-resources.md` | Facts restated: a content security policy or iframe restriction blocks outside fonts, APIs and pages unless allowlisted; diagnose in the browser console and restart the App after the allowlist changes. |
| `admin_guide/6469bf` | `rules/domino-app-external-resources.md`, `rules/domino-app-sharing-mode.md` | Facts restated: the App CSP flag defaults off, the iframe flag on, and flag changes need no restart; an admin permission can admit anonymous viewers. |
| `user_guide/2c3a33` | `rules/domino-app-external-resources.md`, `rules/domino-app-publish-from-commit.md`, `rules/domino-app-workspace-preview.md` | Facts restated: file-system projects sync files only after the workspace saves and stops; preview through the workspace proxy, publish on 8888. Not reproduced (unsafe): usage statistics switched on, CORS and XSRF protection off, unpinned installs. |
| `user_guide/cd0095` | `rules/domino-app-publish-from-commit.md`, `rules/domino-app-deployment-record.md`, `rules/domino-app-sharing-mode.md` | Facts restated: a Git-based App runs the branch or revision chosen at publish time; the per-App settings of the publish dialog; sharing modes and access requests, collaborators as editors. |
| `user_guide/910370` | `rules/domino-app-publish-from-commit.md` | Facts restated: code must be pushed to be seen; no Git LFS. |
| `user_guide/bb4b24` | `rules/domino-app-publish-from-commit.md`, `rules/domino-app-logging.md` | Facts restated: each publish snapshots environment, file references and code paths with no rollback or diff; App stdout and stderr go into the execution logs and support bundle. |
| `user_guide/b04682` | `rules/domino-app-deployment-record.md`, `rules/domino-app-sharing-mode.md` | Practices restated: one branch and environment per stage, clone environments instead of editing them, tag versions; review permissions on publish, describe audience, data and limits, give a team contact. |
| `user_guide/f46bdc` | `rules/domino-app-deployment-record.md`, `rules/domino-app-logging.md` | Facts restated: autoscaling settings persist across launches; the logs of all pods are interleaved into one log. |
| `user_guide/cb9195` | `rules/domino-app-sharing-mode.md` | Facts restated: edit rights come from project collaboration; view rights are Restricted or open to anyone in Domino, with discoverable Restricted Apps and access requests. Not reproduced (unsafe): the debug-on, port-less basic identity launch script (Flask then binds 5000) and the JWT key fetch over plain HTTP with no timeout. Not reused: the decoded-payload sample with personal-looking names. |
| `user_guide/2c01ae` | `rules/domino-app-workspace-preview.md` | Facts restated: a workspace exposes one port, 80 and 9000 are reserved; the server proxy path is built from the project owner, project name and run id. |
| `admin_guide/a9e507` | `rules/domino-app-logging.md` | Fact restated: execution logs are kept indefinitely. |
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
- `rules/domino-app-production-server.md`
- `rules/domino-app-proxy-limits.md`
- `rules/domino-app-external-resources.md`
- `rules/domino-app-publish-from-commit.md`
- `rules/domino-app-deployment-record.md`
- `rules/domino-app-sharing-mode.md`
- `rules/domino-app-workspace-preview.md`
- `rules/domino-app-logging.md`

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
