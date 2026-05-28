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
