# Contributing content

Everything the engine ships as playbook content lives here: rules, prompts,
eval tasks and skills. You never need to touch the Python package
(`src/coding_agent_playbook/`) to add or change content. The build copies this
whole tree into the wheel, so what you commit here is what
`pip install coding-agent-playbook` ships.

## Where each kind lives

```text
content/
├── README.md                 this guide (ships in the wheel, never synced)
├── core/                     the engine layer: always on in every consumer repo
│   ├── ATTRIBUTIONS.md       credit for ideas distilled from third-party sources
│   ├── rules/                always/, languages/python/, frameworks/, ml/
│   ├── prompts/              one <id>.md or <id>.md.j2 per prompt
│   └── eval_tasks/           one <task-id>/ per task, plus ATTRIBUTIONS.md
└── plugins/                  bundled plugins: off until a consumer enables one
    └── <name>/
        ├── README.md         what the plugin is and how to enable it
        ├── ATTRIBUTIONS.md   credit for a third-party source, if any
        ├── LICENSE           only for vendored third-party text
        └── skills/           one <dir>/SKILL.md per skill, plus scripts/, references/
```

`core/` ships no skills: every bundled skill belongs to a bundled plugin. A
bundled plugin may also hold `rules/`, `prompts/` or `eval_tasks/`, laid out
exactly as in `core/`.

The files at a layer root (`README.md`, `LICENSE`, `ATTRIBUTIONS.md`) sit
outside every kind directory, so sync never copies them into a consumer repo.
Never link to one from a rule, prompt or skill: the link would break in every
consumer repo, and CI refuses it.

Two rules keep the content self-contained:

- **No URLs, and links stay in their layer.** No file in this tree holds a
  URL: no `scheme://`, `www.`, `mailto:` or `git@host:` form, and no bare domain
  followed by a path. The exceptions are the license URI in
  `core/eval_tasks/ATTRIBUTIONS.md` and a vendored plugin's upstream text (see
  "Add a bundled plugin"). A markdown link in a rule, prompt or skill must
  resolve to a file inside the same layer (`core/`, or `plugins/<name>/`).
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
   `description`, `version` and `scope` (`always` or `scoped`). Add `globs`
   for a scoped rule, `applies_if` to gate it on detector facts, `priority`
   (lower comes first; the default is 50) and `tags`. SPEC §6.1 has the full
   schema.
3. Keep the body to guidance an assistant can act on. A rule cannot call
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

## Add a skill

1. Pick the bundled plugin it belongs to, or add a new one (below).
2. Create `plugins/<name>/skills/<dir>/SKILL.md`. Its frontmatter must declare
   `id`, which must match `^[a-z0-9]+(-[a-z0-9]+)*$` (at most 64 characters) and
   becomes the output directory name. It also needs a `description` of 1 to
   1024 characters.
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

4. Each plugin's gates under `tests/plugins/` pin its skill inventory. Update
   them in the same change.

The `superpowers` plugin is vendored: its upstream files must stay
byte-identical, and ruff never touches that directory. Add new skills to a
plugin of your own instead.

## Add a bundled plugin

A bundled plugin is pure content: there is no Python file to write. Create
`plugins/<name>/` and it is usable as `coding_agent_playbook.plugins.<name>`
with no change outside `content/`.

- **The leaf rule.** `<name>` must be a Python identifier (`str.isidentifier()`:
  letters, digits and underscores, not starting with a digit) and must not start
  with `_` or `.`. Use `python_design`, not `python-design`. The engine ignores
  any other directory here, and a content gate fails CI on it. Consumers must
  spell the name with exactly the same case.
- **At least one kind directory:** `skills/`, `rules/`, `prompts/` or
  `eval_tasks/`.
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
  `prompts/` and `skills/` must resolve inside `plugins/<name>/`, so a link into
  `core/` or into another plugin fails.
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
with `uv run`). It takes four commands rather than one because local pre-commit
ruff-formats only Python files, while CI's `ruff format --check .` also formats
the Python code blocks inside markdown, this guide's included. The pytest suite
validates the shipped content: link containment and self-containment for `core/`
and every bundled plugin (see "Add a bundled plugin"), every eval task's gate,
and the skill inventory that `python_design` and `superpowers` each pin.
