# coding-agent-playbook
Multi-harness playbook engine

## Status

Engine and CLI are implemented: detector, renderer, the four adapters
(Continue, Claude Code, OpenCode, AGENTS.md), the `cap` commands
(`init` / `sync` / `check` / `validate` / `render` / `eval`), and the Tier 0
eval schema. See `SPEC.md` for the full design.

Working on the engine itself:

```bash
uv sync --extra dev   # install engine + dev tools
uv run pytest         # run the test suite
uv run cap --version  # smoke-test the CLI
```

## Using the playbook in an external repo

Add the playbook to any repo that should get generated assistant context
(`.continue/`, `.claude/`, `.opencode/`, `AGENTS.md`) from the canonical rules
and prompts.

### 1. Install

Install the engine as a dev dependency, plus any organization overlay packages
that ship your team's rules and prompts:

```bash
uv add --dev coding-agent-playbook            # the engine (generic content)
uv add --dev playbook-rules-<org>             # optional: your org's overlay
```

`pip` works too: `pip install coding-agent-playbook`.

### 2. Initialize

```bash
cap init
```

`cap init` detects your stack, then writes:

- `.coding-agent-playbook.toml` — the committed project config (below);
- `.coding-agent-playbook.local.toml` — personal per-engineer overrides
  (gitignored automatically);
- a merged `.pre-commit-config.yaml` and installs the hooks;
- and runs `cap sync` once to generate the initial artifacts.

### 3. Generate

```bash
cap sync     # regenerate .continue/, .claude/, .opencode/, AGENTS.md
```

`cap sync` is the workhorse — re-run it (or let the pre-commit hook run it)
whenever the canonical source or your dependencies change. `AGENTS.md` is always
generated regardless of which adapters are enabled.

### 4. Define which resources apply

Three layers compose, later overriding earlier **by artifact `id`** (SPEC §11):

1. **Engine generic content** — ships with `coding-agent-playbook`.
2. **Overlay packages** — installed org packages, enabled (and ordered) in config.
   They're auto-discovered through Python entry points; you just list them:

   ```toml
   # .coding-agent-playbook.toml
   schema_version = 1

   [project]
   name = "risk-models"
   kind = "python-application"          # python-library | ml-research | notebook
   description = "Counterparty risk scoring service"

   [overlays]
   enabled = ["playbook_rules_bnp"]     # ordered; later wins on id collision

   [adapters]
   enabled = ["continue", "claude_code", "opencode"]   # AGENTS.md always emitted
   ```

3. **Repo-local `playbook/`** — drop in per-repo rules, prompts, or eval tasks;
   anything here wins on `id` collision:

   ```text
   playbook/
   ├── rules/         # add a new rule, or override one by reusing its id
   ├── prompts/
   └── eval_tasks/
   ```

Not every resource renders everywhere: the detector inspects the repo and each
artifact's `applies_if` predicate gates it (a FastAPI rule won't ship to a
non-FastAPI repo; the ML serialization-security rule ships only to repos with an
ML stack). Run `cap check` to see the detected facts and exactly which
rules/prompts are active — the fastest way to debug *"why isn't my rule
appearing?"*

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
