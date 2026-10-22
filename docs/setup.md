# Setting up a repo

Installing the engine in a consumer repo, initializing it, generating its output and choosing what applies. Back to the [README](../README.md).

## Using the playbook in an external repo

Add the playbook to any repo that should get generated assistant context
(`.claude/`, `.opencode/`, `AGENTS.md`, `.agents/skills/`, and `.continue/` when
enabled) from the
canonical rules, prompts, and skills.

### 1. Install

Install the engine as a dev dependency, plus any organization overlay packages
that ship your team's rules and prompts:

```bash
uv add --dev "coding-agent-playbook @ git+https://github.com/msobroza/coding-agent-playbook"   # the engine (generic content)
uv add --dev playbook-rules-<org>             # optional: your org's overlay
```

From an internal index, `uv add --dev coding-agent-playbook` works the same way;
`pip` works too: `pip install coding-agent-playbook`. The engine needs Python
3.12+. Install it per project, never with `uv tool install` or `pipx`: the
hooks pin the project's interpreter.

### 2. Initialize

```bash
playbook init
```

`playbook init` detects your stack, asks whether to enable the
[assistant lifecycle hooks](hooks.md#assistant-lifecycle-hooks) (`--no-hooks` skips
them), then writes:

- `.coding-agent-playbook.toml` — the committed project config (below),
  including `[output] commit = false` and your `[hooks] enabled` answer;
- `.coding-agent-playbook.local.toml` — personal per-engineer overrides
  (gitignored automatically);
- a merged `.pre-commit-config.yaml`;
- and runs `playbook sync` once to generate the initial artifacts (and the
  managed `.gitignore` block that keeps them out of git).

Without `--adapters`, `init` enables `claude_code`, `opencode` and
`shared_skills` (`AGENTS.md` is always written). Continue is opt-in since
v0.21: its upstream is in maintenance, and its IDE already reads `AGENTS.md`
and `.claude/skills/`. To enable it as well:

```bash
playbook init --adapters claude_code,opencode,shared_skills,continue
```

Codex needs no adapter: it reads `AGENTS.md` and `.agents/skills/`.

Choose the spec-driven framework with `playbook init --framework superpowers | mattpocock | none` (default `none`; it writes the committed `framework` key).

Choose the prompt set with the top-level key `prompts = "v1"` or `prompts = "v2"` (default `v1`). The v2 prompt set keeps the v1 names and `includes_rules` and also tells the agent which skills to load and how to check its work; switching changes only the prompt text, so the command list stays the same, and a prompt with no v2 twin in `prompts/v2/` keeps its v1 text. Eval samples keep grading v1; `playbook eval <id> --run --prompt-set v2` grades v2.

Then install the git hooks — all three hook types, so the auto-sync runs after
checkouts and pulls:

```bash
pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge
```

Commit `.coding-agent-playbook.toml`, `.pre-commit-config.yaml`, and
`.gitignore` — **not** the generated files.

### 3. Generate

```bash
playbook sync     # regenerate .claude/, .opencode/, AGENTS.md, .agents/skills/ (+ .continue/)
```

