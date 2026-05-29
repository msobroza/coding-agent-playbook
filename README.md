# coding-agent-playbook
Multi-harness playbook engine

## Status

Early scaffolding (PR 1). The package skeleton, dev tooling, and the public
`Adapter` / `ArtifactSource` / `StateSource` ABCs are in place; behavior lands
in later PRs. See `SPEC.md` for the full design and `specs/pr1-scaffolding.md`
for the current PR's plan.

```bash
uv sync --extra dev   # install engine + dev tools
uv run pytest         # run the test suite
uv run cap --version  # smoke-test the CLI
```

## Pre-commit integration

`coding-agent-playbook` ships a `.pre-commit-hooks.yaml` so consumer repos can wire `cap sync --check` into their pre-commit pipeline directly:

```yaml
# In your repo's .pre-commit-config.yaml:
- repo: https://github.com/msobroza/coding-agent-playbook
  rev: v0.1.0a0     # pin to a released tag
  hooks:
    - id: cap-sync-check
```

After `pre-commit install`, every commit verifies that the generated `.continue/`, `.claude/`, `.opencode/`, and `AGENTS.md` files match what the engine would produce. Drift fails the commit with a pointer to run `cap sync` to regenerate.

`cap init` writes a starter `.pre-commit-config.yaml` for you — see SPEC.md §13.2.

### Hooks

| Hook ID | When it runs | What it does |
| --- | --- | --- |
| `cap-sync-check` | Every commit | Runs `cap sync --check`; fails the commit on drift. Consumer-facing. |
| `cap-validate` | Manual only (`pre-commit run --hook-stage manual cap-validate`) | Runs `cap validate`; surfaces canonical-source mistakes (typo'd `applies_if` keys, orphan eval tasks, etc.). Overlay-author-facing. |
