# coding-agent-playbook
Multi-harness playbook engine

## What it is

coding-agent-playbook keeps your coding-assistant guidance (rules, prompts, skills
and lifecycle hooks) in one place and renders it into the files each assistant
reads: Claude Code, OpenCode, Codex, Continue and every `AGENTS.md` reader. A
detector keeps only what applies to your repository, and the generated files stay
out of git. Nothing reaches the network except [`playbook forge`](docs/checks.md#playbook-forge),
which runs `gh` or `glab` when someone calls it.

```text
 sources                  playbook sync                         outputs
 catalog/core/       ─┐   resolve by id (later layer wins)      AGENTS.md (every AGENTS.md reader)
 bundled plugins     ─┤   keep what applies (detector)          .claude/, .opencode/
 overlays            ─┼─► render (sandboxed Jinja)        ────► .agents/skills/<id>/{SKILL.md,rules/}
 playbook/ (local)   ─┘   write generated files, never commit   .continue/ (when enabled)
                                                                hooks: one playbook-hook dispatcher
```

## Install

Add the engine as a dev dependency (Python 3.12+):

```bash
uv add --dev "coding-agent-playbook @ git+https://github.com/msobroza/coding-agent-playbook"
```

With an internal index configured, `uv add --dev coding-agent-playbook` works the
same way. Install the engine in each project rather than as a global tool, because
the hooks pin the project's interpreter.

## Set up a repo

```bash
playbook init --framework superpowers   # or mattpocock, or none (the default)
pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge
playbook sync                           # writes AGENTS.md, .claude/, .opencode/, .agents/skills/
```

`init` detects your stack, asks whether to turn on the lifecycle hooks and writes
the committed `.coding-agent-playbook.toml`. Commit that file together with
`.gitignore` and `.pre-commit-config.yaml`. Never commit the generated output.

Two optional top-level config keys are worth knowing. `platforms = ["domino"]`
turns the Domino skills on before the repo has Domino markers. A `[layout]` table,
such as `specs = "specs"`, tells the frameworks where the repo keeps its specs and
plans. To add your own rules, prompts and skills, create a `playbook/` directory
(`mkdir playbook`): it is a local layer, and its content wins over the engine's by id.

A core skill's member rules are written to its `rules/` directory, for example
`.claude/skills/<skill>/rules/` (unrelated to Claude Code's `.claude/rules/`).
[docs/skills.md](docs/skills.md#rules-inside-skills) lists the core skills.
Continue gets each rule as its own file but no license file, so the vendored MIT
notices reach only the skill roots.

## Keep it current

After you clone the repo, run `playbook sync` once. From then on the git hooks
re-run it after every checkout and pull. Run it by hand after you edit
`playbook/` or the config, and run `playbook check` to see the detected facts and
what is active. After an engine upgrade, read `MIGRATION.md`.

## Contribute to the catalog

A scoped rule goes in the `rules/` directory of the skill that owns its topic,
`catalog/core/skills/<skill>/rules/<id>.md`. The always rules live in
`catalog/core/rules/always/`. A minimal rule is frontmatter followed by
Description, Bad Example, Good Example and Notes; "Writing a rule" in
`catalog/README.md` lists the keys and gives the template.

Before you push, run `ruff check .`, `ruff format --check .`, `mypy` and
`pytest -q` inside `uv sync --extra dev`. CI runs pytest in parallel with
`-n auto --dist worksteal` ("Run the gate" in `catalog/README.md`), and only the
catalog checks on a skill-only PR ([ADR 0010](docs/adr/0010-skill-only-pull-requests-run-only-the-catalog-checks.md)). PR titles follow Conventional Commits (`feat(catalog): ...`), which commitizen checks.

## Links

- [Documentation site](https://msobroza.github.io/coding-agent-playbook/): these pages and the reference.
- [Overview](docs/overview.md): why, status, architecture, engine packages.
- [Setting up a repo](docs/setup.md): install, init, sync, config layers.
- [Skills and bundled plugins](docs/skills.md): skill roots, core skills, plugins.
- [Hooks](docs/hooks.md): pre-commit hooks and assistant lifecycle hooks.
- [Checks and evals](docs/checks.md): metrics, commitizen, `playbook ci` (GitHub
  Actions, GitLab CI), `playbook forge`, evals.
- [Contributor guide](catalog/README.md), [glossary](CONTEXT.md), [design](SPEC.md),
  [migration notes](MIGRATION.md), [decision records](docs/adr/). Consumer repos
  keep their own documents in one layout under `docs/` (`docs/specs/`,
  `docs/plans/`, `docs/adr/`), set by `[layout]`.
