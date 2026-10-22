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

The domino-jobs skill (its SKILL.md and every rule under its rules/
directory, listed under "Engine-written files") distills facts from the
Domino Data Lab 6.2 user, admin and API documentation, which carries no open
license; it is credited by name only and not vendored. No sentences or
examples from the documentation are copied, and the facts are restated in the
engine's own words. The `domino-docs` section below records, per
documentation page, the files that use its facts or why it was dropped; a
distilled source has no pin and no license copy.

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

Source: the Domino Data Lab 6.2 user, admin and API documentation, cited by page id.
Form: distilled (credited by name only, not vendored; no open license).

Each row names the files that restate a page's facts in the engine's own
words; those files stay under "Engine-written files". Pages a later lane
uses gain its files in their row.

### domino-jobs

| Upstream file | Core files | Changes |
| --- | --- | --- |
| `user_guide/910370` | `SKILL.md`, `rules/domino-project-types.md` | Fact restated: a job in a Git-based project syncs only artifacts back; code edits are neither saved nor pushed. |
| `user_guide/ccaee6` | `SKILL.md`, `rules/domino-project-types.md`, `rules/domino-paths-from-env.md` | Facts restated: the Git-based layout (code checkout as working directory, data, artifacts, imported folders). Not reproduced: the prose's /mnt/local dataset path, which contradicts the tree (code reads the variable instead). |
| `user_guide/de4abb` | `SKILL.md`, `rules/domino-project-types.md`, `rules/domino-paths-from-env.md` | Facts restated: the DFS layout, its working directory and how importing a project moves it. |
| `user_guide/b4f02f` | `rules/domino-project-types.md`, `rules/domino-secrets-in-env-vars.md` | Facts restated: what each project type tracks, a new revision per completed job, the store keeps every version, Apps and endpoints persist nothing. |
| `user_guide/b4cb04` | `rules/domino-project-types.md` | Facts restated: the Finishing and Stopping states copy new and changed files back; Error means a platform failure. |
| `user_guide/5b3b05` | `rules/domino-project-types.md` | Fact restated: changes are captured at completion whether the job succeeded or failed. |
| `user_guide/56938d` | `rules/domino-project-types.md`, `rules/domino-paths-from-env.md` | Facts restated: where artifacts live per project type; variables instead of /mnt literals. Not reproduced: the tip to replace /mnt with DOMINO_WORKING_DIR, which breaks for Git-based artifacts. |
| `user_guide/d8dde6` | `rules/domino-secrets-in-env-vars.md` | Facts restated: no secrets in source; project variables live in a secure store, are passed verbatim up to 64K and are readable by every collaborator. |
| `user_guide/d7bac0` | `rules/domino-secrets-in-env-vars.md` | Contradiction noted: who may edit project variables; the rule validates values at startup instead of trusting either version. |
| `user_guide/910b3a` | `rules/domino-secrets-in-env-vars.md` | Facts restated: user variables are visible only to their owner and injected only into that user's runs, never into models. |
| `user_guide/9c4f82` | `rules/domino-secrets-in-env-vars.md`, `rules/domino-pinned-environments.md` | Facts restated: requirements.txt location and reinstall on every execution; private Git dependencies use the Git integration. |
| `user_guide/aa15a8` | `rules/domino-secrets-in-env-vars.md` | Fact restated: removing a file from the store needs an administrator's full delete across all projects. |
| `admin_guide/a9e507` | `rules/domino-secrets-in-env-vars.md` | Fact restated: execution logs are kept indefinitely. |
| `user_guide/55fc89` | `rules/domino-paths-from-env.md`, `rules/domino-api-proxy-auth.md`, `rules/domino-env-var-names.md` | Facts restated: the injected path and identity variables, the deprecated API key and removed token file, no injected defaults in Model Manager. |
| `user_guide/6942ab` | `SKILL.md`, `rules/domino-paths-from-env.md` | Fact restated: dataset mount paths per project type. |
| `user_guide/e09156` | `SKILL.md`, `rules/domino-paths-from-env.md`, `rules/domino-environment-revisions.md` | Facts restated: DOMINO_IS_WORKFLOW_JOB, Flow task outputs and snapshot mounts, Flow environment and tier IDs and the revision specification with use_latest off. |
| `user_guide/40b91f` | `rules/domino-api-proxy-auth.md` | Facts restated: service-account Bearer tokens from an environment variable, short-lived personal tokens, deprecated API keys, the in-run API proxy. |
| `api_guide/c5ef26` | `rules/domino-api-proxy-auth.md`, `rules/domino-env-var-names.md`, `rules/domino-environment-revisions.md` | Facts restated: python-domino's authentication order, the proxy's HTTPS limitation, DOMINO_MAX_RETRIES and the other tuning variables, job_start's environment and tier arguments, the minimum client version. Not used: budgets, billing tags, files and blobs, App publishing and dataset upload helpers. |
| `api_guide/d9cc25` | `rules/domino-api-proxy-auth.md` | Fact restated: with no authentication arguments the client detects the proxy. Not reproduced: its outdated token-file and API-key description. |
| `user_guide/af97b7` | `rules/domino-api-proxy-auth.md`, `rules/domino-environment-revisions.md` | Facts restated: the job's default revision and the re-run options; the SDK example's API key is noted as outdated. Not used: UI-only parts (tagging, renaming, stopping from the Active tab, volume sizes, tier grouping, cluster attachment). |
| `user_guide/e4f67f` | `rules/domino-api-proxy-auth.md` | Contradiction noted: the Airflow setup stores a user API key; the rule follows the authentication page. |
| `user_guide/6ac5a1` | `rules/domino-env-var-names.md` | Facts restated: four variable levels and their precedence, name syntax, reserved names and prefixes, the advice to use a company prefix. |
| `user_guide/b60bf6` | `rules/domino-env-var-names.md` | Fact restated: compute-environment variables need ARG and ENV lines and a rebuild. |
| `user_guide/813d89` | `rules/domino-env-var-names.md`, `rules/domino-pinned-environments.md` | Facts restated: Dockerfile instructions without FROM, install as root then back to ubuntu, exact pins, one pip install, the 127-layer limit, ARG versus ENV. |
| `user_guide/0e4da9` | `rules/domino-pinned-environments.md`, `rules/domino-environment-revisions.md` | Facts restated: dependency files reinstall over the network on every execution; test new revisions before making them Active. |
| `user_guide/5dd2c1` | `rules/domino-pinned-environments.md` | Facts restated: setup-script order and scope, the build cannot see project files or user variables; the two post-run script definitions are noted. |
| `user_guide/fda6d8` | `rules/domino-pinned-environments.md` | Fact restated: explicit versions in one place. |
| `user_guide/f51038` | `rules/domino-environment-revisions.md` | Facts restated: each save adds a revision, the latest successful build becomes Active unless auto-assign is off, build propagation. |
| `user_guide/5dce1f` | `rules/domino-environment-revisions.md` | Facts restated: a schedule uses the latest revision unless one is chosen; restricted projects. |
| `user_guide/e53646` | `rules/domino-environment-revisions.md` | Contradiction noted: whether re-running with the original version reuses the original environment. |
| `user_guide/dba65c` | `rules/domino-environment-revisions.md` | Fact restated: the project's default tier and environment apply unless overridden. |
| `user_guide/e6e601` | `rules/domino-environment-revisions.md` | Fact restated: a smaller hardware tier provisions faster. |
| `user_guide/e46d54` | DROP | Index page (environments); no fact beyond its children. |
| `user_guide/db2820` | DROP | Long-running job notifications are a per-user UI preference; nothing for code to do. |
| `user_guide/63ac71` | DROP | Saving artifacts through the workspace File Changes panel is an interactive workflow; the job persistence fact comes from user_guide/910370. |
| `user_guide/ca786d` | DROP | Index page (Manage a DFS project); no fact beyond its children. |
| `user_guide/a8e081` | DROP | Index page (Work with Projects). |
| `user_guide/716281` | DROP | Index page (Configure a Project). |
| `user_guide/1c333d` | DROP | Index page (Reference). |
| `user_guide/30b067` | DROP | Index page (Domino CLI). |
| `user_guide/85722a` | DROP | Troubleshooting index; its import-path advice concerns workspaces. |
| `user_guide/5d0521` | DROP | Restates the Git-based layout already taken from user_guide/ccaee6 and user_guide/910370. |
| `user_guide/b9d997` | DROP | Docs lifecycle: informs the 6.2 target and this credit only; no rule. |
| `legal/terms` | DROP | Terms of use: the basis for distilling instead of vendoring; no rule content. |
| `user_guide/66b789` | DROP | Model variables apply to deployed models, which no Domino skill covers. |
| `admin_guide/ed1c08` | DROP | Registry credentials for external images: an administrator task. |
| `admin_guide/de48cc` | DROP | User management index: an administrator topic with no job-code fact. |
| `user_guide/0002fb` | DROP | Workspace management, linked from the job monitoring page by mistake; nothing for jobs. |
| `user_guide/ac5c29` | DROP | MATLAB Launcher wrapper: nothing for Python repos. |

## Engine-written files

Files written for the engine with no upstream text, per core skill. A file
that comes to hold vendored text moves from here into its source's table.

### design-patterns

### domino-agents

### domino-apps

### domino-jobs

- `SKILL.md`
- `rules/domino-project-types.md`
- `rules/domino-secrets-in-env-vars.md`
- `rules/domino-paths-from-env.md`
- `rules/domino-api-proxy-auth.md`
- `rules/domino-env-var-names.md`
- `rules/domino-pinned-environments.md`
- `rules/domino-environment-revisions.md`

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
