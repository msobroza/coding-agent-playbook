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

The domino-agents skill's SKILL.md and rules distill facts from the Domino
Data Lab 6.2 documentation (the agentic-systems, Apps, python-domino and
environment variable pages), which carries no open license, and ideas from the
`simple_agent_api_only` example agent by Domino Data Lab (Apache-2.0, commit
`eee728252c42fa660e65c2dccbea6ae4f679c04c`). The rules restate those facts and
ideas in the engine's own words, with no sentences or code copied, so they are
listed under "Engine-written files", with the upstream files each one draws on
and the upstream text they leave out.

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

## Engine-written files

Files written for the engine with no upstream text, per core skill. A file
that comes to hold vendored text moves from here into its source's table.

### design-patterns

### domino-agents

- `SKILL.md`
- `rules/domino-agent-llm-keys.md`
- `rules/domino-agent-access-token.md`
- `rules/domino-agent-endpoint-auth.md`
- `rules/domino-agent-redact-traces.md`
- `rules/domino-agent-app-factory.md`
- `rules/domino-agent-chat-endpoint.md`
- `rules/domino-agent-run-limits.md`
- `rules/domino-agent-conversation-state.md`
- `rules/domino-agent-logging.md`

Upstream files each rule draws on (example-agent files by path and lines, 6.2
documentation pages by guide and page id):

- domino-agent-llm-keys: `ai_system_config.yaml` 1-33, `README.md` 289-296,
  `dev_eval_simplest_agent.py` 154-164; api_guide/c5ef26, user_guide/baab29.
- domino-agent-access-token: `README.md` 51-77, 366-370, 420-425,
  `simplest_agent.py` 84-98, `chat_app.py` 136-137; admin_guide/71d6ad,
  user_guide/40b91f, api_guide/c5ef26.
- domino-agent-endpoint-auth: `simplest_agent.py` 80-109, `ai_system_config.yaml`
  15-33 (the endpoint shape only); user_guide/e038f2, user_guide/5aedde.
- domino-agent-redact-traces: `chat_app.py` 99-102; api_guide/c5ef26,
  user_guide/da707d.
- domino-agent-app-factory: `chat_app.py` 1-84, 121-133, 180-211,
  `simplest_agent.py` 13-20, 112-128, `app.sh` 1-11, `static/app.js` 4-11;
  user_guide/5aedde, user_guide/9d3c12.
- domino-agent-chat-endpoint: `chat_app.py` 87-118, `README.md` 40-49, 81-103;
  user_guide/5aedde, admin_guide/71d6ad.
- domino-agent-run-limits: `simplest_agent.py` 116-121, `ai_system_config.yaml`
  35-38; admin_guide/71d6ad.
- domino-agent-conversation-state: `chat_app.py` 87-96, 110,
  `ai_system_config.yaml` 38; user_guide/f46bdc, user_guide/b99d5d.
- domino-agent-logging: `chat_app.py` 20-21, 115-118, 203-210,
  `simplest_agent.py` 38, 65, `app.sh` 11, `dev_eval_simplest_agent.py` 31-38;
  admin_guide/a9e507, user_guide/bb4b24.

Upstream text these rules leave out (DROP, with the reason):

- `ai_system_config.yaml` 15-33, 46-61: commented provider blocks with an
  internal host and endpoint id, not reproduced (the endpoint URL moves to
  settings), and unused alternative prompts.
- `chat_app.py` 27-29, 136-146, 153-177: the static directory constants, the
  UI-only platform-info route and the static catch-all go with the playground
  UI; the catch-all's prefix-match check and its 200 for unknown paths are not
  reproduced.
- `static/app.js` 1-3, 12-103, 140-217, 234-625: playground UI code; only its
  relative base-path idea (4-11) is used, as a Note of domino-agent-app-factory.
- user_guide/5aedde: the page's FastAPI sample is not copied; it builds the
  agent inside the traced function on every call, and domino-agent-app-factory
  and domino-agent-endpoint-auth state the safe behavior instead.

### domino-apps

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
