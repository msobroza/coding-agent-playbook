# Contributing content

This guide explains how to add or change the content the engine ships: rules,
prompts, eval samples, lifecycle hooks and skills. All of it lives in `catalog/`, and
you never need to touch the Python package (`src/coding_agent_playbook/`) to add or
change it. The build copies this whole tree into the wheel, so what you commit in
`catalog/` is what `pip install coding-agent-playbook` ships.

This guide uses the project's terms as `CONTEXT.md`, at the repository root, defines
them. The main ones are always rule, scoped rule, member rule, skill, reference,
layer, core and bundled plugin. `CONTEXT.md` is the project's only glossary. It is
not part of the catalog, so never link to it from content.

## Where each kind lives

The tree below shows where each kind of content lives, in `core/` and in the bundled
plugins under `plugins/`.

```text
catalog/
├── README.md                 this guide (ships in the wheel, never synced)
├── core/                     the engine layer: always on in every consumer repo
│   ├── ATTRIBUTIONS.md       per-source mapping tables for vendored text, and
│   │                         credit for distilled ideas
│   ├── rules/always/         the always rules, loaded in every session
│   ├── prompts/              one <id>.md or <id>.md.j2 per prompt
│   ├── hooks/                one <category>/<id>/HOOK.md per lifecycle hook
│   ├── skills/<skill>/
│   │   ├── SKILL.md          intro, quick reference, playbook: block with sections
│   │   ├── rules/            one <rule-id>.md or .md.j2 per member rule
│   │   ├── references/       long-form documents, plus LICENSE.<source> copies
│   │   ├── scripts/          stdlib-only helpers the rules name
│   │   └── examples/         runnable example code, where a skill has one
│   └── eval_samples/         one <prompt>/<name>/ per sample, plus ATTRIBUTIONS.md
└── plugins/                  bundled plugins: off until a consumer enables one
    └── <name>/
        ├── README.md         what the plugin is and how to enable it
        ├── ATTRIBUTIONS.md   credit for a third-party source, if any
        ├── LICENSE           only for vendored third-party text
        └── skills/           one <dir>/SKILL.md per skill, plus scripts/, references/
```

`core/` ships eight base skills. Seven of them are Python skills that hold member
rules in their own `rules/` directory: `python-coding`, `python-testing`,
`python-tooling`, `ml-data`, `web-application`, `design-patterns` and
`python-architecture`. The eighth, `playbook-guardrails`, takes no rules.

Five more core skills are gated: they join the base skills only where the repo calls
for them. `domino-apps`, `domino-jobs` and `domino-agents` join in Domino repos, and
`playbook-creator` joins in repos with a playbook layer. `python-documentation` is
the fifth gated skill.

When you run `playbook sync`, it renders each skill's active member rules into the
skill's `rules/` directory. It adds the scoped rules of other layers that name the
skill in `skill:`. Only a skill that declares a `playbook:` block takes rules, so the
skills of `superpowers` and `mattpocock_skills` own none.

`playbook-guardrails` builds its body differently. Sync starts from its authored
intro and appends one section for each enabled hook, holding that hook's guardrail
text. To change a section, edit the hook's `HOOK.md` body, not the skill.

A bundled plugin may also hold `rules/`, `prompts/`, `hooks/` or `eval_samples/`,
laid out exactly as in `core/`.

The files at a layer root (`README.md`, `LICENSE` and `ATTRIBUTIONS.md`) sit outside
every kind directory, so sync never copies them into a consumer repo. Never link to
one from a rule, prompt or skill. The link would break in every consumer repo, and CI
refuses it.

Two rules keep the content self-contained. The first is that no file holds a URL and
every link stays in its layer. The second is that sources are credited in one place.

No file in this tree holds a URL. That covers the `scheme://`, `www.`, `mailto:` and
`git@host:` forms, and a bare domain followed by a path. There are two exceptions:
the license URI in `core/eval_samples/ATTRIBUTIONS.md`, and a vendored plugin's
upstream text (see "Add a bundled plugin"). A markdown link in a rule, prompt, skill
or hook must resolve to a file inside the same layer, which is `core/` or
`plugins/<name>/`. Example code in a fenced block under `core/skills/` may use a
reserved example host (`example.com`, `*.test`, `localhost`). Prose never holds one.

Sources are credited in one place. Core's Python guidance is vendored: the upstream
text of two MIT-licensed sources is copied, then adapted. The adaptation adds engine
frontmatter, keeps one topic per rule, uses the repository's toolchain and drops
URLs.