`playbook sync` is the workhorse. The generated output is **local-only**: it is
not in the repository, so **run `playbook sync` once right after cloning** (then
install the hooks as above). Output an earlier sync left behind — a skill you
removed, an adapter you disabled — is deleted when untouched, and otherwise kept
gitignored, so it can never slip into a commit. (`playbook sync --check` is for
the legacy committed-output flow and CI there; under the default it is only
meaningful in a working copy that has already been synced.) From then on the `post-checkout` / `post-merge`
hook re-runs it after every checkout and pull; run it by hand whenever you
change `playbook/` or the config. `AGENTS.md` is always generated regardless of
which adapters are enabled (as long as at least one always rule, Where line (a skill with member
rules and a `playbook.files` phrase, while an enabled adapter writes a skills root) or hook advisory applies). A member rule (one in a skill's `rules/`, or a scoped rule that names a skill with `skill:`) is not in it: it
arrives in that skill's `rules/` directory, and a generated `## Where guidance lives`
section maps file kinds to those skills (core ships eight Python skills, see "Rules inside skills" in [skills.md](skills.md#rules-inside-skills)).
Claude Code gets the same always-rule sections and the same map in `.claude/rules/coding-agent-playbook.md`,
which it loads natively; the generated `.claude/CLAUDE.md` is a rule-free stub, so
OpenCode v1 (which attaches that file when it reads under `.claude/`) never loads
the rules twice (SPEC §10.3.1). Any other `.claude/rules/` file is yours, and
`sync` exits 1 rather than overwrite a file of yours already named
`coding-agent-playbook.md` there, write over a hard link at it, or write through
a symlink on the way to it (a symlinked `.claude` or `.claude/rules`, or a link
at the file itself); a symlinked or hard-linked `.claude/CLAUDE.md` (such as a
link to `../AGENTS.md`) stops it the same way.

What `sync` does with git, by `[output] commit` in `.coding-agent-playbook.toml`:

- **`commit = false` (default)** — `sync` writes every generated path into a
  managed block of `.gitignore` (between
  `# >>> coding-agent-playbook (managed — do not edit) >>>` and
  `# <<< coding-agent-playbook <<<`; everything outside the block is left
  byte-for-byte alone). If git still tracks generated files — e.g. a repo
  migrating from committed output — `sync` warns and prints the exact
  `git rm -r --cached -- …` to run (it never touches git state itself).
  `playbook sync --check-staged` fails when a commit stages generated output.
- **`commit = true`** (legacy) — output is committed, `sync` removes the managed
  block, and `playbook sync --check` fails a commit on drift.

### 4. Define which resources apply

Three layers compose, later overriding earlier **by artifact `id`** (SPEC §11):

1. **Engine generic content** — ships with `coding-agent-playbook` (kept in
   the engine repository's `catalog/core/`).
2. **Overlay packages** — installed org packages, enabled (and ordered) in config.
   They're auto-discovered through Python entry points; you just list them:

   ```toml
   # .coding-agent-playbook.toml
   schema_version = 1
   # top-level keys: TOML puts anything after a [table] header inside that table
   overlays_enabled = ["playbook_rules_bnp"]     # ordered; later wins on id collision
   adapters_enabled = ["claude_code", "opencode", "shared_skills"]   # the init default
   # AGENTS.md is always emitted
   # add "continue" to opt in; drop "shared_skills" to skip .agents/skills/
   # add "agent_harness" to also emit an Agent Harness tree (opt-in)

   [project]
   name = "risk-models"
   kind = "python-application"          # python-library | ml-research | notebook
   description = "Counterparty risk scoring service"

   [engine]
   version = "0.1.0a0"                  # engine version the config was written for (required)

   [output]
   commit = false     # default: generated output is gitignored (local-only)
   ```

   (`playbook init` writes this file for you, plus `[storage]` and
   `[detector_cache]` tables; keep its `[engine]` table. Re-running
   `playbook init`, or `playbook check --refresh` after adding a dependency,
   rewrites it from the committed file alone: init's answers and the fresh
   `[detector_cache]` replace their keys, every other value is kept (tables
   the engine does not manage, such as `[hooks]`, `[links]` and `[metrics]`,
   included), but comments and layout are not.)

   The enabled lists are top-level keys only, so they go **above the first
   `[table]` header**. Every command that loads the config (`sync`, `check`,
   `validate`, `render`, `eval`, `init`) stops with an `error:` (exit 2),
   naming the file and the exact line to write instead, before anything is
   written, when it finds: an `[overlays]` / `[adapters]` table (or
   `overlays.enabled = …`); an `overlays_enabled` / `adapters_enabled` key
   written after a `[table]` header, which TOML nests in that table (say,
   appended to the end of the file); a misspelled key such as
   `overlay_enabled`; or a value that is not a list of non-empty strings. A
   personal `.coding-agent-playbook.local.toml` can set `adapters_enabled` too,
   above its `[user_choices]` header; its list replaces the committed one for
   your checkout only — no command writes the local file into the committed
   config.

3. **Repo-local `playbook/`** — drop in per-repo rules, prompts, skills, or eval
   samples; anything here wins on `id` collision:

   ```text
   playbook/
   ├── rules/         # add a new rule, or override one by reusing its id
   │                  # (a scoped rule names its skill with `skill:`)
   ├── prompts/
   ├── skills/        # <id>/SKILL.md (+ scripts/, references/)
   └── eval_samples/
   ```

Not every resource renders everywhere: the detector inspects the repo and each
artifact's `applies_if` predicate gates it (a FastAPI rule won't ship to a
non-FastAPI repo; the ML serialization-security rule ships only to repos with an
ML stack; the uv workflow reference ships only to repos the detector sees as uv
projects, that is with a `uv.lock`). A skill that owns rules follows them: it is
written only when at least one of its rules applies. Run `playbook check` to see
the detected facts and exactly which rules/prompts are active — the fastest way
to debug *"why isn't my rule appearing?"*
