# PR T - Flat concept packages: the src/coding_agent_playbook layout

**Status:** Accepted design, 2026-10-18.

**Links:** [ADR 0002: flat concept packages with an enforced dependency direction](../docs/adr/0002-flat-concept-packages-with-an-enforced-dependency-direction.md) · [CONTEXT.md](../CONTEXT.md) (the glossary; its terms are used as defined there) · the architecture review of 2026-10-18 (working notes, not committed: `arch-review/synthesize.json` for the target layout and the deepening candidates, `verify-depth.json` and `verify-cost.json` for the verifier verdicts, `map-*.json` for the per-area evidence) · [specs/prS-skills-context.md](prS-skills-context.md) (the skills ticket chain #49-#62 this work runs beside).

**Baseline:** `ef19a0a` plus the two uncommitted documents of the `docs/package-layout` branch: CONTEXT.md with the terms Generated output, Lockfile, Guard twin and Grading kernel, and ADR 0002. Every `file:line` anchor was read there. Line numbers are best effort (L9): the chain moves many of them. **Re-anchored on `393b0a1`** (origin/main, 2026-10-18): #49 merged (issue closed 12:45Z; PR #71) and added `adapters/_where_guidance.py` (398 `.py` files under `src/coding_agent_playbook/`), so the open chain is #50-#62. "#49-#62" below names the chain; its open tickets are #50-#62, and the chain-overlap columns treat #49's edits as landed.

**Words.** Glossary terms (Rule, Skill, Hook, Guardrail, Guard twin, Grading kernel, Generated output, Lockfile, Detector, Renderer, Adapter, Harness, Layer and the rest) mean what CONTEXT.md says. Architecture terms: a **module** is a `.py` file; a package's **interface** is its non-underscore modules and its **implementation** is its underscore modules (L5); a **seam** is where an interface lets one implementation stand in for another, and an **adapter** at a seam is one such implementation; a module is **deep** when a small interface hides much behaviour and **shallow** when the interface is as big as what it hides; **leverage** is what callers get from one interface; **locality** is how much of one change stays in one place. PR ids (`T0.1`, `N4`, `B2`, `A6`, `GC-2` ...) are defined in section 7; the harmonisation choices `H1`-`H29` are in section 11.

## 1. Summary and goal

### 1.1 Today's shape (measured at the baseline)

| Measure | Value |
| --- | --- |
| Top-level entries in `src/coding_agent_playbook/` | 58: 48 modules and 10 packages (`adapters`, `commands`, `evals`, `evaluators`, `harness`, `hook_policy`, `hook_registrations`, `hook_runtime`, `security`, `sources`) |
| Source | 397 `.py` files, 80,716 lines |
| Tests | 392 `.py` files, 100,973 lines |
| Modules over the ~500-line budget | 10: `commands/eval.py` 735, `evals/_compile.py` 619, `commands/init.py` 582, `sources/filesystem.py` 550, `commands/import_harness.py` 544, `commands/sync.py` 543, `orchestrator.py` 528, `adapters/agent_harness_adapter.py` 513, `adapters/_skill_writer.py` 508, `evals/runner.py` 503 |
| Package-level import cycle at run time | one, through 15 top-level modules: `adapters, config, evals, evaluators, gate_scan, harness, hook_policy, hook_registrations, hook_runtime, metrics_config, orchestrator, renderer, rule_registry, skill_document, sources` |
| Imports of an underscore module from outside the package that owns it | 41 (importer, private module) pairs |
| Command modules that import another command | 5 edges |
| Package `__init__.py` files (besides the root) that hold code | 8: re-export facades or registration by import |
| One concept in several places | the Hook concept in `hook_policy/`, `hook_registrations/`, `hook_runtime/`, `guard_config.py` and nine `_guard_config_*.py` root modules; sync logic in `commands/` (`sync.py` plus eight `_sync_*`/`_output_*` helpers); `evals/` beside `evaluators/`; the consumer config files across `config.py`, `config_entries.py`, `config_schema.py`, `hooks_config.py`, `_table_shapes.py`, half of `links.py`, half of `sources/filesystem.py` and `commands/_committed_config.py` |

### 1.2 Target

- About 20 top-level packages, each named after a glossary concept (section 3), plus two root modules (`toml_writer.py`, `precommit.py`), the root `__init__.py` and the `templates/` data directory.
- One declared dependency direction: a package imports only packages below it. `hook_runtime/` is a separate stack that imports only stdlib leaves outside itself, except on named, deferred branches.
- An underscore module is imported only from inside its own package. A package `__init__.py` holds only a docstring; the two exceptions are the root (lazy `__version__`) and `cli/` (`main` and its error mapping only, fixed by L2; the parser lives in `cli/parser.py`).
- import-linter enforces both rules from a pytest test, so the CI gate stays `ruff check .`, `ruff format --check .`, `mypy`, `pytest -q` on Python 3.12 and 3.13 (L4).
- Tests for a package live in `tests/<package>/` (L8). The external contract of L2 stays fixed and nothing else gets a shim.
- Files move in move-only PRs (L1, L13). Seven deepening candidates of the review land as behaviour PRs in the new homes (L12).

### 1.3 The plan in numbers

72 PRs: 4 lane-0 PRs (guards, contracts, the rewrite script, deferred pins; T0.3 after #62), 9 move-only PRs and 2 behaviour PRs that run now beside the chain, 39 move-only PRs (16 of the N series and 23 of the A series) and 17 behaviour PRs after the chain (#62) merges, and 1 docs PR at the end. The split follows the answers of 2026-10-18 (2.3): L1 applies per package, so every move out of a package the open chain edits waits for #62. Section 7 lists them with blockers and the lanes that can run in parallel.

## 2. Decisions

### 2.1 The settled decisions (approved 2026-10-18)

| Id | Decision | How this spec applies it |
| --- | --- | --- |
| L1 | Packages the in-flight skills chain does not touch move now, as parallel lanes; packages the chain touches move after it merges. A PR either moves files or changes behaviour, never both. | Applied as written, per package: the wave rule of 2.2 (question 3, resolved 2026-10-18; 2.3). H1, which amended L1 and ADR 0002 to apply L1 per file with timed soft overlaps, is **withdrawn**. So N8-N11, N13, N14-N21, N23 and N24 wait for #62, and so do the PRs that wait on them (N25, B2, B3, B4a, B4b, B6, B8, B9, B10). Every N/A PR is move-only; every B/GC/RS/AH/CP behaviour PR is separate. |
| L2 | Only the external contract stays fixed: `python -m coding_agent_playbook.hook_runtime`, `coding_agent_playbook.cli:main` (`cli/` becomes a package whose `__init__` exports `main`, plus `cli/__main__.py`), `coding_agent_playbook.hook_runtime.cli:main`, `coding_agent_playbook.adapters.base`, and every entry-point group name. Everything else moves with no re-export shims; the module-path values in our own entry points are updated. | N7 converts `cli.py` (5.3, H7). The rewrite script refuses to touch the frozen names (5.4.3). Every existing re-export is removed by the move that touches its module (section 6.3, "L2 shims"). |
| L3 | A flat layout of about 22 top-level concept packages per the review's target layout, amended by L6 and L10. | Section 3. The amendments this spec adds inside L3's frame are H2-H17; one of them (H3, the twin-shared judges in `hook_runtime/judges/`) was question 1, adopted on 2026-10-18 as an amendment of L3 for these judges only (2.3). |
| L4 | import-linter (a new dev dependency) enforces the layer order and "an underscore module is imported only from inside its own package", from a pytest test. | T0.2 (section 6). Rule 2 is a custom import-linter contract type (`private_modules`), because the built-in `protected` type cannot express "its own package". |
| L5 | Package `__init__.py` files hold only a docstring (the root's lazy `__version__` stays); a package's interface is its non-underscore modules. | `tests/architecture/test_package_inits.py` (T0.2) with a shrinking baseline; `cli/__init__.py` is the second permanent exception, narrowed to `main` and its error mapping (L2 names `cli:main`; H7). |
| L6 | `evaluators/` is renamed `grading/` (CONTEXT: Grading kernel); `hooks/` (sync-time half) and `hook_runtime/` keep their names; `evals/` and `metrics_gate/` keep theirs. | N25. |
| L7 | CONTEXT.md gains Generated output, Lockfile, Guard twin, Grading kernel. | Already on the branch. Question 4 (resolved 2026-10-18, 2.3) adds four more terms, each in the PR that creates its package: Agent Harness tree (N12), Consumer config (N2), Validation (A4), Sync (A6); D1 records the `commands/`, `security/` and `precommit.py` exceptions in ADR 0002. CONTEXT.md entries name no paths. |
| L8 | Tests for a package live in `tests/<package>/`, moved in the same PR as the package; `tests/cli/` and `tests/integration/` stay. | Section 5.2. Tests of root modules stay in `tests/unit/` (H18); cross-cutting architecture tests live in `tests/architecture/`. |
| L9 | Each move PR rewrites module paths in the living docs (SPEC.md, README.md, MIGRATION.md, catalog/README.md) with one script; historical `specs/*.md` are records and are not rewritten. | The rewrite script (5.4, T0.0). |
| L10 | The package for engine-owned consumer files is `generated_output/`. | N6, A7. |
| L11 | The work runs through the unattended loop: spec, tickets, implementer, adversarial reviewer, fix, CI, squash merge. | Every PR in section 7 is sized for one implementer context and lists its acceptance criteria and CI commands. |
| L12 | Now, beside the chain: config-files; guard-config-contract reader side; guard-twin-judges; grading-kernel measuring pass; cli-command-protocol for commands outside the chain; the `playbook render` applies_if fix (test first); the import-budget and module-name guards (lane 0). After the chain: guard-config-contract writer side, render-session, agent-harness-roundtrip, cli protocol for sync/validate/render/init. Dropped for now: catalog-layers (except what the detector move needs), sync-engine, the separate hook_runtime review. | Now: B1, B7, the metrics-gate move N22, T0.0-T0.2. The other now-candidates keep their designs but run after #62, because the moves they wait for move out of chain-edited packages (L1 per package, question 3, 2.3): B2, B3/B4a/B4b, N14/N15/B6, B8, B9/B10. After: GC-1..GC-4, RS-1..RS-3, AH-1/AH-2, CP-1..CP-3. Dropped work is listed as "not scheduled" wherever a mapper proposed it. |
| L13 | Within one area: move first (move-only PR), then deepen in the new home (behaviour PR). | Every behaviour PR's blockers include the move of its area (section 7). |
| L14 | The spec decides each candidate's design from the review, with defaults; it flags only genuine product decisions. | Section 12 held four questions, each with a default; the user answered them on 2026-10-18 (2.3), and everything else is decided here. |

### 2.2 How the decisions are applied

- **Wave rule (L1 as written; question 3, resolved 2026-10-18).** L1 and ADR 0002 say that packages the open chain touches move after it merges, and this spec applies that per package: a move runs **now** only when no open chain ticket (#50-#62; #49 merged) edits or creates a file in the package the moved code leaves or joins, and no open ticket's new code imports it. The root `src/coding_agent_playbook/` is not a concept package, so a root module counts on its own: it moves now when no open ticket edits it. Everything else waits for #62, with its other blockers unchanged. A now-move may still rewrite import lines, dotted module strings and single pin lines in chain-edited files. That is a **soft overlap**, allowed provided the move PR merges right after a chain ticket merges (never while one is in review), and the next chain ticket re-runs the rewrite script when it rebases (5.4.6). H1's file granularity (a module of a chain-edited package moving now when no ticket edits that one file) is withdrawn.
- **Move-only.** A move PR contains `git mv`, the rewritten imports and strings, the matching test moves (L8), the living-doc rewrite (L9), the pin and contract updates of sections 5.3 and 6.2, and nothing else. A name is renamed only when the move makes it cross a package (for example `_write_result` becomes `write_import`).
- **No shims, one spelling.** No re-export at an old path, no re-export from a package `__init__`, and no public module re-exporting a name from a private module of its own package.
- **One gate.** `ruff check .`, `ruff format --check .`, `mypy`, `pytest -q`, cache-free, on Python 3.12 and 3.13 (7.1). Conventional Commit titles; no stacked PRs; harness files (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.opencode/`, `.agents/`, `shared_skills/`) are never committed.

### 2.3 The answers of 2026-10-18

The user answered the open questions of section 12 on 2026-10-18. Section 12 keeps each question with its resolution; this table says where the spec applies it.

| Question | Answer | Applied in |
| --- | --- | --- |
| 1. Home of the twin-shared judges | The default: public modules in a new `hook_runtime/judges/` package (N14, N15), amending L3 for these judges only (H3). | 3.1, 4.24, N14, N15, section 8 B.8 |
| 2. An invalid `[metrics]` value in the committed config | The default, option (a): a follow-up after #62 makes `playbook validate` report it as an error, so sync refuses before writing anything. B2 keeps today's behaviour and pins it with a test. | section 8 B.5.5, B.13, B.14 |
| 3. Wave rule granularity (also asked as question 15) | Package granularity: L1 as written. H1 (file granularity with timed soft overlaps) is withdrawn. N8, N9, N10, N11 (`commands/`), N13 (`adapters/`), N14-N21 (`hook_runtime/`), N23 and N24 (`evals/`) move to after #62 with their other blockers unchanged, and so do the PRs that wait on them: N25 (via N24), B2 (via N10), B3, B4a and B4b (via N16), B6, B9 and B10 (via N8, N11 and N14) and B8 (via N25). Now: lane 0 (T0.0, T0.1, T0.2), N1-N7, N12, N22, B1 (it must merge before #54 starts) and B7. Each of these was re-checked against the open chain's touched files (7.2.1): none moves code out of or into a package an open ticket edits, so none moved. One blocker is added so that the designs keep the order they assume: A14 waits for N14 and N15. | 2.2, 4 (Wave column), 7.1.3, 7.2, 7.4-7.7, section 8, AC.1.1, R1, H1 |
| 4. CONTEXT.md terms | The default, with the Consumer config definition corrected (it named a wrong path, and CONTEXT.md entries name no paths): Agent Harness tree (N12), Consumer config (N2), Validation (A4), Sync (A6), and the `commands/`, `security/` and `precommit.py` exceptions recorded in ADR 0002 by D1. | N2, N12, A4, A6, D1 |
| PR granularity (question 16) | Keep this spec's PR granularity: the 72 PRs of section 7. | section 7 |

## 3. Target layout

### 3.1 The package tree

Paths are relative to `src/coding_agent_playbook/`. "CONTEXT" names the glossary term a package is named after; the PR that creates or fills the package is in brackets.

```
__init__.py          lazy __version__ only (L5's root exception)
cli/                 the `playbook` entry point [N7]: __init__ defines main and its error mapping only (L2;
                     the second L5 exception, H7), parser (build_parser, _SUBCOMMANDS), __main__.py,
                     _command.py (the Command protocol) [B9]
commands/            one flat module per subcommand (run, and configure after B9/B10/CP-1/CP-3) with private
                     _<command>_<topic>.py helpers (H6); twins/ (CONTEXT Guard twin) [N8]: gate_scan,
                     scan_secrets, scan_sinks, check_notebooks, check_commit_trailers, check_deps, ci,
                     policy, _git_scope, _secret_scope, _ci_*; _runner [B6]
sync/                the sync pipeline [A6]: pipeline (execute), render, git_client, _check_modes, _dispatch,
                     _hook_outputs, _machine_local, _leftovers, _output_policy, _output_blockers,
                     _protect and _hook_scripts [GC-2]
validation/          the validation rule set [A4]: checks, findings, preflight, link_check, context
                     (SyncContext, H4) [A5], _frontmatter, _hooks, _links, _prompts, _skills
agent_harness/       the Agent Harness format round trip (was harness/) [N12, AH-1, AH-2]: models
                     (HarnessTree), parser, leaf_detectors, manifest, emitter, adapter, hook_sidecars,
                     importer, lint
evals/               CONTEXT Eval task: task, loader, validator, prompting, judge, registry and
                     report_format [N11]; compile/ (compiler, gate_registry, rubric_registry, _expr,
                     _handles) and run/ (harness_runner, scoring, fake_runner, claude_code_runner,
                     opencode_runner, agent_env, git_env) [N23]; checks/ (files, answer, aggregate) [N24]
precommit.py         the pre-commit template and text merge [N9]
adapters/            CONTEXT Adapter: base.py (L2), registry [A5], agents_md, continue_, opencode,
                     shared_skills [A9], _where_guidance; claude_code/ [N13, A8]: adapter, hooks, paths,
                     _secret_native, _destructive_native, _overlay_native, settings/ (managed_merge, drift,
                     _plan, _json_spans, _json_edits); skill_dirs/ (writer, ownership) [A9]
rendering/           CONTEXT Renderer [RS-1]: jinja (the sandbox), formats, rule_registry,
                     prompt_rule_delivery, session (RenderSession) [RS-2]
hooks/               the sync-time half of CONTEXT Hook: resolution/, contract/, enforcement,
                     guardrails_skill [A17]; registrations/ (plan, claude, opencode, stop_gate, launcher,
                     templates/) [A18]; guard_config/ (compile, inputs, resource_roots, ruff_probe,
                     _tables_*) [GC-2]
skills/              CONTEXT Skill, Member rule, Reference [A3]: document, membership, naming
metrics_gate/        `playbook metrics` and the Stop-stage metrics call [N22]: run, config, inputs, suite,
                     policy, snapshot
catalog/             CONTEXT Catalog, Layer, Core, Bundled plugin, Overlay [N3]: roots, layers, source,
                     _hook_walk; resolve [A5]
config/              the two consumer config files [N2]: model, schema, entries, files (ConfigFiles [B2],
                     FileSystemStateSource), committed [N10], tables/ (hooks, links, _table_shapes)
detector/            CONTEXT Detector, Detector fact [N4]: facts, predicate, pep503, pyproject_deps
lockfile/            CONTEXT Lockfile [N5]: model, drift, canonical_json
grading/             CONTEXT Grading kernel (L6) [N25]: metric, check, check_registry, compose, rubric,
                     scheduler, normalizer, scope, parse, types, judged, judge_metric, execution_checks,
                     tool_runner, paths, baseline_git, measuring [B8]; static_metrics/, execution_metrics/
artifacts/           CONTEXT Rule, Prompt, Skill, Hook: path_classes [N15]; hook_schema, hook_frontmatter,
                     member_reference [A1]; frontmatter, rule, prompt, skill, hook [A2]; identity [A5];
                     path_globs [A12]
generated_output/    CONTEXT Generated output (L10) [N6]: sentinel, file_identity, atomic_io, output_io,
                     symlinks, gitignore; write_guard, source_files [A7]
security/            stdlib-only judges with no runtime dependency, and the trust store: secrets, pii,
                     pii_findings, paths, patterns, files, commit_trailers, trust (audit and
                     decision_summary leave for hook_runtime/state/ in N19)
toml_writer.py       the TOML writer (was _toml.py) [N1]
hook_runtime/        the hook runtime, a separate stack; name fixed by L2: cli, __main__, ruff [A16];
                     config/ [N16] (guard_config, reader, keys, hook_records, lock_digest, pin, protected;
                     guard_tables [B3], hook_config [B4a], schema [GC-1]); shell/ [N17]; git/ [N18];
                     state/ [N19]; diagnostics/ [N20]; harness/ (wire, payload) [N21]; judges/ [N14, N15];
                     dispatch/ [A10, A11]; stop/; handlers/{safety,protect,verify,feedback,audit,_shared}/
                     [A14-A16], each handler module named after its snake-cased hook id
templates/precommit/ unchanged data
_plugin_registry.py  not scheduled (L12 split grading-kernel part (f) off; H12)
```

### 3.2 The dependency direction

Highest first. A package may import any package below it; packages joined by `|` are independent siblings and may not import each other. There are no two-way tiers: ADR 0002 allows imports only from packages below in one declared order, so the two groups the review drew as tiers (`catalog : config : detector : lockfile` and the leaves) are ordered strictly by today's one-way edges (`config.py:20` and `config_schema.py:18` import catalog; `commands/_committed_config.py:28`, `config/committed` after N10, imports detector; the state half of `sources/filesystem.py:25`, `config/files` after N2, imports lockfile; `adapters/_skill_sources.py:28, :33`, `generated_output/source_files` after A7, imports security and the Skill type of artifacts; neither `catalog`, `detector` nor `lockfile` imports another of the four, and `artifacts`, `security`, `toml_writer` import none of the leaves; AST scan at the baseline). This is exactly the `engine-layers` contract of section 6 (H2, H5).

```
cli
 └─ commands ─────────────────────────────────┐ twins import public hook_runtime modules
     └─ sync ─────────────────────────────────┤ sync (machine-local hook pins, sync/_machine_local after A6)
                                              │ imports public hook_runtime modules
         └─ validation                        │
             └─ agent_harness | evals | precommit
                 └─ adapters                  │
                     └─ rendering             │
                         └─ hooks ────────────┤ sync-time hooks/ import public hook_runtime modules
                             └─ skills        │
                                 └─ metrics_gate
                                     └─ config
                                         └─ catalog
                                             └─ detector | lockfile
                                                 └─ grading
                                                     └─ generated_output
                                                         └─ artifacts                 (the leaves)
                                                             └─ security | toml_writer | _plugin_registry

hook_runtime   a separate stack, not a layer (contract hook-runtime-stack): it imports only itself, the
               stdlib and STDLIB_LEAVES (artifacts.path_classes, artifacts.path_globs, catalog.roots,
               detector.pep503, detector.pyproject_deps, generated_output.atomic_io,
               generated_output.sentinel, lockfile, security after the moves); its deferred
               branches into grading, metrics_gate, evals, catalog, config, detector and
               artifacts are named ignore_imports lines whose import cost the -X importtime
               budget probes pin per branch.
```

Who may import `hook_runtime`: it sits outside the layers (`exhaustive_ignores = ["hook_runtime"]`), so `engine-layers` does not restrict its importers, and the private-modules contract limits them to its public modules. Three layers import it, as the annotations show: `commands` (the twins, `commands/twins/` after N8), `sync` (`commands/_sync_hook_local.py:40-41, :55-56` imports `hook_runtime.pin`, `proc`, `deps`; `sync/_machine_local.py` after A6) and `hooks` (`guard_config.py`, the `_guard_config_*` readers, `hook_policy/` and `hook_registrations/`). `grading` may not (the `grading-kernel` contract; today's `evaluators/paths.py` and `types.py` edges go in N15 and N22), nor may the leaves (`stdlib-leaves`). No contract forbids another layer from importing `hook_runtime` later; a new importer outside these three is a review item, not a gate failure.

Why this order and not the review's draft: `adapters` imports `renderer`, `hook_policy`, `hook_registrations` and `skill_document`, so it sits above rendering, hooks and skills; `renderer` imports `hook_policy` and `hook_registrations`, so rendering sits above hooks; the sync pipeline runs the validation gate (`sync.py:91-92`), so sync sits above validation; validation imports `evals.loader` and `evals.validator` (`validate.py:84-88`), so evals sits below validation; the sync-time quality reader reads `[metrics]` through `metrics_gate.config`, so `metrics_gate` sits below hooks, and `metrics_gate` imports only `config`, `grading` and the leaves (H5).

## 4. The module map

One table per target package, harmonised from the five area maps; section 11 lists every choice where they disagreed. Paths are relative to `src/coding_agent_playbook/`.

- **Current**: today's module, or a part of it for a split (with line ranges at the baseline); "(new)" or "(created by #N)" marks a file that will exist before its move runs.
- **Target**: the destination; a split or merge lists every destination joined by ` + `. A split row appears in the table of every package it feeds.
- **Action**: `move` (new package), `rename` (new stem), `split`, `merge-into` (concatenated verbatim with another module), `stay`, `delete`.
- **Wave**: `now` or `after-chain`, by the wave rule of 2.2 (per package, question 3 resolved 2026-10-18). A row whose PR moved after #62 on that date reads `after-chain` although its chain-overlap cell may say `none`: the package it leaves or joins is chain-edited.
- **PR**: the section-7 PR that carries the row; `—` for a module that stays.
- **Lines, Importers**: the module's size and the number of source and test modules that import it (AST scan at the baseline, lazy and TYPE_CHECKING imports included; handler modules bound by string show 0).
- **Chain overlap**: what the open tickets #49-#62 do to the file or its importers; "soft" means import lines and dotted strings only (2.2).
- **Note**: pins, reasons and constraints from the area mappers, with the harmonised decisions marked "Harmonised (§11 Hn)".

### 4.1 Root `__init__.py`

The lazy `__version__` (L5's one root exception). 1 row.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `__init__.py` | __init__.py | stay | now | — | 41 | 32 | none | Lazy __version__ only. This is the one L5 exception besides cli/__init__.py. Most of its 32 'importers' are `from coding_agent_playbook import <module>` forms, which the rewrite script must turn into `from coding_agent_playbook.<pkg> import <mod> as <old local name>`. |

### 4.2 `cli/`

The `playbook` entry point (L2: `coding_agent_playbook.cli:main`). 1 row.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `cli.py` | cli/parser.py (git mv: the subcommand imports, _SUBCOMMANDS, build_parser and the _add_*_parser helpers, cli.py:1-422) + cli/__init__.py (main, the error-to-exit-2 mapping and _missing_catalog_line, cli.py:424-478) + new cli/__main__.py | split | now | N7 | 480 | 24 | none remaining (spec:479, the cli.py:86 --adapters help line, landed in #68) | Harmonised (§11 H7): cli/__init__.py holds only what L2 forces (main and its error mapping), the second sanctioned L5 exception; build_parser and _SUBCOMMANDS live in cli/parser.py, and the script rewrites their test importers ([[names]] entry: tests/unit/test_cli.py:11, test_docs_lifecycle_hooks_cli.py:35, test_docs_readme_hooks.py:25, tests/cli/test_ci.py:20, test_metrics_coverage.py:16, test_metrics_selection.py:17, test_ci_commit_convention.py:17, test_init_hooks.py:17, test_sync_output_policy.py:18). __main__.py keeps `python -m coding_agent_playbook.cli` working for hook_runtime/handlers/_source_changed.py:56 and commands/ci.py:99. The Command protocol (cli/_command.py) comes with B9. |

### 4.3 `commands/`

One flat module per subcommand plus `twins/` (CONTEXT: Guard twin). 25 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `commands/__init__.py` | commands/__init__.py | stay | now | N7 (docstring) | 6 | 0 | none | Already docstring-only (L5). No module imports a name from it; the AST scan sees 68 'from coding_agent_playbook.commands import <module>' lines, which are submodule imports. Docstring names cli.py; reword it in N7. |
| `commands/_check_hooks.py` | commands/_check_hooks.py | stay | now | — | 90 | 1 | none in src (#58/#62 change only tests/cli/test_check_hooks.py counts) | A private helper of check.py, imported only by it (rule 2 holds inside commands). Its imports of hook_policy and orchestrator are rewritten by A17 and A5. The target's commands/check/ package is dropped (§11 H6). |
| `commands/_ci_commit_convention.py` | commands/twins/_ci_commit_convention.py | move | after-chain | N8 | 130 | 4 | none | It imports commands.ci at :35 under TYPE_CHECKING and lazily at :115, a type-level cycle that verify-depth confirms is not a runtime cycle at import. Inside twins/ the cycle is intra-package, which is legal. Splitting StepRun/StepRecord into twins/_ci_steps.py is optional tidy-up, not part of the move. The target's twins/ci/ subpackage is dropped: ci has two helpers, and a third path segment buys nothing. Test importers are unit/test_docs_lifecycle_hooks_cli.py:36, unit/test_docs_readme_hooks.py:26 and integration/test_dogfood_config.py:29. |
| `commands/_ci_policy.py` | commands/twins/policy.py (together with _twin_policy.py) | merge-into | after-chain | N8 | 139 | 3 | none | Concatenated verbatim with _twin_policy.py (108 lines), about 245 lines in total. This removes the lazy imports _ci_policy.py:52,65 -> _twin_policy. Public, not underscore, because init.py:461 imports commit_convention_configured from outside twins/. Reading it through ConfigFiles is B2, not part of the move. The lazy import of evaluators.metrics_gate at :78 is rewritten by whichever of N8 and N22 lands second. The CONFIG_FILE at :27 goes with B2. |
| `commands/_ci_report.py` | commands/twins/_ci_report.py | move | after-chain | N8 | 66 | 1 | none | Single caller ci.py. It imports ci.py at :19, but only under TYPE_CHECKING. |
| `commands/_git_base.py` | commands/twins/_git_scope.py (with ScanRange, resolve_range and _symmetric_base from commands/gate_scan.py:51-61,82-104,135-141) | merge-into | after-chain | N8 | 91 | 7 | none | About 140 lines. This stops three twins from importing the gate-scan command as a library (_secret_scope.py:23, scan_sinks.py:30, check_commit_trailers.py:91). Used by every twin and by ci.py, all inside twins/, so it can be underscore. run_twin is B6 (commands/twins/_runner.py). |
| `commands/_init_adapters.py` | commands/_init_adapters.py | stay | now | — (CP-3 drops the cli import) | 56 | 6 | none remaining (spec PR 1 landed in #68) | cli.py:37 imports it, an underscore module from outside commands, which violates rule 2. The fix is init's Command.configure owning --adapters, which L12 puts after the chain; until then the import goes in the ignore list. Tests import DEFAULT_ADAPTERS (unit/test_docs_skill_roots.py:16, adapters/test_agent_harness.py:758). |
| `commands/_secret_scope.py` | commands/twins/_secret_scope.py | move | after-chain | N8 | 122 | 1 | none | Its import of hook_runtime._git_parse at :24 violates rule 2. N18 fixes it (hook_runtime/git/parse.py, public). |
| `commands/_twin_policy.py` | commands/twins/policy.py | merge-into | after-chain | N8 | 108 | 4 | none | Public: init.py:448 imports commit_trailer_policy lazily. That stays an import of a shared twins helper (commands.twins.policy is not a command, so command-independence does not list it); a hooks/twin_policy.py home is not scheduled. Its CONFIG_FILE at :31 goes with B2. |
| `commands/check.py` | commands/check.py | stay | now | — (B9 adds configure) | 254 | 5 | none in src (#52/#58/#62 edit tests/cli/test_check*.py only) | Its import lines are rewritten by the moves of its dependencies: _committed_config (N10), _sync_preflight (A4), adapters._settings_drift at :22 (N13). _format_skip_reason (:96) stays: the catalog-layers predicate slice that would move it is not scheduled (L12). |
| `commands/check_commit_trailers.py` | commands/twins/check_commit_trailers.py | move | after-chain | N8 | 117 | 1 | none | The lazy imports of commands.gate_scan.resolve_range at :91 and _git_base at :110 become twins._git_scope. Tests drive it through cli.main (tests/cli/test_check_commit_trailers.py), so the test files are unchanged. |
| `commands/check_deps.py` | commands/twins/check_deps.py | move | after-chain | N8 | 138 | 1 | none | Imports hook_runtime.handlers._dependency_tiers (:31) and _manifest_diff (:38, :49 under TYPE_CHECKING), rule-2 violations. N14 fixes them (hook_runtime/judges/dependency_tiers.py and manifest_diff.py, H3). |
| `commands/check_notebooks.py` | commands/twins/check_notebooks.py | move | after-chain | N8 | 97 | 1 | none | Imports hook_runtime.handlers._notebook_check (:24) and, lazily, hook_runtime._git_parse (:67), both rule-2 violations. N14 (judges/notebook_check.py) and N18 (git/parse.py) fix them. |
| `commands/ci.py` | commands/twins/ci.py | move | after-chain | N8 | 488 | 8 | none | SPEC calls `playbook ci` the aggregate off-workstation twin. _CLI = ('-m', 'coding_agent_playbook.cli') at :99 depends on cli/__main__.py (N7). Test importers are rewritten: tests/fakes.py:35, cli/test_ci.py, cli/test_ci_commit_convention.py, unit/test_docs_lifecycle_hooks_cli.py:39, unit/test_docs_readme_hooks.py:27. Close to the 500-line budget; do not grow it in the move. |
| `commands/eval.py` | commands/eval.py (~255 lines) + evals/registry.py (eval.py:67-70, 233-264) + evals/report_format.py (eval.py:285-445) + commands/_eval_enumerate.py (eval.py:449-735) | split | after-chain | N11 | 735 | 4 | none | A verbatim split that brings it under budget. Functions that move into a new public module lose their underscore: load_runner_class, available_runner_names, load_judge_class, available_judge_names, task_result_to_dict, format_task_result_text. The entry-point group names coding_agent_playbook.runners and .judges (eval.py:67,70) move unchanged (L2). eval.py calls them through the module (`registry.load_judge_class`), because tests/cli/test_eval_run.py:261,352,464,495,510 monkeypatch them; those patches are retargeted to evals.registry. tests/cli/test_eval_aggregate_render.py:12 is rewritten. SPEC.md:2563 changes commands/eval.py:_display_source_path to commands/_eval_enumerate.py. The target's commands/eval/ package is dropped (§11 H6). The PluginRegistry and UnknownPluginError interface is not scheduled (L12). |
| `commands/gate_scan.py` | commands/twins/gate_scan.py (range half to twins/_git_scope.py) | split | after-chain | N8 | 186 | 4 | none | After the split it is only the command. Root gate_scan.py (the scanner) moves to hook_runtime/judges/gate_weakening.py in N15 (H3). Its CONFIG_FILE at :45 goes with B2. |
| `commands/import_harness.py` | agent_harness/importer.py (import_harness.py:72-512: ImportResult, import_harness, _write_result renamed write_import; the best-effort walk :286-432 to agent_harness/_best_effort.py if the body exceeds 500 lines) + commands/import_harness.py (run) | split | after-chain | AH-1 | 544 | 4 | none remaining (#69 landed its skill= line, :170); L12 puts agent-harness-roundtrip after the chain | Moves in AH-1 (N12 already renamed harness/ to agent_harness/). _write_result becomes write_import as the module interface. Test importers are rewritten: tests/agent_harness/test_import_roundtrip.py:29-30, test_manifest_roundtrip.py:13 (moved by N12), cli/test_import_harness.py. The two harness commands stay two modules rather than the target's commands/harness.py, so each module satisfies the Command protocol. Its import of _sentinel at :35 is rewritten by N6. |
| `commands/init.py` | commands/init.py (pre-commit half :337-439 to precommit.py in N9; CP-2 splits the rest into commands/_init_answers.py, _init_config_plan.py and _init_overlays.py) | split | after-chain | N9, CP-2 | 582 | 10 | none remaining (spec 5.4.6 landed in #68) | About 480 lines after the split, within budget. Imports that still break the rules: commands.sync at :25 (command imports command; fixed by the sync move, which retargets it to sync.pipeline.execute), commands._sync_preflight at :24 (validation move), commands._committed_config at :26 (config lane), and the lazy commands._twin_policy / _ci_policy at :448, :461 (twins move retargets them to commands.twins.policy; they leave commands later with hooks/twin_policy.py). Ask-seam prompts and the init Command protocol come after the chain (L12). Pinned symbols are rewritten: unit/test_docs_lifecycle_hooks_cli.py:40 (_render_fresh_pre_commit) and integration/test_precommit_template.py:18. |
| `commands/metrics.py` | commands/metrics.py | stay | now | — (B9 adds configure) | 332 | 5 | none | Its imports are rewritten by N22 (metrics_gate.run, metrics_gate.config) and N25 (grading.baseline_git, grading.types). SPEC.md:3545 unchanged. B9 adds its configure. |
| `commands/render.py` | commands/render.py | stay | after-chain | B1, RS-2, CP-1 | 287 | 3 | #54 (spec 7.4.9 --show-rules names the skill; _render_prompt spec:3087,3119) | Not moved. Its import of _sync_render at :20 becomes sync.render in A6. The applies_if fix (render.py:191-195 passes the unfiltered ctx.rules_resolved) is B1 (now, regression test first). RS-2 retargets it to rendering/session.py. |
| `commands/scan_secrets.py` | commands/twins/scan_secrets.py | move | after-chain | N8 | 333 | 1 | none | Imports only public security.* and hook_runtime.git modules. Its CONFIG_FILE at :71 goes with B2. |
| `commands/scan_sinks.py` | commands/twins/scan_sinks.py | move | after-chain | N8 | 234 | 2 | none | Imports hook_runtime.handlers._notebook_cells (:32) and _git_parse (:151, lazy), rule-2 violations fixed by N14 (judges/notebook_cells.py) and N18 (git/parse.py). handlers.deser (:33, :43) is a public module that is really a hook handler; N14 moves trusted_artifact_line, and the SinkTable, new_sink_calls and SinkHit names deser re-exports, to hook_runtime/judges/sink_scan.py. SPEC.md:3333 names commands/scan_sinks.py. |
| `commands/sync.py` | sync/pipeline.py (execute, _run_sync, _render_into, _run_write, _leftover_policy, _ABORT_OUTCOME; ~400 lines) + sync/_check_modes.py (sync.py:420-543: _run_check, _check_lockfile, _stale_outputs, _report_drift, _block_drift, _ignore_entries, _run_check_staged) + commands/sync.py (run, _resolve_repo_root; ~30 lines) | split | after-chain | A6 (CP-1 adds configure) | 543 | 31 | #56 and #58 (_render_into keyword arguments, rules= to write_runtime_outputs); spec 8.12 lists it | A verbatim split. After it, init no longer imports a command, the engine core leaves commands/, and the 500-line overrun ends. execute keeps today's signature and int return: the SyncOutcome/SyncDeps interface is sync-engine work, which L12 drops for now. Test rewrite: 28 test files alias `commands import sync as _sync`. The 22 that call only `_sync.execute` switch their import to `from coding_agent_playbook.sync import pipeline as _sync`. The 6 that also call `_sync.run` (cli/test_sync.py, test_sync_skills.py, test_sync_skill_references.py, test_sync_output_policy.py, test_sync_validate_gate.py, plugins/test_superpowers_sync.py) get a second alias. cli/test_sync.py's `_sync._run_sync` and `_sync._leftover_policy` follow pipeline. `_ABORT_OUTCOME` is pinned by unit/test_docs_migration_hooks.py:28. Name 'pipeline' rather than the target's sync/__init__ execute, because L5 keeps __init__ docstring-only and 'sync.execute.execute' would stutter. |
| `commands/validate.py` | validation/checks.py (collect_validation_findings, collect_validation_errors, sync_gate_errors, _artifact_errors and the in-file checks, validate.py:1-410, ~400 lines) + commands/validate.py (run, ~30 lines) | split | after-chain | A4 (CP-1 adds configure) | 436 | 23 | #52 (V1/V2), #54 (spec 7.4.8 prompt-reference checks) | After the split, sync imports validation instead of a command (sync.py:92). _warn_refused_skill_files becomes warn_refused_skill_files, because run calls it from commands/. 52 test calls of `_validate.run(` in tests/hooks/*, plugins and cli are unchanged, because run stays at commands.validate. Only `_validate._check_output_contracts` and `_applies_if_errors` move to validation.checks in tests. Rule-2 violations it carries: adapters._skill_sources (:56) and adapters._skill_writer (:57), fixed by A7 and A9. evals.loader and evals.validator (:84-88) need evals below validation (see contract violations). The ordered CHECKS tuple is not scheduled (validation deepening, L12). SPEC.md:3922 (validate.py::_check_agent_skills) and :3928 are rewritten. |
| `commands/validate_harness.py` | agent_harness/lint.py (_Finding, _is_opaque, _check_skill_leaves, _check_routing_and_content, _collect_findings -> lint_harness; validate_harness.py:56-135) + commands/validate_harness.py (_report, run; ~55 lines) | split | after-chain | AH-2 | 189 | 2 | none in src; follows agent-harness-roundtrip (after chain) | Harmonised (§11 H16): lint.py is created by AH-2 with its HarnessFindings interface, not by a separate move. Joint with the agent_harness/ moves. tests/cli/test_validate_harness.py stays (L8). |

### 4.4 `sync/`

The sync pipeline (after the chain). 12 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_guard_config_protect.py` | hooks/guard_config/inputs.py (ProtectedRow, ProtectInputs) + _tables_protect.py (protected_table) + resource_roots.py (resource_root_ids, resolve_resource_roots, _layer_dir) + sync/_protect.py (COMPOSITE_SINGLETONS, protected_rows, adapter_output_dirs and helpers) | split | after-chain | GC-2 | 282 | 2 | package touched by #58; its importer test tests/unit/test_guard_config.py is in the chain | Private. Its probe at tests/adapters/test_claude_code_rules.py:92-95 changes name. It imports adapters.claude_rule_paths (see contract_violations). |
| `commands/_output_blockers.py` | sync/_output_blockers.py | move | after-chain | A6 | 241 | 3 | none directly; its importer commands/sync.py:70 is edited by #56/#58 | Kept separate from _output_policy: the target's '_output_policy incl. _output_blockers' would be 462 + 241 = 703 lines, over budget. Importers are sync.py and _sync_output.py, both inside sync/ after the move. SPEC.md:2284 names it. |
| `commands/_output_locations.py` | sync/_leftovers.py (with _sync_orphans.py) | merge-into | after-chain | A6 | 156 | 5 | none remaining (spec PR 1 landed); importer sync.py is chain-touched | 156 + 308 = 464 lines today. Re-measure at move time; if the sum exceeds 480, keep sync/_output_locations.py instead. Test importers (unit/test_output_locations.py, test_sync_orphans.py, adapters/test_skill_writer.py:28) are rewritten. SPEC.md:3843. |
| `commands/_sync_hook_local.py` | sync/_machine_local.py | rename | after-chain | A6 | 386 | 5 | none directly; importers sync.py and _sync_hooks.py are edited by #56/#58 | Flat in sync/, not the target's sync/hooks/_machine_local.py. Under rule 2, an underscore module in a sync/hooks/ subpackage could not be imported by sync/pipeline.py. SyncHookDeps is imported by tests (cli/hook_repo.py:19, unit/test_guard_config_ruff.py:25, cli/test_sync_hook_trust.py); test imports are outside rule 2's src scope. Its import of _guard_config_ruff at :38 is rewritten by the guard-config writer move. |
| `commands/_sync_hooks.py` | sync/_hook_outputs.py | rename | after-chain | A6 | 464 | 7 | #56 (SyncHooks.dispatch guardrails_skill), #58 (write_runtime_outputs rules=/skill_globs) | Flat for the same rule-2 reason as _machine_local. HOOKS_NOTICE is pinned by unit/test_docs_lifecycle_hooks_cli.py:37 and unit/test_docs_migration_hooks.py:26. Removing the _CLAUDE / isinstance leak is sync-engine work, dropped for now (L12). |
| `commands/_sync_lockfile.py` | sync/_dispatch.py | rename | after-chain | A6 | 346 | 6 | #56 (HookDispatch.guardrails_skill, _skills_for) | Moves whole, without a split. build_lockfile, _whole_file_entry and LOCKFILE_SCHEMA leave later for lockfile/ stamping (Lockfile.stamp + CURRENT_SCHEMA), a lockfile deepening that is not scheduled. LOCKFILE_SCHEMA is pinned by unit/test_docs_migration_hooks.py:27, and build_lockfile is imported by unit/test_guard_config.py:27. |
| `commands/_sync_orphans.py` | sync/_leftovers.py | merge-into | after-chain | A6 | 308 | 3 | none directly (spec cites it only); importer sync.py is chain-touched | Takes _output_locations.py in. LeftoverPolicy is imported by adapters/test_skill_writer.py:29 and unit/test_sync_orphans.py. SPEC.md:3913. |
| `commands/_sync_output.py` | sync/_output_policy.py | rename | after-chain | A6 | 462 | 4 | none directly; importers sync.py and _sync_hooks.py are chain-touched | tests/cli/test_sync_check.py:113 monkeypatches `_sync_output.file_drift`; the rewrite keeps patching the module attribute. Its import of adapters._skill_writer at :31 violates rule 2 (A9 fixes it: adapters/skill_dirs/writer.py). SPEC.md:3913. |
| `commands/_sync_render.py` | sync/render.py | rename | after-chain | A6 (RS-2 later) | 314 | 6 | #49 (undelivered-member warning), #54 (spec 7.4.6), #56 (guardrails_skill field) | Public because commands/render.py:20 imports it. The target's rendering/session.py needs RenderSession, which is RS-2. Until then the module stays in sync/, because it imports sync's hook resolution (:30 SyncHooks, resolve_sync_hooks), and rendering/ sits below sync. Its import of adapters._agent_skill_rules at :29 violates rule 2 (A3 fixes it). Test importers: unit/test_render_hook_body.py:18, test_sync_render_skills.py:16, test_skill_membership.py:18, cli/test_sync_hook_trust.py. |
| `commands/sync.py` | sync/pipeline.py (execute, _run_sync, _render_into, _run_write, _leftover_policy, _ABORT_OUTCOME; ~400 lines) + sync/_check_modes.py (sync.py:420-543: _run_check, _check_lockfile, _stale_outputs, _report_drift, _block_drift, _ignore_entries, _run_check_staged) + commands/sync.py (run, _resolve_repo_root; ~30 lines) | split | after-chain | A6 (CP-1 adds configure) | 543 | 31 | #56 and #58 (_render_into keyword arguments, rules= to write_runtime_outputs); spec 8.12 lists it | A verbatim split. After it, init no longer imports a command, the engine core leaves commands/, and the 500-line overrun ends. execute keeps today's signature and int return: the SyncOutcome/SyncDeps interface is sync-engine work, which L12 drops for now. Test rewrite: 28 test files alias `commands import sync as _sync`. The 22 that call only `_sync.execute` switch their import to `from coding_agent_playbook.sync import pipeline as _sync`. The 6 that also call `_sync.run` (cli/test_sync.py, test_sync_skills.py, test_sync_skill_references.py, test_sync_output_policy.py, test_sync_validate_gate.py, plugins/test_superpowers_sync.py) get a second alias. cli/test_sync.py's `_sync._run_sync` and `_sync._leftover_policy` follow pipeline. `_ABORT_OUTCOME` is pinned by unit/test_docs_migration_hooks.py:28. Name 'pipeline' rather than the target's sync/__init__ execute, because L5 keeps __init__ docstring-only and 'sync.execute.execute' would stutter. |
| `git_client.py` | sync/git_client.py | move | after-chain | A6 | 105 | 4 | file untouched; all 3 importers are sync commands (commands/sync.py is edited by #56), and sync/ is built after the chain | Moves with A6. tests/fakes.py FakeGitClient follows the import. |
| `guard_config.py` | hooks/guard_config/compile.py (GuardConfigInputs, render_guard_config, serialize_guard_config, write_guard_config, SYNC_OUTPUT_LOCATIONS, HOOK_ARTIFACTS and helpers) + hooks/guard_config/_tables_precommit.py (precommit_hook_ids) + sync/_hook_scripts.py (CopiedScripts, copy_hook_scripts) | split | after-chain | GC-2 | 415 | 21 | #58 adds skill_globs to GuardConfigInputs and the derived table (spec 3720, 3937) | Harmonised (§11 H10): the designer's GC-2 file map (compile.py; the root mapper proposed writer.py). copy_hook_scripts needs adapters, so it leaves hooks/ for the sync side. #58 adds skill_globs to GuardConfigInputs and the derived table (spec 3720, 3937). Pinned at _ENGINE_PATHS (:99) and in SPEC §5.1. |

### 4.5 `validation/`

The validation rule set, preflight and the SyncContext module (after the chain). 11 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `commands/_sync_preflight.py` | validation/preflight.py | move | after-chain | A4 | 262 | 8 | none remaining (spec PR 1 landed); importers sync.py and validate.py are chain-touched | Overrides the target's sync/_preflight. check.py:23, init.py:24 and validate.py:58 import it, so a private sync/ module would break rule 2, and validation -> sync would break the layers (sync imports validation). It must be public and at validation level or lower. catalog/preflight.py would also satisfy the layers; validation/ is chosen because check, init and validate, its callers, are validation's. Its own imports are catalog only (:31, :39). |
| `commands/_validate_context.py` | validation/context.py | rename | after-chain | A4 (A5 adds SyncContext) | 134 | 4 | none directly; importer validate.py is edited by #52/#54 | Public, not the underscore form, because commands/validate.run calls config_less_context, config_less_notes and has_consumer_config (validate.py:59-63, 419-426). It imports orchestrator.SyncContext at :29 (see contract violations). Test importers: cli/test_validate.py:16 and unit/test_docs_lifecycle_hooks_cli.py:38. |
| `commands/_validate_frontmatter.py` | validation/_frontmatter.py | rename | after-chain | A4 | 188 | 2 | none directly (spec:5134 cites it only); importer validate.py is chain-touched | lint_codes_problems is imported by unit/test_rules_lint_codes.py:22, which only rewrites its import. |
| `commands/_validate_hooks.py` | validation/_hooks.py | rename | after-chain | A4 | 208 | 1 | none directly; importer validate.py is chain-touched | Its import of hook_policy._findings at :39 violates rule 2 (fixed by the hooks-area move). SPEC.md:2462. |
| `commands/_validate_links.py` | validation/_links.py | rename | after-chain | A4 | 159 | 3 | none directly (spec:1045 cites it only); importer validate.py is chain-touched | tests/cli/test_validate_links.py:212 monkeypatches `_validate_links._scan_markdown_file`, and plugins/python_design/test_pack.py:33 imports check_markdown_links; both are rewritten. Its own _CONFIG_FILENAME at :31 goes with B2. SPEC.md:3928 (validate.py::_check_markdown_links). |
| commands/_validate_prompts.py (created by #54) | validation/_prompts.py | move | after-chain | A4 | — | 0 | #54 creates it (spec 7.4.8, specs/prS-skills-context.md:3153) | Does not exist yet. Listed so the validation move does not miss it. |
| `commands/_validate_skills.py` | validation/_skills.py | rename | after-chain | A4 | 338 | 2 | #52 (V1/V2, SCOPED_RULE_NEEDS_SKILL_MESSAGE) | Its import of adapters._agent_skill_rules at :31 violates rule 2. SPEC.md:3838. |
| `commands/_validation.py` | validation/findings.py | rename | after-chain | A4 | 122 | 9 | none directly; its importers sync.py, validate.py and _validate_skills.py are chain-touched | Public: sync/pipeline.py (report_validation_errors, sync.py:91) and tests/fakes.py:48 (ValidationError) import it. Its import of adapters._agent_skill_rules at :17 violates rule 2. |
| `commands/validate.py` | validation/checks.py (collect_validation_findings, collect_validation_errors, sync_gate_errors, _artifact_errors and the in-file checks, validate.py:1-410, ~400 lines) + commands/validate.py (run, ~30 lines) | split | after-chain | A4 (CP-1 adds configure) | 436 | 23 | #52 (V1/V2), #54 (spec 7.4.8 prompt-reference checks) | After the split, sync imports validation instead of a command (sync.py:92). _warn_refused_skill_files becomes warn_refused_skill_files, because run calls it from commands/. 52 test calls of `_validate.run(` in tests/hooks/*, plugins and cli are unchanged, because run stays at commands.validate. Only `_validate._check_output_contracts` and `_applies_if_errors` move to validation.checks in tests. Rule-2 violations it carries: adapters._skill_sources (:56) and adapters._skill_writer (:57), fixed by A7 and A9. evals.loader and evals.validator (:84-88) need evals below validation (see contract violations). The ordered CHECKS tuple is not scheduled (validation deepening, L12). SPEC.md:3922 (validate.py::_check_agent_skills) and :3928 are rewritten. |
| links.py (link checker: MarkdownLink, extract_markdown_links, classify_link and helpers) | validation/link_check.py | split | after-chain | A4 | 211 | 7 | importers commands/validate.py (#52) and _validate_links.py; validation/ is built after the chain | Stays at root links.py until A4 takes it. |
| orchestrator.py (rest) | catalog/resolve.py (Collision, OverlayResolver, _resolve, _hook_collision) + catalog/source.py (engine_package_of) + artifacts/identity.py (artifact_id_of, _source_package, template_source) + adapters/registry.py (discover_adapters, installed_output_locations) + validation/context.py (SyncContext, _warn_deprecated_overlays, _resolve_hooks) | split | after-chain | A5 | 528 | 24 | 14 importers are in the chain (commands/_sync_*, render, sync, validate, evals/prompting, rule_registry and tests); destinations adapters/ and sync/ are after-chain | Harmonised (§11 H4, H11): SyncContext goes to validation/context.py, not sync/context.py: validation, check, render and eval import it, and sync sits above validation. template_source joins artifact_id_of in the stdlib leaf artifacts/identity.py, so rendering stops importing the sync context (rule_registry.py:19). _resolve_hooks stays with SyncContext (it needs hook_policy.split_hook_layers). The OverlayResolver defaults (merge_hook_layers, NO_HANDLER_SCHEMAS) keep catalog.resolve -> hooks as a named engine-layers ignore (catalog-layers is not scheduled). |

### 4.6 `agent_harness/`

The Agent Harness format round trip (was `harness/`). 12 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `adapters/_harness_hooks.py` | agent_harness/hook_sidecars.py | move | after-chain | AH-1 | 128 | 2 | none for the file; its only src importer, agent_harness_adapter.py:41, is #54 | Writes .playbook/hooks/<id>/HOOK.md. Moves with the adapter in AH-1. AH-1 waits for A7 because this module imports adapters._skill_sources (:21), which would be a cross-package underscore import. AH-2 merges in the reading half of commands/_import_hooks.py. |
| `adapters/agent_harness_adapter.py` | agent_harness/adapter.py | move | after-chain | AH-1 | 513 | 12 | #54 (PR 3: prompts point to skills) | Over budget. The value of entry point pyproject.toml:59 becomes coding_agent_playbook.agent_harness.adapter:AgentHarnessAdapter; the group name is unchanged. Also updates SPEC.md:1868 and the docstring at commands/validate_harness.py:4. AH-2 splits finalize's skill/prompt/rule-routing emitters to get under 500 lines. Lands in AH-1. |
| `commands/_import_files.py` | agent_harness/_import_files.py | move | after-chain | AH-1 | 52 | 2 | none directly; L12 puts agent-harness-roundtrip after the chain (#54 edits agent_harness_adapter.py) | Moves in AH-1 (N12 already renamed harness/ to agent_harness/). It stays separate from importer.py, because 544 + 52 + 85 lines would exceed the 500 budget. Its import of adapters._skill_files at :14 is a rule-2 violation; A7 fixes it (generated_output/source_files.py, H8). |
| `commands/_import_hooks.py` | agent_harness/_import_hooks.py (AH-1); AH-2 merges its reading half into agent_harness/hook_sidecars.py | move | after-chain | AH-1, AH-2 | 85 | 1 | none directly; follows agent-harness-roundtrip (after chain) | Harmonised (§11 H16): the designer's two steps: the verbatim move first, the merge with the writing half (read_hook_sidecar) in the interface PR. Its only caller is import_harness. |
| `commands/import_harness.py` | agent_harness/importer.py (import_harness.py:72-512: ImportResult, import_harness, _write_result renamed write_import; the best-effort walk :286-432 to agent_harness/_best_effort.py if the body exceeds 500 lines) + commands/import_harness.py (run) | split | after-chain | AH-1 | 544 | 4 | none remaining (#69 landed its skill= line, :170); L12 puts agent-harness-roundtrip after the chain | Moves in AH-1 (N12 already renamed harness/ to agent_harness/). _write_result becomes write_import as the module interface. Test importers are rewritten: tests/agent_harness/test_import_roundtrip.py:29-30, test_manifest_roundtrip.py:13 (moved by N12), cli/test_import_harness.py. The two harness commands stay two modules rather than the target's commands/harness.py, so each module satisfies the Command protocol. Its import of _sentinel at :35 is rewritten by N6. |
| `commands/validate_harness.py` | agent_harness/lint.py (_Finding, _is_opaque, _check_skill_leaves, _check_routing_and_content, _collect_findings -> lint_harness; validate_harness.py:56-135) + commands/validate_harness.py (_report, run; ~55 lines) | split | after-chain | AH-2 | 189 | 2 | none in src; follows agent-harness-roundtrip (after chain) | Harmonised (§11 H16): lint.py is created by AH-2 with its HarnessFindings interface, not by a separate move. Joint with the agent_harness/ moves. tests/cli/test_validate_harness.py stays (L8). |
| `harness/__init__.py` | agent_harness/__init__.py | rename | now | N12 | 13 | 2 | none | Becomes docstring-only (drop the from __future__ line) and reworded as 'the Agent Harness format round trip'. The rename ends the clash with CONTEXT 'Harness' and with hook_runtime.harness. The import rewrite must match only coding_agent_playbook.harness, never hook_runtime.harness or the adapter id agent_harness. |
| `harness/emitter.py` | agent_harness/emitter.py | move | now | N12 | 112 | 4 | none for the file; importers agent_harness_adapter.py:49 (#54) and _skill_writer.py:82 are chain files | Imports renderer (with_sentinel_body) and yaml; that is allowed because agent_harness sits above rendering. Once N12 points _skill_writer at renderer, RS-1 drops the with_sentinel_body re-export (:26-30). |
| `harness/leaf_detectors.py` | agent_harness/leaf_detectors.py | move | now | N12 | 78 | 4 | none | Only importers inside the package plus tests. |
| `harness/manifest.py` | agent_harness/manifest.py | move | now | N12 | 266 | 12 | listed in PR 2 engine; its change landed in #47 (ef19a0a); no open ticket lists it | Before starting, run git diff origin/main...<open ticket branch> -- harness. Pinned in the docstrings at _toml.py:9 and tests/unit/test_toml.py:4, and at SPEC.md:3895. Manifest kinds and rule ids must not change (ADR 0001). |
| `harness/models.py` | agent_harness/models.py | move | now | N12 | 107 | 5 | none | Renaming class Harness to HarnessTree is not part of the move. It goes in AH-2 after the chain, because tests/adapters/test_agent_harness.py is #54's (verify-cost correction 1). It is cited in the docstring at commands/validate_harness.py:23. |
| `harness/parser.py` | agent_harness/parser.py | move | now | N12 | 219 | 3 | none | Imported by commands/import_harness.py:56 and validate_harness.py:47; cited in the docstring at validate_harness.py:18. |

### 4.7 `evals/`

CONTEXT: Eval task. `compile/`, `run/`, `checks/`. 22 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `commands/eval.py` | commands/eval.py (~255 lines) + evals/registry.py (eval.py:67-70, 233-264) + evals/report_format.py (eval.py:285-445) + commands/_eval_enumerate.py (eval.py:449-735) | split | after-chain | N11 | 735 | 4 | none | A verbatim split that brings it under budget. Functions that move into a new public module lose their underscore: load_runner_class, available_runner_names, load_judge_class, available_judge_names, task_result_to_dict, format_task_result_text. The entry-point group names coding_agent_playbook.runners and .judges (eval.py:67,70) move unchanged (L2). eval.py calls them through the module (`registry.load_judge_class`), because tests/cli/test_eval_run.py:261,352,464,495,510 monkeypatch them; those patches are retargeted to evals.registry. tests/cli/test_eval_aggregate_render.py:12 is rewritten. SPEC.md:2563 changes commands/eval.py:_display_source_path to commands/_eval_enumerate.py. The target's commands/eval/ package is dropped (§11 H6). The PluginRegistry and UnknownPluginError interface is not scheduled (L12). |
| `evals/__init__.py` | evals/__init__.py | stay | after-chain | N23 | 36 | 1 | none | PR N23 makes it docstring-only (L5). No src module imports names from the package (scan: 0 src importers); commands/validate.py and sources/filesystem.py import evals.loader, task and validator directly, so the chain files stay untouched. tests/unit/test_evals_package.py, which asserts the re-exports, is rewritten to import the defining modules. |
| `evals/_compile.py` | evals/compile/compiler.py | rename | after-chain | N23 | 619 | 5 | none | PR N23. Public inside compile/ because evals/task.py and evals/run/scoring.py import it from outside compile/ (L4 rule 2 applies per package). At 619 lines it is over the ~500 budget; the split (the default-expr rule once, iter_leaves) is a behaviour follow-up, not part of the move, recorded as not scheduled in AC.6 F-E1 with the budget exception. |
| `evals/_expr.py` | evals/compile/_expr.py | move | after-chain | N23 | 379 | 3 | none | PR N23. Stays private: its only src importer is the compiler. eval_bool (:323) is dead code with only test callers; deleting it is a follow-up. |
| `evals/_handles.py` | evals/compile/_handles.py | move | after-chain | N23 | 215 | 4 | none | PR N23. In N24 it gains the imports of evals/checks/{files,answer,aggregate} that register the eval check families, and it imports the gate and rubric registries from evals/compile/. |
| `evals/agent_env.py` | evals/run/agent_env.py | move | after-chain | N23 | 34 | 4 | none | PR N23. tests/hook_runtime/test_combine.py:16 imports UNATTENDED_ENV_VAR to pin it equal to the hook runtime's copy. |
| `evals/claude_code_runner.py` | evals/run/claude_code_runner.py | move | after-chain | N23 | 121 | 2 | none | PR N23. The value at pyproject.toml:79 is updated. Merging it with opencode_runner into one CliAgentRunner (the target's cli_runner.py) is deepening that L12 does not schedule. |
| `evals/fake_runner.py` | evals/run/fake_runner.py | move | after-chain | N23 | 79 | 6 | none | PR N23. The entry-point value at pyproject.toml:78 is updated; the group name 'coding_agent_playbook.runners' stays fixed (L2). |
| `evals/judge.py` | evals/judge.py | stay | now | — | 303 | 14 | none | The target keeps this path, so the judges entry point 'llm = coding_agent_playbook.evals.judge:LLMJudge' (pyproject.toml:85) is unchanged. |
| `evals/loader.py` | evals/loader.py | stay | after-chain | — | 62 | 13 | importer commands/validate.py (chain) | No move: the target keeps this path. hook_runtime/handlers/eval_task_authoring_lint.py:114 (lazily) and sources/filesystem.py also import it. |
| `evals/opencode_runner.py` | evals/run/opencode_runner.py | move | after-chain | N23 | 122 | 1 | none | PR N23. The value at pyproject.toml:80 is updated. |
| `evals/prompting.py` | evals/prompting.py | stay | after-chain | — | 308 | 6 | #54 rewrites it (spec P3.4.7, D22); tests/evals/test_prompting.py is also chain-touched | The target keeps this path. Its deepening is converging on RenderSession (RS-2, after the chain). N23 does not touch it: runner.py imports prompting, not the reverse, so the run/ move leaves it alone. |
| `evals/runner.py` | evals/run/harness_runner.py | move | after-chain | N23 | 503 | 17 | none | PR N23 moves the whole file. At 503 lines, the split into workspace.py and results.py (target layout) is a follow-up kept out of the move (the `as` re-export forms at :44-45 become plain imports in N23, 6.3.4), recorded as not scheduled in AC.6 F-E2 with the budget exception. 14 string pins ('coding_agent_playbook.evals.runner.subprocess.run' / '.shutil.which'): tests/cli/conftest.py:43,48; tests/integration/test_shipped_task_gates.py:117,119, test_modoboa_cmdi_fixture.py:36-37, test_shipped_eval_tasks_c7.py:75,77, test_crosscommitvuln_fixtures.py:166-167; tests/evaluators/test_eval_runner.py:950-1073. |
| `evals/scoring.py` | evals/run/scoring.py | move | after-chain | N23 | 340 | 6 | none | PR N23. B8 then removes its _IGNORED_DIRS, _iter_py_files and _availability_* copies. |
| `evals/task.py` | evals/task.py | stay | after-chain | — | 446 | 28 | importers commands/validate.py (chain: #52, #54, #59-#62) and evals/prompting.py (#54) | No move: the target keeps this path. N23 rewrites only its imports of evals._compile (:36, :232). Any later evals/task/ package waits for the chain. sources/filesystem.py:21 and _typing.py:23 import it; both are listed under contract_violations. |
| `evals/validator.py` | evals/validator.py | stay | after-chain | — | 223 | 7 | importer commands/validate.py (chain); tests/hook_runtime/test_import_budget.py:453 (#58) pins 'coding_agent_playbook.evals.validator' | No move. Its _AGGREGATE_METRICS and _AGGREGATE_OVER (:28-31) re-declare the aggregate vocabulary; folding them is a behaviour follow-up. |
| `evaluators/checks/aggregate.py` | evals/checks/aggregate.py | move | after-chain | N24 | 288 | 3 | none | PR N24. Eval-only (reads ctx.trials). Its _trial_boolean copy (:70-96) and the dead _compile.over_boolean are a behaviour follow-up (delete over_boolean, define the over-axis set once) and stay out of the move. |
| `evaluators/checks/answer.py` | evals/checks/answer.py | move | after-chain | N24 | 120 | 2 | none | PR N24. Eval-only (reads ctx.artifact). |
| `evaluators/checks/files.py` | evals/checks/files.py | move | after-chain | N24 | 210 | 6 | none | PR N24. Eval-only family (it reads ctx.tree and ctx.baseline_tree). It imports only kernel names, so evals -> grading is the legal direction. Its checks register when evals/compile/_handles.py imports it. evals/checks/__init__.py is new and docstring-only. |
| `evaluators/gates.py` | evals/compile/gate_registry.py | move | after-chain | N24 | 110 | 3 | none | PR N24. Not deleted: L2 fixes the coding_agent_playbook.gates entry-point group, and this module loads it. Its only src consumer is evals/_handles.py (the [gate.bind] ref shape), so it moves beside the compiler for locality. The new name ends the clash with the `gates` alias for metrics_gate (_metrics_pass.py:184, coverage_diff_gate.py:160,230). String pins: tests/evaluators/test_gate_registry.py:80,107. |
| `evaluators/rubrics.py` | evals/compile/rubric_registry.py | move | after-chain | N24 | 110 | 4 | none | PR N24. Same reasoning as gates.py: L2 keeps the coding_agent_playbook.rubrics group, evals/_handles.py is its only consumer, and rubric.py and rubrics.py differ by one letter. N24 also drops its 3 re-exports from evaluators/__init__.py. String pins: tests/evaluators/test_rubrics_registry.py:104,129. |
| `git_env.py` | evals/run/git_env.py | move | after-chain | N23 | 55 | 4 | none | PR N23. The root area may list it too; it is owned here because its target is evals/run/ (synthesize sequencing, wave 0 item 7). Importers: evals/runner.py:47, tests/conftest.py:26, tests/unit/test_git_env.py, tests/unit/test_hermetic_git_env.py. Folding its env-scrub list into hook_runtime's git module is not scheduled. |

### 4.8 `precommit.py`

The pre-commit template and text merge (root module). 2 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (new) precommit.py | precommit.py (from commands/init.py:336-439, incl. PrecommitTemplateMissingError, and all of commands/_precommit_merge.py, 127 lines) | merge-into | after-chain | N9 | 230 | 0 | none: init.py and _precommit_merge.py are not edited by #49-#62 (init edits were PR1, merged) | N9. cli's catch of PrecommitTemplateMissingError and commands/init.py import it from precommit. tests/unit/test_precommit_merge.py becomes tests/unit/test_precommit.py. The template stays at templates/precommit/ (commands/init.py:372, tests/_catalog.py:28). |
| `commands/_precommit_merge.py` | precommit.py (with init.py:337-439) | merge-into | after-chain | N9 | 127 | 2 | none | One root module for the pre-commit concept, about 245 lines: _PRECOMMIT_TEMPLATE_NAME, PrecommitTemplateMissingError, precommit_template_dir, _render_fresh_pre_commit and _write_pre_commit, plus the text merge. The template path is found through resources.files(ENGINE_PACKAGE) (init.py:372), so it is location-independent. init's _has_trailer_rows and _uses_commitizen stay in init.py, so precommit.py never imports a command; it receives booleans, matching the target's write_precommit_config signature in the follow-up. |

### 4.9 `adapters/`

CONTEXT: Adapter. `base.py` stays (L2). 21 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `adapters/__init__.py` | adapters/__init__.py | stay | after-chain | N13 (docstring) | — | 3 | none | Empty today. N13 adds a docstring (L5). The entry-point GROUP coding_agent_playbook.adapters stays (L2). adapters/registry.py (discover_adapters, installed_output_locations from orchestrator.py:271-327) joins this package in A5, not here. |
| `adapters/_claude_hooks.py` | adapters/claude_code/hooks.py | move | after-chain | A8 | 216 | 4 | PR 4 (#56/#57) | ClaudeHookEmitter: managed settings groups, launcher, heartbeat. Pinned at SPEC.md:1811. Imported by tests/unit/test_docs_lifecycle_hooks_cli.py:26 and test_docs_migration_hooks.py:23. Lands in A8. |
| `adapters/_destructive_native.py` | adapters/claude_code/_destructive_native.py | move | after-chain | A8 | 41 | 3 | none for the file; its only src importer, _claude_hooks.py:21, is PR 4 | A8 moves it unchanged, private beside its one importer claude_code/hooks.py. Merging the three row sources into claude_code/native_rows.py is not scheduled (L12). |
| `adapters/_json_edits.py` | adapters/claude_code/settings/_json_edits.py | move | after-chain | N13 | 341 | 3 | none | Splice planner, an internal seam of the settings merge. All its src importers move with it. Its module name is pinned in tests/unit/test_claude_settings.py:540. |
| `adapters/_json_spans.py` | adapters/claude_code/settings/_json_spans.py | move | after-chain | N13 | 312 | 5 | none | Strict span scanner, an internal seam that keeps its own tests (tests/unit/test_json_spans.py goes to tests/adapters/). Its module name is pinned in test_claude_settings.py:541. |
| `adapters/_overlay_native.py` | adapters/claude_code/_overlay_native.py | move | after-chain | A8 | 119 | 3 | none for the file; its importer _claude_hooks.py:22 is PR 4 | A8 moves it unchanged; the native_rows merge is not scheduled. tests/hooks/test_network_egress_guard.py:21 imports it (retargeted in A8). |
| `adapters/_prior_output.py` | adapters/skill_dirs/ownership.py | move | after-chain | A9 | 141 | 3 | none for the file; its src importers _skill_writer.py:80 and commands/sync.py:66 are chain files | Public because sync installs its ContextVar (sync.py:157). The lazy read of sources.filesystem at :110 keeps reading through FileSystemStateSource (config/files.py after N2). Injecting the prior Lockfile and retiring the ContextVar is sync-engine work, dropped by L12, so it is not scheduled. Pinned at SPEC.md:3913. Lands in A9. |
| `adapters/_secret_native.py` | adapters/claude_code/_secret_native.py | move | after-chain | A8 | 114 | 5 | none for the file; its importer _claude_hooks.py:27 is PR 4 | A8 moves it unchanged; the native_rows merge is not scheduled. Holds the JSON pointers the other two row modules import. tests/cli/test_sync_hook_outputs.py:24 imports it. |
| `adapters/_settings_drift.py` | adapters/claude_code/settings/drift.py | move | after-chain | N13 | 80 | 3 | none | Becomes public because commands/check.py:22 imports it. The move fixes that underscore violation. tests/unit/test_settings_drift.py goes to tests/adapters/. |
| `adapters/_settings_plan.py` | adapters/claude_code/settings/_plan.py | move | after-chain | N13 | 413 | 3 | none | Defines LAUNCHER_TOKEN and CLAUDE_SETTINGS_PATH (:41-43). A18 moves LAUNCHER_TOKEN and LAUNCHER_PATH to the stdlib leaf hooks/registrations/launcher.py (H15); moving CLAUDE_SETTINGS_PATH to claude_code/paths.py is not scheduled. Its name is pinned in tests/unit/test_canonical_json.py:14-15 and test_claude_settings.py:542. |
| `adapters/_skill_writer.py` | adapters/skill_dirs/writer.py | move | after-chain | A9 | 508 | 10 | named in the chain's touched list (task brief; PR 2 engine/PR 4) | Over the 500-line budget; the chain expects it to shrink to about 470. Public, because sync (sync.py:67, _sync_output.py:31) and validation (validate.py:57) import it. N12 already rewrites :82 to import with_sentinel_body from renderer instead of harness.emitter (same object). Docs pins: SPEC.md:18, :2012, :3916, :3922. Docstring pins: opencode_adapter.py:17, shared_skills_adapter.py:19, _prior_output.py:3, claude_code_adapter.py:14, commands/_output_blockers.py:24. Lands in A9. |
| `adapters/_where_guidance.py` | adapters/_where_guidance.py | stay | after-chain | — | 46 | 3 | added by #49, on main since `393b0a1` | WhereGuidanceBuffer, used by agents_md and the Claude Code adapter. It stays private to adapters/: claude_code/adapter.py is a descendant of adapters, so the underscore rule allows the import. The review's _rule_sections composer would absorb it, but that is a sync-engine-adjacent deepening and is not scheduled. tests/unit/test_where_guidance_buffer.py goes to tests/adapters/ in A9. |
| `adapters/agents_md_adapter.py` | adapters/agents_md.py | rename | after-chain | A9 | 152 | 10 | #57 (and PR 4 guardrail lines); #49 merged | Entry point pyproject.toml:60 value becomes coding_agent_playbook.adapters.agents_md:AgentsMdAdapter. Pinned at SPEC.md:1867. Lands in A9. |
| `adapters/base.py` | adapters/base.py | stay | now | — | 308 | 25 | PR 4 tickets (#56/#57, guardrail delivery); listed in pr3-pr4 TOUCHED FILES | External contract for out-of-tree adapters (L2). No move. Its test tests/unit/test_adapter_base.py moves to tests/adapters/ in A9. The seam additions (preflight, composite_outputs, public scanned_output_dirs, single-file stale rule, emit(SyncBatch)) belong to sync-engine, which L12 drops for now. |
| `adapters/claude_code_adapter.py` | adapters/claude_code/adapter.py | move | after-chain | A8 | 376 | 14 | #54, #56/#57 (#49, merged, added the import at :61) | L5 forbids exporting ClaudeCodeAdapter from claude_code/__init__, so the entry point pyproject.toml:61 value becomes coding_agent_playbook.adapters.claude_code.adapter:ClaudeCodeAdapter. Its name is pinned negatively in tests/adapters/test_claude_code_rules.py:96 and appears in SPEC.md:1864. commands/_sync_hooks.py:45 keeps importing it (a seam leak that sync-engine would fix; not a layers violation). Lands in A8. |
| `adapters/claude_rule_paths.py` | adapters/claude_code/paths.py | rename | after-chain | N13 | 41 | 4 | none for the file; importer claude_code_adapter.py:57 is a chain file | The stdlib leaf for Claude paths. Pinned in the closure test tests/adapters/test_claude_code_rules.py:94 and at SPEC.md:3865. _guard_config_protect.py:36 imports it, a hooks -> adapters edge once that module is in hooks/; GC-2 moves the protected-set assembly to sync/_protect.py in the same move, so no ignore line is needed. |
| `adapters/claude_settings.py` | adapters/claude_code/settings/managed_merge.py | move | after-chain | N13 | 375 | 12 | none for the file; importers claude_code_adapter.py:62, _claude_hooks.py:28, commands/_sync_hooks.py:49 and commands/sync.py:69 are chain files | The target put this interface (merge_managed_entries, write_settings, parse_settings, SettingsIO, SettingsMergeError) in settings/__init__. L5 forbids that, so it gets a distinctive module name. Its exact closure pin, tests/unit/test_claude_settings.py:524-543, is rewritten (the adapters, adapters.claude_code and adapters.claude_code.settings packages each appear). hook_registrations/claude.py:15 imports LAUNCHER_TOKEN from it, which becomes a hooks->adapters violation (temporary ignore). Pinned at SPEC.md:1811 and :3855. |
| `adapters/continue_adapter.py` | adapters/continue_.py | rename | after-chain | A9 | 93 | 9 | #54 | Trailing underscore because continue is a keyword. Entry point pyproject.toml:62 value becomes coding_agent_playbook.adapters.continue_:ContinueAdapter. Pinned at SPEC.md:1709 and :1863. Lands in A9. |
| `adapters/opencode_adapter.py` | adapters/opencode.py | rename | after-chain | A9 | 245 | 9 | #54 (PR 3); PR 4 per the touched list | Deviates from the target's opencode/ package. Under L5 a one-module package is only an extra path segment; claude_code/ earns its package with 11 modules. The planned home for hook_registrations/opencode.py shim planning cannot be adapters while renderer imports hook_registrations. Entry point pyproject.toml:63 value becomes coding_agent_playbook.adapters.opencode:OpenCodeAdapter. Pinned at SPEC.md:1865. Lands in A9. |
| `adapters/shared_skills_adapter.py` | adapters/shared_skills.py | rename | after-chain | A9 | 83 | 6 | PR 4 (#56, playbook-guardrails skill) | Entry point pyproject.toml:64 value becomes coding_agent_playbook.adapters.shared_skills:SharedSkillsAdapter; the adapter id shared_skills is unchanged. Pinned at SPEC.md:1866 and :3922. Lands in A9. |
| orchestrator.py (rest) | catalog/resolve.py (Collision, OverlayResolver, _resolve, _hook_collision) + catalog/source.py (engine_package_of) + artifacts/identity.py (artifact_id_of, _source_package, template_source) + adapters/registry.py (discover_adapters, installed_output_locations) + validation/context.py (SyncContext, _warn_deprecated_overlays, _resolve_hooks) | split | after-chain | A5 | 528 | 24 | 14 importers are in the chain (commands/_sync_*, render, sync, validate, evals/prompting, rule_registry and tests); destinations adapters/ and sync/ are after-chain | Harmonised (§11 H4, H11): SyncContext goes to validation/context.py, not sync/context.py: validation, check, render and eval import it, and sync sits above validation. template_source joins artifact_id_of in the stdlib leaf artifacts/identity.py, so rendering stops importing the sync context (rule_registry.py:19). _resolve_hooks stays with SyncContext (it needs hook_policy.split_hook_layers). The OverlayResolver defaults (merge_hook_layers, NO_HANDLER_SCHEMAS) keep catalog.resolve -> hooks as a named engine-layers ignore (catalog-layers is not scheduled). |

### 4.10 `rendering/`

CONTEXT: Renderer (after the chain). 3 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `prompt_rule_delivery.py` | rendering/prompt_rule_delivery.py | move | after-chain | RS-1 | 51 | 2 | #54 grows it (SkillReferenceIndex, spec 2901-2988) | Kept as a separate module: #65 split it out on purpose (verifier). |
| `renderer.py` | rendering/jinja.py (75-240: RULE_CALL_RE, build_environment, render_artifact_body, render_string, TemplateSecurityError, render_sandboxed) + rendering/formats.py (44-73, 78-94, 241-499: FORMAT_ALIASES, BUILTIN_FORMATS, with_sentinel_body, render_for and the per-harness transforms) + rendering/rule_registry.py (RuleRegistry protocol, 95-110) | split | after-chain | RS-1 | 499 | 37 | #54 edits it (spec §7.4.3, 3033-3091) | #54 edits it (spec §7.4.3). The SENTINEL re-export (:21-23) is already gone (N6). The formats/ per-harness registry is not scheduled; RenderSession is RS-2. |
| `rule_registry.py` | rendering/rule_registry.py | move | after-chain | RS-1 | 86 | 5 | #54 | — |

### 4.11 `hooks/`

The sync-time half of CONTEXT Hook (after the chain). 33 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_guard_config_allowlists.py` | hooks/guard_config/_tables_allowlists.py | move | after-chain | GC-2 | 79 | 1 | package touched: #58 edits guard_config.py and adds _guard_config_skills.py (spec 3699, 3720, 3924, 3937) | Private, per the target's _tables_* naming. |
| `_guard_config_detect.py` | hooks/guard_config/inputs.py (HookView, ApplicabilityRow, DetectInputs, applicability_rows) + hooks/guard_config/_tables_detect.py (facts_table, applicability_table and helpers) | move | after-chain | GC-2 | 196 | 1 | package touched by #58; the spec only cites this file (5054, 5135; PR7 already merged in #66) | Private. |
| `_guard_config_prompts.py` | hooks/guard_config/_tables_prompts.py | move | after-chain | GC-2 | 58 | 1 | package touched by #58 | Private. |
| `_guard_config_protect.py` | hooks/guard_config/inputs.py (ProtectedRow, ProtectInputs) + _tables_protect.py (protected_table) + resource_roots.py (resource_root_ids, resolve_resource_roots, _layer_dir) + sync/_protect.py (COMPOSITE_SINGLETONS, protected_rows, adapter_output_dirs and helpers) | split | after-chain | GC-2 | 282 | 2 | package touched by #58; its importer test tests/unit/test_guard_config.py is in the chain | Private. Its probe at tests/adapters/test_claude_code_rules.py:92-95 changes name. It imports adapters.claude_rule_paths (see contract_violations). |
| `_guard_config_quality.py` | hooks/guard_config/_tables_quality.py | move | after-chain | GC-2 | 117 | 4 | package touched by #58; importer commands/_sync_hooks.py is edited by #56/#58 | Private by target. Until GC-3, commands/_sync_hooks.py:37-42 imports it across the package line, so that edge goes on the allowlist. |
| `_guard_config_ruff.py` | hooks/guard_config/_tables_ruff.py (RuffSelection, read_project_ruff_selection, ruff_table, SAFE_FIX_ALLOWLIST, RUFF_CONFIG_FILES, :58-165) + hooks/guard_config/ruff_probe.py (ruff_candidate_codes and the probe, :167-344) | move | after-chain | GC-2 | 344 | 8 | package touched by #58; importer commands/_sync_hooks.py is in the chain | Private by target. The negative pin at tests/hook_runtime/test_import_budget.py:576 is renamed. commands/_sync_hook_local.py:38 imports it until GC-2 makes the ruff probe public (hooks/guard_config/ruff_probe.py). |
| `_guard_config_secrets.py` | hooks/guard_config/_tables_secrets.py | move | after-chain | GC-2 | 104 | 1 | package touched by #58 | Private. |
| _guard_config_skills.py (created by #58, not on main yet) | hooks/guard_config/_tables_skills.py | move | after-chain | GC-2 | — | 0 | created by #58 (spec 3924, about 50 lines) | Gets a row because it exists by the time the guard_config move runs. |
| `_guard_config_toolchain.py` | hooks/guard_config/_tables_toolchain.py | move | after-chain | GC-2 | 198 | 4 | package touched by #58; the derived-config mechanism is cited at spec 3699 | Private by target. commands/_sync_hooks.py imports it until GC-3. |
| `_guard_config_verify.py` | hooks/guard_config/_tables_verify.py | move | after-chain | GC-2 | 120 | 1 | package touched by #58 | Private. |
| `guard_config.py` | hooks/guard_config/compile.py (GuardConfigInputs, render_guard_config, serialize_guard_config, write_guard_config, SYNC_OUTPUT_LOCATIONS, HOOK_ARTIFACTS and helpers) + hooks/guard_config/_tables_precommit.py (precommit_hook_ids) + sync/_hook_scripts.py (CopiedScripts, copy_hook_scripts) | split | after-chain | GC-2 | 415 | 21 | #58 adds skill_globs to GuardConfigInputs and the derived table (spec 3720, 3937) | Harmonised (§11 H10): the designer's GC-2 file map (compile.py; the root mapper proposed writer.py). copy_hook_scripts needs adapters, so it leaves hooks/ for the sync side. #58 adds skill_globs to GuardConfigInputs and the derived table (spec 3720, 3937). Pinned at _ENGINE_PATHS (:99) and in SPEC §5.1. |
| `hook_policy/__init__.py` | hooks/__init__.py (docstring only; the re-exports dissolve into the defining modules) | split | after-chain | A17 | 138 | 63 | edited by #56 (exports guardrails_skill) | [A17] a 138-line re-export facade with 63 importers; each importer is rewritten to name the defining module |
| `hook_policy/_contract_handlers.py` | hooks/contract/_contract_handlers.py | move | after-chain | A17 | 177 | 3 | none | [A17] all its importers are in contract/ |
| `hook_policy/_findings.py` | hooks/contract/findings.py | rename | after-chain | A17 | 81 | 6 | #52's commands/_validate_skills reuses did_you_mean (spec:3171): a new cross-package private import | [A17] public, because commands/_validate_hooks.py:39 and the chain's _validate_skills import it |
| `hook_policy/advisory.py` | hooks/enforcement.py | merge-into | after-chain | A17 | 114 | 3 | edited by #56, #57 (GUARDRAIL_SUMMARY_MAX_CHARS, summary/line/section helpers) | [A17] tests/unit/test_docs_readme_hooks.py:35 imports ADAPTER_LABELS and enforcement_targets |
| `hook_policy/contract.py` | hooks/contract/contract.py | move | after-chain | A17 | 430 | 1 | cited by spec (:5133, :5338); tests/unit/test_hook_policy_contract.py is in #59-#62 | [A17] |
| `hook_policy/contract_set.py` | hooks/contract/contract_set.py | move | after-chain | A17 | 260 | 1 | none | [A17] |
| `hook_policy/effective.py` | hooks/resolution/effective.py | move | after-chain | A17 | 440 | 1 | edited by #55 (_linked_lint_codes passes rule.frontmatter.skill, spec:3389) | [A17] |
| hook_policy/guardrails_skill.py (new in #56) | hooks/guardrails_skill.py | move | after-chain | A17 | — | 0 | created by #56 (~90 lines) | not on main yet; it moves with A17 and stays its own module beside hooks/enforcement.py (it composes the guardrails skill text; enforcement classifies) |
| `hook_policy/handler_catalog.py` | hooks/contract/handler_catalog.py | move | after-chain | A17 | 343 | 5 | none | [A17] it reads the runtime registry (allowed: hooks import hook_runtime) |
| `hook_policy/labels.py` | hooks/enforcement.py | merge-into | after-chain | A17 | 73 | 1 | cited by spec (:5333); #62 flips skill-nudge's OpenCode label via HOOK.md data, no code edit | [A17] concatenated verbatim with advisory (73 + about 150 lines after the chain). The single adapter_label classifier and the guardrail vocabulary rename are not scheduled |
| `hook_policy/lint_codes.py` | hooks/resolution/lint_codes.py | move | after-chain | A17 | 76 | 2 | edited by #55 (linked_lint_config gains skill_id) | [A17] |
| `hook_policy/merge.py` | hooks/resolution/merge.py | move | after-chain | A17 | 279 | 5 | none | [A17] |
| `hook_policy/override_rules.py` | hooks/resolution/override_rules.py | move | after-chain | A17 | 142 | 3 | none | [A17] commands/_twin_policy.py:52 imports it |
| `hook_policy/resolved.py` | hooks/resolution/resolved.py | move | after-chain | A17 | 243 | 4 | edited by #55, #56 (guardrail_text property, spec:3515) | [A17] GC-4 types the record shape instead; delegating to HookRecord is not scheduled (GC-D6) |
| `hook_policy/tables.py` | hooks/resolution/tables.py | move | after-chain | A17 | 182 | 9 | cited by spec (:5335), no edit | [A17] it re-exports runtime tables (decision, event, policy, harness): hooks to public hook_runtime modules, which is allowed |
| `hook_registrations/__init__.py` | hooks/registrations/__init__.py (docstring only; the re-exports dissolve into the defining modules) | split | after-chain | A18 | 115 | 27 | its importers renderer.py, adapters/_claude_hooks.py, claude_code_adapter.py, opencode_adapter.py, commands/_sync_hooks.py and guard_config.py are all chain-edited | [A18] a 115-line facade with 27 importers |
| `hook_registrations/_templates.py` | hooks/registrations/_templates.py | move | after-chain | A18 | 49 | 4 | none | [A18] _TEMPLATE_DIR (:20) changes from ('templates','hook_shims') to ('hooks','registrations','templates') |
| `hook_registrations/claude.py` | hooks/registrations/claude.py | move | after-chain | A18 | 200 | 1 | none | [A18] Harmonised (§11 H15): LAUNCHER_TOKEN (adapters/_settings_plan.py:43) and LAUNCHER_PATH move to a new stdlib-only hooks/registrations/launcher.py, which claude.py and the Claude Code settings merge import; that ends the hooks -> adapters edge at :15 and keeps the settings merge's stdlib-only closure pin (test_claude_settings.py:524-543). |
| `hook_registrations/opencode.py` | hooks/registrations/opencode.py | move | after-chain | A18 | 273 | 1 | none | [A18] |
| `hook_registrations/plan.py` | hooks/registrations/plan.py | move | after-chain | A18 | 407 | 3 | none | [A18] |
| `hook_registrations/stop_gate.py` | hooks/registrations/stop_gate.py | move | after-chain | A18 | 313 | 2 | none | [A18] it moves whole; plan.py imports its timeout half. GC-2 moves the stop_gate_table half (:213) into hooks/guard_config/_tables_stop_gate.py |
| `templates/hook_shims/opencode_wire_port.py` | hooks/registrations/templates/opencode_wire_port.py | move | after-chain | A18 | 198 | 3 | none | [A18] a test oracle that stays beside the template it ports (spec C.7), imported as a namespace package (no __init__.py). claude-launch.sh and opencode-plugin.js move with it; templates/precommit/ stays. _TEMPLATE_DIR changes at hook_registrations/_templates.py:20. Harmonised (§11 H17): after the chain with the registrations (the root mapper had it now). |

### 4.12 `skills/`

CONTEXT: Skill, Member rule, Reference (after the chain). 3 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `adapters/_agent_skill_rules.py` | skills/naming.py | move | after-chain | A3 | 102 | 8 | no open ticket lists it (created by #42/#64, merged), but every src importer is a chain file: skill_document, skill_membership, commands/_sync_render, _sync_lockfile, _validate_skills, _validation, adapters/_skill_writer | Moves to the target layout's skills/naming.py (the Agent Skills naming standard) in A3. That move also clears the skills->adapters upward import (skill_document.py:23, skill_membership.py:18). Its exact import-closure pin, tests/adapters/test_agent_skill_rules.py:39-50, is rewritten in the same PR. A3 also drops the re-export ladder at _skill_writer.py:78-79 and the test that pins it (test_skill_writer_reexports_the_one_object_the_rules_module_defines): one spelling per name (L2). |
| `skill_document.py` | skills/document.py | move | after-chain | A3 | 330 | 9 | #49 wires where_guidance_section; importers adapters/_skill_writer.py and commands/_sync_render.py are in the chain | — |
| `skill_membership.py` | skills/membership.py | move | after-chain | A3 | 140 | 3 | #49 wires compose_skills and undelivered_member_warning | In the same PR, adapters/_agent_skill_rules.py (adapters/) moves to skills/naming.py, which removes the skills -> adapters private import. |

### 4.13 `metrics_gate/`

`playbook metrics` and the Stop-stage metrics call. 6 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `evaluators/_metrics_inputs.py` | metrics_gate/inputs.py | rename | now | N22 | 374 | 3 | none | PR N22. The underscore goes: hook_runtime/handlers/_metrics_pass.py:440 imports decode_source_blob from outside the package, so L4 rule (2) requires a public module (the target layout's inputs.py). This module holds the second file walk (IGNORED_DIRS :30, _iter_py_files :105) that B8's measuring.py absorbs. |
| `evaluators/_metrics_suite.py` | metrics_gate/suite.py | rename | now | N22 | 247 | 2 | none | PR N22. The underscore goes: hook_runtime/handlers/coverage_diff_gate.py:47 imports ProjectFactory from outside the package. |
| `evaluators/measurement_snapshot.py` | metrics_gate/snapshot.py | rename | now | N22 | 135 | 4 | none | PR N22. Gate-only: used by metrics_gate.py and hook_runtime/handlers/_coverage_report.py:164,181. It imports _atomic_io; if the root lane has already moved that to generated_output/atomic_io.py, the codemod rewrites to whichever path exists. |
| `evaluators/metrics_gate.py` | metrics_gate/run.py | move | now | N22 | 491 | 13 | none | PR N22. The gate's interface module: run_metrics_gate, MetricsGateRequest/Deps/Result, load_metrics_config, build_rubric. Named run.py so the import line reads metrics_gate.run; L5 forbids the __init__ re-exports the target layout listed. CONFIG_FILENAME at :94 stays until B2 folds it. In the same PR, tests/hook_runtime/test_import_budget_stop.py:30 _METRICS_GATE becomes 'coding_agent_playbook.metrics_gate.run'. |
| `evaluators/policy.py` | metrics_gate/policy.py | move | now | N22 | 269 | 11 | none | PR N22. No kernel module imports it (importers: metrics_gate, _metrics_pass, quality_metrics, tests). It moves whole as policy.py rather than the target's selection.py, because it holds METRIC_DEFAULTS and metric_check as well as selection. Moving the defaults onto Metric (grading-kernel part e) is a design question that L12 does not schedule. |
| `metrics_config.py` | metrics_gate/config.py | move | now | N22 | 247 | 4 | none | PR N22. Also receives class MetricConfig (with its ruff_settings property) from evaluators/types.py:280, which ends the types.py:322 <-> metrics_config lazy cycle; ruff_config_flags stays beside it. Harmonised (§11 H9): the root mapper proposed the opposite (ruff_config_flags into grading). config.py:34's parse_metrics_config re-export is already gone (N2). _guard_config_quality.py:74,98 import it, so metrics_gate sits below hooks (H5). |

### 4.14 `catalog/`

CONTEXT: Catalog, Layer, Core, Bundled plugin, Overlay. 6 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_layers.py` | catalog/layers.py | move | now | N3 | 16 | 4 | none | Public: hook_policy contract, contract_set and merge import it. Remove the ENGINE_PACKAGE/REPO_LOCAL_SOURCE re-export at sources/filesystem.py:16-17. The duplicate label definitions (catalog.py:34, evals/prompting.py:54-57, eval_task_authoring_lint.py:62, guard_generated_outputs.py:141) stay: catalog-layers is not scheduled (L12). |
| `catalog.py` | catalog/roots.py | move | now | N3 | 235 | 21 | none for the file; importers commands/_sync_preflight.py and init.py were edited only by merged PR1 | Stdlib-only. hook_runtime/protected.py:242 imports it lazily on the guard-generated-outputs path. So catalog/__init__ stays docstring-only and FORBIDDEN names catalog.source and catalog.resolve, not catalog. Its _PACKAGE_DIR (:42) is __file__-relative and gains one level (`.parents[1]`) in N3 (7.1.2 rule 11), else catalog_root() raises CatalogMissingError everywhere. |
| orchestrator.py (rest) | catalog/resolve.py (Collision, OverlayResolver, _resolve, _hook_collision) + catalog/source.py (engine_package_of) + artifacts/identity.py (artifact_id_of, _source_package, template_source) + adapters/registry.py (discover_adapters, installed_output_locations) + validation/context.py (SyncContext, _warn_deprecated_overlays, _resolve_hooks) | split | after-chain | A5 | 528 | 24 | 14 importers are in the chain (commands/_sync_*, render, sync, validate, evals/prompting, rule_registry and tests); destinations adapters/ and sync/ are after-chain | Harmonised (§11 H4, H11): SyncContext goes to validation/context.py, not sync/context.py: validation, check, render and eval import it, and sync sits above validation. template_source joins artifact_id_of in the stdlib leaf artifacts/identity.py, so rendering stops importing the sync context (rule_registry.py:19). _resolve_hooks stays with SyncContext (it needs hook_policy.split_hook_layers). The OverlayResolver defaults (merge_hook_layers, NO_HANDLER_SCHEMAS) keep catalog.resolve -> hooks as a named engine-layers ignore (catalog-layers is not scheduled). |
| `sources/_hook_walk.py` | catalog/_hook_walk.py | move | now | N3 | 111 | 1 | none | Private within catalog. |
| `sources/base.py` | catalog/source.py (ArtifactSource, :30-76) + config/files.py (StateSource, :77-135) | split | now | N2, N3 | 135 | 5 | none for the file | The StateSource half moves in N2, the ArtifactSource half in N3. The StateSource ABC is kept because L2 freezes the state_sources entry-point group name, which overrides the config-files plan to delete the group. The group's value keeps naming FileSystemStateSource. |
| `sources/filesystem.py` | catalog/source.py (FileSystemArtifactSource :229-385 + helpers :62-160, :220-228) + config/files.py (FileSystemStateSource :387-550, _deep_merge :40-60, _atomic_write_text :162-172, _read_config_file/_decode_config_file :174-218) | split | now | N2, N3 | 550 | 47 | file untouched (spec 870-871); 16 importers are in the chain; tests/unit/test_sources_filesystem_bundled.py is edited by #50/#56 | Estimated sizes: catalog/source.py about 420 lines, config/files.py about 300. After the split, catalog/source.py no longer imports config, which leaves only the catalog -> evals edge (list_eval_tasks). The pyproject.toml:70 and :73 values are updated. |

### 4.15 `config/`

The two consumer config files and their tables. 9 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_table_shapes.py` | config/tables/_table_shapes.py | move | now | N2 | 145 | 1 | none | Stays private: only config/tables/hooks.py imports it. The target names it public, but nothing outside config.tables needs it. The probe at tests/unit/test_hooks_config.py:377-385 becomes [config, config.tables, config.tables._table_shapes, config.tables.hooks]. |
| `commands/_committed_config.py` | config/committed.py | move | after-chain | N10 | 154 | 3 | none | Harmonised (§11 H13): its own module, not merged into config/files.py, which B2 grows. Importers check.py:23, init.py:26 and tests/unit/test_committed_config.py, whose AST guard (_HOME, _WRITERS_HOME at :230-232; :312-313) changes in the same commit. SPEC.md:15, 2251, 2394 and 3890. The private reads of FileSystemStateSource._CONFIG_FILENAME (check.py:246, init.py:316/568) go with B2. |
| `config.py` | config/model.py | move | now | N2 | 286 | 19 | none for the file; importer orchestrator.py is not edited by remaining tickets | Holds Config, ProjectMeta, StorageConfig, OutputConfig, check_config_file and parse_output_config. The re-exports at config.py:26-34 go (L2): ConfigError moves to config.schema, HooksConfig and parse_* to config.tables.hooks, and parse_metrics_config's importer (evaluators/metrics_gate.py:44) points at metrics_config. parse_links_config (:237-255) moves to config/tables/links.py. Same-name module-to-package conversion. |
| `config_entries.py` | config/entries.py | move | now | N2 | 167 | 3 | none | — |
| `config_schema.py` | config/schema.py | move | now | N2 | 299 | 1 | none | Home of ConfigError. Its many importers today reach it through config.py's re-export and are rewritten by name. |
| `hooks_config.py` | config/tables/hooks.py | move | now | N2 | 378 | 39 | file untouched; 13 importers are in the chain (adapters/_claude_hooks, base, claude_code_adapter, commands/_sync_hooks, _sync_lockfile, guard_config, hook_policy/effective and tests) | Light path: hook_policy and catalog/source import it. config/__init__ and config/tables/__init__ stay docstring-only. Pinned at _ENGINE_PATHS (:100) and in SPEC §5.1. |
| links.py (LinksConfig, :41-62) | config/tables/links.py (together with parse_links_config from config.py:237-255) | split | now | N2 | 211 | 7 | none | Removes the lazy config -> links import (config.py:39, :250). |
| `sources/base.py` | catalog/source.py (ArtifactSource, :30-76) + config/files.py (StateSource, :77-135) | split | now | N2, N3 | 135 | 5 | none for the file | The StateSource half moves in N2, the ArtifactSource half in N3. The StateSource ABC is kept because L2 freezes the state_sources entry-point group name, which overrides the config-files plan to delete the group. The group's value keeps naming FileSystemStateSource. |
| `sources/filesystem.py` | catalog/source.py (FileSystemArtifactSource :229-385 + helpers :62-160, :220-228) + config/files.py (FileSystemStateSource :387-550, _deep_merge :40-60, _atomic_write_text :162-172, _read_config_file/_decode_config_file :174-218) | split | now | N2, N3 | 550 | 47 | file untouched (spec 870-871); 16 importers are in the chain; tests/unit/test_sources_filesystem_bundled.py is edited by #50/#56 | Estimated sizes: catalog/source.py about 420 lines, config/files.py about 300. After the split, catalog/source.py no longer imports config, which leaves only the catalog -> evals edge (list_eval_tasks). The pyproject.toml:70 and :73 values are updated. |

### 4.16 `detector/`

CONTEXT: Detector, Detector fact. 4 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_pep503.py` | detector/pep503.py | move | now | N4 | 131 | 9 | none (detector edits from spec §11.2 merged in #66) | Kept in detector/ as the target says, against the verifier. It is imported at module level on the Bash pre_tool_use hot path (handlers/dependencies.py, _install_cmds.py, _dependency_tiers.py). That is cheap only because detector/__init__ is docstring-only (L5), and N4 replaces `_pep503` and `_pyproject_deps` in STDLIB_LEAVES with the dotted `detector.pep503` and `detector.pyproject_deps`, so T0.1's derived FORBIDDEN lists detector.facts and detector.predicate. 'packaging' stays forbidden and still catches the real cost. |
| `_pyproject_deps.py` | detector/pyproject_deps.py | move | now | N4 | 171 | 5 | none | Stdlib-only. Hot-path importers are handlers/_detector_inputs.py and _manifest_diff.py. |
| `detector.py` | detector/facts.py (lines 1-308: Facts, KNOWN_*, detect) + detector/predicate.py (304-454: evaluate_predicate and helpers) | split | now | N4 | 454 | 24 | none remaining (spec §11.2 landed in #66; tickets #59-#62 only cite line numbers); importers commands/render.py, validate.py, evals/prompting.py, rule_registry.py and hook_policy/effective.py are in the chain (import lines) | `from coding_agent_playbook import detector` at resync_on_detector_input_change.py:126,141 becomes `from coding_agent_playbook.detector import facts as detector`. Same-name module-to-package conversion. The empty-predicate guard cleanup is not scheduled (catalog-layers, L12). |
| orchestrator.py (filter_applies_if, :251-269) | detector/predicate.py | split | now | N4 | 19 | 3 | importers commands/_sync_hooks.py and _sync_render.py are in the chain (import lines only); orchestrator.py itself is not edited by #49-#62 (spec 868-871, 3115) | Part of the detector move. This is the piece L12 means by 'what the detector move needs'. evals/prompting.py:250-253 re-implements it, and RS-2 removes that copy (section 9 AC.3). |

### 4.17 `lockfile/`

CONTEXT: Lockfile. 3 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_canonical_json.py` | lockfile/canonical_json.py | move | now | N5 | 87 | 6 | none | Public: hook_runtime/handlers/_control_plane_json imports it on a hot path, which is allowed because lockfile is a hot-path leaf. Remove the re-export at adapters/_settings_plan.py:17 (L2: no shims) and rewrite its users. The exact-list probe in tests/unit/test_canonical_json.py:46-50 changes. |
| `_lock_drift.py` | lockfile/drift.py | move | now | N5 | 246 | 1 | none | Public. The drift_entries re-export in lockfile.py (docstring :17-21) is removed and its users import lockfile.drift. |
| `lockfile.py` | lockfile/model.py | move | now | N5 | 325 | 45 | file untouched; 15 importers are in the chain (adapters/_claude_hooks, base, claude_code_adapter, commands/_sync_hooks, _sync_lockfile, sync and 9 tests), so import-line conflicts | Must stay free of jinja and yaml (3 hook_runtime importers). load/save stays inside FileSystemStateSource (config/files.py) (a lockfile/files.py is not scheduled). _LOCKFILE_MODULE (test_import_budget.py:471) becomes lockfile.model. |

### 4.18 `grading/`

CONTEXT: Grading kernel (L6: was `evaluators/`). 35 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `evaluators/__init__.py` | grading/__init__.py | rename | after-chain | N25 | 69 | 14 | importer tests/hook_runtime/test_import_budget.py (#58) pins 'coding_agent_playbook.evaluators' at :64 and :462 | PR N25. Becomes docstring-only (L5) and its 24 re-exports go. The 5 src importers (commands/metrics.py:100, evals/runner.py:51, evals/scoring.py:47,60, _metrics_pass.py:184, coverage_diff_gate.py:160,230) and 9 tests import the defining module instead. Side effect: importing grading.paths no longer loads the metric registry, which is the reason paths.py's docstring gives for the hot-path ban. |
| `evaluators/baseline_git.py` | grading/baseline_git.py | move | after-chain | N25 | 336 | 9 | none | PR N25. The kernel needs it: types.py:25 (GitRunner in ToolSetup.git) and execution/git_diff.py:23. The gate-side BaselineGit users (metrics_gate.*, commands/metrics.py:85) import it downward. The name is kept to avoid churn on its 9 importers, tests/fakes.py among them. |
| `evaluators/builtins/__init__.py` | grading/static_metrics/__init__.py | rename | after-chain | N25 | 24 | 1 | none | PR N25. Docstring-only (L5); its 9 imports move into metric.py's explicit builtin list. The package is static_metrics/ rather than the target's metrics/static/, so grading/metric.py and a grading/metrics/ package do not sit side by side and one path segment goes. |
| `evaluators/builtins/cbo.py` | grading/static_metrics/cbo.py | move | after-chain | N25 | 118 | 1 | none | PR N25. |
| `evaluators/builtins/cyclomatic.py` | grading/static_metrics/cyclomatic.py | move | after-chain | N25 | 43 | 1 | none | PR N25. |
| `evaluators/builtins/dit.py` | grading/static_metrics/dit.py | move | after-chain | N25 | 65 | 1 | none | PR N25. |
| `evaluators/builtins/docstring_example.py` | grading/static_metrics/docstring_example.py | move | after-chain | N25 | 88 | 2 | none | PR N25. |
| `evaluators/builtins/file_sloc.py` | grading/static_metrics/file_sloc.py | move | after-chain | N25 | 57 | 2 | none | PR N25. The lazy radon import is unchanged. |
| `evaluators/builtins/lcom4.py` | grading/static_metrics/lcom4.py | move | after-chain | N25 | 117 | 1 | none | PR N25. |
| `evaluators/builtins/maintainability.py` | grading/static_metrics/maintainability.py | move | after-chain | N25 | 89 | 2 | none | PR N25. String pin: tests/evaluators/test_metric.py:324 '...evaluators.builtins.maintainability.importlib.util.find_spec'. |
| `evaluators/builtins/ruff_violations.py` | grading/static_metrics/ruff_violations.py | move | after-chain | N25 | 204 | 5 | importer hook_runtime/handlers/docstring_nonregression.py:139 (#55) | PR N25. _metrics_pass.py:43,416 and quality_metrics.py:145 also import it, lazily. |
| `evaluators/builtins/wmc.py` | grading/static_metrics/wmc.py | move | after-chain | N25 | 46 | 1 | none | PR N25. |
| `evaluators/check.py` | grading/check.py | move | after-chain | N25 | 430 | 37 | none | PR N25. _MetricCheck.available (:267) is what the B8 measuring-pass PR changes. |
| `evaluators/checks/compose.py` | grading/compose.py | move | after-chain | N25 | 252 | 11 | none | PR N25. Kernel module (AllOf/AnyOf/Not) used by rubric, scheduler and evals. It comes out of checks/, one path segment fewer (ADR 0002). |
| `evaluators/checks/execution.py` | grading/execution_checks.py | rename | after-chain | N25 | 78 | 3 | importer tests/unit/test_docs_migration_hooks.py:29 (PR 2 tickets #49-#53) | PR N25. Kernel check factories (CoverageCheck, TestsPassCheck), renamed so the name does not collide with the execution_metrics package. |
| `evaluators/checks/judge_metric.py` | grading/judge_metric.py | move | after-chain | N25 | 77 | 4 | none | PR N25. Stays in the kernel, against the target layout: checks/registry.py:88 imports JudgeMetric at module level for the threshold factory's judge= source. |
| `evaluators/checks/judged.py` | grading/judged.py | move | after-chain | N25 | 98 | 7 | none | PR N25. Stays in the kernel, against the target layout's evals/checks/: rubric.py imports JudgeCheck for weighted judged groups, so moving it to evals would make grading import evals. It moves to evals only with grading-kernel part (c), which folds JudgeLike into Judge and which L12 does not schedule. |
| `evaluators/checks/registry.py` | grading/check_registry.py | rename | after-chain | N25 | 216 | 9 | none | PR N25. 'registry.py' is a generic name (hook_runtime/registry.py, adapters/registry.py); check_registry greps to one place. It keeps the coding_agent_playbook.checks group (L2). _load_check_builtins (:156-163) imports grading.execution_checks explicitly instead of the checks package. String pins: tests/evaluators/test_check_registry.py:114,137. |
| `evaluators/execution/__init__.py` | grading/execution_metrics/__init__.py | rename | after-chain | N25 | 19 | 2 | none | PR N25. Docstring-only (L5); its 3 imports move into metric.py's explicit builtin list. |
| `evaluators/execution/coverage.py` | grading/execution_metrics/coverage.py | move | after-chain | N25 | 90 | 2 | none | PR N25. |
| `evaluators/execution/coverage_xml.py` | grading/execution_metrics/coverage_xml.py | move | after-chain | N25 | 141 | 8 | none | PR N25. tests/fakes.py:37 and tests/hooks/test_coverage_diff_gate.py import it. |
| `evaluators/execution/diff_coverage.py` | grading/execution_metrics/diff_coverage.py | move | after-chain | N25 | 247 | 5 | none | PR N25. hook_runtime/handlers/_coverage_report.py:28 imports it at module top; coverage_diff_gate.py:139,197 imports it lazily. |
| `evaluators/execution/git_diff.py` | grading/execution_metrics/git_diff.py | move | after-chain | N25 | 181 | 3 | none | PR N25. _coverage_report.py:29 imports every_line at module top. |
| `evaluators/execution/junit.py` | grading/execution_metrics/junit.py | move | after-chain | N25 | 87 | 5 | none | PR N25. |
| `evaluators/execution/project.py` | grading/execution_metrics/project.py | move | after-chain | N25 | 276 | 15 | none | PR N25. hook_runtime/stop/suite.py:32 imports ProjectHandle at module top, and hook_runtime/deps.py:27 imports it under TYPE_CHECKING. String pins: tests/evaluators/test_execution_project.py:113 and test_execution_evaluators.py:161 ('...execution.project.subprocess.run'). |
| `evaluators/execution/test_pass.py` | grading/execution_metrics/test_pass.py | move | after-chain | N25 | 73 | 2 | none | PR N25. |
| `evaluators/metric.py` | grading/metric.py | move | after-chain | N25 | 191 | 39 | none | PR N25. Lines :124-125 import the builtins and execution packages to fire @register_metric. With docstring-only __init__ files (L5), they become an explicit tuple of the 12 metric modules that metric.py imports, so the registry contents stay the same. String pins: tests/evaluators/test_metric.py:139,162 'coding_agent_playbook.evaluators.metric.metadata.entry_points'. |
| `evaluators/normalizer.py` | grading/normalizer.py | move | after-chain | N25 | 113 | 23 | none | PR N25. MIGRATION.md:756,766 name it as the import for out-of-tree metric authors. The L9 script rewrites those lines, and N25 adds one MIGRATION line saying the evaluators.* paths moved (no shim, L2). |
| `evaluators/parse.py` | grading/parse.py | move | after-chain | N25 | 208 | 22 | none | PR N25. It stays at the kernel root rather than under static metrics, where the target layout put it: types.py:26 (EvalContext.module: ModuleModel), metrics_gate inputs and the execution metrics all import it. |
| `evaluators/paths.py` | grading/paths.py | move | after-chain | N25 | 74 | 4 | none | PR N25. The target layout is wrong to put it in metrics_gate/: execution/diff_coverage.py:31, a kernel metric, imports is_test_path and matches_any_glob. Its imports of gate_scan, hook_runtime.globs and hook_runtime.handlers._eval_paths are contract exceptions owned by other lanes (see contract_violations). |
| `evaluators/rubric.py` | grading/rubric.py | move | after-chain | N25 | 330 | 12 | none | PR N25. It imports checks/judged.py for weighted judged groups, which is why judged stays in the kernel. |
| `evaluators/scheduler.py` | grading/scheduler.py | move | after-chain | N25 | 177 | 4 | none | PR N25. |
| `evaluators/scope.py` | grading/scope.py | move | after-chain | N25 | 51 | 47 | none | PR N25. hook_runtime/stop/stages.py:62-66 StageCost mirrors CostTier, and its docstring names evaluators.scope; tests/hook_runtime/test_stop_stages.py:11 pins the values equal. |
| `evaluators/tool_runner.py` | grading/tool_runner.py | move | after-chain | N25 | 93 | 6 | none | PR N25. The target layout is wrong to put it in metrics_gate/: the kernel imports it (builtins/ruff_violations.py:36, and types.py:28 for ToolSetup.runner), so a metrics_gate home would make grading import upward. |
| `evaluators/types.py` | grading/types.py | move | after-chain | N25 | 386 | 73 | importer hook_runtime/handlers/docstring_nonregression.py:41 (#55); importer tests/unit/test_docs_lifecycle_hooks_spec.py:25 (PR 2 tickets #49-#53; MetricConfig, rewritten in N22) | PR N25; MetricConfig leaves earlier, in N22. With 73 importers it is the largest. It stays one module: splitting it into report.py/context.py as the target layout shows is deepening that L12 does not schedule. JudgeLike, GradePolicy, ResolvedPolicy and TrialResult stay for now, since grading-kernel parts (c) and (d) are not scheduled. DEFAULT_RUFF_FAMILIES and DEFAULT_GIT_TIMEOUT_S stay too: RuffSettings and ToolSetup read them. |

### 4.19 `artifacts/`

CONTEXT: Rule, Prompt, Skill, Hook; stdlib-only path classes and globs. 7 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_hook_frontmatter.py` | artifacts/hook_frontmatter.py | move | after-chain | A1 | 120 | 2 | #57 adds the summary field (spec 3474, 3926) | Public. The HookFrontmatter re-export at types.py:27 is removed and importers are rewritten. The probe at tests/unit/test_hook_frontmatter_module.py:42-48 changes. |
| `_hook_schema.py` | artifacts/hook_schema.py | move | after-chain | A1 | 372 | 14 | #57 adds a TOP_KEYS entry and FieldReader.guardrail_summary (spec 3927); importers hook_policy/effective.py and resolved.py are in the chain | Public and stdlib-only: hook_policy loads it on a light path, pinned at tests/unit/test_hook_policy_tables.py:195-207. The re-exports at types.py:30-39 are removed. |
| `_member_reference.py` | artifacts/member_reference.py | move | after-chain | A1 | 89 | 12 | PR3/PR4 interface (#54 pointer lines use member_reference_path, spec 2882); importers adapters/_skill_writer.py, commands/_sync_lockfile.py and _validate_skills.py are in the chain | Goes to artifacts/ and not skills/, as the target says, because artifacts.skill.Skill.member_references imports it. skills/ sits above artifacts. |
| `hook_runtime/globs.py` | artifacts/path_globs.py | move | after-chain | A12 | 135 | 18 | #58's new skill_nudge imports it (spec 8.5.3 'imports only globs, decision, registry') | [A12] the target said config/globs, but this must be a leaf: metrics_gate.paths (evaluators/paths.py:27) and gate_weakening import it, and grading/metrics_gate sit below hook_runtime. It is the path-pattern grammar that rule globs, hook matchers and eval fixtures all use. It takes fold_key and FOLDING_PLATFORMS from paths.py:194 with it |
| `hook_runtime/handlers/_eval_paths.py` | artifacts/path_classes.py | rename | after-chain | N15 | 52 | 7 | soft: guard_config.py:106 (#58) import-line rewrite | [N15] it must be a leaf, because grading (evaluators/types.py:19), metrics_gate (evaluators/paths.py:28), the gate_weakening judge and guard_config import FIXTURE_GLOBS. gate_scan.TEST_PATH_GLOBS (:74) joins it. It creates artifacts/ before A1 (stdlib-only, re only) |
| orchestrator.py (rest) | catalog/resolve.py (Collision, OverlayResolver, _resolve, _hook_collision) + catalog/source.py (engine_package_of) + artifacts/identity.py (artifact_id_of, _source_package, template_source) + adapters/registry.py (discover_adapters, installed_output_locations) + validation/context.py (SyncContext, _warn_deprecated_overlays, _resolve_hooks) | split | after-chain | A5 | 528 | 24 | 14 importers are in the chain (commands/_sync_*, render, sync, validate, evals/prompting, rule_registry and tests); destinations adapters/ and sync/ are after-chain | Harmonised (§11 H4, H11): SyncContext goes to validation/context.py, not sync/context.py: validation, check, render and eval import it, and sync sits above validation. template_source joins artifact_id_of in the stdlib leaf artifacts/identity.py, so rendering stops importing the sync context (rule_registry.py:19). _resolve_hooks stays with SyncContext (it needs hook_policy.split_hook_layers). The OverlayResolver defaults (merge_hook_layers, NO_HANDLER_SCHEMAS) keep catalog.resolve -> hooks as a named engine-layers ignore (catalog-layers is not scheduled). |
| `types.py` | artifacts/frontmatter.py (44-77: split_frontmatter, format_frontmatter, _without_empty, _read_markdown) + artifacts/rule.py (78-160) + artifacts/prompt.py (161-245) + artifacts/skill.py (246-321) + artifacts/hook.py (322-416) | split | after-chain | A2 | 416 | 111 | the artifacts/ package is touched by #57 (_hook_schema/_hook_frontmatter); 54 of the 111 importers are in the chain | The largest codemod in the reorganisation, done by name: each `from ...types import A, B` is split by destination module, and the hook_schema re-exports (:30-39) are dropped. Skill.id and the other catalog-layers work are not scheduled (L12). |

### 4.20 `generated_output/`

CONTEXT: Generated output (L10). 9 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_atomic_io.py` | generated_output/atomic_io.py | move | now | N6 | 51 | 5 | none for the file; its importer gitignore.py was edited only by merged PR1 (#68) | Public: imported by adapters/claude_settings, evaluators/measurement_snapshot and config/files.py (from sources/filesystem). |
| `_file_identity.py` | generated_output/file_identity.py | move | now | N6 | 80 | 6 | file untouched; importers adapters/base.py, opencode_adapter.py and agent_harness_adapter.py are edited by #49/#54/#56/#57 (import-line conflicts only) | Public. |
| `_output_io.py` | generated_output/output_io.py | move | now | N6 | 136 | 15 | file untouched; 8 importers are in the chain (agent_harness, agents_md, claude_code, continue and opencode adapters, commands/_sync_hooks.py, guard_config.py, harness/manifest.py), so import-line conflicts | Public. The exact-list probe at tests/unit/test_claude_settings.py:526-544 changes. |
| `_sentinel.py` | generated_output/sentinel.py | move | now | N6 | 175 | 34 | file untouched; importers adapters/_skill_writer, agents_md, base, claude_code, renderer.py, guard_config.py and commands/import_harness.py are in the chain (import lines) | Public. It is a hot-path leaf (hook_runtime/protected.py, handlers/_drift). Remove the test-only SENTINEL re-export at renderer.py:21-23. Pinned at _ENGINE_PATHS (tests/unit/test_docs_lifecycle_hooks_spec.py:101) and by the probe at tests/unit/test_sentinel.py:53-66. |
| `_symlinks.py` | generated_output/symlinks.py | move | now | N6 | 80 | 9 | file untouched; importers adapters/_skill_writer, opencode_adapter and commands/sync.py are in the chain | Public. |
| `adapters/_owned_files.py` | generated_output/write_guard.py | move | after-chain | A7 | 202 | 9 | none for the file; its src importers _claude_hooks.py:26, claude_code_adapter.py:49, opencode_adapter.py:51, commands/sync.py:65 and commands/_sync_hooks.py:44 are chain files | Uses the L10 package name, per the target's owned_output list. The stem is write_guard, not owned_files: CONTEXT.md lists 'owned file' under Avoid for Generated output, and the module holds the guard every engine write passes (check_engine_owned, check_unlinked, write_engine_owned, UserOwnedFileError). It becomes public because sync imports it, which fixes today's underscore violations at sync.py:65 and _sync_hooks.py:44. Lands in A7, after N6 created generated_output/ with _sentinel, _file_identity, _atomic_io, _output_io, _symlinks and gitignore. Pinned at SPEC.md:1807, SPEC.md:1825 and the docstring at commands/_sync_hooks.py:20. tests/adapters/test_owned_files.py goes to tests/generated_output/. |
| `adapters/_skill_files.py` | generated_output/source_files.py | merge-into | after-chain | A7 | 63 | 4 | no open ticket (last changed by #43, merged); merged with _skill_sources, whose importers are chain files | Deviates from the target's adapters/skill_dirs/source_files.py. The rule 'which files under a source subtree may be copied into generated output (skip bytecode, refuse secrets and escaping links)' is also used by hooks/guard_config for hook scripts (guard_config.py:92, :373) and by commands/_import_files.py:14. hooks sits below adapters, so the rule must live in the generated_output leaf. Lands in A7 as a mechanical concatenation (H8). Pinned at SPEC.md:2016; cross-referenced in the docstrings at _skill_sources.py:7 and _skill_writer.py:13. |
| `adapters/_skill_sources.py` | generated_output/source_files.py | move | after-chain | A7 | 110 | 6 | none for the file; its src importers _skill_writer.py:81, agent_harness_adapter.py:47, commands/validate.py:56 and guard_config.py:92 are chain files (#54, PR 4, #52) | Public in generated_output/ (see _skill_files for why). This fixes the hooks->adapters violation at guard_config.py:92, the underscore violations at commands/validate.py:56 and guard_config.py:92, and lets agent_harness import it. Its Skill import (:33) is TYPE_CHECKING only, but TYPE_CHECKING imports count (D0-8), so generated_output imports artifacts (allowed: generated_output sits above artifacts in the leaf tier, 3.2) and source_files.py is not a stdlib leaf; that is why N6 admits only the dotted leaves generated_output.atomic_io and generated_output.sentinel. generated_output may import security (security/files.py imports nothing from the output leaves). Pinned at SPEC.md:2015. tests/adapters/test_skill_sources.py goes to tests/generated_output/. |
| `gitignore.py` | generated_output/gitignore.py | move | now | N6 | 367 | 8 | none remaining (PR1 edits merged in #68) | The managed .gitignore block. |

### 4.21 `security/`

Stdlib-only judges with no runtime dependency, and the trust store. 11 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `security/__init__.py` | security/__init__.py | stay | now | — | 7 | 0 | none | already docstring-only; a stdlib-only leaf that hosts only judges with no runtime dependency, plus the trust store |
| `security/_pii_checksums.py` | security/_pii_checksums.py | stay | now | — | 158 | 1 | none | — |
| `security/_regex_shape.py` | security/_regex_shape.py | stay | now | — | 66 | 2 | none | — |
| `security/commit_trailers.py` | security/commit_trailers.py | stay | now | — | 198 | 4 | none | a stdlib-only judge shared by the git-policy guard and check-commit-trailers |
| `security/files.py` | security/files.py | stay | now | — | 55 | 12 | adapters/base.py (#49-#58) imports it; no move | — |
| `security/paths.py` | security/paths.py | stay | now | — | 230 | 12 | none | — |
| `security/patterns.py` | security/patterns.py | stay | now | — | 265 | 14 | tests/adapters/test_claude_code_hooks.py (#56) imports it; no move | DESTRUCTIVE_NATIVE_PREFIXES (:252) stays here as the one shared list (adapters/_destructive_native.py and the safety judge) |
| `security/pii.py` | security/pii.py | stay | now | — | 442 | 9 | none | — |
| `security/pii_findings.py` | security/pii_findings.py | stay | now | — | 92 | 2 | none | — |
| `security/secrets.py` | security/secrets.py | stay | now | — | 380 | 14 | none | — |
| `security/trust.py` | security/trust.py | stay | now | — | 365 | 14 | none | used by both sync (commands/_sync_hook_local) and the runtime |

### 4.22 `toml_writer.py`

The TOML writer (root module, was `_toml.py`). 1 row.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_toml.py` | toml_writer.py | rename | now | N1 | 361 | 9 | none (the harness/manifest.py edit was #69, merged) | A public root leaf. This is the smallest move, so it goes first as the pilot of the T0.0 rewrite script. Docstring references to sources/filesystem.py at :7, :30, :282 and :291 are reworded. |

### 4.23 `_plugin_registry.py`

Not scheduled. 1 row.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| (new) _plugin_registry.py | _plugin_registry.py (not scheduled) | — | after-chain | not scheduled | — | 0 | none | Harmonised (§11 H12): not scheduled (L12 split grading-kernel part (f) off). Under the private-modules contract a root-level underscore module is engine-private, so grading, evals and metrics_gate may import it; the target-layout name stays. |

### 4.24 `hook_runtime/`

The hook runtime, a separate stack (name fixed by L2). 178 rows.

#### `hook_runtime/ (root modules)`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/__init__.py` | hook_runtime/__init__.py | stay | now | — | 10 | 0 | none | already docstring-only; L2 fixes the package name (committed launchers run python -m coding_agent_playbook.hook_runtime). Its docstring line on the hot path's imports changes in N15/A12 |
| `hook_runtime/__main__.py` | hook_runtime/__main__.py | stay | now | — | 8 | 0 | none | L2 fixed entry: python -I -m coding_agent_playbook.hook_runtime; imports hook_runtime.cli |
| `hook_runtime/_ruff.py` | hook_runtime/ruff.py | rename | after-chain | A16 | 424 | 7 | cited by spec (:4099, :5766), no edit; imported by #55's _ruff_buckets/ruff_feedback | [A16] the target is silent here. It is the one ruff tool seam, shared by the feedback handlers, the lint stage and the sync-side ruff readers (_guard_config_ruff.py:30, _guard_config_quality.py:21). So it can be neither private nor owned by the handlers, and it stays a public root module |
| `hook_runtime/cli.py` | hook_runtime/cli.py | stay | now | — | 224 | 7 | none | L2 fixed: playbook-hook = hook_runtime.cli:main (pyproject.toml:53, tests/unit/test_entry_points.py:54) |

#### `hook_runtime/config/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_config_keys.py` | hook_runtime/config/keys.py | move | after-chain | N16 | 82 | 3 | soft: registry.py:27 (#58) import-line rewrite | [N16] public: _guard_config_secrets, hook_policy.handler_catalog and registry import it (an underscore violation today) |
| `hook_runtime/_config_reader.py` | hook_runtime/config/reader.py | move | after-chain | N16 | 151 | 13 | none | [N16] public: 12 src importers, including handlers and protected |
| `hook_runtime/_hook_records.py` | hook_runtime/config/hook_records.py | move | after-chain | N16 | 179 | 4 | none | [N16] public: dispatch._selection imports it; the single HookRecord home (to_json/from_json) waits until after the chain, because resolved.py is edited there |
| `hook_runtime/_lock_digest.py` | hook_runtime/config/lock_digest.py | move | after-chain | N16 | 145 | 5 | none | [N16] public: diagnostics and 2 handlers import it |
| `hook_runtime/config.py` | hook_runtime/config/guard_config.py | move | after-chain | N16 | 287 | 51 | soft: guard_config.py:101 (#58), ruff_feedback.py:73, _ruff_buckets.py:55 (#55), registry.py:35 (#58), tests/unit/test_guard_config.py:49 get import-line rewrites | [N16] load_guard_config/GuardConfig; B3's typed accessors (config/guard_tables.py) and GC-1's config/schema.py land beside it after the move (L13) |
| `hook_runtime/pin.py` | hook_runtime/config/pin.py | move | after-chain | N16 | 307 | 23 | none | [N16] test_import_budget.py:262 pins it |
| `hook_runtime/protected.py` | hook_runtime/config/protected.py | move | after-chain | N16 | 283 | 4 | none | [N16] the target said handlers/_shared, but config/ fits better because B3 reads its table through GuardTables.protected(); test_import_budget.py:214 pins it |

#### `hook_runtime/diagnostics/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_doctor_checks.py` | hook_runtime/diagnostics/_doctor_checks.py | move | after-chain | N20 | 256 | 4 | none | [N20] |
| `hook_runtime/_doctor_decisions.py` | hook_runtime/diagnostics/_doctor_decisions.py | move | after-chain | N20 | 49 | 1 | none | [N20] folding it into a state/decision_log is not scheduled |
| `hook_runtime/_doctor_opencode.py` | hook_runtime/diagnostics/_doctor_opencode.py | move | after-chain | N20 | 231 | 4 | none | [N20] tests/unit/test_docs_lifecycle_hooks_cli.py:48 and test_docs_readme_hooks.py:37 import OPENCODE_MIN_VERSION from it (tests are outside the contract) |
| `hook_runtime/canary.py` | hook_runtime/diagnostics/canary.py | move | after-chain | N20 | 202 | 5 | none | [N20] |
| `hook_runtime/doctor.py` | hook_runtime/diagnostics/doctor.py | move | after-chain | N20 | 154 | 3 | none | [N20] |
| `hook_runtime/heartbeat.py` | hook_runtime/diagnostics/heartbeat.py | move | after-chain | N20 | 51 | 3 | none | [N20] |
| `hook_runtime/simulate.py` | hook_runtime/diagnostics/simulate.py | move | after-chain | N20 | 274 | 45 | soft: 4 chain hook tests (test_ruff_feedback, typing/pytest lint feedback, docstring) get import-line rewrites | [N20] about 43 tests/hooks files import it directly; the ci.yml:54 comment cites tests/hook_runtime/test_simulate.py |

#### `hook_runtime/dispatch/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_decision_log.py` | hook_runtime/dispatch/_decision_log.py | move | after-chain | A11 | 201 | 4 | none | [A11] it builds log lines from execution records (_execute), so it stays with dispatch for the move. A merge into state/decision_log with record(trace) and summarize(state_dir, since) is not scheduled |
| `hook_runtime/_event_memo.py` | hook_runtime/dispatch/event_memo.py | move | after-chain | A11 | 47 | 4 | none | [A11] public: the ruff seam imports it |
| `hook_runtime/_execute.py` | hook_runtime/dispatch/_execute.py | move | after-chain | A11 | 227 | 4 | none | [A11] |
| `hook_runtime/_external.py` | hook_runtime/dispatch/external.py | move | after-chain | A11 | 283 | 5 | none | [A11] public: diagnostics and handlers._briefing_probes import it |
| `hook_runtime/_faults.py` | hook_runtime/dispatch/_faults.py | move | after-chain | A11 | 163 | 2 | none | [A11] |
| `hook_runtime/_pipeline.py` | hook_runtime/dispatch/_pipeline.py | move | after-chain | A11 | 306 | 1 | none | [A11] |
| `hook_runtime/_ports.py` | hook_runtime/dispatch/ports.py | move | after-chain | A11 | 169 | 9 | none | [A11] public: diagnostics and 3 handlers import it |
| `hook_runtime/_post_write.py` | hook_runtime/dispatch/_post_write.py | move | after-chain | A11 | 189 | 1 | none | [A11] |
| `hook_runtime/_prefilter.py` | hook_runtime/dispatch/prefilter.py | move | after-chain | A11 | 84 | 3 | none | [A11] public: handlers.destructive imports argv0_matches |
| `hook_runtime/_selection.py` | hook_runtime/dispatch/selection.py | move | after-chain | A11 | 250 | 6 | none | [A11] public: handlers._ruff_pipeline and stop_ci_parity_gate import it |
| `hook_runtime/_tail.py` | hook_runtime/dispatch/tail.py | move | after-chain | A11 | 116 | 3 | none | [A11] public: diagnostics.simulate imports it |
| `hook_runtime/caps.py` | hook_runtime/dispatch/caps.py | move | after-chain | A10 | 159 | 56 | none | [A10] public: commands.check_notebooks and the gate_weakening judge import clean_text/clip |
| `hook_runtime/combine.py` | hook_runtime/dispatch/combine.py | move | after-chain | A11 | 221 | 3 | cited by spec 8.5.3 (combine.py:167-183), no edit | [A11] |
| `hook_runtime/decision.py` | hook_runtime/dispatch/decision.py | move | after-chain | A10 | 153 | 127 | #58's new skill_nudge imports it | [A10] out-of-tree handlers import HandlerResult/Decision from here |
| `hook_runtime/deps.py` | hook_runtime/dispatch/deps.py | move | after-chain | A11 | 186 | 94 | none | [A11] RuntimeDeps; most of the 94 importers are tests (both conftests) |
| `hook_runtime/dispatch.py` | hook_runtime/dispatch/run.py | rename | after-chain | A10 | 276 | 8 | none | [A10] moves in the PR that creates the dispatch/ package: a package directory shadows the same-name module, so `from coding_agent_playbook.hook_runtime.dispatch import run_event` (hook_runtime/cli.py:196, canary.py:29, simulate.py:38) would fail if dispatch.py outlived A10 (7.1.2 rule 5). dispatch/dispatch.py would stutter. test_import_budget.py:168 asserts 'hook_runtime.dispatch' is imported, which would pass vacuously on the package; A10 changes it to dispatch.run |
| `hook_runtime/escape.py` | hook_runtime/dispatch/escape.py | move | after-chain | A11 | 245 | 19 | none | [A11] |
| `hook_runtime/event.py` | hook_runtime/dispatch/event.py | move | after-chain | A10 | 291 | 172 | soft: test_import_budget.py:38 (#58); 5 chain-edited handlers/tests import it | [A10] the target is silent here; the canonical event is the dispatcher's input type. Out-of-tree handlers import CanonicalEvent from here |
| `hook_runtime/paths.py` | hook_runtime/dispatch/paths.py | move | after-chain | A10 | 275 | 51 | cited by spec 8.5.3 (paths.py:117-153); #58's skill_nudge uses NormalizedPath | [A10] the target is silent here; NormalizedPath is a field type of the event. fold_key/FOLDING_PLATFORMS leave with globs in A12 |
| `hook_runtime/policy.py` | hook_runtime/dispatch/policy.py | move | after-chain | A10 | 164 | 19 | none | [A10] the failure-policy tables; hook_policy.tables and hook_registrations.plan import it |
| `hook_runtime/proc.py` | hook_runtime/dispatch/proc.py | move | after-chain | A11 | 154 | 36 | soft: test_import_budget.py:46 (#58) | [A11] the one process seam; commands._git_base, _guard_config_ruff and git/ import it |
| `hook_runtime/registry.py` | hook_runtime/dispatch/registry.py | move | after-chain | A11 | 436 | 84 | edited by #58 (one _BUILTIN_HANDLER_MODULES row for skill_nudge) | [A11] holds _BUILTIN_HANDLER_MODULES. Out-of-tree handlers import register_hook_handler/HandlerContext from here, and L2 does not pin it, so it moves; A11 adds it to A10's MIGRATION.md entry for handler authors |
| `hook_runtime/routing.py` | hook_runtime/dispatch/routing.py | move | after-chain | A11 | 86 | 4 | none | [A11] guard_config.py:108 and hook_registrations.plan import it |
| `hook_runtime/watchdog.py` | hook_runtime/dispatch/watchdog.py | move | after-chain | A11 | 129 | 4 | none | [A11] |

#### `hook_runtime/git/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_git_argv.py` | hook_runtime/git/_argv.py | move | after-chain | N18 | 100 | 2 | none | [N18] merging git_env.py's scrub list into this one is not scheduled |
| `hook_runtime/_git_cache.py` | hook_runtime/git/_cache.py | move | after-chain | N18 | 188 | 1 | none | [N18] |
| `hook_runtime/_git_fingerprint.py` | hook_runtime/git/_fingerprint.py | move | after-chain | N18 | 174 | 2 | none | [N18] |
| `hook_runtime/_git_memo.py` | hook_runtime/git/memo.py | move | after-chain | N18 | 98 | 2 | none | [N18] public: dispatch._ports imports it |
| `hook_runtime/_git_parse.py` | hook_runtime/git/parse.py | move | after-chain | N18 | 239 | 18 | soft: tests/hooks/test_docstring_nonregression.py:16 (#55) import-line rewrite | [N18] public: commands._secret_scope, check_notebooks, scan_sinks and gate_scan import it (an underscore violation today) |
| `hook_runtime/_head_snapshot.py` | hook_runtime/git/head_snapshot.py | move | after-chain | N18 | 105 | 2 | none | [N18] the target places it in git/; public because handlers.subagent_verify imports it |
| `hook_runtime/git.py` | hook_runtime/git/safe_git.py | move | after-chain | N18 | 298 | 49 | soft: registry.py:40 (#58) import-line rewrite; test_import_budget.py (#58) constants | [N18] SafeGit/GitPort; imported by 10 commands and gate_scan; test_import_budget pins it 5 times |
| `hook_runtime/git_log.py` | hook_runtime/git/log.py | move | after-chain | N18 | 104 | 3 | none | [N18] |
| `hook_runtime/git_range.py` | hook_runtime/git/range.py | move | after-chain | N18 | 292 | 5 | none | [N18] |

#### `hook_runtime/handlers/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/handlers/__init__.py` | hook_runtime/handlers/__init__.py | stay | now | — | 9 | 1 | none | already docstring-only; the new pack sub-packages (audit, feedback, protect, safety, verify, _shared) get docstring-only __init__ files |

#### `hook_runtime/handlers/_shared/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/edit_preview.py` | hook_runtime/handlers/_shared/edit_preview.py | move | after-chain | A14 | 89 | 6 | none | [A14] used by 5 handlers in 4 packs |
| `hook_runtime/handlers/_control_plane_paths.py` | hook_runtime/handlers/_shared/control_plane_paths.py | rename | after-chain | A14 | 285 | 4 | cited by spec (:222), no edit | [A14] it is used by both the protect and safety packs (taint). GC-1 first moves the constants guard_config.py:102 takes from it |
| `hook_runtime/handlers/_control_plane_text.py` | hook_runtime/handlers/_shared/control_plane_text.py | rename | after-chain | A14 | 107 | 5 | none | [A14] it is used by both the protect and verify packs (_metrics_pass). GC-1 first moves the constants guard_config.py:103 takes from it to config/schema.py |
| `hook_runtime/handlers/_control_plane_toml.py` | hook_runtime/handlers/_shared/control_plane_toml.py | rename | after-chain | A14 | 201 | 4 | none | [A14] it goes to _shared because _shared/control_plane_paths imports it (:37); in protect/ it would be a private-module violation |
| `hook_runtime/handlers/_pii_settings.py` | hook_runtime/handlers/_shared/pii_settings.py | rename | after-chain | A14 | 48 | 3 | none | [A14] it is used by both the audit and safety packs |
| `hook_runtime/handlers/_ruff_pipeline.py` | hook_runtime/handlers/_shared/ruff_pipeline.py | rename | after-chain | A14 | 431 | 3 | imported by #55's _ruff_buckets/ruff_feedback | [A14] it is used by both the feedback and verify packs (_metrics_pass). test_import_budget.py:539 pins it |
| `hook_runtime/handlers/_targets.py` | hook_runtime/handlers/_shared/targets.py | rename | after-chain | A14 | 109 | 12 | none | [A14] used by 12 handlers in 4 packs |

#### `hook_runtime/handlers/audit/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/handlers/_activity_record.py` | hook_runtime/handlers/audit/_activity_record.py | move | after-chain | A15 | 297 | 2 | none | [A15] test_import_budget.py:774 pins it |
| `hook_runtime/handlers/_transcript_prompts.py` | hook_runtime/handlers/audit/_transcript_prompts.py | move | after-chain | A15 | 266 | 2 | none | [A15] |
| `hook_runtime/handlers/activity_log.py` | hook_runtime/handlers/audit/local_audit_log.py | rename | after-chain | A15 | 103 | 0 | none | [A15] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/compaction.py` | hook_runtime/handlers/audit/precompact_checkpoint.py | rename | after-chain | A15 | 277 | 1 | none | [A15] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/decision_log.py` | hook_runtime/handlers/audit/guard_decision_log.py | rename | after-chain | A15 | 37 | 0 | none | [A15] the value in the registry.py:69-124 map changes; the registry name stays |

#### `hook_runtime/handlers/feedback/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/handlers/_lint_ast.py` | hook_runtime/handlers/feedback/_lint_ast.py | move | after-chain | A16 | 150 | 2 | imported by #55's _ruff_buckets | [A16] |
| `hook_runtime/handlers/_ruff_buckets.py` | hook_runtime/handlers/feedback/_ruff_buckets.py | move | after-chain | A16 | 414 | 1 | edited by #55 (rule_label, rule_suffix, _skill_of) | [A16] |
| `hook_runtime/handlers/_sink_regex.py` | hook_runtime/handlers/feedback/_sink_regex.py | move | after-chain | A16 | 109 | 1 | none | [A16] |
| `hook_runtime/handlers/_sink_writes.py` | hook_runtime/handlers/feedback/_sink_writes.py | move | after-chain | A16 | 170 | 2 | none | [A16] |
| `hook_runtime/handlers/deser.py` | hook_runtime/handlers/feedback/ml_unsafe_deserialization_guard.py | rename | after-chain | A16 | 195 | 3 | none | [A16] the value in the registry.py:69-124 map changes; the registry name stays. Twin commands/scan_sinks.py:33 imports this public module; N14 moves the scan names it re-exports and trusted_artifact_line to judges/sink_scan.py; extracting the rest of the sinks judge is not scheduled |
| `hook_runtime/handlers/notebooks.py` | hook_runtime/handlers/feedback/notebook_output_hygiene.py | rename | after-chain | A16 | 248 | 1 | none | [A16] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |
| `hook_runtime/handlers/prompt_scope.py` | hook_runtime/handlers/feedback/prompt_write_scope_guard.py | rename | after-chain | A16 | 192 | 1 | none | [A16] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/ruff_feedback.py` | hook_runtime/handlers/feedback/ruff_feedback.py | move | after-chain | A16 | 283 | 2 | edited by #55 (docstring example :135) | [A16] it serves 4 hooks (post-edit-ruff-format and three *-lint-feedback hooks), so it keeps its shared name; the registry.py:69-124 map value changes |
| hook_runtime/handlers/skill_nudge.py (new in #58) | hook_runtime/handlers/feedback/skill_nudge.py | move | after-chain | A16 | — | 0 | created by #58 (~110 lines) | not on main yet; it is already named after its hook id and moves with A16 |
| `hook_runtime/handlers/toolchain.py` | hook_runtime/handlers/feedback/toolchain_missing_hint.py | rename | after-chain | A16 | 107 | 1 | none | [A16] the value in the registry.py:69-124 map changes; the registry name stays |

#### `hook_runtime/handlers/protect/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/handlers/_briefing_probes.py` | hook_runtime/handlers/protect/_briefing_probes.py | move | after-chain | A16 | 310 | 2 | none | [A16] test_import_budget.py:472 pins it |
| `hook_runtime/handlers/_control_plane_json.py` | hook_runtime/handlers/protect/_control_plane_json.py | move | after-chain | A16 | 262 | 2 | none | [A16] |
| `hook_runtime/handlers/_control_plane_shell.py` | hook_runtime/handlers/protect/_control_plane_shell.py | move | after-chain | A16 | 95 | 2 | none | [A16] |
| `hook_runtime/handlers/_detector_inputs.py` | hook_runtime/handlers/protect/_detector_inputs.py | move | after-chain | A16 | 172 | 2 | none | [A16] test_import_budget.py:421 pins it |
| `hook_runtime/handlers/_drift.py` | hook_runtime/handlers/protect/_drift.py | move | after-chain | A16 | 256 | 4 | none | [A16] test_import_budget.py:473 and test_import_budget_stop.py:64 pin it |
| `hook_runtime/handlers/_source_changed.py` | hook_runtime/handlers/protect/_source_changed.py | move | after-chain | A16 | 146 | 5 | none | [A16] all 4 importers are in protect, so it does not go to _shared as the target said. :56 runs '-I -m coding_agent_playbook.cli', so cli/__main__.py is needed |
| `hook_runtime/handlers/control_plane_guard.py` | hook_runtime/handlers/protect/control_plane_guard.py | move | after-chain | A16 | 236 | 0 | none | [A16] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/eval_task_authoring_lint.py` | hook_runtime/handlers/protect/eval_task_authoring_lint.py | move | after-chain | A16 | 210 | 0 | none | [A16] the registry.py:69-124 map value changes. Its lazy imports of evals (:46, :114, :138) are an upward layers edge; see contract_violations |
| `hook_runtime/handlers/guard_eval_fixtures.py` | hook_runtime/handlers/protect/guard_eval_fixtures.py | move | after-chain | A16 | 163 | 0 | none | [A16] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/guard_generated_outputs.py` | hook_runtime/handlers/protect/guard_generated_outputs.py | move | after-chain | A16 | 227 | 0 | cited by spec (:1521), no edit | [A16] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/resync_on_detector_input_change.py` | hook_runtime/handlers/protect/resync_on_detector_input_change.py | move | after-chain | A16 | 212 | 1 | cited by spec (:1524, :3383), no edit | [A16] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/session_start_playbook_briefing.py` | hook_runtime/handlers/protect/session_start_playbook_briefing.py | move | after-chain | A16 | 136 | 0 | none | [A16] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/stop_drift_and_orphan_gate.py` | hook_runtime/handlers/protect/stop_drift_and_orphan_gate.py | move | after-chain | A16 | 214 | 2 | none | [A16] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |
| `hook_runtime/handlers/validate_then_sync_on_canonical_edit.py` | hook_runtime/handlers/protect/validate_then_sync_on_canonical_edit.py | move | after-chain | A16 | 189 | 1 | none | [A16] the value in the registry.py:69-124 map changes; the registry name stays |

#### `hook_runtime/handlers/safety/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/handlers/_commit_checks.py` | hook_runtime/handlers/safety/_commit_checks.py | move | after-chain | A14 | 89 | 1 | none | [A14] |
| `hook_runtime/handlers/_cz.py` | hook_runtime/handlers/safety/_cz.py | move | after-chain | A14 | 215 | 2 | none | [A14] |
| `hook_runtime/handlers/_data_reads.py` | hook_runtime/handlers/safety/_data_reads.py | move | after-chain | A14 | 90 | 2 | none | [A14] |
| `hook_runtime/handlers/_destructive_git.py` | hook_runtime/handlers/safety/_destructive_git.py | move | after-chain | A14 | 298 | 2 | none | [A14] no twin command, so it stays private to the pack |
| `hook_runtime/handlers/_destructive_paths.py` | hook_runtime/handlers/safety/_destructive_paths.py | move | after-chain | A14 | 299 | 4 | none | [A14] |
| `hook_runtime/handlers/_egress.py` | hook_runtime/handlers/safety/_egress.py | move | after-chain | A14 | 214 | 4 | none | [A14] egress has no twin: its importers (network, exfil, taint, _net_targets) are all in the safety pack. test_import_budget.py:674 pins it |
| `hook_runtime/handlers/_git_identity.py` | hook_runtime/handlers/safety/_git_identity.py | move | after-chain | A14 | 119 | 2 | none | [A14] |
| `hook_runtime/handlers/_net_targets.py` | hook_runtime/handlers/safety/_net_targets.py | move | after-chain | A14 | 206 | 1 | none | [A14] test_import_budget.py:783 pins it |
| `hook_runtime/handlers/_secret_inodes.py` | hook_runtime/handlers/safety/_secret_inodes.py | move | after-chain | A14 | 218 | 2 | none | [A14] |
| `hook_runtime/handlers/_secret_policy.py` | hook_runtime/handlers/safety/_secret_policy.py | move | after-chain | A14 | 189 | 5 | none | [A14] the target said _shared, but all 5 importers are safety handlers. test_import_budget.py:579 pins it |
| `hook_runtime/handlers/_secret_sweep.py` | hook_runtime/handlers/safety/_secret_sweep.py | move | after-chain | A14 | 213 | 2 | none | [A14] |
| `hook_runtime/handlers/commit_convention.py` | hook_runtime/handlers/safety/commit_message_convention.py | rename | after-chain | A14 | 172 | 0 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/conventions.py` | hook_runtime/handlers/safety/command_convention_guard.py | rename | after-chain | A14 | 146 | 0 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/dependencies.py` | hook_runtime/handlers/safety/dependency_allowlist_guard.py | rename | after-chain | A14 | 236 | 0 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/destructive.py` | hook_runtime/handlers/safety/destructive_command_guard.py | rename | after-chain | A14 | 230 | 1 | none | [A14] the registry.py:69-124 map value changes. Destructive has no twin command, so its judge stays in the safety pack. The shared native-deny list stays in security/patterns.py:252, and B7 adds the test that the hook denies every native prefix |
| `hook_runtime/handlers/exfil.py` | hook_runtime/handlers/safety/exfil_channel_guard.py | rename | after-chain | A14 | 232 | 0 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/git_policy.py` | hook_runtime/handlers/safety/git_commit_push_policy_guard.py | rename | after-chain | A14 | 260 | 1 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/network.py` | hook_runtime/handlers/safety/network_egress_guard.py | rename | after-chain | A14 | 218 | 0 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/pii_prompt_guard.py` | hook_runtime/handlers/safety/pii_prompt_guard.py | move | after-chain | A14 | 202 | 1 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/secret_content.py` | hook_runtime/handlers/safety/secret_content_guard.py | rename | after-chain | A14 | 304 | 1 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/secret_paths.py` | hook_runtime/handlers/safety/secrets_path_guard.py | rename | after-chain | A14 | 309 | 1 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/sensitive_reads.py` | hook_runtime/handlers/safety/sensitive_data_read_guard.py | rename | after-chain | A14 | 256 | 0 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/stop_sweep.py` | hook_runtime/handlers/safety/stop_diff_sweep.py | rename | after-chain | A14 | 222 | 1 | none | [A14] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |
| `hook_runtime/handlers/taint.py` | hook_runtime/handlers/safety/taint_escalation.py | rename | after-chain | A14 | 236 | 0 | none | [A14] the value in the registry.py:69-124 map changes; the registry name stays |

#### `hook_runtime/handlers/verify/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_agent_transcript.py` | hook_runtime/handlers/verify/_agent_transcript.py | move | after-chain | A15 | 96 | 2 | none | [A15] only subagent_verify imports it |
| `hook_runtime/_public_api.py` | hook_runtime/handlers/verify/_public_api.py | move | after-chain | A15 | 89 | 1 | none | [A15] only tests_nudge imports it |
| `hook_runtime/handlers/_bypass_rules.py` | hook_runtime/handlers/verify/_bypass_rules.py | move | after-chain | A15 | 147 | 1 | none | [A15] |
| `hook_runtime/handlers/_coverage_report.py` | hook_runtime/handlers/verify/_coverage_report.py | move | after-chain | A15 | 191 | 2 | none | [A15] top-level imports of evaluators.execution (:28-29) are allowed, because hook_runtime sits above grading |
| `hook_runtime/handlers/_exec_stages.py` | hook_runtime/handlers/verify/_exec_stages.py | move | after-chain | A15 | 246 | 1 | none | [A15] bound by string in STAGE_FACTORIES (stop_ci_parity_gate.py:83-84) |
| `hook_runtime/handlers/_lint_stage.py` | hook_runtime/handlers/verify/_lint_stage.py | move | after-chain | A15 | 280 | 1 | none | [A15] bound by string in STAGE_FACTORIES (stop_ci_parity_gate.py:75) |
| `hook_runtime/handlers/_metrics_pass.py` | hook_runtime/handlers/verify/_metrics_pass.py | move | after-chain | A15 | 443 | 3 | imported by #55's docstring_nonregression | [A15] :440 imports evaluators._metrics_inputs; the grading lane makes that module public |
| `hook_runtime/handlers/_verify_claim.py` | hook_runtime/handlers/verify/_verify_claim.py | move | after-chain | A15 | 131 | 3 | none | [A15] bound by string in STAGE_FACTORIES (stop_ci_parity_gate.py:80) |
| `hook_runtime/handlers/coverage_diff_gate.py` | hook_runtime/handlers/verify/coverage_diff_gate.py | move | after-chain | A15 | 282 | 0 | none | [A15] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |
| `hook_runtime/handlers/docstring_nonregression.py` | hook_runtime/handlers/verify/docstring_nonregression.py | move | after-chain | A15 | 191 | 1 | edited by #55 (docstring example :185) | [A15] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |
| `hook_runtime/handlers/gate_weakening.py` | hook_runtime/handlers/verify/gate_weakening_guard.py | rename | after-chain | A15 | 213 | 1 | none | [A15] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string. It is not merged with gate_weakening_edit, because the pre_edit companion is on the hot path (test_import_budget_stop.py:138-139) |
| `hook_runtime/handlers/gate_weakening_edit.py` | hook_runtime/handlers/verify/gate_weakening_guard_edit.py | rename | after-chain | A15 | 161 | 0 | none | [A15] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/output_contract.py` | hook_runtime/handlers/verify/prompt_output_contract_on_stop.py | rename | after-chain | A15 | 164 | 0 | none | [A15] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |
| `hook_runtime/handlers/precommit_bypass.py` | hook_runtime/handlers/verify/block_precommit_bypass.py | rename | after-chain | A15 | 217 | 1 | none | [A15] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/quality_metrics.py` | hook_runtime/handlers/verify/clean_code_metrics_nonregression.py | rename | after-chain | A15 | 213 | 1 | none | [A15] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |
| `hook_runtime/handlers/stop_ci_parity_gate.py` | hook_runtime/handlers/verify/stop_ci_parity_gate.py | move | after-chain | A15 | 214 | 3 | none | [A15] it owns STAGE_FACTORIES (:69-86, 13 'module:function' strings), which each pack PR edits; the registry.py:69-124 map value changes |
| `hook_runtime/handlers/subagent_verify.py` | hook_runtime/handlers/verify/subagent_stop_verify.py | rename | after-chain | A15 | 296 | 1 | none | [A15] the value in the registry.py:69-124 map changes; the registry name stays |
| `hook_runtime/handlers/tests_nudge.py` | hook_runtime/handlers/verify/tests_with_source_nudge.py | rename | after-chain | A15 | 192 | 1 | none | [A15] the registry.py:69-124 map value changes and so does its STAGE_FACTORIES string; the registry name stays |

#### `hook_runtime/harness/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/harness/__init__.py` | hook_runtime/harness/wire.py (body); harness/__init__.py keeps the docstring only | split | after-chain | N21 | 137 | 26 | soft: tests/hook_runtime/test_import_budget.py:39 (#58) import-line rewrite | [N21] L5: the 137-line __init__ body (WireOutput, ForeignPayload, ContractFault, ParseContext, DENY_EXIT) moves verbatim to harness/wire.py, and the 26 importers are rewritten |
| `hook_runtime/harness/_patch.py` | hook_runtime/harness/_patch.py | stay | now | — | 69 | 1 | none | — |
| `hook_runtime/harness/_payload.py` | hook_runtime/harness/payload.py | rename | after-chain | N21 | 145 | 4 | none | [N21] public: dispatch.py:246 imports it from outside harness/ (an underscore violation today) |
| `hook_runtime/harness/_render.py` | hook_runtime/harness/_render.py | stay | now | — | 69 | 3 | none | — |
| `hook_runtime/harness/_tools.py` | hook_runtime/harness/_tools.py | stay | now | — | 254 | 3 | none | — |
| `hook_runtime/harness/claude.py` | hook_runtime/harness/claude.py | stay | now | — | 151 | 3 | none | — |
| `hook_runtime/harness/opencode.py` | hook_runtime/harness/opencode.py | stay | now | — | 152 | 10 | none | — |

#### `hook_runtime/judges/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_gate_scan_files.py` | hook_runtime/judges/_gate_weakening_files.py | move | after-chain | N15 | 302 | 1 | none | Harmonised (§11 H3): the gate-weakening judge goes to hook_runtime/judges/, not security/, because it imports hook_runtime and security is a stdlib leaf below it. Stays private: only gate_weakening imports it; it moves with gate_scan.py in N15. |
| `gate_scan.py` | hook_runtime/judges/gate_weakening.py (TEST_PATH_GLOBS, :74, goes to artifacts/path_classes.py) | move | after-chain | N15 | 457 | 7 | none | Harmonised (§11 H3): not security/gate_weakening.py: its imports of hook_runtime._git_parse, caps, globs and handlers._eval_paths (:43-46) become internal to hook_runtime. Pinned at _ENGINE_PATHS (test_docs_lifecycle_hooks_spec.py:103), _GATE_SCAN (tests/hook_runtime/test_import_budget_stop.py:29) and SPEC §5.1. |
| `hook_runtime/_hosts.py` | hook_runtime/judges/hosts.py | move | after-chain | N14 | 151 | 7 | none | [N14] the target said security/egress.py, but security is a leaf below hook_runtime; the deps judge (twin: check_deps) needs it |
| `hook_runtime/cutover.py` | hook_runtime/judges/commit_cutover.py | move | after-chain | N14 | 158 | 5 | none | [N14] the commit-convention cut-over, shared by the guard and its twin commands._ci_commit_convention; imports git.log |
| `hook_runtime/handlers/_cli_words.py` | hook_runtime/judges/cli_words.py | move | after-chain | N14 | 94 | 4 | none | [N14] the target said handlers/_shared, but install_commands (the deps judge) and the safety egress helpers both use it |
| `hook_runtime/handlers/_dependency_tiers.py` | hook_runtime/judges/dependency_tiers.py | move | after-chain | N14 | 224 | 3 | none | [N14] Harmonised (§11 H14): a plain git mv (the designer's B5), not merged with _manifest_diff: rename detection keeps history and a merge would be a deepening. The twin commands/check_deps.py:31 imports it. |
| `hook_runtime/handlers/_install_cmds.py` | hook_runtime/judges/install_commands.py | rename | after-chain | N14 | 315 | 7 | soft: tests/hook_runtime/test_import_budget.py:673 (#58 adds a test there) constant rewrite | [N14] an input of the deps judge, also used by 3 safety handlers |
| `hook_runtime/handlers/_manifest_diff.py` | hook_runtime/judges/manifest_diff.py | move | after-chain | N14 | 195 | 3 | none | [N14] see _dependency_tiers; imported at check_deps.py:38,49. |
| `hook_runtime/handlers/_notebook_cells.py` | hook_runtime/judges/notebook_cells.py | move | after-chain | N14 | 95 | 6 | none | [N14] the twin commands/scan_sinks.py:32 imports it |
| `hook_runtime/handlers/_notebook_check.py` | hook_runtime/judges/notebook_check.py | move | after-chain | N14 | 197 | 4 | soft: guard_config.py:107 (#58) import-line rewrite | [N14] the twin commands/check_notebooks.py:24 and guard_config.py:107 import it (NOTEBOOK_MAX_BYTES). |
| `hook_runtime/handlers/_sink_scan.py` | hook_runtime/judges/sink_scan.py | move | after-chain | N14 | 296 | 3 | none | [N14] Harmonised (§11 H14): moved now with the judges (the designer's B5): the twin commands/scan_sinks.py uses SinkTable and new_sink_calls through deser.py's re-export. deser.trusted_artifact_line joins it. |
| hook_runtime/handlers/deser.py (trusted_artifact_line, :117-131) | hook_runtime/judges/sink_scan.py | split | after-chain | N14 | — | — | none | [N14] the twin commands/scan_sinks.py and handlers/stop_sweep.py:187,195-197 import it; the rest of deser.py moves in A16. |

#### `hook_runtime/shell/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_git_options.py` | hook_runtime/shell/git_options.py | move | after-chain | N17 | 199 | 9 | none | [N17] public: 8 handlers read git_args |
| `hook_runtime/_shell_options.py` | hook_runtime/shell/_options.py | move | after-chain | N17 | 112 | 2 | none | [N17] only shell.wrappers and shell.writes import it |
| `hook_runtime/_shell_scan.py` | hook_runtime/shell/_scan.py | move | after-chain | N17 | 295 | 2 | none | [N17] only shell.parse and shell.segments import it |
| `hook_runtime/_shell_segments.py` | hook_runtime/shell/segments.py | move | after-chain | N17 | 243 | 3 | none | [N17] public: handlers._activity_record imports it |
| `hook_runtime/_shell_tokens.py` | hook_runtime/shell/tokens.py | move | after-chain | N17 | 154 | 6 | none | [N17] public: _verify_tag (moving to stop/) imports it |
| `hook_runtime/_shell_wrappers.py` | hook_runtime/shell/wrappers.py | move | after-chain | N17 | 300 | 6 | soft: guard_config.py:100 (#58) import-line rewrite | [N17] public: guard_config.py:100 and hook_runtime.config import it |
| `hook_runtime/_shell_writes.py` | hook_runtime/shell/writes.py | move | after-chain | N17 | 182 | 4 | none | [N17] public: write_targets, imported by 3 handlers |
| `hook_runtime/gitargv.py` | hook_runtime/shell/git_command.py | rename | after-chain | N17 | 277 | 15 | none | [N17] target rename: it parses a git command found in a shell segment, and the new name ends the gitargv/_git_argv near-collision |
| `hook_runtime/shell.py` | hook_runtime/shell/parse.py | move | after-chain | N17 | 116 | 38 | none | [N17] parse_shell, Segment, ShellCommand: the package's interface (shell/__init__ docstring-only) |
| `hook_runtime/wrapper_policy.py` | hook_runtime/shell/wrapper_policy.py | move | after-chain | N17 | 161 | 5 | none | [N17] |

#### `hook_runtime/state/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_prompt_boundary.py` | hook_runtime/state/_prompt_boundary.py | move | after-chain | N19 | 178 | 2 | none | [N19] only active_prompt imports it |
| `hook_runtime/_state_files.py` | hook_runtime/state/_files.py | move | after-chain | N19 | 189 | 1 | none | [N19] |
| `hook_runtime/_state_sweep.py` | hook_runtime/state/_sweep.py | move | after-chain | N19 | 215 | 1 | none | [N19] |
| `hook_runtime/active_prompt.py` | hook_runtime/state/active_prompt.py | move | after-chain | N19 | 268 | 6 | none | [N19] the target put it in handlers/_shared, but _guard_config_prompts (sync side) and dispatch._pipeline import it, so it cannot be private to the handlers; it reads session state |
| `hook_runtime/ledger.py` | hook_runtime/state/ledger.py | move | after-chain | N19 | 258 | 5 | soft: registry.py:41 (#58) import-line rewrite | [N19] |
| `hook_runtime/session.py` | hook_runtime/state/session.py | move | after-chain | N19 | 211 | 14 | cited by spec 8.5.3 (session.py:96-103), no edit; registry.py (#58) imports it: import-line rewrite only | [N19] |
| `hook_runtime/state.py` | hook_runtime/state/store.py | move | after-chain | N19 | 298 | 57 | cited by spec 8.5.3 (state.py:147-150), no edit; ruff_feedback.py (#55) and registry.py (#58) import it: import-line rewrites only | [N19] StateStore (state/state.py would stutter) |
| `security/audit.py` | hook_runtime/state/audit_log.py | move | after-chain | N19 | 489 | 8 | none | [N19] every importer is in hook_runtime (ledger, state, _decision_log and the activity handlers). Pinned by tests/unit/test_docs_lifecycle_hooks_cli.py:263-264 and SPEC.md:3209 (§17.4) |
| `security/decision_summary.py` | hook_runtime/state/decision_summary.py | move | after-chain | N19 | 136 | 2 | none | [N19] its only caller is _doctor_decisions; a decision-log merge is not scheduled |

#### `hook_runtime/stop/`

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `hook_runtime/_verify_tag.py` | hook_runtime/stop/verify_tag.py | move | after-chain | N17 | 95 | 2 | none | [N17] the target puts it in stop/; public because dispatch._post_write imports it |
| `hook_runtime/stop/__init__.py` | hook_runtime/stop/__init__.py | stay | now | — | 8 | 0 | none | already docstring-only |
| `hook_runtime/stop/alone.py` | hook_runtime/stop/alone.py | stay | now | — | 81 | 7 | none | — |
| `hook_runtime/stop/chain.py` | hook_runtime/stop/chain.py | stay | now | — | 130 | 4 | none | — |
| `hook_runtime/stop/coordinator.py` | hook_runtime/stop/coordinator.py | stay | now | — | 375 | 7 | none | GatePolicy.from_table (:95) is the reader of the stop_gate table |
| `hook_runtime/stop/output.py` | hook_runtime/stop/output.py | stay | now | — | 176 | 6 | none | — |
| `hook_runtime/stop/runner.py` | hook_runtime/stop/runner.py | stay | now | — | 146 | 11 | none | — |
| `hook_runtime/stop/stages.py` | hook_runtime/stop/stages.py | stay | now | — | 220 | 34 | none | hook_registrations (claude, plan, stop_gate) import it: hooks to hook_runtime, which is allowed |
| `hook_runtime/stop/suite.py` | hook_runtime/stop/suite.py | stay | now | — | 298 | 6 | none | top-level import of evaluators.execution.project (:32): allowed, because hook_runtime sits above grading |
| `hook_runtime/stop/tools.py` | hook_runtime/stop/tools.py | stay | now | — | 106 | 7 | none | — |

### 4.25 `templates/`

Packaged data files. 1 row.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `templates/precommit/config.yaml.j2` | templates/precommit/config.yaml.j2 | stay | now | — | — | — | none | Found through resources.files(ENGINE_PACKAGE)/templates/precommit (commands/init.py:372, tests/_catalog.py:28), so precommit.py (N9) needs no path change. |

### 4.26 Deleted

Modules that leave the tree. 3 rows.

| Current | Target | Action | Wave | PR | Lines | Importers | Chain overlap | Note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `_typing.py` | (deleted) | delete | after-chain | CF-2 | 30 | 7 | all 5 adapter importers (base, agents_md, continue, opencode, shared_skills) are edited by the chain | A TYPE_CHECKING pass-through where Config and Lockfile are Any. CF-2 points its users at artifacts.*, config.model.Config and lockfile.model.Lockfile and drops pyproject.toml:219 (coverage omit). A type-level change, not a move, so it is its own PR (config-files remainder, after #62). |
| `evaluators/checks/__init__.py` | (deleted; grading/ has no checks/ sub-package) | delete | now | — | 75 | 2 | none | N24 removes the eval-family imports and N25 deletes the package. Its job, firing @register_check by import (:37-56), moves into grading/check_registry.py _load_check_builtins for the kernel families and into evals/compile/_handles.py for the eval families. The registry contents stay the same for every get_check caller; evals/_handles.py:121,136 is the only one. |
| `sources/__init__.py` | (deleted) | delete | now | N3 | — | 0 | none | Deleted with the last sources/ file, in N3. |

## 5. Test map, fixed paths and the rewrite script

### 5.1 Rules (L8)

- Tests of a package live in `tests/<package>/`, mirroring the source tree one level deep (`tests/config/`, `tests/hook_runtime/judges/`, `tests/hooks/guard_config/`). Each new directory gets an empty `__init__.py`: the test tree is imported as packages (`tests.hook_runtime.guard_repo`).
- A test file moves in the same PR as the module it tests. A test file that tests two destinations is split by function in that PR, and the split is the only content change.
- Tests of root modules (`toml_writer`, `precommit`) and the cross-cutting docs tests (`tests/unit/test_docs_*`, `test_package_init`, `test_entry_points`) stay in `tests/unit/` (H18). The architecture tests of lane 0 live in `tests/architecture/`.
- `tests/cli/` and `tests/integration/` stay as they are; their files only get rewritten imports. Shared helpers at the tests root (`fakes.py`, `hook_samples.py`, `member_skill_samples.py`, `conftest.py`, `import_probe.py`) stay and get rewritten imports.
- `tests/hooks/` holds the hook-pack tests until A13 moves them to `tests/hook_runtime/handlers/`; after that it belongs to the sync-time `hooks/` package (H19).
- Tests may import private modules (the private-modules contract covers `src/` only, D0-13), so a move-only PR never has to make a module public for a test.
- Replace, do not layer: a behaviour PR that gives a private helper an interface deletes the tests that reached the helper in the same PR (section 8 B.1 rule 6, section 9 AC.2.5).

### 5.2 Test moves

Each bullet names the PR that carries the move (ids in section 7). The text comes from the area mappers, harmonised.

#### 5.2.1 What stays where it is

- Rule: tests of a package go to tests/<package>/, each new directory with an empty __init__.py (tests are imported as packages, e.g. tests.hook_runtime.guard_repo). Tests of root modules (toml_writer, precommit, plugin_registry) and the cross-cutting docs and architecture tests (test_docs_*, test_package_init, test_entry_points) stay in tests/unit/. Shared helpers at tests/ root (fakes.py, hook_samples.py, member_skill_samples.py, conftest.py) stay and only get rewritten imports.
- Unchanged in every PR: all tests/cli/*.py, tests/integration/*, and the 12 tests/hooks/* files that call only `_validate.run(`.
- Stay in tests/adapters/: test_agents_md, test_always_only_composites (#49), test_claude_code, test_claude_code_hooks, test_claude_code_rules, test_claude_launcher, test_cleanup, test_continue, test_opencode, test_opencode_hooks, test_opencode_shim_node, opencode_shim_kit, test_sandbox_parity, test_shared_skills, test_skill_writer, test_skill_writer_member_references, and test_guardrails_skill_targets (new in PR 4). Stay per L8: tests/cli/test_import_harness.py, tests/cli/test_validate_harness.py
- These stay: tests/security/* except test_audit.py; tests/cli/* and tests/integration/* (L8; import rewrites only); the tests/unit/test_docs_*.py doc tests (edits to their pins only); tests/fixtures/hook_payloads/** and tests/fixtures/hook_guard_config/** (data, which CI step ci.yml:55-58 reads).
- Stay in place, imports rewritten only: tests/cli/test_metrics.py, test_metrics_coverage.py, test_metrics_golden.py, test_metrics_selection.py, test_eval.py, test_eval_run.py, test_eval_aggregate_render.py, test_validate_links.py, tests/cli/conftest.py (L8: tests/cli stays); tests/integration/test_shipped_task_gates.py, test_shipped_eval_tasks_c7.py, test_modoboa_cmdi_fixture.py, test_crosscommitvuln_fixtures.py (L8); tests/hooks/test_clean_code_metrics_nonregression.py, test_coverage_diff_gate.py; tests/hook_runtime/tool_fakes.py, test_import_budget_stop.py (test_combine.py moves in A11, test_stop_stages.py in N21); tests/fakes.py; tests/unit/test_docs_lifecycle_hooks_spec.py, test_docs_lifecycle_hooks_cli.py, test_docs_migration_hooks.py, test_docs_readme_hooks.py, test_no_unsandboxed_jinja.py, test_hermetic_git_env.py (test_filesystem_list_eval_tasks.py moves in N3)
- Chain-owned, kept in place until #62: tests/evals/test_prompting.py (#54; import paths unchanged) and tests/unit/test_sources_filesystem_bundled.py (#50-#53, #56): N3 rewrites only its import lines (`from coding_agent_playbook import catalog` at :18, a soft overlap) and A4 moves it to tests/catalog/test_source_bundled.py after #62
- Already home, no move: tests/evals/{test_agent_env, test_aggregate, test_compile, test_expr, test_handles, test_weighted_verdict}.py (only imports rewritten in N23/N24/N25)

#### 5.2.2 Test moves per PR

- **N1**
  - tests/unit/test_toml.py -> tests/unit/test_toml_writer.py; tests/unit/test_dump_toml.py stays (imports rewritten)
- **N2**
  - tests/unit/test_config.py -> tests/config/test_model.py (the LinksConfig parse cases -> tests/config/test_tables_links.py); tests/unit/test_config_enabled_keys.py -> tests/config/test_schema_enabled_keys.py; tests/unit/test_hooks_config.py -> tests/config/test_tables_hooks.py; tests/unit/test_sources_filesystem.py FileSystemStateSource cases (including the entry-point check at :579-589) -> tests/config/test_files.py; tests/unit/test_sources_base.py StateSource cases -> tests/config/test_files_state_source.py; tests/unit/test_committed_config.py stays until N10, but its _WRITERS_HOME pin (:232) becomes config/files.py here
- **N3**
  - tests/unit/test_catalog.py -> tests/catalog/test_roots.py; tests/unit/test_sources_filesystem.py remaining FileSystemArtifactSource cases -> tests/catalog/test_source.py; tests/unit/test_sources_base.py ArtifactSource cases -> tests/catalog/test_source_abc.py; tests/unit/test_sources_filesystem_bundled.py stays at tests/unit/ (edited by #50-#53/#56; wave rule, 2.2): only its module-object import at :18 is rewritten (`from coding_agent_playbook.catalog import roots as catalog`, R-IMPORT same-name conversion) and its `_PACKAGE_DIR` patches at :128, :204 keep working; A4 moves it; tests/unit/test_sources_filesystem_hooks.py -> tests/catalog/test_source_hooks.py; tests/unit/test_sources_layer_roots.py -> tests/catalog/test_source_layer_roots.py; tests/unit/test_filesystem_list_eval_tasks.py -> tests/catalog/test_source_eval_tasks.py
- **N4**
  - tests/unit/test_detector.py -> tests/detector/test_facts.py (detect cases) + tests/detector/test_predicate.py (evaluate_predicate cases); the filter_applies_if cases in tests/unit/test_orchestrator.py -> tests/detector/test_predicate.py; tests/unit/test_detector_package_manager.py -> tests/detector/test_package_manager.py; tests/unit/test_pep503.py -> tests/detector/test_pep503.py; tests/unit/test_pyproject_deps.py -> tests/detector/test_pyproject_deps.py; tests/unit/test_check_skip_reason.py -> tests/cli/test_check_skip_reason.py (a test of commands/check, whose tests live in tests/cli/, L8; a test move only, independent of the unscheduled catalog-layers predicate work); tests/hooks/test_resync_on_detector_input_change.py:17 (`import coding_agent_playbook.detector as detector`, used at :58, :87, :97) becomes `from coding_agent_playbook.detector import facts as detector` (R-IMPORT same-name conversion)
- **N5**
  - tests/unit/test_lockfile.py -> tests/lockfile/test_model.py; tests/unit/test_canonical_json.py -> tests/lockfile/test_canonical_json.py
- **N6**
  - tests/unit/test_sentinel.py -> tests/generated_output/test_sentinel.py; tests/unit/test_file_identity.py -> tests/generated_output/test_file_identity.py; tests/unit/test_atomic_io.py -> tests/generated_output/test_atomic_io.py; tests/unit/test_output_io.py -> tests/generated_output/test_output_io.py; tests/unit/test_symlinks.py -> tests/generated_output/test_symlinks.py; tests/unit/test_gitignore.py -> tests/generated_output/test_gitignore.py; tests/unit/test_docs_sentinel.py stays (docs test) (test_owned_files.py follows in A7)
- **N7**
  - tests/unit/test_cli.py -> tests/cli/test_cli.py (tests/cli/ stays per L8 and is the cli package's test home); T0.1 has already added tests/cli/test_module_entry.py, which pins `python -I -m coding_agent_playbook.cli --help` exit 0
  - tests/unit/test_entry_points.py gains test_console_scripts_load_cli_main: the `playbook` and `coding-agent-playbook` console scripts load `coding_agent_playbook.cli:main` (L2).
- **N8**
  - no test file moves; the twin tests stay in tests/cli/ (L8). Import-only rewrites: tests/fakes.py:35 (StepRun), tests/cli/test_ci.py, tests/cli/test_ci_commit_convention.py, tests/cli/test_scan_sinks.py, tests/unit/test_docs_lifecycle_hooks_cli.py:36,39, tests/unit/test_docs_readme_hooks.py:26-27, tests/integration/test_dogfood_config.py:29.
- **N9**
  - tests/unit/test_precommit_merge.py -> tests/unit/test_precommit.py (tests of a root module stay in tests/unit/, H18). Import rewrites: tests/integration/test_precommit_template.py:18-21, tests/unit/test_docs_lifecycle_hooks_cli.py:40 (#56 edits that file: import block only), tests/adapters/test_sandbox_parity.py:20,108-110, tests/unit/test_cli.py:426-431.
- **N10**
  - tests/unit/test_committed_config.py -> tests/config/test_committed.py. Its AST guard sets _HOME (:230) to 'config/committed.py' and keeps _WRITERS_HOME = 'config/files.py' (set by N2); the importer pins (:312-313) stay, because check.py and init.py still import it.
- **N11**
  - no file moves (tests/cli stays). Rewrites: tests/cli/test_eval_aggregate_render.py:12 (evals.report_format) and the monkeypatch targets in tests/cli/test_eval_run.py:261,352,464,495,510 (evals.registry).
- **N12**
  - `git mv tests/harness tests/agent_harness`: the whole directory, so the 21 files of tests/harness/fixtures/ (full/, minimal/) move with test_parser.py, which finds them with `Path(__file__).parent / "fixtures"` (:21, same depth, no edit). Files: tests/harness/__init__.py -> tests/agent_harness/__init__.py; tests/harness/test_emitter.py -> tests/agent_harness/test_emitter.py; tests/harness/test_import_roundtrip.py -> tests/agent_harness/test_import_roundtrip.py; tests/harness/test_leaf_detectors.py -> tests/agent_harness/test_leaf_detectors.py; tests/harness/test_manifest_roundtrip.py -> tests/agent_harness/test_manifest_roundtrip.py; tests/harness/test_manifest_rule_skill.py -> tests/agent_harness/test_manifest_rule_skill.py; tests/harness/test_models.py -> tests/agent_harness/test_models.py; tests/harness/test_parser.py -> tests/agent_harness/test_parser.py
  - tests/adapters/test_agent_harness.py:23, tests/adapters/test_agent_harness_hooks.py:20, tests/adapters/test_agent_harness_member_rules.py:15, tests/adapters/test_skill_writer.py:30, tests/plugins/test_superpowers_sync.py:37, tests/unit/test_docs_lifecycle_hooks_spec.py:26, plus the docstring at tests/unit/test_toml.py:4
- **N13**
  - tests/unit/test_claude_settings.py -> tests/adapters/test_claude_settings.py (closure pin :524-543 rewritten); tests/unit/test_json_spans.py -> tests/adapters/test_json_spans.py; tests/unit/test_settings_drift.py -> tests/adapters/test_settings_drift.py
  - tests/unit/test_canonical_json.py:14-15 (the file itself moves with N5), tests/unit/test_lockfile.py:13, tests/adapters/test_claude_code_hooks.py:39, tests/adapters/test_claude_launcher.py:21, tests/adapters/test_claude_code_rules.py:29 and :94 (closure name), tests/cli/test_check_hooks.py:19, tests/cli/test_check.py:12, tests/unit/test_docs_migration_hooks.py:25
- **N14**
  - tests/hook_runtime/test_hosts.py -> tests/hook_runtime/judges/test_hosts.py; tests/hook_runtime/test_install_cmds.py -> tests/hook_runtime/judges/test_install_commands.py; tests/hook_runtime/test_manifest_diff.py -> tests/hook_runtime/judges/test_manifest_diff.py; tests/hook_runtime/test_sink_scan.py -> tests/hook_runtime/judges/test_sink_scan.py; tests/hook_runtime/test_cutover.py -> tests/hook_runtime/judges/test_commit_cutover.py (each new directory gets an empty __init__.py). Import-line rewrites only: tests/hook_runtime/test_wrapper_policy.py, tests/hooks/test_dependency_allowlist_guard.py, tests/integration/test_dogfood_config.py:30, tests/hook_runtime/test_import_budget.py:673 (#58 appends to that file: constant only).
- **N15**
  - tests/unit/test_gate_scan.py -> tests/hook_runtime/judges/test_gate_weakening.py. Import rewrite: tests/evaluators/test_paths.py (FIXTURE_GLOBS now in artifacts.path_classes). L8 creates tests/artifacts/, which stays empty until the artifacts lane, because no test targets _eval_paths alone.
- **N16**
  - tests/hook_runtime/test_runtime_config.py -> tests/hook_runtime/config/test_guard_config.py; test_pin.py -> tests/hook_runtime/config/test_pin.py; test_protected.py -> tests/hook_runtime/config/test_protected.py.
- **N17**
  - tests/hook_runtime/test_shell.py -> tests/hook_runtime/shell/test_parse.py; test_gitargv.py -> tests/hook_runtime/shell/test_git_command.py; test_wrapper_policy.py -> tests/hook_runtime/shell/test_wrapper_policy.py; test_verify_tag.py -> tests/hook_runtime/stop/test_verify_tag.py.
- **N18**
  - tests/hook_runtime/test_safegit.py -> tests/hook_runtime/git/test_safe_git.py; test_git_log.py -> tests/hook_runtime/git/test_log.py; test_git_memo.py -> tests/hook_runtime/git/test_memo.py; test_git_range.py -> tests/hook_runtime/git/test_range.py.
- **N19**
  - tests/hook_runtime/test_state.py -> tests/hook_runtime/state/test_store.py; test_session.py -> tests/hook_runtime/state/test_session.py; test_prompt_boundary.py -> tests/hook_runtime/state/test_prompt_boundary.py; tests/security/test_audit.py -> tests/hook_runtime/state/test_audit_log.py (it covers audit and decision_summary, which move together).
- **N20**
  - tests/hook_runtime/test_doctor.py, test_doctor_opencode.py, test_heartbeat.py, test_simulate.py -> tests/hook_runtime/diagnostics/; the ci.yml:54 comment follows test_simulate.py. Depth edit (7.1.2 rule 11): test_simulate.py:321 `parents[1] / "fixtures"` -> `parents[2]`.
- **N21**
  - tests/hook_runtime/test_render_claude.py, test_render_opencode.py, test_wire_contract.py -> tests/hook_runtime/harness/; tests/hook_runtime/test_stop_coordinator.py, test_stop_output.py, test_stop_runner.py, test_stop_stages.py, test_stop_suite.py -> tests/hook_runtime/stop/test_coordinator.py, test_output.py, test_runner.py, test_stages.py, test_suite.py (mirroring a package that does not move). Depth edits (7.1.2 rule 11): test_wire_contract.py:51 `parents[2] / "src"` -> `parents[3]`; test_stop_stages.py:23 `parents[2] / "specs"` -> `parents[3]`.
- **N22**
  - tests/evaluators/test_metrics_gate.py -> tests/metrics_gate/test_run.py
  - tests/evaluators/test_metrics_gate_selection.py -> tests/metrics_gate/test_run_selection.py
  - tests/evaluators/test_metric_selection.py -> tests/metrics_gate/test_policy.py
  - tests/evaluators/test_measurement_snapshot.py -> tests/metrics_gate/test_snapshot.py
  - new tests/metrics_gate/test_config.py takes the parse_metrics_config cases from tests/unit/test_config.py:113-~170 (they import it through the config.py:34 re-export, which goes) and the MetricConfig cases from tests/evaluators/test_types.py (import at :16); both source files keep their other cases
  - tests/metrics_gate/__init__.py (new, empty)
  - metrics_config has no direct test; tests/unit/test_docs_readme_hooks.py:41 gets its import rewritten.
- **N23**
  - tests/evaluators/test_eval_runner.py -> tests/evals/test_harness_runner.py (39.8K; also rewrite its 8 monkeypatch strings at :950-1073)
  - tests/evaluators/test_aggregate_runner.py -> tests/evals/test_aggregate_runner.py
  - tests/evaluators/test_claude_code_runner.py -> tests/evals/test_claude_code_runner.py
  - tests/evaluators/test_opencode_runner.py -> tests/evals/test_opencode_runner.py
  - tests/evaluators/test_runner_git_isolation.py -> tests/evals/test_runner_git_isolation.py
  - tests/evaluators/test_judge.py -> tests/evals/test_judge.py
  - tests/unit/test_evals_compile_blocks.py -> tests/evals/test_compile_blocks.py
  - tests/unit/test_evals_loader.py -> tests/evals/test_loader.py
  - tests/unit/test_evals_task.py -> tests/evals/test_task.py
  - tests/unit/test_evals_validator.py -> tests/evals/test_validator.py
  - tests/unit/test_evals_placeholders.py -> tests/evals/test_placeholders.py
  - tests/unit/test_evals_package.py -> tests/evals/test_package.py, rewritten: the re-export assertions go with the docstring-only evals/__init__ (L5), and the defining-module imports stay
  - tests/unit/test_git_env.py -> tests/evals/test_git_env.py (tests/unit/test_hermetic_git_env.py stays: it tests the shared test-env helper, only its import changes)
- **N24**
  - tests/evaluators/test_answer_check.py -> tests/evals/test_answer_check.py
  - tests/evaluators/test_gate_registry.py -> tests/evals/test_gate_registry.py (string pins :80,107 -> 'coding_agent_playbook.evals.compile.gate_registry.metadata.entry_points')
  - tests/evaluators/test_rubrics_registry.py -> tests/evals/test_rubric_registry.py (string pins :104,129)
  - tests/evaluators/test_check_registry.py stays until N25, but any assertion that file_exists/answer_matches/pass_at_k are registered after importing only the kernel registry moves to tests/evals/test_handles.py, since those ids now register from evals/compile/_handles.py
- **N25**
  - tests/evaluators/{test_baseline_git, test_builtins, test_builtins_edge, test_check, test_check_granularity, test_check_registry, test_compose, test_diff_coverage, test_docstring_example, test_execution_parsers, test_execution_project, test_file_sloc, test_git_diff, test_judge_check, test_judge_metric, test_maintainability, test_metric, test_nested_rubric, test_normalization, test_normalizer, test_parse, test_paths, test_rubric, test_ruff_violations, test_scheduler, test_scope, test_tool_runner, test_types}.py -> tests/grading/ (same basenames)
  - tests/evaluators/test_execution_evaluators.py -> tests/grading/test_execution_metrics.py
  - tests/evaluators/test_package_exports.py -> deleted (it asserts the evaluators/__init__ re-exports that L5 removes; lane 0's docstring-only __init__ guard replaces it)
  - tests/evaluators/__init__.py -> tests/grading/__init__.py; tests/evaluators/ is then empty and removed
- **A1**
  - tests/unit/test_hook_frontmatter_module.py -> tests/artifacts/test_hook_frontmatter.py
- **A2**
  - tests/unit/test_types.py -> tests/artifacts/test_artifacts.py; tests/unit/test_types_hook.py -> tests/artifacts/test_hook.py; tests/unit/test_types_hook_roundtrip.py -> tests/artifacts/test_hook_roundtrip.py; tests/unit/test_types_skill_fields.py -> tests/artifacts/test_skill_fields.py
- **A3**
  - tests/unit/test_skill_document.py -> tests/skills/test_document.py; tests/unit/test_skill_document_sections.py -> tests/skills/test_document_sections.py; tests/unit/test_skill_membership.py -> tests/skills/test_membership.py; tests/adapters/test_agent_skill_rules.py -> tests/skills/test_naming.py
  - tests/adapters/test_agent_skill_rules.py -> tests/skills/test_naming.py (closure pin :39-50 rewritten)
- **A4**
  - tests/unit/test_validate_skills_checks.py -> tests/validation/test_skills.py; tests/unit/test_sync_preflight.py -> tests/validation/test_preflight.py (new tests/validation/__init__.py). Import-only: tests/cli/test_validate.py:16, tests/cli/test_validate_links.py (also its monkeypatch at :212), tests/cli/test_sync_validate_gate.py, tests/cli/test_unusable_overlays.py, tests/fakes.py:48, tests/unit/test_docs_lifecycle_hooks_cli.py:38, tests/unit/test_rules_lint_codes.py:22, tests/plugins/python_design/test_pack.py:32-33.
  - tests/unit/test_sources_filesystem_bundled.py -> tests/catalog/test_source_bundled.py (chain-owned until #62, 5.2.1), with its import at :21 rewritten.
  - tests/unit/test_links.py -> tests/validation/test_link_check.py (the link checker half of links.py).
- **A5**
  - tests/unit/test_orchestrator.py -> tests/catalog/test_resolve.py (OverlayResolver cases) + tests/adapters/test_registry.py (discover_adapters, installed_output_locations) + tests/validation/test_context.py (SyncContext, H4); tests/unit/test_orchestrator_hooks.py -> tests/catalog/test_resolve_hooks.py (the _resolve_hooks cases -> tests/validation/test_context.py)
  - The template_source and artifact_id_of cases (tests/unit/test_orchestrator.py:132-141, :198) -> tests/artifacts/test_identity.py. The monkeypatch target 'coding_agent_playbook.orchestrator.detect' (tests/cli/test_sync_check.py:458) becomes 'coding_agent_playbook.validation.context.detect'; tests/fakes.py follows the SyncContext import.
- **A6**
  - tests/unit/test_sync_lockfile.py -> tests/sync/test_dispatch.py; tests/unit/test_sync_hooks.py -> tests/sync/test_hook_outputs.py; tests/unit/test_sync_output.py -> tests/sync/test_output_policy.py; tests/unit/test_output_blockers.py -> tests/sync/test_output_blockers.py; tests/unit/test_sync_orphans.py -> tests/sync/test_leftovers.py; tests/unit/test_output_locations.py -> tests/sync/test_output_locations.py; tests/unit/test_sync_render_skills.py -> tests/sync/test_render_skills.py; tests/unit/test_render_hook_body.py -> tests/sync/test_render_hook_body.py (moves again to tests/rendering/ with render-session). New tests/sync/__init__.py.
  - the 28 test files aliasing `commands import sync as _sync`/`sync_cmd` (codemod rule in the sync row), tests/cli/test_sync_check.py:113 monkeypatch, tests/cli/hook_repo.py:19, tests/cli/test_sync_hook_trust.py, tests/adapters/test_skill_writer.py:27-29, tests/adapters/test_shared_skills.py:22, tests/adapters/test_sandbox_parity.py:21, tests/unit/test_guard_config.py:27, tests/unit/test_guard_config_ruff.py:25, tests/unit/test_skill_membership.py:18, tests/unit/test_docs_migration_hooks.py:26-28, tests/unit/test_docs_lifecycle_hooks_cli.py:37, tests/unit/test_no_unsandboxed_jinja.py:34, tests/hooks/test_overlay_activation.py:20.
  - tests/unit/test_git_client.py -> tests/sync/test_git_client.py (git_client.py joins sync/).
- **A7**
  - tests/adapters/test_owned_files.py -> tests/generated_output/test_write_guard.py; tests/adapters/test_skill_sources.py -> tests/generated_output/test_skill_sources.py; tests/adapters/test_skill_files.py -> tests/generated_output/test_skill_files.py (names kept; merging them into test_source_files.py is a content change for the deepen PR)
  - If A7 lands after N12/AH-1, the import of _skill_files in agent_harness/_import_files.py is rewritten to generated_output.source_files.
- **A8**
  - no file moves (the Claude Code adapter tests already live in tests/adapters/). Import edits in the 14 importers of claude_code_adapter, the 4 of _claude_hooks, tests/cli/test_sync_hook_outputs.py:20,24 and tests/hooks/test_network_egress_guard.py:21; test_claude_code_rules.py:96 closure name
- **A9**
  - tests/unit/test_adapter_base.py -> tests/adapters/test_adapter_base.py; tests/unit/test_where_guidance_buffer.py (added by #49) -> tests/adapters/test_where_guidance_buffer.py
- **A10**
  - tests/hook_runtime/test_event.py -> tests/hook_runtime/dispatch/test_event.py; test_paths.py -> tests/hook_runtime/dispatch/test_paths.py. test_attendance_env.py stays at tests/hook_runtime/ (it pins tests/attendance_env.py).
- **A11**
  - tests/hook_runtime/test_combine.py, test_deps.py, test_dispatch_records.py, test_escape.py, test_failure_policy.py, test_prefilter.py, test_registry.py, test_watchdog.py -> tests/hook_runtime/dispatch/. These stay at tests/hook_runtime/: test_cli_argv.py (cli), test_ruff.py (hook_runtime/ruff.py), test_import_budget.py, test_import_budget_stop.py, test_latency_budget.py (whole package), and the helpers conftest.py, fakes.py, dispatch_kit.py, guard_repo.py, tool_fakes.py, transcript_kit.py.
- **A13**
  - the helpers tests/hooks/conftest.py, pack_repo.py, ruff_kit.py, stop_kit.py, __init__.py -> tests/hook_runtime/handlers/. They then also inherit tests/hook_runtime/conftest.py: its autouse runtime_deps is a pure factory and harmless; drop the duplicated real_proc fixture. Also tests/hooks/test_overlay_activation.py and the chain-created test_hook_summaries.py -> tests/hook_runtime/handlers/.
  - tests/hooks/test_command_convention_guard.py, test_commit_message_convention.py, test_dependency_allowlist_guard.py, test_destructive_command_guard.py, test_exfil_channel_guard.py, test_git_commit_push_policy_guard.py, test_network_egress_guard.py, test_pii_prompt_guard.py, test_secret_content_guard.py, test_secrets_path_guard.py, test_sensitive_data_read_guard.py, test_stop_diff_sweep.py, test_taint_escalation.py, test_wrapper_prefixes_env.py -> tests/hook_runtime/handlers/safety/; test_pack_safety_manifest.py -> tests/hook_runtime/handlers/safety/test_manifest.py.
  - tests/hooks/test_block_precommit_bypass.py, test_clean_code_metrics_nonregression.py, test_coverage_diff_gate.py, test_docstring_nonregression.py, test_gate_weakening_guard.py, test_prompt_output_contract_on_stop.py, test_stop_ci_parity_gate.py, test_stop_ci_parity_gate_exec.py, test_subagent_stop_verify.py, test_tests_with_source_nudge.py -> tests/hook_runtime/handlers/verify/; test_pack_verify_manifest.py -> tests/hook_runtime/handlers/verify/test_manifest.py.
  - tests/hooks/test_local_audit_log.py, test_precompact_checkpoint.py -> tests/hook_runtime/handlers/audit/; test_pack_audit_manifest.py -> tests/hook_runtime/handlers/audit/test_manifest.py.
  - tests/hooks/test_control_plane_guard.py, test_control_plane_verdicts.py, test_eval_task_authoring_lint.py, test_guard_eval_fixtures.py, test_guard_generated_outputs.py, test_resync_on_detector_input_change.py, test_session_start_playbook_briefing.py, test_stop_drift_and_orphan_gate.py, test_validate_then_sync_on_canonical_edit.py -> tests/hook_runtime/handlers/protect/; test_pack_protect_manifest.py -> tests/hook_runtime/handlers/protect/test_manifest.py.
  - tests/hooks/test_error_handling_lint_feedback.py, test_ml_unsafe_deserialization_guard.py, test_notebook_output_hygiene.py, test_prompt_write_scope_guard.py, test_pytest_conventions_feedback.py, test_toolchain_missing_hint.py, test_typing_lint_feedback.py, test_ruff_feedback.py, and the chain-created test_skill_nudge.py -> tests/hook_runtime/handlers/feedback/.
  - Depth edits (7.1.2 rule 11; the files move one or two levels deeper): pack_repo.py:69 `.parent.parent / "fixtures" / "overlays"` -> `.parents[2]` (tests/hook_runtime/handlers/); test_precompact_checkpoint.py:54 `parents[1] / "fixtures"` -> `parents[3]` (tests/hook_runtime/handlers/audit/). `rg "__file__"` over every file A13 moves lists any further case (pack_repo.py:121 resolves a package's `__file__`, not its own, and stays).
- **A14**
  - tests/hook_runtime/test_edit_preview.py -> tests/hook_runtime/handlers/_shared/test_edit_preview.py.
- **A15**
  - tests/hook_runtime/test_agent_transcript.py -> tests/hook_runtime/handlers/verify/test_agent_transcript.py.
- **A16**
  - tests/hook_runtime/test_lint_ast.py, test_sink_writes.py and the chain-created test_ruff_bucket_labels.py -> tests/hook_runtime/handlers/feedback/ (test_sink_scan.py already moved to judges/ in N14).
- **A17**
  - tests/unit/test_hook_policy_merge.py, test_hook_policy_override_rules.py, test_hook_policy_effective.py, test_hook_policy_resolved.py, test_hook_policy_tables.py -> tests/hooks/resolution/test_merge.py, test_override_rules.py, test_effective.py, test_resolved.py, test_tables.py; test_hook_policy_contract.py, test_hook_policy_contract_set.py, test_hook_policy_handler_catalog.py -> tests/hooks/contract/test_contract.py, test_contract_set.py, test_handler_catalog.py; test_hook_policy_labels.py and the chain-created test_hook_policy_advisory.py -> tests/hooks/test_enforcement_labels.py and tests/hooks/test_enforcement_guardrails.py; the chain-created test_hook_policy_guardrails_skill.py -> tests/hooks/test_guardrails_skill.py.
- **A18**
  - tests/unit/test_hook_registrations.py -> tests/hooks/registrations/test_registrations.py; tests/unit/test_hook_registrations_opencode.py -> tests/hooks/registrations/test_opencode.py. tests/adapters/test_claude_launcher.py, test_opencode_hooks.py and test_opencode_shim_node.py stay in the adapters tree, with import rewrites only.
  - Import rewrites of opencode_wire_port: tests/hook_runtime/harness/test_wire_contract.py:36,52 (moved by N21), tests/adapters/test_opencode_hooks.py:33, tests/adapters/test_opencode_shim_node.py:24; the message at test_wire_contract.py:193 names hooks/registrations/templates/opencode-plugin.js.
- **RS-1**
  - tests/unit/test_renderer.py -> tests/rendering/test_jinja.py + tests/rendering/test_formats.py (split by function); tests/unit/test_renderer_hooks.py -> tests/rendering/test_formats_hooks.py; tests/unit/test_render_hook_body.py -> tests/rendering/test_render_hook_body.py; tests/unit/test_rule_registry.py -> tests/rendering/test_rule_registry.py; tests/unit/test_prompt_rule_delivery.py -> tests/rendering/test_prompt_rule_delivery.py; tests/unit/test_no_unsandboxed_jinja.py -> tests/rendering/test_no_unsandboxed_jinja.py
- **AH-1**
  - tests/adapters/test_agent_harness.py -> tests/agent_harness/test_adapter.py; tests/adapters/test_agent_harness_hooks.py -> tests/agent_harness/test_adapter_hooks.py; tests/adapters/test_agent_harness_member_rules.py -> tests/agent_harness/test_adapter_member_rules.py (the designer's names, §9 AC.4.5).
  - tests/agent_harness/test_import_roundtrip.py and test_manifest_roundtrip.py (moved by N12) rewrite their imports of commands.import_harness:import_harness to agent_harness.importer. tests/cli/test_import_harness.py and test_validate_harness.py stay (L8).
- **GC-2**
  - tests/unit/test_guard_config.py -> tests/hooks/guard_config/test_compile.py; tests/unit/test_guard_config_quality.py, test_guard_config_ruff.py, test_guard_config_toolchain.py and the chain-created test_guard_config_skills.py -> tests/hooks/guard_config/test_tables_quality.py, test_tables_ruff.py, test_tables_toolchain.py, test_tables_skills.py; the probe tests (test_guard_config_ruff.py:151-214) -> tests/hooks/guard_config/test_ruff_probe.py. Needs A13 first, which empties tests/hooks/ of the hook-pack tests (H19).
- **not scheduled**
  - tests/unit/test_check_skip_reason.py stays: the catalog-layers predicate slice that would move _format_skip_reason is not scheduled (L12).


### 5.3 Fixed paths and pins to update

Every string, table and pin below names an engine module or path. Each row says what changes and in which PR. "Script" means the rewrite script (5.4) does it; "hand" means the PR author does it, and a named test fails until it is done.

#### 5.3.1 The external contract (never changes, L2)

| What | Where | Rule |
| --- | --- | --- |
| `python -I -m coding_agent_playbook.hook_runtime` | committed launchers `templates/hook_shims/claude-launch.sh:20`, `opencode-plugin.js:86,104` (moved by A18, content unchanged), `tests/fixtures/opencode/playbook-hooks.golden.js`, `tests/hook_runtime/test_import_budget.py:88`, `test_latency_budget.py:63` | frozen; the script refuses a map entry that renames `hook_runtime` |
| `coding_agent_playbook.cli:main` | `pyproject.toml:49-50` (`playbook`, `coding-agent-playbook`) | value unchanged; after N7 it resolves to `cli/__init__.main` (which imports `build_parser` from `cli.parser`); N7 pins it (`test_console_scripts_load_cli_main`) |
| `coding_agent_playbook.hook_runtime.cli:main` | `pyproject.toml:53`, `tests/unit/test_entry_points.py:54` | frozen; `hook_runtime/cli.py` never moves |
| `coding_agent_playbook.adapters.base` | out-of-tree adapters; `adapters/base.py` | frozen; it never moves |
| entry-point group names | `pyproject.toml` `[project.entry-points."coding_agent_playbook.*"]`: `adapters`, `overlays`, `artifact_sources`, `state_sources`, `runners`, `judges`, `metrics`, `checks`, `rubrics`, `gates`, `hook_handlers`; their loaders keep the strings verbatim (`commands/eval.py:67,70` moving to `evals/registry.py` in N11; `evaluators/checks/registry.py` to `grading/check_registry.py` and `gates.py`/`rubrics.py` to `evals/compile/` in N24/N25) | frozen; groups stay even where the review proposed deleting them (`state_sources`, `artifact_sources`, `gates`, `rubrics`), so `StateSource` and `FileSystemStateSource` stay |
| `python -m coding_agent_playbook.cli` child processes | `hook_runtime/handlers/_source_changed.py:56`, `commands/ci.py:99` (and its docstring at :5), `tests/fakes.py:338-342`, `tests/hooks/pack_repo.py:358-362`, `tests/cli/test_ci.py:3,29`, `tests/hooks/test_validate_then_sync_on_canonical_edit.py:6,120`, SPEC.md (3 mentions); the prefix check at `tests/evaluators/test_metrics_gate.py:525` | string unchanged; N7 adds `cli/__main__.py` (moving the `if __name__` tail, `cli.py:479-480`); T0.1 pins `python -I -m coding_agent_playbook.cli --help` |

#### 5.3.2 Entry-point values and pyproject tables

| Line | Today | After | PR |
| --- | --- | --- | --- |
| `pyproject.toml:59` | `agent_harness = "coding_agent_playbook.adapters.agent_harness_adapter:AgentHarnessAdapter"` | `coding_agent_playbook.agent_harness.adapter:AgentHarnessAdapter` | AH-1 |
| `:60` | `agents_md = "...adapters.agents_md_adapter:AgentsMdAdapter"` | `coding_agent_playbook.adapters.agents_md:AgentsMdAdapter` | A9 |
| `:61` | `claude_code = "...adapters.claude_code_adapter:ClaudeCodeAdapter"` | `coding_agent_playbook.adapters.claude_code.adapter:ClaudeCodeAdapter` | A8 |
| `:62` | `continue = "...adapters.continue_adapter:ContinueAdapter"` | `coding_agent_playbook.adapters.continue_:ContinueAdapter` | A9 |
| `:63` | `opencode = "...adapters.opencode_adapter:OpenCodeAdapter"` | `coding_agent_playbook.adapters.opencode:OpenCodeAdapter` | A9 |
| `:64` | `shared_skills = "...adapters.shared_skills_adapter:SharedSkillsAdapter"` | `coding_agent_playbook.adapters.shared_skills:SharedSkillsAdapter` | A9 |
| `:70` | `filesystem = "...sources.filesystem:FileSystemArtifactSource"` | `coding_agent_playbook.catalog.source:FileSystemArtifactSource` | N3 |
| `:73` | `filesystem = "...sources.filesystem:FileSystemStateSource"` | `coding_agent_playbook.config.files:FileSystemStateSource` | N2 |
| `:78-80` | `fake`, `claude_code`, `opencode` runners in `evals.*_runner` | `coding_agent_playbook.evals.run.{fake_runner,claude_code_runner,opencode_runner}:...` | N23 |
| `:85` | `llm = "coding_agent_playbook.evals.judge:LLMJudge"` | unchanged | — |
| `:219` | `[tool.coverage.run] omit = ["*/_typing.py"]` | deleted | CF-2 |
| `[tool.importlinter]` | T0.2's contracts | every move edits them (6.2) | all moves |

The script rewrites the values (5.4.2 rule R-TOML). After a PR changes an entry-point value, the author re-installs the package (`python -m pip install -e ".[dev]"` or `uv sync`) before running the gate: an editable install keeps the old `entry_points.txt`, and `orchestrator.discover_adapters` (`orchestrator.py:286`, `:316`) then raises `ModuleNotFoundError` locally while CI, which installs fresh, stays green. `tests/unit/test_entry_points.py` checks only the group names; `tests/unit/test_sources_filesystem.py:579-589` (moved by N2/N3) loads the two source values.

#### 5.3.3 Import-budget guards and module-name pins

T0.1 makes every engine-module pin go through `engine_module(...)` (a stale name fails collection with `StaleModulePin`) and derives `FORBIDDEN` from the package tree. `engine_module` cannot catch a **same-name module-to-package conversion** (the old name stays importable as the package), so each such move renames its pins by hand (H24):

| Pin | Today | After | PR |
| --- | --- | --- | --- |
| `test_import_budget.py:439,441` | `coding_agent_playbook.detector` | `...detector.facts` | N4 |
| `test_import_budget.py:454`, `:461-463` (branch_local) | `sources.filesystem`, `sources` | `catalog.source` (and `config.files` if the branch loads it) | N3 |
| `_LOCKFILE_MODULE` (`:471`) | `coding_agent_playbook.lockfile` | `...lockfile.model` | N5 |
| `_GIT_MODULE` (`:180, :625, :669, :777, :839`) | `...hook_runtime.git` | `...hook_runtime.git.safe_git` | N18 |
| `_PROTECTED_MODULE` (`:214`), pin (`:262`) | `...hook_runtime.protected`, `...hook_runtime.pin` | `...hook_runtime.config.protected`, `...config.pin` | N16 |
| `:168` (asserted imported) | `...hook_runtime.dispatch` | `...hook_runtime.dispatch.run` (else it passes vacuously on the package) | A10 |
| `:576` | `coding_agent_playbook._guard_config_ruff` | deleted: the derived `FORBIDDEN` entry `coding_agent_playbook.hooks` covers `hooks.guard_config._tables_ruff` by prefix | GC-2 |
| `_CPG_PREFIX` (`:265`) | `...handlers._control_plane_` | two prefixes, `...handlers._shared.control_plane_` and `...handlers.protect._control_plane_` | A14, A16 |
| `:421`, `:472`, `:473`, `:539`, `:579`, `:673`, `:674`, `:774`, `:783` | handler helper modules | their pack paths (`_detector_inputs`, `_briefing_probes`, `_drift` in protect/; `_ruff_pipeline` in _shared/; `_secret_policy`, `_egress`, `_net_targets` in safety/; `_install_cmds` in judges/; `_activity_record` in audit/) | A16, A14, N14, A15 |
| eval-task branch allowance (`:457-465` after T0.1) | the 15 engine modules that branch loads | each move renames or deletes its names: `_toml` -> `toml_writer` (N1); `config_entries`, `config_schema`, `hooks_config`, `_table_shapes` deleted, covered by `config` (N2); `_layers`, `sources` -> `catalog.layers`, `catalog.source` (N3); `metrics_config` -> `metrics_gate` (N22); `evaluators` -> `grading` (N25); `_hook_frontmatter`, `_hook_schema`, `_member_reference` -> `artifacts.*` (A1); `types` -> the `artifacts` modules (A2). Once a package holds a dotted leaf (`catalog.roots`, `detector.pep503`, `artifacts.path_classes`), the allowance names each other submodule the branch loads (for example `catalog._hook_walk`); the failing assertion prints them | each PR |
| `test_import_budget_stop.py:28-30` | `_COORDINATOR`, `_GATE_SCAN`, `_METRICS_GATE` | `_GATE_SCAN` -> `...hook_runtime.judges.gate_weakening` and `_GATE_SCAN_FILES` -> `...judges._gate_weakening_files` (N15); `_METRICS_GATE` -> `...metrics_gate.run` (N22) | N15, N22 |
| `test_import_budget_stop.py:64` | `_DRIFT_FAST_PATH` (from the budget test) | follows `_drift` | A16 |
| `tests/evaluators/test_metrics_gate.py:525-527` | forbids the `cli` and `commands` prefixes while the gate runs in-process (T0.1 wraps them in `engine_module`) | moves to `tests/metrics_gate/test_run.py` (N22); each PR that creates a package above `metrics_gate` in the layers adds its prefix: `precommit` (N9), `agent_harness` (N12), `validation` (A4), `sync` (A6) | N22, N9, N12, A4, A6 |
| `tests/hook_runtime/test_runtime_config.py:499-502` | `lockfile` not loaded; `hook_policy` prefix | `lockfile` stays a package-level check; `hook_policy` -> `hooks` | N5 (the file itself moves in N16), A17 |
| `STAGE_FACTORIES` (`handlers/stop_ci_parity_gate.py:72-86`, 13 `module:function` strings), `_BUILTIN_HANDLER_MODULES` (`hook_runtime/registry.py:69-124`) | handler module paths, built as `f"{_HANDLERS}.<module>..."` from a prefix constant (`stop_ci_parity_gate.py:69-70`, `registry.py:69-73`) | the pack paths; registry names, hook ids and stage names never change (HOOK.md `builtin:` fields and `guard_config.json` persist them). R-STRING cannot rewrite f-strings, so A14 rewrites both tables by hand as full literal strings (and drops `_HANDLERS`); A15 and A16 are then script-covered | A14 (hand), A15, A16 (script) |
| `tests/hook_runtime/test_registry.py` (4 string pins of `...hook_runtime.registry`) | `...hook_runtime.registry` | `...hook_runtime.dispatch.registry` | A11 (script) |

T0.1 adds `tests/hook_runtime/test_stage_factories.py` (every `STAGE_FACTORIES` row resolves, and `test_every_builtin_handler_module_resolves`: every `_BUILTIN_HANDLER_MODULES` value resolves with `importlib.util.find_spec`) and the derived-`FORBIDDEN` machinery; each PR that creates a package confirms its name is derived as forbidden (no hand-kept list).

#### 5.3.4 Exact-module-list probes

These compare a list of loaded module names with `==`, so they fail loudly; the moving PR rewrites the names (script) and adds any new package `__init__` that now loads (hand).

| Probe | Changes in |
| --- | --- |
| `tests/unit/test_sentinel.py:53-66` | N6 |
| `tests/unit/test_canonical_json.py:46-50` | N5 |
| `tests/unit/test_hooks_config.py:377-385` | N2: becomes `[config, config.tables, config.tables._table_shapes, config.tables.hooks]` |
| `tests/unit/test_hook_policy_tables.py:195-207` | N3 (`_layers`), A1 (`_hook_schema`) |
| `tests/unit/test_hook_frontmatter_module.py:42-48` | A1 |
| `tests/unit/test_claude_settings.py:524-543` | N13 (adds `adapters.claude_code` and `adapters.claude_code.settings`), N6 (`_atomic_io`, `_output_io`), N5 (`_canonical_json`, `_lock_drift`, `lockfile`), A18 (the settings merge now imports `hooks.registrations.launcher`) |
| `tests/unit/test_hook_registrations.py:507-517` | A2 (`types`), RS-1 (`renderer` -> `rendering`) |
| `tests/unit/test_prompt_rule_delivery.py:125-127` | RS-1: `[rendering, rendering.prompt_rule_delivery]` |
| `tests/unit/test_rule_registry.py:206-213` | A5/RS-1: replaced by `test_rendering_never_imports_the_sync_context` (section 9 AC.3.6) |
| `tests/adapters/test_claude_code_rules.py:89-96` | N13 (`claude_rule_paths` -> `claude_code.paths`), A8 (`claude_code_adapter`), RS-1 (`renderer`), GC-2 (the probe moves to `sync._protect` with the same three assertions) |
| `tests/adapters/test_agent_skill_rules.py:39-50` | A3 |

#### 5.3.5 Docs-architecture pins

| Pin | Entries | PR |
| --- | --- | --- |
| `tests/unit/test_docs_lifecycle_hooks_spec.py:94-105` `_ENGINE_PATHS` (each path must exist and be named in the SPEC §5.1 tree, SPEC.md:281-330; asserted at :207-213) | `hooks_config.py` -> `config/tables/hooks.py` (N2); `_pep503.py` -> `detector/pep503.py` (N4); `_sentinel.py` -> `generated_output/sentinel.py` (N6); `gate_scan.py` -> `hook_runtime/judges/gate_weakening.py` (N15); `hook_policy/` -> `hooks/` (A17); `hook_registrations/` -> `hooks/registrations/` and `templates/hook_shims/` -> `hooks/registrations/templates/` (A18); `guard_config.py` -> `hooks/guard_config/` (GC-2); `hook_runtime/` and `security/` stay | hand: the §5.1 tree lines are not full paths, so the PR edits the tree and `_ENGINE_PATHS` together. The test file is chain-edited (#50, #53): a soft overlap (H1) |
| `tests/unit/test_docs_lifecycle_hooks_cli.py:263-264` | `security/audit.py` must exist and SPEC §17.4 (SPEC.md:3209) name it -> `hook_runtime/state/audit_log.py` | N19 |
| `tests/unit/test_docs_lifecycle_hooks_cli.py:26-50`, `test_docs_readme_hooks.py:25-41`, `test_docs_migration_hooks.py:23-29`, `test_docs_lifecycle_hooks_spec.py:25-26` | imports of moving symbols (`_SUBCOMMANDS`, `build_parser`, `PR_TITLE_ENV`, `CI_STEPS`, `HOOKS_NOTICE`, `LOCKFILE_SCHEMA`, `_ABORT_OUTCOME`, `config_less_notes`, `_render_fresh_pre_commit`, `OPENCODE_MIN_VERSION`, `hook_policy.advisory`, the registrations facade, `MetricConfig`, `checks.execution` ...) | script, in the PR that moves each module; these files are chain-edited (#53, #56, #58): import-block soft overlaps |
| `tests/unit/test_committed_config.py:230-232, 312-313` (AST guard: `_HOME`, `_WRITERS_HOME`, and that check.py and init.py import the builders) | `_WRITERS_HOME` -> `config/files.py` (N2); `_HOME` -> `config/committed.py` and the file -> `tests/config/test_committed.py` (N10) | hand |
| `tests/unit/test_no_unsandboxed_jinja.py:115`, `tests/unit/test_committed_config.py:237-240` | skip any directory named `resources`: never name a new package `resources` | rule |
| `tests/hook_runtime/test_wire_contract.py:36, :52, :193, :211` | `_PORT_MODULE` name unchanged; its import path and the message at :193 follow the templates | A18 |

#### 5.3.6 Monkeypatch targets and other dotted strings

| String | Where | After | PR |
| --- | --- | --- | --- |
| `coding_agent_playbook.orchestrator.detect` | `tests/cli/test_sync_check.py:458` | valid through N4 (orchestrator binds `detect` by name); then `...validation.context.detect` | A5 |
| `_sync_output.file_drift` | `tests/cli/test_sync_check.py:113` | `sync._output_policy.file_drift` | A6 |
| `_validate_links._scan_markdown_file` | `tests/cli/test_validate_links.py:212` | `validation._links._scan_markdown_file` | A4 |
| `_eval._load_judge_class`, `_load_runner_class` | `tests/cli/test_eval_run.py:261,352,464,495,510` | `evals.registry.load_judge_class`, `load_runner_class` (commands/eval.py calls them through the module) | N11 |
| `...evals.runner.subprocess.run`, `.shutil.which` (14 strings) | `tests/cli/conftest.py:43,48`; `tests/integration/test_shipped_task_gates.py:117,119`, `test_modoboa_cmdi_fixture.py:36-37`, `test_shipped_eval_tasks_c7.py:75,77`, `test_crosscommitvuln_fixtures.py:166-167`; `tests/evaluators/test_eval_runner.py:950-1073` | `...evals.run.harness_runner.*` | N23 |
| `...evaluators.metric.metadata.entry_points`, `...builtins.maintainability.importlib.util.find_spec`, `...checks.registry.metadata.entry_points`, `...execution.project.subprocess.run` | `tests/evaluators/test_metric.py:139,162,324`, `test_check_registry.py:114,137`, `test_execution_project.py:113`, `test_execution_evaluators.py:161` | the `grading.*` paths | N25 |
| `...evaluators.rubrics.metadata.entry_points`, `...evaluators.gates.metadata.entry_points` | `tests/evaluators/test_rubrics_registry.py:104,129`, `test_gate_registry.py:80,107` | `...evals.compile.rubric_registry.*`, `...evals.compile.gate_registry.*` | N24 |
| `sync_cmd.run`, `init_cmd.run` | `tests/unit/test_cli.py:395,417,433` | unchanged; the Command protocol (B9, CP-1, CP-3) must keep resolving `run` at dispatch time so these patches still bite | — |

#### 5.3.7 Templates, catalog and guard tables

- `hook_registrations/_templates.py:20` `_TEMPLATE_DIR = ("templates", "hook_shims")` becomes `("hooks", "registrations", "templates")` (A18); its docstring (`:1, :6, :24`) and `catalog/README.md:127` follow. The test oracle `opencode_wire_port.py` stays beside the template it ports and gets no `__init__.py` (it is imported as a namespace package).
- `templates/precommit/` does not move: `commands/init.py:372` and `tests/_catalog.py:28` find it through `resources.files(ENGINE_PACKAGE)/"templates"/"precommit"`, and `tests/integration/test_resources_self_contained.py:81` keeps its prefix.
- No catalog file names an engine module. `catalog/core/hooks/**/HOOK.md` bind builtins by registry name (`builtin: secret_path_guard`), never by module path. `coding_agent_playbook.plugins.<name>` (`catalog/README.md:175-191`, `catalog/plugins/*/README.md`, `.github/workflows/ci.yml:145`) is an overlay label, not a module: no new package may be named `plugins/`. Packaging is unaffected: the wheel's force-include of `catalog` as `coding_agent_playbook/_catalog` does not collide with the `catalog/` package.
- The guard tables `hook_runtime/handlers/_control_plane_paths.py:82-87` list catalog directories and `hook_runtime/protected.py:66` `ENGINE_RESOURCES_ID` is a label; neither names an engine module. GC-4 builds `ENGINE_RESOURCES_ID` from the shared `RESOURCE_ROOT_ID_FORMAT` (GC-1 only moves the format verbatim).
- `.github/workflows/ci.yml:54` (a comment citing `tests/hook_runtime/test_simulate.py`) follows N20; the fixture paths at `:55-58` do not move.

#### 5.3.8 Living docs and docstrings

- SPEC.md: about 80 module-path mentions for the root modules, 61 for `cli.py` and `commands/`, about 60 for `evaluators/` and `evals/` (§15, §21), and the §5.1 tree (`SPEC.md:281-330, 333, 346-348`). The script rewrites the prefixed forms; the §5.1 tree and the diagram at `:90, :117-118` are hand-edited by each move that changes a line in them. `SPEC.md:201` ("imports nothing outside `hook_runtime.*`, `security.*`") is reworded by N15 and A12 to name the stdlib leaves. History is a record: the top **Changelog** list (`SPEC.md:11-26`) and the `## Changelog` section (`SPEC.md:3832` to the end of the file, 4040 lines at the baseline) name module paths of their time (for example `adapters/_skill_writer.py` at `:18`, and `sources/filesystem.py`, `commands/_sync_orphans.py`, `commands/_output_locations.py`, `commands/_committed_config.py`, `commands/_precommit_merge.py`, `harness/manifest.py`, `evaluators/types.py` in `:3855-3993`). T0.0 wraps both ranges in `<!-- module-moves: keep -->` markers, so R-DOC skips them and `check` does not report them, and `test_spec_history_has_keep_markers` (5.4.4) pins that both marker pairs exist. A module-map note that cites a SPEC.md line inside these ranges (`:3838`, `:3843`, `:3895`, `:3913`, `:3916`, `:3922`, `:3928`) names a record: the line stays as written.
- README.md: only the `-m hook_runtime` mention (fixed) and the concept-level architecture overview at `README.md:80-160` (`:158` "sources, renderer, adapters, CLI"), refreshed once by D1. The adapter ids it uses (`agent_harness`, `claude_code`, `shared_skills`) are config values and are never rewritten.
- MIGRATION.md: the script maintains one "Module paths" section between `<!-- module-moves:start -->` and `<!-- module-moves:end -->` (created by N1), one row per old public path -> new path, for out-of-tree code (only `adapters.base` is kept). N25 also adds one sentence for out-of-tree Metric, Check, rubric and gate authors (`coding_agent_playbook.evaluators.*` is now `coding_agent_playbook.grading.*`, the rubric and gate registries `evals.compile.*`, no shim). Record rows (`MIGRATION.md:419, :542, :863-864, :907, :942-944, :962-965`) are wrapped in `<!-- module-moves: keep -->` markers by T0.0 and never rewritten.
- catalog/README.md: `:127` (`src/coding_agent_playbook/templates/hook_shims/`, A18).
- Module docstrings and comments that name moved paths are rewritten by the script when the reference is prefixed or dotted (`_toml.py:7,30,282,291`; `catalog.py:9-10`; `config_entries.py:11`; `config_schema.py:8-9`; `hooks_config.py:13`; `metrics_config.py:3-6`; `_hook_schema.py:14-15`; `_hook_frontmatter.py:3-5`; `sources/base.py:1-6`; `sources/_hook_walk.py:6`; `orchestrator.py:1-25`; `commands/__init__.py:3-5`; `hook_registrations/_templates.py:1,6,24`; `commands/init.py:361-384`; `evaluators/metrics_gate.py:8`; `harness/manifest.py:11`; `hook_runtime/__init__.py:8-9`; `hook_runtime/handlers/__init__.py:4`; `commands/validate.py:121`; `hook_policy/handler_catalog.py:5`; the Sphinx roles at `evals/validator.py:3`, `evaluators/policy.py:9`, `cli.py:5,441`, `commands/sync.py:30`, `commands/_validate_hooks.py:4`, `commands/init.py:290`, `tests/fakes.py:17,278,321`, `tests/cli/test_eval_aggregate_render.py:3`, `tests/cli/conftest.py:11`). A bare filename (`renderer.py`, `config.py`) is only reported (5.4.3) and reworded by hand.
- Not rewritten: `specs/*.md` (records, L9), `docs/adr/*`, CONTEXT.md (its `_Avoid_: evaluators` is a glossary entry), `catalog/**` except `catalog/README.md`, `tests/fixtures/**`. `specs/prS-skills-context.md` is the live chain spec: when N16 or N19 moves a module it cites by line (`session.py:96-103`, `state.py:147-150`, `paths.py:117-153`, `globs.py:57-71`, `combine.py:167-183`, `_ruff.py:212-213`, `registry.py:70-127`), the loop adds one note to the affected open ticket instead of editing the spec.

### 5.4 The rewrite script (T0.0)

Every move PR runs the same script, and so does every chain ticket that rebases onto a move (2.2, 5.4.6). It lives under `tests/architecture/` so that ruff, mypy and pytest already cover it, and so that the CI gate stays four commands.

#### 5.4.1 Files and interface

| File | Content |
| --- | --- |
| `tests/architecture/module_moves.py` | the script, stdlib-only; `python -m tests.architecture.module_moves apply` rewrites the working tree, `python -m tests.architecture.module_moves check` lists stale references (exit 1) |
| `tests/architecture/move_map/<pr>.toml` | the cumulative move map, one file per move PR (`n01.toml`, `a10.toml`, `gc-2.toml`; lower-case PR id), and nothing is ever removed, so a branch written against any older layout is rewritten in one `apply`. One file per PR, not one shared file, so two parallel move PRs never edit the same map file (an append at the end of a shared file conflicts every time). The directory is not named `module_moves/`: a package of that name would shadow `module_moves.py` (the A10 pitfall) |
| `tests/architecture/test_module_moves.py` | unit tests of each rule on strings, the idempotency property, and `test_tree_has_no_stale_module_paths` (runs `check` over the repository) |

```python
@dataclass(frozen=True, slots=True)
class ModuleMove:
    """One old dotted module (or package, with ``package=True``) and its new name."""

    pr: str
    old: str
    new: str
    package: bool = False


@dataclass(frozen=True, slots=True)
class NameMove:
    """Names that leave ``old`` for ``new``: a split, or a removed re-export."""

    pr: str
    old: str
    new: str
    names: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class MoveMap:
    """The composed map: every ``move_map/*.toml`` file, chains resolved by name, not by file order."""

    modules: tuple[ModuleMove, ...]
    names: tuple[NameMove, ...]

    def resolve(self, dotted: str, tree: Path) -> str | None:
        """The current spelling of ``dotted`` (a module or ``module.attr``), or None if current.

        Example: ``resolve("coding_agent_playbook._toml", repo)`` -> ``"coding_agent_playbook.toml_writer"``.
        """


def load_map(path: Path) -> MoveMap:
    """Read and compose every ``*.toml`` under ``path`` (the ``move_map/`` directory); raise
    ``ValueError`` naming an entry that renames a frozen name (5.4.4), that is not
    idempotent (``new`` under ``old`` with ``package=True``), or whose ``old`` another file
    also moves (two PRs moving one module is a planning error, not a merge order)."""


def apply(repo_root: Path, moves: MoveMap) -> list[Path]:
    """Rewrite every file the rules of 5.4.2 cover; return the files changed."""


def check(repo_root: Path, moves: MoveMap) -> list[str]:
    """``path:line: <old> -> <new>`` for every stale reference, plus the ``review:`` lines of 5.4.3."""
```

The map format, one TOML array per entry kind:

```toml
[[module]]
pr = "N1"
old = "coding_agent_playbook._toml"
new = "coding_agent_playbook.toml_writer"

[[module]]
pr = "N25"
old = "coding_agent_playbook.evaluators"
new = "coding_agent_playbook.grading"
package = true # submodules follow by prefix unless another entry names them (the longer `old` wins)

[[names]]
pr = "N2"
old = "coding_agent_playbook.config"
new = "coding_agent_playbook.config.schema"
names = ["ConfigError"]

[[path]]
pr = "N1"
old = "_toml.py"
new = "toml_writer.py"
```

`[[path]]` entries are derived from `[[module]]` entries (`coding_agent_playbook.x.y` is `x/y.py` or `x/y/`) and written by hand only for a split (one primary destination for docs, for example `renderer.py` -> `rendering/formats.py`) and for test files that move (`tests/hooks/` -> `tests/hook_runtime/handlers/`).

#### 5.4.2 What it rewrites

A dotted name is **current** when its longest module prefix resolves to a module or package in the working tree and the remainder is a submodule of it or a top-level name defined in that module's source (read with `ast`). Only names that are not current and that the map resolves are rewritten. This makes every rule idempotent, and it handles a same-name module-to-package conversion (`coding_agent_playbook.config.Config` is stale once `config/__init__.py` holds only a docstring; `coding_agent_playbook.config.schema` is current).

| Rule | Files | What |
| --- | --- | --- |
| R-IMPORT | `src/**/*.py`, `tests/**/*.py` | `import a.b [as c]` and `from a.b import x, y` (located with `ast`, edited as text so comments and `TYPE_CHECKING` or function-level indentation stay): the module part is rewritten; when names of one statement go to different modules (a `[[names]]` entry), the statement is split into one `from` per destination, keeping aliases. `from coding_agent_playbook import mod [as x]` and `from pkg import submod` (a submodule import, detected against the working tree) become `from <new parent> import <new leaf> as <old local name>`, so call sites stay unchanged; the alias is dropped when it equals the leaf. A relative import is refused (the code base has none). **Same-name conversion:** when an entry's `old` is now a package (the module became a same-name package: `catalog`, `detector`, `config`, `lockfile`, `cli`, `hook_runtime.{config,git,shell,state,dispatch}`), the currentness test above cannot see that a module-object import is stale, because `from coding_agent_playbook import catalog` and `import coding_agent_playbook.detector as detector` still resolve, to the docstring-only package. So a module-object import of such an `old` (`from <parent> import <leaf> [as x]` or `import <old> as x`) is always rewritten to `from <old> import <new leaf> as x`, using the entry's `new` (`from coding_agent_playbook.catalog import roots as catalog`), and the attribute uses (`catalog._PACKAGE_DIR`, `detector.detect`) then resolve unchanged. The baseline has 6 such test files for N3 (`tests/unit/test_catalog.py:13`, `test_sync_preflight.py:9`, `test_sources_filesystem_bundled.py:18`, `test_cli.py:10`, `tests/hook_runtime/test_protected.py:251`) and 2 for N4 (`tests/hooks/test_resync_on_detector_input_change.py:17`, and the src sites N4 lists) |
| R-STRING | the same files | string constants that are exactly a stale dotted module, a stale `module.attr` (monkeypatch targets), or a `module:attr` (entry-point values). An f-string or a string built from a prefix constant is not a constant and is never rewritten: `STAGE_FACTORIES` (`handlers/stop_ci_parity_gate.py:69-86`) and `_BUILTIN_HANDLER_MODULES` (`hook_runtime/registry.py:69-80`) build every row as `f"{_HANDLERS}.<module>..."`, so A14, the first pack split, rewrites both tables by hand as full literal strings (the packs split the common prefix anyway), and later moves are script-covered (5.3.3) |
| R-TOML | `pyproject.toml` | entry-point values under `[project.scripts]` and `[project.entry-points.*]` (never the group headers), and every full dotted name in `[tool.importlinter]` (`source_modules`, `forbidden_modules`, `ignore_imports`, `modules`). Container-relative names (`layers`, `exhaustive_ignores`) are hand-edited; the tests of section 6 print what they expect |
| R-DOC | SPEC.md, README.md, MIGRATION.md, catalog/README.md, `.github/workflows/ci.yml` comments, and docstrings and comments in `src/` and `tests/` | prefixed forms only: `coding_agent_playbook.<dotted>` (in backticks, Sphinx roles `:mod:`/`:func:`/`:class:`, or plain), `src/coding_agent_playbook/<path>`, and `<package dir>/<file>.py` or `<package dir>/` where the directory is an engine package or test directory and the whole relative path is in the map (`commands/_sync_render.py`, `sources/filesystem.py`, `tests/hooks/`). A `:line` or `:a-b` suffix is kept as is (best effort, L9). Lines inside `<!-- module-moves: keep -->` markers are skipped |
| R-MIGRATION | MIGRATION.md | regenerates the section between `<!-- module-moves:start -->` and `<!-- module-moves:end -->` from the composed map (public modules only) |
| R-FORMAT | the files it changed | runs `ruff check --fix --select I` (import order) and `ruff format` on changed `.py` files and on changed `.md` files, because `ruff format --check .` also formats the Python code blocks of markdown files and a longer import line can need a reflow |

#### 5.4.3 What it must not touch, and what it only reports

- **Frozen names** (L2): `coding_agent_playbook.hook_runtime` as a module or package, `coding_agent_playbook.hook_runtime.cli`, `coding_agent_playbook.cli` (the module path; `cli:main`), `coding_agent_playbook.adapters.base`, and every entry-point group name. `load_map` refuses an entry whose `old` is one of them or (with `package=True`) contains one.
- **Segment boundaries.** `coding_agent_playbook.harness` is rewritten only as that exact prefix: `coding_agent_playbook.hook_runtime.harness` (`tests/hook_runtime/test_import_budget.py:39`, `tests/unit/test_hook_policy_tables.py:227`) and the adapter id `agent_harness` stay. A path `harness/` is rewritten only after `coding_agent_playbook/` or as a whole doc path in the map; the harness directory name `evals/` of the Agent Harness format (`tests/harness/test_manifest_roundtrip.py:100,444,491`, `tests/harness/test_parser.py:65,151,157`, `adapters/agent_harness_adapter.py:22`, `harness/parser.py:101`, `commands/validate_harness.py:67` and others) is never rewritten.
- **Not modules:** overlay labels (`coding_agent_playbook.plugins.*`, `coding_agent_playbook.packs.*`), the `<repo-local>` label, adapter ids and config values in docs (README.md:100, :285, :469, :549-557; MIGRATION.md:102), hook ids and registry names.
- **Bare root filenames** (`config.py`, `types.py`, `base.py`, `filesystem.py`, `links.py`, `cli.py`, `renderer.py`): they also name consumer-file samples in tests (`tests/hooks/test_stop_diff_sweep.py:51`, `tests/hook_runtime/test_protected.py:156`, `tests/hooks/test_guard_generated_outputs.py:77`, `hook_runtime/handlers/secret_content.py:103`). `check` prints them as `review: path:line: bare 'renderer.py'` for the PR author; it never rewrites them and they never fail the test.
- **Never opened:** `specs/*.md`, `docs/adr/*`, CONTEXT.md, `catalog/**` except `catalog/README.md`, `tests/fixtures/**`, `.venv/`, `__pycache__/`, build output, and the harness files (`AGENTS.md`, `CLAUDE.md`, `.claude/`, `.opencode/`, `.agents/`, `shared_skills/`).

#### 5.4.4 Tests (T0.0)

`tests/architecture/test_module_moves.py`, each on in-memory sources and a `tmp_path` tree:

- `test_import_rewrites_the_module_part`, `test_from_import_splits_by_destination_and_keeps_aliases`, `test_submodule_import_keeps_the_local_name`, `test_type_checking_and_function_level_imports_keep_their_indentation`, `test_relative_import_is_refused`;
- `test_string_rewrites_module_attr_and_colon_forms`, `test_current_names_are_never_rewritten` (`config.schema` after the conversion), `test_same_name_conversion_rewrites_stale_attributes`, `test_same_name_conversion_rewrites_module_object_imports` (`from coding_agent_playbook import catalog` and `import coding_agent_playbook.detector as detector` after their conversions);
- `test_pyproject_rewrites_values_never_group_names`, `test_frozen_names_are_refused`;
- `test_doc_rewrites_prefixed_forms_and_keeps_line_suffixes`, `test_doc_skips_keep_markers`, `test_spec_history_has_keep_markers` (the two SPEC.md ranges of 5.3.8 and the MIGRATION.md record rows sit inside keep markers in the real tree), `test_hook_runtime_harness_and_adapter_ids_stay`, `test_bare_filenames_are_reported_not_rewritten`;
- `test_apply_is_idempotent` (applying the map twice changes nothing), `test_chained_moves_compose` (`harness` -> `agent_harness` (N12), then `adapters.agent_harness_adapter` -> `agent_harness.adapter` (AH-1));
- `test_migration_section_lists_public_moves`;
- `test_tree_has_no_stale_module_paths`: runs `check` on the repository and fails listing `path:line: old -> new` with the fix (`python -m tests.architecture.module_moves apply`). This is what tells a chain ticket that rebased onto a move how to repair its branch.

T0.0 ships the empty map (the test passes vacuously until N1 adds the first entry) and the `keep` markers in MIGRATION.md and SPEC.md.

#### 5.4.5 How a move PR uses it

1. `git mv` the files (and split modules by moving whole top-level definitions, verbatim).
2. Write the PR's `[[module]]`, `[[names]]` and `[[path]]` entries to its own `tests/architecture/move_map/<pr>.toml`.
3. `python -m tests.architecture.module_moves apply`, then `python -m tests.architecture.module_moves check` (no stale line; read every `review:` line).
4. Hand edits: the SPEC §5.1 tree, `_ENGINE_PATHS`, the contract edits of 6.2, the same-name-conversion pins of 5.3.3, the f-string tables `STAGE_FACTORIES` and `_BUILTIN_HANDLER_MODULES` (A14 only, 5.3.3), the `__file__`-relative paths of moved test files and of `catalog/roots.py` (7.1.2 rule 11), new package `__init__.py` docstrings, and the call sites of any name the move renames because it now crosses a package (the script rewrites module paths, never names).
5. The gate (7.1).

#### 5.4.6 How a chain ticket rebases onto a move

A chain ticket that conflicts with a move on import lines takes its own side of each conflicting hunk, then runs `apply`: the cumulative map rewrites its imports, strings and docs to the new layout. If the ticket created a file the move would have moved, the ticket keeps it where its spec says and the move's area owner moves it later (for example #58's `_guard_config_skills.py`, moved by GC-2). If the ticket added an import of a private module of another package, or a new top-level module, after T0.2, it adds the matching `private-modules` line or the `exhaustive_ignores` and forbidden-list entries in the same ticket (section 6, 0.8): the contract tests print what they expect.

## 6. Enforcement: lane 0 guards and import contracts

Lane 0 is the prerequisite of every move: no N or A PR starts before T0.0, T0.1 and T0.2 have merged. Section 6.1 is the contracts designer's lane-0 design, verified on a copy of the baseline with import-linter 2.15 on Python 3.12.12 and 3.13.9. This spec changes it in these places only, each marked in the text:

- T0.0, the rewrite script (5.4), joins lane 0 (no designer covered it; H21).
- T0.1 also adds `tests/cli/test_module_entry.py`, which pins `python -I -m coding_agent_playbook.cli --help` before N7 turns `cli.py` into a package (from the root mapper).
- `metrics_gate` moves from the `agent_harness | evals | metrics_gate | precommit` tier to its own layer below `skills` (H5).
- The `ignore_imports` comments name the PR of section 7 that removes each line, and the worked examples of 0.7.3 follow the harmonised plan (H3, H5).
- `cli/__init__.py` becomes the second permanent exception of `test_package_inits.py` when N7 creates it, narrowed to "defines `main` and its private error-mapping helpers only" (H7).

Sections 6.2 to 6.4, after the designer's text, list the contract edits of every PR, every violation the area mappers found with the PR that fixes it, and the end state.

### 6.1 Lane 0: module-name guards and import contracts (contracts designer, harmonised)

Lane 0 runs now, beside the #49-#62 chain (L1, L12), and changes no file under `src/`. It does two things before any package moves:

1. It hardens every guard keyed on a module name, so a moved module fails the guard loudly instead of passing it vacuously.
2. It adds import-linter contracts that enforce ADR 0002's two rules from pytest (L4): the declared dependency direction, and "an underscore module is imported only from inside its own package". The CI gate stays `ruff check .`, `ruff format --check .`, `mypy`, `pytest -q`.

Every contract holds on today's tree when it lands. Each gap it finds today is written down as a commented burn-down entry, and every move PR tightens the contracts (section 0.7). The burn-down lists can only shrink, because an entry that no longer matches anything fails the run.

Terms: a package's *interface* is its non-underscore modules (L5); its underscore modules are its *implementation*. The private-module contract keeps callers on the interface. The layer contract keeps each package's *leverage* flowing one way. All the rules sit in one pyproject table (*locality*).

All code below was run on a copy of this branch (`docs/package-layout`, i.e. `ef19a0a` plus the CONTEXT.md and ADR 0002 edits) with import-linter 2.15 on Python 3.12.12 and 3.13.9. It passes ruff 0.17.0 (`ruff check`, `ruff format --check`) and strict mypy over the whole tree. The following pass on both Python versions: every new test, both budget files, the 11 edited probe files, and the tests that read pyproject.toml (`tests/integration/test_dogfood_config.py`, `test_dev_precommit_config.py`, `test_ruff_scope.py`, `tests/unit/test_entry_points.py`, `test_package_init.py`). The full suite was not run end to end: it ran its first 1,163 tests with no failure and was stopped, because it takes more than an hour on this machine. CI must give the final verdict. The verified files are kept under `/private/tmp/claude-501/-Users-msobroza-Projects-coding-agent-playbook-coding-agent-playbook--claude-worktrees-python-best-practices-skills-c9552a/6544398b-ab5a-45bd-b04b-8eac201dbc22/scratchpad/layout-spec/lane0-enforcement/repo/`.

#### 0.1 Goal

1. A guard that names an engine module fails as soon as that module moves or is renamed. This covers the import-budget probes, the probe tests that assert something is *not* loaded, and the hook-runtime stage table.
2. The engine modules the hook hot path must not load are derived from the package tree, never hand-listed. A new top-level package is forbidden on the hot path until someone admits it on purpose.
3. import-linter checks, from one pytest test:
   - the layer order of ADR 0002;
   - that the hook runtime and the grading kernel are stacks that import only stdlib leaves;
   - that the leaves import nothing else;
   - that no command imports another command;
   - the underscore rule.
4. Every contract holds today. Every known violation is an explicit `ignore_imports` (or `exhaustive_ignores`) entry with a comment naming the PR that removes it.

#### 0.2 Scope, tickets and order

| Ticket | When | Title (Conventional Commits) | Files |
|---|---|---|---|
| T0.0 | now | `test(layout): add the module-path rewrite script` | new `tests/architecture/module_moves.py`, `move_map/` (empty but for a `README` line), `test_module_moves.py`; `keep` markers in MIGRATION.md and SPEC.md (section 5.4 of this spec; added by the harmonisation, H21) |
| T0.1 | now | `test(layout): pin engine module names and derive the hot-path forbidden list` | new `tests/engine_modules.py`, `tests/cli/test_module_entry.py` (0.5.9), `tests/architecture/__init__.py`, `tests/architecture/test_engine_modules.py`, `tests/architecture/test_module_pins.py`, `tests/hook_runtime/test_stage_factories.py`; edits `tests/hook_runtime/test_import_budget.py`, `tests/hook_runtime/test_import_budget_stop.py` and 11 probe tests (section 0.5.4) |
| T0.2 | after T0.1 merges | `test(layout): enforce the ADR 0002 import contracts with import-linter` | `pyproject.toml` (dev dependency and `[tool.importlinter]`), `.gitignore`, new `tests/architecture/private_modules_contract.py`, `tests/architecture/test_import_contracts.py`, `tests/architecture/test_private_modules_contract.py`, `tests/architecture/test_package_inits.py` |
| T0.3 | after #62 merges | `test(layout): pin the module names deferred for the skills chain` | `tests/adapters/test_claude_code_rules.py:95-96`, `tests/unit/test_rule_registry.py:211`; empty `_DEFERRED_UNTIL_CHAIN_MERGES` in `tests/architecture/test_module_pins.py` |

T0.2 imports `tests.engine_modules`, so it follows T0.1. T0.0 shares only the empty `tests/architecture/__init__.py` with them; whichever lands second keeps the file. These are sequential PRs, not stacked ones. Both are test and config only, so neither "moves files or changes behaviour" (L1).

Out of scope:
- any `src/` change;
- the moves themselves;
- SPEC.md, README.md, MIGRATION.md and catalog/README.md (L9 applies to move PRs). CONTEXT.md already has the four terms (L7).

#### 0.3 Decisions taken in this lane

| # | Decision | Why (verified) |
|---|---|---|
| D0-1 | `FORBIDDEN` in the import-budget test is derived from the package tree: every top-level engine module except `hook_runtime` and `STDLIB_LEAVES`, plus the engine's runtime dependencies read from pyproject.toml. Today's list names 9 engine packages (`tests/hook_runtime/test_import_budget.py:48-69`). | A new package (`config/`, `catalog/`, `rendering/`, `sync/`, `metrics_gate/`, `grading/` …) would otherwise be allowed on the hot path by default. The derived list is fail-safe: a new package is forbidden by default. |
| D0-2 | `STDLIB_LEAVES` = `_atomic_io`, `_canonical_json`, `_lock_drift`, `_pep503`, `_pyproject_deps`, `_sentinel`, `catalog`, `lockfile`, `security`. | These are exactly the engine modules the hook runtime and the grading kernel import today outside their deferred branches (AST scan, section 0.4). All nine import only the stdlib and each other (contract `stdlib-leaves` holds). `catalog` is in the list because `hook_runtime/protected.py:242` loads it on the protected-edit branch: the derived list without it failed 4 probes. |
| D0-3 | Every engine module name a test pins goes through `engine_module(name)`. It resolves the name with `importlib.util.find_spec` when the constant is defined and raises `StaleModulePin` if the name does not resolve. | A stale pin fails at collection, naming the module. Without this, `{_METRICS_GATE, _GATE_SCAN}.isdisjoint(imported)` (`tests/hook_runtime/test_import_budget_stop.py:114`) stays true forever once either module moves. |
| D0-4 | A static scan (`tests/architecture/test_module_pins.py`) rejects the four raw spellings that can pass vacuously: `"<engine name>" not in x`, a module-level constant, a set display not compared with `==`, and a `startswith("<engine name>")` prefix. | It enforces D0-3 on tests written later, including the chain's. Equality lists and positive `in` checks already fail loudly, so the scan leaves them alone. |
| D0-5 | import-linter is pinned exactly: `import-linter==2.15`. | 2.15 is the current release (PyPI, 2026-09-04, more than two weeks old). The custom contract uses `importlinter.application.contract_utils`, the helper the built-in contracts use for `ignore_imports`. That helper is not part of the documented `importlinter` API, so an upgrade is a deliberate PR that re-runs `tests/architecture/`. |
| D0-6 | The contracts run in a child interpreter: `sys.executable -c "…lint_imports(config_filename='pyproject.toml', no_cache=True, no_logo=True)"`, with cwd at the repo root. | `importlinter.cli.lint_imports` calls `logging.config.dictConfig` and `sys.path.insert(0, os.getcwd())`, both process-wide side effects that must stay out of the pytest process. The child sees this checkout with no cache. It runs in about 1 s on 396 modules. It uses `sys.executable`, not a `lint-imports` binary on PATH. |
| D0-7 | Rule (2) is a custom contract type (`private_modules`, in `tests/architecture/private_modules_contract.py`). It is neither the built-in `protected` contract nor a separate AST check. | `protected` takes one fixed `allowed_importers` list per contract (`importlinter/contracts/protected.py`, illegal importers = importers minus allowed minus protected). "Its own package" would need one contract per package, kept in step with every move by hand. The custom type derives the owner from the module name. It reuses the same grimp graph, `ignore_imports` semantics (including the unmatched → error default) and report as the other contracts, inside the same `lint_imports` run. |
| D0-8 | `exclude_type_checking_imports = false`. | An interface that names a higher layer's type depends on that layer. All six contracts hold with type-only imports counted. |
| D0-9 | `include_external_packages = true`, and the two stacks plus the leaves forbid the engine's runtime dependencies (`jinja2`, `packaging`, `yaml`, derived from `[project].dependencies`). | This statically enforces "stdlib-only" for every branch, not only the branches the probes run. With the deferred-branch ignores in place, the hook runtime has no direct or transitive third-party import. `radon` (optional `metrics` extra) stays allowed in the grading kernel. |
| D0-10 | `hook_runtime` is not a layer. It is a separate forbidden contract, and its deferred branch imports are `ignore_imports` lines of the form `"<importing module> -> <package>.**"`. | grimp records function-scope imports like any other: `hook_runtime/protected.py:242` reports `is_lazy: False`, because `is_lazy` means the PEP 810 `lazy import` syntax. A static contract therefore cannot tell "at import time" apart. The per-branch import-time budget stays the job of the `-X importtime` probes. The ignore lines are the explicit inventory of the runtime's deferred branches. |
| D0-11 | The layer contract is written in its target form now: not-yet-existing packages are optional `(name)` layers, `exhaustive = true`, and `exhaustive_ignores` lists the 49 old-layout top-level modules. Tests pin both lists to the tree. | import-linter skips a missing optional layer, so a typo would never be checked, and it silently accepts a stale `exhaustive_ignores` entry (both verified). The tests close those two gaps. `exhaustive` makes a new top-level module fail until it is placed. |
| D0-12 | A package `__init__.py` holds only a docstring (L5), enforced by `tests/architecture/test_package_inits.py`. The 8 non-root inits that hold code today form a shrinking baseline. | New packages created by moves cannot add re-exports or shims (L2). |
| D0-13 | Rule (2) applies to `src/` only. Tests may import private modules. | Tests are outside `root_packages`. 25 test files import `hook_runtime.handlers._*` today, and L8 keeps tests white-box. |

#### 0.4 Facts the design relies on (verified)

**import-linter 2.15**: requires `grimp>=3.17`. The documentation index lists the contract types `forbidden`, `protected`, `layers`, `independence`, `acyclic_siblings` and custom types (`importlinter.Contract`, `ContractCheck`, `fields`, `output`; registered via `contract_types = ["name: dotted.path.Class"]`). Behaviour observed by running 2.15 against the copy:

- `ignore_imports` wildcards: `"X -> P.**"` matches the modules under `P` but not `P` itself (0 matches for `gate_weakening -> gate_scan.**`, 1 for `-> gate_scan`). So an edge into a module uses its exact name, and an edge into a package's submodules uses `P.**`.
- An ignored import that matches nothing aborts the run with `No matches for ignored import <expr>.`, exit 1. This happens for the built-in types and for the custom type (default `unmatched_ignore_imports_alerting = "error"`).
- A missing non-optional layer fails (`Missing layer in container 'coding_agent_playbook': module … does not exist.`). A missing optional `(layer)` is skipped silently. A non-existent `exhaustive_ignores` entry is accepted silently.
- With `exhaustive = true`, a new top-level module fails `engine-layers` ("must be declared as a layer").
- Layers follow chains through modules outside the layers. Example: `adapters → _typing → evals.task`.
- `include_external_packages = true` adds every non-engine top-level package as a squashed node, the stdlib (`tomllib`, `argparse`) included. So only third-party names are forbidden statically. `tomllib` stays a probe-only, branch-local concern.

**Mutation checks**: each line was applied to the copy, linted, then reverted.

| Mutation | Result |
|---|---|
| `catalog.py` imports `commands.sync` | `engine-layers`, `stdlib-leaves`, `hook-runtime-stack`, `command-independence` BROKEN |
| new `src/coding_agent_playbook/newthing.py` | `engine-layers` BROKEN (must be declared as a layer) |
| `hook_runtime/globs.py` imports `renderer` (module level, or inside a function) | `hook-runtime-stack` BROKEN |
| `_sentinel.py` imports `renderer` | `stdlib-leaves`, `hook-runtime-stack` BROKEN (through the leaf) |
| `_sentinel.py` imports `yaml` | `stdlib-leaves`, `hook-runtime-stack` BROKEN (`… is not allowed to import yaml`) |
| `lockfile.py` imports `commands.sync` under `TYPE_CHECKING` | `engine-layers`, `stdlib-leaves`, `hook-runtime-stack`, `command-independence` BROKEN |
| `commands/check.py` imports `adapters._json_edits` | `private-modules` BROKEN: `- coding_agent_playbook.commands.check -> coding_agent_playbook.adapters._json_edits (l.255): private to coding_agent_playbook.adapters` plus the guidance line |
| `commands/metrics.py` imports `commands.eval` | `command-independence` BROKEN |
| new `rendering/__init__.py` importing `commands.sync` | `engine-layers` BROKEN (the optional layer became active) |
| `evaluators/policy.py` imports `evals.task` | `grading-kernel` BROKEN |
| extra ignore line `commands.metrics -> commands.eval` | run aborts: `No matches for ignored import …` |
| new `newpkg.py` imported by `hook_runtime/dispatch.py` | old `test_hot_path_branches_import_no_forbidden_module`: 3 passed (vacuous); derived list: 3 failed |

**Today's tree** (`src/coding_agent_playbook`, 58 top-level modules, grimp 3.17):

- Package-level edges at run time (type-only excluded) form one 15-module cycle: `adapters, config, evals, evaluators, gate_scan, harness, hook_policy, hook_registrations, hook_runtime, metrics_config, orchestrator, renderer, rule_registry, skill_document, sources`. So today the layer contract can check only the 9 target names that already exist (`cli, commands, evals, adapters, catalog, config, detector, lockfile, security`). It finds one violation: `adapters → evals`, via `_typing.py:23` and via `adapters/_prior_output.py:110 → sources/filesystem.py:21,34`.
- Hook runtime imports outside itself, as (importer → imported): eager/deferred/type-only.
  - Leaves:
    - `security.*`: 22 eager, 13 deferred and 13 type-only import statements;
    - `_pep503`: `handlers/_dependency_tiers.py:19`, `_install_cmds.py:30`, `_manifest_diff.py:29`, `dependencies.py:33`;
    - `_pyproject_deps`: deferred at `_detector_inputs.py:149` and `_manifest_diff.py:114`;
    - `_sentinel`: `_drift.py:30`, `protected.py:38`;
    - `lockfile`: `_drift.py:37`;
    - `_canonical_json`: `_control_plane_json.py:28`;
    - `catalog`: deferred, `protected.py:242`.
  - Deferred branches:
    - `evaluators.*`: `_coverage_report.py:28-29` (eager, in a helper of `coverage_diff_gate`, a handler the dispatcher loads by name), `_metrics_pass.py:184-440`, `coverage_diff_gate.py:139-231`, `docstring_nonregression.py:139`, `quality_metrics.py:145-146`, `stop/suite.py:32` (eager), `deps.py:27` (type);
    - `evals.loader`, `evals.validator`, `sources.filesystem`: `eval_task_authoring_lint.py:114,138,167`;
    - `types`: `eval_task_authoring_lint.py:51` (type);
    - `gate_scan`: `gate_weakening.py:80,120,168`, `gate_weakening_edit.py:104`;
    - `detector`: `resync_on_detector_input_change.py:52,126,141`.
- Grading kernel (`evaluators/`) outside the leaves:
  - `metrics_gate.py:44 → config`;
  - `types.py:322 → metrics_config` (deferred);
  - `paths.py:26-28 → gate_scan, hook_runtime.globs, hook_runtime.handlers._eval_paths`;
  - `types.py:19 → hook_runtime.handlers._eval_paths`.
- 41 (importer, private module) pairs cross their owner (section 0.6.1 lists them grouped by the PR that removes them). 5 command → command edges (section 0.6.1).
- The derived `FORBIDDEN` with no other change failed exactly 6 budget cases:
  - `catalog` on the protected-edit (2 cases), control-plane edit-py and TOML-policy branches. Fixed by D0-2.
  - `gate_scan` and `_gate_scan_files` on the pre-edit companion's test-file path (`test_import_budget_stop.py:141`). Now an explicit allowance.
  - On the eval-task branch, 15 engine modules the old list never forbade: `_hook_frontmatter, _hook_schema, _layers, _member_reference, _table_shapes, _toml, config, config_entries, config_schema, evals, evaluators, hooks_config, metrics_config, sources, types`. Now named one by one.

#### 0.5 T0.1 — Module-name guards

##### 0.5.1 New `tests/engine_modules.py`

It is the single home of the module-name logic, used by the budget probes, the pin scan and the contract tests. It is stdlib-only and is imported by the pytest process only, never by a probe's child interpreter.

```python
"""Engine module names as tests pin them, checked against the installed package tree.

Two kinds of guard are keyed on module names, and both pass vacuously once a
module moves:

- a probe asserting that a module is *not* loaded: the old name is simply never
  imported again;
- the hook hot path's forbidden engine packages, which were a hand-kept list that
  a new top-level package escaped.

So every engine module a probe pins goes through ``engine_module``, which raises
``StaleModulePin`` when the name no longer resolves, and what a stack must not
import is derived, never listed: every top-level engine module outside
``STDLIB_LEAVES`` (``non_leaf_modules``) and every runtime dependency of the engine
(``runtime_dependency_imports``, read from pyproject.toml). A new top-level package
or a new dependency is forbidden to the hook runtime, the grading kernel and the
leaves until it is admitted on purpose. tests/architecture/test_import_contracts.py
pins pyproject.toml's import-linter contracts to these functions.

Stdlib-only. Only the pytest process imports it, never a probe's child interpreter.
"""

from __future__ import annotations

import functools
import importlib.metadata
import importlib.util
import pkgutil
import re
import tomllib
from pathlib import Path
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator, Set

ENGINE: Final = "coding_agent_playbook"
_PYPROJECT: Final = Path(__file__).resolve().parents[1] / "pyproject.toml"
_REQUIREMENT_NAME: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")

#: Top-level engine modules that import only the stdlib and each other. They are
#: the only engine modules the hook runtime and the grading kernel may import, so
#: the dispatch hot path may load them. A module joins only when it is stdlib-only
#: and one of those stacks needs it. A dotted entry (``"catalog.roots"``) admits
#: that module and the docstring-only packages above it, never its siblings.
STDLIB_LEAVES: Final = frozenset(
    {
        "_atomic_io",
        "_canonical_json",
        "_lock_drift",
        "_pep503",
        "_pyproject_deps",
        "_sentinel",
        "catalog",
        "lockfile",
        "security",
    }
)


class StaleModulePin(AssertionError):
    """A test pins an engine module name that no longer resolves."""


def engine_module(name: str) -> str:
    """Return ``name`` after checking that it resolves to an engine module.

    Raises ``StaleModulePin`` when the module moved or was renamed, so an
    assertion that it is *not* loaded fails instead of passing vacuously.

    Example::

        >>> engine_module("coding_agent_playbook.hook_runtime.dispatch")
        'coding_agent_playbook.hook_runtime.dispatch'
    """
    if not name.startswith(f"{ENGINE}."):
        raise ValueError(f"expected a dotted module name under {ENGINE!r}, got {name!r}")
    try:
        spec = importlib.util.find_spec(name)
    except ModuleNotFoundError:  # a parent package is gone as well
        spec = None
    if spec is None:
        raise StaleModulePin(f"{name!r} no longer resolves: pin the module's new path")
    return name


def child_modules(package: str) -> tuple[str, ...]:
    """Dotted names of the modules and packages directly inside ``package``, sorted.

    Example::

        >>> f"{ENGINE}.hook_runtime" in child_modules(ENGINE)
        True
    """
    spec = importlib.util.find_spec(package)
    if spec is None or spec.submodule_search_locations is None:
        raise ValueError(f"expected an importable package, got {package!r}")
    infos = pkgutil.iter_modules(spec.submodule_search_locations)
    return tuple(sorted(f"{package}.{info.name}" for info in infos))


def _outside(package: str, allowed: Set[str]) -> Iterator[str]:
    for child in child_modules(package):
        if child in allowed:
            continue
        if any(name.startswith(f"{child}.") for name in allowed):
            yield from _outside(child, allowed)
        else:
            yield child


def non_leaf_modules(
    stack: str | None = None, *, root: str = ENGINE, leaves: Set[str] = STDLIB_LEAVES
) -> tuple[str, ...]:
    """The modules under ``root`` that ``stack`` (or, for ``None``, a leaf) must not import.

    Every top-level module except ``stack`` itself and ``leaves``, sorted; under a
    package that holds a dotted leaf, the leaf's siblings are listed instead.

    Example::

        >>> f"{ENGINE}.cli" in non_leaf_modules("hook_runtime")
        True
    """
    allowed = {f"{root}.{leaf}" for leaf in leaves}
    if stack is not None:
        if f"{root}.{stack}" not in child_modules(root):
            raise ValueError(f"{stack!r} is not a top-level package of {root!r}")
        allowed.add(f"{root}.{stack}")
    return tuple(_outside(root, allowed))


def _normalized(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


@functools.cache
def runtime_dependency_imports(pyproject: Path = _PYPROJECT) -> tuple[str, ...]:
    """Top-level import names of the engine's ``[project].dependencies``, sorted.

    Example::

        >>> runtime_dependency_imports()
        ('jinja2', 'packaging', 'yaml')
    """
    project = tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]
    wanted = set()
    for requirement in project["dependencies"]:
        match = _REQUIREMENT_NAME.match(requirement)
        if match is None:
            raise ValueError(f"unparseable requirement {requirement!r} in {pyproject}")
        wanted.add(_normalized(match.group()))
    provided = importlib.metadata.packages_distributions().items()
    names = {name for name, dists in provided if wanted & {_normalized(d) for d in dists}}
    return tuple(sorted(name for name in names if not name.startswith("_")))
```

##### 0.5.2 `tests/hook_runtime/test_import_budget.py`

Changes, as a diff against `ef19a0a`:

- the docstring now states the derivation;
- `FORBIDDEN` is derived (`:48-69` today);
- `_forbidden` (`:130-137`) pins every engine name in `allowed`;
- every module constant and negative assertion goes through `engine_module`;
- `_CPG_PREFIX` (`:265`) is built from the pinned handlers package;
- the eval-task branch allowance (`:457-465`) names its 15 engine modules.

`FORBIDDEN`, `_forbidden(imported, allowed=())` and `_imports` keep their names and signatures, because the chain appends a test that calls them (section 0.8).

```diff
--- a/tests/hook_runtime/test_import_budget.py
+++ b/tests/hook_runtime/test_import_budget.py
@@ -5,8 +5,11 @@
 against a synced fixture repo, and reads every imported module from the
 ``importtime`` report. The hot path (``pre_tool_use`` for an Edit and for a
 Bash command, and ``post_tool_use`` after a Python edit) may import only the
-stdlib, ``hook_runtime.*`` and ``security.*``; ``tomllib`` loads only on
-``session_start`` or when the lockfile's stat changed (§D.8.1). P-D1 (the lazy
+stdlib, ``hook_runtime.*`` and the stdlib leaves (``security.*`` and the others in
+``tests.engine_modules.STDLIB_LEAVES``): ``FORBIDDEN`` is every other engine module,
+derived from the package tree, so a new package is forbidden by default.
+``tomllib`` loads only on ``session_start`` or when the lockfile's stat changed
+(§D.8.1). P-D1 (the lazy
 ``__version__``) is what keeps ``importlib.metadata`` off this path. The first
 pack guard (guard-generated-outputs, Track K5) denies a protected edit from the
 rendered tables alone: no TOML, no render, no subprocess. control-plane-guard
@@ -37,6 +40,12 @@
 from coding_agent_playbook._sentinel import SENTINEL, sentinel_line
 from coding_agent_playbook.hook_runtime.event import EventName
 from coding_agent_playbook.hook_runtime.harness import DENY_EXIT
+from tests.engine_modules import (
+    ENGINE,
+    engine_module,
+    non_leaf_modules,
+    runtime_dependency_imports,
+)
 from tests.hook_runtime.guard_repo import GuardRepo, hook_record
 from tests.import_probe import PROBE_TIMEOUT_S, probe_env
 
@@ -45,28 +54,19 @@
 
     from coding_agent_playbook.hook_runtime.proc import SubprocessProc
 
-FORBIDDEN: Final = (
-    "jinja2",
-    "yaml",
+#: The engine's runtime dependencies (pyproject.toml) and the stdlib modules the
+#: dispatch hot path never loads (§D.1).
+_FORBIDDEN_LIBRARIES: Final = (
+    *runtime_dependency_imports(),
     "importlib.metadata",
     "tomllib",
-    "packaging",
     "argparse",
-    *(
-        f"coding_agent_playbook.{name}"
-        for name in (
-            "cli",
-            "renderer",
-            "orchestrator",
-            "adapters",
-            "sources",
-            "commands",
-            "evaluators",
-            "evals",
-            "detector",
-        )
-    ),
 )
+#: Plus every engine module outside the hook runtime and its stdlib leaves. Derived
+#: from the package tree, so a new top-level package is forbidden until it joins
+#: ``tests.engine_modules.STDLIB_LEAVES`` on purpose.
+FORBIDDEN: Final = (*_FORBIDDEN_LIBRARIES, *non_leaf_modules("hook_runtime"))
+_GIT_MODULE: Final = engine_module("coding_agent_playbook.hook_runtime.git")
 _IMPORT_LINE: Final = re.compile(r"^import time:\s+\d+ \|\s+\d+ \|\s*(\S+)\s*$")
 
 
@@ -128,6 +128,14 @@
 
 
 def _forbidden(imported: set[str], allowed: tuple[str, ...] = ()) -> list[str]:
+    """The ``FORBIDDEN`` modules in ``imported``, apart from the branch-local ``allowed`` ones.
+
+    Every engine name in ``allowed`` must still resolve (``engine_module``): a stale
+    allowance would let the moved module's new name through unnoticed.
+    """
+    for name in allowed:
+        if name.startswith(f"{ENGINE}."):
+            engine_module(name)
     return sorted(
         name
         for name in imported
@@ -177,7 +185,7 @@
     imported = _imports(real_proc, synced, EventName.PRE_TOOL_USE, payload)
 
     assert "subprocess" not in imported
-    assert "coding_agent_playbook.hook_runtime.git" not in imported
+    assert _GIT_MODULE not in imported
 
 
 def test_tomllib_loads_only_on_session_start_or_lock_stat_change(
@@ -208,10 +216,11 @@
         real_proc, synced, EventName.STOP, synced.payload(EventName.STOP, stop_hook_active=False)
     )
 
-    assert {"json", "coding_agent_playbook.hook_runtime.cli"} <= imported
+    assert {"json", engine_module("coding_agent_playbook.hook_runtime.cli")} <= imported
 
 
-_PROTECTED_MODULE: Final = "coding_agent_playbook.hook_runtime.protected"
+_PROTECTED_MODULE: Final = engine_module("coding_agent_playbook.hook_runtime.protected")
+_PIN_MODULE: Final = engine_module("coding_agent_playbook.hook_runtime.pin")
 
 
 @pytest.fixture
@@ -259,10 +268,12 @@
     assert _PROTECTED_MODULE in imported  # the guard ran (and denied: exit 10)
     assert _forbidden(imported) == []
     assert "subprocess" not in imported
-    assert "coding_agent_playbook.hook_runtime.pin" not in imported  # no machine.json read
+    assert _PIN_MODULE not in imported  # no machine.json read
 
 
-_CPG_PREFIX: Final = "coding_agent_playbook.hook_runtime.handlers._control_plane_"
+_CPG_PREFIX: Final = (
+    f"{engine_module('coding_agent_playbook.hook_runtime.handlers')}._control_plane_"
+)
 
 
 @pytest.fixture
@@ -454,13 +465,32 @@
     assert "yaml" in imported and "coding_agent_playbook.sources.filesystem" in imported
     # The compile resolves check/gate/metric entry points (importlib.metadata), never
     # the runner or judge groups; the prompts come from sources.filesystem (yaml).
+    # evals.validator compiles the task through config and the canonical types:
+    # every engine module that branch loads is named, so a new one fails here.
     branch_local = (
         "tomllib",
         "yaml",
         "importlib.metadata",
-        "coding_agent_playbook.evals",
-        "coding_agent_playbook.evaluators",
-        "coding_agent_playbook.sources",
+        *(
+            engine_module(f"{ENGINE}.{name}")
+            for name in (
+                "_hook_frontmatter",
+                "_hook_schema",
+                "_layers",
+                "_member_reference",
+                "_table_shapes",
+                "_toml",
+                "config",
+                "config_entries",
+                "config_schema",
+                "evals",
+                "evaluators",
+                "hooks_config",
+                "metrics_config",
+                "sources",
+                "types",
+            )
+        ),
     )
     assert _forbidden(imported, allowed=branch_local) == []
     assert "jinja2" not in imported
@@ -468,9 +498,9 @@
 
 # --- K5 step 4: the briefing and the drift stage (§D.1 rows: lockfile + tomllib) ------
 
-_LOCKFILE_MODULE: Final = "coding_agent_playbook.lockfile"
-_BRIEFING: Final = "coding_agent_playbook.hook_runtime.handlers._briefing_probes"
-_DRIFT_FAST_PATH: Final = "coding_agent_playbook.hook_runtime.handlers._drift"
+_LOCKFILE_MODULE: Final = engine_module("coding_agent_playbook.lockfile")
+_BRIEFING: Final = engine_module("coding_agent_playbook.hook_runtime.handlers._briefing_probes")
+_DRIFT_FAST_PATH: Final = engine_module("coding_agent_playbook.hook_runtime.handlers._drift")
 
 
 @pytest.fixture
@@ -536,7 +566,8 @@
 
 # --- K7 step 2: the post-edit ruff branch (specs/prK-hook-pack.md §E.3) ------------------
 
-_RUFF_PIPELINE: Final = "coding_agent_playbook.hook_runtime.handlers._ruff_pipeline"
+_RUFF_PIPELINE: Final = engine_module("coding_agent_playbook.hook_runtime.handlers._ruff_pipeline")
+_GUARD_CONFIG_RUFF: Final = engine_module("coding_agent_playbook._guard_config_ruff")
 
 
 @pytest.fixture
@@ -573,10 +604,10 @@
     assert _RUFF_PIPELINE in imported  # the post-edit handler ran up to its pin check
     assert _forbidden(imported) == []
     assert "subprocess" not in imported
-    assert "coding_agent_playbook._guard_config_ruff" not in imported  # sync-time (tomllib)
+    assert _GUARD_CONFIG_RUFF not in imported  # sync-time (tomllib)
 
 
-_SECRET_POLICY: Final = "coding_agent_playbook.hook_runtime.handlers._secret_policy"
+_SECRET_POLICY: Final = engine_module("coding_agent_playbook.hook_runtime.handlers._secret_policy")
 
 
 @pytest.fixture
@@ -622,7 +653,7 @@
     assert _SECRET_POLICY in imported  # a secret guard ran (and denied: exit 10)
     assert _forbidden(imported) == []
     assert "subprocess" not in imported
-    assert "coding_agent_playbook.hook_runtime.git" not in imported
+    assert _GIT_MODULE not in imported
 
 
 @pytest.fixture
@@ -666,12 +697,12 @@
 
     assert _forbidden(imported) == []
     assert "subprocess" not in imported
-    assert "coding_agent_playbook.hook_runtime.git" not in imported
+    assert _GIT_MODULE not in imported
 
 
 #: The helpers each guard imports at module load: their presence shows the guard ran.
-_INSTALL_CMDS: Final = "coding_agent_playbook.hook_runtime.handlers._install_cmds"
-_EGRESS: Final = "coding_agent_playbook.hook_runtime.handlers._egress"
+_INSTALL_CMDS: Final = engine_module("coding_agent_playbook.hook_runtime.handlers._install_cmds")
+_EGRESS: Final = engine_module("coding_agent_playbook.hook_runtime.handlers._egress")
 _BRANCH_LOCAL: Final = ("tomllib", "difflib", "ipaddress")
 
 
@@ -774,13 +805,13 @@
     assert "coding_agent_playbook.hook_runtime.handlers._activity_record" in imported
     assert _forbidden(imported) == []
     assert "subprocess" not in imported
-    assert "coding_agent_playbook.hook_runtime.git" not in imported
+    assert _GIT_MODULE not in imported
     (log,) = audited.state_root.glob("audit-*.jsonl")
     assert '"event":"post_tool_use"' in log.read_text(encoding="ascii")
 
 
 #: network-egress-guard's destination parser: its presence shows the guard ran (K9 step 4).
-_NET_TARGETS: Final = "coding_agent_playbook.hook_runtime.handlers._net_targets"
+_NET_TARGETS: Final = engine_module("coding_agent_playbook.hook_runtime.handlers._net_targets")
 
 
 @pytest.fixture
@@ -836,4 +867,4 @@
     assert _forbidden(imported) == []
     assert "subprocess" not in imported
     assert "socket" not in imported
-    assert "coding_agent_playbook.hook_runtime.git" not in imported
+    assert _GIT_MODULE not in imported
```

##### 0.5.3 `tests/hook_runtime/test_import_budget_stop.py`

The changes:

- the three constants (`:28-30`) are pinned;
- the raw `_drift` name (`:64`) reuses the budget test's pinned `_DRIFT_FAST_PATH`;
- the test-file path's `gate_scan` load becomes an explicit allowance (`:141`) instead of passing only because `gate_scan` was never forbidden.

```diff
--- a/tests/hook_runtime/test_import_budget_stop.py
+++ b/tests/hook_runtime/test_import_budget_stop.py
@@ -16,8 +16,9 @@
 from typing import TYPE_CHECKING, Any
 
 from coding_agent_playbook.hook_runtime.event import EventName
+from tests.engine_modules import engine_module
 from tests.hook_runtime.guard_repo import GuardRepo, hook_record
-from tests.hook_runtime.test_import_budget import _forbidden, _imports
+from tests.hook_runtime.test_import_budget import _DRIFT_FAST_PATH, _forbidden, _imports
 from tests.hooks.stop_kit import TREE
 
 if TYPE_CHECKING:
@@ -25,9 +26,10 @@
 
     from coding_agent_playbook.hook_runtime.proc import SubprocessProc
 
-_COORDINATOR = "coding_agent_playbook.hook_runtime.stop.coordinator"
-_GATE_SCAN = "coding_agent_playbook.gate_scan"
-_METRICS_GATE = "coding_agent_playbook.evaluators.metrics_gate"
+_COORDINATOR = engine_module("coding_agent_playbook.hook_runtime.stop.coordinator")
+_GATE_SCAN = engine_module("coding_agent_playbook.gate_scan")
+_GATE_SCAN_FILES = engine_module("coding_agent_playbook._gate_scan_files")
+_METRICS_GATE = engine_module("coding_agent_playbook.evaluators.metrics_gate")
 
 
 def test_stop_coordinator_imports_no_forbidden_module(
@@ -61,7 +63,7 @@
     )
 
     assert _COORDINATOR in imported
-    assert "coding_agent_playbook.hook_runtime.handlers._drift" not in imported  # inactive stage
+    assert _DRIFT_FAST_PATH not in imported  # inactive stage
     assert _forbidden(imported) == []
 
 
@@ -138,4 +140,5 @@
     assert _GATE_SCAN not in source
     assert _GATE_SCAN in test
     assert "tomllib" not in source | test
-    assert _forbidden(source) == _forbidden(test) == []
+    assert _forbidden(source) == []
+    assert _forbidden(test, allowed=(_GATE_SCAN, _GATE_SCAN_FILES)) == []
```

##### 0.5.4 The other negative pins

Each file gains `from tests.engine_modules import engine_module`. The line numbers below are those at `ef19a0a`.

| File:line | Before | After |
|---|---|---|
| `tests/evaluators/test_metrics_gate.py:527` | `m.startswith("coding_agent_playbook.commands")` | `m.startswith(engine_module("coding_agent_playbook.commands"))` |
| `tests/hook_runtime/test_combine.py:456` | `all(m.startswith("coding_agent_playbook.hook_runtime") for m in engine)` | `runtime = engine_module("coding_agent_playbook.hook_runtime")` then `all(m.startswith(runtime) for m in engine)` |
| `tests/hook_runtime/test_event.py:253` | `"coding_agent_playbook.hook_runtime.shell" not in loaded` | `engine_module("coding_agent_playbook.hook_runtime.shell") not in loaded` |
| `tests/hook_runtime/test_render_claude.py:445-446` | the same two shapes | the same two rewrites |
| `tests/hook_runtime/test_runtime_config.py:502-503` | `"coding_agent_playbook.lockfile" not in loaded`; `m.startswith("coding_agent_playbook.hook_policy")` | `engine_module(...)` around both names |
| `tests/security/test_audit.py:373`, `test_patterns.py:219`, `test_pii.py:314`, `test_secrets.py:254`, `test_trust.py:371` | `name.startswith("coding_agent_playbook.security")` | `name.startswith(engine_module("coding_agent_playbook.security"))` |
| `tests/unit/test_hook_registrations.py:516-517` | `"coding_agent_playbook.types"` / `"coding_agent_playbook.renderer" not in loaded` | `engine_module(...)` around both names |

Three pins in chain files are deferred to T0.3 and listed in `_DEFERRED_UNTIL_CHAIN_MERGES`:

- `tests/adapters/test_claude_code_rules.py:95`: `renderer` in a set display;
- `tests/adapters/test_claude_code_rules.py:96`: `adapters.claude_code_adapter not in`;
- `tests/unit/test_rule_registry.py:211`: `rule_registry not in`.

##### 0.5.5 New `tests/architecture/test_module_pins.py`

It scans every `tests/**/*.py` file except `tests/fixtures/`. Strings under the engine name that are not modules are skipped:

- the bundled-plugin overlay ids (`coding_agent_playbook.plugins.*`, `coding_agent_playbook.packs.*`);
- the entry-point group names from pyproject.toml, matched exactly, because `coding_agent_playbook.adapters` is both a group and a package.

With the two budget files converted (sections 0.5.2-0.5.3), the scan found exactly 17 sites on today's tree: the 14 of section 0.5.4 and the 3 deferred ones.

```python
"""Engine module names a test asserts on go through ``tests.engine_modules.engine_module``.

``assert "coding_agent_playbook.x" not in loaded`` stays true forever once ``x``
moves, and so does a module-level constant, a set display or a ``startswith``
prefix spelled as a raw string. ``engine_module`` resolves the name with
``importlib.util.find_spec`` and fails when it is stale, so this scan rejects those
raw spellings in every test file. A list, tuple or set of expected names compared
with ``==`` fails loudly on its own and is not flagged.
"""

from __future__ import annotations

import ast
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator, Set

_TESTS_ROOT: Final = Path(__file__).resolve().parents[1]
_ENGINE_NAME: Final = re.compile(r"^coding_agent_playbook(\.[A-Za-z_][A-Za-z0-9_]*)+$")
#: Engine-prefixed strings that are not modules: bundled-plugin overlay ids, and
#: (exact names only, read from pyproject.toml) the entry-point group names, one of
#: which is also a package (``coding_agent_playbook.adapters``).
_OVERLAY_NAMESPACES: Final = ("coding_agent_playbook.plugins", "coding_agent_playbook.packs")
#: Raw pins in test files the #49-#62 ticket chain edits. They are wrapped in the
#: PR after the chain merges; an entry that no longer matches fails
#: test_deferred_raw_pins_still_exist, so the list only shrinks.
_DEFERRED_UNTIL_CHAIN_MERGES: Final = frozenset(
    {
        (
            "adapters/test_claude_code_rules.py",
            "coding_agent_playbook.adapters.claude_code_adapter",
        ),
        ("adapters/test_claude_code_rules.py", "coding_agent_playbook.renderer"),
        ("unit/test_rule_registry.py", "coding_agent_playbook.rule_registry"),
    }
)


@dataclass(frozen=True, order=True)
class RawPin:
    """One raw engine module name in a test file."""

    path: str
    line: int
    name: str


def _entry_point_groups() -> frozenset[str]:
    pyproject = tomllib.loads((_TESTS_ROOT.parent / "pyproject.toml").read_text(encoding="utf-8"))
    return frozenset(pyproject["project"]["entry-points"])


def _is_module_name(value: str, not_modules: Set[str]) -> bool:
    if not _ENGINE_NAME.match(value) or value in not_modules:
        return False
    return not any(value == ns or value.startswith(f"{ns}.") for ns in _OVERLAY_NAMESPACES)


def _equality_sets(tree: ast.Module) -> set[int]:
    compared: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.Eq) for op in node.ops):
            operands = (node.left, *node.comparators)
            compared.update(id(operand) for operand in operands if isinstance(operand, ast.Set))
    return compared


def _startswith_prefix(node: ast.AST) -> ast.AST | None:
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return None
    return node.args[0] if node.func.attr == "startswith" and node.args else None


def _positions(tree: ast.Module) -> Iterator[ast.AST | None]:
    """Every expression whose raw engine name would pass vacuously after a move."""
    compared = _equality_sets(tree)
    for statement in tree.body:
        if isinstance(statement, ast.Assign | ast.AnnAssign):
            yield statement.value
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(isinstance(op, ast.NotIn) for op in node.ops):
            yield node.left
        if isinstance(node, ast.Set) and id(node) not in compared:
            yield from node.elts
        yield _startswith_prefix(node)


def raw_pins(source: str, path: str, *, not_modules: Set[str] = frozenset()) -> list[RawPin]:
    """The raw engine module names in ``source`` at a position that can pass vacuously.

    Example::

        >>> raw_pins('assert "coding_agent_playbook.gate_scan" not in loaded', "t.py")
        [RawPin(path='t.py', line=1, name='coding_agent_playbook.gate_scan')]
    """
    strings = [
        (node.lineno, node.value)
        for node in _positions(ast.parse(source))
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    ]
    pins = {
        RawPin(path, line, value) for line, value in strings if _is_module_name(value, not_modules)
    }
    return sorted(pins)


def _scan_tests() -> list[RawPin]:
    not_modules = _entry_point_groups()
    found = []
    for path in sorted(_TESTS_ROOT.rglob("*.py")):
        relative = path.relative_to(_TESTS_ROOT).as_posix()
        if relative.startswith("fixtures/") or path == Path(__file__).resolve():
            continue
        source = path.read_text(encoding="utf-8")
        found.extend(raw_pins(source, relative, not_modules=not_modules))
    return found


def test_tests_pin_engine_modules_through_engine_module() -> None:
    deferred = _DEFERRED_UNTIL_CHAIN_MERGES
    raw = [pin for pin in _scan_tests() if (pin.path, pin.name) not in deferred]

    assert raw == [], "wrap each name in tests.engine_modules.engine_module(...)"


def test_deferred_raw_pins_still_exist() -> None:
    found = {(pin.path, pin.name) for pin in _scan_tests()}

    assert sorted(_DEFERRED_UNTIL_CHAIN_MERGES - found) == []


@pytest.mark.parametrize(
    "source",
    [
        'assert "coding_agent_playbook.gate_scan" not in loaded',
        '_GATE_SCAN = "coding_agent_playbook.gate_scan"',
        'assert not {"yaml", "coding_agent_playbook.gate_scan"} & loaded',
        'assert not [m for m in loaded if m.startswith("coding_agent_playbook.gate_scan")]',
    ],
    ids=["not-in", "module-constant", "set-display", "startswith"],
)
def test_raw_pins_flags_each_vacuous_spelling(source: str) -> None:
    assert [pin.name for pin in raw_pins(source, "t.py")] == ["coding_agent_playbook.gate_scan"]


@pytest.mark.parametrize(
    "source",
    [
        '_GATE_SCAN = engine_module("coding_agent_playbook.gate_scan")',
        'assert loaded == ["coding_agent_playbook.security", "coding_agent_playbook.security.pii"]',
        'assert engine == {"coding_agent_playbook.hook_runtime"}',
        'assert "coding_agent_playbook.gate_scan" in loaded',
        'run_python_probe("import coding_agent_playbook.gate_scan")',
    ],
    ids=["wrapped", "equality-list", "equality-set", "positive-in", "probe-code"],
)
def test_raw_pins_accepts_loud_spellings(source: str) -> None:
    assert raw_pins(source, "t.py") == []


def test_raw_pins_skips_names_that_are_not_modules() -> None:
    source = '_GROUP = "coding_agent_playbook.hook_handlers"'

    assert raw_pins(source, "t.py", not_modules={"coding_agent_playbook.hook_handlers"}) == []
```

##### 0.5.6 New `tests/hook_runtime/test_stage_factories.py`

`STAGE_FACTORIES` (`hook_runtime/handlers/stop_ci_parity_gate.py:72-88`) binds Stop stages to `"module:function"` strings. The coordinator imports them only when a stage runs (`_factory`, `:169-176`), and no test resolved them. A hook-runtime move that renames `_exec_stages`, `_lint_stage` or a handler module would fail only inside a consumer's Stop hook.

```python
"""Every ``STAGE_FACTORIES`` row names a module and a callable that exist.

The Stop coordinator imports a stage's module from this string table only when the
stage runs (stop_ci_parity_gate._factory), so a moved or renamed stage module
would surface as a failing Stop stage in a consumer session, never in an import.
"""

from __future__ import annotations

import importlib
import importlib.util

import pytest

from coding_agent_playbook.hook_runtime.handlers.stop_ci_parity_gate import STAGE_FACTORIES
from coding_agent_playbook.hook_runtime.registry import _BUILTIN_HANDLER_MODULES


@pytest.mark.parametrize(("stage", "target"), sorted(STAGE_FACTORIES.items()))
def test_every_stage_factory_resolves(stage: str, target: str) -> None:
    module, _, attr = target.partition(":")

    factory = getattr(importlib.import_module(module), attr, None)

    assert callable(factory), f"stage {stage!r}: {target!r} does not resolve"


@pytest.mark.parametrize(("name", "module"), sorted(_BUILTIN_HANDLER_MODULES.items()))
def test_every_builtin_handler_module_resolves(name: str, module: str) -> None:
    # The registry imports these lazily by string, so a moved handler fails only
    # when its hook first fires; find_spec checks the path without importing it.
    assert importlib.util.find_spec(module) is not None, f"{name!r}: {module!r} does not resolve"
```

The pin path of `_BUILTIN_HANDLER_MODULES` follows the registry move (A11, `hook_runtime.dispatch.registry`), by the script.

##### 0.5.7 New `tests/architecture/test_engine_modules.py` (and an empty `tests/architecture/__init__.py`)

```python
"""``tests.engine_modules``: pinned engine names resolve, and forbidden lists track the tree."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from tests.engine_modules import (
    ENGINE,
    STDLIB_LEAVES,
    StaleModulePin,
    child_modules,
    engine_module,
    non_leaf_modules,
    runtime_dependency_imports,
)

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def test_engine_module_returns_a_name_that_resolves() -> None:
    assert engine_module(f"{ENGINE}.hook_runtime.dispatch") == f"{ENGINE}.hook_runtime.dispatch"


@pytest.mark.parametrize("name", [f"{ENGINE}.no_such_module", f"{ENGINE}.no_such_package.x"])
def test_engine_module_fails_for_a_moved_module(name: str) -> None:
    with pytest.raises(StaleModulePin, match="no longer resolves"):
        engine_module(name)


def test_engine_module_rejects_a_name_outside_the_engine() -> None:
    with pytest.raises(ValueError, match="under 'coding_agent_playbook'"):
        engine_module("json")


@pytest.mark.parametrize("leaf", sorted(STDLIB_LEAVES))
def test_every_stdlib_leaf_resolves(leaf: str) -> None:
    engine_module(f"{ENGINE}.{leaf}")


def test_child_modules_lists_modules_and_packages(make_package: Callable[..., str]) -> None:
    make_package("lane0_pkg")
    make_package("lane0_pkg.sub")

    assert child_modules("lane0_pkg") == ("lane0_pkg.sub",)


def test_child_modules_rejects_a_plain_module() -> None:
    with pytest.raises(ValueError, match="importable package"):
        child_modules(f"{ENGINE}.gate_scan")


def test_non_leaf_modules_forbids_a_new_top_level_package(
    make_package: Callable[..., str],
) -> None:
    for name in ("lane0_eng", "lane0_eng.runtime", "lane0_eng.leaf", "lane0_eng.brand_new"):
        make_package(name)

    forbidden = non_leaf_modules("runtime", root="lane0_eng", leaves={"leaf"})

    assert forbidden == ("lane0_eng.brand_new",)


def test_non_leaf_modules_lists_the_siblings_of_a_dotted_leaf(
    make_package: Callable[..., str],
) -> None:
    for name in ("lane0_art", "lane0_art.runtime", "lane0_art.artifacts"):
        make_package(name)
    for name in ("lane0_art.artifacts.hook_schema", "lane0_art.artifacts.frontmatter"):
        make_package(name)

    forbidden = non_leaf_modules("runtime", root="lane0_art", leaves={"artifacts.hook_schema"})

    assert forbidden == ("lane0_art.artifacts.frontmatter",)


def test_non_leaf_modules_rejects_an_unknown_stack() -> None:
    with pytest.raises(ValueError, match="not a top-level package"):
        non_leaf_modules("evaluators_renamed")


def test_non_leaf_modules_without_a_stack_forbids_every_stack(
    make_package: Callable[..., str],
) -> None:
    for name in ("lane0_all", "lane0_all.runtime", "lane0_all.leaf"):
        make_package(name)

    assert non_leaf_modules(root="lane0_all", leaves={"leaf"}) == ("lane0_all.runtime",)


def test_runtime_dependency_imports_reads_the_dependency_table(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        '[project]\ndependencies = ["PyYAML>=6.0", "packaging>=24.0"]\n', encoding="utf-8"
    )

    assert runtime_dependency_imports(pyproject) == ("packaging", "yaml")


def test_runtime_dependency_imports_are_the_engine_dependencies() -> None:
    assert runtime_dependency_imports() == ("jinja2", "packaging", "yaml")
```

##### 0.5.8 Name guards that already fail loudly

Lane 0 leaves these unchanged. Each move PR must update the ones that name what it moves:

- `tests/unit/test_docs_lifecycle_hooks_spec.py:94-104` (`_ENGINE_PATHS`, asserted to exist at `:207-213`). It names `guard_config.py, hooks_config.py, _sentinel.py, _pep503.py, gate_scan.py, hook_policy/, hook_registrations/, security/, templates/hook_shims/`. A move PR that renames one of those paths edits the test and the SPEC §5.1 tree together. The test file is chain-edited (#50, #53), so that one-line edit is a soft overlap (H1): the move merges between two chain tickets and the next ticket rebases.
- `tests/unit/test_docs_lifecycle_hooks_cli.py:263-264` (`security/audit.py`) and `tests/unit/test_committed_config.py:230-232` (`_HOME`, `_WRITERS_HOME`).
- `hook_runtime/registry.py:69-124` (`_BUILTIN_HANDLER_MODULES`), pinned by `tests/hook_runtime/test_registry.py:96` (it imports every mapped module) and `:112`.
- Every `new_modules_after("import …")` / `run_python_probe("import …")` statement (the child exits non-zero), every equality list of module names, and every positive `in` assertion.

##### 0.5.9 New `tests/cli/test_module_entry.py` (added by the harmonisation)

`hook_runtime/handlers/_source_changed.py:56` and `commands/ci.py:99` spawn `python -I -m coding_agent_playbook.cli` as a child process, so a missing `cli/__main__.py` would fail only inside a consumer session. This test pins the entry before N7 turns `cli.py` into the `cli/` package; it passes on the baseline, where `cli.py` ends with an `if __name__ == "__main__"` tail.

```python
"""``python -m coding_agent_playbook.cli`` keeps working: the hook runtime and ``playbook ci`` spawn it."""

from __future__ import annotations

import subprocess
import sys

from tests.import_probe import PROBE_TIMEOUT_S, probe_env


def test_python_dash_m_cli_prints_help() -> None:
    result = subprocess.run(
        [sys.executable, "-I", "-m", "coding_agent_playbook.cli", "--help"],
        capture_output=True,
        text=True,
        timeout=PROBE_TIMEOUT_S,
        env=probe_env(),
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "usage: " in result.stdout
```

#### 0.6 T0.2 — Import contracts

##### 0.6.1 `pyproject.toml`

Add the dev dependency at the end of `[project.optional-dependencies].dev` (after `"types-pyyaml>=6.0",`, `pyproject.toml:45`):

```toml
    # Pinned like ruff: the contracts in [tool.importlinter] run from pytest
    # (tests/architecture/test_import_contracts.py), so a release that changes a
    # contract type's semantics must not change the CI verdict on its own.
    "import-linter==2.15",
```

Insert the block below before `# --- coverage ---` (`pyproject.toml:216`).

The three `forbidden_modules` lists are exactly `non_leaf_modules(<stack>)` (or `non_leaf_modules()` for the leaves) followed by `runtime_dependency_imports()`. When one drifts, `test_stack_contract_forbids_every_non_leaf_module` or `test_leaf_contract_covers_every_stdlib_leaf` prints the expected list. They can also be regenerated with `python -c "from tests.engine_modules import *; print(non_leaf_modules('hook_runtime') + runtime_dependency_imports())"`.

```toml
# --- import-linter (ADR 0002: the package dependency direction) ---
# Run by tests/architecture/test_import_contracts.py, so the CI gate stays ruff,
# ruff format, mypy and pytest. An ignore_imports line is a known edge, commented
# with the PR that removes it (or, for the stacks, the deferred branch it is); a
# line that no longer matches any import fails the run. The forbidden lists and
# exhaustive_ignores are pinned to the package tree by the same test file.

[tool.importlinter]
root_packages = ["coding_agent_playbook"]
# TYPE_CHECKING imports count: an interface that names a higher layer's type
# depends on that layer even when nothing imports it at run time.
exclude_type_checking_imports = false
# The third-party top-level packages join the graph, so the stacks and the leaves can
# forbid the engine's runtime dependencies (jinja2, packaging, yaml) statically.
include_external_packages = true
contract_types = ["private_modules: tests.architecture.private_modules_contract.PrivateModulesContract"]

[[tool.importlinter.contracts]]
id = "engine-layers"
name = "A package imports only packages below it"
type = "layers"
containers = ["coding_agent_playbook"]
# Highest first. A parenthesised layer does not exist yet; the PR that creates the
# package drops the parentheses. hook_runtime is a separate stack, never a layer.
layers = [
    "cli",
    "commands",
    "(sync)",
    "(validation)",
    "(agent_harness) | evals | (precommit)",
    "adapters",
    "(rendering)",
    "(hooks)",
    "(skills)",
    "(metrics_gate)",
    "config",
    "catalog",
    "detector | lockfile",
    "(grading)",
    "(generated_output)",
    "(artifacts)",
    "security | (toml_writer) | (_plugin_registry)",
]
exhaustive = true
# Top-level modules not yet in their target package: each move PR deletes its
# names. hook_runtime stays here for good.
exhaustive_ignores = [
    "_atomic_io",
    "_canonical_json",
    "_file_identity",
    "_gate_scan_files",
    "_guard_config_allowlists",
    "_guard_config_detect",
    "_guard_config_prompts",
    "_guard_config_protect",
    "_guard_config_quality",
    "_guard_config_ruff",
    "_guard_config_secrets",
    "_guard_config_toolchain",
    "_guard_config_verify",
    "_hook_frontmatter",
    "_hook_schema",
    "_layers",
    "_lock_drift",
    "_member_reference",
    "_output_io",
    "_pep503",
    "_pyproject_deps",
    "_sentinel",
    "_symlinks",
    "_table_shapes",
    "_toml",
    "_typing",
    "config_entries",
    "config_schema",
    "evaluators",
    "gate_scan",
    "git_client",
    "git_env",
    "gitignore",
    "guard_config",
    "harness",
    "hook_policy",
    "hook_registrations",
    "hook_runtime",
    "hooks_config",
    "links",
    "metrics_config",
    "orchestrator",
    "prompt_rule_delivery",
    "renderer",
    "rule_registry",
    "skill_document",
    "skill_membership",
    "sources",
    "types",
]
ignore_imports = [
    # CF-2 deletes _typing.py (after #62)
    "coding_agent_playbook._typing -> coding_agent_playbook.evals.task",
    # kept: catalog-layers (the artifact source parses eval tasks) is not scheduled (L12); N3 renames it
    "coding_agent_playbook.sources.filesystem -> coding_agent_playbook.evals.**",
]
broken_contract_guidance = """
A lower layer may not import a higher one, directly or through modules outside the layers.
Move the shared code down, or pass the value in from the caller. A new top-level module
belongs in a layer, or (old layout only) in exhaustive_ignores.
"""

[[tool.importlinter.contracts]]
id = "stdlib-leaves"
name = "A stdlib leaf imports only the stdlib and other leaves"
type = "forbidden"
# tests/engine_modules.py STDLIB_LEAVES: the only engine modules the two stacks import.
source_modules = [
    "coding_agent_playbook._atomic_io",
    "coding_agent_playbook._canonical_json",
    "coding_agent_playbook._lock_drift",
    "coding_agent_playbook._pep503",
    "coding_agent_playbook._pyproject_deps",
    "coding_agent_playbook._sentinel",
    "coding_agent_playbook.catalog",
    "coding_agent_playbook.lockfile",
    "coding_agent_playbook.security",
]
forbidden_modules = [
    "coding_agent_playbook._file_identity",
    "coding_agent_playbook._gate_scan_files",
    "coding_agent_playbook._guard_config_allowlists",
    "coding_agent_playbook._guard_config_detect",
    "coding_agent_playbook._guard_config_prompts",
    "coding_agent_playbook._guard_config_protect",
    "coding_agent_playbook._guard_config_quality",
    "coding_agent_playbook._guard_config_ruff",
    "coding_agent_playbook._guard_config_secrets",
    "coding_agent_playbook._guard_config_toolchain",
    "coding_agent_playbook._guard_config_verify",
    "coding_agent_playbook._hook_frontmatter",
    "coding_agent_playbook._hook_schema",
    "coding_agent_playbook._layers",
    "coding_agent_playbook._member_reference",
    "coding_agent_playbook._output_io",
    "coding_agent_playbook._symlinks",
    "coding_agent_playbook._table_shapes",
    "coding_agent_playbook._toml",
    "coding_agent_playbook._typing",
    "coding_agent_playbook.adapters",
    "coding_agent_playbook.cli",
    "coding_agent_playbook.commands",
    "coding_agent_playbook.config",
    "coding_agent_playbook.config_entries",
    "coding_agent_playbook.config_schema",
    "coding_agent_playbook.detector",
    "coding_agent_playbook.evals",
    "coding_agent_playbook.evaluators",
    "coding_agent_playbook.gate_scan",
    "coding_agent_playbook.git_client",
    "coding_agent_playbook.git_env",
    "coding_agent_playbook.gitignore",
    "coding_agent_playbook.guard_config",
    "coding_agent_playbook.harness",
    "coding_agent_playbook.hook_policy",
    "coding_agent_playbook.hook_registrations",
    "coding_agent_playbook.hook_runtime",
    "coding_agent_playbook.hooks_config",
    "coding_agent_playbook.links",
    "coding_agent_playbook.metrics_config",
    "coding_agent_playbook.orchestrator",
    "coding_agent_playbook.prompt_rule_delivery",
    "coding_agent_playbook.renderer",
    "coding_agent_playbook.rule_registry",
    "coding_agent_playbook.skill_document",
    "coding_agent_playbook.skill_membership",
    "coding_agent_playbook.sources",
    "coding_agent_playbook.types",
    "jinja2",
    "packaging",
    "yaml",
]
broken_contract_guidance = """
A stdlib leaf is imported by the hook runtime and the grading kernel, so it imports only the
stdlib and other leaves (tests/engine_modules.py STDLIB_LEAVES).
"""

[[tool.importlinter.contracts]]
id = "hook-runtime-stack"
name = "The hook runtime imports only stdlib leaves"
type = "forbidden"
source_modules = ["coding_agent_playbook.hook_runtime"]
# Every top-level module except hook_runtime and STDLIB_LEAVES, then the runtime
# dependencies (tests/engine_modules.py; test_stack_contract_forbids_every_non_leaf_module
# prints the expected list).
forbidden_modules = [
    "coding_agent_playbook._file_identity",
    "coding_agent_playbook._gate_scan_files",
    "coding_agent_playbook._guard_config_allowlists",
    "coding_agent_playbook._guard_config_detect",
    "coding_agent_playbook._guard_config_prompts",
    "coding_agent_playbook._guard_config_protect",
    "coding_agent_playbook._guard_config_quality",
    "coding_agent_playbook._guard_config_ruff",
    "coding_agent_playbook._guard_config_secrets",
    "coding_agent_playbook._guard_config_toolchain",
    "coding_agent_playbook._guard_config_verify",
    "coding_agent_playbook._hook_frontmatter",
    "coding_agent_playbook._hook_schema",
    "coding_agent_playbook._layers",
    "coding_agent_playbook._member_reference",
    "coding_agent_playbook._output_io",
    "coding_agent_playbook._symlinks",
    "coding_agent_playbook._table_shapes",
    "coding_agent_playbook._toml",
    "coding_agent_playbook._typing",
    "coding_agent_playbook.adapters",
    "coding_agent_playbook.cli",
    "coding_agent_playbook.commands",
    "coding_agent_playbook.config",
    "coding_agent_playbook.config_entries",
    "coding_agent_playbook.config_schema",
    "coding_agent_playbook.detector",
    "coding_agent_playbook.evals",
    "coding_agent_playbook.evaluators",
    "coding_agent_playbook.gate_scan",
    "coding_agent_playbook.git_client",
    "coding_agent_playbook.git_env",
    "coding_agent_playbook.gitignore",
    "coding_agent_playbook.guard_config",
    "coding_agent_playbook.harness",
    "coding_agent_playbook.hook_policy",
    "coding_agent_playbook.hook_registrations",
    "coding_agent_playbook.hooks_config",
    "coding_agent_playbook.links",
    "coding_agent_playbook.metrics_config",
    "coding_agent_playbook.orchestrator",
    "coding_agent_playbook.prompt_rule_delivery",
    "coding_agent_playbook.renderer",
    "coding_agent_playbook.rule_registry",
    "coding_agent_playbook.skill_document",
    "coding_agent_playbook.skill_membership",
    "coding_agent_playbook.sources",
    "coding_agent_playbook.types",
    "jinja2",
    "packaging",
    "yaml",
]
# The deferred branches (specs/prK-lifecycle-hooks.md §D.1): modules the dispatcher
# loads only on their branch, pinned per branch by tests/hook_runtime/test_import_budget*.py.
ignore_imports = [
    "coding_agent_playbook.hook_runtime.deps -> coding_agent_playbook.evaluators.**",
    "coding_agent_playbook.hook_runtime.handlers._coverage_report -> coding_agent_playbook.evaluators.**",
    "coding_agent_playbook.hook_runtime.handlers._metrics_pass -> coding_agent_playbook.evaluators.**",
    "coding_agent_playbook.hook_runtime.handlers.coverage_diff_gate -> coding_agent_playbook.evaluators.**",
    "coding_agent_playbook.hook_runtime.handlers.docstring_nonregression -> coding_agent_playbook.evaluators.**",
    "coding_agent_playbook.hook_runtime.handlers.eval_task_authoring_lint -> coding_agent_playbook.evals.**",
    "coding_agent_playbook.hook_runtime.handlers.eval_task_authoring_lint -> coding_agent_playbook.sources.**",
    "coding_agent_playbook.hook_runtime.handlers.eval_task_authoring_lint -> coding_agent_playbook.types",
    # N15 moves the judge into hook_runtime/judges/ and deletes these two lines
    "coding_agent_playbook.hook_runtime.handlers.gate_weakening -> coding_agent_playbook.gate_scan",
    "coding_agent_playbook.hook_runtime.handlers.gate_weakening_edit -> coding_agent_playbook.gate_scan",
    "coding_agent_playbook.hook_runtime.handlers.quality_metrics -> coding_agent_playbook.evaluators.**",
    "coding_agent_playbook.hook_runtime.handlers.resync_on_detector_input_change -> coding_agent_playbook.detector",
    "coding_agent_playbook.hook_runtime.stop.suite -> coding_agent_playbook.evaluators.**",
]
broken_contract_guidance = """
The hook runtime imports only the stdlib, itself and STDLIB_LEAVES (tests/engine_modules.py).
An import that runs only on one dispatch branch goes in ignore_imports as
"<importing module> -> <package>.**", with a branch-local row in the import-budget tests.
"""

[[tool.importlinter.contracts]]
id = "grading-kernel"
name = "The grading kernel imports only stdlib leaves"
type = "forbidden"
source_modules = ["coding_agent_playbook.evaluators"]
forbidden_modules = [
    "coding_agent_playbook._file_identity",
    "coding_agent_playbook._gate_scan_files",
    "coding_agent_playbook._guard_config_allowlists",
    "coding_agent_playbook._guard_config_detect",
    "coding_agent_playbook._guard_config_prompts",
    "coding_agent_playbook._guard_config_protect",
    "coding_agent_playbook._guard_config_quality",
    "coding_agent_playbook._guard_config_ruff",
    "coding_agent_playbook._guard_config_secrets",
    "coding_agent_playbook._guard_config_toolchain",
    "coding_agent_playbook._guard_config_verify",
    "coding_agent_playbook._hook_frontmatter",
    "coding_agent_playbook._hook_schema",
    "coding_agent_playbook._layers",
    "coding_agent_playbook._member_reference",
    "coding_agent_playbook._output_io",
    "coding_agent_playbook._symlinks",
    "coding_agent_playbook._table_shapes",
    "coding_agent_playbook._toml",
    "coding_agent_playbook._typing",
    "coding_agent_playbook.adapters",
    "coding_agent_playbook.cli",
    "coding_agent_playbook.commands",
    "coding_agent_playbook.config",
    "coding_agent_playbook.config_entries",
    "coding_agent_playbook.config_schema",
    "coding_agent_playbook.detector",
    "coding_agent_playbook.evals",
    "coding_agent_playbook.gate_scan",
    "coding_agent_playbook.git_client",
    "coding_agent_playbook.git_env",
    "coding_agent_playbook.gitignore",
    "coding_agent_playbook.guard_config",
    "coding_agent_playbook.harness",
    "coding_agent_playbook.hook_policy",
    "coding_agent_playbook.hook_registrations",
    "coding_agent_playbook.hook_runtime",
    "coding_agent_playbook.hooks_config",
    "coding_agent_playbook.links",
    "coding_agent_playbook.metrics_config",
    "coding_agent_playbook.orchestrator",
    "coding_agent_playbook.prompt_rule_delivery",
    "coding_agent_playbook.renderer",
    "coding_agent_playbook.rule_registry",
    "coding_agent_playbook.skill_document",
    "coding_agent_playbook.skill_membership",
    "coding_agent_playbook.sources",
    "coding_agent_playbook.types",
    "jinja2",
    "packaging",
    "yaml",
]
ignore_imports = [
    # N22: the metrics gate leaves the kernel and takes MetricConfig with it
    "coding_agent_playbook.evaluators.metrics_gate -> coding_agent_playbook.config",
    "coding_agent_playbook.evaluators.types -> coding_agent_playbook.metrics_config",
    # N15: TEST_PATH_GLOBS moves to artifacts/path_classes.py
    "coding_agent_playbook.evaluators.paths -> coding_agent_playbook.gate_scan",
    # A12: the glob grammar moves to artifacts/path_globs.py (after #62)
    "coding_agent_playbook.evaluators.paths -> coding_agent_playbook.hook_runtime.**",
    # N15 or N22, whichever lands first: FIXTURE_GLOBS leaves types.py
    "coding_agent_playbook.evaluators.types -> coding_agent_playbook.hook_runtime.**",
]
broken_contract_guidance = """
The grading kernel is shared by eval tasks and the metrics gate, so it imports neither, nor
the hook runtime: only the stdlib, itself and STDLIB_LEAVES (tests/engine_modules.py).
"""

[[tool.importlinter.contracts]]
id = "command-independence"
name = "No command imports another command"
type = "independence"
modules = [
    "coding_agent_playbook.commands.check",
    "coding_agent_playbook.commands.check_commit_trailers",
    "coding_agent_playbook.commands.check_deps",
    "coding_agent_playbook.commands.check_notebooks",
    "coding_agent_playbook.commands.ci",
    "coding_agent_playbook.commands.eval",
    "coding_agent_playbook.commands.gate_scan",
    "coding_agent_playbook.commands.import_harness",
    "coding_agent_playbook.commands.init",
    "coding_agent_playbook.commands.metrics",
    "coding_agent_playbook.commands.render",
    "coding_agent_playbook.commands.scan_secrets",
    "coding_agent_playbook.commands.scan_sinks",
    "coding_agent_playbook.commands.sync",
    "coding_agent_playbook.commands.validate",
    "coding_agent_playbook.commands.validate_harness",
]
ignore_imports = [
    # N8: resolve_range moves to commands/twins/_git_scope.py
    "coding_agent_playbook.commands._secret_scope -> coding_agent_playbook.commands.gate_scan",
    "coding_agent_playbook.commands.check_commit_trailers -> coding_agent_playbook.commands.gate_scan",
    "coding_agent_playbook.commands.scan_sinks -> coding_agent_playbook.commands.gate_scan",
    # A6: init calls sync.pipeline.execute, not the sync command (after #62)
    "coding_agent_playbook.commands.init -> coding_agent_playbook.commands.sync",
    # A4: the sync command imports validation/, not the validate command (after #62)
    "coding_agent_playbook.commands.sync -> coding_agent_playbook.commands.validate",
]
broken_contract_guidance = """
Shared code goes below commands (a domain package) or into a commands/_helper module that
imports no command.
"""

[[tool.importlinter.contracts]]
id = "private-modules"
name = "An underscore module is imported only from inside its own package"
type = "private_modules"
containers = ["coding_agent_playbook"]
ignore_imports = [
    # A7: adapters/_skill_files.py becomes generated_output/source_files.py (after #62)
    "coding_agent_playbook.commands._import_files -> coding_agent_playbook.adapters._skill_files",
    # N13: becomes adapters/claude_code/settings/drift.py
    "coding_agent_playbook.commands.check -> coding_agent_playbook.adapters._settings_drift",
    # CP-3: init's configure() owns --adapters (after #62)
    "coding_agent_playbook.cli -> coding_agent_playbook.commands._init_adapters",
    # N22: becomes metrics_gate/inputs.py
    "coding_agent_playbook.hook_runtime.handlers._metrics_pass -> coding_agent_playbook.evaluators._metrics_inputs",
    # N22: becomes metrics_gate/suite.py
    "coding_agent_playbook.hook_runtime.handlers.coverage_diff_gate -> coding_agent_playbook.evaluators._metrics_suite",
    # N15: FIXTURE_GLOBS moves to the stdlib leaf artifacts/path_classes.py
    "coding_agent_playbook.evaluators.paths -> coding_agent_playbook.hook_runtime.handlers._eval_paths",
    "coding_agent_playbook.evaluators.types -> coding_agent_playbook.hook_runtime.handlers._eval_paths",
    "coding_agent_playbook.gate_scan -> coding_agent_playbook.hook_runtime.handlers._eval_paths",
    "coding_agent_playbook.guard_config -> coding_agent_playbook.hook_runtime.handlers._eval_paths",
    # A16: hook_runtime/_ruff.py becomes the public hook_runtime/ruff.py (after #62)
    "coding_agent_playbook._guard_config_quality -> coding_agent_playbook.hook_runtime._ruff",
    "coding_agent_playbook._guard_config_ruff -> coding_agent_playbook.hook_runtime._ruff",
    # N16: becomes hook_runtime/config/keys.py
    "coding_agent_playbook._guard_config_secrets -> coding_agent_playbook.hook_runtime._config_keys",
    "coding_agent_playbook.hook_policy.handler_catalog -> coding_agent_playbook.hook_runtime._config_keys",
    # N17: becomes hook_runtime/shell/wrappers.py
    "coding_agent_playbook.guard_config -> coding_agent_playbook.hook_runtime._shell_wrappers",
    # GC-1: the constants move to hook_runtime/config/schema.py (after #62)
    "coding_agent_playbook.guard_config -> coding_agent_playbook.hook_runtime.handlers._control_plane_paths",
    "coding_agent_playbook.guard_config -> coding_agent_playbook.hook_runtime.handlers._control_plane_text",
    # N14: the twin-shared judges get public modules in hook_runtime/judges/
    "coding_agent_playbook.commands.check_deps -> coding_agent_playbook.hook_runtime.handlers._dependency_tiers",
    "coding_agent_playbook.commands.check_deps -> coding_agent_playbook.hook_runtime.handlers._manifest_diff",
    "coding_agent_playbook.commands.check_notebooks -> coding_agent_playbook.hook_runtime.handlers._notebook_check",
    "coding_agent_playbook.guard_config -> coding_agent_playbook.hook_runtime.handlers._notebook_check",
    "coding_agent_playbook.commands.scan_sinks -> coding_agent_playbook.hook_runtime.handlers._notebook_cells",
    # N18: becomes hook_runtime/git/parse.py
    "coding_agent_playbook.commands._secret_scope -> coding_agent_playbook.hook_runtime._git_parse",
    "coding_agent_playbook.commands.check_notebooks -> coding_agent_playbook.hook_runtime._git_parse",
    "coding_agent_playbook.commands.scan_sinks -> coding_agent_playbook.hook_runtime._git_parse",
    # N15: the gate judge moves inside hook_runtime, where _git_parse is its own package's
    "coding_agent_playbook.gate_scan -> coding_agent_playbook.hook_runtime._git_parse",
    # N21: becomes hook_runtime/harness/payload.py
    "coding_agent_playbook.hook_runtime.dispatch -> coding_agent_playbook.hook_runtime.harness._payload",
    # A3: becomes skills/naming.py (after #62)
    "coding_agent_playbook.commands._sync_lockfile -> coding_agent_playbook.adapters._agent_skill_rules",
    "coding_agent_playbook.commands._sync_render -> coding_agent_playbook.adapters._agent_skill_rules",
    "coding_agent_playbook.commands._validate_skills -> coding_agent_playbook.adapters._agent_skill_rules",
    "coding_agent_playbook.commands._validation -> coding_agent_playbook.adapters._agent_skill_rules",
    "coding_agent_playbook.skill_document -> coding_agent_playbook.adapters._agent_skill_rules",
    "coding_agent_playbook.skill_membership -> coding_agent_playbook.adapters._agent_skill_rules",
    # A9: becomes adapters/skill_dirs/ownership.py (after #62)
    "coding_agent_playbook.commands.sync -> coding_agent_playbook.adapters._prior_output",
    # A7: becomes generated_output/write_guard.py (after #62)
    "coding_agent_playbook.commands._sync_hooks -> coding_agent_playbook.adapters._owned_files",
    "coding_agent_playbook.commands.sync -> coding_agent_playbook.adapters._owned_files",
    # A9: becomes adapters/skill_dirs/writer.py (after #62)
    "coding_agent_playbook.commands._sync_output -> coding_agent_playbook.adapters._skill_writer",
    "coding_agent_playbook.commands.sync -> coding_agent_playbook.adapters._skill_writer",
    "coding_agent_playbook.commands.validate -> coding_agent_playbook.adapters._skill_writer",
    # A7: becomes generated_output/source_files.py (after #62)
    "coding_agent_playbook.commands.validate -> coding_agent_playbook.adapters._skill_sources",
    "coding_agent_playbook.guard_config -> coding_agent_playbook.adapters._skill_sources",
    # A17: becomes hooks/contract/findings.py (after #62)
    "coding_agent_playbook.commands._validate_hooks -> coding_agent_playbook.hook_policy._findings",
]
broken_contract_guidance = """
Import a public module of the owning package, or move the importer inside that package.
"""
```

How each contract holds today:

| id | Type | Rule | Baseline today | Burned down by |
|---|---|---|---|---|
| `engine-layers` | layers | A package imports only packages below it; target order of ADR 0002 with L6/L10 names. | 2 edges; 49 `exhaustive_ignores` | CF-2 (`_typing`); catalog-layers (not scheduled, L12); every move PR (exhaustive) |
| `stdlib-leaves` | forbidden | The 9 leaves import only the stdlib and each other. | none | — |
| `hook-runtime-stack` | forbidden | The hook runtime imports only itself and the leaves. | 13 deferred-branch lines (permanent, renamed by moves; the 2 `gate_scan` lines go with N15) | N15; N22, N25 and A14-A16 rename |
| `grading-kernel` | forbidden | The grading kernel imports only itself and the leaves. | 5 lines | N15, N22, A12 |
| `command-independence` | independence | No command module imports another. | 5 lines | N8; A4 and A6 (after #62) |
| `private-modules` | `private_modules` (custom) | Rule (2) of L4. | 41 lines | the PR named in each comment |

The layer order comes from ADR 0002's dependency direction (synthesize.json `target_layout`), refined by today's edges:

- `adapters` imports `renderer`, `hook_policy`, `hook_registrations` and `skill_document`, so it sits above rendering, hooks and skills.
- `renderer` imports `hook_policy` and `hook_registrations`, so rendering sits above hooks.
- `commands/validate.py` imports `evals.loader`/`validator`, so validation sits above evals.
- sync runs the validation gate, so sync sits above validation.
- No tier uses `:` (ADR 0002 allows no two-way package dependency): `config` imports `catalog` (`config.py:20`, `config_schema.py:18`), `detector` (`_committed_config.py:28`, after N10) and `lockfile` (`sources/filesystem.py:25`, after N2), so it sits above them; `catalog`, `detector` and `lockfile` import none of each other, so `catalog` sits above the independent pair `detector | lockfile` (room for `catalog.resolve` to read detector facts later). In the leaves, `generated_output` imports `artifacts` (the `Skill` type, after A7) and `security`, so it sits above `artifacts`, which sits above the independent `security | toml_writer | _plugin_registry`.
- `agent_harness | evals | precommit` are independent siblings.
- `metrics_gate` sits alone below `skills` (harmonisation H5): the sync-time quality reader of `hooks/guard_config` reads `[metrics]` through `metrics_gate.config`, and `metrics_gate` imports only `config`, `grading` and the leaves.
- The grading kernel sits alone directly above the bottom line, so nothing in it imports catalog, config, detector or lockfile.

##### 0.6.2 Why rule (2) is a custom contract type

The built-in `protected` contract needs a fixed allow-list per contract (D0-7). This type derives the owner instead:

- A module is private to the package above its first underscore segment. Dunder names are not private.
- Any module inside that package, at any depth, may import it.
- A root-level underscore module (`_toml`, `_sentinel`) is private to the engine as a whole, so any engine module may import it. Moving it into a package is what makes it package-private (section 0.7.2, R1).

##### 0.6.3 New `tests/architecture/private_modules_contract.py`

```python
"""import-linter contract type: an underscore module is imported only from inside its own package.

ADR 0002 rule 2. A module is private to the package above its first underscore
segment: ``coding_agent_playbook.adapters._skill_writer`` is private to
``coding_agent_playbook.adapters``, and ``coding_agent_playbook.hook_runtime.handlers._shared.paths``
to ``coding_agent_playbook.hook_runtime.handlers``. Any module inside that package,
at any depth, may import it; nothing else may. Dunder names (``__init__``,
``__main__``) are not private. A root-level underscore module is private to the
engine as a whole, so every engine module may import it.

import-linter's built-in ``protected`` contract takes one fixed allow-list per
contract, so "its own package" would need one contract per package, kept in step
with every move by hand. This type derives the owner from the name instead.
pyproject.toml registers it as ``private_modules``;
tests/architecture/test_import_contracts.py runs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from importlinter import Contract, ContractCheck, fields, output
from importlinter.application import contract_utils

if TYPE_CHECKING:
    from collections.abc import Iterable

    from grimp import ImportGraph
    from importlinter.domain.imports import ImportExpression, Module


@dataclass(frozen=True)
class PrivateImport:
    """One direct import of a private module from outside the package that owns it."""

    importer: str
    imported: str
    owner: str
    line_numbers: tuple[int, ...]


def _is_private_segment(segment: str) -> bool:
    is_dunder = segment.startswith("__") and segment.endswith("__")
    return segment.startswith("_") and not is_dunder


def private_owner(module: str) -> str | None:
    """The package ``module`` is private to, or ``None`` when no segment is private.

    Example::

        >>> private_owner("pkg.adapters._skill_writer.plan")
        'pkg.adapters'
        >>> private_owner("pkg.hook_runtime.__main__") is None
        True
    """
    segments = module.split(".")
    for index, segment in enumerate(segments[1:], start=1):
        if _is_private_segment(segment):
            return ".".join(segments[:index])
    return None


def is_inside(module: str, package: str) -> bool:
    """Whether ``module`` is ``package`` itself or one of its descendants.

    Example::

        >>> is_inside("pkg.adapters.base", "pkg.adapters"), is_inside("pkg.adapters_x", "pkg.adapters")
        (True, False)
    """
    return module == package or module.startswith(f"{package}.")


def _leaks_of(graph: ImportGraph, imported: str, owner: str) -> list[PrivateImport]:
    importers = graph.find_modules_that_directly_import(imported)
    leaks = []
    for importer in sorted(m for m in importers if not is_inside(m, owner)):
        details = graph.get_import_details(importer=importer, imported=imported)
        lines = tuple(sorted({detail["line_number"] for detail in details}))
        leaks.append(PrivateImport(importer, imported, owner, lines))
    return leaks


def find_private_imports(graph: ImportGraph, containers: Iterable[str]) -> list[PrivateImport]:
    """Every direct import, into a private module under ``containers``, from outside its owner.

    Example::

        >>> import grimp
        >>> graph = grimp.ImportGraph()
        >>> graph.add_import(importer="pkg.cli", imported="pkg.commands._helper")
        >>> [leak.importer for leak in find_private_imports(graph, ["pkg"])]
        ['pkg.cli']
    """
    roots = tuple(containers)
    leaks: list[PrivateImport] = []
    for imported in sorted(graph.modules):
        owner = private_owner(imported)
        if owner is not None and any(is_inside(imported, root) for root in roots):
            leaks.extend(_leaks_of(graph, imported, owner))
    return leaks


class PrivateModulesContract(Contract):
    """Underscore modules under ``containers`` are imported only from inside their owner.

    Options: ``containers`` (the packages whose private modules are checked), and
    ``ignore_imports`` / ``unmatched_ignore_imports_alerting`` /
    ``broken_contract_guidance`` with the built-in contracts' meaning: an ignored
    import that matches nothing fails by default.
    """

    containers = fields.ListField(subfield=fields.ModuleField())
    ignore_imports = fields.SetField(subfield=fields.ImportExpressionField(), required=False)
    unmatched_ignore_imports_alerting = fields.EnumField(
        contract_utils.AlertLevel, default=contract_utils.AlertLevel.ERROR
    )
    broken_contract_guidance = fields.TextField(required=False)

    def check(self, graph: ImportGraph, verbose: bool) -> ContractCheck:
        ignored = cast("set[ImportExpression] | None", self.ignore_imports)
        removal = contract_utils.remove_ignored_imports_and_report(
            graph=graph,
            ignore_imports=sorted(ignored or (), key=str),
            unmatched_alerting=cast(
                "contract_utils.AlertLevel", self.unmatched_ignore_imports_alerting
            ),
        )
        containers = cast("list[Module]", self.containers)
        leaks = find_private_imports(graph, (module.name for module in containers))
        output.verbose_print(
            verbose, f"{len(leaks)} private-module imports from outside their owner"
        )
        return ContractCheck(
            kept=not leaks,
            warnings=list(removal.warnings),
            ignored_import_count=removal.ignored_import_count,
            metadata={"leaks": leaks},
        )

    def render_broken_contract(self, check: ContractCheck) -> None:
        leaks = cast("list[PrivateImport]", check.metadata["leaks"])
        for leak in leaks:
            lines = ", ".join(map(str, leak.line_numbers))
            message = f"- {leak.importer} -> {leak.imported} (l.{lines}): private to {leak.owner}"
            output.print_error(message, bold=False)
        output.new_line()
        guidance = cast("str | None", self.broken_contract_guidance)
        contract_utils.render_broken_contract_guidance(guidance)
```

##### 0.6.4 New `tests/architecture/test_import_contracts.py`

```python
"""The import contracts in pyproject.toml hold, and their package lists track the tree (ADR 0002).

``test_import_contracts_hold`` runs import-linter in a fresh interpreter from the
repository root, so ``pytest -q`` enforces the layers, the stdlib leaves and the two
stacks built on them, command independence and the private-module rule without a
fifth CI command. The other tests close the gaps import-linter leaves open: it
skips an optional layer that does not exist (a typo would never be checked),
accepts an ``exhaustive_ignores`` entry that names nothing, and cannot derive a
forbidden list from the tree.
"""

from __future__ import annotations

import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any, Final

import pytest

from tests.engine_modules import (
    ENGINE,
    STDLIB_LEAVES,
    child_modules,
    non_leaf_modules,
    runtime_dependency_imports,
)
from tests.import_probe import probe_env

_REPO_ROOT: Final = Path(__file__).resolve().parents[2]
_LINT_TIMEOUT_S: Final = 120
#: No cache: the run must see this checkout, and must not write .import_linter_cache/.
_LINT: Final = (
    "import sys; from importlinter.cli import lint_imports; "
    "sys.exit(lint_imports(config_filename='pyproject.toml', no_cache=True, no_logo=True))"
)
#: The top-level packages of ADR 0002's target layout that sit in engine-layers.
#: hook_runtime is a separate stack (hook-runtime-stack), never a layer.
_TARGET_PACKAGES: Final = frozenset(
    {
        "_plugin_registry",
        "adapters",
        "agent_harness",
        "artifacts",
        "catalog",
        "cli",
        "commands",
        "config",
        "detector",
        "evals",
        "generated_output",
        "grading",
        "hooks",
        "lockfile",
        "metrics_gate",
        "precommit",
        "rendering",
        "security",
        "skills",
        "sync",
        "toml_writer",
        "validation",
    }
)


def _contract(contract_id: str) -> dict[str, Any]:
    pyproject = tomllib.loads((_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    contracts: list[dict[str, Any]] = pyproject["tool"]["importlinter"]["contracts"]
    (contract,) = [c for c in contracts if c["id"] == contract_id]
    return contract


def _layer_names(layers: list[str]) -> list[tuple[str, bool]]:
    """Each layer name with whether it is optional (parenthesised), in layer order."""
    names = []
    for layer in layers:
        separator = "|" if "|" in layer else ":"
        for raw in layer.split(separator):
            name = raw.strip()
            optional = name.startswith("(") and name.endswith(")")
            names.append((name.strip("()"), optional))
    return names


def _top_level_names() -> set[str]:
    return {name.rsplit(".", 1)[1] for name in child_modules(ENGINE)}


def test_import_contracts_hold() -> None:
    result = subprocess.run(
        [sys.executable, "-c", _LINT],
        cwd=_REPO_ROOT,
        capture_output=True,
        text=True,
        timeout=_LINT_TIMEOUT_S,
        env={**probe_env(), "COLUMNS": "200"},
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize(
    ("contract_id", "stack"),
    [("hook-runtime-stack", "hook_runtime"), ("grading-kernel", "evaluators")],
)
def test_stack_contract_forbids_every_non_leaf_module(contract_id: str, stack: str) -> None:
    contract = _contract(contract_id)

    assert contract["source_modules"] == [f"{ENGINE}.{stack}"]
    expected = [*non_leaf_modules(stack), *runtime_dependency_imports()]
    assert contract["forbidden_modules"] == expected


def test_leaf_contract_covers_every_stdlib_leaf() -> None:
    contract = _contract("stdlib-leaves")

    assert contract["source_modules"] == sorted(f"{ENGINE}.{leaf}" for leaf in STDLIB_LEAVES)
    expected = [*non_leaf_modules(), *runtime_dependency_imports()]
    assert contract["forbidden_modules"] == expected


def test_layer_names_are_target_packages() -> None:
    names = _layer_names(_contract("engine-layers")["layers"])

    assert sorted(name for name, _ in names if name not in _TARGET_PACKAGES) == []


def test_a_layer_is_optional_exactly_until_its_package_exists() -> None:
    existing = _top_level_names()
    names = _layer_names(_contract("engine-layers")["layers"])

    assert sorted(name for name, optional in names if optional and name in existing) == []
    assert sorted(name for name, optional in names if not optional and name not in existing) == []


def test_exhaustive_ignores_are_exactly_the_unplaced_top_level_modules() -> None:
    contract = _contract("engine-layers")
    placed = {name for name, _ in _layer_names(contract["layers"])}

    assert contract["exhaustive"] is True
    assert contract["exhaustive_ignores"] == sorted(_top_level_names() - placed)


def test_command_independence_lists_every_command() -> None:
    commands = [
        name
        for name in child_modules(f"{ENGINE}.commands")
        if not name.rsplit(".", 1)[1].startswith("_")
    ]

    assert _contract("command-independence")["modules"] == commands
```

##### 0.6.5 New `tests/architecture/test_private_modules_contract.py`

```python
"""The ``private_modules`` import-linter contract type (ADR 0002 rule 2), on in-memory graphs."""

from __future__ import annotations

import grimp
import pytest
from importlinter.domain.helpers import MissingImport

from tests.architecture.private_modules_contract import (
    PrivateImport,
    PrivateModulesContract,
    find_private_imports,
    is_inside,
    private_owner,
)


def _graph(*imports: tuple[str, str]) -> grimp.ImportGraph:
    graph = grimp.ImportGraph()
    for importer, imported in imports:
        graph.add_import(importer=importer, imported=imported, line_number=1, line_contents="")
    return graph


def _contract(**options: object) -> PrivateModulesContract:
    return PrivateModulesContract(
        name="private", session_options={}, contract_options={"containers": ["pkg"], **options}
    )


@pytest.mark.parametrize(
    ("module", "owner"),
    [
        ("pkg._toml", "pkg"),
        ("pkg.adapters._skill_writer", "pkg.adapters"),
        ("pkg.hook_runtime.handlers._shared.paths", "pkg.hook_runtime.handlers"),
        ("pkg.adapters.base", None),
        ("pkg.hook_runtime.__main__", None),
    ],
)
def test_private_owner_is_the_package_above_the_first_underscore(
    module: str, owner: str | None
) -> None:
    assert private_owner(module) == owner


def test_is_inside_matches_whole_segments_only() -> None:
    assert is_inside("pkg.adapters", "pkg.adapters")
    assert is_inside("pkg.adapters.claude.paths", "pkg.adapters")
    assert not is_inside("pkg.adapters_extra", "pkg.adapters")


def test_an_import_from_inside_the_owner_is_kept() -> None:
    graph = _graph(
        ("pkg.adapters.claude.paths", "pkg.adapters._json_edits"), ("pkg.x", "pkg._toml")
    )

    assert find_private_imports(graph, ["pkg"]) == []


def test_an_import_from_outside_the_owner_is_reported_with_its_lines() -> None:
    graph = _graph(("pkg.commands.sync", "pkg.adapters._skill_writer"))

    assert find_private_imports(graph, ["pkg"]) == [
        PrivateImport("pkg.commands.sync", "pkg.adapters._skill_writer", "pkg.adapters", (1,))
    ]


def test_a_sibling_subpackage_is_outside_the_owner() -> None:
    graph = _graph(("pkg.hook_runtime.dispatch", "pkg.hook_runtime.harness._payload"))

    [leak] = find_private_imports(graph, ["pkg"])

    assert leak.owner == "pkg.hook_runtime.harness"


def test_the_contract_breaks_on_a_leak_and_keeps_once_it_is_ignored() -> None:
    def check(**options: object) -> bool:
        graph = _graph(("pkg.cli", "pkg.commands._init_adapters"))
        return _contract(**options).check(graph, verbose=False).kept

    assert not check()
    assert check(ignore_imports=["pkg.cli -> pkg.commands._init_adapters"])


def test_an_ignored_import_that_matches_nothing_fails() -> None:
    graph = _graph(("pkg.cli", "pkg.commands.sync"))

    with pytest.raises(MissingImport, match="No matches for ignored import"):
        _contract(ignore_imports=["pkg.cli -> pkg.commands._gone"]).check(graph, verbose=False)


def test_render_names_each_leak_and_the_guidance(capsys: pytest.CaptureFixture[str]) -> None:
    contract = _contract(broken_contract_guidance="Import a public module instead.")
    check = contract.check(_graph(("pkg.cli", "pkg.commands._init_adapters")), verbose=False)

    contract.render_broken_contract(check)

    out = capsys.readouterr().out
    assert "pkg.cli -> pkg.commands._init_adapters (l.1): private to pkg.commands" in out
    assert "Import a public module instead." in out
```

##### 0.6.6 New `tests/architecture/test_package_inits.py`

```python
"""A package ``__init__.py`` holds only a docstring (ADR 0002): its interface is its public modules.

Re-exports would give every name two spellings and cost import time on the hook
hot path. The root ``__init__`` is the one exception (the lazy ``__version__``,
tests/unit/test_package_init.py). The packages that hold code today are listed in
``_INITS_WITH_CODE``; the move or deepening PR that empties one removes its entry,
and test_inits_with_code_baseline_is_current fails until it does.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest

_SRC: Final = Path(__file__).resolve().parents[2] / "src"
_ROOT_INIT: Final = "coding_agent_playbook/__init__.py"
_INITS_WITH_CODE: Final = frozenset(
    {
        "coding_agent_playbook/evals/__init__.py",
        "coding_agent_playbook/evaluators/__init__.py",
        "coding_agent_playbook/evaluators/builtins/__init__.py",
        "coding_agent_playbook/evaluators/checks/__init__.py",
        "coding_agent_playbook/evaluators/execution/__init__.py",
        "coding_agent_playbook/hook_policy/__init__.py",
        "coding_agent_playbook/hook_registrations/__init__.py",
        "coding_agent_playbook/hook_runtime/harness/__init__.py",
    }
)


def holds_only_a_docstring(source: str) -> bool:
    """Whether ``source`` is at most a docstring plus ``from __future__`` imports.

    Example::

        >>> holds_only_a_docstring("'The adapters.'"), holds_only_a_docstring("x = 1")
        (True, False)
    """
    body = ast.parse(source).body
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
        body = body[1:]
    return all(isinstance(s, ast.ImportFrom) and s.module == "__future__" for s in body)


def _inits_with_code() -> set[str]:
    inits = sorted(_SRC.joinpath("coding_agent_playbook").rglob("__init__.py"))
    relative = {path.relative_to(_SRC).as_posix(): path for path in inits}
    return {
        name
        for name, path in relative.items()
        if name != _ROOT_INIT and not holds_only_a_docstring(path.read_text(encoding="utf-8"))
    }


def test_package_inits_hold_only_a_docstring() -> None:
    assert sorted(_inits_with_code() - _INITS_WITH_CODE) == []


def test_inits_with_code_baseline_is_current() -> None:
    assert sorted(_INITS_WITH_CODE - _inits_with_code()) == []


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("", True),
        ('"""Doc."""\nfrom __future__ import annotations\n', True),
        ('"""Doc."""\nfrom .base import Adapter\n', False),
        ("__all__ = []\n", False),
    ],
)
def test_holds_only_a_docstring(source: str, expected: bool) -> None:
    assert holds_only_a_docstring(source) is expected
```

##### 0.6.7 `.gitignore`

Append after the `.ruff_cache/` block (`.gitignore:206-207`):

```gitignore

# import-linter graph cache (lint-imports run by hand; the pytest run passes --no-cache)
.import_linter_cache/
```

#### 0.7 Tightening protocol (every move PR and deepening PR)

##### 0.7.1 Checklist

Run `pytest -q tests/architecture tests/hook_runtime/test_import_budget.py tests/hook_runtime/test_import_budget_stop.py tests/hook_runtime/test_stage_factories.py`. Every item below has a test that fails until it is done.

| When the PR… | Edit | The test that fails if it is forgotten |
|---|---|---|
| removes or renames a top-level module | delete its name from `exhaustive_ignores` | `test_exhaustive_ignores_are_exactly_the_unplaced_top_level_modules` |
| creates a target package | drop the parentheses of its layer; never add a name that is not in `_TARGET_PACKAGES` | `test_a_layer_is_optional_exactly_until_its_package_exists`, `test_layer_names_are_target_packages` |
| changes the top-level tree | regenerate the three `forbidden_modules` lists | `test_stack_contract_forbids_every_non_leaf_module`, `test_leaf_contract_covers_every_stdlib_leaf` |
| moves a module named in any `ignore_imports` | rename the line to the new path, or delete it if the import is gone | `test_import_contracts_hold` (`No matches for ignored import …`) |
| moves a leaf, or makes a stack need a new stdlib-only module | edit `STDLIB_LEAVES` (dotted entries allowed) | `test_every_stdlib_leaf_resolves`, the stack and leaf contracts |
| moves a module a probe pins | rename the `engine_module(...)` argument | collection error `StaleModulePin: '<old>' no longer resolves` |
| moves a module a branch allowance names | rename it in the `allowed=` tuple | `StaleModulePin` from `_forbidden` |
| renames `evaluators` to `grading` | `source_modules` of `grading-kernel` and the `("grading-kernel", "evaluators")` parameter | `test_stack_contract_forbids_every_non_leaf_module` |
| changes commands' public modules | regenerate `command-independence.modules` | `test_command_independence_lists_every_command` |
| empties a package `__init__` | delete it from `_INITS_WITH_CODE` | `test_inits_with_code_baseline_is_current` |
| moves a stage module | nothing in the tests; update `STAGE_FACTORIES` | `test_every_stage_factory_resolves` |

The same path-rewrite map that the move PR applies to the living docs (L9) is applied to `pyproject.toml`'s `[tool.importlinter]` strings and to the `engine_module(...)` arguments in `tests/`.

##### 0.7.2 Rules for baseline entries

- **R1.** A move-only PR may rename an entry or delete a dead one. It may add an entry only for an import that existed before the move and becomes visible through the move. Two cases make an import visible: a root-level `_x` that every engine module could import turns package-private, or a package enters its layer and an old upward edge shows. Each added entry carries a comment naming the deepening PR that removes it. A move PR never adds an import (L1, L13).
- **R2.** A deepening (behaviour) PR deletes the entries it resolves and adds none.
- **R3.** In a move, a module that code outside its new package imports gets a public name (no underscore). That is preferred over a new `private-modules` entry: the module is part of that package's interface.
- **R4.** The `hook-runtime-stack` ignore lines are the runtime's deferred branches. They are permanent and renamed by moves. A new deferred branch adds its line and a branch-local allowance in the import-budget probes in the same PR.
- **R5.** `STDLIB_LEAVES` grows only by a stdlib-only module that the hook runtime or the grading kernel needs. `stdlib-leaves` proves the first property.

##### 0.7.3 Worked examples

- **N2 (the config package)**: `config.py` becomes `config/` with `config_entries`, `config_schema`, `hooks_config`, `_table_shapes` and the `LinksConfig` half of `links.py` inside (`links.py` keeps its link checker until A4).
  - The four whole-module names leave `exhaustive_ignores`, and the three forbidden lists are regenerated. `config` is already a layer, so all of `config/` is now checked at the `config` layer, above `catalog` and `detector | lockfile`.
  - The eval-task allowance in `test_import_budget.py` drops the four names that moved (the `config` entry now covers the package). `StaleModulePin` names each one.
  - `config/__init__.py` is docstring-only. A re-export there fails `test_package_inits_hold_only_a_docstring` (L2, L5).
- **N15 (the gate-weakening judge)**: `gate_scan.py` and `_gate_scan_files.py` move into `hook_runtime/judges/` as `gate_weakening.py` and `_gate_weakening_files.py`; `TEST_PATH_GLOBS` and `handlers/_eval_paths.py` move to the stdlib leaf `artifacts/path_classes.py`.
  - The two `gate_scan` lines of `hook-runtime-stack`, `evaluators.paths -> gate_scan` in `grading-kernel`, and the four `_eval_paths` lines and `gate_scan -> hook_runtime._git_parse` of `private-modules` go dead and are deleted. The three `commands.gate_scan` lines of `command-independence` go with N8, which moves `resolve_range` to `commands/twins/_git_scope.py`.
  - `_GATE_SCAN` and `_GATE_SCAN_FILES` in `test_import_budget_stop.py` are renamed; `(artifacts)` loses its parentheses and `artifacts.path_classes` joins `STDLIB_LEAVES`, because the pre-edit eval-fixture guard loads it on the hot path.
  - Why not `security/`: `security` is a stdlib leaf, and `gate_scan.py:43-46` imports `hook_runtime._git_parse`, `caps`, `globs` and `handlers._eval_paths`, so `stdlib-leaves` would break (harmonisation H3, question 1, resolved 2026-10-18).
- **N25 (the grading rename, L6)**, after N22 has taken the metrics gate out of the kernel:
  - `(grading)` loses its parentheses and `evaluators` leaves `exhaustive_ignores`;
  - `grading-kernel.source_modules` becomes `coding_agent_playbook.grading`, the `("grading-kernel", "evaluators")` test parameter follows, and every `evaluators` string in `ignore_imports` becomes `grading`;
  - the four `evaluators/…/__init__.py` baseline entries leave `_INITS_WITH_CODE`, because N25 makes those inits docstring-only (`_METRICS_GATE` was already renamed by N22).
  - No upward edge becomes visible: N22 already moved `evaluators/metrics_gate.py`, the only kernel module that imports `config`, to `metrics_gate/run.py`, and `metrics_gate` sits above the `config` tier.
- **N5 (the lockfile package)**: `_lock_drift` and `_canonical_json` move inside `lockfile/` and leave `STDLIB_LEAVES`. If `lockfile/files.py` writes TOML through `toml_writer`, `toml_writer` must join `STDLIB_LEAVES`, because `hook_runtime → lockfile → toml_writer` is otherwise a `hook-runtime-stack` violation. The contract makes that admission explicit.

##### 0.7.4 End state

After the last move:
- `engine-layers` has no parenthesised layer and `exhaustive_ignores = ["hook_runtime"]`.
- Every `ignore_imports` list is empty except two:
  - `hook-runtime-stack` keeps its deferred-branch lines (into `grading`, `metrics_gate`, `evals`, `catalog`, `detector`, `artifacts`);
  - an entry the scheduler chose to keep, such as the catalog-to-evals edge while catalog-layers stays unscheduled.
- `_INITS_WITH_CODE` and `_DEFERRED_UNTIL_CHAIN_MERGES` are empty.
- `STDLIB_LEAVES` is whatever the moves admitted; section 6.4 lists the expected end state.

#### 0.8 Interaction with the in-flight chain (#49-#62)

- **Shared file.** Lane 0 edits one chain file, `tests/hook_runtime/test_import_budget.py`. The chain appends `test_skill_nudge_loads_nothing_forbidden_on_a_python_edit` (specs/prS-skills-context.md:3868). Lane 0 changes only the docstring, the constants and `_forbidden`'s body, and keeps every name and signature, so the appended test works unchanged. Whichever PR lands second rebases; the conflict is textual only.
- **Deferred pins.** The three raw pins in chain-edited test files are deferred to T0.3 (section 0.5.4).
- **New top-level module.** After T0.2, a chain ticket that adds a top-level module edits `pyproject.toml` in the same PR: #58 adds `src/coding_agent_playbook/_guard_config_skills.py` (spec:3720). It adds the name to `exhaustive_ignores` and to the three forbidden lists; the failing tests print the expected lists. Any import it makes of another package's private module (for example `adapters._skill_sources`) gets a `private-modules` line under `# chain #58: guard-config-contract writer side (after #62)`.
- **#52.** If T0.2 merges first, #52's new `commands/_validate_skills.py -> hook_policy._findings` import (`did_you_mean`, spec:3171) needs its own `private-modules` line, commented `# A17: becomes hooks/contract/findings.py (after #62)`. A line cannot be added before the import exists: an unmatched ignore fails the run.
- **Removed imports.** A chain ticket that removes an import listed in a baseline deletes that line. import-linter names it.
- **New skill-nudge handler.** If it imports a sync-side module, `hook-runtime-stack` fails. That is correct: the chain's own budget test requires `_forbidden(...) == []` on that branch.
- **`hook_policy/__init__.py`.** The chain edits it, and it stays in `_INITS_WITH_CODE`. If the chain empties it, `test_inits_with_code_baseline_is_current` asks for the entry to be deleted.

#### 0.9 Tests

| File | Tests |
|---|---|
| `tests/architecture/test_engine_modules.py` (new) | `test_engine_module_returns_a_name_that_resolves`, `test_engine_module_fails_for_a_moved_module[2]`, `test_engine_module_rejects_a_name_outside_the_engine`, `test_every_stdlib_leaf_resolves[9]`, `test_child_modules_lists_modules_and_packages`, `test_child_modules_rejects_a_plain_module`, `test_non_leaf_modules_forbids_a_new_top_level_package`, `test_non_leaf_modules_lists_the_siblings_of_a_dotted_leaf`, `test_non_leaf_modules_rejects_an_unknown_stack`, `test_non_leaf_modules_without_a_stack_forbids_every_stack`, `test_runtime_dependency_imports_reads_the_dependency_table`, `test_runtime_dependency_imports_are_the_engine_dependencies` |
| `tests/architecture/test_module_pins.py` (new) | `test_tests_pin_engine_modules_through_engine_module`, `test_deferred_raw_pins_still_exist`, `test_raw_pins_flags_each_vacuous_spelling[not-in, module-constant, set-display, startswith]`, `test_raw_pins_accepts_loud_spellings[wrapped, equality-list, equality-set, positive-in, probe-code]`, `test_raw_pins_skips_names_that_are_not_modules` |
| `tests/hook_runtime/test_stage_factories.py` (new) | `test_every_stage_factory_resolves[13]` |
| `tests/cli/test_module_entry.py` (new) | `test_python_dash_m_cli_prints_help` |
| `tests/hook_runtime/test_import_budget.py`, `test_import_budget_stop.py` | the existing 37 cases, unchanged in number, now against the derived `FORBIDDEN` |
| `tests/architecture/test_import_contracts.py` (new) | `test_import_contracts_hold`, `test_stack_contract_forbids_every_non_leaf_module[hook-runtime-stack, grading-kernel]`, `test_leaf_contract_covers_every_stdlib_leaf`, `test_layer_names_are_target_packages`, `test_a_layer_is_optional_exactly_until_its_package_exists`, `test_exhaustive_ignores_are_exactly_the_unplaced_top_level_modules`, `test_command_independence_lists_every_command` |
| `tests/architecture/test_private_modules_contract.py` (new) | `test_private_owner_is_the_package_above_the_first_underscore[5]`, `test_is_inside_matches_whole_segments_only`, `test_an_import_from_inside_the_owner_is_kept`, `test_an_import_from_outside_the_owner_is_reported_with_its_lines`, `test_a_sibling_subpackage_is_outside_the_owner`, `test_the_contract_breaks_on_a_leak_and_keeps_once_it_is_ignored`, `test_an_ignored_import_that_matches_nothing_fails`, `test_render_names_each_leak_and_the_guidance` |
| `tests/architecture/test_package_inits.py` (new) | `test_package_inits_hold_only_a_docstring`, `test_inits_with_code_baseline_is_current`, `test_holds_only_a_docstring[4]` |

`tests/architecture/` is cross-cutting, like `tests/integration/` (L8): it tests no single package. The new tests plus the two budget files (109 cases) ran in about 25 s on each Python version, almost all of it the existing budget probes.

#### 0.10 Acceptance criteria

T0.1:
1. No file under `src/` changes, and no dependency changes.
2. `FORBIDDEN` in `tests/hook_runtime/test_import_budget.py` contains no hand-listed engine package. Adding `src/coding_agent_playbook/newpkg.py` and importing it from `hook_runtime/dispatch.py` makes `test_hot_path_branches_import_no_forbidden_module` fail (3 cases).
3. Renaming any module named in an `engine_module(...)` call makes collection fail with `StaleModulePin` naming the old path.
4. `test_tests_pin_engine_modules_through_engine_module` passes with exactly the three deferred entries. Adding `assert "coding_agent_playbook.gate_scan" not in loaded` to any test makes it fail.
5. `test_every_stage_factory_resolves` covers all 13 `STAGE_FACTORIES` rows.
6. `test_python_dash_m_cli_prints_help` passes; it fails if `cli.py` becomes a package without `__main__.py`.
7. `ruff check .`, `ruff format --check .`, `mypy` and `pytest -q` pass on Python 3.12 and 3.13.

T0.2:
1. `pip install -e ".[dev]"` installs `import-linter==2.15` (and grimp 3.17). `.github/workflows/ci.yml` is unchanged.
2. `pytest -q` runs `test_import_contracts_hold`, which reports `Contracts: 6 kept, 0 broken.` with 3, 0, 31, 6, 5 and 41 ignored imports (engine-layers, stdlib-leaves, hook-runtime-stack, grading-kernel, command-independence, private-modules).
3. Each mutation in section 0.4 breaks the contract named there, and the failure message names importer, imported module, line and guidance.
4. An `ignore_imports` line that matches nothing, a stale `exhaustive_ignores` entry, an optional layer whose package exists, and a forbidden list that differs from the tree each fail a named test.
5. Running `lint-imports` by hand from the repo root gives the same verdict, and its `.import_linter_cache/` is ignored by git.
6. The four CI commands pass on Python 3.12 and 3.13.

T0.3 (after #62):
1. `_DEFERRED_UNTIL_CHAIN_MERGES` is empty.
2. `test_deferred_raw_pins_still_exist` is deleted with it, in the same commit.
3. The three sites use `engine_module(...)`.


### 6.2 How the contracts tighten, PR by PR

The checklist of 0.7.1 says which test fails when an edit is forgotten. This table says which edits each PR makes. "Drop" means delete the line or name; "layer" means the parentheses of an optional layer come off because the package now exists. Every PR regenerates the three `forbidden_modules` lists when the top-level tree changes (`test_stack_contract_forbids_every_non_leaf_module` and `test_leaf_contract_covers_every_stdlib_leaf` print the expected lists). Under rule R1 of 0.7.2 a move may also add a line for an existing import that the move makes visible; the known ones are listed, and any other one carries a comment naming the PR that removes it.

| PR | `engine-layers` | `STDLIB_LEAVES` | ignore lines dropped (-) or added (+) | Other |
| --- | --- | --- | --- | --- |
| T0.2 | the target order with optional layers; 49 `exhaustive_ignores` | 9 leaves | the baselines of 0.6.1 | `_INITS_WITH_CODE` (8) |
| N1 | layer `toml_writer`; drop `_toml` from `exhaustive_ignores` | — | — | eval-task allowance `_toml` -> `toml_writer` |
| N2 | drop `config_entries`, `config_schema`, `hooks_config`, `_table_shapes` | — | — | allowance drops those four (`config` covers them) |
| N3 | drop `_layers`, `sources` | `catalog` -> `catalog.roots` (`catalog/source.py` imports yaml and evals) | rename `sources.filesystem -> evals.**` to `catalog.source -> evals.**` (kept, catalog-layers not scheduled); stack: `eval_task_authoring_lint -> sources.**` -> `-> catalog.source` | budget pins `:454`, `:461-463` |
| N4 | drop `_pep503`, `_pyproject_deps` | `_pep503`, `_pyproject_deps` -> `detector.pep503`, `detector.pyproject_deps` | stack: `resync_on_detector_input_change -> detector` -> `-> detector.facts` | budget pins `:439, :441` |
| N5 | drop `_lock_drift`, `_canonical_json` | drop `_lock_drift`, `_canonical_json` (inside the `lockfile` leaf) | — | `_LOCKFILE_MODULE` -> `lockfile.model` |
| N6 | layer `generated_output`; drop `_atomic_io`, `_file_identity`, `_output_io`, `_sentinel`, `_symlinks`, `gitignore` | `_atomic_io`, `_sentinel` -> the dotted `generated_output.atomic_io`, `generated_output.sentinel` (the only two the stacks import: `hook_runtime/protected.py:38`, `handlers/_drift.py:30`, `evaluators/measurement_snapshot.py:21`). Not the whole package: A7 adds `generated_output/source_files.py`, whose `Skill` annotation (`_skill_sources.py:33`, TYPE_CHECKING, counted per D0-8) reaches `artifacts` and yaml | — | probes of 5.3.4 |
| N7 | `cli` stays a layer (module becomes package) | — | rename `cli -> commands._init_adapters` to `cli.parser -> commands._init_adapters` (the importer is now `cli/parser.py`) | `test_package_inits.py` gains the permanent exception `coding_agent_playbook/cli/__init__.py`, limited to `main` and its error mapping (H7) |
| N8 | — | — | `command-independence`: - the three `-> commands.gate_scan` lines; `modules` lists `commands.twins.*` commands; private lines renamed to `commands.twins.*` | `test_command_independence_lists_every_command` walks `commands/` and `commands/twins/`, skipping the shared public helper `commands.twins.policy` |
| N9 | layer `precommit` | — | — | the metrics-gate prefix probe gains `precommit` |
| N10 | — | — | — | `test_committed_config.py` pins (5.3.5) |
| N11 | — | — | — | — |
| N12 | layer `agent_harness`; drop `harness` | — | engine-layers + `adapters.agent_harness_adapter -> agent_harness.**` and + `adapters._harness_hooks -> agent_harness.**` (`# AH-1 moves both into agent_harness/`) | prefix probe gains `agent_harness` |
| N13 | — | — | private - `commands.check -> adapters._settings_drift` | — |
| N14 | — | — | private - `commands.check_deps -> ..._dependency_tiers`, `-> ..._manifest_diff`, `commands.check_notebooks -> ..._notebook_check`, `guard_config -> ..._notebook_check`, `commands.scan_sinks -> ..._notebook_cells` (names after N8 where it landed first) | budget pin `:673` |
| N15 | layer `artifacts`; drop `gate_scan`, `_gate_scan_files` | + `artifacts.path_classes` | stack - both `-> gate_scan` lines; grading - `evaluators.paths -> gate_scan`, - `evaluators.types -> hook_runtime.**` (or N22, whichever lands first); private - the four `-> handlers._eval_paths` lines and `gate_scan -> hook_runtime._git_parse` (now inside `hook_runtime`) | `_GATE_SCAN`, `_GATE_SCAN_FILES` |
| N16 | — | — | private - `_guard_config_secrets -> hook_runtime._config_keys`, - `hook_policy.handler_catalog -> hook_runtime._config_keys` | budget pins `:214`, `:262` |
| N17 | — | — | private - `guard_config -> hook_runtime._shell_wrappers` | — |
| N18 | — | — | private - the three twin lines `-> hook_runtime._git_parse` | `_GIT_MODULE` -> `git.safe_git` |
| N19, N20 | — | — | stack lines renamed if a deferred importer moved | `security/audit.py` pins (5.3.5) |
| N21 | — | — | private - `hook_runtime.dispatch -> hook_runtime.harness._payload` | `_INITS_WITH_CODE` - `hook_runtime/harness/__init__.py` |
| N22 | layer `metrics_gate`; drop `metrics_config` | — | grading - `evaluators.metrics_gate -> config`, - `evaluators.types -> metrics_config`; private - `_metrics_pass -> evaluators._metrics_inputs`, - `coverage_diff_gate -> evaluators._metrics_suite`; private `evaluators.types -> ..._eval_paths` renamed `metrics_gate.config -> ...` if N15 has not landed; stack: each deferred line into `evaluators.**` whose importer now reaches `metrics_gate` gains a `-> metrics_gate.**` twin | `_METRICS_GATE` |
| N23 | drop `git_env` | — | — | `_INITS_WITH_CODE` - `evals/__init__.py` |
| N24 | — | — | — | — |
| N25 | layer `grading`; drop `evaluators` | — | every `evaluators` string -> `grading` | `grading-kernel.source_modules` and the test parameter `("grading-kernel", "grading")`; `_INITS_WITH_CODE` - the four `evaluators/` inits |
| B6 | — | — | + a new forbidden contract `twins-use-judges`: `coding_agent_playbook.commands.twins` must not import `coding_agent_playbook.hook_runtime.handlers` directly (`allow_indirect_imports = "true"`; no exception after N14) | — |
| T0.3 | — | — | — | `_DEFERRED_UNTIL_CHAIN_MERGES` emptied |
| A1 | drop `_hook_frontmatter`, `_hook_schema`, `_member_reference` | — | — | allowance -> `artifacts.hook_schema`, `artifacts.hook_frontmatter`, `artifacts.member_reference` |
| A2 | drop `types` | — | stack: `eval_task_authoring_lint -> types` -> `-> artifacts.**` | allowance -> the `artifacts` modules `types.py` split into |
| A3 | layer `skills`; drop `skill_document`, `skill_membership` | — | private - the six `-> adapters._agent_skill_rules` lines; engine-layers + `skills.membership -> adapters.base` (`# SK-1`, TYPE_CHECKING) | — |
| A4 | layer `validation`; drop `links` | — | independence - `commands.sync -> commands.validate`; private lines renamed `commands._validate_*` -> `validation._*`, `commands.validate` -> `validation.checks` (and #52's `_validate_skills -> hook_policy._findings`) | prefix probe gains `validation` |
| A5 | drop `orchestrator` | — | engine-layers + `catalog.resolve -> hook_policy.**` (`hooks.**` after A17) if visible, kept (catalog-layers not scheduled) | monkeypatch target (5.3.6) |
| A6 | layer `sync`; drop `git_client` | — | independence - `commands.init -> commands.sync`; private lines renamed `commands.sync`, `commands._sync_*` -> `sync.*` | prefix probe gains `sync` |
| A7 | — | — (the dotted leaves of N6 keep `generated_output.source_files` and `write_guard` out of `STDLIB_LEAVES`; the regenerated `FORBIDDEN` lists gain both, and `stdlib-leaves` stays green) | private - `... -> adapters._owned_files` (2), - `... -> adapters._skill_sources` (2), - `... -> adapters._skill_files` | — |
| A8 | — | — | — | — |
| A9 | — | — | private - `... -> adapters._skill_writer` (3), - `... -> adapters._prior_output` | — |
| A10, A11 | — | — | stack lines renamed (`hook_runtime.deps` -> `hook_runtime.dispatch.deps`) | budget pin `:168` |
| A12 | — | + `artifacts.path_globs` | grading - `grading.paths -> hook_runtime.**` | SPEC.md:201 wording |
| A13 | — | — | — | — |
| A14-A16 | — | — | stack lines renamed to the pack paths; private - `_guard_config_quality`/`_guard_config_ruff` (or their `hooks.guard_config._tables_*` names) `-> hook_runtime._ruff` (A16) | budget pins (5.3.3) |
| A17 | layer `hooks`; drop `hook_policy` | — | private - `validation._hooks -> hook_policy._findings` and #52's line; engine-layers `catalog.resolve -> hooks.**` (renamed or added, kept) | `_INITS_WITH_CODE` - `hook_policy/__init__.py` |
| A18 | drop `hook_registrations` | — | — | `_INITS_WITH_CODE` - `hook_registrations/__init__.py` |
| RS-1 | layer `rendering`; drop `renderer`, `rule_registry`, `prompt_rule_delivery` | — | — | — |
| AH-1 | — | — | engine-layers - the two N12 lines | — |
| GC-1 | — | — | private - `guard_config -> handlers._control_plane_paths`, `-> handlers._control_plane_text` | — |
| GC-2 | drop `guard_config` and the ten `_guard_config_*` names | — | private + `sync._hook_outputs -> hooks.guard_config._tables_{precommit,quality,ruff,toolchain,verify}` (`# GC-3`) | budget pin `:576` deleted |
| GC-3 | — | — | private - the five GC-2 lines | — |
| CF-2 | drop `_typing` | — | engine-layers - `_typing -> evals.task` | `pyproject.toml:219` |
| SK-1 | — | — | engine-layers - `skills.membership -> adapters.base` | — |
| CP-3 | — | — | private - `cli -> commands._init_adapters` | — |

### 6.3 Every contract violation found, and the PR that fixes it

The area mappers found the edges below (file:line at the baseline). "Baseline" says whether T0.2's `ignore_imports` lists the edge on day one; edges between modules that sit outside every layer today become visible only when a move puts both ends in layers, and the PR that makes them visible adds the line (R1).

#### 6.3.1 Layer direction (`engine-layers`, `hook-runtime-stack`, `grading-kernel`)

| Edge | Evidence | Baseline | Fixed by |
| --- | --- | --- | --- |
| `_typing -> evals.task` | `_typing.py:23` (TYPE_CHECKING) | yes | CF-2 deletes `_typing.py` |
| catalog's artifact source -> `evals.loader`, `evals.task` | `sources/filesystem.py:21-24, :34`; `ArtifactSource.list_eval_tasks`, `sources/base.py:74` | yes (`sources.filesystem -> evals.**`) | kept: catalog-layers (the catalog lists eval-task directories, `evals.loader` builds tasks) is not scheduled (L12). N3 renames the line |
| `catalog.resolve -> hooks` (OverlayResolver defaults `merge_hook_layers`, `NO_HANDLER_SCHEMAS`) | `orchestrator.py:37-42, 97-101` | no; added by A5 or A17 | kept (catalog-layers not scheduled); the follow-up would inject the merger from callers |
| `rendering.rule_registry -> ` sync context (`template_source`) | `rule_registry.py:19` | no (both ends outside layers) | A5 moves `template_source` and `artifact_id_of` to `artifacts/identity.py` before RS-1 (H11) |
| `skills.membership -> adapters.base` (TYPE_CHECKING `Adapter`) | `skill_membership.py:24`, used at `:94, :128` | no; added by A3 | SK-1 (a local Protocol with `name` and `delivers_member_rules`) |
| `hooks -> adapters`: registrations' `LAUNCHER_TOKEN` | `hook_registrations/claude.py:15` (from `adapters/claude_settings.py`, defined at `adapters/_settings_plan.py:43`) | no | A18 moves `LAUNCHER_TOKEN` and `LAUNCHER_PATH` to the stdlib leaf `hooks/registrations/launcher.py` (H15) |
| `hooks -> adapters`: the protected set and script copies | `_guard_config_protect.py:36` (`CLAUDE_CODE_COMPOSITES`), `:43` (TYPE_CHECKING `Adapter`), `:178` (private `adapter._output_directories()`); `guard_config.py:92` (`adapters._skill_sources`) | no | GC-2 moves the protected-set assembly to `sync/_protect.py` and `copy_hook_scripts` to `sync/_hook_scripts.py` (H10); A7 makes `copyable_skill_files` public in `generated_output/source_files.py` |
| `adapters -> agent_harness` | `agent_harness_adapter.py:49`, `_harness_hooks.py:22` (after N12) | no; added by N12 | AH-1 moves both modules into `agent_harness/` |
| `adapters._skill_writer -> harness.emitter.with_sentinel_body` | `_skill_writer.py:82` | no | N12 points it at `renderer.with_sentinel_body` (the same object); RS-1 deletes the emitter's re-export |
| `hooks.guard_config._tables_quality -> metrics_gate.config` | `_guard_config_quality.py:74, :98` | no | legal: `metrics_gate` sits below `hooks` (H5) |
| grading kernel -> `metrics_config` (`ruff_config_flags`) | `evaluators/types.py:322` (lazy, inside `MetricConfig.ruff_settings`) | yes | N22 moves `MetricConfig` into `metrics_gate/config.py` (H9) |
| grading kernel -> `config` | `evaluators/metrics_gate.py:44` | yes | N22 (the gate leaves the kernel) |
| grading kernel -> `gate_scan.TEST_PATH_GLOBS` | `evaluators/paths.py:26` | yes | N15 (`artifacts/path_classes.py`) |
| grading kernel -> `hook_runtime.globs` | `evaluators/paths.py:27, :33` | yes | A12 (`artifacts/path_globs.py`, after #62 because #58's skill-nudge imports `globs`) |
| grading kernel -> `hook_runtime.handlers._eval_paths.FIXTURE_GLOBS` | `evaluators/types.py:19`, `evaluators/paths.py:28` | yes | N15 (or N22 for `types.py`, whichever lands first) |
| the twin-shared judges would make `security -> hook_runtime` | `_dependency_tiers.py:20-28`, `_install_cmds.py:30-40`, `_egress.py:25-37`, `destructive.py:27-51`, `gate_scan.py:43-46` import `hook_runtime.shell`, `gitargv`, `_git_options`, `caps`, `decision`, `_git_parse`, `globs` | n/a (design) | N14 and N15 put them in `hook_runtime/judges/`, not `security/` (H3, question 1, resolved 2026-10-18) |
| `hook_runtime -> evals` | `handlers/eval_task_authoring_lint.py:46` (TYPE_CHECKING), `:114`, `:138` | yes (deferred branch) | permanent: a branch-local import pinned by `test_import_budget.py:445-466`; removing it would take a subprocess or an evals split |
| `hook_runtime -> grading`, `metrics_gate` | `stop/suite.py:32` and `handlers/_coverage_report.py:28-29` (module top), `deps.py:27` (TYPE_CHECKING), `_metrics_pass.py`, `coverage_diff_gate.py`, `quality_metrics.py`, `docstring_nonregression.py` (lazy) | yes (deferred branches) | permanent and renamed by N22, N25, A14-A16. `stop/suite.py:32`'s module-top import contradicts the review's "Stop stages import metrics_gate lazily"; it is not changed (the separate hook_runtime review is dropped, L12) |
| `hook_runtime -> catalog`, `detector`, `sources`, `types`, `gate_scan` | `protected.py:242`; `resync_on_detector_input_change.py:52,126,141`; `eval_task_authoring_lint.py:51,167`; `gate_weakening.py:80,120,168`, `gate_weakening_edit.py:104` | `catalog` is a leaf; the rest are deferred lines | renamed by N3, N4, A2; the `gate_scan` lines die in N15 |

#### 6.3.2 Underscore modules (`private-modules`)

| Edge | Evidence | Fixed by |
| --- | --- | --- |
| twins -> `handlers._dependency_tiers`, `_manifest_diff` | `commands/check_deps.py:31, :38, :49` | N14 |
| twin and writer -> `handlers._notebook_check` | `commands/check_notebooks.py:24`, `guard_config.py:107` | N14 |
| twin -> `handlers._notebook_cells` | `commands/scan_sinks.py:32` | N14 |
| twins and the gate judge -> `hook_runtime._git_parse` | `commands/_secret_scope.py:24`, `check_notebooks.py:67`, `scan_sinks.py:151`, `gate_scan.py:43` | N18 (the gate judge's line dies in N15) |
| grading, gate judge and writer -> `handlers._eval_paths` | `evaluators/types.py:19`, `evaluators/paths.py:28`, `gate_scan.py:46`, `guard_config.py:106` | N15 |
| writer -> `hook_runtime._shell_wrappers` | `guard_config.py:100` | N17 |
| writer and handler catalog -> `hook_runtime._config_keys` | `_guard_config_secrets.py:22`, `hook_policy/handler_catalog.py:33` | N16 |
| writer -> `handlers._control_plane_paths`, `_control_plane_text` | `guard_config.py:102, :103` | GC-1 |
| sync-time ruff readers -> `hook_runtime._ruff` | `_guard_config_quality.py:21`, `_guard_config_ruff.py:30` | A16 (`hook_runtime/ruff.py`, public) |
| dispatcher -> `harness._payload` | `hook_runtime/dispatch.py:246` | N21 |
| Stop handlers -> `evaluators._metrics_inputs`, `_metrics_suite` | `handlers/_metrics_pass.py:440`, `handlers/coverage_diff_gate.py:47` | N22 (`metrics_gate/inputs.py`, `suite.py`) |
| `cli -> commands._init_adapters` | `cli.py:37` (`ADAPTERS_FLAG_HELP`) | CP-3 (init's `configure` owns `--adapters`) |
| `commands.check -> adapters._settings_drift` | `check.py:22` | N13 |
| commands and skills -> `adapters._agent_skill_rules` | `_sync_lockfile.py:32`, `_sync_render.py:29`, `_validate_skills.py:31`, `_validation.py:17`, `skill_document.py:23`, `skill_membership.py:18` | A3 (`skills/naming.py`) |
| sync -> `adapters._owned_files` | `sync.py:65`, `_sync_hooks.py:44` | A7 |
| sync -> `adapters._prior_output` | `sync.py:66` | A9 (`adapters/skill_dirs/ownership.py`) |
| sync and validation -> `adapters._skill_writer` | `sync.py:67`, `_sync_output.py:31`, `validate.py:57` | A9 (`adapters/skill_dirs/writer.py`) |
| validation and writer -> `adapters._skill_sources` | `validate.py:56`, `guard_config.py:92` | A7 |
| import helpers -> `adapters._skill_files` | `commands/_import_files.py:14` | A7 |
| validation -> `hook_policy._findings` | `commands/_validate_hooks.py:39`; #52 adds `commands/_validate_skills.py -> _findings.did_you_mean` (spec:3171) | A17 (`hooks/contract/findings.py`); #52 adds its own line if T0.2 has merged |
| sync -> `hooks.guard_config._tables_*` (after GC-2) | `commands/_sync_hooks.py:37-42` (`_guard_config_quality`, `_ruff`, `_toolchain`), `_sync_hook_local.py:38` (`_ruff`) | GC-2 makes the ruff probe public (`ruff_probe.py`); GC-3 removes the reader imports |
| agent_harness -> `adapters._skill_sources` (after AH-1) | `agent_harness_adapter.py:47`, `_harness_hooks.py:21` | AH-1 waits for A7 |
| root-level underscore modules imported from subpackages | `_sentinel` (13 src importers), `_output_io` (13), `_symlinks` (8), `_file_identity` (5), `_atomic_io` (4), `_pep503` (7), `_pyproject_deps` (4), `_canonical_json` (3), `_layers` (4), `_hook_schema` (12), `_member_reference` (6), `_typing` (6), `_toml` (4) | not violations: a root-level underscore module is engine-private (0.6.2); each move makes it public or package-private (R3) |

#### 6.3.3 Command independence (`command-independence`)

| Edge | Evidence | Fixed by |
| --- | --- | --- |
| twins use the `gate-scan` command as a library | `_secret_scope.py:23`, `scan_sinks.py:30`, `check_commit_trailers.py:91` (lazy) -> `commands.gate_scan.resolve_range` | N8 (`commands/twins/_git_scope.py`) |
| `sync` runs the `validate` command | `sync.py:91-92` | A4 (sync imports `validation.checks`, `validation.findings`) |
| `init` runs the `sync` command | `init.py:25` (`execute`, called at `:582`) | A6 (`sync.pipeline.execute`) |
| `init`, `check`, `validate` share `_sync_preflight`; `init`, `check` share `_committed_config`; `init` uses `_precommit_merge`; `render` uses `_sync_render` | `init.py:24, :26, :39`; `check.py:23`; `validate.py:58`; `render.py:20` | not contract violations (helpers are not listed commands); they leave `commands/` in A4 (`validation.preflight`), N10 (`config.committed`), N9 (`precommit`), A6 (`sync.render`) |
| `init` reads the twin policy | `init.py:448, :461` (lazy) -> `_twin_policy`, `_ci_policy` | not a violation after N8: `commands.twins.policy` is a shared helper, not a listed command |

#### 6.3.4 L2 shims (re-exports removed by the move that touches the module)

| Re-export | Removed by |
| --- | --- |
| `config.py:26-34` (`ConfigError`, `check_*`, `HooksConfig`, `GuardrailsConfig`, `parse_hooks_config`, `parse_guardrails_config`, `parse_metrics_config`) | N2 (importers named by defining module; `parse_metrics_config` then lives in `metrics_config.py` until N22) |
| `sources/filesystem.py:16-17` (`ENGINE_PACKAGE`, `REPO_LOCAL_SOURCE`) | N3 |
| `lockfile.py` `drift_entries` (docstring `:17-21`), `adapters/_settings_plan.py:17` (`canonical_json`) | N5 |
| `renderer.py:21-23` (`SENTINEL`, 13 test importers) | N6 |
| `evals/runner.py:44-45` (`PromptResolutionError as PromptResolutionError`, `render_prompt as render_prompt`; no importer uses them, the module does) | N23 (plain imports) |
| `harness/emitter.py:26-30` (`with_sentinel_body`), `commands/_validation.py:22` (`RULE_CALL_RE`) | RS-1 |
| `types.py:27`, `:30-39` (`HookFrontmatter` and nine `_hook_schema` names) and the `as` re-exports in `_hook_frontmatter.py:22-26` | A1 (and A2 for what is left in `types.py`) |
| `adapters/_skill_writer.py:78-79` (`_agent_skill_rules` names) | A3 |
| package facades: `evals/__init__.py` (N23), `evaluators/__init__.py`, `checks/`, `builtins/`, `execution/` inits (N25), `hook_runtime/harness/__init__.py` (N21), `hook_policy/__init__.py` (A17), `hook_registrations/__init__.py` (A18) | as listed |

### 6.4 End state

After the last PR of section 7:

- `engine-layers` has no parenthesised layer and `exhaustive_ignores = ["hook_runtime"]`; its `ignore_imports` holds `catalog.source -> evals.**` and `catalog.resolve -> hooks.**`, both kept because catalog-layers is not scheduled.
- `hook-runtime-stack` keeps its deferred-branch lines (into `grading`, `metrics_gate`, `evals`, `catalog`, `config`, `detector`, `artifacts`), each matched by a branch-local allowance in the budget probes. `grading-kernel`, `command-independence`, `private-modules` and `twins-use-judges` have empty ignore lists.
- `STDLIB_LEAVES` = `artifacts.path_classes`, `artifacts.path_globs`, `catalog.roots`, `detector.pep503`, `detector.pyproject_deps`, `generated_output.atomic_io`, `generated_output.sentinel`, `lockfile`, `security`.
- `_INITS_WITH_CODE` and `_DEFERRED_UNTIL_CHAIN_MERGES` are empty; the permanent `__init__` exceptions are the root and `cli/`.
- `tests/architecture/move_map/` holds one file per move PR, and MIGRATION.md's "Module paths" section lists every public path that moved.

## 7. The PR plan

### 7.1 Rules for every PR

#### 7.1.1 The gate

Run in a fresh virtual environment per Python version (3.12 and 3.13), from the repository root, cache-free:

```bash
python -m pip install -e ".[dev]"   # again after any change to pyproject.toml entry points or dependencies
ruff check --no-cache .
ruff format --check --no-cache .
mypy --cache-dir=/dev/null
pytest -q -p no:cacheprovider
```

No path arguments and no optional extras (`radon` stays uninstalled). A PR that changes what sync, `playbook render` or the hook runtime writes is not a move; a move PR that touches those code paths (N2, N3, N6, N13, A4-A9, A17, A18, RS-1, GC-2, AH-1) also runs the parity check of section 9 (AC.1.3): `playbook sync --check` with the PR's code exits 0 on a probe repository synced with the base commit's code, run in the scratchpad with `--non-interactive`, `</dev/null` and `timeout 180`.

#### 7.1.2 Acceptance criteria shared by every move PR

1. `git diff -M --stat origin/main...HEAD` shows renames (the moved bodies are byte-identical apart from import lines, dotted strings, docstring paths and the location-preserving edits of rule 11) plus import, string and doc edits. No test assertion changes except module names, paths and the probe lists of 5.3.4.
2. The PR's entries are in its own `tests/architecture/move_map/<pr>.toml`; `python -m tests.architecture.module_moves check` prints no stale reference, and every `review:` line it prints has been read.
3. The contract edits of 6.2 for this PR are made and `tests/architecture/` passes. No ignore line is added except under R1 (0.7.2), with a comment naming the PR that removes it.
4. New packages have a docstring-only `__init__.py` (L5); new test directories have an empty `__init__.py`.
5. No re-export at an old path and no new re-export anywhere (L2).
6. The import-budget tests pass with the same number of cases; the pins of 5.3.3 that name a moved module are renamed.
7. The living docs are rewritten by the script; the SPEC §5.1 tree and `_ENGINE_PATHS` are edited by hand where 5.3.5 lists the PR.
8. No moved module grows; a split leaves every new module at 500 lines or fewer.
9. The gate of 7.1.1 passes on 3.12 and 3.13.
10. The PR body states the move map, every soft overlap with an open chain ticket (file and line), and which chain tickets must re-run `apply` after it merges.
11. **Location-preserving edits.** A moved file that finds other files relative to its own location keeps finding the same files: its `Path(__file__)` depth is adjusted by the number of levels it moved (`.parent` -> `.parents[1]`, `parents[k]` -> `parents[k+1]`), with a WHY comment naming the move. This is the one code edit a move-only PR may make besides imports and strings. `rg "__file__" <moved files>` is part of the PR check, and the PR lists each adjusted line. Known cases: `catalog.py:42` `_PACKAGE_DIR` (N3; 7.4 N3) and the test files of N12, N20, N21 and A13 (5.2.2).
12. **A package replaces its same-name module in one PR.** A PR that creates the package `x/` removes or moves `x.py` in the same PR: a regular package directory shadows a same-name module, so `from <parent>.x import <name>` raises ImportError once both exist (A10 moves `hook_runtime/dispatch.py` for this reason).

#### 7.1.3 Working beside the chain

- **Timed merges.** A move with soft overlaps (marked "timed" below) merges right after a chain ticket merges and before the next one is opened for review. It never merges while a chain PR is in review.
- **Replay.** After a move merges, the loop adds one line to the next open chain ticket: the move's id, the files it moved, and "rebase, take your side of import conflicts, run `python -m tests.architecture.module_moves apply`".
- **Coordination notes for chain tickets** (added to the issues before they start):
  - #54: `commands/render.py` filters included rules by `applies_if` since B1; keep that filter when passing `skill_references`, and spec §7.3's "stays unfiltered" row is superseded (section 8 B.4.6, section 9 AC.3.8).
  - #52: if T0.2 has merged, the new `commands/_validate_skills.py -> hook_policy._findings` import needs a `private-modules` ignore line commented `# A17: becomes hooks/contract/findings.py`.
  - #58: if T0.2 has merged, the new root module `_guard_config_skills.py` joins `exhaustive_ignores` and the three forbidden lists (the tests print them).
  - #55 and #58: no rebase onto the hook_runtime moves; the serial lane N16-N21 runs after #62 (question 3, 2.3).
- **Rebasing a lane onto another lane.** Parallel move PRs share derived files besides import lines. When a rebase conflicts in one of them, take main's side and re-derive this PR's change, never hand-merge both sides:
  - MIGRATION.md's generated "Module paths" section: take main's side, then `apply` regenerates it from the composed map;
  - `pyproject.toml` `[tool.importlinter]` (`layers`, `exhaustive_ignores`, the three sorted `forbidden_modules` lists, the ignore lines) and `tests/engine_modules.py` `STDLIB_LEAVES`: take main's side, re-apply this PR's row of 6.2, then run `tests/architecture/`; the contract tests print the expected lists;
  - `_ENGINE_PATHS` (`tests/unit/test_docs_lifecycle_hooks_spec.py:99-103`), the SPEC §5.1 tree and the exact-list probes of 5.3.4 (`tests/unit/test_claude_settings.py:524-543`): take main's side and re-apply this PR's lines from 5.3.4-5.3.5;
  - a package `__init__.py` that two PRs create (for example `hook_runtime/judges/__init__.py`, N14 and N15): its docstring text is fixed in this spec, so both sides are identical and git takes either.
  - a re-export facade that two PRs trim (`evaluators/__init__.py`: N22 drops `MetricConfig`, N24 the rubric and gate re-exports): take main's side and delete this PR's names again.
  
  Then `apply`, `check` and the gate. The move map itself never conflicts: each PR writes its own `move_map/<pr>.toml` (5.4.1).
- **No stacked PRs.** Each PR branches from main once its blockers have merged.

### 7.2 Schedule

#### 7.2.1 Lanes that run now, beside the chain

Since question 3 was resolved (package granularity, 2.2 and 2.3), only these PRs run beside the chain: lane 0, N1-N7, N12, N22, B1 and B7. Every N PR waits for lane 0 (T0.0, T0.1, T0.2). Within a lane, PRs merge in order; lanes run in parallel. A PR that lands after a PR of another lane rebases onto it: import lines, and the shared derived files (MIGRATION.md's generated section, `[tool.importlinter]`, `STDLIB_LEAVES`, `_ENGINE_PATHS`, the SPEC §5.1 tree, the exact-list probes), resolved with the recipe of 7.1.3.

```
B1 ───────────────────────────────── any time; must merge before #54 starts
B7 ───────────────────────────────── any time
T0.0 ─┐
T0.1 ─┴─ T0.2 ─┬─ core-a:   N1 ─ N2 ─┬─ N3
               │                     └─ N22
               ├─ core-b:   N4    N5    N6 (timed)
               ├─ cli:      N7
               └─ adapters: N12
```

**Re-check against the package rule** (the touched files of the open tickets #50-#62, as the chain-overlap cells of section 4 record them). No "now" PR moves code out of, or into, a package an open ticket edits, so none of them moved to after #62:

| PR | What it moves | Package check |
| --- | --- | --- |
| N1 | root `_toml.py` | a root module no open ticket edits |
| N2 | root `config.py`, `config_entries.py`, `config_schema.py`, `hooks_config.py`, `_table_shapes.py`, `LinksConfig` of root `links.py`; the state half of `sources/` into the new `config/` | the root modules are not edited by an open ticket; no open ticket edits a file of `sources/` (`sources/filesystem.py` is untouched, chain spec 870-871); its edits in chain files are import lines and the `_ENGINE_PATHS` line (timed) |
| N3 | root `catalog.py`, `_layers.py`; the rest of `sources/` into the new `catalog/` | as N2; `tests/unit/test_sources_filesystem_bundled.py` (chain-edited) keeps its place and gets one import line (timed); `hook_runtime/protected.py:242` gets one import line |
| N4 | root `detector.py`, `_pep503.py`, `_pyproject_deps.py`, `orchestrator.filter_applies_if` into the new `detector/` | root modules no open ticket edits (`orchestrator.py` is not edited by #50-#62); importers in `commands/`, `evals/` and `hook_runtime/` get import lines (timed) |
| N5 | root `lockfile.py`, `_lock_drift.py`, `_canonical_json.py` into the new `lockfile/` | root modules no open ticket edits; it also deletes one re-export line in `adapters/_settings_plan.py:17`, a file no open ticket edits; importers get import lines (timed) |
| N6 | the six root generated-output helpers into the new `generated_output/` | root modules no open ticket edits; `adapters/_owned_files.py` stays for A7; importers in `adapters/`, `commands/` and `renderer.py` get import lines (timed) |
| N7 | root `cli.py` into the new `cli/` | a root module no open ticket edits (its last chain edit landed in #68); the `commands/__init__.py` docstring it rewords is not chain-edited |
| N12 | `harness/` into the new `agent_harness/` | no open ticket edits a file of `harness/`; `adapters/agent_harness_adapter.py` and `_skill_writer.py` get import lines (timed) |
| N22 | `evaluators/metrics_gate.py`, `_metrics_inputs.py`, `_metrics_suite.py`, `measurement_snapshot.py`, `policy.py`, `MetricConfig` of `evaluators/types.py` and root `metrics_config.py` into the new `metrics_gate/` | no open ticket edits a file of `evaluators/` or `metrics_config.py`; the `hook_runtime` handlers and `commands/` modules it touches get import lines, and `tests/unit/test_docs_lifecycle_hooks_spec.py:25` (#50/#53) one import line (timed) |
| B1 | behaviour of `commands/render.py` | edits a chain file on purpose; it must merge before #54 starts (7.1.3) |
| B7 | a test of the destructive guard | test only; edits no chain file |

#### 7.2.2 After the chain (#62 merged)

Every PR here waits for #62 and lane 0. Since question 3 was resolved (2.3) this includes the N PRs whose package the open chain edits (N8-N11, N13-N21, N23-N25) and the B PRs that wait on them (B2, B3, B4a, B4b, B6, B8, B9, B10), with their other blockers unchanged. None of them is timed any more: the chain has merged, so their former soft overlaps are plain rewrites, and each re-reads its rows and anchors on main before it starts (L9). Where a deferred N PR and an A PR move code of the same area, the N PR goes first, as the designs of sections 4 and 9 assume; the listed blockers already enforce that, with one edge added on 2026-10-18: A14 waits for N14 and N15 (the judges leave `handlers/` before the packs split).

```
T0.3
commands:          N8 ─┬─ B6 (after N14) ─ B9 ─ B10 (after N11)
                   N9  │
                   N11 │
judges:            N14 ┘    N15
config:            N10 ─ B2
grading:           N23 ─ N24 ─ N25 (after N22) ─ B8
hook_runtime:      N16 ─ N17 ─ N18 ─ N19 ─ N20 ─ N21 ─ A10 ─ A11 ─ A12 (after N15)
                    └─ B3 ─ B4a (after N14) ─ B4b
artifacts/skills:  A1 ─┬─ A2 ─ CF-2 (after N2, N5)
                       └─ A3 ─ SK-1
validation/sync:   A4 ─┬─ A5 (after A2, N3, N4) ─ RS-1 (after B1, A18) ─ RS-2
                       └─ A6 ─────────────────────────────────────┐
generated_output:  A7 (after N6)                                  │
adapters:          N13 ─ A8      A9                               │
agent_harness:     AH-1 (after N12, A7, B9, RS-1) ─ AH-2 ─ RS-3   │
hook packs:        A13 ─┬─ A14 (after A11, GC-1, N14, N15) ─┬─ A15│
                        │                                   └─ A16│
hooks:                  └─ A17 ─ A18 (after N13) ─ GC-2 (after GC-1, A6) ─ GC-3 (after B2, N22)
guard_config:      GC-1 (after N16, B3) ─ GC-4 (after A17)
cli protocol:      CP-1 (after B9) ─ CP-3 (after CP-2)
init:              CP-2 (after N9, B9, RS-1)
docs:              D1 (after every move)
```

#### 7.2.3 Summary

| Id | Title | Kind | When | Blockers |
| --- | --- | --- | --- | --- |
| T0.0 | `test(layout): add the module-path rewrite script` | tooling | now | — |
| T0.1 | `test(layout): pin engine module names and derive the hot-path forbidden list` | tests | now | — |
| T0.2 | `test(layout): enforce the ADR 0002 import contracts with import-linter` | tests, dev dependency | now | T0.1 |
| T0.3 | `test(layout): pin the module names deferred for the skills chain` | tests | after #62 | #62 |
| N1 | `refactor: rename _toml to toml_writer` | move | now | lane 0 |
| N2 | `refactor(config): move the config modules into a config package` | move | now, timed | N1 |
| N3 | `refactor(catalog): move catalog, layers and the artifact source into a catalog package` | move | now, timed | N2 |
| N4 | `refactor(detector): split detector.py into a detector package` | move | now, timed | lane 0 |
| N5 | `refactor(lockfile): move the lockfile modules into a lockfile package` | move | now, timed | lane 0 |
| N6 | `refactor: move the generated-output helpers into a generated_output package` | move | now, timed | lane 0 |
| N7 | `refactor(cli): turn cli.py into the cli package with a __main__ module` | move | now, timed | lane 0 |
| N8 | `refactor(commands): gather the guard twins in commands/twins/` | move | after #62 | #62, N7 |
| N9 | `refactor(init): move pre-commit config writing to precommit.py` | move | after #62 | #62, N7 |
| N10 | `refactor(config): move committed-config planning into config/committed.py` | move | after #62 | #62, N2 |
| N11 | `refactor(eval): move runner lookup and result formatting out of commands/eval.py` | move | after #62 | #62, lane 0 |
| N12 | `refactor(agent_harness): move harness/ to agent_harness/` | move | now, timed | lane 0 |
| N13 | `refactor(adapters): move the Claude Code settings merge into adapters/claude_code/` | move | after #62 | #62, lane 0 |
| N14 | `refactor(hook_runtime): move the guard-twin judges into hook_runtime/judges/` | move | after #62 | #62, lane 0 |
| N15 | `refactor(hook_runtime): move the gate-weakening judge and the eval path classes` | move | after #62 | #62, lane 0 |
| N16 | `refactor(hook_runtime): group guard_config reading into hook_runtime/config/` | move | after #62 | #62, lane 0 |
| N17 | `refactor(hook_runtime): group the shell parser into hook_runtime/shell/` | move | after #62 | #62, N16 |
| N18 | `refactor(hook_runtime): group SafeGit into hook_runtime/git/` | move | after #62 | #62, N17 |
| N19 | `refactor(hook_runtime): group runtime state into hook_runtime/state/` | move | after #62 | #62, N18 |
| N20 | `refactor(hook_runtime): group doctor, canary and simulate into hook_runtime/diagnostics/` | move | after #62 | #62, N19 |
| N21 | `refactor(hook_runtime): move the harness wire types out of harness/__init__` | move | after #62 | #62, N20 |
| N22 | `refactor(metrics-gate): move the metrics gate into metrics_gate/` | move | now, timed | N2 |
| N23 | `refactor(evals): group the task compiler under evals/compile and the run pipeline under evals/run` | move | after #62 | #62, lane 0 |
| N24 | `refactor(evals): move the eval-only check families and the named gate and rubric registries into evals` | move | after #62 | #62, N23 |
| N25 | `refactor(grading): rename evaluators to grading` | move | after #62 | #62, N22, N24 |
| B1 | `fix(render): omit included rules whose applies_if is false` | behaviour (test first) | now, before #54 | — |
| B2 | `refactor(config): read and write the two config files through ConfigFiles` | behaviour | after #62 | #62, N2, N10 |
| B3 | `refactor(hook-runtime): read guard_config.json pack tables through typed accessors` | behaviour | after #62 | #62, N16 |
| B4a | `refactor(hook-runtime): read handler config through its CONFIG_SCHEMA` | behaviour | after #62 | #62, B3, N14 |
| B4b | `refactor(hook-runtime): every builtin reads its config through HookConfig` | behaviour | after #62 | #62, B4a |
| B6 | `refactor(twins): one run skeleton for the guard twins` | behaviour | after #62 | #62, N8, N14 |
| B7 | `test(hooks): the destructive guard denies every native deny prefix` | tests | now | — |
| B8 | `refactor(grading): one measuring pass for eval tasks and the metrics gate` | behaviour | after #62 | #62, N22, N23, N25 |
| B9 | `refactor(cli): commands declare their own flags` | behaviour | after #62 | #62, N7, B6 |
| B10 | `refactor(cli): eval declares its own flags` | behaviour | after #62 | #62, B9, N11 |
| A1 | `refactor(artifacts): move hook schema, hook frontmatter and member references into artifacts/` | move | after #62 | #62 |
| A2 | `refactor(artifacts): split types.py into artifacts modules` | move | after #62 | A1 |
| A3 | `refactor(skills): move skill composition into a skills package` | move | after #62 | A1 |
| A4 | `refactor(validation): move the validation rule set and preflight into validation/` | move | after #62 | #62 |
| A5 | `refactor: split orchestrator into catalog, artifacts, adapters and validation modules` | move | after #62 | A2, A4, N3, N4 |
| A6 | `refactor(sync): move the sync pipeline out of commands/ into sync/` | move | after #62 | A4 |
| A7 | `refactor: move the generated-output write guard and copyable source files into generated_output/` | move | after #62 | N6 |
| A8 | `refactor(adapters): move the Claude Code adapter into adapters/claude_code/` | move | after #62 | N13 |
| A9 | `refactor(adapters): rename the harness adapters and move the skill writer into adapters/skill_dirs/` | move | after #62 | #62 |
| A10 | `refactor(hook_runtime): move the event and decision model into hook_runtime/dispatch/` | move | after #62 | N21 |
| A11 | `refactor(hook_runtime): move the dispatcher into hook_runtime/dispatch/` | move | after #62 | A10 |
| A12 | `refactor(artifacts): move the path-glob grammar to artifacts/path_globs.py` | move | after #62 | A10, N15 |
| A13 | `test(hook_runtime): move the hook pack tests under tests/hook_runtime/handlers/` | test move | after #62 | #62 |
| A14 | `refactor(hook_runtime): split the safety pack and shared helpers into handlers/safety and handlers/_shared` | move | after #62 | A13, A11, GC-1, N14, N15 |
| A15 | `refactor(hook_runtime): split the verify and audit packs into handlers/verify and handlers/audit` | move | after #62 | A14 |
| A16 | `refactor(hook_runtime): split the protect and feedback packs and make the ruff seam public` | move | after #62 | A14 |
| A17 | `refactor(hooks): move hook_policy into hooks/resolution, hooks/contract and hooks/enforcement` | move | after #62 | A13 |
| A18 | `refactor(hooks): move hook_registrations and the hook shim templates into hooks/registrations` | move | after #62 | A17, N13 |
| RS-1 | `refactor(rendering): move the renderer, rule registry and prompt delivery into rendering/` | move | after #62 | B1, N4, A5, A18 |
| AH-1 | `refactor(agent_harness): move the Agent Harness adapter and importer into agent_harness/` | move | after #62 | N12, A7, B9, RS-1 |
| GC-1 | `refactor(hook_runtime): give the guard_config contract names public homes` | move | after #62 | N16, B3 |
| GC-2 | `refactor(hooks): move the guard_config writer into hooks/guard_config` | move | after #62 | GC-1, A6, A13, A17, A18 |
| CP-2 | `refactor(init): split commands/init.py into _init_answers, _init_config_plan and _init_overlays` | move | after #62 | N9, B9, RS-1 |
| CF-2 | `refactor(types): delete _typing and type the sources with the real classes` | types only | after #62 | A2, N2, N5 |
| SK-1 | `refactor(skills): type undelivered_member_warning with a local protocol` | types only | after #62 | A3 |
| GC-3 | `refactor(hooks): compile_guard_config reads its own repo inputs` | interface | after #62 | GC-2, B2, N22 |
| GC-4 | `refactor(hooks): one typed hook-record shape for guard_config.json` | interface | after #62 | GC-1, A17 |
| RS-2 | `refactor(rendering): one RenderSession renders for sync, playbook render and the eval runner` | interface | after #62 | RS-1 |
| RS-3 | `test(rendering): one FakeRuleRegistry for the adapter tests` | tests | after #62 | RS-1, AH-1 |
| AH-2 | `refactor(agent_harness): import, lint and hook sidecars at the package interface` | interface | after #62 | AH-1 |
| CP-1 | `refactor(cli): sync, validate and render declare their own flags` | interface | after #62 | B9 |
| CP-3 | `refactor(init): init declares its own flags and asks through an injected prompt` | interface | after #62 | CP-2, CP-1 |
| D1 | `docs(readme): refresh the architecture overview for the flat layout` | docs | last | every move |

"Lane 0" means T0.0, T0.1 and T0.2; every "after #62" PR also waits for lane 0. The When column follows question 3 (resolved 2026-10-18, 2.3): only lane 0, N1-N7, N12, N22, B1 and B7 run now. Ids that were folded: the designer's B5 is N14; the root mapper's M8 is N15 and its A5 is GC-2; the adapters mapper's M-AH2 and the commands mapper's AFTER-3 are AH-1 (H21, table 11.2).

### 7.3 Lane 0

Lane 0 changes no file under `src/`. Its full design is section 6.1.

#### T0.0 `test(layout): add the module-path rewrite script`

- **When:** now; no blocker; runs beside T0.1.
- **Scope:** section 5.4: `tests/architecture/__init__.py` (empty, shared with T0.1), `module_moves.py`, the empty `move_map/` directory (one `.gitkeep`), `test_module_moves.py`; the `<!-- module-moves: keep -->` markers around the MIGRATION.md record rows and the SPEC.md history ranges listed in 5.3.8.
- **Tests:** the list of 5.4.4.
- **Acceptance:** every test of 5.4.4 passes; `apply` on the unchanged tree changes nothing; `check` on the tree prints nothing (empty map); the module imports only the stdlib; the gate (7.1.1) passes.
- **Size:** about 450 lines of code and 300 of tests; one context.

#### T0.1 `test(layout): pin engine module names and derive the hot-path forbidden list`

- **When:** now; no blocker. **Soft overlap:** `tests/hook_runtime/test_import_budget.py` (#58 appends a test; names and signatures are kept, 6.1 0.8).
- **Scope:** section 6.1, 0.5, plus `tests/cli/test_module_entry.py` (6.1 0.5.9).
- **Acceptance:** 6.1 0.10 (T0.1 list) and `test_python_dash_m_cli_prints_help` passes.

#### T0.2 `test(layout): enforce the ADR 0002 import contracts with import-linter`

- **When:** now; after T0.1.
- **Scope:** section 6.1, 0.6, with the harmonised `layers` list and comments.
- **Acceptance:** 6.1 0.10 (T0.2 list).

#### T0.3 `test(layout): pin the module names deferred for the skills chain`

- **When:** after #62.
- **Scope and acceptance:** 6.1 0.10 (T0.3 list).

### 7.4 Moves N1-N25 (N1-N7, N12 and N22 now; the rest after #62)

Every entry adds to the shared criteria of 7.1.2. "Rows" are the rows of section 4 whose PR column names the PR; "tests" are its bullets in 5.2; "contracts" its row in 6.2. A **timed** PR has soft overlaps with open chain tickets and follows 7.1.3. An entry marked **after #62** moves code out of, or into, a package the open chain edits, so it waits for #62 and lane 0 (L1 per package, question 3, 2.3); it is not timed, and it re-reads its rows and anchors on main before it starts (the chain moved them, L9).

#### N1 `refactor: rename _toml to toml_writer`

- **When:** now; first among the moves (the pilot of the rewrite script). **Blockers:** lane 0.
- **Files:** `_toml.py` -> `toml_writer.py`; 4 source importers (`config_schema.py`, `harness/manifest.py`, `metrics_config.py`, `sources/filesystem.py`) and 5 test importers; the docstring references at `_toml.py:7, :30, :282, :291` (reworded where they name `sources/filesystem.py`); the SPEC mention.
- **Tests:** `tests/unit/test_toml.py` -> `tests/unit/test_toml_writer.py`.
- **Contracts:** layer `toml_writer`; the eval-task allowance names `toml_writer`.
- **Acceptance:** MIGRATION.md has the generated "Module paths" section with one row; the script's output on this PR is what the reviewer reads first.
- **Size:** about 15 files.

#### N2 `refactor(config): move the config modules into a config package`

- **When:** now, timed (13 chain-edited importers of `hooks_config.py`, the `_ENGINE_PATHS` line). **Blockers:** N1 (`config_schema.py` imports `_toml`).
- **Rows:** `config.py` -> `config/model.py`; `config_entries.py` -> `config/entries.py`; `config_schema.py` -> `config/schema.py`; `hooks_config.py` -> `config/tables/hooks.py`; `_table_shapes.py` -> `config/tables/_table_shapes.py`; `LinksConfig` (`links.py:41-62`) and `parse_links_config` (`config.py:237-255`) -> `config/tables/links.py` (removes the lazy config -> links import, `config.py:39, :250`); `StateSource` (`sources/base.py:77-135`) and `FileSystemStateSource` with its helpers (`sources/filesystem.py:40-60, 162-218, 387-550`) -> `config/files.py`.
- **Also:** `pyproject.toml:73` value (re-install); the `config.py:26-34` re-exports are removed and their importers named by defining module (`ConfigError` from `config.schema`; `HooksConfig`, `GuardrailsConfig`, `parse_hooks_config`, `parse_guardrails_config` from `config.tables.hooks`; `parse_metrics_config` from `metrics_config`, which keeps it until N22). `config/__init__.py` and `config/tables/__init__.py` stay docstring-only: `hook_policy` and `catalog/source.py` import the hooks table on a light path.
- **Tests and pins:** 5.2 N2; `_ENGINE_PATHS` `hooks_config.py` with the SPEC §5.1 tree; the `test_hooks_config.py:377-385` probe; `test_committed_config.py` `_WRITERS_HOME` -> `config/files.py`.
- **Contracts:** drop four names from `exhaustive_ignores`; the eval-task allowance shrinks.
- **CONTEXT.md:** adds the term **Consumer config**: "the committed config file and the machine-local overrides file in a consumer repo that steer sync and the hooks" (question 4; the entry names no paths).
- **Size:** about 1,600 moved lines, about 70 importer files (26 in `src`); one context with the script.

#### N3 `refactor(catalog): move catalog, layers and the artifact source into a catalog package`

- **When:** now, timed (16 chain-edited importers; `tests/unit/test_sources_filesystem_bundled.py`, edited by #50-#53/#56, stays at `tests/unit/` with its import line rewritten, a soft overlap, and moves in A4). **Blockers:** N2 (both split `sources/filesystem.py` and `sources/base.py`).
- **Rows:** `catalog.py` -> `catalog/roots.py`; `_layers.py` -> `catalog/layers.py`; `ArtifactSource` (`sources/base.py:30-76`) and `FileSystemArtifactSource` with its helpers (`sources/filesystem.py:62-160, 220-385`) -> `catalog/source.py` (about 420 lines); `sources/_hook_walk.py` -> `catalog/_hook_walk.py`; `sources/` deleted.
- **Also:** `pyproject.toml:70` value (re-install); the `ENGINE_PACKAGE`/`REPO_LOCAL_SOURCE` re-export at `sources/filesystem.py:16-17` is removed. `catalog/__init__.py` stays docstring-only: `hook_runtime/protected.py:242` imports `catalog.roots` lazily on the protected-edit branch.
- **Location-preserving edit (7.1.2 rule 11):** `catalog.py` finds the catalog relative to its own file (`_PACKAGE_DIR: Path = Path(__file__).resolve().parent`, `catalog.py:42`; `catalog_root()` looks for `package / _catalog` and, in a checkout, requires `package.parent.name == "src"`, `:86-91`). After a byte-identical move to `catalog/roots.py`, `_PACKAGE_DIR` would be `src/coding_agent_playbook/catalog/`, and `catalog_root()` would raise `CatalogMissingError` in a checkout and in the wheel, breaking sync, validate, render and the protected-edit hook branch. N3 changes the one line to `_PACKAGE_DIR: Path = Path(__file__).resolve().parents[1]` with a WHY comment ("the module moved one level down into catalog/; the package directory is its parent's parent"). It is the only `__file__`-relative path in `src/` (grep). New regression test `tests/catalog/test_roots.py::test_catalog_root_finds_the_checkout_catalog_unpatched`: `catalog_root()` with no `package_dir` and no monkeypatch returns `<repo>/catalog` in the checkout.
- **Tests and pins:** 5.2 N3; budget pins `:454`, `:461-463`; the `test_hook_policy_tables.py:195-207` probe (`_layers`); SPEC §5.1 and §20.
- **Contracts:** `STDLIB_LEAVES` `catalog` -> `catalog.roots`; the `catalog.source -> evals.**` line (kept).
- **Size:** about 850 moved lines, about 60 importer files.

#### N4 `refactor(detector): split detector.py into a detector package`

- **When:** now, timed (5 chain-edited importers: `commands/render.py`, `validate.py`, `evals/prompting.py`, `rule_registry.py`, `hook_policy/effective.py`; the `_ENGINE_PATHS` line). **Blockers:** lane 0.
- **Rows:** `detector.py` -> `detector/facts.py` (lines 1-308: `Facts`, `KNOWN_*`, `detect`) and `detector/predicate.py` (304-454: `evaluate_predicate` and helpers); `_pep503.py` -> `detector/pep503.py`; `_pyproject_deps.py` -> `detector/pyproject_deps.py`; `orchestrator.filter_applies_if` (`orchestrator.py:251-269`) -> `detector/predicate.py`.
- **Also:** `from coding_agent_playbook import detector` (`resync_on_detector_input_change.py:126, :141`) becomes `from coding_agent_playbook.detector import facts as detector`. `detector/__init__.py` stays docstring-only: `pep503` loads at module level on the Bash `pre_tool_use` hot path (`handlers/dependencies.py`, `_install_cmds.py`, `_dependency_tiers.py`), and `packaging` stays forbidden there.
- **Tests and pins:** 5.2 N4; budget pins `:439, :441`; `_ENGINE_PATHS` `_pep503.py`; the import in `tests/unit/test_docs_migration_hooks.py`; SPEC §5.1.
- **Contracts:** `STDLIB_LEAVES` `_pep503`, `_pyproject_deps` -> `detector.pep503`, `detector.pyproject_deps`, so the derived `FORBIDDEN` lists `detector.facts` and `detector.predicate`; the stack line `-> detector.facts`.
- **Not in scope:** dropping the redundant empty-predicate guards outside `validate.py` (catalog-layers, not scheduled).
- **Size:** about 780 moved lines, about 40 importer files.

#### N5 `refactor(lockfile): move the lockfile modules into a lockfile package`

- **When:** now, timed (15 chain-edited importers). **Blockers:** lane 0.
- **Rows:** `lockfile.py` -> `lockfile/model.py`; `_lock_drift.py` -> `lockfile/drift.py`; `_canonical_json.py` -> `lockfile/canonical_json.py`.
- **Also:** the `drift_entries` re-export (docstring `lockfile.py:17-21`) and the `canonical_json` re-export at `adapters/_settings_plan.py:17` are removed. The package stays free of jinja and yaml (three `hook_runtime` importers). `FileSystemStateSource` keeps the lockfile load and save.
- **Tests and pins:** 5.2 N5; `_LOCKFILE_MODULE` -> `lockfile.model`; the probes `test_claude_settings.py:526-544`, `test_canonical_json.py:46-50`, `test_runtime_config.py:499-502`; SPEC.
- **Contracts:** drop `_lock_drift` and `_canonical_json` from `exhaustive_ignores` and from `STDLIB_LEAVES`.
- **Size:** about 660 moved lines, about 50 importer files.

#### N6 `refactor: move the generated-output helpers into a generated_output package`

- **When:** now, timed (8 chain-edited adapter and command importers; `renderer.py`, #54). Merge right after a chain ticket merges. **Blockers:** lane 0.
- **Rows:** `_sentinel.py`, `_file_identity.py`, `_atomic_io.py`, `_output_io.py`, `_symlinks.py`, `gitignore.py` -> `generated_output/{sentinel,file_identity,atomic_io,output_io,symlinks,gitignore}.py`.
- **Also:** the test-only `SENTINEL` re-export at `renderer.py:21-23` is removed (13 test importers name `generated_output.sentinel`). `adapters/_owned_files.py` waits for A7 (H1).
- **Tests and pins:** 5.2 N6; `_ENGINE_PATHS` `_sentinel.py`; the probes `test_sentinel.py:53-66` and `test_claude_settings.py`; the `test_import_budget.py:37` import; SPEC §5.1 (5 entries).
- **Contracts:** layer `generated_output`; `STDLIB_LEAVES` per 6.2.
- **Size:** about 890 moved lines, about 75 importer files.

#### N7 `refactor(cli): turn cli.py into the cli package with a __main__ module`

- **When:** now, timed (import lines in `tests/unit/test_docs_lifecycle_hooks_cli.py`, #56, and `test_docs_readme_hooks.py`, #53/#58); it lands before N8 and N9 (after #62), which edit the cli import block. **Blockers:** lane 0 (T0.1's `-m` pin must already be on main).
- **Files:** `git mv cli.py cli/parser.py` (the subcommand imports, `_SUBCOMMANDS`, `build_parser` and the `_add_*_parser` helpers, `cli.py:1-422`, keep their bodies); `main`, its error-to-exit-2 mapping and `_missing_catalog_line` (`cli.py:424-478`) move verbatim to a new `cli/__init__.py`, which imports `build_parser` from `coding_agent_playbook.cli.parser`; new `cli/__main__.py` holding the `if __name__ == "__main__"` tail moved verbatim from `cli.py:479-480`, importing `main` from `coding_agent_playbook.cli`; `commands/__init__.py`'s docstring reworded (it names `cli.py`); SPEC.md:163, :283, :303. A `[[names]]` entry (`coding_agent_playbook.cli` -> `coding_agent_playbook.cli.parser`, names `build_parser`, `_SUBCOMMANDS`) lets the script rewrite the 9 test importers listed in 4.2; `from coding_agent_playbook.cli import main` (17 test files) is unchanged.
- **Tests:** 5.2 N7 (`tests/unit/test_cli.py` -> `tests/cli/test_cli.py`; `test_console_scripts_load_cli_main`).
- **Contracts:** the permanent `cli/__init__.py` exception in `test_package_inits.py`, with a comment citing L2 (H7), plus `test_cli_init_defines_main_only`: the only public top-level name `cli/__init__.py` defines is `main` (private helpers of its error mapping are allowed), so the exception cannot grow into a second parser module.
- **Acceptance:** `python -I -m coding_agent_playbook.cli --help` exits 0 (T0.1's test); `playbook --version` and `coding-agent-playbook --version` print the version; `cli/__init__.py` is under 80 lines.
- **Size:** small (about 480 moved lines, 10 test files with import edits).

#### N8 `refactor(commands): gather the guard twins in commands/twins/`

- **When:** after #62 (package rule: it moves modules out of `commands/`, which the open chain edits); the import blocks of `tests/unit/test_docs_lifecycle_hooks_cli.py` (#56) and `test_docs_readme_hooks.py` (#53/#58) are then plain rewrites. **Blockers:** #62, lane 0, N7.
- **Rows:** section 4.3: `gate_scan.py` (the command), `scan_secrets.py`, `_secret_scope.py`, `scan_sinks.py`, `check_notebooks.py`, `check_commit_trailers.py`, `check_deps.py`, `ci.py`, `_ci_commit_convention.py`, `_ci_report.py` -> `commands/twins/`; `_git_base.py` plus `ScanRange`, `resolve_range` and `_symmetric_base` (`commands/gate_scan.py:51-61, 82-104, 135-141`) -> `commands/twins/_git_scope.py`; `_twin_policy.py` and `_ci_policy.py` -> `commands/twins/policy.py` (verbatim concatenation, about 245 lines, public because `init.py:461` imports it); docstring-only `commands/twins/__init__.py`. No `twins/ci/` subpackage (H6).
- **Also:** the cli imports; `init.py:448, :461` lazy imports; SPEC.md:3333. `ci.py` is close to 500 lines: it must not grow.
- **Tests:** 5.2 N8 (no test file moves; the twin tests stay in `tests/cli/`).
- **Contracts:** `command-independence` per 6.2.
- **Coordination:** B2 also edits the twins' `CONFIG_FILE` constants (`gate_scan.py:45`, `scan_secrets.py:71`, `_twin_policy.py:31`, `_ci_policy.py:27`); either order works, and whichever lands second rebases (7.5 B2 names the call sites under both layouts). N22 rewrites the lazy `evaluators.metrics_gate` import at `_ci_policy.py:78`; whichever lands second rewrites it.
- **Size:** about 1,950 moved lines; one context.

#### N9 `refactor(init): move pre-commit config writing to precommit.py`

- **When:** after #62 (package rule: it moves code out of `commands/`); the import line in `tests/unit/test_docs_lifecycle_hooks_cli.py:40` (#56) is then a plain rewrite. **Blockers:** #62, lane 0, N7.
- **Files:** `commands/init.py:337-439` (`_PRECOMMIT_TEMPLATE_NAME`, `PrecommitTemplateMissingError`, `precommit_template_dir`, `_render_fresh_pre_commit`, `_write_pre_commit`) and all of `commands/_precommit_merge.py` -> `src/coding_agent_playbook/precommit.py` (about 245 lines). The two functions `init.py` now calls across the package lose their underscore (`render_fresh_pre_commit`, `write_pre_commit`); their callers are edited by hand. `init.py` keeps `_has_trailer_rows` and `_uses_commitizen` and passes booleans, so `precommit.py` imports no command. `cli/__init__.py`'s catch of `PrecommitTemplateMissingError` imports it from `precommit`. The template stays at `templates/precommit/`.
- **Tests:** 5.2 N9.
- **Docs:** SPEC.md:2829, :3881 and the `_precommit_merge` mentions.
- **Contracts:** layer `precommit`; the metrics-gate prefix probe gains `precommit`.
- **Acceptance:** `init.py` is about 480 lines (under budget).

#### N10 `refactor(config): move committed-config planning into config/committed.py`

- **When:** after #62 (package rule: it moves `commands/_committed_config.py` out of `commands/`). **Blockers:** #62, lane 0, N2.
- **Files:** `commands/_committed_config.py` -> `config/committed.py` (H13); the imports at `check.py:23` and `init.py:26`; SPEC.md:15, :2251, :2394, :3890.
- **Tests and pins:** 5.2 N10.
- **Coordination:** B2 changes the builders' signatures (`FileSystemStateSource` -> `ConfigFiles`) after this move.

#### N11 `refactor(eval): move runner lookup and result formatting out of commands/eval.py`

- **When:** after #62 (package rule: it moves code out of `commands/` and into `evals/`, both chain-edited). **Blockers:** #62, lane 0.
- **Files:** a verbatim split of `commands/eval.py` (735 lines): the lookups (`:67-70`, `:233-264`) -> `evals/registry.py` (`load_runner_class`, `available_runner_names`, `load_judge_class`, `available_judge_names`, the underscores dropped because they now cross a package); the result serialisers (`:285-445`) -> `evals/report_format.py` (`task_result_to_dict`, `format_task_result_text` and helpers); the listing and show helpers (`:449-735`) -> `commands/_eval_enumerate.py` (H6). `commands/eval.py` keeps `run`, `_run_task_cli`, `_load_task` (about 255 lines) and calls the lookups through the module (`registry.load_judge_class`), because tests monkeypatch them. The group names `coding_agent_playbook.runners` and `.judges` move unchanged (L2).
- **Tests:** 5.2 N11 (the five monkeypatch strings of 5.3.6; `test_eval_aggregate_render.py:12`).
- **Docs:** SPEC.md:2563 (`commands/eval.py:_display_source_path` -> `commands/_eval_enumerate.py`).
- **Not touched:** `evals/prompting.py`, `loader.py`, `validator.py` (chain and grading lanes).
- **Size:** about 500 relocated lines.

#### N12 `refactor(agent_harness): move harness/ to agent_harness/`

- **When:** now, timed (import lines in `adapters/agent_harness_adapter.py` and `tests/adapters/test_agent_harness.py`, #54; `adapters/_skill_writer.py`; `tests/unit/test_docs_lifecycle_hooks_spec.py`). #49 touches none of them. **Blockers:** lane 0. Before starting: `git diff origin/main...<each open ticket branch> -- src/coding_agent_playbook/harness` is empty.
- **Rows:** `harness/{__init__,models,parser,leaf_detectors,emitter,manifest}.py` -> `agent_harness/` (`__init__.py` reworded as "the Agent Harness format round trip" and made docstring-only).
- **Also:** `adapters/_skill_writer.py:82` imports `with_sentinel_body` from `renderer` (the object `harness/emitter.py:28-30` re-exports); the import edits at `adapters/_harness_hooks.py:22`, `adapters/agent_harness_adapter.py:49`, `commands/import_harness.py:46-56`, `commands/_import_hooks.py:22`, `commands/validate_harness.py:4, :18, :23, :40, :47`, `_toml.py:9` (toml_writer after N1); SPEC.md:3895-3896 are changelog records and stay (5.3.8). Manifest kinds and rule ids do not change (ADR 0001). The rename rule matches only `coding_agent_playbook.harness`, never `hook_runtime.harness` or the adapter id `agent_harness` (5.4.3).
- **Tests:** 5.2 N12 (`tests/harness/` -> `tests/agent_harness/`, 8 files).
- **Contracts:** layer `agent_harness`; the two engine-layers lines; the metrics-gate prefix probe gains `agent_harness`.
- **CONTEXT.md:** adds the term **Agent Harness tree**: "the directory tree the agent_harness adapter writes for Agent Harness clients and `import-harness` reads back; it is not a Harness" (question 4).
- **Size:** about 800 moved lines, about 25 files.

#### N13 `refactor(adapters): move the Claude Code settings merge into adapters/claude_code/`

- **When:** after #62 (package rule: it moves modules within `adapters/`, which the open chain edits: #54 and #56/#57 edit `claude_code_adapter.py`, `_claude_hooks.py` and other adapters). **Blockers:** #62, lane 0.
- **Rows:** `claude_settings.py` -> `adapters/claude_code/settings/managed_merge.py`; `_settings_plan.py` -> `settings/_plan.py`; `_settings_drift.py` -> `settings/drift.py` (public: `commands/check.py:22` imports it); `_json_spans.py`, `_json_edits.py` -> `settings/`; `claude_rule_paths.py` -> `adapters/claude_code/paths.py`. Docstring-only `adapters/claude_code/__init__.py` and `settings/__init__.py`; `adapters/__init__.py` gets a docstring.
- **Also:** source import edits at `hook_registrations/claude.py:15`, `commands/check.py:22`, `_guard_config_protect.py:36`, `_canonical_json.py:9` (doc; `lockfile/canonical_json.py` after N5), and in the chain files `claude_code_adapter.py:57, :62`, `_claude_hooks.py:28`, `commands/_sync_hooks.py:49`, `commands/sync.py:69`; SPEC.md:1811 (`:3855` and `:3865` are changelog records, 5.3.8).
- **Tests and pins:** 5.2 N13; the closure pins `test_claude_settings.py:524-543` and `test_claude_code_rules.py:94`.
- **Contracts:** the private line `commands.check -> adapters._settings_drift` goes.
- **Size:** about 1,560 moved lines, about 22 files.

#### N14 `refactor(hook_runtime): move the guard-twin judges into hook_runtime/judges/`

- **When:** after #62 (package rule: it moves modules within `hook_runtime/`, which the open chain edits; `guard_config.py:107` and `tests/hook_runtime/test_import_budget.py:673` are #58's). **Blockers:** #62, lane 0.
- **Rows:** section 4.24, `hook_runtime/judges/`: `_hosts.py` -> `judges/hosts.py`; `cutover.py` -> `judges/commit_cutover.py`; `handlers/_cli_words.py` -> `judges/cli_words.py`; `handlers/_install_cmds.py` -> `judges/install_commands.py`; `handlers/_dependency_tiers.py` -> `judges/dependency_tiers.py`; `handlers/_manifest_diff.py` -> `judges/manifest_diff.py`; `handlers/_notebook_cells.py` -> `judges/notebook_cells.py`; `handlers/_notebook_check.py` -> `judges/notebook_check.py`; `handlers/_sink_scan.py` -> `judges/sink_scan.py`, with `trusted_artifact_line` from `handlers/deser.py:117-131` (H3, H14). Docstring-only `judges/__init__.py` with exactly this text, so N14 and N15 (parallel lanes) create identical files and whichever lands first adds it: `"""Judges the hooks and their guard twins share: pure checks that return verdicts, with no hook I/O."""`. This is the designer's B5 (section 8 B.8) widened to every twin-shared judge.
- **Also:** handler module paths do not change, so `hook_runtime/registry.py` (#58) and every `STAGE_FACTORIES` string stay. `deser.py`'s re-export of `SinkTable` and `new_sink_calls` (`:31-35`) is removed: `commands/scan_sinks.py` imports `SinkTable`, `new_sink_calls`, `SinkHit` and `trusted_artifact_line` from `judges.sink_scan`. Import rewrites in the twins (`check_deps`, `scan_sinks`, `check_notebooks`, `_ci_commit_convention`), the handlers that use these helpers (`dependencies`, `deser`, `_sink_writes`, `_sink_regex`, `notebooks`, `stop_sweep` at `:54, :187, :195-197`, `network`, `exfil`, `taint`), and the tests.
- **Tests:** 5.2 N14.
- **Contracts:** five private lines go.
- **Acceptance:** `rg "hook_runtime\.handlers\._" src/coding_agent_playbook/commands` prints nothing; the egress judge keeps its lazy imports (no `socket`, `ipaddress` only for an address-shaped host); the budget tests pass unchanged in count.
- **Size:** about 1,730 moved lines, about 30 files.

#### N15 `refactor(hook_runtime): move the gate-weakening judge and the eval path classes`

- **When:** after #62 (package rule: it moves root `gate_scan.py` and `_gate_scan_files.py` into `hook_runtime/judges/` and `handlers/_eval_paths.py` out of `hook_runtime/`, which the open chain edits; `guard_config.py:106` is #58's). **Blockers:** #62, lane 0.
- **Rows:** `gate_scan.py` -> `hook_runtime/judges/gate_weakening.py`; `_gate_scan_files.py` -> `hook_runtime/judges/_gate_weakening_files.py`; `handlers/_eval_paths.py` and `gate_scan.TEST_PATH_GLOBS` (`:74`) -> `artifacts/path_classes.py` (stdlib-only; `re` only). Docstring-only `artifacts/__init__.py` (the package A1 and A2 fill later). If N15 lands before N14, it also creates `hook_runtime/judges/__init__.py` with the exact docstring given in N14.
- **Also:** rewrites in `commands/gate_scan.py` (or `commands/twins/gate_scan.py`), `evaluators/paths.py`, `evaluators/types.py` (whichever of N15 and N22 lands second), `guard_config.py:106`, and the `gate_weakening`, `gate_weakening_edit`, `eval_task_authoring_lint` and `guard_eval_fixtures` handlers. `SPEC.md:201` and `hook_runtime/__init__.py:8-9` say the hot path may also import `artifacts.path_classes`.
- **Tests and pins:** 5.2 N15; `_GATE_SCAN`, `_GATE_SCAN_FILES` (the negative assertion at `test_import_budget_stop.py:114` and the positive ones at `:138-139` stay meaningful); `_ENGINE_PATHS` `gate_scan.py` -> `hook_runtime/judges/gate_weakening.py` with the SPEC §5.1 tree.
- **Contracts:** layer `artifacts`; `STDLIB_LEAVES` + `artifacts.path_classes`; the lines of 6.2.
- **Size:** about 810 moved lines, about 20 files.

#### N16 `refactor(hook_runtime): group guard_config reading into hook_runtime/config/`

- **When:** after #62 (package rule: the open chain edits `hook_runtime/`, among them `registry.py` (#58), `ruff_feedback.py` and `_ruff_buckets.py` (#55)); first in the serial hook_runtime lane, which runs N16 -> N17 -> N18 -> N19 -> N20 -> N21 one after another because all six rewrite the import blocks of the same hub files (`_pipeline.py`, `registry.py`, `dispatch.py`, `tests/hook_runtime/fakes.py`, both conftests). **Blockers:** #62, lane 0.
- **Rows:** `config.py`, `_config_reader.py`, `_config_keys.py`, `_hook_records.py`, `_lock_digest.py`, `pin.py`, `protected.py` -> `hook_runtime/config/{guard_config,reader,keys,hook_records,lock_digest,pin,protected}.py`.
- **Tests and pins:** 5.2 N16; budget pins `:214`, `:262`.
- **Contracts:** the two `_config_keys` lines go.
- **Size:** 1,434 moved lines, about 80 importer files.

#### N17 `refactor(hook_runtime): group the shell parser into hook_runtime/shell/`

- **When:** after #62 (package rule, `hook_runtime/`). **Blockers:** #62, N16 (serial lane).
- **Rows:** `shell.py` -> `shell/parse.py`; `_shell_scan.py` -> `shell/_scan.py`; `_shell_segments.py`, `_shell_tokens.py`, `_shell_wrappers.py`, `_shell_writes.py` -> `shell/{segments,tokens,wrappers,writes}.py`; `_shell_options.py` -> `shell/_options.py`; `wrapper_policy.py` -> `shell/wrapper_policy.py`; `gitargv.py` -> `shell/git_command.py`; `_git_options.py` -> `shell/git_options.py`; `_verify_tag.py` -> `stop/verify_tag.py`.
- **Tests:** 5.2 N17. **Contracts:** the `_shell_wrappers` line goes.
- **Size:** 11 modules, 2,134 lines, 56 importer files.

#### N18 `refactor(hook_runtime): group SafeGit into hook_runtime/git/`

- **When:** after #62 (package rule, `hook_runtime/`). **Blockers:** #62, N17.
- **Rows:** `git.py` -> `git/safe_git.py`; `_git_argv.py`, `_git_cache.py`, `_git_fingerprint.py` -> `git/_argv.py`, `_cache.py`, `_fingerprint.py`; `_git_memo.py` -> `git/memo.py`; `_git_parse.py` -> `git/parse.py` (public: the twins and the gate judge import it); `git_log.py`, `git_range.py` -> `git/log.py`, `git/range.py`; `_head_snapshot.py` -> `git/head_snapshot.py`.
- **Tests and pins:** 5.2 N18; `_GIT_MODULE` -> `...hook_runtime.git.safe_git` (H24). **Contracts:** the three twin `_git_parse` lines go.
- **Size:** 9 modules, 1,598 lines, 62 importer files (10 twin commands among them).

#### N19 `refactor(hook_runtime): group runtime state into hook_runtime/state/`

- **When:** after #62 (package rule, `hook_runtime/`). **Blockers:** #62, N18.
- **Rows:** `state.py` -> `state/store.py`; `_state_files.py`, `_state_sweep.py` -> `state/_files.py`, `_sweep.py`; `session.py`, `ledger.py`, `active_prompt.py` -> `state/`; `_prompt_boundary.py` -> `state/_prompt_boundary.py`; `security/audit.py` -> `state/audit_log.py`; `security/decision_summary.py` -> `state/decision_summary.py`.
- **Tests and docs:** 5.2 N19; SPEC.md:3209 (§17.4) and `tests/unit/test_docs_lifecycle_hooks_cli.py:263-264`. #58 has merged by then, so no chain ticket needs a note.
- **Size:** 9 modules, 2,242 lines, 68 importer files.

#### N20 `refactor(hook_runtime): group doctor, canary and simulate into hook_runtime/diagnostics/`

- **When:** after #62 (package rule, `hook_runtime/`; simulate's import line in about 43 `tests/hooks` files is then a plain rewrite). **Blockers:** #62, N19.
- **Rows:** `doctor.py`, `_doctor_checks.py`, `_doctor_opencode.py`, `_doctor_decisions.py`, `canary.py`, `heartbeat.py`, `simulate.py` -> `hook_runtime/diagnostics/`.
- **Tests and docs:** 5.2 N20; the `.github/workflows/ci.yml:54` comment.
- **Size:** 7 modules, 1,217 lines, 55 importer files.

#### N21 `refactor(hook_runtime): move the harness wire types out of harness/__init__`

- **When:** after #62 (package rule, `hook_runtime/`). **Blockers:** #62, N20.
- **Rows:** the 137-line body of `hook_runtime/harness/__init__.py` (`WireOutput`, `ForeignPayload`, `ContractFault`, `ParseContext`, `DENY_EXIT`) -> `hook_runtime/harness/wire.py`, verbatim; `harness/_payload.py` -> `harness/payload.py` (public: `dispatch.py:246` imports it); `harness/__init__.py` keeps its docstring only.
- **Tests:** 5.2 N21 (the harness and stop tests mirror into `tests/hook_runtime/{harness,stop}/`).
- **Contracts:** the `_payload` line goes; `_INITS_WITH_CODE` shrinks.
- **Size:** about 280 lines, 26 importer files.

#### N22 `refactor(metrics-gate): move the metrics gate into metrics_gate/`

- **When:** now, timed (`tests/unit/test_docs_lifecycle_hooks_spec.py:25` imports `MetricConfig`, #50/#53). **Blockers:** N2 (the `config.py:34` re-export of `parse_metrics_config` is gone).
- **Rows:** `evaluators/metrics_gate.py` -> `metrics_gate/run.py`; `evaluators/_metrics_inputs.py` -> `metrics_gate/inputs.py` and `_metrics_suite.py` -> `metrics_gate/suite.py` (public: Stop handlers import them); `measurement_snapshot.py` -> `metrics_gate/snapshot.py`; `policy.py` -> `metrics_gate/policy.py`; `metrics_config.py` -> `metrics_gate/config.py`, which also receives class `MetricConfig` from `evaluators/types.py:280` (H9). Docstring-only `metrics_gate/__init__.py`; the gate's interface is `run.py`, `config.py`, `inputs.py`, `suite.py`, `policy.py` and `snapshot.py`.
- **Also:** rewrites in `commands/metrics.py`, `commands/_ci_policy.py` (or `twins/policy.py`), `_guard_config_quality.py:74, :98`, `evaluators/__init__.py` (drops `MetricConfig`), and the handlers `_metrics_pass.py`, `coverage_diff_gate.py`, `_coverage_report.py`, `quality_metrics.py` (`docstring_nonregression.py`, #55, is untouched).
- **Tests and pins:** 5.2 N22; `_METRICS_GATE` -> `...metrics_gate.run`.
- **Contracts:** layer `metrics_gate`; the lines of 6.2.
- **Size:** about 1,800 moved lines, about 12 source and 15 test files.

#### N23 `refactor(evals): group the task compiler under evals/compile and the run pipeline under evals/run`

- **When:** after #62 (package rule: the open chain edits `evals/`, `prompting.py` for #54). N22 runs now and has landed by then; a parallel after-chain lane that lands first is handled by the rebase recipe of 7.1.3 (`pyproject.toml`, MIGRATION.md). **Blockers:** #62, lane 0.
- **Rows:** `evals/_compile.py` -> `evals/compile/compiler.py` (public inside `compile/`: `evals/task.py` and `evals/run/scoring.py` import it); `_expr.py`, `_handles.py` -> `evals/compile/`; `runner.py` -> `evals/run/harness_runner.py`; `scoring.py`, `fake_runner.py`, `claude_code_runner.py`, `opencode_runner.py`, `agent_env.py` -> `evals/run/`; root `git_env.py` -> `evals/run/git_env.py`. Docstring-only `compile/__init__.py` and `run/__init__.py`; `evals/__init__.py` becomes docstring-only (no source module imports names from it).
- **Also:** rewrites in `evals/task.py:36, :232`, `commands/eval.py:60`, `tests/conftest.py:26`; `pyproject.toml:78-80` values (re-install); the 14 monkeypatch strings of 5.3.6.
- **Not touched:** `evals/prompting.py`, the model code of `task.py`, `loader.py`, `validator.py`, `tests/evals/test_prompting.py`, `commands/validate.py`, `sources/filesystem.py`.
- **Tests:** 5.2 N23. **Contracts:** drop `git_env`; `_INITS_WITH_CODE` - `evals/__init__.py`.
- **Size:** about 2,400 moved lines, about 20 test files.

#### N24 `refactor(evals): move the eval-only check families and the named gate and rubric registries into evals`

- **When:** after #62 (package rule: it moves code into `evals/`). **Blockers:** #62, N23 (`evals/compile/` exists).
- **Rows:** `evaluators/checks/files.py`, `answer.py`, `aggregate.py` -> `evals/checks/` (docstring-only `__init__.py`); `evaluators/gates.py` -> `evals/compile/gate_registry.py`; `evaluators/rubrics.py` -> `evals/compile/rubric_registry.py` (both keep loading their fixed entry-point groups, L2).
- **Also:** registration by import moves with the families: `evaluators/checks/__init__.py` stops importing them and `evals/compile/_handles.py` (the only `get_check` caller) imports them, so `@register_check` fires before its first lookup; `evaluators/__init__.py` drops the `get_rubric`, `register_rubric`, `all_rubric_names` re-exports.
- **Tests:** 5.2 N24, plus `test_handles_sees_every_check_family` (the sorted check ids `_handles` can look up equal the baseline list).
- **Size:** about 840 lines, about 10 test files.

#### N25 `refactor(grading): rename evaluators to grading`

- **When:** after #62, because it waits for N24 (question 3); `docstring_nonregression.py:41, :139` (#55), `tests/hook_runtime/test_import_budget.py:64, :462` (#58) and `test_docs_migration_hooks.py` are then plain rewrites. **Blockers:** #62, N22, N24.
- **Rows:** every remaining `evaluators/` module -> `grading/` (section 4.18): `checks/compose.py` -> `grading/compose.py`, `checks/execution.py` -> `grading/execution_checks.py`, `checks/registry.py` -> `grading/check_registry.py`, `checks/judged.py`, `checks/judge_metric.py` -> `grading/`, `builtins/` -> `grading/static_metrics/`, `execution/` -> `grading/execution_metrics/`; `tool_runner.py`, `paths.py`, `baseline_git.py` stay in the kernel (kernel metrics import them).
- **Also:** every package `__init__.py` becomes docstring-only; registration by import moves to explicit module lists in `grading/metric.py` (`:124-125`, the 12 metric modules) and `grading/check_registry.py` (`:156-163`); about 60 files rewritten by the script; the MIGRATION sentence for out-of-tree Metric, Check, rubric and gate authors (5.3.8).
- **Tests:** 5.2 N25, plus `test_metric_and_check_registries_are_unchanged` (sorted metric names and check ids equal the baseline lists).
- **Contracts:** layer `grading`; the renames of 6.2.
- **Size:** about 4,600 lines moved by `git mv`, about 60 files edited; one context, provided the codemod is the script.


### 7.5 Behaviour PRs B1-B10 (B1 and B7 now; the rest after #62)

Their designs are section 8. Each runs the gate; B1, B2, B3, B4a and B4b also run the parity check where they touch what sync or the runtime reads. B2, B3, B4a, B4b, B6, B8, B9 and B10 wait for #62 and lane 0, because the moves they wait for do (question 3, 2.3).

| Id | Blockers | Section | Harmonised notes |
| --- | --- | --- | --- |
| B1 | none; must merge before #54 starts | 8 B.4 | the four tests are written first and are red on the parent commit |
| B2 | #62, N2, N10 | 8 B.5 | `ConfigFiles` and `CommittedDocument` join `config/files.py`, which N2 created with `FileSystemStateSource`; the committed-config builders live in `config/committed.py` (N10); if N8 has landed, the twin call sites are under `commands/twins/` |
| B3 | #62, N16 | 8 B.6 | `hook_runtime/config/guard_tables.py` (in the package N16 created, L13) |
| B4a | #62, B3, N14 | 8 B.7 | `hook_runtime/config/hook_config.py`; N14's judge moves land first (the handlers it edits import them) |
| B4b | #62, B4a | 8 B.7 | — |
| B6 | #62, N8, N14 | 8 B.9 | `commands/twins/_runner.py`; adds the `twins-use-judges` forbidden contract (direct imports from `commands.twins`) with no exception (N14 made every twin-shared judge public) |
| B7 | none | 8 B.10 | test only |
| B8 | #62, N22, N23, N25 | 8 B.11 | `grading/measuring.py`; `ProjectFactory` moves beside `ProjectHandle` in `grading/execution_metrics/project.py` |
| B9 | #62, N7, B6 | 8 B.12 | `cli/_command.py`; the twin modules are under `commands/twins/` |
| B10 | #62, B9, N11 | 8 B.12.6 | `eval`'s flags go into the flat `commands/eval.py` (H6) |

### 7.6 Moves after the chain

Every PR here waits for #62 and lane 0, adds to the criteria of 7.1.2 and runs the parity check when it touches sync, rendering, adapters or the runtime.

#### A1 `refactor(artifacts): move hook schema, hook frontmatter and member references into artifacts/`

- **Blockers:** #62 (#57 edits `_hook_schema.py` and `_hook_frontmatter.py`).
- **Rows:** `_hook_schema.py` -> `artifacts/hook_schema.py` (stdlib-only; `hook_policy` loads it on a light path, pinned by `test_hook_policy_tables.py:195-207`); `_hook_frontmatter.py` -> `artifacts/hook_frontmatter.py`; `_member_reference.py` -> `artifacts/member_reference.py` (in `artifacts/`, not `skills/`, because `Skill.member_references` imports it and `skills/` sits above `artifacts/`).
- **Also:** the re-exports `types.py:27` and `:30-39` and the `as` re-exports of `_hook_frontmatter.py:22-26` are removed; importers name the defining module (`types.py` itself stays until A2).
- **Tests and pins:** 5.2 A1; the probes of 5.3.4; the eval-task allowance.
- **Size:** about 30 importer files.

#### A2 `refactor(artifacts): split types.py into artifacts modules`

- **Blockers:** A1.
- **Rows:** `types.py` -> `artifacts/frontmatter.py` (44-77), `rule.py` (78-160), `prompt.py` (161-245), `skill.py` (246-321), `hook.py` (322-416).
- **Also:** a name-level rewrite of the 111 importer modules: one `[[names]]` entry per destination, so every `from ...types import A, B` is split by destination. `Skill.id` and the rest of catalog-layers are not scheduled.
- **Tests:** 5.2 A2. **Contracts:** drop `types`; the stack line `-> artifacts.**`.
- **Size:** about 115 files, mechanical; one implementer context with the script. The reviewer checks the map, the `check` output and the gate rather than every line.

#### A3 `refactor(skills): move skill composition into a skills package`

- **Blockers:** A1 (`member_reference` in `artifacts/`).
- **Rows:** `skill_document.py` -> `skills/document.py`; `skill_membership.py` -> `skills/membership.py`; `adapters/_agent_skill_rules.py` -> `skills/naming.py` (public; ends the skills -> adapters private import).
- **Also:** the re-export ladder at `adapters/_skill_writer.py:78-79` and its pin test `test_skill_writer_reexports_the_one_object_the_rules_module_defines` are removed (L2, H22).
- **Tests and pins:** 5.2 A3; the closure pin `tests/adapters/test_agent_skill_rules.py:39-50`.
- **Contracts:** layer `skills`; six private lines go; the engine-layers line for `skill_membership.py:24` (TYPE_CHECKING `Adapter`) is added with `# SK-1`.
- **Size:** about 20 files.

#### A4 `refactor(validation): move the validation rule set and preflight into validation/`

- **Blockers:** #62 (#52 and #54 edit `validate.py` and `_validate_skills.py`).
- **Rows:** `commands/validate.py:1-410` -> `validation/checks.py` (`collect_validation_findings`, `collect_validation_errors`, `sync_gate_errors`, `_artifact_errors` and the in-file checks; `_warn_refused_skill_files` becomes `warn_refused_skill_files`), `commands/validate.py` keeps `run` (about 30 lines); `_validation.py` -> `validation/findings.py`; `_validate_context.py` -> `validation/context.py`; `_validate_frontmatter.py`, `_validate_hooks.py`, `_validate_links.py`, `_validate_skills.py`, `_validate_prompts.py` (#54) -> `validation/_frontmatter.py`, `_hooks.py`, `_links.py`, `_skills.py`, `_prompts.py`; `_sync_preflight.py` -> `validation/preflight.py`; the link checker of `links.py` -> `validation/link_check.py` (`links.py` is then gone).
- **Also:** the import rewrites at `sync.py:70, :91-92`, `check.py:23`, `init.py:24`; SPEC.md:2462 (`:3838`, `:3922`, `:3928` are changelog records, 5.3.8); `orchestrator.py` is left alone (A5 moves `SyncContext`).
- **Tests:** 5.2 A4, including the deferred catalog test move `tests/unit/test_sources_filesystem_bundled.py` -> `tests/catalog/test_source_bundled.py` (kept at `tests/unit/` by N3 because #50-#53/#56 edit it). **Contracts:** layer `validation`; the lines of 6.2; the prefix probe gains `validation`.
- **CONTEXT.md:** adds the term **Validation**: "the checks `playbook validate` and the sync gate run over canonical artifacts before anything is written" (question 4).
- **Size:** about 2,100 lines, mostly `git mv`.

#### A5 `refactor: split orchestrator into catalog, artifacts, adapters and validation modules`

- **Blockers:** A2, A4, N3, N4.
- **Rows:** `orchestrator.py` (the rest after N4) -> `catalog/resolve.py` (`Collision`, `OverlayResolver`, `_resolve`, `_hook_collision`), `catalog/source.py` (`engine_package_of`, beside `FileSystemArtifactSource`, because `_validate_hooks` also calls it), `artifacts/identity.py` (`artifact_id_of`, `_source_package`, `template_source`; H11), `adapters/registry.py` (`discover_adapters`, `installed_output_locations`, `orchestrator.py:271-327`), `validation/context.py` (`SyncContext`, `_warn_deprecated_overlays`, `_resolve_hooks`, joining the config-less context helpers A4 put there; H4). `validation/context.py` stays under 500 lines.
- **Also:** `tests/fakes.py`; the monkeypatch target of 5.3.6; the `orchestrator.py:1-25` docstring's content goes to the new modules' docstrings.
- **Tests:** 5.2 A5. **Contracts:** drop `orchestrator`; the `catalog.resolve` line of 6.2 if it is visible now.
- **Size:** about 35 files.

#### A6 `refactor(sync): move the sync pipeline out of commands/ into sync/`

- **Blockers:** A4 (sync imports `validation.checks` and `validation.preflight`). A9 and A7 first is better (they retire the adapters private lines), not required.
- **Rows:** `commands/sync.py` -> `sync/pipeline.py` (`execute`, `_run_sync`, `_render_into`, `_run_write`, `_leftover_policy`, `_ABORT_OUTCOME`; about 400 lines), `sync/_check_modes.py` (`sync.py:420-543`) and the thin `commands/sync.py` (`run`, `_resolve_repo_root`); `_sync_render.py` -> `sync/render.py` (public: `commands/render.py:20`); `_sync_lockfile.py` -> `sync/_dispatch.py`; `_sync_hooks.py` -> `sync/_hook_outputs.py`; `_sync_hook_local.py` -> `sync/_machine_local.py` (flat, not `sync/hooks/`, so `sync/pipeline.py` may import both); `_sync_orphans.py` and `_output_locations.py` -> `sync/_leftovers.py` (re-measure: if the sum exceeds 480 lines keep `sync/_output_locations.py`); `_sync_output.py` -> `sync/_output_policy.py`; `_output_blockers.py` -> `sync/_output_blockers.py`; root `git_client.py` -> `sync/git_client.py`.
- **Also:** `init.py:25` -> `sync.pipeline.execute`; `render.py:20` -> `sync.render`; `execute` keeps its signature and `int` return (the `SyncOutcome` interface is sync-engine, not scheduled). Test codemod: the 22 test files that call only `_sync.execute` import `from coding_agent_playbook.sync import pipeline as _sync`; the 6 that also call `_sync.run` keep a second alias for the command.
- **Tests:** 5.2 A6. **Contracts:** layer `sync`; the lines of 6.2; the prefix probe gains `sync`.
- **CONTEXT.md:** adds the term **Sync**: "one `playbook sync` run: resolve the catalog, render every adapter's Generated output and write the Lockfile" (question 4).
- **Size:** about 3,300 moved lines and about 45 test files with import edits; one context with the script.

#### A7 `refactor: move the generated-output write guard and copyable source files into generated_output/`

- **Blockers:** N6.
- **Rows:** `adapters/_owned_files.py` -> `generated_output/write_guard.py`; `adapters/_skill_sources.py` and `adapters/_skill_files.py` -> `generated_output/source_files.py` (a verbatim concatenation, about 175 lines; H8).
- **Also:** SPEC.md:1807, :1825, :2015, :2016; the docstring cross-references at `_skill_sources.py:7`, `_skill_files.py:6`, `_skill_writer.py:13`, `commands/_sync_hooks.py:20`.
- **Tests:** 5.2 A7. **Contracts:** five private lines go. `STDLIB_LEAVES` is unchanged (N6 admitted only `generated_output.atomic_io` and `generated_output.sentinel`), so `stdlib-leaves` stays green although `source_files.py` imports the `Skill` type under TYPE_CHECKING; the regenerated `FORBIDDEN` lists of both stacks gain `generated_output.source_files` and `generated_output.write_guard`. Acceptance: `test_leaf_contract_covers_every_stdlib_leaf` and `test_stack_contract_forbids_every_non_leaf_module` pass with exactly those two additions.

#### A8 `refactor(adapters): move the Claude Code adapter into adapters/claude_code/`

- **Blockers:** N13.
- **Rows:** `claude_code_adapter.py` -> `adapters/claude_code/adapter.py`; `_claude_hooks.py` -> `adapters/claude_code/hooks.py`; `_secret_native.py`, `_destructive_native.py`, `_overlay_native.py` -> `adapters/claude_code/` under the same names (private; merging them into `native_rows.py` is not scheduled).
- **Also:** `pyproject.toml:61` value (re-install); SPEC.md:1811, :1864; `commands/_sync_hooks.py:45` keeps importing the adapter class (not a layer violation).
- **Tests and pins:** 5.2 A8; the closure pin `test_claude_code_rules.py:96`.
- **Size:** about 870 moved lines.

#### A9 `refactor(adapters): rename the harness adapters and move the skill writer into adapters/skill_dirs/`

- **Blockers:** #62. Not blocked by A3 or A7: under the private-modules rule `adapters/skill_dirs/writer.py` may still import `adapters._agent_skill_rules` and `adapters._skill_sources`.
- **Rows:** `agents_md_adapter.py` -> `agents_md.py`; `continue_adapter.py` -> `continue_.py` (`continue` is a keyword); `opencode_adapter.py` -> `opencode.py` (a one-module package would only add a segment); `shared_skills_adapter.py` -> `shared_skills.py`; `_skill_writer.py` -> `skill_dirs/writer.py` (public: sync and validation import it); `_prior_output.py` -> `skill_dirs/ownership.py` (public: sync installs its ContextVar). Docstring-only `skill_dirs/__init__.py`.
- **Also:** `pyproject.toml:60, :62-64` values (re-install); SPEC.md:18, :1709, :1863, :1865-1867, :2012, :3913, :3916, :3922; the docstring pins of the `_skill_writer.py` reference (`opencode_adapter.py:17`, `shared_skills_adapter.py:19`, `_prior_output.py:3`, `claude_code_adapter.py:14`, `commands/_output_blockers.py:24`).
- **Tests:** 5.2 A9. **Contracts:** four private lines go.
- **Size:** about 1,220 moved lines, about 40 test import edits.

#### A10 `refactor(hook_runtime): move the event and decision model into hook_runtime/dispatch/`

- **Blockers:** #62, N21. L2 does not list `hook_runtime.event`, `decision`, `paths` or `registry`, so they move with no shim; A10 adds a MIGRATION.md entry for out-of-tree handler authors with the old and new paths of `CanonicalEvent`, `HandlerResult` and `Decision` (A11 adds `register_hook_handler` and `HandlerContext`).
- **Rows:** `event.py`, `decision.py`, `paths.py`, `caps.py`, `policy.py` -> `hook_runtime/dispatch/`; `dispatch.py` -> `dispatch/run.py`. The dispatcher module moves here, not in A11, because the new `hook_runtime/dispatch/` directory shadows `hook_runtime/dispatch.py`: with both present, `from coding_agent_playbook.hook_runtime.dispatch import run_event` (hook_runtime/cli.py:196) raises ImportError (reproduced in the review scratchpad). `run.py` keeps importing `_pipeline`, `_execute` and the other root helpers from `hook_runtime/` until A11; an underscore import from a descendant package is legal under rule 2.
- **Tests and pins:** 5.2 A10; budget pin `test_import_budget.py:168` -> `hook_runtime.dispatch.run`. **Size:** 1,318 lines, a mechanical rewrite of about 225 importer files.

#### A11 `refactor(hook_runtime): move the dispatcher into hook_runtime/dispatch/`

- **Blockers:** A10.
- **Rows:** (`dispatch.py` already moved in A10) `_pipeline.py`, `_execute.py`, `_faults.py`, `_post_write.py`, `_decision_log.py` -> `dispatch/` (private); `_selection.py`, `_prefilter.py`, `_tail.py`, `_ports.py`, `_external.py`, `_event_memo.py` -> `dispatch/selection.py`, `prefilter.py`, `tail.py`, `ports.py`, `external.py`, `event_memo.py` (public: imported from outside `dispatch/`); `combine.py`, `watchdog.py`, `routing.py`, `registry.py`, `escape.py`, `deps.py`, `proc.py` -> `dispatch/`.
- **Tests and pins:** 5.2 A11.
- **Size:** 18 modules, 3,492 lines, about 165 importer files. The MIGRATION.md entry of A10 gains `register_hook_handler` and `HandlerContext` (`hook_runtime.dispatch.registry`).

#### A12 `refactor(artifacts): move the path-glob grammar to artifacts/path_globs.py`

- **Blockers:** A10, N15.
- **Rows:** `hook_runtime/globs.py` with `fold_key` and `FOLDING_PLATFORMS` from `paths.py:194` -> `artifacts/path_globs.py`.
- **Contracts:** `STDLIB_LEAVES` + `artifacts.path_globs`; the grading-kernel line goes. **Docs:** SPEC.md:201.
- **Size:** 135 lines, 18 importer files.

#### A13 `test(hook_runtime): move the hook pack tests under tests/hook_runtime/handlers/`

- **Blockers:** #62 (#55 and #58 edit or create files in `tests/hooks/`). Test-only.
- **Files:** the 53 files of 5.2 A13, renamed `test_<hook id>.py` in the pack directories; SPEC.md:3187. After it, `tests/hooks/` belongs to the sync-time `hooks/` package (H19).

#### A14 `refactor(hook_runtime): split the safety pack and shared helpers into handlers/safety and handlers/_shared`

- **Blockers:** A13, A11, GC-1 (`guard_config.py` must no longer import `_control_plane_*`), N14 and N15 (added 2026-10-18: since question 3 they no longer land before #62, and the pack split assumes the twin-shared judges and `_eval_paths` have left `handlers/`).
- **Rows:** section 4.24, `handlers/safety/` and `handlers/_shared/` (31 modules, about 6,440 lines): each handler module named after its snake-cased hook id.
- **Also:** the `_BUILTIN_HANDLER_MODULES` and `STAGE_FACTORIES` strings (the registry names stay); the budget constants of 5.3.3.

#### A15 `refactor(hook_runtime): split the verify and audit packs into handlers/verify and handlers/audit`

- **Blockers:** A14. **Rows:** section 4.24 (23 modules, 4,746 lines, including `_agent_transcript.py` and `_public_api.py`). `gate_weakening.py` and `gate_weakening_edit.py` stay two modules (the pre-edit companion is on the hot path, `test_import_budget_stop.py:138-139`).

#### A16 `refactor(hook_runtime): split the protect and feedback packs and make the ruff seam public`

- **Blockers:** A14. **Rows:** section 4.24 (25 modules, 5,416 lines, plus #58's `skill_nudge.py`); `hook_runtime/_ruff.py` -> `hook_runtime/ruff.py` (public: the feedback handlers, the lint stage and the sync-time ruff readers share it). **Contracts:** the two `_ruff` private lines go.

#### A17 `refactor(hooks): move hook_policy into hooks/resolution, hooks/contract and hooks/enforcement`

- **Blockers:** A13.
- **Rows:** section 4.11: `merge`, `override_rules`, `effective`, `resolved`, `lint_codes`, `tables` -> `hooks/resolution/`; `contract`, `contract_set`, `_contract_handlers`, `handler_catalog` -> `hooks/contract/`; `_findings.py` -> `hooks/contract/findings.py` (public); `labels.py` and `advisory.py` -> `hooks/enforcement.py` (verbatim concatenation); #56's `guardrails_skill.py` -> `hooks/guardrails_skill.py`. `hook_policy/__init__.py`'s 138-line facade dissolves: its 63 importers name the defining module.
- **Tests and pins:** 5.2 A17; `_ENGINE_PATHS` `hook_policy/` -> `hooks/`; `test_runtime_config.py:503`.
- **Size:** about 3,000 lines.

#### A18 `refactor(hooks): move hook_registrations and the hook shim templates into hooks/registrations`

- **Blockers:** A17, N13.
- **Rows:** `hook_registrations/*` -> `hooks/registrations/` (the 115-line facade dissolves, 27 importers); `templates/hook_shims/*` -> `hooks/registrations/templates/` (H17); `LAUNCHER_TOKEN` (`adapters/_settings_plan.py:43`, by then `adapters/claude_code/settings/_plan.py`) and `LAUNCHER_PATH` -> the new stdlib-only `hooks/registrations/launcher.py`, imported by `claude.py` and the settings merge (H15).
- **Also:** `_TEMPLATE_DIR` (`hook_registrations/_templates.py:20`), `test_wire_contract.py:193`, `_ENGINE_PATHS` (`hook_registrations/`, `templates/hook_shims/`), `catalog/README.md:127`.
- **Tests:** 5.2 A18.

#### RS-1 `refactor(rendering): move the renderer, rule registry and prompt delivery into rendering/`

- **Blockers:** B1 (P5), N4 (P6), A5 (`template_source` already in `artifacts/identity.py`, H11), A18. A18 is needed because `rendering` becomes a layer below `adapters` here, and layer contracts follow chains through modules outside the layers: until A18 moves `LAUNCHER_TOKEN` to the stdlib leaf `hooks/registrations/launcher.py` (H15), `renderer > hook_registrations > hook_registrations.claude > adapters.claude_settings` (`hook_registrations/claude.py:15`; grimp on the baseline) is an upward edge, and `engine-layers` would turn red. AH-1 and CP-2 inherit the blocker through RS-1.
- **Design:** section 9 AC.3.5, with the harmonised rows: `template_source` stays in `artifacts/identity.py` and `rendering/` imports it; the `SENTINEL` re-export is already gone (N6).

#### AH-1 `refactor(agent_harness): move the Agent Harness adapter and importer into agent_harness/`

- **Blockers:** N12, A7 (public `generated_output.source_files`), B9 (the two harness commands export their protocol members), RS-1.
- **Design:** section 9 AC.4.5 minus the `harness/*` rows (N12 moved them): `adapters/agent_harness_adapter.py` -> `agent_harness/adapter.py`; `adapters/_harness_hooks.py` -> `agent_harness/hook_sidecars.py`; `commands/import_harness.py:72-512` -> `agent_harness/importer.py` (`_write_result` becomes `write_import`); `commands/_import_files.py`, `commands/_import_hooks.py` -> `agent_harness/_import_files.py`, `_import_hooks.py`; `pyproject.toml:59` value (re-install).
- **Contracts:** the two N12 engine-layers lines go.

#### GC-1 `refactor(hook_runtime): give the guard_config contract names public homes`

- **Blockers:** N16, B3 (and #62: it rewrites `guard_config.py`, which #58 edits).
- **Design:** section 9 AC.2.5 (GC-1), with the rows N14, N15, N16, N17 and A16 already made public removed; GC-1 creates the stdlib-only `hook_runtime/config/schema.py`.
- **Contracts:** the two `_control_plane_*` private lines go.

#### GC-2 `refactor(hooks): move the guard_config writer into hooks/guard_config`

- **Blockers:** GC-1, A6 (`sync/` exists), A13 (`tests/hooks/` is free), A17, A18.
- **Design:** section 9 AC.2.5 (GC-2); the script copies and the protected-set assembly go to `sync/_hook_scripts.py` and `sync/_protect.py` (H10).
- **Contracts:** drop `guard_config` and the ten `_guard_config_*` names; the five private lines `# GC-3`; delete the budget pin `:576`.

#### CP-2 `refactor(init): split commands/init.py into _init_answers, _init_config_plan and _init_overlays`

- **Blockers:** N9, B9, RS-1, and #62 (L12 puts the init command protocol after the chain). Note: ticket 03 (#43, PR #68) was the last chain ticket that edits `commands/init.py`, `commands/_init_adapters.py` and `cli.py`, so no open ticket touches them; L12 still schedules CP-2 and CP-3 after #62, which keeps CP-1 before CP-3 and lets RS-1 land before the split rewrites the renderer imports.
- **Design:** section 9 AC.5.5 (CP-2) with flat modules (H6): `commands/_init_answers.py`, `commands/_init_config_plan.py`, `commands/_init_overlays.py`; `commands/init.py` and `commands/_init_adapters.py` stay.

### 7.7 Behaviour PRs after the chain

| Id | Blockers | Design | Notes |
| --- | --- | --- | --- |
| CF-2 | A2, N2, N5 | below | the config-files remainder |
| SK-1 | A3 | below | contract burn-down, types only (H27) |
| GC-3 | GC-2, B2 (P1), N22 (P3) | 9 AC.2 | `compile_guard_config` reads its own repo inputs |
| GC-4 | GC-1, A17 | 9 AC.2 | `HookRecordJson` |
| RS-2 | RS-1 | 9 AC.3 | `RenderSession` |
| RS-3 | RS-1, AH-1 | 9 AC.3 | `FakeRuleRegistry` |
| AH-2 | AH-1 | 9 AC.4 | `HarnessTree`, `lint_harness`, `read_hook_sidecar` |
| CP-1 | B9 (P4) | 9 AC.5 | sync, validate, render own their flags |
| CP-3 | CP-2, CP-1 | 9 AC.5 | init owns its flags; the `Ask` seam |

#### CF-2 `refactor(types): delete _typing and type the sources with the real classes`

- **Scope:** delete `_typing.py` (a TYPE_CHECKING pass-through whose `Config` and `Lockfile` are `Any`); its users import `artifacts.*`, `config.model.Config` and `lockfile.model.Lockfile` under `TYPE_CHECKING` (`adapters/base.py`, `agents_md.py`, `continue_.py`, `opencode.py`, `shared_skills.py`, `skills/membership.py`, `hook_runtime/handlers/feedback/_ruff_buckets.py`, `config/files.py`); delete `pyproject.toml:219`.
- **Acceptance:** `rg "_typing" src` prints nothing; strict mypy passes with the real classes; an error mypy now finds is fixed in annotations only, and any fix that needs a code change is reported to the user instead of made; the engine-layers line `_typing -> evals.task` goes; the gate passes.

#### SK-1 `refactor(skills): type undelivered_member_warning with a local protocol`

- **Scope:** `skills/membership.py` replaces its `TYPE_CHECKING` import of `adapters.base.Adapter` (`skill_membership.py:24`, used at `:94, :128`) with a local `Protocol` holding the two members it reads (`name` and `delivers_member_rules`, typed as `Adapter` declares them). No runtime change.
- **Tests:** `tests/skills/test_membership.py::test_undelivered_member_warning_accepts_any_deliverer` (a plain fake satisfies the protocol), plus a typed assignment in the test module that makes mypy check that every in-tree adapter class satisfies the protocol.
- **Acceptance:** the engine-layers line `skills.membership -> adapters.base` goes; the gate passes.

### 7.8 Docs

#### D1 `docs(readme): refresh the architecture overview for the flat layout`

- **Blockers:** every move PR of this plan has merged.
- **Scope:** README.md's architecture overview (`README.md:80-160`, including `:158`) shows the packages of section 3.1 and the dependency direction of 3.2 (ASCII), names the external contract of L2, and points to ADR 0002 and section 6's contracts; ADR 0002 records the packages named after no glossary term (question 4): `commands/` holds the CLI subcommands (an implementation layer, not a domain concept), `security/` the stdlib-only secret, PII and path judges plus the trust store, and `precommit.py` the pre-commit template. No other file.
- **Acceptance:** the docs tests (`tests/unit/test_docs_*`) pass; `ruff format --check .` passes on README.md.

## 8. Candidate designs B1-B10: the behaviour PRs designed beside the chain

**Timing (question 3, resolved 2026-10-18; 2.3).** Only B1 and B7 run beside the chain. B2, B3, B4a, B4b, B6, B8, B9 and B10 run after #62, because the moves they wait for move code out of chain-edited packages (7.2.2); N14, which carries B5, runs after #62 too. The designs below are unchanged: they edit no chain file, the sites they leave for after #62 stay with the PRs B.13 names, and each PR re-reads its anchors on main before it starts (L9).

This section is the now-designer's design with the harmonisation of section 11 applied. The move ids it names are this spec's (section 7): lane 0 is T0.0-T0.2, M-config is N2 (and N10 for the committed-config builders), M-twins N8, M-metrics-gate N22, M-grading N25, M-cli N7, M-eval N11. The designer's B5 is folded into N14, which moves every twin-shared judge (H14). Rule 2 of B.1 covers test paths as well: a test file named here at its baseline path is edited where section 5.2 moved it.

Status: implementation spec for the behaviour PRs that run as parallel lanes next to the skills
ticket chain (#49-#62). Settled decisions L1-L14 (2026-10-18) bound every choice below. Every
file:line anchor was read on 2026-10-18 at `ef19a0a` (`origin/main`; the branch
`docs/package-layout` adds only `CONTEXT.md` and ADR 0002). Two findings were reproduced, not
only read: the `playbook render` divergence (B.4.1) and the destructive prefix parity (B.10.1),
both with scratch tests run against the real fixtures.

Words: the CONTEXT.md glossary (Generated output, Lockfile, Guard twin, Grading kernel, Hook,
Guardrail, Detector fact, Renderer, Adapter) and the architecture terms module, interface,
implementation, depth, deep, shallow, seam, adapter, leverage, locality.

### B.1 Rules for every PR in this section

1. A PR either moves files or changes behaviour (L1). B5 (now N14) is the only move-only PR here. Every
   other PR lands after the move PRs it names (L13), in the package the move created.
2. Path rule. Paths are today's. When a move PR has relocated a module first, the change applies
   at the moved path: symbol names are the contract, and the move spec is authoritative on paths.
   No re-export shims (L2).
3. Package `__init__.py` files hold only a docstring (L5); the new source package
   `hook_runtime/judges/` follows it. New test directories (`tests/config/`, `tests/grading/`,
   `tests/hook_runtime/judges/`) get an empty `__init__.py`, like the existing ones (L8).
4. A *chain file* is any file in the TOUCHED FILES lists of the chain tickets still open
   (#49-#62). Only B1 edits chain files (`commands/render.py`, `tests/cli/test_render.py`), on
   purpose and before #54 starts. Every other PR in this section edits no chain file; where a
   chain file holds a site the PR would otherwise migrate, the site is listed under "left for
   after #62" in B.13. `SPEC.md` is edited by the chain too: B2, B8 and B9 change only SPEC
   sections no open ticket edits (§7.1, §7.2, §20.3, §15.3.1 and §12's opening paragraph; the
   chain edits §3, §4.2, §6, §8.2, §9, §10, §11, §12.1, §12.2, §12.6 and §15.3).
5. The gate is the four commands on Python 3.12 and 3.13: `ruff check .`,
   `ruff format --check .`, `mypy`, `pytest -q`. Titles are Conventional Commits; one PR per row
   of B.2; no stacked PRs; harness files are never committed.
6. Replace, do not layer. A test that reached a private module for what now has an interface is
   deleted in the same PR as its replacement, and each PR lists both.
7. Every new public function gets a docstring with intent and one example, explicit types, and a
   test. Errors carry the offending value and the expected shape.

### B.2 The PRs, their order and their blockers

| Id | Title (Conventional Commit) | Kind | Waits for | Chain files edited |
| --- | --- | --- | --- | --- |
| B1 | `fix(render): omit included rules whose applies_if is false` | behaviour, test first | nothing; must merge before #54 starts | `commands/render.py`, `tests/cli/test_render.py` |
| B2 | `refactor(config): read and write the two config files through ConfigFiles` | behaviour | #62, lane 0, N2, N10 | none |
| B3 | `refactor(hook-runtime): read guard_config.json pack tables through typed accessors` | behaviour | #62, N16 (its package, L13) | none |
| B4a | `refactor(hook-runtime): read handler config through its CONFIG_SCHEMA` | behaviour | #62, B3, N14 | none |
| B4b | `refactor(hook-runtime): every builtin reads its config through HookConfig` | behaviour | #62, B4a | none |
| B5 | folded into N14, `refactor(hook_runtime): move the guard-twin judges into hook_runtime/judges/` | move only | #62, lane 0 | none |
| B6 | `refactor(twins): one run skeleton for the guard twins` | behaviour | #62, N14, N8 | none |
| B7 | `test(hooks): the destructive guard denies every native deny prefix` | test only | nothing | none |
| B8 | `refactor(grading): one measuring pass for eval tasks and the metrics gate` | behaviour | #62, lane 0, N22, N23, N25 | none |
| B9 | `refactor(cli): commands declare their own flags` | behaviour | #62, lane 0, N7; after B6 for the twins | none |
| B10 | `refactor(cli): eval declares its own flags` | behaviour | #62, B9, N11 | none |

The move PRs named here are specified in section 7; this section assumes only what follows:

| Move | What this section assumes after it |
| --- | --- |
| lane 0 | import-linter runs from a pytest test (L4); the import-budget guards derive `FORBIDDEN` from the package tree and fail on a stale module-name pin. Rule (2), "an underscore module is imported only from inside its own package", uses the owner rule of 6.1 0.6.2: a module is private to the package above its first underscore segment, and any module inside that package may import it. B6's `commands/twins/_runner.py` is imported only from inside `commands/twins/`. |
| N2 (+ N10) | `config.py`, `config_entries.py`, `config_schema.py`, `hooks_config.py` and `_table_shapes.py` live in `config/` (`config/model.py`, `config/entries.py`, `config/schema.py`, `config/tables/hooks.py`, `config/tables/_table_shapes.py`), and `FileSystemStateSource` with the config half of `sources/filesystem.py` lives in `config/files.py`. `hooks_config.py` moves now: its `_ENGINE_PATHS` line is a soft overlap (H1). `commands/_committed_config.py` is `config/committed.py` (N10). |
| N8 | the six twin commands, `_secret_scope.py`, `ci.py` and `_ci_*.py` live under `commands/twins/` (no `ci/` subpackage, H6); `_twin_policy.py` and `_ci_policy.py` are `commands/twins/policy.py`; `ScanRange` and `resolve_range` left `commands/gate_scan.py:51,82` for `commands/twins/_git_scope.py`, with `_git_base.py`. |
| N25 | `evaluators/` is renamed `grading/` (L6), with `builtins/` as `static_metrics/`, `execution/` as `execution_metrics/` and the kernel's `checks/` flattened (section 4.18). |
| N22 | `evaluators/metrics_gate.py`, `_metrics_inputs.py`, `_metrics_suite.py`, `measurement_snapshot.py`, `policy.py` and the root `metrics_config.py` live in `metrics_gate/` (`run.py`, `inputs.py`, `suite.py`, `snapshot.py`, `policy.py`, `config.py`); `baseline_git.py`, `tool_runner.py` and `paths.py` stay in the kernel, because kernel metrics import them. |
| N7 | `cli.py` becomes `cli/` (`git mv cli.py cli/parser.py`, `main` moved to `cli/__init__.py`); `coding_agent_playbook.cli:main` stays importable, `build_parser` becomes `coding_agent_playbook.cli.parser.build_parser`, and `cli/__main__.py` keeps `python -m coding_agent_playbook.cli` working (used by `hook_runtime/handlers/_source_changed.py:56`, `commands/ci.py:99`, `tests/fakes.py:338`, `tests/hooks/pack_repo.py:358` and SPEC). |
| N11 | `commands/eval.py` (735 lines) is split with no code change; the file map is in B.12.6. |

Lanes that can run at the same time once their blockers have merged, each merged with a full re-gate (section 7.2 has the whole schedule: B1 and B7 run now, every other lane below starts after #62):

```
B1 ─────────────────────────────── (any time; before #54)
B7 ─────────────────────────────── (any time)
lane 0 ─┬─ N16 ─ B3 ─ B4a (after N14) ─ B4b
        ├─ N2 ─ N10 ─ B2
        ├─ N14 ─┬─ B6 ─┐
        │  N8 ──┘      │
        ├─ N22, N23 ─ N24 ─ N25 ─ B8
        └─ N7 ─ B9 (twins after B6) ─ B10 (after N11)
```

B2 and B6 both edit twin modules (B2 the config reads, B6 the run skeleton); whichever merges
second rebases. B3 and B4 edit the same handler files; B4a starts after B3 merges.

### B.3 The review checked against the code (corrections designed on)

Each claim of `synthesize.json` used below was re-read at `ef19a0a`. Where it was wrong or
incomplete, this section designs on the corrected fact:

1. **Baseline.** `origin/main` is `ef19a0a` (#69 merged after #38's `d6501aa`). The chain's
   cli/init edits (`cli.py:87`, `commands/_init_adapters.py`) and its `import_harness.py` lines
   (`_rule_from_entry` passes `skill=entry.skill`; the `skill_hint` at `:399`) have already
   landed with #68 and #69. The open chain tickets touch neither `cli.py`, `commands/init.py`,
   `commands/check.py`, `commands/import_harness.py` nor `commands/validate_harness.py`; their
   test files `tests/cli/test_check.py`, `test_import_harness.py` and `test_validate_harness.py`
   still get fixture edits from #52 (`scope: scoped` rules gain `skill:`), so B9 keeps those
   tests byte-identical. Leaving `init` for after the chain is L12's choice, not a conflict.
2. **The render filter anchors moved.** Sync filters at `commands/_sync_render.py:182-183` and
   builds the registry at `:189-190`; `playbook render` builds it from the unfiltered list at
   `commands/render.py:194-195`.
3. **The chain spec records the divergence as intended.** `specs/prS-skills-context.md` §7.3,
   row "`playbook render <prompt> --format …`", says "the registry stays unfiltered, as today
   (`render.py:188-203`)". SPEC §6.2.5 ("Filtered rules … silently omitted from the prompt's
   appendix") and §12.7 (`--show-rules` prints `applies_if=False → OMITTED`) say the opposite,
   and L12 calls it a bug, so B1 follows SPEC; #54 must keep the filter (B.4.6).
4. **Validate's sub-modules are not in the chain.** `commands/_validate_links.py`,
   `_validate_hooks.py` and `_validate_context.py` are only cited by the chain spec; only
   `commands/validate.py` is edited. B2 migrates their config constants (after #62 since
   question 3, 2.3).
5. **The [metrics] disagreement cannot be fixed by raising at sync.** Sync reads the quality
   rows inside `write_runtime_outputs` (`commands/_sync_hooks.py:221`), which `_render_into`
   calls (`commands/sync.py:159`) after `dispatch_to_adapters` has already written into the repo
   (`sync.py:151-158`), and again in `finish_write` (`_sync_hooks.py:425`) after the lockfile is
   saved. Raising there leaves a half-written sync. A file that does not decode already fails
   earlier, in `SyncContext.from_repo`; only an invalid [metrics] *value* reaches the silent
   default (`_guard_config_quality.py:79`). B2 therefore unifies the reader and keeps the
   value-level policy; choosing a new one needs `commands/validate.py` or `_sync_hooks.py`, both
   chain files (question 2, resolved 2026-10-18 as option (a)).
6. **"15 private coercers re-coerce hook config" overstates it.** Of the 15 `_strings`/`_table`
   definitions, those in `session.py:44`, `stop/tools.py:105`, `handlers/compaction.py:269`,
   `handlers/_sink_writes.py:156`, `handlers/_control_plane_json.py:198` and
   `handlers/_manifest_diff.py:190` read session documents, ledger lines, tool payloads, edited
   JSON or TOML, not a hook's config. The config coercers are in 11 handlers (B.7.1), plus three
   copies of `_positive` (`notebooks.py:89`, `sensitive_reads.py:250`; `secret_content.py:297`
   as `_cap`) and a shared `strings` in `handlers/_secret_policy.py:148` the review missed. The
   empty-string rules really differ per hook (`destructive.py:227` drops `""`,
   `git_policy.py:257` keeps it, `network.py:215` drops blank strings,
   `guard_generated_outputs.py:209` raises), so B4 keeps each rule, written at the call site.
7. **The twin judges cannot move into `security/` as they are.** `security/` imports nothing
   from `hook_runtime` (every `security/*.py` import is stdlib or `security.*`), while
   `hook_runtime` imports `security` (`hook_runtime/config.py:41`). The judges import
   `hook_runtime.caps`, `.decision`, `._hosts`, `.globs`, `._git_parse` and
   `handlers._install_cmds` (`_dependency_tiers.py:19-23`, root `gate_scan.py:43-46`,
   `deser.py:29-37`), so a `security/` home would make the two packages import each other.
   N14 (the designer's B5) gives them public modules in a new `hook_runtime/judges/` package (question 1, resolved 2026-10-18).
8. **Some judge moves are chain-blocked.** `guard_config.py:107` (chain, #58) imports
   `handlers._notebook_check.NOTEBOOK_MAX_BYTES`, and `guard_config.py`, `evaluators/paths.py`
   and root `gate_scan.py:46` import `handlers._eval_paths`. Root `gate_scan.py` is pinned by
   `tests/unit/test_docs_lifecycle_hooks_spec.py:103` (chain) and by
   `tests/hook_runtime/test_import_budget_stop.py:29`. Harmonised (H1): each of these is a soft
   overlap (one import line in `guard_config.py`, one pin line in
   `tests/unit/test_docs_lifecycle_hooks_spec.py`, one import line in
   `tests/hooks/test_docstring_nonregression.py`), so the notebook check and the other judges move now
   in N14, `_eval_paths` and the gate-weakening judge in N15, and `_git_parse` gets its public name
   (`hook_runtime/git/parse.py`) in N18, each merged between two chain tickets.
9. **The destructive guard has no CLI twin.** Its second adapter is the Claude Code native deny
   rows (`adapters/_destructive_native.py:30-41` over
   `security/patterns.py:252 DESTRUCTIVE_NATIVE_PREFIXES`). Moving its judge would be relocation;
   the missing parity test is the new depth (B7). The probe at `ef19a0a`: the hook denies all 24
   forms (each of the 12 prefixes alone and followed by an argument).
10. **The ci cycle is a lazy run-time cycle, not type-only.** `_ci_commit_convention.py:115`
    imports `ci.StepRun` inside a function; `:35` and `_ci_report.py:19` are `TYPE_CHECKING`
    imports. Splitting `ci.py`'s step types out is optional tidy-up, not part of N8.
11. **Twins read policy as committed at the base revision.** `commands/gate_scan.py:114` and
    `commands/scan_secrets.py:176` decode `git.show(base, CONFIG_FILE)`, a git blob, not the
    worktree file, so a change cannot loosen its own check. `ConfigFiles` needs a document type
    that also decodes a blob (`CommittedDocument`, B.5).
12. **L2 keeps every entry-point group name.** The review's deletion of the `artifact_sources`,
    `state_sources`, `gates` and `rubrics` groups (`pyproject.toml:69-73`, `:97-107`) is dropped.
    `FileSystemStateSource` stays the `state_sources` entry until the post-chain StateSource
    decision.
13. **Measured availability in eval tasks.** `evals/scoring.py:138-150` builds its grading
    context without `tool_paths`, so `ruff_violations` (`builtins/ruff_violations.py:199-201`)
    is never available in an eval task, while the gate passes them
    (`evaluators/metrics_gate.py:490`). B8 keeps that outcome.
14. **The config filename.** 16 modules spell `.coding-agent-playbook.toml` or `.local.toml` in
    code (not docstrings): 13 outside `hook_runtime`, 3 inside (`handlers/_briefing_probes.py:50`,
    `_control_plane_paths.py:77-78`, `validate_then_sync_on_canonical_edit.py:61,70`).

### B.4 B1: `playbook render` omits included rules whose applies_if is false

#### B.4.1 Goal

`playbook render <prompt>` shows the included rules sync would deliver. Today it renders the
registry from every resolved rule (`commands/render.py:194`), so a rule whose `applies_if` is
false is inlined, while `--show-rules` on the same prompt prints it as `OMITTED`
(`render.py:164-172`) and sync drops it (`_sync_render.py:182`). Reproduced at `ef19a0a` with a
repo-local always rule `gated` (`applies_if: {has_framework: ["fastapi"]}`, body `GATED-BODY`)
included by a prompt `tidy` in a repo without fastapi: `render tidy --format prompt_continue`
prints `GATED-BODY`, and `--show-rules` prints `gated (<repo-local>, applies_if=False -> OMITTED)`.
The same holds for a malformed predicate (`has_framework: "fastapi"`).

#### B.4.2 Interface

No public interface changes. Inside `commands/render.py`:

```python
def _rule_applies(rule: Rule, ctx: SyncContext) -> bool:
    """Whether ``rule``'s ``applies_if`` holds for the repo; a malformed predicate does not.

    The one predicate rule of ``playbook render``: an empty predicate holds, and
    ``evaluate_predicate``'s ``ValueError`` (a predicate validate would reject) reads as
    false, as ``--show-rules`` has always printed it.

    Example: ``_rule_applies(rule, SyncContext.from_repo(repo))`` -> ``False`` without fastapi.
    """
```

- `_render_prompt` (`render.py:190-204`) renders
  `[render_rule_body(rule, context, base_env) for rule in ctx.rules_resolved if _rule_applies(rule, ctx)]`.
- `_show_rules` (`render.py:153-174`) replaces its inline predicate block (`:164-171`) with
  `applies = _rule_applies(rule, ctx)`. Its output is byte-identical.
- The comment at `render.py:276-277` says "Every applicable rule renders here".
- The artifact the user asked for is still rendered whatever its own `applies_if`
  (`orchestrator.py:23-25`, "render does not [filter]", stays true and is not edited).

`orchestrator.filter_applies_if` (`orchestrator.py:251-268`) is not reused: it raises
`ValueError` on a malformed predicate. Sync never meets one, because its validate gate runs
first (`sync.py:230-231`); `playbook render` has no validate gate and has never raised on one.

#### B.4.3 What moves behind the seam

The predicate rule of the command lives once (`_rule_applies`), where today `_show_rules` and
`_render_prompt` disagree. Dependency category: in-process.

#### B.4.4 Tests (written first; the first, third and fourth fail at `ef19a0a`)

In `tests/cli/test_render.py`, with a local helper
`_write_gated_rule(repo: Path, rule_id: str, predicate: str, body: str) -> None` that writes a
repo-local `scope: always` rule with `applies_if:\n  has_framework: <predicate>`:

- `test_render_prompt_omits_an_included_rule_whose_applies_if_is_false`: the B.4.1 repo;
  `rc == 0`, `"GATED-BODY" not in out`, `"## Reference rules" not in out`.
- `test_render_prompt_inlines_an_applicable_included_rule`: the same repo with
  `pyproject_extras={"dependencies": ["fastapi"]}`; `"GATED-BODY" in out` (the control that
  proves the first test can see an inlined rule).
- `test_render_prompt_agrees_with_show_rules`: one gated-off and one ungated included rule; the
  rule ids marked `INLINED` by `--show-rules` are exactly those whose bodies appear in the
  rendered prompt.
- `test_render_prompt_omits_an_included_rule_with_a_malformed_predicate`: predicate
  `"fastapi"` (a string, `detector.py:318` raises); `rc == 0` and the body is absent.

`tests/cli/test_sync_sandbox.py:119` keeps passing (its escaping rule has no `applies_if`); B1
updates its docstring to "every applicable rule". No test is deleted.

#### B.4.5 Docs

None: SPEC §6.2.5 and §12.7 already describe the fixed behaviour.

#### B.4.6 Acceptance criteria, blockers, risks

- The four tests pass; the first, third and fourth are red on the parent commit; `--show-rules`
  output is unchanged for every existing test; the gate passes on 3.12 and 3.13.
- Blockers: none. It must merge before #54 starts, because #54 rewrites `_render_prompt`'s
  `render_for` call (spec §7.4.5) and `_show_rules`' marker (§7.4.9).
- Coordination: the loop adds one line to issue #54's body: "`commands/render.py` filters
  included rules by `applies_if` since B1 (`_rule_applies`); keep that filter when passing
  `skill_references`, so the block lists only applicable rules; spec §7.3's 'stays unfiltered'
  row is superseded." B1's tests then guard #54.
- Risk: #54's rebase conflicts in `render.py:190-204` and `:164-173`; both are adjacent-line
  conflicts, and the four tests pin the merged result.

### B.5 B2: `ConfigFiles`, one interface for the two config files

#### B.5.1 Goal

The consumer repo's `.coding-agent-playbook.toml` and `.coding-agent-playbook.local.toml` get one
deep module. Today the reading, the per-file checks, the merge and the atomic write sit in the
config half of `sources/filesystem.py` (`:40-59`, `:162-218`, `:387-533`), the filename is
spelled in 13 modules outside `hook_runtime`, and five readers decode the committed file
themselves, each with its own error policy (`evaluators/metrics_gate.py:240-252`,
`_guard_config_quality.py:73-80`, `commands/gate_scan.py:142-156`,
`commands/scan_secrets.py:228-238`, `commands/_ci_policy.py:126-139`).

#### B.5.2 Interface (`src/coding_agent_playbook/config/files.py`, public; N2 created the module with `FileSystemStateSource`, B2 adds these types)

```python
CONFIG_FILENAME: Final = ".coding-agent-playbook.toml"
CONFIG_LOCAL_FILENAME: Final = ".coding-agent-playbook.local.toml"


@dataclass(frozen=True, slots=True)
class CommittedDocument:
    """The decoded committed config, read from the worktree or from a git blob at a revision.

    Example::

        >>> doc = CommittedDocument.decode(b"[hooks.x]\\nk = 1\\n", where="c.toml at abc123")
        >>> doc.table("hooks", "x")
        {'k': 1}
    """

    where: str
    data: Mapping[str, object]

    @classmethod
    def decode(cls, raw: bytes | None, *, where: str) -> CommittedDocument:
        """``raw`` decoded; ``None`` (no such file at that revision) is the empty document.

        Raises ``ConfigError`` naming ``where`` for bad TOML syntax, non-UTF-8 bytes or values
        nested past Python's recursion limit, with the texts ``sources/filesystem.py:208-218``
        prints today (``<where>: invalid TOML: …``, ``<where>: not UTF-8 text (…)``).
        """

    def table(self, *path: str) -> Mapping[str, object]:
        """The table at ``path`` (``{}`` when a segment is absent).

        Raises ``ConfigError("<where>: [hooks.x] must be a table, got 'on'")`` when a segment
        is present but not a table.
        """


class ConfigFiles:
    """The committed config and the personal local overrides of one consumer repo (SPEC §7.2).

    Example::

        >>> ConfigFiles(Path("/no/such/repo")).committed_table("metrics")
        {}
    """

    def __init__(self, repo_root: Path) -> None: ...

    @property
    def committed_path(self) -> Path: ...

    @property
    def local_path(self) -> Path: ...

    def has_committed(self) -> bool: ...

    def committed(self) -> CommittedDocument: ...

    def committed_table(self, *path: str) -> Mapping[str, object]: ...

    def local_overrides(self) -> dict[str, Any]: ...

    def load(self) -> Config: ...

    def load_committed(self) -> Config: ...

    def preview(self, document: Mapping[str, Any]) -> Config: ...

    def write_committed(self, document: Mapping[str, Any]) -> None: ...
```

| Method | No committed file | File does not decode | Checks | Merge |
| --- | --- | --- | --- | --- |
| `committed()` | `FileNotFoundError("missing .coding-agent-playbook.toml; run \`playbook init\`")` | `ConfigError` naming the file | `check_config_file` (today `_read_config_file`, `filesystem.py:174-187`) | none |
| `committed_table(*path)` | `{}` (team policy defaults) | `ConfigError` naming the file | only that each segment of `path` is a table | none |
| `local_overrides()` | `{}` when the local file is absent | `ConfigError` naming the local file | `check_config_file` on the local file | none |
| `load()` | `FileNotFoundError` as above | `ConfigError` | both files, each on its own | deep merge, `Config.from_dict(source=CONFIG_FILENAME)` |
| `load_committed()` | `FileNotFoundError` | `ConfigError` | committed file | none (P6) |
| `preview(document)` | not read | local file only | local file | `document` plus the local file, `source=CONFIG_LOCAL_FILENAME` |
| `write_committed(document)` | creates it | n/a | none | atomic write of `dump_toml(document)`; the committed file's only writer |

`committed_table` decodes only: a policy reader must not fail on a table it does not read (a
broken `[output]` must not stop `playbook metrics`). `committed()` keeps every per-file check,
because its callers build a `Config` from it.

#### B.5.3 What moves behind the seam

N2 has already moved these bodies into `config/files.py` (beside `FileSystemStateSource`); B2 puts them behind the new interface, unchanged in behaviour unless B.5.5 says otherwise:
`_deep_merge` (`sources/filesystem.py:40-59`), `_atomic_write_text` (`:162-171`),
`_read_config_file` (`:174-187`), `_decode_config_file` (`:190-218`), and the bodies of
`FileSystemStateSource.load_config`, `preview_config`, `_merged_config`,
`read_committed_config_table`, `load_primary_config`, `has_committed_config`,
`load_local_overrides`, `save_config`, `save_config_table` (`:401-533`). The decode of a blob at
the base revision (`commands/gate_scan.py:142-156`, `commands/scan_secrets.py:228-238`)
becomes `CommittedDocument.decode`. The committed-config reads of `_ci_policy`
(`_toml(repo_root / CONFIG_FILE)` at `:98,115`, with `_table` at `:137-139`) become
`committed_table`; its `pyproject.toml` read keeps `_toml`.

`FileSystemStateSource` stays: it is the `state_sources` entry point (L2), the chain file
`orchestrator.py:326-344,412,487` builds it, and `adapters/_prior_output.py:110-113` reads the
lockfile through it. Its config methods delegate to a `ConfigFiles` it builds in `__init__`;
it keeps `_CONFIG_FILENAME = CONFIG_FILENAME` and
`_CONFIG_LOCAL_FILENAME = CONFIG_LOCAL_FILENAME` as class attributes, because
`orchestrator.py:344` reads them; its lockfile methods (`:535-550`) are unchanged.

Dependency category: local-substitutable (two TOML files; tests use `tmp_path`, no fake).
Adapters at the seam: the worktree (`ConfigFiles`) and a git blob (`CommittedDocument.decode`).

#### B.5.4 Callers migrated (none is a chain file)

| Caller | Today | After |
| --- | --- | --- |
| `commands/_committed_config.py:22-30,47-141` | builders take `state: FileSystemStateSource`; `_COMMITTED = FileSystemStateSource._CONFIG_FILENAME` | `plan_first_config(files: ConfigFiles, config: Config)`, `plan_committed_update(files: ConfigFiles, update: Callable[[Config], Config])`, `plan_detector_cache_refresh(files: ConfigFiles, cache: dict[str, Any])`, `ConfigRewrite.save(files: ConfigFiles) -> Config`; `_COMMITTED = CONFIG_FILENAME` |
| `commands/init.py:43,80,196,234-238,316,485,548-568` | `FileSystemStateSource(...)`, its private filename attributes, `_GITIGNORE_LINE` literal | `ConfigFiles(repo_root)`, `files.local_path`, `CONFIG_LOCAL_FILENAME` |
| `commands/check.py:28,230-246` | `FileSystemStateSource` for `--refresh` | `ConfigFiles` |
| `commands/_ci_policy.py:27,32-44,89-139` | own `CONFIG_FILE`, `FileSystemStateSource.load_config`, own `_toml`/`_table` | `ConfigFiles.load()`, `committed_table("hooks")`, `committed_table("hooks", "commit_convention")`; fail-closed rules unchanged |
| `commands/_twin_policy.py:31,80,93` | own `CONFIG_FILE`, `is_file()` | `ConfigFiles(repo_root).has_committed()` |
| `commands/gate_scan.py:45,114,142-156` | own `CONFIG_FILE`, `_hook_table` | `CommittedDocument.decode(git.show(base, CONFIG_FILENAME), where=f"{CONFIG_FILENAME} at {base}").table("hooks", HOOK_ID)` |
| `commands/scan_secrets.py:71,176,228-238` | own `CONFIG_FILE`, `_guardrails_table` | the same, `.data.get("guardrails")` |
| `commands/_validate_links.py:31,45`, `_validate_hooks.py:149,184-185`, `_validate_context.py:57,69` | own literal or `FileSystemStateSource._CONFIG_*` | the constants |
| `commands/_sync_output.py:59-60`, `commands/_sync_orphans.py:52-53` | literals | the constants |
| `hook_policy/contract_set.py:85-86` | literal defaults | the constants |
| `evaluators/metrics_gate.py:94,100,228-252` (its N22 home, `metrics_gate/run.py`) | own `CONFIG_FILENAME` (exported), own `tomllib` read | `ConfigFiles(repo_root).committed_table("metrics")`; `CONFIG_FILENAME` leaves its `__all__` |
| `_guard_config_quality.py:38,66-87` | own `_CONFIG_FILE`, own read | `ConfigFiles(repo_root).committed_table("metrics")` |

Left on `FileSystemStateSource` or a literal until after #62 (B.13): `orchestrator.py` and
`guard_config.py:179-180` (chain files), and the three `hook_runtime` spellings (B.3 item 14),
which must not import the sync-side `config/` package; they take the names from the runtime's
guard_config schema module with the writer side.

#### B.5.5 Error policy, one per reader, stated

- `load_metrics_config(repo_root: Path) -> MetricConfig` keeps its signature. A `ConfigError`
  from `committed_table` becomes `MetricsGateUsageError(str(exc))` (exit 2, as today); a
  `ValueError` from `parse_metrics_config` keeps today's text
  `invalid [metrics] config in .coding-agent-playbook.toml: …`
  (`tests/evaluators/test_metrics_gate.py:233` and `tests/hooks/test_coverage_diff_gate.py:404`
  pin it). Changed on purpose: an undecodable file now reads
  `.coding-agent-playbook.toml: invalid TOML: …`, the text every other command prints, instead
  of `malformed .coding-agent-playbook.toml: …`; non-UTF-8 bytes report `not UTF-8 text`
  instead of being misreported as an invalid [metrics] value (today `UnicodeDecodeError` falls
  into `except ValueError`, `metrics_gate.py:249`); deep nesting no longer escapes as a
  `RecursionError` traceback.
- `read_quality_lint(repo_root: Path) -> QualityLint` keeps its signature and its sync-time
  policy: `ConfigError` or an invalid value returns `QualityLint()`. The new test pins it, so the
  decision of question 2 (resolved 2026-10-18 as option (a)) becomes a one-line, visible diff after #62.
- The twins at the base revision keep exit 2 for any config error (`ConfigError` is a
  `ValueError`, caught at `gate_scan.py:75` and `scan_secrets.py:137`). Their messages become
  `<file> at <rev>: invalid TOML: …` and `<file> at <rev>: [hooks.gate-weakening-guard] must be
  a table, got …`. Stricter on purpose: a committed `hooks = "x"` at the base now fails
  `gate-scan` (today `gate_scan.py:153` reads it as `{}`); sync already refuses that file.
- `_ci_policy` keeps failing closed (`:1-6`): a committed `hooks` that is not a table now makes
  `commit_convention_configured` return `True` (the step runs and reports the file), where
  today `_table` (`:137-139`) read it as absent.

#### B.5.6 Tests

`tests/config/test_files.py` (L8; N2 moved the `FileSystemStateSource` cases of `tests/unit/test_sources_filesystem.py` there, so "ported" means rewritten in place). Ported from `tests/unit/test_sources_filesystem.py` (the
right column is deleted there in the same PR):

| New test | Replaces (`tests/unit/test_sources_filesystem.py`) |
| --- | --- |
| `test_load_reads_the_committed_file` | `test_load_config_reads_primary_toml` (:150) |
| `test_load_merges_the_local_overrides_on_top` | `test_load_config_merges_local_overrides` (:161) |
| `test_load_deep_merges_nested_tables` | `test_load_config_deep_merges_nested_dicts` (:172) |
| `test_load_without_the_committed_file_says_run_init` | `test_load_config_missing_raises_fnf` (:206) |
| `test_load_committed_ignores_the_local_file` | `test_load_primary_config_ignores_local_overrides` (:212) |
| `test_load_committed_checks_the_committed_file` | `test_load_primary_config_checks_the_committed_file` (:228) |
| `test_write_committed_of_a_config_round_trips` | `test_save_config_emits_valid_toml` (:239), `test_save_then_load_config_roundtrip` (:309), `test_save_config_writes_exactly_config_to_dict` (:741) |
| `test_write_then_load_keeps_a_nested_detector_cache` | `test_save_then_load_config_roundtrip_with_nested_detector_cache` (:291) |
| `test_committed_ignores_the_local_file` | `test_read_committed_config_table_ignores_the_local_file` (:652) |
| `test_committed_without_the_file_says_run_init` | `test_read_committed_config_table_missing_raises_fnf` (:659) |
| `test_committed_error_names_the_committed_file` | `test_read_committed_config_table_error_names_the_committed_file` (:665) |
| `test_committed_never_reads_a_broken_local_file` | `test_read_committed_config_table_never_reads_a_broken_local_file` (:676) |
| `test_has_committed` | `test_has_committed_config` (:684) |
| `test_a_file_tomllib_cannot_read_is_a_config_error_naming_it` | same name (:709) |
| `test_a_table_header_a_thousand_levels_deep_loads` | same name (:723) |
| `test_write_committed_writes_every_entry_back_verbatim` | `test_save_config_table_writes_every_entry_back_verbatim` (:733) |
| `test_a_rewrite_keeps_unknown_keys_of_managed_tables` | same name (:757) |
| `test_preview_is_load_after_the_write_and_writes_nothing` | `test_preview_config_is_load_config_after_the_save_and_writes_nothing` (:775) |
| `test_every_read_of_a_misread_local_file_names_the_local_file` | same name (:808) |
| `test_a_misread_committed_table_is_refused_even_when_the_local_file_hides_it` | same name (:828) |
| `test_write_then_load_keeps_keys_that_need_quotes` | `test_save_then_load_config_keeps_keys_that_need_quotes` (:852) |

New behaviour, same file: `test_committed_table_is_empty_without_the_file`,
`test_committed_table_walks_nested_tables`,
`test_committed_table_refuses_a_non_table_naming_the_file_and_the_path`,
`test_committed_table_does_not_run_the_whole_file_checks` (a malformed `[output]` does not stop
a `[metrics]` read), `test_committed_document_decodes_a_git_blob_naming_the_revision`,
`test_committed_document_of_a_missing_blob_is_empty`,
`test_the_config_filenames_have_one_definition_outside_the_hook_runtime` (an AST walk of every
non-docstring string constant: the two names appear only in `config/files.py` and in the
allowlist `{"guard_config.py"}`, marked "until #62").

Kept in `tests/unit/test_sources_filesystem.py`: the lockfile, artifact-source, `dump_toml` and
entry-point tests, plus one new `test_filesystem_state_source_delegates_its_config_half` (a
`load_config()` equals `ConfigFiles(root).load()` on the same files).

Updated:
- `tests/unit/test_committed_config.py`: the builders take `ConfigFiles`; `_WRITERS` becomes
  `{"save_config", "save_config_table", "write_committed"}` and the single `_WRITERS_HOME`
  (`:232`) a tuple `("sources/filesystem.py", "config/files.py")`; the SPEC §7.2 invariant
  test (`:277-301`) keeps its three rules.
- `tests/evaluators/test_metrics_gate.py:229-243`: the `malformed` case expects the prefix
  `f"{CONFIG_FILENAME}: invalid TOML: "`, and a new `not_utf8` case (bytes `b"\xff"`) expects
  `not UTF-8 text`.
- `tests/cli/test_metrics.py:31`, `tests/cli/test_metrics_selection.py:19`,
  `tests/evaluators/test_metrics_gate.py:20` import `CONFIG_FILENAME` from `config.files`.
- `tests/unit/test_guard_config_quality.py`: add
  `test_read_quality_lint_keeps_the_defaults_for_an_invalid_metrics_value`.
- `tests/cli/test_gate_scan.py`: add `test_a_base_config_that_is_not_toml_exits_2_naming_the_revision`;
  `tests/cli/test_scan_secrets.py`: the same test name.

#### B.5.7 Docs

SPEC §7.2 (`SPEC.md:1380`), §7.1 (`:1264`) and §20.3 (`:3337`) name
`FileSystemStateSource.load_config`, `read_committed_config_table` and `save_config_table`; they
name `ConfigFiles.load`, `committed()` and `write_committed`, and §20.3 says that
`FileSystemStateSource` delegates its config half. None of these sections is edited by the
chain.

#### B.5.8 Acceptance criteria, blockers, risks

- `tests/config/test_files.py` passes; the 23 listed tests are replaced; the filename AST test
  passes; no module outside `config/`, `orchestrator.py` (`validation/context.py` after A5) and
  `adapters/_prior_output.py` imports
  `FileSystemStateSource`; every `tests/cli/test_init.py`, `test_check.py` and
  `test_config_errors.py` test passes unchanged; the gate passes on 3.12 and 3.13.
- Blockers: #62, lane 0, N2, N10.
- Risks: (1) the SPEC §7.2 invariant (local overrides never written back) must survive the
  builder signature change; the AST guard and `tests/cli/test_init.py` re-run tests pin it.
  (2) Three message texts change (B.5.5), pinned by the updated tests. (3) Until the post-chain
  StateSource decision, `FileSystemStateSource` and `ConfigFiles` are two ways in; only
  `orchestrator.py` (chain) and `adapters/_prior_output.py` (the lockfile) use the first.

### B.6 B3: typed reads of the guard_config.json pack tables

#### B.6.1 Goal

`guard_config.json` is the contract between sync (writer) and the hook runtime (reader). The
reader side parses the runtime keys once (`hook_runtime/config.py:223-248`) but hands every
other top-level table to handlers as a raw mapping (`GuardConfig.tables`, `config.py:129,247`),
and 25 sites re-parse tables by string. `stop_gate` alone is read at 9 sites, and its stage rows
are walked by four separate loops with slightly different rules (`stop/tools.py:48-55`,
`handlers/stop_ci_parity_gate.py:179-191`, `handlers/subagent_verify.py:235-247`,
`handlers/_ruff_buckets.py:402-404`). B3 gives the reader side one module that owns the shape of
every pack table.

#### B.6.2 Interface (`src/coding_agent_playbook/hook_runtime/config/guard_tables.py`, new, public, stdlib-only; in the package N16 created)

```python
#: guard_config.json's pack tables (specs/prK-hook-pack.md §E.0.5): one spelling for both sides.
STOP_GATE: Final = "stop_gate"
PROMPTS: Final = "prompts"
NOTEBOOKS: Final = "notebooks"
EVAL: Final = "eval"
PROTECTED: Final = "protected"
PRECOMMIT: Final = "precommit"
AUTO_SYNC: Final = "auto_sync"
FACTS: Final = "facts"
APPLICABILITY: Final = "applicability"
NETWORK: Final = "network"
RUFF: Final = "ruff"
#: ``[hooks.stop-ci-parity-gate] max_blocks`` default and range (§B.1); moved from
#: ``stop/coordinator.py:70-71`` and ``handlers/subagent_verify.py:91``.
DEFAULT_MAX_BLOCKS: Final = 2
MAX_BLOCKS_RANGE: Final = (1, 8)


@dataclass(frozen=True, slots=True, kw_only=True)
class StageRecord:
    """One well-formed ``stop_gate.stages`` row: a ``str`` name, the rest optional."""

    name: str
    owner: str | None
    tool: str | None  # a non-empty str, else None
    args: tuple[str, ...] | None  # ``str(arg)`` of a list, else None
    timeout_s: float | None  # an int or float > 0 that is not a bool, else None


@dataclass(frozen=True, slots=True, kw_only=True)
class VerifyCommand:
    """One ``stop_gate.verify_commands`` row with a non-empty str ``id`` and a list ``argv``."""

    id: str
    argv: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class StopGate:
    """``guard_config.stop_gate``, parsed once.

    Example::

        >>> GuardTables({"stop_gate": {"max_blocks": 99}}).stop_gate().max_blocks
        8
    """

    budget_s: float  # positive, else stop.stages.DEFAULT_BUDGET_S
    max_blocks: int  # clamped into MAX_BLOCKS_RANGE, else DEFAULT_MAX_BLOCKS
    stage_rows: tuple[Any, ...]  # the rendered rows verbatim: what an approval hashes
    stages: tuple[StageRecord, ...]
    verify_commands: tuple[VerifyCommand, ...]
    claim_patterns: tuple[str, ...]


@dataclass(frozen=True, slots=True, kw_only=True)
class ProtectedTable:
    """``guard_config.protected``: the hook artifacts, the layer resource roots, the lockfile ids."""

    hook_artifacts: tuple[str, ...]
    resource_roots: tuple[str, ...]
    artifact_ids: frozenset[str]


class GuardTables(Mapping[str, object]):
    """The pack tables of a trusted guard_config.json: still a read-only mapping, plus typed reads.

    Each accessor parses its table on first use and caches it; a missing or malformed
    table reads as its default, never raises (``load_guard_config`` already vouched for
    the bytes). The mapping half stays for out-of-tree handlers.

    Example::

        >>> GuardTables({"precommit": {"playbook_hook_ids": ["playbook-validate", 3]}}).precommit_hook_ids()
        ('playbook-validate',)
    """

    def __init__(self, raw: Mapping[str, object]) -> None: ...
    def stop_gate(self) -> StopGate: ...
    def prompt_output_contract(self, slash: str) -> tuple[str, ...]: ...
    def notebook_max_bytes(self, default: int) -> int: ...
    def eval_fixture_globs(self, default: Sequence[str]) -> tuple[str, ...]: ...
    def protected(self) -> ProtectedTable: ...
    def precommit_hook_ids(self) -> tuple[str, ...]: ...
    def auto_sync(self) -> bool: ...
    def facts(self) -> Mapping[str, object] | None: ...  # the decoded JSON object itself
    def applicability(self) -> tuple[Mapping[str, object], ...]: ...
    def network_mode(self) -> str | None: ...
```

`GuardConfig.tables` (`config.py:129`) changes type from `Mapping[str, Any]` to `GuardTables`,
built at `config.py:247` from the same `MappingProxyType`. `GuardConfig` is built only there
(tests use `parse_guard_config` or a cast fake), so the change is contained.
`GatePolicy.from_table(table: object)` (`stop/coordinator.py:95-106`) is replaced by
`GatePolicy.from_gate(gate: StopGate) -> GatePolicy` (`budget_s`, `max_blocks`,
`stages=gate.stage_rows`); `stages_sha256` is unchanged, so every stored execution approval
still matches.

#### B.6.3 Sites migrated (22 of 25; the other 3 are in chain files)

| Accessor | Sites today (paths under `hook_runtime/`) |
| --- | --- |
| `stop_gate()` | `_verify_tag.py:67-74`, `stop/tools.py:48-55`, `handlers/stop_ci_parity_gate.py:110,181-191`, `handlers/coverage_diff_gate.py:281`, `handlers/_verify_claim.py:56,107-109,128-131`, `handlers/subagent_verify.py:183,237-247` |
| `prompt_output_contract(slash)` | `handlers/output_contract.py:133-138` |
| `notebook_max_bytes(NOTEBOOK_MAX_BYTES)` | `handlers/sensitive_reads.py:244-247`, `handlers/notebooks.py:79-82` |
| `eval_fixture_globs(FIXTURE_GLOBS)` | `handlers/guard_eval_fixtures.py:115-119` |
| `protected()` | `handlers/validate_then_sync_on_canonical_edit.py:157-158`, `handlers/eval_task_authoring_lint.py:186-188`, `handlers/resync_on_detector_input_change.py:177-180` |
| `precommit_hook_ids()` | `handlers/precommit_bypass.py:99-101`, `handlers/_metrics_pass.py:321-323` |
| `auto_sync()` | `handlers/_source_changed.py:117` |
| `facts()` | `handlers/resync_on_detector_input_change.py:99`, `handlers/dependencies.py:106` |
| `applicability()` | `handlers/resync_on_detector_input_change.py:153-159` |
| `network_mode()` | `handlers/_briefing_probes.py:212-214` |

Left until after #62: `handlers/ruff_feedback.py:230` and `handlers/_ruff_buckets.py:335,402`
(#55). The defaults that live with their hook (`NOTEBOOK_MAX_BYTES`, `FIXTURE_GLOBS`) are passed
in, so `guard_tables.py` imports no handler module.

Tightened on rows sync never writes: a `bool` is never a `timeout_s`; a non-list `argv` is
skipped rather than iterated (`_verify_tag.py:72` iterates any value today); a non-str
`claim_patterns` item is skipped rather than `str()`-ed (`_verify_claim.py:56-58`).

#### B.6.4 What moves behind the seam

The shape and defaults of every pack table on the reader side, including `GatePolicy`'s parse
rules (`_budget`, `coordinator.py:371-375`; the `max_blocks` clamp, `:99-103`) and the stage-row
rules of four loops. Dependency category: in-process (a decoded JSON object). The writer side
(`guard_config.py`, chain #58) adopts the table-name constants after #62.

#### B.6.5 Tests

New `tests/hook_runtime/test_guard_tables.py`:
- `test_accessors_read_what_sync_renders`: a `tests/hooks/pack_repo.PackRepo` with the Stop
  coordinator, the stage hooks and the pack tables installed; `load_guard_config` on it; each
  accessor equals the rendered table's values (the writer-to-reader round trip).
- `test_a_missing_table_reads_as_its_default` (parametrized over the ten accessors).
- `test_a_malformed_table_reads_as_its_default` (a non-table, wrong item types).
- `test_stage_records_skip_rows_without_a_str_name`, `test_a_bool_is_never_a_timeout`,
  `test_verify_commands_need_an_id_and_a_list_argv`.
- `test_max_blocks_is_clamped_into_its_range`, `test_budget_defaults_when_not_positive`.
- `test_gate_policy_from_gate_hashes_the_rows_verbatim`
  (`GatePolicy.from_gate(gate).stages_sha256() == sha256_of_json(list(gate.stage_rows))`).
- `test_tables_stay_a_read_only_mapping` (`cfg.tables.get("x")` and `cfg.tables["stop_gate"]`).
- `test_pack_tables_are_read_only_through_guard_tables`: an AST walk of `hook_runtime/` finds no
  `.tables.get(` or `.tables[` outside `guard_tables.py`; allowlist
  `{"handlers/ruff_feedback.py", "handlers/_ruff_buckets.py"}`, marked "until #62".

Updated: `tests/hook_runtime/test_verify_tag.py:65,96,105` build their fake with
`tables=GuardTables({...})`; `tests/hooks/test_coverage_diff_gate.py:71` uses
`GatePolicy.from_gate(GuardTables({"stop_gate": table}).stop_gate())`; the doctest
`coordinator.py:86` moves to `StopGate`. No test is deleted: the handler tests already pin each
site's behaviour and must pass unchanged.

#### B.6.6 Docs, acceptance, blockers, risks

- Docs: none in SPEC (the pack tables are documented in `specs/prK-hook-pack.md`, a record).
- Acceptance: the new tests pass; every `tests/hooks/` and `tests/hook_runtime/` test passes
  unchanged except the three listed updates; `test_import_budget.py` and
  `test_latency_budget.py` pass unchanged (`guard_tables.py` imports only the stdlib); the
  gate passes.
- Blockers: #62, N16 (the move of `hook_runtime/config.py` into `hook_runtime/config/` lands first, L13). B4a starts after B3 merges.
- Risks: `hook_runtime/config/guard_config.py` (today's `hook_runtime/config.py`) imports `guard_tables.py`, so it loads on every dispatch: it
  must stay stdlib-only, with no `tomllib` and no `hook_runtime.globs` (callers compile the
  globs it returns); the existing budget tests catch a regression. `stop_gate()` imports
  `stop.stages.DEFAULT_BUDGET_S` inside the method (only Stop-stage callers pay for it), so
  `guard_tables.py` never imports `stop.*` at module level.

### B.7 B4: each builtin reads its config through its CONFIG_SCHEMA (B4a, B4b)

#### B.7.1 Goal

A builtin's merged `handler.config` reaches it as `Mapping[str, Any]`
(`hook_runtime/registry.py:183`, built at `_pipeline.py:242`), and each handler re-coerces it with
its own helper. Eleven handlers outside the chain carry such helpers:

| Handler | Key | Rule today |
| --- | --- | --- |
| `destructive.py` | `protected_branches`, `safe_rm_dirs` | `:161,185,227`: a non-list is the default; drop non-str and `""` |
| `git_policy.py` | `placeholder_identity`, `never_commit_globs` | `:156,182,257`: a non-list is the default; drop non-str, keep `""` |
| `git_policy.py` | `ask_on_default_branch`, `push_requires_green` | `:166` `is False`, `:203` `is not True` |
| `network.py` | `allowed_hosts`, `gateway_hosts` | `:93,215`: drop non-str and blank strings |
| `network.py` | `webfetch_max_query_chars`, `mode` | `:94-95` an int ≥ 0 (never a bool) else 256; `:117` outside `MODES[1:]` is inert |
| `guard_generated_outputs.py` | `extra_protected`, `restore_commands` | `:209-213`: anything but a list of str raises `ValueError` naming the key |
| `exfil.py` | `allowed_hosts` | `:178`: `str(h)` of each str item of `value or ()` (a string value is iterated per character) |
| `sensitive_reads.py` | `allow_globs`, `deny_globs`, `csv_max_sample_bytes`, `mode` | `:98-99` `_secret_policy.strings` (drop non-str and `""`); `:104,250` positive int else default; `:181` |
| `notebooks.py` | `max_cell_output_kb` | `:83-84,89`: a positive int (never a bool) else 64 |
| `secret_content.py` | `max_scan_bytes` | `:120,216,297`: a positive int (never a bool) else 1 MiB |
| `compaction.py` | `max_prompts` | `:273-277`: a positive int, capped at the ceiling, else the default |
| `subagent_verify.py` | `max_blocks`, `agent_types`, `stages` | `:184-186` clamp into 1..8; `:175` a non-empty list else every type; `:204` a non-empty list else `DEFAULT_STAGES` |
| `tests_nudge.py` | `source_roots`, `test_roots`, `block` | `:168-172` drop non-str and `""`, strip `/`, empty is `(default,)`; `:149` `is True` |

B4 gives them one reader that knows the declared kind (the same `CONFIG_SCHEMA` validate checks
consumers against, H21), while each handler keeps its own emptiness and range rule, written
explicitly at the call site. The dispatcher, `HandlerContext` and `registry.py` (a chain file)
are not touched: a handler builds the view from its own schema.

#### B.7.2 Interface (`src/coding_agent_playbook/hook_runtime/config/hook_config.py`, new, public, stdlib-only)

```python
type Blanks = Literal["keep", "drop_empty", "drop_blank"]
type Bound = Literal["default", "clamp"]


class HookConfig:
    """A builtin's merged ``handler.config``, read against its own ``CONFIG_SCHEMA``.

    A value of the wrong kind reads as the caller's default (validate refuses it in a
    consumer's ``[hooks.<id>]``, H21; the digest check keeps the file as sync wrote it). Reading
    a key the schema does not declare raises ``KeyError`` naming the key and the declared keys,
    and a read method that does not match the declared kind raises ``TypeError``: both are
    programming errors the handler's own tests surface.

    Example::

        >>> config = HookConfig({"protected_branches": ["main", ""]}, CONFIG_SCHEMA)
        >>> config.strings("protected_branches", ("main", "master"))
        ('main',)
    """

    def __init__(self, raw: Mapping[str, object], schema: Mapping[str, ConfigKey]) -> None: ...

    def flag(self, key: str, default: bool) -> bool: ...

    def choice(self, key: str, default: str) -> str:
        """The value when it is one of the key's declared ``ConfigKey.order``, else ``default``."""

    def integer(
        self,
        key: str,
        default: int,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        below: Bound = "default",
        above: Bound = "default",
    ) -> int:
        """An int that is not a bool; out of range reads as ``default`` or is clamped."""

    def strings(
        self,
        key: str,
        default: tuple[str, ...] = (),
        *,
        blanks: Blanks = "drop_empty",
        strict: bool = False,
    ) -> tuple[str, ...]:
        """The str items of a list (a non-list is ``default``); ``strict`` raises ``ValueError``
        naming the key for anything but a list of str."""

    def value(self, key: str) -> object:
        """The raw value of a ``regex`` or ``table`` key, for its own row parser."""
```

Kind compatibility: `flag` ↔ `boolean`; `choice` ↔ `string`; `integer` ↔ `integer`/`number`;
`strings` ↔ `list`; `value` ↔ `regex`/`table`.

The rules of B.7.1 map one to one: `destructive` uses `strings(k, DEFAULT, blanks="drop_empty")`;
`git_policy` `strings(k, DEFAULT, blanks="keep")`, `flag("ask_on_default_branch", True)`,
`flag("push_requires_green", False)`; `network` `strings(k, blanks="drop_blank")`,
`integer("webfetch_max_query_chars", 256, minimum=0)`, `choice("mode", "off")`;
`guard_generated_outputs` `strings(k, blanks="keep", strict=True)`; `exfil`
`strings("allowed_hosts", blanks="keep")` (a string value now reads as the default, a value
validate already refuses); `notebooks`, `secret_content`, `sensitive_reads` `integer(k, DEFAULT,
minimum=1)`; `compaction` `integer("max_prompts", DEFAULT_MAX_PROMPTS, minimum=1,
maximum=_MAX_PROMPTS_CEILING, above="clamp")`; `subagent_verify`
`integer("max_blocks", DEFAULT_MAX_BLOCKS, minimum=1, maximum=8, below="clamp", above="clamp")`
with `MAX_BLOCKS_RANGE` from B3; `tests_nudge` `strings(k, blanks="drop_empty")` then its
`/`-strip; `destructive`, `exfil` and `conventions` pass `value("extra_rows")`/`value("rules")`
to their row parsers.

- **B4a** migrates the eleven handlers of B.7.1 and deletes their helpers: `destructive._strings`,
  `git_policy._strings`, `network._strings`, `guard_generated_outputs._strings`,
  `notebooks._positive`, `sensitive_reads._positive`, `secret_content._cap`,
  `compaction._max_prompts`, `tests_nudge._roots` (its strip stays inline) and
  `subagent_verify._MAX_BLOCKS_RANGE`. `_secret_policy.strings` stays for its non-config callers.
  `dependencies` is excluded: its config reader is the shared judge `dependency_policy`
  (`_dependency_tiers.py:90-111`), which the twin calls with a merged dict, and stays the one
  reader for both adapters.
- **B4b** migrates the remaining `ctx.config` reads of non-chain handlers (`output_contract.py:124`,
  `commit_convention.py:94,155`, `quality_metrics.py:205`, `coverage_diff_gate.py:189,254`,
  `precommit_bypass.py:133`, `activity_log.py:92,95`, `conventions.py:70`,
  `control_plane_guard.py:121`, `_exec_stages.py:157`, `stop_sweep.py:125`) and adds the guard
  test below. A shared stage helper reads through the schema that declares its key:
  `_exec_stages.py:157` uses `stop_ci_parity_gate.CONFIG_SCHEMA` (`tests_scope`, `:68`), so under
  `subagent_verify`'s config the key is absent and reads as its default, as today. Chain files
  keep raw reads until after #62: `ruff_feedback.py:137,232`, `docstring_nonregression.py:187`.

#### B.7.3 What moves behind the seam

Kind checking, the bool-is-not-an-int rule, the list-of-str filtering and the range rules, once.
Dependency category: in-process. Adapters: every builtin handler. Out-of-tree handlers (the
`coding_agent_playbook.hook_handlers` group) keep receiving the same `Mapping` and may build a
`HookConfig` from their own schema.

#### B.7.4 Tests

New `tests/hook_runtime/test_hook_config.py` (B4a):
`test_flag_reads_only_a_bool`, `test_choice_outside_the_declared_order_is_the_default`,
`test_integer_never_counts_a_bool`, `test_integer_below_the_minimum_is_the_default`,
`test_integer_clamps_when_asked` (parametrized `below`/`above`),
`test_strings_drop_empty_by_default`, `test_strings_keep_blanks_when_asked`,
`test_strings_drop_blank_strings_when_asked`, `test_strings_of_a_non_list_is_the_default`,
`test_strict_strings_raise_naming_the_key`, `test_value_returns_regex_rows_verbatim`,
`test_an_undeclared_key_raises_naming_the_declared_keys`,
`test_a_read_that_does_not_match_the_declared_kind_raises`. B4b adds
`test_in_tree_builtins_read_their_config_through_hook_config` (an AST walk of
`hook_runtime/handlers/` and `hook_runtime/stop/` finds no `ctx.config.get(`, `config.get(` on a
handler config parameter, or `ctx.config[`; allowlist `{"ruff_feedback.py",
"docstring_nonregression.py"}`, marked "until #62").

Every handler test in `tests/hooks/` and `tests/hook_runtime/` must pass unchanged; those
tests pin each rule of B.7.1. For the two rules no test covers today, B4a adds regression
tests through the real dispatch:
`tests/hooks/test_destructive_command_guard.py::test_an_empty_safe_rm_dir_does_not_make_the_repo_root_safe`
(`safe_rm_dirs = [""]`, `rm -rf .` still denies) and
`tests/hooks/test_guard_generated_outputs.py::test_a_non_string_extra_protected_entry_fails_the_hook`
(the handler raises, as today, and the failure policy decides). `git_policy`'s keep-empty rule
is pinned at the `HookConfig` level (`test_strings_keep_blanks_when_asked`).

#### B.7.5 Docs, acceptance, blockers, risks

- Docs: none now. The sentence for SPEC §6.6.7's handlers paragraph (`SPEC.md:1199`), "At run
  time a builtin reads its config only through `HookConfig`, against the same `CONFIG_SCHEMA`; a
  value of the wrong kind reads as that key's default", waits for #62, because #57 edits §6.6.7
  (B.13).
- Acceptance: the new tests pass; the ten helpers listed above are gone (B4a); the AST guard
  passes (B4b); the budget tests pass unchanged; the gate passes.
- Blockers: #62, B3 (same files) and N14 (the judge moves land first).
- Risks: (1) A handler reading a key its schema forgot now raises; the guard test plus each
  handler's tests surface it in this PR, and the failure policy (fail-open or closed per hook)
  applies if one escapes. (2) `exfil`'s per-character iteration of a string value is fixed, a
  behaviour change on a value validate refuses. (3) `hook_config.py` loads on every hot path:
  stdlib-only, imports `hook_runtime.config.keys` (N16's name for `_config_keys`) only under `TYPE_CHECKING`.

### B.8 B5, folded into N14 (move only): public homes for the twin-shared judges

N14 (section 7.4) carries this design and widens it to every twin-shared judge: besides the rows below it moves `hook_runtime/_hosts.py`, `cutover.py`, `handlers/_cli_words.py`, `handlers/_install_cmds.py` and `handlers/_notebook_check.py` to `hook_runtime/judges/` (`hosts.py`, `commit_cutover.py`, `cli_words.py`, `install_commands.py`, `notebook_check.py`), because the notebook check is a soft overlap, not a chain block. Since question 3 was resolved (2.3), N14 runs after #62 as a whole: the judges leave `hook_runtime/handlers/`, a package the open chain edits.

#### B.8.1 Goal

No guard twin imports a `hook_runtime.handlers._*` module. Today the twins reach into the
handlers' private judges: `commands/check_deps.py:31,38`,
`commands/scan_sinks.py:32-33` (and `SinkTable`, `new_sink_calls` through `deser.py`'s re-export
of `_sink_scan`, `deser.py:31-35`), `commands/check_notebooks.py:24`. A judge shared by a guard
hook and its guard twin gets one public module both adapters import. (The sync-side writer's
own private imports, `guard_config.py:102-107`, leave with the writer side after #62.)

#### B.8.2 The moves (git mv, import rewrites, no code change)

| From | To |
| --- | --- |
| `hook_runtime/handlers/_dependency_tiers.py` | `hook_runtime/judges/dependency_tiers.py` |
| `hook_runtime/handlers/_manifest_diff.py` | `hook_runtime/judges/manifest_diff.py` |
| `hook_runtime/handlers/_sink_scan.py` | `hook_runtime/judges/sink_scan.py` |
| `hook_runtime/handlers/_notebook_cells.py` | `hook_runtime/judges/notebook_cells.py` |
| `hook_runtime/handlers/_notebook_check.py` | `hook_runtime/judges/notebook_check.py` (N14) |
| `deser.trusted_artifact_line` (`handlers/deser.py:117-131`) | `hook_runtime/judges/sink_scan.py` |
| (new) | `hook_runtime/judges/__init__.py`, docstring only |
| `tests/hook_runtime/test_manifest_diff.py`, `tests/hook_runtime/test_sink_scan.py` | `tests/hook_runtime/judges/` |

Imports rewritten: `handlers/dependencies.py`, `handlers/deser.py`, `handlers/_sink_writes.py`,
`handlers/_sink_regex.py`, `handlers/_notebook_check.py`, `handlers/notebooks.py`,
`handlers/stop_sweep.py:54,187,195-197` (`SinkTable`, `trusted_artifact_line`),
`commands/check_deps.py`, `commands/scan_sinks.py` (`SinkTable`, `new_sink_calls`,
`trusted_artifact_line` and `SinkHit` now from `judges.sink_scan`, not via `deser`),
`tests/hooks/test_dependency_allowlist_guard.py`, the two moved tests. Handler module
paths are unchanged, so `hook_runtime/registry.py:69-124` (chain) and every string-bound stage
target stay as they are; no budget test pins these four module names (checked in
`test_import_budget.py` and `test_import_budget_stop.py`).

Why `hook_runtime/judges/` and not `security/`: B.3 item 7 (question 1, resolved 2026-10-18). The judges speak the
runtime's vocabulary (`Decision`, the `caps` sanitizers, `GlobSet`); a second adapter needs only a
public module, which the twins already reach through an existing edge (`commands/_git_base.py:17-19`
imports `hook_runtime.git`, `.paths`, `.proc`).

#### B.8.3 Acceptance, blockers, risks

- `git diff -M --stat` shows only renames plus import lines;
  `rg "hook_runtime\.handlers\._" src/coding_agent_playbook/commands` prints nothing; the gate
  passes.
- Blockers: #62, lane 0.
- Risk: a later PR re-adds a private import; B6 adds the contract that stops it.

### B.9 B6: one run skeleton for the guard twins

#### B.9.1 Goal

Six twins copy the same `run()` skeleton: resolve the repo root, open git, map `GitError` and
`ValueError` (and `OSError` for two) to `error: <message>` on stderr with exit 2, print text or
JSON, return the report's code (`commands/gate_scan.py:62-80`, `scan_sinks.py:89-109`,
`scan_secrets.py:116-142`, `check_commit_trailers.py:40-64`, `check_notebooks.py:42-63`,
`check_deps.py:56-77`). B6 makes the guard twins' shared contract one function.

#### B.9.2 Interface (`commands/twins/_runner.py`, new; private to `commands.twins`)

```python
#: What a twin may raise that means "cannot check": exit 2, one ``error:`` line.
TWIN_ERRORS: Final = (GitError, ValueError)


@dataclass(frozen=True, slots=True)
class TwinOutcome:
    """A twin's verdict: its exit code and the text it prints (nothing when empty)."""

    exit_code: int
    output: str


def run_twin(
    repo_root: str | None,
    scan: Callable[[Path], TwinOutcome],
    *,
    errors: tuple[type[Exception], ...] = TWIN_ERRORS,
) -> int:
    """Resolve ``repo_root`` (cwd by default), run ``scan``, print its output, return its code.

    An exception in ``errors`` prints ``error: <exc>`` on stderr and returns 2, the guard
    twins' shared contract (specs/prK-hook-pack.md §E.4).

    Example::

        >>> run_twin(None, lambda root: TwinOutcome(0, ""))
        0
    """
```

Each twin's `run(args, *, git=None) -> int` becomes one `run_twin` call; its scan function builds
the text with its existing `_text`/`_json`. The usage checks that print `error: …` today
(`scan_secrets.py:126-130`, `check_commit_trailers.py:50-52`, `check_notebooks.py:56-59`) raise
`ValueError` inside the scan with the same text, so stderr is byte-identical.
`check_commit_trailers` and `check_deps` pass `errors=(*TWIN_ERRORS, OSError)` (today's
`check_commit_trailers.py:58`, `check_deps.py:71`).

B6 also adds an import-linter forbidden contract to lane 0's test (contract id `twins-use-judges`):
`source_modules = ["coding_agent_playbook.commands.twins"]` must not import
`coding_agent_playbook.hook_runtime.handlers`, with `allow_indirect_imports = "true"`, and no
exception: N14 made the notebook check public too. The contract checks direct twin-to-handler
imports, the property N14 establishes. It is scoped to `commands.twins` and allows indirect chains
because a forbidden contract otherwise follows chains through modules that B6 does not own and that
reach handlers until later PRs (grimp on the baseline: `commands.sync > guard_config >
handlers._control_plane_paths` and `commands._sync_hooks > guard_config > handlers._eval_paths`
until GC-1 after #62; `commands.gate_scan > gate_scan > handlers._eval_paths`, `commands.eval >
evaluators.types > handlers._eval_paths` and `commands._ci_policy > evaluators.metrics_gate > ... >
handlers._eval_paths` until N15). Indirect edges stay covered by the layer and private-modules
contracts.

#### B.9.3 What moves behind the seam, tests, docs

- Behind the seam: repo-root resolution, the error-to-exit-2 mapping and the print rule.
  Dependency category: in-process.
- New `tests/cli/test_twin_contract.py`:
  `test_every_twin_outside_a_git_repository_exits_2_with_one_error_line` (parametrized over the
  six twins, a `tmp_path` with no `.git`: stdout empty, stderr one `error: ` line) and
  `test_twins_with_a_format_flag_print_json_when_asked` (gate-scan, scan-sinks, scan-secrets on
  a `FakeGit`). Every existing `tests/cli/test_<twin>.py` passes unchanged. No test is deleted.
- Docs: none.

#### B.9.4 Acceptance, blockers, risks

- Each twin's `run` is at most 15 lines; the contract tests pass; the forbidden contract passes
  with no exception; the gate passes.
- Blockers: #62, N14, N8.
- Risk: a twin printing an empty line today where `output` is now empty; the existing CLI tests
  pin stdout exactly.

### B.10 B7: the destructive guard denies every native deny prefix

#### B.10.1 Goal

`security/patterns.py:244-251` promises that the native `permissions.deny` rows are a subset of
the guard: "While the guard is on, the claude_code adapter also renders them as native
`permissions.deny` `Bash(<prefix> *)` rows". Only `tests/adapters/test_claude_code_hooks.py:493-495`
covers the rows, and only their rendering. B7 pins parity. At `ef19a0a` the probe ran the shipped
`HOOK.md` through `simulate` for each of the 12 prefixes alone and followed by `" x"`: all 24
deny, so B7 is a test-only PR.

#### B.10.2 Test

In `tests/hooks/test_destructive_command_guard.py` (beside `GOLDEN`, using its `repo`, `_bash`
and `_decision`):

```python
@pytest.mark.parametrize("suffix", ["", " x"])
@pytest.mark.parametrize("prefix", DESTRUCTIVE_NATIVE_PREFIXES)
def test_the_hook_denies_every_native_prefix(
    repo: PackRepo, deps: Deps, prefix: str, suffix: str
) -> None:
    """A native ``Bash(<prefix> *)`` row is never stricter than the hook (security/patterns.py:244)."""
    assert _decision(_bash(repo, deps, prefix + suffix)) is Decision.DENY
```

Acceptance: 24 cases pass; the gate passes. Blockers: none. Risk: none (a future prefix that the
hook only asks for fails here, by design).

### B.11 B8: one measuring pass for eval tasks and the metrics gate

#### B.11.1 Goal

The grading kernel measures twice. `evals/scoring.py` and the metrics gate each walk the tree
(`scoring.py:65,301-316` and `_metrics_inputs.py:30,105-115`: the same `IGNORED_DIRS`, two
walks), each run the per-file loop (`scoring.py:275-298`; `_metrics_inputs.SourceMeter`,
`:172-230`) and the suite loop (`scoring.py:321-339`; `_metrics_suite.SuiteRun.measure`,
`:85-122`), and each builds a stand-in context before grading (`scoring.py:240-266`
`_availability_module`/`_availability_project`; `metrics_gate.py:465-491` `_grading_ctx`), only
because a metric-backed check asks the measure-time rule at grade time
(`evaluators/check.py:265-267` → `metric.py:87-100`). B8 gives the kernel one measuring module
whose result also decides grade-time availability.

#### B.11.2 Interface (`src/coding_agent_playbook/grading/measuring.py`, new, public)

```python
IGNORED_DIRS: Final[frozenset[str]]  # moved from _metrics_inputs.py:30; scoring.py:65 deleted
SUITE_LABEL: Final = "suite"  # moved from _metrics_suite.py:40; scoring.py:70 deleted


def python_files(root: Path) -> list[Path]:
    """Every ``*.py`` under ``root``, sorted, skipping dot dirs and ``IGNORED_DIRS``.

    Paths are ``root`` joined with the relative path, never resolved, so a label
    ``relative_to(root)`` always works (a macOS ``/tmp`` -> ``/private/tmp`` link included).
    """


@dataclass(frozen=True, slots=True)
class TreeMeasurements:
    """One tree measured file by file: the rows, the files skipped and why, the measured count."""

    measurements: tuple[Measurement, ...]
    skipped: tuple[tuple[str, str], ...]
    measured_count: int


class SourceMeter:
    ...  # moved from _metrics_inputs.py:172-230; takes
    # setup: MeasureSetup in place of its tool_paths,
    # max_file_bytes and tool_setup fields


def decode_source_blob(raw: bytes, max_file_bytes: int = MAX_FILE_BYTES) -> str | None:
    ...
    # moved from _metrics_inputs.py:233-251


def measure_tree(root: Path, meter: SourceMeter) -> TreeMeasurements:
    """Measure every ``python_files(root)`` file, labelled root-relative (posix)."""


def measure_suite(
    project: ProjectHandle, metrics: Sequence[Metric], setup: MeasureSetup
) -> list[Measurement]:
    """Run every execution metric over one handle (the suite runs once).

    Raises the ``RuntimeError`` a metric raises; the caller applies its policy (eval scoring
    measures nothing, the gate raises ``MetricsGateUsageError``), as today.
    """


def measured_metrics(metrics: Iterable[Metric], setup: MeasureSetup) -> frozenset[str]:
    """The names of the non-judge ``metrics`` that can run with ``setup``: the pass's promise."""
```

In `grading/types.py` (today `evaluators/types.py`), so that `types.py` never imports
`measuring.py`:

```python
MAX_FILE_BYTES: Final = 1_000_000  # moved from _metrics_inputs.py:43


@dataclass(frozen=True, slots=True, kw_only=True)
class MeasureSetup:
    """What a measuring pass may run: the tools, how they run, the per-file byte cap."""

    tool_paths: Mapping[str, str] = field(default_factory=dict)
    tool_setup: ToolSetup = field(default_factory=ToolSetup)
    max_file_bytes: int = MAX_FILE_BYTES
```

`EvalContext` (`types.py:332-386`) gains `measured_metrics: frozenset[str] = frozenset()`.
`Metric` (`metric.py:47`) gains `runnable(self, setup: MeasureSetup) -> bool`, the environment
half of today's `available`: the base checks `requires` (`find_spec`), `ruff_violations` needs
`setup.tool_paths["ruff"]`, `maintainability` and `file_sloc` need radon. Each `available(ctx)`
keeps its measure-time slot check and calls `runnable` for the environment half, so the rule is
written once.

`_MetricCheck.available` (`check.py:265-267`) becomes:

```python
def available(self, ctx: EvalContext) -> bool:
    """A judged metric needs its judge; any other was measured by this run's pass, or not."""
    if self.metric.needs_judge:
        return self.metric.available(ctx)
    return self.metric.name in ctx.measured_metrics
```

`measured_metrics` holds every non-judge metric the compiled tree references (nested rubrics'
leaves included) that is runnable, whether or not a file produced a row. The tree walk is
`referenced_metrics(checks: Sequence[Check]) -> list[Metric]`, moved from
`scoring._referenced_metrics` (`scoring.py:201-232`) into `measuring.py`; it gains a
`nested: bool` flag, because measuring still treats a nested `Rubric` as one judged metric
while the availability set descends into it. The gate's set is its selected static and
execution metrics that are runnable (`_Measured.static`/`.execution`, `metrics_gate.py:216-226`).
That keeps today's outcomes: a check over zero files still grades vacuously
(`check.py:341-343`), and `ruff_violations` stays unavailable in eval tasks (B.3 item 13).

#### B.11.3 The two callers

- `evals/scoring.py`: `_static_measurements`, `_iter_py_files`, `_execution_measurements`,
  `_availability_module`, `_availability_project`, `_IGNORED_DIRS`, `_SUITE_LABEL` are deleted.
  `score` measures the candidate tree and the `setup/` snapshot with
  `measure_tree(root, SourceMeter(metrics=static, setup=MeasureSetup()))`, runs `measure_suite`
  on one candidate handle it also passes as `ctx.project` (so a nested rubric's own
  availability, `rubric.py:142-163`, sees a real project), and sets
  `measured_metrics=measured_metrics(referenced, MeasureSetup())` on its grading context, whose
  `module` is now `None`.
- The metrics gate: `discover_targets` (`_metrics_inputs.py:74-102`) uses `python_files` and
  resolves its results as today; `measure_candidates`, `static_baseline` and `SuiteRun.measure`
  use `SourceMeter` and `measure_suite` from `measuring`; `_grading_ctx` is deleted and `_grade`
  sets `measured_metrics`. `ProjectFactory` (`_metrics_suite.py:43-60`) moves next to
  `ProjectHandle` (`grading/execution_metrics/project.py`), public.
- The two hook handlers that import kernel-private names switch to the public ones:
  `handlers/_metrics_pass.py:440` (`decode_source_blob` from `grading.measuring`) and
  `handlers/coverage_diff_gate.py:47` (`ProjectFactory` from `grading.execution.project`).

Changed on purpose in eval scoring, both from the gate's `SourceMeter`: a candidate file over
1 MB is skipped, not measured, and a source that raises `RecursionError`, `MemoryError` or a
`ValueError` while it is parsed is skipped instead of failing the score
(`_metrics_inputs.py:49`).

#### B.11.4 What moves behind the seam

The tree walk, the per-file loop with its byte cap and hostile-source handling, the suite loop,
and the grade-time availability rule. Dependency category: local-substitutable (files in a tmp
tree; `ProjectHandle` already has fakes). Adapters: eval scoring and the metrics gate.

#### B.11.5 Tests

New `tests/grading/test_measuring.py`:
`test_python_files_skip_dot_and_ignored_dirs`,
`test_python_files_keep_paths_under_the_given_root` (a symlinked root),
`test_measure_tree_labels_are_root_relative_posix`,
`test_measure_tree_skips_an_unparseable_file_with_a_reason`,
`test_measure_tree_skips_a_file_over_the_byte_cap`,
`test_measured_metrics_drop_ruff_without_a_ruff_path`,
`test_measured_metrics_never_list_a_judged_metric`,
`test_a_metric_check_is_available_iff_its_metric_was_measured`,
`test_a_metric_check_over_zero_files_grades_vacuously` (the behaviour pin),
`test_measure_suite_runs_the_suite_once_for_every_execution_metric`,
`test_decode_source_blob_normalizes_newlines_and_refuses_non_utf8`.

Deleted: `tests/evaluators/test_eval_runner.py:817`
`test_static_measurements_recurse_subdirs_and_skip_unparseable` (replaced by the first and
fourth tests above). Updated: tests that build an `EvalContext` with a parsed empty module or a
handle only to make a metric check available set `measured_metrics` instead
(`tests/evaluators/test_rubric.py`, `test_nested_rubric.py`, `test_execution_evaluators.py`,
`test_check.py`, `test_check_granularity.py`, `test_normalization.py`,
`tests/evals/test_compile.py`, `test_weighted_verdict.py`,
`tests/unit/test_evals_compile_blocks.py`; the implementer finds each by the failing run). Every
`tests/cli/test_eval*.py`, `tests/cli/test_metrics*.py` and `tests/hooks/` metrics test passes
unchanged; `tests/cli/test_metrics_golden.py` pins the gate's report bytes.

#### B.11.6 Docs, acceptance, blockers, risks

- Docs: SPEC §15.3.1 (`SPEC.md:3130-3131`) says the bridge measures through
  `grading/measuring.measure_tree` and `measure_suite`, and that a metric check is available when
  the pass measured its metric.
- Acceptance: `rg "_availability_|_grading_ctx|_IGNORED_DIRS|def _iter_py_files" src` prints
  nothing; one `IGNORED_DIRS`; the new tests pass; the golden metrics report is byte-identical;
  the gate passes.
- Blockers: #62, lane 0, N22, N23, N25 (and the `test_import_budget_stop.py` pin of the moved gate
  module, renamed by N22).
- Risks: (1) `measured_metrics` must include nested-rubric leaves, or a static check inside a
  nested rubric becomes unavailable; `test_nested_rubric.py` pins it. (2) The layer contract
  must allow `hook_runtime -> grading` (lazy, Stop stage) as it allows `evaluators` today.
- Out of scope, as the verifiers advised: moving the eval-only check families to `evals/`, the
  zero-adapter seams, `METRIC_DEFAULTS` for eval tasks (a score change for every task), and a
  shared plugin registry.

### B.12 B9 and B10: each command declares its own flags

#### B.12.1 Goal

`cli.build_parser` (`cli.py:68-422`) declares the flags of all 16 subcommands and binds them by
tuple position (`_SUBCOMMANDS[0]`..`[15]`, `cli.py:81-416`), so a new flag edits two files and a
reordered tuple silently rebinds commands. B9 puts each command's flags next to the `run` that
reads them, behind a protocol `cli` loops over.

#### B.12.2 Interface

`cli/_command.py` (new; private to `cli`):

```python
class Command(Protocol):
    """A ``playbook`` subcommand: a module with these four names (mypy checks modules
    structurally against a protocol, so commands never import ``cli``)."""

    @property
    def NAME(self) -> str: ...

    @property
    def HELP(self) -> str: ...

    def configure(self, parser: argparse.ArgumentParser) -> None: ...

    def run(self, args: argparse.Namespace) -> int: ...
```

Each migrated command module adds, next to its unchanged `run`:

```python
NAME: Final = "gate-scan"
HELP: Final = "flag gate-weakening changes in a commit range (prK §E.2)"


def configure(parser: argparse.ArgumentParser) -> None:
    """Declare ``playbook gate-scan``'s flags (moved verbatim from cli.py:310-319)."""
```

A module is the command; no `COMMAND` object and no import of `cli` (the layers run
`cli -> commands`). A probe with mypy 2.4 confirmed that `tuple[Command, ...] = (module, ...)`
type-checks a conforming module and rejects one whose `run` returns `str`. A `run` with extra
keyword-only parameters (`git: GitPort | None = None`) conforms.

In `cli/parser.py` (N7), which `main` calls:

```python
#: The order ``playbook --help`` lists, and the public surface tests pin.
_SUBCOMMANDS: tuple[str, ...] = ...  # unchanged, cli.py:48-65
_COMMANDS: Final[tuple[Command, ...]] = (check_cmd, metrics_cmd, ...)  # the migrated modules
_LEGACY: Final[Mapping[str, Callable[[_SubParsers], None]]] = {
    "init": _add_init_parser,
    "sync": _add_sync_parser,
    "validate": _add_validate_parser,
    "render": _add_render_parser,
    "eval": _add_eval_parser,
}


def build_parser() -> argparse.ArgumentParser:
    """The ``playbook`` parser: one subparser per name of ``_SUBCOMMANDS``, looked up by name."""
```

`build_parser` stays public (tests in `tests/unit/` and `tests/cli/` call it) and walks
`_SUBCOMMANDS` by name: a migrated command gets
`subparsers.add_parser(command.NAME, help=command.HELP)`, `command.configure(sub)`,
`sub.set_defaults(func=command.run)`; a legacy name calls its `_add_<name>_parser`, today's
block moved verbatim. `main`'s error mapping (`cli.py:449-467`) is unchanged, including
`init_cmd.PrecommitTemplateMissingError` until init migrates.

#### B.12.3 Commands migrated

| PR | Commands (flags moved from) |
| --- | --- |
| B9 | `check` (`cli.py:117-123`), `metrics` (`:197-273`), `import-harness` (`:277-284`), `validate-harness` (`:288-299`), `gate-scan` (`:310-319`), `ci` (`:322-328`), `scan-sinks` (`:331-342`), `check-notebooks` (`:345-351`), `scan-secrets` (`:360-389`), `check-commit-trailers` (`:398-407`), `check-deps` (`:416-420`) |
| B10 | `eval` (`:141-193`), into `commands/eval.py` after N11 |
| after #62 (L12) | `init`, `sync`, `validate`, `render`; then `_LEGACY` and `_SUBCOMMANDS`' literal go (`_SUBCOMMANDS = tuple(c.NAME for c in _COMMANDS)`) |

The 47 `getattr(args, …)` reads stay: typed per-command argument dataclasses are a separate,
optional step (verify-depth), not part of the protocol.

Sizes: `commands/metrics.py` 332 → about 410 lines, `ci.py` 488 → about 496, `check.py`,
`validate_harness.py` and the twins stay small. `commands/import_harness.py` is 544 lines before
and about 552 after: a pre-existing overrun that the post-chain agent-harness round trip splits.
`commands/eval.py` (735) gets its flags only after N11's split (B10).

#### B.12.4 Tests (the surface test is written first)

- New `tests/cli/test_cli_surface.py::test_every_subcommand_keeps_its_flags`, with
  `tests/cli/golden/cli_surface.json`: for each subcommand, each action's `option_strings`,
  `dest`, `nargs`, `const`, `default`, `type` name, `choices`, `required`, `help`, `metavar`
  and mutually exclusive group, recorded from `build_parser()` on the parent commit before any
  flag moves. It is independent of the Python version (unlike `--help` text, whose layout differs
  between 3.12 and 3.13).
- New `tests/unit/test_cli.py::test_every_subcommand_is_a_command_or_legacy` and
  `test_command_names_are_unique_and_match_their_place`.
- Unchanged and passing: `tests/unit/test_cli.py` (including `:52` and `:277`, which read
  `_SUBCOMMANDS`), `tests/unit/test_docs_lifecycle_hooks_cli.py:35`,
  `tests/unit/test_docs_readme_hooks.py:25`, every `tests/cli/` test, including the chain's
  `test_check.py`, `test_import_harness.py` and `test_validate_harness.py`.

#### B.12.5 Docs, acceptance, blockers, risks

- Docs: SPEC §12's opening paragraph (`SPEC.md:2192`) gains "Each subcommand's module declares
  its flags (`NAME`, `HELP`, `configure`, `run`); `cli` lists them in `_SUBCOMMANDS` order."
- Acceptance: the surface golden is unchanged; `rg "_SUBCOMMANDS\[" src` prints nothing; no
  command module imports `cli`; the gate passes.
- Blockers: #62, lane 0, N7; for the twins, after B6 (both edit their modules).
- Risks: the private helpers `_add_twin_parsers`, `_add_scan_secrets_parser`,
  `_add_check_commit_trailers_parser` and `_add_check_deps_parser` (`cli.py:306-421`) go; their
  help strings must move verbatim, which the golden pins.

#### B.12.6 B10 and N11's split

N11 (move only, section 7.4; harmonised to flat modules, H6): `commands/eval.py` keeps `run`,
`_run_task_cli` and `_load_task` (today `:94-231`, about 255 lines); the listing and show helpers
(`_print_list`, `_plural`, `_print_show`, `_print_run_hint`, `_short_source`,
`_display_source_path`, `_count_gate_checks`, `_count_rubric_criteria`,
`_gate_check_descriptions`, `_describe_binding`, `_rubric_criteria_with_weights`, `:449-735`)
move to `commands/_eval_enumerate.py`; the runner and judge lookups (`_load_runner_class`,
`_available_runner_names`, `_load_judge_class`, `_available_judge_names`, `_runner_available`,
`:233-283`) move to `evals/registry.py` and the result serialisers (`_result_to_dict`,
`_check_to_dict`, `_finding_to_dict`, `_format_result_text`, `_aggregate_line`,
`_any_trial_judge_scored`, `_judge_scored`, `_judge_scored_leaf`, `_scope_detail`, `:285-447`)
to `evals/report_format.py`, under names without the leading underscore. `commands/eval.py` calls
the lookups through the module (`registry.load_judge_class`), because
`tests/cli/test_eval_run.py:261,352,464,495,510` monkeypatch them. `tests/cli/test_eval.py:15,220,335,356,391,418`,
`test_eval_run.py:21` and `test_eval_aggregate_render.py:12` follow the imports; SPEC `:2563`
names the new path.

B10 then adds `NAME`, `HELP` and `configure` to `commands/eval.py` (the flags of
`cli.py:141-193`), moves `eval` from `_LEGACY` to `_COMMANDS`, and passes B9's surface golden
unchanged.

### B.13 What these PRs leave for after #62

| Left | Where | Done by |
| --- | --- | --- |
| `[metrics]` value policy at sync | `commands/validate.py` or `_sync_hooks.py` | follow-up of B2 after #62: question 2 resolved 2026-10-18 as option (a), `playbook validate` reports the invalid value as an error |
| `FileSystemStateSource` config half, `_typing.py`, the StateSource decision under L2 | `orchestrator.py`, `adapters/base.py` and the other `_typing` importers | config-files remainder (CF-2 deletes `_typing.py`; L2 keeps the `state_sources` group, so `StateSource` stays) |
| `guard_config.py:179-180` filename literals; `hook_runtime` filename spellings | writer side; runtime schema module | GC-1, GC-3 |
| writer adopts `guard_tables` table names; `HookRecord` one home | `guard_config.py`, `hook_policy/resolved.py` | GC-3, GC-4 |
| the three `ruff` table reads, two `ctx.config` reads | `ruff_feedback.py`, `_ruff_buckets.py`, `docstring_nonregression.py` | after #55, with the writer side |
| SPEC §6.6.7 sentence on `HookConfig` (B.7.5) | `SPEC.md:1199` | with the writer side |
| the writer-side copies of the `max_blocks` default and range | `hook_registrations/stop_gate.py:66-67,285-286` | guard-config-contract writer side, from `guard_tables` |
| `init`, `sync`, `validate`, `render` on the Command protocol; `_LEGACY` deleted | `cli/`, those commands | CP-1, CP-3 |

### B.14 Questions 1 and 2 (product decisions; resolved 2026-10-18, section 12)

1. **Where the twin-shared judges live.** The approved layout (L3) puts them in `security/`. As
   written they import `hook_runtime` (`caps`, `decision`, `_hosts`, `globs`, `_git_parse`),
   and `hook_runtime` imports `security`, so a `security/` home needs either a two-way package
   dependency, which ADR 0002's layers forbid, or a rewrite of the judges into stdlib-only code
   that returns plain findings and leaves message text to each adapter, which puts the
   byte-exact hook messages at risk. Resolved 2026-10-18: the default, public modules in
   `hook_runtime/judges/` (N14, N15), an amendment of L3 for these judges only.
2. **An invalid `[metrics]` value in the committed config at sync.** Today sync silently writes
   the default quality-lint rows into `guard_config.json`, while `playbook metrics` exits 2.
   Sync cannot raise where it reads the table (after its adapters wrote, B.3 item 5). Options
   for the post-#62 follow-up: (a) `playbook validate` reports it as an error, so sync refuses
   before writing anything, as `playbook metrics` does; (b) sync prints one `warning:` line and
   keeps the defaults. Resolved 2026-10-18: (a). B2 keeps today's behaviour and pins it with a
   test, so the follow-up is a one-line, visible diff.

## 9. Candidate designs after the chain: the guard_config writer, RenderSession, agent_harness/ and the command protocol

This section designs the four L12 candidates that wait for the skills ticket chain (#49-#62): the writer side of guard-config-contract (AC.2), render-session (AC.3), agent-harness-roundtrip (AC.4) and the command protocol for `sync`, `validate`, `render` and `init` (AC.5). Every PR here is re-read against the merged chain before it starts; AC.2.9, AC.3.9, AC.4.9 and AC.5.9 list what to re-check.

Baseline: `ef19a0a` (origin/main, 2026-10-18). Every `file:line` anchor below was verified there. The chain will move most of them, so line numbers are best effort (L9).

Facts that differ from the architecture review (`synthesize.json`):

- #47 (ticket 07) is merged, as PR #69 (`ef19a0a`); the review lists it as open. That ticket already added the `skill=` lines that the review attributes to spec §6.4.13 (`adapters/agent_harness_adapter.py:379`, `commands/import_harness.py:170,399-403`). The agent_harness move therefore has no chain lines to carry across.
- Ticket 03 (#43, PR #68) is merged. It was the last chain ticket that edits `commands/init.py`, `commands/_init_adapters.py` and `cli.py`: `cli.py:37` already imports `ADAPTERS_FLAG_HELP`, and no open ticket (#50-#62) touches those three files. L12 still puts CP-2 and CP-3 after the chain (7.6 CP-2).
- On the writer side, the chain edits only what #58 lists: the new `_guard_config_skills.py`, plus `guard_config.py`, `commands/_sync_hooks.py` and `commands/sync.py` (spec:3699-3722). Spec:315 states "No code change" for `_guard_config_protect.py`. #55's `linked_lint_config.skill_id` reaches `guard_config.json` through `ResolvedHook.to_json`, with no writer edit. #56 edits `_sync_hooks.py`'s dispatch, and #57 adds a `ResolvedHook.guardrail_text` property that is not serialized (spec:3515).
- #54's spec says `playbook render`'s registry "stays unfiltered" and is also passed as `skill_references` (spec:2919). The approved `playbook render` fix (P5) contradicts that sentence, so #54's ticket needs a note before it starts (AC.3.8).
- Anchors have drifted. The sync filter is now at `commands/_sync_render.py:182-183` (the review says 150-158). The unfiltered `playbook render` registry is at `commands/render.py:194`, `import_harness()` is at `commands/import_harness.py:433`, and the harness emitter import in `adapters/_skill_writer.py` is at `:82` (the review says 70).


**Harmonisation applied to this section** (section 11; the move spec of section 7 wins on paths):

| This section says | Read it as |
| --- | --- |
| P0 | lane 0: T0.0, T0.1, T0.2 |
| P1 | B2 (`ConfigFiles` in `config/files.py`; the committed-config builders in `config/committed.py`, N10) |
| P2 | N16 (`hook_runtime/config/`, with `ConfigKey` public in `config/keys.py`), B3 (`hook_runtime/config/guard_tables.py`), B4a; the runtime's schema module `hook_runtime/config/schema.py` is created by GC-1 |
| P3 | N22: `parse_metrics_config`, `ruff_config_flags` and `MetricConfig` live in `metrics_gate/config.py`, and `metrics_gate` sits below `hooks` (H5) |
| P4 | N7 and B9. B9 landed the protocol as module-level `NAME`, `HELP`, `configure` and `run` (no `COMMAND` object, section 8 B.12.2); read every `COMMAND` below as those four members and `COMMANDS` as B9's `_COMMANDS` tuple (H29) |
| P5, P6 | B1; N4 |
| M-hooks | A17 and A18 (A18 moves `LAUNCHER_TOKEN` to `hooks/registrations/launcher.py`, H15); A13 empties `tests/hooks/` first (H19) |
| M-skill-dirs | A7: the home is `generated_output/source_files.py`, not `adapters/skill_dirs/` (H8) |
| `commands/_sync_*` modules | `sync/*` (A6 lands before GC-2): `commands/_sync_hooks.py` is `sync/_hook_outputs.py`, and GC-2's relocations go to `sync/_protect.py` and `sync/_hook_scripts.py` (H10) |
| `tests/hooks/pack_repo.py` and the hook-pack tests | `tests/hook_runtime/handlers/` (A13) |
| `harness/*` in AH-1 | already `agent_harness/*` (N12, now); AH-1 moves the adapter, the sidecars, the importer and its helpers (H16) |
| `template_source` in RS-1 | already in `artifacts/identity.py` (A5), which RS-1 imports (H11) |
| `commands/init/` in CP-2 and CP-3 | flat modules: `commands/init.py`, `commands/_init_answers.py`, `commands/_init_config_plan.py`, `commands/_init_overlays.py`; `commands/_init_adapters.py` stays; `precommit.py` already exists (N9) (H6) |

### AC.1 Rules shared by every PR in this section

1. **No generated output changes.** Every PR here moves code or changes an interface; none changes a byte the engine writes into a consumer repo, the eval runner's prompt text, CLI output or exit codes. Each PR passes the parity check in AC.1.3.
2. **Move-only PRs** (GC-1, GC-2, RS-1, AH-1, CP-2) contain `git mv`, the import rewrites, the matching test moves (L8), the doc-path rewrite with the shared script (L9) and the pin updates of AC.1.4. Nothing else, with one exception: a name is renamed when the move makes it cross a package (for example `_write_result` becomes `write_import`). The file map of each PR says which names this applies to. Each new `tests/<package>/` folder gets an empty `__init__.py`, because the test tree is a package (`tests/__init__.py`).
3. **No shims, one spelling per name.** There are no re-exports at old paths (L2), and package `__init__.py` files hold only a docstring (L5). A public module also never re-exports names from a private module of its own package: a name that callers outside the package need is defined in a public module.
4. **Order.** There are no stacked PRs: each PR branches from main once the PRs it waits for have merged. Titles are Conventional Commits. The gate is `ruff check .`, `ruff format --check .`, `mypy` and `pytest -q`, run cache-free on Python 3.12 and 3.13.

#### AC.1.1 Prerequisites from other lanes

| Id | Lane | What this section needs from it | Needed by |
| --- | --- | --- | --- |
| P0 | lane 0 (import guards) | The import-linter dependency-order contract and the private-module check, both run from pytest, with an allow-list for the crossings that exist today. `FORBIDDEN` in `tests/hook_runtime/test_import_budget.py:48-66` derived from one list of sync-side packages that includes `hooks`, `rendering`, `agent_harness` and `precommit`; pinned module names checked with `importlib.util.find_spec`. The L9 doc-path rewrite script. In the dependency order, `metrics_gate` (or wherever `[metrics]` parsing lives) placed below `hooks` (GC-D5). | every PR |
| P1 | config-files (after #62 since question 3, 2.3) | `ConfigFiles(repo_root)` with its committed-table read, and the one `CONFIG_FILENAME` constant (it replaces `_guard_config_quality.py:38`'s private copy). | GC-3 |
| P2 | guard-config-contract, reader side (after #62 since question 3, 2.3) | The stdlib-only schema module owned by the runtime (`hook_runtime/config/schema.py` in the review) with the table names and the schema version; typed `GuardConfig` accessors; a public home for the `CONFIG_SCHEMA` key format (`hook_runtime/_config_keys.py` today). | GC-1, GC-3, GC-4 |
| P3 | grading-kernel (now) | The final home of `parse_metrics_config` and `ruff_config_flags` (`metrics_config.py:34,112` today). | GC-2, GC-3 |
| P4 | cli-command-protocol (N7 now; B9 after #62 since question 3, 2.3) | The `cli/` package (`__init__` with `main` and `build_parser`, plus `__main__.py`, because `python -m coding_agent_playbook.cli` is spawned by `hook_runtime/handlers/_source_changed.py:56` and `commands/ci.py:99`); the `Command` protocol; the ordered `COMMANDS` tuple; the shared exit-2 error type; the transitional dual style. | CP-1, CP-2, CP-3 |
| P5 | the `playbook render` applies_if fix (now, test first) | `_render_prompt` builds its registry from applies_if-filtered rules (`commands/render.py:194` today), with its regression test in `tests/cli/test_render.py`. | RS-2 |
| P6 | catalog-layers, conflict-free slice (now) | `filter_applies_if` (`orchestrator.py:251-269`) and `evaluate_predicate` in `detector/predicate.py`, so `rendering/` never imports the sync context module. | RS-1 |
| M-hooks | the post-chain move of the hook packages (move section of this spec) | `hook_policy/` becomes `hooks/resolution/` and `hook_registrations/` becomes `hooks/registrations/`, with `hooks/__init__.py` docstring-only. It must also remove the `hooks -> adapters` import at `hook_registrations/claude.py:15` (`LAUNCHER_TOKEN` from `adapters/claude_settings.py`), which the dependency order forbids. | GC-2 |
| M-skill-dirs (= A7) | the post-chain generated_output additions (target `generated_output/source_files.py`, H8) | A public home for `copyable_skill_files` (`adapters/_skill_sources.py`) and `skill_subtree_files` (`adapters/_skill_files.py`). | AH-1; GC-2 relocates an existing crossing |

When a move section of this spec already schedules M-hooks as one PR for the whole `hooks/` area, GC-2's file map (AC.2.5) is the `guard_config` part of that PR and GC-2 is not a separate PR.

#### AC.1.2 The PRs and their order

| PR | Title | Kind | Chain tickets it waits for | PRs it waits for | Can run beside |
| --- | --- | --- | --- | --- | --- |
| GC-1 | `refactor(hook_runtime): give the guard_config contract names public homes` | move | #62 (the writer side; the `selector_matches` row is gone, A16 makes `hook_runtime/ruff.py` public) | P2 (N16, B3) | RS-1, AH-1, CP-* |
| GC-2 | `refactor(hooks): move the guard_config writer into hooks/guard_config` | move | #55, #56, #57, #58 | P0, M-hooks (A17, A18), A13, A6, GC-1 | AH-1, CP-* (RS-1 after a rebase: both edit one import line of `commands/sync.py`) |
| GC-3 | `refactor(hooks): compile_guard_config reads its own repo inputs` | interface | none | GC-2, P1, P3 | RS-2, AH-2, CP-* |
| GC-4 | `refactor(hooks): one typed hook-record shape for guard_config.json` | interface | #57 (edits `hook_policy/resolved.py`) | GC-1, M-hooks | anything |
| RS-1 | `refactor(rendering): move the renderer, rule registry and prompt delivery into rendering/` | move | #54, #56, #57 (#49 merged) | P0, P5, P6, A5, A18 | GC-2, CP-1 |
| RS-2 | `refactor(rendering): one RenderSession renders for sync, playbook render and the eval runner` | interface | none | RS-1 | GC-3, AH-2, CP-3 |
| RS-3 | `test(rendering): one FakeRuleRegistry for the adapter tests` | tests | none | RS-1, AH-1 | RS-2 |
| AH-1 | `refactor(agent_harness): move the Agent Harness adapter and importer into agent_harness/` | move | #54 | P0, N12, P4's `import-harness` and `validate-harness` migration, RS-1, M-skill-dirs (or AC.4.5's fallback) | GC-*, CP-* |
| AH-2 | `refactor(agent_harness): import, lint and hook sidecars at the package interface` | interface | none | AH-1 | GC-3, RS-2, CP-* |
| CP-1 | `refactor(cli): sync, validate and render declare their own flags` | interface | #52, #54 (`validate.py`, `render.py`), #56, #58 (`sync.py`) | P4 | GC-*, AH-* (RS-2 after a rebase: both edit `commands/render.py`) |
| CP-2 | `refactor(init): split commands/init.py into _init_answers, _init_config_plan and _init_overlays` | move | none open (see section 12, question 4) | P4, N9, RS-1 (rewrites `init.py:42`'s import) | GC-*, AH-* |
| CP-3 | `refactor(init): init declares its own flags and asks through an injected prompt` | interface | none | CP-2, CP-1 (both edit `cli/parser.py`) | GC-*, AH-* |

The schedule reads as four lanes, one per candidate, started once #62 (the end of the chain) has merged. Inside a lane, PRs merge in order. Across lanes, the only couplings are the ones the table lists: RS-1 goes before AH-1 and CP-2, and CP-1 goes before CP-3.

#### AC.1.3 Parity check (an acceptance item of every PR)

This check proves rule 1. Run it in the scratchpad, never in the worktree. `P` is a worktree at the PR's base commit, `N` is the PR's worktree, and `S` is a fresh scratch directory:

```bash
git init -q "$S/probe"   # pyproject declaring fastapi, pydantic, torch, numpy, pandas; dev: pytest, ruff, mypy; one .ipynb; uv.lock
timeout 180 uv run --project "$P" playbook init --non-interactive --name probe --kind python-application \
  --adapters claude_code,opencode,shared_skills,continue,agent_harness \
  --overlays coding_agent_playbook.plugins.python_design --repo-root "$S/probe" </dev/null
timeout 180 uv run --project "$P" playbook sync --repo-root "$S/probe" </dev/null
timeout 180 uv run --project "$N" playbook sync --check --repo-root "$S/probe" </dev/null   # must exit 0
```

`init` leaves hooks enabled in non-interactive mode (`commands/init.py:252-268`), so `guard_config.json` and the hook sidecars are part of the comparison. `sync --check` byte-compares every generated output and the lockfile hashes. The reviewer reruns the last command. PR-specific additions are listed in each acceptance section: for AH, an `import-harness` round trip; for RS, an eval prompt render; for CP, a fresh `init` comparison.

#### AC.1.4 Test pins that name the modules moved here

These pins must change in the same commit as the move. Where a pinned name would go silently vacuous, the pin is renamed rather than deleted, unless P0's prefix-based `FORBIDDEN` already covers it.

| Pin (verified at `ef19a0a`) | What it pins | Changed by |
| --- | --- | --- |
| `tests/unit/test_docs_lifecycle_hooks_spec.py:94-105` (`_ENGINE_PATHS`, `"guard_config.py"` at :99) | the file exists and SPEC §5.1 shows it | GC-2: becomes `"hooks/guard_config/"`, and SPEC §5.1's tree shows `── guard_config/` under `hooks/` |
| `tests/hook_runtime/test_import_budget.py:576` (`coding_agent_playbook._guard_config_ruff` not imported) | the sync-time ruff reader stays off the hot path | GC-2: deleted, because P0's `FORBIDDEN` entry `coding_agent_playbook.hooks` covers `hooks.guard_config._tables_ruff` by prefix (`_forbidden`, :130-136) |
| `tests/adapters/test_claude_code_rules.py:89-96` (imports `_guard_config_protect`) | the protected-table inputs stay free of jinja2, yaml and the renderer | GC-2: probes `coding_agent_playbook.sync._protect` with the same three assertions |
| `tests/unit/test_rule_registry.py:206-213` | `orchestrator` never loads `coding_agent_playbook.rule_registry` | RS-1: replaced by `test_rendering_never_imports_the_sync_context` (AC.3.6) |
| `tests/unit/test_hook_registrations.py:517`, `tests/adapters/test_claude_code_rules.py:95` | `coding_agent_playbook.renderer` not loaded | RS-1: the name becomes `coding_agent_playbook.rendering` |
| `tests/unit/test_prompt_rule_delivery.py:125-127` | importing the module loads only itself | RS-1: the expected list becomes `["coding_agent_playbook.rendering", "coding_agent_playbook.rendering.prompt_rule_delivery"]` |
| `tests/unit/test_docs_lifecycle_hooks_cli.py:27-28` | imports `HOOKS_SIDECAR` and the adapter from `adapters` | AH-1 |
| `tests/unit/test_committed_config.py:313` (`modules["commands/init.py"]`) | init imports the committed-config builders | CP-2: becomes `"commands/_init_config_plan.py"` (the builders themselves are in `config/committed.py` since N10) |
| `tests/unit/test_cli.py:426-431` | the missing pre-commit template exits 2 | N9 (import path), CP-3 (error base) |

### AC.2 guard-config-contract, writer side

#### AC.2.1 Goal

`guard_config.json` is the contract between sync (the writer) and the hook runtime (the reader). After this work, the writer is one deep module: sync hands it only what sync owns, and the module reads every repo input itself, builds every table and returns canonical bytes. Its interface stops knowing adapters, and it imports no private runtime module. The contract names it shares with the runtime have one definition each, owned by the runtime (the review's ADR callout).

#### AC.2.2 Today (`ef19a0a`)

- **Interface.** `render_guard_config(inputs: GuardConfigInputs) -> dict[str, Any]` (`guard_config.py:244-303`). `GuardConfigInputs` has 13 fields (`:199-233`), and #58 adds a 14th, `skill_globs` (spec:3720).
- **The caller reads the repo for the writer**, five times: `precommit_hook_ids` (`commands/_sync_hooks.py:215`), `repo_layout` (`:218`), `read_project_ruff_selection` (`:219`), `read_toolchain_inputs` (`:220`) and `read_quality_lint` (`:221`). #58 adds `skill_globs=skill_glob_rows(rules)` (spec:3721). `tests/hooks/pack_repo.py:27-29,240-256` repeats the same assembly and imports three private `_guard_config_*` readers.
- **The machine-local step reads twice more:** `resolve_resource_roots` (`_sync_hooks.py:413`) and `{*ruff_candidate_codes(...), *read_quality_lint(...).codes}` (`:422-426`). It also imports the probe from `_guard_config_ruff` (`commands/_sync_hook_local.py:38`).
- **Private runtime imports.** `guard_config.py:100-107` imports `_shell_wrappers`, `handlers._control_plane_paths`, `handlers._control_plane_text`, `handlers._eval_paths` and `handlers._notebook_check`. `_guard_config_quality.py:21` and `_guard_config_ruff.py:30` import `hook_runtime._ruff`, and `_guard_config_secrets.py:22` imports `hook_runtime._config_keys`.
- **Adapter knowledge.** `guard_config.py:92` imports `adapters._skill_sources` for `copy_hook_scripts` (`:352-376`). `_guard_config_protect.py:36` imports `CLAUDE_CODE_COMPOSITES`, and `:178` calls the private `adapter._output_directories()`.
- **Contract values defined twice:**
  - the schema version: `GUARD_CONFIG_SCHEMA = 1` (`guard_config.py:148`) against `SUPPORTED_SCHEMA_VERSIONS = (1, 1)` (`hook_runtime/config.py:66`);
  - the file path: `GUARD_CONFIG_PATH = GUARD_CONFIG_REL` (`guard_config.py:146`);
  - the resource-root id format: `"pkg:{package}/resources"` at `_guard_config_protect.py:66`, with the engine's id spelled out again as a literal at `hook_runtime/protected.py:66`;
  - the hook record: `ResolvedHook.to_json` (`hook_policy/resolved.py:139-153`) against `parse_hook_record` (`hook_runtime/_hook_records.py:87-118`). These two are already pinned together by `tests/hook_runtime/test_runtime_config.py:251`.
- **The `stop_gate` table builder** (`hook_registrations/stop_gate.py:213-229`) sits beside the stage records that the registrations use for deadlines (`hook_registrations/plan.py:28-32`).

#### AC.2.3 Decisions

- **GC-D1.** `hooks/guard_config/` owns exactly the `guard_config.json` document. The hook script copies (`copy_hook_scripts`) and the protected-set assembly (`protected_rows`, `adapter_output_dirs`, `COMPOSITE_SINGLETONS`) need adapters, and `hooks` sits below `adapters` in the dependency order (P0). So they move to the sync side, into `sync/_hook_scripts.py` and `sync/_protect.py` (A6 has created `sync/`).
- **GC-D2.** The request carries only data that sync computes from its merged catalog and its adapters: the resolved hooks, the `[hooks]` and `[guardrails]` policy, the engine version, the generated locations, the protected set, the detector facts with the applicability rows, the rendered prompts and the rendered rules. Every input read from a repo file is read inside the writer. Skill globs are derived inside, from `rules`, and do not become a caller-built field (review callout on ADR 0001).
- **GC-D3.** `compile_guard_config` returns the document and its canonical bytes, and writing is a separate call. `sync --check` thus writes the same bytes into its scratch directory while the readers read the real repo (`repo_root`), as `_sync_hooks.py:214` does today.
- **GC-D4.** The runtime owns the contract names. The writer imports them from public `hook_runtime` modules (table in GC-1). No ADR is added: ADR 0002's dependency order and P0's forbidden contract (`hook_runtime` never imports `hooks`) already enforce the direction, and the schema module's docstring states it.
- **GC-D5.** Readers keep today's error policy: an unreadable or malformed pyproject, ruff config or pre-commit config gives the reader's default (verify-depth: a sync-time reader degrades rather than raises). For `[metrics]`, the writer calls the quality reader with whatever policy P1 landed. Reading `[metrics]` from `hooks/` requires the parser's home (P3) to sit below `hooks` in the dependency order. Today's lane-0 draft lists `metrics_gate` above `adapters`, but `metrics_gate` imports only the grading kernel, `config` and leaves, so placing it below `hooks` costs nothing.
- **GC-D6.** The hook record gets one typed shape, a `HookRecordJson` TypedDict in the schema module that `ResolvedHook.to_json` returns. `ResolvedHook` does not delegate to the parsed `HookRecord` (`_hook_records.py:65-84`), because that form is lossy: its globs are compiled, its `on_error` is clamped per event and its `raw` is a read-only proxy. The win is a mypy-checked key set. Drift is already pinned by a test (verify-depth), so GC-4 is small.
- **GC-D7.** The `HOOK_ARTIFACTS` default stays defined twice (`guard_config.py:156-160` and `hook_runtime/protected.py:68-72`). The runtime copy is a fallback for a file written before the table existed, so removing it needs a schema decision. It is recorded as follow-up F-G1.

#### AC.2.4 Interface

```python
# src/coding_agent_playbook/hooks/guard_config/compile.py
"""Compile guard_config.json, the hook runtime's only configuration, from what sync owns."""

#: guard_config.json plus the copied hook scripts; joins the adapters' output_locations.
#: HOOKS_OUTPUT_DIR comes from the runtime's schema module.
SYNC_OUTPUT_LOCATIONS: Final[tuple[str, ...]] = (HOOKS_OUTPUT_DIR,)


@dataclass(frozen=True, slots=True, kw_only=True)
class GuardConfigRequest:
    """What sync owns and hands the writer; every other input is read from ``repo_root``.

    ``repo_root`` is the real repository in every mode: ``sync --check`` writes into
    a scratch directory but reads the repo's own pyproject, ruff config, pre-commit
    config and committed config. ``rules`` and ``prompts`` are this sync's rendered,
    ``applies_if``-filtered artifacts.

    Example::

        compile_guard_config(GuardConfigRequest(repo_root=repo, hooks=hooks.resolved,
            hooks_config=hooks.config, guardrails=hooks.guardrails, engine_version="0.2.0"))
    """

    repo_root: Path
    hooks: Sequence[ResolvedHook]
    hooks_config: HooksConfig
    guardrails: GuardrailsConfig
    engine_version: str
    generated: Sequence[str] = ()
    protected: ProtectInputs = field(default_factory=ProtectInputs)
    detect: DetectInputs = field(default_factory=DetectInputs)
    prompts: Sequence[Prompt] = ()
    rules: Sequence[Rule] = ()


@dataclass(frozen=True, slots=True)
class CompiledGuardConfig:
    """The guard_config.json document and its canonical bytes (``serialize_guard_config``)."""

    document: Mapping[str, Any]
    data: bytes

    def write(self, out_root: Path) -> Path:
        """Write ``data`` to ``<out_root>/<GUARD_CONFIG_REL>`` (bytes, never CRLF); return the path."""


def compile_guard_config(request: GuardConfigRequest) -> CompiledGuardConfig:
    """Read the repo inputs, build every table, serialize canonically. Writes nothing.

    An unreadable repo input gives its reader's default (GC-D5); a template or
    policy error was raised earlier, by sync's render and hook resolution.
    """


def serialize_guard_config(document: Mapping[str, Any]) -> bytes:
    """Unchanged (``guard_config.py:327-336``); tests that edit a document re-serialize with it."""
```

```python
# src/coding_agent_playbook/hooks/guard_config/inputs.py: the request's value types (moved, unchanged)
ProtectedRow, ProtectInputs  # from _guard_config_protect.py:69-115
HookView, ApplicabilityRow, DetectInputs, applicability_rows  # from _guard_config_detect.py:49-155

# src/coding_agent_playbook/hooks/guard_config/ruff_probe.py: the machine-local probe (moved)
RuleProbe, RuleCache, probe_ruff_rules, ruff_drop_codes  # from _guard_config_ruff.py:195-344


def ruff_probe_codes(hooks: Iterable[ResolvedHook], repo_root: Path) -> list[str]:
    """Sorted rule codes the pinned ruff is probed for: hook lint codes plus the quality family's.

    Replaces the set expression at ``commands/_sync_hooks.py:422-426``.
    Example: ``ruff_probe_codes(hooks.resolved, repo)`` -> ``["C901", "D100", ...]``.
    """


# src/coding_agent_playbook/hooks/guard_config/resource_roots.py (moved, unchanged)
resource_root_ids, resolve_resource_roots  # from _guard_config_protect.py:186-233
```

#### AC.2.5 PRs and file maps

**GC-1 (move-only, runtime side).** It gives every contract name that the writer imports a public home. GC-1 creates the stdlib-only schema module `hook_runtime/config/schema.py`, beside B3's `guard_tables.py` (B3 owns the pack-table names; the schema module owns the file path, the schema version and the shared constants below). Rows that earlier moves already made public are marked and dropped. Runtime importers import each name from its new home (no re-export). The schema module stays stdlib-only, and the hot-path budget tests stay green. GC-1 moves each name **verbatim** (its definition text unchanged, imports rewritten); it merges no literal and derives no constant from another. Folding duplicate literals into one definition is behaviour-adjacent and goes to GC-4 (below).

| Name | Today | Home after GC-1 |
| --- | --- | --- |
| `GUARD_CONFIG_REL`, `LOCKFILE_REL`, `SUPPORTED_SCHEMA_VERSIONS` | `hook_runtime/config.py:63-66` | schema module |
| `GUARD_CONFIG_SCHEMA` (the writer's `1`) | `guard_config.py:148` | schema module, moved verbatim under its own name (renaming it `GUARD_CONFIG_SCHEMA_VERSION` and writing `SUPPORTED_SCHEMA_VERSIONS = (1, GUARD_CONFIG_SCHEMA_VERSION)` is GC-4) |
| `HOOKS_OUTPUT_DIR` | `guard_config.py:150` (literal again at `hook_runtime/protected.py:69`) | schema module; the second literal at `protected.py:69` stays until GC-4 replaces it with the import |
| `CONTROL_PLANE` with `PolicyKeys` and `DEFAULT_POLICY_KEYS` (pure data) | `handlers/_control_plane_paths.py:73-104`, `handlers/_control_plane_toml.py:50-68` | schema module |
| `PRECOMMIT_CONFIG`, `PRECOMMIT_ID_RE`, `playbook_precommit_ids` | `guard_config.py:163`, `handlers/_control_plane_text.py:35-51` | schema module |
| `FIXTURE_GLOBS` | `handlers/_eval_paths.py:18` | dropped: N15 moved it to the stdlib leaf `artifacts/path_classes.py`, which the writer imports |
| `NOTEBOOK_MAX_BYTES` | `handlers/_notebook_check.py:41` | dropped: public in `hook_runtime/judges/notebook_check.py` since N14 |
| `DEFAULT_RUNNER_WRAPPERS` | `hook_runtime/_shell_wrappers.py:38` | dropped: public in `hook_runtime/shell/wrappers.py` since N17 |
| `RESOURCE_ROOT_ID_FORMAT = "pkg:{package}/resources"` | `_guard_config_protect.py:66` (and the engine's literal id at `hook_runtime/protected.py:66`) | schema module; `ENGINE_RESOURCES_ID` keeps its literal until GC-4 builds it from the format |
| `selector_matches`, `intersect_selectors` (and `_letters`) | `hook_runtime/_ruff.py:87-135` | dropped: public in `hook_runtime/ruff.py` since A16 |
| `ConfigKey`, `regex_of` | `hook_runtime/_config_keys.py` | dropped: public in `hook_runtime/config/keys.py` since N16 |

**GC-2 (move-only, writer side).** The `hooks/guard_config/` package plus two sync-side modules:

| From (`ef19a0a`; #58's module included) | To |
| --- | --- |
| `guard_config.py`: `GuardConfigInputs`, `render_guard_config`, `serialize_guard_config`, `write_guard_config`, `SYNC_OUTPUT_LOCATIONS`, `HOOK_ARTIFACTS`, `COMMIT_CONVENTION_HOOK_ID`, `_PATH_CLASSES`, `_logging`, `_path_classes`, `_unique`, `_DECISION_LOG_HOOK`, `_AUDIT_LOG_HOOK` | `hooks/guard_config/compile.py` |
| `guard_config.py`: `precommit_hook_ids`, `_PRECOMMIT_MAX_BYTES` (`:165`, `:306-324`) | `hooks/guard_config/_tables_precommit.py` |
| `guard_config.py`: `CopiedScripts`, `copy_hook_scripts`, `_copy`, `_runs_a_script` (`:236-241`, `:352-385`) | `sync/_hook_scripts.py` |
| `_guard_config_allowlists.py`, `_prompts.py`, `_quality.py`, `_secrets.py`, `_toolchain.py`, `_verify.py`, `_skills.py` (#58) | `hooks/guard_config/_tables_<same suffix>.py` |
| `_guard_config_detect.py`: `HookView`, `ApplicabilityRow`, `DetectInputs`, `applicability_rows` | `hooks/guard_config/inputs.py` |
| `_guard_config_detect.py`: `facts_table`, `applicability_table`, `_artifact_row`, `_holds`, `_plain`, `_FLAGS` | `hooks/guard_config/_tables_detect.py` |
| `_guard_config_protect.py`: `ProtectedRow`, `ProtectInputs` | `hooks/guard_config/inputs.py` |
| `_guard_config_protect.py`: `protected_table` | `hooks/guard_config/_tables_protect.py` |
| `_guard_config_protect.py`: `resource_root_ids`, `resolve_resource_roots`, `_layer_dir` | `hooks/guard_config/resource_roots.py` |
| `_guard_config_protect.py`: `COMPOSITE_SINGLETONS`, `protected_rows`, `adapter_output_dirs`, `_lock_path_via_repo_links`, `_relative` | `sync/_protect.py` |
| `_guard_config_ruff.py`: `RuffSelection`, `read_project_ruff_selection`, `ruff_table`, `SAFE_FIX_ALLOWLIST`, `RUFF_CONFIG_FILES` and their helpers (`:58-165`) | `hooks/guard_config/_tables_ruff.py` |
| `_guard_config_ruff.py`: `ruff_candidate_codes`, `_listed_codes`, the probe (`:167-344`), `PROBE_TIMEOUT_S`, `RULE_CACHE_DOCUMENT` | `hooks/guard_config/ruff_probe.py` |
| `hooks/registrations/stop_gate.py` (after M-hooks; `:213-229` today): `stop_gate_table`, `_max_blocks`, `_verify_commands`, `_argv`, `_claim_patterns` and the constants only they use | `hooks/guard_config/_tables_stop_gate.py`; the stage records stay in `stop_gate.py` and are imported from there |
| `tests/unit/test_guard_config.py`, `test_guard_config_{quality,ruff,toolchain,skills}.py` | `tests/hooks/guard_config/test_compile.py`, `test_tables_{quality,ruff,toolchain,skills}.py`; the probe tests (`test_guard_config_ruff.py:151-214`) go to `test_ruff_probe.py`. A13 has moved the hook-pack tests out of `tests/hooks/` (H19) |

GC-2 adds exactly five rows to P0's private-module allow-list, all from `sync._hook_outputs` (today's `commands._sync_hooks`), to `hooks.guard_config._tables_precommit`, `_tables_quality`, `_tables_ruff`, `_tables_toolchain` and `_tables_verify`. These are the five repo readers; GC-3 deletes all five rows. The existing rows for the writer's runtime and adapter imports are renamed or deleted, to match GC-1 and the sync-side relocations. Doc-path map for the L9 script: `guard_config.py` becomes `hooks/guard_config/compile.py`, and `_guard_config_<x>.py` becomes `hooks/guard_config/_tables_<x>.py`. Hand-edit the two SPEC mentions of `copy_hook_scripts` and `protected_rows`.

**GC-3 (interface).**

- `GuardConfigInputs` and `render_guard_config` give way to `GuardConfigRequest`, `compile_guard_config` and `CompiledGuardConfig`. `write_guard_config(out_root, cfg)` becomes `CompiledGuardConfig.write(out_root)`.
- Inside `compile_guard_config`:
  - `precommit_hook_ids(request.repo_root)`;
  - `repo_layout(request.repo_root)`;
  - `read_project_ruff_selection(request.repo_root)`;
  - `read_toolchain_inputs(request.repo_root, request.detect.facts)`;
  - `read_quality_lint(ConfigFiles(request.repo_root))` (P1);
  - `skill_glob_rows(request.rules)`.
- `ruff_probe.ruff_probe_codes` replaces `_sync_hooks.py:422-426`.
- `GUARD_CONFIG_PATH` is deleted. Its importers use the schema module's `GUARD_CONFIG_REL`: `tests/unit/test_docs_readme_hooks.py:34`, `tests/unit/test_sync_hooks.py:15`, and the docstring at `_output_io.py:100`.
- `commands/_sync_hooks.write_runtime_outputs` builds one `GuardConfigRequest` from `ctx`, `hooks`, the recorder and #58's `rules` argument, then calls `.write(out_root)`.
- `tests/hooks/pack_repo.py`:
  - `install_pack` builds a request with `repo_root=self.root` and imports no private module;
  - it loses the `precommit_ids` parameter, so its one user (`tests/hooks/test_block_precommit_bypass.py:42`) writes a `.pre-commit-config.yaml` instead, as `tests/unit/test_guard_config.py:464,474` also do;
  - `extra_tables` and `handler_config` keep working on a deep copy of `compiled.document`, re-serialized with `serialize_guard_config`.
- Tests that reach a private reader are rewritten at the interface and then deleted, so old and new tests never sit side by side. This covers `test_read_quality_lint_from_the_committed_table`, `test_read_quality_lint_defaults_on_absent_or_bad_table`, `test_read_toolchain_inputs_from_the_repository`, `test_project_select_from_pyproject_ruff_toml_and_defaults` and `test_dot_ruff_toml_wins_over_ruff_toml_over_pyproject`. The pure table-builder tests that need no repo stay where GC-2 moved them (`test_install_hint_per_package_manager`, `test_asyncio_marks_follow_the_rule_body_fact_and_the_mode`, `test_quality_hook_config_drops_override_of_project_selected_code`, `test_safe_fix_select_is_I_UP_intersect_project`): an interface test would only repeat them.

**GC-4 (interface).**

- The literal merges GC-1 leaves out, each with a test that the derived value equals today's literal: `GUARD_CONFIG_SCHEMA` becomes `GUARD_CONFIG_SCHEMA_VERSION` and `SUPPORTED_SCHEMA_VERSIONS = (1, GUARD_CONFIG_SCHEMA_VERSION)`; `hook_runtime/protected.py:69` imports `HOOKS_OUTPUT_DIR` instead of repeating the literal; `ENGINE_RESOURCES_ID` (`protected.py:66`) is built from `RESOURCE_ROOT_ID_FORMAT`.
- The schema module gains `HandlerRecordJson`, `HookRecordJson` (TypedDicts) and `HOOK_RECORD_KEYS: Final[frozenset[str]]`, built from the TypedDict's required keys.
- `ResolvedHandler.to_json` returns `HandlerRecordJson`, and `ResolvedHook.to_json` returns `HookRecordJson` (in `hooks/resolution/resolved.py` after M-hooks; `hook_policy/resolved.py:57-66,139-153` today). #57's `guardrail_text` is not part of the record.
- `_hook_records.py`'s docstring (`:3-7`) names `HOOK_RECORD_KEYS` as the schema.
- `_tables_*` helpers that rewrite a record keep `Mapping[str, Any]` parameters, since a TypedDict is a Mapping.

#### AC.2.6 Tests

| File | Test | Asserts |
| --- | --- | --- |
| `tests/hooks/guard_config/test_compile.py` | `test_request_fields_are_only_what_sync_owns` | `{f.name for f in fields(GuardConfigRequest)}` equals the ten names in AC.2.4, which pins GC-D2 |
| same | `test_compile_reads_the_project_ruff_selection` | a tmp repo whose `ruff.toml` selects `I`: `document["ruff"]` carries that selection and the `I` safe fix |
| same | `test_compile_reads_toolchain_hints_from_pyproject` | `uv.lock` plus a dev group without pytest: toolchain-missing-hint's derived config carries the uv install hint |
| same | `test_compile_reads_the_quality_family_from_the_committed_metrics_table` | `[metrics.ruff_violations]` in `.coding-agent-playbook.toml` reaches `clean-code-metrics-nonregression`'s `lint_codes.warn` and `ruff_config` |
| same | `test_compile_keeps_defaults_for_unreadable_repo_inputs` (parametrized: malformed pyproject, malformed `ruff.toml`, `.pre-commit-config.yaml` over 1 MiB, no committed config) | the matching table equals its default; no exception |
| same | `test_compile_reads_precommit_ids_from_the_repo_config` | `precommit.playbook_hook_ids` lists the ids of the repo's `.pre-commit-config.yaml`, sorted |
| same | `test_compile_derives_skill_globs_from_rendered_member_rules` | replaces #58's three `test_guard_config_skills.py` tests at the interface: globs grouped by skill, no row from a rule without `skill` or `globs`, rows sorted and globs deduplicated |
| same | `test_compiled_data_is_the_canonical_serialization` | `data == serialize_guard_config(document)`, the bytes are ASCII and end in one `\n` |
| same | `test_check_mode_reads_the_real_repo_not_the_output_root` | the same request written to two output roots gives identical bytes; the repo inputs come from `repo_root` |
| `tests/hooks/guard_config/test_round_trip.py` (new) | `test_compiled_config_loads_and_every_table_reads_typed` | compile on a tmp repo with every engine hook on, write it, record its sha256 in a lockfile: `load_guard_config` returns a `GuardConfig` (no `ConfigFault`), and P2's typed accessors (`stop_gate()`, `protected()`, `ruff()` and the rest) return what the request implies |
| same | `test_written_schema_version_is_supported_by_the_runtime` | `document["schema_version"]` lies inside `SUPPORTED_SCHEMA_VERSIONS` |
| `tests/hooks/guard_config/test_ruff_probe.py` | `test_probe_codes_add_the_quality_family` | `ruff_probe_codes` equals today's set expression on a repo with a `[metrics]` quality family |
| `tests/hook_runtime/test_runtime_config.py` | `test_resolved_hook_json_has_exactly_the_record_keys` (GC-4) | `set(resolved.to_json()) == HOOK_RECORD_KEYS` for a builtin, an entry-point and an external hook |

#### AC.2.7 Acceptance criteria

1. The parity check (AC.1.3) exits 0 for GC-1 to GC-4, with hooks on and every engine hook enabled, skill-nudge included.
2. After GC-3, `grep -rn "read_quality_lint\|read_project_ruff_selection\|read_toolchain_inputs\|precommit_hook_ids\|repo_layout\|skill_glob_rows" src/coding_agent_playbook/sync src/coding_agent_playbook/commands tests/hook_runtime/handlers/pack_repo.py` is empty. From `hooks.guard_config`, `sync/_hook_outputs.py` imports only `compile`, `inputs`, `ruff_probe` and `resource_roots`.
3. No module outside `hooks/guard_config/` imports one of its underscore modules, and P0's allow-list has no row that names `hooks.guard_config`.
4. No module under `hooks/` imports `adapters`, `rendering`, `commands`, `orchestrator` or an underscore module of `hook_runtime` (dependency-order contract plus the private check). `grep -rn "hook_runtime\.\(handlers\.\)\?_" src/coding_agent_playbook/hooks` is empty.
5. Each contract value has one definition: `GUARD_CONFIG_PATH` and `GUARD_CONFIG_SCHEMA` no longer exist (`grep -rnw 'GUARD_CONFIG_PATH\|GUARD_CONFIG_SCHEMA' src tests` is empty), and `grep -rn '"pkg:{package}/resources"' src` finds only the schema module.
6. The schema module loads nothing outside the stdlib and `hook_runtime` (an import probe in the style of `tests/import_probe.py`), and every hot-path case of `tests/hook_runtime/test_import_budget.py` passes.
7. `hooks/guard_config/compile.py` has at most 300 lines and every module of the package at most 400. `_ENGINE_PATHS` and SPEC §5.1 name `hooks/guard_config/`.
8. The full gate passes on Python 3.12 and 3.13.

#### AC.2.8 Risks

- **Byte drift in `guard_config.json`** (key order, a reader's default, a table built from a different `repo_root` in `--check`). Mitigation: the parity check, `test_check_mode_reads_the_real_repo_not_the_output_root`, and the existing table tests moved unchanged in GC-2.
- **The dependency order bites in GC-2.** Any adapter import left under `hooks/` fails the contract. That is why GC-D1 relocates the script copies and the protected-set assembly first. M-hooks must also clear `hook_registrations/claude.py:15`.
- **P1, P2 or P3 land under other names.** GC-3 then uses the landed names; AC.2.9 lists them.
- **`pack_repo.py` is used by about 55 test files.** Only `install_pack`'s signature changes, and only one caller passes `precommit_ids`.
- **Hot path.** The schema module gains data (`CONTROL_PLANE`, `PolicyKeys`) that hot-path modules already import today. It gains no new stdlib import beyond `re`, which `hook_runtime/config.py:23` already loads.

#### AC.2.9 Re-check after #62

- #58 landed `_guard_config_skills.py` with `SKILL_NUDGE_HOOK_ID` and `skill_glob_rows(rules)`; `GuardConfigInputs.skill_globs`; `write_runtime_outputs(..., rules=...)`; and `commands/sync.py` passing `rules=rendered.rules` (spec:3720-3722). Its tests in `tests/unit/test_guard_config_skills.py` become GC-3's interface test.
- #55 added no writer-side reader (spec 8.1-8.3), and #56 left `write_runtime_outputs` signature-compatible.
- #57's `guardrail_text` is not serialized (GC-4).
- The anchors in AC.2.2: `guard_config.py:199-303`, `_sync_hooks.py:189-227,400-433`.
- The names P1, P2 and P3 landed: the schema module's path, the typed accessor names, the `ConfigFiles` committed-table method, and the home of `parse_metrics_config` with its position in the dependency order.
- Whether M-hooks ships as one PR that absorbs GC-2.

### AC.3 render-session

#### AC.3.1 Goal

One module renders artifact bodies for sync, `playbook render` and the eval runner. Each render pass gets one sandboxed environment and one rule registry built only from applies_if-filtered rules, so the three callers cannot diverge again (`commands/render.py:194` against `_sync_render.py:182`). `prompt_rule_delivery.py` stays its own module: #65 created it on purpose and #54 grows it (verify-cost).

#### AC.3.2 Today (`ef19a0a`, before #54)

- **Three assemblies of the pipeline.**
  - `_sync_render.render_artifacts` (`commands/_sync_render.py:166-203`): filter `:182-183`, environment `:184-185`, rule bodies `:189`, registry and prompt environment `:190`, prompt bodies `:191`, inclusions `:192`, hook bodies `:193`.
  - `commands/render.py`: `_render_rule` (`:177-187`), `_render_prompt` (`:190-204`, with the registry built from the unfiltered `ctx.rules_resolved` at `:194`) and `_render_hook` (`:207-221`).
  - `evals/prompting.py`: `_render_body` (`:131-145`), `_render_context` (`:175-189`, which "Mirrors" `build_jinja_context`, `_sync_render.py:97-108`), `_prompt_environment` (`:208-214`), `_LazyRuleRegistry` (`:217-235`) and `_applicable_rules` (`:238-254`, its own applies_if loop at `:250-253`, the same rule as `filter_applies_if`, `orchestrator.py:251-269`). The module docstring says the two "should converge on one shared helper" (`:16-17`).
- **The environment setup pair** (`build_environment` plus `env.globals["_facts"]`) appears at `_sync_render.py:184-185`; `render.py:178-179`, `:191-192` and `:213-214`; `evals/prompting.py:210-213` and `:231-232`; `rule_registry.py:81-82` and `:84-85`; and `commands/init.py:404-405`.
- **`rule_registry.py:19` imports `orchestrator.template_source`** (`orchestrator.py:242-248`), so rendering code depends on the sync context module, and `orchestrator.py:61` imports `RuleRegistry` back under `TYPE_CHECKING`.
- **`renderer.py` (499 lines)** mixes the sandbox (`:111-238`), the format switch (`:241-296`), the per-format transforms and hook projections (`:299-499`) and `with_sentinel_body` (`:78-92`). `with_sentinel_body` is re-exported by `harness/emitter.py:28-30` for `adapters/_skill_writer.py:82` and `agent_harness_adapter.py:178,242,358`. `renderer.py:23` re-exports `SENTINEL` for 13 test modules, and `commands/_validation.py:22` re-exports `RULE_CALL_RE`.
- **After #54 (spec §7.4).**
  - `build_environment(template_search_paths)` loses its other parameters.
  - `render_for` gains `skill_references` and loses `template_body`; `render_inline_prompt_markdown` is new.
  - `RuleRegistryImpl.reference_for` is added, and `prompt_rule_delivery` holds `SkillReference`, `SkillReferenceIndex`, `skill_pointer_block`, `insert_pointer_block` and `includes_rules_appendix`.
  - In the eval runner, `_render_with_references` adds the `## Reference rules` section.
  - Spec:2919 says `playbook render`'s registry "stays unfiltered". P5, which the user approved, supersedes that sentence (AC.3.8).

#### AC.3.3 Decisions

- **RS-D1.** `rendering/` holds `jinja.py` (the sandbox), `formats.py` (`render_for` and its transforms), `rule_registry.py` (the `RuleRegistry` protocol and `RuleRegistryImpl`), `prompt_rule_delivery.py` and `session.py`. There is no `OutputFormat` registry and there are no per-harness format modules: the string switch has one owner, so splitting it per harness would be relocation without depth (verify-depth).
- **RS-D2.** `prompt_rule_delivery.py` moves unchanged; it is not merged into `rule_registry.py`.
- **RS-D3 (harmonised, H11).** `template_source` and `artifact_id_of` leave the sync context module in A5, for the stdlib leaf `artifacts/identity.py`: `catalog/resolve.py`, `commands/render.py` and the lockfile builder also need `artifact_id_of`, which `template_source` calls. RS-1 imports `template_source` from there, which removes rendering's only import of the sync context module and the cycle note at `rule_registry.py:10-12`.
- **RS-D4.** `RenderSession.open` filters the rules once, with `filter_applies_if` from `detector/predicate.py` (P6), and builds the registry from the kept rules only. `render_rule(rule)` still renders any rule it is given, because `playbook render <rule-id>` renders a rule whatever its `applies_if`, as it does today.
- **RS-D5.** There are two prompt renders, so today's outputs stay byte for byte. `render_prompt` is bound for adapters: it masks the `input_variables` names (today's `render_prompt_body`, `_sync_render.py:127-144`) so the adapters can map placeholders. `prompt_text` is the eval runner's: it renders with the full context, the invocation's input variables included, and appends the `## Reference rules` section.
- **RS-D6.** `TemplateContext` replaces `build_jinja_context` and the eval runner's `_render_context`, keeping today's precedence: facts, then project, then `user_choices`, then `engine_version`, then overrides. The two current orders agree under that rule: sync has no overrides, and the eval runner has no `user_choices`.
- **RS-D7.** The eval runner keeps its laziness. It opens the session with `rules=()` when the prompt lists no `includes_rules`, so a broken rule file under a task's `setup/` cannot fail that prompt (today's guarantee, `evals/prompting.py:217-222`). `_LazyRuleRegistry` is deleted.
- **RS-D8.** The registry keeps rendering included rules with the facts only (`rule_registry.py:58` merges the stored facts under the caller's `{}`). Giving it the session's full context is a behaviour change, recorded as F-R1. No shipped output would change: the only catalog rule that reads project keys is the always rule `00-project-context.md.j2`, and no prompt includes it.
- **RS-D9.** `init`'s pre-commit template does not use `RenderSession`: it renders a template file through a loader, not an artifact. That code (`precommit.py` since N9) remains the one other caller of `rendering.jinja.build_environment`.

#### AC.3.4 Interface

```python
# src/coding_agent_playbook/rendering/session.py
@dataclass(frozen=True, slots=True, kw_only=True)
class TemplateContext:
    """The Jinja context every artifact body renders with (SPEC §9.4).

    Example::

        TemplateContext.for_config(ctx.config, ctx.facts).as_dict()["project_name"]
    """

    facts: Facts
    project_name: str
    project_description: str = ""
    engine_version: str
    user_choices: Mapping[str, object] = field(default_factory=dict)
    overrides: Mapping[str, object] = field(default_factory=dict)

    @classmethod
    def for_config(cls, config: Config, facts: Facts) -> TemplateContext:
        """Sync and ``playbook render``: ``[project]``, ``user_choices``, the pinned or installed version."""

    def as_dict(self) -> dict[str, object]:
        """facts, then project, then user_choices, then engine_version, then overrides (later wins)."""


class RenderSession:
    """One sandboxed environment and one applies_if-filtered rule registry per render pass.

    Example::

        session = RenderSession.open(ctx.rules_resolved,
                                     TemplateContext.for_config(ctx.config, ctx.facts),
                                     repo_root=ctx.repo_root)
        rules = session.render_rules()
    """

    @classmethod
    def open(
        cls, rules: Sequence[Rule], context: TemplateContext, *, repo_root: Path
    ) -> RenderSession:
        """Filter ``rules`` by ``applies_if`` once; build the environment and the registry from them."""

    @property
    def registry(self) -> RuleRegistryImpl:
        """The applicable rules only; a ``RuleRegistry`` and a ``SkillReferenceIndex`` (#54)."""

    def render_rules(self) -> list[Rule]:
        """Every applicable rule with its body rendered, in input order (sync, skill references)."""

    def render_rule(self, rule: Rule) -> Rule:
        """``rule`` rendered whatever its ``applies_if`` (``playbook render <rule-id>``)."""

    def render_prompt(self, prompt: Prompt) -> Prompt:
        """The body rendered with ``input_variables`` names masked, for an adapter's format."""

    def check_inclusions(self, prompts: Sequence[Prompt]) -> None:
        """Render each included rule once now, so a sandbox violation raises before any write."""

    def render_hook_body(self, hook: Hook) -> str:
        """``HOOK.md`` verbatim, or ``HOOK.md.j2`` rendered; ``rule()`` is undefined (H19)."""

    def with_hook_body(self, hook: ResolvedHook) -> ResolvedHook:
        """``hook`` with its rendered body; a hook built in memory passes through."""

    def prompt_text(self, prompt: Prompt) -> str:
        """The eval runner's text: the body with the full context, plus the Reference rules section."""
```

Every method raises `TemplateSecurityError`, naming the template file, as today.

#### AC.3.5 PRs and file maps

**RS-1 (move-only).**

| From (post-#54 names; re-check) | To |
| --- | --- |
| `renderer.py`: `build_environment`, `render_artifact_body`, `render_string`, `TemplateSecurityError`, `render_sandboxed`, `RULE_CALL_RE` | `rendering/jinja.py` |
| `template_source` (`artifacts/identity.py` since A5) | stays there; `rendering/jinja.py` imports it |
| `renderer.py`: `FORMAT_ALIASES`, `BUILTIN_FORMATS`, `CLAUDE_READ_ONLY_DISALLOWED`, `with_sentinel_body`, `render_for`, `render_inline_prompt_markdown` (#54), `is_read_only_prompt` and the private transforms | `rendering/formats.py` |
| `renderer.py:95-108` `RuleRegistry`; `rule_registry.py` | `rendering/rule_registry.py` |
| `prompt_rule_delivery.py` | `rendering/prompt_rule_delivery.py` |
| the re-exports `harness/emitter.py:28-30` (`with_sentinel_body`, in `agent_harness/emitter.py` since N12) and `commands/_validation.py:22` (`RULE_CALL_RE`, in `validation/findings.py` since A4); `renderer.py:23`'s `SENTINEL` is already gone (N6) | deleted; every importer imports the defining module |
| `tests/unit/test_renderer.py`, `test_renderer_hooks.py`, `test_render_hook_body.py`, `test_rule_registry.py`, `test_prompt_rule_delivery.py` | `tests/rendering/` (same names) |
| `tests/unit/test_orchestrator.py:132-141` (the `template_source` tests) | already `tests/artifacts/test_identity.py` (A5) |

Doc-path map for the L9 script: `renderer.py` becomes `rendering/formats.py`, and the SPEC §9.3 sandbox mentions are hand-edited to `rendering/jinja.py`. `rule_registry.py` and `prompt_rule_delivery.py` move under `rendering/`. Expected sizes: about 170 lines for `jinja.py` and about 330 for `formats.py`, against `renderer.py`'s roughly 470 after #54 (spec:3087).

**RS-2 (interface).**

- `rendering/session.py` is new.
- `commands/_sync_render.py`: `render_artifacts` opens one session. `build_jinja_context`, `render_rule_body`, `render_prompt_body`, `render_hook_body`, `_with_body` and `_prerender_inclusions` are deleted. `RenderedArtifacts`, `SkillDescriptionOverflowError`, skill composition (including #56's guardrails skill) and the `report_*` helpers stay.
- `commands/render.py`: one session per run. `_render_rule`, `_render_prompt` and `_render_hook` call it. `_show_rules` keeps its own report of applies_if outcomes (`:153-174`), so a malformed predicate still prints `applies_if=False` instead of raising.
- `evals/prompting.py`: `_render_with_references` (#54) calls `session.prompt_text`. `_render_context`, `_prompt_environment`, `_LazyRuleRegistry` and the filter loop of `_applicable_rules` are deleted, and `_applicable_rules` is renamed `_resolved_rules`. The docstring's "Mirrors ... should converge" (`:16-17`) is deleted.
- `rule_registry.build_prompt_environment` is deleted: the session builds the environment and the registry.
- `tests/_budget_probe.render_core_rule` (#50) uses `RenderSession`.

**RS-3 (tests only).**

- `tests/fakes.py` gains `FakeRuleRegistry(fragments: Mapping[str, str] = {}, references: Mapping[str, SkillReference] = {})`, which implements `render_for_inclusion` and `reference_for`.
- It replaces the `_StubRegistry` copies in `tests/adapters/test_{continue,claude_code,opencode,shared_skills}.py`, `tests/agent_harness/test_adapter.py`, `tests/rendering/test_renderer.py`, `tests/rendering/test_prompt_rule_delivery.py` and `tests/agent_harness/test_import_roundtrip.py`: eight files at `ef19a0a`, plus any that #54 added.

#### AC.3.6 Tests

| File | Test | Asserts |
| --- | --- | --- |
| `tests/rendering/test_session.py` (new) | `test_registry_holds_only_applicable_rules` | for `gated` (applies_if false) and `open`: `registry.render_for_inclusion("gated", {}) == ""`, `registry.reference_for("gated") is None`, and `open` renders |
| same | `test_every_caller_omits_an_inapplicable_included_rule` (parametrized: sync, `playbook render <prompt> --format prompt_continue`, eval runner) | a prompt with `includes_rules: [gated, open]`: the output contains `### Open` and not `### Gated`. This is the convergence test; P5's regression test stays in `tests/cli/test_render.py` |
| same | `test_render_rules_renders_applicable_rules_in_input_order_with_the_full_context` | a templated rule reading `{{ project_name }}` renders the config's name; a gated rule is absent |
| same | `test_render_rule_renders_an_inapplicable_rule_on_request` | `render_rule(gated)` returns the rendered body |
| same | `test_render_prompt_masks_input_variable_names` | a fact named like an input variable does not replace the `{{ var }}` placeholder |
| same | `test_prompt_text_keeps_invocation_values_and_appends_reference_rules` | the invocation's input variable is substituted, and the text ends with the `## Reference rules` section |
| same | `test_check_inclusions_names_the_file_of_a_sandbox_escape` | `TemplateSecurityError.source` is the included rule's path |
| same | `test_hook_body_cannot_call_rule` | `UndefinedError` (H19) |
| same | `test_template_context_precedence` | facts < project < user_choices < engine_version < overrides |
| `tests/rendering/test_jinja.py` | `test_rendering_never_imports_the_sync_context` | importing `rendering.rule_registry` and `rendering.session` loads no `coding_agent_playbook.orchestrator`, `validation`, `commands` or `sync` module |
| `tests/unit/test_no_unsandboxed_jinja.py` | `test_only_rendering_jinja_builds_an_environment` | an AST scan of `src/`: the only call to `SandboxedEnvironment(` is in `rendering/jinja.py` |

#### AC.3.7 Acceptance criteria

1. The parity check exits 0. The eval prompt of every shipped eval task (`render_prompt(task, strict=True)` over `catalog/core/eval_tasks/*`) is byte-identical between `P` and `N`.
2. `grep -rn "build_environment(" src/coding_agent_playbook` matches only its definition, `rendering/session.py` and the pre-commit template renderer (`precommit.py`, N9).
3. `grep -rn "evaluate_predicate\|filter_applies_if" src/coding_agent_playbook/evals/prompting.py src/coding_agent_playbook/commands/render.py` matches only `commands/render.py`'s import of `evaluate_predicate` and its use in `_show_rules`.
4. `rendering/` imports nothing from `orchestrator`, `commands`, `sync`, `evals`, `agent_harness` or `adapters` (dependency-order contract). `coding_agent_playbook.rendering` is in `FORBIDDEN`, and the hot-path budget tests pass.
5. `evals/prompting.py` defines no `RuleRegistry` implementation and no Jinja context builder.
6. Sizes: `session.py` at most 250 lines, `formats.py` at most 400 and `jinja.py` at most 250. `_sync_render.py` shrinks.
7. `tests/evals/test_prompting.py`, `tests/cli/test_render.py` and `tests/cli/test_sync*.py` pass with import-only edits.
8. The full gate passes on Python 3.12 and 3.13.

#### AC.3.8 Risks

- **#54 may undo P5.** Spec:2919 tells #54's implementer that `playbook render`'s registry "stays unfiltered" and that it is now also passed as `skill_references`. Kept as written, `--format prompt_claude_command` would point at a skill reference that sync never wrote. Before #54 starts, its implementation notes must say that `_render_prompt` builds its registry from applies_if-filtered rules and passes it as both `rule_registry` and `skill_references`. This is a coordination action for the orchestrator.
- **Eval prompt drift** through context precedence or masking. Mitigation: RS-D5, RS-D6, `test_template_context_precedence` and acceptance item 1.
- **Eval laziness.** RS-D7 keeps a broken unrelated rule from failing a prompt; the existing `tests/evals/test_prompting.py` cases stay green.
- **Import time.** `rendering` loads jinja2 and yaml, so it must stay off the hot path. The `adapters/claude_rule_paths` leaf test and `test_hook_registrations.py:517` keep watching it under its new name.
- **Wide import rewrite.** RS-1 rewrites one import line in every adapter, so AH-1 and the adapters moves rebase on it.
- **`evals/prompting.py:34` still imports `orchestrator.OverlayResolver`**, an existing crossing of the dependency order, until catalog-layers moves it. RS-2 neither adds nor removes it.

#### AC.3.9 Re-check after #62

- The final #54 shapes: `build_environment`, `render_for`, `render_inline_prompt_markdown`, `RuleRegistryImpl.reference_for`, the contents of `prompt_rule_delivery`, `_prerender_inclusions`, `_render_with_references`, and `_show_rules`' delivery column (spec §7.4.9).
- #56's `RenderedArtifacts.guardrails_skill` and `compose_guardrails_skill` call (spec:3590-3591) stay on the sync side and consume `session.with_hook_body`.
- #50's `tests/_budget_probe.render_core_rule`, and whether P5's registry fix survived #54.
- `renderer.py`'s line ranges and size after #54, which RS-1's split depends on, and the number of `_StubRegistry` copies (RS-3).

### AC.4 agent-harness-roundtrip

#### AC.4.1 Goal

One package holds both directions of the Agent Harness output format (`specs/prH-agent-harness.md`, the tree the `agent_harness` adapter writes for harness clients):

- emitting the tree, through `AgentHarnessAdapter` behind the Adapter seam;
- importing a tree, through `import_harness`;
- the hook sidecar that both directions read or write;
- the `validate-harness` lint.

The parsed-tree class stops sharing its name with CONTEXT's Harness, which is `hook_runtime/event.py:51`, a coding-agent runtime.

#### AC.4.2 Today (`ef19a0a`)

- **`harness/`**: `models.py` (107 lines), `parser.py` (219), `leaf_detectors.py` (78), `manifest.py` (266), `emitter.py` (112) and `__init__.py` (13; its docstring calls the package the substrate of both directions).
- **Emit**: `adapters/agent_harness_adapter.py` (513 lines, over budget) and `adapters/_harness_hooks.py` (128), which writes `.playbook/hooks/<id>/HOOK.md`.
- **Import**: `commands/import_harness.py` (544 lines, over budget).
  - `import_harness()` (`:433-451`) is a pure transform.
  - It contains the per-kind readers (`:97-246`), the lossless path (`:247-284`), the best-effort path (`:286-432`) and the writes (`:454-512`).
  - `commands/_import_hooks.py` (85) reads the sidecar and writes `playbook/hooks/`, and `commands/_import_files.py` (52) holds file helpers.
- **Lint**: `commands/validate_harness.py:56-155` (`_Finding`, `_check_*`, `_collect_findings`, `_report`).
- **Tests import the importer from the command**: `tests/harness/test_import_roundtrip.py:29-30`, `test_manifest_roundtrip.py:13`, and one use of `_import._write_result`.
- **Name collision**: `class Harness` at `harness/models.py:100` against `hook_runtime/event.py:51`.
- **Entry point**: `pyproject.toml:59`.
- **Private crossings**: `agent_harness_adapter.py:47` and `_harness_hooks.py:21` import `adapters._skill_sources`; `commands/_import_files.py:14` imports `adapters._skill_files`; `_skill_writer.py:82` uses the `harness.emitter` re-export (RS-1 removes it).

#### AC.4.3 Decisions

- **AH-D1.** `agent_harness/` sits above `adapters` in the dependency order: it holds an Adapter implementation and imports `adapters.base`. `adapters` never imports it (RS-1 points `_skill_writer.py` at `rendering.formats`). The adapter is discovered only through its entry point.
- **AH-D2.** `Harness` is renamed `HarnessTree`, without an alias: an alias would be a second spelling (L2). The CONTEXT term Harness keeps meaning the runtime.
- **AH-D3.** The interface is `AgentHarnessAdapter` (the entry point), `import_harness`, `write_import` and `ImportResult`, `lint_harness` and `HarnessFindings`, `parse_harness` and `HarnessTree`, the manifest read and write, and `hook_sidecars`. `--strict` is a reporting choice, so it is `HarnessFindings.failed(strict=...)`, not an input to the lint.
- **AH-D4.** Manifest kinds, rule ids and every written byte stay unchanged (ADR 0001: the manifest keys on rule ids).
- **AH-D5.** The two subcommands keep one module each, `commands/import_harness.py` and `commands/validate_harness.py`, each exporting `COMMAND` (P4). This departs from the target layout's single `commands/harness.py`: the protocol has one `COMMAND` per module, and a bare `harness` names CONTEXT's Harness, the collision this candidate removes.

#### AC.4.4 Interface

```python
# src/coding_agent_playbook/agent_harness/importer.py
IMPORTED_SOURCE_PACKAGE: Final = "<imported>"

@dataclass
class ImportResult: ...  # unchanged fields (commands/import_harness.py:78-94)

def import_harness(harness_root: Path) -> ImportResult:
    """Parse the tree into canonical artifacts (lossless with the sidecar manifest); writes nothing.

    Raises ``NotAHarnessError`` without ``HARNESS.md``.
    """

def write_import(result: ImportResult, into: Path) -> None:
    """Write rules, prompts, skills, hooks and raw assets under ``into`` (was ``_write_result``)."""

# src/coding_agent_playbook/agent_harness/lint.py
@dataclass(frozen=True, slots=True)
class HarnessFinding:
    path: str
    message: str

@dataclass(frozen=True, slots=True)
class HarnessFindings:
    errors: tuple[HarnessFinding, ...] = ()
    warnings: tuple[HarnessFinding, ...] = ()

    def failed(self, *, strict: bool) -> bool:
        """Errors fail; with ``strict``, warnings fail too (``validate-harness --strict``)."""

def lint_harness(tree: HarnessTree) -> HarnessFindings:
    """Skill leaves without name or description (errors); missing routing files and
    undescribed content (warnings); opaque ``.harnessleaf`` directories are never inspected."""

# src/coding_agent_playbook/agent_harness/hook_sidecars.py (public: SPEC §10.7.2 documents the layout)
HOOKS_SIDECAR: Final = ".playbook/hooks"
def emit_hook_sidecars(...) -> list[Path]: ...                  # adapters/_harness_hooks.py:45-62
def read_hook_sidecar(path: Path, entry: ManifestEntry) -> Hook: ...  # was _import_hooks.hook_from_entry (:27-56)
```

#### AC.4.5 PRs and file maps

**AH-1 (move-only).**

| From | To |
| --- | --- |
| `harness/__init__.py`, `models.py`, `parser.py`, `leaf_detectors.py`, `manifest.py`, `emitter.py` | already `agent_harness/` (N12, now; H16) |
| `adapters/agent_harness_adapter.py` | `agent_harness/adapter.py` |
| `adapters/_harness_hooks.py` | `agent_harness/hook_sidecars.py` |
| `commands/import_harness.py:72-512` (everything but `run`) | `agent_harness/importer.py`; `_write_result` is renamed `write_import`, because it now crosses a package. If the moved body exceeds 500 lines, the best-effort walk (`:286-432`) goes to `agent_harness/_best_effort.py` in the same move |
| `commands/_import_files.py`, `commands/_import_hooks.py` | `agent_harness/_import_files.py`, `agent_harness/_import_hooks.py` |
| `pyproject.toml:59` | `agent_harness = "coding_agent_playbook.agent_harness.adapter:AgentHarnessAdapter"` (the group name is unchanged, L2) |
| `tests/harness/*.py` | already `tests/agent_harness/` (N12) |
| `tests/adapters/test_agent_harness.py`, `test_agent_harness_hooks.py`, `test_agent_harness_member_rules.py` | `tests/agent_harness/test_adapter.py`, `test_adapter_hooks.py`, `test_adapter_member_rules.py` |

- `tests/cli/test_import_harness.py` and `test_validate_harness.py` stay (L8).
- The private crossings into `adapters/_skill_sources.py` (from `adapter.py` and `hook_sidecars.py`) and `adapters/_skill_files.py` (from `_import_files.py`) are cleared by A7 (M-skill-dirs), which AH-1 waits for.
- Doc-path map: (`harness/` became `agent_harness/` in N12); `adapters/agent_harness_adapter.py` becomes `agent_harness/adapter.py`; `adapters/_harness_hooks.py` becomes `agent_harness/hook_sidecars.py`; and the `import_harness` function's mentions move to `agent_harness/importer.py`.

**AH-2 (interface).**

- `class Harness` becomes `HarnessTree` (`models.py:100`), and `parse_harness` returns it (`parser.py:53,81`). Its users are updated: the importer, the lint, `tests/agent_harness/test_models.py` and `test_parser.py`.
- `agent_harness/lint.py` is new, built from `commands/validate_harness.py:56-133`. `validate_harness.run` keeps its argument checks, its exit-code choices (`:158-189`; a malformed `HARNESS.md` is exit 1, deliberately) and the printing of `_report`, which now uses `findings.failed(strict=...)`.
- `hook_sidecars.py` gains `read_hook_sidecar`. `_import_hooks.write_hook` and `guardrail_warning` join the importer's private writes, and `_import_hooks.py` is deleted.
- The importer splits into `importer.py` (`ImportResult`, `import_harness`, `write_import`), `_lossless.py` (the manifest-entry readers), `_best_effort.py` and `_import_writes.py`, which absorbs `_import_files.py`.
- `adapter.py` drops to at most 400 lines:
  - the stateless builders move to `emitter.py` as public pure functions: `_always_rule_filename` (`:385-388`) as `always_rule_filename`, the `HARNESS.md` text of `_emit_harness_md` (`:399-443`) as `harness_md_text`, and `_inside_skill_dir` (`:508`);
  - if that is not enough, the per-kind emission methods move to a private `_emit_skills.py` that takes explicit arguments.
- `commands/import_harness.py` and `commands/validate_harness.py` have at most 60 lines each. Tests import the importer from `agent_harness.importer`, never from `commands`.

#### AC.4.6 Tests

| File | Test | Asserts |
| --- | --- | --- |
| `tests/agent_harness/test_lint.py` (new) | `test_skill_leaf_without_name_or_description_is_an_error` | one error per empty field, anchored at the leaf path |
| same | `test_missing_routing_file_and_undescribed_content_are_warnings` | two warnings, no error |
| same | `test_opaque_leaf_directory_is_never_inspected` | a `.harnessleaf` directory with bad content gives no finding |
| same | `test_strict_fails_on_warnings_only` | `failed(strict=False)` is false and `failed(strict=True)` is true for warnings only |
| `tests/agent_harness/test_hook_sidecars.py` (new) | `test_sidecar_written_by_the_adapter_reads_back_as_the_same_hook` | `emit_hook_sidecars` then `read_hook_sidecar`: same frontmatter (#57's `summary` included), unrendered body, script exec bits |
| `tests/agent_harness/test_import_roundtrip.py`, `test_manifest_roundtrip.py` (moved) | unchanged | same assertions, with imports from `agent_harness.importer` |
| `tests/agent_harness/test_adapter.py` | `test_agent_harness_entry_point_targets_the_package` | `entry_points(group="coding_agent_playbook.adapters")["agent_harness"].load() is AgentHarnessAdapter` |

#### AC.4.7 Acceptance criteria

1. The parity check exits 0 with `agent_harness` enabled and hooks on (sidecars). The probe's harness tree sits at its root (`HARNESS.md`, `skills/`, `prompts/`, `rules/`, `references/`, `.playbook/`; `agent_harness_adapter.py:65-68`). `playbook import-harness "$S/probe" --into "$S/import-P"` with `P`, and the same with `N` into `"$S/import-N"`, give trees that `diff -r` reports as identical.
2. `grep -rn "class Harness\b" src` finds only `hook_runtime/event.py:51`.
3. No module in `adapters/`, `rendering/` or below imports `agent_harness`. The two harness subcommands import only public `agent_harness` modules.
4. Sizes: `agent_harness/adapter.py` at most 400 lines, `importer.py` at most 300, every module of the package at most 400, and each of the two harness subcommands at most 60.
5. `tests/agent_harness/test_manifest_roundtrip.py` passes with import-only edits (manifest kinds and rule ids unchanged).
6. The full gate passes on Python 3.12 and 3.13.

#### AC.4.8 Risks

- **Stale entry points.** An editable install keeps the old entry-point target until it is reinstalled. Run `uv sync` after pulling AH-1; CI installs fresh.
- **The importer's line budget.** The moved body sits near 500 lines; AH-1's file map has the fallback.
- **Ordering.** P4's `COMMAND` edits to the two harness commands must land before AH-1, and RS-1 before AH-1.
- **Test folder rename.** `tests/harness/` became `tests/agent_harness/` in N12; AH-1 only adds the three adapter test files.

#### AC.4.9 Re-check after #62

- #54's `_prompt_body` (`agent_harness_adapter.py:272-301`) calls `render_inline_prompt_markdown`, together with its new test `test_prompt_leaf_bytes_unchanged_for_a_prompt_without_rule_calls`.
- #56 kept `writes_guardrails_skill` at its default `False` for `agent_harness`, with `rules/30-guardrail-<id>.md` unchanged (spec:3626).
- #57's `summary` round-trips through the sidecar.
- The sizes of the adapter and importer files, and P4's `COMMAND` objects in the two harness commands.

### AC.5 Command protocol for sync, validate, render and init

#### AC.5.1 Goal

After P4, `cli` still declares the flags of the four subcommands the chain touched. Each flag declaration moves into the command that reads it. This completes the switch, so `cli` keeps no legacy parser branch, and it cuts `cli`'s knowledge of init's private module and error type. `init`'s 582-line module becomes a package whose questions go through an injected ask function, and the pre-commit template and its merge become the root module `precommit.py`.

#### AC.5.2 Today (`ef19a0a`)

- **Flags declared in `cli.py`**: `init` at `cli.py:80-95` (with `ADAPTERS_FLAG_HELP` from the private `commands._init_adapters`, `:37`), `sync` at `:97-114`, `validate` at `:126-129` and `render` at `:131-138`. Each is bound by tuple position, `_SUBCOMMANDS[0..4]`.
- **The error map** (`cli.py:453-468`) names `init_cmd.PrecommitTemplateMissingError` (`:461`).
- **Flags are read back in the commands**: `sync.py:123,263-264`, `validate.py:419`, `render.py:240-263` and `init.py:135-164,545`, all through `getattr`.
- **`init.py` calls `input()` directly** at `:91`, `:102` and `:126`.
- **The pre-commit concept is split** between `init.py:337-440` and `commands/_precommit_merge.py` (127 lines).
- **Tests patch `builtins.input`**: `tests/cli/test_init.py:159,215,229,240,249`, `test_init_adapters.py:67` and `test_init_hooks.py:64`.

#### AC.5.3 Decisions

- **CP-D1.** This section uses P4's protocol exactly as it landed, and assumes the following of it:
  - each commands module exports `COMMAND`, with `name`, `help`, `configure(parser) -> None` and `run(args) -> int`;
  - `cli/__init__.py` keeps `main` and `cli/parser.py` keeps `build_parser` public (`tests/cli` drives `build_parser().parse_args`);
  - `COMMANDS` keeps today's `_SUBCOMMANDS` order, so `--help` lists the subcommands as today;
  - `commands/` never imports `cli/`, which is the top of the dependency order, so the `Command` type lives in `commands/` or is satisfied structurally.
- **CP-D2.** Flags move verbatim: the same `dest`, defaults, help text, `choices` and mutually exclusive groups. `sync`, `validate` and `render` keep reading `getattr(args, name, default)`, because tests build partial `Namespace` objects (for example `tests/cli/test_sync.py`). Only `init` gets a typed `InitArgs`, because its `run` is restructured anyway. Verify-depth: typed args are optional and not part of the protocol migration.
- **CP-D3.** `init` asks through `Ask = Callable[[str], str]`. The default, `console_ask`, looks up `builtins.input` at call time, so the seven monkeypatch sites keep working; new tests inject a fake.
- **CP-D4.** `precommit.py` owns the template directory, the render and the text merge. `init` computes the template variables (`commit_trailers` and `commitizen`, from the committed config, `init.py:442-464`), so `precommit.py` reads no config.
- **CP-D5.** `PrecommitTemplateMissingError` subclasses P4's shared exit-2 error type, so `cli`'s map stops naming it. Stderr (`error: <message>`) and exit 2 stay as they are.
- **CP-D6.** `init` keeps calling `commands.sync.execute` (`init.py:582`) until sync-engine gives sync an engine interface outside `commands/`.
- **CP-D7.** `commands/sync.py` is already over budget: 543 lines at `ef19a0a`, and more after #56 and #58. CP-1 adds only its roughly 20-line `configure` to it; splitting the module belongs to sync-engine.

#### AC.5.4 Interface

```python
# src/coding_agent_playbook/commands/sync.py (validate.py and render.py follow the same shape)
def configure(parser: argparse.ArgumentParser) -> None:
    """``playbook sync [--repo-root R] [--check | --check-staged]`` (SPEC §12.2); cli.py:97-114 verbatim."""


NAME: Final = "sync"  # B9's module-level protocol members (H29)
HELP: Final = "regenerate all artifacts (SPEC §12.2)"


# src/coding_agent_playbook/commands/init.py
@dataclass(frozen=True, slots=True, kw_only=True)
class InitArgs:
    """The parsed ``playbook init`` flags (cli.py:80-95), read once."""

    repo_root: Path
    non_interactive: bool = False
    name: str | None = None
    kind: str | None = None
    description: str = ""
    adapters: str | None = None
    overlays: str = ""
    no_hooks: bool = False

    @classmethod
    def from_namespace(cls, args: argparse.Namespace) -> InitArgs:
        """``getattr`` with today's defaults, so a partial Namespace still works."""


def run(args: argparse.Namespace, *, ask: Ask = console_ask) -> int: ...


# src/coding_agent_playbook/commands/_init_answers.py
type Ask = Callable[[str], str]


def console_ask(question: str) -> str:
    """``input(question)``, with ``builtins.input`` looked up at call time."""


def collect_answers(args: InitArgs, ask: Ask) -> Answers: ...


# src/coding_agent_playbook/precommit.py
# ExitTwoError: B9's shared exit-2 type, by its landed name
class PrecommitTemplateMissingError(ExitTwoError): ...


def precommit_template_dir(templates_root: Path | None = None) -> Path: ...
def render_fresh_pre_commit(
    *, output_commit: bool = False, commit_trailers: bool = False, commitizen: bool = False
) -> str: ...
# merge_pre_commit is all of _precommit_merge.py
def merge_pre_commit(content: str, *, output_commit: bool) -> MergeResult: ...
```

#### AC.5.5 PRs and file maps

**CP-1 (interface).**

- `commands/sync.py`, `validate.py` and `render.py` each gain `configure` (moved verbatim from `cli.py:97-114`, `:126-129` and `:131-138`) and `COMMAND`.
- `cli/parser.py` drops their legacy branches and the three command imports.

**CP-2 (move-only).** Flat helper modules (H6); `precommit.py` already holds the pre-commit half (N9).

| From (`commands/init.py` at `ef19a0a`) | To |
| --- | --- |
| `:50-193` (`_Answers`, `_VALID_KINDS`, `_HOOKS_QUESTION`, `_YES`, `_NO`, `_prompt`, `_prompt_multi_select`, `_prompt_yes_no`, `_hooks_answer`, `_collect_answers`) | `commands/_init_answers.py` |
| `:196-308` (`_plan_config`, `_project_meta`, `_with_hooks_answer`, `_fresh_config`, `_apply_answers`) | `commands/_init_config_plan.py` |
| `:466-526` (`_overlay_lists_to_check`, `_refuse_unusable_overlays`, `_warn_deprecated_flag_overlays`) | `commands/_init_overlays.py` |
| `:76-80`, `:310-335`, `:414-464`, `:528-582` (`_HOOK_INSTALL_COMMAND`, `_GITIGNORE_LINE`, `_write_local_config`, `_append_to_gitignore`, `_has_trailer_rows`, `_uses_commitizen`, `run`) | stay in `commands/init.py` |
| `:337-439` and `commands/_precommit_merge.py` | already `precommit.py` (N9) |
| `commands/_init_adapters.py` | stays |

- A function that `commands/init.py` imports from a helper module loses its leading underscore (`collect_answers`, `plan_config`, ...). The module's underscore is what keeps it private to `commands/`.
- `cli` keeps importing `commands.init` and `commands._init_adapters.ADAPTERS_FLAG_HELP` (the allow-list row is unchanged; CP-3 deletes it).
- Test imports: `from coding_agent_playbook.commands import init as _init` stays, so the 48 calls to `_init.run` stay. The private uses (`_prompt_multi_select` four times, `_apply_answers`, `_Answers`) follow their functions into the helper modules.
- Doc-path map: none; SPEC names these functions through `commands/init.py`, which stays.

**CP-3 (interface).**

- `commands/init.py` gains `NAME`, `HELP`, `configure` (`cli.py:80-95` verbatim, its help taken from `_init_adapters.ADAPTERS_FLAG_HELP`), `InitArgs` and `run(args, *, ask=console_ask)`.
- `commands/_init_answers.py` gains `Ask`, `console_ask` and `collect_answers(args, ask)`, and every `input(...)` becomes `ask(...)` with the same strings.
- `PrecommitTemplateMissingError` gets P4's exit-2 base.
- `cli/parser.py` drops the init branch, the `commands.init` import and the `ADAPTERS_FLAG_HELP` import; `cli/__init__.py` drops the init entry in its error map.

#### AC.5.6 Tests

| File | Test | Asserts |
| --- | --- | --- |
| `tests/cli/test_command_flags.py` (new) | `test_flag_table_is_unchanged` (parametrized: `init`, `sync`, `validate`, `render`) | the `(option_strings, dest, default, choices, nargs, help)` rows and the mutually exclusive groups of each subparser equal `tests/cli/golden/flags.json`, captured from the base commit in the same PR. Comparing structure rather than `--help` text keeps the golden independent of argparse's help formatting, which can differ between Python 3.12 and 3.13 |
| same | `test_each_command_parses_its_flags_alone` (parametrized) | a parser built from `COMMAND.configure` alone accepts today's flag sets (`--check`, `--check-staged`, `--show-rules`, `--non-interactive --name x --kind python-library`), and `--check --check-staged` exits 2 |
| `tests/cli/test_init_ask.py` (new) | `test_interactive_init_asks_through_the_injected_ask` | a scripted fake records the questions, which equal today's strings (`"Project name: "`, ...); `builtins.input` is not patched |
| same | `test_console_ask_reads_builtins_input_at_call_time` | a monkeypatch applied after import is still used |
| same | `test_init_args_from_a_partial_namespace_uses_the_flag_defaults` | `InitArgs.from_namespace(Namespace(repo_root="r"))` gives the defaults |
| `tests/unit/test_cli.py` | `test_missing_precommit_template_exits_2` (the rewrite of `:426-431`) | raising `precommit.PrecommitTemplateMissingError` prints the same `error:` line and returns 2 |

#### AC.5.7 Acceptance criteria

1. The parity check exits 0. A fresh `timeout 180 playbook init --non-interactive --name probe --kind python-application </dev/null` gives byte-identical trees (`.pre-commit-config.yaml` included) and stdout with `P` and with `N`.
2. `grep -n "add_argument" src/coding_agent_playbook/cli/*.py` finds only `--version`. `cli/` imports no `commands._*` module and no `PrecommitTemplateMissingError`; it reaches `init` only through B9's `_COMMANDS`.
3. Each of `commands/sync.py`, `validate.py`, `render.py` and `init.py` defines `NAME`, `HELP` and `configure`. A flag's `dest` is read only in the module that declares it: for example, `grep -rn '"check_staged"' src` finds only `commands/sync.py`.
4. `commands/init.py` and each `commands/_init_*.py` module have at most 300 lines, and `grep -rn "input(" src/coding_agent_playbook/commands/init.py src/coding_agent_playbook/commands/_init_*.py` finds only `console_ask`.
5. `commands/sync.py` grows by at most 20 lines against its post-#62 size.
6. The full gate passes on Python 3.12 and 3.13.

#### AC.5.8 Risks

- **Flag drift** while moving the declarations. Mitigation: the structural golden and `test_each_command_parses_its_flags_alone`.
- **Hand-built `Namespace` objects** in tests. CP-D2 keeps `getattr` reads, and `InitArgs.from_namespace` keeps the defaults.
- **The `input` monkeypatches.** CP-D3 keeps them working.
- **P4 lands with other names or shapes.** CP-1 and CP-3 then use what landed; AC.5.9 lists what to check.

#### AC.5.9 Re-check after #62

- P4's protocol module path, the `Command` constructor or structural form, the name of the exit-2 base, the `COMMANDS` mechanism, and whether `_SUBCOMMANDS` survives (`tests/unit/test_docs_lifecycle_hooks_cli.py:35`, `tests/unit/test_docs_readme_hooks.py:25`).
- No chain ticket added a flag to `sync`, `validate` or `render`. The sizes of `sync.py`, `validate.py` and `render.py` after #52, #54, #56 and #58.
- The `tests/unit/test_committed_config.py:313` pin (moved to `tests/config/test_committed.py` by N10) names `commands/_init_config_plan.py` after CP-2.

### AC.6 Follow-ups recorded, not scheduled

- **F-R1.** The registry renders included rules with the session's full template context, as skill references are rendered (RS-D8). This is a behaviour change with no change to shipped output. Test: `test_included_rule_renders_with_the_session_context`.
- **F-G1.** One definition of the hook-artifact list: `HOOK_ARTIFACTS` (`guard_config.py:156-160`) against `DEFAULT_HOOK_ARTIFACTS` (`hook_runtime/protected.py:68-72`). This needs a decision on dropping support for files written before the table existed (GC-D7).
- **F-C1.** `init` stops importing `commands.sync`, once sync-engine gives sync an interface outside `commands/` (CP-D6).
- **F-E1.** `evals/compile/compiler.py` (was `evals/_compile.py`) stays at 619 lines after N23, over the ~500-line budget. Its split (the default-expr rule defined once, `iter_leaves`) changes code, so it is not a move; L12 schedules no evals deepening. Budget exception recorded here until a follow-up is approved; N23 must not grow the file.
- **F-E2.** `evals/run/harness_runner.py` (was `evals/runner.py`) stays at 503 lines after N23. The target layout's split into `workspace.py` and `results.py` is not scheduled (the explicit `as` re-export forms at `runner.py:44-45` become plain imports in N23, 6.3.4: the module uses both names and nothing imports them from it); a verbatim split could be a later move-only PR after N23. Budget exception recorded here; N23 must not grow the file.

## 10. Risks

| # | Risk | Mitigation |
| --- | --- | --- |
| R1 | Rebase churn with the chain: a now-move rewrites import lines in files an open ticket edits. | The wave rule (2.2, per package since question 3) keeps every now-move out of chain-edited packages and allows only soft overlaps; timed merges and the replay protocol (7.1.3); the cumulative map makes `apply` one command; `test_tree_has_no_stale_module_paths` tells a rebased ticket exactly what to run. |
| R2 | A same-name module-to-package move (`config`, `detector`, `lockfile`, `catalog`, `cli`, `hook_runtime.git`, `hook_runtime.config`, `hook_runtime.state`, `hook_runtime.shell`, `hook_runtime.dispatch`) keeps the old name importable, so `engine_module()` passes and a "not loaded" pin tests the whole package. | The pins are listed per PR in 5.3.3 and renamed by hand (H24); reviewers check the list. Module-object imports of the old name (`from coding_agent_playbook import catalog`) are rewritten by R-IMPORT's same-name-conversion rule (5.4.2). The package must replace the module in the same PR (7.1.2 rule 12), which is why A10 moves `hook_runtime/dispatch.py`. |
| R3 | A stale editable install after an entry-point value change makes adapter discovery fail locally while CI stays green. | Every PR that changes a value says so and re-installs before the gate (5.3.2). |
| R4 | A move adds an import to the hook hot path (a package `__init__` with code, a non-leaf module). | Docstring-only inits (`test_package_inits.py`); the derived `FORBIDDEN`; the stack contract; `STDLIB_LEAVES` changes only on purpose (6.2). |
| R5 | The rewrite script rewrites what is not a module (adapter ids, overlay labels, `hook_runtime.harness`, bare consumer-file names) or misses a dotted string. | The rules and exclusions of 5.4.2-5.4.3 with a test each; bare names are only reported; `check` runs in pytest. |
| R6 | `ruff format --check .` also formats the Python code blocks of markdown files, and a rewritten import path can need a reflow in SPEC.md. | The script runs `ruff format` on every markdown file it changes (R-FORMAT). |
| R7 | The custom private-modules contract uses `importlinter.application.contract_utils`, which is not documented API. | import-linter is pinned exactly (`==2.15`, D0-5); an upgrade is its own PR that re-runs `tests/architecture/`. |
| R8 | A chain ticket that lands after T0.2 adds a private import or a top-level module and turns CI red. | The coordination notes of 7.1.3 for #52 and #58; the contract tests print the expected lists. |
| R9 | Large mechanical codemods (A2: 111 importers; A10: 218; A11: 173; N25: about 60) overload one review. | Each is a pure script run; the reviewer checks the map, the `check` output and the gate. |
| R10 | `_ENGINE_PATHS` and the SPEC §5.1 tree are not full paths, so the script cannot keep them in step. | Each PR that 5.3.5 lists edits both by hand; the docs test fails otherwise. |
| R11 | Test files that move while a chain ticket edits them (`tests/harness/*`, `tests/hooks/*`). | Chain-edited test files stay in place until #62 (`tests/unit/test_sources_filesystem_bundled.py` moves in A4, `tests/hooks/` in A13); before N12, `git diff origin/main...<open ticket branch> -- tests/harness` is checked empty. |
| R12 | #54 restores the unfiltered `playbook render` registry and undoes B1. | The coordination note to #54 (7.1.3); B1's four tests then guard it. |
| R13 | Out-of-tree hook handlers break when A10/A11 move `registry`, `decision` and `event`. | L2 does not pin them, so they move with no shim; A10 and A11 add a MIGRATION.md entry for handler authors, and the script's generated "Module paths" section lists the new paths. |
| R14 | Python 3.12 and 3.13 differ in path handling (`Path.resolve()` on symlink loops raises on 3.12). | The gate runs on both versions; no move changes path logic. |
| R15 | The full suite takes more than an hour locally, so lane 0 was verified on a subset. | CI gives the verdict on both versions; the designer's mutation checks (0.4) cover the contracts. |
| R16 | CF-2's real types expose annotation errors that `Any` hid. | Fix annotations only; a needed code change is reported, not made (7.7). |
| R17 | `validation/context.py` (H4) collects `SyncContext` and the config-less helpers and could exceed the line budget. | A5 measures it; if it exceeds 480 lines, `SyncContext` takes its own public module `validation/sync_context.py`. |

## 11. Harmonisation notes

### 11.1 Choices made where the inputs disagreed

| Id | Topic | Inputs | Decision and reason |
| --- | --- | --- | --- |
| H1 | Wave rule (**withdrawn 2026-10-18**: question 3 chose package granularity, L1 as written; it had amended L1 and ADR 0002 with file granularity plus timed soft overlaps) | The root mapper put a row after the chain when a remaining ticket edits the file or its destination package is after the chain; the adapters mapper when the file is in an open ticket's touched list or most importers are chain files; the hooks mapper allowed soft overlaps; the now-designer kept anything that edits a chain file for after #62. | Withdrawn. H1 let a module of a chain-edited package move now when no open ticket edits that file, so the notebook check, `_eval_paths`, the gate-weakening judge and `_git_parse` would have moved now (N14, N15, N18). Under L1 as written they move after #62 with the rest of N8-N11, N13-N21, N23 and N24 (2.2, 7.2.2). `hooks_config.py` still moves now in N2: it is a root module no open ticket edits. What remains of H1 is the soft-overlap protocol for the now-moves: import lines, dotted strings and single pin lines in chain files, timed (2.2, 7.1.3). The adapters mapper's after-chain call stands for `_owned_files`, `_skill_sources` and `_skill_files` (A7): the adapters package is the chain's busiest area. |
| H2 | Layer order | Five orders: the contracts designer's (verified), the root, adapters, hooks and grading mappers'. | The designer's order (it holds on the baseline), with `metrics_gate` in its own layer below `skills` (H5). `hook_runtime` stays a separate stack, not a layer (the root and hooks mappers drew it as one); the stack contract enforces the same direction and also bans third-party imports. |
| H3 | Home of the twin-shared judges | The target layout, the root mapper (`security/gate_weakening.py`) and the commands mapper's notes said `security/`; the hooks mapper and the now-designer said `hook_runtime/judges/`. | `hook_runtime/judges/` (N14, N15): the judges import `hook_runtime` (`caps`, `decision`, `globs`, `shell`, `_git_parse`), and `security` is a stdlib leaf imported by the hot path, so `security/` would need a two-way dependency. This amends L3: question 1, resolved 2026-10-18. |
| H4 | Home of `SyncContext` | The target and the root mapper: `sync/context.py`. The commands mapper: anywhere below validation, not `sync/`. | `validation/context.py` (A5): `validate`, `check`, `render`, `eval` and the validation helpers import it, and sync sits above validation. That module already holds `config_less_context`, which builds a `SyncContext`. Internal design, not a product decision (L14). |
| H5 | Place of `metrics_gate` | The contracts designer: in the evals tier. The root, hooks and grading mappers and the after-designer (GC-D5): below hooks. | Below `skills`, above the config tier: `hooks/guard_config/_tables_quality` reads `[metrics]` through `metrics_gate.config`, and `metrics_gate` imports only `config`, `grading` and the leaves. |
| H6 | Shape of `commands/` | The target and both designers: packages `commands/init/`, `eval/`, `check/`, `twins/ci/`. The commands mapper: flat modules, `twins/` only. | Flat modules with `_<command>_<topic>.py` helpers; `commands/twins/` is the one subpackage (Guard twin is a CONTEXT term). Under L5 a package per command would make `from coding_agent_playbook.commands import init` (62 test files) import a docstring-only package. So the designer's `commands/eval/command.py` (B.12.6) and `commands/init/command.py` (CP-2, CP-3) become `commands/eval.py` and `commands/init.py`. |
| H7 | Shape of `cli/` | The root mapper: `cli/__init__.py` (`main`) plus `cli/parser.py`. The commands mapper and both designers: one `git mv`, `main` and `build_parser` in `__init__`. | The root mapper's shape (N7): `git mv cli.py cli/parser.py`, `main` and its error mapping in `cli/__init__.py`, plus `__main__.py`. L2 forces only `main` into `cli/__init__.py`, so L5's second exception covers only that; the test importers of `build_parser` and `_SUBCOMMANDS` are a script rewrite like every other move (review finding, 2026-10-18). |
| H8 | Home of the copyable-source-file rule | The target and the after-designer: `adapters/skill_dirs/source_files.py`. The adapters mapper: `generated_output/source_files.py`. | `generated_output/source_files.py` (A7): sync's hook script copies, the harness importer and the skill writer all use it, and a leaf serves every one of them without an ordering constraint. |
| H9 | The `types.py` <-> `metrics_config` cycle | The root mapper: move `ruff_config_flags` into grading. The grading mapper: move `MetricConfig` into `metrics_gate/config.py`. | `MetricConfig` moves (N22): only the gate side reads it, and it takes its `FIXTURE_GLOBS` import out of the kernel. |
| H10 | The guard_config writer | The root mapper's A5: `hooks/guard_config/writer.py` plus `_tables_*`. The after-designer's GC-2: `compile.py`, `inputs.py`, `resource_roots.py`, `ruff_probe.py`, `_tables_*`, and the adapter-dependent parts to the sync side. | GC-2's map, with the sync-side parts in `sync/_protect.py` and `sync/_hook_scripts.py` because A6 lands first. Root A5 folds into GC-2. |
| H11 | Home of `template_source` | The after-designer (RS-D3): `rendering/jinja.py`. The root mapper: `artifacts/identity.py` with `artifact_id_of`. | `artifacts/identity.py` (A5, before RS-1): `template_source` calls `artifact_id_of`, which `catalog/resolve.py`, `commands/render.py` and the lockfile builder also need; a leaf serves all of them. |
| H12 | `_plugin_registry.py` naming | The target and the contracts designer: `_plugin_registry`. The root mapper: `plugin_registry.py`, reading rule 2 as "root underscore modules are imported only by root modules". | The contracts designer's rule: a root-level underscore module is engine-private, so any engine module may import it. The name stays; the module is not scheduled. |
| H13 | Home of committed-config planning | The commands mapper: merge into `config/files.py`. | Its own `config/committed.py` (N10), because B2 grows `config/files.py`. |
| H14 | Judge module names | The hooks mapper: `deps.py` (merging `_dependency_tiers` and `_manifest_diff`), `notebooks.py`, and `_sink_scan` into `handlers/feedback/` after the chain. The now-designer (B5): `dependency_tiers.py`, `manifest_diff.py`, `sink_scan.py` now. | Plain renames (`dependency_tiers.py`, `manifest_diff.py`, `notebook_check.py`; a merge is a deepening), and `sink_scan.py` moves now with `trusted_artifact_line`, because the twin `scan_sinks` uses it. B5 folds into N14. |
| H15 | Home of `LAUNCHER_TOKEN` | The hooks mapper: `hooks/registrations/claude.py`. The adapters mapper: a stdlib leaf of `hooks/registrations`. | A new stdlib-only `hooks/registrations/launcher.py` (A18): the Claude settings merge imports it and keeps its stdlib-only closure pin, which importing `claude.py` would break. |
| H16 | Agent Harness moves | The adapters mapper: `harness/` now (M-AH1), the adapter later (M-AH2). The commands mapper: the importer and lint after the chain, merging `_import_hooks` into the sidecar module during the move. The after-designer: AH-1 moves everything. | `harness/` moves now (N12). AH-1 carries the adapter, the sidecars, the importer and the import helpers; `_import_hooks.py` moves verbatim and merges in AH-2; `lint.py` is created by AH-2 with its interface. |
| H17 | `templates/hook_shims/` timing | The root mapper: now. The hooks mapper: after the chain with the registrations. | After the chain (A18): `_TEMPLATE_DIR` lives in `hook_registrations`, whose facade importers are chain files. |
| H18 | Tests of root modules | The commands mapper: `tests/precommit/`. The root mapper: `tests/unit/`. | `tests/unit/` (N9: `tests/unit/test_precommit.py`). |
| H19 | `tests/hooks/` | The after-designer put `tests/hooks/guard_config/` beside the hook-pack tests. The hooks mapper empties `tests/hooks/` first. | A13 empties it; GC-2 and A17 wait for A13, so `tests/hooks/` holds only the sync-time `hooks/` tests (L8). |
| H20 | Order of the orchestrator split and the rendering move | The root mapper: A3 (here A5) before rendering. The after-designer: RS-1 moves `template_source` itself. | A5 before RS-1 (H11). |
| H21 | PR ids and lane-0 scope | Mapper and designer ids overlapped (`M1` meant two different PRs, `B1` too). No input specified the rewrite script beyond its features. | One id scheme (table 11.2). T0.0 specifies the script (5.4). T0.1 gains the root mapper's `-m cli` pin test. |
| H22 | The `_skill_writer.py:78-79` re-export ladder | The adapters mapper: a later deepening PR. | A3 removes it with its pin test: L2 allows no re-export. |
| H23 | `STDLIB_LEAVES` under the moves | The contracts designer's list is the baseline's. | It evolves move by move (6.2): `catalog` -> `catalog.roots` (N3), `detector.*` (N4), `lockfile` absorbs two leaves (N5), `generated_output.atomic_io` and `generated_output.sentinel` (N6; dotted, because A7's `source_files.py` is not a leaf), `artifacts.path_classes` (N15), `artifacts.path_globs` (A12). |
| H24 | Same-name module-to-package conversions | The guard of T0.1 resolves names, so it cannot see that a module became a package. | Each such move renames its pins by hand; the list is in 5.3.3 and R2. |
| H25 | `playbook render` and #54 | The chain spec §7.3 keeps the registry unfiltered; SPEC §6.2.5 and §12.7 and L12 call it a bug. | B1 follows SPEC; #54 is told before it starts (7.1.3). |
| H26 | config-files remainder | L12 lists config-files as "now"; deleting `_typing.py` cannot run before #62 (its importers are chain files). | CF-2 runs after the chain as the remainder of the approved candidate. |
| H27 | SK-1 | Not a candidate in L12. A3 makes the `skills -> adapters` type-only edge visible. | A small types-only PR so the engine-layers baseline reaches its end state; it changes no behaviour. |
| H28 | README architecture overview | The root mapper: one manual refresh in the last move PR. | Its own docs PR (D1) after every move. |
| H29 | Shape of the Command protocol | The now-designer (B9): each command module is the command (module-level `NAME`, `HELP`, `configure`, `run`; no object). The after-designer (CP-1, CP-3): a `COMMAND` object per module, "as P4 landed". | B9's module-level form; section 9 reads every `COMMAND` as those four members (the after-designer deferred to what B9 lands). |

### 11.2 Id map

| Input | Their id | This spec |
| --- | --- | --- |
| Contracts designer | T0.1, T0.2, T0.3 | T0.1, T0.2, T0.3 (T0.0 added) |
| Root mapper | M1, M2, M3, M4, M5, M6, M7, M8 | N1, N2, N3, N4, N5, N6, N7, N15 |
| Root mapper | A1a, A1b, A2, A3, A4, A5, A6, A7, A8 | A1, A2, A3, A5, RS-1, GC-2, CF-2, A4 (links checker), A6 (git_client) |
| Commands mapper | NOW-1, NOW-2, NOW-3, NOW-4, NOW-5 | N7, N8, N9, N10, N11 |
| Commands mapper | AFTER-1, AFTER-2, AFTER-3 | A4, A6, AH-1 (+ AH-2 for the lint) |
| Adapters mapper | M-AH1, M-CC1, M-AD1, M-AD2, M-AH2 | N12, N13, A8, A9, AH-1 |
| Adapters mapper | "the generated_output/ PR", "the skills/ PR" | A7, A3 |
| Hooks mapper | HS-1, HS-2, HS-3, HS-4, HS-5, HS-6, HS-7, HS-8 | N14, N15, N17, N18, N19, N20, N16, N21 |
| Hooks mapper | HS-10a, HS-10b, HS-11, HS-12, HS-13a, HS-13b, HS-13c, HS-14a, HS-14b | A10, A11, A12, A13, A14, A15, A16, A17, A18 |
| Grading mapper | M1, M3, M2a, M2b, B1 | N22, N23, N24, N25, B8 |
| Now-designer | B1-B4b, B5, B6-B10; M-config, M-twins, M-metrics-gate, M-grading, M-cli, M-eval | B1-B4b, N14, B6-B10; N2 (+N10), N8, N22, N25, N7, N11 |
| After-designer | P0, P1, P2, P3, P4, P5, P6, M-hooks, M-skill-dirs | lane 0, B2, N16 + B3 + B4a, N22, N7 + B9, B1, N4, A17 + A18, A7 |
| After-designer | GC-1..GC-4, RS-1..RS-3, AH-1, AH-2, CP-1..CP-3 | unchanged |

## 12. Open questions (resolved 2026-10-18)

Each was a product decision the inputs could not settle. The user answered all of them on 2026-10-18; section 2.3 lists where the spec applies each answer.

1. **Where do the twin-shared judges live?** The approved layout (L3) puts the dependency, sink, notebook and gate-weakening judges in `security/`. They import `hook_runtime` (`caps`, `decision`, `_hosts`, `globs`, `_git_parse`, `shell`), and `hook_runtime` imports `security`, so `security/` would need a two-way package dependency, which ADR 0002 forbids, or a rewrite of the judges into stdlib-only code that returns plain findings and leaves message text to each adapter, which puts the byte-exact hook messages at risk. **Resolved 2026-10-18:** the default is adopted: public modules in a new `hook_runtime/judges/` package (N14, N15), amending L3 for these judges only (H3).
2. **What does sync do with an invalid `[metrics]` value in the committed config?** Today sync silently writes the default quality-lint rows into `guard_config.json`, while `playbook metrics` exits 2, and sync cannot raise where it reads the table (its adapters have already written). The options for a follow-up after #62 were (a) `playbook validate` reports it as an error, so sync refuses before writing anything; (b) sync prints one `warning:` line and keeps the defaults. **Resolved 2026-10-18:** option (a), the default. A follow-up after #62 makes `playbook validate` report the invalid value as an error, so sync refuses before writing; B2 keeps today's behaviour and pins it with a test, so the change is a one-line diff.
3. **Does the wave rule's file granularity stand (H1)?** (Also asked as question 15.) L1 and ADR 0002 say that packages the open chain touches move after the chain merges. H1 applied that per file, with timed soft overlaps in chain-edited files. The open tickets edit files in four packages that "now" PRs moved from: `hook_runtime` (`handlers/_ruff_buckets.py`, `ruff_feedback.py`, `docstring_nonregression.py`, the new `skill_nudge.py`, `registry.py`), `commands` (`render.py`, `validate.py`, `_sync_*`), `evals` (`prompting.py`) and `adapters` (`base.py`, `claude_code_adapter.py`, `opencode_adapter.py` and others). **Resolved 2026-10-18:** package granularity, L1 as written; H1 is withdrawn. N8, N9, N10, N11 (commands), N13 (adapters), N14-N21 (hook_runtime), N23 and N24 (evals) move to after #62 with their other blockers unchanged, and so do the PRs that wait on them: B2 (via N10), B3, B4a and B4b (via N16), B6, B9 and B10 (via N8, N11 and N14), N25 (via N24) and B8 (via N25). What stays now: lane 0 (T0.0, T0.1, T0.2), N1-N7, N12, N22, B1 (it must merge before skills ticket #54 starts) and B7. Each of these was re-checked against the open chain's touched files (7.2.1): none moves code out of or into a package an open ticket edits, so none moved. A14 gains N14 and N15 as blockers, so the pack split still follows the judge moves (7.6 A14).
4. **Which packages get a CONTEXT.md term?** ADR 0002 names each top-level package after a glossary concept and cites `config/`, `sync/` and `validation/` among them, but CONTEXT.md defines no Config, Sync or Validation term, and some packages are named after something that is not a glossary concept at all. `agent_harness/` is named after the Agent Harness output format (`specs/prH-agent-harness.md`), and its name sits close to the glossary's Harness ("A coding-agent runtime"). Proposed per package (each added by the PR that creates the package, or recorded as an ADR 0002 exception):
   - `agent_harness/`: **Agent Harness tree**, "the directory tree the agent_harness adapter writes for Agent Harness clients and `import-harness` reads back; it is not a Harness" (N12);
   - `config/`: **Consumer config**, "the committed config file and the machine-local overrides file in a consumer repo that steer sync and the hooks" (N2);
   - `sync/`: **Sync**, "one `playbook sync` run: resolve the catalog, render every adapter's Generated output and write the Lockfile" (A6);
   - `validation/`: **Validation**, "the checks `playbook validate` and the sync gate run over canonical artifacts before anything is written" (A4);
   - `commands/`, `security/` and `precommit.py`: an ADR 0002 exception, recorded in ADR 0002 by D1: `commands/` holds the CLI subcommands (an implementation layer, not a domain concept), `security/` the stdlib-only secret, PII and path judges plus the trust store, `precommit.py` the pre-commit template, and none of them is a term a reader of the domain needs.

   **Resolved 2026-10-18:** the default is adopted, with one correction: the first draft of the Consumer config definition named a wrong path. The config files are `.coding-agent-playbook.toml` (committed) and `.coding-agent-playbook.local.toml` (machine-local), and CONTEXT.md entries carry no paths, so the definition above names neither. N12 adds the Agent Harness tree term (it removes the clash with Harness), N2, A4 and A6 add Consumer config, Validation and Sync, and D1 records the three exceptions.
5. **Is the PR granularity right?** (Asked as question 16.) **Resolved 2026-10-18:** keep this spec's PR granularity, the 72 PRs of section 7.
