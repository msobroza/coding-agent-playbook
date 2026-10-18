# Contributing content

Everything the engine ships as playbook content lives here: rules, prompts,
eval tasks, lifecycle hooks and skills. You never need to touch the Python
package (`src/coding_agent_playbook/`) to add or change content. The build
copies this whole tree into the wheel, so what you commit here is what
`pip install coding-agent-playbook` ships.

The terms this guide uses (always rule, scoped rule, member rule, skill,
reference, layer, core, bundled plugin) mean what `CONTEXT.md` at the
repository root says. That file is the project's only glossary; it is not part
of the catalog, so never link to it from content.

## Where each kind lives

```text
catalog/
├── README.md                 this guide (ships in the wheel, never synced)
├── core/                     the engine layer: always on in every consumer repo
│   ├── ATTRIBUTIONS.md       credit for ideas distilled from third-party sources
│   ├── rules/                always/, languages/python/, frameworks/, ml/
│   ├── prompts/              one <id>.md or <id>.md.j2 per prompt
│   ├── hooks/                one <category>/<id>/HOOK.md per lifecycle hook
│   ├── skills/               one <id>/SKILL.md per core skill; its
│   │                         references come from the rules that name it
│   └── eval_tasks/           one <task-id>/ per task, plus ATTRIBUTIONS.md
└── plugins/                  bundled plugins: off until a consumer enables one
    └── <name>/
        ├── README.md         what the plugin is and how to enable it
        ├── ATTRIBUTIONS.md   credit for a third-party source, if any
        ├── LICENSE           only for vendored third-party text
        └── skills/           one <dir>/SKILL.md per skill, plus scripts/, references/
```

`core/` ships four skills, `python-coding`, `python-testing`, `python-tooling`
and `ml-data`. Each one's references are rendered from the scoped rules that
name it. Only a skill that declares a `playbook:` block takes rules, so the
skills of `superpowers` and `python_design` own none. A bundled plugin may also
hold `rules/`, `prompts/`, `hooks/` or `eval_tasks/`, laid out exactly as in
`core/`.

The files at a layer root (`README.md`, `LICENSE`, `ATTRIBUTIONS.md`) sit
outside every kind directory, so sync never copies them into a consumer repo.
Never link to one from a rule, prompt or skill: the link would break in every
consumer repo, and CI refuses it.

Two rules keep the content self-contained:

- **No URLs, and links stay in their layer.** No file in this tree holds a
  URL: no `scheme://`, `www.`, `mailto:` or `git@host:` form, and no bare domain
  followed by a path. The exceptions are the license URI in
  `core/eval_tasks/ATTRIBUTIONS.md` and a vendored plugin's upstream text (see
  "Add a bundled plugin"). A markdown link in a rule, prompt, skill or hook
  must resolve to a file inside the same layer (`core/`, or `plugins/<name>/`).
