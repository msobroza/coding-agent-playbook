# coding-agent-playbook
Multi-harness playbook engine

## What it is

One source of coding-assistant guidance (rules, prompts, skills, lifecycle
hooks) rendered into what each assistant reads: Claude Code, OpenCode, Codex,
Continue and every `AGENTS.md` reader. A detector keeps only what applies to the
repo, generated files stay out of git, and nothing reaches the network except
[`playbook forge`](docs/checks.md#playbook-forge), which runs `gh` or `glab` when
someone calls it.

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

From an internal index, `uv add --dev coding-agent-playbook` with that index
configured works the same way. Install it per project, not as a global tool:
the hooks pin the project's interpreter.

## Set up a repo

```bash
playbook init --framework superpowers   # or mattpocock, or none (the default)
pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge
playbook sync                           # writes AGENTS.md, .claude/, .opencode/, .agents/skills/
```

`init` detects the stack, asks about the lifecycle hooks and writes the
committed `.coding-agent-playbook.toml`. Commit that file, `.gitignore` and
`.pre-commit-config.yaml`, never the generated output. Top-level config keys:
`platforms = ["domino"]` turns the Domino skills on before the repo has
Domino markers, and a `[layout]` table (for example `specs = "specs"`) points
the frameworks at a repo that keeps its specs or plans elsewhere. A `playbook/`
directory (`mkdir playbook`) starts a local layer whose rules, prompts and skills
win over the engine's by id.

A core skill's member rules land in its `rules/` directory
(`.claude/skills/<skill>/rules/`, unrelated to Claude Code's `.claude/rules/`);
[docs/skills.md](docs/skills.md#rules-inside-skills) lists the core skills. Continue gets each rule as its own file but no license file,
so the vendored MIT notices reach only the skill roots.

## Keep it current

After a clone, run `playbook sync` once; the git hooks re-run it after every
checkout and pull. Run it by hand after editing `playbook/` or the config, and
`playbook check` to see the detected facts and what is active. After an engine
upgrade, read `MIGRATION.md`.

## Contribute to the catalog

- **Where a rule goes:** a scoped rule goes in the `rules/` directory of the
  skill that owns its topic (`catalog/core/skills/<skill>/rules/<id>.md`); the
  always rules live in `catalog/core/rules/always/`.
- **A minimal rule:** frontmatter, then Description, Bad Example, Good Example
  and Notes; `catalog/README.md` ("Writing a rule") lists the keys and has the
  template.
- **The commands to run:** `ruff check .`, `ruff format --check .`, `mypy` and
  `pytest -q`, inside `uv sync --extra dev`; CI runs pytest in parallel with
  `-n auto --dist worksteal` (`catalog/README.md`, "Run the gate"). A pull
  request that changes nothing but skill content runs only the catalog checks in
  its pytest step, the skill lane of [ADR 0009](docs/adr/0009-skill-only-pull-requests-run-only-the-catalog-checks.md).
- **PR titles** follow Conventional Commits (`feat(catalog): ...`); commitizen
  checks them.

## Links

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