`core/ATTRIBUTIONS.md` holds one mapping table per source. For each upstream file,
the table names the core rules and references it became and what changed, or says
`DROP` with a reason. Files with no upstream text are listed as distilled or
engine-written. CI checks three things: every core file with vendored text is
listed, every listed file exists, and the pinned upstream commits match.

Each skill that holds a source's text ships that source's license notice,
byte-identical, as `references/LICENSE.<source>`. Those license copies and
`ATTRIBUTIONS.md` are the only core files that may name a source. CI scans every
other file of `core/`, and of every bundled plugin, for the source names it knows.
To add a new source, add a mapping table for it to `ATTRIBUTIONS.md`, and add its
name to `_PLUGIN_MARKER_RE` in `tests/integration/test_resources_self_contained.py`.
A vendored plugin such as `superpowers` is exempt from the name scan. It keeps its
upstream wording, including the source name.

Rule, prompt and skill sources use `.md` when the body is plain text. Use `.md.j2`
only when the body needs Jinja, for example to insert a detector fact (a property of
the consumer repo) such as `{{ project_name }}`, or to add a
`{% if has_framework("fastapi") %}` branch. No template can call `{{ rule() }}`,
because that helper is gone.

The overlay merge key is the frontmatter `id`, not the file name. A later layer
replaces an artifact with the same `id`. The order is core, then an overlay, then
the consumer's `playbook/`.

## Add a rule

A rule is either an always rule, loaded in every session, or a scoped rule, delivered
on demand inside the one skill that owns its topic. Follow these steps to add one.

1. Create the file in the right place. A scoped rule goes in
   `core/skills/<skill>/rules/<id>.md`, inside the skill that owns its topic. That
   location makes it a member rule of the skill, so it sets no `skill:`. An always
   rule goes in `core/rules/always/`. A scoped rule anywhere else in core fails
   `playbook validate`, which names the skill directory to move it to.
2. Give it the frontmatter keys that "Writing a rule" lists. SPEC §6.1 has the full
   schema. A scoped rule in another layer, such as an overlay or a consumer's
   `playbook/rules/`, names the skill that delivers it in `skill:`.
   `playbook validate` fails on such a rule without one. The skill must exist after
   the layer merge, so it may name a core skill.
3. For a scoped rule, pick the skill by topic:

   - `python-coding` when no library is needed, Pydantic validation included
   - `python-testing` for tests
   - `python-tooling` for one named developer tool
   - `web-application` for web backends
   - `ml-data` for ML and data libraries
   - `domino-apps` for Apps served on Domino
   - `domino-jobs` for jobs and launchers on Domino
   - `domino-agents` for LLM agent services on Domino
   - `design-patterns` for the shape of classes and modules inside one module
   - `python-architecture` for relations between modules
   - `python-documentation` for documentation practice
   - `playbook-creator` for authoring playbook content

   When that skill declares `sections:` in its `playbook:` block, name one of its
   section ids in the rule's `section:`. `playbook validate` fails without one. Each
   section has an impact, which says how much harm ignoring its rules does. Pick a
   `priority` in that impact's band: CRITICAL 20-39, HIGH 40-59, MEDIUM 60-79, LOW
   80-99.

   Write `description` as the one actionable line the skill's index shows for the
   rule. Keep `name` a short topic label, such as `Typing` or `Error handling`. The
   skill's "Covers ..." clause names its active sections when it declares any, and
   its member rules' names otherwise. Last, add the rule to the `members` of the
   skill's pins module in `tests/core_skill_pins/`.
4. Pick `globs` with the skill nudge in mind. The skill nudge is a one-line message
   that names a skill to load, sent the first time in a session that the agent edits
   a file the skill covers. One edit names at most five skills, ranked by the most
   specific glob that matched. A glob with fewer wildcards is more specific. Between
   globs with as many wildcards, the one with the longer literal part is more
   specific. A `**/` counts least.

   A test-related rule must use the shared test-file glob set, so that a test edit
   names `python-testing` first: `**/test_*.py`, `**/*_test.py`,
   `**/tests/**/*.py`, `**/conftest.py` and `**/fakes.py`. Some core test rules still
   use `tests/**/*.py`. They move to the set as they are revised.
5. Limit the body to guidance an assistant can act on, in the shape that "Writing a
   rule" gives. A rule cannot include another rule.

## Writing a rule