- **Distilled content never names its source plugin.** When rules, prompts or
  skills distill ideas from a third-party plugin (the engine's own `core/`, or a
  distilled plugin such as `python_design`), the credit goes in the layer
  root's `ATTRIBUTIONS.md` and nowhere else. CI scans every other file of
  `core/` and of every bundled plugin for the names of the sources the scan
  knows (today, `python_design`'s source). Distilling from a new source means
  adding its name to `_PLUGIN_MARKER_RE` in
  `tests/integration/test_resources_self_contained.py`. A vendored plugin such
  as `superpowers` is exempt: it keeps its upstream wording, source name
  included.

Rule, prompt and skill sources use `.md` when the body is plain text, and
`.md.j2` only when the body needs Jinja (detector facts such as
`{{ project_name }}`, or `{{ rule("<id>") }}` in a prompt). The overlay merge
key is the frontmatter `id`, not the file name. A later layer (an overlay, then
the consumer's `playbook/`) replaces an artifact with the same `id`.

## Add a rule

1. Create `core/rules/<group>/<file>.md`, where `<group>` is `always/`,
   `languages/python/`, `frameworks/` or `ml/`.
2. Give it frontmatter with `id` (unique across every layer), `name`,
   `description`, `version` and `scope` (`always` or `scoped`). A scoped rule
   also names the skill that delivers it in `skill:` (`playbook validate`
   fails on a scoped rule without one), which an always rule must not carry;
   the skill must exist after the layer merge, so an overlay or a
   consumer's `playbook/rules/` may name a core skill. Add `globs` for a scoped
   rule, `applies_if` to gate it on detector facts, `priority` (lower comes
   first; the default is 50) and `tags`. SPEC §6.1 has the full schema.
3. For a scoped rule, pick the skill by topic: `python-coding` when no library
   is needed, `python-testing` for tests, `python-tooling` for one named
   framework or tool, `ml-data` for ML and data libraries. Write `description`
   as the one actionable line the skill's references index shows for the rule,
   and keep `name` a short topic label (`Typing`, `Error handling`): it is the
   rule's label in the skill's "Covers ..." clause. Add the rule to
   `EXPECTED_MEMBERSHIP` in `tests/integration/test_core_skills.py`.
4. Keep the body to guidance an assistant can act on. A rule cannot call
   `{{ rule(...) }}`.

## Add a prompt

1. Create `core/prompts/<id>.md`.
2. Give it frontmatter with `id`, `name`, `description`, `version` and `slash`
   (the slash-command name). Optional keys: `applies_if`, `input_variables`,
   `includes_rules` (rule ids to inline) and `eval_tasks` (the ids of the tasks
   that test it). SPEC §6.2 has the full schema.
3. Every `{{ rule("<id>") }}` in the body must be listed in `includes_rules`.

## Add an eval task

1. Create `core/eval_tasks/<task-id>/task.toml` with `id`, `prompt_id`,
   `description`, `version`, `[setup]`, `[invocation]`, and the `[gate]` /
   `[rubric]` / `[verdict]` layers (SPEC §6.5.3).
2. Put the starting repo in `setup/`, including a `setup/pyproject.toml` when
   the task depends on detector facts.
3. Ship a reference answer in `solution/`. For an edit task, mirror `setup/`
   paths with the files a correct agent would write. For a review-only task,
   write the answer to `solution/transcript.md`. Put known-wrong attempts in
   `solution/negatives/`; a review-only task needs at least one. CI proves the
   gate fails on the untouched `setup/` and on every negative, and passes on the
   solution.
4. Add the task id to the `eval_tasks:` list of the prompt named by
   `prompt_id`. A task finds its prompt in the `prompts/` directory next to its
   layer's `eval_tasks/`, so a core task uses `core/prompts/`.
5. Credit third-party fixture code in `core/eval_tasks/ATTRIBUTIONS.md`.

Eval tasks belong to a layer, like every other kind. A bundled plugin ships
its own in `plugins/<name>/eval_tasks/<task-id>/`, laid out as above, and each
of its tasks finds its prompt in `plugins/<name>/prompts/`. Its tasks are
listed by `playbook eval --list` only in a repo that enables the plugin. Ruff
never lints or reformats `setup/` in either home
(`core/eval_tasks/*/setup` and `plugins/*/eval_tasks/*/setup`), and mypy never
reads this tree.

## Add a hook

1. Create `core/hooks/<category>/<id>/HOOK.md`, where `<category>` is
   `protect/`, `verify/`, `feedback/`, `safety/` or `audit/`. The directory
   name is the hook id; the category folder carries no meaning.
2. Give it frontmatter with `id`, `name`, `description`, `version`, `tier`,
   `events`, `handler`, `decisions` (only `deny`, `ask`, `context` or `none`),
   `timeout`, `on_error` and `supports`, plus `matcher`, `priority` and `tags`
   as needed. Engine hooks name a builtin handler (`handler: {builtin: <name>}`)
   and ship no `scripts/`. SPEC §6.6.7 has the full schema, and
   `playbook validate` checks the hook trust contract H1-H21.
3. Write the body as guidance an assistant can act on: an assistant without
   native hooks receives it as advisory text.
4. The gates under `tests/hooks/` pin the shipped hooks: one test module per
   hook, plus the `test_pack_*_manifest.py` rows. Update them in the same change.

The Claude Code launcher and the OpenCode plugin that run the hooks are engine
wiring, not content: their templates stay in the package, under
`src/coding_agent_playbook/templates/hook_shims/`.

## Add a skill

1. Pick its layer: `core/skills/<id>/` for a skill that owns rules in core,
   otherwise the bundled plugin it belongs to, or a new one (below).
2. Create `<layer>/skills/<dir>/SKILL.md`. Its frontmatter must declare
   `id`, which must match `^[a-z0-9]+(-[a-z0-9]+)*$` (at most 64 characters) and
   becomes the output directory name. It also needs a `description` of 1 to
   1024 characters.
   - A skill that owns rules (every core skill) gives `id`, `name` and the
     directory the same value, writes `description` as one third-person
     capability sentence without "Use when", and declares a `playbook:` block
     with `use_when` (the condition only: the engine writes "Use when
     <use_when>.") and `files` (a file-kind phrase of at most 80 characters with
     no trailing period, for the "Where guidance lives" map). The engine strips
     the block, appends a "Covers ..." clause naming the active member rules and
     a generated `## References` index, and keeps the result within 300
     characters. The body says what the skill is for and how to pick a
     reference; it never lists the references, never names a rule id, and holds
     no Jinja and no markdown links.
3. Put optional helpers in `scripts/` and optional long-form material in
   `references/`. Sync copies only `SKILL.md`, `scripts/` and `references/`.
   Make scripts executable. Keep Python scripts stdlib-only and valid on
   Python 3.10, because they run in consumer repos; ruff lints them at that
   target. Exit 2 on a usage error:

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

4. Each plugin's gates under `tests/plugins/` pin its skill inventory, and
   `tests/integration/test_core_skills.py` pins the core one. Update them in
   the same change.

The `superpowers` plugin is vendored: its upstream files must stay
byte-identical, and ruff never touches that directory. Add new skills to a
plugin of your own instead.

## Add a bundled plugin

A bundled plugin is pure content: there is no Python file to write. Create
`plugins/<name>/` and it is usable as `coding_agent_playbook.plugins.<name>`
with no change outside `catalog/`.

- **The leaf rule.** `<name>` must be a Python identifier (`str.isidentifier()`:
  letters, digits and underscores, not starting with a digit) and must not start
  with `_` or `.`. Use `python_design`, not `python-design`. The engine ignores
  any other directory here, and a content gate fails CI on it. Consumers must
  spell the name with exactly the same case.
- **At least one kind directory:** `skills/`, `rules/`, `prompts/`, `hooks/`
  or `eval_tasks/`.
- **A `README.md`** saying what the plugin is and how to enable it, as plain
  prose with no URL:
  `overlays_enabled = ["coding_agent_playbook.plugins.<name>"]`.
- **An `ATTRIBUTIONS.md`** when any idea or text comes from a third party, and
  the upstream `LICENSE` when the text is vendored.

To try it, run `playbook init --non-interactive --name demo --kind python-library --overlays coding_agent_playbook.plugins.<name> </dev/null`
in an empty scratch directory.

CI gates every directory under `plugins/` with no test edit, because the gates
read the directory listing rather than a list of plugin names:

- **URL and source-name scan:** every file of the plugin, its root files
  included, must hold no URL. Every file except its root `ATTRIBUTIONS.md` must
  also name none of the distilled sources the scan knows.
- **Link gate:** the suite runs `playbook validate`'s link check with every
  bundled plugin enabled. Each markdown link in the plugin's `rules/`,
  `prompts/`, `skills/` and `hooks/` must resolve inside `plugins/<name>/`, so a
  link into `core/` or into another plugin fails.
- **Layout guards:** the leaf rule, at least one kind directory, and no link to
  a layer-root file.

A vendored plugin, whose upstream text must stay byte-identical, may be left out
of the URL and source-name scan only through one commented allowlist:
`_VENDORED_PLUGIN_GATES` in `tests/integration/test_resources_self_contained.py`.
Each entry names the dedicated test that scans that plugin instead, and that
test must check every file for URLs. Today the only entry is `superpowers`,
whose upstream markdown holds bare-domain URLs in code samples; its gate is
`tests/plugins/test_superpowers_self_contained.py`. The link gate has no
allowlist.

## Run the gate

CI runs four commands from the repository root. Run them all before you push:

```bash
ruff check .
ruff format --check .
mypy
pytest -q
```

Run them inside the dev environment (`uv sync --extra dev`, then prefix each
with `uv run`). CI's `ruff format --check .` also formats the Python code
blocks inside markdown, this guide's included. The pytest suite validates the
shipped content: link containment and self-containment for `core/` and every
bundled plugin (see "Add a bundled plugin"), every eval task's gate, and the
skill inventory that `python_design` and `superpowers` each pin.

With `pre-commit install`, every commit formats markdown the way CI does, and a
commit that touches `catalog/` also runs the catalog checks (`pytest -m catalog`).
The hooks run a subset of the suite, so the four commands above stay the source
of truth.
