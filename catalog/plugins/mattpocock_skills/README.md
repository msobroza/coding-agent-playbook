# mattpocock_skills (bundled plugin)

Vendored content of Matt Pocock's engineering and productivity skills: 26
skills, pinned to upstream v1.3.1 and kept near-verbatim. The skills are
MIT-licensed; `LICENSE` next to this file holds the notice, and
`ATTRIBUTIONS.md` records the provenance and every change from upstream (the
renames, the removed imposed tools, the reworded harness built-ins, the
user-invoked guard line and the glossary fallback).

## Enable it

The plugin ships with the engine and is off by default. List it in the
consumer repo's `.coding-agent-playbook.toml`, as a top-level key above the
first `[table]` header, then run `playbook sync`:

```toml
overlays_enabled = ["coding_agent_playbook.plugins.mattpocock_skills"]
```

The plugin is a spec-driven framework (`framework.toml`), so
`framework = "mattpocock"` (what `playbook init --framework mattpocock`
writes) enables it the same way.

Then, once per repo:

- Run `/setup-matt-pocock-skills`. It writes `docs/agents/issue-tracker.md`,
  `docs/agents/triage-labels.md` and `docs/agents/domain.md`, the tracker,
  label and domain configuration the other skills read. On a repo that pushes
  to GitHub or GitLab it proposes the Forge issues tracker, which reaches the
  forge only through `playbook forge`; otherwise local markdown. The plugin
  always rule (`mattpocock-skills-tracker`) points the agent at these files and
  asks it to tell you to run setup when a skill needs one that is missing.
- Add `.scratch/` to the repo's `.gitignore`: it holds only throwaway
  prototypes, untracked and never staged or committed. The local issue tracker
  keeps its specs in `docs/specs/` and its maps and tickets in `docs/plans/`.

## User-invoked skills

Fifteen skills run only when you ask for them by name: `/ask-matt`,
`/grill-me`, `/grill-with-docs`, `/handoff`, `/implement`, `/implement-spec`,
`/improve-codebase-architecture`, `/retro`, `/setup-matt-pocock-skills`,
`/teach`, `/to-questionnaire`, `/to-spec`, `/to-tickets`, `/wait-what` and
`/wayfinder`. Their frontmatter sets `disable-model-invocation: true`, which
only Claude Code honours. In every other harness each of them starts with the
line "Run this only when the user asked for it by name; otherwise stop.", so
the model stops if it picks one up on its own.

The other eleven are model-invoked: the agent loads them when a task calls for
them, and the user-invoked skills load them by name.

## Harnesses

- **Claude Code** reads `.claude/skills/<id>/`.
- **Codex** and **OpenCode** read the shared skill root, `.agents/skills/<id>/`;
  the `opencode` adapter also writes `.opencode/skills/<id>/`.
- **Agent Harness** (opt-in) gets `skills/<id>/`, with the keys beyond `id`,
  `name` and `description` in `.playbook/manifest.toml`.
- **Continue** is opt-in: list the `continue` adapter to get one prompt per
  skill in `.continue/prompts/<id>.md`. These prompts are degraded: they carry
  only the `SKILL.md` body, without `references/`, `scripts/` or the licence
  copy, so the relative links in them dangle. `ATTRIBUTIONS.md` records what
  each skill loses there.

## Listing budget

Every session lists each enabled skill's description. The 26 descriptions of
this plugin cost about 3,800 characters of skill listing, within the 6,000
characters allowed for core plus one bundled plugin. Do not enable this plugin
together with superpowers: several skills overlap (see below), and the two
listings together exceed that budget.

## Coexistence

- With superpowers, these pairs cover the same ground; keep one side of each:
  - `tdd` and `test-driven-development`;
  - `diagnosing-bugs` and `systematic-debugging`;
  - `writing-for-agents` and `writing-skills`;
  - `two-axis-review` and `requesting-code-review` / `receiving-code-review`;
  - `grilling` and `brainstorming`.
- Core's `python-testing` skill, where core lists it, and `tdd` both shape how
  tests are written; `tdd` drives the red-green loop, `python-testing` the
  Python conventions.
- Core's `review` and `review-architecture` prompts overlap `two-axis-review`
  and `improve-codebase-architecture`.
- The upstream Claude Code plugin of these skills: disable it in any repo where
  this bundled plugin is enabled, or each skill appears twice.
- A personal skill with the same name outranks a project skill in Claude Code,
  so a personal skill named like one of these ids hides the synced copy there.

## Overriding and re-adding

A repo-local skill at `playbook/skills/<id>/` replaces the plugin skill with the
same id. The dropped `triage` skill can be added back the same way, at
`playbook/skills/triage/`; setup still writes the label vocabulary it needs.