One rule holds one topic. Every core member rule has the same shape, so an agent
that opens one rule knows where to look in the next.

The table lists every frontmatter key a rule may use. `playbook validate` rejects
any other key, and its error names the file and the allowed keys.

| Key | Required | What it holds |
| --- | --- | --- |
| `id` | yes | The merge key. It is unique in its layer and equal to the file name without `.md` or `.md.j2`. Keep an existing id when you split a rule, so that hook links, prompt lists and lint codes keep working. A new id takes its skill's prefix: `python-`, `pytest-`, `ml-`, `design-`, `arch-`, `web-`, `docs-`, `domino-`, `a2a-`, or the tool that owns the topic (`fastapi-`, `pydantic-`, `sqlalchemy-`, `alembic-`, `httpx-`, `ruff-`, `mypy-`). |
| `name` | yes | A short topic label, such as `Typing` or `Error handling`. It is the rendered title. |
| `description` | yes | The one actionable line the skill's index shows for the rule. |
| `scope` | yes | `scoped` for a member rule, `always` for one of the always rules. |
| `skill` | no | Only for a scoped rule from another layer. It names the skill the rule joins. A rule inside `skills/<skill>/rules/` never names another skill, and an always rule never carries this key. |
| `section` | for a sectioned skill | One section id from the skill's `playbook.sections`. Its impact sets the `[IMPACT]` tag of the rendered title. |
| `priority` | no | 0-99, 50 by default. Lower sorts first. In a sectioned skill, pick it in the section's impact band: CRITICAL 20-39, HIGH 40-59, MEDIUM 60-79, LOW 80-99. Rules are ranked within the section. |
| `applies_if` | no | A detector-fact predicate that decides whether the rule renders in a repo (`has_framework: ["fastapi"]`, `has_dependency: ["sqlalchemy"]`, `domino_project: true`). |
| `globs` | no | The files for which the skill nudge names the skill. Test-related rules use the shared test-file glob set listed in "Add a rule". |
| `lint_codes` | no | The ruff codes a lint feedback hook reports for this rule: `{warn: [...], when: [{applies_if, warn}]}`. |
| `tags` | no | Free-form labels such as `[python, testing]`. |

This example shows the frontmatter of a member rule:

```yaml
---
id: pytest-fixtures
name: Fixtures
description: "Share setup through small, explicit fixtures and keep their scope as narrow as the test allows."
scope: scoped
globs: ["**/test_*.py", "**/*_test.py", "**/tests/**/*.py", "**/conftest.py", "**/fakes.py"]
section: fixtures
priority: 42
tags: [python, testing]
---
```

The body follows the frontmatter, with these sections in this order:

```markdown
# Fixtures

## Description

Why the topic matters and what the rule asks, in a short paragraph.

## Bad Example

A python code block with the code the rule rejects.

## Good Example

The same case written the way the rule asks.

## Notes

- Exceptions, edge cases, the lint codes involved, and the other rules or
  references to read, by plain id or path.
```

Never write the `[IMPACT]` tag yourself. Write `# Fixtures`, never
`# Fixtures [HIGH]`. The engine renders the tag from the rule's section.

A rule has a size limit: at most 100 lines and 750 words as rendered. The limit
applies after `ruff format` has laid out the code blocks, and on every branch of a
template. Split longer material into several rules, or turn it into a document under
the skill's `references/`.

Prefer a gate to a template. Gate a whole rule with `applies_if`. Write a `.md.j2`
template only when a detector fact changes part of its text, such as a
`{% if python_at_least("3.11") %}` branch for a newer idiom, or a library branch.
Example code targets Python 3.10 in the lowest branch.

Code blocks are ruff-formatted. CI runs `ruff format --check .`, which formats the
Python code blocks in markdown, so every block must parse. The block of one example
stands on its own: no rule depends on another rule's example.

Keep each rule self-contained. A rule holds no URLs in its prose and no upstream
source or author names. Credit goes in `ATTRIBUTIONS.md` only. Name other rules by
plain id, and references or examples by path, never by a link to another skill.

## Add a prompt

A prompt is a named task the user invokes explicitly, as a slash command. Follow
these steps to add one.

1. Create `core/prompts/<id>.md`.
2. Give it frontmatter with `id`, `name`, `description` and `slash`, the
   slash-command name. The optional keys are `applies_if`, `input_variables` and
   `includes_rules` (the ids of the rules the prompt needs). A prompt does not list
   its eval samples: they are the samples whose `prompt_id` names it. SPEC §6.2 has
   the full schema.
