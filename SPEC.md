# SPEC.md — coding-agent-playbook
| Field | Value |
| --- | --- |
| Version | 0.21 (draft) |
| Status | Proposed |
| Last updated | 2026-10-18 |
| Authors | Max Pereira, with Claude |
| Audience | Implementers, reviewers, future contributors |
| License | Apache-2.0 (engine); organization overlays may be private |

<!-- module-moves: keep -->
**Changelog**
- **0.21** — Skills-first context: scoped rules ship inside skills (draft; design `specs/prS-skills-context.md`, decision record `docs/adr/0001-scoped-rules-are-delivered-as-skill-references.md`). Only always rules stay in always-loaded context; every scoped rule is delivered as a reference inside the one skill that owns its topic. **A scoped rule names its owning skill** in `skill:` (required on a scoped rule, forbidden on an always rule; §6.1.1), and the engine renders it as `<skill root>/<skill>/references/<rule-id>.md`, listed in a generated `## References` index of that skill, whose description gains a `Covers …` clause of at most 300 characters (§6.1.6, §6.3.3). A skill takes member rules only when it declares the catalog-only `playbook:` block (`use_when`, `files`), and is written only while one of its members passes `applies_if` (§6.3.3, §6.4). **Core ships four skills**, `python-coding`, `python-testing`, `python-tooling` and `ml-data` (`catalog/core/skills/<id>/SKILL.md`), and every scoped rule in core names one of them; the `python-coding` members carry short topic-label names (§5.1, §6.3). **`AGENTS.md` and the Claude Code rules file hold only always rules**, then one generated `## Where guidance lives` map from file kinds to skills, byte-identical in the two (kept only when an enabled adapter writes a skills root); `playbook sync` warns when member rules are active but no enabled adapter delivers them (§6.1.4, §6.1.5, §10.3.1, §10.4). Continue still gets one rule file per rule, scoped ones included, ignores `skill:`, and never receives a skill with member rules as a prompt (§6.3.2, §10.2). **The always text is shorter** (D17): `project-context` keeps two reminders and `python-house-style` eight bullets; the rest moves into the new `python-coding` members `python-data-shapes` and `python-idioms` (§10.2.1). **`playbook validate` checks membership** (V1-V14, W1-W3): a scoped rule without `skill:` fails, so `playbook sync` writes nothing until every overlay and repo-local scoped rule names a skill (§12.6). **The shared-skills adapter writes the shared skill root `.agents/skills/`**, read by Codex and OpenCode, and settles the retired `shared_skills/` tree by the leftover policy (§10.1, §10.8, §4.2 step 9). **`playbook init` no longer enables `continue`** and no longer offers `codex` (§12.1, §12.2). `applies_if` gains a `package_manager` key, and validate checks each key on its own (§6.4). **`python-coding` gains three members distilled from the python-best-practices collection** (D7, D8), written in the catalog's own words and credited in `catalog/core/ATTRIBUTIONS.md` only: `python-performance-idioms`, `python-async` (`python_version: ">=3.11"`) and `python-classes-and-protocols`, which takes the composition and framework-base-class bullets over from `python-idioms`; six existing members take in upstream ideas, and no rule's `lint_codes` changes (§5.1, §6.1.6, §10.2.1). **`python-testing` gains two members from the same collection**, `pytest-test-doubles` (named fakes first, autospec only at thin third-party seams) and `pytest-fixtures`, which take over the `pytest` rule's fixture section and `monkeypatch` clause; `pytest` gains parametrize and one-thing-per-test detail with its `lint_codes` unchanged, and the `generate-tests` prompt recommends named fakes instead of `mocker` (§5.1). **`python-tooling` gains four members from the same collection**: the ungated `python-static-checks`, so the skill is now written in every Python repo, `pytest-configuration` (pytest only), `python-uv-workflow` (`package_manager: uv`) and `pydantic-boundaries` (`has_framework: ["pydantic"]`); its authored description, `use_when` and `files` become generic, and its "Where guidance lives" line reads `Tool configuration and framework wiring` (§5.1, §6.1.4). **Core ships a fifth skill, `playbook-guardrails`**, with no member rules: with hooks on, sync composes it from the on hooks' full guardrail text, one section per hook, and writes it to `.opencode/skills/` and `.agents/skills/` (to `.claude/skills/` only for a hook Claude Code cannot run natively), through the new `Adapter.writes_guardrails_skill` (§6.3.4, §10.1). **`ml-data` gains four members from the same collection** for array and data-frame code, `ml-vectorization`, `ml-data-transforms`, `ml-dtypes-and-typing` and `ml-reproducibility-and-testing`, gated `any_ml_stack: ["numpy", "pandas", "polars"]` with one section per library and globs `**/*.py` and `**/*.ipynb`; `skill-nudge` also matches `notebook_edit`, so it nudges on Claude Code notebook edits and `playbook check` labels it degraded on OpenCode, which has no notebook tool (§5.1, §6.1.4, §6.4, §12.2). **`AGENTS.md`'s Guardrails section is one line per hook** (D6): `- `<id>`: <text>` under a preface that names `playbook-guardrails`, where the text is the new optional `HOOK.md` key `summary` (one line of 1-120 characters, no Jinja; every core hook with a body declares one), else the body's first sentence cut at a word boundary; a hook Claude Code cannot run gets the same line in the Claude Code rules file instead of a full section (§6.6.2, §6.6.7, §9.7, §10.3.1, §10.4). **`CONTEXT.md` at the repository root is the project's only glossary** (§3 is a one-line pointer to it). The `### v0.21` entry of the Changelog appendix lists every changed section; later changes of this release (prompts and hooks that point at skills) append to it.
- **0.20** — Assistant lifecycle hooks (PR K; design `specs/prK-lifecycle-hooks.md` + `specs/prK-hook-pack.md`). **`Hook` is the fourth emitted canonical kind**: a `<id>/HOOK.md` (or `HOOK.md.j2`) directory, found at any depth under each layer's `hooks/` (the engine's bundled `catalog/core/hooks/`, a bundled plugin's `catalog/plugins/<name>/hooks/`, an overlay package's `resources/hooks/`) and `playbook/hooks/`, whose static frontmatter binds canonical events to a builtin or external handler and declares its decisions (only `deny | ask | context | none`), timeout, `on_error` and supported adapters (§6.6.7). Hooks are **opt-in per repo**: an absent `[hooks]` table, or one without `enabled = true`, adds no hook output on upgrade (no settings entries, launcher, shim or advisory text); `playbook init` asks (`--no-hooks` opts out). New committed policy tables `[hooks]`, `[hooks.<hook-id>]`, `[hooks.commit_convention]` and `[guardrails]`, plus new `[metrics]` keys, none of which `.coding-agent-playbook.local.toml` may carry (§7.1.1, §7.2). Overlays merge hooks additively — `extend` / `strictest` / `relax` / `replace` config keys, overlay-only `mandatory` hooks (§11.6). Sync resolves the effective set (`hook_policy.resolve_effective_hooks`), dispatches each hook through the new `Adapter.write_hook`, and writes the sync-level `.coding-agent-playbook/hooks/guard_config.json`; Claude Code gets managed entries in `.claude/settings.json` plus the committed launcher `.claude/hooks/playbook/launch.sh`, OpenCode gets the one generated plugin `.opencode/plugins/playbook-hooks.js`, and every other target gets the hook's advisory text. Every harness event runs one dispatcher, `playbook-hook` (§4.1, §4.2). New: the `has_dev_dependency` predicate (§6.4), prompt `write_scope` / `output_contract` and rule `lint_codes` frontmatter (§6.1, §6.2), the `hook_advisory` / `hook_claude_settings` formats (§9.7), `ArtifactSource.list_hooks` (§20.2) and manifest kind `"hook"` (§20.10). The adapter contract (§10.1), the Claude Code settings merge, launcher and pin (§10.3.2), the OpenCode shim (§10.6.2), the `playbook ci` aggregate twin, the `playbook-hook` runtime and the other off-workstation twins (§12.11–§12.19), the new pre-commit ids (§13), populated scoped lockfile entries (§14.4), the hook test strategy (§16.6), the air-gapped `playbook-secrets` scan in place of the unshipped gitleaks promise (§17.3) and the opt-in metrics `ruff_violations`, `file_sloc`, `docstring_example` and `diff_coverage` (§21) complete the release. Q8 resolved, Q1 partially answered (§19). `Config.extra_tables` now carries every entry `Config` does not own, `[hooks]` and `[guardrails]` included, so an `init` re-run and `check --refresh` write them back (§7.1, §7.2). The launcher and OpenCode shim templates are engine wiring, not content: they ship in the package as `templates/hook_shims/`, next to the pre-commit template (§5.1). The engine's content tree `content/` (v0.19) is renamed `catalog/` (§5.1): the wheel ships it as `coding_agent_playbook/_catalog/`, `bundled_content.py` becomes `catalog.py` (`catalog_root`, `catalog_layer_root`, `CatalogMissingError`; §20.3), the missing-tree error line reads `error: the engine's catalog was not found (…)` (§12), and the engine's own pytest marker and dev pre-commit hook are `catalog` and `catalog-checks`. Eval tasks stay a per-layer kind: a bundled plugin may ship `catalog/plugins/<name>/eval_tasks/` (§6.5.2). Claude Code's rules move out of `.claude/CLAUDE.md` (§10.3.1): the `claude_code` adapter writes every rule section, hook advisory and the heartbeat line to one unscoped rules file, `.claude/rules/coding-agent-playbook.md` (no `paths:` frontmatter, so Claude Code loads it at launch with the same priority as `.claude/CLAUDE.md`), and leaves `.claude/CLAUDE.md` a rule-free four-line stub, so OpenCode v1, which attaches `.claude/CLAUDE.md` when its read tool opens a file under `.claude/` (once per uncompacted session, §10.6), no longer loads the rules twice or sees the Claude-only heartbeat line (§10.6). The stub stays because a `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` in the working directory or above it stops Claude Code (default `claude-md-or-agents-md` mode) from also reading the root `AGENTS.md`, while a rules file does not; the next `playbook sync` rewrites it (MIGRATION.md).
- **0.19** — Bundled content leaves the Python package, and packs become **bundled plugins**. Every engine rule, prompt and eval task now lives in a top-level `content/core/` (now `catalog/core/`), and every bundled plugin in `content/plugins/<name>/`, in the same repository; the contributor guide is `content/README.md`. Hatch copies `content/` into the one wheel at build time (`force-include`, as `coding_agent_playbook/_content/`), so `pip install coding-agent-playbook` behaves as before, and `src/coding_agent_playbook/` holds logic only. The new leaf module `bundled_content.py` (now `catalog.py`) is the only code that knows where that content is: the wheel's `_content/` when it has a `core/`, else a source checkout's `content/`, else `BundledContentMissingError` (now `CatalogMissingError`). Every command that loads that content (`init`, `sync`, `check`, `validate`, `render`, `eval`) then exits 2 with `error: the engine's bundled content was not found (looked in <a>, <b>); reinstall coding-agent-playbook`, where it used to render zero engine artifacts silently. Bundled plugins are pure content: adding `content/plugins/<name>/` ships one, with no Python file. They are enabled as `coding_agent_playbook.plugins.<name>`. `coding_agent_playbook.packs.<name>` keeps working as a deprecated alias: the config canonicalizes it on load, and each such name prints one `warning: <file>: overlays_enabled: '<old>' is deprecated; use '<new>'` line (`init` prints `warning: --overlays: '<old>' is deprecated; use '<new>'`). The `coding_agent_playbook.packs` modules and `PACK_NAME` are removed with no shim. The sync preflight checks a bundled-plugin name against `content/plugins/<leaf>/` and never imports it: an unknown leaf is `no such bundled plugin`, a bare namespace is `the bundled plugin namespace, not a plugin`, and the hint reads ` (bundled plugins: …)`. Eval `--show` labels and the eval prompt lookup follow the layer instead of searching for a `resources` path segment, and the pre-commit template moves to `src/coding_agent_playbook/templates/precommit/`. Rendered output is unchanged under both spellings, and the third-party overlay contract (`<pkg>/resources/…`) is unchanged.
- **0.18** — No command writes local overrides into the committed config: an `init` re-run and `playbook check --refresh` now rewrite `.coding-agent-playbook.toml` from the committed file alone (new `FileSystemStateSource.read_committed_config_table`, shared through `commands/_committed_config.py`), not from the `.local.toml` merge `load_config` returns. Both used to save that merge, which wrote one engineer's `adapters_enabled` (reordered), `overlays_enabled`, `[user_choices]` and `[output]` into the team's file (an `init` re-run also swapped the committed hooks to match a personal `[output] commit`), and both deleted every key `Config` does not read — `[links]`, `[metrics]`, a future table, `[project] homepage`. Now an `init` re-run replaces, not merges, the keys `Config` owns (`config_entries.CONFIG_MANAGED_KEYS`; inside `[project]`/`[engine]`/`[storage]`/`[output]` only the keys it reads, `config_entries.CONFIG_MANAGED_TABLE_KEYS`) with the updated config and writes everything else back with the same parsed values; `check --refresh` replaces `[detector_cache]` alone and writes every other entry back as parsed, not through `Config` (whose round trip dropped explicit empty lists and filled defaults). `FileSystemStateSource.save_config_table` is the committed file's one writer and `commands/_committed_config.ConfigRewrite.save` its one caller, built only by that module's `plan_*` functions — an AST test pins it. Before writing, both commands check that the result still loads with the local file merged on top (`preview_config`; a first `init` too), and a committed file missing a required key only the local file supplies exits 2 with nothing written, where it used to be completed with that personal value. Each config file is checked whole on its own, naming it, in every command: a file `tomllib` cannot read (syntax, not UTF-8, nested too deeply), a `project`/`engine`/`storage`/`output`/`detector_cache`/`user_choices` that is not a table, and a malformed `[output]` are `ConfigError`s (exit 2) where they were tracebacks or were reported against the wrong file, and a committed non-table is refused even when a local table hides it. A missing required key (`schema_version`, `[project] name`/`kind`, `[engine] version`) is a `ConfigError` (exit 2) in every command, no longer a `KeyError` traceback. `init` checks `--overlays` even when a local `overlays_enabled` replaces it for its own sync, since that list is what gets committed. The TOML writer (`_toml.dump_toml`, moved from `sources/filesystem.py::_dump_toml`, + `_toml.format_scalar`) now writes anything `tomllib` parses — floats (a NaN's sign included), dates/times, tables, arrays of tables and inline values at any depth (both walks are iterative: no `RecursionError`), keys that need quoting — and fixes four latent writer bugs: a non-ASCII bare key and a raw U+007F made the file unparseable; an integer past Python's int-to-str limit (which `tomllib` reads from `0x`/`0o`/`0b` literals) raised `ValueError`, and is now written in hex; and keys and header parts were written unquoted, so a dotted `[detector_cache]` dependency name (`ruamel.yaml`) or a `[user_choices]` key such as `"docs.style"` was re-read as a nested table. Config/lockfile/manifest bytes change only where the old writer crashed or its output was refused or misread; the `agent_harness` manifest now also carries float and date frontmatter values, which used to stop `sync` with a `TypeError` (§7.1, §7.2, §12.1, §12.4, §12.5, §20.3, §20.10).
- **0.17** — Bundled opt-in packs: the engine wheel now ships **packs**, importable subpackages under `coding_agent_playbook.packs.*` layered exactly like overlay packages but needing no extra install, **off by default** and enabled by listing the pack's dotted name in the top-level `overlays_enabled` key. The first pack, `coding_agent_playbook.packs.superpowers`, is a near-verbatim, self-contained port of the Superpowers skills library (v7.0.0, MIT): 15 skills rendered like any canonical skill — natively and byte-identically to `.claude/skills/<id>/`, `.opencode/skills/<id>/` and the `shared_skills/<id>/` hub through the shared `SkillWriter` (`SKILL.md` with the sentinel as its first body line), degraded to Continue prompts, and to `skills/<id>/` under the opt-in `agent_harness` — with only the self-containment edits applied (supporting files moved under `references/`/`scripts/`, an `id` frontmatter key, plain skill names instead of `superpowers:<skill>`, no external URLs, upstream-plugin coupling removed). Dropped: the brainstorming visual companion, the SessionStart bootstrap hook, and diagnosing-superpowers' upstream issue filing. MIT notice in the pack's `LICENSE` + `ATTRIBUTIONS.md`, and as `references/LICENSE` in every skill so it travels with each synced copy. No rendering behaviour changes: opting out of the pack or overriding one of its skills is settled by the v0.16 lockfile leftover policy (§4.2 step 9). **Config hardening (same release):** the enabled lists are the top-level `overlays_enabled` / `adapters_enabled` keys only, above the first `[table]` header — an `[overlays]`/`[adapters]` table (incl. the dotted `overlays.enabled` key), an enabled key nested in any table (what applying the fix-it hint in place, or appending the key to the end of the file, produces), a close misspelling such as `overlay_enabled`, or a value that is not a list of non-empty strings is a new `config.ConfigError` naming the file (`.toml` and `.local.toml` are checked separately, before the merge) and showing the line to write and where, and every command that loads the config (`sync`, `check`, `validate`, `render`, `eval`, `init`) prints `error: …` and exits 2 before writing anything (each of these shapes used to read as an empty list, so `sync` rendered only `AGENTS.md` and deleted the rest as leftovers); `[output]` value errors are `ConfigError`s too (they were a traceback). An unusable overlay — its import fails (missing, or raising at import time, which used to be a traceback and is now reported with its error), or it imports with no `resources/` directory — is caught by the one shared preflight check in every command, one line per overlay: `sync` refuses (exit 1), `validate` fails (exit 1), `check` flags it and no longer reports a clean state (exit 0), `init` refuses before writing (exit 2; it checks the overlays its sync will use — `--overlays`, or the local file's list that replaces it); a pack-like typo lists the bundled packs (discovered with `pkgutil`). Every config example uses the top-level keys, and §7.1 shows the `detector_cache` table the code reads and writes (§4.2, §7.1, §7.2, §10.7, §10.8, §11.1, §11.5, §12.1–§12.6). `[tool.ruff] extend-exclude` keeps the vendored text byte-faithful; `tests/packs/` gates it (§5.1, §6.3, §11.5).
- **0.16** — Generated output is **local-only by default**: everything `playbook sync` renders into a consumer repo (`AGENTS.md`, `.claude/`, `.continue/`, `.opencode/`, skill directories, the lockfile) is gitignored and never committed. New `[output] commit = <bool>` toggle in `.coding-agent-playbook.toml` (default `false`; `playbook init` writes it explicitly; `true` restores the legacy committed-output policy). With `commit = false`, write-mode `sync` keeps an engine-owned **managed block** in the consumer's `.gitignore` current (root-anchored, escaped entries — one per generated file, skill directories collapsed to `/<dir>/`; byte-preserving, atomic, idempotent; malformed markers fail loudly) and warns on stderr about generated paths git still tracks, printing the exact `git rm -r --cached -- …` to run (it never changes git state). Leftovers of an earlier sync stay owned through the previous lockfile: deleted only when pristine, untracked and every enabled adapter is installed, else kept (and, for `commit = false`, kept ignored). This **lockfile leftover policy is the one deletion policy for stale native-skill output**, under both `commit` settings: adapters' `cleanup_stale` never deletes inside a skill directory, and a file the engine never wrote — even one dropped into an engine-owned skill dir — is never deleted (it replaces the v0.15 `SkillWriter` cleanup, which deleted every unwritten file in an engine-owned dir). It deletes only inside the `output_locations` installed adapters declare (§10.1) — never under `.git/`, never through a symlink the user put on the path — prunes emptied directories no higher than the skills root (never a symlinked root's target), and fails closed when git cannot say whether a leftover is tracked (asked case-insensitively, matched in NFC or by file identity); a file/folder swap inside a skill dir displaces only what the same policy would delete, and the pre-v0.15 lockfile claim needs unchanged `SKILL.md` bytes. Stale-vs-written comparisons use file identity (the `agent_harness` cleanup too), so a case-only skill-id rename on a case-insensitive filesystem never deletes fresh output; `sync --check`/`--check-staged` render into an empty scratch dir but decide skill-dir ownership against the real tree, so they skip exactly the skill dirs write mode skips. A missing overlay package makes every `sync` mode refuse to run. `sync --check` reports a stale/missing block as drift; the new **`sync --check-staged`** fails a commit that stages generated output. New hooks: `playbook-sync` (`post-checkout`/`post-merge` auto-sync) and `playbook-no-generated-output` (pre-commit guard); `playbook-sync-check` is kept as the legacy hook for `commit = true`. New stdlib modules `gitignore.py` + `git_client.py` (an injectable read-only `GitClient`) and `commands/_sync_output.py` (§4.2, §5.3, §6.3, §7.1, §10.8, §12.1–§12.3, §13, §14.4).
- **0.15** — Native skills for every Agent-Skills harness + the `shared_skills/` hub: a new shared `SkillWriter` (`adapters/skill_dirs/writer.py`) is the single source of truth for a native skill directory (`<root>/<id>/SKILL.md` + byte-copied `scripts/`/`references/`), byte-identical across roots. `claude_code` writes `.claude/skills/`, `opencode` now writes **`.opencode/skills/`** natively (no longer relying on `claude_code`), and the new **`shared_skills`** adapter (on by default, not force-enabled) writes the cross-agent hub `shared_skills/`. Two bug fixes: `SKILL.md` frontmatter `name` is now the skill id (= directory name, the Agent Skills rule OpenCode enforces), and `SKILL.md` carries the sentinel as its first body line, so a skill directory is recognisably engine-owned (user-authored skill dirs are never touched; since v0.16 a deleted skill's unchanged, untracked files are removed by the lockfile leftover policy, §4.2 step 9, and edited or user-added files are kept). New `playbook validate` rule for the Agent Skills `id`/`name`/`description` constraints (id-less skills included). Ownership is decided before writing: a colliding hand-written skill dir is skipped with a warning, never overwritten (§6.3, §10.3, §10.6, §10.8, §12.6).
- **0.14** — Self-contained markdown links (PR L): every markdown link in every canonical artifact (rules, prompts, skills incl. `references/`) must be **self-contained** — relative targets resolve to a file inside the artifact's source layer (the package `resources/` or repo-local `playbook/`; `..`-escapes, absolute paths, and non-`http(s)` schemes are violations), and `http(s)` links pass only through the new `[links] allowed_domains` allowlist (default empty = fully strict). Deterministic (stdlib-only, no network), extraction masks frontmatter/code fences/inline code. New `links.py` + `config.parse_links_config` + a `playbook validate` rule (§12.6, §7.1); the engine's own artifacts are gated on CI by a pytest integration test. Design: `specs/prL-markdown-links.md`.
- **0.13** — Eval task-config redesign ("2b refined", Tracks C1–C8): the `[expected]`/`[metrics]`/`[rubric]` triple is replaced by a **layered** task config. Three layers share one `[<layer>.bind]` + `[<layer>].expr` shape — **`[gate]`** (deterministic boolean), **`[rubric]`** (llm-judge weighted), and an optional cross-trial **`[aggregate]`** — composed by a tiny boolean-expression DSL; `[verdict].trial` is a boolean expression over the layers, and the **verdict is *derived*** from the layer results (not re-run). There is **no `[expected]` block** — file predicates are gate `check`s (`file_exists`/`file_contains`/`file_unchanged`/`file_forbidden`). Thresholds are now **0–1 normalized**: every `Metric` owns a `Normalizer` (`evaluators/normalizer.py`: `RampNormalizer`/`PercentNormalizer`/`Identity`) mapping raw→0–1 goodness (higher = better), and `higher_is_worse` is **deleted** — `warn`/`fail`/`max_worsening` are 0–1 cutoffs. A check is `(type) × (metric|judge) × kwargs`: `check = "threshold"|"non_regression"` over a registered `metric=` **or** a `judge=` criterion (a `JudgeMetric` — an llm-judge criterion **is a metric**). New registries: checks via `@register_check` + `coding_agent_playbook.checks`, gates via `@register_gate` + the new **`coding_agent_playbook.gates`**; `{ref="name"}` resolves a registered composed **gate** or **rubric**. The `[aggregate]` layer is the same bind+expr shape over `pass_at_k`/`pass_pow_k` (`k` kwarg, `over ∈ {gate,rubric,verdict}`); the runner runs `N=max(k)` trials. Deleted from the prior model: the `[expected]`/`[metrics]`-triple authoring, `higher_is_worse`, `rubric_for_task`, `ExpectedOutcome`. Authoritative design: `specs/pr2b-task-config.md`; migration: `MIGRATION.md` (§6.5, §15.2/§15.3/§15.3.1, §21).
- **0.12** — Evaluator subsystem refactor (PR R6 — clean-slate): the fused `Evaluator` ABC + free `grade()` are replaced by three single-responsibility abstractions — **`Metric`** (`measure(ctx) -> list[Measurement]`), **`Check`** (`grade(ctx, measurements) -> CheckResult`, a boolean gate + optional partial-credit score), and **`Rubric`** (a weighted set of checks; `evaluate(ctx, measurements) -> EvaluationReport`). `Rubric` **is also a `Metric`** (it surfaces its composite via `measure()`), so a rubric thresholds into a check and nests into a Composite tree. A cost-tiered (`CostTier` DETERMINISTIC < EXECUTION < JUDGED) `scheduler` runs checks cheapest-tier-first with short-circuit, so a failing deterministic check **never invokes the LLM judge** (`playbook eval --run --full-scoring` forces every check). Entry-point groups are renamed/split: out-of-tree metrics register under **`coding_agent_playbook.metrics`** (was `…​.evaluators`), custom graders under the new **`coding_agent_playbook.checks`**. `grade()` is replaced by `Rubric.evaluate`; the `extra_evaluators` side-channel, `value_kind`/`to_score`, the weight-0/fail-floor `[expected]` hack, and `evaluators_for_task` are deleted. The authored `[expected]`/`[metrics]`/`[rubric]` task TOML is **unchanged** (zero authoring migration). Authoritative design: `specs/prR6-check-rubric.md`; migration guide: `MIGRATION.md` (§15.3/§15.3.1, §21).
- **0.11** — Judged scoring + `[expected]` unification + a second real runner (PR R2/R3): the judge is **live**. `Judge.score_criterion(criterion, artifact, n)` is the canonical per-criterion primitive (Option A; batch `score()` wraps it), with the opt-in `LLMJudge` (`name="llm"`, shells out to the `claude` CLI, `available()`-gated, never in CI) via the `coding_agent_playbook.judges` group. There is **no `ProgrammaticOnlyJudge`** — deterministic-only is simply no judge configured (`ctx.judge is None`). `[expected]` file checks are now **unified** into `evaluators_for_task` as real BOOL deterministic `Evaluator`s (`evaluators/expected.py`); the R1 interim inline compile is removed, so `[expected]` + `[metrics]` + (with a judge) `[rubric]` all flow through one `grade(…, extra_evaluators=…)` call. New opt-in **`OpenCodeRunner`** (`name="opencode"`, `available()`-gated, never in CI) joins `FakeRunner`/`ClaudeCodeRunner`. CLI: `playbook eval <id> --run [--judge llm] [--samples N]` (default no judge ⇒ deterministic-only). The §21.2.3 `Judge.score` signature debt is closed (§15.3/§15.3.1, §12.8, §21.2.3).
- **0.10** — Eval runner activation (PR R1): `HarnessRunner` becomes a concrete **template method** (materialize → render_prompt → `_invoke_agent` → capture → score) so an eval task runs end-to-end and is scored through the unified PR-M `Evaluator`/`grade()` model — the deterministic layers (`[expected]` file checks + `[metrics]` static/execution non-regression vs the `setup/` baseline) are **live**. Concrete runners: hermetic `FakeRunner` (default test driver) + opt-in `ClaudeCodeRunner` (`available()`-gated, never in CI), via the `coding_agent_playbook.runners` entry-point group. Result model evolved to **Option B** (`TaskResult.report: EvaluationReport`; `programmatic_checks`/`rubric_scores`/`CheckResult` retired). New `playbook eval <id> --run [--runner …] [--format …]` (no `--run-tests` — intent is in the task's `[metrics]`). Judged `[rubric]` scoring stays deferred to R2 (§15).
- **0.9** — Code-quality evaluator subsystem (PR M): one `Evaluator` abstraction with three families — static metrics (CC/WMC/LCOM4/DIT/CBO≈ via `ast`, MI via the optional `radon` extra), execution metrics (`test_pass_rate`/`coverage`, shelling out to the target's `pytest`), and judged criteria (the rubric, generalized; dormant until v1.1) — plus the standalone `playbook metrics` gate + a `repo: local` static pre-commit hook, and dormant eval `[metrics]` wiring (§21).
- **0.8** — Agent Harness round-trip support (PR H): the opt-in `agent_harness` output adapter (§10.7), the `playbook import-harness` / `playbook validate-harness` subcommands (§12.9, §12.10), and the `.playbook/manifest.toml` round-trip sidecar (§20.10).
- **0.7** — Storage source abstraction (§20), ML serialization-security guideline, air-gapped pre-commit.
<!-- module-moves: end-keep -->
---
## 1. Context
AI coding assistants — Continue, Claude Code, Codex CLI, Cursor — have each converged on their own way of loading context: rules, prompts, skills, hooks, and harness-specific config files. Teams that want a single source of truth for their conventions are forced to either (a) pick one assistant and accept lock-in, (b) maintain N copies of the same rules in N different formats, or (c) settle for `AGENTS.md` as a lowest common denominator and lose the richer features each assistant offers.
`coding-agent-playbook` provides a single canonical source for organizational coding context and renders it into whatever shape each assistant expects. It is opinionated, Python-first, and designed to be reusable across teams and organizations. The core engine is open-source and organization-agnostic. Organization-specific content (rules, prompts) ships as separate overlay packages that depend on the engine.
Prior art that shaped this design:
- **LinkedIn's CAPT** (Contextual Agent Playbooks and Tools) — established the playbook pattern at enterprise scale, validated the "playbook as executable institutional knowledge" concept.
- **The `rules` CLI from rules.so** — render-from-canonical model, the operational pattern this spec extends.
- **continuedev/awesome-rules** — community catalogue of rule shapes; informs the rule taxonomy.
- **The convergence on `AGENTS.md`** (Codex, GitHub Copilot, Cursor, and now Continue) as the universal baseline.
- **The ACE paper (Agentic Context Engineering)** — argues for contexts as evolving playbooks; influences the versioning and incremental-update semantics here.
## 2. Goals and non-goals
### 2.1 v1 goals
**G1 — One canonical source, multi-harness output.** A team writes a rule once. The tool renders it to `.continue/rules/`, Claude Code's `.claude/rules/coding-agent-playbook.md`, `.opencode/command/`, and `AGENTS.md` automatically, using each harness's native features (frontmatter, globs, sections): always rules go to always-loaded files; a scoped rule becomes a reference inside the skill it names, and Continue still gets one rule file per rule. v1 primary adapters: Continue, Claude Code, OpenCode. Universal fallback: AGENTS.md.
**G2 — Detect-and-condition.** Rules and prompts are gated by what's actually in the repo: Python version, installed frameworks, presence of notebooks, etc. A FastAPI rule does not ship to a non-FastAPI repo.
**G3 — Three-layer overlay model.** Engine package ships generic content. Organization-specific packages (e.g. `playbook-rules-bnp`) ship overlay content. Consumer repos can override locally.
**G4 — Pre-commit-native distribution.** Installation produces pre-commit-managed sync hooks. By default (`[output] commit = false`, §7.1) generated output is **local-only**: it is gitignored, re-rendered automatically after every checkout and merge, and a commit that stages any of it fails. Repos that opt into committed output (`commit = true`) keep the legacy guarantee instead: drift between the canonical source and what is checked into the repo fails the commit and CI.
**G5 — Air-gapped friendly.** No required network calls at sync time. Internal PyPI distribution. No HTTP-based hooks shipped by default. No telemetry.
**G6 — Eval task authoring (Tier 0).** v1 ships the schema, loader, validator, and read-only CLI for prompt-associated eval tasks (Section 6.5). The runner, programmatic checks, and LLM-as-judge are deferred to v1.1 (Tier 1) and v2 (Tier 2) respectively. Authors write tasks alongside prompts from day one; the corpus accumulates as documentation and is ready when the runner lands.
### 2.2 v1 non-goals (named so people stop asking)
- Skills are first-class only for harnesses that implement the Agent Skills layout (`<root>/<name>/SKILL.md`): Claude Code (`.claude/skills/`) and OpenCode (`.opencode/skills/`), plus the shared skill root `.agents/skills/` (§10.8) — and, in its own tree, the opt-in `agent_harness` adapter (`skills/<id>/SKILL.md`, §10.7). Adapters that keep the ABC default (Continue) degrade skills to prompts; the rules-only `agents_md` adapter does not emit skills at all.
- No MCP server configuration management. (v2.)
- No Cursor dedicated adapter beyond the universal AGENTS.md fallback. (v2.)
- No Codex CLI dedicated adapter — Codex reads AGENTS.md natively, so the universal adapter is sufficient, and its skills from `.agents/skills/` (§10.8).
- No OpenCode agents (custom modes in `.opencode/agent/`) — users author these by hand. (v2; see open question 9.)
- No management of user-authored OpenCode plugins. The engine generates exactly one plugin, the lifecycle-hook shim `.opencode/plugins/playbook-hooks.js` (§10.6), and only when the repo opts into hooks (§7.1.1); every other file under `.opencode/plugin/` or `.opencode/plugins/` is the user's, authored by hand and never touched. (Open question 8, resolved.)
- No `opencode.json` management — MCP servers, permissions, model selection are owned by the user.
- No eval runner — `playbook eval` prints a deferred-implementation message; task authoring + validation is v1, execution is v1.1 / v2.
- No LLM-as-judge — rubric scoring is human-only until v2.
- No web UI for browsing or authoring rules.
- No telemetry of any kind.
- No automatic generation of rules from PR review comments.
### 2.3 v2+ aspirations
- MCP server registry and per-harness MCP config generation (including OpenCode's `opencode.json` mcp block)
- Cursor dedicated adapter with `.cursor/rules/*.mdc` output
- OpenCode agent definitions as a further canonical artifact category
- Eval runner (Tier 1) — programmatic checks against agent output, per-harness comparison
- LLM-as-judge for rubrics (Tier 2) with calibration tooling
- Per-team overlay packages discoverable via internal registry
- Rule provenance and changelogs

Delivered: OpenCode plugin generation from canonical hook descriptions — listed here through v0.19 — shipped in v0.20 as the generated lifecycle-hook shim, driven by the canonical `Hook` artifact (§6.6.7, §10.6.2).
## 3. Glossary
`CONTEXT.md` at the repository root is the project's only glossary; every term this spec uses (rule, always rule, scoped rule, member rule, skill, reference, prompt, hook, guardrail, layer, bundled plugin, harness, adapter and the rest) means what `CONTEXT.md` says.
## 4. Architecture overview
### 4.1 Component diagram
```
                                    ┌──────────────────────────────────┐
                                    │      coding-agent-playbook       │
                                    │            (engine)              │
                                    │                                  │
                                    │  ┌────────────────────────────┐  │
                                    │  │  catalog/     (canonical)  │  │
                                    │  │   ├── core/                │  │
                                    │  │   │   ├── rules/*.md|.j2   │  │
                                    │  │   │   ├── prompts/*.md|.j2 │  │
                                    │  │   │   ├── skills/<id>/     │  │
                                    │  │   │   └── hooks/**/HOOK.md │  │
                                    │  │   └── plugins/<name>/      │  │
                                    │  │       └── skills/<id>/     │  │
                                    │  └─────────────┬──────────────┘  │
                                    │                │                 │
                                    │                ▼                 │
                                    │  ┌────────────────────────────┐  │
                                    │  │  overlay merge + applies_if│  │
                                    │  │  hooks: hook_policy.       │  │
                                    │  │    resolve_effective_hooks │  │
                                    │  └─────────────┬──────────────┘  │
                                    │                │                 │
                                    │                ▼                 │
                                    │  ┌────────────────────────────┐  │
                                    │  │  renderer (Jinja2)         │  │
                                    │  └─────────────┬──────────────┘  │
                                    │                │                 │
                                    │                ▼                 │
                                    │  ┌────────────────────────────┐  │
                                    │  │  adapters (one per harness)│  │
                                    │  │   ├── continue             │  │
                                    │  │   ├── claude_code          │  │
                                    │  │   ├── opencode             │  │
                                    │  │   ├── shared_skills        │  │
                                    │  │   └── agents_md            │  │
                                    │  │  write_rule / write_prompt │  │
                                    │  │  / write_skill / write_hook│  │
                                    │  │  then finalize             │  │
                                    │  └────────────────────────────┘  │
                                    │  ┌────────────────────────────┐  │
                                    │  │  guard_config.py: the sync-│  │
                                    │  │  level guard_config.json   │  │
                                    │  │  (hooks on only)           │  │
                                    │  └────────────────────────────┘  │
                                    │  ┌────────────────────────────┐  │
                                    │  │  hook_runtime: the one     │  │
                                    │  │  dispatcher, playbook-hook │  │
                                    │  │  dispatch|simulate|doctor  │  │
                                    │  └────────────────────────────┘  │
                                    └──────────────────────────────────┘
                                                    │
                              ┌─────────────────────┴─────────────────────┐
                              │                                           │
                              ▼                                           ▼
              ┌──────────────────────────────┐         ┌──────────────────────────────┐
              │  playbook-rules-bnp          │         │      consumer repo           │
              │     (overlay)                │         │                              │
              │                              │         │  .coding-agent-playbook.toml │
              │  Adds:                       │         │                              │
              │   - banking-security rules   │         │  Generated (gitignored):     │
              │   - PII redaction prompts    │         │   .continue/rules/*.md       │
              │   - LiteLLM-aware config     │         │   .continue/prompts/*.md     │
              │   - overlay hooks (data-only │         │   .claude/CLAUDE.md (stub)   │
              │     unless allow_code_from)  │         │   .claude/rules/             │
              │                              │         │     coding-agent-playbook.md │
              │                              │         │   .claude/commands/*.md      │
              │                              │         │   .claude/skills/*/          │
              │                              │         │       references/*.md        │
              └──────────────┬───────────────┘         │   .opencode/command/*.md     │
                             │                         │   .opencode/skills/*/        │
                             │                         │   .agents/skills/*/          │
                             │                         │   AGENTS.md                  │
                             │                         │  ... and with hooks on:      │
                             │                         │   .claude/hooks/playbook/    │
                             │                         │       launch.sh              │
                             │                         │   .opencode/plugins/         │
                             │                         │       playbook-hooks.js      │
                             │                         │   .coding-agent-playbook/    │
                             │                         │       hooks/guard_config.json│
                             │                         │                              │
                             │                         │  Managed entries (user file):│
                             │                         │   .claude/settings.json      │
                             │                         │       `hooks` (hooks on)     │
                             │                         │                              │
                             │                         │  Merged by init (committed): │
                             └─────── merges ─────────►│   .pre-commit-config.yaml    │
                                                       │                              │
                                                       │  Personal overrides:         │
                                                       │   .coding-agent-playbook.    │
                                                       │       local.toml (gitignored)│
                                                       └──────────────────────────────┘
```
**Runtime path, only with `[hooks] enabled = true`.** One dispatcher serves every harness event; nothing in it imports the `cli` package, Jinja or YAML, and it reads only the compiled `guard_config.json`, never the canonical sources (`specs/prK-lifecycle-hooks.md` §D):
```
  Claude Code ── .claude/settings.json `hooks` ──► sh .claude/hooks/playbook/launch.sh ──┐
                                                                                         │
  OpenCode ───── .opencode/plugins/playbook-hooks.js (spawn) ────────────────────────────┤
                                                                                         ▼
                    <pin> -I -m coding_agent_playbook.hook_runtime dispatch <event> --harness H
                    (<pin> = <git_dir>/playbook-hooks/interpreter, written by write-mode sync)
                         │  reads .coding-agent-playbook/hooks/guard_config.json
                         │  fans out in-process to the enabled hooks, one Stop coordinator
                         ▼
                    exit 0 (decision on stdout) | exit 10 (deny); the launcher maps 10 to 2
```
### 4.2 Data flow
The end-to-end flow of `playbook sync` in a consumer repo:
1. **Load configuration.** Read `.coding-agent-playbook.toml` (committed), merge `.coding-agent-playbook.local.toml` (gitignored, personal overrides) on top. The read goes through the configured `StateSource` (filesystem in v1; see Section 20); a config the engine would misread — an `[overlays]`/`[adapters]` table, an enabled key nested in a table or misspelled, a `*_enabled` value that is not a list of non-empty strings, a non-boolean `[output] commit` — is a `ConfigError` and `sync` exits 2 before anything else runs (§7.1). A deprecated `coding_agent_playbook.packs.<leaf>` entry is rewritten to `coding_agent_playbook.plugins.<leaf>` as the config loads, and `SyncContext.from_repo` prints one `warning:` line per such name (§11.5). **Preflight:** every package in `overlays_enabled` must import without error in the running environment and ship a `resources/` directory, else `sync` (every mode) exits 1 naming it with the reason and writes nothing — rendering without an overlay would silently drop its rules and un-ignore its output (the classic case is a pre-commit hook venv, §13.1). A bundled-plugin name is checked against `catalog/plugins/<leaf>/` and never imported (the engine package resolves to `catalog/core/`, and a bare plugin namespace is refused, §11.5). The check is `validation.preflight.unusable_overlays`, shared with `validate` (§12.6), `check` (§12.4) and `init --overlays` (§12.1). An enabled adapter with no installed entry point is only warned about (its earlier output is kept, step 9).
   The hook policy tables `[hooks]` and `[guardrails]` are read from the committed file only (`StateSource.load_policy_tables`, §7.2). Write mode and `--check` then run the full `playbook validate` rule set, the hook trust contract H1–H21 included, and exit 1 on any finding before writing anything (§12.6).
2. **Run detector.** Inspect `pyproject.toml`, lockfiles, filesystem. Produce a facts dictionary.
3. **Resolve overlays.** Query the configured `ArtifactSource` (filesystem in v1; see Section 20) for rules, prompts, skills, hooks, and eval tasks across the engine's catalog, each declared overlay package or bundled plugin, and the consumer's `playbook/` directory. Build a unified artifact list, with later layers overriding earlier ones by ID — except hooks, whose layers merge additively (`OverlayResolver.resolve_hooks` + `hook_policy.merge_hook_layers`, §11.6).
4. **Filter.** For each artifact, evaluate its `applies_if` predicate against the facts dictionary. Drop non-matching artifacts. Hooks are gated in one place only, `hook_policy.resolve_effective_hooks`: the `[hooks]` on-formula (`enabled`, `tiers`, `enable`, `disable`, `mandatory`), `applies_if` ANDed with a `linked_rule`'s, the `[guardrails]` domain merge, and `supports ∩ [hooks] adapters`. It returns the on hooks as `ResolvedHook`s and the off ones as `SkippedHook`s (reported by `playbook check`); with `[hooks]` off both lists are empty.
5. **Render.** Apply Jinja2 to each surviving artifact's template with `facts | config` as context. Then compose skills (`skills.membership.compose_skills`): a skill with a `playbook:` block gets its surviving member rules, rendered, and is dropped when none survived step 4; every other skill passes through (§6.3.3). The adapters receive the composed skills. A `HOOK.md.j2` body renders the same way (no template has a `rule()` helper since v0.21); hook frontmatter, handler commands and scripts never pass through Jinja.
6. **Dispatch to adapters.** For each enabled adapter (`continue`, `claude_code`, `opencode`, `shared_skills`, `agents_md`), call `begin_sync(repo_root, prior_lock)` (the real repo and the previous lockfile, even under `--check`), pass the rendered artifacts, then every `ResolvedHook` through `write_hook`, then `finalize`; the adapter writes to its harness-specific locations. Claude Code merges its managed entries into `.claude/settings.json` and writes the launcher `.claude/hooks/playbook/launch.sh`, OpenCode writes the one shim `.opencode/plugins/playbook-hooks.js`, and every other adapter degrades a hook to its advisory text (§10). `managed_lock_entries()` then reports the sub-file elements the adapter owns. Before the first adapter writes, sync checks on the real repo every runtime output an adapter is about to write whole (`planned_runtime_outputs`, §10.1): a same-named file without the line-1 sentinel, a hard link (even a sentinel-tagged one: writing it whole would truncate the other name too), or a symlink at that path or at a directory between it and the repo root, stops every mode with exit 1 naming the file, and nothing is written.
7. **`AGENTS.md` is always among the outputs.** The `agents_md` adapter is force-enabled, so step 6 writes `AGENTS.md` (in its `finalize()`) whichever other adapters are enabled, as long as at least one always rule survived step 4, a skill contributes a Where line or a hook advisory exists (§10.4). With hooks on it gains a Guardrails section holding the on hooks' advisory text. **Sync-level hook output:** whenever `[hooks] enabled` and a hook-capable adapter is on, sync itself (not an adapter) writes `.coding-agent-playbook/hooks/guard_config.json` — the machine-independent record the dispatcher reads (`guard_config.render_guard_config`) — and byte-copies external handlers' scripts beside it.
8. **Stamp.** Write a `.coding-agent-playbook.lock` file containing the rendered file hashes via the configured `StateSource`; used by `playbook sync --check` to detect drift. Paths are recorded resolved through the repo's own symlinks, and a written file that resolves outside the repo (an output dir linked to a folder elsewhere, `.claude/skills -> /shared/skills`) gets no entry: the lockfile never owns output there (step 9 releases such an entry, so the leftover policy never deletes it; the adapters' sentinel-based `cleanup_stale` still removes a stale tagged file through the link), so the lockfile never holds an absolute, machine-specific path. The lockfile is schema 2: every entry records its provenance (`kind`, `artifact_id`, `source`, `adapter`), and each managed element of a co-owned file (`.claude/settings.json`) is a scoped entry hashed on its canonical JSON (§14.4).
9. **Settle leftovers, then apply the output policy** (`[output] commit`, §7.1). Under **both** `commit` settings, first settle **orphans** — paths the *previous* lockfile lists that this run did not rewrite but that are still on disk (a removed skill's `SKILL.md` + scripts, a script dropped from a skill that still exists, everything a since-disabled adapter wrote). "Did not rewrite" compares file identity (`st_dev`/`st_ino`), not path spelling: after a case-only skill-id rename on a case-insensitive filesystem the old entry names the very file just written, so it is no orphan (and two entries naming one file yield one orphan, so no duplicate block entries). This is the **only** deletion policy for stale native-skill output — adapters' `cleanup_stale` never deletes inside a skill directory (`agent_harness`'s `skills/<id>/` included), and a file/folder swap inside a skill dir displaces only files this same policy would delete (§10.8) — and a path the previous lockfile does not list is a user file, never an orphan, even inside an engine-owned skill directory (with no readable previous lockfile nothing there is deleted). An entry is **released** — never deleted, no longer owned — when it leaves the repo, names a user/state file, has a `.git` segment, or reaches its file through a symlink (lockfile paths are recorded resolved, so a symlink on the way means the user re-pointed the path since — e.g. moved a skill dir into their own tree and linked it back — and git cannot see through it either), and, unless an adapter is missing, when it lies outside every installed adapter's declared `output_locations` and `retired_output_locations` (§10.1), so a hand-edited or merged lockfile can never aim `sync` at `.git/HEAD` or a source file. An orphan inside a declared location whose bytes still hash to its old lockfile entry and that git does not track is deleted, and the directories it leaves empty are pruned bottom-up: never above the declared directory that holds it, the declared directory itself (an emptied skills root such as `.claude/skills/`) only when it is a real directory as spelled — so the target of a symlinked root (`.claude/skills -> ../.agents/skills`) is never removed, even when the target is itself a declared location (`.claude/skills -> ../.agents/skills` with `shared_skills` on, or `.agents/skills -> ../.claude/skills`), whatever order the adapters declare them in — never the repo root, never a directory with anything left in it. Directories emptied by `cleanup_stale`, or by a kept leftover the user later deleted, are pruned within the same bounds. If an enabled adapter is missing from the environment, all orphans are kept. "Git does not track it" is asked with case-insensitive literal pathspecs (`:(literal,icase)`; plain pathspecs are case-sensitive even under `core.ignorecase`) and a match is confirmed by NFC spelling (git on macOS reports precomposed names) or file identity (the index's `Demo/x` *is* `demo/x` on a case-insensitive filesystem); when git cannot answer (missing, timeout, "dubious ownership", non-zero exit) inside a git work tree (a `.git` at or above the repo root) every orphan is kept — the check fails closed. Every other orphan stays engine-owned: carried into the lockfile stamped in step 8 (orphans are settled just before stamping). With `commit = false` (the default) kept orphans are also listed in the managed block until they are gone, so leftover output never becomes committable: write the root-anchored paths of everything rendered plus the kept orphans into the managed block of the consumer's `.gitignore`, and ask git (read-only) whether any of them is still tracked and, if so, warn with the exact `git rm -r --cached -- …` to run. With `commit = true` remove the managed block and list the kept orphans on stderr — committed output is normally tracked, so a removed skill's committed files stay until the user deletes them (`git rm`). `.gitignore` is a user file: it is never hashed into the lockfile and never part of the written set. `.claude/settings.json` is a co-owned file of the same kind: its managed hook entries are owned through scoped lockfile entries, but the file itself is never whole-file locked, never listed in the managed block and never flagged as staged output.
10. **Hooks: pins, notices, approvals** (write mode). With hooks on, write the per-worktree interpreter pin `<git_dir>/playbook-hooks/interpreter` from `sys.executable` (first writer wins; `playbook-hook doctor --repin` rewrites it) and the tool pins in `machine.json` beside it — machine-local files outside the working tree, never committed and never in the lockfile. Print the summary lines and, when the shim's lockfile entry changed, the OpenCode restart notice; then, only on a TTY, ask the trust-on-first-use questions for external handlers and execution stages (§7.1.1). With `[hooks]` absent, print one notice line instead (`hooks available: …`) and change nothing.
Eval tasks (Section 6.5) are intentionally **not** part of the sync flow. They live in the engine's content, bundled plugins and overlay packages, are read at validation time (`playbook validate`) and enumeration time (`playbook eval --list`), and v2 will read them at runner time — but they never produce files in the consumer repo. They are authoring-side artifacts, not deliverables.
### 4.3 Key design choices, recapped
- **Copies, not symlinks.** Cross-platform, banking-friendly, git-friendly.
- **Jinja sparingly.** Variable substitution and conditional file selection only. Avoid `{% if %}` inside rule bodies — makes templates unreadable.
- **Sentinel headers.** Generated text files carry the sentinel `AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync'` — verbatim the code string `SENTINEL` of the import-light `coding_agent_playbook.generated_output.sentinel`. The wording is never changed, since a new wording would make every consumer's generated files drift on upgrade. Markdown output carries it as an HTML comment, `<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->`, on line 1, or — when the harness needs frontmatter on line 1 (the `agent_harness` adapter, §10.7.3) — on the first body line after the closing `---` fence. Native skill `SKILL.md` files (§10.8) use that second position too, as do OpenCode commands (§10.6.1; gray-matter reads frontmatter only at offset 0) and read-only Claude commands, which open with a `disallowed-tools` frontmatter block (§9.7). Non-markdown output carries it on line 1 in its own comment syntax: `# …` in the Claude Code launcher `.claude/hooks/playbook/launch.sh`, `// …` in the OpenCode shim `.opencode/plugins/playbook-hooks.js`; neither has a shebang. Those two anchored positions are the only ones cleanup recognises (`generated_output.sentinel.has_sentinel`, every scanner and hook guard alike), and only as an exact sentinel line (a leading UTF-8 BOM some editors add on save is ignored); the sentinel quoted anywhere else — or inside prose on one of those lines — is user text. **Exceptions** — files that carry no sentinel and whose ownership is recorded only in `.coding-agent-playbook.lock` (§14.4; `agent_harness` scripts also in `.playbook/manifest.toml`, §20.10): byte-copied skill `scripts/` and `references/`, byte-copied external hook scripts (`.coding-agent-playbook/hooks/scripts/<hook-id>/`), and strict-JSON output (JSON has no comment syntax): `guard_config.json` as a whole file, and each managed hook entry of the user's `.claude/settings.json` as one scoped lockfile entry — never markers. Everything inside a skill directory — `SKILL.md` included — is deleted only through the lockfile leftover policy (§4.2 step 9), never by a sentinel scan.
- **Detector facts are cached.** Written into `.coding-agent-playbook.toml` at init. Refreshed automatically when `pyproject.toml` mtime changes, or manually via `playbook check --refresh`.
- **`AGENTS.md` is always generated.** Even if no adapters are enabled — as long as at least one always rule survives `applies_if` filtering, a skill contributes a Where line or a hook advisory exists (§10.4). It is the lowest-common-denominator output and costs nothing. That includes a repo whose only content is hooks; its Guardrails section exists only when hooks are on.
- **Generated output is local-only by default.** Rendered files are build products of the installed engine + overlays + `playbook/`, so (with `[output] commit = false`) they are gitignored through an engine-owned managed block and regenerated on each machine by the `post-checkout`/`post-merge` hook — the committed source of truth is the config and `playbook/`, not the rendered copies.
- **Lifecycle hooks keep these invariants** (v0.20; the full list with its owners is `specs/prK-lifecycle-hooks.md` §I). The bullets above apply to hooks too: hook scripts are byte copies, only `HOOK.md.j2` bodies pass through the sandboxed Jinja environment, and frontmatter is static YAML.
  - **Engine upgrades never inject executable hooks.** An absent `[hooks]` table, or one without `enabled = true`, means no hook output: no settings entries, launcher, shim or advisory text; `playbook init` asks, and `playbook sync` prints one notice line.
  - **Hook outputs are only `deny | ask | context | none`.** Never `allow`, an input rewrite, or an HTTP, async, prompt or agent handler (validate rules H5 and H8, backed by the dispatcher's closed-key renderers). Only engine builtins may hold the `mutates_edited_file` capability (post-edit formatting).
  - **One registration per harness event**, fanned out in-process, plus at most one async, non-deciding, output-free `PostToolUse` registration for audit-only handlers.
  - **The hot path is import-light.** The dispatcher imports nothing outside `hook_runtime.*`, `security.*`, `artifacts.path_classes` and the standard library, and starts no subprocess for a call that touches neither git nor a pragma.
  - **Exit codes.** The launcher exits 0 or 2 (1 only under `--strict-launch`); `dispatch` exits 0 or 10 (`DENY_EXIT`); a raw 2 is never a deny; the OpenCode shim throws only on exit 10 or a `deny` decision.
  - **Rendered hook outputs are machine-independent.** No absolute path, stat signature or `$HOME` path in any file sync renders; the interpreter and tool pins live under the git dir.
  - **`.local.toml` never carries policy.** `[hooks]`, `[guardrails]`, `[metrics]` and `[hooks.commit_convention]` written there are ignored (§7.2).
  - **No repo- or overlay-controlled code runs without a user-local trust entry** (`[hooks] allow_code_from` plus a TTY-only trust-on-first-use approval); the interpreter pin is not trust.
  - **Escape hatches come only from the hook process's own environment**, with exact values. A hatch set through a settings file's `env` object is ignored and reported, and a pragma counts only when present at `HEAD`.
  - **Every git call goes through `SafeGit`**: filter drivers neutralized, `core.fsmonitor=false`, no external diff or textconv, a scrubbed environment, bounded timeouts.
  - **The decision log stores no content**: no command text, paths, prompts, reasons or environment values.
  - **A stage never reports green on an error, and red is never presented as green.** One combined Stop reason per tree fingerprint, at most `max_blocks` blocks per stop chain.
  - **Every speed bump has an off-workstation twin** (a pre-commit hook or a `playbook ci` step), and every guard is labelled honestly as a boundary, a speed bump or detective.
  - **User-owned settings are never modified.** User keys, user hook groups and user permission entries in `.claude/settings.json` stay byte-stable, managed elements are identified only by lockfile hash, and `settings.local.json` is never written.
  - **Overlays only add**, and a `mandatory` overlay hook cannot be disabled by `[hooks] disable` or shadowed by a repo-local override (§11.6).
  - **Tool policy has one source** shared by a hook and its twins: `[metrics]`, `[tool.commitizen]` and `[hooks.commit_convention]`.
  - **Hooks are git-only in v1.**
## 5. Repository layout
### 5.1 The engine repo (`coding-agent-playbook`)
```
coding-agent-playbook/
├── pyproject.toml                          # hatch force-includes catalog/ as coding_agent_playbook/_catalog/
├── README.md
├── SPEC.md                                 # this file
├── CHANGELOG.md
├── .pre-commit-hooks.yaml                  # exposes hooks to consumers
├── catalog/                                # everything content maintainers edit; not a Python package
│   ├── README.md                           # contributor guide: where each kind lives, how to add one
│   ├── core/                               # the engine layer, always on (Section 6.3.3 for its skills)
│   │   ├── ATTRIBUTIONS.md
│   │   ├── rules/                          # the shipped inventory: 2 always rules, 26 scoped
│   │   │   ├── always/
│   │   │   │   ├── 00-project-context.md.j2      # uses {{ project_name }}
│   │   │   │   └── 10-python-house-style.md      # plain markdown, no vars: eight bullets
│   │   │   ├── languages/python/                 # python-coding members in priority order, then two python-tooling members
│   │   │   │   ├── dependency-injection.md       # 40
│   │   │   │   ├── pure-core.md                  # 42
│   │   │   │   ├── data-shapes.md                # 44
│   │   │   │   ├── typing.md.j2                  # 50, Python >=3.11; branches on python_version
│   │   │   │   ├── performance-idioms.md         # 51, distilled
│   │   │   │   ├── async.md                      # 53, distilled; Python >=3.11
│   │   │   │   ├── classes-and-protocols.md      # 53, distilled
│   │   │   │   ├── error-handling.md             # 55
│   │   │   │   ├── context-managers.md           # 56
│   │   │   │   ├── docstrings.md                 # 56
│   │   │   │   ├── retries-and-timeouts.md       # 57, when requests, httpx or aiohttp is used
│   │   │   │   ├── idioms.md                     # 58
│   │   │   │   ├── static-checks.md              # python-tooling member (21), distilled; ungated
│   │   │   │   └── uv-workflow.md                # python-tooling member (28), distilled; uv projects only
│   │   │   ├── frameworks/
│   │   │   │   ├── fastapi-app-wiring.md         # python-tooling member (60), FastAPI only
│   │   │   │   ├── fastapi-error-boundaries.md   # python-tooling member (61), FastAPI only
│   │   │   │   ├── pytest-configuration.md       # python-tooling member (23), distilled; pytest only
│   │   │   │   ├── pydantic-boundaries.md        # python-tooling member (63), distilled; Pydantic declared
│   │   │   │   ├── pytest.md.j2                  # python-testing member (60); branches on pytest-asyncio
│   │   │   │   ├── pytest-test-doubles.md        # python-testing member (61), distilled
│   │   │   │   └── pytest-fixtures.md            # python-testing member (63), distilled
│   │   │   └── ml/
│   │   │       ├── serialization-security.md.j2  # ml-data member (30); branches on the ML stack
│   │   │       ├── vectorization.md.j2           # ml-data member (71), distilled; these four: NumPy, pandas or polars, a section per library
│   │   │       ├── data-transforms.md.j2         # ml-data member (71), distilled
│   │   │       ├── dtypes-and-typing.md.j2       # ml-data member (73), distilled
│   │   │       └── reproducibility-and-testing.md.j2  # ml-data member (73), distilled
│   │   ├── prompts/
│   │   │   ├── refactor.md                     # plain markdown
│   │   │   ├── generate-tests.md.j2            # branches + includes_rules
│   │   │   ├── tdd-cycle.md.j2                 # includes_rules
│   │   │   ├── review.md.j2                    # includes_rules
│   │   │   ├── docstrings.md.j2                # uses {{ docstring_style }}
│   │   │   ├── explain.md                      # plain markdown
│   │   │   └── spec.md                         # plain markdown
│   │   ├── hooks/                          # canonical <id>/HOOK.md dirs, builtin handlers only (Section 6.6.7)
│   │   │   ├── protect/  verify/  feedback/
│   │   │   └── safety/  audit/                 # category folders carry no meaning
│   │   ├── skills/                         # python-coding/ python-testing/ python-tooling/ ml-data/: SKILL.md only
│   │   └── eval_tasks/
│   │       ├── ATTRIBUTIONS.md
│   │       ├── generate-tests-happy-path/
│   │       │   ├── task.toml
│   │       │   └── setup/
│   │       │       └── src/calculator.py
│   │       ├── generate-tests-edge-cases/
│   │       │   └── ...
│   │       ├── make-testable-inject-clock/
│   │       │   ├── task.toml
│   │       │   ├── setup/                  # the repo the agent starts from
│   │       │   └── solution/               # reference answer the gate must pass
│   │       │       └── negatives/          # known-wrong attempts the gate must fail
│   │       └── refactor-extract-helper/
│   │           └── ...
│   └── plugins/                            # bundled plugins, off by default (Section 11.5)
│       ├── python_design/                  # distilled Python design skills (Section 11.5.2)
│       │   ├── README.md                   # what it is and how to enable it
│       │   ├── ATTRIBUTIONS.md             # credit for the distilled ideas (no copied text)
│       │   └── skills/<id>/                # 2 skills: SKILL.md + scripts/ (stdlib) + references/
│       └── superpowers/                    # vendored Superpowers skills (Section 11.5.1)
│           ├── README.md                   # what it is and how to enable it
│           ├── LICENSE                     # upstream MIT notice (ships with every copy)
│           ├── ATTRIBUTIONS.md             # source, version, indication of changes
│           └── skills/<id>/                # 15 skills: SKILL.md + scripts/ + references/
├── src/coding_agent_playbook/              # logic only: no rule, prompt, eval task, skill or hook file
│   ├── __init__.py
│   ├── cli/                                # `playbook` entrypoint: __init__ (main), parser, __main__, _command (the Command protocol)
│   ├── artifacts/                          # Rule, Prompt, Skill, Hook dataclasses (Section 6.6)
│   │   ├── rule.py, prompt.py, skill.py, hook.py   # one module per artifact
│   │   ├── frontmatter.py                  # the markdown + YAML frontmatter format they share
│   │   ├── identity.py                     # artifact_id_of, template_source: the id and template name (stdlib)
│   │   └── hook_schema.py, hook_frontmatter.py, member_reference.py, path_classes.py   # stdlib leaves
│   ├── skills/                             # skill composition (§6.3.3): document, membership, naming
│   ├── config/                             # the consumer config (Section 7)
│   │   ├── model.py                        # Config dataclass and the [output] parser
│   │   ├── schema.py                       # per-file checks, ConfigError
│   │   ├── entries.py                      # the entries Config owns; the others ride along
│   │   ├── files.py                        # ConfigFiles: the two files' reads, checks, merge and write; StateSource ABC + FileSystemStateSource
│   │   ├── committed.py                    # the committed-config rewrites of init and check --refresh (Section 7.2)
│   │   └── tables/
│   │       ├── hooks.py                    # [hooks] / [guardrails] tables (Section 7.1.1)
│   │       └── links.py                    # [links] table (Section 12.6)
│   ├── metrics_gate/                       # the metrics gate (§21.5); config.py: [metrics] table (§7.1.1)
│   ├── catalog/                            # the Catalog: its roots, layers, artifact source and overlay merge
│   │   ├── roots.py                        # the only code that knows where catalog/ is (Section 20.3)
│   │   ├── layers.py                       # the layer labels ENGINE_PACKAGE and REPO_LOCAL_SOURCE (Section 11)
│   │   ├── source.py                       # ArtifactSource ABC + the filesystem artifact source (Section 20)
│   │   ├── resolve.py                      # OverlayResolver: the three-layer merge by id, collisions (Section 11)
│   │   └── _hook_walk.py                   # one layer's hook directories (Section 6.6.7)
│   ├── detector/                           # the Detector (Section 8)
│   │   ├── facts.py                        # facts dictionary (Facts, detect)
│   │   ├── predicate.py                    # applies_if evaluator and filter (Section 6.4)
│   │   ├── pep503.py                       # PEP 503 package-name normalization
│   │   └── pyproject_deps.py               # pyproject dependency tables, one parser
│   ├── sync/                               # the sync pipeline (§12.2, §12.3): pipeline (execute), render, git_client (GitClient), check modes, leftovers
│   ├── validation/                         # the validation rule set: checks, findings, context (SyncContext), preflight, prompts, link_check (§12.6)
│   ├── renderer.py                         # Jinja2 environment
│   ├── generated_output/                   # the files the engine writes and owns in a consumer repo
│   │   ├── sentinel.py                     # SENTINEL, import-light (Section 4.3)
│   │   ├── gitignore.py                    # managed .gitignore block ([output] commit = false)
│   │   ├── file_identity.py                # FileSet: stale-vs-written by file identity (§4.2 step 9)
│   │   ├── symlinks.py                     # dangling-link predicates that never raise (§12.2)
│   │   └── output_io.py                    # generated-file writers that refuse a FIFO/socket/device (§12.2)
│   ├── overlays.py                         # overlay resolution
│   ├── lockfile/                           # .coding-agent-playbook.lock: model, drift, canonical_json
│   ├── toml_writer.py                      # the TOML writer: dump_toml and the shared scalar/key primitives
│   ├── precommit.py                        # the pre-commit starter template and the text merge (§13.2, §13.3)
│   ├── hook_policy/                        # sync-time: hook layer merge, effective view, validate H1-H21
│   ├── hook_registrations/                 # per-harness registrations: Claude groups, OpenCode REG + shim
│   ├── guard_config.py                     # the sync-level guard_config.json (§4.2 step 7)
│   ├── hook_runtime/                       # the playbook-hook dispatcher: import-light, never imports cli/
│   │   ├── handlers/                       # builtin hook handlers (@register_hook_handler)
│   │   ├── harness/                        # per-harness payload parsers and wire renderers
│   │   ├── judges/                         # the checks a guard hook shares with its guard twin
│   │   │   └── gate_weakening.py           # added-line suppression/loosening scan (`playbook gate-scan`)
│   │   └── stop/                           # the Stop stage contract and coordinator
│   ├── security/                           # secret paths/patterns, PII, trust store, audit log (stdlib)
│   ├── adapters/
│   │   ├── __init__.py
│   │   ├── base.py                         # Adapter ABC
│   │   ├── registry.py                     # entry-point discovery: discover_adapters, installed_output_locations
│   │   ├── skill_dirs/
│   │   │   ├── __init__.py
│   │   │   ├── writer.py                   # shared native SkillWriter (Section 10.8)
│   │   │   └── ownership.py                # previous lockfile as proof of engine-written files
│   │   ├── continue_.py                    # trailing underscore: `continue` is a keyword
│   │   ├── claude_code/
│   │   │   ├── __init__.py
│   │   │   ├── adapter.py                  # ClaudeCodeAdapter: the rules file, the CLAUDE.md stub, skills
│   │   │   ├── hooks.py                    # ClaudeHookEmitter: managed settings groups, launcher, heartbeat
│   │   │   ├── _secret_native.py           # native deny rows of the secret guards
│   │   │   ├── _destructive_native.py      # native deny rows of the destructive-command guard
│   │   │   ├── _overlay_native.py          # native rows of the network and sensitive-read guards
│   │   │   ├── paths.py                    # stdlib-only: the rules file and CLAUDE.md stub paths (§10.3.1)
│   │   │   └── settings/
│   │   │       ├── __init__.py
│   │   │       ├── managed_merge.py        # managed merge into .claude/settings.json `hooks`
│   │   │       └── drift.py                # how `playbook check` judges the managed elements
│   │   ├── opencode.py
│   │   ├── shared_skills.py                # the shared skill root .agents/skills/
│   │   └── agents_md.py
│   ├── evals/                              # v1: task schema active; v2: runner placeholder
│   │   ├── __init__.py
│   │   ├── task.py                         # v1: EvalTask + dataclasses (active)
│   │   ├── loader.py                       # v1: walks each layer's eval_tasks/ (active)
│   │   ├── validator.py                    # v1: cross-reference checks (active)
│   │   ├── runner.py                       # v2: HarnessRunner ABC (placeholder)
│   │   ├── judge.py                        # v2: Judge ABC (placeholder)
│   │   ├── registry.py                     # runner and judge lookups (entry-point groups)
│   │   └── report_format.py                # text and JSON views of a task result
│   └── templates/
│       ├── hook_shims/                     # launcher + OpenCode shim templates (str.replace, never Jinja)
│       └── precommit/
│           └── config.yaml.j2              # starter .pre-commit-config.yaml (engine wiring, not content; Section 13.2)
├── tests/
│   ├── plugins/                            # bundled-plugin gates (Sections 11.5.1, 11.5.2)
│   ├── artifacts/                          # test_artifacts.py, test_hook.py, test_hook_frontmatter.py, ...
│   ├── catalog/                            # test_roots.py, test_source.py, ...
│   ├── detector/                           # test_facts.py, test_predicate.py, ...
│   ├── unit/
│   │   ├── test_renderer.py
│   │   ├── test_overlays.py
│   │   └── test_eval_tasks.py
│   ├── lockfile/
│   │   └── test_model.py
│   ├── metrics_gate/                       # test_run.py, test_config.py, test_policy.py, ...
│   ├── sync/                               # test_dispatch.py, test_leftovers.py, test_output_policy.py, ...
│   ├── validation/                         # test_skills.py, test_preflight.py, test_link_check.py, ...
│   ├── hook_runtime/                       # dispatcher, normalization, decisions, Stop coordinator
│   ├── hooks/                              # one module per shipped hook, golden payloads
│   ├── security/
│   ├── adapters/
│   │   ├── test_continue.py
│   │   ├── test_claude_code.py
│   │   ├── test_opencode.py
│   │   └── test_agents_md.py
│   ├── integration/
│   │   └── test_end_to_end.py              # fake consumer repo, full sync
│   └── fixtures/
│       ├── repos/                          # synthetic consumer repos
│       └── golden/                         # expected adapter outputs
└── docs/
    ├── getting-started.md
    ├── authoring-rules.md
    ├── authoring-overlays.md
    └── adapter-contract.md
```
`catalog/` is a source folder only: there is one wheel, and hatch copies `catalog/` into it at build time as `coding_agent_playbook/_catalog/` (`[tool.hatch.build.targets.wheel.force-include]` `"catalog" = "coding_agent_playbook/_catalog"`), so an installed engine holds `coding_agent_playbook/_catalog/{README.md,core/…,plugins/<name>/…}` next to `coding_agent_playbook/templates/precommit/config.yaml.j2` and `coding_agent_playbook/templates/hook_shims/`. That installed layout is internal, not a user-facing contract. `catalog.roots.catalog_root()` finds the content in either place (Section 20.3). The pre-commit template stays in `src/`: it is engine wiring, not playbook content, and its hook ids are duplicated in `precommit.py`. So do the hook shim templates (the Claude Code launcher and the OpenCode plugin, with `opencode_wire_port.py`, the Python port of the plugin's wire parser): they are filled by `str.replace` (`hook_registrations/_templates.py`), never walked as artifacts, and no layer can override them; the hooks themselves are content (`catalog/core/hooks/`). `README.md`, `LICENSE` and `ATTRIBUTIONS.md` sit at a layer root, outside every kind directory, so no artifact walk picks them up and sync never copies them into a consumer repo. The top-level name `catalog/` avoids every name the path logic or the adapters treat specially: `resources/` and `playbook/` (matched by path logic), a root-level `skills/`, `prompts/`, `rules/` or `references/` (adapter output), a gitignored harness directory, and unanchored ignored names such as `build/` or `lib/`.
### 5.2 An overlay repo (`playbook-rules-bnp`)
Overlays are minimal — they ship only their additional content. They depend on the engine for the renderer, adapters, and CLI.
```
playbook-rules-bnp/
├── pyproject.toml                          # depends on coding-agent-playbook>=0.4
├── README.md
└── src/playbook_rules_bnp/
    ├── __init__.py                         # registers entry point
    └── resources/
        ├── rules/
        │   ├── always/
        │   │   └── 30-bnp-banking.md       # plain markdown
        │   ├── compliance/
        │   │   ├── pii-handling.md         # plain markdown
        │   │   ├── dependency-allowlist.md.j2  # iterates allowlist from config
        │   │   └── audit-logging.md        # plain markdown
        │   └── infra/
        │       ├── litellm-routing.md.j2   # uses {{ litellm_base_url }}
        │       └── air-gapped-net.md       # plain markdown
        └── prompts/
            ├── pii-scan.md.j2              # includes_rules: [pii-handling]
            └── compliance-review.md.j2     # includes_rules: [...]
```
The overlay registers itself via an entry point in its `pyproject.toml`:
```toml
[project.entry-points."coding_agent_playbook.overlays"]
bnp = "playbook_rules_bnp:OVERLAY"
```
The engine discovers all installed overlays via `importlib.metadata.entry_points`.
### 5.3 A consumer repo after `playbook init`
```
risk-models/                                # the user's project
├── pyproject.toml                          # already there; deps added by init
├── .coding-agent-playbook.toml             # committed ([output] commit = false)
├── .coding-agent-playbook.local.toml       # gitignored
├── .coding-agent-playbook.lock             # gitignored (managed block); drift detection
├── .pre-commit-config.yaml                 # committed; auto-sync + staged-output guard
├── .gitignore                              # committed; .local.toml + the managed block
├── AGENTS.md                               # AUTOGENERATED, gitignored
├── .continue/                              # only with continue in adapters_enabled (opt-in since v0.21)
│   ├── rules/
│   │   ├── 00-project-context.md           # AUTOGENERATED
│   │   ├── 10-python-house-style.md
│   │   ├── 20-tooling-baseline.md
│   │   ├── 30-bnp-banking.md               # from overlay
│   │   ├── 44-python-data-shapes.md        # a python-coding member: Continue still gets one file per rule
│   │   ├── 50-python-typing.md
│   │   ├── 60-fastapi.md                   # only because fastapi detected
│   │   └── 70-pydantic-v2.md
│   └── prompts/
│       ├── refactor.md
│       ├── generate-tests.md
│       ├── review.md
│       └── explain.md
├── .coding-agent-playbook/
│   └── hooks/                              # AUTOGENERATED (hooks on): sync-level, no adapter
│       ├── guard_config.json               # the record the playbook-hook dispatcher reads
│       └── scripts/<hook-id>/              # byte-copied external-handler scripts, if any
├── .claude/
│   ├── CLAUDE.md                           # AUTOGENERATED: a rule-free stub (§10.3.1)
│   ├── rules/
│   │   └── coding-agent-playbook.md        # AUTOGENERATED: always rules + Where map; every other file here is the user's
│   ├── settings.json                       # the user's; with hooks on, sync manages its `hooks` entries
│   ├── hooks/playbook/launch.sh            # AUTOGENERATED (hooks on): the machine-independent launcher
│   ├── commands/
│   │   ├── refactor.md
│   │   ├── generate-tests.md
│   │   ├── review.md
│   │   └── explain.md
│   └── skills/                             # AUTOGENERATED — Claude Code native skills
│       ├── python-coding/                  # AUTOGENERATED: core skill; references rendered from its member rules
│       │   ├── SKILL.md                    #   (composed description + generated references index, §6.1.6)
│       │   └── references/python-typing.md …
│       └── query-db/
│           ├── SKILL.md
│           └── scripts/run.py
├── .opencode/
│   ├── command/                            # AUTOGENERATED — OpenCode slash commands
│   │   ├── refactor.md
│   │   ├── generate-tests.md
│   │   ├── review.md
│   │   └── explain.md
│   ├── plugins/
│   │   └── playbook-hooks.js               # AUTOGENERATED (hooks on): the one generated OpenCode plugin
│   └── skills/                             # AUTOGENERATED — OpenCode native skills
│       ├── python-coding/                  #   (byte-identical to .claude/skills/python-coding/)
│       └── query-db/                       #   (byte-identical to .claude/skills/query-db/)
├── .agents/
│   └── skills/                             # AUTOGENERATED — shared skill root (Codex, OpenCode), §10.8
│       ├── python-coding/                  #   (byte-identical to .claude/skills/python-coding/)
│       └── query-db/                       #   (byte-identical to .claude/skills/query-db/)
└── playbook/                               # OPTIONAL: per-repo customizations
    ├── rules/
    │   └── risk-models-specific.md.j2
    ├── skills/
    │   └── query-db/                       # canonical skill source (SKILL.md with `id: query-db` + scripts/)
    └── hooks/
        └── check-names/                    # repo-local hook: HOOK.md (+ scripts/ for an external handler)
```
Everything marked AUTOGENERATED carries the sentinel and is owned by `playbook sync` (a `SKILL.md` and an OpenCode command carry it as their first body line, since their frontmatter must stay on line 1; the files the engine writes into a skill directory are owned through that `SKILL.md` and the lockfile — a file a user adds to a generated skill directory stays the user's and is never deleted, §4.2 step 9). The user owns `.coding-agent-playbook.toml`, `.coding-agent-playbook.local.toml`, anything under `playbook/`, their own source code, and any hand-written skill directory (no sentinel) under the three skill roots — a canonical skill whose `id` collides with one is skipped for that root with a warning (Section 10.8). The output directory name is the skill's `id:` frontmatter value, not the source folder name (Section 6.3).
**Hook output (only with `[hooks] enabled = true`, which `playbook init` writes unless `--no-hooks` is given; §7.1.1).** Sync writes `.coding-agent-playbook/hooks/guard_config.json` and any copied scripts under `.coding-agent-playbook/hooks/scripts/`, the Claude Code launcher `.claude/hooks/playbook/launch.sh` and the OpenCode shim `.opencode/plugins/playbook-hooks.js`; they follow the `[output] commit` policy like every other generated file. `.claude/settings.json` is different: it stays the user's file (never gitignored, never whole-file owned), and sync only merges its managed matcher groups into the `hooks` key, each owned through a scoped lockfile entry. The pins the launcher and the shim read live outside the working tree, under `<git_dir>/playbook-hooks/`. Repo-local hooks are authored under `playbook/hooks/<id>/`.
**Generated output is local-only (default `[output] commit = false`, §7.1).** `AGENTS.md`, `.continue/`, `.claude/CLAUDE.md`, `.claude/rules/coding-agent-playbook.md`, `.claude/commands/`, `.claude/skills/<id>/`, `.opencode/command/`, `.opencode/skills/<id>/`, `.agents/skills/<id>/` and the lockfile are **not committed**: `playbook sync` lists them in an engine-owned block of the repo's `.gitignore`, and every clone regenerates them locally (the `post-checkout`/`post-merge` hook runs `playbook sync`; run it once by hand right after cloning). The `.gitignore` itself, including that block, *is* committed so every checkout ignores the same paths:
```gitignore
.coding-agent-playbook.local.toml

# >>> coding-agent-playbook (managed — do not edit) >>>
/.agents/skills/review/
/.claude/CLAUDE.md
/.claude/commands/refactor.md
/.claude/rules/coding-agent-playbook.md
/.claude/skills/review/
/.coding-agent-playbook.lock
/.opencode/skills/review/
/AGENTS.md
# <<< coding-agent-playbook <<<
```
Block rules: entries are root-anchored (relative to the playbook repo root, where the `.gitignore` lives), sorted and de-duplicated, one per generated **file** — except that every file inside a generated skill directory (any directory holding a written `SKILL.md`, whatever adapter root it sits under) collapses to one `/<dir>/` entry. Glob metacharacters (`*`, `?`, `[`, `!`, `#`, `\`, leading/trailing spaces) are backslash-escaped so names match literally. Entries are Unicode-NFC-normalised (git on macOS reports precomposed paths and never normalises patterns); a name written in another form (NFD) gets a second entry in that form for Linux checkouts. Leftover output from an earlier sync that is still engine-owned (§4.2 step 9) stays in the block. The block is replaced in place (or appended after one blank line, creating `.gitignore` if needed); every byte outside it — CRLF endings, a missing final newline, a UTF-8 BOM before a first-line block — is preserved, the write is atomic (a uniquely named temp file + `os.replace`, never a fixed name that could clobber a user file), and re-running is a no-op. A start marker without an end marker, an orphan end marker, or a duplicated block is an error naming the file and line; the engine never guesses and never clobbers. With `[output] commit = true` the block is removed and the generated files are committed as before v0.16.
Note one deliberate non-duplication for OpenCode, and one deliberate duplication:
- **No `.opencode/rules/` directory.** OpenCode reads `AGENTS.md` natively as its primary rules source, walking up the directory tree (§10.6). The universal AGENTS.md adapter delivers OpenCode's always rules, and its scoped rules arrive as references in `.opencode/skills/<skill>/` (§6.1.6). OpenCode never scans a `.opencode/rules/` directory on its own: such files would load only if registered in `opencode.json`'s `instructions` array (user-owned, §10.6.4) or by a plugin, and would then duplicate what OpenCode already reads from `AGENTS.md`.
- **`.opencode/skills/` is written natively.** The OpenCode adapter emits its own skill tree so OpenCode works without the Claude Code adapter enabled. OpenCode also scans `.agents/skills/` and `.claude/skills/`; the duplicates are harmless because OpenCode keeps one discovered skill per name/id (v2 by precedence `.opencode > .agents > .claude`; v1 logs one duplicate warning per extra copy) and every copy is byte-identical (§10.6).
The user's own `.opencode/agent/` (custom agents), every other file under `.opencode/plugin/` or `.opencode/plugins/` (the user's own plugins), and `opencode.json` (MCP servers, permissions, model selection) are owned by the user and not touched by the engine. The one exception is the generated shim `.opencode/plugins/playbook-hooks.js`, which the OpenCode adapter owns (sentinel on line 1, whole-file lockfile entry) and writes only when hooks are on; OpenCode auto-discovers it, so `opencode.json` is never edited. See Section 10.6 for the OpenCode adapter's boundaries.
## 6. Canonical artifact model
### 6.0 File formats: `.md` and `.md.j2`
Every artifact — rules, prompts, skills — is a markdown file with YAML frontmatter. The file extension chooses between two processing paths:
- **`.md`** — plain markdown. No Jinja processing. The file is loaded, the frontmatter is parsed, and the body is used verbatim. Use this for the majority of artifacts.
- **`.md.j2`** — Jinja template. The file is loaded, the frontmatter is parsed, and the body is rendered through Jinja2 against the rendering context (facts + user_choices + project metadata). Use this only when the body needs variable substitution, conditionals, or rule inclusion.
The choice is made by the author per file. The renderer dispatches on extension:
```python
def render_artifact_body(template_path: Path, context: dict) -> str:
    if template_path.suffix == ".j2":
        return jinja_env.get_template(str(template_path)).render(**context)
    return template_path.read_text(encoding="utf-8")
```
**Important: frontmatter is always static YAML.** It is parsed by the engine *before* any Jinja rendering happens, because the engine needs to evaluate `applies_if` to decide whether to render the artifact at all. Putting Jinja inside frontmatter would create a chicken-and-egg problem and is rejected by the validator.
**When to use which:**
| Use `.md` when | Use `.md.j2` when |
| --- | --- |
| No variables, no conditionals | You substitute project facts (`{{ project_name }}`, `{{ python_version }}`) |
| The rule is generic across all projects | You branch on detected state (`{% if has_framework("fastapi") %}`) |
| You want the source to be readable as-is in a GitHub preview | You render a section only for some projects (`{% if has_ml_dep("torch") %}`) |
| Authors prefer not to learn Jinja | You loop over a list (`{% for dep in dependencies %}`) |
A realistic split from the engine's content (`catalog/core/`):
- `rules/frameworks/fastapi.md` — plain markdown. FastAPI conventions don't depend on project facts.
- `rules/always/00-project-context.md.j2` — needs `{{ project_name }}` and `{{ project_description }}`.
- `rules/languages/python/typing.md.j2` — branches on Python version for PEP 695 syntax.
- `prompts/refactor.md` — plain instructions, no variation needed.
- `prompts/generate-tests.md.j2` — branches on `pytest-asyncio` and project layout choice.
The `.j2` suffix is the author's explicit signal to readers: *"this file has logic in it."* Without it, the file is just markdown.
**Validation.** `playbook validate` checks `.j2` files for Jinja syntax errors and undefined variables. It does not run Jinja against `.md` files — they're treated as static content. This means renaming a file from `.md` to `.md.j2` triggers a stricter check on next validate.
### 6.1 Rules
A canonical rule is a Markdown file (with or without Jinja templating, per Section 6.0) and YAML frontmatter. The frontmatter declares metadata used by the adapters to render harness-specific output; the body is the rule content.
Where a rule lands depends on its scope. An always rule goes to the always-loaded files: `AGENTS.md`, the Claude Code rules file (§6.1.4) and Continue's rule files. A scoped rule names the skill that owns its topic (`skill:`, §6.1.1) and is written as a reference inside that skill (§6.1.6, §6.3.3); Continue, which reads no skills, still gets it as its own rule file (§6.1.3). For OpenCode, rules are not written to a separate location — OpenCode reads the universal `AGENTS.md` natively for the always rules (walking up the directory tree; see §10.6 for the per-version lookup and the v1-only `CLAUDE.md` fallback) and finds the scoped ones in `.opencode/skills/<skill>/references/`. No dedicated OpenCode rule directory is generated.
#### 6.1.1 Frontmatter schema
```yaml
id: python-typing                    # required, unique across all overlays
name: Typing                         # required, human-readable; a scoped rule's label in its skill's Covers clause
description: Prefer a concrete type …  # required: Continue's agentic pull-in; a scoped rule's line in its skill's index
version: 1                           # bump on breaking content change
scope: scoped                        # one of: always | scoped
skill: python-coding                 # required when scope=scoped, forbidden when scope=always: the one skill that owns this rule's topic (§6.3.3)
globs:                               # optional, list. When scope=scoped, these gate inclusion in Continue
  - "**/*.py"
applies_if:                          # optional Python expression evaluated against facts dict
  python_version: ">=3.11"
  has_framework: ["pydantic"]
priority: 50                         # optional, lower = earlier in lex order; default 50
tags: [language, python]             # optional, for filtering
lint_codes:                          # optional: the ruff codes a rule-linked lint hook reports (v0.20)
  warn: [ANN001, ANN201, UP007]
  when:                              # extra codes under a sync-time applies_if predicate
    - applies_if: {python_version: ">=3.12"}
      warn: [UP040]
```
`skill` must name a skill that exists after the layer merge and declares a `playbook:` block (§6.3.3, §11.2), so an overlay or `playbook/rules/` adds a rule to a core skill just by naming it; Continue ignores the field (§10.2). Because the engine delivers a scoped rule as a reference of that skill, `description` is the rule's line in the skill's references index: write it as one actionable sentence. `name` is the rule's label in the skill's Covers clause, so keep it a short topic label (`Typing`, not `Python typing conventions`).

`lint_codes` links the rule's text to the hook that enforces it: a hook whose `linked_rule` names this rule inherits its `applies_if` and `globs`, and the resolved code list (`warn` plus every `when` row whose predicate holds at sync) is merged into the hook's handler `config` (§6.6.7) as `lint_codes = {rule, skill, warn}`, with `skill` the rule's own `skill` (absent when it names none), so lint feedback names where the fix lives: `rule python-error-handling (skill python-coding): …`. There is no `block` key: lint feedback is warn-only. `playbook validate` checks the shape and the predicates, and an empty `lint_codes` is dropped from the markdown round trip, so unlinked rules stay byte-identical.
#### 6.1.2 Example: `catalog/core/rules/languages/python/typing.md.j2`
```markdown
---
id: python-typing
name: Typing
description: Prefer a concrete type or a Protocol to Any, write X | None, and take abstract read-only types as inputs.
version: 1
scope: scoped
skill: python-coding
globs:
  - "**/*.py"
applies_if:
  python_version: ">=3.11"
priority: 50
tags: [language, python]
---
# Python typing standards
Target Python version: {{ python_version }}.
## Always
- All public functions and methods have full type annotations on parameters and return value.
- Use `from __future__ import annotations` at the top of every module that uses forward references.
- Prefer built-in generics over `typing` aliases: `list[int]` not `List[int]`, `dict[str, Any]` not `Dict[str, Any]`.
{%- if python_version >= "3.12" %}
## Python 3.12+ specific
- Use PEP 695 generic syntax for new code: `def first[T](xs: list[T]) -> T: ...`.
- Use the `type` statement for aliases, not `TypeAlias`.
{%- else %}
## Python 3.11
- Use `TypeVar` for generics, `TypeAlias` for aliases.
- Note: PEP 695 generic syntax is not yet available.
{%- endif %}
## Never
- Never use `Any` without a `# type: ignore[misc]` and a comment explaining why.
- Never use bare `Optional[X]` — write `X | None`.
- Never use string forward references unless the cycle is genuinely unavoidable.
## Examples
✅ Good:
```python
from __future__ import annotations
def parse_response(payload: dict[str, object]) -> Response | None:
    ...
```
❌ Bad:
```python
from typing import Dict, Optional


def parse_response(payload: Dict) -> Optional["Response"]: ...
```
```
#### 6.1.3 Rendered output for Continue: `.continue/rules/50-python-typing.md`
```markdown
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->
---
name: Typing
description: Prefer a concrete type or a Protocol to Any, write X | None, and take abstract read-only types as inputs.
alwaysApply: false
globs:
- '**/*.py'
---
# Python typing standards
Target Python version: 3.12.
## Always
- All public functions and methods have full type annotations...
[body, fully rendered with Jinja substitutions]
```
#### 6.1.4 Rendered output for Claude Code: always rules in `.claude/rules/coding-agent-playbook.md`
```markdown
## Python house style

[the body of python-house-style, verbatim]

---

## Where guidance lives

Detailed conventions live in skills. Before you edit one of these files, load its skill and open the references its index lists.

- Model, array and data-frame code: skill `ml-data`
- Any Python file: skill `python-coding`
- Test files and conftest.py: skill `python-testing`
- Tool configuration and framework wiring: skill `python-tooling`

Lint feedback names a rule id; that rule's reference in the skill has the fix.

---
```
The Claude Code adapter concatenates the rules that name no skill into one rules file, `.claude/rules/coding-agent-playbook.md`, then the generated `## Where guidance lives` section, and leaves `.claude/CLAUDE.md` a rule-free stub (§10.3.1). A member rule (a scoped rule that names a skill in `skill:`, every scoped rule in core among them) is not in this file: it is a reference of that skill (§6.1.6, `docs/adr/0001-scoped-rules-are-delivered-as-skill-references.md`). Each section gets a `## {name}` heading and, for scoped rules, their globs in italics; the italic line is advisory only. The body follows verbatim — its own headings, a leading `# ` title included, are not demoted.
#### 6.1.5 Rendered output for AGENTS.md: section
Same shape as the Claude Code rules file, plus the Guardrails section (§10.4). Identical rule sections and the same `## Where guidance lives` section, byte for byte.
#### 6.1.6 Rendered output as a skill reference: `.claude/skills/python-coding/references/python-typing.md`
A member rule is written as `<skill root>/<skill>/references/<rule-id>.md` in every enabled skill root (§6.3.3), the same bytes everywhere: one italic line naming the rule and its globs, a blank line, then the body after Jinja, unchanged. A member without globs gets ``*Rule `<id>`.*``; the globs line is advisory. Reference files carry no sentinel: like copied references, they are owned through the lockfile, as `kind = "rule"` entries (§14.4).
```markdown
*Rule `python-typing`; applies to `**/*.py`.*

# Python typing conventions
[rest of the body, verbatim]
```
The skill's `SKILL.md` carries the composed description and, after the authored body, the generated index, one line per active member in `(priority, id)` order (`python-coding` on a repo where all twelve members apply):
```markdown
---
name: python-coding
id: python-coding
description: Library-agnostic Python conventions. Covers Dependency injection, Pure
  core, Data shapes, Typing, Performance idioms, Asyncio, Classes and protocols, Error
  handling, Context managers, Docstrings, Timeouts and retries, Idioms. Use when writing,
  changing or reviewing Python code.
---
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->

# Python coding
[the authored body]

## References

Each reference is one rule. Open only the ones the current task needs.

- [python-dependency-injection](references/python-dependency-injection.md) — Dependency injection: Pass I/O collaborators in as parameters; pick concrete implementations in one composition root per entry point.
- [python-pure-core](references/python-pure-core.md) — Pure core: Keep business logic free of I/O, clocks, randomness and hidden mutation; perform effects in a thin outer shell.
- [python-data-shapes](references/python-data-shapes.md) — Data shapes: Model records as dataclasses, not string dicts or parallel lists; freeze them with tuple fields; return at most three values; name magic constants.
- [python-typing](references/python-typing.md) — Typing: Prefer a concrete type or a Protocol to Any, write X | None, and take abstract read-only types as inputs.
[one line per remaining active member]
```
### 6.2 Prompts
A prompt is a named, invokable instruction. In Continue it becomes a slash command; in Claude Code it lives under `.claude/commands/`.
A prompt declares the rules its task needs in `includes_rules` — important enough to warrant a dedicated subsection (6.2.5). Since v0.21 (D15) that list is the only declaration: a Claude Code or OpenCode command opens with a generated `## Before you start` block naming the skills and references to load, while Continue, the `agent_harness` leaf and the eval runner append the rules' text.
#### 6.2.1 Frontmatter schema
```yaml
id: generate-tests                   # required
name: Generate tests                 # required
description: Generate pytest tests   # required
version: 1
slash: generate-tests                # the slash command name (Continue, Claude Code, OpenCode)
applies_if:                          # optional
  has_framework: ["pytest"]
input_variables:                     # optional, declared variables filled at invocation
  - name: target
    description: file or function to test
    required: true
includes_rules:                      # optional, the rule IDs the task needs (§6.2.5)
  - python-typing
  - pytest
  - python-error-handling
eval_tasks:                          # optional, task IDs that test this prompt (see Section 6.5)
  - generate-tests-happy-path
  - generate-tests-edge-cases
  - generate-tests-async-code
write_scope:                         # optional (v0.20): exactly one of `read_only: true` | `globs: [...]`
  globs: ["tests/**", "**/conftest.py"]
output_contract:                     # optional (v0.20): regexes the final message must match
  - '(?im)^\W*verdict\W*(approve|request changes)\W*$'
```
Two optional keys tie a prompt to the lifecycle hooks (§6.6.7); both are dropped from the markdown when empty, so other prompts render byte-identically:
- **`write_scope`** — what the prompt may write while it is active: `{read_only: true}` (a review or explain prompt) or `{globs: [...]}` (repo-relative globs, e.g. a test generator limited to `tests/**`). Absent means unrestricted. `playbook validate` rejects any other shape (both keys, `read_only: false`, an empty glob list). The prompt-write-scope-guard hook enforces it; a read-only prompt also renders natively restricted, as a Claude command with a `disallowed-tools` frontmatter block (§9.7) and as an OpenCode command bound to the read-only `plan` agent (§10.6.1).
- **`output_contract`** — Python regexes the agent's final message must match while the prompt is active, checked by the `output-contract` Stop stage (prompt-output-contract-on-stop). `playbook validate` compiles every entry and fails closed on one that does not compile.

A prompt is *active* for the turn the user opens with it, or in which the model runs it as a `Skill`. The hooks resolve that from Claude's session transcript once per turn (the turn's opening entry, its slash only); no hook process runs per prompt.
#### 6.2.2 Example: `catalog/core/prompts/generate-tests.md.j2`
```markdown
---
id: generate-tests
name: Generate tests
description: Generate pytest tests for the provided code, following the project's testing conventions
version: 1
slash: generate-tests
applies_if:
  has_framework: ["pytest"]
input_variables:
  - name: target
    description: File or function to test
    required: false
includes_rules:
  - python-typing
  - pytest
---
# Task: generate tests
You are writing tests for {{ project_name }}, a {{ project_kind }} project.
## Conventions
- Test framework: pytest{% if "pytest-asyncio" in dev_dependencies %} (with pytest-asyncio for async code){% endif %}.
- Test files live in `tests/`, mirroring the source layout under `src/`.
- One test file per source module: `src/foo/bar.py` → `tests/foo/test_bar.py`.
- Use `parametrize` for table-driven tests. Avoid loops inside test functions.
- Replace external services with named fakes passed in like production collaborators; patch with autospec only at thin third-party seams.
{%- if "pydantic" in dependencies %}
- For Pydantic models, prefer constructing real instances over mocking.
{%- endif %}
## Workflow
1. Read the target code carefully. List the branches, edge cases, and error paths.
2. Identify the public surface — only test public functions/methods. Private helpers are tested through their public callers.
3. For each public function, draft tests covering:
   - happy path
   - each branch identified above
   - each error path
   - boundary values (empty input, max size, None where allowed)
4. Run the tests. If any fail because the code has bugs, **report them; do not silently fix the code**. The user decides whether to fix the code or adjust the test.
5. Report coverage of the public surface.
## Output format
Produce one or more test files in the correct location. After writing, run `pytest -q tests/<path>` and report the result.
```
`includes_rules:` is the only declaration of the rules a prompt needs (D15): nothing in a body places rule text. `playbook check` shows the list, `playbook validate` errors when an id names no rule, and each adapter turns the list into its own delivery (§6.2.5). The body ends with its own last section; no `## Reference rules` heading is written by hand.
#### 6.2.3 Rendered output for Continue: `.continue/prompts/generate-tests.md`
```markdown
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->
---
name: Generate tests
description: Generate pytest tests for the provided code, following the project's testing conventions
invokable: true
---
# Task: generate tests
You are writing tests for risk-models, a python-application project.
[rest of body, fully rendered]

## Reference rules

### Typing

[full body of python-typing rule, inlined verbatim]

### pytest conventions

[full body of pytest rule, inlined verbatim]
```
The user types `/generate-tests` in the Continue panel and the rendered prompt — including the appended rule bodies — becomes the system instruction for the turn. Continue reads no skills, so its prompts keep the text inline.
#### 6.2.4 Rendered output for Claude Code: `.claude/commands/generate-tests.md`
Same body, no top-level frontmatter — Claude Code commands are pure markdown. Invoked via `/generate-tests`. Instead of rule bodies the command carries the `## Before you start` block, before the body's first `##` section:
```markdown
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->
# Task: generate tests
You are writing tests for risk-models, a python-application project.

## Before you start

1. Load skill `python-coding` and read its reference `references/python-typing.md`.
2. Load skill `python-testing` and read its reference `references/pytest.md`.
3. For each file in scope, also load any other listed skill whose description matches it.

## Conventions
[rest of body, fully rendered; no rule text]
```
The OpenCode command `.opencode/command/generate-tests.md` carries the same block, after its `description:` envelope and the sentinel line.
#### 6.2.5 Rule inclusion in prompts — full design
Why this exists. An authoritative slash command like `/generate-tests` must not depend on the agent stumbling onto the right guidance: *"every time this is invoked, the typing rule and the pytest rule are part of the task."* `includes_rules:` is that declaration. Since v0.21 a scoped rule is a reference inside the skill it names (§6.1.6, §6.3.3), and `includes_rules` is how a prompt carries a scoped rule into its own turn: on Claude Code and OpenCode as a pointer to that reference, loaded on demand, and inline for the harnesses without skills (D15, D22).

**The declaration: `includes_rules:`.** A list of rule ids, in the order the task needs them. It is the only mechanism: the `{{ rule() }}` Jinja helper was removed in v0.21, and a prompt (or rule, or hook body) that calls it fails `playbook validate` with a migration message (§12.6).
```yaml
includes_rules:
  - python-typing
  - pytest
```

**Delivery by consumer.**

| Consumer | What `includes_rules` becomes |
| --- | --- |
| Claude Code `.claude/commands/<slash>.md` | a `## Before you start` block; no rule body |
| OpenCode `.opencode/command/<slash>.md` | the same block as Claude Code |
| Continue `.continue/prompts/<slash>.md` | a `## Reference rules` appendix at the end: one `### <rule name>` section per rule, inline |
| agent_harness `prompts/<slash>/SKILL.md` | the same appendix (its scoped rules are top-level `references/<id>.md` files, not skill references, §10.7.2) |
| Eval runner (`evals/prompting.py`) | the body plus the same appendix, the text Continue gets (§15.3) |
| `playbook render <prompt> --format …` | per format, through the unfiltered registry of applicable rules (§12.7) |

**The block.** Inserted before the body's first level-2 heading outside a code fence (without one, after the leading `# ` title, or at the top). One numbered step per owning skill, in the order its first rule appears in `includes_rules`, listing only the references of rules that are active here; then a closing step:
```markdown
## Before you start

1. Load skill `python-coding` and read its references `references/python-typing.md`, `references/python-error-handling.md`.
2. For each file in scope, also load any other listed skill whose description matches it.
```
A prompt whose included rules resolve to no active reference gets no block, so it renders byte-identically to a prompt without `includes_rules`. Always rules get no line: they are already in always-loaded context.

**The appendix.** `## Reference rules`, then each included rule's text under `### {rule.name}`, each id once, in `includes_rules` order; a plain `.md` prompt gets it as well as a `.md.j2` one, since the adapter writes it, not Jinja.

**Resolution semantics.**
Rule inclusion happens after overlay resolution. If `python-typing` is overridden by the BNP overlay, the prompt gets the *overridden* version (its text in the appendix, its reference in its owning skill). This is intentional — prompts depend on rule IDs, not on the original engine content. An overlay author who improves a rule automatically improves every prompt that includes it.

**Filtered rules and inactive skills.**

| Situation | Claude Code / OpenCode | Continue / agent_harness / eval runner |
| --- | --- | --- |
| an included rule fails its `applies_if` | no reference listed (the registry holds only applicable rules) | rule omitted from the appendix |
| every member of a skill is filtered out | the skill is not written (§6.3.2), so no step names it | no change |
| every included rule filtered out | no block at all; the command is the body alone | no appendix |
| an included rule is `scope: always` | no line: it is already in always-loaded context | inlined |
| an included id names no rule | `playbook validate` error; if validate is bypassed (`playbook render`), no line | omitted |
| the same id listed twice | listed once | inlined once |

`playbook validate` does NOT error on a filtered rule, because the omission is a feature, not a misconfiguration: a rule filtered out in this repo is still a valid id.

**Validation (§12.6).** Three checks guard the declaration, since a typo would silently drop guidance: no prompt body calls `rule()` (any spelling, with or without trim markers); `includes_rules` is a list of non-empty strings (a bare string used to be iterated character by character); and every id names a rule in core, an enabled overlay or `playbook/rules/`, with a did-you-mean.

**Recursive inclusion is forbidden.**
A rule cannot itself reference other rules via `includes_rules:`. Only prompts have `includes_rules:`. This keeps the dependency graph one level deep and trivially analyzable. If a rule needs to reference content from another rule, the author should either (a) duplicate the relevant fragment, or (b) refactor both rules to share a common third rule, kept in `rules/shared/`. The validator enforces this.
**Tooling support.**
- `playbook check` shows, for each prompt, which rules it includes.
- `playbook render <prompt-id> --show-rules` prints each included rule with its `applies_if` outcome and its delivery: the owning skill and reference, or `always loaded` (§12.7).
- `playbook validate` runs the three checks above.
**Why not let rules be included by globs too?**
A natural follow-on idea: a prompt declares `includes_rules_matching: { tags: ["python", "testing"] }` and the engine picks up all matching rules. Rejected for v1 because it makes the rendered prompt non-deterministic from a glance at the source — you need to mentally execute the matcher against the current rule registry. Explicit lists are uglier but trivially readable. Revisit in v2 if the explicit lists become unwieldy.
### 6.3 Skills
Skills follow the **Agent Skills** layout that Claude Code and OpenCode both read natively. Core (`catalog/core/skills/`) ships the skills that own its scoped rules: `python-coding`, `python-testing`, `python-tooling` and `ml-data` (§6.3.3), plus `playbook-guardrails`, which takes no rules and holds the full guardrail text of the on hooks (§6.3.4). The skills of the opt-in bundled plugins (`catalog/plugins/superpowers/` and `catalog/plugins/python_design/`, off unless a consumer enables them, Section 11.5) own none. Overlay packages and repo-local `playbook/skills/<id>/` may ship either kind. They are written natively by the `claude_code` (`.claude/skills/`), `opencode` (`.opencode/skills/`) and `shared_skills` (`.agents/skills/`) adapters through one shared `SkillWriter` (§10.8), so every copy is byte-identical; the opt-in `agent_harness` adapter writes them natively in its own tree (`skills/<id>/SKILL.md`, §10.7). Adapters that keep the ABC default `write_skill` (Continue) degrade a skill to a prompt, except a skill with member rules (§6.3.2); the rules-only `agents_md` adapter does not emit skills at all (a skill with member rules adds its line to the Where map, §10.4).

**Every canonical skill must declare `id:` in its `SKILL.md` frontmatter.** The `id` — not the source folder name — is the overlay merge key (§11), the output directory name (`<root>/<id>/`) and the emitted `name`. A skill without `id:` falls back to the id `skill`, so several id-less skills collapse into one and all but the last are silently dropped; `playbook validate` reports every id-less (or non-string-id) skill (§12.6).

Emitted `SKILL.md` contract (enforced by the `SkillWriter`):
- **`name` = the skill id = the output directory name.** The Agent Skills standard requires `name` to equal the directory name and match `^[a-z0-9]+(-[a-z0-9]+)*$` (1–64 chars); OpenCode silently drops a skill that fails it. The writer always sets `name` to the canonical `id` (an authored display `name` is replaced); every other frontmatter key, including `id`, is kept. A `description` of 1–1024 chars is required. `playbook validate` flags ids that break the pattern and skills without a description (§12.6).
- **Path-safe ids only.** An id containing a path separator, `..`/`.`, NUL, or a drive/absolute prefix is rejected with a `ValueError` naming it — the writer never writes outside its root (and never writes through a symlink that escapes it: what lies under one is skipped with a warning, §10.8).
- **Sentinel as the first body line.** Frontmatter must start on line 1 (`^---`) for agent parsers, so the `SENTINEL` is an HTML comment right after the closing fence (the §10.7.3 pattern). A skill directory is engine-owned iff its `SKILL.md` carries the sentinel. Stale files in it are removed only by the lockfile leftover policy (§4.2 step 9) — a file the previous sync wrote that is still pristine and untracked; an edited copy, a tracked file, or a file the user added is kept.
- **Ownership is decided before writing.** If `<root>/<id>/` already exists and is not engine-owned — a hand-written skill dir with a colliding id, a symlink, or a plain file — the writer leaves it untouched and prints a warning instead of overwriting `SKILL.md` (which would turn the user's directory into engine output). Exceptions: an empty directory, and a sentinel-less directory whose `SKILL.md` the previous sync's lockfile lists (the pre-v0.15 `.claude/skills/` output had no sentinel), are claimed.
#### 6.3.1 Schema
A skill is a directory:
```
any-folder-name/                     # the output dir comes from `id:`, not this name
├── SKILL.md.j2                      # the prompt body, with frontmatter (must declare `id:`)
├── scripts/                         # optional, bundled scripts the skill can call
│   └── helper.py
└── references/                      # optional, additional context
    └── reference.md
```
#### 6.3.2 Degradation rule
When the Continue adapter encounters a skill, it:
1. Renders `SKILL.md.j2` as a prompt with `invokable: true`.
2. Copies the `scripts/` directory to `.coding-agent-playbook/skills/<skill-id>/scripts/` (a known location the prompt body can reference).
3. Inlines a note in the prompt: *"Helper scripts are available at `.coding-agent-playbook/skills/<skill-id>/scripts/`. You can read them if useful."*
This is graceful — the user loses the auto-discovery of skills but keeps the content and the scripts.
As implemented, only step 1 happens: `Adapter.write_skill` degrades through `Skill.to_prompt`, so neither `scripts/` nor `references/` reaches Continue, and no note is added (Section 11.5.1).
A skill with member rules (§6.3.3) is never degraded: its members already reach Continue as their own rule files, and the prompt would index `references/` files Continue never receives. So no `.continue/prompts/<core-skill>.md` is written.
#### 6.3.3 Skills with member rules
A scoped rule names the one skill that owns its topic in `skill:` (§6.1.1); seen from that skill it is a **member rule** (`CONTEXT.md`). Membership is resolved after the layer merge (§11.2), so an overlay or `playbook/rules/` joins a core skill by naming it, and an override of the skill keeps its members.
- **Which skills take members.** Only a skill that declares the catalog-only `playbook:` block; `playbook validate` rejects a rule naming any other skill (V14, §12.6), such as a bundled plugin skill.
- **Presence.** Such a skill is written only when at least one member passes `applies_if` (`skills.membership.compose_skills`); with none, it is absent from every root, and its earlier output is settled by the leftover policy (§4.2 step 9).
- **References.** Each active member is rendered as `references/<rule-id>.md` (§6.1.6) in every root the `SkillWriter` writes, and the emitted `SKILL.md` gains a generated `## References` index, one line per member in `(priority, id)` order: ``- [<rule-id>](references/<rule-id>.md) — <name>: <description>``.
- **The `playbook:` block.** `use_when` (the condition only) and `files` (a file-kind phrase of at most 80 characters, no trailing period) are read by the engine and never emitted: the emitted frontmatter keeps `name`, `id`, `description` and any other authored key.
- **Description.** The emitted description is `<capability sentence> Covers <member names>. Use when <use_when>.`, at most 300 characters by construction: when every name does not fit, the clause names the highest-priority members that do and ends with `and N more` (`skills.document.compose_description`).
- **Where map.** Each written skill with members and a `files` phrase adds one line, `- <files>: skill `<id>``, to the `## Where guidance lives` section of `AGENTS.md` and the Claude Code rules file (§10.3.1, §10.4).
- **Authoring.** The capability sentence is third person and has no `Use when`; the body says what the skill is for and how to pick a reference, never lists the references, names no rule id, has no Jinja and no markdown links, and stays well under 500 lines; hand-written files in the skill's own `references/` may sit next to the rendered ones, but none may take a member's file name (V12). Core's four skills are pinned by `tests/integration/test_core_skills.py` (§16.3).
#### 6.3.4 The guardrails skill
`catalog/core/skills/playbook-guardrails/SKILL.md` (id `hook_policy.guardrails_skill.GUARDRAILS_SKILL_ID`) holds the full text of every guardrail a repository enables, the text-form of its on hooks (`CONTEXT.md`: **Guardrail**). It has no member rules and no `playbook:` block, so its authored description carries its own `Use when` clause and is emitted as written; the D13 checks and the listing budget cover it like any core skill (`EXPECTED_PLAIN_CORE_SKILLS` in `tests/integration/test_core_skills.py`). An overlay or repo-local skill with the same id replaces the authored description and intro and still gets the generated sections.
- **Composition.** After skills are composed, sync takes this skill out of the skills every adapter receives (`split_guardrails_skill`) and appends to its authored body one section per on hook that has an advisory, sorted by hook id: ``## <name> (`<id>`)`` over the hook's advisory text, the rendered body plus its enforcement line (`compose_guardrails_skill`). One file, no references: the agent loads it rarely, and the core pack's sections stay far under 500 lines.
- **Presence.** It is written only with hooks on and at least one on hook with an advisory: with `[hooks] enabled = false`, no hook with a body, or `[hooks] advisory = false`, no adapter writes it, and output an earlier sync wrote is settled by the leftover policy (§4.2 step 9).
- **Targets.** Only an adapter whose `writes_guardrails_skill` holds for the on hooks receives it (§10.1): `opencode` (`.opencode/skills/`) and `shared_skills` (`.agents/skills/`) whenever any hook has an advisory, `claude_code` (`.claude/skills/`) only for a hook it cannot run natively (an overlay hook without `claude_code` in `supports`, or one whose events Claude Code cannot reach), never `continue` (which keeps `.continue/rules/30-guardrail-<id>.md`), `agent_harness` (`rules/30-guardrail-<id>.md`) or `agents_md`. It travels through `write_skill`, so it is written by the shared `SkillWriter`, byte-identical in every root, and locked as `kind = "skill"` with artifact id `playbook-guardrails` (§14.4).
- **AGENTS.md.** Its `## Guardrails` section (§10.4) carries one line per hook with guardrail text and names this skill in its preface; the skill holds each hook's full text and enforcement line, under one heading per hook, for the harnesses that read skills.
### 6.4 The `applies_if` predicate
`applies_if` is a small DSL that gates artifact inclusion. It is intentionally restricted to a handful of operators to keep it auditable; arbitrary Python is not allowed.
```yaml
applies_if:
  python_version: ">=3.11"           # comparison against detector facts
  has_framework: ["fastapi"]         # all of these must be present in facts["frameworks"]
  any_framework: ["pytest", "unittest"]  # at least one must be present in facts["frameworks"]
  has_ml_stack: ["torch", "numpy"]   # all of these must be present in facts["ml_stack"]
  any_ml_stack: ["torch", "tensorflow"]  # at least one must be present in facts["ml_stack"]
  has_dev_dependency: ["pytest-cov"] # all of these must be declared dev dependencies (v0.20)
  has_file: ["Dockerfile"]           # file must exist in repo root
  package_manager: "uv"              # facts["package_manager"] is this name (a list: any of them) (v0.21)
  banking_mode: true                 # boolean facts
```
Multiple keys are ANDed together. The evaluator lives in `coding_agent_playbook.detector.predicate.evaluate_predicate(predicate, facts) -> bool`. `playbook validate` checks each key on its own, so a malformed key is reported even when an earlier key does not hold (v0.21; hooks and `lint_codes.when` were already checked this way).
The framework operators (`has_framework`, `any_framework`) read `facts["frameworks"]`; the ML-stack operators (`has_ml_stack`, `any_ml_stack`) read the separate `facts["ml_stack"]` fact (torch, tensorflow, scikit-learn, … — see Section 8.2). Use the ML-stack operators to gate ML-specific rules and prompts, since ML libraries never appear in `frameworks`.
Skills carry no `applies_if`. A skill with member rules follows its members' gates: it is written only when at least one member passes (§6.3.3). There is no `any_of` combinator, so a skill whose members span stacks gates each member on its own (`ml-data`'s serialization rule on the model libraries and its four array and data-frame rules on NumPy, pandas or polars, each through `any_ml_stack`).
`has_dev_dependency` reads `facts["dev_dependencies"]` (Section 8.2) and compares names PEP 503-normalized, so `pytest_cov` matches `pytest-cov`. It mirrors `has_framework` for tools that live only in a dev group, and gates artifacts that need one: the opt-in coverage-diff-gate hook applies only with `has_dev_dependency: [pytest-cov]`.
`package_manager` reads the single-valued `facts["package_manager"]` (Section 8.2). Its value is one of `uv`, `poetry`, `pip-tools` or `pip`, or a non-empty list of them meaning any of them (a list of alternatives is the only useful reading of a single-valued fact). A repo whose detector sets no package manager never matches. The value is validated before the fact is read, so an unknown name, a wrong case, an empty list or a non-string is a `playbook validate` error in every repo, even one without the fact, naming the offending value and the four allowed names.
Note that `has_framework` appears in two distinct places with different shapes — once as a predicate key here (taking a list of required framework names), and once as a Jinja helper in the rendering context (taking a single framework name and returning a bool, see Section 9.4). The same split applies to the ML stack: `has_ml_stack`/`any_ml_stack` are `applies_if:` predicate keys (lists), while `has_ml_dep("torch")` is the Jinja callable (single name) used inside `{% if %}`. They share concepts but live at different evaluation layers (frontmatter is parsed before Jinja runs). When reading or writing artifacts, the rule is: lists in `applies_if:`, callables inside `{% if %}`.
### 6.5 Eval tasks (Tier 0: schema only, no runner)
Eval tasks are reproducible test cases associated with prompts. Each task captures: *"given this starting state and this invocation, here's what success looks like for this prompt."* In v1 only the **schema and validation** ship — there is no `playbook eval` runner, no LLM-as-judge, no scoring. Authors write tasks alongside the prompts they create; the tasks accumulate as institutional knowledge and become the input to the runner in v2.
This is what the spec means by "forward-compatible eval abstractions" (G6). Section 15 gives the runtime-side ABCs that v2 will implement; this section defines the authoring-side artifact format that v1 ships.
#### 6.5.1 Why ship the schema before the runner
Three reasons:
1. **Tasks are documentation.** A well-written task tells future authors what the prompt is for, what good output looks like, and what edge cases the prompt is expected to handle. That value exists with zero tooling — it lives in source review.
2. **Lock the format early.** If the schema lands in v1, every prompt added in v1 ships with eval tasks from day one. When v2's runner arrives, there's a corpus to run against. If the schema lands in v2, prompts written in v1 retroactively need tasks added, which never happens.
3. **`playbook validate` can already enforce hygiene.** Even without a runner, the engine can check that every `eval_tasks:` reference resolves, that no orphan tasks exist, and that task `setup/` files are present. This catches breakage at commit time.
#### 6.5.2 Directory layout
Eval tasks live alongside rules and prompts in the engine's core content, with the same overlay semantics:
```
catalog/core/
├── rules/
├── prompts/
└── eval_tasks/
    ├── generate-tests-happy-path/
    │   ├── task.toml                 # task metadata + the gate/rubric/verdict layers
    │   └── setup/                    # files written to scratch repo before invocation
    │       └── src/calculator.py
    ├── generate-tests-edge-cases/
    │   └── ...
    └── refactor-extract-helper/
        └── ...
```
Each task is a directory, not a single file, because tasks need fixture files (the `setup/` tree). The success criteria live inline in `task.toml` (the `[gate]`/`[rubric]` layers), not as separate golden-file fragments. Mirrors the skills pattern (Section 6.3).
Overlay packages (under `resources/`), bundled plugins and the consumer's `playbook/` can ship their own `eval_tasks/` directory, and the merge semantics are the same as for rules and prompts — later layers override earlier ones by task ID. A BNP overlay can override `generate-tests-happy-path` with a banking-flavored variant that includes the BNP rule pack.
Eval tasks are a **per-layer** kind: a bundled plugin ships its tasks in `catalog/plugins/<name>/eval_tasks/<id>/`, laid out exactly as in `catalog/core/`, and each task finds its prompt in the `prompts/` directory of its own layer (`evals/prompting.py:_infer_prompts_dir`, §12.8), so a plugin's task resolves the plugin's prompt even when another layer ships one with the same id. A plugin's tasks are walked, listed by `playbook eval --list` and runnable only in a repo that enables the plugin. In the engine repository, ruff's `extend-exclude` covers both fixture homes, `catalog/core/eval_tasks/*/setup` and `catalog/plugins/*/eval_tasks/*/setup` (with `force-exclude`, so an explicitly passed fixture path is skipped too), and `catalog/` is outside mypy's `files`.
#### 6.5.3 The `task.toml` schema
```toml
# catalog/core/eval_tasks/generate-tests-happy-path/task.toml
id = "generate-tests-happy-path"
prompt_id = "generate-tests"            # required; back-reference to the prompt
description = "Generate tests for a simple pure function with no edge cases"
version = 1
[setup]
# Files in the setup/ subdirectory that get copied into the scratch repo
# before invocation. Listed for documentation; the runner walks setup/ itself.
files = ["src/calculator.py"]
# Mock project facts the detector should report for this task.
# Lets framework-conditional prompts be evaluated without depending on
# the eval-runner's own environment.
project_kind = "python-application"
python_version = "3.12"
frameworks = ["pytest", "pytest-asyncio"]
[invocation]
# The arguments / free text the user "types" after the slash command.
prompt_args = "for the add function in src/calculator.py"
# Values for the prompt's declared input_variables.
input_variables = { target = "src/calculator.py::add" }

# --- The DETERMINISTIC layer: a boolean expression over named handles. ---
[gate]
expr = "test_created and names_test and parametrized and src_unchanged"
[gate.bind]
# A handle is a group | a standalone check | a {ref="<gate>"}. File predicates,
# metric thresholds, and non-regression checks all live here. Thresholds are 0-1.
test_created  = { check = "file_exists",    path = "tests/test_calculator.py" }
names_test    = { check = "file_contains",  path = "tests/test_calculator.py", pattern = "def test_add" }
parametrized  = { check = "file_contains",  path = "tests/test_calculator.py", pattern = "parametrize" }
src_unchanged = { check = "file_unchanged", path = "src/calculator.py" }
# A metric threshold/non-regression handle (0-1 normalized cutoffs):
#   cc  = { check = "threshold",      metric = "cyclomatic_complexity", fail = 0.5 }
#   cov = { check = "non_regression", metric = "coverage",              max_worsening = 0.0 }

# --- The LLM-JUDGE layer: a weighted rubric, thresholded to a boolean. ---
[rubric]
expr = "quality"
[rubric.bind]
# A `rubric` group is a weighted set of judge criteria (weights sum to 1.0),
# thresholded into a boolean by `fail` (a 0-1 cutoff on the rubric composite).
quality = { fail = 0.5, rubric = [
  { judge = "Tests use pytest.parametrize for table-driven cases", weight = 0.2 },
  { judge = "Test file lives at tests/test_calculator.py (mirror layout)", weight = 0.2 },
  { judge = "All public branches of `add` are covered", weight = 0.4 },
  { judge = "No mocking is used (the function is pure)", weight = 0.2 },
] }
# A standalone judged non-regression handle is also valid (a judge criterion IS a metric):
#   no_drop = { check = "non_regression", judge = "overall quality", max_worsening = 0.1 }

# --- The trial verdict: a boolean expression over the two layers (default below). ---
[verdict]
trial = "gate and rubric"

# --- OPTIONAL cross-trial reliability layer; omit ⇒ a single trial. ---
# [aggregate]
# expr = "reliable"
# [aggregate.bind]
# reliable = { metric = "pass_at_k", k = 5, over = "verdict", fail = 0.9 }
```
Field-by-field:
| Field | Required | Purpose |
| --- | --- | --- |
| `id` | yes | Unique across all overlays. |
| `prompt_id` | yes | Back-reference to the prompt this task tests. Must appear in that prompt's `eval_tasks:` list. |
| `description` | yes | One-sentence summary, shown in `playbook eval --list`. |
| `version` | no | Bump on breaking changes to setup/checks. |
| `[setup]` | yes | Mock facts and `setup/` directory listing. |
| `[invocation]` | yes | What the user "types" — prompt arguments and variable bindings. |
| `[gate]` | no¹ | Deterministic boolean layer: `bind` (named handles) + `expr` (a boolean expression over them). Handles are file/metric `check`s, composed boolean groups, or a `{ref="<gate>"}`. |
| `[rubric]` | no¹ | LLM-judge weighted layer: same `bind`+`expr` shape; a `rubric` group is a weighted set of judge criteria thresholded to a boolean. |
| `[verdict]` | no | `trial` is a boolean expression over `gate`/`rubric` (default `"gate and rubric"`) deriving the per-trial verdict. |
| `[aggregate]` | no | Cross-trial reliability: same `bind`+`expr` shape over `pass_at_k`/`pass_pow_k`. Omit ⇒ a single trial. |

¹ A task must declare **at least one** of `[gate]` / `[rubric]` (a task with neither does not measure anything). All thresholds are **0–1 normalized** (every metric owns a `Normalizer`, §21); there is **no `[expected]` block** — file predicates are gate `check`s (`file_exists`/`file_contains`/`file_unchanged`/`file_forbidden`). The compiler (`evals/_compile.py`) turns the layer blocks into one per-trial `Rubric` of checks + a derived-verdict AST; the validator only enforces structural correctness (it trial-compiles the blocks).
#### 6.5.4 Authoring discipline
Recommended (not enforced, since this is conventions over rules):
- **Three tasks per prompt minimum.** One happy-path, one edge-case, one regression target. Adding a fourth means the prompt is genuinely complex; if you can't find a fourth, the prompt is probably fine.
- **Task IDs follow `<prompt-id>-<scenario>`.** Predictable, sortable, makes `playbook eval --list` readable.
- **Gate checks are cheap, rubric criteria are precious.** Every `[gate]` file/metric check is deterministic and free to run forever. `[rubric]` judge criteria cost LLM tokens, so reserve them for things that genuinely can't be checked deterministically. *"Tests use parametrize"* → a `[gate]` `file_contains` check. *"Tests cover all public branches"* → a `[rubric]` judge criterion.
- **Don't test the model; test the prompt.** If a task fails because Claude 4.6 is dumber than Claude 4.7, that's not your prompt regressing. Tasks should target things the prompt itself controls: layout, conventions, what gets imported, what doesn't.
#### 6.5.5 `eval_tasks:` validation in `playbook validate`
Two new validation rules ship in v1:
1. **Every `eval_tasks:` reference resolves to a real task.** If a prompt declares `eval_tasks: [foo, bar]` but `eval_tasks/bar/` doesn't exist, error.
2. **Every task's `prompt_id` points back to a prompt that lists it.** Bi-directional check, like `includes_rules`, whose every id must name a rule (§12.6). Catches orphan tasks where someone deleted the prompt but left the task behind, or where a task was renamed and a prompt's frontmatter wasn't updated.
`playbook validate` does **not** run the agent — it only trial-compiles the layer blocks and checks cross-references, so a malformed `[gate]`/`[rubric]` handle or an `expr` referencing an unknown handle is caught at commit time, but whether the gate checks *hold* against real agent output requires `playbook eval --run`.
#### 6.5.6 What runs at validate-time vs run-time
| Capability | `playbook validate` | `playbook eval --run` |
| --- | --- | --- |
| Author `eval_tasks/` directories | yes | yes |
| `task.toml` schema + trial-compile validation | yes | yes |
| `playbook validate` cross-reference checks | yes | — |
| `playbook eval --list` (read-only enumeration) | yes | yes |
| Run the agent + grade the `[gate]` checks against its output | no | yes |
| LLM-as-judge for the `[rubric]` layer | no | yes (opt-in via `--judge`) |
| Per-runner eval (`--runner claude_code` / `opencode`) | no | yes |
Validation stays cheap: it ships as schema + trial-compile + cross-reference checks, with the actual execution behind `--run`. Section 15 carries the matching execution abstractions (`HarnessRunner`, `EvaluationReport`, and the `Metric`/`Check`/`Rubric` scoring model of §21), live since v1.1.
### 6.6 Canonical types and serialization
This section codifies a distinction that has been implicit throughout the spec and makes it explicit: there are **two** formats in this system, and they serve different audiences.
**The authoring format** is markdown + YAML frontmatter (`.md` or `.md.j2`). It is what humans write, what gets reviewed in PRs, what lives in `catalog/`, overlay `resources/` and repo-local `playbook/` directories. It never changes. Authors at every level — engine maintainers, overlay authors, repo-local customizers — write exclusively in this format.
**The canonical internal format** is a set of typed Python dataclasses: `Rule`, `Prompt`, `Skill`, `Hook`, `EvalTask`. These are what the engine operates on internally between parse-time and adapter-time. Adapters consume these objects, not markdown. The renderer produces these objects. The validator type-checks these objects.
The two formats round-trip exactly: `Rule.from_markdown(rule.to_markdown())` is the identity. The dataclasses also serialize to JSON via `to_dict()` / `from_dict()` for alternative storage and transport.
#### 6.6.1 Why this distinction matters
Three reasons to make the canonical types a first-class concern, even though v1's authoring story doesn't need them:
**1. Validation gets precise error locations.** Today's `playbook validate` parses YAML into a dict and conditionally checks fields. With typed dataclasses, validation errors point at the exact field that's wrong — "field `priority` must be int, got 'high'" instead of "something wrong in priority". Pydantic-style messages for free.
**2. Tests get cleaner.** Unit tests for adapters and the renderer can construct `Rule(...)` objects inline instead of writing markdown fixtures to disk and parsing them back. Combined with `InMemoryArtifactSource` (Section 20), the entire engine becomes testable without any filesystem activity.
**3. Alternative deployments get a stable interchange format.** A future hosted product can store rules as JSON in a database or transmit them over HTTP as JSON payloads — operating on the *same* canonical type the OSS engine uses internally. The markdown authoring format is the lossless serialization for humans; the JSON serialization is the lossless serialization for machines. Both produce identical `Rule` objects when parsed.
#### 6.6.2 The canonical types
```python
# coding_agent_playbook/artifacts/rule.py (and prompt.py, skill.py below)
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal


@dataclass
class RuleFrontmatter:
    id: str
    name: str
    description: str
    scope: Literal["always", "scoped"]
    version: int = 1
    globs: list[str] = field(default_factory=list)
    applies_if: dict[str, Any] = field(default_factory=dict)
    priority: int = 50
    tags: list[str] = field(default_factory=list)
    lint_codes: dict[str, Any] = field(default_factory=dict)  # {warn, when}; §6.1.1
    skill: str | None = None  # owning skill; required for scoped, forbidden for always; §6.1.1


@dataclass
class Rule:
    frontmatter: RuleFrontmatter
    body: str  # post-Jinja markdown body
    template_body: str  # pre-Jinja source, if needed for re-render
    is_templated: bool  # True if source was .md.j2
    source_path: Path | None  # filesystem origin; None for non-filesystem sources
    source_package: str  # e.g. "coding_agent_playbook", "playbook_rules_bnp"

    @classmethod
    def from_markdown(cls, path: Path, context: dict, source_package: str) -> "Rule": ...
    def to_markdown(self) -> str: ...
    def to_dict(self) -> dict: ...  # JSON-serializable
    @classmethod
    def from_dict(cls, data: dict) -> "Rule": ...


# coding_agent_playbook/artifacts/prompt.py
@dataclass
class PromptFrontmatter:
    id: str
    name: str
    description: str
    slash: str
    version: int = 1
    applies_if: dict[str, Any] = field(default_factory=dict)
    input_variables: list[dict] = field(default_factory=list)
    includes_rules: list[str] = field(default_factory=list)
    eval_tasks: list[str] = field(default_factory=list)
    output_contract: list[str] = field(default_factory=list)  # regexes; §6.2.1
    write_scope: dict[str, Any] = field(default_factory=dict)  # {read_only: true} | {globs}; §6.2.1


@dataclass
class Prompt:
    frontmatter: PromptFrontmatter
    body: str
    template_body: str
    is_templated: bool
    source_path: Path | None
    source_package: str
    # Same from_markdown / to_markdown / to_dict / from_dict shape as Rule.
    ...


# coding_agent_playbook/artifacts/skill.py
@dataclass
class Skill:
    # Agent Skills directory, see Section 6.3
    frontmatter: dict  # SKILL.md frontmatter (open mapping)
    body: str
    scripts_dir: Path | None  # if the skill bundles scripts
    references_dir: Path | None
    source_package: str
    member_references: tuple[MemberReference, ...] = ()  # active member rules, set at sync
    ...


# coding_agent_playbook/artifacts/member_reference.py (a stdlib-only leaf skill.py imports)
def member_reference_path(rule_id: str) -> str: ...  # "references/<rule_id>.md"


@dataclass(frozen=True)
class MemberReference:  # one member rule, rendered as its skill's references/<rule_id>.md
    rule_id: str
    name: str  # its label in the skill's Covers clause and index
    description: str  # its line in the skill's index
    priority: int  # members are ordered by (priority, rule_id)
    globs: tuple[str, ...]  # shown on the reference's first line
    text: str  # the whole file, identical in every skill root
    source_package: str  # lockfile provenance
    # filename property, plus to_dict / from_dict; a Skill dict without the key still loads


# --- Hook: the fourth emitted kind (Section 6.6.7) ---
# coding_agent_playbook/artifacts/hook_schema.py (HookSchemaError, HookMatcher, HookHandler)
class HookSchemaError(ValueError):
    """Field-precise HOOK.md error: carries where / field (dotted path) / value / expected."""


@dataclass
class HookMatcher:  # per-event filter; present dimensions are ANDed
    tools: list[str] = field(default_factory=list)  # canonical tool classes
    tool_names: list[str] = field(default_factory=list)  # regexes over Claude tool names
    paths: list[str] = field(default_factory=list)  # repo-relative globs
    command: list[str] = field(default_factory=list)  # regexes over shell segments
    sources: list[str] = field(default_factory=list)  # session_start
    triggers: list[str] = field(default_factory=list)  # pre_compact
    agent_types: list[str] = field(default_factory=list)  # subagent_stop


@dataclass
class HookHandler:  # exactly one form: builtin, or external command + script
    builtin: str | None = None  # a registered handler name
    command: Literal["python", "bash", "sh", "node"] | None = None  # the launcher
    script: str | None = None  # under the hook's scripts/
    args: list[str] = field(default_factory=list)  # static argv
    config: dict[str, Any] = field(default_factory=dict)


# coding_agent_playbook/artifacts/hook_frontmatter.py
@dataclass
class HookFrontmatter:
    id: str
    name: str
    description: str
    tier: Literal["default", "opt-in", "overlay"]
    events: list[str]  # canonical event names
    decisions: list[Literal["deny", "ask", "context", "none"]]
    timeout: float  # seconds
    on_error: Literal["ask", "deny", "open"]
    supports: list[str]  # hook-capable adapters: claude_code, opencode
    handler: HookHandler | None = None  # exactly one of handler / handlers
    handlers: dict[str, HookHandler] = field(default_factory=dict)  # per event
    version: int = 1
    enabled: bool = True
    mandatory: bool = False  # overlay-only
    priority: int = 50  # fan-out order within an event
    matcher: dict[str, HookMatcher] = field(default_factory=dict)  # per event
    applies_if: dict[str, Any] = field(default_factory=dict)
    linked_rule: str | None = None
    tags: list[str] = field(default_factory=list)
    summary: str = ""  # one-line guardrail (§6.6.7); "" = the body's first sentence

    @classmethod
    def from_mapping(cls, data: Mapping[str, Any], *, where: str) -> "HookFrontmatter": ...
    def to_mapping(self) -> dict: ...  # empty values (an empty summary too) dropped at every level


# coding_agent_playbook/artifacts/hook.py
@dataclass
class Hook:
    frontmatter: HookFrontmatter
    body: str  # post-Jinja advisory prose
    template_body: str
    is_templated: bool  # source was HOOK.md.j2
    source_path: Path | None  # kept, unlike Skill: validate and script containment need it
    source_package: str
    scripts_dir: Path | None = None

    @classmethod
    def from_markdown(cls, path: Path, source_package: str) -> "Hook": ...
    def to_markdown(self) -> str: ...
    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "Hook": ...
    def to_advisory_rule(self) -> Rule | None: ...  # Section 6.6.7


# EvalTask is already defined in Section 15.2 with the same to_dict / from_dict pattern.
```
The fields capture three things every artifact needs:
- **Frontmatter** as a nested dataclass — typed, validated, the "metadata" half.
- **Body content** — both post-Jinja (the final text) and pre-Jinja (the template, for re-rendering with different contexts).
- **Provenance** — where the artifact came from. `source_package` lets the engine answer "is this from the engine, an overlay, or repo-local?" without filesystem inspection. `source_path` is optional because alternative sources (database, HTTP) have no path.
#### 6.6.3 The round-trip contract
```python
# These two are identity transforms:
rule == Rule.from_markdown(Path("rule.md"), context, "pkg").to_markdown_then_back()
rule == Rule.from_dict(rule.to_dict())
# These two produce equivalent rules from different inputs:
Rule.from_markdown(some_path, context, "pkg")
Rule.from_dict(some_dict)
# Hooks: the dict form is the identity; the markdown form keeps frontmatter and template.
hook == Hook.from_dict(hook.to_dict())
```
Round-trip is **lossless for both directions** for static (`.md`) artifacts. For templated (`.md.j2`) artifacts, the round-trip preserves `template_body` so re-rendering with a new context produces correct output.
A `Hook` round-trips the same way: `Hook.from_dict(hook.to_dict())` is the identity (`to_dict` keeps the full frontmatter, with `source_path` and `scripts_dir` as `str | None`), and `Hook.from_markdown(p, pkg).to_markdown()` re-parses to an equal frontmatter and `template_body`. `to_markdown` drops empty values at every schema level (`handler`, `handlers.*`, `matcher.*`), so `handler: {builtin: x}` does not come back as a block of nulls; byte identity of the authored file is not promised, the same contract rules and prompts have. Scripts are not part of the canonical type: `scripts_dir` points at them and they are byte-copied.
The pre-Jinja `template_body` is kept because some operations need it. The OSS engine's `playbook sync` re-renders templates on every run, so it needs the template, not just the last rendered output. The commercial version's hosted registry might store the template once and render per-customer at fetch time — same pattern.
#### 6.6.4 What does NOT live on the canonical type
Equally important is what's deliberately absent:
- **No harness-specific rendering** lives on the type. `Rule.to_continue_rule()` doesn't exist. That logic lives in the Continue adapter. The `Rule` type is harness-neutral.
- **No source-specific data** beyond `source_package` and the optional `source_path`. A `Rule` from a database row should be indistinguishable in behavior from a `Rule` from a markdown file.
- **No render context** (the Jinja variables). The render context is supplied at parse-time and consumed; the resulting `Rule` carries only the rendered `body` and (for templated rules) the `template_body`. Two different contexts produce two different `Rule` objects.
#### 6.6.5 What v1 ships
The dataclasses themselves: `coding_agent_playbook/artifacts/` (`rule.py`, `prompt.py`, `skill.py`, `hook.py`, with the frontmatter helpers in `frontmatter.py`) with the full type definitions and the `from_markdown` / `to_markdown` / `to_dict` / `from_dict` methods. The existing loader becomes a thin wrapper that calls `Rule.from_markdown` per file. Adapters' signatures explicitly typed as taking `Rule`, `Prompt`, `Skill`, and the resolved form of a `Hook` (`ResolvedHook`, §6.6.7). The renderer produces these typed objects.
v1 does **not** ship:
- Any non-markdown source of canonical types (no `from_database`, no `from_http`).
- Any non-markdown serialization (the JSON `to_dict` is available, but the OSS engine never writes it to disk — that's a commercial-version concern). The one JSON file sync writes for hooks, `guard_config.json`, holds derived `ResolvedHook.to_json()` records, not canonical artifacts (§6.6.7).
- Any schema versioning beyond the `version: int` field already in frontmatter (per-artifact). Schema evolution at the type level is a v2 concern; v1 commits to the type as defined.
This means v1's `playbook sync` flow is *exactly* what it was before introducing this section — markdown in, markdown out, no canonical JSON anywhere (the JSON that hooks add — `guard_config.json` and the managed `.claude/settings.json` entries — holds derived records, §6.6.7). The types are an internal refactor for clarity and testability. The dual-format story matters for the commercial path; it doesn't change anything user-visible in v1.
#### 6.6.6 The contract for alternative deployments
For implementations beyond the OSS engine, the contract is:
1. **The authoring format never changes.** Any product accepting user-authored rules accepts markdown + YAML frontmatter, byte-compatible with the OSS engine. Customers can paste a rule from OSS into the commercial product and have it work.
2. **The canonical type is the interchange format.** Commercial versions may store, transmit, and operate on `Rule` / `Prompt` / `EvalTask` objects in any serialization (JSON, MessagePack, database rows). The dataclass definition is the schema.
3. **Round-trip remains lossless.** A rule that goes markdown → `Rule` → JSON → `Rule` → markdown produces a markdown file byte-identical to the original (modulo whitespace normalization in the frontmatter YAML).
These three guarantees are what make the OSS engine and a future commercial product *compatible*, not *competitors*. A customer using both should never have to convert formats.
#### 6.6.7 Hooks (v0.20)
A **hook** is the fourth emitted canonical kind, after `Rule`, `Prompt` and `Skill` (eval tasks are never emitted). It is authored as a **directory** holding `HOOK.md` (or `HOOK.md.j2`) plus, for an external handler only, a `scripts/` folder. The directory name is the hook id, and category folders above it carry no meaning, so hooks are found at any depth under each layer's `hooks/` — the engine's bundled `catalog/core/hooks/`, a bundled plugin's `catalog/plugins/<name>/hooks/`, an overlay package's `resources/hooks/` — and `playbook/hooks/` (repo-local); a `HOOK.md` beneath another hook directory is a validate error. Engine hooks are builtin-only and ship no `scripts/`. Scripts are never templated, never get a sentinel, and are byte-copied (`shutil.copy2`).
```markdown
---
id: guard-generated-outputs
name: Guard generated outputs
description: Deny hand-edits to files that playbook sync generates and point at the canonical source.
tier: default                        # default | opt-in | overlay (an engine mechanism an overlay activates)
priority: 10                         # fan-out order within an event, never the Stop stage order
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, notebook_edit, shell]
handler:
  builtin: guard_generated_outputs   # or: command: python|bash|sh|node + script: scripts/x.py + args
  config:
    extra_protected: []
decisions: [deny, ask, none]         # the only decisions this hook may emit; never `allow`
timeout: 2                           # seconds; ≤ 30 on tool and prompt events
on_error: ask                        # ask | deny (overlay hooks only) | open
supports: [claude_code, opencode]    # adapters allowed to render native enforcement
---
Files that begin with the AUTOGENERATED sentinel are produced by `playbook sync`; a hand
edit is overwritten by the next sync. Edit the canonical source under `playbook/` instead.
```
**Frontmatter** is static YAML, parsed by `HookFrontmatter.from_mapping` before any Jinja; an unknown key, a missing required key or a wrong type is a `HookSchemaError` naming the dotted field and the value. Required: `id` (`^[a-z0-9][a-z0-9-]{0,62}$`, equal to the directory name), `name`, `description`, `tier`, `events`, `decisions`, `timeout`, `on_error`, `supports`, and exactly one of `handler` (shared by every event) or `handlers` (one per event, e.g. a Stop stage plus a `pre_tool_use` companion). Optional: `version`, `enabled`, `mandatory` (overlay hooks only: cannot be disabled or shadowed, §11.6), `priority`, `matcher` (per event; present dimensions are ANDed), `applies_if` (the §6.4 DSL), `linked_rule` (inherit a rule's `applies_if`, `globs` and `lint_codes`, §6.1.1), `tags` and `summary` (the hook's one-line guardrail, below).

**Events** use one canonical snake_case spelling; the harness names live in the adapters. OpenCode renders four of them (two degraded); a hook must reach at least one declared event on every adapter it `supports`:

| Canonical event | Claude Code event | OpenCode | Allowed decisions | `on_error` allowed | Matcher fields |
| --- | --- | --- | --- | --- | --- |
| `session_start` | `SessionStart` | degraded | `context`, `none` | `open` | `sources` |
| `user_prompt_submit` | `UserPromptSubmit` | — | `deny`, `context`, `none` | `deny`, `open` | — |
| `pre_tool_use` | `PreToolUse` | yes | `deny`, `ask`, `context`, `none` | `ask`, `deny`, `open` | `command`, `paths`, `tool_names`, `tools` |
| `post_tool_use` | `PostToolUse` | yes | `context`, `none` | `open` | `command`, `paths`, `tool_names`, `tools` |
| `post_tool_use_failure` | `PostToolUseFailure` | — | `context`, `none` | `open` | `command`, `paths`, `tool_names`, `tools` |
| `stop` | `Stop` | degraded (evidence-only) | `deny`, `context`, `none` | `open` | — |
| `subagent_stop` | `SubagentStop` | — | `deny`, `context`, `none` | `open` | `agent_types` |
| `pre_compact` | `PreCompact` | — | `none` | `open` | `triggers` |
| `session_end` | `SessionEnd` | — | `none` | `open` | — |

`on_error` is clamped per firing event: on an event whose column allows only `open`, the effective value is `open` whatever is declared. Matcher `tools` name canonical **tool classes**, one vocabulary for authors, harness registrations and the runtime: `shell`, `edit`, `write`, `notebook_edit`, `read`, `search`, `web`, `subagent`, `mcp`.

**Handlers.** A builtin handler is a registered snake_case name (`@register_hook_handler`, or the `coding_agent_playbook.hook_handlers` entry-point group for out-of-tree packages); several hooks may share one with different `config`. An external handler is a launcher (`python`, `bash`, `sh` or `node`, never a shell string), a script contained in the hook's `scripts/`, and static `args`; it comes only from an overlay or repo-local source and runs only behind `[hooks] allow_code_from` plus a user-local trust approval (§7.1.1). A builtin's `config` is validated against the handler's `CONFIG_SCHEMA` and merged across layers (§11.6) and with the consumer's `[hooks.<hook-id>]` table.

**The body degrades to advisory text.** `Hook.to_advisory_rule()` returns `None` for a blank body, else a `Rule` with id `guardrail-<id>` (the prefix is reserved), priority 30, `scoped` on the effective paths or `always`, whose body is the `hook_advisory` projection: the rendered body plus one line saying where the hook is enforced (§9.7). It goes to Continue and `agent_harness` for every on hook, and is that hook's section of the `playbook-guardrails` skill (§6.3.4). Always-loaded context gets one **guardrail line** per such hook instead (v0.21, D6): `- `<id>`: <text>` in `AGENTS.md`'s Guardrails section (§10.4), and in the Claude Code rules file `.claude/rules/coding-agent-playbook.md` only when Claude Code does not run the hook (§10.3.1). The text is the frontmatter's `summary` (one line of 1-120 characters, `hook_policy.GUARDRAIL_SUMMARY_MAX_CHARS`, without `{{` or `{%`, since frontmatter is never rendered; a wrong shape is a `HookSchemaError` from `HookFrontmatter.from_mapping`, and an empty one is dropped by `to_mapping`), else the rendered body's first sentence (headings skipped, list and quote markers dropped), cut at the last word boundary with `…` appended once it passes 120 characters (`ResolvedHook.guardrail_text`, `hook_policy.guardrail_summary`). Every core hook with a body declares `summary` (`tests/hook_runtime/handlers/test_hook_summaries.py`); an overlay or repo-local hook keeps working without one. `[hooks] advisory = false` turns the degrade off.

**The effective view.** `hook_policy.resolve_effective_hooks` (§4.2 step 4) turns the merged hooks into `ResolvedHook`s — frozen, with the merged handler config, the clamped `on_error` per event, the inherited matcher paths, the `supports` narrowed to the adapters that receive hooks, and the copied script's `script_sha256` — and `SkippedHook(id, reason)` records. `ResolvedHook.to_json()` is the single hook-record schema of `guard_config.json`, the file the dispatcher reads instead of the canonical sources.

**The sidecar.** The opt-in `agent_harness` adapter has no lifecycle-event concept, so it is advisory-only, but it keeps the `playbook/hooks/` → harness → `import-harness` round trip lossless: it writes `.playbook/hooks/<id>/HOOK.md` (canonical frontmatter, the sentinel as first body line, the un-rendered body) with any scripts byte-copied, and records it in `.playbook/manifest.toml` as kind `"hook"` (§20.10).
## 7. Configuration files
### 7.1 `.coding-agent-playbook.toml` (committed)
The project's playbook config. Committed to git, reviewed in PRs.
```toml
# .coding-agent-playbook.toml
schema_version = 1
# Top-level keys: TOML puts any key written after a [table] header inside that table.
# Ordered list of overlay packages to merge in.
# Earlier overlays are overridden by later ones on ID collision.
overlays_enabled = ["playbook_rules_bnp"]
# Which adapters render output. AGENTS.md is always generated.
# The playbook init default; add "continue" to opt in. shared_skills writes the shared
# skill root .agents/skills/ (Section 10.8); drop it to opt out.
adapters_enabled = ["claude_code", "opencode", "shared_skills"]
[project]
name = "risk-models"
kind = "python-application"          # or "python-library", "ml-research", "notebook"
description = "Counterparty risk scoring service"
[engine]
version = "0.4.0"                    # engine version this config was generated against
[storage]
# Where artifacts and state come from / go to. See Section 20.
# v1 ships only "filesystem"; future deployments can add others.
artifact_source = "filesystem"
state_source = "filesystem"
[links]
# External-link allowlist for the self-contained-markdown-links rule
# (Section 12.6). Default: [] — no external links in artifacts at all.
# Subdomains of an entry are allowed too.
allowed_domains = ["agentharnesses.io"]
[output]
# Is generated output committed? Default false: everything `playbook sync`
# renders is local-only — gitignored via a managed .gitignore block and
# refused at commit time by `playbook sync --check-staged`. true = legacy:
# output is committed and `playbook sync --check` fails a commit on drift.
commit = false
[detector_cache]
# Cached detector output. Refreshed on pyproject.toml change or `playbook check --refresh`.
python_version = "3.12"
package_manager = "uv"
has_notebooks = false
has_dockerfile = true
[detector_cache.frameworks]
fastapi = "0.115.0"
pydantic = "2.9.2"
sqlalchemy = "2.0.35"
pytest = "8.3.3"
[user_choices]
# Answered during `playbook init`.
docstring_style = "numpy"            # numpy | google | none
test_layout = "tests-mirror"         # tests-mirror | tests-flat | inline
```
**`overlays_enabled` / `adapters_enabled`** are top-level keys holding lists of non-empty strings; they are the only place `Config` reads the enabled overlays and adapters (`playbook init` writes them there). Being top-level, they must sit **above the first `[table]` header**: TOML puts every key written after a header inside that table. Each of the following shapes used to be ignored without a word — read as an empty list, so `playbook sync` exited 0, rendered with only `agents_md`, and settled every other adapter's earlier output as leftovers (§4.2 step 9) — and is now refused with a `config.schema.ConfigError` (a `ValueError`) rather than loaded:
- an `[overlays]` or `[adapters]` table — including the dotted `overlays.enabled = [...]` key, which TOML parses as that table — or any other top-level `overlays`/`adapters` key. The message names the file, quotes the value, and shows the line to write and where, e.g. `.coding-agent-playbook.toml: the [overlays] table is not read (found {'enabled': ['playbook_rules_bnp']}); use the top-level key instead, at the top of the file, above the first [table] header: overlays_enabled = ["playbook_rules_bnp"]`;
- an `overlays_enabled`/`adapters_enabled` key inside any table, at any depth — what replacing an `[overlays]` table with the key *in place* produces (it nests under the table above), as does appending the key to a file that ends with a table (the file `playbook init` writes ends with `[detector_cache.frameworks]`; the local file it writes is `[user_choices]` only). Likewise a nested `overlays`/`adapters` table that holds an `enabled` key (`[engine]` followed by `overlays.enabled = …`). E.g. `.coding-agent-playbook.toml: 'overlays_enabled' in the [detector_cache.frameworks] table is not read (found ['…']) (TOML puts every key written after a [table] header in that table); use the top-level key instead, at the top of the file, above the first [table] header: overlays_enabled = ["…"]`;
- a close misspelling of either key, at any level (`overlay_enabled`, `adapters-enabled`, `enabled_adapters`, compared case-insensitively with `difflib`): `the top-level key 'overlay_enabled' is not read (found […]) (did you mean overlays_enabled?); use the top-level key instead, …`. A plain `overlays`/`adapters` entry inside a table (a framework called `adapters` in `[detector_cache.frameworks]`) is not a mistake and still loads;
- an `overlays_enabled`/`adapters_enabled` value that is not a list of strings (a lone string used to become a list of characters): `overlays_enabled must be a list of strings, got '…'; write overlays_enabled = ["…"]` — or that lists an empty name (`""` used to crash every command inside `importlib`): `overlays_enabled lists an empty name, got ['']; remove the empty entry`.

`config.schema.check_enabled_keys` is the one check: `ConfigFiles.load` (`config/files.py`) runs it on `.coding-agent-playbook.toml` and on `.coding-agent-playbook.local.toml` separately, before the §7.2 merge, so the error names the file that holds the mistake, and `Config.from_dict` runs it again for other callers. It walks every table of the file (iteratively, so a header nested a thousand levels deep still loads), and every problem in a file is listed in one error. Other unknown keys are still ignored.

Since v0.18 the same per-file pass (`config.model.check_config_file`, its checks in `config/schema.py` with `ConfigError`) also refuses, in each file on its own: a file `tomllib` cannot read — a syntax error (`error: .coding-agent-playbook.local.toml: invalid TOML: Expected ']' at the end of a table declaration (at line 1, column 14)`), a byte that is not UTF-8, inline arrays/tables nested past Python's recursion limit — each of which was a traceback (exit 1); a top-level `project`, `engine`, `storage`, `output`, `detector_cache` or `user_choices` that is not a table (`error: .coding-agent-playbook.local.toml: [project] must be a table, got 'x'; write name = "<project name>" under the [project] header`), which was a `TypeError`/`AttributeError`/`ValueError` traceback; and a malformed `[output]`. Because each file is checked alone, the error names the file at fault in every command — a local `project = "x"` used to be reported against the committed file by `load_config` — and a committed non-table is refused even when the local file's table replaces it in the merge (the `[user_choices]` local file `init` writes always did), since every teammate without that local file would load it. A missing required key — `schema_version`, `[project] name`/`kind`, `[engine] version` — is a `ConfigError` too (it was a `KeyError` traceback), naming the file, the key and the line to write: `error: .coding-agent-playbook.toml: the required key engine.version is missing; write version = "<engine version>" under the [engine] header`. It is checked on the merged config, so the local file may supply one for `sync` and plain `check`, and it names the committed file, where the key belongs. Every command that loads the config (`sync` in all modes, `check` incl. `--refresh`, `validate`, `render`, `eval`, `init`) loads it first, so a `ConfigError` stops it before it writes or deletes anything: the CLI prints `error: <message>` on stderr and exits 2, like a missing config. `init` checks each existing file on its own, then the config its final sync will load (the planned committed file with the local file merged on top), on a first run too (§12.1). The policy readers — `playbook metrics` (`[metrics]`), `gate-scan`, `scan-secrets` and the `playbook ci` rows — read only their own table, through `ConfigFiles.committed_table` (the twins decode the committed file of their base revision with `CommittedDocument.decode`): a file `tomllib` cannot read is the same `ConfigError` (`error: .coding-agent-playbook.toml: invalid TOML: …`, or `.coding-agent-playbook.toml at <rev>: …` for a base revision), and a table on the path that is not one is named (`[hooks.gate-weakening-guard] must be a table, got …`), but none of the other per-file checks runs, so a broken `[output]` never stops `playbook metrics`. Sync's read of `[metrics.ruff_violations]` for the quality companion keeps the defaults on a bad table instead, as before. `import-harness`/`validate-harness` never read the config. An overlay that is listed correctly but cannot be used (an overlay package whose import fails or that has no `resources/` directory, or a bundled-plugin name with no `catalog/plugins/<leaf>/`, or a bare plugin namespace) is a separate, environment-dependent check (§4.2 step 1, §12.4, §12.6). A deprecated `coding_agent_playbook.packs.<leaf>` entry is not an error: it is canonicalized with a warning (§11.5).

**`[output] commit`** (`config.model.OutputConfig`, parsed by `config.model.parse_output_config`) selects the output policy. An absent table means `false`; `playbook init` always writes the table explicitly so the policy is discoverable; it and `playbook check --refresh` keep the value already in the committed file (a `.local.toml` `[output]` is never written back, §7.2). The value must be a TOML boolean — `commit = "false"` is rejected with a `ConfigError` naming the file and carrying the offending value rather than coerced (`error: .coding-agent-playbook.toml: [output] commit must be a boolean (true or false), got 'false'`, exit 2). What each value implies:

| | `commit = false` (default) | `commit = true` (legacy) |
| --- | --- | --- |
| Generated files + lockfile | gitignored (managed block, §5.3) | committed |
| Write-mode `playbook sync` | applies the managed block; warns about still-tracked output (§12.2) | removes the managed block |
| `playbook sync --check` | file drift **and** a stale/missing block — only meaningful in a working copy that has run `playbook sync` (a fresh clone, e.g. CI, has no output: every file is "missing") | file drift only; suitable for CI |
| `playbook sync --check-staged` | fails when generated output is staged (§12.3.1) | no-op (exit 0) |
| Hooks (§13) | `post-checkout`/`post-merge` auto-sync + staged-output guard | `playbook sync --check` drift check |

The managed block lists what *this* checkout renders (plus still-owned leftovers, §4.2 step 9). A `.local.toml` that narrows `adapters_enabled` (§7.2) therefore narrows the block too — the dropped adapter's pristine output is deleted — and that `.gitignore` change is personal and should not be committed.
#### 7.1.1 Hooks and tool policy: `[hooks]`, `[guardrails]`, `[metrics]` (v0.20)
Three tables are team policy: they are read from the committed file only (§7.2), and their parsers raise one `ValueError` that names every offending value and its expected shape, which `playbook validate` reports (rule H21 for the first two). `[hooks]` is **mechanism** — which lifecycle hooks render, and how — parsed by `hooks_config.parse_hooks_config` into `HooksConfig`. `[guardrails]` is **policy data** read by the hooks *and* by their off-workstation twins (pre-commit hooks, `playbook ci` steps), so it applies even with hooks off; it is parsed by `hooks_config.parse_guardrails_config` into `GuardrailsConfig`. Both parsers are re-exported from `config`. `[metrics]` is the code-quality gate's table (§21.5), parsed by `metrics_gate.config.parse_metrics_config` into `MetricConfig`, and is shared by `playbook metrics`, its pre-commit hook, the `playbook ci` step and the quality Stop stages.
```toml
[hooks]
enabled = true                        # the opt-in: an absent table or key means off
tiers = ["default"]                   # add "opt-in" to turn every opt-in hook on
enable = ["coverage-diff-gate"]       # single hooks, whatever their tier
disable = ["typing-lint-feedback"]     # wins over enable; never a mandatory hook
allow_code_from = ["<repo-local>"]    # whose external handlers may run (plus a trust approval)
wrapper_prefixes = ["proxy"]          # extra command prefixes stripped before shell matching

[hooks.stop-ci-parity-gate]           # [hooks.<hook-id>]: the consumer layer of that hook's config
max_blocks = 2

[hooks.commit_convention]             # the one reserved sub-table that is not a hook id
cutover_date = "2026-10-15"           # a TOML string, never a date literal

[guardrails.git]
protected_branches = ["develop"]      # extends main, master, release/*

[metrics]
extend_select = ["ruff_violations", "file_sloc"]   # opt-in metrics are selected by name
exclude = ["**/eval_tasks/*/setup/**", "legacy/**"]

[metrics.ruff_violations]
config = { "lint.mccabe.max-complexity" = 10 }
```
**`[hooks]`** (`HooksConfig`). Unknown keys and wrong types are errors.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `enabled` | bool | `false`, whether the table or only the key is absent | The opt-in. `false` renders no registration, no shim, no `guard_config.json` and no advisory text, and strips the entries an earlier sync managed. `playbook init` writes `true` unless given `--no-hooks`. |
| `adapters` | list | `adapters_enabled` ∩ {`claude_code`, `opencode`} | Adapters that receive native registrations. |
| `tiers` | list ⊆ {`default`, `opt-in`} | `["default"]` | Tiers that are on. An `overlay`-tier hook is an engine mechanism, turned on only when an overlay promotes it to `tier: default` (§11.6), never from here. |
| `enable` | list of hook ids | `[]` | Hooks turned on whatever their tier. |
| `disable` | list of hook ids | `[]` | Hooks turned off; wins over `enable`; may not name a `mandatory` hook. |
| `advisory` | bool | `true` | Render the on hooks' bodies as advisory text (§6.6.7). |
| `unattended_ask` | `"deny"` \| `"warn"` | `"deny"` | What an `ask` becomes when no human can answer (headless runs, CI, evals, OpenCode). `"warn"` adds context and lets the call proceed. |
| `allow_code_from` | list | `[]` | Source packages whose external or entry-point handlers may run: names from `overlays_enabled` and/or `"<repo-local>"` (the engine is implicit). An external handler also needs a **trust-on-first-use approval**: an interactive `playbook sync` (stdin and stdout are TTYs; there is no non-interactive approve flag) lists each pending command and script hash and asks `[y/N]`, and the answer is stored per user outside the repo, shared by every worktree of the clone. Any change to the launcher, args or script bytes asks again. Enabling an execution stage that runs repo code (`pytest`, `mypy`, coverage) is approved the same way. |
| `auto_sync` | bool | `false` | Let validate-then-sync-on-canonical-edit run `playbook sync` itself. |
| `wrapper_prefixes` | list | `[]` | Command prefixes the dispatcher strips before shell matching, beyond the built-in `env`, `sudo`, `timeout`, `nice` and `nohup`: a launcher of your own, such as `proxy` or `proxy run`. A stripped prefix is invisible to every guard, so an entry with any token naming a guarded command (a program a guard inspects, such as `git`, `rm`, `curl` or `pip`; a built-in launcher; a runner such as `uv`; a shell or interpreter) is a validate error (H21). A launcher only you use is declared in your own shell instead: `PLAYBOOK_HOOK_WRAPPER_PREFIXES=proxy,proxy run` (see the escape hatches below). |
| `state_ttl_days` | int > 0 | `7` | Age after which per-session hook state is swept. |
| `render_remediation_allow` | bool | `false` | Render a fixed list of remediation commands into `.claude/settings.json` `permissions.allow`. Off by default, because an allow list is a privilege grant. |
| `[hooks.<hook-id>]` | table | — | The **consumer layer** of that hook's handler `config`, merged last with the §11.6 key policies and validated against the handler's `CONFIG_SCHEMA`. Its keys are the hook's own `config` keys, e.g. `[hooks.stop-ci-parity-gate] stages` (⊆ `typecheck`, `tests`), `max_blocks` (1–8) and `budget_s`. |
| `[hooks.commit_convention]` | table | — | The one reserved sub-table that is not a hook id: `cutover_date`, a `"YYYY-MM-DD"` TOML string (a date literal is an error). Range checks (the `playbook ci` step and the push scan, which `[hooks.commit-message-convention] check_push = true` opts into) skip commits whose **committer** date is earlier; unset, every commit is checked. The convention itself is commitizen's, in the consumer's `pyproject.toml` `[tool.commitizen]` (default `cz_conventional_commits`). |

Per-event deadlines are derived from the hooks' `timeout`s, never configured. A hook is on when (`resolve_effective_hooks`, evaluated at sync on the winning definition `w` of §11.6):
```
on(w) = cfg.enabled and w.enabled
        and applicable(w)    # applies_if ∧ linked rule applies ∧ (w.supports ∩ cfg.adapters ≠ ∅)
        and (w.mandatory or (w.id not in cfg.disable and (w.id in cfg.enable or w.tier in cfg.tiers)))
```
**`[guardrails]`** (`GuardrailsConfig`): one table per policy domain. A builtin handler declares its domain, and the keys the consumer sets merge into its config after the layer merge, with the key policy shown (§11.6; a consumer's `relax` key is ignored for a `mandatory` hook).

| Key | Type | Merge | Meaning |
| --- | --- | --- | --- |
| `secrets.extra_globs` | list | `extend` | Added to the built-in secret path globs (`security.patterns`). |
| `secrets.allow_paths` | list | `relax` | Exempt paths, such as test fixtures. |
| `git.protected_branches` | list | `extend` | Branches no agent may force-push to; default `["main", "master", "release/*"]`. |
| `network.mode` | `"off"` \| `"ask"` \| `"enforce"` | `strictest` | network-egress-guard (an overlay-tier mechanism); default `"off"`. |
| `network.allowed_hosts` | list | `relax` | Allowed host suffixes; loopback is always allowed. |
| `dependencies.mode` | string | `strictest` | dependency-allowlist-guard's mode. |
| `dependencies.allowlist` | list | `relax` | Allowed new direct dependencies. |
| `audit.retain_days` | int > 0 | `replace` | local-audit-log retention. |
| `stop_sweep.mode` | `"block"` \| `"warn"` \| `"off"` | `strictest` | stop-diff-sweep; default `"block"`. |

**`[metrics]`** (`MetricConfig`; the gate itself is §21.5). New in v0.20: the selection keys, `exclude`, both timeouts and the `[metrics.ruff_violations]` sub-table.

| Key | Type | Default | Meaning |
| --- | --- | --- | --- |
| `mode` | `"regression"` \| `"absolute"` \| `"both"` | `"regression"` | The comparison strategy. |
| `fail_on_breach` | bool | `true` | A breach exits 1. |
| `strict` | bool | `false` | Warnings fail the gate too. |
| `run_tests` | bool | `false` | Add the execution metrics. `--no-run-tests` overrides it, and both metrics pre-commit hooks pass that flag. |
| `test_cmd` | list | detected | The suite command for the execution metrics. |
| `git_timeout_s` | number > 0 | `10` | Bound on every git call a `git:` baseline makes. |
| `test_timeout_s` | number > 0 | unbounded | Bound on one suite run. |
| `select` | list | the default set | Metric or family names (`quality`, `docstrings`, `testing`) replacing the default selection. A family expands to its non-opt-in members. |
| `extend_select` | list | `[]` | Added to the selection. The opt-in metrics `ruff_violations`, `file_sloc` and `docstring_example` are selected only by name, so an upgrade leaves existing results byte-stable. |
| `ignore` | list | `[]` | Removed from the selection. |
| `exclude` | list of globs | `["**/eval_tasks/*/setup/**"]` | Never measured; a list replaces the default. |
| `[metrics.thresholds.<metric>]` | `warn`, `fail` | per metric | Absolute 0–1 cutoffs. |
| `[metrics.regression.<metric>]` | `max_worsening` | per metric | Non-regression tolerance. |
| `[metrics.weights]` | table | per metric | Composite weights. |
| `[metrics.ruff_violations] families` | table of code lists | `quality` = C901, PLR0911, PLR0912, PLR0913, PLR0915; `docstrings` = D100–D107 | Replaces the named families only (`[]` drops one). |
| `[metrics.ruff_violations] config` | table | `{}` | Per-invocation ruff `--config` overrides, shared by the post-edit feedback and the Stop gate. |
| `[metrics.ruff_violations] preview` | bool | `false` | ruff `--preview` on this call only. |

Unknown `[metrics]` keys are ignored; a selection name the gate does not know is a usage error (exit 2).
### 7.2 `.coding-agent-playbook.local.toml` (gitignored)
Personal, per-engineer overrides. Merged on top of the committed config but never checked in. `playbook init` appends it to `.gitignore`.
```toml
# .coding-agent-playbook.local.toml — DO NOT COMMIT
# I only use Claude Code, skip Continue rendering for my checkout
adapters_enabled = ["claude_code"]   # replaces the committed list (top-level key, above the first [table])
[user_choices]
docstring_style = "google"           # overrides project default for me
```
Merge semantics: deep merge, with `.local.toml` winning — tables merge key by key, while lists and scalars are **replaced**, not merged: a local `adapters_enabled` is the whole adapter list for this checkout. The local file is checked on its own before the merge (§7.1), so an `[adapters]` table there fails with `error: .coding-agent-playbook.local.toml: the [adapters] table is not read …` (exit 2) instead of being ignored. `playbook init` writes the local file as a lone `[user_choices]` header, so add `adapters_enabled` **above** that header: appended below it, the key lands in `[user_choices]` and fails the same way (`'adapters_enabled' in the [user_choices] table is not read …`). The committed config always remains the team's source of truth; local just lets individuals deviate without polluting the repo.
**Policy tables are never local (v0.20).** `[hooks]` (with every `[hooks.<hook-id>]` and `[hooks.commit_convention]`), `[guardrails]` and `[metrics]` in `.coding-agent-playbook.local.toml` are **ignored**: the rendered hook outputs, the CI twins and the metrics gate must not depend on a gitignored file CI never sees, and a deep-merged local file would be an unreviewed off switch. `playbook sync` warns and `playbook validate` fails on a `[hooks]` or `[guardrails]` key there (H21). This narrows the deep merge above for these tables only; a developer deviates at runtime instead, through the hook-process environment (`PLAYBOOK_HOOKS=off`, `PLAYBOOK_HOOKS_DISABLE=<ids>`). `playbook init` and `playbook check --refresh` rewrite the committed file from itself alone, so a local override is never written back into it (the invariant below).

**Invariant: local overrides are read, never written back** (v0.18). The merged config `ConfigFiles.load()` returns (`FileSystemStateSource.load_config()` delegates to it) is what every command runs with, and is never saved. `.coding-agent-playbook.toml` has one writer, `ConfigFiles.write_committed` (the `StateSource` method `save_config` and `FileSystemStateSource.save_config_table` wrap it, and no command calls either), called only by `config/committed.ConfigRewrite.save` — from `playbook init` (§12.1) and `playbook check --refresh` (§12.5). A `ConfigRewrite` is built only in that module, by a `plan_*` function that starts from the committed file alone (`plan_committed_update`, `plan_detector_cache_refresh`) or refuses when one exists (`plan_first_config`, a first `init`'s answers), with the local file never merged in. `tests/config/test_committed.py` walks the engine's AST and fails when another module references a writer, builds a `ConfigRewrite`, or — importing `config.committed` — references the merged config (`load_config`, `preview_config`, `load` or `preview`); it cannot see a merged config handed to a plan another way (an `update` callback returning `SyncContext.config`), which the `init` and `check --refresh` CLI tests pin by their output. So a local `adapters_enabled`, `overlays_enabled`, `[user_choices]`, `[output]`, `[engine]` or table of any name never reaches the committed file, and a committed file that lacks a required key only the local file supplies is refused by `init` and `check --refresh` (exit 2, nothing written), not completed with it — the commands that only read the merged config (`sync`, plain `check`, …) still run. Nothing rewrites an existing local file: `init` creates it only when it is missing.
### 7.3 `pyproject.toml` entry for the consumer
`playbook init` adds the engine and any chosen overlays as dev dependencies:
```toml
[dependency-groups]
dev = [
    "coding-agent-playbook>=0.4.0,<0.5.0",
    "playbook-rules-bnp>=0.2.0,<0.3.0",
]
```
The engine is pinned to a minor range; the consumer bumps it deliberately. Overlay versions move independently.
## 8. Detector subsystem
### 8.1 Responsibility
Inspect the consumer repo and produce a `facts` dictionary used as the rendering context. Run at init, cached in `.coding-agent-playbook.toml`, refreshed on `pyproject.toml` change or explicit `playbook check --refresh`.
### 8.2 Facts inventory (v1)
| Fact | Type | Source |
| --- | --- | --- |
| `python_version` | `str` (e.g. `"3.12"`) | `pyproject.toml [project] requires-python`, then `python --version` |
| `package_manager` | `Literal["uv", "poetry", "pip-tools", "pip"]` | presence of `uv.lock`, `poetry.lock`, `requirements.txt`, `[tool.poetry]`; usable in `applies_if` (§6.4) |
| `dependencies` | `dict[str, str]` (name → version) | `pyproject.toml` + resolved from lockfile |
| `dev_dependencies` | `dict[str, str]` | same, dev group |
| `frameworks` | `dict[str, str]` | subset of dependencies matching a known list (fastapi, pydantic, sqlalchemy, pytest, etc.) |
| `ml_stack` | `dict[str, str]` | subset matching ML deps (torch, transformers, scikit-learn, etc.) |
| `has_notebooks` | `bool` | any `**/*.ipynb` under repo |
| `has_dockerfile` | `bool` | `Dockerfile` exists at root or `./docker/` |
| `has_ci` | `bool` | `.github/workflows/`, `Jenkinsfile`, `.gitlab-ci.yml`, etc. |
| `dev_tools` | `set[str]` | `ruff`, `black`, `flake8`, `mypy`, `pyright` from dev deps + config presence |
| `project_kind` | `Literal[...]` | inferred from layout: presence of `src/`, notebooks, etc. (see 8.3) |
### 8.3 Project-kind inference rule
```
if has_notebooks and not has_src_layout:
    kind = "notebook"
elif has_notebooks and has_src_layout:
    kind = "ml-research"
elif has_src_layout and "fastapi" in frameworks:
    kind = "python-application"
elif has_src_layout:
    kind = "python-library"
else:
    kind = "python-unknown"
```
Tie-breakers can be overridden by the user via `[project] kind` in the config file. The detector never overrides explicit user choice.
### 8.4 Example: detector output
For Max's `risk-models` repo with FastAPI + Pydantic + pytest, the detector returns:
```python
{
    "python_version": "3.12",
    "package_manager": "uv",
    "project_kind": "python-application",
    "dependencies": {
        "fastapi": "0.115.0",
        "pydantic": "2.9.2",
        "sqlalchemy": "2.0.35",
        "httpx": "0.27.2",
    },
    "dev_dependencies": {
        "pytest": "8.3.3",
        "pytest-asyncio": "0.24.0",
        "ruff": "0.8.0",
        "mypy": "1.13.0",
    },
    "frameworks": {
        "fastapi": "0.115.0",
        "pydantic": "2.9.2",
        "sqlalchemy": "2.0.35",
        "pytest": "8.3.3",
    },
    "ml_stack": {},
    "has_notebooks": False,
    "has_dockerfile": True,
    "has_ci": True,
    "dev_tools": {"ruff", "mypy"},
}
```
### 8.5 API
```python
# coding_agent_playbook/detector/facts.py
from pathlib import Path
from typing import TypedDict


class Facts(TypedDict, total=False):
    python_version: str
    package_manager: str
    project_kind: str
    dependencies: dict[str, str]
    dev_dependencies: dict[str, str]
    frameworks: dict[str, str]
    ml_stack: dict[str, str]
    has_notebooks: bool
    has_dockerfile: bool
    has_ci: bool
    dev_tools: set[str]


def detect(repo_root: Path) -> Facts: ...


# coding_agent_playbook/detector/predicate.py
def evaluate_predicate(predicate: dict, facts: Facts) -> bool: ...
```
## 9. Renderer subsystem
### 9.1 Responsibility
Render canonical templates with the merged context (facts + user_choices + project metadata). Two paths depending on file extension (see Section 6.0): `.md.j2` files go through Jinja2; `.md` files are returned verbatim.
### 9.2 Extension dispatch
```python
# coding_agent_playbook/renderer.py
def render_artifact_body(template_path: Path, context: dict) -> str:
    if template_path.suffix == ".j2":
        return jinja_env.get_template(str(template_path)).render(**context)
    return template_path.read_text(encoding="utf-8")
```
Frontmatter parsing is done by the engine before this call and is always treated as static YAML (no Jinja). Only the body is passed through this dispatch.
### 9.3 Jinja environment
```python
from jinja2 import FileSystemLoader, StrictUndefined
from jinja2.sandbox import SandboxedEnvironment

env = SandboxedEnvironment(
    loader=FileSystemLoader([...]),  # engine content + overlay resources
    autoescape=False,  # markdown, not HTML
    keep_trailing_newline=True,
    trim_blocks=True,
    lstrip_blocks=True,
    undefined=StrictUndefined,  # fail loudly on undefined vars
)
```
`StrictUndefined` is important: a typo'd `{{ python_versoin }}` should raise, not silently render as empty. Renders are cheap; failure modes should be loud.

The environment is sandboxed because templates are author-controlled *and* agent-writable (`playbook/**/*.md.j2`, overlay `resources/`), and rendering runs inside `playbook sync`, `render`, `init` and the eval runner. Under a plain `Environment`, `{{ lipsum.__globals__["os"] }}` reaches the `os` module; under `SandboxedEnvironment` every such attribute escape raises `SecurityError`. `playbook sync` (every mode) and `playbook render` report it as `error: <file>: template rejected by the Jinja sandbox: <reason>`, naming the source file relative to the repo, and exit 1. `sync` writes nothing: every template — rule and prompt bodies, and each rule a prompt lists in `includes_rules` (pre-rendered, since the Continue and `agent_harness` adapters repeat that render for their appendix inside `write_prompt`) — runs before the first adapter write. It is the mutable sandbox, not `ImmutableSandboxedEnvironment`: blocking the escape does not require rejecting in-template list/dict mutation, which authored templates may use. Every engine construction site is sandboxed, including `playbook validate`'s parse-only syntax check. The sandbox does not bound CPU beyond Jinja's `MAX_RANGE`. Every shipped `.md.j2` renders byte-identically under it. The runtime floor is `jinja2>=3.1.6`: older releases have published sandbox escapes for anyone who controls a template (CVE-2024-56326, an indirect `str.format` call, fixed in 3.1.5; CVE-2025-27516, the `|attr` filter returning the raw `format` method, fixed in 3.1.6), and `tests/unit/test_renderer.py` pins the floor.
### 9.4 Rendering context
The context passed to every template render:
```python
context = {
    # From detector
    **facts,
    # From config [project]
    "project_name": ...,
    "project_description": ...,
    # From config [user_choices]
    **user_choices,
    # Engine metadata
    "engine_version": "0.4.0",
    "rendered_at": "2026-05-20T10:30:00Z",
    # Convenience predicates
    "has_framework": lambda name: name in facts["frameworks"],
    "has_ml_dep": lambda name: name in facts["ml_stack"],
}
```
Rules, prompts and hook bodies all render in this one environment shape (`build_environment(template_search_paths)`).
### 9.5 The removed `rule()` helper
Removed in v0.21 (D15). A prompt declares the rules it needs in `includes_rules` (§6.2.5), and the adapters turn that list into a `## Before you start` block or a `## Reference rules` appendix; no template places rule text itself. `{{ rule(...) }}` therefore raises `UndefinedError` in every template, and `playbook validate` names any such call in a prompt, rule or hook body (§12.6).
### 9.6 Example: render call
```python
rendered = renderer.render_artifact(
    template_path="rules/languages/python/typing.md.j2",
    context=context,
)
# rendered is now the full markdown including frontmatter, with all {{ vars }} substituted
rendered_plain = renderer.render_artifact(
    template_path="rules/frameworks/fastapi.md",
    context=context,
)
# .md files: frontmatter parsed, body returned verbatim. Context is unused for body.
```
### 9.7 Format-specific post-processing
The renderer exposes per-format transforms applied after Jinja substitution:
| Format | Transform |
| --- | --- |
| `continue_rule` | Emit the sentinel on line 1, then a new frontmatter: `name`, `description`, `alwaysApply` (`true` for `scope: always`, whose `globs` are dropped; `false` for `scoped`, plus `globs` when non-empty). Canonical-only keys (`id`, `version`, `scope`, `skill`, `priority`, `applies_if`, `tags`) are dropped. Then the body. |
| `claude_md_section` | Drop frontmatter; emit a `## {name}` heading, then `` *Applies to: `g1`, `g2`* `` (each glob in backticks, comma-separated) when the rule is `scope: scoped` with non-empty `globs` (advisory only — nothing gates on it), then the body verbatim (its own headings are not demoted) and a `---` separator. Emitted into the Claude Code rules file `.claude/rules/coding-agent-playbook.md` (§10.3.1); the name predates the rules' move out of `.claude/CLAUDE.md` and stays, since `--format claude_md_section` is CLI surface. The composite adapters render it only for rules that name no skill (§10.3.1, §10.4); a member rule is a skill reference instead. |
| `agents_md_section` | Same as `claude_md_section`. |
| `skill_reference` | A member rule's reference, `<skill root>/<skill>/references/<rule-id>.md` (§6.1.6): one italic line, ``*Rule `<id>`; applies to `g1`, `g2`.*`` (``*Rule `<id>`.*`` without globs; advisory only), a blank line, then the body after Jinja, unchanged. No frontmatter and no sentinel: the file is owned through its `kind = "rule"` lockfile entry (§14.4). Rendered by `skills.document.render_member_reference` when skills are composed, not by `render_for`, so it is no `--format` value of `playbook render`. |
| `prompt_continue` | Emit the sentinel on line 1, then a new frontmatter `name`, `description`, `invokable: true`, then the body. When `includes_rules:` is set, append the `## Reference rules` appendix built through `rule_registry`: each included rule once, in order, under `### {rule.name}`; a rule filtered out by `applies_if` is skipped (§6.2.5). |
| `prompt_claude_command` | Strip frontmatter; prepend a title line if not present. Insert the `## Before you start` block built through `skill_references` before the body's first `##` heading outside a code fence (§6.2.5); no rule text. A prompt with no active skill reference gets no block and renders byte-identically. A read-only prompt (`write_scope: {read_only: true}`, §6.2.1) instead opens with the frontmatter block `---` / `disallowed-tools: Edit Write NotebookEdit` / `---`, so Claude Code removes those tools while the command runs, and carries the sentinel on the first body line (§4.3). Every other prompt renders as before. |
| `prompt_opencode_command` | Strip canonical frontmatter; emit a new minimal frontmatter with `description:` only (OpenCode's required field), plus `agent: plan` for a read-only prompt (§10.6.1), on line 1, the sentinel as the first body line. Map `input_variables` to `$ARGUMENTS` / `$1` / `$2`, then insert the same `## Before you start` block as `prompt_claude_command` (it holds no placeholder). |
| `hook_advisory` | A hook's advisory text (§6.6.7): a `### <name>` heading, the rendered hook body, and one italic line saying where the hook is enforced, derived from its declared `events` and `supports` (e.g. `*Enforced by lifecycle hooks on: Claude Code, OpenCode. …*`, or `*Not enforced automatically; apply it yourself.*`). Its text (the body plus that line) is shared by every full-text guardrail target: Continue's `30-guardrail-<id>.md`, `agent_harness`'s `rules/30-guardrail-<id>.md` and each section of the `playbook-guardrails` skill (§6.3.4); since v0.21 `AGENTS.md` and the Claude Code rules file carry one guardrail line per hook instead (§6.6.7). The default format of `playbook render <hook-id>`. |
| `hook_claude_settings` | Debug only: the hook's Claude Code registrations as `settings.json` JSON, built from its declared frontmatter alone (no `[hooks]` gating, no consumer config). Never written by sync; a malformed frontmatter is a `HookSchemaError` naming the file. |
The CLI accepts both the full internal name and a short alias (e.g., `--format continue` is shorthand for `continue_rule`; `--format claude` for `claude_md_section`; `--format opencode` for `prompt_opencode_command`). The full names appear in `playbook render --show-source` output for precision; the short aliases are the daily UX.
```python
def render_for(
    template_path: Path,
    body: str,  # already Jinja-rendered
    fmt: str,
    *,
    frontmatter: dict[str, Any],
    rule_registry: RuleRegistry | None = None,  # prompt_continue: the appendix text
    skill_references: SkillReferenceIndex | None = None,  # commands: the block
) -> str: ...
```
Without the matching argument a prompt renders with neither block nor appendix, so `includes_rules` is declarative only. The `agent_harness` prompt leaf is not a `render_for` format: `render_inline_prompt_markdown(body, frontmatter, rule_registry)` returns the titled body plus the same appendix as `prompt_continue`, with no sentinel and no frontmatter (§10.7.2).
## 10. Adapter subsystem
### 10.1 Adapter ABC
```python
# coding_agent_playbook/adapters/base.py
from abc import ABC, abstractmethod
from pathlib import Path
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.artifacts.skill import Skill


class Adapter(ABC):
    name: str  # e.g. "continue"
    # Repo-relative POSIX locations the adapter writes ("dir/" = everything
    # beneath it, else one file), e.g. (".claude/CLAUDE.md",
    # ".claude/rules/coding-agent-playbook.md", ".claude/commands/",
    # ".claude/skills/"). The leftover policy (Section 4.2 step 9) deletes only
    # inside a declared location and never prunes above one.
    output_locations: ClassVar[tuple[str, ...]] = ()
    # Locations an earlier engine release wrote for this adapter and it no longer
    # writes (shared_skills: ("shared_skills/",)). They bound the leftover policy
    # exactly like output_locations, so the first sync after an upgrade settles
    # the old tree; guard_config.json's generated path class never lists them.
    retired_output_locations: ClassVar[tuple[str, ...]] = ()
    # Whether the harness receives scoped rules: through its own rule files
    # (continue, agent_harness) or as skill references (claude_code, opencode,
    # shared_skills). Only agents_md sets False (always rules only); sync warns
    # when every enabled adapter sets False. True for out-of-tree adapters.
    delivers_member_rules: ClassVar[bool] = True
    # Canonical hook event -> the decisions this adapter renders natively. The
    # empty default means advisory-only: hooks degrade to text (v0.20).
    hook_support: ClassVar[Mapping[str, frozenset[str]]] = MappingProxyType({})
    # Files co-owned with the user and the harness (Claude Code's
    # .claude/settings.json): managed elements only, never a whole-file entry.
    # Written by atomic replace, so a dangling link at one is replaced (§12.3).
    shared_outputs: ClassVar[tuple[str, ...]] = ()
    # The root a native Agent-Skills writer writes <root>/<id>/ under
    # (".claude/skills"); None when the adapter writes no native skills. Inside
    # <root>/<id>/ the SkillWriter settles what is in the way (§10.8), so sync
    # --check explains a missing file there its way (§12.3).
    native_skills_root: ClassVar[str | None] = None
    # finalize() outputs that are hook runtime plumbing (the launcher, the
    # OpenCode shim): lock entries of kind "runtime", no artifact id (§14.4).
    # Each is written whole at a fixed path, so sync refuses one the user holds.
    runtime_outputs: ClassVar[tuple[str, ...]] = ()

    @abstractmethod
    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        """Write a rendered rule to the harness-specific location(s).
        Return the paths actually written. Adapters that route rules
        through another adapter (e.g. OpenCode → AGENTS.md) return []."""

    @abstractmethod
    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        """Write a rendered prompt."""

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        """Default: degrade to prompt, except a skill with member rules (§6.3.2),
        which returns []. Subclasses with native skill support (claude_code,
        opencode, shared_skills) override this and delegate to the shared
        SkillWriter (Section 10.8); rules-only adapters return []."""
        if skill.member_references:
            return []
        prompt = skill.to_prompt()
        return self.write_prompt(prompt, repo_root)

    def note_native_skill_roots(self, roots: frozenset[str]) -> None:
        """Called once per sync, before begin_sync, with the native_skills_root
        of every enabled adapter (empty when none writes Agent Skills). agents_md
        keeps its Where map only when it is not empty (§10.4). A separate call,
        not a begin_sync keyword, so an existing begin_sync override keeps
        working. Default: no-op."""

    def begin_sync(
        self,
        repo_root: Path,
        prior_lock: Lockfile | None,
        *,
        hooks_config: HooksConfig | None = None,
    ) -> None:
        """Called once per sync, before any write_*. repo_root is always the
        real repository, even when output goes to a scratch dir (sync --check),
        so an adapter that owns sub-file regions reads the co-owned file and its
        prior ownership hashes here. hooks_config is the parsed [hooks] table.
        Default: no-op."""

    def write_hook(self, hook: ResolvedHook, repo_root: Path) -> list[Path]:
        """Default: degrade the hook to advisory text through this adapter's own
        rule channel (mirrors write_skill -> to_prompt). Hook-capable adapters
        override and fall back to super() for hooks they cannot enforce; a hook
        with a blank body (or [hooks] advisory = false) degrades to nothing."""
        rule = hook.advisory
        return [] if rule is None else self.write_rule(rule, repo_root)

    def writes_guardrails_skill(self, hooks: Sequence[ResolvedHook]) -> bool:
        """Whether this adapter writes the playbook-guardrails skill for these on
        hooks (v0.21, §6.3.4). When True, sync adds the composed skill after the
        other skills write_skill receives. Default: False (continue and
        agent_harness keep their per-hook guardrail rule files, AGENTS.md is no
        skill root); opencode and shared_skills: any hook has an advisory;
        claude_code: a hook with an advisory it cannot run natively."""
        return False

    def planned_runtime_outputs(self, hooks: Sequence[ResolvedHook]) -> tuple[str, ...]:
        """The runtime_outputs finalize() will write for these on hooks
        (repo-relative). Sync checks each on the real repo before any adapter
        writes and exits 1 when it is the user's (no line-1 sentinel, a hard
        link, or a symlink on the way). Default: every declared runtime output once any
        hook lists this adapter in supports; claude_code and opencode override
        it with the exact plan their finalize() uses."""
        targeted = any(self.name in hook.supports for hook in hooks)
        return type(self).runtime_outputs if targeted else ()

    def managed_lock_entries(self) -> list[LockEntry]:
        """The scoped lock entries of the last finalize(): one per managed JSON
        element of a shared output, unchanged ones included. Default: []."""
        return []

    def finalize(self, repo_root: Path) -> list[Path]:
        """Optional lifecycle hook called after all write_* calls for this adapter.
        Used by adapters that buffer artifacts and emit a composite file at the
        end (e.g. Claude Code concatenates rules into one rules file
        next to a rule-free .claude/CLAUDE.md stub).
        Default: no-op."""
        return []

    def stale_outputs(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Read-only: the generated files no longer corresponding to a current
        artifact. THE override point for staleness. Default: the anchored
        sentinel scan (generated_output.sentinel.has_sentinel) of _output_directories(), each
        file once, skipping files in written_paths (compared by file identity
        too, so a case-only rename never reports fresh output), symlinks and
        secret paths (Section 17.3). Native skill directories are never
        reported (Section 4.2 step 9). `playbook sync --check` calls this."""
        return self._stale_by_sentinel(written_paths, repo_root)

    def cleanup_stale(self, written_paths: set[Path], repo_root: Path) -> list[Path]:
        """Write mode: delete exactly what stale_outputs() reports and return it.
        Do not override: check and write mode must never disagree."""
        stale = self.stale_outputs(written_paths, repo_root)
        for path in stale:
            path.unlink(missing_ok=True)
        return stale
```
Adapters customize staleness by overriding `stale_outputs`, never `cleanup_stale`: `playbook sync --check` asks `stale_outputs` and write mode deletes what `cleanup_stale` returns, so only a shared source keeps the check's "run 'playbook sync' to remove" hint true. An out-of-tree adapter written against the pre-v0.16 contract (which overrode `cleanup_stale`, often returning `self._default_cleanup(...)`) keeps working in write mode — `_default_cleanup` is kept, deprecated — but `--check` cannot see what its cleanup deletes: it warns (`adapter '<name>' overrides cleanup_stale() but not stale_outputs()`) and reports no sentinel orphans for that adapter, rather than orphans its cleanup may never remove (MIGRATION.md). Adapters return the paths they wrote. The CLI uses these for the lockfile and for `cleanup_stale`. `output_locations` is read from **every installed** adapter class, enabled or not (`adapters.registry.installed_output_locations()`), so a since-disabled adapter's leftovers can still be settled; so is `retired_output_locations` (v0.21), the locations an earlier release wrote and the adapter no longer writes (`shared_skills` declares the pre-v0.21 `shared_skills/`), so the first sync after an upgrade settles that tree like any leftover, while `guard_config.json`'s `generated` path class lists only current output; a third-party adapter that declares none never has a leftover deleted by the policy (its own `cleanup_stale` still runs while enabled). Of the six adapters the engine ships (the five built-ins plus the opt-in `agent_harness`), four override `finalize()`: `ClaudeCodeAdapter` (it composes `.claude/rules/coding-agent-playbook.md` and the `.claude/CLAUDE.md` stub, §10.3.1, then merges the hook registrations into `.claude/settings.json` and writes the launcher, §10.3.2), `AgentsMdAdapter` (`AGENTS.md`, with its Guardrails section, §10.4), `OpenCodeAdapter` (the one generated plugin, §10.6.2) and `AgentHarnessAdapter` (the whole harness tree, §10.7). Continue and shared_skills write immediately in `write_rule` / `write_prompt` / `write_skill`.

**Hook members (v0.20).** `hook_support`, `shared_outputs`, `runtime_outputs`, `planned_runtime_outputs`, `begin_sync`, `write_hook` and `managed_lock_entries` are concrete defaults, like `write_skill`: an `@abstractmethod` would break every out-of-tree adapter written before hooks existed, and an adapter that overrides none of them is an advisory-only target whose hooks reach its users as text. Sync calls them in one order per adapter (§4.2): `begin_sync(repo_root, prior_lock, hooks_config=…)` with the real repository (under `--check` too), the `write_rule` / `write_prompt` / `write_skill` loops, `write_hook` for every on hook after the skills (a `hook_policy.ResolvedHook`: the winning definition with its rendered body and merged config, §6.6.7), `finalize`, then `managed_lock_entries`; `cleanup_stale` still runs after every adapter's `finalize`. Every on hook goes to every adapter, whatever its `supports`: each adapter decides what it enforces from its own `hook_support` and the hook's `supports`, and `playbook check` labels each pair `enforced`, `degraded`, `advisory` or `—` from the same two (§12.4). Before that loop, sync asks every adapter's `planned_runtime_outputs` for the on hooks and refuses a runtime output the user holds (§4.2 step 6), so an out-of-tree adapter is guarded just by declaring its `runtime_outputs`.

| Adapter | `hook_support` | `write_hook` | Hook output of `finalize` |
| --- | --- | --- | --- |
| `claude_code` | every canonical event (`hook_policy.HOOK_SUPPORT`) | buffers the hooks it enforces; any other goes to `super()`, a section of `.claude/rules/coding-agent-playbook.md` | managed matcher groups in `.claude/settings.json` (its `shared_outputs`) and `.claude/hooks/playbook/launch.sh` (its `runtime_outputs`), §10.3.2 |
| `opencode` | `pre_tool_use`, `post_tool_use`, `session_start` and `stop` (the last two degraded) | buffers every hook and returns `[]` | `.opencode/plugins/playbook-hooks.js` (its `runtime_outputs`), §10.6.2 |
| `agents_md` | `{}` | buffers every on hook's advisory | the trailing `## Guardrails` section of `AGENTS.md`, §10.4 |
| `continue` | `{}` | ABC default: `.continue/rules/30-guardrail-<id>.md` through `write_rule` | — |
| `agent_harness` | `{}` | buffers every hook | `rules/30-guardrail-<id>.md` and the `.playbook/hooks/<id>/` sidecar, §10.7.2 |
| `shared_skills` | `{}` | ABC default (its `write_rule` writes nothing) | — |

**The guardrails skill (v0.21).** `writes_guardrails_skill(hooks)` is a concrete default like the hook members, so an out-of-tree adapter keeps what it wrote before. Sync composes the `playbook-guardrails` skill once from the on hooks (§6.3.4) and, for each adapter whose `writes_guardrails_skill` holds for them, appends it to the skills that adapter's `write_skill` receives; every other adapter never sees it, so Continue writes no prompt for it. `opencode` and `shared_skills` return `True` when any on hook has an advisory (their harnesses read the `AGENTS.md` guardrails); `claude_code` returns `True` only for a hook with an advisory that it does not run natively (`adapters.claude_code.hooks.runs_natively`, the same test `write_hook` uses: `claude_code` in the hook's `supports` and one of its events in `hook_support`), so with the core pack `.claude/skills/` gets no `playbook-guardrails`; `continue`, `agent_harness` and `agents_md` keep the default `False`.
### 10.2 Continue adapter
```python
# coding_agent_playbook/adapters/continue_.py
class ContinueAdapter(Adapter):
    name = "continue"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        target = repo_root / ".continue" / "rules" / f"{rule.priority:02d}-{rule.id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render(rule), encoding="utf-8")
        return [target]

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / ".continue" / "prompts" / f"{prompt.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render(prompt, invokable=True), encoding="utf-8")
        return [target]
```
**Hooks: none — guardrail text only.** Continue ships no wired hook mechanism: the `cn` CLI's hook code is dormant in every published bundle and the IDE `config.yaml` has no hooks key. The Continue adapter therefore never writes hook configuration under `.continue/`; Continue receives each enabled hook's guardrail text only, as a rule file (`specs/prK-lifecycle-hooks.md` §A.8).

**Rules: one file per rule, scoped ones included.** Continue reads no skills, so the skills-first delivery (§6.3.3) does not apply to it: every rule that passes `applies_if` keeps its own `.continue/rules/<priority>-<id>.md` (§6.1.3), a member rule included, and `continue_rule` drops the `skill` key like every other canonical-only key (§9.7). A skill with member rules is not degraded to a Continue prompt either (§6.3.2): its members already arrive here as rule files, and the prompt would index `references/` files Continue never receives.
#### 10.2.1 Numbering scheme
Continue loads rules in lexicographical order, so the file name controls priority. The adapter prefixes filenames with the rule's `priority` (default 50, zero-padded to 2 digits). Authors keep priorities sparse (00, 10, 20, ..., 90) so new rules can slot in without renumbering.
| Priority | Used for |
| --- | --- |
| `00` | Project context (project name, kind, top-level description) |
| `10` | Python house style (the eight always-loaded conventions) |
| `20` | Tooling baseline (ruff, mypy, pytest, package manager) |
| `30` | Compliance and security (overlay territory) |
| `40`-`59` | Language-specific scoped rules (dependency injection, pure core, data shapes, typing, performance idioms, asyncio, classes and protocols, error handling, idioms) |
| `60` | Framework-specific scoped rules (fastapi, pydantic, sqlalchemy) |
| `70` | Domain-specific scoped rules |
| `90` | Per-repo customizations from `playbook/` |
### 10.3 Claude Code adapter
```python
class ClaudeCodeAdapter(Adapter):
    name = "claude_code"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        # Rules are concatenated into .claude/rules/coding-agent-playbook.md,
        # not written individually (§10.3.1). The adapter buffers rules and
        # writes once in finalize(). A member rule is skipped: it is a
        # reference of the skill it names, written by write_skill.
        if is_skill_member(rule):
            return []
        self._buffered_rules.append(rule)
        return []  # actual path returned by finalize()

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / ".claude" / "commands" / f"{prompt.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_command(prompt), encoding="utf-8")
        return [target]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        # .claude/skills/<id>/ via the shared SkillWriter (Section 10.8); a skill
        # with member rules and a playbook.files phrase also adds its line to
        # the rules file's "Where guidance lives" section.
        self._where.add(skill)
        return SkillWriter(Path(".claude") / "skills").write(skill, repo_root)

    def finalize(self, repo_root: Path) -> list[Path]:
        # settings.json first: a file that cannot be merged stops the sync
        # before this adapter writes anything (§10.3.2).
        hook_paths = self._compose_settings(repo_root)
        return [*self._compose_rule_files(repo_root), *hook_paths]

    def _compose_rule_files(self, repo_root: Path) -> list[Path]:
        body = self._rules_body()  # sorted sections, Where section (+ heartbeat line), §10.3.1
        if body is None:
            return []  # nothing written; cleanup_stale removes a stale engine-owned pair
        # .claude/rules/ holds the user's files, and the stub is never written
        # through a symlink or a hard link: refuse before writing either (§10.3.1)
        check_rule_files_writable(repo_root)
        stub = _generated_header("# CLAUDE.md")  # the whole .claude/CLAUDE.md
        rules = f"{_generated_header('# Project rules (coding-agent-playbook)')}\n{body}"
        rules_path = repo_root / CLAUDE_RULES_PATH
        return [
            _write_output(repo_root / CLAUDE_MD_PATH, stub),  # plain overwrite, LF bytes
            write_engine_owned(rules_path, repo_root, rules.encode("utf-8")),
        ]
```
Skills are written natively to `.claude/skills/<id>/` (`SKILL.md` + byte-copied `scripts/` and `references/`) by the shared `SkillWriter`, with `name` = id and the sentinel as the first body line (§6.3). Core's skills are among them: a skill with member rules also gets one `references/<rule-id>.md` per active member and the generated index (§6.1.6, §6.3.3). `stale_outputs` (and so `cleanup_stale`) combines two passes: the anchored sentinel scan (`generated_output.sentinel.has_sentinel`) over `.claude/commands/` and the launcher directory `.claude/hooks/playbook/`, and the single-file check of `.claude/CLAUDE.md` and `.claude/rules/coding-agent-playbook.md` (each reported only when it carries the sentinel and was not re-written this sync). It never scans `.claude/rules/`: every other file there is the user's. It never deletes inside `.claude/skills/`: stale skill output is settled by the lockfile leftover policy (§4.2 step 9, §10.8). `.claude/settings.json` is never stale: managed elements are removed inside `finalize`, and the file itself is never deleted. Hooks are §10.3.2.
#### 10.3.1 Rule composition: the rules file and the `CLAUDE.md` stub
`finalize()` writes two files. The always rules, then the generated `## Where guidance lives` section, go to `.claude/rules/coding-agent-playbook.md`:
```markdown
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->
# Project rules (coding-agent-playbook)

This file is generated by coding-agent-playbook.

[for each rule, ordered by (priority, id) — one flat list, no grouping by scope:]
## {rule.name}

*Applies to: `{glob}`, `{glob}`*        ← only for scope=scoped with non-empty globs; advisory, gates nothing

[body]

---
[when a written skill has member rules and a playbook.files phrase:]
## Where guidance lives

Detailed conventions live in skills. Before you edit one of these files, load its skill and open the references its index lists.

- {playbook.files}: skill `{skill id}`        ← one line per such skill, sorted by skill id

Lint feedback names a rule id; that rule's reference in the skill has the fix.

---
[with session-start-playbook-briefing on, the closing heartbeat line (§10.3.2)]
```
`.claude/CLAUDE.md` is that four-line header with its own title, and nothing else:
```markdown
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->
# CLAUDE.md

This file is generated by coding-agent-playbook.
```
Each section is a `claude_md_section` rendering (§9.7): the rules, each byte-identical to its `AGENTS.md` section (up to line endings: both Claude Code files are written as LF bytes, while `AGENTS.md` is still written in text mode, so CRLF on Windows), in one list sorted by `(priority, id)`. A member rule (a scoped rule that names a skill in `skill:`) is never a section: the adapter drops it, and the Where section after the list names its skill instead (`skills.document.where_guidance_section`, the one function both composite files call, so the section is byte-identical in `AGENTS.md`). A hook Claude Code cannot run (`adapters.claude_code.hooks.runs_natively` is false: `claude_code` is missing from its `supports`, or none of its events reaches Claude Code) adds no section: with guardrail text, it adds one guardrail line to a `## Guardrails` section after the Where section, `hook_policy.guardrails_section` as in `AGENTS.md` (§10.4), and its full text is in `.claude/skills/playbook-guardrails/` (§6.3.4; D26). With the core hooks every hook runs natively, so the file has no Guardrails section. With session-start-playbook-briefing on, one fixed heartbeat line closes the rules file (§10.3.2). Project name and description reach the file only through rules that render them (e.g. the bundled `00-project-context` rule). Prompts are not listed: they live in `.claude/commands/`. With no rule, no Where line, no guardrail line and no heartbeat line, `finalize()` writes neither file and a stale engine-owned one is removed; a heartbeat line alone still writes both, the rules file then holding only that line. The rules file is one unscoped engine file: it carries no frontmatter, so Claude Code always loads it, and per-rule `paths:` scoping (Claude Code's native path-scoped `.claude/rules/<id>.md`) is still not used: no scoped rule reaches it in full (`playbook validate` requires `skill:` on every authored scoped rule, V1 in §12.6, and a hook's advisory rule becomes a guardrail line), and a member rule is not in this file: it is a reference of the skill it names, under `.claude/skills/<skill>/references/`. The engine owns exactly that one path: `output_locations` declares the file, never the `.claude/rules/` directory, so every other file there is the user's and is never read, rewritten, gitignored or deleted. Because that directory holds the user's files, the rules file is written whole only over nothing or a file carrying the sentinel on line 1, like the launcher (§10.3.2, `adapters/_owned_files.py`): a same-named file of the user's, anything that is not a regular file, a hard link, or a symlink at the path, at `.claude` or at `.claude/rules` is refused, never written through, and a stale-output check never reports a file reached through such a link. With `claude_code` enabled, sync checks the path before any adapter writes, hooks or not: write mode exits 1 with `error: .claude/rules/coding-agent-playbook.md: <reason>` and `error: playbook sync stopped; .claude/rules/coding-agent-playbook.md was not changed.`, and `--check` / `--check-staged` print `Cannot verify .claude/rules/coding-agent-playbook.md: <reason>.` and exit 1. The stub keeps its plain overwrite of whatever regular file is there, but is never written through a link either: a symlink at `.claude/CLAUDE.md` is refused the same way, before any adapter writes, with `error: .claude/CLAUDE.md: it is a symbolic link, and the engine never writes through one` (`--check`: `Cannot verify .claude/CLAUDE.md: …`), and so are a hard link (`it is a hard link shared with another file, …`) and anything that is not a regular file, such as a directory or a FIFO (`it is not a regular file`). Writing the stub in place through the common `.claude/CLAUDE.md -> ../AGENTS.md` link, or through the same file hard-linked (the usual stand-in on Windows, where file symlinks need developer mode), would otherwise turn `AGENTS.md` into the stub for every other tool. (A linked `.claude` is already refused by the rules-file check above.) Both files are `kind = "composite"` lock entries (§14.4) and composite singletons of the hook guard tables, so guard-generated-outputs denies an agent's edit of either with the same reason and the drift scan reports either as an orphan (`specs/prK-hook-pack.md` §E.1).

**Why two files.** OpenCode v1 (anomalyco/opencode v1.19.3, `session/instruction.ts:171-218` via `tool/read.ts:300`) attaches the first `AGENTS.md`/`CLAUDE.md` of each directory between a file its read tool opens and the working directory (§10.6), so with the rules in `.claude/CLAUDE.md`, an OpenCode run at or above the repo root added a second full copy of them when its read tool opened a file under `.claude/` (once per uncompacted session, §10.6), and leaked the Claude-only heartbeat line to OpenCode. Neither OpenCode v1 (1.19.3) nor v2 (dev `24c7f7a`) discovers `.claude/rules/` on its own (v1 looks up files named `AGENTS.md`, `CLAUDE.md` or `CONTEXT.md`; v2 only `AGENTS.md`, and its `.claude/` compatibility reads only `skills/`). Only an `opencode.json` `instructions` entry the user adds, such as `.claude/rules/*.md`, would load it, next to `AGENTS.md`. Claude Code loads `.claude/rules/*.md` files without `paths:` frontmatter "at launch with the same priority as `.claude/CLAUDE.md`" (code.claude.com/docs/en/memory). `.claude/CLAUDE.md` must still exist, rule-free: in Claude Code's default `claude-md-or-agents-md` mode (v2.1.277+) a `CLAUDE.md`, `.claude/CLAUDE.md` or `CLAUDE.local.md` in the working directory or above it stops Claude from also reading the root `AGENTS.md` natively, while a `.claude/rules/` file does not count and keeps loading alongside `AGENTS.md`, so without the stub Claude would load the rules twice. The stub names no rules file on purpose: OpenCode v1 still attaches it, and a pointer would invite its model to read the rules again. Live-verified on Claude Code 2.1.292 (2026-10-16, `claude -p` witness tokens): with `AGENTS.md`, a header-only `.claude/CLAUDE.md` and a `.claude/rules/` file, Claude loads only the rules file, both at the repo root and when launched from a subdirectory.
#### 10.3.2 Hooks: the managed `settings.json` merge, the launcher and the pin (v0.20)
With `[hooks] enabled = true` and `claude_code` among the `[hooks] adapters` (§7.1.1), the adapter enforces hooks natively (`adapters/claude_code/hooks.py`, `adapters/claude_code/settings/managed_merge.py`, `hook_registrations/claude.py`; design `specs/prK-lifecycle-hooks.md` §C.2). Its `finalize` merges the registrations into the co-owned `.claude/settings.json` **first**, so a file it cannot merge stops the sync before this adapter writes anything.

**Registrations.** There is one managed matcher group per Claude event that has an on hook, each holding exactly one `command` handler; the dispatcher fans out to the hooks in-process. `SessionStart` is registered whenever any registration exists (the session bootstrap, the heartbeat briefing, and the launcher's one visible failure channel), and at most one extra `async: true`, non-deciding `PostToolUse` group carries the async-safe handlers (local-audit-log). Handler keys are closed: `type`, `command` and `timeout`, plus `statusMessage` on `Stop` / `SubagentStop`, `onFailure: "block"` only in overlay strict mode, and `async: true` only on that one group — never `if`, `args`, or a handler type other than `command`. The command is the same string on every machine (here for `pre_tool_use`):
```text
sh "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null || echo .)}/.claude/hooks/playbook/launch.sh" dispatch pre_tool_use --harness claude_code
```
In overlay strict mode `--strict-launch` precedes `dispatch`, and the async group's command ends in `--async`. The shell fallback is the git top level, never the cwd, and no path or digest of `guard_config.json` appears, so the registration bytes never change when only `guard_config.json` does. The timeout is `ceil(deadline_ms / 1000) + 2` seconds over the event's deadline in `guard_config.json` (sync checks the one-second margin), and the matcher is the union of the members' tool classes: `*` when one matches every tool, else a sorted exact list (`Edit` never matches `NotebookEdit`), anchored as `^(?:…)$` once an `mcp` class adds a regex.

**Ownership: lockfile hashes, never markers.** JSON has no comment syntax, so a managed element is identified only by the sha256 of its canonical JSON, recorded as a scoped lock entry (`scope = "json:/hooks/<Event>"`, `kind = "runtime"`, `artifact_id = "registration:<event>"`, §14.4); teammates share ownership through the lockfile. The merge parses strictly (duplicate keys, `NaN`, comments and trailing commas are errors, as they are for Claude Code) and plans per event: an equal element is kept; a hand-edited group the prior lockfile records is **restored with a warning** (`managed entry was edited by hand; restored`); a deleted one is re-added, since deleting a group is no off switch (`[hooks]` is); a stale one is removed; and a group mixing the launcher with a user handler is an error naming `hooks.<Event>[i]`. An empty plan rewrites nothing; otherwise each edit is spliced into the original text, so user keys, user hook groups, indentation, line endings and a BOM stay byte-identical. The file is never deleted, even when its last managed element goes. A file that cannot be merged raises `SettingsMergeError` (`path:line:col: message`): write mode exits 1 with `error: playbook sync stopped; .claude/settings.json was not changed.`, and `--check` prints `Cannot verify .claude/settings.json: <message> at L:C.` and exits 1.

**Other managed arrays.** The same machinery manages engine strings in `permissions.deny`, `sandbox.filesystem.denyRead` and `sandbox.network.allowedDomains` — the native twins of the secret, destructive-command and overlay network and read guards that are on: deny rows, and the network guard's allowed domains — and, only with `[hooks] render_remediation_allow = true`, a fixed `permissions.allow` list (`playbook validate`, `playbook check`, `playbook sync --check`, `playbook sync`, `ruff check .`, `ruff format --check .`; never `pytest` or `mypy`, which run repo-controlled code). Each string is one scoped lock entry (`artifact_id = "permission:<list>:<string>"`), and user entries are never touched. `.claude/settings.local.json` is **never written**: it is Claude Code's personal file.

**Both `[output] commit` values.** `.claude/settings.json` is a shared output under either value: it never gets a whole-file lock entry, never enters the managed `.gitignore` block, is never flagged by `playbook sync --check-staged` and is never deleted, so whether it is committed stays the team's decision. `--check` merges against the real file although it renders into an empty scratch directory, and reports drift only when the managed projection differs (a hand-edited or deleted managed group, an on hook not yet registered); user edits to `permissions`, `env` or formatting are never drift. The launcher, like `guard_config.json` and copied hook scripts, is ordinary generated output: under `[output] commit = false` it is gitignored and rendered in each clone by the post-checkout `playbook sync`; under `[output] commit = true` it is committed and compared by `sync --check`. Either way a registration is inert until a local write-mode sync: without the launcher (a fresh `commit = false` clone of a repo that commits `settings.json`) Claude Code reports a non-blocking hook error and the call proceeds, and without the interpreter pin the launcher exits 0.

**The launcher.** `.claude/hooks/playbook/launch.sh` carries the sentinel as `# …` on line 1 and no shebang (it runs as `sh launch.sh`), holds nothing machine-specific, and is rendered from a one-placeholder template (`str.replace`, never Jinja). It reads the interpreter from the per-worktree pin `<git-dir>/playbook-hooks/interpreter` and runs `<pin> -I -m coding_agent_playbook.hook_runtime "$@"`. It exits 0, or 2 only when the dispatcher exits 10 (a decided deny); any other dispatcher exit is appended to `<git-dir>/playbook-hooks/launcher.log` and becomes 0, so a broken install never blocks a tool call. Under `--strict-launch` it exits 1 instead, which `onFailure: "block"` turns into a block. On `session_start` without a usable pin it prints a `systemMessage` saying the lifecycle hooks are INACTIVE and pointing at `playbook-hook doctor`. The launcher is written whole, and only over nothing or a file carrying the sentinel on line 1: a same-named file of the user's, anything that is not a regular file, a hard link (`st_nlink > 1`, sentinel-tagged or not), or a symlink at the path or at a directory between it and the repo root (`.claude`, `.claude/hooks`, `.claude/hooks/playbook`) is refused, never written through (`adapters/_owned_files.py`). Sync checks it before any adapter writes, so the merge above never runs half-way: write mode exits 1 with `error: .claude/hooks/playbook/launch.sh: <reason>` and `error: playbook sync stopped; .claude/hooks/playbook/launch.sh was not changed.`, and `--check` / `--check-staged` print `Cannot verify .claude/hooks/playbook/launch.sh: <reason>.` and exit 1. The engine never moves the file itself: the user renames it, then re-runs sync.

**The pin.** Write-mode `playbook sync` (hooks on, `claude_code` or `opencode` enabled) writes the interpreter pin — `sys.executable`, unresolved, so a venv's `bin/python` keeps its site-packages — only when none names an executable file yet (the first writer wins, so a venv and pre-commit's environment never flap), and rewrites `<git-dir>/playbook-hooks/machine.json`, the per-machine tool pins (a path plus a stat signature; a Stop stage whose tool changed is skipped, never green). Neither file is committed, so committed output stays machine-independent. `playbook-hook doctor --repin [PYTHON]` rewrites the pin (§12.13). Outside a git work tree nothing is pinned and sync warns: hooks are git-only in v1. The pin is not a trust approval (§7.1.1 `allow_code_from`).

**The rules file and commands.** Hooks Claude Code enforces add nothing to the rules file `.claude/rules/coding-agent-playbook.md` (their deny reasons and the session-start briefing carry the context); a hook it cannot run becomes one guardrail line there (§10.3.1). When session-start-playbook-briefing is on, the rules file ends with one fixed heartbeat line, which is never written to `AGENTS.md` nor to the `.claude/CLAUDE.md` stub (OpenCode v1 attaches the stub, §10.3.1, so a hookless OpenCode session would see an instruction it can never satisfy) and changes the rules file once per opted-in repo (MIGRATION.md):
```text
If PLAYBOOK-GUARDS: OK did not appear at session start, tell the user guardrails are not running before risky work.
```
A read-only prompt (`write_scope: {read_only: true}`) renders as a command whose frontmatter is `disallowed-tools: Edit Write NotebookEdit`, with the sentinel on the first body line (§9.7); every other command renders as before.

**Caveats** (`specs/prK-lifecycle-hooks.md` §C.2.9, §C.5.2):
- *Launch directory.* Claude Code reads project settings only from the `.claude/` of the directory the session starts in, with no parent fallback: a session started in a subdirectory loads no playbook hook, and the heartbeat cannot report it either.
- *Trust and `-p`.* An interactive session holds every project hook until the folder's trust dialog is accepted; `-p` and SDK runs count as trusted and run the registrations at once, inert until a local sync has pinned an interpreter.
- *Cloud sessions.* Anthropic-hosted multi-repo cloud sessions read only `enabledPlugins` / `extraKnownMarketplaces` from repo settings, so no playbook hook runs there.
- *Policy kill switches.* `disableAllHooks` in any settings file, a managed `allowManagedHooksOnly` and `strictPluginOnlyCustomization: ["hooks"]` silently drop project hooks.
- *Hot reload.* Settings edits apply to the running session: a `playbook sync` takes effect without a restart, and so would an agent's edit removing a managed group, which is why control-plane-guard denies structured edits of the settings files in-session.
- *Windows.* Supported with Git Bash, which Claude Code uses for shell-form hooks; on a PowerShell-only install the `sh …` command fails and Claude Code shows its non-blocking hook error: fail-open (OQ-14).
- *Concurrent handlers.* Claude Code runs every matching handler in parallel, the user's own included, and the playbook group always sees the original `tool_input`. A user, plugin or skill hook returning `updatedInput` can still change the executed input after the playbook's verdict, a known gap that ordering cannot close.
- *Incidental reach.* Other harnesses read `.claude/settings.json` too (Cursor, GitHub Copilot CLI, VS Code's opt-in Claude format); the dispatcher goes inert on a payload that is not Claude-shaped. Copilot CLI's `preToolUse` fails closed on errors, so a repo used with Copilot CLI, on Windows above all, must be verified against the real CLI before relying on hooks (OQ-15). Gemini CLI's `gemini hooks migrate --from-claude` copies `timeout` into a milliseconds field: never migrate playbook-managed entries.
### 10.4 AGENTS.md adapter
Always enabled (adapter discovery, `adapters.registry.discover_adapters`, adds `agents_md` to every enabled set). Produces a single `AGENTS.md` at the repo root. Identical in shape to the Claude Code rules file (§10.3.1, title `# AGENTS.md`; rule sections byte-identical) but lives at the root because that's where Codex, Cursor, and Copilot look for it; hooks go to a trailing Guardrails section (below), one line each, instead of being sorted in with the rules. It holds the always rules (a member rule, one that names a skill in `skill:`, is dropped: it is a reference of that skill), then the generated `## Where guidance lives` section, byte-identical to the rules file's, then the Guardrails section. Without member skills the file is byte-identical to the rules-only composition. The map names only skills a sync writes, so it is kept only when some enabled adapter declares a `native_skills_root` (`Adapter.note_native_skill_roots`, §10.1): with `adapters_enabled = []` or only `continue`, `AGENTS.md` has no Where section. With no always rule left after `applies_if` filtering, no Where line and no guardrail line, nothing is written and a stale engine-owned `AGENTS.md` is removed. When member rules are active and no enabled adapter delivers them (`Adapter.delivers_member_rules`, False only here), `playbook sync` prints `warning: no enabled adapter delivers scoped rules (only agents_md is on); skill <id> reaches no assistant: add claude_code, opencode or shared_skills to adapters_enabled` on stderr; nothing is inlined into `AGENTS.md` instead.
```python
class AgentsMdAdapter(Adapter):
    name = "agents_md"
    # Buffers each always rule's agents_md_section in write_rule (a member
    # rule is skipped), each skill's Where line in write_skill and each on
    # hook's guardrail line in write_hook; finalize() composes repo_root / "AGENTS.md":
    # rules ordered by (priority, id), the Where section, then the Guardrails
    # section by hook id. write_prompt is a no-op and write_skill writes no
    # file: prompts are not listed in AGENTS.md, and a skill appears only as
    # its Where line. Continue, Claude
    # Code and OpenCode get them from their own adapters (skills also through
    # .agents/skills/); a harness that only reads AGENTS.md (Cursor, Copilot)
    # gets the always rules and the map of skills, and Codex reads its skills
    # from .agents/skills/.
```
**Guardrails section (v0.20, one line per hook since v0.21).** With hooks on, `AGENTS.md` ends with a `## Guardrails` section with one guardrail line per on hook that has guardrail text, enforced elsewhere or not: Codex, Cursor, Copilot, Gemini and the other AGENTS.md readers see this list, and OpenCode reads its guardrails here too. The section opens with one fixed preface (`Lifecycle hooks enforce these on assistants that run them; on every other assistant, follow them yourself. Skill `playbook-guardrails` has the full text of each one and where it is enforced.`), then one line `- `<id>`: <text>` per hook, sorted by hook id (`hook_policy.guardrails_section` over `guardrail_line`), where the text is the hook's `summary`, else its body's first sentence (§6.6.7). The preface says once what each `### <hook name>` block used to say with its italic enforcement line: those blocks are now the sections of the `playbook-guardrails` skill (§6.3.4), written by `opencode` and `shared_skills`. With both of them off the preface names a skill no `AGENTS.md` reader can load, like a Where line; there is no fallback. A hook with a blank body (infrastructure such as guard-decision-log) or `[hooks] advisory = false` adds nothing. `AGENTS.md` is always generated, in a hooks-only repo too (§4.3); with no on hook it is byte-identical to v0.19's. `playbook check` labels this channel `advisory`, never `enforced` (§12.4).
### 10.5 Adapter registration
Adapters are registered via entry points so overlay packages can ship their own (e.g. a Cursor adapter from a community package).
```toml
[project.entry-points."coding_agent_playbook.adapters"]
continue = "coding_agent_playbook.adapters.continue_:ContinueAdapter"
claude_code = "coding_agent_playbook.adapters.claude_code.adapter:ClaudeCodeAdapter"
opencode = "coding_agent_playbook.adapters.opencode:OpenCodeAdapter"
shared_skills = "coding_agent_playbook.adapters.shared_skills:SharedSkillsAdapter"
agents_md = "coding_agent_playbook.adapters.agents_md:AgentsMdAdapter"
agent_harness = "coding_agent_playbook.adapters.agent_harness_adapter:AgentHarnessAdapter"
```
### 10.6 OpenCode adapter
OpenCode is structurally close to Claude Code but with one architectural twist: rules are not in a dedicated directory. OpenCode reads `AGENTS.md` as its primary rules source, walking up the directory tree. This means the AGENTS.md adapter already delivers the always rules to OpenCode, while member rules reach it as references in `.opencode/skills/<skill>/` — the OpenCode adapter's job is prompts, skills and, with hooks on, the one generated plugin (§10.6.2). **Hooks need OpenCode ≥ 1.18.29**, the floor of the V1 plugin API the shim targets; `playbook-hook doctor` warns below it (§12.13), and the README states it. The lookup differs by version (verified against anomalyco/opencode source; the docs lag it):
- **v1 (`opencode-ai` ≤ 1.19.x)** walks from the working directory up to the git worktree root and loads *every* `AGENTS.md` on that path, not just the nearest (`packages/opencode/src/session/instruction.ts:122-133`, `packages/core/src/fs-util.ts:154-166` at v1.19.3). At startup `CLAUDE.md` replaces it only when no `AGENTS.md` exists anywhere on that path. Separately, when the agent reads a file, v1 attaches the first `AGENTS.md`/`CLAUDE.md` found in each directory between that file and the working directory (`instruction.ts:171-218`, `tool/read.ts:300`) — so reading anything under `.claude/` also attaches the Claude Code adapter's `.claude/CLAUDE.md`. That file is a rule-free four-line stub (§10.3.1), so the attachment adds only its header; the rules, hook advisories and heartbeat line live in `.claude/rules/coding-agent-playbook.md`, which neither OpenCode v1.19.3 nor v2 (dev `24c7f7a`) discovers on its own (§10.3.1). Neither path uses `CLAUDE.md` when `OPENCODE_DISABLE_CLAUDE_CODE` or `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT` is set.
- **v2 (`@opencode/cli` 2.x, the `packages/core` rewrite; verified at dev `24c7f7a`)** loads `AGENTS.md` only — no `CLAUDE.md`, at startup or on reads (`packages/core/src/tool/plugin/read.ts:16`). Like v1 it loads *every* `AGENTS.md` on the walk, which goes up to `$HOME` when the working directory is under it and otherwise stops at the project root (`packages/core/src/config/plugin/instruction.ts:36-40,76-86`). Under `$HOME` that includes `AGENTS.md` files above the repo — e.g. the main checkout enclosing a nested `.claude/worktrees/<name>` worktree.
Either way, unless `OPENCODE_DISABLE_PROJECT_CONFIG` is set, the root `AGENTS.md` is loaded in full on every step. OpenCode's only scoped loading is by directory (the read-time attachment above); it has no glob-scoped rule loading, so a scoped rule's `globs` gate nothing here: OpenCode loads the rule's skill by its description, then opens the reference.
**The v1 read-time attachment (with `claude_code` enabled).** The read-time attachment of `.claude/CLAUDE.md` happens only when OpenCode runs at or above the repo root (the walk never leaves the working directory), and only when the read tool reads a *file* under `.claude/` (a directory listing does not trigger it). It recurs: v1 skips an instruction file only if an earlier, uncompacted `read` result in the same session already carried it (`instruction.ts:17-32`), so the file comes back after every compaction and in every subagent session, and each `@`-mention of a file under `.claude/` re-attaches it, because prompt-time file reads run with no message history (`session/prompt.ts:808-827`). Because the Claude Code adapter keeps `.claude/CLAUDE.md` rule-free (§10.3.1), each attachment adds only the four-line header: no rule, no hook advisory and no heartbeat line, so no workaround is needed. Engine versions before that change put every rule section (and, with hooks on, the advisories and the heartbeat line) in `.claude/CLAUDE.md`, so OpenCode v1 loaded the rules twice; until such a repo is synced with a current engine, the workaround is to set `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=1` in the environment OpenCode runs in. It removes `CLAUDE.md` from both the startup and the read-time lookup, but also drops the global `~/.claude/CLAUDE.md` fallback (`effect/runtime-flags.ts:23-30`, `instruction.ts:60-68`). `OPENCODE_DISABLE_CLAUDE_CODE=1` does the same and also disables `.claude/skills/` discovery, which is harmless here because the OpenCode adapter writes `.opencode/skills/`. There is no `opencode.json` equivalent, and the engine sets neither variable (the environment and `opencode.json` belong to the user, §10.6.4). v2 needs no workaround.
Skills are written natively to `.opencode/skills/<id>/SKILL.md` (+ `scripts/`, `references/`) through the shared `SkillWriter` (§10.8), so OpenCode no longer depends on the Claude Code adapter being enabled. OpenCode *also* scans `.agents/skills/` and `.claude/skills/` (its compatibility roots), so with `shared_skills` and `claude_code` on the same skill is discovered up to three times (`.opencode`, `.agents`, `.claude`). That is safe: OpenCode keeps one skill per key — v2 in a `Map` keyed by skill id, the directory name (`packages/core/src/skill.ts:100-101` at dev `24c7f7a`), applying its precedence `.opencode > .agents > .claude`; v1.19.x in a record keyed by frontmatter `name`, logging one "duplicate skill name" warning per extra copy (`packages/opencode/src/skill/index.ts:125-134`), which `OPENCODE_DISABLE_EXTERNAL_SKILLS` (drops `.agents` and `.claude`) or `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` (drops `.claude`) silence; the engine sets neither. The engine writes `name` = id = directory name, and every copy is byte-identical, so any winner is correct.
```python
class OpenCodeAdapter(Adapter):
    name = "opencode"

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        # OpenCode reads AGENTS.md natively: always rules are routed through
        # the AgentsMdAdapter, member rules travel as references of the
        # skills write_skill writes, and nothing is duplicated here.
        return []

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        target = repo_root / ".opencode" / "command" / f"{prompt.slash}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self._render_command(prompt), encoding="utf-8")
        return [target]

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        # .opencode/skills/<id>/ via the shared SkillWriter (Section 10.8);
        # byte-identical to the .claude/skills/ copy.
        return SkillWriter(Path(".opencode") / "skills").write(skill, repo_root)
```
#### 10.6.1 Prompt → OpenCode command format
OpenCode commands are markdown with YAML frontmatter. Required field is `description`; optional fields include `agent`, `model`, `subtask`. Placeholders supported in the body: `$ARGUMENTS`, `$1`, `$2`, …, `@path/to/file`, ``!`shell command` ``.
For a canonical prompt like `generate-tests`, the rendered output at `.opencode/command/generate-tests.md`:
```markdown
---
description: Generate pytest tests for the provided code, following the project's testing conventions
---
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->

# Task: generate tests
You are writing tests for risk-models, a python-application project.

## Before you start

1. Load skill `python-coding` and read its reference `references/python-typing.md`.
2. Load skill `python-testing` and read its reference `references/pytest.md`.
3. For each file in scope, also load any other listed skill whose description matches it.

## Conventions
[rest of body, fully rendered; no rule text]
```
The frontmatter must be the first line: OpenCode parses commands with gray-matter, which only recognises frontmatter at offset 0, so the sentinel is the first body line. (Engines before this release wrote it on line 1, which dropped the `description` and leaked the envelope into the prompt; the sentinel comment line itself remains the first template line, as it does for skills.) The OpenCode adapter's cleanup uses the shared anchored detector (`generated_output.sentinel.has_sentinel`, §4.3): the exact sentinel line on line 1 or as the first line after a leading frontmatter block, ignoring a UTF-8 BOM, so a re-sync rewrites old-layout commands in place and still removes stale ones, while a hand-written command that merely quotes the sentinel is kept.
Mapping from canonical to OpenCode:
| Canonical field | OpenCode placement |
| --- | --- |
| `description` | Frontmatter `description` (required) |
| `slash` | Filename: `.opencode/command/<slash>.md` |
| `input_variables` | Mapped to `$ARGUMENTS` and positional `$1`, `$2`, … |
| `includes_rules` | The `## Before you start` block naming each active rule's skill and reference, the same block as the Claude Code command (§6.2.5); no rule text |
| `name` | Not used in frontmatter; OpenCode uses filename as the command name |
| `applies_if` | Evaluated upstream by the engine; non-matching prompts produce no file |
| `write_scope` | `{read_only: true}` adds `agent: plan` to the frontmatter; any other scope adds nothing |
OpenCode commands have no native concept of named input variables beyond positional `$N`. If a prompt declares an input variable `target`, the adapter substitutes `$ARGUMENTS` for it in the body and inlines a brief HTML comment noting the variable's purpose for the human reader. Of OpenCode's optional `agent` / `model` / `subtask` frontmatter fields the adapter models one case: a read-only prompt (`write_scope: {read_only: true}`, §6.2.1) adds `agent: plan`, so the command runs as OpenCode's built-in `plan` agent, which has no edit tools (§9.7). Every other command runs in OpenCode's default agent with the user's default model. `/review` and `/security-review` are read-only, so their `## Before you start` block assumes the `plan` agent may call OpenCode's `skill` tool; that is not yet verified on OpenCode v1.19.3 and v2.0.32 (specs/prS-skills-context.md R3-3, Q2). Until a manual smoke test (specs/prS-skills-context.md §7.9 item 8) checks it, the engine ships D15 as written. Should the test fail, D25 adopts one fallback, to be recorded here when implemented: those two commands, on OpenCode only, get the inline `## Reference rules` appendix instead of the block.
#### 10.6.2 Hooks: the one generated plugin (v0.20)
With `[hooks] enabled = true` and `opencode` among the `[hooks] adapters` (§7.1.1), `write_hook` buffers every on hook and `finalize` renders **exactly one file**, `.opencode/plugins/playbook-hooks.js`, an OpenCode V1 plugin (`hook_registrations/opencode.py`; design `specs/prK-lifecycle-hooks.md` §C.3). With no hook OpenCode can enforce, nothing is written. It is the one exception to §10.6.4's "never touch `.opencode/plugin(s)/`": V1's non-recursive `{plugin,plugins}/*.{ts,js}` scan finds it, so `opencode.json` is never touched, and every other file in those directories stays the user's.
- **Shape.** Plain `.js` importing only `node:` built-ins (the desktop sidecar runs plugins under Node, not Bun), with one default export and no helper file beside it. Line 1 is the sentinel as `// …`. It is rendered from a packaged template whose one placeholder is replaced (`str.replace`, never Jinja) by `REG`, a JSON table `{event: {timeout_ms, tools}}` whose strings all come from closed vocabularies (canonical event names, OpenCode's V1 tool names, `*`), never from a hook author.
- **Events.** `tool.execute.before` → `pre_tool_use` (deny, ask → deny, context deferred into the tool result), `tool.execute.after` → `post_tool_use` (context), `experimental.chat.system.transform` → `session_start` (context, degraded: an experimental API), and `session.idle` → `stop` (degraded, evidence-only: the findings ride into the next turn, since `session.idle` cannot block). `pre_compact` has no V1 hook, so it is never registered; other events reach OpenCode only as `AGENTS.md` text.
- **Spawning.** Each event spawns the pinned interpreter (`<git-dir>/playbook-hooks/interpreter`, as for the Claude Code launcher, §10.3.2) as `<pin> -I -m coding_agent_playbook.hook_runtime dispatch <event> --harness opencode --project-dir <repo root>` (the repo root taken from the shim's own location), kills it at the registration's `timeout_ms`, and throws — blocking the tool call — only on dispatcher exit 10 or a `deny` decision. Every harness-level failure (no pin, a crash, a timeout, unparseable output) fails open and says so once per process.
- **Restart.** V1 has no plugin hot reload: when the shim's lock entry changes, write-mode `playbook sync` prints `! .opencode/plugins/playbook-hooks.js changed: restart OpenCode to load it` (or `removed: restart OpenCode to unload it`). A `guard_config.json` change needs no restart.
- **OpenCode V2.** The default export also carries an inert `setup()` stub, so OpenCode V2 loads the file without error and logs that the lifecycle hooks are inactive (the `AGENTS.md` Guardrails section stays the instruction). The shim is ported when V2 becomes OpenCode's default installer (OQ-11).
- **Ownership.** The shim is a `runtime_outputs` file (`kind = "runtime"`, §14.4): gitignored under `[output] commit = false`, committed under `true`. `stale_outputs` checks that one path only, never walking `.opencode/plugins/`, and reports it only when it carries the sentinel, is reached without a symlink and was not written this sync. `finalize` writes it the same way the launcher is written (§10.3.2): only over nothing or a file with the `// …` sentinel on line 1. A plugin of the user's with that name, anything that is not a regular file, a hard link, or a symlink at the path or at `.opencode` / `.opencode/plugins` is refused before any adapter writes — write mode exits 1 with `error: playbook sync stopped; .opencode/plugins/playbook-hooks.js was not changed.`, `--check` prints `Cannot verify .opencode/plugins/playbook-hooks.js: <reason>.` and exits 1 — and is never overwritten. With no hook OpenCode enforces, nothing is written, so such a file is not checked either.
#### 10.6.3 Agents gap (out of scope for v1)
OpenCode supports named agents (`build`, `plan`, custom modes) with their own model and permission overrides, defined in `.opencode/agent/<name>.md`. The canonical artifact model has no concept of named agents in v1. Users wanting custom OpenCode agents write them by hand. See open question 9.
#### 10.6.4 What the OpenCode adapter does NOT touch
To make the boundaries explicit, the OpenCode adapter writes only `.opencode/command/`, `.opencode/skills/` and the one shim file `.opencode/plugins/playbook-hooks.js`, and its own `cleanup_stale` scans only `.opencode/command/` plus that one shim path (stale `.opencode/skills/` output is settled by the lockfile leftover policy, §4.2 step 9). In `.opencode/skills/` it writes only engine-owned skill dirs — a hand-written skill dir whose name collides with a canonical skill id is skipped with a warning, never overwritten. It does **not** write or modify:
- **`.opencode/agent/`** — out of scope; users own custom agents.
- **`.opencode/plugin/` and `.opencode/plugins/`** — users own every plugin there except the one generated shim, `.opencode/plugins/playbook-hooks.js` (§10.6.2), which the adapter writes only with hooks on, never as a directory, and never over a same-named plugin of the user's or through a symlink (sync stops instead, §10.6.2).
- **`opencode.json`** — out of scope; users own MCP server config, permissions, model selection, and the `instructions` array.
- **`AGENTS.md`** — owned by the AGENTS.md adapter; OpenCode reads it natively.
- **`.claude/` (incl. `.claude/skills/`)** — owned by the Claude Code adapter, and **`.agents/skills/`**, owned by the `shared_skills` adapter. OpenCode may also discover skills there; duplicates are safe (see above).
This deliberate minimalism keeps the OpenCode adapter small and avoids stepping on user-owned config.
### 10.7 Agent Harness adapter
The `agent_harness` adapter renders canonical artifacts into a [Agent Harness](https://agentharnesses.io/specification) tree — a `HARNESS.md`-rooted format consumed by harness clients. Unlike the five built-in adapters it is **opt-in**: it is not in the default adapter set and is not force-enabled like `agents_md`. Enable it by listing `agent_harness` in the top-level `adapters_enabled` list (§7.1). It is discovered through the same entry-point mechanism (§10.5); the engine never constructs it directly.
```python
class AgentHarnessAdapter(Adapter):
    name = "agent_harness"
    # Buffers write_rule/write_prompt/write_skill, then composes the whole
    # tree in finalize() so HARNESS.md can index everything that was emitted.
    # Accepts an optional rule_registry to append a prompt's includes_rules
    # as a ## Reference rules appendix (render_inline_prompt_markdown).
```
#### 10.7.1 Emitted tree
The adapter emits a harness tree under the repo root (`specs/prH-agent-harness.md` §B):
```
<repo-root>/
├── HARNESS.md                  # name/description (repo-derived) + dir index +
│                               #   "Always consult these" pointer at scope=always rules
├── .leaf-detectors             # "skill=SKILL.md" — written only when a skill/prompt leaf exists
├── skills/
│   ├── SKILLS.md               #   routing file (description-only frontmatter)
│   └── <id>/
│       ├── SKILL.md            #   name + description + body
│       ├── scripts/            #   ← Skill.scripts_dir, byte-copied verbatim (shutil.copy2)
│       └── references/         #   ← Skill.references_dir, byte-copied verbatim
│                               #   (both minus bytecode caches, §10.8)
├── prompts/
│   ├── PROMPTS.md
│   └── <slash>/SKILL.md        #   skill-shaped leaf; includes_rules as an inline appendix
├── rules/
│   ├── RULES.md
│   └── <priority:02d>-<id>.md  #   scope=always rules; frontmatter = description only
├── references/
│   ├── REFERENCES.md
│   └── <id>.md                 #   scope=scoped rules; frontmatter = description only
└── .playbook/                  # round-trip sidecar (dotfile; harness clients skip it)
    ├── manifest.toml           #   full canonical reconstruction payload (§20.10)
    ├── hooks/<id>/             #   hook sidecar: HOOK.md (+ byte-copied scripts/), v0.20
    └── .harnessleaf            #   terminal marker so clients treat .playbook/ as opaque
```
#### 10.7.2 Canonical → harness mapping
| Canonical type | Harness destination | Native fields on the leaf |
| --- | --- | --- |
| `Skill` | `skills/<id>/SKILL.md` (+ `scripts/`, `references/`) | `name`, `description`, body, copied script/reference bytes |
| `Prompt` | `prompts/<slash>/SKILL.md` (skill-shaped leaf) | `name`, `description`, the titled body, its `includes_rules` as a `## Reference rules` appendix (`render_inline_prompt_markdown`, §9.7) + an input-variables note; no `## Before you start` block, since the tree's scoped rules are top-level `references/<id>.md` files, not skill references |
| `Rule` (scope=always) | `rules/<priority:02d>-<id>.md` | `description`, body |
| `Rule` (scope=scoped) | `references/<id>.md` (one file per scoped rule, member rules included: the harness tree has its own `references/` and composes no skills from rules) | `description`, body; the owning `skill` is recorded in `manifest.toml` (§20.10) |
| `Hook` (v0.20) | `.playbook/hooks/<id>/HOOK.md` (+ `scripts/`), and `rules/30-guardrail-<id>.md` when its body is not blank | none: the harness spec has no lifecycle-event concept, so the sidecar is opaque and the rule file is advisory text (`description` + the `hook_advisory` body) |

`scope=always` rules go to `rules/` and `HARNESS.md` adds an "Always consult these" section instructing the agent to read them every session — keeping the root body small and spec-idiomatic. The harness rule file emits **only** `description`; the rule `name` and every other non-native field round-trip via the sidecar (§20.10).

**Hooks are advisory here (v0.20).** The Agent Harness spec defines no lifecycle event, so `agent_harness` has an empty `hook_support` and only ever degrades a hook. `write_hook` buffers every on hook, and `finalize` emits two things per hook. The **sidecar**, always: `.playbook/hooks/<id>/HOOK.md` with the canonical frontmatter, the sentinel as its first body line and the un-rendered body, plus the hook's `scripts/` byte-copied with their exec bits, recorded in `manifest.toml` as kind `"hook"` (§20.10); `.playbook/` carries `.harnessleaf`, so clients and `playbook validate-harness` treat it as opaque, and a hook script is never exposed as a skill script. The **advisory**, only for a non-blank body: `rules/30-guardrail-<id>.md`, listed in `RULES.md` and under `HARNESS.md`'s "Always consult these", with no manifest entry, so a lossless `playbook import-harness` rebuilds the hook from the sidecar and never imports the advisory as a spurious `Rule` (§12.9). Without the sidecar, the importer reads `rules/NN-guardrail-*.md` as a rule and warns that the hook cannot be reconstructed.

**Eval tasks are not emitted.** The `Adapter` ABC has no eval hook — `sync` only dispatches `write_rule` / `write_prompt` / `write_skill` / `write_hook` / `finalize` — so eval tasks are authoring-only and never reach any adapter. The `agent_harness` adapter therefore never writes an `evals/` directory, exactly like the five built-in adapters. (The importer in §12.9 can still *read* a foreign `evals/` directory.)
#### 10.7.3 Sentinel placement and cleanup
A harness parser requires frontmatter to start on line 1 (`^---`), so the playbook `SENTINEL` cannot be line 1. The adapter writes it as the **first body line** (an HTML comment, after the closing frontmatter fence) on every generated text file — one of the two anchored positions `generated_output.sentinel.has_sentinel` accepts (§4.3), so its cleanup recognises engine output exactly like every other adapter's scanner: an exact sentinel line on line 1, or on the first body line after a leading frontmatter block. A user file under `skills/`, `prompts/`, `rules/` or `references/` that merely quotes the sentinel (in prose, a code block, or any later line) is user-authored and never deleted. Its scan (the read-only `stale_outputs`, which `cleanup_stale` deletes and `sync --check` reports) compares against the written set by file identity (a case-only id rename on a case-insensitive filesystem never deletes the file just written). Files without a sentinel are user-authored and never deleted. The scan also covers every `.playbook/hooks/<id>/HOOK.md` (sentinel-tagged); copied hook scripts carry no sentinel and are settled by the lockfile leftover policy (§4.2 step 9). `cleanup_stale` never deletes inside a skill directory (`skills/<id>/` — its `SKILL.md`, scripts and references): like every native skill root, stale skill output there is settled only by the lockfile leftover policy (§4.2 step 9), so a user-edited script is kept; `skills/SKILLS.md` and the `prompts/`, `rules/`, `references/` and root files are still cleaned here. The `HARNESS.md` directory index lists what this render emits, never what happens to be on disk (a leftover or user-owned top-level `skills/` would otherwise change its bytes, and `sync --check`, rendering into an empty scratch dir, would drift forever).
### 10.8 Shared-skills adapter and the `SkillWriter`
The shared-skills adapter (`shared_skills`) writes every canonical skill to the **shared skill root** `<repo>/.agents/skills/<id>/`. Codex reads it natively (`.agents/skills` in every directory from the project root to cwd), and OpenCode v1/v2 scans it as a compatibility root; Claude Code and Continue do not read it (they read `.claude/skills/`). Engines before v0.21 wrote this adapter's copies to `shared_skills/<id>/`, a directory no harness reads; v0.21 moved them where a harness actually looks (specs/prS-skills-context.md D10) and keeps `shared_skills/` as a retired output location (below). Like all generated output it is gitignored and regenerated on each machine by default; it is committed only with `[output] commit = true` (§5.3, §7.1). It is **on by default** (`playbook init` lists it in `adapters_enabled`) but, unlike `agents_md`, **not force-enabled** — remove it from `adapters_enabled` to opt out. `write_rule` / `write_prompt` return `[]` (always rules reach every assistant through `AGENTS.md`; scoped rules travel inside the skills this adapter writes; prompts through the harness adapters). It takes no `rule_registry`, so `discover_adapters` constructs it with no arguments, like `agents_md`.
```python
class SharedSkillsAdapter(Adapter):
    name = "shared_skills"
    output_locations = (".agents/skills/",)
    retired_output_locations = ("shared_skills/",)  # settled by the leftover policy

    def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
        return []  # always rules -> AGENTS.md; member rules -> skill references

    def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
        return []  # prompts -> harness adapters

    def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
        return SkillWriter(Path(".agents") / "skills").write(skill, repo_root)
```
**The `SkillWriter`** (`adapters/skill_dirs/writer.py`) is the single source of truth for a native skill directory; `claude_code` (`.claude/skills`), `opencode` (`.opencode/skills`) and `shared_skills` (`.agents/skills`) each hold one, differing only in the repo-relative root, so a skill is **byte-identical in every root**.
- **Retired location.** `retired_output_locations = ("shared_skills/",)` (§10.1) keeps the pre-v0.21 root a deletion bound and prune boundary, in write mode and `--check`, until 1.0. The first sync after an upgrade writes `.agents/skills/<id>/`, deletes every `shared_skills/` file the previous lockfile lists whose bytes still match and that git does not track, prunes the emptied tree (`shared_skills/` itself is a real directory as spelled) and swaps `/shared_skills/<id>/` for `/.agents/skills/<id>/` in the managed `.gitignore` block. Edited or tracked files are kept and stay owned (in the lockfile and, under `commit = false`, in the block); under `commit = true` they are listed on stderr (`note: kept output …`). A file no lockfile lists, such as a hand-written `shared_skills/<id>/`, is never touched. The location is not current output, so `guard_config.json`'s `generated` path class lists `.agents/skills/` and never `shared_skills/`. While an enabled adapter is missing (a listed `codex` included, §12.2) every leftover is kept and the cleanup waits.
- **No loose file in a skill root.** Every path an adapter writes under `.claude/skills/`, `.opencode/skills/` or `.agents/skills/` is `<root>/<id>/<…>`: OpenCode v2 loads any root-level `*.md` in a skill root as a skill, so a loose file there would be a phantom skill. The invariant is structural and pinned by tests, with no runtime guard: `ensure_path_safe_skill_id` accepts one relative segment, the writer refuses a skill directory resolving outside its root and writes only `SKILL.md`, `scripts/**` and `references/**` inside it, and the validate gate refuses ids that break the Agent Skills name rule before any write. `agent_harness`'s `skills/SKILLS.md` is the one engine file directly inside a skills-like directory, and `skills/` is not a harness skill root: do not point `.agents/skills`, `.claude/skills` or `.opencode/skills` at it.
- **Member references.** For a skill with member rules (§6.3.3) the writer also writes one `references/<rule-id>.md` per `MemberReference`, from its `text` (the `skill_reference` format, §9.7), in the same `<root>/<id>/` and with the same bytes in every root, and the `SKILL.md` it writes carries the composed description and the generated `## References` index (`skills.document.emitted_frontmatter` / `emitted_body`). The `playbook:` block is never emitted. A rendered reference is recorded as `kind = "rule"` with its rule id (§14.4), so ownership and leftovers work exactly as for a copied reference.
- **Write.** `<root>/<id>/SKILL.md` (frontmatter on line 1 with `name` = id, the sentinel HTML comment as the first body line, then the body) plus byte-copies (`shutil.copy2`, copies not symlinks — source symlinks are dereferenced, exec bits preserved) of the canonical `scripts/` and `references/` subtrees. Two kinds of source file are never copied, each named in a stderr warning (and by `playbook validate`): a secret path (§17.3), judged by its name in the skill *and* by where it resolves, so `scripts/notes.txt -> ~/.aws/credentials` is not published under an innocent name; and a file whose real location lies outside the skill's own source directory (a link leaving it). Links that stay inside the skill are copied. The same filter (`adapters/_skill_sources.py`) applies to the `agent_harness` skill copies. Returns every file written.
- **Bytecode caches are never copied.** Any path under `scripts/` or `references/` with a `__pycache__` component, and any `*.pyc`/`*.pyo` file, is skipped silently (`adapters/_skill_files.py`, the walk the secret/link filter above starts from, shared with the `agent_harness` adapter's `skills/<id>/` copy, so such a file is never written, listed in the lockfile or recorded in `.playbook/manifest.toml`). They are interpreter-tagged by-products: `pip install` byte-compiles the `.py` scripts a bundled plugin ships, and importing a script in-process writes `scripts/__pycache__/`; copying them made the output depend on how and under which Python the engine was installed. A cache an earlier engine synced is settled as a leftover (§4.2 step 9). Nothing else is skipped — a dot-file may be authored content.
- **Path safety.** Non-path-safe ids (separators, `.`/`..`, NUL, drive/absolute) raise `ValueError` with the offending value; a destination under a symlink leading out of the skill directory is skipped with a stderr warning before anything is created — never written through, never a crash, the user's link left alone, the rest of the skill still written (`link_leaving`; until v0.20 it was a `ValueError` that stopped `playbook sync` with a traceback) — and so is a `<root>/<id>` that is itself a link leading out of the skills root, in every mode. A symlink sitting at a destination file is replaced, never written through. `sync --check` names a link leading out of a skill directory in its `Missing on disk:` hint (§12.3).
- **Ownership before writing.** `write` claims `<root>/<id>/` only if it is absent, an empty directory, engine-owned (sentinel), or a real directory whose `SKILL.md` the previous sync's lockfile lists **with unchanged bytes** (pre-v0.15 output). Anything else — a hand-written skill dir with a colliding id, a symlinked dir or `SKILL.md`, a plain file, a listed `SKILL.md` the user has since rewritten (an adopted leftover, which the lockfile keeps listing as a kept orphan, or a stripped sentinel) — is skipped with a stderr warning and returns `[]`, so its files are never overwritten. A skills root that cannot hold directories (a dangling symlink, a plain file) is skipped with a warning too, never a crash. Inside a claimed dir an existing destination file or symlink is unlinked before writing (never written through, so a read-only copy from an earlier sync cannot fail the rewrite), as is a symlink where a parent directory must go. A file/folder swap — a regular file where a parent directory must go, or a real directory where a file must go — is displaced only if every file it holds is one the §4.2 step 9 leftover policy would delete (listed in the previous lockfile, bytes unchanged, untracked by git, inside a declared output location, every adapter installed): write-mode `sync` installs that very policy around its render (`skill_dirs.ownership.judging_leftovers_with`), displaced files count as `removed`, and outside `sync` nothing is displaced. Anything else (a user file, an edited or tracked copy, a symlink) vetoes it, and that one destination is skipped with a stderr warning (`--check` then reports it missing, naming the blocker, until the user moves those files). Only files are ever recorded as written.
- **Check modes decide ownership against the real tree.** `playbook sync --check`/`--check-staged` render into an empty scratch dir, but inside `deciding_ownership_against(repo_root)` the writer judges `<root>/<id>/` (and the legacy lockfile claim) on the real repo, so the render skips exactly the dirs write mode skips: a colliding hand-written dir is neither false drift nor "generated output" to the staged-output guard.
- **Case-only id renames.** On a case-insensitive filesystem (default macOS APFS, Windows), an engine-owned `<root>/<Old>/` that *is* `<root>/<old>/` is renamed to the new spelling before writing, so the directory keeps matching the emitted `name`.
- **No cleanup in the writer.** `<root>/<id>/` is engine-owned iff it is a real directory whose `SKILL.md` (a regular file) carries the sentinel at an anchored position (`generated_output.sentinel.has_sentinel`, §4.3: the exact sentinel line as its first body line) — a hand-written `SKILL.md` that merely quotes it is the user's, and a binary or undecodable one never crashes the check (it is user-owned). The writer and the adapters' `cleanup_stale` never delete stale skill files: a skill dir mixes engine output with files a user may have edited or added, so stale output there is settled only by the lockfile leftover policy (§4.2 step 9) — deleted only if the previous lockfile lists it, its bytes still match, git does not track it, it lies in a declared output location and every enabled adapter is installed; directories left empty are pruned (the skill dir, then an emptied skills root — never above it, and never the target of a symlinked root). A file the engine never wrote is never deleted, even inside an engine-owned dir, and directories without the sentinel are user-authored and **never touched**.
- **Upgrade note.** `.claude/skills/<id>/` directories written before v0.15 carry no sentinel. A skill still present after upgrading is re-claimed through the lockfile (its `SKILL.md` is listed there with the bytes the old engine wrote; one edited since stays the user's), gains the sentinel, and its stale engine-written files are settled by the leftover policy from then on. A skill deleted *before* upgrading is never written again, so it is left in place (treated as user-authored); delete it by hand once.
## 11. Overlay system
### 11.1 Three layers
The artifact list is built by merging three sources in order:
1. **Engine content** (`catalog/core/` in the engine repository, shipped in the wheel; located only by `catalog.roots.catalog_root`, Section 20.3). Generic, open-source, organization-neutral.
2. **Overlay packages** (e.g. `playbook_rules_bnp/resources/`) and **bundled plugins** (`catalog/plugins/<name>/`, Section 11.5). Each enabled overlay contributes additional artifacts and can override engine artifacts by ID. Overlays are applied in the order listed in the top-level `overlays_enabled` key (§7.1); each overlay package must be importable and ship a `resources/` directory, while a bundled-plugin name is checked against `catalog/plugins/<leaf>/` and never imported (§4.2 step 1).
3. **Repo-local** (`<repo>/playbook/`). The consumer's own customizations, with the same subdirectory shape as the engine's `catalog/core/` — i.e. `<repo>/playbook/rules/`, `<repo>/playbook/prompts/`. Always wins on ID collision. The `resources/` subfolder used by overlay packages is dropped here because consumer repos are not Python packages and don't need the extra nesting.
### 11.2 Merge semantics
For each artifact ID across all layers:
- If only one layer defines it, use it.
- If multiple layers define it, the later layer wins (overrides). The original is not merged; it is replaced.
- If a layer wants to *extend* rather than *replace*, it ships an artifact with a different ID (e.g. `python-typing-banking-extras`) and relies on both being loaded.
- Skill membership is resolved after the merge, so a rule's `skill:` names the winning skill of that id, and an override of a skill keeps its member rules (§6.3.3).
- **Hooks are the one exception** (v0.20): an overlay's same-id hook replaces the definition but may only add to it, and builtin handler config merges key by key across layers (Section 11.6).
This is intentionally non-magic. We considered Jinja-based block inheritance across layers and rejected it as too implicit — the user reading `playbook render --show-source python-typing` should see exactly one source file.
### 11.3 Example
Engine ships:
- `python-typing` (always-on, generic)
- `fastapi` (scoped)
Overlay `playbook-rules-bnp` ships:
- `python-typing` (overrides — adds BNP-specific typing requirements like Pydantic field-level validators on PII fields)
- `banking-pii-handling` (new, always-on)
Consumer repo `playbook/` ships:
- `risk-models-glossary` (new, always-on)
Result: 4 active artifacts. The engine's `python-typing` is shadowed by BNP's version. The user can see this via `playbook render --show-source`:
```
$ playbook render --show-source python-typing
Template:  playbook_rules_bnp/resources/rules/languages/python/typing.md.j2
Format:    .md.j2 (Jinja-templated)
Overrides: coding_agent_playbook
```
### 11.4 Authoring an overlay
A minimal overlay package:
```python
# src/playbook_rules_bnp/__init__.py
from importlib.resources import files
from coding_agent_playbook.overlays import Overlay

OVERLAY = Overlay(
    name="bnp",
    version="0.2.0",
    resources_root=files("playbook_rules_bnp") / "resources",
    description="BNP Paribas-specific rules for ML/DS teams",
)
```
```toml
# pyproject.toml
[project]
name = "playbook-rules-bnp"
dependencies = ["coding-agent-playbook>=0.4.0,<0.5.0"]
[project.entry-points."coding_agent_playbook.overlays"]
bnp = "playbook_rules_bnp:OVERLAY"
```
That's the entire integration surface. The overlay then drops its content into `resources/rules/`, `resources/prompts/`, etc., with the same kind layout as the engine's `catalog/core/`. This overlay contract is unchanged by the move of the engine's own content to `catalog/` (v0.19).
### 11.5 Bundled opt-in plugins
A **bundled plugin** (called a *pack* before v0.19) is a directory `catalog/plugins/<name>/` whose kind directories (`rules/`, `prompts/`, `skills/`, `eval_tasks/`, `hooks/`) are layered **exactly like an overlay package's `resources/`** (Section 11.1, layer 2; same ID-collision rule as Section 11.2, and hooks merge additively as Section 11.6 says), but ship **inside the engine wheel**: enabling one needs no extra install, package index, or network access (G5). Bundled plugins are **pure content**. There is no Python file per plugin, so adding `catalog/plugins/<name>/` is all it takes to ship a new one. The leaf rule: `<name>` must be a Python identifier (`str.isidentifier()`) that does not start with `_` or `.`, and the directory must hold at least one kind directory (a content gate in `tests/integration/test_catalog_layout.py` pins both). Bundled plugins are **off by default**. The engine layer never walks them. A consumer opts in by listing `coding_agent_playbook.plugins.<name>` in the top-level `overlays_enabled` key, and `FileSystemArtifactSource` resolves `catalog/plugins/<name>/<kind>/` through `catalog.roots.catalog_layer_root` (Section 20.3). Nothing is imported, and no entry point is involved. Both namespaces, `coding_agent_playbook.plugins.*` and `coding_agent_playbook.packs.*`, are reserved for bundled plugins: a third-party package under either one is not supported. Repo-local artifacts still win on ID collision, so a consumer overrides one plugin skill by shipping `playbook/skills/<id>/`.
Skills from a bundled plugin own no rules: they declare no `playbook:` block, so no rule can name them (V14, §6.3.3). A bundled plugin may still add a rule to a core skill by naming it in `skill:`. Every enabled plugin's skill descriptions count toward the skill-listing budget, which CI caps at 6,000 characters for core plus every bundled plugin on the reference probe (§16.3); §11.5.2's "reconciled with the engine's shipped Python and FastAPI rules" stays true.
```toml
# .coding-agent-playbook.toml (top-level keys, above the first [table] header: the form `playbook init` writes and Config reads)
overlays_enabled = ["coding_agent_playbook.plugins.superpowers"]
adapters_enabled = ["claude_code", "opencode", "shared_skills"]   # the init default
```
Use the top-level keys; they are the only form `Config` reads. Put them above the first `[table]` header: a config `playbook init` wrote without `--overlays` has no `overlays_enabled` line and ends with `[detector_cache.frameworks]`, so a line appended to the end lands in that table. The configuration mistakes this invites are all caught:
- **The table form, a nested key and a misspelled key are refused.** An `[overlays] enabled` / `[adapters] enabled` table (or the dotted `overlays.enabled = …` key), an `overlays_enabled`/`adapters_enabled` key written after a `[table]` header (TOML nests it in that table), or a close misspelling such as `overlay_enabled`, in `.coding-agent-playbook.toml` or `.coding-agent-playbook.local.toml`, is a `ConfigError` naming the file (and the table) and showing the top-level line to write instead, above the first `[table]` header (§7.1). Every command that loads the config exits 2 with `error: …` before writing or deleting anything, so a repo already synced with a bundled plugin keeps its skills, lockfile and managed `.gitignore` block byte-identical (pinned for every sync mode by `tests/cli/test_config_errors.py`). (Before this check the table form read as two empty lists: `sync` exited 0, rendered only `AGENTS.md`, and settled every other adapter's output as leftovers.)
- **A misspelled bundled-plugin name is caught by every command**, through the one shared check `validation.preflight.unusable_overlays` (§4.2 step 1). Its `_unusable_reason` classifies each listed name in this order, importing nothing for the first two. (1) A bare plugin namespace, `coding_agent_playbook.plugins` or `coding_agent_playbook.packs` (`catalog.roots.is_plugin_namespace`), is refused with the fixed reason `the bundled plugin namespace, not a plugin`; because it is never imported, a leftover `src/coding_agent_playbook/packs/` holding only gitignored `__pycache__/` cannot change the result. (2) A bundled layer (`catalog.roots.is_bundled_layer`: the engine package, or a name under either plugin namespace) is checked against the catalog tree and never imported: it is usable when `catalog_layer_root(name)` resolves — the engine to `catalog/core/`, a plugin name to `catalog/plugins/<leaf>/` only when its canonical name is exactly one of `catalog.roots.bundled_plugins()` — and otherwise the reason is `no such bundled plugin`. (3) Every other name is an overlay package and keeps the import check: it is imported, as rendering's `importlib.resources.files` does, so a package that raises at import time is reported with its error (`not importable (RuntimeError: …)`, likewise a missing dependency of the overlay) instead of crashing the command with a traceback, and one that imports but ships no `resources/` directory (a plain module such as `json`, say) is unusable too; artifact discovery skips such a package like a missing one, so only this check names it. Every `playbook sync` mode refuses with an `error:` naming each unusable overlay package or bundled plugin and its reason, one per line, and writes nothing — write mode, `--check` and `--check-staged` (the last only under `commit = false`, where it is not a no-op, §12.3.1). `playbook validate` reports each as a validation error (exit 1, §12.6); `playbook check` flags each under `Overlays:` and no longer reports a clean state (exit 0, §12.4); `playbook init` refuses them before writing any file (exit 2, §12.1) — from `--overlays`, or from the local file's `overlays_enabled`, which replaces it. A name that reads like a mistyped bundled plugin (it starts with the engine package, or its last segment is close to a plugin's leaf) gets the bundled-plugin list, ` (bundled plugins: <comma-separated sorted dotted names>)` from `catalog.roots.bundled_plugins()`: `coding_agent_playbook.plugins.superpower: no such bundled plugin (bundled plugins: coding_agent_playbook.plugins.python_design, coding_agent_playbook.plugins.superpowers)`, and `coding_agent_playbook.plugins: the bundled plugin namespace, not a plugin (bundled plugins: coding_agent_playbook.plugins.python_design, coding_agent_playbook.plugins.superpowers)`.

`playbook init --non-interactive --name … --kind … --overlays coding_agent_playbook.plugins.superpowers` writes the top-level form, with the default adapter list.

**The deprecated `packs` alias.** `coding_agent_playbook.packs.<leaf>` keeps working as an alias of `coding_agent_playbook.plugins.<leaf>`. The alias stays through 0.x; its removal will be announced in MIGRATION.md one release ahead.
- **Canonicalization.** `Config.__post_init__` runs `catalog.canonical_overlay_list`: it rewrites `overlays_enabled` to the canonical names, in the same order and with no dedup (listing an overlay twice already walks it twice, the later walk winning), and records the rewritten names in the derived field `deprecated_overlay_names` (`init=False`, `compare=False`, `repr=False`), which `to_dict` never writes. `from_dict`, direct construction and `dataclasses.replace` therefore agree, and the field never goes stale. `canonical_overlay_name` rewrites only a non-empty `<leaf>` after the `coding_agent_playbook.packs.` prefix, so the bare `coding_agent_playbook.packs` is left as it is (and refused by the preflight). Diagnostics (collisions, `check`, `render`, `eval` labels) print the canonical name; the lockfile stores only paths and hashes, so the rename causes no `sync --check` drift.
- **The warning line.** `SyncContext.from_repo` prints exactly one stderr line per deprecated name: `warning: <file>: overlays_enabled: '<old>' is deprecated; use '<new>'`, for example `warning: .coding-agent-playbook.toml: overlays_enabled: 'coding_agent_playbook.packs.superpowers' is deprecated; use 'coding_agent_playbook.plugins.superpowers'`. `<file>` is `.coding-agent-playbook.local.toml` when that file has an `overlays_enabled` key (lists replace whole in the §7.2 merge), and `.coding-agent-playbook.toml` otherwise. Only `from_repo` prints, never `Config` or `SyncContext(...)`, so tests that build one directly stay silent; every command that reads `overlays_enabled` (sync, check, validate, render, eval, and init's final sync) goes through it. The warning is a print, not `warnings.warn`: CLI users never see a `DeprecationWarning`, and pytest runs with `filterwarnings = error`. A typo under the old namespace still warns, recommending the canonical spelling, and the next line is then the preflight error for that canonical name:
```
$ playbook sync
warning: .coding-agent-playbook.toml: overlays_enabled: 'coding_agent_playbook.packs.superpower' is deprecated; use 'coding_agent_playbook.plugins.superpower'
error: overlay package(s) or bundled plugin(s) in overlays_enabled are not usable here:
  coding_agent_playbook.plugins.superpower: no such bundled plugin (bundled plugins: coding_agent_playbook.plugins.python_design, coding_agent_playbook.plugins.superpowers)
Rendering without them would drop their rules and un-ignore their output, so nothing
was written. Fix the name, or install the overlay package where 'playbook' runs.
A pre-commit hook from the engine's .pre-commit-hooks.yaml (language: python) runs in
pre-commit's own venv: list the package under that hook's additional_dependencies, or
use the repo: local + language: system hooks that 'playbook init' writes.
exit code: 1
```
- **`init --overlays`** canonicalizes its arguments with the same helper and prints `warning: --overlays: '<old>' is deprecated; use '<new>'` once per deprecated argument, after the preflight passes, so a typo such as `coding_agent_playbook.packs.superpower` is refused under its canonical name with no warning (exit 2, nothing written). It writes the canonical names, on a first run and on a re-run, so re-running `init --overlays …` is the migration path for the committed file. It does not warn about the local file's list: its final sync's `from_repo` already does.
- **What rewrites the config.** `check --refresh` keeps writing every key except `[detector_cache]` exactly as parsed (§12.5), so a deprecated name in the committed file stays there; for a refresh, `ConfigRewrite.config` is the canonicalized view of `ConfigRewrite.table`. `sync` never rewrites the config, and no command rewrites `.coding-agent-playbook.local.toml`, so the warning is the migration nudge until the user edits the file or re-runs `init --overlays …`.
- **Removed with no shim.** The `coding_agent_playbook.packs` package, its per-pack subpackages and their `PACK_NAME` constants are gone (bundled plugins have no Python file to import). Code that imported `PACK_NAME` lists the dotted string instead. `config/schema.py` maps each item through `canonical_overlay_name` in the fix-it hint for a misspelled `[overlays] enabled`, so the hint never recommends the deprecated name.

**Plugin root files and tooling.** A bundled plugin's `README.md` says what it is and how to enable it, and an `ATTRIBUTIONS.md` at the plugin root credits any third-party source. `README.md`, `LICENSE` and `ATTRIBUTIONS.md` sit at the plugin root, outside every kind directory, so no artifact walk picks them up and sync never copies them into a consumer repo. They are scanned by the self-containment gates like every other plugin file, so they contain no URL; and because they ship in the wheel but are never synced, no bundled artifact may link to one (`tests/integration/test_catalog_layout.py` pins it). A **vendored** plugin (`superpowers`) also ships its upstream `LICENSE` and keeps its whole directory out of `[tool.ruff]` (`extend-exclude = ["catalog/plugins/superpowers", …]`), because vendored text must stay byte-faithful and newer unpinned ruff versions also reformat code blocks inside markdown. A **distilled** plugin (`python_design`, Section 11.5.2) is the engine's own text and code: ruff lints and formats its scripts, at a `py310` `per-file-target-version` (`catalog/plugins/*/skills/*/scripts/*.py`) because skill scripts run in consumer repos on Python 3.10+, and excludes only its markdown (`catalog/plugins/python_design/**/*.md`), whose fenced examples include deliberate "before" code. `catalog/` is outside `[tool.mypy] files` (fixture module names would collide), so mypy needs no exclude for it, and each plugin's own tests type-check its scripts by path. Hatch force-includes `catalog/` into the wheel as `coding_agent_playbook/_catalog/` (Section 5.1), so the plugin's markdown, `LICENSE`, `ATTRIBUTIONS.md`, and scripts ship in the wheel, and the scripts keep their executable mode. The wheel's distribution metadata (`License: Apache-2.0`, `License-File: LICENSE`) describes the engine only. A plugin's third-party license ships as a file inside the package (`_catalog/plugins/<name>/LICENSE`), not in the dist-info metadata.

A bundled plugin's skills are canonical skills like any other, so they render through the same adapters (Section 6.3, Section 10.8) and, under the default `[output] commit = false`, are generated output like any other: the managed `.gitignore` block lists one `/<root>/<id>/` entry per skill directory, and every clone regenerates them (Section 5.3).

**Opting out and overriding.** Removing a bundled plugin from `overlays_enabled` turns everything earlier syncs wrote for it into **leftovers**, which the next write-mode `playbook sync` settles by the lockfile leftover policy (§4.2 step 9, §10.8) under both `[output] commit` settings. A file the previous lockfile lists is deleted only when its bytes still match that entry, git does not track it, it lies inside an installed adapter's declared `output_locations` (§10.1), and every enabled adapter is installed; the directories it leaves empty are pruned, never above a skills root. Generated output is untracked under the default `commit = false`, so each plugin skill directory disappears from every skill root (`.claude/skills/`, `.opencode/skills/`, `.agents/skills/`, and `agent_harness`'s `skills/` when enabled), and a skills root left empty is pruned too. Edited and user-added files are kept:
- A plugin file you edited after it was synced stays engine-owned: it is carried forward in the lockfile and, under `commit = false`, stays in the managed block, until you delete it by hand.
- A file you added inside a synced skill directory (say, notes under `.claude/skills/<id>/references/`, or `node_modules/` under a `scripts/` directory) is not in the lockfile, so it is never deleted, and the directory that holds it is not pruned.
- Under `commit = true`, committed (tracked) skill files are kept as well and listed on stderr (`note: kept output an earlier sync wrote …`) until you `git rm` them.

The plugin's degraded Continue prompts are not skill output. They carry the sentinel on line 1, so Continue's `cleanup_stale` deletes them as soon as the plugin is off, edited or not, tracked or not (under `commit = true` the deletion shows up as an unstaged git deletion), as long as that line is still there (§10.1). Between opting out and that sync, `playbook sync --check` under `commit = false` reports the managed `.gitignore` block as stale (exit 1); it does not list the individual leftovers, and under `commit = true` it reports no drift.

The same policy runs when a repo-local `playbook/skills/<id>/` overrides one plugin skill. The override's `SKILL.md` replaces the plugin's in every skill root, and every unedited, untracked plugin file under `<root>/<id>/scripts/` or `references/` that the override does not ship is deleted, whether the override ships no such directory or only some of its files. `tests/plugins/test_superpowers_sync.py` pins the opt-out across all three native skill roots (and `agent_harness`'s `skills/`), the kept edited and user-added files, and both override cases, in hermetic real git repos.
#### 11.5.1 The `superpowers` bundled plugin
`coding_agent_playbook.plugins.superpowers` (`catalog/plugins/superpowers/`) is a **near-verbatim port** of the Superpowers skills library by Jesse Vincent (repository obra/superpowers, v7.0.0, upstream commit `bb92a77`, MIT). It ships 15 skills and nothing else (no rules, prompts, or eval tasks): `brainstorming`, `diagnosing-superpowers`, `dispatching-parallel-agents`, `executing-plans`, `finishing-a-development-branch`, `receiving-code-review`, `requesting-code-review`, `subagent-driven-development`, `systematic-debugging`, `test-driven-development`, `using-git-worktrees`, `using-superpowers`, `verification-before-completion`, `writing-plans`, `writing-skills`.

The upstream wording is kept. The only edits are the self-containment transformations:
- **Restructure.** Skill sync copies only `SKILL.md`, `scripts/`, and `references/` (Section 6.3.1). Every other file at an upstream skill root moved under `references/` (e.g. `systematic-debugging/root-cause-tracing.md` → `references/root-cause-tracing.md`, `diagnosing-superpowers/prompts/` → `references/prompts/`), and root executables moved under `scripts/` (`find-polluter.sh`, `render-graphs.js`). One file is new: `writing-skills/scripts/package.json` (`{"type": "module"}`), because `render-graphs.js` is ES-module syntax that upstream parsed as ESM only through its repo-root `package.json` (not vendored); the helper stays optional and still needs Node.js + Graphviz where it runs. Every mention of a moved file (links, inline paths, prose, graph labels, the usage comments of `find-polluter.sh` and `render-graphs.js`) points at the new location; inline paths are written relative to the skill directory, as upstream's were.
- **License copies.** Every skill ships `references/LICENSE`, a byte-identical copy of the plugin's `LICENSE`, so the MIT notice travels with each synced skill directory (see Attribution below).
- **Frontmatter.** `id: <dir-name>` is inserted as the first key; `name` and `description` are kept. The one changed description is diagnosing-superpowers', which no longer names the upstream maintainers as the bug report's recipient.
- **Cross-skill references.** `superpowers:<skill>` becomes the plain skill name. All 15 skills ship together, so every reference resolves inside the bundled plugin.
- **No external URLs.** No URL (any `scheme://`, `mailto:`, or `www.` form) remains anywhere in the bundled plugin. Markdown links keep their text as plain text, MDX cards keep their title and body but lose their `href`, and each external image becomes an italic `*(Diagram omitted: <alt text>)*` note. The PR-L link gate (Section 12.6) passes under the strict default allowlist.
- **Upstream-plugin coupling removed.** Text that required installing the upstream plugin or marketplace, relied on its hooks or plugin environment variables, read upstream-repo files not in the bundled plugin, or asked the reader to file issues upstream was removed or minimally reworded. Two short additions keep dropped plumbing usable. using-superpowers' Platform Adaptation list names `references/gemini-tools.md` for Gemini CLI, because upstream loaded that file only through the dropped repo-root `GEMINI.md`. diagnosing-superpowers' skill-timeline prompt and case template explain how to attribute skills that come from a rendered, un-namespaced pack (this engine-authored text keeps the word "pack", so rendered output stays byte-identical across the v0.19 rename).

Dropped, and why:
- **The brainstorming visual companion** (a Node.js server with its HTML/JS assets and start/stop scripts, plus `visual-companion.md`). It needs a JavaScript runtime and a local web server, so it cannot be self-contained.
- **The SessionStart bootstrap hook** that injects `using-superpowers` at session start. The bundled plugin ships skills only — no `Hook` artifact (Section 6.6.7), since lifecycle hooks are opt-in per consumer repo and a content plugin should not switch one on — so `using-superpowers` is discovered like any other skill, by its description.
- **diagnosing-superpowers' upstream issue filing.** The issue-filing reference, issue template, and GitHub-issues workflow step are gone. The skill still writes its local report and, when the goal is a bug report, offers a scrubbed bundle on request.
- **All non-skill repository content**: per-harness plugin manifests (including the repo-root `GEMINI.md`), hooks, docs, tests, and repo-root scripts.

Third-party content: `writing-skills/references/anthropic-best-practices.md` reproduces Anthropic's public skill-authoring best-practices documentation as upstream shipped it. `ATTRIBUTIONS.md` records that it is not authored by Jesse Vincent.

Consumer-repo conventions the skills use (`docs/superpowers/specs/`, `docs/superpowers/plans/`, the `.superpowers/sdd/` runtime workspace) are paths inside the consumer's own repo, not dependencies, and stay verbatim.

**Rendering per adapter.**
- **Claude Code, OpenCode, shared_skills:** native, through the shared `SkillWriter` (Section 10.8), to `.claude/skills/<id>/`, `.opencode/skills/<id>/` and `.agents/skills/<id>/`. The three copies are byte-identical: `SKILL.md` with its frontmatter on line 1 (`name` = id, which the plugin's `id == name` frontmatter already satisfies) and the sentinel HTML comment as the first body line, followed by the vendored body unchanged, plus byte-copied `references/` and `scripts/` (`shutil.copy2` keeps the scripts' executable bit). OpenCode no longer needs `claude_code` enabled, and `shared_skills` is on by default (the `playbook init` adapter list). Each adapter writes only directories it owns: a hand-written `<root>/<id>/` that collides with a plugin skill id is skipped with a warning, never overwritten.
- **Continue:** has no native skills. Each skill degrades to `.continue/prompts/<id>.md` through `Skill.to_prompt`, which carries the `SKILL.md` body but not `scripts/` or `references/`. Reference links and script-driven steps therefore only work under the native adapters. Steps 2–3 of Section 6.3.2 (copying `scripts/` to `.coding-agent-playbook/skills/<id>/scripts/` and adding a helper-scripts note to the prompt) are not implemented: `Adapter.write_skill` only calls `write_prompt(skill.to_prompt())`. The degraded prompts also lack `references/LICENSE`, so a consumer that renders the plugin only for Continue must keep the plugin's `LICENSE` next to them.
- **Agent Harness (opt-in, Section 10.7):** emits `skills/<id>/SKILL.md` (sentinel as the first body line) with `scripts/` and `references/` byte-copied, and records each script's executable flag in `.playbook/manifest.toml`. Enable it through the top-level `adapters_enabled` key.
- **AGENTS.md:** rules only. Skills are a no-op.

**Sibling-skill dependency.** `executing-plans/scripts/task-start` and `task-done` resolve `$(dirname "$0")/../../subagent-driven-development/scripts` and call its `task-brief` and `sdd-workspace`, and `executing-plans/SKILL.md` names `../subagent-driven-development/scripts/…` helpers. This holds because sync writes every plugin skill as a sibling directory under each skill root. A consumer that overrides `subagent-driven-development` must ship `scripts/task-brief` and `scripts/sdd-workspace` in its `playbook/skills/subagent-driven-development/scripts/`: sync removes the plugin's unedited copies of every script the override does not ship (Section 11.5), which breaks executing-plans' scripted flow.

**Attribution.** `catalog/plugins/superpowers/LICENSE` is the upstream MIT text verbatim. MIT requires the copyright and permission notice in every copy, so it ships in the wheel, and the byte-identical `references/LICENSE` in every skill carries it into each synced skill directory (`.claude/skills/<id>/`, `.opencode/skills/<id>/`, `.agents/skills/<id>/`, and the Agent Harness `skills/<id>/`). Continue's body-only prompts are the exception noted above. `ATTRIBUTIONS.md` records the source, version, commit, the indication of changes above, the provenance of `anthropic-best-practices.md`, and a per-skill table. Both are plain text with no URLs.

**Gates.** `tests/plugins/` pins the 15 ids, the 7-script inventory (plus the `package.json` module-type sidecar), and the full `references/` inventory, with every `references/LICENSE` byte-identical to the plugin's. It also pins frontmatter identity (`id` first, `id == name ==` directory name), the synced-entries-only layout, and self-containment: no URL of any scheme anywhere in the plugin (including `LICENSE`, `ATTRIBUTIONS.md`, and `README.md`), no `superpowers:` references, no upstream-plugin markers, and every `references/…` / `scripts/…` path named in a `SKILL.md` or reference file resolving inside the plugin, apart from an explicit allowlist of illustrative examples. Further gates cover executable bits and `bash -n`; an end-to-end opt-in `playbook sync` + `validate` + `sync --check` that checks each synced `SKILL.md` (sentinel body line, then the vendored body), the license copy in every synced skill, that the `.claude/skills/`, `.opencode/skills/` and `.agents/skills/` copies are byte-identical, and each degraded Continue prompt (sentinel on line 1, then the vendored body); an opt-in `agent_harness` sync whose `skills/<id>/` copies carry the sentinel body line, the vendored body and `references/LICENSE`, with every script executable and flagged in `.playbook/manifest.toml`; and the opt-out and override removal described in Section 11.5. `tests/cli/test_validate_links.py` runs the PR-L link gate over the plugin and asserts that the plugin's `skills/` directory resolves, so the gate cannot pass without scanning anything.
#### 11.5.2 The `python_design` bundled plugin
`coding_agent_playbook.plugins.python_design` (`catalog/plugins/python_design/`) ships two Agent Skills for designing and reviewing Python code, and nothing else (no rules, prompts, or eval tasks). Enable it like any bundled plugin: `overlays_enabled = ["coding_agent_playbook.plugins.python_design"]`, or `playbook init --non-interactive --name … --kind … --overlays coding_agent_playbook.plugins.python_design`.

**Distilled, not vendored.** Unlike `superpowers`, nothing in this bundled plugin is upstream text. The design ideas come from a third-party MIT-licensed source, credited only in `catalog/plugins/python_design/ATTRIBUTIONS.md`; every sentence, table, example, code fragment and script was written fresh for this engine, with fresh example domains. Because no text or code is copied, the plugin ships no third-party `LICENSE`, and the skills carry no attribution. The guidance is reconciled with the engine's shipped Python and FastAPI rules: `Protocol` or `Callable` seams by default, with an abstract base class still allowed for shared implementation or a documented extension point; timeouts and bounded, transient-only retries by default, with backoff or circuit breakers only when asked; an unmapped domain error surfaces as HTTP 500; typed records instead of `dict[str, Any]` payloads; and no blanket bans (mixins, ABCs and singletons are judged by fit, not forbidden).

The two skills:
- **`python-design-review`** reviews Python code for design smells, principle violations, and patterns that are missing or over-applied. Its `SKILL.md` carries, inline, when to load it, the scan order, a severity scheme, a smell-to-fix table, a construct-choice table and a table of each pattern's lightest form. `references/` holds the long form: the smell catalog, the design-quality checklist, design principles with GRASP as a responsibility lens, the pattern catalog (recognition signals, lightest-to-heaviest progression, when not to use one, the framework built-in that replaces it, common pitfalls) and the lint guardrails worth enabling. `scripts/` holds two AST scanners:
  - `detect_smells.py [PATH ...]` prints a JSON array of `{"smell", "file", "line", "evidence"}` candidates, sorted by file, line and smell, for twelve smells (`mutable-default-argument`, `isinstance-ladder`, `long-parameter-list`, `boolean-flag-parameter`, `bare-except`, `swallowed-exception`, `deep-nesting`, `long-function`, `method-could-be-function`, `namespace-class`, `type-in-name`, `module-level-mutable-global-rebound`). For `method-could-be-function` it skips base-class overrides, methods marked `@override`, `@abstractmethod`, `@property` or a setter, class and static methods, dunders, and `Protocol` classes. Unparseable files are reported on stderr and skipped; the exit code is 0 even with hits.
  - `lcom4_clusters.py [PATH ...] [--all]` prints `{"class", "file", "line", "lcom4", "clusters"}` for every class whose methods split into more than one cohesion cluster (shared `self` attributes or `self.m()` calls connect methods; stub-only methods, class and static methods, `Protocol` classes and classes with fewer than two methods are ignored), the evidence for splitting a god class.
- **`python-architecture`** structures a Python application into layers with a composition root per entry point, dependency injection, testable seams and a persistence strategy. Its `SKILL.md` carries, inline, the layer model, a table of when a port is worth it versus injecting the ORM session directly, and the persistence decision flow (plain CRUD, repository, CQRS, event sourcing). `references/` holds the long form on layers and the composition root, dependency injection, testability with in-memory fakes, repository and unit of work, CQRS and event sourcing, and a worked FastAPI example written as fenced code in markdown, so the example adds no `.py` file to the skill (its script does; see "Scripts in a consumer repo" below). `scripts/layer_map.py [ROOT] [--layer NAME=dir,…] [--allow NAME=DEP,…] [--root-module NAME] [--json]` maps modules to layers by directory name (`interface`, `application`, `domain`, `infrastructure` by default), lets composition-root modules (`main.py`, `app.py`, `deps.py`, `container.py`, …) import anything, treats imports under `if TYPE_CHECKING:` as type-only, reads a top-level package whose subpackages span other layers (e.g. `api/` holding `routers/`, `domain/`, `db/`) as a container rather than a layer, flags imports of a composition root from below the interface layer, and reports layer flows, forbidden imports and module-level import cycles; it exits 1 on a violation or a cycle and 2 on a usage error (including a `--root-module` that matches nothing, or no Python module to scan).

Every script is stdlib-only, runs on Python 3.10+, never imports `coding_agent_playbook`, exits 2 on a usage error, and prints candidates for the agent to judge, not verdicts.

**Scripts in a consumer repo.** The three scripts are `.py` files, and sync copies them like any skill file (Section 10.8; bytecode caches are never copied): to `.claude/skills/<id>/scripts/`, `.opencode/skills/<id>/scripts/` and `.agents/skills/<id>/scripts/` with the default adapters, and to `skills/<id>/scripts/` under the opt-in `agent_harness` adapter. A tool that discovers files on its own can therefore pick them up. `mypy .` skips dot-directories but does not read `.gitignore`, so the default adapters' copies, all under dot-directories since v0.21, never reach it; it checks only the `skills/` copies of the opt-in `agent_harness` adapter, which are a single copy, so the duplicate-module error that `shared_skills/` plus `skills/` caused before v0.21 is gone. `ruff check .` honours `.gitignore` inside a git repository, so under the default `[output] commit = false` (generated roots in the managed `.gitignore` block) it skips every copy; under `commit = true` it lints every copy, including those under `.claude/` and `.opencode/`. A consumer that runs these tools over the repository root can exclude the generated skill roots, for example with `exclude` under `[tool.mypy]` and `extend-exclude` under `[tool.ruff]`.

**Standing alone.** Continue degrades a skill to its `SKILL.md` body (dropping `references/` and `scripts/`, Section 6.3.2) and `AGENTS.md` drops skills, so each `SKILL.md` is usable on its own: its decision tables are inline, its references are optional depth, and it names its own files only in plain text ("if `scripts/detect_smells.py` exists next to this file, run it") — never as a markdown link. No file in the bundled plugin contains a URL of any scheme, and no skill file contains the name of the source Claude Code plugin or a dependency on another skill or plugin; a reference names a sibling file in plain text. The plugin root's `README.md` and `ATTRIBUTIONS.md` are not skill files: the README calls the directory a bundled plugin but never names the source plugin, and `ATTRIBUTIONS.md` is the one file that credits it.

**Rendering per adapter.** The same as `superpowers` (Section 11.5.1): native and byte-identical under `.claude/skills/<id>/`, `.opencode/skills/<id>/` and `.agents/skills/<id>/` (with `references/` and executable `scripts/`), a body-only prompt under `.continue/prompts/<id>.md`, `skills/<id>/` under the opt-in `agent_harness` adapter, and nothing in `AGENTS.md`. Skills carry no `applies_if`, so once the plugin is on both skills ship to every consumer repo; they load on demand, by their descriptions. Opting out and overriding follow Section 11.5.

**Gates.** `tests/plugins/python_design/test_pack.py` pins that it is a bundled plugin that is off by default and ships exactly the two skills; for each skill, `id == name ==` the directory name, a 1–1024-character description, a plain `SKILL.md` with no Jinja, no markdown link in any `SKILL.md` or reference, and every `references/…` / `scripts/…` path mention resolving inside the same skill; for each script, the `#!/usr/bin/env python3` shebang, the executable bit, Python 3.10 syntax, stdlib-only imports and a clean `mypy --strict --python-version 3.10`; and an end-to-end `playbook init --overlays …` that syncs each skill byte-identically into every native root of the enabled adapters (and nowhere without the overlay; the synced file list is compared unfiltered, so a bytecode cache next to the source scripts that leaked into a root fails it), passes `validate`, `sync --check` and the PR-L link gate, and runs the synced scripts from the consumer tree. `tests/integration/test_resources_self_contained.py` scans every file of the plugin (its `README.md` included) for URLs and source-plugin markers, with only the plugin's `ATTRIBUTIONS.md` exempt from the marker scan. The script contracts have their own unit tests under `tests/plugins/python_design/`, which write their fixtures to a temporary directory.
### 11.6 Hook layers: overlays only add (v0.20)
Hooks follow the three layers of Section 11.1, but not the replace-only rule of Section 11.2: `OverlayResolver.resolve_hooks` hands **every** layer's definition of an id, in layer order (engine, overlays in `overlays_enabled` order, repo-local), to `hook_policy.merge_hook_layers`, because the policy compares each override with what it overrides. Violations are collected and reported by `playbook validate` (H14, H15), and the validate-gated `playbook sync` refuses to render while one stands; resolution itself never raises.

| A layer overriding an earlier definition | Frontmatter | Builtin `handler.config` |
| --- | --- | --- |
| **Overlay** over the engine or an earlier overlay | Replaced by id, but the override may not swap `handler.builtin`, set `enabled: false` on a `default`-tier hook, drop an event, a tool class or a `deny`/`ask` decision, weaken `on_error` (`open` < `ask` < `deny`), or demote `tier`. Promoting `opt-in` or `overlay` to `default` is how an overlay **activates** an engine mechanism. | Merged per the handler's `CONFIG_SCHEMA` key policy (below). |
| **Repo-local** over a non-mandatory hook | Replaced by id: the consumer's choice, as strong as `[hooks] disable`. | Every key `replace`. |
| **Repo-local** over a `mandatory` hook | Refused (H15). | — |
| **Consumer** `[hooks.<hook-id>]` (§7.1.1), applied last | — | Merged with the same key policies as an overlay; a `relax` key is ignored for a `mandatory` hook (sync warns). |

Each key of a builtin handler's config declares one merge policy (`hook_policy.KeyPolicy`):
- `extend` — deny rows, patterns, protected paths: the union, earlier layers first, de-duplicated;
- `strictest` — ordered modes (e.g. `off` < `warn` < `block`): the stricter value wins;
- `relax` — allowlists and exemptions: the union;
- `replace` — messages, caps: the later value wins.

An overlay therefore can never shrink an `extend` key or lower a `strictest` key. A `[guardrails]` domain (§7.1.1) merges into the handlers that declare it with the same policies.

**`mandatory`** (overlay hooks only, and only with `enabled: true`) makes an overlay's hook binding on its consumers: `[hooks] disable` may not name it, a repo-local same-id override is refused, `[hooks] enabled = false` is an error while an enabled overlay ships one, and `PLAYBOOK_HOOKS_DISABLE` does not skip it. The consumer still tunes it through `[hooks.<hook-id>]` and `[guardrails]`, minus the `relax` keys. (`PLAYBOOK_HOOKS=off` still switches every hook off for one machine — the same-UID user can always do that, which is why every guard has an off-workstation twin.)

**Overlays are data-only by default.** An overlay may ship builtin-handler hooks, same-id overrides and handler config freely; an **external-command** hook, from an overlay or from `playbook/hooks/`, runs only when its source package is listed in `[hooks] allow_code_from` and its command and script hash are approved in the user-local trust store (§7.1.1).
## 12. CLI contract
The CLI binary is `coding-agent-playbook`, with a short alias `playbook`. Both names are entry points in `pyproject.toml`:
```toml
[project.scripts]
coding-agent-playbook = "coding_agent_playbook.cli:main"
playbook = "coding_agent_playbook.cli:main"
playbook-hook = "coding_agent_playbook.hook_runtime.cli:main"   # the hook runtime, §12.13 (v0.20)
```
Each subcommand's module declares its flags (`NAME`, `HELP`, `configure`, `run`); `cli` lists them in `_SUBCOMMANDS` order (`cli/parser.py`), and `cli/_command.py` holds the `Command` protocol the modules satisfy structurally, so no command imports `cli`. `init`, `sync`, `validate`, `render` and `eval` still have their flags declared in `cli/parser.py` until they move onto the protocol.

**Missing catalog.** Every command that loads the engine's catalog (`init`, `sync` in every mode, `check`, `validate`, `render`, `eval`) locates it through `catalog_root()`, which raises `CatalogMissingError` when it cannot be found. The error carries every path it tried: the wheel's `<package>/_catalog` (which must hold `core/`) and a source checkout's `<repo>/catalog` (used only when the package directory sits under `src/` and `catalog/core` exists). `cli.main` catches it and exits 2, printing this line to stderr, with the two tried paths as `<a>` and `<b>`:

`error: the engine's catalog was not found (looked in <a>, <b>); reinstall coding-agent-playbook`

Before v0.19 a lookup miss silently produced zero engine artifacts. `playbook init` locates the catalog in its preflight, before writing anything (§12.1), so a broken install never leaves a half-initialized repo. `--version`, `metrics`, `validate-harness` and `import-harness` never look for the catalog, so they still run on such an install.
### 12.1 `playbook init`
Interactive bootstrap for a fresh repo. Safe to re-run: `.coding-agent-playbook.toml` is rewritten from itself — values and unknown keys are kept, comments and layout are not (see *Re-running* below); a file `init` wrote comes back byte-identical for the same answers and detected facts — the local file is never rewritten, and `.gitignore` and `.pre-commit-config.yaml` are merged into, not replaced.
```
$ playbook init
coding-agent-playbook v0.4.0
? Project name: risk-models
? Project description: Counterparty risk scoring service
? Project kind: › python-application
                   python-library
                   ml-research
                   notebook
? Which assistants will the team use? (multi-select)
   ◉ Claude Code
   ◉ OpenCode
   ◉ Shared skills (.agents/skills/: Codex, OpenCode)
   ◯ Continue (opt-in)
? Enable overlay packages? (detected: playbook-rules-bnp)
   ◉ playbook-rules-bnp
? Enable assistant lifecycle hooks? [Y/n]: y
? Docstring style: › numpy
                     google
                     none
? Test layout: › tests/ mirroring src/
                 tests/ flat
                 inline (test_*.py next to source)
✓ Detected Python 3.12 with uv
✓ Detected frameworks: fastapi, pydantic, sqlalchemy, pytest
✓ Wrote .coding-agent-playbook.toml ([output] commit = false)
✓ Wrote .coding-agent-playbook.local.toml (gitignored)
✓ Appended .coding-agent-playbook.local.toml to .gitignore
✓ Wrote .pre-commit-config.yaml (merged with existing)
Install the git hooks with: pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge
✓ Ran playbook sync — generated 12 files, gitignored via the managed block
Next steps:
  - Review generated AGENTS.md, .claude/, .opencode/, .agents/skills/ (local-only)
  - Commit .coding-agent-playbook.toml, .pre-commit-config.yaml, and .gitignore
  - Start your assistant; it reads AGENTS.md and its own directory
```
**Adapters (v0.21).** Without `--adapters`, `playbook init` enables `claude_code`, `opencode` and `shared_skills` (`commands/_init_adapters.DEFAULT_ADAPTERS`); `--adapters claude_code,opencode,shared_skills,continue` opts into Continue, whose upstream is in a maintenance freeze and whose IDE already loads the root `AGENTS.md` and `.claude/skills/` without an adapter of its own (specs/prS-skills-context.md D11). A re-run keeps every committed adapter, so a committed `continue` stays and renders exactly what it rendered before. The interactive question offers the installed `claude_code`, `opencode`, `shared_skills` (the defaults) and `continue`; it no longer offers `codex`, which names no adapter: Codex reads `AGENTS.md` and `.agents/skills/`.

`playbook init` writes `[output] commit = false` explicitly (an existing value is preserved) and picks the playbook hooks for that policy (§13.2/§13.3). It **does not run pre-commit itself**: under `commit = false` it prints the hook-install command, since the auto-sync hook only fires once the `post-checkout`/`post-merge` git hooks are installed: `pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge` (a plain `pre-commit install` does the same when the config carries `default_install_hook_types`, as the fresh starter does). Merging into an existing config can also print a `warning:` (a hand-edited legacy drift hook to delete) or a `note:` (no `default_stages`) on stderr — §13.3.

**Hooks (v0.20).** `playbook init` asks `Enable assistant lifecycle hooks? [Y/n]` and writes the answer as `[hooks] enabled` (§7.1.1), keeping the table's other keys. `--no-hooks` writes `enabled = false` without asking, in `--non-interactive` mode too; a non-interactive run without it keeps a value the config already has, else enables hooks, so a re-run never flips an earlier choice. Engine upgrades never write the key: an absent `[hooks]` table means hooks are off and nothing changes, apart from the one notice line `playbook sync` prints (§12.2). The starter pre-commit config gains `coding-agent-playbook-commit-msg` when the repo opted into commitizen (`[tool.commitizen]` or `[hooks.commit_convention]`) and `coding-agent-playbook-commit-trailers` when a commit-trailer row is configured, each adding `commit-msg` to `default_install_hook_types` (§13.2).

`playbook init` writes the enabled lists as the top-level `overlays_enabled` / `adapters_enabled` keys (§7.1). Before writing **any** file it exits 2 on a usage error: missing `--name`/`--kind` in non-interactive mode, an overlay the sync preflight would reject among those its final sync will use (`error: --overlays names overlay package(s) or bundled plugin(s) that cannot be used here; nothing was written:` followed by one `<name>: <reason>` line each — for a bundled-plugin name, `no such bundled plugin` or `the bundled plugin namespace, not a plugin`, checked against `catalog/plugins/<leaf>/` and never imported; for an overlay package, not importable, with the import error when there is one, or no `resources/` directory; a plugin-like typo lists the bundled plugins, §11.5). It also locates the engine's catalog (`catalog_root()`) in this preflight, next to the overlay check: a broken install exits 2 with the missing-catalog error (§12) and nothing written. `--overlays` accepts the deprecated `coding_agent_playbook.packs.<leaf>` spelling: init canonicalizes each argument, prints `warning: --overlays: '<old>' is deprecated; use '<new>'` once per deprecated argument after the preflight passes, and writes the canonical name, on a first run and on a re-run alike, so a re-run with `--overlays` migrates the committed file (§11.5). It does not warn about the local file's list; its final sync's `SyncContext.from_repo` does. When `.coding-agent-playbook.local.toml` sets `overlays_enabled`, that list replaces `--overlays` for init's final sync (§7.2), so it is checked too, and its error starts `error: overlays_enabled in .coding-agent-playbook.local.toml names overlay package(s) or bundled plugin(s) …`; `--overlays` is still checked, since it is what the committed file gets and every teammate without that local file syncs with it (before v0.18 a local list hid an unusable `--overlays`, which was committed and broke their `playbook sync`). Both lists are reported when both are unusable. A `ConfigError` (§7.1) stops it too, checked in this order before the first write: the local file on its own (up front, with the overlay check: a syntax error, `[output] commit = "yes"` or `project = "x"` there exits 2 naming it); on a re-run, the committed file on its own (a missing required key included — the local file is never allowed to supply one); then the config its final sync will load, i.e. the planned committed file with the local file merged on top (`ConfigFiles.preview`), on a first run too. So nothing is written, and nothing fails in the final sync after the committed files were rewritten.

**Re-running `playbook init`** rewrites `.coding-agent-playbook.toml` from the committed file alone, through `config/committed.plan_committed_update` (`check --refresh` uses its sibling `plan_detector_cache_refresh`, §12.5). The local file is checked but never merged into what is written, so one engineer's `adapters_enabled`, `overlays_enabled`, `[user_choices]`, `[output]` or any other local key never reaches the committed file (§7.2); an existing local file is left untouched. A re-run needs a complete committed file: one missing a required key exits 2 with nothing written, even when the local file supplies the key. What the rewrite does with each key:
- **Replaced** — what `Config` owns, written from the updated committed config and never merged with the old file, so an emptied list or a dropped key stays dropped: the top-level keys in `config_entries.CONFIG_MANAGED_KEYS` — `[detector_cache]` and `[user_choices]` whole, and inside `[project]`/`[engine]`/`[storage]`/`[output]` only the keys `Config` reads (`config_entries.CONFIG_MANAGED_TABLE_KEYS`). `[project]` and `overlays_enabled` take the answers: an omitted or empty `--overlays` removes the key (both mean no overlays), and so does an empty description; `adapters_enabled` keeps the committed list in its order, then appends each answered adapter it lacks; `[detector_cache]` is re-detected, so a stale entry goes. `schema_version`, `[engine] version`, `[storage]`, `[user_choices]` and `[output] commit` keep their committed values (`[output] commit = false` is added when the table is absent, a missing `[storage]` is written with its defaults). Like `Config.to_dict`, the rewrite omits a list or description left empty: an explicit `overlays_enabled = []` or `description = ""` disappears.
- **Preserved** — everything else, with the same parsed values (floats, dates, nested tables and arrays of tables included), carried in `Config.extra_tables`: every other top-level key (`[hooks]`, `[guardrails]`, `[links]`, `[metrics]`, a table a later engine version adds, a key the engine does not know), written after the managed keys, except that `[hooks] enabled` takes the hooks answer above, and the unknown keys inside `[project]`/`[engine]`/`[storage]`/`[output]` (`[project] homepage`), written after that table's own keys.

The file is re-serialized: values survive, comments and layout do not, and a value comes back in the writer's spelling — a hex, octal or binary integer in decimal, a `Z` offset as `+00:00`, an inline table as a `[sub]` table and an array holding only inline tables as `[[sub]]` tables (inside a mixed or nested array they stay inline). The hooks merged into `.pre-commit-config.yaml` (and the hook-install hint) follow the committed `[output] commit`; the final `playbook sync` runs with the merged config, local overrides included.
### 12.2 `playbook sync`
Regenerate all artifacts. The workhorse command. Run automatically by the `post-checkout`/`post-merge` hook under the default `[output] commit = false` (and **once by hand after cloning** — the rendered output is not in the repository); can also be run manually any time.
```
$ playbook sync
✓ Loaded config (engine 0.4.0, overlay bnp 0.2.0)
✓ Detector cache valid (pyproject.toml unchanged since last sync)
✓ Resolved 18 artifacts (3 overlay overrides, 1 repo-local)
✓ Filtered to 14 applicable artifacts
✓ Rendered all artifacts
✓ Wrote 12 files via continue adapter
✓ Wrote 5 files via claude_code adapter
✓ Wrote 5 files via opencode adapter
✓ Wrote 1 file via agents_md adapter
✓ Removed 0 stale files
✓ Updated .coding-agent-playbook.lock
Updated the managed block in .gitignore
Summary: 23 files written, 0 unchanged, 0 removed
```
After the lockfile is stamped, write mode applies the output policy (§4.2 step 9). With `commit = false` it rewrites the managed `.gitignore` block (§5.3) from this run's written paths — printing `Updated the managed block in .gitignore` only when the file actually changed — and then asks git, read-only, whether any generated path (or the lockfile) is **still tracked**, e.g. in a repo migrating from committed output. If so it warns on stderr and prints the exact command to stop tracking them; the exit code stays 0 and the engine never runs it itself:
```
warning: generated output is still tracked by git, but [output] commit = false
keeps it local-only (gitignored). Tracked paths:
  .claude/CLAUDE.md
  AGENTS.md
Stop tracking them (the files stay on disk) with:
  git rm -r --cached -- .claude/CLAUDE.md AGENTS.md
```
The query is `git --literal-pathspecs ls-files -z -- <paths>` (arg-list, no shell, `cwd` = repo root, 10 s timeout) behind the injectable `GitClient` protocol (`sync/git_client.py`; tests use a `FakeGitClient`). Not a git repository, git missing, or a timeout → the warning is skipped silently. Deciding whether a *leftover* is tracked is stricter (§4.2 step 9): it asks with `:(literal,icase)` pathspecs, confirms each match by NFC spelling or file identity, and when git cannot answer inside a git work tree it keeps every leftover — it never reads "unknown" as "untracked". The paths are relative to the repo root, so when that is not the current directory (`playbook sync --repo-root packages/foo` from a monorepo root) the printed command is `git -C <repo-root> rm -r --cached -- …`. Before the block is written, leftovers of an earlier sync are settled from the previous lockfile (§4.2 step 9): pristine, untracked orphans are deleted and counted in `removed`; the rest are carried forward in the lockfile and kept in the block. A `ConfigError` (§7.1) exits 2 before anything runs. If an overlay package in `overlays_enabled` is not importable or ships no `resources/` directory, or a bundled-plugin name matches no `catalog/plugins/<leaf>/` or is a bare plugin namespace (checked without importing anything, §11.5), `sync` prints `error: overlay package(s) or bundled plugin(s) in overlays_enabled are not usable here:` with one `<name>: <reason>` line per entry (plus the bundled-plugin list for a plugin-like typo, §11.5) and the fix (§13.1), and exits 1 before writing anything; a missing adapter is a `warning:` and the run continues. With `commit = true` write mode removes the managed block instead (`Removed the managed block from .gitignore`); it settles leftovers by the same policy (asking git only when there are leftovers to judge) and lists every kept one on stderr (`note: kept output an earlier sync wrote …`), since a committed — tracked — leftover is never deleted. A malformed block (unmatched or duplicated markers) makes `sync` print `error: <file>:<line>: …` and exit 1 after the outputs and lockfile are written, without touching `.gitignore`.
**Something in the way of output** stops write mode with exit 1 instead of a traceback (`sync/_output_blockers.py`), naming it; sync never creates, replaces or deletes it, since it cannot tell whose it is. Four kinds: a dangling symlink on the way (`.claude/commands -> ../tools/cc` with no `tools/cc`), reported with the target the link stores; a non-directory where an output directory goes (a file, or a link to one, at `.claude/commands` or `.continue`); a directory where an output file goes (`AGENTS.md/`); and a FIFO, socket or block device where an output file goes, which the owned writers (`generated_output.output_io.write_output_text` / `write_output_bytes` / `copy_output`, used for every generated file written in place outside a native skill directory; the engine-owned launcher, shim, rules file and stub are refused earlier by the preflight, §10.1) refuse before `open()` would block on the FIFO or fail on the socket. The same guard (`refuse_special_file(…, reading=True)`) runs before the two files sync reads before replacing them, `.gitignore` and `.claude/settings.json`, since reading a FIFO blocks too; there it refuses a character device as well (`/dev/zero` never ends, `/dev/tty` blocks). A character device at an output path is written into as before (`copy_output` writes only the bytes: `copy2` would chmod the device): `AGENTS.md -> /dev/null` discards the output, never blocks, and `--check` counts it as delivered, nothing to compare — except inside a native skill directory, where the skill writer replaces such a link with the real file (§10.8) and `--check` reports it missing:
```
error: .claude/commands is a dangling symbolic link: its target ../tools/cc does not exist
error: playbook sync stopped before finishing.
error: Create the link's target, or re-point or remove the link, then re-run 'playbook sync'.
```
The others read `error: .claude/commands is not a directory, but sync writes generated files inside it` (remedy `Move or rename it (sync never deletes it)`; for a link to a file, `… is a symbolic link to ../NOTES.md, which is not a directory, …` and `Re-point or remove the link`) `error: AGENTS.md is a directory, but sync writes a generated file at that path` (for a link to a directory, `… is a symbolic link to docs, which is a directory, …` and `Re-point or remove the link`) and `error: AGENTS.md is a FIFO, not a regular file, but sync writes a generated file at that path` (or `a socket`, `a block device`). A link loop (`.claude/commands -> commands`) reads `its target commands is a symbolic link loop`, and a link to another dangling link `its target … is itself a dangling symbolic link`. Paths a user's link can make loop are resolved with `os.path.realpath`, never `Path.resolve()`, which raises `RuntimeError` on a loop on Python 3.12 (`generated_output.symlinks.real_path`). Only the errnos a blocker causes (`EEXIST`, `ENOENT`, `ENOTDIR`, `ELOOP`, `EISDIR`, and `ENXIO`/`EOPNOTSUPP` for a special file) are attributed to one, and an existing file at the failing path only for `mkdir`'s `EEXIST`; any other `OSError` (`EACCES`, `ENOSPC`) keeps its traceback. The check runs when a write fails, not as a preflight, so a blocker nothing is written past (a dangling `.claude/skills` with no skills enabled) stops nothing; the run stops part-way, and the next sync reconciles what it wrote. `--check` names the same blocker in its `Missing on disk:` hint (§12.3); when one stops the check itself (it reads the real tree, e.g. a FIFO or a directory at `.gitignore`), it prints `Cannot verify <path>: it <reason>.`, the shape it shares with the owned-file and `settings.json` refusals, which the `drift` Stop stage reads as a `cannot verify` finding for `<path>`. The native skill writer is the exception: it skips a skills root that cannot hold directories with a warning, and inside a skill directory settles a file/folder swap itself (§10.8).
**Hooks (v0.20).** Without a `[hooks]` table, every mode renders byte for byte what v0.19 rendered (apart from the Claude Code rules' move to `.claude/rules/coding-agent-playbook.md`, §10.3.1) and write mode prints one line, `hooks available: add [hooks] enabled = true or re-run playbook init`. With `[hooks] enabled = true`, every mode resolves the on hooks (`hook_policy.resolve_effective_hooks`, §7.1.1), dispatches them to the adapters (§10.1), and writes the sync-level `.coding-agent-playbook/hooks/guard_config.json` and the copied external-handler scripts beside it whenever a hook-capable adapter is enabled. Write mode then, after the `Summary:` line, pins the interpreter (§10.3.2) and prints:
```
✓ Pinned the hook interpreter for this worktree: /repo/.venv/bin/python
✓ Hooks: 30 enabled, 12 skipped (agents_md: 23 advisory; claude_code: 30 enforced; continue: 23 advisory; opencode: 13 enforced, 16 degraded, 1 advisory; shared_skills: 23 advisory)
✓ .claude/settings.json: 9 managed entries updated, 0 removed (user keys untouched)
! .opencode/plugins/playbook-hooks.js changed: restart OpenCode to load it
```
The pin line appears only when the pin is first written; the `Hooks:` counts use the `playbook check` labels (§12.4); the `settings.json` line (with its `note:` lines) only when the merge changed the file; the restart line only when the shim's lock entry changed (§10.6.2). `warning:` lines follow on stderr — a restored hand edit of a managed group, a pinned interpreter in a uv or pipx cache, a `[hooks]` / `[guardrails]` table in `.local.toml` that is ignored (§7.2), hooks outside a git work tree. Last, and only when stdin and stdout are terminals, sync asks the trust questions for pending external handlers and execution Stop stages (`[y/N]` per item, §7.1.1); this is the one interactive `playbook sync` each machine needs. Write mode and `--check` first run the validate gate (§12.6), and a `.claude/settings.json` the merge cannot parse stops write mode before any write (§10.3.2).
### 12.3 `playbook sync --check`
Verify, don't write. Exits non-zero on drift: a generated file that differs or is missing, or an **orphan** — generated output a real `playbook sync` would delete: a sentinel-tagged file an adapter's `cleanup_stale` removes, or a previous-lockfile entry (§14.4) the leftover policy deletes (§4.2 step 9: not regenerated, still on disk, bytes unchanged, untracked, inside a declared output location) — the only record for files without a sentinel (copied skill scripts and references) and for everything in a skill directory. Leftovers that policy keeps (edited, tracked by git, or an enabled adapter missing) stay owned by design and are not orphans, so the hint `run 'playbook sync' to remove` is always true. An unreadable lockfile (merge-conflict markers, a key of the wrong type) is drift too, reported as one line naming the offending key — never a traceback. Under `[output] commit = true` it is the CI and legacy pre-commit check: the output is committed, so a fresh checkout has everything to compare. Under the default `commit = false` the output is **not in the repository**, so `--check` only makes sense in a working copy where `playbook sync` has already run (it then also reports a stale, missing, or malformed managed `.gitignore` block, and a not-yet-settled leftover, as drift; `--check` never writes `.gitignore`). Do not run it on a fresh CI clone under `commit = false` — every generated file reports "Missing on disk"; running `playbook sync` first would make it vacuous. CI for such repos validates the source instead (`playbook validate`). A generated file missing because something write mode stops on is in its way (§12.2) — a dangling symlink or a non-directory on the way (`.claude/commands -> ../tools/cc`, a file at `.continue`), a directory, a FIFO, a socket or a block device at the file's path, or the file itself a dangling link that loops or whose target's directory is missing (`AGENTS.md -> gone/AGENTS.md`; not the co-owned `.claude/settings.json`, which write mode replaces whole by atomic rename) — gets the hint `Missing on disk: .claude/commands is a dangling symbolic link: its target ../tools/cc does not exist.` (or the matching problem) plus the remedy, never a promise that sync replaces it. Only inside `<root>/<id>/` of a native skills root (`native_skill_roots`: `.claude/skills`, `.opencode/skills`, `.agents/skills`; not `agent_harness`'s `skills/`, written plainly) does the hint follow the skill writer instead: a link leading out of the skill directory reads `Missing on disk: .claude/skills/demo/scripts is a symbolic link leading outside the skill directory, and sync never writes through one.` (`Remove or re-point the link`), and a file/folder swap says sync replaces what is in the way when it holds nothing but unchanged files it wrote (§10.8). The link is named even when a file sits behind it with other bytes: sync never writes through it, so `Run 'playbook sync' to regenerate` would never clear that drift. A file write mode skips there can also make `guard_config.json` (hooks on) and, for a link into the repo, the managed `.gitignore` block report drift, until the cause is gone.
```
$ playbook sync --check
Drift detected:
  .continue/rules/50-python-typing.md
    Generated content differs from on-disk content.
    Run 'playbook sync' to regenerate.
  .claude/skills/query-db/SKILL.md
    Orphaned generated file; run 'playbook sync' to remove.
  .gitignore
    Managed block is missing or stale ([output] commit = false).
    Run 'playbook sync' to regenerate.
exit code: 1
```
Implementation: the render reads its inputs (config, detector facts, artifacts, `applies_if` file checks) from the real repo but the adapters write into an **empty** scratch directory named like the repo — nothing from the working tree is copied, so a dangling symlink, an unreadable data directory, a socket/FIFO, or a large `.venv` can neither crash nor slow the check, and the real tree is never written. Skill-dir ownership is decided against the real tree, not the empty scratch (§10.8), so a skill dir write mode skips — hand-written with a colliding id, a symlink, a plain file, an unusable skills root — is skipped in the render too, and nothing the adapters render depends on what else is on disk (the `agent_harness` `HARNESS.md` index lists what it emits, §10.7.3). So after a successful `playbook sync`, `--check` exits 0 — with two documented exceptions inside a skill dir, where `sync` skips a file with a warning (§10.8): a file/folder swap it refused because files it may not delete are in the way (a user file, an edited or tracked copy), and a file under a link leading out of the skill dir. That destination stays missing, and `--check` reports it as `Missing on disk: <blocker> is in the way …`, telling the user to move those files rather than to re-run `playbook sync` (which cannot fix it); under `commit = true` the legacy `playbook-sync-check` hook fails until they do. Scratch paths are mapped back onto the real tree before ignore entries and orphans are computed, so a symlinked output directory (e.g. `.claude/skills -> ../.agents/skills`, or `.claude/commands -> ../tools/claude-commands`) yields exactly the entries and lockfile paths write mode writes — no false orphan. The same mapping feeds `guard_config.json`'s `protected` table (`entries` and `output_dirs`, `_guard_config_protect._lock_path_via_repo_links`), so with hooks on the scratch render names the link's target like write mode does, two adapters' roots on one directory merge into one `composite` row as in write mode (`lockfile.model.merge_provenance`), and the file never reports false drift. The scratch output is then diffed against the repo, and orphans are judged on the real tree, read-only: each enabled adapter's `stale_outputs` (the twin of `cleanup_stale` that deletes nothing) plus the leftover policy's plan, computed exactly as write mode settles it. Because nothing is copied, inputs whose paths look like build output or secrets (a `build` skill, a `*credentials*` rule, a `.env` that an `applies_if: has_file` checks) render as in write mode. The orphan scan reads only what it needs, on the real tree: each file once, never a symlink, never a secret path (§17.3), and only the head `has_sentinel` decides on (line 1, or a leading frontmatter block plus one line, at most 64 KiB). So an output whose own name is secret-classified (`rotate-credentials.md`) is judged by the lockfile leftover policy alone. An orphan reached through an output directory symlinked outside the repo (`.claude/commands -> ../shared-commands`) is reported under its in-repo spelling, since write mode deletes it through the link. A template the Jinja sandbox rejects makes every mode exit 1 naming the source file (§9.3), before any adapter writes.
**Hooks (v0.20).** The hook outputs are rendered into the scratch directory and compared like every other file: the launcher, the shim, `guard_config.json` and the copied scripts byte for byte, plus, on POSIX, `Mode differs: generated as executable.` for a copied script that lost its exec bit. `.claude/settings.json` is the exception: it is re-merged against the **real** file, so it is drift only when its managed projection differs — a managed group edited, deleted or not yet registered — never for the user's keys, hook groups or formatting (§10.3.2). A `settings.json` that cannot be parsed ends the check with `Cannot verify .claude/settings.json: <message> at L:C.` and exit 1. So does a user file or a symlink on the **real** tree where the launcher, the shim or the Claude Code rules file is about to be written, or a symlinked `.claude/CLAUDE.md` stub (`Cannot verify <path>: <reason>.`, §10.3.1, §10.3.2, §10.6.2): the scratch directory is empty, so the ownership check reads the repo, as write mode does. Under `[output] commit = false` the shared `settings.json` is never in the managed block and never flagged by `--check-staged`; the launcher, the shim and `.coding-agent-playbook/hooks/` are local output like the rest.
#### 12.3.1 `playbook sync --check-staged`
The `[output] commit = false` commit guard (pre-commit stage). It renders into an empty scratch directory exactly like `--check` (no writes, no working-tree copy; skill-dir ownership judged on the real tree, so files in a hand-written skill dir are never flagged), asks git for the staged paths — `git diff --cached --name-only -z --relative --no-renames --diff-filter=d`, so staged *deletions* (the `git rm --cached` migration) never trip it — and exits 1 listing every staged path covered by an entry for this render's output **or for any leftover of an earlier sync still on disk** (every orphan in the previous lockfile, pristine or not), including files under a collapsed skill directory. Paths are matched in Unicode NFC on both sides:
```
$ playbook sync --check-staged
Generated output is staged for commit ([output] commit = false keeps it local-only):
  AGENTS.md
  .claude/skills/review/scripts/run.sh
Unstage it (the files stay on disk) with:
  git rm -r --cached -- AGENTS.md .claude/skills/review/scripts/run.sh
exit code: 1
```
Exit 0 when nothing generated is staged, when nothing is staged at all (fast path: no render), when the directory is not a git repository (or git is unavailable), and always under `commit = true` (no-op). Exit 1 with an `error:` (not a staged-path list) when an overlay package or bundled plugin is unusable (§4.2 step 1). A `ConfigError` (§7.1) exits 2 even under `commit = true`: the config is loaded before the no-op decision, and a config the engine would misread must never pass silently. `--check` and `--check-staged` are mutually exclusive.
### 12.4 `playbook check`
Diagnostic dump. No writes. Used to debug "why isn't my rule appearing?"
```
$ playbook check
=== Environment ===
  Python: 3.12.1
  Package manager: uv
  Engine: coding-agent-playbook 0.4.0
  Overlays: playbook-rules-bnp 0.2.0
=== Detected ===
  project_kind: python-application
  frameworks: fastapi=0.115.0, pydantic=2.9.2, sqlalchemy=2.0.35, pytest=8.3.3
  has_notebooks: False
  has_dockerfile: True
  has_ci: True
=== Artifacts ===
  Rules (14 applicable / 18 total):
    [✓] 00-project-context         (engine, scope=always)
    [✓] 10-python-house-style      (engine, scope=always)
    [✓] 20-tooling-baseline        (engine, scope=always)
    [✓] 30-bnp-banking             (overlay bnp, scope=always)
    [✓] 50-python-typing           (overlay bnp OVERRIDES engine, scope=scoped)
    [✓] 60-fastapi                 (engine, scope=scoped)
    [✓] 70-pydantic-v2             (engine, scope=scoped)
    [✓] 70-sqlalchemy-v2           (engine, scope=scoped)
    [✗] 70-notebooks               (skipped: has_notebooks=False)
    [✗] 70-data-validation         (skipped: applies_if has_framework=['great-expectations'])
    ...
  Prompts (5 applicable / 7 total):
    [✓] refactor                   (includes_rules: [python-typing])
    [✓] generate-tests             (includes_rules: [python-typing, pytest])
    [✓] review                     (includes_rules: [python-typing, python-error-handling])
    [✓] explain
    [✓] pii-scan                   (from overlay bnp; includes_rules: [pii-handling])
    [✗] tdd-cycle                  (skipped: applies_if has_framework=['hypothesis'])
    ...
=== Drift ===
  All on-disk files match generated output ✓
```
Each overlay in `overlays_enabled` that `playbook sync` would refuse (the shared `validation.preflight.unusable_overlays` check, §4.2 step 1: an overlay package whose import fails or that has no `resources/` directory, or a bundled-plugin name that matches no `catalog/plugins/<leaf>/` — checked without importing anything — or is a bare plugin namespace) is flagged right under the `Overlays:` line, one `✗` line each, and the Drift section then never claims a clean state — a lockfile that matches the disk only describes what the last sync wrote, and no sync can run now:
```
  Overlays: coding_agent_playbook.plugins.superpower
    ✗ coding_agent_playbook.plugins.superpower: no such bundled plugin (bundled plugins: coding_agent_playbook.plugins.python_design, coding_agent_playbook.plugins.superpowers)
    'playbook sync' refuses to run until every overlay in overlays_enabled is usable; the artifacts below omit the unusable ones.
…
=== Drift ===
  On-disk files match the lockfile, but the state is not clean:
  'playbook sync' refuses to run until every overlay in overlays_enabled is usable (see Environment).
```
`playbook check` is a diagnostic: it exits 0 whatever it reports, drift included, as before; `playbook validate` (§12.6) and `playbook sync` are the gates that exit non-zero. A `ConfigError` (§7.1) is the exception — the config cannot be loaded, so `check` (and `check --refresh`, which then writes nothing) exits 2 with `error: …`; §12.5 adds the cases where only `--refresh` refuses.
**Hooks block (v0.20).** Between `=== Artifacts ===` and `=== Drift ===`, `playbook check` prints the `[hooks]` switch and every hook the sources define, by id. An on hook is labelled per enabled adapter from that adapter's `hook_support` and the hook's events and `supports` — `enforced`, `degraded` (registered there, with a gap: an unreachable or degraded event, or a tool class the harness lacks), `advisory` (text only) or `—` (neither: not registered there and no advisory body) — so advice is never mistaken for enforcement; an off hook gives its reason:
```
=== Hooks ===
  [hooks]: on
  Hooks (29 on / 43 total):
    [✓] block-precommit-bypass (agents_md: advisory, claude_code: enforced, continue: advisory, opencode: enforced)
    [✓] session-start-playbook-briefing (agents_md: advisory, claude_code: enforced, continue: advisory, opencode: degraded)
    [✗] coverage-diff-gate (skipped: tier 'opt-in' is not in [hooks] tiers ['default'] and [hooks] enable does not name it)
=== Drift ===
  managed entry edited: .claude/settings.json#/hooks/PreToolUse
  mode mismatch: .coding-agent-playbook/hooks/scripts/bnp-sql-pii-columns/check.py (expected executable)
```
Without a table the switch reads `off — no [hooks] table (add [hooks] enabled = true or re-run 'playbook init')`. The Drift section reads the lockfile's scoped entries too: for each `json:<pointer>` entry it parses the shared file and looks for an element under the pointer whose canonical hash matches, printing `managed entry missing: <path>#<pointer>` or `managed entry edited: <path>#<pointer>`, and `unreadable: <path> (<why>)` when the file cannot be parsed; user edits elsewhere in the file are never drift. An `executable` entry whose file lost its exec bit is `mode mismatch:` (POSIX only).
### 12.5 `playbook check --refresh`
Re-runs the detector and writes the fresh facts back to `.coding-agent-playbook.toml`, prints `Refreshed detector_cache in .coding-agent-playbook.toml.`, then the §12.4 report. Use after adding a dependency.

It rewrites only `[detector_cache]` (whole, so a stale entry goes; appended when absent), from the committed file alone (`config/committed.plan_detector_cache_refresh`). The committed table is written back as parsed with that one entry replaced — not through `Config`, as an `init` re-run does — so every other key, managed or not (`adapters_enabled`, `[output]`, `[user_choices]`, `[links]`, `[metrics]`, `[project] homepage`, …), keeps its committed value as written: an explicit `adapters_enabled = []`, `description = ""` or empty `[user_choices]` stays, and a partial `[storage]` or an `[output]` without `commit` is not filled in. Nothing from `.coding-agent-playbook.local.toml` is written (§7.2). Before v0.18 it saved the merged config, which committed the local overrides and deleted `[links]`/`[metrics]`. A deprecated `coding_agent_playbook.packs.<leaf>` in the committed `overlays_enabled` is therefore written back as parsed: the deprecation warning still prints, and the report's `Overlays:` line shows the canonical name (§11.5). The file is re-serialized by the same writer as an `init` re-run (§12.1): values survive, comments and layout do not, and a literal comes back in the writer's spelling. It exits 2 with `error: …`, writing and printing nothing, when the config cannot be loaded (§7.1), when the committed file alone lacks a required key (even one the local file supplies — plain `check` and `sync` still run on the merged config), or when the local file merged over the refreshed config would not load.
### 12.6 `playbook validate`
Validate canonical sources without rendering. Used in the engine's own CI and by overlay authors.
```
$ playbook validate
✓ 18 artifacts loaded from 2 sources
✓ All frontmatter valid against schema
✓ All Jinja templates compile
✓ All `includes_rules:` lists are rule ids that resolve
✓ No prompt calls the removed `{{ rule() }}` helper
✓ All `eval_tasks:` references resolve to existing tasks
✓ All task `prompt_id` back-references match a prompt's `eval_tasks:` list
✓ All markdown links self-contained (relative targets resolve; externals allowlisted)
✓ All skills are valid Agent Skills (string id declared, id/name matches ^[a-z0-9]+(-[a-z0-9]+)*$, description present)
✓ Every scoped rule names a skill that takes member rules (V1–V14)
✓ All hooks honour the hook trust contract (H1–H21)
✗ overlays_enabled: coding_agent_playbook.plugins.superpower: no such bundled plugin (bundled plugins: coding_agent_playbook.plugins.python_design, coding_agent_playbook.plugins.superpowers)
✗ rules/frameworks/sqlalchemy-v2.md.j2: applies_if references unknown fact 'orm_version'
✗ prompts/refactor.md.j2: body calls {{ rule("python-typing") }}; prompts no longer inline rules. Remove the call and keep 'python-typing' in includes_rules: Claude Code and OpenCode commands then point at its skill, Continue appends its text
✗ prompts/review.md.j2: includes_rules names 'python-typng', which is no rule in core, an enabled overlay or playbook/rules/; did you mean 'python-typing'?
✗ prompts/tidy.md: includes_rules 'python-typing': expected a list of rule ids, e.g. ['python-typing', 'pytest']
✗ rules/languages/python/typing.md.j2: body calls `{{ rule(...) }}` — rules cannot include other rules
✗ eval_tasks/orphan-task/task.toml: prompt_id 'deleted-prompt' does not exist
✗ prompts/generate-tests.md.j2: declares eval_task 'foo-bar' but eval_tasks/foo-bar/ not found
✗ rules/languages/python/typing.md.j2: markdown link 'style.md' (line 12): target 'style.md' does not exist in the artifact set
✗ prompts/review.md.j2: markdown link 'https://blog.example.com/x' (line 4): external link to host 'blog.example.com' is not in [links] allowed_domains
✗ skills/My_Skill (<repo-local>): skill id 'My_Skill' is not a valid Agent Skills name (must match ^[a-z0-9]+(-[a-z0-9]+)*$); OpenCode silently skips it
✗ skills/query-db (<repo-local>): skill has no 'description'; Agent Skills requires a non-empty description
✗ playbook/hooks/guard-x/HOOK.md: decision 'allow' is never permitted: it would bypass the harness permission system
✗ skills/<no id; name 'pdf-tools', at playbook/skills/pdf-tools> (<repo-local>): skill has no 'id'; it is emitted as 'skill' and collides with every other id-less skill (declare 'id:' in its SKILL.md frontmatter)
exit code: 1
```
The sample is stylized: the command prints `OK <N> artifacts validated` (rules, prompts and hooks) when it passes, and otherwise one `FAIL <path>: <message>` line per error followed by `validation failed with <N> error(s)`.

**Prompt rule references (v0.21).** `includes_rules` is the only declaration of the rules a prompt needs (§6.2.5, D15), so `validation/prompts.py` checks it three ways, each finding naming the prompt's source path (its id without one): a body that calls `rule()` in any spelling (`RULE_CALL_RE`, with or without trim markers, in a `.md` or `.md.j2` prompt) fails with the migration message above, since the helper is gone; an `includes_rules` that is not a list of non-empty strings fails once with the expected shape (a bare string used to be iterated character by character); and an id that names no rule of the merged set fails with a did-you-mean. The merged set is taken before `applies_if`: a rule filtered out in this repo is still a valid id and simply gets no pointer line. A rule body that calls `rule()` keeps its own message (rules cannot include other rules), and so does a hook body (H19). Being validate errors, all three stop `playbook sync` before any write. `--check-staged`, which is not validate-gated, still runs the first check alone (`check_prompt_rule_calls`) once something is staged, so a leftover call fails the commit with the same message instead of a jinja2 `UndefinedError` traceback.

The self-contained-links rule (PR L, design in `specs/prL-markdown-links.md`) covers rule bodies, prompt bodies, and skills (`SKILL.md` + every markdown file under `references/`) across all three source layers. Extraction masks frontmatter, fenced code blocks, and inline code spans (code examples like `def first[T](items: list[T])` are not links); Jinja-bearing targets are skipped as not statically checkable. Relative targets must resolve — `other.md` is satisfied by a canonical `other.md.j2` since rendering drops the suffix — and must stay inside the artifact's source layer (`catalog/core/` for the engine, `catalog/plugins/<name>/` for a bundled plugin, an overlay package's `resources/`, or the consumer's `playbook/`); a bundled artifact must also not link to a file at its layer root (`README.md`, `LICENSE`, `ATTRIBUTIONS.md`), which ships in the wheel but is never synced, so `tests/integration/test_catalog_layout.py` refuses such a link; `http(s)` targets pass only via `[links] allowed_domains` (§7.1); every other scheme and absolute paths are violations. Deterministic by construction: stdlib only, no network. The engine's own shipped artifacts are enforced on CI by a pytest integration test (`tests/cli/test_validate_links.py`); consumer repos and overlays inherit the rule through `playbook validate`.

The overlay rule (v0.17) runs the sync preflight's own check (`validation.preflight.unusable_overlays`, §4.2 step 1) over `overlays_enabled`: one error per overlay package whose import fails (the reason quotes the error when the package exists but raises), or that imports with no `resources/` directory, and per bundled-plugin name that matches no `catalog/plugins/<leaf>/` (`no such bundled plugin`) or is a bare plugin namespace (`the bundled plugin namespace, not a plugin`) — a bundled-plugin name is checked against the catalog tree and never imported — printed as `FAIL overlays_enabled: <name>: <reason>` (with the bundled-plugin list for a plugin-like typo, §11.5) and counted in the exit-1 `validation failed with <N> error(s)` summary. Before v0.17 `validate` skipped such a package silently (its artifacts were simply absent) and exited 0 on a config every `sync` mode refuses. A `ConfigError` (§7.1) is not a validation error: the config cannot be loaded, so `validate` exits 2 with `error: …` before checking anything.

The Agent Skills rule (v0.15) checks every resolved skill: it must declare a string `id` (§6.3), its id — emitted as the `SKILL.md` `name` and the output directory — must match `^[a-z0-9]+(-[a-z0-9]+)*$` and be at most 64 chars, and it must carry a `description` of 1–1024 chars. OpenCode silently drops a skill that breaks either name/description constraint, so authors learn here instead of at runtime. Id-less skills all merge under the fallback id `skill` (all but one silently dropped), so they are checked from the **pre-merge** list and each one is reported. Skills carry no source path, so errors are reported as `skills/<id> (<source package>)`, or — for an id-less skill — by its authored `name` plus, when it has `scripts/`/`references/`, its source directory.

**Member rules and `playbook:` blocks (v0.21).** A scoped rule that names a skill in `skill:` is a member rule of that skill (§6.1.1; design `specs/prS-skills-context.md` §6.6), and a skill takes members only when it declares the catalog-only `playbook:` block. `validation/_skills.py` checks both sides over the merged rule and skill sets, ignoring `applies_if`, so every repo sees the same findings whatever its detector facts. Rule findings name the rule's file; skill findings use the `skills/<id> (<source package>)` label above. Errors stop `playbook sync` before any write; warnings print on stderr. Every scoped rule must name its skill (V1, the message is `SCOPED_RULE_NEEDS_SKILL_MESSAGE`, which MIGRATION.md quotes): an overlay or `playbook/rules/` scoped rule without `skill:` stops `playbook sync` until it names one. The known skills it lists are the merged skills that declare a `playbook:` block, sorted. The advisory rule of a hook names no skill and never reaches these checks, since it is not an authored rule.

| # | Check | Sample line |
| --- | --- | --- |
| V1 | a scoped rule without `skill` | `FAIL rules/x.md: scope 'scoped' needs 'skill: <skill-id>' naming the skill whose references deliver this rule; known skills: ml-data, python-coding, python-testing, python-tooling` |
| V2 | V1 on an override of a rule that named a skill | V1's line plus `; the rule it overrides (coding_agent_playbook) names 'python-coding'` (the nearest overridden definition that names one) |
| V3 | an always rule sets `skill` | `FAIL rules/x.md: 'skill: python-coding' is not allowed on an always rule (always rules stay in always-loaded context); remove 'skill', or set 'scope: scoped' to deliver the rule through that skill` |
| V4 | `skill` is not an id string | `FAIL rules/x.md: skill 42 must be a skill id string matching ^[a-z0-9]+(-[a-z0-9]+)*$ (1-64 chars), e.g. 'python-coding'` |
| V5 | no skill of that id after the merge | `FAIL rules/x.md: skill 'python-codng' does not exist after merging every layer; expected one of: ml-data, python-coding, python-testing, python-tooling (or enable the overlay that ships it)` |
| V6 | a member rule's id is not a skill-safe file name | `FAIL rules/x.md: rule id 'Py_Typing' cannot be a member of skill 'python-coding': its reference is written as references/<id>.md, so the id must match ^[a-z0-9]+(-[a-z0-9]+)*$ (1-64 chars)` |
| V7 | `playbook` is not a mapping | `FAIL skills/x (pkg): 'playbook' must be a mapping with optional keys files and use_when, got str 'yes'` |
| V8 | an unknown key in `playbook` | `FAIL skills/x (pkg): 'playbook' has unknown key 'when'; allowed keys: files, use_when` |
| V9 | `use_when` or `files` is not one non-empty line; `files` is over 80 chars or ends with a period | `FAIL skills/x (pkg): 'playbook.files' is 112 chars; keep it to one line of at most 80 chars without a trailing period (it becomes one line of 'Where guidance lives')` |
| V10 | `use_when` starts with "Use when" (the engine adds it) | `FAIL skills/x (pkg): 'playbook.use_when' starts with 'Use when'; write only the condition (the engine adds 'Use when'), e.g. 'editing a Python module'` |
| V11 | the worst-case composed description, the longest member name plus the `and <N-1> more` tail, is over 300 chars | `FAIL skills/python-coding (pkg): the composed description cannot fit 300 chars even when the Covers clause names one member: '<text>' is 312 chars; shorten 'description' (88 chars), 'playbook.use_when' (130 chars) or the longest member name (python-typing: 'Python typing conventions')` |
| V12 | a hand-written reference has a member's file name | `FAIL skills/python-coding (pkg): references/python-typing.md is hand-written in this skill but is also the rendered reference of member rule 'python-typing'; rename the hand-written file` |
| V13 | the authored body has a line that is exactly `## References` | `FAIL skills/python-coding (pkg): the body has its own '## References' heading; the engine appends that section for member rules, so rename yours (e.g. '## Further reading')` |
| V14 | `skill` names a skill without a `playbook:` block, such as a bundled plugin skill | `FAIL rules/x.md: skill 'brainstorming' (coding_agent_playbook.plugins.superpowers) declares no 'playbook:' block, so it cannot take member rules; name one that does (ml-data, python-coding, python-testing, python-tooling), or add a 'playbook:' block to a skill of your own (an override of a core skill must keep one)` |
| W1 | a `playbook:` block that no rule names | `warning: skills/x (pkg): declares 'playbook' but no rule names it in 'skill:'; it is never written` |
| W2 | member rules but no `playbook.files` | `warning: skills/x (pkg): has member rules but no 'playbook.files'; it is left out of the 'Where guidance lives' section` |
| W3 | the full member list would be truncated | `warning: skills/python-coding (pkg): the composed description names 6 of 9 member rules within 300 chars ('... and 3 more'); shorten member names or the authored parts to list them all` |

V11 measures with `skills.document.worst_case_description`, the same bound the sync's composition holds: a real composition of `M` active members (`M` at most the merged count `N`) that falls back to one name is never longer than that worst case, so a skill that validates cannot make `playbook sync` raise. The D13 description lint, the 500-line limit and the one-level references check are CI tests over the core skills only, never validate checks, so enabling a bundled plugin whose skills predate them keeps validate passing.

**Without a consumer config (v0.20).** An engine or overlay checkout has no `.coding-agent-playbook.toml`, and `playbook validate` no longer fails there: it validates the engine's catalog, the checkout's own `src/*/resources/` (an overlay checkout; a checkout whose `src/<pkg>` is the engine package is never walked twice) and `playbook/`, and first names the consumer-config checks it skips. Installed overlays are not discovered, since overlays resolve by package name from `overlays_enabled` only:
```
note: no .coding-agent-playbook.toml in /repo; validating the engine package, src/*/resources/ and playbook/ only
skipped: overlays_enabled usability (no overlay list to check)
skipped: [links] allowed_domains (no allowlist to read; external links fail the strict default)
skipped: [hooks] / [guardrails] policy: H15 switches, H16 allow_code_from, H21 tables (no consumer config to read)
```
**The validate gate on `playbook sync` (v0.20).** Write-mode `playbook sync` and `playbook sync --check` run this whole rule set (`validation.checks.sync_gate_errors`) before rendering. On any error they print its `FAIL` lines and `playbook sync aborted; no files were written.` to stderr and exit 1, so content the engine would render wrongly — an unknown `applies_if` fact, a broken eval-task reference, an invalid Agent Skill, a hook that breaks its contract — never reaches disk. Warnings never stop a sync, and `--check-staged`, the pre-commit hot path, is not gated. A repo whose content fails `playbook validate` today stops syncing on upgrade, so run `playbook validate` before upgrading (MIGRATION.md).

**The hook trust contract, H1–H21 (v0.20).** Every hook is checked (`validation/_hooks.py` over `hook_policy`), and each message names the offending value and the expected shape. A malformed `HOOK.md` is a `FAIL` line, never a traceback; degraded cells and clamped timeouts are `warning:` lines on stderr.

| Rule | Checks |
| --- | --- |
| H1 | `HOOK.md` parses; frontmatter keys come from the schema, required fields are present and types match §6.6.7. |
| H2 | `id` matches `^[a-z0-9][a-z0-9-]{0,62}$` and equals its directory name; it is unique within a layer; a directory holds `HOOK.md` or `HOOK.md.j2`, not both, and no hook directory sits inside another. |
| H3 | `events` is non-empty, unique and canonical (§6.6.7). |
| H4 | `matcher` keys are declared events; each entry uses only the fields its event allows and tool classes from the authoring vocabulary (`mcp` on a hook that supports `opencode` is a warning); regexes compile; globs are relative, without `..`. |
| H5 | `decisions` ⊆ {`deny`, `ask`, `context`, `none`}, each valid for a declared event. `allow` is always an error: it would bypass the harness permission system. |
| H6 | Exactly one of `handler` / `handlers` (whose keys equal `events`). A builtin is registered, supports its event, validates its `config` against its `CONFIG_SCHEMA`, emits only declared decisions and never mutates the tool input. |
| H7 | An external handler's `command` is `python`, `bash`, `sh` or `node`; its `script` is a regular file under the hook's own `scripts/`, never a symlink or an escape; `args` carry no URL; `config` is JSON-serializable. |
| H8 | No HTTP, async, prompt, agent or input-rewriting handler: the keys `type`, `url`, `headers`, `async`, `updated_input`, `prompt` and `model` are rejected (§17.1). |
| H9 | `0 < timeout ≤ 600`, and `≤ 30` on tool and prompt events; a timeout above its event's cap is clamped, with a warning. |
| H10 | `on_error` is valid for a declared event; `deny` (fail-closed) only on an overlay hook. |
| H11 | `supports` lists hook-capable adapters only, with at least one declared event reachable on each; an event unreachable on a listed adapter is a warning, and the hook is `degraded` and not registered there for it. |
| H12 | `tier` is valid; `tier: overlay` only on an engine hook or an overlay's same-id override of one; `mandatory: true` only on an overlay hook, with `enabled: true`. |
| H13 | An engine hook is builtin-only and ships no `scripts/`. |
| H14 | An overlay override only adds (§11.6): no handler swap, no dropped event, tool class, `deny` or `ask`, no weaker `on_error`, no tier demotion. |
| H15 | No repo-local override of a `mandatory` hook; `[hooks] disable` names none, and `[hooks] enabled = false` is an error while an enabled overlay ships one. |
| H16 | An external or entry-point handler of an on hook comes from a package listed in `[hooks] allow_code_from`. |
| H17 | `applies_if` uses known facts. |
| H18 | `linked_rule` resolves in the merged rule set. |
| H19 | A `HOOK.md.j2` body compiles in the sandbox and never calls `rule()`; the body's markdown links are self-contained. |
| H20 | No authored rule id takes the reserved `guardrail-` prefix, and no hook id equals a rule or prompt id (`playbook render` looks ids up across kinds). |
| H21 | `[hooks]` and `[guardrails]` parse; `enable` / `disable` name existing hooks and are disjoint; `allow_code_from` ⊆ `overlays_enabled` ∪ {`<repo-local>`}; no `wrapper_prefixes` entry has a token naming a guarded command; every `[hooks.<x>]` names a hook (or `commit_convention`) and validates against its `CONFIG_SCHEMA`; `[hooks.stop-ci-parity-gate] stages` ⊆ {`typecheck`, `tests`}; `cutover_date` is a `"YYYY-MM-DD"` string; neither table appears in `.local.toml` (an error here, a warning in `sync`). |
### 12.7 `playbook render` (debug)
Render a single artifact to stdout for debugging. Does not write.
```
$ playbook render python-typing --format continue
[full rendered .continue/rules/50-python-typing.md to stdout]
$ playbook render python-typing --format claude_md_section
[the section that would be emitted into .claude/rules/coding-agent-playbook.md]
$ playbook render python-typing --show-source
Template:  playbook_rules_bnp/resources/rules/languages/python/typing.md.j2
Format:    .md.j2 (Jinja-templated)
Overrides: coding_agent_playbook
Adapters:  continue, claude_code, agents_md
           (opencode reads rules via AGENTS.md natively — no direct render)
applies_if evaluated: True
$ playbook render generate-tests --show-rules
Prompt:    generate-tests
includes_rules:
  - python-typing  (playbook_rules_bnp, applies_if=True -> skill python-coding, references/python-typing.md)
  - pytest  (coding_agent_playbook, applies_if=True -> skill python-testing, references/pytest.md)
  - project-context  (coding_agent_playbook, applies_if=True -> always loaded)
  - python-style  (coding_agent_playbook, applies_if=False -> OMITTED)
  - python-typng  (UNKNOWN)
$ playbook render destructive-command-guard
[the hook's advisory: ### heading, rendered body, the italic enforcement line]
$ playbook render destructive-command-guard --format hook_claude_settings
[{"hooks": {"PreToolUse": [...]}}: its Claude Code registrations, from its own frontmatter]
```
`--show-rules` names each included rule's delivery in a Claude Code or OpenCode command (v0.21, D15): its owning skill and reference, `always loaded` for an always rule, `OMITTED` when its `applies_if` is false here, `UNKNOWN` when no rule has the id. Rendering a prompt with `--format prompt_claude_command` or `prompt_opencode_command` shows the `## Before you start` block, and `--format prompt_continue` the `## Reference rules` appendix, both through the registry of the rules that apply here, unfiltered by validate. A prompt whose body still calls the removed `rule()` prints `error: <file>: 'rule' is undefined` and `error: playbook render aborted.` and exits 1, instead of a traceback.
The `--show-source` sample is stylized: `Template:` prints the template's absolute path, `Overrides:` names the package of each layer whose artifact this one replaces (`coding_agent_playbook` for the engine), and `Adapters:` lists the enabled adapters in sorted order.
**Hooks (v0.20).** A hook id renders `hook_advisory` by default — the full text Continue and `agent_harness` receive and the `playbook-guardrails` skill holds (`AGENTS.md` gets one line, §10.4) — and `--format hook_claude_settings` shows the hook's Claude Code registrations as `settings.json` JSON, built from its declared frontmatter alone (no `[hooks]` gating, no deadlines from other hooks), for debugging; sync never writes that projection (§9.7). Only these two formats apply to a hook, and rule or prompt formats are refused for it. Ids are looked up across rules, prompts, skills and hooks, which is why validate reports a hook id that equals a rule or prompt id (H20, §12.6). A hook body that calls `rule()` fails naming the file (H19).
### 12.8 `playbook eval` (Tier 0 enumeration + the v1.1 `--run` runner)
`playbook eval` is a read-only enumeration of the prompt-to-task graph and — with `--run` (v1.1 PR R1) — the entry point that *executes* one task end-to-end through a `HarnessRunner` and grades it (§15.3). Without `--run`, the bare `playbook eval <id>` prints how to run the task (exit 0; example below).
```
$ playbook eval --list
=== Eval tasks ===
generate-tests (engine)
  ├── generate-tests-happy-path        ✓ task defined
  │   └── 4 rubric criteria, 4 gate checks
  ├── generate-tests-edge-cases        ✓ task defined
  │   └── 5 rubric criteria, 4 gate checks
  └── generate-tests-async-code        ✓ task defined
      └── 3 rubric criteria, 2 gate checks
refactor (engine)
  └── refactor-extract-helper          ✓ task defined
      └── 3 rubric criteria, 2 gate checks
review (engine)
  └── (no eval tasks declared)         ⚠ consider adding tasks
pii-scan (overlay bnp)
  └── pii-scan-detects-iban            ✓ task defined
      └── 2 rubric criteria, 1 gate checks
Total: 5 prompts, 5 eval tasks, 1 prompt without tasks
```
`playbook eval --list` walks the prompt registry, reads each prompt's `eval_tasks:`, and reports coverage. The "no eval tasks declared" warning is informational, not a `playbook validate` failure — eval tasks are recommended, not required.
```
$ playbook eval --show generate-tests-happy-path
Task: generate-tests-happy-path
Source: coding_agent_playbook/eval_tasks/generate-tests-happy-path/
Prompt under test: generate-tests
Description: Generate tests for a simple pure function with no edge cases
Setup:
  Mock facts: python_version=3.12, frameworks=[pytest, pytest-asyncio]
  Files (1): src/calculator.py
Invocation:
  Prompt: /generate-tests
  Args: "for the add function in src/calculator.py"
  Variables: target=src/calculator.py::add
Gate (deterministic, 4 checks, expr: test_created and names_test and parametrized and src_unchanged):
  - test_created: check file_exists tests/test_calculator.py
  - names_test: check file_contains tests/test_calculator.py ~/def test_add/
  - parametrized: check file_contains tests/test_calculator.py ~/parametrize/
  - src_unchanged: check file_unchanged src/calculator.py
Rubric (manual / LLM-judge, 4 criteria):
  - 0.2: Tests use pytest.parametrize for table-driven cases
  - 0.2: Test file lives at tests/test_calculator.py (mirror layout)
  - 0.4: All public branches of `add` are covered
  - 0.2: No mocking is used (the function is pure)
Verdict: gate and rubric
```
The `Source:` label (`commands/_eval_enumerate.py:_display_source_path`) is built from the task's layer, never by searching its path for a `resources` segment, and never shows the absolute filesystem path. `<dir>` is always the task directory's name (`task.source_path.parent.name`), never `task.id`, which nothing ties to the directory:
- **Bundled layers** (the engine and bundled plugins): `<source_package>/eval_tasks/<dir>/`, e.g. `coding_agent_playbook/eval_tasks/generate-tests-happy-path/` or `coding_agent_playbook.plugins.<name>/eval_tasks/<dir>/`. Before v0.19 the engine's label read `coding_agent_playbook/resources/eval_tasks/<dir>/`.
- **Third-party overlays:** `<source_package>/resources/eval_tasks/<dir>/`, still a real package-relative path, so it is unchanged.
- **Repo-local:** `playbook/eval_tasks/<dir>/`.
```
$ playbook eval generate-tests-happy-path
playbook eval generate-tests-happy-path:
Add --run to execute this task against an agent and grade it:
  playbook eval generate-tests-happy-path --run --runner fake    # hermetic no-op agent, no CLI
  playbook eval generate-tests-happy-path --run                  # default runner: claude_code
  playbook eval generate-tests-happy-path --run --judge llm      # also score the [rubric] layer
Inspect it with `playbook eval --show generate-tests-happy-path`; coverage: `playbook eval --list`.
To run it by hand, copy setup/ to a scratch repo and invoke /generate-tests.
exit code: 0
```
(The bare `playbook eval <id>` path prints how to run the task and exits 0 — the runner is not invoked without `--run`, so `playbook eval <id>` stays a cheap existence check.) To actually execute a task, add `--run`:
```
$ playbook eval refactor-extract-helper --run --runner fake [--judge llm] [--samples N] [--format text|json]
```
- **`--runner NAME`** selects a runner from the `coding_agent_playbook.runners` entry-point group; the default is **`claude_code`** (the real runner). Use `--runner fake` for a hermetic, no-network demo/CI run.
- **`--judge NAME`** selects a judge from the `coding_agent_playbook.judges` group to score the task's `[rubric]` layer too. The shipped judge is **`llm`** (`LLMJudge`, shells out to the `claude` CLI, `available()`-gated, never in CI). **Omitting `--judge` is deterministic-only** — no `ProgrammaticOnlyJudge`, just no judge configured ⇒ the `[rubric]` layer skips (a skipped layer is neutral in the derived verdict). **`--samples N`** (default 1) is the per-criterion sample count the judge averages.
- The task's `[gate]` layer (file checks + static/execution metric checks, 0–1 normalized non-regression) is scored deterministically into one `EvaluationReport`, rendered with the same text/json renderer as `playbook metrics`. With `--judge` set, the `[rubric]` layer's judged scores fold into the same report; the per-trial verdict is then derived from the two layers' results via `[verdict].trial`.
- **`--full-scoring`** forces every check to run (no short-circuit), for a complete report even when a cheap gate check has already failed.
- **There is no `--run-tests` flag.** Unlike `playbook metrics`, execution intent is *inferred*: a task runs the suite iff its `[gate]` references an execution metric (`coverage` / `test_pass_rate`), so the task — not a CLI flag — decides whether the execution checks run.
- **Exit codes:** `0` on a passing report (the task verdict holds), `1` on a failing report, `2` on usage errors — unknown task id, unknown `--runner`, a runner that is unavailable in this environment (e.g. `claude_code` with no `claude` CLI on `PATH` — the error suggests `--runner fake`), an unknown or unavailable `--judge` (e.g. `llm` with no `claude` CLI), or a bad `--format` — and when the task **cannot be scored at all**: its prompt fails to render (`PromptResolutionError`), or the judge gives no score after its bounded retries (`JudgeError`: the CLI exited non-zero, timed out, or did not answer with exactly one number in `[0, 1]`). An unscored task is neither a pass nor a fail, so it never exits `0`/`1`.
- **Judged scores are labelled uncalibrated.** Whenever a judged check ran, the text report adds a note and the JSON carries `"uncalibrated_judge": true`, until judge calibration (§19 Q12) exists.
### 12.9 `playbook import-harness`
Parse an Agent Harness tree back into canonical artifacts and write them into an overlay directory (default `./playbook/`) in the `FileSystemArtifactSource` layout, so a later `playbook sync` re-reads them. The reverse of the `agent_harness` adapter (§10.7).
```
$ playbook import-harness ./vendor/some-harness
imported 6 artifact(s) into /repo/playbook (3 rules, 2 prompts, 1 skills, 0 hooks)
```
Two fidelity tiers, picked automatically (`specs/prH-agent-harness.md` §C):
- **Lossless** — when a `.playbook/manifest.toml` sidecar is present (a playbook-emitted harness): every artifact is rebuilt from the manifest's full reconstruction payload (full frontmatter incl. rule `name`, the un-rendered source body, `is_templated`, per-script `executable` bit), independent of how the leaf rendered or inlined content. Script exec bits are restored on POSIX, no-op on Windows.
- **Best-effort** — no sidecar (a foreign harness): kinds are inferred from directory placement (`skills/*` → `Skill`, `prompts/*` → `Prompt`, `rules/*.md` → `Rule` scope=always, `references/*.md` → `Rule` scope=scoped, non-markdown → opaque asset). Non-native fields are defaulted and every lossy assumption is reported as a `warning:` on stderr — the importer never silently guesses.
```
$ playbook import-harness ./vendor/foreign-harness --into playbook
warning: no .playbook/manifest.toml sidecar found; reconstructing best-effort. ...
warning: rule 'pep8': scope inferred as 'always' from rules/ placement; globs/applies_if/priority/tags/version not recoverable without sidecar
imported 2 artifact(s) into /repo/playbook (2 rules, 0 prompts, 0 skills, 0 hooks)
```
All reconstructed rules — `scope=always` *and* `scope=scoped` — are written under `<into>/rules/<id>.md` (the only directory `FileSystemArtifactSource.list_rules()` reads); `scope` is preserved in the rule's emitted frontmatter, so a scoped rule stays scoped without needing a separate directory. A lossless import also rebuilds every hook from its manifest entry (kind `"hook"`, v0.20) through `Hook.from_dict`, never from the rendered files, and writes it as `<into>/hooks/<id>/HOOK.md` (`HOOK.md.j2` when templated) with its `scripts/`, exec bits restored; a best-effort import reads a `rules/NN-guardrail-*.md` advisory as a rule and warns that the hook cannot be reconstructed without the sidecar (§10.7.2). Exit code is 2 on a usage error (missing/non-directory path, or no `HARNESS.md`), else 0.
### 12.10 `playbook validate-harness`
Run `harnesses-ref`-equivalent structural checks on an Agent Harness tree (emitted or foreign). This is the lint half of the client-runtime decision (§10.7 / decision #3): the playbook validates harness *structure*, it does not implement a harness client runtime.
```
$ playbook validate-harness ./build/harness
OK harness validated (0 warning(s))
exit code: 0
```
Checks:
- **Errors** (non-zero exit): `HARNESS.md` present with non-empty `name` and `description`; every detected skill leaf carries a non-empty `name` and `description`.
- **Warnings** (exit 0 by default; promoted to errors by `--strict`): a grouping subdirectory lacks its routing file (`<DIR>.upper() + ".md"`); a content `.md` lacks a `description`.
```
$ playbook validate-harness ./build/harness --strict
warning: /build/harness/skills: grouping directory lacks its routing file 'SKILLS.md'
validation failed with 0 error(s), 1 warning(s) (warnings promoted by --strict)
exit code: 1
```
A missing or malformed `HARNESS.md` is reported as a validation **error** (exit 1) — not a usage error (exit 2) — because for a validator a malformed harness is precisely the failure it exists to report. Directories marked opaque by a `.harnessleaf` marker are terminal leaves: the validator never expects a routing file for them and does not inspect their internal content.
### 12.11 `playbook ci`
```
playbook ci [--base REF] [--steps STEP[,STEP…]] [--format text|json] [--repo-root DIR]
```
The aggregate off-workstation twin of the hooks (v0.20; design `specs/prK-hook-pack.md` §F.5): one required status check. Hooks are speed bumps on the developer's machine; this is the authoritative check. It runs each row of `commands.twins.ci.CI_STEPS` as a **child process** — `<python> -m coding_agent_playbook.cli <argv> --repo-root <root>`, an argv list with no shell and a 600 s timeout per step — so one step crashing cannot take the others down, and every step sees exactly what a developer running it would. Steps run in table order with no fail-fast; a row whose condition does not hold is reported `skipped` with its reason, and a config that does not load runs the rows it gates anyway, so the child reports why (fail closed). `--steps` selects a comma-separated subset (an unknown name is a usage error listing the valid ones) and also switches on the opt-in rows it names. The base is `--base REF`, else the default branch (`refs/remotes/origin/HEAD`, then `main`, then `master`); the range is `<merge base>..HEAD`, resolved only when a selected step needs it, so the CI checkout needs the full history (`fetch-depth: 0`). `--repo-root DIR` checks another checkout.

| Step | Runs | When |
| --- | --- | --- |
| `sync-check` | `playbook sync --check` | a config exists and sets `[output] commit = true` (under `commit = false` a fresh clone has no output to compare) |
| `validate` | `playbook validate` | always |
| `metrics` | `playbook metrics --baseline git:<merge base> --changed --no-run-tests` | always: static, never the suite |
| `coverage` | `playbook metrics --run-tests --select testing --baseline git:<merge base>` | `[metrics] run_tests = true`, or `--steps coverage` |
| `gate-scan` | `playbook gate-scan --range <merge base>..HEAD` | always |
| `scan-secrets` | `playbook scan-secrets --range <merge base>..HEAD` | always |
| `commit-convention` | `cz check` itself, not an engine child: the range's commits whose committer date is on or after `[hooks.commit_convention] cutover_date`, plus `cz check --message` on `$PLAYBOOK_PR_TITLE` when it is set; a missing `cz` fails the step | `[tool.commitizen]` in `pyproject.toml`, or `[hooks.commit_convention]` |
| `commit-trailers` | `playbook check-commit-trailers --range <merge base>..HEAD` | a commit-trailer row is configured |
| `check-deps` | `playbook check-deps --base <merge base>` | a dependency policy is configured |
| `scan-sinks` | `playbook scan-sinks --range <merge base>..HEAD` | only when `--steps` names it |

Exit codes: `0` every step that ran passed; `1` any failed or timed out; `2` a usage error or an unresolvable base (nothing ran). `--format json` prints one `{step, argv, exit, duration_s, status}` record per step (plus `note` for a skipped one) on stdout, and the children's output on stderr.

**Pull-request titles.** In a squash-merge repository the PR title becomes the commit subject, so the `commit-convention` step also checks `PLAYBOOK_PR_TITLE` when it is set, passed to `cz` as one argv element. A PR title is attacker-controlled text: the workflow passes it only through `env:`, never interpolated into a `run:` line (the GitHub Actions script-injection pattern). A consumer's pull-request job:
```yaml
jobs:
  playbook-ci:
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0                 # playbook ci diffs <merge base>..HEAD
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install the project with its dev tools (coding-agent-playbook, commitizen)
        run: python -m pip install -e ".[dev]"
      - name: playbook ci
        run: playbook ci --base origin/main
        env:
          PLAYBOOK_PR_TITLE: ${{ github.event.pull_request.title }}
```
### 12.12 `playbook metrics`
The static code-quality gate and, with `--run-tests`, its execution metrics. The whole contract — targets, selection (`--select`, `--extend-select`, `--ignore`), baselines, `--changed`, exit codes and the pre-commit hooks — is §21.5; `playbook ci` runs it as its `metrics` and `coverage` steps (§12.11).
### 12.13 `playbook-hook`: the hook runtime (v0.20)
One console script with two kinds of caller (design `specs/prK-lifecycle-hooks.md` §D). Harnesses never use the console script: the Claude Code launcher and the OpenCode shim run `<pin> -I -m coding_agent_playbook.hook_runtime dispatch …` with the pinned interpreter (§10.3.2, §10.6.2). Humans run `simulate`, `doctor` and `--version`.
```
usage: playbook-hook dispatch <event> --harness claude_code|opencode [--project-dir DIR] [--async]
       playbook-hook simulate <event> [options] < payload.json
       playbook-hook doctor [options]
       playbook-hook --version
```
**`playbook-hook dispatch`** reads one harness payload on stdin, normalizes it to a canonical event (under `--harness claude_code`, a foreign payload from another harness that reads `.claude/settings.json` leaves it inert), runs every on hook bound to that event in-process from `.coding-agent-playbook/hooks/guard_config.json` (checked against its lockfile digest), combines their results — deny over ask over context over none — and writes one JSON object to stdout in the harness's shape. It is hand-parsed and import-light: the hot path imports only `hook_runtime.*`, `security.*` and the stdlib, and runs no subprocess for a non-git, non-pragma call. It **exits 0 or 10**, never 2: 10 is a decided deny, which the launcher turns into Claude Code's exit 2 and the shim into a throw, while a usage error, an unknown flag or a version-skewed engine goes to the failure policy, so a raw 2 is never a deny. At entry fd 1 is moved to fd 2, so a stray print from a handler or a child cannot corrupt the one JSON object. `--async` (valid on `post_tool_use` only) runs the async-safe handlers and writes nothing. A handler that fails is judged by its hook's `on_error` — `open` skips it with one note per session, `ask` asks (a deny when no human can answer), `deny` is an overlay's fail-closed choice — and a watchdog writes the decided result before the harness's own timeout.

**Kill switches and escape hatches** are read only from the dispatcher's own environment, with exact values: `PLAYBOOK_HOOKS=off` turns every hook off, mandatory ones included (the off-workstation twins stay the control); `PLAYBOOK_HOOKS_DISABLE=<id>,<id>` turns off non-mandatory ones; `PLAYBOOK_GATE=off` makes the Stop coordinator allow the stop, reported as not verified; `PLAYBOOK_ALLOW_GENERATED_EDIT=1` allows hand edits of generated files; `PLAYBOOK_HOOK_WRAPPER_PREFIXES=proxy,proxy run` declares this developer's own command launchers, merged with `[hooks] wrapper_prefixes` for the guards and verify-run tagging (an entry naming a guarded command is ignored, logged and reported by `playbook-hook doctor`). A `VAR=1 cmd` prefix inside a Bash call never counts, and a hatch set through a settings file's `env` object is ignored and reported. `PLAYBOOK_HOOK_UNATTENDED=1` marks a headless run, where an `ask` becomes what `[hooks] unattended_ask` says.

**The Stop coordinator** is the one registration on each stop event. Its stages run in this fixed order (`hook_runtime.stop.stages.STOP_STAGE_ORDER`), never by hook priority:

`drift` → `lint` → `quality-metrics` → `docstrings` → `gate-integrity` → `secrets` → `notebooks` → `verify-claim` → `output-contract` → `tests-nudge` → `typecheck` → `tests` → `coverage`

The deterministic stages share a 3 s default budget and feed one combined reason of at most 40 lines. The execution stages — `typecheck`, `tests` and `coverage`, which run repo-controlled code — run only when every deterministic stage is green, they are enabled (`[hooks.stop-ci-parity-gate] stages`, or coverage-diff-gate), and this machine approved the stage list (§7.1.1). A stage that times out, crashes or finds its tool missing or changed is reported NOT verified, never green. A tree unchanged since its last block is not blocked again, and a stop chain is blocked at most `max_blocks` times (default 2, 1–8). On OpenCode the Stop gate is evidence-only (§10.6.2).

**`playbook-hook simulate <event>`** runs the exact dispatch pipeline on one payload from stdin and prints what the harness would get. Options: `--harness claude_code|opencode`, `--repo DIR`, `--config PATH` (a `guard_config.json` run without the digest check), `--state DIR` (default: an ephemeral directory, so the real decision log is never touched), `--unattended` (force the ask degradation), `--env NAME=VALUE` (repeatable, to try kill switches), `--async` and `--format text|json`. The JSON is `{exit_code, stdout, stderr, decisions, combined, latency_ms}`, where `exit_code` is the harness-facing code: a `pre_tool_use` deny is 2, though `dispatch` itself exits 10. A completed simulation exits 0 whatever it decided; a usage error exits 2.

**`playbook-hook doctor`** is human-run and read-only (it never syncs). It checks what a harness hides by failing open: the `guard_config.json` digest against its lock entry; the interpreter pin (present, executable, Python ≥ 3.12, isolated under `-I`, importing this engine; an interpreter in a uv or pipx cache is degraded); the state root `<git-dir>/playbook-hooks/` (mode 700, owned by the user); the `machine.json` tool signatures; the trust approvals of external handlers; `PLAYBOOK_HOOK_WRAPPER_PREFIXES` when set (the prefixes it adds, or a warning for an entry it refuses or a value a settings file sets); OpenCode (`opencode --version` ≥ 1.18.29, `OPENCODE_DISABLE_PROJECT_CONFIG`, the shim's lock digest and registrations); and a guard-decision-log summary of the last `--since DAYS` (default 30): per guard, the deny, ask, override and degraded counts. `--repin [PYTHON]` is its one write: it rewrites the interpreter pin (default: the running interpreter) before checking. `--repo DIR` and `--format text|json` as for `simulate`. Exit codes: `0` healthy (warnings included), `1` degraded, `2` broken, and `2` for usage errors. Running the exact registered commands with canary payloads, reporting `disableAllHooks` and the managed-policy kill switches, and warning when `copilot` is on `PATH` are designed (`specs/prK-lifecycle-hooks.md` §D.9) but not implemented yet.

**`playbook-hook --version`** prints `playbook-hook <version>`.
### 12.14 `playbook gate-scan`
```
playbook gate-scan [--range A..B | --range A...B] [--format text|json] [--repo-root DIR]
```
gate-weakening-guard's off-workstation twin (v0.20); the `gate-integrity` Stop stage calls the same `hook_runtime.judges.gate_weakening.scan`, so the hook and CI never disagree. It flags added checker suppressions (`# type: ignore`, `# noqa`, `# pragma: no cover`, `# nosec`), skipped or non-strict-xfail tests, `cast(Any, …)`, a new bare `Any` under the source roots, `verify=False` and the self-service escape pragmas, plus loosened checker config, removed pre-commit hooks or workflow steps, and any `.gitleaks.toml` change. A trailing reason comment exempts a suppression (`# type: ignore[attr-defined]  # stub gap`); config loosenings and pragmas always reach the user as notes. `--range A..B` diffs A to B and `--range A...B` their merge base to B; without it the range is `<merge base with the default branch>..HEAD`. The policy is the engine default extended by `[hooks.gate-weakening-guard]` **as committed at the range's base**, so a change cannot loosen the rules it is judged by; `.local.toml` never applies. `--format json` prints the findings as JSON; `--repo-root DIR` scans another checkout. Exit: `0` clean (justified notes only), `1` blocking findings, `2` a usage error, an unresolvable base, a malformed policy table (a base config that does not decode is named with its revision: `error: .coding-agent-playbook.toml at <rev>: invalid TOML: …`) or a git failure.
### 12.15 `playbook scan-secrets`
```
playbook scan-secrets [--staged | --range A..B | --worktree | PATH…] [--pii] [--pii-detectors NAMES] [--format text|json] [--repo-root DIR]
```
The secret guards' off-workstation twin (v0.20), run by the `playbook-secrets` pre-commit hook (`--staged`, the index against `HEAD`) and the `scan-secrets` step of `playbook ci` (`--range <merge base>..HEAD`, also the default). `--worktree` scans tracked changes against `HEAD` plus untracked, non-ignored files; PATHs are scanned whole. Tokens — cloud, VCS, chat and LLM API keys, PEM private keys, JWTs, URLs with inline passwords — are found with the in-session guard's own rules (`security.secrets`) and reported **masked**: rule, place and match length, never a character of the value. Credential files (§17.3) are flagged by path and never read. `# playbook: allow-secret <rule-id>` waives its line only when the base revision already has it. The path policy is the engine catalog extended by `[guardrails.secrets]` as committed at the base (a base config that does not decode exits `2`, named with its revision: `error: .coding-agent-playbook.toml at <rev>: invalid TOML: …`); `.local.toml` never applies. `--pii` adds checksum-validated PII on the same lines and files, masked as `pii:<detector>`; `--pii-detectors iban,card_pan,fr_nir,us_ssn` chooses the detectors (default `iban,card_pan`) and implies `--pii`. `--format json` and `--repo-root DIR` as above. Exit: `0` clean (notes only), `1` a token, PII or a credential file, `2` a usage, policy or git error.
### 12.16 `playbook scan-sinks`
```
playbook scan-sinks [--staged | --range A..B] [--format text|json] [--repo-root DIR]
```
ml-unsafe-deserialization-guard's off-workstation twin (v0.20): it counts the unsafe deserialization sinks a change adds (`pickle.loads`, `torch.load(weights_only=False)`, …) in Python files and notebook code cells, with the guard's own visitor and the sink table its `HOOK.md` ships. `--staged` scans the index against `HEAD` (the opt-in `playbook-scan-sinks` pre-commit hook); `--range` works as for `gate-scan`, defaulting to `<merge base>..HEAD` (the opt-in `scan-sinks` step of `playbook ci`). A block sink under a `# playbook: trusted-artifact` comment the base already had passes; under a new one it is a note for the reviewer. `--format json` and `--repo-root DIR` as above. Exit: `0` clean (notes only), `1` a new block sink, `2` a usage or git error.
### 12.17 `playbook check-deps`
```
playbook check-deps [--base REF] [--repo-root DIR]
```
dependency-allowlist-guard's off-workstation twin (v0.20), the "separate package-check step" of §17.2. Each dependency manifest changed since the merge base of `--base REF` (default: the default branch) and `HEAD`, or untracked, is read at the base and in the working tree, and only newly declared names (PEP 503-normalized) and package indexes count, so existing dependencies are grandfathered. The rules are the guard's merged config, whatever `[hooks]` says: a name outside the overlay's `allowlist` or an index other than `required_index` is deny-class, index mixing follows `index_mode`, and without an allowlist the new names are listed. One `<path>: <deny|ask> <rule>: <detail>` line per finding; `--repo-root DIR` checks another checkout. Exit: `0` no deny-class finding, `1` a deny-class finding, `2` a git or config error.
### 12.18 `playbook check-commit-trailers`
```
playbook check-commit-trailers <msgfile> | --range A..B [--repo-root DIR]
```
The commit-trailer rows of git-commit-push-policy-guard (`[hooks.git-commit-push-policy-guard]`: forbidden, co-author and required trailers, the `CP4xx` rows; the subject form is commitizen's) as a twin that judges every commit, the human's and editor-composed ones included (v0.20). `<msgfile>` is what the pre-commit `commit-msg` stage passes (`coding-agent-playbook-commit-trailers`, §13.2); `--range A..B` checks every commit of a range, each line prefixed with its short sha (the `commit-trailers` step of `playbook ci`). The policy is the one of `--repo-root DIR` (default: the cwd). Exit: `0` nothing breaks a row (always, with no rows), `1` a violation, `2` the message, the range or the config cannot be read.
### 12.19 `playbook check-notebooks`
```
playbook check-notebooks [PATH…] [--repo-root DIR]
```
notebook-output-hygiene's off-workstation twin (v0.20), run by the opt-in `playbook-notebooks` pre-commit hook: every cell of each notebook named (pre-commit passes the staged ones), or of every tracked `.ipynb` file without PATHs, must keep no outputs. It is stdlib-only, standing in for nbstripout and nbqa, which the air-gapped starter leaves out (§13.2). PATHs are relative to `--repo-root DIR` (default: the cwd). Exit: `0` clean, `1` a notebook keeps outputs or is not valid notebook JSON, `2` a path that does not exist or no git repository to list.
## 13. Pre-commit integration
### 13.1 The engine's `.pre-commit-hooks.yaml`
Shipped at the root of `coding-agent-playbook` so consumers can reference it. The first two hooks implement the default `[output] commit = false` policy; `playbook-sync-check` is the **legacy** hook, only for repos that set `commit = true`; the rest (second block) gate code quality, secrets, notebooks and commit messages:
```yaml
# .pre-commit-hooks.yaml (inside the engine repo)
- id: playbook-sync
  name: coding-agent-playbook sync (regenerate local output)
  description: Re-render the gitignored AGENTS.md/.claude/.continue/.opencode output after checkout or merge
  entry: playbook sync
  language: python
  pass_filenames: false
  always_run: true
  stages: [post-checkout, post-merge]
  minimum_pre_commit_version: "3.2.0"
- id: playbook-no-generated-output
  name: coding-agent-playbook guard (no generated output staged)
  description: Fail the commit when any staged path is gitignored generated output ([output] commit = false)
  entry: playbook sync --check-staged
  language: python
  pass_filenames: false
  always_run: true
  stages: [pre-commit]
  minimum_pre_commit_version: "3.2.0"
# LEGACY — only for [output] commit = true (generated output is committed).
- id: playbook-sync-check
  name: coding-agent-playbook sync check (legacy, [output] commit = true)
  description: Verify committed .continue/, .claude/, AGENTS.md are in sync with the installed playbook
  entry: playbook sync --check
  language: python
  pass_filenames: false
  always_run: true
- id: playbook-validate
  name: coding-agent-playbook validate (overlay authors)
  description: Validate canonical artifacts (only run when authoring an overlay)
  entry: playbook validate
  language: python
  pass_filenames: false
  always_run: true
  stages: [manual]
```
```yaml
# Static code-quality gate (§21.5): never the suite, even with [metrics] run_tests = true.
- id: playbook-metrics
  name: coding-agent-playbook metrics (static, non-regression vs HEAD)
  description: Static code-quality gate — fail when staged Python worsens vs HEAD
  entry: playbook metrics --baseline git:HEAD --no-run-tests
  language: python
  types_or: [python, pyi]
  require_serial: true
# Coverage gate (§21.5): RUNS YOUR TEST SUITE, so manual only.
- id: playbook-coverage
  name: coding-agent-playbook coverage (diff + non-regression; runs your test suite)
  description: Changed-line and total coverage vs HEAD — runs the project's test suite
  entry: playbook metrics --run-tests --select testing --baseline git:HEAD
  language: python
  pass_filenames: false
  types_or: [python]
  require_serial: true
  stages: [manual]
# Opt-in ML twins (§12.16, §12.19).
- id: playbook-notebooks
  name: coding-agent-playbook notebooks (no outputs committed)
  description: Fail when a staged notebook keeps cell outputs, embedded images or oversized output
  entry: playbook check-notebooks
  language: python
  types: [jupyter]
  stages: [pre-commit]
- id: playbook-scan-sinks
  name: coding-agent-playbook scan-sinks (no new unsafe deserialization)
  description: Fail when staged Python or notebook code adds pickle-based loads or other unsafe sinks
  entry: playbook scan-sinks --staged
  language: python
  types_or: [python, jupyter]
  pass_filenames: false
  stages: [pre-commit]
# The air-gapped secret scan (§12.15), every commit.
- id: playbook-secrets
  name: coding-agent-playbook secrets (no tokens or credential files committed)
  description: Fail when staged changes add a secret token or stage a credential file (masked output)
  entry: playbook scan-secrets --staged
  language: python
  pass_filenames: false
  always_run: true
  stages: [pre-commit]
# Commit-message convention: commitizen's own check, from the project environment.
- id: playbook-commit-msg
  name: commit message convention (commitizen)
  description: Fail a commit whose message breaks the repo's commitizen convention (cz check)
  entry: cz check --commit-msg-file
  language: system
  stages: [commit-msg]
  minimum_pre_commit_version: "3.2.0"
```
**The second block (v0.20).** `playbook-metrics` passes `--no-run-tests`, so the static-only promise of §21.5 holds even when `[metrics] run_tests = true` (that setting is for CI and manual runs). `playbook-coverage` runs the project's suite, so it is `stages: [manual]` (`pre-commit run playbook-coverage --hook-stage manual`, or move it to `pre-push`): changed lines at least 80% executed (`diff_coverage`) and total coverage not below `HEAD`. `playbook-secrets` runs on every commit: the stdlib, air-gapped stand-in for gitleaks and detect-private-key, which need a remote clone (§13.2, §17.3). `playbook-notebooks` and `playbook-scan-sinks` are opt-in ML twins of the notebook and deserialization hooks. `playbook-commit-msg` is commitizen's own `cz check` on every commit message, editor-composed and human ones included, with the convention from the project's `[tool.commitizen]` (default `cz_conventional_commits`) and no cut-over (every new commit conforms; `playbook ci` applies `cutover_date` to history, §12.11). It is `language: system`, so `cz` comes from the project environment and a machine without it fails loudly, and it needs the `commit-msg` hook type installed: `default_install_hook_types: [pre-commit, post-checkout, post-merge, commit-msg]`, or `pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge --hook-type commit-msg`. Every engine pre-commit id starts with `playbook-` (and every starter id with `coding-agent-playbook-`), which is how block-precommit-bypass recognises them, `SKIP=` included.

Stage names are pre-commit's hook-type names (`pre-commit`, `post-checkout`, `post-merge`, …; verified against pre-commit 4.7.0's `clientlib.STAGES`), introduced in pre-commit 3.2.0 — hence `minimum_pre_commit_version`. `post-checkout`/`post-merge` hooks receive no filenames, so `always_run: true` is required for them to run at all. A consumer wiring the default policy installs all three hook types (`pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge`; explicit `--hook-type` flags *replace* `default_install_hook_types`, so all three must be named):
```yaml
# consumer .pre-commit-config.yaml
default_install_hook_types: [pre-commit, post-checkout, post-merge]
default_stages: [pre-commit]     # keep other always_run hooks off checkout/merge
repos:
  - repo: https://github.com/msobroza/coding-agent-playbook
    rev: v0.1.0a0                # the engine version the project pins
    hooks:
      - id: playbook-sync
        additional_dependencies: [playbook-rules-bnp]   # every third-party overlay package / out-of-tree adapter (bundled plugins need none)
      - id: playbook-no-generated-output
        additional_dependencies: [playbook-rules-bnp]
```
**These hooks run in pre-commit's own venv.** `language: python` means pre-commit builds an isolated environment holding only the engine at `rev:` — not the project's environment. An overlay package or out-of-tree adapter must therefore be listed under `additional_dependencies` (and `rev` kept on the engine version the project pins, or hook runs and manual runs render with different engines). Without it the sync refuses to run (missing overlay, §4.2 step 1) or skips the adapter with a warning — it never silently re-renders without the org rules. Overlay users (and anyone pinning the engine in their project environment) should prefer the `repo: local` + `language: system` hooks `playbook init` writes (§13.2), which run the project's own `playbook`.
### 13.2 Template `.pre-commit-config.yaml` (written by `playbook init`)
`playbook init` renders this starter from the packaged template `src/coding_agent_playbook/templates/precommit/config.yaml.j2`. The template is engine wiring, not playbook content (its hook ids are duplicated in `precommit.py`), so it stays in the package rather than in `catalog/`. `precommit.py:precommit_template_dir()` returns its directory (`resources.files(ENGINE_PACKAGE) / "templates" / "precommit"`) and raises `PrecommitTemplateMissingError` (`the engine's pre-commit template was not found at <path>; reinstall coding-agent-playbook`) when the directory or `config.yaml.j2` is missing, instead of an `assert` that `python -O` strips; `cli.main` reports it as `error: <message>` with exit 2, like a missing catalog (§12). It is **air-gapped-friendly**: every hook is `repo: local` + `language: system`, so pre-commit never clones a remote hook repo (it would otherwise fetch each `repo:` URL into `~/.cache/pre-commit` on first run — impossible offline, which also satisfies the engine's "air-gapped-friendly" invariant). The tradeoff is that the consumer must have `ruff` and `mypy` installed in their environment; `language: system` runs the tools on PATH, it does not install them. The template is rendered with one variable, `output_commit` (the `[output] commit` policy), which selects the playbook hooks — the default `commit = false` variant is shown:
```yaml
# AUTOGENERATED starter by coding-agent-playbook `playbook init`.
# Air-gapped-friendly: all hooks are `repo: local` + `language: system`.
# Requires ruff and mypy installed in your environment.
minimum_pre_commit_version: "3.2.0"
default_install_hook_types: [pre-commit, post-checkout, post-merge]
default_stages: [pre-commit]
default_language_version:
  python: python3.12
fail_fast: false
repos:
  - repo: local
    hooks:
      # The playbook — re-render the local-only output after checkout / merge
      - id: coding-agent-playbook-autosync
        name: coding-agent-playbook sync (regenerate local output)
        entry: playbook sync
        language: system
        pass_filenames: false
        always_run: true
        stages: [post-checkout, post-merge]
      # The playbook — refuse commits that stage generated output
      - id: coding-agent-playbook-no-generated-output
        name: coding-agent-playbook guard (no generated output staged)
        entry: playbook sync --check-staged
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
      # The playbook — static code-quality gate (§21.5); --no-run-tests keeps it static
      - id: coding-agent-playbook-metrics
        name: coding-agent-playbook metrics (static)
        entry: playbook metrics --baseline git:HEAD --no-run-tests
        language: system
        types_or: [python, pyi]
        require_serial: true
      # The playbook — coverage gate; RUNS YOUR TEST SUITE, so manual-only
      - id: coding-agent-playbook-coverage
        name: coding-agent-playbook coverage (diff + non-regression; runs your test suite)
        entry: playbook metrics --run-tests --select testing --baseline git:HEAD
        language: system
        pass_filenames: false
        types_or: [python]
        require_serial: true
        stages: [manual]
      # The playbook — secret scan of every commit (stands in for gitleaks)
      - id: coding-agent-playbook-secrets
        name: coding-agent-playbook secrets
        entry: playbook scan-secrets --staged
        language: system
        pass_filenames: false
        always_run: true
        stages: [pre-commit]
      # Linting and formatting (ruff must be installed)
      - id: ruff
        name: ruff (lint + autofix)
        entry: ruff check --fix
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: ruff-format
        name: ruff format
        entry: ruff format
        language: system
        types_or: [python, pyi]
        require_serial: true
      # Type checking (mypy must be installed)
      - id: mypy
        name: mypy
        entry: mypy --config-file=pyproject.toml
        language: system
        pass_filenames: false
        always_run: true
```
`default_install_hook_types` makes a plain `pre-commit install` install the `post-checkout`/`post-merge` git hooks the auto-sync needs; `default_stages: [pre-commit]` keeps every hook without an explicit `stages` (notably the `always_run` mypy hook) from also running after each checkout/merge — pre-commit's default is *all* stages. With `[output] commit = true` the template instead renders the legacy `coding-agent-playbook-sync` hook (`entry: playbook sync --check`, every commit) and omits those three top-level keys.

**Commit-message hooks (v0.20).** Two more variables add `commit-msg` hooks, and `commit-msg` to `default_install_hook_types` (which the template then writes under `commit = true` too). `commitizen` — the repo opted into a convention, through `[tool.commitizen]` in `pyproject.toml` or `[hooks.commit_convention]` — adds `coding-agent-playbook-commit-msg` (`entry: cz check --commit-msg-file`, `stages: [commit-msg]`); `commit_trailers` — a trailer row is configured in `[hooks.git-commit-push-policy-guard]` — adds `coding-agent-playbook-commit-trailers` (`entry: playbook check-commit-trailers`, `stages: [commit-msg]`, §12.18). A consumer without either never gets a commit hook that cannot run.

Intentionally **not** shipped in the starter: generic-hygiene hooks (trailing-whitespace, end-of-file-fixer, check-yaml/-toml, detect-private-key, check-merge-conflict, check-added-large-files), gitleaks, and notebook hooks (nbstripout/nbqa) — all of which require cloning a remote repo. Secret scanning is covered without them: `coding-agent-playbook-secrets` runs the stdlib `playbook scan-secrets --staged` on every commit (§12.15); notebook hygiene is the opt-in `playbook-notebooks` hook of §13.1. `ruff format` already covers Python whitespace/EOF; a pre-push `pytest` hook can be added by the consumer as a `repo: local` entry if desired.
### 13.3 Merge with existing `.pre-commit-config.yaml`
If the consumer already has a config, `playbook init` appends only our playbook `- repo: local` hook block for the configured policy — the `coding-agent-playbook-autosync` + `coding-agent-playbook-no-generated-output` pair for `commit = false` (deduplicated on the guard's id), the legacy `coding-agent-playbook-sync` drift check for `commit = true` — and only when it is not already present. It never injects ruff/mypy into a config the consumer already curates, and it does not add top-level keys (`default_install_hook_types`, `default_stages`) to a file it does not own: the consumer installs the extra hook types with `pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge` (which `init` prints) and should confine their own `always_run` hooks with `stages:`/`default_stages`. A legacy `coding-agent-playbook-sync` hook (`playbook sync --check`) left over from before v0.16 is **swapped in place** for the `commit = false` pair when it is still byte-for-byte what `init` wrote (in the old starter or the old appended block) — it would otherwise report drift after every checkout/merge, since the output is no longer committed. A hand-edited one is left alone and `init` prints a `warning:` telling the user to delete it. When the merged config has no `default_stages`, `init` also prints a `note:` that the consumer's own `always_run` hooks need `stages: [pre-commit]` (or `default_stages: [pre-commit]`) before the `post-checkout`/`post-merge` hook types are installed. The current implementation is a text-based append; round-trip merging with `ruamel.yaml` (to preserve comments/ordering and surface version conflicts, e.g. a different ruff pin) can land later.
## 14. Distribution and versioning
### 14.1 Channels
- **Engine and overlays**: distributed via internal PyPI (Artifactory). No public PyPI for v1.
- **Pre-commit hooks**: distributed via internal git server.
- **Release builds come from the sdist.** The wheel force-includes `catalog/` (§5.1), and force-include ignores `.gitignore` in both directions: it would ship untracked ignored junk from a dirty tree, and it ships tracked files that match `.gitignore`, which the sdist drops. Releases are therefore built with plain `uv build` or `python -m build` (the sdist first, then the wheel from it), never `--wheel`. git and pre-commit installs always build from the tree, so a pytest guard asserts that `git ls-files -ci --exclude-standard` is empty (skipped outside a git checkout); its failure names each path and suggests a `!` negation in `.gitignore` instead of `git add -f`. An editable install also gets a shadow copy of the tree in `site-packages/coding_agent_playbook/_catalog/`; nothing reads it, because the package resolves from `src/` and `catalog_root` looks only under the package directory.
### 14.2 Versioning contract
SemVer applied to the **rendered output format**, not the Python API:
- **Patch** (`0.4.0 → 0.4.1`): rule wording improvements, bug fixes, no consumer action needed.
- **Minor** (`0.4.0 → 0.5.0`): new rules or prompts added, new optional features. Consumer re-runs `playbook sync`. Under `[output] commit = true` they review the regenerated diff; under the default `commit = false` the output is local-only, so the review happens on the engine/overlay release (its changelog and diff), or by comparing a local `playbook sync` before and after the bump.
- **Major** (`0.4.0 → 1.0.0`): breaking changes to artifact schema, adapter contract, or CLI surface. Consumer follows a migration guide.
### 14.3 Pinning policy
Consumers pin to a minor range: `coding-agent-playbook>=0.4.0,<0.5.0`. Overlays pin to the engine's minor range. Under `[output] commit = true`, Dependabot / Renovate bumps trigger a `playbook sync` and the regenerated diff lands in the PR for review. Under the default `commit = false` the PR only carries the dependency bump (rendered output is gitignored): reviewers read the engine/overlay release notes, or render locally before and after the bump.
### 14.4 Lockfile
`.coding-agent-playbook.lock` is a TOML file written by `playbook sync` (write mode) through the configured `StateSource` — local state under the default `[output] commit = false`, committed with the output under `commit = true`. Schema 2 (`sync/_dispatch.py` `LOCKFILE_SCHEMA`; `lockfile/model.py` `Lockfile` / `LockEntry` / `Provenance`) records three top-level keys and one `[[entries]]` table per generated file, sorted by path, each carrying the file's **provenance** — which artifact produced it and which adapter wrote it:
```toml
schema_version = 2
engine_version = "0.1.0a0"            # [engine] version from the consumer config
rendered_at = "2026-10-14T10:00:00Z"  # RFC 3339 UTC, when sync ran

[[entries]]
path = ".claude/CLAUDE.md"
sha256 = "e264be4d…"
bytes = 150
kind = "composite"
adapter = "claude_code"

[[entries]]
path = ".claude/rules/coding-agent-playbook.md"
sha256 = "fed44cc5…"
bytes = 7883
kind = "composite"
adapter = "claude_code"

[[entries]]
path = ".claude/skills/query-db/SKILL.md"
sha256 = "fc20ff82…"
bytes = 67
kind = "skill"
artifact_id = "query-db"
source = "<repo-local>"
adapter = "claude_code"

[[entries]]                           # a member rule's reference: its rule's provenance (§6.3.3)
path = ".claude/skills/python-coding/references/python-typing.md"
sha256 = "5d07…"
bytes = 2641
kind = "rule"
artifact_id = "python-typing"
source = "coding_agent_playbook"
adapter = "claude_code"

[[entries]]
path = ".continue/rules/10-python-house-style.md"
sha256 = "9c1e…"
bytes = 1834
kind = "rule"
artifact_id = "python-house-style"
source = "coding_agent_playbook"
adapter = "continue"

[[entries]]                           # one managed element of a shared file (v0.20)
path = ".claude/settings.json"
sha256 = "41ab…"                     # canonical JSON of this one matcher group
bytes = 212
kind = "runtime"
artifact_id = "registration:pre_tool_use"
adapter = "claude_code"
scope = "json:/hooks/PreToolUse"

[[entries]]                           # sync-level hook output: no adapter
path = ".coding-agent-playbook/hooks/guard_config.json"
sha256 = "07d2…"
bytes = 18340
kind = "runtime"

[[entries]]                           # a copied external-handler script
path = ".coding-agent-playbook/hooks/scripts/bnp-sql-pii-columns/check.py"
sha256 = "5be0…"
bytes = 2210
kind = "hook"
artifact_id = "bnp-sql-pii-columns"
source = "playbook_rules_bnp"
executable = true
```
| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| `path` | `str` | — | Repo-relative, forward slashes, resolved through the repo's own symlinks (with `.claude/skills -> ../.agents/skills` an entry reads `.agents/skills/…`). A written file that resolves outside the repo gets no entry (§4.2 step 8). |
| `sha256` / `bytes` | `str` / `int` | — | Hex digest and size of the file's bytes as written. |
| `kind` | `str` | `""` | `rule` / `prompt` / `skill` = the output of one artifact's `write_rule` / `write_prompt` / `write_skill` (a skill degraded to a prompt by an adapter stays `skill`); `composite` = a multi-source output: every path returned by `finalize` (`.claude/CLAUDE.md`, `.claude/rules/coding-agent-playbook.md`, `AGENTS.md`, the `agent_harness` tree) and any path returned for two different artifacts. `hook` = a hook's advisory file from `write_hook` (e.g. `.continue/rules/30-guardrail-<id>.md`) or a copied external-handler script; `runtime` = hook plumbing with no source artifact to edit: `guard_config.json`, the Claude Code launcher, the OpenCode shim and each managed element of `.claude/settings.json` (v0.20). `""` = unknown provenance (an entry read from a schema-1 lockfile). |
| `artifact_id` | `str` | `""` | Canonical artifact id (frontmatter `id`); `"registration:<canonical_event>"` for a managed hook registration and `"permission:<list>:<string>"` for a managed `permissions` / `sandbox` array string; `""` for `composite` and the other `runtime` files. |
| `source` | `str` | `""` | The artifact's `source_package`: `coding_agent_playbook`, an overlay package name, or `<repo-local>`; `""` for `composite`. |
| `adapter` | `str` | `""` | Entry-point name of the adapter that wrote the path; `""` when two different adapters returned the same path. |
| `scope` | `str` | `""` | `""` = the entry covers the whole file. `json:<pointer>` = one managed element of the JSON array at that pointer in a shared file (`json:/hooks/PreToolUse`, `json:/permissions/deny`, …), from the adapter's `managed_lock_entries` (§10.1); the element index is deliberately not recorded, since user inserts shift it. A path with scoped entries — `.claude/settings.json` — gets no whole-file entry. |
| `executable` | `bool` | `false` | The git-style exec bit of a copied hook script, compared on POSIX only. |

Every field after `bytes` is **omitted from the TOML when it holds its default**, so a composite entry carries no `artifact_id`/`source` keys, `scope` appears only on scoped entries, and `executable` only on a copied script that has the bit. Provenance is recorded by `playbook sync` wrapping each adapter's `write_rule`/`write_prompt`/`write_skill`/`finalize` call (`sync/_dispatch.py`); the adapter return type (`list[Path]`) is unchanged. The lockfile is the ownership record for generated files that cannot carry a sentinel (§4.3 exceptions: copied skill scripts and references, copied hook scripts, `guard_config.json`, and the managed elements of `.claude/settings.json`) and the only deletion authority inside a skill directory (§10.8). A lockfile that parses as TOML but has the wrong shape (a key missing or of the wrong type) raises `LockfileFormatError`, a `ValueError` naming the key and value. There is no `[overlay_versions]` or `[file_hashes]` table.

**Drift.** `playbook sync --check` re-renders into an empty scratch directory and byte-compares every generated file against the working tree (missing or different → exit 1); it reads the lockfile to find the orphans write mode would delete — a whole-file entry (`scope = ""`) not regenerated whose file still exists and that the leftover policy deletes (§12.3, §4.2 step 9). `playbook check` reports drift from the lockfile: each whole-file entry's path is re-hashed and compared with `sha256` (`missing:` / `hash mismatch:`, and `mode mismatch:` for an `executable` entry that lost its bit); for a scoped entry it parses the shared file and looks for an element under the pointer whose canonical hash equals `sha256` (`managed entry missing:` / `managed entry edited: <path>#<pointer>`, or `unreadable:` when the file cannot be parsed), so user edits elsewhere in the file are never drift (§12.4).

**Ownership.** Write mode settles orphans from the previous lockfile before stamping: pristine, untracked ones in a declared output location are deleted; every other orphan is **carried** into the new lockfile with its old entry unchanged (provenance included) — except a released one (§4.2 step 9), such as an entry that leaves the repo (an absolute path an older engine recorded for output linked out of the repo), which is dropped and never deleted. A scoped (`json:<pointer>`) entry is never an orphan: its file is shared with the user. Under the default `[output] commit = false` the lockfile is local state like the output it describes: it is always listed in the managed `.gitignore` block (`/.coding-agent-playbook.lock`) and never committed. The consumer's `.gitignore` is never a lockfile entry — it is a user file the engine only edits inside its managed block.

**Compatibility.** A schema-1 lockfile (`path`/`sha256`/`bytes` only) loads with every new field at its default, and the next `playbook sync` rewrites it as schema 2. An older engine reading a schema-2 file still loads it: its reader picks only `path`, `sha256` and `bytes` and ignores the other keys.
## 15. Eval abstractions
v1 shipped **Tier 0**: the task authoring format (Section 6.5), the loader, the validator, and a read-only CLI. **v1.1 makes Tier 1 live**: `HarnessRunner` executes one task end-to-end against an agent and scores it through the `Metric` / `Check` / `Rubric` model (§21). The **task-config redesign (v0.13, Tracks C1–C8)** then reshaped the *authored* format into the layered `[gate]` / `[rubric]` / `[verdict]` / `[aggregate]` model (§6.5.3): a task compiles into one per-trial `Rubric` of checks whose deterministic `[gate]` layer (file/metric checks, 0–1 normalized thresholds + non-regression vs the `setup/` baseline) is computable today, and whose judged `[rubric]` layer scores against the captured diff when a judge is configured (`--judge llm`, or any `coding_agent_playbook.judges` entry). With **no judge configured** the runner is deterministic-only (the rubric layer reports `available() is False` and is skipped — the verdict treats a skipped layer as neutral). §15.3 describes the as-built v1.1 runner; the design docs are `specs/prR-eval-runner.md` (R1), `specs/prR2-judge-r3-opencode.md` (R2), `specs/prR6-check-rubric.md` (the R6 `Metric`/`Check`/`Rubric` refactor), and **`specs/pr2b-task-config.md`** (the task-config redesign).
### 15.1 The Tier 0 / Tier 1 / Tier 2 ladder
| Tier | Capability | status |
| --- | --- | --- |
| 0 | Task schema, loader, validator, `playbook eval --list/--show` | **shipped (v1)** |
| 1 | Per-runner agent invocation + deterministic scoring (the `[gate]` layer: file + metric checks, 0–1 normalized non-regression) via the `Metric`/`Check`/`Rubric` model | **shipped (v1.1 R1)** |
| 2 | The `[rubric]` llm-judge layer (LLM-as-judge) | **shipped (v1.1 R2)** — opt-in `LLMJudge` via `--judge llm`; calibration is future work |
The ladder is deliberate: Tier 0 produces value (documentation, validation) immediately. Tier 1 makes the value computable. Tier 2 closes the loop on subjective quality. Each tier is independently shippable.
### 15.2 v1 abstractions (active)
These ship in v1 and back the `playbook eval --list` / `playbook eval --show` CLI.
```python
# coding_agent_playbook/evals/task.py
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class TaskSetup:
    files: list[Path]  # files in setup/ subdir, relative to task dir
    project_kind: str
    python_version: str
    frameworks: list[str]
    # Free-form facts the task wants the detector to mock.
    extra_facts: dict[str, object] = field(default_factory=dict)


@dataclass
class TaskInvocation:
    prompt_args: str  # what the user "types" after the slash command
    input_variables: dict[str, str] = field(default_factory=dict)


@dataclass
class Layer:  # one [gate] / [rubric] / [aggregate] block
    bind: dict[str, dict] = field(default_factory=dict)  # name -> raw handle binding
    expr: str | None = None  # boolean/aggregate expr over the handle names


@dataclass
class EvalTask:
    id: str
    prompt_id: str
    description: str
    source_path: Path  # where the task.toml lives
    source_package: str
    version: int = 1
    setup: TaskSetup = field(default_factory=TaskSetup)
    invocation: TaskInvocation = field(default_factory=TaskInvocation)
    gate: Layer | None = None  # the deterministic boolean layer
    rubric: Layer | None = None  # the llm-judge weighted layer
    verdict: str = "gate and rubric"  # [verdict].trial — boolean expr over the layers
    aggregate: Layer | None = None  # optional cross-trial pass@k / pass^k layer
```
The loader (`coding_agent_playbook.evals.loader.load_tasks`) walks each layer's `eval_tasks/` (the engine's `catalog/core/eval_tasks/`, a bundled plugin's or an overlay's, and the consumer's `playbook/eval_tasks/`), parses `task.toml` per directory, and produces a `list[EvalTask]`. Overlays add their tasks via the same entry-point mechanism as rules and prompts. `EvalTask.compiled()` (a thin wrapper over `evals._compile.compile_task`) turns the raw layer blocks into a `CompiledTask` — one per-trial `Rubric` (the present `gate`/`rubric` layer checks, ids `"gate"` / `"rubric"`), the parsed `[verdict].trial` AST, and the optional compiled `[aggregate]` layer + `trials_needed`.

The validator (`coding_agent_playbook.evals.validator.validate_tasks`) enforces:
- Each `task.toml` is well-formed (the loader parses it; a task reaching the validator already parsed).
- The `[gate]`/`[rubric]`/`[verdict]` schema **trial-compiles cleanly** — unknown `check`/`metric`/gate-`ref`/rubric-`ref`, a malformed handle binding, an `expr` identifier not in its `bind` keys, a rubric group's weights ≠ 1.0, a `[verdict].trial` naming an absent layer, or no layer at all.
- A light `[aggregate]` shape check (each handle names `pass_at_k`/`pass_pow_k`, an integer `k ≥ 1`, and an `over ∈ {gate, rubric, verdict}`).
- Each task's `setup.files` list matches files actually present in `setup/`.
- Each task's `prompt_id` resolves to a known prompt, and the prompt↔task back-reference is symmetric.

**Named-rubric / named-gate refs.** A handle may `{ref = "name"}` instead of inlining a check: in the **rubric** layer it resolves a *code-defined* rubric registered under `@register_rubric("code-review")` (`coding_agent_playbook.evaluators.rubrics` + the `coding_agent_playbook.rubrics` entry-point group), wrapped in a `ThresholdCheck` on its 0–1 composite; in the **gate** layer it resolves a *code-defined* composed gate registered under `@register_gate("name")` (`coding_agent_playbook.evaluators.gates` + the new `coding_agent_playbook.gates` group). A `Rubric` subclass declares its `CRITERIA = (("criterion", weight), …)`; `get_rubric(name)` returns `cls.define()` (a built `Rubric` of `JudgeCheck`s). The engine ships **no** builtin gates or rubrics — both are purely third-party extension points; in-tree registrations win on a name clash.

That's the entire active task surface.
### 15.3 The v1.1 runner (live — deterministic layers)
`HarnessRunner` is a concrete **template method**: `run_task` owns a fixed pipeline (materialize → render prompt → `_invoke_agent` → capture → score → assemble a `TaskResult`) and the single abstract per-assistant hook is `_invoke_agent`. Scoring runs through the `Metric` / `Check` / `Rubric` model (§21): the task's layer blocks compile (via `evals._compile.compile_task`) into one per-trial `Rubric` carrying the two named layer checks (ids `"gate"` / `"rubric"`), and a single `Rubric.evaluate` folds them into one report — so the deterministic `[gate]` layer (file checks + static/execution metric checks, 0–1 normalized non-regression vs the `setup/` baseline) is live. **The judged `[rubric]` layer is opt-in**: `run_task(task, scratch_dir, *, judge=None, samples=1, fail_fast=True)` takes an optional `Judge` (keyword-only) and threads it onto the `EvalContext`; with a judge set the rubric criteria score against the captured diff and fold into the same report, and with none (the default) the rubric layer reports `available() is False` and the report is deterministic-only. The per-trial **verdict** is then *derived* from the gate/rubric layer results (a skipped layer is neutral) via `[verdict].trial` — not re-run, so the judge / test-suite is never double-invoked. The cost-tiered scheduler (§21.4) runs checks cheapest-tier-first; `run_task` is **fail-fast by default** (a lost deterministic gate skips the costlier execution/judged tiers — for the default conjunction verdict `gate and rubric`, a failing gate check never spends an LLM call; a task whose verdict or aggregate a skipped layer could change is always scored in full, see `CompiledTask.short_circuit_safe`), and `playbook eval --run --full-scoring` forces every check to run. When the task carries an `[aggregate]` block the runner runs `N = max(k)` trials and the aggregate `pass@k` / `pass^k` checks reduce them into the task verdict (§21.2.5); omit it ⇒ a single trial.
```python
# coding_agent_playbook/evals/runner.py     (v1.1, live)
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
@dataclass
class AgentRun:
    transcript: str
    returncode: int                              # 0 = the agent loop completed
@dataclass
class TaskResult:
    task_id: str
    harness: str                                 # the runner's entry-point name, e.g. "fake", "claude_code"
    report: EvaluationReport                      # the per-trial Rubric.evaluate report (the gate + rubric layer checks)
    passed: bool                                  # the TASK verdict (derived [verdict].trial, or the [aggregate] pass/fail; if that is skipped, every trial passed)
    aggregate_score: float                        # report.composite (single-trial), or the aggregate reliability score (the trial pass rate if skipped)
    duration_seconds: float
    transcript: str                              # full agent transcript for debugging
    trials: list[TrialResult] = field(default_factory=list)   # one per trial (one for N=1)
    aggregate: CheckResult | None = None          # the graded [aggregate] check, when present
@dataclass
class EvalReport:                                 # aggregate over several tasks for one harness
    engine_version: str
    harness: str
    task_results: list[TaskResult]
    aggregate_pass_rate: float                    # mean of tr.passed across task_results
    timestamp: str
    @staticmethod
    def pass_rate(task_results: list[TaskResult]) -> float: ...   # mean(tr.passed), 0.0 when empty
class PromptResolutionError(RuntimeError):
    """A task's prompt could not be resolved (strict mode) or failed to render."""
class HarnessRunner(ABC):
    """Invoke an agent for one task and grade the result (template method)."""
    name: str                                    # the coding_agent_playbook.runners entry-point key
    requires_resolved_prompt: bool = False       # real runners set True (strict render_prompt)
    def run_task(self, task, scratch_dir, *, judge=None, samples=1, fail_fast=True) -> TaskResult:   # CONCRETE template
        baseline = materialize(task, scratch_dir)            # copy setup/ + git-init baseline commit + pristine snapshot
        prompt   = render_prompt(task, strict=self.requires_resolved_prompt)
        run      = self._invoke_agent(prompt, scratch_dir)   # ← the ONLY per-assistant step
        candidate = capture(scratch_dir, baseline, run.transcript)   # post-agent tree + git diff + transcript
        report   = score(task, baseline, candidate, judge=judge, samples=samples, fail_fast=fail_fast)  # one Rubric.evaluate (§15.3.1)
        return TaskResult(task_id=task.id, harness=self.name, report=report, ...)
    @abstractmethod
    def _invoke_agent(self, prompt: str, scratch_dir: Path) -> AgentRun:
        """Drive the agent against scratch_dir and return its raw outcome. The only per-assistant step."""
        ...
```
**Result model (Option B).** `TaskResult` carries one representative `report: EvaluationReport` (the first trial's, covering the `[gate]` / `[rubric]` layer checks) plus the convenience aggregates `passed` / `aggregate_score` / `duration_seconds` / `transcript`, and — for a multi-trial `[aggregate]` task — `trials` (every per-trial `TrialResult`) and `aggregate` (the graded aggregate `CheckResult`). `passed` is the **task** verdict: the single trial's derived `[verdict].trial` for a non-aggregate task, or the `[aggregate]` layer's pass/fail when the task aggregates across trials — unless that layer is skipped (its `over` axis ran in fewer than `k` trials, e.g. `over = "rubric"` with no judge): then `aggregate` is a `status="skipped"` result, `passed` holds only if every trial's verdict passed, and `aggregate_score` is the trial pass rate (§21.2.5). A gate predicate is a deterministic `Check` whose result rides on `report.checks`; `CheckResult` is the per-check outcome of `Check.grade`. `EvalReport.pass_rate` is the mean of `tr.passed`.

Concrete runners (discovered via the `coding_agent_playbook.runners` entry-point group — never instantiated directly):
- **`FakeRunner`** (`name="fake"`, `evals/fake_runner.py`) — the **hermetic default + test driver**. Its `_invoke_agent` applies a caller-supplied deterministic mutation (`Callable[[Path], None]`; default a no-op) to the scratch tree and returns a canned transcript. No network, no CLI; every unit test uses it. It leaves `requires_resolved_prompt=False`, so it tolerates the placeholder `render_prompt` emits for a synthetic test task.
- **`ClaudeCodeRunner`** (`name="claude_code"`, `evals/claude_code_runner.py`) — a **thin, opt-in real runner**. Its `_invoke_agent` drives the Claude Code CLI via a plain `subprocess` arg-list (default `claude -p <prompt>`) bound to the scratch repo and captures stdout/stderr as the transcript. Lazy — no top-level CLI import; `available()` returns `False` when the `claude` binary is not on `PATH` (mirroring the `radon` lazy-availability pattern), so it is cleanly skippable and **never exercised in CI**. It sets `requires_resolved_prompt=True`.
- **`OpenCodeRunner`** (`name="opencode"`, `evals/opencode_runner.py`) — a second thin, opt-in real runner, the same shape as `ClaudeCodeRunner`. Its `_invoke_agent` drives the OpenCode CLI via a plain `subprocess` arg-list (default `opencode run <prompt>`) with `cwd=scratch_dir` and merges stdout/stderr into the transcript. Lazy — no top-level CLI import; `available()` returns `False` when the `opencode` binary is not on `PATH`, so it is cleanly skippable and **never exercised in CI**. It sets `requires_resolved_prompt=True`. The `command`/`timeout` are configurable (a `{prompt}` token is interpolated, else the prompt is appended).

`ContinueCLIRunner` remains future work (not yet implemented).

**`render_prompt` strictness.** `render_prompt(task, strict=…)` (`evals/prompting.py`, re-exported from the runner) resolves `task.prompt_id` to its `Prompt` (scanning the `prompts/` directory of the layer that holds the task: `evals/prompting.py:_infer_prompts_dir` maps `<layer>/eval_tasks/<dir>/task.toml` to `<layer>/prompts`, whatever the layer — `catalog/core/`, an overlay's `resources/`, or `playbook/` — and returns `None` when the task directory's parent is not `eval_tasks`; it searches for no `resources` path segment and does not resolve symlinks. Since v0.19 a repo-local task under `playbook/eval_tasks/` therefore finds `playbook/prompts/`; before, it never found a prompt) and renders it like `playbook sync` would for the task's `setup/` tree. The Jinja context is the detector facts for `setup/` overlaid with the `[setup]` mock facts (`project_kind` unless left at its `python-unknown` default; extra keys win, and list-shaped name maps such as `ml_stack = ["torch"]` are normalized to the detector's `{name: spec}` shape), plus `project_name`/`project_description` from `setup/pyproject.toml` (falling back to the task id and `""`), `engine_version`, and the task's `input_variables` (which win). The body is followed by the `## Reference rules` appendix of its `includes_rules` (v0.21, D15, D22): the text Continue gets, since the eval scratch repo has no synced skills a `## Before you start` pointer could name. Its rules resolve from the engine rules plus the task's overlay package's and `setup/playbook/rules/`, filtered by `applies_if` with `has_file` anchored at `setup/` (§6.2.5 silent omission), and load only for a prompt that lists `includes_rules`. Plain `.md` prompts pass through Jinja-free but still get the appendix; the `rule()` helper no longer exists, so a prompt still calling it fails to render. A prompt that resolves but fails to render raises `PromptResolutionError` in either mode. When the prompt cannot be resolved: a *real* runner (`requires_resolved_prompt=True`) raises `PromptResolutionError` — a live agent must never be driven with a placeholder; the hermetic `FakeRunner` (`strict=False`) tolerates a stable placeholder because the deterministic scoring layers never read the rendered text.

#### 15.3.1 Scoring bridge (`evals/scoring.py`)
`score(task, baseline, candidate, *, judge=None, samples=1, fail_fast=False) -> EvaluationReport` produces one report covering both layers. It compiles the task's layer blocks into the per-trial `Rubric` (`task.compiled().per_trial`; §6.5.3), **walks the compiled check tree** to discover which metrics the gate/rubric checks reference, pre-measures them into a `MeasurementSet`, and runs `Rubric.evaluate`. The two named layer checks (`id="gate"` / `id="rubric"`) draw on the checks compiled from the handle tables:
- **`[gate]` metric checks** — `ThresholdCheck` / `NonRegressionCheck` over a registered `metric=` grade a `MeasurementSet` the bridge builds up front: **static** metrics measured per candidate `*.py` file (label = tree-relative path so a candidate matches its baseline counterpart), **execution** metrics run a `ProjectHandle` over the candidate tree (only when an execution metric is referenced — `run_tests` is *inferred*) — both with the baseline measured on the **pristine `setup/` snapshot** so non-regression compares against the untouched setup, not the post-agent tree. Thresholds and `max_worsening` are **0–1 cutoffs on the metric's normalized score** (every metric owns a `Normalizer`; §21).
- **`[gate]` file checks** — `FileExistsCheck` / `FileContainsCheck` / `FileUnchangedCheck` / `FileForbiddenCheck` (`evaluators/checks/files.py`) ignore the `MeasurementSet` and read the candidate tree from `ctx.tree` (`available()` is `False` without one); `FileUnchangedCheck` compares candidate bytes against the `setup/` snapshot via `ctx.baseline_tree`. Each is a pure gate (`required=True`, `weight=0.0`).
- **`[gate]` answer checks** — `AnswerMatchesCheck` (`evaluators/checks/answer.py`, `{check = "answer_matches", pattern = …}`) regex-searches the graded artifact (`ctx.artifact`, below) instead of the tree, so a review-only task can be gated deterministically on its *conclusion*. Fail-closed: always `available()`, so an empty artifact fails rather than skipping. See §21.2.4.
- **`[rubric]` judge checks** — the `JudgeCheck`s in a `rubric` group (and standalone `judge=` checks) score the graded artifact (`ctx.artifact`) into a `0-1` leaf (averaged over `samples`), feeding the rubric-group composite and gating on the group's `fail` (or the criterion's `threshold`). They are JUDGED-cost so the scheduler runs them last, and **`available()` is `True` only when `ctx.judge is not None`** — with no judge (the default) the whole rubric layer reports `status="skipped"`. "Deterministic-only" is **simply no judge configured**; there is no `ProgrammaticOnlyJudge`.

**The graded artifact (`ctx.artifact`).** `_graded_artifact(candidate)` is the candidate's captured `git diff` when it is non-empty, and its **transcript** otherwise. An *edit* task is graded on what the agent did, so its diff is the artifact — unchanged, and the only case that existed before. A *review* task is graded on what it **said**: such a task forbids edits (its gate is `file_unchanged`), so a well-behaved agent leaves the diff empty and its whole contribution is the transcript — grading that empty diff scored every review task against nothing at all. The discriminator is the diff rather than anything declared on the task, because a task does not announce its kind and an edit task whose agent did nothing has no diff to grade either. This is byte-identical for any task with a non-empty diff.

Both layer checks flow through one `Rubric.evaluate(ctx, measurements, *, strict, fail_fast)` into a single `EvaluationReport` whose `report.checks` carry the gate/rubric `CheckResult`s. The bridge then **derives** the per-trial verdict from those results (`evals._compile.verdict_passed` over `[verdict].trial`, skipped-neutral) and writes it onto `report.passed` — the layers ran once; the verdict is a boolean fold, not a third check. `fail_fast` (the runner's default; `--full-scoring` flips it off) lets the cost-tiered scheduler short-circuit once a required gate check fails, so a failing deterministic gate spares the execution/judged tiers (the LLM judge is never invoked) — for a task whose result the skip cannot change, i.e. a pure-conjunction verdict over every layer (the default `gate and rubric`) and no aggregate over a skippable layer; any other task is scored in full (see `CompiledTask.short_circuit_safe`).

### 15.4 Why the eval abstractions live in one tree
The `coding_agent_playbook/evals/` package ships `task.py`, `loader.py`, `validator.py` (active since v1), the task-config compiler trio `_expr.py` (the boolean-expression DSL) + `_handles.py` (the handle Factory/Composite builder) + `_compile.py` (the layer compiler + derived verdict), `runner.py` + `fake_runner.py` + `claude_code_runner.py` + `opencode_runner.py` + `scoring.py` (live since v1.1 R1), and `judge.py` (**live since v1.1 R2**). `judge.py` defines the concrete-able `Judge` ABC — **Option A**: the per-criterion primitive `score_criterion(criterion, artifact, n=1) -> float` (0–1, n-sample average) is canonical, and the batch `score(rubric, transcript, scratch_dir_state) -> list[float]` is a thin wrapper that maps it over the rubric — plus the opt-in `LLMJudge` (`name="llm"`, shells out to the `claude` CLI, `available()`-gated, never in CI) and the test-only `StubJudge`. A configured judge that cannot score — `LLMJudge`'s CLI exits non-zero, times out, or answers anything but exactly one number in `[0, 1]` — retries a bounded number of times (default 2, no backoff) and then raises `JudgeError`; it never degrades to a number (an `"API Error: 529"` used to clamp to a perfect `1.0`). `prompting.py` renders a task's prompt the way `playbook sync` renders it for Continue — the `## Reference rules` appendix of its `includes_rules`, built from the `applies_if`-filtered engine (+ the task's overlay) rules (§15.3, D22), and a Jinja context of detector facts over `setup/` overlaid with the task's mock facts, plus `project_name` from `setup/pyproject.toml`. This means:
- Overlay authors writing tasks can import `EvalTask`, `TaskSetup`, etc. for type hints in their own tooling.
- The module layout is stable across the v1 → v1.1 progression; only the placeholder bodies get filled in.
- The `[project.entry-points."coding_agent_playbook.runners"]` group is populated (`fake`, `claude_code`, `opencode`); the `coding_agent_playbook.judges` group is populated with `llm`; the engine ships no builtin `coding_agent_playbook.gates` / `coding_agent_playbook.rubrics` / `coding_agent_playbook.checks` entries — those are the third-party extension points a task references by `ref`/`check` name.
## 16. Testing strategy
### 16.1 Unit tests
- `tests/detector/test_facts.py` (and `test_predicate.py` for `applies_if`) — synthetic `pyproject.toml` files in `tests/fixtures/repos/`; assert facts dict matches expected.
- `test_renderer.py` — render templates with hand-crafted context; assert exact output.
- `test_overlays.py` — registration, ordering, override resolution.
- `lockfile/test_model.py` — hash compute, drift detection.
- `skills/test_membership.py`, `skills/test_document.py` — skill composition (§6.3.3): membership and gating, the composed description and its `and N more` truncation, the references index, the reference text and the Where section. `tests/cli/test_validate_skills.py` pins the V1–V14 and W1–W3 lines of `playbook validate` (§12.6), and `tests/cli/test_sync_skill_references.py` runs a sync end to end.
- The docs-consistency tests (`tests/unit/test_docs_*.py`) read SPEC, README, MIGRATION, `catalog/README.md` and `CONTEXT.md`, never engine behaviour: `test_docs_glossary.py` pins the glossary pointer, every `CONTEXT.md` term, the `skill` field of §6.1 and the core skills of §6.3, and `test_docs_migration_skills.py` the v0.21 MIGRATION section, quoting `SCOPED_RULE_NEEDS_SKILL_MESSAGE` verbatim.
- `generated_output/test_gitignore.py` — managed-block entries (skill-dir collapse under any root, escaping verified against real git), append/replace/idempotence, CRLF and missing-final-newline preservation, malformed markers, removal.
- `sync/test_git_client.py` — `SubprocessGitClient` against throwaway repos (guarded on git being on PATH, hermetic git env) plus its silent failure modes; `playbook sync` tests inject `tests/fakes.py::FakeGitClient` instead of patching `subprocess`.
### 16.2 Adapter tests (golden file)
Each adapter has a directory of input/output pairs:
```
tests/fixtures/golden/continue/python-typing/
├── input.facts.toml
├── input.rule.md.j2
└── output.md                    # expected exact bytes
```
Test asserts the adapter output matches `output.md` byte-for-byte. Update via `pytest --snapshot-update`.
### 16.3 Integration tests
`tests/integration/test_end_to_end.py` builds a synthetic consumer repo in a `tmp_path`, runs the full `playbook init` → `playbook sync` flow, and asserts the resulting file tree matches expectations.
The **reference probe** (`tests/_budget_probe.py`, synced once per module by `tests/integration/conftest.py`: a FastAPI + ML service with a pytest suite and a notebook, hooks on, both bundled plugins, the adapters `claude_code`, `opencode`, `shared_skills` and `continue`) carries two gates. `tests/integration/test_context_budget.py` enforces the context budget: the always rules plus the Where map at most 800 words, the two always sections alone at most 240, `AGENTS.md` before its Guardrails section at most 1,500 (the whole file is a strict xfail until the guardrails shrink to one line each), each core skill description at most 300 characters, core descriptions at most 2,000 in total, core plus every bundled plugin at most 6,000. `tests/integration/test_core_skills.py` pins the core skill inventory, each scoped rule's owning skill, the description shape, the Where phrases, plain-markdown bodies within 500 lines with references one level deep, and the emitted skills on the probe; plugin skills are exempt from its static checks, because their vendored or distilled text fails them as written. `tests/integration/test_core_always_rules.py` reads the catalog, not the probe: it pins the eight house-style bullets, the two project-context reminders and one owner, `python-data-shapes`, `python-idioms` or `python-classes-and-protocols`, for every item that left the house style. Two more gates render core rules with the probe's detector facts (`reference_probe_facts`, `render_core_rule`): `tests/unit/test_core_rule_shapes.py` bounds every core scoped rule to 100 lines and 750 words, the size one reference read takes in, and `tests/unit/test_distilled_content_policy.py` keeps distilled content within the D8 import policy (no dropped recommendation in a core rule or prompt, one owner per moved topic, a credit for every distilled rule).
### 16.4 CI
GitHub Actions (`.github/workflows/ci.yml`, ubuntu, Python 3.12 and 3.13) runs the tools directly rather than through pre-commit, installed with pip and first-party actions only:
1. `python -m pip install -e ".[dev]"` (no `metrics` extra: the gate must pass without radon)
2. `ruff check .` and `ruff format --check .`
3. `mypy` (strict)
4. `pytest -q` (coverage floor 80%), which also runs `playbook validate` over the engine's own content and the docs-consistency tests
5. `--version` smoke tests of `playbook`, `coding-agent-playbook` and `playbook-hook`
6. a `playbook-hook simulate` smoke test: the committed destructive-command fixture config denies `rm -rf /` (harness-facing exit code 2, §12.13)

The same four tools from the repo root, with no path arguments, cache-free and without radon, are the CI-parity gate every change must pass locally. A consumer's pull-request job runs `playbook ci` (§12.11).

A **`wheel-smoke`** job (Python 3.12, pip only) proves the built wheel carries `catalog/` and works without a checkout. In order:
1. `python -m pip install build && python -m build`, which builds the sdist and then a wheel from it.
2. Assert that the wheel's `coding_agent_playbook/_catalog/**` entries equal `git ls-files catalog`, mapped to `_catalog/`.
3. Install the wheel non-editable into a fresh venv and run `playbook --version`.
4. In an empty scratch git repository outside the checkout (`git init`: `init` turns the lifecycle hooks on, and hooks are git-only, so outside a work tree sync would warn), run `playbook init --non-interactive --name smoke --kind python-library --overlays coding_agent_playbook.plugins.superpowers,coding_agent_playbook.plugins.python_design </dev/null`. Assert exit 0, no `warning:` line, and that both `.claude/skills/brainstorming/SKILL.md` and `.claude/skills/python-design-review/SKILL.md` exist.
5. In that same directory, run `playbook eval --list </dev/null` and assert the output contains `23 eval tasks`, a count that comes from the core content only.
6. In that same directory, run `playbook-hook simulate pre_tool_use --format json` on the `bash_rm_root` golden payload and assert `exit_code == 2`: the wheel's own `catalog/core/hooks/` rendered a working destructive-command-guard.
### 16.5 Backwards compatibility tests
A `tests/compatibility/` directory contains a frozen consumer repo from v0.3 with its expected generated output. CI asserts v0.4 still generates compatible output (or that the migration is explicitly documented).
### 16.6 Hook tests (v0.20)
Hook code is tested where it lives, hermetically, and never against a real harness in CI:
- **Layout.** Runtime tests in `tests/hook_runtime/`, pack and tool-hook tests in `tests/hook_runtime/handlers/` (one sub-directory per pack: `safety/`, `verify/`, `audit/`, `protect/`, `feedback/`), security-library tests (secret patterns, PII checksums, the trust store, the audit writer) in `tests/security/`, adapter rendering in `tests/adapters/`, and sync, check, validate and twin commands in `tests/cli/`.
- **Named fakes through `RuntimeDeps`.** Every external effect of the dispatcher has one injected seam — harness I/O, git (`GitPort`), processes, the clock, the trust store, state — with named fakes in `tests/hook_runtime/fakes.py` (`FakeGit`, `FakeProc`, `FakeClock`, `FakeTrustStore`, …); an autouse fixture gives every in-process dispatch a `FakeProc` that fails on any unscripted subprocess, so a missing binary in CI can never pass silently. `SafeGit` itself is tested against throwaway real repositories (a clean filter that must never run, an untracked secret that must never be read).
- **Golden payloads.** `tests/fixtures/hook_payloads/{claude_code,opencode,foreign}/<event>/<case>.json`, each with the exact expected wire output beside it, served by the root `hook_payload` fixture; the `foreign` set (VS Code, Copilot CLI, Cursor) pins the inert check of §10.3.2.
- **Red-team tables.** Parametrized shell-parsing, path, combination and failure-policy cases: wrappers and `bash -lc`, heredocs, Windows paths, symlinks into `.git/`, a raising guard, a usage error that must never become exit 2.
- **Import budget.** In the default run, a fresh `-I -X importtime` dispatch per hot-path branch asserts that no forbidden module (`jinja2`, `yaml`, `importlib.metadata`, `argparse`, the CLI, renderer, adapters, evaluators, …) is imported.
- **Shim and launcher.** The OpenCode shim's wire-parse slice runs under node (skipped without it) and is pinned by sha256 to a Python port; the launcher runs under `sh` against fake dispatchers.
- **Gated tests.** Wall-clock latency budgets run only with `PLAYBOOK_LATENCY_TESTS=1` and assert the excess over a bare interpreter start (the default run keeps one generous N = 3 smoke); the real-OpenCode end-to-end test runs only with the CLI on `PATH` and `PLAYBOOK_E2E_OPENCODE=1`, like the `PLAYBOOK_E2E_CLAUDE=1` runner and judge smokes. None runs in CI.

## 17. Security and operational considerations
### 17.1 Air-gapped operation
- **No network calls at sync time.** All engine content is bundled in the package (the wheel's copy of `catalog/`).
- **No HTTP-handler hooks shipped by default.** HTTP hook handlers are not expressible in the canonical `Hook` schema and are rejected by `playbook validate` (rule H8, §12.6); neither are async, prompt, agent or input-rewriting handlers.
- **Hooks never reach the network (v0.20).** Guards never resolve or connect to a host, tools are never downloaded (a guard uses a tool only when it is already installed and pinned), there is no telemetry, and the decision and audit logs stay on the machine (§17.4).
- **Internal PyPI only.** No public PyPI dependency required for runtime; `uv` itself is the only binary dependency for the install flow.
### 17.2 Dependency allowlist
For BNP, the overlay package ships a rule (`30-bnp-banking-dependencies`) that lists approved third-party packages. The rule appears in every harness's context, so the assistant won't suggest unapproved libraries. This is enforcement-by-convention; actual enforcement happens at CI time via a separate package-check step.
### 17.3 Secrets
- Secret paths are defined once, in `coding_agent_playbook/security/patterns.py`: a path is secret when it matches a `SECRET_PATH_GLOBS` entry (`.env*`, `*.pem`, `*.key`, `*credentials*`; key stores and SSH private keys; `.netrc`, `.pypirc`, `.npmrc`, `pip.conf`, `uv.toml`, `.git-credentials`, `.vault-token`, `krb5cc_*`; `*.tfstate`, `*.tfstate.*`, `*.tfvars`, `*.tfvars.json`, `*.kdbx`; per-user stores under `~/` such as `~/.aws/**` and `~/.ssh/**`) not cancelled for it — by a `SECRET_PATH_EXEMPT` entry (`.env.example`, `.env.sample`, `.env.template`, `.env.dist`, SSH public keys), which cancels every glob, or by `SECRET_GLOB_EXEMPT`, which cancels one glob only: source files such as `credentials.py` are spared by `*credentials*` but `.env.credentials.py` stays secret through `.env*`. `security/paths.py`'s `is_secret_path(path, *, home)` decides from the path string alone and never opens the file; the caller passes the home that anchors the `~/` globs, and matching is case-insensitive on macOS and Windows.
- The detector never opens a secret path: it reads only `pyproject.toml`, and its filesystem walks skip every secret path. `playbook sync --check` copies nothing from the working tree — it renders into an empty scratch directory and reads its inputs in place (§12.3) — and its orphan scan never opens a secret path or follows a file symlink (`security/files.py::is_secret_file` judges a path by its spelling and by its resolved target). Skill copies refuse secret paths and links leaving the skill's source directory in every mode (§10.8), so no secret file reaches the scratch tree, a skills root, `.agents/skills/` or the lockfile; `playbook validate` warns about each refused file.
- **Secret scanning without a download (v0.20).** The engine ships neither gitleaks nor detect-private-key — both need a remote clone, which an air-gapped starter cannot do (§13.2) — and never downloads or runs gitleaks. Its own stdlib scanner stands in for them: the `playbook-secrets` pre-commit hook (`coding-agent-playbook-secrets` in the starter) runs `playbook scan-secrets --staged` on every commit, `playbook ci` scans the branch (§12.11, §12.15), and the in-session guards — secrets-path-guard (agent reads and writes of credential paths), secret-content-guard (tokens in written content and pushed ranges) and stop-diff-sweep — use the same rules (`security.secrets`) and the same path catalog (`security.paths`). Findings are always masked; credential files are judged by path and never read.
- No log statement in the engine ever logs config values; only structural facts (counts, paths).
### 17.4 Audit log
Every engine log is append-only JSONL written by one module, `security/audit.py` (`append_jsonl`): a line is one `O_APPEND` write of at most 4 KiB, so concurrent writers never interleave; `O_NOFOLLOW` refuses a log swapped for a symlink; files are mode 0600 and rotate by size under a bounded lock that never stalls a tool call. The hook logs live under the per-worktree state root `<git-dir>/playbook-hooks/`, never in the working tree (v0.20):
- **guard-decision-log** (`decisions-YYYY-MM.jsonl`, on by default with hooks): one line per deny, ask, warn, override, degraded or escape event, and **no content** — never a command, path, prompt, reason or environment value; the writer refuses any record key outside its fixed set. `playbook-hook doctor` summarizes it (§12.13).
- **local-audit-log** (`audit-YYYY-MM.jsonl`, an overlay-enabled mechanism): one structure-only activity line per event, with an optional hash chain and `[guardrails.audit] retain_days` retention.

A `playbook sync` audit line — JSON, one per invocation, to `.coding-agent-playbook.log` (gitignored) — is a design target that will go through the same writer; sync writes no log yet:
```json
{"timestamp": "2026-05-20T10:30:00Z", "command": "sync", "engine": "0.4.0", "overlays": {"bnp": "0.2.0"}, "files_written": 18, "duration_ms": 340}
```
For BNP, the overlay can extend this to write to a central audit endpoint at sync time (the only network egress the BNP overlay would add, and explicitly opt-in).
## 18. Rollout plan
### 18.1 Phase 0 — engine alpha (internal, 1-2 weeks)
- Build tracks 1-4 from the PR plan
- Test in Max's own repos (`conversational_core`, plus one ML/DS team repo)
- No external announcement
### 18.2 Phase 1 — engine beta + BNP overlay (2-4 weeks)
- Build tracks 5-6
- Author the BNP overlay (Track 7 content)
- Onboard 3-5 friendly teams; collect feedback
- Iterate on rule wording based on observed agent behavior
### 18.3 Phase 2 — engine 1.0 + open source release
- Move engine repo to a public namespace (GitHub, Apache-2.0)
- BNP overlay stays private; documented as the canonical example overlay
- Internal announcement; opt-in for any BNP team
- Write a Medium / engineering blog post describing the design
### 18.4 Phase 3 — v2 features
- MCP server config management
- Cursor and Codex CLI dedicated adapters
- Eval harness implementation
- Auto-suggestion of new rules from PR review patterns
## 19. Open questions
1. **Should overlay packages be allowed to ship adapters?** (E.g. a community Cursor adapter via overlay.) Currently the design says yes via entry points; we should validate no security implications. *Partially answered in v0.20 (PR K), for executable hook code:* overlays are data-only by default. An overlay's external-command hook or out-of-tree handler runs only when the consumer lists the overlay in `[hooks] allow_code_from` (committed, reviewed), and an external command additionally needs a user-local trust-on-first-use approval; `mandatory` overlay hooks can only add (Section 11.6). Overlay-shipped adapters are still discovered through entry points without such a gate, so that half stays open.
2. **Lockfile granularity.** Per-file hashes vs. content-addressable single hash. Current spec is per-file; simpler but more lock churn. Revisit if churn becomes a problem.
3. **Migration of existing `.continue/rules/` content.** If a consumer already has rules they hand-authored, `playbook init` should detect and offer to convert them to canonical templates. Out of scope for v1, but worth scoping in v2.
4. **Multi-language support.** v1 assumes Python. The architecture is language-agnostic (rules are just markdown), but the detector is Python-specific. v2 would add JS/TS detection. Defer.
5. **Versioning of overlays vs. engine.** Currently overlays pin the engine's minor range. Is that the right contract? Or should overlays declare a `compatible_engine_versions` field explicitly?
6. **Glob/tag-based rule inclusion in prompts.** Currently `includes_rules:` requires explicit rule IDs. A natural follow-on is `includes_rules_matching: { tags: ["python", "testing"] }`. Rejected for v1 for readability reasons (see Section 6.2.5); revisit in v2 if explicit lists become unwieldy.
7. **Cross-prompt rule sharing.** If three prompts all `includes_rules: [python-typing, pytest]`, the rule content is duplicated three times in three rendered files. Acceptable for v1; v2 might explore a shared "context library" referenced from prompts.
8. **OpenCode plugin generation.** *Resolved in v0.20 (PR K).* OpenCode's only lifecycle hook mechanism is JS/TS plugins under `.opencode/plugin/` or `.opencode/plugins/`, subscribing to runtime events (`tool.execute.before`, `session.idle`, etc.). The engine does not generate per-hook plugin code. It generates **one** static shim, `.opencode/plugins/playbook-hooks.js` (OpenCode V1 plugin API), which forwards `pre_tool_use`, `post_tool_use`, `session_start` and `stop` to the same `playbook-hook` dispatcher Claude Code uses, so the hook logic stays in canonical `Hook` artifacts and engine Python (Section 6.6.7). The API gaps are accepted and labelled: `ask` degrades to deny (OpenCode has no ask primitive), Stop is evidence-only, and session context goes through an experimental API. Every other plugin stays the user's. The regulated-overlay use case this question named ships as overlay-tier engine mechanisms that an overlay activates: `pii-prompt-guard` (user prompts; Claude Code only, since OpenCode does not render `user_prompt_submit`) and `sensitive-data-read-guard` (`pre_tool_use` reads, on both harnesses).
9. **OpenCode agents as a first-class artifact.** OpenCode supports named modes (`build`, `plan`, custom agents) with distinct system prompts, models, and permissions, defined in `.opencode/agent/<name>.md`. Claude Code subagents are conceptually similar. v1 treats agents as out of scope; users author them by hand. v2 could add a fifth artifact category — but the degradation story for harnesses without named agents (Continue, Codex) is unclear. Revisit when a concrete use case appears.
10. **HarnessRunner invocation contract.** v2 needs a uniform way to programmatically invoke Claude Code, Continue CLI, and OpenCode with a given prompt and working directory. Each harness exposes a different surface — Claude Code SDK with session API, `cn -p --prompt`, `opencode` CLI flags. Decide: thin wrappers per harness (matched to native APIs, more flexible) or a normalized "agent loop" interface the engine owns (LiteLLM-backed, more portable but reimplements harness behavior). My instinct is thin wrappers because the value of evals is catching *harness-specific* regressions, not papering over them.
11. **Determinism and seeding for evals.** Coding agents are non-deterministic. A Tier 1 runner that fails a task once might pass it on retry. Options: (a) seed temperature=0 and accept residual noise; (b) run each task N times and report pass-rate; (c) accept flakiness, focus on aggregate trends across many tasks. (b) is statistically honest but expensive; (a) is cheap but the seed isn't always honored. Defer to v2 with bias toward (a) + per-task `flaky: true` annotation for known-noisy tasks.
12. **Rubric judging calibration.** Tier 2 uses an LLM-as-judge. Before trusting its scores, the runner needs a calibration step where humans grade ~20 task outputs and the judge is evaluated against them. If judge–human correlation is below some threshold (0.7? 0.8?), the judge's grades shouldn't be reported. v2 decision: ship the calibration tooling, or assume good correlation and add it only if scores look noisy? Lean toward shipping it — calibration is cheap relative to the cost of acting on bad eval data.
## 20. Storage sources
This section adds one architectural seam to the engine. It is purely additive — v1 behavior is unchanged — and it exists to keep the engine swappable later without a rewrite.
### 20.1 The problem this solves
Today, the engine has filesystem operations scattered across several modules: the artifact loader walks `importlib.resources` and `<repo>/playbook/`, the config module reads `.coding-agent-playbook.toml`, the lockfile module reads and writes `.coding-agent-playbook.lock`. Each of these is hardcoded to "use the local filesystem."
That is correct for v1, but it makes two things hard:
- **Testing.** Tests that exercise the loader need real temp directories with fixture files. There is no clean way to inject hardcoded artifacts.
- **Future flexibility.** If a future deployment (a hosted product, an internal company registry, an air-gapped mirror with version pinning) needs artifacts or state to come from somewhere other than the local filesystem, every call site has to be refactored.
The fix is a small abstraction: route "where do artifacts come from" and "where does state live" through two interfaces, with one concrete implementation each in v1.
### 20.2 The two interfaces
```python
# coding_agent_playbook/catalog/source.py (ArtifactSource) and config/files.py (StateSource)
from abc import ABC, abstractmethod
from coding_agent_playbook.artifacts.hook_schema import HookSchemaError
from coding_agent_playbook.artifacts.hook import Hook
from coding_agent_playbook.artifacts.prompt import Prompt
from coding_agent_playbook.artifacts.rule import Rule
from coding_agent_playbook.artifacts.skill import Skill
from coding_agent_playbook.evals.task import EvalTask
from coding_agent_playbook.config.model import Config
from coding_agent_playbook.config.tables.hooks import PolicyTables
from coding_agent_playbook.lockfile import Lockfile


class ArtifactSource(ABC):
    """Where rules, prompts, skills, hooks, and eval tasks come from."""

    name: str

    @abstractmethod
    def list_rules(self) -> list[Rule]: ...
    @abstractmethod
    def list_prompts(self) -> list[Prompt]: ...
    @abstractmethod
    def list_skills(self) -> list[Skill]: ...
    def list_hooks(self) -> list[Hook]: ...  # concrete: returns [] (v0.20)
    def collect_hooks(self) -> tuple[list[Hook], list[HookSchemaError]]: ...  # concrete
    @abstractmethod
    def list_eval_tasks(self) -> list[EvalTask]: ...


class StateSource(ABC):
    """Where config and lockfile are read from and written to."""

    name: str

    @abstractmethod
    def load_config(self) -> Config: ...
    def load_primary_config(self) -> Config: ...  # concrete: the committed file alone
    def load_local_overrides(self) -> dict: ...  # concrete: {}
    def load_policy_tables(self) -> PolicyTables: ...  # concrete: committed [hooks]/[guardrails]
    @abstractmethod
    def save_config(self, config: Config) -> None: ...
    @abstractmethod
    def load_lockfile(self) -> Lockfile | None: ...
    @abstractmethod
    def save_lockfile(self, lockfile: Lockfile) -> None: ...
```
These are deliberately small. They expose typed Python objects, not raw bytes or filesystem paths. The engine never has to know whether something came from a wheel, a TOML file, or anywhere else.
The methods added since v1 are **concrete defaults**, never `@abstractmethod`, so a third-party source written before them still instantiates (§20.7). `list_hooks` returns `[]` and raises `HookSchemaError` on the first malformed hook; `collect_hooks` returns the well-formed hooks plus the errors of the malformed ones without raising, which is what `playbook validate` reads so it reports every malformed hook, not a traceback. `FileSystemArtifactSource.list_hooks` walks each layer's `hooks/` through `layer_roots` — the engine's `catalog/core/hooks/`, then each overlay package's `resources/hooks/` or bundled plugin's `catalog/plugins/<name>/hooks/` in `overlays_enabled` order, then `<repo>/playbook/hooks/` — yielding one `Hook` per directory that holds `HOOK.md` or `HOOK.md.j2` at any depth (dot-directories skipped). On the state side, `load_primary_config` is the committed file alone as a `Config` (`FileSystemStateSource`: `ConfigFiles.load_committed()`, the checked committed table through `Config.from_dict`, whose `extra_tables` hold the committed `[hooks]`/`[guardrails]`; the rewrites of `init` and `check --refresh` go through `config/committed`, so a local override is never persisted), `load_local_overrides` the `.local.toml` table, and `load_policy_tables` the committed `[hooks]` and `[guardrails]` tables, recording any local keys only to warn about them (§7.2).
### 20.3 What v1 ships
Two concrete implementations, both already implied by the rest of the spec:
```python
# coding_agent_playbook/catalog/source.py (FileSystemArtifactSource) and
# coding_agent_playbook/config/files.py (FileSystemStateSource)
class FileSystemArtifactSource(ArtifactSource):
    """Walks the engine's catalog (catalog/core/ and the enabled
    catalog/plugins/<name>/, located by catalog.roots), importlib.resources
    for overlay packages, plus <repo>/playbook/ for repo-local artifacts."""

    name = "filesystem"
    # Implementation = the current loader logic, just renamed.


class FileSystemStateSource(StateSource):
    """Reads and writes TOML files in the consumer repo:
    .coding-agent-playbook.toml, .coding-agent-playbook.local.toml,
    .coding-agent-playbook.lock."""

    name = "filesystem"
    # Implementation = the current config + lockfile logic, just renamed.
```
These are the **only** sources v1 ships. They depend on nothing beyond the existing dependency budget (jinja2, packaging) — both use stdlib `tomllib`, `pathlib`, and `importlib.metadata` only.

**Where the engine's own content comes from (`catalog/roots.py`; v0.19 named it `bundled_content.py`, N3 moved `catalog.py` into the `catalog/` package).** One leaf module, importing nothing from the engine (so `config/model.py` and `config/schema.py` can import it), is the only code that knows where `catalog/` is. Its constants are `ENGINE_PACKAGE = "coding_agent_playbook"`, `PLUGIN_NAMESPACE = "coding_agent_playbook.plugins"`, `DEPRECATED_PACK_NAMESPACE = "coding_agent_playbook.packs"`, `PACKAGED_CATALOG_DIRNAME = "_catalog"` and `CHECKOUT_CATALOG_DIRNAME = "catalog"`, plus `_PACKAGE_DIR`, the package directory, which is read at call time and is the one seam end-to-end tests may monkeypatch. Names follow one rule: a function that returns a directory of the catalog says `catalog` (`catalog_root`, `catalog_layer_root`), and a predicate or listing of what ships says `bundled` (`is_bundled_layer`, `bundled_plugins`), the user-facing term.
- `catalog_root(package_dir=None)` returns `<package_dir>/_catalog` when `<package_dir>/_catalog/core` is a directory (an installed wheel); otherwise `<package_dir>/../../catalog` when `package_dir.parent.name == "src"` and `<repo>/catalog/core` is a directory (a source checkout); otherwise it raises `CatalogMissingError` naming both paths (§12). Requiring `core/` in the wheel case means a mis-scoped force-include fails loudly instead of loading zero engine artifacts.
- `bundled_plugins(catalog_dir=None)` lists the sorted dotted names `coding_agent_playbook.plugins.<dir>` from `iterdir()` on `<root>/plugins`, keeping only directories whose name `isidentifier()` and does not start with `.` or `_`; `iterdir()` returns the on-disk spelling, so later comparisons stay exact on case-insensitive volumes.
- `canonical_overlay_name(name)` and `canonical_overlay_list(names)` implement the `packs` alias (§11.5); `is_plugin_namespace(name)` is true only for the two bare namespaces, and `is_bundled_layer(name)` for the engine and any name under either namespace.
- `catalog_layer_root(name, *, catalog_dir=None)` returns `<root>/core` for the engine and, after canonicalizing, `<root>/plugins/<leaf>` only when the canonical name is exactly an entry of `bundled_plugins()`. It returns `None` for anything else (an empty leaf, `..`, `/`, nested dots, the wrong case, `__pycache__`), so it never joins unchecked config text onto a path.
- `engine_layer_root(*, catalog_dir=None)` is `<root>/core`, `catalog_layer_root` for the engine typed never `None`, for code that reads one known engine file (`commands/twins/scan_sinks.py` reads the shipped ml-unsafe-deserialization-guard `HOOK.md`) and for the hook runtime's fallback protected root (`hook_runtime/config/protected.py`, §12.13).

`FileSystemArtifactSource`'s `_resource_subdir(package, subdir)` keeps its name, signature and `None` contract. For a bundled layer it returns `catalog_layer_root(package) / subdir` when that is a directory; this branch sits outside the `except Exception` guard, so `CatalogMissingError` propagates — the one exception to its never-raise contract. Every other package keeps the pre-v0.19 body verbatim: the single two-segment `resources.files(package).joinpath("resources", subdir)` call inside the guard, converted with `Path(str(...))` only after the full join, because splitting the join would silently drop a namespace overlay whose `resources/` spans two portions. A namespace overlay whose single kind directory spans portions is not supported (pre-existing). The walks, the `source_package` attribution and the layer order are unchanged.

`FileSystemStateSource` delegates its config half to `ConfigFiles` (`config/files.py`), the one interface to the two config files, which it builds for its repo root: `load_config()` is `ConfigFiles.load()`, `load_primary_config()` is `load_committed()`, `load_local_overrides()` is `local_overrides()`, and `save_config(config)` writes `config.to_dict()` through `write_committed`; its other config methods stay for code that calls them, each one call: `read_committed_config_table()` is `committed()`'s table as a new dict, `has_committed_config()` is `has_committed()`, `preview_config(table)` is `preview(table)` and `save_config_table(table)` is `write_committed(table)`. Its lockfile half is its own. `ConfigFiles` reads the committed file alone — `committed()`, the checked, decoded `CommittedDocument` with every key, which never reads `.coding-agent-playbook.local.toml`; `has_committed()` says whether it exists; `committed_table(*path)` decodes it and walks one table without the per-file checks, for the policy readers — and writes a decoded table verbatim with `write_committed(document)`, the committed file's one writer (`save_config` goes through it, `extra_tables` included, but a `Config` from `load()` has the local file merged in, so no command calls it). `preview(document)` returns what `load()` will give once that document is written — the document with the local file merged on top — without writing. Every rewrite is built in `config/committed` as a `ConfigRewrite` (the table and its `Config`) and checked with `preview` before `ConfigRewrite.save` writes it: `plan_first_config` (a first `init`; refused when the file exists), `plan_committed_update` (an `init` re-run: read the committed table once, build its `Config`, apply the answers, write it through `Config.to_dict`, which appends `Config.extra_tables` with `config_entries.with_unmanaged_entries` — top-level entries after the config's own keys, unknown keys of `[project]`/`[engine]`/`[storage]`/`[output]` inside that table, a key `Config` owns never taken from `extra_tables`) and `plan_detector_cache_refresh` (`check --refresh`: the committed table with `[detector_cache]` replaced, nothing else) (§12.1, §12.5). `load()` stays the merged, effective config (§7.2) and is never saved (the §7.2 invariant).
### 20.4 Configuration
The `[storage]` section of `.coding-agent-playbook.toml` selects which source to use. v1 defaults are filesystem for both, so existing configs need no changes:
```toml
[storage]
artifact_source = "filesystem"      # default; the only v1 option
state_source = "filesystem"         # default; the only v1 option
```
When v1 reads a config without a `[storage]` section, both default to `"filesystem"`. Users who never customize storage never see this section.
### 20.5 Discovery via entry points
Sources are registered the same way as adapters and overlays — through Python entry points. The engine ships:
```toml
[project.entry-points."coding_agent_playbook.artifact_sources"]
filesystem = "coding_agent_playbook.catalog.source:FileSystemArtifactSource"
[project.entry-points."coding_agent_playbook.state_sources"]
filesystem = "coding_agent_playbook.config.files:FileSystemStateSource"
```
A future package — open-source or proprietary — can register alternative sources by declaring its own entry points. The engine code does not change.
### 20.6 What this enables later (not in v1)
Concrete examples of what the seam buys, intended to clarify the design intent — none of these ship in v1:
- **An internal company registry** could provide a `RegistryArtifactSource` that fetches rule packs from a versioned HTTP endpoint behind corporate auth. The engine sees the same `Rule` objects regardless.
- **A hosted product** could provide a `DatabaseStateSource` that writes lockfile state to a central database, enabling cross-repo drift dashboards without changing how the engine writes lockfiles.
- **A test harness** can use an `InMemoryArtifactSource` to inject hardcoded rules into the engine without touching the filesystem.
These are alternative deployments of the same engine, not forks of it.
### 20.7 What v1 promises and does not promise
Promises:
- The `ArtifactSource` and `StateSource` interfaces are public API once v1 ships. Breaking changes require a major version bump.
- The filesystem implementations are the reference implementations; their behavior is what other sources must match for consumer-visible parity.
- The engine code never instantiates a specific source class; it always goes through entry-point discovery and the configured source name.
Does not promise:
- v1 does not commit to building any non-filesystem source.
- v1 does not commit to backward compatibility for the *internal* helpers used by the filesystem implementation (only the abstract base class is API).
- v1 does not commit to a sync-time API for sources beyond what the abstract base requires. Future sources may need additional capabilities (caching, prefetch, signed updates) — these will be added as optional methods on the ABC with default implementations.
### 20.8 What changes in the rest of the spec
The Repository pattern is now the implementation strategy for several earlier sections; the user-visible behavior in those sections is unchanged. Specifically:
- **Section 4.2 (data flow)**: Step 3 ("Resolve overlays. Walk the engine's resources/...") is implemented by calling `ArtifactSource.list_rules()` and friends. The resolution-order semantics are unchanged.
- **Section 5.1 (engine layout)**: Adds a `sources/` package alongside `adapters/` and `evals/`.
- **Section 8 (detector)**: Unchanged. The detector reads `pyproject.toml` from the local repo and is independent of artifact storage.
- **Section 14.4 (lockfile)**: The lockfile's *content* is unchanged; only the read/write path goes through `StateSource`.
### 20.9 Why this matters even if commercialization never happens
Two non-commercial reasons to ship this in v1:
1. **Tests get simpler.** An `InMemoryArtifactSource` in `tests/` lets every unit test build a tiny artifact list inline, with no temp directories, no fixture files, no filesystem walks. The integration tests still use the real filesystem source for end-to-end coverage.
2. **The engine codebase becomes more honest about its dependencies.** Right now, "load some rules" implicitly depends on `importlib.resources`, `pathlib`, the filesystem layout convention, and overlay entry-point discovery — all tangled together. After this change, those dependencies live in one named class with one clear responsibility. The rest of the engine depends on an interface, not a tangle.
The cost is roughly 100 lines of interface code and a renaming of existing modules. No new runtime dependencies. No new operational complexity for the consumer.
### 20.10 The `.playbook/manifest.toml` round-trip sidecar
The Agent Harness format (§10.7) cannot represent several canonical fields — a rule's `name`/`scope`/`globs`/`priority`/`tags`, a prompt's `slash`/`includes_rules`/`input_variables`, a skill's open-dict extra frontmatter, a script's executable bit. To make the harness round-trip lossless, the `agent_harness` adapter writes a dotfile sidecar at `<harness-root>/.playbook/manifest.toml` (harness clients skip dotfiles, so it is invisible to them). It is not a `StateSource` — it is a per-harness reconstruction record co-located with the emitted tree — but it plays the same role for the harness direction that the lockfile plays for sync.
The sidecar stores the **full canonical reconstruction payload**, not merely "non-native fields". For every emitted artifact, keyed by its harness-relative path, it records:
- every frontmatter field the harness leaf cannot carry (notably the rule `name`, since the harness rule file emits `description` only);
- the original, **un-rendered** canonical source `body` for every kind — the harness leaf is the client-facing *presentation* and may rewrite/inline content (a prompt's `includes_rules` are inlined into its `SKILL.md`), so the recorded body is the authoritative canonical text;
- `is_templated` for every kind (tracks `.md` vs `.md.j2` origin);
- for skills, a per-script `executable` boolean (git's single-bit model, not a full octal mode).
Frontmatter values are written with the shared `toml_writer` primitives as inline TOML, keeping every type YAML frontmatter yields — strings, booleans, integers, floats, dates and datetimes, nested in arrays and inline tables — so they read back with the same types. Floats and dates are written since v0.18; before, such a value in `applies_if`, `input_variables` or a skill's extra frontmatter stopped `init`/`sync` with `TypeError: manifest TOML does not support value of type float`.

v0.20 adds, with **no schema bump** (an older engine ignores unknown keys and warns-and-skips an unknown kind):
- **`kind = "hook"`**: one entry per hook, keyed by `.playbook/hooks/<id>/HOOK.md`, holding `name`, the un-rendered `body`, `is_templated`, the canonical frontmatter as the inline table `hook_frontmatter` (`HookFrontmatter.to_mapping()`, floats and all), and a `ScriptEntry(path, executable)` per copied script. `import-harness` rebuilds the hook through `Hook.from_dict` and writes it in the repo-local layout, `<into>/hooks/<id>/HOOK.md` (or `.md.j2`) plus `scripts/`, restoring the scripts' exec bits. The client-facing advisory `rules/30-guardrail-<id>.md` is presentation only and gets no entry, so a lossless import never turns it into a spurious `Rule`;
- the rule field `lint_codes` and the prompt fields `write_scope` and `output_contract` (§6.1.1, §6.2.1), each emitted only when non-empty, so existing sidecars stay byte-identical.

v0.21 adds the rule field `skill` (§6.1.1), likewise with no schema bump and only when set, so a rule entry keeps its owning skill and `import-harness` rebuilds a member rule that still passes the V1 check (§12.6).
Because each entry carries the whole payload, `import-harness` reconstructs each artifact via `from_dict` **independently of how the leaf rendered or inlined things** — the leaf files exist only for harness clients; the sidecar is the source of truth. When the sidecar is absent (a foreign harness), the importer falls back to best-effort structural inference and surfaces the lossiness (§12.9).
### 20.11 Out of scope: the harness client runtime
The Agent Harness spec also defines a **client runtime contract** — `load_content` / `run_script` and the four loading phases (Load → Discovery → Activation → Execution). The playbook intentionally does **not** implement that runtime. It produces harness files (the `agent_harness` adapter), consumes them (`import-harness`), and validates their structure (`validate-harness`), but it is not a harness *client*: it never injects `HARNESS.md` into a session, reads routing files at runtime, or executes scripts. Modeling the full client runtime is future work; for v1 the `validate-harness` lint is the structural stand-in for runtime conformance (decision #3 in `specs/prH-agent-harness.md` §D).
## 21. Code-quality evaluator subsystem
Added in PR M; **refactored to the `Metric` / `Check` / `Rubric` model in PR R6** (clean-slate, `specs/prR6-check-rubric.md`). This section adds a code-quality measurement engine — static metrics, execution metrics (tests/coverage), and a generalized rubric — behind **three single-responsibility abstractions**, plus a standalone `playbook metrics` gate and a static pre-commit hook. It is purely additive to the sync pipeline: it touches none of it and ships no new hard dependency. The authoritative design is `specs/prR6-check-rubric.md` (and the original `specs/prM-code-metrics.md`, now superseded for the abstraction shape); the as-built lives in `src/coding_agent_playbook/evaluators/` and `commands/metrics.py`.
### 21.1 Three abstractions: `Metric` → `Check` → `Rubric`
A rubric criterion, a code metric, a coverage number, and a test-pass rate are all the same thing — a **graded measurement over a scope** — but *measuring* a value, *grading* it pass/fail, and *aggregating* graded results into a verdict are three distinct responsibilities. PR M originally fused them into one `Evaluator` ABC + a free `grade()`; PR R6 split them along the grain (the realization of the Anthropic "Demystifying Evals for AI Agents" framing — a Check ≈ a grader's pass/fail assertion, a Rubric = a weighting of checks, and a metric becomes a check via a threshold):
```python
class Scope(Enum):
    FUNCTION
    METHOD
    CLASS
    FILE
    MODULE  # MODULE = the whole target/suite


class Determinism(Enum):
    DETERMINISTIC
    JUDGED  # who produces the value (routing)


class CostTier(IntEnum):
    DETERMINISTIC < EXECUTION < JUDGED  # cheapest-first scheduling


class Metric(ABC):  # the "measure" leaf  (evaluators/metric.py)
    name: str
    scope: Scope
    normalizer: Normalizer  # maps raw -> 0-1 GOODNESS (higher = always better)
    requires: str | None = None  # optional importable dep (e.g. "radon"); None = stdlib
    needs_project: bool = False  # True => execution metric (needs ctx.project)
    needs_judge: bool = False  # True => judge-backed metric (needs ctx.judge)

    def available(self, ctx: EvalContext) -> bool: ...
    def score(self, raw: float) -> float: ...  # raw -> 0-1 via self.normalizer
    @abstractmethod
    def measure(self, ctx: EvalContext) -> list[Measurement]: ...  # one Measurement per scope


class Check(ABC):  # the "grade" stage  (evaluators/check.py)
    id: str
    weight: float  # > 0 => contributes to the weighted composite
    required: bool  # a gate check
    determinism: Determinism  # routing axis
    cost: CostTier  # scheduling tier

    def available(self, ctx: EvalContext) -> bool: ...
    @abstractmethod
    def grade(self, ctx: EvalContext, measurements: MeasurementSet) -> CheckResult: ...


class Rubric(Metric):  # the "aggregate" stage  (evaluators/rubric.py)
    def evaluate(
        self, ctx, measurements, *, strict=False, fail_fast=False, max_workers=1
    ) -> EvaluationReport: ...
    def measure(
        self, ctx
    ) -> list[Measurement]: ...  # a Rubric is ALSO a Metric (composite as one MODULE measurement)
```
The split: a **`Metric`** carries only the measurement-side descriptors (`name`, `scope`, `normalizer`, `requires`, `needs_project`/`needs_judge`) and produces a raw `Measurement` per scope; a **`Check`** carries the grading-side policy (thresholds, regression tolerance, `weight`, `required`) and turns measurements (or `ctx` directly, for file/judge checks) into one `CheckResult` — a boolean `passed` gate **plus** an optional `0-1` `score` for partial credit; a **`Rubric`** holds an ordered set of checks and folds their results into one `EvaluationReport` (gate = all `required` checks pass; composite = `Σ(weight·score)/Σweight`). The `EvalContext` (`evaluators/types.py`) carries everything a family might need, decoupled: static reads `module`/`source`/`label`; execution reads `project`; judged reads `judge`/`artifact`/`samples`; file checks read `tree`/`baseline_tree`. `available(ctx)` lets each piece degrade gracefully when its slot or dependency is missing.

**Normalization lives on the `Metric` — `higher_is_worse` is gone.** Every metric owns a `Normalizer` (`evaluators/normalizer.py`: `RampNormalizer(good, bad)` / `PercentNormalizer` / `Identity`) mapping its raw value to a `0-1` **goodness** where `1.0` is best and **higher is always better**, regardless of the metric's native direction (`cyclomatic_complexity` ramps *down* as it grows, `coverage` ramps *up*). `Metric.score(raw)` applies it. Folding direction into the normalizer is what let the per-metric `higher_is_worse` flag be **deleted**: the `Check` grades on the normalized score, so it never reasons about direction, and every threshold (`warn` / `fail` / `max_worsening`) is a `0-1` cutoff on that goodness.

**A `Rubric` is also a `Metric` — the Composite.** `Rubric` subclasses `Metric` and exposes its composite as one MODULE-scope `Measurement` via `measure()`, so a rubric thresholds into a parent `ThresholdCheck` and **nests** into a Composite tree (a rubric-of-rubrics). `measure()` self-builds its `MeasurementSet` from the additive `EvalContext.candidate_measurements`/`baseline_measurements`, guards against a re-entrant self-measure (`ValueError`), and memoizes per `ctx`. This replaces the old fused `Evaluator` with a composable algebra: any check tree (booleans via `AllOf`/`AnyOf`/`Not`, §21.2.4) is itself a check.

**The static / execution / judged discriminator is `needs_project` / `needs_judge`, not the scope axis.** A FILE-scope metric like `coverage` is *execution*, not static, so scope alone cannot separate them; `needs_project=True` (execution) / `needs_judge=True` (judge-backed) are the explicit flags. `static_metrics()` excludes `needs_project`; a metric-backed check derives its `cost` (DETERMINISTIC / EXECUTION / JUDGED) from these flags.

**How the families are differentiated — orthogonal axes, no `kind` enum.** The families are *emergent* from independent fields, so the engine never switches on a "type". A task `check` is `(type) × (metric|judge) × kwargs` — `check = "threshold"|"non_regression"` over a registered `metric=` or a `judge=` criterion (a `JudgeMetric`, §21.2.3) — plus the standalone file checks and rubric groups:

| Family | check class / id | `determinism` | `cost` | `available(ctx)` needs | task layer |
|---|---|---|---|---|---|
| static metric (§21.2.1) | `threshold` / `non_regression` over a static `metric=` | DETERMINISTIC | DETERMINISTIC | `ctx.module` (source/AST) | `[gate]` |
| execution (§21.2.2) | `threshold` / `non_regression` over an execution `metric=` | DETERMINISTIC | EXECUTION | `ctx.project` | `[gate]` |
| judged metric (§21.2.3) | `threshold` / `non_regression` over a `judge=` (a `JudgeMetric`), or a `rubric` group of `JudgeCheck`s | JUDGED | JUDGED | `ctx.judge` | `[rubric]` |
| file check (§21.2.4) | `file_exists` / `file_contains` / `file_unchanged` / `file_forbidden` | DETERMINISTIC | DETERMINISTIC | `ctx.tree` | `[gate]` |
| answer check (§21.2.4) | `answer_matches` — a regex over `ctx.artifact` | DETERMINISTIC | DETERMINISTIC | *nothing* (always available, fail-closed) | `[gate]` |
| aggregate (§21.2.5) | `pass_at_k` / `pass_pow_k` over the runner's trials | DETERMINISTIC | DETERMINISTIC | `ctx.trials` | `[aggregate]` |

Authors differentiate by **task layer + handle shape** (a `[gate.bind]` / `[rubric.bind]` / `[aggregate.bind]` handle), which the compiler turns into a `Rubric` of checks (§21.6); the engine differentiates by the axes and the cost-tiered scheduler routes by capability (`available(ctx)`) + tier, not a type switch — so a new kind drops in by choosing axis values, with no second `grade()` path.

### 21.2 The check families
| Task handle | Family | Metric / Check | `determinism` · `cost` / needs | primary use |
| --- | --- | --- | --- | --- |
| `[gate]` `{check="threshold"|…, metric="cyclomatic_complexity"|…}` | **static** | static `Metric` → `ThresholdCheck`/`NonRegressionCheck` | DETERMINISTIC · DETERMINISTIC · `ctx.module` (`ast`/`radon`) | 0–1 threshold + **non-regression** |
| `[gate]` `{check=…, metric="test_pass_rate"|"coverage"}` | **execution** | execution `Metric` → `ThresholdCheck`/`NonRegressionCheck` | DETERMINISTIC · EXECUTION · `ctx.project` (shells out to `pytest`) | 0–1 threshold + **non-regression** |
| `[rubric]` `{rubric=[{judge,weight},…]}` or `{check=…, judge="…"}` | **judged** | `JudgeCheck` (rubric group) or a `JudgeMetric`-backed check | JUDGED · JUDGED · `ctx.judge` (LLM) | weighted composite + threshold |
| `[gate]` `{check="file_exists"|…}` | **file** | `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden` | DETERMINISTIC · DETERMINISTIC · `ctx.tree` | must-be-true gate |
| `[aggregate]` `{metric="pass_at_k"|"pass_pow_k", k, over}` | **aggregate** | `PassAtK`/`PassPowK` over the runner's trials | DETERMINISTIC · DETERMINISTIC · `ctx.trials` | cross-trial reliability |
#### 21.2.1 Static metrics (`evaluators/builtins/`)
Source is parsed **once** into a `ModuleModel` (`evaluators/parse.py`, which also owns the shared `_cyclomatic` helper and the stable scope keys `<label>::<qualname>` / `<label>`); each available static `Metric` reads that model via its module-level `_measure` helper. All are stdlib-`ast`-only except MI, which is the lone radon-backed one. Each metric owns a `Normalizer` that folds its native direction into a 0–1 goodness (higher = better). The grading-side policy (the warn/fail bounds + regression tolerance below) lives on the *check*, not the metric, as **0–1 cutoffs on the normalized score**: the shared per-metric defaults are `metrics_gate/policy.py::METRIC_DEFAULTS`, applied by `metric_check()` when an override is absent.
| `name` | scope | `normalizer` (raw→0–1) | default warn/fail (0–1) | default `max_worsening` | requires |
| --- | --- | --- | --- | --- | --- |
| `cyclomatic_complexity` | FUNCTION/METHOD | `Ramp(good=5, bad=20)` | `warn=0.5, fail=0.25` | `0` | — |
| `wmc` | CLASS | `Ramp(good=10, bad=60)` | `fail=0.2` | `0` | — |
| `lcom4` | CLASS | `Ramp(good=1, bad=6)` | `warn=0.5` | `0` | — |
| `dit` | CLASS | `Ramp(good=1, bad=8)` | `warn=0.5` | `0` | — |
| `cbo` (≈) | CLASS | `Ramp(good=3, bad=25)` | `warn=0.5` | `0` | — |
| `maintainability_index` | FILE | `Percent` (0–100→0–1) | `fail=0.65` | `0` | `radon` |
| `ruff_violations` (opt-in) | FILE, one value per ruff code family (`<file>::ruff:<family>`) | `Ramp(good=0, bad=5)` | none (non-regression only) | `0` | `ruff` on `PATH` (a subprocess, never an import) |
| `file_sloc` (opt-in) | FILE | `Ramp(good=300, bad=800)` | none; a band is configured, e.g. `warn=1.0, fail=0.6` | `1.0` (regression-exempt) | `radon` |
| `docstring_example` (opt-in) | FUNCTION/METHOD, public only | `Identity` (1.0 an example, 0.5 a summary only, 0.0 none) | none; strict mode sets `fail=1.0` | `0` | — |
A `Ramp(good, bad)` scores `good`→`1.0`, `bad`→`0.0` and interpolates between (clamped); the single direction-free formula handles a worse-when-larger metric (`good < bad`) and a better-when-larger one alike. Algorithms: **CC** = 1 + decision points (`If/For/AsyncFor/While`, comprehension `if`s, `BoolOp` operands−1, `ExceptHandler`, `IfExp`, `match` guards, `assert`); **WMC** = Σ of method CC; **LCOM4** = connected components of the method graph (shared `self.x` attr or `self.m()` call); **DIT** = longest resolvable base chain (external base = depth 1); **CBO≈** = distinct external types referenced (labeled approximate — undercounts under duck typing); **MI** = `radon.metrics.mi_visit(source, multi=True)`, the SEI 0–100 variant. `maintainability_index` is the engine's only optional extra (`pip install 'coding-agent-playbook[metrics]'`): it self-registers like every builtin, but radon is imported **lazily inside `measure`** and `available()` returns `False` when radon is absent, so the gate transparently skips MI and the engine still loads air-gapped with nothing extra installed.
**The v0.20 static metrics are opt-in** (`OPT_IN_METRICS`, §21.3): selected only by name, never by default or through a family, so an engine upgrade leaves every consumer's `playbook-metrics` results byte-stable. `ruff_violations` wraps ruff, a consumer-toolchain subprocess: one `<ruff> check --no-fix --exit-zero --force-exclude --output-format json --stdin-filename <file> --select <codes> -` call per side and file, with the source on stdin for the candidate and the baseline alike (so no worktree is needed, the project's `per-file-ignores` and `# noqa` still apply, and its excludes stay effective). It yields one measurement per configured family — `quality` (C901, PLR0911, PLR0912, PLR0913, PLR0915) and `docstrings` (D100–D107), both overridable in `[metrics.ruff_violations]` (§7.1.1) — including a zero, so `0 → 1` is a regression; a syntax error, a failed or timed-out call or unreadable output yields no measurement, never a zero, and without a ruff the metric is unavailable. `file_sloc` is radon's source lines of code per file (`radon.raw.analyze(source).sloc`), the one gap ruff lacks (no too-many-lines rule): a growing legacy file is never a regression, and a new file is graded only against a configured band (`warn=1.0` flags over 300 SLOC, `fail=0.6` over 500). `docstring_example` is the strict "intent + one usage example" docstring mode in stdlib `ast`: a public function scores 1.0 when its docstring holds a usage example (a `>>>` line, an `Example:` / `Examples:` / `Usage:` header, a numpy `Examples` section or a reST `::` block); with `[metrics.thresholds.docstring_example] fail = 1.0` in regression mode it bites only new public functions.
#### 21.2.2 Execution metrics (`evaluators/execution/`)
Deterministic, but they need to **run the target's test suite**, so they add **no playbook dependency**: a `ProjectHandle` (`execution/project.py`) runs a configurable command (default `python -m pytest --junitxml=… --cov --cov-report=xml:… -q`) in the target, and the metrics parse the standard **junit XML** + **coverage XML** with stdlib `xml.etree.ElementTree` (`execution/junit.py`, `execution/coverage_xml.py`). The target supplies `pytest`/`pytest-cov`. The convenience check factories `TestsPassCheck()`/`CoverageCheck()` (`evaluators/checks/execution.py`) are thin `ThresholdCheck` wrappers bound to these metrics with the conventional default bounds.
| `name` | scope | `normalizer` (raw→0–1) | default warn/fail (0–1) | default `max_worsening` | needs |
| --- | --- | --- | --- | --- | --- |
| `test_pass_rate` | MODULE (suite) | `Identity` (already 0–1) | `fail=1.0` (all must pass) | `0` (no new failures) | `ctx.project` |
| `coverage` | FILE (+MODULE total) | `Percent` (0–100→0–1) | `warn=0.8` | `0` (must not drop) | `ctx.project` |
| `diff_coverage` | MODULE (the change) | `Percent` (0–100→0–1) | `fail=0.8` (changed lines ≥ 80% executed) | moot: diff-based, never compared with a baseline value | `ctx.project` + the changed lines against `ProjectHandle.diff_base` |
- **One run, both metrics:** `ProjectHandle.run()` executes the suite once and caches the parsed junit + coverage reports; both metrics read that cache (no double run).
- **Flaky tolerance:** `test_pass_rate` is DETERMINISTIC but supports an optional flaky-retry (`ProjectHandle.flaky_retries`; reruns and takes the best observed pass rate); off (`0`) by default.
- **Non-regression needs two runs.** Standalone with `--baseline git:<ref>` materialises the ref via a temporary `git worktree add` (heavier than the static `git show`); `--baseline <dir>` runs the suite there. Absolute mode (single run on the current tree) is the lighter default.
- **`diff_coverage` (v0.20)** is the attribution-correct coverage signal: the share of the executable lines a change added or edited that the suite ran. It declares `diff_based = True` (a new `Metric` descriptor): one suite run, no baseline run. Test paths (`evaluators/paths.py::TEST_PATH_GLOBS`) and `[metrics] exclude` are never scored; a changed file the coverage report does not list is *unmeasured*, named but not scored; and a change with no executable line yields nothing, so its check passes vacuously, never on a fake 100%. For it, `CoverageReport` gains `lines` (per-file line hits) and `sources` (the report's source roots), and `ProjectHandle` gains `diff_base`, `timeout_s` (`[metrics] test_timeout_s`; a hook-driven suite must never hang the agent) and `env_overrides` (a hook points `COVERAGE_FILE` into its state dir, so the run leaves no file in the worktree). `default_test_cmd(report_dir, python=, cov_sources=)` takes the interpreter to run (a hook passes the project's, not the engine's) and the `--cov=<source>` roots, which also report never-imported files at 0%.
- **`CoverageCheck()` grades on the normalized score (v0.20 fix):** its default `warn=0.8` flags a file under 80% coverage; the earlier raw `warn=80.0` could never be met, since a 0–1 score is never 80.
- **Opt-in & cost-gated:** running tests has side effects and cost, so execution metrics are opt-in — `--run-tests` on the standalone `playbook metrics` gate, *inferred* (a `[gate]` referencing an execution metric) on `playbook eval --run`. Their checks are EXECUTION-tier (the scheduler runs them after the deterministic tier) and are **excluded from the default pre-commit hook** — it stays static-only.
#### 21.2.3 Judged criteria — the rubric, as checks (`evaluators/checks/judged.py`, `judge_metric.py`)
A rubric criterion is a `JudgeCheck`: a graded SCORE whose value comes from a *judge* (LLM/human). It is **parameterized**, not a registered singleton — a `[rubric.bind]` `rubric` group instantiates one per criterion line (via `Rubric.of`), each carrying its own `criterion` text, `weight`, and a `0-1` `threshold` floor (id `judge:<slug>`, `determinism=JUDGED`, `cost=JUDGED`). `grade` calls `ctx.judge.score_criterion(self.criterion, ctx.artifact, n=ctx.samples) -> float` and averages over `ctx.samples` to damp LLM noise; the score feeds the composite and the `passed` gate is `score >= threshold`. It is **dormant without a judge**: `available()` returns `True` only when `ctx.judge` is set, so a `Rubric` evaluated with no judge records each `JudgeCheck` as `status="skipped"` (never sinking the gate). Because `JudgeCheck` is JUDGED-cost, the cost-tiered scheduler (§21.4) runs it **last** — a failing deterministic gate short-circuits it away, so under the default conjunction verdict a failed gate check never spends an LLM call (see `CompiledTask.short_circuit_safe` for the tasks scored in full).

**`JudgeMetric` — a judged criterion *as a metric* (`evaluators/checks/judge_metric.py`).** A weighted rubric group is the *one* shape that builds `JudgeCheck`s directly. The *other* shape — a standalone `{check = "threshold"|"non_regression", judge = "<criterion>"}` handle — needs a judged criterion that an ordinary metric-backed `ThresholdCheck`/`NonRegressionCheck` can grade, so `JudgeMetric` is an **Adapter** that presents the judge as a `Metric`: `needs_judge=True`, `normalizer=Identity` (a judge score is already a 0–1 goodness), and `measure(ctx)` returns one `Measurement` = `ctx.judge.score_criterion(criterion, ctx.artifact, n=max(1, ctx.samples))`. This is what makes **non-regression on a judged criterion** work (`{check="non_regression", judge="overall quality", max_worsening=0.1}`) — the same regression machinery as any metric, no special-casing. Like `JudgeCheck`, it never imports `evals` (it consumes only the `JudgeLike` protocol) and is `available()`-gated on `ctx.judge`.
> **Judge signature — reconciled (R2), still closed.** `JudgeCheck.grade` calls `ctx.judge.score_criterion(criterion, artifact, n) -> float` — the **canonical per-criterion primitive** (Option A). The `Judge` ABC's batch `score(rubric, transcript, scratch_dir_state) -> list[float]` is a thin wrapper that maps `score_criterion` over the rubric, so the two shapes are the *same* operation at different granularities. `ctx.judge` is typed as the structural `JudgeLike` protocol **defined in `evaluators/types.py`** (not `evals`) so `evaluators` never imports `evals` — avoiding the `evaluators` ↔ `evals` cycle; the concrete `Judge` satisfies it structurally. Tests exercise `JudgeCheck` via the deterministic `StubJudge`.
#### 21.2.4 File checks + the answer check + boolean composers (`evaluators/checks/`)

**The answer check — `answer_matches` (`evaluators/checks/answer.py`).** The file checks gate on what the agent *did*; `AnswerMatchesCheck` gates on what it *said*. Authored as `[gate.bind] <name> = { check = "answer_matches", pattern = '<regex>' }`, it applies a Python `re` search to `ctx.artifact` — which, for a **review-only** task, is the agent's transcript (§15.3.1). Such a task forbids edits (its gate is `file_unchanged`), so it produces no diff and the file predicates alone can only prove the agent stayed its hand, never that it reached the right conclusion. Its purpose is a cheap **class gate in front of the judge**: the cost-tiered scheduler's short-circuit (§21.4, `fail_fast=True` — the runner default) skips the JUDGED tier entirely when it fails, so a plainly wrong answer costs zero judge tokens. Two deliberate properties: it is **fail-closed** — `available()` is unconditionally `True` (it needs no judge, project, or tree), so a missing/empty artifact grades `False` rather than skipping (a skipped check is *neutral* in the layer expression and would let a silent agent through); and its regex **compiles at construction**, so a malformed pattern raises during task compilation (hence `playbook validate`) rather than midway through a scored run. Case-insensitivity is the pattern's business (`(?i)`), not a separate flag. The shipped `find-injected-vuln-*` fixtures each carry one, holding a lenient CWE-class regex — lenient by design, since the gate rejects a wrong *class* while the judge grades precision.

The four file predicates are first-class deterministic `Check`s (`evaluators/checks/files.py`), authored as `[gate.bind]` handles (`{check = "file_exists"|"file_contains"|"file_unchanged"|"file_forbidden", path = …, pattern = …}`): `FileExistsCheck`, `FileContainsCheck` (path + regex), `FileUnchangedCheck` (byte-identical to the `setup/` snapshot via `ctx.baseline_tree`), and `FileForbiddenCheck`. Each ignores the `MeasurementSet` and reads `ctx.tree` directly, is a pure gate (`required=True`, `weight=0.0`), and its `passed` comes straight from the predicate (`available()` is `False` without a candidate tree). The boolean composers `AllOf`/`AnyOf`/`Not` (`evaluators/checks/compose.py`) are themselves checks that fold child checks through the scheduler (an unavailable child is *neutral*, not a failure; a composer none of whose children can run is itself unavailable and records `status="skipped"`, so the skip propagates up instead of becoming a vacuous pass for `AllOf` or a fail for `AnyOf`), so any check tree nests freely inside a `Rubric` — and they back both the `{all_of=[…]}`/`{any_of=[…]}`/`{not=…}` handle groups and the compiled `[<layer>].expr`/`[verdict].trial` boolean expressions (§21.2.6).
#### 21.2.5 Aggregate checks — `pass@k` / `pass^k` across trials (`evaluators/checks/aggregate.py`)
The `[aggregate]` layer grades **reliability across `k` runner trials**, a dimension orthogonal to the per-trial gate/rubric. A handle is `{metric = "pass_at_k"|"pass_pow_k", k = <int>, over = "gate"|"rubric"|"verdict", warn?, fail?}`; the runner runs `N = max(k)` trials and the `AggregateCheck` reduces the selected `over` axis (each trial's `gate`/`rubric` `CheckResult.passed`, or its derived `verdict`) to `c` successes over `n` trials, then estimates: **pass@k** = the probability a random `k`-subset of the trials contains ≥1 success (`1 - C(n-c,k)/C(n,k)`, or `1.0` when fewer than `k` failed); **pass^k** = the probability a random `k`-subset is all successes (`C(c,k)/C(n,k)`, or `0.0` when fewer than `k` succeeded). The 0–1 estimate is graded against an absolute `warn`/`fail` floor (same higher-is-better strict-below rule the metric checks use). An aggregate check does no agent work — it reads the already-run `ctx.trials` — so it is `DETERMINISTIC` on both axes; `available()` is `True` only once the runner has populated `ctx.trials` **and** the `over` axis ran in at least `k` trials. An aggregate over a **layer** (`over = "gate"|"rubric"`) that the cross-layer short-circuit could skip — one costlier than the cheapest layer, e.g. the judged rubric behind a deterministic gate — makes scoring run every trial in full (no short-circuit): otherwise a trial whose cheaper gate failed would leave that layer ungraded, and the aggregate would depend on `fail_fast`. (A layer in the cheapest tier always runs, so `over = "gate"` with a deterministic gate keeps the short-circuit and still spares the judge.) A trial whose `over` layer was still skipped — it was *unavailable*, e.g. `over = "rubric"` with no judge — does not vote, so `n` counts only the trials where that layer ran; with fewer than `k` votes (in practice: none) the aggregate is skipped (neutral) and the task verdict falls back to the trials' own verdicts: it passes only if every trial passed, scored by the trial pass rate. (`max_worsening` vs baseline trials is accepted by the validator but not yet supported — the absolute path executes.)
#### 21.2.6 Expression DSL + derived verdict (`evals/_expr.py`, `evals/_compile.py`)
A task's `[<layer>].expr` and `[verdict].trial` are tiny boolean expressions (`and`/`or`/`not`/parens) over handle names. `evals/_expr.py` is a self-contained **Interpreter** — a hand-rolled tokenizer + recursive-descent parser (precedence `not > and > or`, chained operators flattened to n-ary nodes) to a small immutable AST — with no `eval`/`exec`/`ast` and no third-party dep. `compile_expr` folds the AST into a `compose.py` `AllOf`/`AnyOf`/`Not` check tree over the layer's `name -> Check` handle map (built by `evals/_handles.py`, the **Factory + Composite** that turns each binding into a check). The **verdict is derived, not re-run**: the per-trial `Rubric` evaluates the `gate` and `rubric` layer checks *once*, and `[verdict].trial` is a boolean fold (`eval_bool`/`verdict_passed`) over their already-decided results with **skipped-neutral** semantics (a layer that did not run — e.g. the rubric layer with no judge — is neutral, exactly like an unavailable child of `AllOf`/`AnyOf`). Folding the verdict from the layer results instead of compiling it as a third check is what keeps the judge / test-suite single-shot.
### 21.3 Registry — decorator + entry points
In-tree metric builtins self-register via the `@register_metric` class decorator (each `builtins/*` and `execution/*` module decorates its class; `builtins/__init__` and `execution/__init__` import them so the decorators fire). The extension surface is four entry-point groups, each with an in-tree-wins dedup:
- **`coding_agent_playbook.metrics`** — out-of-tree `Metric`s (renamed from the old `…​.evaluators`); `@register_metric`. An out-of-tree metric **must** declare a `normalizer`.
- **`coding_agent_playbook.checks`** — out-of-tree custom grader `Check` factories, resolved by `get_check(id, **kwargs)` from a task's `{check = "<id>", …}` handle; `@register_check`. The in-tree `threshold`/`non_regression`/`file_*`/`answer_matches`/`pass_at_k`/`pass_pow_k` ids register here too.
- **`coding_agent_playbook.gates`** (new) — out-of-tree composed boolean gates, resolved by `get_gate(name)` from a gate-layer `{ref = "<name>"}`; `@register_gate("name")`. The engine registers no gate of its own.
- **`coding_agent_playbook.rubrics`** — out-of-tree named rubrics, resolved by `get_rubric(name)` from a rubric-layer `{ref = "<name>"}`; `@register_rubric("name")`. The engine registers no rubric of its own.

The list is never hardcoded; **in-tree builtins win** over an entry point reusing a name. Metric selection helpers (`evaluators/metric.py`):
- `all_metrics()` — builtins + entry points, deduped by name.
- `static_metrics()` — every metric with `not needs_project` (the `playbook metrics` default set).
- `execution_metrics()` — every metric with `needs_project` (`coverage`, `test_pass_rate`); `--run-tests` adds these.
- `get_metric(name)` — a fresh instance, or `KeyError`.

**Selection (v0.20).** Which metrics a gate run measures is ruff-shaped policy, so it lives in `metrics_gate/policy.py` beside `METRIC_DEFAULTS`, never on the `Metric`: `resolve_metric_selection(available, *, select, extend_select, ignore, run_tests)`. `METRIC_FAMILIES` names three families — `quality` (`cyclomatic_complexity`, `wmc`, `lcom4`, `dit`, `cbo`, `maintainability_index`, `file_sloc`, `ruff_violations`), `docstrings` (`ruff_violations`, `docstring_example`) and `testing` (`test_pass_rate`, `coverage`, `diff_coverage`); `ruff_violations` sits in two because it measures per ruff code family, and a Stop stage keeps only its own family's scope keys. `OPT_IN_METRICS` (`ruff_violations`, `file_sloc`, `docstring_example`) are enabled only by name. The default selection is `static_metrics()` minus the opt-ins, plus the non-opt-in execution metrics under `run_tests`; `select` replaces it, `extend_select` adds, `ignore` removes (a family in `ignore` removes all its members). A name that is neither a family nor a metric, or an execution metric named without `run_tests`, raises `ValueError`, a usage error in the CLI: running tests is never implied.
### 21.4 Aggregation — `Rubric.evaluate` + the cost-tiered scheduler
`Rubric.evaluate(ctx, measurements, *, strict=False, fail_fast=False, max_workers=1) -> EvaluationReport` replaces the old free `grade()`. It runs its ordered checks through the cost-tiered scheduler (`evaluators/scheduler.py`) and folds the `CheckResult`s into one report. Each metric-backed check (`_MetricCheck`) grades on the metric's **normalized 0–1 score** (every metric owns a `Normalizer`, so direction is already baked in — higher is always better), per scope, matching the baseline by `(metric.name, scope_key)`:
- **existing scope:** `worsening = base_score − cand_score` (a *drop* in goodness); `> max_worsening` ⇒ `fail`/`kind="regression"`; otherwise the absolute level. The per-scope `score` is the normalized `0-1` goodness.
- **new scope:** absolute only, `kind="new"`. **removed scope:** ignored.
**Gate-boundary semantics** on the normalized score are higher-is-better and strict-below: a score *strictly below* `fail` fails, *strictly below* `warn` warns, exactly-on is `ok` (so coverage of exactly `0.8` with `warn=0.8` is `ok`, `test_pass_rate` of exactly `1.0` with `fail=1.0` is `ok`). Because direction lives in the normalizer, a worse-when-larger raw metric (`cyclomatic_complexity`) and a better-when-larger one (`coverage`) share the one rule.
Two aggregates fall out: the **gate** (`passed` = every *required, run* check passes; under `strict` no required run check may carry a `warn` leaf; skipped checks are neutral) and the **composite** (weight-normalized mean of the run checks' `score` over checks with `weight > 0`, spanning all families uniformly; `None` when no weights are set). The metric-backed check `mode` is `regression` (default), `absolute`, or `both` (regression failure takes precedence, then absolute), set when the check is built.

**The scheduler (`evaluators/scheduler.schedule`)** is the Strategy a `Rubric` (and the composers) use to run checks: **cheapest-tier-first** (`DETERMINISTIC` → `EXECUTION` → `JUDGED`), results always returned in **authored order**, with an optional **short-circuit** (`op="and"` stops descending into costlier tiers the moment a required check fails; `op="or"` stops on the first pass) and optional within-tier `concurrent.futures` concurrency (`max_workers > 1`; the default `1` is the deterministic path CI uses). The headline guarantee: with the short-circuit on, a lost deterministic gate **never grades the JUDGED tier** — the LLM judge is never invoked. Eval scoring turns it on only where it cannot change a result (see `CompiledTask.short_circuit_safe`). `Rubric.evaluate` defaults to `fail_fast=False` (complete report); the runner passes `fail_fast=True` for cost-saving, which `playbook eval --run --full-scoring` flips off.
### 21.5 Standalone gate — `playbook metrics` (`commands/metrics.py`)
```
playbook metrics [PATHS…] [--baseline git:REF|json:PATH|DIR] [--changed]
                 [--mode regression|absolute|both] [--strict]
                 [--select NAMES] [--extend-select NAMES] [--ignore NAMES]
                 [--run-tests | --no-run-tests] [--test-cmd "…"]
                 [--emit-measurements PATH] [--format text|json] [--repo-root DIR]
```
- **Default targets** — the repo's `src/` if it exists, else the repo root; directories recurse for `*.py`, skipping dotdirs and common ignores (`__pycache__`, `.venv`, `venv`, `node_modules`, `build`, `dist`, `.git`, `.tox`, `.mypy_cache`).
- **Default checks** — one metric-backed check per `static_metrics()` metric (fast, air-gapped), assembled into one `Rubric` via the shared `metric_check()` factory. `--run-tests` (or `[metrics] run_tests`) additionally builds a `ProjectHandle` and adds the `execution_metrics()` checks (run once).
- **Baseline** — static via `git show <ref>:<relpath>` (`git:` form) or the matching relative file under a `<dir>`; a file missing from the baseline is treated all-new. Execution baseline via temp `git worktree` (`git:`) or running in `<dir>`. `regression`/`both` without a baseline degrade to `absolute` with a note.
- **Config** — a `[metrics]` table in `.coding-agent-playbook.toml` (parsed by `metrics_gate.config.parse_metrics_config` into a `MetricConfig`, §7.1.1), read from the committed file only; CLI flags override it.
- **Library (v0.20)** — the gate is `metrics_gate/run.py::run_metrics_gate(MetricsGateRequest) -> MetricsGateResult`: discovery, baselines, measurement and grading, without printing, parsing argv or importing the CLI or jinja2, so the Stop stages call it in-process. `commands/metrics.py` is the thin CLI over it, its output pinned byte for byte by goldens. Running the suite is the explicit `run_tests` request field, never inferred from `[metrics] run_tests`, and `tool_paths` carries the pinned ruff (`machine.json` in a hook, `PATH` elsewhere).
- **Selection (v0.20)** — `--select`, `--extend-select` and `--ignore` take comma-separated metric or family names and override `[metrics] select`, `extend_select` and `ignore` key by key (§21.3).
- **`--changed` (v0.20)** — only the `*.py` files changed against the `git:` baseline (`git diff --name-only --diff-filter=AMR <ref>`) plus untracked ones; it requires a `git:` baseline. The Stop stages and the `playbook ci` `metrics` step use it, so the hook and CI agree on what was touched.
- **Snapshots (v0.20)** — `--emit-measurements PATH` writes the raw candidate measurements as `{"schema": 1, "tree": …, "measurements": [{"evaluator", "scope_key", "value"}]}`, and `--baseline json:PATH` compares against such a file instead of re-running a baseline suite.
- **`--run-tests` / `--no-run-tests`** — omitted, `[metrics] run_tests` decides; `--no-run-tests` overrides `run_tests = true`, which is how both metrics pre-commit hooks stay static.
- **Robustness (v0.20)** — every git call is bounded by `[metrics] git_timeout_s` (default 10 s) and a suite run by `test_timeout_s`; baseline sources are read through one `git cat-file --batch`; a file that does not parse, or is over 1 MB, is skipped with a note, never a traceback; and `[metrics] exclude` (default `**/eval_tasks/*/setup/**`) is never measured, so intentionally bad eval fixtures never gate a commit.
- **Exit codes** — `0` pass; `1` when `report.passed` is `False` and `fail_on_breach`; `2` on usage errors (bad path, bad baseline ref/dir, unparseable `--test-cmd`, malformed/invalid `[metrics]` config, and since v0.20 an unknown selection name, an execution metric selected without `--run-tests`, `--changed` without a `git:` baseline, and an unreadable or wrong-schema `json:` baseline).
- **Output** — `--format text` shows only `warn`/`fail` findings grouped by file plus a summary; `--format json` includes every finding (`ok` too) for machine consumption.
**Pre-commit:** the engine ships a `language: python` hook `playbook-metrics` running `playbook metrics --baseline git:HEAD --no-run-tests` — **static only**, never the suite, even when `[metrics] run_tests = true` — and the starter's `coding-agent-playbook-metrics` is the same command (§13). Execution non-regression belongs in CI (`playbook ci`'s `coverage` step, §12.11) or the manual `playbook-coverage` hook (`playbook metrics --run-tests --select testing --baseline git:HEAD`, `stages: [manual]`), which runs the project's suite: changed lines at least 80% executed and total coverage not below `HEAD`. (The static hook diffs the working tree against `HEAD`, not the index, which is exact for the common all-staged case.)
### 21.6 Eval `[gate]`/`[rubric]`/`[verdict]`/`[aggregate]` wiring — live (v1.1)
The eval task schema (§6.5.3, §15.2) declares its evaluation as layer blocks, each a `[<layer>.bind]` handle table + an `expr`. `evals/task.py::compile_eval_task` → `evals/_compile.py::compile_task` turns them into one `CompiledTask`:
- `[gate]` / `[rubric]` → `evals/_handles.py::build_handles` turns each handle binding into a `Check` (a `{check=…}` via `get_check`, a `{ref=…}` via `get_gate`/`get_rubric`, a `{rubric=[…]}` group via `Rubric.of` + a `ThresholdCheck`, or a boolean `{all_of/any_of/not=…}` group), then `compile_expr` folds the layer `expr` into a `compose.py` check tree labeled with the layer id. Each present layer is one named check (`id="gate"` / `id="rubric"`) inside the per-trial `Rubric` (named `task.id`).
- `[verdict].trial` → parsed to an AST; the verdict is **derived** from the gate/rubric results (skipped-neutral), not re-run (§21.2.6).
- `[aggregate]` → the same handle/expr machinery over `pass_at_k`/`pass_pow_k` handles, plus `trials_needed = max(k)`.

The validator (`evals/validator.py`) **trial-compiles** the blocks (surfacing any unknown check/metric/ref, malformed binding, expr ident ⊄ bind keys, rubric weight-sum ≠ 1.0, or verdict ident ⊄ present layers) and does a light `[aggregate]` shape check. The scoring bridge (§15.3.1) walks the compiled check tree to find the referenced metrics, measures them over the candidate (vs the pristine `setup/` snapshot), and runs `Rubric.evaluate` — so both layers flow through **one report**, gate + composite, and the verdict is derived from it.
```toml
# task.toml — the layered model (replaces the [expected]/[metrics]/[rubric] triple)
[gate]
expr = "build and no_regress and src_unchanged"
[gate.bind]
build         = { check = "threshold",      metric = "cyclomatic_complexity", fail = 0.5 }
no_regress    = { check = "non_regression", metric = "coverage",              max_worsening = 0.0 }  # coverage must not drop
src_unchanged = { check = "file_unchanged", path = "src/pagination.py" }
[rubric]
expr = "quality"
[rubric.bind]
quality = { fail = 0.8, rubric = [
  { judge = "Findings are prioritized correctly", weight = 0.5 },
  { judge = "Each finding proposes a concrete fix", weight = 0.5 },
] }
[verdict]
trial = "gate and rubric"
```
With no judge configured the `[rubric]` layer reports `available() is False` and skips; the report is the deterministic `[gate]` layer only, and the derived verdict treats the skipped rubric layer as neutral. With `--judge llm` the rubric criteria score against the captured diff and fold in. All thresholds are 0–1 normalized (every metric owns a `Normalizer`, §21.1).
### 21.7 Invariants
- **Single responsibility — `Metric` measures, `Check` grades, `Rubric` aggregates.** No fused `Evaluator`; no free `grade()` (it is `Rubric.evaluate`); no `value_kind`/`to_score`/`default_*`/`extra_evaluators`. A metric becomes a gateable thing only by wrapping it in a `Check` (a threshold). A `Rubric` is also a `Metric`, so check trees compose (Composite) and nest.
- **Air-gapped / no new hard deps.** Core is stdlib-only (`ast`, `dataclasses`, `enum`, `subprocess`, `xml.etree`, `tempfile`, `importlib.metadata`); `radon` is the only optional extra (`[metrics]`, lazy import via `available()`); execution metrics shell out to the *target's* `pytest` and parse XML with stdlib — no playbook dep. The engine + static `playbook metrics` run with nothing extra installed.
- **Normalization lives on the `Metric`; `higher_is_worse` is gone.** Every metric owns a `Normalizer` (`Ramp`/`Percent`/`Identity`) mapping raw→0–1 goodness (higher = better); the `Check` grades on that score and never reasons about direction. All thresholds (`warn`/`fail`/`max_worsening`) are 0–1 cutoffs. Out-of-tree metrics **must** declare a `normalizer`.
- **Registry via decorator AND entry points** — metrics under `coding_agent_playbook.metrics` (`@register_metric`), grader checks under `coding_agent_playbook.checks` (`@register_check`, resolved by a task `{check=…}`), composed gates under the new `coding_agent_playbook.gates` (`@register_gate("name")`, resolved by a gate-layer `{ref=…}`), named rubrics under `coding_agent_playbook.rubrics` (`@register_rubric("name")`, resolved by a rubric-layer `{ref=…}`); never hardcode the list; never instantiate out-of-tree metrics/checks/gates/rubrics directly. In-tree builtins/registrations win on a name clash.
- **A check is `(type) × (metric|judge) × kwargs`.** `check = "threshold"|"non_regression"` over a registered `metric=` (a `Metric`) or a `judge=` criterion (a `JudgeMetric` — an llm-judge criterion *is* a metric); non-regression works on any metric incl. judged. Weights live only inside a `rubric` group (sum to 1.0).
- **The verdict is derived, not re-run.** `[<layer>].expr` / `[verdict].trial` are a tiny boolean DSL (`evals/_expr.py`) over handle names; the per-trial `Rubric` evaluates each layer once and the verdict is a boolean fold over the results (skipped layer = neutral), so the judge / test-suite is never double-invoked.
- **Cost-tiered short-circuit.** The scheduler runs checks `DETERMINISTIC` → `EXECUTION` → `JUDGED`, so a failing deterministic gate **never invokes the LLM judge**; results stay in authored order. `--full-scoring` forces every check. The short-circuit may only save work, never change a result, so scoring disables it for a task where a skipped layer could flip the outcome (`CompiledTask.short_circuit_safe`): a verdict that is not a pure conjunction of every present layer (`gate or rubric`, `not …`, `rubric` alone beside a gate — which passed on a failing gate — or a weighted verdict), or an `[aggregate]` over a layer the short-circuit could skip.
- **Non-regression is primary** (new scopes fall back to absolute); it compares the normalized goodness (`worsening = base_score − cand_score`). Deterministic static/execution use `max_worsening=0`; judged uses a `threshold` floor + n-sample averaging; `test_pass_rate` has an optional flaky-retry.
- **Execution is opt-in and excluded from the default pre-commit** (side effects + cost); the static gate is the only thing that runs on every commit, and both metrics pre-commit hooks pass `--no-run-tests` so a config setting cannot change that.
- **ruff is a consumer-toolchain subprocess, never an engine import; radon stays the only optional extra.** `ruff_violations` shells out to the pinned or `PATH` ruff (as `cz` and `pytest` run, never imported); the engine adds no dependency for the v0.20 metrics.
- **`file_sloc` is regression-exempt** (`max_worsening=1.0`, the one exception to `max_worsening=0`): a growing legacy file is never a regression; only a configured band grades it.
- **Tool policy has one source**, shared by the CLI, the pre-commit hooks, `playbook ci` and the lifecycle hooks: `[metrics]` (with `[metrics.ruff_violations]`) for coverage, quality and docstrings. A hook is never stricter or looser than its twin, and `.coding-agent-playbook.local.toml` never overrides it (§7.2).
- **New metrics are opt-in by name**, so an engine upgrade never changes a consumer's gate results (§21.3).
- **CI parity** — `mypy` + `pytest -q` + `ruff` from the repo root with no path args.
### 21.8 Open caveats (documented, not blocking)
- **CBO≈** undercounts under duck typing (rendered approximate); **DIT** cross-module bases are approximated and low-signal in idiomatic Python; **MI** variant is pinned (SEI 0–100); **RFC/NOC/Abstractness/Distance/LCOM1-2/standalone Halstead** are intentionally absent.
- **Execution cost/flakiness:** running tests is slow and can be flaky; test non-regression is exact only modulo flaky-retry; coverage non-regression assumes a stable test set. The two-run baseline (`git worktree`) is the cost.
- **`ruff_violations` counts per file and family**, so moving a violation between functions of one file is invisible, and its `Ramp(good=0, bad=5)` saturates: a family already at five or more violations no longer regresses.
- **`diff_coverage` reports files outside the measured sources as unmeasured**, not as 0%, so a source root missing from the coverage configuration hides changed lines; the report names them.
- **MI non-regression is volatile on any growth**: adding code to a file lowers its maintainability index even when the new code is clean.
- **Judged scoring is stochastic** — meaningful only with ≥N samples; single-sample judged scores are advisory. The judge signature is reconciled (§21.2.3, Option A) — no forward-compat debt remains.
## Appendix A: Full worked example
Walking through `risk-models`, a counterparty risk scoring service, going from zero to a fully synced playbook.
### A.1 Starting state
```
risk-models/
├── pyproject.toml              # FastAPI app with pydantic, sqlalchemy, pytest
├── src/risk_models/
│   ├── __init__.py
│   ├── api/
│   │   └── routes.py
│   ├── models/
│   │   └── counterparty.py
│   └── services/
│       └── scoring.py
├── tests/
│   ├── api/
│   │   └── test_routes.py
│   └── services/
│       └── test_scoring.py
├── Dockerfile
└── .github/workflows/ci.yml
```
`pyproject.toml`:
```toml
[project]
name = "risk-models"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115",
    "pydantic>=2.9",
    "sqlalchemy>=2.0",
    "httpx>=0.27",
]
[dependency-groups]
dev = [
    "pytest>=8.3",
    "pytest-asyncio>=0.24",
    "ruff>=0.8",
    "mypy>=1.13",
]
```
### A.2 Step 1: install
```bash
$ uv add --dev coding-agent-playbook playbook-rules-bnp
```
### A.3 Step 2: init
```bash
$ playbook init
```
User answers the prompts. The tool writes:
- `.coding-agent-playbook.toml` (with `[output] commit = false`)
- `.coding-agent-playbook.local.toml`
- updated `.gitignore`
- merged `.pre-commit-config.yaml`
- prints the `pre-commit install --hook-type pre-commit --hook-type post-checkout --hook-type post-merge` command for you to run (init never runs pre-commit itself)
- runs `playbook sync` (which also writes the managed `.gitignore` block)
### A.4 Step 3: result
Generated files (all with sentinel headers; all local-only — listed in the managed `.gitignore` block, never committed):
```
AGENTS.md
.continue/
├── rules/
│   ├── 00-project-context.md       # engine
│   ├── 10-python-house-style.md    # engine
│   ├── 20-tooling-baseline.md      # engine
│   ├── 30-bnp-banking.md           # overlay
│   ├── 50-python-typing.md         # overlay (overrides engine)
│   ├── 50-python-error-handling.md # engine
│   ├── 50-python-logging.md        # engine
│   ├── 60-fastapi.md               # engine (because fastapi detected)
│   ├── 70-pydantic-v2.md           # engine (pydantic 2.x detected)
│   └── 70-sqlalchemy-v2.md         # engine
└── prompts/
    ├── refactor.md
    ├── generate-tests.md
    ├── review.md
    ├── explain.md
    └── pii-scan.md                 # overlay
.claude/
├── CLAUDE.md                       # rule-free stub (§10.3.1)
├── rules/
│   └── coding-agent-playbook.md    # always rules + "Where guidance lives", as in AGENTS.md
├── commands/
│   ├── refactor.md
│   ├── generate-tests.md
│   ├── review.md
│   ├── explain.md
│   └── pii-scan.md
└── skills/                         # core skills: scoped rules as references (§6.3.3)
    ├── python-coding/              # SKILL.md + references/python-typing.md (overlay's text) …
    ├── python-testing/
    └── python-tooling/             # static checks always; FastAPI wiring because fastapi detected
.opencode/
├── skills/                         # byte-identical to .claude/skills/
└── command/
    ├── refactor.md
    ├── generate-tests.md
    ├── review.md
    ├── explain.md
    └── pii-scan.md
.coding-agent-playbook.lock
```
### A.5 Step 4: usage
Engineer opens VS Code with Continue.
```
User opens src/risk_models/api/routes.py
→ Continue loads:
  - All scope=always rules (5 rules)
  - 60-fastapi.md (matches glob **/api/**/*.py)
  - 50-python-typing.md (matches glob **/*.py)
  - 70-pydantic-v2.md (matches glob, since pydantic models are imported)
User types: "/generate-tests for the score_counterparty endpoint"
→ Continue invokes .continue/prompts/generate-tests.md
→ The fully rendered prompt includes:
  - Project context (project_name, project_kind, pytest conventions)
  - Inlined body of python-typing rule       (via includes_rules)
  - Inlined body of pytest rule              (via includes_rules)
  → All three are guaranteed in context, regardless of which files are open
→ Assistant generates tests/api/test_routes.py extension following the mirror layout
```
The `includes_rules:` mechanism is what gives `/generate-tests` its reliability. Even if the user invokes it from a markdown file or an unrelated module, the typing and pytest rules are still in scope because the prompt declared them as dependencies. Without `includes_rules:`, the agent would only see whichever scoped rules happened to match the currently-open file's globs — which on a markdown file would be none of them. In Claude Code and OpenCode the same declaration becomes the command's `## Before you start` block: load `python-coding` and read `references/python-typing.md`, load `python-testing` and read `references/pytest.md` (§6.2.4, §6.2.5), so the rules arrive on demand instead of in the command text.
### A.6 Step 5: update
Two weeks later, the engine releases v0.4.1 with improved test-generation prompt wording.
```bash
$ uv lock --upgrade-package coding-agent-playbook
$ playbook sync
✓ Rendered all artifacts
✓ Wrote 1 file via continue adapter (.continue/prompts/generate-tests.md updated)
✓ Wrote 1 file via claude_code adapter (.claude/commands/generate-tests.md updated)
✓ Wrote 1 file via opencode adapter (.opencode/command/generate-tests.md updated)
✓ Updated .coding-agent-playbook.lock
Summary: 3 files changed
```
Engineer commits the dependency bump (`uv.lock`) — the regenerated files are local-only, so the review happens on the engine/overlay release itself. Teammates pulling the bump must **update their environment first** (`uv sync`) and then run `playbook sync`: the `post-merge` hook re-renders only with the engine and overlays *already installed* (the `language: system` init hook uses their current venv; a remote `language: python` hook uses the `rev:`-pinned engine), so on its own it renders the old wording. (Under `[output] commit = true` the engineer commits the regenerated diff instead, and the team reviews it like any other config change.)
### A.7 Step 6: generated output stays out of commits
A junior developer hand-edits `.continue/rules/50-python-typing.md` without going through the source, then force-adds it to share the tweak.
```bash
$ git add -f .continue/rules/50-python-typing.md
$ git commit -m "tweak rule"
[pre-commit running]
playbook-no-generated-output:
Generated output is staged for commit ([output] commit = false keeps it local-only):
  .continue/rules/50-python-typing.md
Unstage it (the files stay on disk) with:
  git rm -r --cached -- .continue/rules/50-python-typing.md
[commit blocked]
```
The dev unstages it and either adds a repo-local override under `playbook/rules/` or files a PR against the overlay to make the change properly; the next `playbook sync` (or checkout) overwrites the local hand-edit anyway. Under `[output] commit = true` the legacy `playbook-sync-check` hook blocks the same commit as drift instead.
## Appendix B: BNP overlay shape
For Max's reference, the BNP overlay layout in detail:
```
playbook-rules-bnp/
├── pyproject.toml
├── README.md
├── src/playbook_rules_bnp/
│   ├── __init__.py                         # registers OVERLAY
│   └── resources/
│       ├── rules/
│       │   ├── always/
│       │   │   └── 30-bnp-banking.md.j2
│       │   ├── languages/python/
│       │   │   └── typing.md.j2            # OVERRIDES engine python-typing
│       │   ├── compliance/
│       │   │   ├── pii-handling.md.j2
│       │   │   ├── dependency-allowlist.md.j2
│       │   │   └── audit-logging.md.j2
│       │   └── infra/
│       │       ├── litellm-routing.md.j2
│       │       └── air-gapped-net.md.j2
│       └── prompts/
│           ├── pii-scan.md.j2
│           └── compliance-review.md.j2
└── tests/
    └── test_rules_compile.py               # smoke test that all .j2 files render
```
The overlay is small. It carries only what's BNP-specific. Anything generic (Python style, FastAPI conventions, pytest patterns) stays in the engine where every other team can benefit from improvements.
---
## Implementation order (recap)
Cross-referencing the prior conversation's track plan:
| PR | Track | What | LoC estimate |
| --- | --- | --- | --- |
| 1 | Track 1 | Project scaffolding + adapter ABC + source ABCs | ~400 |
| 2 | Track 1b | Canonical types (`Rule`, `Prompt`, `Skill`) with markdown round-trip | ~250 |
| 3 | Track 2a | Detector module | ~400 |
| 4 | Track 2b | Renderer module | ~250 |
| 5 | Track 2c | `FileSystemArtifactSource` + `FileSystemStateSource` | ~250 |
| 6 | Track 3 | Continue adapter | ~300 |
| 7 | Track 4a | Claude Code adapter | ~300 |
| 8 | Track 4b | AGENTS.md adapter | ~200 |
| 9 | Track 4c | OpenCode adapter | ~150 |
| 10 | Track 5 | CLI (`init`, `sync`, `check`, `validate`, `render`) | ~500 |
| 11 | Track 5b | Eval Tier 0 (task schema + loader + validator + `playbook eval --list/--show/<stub>`) | ~250 |
| 12 | Track 6 | Pre-commit integration + `.pre-commit-hooks.yaml` | ~150 |
| 13 | Track 7 | Initial Python rule pack (5 rules + 4 prompts + 8 eval tasks) | ~800 (mostly markdown + TOML) |
| 14 | — | SPEC.md, README, internal wiki page | this file |
Total: ~3900 lines of Python + ~800 lines of markdown/TOML content. 5-7 weeks at half-time, 2.5-3.5 weeks full-time.
Notes on sequencing:
- **Track 1 (PR 1)** adds the source ABCs (interfaces only, in `catalog/source.py`) alongside the adapter ABC. The interfaces are public API from v1, so they ship in the scaffolding PR.
- **Track 1b (PR 2)** adds the canonical types (`Rule`, `Prompt`, `Skill` dataclasses) with markdown round-trip. Lands second because almost every subsequent module imports from `types.py`. Includes the round-trip property tests (Section 6.6.3).
- **Track 2c (PR 5)** adds the filesystem implementations after the detector and renderer because those modules' types (`Config`, `Facts`, `Lockfile`) are needed by `StateSource`.
- **Track 5b (Eval Tier 0)** lands after the main CLI because it adds CLI subcommands and one new validator pass. It is independent of the adapters — eval tasks are authoring-side artifacts and don't flow through any adapter.
- The source abstraction and the canonical types together add maybe two days of work to the early tracks but pay for themselves in test simplicity from PR 6 onward, and in clean serialization boundaries when the commercial product arrives.

**PR K — assistant lifecycle hooks (v0.20).** Authoritative design: `specs/prK-lifecycle-hooks.md` (mechanism, tracks P and K1–K4, K11) and `specs/prK-hook-pack.md` (the hook pack and the new tools, tracks K5–K10). Phases: **P (Pa → Pb) → K1 → K2 → {K3 ∥ K4} → K5 → K6 → K7 → K8 → K9 → K10 → K11**; the "Depends on" column is the hard ordering. Sizes are production lines (Python, JS, shell and shipped markdown), tests excluded.

| Track | What | Depends on | LoC estimate |
| --- | --- | --- | --- |
| Pa | Prerequisites, first PR: the sandboxed Jinja environment, an orphan-aware `sync --check`, one import-light sentinel, lockfile schema 2 with provenance, the corrected Continue hook claims, one `SECRET_PATH_GLOBS` | — | ~1,000 (with Pb) |
| Pb | Prerequisites, second PR: config extension tables and primary-only saves, config-less `validate` and the validate-gated `sync`, ruff kept off eval fixtures, the runtime prerequisites (an import-light package, unattended runner env, the extracted metrics gate, the audit writer, the `hook_handlers` entry-point group) | Pa | (see Pa) |
| K1 | The canonical `Hook` kind, discovery, the additive overlay merge, `[hooks]`/`[guardrails]`, the trust store, validate H1–H21 | Pa, Pb | ~1,100 |
| K2 | The `hook_runtime` core: dispatcher, payload normalization, decisions, failure policy, state, pins, the Stop stage contract, `playbook-hook simulate`/`doctor` | Pa, Pb, K1 | ~3,000 |
| K3 | The adapter contract, sync dispatch, `guard_config.json`, the Claude Code managed merge and launcher, the advisory degrade, the agent_harness round trip | K1, K2 | ~1,700 |
| K4 | The OpenCode V1 shim | K2, K3 | ~350 |
| K5 | Pack: protect the playbook | K2, K3 | ~1,600 |
| K6 | Pack: verify before done, the Stop coordinator, `playbook ci` | Pa, Pb, K2, K3, K5 | ~2,200 |
| K7 | Pack: rule-linked edit feedback and the shared ruff call | Pb, K2, K3 | ~1,550 |
| K8 | Pack: secrets and risky actions, with their native deny twins | K2, K3, K6, K7 | ~2,500 |
| K9 | Pack: audit and overlay mechanisms | Pb, K2, K3, K8 | ~1,250 |
| K10 | New tools: coverage, quality metrics, docstrings, commit names | Pa, Pb, K2, K6, K7, K8 | ~2,100 |
| K11 | Docs and rollout: this SPEC, the README, MIGRATION.md, dogfooding the commit convention | all | prose |
---
*End of SPEC.md v0.21.*
---
<!-- module-moves: keep -->
## Changelog
### v0.21 (2026-10-18)
Skills-first context (design `specs/prS-skills-context.md`; decision record `docs/adr/0001-scoped-rules-are-delivered-as-skill-references.md`). Only always rules stay in always-loaded context, and every scoped rule is delivered as a reference inside the one skill that owns its topic. Each bullet below is one change of the release and names the sections it changed; later changes of this release append their own bullets.
- **Section 2.3**: the "Delivered:" line for OpenCode plugin generation no longer cites §3, which is now only a pointer to `CONTEXT.md`; it cites §6.6.7 (the hook artifact) and §10.6.2 (the one generated plugin), the sections that document the shim.
- **Section 3 (glossary)**: the entries are replaced by one line pointing at `CONTEXT.md` at the repository root, which is now the project's only glossary (it also gains the **Member rule** entry), so definitions can no longer drift between two files. The other facts the old entries carried already lived in the sections that own them: rule and prompt destinations in §6.1, §6.2 and §9.7; skill layout, roots and the Continue degrade in §6.3 and §10.8; the pre-commit hook in §13; the one generated OpenCode plugin in §10.6.2; the bundled plugin in §11.5; OpenCode agents in §10.6.3 and §19 Q9; eval tasks in §6.5.
- **Sections 6.6.7 / 10.2**: the two facts only the old glossary's Hook entry carried now live in the sections that own them. §6.6.7 says a hook is "the fourth emitted canonical kind, after `Rule`, `Prompt` and `Skill`" (eval tasks are never emitted). §10.2 opens its hooks paragraph with "Hooks: none — guardrail text only." and says "Continue ships no wired hook mechanism": Continue receives each enabled hook's guardrail text only, as a rule file.
- **Section 12.6 (`playbook validate`)**: new checks over member rules and `playbook:` blocks (`commands/_validate_skills.py`, V3-V14 and W1-W3): `skill` is forbidden on an always rule, must be an id string naming a skill that exists after the layer merge and declares a `playbook:` block, and a member rule's id must be a skill-safe name; the block holds only `files` and `use_when`, each one valid line, `use_when` without a leading "Use when"; the worst-case composed description fits 300 chars; no hand-written reference collides with a member and no body has its own `## References`. Warnings cover a block without members, members without `files` and a truncated member list. The sync gate runs them, so a membership error writes nothing.
- **CI**: `tests/unit/test_docs_glossary.py` pins the §3 pointer, that no fact in the spec body is cited to it, and every term `CONTEXT.md` must define; `test_docs_lifecycle_hooks_spec.py` and `test_docs_continue_hooks.py` pin the two moved facts in §6.6.7 and §10.2 (and the one generated OpenCode plugin in §10.6.2); `test_spec_top_changelog_bullet_is_the_header_version` pins that the top changelog bullet is the header's version; `tests/unit/test_docs_migration_skills.py` pins that MIGRATION.md opens with the v0.21 section and its TL;DR table, and `test_docs_migration_hooks.py` that the release headings stay in descending version order.
- **Sections 6.4 / 8.2**: `applies_if` gains a `package_manager` key over the existing detector fact: a name, or a non-empty list meaning any of them; a repo with no detected package manager never matches; the value is validated before the fact is read, so a typo fails in every repo with an error naming the value and the four allowed names. `playbook validate`, and so the validate-gated `playbook sync`, now checks each `applies_if` key of a rule or prompt on its own, as it already did for hooks and `lint_codes.when`, so a malformed key after a false one is no longer hidden. Hooks and `lint_codes.when` gain the key with no change.
- **Shared skill root (§2.2, §4.1, §5.1, §5.3, §6.3, §10.4, §10.6, §10.8, §11.5, §17.3)**: the shared-skills adapter (`shared_skills`, id unchanged) writes `.agents/skills/<id>/`, read natively by Codex and as a compatibility root by OpenCode, instead of `shared_skills/<id>/`, which no harness reads; the bytes are those of the `.claude/skills/` and `.opencode/skills/` copies. §10.6 documents up to three OpenCode copies (v2 precedence `.opencode > .agents > .claude`; v1 warns once per extra copy, silenced by `OPENCODE_DISABLE_EXTERNAL_SKILLS` / `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS`). §10.8 gains the **Retired location** and **No loose file in a skill root** bullets; §11.5.2 drops the mypy duplicate-module caveat for the default adapters.
- **Section 10.1**: new class attribute `Adapter.retired_output_locations` (default `()`); `orchestrator.installed_output_locations()` returns it with `output_locations`, so it bounds the leftover policy (deletion allowlist and prune boundary) in write mode and `--check`, while `guard_config.json`'s `generated` path class still lists only current output. `shared_skills` declares `("shared_skills/",)` until 1.0.
- **Section 4.2 step 9**: pruning is order-independent: a declared directory is prunable only when it is real as spelled and no other declared directory is a symlink to it, so neither `.claude/skills -> ../.agents/skills` nor `.agents/skills -> ../.claude/skills` loses its target, whatever order the adapters declare the roots in (before, two of the four combinations removed it). The deletion and prune bounds (`commands/_output_locations.py`) resolve paths through `os.path.realpath`, so building and applying them no longer raises on a symlink loop on Python 3.12; the rest of the sync path does not yet make that guarantee.
- **Sections 7.1 / 11.5 / 12.1 / 12.2**: `playbook init` enables `claude_code`, `opencode`, `shared_skills` by default; `continue` is opt-in (`--adapters …,continue`), a committed `continue` survives every re-run and renders unchanged. The default set, the interactive choices (no `codex`), the question and the `--adapters` help text live in the new `commands/_init_adapters.py`. A listed `codex` adds `'codex' is not an adapter: Codex reads AGENTS.md and .agents/skills/ (the shared_skills adapter); remove it from adapters_enabled.` to the missing-adapter warning.
- **CI (shared skill root, Continue opt-in)**: `tests/adapters/test_shared_skills.py` pins the three native roots, the retired location and that no adapter writes a file directly in its skills root; `tests/unit/test_output_locations.py` pins the order-independent prune (2 orders × 2 link directions); `tests/cli/test_sync_skill_root_move.py` runs the upgrade from `shared_skills/` end to end; `tests/cli/test_init_adapters.py` pins the init default, choices and flag help; `tests/unit/test_docs_skill_roots.py` pins §10.8, §12.1 and every documented init default.
- **Always-only composites (§6.1.4, §6.1.5, §9.7, §10.3, §10.3.1, §10.4, §10.6)**: `AgentsMdAdapter` and `ClaudeCodeAdapter` drop every member rule (`skill_membership.is_skill_member`: the rule names a skill in `skill:`) in `write_rule`, since dispatch still hands every rule to every adapter (E3), and buffer one `skill_document.where_entry` per skill handed to `write_skill` (a skill with active member rules and a `playbook.files` phrase; `adapters/_where_guidance.WhereGuidanceBuffer`, keyed by skill id). `AGENTS.md` is the title, the always sections by `(priority, id)`, one `## Where guidance lives` section, then the unchanged Guardrails section; the Claude Code rules file is its title, the same sections and Where section, then the heartbeat line. Both files render the Where section with the one `where_guidance_section` function from the same skills, so it is byte-identical; it is written even when no always rule is (a Where line alone writes either file). Advisory rules of hooks Claude Code cannot enforce carry `skill=None` and keep their full sections in the rules file. Without member skills both files are byte-identical to before, and `.claude/CLAUDE.md` stays the four-line stub. `playbook sync` prints the undelivered-member warning when member rules are active and only `agents_md` is on. CI: `tests/adapters/test_always_only_composites.py`, `tests/unit/test_where_guidance_buffer.py` and two end-to-end cases in `tests/cli/test_sync_skill_references.py`.
- **Core skills (§2.1, §4.1, §4.2, §5.1, §5.3, §6.1.1, §6.1.2, §6.1.4, §6.1.6, §6.3, §6.3.2, §6.3.3, §6.4, §9.7, §10.3, §11.2, §11.5, §14.4, §16.3)**: core ships four skills, `catalog/core/skills/{python-coding,python-testing,python-tooling,ml-data}/SKILL.md`, each a third-person capability sentence plus a `playbook:` block (`use_when`, `files`). The 11 scoped rules in core name their skill in `skill:` (seven in `python-coding`, `pytest` in `python-testing`, the two FastAPI rules in `python-tooling`, `ml-serialization-security` in `ml-data`); the seven `python-coding` members get short topic-label names (`Typing`, `Error handling`, …), and `python-typing`, `python-error-handling`, `pytest` and `fastapi-app-wiring` get one-line descriptions, because a member's name is its Covers label and its description its line in the skill's index. So on every repo those rules leave `AGENTS.md` and the Claude Code rules file and arrive as `<root>/<skill>/references/<rule-id>.md`, each skill being written only while one of its members applies. New §6.1.6 shows a rendered reference and the composed `SKILL.md`; new §6.3.3 documents skills with member rules; §6.3.2 says such a skill is never degraded to a Continue prompt.
- **Sections 10.1 / 10.4**: new concrete `Adapter.note_native_skill_roots(roots)`, called once per sync before `begin_sync` with the `native_skills_root` of every enabled adapter. `agents_md` keeps its `## Where guidance lives` map only when that set is not empty, so with `adapters_enabled = []` or only `continue` the map no longer names skills no adapter writes.
- **CI (core skills)**: the reference probe (`tests/_budget_probe.py`, the module-scoped `reference_probe_repo` fixture of `tests/integration/conftest.py`) feeds `tests/integration/test_context_budget.py` (always rules plus the Where map at most 800 words, `AGENTS.md` before Guardrails at most 1,500, the whole file a strict xfail until the guardrails shrink, core descriptions at most 300 each and 2,000 in total, core plus every bundled plugin at most 6,000) and `tests/integration/test_core_skills.py` (the core inventory, `EXPECTED_MEMBERSHIP`, `EXPECTED_WHERE`, the static D13 checks over core skills only, the emitted skills, the byte-identical references and their `kind = "rule"` lock rows on the probe).
- **Always text (§5.1, §5.3, §6.1.6, §10.2.1, §16.3)**: `project-context` and `python-house-style` are rewritten to the D17 text at version 2. `project-context` renders the name, `(project kind: …)` (still the detector's `project_kind`) and the description, then two reminders: ask before coding when the scope or approach is unclear, and report a problem outside the task instead of fixing it in the same change. `python-house-style` is eight bullets, four of them with a one-line reason. Neither body has a title heading (the adapters add one) or names a skill. Every other item of the old house style has one owner in a new `python-coding` member: `python-data-shapes` (records, shallow freezing, return shapes, constants and settings; priority 44) or `python-idioms` (the `os.path` exception, flag-driven functions, composition, strings, imports, small idioms; priority 58). On the reference probe the two always sections total 231 words, down from 691, and `python-coding`'s composed description names all nine members in 226 characters. Continue, when enabled, gains `44-python-data-shapes.md` and `58-python-idioms.md`; §10.2.1's `10` and `40`-`59` rows say so.
- **CI (always text)**: `tests/integration/test_core_always_rules.py` pins the eight bullets, the D17 phrases, the two rendered reminders, the description layout, the cut reminders, that neither always body names a skill, and one owner for every moved item; `test_context_budget.py` caps the two always sections at 240 words; `test_core_skills.py` adds the two members to `EXPECTED_MEMBERSHIP` and checks their Continue rule files.
- **Sections 10.3.1 / 12.6 (`skill:` required, §6.1.1)**: a scoped rule without `skill` now fails `playbook validate` (V1, `SCOPED_RULE_NEEDS_SKILL_MESSAGE`, naming the merged skills that declare a `playbook:` block), and an override of a rule that named one gets V2's hint naming that rule's layer and skill (`check_skill_membership(..., all_rules=...)` reads every layer's definitions for it). The sync gate runs it, so such a rule makes `playbook sync` write nothing. §10.3.1 now says only a hook's advisory rule can be a scoped rule without a skill in the rules file. Breaking for overlays and repo-local scoped rules; MIGRATION.md leads with it. CI: the V1/V2 lines in `tests/cli/test_validate_skills.py`, the gate in `tests/cli/test_sync_validate_gate.py`, the MIGRATION quote in `tests/unit/test_docs_migration_skills.py`.
- **Skills-first docs (§5.3, §6.1, §6.1.1, §6.1.2, §6.1.3, §6.2.3, §6.2.5, §9.7, §10.2, §10.6, §10.7.2, §10.8, §12.6, §16.1, §20.10, Appendix A.4)**: the documentation catches up with skills-first delivery, with no behaviour change. §6.1 says where each scope lands; the §6.1.1 and §6.1.2 examples use the rule's short name `Typing` and its one-line description, and the prompt appendices of §6.2.3 and §6.2.5 show `### Typing`. §6.2.5 says `includes_rules` is how a prompt carries a scoped rule's text now that the rule is a skill reference. §9.7 gains the `skill_reference` row (rendered by `skill_document.render_member_reference`, not a `render_for` format). §10.2 says Continue keeps one rule file per rule, scoped ones included, ignores `skill:` and never gets a skill with member rules as a prompt. §10.6: a scoped rule's `globs` gate nothing on OpenCode, which loads the rule's skill by description. §10.7.2 and §20.10: `agent_harness` keeps one `references/<id>.md` per scoped rule and records `skill` in `manifest.toml`. §10.8 gains the **Member references** bullet. The top changelog bullet and this entry's intro describe the release in the present tense, and no section still claims that core has no skills. README and `catalog/README.md` point at `CONTEXT.md` for the vocabulary; MIGRATION's v0.21 subsections follow the order of its TL;DR. CI: `tests/unit/test_docs_glossary.py` adds `test_spec_section_6_1_documents_the_skill_field`, `test_spec_section_6_3_says_core_ships_skills`, `test_catalog_readme_add_a_rule_documents_skill`, `test_no_doc_says_core_ships_no_skills` and `test_readme_architecture_names_skill_references`; `tests/unit/test_docs_migration_skills.py` adds `test_migration_v0_21_tldr_pointers_follow_subsection_order`; `tests/unit/test_docs_skill_references_spec.py` pins the §6.2.5, §9.7, §10.2, §10.6, §10.8 and §20.10 sentences above.
- **Lint feedback names the skill (§6.1.1)**: sync puts the linked rule's `skill` next to its id and codes in the lint hook's `config["lint_codes"]` (`{"rule": ..., "skill": ..., "warn": [...]}`; `hook_policy.lint_codes.linked_lint_config` gains `skill_id`), set only when the rule names a skill. The post-edit ruff buckets print `rule <id> (skill <skill>): …` and the bucket-1 suffix ` (rule <id>, skill <skill>)`; a rule without a skill, or a `guard_config.json` rendered before this change, keeps `rule <id>:` and ` (rule <id>)`, so the runtime never fails on a stale config. Decision-log rule ids (`HandlerResult.rule_id`) and the resync hook's message are unchanged. `specs/prK-hook-pack.md` §E.3 shows the new prefixes. CI: `tests/hook_runtime/test_ruff_bucket_labels.py` and the two `test_linked_lint_codes_*` tests in `tests/unit/test_hook_policy_effective.py`.
- **Distilled python-best-practices content (§5.1, §6.1.6, §10.2.1)**: three new `python-coding` members, `python-performance-idioms` (priority 51), `python-async` (53, gated `python_version: ">=3.11"` because its advice needs `asyncio.TaskGroup` and `asyncio.timeout`) and `python-classes-and-protocols` (53), so the skill has twelve members and its composed description (278 characters on the reference probe) still names every one; priorities are the §10.2.1 band plus an offset from the collection's impact rating. `python-classes-and-protocols` owns class design, including the composition and framework-base-class bullets that leave `python-idioms`; `python-data-shapes` gains `slots=True`, `python-idioms` a fuller guard-clause bullet, and `python-error-handling`, `python-typing`, `python-docstrings` and `python-dependency-injection` one to three bullets each. Rule ids, gates and priorities of existing rules, and every rule's `lint_codes`, are unchanged (D23). `catalog/core/ATTRIBUTIONS.md` gains a plain-text python-best-practices entry and lists `python-classes-and-protocols` under the clean-architecture entry too; §5.1's rules tree now shows the shipped inventory.
- **CI (distilled content)**: the self-contained gate's marker regex also flags the collection's name, its publisher and the publisher's analyzer; `tests/unit/test_core_rule_shapes.py` bounds every core scoped rule to 100 rendered lines and 750 words with the reference-probe facts and checks those facts reach the `pytest-asyncio` branch and the torch, NumPy, pandas and scikit-learn sections (the probe has no `transformers`, so the Hugging Face section is not measured); `tests/unit/test_distilled_content_policy.py` scans core rules and prompts for the recommendations D8 drops, keeps each moved topic in one owner rule, requires the credit for every distilled rule and keeps the docstring example contract; `test_core_skills.py` pins the twelve `python-coding` members and the new rules' frontmatter (`DISTILLED_RULES`).
- **Distilled pytest content (§5.1)**: two new `python-testing` members gated `has_framework: ["pytest"]` with globs `tests/**/*.py` and `**/conftest.py`: `pytest-test-doubles` (priority 61), where a named fake passed in like production is the default double, autospec only a fallback at thin third-party seams and `monkeypatch` reserved for the environment, the working directory, dict entries and code that cannot take a parameter yet; and `pytest-fixtures` (63), on scope, `yield` teardown, placement, names and types, and factories. Each topic has one owner: the `pytest` rule loses its `## Fixtures` section and its `monkeypatch` clause, and gains `pytest.param` ids for non-scalar cases, parametrized expected outcomes (`pytest.raises` or `contextlib.nullcontext()` as a parameter), a `pytest.raises` that wraps only the Act, no logic in test bodies and scenario names that state the condition and the outcome. Its id, gate, priority and `lint_codes` are unchanged (D23), so `pytest-conventions-feedback` reports what it did before. The `generate-tests` prompt's line on external services now recommends named fakes and autospec only at thin seams instead of the `mocker` fixture; its `includes_rules` is unchanged. `catalog/core/ATTRIBUTIONS.md` lists both ids and the `pytest` additions. CI: `test_core_skills.py` pins the three `python-testing` members and the two `DISTILLED_RULES` rows; `test_distilled_content_policy.py` adds the `monkeypatch` and `from conftest import` owners, `test_pytest_test_doubles_puts_named_fakes_first` and `test_generate_tests_prompt_recommends_named_fakes`; the engine rule count is 20.
- **Distilled tooling content (§5.1, §6.1.4)**: four new `python-tooling` members: `python-static-checks` (priority 21, ungated, globs `**/*.py` plus the ruff and mypy config files), on treating the repo's ruff and mypy settings as the contract, running what CI runs, safe and unsafe fixes, suppressions and stub packages proposed for the dev group instead of letting mypy install them; `pytest-configuration` (23, `has_framework: ["pytest"]`), on one settings file, registered markers, narrow warning filters and a coverage bar that never drops; `python-uv-workflow` (28, `package_manager: uv`, glob `pyproject.toml`), on changing dependencies only through uv, `uv run`, and a `uv.lock` only uv writes; and `pydantic-boundaries` (63, `has_framework: ["pydantic"]`), on validating untrusted data once at the boundary with Pydantic 2 models. Configuration values in their examples are illustrations, not mandates (D8). Because `python-static-checks` is ungated, `python-tooling` is now written in every Python repo, so its authored texts are generic: the description "Conventions tied to a named tool or framework.", `use_when` "editing tool configuration or code wired to a framework" and `files` "Tool configuration and framework wiring"; on the reference probe (no `uv.lock`) its composed description is 223 characters and names five members, 236 with a `uv.lock`. A FastAPI repo that gets Pydantic only transitively gets no `pydantic-boundaries`, and creating a `uv.lock` without `uv add` surfaces `python-uv-workflow` only at the next sync. `catalog/core/ATTRIBUTIONS.md` lists the four ids; no rule's `lint_codes` changes (D23). CI: `test_core_skills.py` pins the six `python-tooling` members, the four `DISTILLED_RULES` rows and the new Where phrase, and filters the probe checks to the members the probe activates; `tests/integration/test_core_python_tooling.py` pins both descriptions; `tests/cli/test_sync_tooling_references.py` checks the uv and Pydantic gates and the skill in a plain Python repo; the dropped-recommendation scan also bans a blanket `DeprecationWarning` ignore; the engine rule count is 24.
- **Guardrails skill (§6.3, §6.3.4, §10.1)**: core ships `catalog/core/skills/playbook-guardrails/SKILL.md`, a plain skill (no `playbook:` block, a 281-character description with its own `Use when`). `commands/_sync_render.render_artifacts` splits it off the composed skills and composes it with one ``## <name> (`<id>`)`` section per on hook with an advisory, sorted by id (`hook_policy/guardrails_skill.py`); `HookDispatch.guardrails_skill` carries it, and `dispatch_to_adapters` appends it to the skills of each adapter whose new concrete `Adapter.writes_guardrails_skill(hooks)` is true: `opencode` and `shared_skills` when any hook has an advisory, `claude_code` only for a hook it does not run natively (`adapters._claude_hooks.runs_natively`, now shared with `ClaudeHookEmitter.add`). With hooks off, or no hook with an advisory, it is not written. Continue's and agent_harness's guardrail rule files are unchanged, and so is `AGENTS.md` until the one-line guardrails below.
- **CI (guardrails skill)**: `tests/unit/test_hook_policy_guardrails_skill.py` pins the split and the composed body; `tests/adapters/test_guardrails_skill_targets.py` the adapters that write it and Continue's unchanged bytes; `test_claude_code_hooks.py` that `runs_natively` agrees with `ClaudeHookEmitter.add`; `tests/cli/test_sync_guardrails_skill.py` the two roots, the `kind = "skill"` lock rows, the hooks-off case and a repo-local override that keeps the sections; `tests/integration/test_core_skills.py` runs the D13 checks over it as `EXPECTED_PLAIN_CORE_SKILLS`, its 500 lines with every core hook, and its two byte-identical probe copies; `test_sources_filesystem_bundled.py` expects five engine skills.
- **Distilled ML data content (§5.1, §6.1.4, §6.4, §12.2)**: four new `ml-data` members for array and data-frame code, all `.md.j2` with globs `**/*.py` and `**/*.ipynb` and the one gate `any_ml_stack: ["numpy", "pandas", "polars"]`: `ml-vectorization` (priority 71: whole-array operations first, a ladder before any per-value Python, and arrays and frames built once instead of grown in a loop), `ml-data-transforms` (71: inputs treated as values, NumPy views, one pandas indexer per write, no `inplace=True`, chained pipelines and named aggregation), `ml-dtypes-and-typing` (73: dtypes declared where data enters, shared categorical constants, NumPy widths, a column and dtype check after loading, pandera only where the repo already uses it, `numpy.typing` annotations) and `ml-reproducibility-and-testing` (73: one seeded generator built at the entry point and passed down, every library seeded explicitly, the seed recorded, tolerance-aware assertions on small inline data). Each renders a NumPy, a pandas and a polars section only when `ml_stack` declares that library, so a NumPy-only repo gets no data-frame guidance; torch alone activates none of them, so the resync hook's message for adding torch is unchanged. `ml-data`'s authored texts become generic (`description` "Conventions for ML models and for array and data-frame code.", `playbook.use_when` "loading or saving models, or transforming arrays and data frames" and `playbook.files`, the Where phrase, "Model, array and data-frame code"), and its composed description is 273 characters on the reference probe with every member named. `skill-nudge`'s matcher gains `notebook_edit`, so a Claude Code notebook edit nudges `ml-data` and the managed `PostToolUse` matcher in `.claude/settings.json` gains `NotebookEdit`; `playbook check` labels the hook `degraded` on OpenCode, which has no notebook tool (OpenCode writes of `.py` and `.ipynb` files still nudge), and `playbook validate` stays clean because an engine hook's degraded cells do not warn. `catalog/core/ATTRIBUTIONS.md` lists the four ids. CI: `tests/unit/test_ml_data_rules.py` pins the gate, the per-library sections and the bound with every library rendered; `test_core_skills.py` pins the five `ml-data` members and four `DISTILLED_RULES` rows; `test_skill_nudge.py` adds `test_notebook_edit_names_ml_data`; the engine rule count is 28.
- **Prompts point at skills (§5 step 5, §6, §6.2, §6.2.1-§6.2.5, §6.5, §9.3-§9.7, §10.6.1, §10.7, §10.7.2, §12.6, §12.7, §15.3, Appendix A.5; D15, D22)**: `includes_rules` is the only declaration of a prompt's rules. Claude Code and OpenCode commands carry no rule body: each opens with a generated `## Before you start` block, before the body's first `##` heading outside a code fence, with one numbered step per owning skill in `includes_rules` order listing only the references of active scoped rules (`RuleRegistryImpl.reference_for`, `_member_reference.member_reference_path`), then a closing step; a prompt with no active reference renders byte-identically. Continue prompts, the `agent_harness` prompt leaf (`render_inline_prompt_markdown`) and the eval runner get the `## Reference rules` appendix built from `includes_rules`, each id once. The `rule()` Jinja helper is removed from every template, so `build_environment` takes only the search paths and `render_for` takes `skill_references` instead of `template_body`; `generate-tests`, `review` and `security-review` drop their hand-written `## Reference rules` blocks. `playbook validate` replaces the `rule()` ⊆ `includes_rules` check with three (`commands/_validate_prompts.py`): no `rule()` call, `includes_rules` a list of non-empty strings, every id naming a rule (with a did-you-mean); `playbook render --show-rules` names each rule's delivery (skill and reference, `always loaded`, `OMITTED`, `UNKNOWN`) and a prompt still calling `rule()` is reported naming its file. §10.6.1 records the unverified OpenCode `plan` agent case and its D25 fallback.
- **CI (prompts point at skills)**: `tests/unit/test_prompt_rule_delivery.py` pins the block (grouping, wording, filtered ids, dedupe, placement around code fences and titles, byte identity without a block) and the appendix; `tests/unit/test_rule_registry.py` pins `reference_for`; `tests/unit/test_catalog_prompt_references.py` pins that no shipped prompt calls `rule()` and that every included id names a core rule with a skill when scoped; `tests/unit/test_validate_prompts.py` and `tests/cli/test_validate.py` pin the three messages, and `tests/cli/test_sync_validate_gate.py` that `sync --check-staged` refuses a leftover `rule()` call with the first one; `tests/cli/test_sync.py` and `tests/cli/test_render.py` pin the four deliveries end to end; `tests/adapters/test_agent_harness.py` pins a prompt leaf's bytes from before the change.
- **One-line guardrails (§6.3.4, §6.6.2, §6.6.7, §9.7, §10.3, §10.3.1, §10.4, §12)**: `HookFrontmatter` gains `summary: str = ""` (after `tags`; `_hook_schema.TOP_KEYS` lists it after `description`), read by `FieldReader.guardrail_summary`: a missing, blank or empty value is `""`, anything but one line of 1-120 characters without `{{` or `{%` is a `HookSchemaError` naming `summary`, the value and that shape, and `to_mapping` drops an empty one, so a hook without it round-trips byte-identically. `hook_policy.advisory` adds `GUARDRAIL_SUMMARY_MAX_CHARS` (defined in `_hook_schema`, which the parser needs and which imports nothing from the package), `guardrail_summary` (the summary, else the first sentence of the body outside code spans, with headings skipped and list and quote markers dropped, cut at a word boundary with `…`, never inside an open code span unless closing it would leave no text, when the cut is hard at the cap), `guardrail_line` and `guardrails_section`; `ResolvedHook.guardrail_text` applies it to the rendered body. `AgentsMdAdapter.write_hook` buffers one line per hook with guardrail text (an `advisory`), and `ClaudeCodeAdapter.write_hook` does the same for a hook it does not run natively, its `finalize` writing the section after the Where section and before the heartbeat line. Every core hook with a body declares a `summary`. Continue's and `agent_harness`'s guardrail rule files are unchanged; the `agent_harness` sidecar `HOOK.md` and manifest copy the new key.
- **CI (one-line guardrails)**: `tests/unit/test_types_hook.py` and `test_types_hook_roundtrip.py` pin the `summary` shape errors and the round trip; `tests/unit/test_hook_policy_advisory.py` the summary, its fallback and cut, the line and the sorted section; `test_hook_policy_resolved.py` `guardrail_text`; `tests/hooks/test_hook_summaries.py` that every core hook with a body declares a summary and that `stop-ci-parity-gate`'s names `ruff check .`, `ruff format --check .`, the type checker and the tests; `tests/adapters/test_agents_md.py`, `test_always_only_composites.py` and `test_guardrails_skill_targets.py::test_claude_code_writes_skill_and_line_for_a_hook_it_cannot_run` the two sections; `tests/cli/test_validate_hooks.py` the `FAIL` line; `tests/integration/test_context_budget.py::test_agents_md_within_1500_words` loses its strict xfail (the probe's `AGENTS.md` is about 800 words) and a new test checks one line per advised hook.
### v0.20 (2026-10-16)
Assistant lifecycle hooks (PR K). `Hook` joins `Rule`, `Prompt` and `Skill` as the fourth emitted canonical kind, rendered natively for Claude Code and OpenCode and as advisory text everywhere else, with one import-light dispatcher for every harness event. **Opt-in, with no hook output on upgrade:** a repo without `[hooks] enabled = true` gets no settings entries, launcher, shim or advisory text, only one notice line from `playbook sync`; the Claude Code rules file below is the one non-hook layout change. Authoritative design: `specs/prK-lifecycle-hooks.md` and `specs/prK-hook-pack.md`; migration: `MIGRATION.md`.
- **Layout (on top of v0.19)**: the engine's hooks live in the catalog, `catalog/core/hooks/<category>/<id>/HOOK.md`, found through the `catalog` module like every other engine kind; a bundled plugin may ship `catalog/plugins/<name>/hooks/` and an overlay package `<pkg>/resources/hooks/`. The launcher and OpenCode shim templates are engine wiring and stay in the package, `src/coding_agent_playbook/templates/hook_shims/`, next to `templates/precommit/`. The protected `resource_roots` ids keep their `pkg:<layer>/resources` spelling, and a bundled layer's id resolves to its content directory (`catalog/core/`, `catalog/plugins/<name>/`). In the engine checkout, validate-then-sync-on-canonical-edit and control-plane-guard treat `catalog/core/<kind>/**` and `catalog/plugins/*/<kind>/**` as canonical sources, as they treat an overlay checkout's `src/*/resources/<kind>/**`.
- **Catalog rename (on top of v0.19)**: the top-level `content/` tree is now `catalog/` (`catalog/core/`, `catalog/plugins/<name>/`, the guide `catalog/README.md`), and the wheel's `coding_agent_playbook/_content/` is `coding_agent_playbook/_catalog/` (`force-include` `"catalog" = "coding_agent_playbook/_catalog"`). The resolver `bundled_content.py` is `catalog.py`, with no shim: `bundled_content_root` → `catalog_root`, `bundled_layer_root` → `catalog_layer_root`, `BundledContentMissingError` → `CatalogMissingError`, the `content_root=` keyword → `catalog_dir=`; `is_bundled_layer`, `bundled_plugins`, `engine_layer_root` and the plugin namespaces keep their names (§20.3). The missing-tree line reads `error: the engine's catalog was not found (looked in <a>, <b>); reinstall coding-agent-playbook` (§12). Tooling follows: ruff `extend-exclude` and `per-file-target-version`, the `wheel-smoke` comparison (§16.4), the engine's pytest marker `catalog` and its dev pre-commit hook `catalog-checks`, the `hook_sources` defaults and the validate-then-sync globs. Eval tasks stay per layer: a bundled plugin may ship `catalog/plugins/<name>/eval_tasks/`, ruff excludes `catalog/plugins/*/eval_tasks/*/setup` next to `catalog/core/eval_tasks/*/setup`, and a test proves such a task is listed with its plugin's own prompt only when the plugin is enabled (§6.5.2).
- **`wheel-smoke` (§16.4, on top of v0.19)**: the scratch consumer repo is a git work tree, because `init` turns the hooks on and hooks are git-only, and a sixth step runs `playbook-hook simulate` on the `bash_rm_root` payload with the wheel's own hooks (exit code 2).
- **Sections 2.2 / 2.3**: the "No OpenCode plugins" non-goal narrows to user-authored plugins — the engine owns exactly one generated plugin, `.opencode/plugins/playbook-hooks.js` — and the "OpenCode plugin generation" aspiration is marked delivered.
- **Section 3 (glossary)**: Hook is the fourth emitted kind (the Continue correction of PR K Track P is kept verbatim); the Plugin (OpenCode) entry names the one generated shim.
- **Sections 4.1 / 4.2 (architecture, data flow)**: the component diagram gains `hooks/**/HOOK.md`, `hook_policy.resolve_effective_hooks`, `write_hook`, the sync-level `guard_config.json` and the `playbook-hook` runtime, plus a runtime-path diagram (launcher or shim → `<pin> -I -m coding_agent_playbook.hook_runtime dispatch` → exit 0 or 10). The data flow reads the policy tables from the committed file, runs the validate gate, merges hook layers additively, gates hooks in `resolve_effective_hooks`, dispatches `begin_sync` / `write_hook` / `finalize` / `managed_lock_entries`, writes the sync-level hook output, and (new step 10) pins the interpreter, prints notices and asks the TTY-only trust questions.
- **Section 4.3 (design recap)**: the sentinel positions and exceptions for hook outputs (`# …` launcher, `// …` shim, read-only Claude commands in the second position, byte-copied hook scripts and strict JSON without one), and the hook invariants of `specs/prK-lifecycle-hooks.md` §I, recorded here because the repo's agent instruction files are local-only.
- **Sections 5.1 / 5.3 (layouts)**: the engine gains `hook_runtime/`, `hook_policy/`, `hook_registrations/`, `security/`, `guard_config.py`, `hooks_config.py`, `metrics_config.py`, `_sentinel.py`, `_pep503.py`, `gate_scan.py`, `adapters/claude_settings.py`, the bundled `catalog/core/hooks/` and `templates/hook_shims/`; the consumer gains `playbook/hooks/`, `.coding-agent-playbook/hooks/`, `.claude/hooks/playbook/launch.sh`, `.opencode/plugins/playbook-hooks.js` and managed entries in the user's `.claude/settings.json`. The `.opencode/plugin/` ownership note now gives the user every plugin but the shim.
- **Sections 6.1 / 6.2 / 6.6**: `RuleFrontmatter.lint_codes`, `PromptFrontmatter.write_scope` and `output_contract`; the `Hook`, `HookFrontmatter`, `HookMatcher`, `HookHandler` and `HookSchemaError` types with their round trip (`Hook.from_dict(hook.to_dict())` is the identity); new §6.6.7 on the authoring layout, the event table, handlers, the advisory degrade, `ResolvedHook` and the agent_harness sidecar.
- **Section 6.4**: the `has_dev_dependency` predicate (PEP 503-normalized names over `facts["dev_dependencies"]`).
- **Sections 7.1 / 7.2 (config)**: new §7.1.1 with every `[hooks]` key, `[hooks.<hook-id>]`, `[hooks.commit_convention] cutover_date`, every `[guardrails]` domain key with its merge policy, the `[metrics]` keys (new: `select`, `extend_select`, `ignore`, `exclude`, `git_timeout_s`, `test_timeout_s`, `[metrics.ruff_violations]`), the on-formula, and the trust-on-first-use approval. `.local.toml` never carries `[hooks]`, `[guardrails]` or `[metrics]`.
- **Section 9.7 (formats)**: `hook_advisory` and `hook_claude_settings`; the `disallowed-tools` frontmatter of a read-only Claude command and `agent: plan` for a read-only OpenCode command.
- **Section 11 (overlays)**: new §11.6 — overlays only add to a hook, the `extend` / `strictest` / `relax` / `replace` config key policies, `mandatory` overlay hooks, data-only overlays. The stale §11.5.1 claim that the canonical model has no hook artifact is corrected.
- **Section 19**: Q8 (OpenCode plugin generation) resolved; Q1 partially answered for executable overlay code.
- **Sections 20.2 / 20.10**: the concrete `ArtifactSource.list_hooks` / `collect_hooks` and `StateSource.load_primary_config` / `load_local_overrides` / `load_policy_tables` defaults; manifest `kind = "hook"` with `hook_frontmatter`, and the optional `lint_codes` / `write_scope` / `output_contract` sidecar fields.
- **Implementation order (recap)**: the PR K tracks, Pa and Pb through K11.
- **Section 10 (adapters)**: §10.1's ABC gains the concrete `hook_support`, `shared_outputs`, `runtime_outputs`, `planned_runtime_outputs`, `begin_sync`, `write_hook` and `managed_lock_entries`, the sync dispatch order and a per-adapter hook table; the stale claim that Claude Code is the only adapter overriding `finalize()` is corrected (four of the six shipped adapters do). New §10.3.2: the managed `.claude/settings.json` merge (ownership by lockfile hash, restore-and-warn, a span-preserving splice, the file never deleted, `settings.local.json` never written), the launcher (never written over a user file or through a symlink), the interpreter pin, the heartbeat line, read-only command frontmatter, the behaviour under both `[output] commit` values, and the Claude Code caveats (launch directory, trust and `-p`, cloud sessions, policy kill switches, hot reload, Windows, concurrent handlers, incidental reach and `gemini hooks migrate`). §10.4: the `## Guardrails` section. §10.6: OpenCode ≥ 1.18.29 and `agent: plan` for read-only commands; §10.6.2, formerly the out-of-scope hook gap, now documents the one generated V1 shim (events, spawning, the restart notice, the inert V2 `setup()` stub, the refusal of a same-named user plugin); §10.6.4 gives users every plugin but the shim. §10.7: the `.playbook/hooks/<id>/` sidecar and the `rules/30-guardrail-<id>.md` advisory.
- **Claude Code rules file (on top of PR K)**: §10.3.1 — the `claude_code` adapter's `finalize` writes the rule sections, hook advisories and heartbeat line to `.claude/rules/coding-agent-playbook.md` and a rule-free four-line `.claude/CLAUDE.md` stub; both paths are named once in the stdlib-only `adapters/claude_rule_paths.py`, and both are `output_locations`, composite lock entries, managed-`.gitignore` entries and composite singletons of the guard tables (`_guard_config_protect.COMPOSITE_SINGLETONS`), so guard-generated-outputs and the drift scan cover the rules file like the stub, and no other `.claude/rules/` file is ever read, written or deleted. §10.6 keeps the v1 read-time attachment, which now adds only the stub's header; the `OPENCODE_DISABLE_CLAUDE_CODE_PROMPT=1` workaround is needed only before a repo is re-synced. Also §2.1, §3, §4.1, §4.3 (the upgrade invariant now reads 'no hook output'), §5.1, §5.3, §6.1.4/§6.1.5, §6.6.7, §9.7, §10.1, §10.3.2, §10.4, §12.2, §12.3, §12.7, §14.4 and A.4.
- **Section 12 (CLI)**: `init` asks to enable hooks (`--no-hooks`); `sync` prints the absent-table notice or the hook summary lines, pins the interpreter and asks the TTY-only trust questions; `sync --check` compares the hook outputs and re-merges `settings.json` against the real file; `playbook check` gains the Hooks block and scoped drift lines; `validate` runs without a consumer config, gates `sync` (P8) and lists H1–H21; `render <hook-id>`; `import-harness` rebuilds hooks. New: §12.11 `playbook ci` (the `CI_STEPS` table and a pull-request job that passes the PR title only through `env:`), §12.12 `playbook metrics` (a pointer to §21.5), §12.13 the `playbook-hook` runtime (`dispatch` and its 0-or-10 exit contract, the kill switches, the Stop stage order, `simulate`, `doctor`), and §12.14–§12.19 the off-workstation twins `gate-scan`, `scan-secrets`, `scan-sinks`, `check-deps`, `check-commit-trailers` and `check-notebooks`.
- **Section 13 (pre-commit)**: the stale §13.1 snippet gains `playbook-metrics` (now with `--no-run-tests`), the manual `playbook-coverage`, `playbook-secrets`, `playbook-commit-msg` and the opt-in `playbook-notebooks` / `playbook-scan-sinks`; the §13.2 starter gains `--no-run-tests`, `coding-agent-playbook-coverage`, `coding-agent-playbook-secrets` and the conditional `commit-msg` hooks with `default_install_hook_types`.
- **Section 14.4 (lockfile)**: scoped `json:<pointer>` entries and `executable` are populated; the `hook` and `runtime` kinds and the `registration:` / `permission:` artifact ids are documented, and `playbook check` reports scoped drift.
- **Sections 16 / 17**: the §16.4 CI list matches `ci.yml` (no gitleaks), and new §16.6 is the hook test strategy (`tests/hook_runtime/`, `tests/hooks/`, `tests/security/`, golden payloads, named fakes, the import budget, gated latency and end-to-end tests). §17.1 adds that hooks never reach the network; §17.3's unshipped gitleaks promise becomes `playbook-secrets` / `playbook scan-secrets`; §17.4 names `security/audit.py` as the one log writer (guard-decision-log, local-audit-log) and marks the `playbook sync` audit line as not written yet.
- **Section 21 (metrics)**: the opt-in `ruff_violations`, `file_sloc` and `docstring_example` rows; `diff_coverage` with the `diff_based` descriptor, the new `CoverageReport` and `ProjectHandle` fields and the `CoverageCheck` `warn=0.8` fix; `resolve_metric_selection`, `METRIC_FAMILIES` and `OPT_IN_METRICS`; the `metrics_gate.py` library, the new flags and usage errors, and the pre-commit paragraph; new invariants (ruff as a consumer-toolchain subprocess, the `file_sloc` exemption, one tool policy) and caveats.
- **CI**: `tests/unit/test_docs_lifecycle_hooks_spec.py` derives the names it requires from the landed code (`HooksConfig`, `GuardrailsConfig` and `MetricConfig` fields, the canonical `Hook` dataclasses, `renderer.BUILTIN_FORMATS`, the merge key policies, the manifest kinds), and `tests/unit/test_docs_lifecycle_hooks_cli.py` does the same for §10–§21 (the `Adapter` members, `cli._SUBCOMMANDS` and their argparse flags, `CI_STEPS`, the `playbook-hook` usage, `STOP_STAGE_ORDER`, `.pre-commit-hooks.yaml`, the starter template, the OpenCode floor, the metric families), so a key, field, command, flag, step, hook id or metric added without documentation fails the docs gate.
### v0.19 (2026-10-16)
The engine's own content moves out of the Python package into a top-level `content/` (now `catalog/`) tree of the same repository, and the opt-in "packs" become **bundled plugins**. Content maintainers now work in one place and never touch the logic layer, and a bundled plugin no longer needs a Python subpackage to exist. Rendered output is unchanged: a consumer repo with every adapter and both plugins enabled renders the same files, bytes and modes as before the change, under the old and the new names alike (only the config file, which is input, and the lockfile's `rendered_at` timestamp differ). The third-party overlay contract (`<pkg>/resources/{rules,prompts,skills,eval_tasks}`) and the entry-point groups are unchanged.
- **Sections 4.1 / 5.1 / 6.3 / 6.5.2 / 11.1 (layout)**: `content/core/` (now `catalog/core/`) holds the engine built-ins (rules, prompts, eval tasks, `ATTRIBUTIONS.md`; was `src/coding_agent_playbook/resources/` minus `precommit/`), and `content/plugins/<name>/` holds each bundled plugin (was `src/coding_agent_playbook/packs/<name>/`), with a `README.md`, its `ATTRIBUTIONS.md` and, for `superpowers`, its `LICENSE` at the plugin root. The contributor guide is `content/README.md`. `src/coding_agent_playbook/` is logic only, apart from `templates/precommit/config.yaml.j2` and `py.typed`. The examples' paths (§6.1.2, §6.2.2, §6.5.3, §11.3, §12.7) follow. `content/` is a source folder only: hatch copies it into the one wheel as `coding_agent_playbook/_content/`, an internal layout that is not a user-facing contract.
- **Section 3 (glossary)**: new entry "Bundled plugin (formerly pack)"; "Plugin (OpenCode)" is renamed "OpenCode plugin". Prose says *bundled plugin* for ours, because "plugin" also means an OpenCode plugin, an upstream Claude Code plugin and an entry-point extension.
- **Section 20.3 (`bundled_content.py` (now `catalog.py`), new)**: the one leaf module that locates the engine's content — `bundled_content_root` (the wheel's `_content/` when it holds `core/`, else a checkout's `content/` (now `catalog/`) under `src/`, else `BundledContentMissingError` naming both paths), `bundled_plugins` (sorted dotted names from the directory listing; identifier names only, no `.`/`_` prefix), `canonical_overlay_name`/`canonical_overlay_list`, `is_plugin_namespace`, `is_bundled_layer` and `bundled_layer_root` (exact membership only, so config text is never joined onto a path). `_resource_subdir` routes bundled layers through it, outside its `except Exception` guard, and keeps its single two-segment `resources.files(...).joinpath("resources", subdir)` call for every other package.
- **Section 11.5 (bundled plugins and the `packs` alias)**: a bundled plugin is pure content, enabled as `coding_agent_playbook.plugins.<name>`; adding `content/plugins/<name>/` (now `catalog/plugins/<name>/`) (an identifier name, not starting with `_` or `.`, holding at least one kind directory) ships one with no change outside `content/`. **Deprecated alias:** `coding_agent_playbook.packs.<name>` keeps working through 0.x. `Config.__post_init__` canonicalizes `overlays_enabled` (same order, no dedup) and records the rewritten names in the derived field `deprecated_overlay_names` (`compare=False`, never written by `to_dict`). `SyncContext.from_repo` prints one `warning: <file>: overlays_enabled: '<old>' is deprecated; use '<new>'` line per deprecated name, naming `.coding-agent-playbook.local.toml` when that file sets `overlays_enabled` and `.coding-agent-playbook.toml` otherwise. `init --overlays` canonicalizes, prints `warning: --overlays: '<old>' is deprecated; use '<new>'` after its preflight passes, and writes the canonical names on a first run and on a re-run. `check --refresh` writes a deprecated name back as parsed, `sync` never rewrites the config, and nothing rewrites the local file. The config fix-it hint never recommends the deprecated name. **Removed with no shim:** the `coding_agent_playbook.packs[.<name>]` modules and their `PACK_NAME` constants; list the dotted string instead.
- **Sections 4.2 / 11.1 / 11.5 / 12.1 / 12.2 / 12.4 / 12.6 (preflight)**: `_unusable_reason` classifies a bare plugin namespace first (`the bundled plugin namespace, not a plugin`, never imported), then a bundled layer, the engine included (usable when `bundled_layer_root` resolves, else `no such bundled plugin`, never imported), and only then imports an overlay package and checks for `resources/` as before. The hint is ` (bundled plugins: <comma-separated sorted dotted names>)`, still appended for a name under the engine package or close to a plugin's leaf. The refusal headers call each entry an overlay package or bundled plugin: `sync` prints `error: overlay package(s) or bundled plugin(s) in overlays_enabled are not usable here:`, and `init` prints `error: <origin> names overlay package(s) or bundled plugin(s) that cannot be used here; nothing was written:`. The `check`, `validate` and §11.5 sample outputs show the new reason, hint and warning lines.
- **Section 12 (loud failure)**: `cli.main` catches `BundledContentMissingError` (now `CatalogMissingError`) (raised by every command that loads the content: `init`, `sync`, `check`, `validate`, `render`, `eval`) and exits 2 with `error: the engine's bundled content was not found (looked in <a>, <b>); reinstall coding-agent-playbook`; a lookup miss used to produce zero engine artifacts silently. `init` locates the content in its preflight, before writing anything.
- **Sections 12.8 / 15.3 (eval paths)**: the `--show` `Source:` label is built from the layer, with `<dir>` the task directory's name (never `task.id`): `<source_package>/eval_tasks/<dir>/` for bundled layers (was `coding_agent_playbook/resources/eval_tasks/<dir>/`), `<source_package>/resources/eval_tasks/<dir>/` for third-party overlays (unchanged), and `playbook/eval_tasks/<dir>/` for repo-local tasks. `_infer_prompts_dir` returns `<layer>/prompts` when the task directory's parent is `eval_tasks`, without searching for a `resources` segment or resolving symlinks. **Behaviour change:** a repo-local task under `playbook/eval_tasks/` now finds `playbook/prompts/`; before, it never found a prompt.
- **Section 13.2 (pre-commit template)**: the template moves to `src/coding_agent_playbook/templates/precommit/config.yaml.j2` (engine wiring, not content). `commands/init.py:precommit_template_dir()` raises an explicit error naming the expected path when it is missing, replacing an `assert` that `-O` strips; `_resource_subdir(ENGINE_PACKAGE, "precommit")` now returns `None` by design.
- **Sections 14.1 / 16.4 (packaging, CI)**: `[tool.hatch.build.targets.wheel.force-include]` gains `"content" = "coding_agent_playbook/_content"` (now `"catalog" = "coding_agent_playbook/_catalog"`); the sdist needs no change. Force-include ignores `.gitignore` in both directions, so releases are built from the sdist (plain `uv build` or `python -m build`, never `--wheel`), and a pytest guard asserts that `git ls-files -ci --exclude-standard` is empty. A new CI `wheel-smoke` job builds the sdist and wheel, compares the wheel's `_content/` entries with `git ls-files content`, installs the wheel into a fresh venv, runs `playbook init --overlays coding_agent_playbook.plugins.superpowers,coding_agent_playbook.plugins.python_design` in a scratch directory (exit 0, no `warning:`, both plugins' skills synced) and checks that `playbook eval --list` reports `23 eval tasks`.
- **Tooling**: ruff `extend-exclude` is repointed to `content/plugins/superpowers` (now `catalog/plugins/superpowers`) and `content/plugins/python_design/**/*.md`, and `per-file-target-version` to `content/plugins/*/skills/*/scripts/*.py`. The mypy `exclude` patterns for `resources/eval_tasks/…` and `packs/…/scripts|references` are deleted, because content is outside mypy's `files`.
- **Sections 11.5.1 / 11.5.2**: paths follow the move (`content/plugins/<name>/{README.md,LICENSE,ATTRIBUTIONS.md}` (now `catalog/plugins/<name>/{README.md,LICENSE,ATTRIBUTIONS.md}`), gates under `tests/plugins/`). §11.5.2's "no plugin name" rule is scoped to skill files: no skill file names the source Claude Code plugin; the plugin root's `README.md` carries no URL and does not name it either.
- **Content (path text only)**: the 10 `find-injected-vuln-*/task.toml` descriptions say `See eval_tasks/ATTRIBUTIONS.md.` (was `See resources/eval_tasks/ATTRIBUTIONS.md.`), and line 3 of `content/plugins/superpowers/ATTRIBUTIONS.md` (now `catalog/plugins/superpowers/ATTRIBUTIONS.md`) says `skills/` (was `resources/skills/`). Both ATTRIBUTIONS.md files keep "pack" and "the plugin" (the upstream Claude Code plugin), and the engine-authored additions inside the vendored superpowers skills keep "pack", which output parity requires. Vendored upstream files stay byte-identical, including all 15 `references/LICENSE` copies.
- **CI**: `tests/packs/` → `tests/plugins/`; shared checkout-anchored paths in `tests/_content.py` (now `tests/_catalog.py`) (with one test that the resolver agrees with the tree); "found at least one" assertions wherever empty content used to pass; resolver, alias end-to-end, loud-failure, prompts-dir, template, two-portion namespace overlay, content-layout (leaf rule, no link to a layer-root file, no content under `src/`) and gitignore-guard tests.
### v0.18 (2026-10-14)
No command writes local overrides into the committed config, and the two that rewrite it — `playbook init` and `playbook check --refresh` — keep what `Config` does not manage. Two bugs, shared by a re-run of `init` and by `check --refresh` on a repo with a committed config: (1) each loaded the config through `load_config`, i.e. merged with the gitignored `.coding-agent-playbook.local.toml` (§7.2), and saved the result as the committed file — a personal `adapters_enabled = ["claude_code"]` turned the team's `["continue", "claude_code", "opencode", "shared_skills"]` into `["claude_code", "continue", "opencode", "shared_skills"]`, and a personal `[user_choices]`, `overlays_enabled` or `[output] commit` (which, on an `init` re-run, also picked the committed pre-commit hooks) landed in the commit; (2) the round trip through `Config` dropped every table `Config` does not carry — `[links]` and `[metrics]`, which `validate` and `metrics` read from the raw TOML — and every unknown key inside the tables it does carry (`[project] homepage`), although `init` promised to preserve what it does not know. **Behaviour change:** an `init` re-run's committed file now depends on the committed file, the answers and the detected facts only, a refresh's on the committed file and the detected facts only. Both exit 2 with nothing written on a committed file missing a required key (they used to complete it from the local file) and on a local file `Config` refuses (a malformed `[output]`, checked up front); a first `init` checks the latter too, where it used to write every file and fail only in its final sync. `check --refresh` no longer round-trips through `Config`, so only `[detector_cache]` changes (an explicit `adapters_enabled = []` or `description = ""` used to vanish, and `artifact_source`/`commit = false` to appear). Each config file is checked whole on its own, naming it, in every command: a syntax error, a non-UTF-8 byte or inline values nested too deeply (tracebacks, exit 1), a top-level `project`/`engine`/`storage`/`output`/`detector_cache`/`user_choices` that is not a table (a `TypeError`/`AttributeError`/`ValueError` traceback; a local one was blamed on the committed file, and a committed one hidden by a local table crashed only `init`/`check --refresh`), and a malformed `[output]` (its error now names the file) are `ConfigError`s, exit 2. A missing required key (`schema_version`, `[project] name`/`kind`, `[engine] version`) is a `ConfigError` (exit 2) in every command, where it was a `KeyError` traceback. `init` now checks `--overlays` even when a local `overlays_enabled` replaces it for its own sync: a local list used to hide an unusable `--overlays`, which was committed and broke every teammate's `playbook sync`. A first `init` writes the same bytes as before, except where the old writer was wrong: a detected dependency name that needs quotes is now written quoted in `[detector_cache]` (`"ruamel.yaml" = ">=0.17"`, which used to be re-read as a `ruamel` table; a non-ASCII name such as `Café_Pkg` used to make the file unparseable) — see the TOML writer bullet.
- **Section 7.1 (config)**: a missing required key is a `ConfigError`; each file is checked whole on its own before the merge (`config.check_config_file`: a file `tomllib` cannot read, a non-table `project`/`engine`/`storage`/`output`/`detector_cache`/`user_choices`, a malformed `[output]`), so the error names the file at fault; `init` checks each file on its own, then the config its final sync will load, before writing (a first run too); `init` and `check --refresh` keep the committed `[output] commit`, not a local one.
- **Section 7.2 (local overrides)**: the invariant — local overrides are read, never written back: `save_config_table` is the committed file's one writer and `commands/_committed_config.ConfigRewrite.save` its one caller, a `ConfigRewrite` being built only by that module's `plan_*` functions from the committed file alone (or with none, on a first `init`); an AST test pins the writers, the builders and that no importer of `_committed_config` references `load_config`; nothing rewrites an existing local file.
- **Section 12.1 (`playbook init`)**: safe to re-run (re-serialized, not clobbered); the order of the pre-write checks; what a re-run replaces (what `Config` owns, from the updated committed config, never merged with the old file: an omitted or empty `--overlays`, an empty description and a stale detector entry stay dropped; adapters are the committed list then each answered one it lacks; `schema_version`/`[engine] version`/`[storage]`/`[user_choices]`/`[output] commit` kept) and preserves (every other top-level key and the unknown keys of `[project]`/`[engine]`/`[storage]`/`[output]`, same parsed values); a re-run needs a complete committed file; comments, layout and literal spelling are not kept. The pre-commit hooks follow the committed `[output] commit`; the final sync still uses the merged config. `--overlays` is checked even when the local file's list replaces it.
- **Sections 12.4 / 12.5 (`playbook check --refresh`)**: rewrites only `[detector_cache]`, from the committed file alone, writing every other entry back as parsed (`plan_detector_cache_refresh`, no `Config` round trip); exits 2 with nothing written or printed on a committed file missing a required key or a local file that breaks the result.
- **Section 20.3 (state source)**: `FileSystemStateSource.read_committed_config_table()` reads the committed file alone and `has_committed_config()` says whether it exists; `save_config_table(table)` writes a decoded table verbatim (`save_config(config)` wraps it, unused by commands); `preview_config(table)` is what `load_config()` will return after that save, without writing; the rewrites are `commands/_committed_config`'s `plan_*` functions. `load_config()` keeps its merged behaviour, so `sync` and every other command still apply local overrides.
- **TOML writer**: `_toml.dump_toml` (moved from `sources/filesystem.py::_dump_toml`, which pushed that module past 500 lines) writes anything `tomllib` parses — tables and arrays of tables at any depth (the deliberate two-level `TypeError` is gone; preserved `[metrics.thresholds.<metric>]` tables nest three deep), a table's own keys before its sub-tables, empty tables, a non-empty array holding only tables as `[[…]]` sections and every other array (mixed, nested, empty) inline, tables in it as inline tables, keys quoted through `_toml.format_key`. `_toml.format_scalar` gains `float` (`float.__repr__`: `1.0`, `1e-05`, `inf`, `-inf`, `nan`, plus `-nan`, whose sign `repr` drops) and `date`/`datetime`/`time` (`isoformat`; a time with an offset or a sub-minute offset is a `ValueError`, as TOML cannot hold it); an integer too long for `str` is written in hex, and a negative one — no TOML literal holds it, and `tomllib` never yields one — is a `ValueError`. Other Python types still raise `TypeError`. Both walks are iterative — `_dump_toml` over tables and `format_scalar` over inline values — so no depth `tomllib` accepts can overflow the writer (a recursive table walk hits `RecursionError` at headers a few hundred levels deep, and `tomllib` builds headers with no depth limit). Four latent writer bugs are fixed, each with a regression test: `format_key` left non-ASCII keys (`café`) bare and `format_string` wrote U+007F raw, both unparseable; `format_scalar` passed every `int` to `str`, which raises `ValueError` past `sys.get_int_max_str_digits()` digits although `tomllib` reads such integers from `0x`/`0o`/`0b` literals (the Config, lockfile and manifest paths alike); and `_dump_toml` wrote keys and header parts raw instead of through `format_key`, so a key that needs quotes was valid TOML that `tomllib` re-read as a different structure — a detected `ruamel.yaml` dependency became a `ruamel` table on a first `init`, and a committed `[user_choices] "docs.style"` became a `docs` table on every `save_config` (`init` re-run, `check --refresh`). Config, lockfile and `.playbook/manifest.toml` bytes are unchanged wherever the old output parsed back correctly (golden tests). The manifest (§20.10) now also writes the float and date values YAML frontmatter yields (`applies_if`, `input_variables`, a skill's extra frontmatter), which used to stop `init`/`sync` with `TypeError: manifest TOML does not support value of type float`.
- **Implementation**: `config.py` (`check_config_file`, `Config.from_dict` running it and the required-key check, `parse_output_config(…, source=…)`; it re-exports `ConfigError`, `check_enabled_keys` and `check_config_tables`), the new `config_schema.py` (split from `config.py`: `ConfigError`, the enabled-key checks with an iterative table walk, `check_config_tables`, `required_value`), the new `config_entries.py` (`CONFIG_MANAGED_KEYS`, `CONFIG_MANAGED_TABLE_KEYS`, `unmanaged_config_entries`, `with_unmanaged_entries`), `sources/filesystem.py` (`read_committed_config_table`, `has_committed_config`, `preview_config(table)`, `save_config_table`, `save_config` through it, per-file checks and decode errors in `_read_config_file`), `_toml.py` (`dump_toml`, moved here, and the iterative `format_scalar`), `harness/manifest.py` (docstring only), the new `commands/_committed_config.py` (`ConfigRewrite`, `plan_first_config`, `plan_committed_update`, `plan_detector_cache_refresh`, `detector_cache_table`), `commands/init.py` (`_plan_config`, `_fresh_config`, `_apply_answers`, `_adapters_union`, `_overlay_lists_to_check`) and `commands/check.py` (`_refresh`).
- **CI**: `tests/cli/test_init.py` (a re-run with every local override leaves the committed file byte-identical, committed `[user_choices]` included, and the local file untouched; the committed hooks ignore a local `[output] commit = true`; `[links]`, `[metrics]` with 3-level thresholds, float weights and arrays, a future table with a date, a mixed array, nested tables and an array of tables, and a future top-level key come back as the same parsed values, compared type-strictly; an emptied `--overlays`, a dropped description and a stale detector entry stay dropped; unknown keys inside `[project]`/`[engine]`/`[storage]`/`[output]` survive; a local file `Config` refuses, and a committed file missing a key only the local file supplies, exit 2 with every file unchanged), `tests/cli/test_check.py` (`check --refresh` with local overrides changes only `[detector_cache]` and leaves the local file untouched; the same two exit-2 cases), `tests/unit/test_committed_config.py` (each `plan_*` builder: the committed file alone, a refresh changing nothing but `[detector_cache]`, a first-run plan refusing an existing file, both plans refusing a broken local file or a committed file missing a key; an AST walk: the writers and `ConfigRewrite` builders are named only in `_committed_config`, and no importer of it references `load_config` — four bypass mutants are caught), `tests/unit/test_sources_filesystem.py` (the committed-only reader: local file ignored even when broken, missing file, `ConfigError` naming the committed file; `save_config_table`/`save_config`, unknown keys of managed tables; `preview_config` writes nothing; a syntax error, a non-UTF-8 byte and deep inline nesting are `ConfigError`s naming either file; a 1000-level header loads; every misread table shape names the local file from `load_local_overrides`, `load_config` and `preview_config`, and the committed file even when a local table hides it; a `save_config`/`load_config` round trip keeps `"docs.style"` and `ruamel.yaml` keys), `tests/cli/test_check.py` (`check`, `check --refresh`, `sync` and `validate` name the local file for a local non-table, and refuse a committed non-table a local table hides; `check --refresh` keeps a hand-written file's explicit empties), `tests/cli/test_unusable_overlays.py` (`init` refuses an unusable `--overlays` behind a usable local list, and reports both lists), `tests/unit/test_config.py` (`CONFIG_MANAGED_KEYS` and `CONFIG_MANAGED_TABLE_KEYS` equal what a full `to_dict` writes, the full fixture sets every dataclass field off its default, every key is read by `from_dict`; a missing required key or a non-table `project` is a `ConfigError` naming the file, the key and the line to write; `unmanaged_config_entries`/`with_unmanaged_entries`), `tests/unit/test_dump_toml.py` (a round-trip corpus over every TOML value type, a fixed-point check, the rendering shape, golden Config/lockfile bytes, tables, arrays of tables and inline values nested 200–400 deep written with 60 stack frames to spare, integers past the int-to-str limit, Config keys that need quotes), `tests/unit/test_toml.py` (integral floats, `-nan`, hex for huge ints — with the int-to-str limit pinned by the `default_int_max_str_digits` fixture, so `PYTHONINTMAXSTRDIGITS` cannot change the outcome — decimal when the limit is off, inline nesting twice the recursion limit) and `tests/harness/test_manifest_roundtrip.py` (golden manifest bytes; float and date frontmatter through `write_manifest`/`read_manifest` and `import-harness`). Round trips compare with `tests/toml_equality.py`, which checks exact types, float signs (NaN-aware) and datetime offsets — Python `==` passes `1.0` written as `1`.
### v0.17 (2026-10-14)
Bundled opt-in packs and the `superpowers` pack. The pack itself is purely additive: no rendering, config-schema, or lockfile change; it is consumed through the existing overlay path and rendered by the v0.15 native-skill adapters, and leaving or overriding it is settled by the v0.16 lockfile leftover policy. The config hardening below changes what is *accepted*: the enabled-list shapes the engine used to misread silently are now refused (other unknown keys are still ignored).
- **Section 11.5 (new)**: packs are importable subpackages under `coding_agent_playbook.packs.*`, layered exactly like overlay packages but shipped in the engine wheel (no extra install), off by default, and enabled by listing the dotted package name in the top-level `overlays_enabled` key. It documents the two configuration mistakes the pack invites and how each is now caught (see the config-hardening bullet): the `[overlays]`/`[adapters]` table form is refused with a `ConfigError`, and a misspelled pack name is flagged by `sync`, `validate`, `check` and `init`. "Opting out and overriding" applies §4.2 step 9 to a pack: removing it, or overriding one of its skills with fewer `scripts/`/`references/` files, deletes the pristine, untracked pack files from every skill root on the next sync and prunes the emptied directories; edited, tracked, and user-added skill files are kept; the degraded Continue prompts are removed by `cleanup_stale`, edited or not, tracked or not.
- **Section 11.5.1 (new)**: the `superpowers` pack: 15 skills ported near-verbatim from the Superpowers skills library (v7.0.0, MIT), the self-containment transformations, what was dropped and why, the per-adapter rendering (`.claude/skills/`, `.opencode/skills/`, `shared_skills/` byte-identical via the `SkillWriter`, `SKILL.md` with the sentinel as its first body line; Continue degrades to prompts; `agent_harness` `skills/<id>/`), the executing-plans → subagent-driven-development sibling-script dependency (an override of `subagent-driven-development` must ship the two scripts executing-plans calls), and the MIT attribution (`LICENSE` + `ATTRIBUTIONS.md`, plus a `references/LICENSE` copy in every skill so the notice travels with each synced skill directory).
- **Sections 5.1 / 6.3**: `packs/` added to the engine layout. The engine's default `resources/` held no skills at the time (core gained its own in v0.21); the only bundled skills lived in the opt-in pack. Section 6.3.2 now notes that only its step 1 (render as a prompt) is implemented.
- **Config hardening (same release; Sections 4.2, 7.1, 7.2, 10.7, 10.8, 11.1, 11.5, 12.1–12.6)**: `Config` read only the top-level `overlays_enabled`/`adapters_enabled` keys, while the SPEC and README showed an `[overlays] enabled` / `[adapters] enabled` table form that parsed as two empty lists — `playbook sync` exited 0, rendered only `AGENTS.md`, and settled every other adapter's earlier output as leftovers ("1 files written, 278 removed" in a repo synced with the pack); a string value became a list of characters. **Behaviour change:** the new `config.ConfigError` (a `ValueError`) refuses an `overlays`/`adapters` key of any shape (table, dotted key, plain value), an `overlays_enabled`/`adapters_enabled` key inside any table at any depth (TOML nests a key written after a `[table]` header there — so applying the fix-it hint in place, or appending the key to an init-written file that ends with `[detector_cache.frameworks]` or a local file that is `[user_choices]` only, would still be ignored), a nested `overlays`/`adapters` table holding `enabled`, a close misspelling of either key (`difflib`, case- and separator-insensitive), and any `*_enabled` value that is not a list of non-empty strings (an empty name used to crash in `importlib`), with a message that names the file (and table), quotes the value and shows the top-level line to write instead, "at the top of the file, above the first [table] header". One helper, `config.check_enabled_keys`, walks every table of each of `.coding-agent-playbook.toml` and `.coding-agent-playbook.local.toml` before the §7.2 merge (`FileSystemStateSource.load_config`; `load_local_overrides` lets `init` check the local file up front) and again in `Config.from_dict` for other callers. `parse_output_config` raises `ConfigError` too. `cli.main` maps `ConfigError` like a missing config — `error: <message>`, exit 2 — and every command that loads the config does so before writing or deleting anything (`sync` in every mode, `--check-staged` under `commit = true` included; `check` incl. `--refresh`; `validate`; `render`; `eval`; `init`). Unusable overlays: `_sync_preflight.missing_overlays` became `unusable_overlays`, which also refuses an importable package with no `resources/` directory (it would contribute nothing, e.g. the parent `coding_agent_playbook.packs`), so every sync mode refuses it too. It now imports each overlay (`find_spec` alone passed a package that raises at import time, and a dotted name whose parent raised escaped as a traceback): any import failure is a reason, quoting the error unless it only says the package does not exist; a `ModuleNotFoundError` for an overlay's own dependency is named as such. `sources.filesystem._resource_subdir` correspondingly skips a package whose import raises, like a missing one, so discovery never crashes before the check can report it. The check is shared by `validate` (a `FAIL overlays_enabled: <name>: <reason>` validation error, exit 1), `check` (a `✗` line under `Overlays:` and no clean Drift claim; still exit 0 as a diagnostic) and `init` (exit 2, nothing written; it checks `--overlays`, or the local file's `overlays_enabled` when that replaces it), each reporting every unusable overlay on its own line. A pack-like typo lists the bundled packs (`_sync_preflight.bundled_packs`, via `pkgutil`). Docs: every config example now uses the top-level keys (`.local.toml` overrides replace lists), and §7.1 shows the `[detector_cache]` table the code reads and writes (was `[detector.cache]`).
- **Tooling**: `[tool.ruff] extend-exclude = ["src/coding_agent_playbook/packs/*/resources"]` keeps vendored text byte-faithful, because newer unpinned ruff also formats code blocks inside markdown.
- **CI**: `tests/packs/` (identity, opt-in, per-skill layout, `references/` inventory + license copies, self-containment incl. path-mention resolution, executable scripts + `bash -n`, end-to-end opt-in sync/validate/`sync --check` with the `SKILL.md` sentinel body line, byte-identical `.claude/skills/`/`.opencode/skills/`/`shared_skills/` copies and the Continue prompts' sentinel line + vendored body, an opt-in `agent_harness` sync (`skills/<id>/` copies, script flags in `.playbook/manifest.toml`, removal on opt-out), opt-out removal from every skill root that keeps a consumer-added and an edited file, SKILL.md-only and fewer-references override removal, the mutating cases in hermetic real git repos) and `tests/cli/test_validate_links.py::test_superpowers_pack_has_self_contained_links` (the PR-L link gate over the pack). Config hardening: `tests/unit/test_config_enabled_keys.py` (each table in each file, both tables, dotted keys, an enabled key nested under `[engine]`/`[output]`/`[project]`/`[detector_cache.frameworks]` and under the local `[user_choices]`, misspelled keys, empty names, non-list and non-string values, framework names that resemble the legacy names, valid configs and the `to_dict`/`from_dict` round trip unchanged), `tests/unit/test_sync_preflight.py` (unimportable vs. no-`resources/` overlays, packages raising at import or whose parent raises, a missing dependency, `pkgutil` pack discovery of subpackages only, the pack-typo hint), `tests/cli/test_config_errors.py` (every config-loading command exits 2 with the tree byte-identical — for the table form, the hint applied in place, keys appended after the last table, a misspelled key and an empty name — `--check-staged` under `commit = true`, the local-file case, `init`, and the safety test: a repo synced with the pack, then switched to any of those shapes in the committed or the local file, is left byte-identical — lockfile and `.gitignore` included — by every sync mode, in a hermetic real git repo) and `tests/cli/test_unusable_overlays.py` (`validate`/`check`/`init` with a misspelled pack, the parent `coding_agent_playbook.packs`, an unrelated name, packages raising at import and several at once, one line each; `init` checking the local file's list; every sync mode refusing a package with no `resources/` or one that raises at import).
### v0.16 (2026-10-14)
Generated output is **local-only** in consumer repos by default. Rendered files are build products of the installed engine + overlays + `playbook/`, so they are gitignored and regenerated on each machine instead of being committed. Behaviour change for consumers: new repos (and repos without an `[output]` table) stop committing output; `[output] commit = true` restores the pre-v0.16 committed-output policy.
- **Section 7.1 (config)**: new `[output]` table — `commit` (bool, default `false`), parsed by `config.parse_output_config` into `config.OutputConfig`; a non-bool is a `ValueError` carrying the value. `Config.output` is `None` when the table is absent (sparse round-trip) and `Config.commit_output` is the effective value. `playbook init` writes `commit = false` explicitly and preserves an existing value.
- **Sections 4.2 / 5.3 (data flow, consumer layout)**: new step 9 — the output policy. `commit = false`: an engine-owned managed block in the consumer's `.gitignore` lists every generated file root-anchored and escaped (skill directories — any directory holding a written `SKILL.md` — collapse to `/<dir>/`), plus the lockfile. Byte-preserving (CRLF, missing final newline), atomic, idempotent; malformed markers fail with file + line. `.gitignore` is never in the lockfile. `commit = true`: the block is removed. Leftover settling (below) runs under **both** settings.
- **Sections 12.2 / 12.3 / 12.3.1 (sync)**: write mode applies/removes the block and, under `commit = false`, warns on stderr about generated paths git still tracks with the exact `git rm -r --cached -- …` (read-only `git ls-files`, 10 s timeout, silent when git cannot answer; exit code unchanged). `--check` also reports a stale/missing/malformed block as drift. New `--check-staged` (mutually exclusive with `--check`) fails when a staged path is generated output; no-op under `commit = true` or outside a git repo.
- **Section 13 (pre-commit)**: new consumer hooks `playbook-sync` (`post-checkout`/`post-merge` auto-sync) and `playbook-no-generated-output` (pre-commit guard), both `minimum_pre_commit_version: "3.2.0"`; `playbook-sync-check` is kept as the legacy `commit = true` hook. The `playbook init` starter renders per policy and, for `commit = false`, adds `default_install_hook_types: [pre-commit, post-checkout, post-merge]` and `default_stages: [pre-commit]`.
- **Review hardening (same release)**: leftovers of an earlier sync (a removed skill's `SKILL.md`/scripts, a disabled adapter's output) are owned through the previous lockfile — pristine untracked ones deleted, the rest carried forward (and, under `commit = false`, kept in the managed block), and always caught by `--check-staged` (§4.2 step 9). Under `commit = true` the same settling runs and kept leftovers are listed on stderr (`_sync_output.report_kept_leftovers`): **behaviour change from v0.15** — a removed skill's committed (tracked) files are no longer deleted; they stay until the user runs `git rm`. This is the **single deletion policy for skill dirs**: adapters' `cleanup_stale` never deletes inside one (`agent_harness` `skills/<id>/` included), a file absent from the previous lockfile is never deleted, a skill-dir file/folder swap displaces only what the policy would delete, and the pre-v0.15 lockfile claim needs unchanged `SKILL.md` bytes. Bounds: deletion only inside installed adapters' declared `Adapter.output_locations` (§10.1), never under `.git/` or through a symlink; pruning never above a declared directory or into a symlinked root's target; a skills root that is a dangling symlink is skipped with a warning. The tracked check asks `:(literal,icase)` pathspecs, matches in NFC or by file identity, and keeps everything when git cannot answer inside a work tree. Stale-vs-written comparisons use file identity; `--check`/`--check-staged` decide skill ownership on the real tree (`deciding_ownership_against`), `HARNESS.md` indexes only what it emits, and `--check` names the blocker of a refused swap (the one documented exception to "`--check` exits 0 after a successful sync", §12.3). `--check`/`--check-staged` render into an empty scratch dir (no working-tree copy: dangling symlinks, unreadable dirs, FIFOs and big venvs no longer crash or slow the guard) and map paths back through the repo's own symlinks, so they agree with write mode. Every `sync` mode refuses to run when an `overlays_enabled` package is not importable; a missing adapter is a warning. Entries are NFC-normalised (plus the as-written form); a BOM before a first-line block is tolerated and preserved; the atomic write uses a unique temp name. The `git rm -r --cached` hint gains `git -C <repo-root>` when run from elsewhere. `init` swaps a verbatim pre-v0.16 `coding-agent-playbook-sync` hook for the new pair, warns about a hand-edited one, and notes a missing `default_stages`. Docs: §12.3 limits CI use of `--check` to `commit = true`; §13.1 documents `additional_dependencies`/`rev` for the remote hooks (or the init `language: system` hooks); §12.1/A.3 say init prints (not runs) `pre-commit install`; §14.2/§14.3/A.6 drop the "review the regenerated diff" assumption under `commit = false`.
- **Adapter cleanup contract + secret hygiene (PR K Track P review)**: `Adapter.stale_outputs` is the read-only override point and `cleanup_stale` deletes exactly what it reports (§10.1; an adapter overriding only `cleanup_stale` is warned about and skipped by `--check`, see MIGRATION.md). The orphan scan opens each file once (aliased output dirs no longer crash `sync`), never a symlink or a secret path, and reads a bounded head; `--check` reports orphans reached through an output dir symlinked outside the repo (§12.3). Skill copies refuse secret paths and links leaving the skill's source dir (§10.8, §17.3; `playbook validate` warns). A `rule()`-inlined rule rejected by the sandbox makes `playbook eval --run` exit 2, not 1 (§12.8). Runtime floor `jinja2>=3.1.6` (§9.3).
- **Implementation**: `gitignore.py` (stdlib-only entries + managed block), `git_client.py` (`GitClient` protocol + `SubprocessGitClient`), `commands/_sync_output.py` (policy glue), `commands/_sync_orphans.py` (lockfile-based ownership of leftovers: `LeftoverPolicy`), `commands/_output_locations.py` (deletion allowlist + prune bounds), `_file_identity.py` (`FileSet`), `adapters/skill_dirs/ownership.py` (the previous lockfile as proof + the installed leftover judge), `commands/_sync_preflight.py` (overlay/adapter availability), `commands/_precommit_merge.py` (existing-config merge + legacy swap), `commands/sync.py` (`--check-staged`, empty-scratch render shared with `--check`), `cli.py`, `commands/init.py`, `resources/precommit/config.yaml.j2`, `.pre-commit-hooks.yaml`, with tests (`tests/fakes.py::FakeGitClient` instead of patching `subprocess`; `tests/conftest.py::apply_hermetic_git_env` drops inherited `GIT_*` and the default global excludes).
### v0.15 (2026-10-14)
Native skills for every Agent-Skills harness plus the cross-agent `shared_skills/` hub, and two skill-output bug fixes. Additive for authors — the canonical skill format is unchanged.
- **Section 10.8 (NEW)**: the `shared_skills` adapter (`shared_skills/<id>/`, on by default, not force-enabled; rules/prompts are no-ops) and the shared `SkillWriter` (`adapters/skill_dirs/writer.py`) — the single source of truth for a native skill directory, byte-identical across roots, path-safe, with the sentinel marking a skill dir as engine-owned. (v0.15 shipped a per-directory `SkillWriter` cleanup; **since v0.16** there is none — stale skill output is settled only by the §4.2 step 9 lockfile leftover policy.)
- **Sections 10.3 / 10.6 / 10.6.4**: `claude_code` and `opencode` delegate `write_skill` to the `SkillWriter`; OpenCode now writes `.opencode/skills/` natively instead of relying on `.claude/skills/` (duplicate discovery is safe: OpenCode keys skills by name, last wins).
- **Section 6.3 (bug fixes)**: emitted `SKILL.md` sets `name` = the skill id (= directory name), as the Agent Skills standard requires — previously the authored display name was copied verbatim and OpenCode dropped the skill. `SKILL.md` now carries the sentinel as its first body line, so a skill directory is recognisably engine-owned (previously skill output was never cleaned); user-authored skill dirs (no sentinel) are never touched. Since v0.16 a deleted skill's output is settled only by the §4.2 step 9 lockfile leftover policy: pristine, untracked, lockfile-listed files are deleted; edited and user-added files are kept.
- **Section 12.6 (`playbook validate`)**: new rule flagging skill ids that break `^[a-z0-9]+(-[a-z0-9]+)*$` / 64 chars, skills without a 1–1024 char `description`, and every skill with no (or a non-string) `id` — id-less skills all merge under `skill`, so they are checked from the pre-merge list.
- **Section 10.8 (cleanup safety)**: ownership is decided before writing (a colliding hand-written skill dir is skipped with a warning, never overwritten; pre-v0.15 output is re-claimed via the lockfile); stale-vs-written decisions compare file identity, not path spelling (the identity comparison now lives in `_file_identity.FileSet`, used by the leftover policy and `Adapter._default_cleanup`); case-only id renames, file↔folder flips in `scripts/`/`references/`, and read-only copies from an earlier sync no longer delete fresh output or crash `sync` / `sync --check`.
- **Sections 2.2 / 3 / 4 / 5.1 / 5.3 / 7.1 / 12.1**: skills are no longer described as Claude-Code-only; the consumer layout gains `.claude/skills/`, `.opencode/skills/` and `shared_skills/`; `shared_skills` joins the default adapter list.
- **Implementation**: `adapters/skill_dirs/writer.py`, `adapters/shared_skills.py` (+ the `shared_skills` entry point), `commands/init.py` default adapters, `commands/validate.py::_check_agent_skills`, with tests (`tests/adapters/test_skill_writer.py`, `tests/adapters/test_shared_skills.py`, `tests/cli/test_sync_skills.py`).
### v0.14 (2026-07-14)
Self-contained markdown links in canonical artifacts (PR L). A deterministic, CI-enforced rule: every markdown link in every artifact must stay inside the shipped bundle. Purely additive — no rendering changes, no new dependency. Authoritative design: `specs/prL-markdown-links.md`.
- **Section 12.6 (`playbook validate`)**: new rule — links extracted from rule/prompt/skill bodies (plus skill `references/*.md`), after masking frontmatter, fenced code blocks, and inline code spans. Relative targets must resolve inside the artifact's source layer (package `resources/` or repo-local `playbook/`; `.j2`-suffixed sources satisfy their rendered names); absolute paths, `..`-escapes, and non-`http(s)` schemes are violations; `http(s)` hosts pass only via the allowlist. Jinja-bearing targets are skipped.
- **Section 7.1 (config)**: new `[links]` table — `allowed_domains` (list of hostnames, subdomains included; default `[]` = fully strict), parsed by `config.parse_links_config`.
- **CI**: the engine's own shipped artifacts are gated by `tests/cli/test_validate_links.py::test_shipped_engine_artifacts_have_self_contained_links` under the existing `pytest` step (a bare `playbook validate` step needs a consumer config, which the engine repo has none of).
- **Implementation**: `links.py` (`MarkdownLink`, `LinksConfig`, `extract_markdown_links`, `classify_link`; stdlib-only), `config.parse_links_config`, `commands/validate.py::_check_markdown_links`, with tests.
### v0.13 (2026-06-29)
Eval **task-config redesign** ("2b refined", Tracks C1–C8): the `[expected]`/`[metrics]`/`[rubric]` triple is replaced by a layered, expression-composed task config. This is a **destructive cutover** of the *authored* task format (no backward compat); the `Metric`/`Check`/`Rubric` engine (v0.12) is reused underneath. Authoritative design: `specs/pr2b-task-config.md`.
- **Sections 6.5.3 / 15.2 (task schema)**: a task now declares up to four layer blocks sharing one `[<layer>.bind]` + `[<layer>].expr` shape — `[gate]` (deterministic boolean), `[rubric]` (llm-judge weighted), `[verdict]` (boolean expr over the two), and an optional `[aggregate]` (cross-trial `pass@k`/`pass^k`). **There is no `[expected]` block** — file predicates are gate `check`s. `ExpectedOutcome`/`Rubric`(`criteria`/`weights`) dataclasses are deleted; `EvalTask` carries `gate`/`rubric`/`verdict`/`aggregate` `Layer`s.
- **0–1 normalization**: every `Metric` owns a `Normalizer` (`evaluators/normalizer.py`: `RampNormalizer`/`PercentNormalizer`/`Identity`) folding the metric's native direction into a 0–1 goodness (higher = better). `higher_is_worse` is **deleted**; `warn`/`fail`/`max_worsening` are 0–1 cutoffs on the normalized score.
- **A check is `(type) × (metric|judge) × kwargs`**: `check = "threshold"|"non_regression"` over a registered `metric=` **or** a `judge=` criterion (a `JudgeMetric` — an llm-judge criterion *is* a metric, normalized `Identity`). Non-regression works on any metric including judged.
- **Registries**: checks via `@register_check` + `coding_agent_playbook.checks`; gates via `@register_gate` + the new **`coding_agent_playbook.gates`**; rubrics via `@register_rubric` + `coding_agent_playbook.rubrics`. A handle `{ref="name"}` resolves a registered composed **gate** (gate layer) or **rubric** (rubric layer).
- **Expression DSL + derived verdict**: `[<layer>].expr` and `[verdict].trial` are tiny boolean expressions (`and`/`or`/`not`/parens) over handle names (`evals/_expr.py` → `compose.py` tree). The verdict is **derived** from the already-run gate/rubric layer results (a skipped layer is neutral), so the judge / test-suite is never double-invoked.
- **Aggregate / pass@k**: `[aggregate]` is the same bind+expr shape over `pass_at_k`/`pass_pow_k` (`k`, `over ∈ {gate,rubric,verdict}`, 0–1 `warn`/`fail`); the runner runs `N=max(k)` trials and the aggregate composes them into a reliability score. Omit ⇒ single trial.
- **Implementation**: `evaluators/{normalizer,gates,rubrics}.py`, `evaluators/checks/{registry,judge_metric,aggregate}.py`, and `evals/{_expr,_handles,_compile}.py` (the expression DSL, handle Factory+Composite, and task compiler), with the parser/validator/scoring/runner cut over and all 10 authored tasks migrated. `rubric_for_task`/`ExpectedOutcome`/`higher_is_worse` are removed. Out-of-tree migration: `MIGRATION.md`.
### v0.12 (2026-06-28)
Evaluator subsystem refactored to the `Metric`/`Check`/`Rubric` model (PR R6 — clean-slate). The fused `Evaluator` ABC + free `grade()` are replaced by three single-responsibility abstractions; a cost-tiered scheduler short-circuits so a failing deterministic check never invokes the LLM judge. The authored `[expected]`/`[metrics]`/`[rubric]` task TOML is **unchanged** — zero authoring migration; only the engine internals and the out-of-tree extension surface change.
- **Section 21 (rewritten 21.1–21.8)**: `Metric` (measure) / `Check` (grade — a boolean gate + optional partial-credit score) / `Rubric` (aggregate — gate + weighted composite). A `Rubric` is also a `Metric` (Composite — it surfaces its composite via `measure()`, so checks compose + nest). Builtins: static metrics + execution `coverage`/`test_pass_rate`; checks: `ThresholdCheck`/`NonRegressionCheck`, `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden`, `JudgeCheck`, `TestsPassCheck`/`CoverageCheck`, and the boolean composers `AllOf`/`AnyOf`/`Not`. The cost-tiered (`CostTier` DETERMINISTIC < EXECUTION < JUDGED) scheduler with short-circuit + optional concurrency (21.4). Entry-point groups renamed/split: metrics under `coding_agent_playbook.metrics` (was `…​.evaluators`), custom grader checks under the new `coding_agent_playbook.checks` (21.3). `grade()`/`value_kind`/`to_score`/`default_*`/`extra_evaluators`/`JudgedCriterion`/`evaluators_for_task`/the `Evaluator` ABC are **deleted** (21.7).
- **Sections 15.3 / 15.3.1**: the scoring bridge builds one `Rubric` via `rubric_for_task` and runs `Rubric.evaluate`; `score(...)` gains `fail_fast` (the runner default; `--full-scoring` flips it off so every check runs). The `[metrics]`/`[rubric]`/`[expected]` blocks compile into one ordered check list → one `EvaluationReport`.
- **Implementation**: `evaluators/{metric,check,rubric,scheduler,policy}.py` + `evaluators/checks/{files,judged,execution,compose}.py`; consumers `evals/scoring.py`, `evals/task.py::rubric_for_task`, `commands/metrics.py`. Authoritative design `specs/prR6-check-rubric.md`; out-of-tree migration `MIGRATION.md`.
### v0.11 (2026-06-28)
Judged `[rubric]` scoring activated, the `[expected]` family unified, and a second real runner added (PR R2 Track J + R3 Tracks E/O). The judge is live: the deterministic-only behaviour of R1 is preserved as the default (no judge configured), and passing `--judge llm` folds the rubric scores into the same report. The v1 public surface (`Evaluator`/`grade`/`evaluators_for_task` API and the `[metrics]`/`[rubric]`/`[expected]` task schema) is unchanged — only the eval result/scoring internals evolve, the sanctioned v1.1-activation revision.
- **Section 15.1 (Tier ladder)**: Tier 2 (rubric judging) marked **shipped (v1.1 R2)** — opt-in `LLMJudge` via `--judge llm`; calibration remains future work.
- **Section 15.3 (runner)**: `run_task(task, scratch, *, judge=None, samples=1)` documented as taking an optional judge threaded onto the `EvalContext` (with a judge, the `[rubric]` criteria score against the captured diff and fold into the same report; with none — the default — judged evaluators report `available() is False` and the report is deterministic-only). **`OpenCodeRunner`** (`name="opencode"`, `evals/opencode_runner.py`) added to the runners list as a second thin, opt-in real runner (default `opencode run <prompt>` with `cwd=scratch_dir`, `available()`-gated on the `opencode` binary, never in CI); `ContinueCLIRunner` is the only remaining future runner.
- **Section 15.3.1 (scoring bridge)**: the `[expected]` checks are now **real BOOL `Evaluator`s** (`evaluators/expected.py`: `FileExists`/`FileContains`/`FileUnchanged`/`FileForbidden`) compiled by `evaluators_for_task` and graded through the **same `grade(…, extra_evaluators=…)` call** as `[metrics]` and the judged `[rubric]` criteria — one model, one `EvaluationReport`. The R1 interim that compiled `[expected]` into BOOL findings outside `grade()` is removed. The `[rubric]` pass is included only when `judge is not None`; "deterministic-only" is **simply no judge configured** (`ctx.judge is None`), there is no `ProgrammaticOnlyJudge`.
- **Section 15.4**: `judge.py` documented as **live** — the `Judge` ABC's canonical per-criterion primitive `score_criterion(criterion, artifact, n=1) -> float` (Option A; batch `score()` wraps it), the opt-in `LLMJudge`, and the test-only `StubJudge`. The `JudgeLike` protocol lives in `evaluators/types.py` so `evaluators` never imports `evals`.
- **Section 12.8 (`playbook eval`)**: `playbook eval <id> --run` gains **`--judge NAME`** (default: no judge ⇒ deterministic-only) and **`--samples N`** (default 1, the per-criterion sample count the judge averages); exit `2` now also covers an unknown/unavailable `--judge`.
- **Section 21.2.3 / 21.8**: the forward-compat `Judge.score` signature debt is **closed** — `JudgedCriterion` calls `score_criterion` through the structural `JudgeLike` protocol.
- **`pyproject.toml`**: the `coding_agent_playbook.runners` group gains `opencode`; the `coding_agent_playbook.judges` group is populated with `llm`.
- **Implementation**: `evals/judge.py` (`Judge` ABC + `LLMJudge` + `StubJudge`), `evaluators/expected.py` (the four BOOL evaluators), `evaluators/types.py` (`JudgeLike` protocol + `EvalContext.judge`/`tree`/`baseline_tree`), `evals/opencode_runner.py`, and the unified `evaluators_for_task`/`evals/scoring.py`/`commands/eval.py` wiring, with tests. See `specs/prR2-judge-r3-opencode.md` and the roadmap `specs/v1.1-eval-execution.md`.

### v0.10 (2026-06-28)
Eval runner activated (PR R1). The former v2 placeholder is now a live, hermetic-by-default runner that executes one task end-to-end and scores it through the unified PR-M `Evaluator`/`grade()` model. The deterministic layers (`[expected]` file checks + `[metrics]` static/execution non-regression) are computable today; judged `[rubric]` scoring stays deferred to R2. The v1 public surface (the `Evaluator`/`grade`/`evaluators_for_task` API and the `[metrics]`/`[rubric]`/`[expected]` task schema) is unchanged — only the eval *result* types evolve, which is the sanctioned v2-activation revision.
- **Section 15 (rewritten 15.1 / 15.3 / 15.4)**: the Tier ladder now marks Tier 1's deterministic layers **shipped (v1.1 R1)**. `HarnessRunner` documented as a concrete **template method** (`run_task` = materialize → `render_prompt` → `_invoke_agent` → `capture` → `score`; `_invoke_agent` the only per-assistant hook) with `render_prompt` strictness (`requires_resolved_prompt` ⇒ `PromptResolutionError` for real runners). Result model evolved to **Option B** — `TaskResult.report: EvaluationReport` (+ `passed`/`aggregate_score`/`duration_seconds`/`transcript`); `programmatic_checks`/`rubric_scores`/`CheckResult` retired; `EvalReport.pass_rate` = mean of `tr.passed`. Concrete runners: hermetic `FakeRunner` (`name="fake"`, default test driver, no-op default mutation) + opt-in `ClaudeCodeRunner` (`name="claude_code"`, lazy, `available()`-gated on the `claude` CLI, never in CI), via the `coding_agent_playbook.runners` group. New 15.3.1 documents the `evals/scoring.py` bridge ([metrics] via `evaluators_for_task` + non-regression vs the pristine `setup/` snapshot; `[expected]` compiled to BOOL findings — the R1 interim, full compile is R3).
- **Section 12.8 (`playbook eval`)**: documents `playbook eval <id> --run [--runner fake|claude_code] [--format text|json]` — default runner `claude_code`, **no `--run-tests`** (execution intent lives in the task's `[metrics]` block), exit `0` pass / `1` fail / `2` usage or runner-unavailable. The bare `playbook eval <id>` (no `--run`) deferral path is unchanged.
- **`pyproject.toml`**: the `coding_agent_playbook.runners` entry-point group is now populated (`fake`, `claude_code`); the `coding_agent_playbook.judges` group stays reserved for the R2 judge.
- **Implementation**: `evals/runner.py` (template + result types + orchestration helpers `materialize`/`render_prompt`/`capture` + `PromptResolutionError`), `evals/scoring.py`, `evals/fake_runner.py`, `evals/claude_code_runner.py`, and the `--run` path in `commands/eval.py`, with tests. See `specs/prR-eval-runner.md` (tracks R1a–R1e) and the roadmap `specs/v1.1-eval-execution.md`.

### v0.9 (2026-06-27)
Code-quality evaluator subsystem added (PR M). A single `Evaluator` abstraction unifies static metrics, execution metrics, and judged criteria; a standalone `playbook metrics` gate + static pre-commit hook ship now; eval `[metrics]` wiring is parsed/validated but dormant until v1.1. Purely additive — no new hard dependency, no edits to the sync pipeline, and the v2 eval ABCs (§15) stay inert.
- **Section 21 (NEW)**: the evaluator subsystem. The `Evaluator` ABC + `Scope`/`ValueKind`/`Determinism` axes (21.1); the three families — static (CC/WMC/LCOM4/DIT/CBO≈ via `ast`, MI via the optional `radon` extra), execution (`test_pass_rate`/`coverage`, shelling out to the target's `pytest` and parsing junit/coverage XML with stdlib), and judged (`JudgedCriterion`, dormant) — with per-evaluator default tables (21.2); the `@register_evaluator` decorator + `coding_agent_playbook.evaluators` entry-point group + `static/deterministic_evaluators()` selection (21.3); `grade()` gate + weighted composite with the inclusive/strict gate-boundary semantics and the non-regression comparator (21.4); the `playbook metrics` command, flags, exit codes, `[metrics]` config, and the `repo: local` static pre-commit hook (21.5); the eval `[metrics]` block (sibling of `[rubric]`), `EvalTask.metrics`, `evaluators_for_task`, and validator rule 7 (21.6); invariants (21.7) and open caveats incl. the forward-compat `Judge.score` signature mismatch (21.2.3 / 21.8).
- **Section 15 (eval)**: the eval-task schema gains a top-level `[metrics]` block parsed into `EvalTask.metrics`; validated in v1, executed by the v1.1 runner via `evaluators_for_task` against the same registry + `grade()`. The `[expected]` → bool-evaluator compilation is deferred.
- **`pyproject.toml`**: new `[project.optional-dependencies] metrics = ["radon>=6.0"]` extra (backs `maintainability_index` only; lazy-imported) and the `coding_agent_playbook.evaluators` entry-point group (empty in-tree; for third-party evaluators).
- **Implementation**: `evaluators/` package (`registry`, `types`, `scope`, `parse`, `grade`, `judged`, `builtins/*`, `execution/*`) + `commands/metrics.py` + `config.parse_metrics_config` + the `playbook-metrics` hook in `.pre-commit-hooks.yaml`, with tests. See `specs/prM-code-metrics.md` (tracks M1–M6).

### v0.8 (2026-06-26)
Agent Harness round-trip support added (the [agentharnesses.io](https://agentharnesses.io/specification) format) as a fifth, opt-in output target plus a reverse importer and a structural validator. Authoring and the existing four adapters are unchanged; the new surface is purely additive (no edits to `types.py`, `renderer.py`, or `orchestrator.py`).
- **Section 10.7 (NEW)**: the `agent_harness` output adapter. Renders canonical `Rule`/`Prompt`/`Skill` into a `HARNESS.md`-rooted tree (`skills/`, `prompts/`, `rules/`, `references/`, `.leaf-detectors`, `.playbook/`). Opt-in via `adapters_enabled`. Eval tasks are not emitted (no eval hook on the adapter ABC). Documents the sentinel-as-first-body-line nuance (frontmatter must be line 1) and the custom `cleanup_stale`.
- **Sections 12.9 / 12.10 (NEW)**: `playbook import-harness <path> [--into]` (harness → canonical, lossless via the sidecar / best-effort otherwise) and `playbook validate-harness <path> [--strict]` (`harnesses-ref`-equivalent structural checks).
- **Sections 20.10 / 20.11 (NEW)**: the `.playbook/manifest.toml` sidecar — full canonical reconstruction payload (rule `name`, un-rendered source body, `is_templated`, per-script `executable` flag) enabling lossless round-trip; and a future-work note that the harness client runtime (`load_content`/`run_script`) is intentionally out of scope.
- **Implementation**: `harness/` core module (`models`, `leaf_detectors`, `parser`, `emitter`, `manifest`) + the adapter, two CLI commands, and tests. See `specs/prH-agent-harness.md`.

### v0.7 (2026-05-20)
Canonical types formalized. Authoring stays markdown; internal pipeline becomes typed end-to-end; alternative deployments (commercial, hosted) get a stable interchange format.
- **Section 5.1 (engine layout)**: Added `types.py` at the package root containing the `Rule`, `Prompt`, `Skill` dataclasses. Added `test_types.py` to unit tests.
- **Section 6.6 (NEW)**: Canonical types and serialization. Explicitly separates the *authoring format* (markdown + YAML frontmatter, what humans write) from the *canonical internal format* (typed dataclasses, what the engine operates on). Defines `RuleFrontmatter` / `Rule` / `PromptFrontmatter` / `Prompt` / `Skill` with full field lists. Specifies the lossless round-trip contract (`Rule.from_markdown` ↔ `Rule.to_markdown`, `Rule.to_dict` ↔ `Rule.from_dict`). Documents what is deliberately absent from the canonical type (no harness-specific rendering, no source-specific data, no render context). Includes a "contract for alternative deployments" subsection that protects compatibility between the OSS engine and a future commercial product.
- **Implementation order**: Added Track 1b (PR 2) for the canonical types with markdown round-trip. Lands second because almost every subsequent module imports from `types.py`. Total LoC bumped to ~3900.
### v0.6 (2026-05-20)
Storage abstraction added. Engine still ships filesystem-only in v1; the seam exists so future deployments can swap in alternative artifact/state backends without modifying engine code.
- **Section 4.2 (data flow)**: Steps 1 and 3 now reference `StateSource` and `ArtifactSource` instead of hardcoded filesystem walks. Behavior unchanged in v1; framing reflects the abstraction.
- **Section 5.1 (engine layout)**: Added `sources/` package with `base.py` (ABCs) and `filesystem.py` (v1 implementations). Added `test_sources.py` to unit tests.
- **Section 7.1 (config example)**: Added `[storage]` block with `artifact_source = "filesystem"` and `state_source = "filesystem"` defaults. Configs without this block default to filesystem, so existing configs need no changes.
- **Section 20 (NEW)**: Storage sources. Defines `ArtifactSource` and `StateSource` ABCs as public API from v1. Lists the v1 filesystem implementations as the only concrete sources shipped. Documents entry-point discovery, the `[storage]` config block, and what the seam enables later (registry sources, database state, in-memory test sources) — none of which ship in v1. Includes an explicit "what v1 promises and does not promise" subsection.
- **Implementation order**: Added Track 2c (PR 4) for the filesystem source implementations. Track 1 (PR 1) now also adds the source ABCs alongside the adapter ABC. Total LoC bumped to ~3650.
### v0.5 (2026-05-20)
Eval Tier 0 added: prompts can declare eval tasks, tasks are validated, but no runner ships in v1.
- **Section 2.1 (G6)**: Rewrote eval goal to be specific about Tier 0 — schema + validator + read-only CLI, no runner.
- **Section 2.2 / 2.3**: Non-goals now distinguish "no eval runner" (Tier 1) from "no LLM-as-judge" (Tier 2). v2 aspirations split the eval work into two milestones.
- **Section 3 (glossary)**: Added "Eval task" entry.
- **Section 4.2 (data flow)**: Added explicit note that eval tasks are authoring-side artifacts and not part of `playbook sync`.
- **Section 5.1 (engine layout)**: Added `resources/eval_tasks/` tree with three example tasks. Updated `evals/` package to split active modules (`task.py`, `loader.py`, `validator.py`) from v2 placeholders (`runner.py`, `judge.py`). Added `test_eval_tasks.py` to unit tests.
- **Section 6.2.1 (prompt frontmatter)**: Added optional `eval_tasks:` field.
- **Section 6.5 (NEW)**: Eval tasks — Tier 0 design. Directory layout, `task.toml` schema (setup / invocation / expected / rubric), authoring discipline, validation rules, Tier 0/1/2 capability table.
- **Section 12.6 (`playbook validate`)**: Added two new validation rules — `eval_tasks:` references resolve, and task `prompt_id` back-references are consistent.
- **Section 12.8 (NEW)**: `playbook eval --list` enumerates the prompt-to-task graph; `playbook eval --show <task>` displays a single task; `playbook eval <task>` prints a deferred-implementation message (exit 0).
- **Section 15**: Complete rewrite. Now structured as Tier 0 (v1, active) / Tier 1 (v1.1) / Tier 2 (v2). Active dataclasses (`EvalTask`, `TaskSetup`, `TaskInvocation`, `ExpectedOutcome`, `Rubric`) replace the old `GoldenTask`. Added `HarnessRunner` and `Judge` ABCs as v2 placeholders. Added concrete examples of v2 runners (`ClaudeCodeRunner`, `ContinueCLIRunner`, `OpenCodeRunner`).
- **Section 19**: Added open questions Q10 (HarnessRunner invocation contract), Q11 (determinism / seeding), Q12 (rubric calibration).
- **Implementation order**: Added PR 9 (Track 5b, Eval Tier 0, ~250 LoC). PR 11 (initial content pack) now also ships 8 eval tasks alongside the rules and prompts. Total LoC and timeline bumped slightly.
### v0.4 (2026-05-20)
Consistency audit — no new design decisions, only reconciliation of drift introduced by previous additions.
- **Section 4.1 (component diagram)**: Added `opencode` adapter and `.opencode/command/*.md` to the consumer repo. Resources block now shows `*.md|*.md.j2` (consistent with Section 6.0) instead of uniform `*.md.j2`.
- **Section 6.1.1 (rule frontmatter)**: Removed unused `invokable` scope value (rules have `always | scoped`; only prompts are invokable, via their own frontmatter).
- **Section 6.2.1 (prompt frontmatter)**: `slash:` comment now mentions OpenCode alongside Continue & Claude Code.
- **Section 6.4 (applies_if)**: Added explanatory note disambiguating `has_framework` as both an `applies_if` predicate key (list-of-strings) and a Jinja context callable (single-string). Same conceptual question, different evaluation layers.
- **Section 7.1 (config example)**: `[adapters] enabled` now includes `"opencode"`.
- **Section 9.7 (format table)**: Added `prompt_opencode_command` row. Documented the CLI's short-alias mapping (`--format continue` → `continue_rule`, etc.).
- **Section 10.1 (Adapter ABC)**: Reconciled with concrete implementations. `finalize()` is now declared as a default no-op lifecycle hook (used by ClaudeCodeAdapter). `cleanup_stale()` is no longer `@abstractmethod` and ships with a default implementation that all built-in adapters can rely on. `write_skill()` docstring clarifies the OpenCode case (returns [] because Claude Code adapter already writes to a path OpenCode reads).
- **Section 11.1 (overlay layers)**: Resolved a three-way contradiction. The repo-local override directory is `<repo>/playbook/` (containing `rules/`, `prompts/`), not `<repo>/playbook/resources/`. Section 4.2 and Section 5.3 were already consistent with this; Section 11.1 was the outlier and is now fixed.
- **Section 12.1 (playbook init)**: "Next steps" now mentions `.opencode/`.
- **Section 12.2 (playbook sync)**: Output includes a line for opencode adapter writes (5 files). Total adjusted to 23.
- **Section 12.7 (playbook render)**: `--show-source` output explains why opencode isn't listed for rules ("reads rules via AGENTS.md natively — no direct render").
- **Appendix A.4 (worked example)**: Result tree includes `.opencode/command/` with the five prompts.
- **Appendix A.6 (update step)**: playbook sync output includes opencode adapter line; summary count updated to 3.
### v0.3 (2026-05-20)
OpenCode support added as a third primary adapter alongside Continue and Claude Code.
- **Section 2.1 (G1)**: Updated primary adapter list to include OpenCode.
- **Section 2.2 (non-goals)**: Expanded with OpenCode-specific exclusions — no agents, no plugins, no `opencode.json` management in v1. Codex moved from "no dedicated adapter" to "AGENTS.md is sufficient".
- **Section 2.3 (v2 aspirations)**: Added OpenCode plugin generation and OpenCode agents as a fifth canonical artifact category.
- **Section 3 (glossary)**: Added entries for OpenCode plugin and OpenCode agent. Updated rule/prompt/skill entries to mention OpenCode's discovery paths.
- **Section 4.2 (data flow)**: Step 6 now lists four adapters including `opencode`.
- **Section 5.1 (engine layout)**: Added `opencode_adapter.py` and `test_opencode.py`.
- **Section 5.3 (consumer repo layout)**: Added `.opencode/command/` block, with explicit notes on why no `.opencode/rules/` or `.opencode/skills/` is generated.
- **Section 6.1 (rules)**: Added note that OpenCode receives rules via the AGENTS.md adapter.
- **Section 10.6 (NEW)**: OpenCode adapter design — prompt-to-command translation, hook gap, agents gap, explicit boundaries on what the adapter does not touch.
- **Section 12.1 (`playbook init`)**: OpenCode added to the assistant multi-select.
- **Section 19**: Added open questions Q8 (OpenCode plugin generation) and Q9 (OpenCode agents as a first-class artifact).
- **Implementation order recap**: Added PR 7 (Track 4c, OpenCode adapter, ~150 LoC); subsequent PRs renumbered.
### v0.2 (2026-05-20)
- **Section 6.0**: Added explicit `.md` vs `.md.j2` distinction. Plain markdown is the default; Jinja is opt-in via `.j2` suffix.
- **Section 6.2**: Added rule inclusion in prompts. New `includes_rules:` frontmatter field, `{{ rule("id") }}` Jinja helper, and implicit-appendix mode for plain-markdown prompts. Full design in new Section 6.2.5.
- **Section 9**: Renderer subsystem updated with extension dispatch (9.2) and the `rule()` Jinja helper (9.5). Format post-processing in 9.7 documents the auto-appendix behavior for prompts.
- **Section 12.6 (`playbook validate`)**: New validation rules for `includes_rules:` consistency and the "rules cannot include rules" constraint.
- **Section 12.7 (`playbook render`)**: New `--show-rules` flag to display resolved rule inclusions for a prompt.
- **Section 19**: Added open questions on glob/tag-based rule inclusion (Q6) and cross-prompt rule sharing (Q7).
- **Sections 5.1, 5.2**: Tree examples updated to mix `.md` and `.md.j2` realistically rather than uniformly using `.md.j2`.
- **Appendix A.5**: Worked example updated to show how `includes_rules:` makes slash commands reliable across contexts.
### v0.1 (2026-05-20)
- Initial draft.
<!-- module-moves: end-keep -->