3. List the rules the prompt needs in `includes_rules`, and never place rule text in
   the body. Claude Code and OpenCode commands then open with a generated
   `## Before you start` block, which names each scoped rule's skill and reference.
   Continue prompts get the rules' text as a `## Reference rules` appendix
   (SPEC §6.2.5). `playbook validate` fails on a `{{ rule(...) }}` call and on an id
   that names no rule. `tests/unit/test_catalog_prompt_references.py` requires every
   included scoped rule to name its skill.

## Add an eval sample

An eval sample is a reproducible test case for a prompt: a starting repo state, an
invocation and a definition of success. The eval samples of one prompt form its
task, and they live in a directory named after the prompt's id. Follow these
steps to add one.

1. Create `core/eval_samples/<prompt>/<name>/sample.toml`, where `<prompt>` is the id
   of the prompt the sample grades. Give it `id = "<prompt>/<name>"`,
   `description`, `[setup]` and `[invocation]`, plus the `[gate]`, `[rubric]` and
   `[verdict]` layers (SPEC §6.5.3). Any other top-level key is a validation error,
   `prompt_id` included: the task directory names the prompt.
2. Put the starting repo in `setup/`. Include a `setup/pyproject.toml` when the
   sample depends on detector facts.
3. Ship a reference answer in `solution/`. For an edit sample, mirror `setup/` paths
   with the files a correct agent would write. For a review-only sample, write the
   answer to `solution/transcript.md`. Put known-wrong attempts in
   `solution/negatives/`. A review-only sample needs at least one. CI proves that
   the gate fails on the untouched `setup/` and on every negative, and that it passes
   on the solution.
4. Check the task: the prompt does not list its samples, and a task directory that
   names no prompt fails `playbook validate`. A sample finds its prompt in the
   `prompts/` directory next to its layer's `eval_samples/`, so a core sample uses
   `core/prompts/`. `playbook eval <prompt>` selects every sample of the task.
5. Credit third-party fixture code in `core/eval_samples/ATTRIBUTIONS.md`.

Eval samples belong to a layer, like every other kind. A bundled plugin ships its
own samples in `plugins/<name>/eval_samples/<prompt>/<sample>/`, laid out as above. Each of
its samples finds its prompt in `plugins/<name>/prompts/`. `playbook eval --list`
lists a plugin's samples only in a repo that enables the plugin. A later layer may
add samples to a task of an earlier one, but a sample id found twice fails.

Ruff never lints or reformats `setup/` in either location:
`core/eval_samples/*/*/setup` and `plugins/*/eval_samples/*/*/setup`. Mypy never reads
this tree.

## Add a hook

A hook is an assistant lifecycle handler. It runs on agent events, such as before a
tool, after an edit or at stop, and it can block, warn or feed back to the agent.
Follow these steps to add one.

1. Create `core/hooks/<category>/<id>/HOOK.md`, where `<category>` is the hook
   family: `protect/`, `verify/`, `feedback/`, `safety/` or `audit/`. The directory
   name is the hook id. The family folder carries no meaning.
2. Give it frontmatter with `id`, `name`, `description`, `tier`,
   `events`, `handler`, `decisions`, `timeout`, `on_error` and `supports`.
   `decisions` takes only `deny`, `ask`, `context` or `none`. Add `matcher`,
   `priority` and `tags` as needed.

   A hook with a body also declares `summary`, its guardrail line. A guardrail is
   the text form of a hook, for a harness that cannot run it. The `summary` is one
   line of at most 120 characters, without `{{` or `{%`, that keeps the point of the
   body. For `stop-ci-parity-gate`, that point is the checks to run.

   Engine hooks name a builtin handler (`handler: {builtin: <name>}`) and ship no
   `scripts/`. SPEC §6.6.7 has the full schema. `playbook validate` checks the hook
   trust contract, H1-H21.
3. Write the body as guidance an assistant can act on. The body is the hook's
   section in the `playbook-guardrails` skill, and Continue's
   `30-guardrail-<id>.md`. The `summary` is the hook's one line in `AGENTS.md`, and
   in the Claude Code rules file when Claude Code cannot run the hook.
   `tests/hook_runtime/handlers/test_hook_summaries.py` fails when a core hook with
   a body has no `summary`.
4. Update the gates in the same change. The gates under
   `tests/hook_runtime/handlers/` pin the shipped hooks. They hold one test module
   per hook, plus the rows of `<family>/test_manifest.py` for the safety, verify,
   audit and protect families.

The Claude Code launcher and the OpenCode plugin that run the hooks are engine
wiring, not content. Their templates stay in the package, under
`src/coding_agent_playbook/hooks/registrations/templates/`.

## Add a skill

A skill is a named unit of on-demand guidance. It is a short index the agent loads
by name, plus member rules and references it opens only when needed. Follow these
steps to add one.

1. Pick its layer. A skill that owns rules in core goes in `core/skills/<id>/`.
   Any other skill goes in the bundled plugin it belongs to, or in a new one (see
   "Add a bundled plugin").
2. Create `<layer>/skills/<dir>/SKILL.md`. Its frontmatter must declare an `id`
   and a `description`. The `id` must match `^[a-z0-9]+(-[a-z0-9]+)*$`, with at most
   64 characters, and it becomes the output directory name. The `description` holds
   1 to 1024 characters.

   A skill that owns rules, as every core skill does, has more requirements. It
   gives `id`, `name` and the directory the same value. It writes `description` as
   one third-person capability sentence without "Use when". It declares a
   `playbook:` block with `use_when` and `files`. `use_when` holds only the
   condition, because the engine writes the sentence "Use when <use_when>." itself.
   `files` holds a file-kind phrase of at most 80 characters with no trailing
   period, for the "Where guidance lives" map.

   A core skill also lists its `sections` and its `references` in that block. Each
   section has `id`, `title`, `impact`, `summary` and `open_when`. Each reference
   has a path, `open_when` and an optional `applies_if`.

   The engine strips the block and appends a "Covers ..." clause to the
   description. The clause names the active sections, or the member rules for a
   skill without sections. The engine keeps the description within 300 characters.
   After the body, it renders the navigation: "How to use this skill", then
   `## Rules` with one heading per active section, then `## References and examples`.

   The body is the skill's intro and a short quick reference. It never lists the
   rules or references, and never names a rule id. It holds no Jinja and no markdown
   links.
3. Put optional helpers in `scripts/`, optional long-form material in `references/`
   and runnable example code in `examples/`. Sync copies `SKILL.md`, `scripts/`,
   `references/` and `examples/`, and renders `rules/`.

   Make scripts executable. Keep Python scripts stdlib-only and valid on Python
   3.10, because they run in consumer repos. Ruff lints them at that target. A
   script exits with code 2 on a usage error, as in this example:

   ```python
   #!/usr/bin/env python3
   """Print the candidates for the agent to judge, as a JSON array."""

   from __future__ import annotations

   import json
   import sys


   def main(argv: list[str]) -> int:
       """Scan each path in ``argv`` and print what was found."""
       if not argv:
           print("usage: scan.py PATH [PATH ...]", file=sys.stderr)
           return 2
       print(json.dumps([{"file": path, "line": 1} for path in argv]))
       return 0


   if __name__ == "__main__":
       raise SystemExit(main(sys.argv[1:]))
   ```

4. Update the pinning tests in the same change. Each plugin's gates under
   `tests/plugins/` pin its skill inventory. Each core skill has its own pins module
   in `tests/core_skill_pins/`, which `tests/integration/test_core_skills.py` reads.

The `superpowers` plugin is vendored. Its upstream files must stay byte-identical,
and ruff never touches that directory. Add new skills to a plugin of your own
instead.

## Add a bundled plugin

A bundled plugin is an opt-in layer that ships inside the engine. It is pure
content, so there is no Python file to write. Create `plugins/<name>/`, and the
plugin is usable as `coding_agent_playbook.plugins.<name>` with no change outside
`catalog/`.

The plugin directory must follow the leaf rule. `<name>` must be a Python
identifier, as `str.isidentifier()` defines it: letters, digits and underscores, not
starting with a digit. It must not start with `_` or `.`. Use `mattpocock_skills`,
not `mattpocock-skills`. The engine ignores any other directory here, and a content
gate fails CI on it. Consumers must spell the name with exactly the same case.

The plugin directory must also hold:

- at least one kind directory: `skills/`, `rules/`, `prompts/`, `hooks/` or
  `eval_samples/`
- a `README.md` that says, as plain prose with no URL, what the plugin is and how to
  enable it: `overlays_enabled = ["coding_agent_playbook.plugins.<name>"]`
- an `ATTRIBUTIONS.md` when any idea or text comes from a third party, and the
  upstream `LICENSE` when the text is vendored

To try the plugin, run this command in an empty scratch directory:

```bash
playbook init --non-interactive --name demo --kind python-library --overlays coding_agent_playbook.plugins.<name> </dev/null
```

CI gates every directory under `plugins/` with no test edit, because the gates read
the directory listing rather than a list of plugin names. There are three gates:

| Gate | What it checks |
| --- | --- |
| URL and source-name scan | Every file of the plugin, its root files included, must hold no URL. Every file except its root `ATTRIBUTIONS.md` must also name none of the distilled sources the scan knows. |
| Link gate | The suite runs `playbook validate`'s link check with every bundled plugin enabled. Each markdown link in the plugin's `rules/`, `prompts/`, `skills/` and `hooks/` must resolve inside `plugins/<name>/`, so a link into `core/` or into another plugin fails. |
| Layout guards | The leaf rule, at least one kind directory, and no link to a layer-root file. |

A vendored plugin, whose upstream text must stay byte-identical, may be left out of
the URL and source-name scan. The only way to do that is one commented allowlist,
`_VENDORED_PLUGIN_GATES` in `tests/integration/test_resources_self_contained.py`.
Each entry names the dedicated test that scans that plugin instead, and that test
must check every file for URLs. Today the only entry is `superpowers`, whose
upstream markdown holds bare-domain URLs in code samples. Its gate is
`tests/plugins/test_superpowers_self_contained.py`. The link gate has no allowlist.

## Editions and releases

Every consumer repo renders the current text of the release it installed, so edit
only the current text: the files under `core/` and `plugins/`. ADR 0012 records why.

- `catalog/editions/` holds the frozen editions that pinned eval samples grade, and
  `catalog/releases/` holds each release's manifest, notes and metrics. The release
  script generates both. Never edit them by hand: CI fails when an edition differs
  from its release tag, and the generated `catalog/editions/README.md` sends you to
  the same path under `catalog/core/`.
- A pull request that changes shipped rules, prompts, skills or hooks must have a
  title of type `feat` or `fix`, or carry `!` for a breaking change, such as a
  removed or renamed id. The release version is computed from these titles.
- There is no per-artifact version field to bump. The engine computes a content
  digest for each artifact instead.

## Run the gate

CI runs these four commands from the repository root. Run them all before you push:

```bash
ruff check .
ruff format --check .
mypy
pytest -q
```

Run them inside the dev environment. Set it up with `uv sync --extra dev`, then
prefix each command with `uv run`.

CI runs pytest in parallel, as `pytest -q -n auto --dist worksteal`. It uses
pytest-xdist, which is in the dev extra. Running in parallel does not change the
result. To reproduce a failure seen only in CI, run pytest with
`-n 4 --dist worksteal`.

On a pull request whose changes are all skill content (`catalog/core/skills/`,
`catalog/core/ATTRIBUTIONS.md`, `tests/core_skills/`, `tests/core_skill_pins/`),
CI's pytest step runs only `pytest -m catalog`, without coverage. This is the
skill lane of ADR 0010. The other steps run as usual, and the `ci:full` label
runs the whole suite. So a test that depends on skill content must carry the
`catalog` marker. A guard test fails when a test module that imports the skill
helpers lacks it, unless the guard's exemption list names it with a reason. The
skill helpers are the core skill pins, `tests/_core_skill_layout.py`,
`tests/core_skills`, and the skill names of `tests/_catalog.py`. Every test module
under `tests/core_skills/` or `tests/core_skill_pins/` needs the marker too.

CI's `ruff format --check .` also formats the Python code blocks inside markdown,
including the ones in this guide. The pytest suite validates the shipped content:

- link containment and self-containment for `core/` and every bundled plugin (see
  "Add a bundled plugin")
- every eval sample's gate
- the skill inventory that `mattpocock_skills` and `superpowers` each pin

If you run `pre-commit install`, every commit formats markdown the way CI does. A
commit that touches `catalog/` also runs the catalog checks (`pytest -m catalog`),
in parallel with `-n auto`. These pre-commit hooks run only a subset of the suite,
so the four commands above stay the source of truth.

The documentation site builds from `docs/` with the `docs` extra. CI runs the same
script, in the GitHub docs workflow and in the `docs` and `pages` jobs of
`.gitlab-ci.yml` on a GitLab copy, and any warning fails the build. These commands build the site and
serve a local preview:

```bash
uv sync --extra dev --extra docs
uv run scripts/build_docs.py --serve    # build, then preview on http://127.0.0.1:8000/
```
