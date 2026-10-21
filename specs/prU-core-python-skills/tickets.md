# prU: tickets

Generated from the verified mapping data during design; since implementation started it is edited by hand (see [implementation-runbook.md](implementation-runbook.md)). Decisions: [../prU-core-python-skills.md](../prU-core-python-skills.md).

| Wave | Tickets | Note |
| --- | --- | --- |
| 0 | L0-00 | bootstrap the integration branch |
| 0b | L0-00b | eval sample rename before any other ticket (D68) |
| 1 | L0-01, L0-02, L0-03, L0-04, L0-19, L0-21, L0-25, L0-26, L0-27 | independent engine pieces and test-pin restructuring; parallel; framework choice (D57); inert-hook logging and harness hints (D79); the --judge-samples flag (D80) |
| 2 | L0-05, L0-08, L0-20, L0-23 | in-skill discovery and rendered rules/ path; parallel (both touch validation/_skills.py in different functions); Domino detection (D51); layout adapter (D71) |
| 3 | L0-06, L0-09, L0-10, L0-22, L0-24 | layout checks, section schema, agent_harness; parallel; layout guard and always rule (D61, D71); prompt sets (D76) |
| 4 | L0-07, L0-11, L0-12 | mechanical move + D36 check, sectioned index, impact tag; parallel |
| 5 | L0-13, L0-14, L0-17, L0-18 | core skill directory gates and provenance gates; parallel; template fact-matrix test and nudge ranking (round 5) |
| 6 | L0-15, L0-16 | sections and priorities for the moved rules, web-application skill; parallel; needs the per-skill mapping merged into the spec |
| 7 | C-python-coding-01, C-python-coding-02, C-python-coding-03, C-python-coding-04, C-python-coding-05, C-python-coding-06, C-python-coding-07, C-python-coding-refs, C-python-testing-01, C-python-testing-02, C-python-testing-refs, C-python-tooling-01, C-python-tooling-refs, C-ml-data-01, C-ml-data-02, C-ml-data-refs, C-web-application-01, C-web-application-02, C-web-application-03, C-web-application-04, C-web-application-refs, C-web-application-example, C-design-patterns-01, C-design-patterns-02, C-design-patterns-03, C-design-patterns-04, C-design-patterns-refs, C-python-architecture-01, C-python-architecture-02, C-python-architecture-03, C-python-architecture-refs, C-python-documentation-01, C-python-documentation-02, C-python-documentation-refs, C-domino-apps-01, C-domino-apps-02, C-domino-apps-03, C-domino-apps-refs, C-domino-jobs-01, C-domino-jobs-02, C-domino-jobs-03, C-domino-jobs-04, C-domino-jobs-refs, C-domino-agents-01, C-domino-agents-02, C-domino-agents-03, C-domino-agents-refs, C-domino-agents-example, C-playbook-creator-01, C-playbook-creator-02, C-playbook-creator-refs, D-01, D-02, D-03, D-04, C-frameworks-layout, C-prompts-v2 | content lanes (generated separately, follow content_ticket_template) and the docs lane, all in parallel worktrees |
| 8 | F-01 | opt-in eval comparison (implemented, not run; D30 as amended) |
| 9 | F-02 | final-state checks, full CI-parity gate, one PR into main |

Every ticket is implemented in its own fresh-context subagent running `/mattpocock-skills:implement` at medium effort; the tickets of one wave run in parallel (D33).

## Engine, docs and final tickets

### L0-00: refactor(plugins)!: remove the python_design bundled plugin and record prU

Lane lane0, size S, depends on nothing; decisions D2, D12, D13, D33.

Create branch integration/core-python-skills from main and commit the state that already exists in the working tree: the python_design plugin, its tests and every live reference removed (SPEC 11.5.2 tombstone, MIGRATION v0.21 'Removed bundled plugin' entry, ci.yml wheel-smoke, pyproject ruff exclude, roots.py docstring), plus specs/prU-core-python-skills.md, ADR 0004, ADR 0005, the ADR 0001 amendment line and the CONTEXT.md glossary edits. Two commits: the breaking removal, then docs(adr) for the spec and ADRs. Every later ticket branches from here.

- `catalog/plugins/python_design/**`: already deleted in the working tree; commit the deletion (scripts and worked-example.md stay recoverable at f7ece8b0 for lanes design-patterns and python-architecture)
- `tests/plugins/python_design/**`: already deleted; commit
- `.github/workflows/ci.yml, pyproject.toml, src/coding_agent_playbook/catalog/roots.py, SPEC.md, README.md, MIGRATION.md, CONTEXT.md, catalog/README.md, tests/_budget_probe.py, tests/_catalog.py, tests/catalog/test_roots.py, tests/cli/test_sync_skill_root_move.py, tests/cli/test_validate_links.py, tests/cli/test_validate_skills.py, tests/integration/conftest.py, tests/integration/test_core_skills.py, tests/integration/test_resources_self_contained.py, tests/integration/test_ruff_scope.py, tests/validation/test_preflight.py`: existing uncommitted edits from the removal; commit as they are after a re-read
- `specs/prU-core-python-skills.md, docs/adr/0004-upstream-python-guidance-is-vendored-into-core.md, docs/adr/0005-member-rules-live-in-their-skills-rules-directory.md, docs/adr/0001-scoped-rules-are-delivered-as-skill-references.md`: commit in a separate docs(adr) commit
- test `whole suite`: no new test; the removal must leave every remaining test green

Acceptance:
- Branch integration/core-python-skills exists and holds exactly two new commits on top of main.
- git ls-files catalog/plugins/python_design tests/plugins/python_design prints nothing.
- rg -n 'python_design' src catalog tests finds no live reference (tombstone text in SPEC.md and MIGRATION.md only).
- ruff check ., ruff format --check ., mypy and pytest -q pass on Python 3.12, cache-free, without optional extras.
- No CLAUDE.md, .claude/, AGENTS.md, .opencode/, .agents/ or shared_skills/ file is committed; commits are authored by the configured user with no Co-Authored-By trailer.
- No GitHub tracker or ticket issue is created before the owner says to start (D33).

### L0-00b: refactor!: rename eval tasks to eval samples everywhere

Lane lane0, size M, depends on L0-00; decisions D68.

D68: one scripted rename, run right after L0-00 and before every other ticket: catalog/<layer>/eval_tasks/ -> eval_samples/ (git mv), the prompts' eval_tasks: key -> eval_samples:, EvalTask -> EvalSample and every derived name, CLI help and messages, hook eval-task-authoring-lint -> eval-sample-authoring-lint, SPEC, README, MIGRATION (one entry; no compatibility alias) and tests. No behavior change.

- `catalog/core/eval_tasks/ -> catalog/core/eval_samples/`: git mv
- `src/coding_agent_playbook/evals/**`: rename types, functions and messages
- `catalog/core/prompts/*`: eval_tasks: -> eval_samples:
- test `tests/**`: renamed fixtures and assertions; a test that no eval_task spelling remains outside MIGRATION's history

Acceptance:
- git grep -i -E 'eval[_ ]?tasks?|EvalTask' returns only MIGRATION history lines and the glossary's Avoid line.
- playbook eval --list reports the same 23 samples as before.
- The full gate passes.
- Each sample's task.toml is renamed sample.toml (D68 'everywhere').

### L0-01: feat(validation): report malformed rule frontmatter as errors naming the file

Lane lane0, size M, depends on L0-00, L0-00b; decisions D21, D17, ADR 0005.

Today Rule.from_markdown builds RuleFrontmatter(**data) (src/coding_agent_playbook/artifacts/rule.py:70-73), so an unknown key such as impact: or section: raises a TypeError while SyncContext loads (validation/context.py:305), before any check runs; the CLI catches only FileNotFoundError, ConfigError, HookSchemaError, ExitTwoError and CatalogMissingError (cli/__init__.py:59-69), so validate and sync die with a traceback that does not name the file. scope is never validated (validation/_skills.py:154 only tests == 'scoped'; a typo becomes an always-loaded rule in the Claude Code and AGENTS.md adapters) and priority is never type- or range-checked (rule.py:29; a string crashes the sort, a negative breaks Continue's {priority:02d} name). Add RuleLoadError (path + problem + allowed keys) for an unknown key, a missing required key, a missing --- fence or a non-mapping frontmatter; a tolerant collect_rules() mirroring collect_hooks (catalog/source.py:69-83, prK P8c) so validate reports every bad file; a CLI handler; shape checks for scope (always|scoped), priority (int, not bool, 0-99) and the new optional section field (str | None, dropped from markdown when None so every existing file stays byte-identical).

- `src/coding_agent_playbook/artifacts/rule.py`: RuleFrontmatter.section: str | None = None; RuleLoadError(Exception) carrying path and problem; from_markdown checks keys against dataclasses.fields before construction and wraps the split_frontmatter ValueError
- `src/coding_agent_playbook/catalog/source.py`: ArtifactSource.collect_rules() concrete default wrapping list_rules; FileSystemArtifactSource.collect_rules() returns (rules, errors) per file without raising
- `src/coding_agent_playbook/validation/context.py`: SyncContext.rule_load_errors filled on the tolerant path validate already takes (from_repo/from_config :229-342); sync, check and render raise
- `src/coding_agent_playbook/validation/_frontmatter.py`: check_rule_shape(rules): scope literal, priority int 0..99 with bool rejected, section a kebab-case string when set; each message carries the value and the expected shape
- `src/coding_agent_playbook/validation/checks.py`: _artifact_errors (:362-390) reports load errors and shape errors
- `src/coding_agent_playbook/cli/__init__.py`: catch RuleLoadError -> 'error: <path>: <problem>' and exit 2
- test `tests/artifacts/test_rule_load_errors.py`: new: unknown key, missing required key, no fence, non-mapping frontmatter each raise RuleLoadError whose message names the path, the key and the allowed keys; section round-trips; a rule without section renders byte-identical markdown
- test `tests/catalog/test_source.py`: collect_rules never raises and returns one error per bad file plus every good rule; list_rules raises RuleLoadError
- test `tests/cli/test_validate_rule_frontmatter.py`: new: validate exits 1 with 'FAIL playbook/rules/x.md: unknown frontmatter key 'impact' ...' and no 'Traceback' in output; sync exits 2 with 'error: ...x.md'; scope 'Scoped' and priority 'high', true, -1, 100 each fail with the value named

Acceptance:
- A repo-local rule with impact: HIGH makes playbook validate exit 1 with one finding naming the file and listing the allowed keys; stderr holds no Traceback.
- playbook sync, check and render on that repo exit 2 with an 'error:' line naming the file.
- scope values other than always/scoped, and priorities that are not an int in 0-99 (bool included), are validation errors naming the value.
- Every shipped core rule still loads; git diff --stat catalog/ is empty.
- section: is accepted on any rule and rendered nowhere yet.
- ruff check ., ruff format --check ., mypy, pytest -m catalog and the listed tests pass.

### L0-02: feat(detector): add has_dependency and any_dependency predicates

Lane lane0, size S, depends on L0-00, L0-00b; decisions D23, D8, D40, D78.

D23 gates rules on libraries that are neither frameworks nor ML stack (pydantic-settings, pandera, pyjwt, anyio, argon2-cffi): today they are reachable only through has_dev_dependency, and runtime ones not at all (detector/predicate.py:61-67, :101-176). Add applies_if keys has_dependency (all) and any_dependency (any) over runtime and dev dependency names, PEP 503-normalized, in the single seam evaluate_predicate that validate, sync, guard-config applicability rows, the resync hook and the coverage gate share; add the Jinja global has_dependency(name) next to has_framework and has_ml_dep (rendering/jinja.py:73-84) so templates need no 'dependencies is defined' guard. Document both in SPEC 6.4 and 9.4 in this ticket (docs pin precedent: tests/unit/test_docs_lifecycle_hooks_spec.py:267-269); D-01 does not touch those rows again.

- `src/coding_agent_playbook/detector/predicate.py`: two branches using one helper _canonical_keys(facts, *fields) = canonical names of facts['dependencies'] and facts['dev_dependencies'] (has_dev_dependency shares it); value shape via _coerce_string_list; all/any per key from one explicit _LIST_COMBINERS map; public LIST_PREDICATE_KEYS; docstring list of keys
- `src/coding_agent_playbook/rendering/jinja.py`: env.globals['has_dependency'] and env.globals['python_at_least'] (a malformed version names the helper)
- `src/coding_agent_playbook/commands/check.py`: the skip reason imports LIST_PREDICATE_KEYS instead of keeping its own copy, so has_dependency, any_dependency, any_file (and has_ml_stack, any_ml_stack) are quoted as written (D23, D78(10)); D-01 does not touch it again
- test `tests/cli/test_check.py`: the skip reason quotes each new list key as written
- `SPEC.md`: 6.4 operator list and 9.4 helper list gain the two keys and the helper (only these rows)
- test `tests/detector/test_predicate.py`: runtime-only, dev-only, both, absent facts, PEP 503 spelling (Pydantic_Settings vs pydantic-settings), all vs any, a non-list value raises ValueError
- test `tests/rendering/test_jinja.py`: has_dependency true/false with and without the dependency facts, under StrictUndefined
- test `tests/unit/test_docs_lifecycle_hooks_spec.py`: SPEC 6.4 documents has_dependency and any_dependency
- test `tests/cli/test_validate_applies_if.py`: a misspelled key still fails; any_dependency given a string fails with the shape message

Acceptance:
- applies_if {any_dependency: [pandera]} holds when pandera is only a runtime dependency and when only a dev dependency, and fails in an empty repo.
- {% if has_dependency('anyio') %} renders in a .md.j2 rule without an 'is defined' guard.
- Every pre-existing predicate test passes unchanged.
- SPEC 6.4 lists both keys and the docs pin passes.
- A Jinja helper python_at_least('3.11') compares versions numerically (3.9 < 3.10 < 3.11) and returns False when python_version is undefined, so templates fall back to the 3.10 branch (D40).
- catalog/core/rules/languages/python/typing.md.j2 stops comparing python_version as a string and uses python_at_least('3.12').
- A new any_file predicate is true when at least one listed path exists (D78(10)).

### L0-03: test(catalog): split the core-skill pins per skill and derive counts

Lane lane0, size M, depends on L0-00, L0-00b; decisions D13, D21, D33.

Seven content lanes run in parallel; today each would edit the same pins: EXPECTED_MEMBERSHIP, EXPECTED_WHERE, the member tuples, PYTHON_CODING_MEMBER_COUNT and DISTILLED_RULES in tests/integration/test_core_skills.py (:54-255), _ENGINE_RULE_COUNT = 28 and _ENGINE_SKILL_COUNT = 5 in tests/catalog/test_source_bundled.py (:41-44), and the literal known-skills strings in tests/cli/test_validate_skills.py:34 and tests/cli/test_sync_validate_gate.py:239,270-271. Pure test refactor, no behaviour change: one pins module per core skill under tests/core_skill_pins/ (discovered with pkgutil, so adding a skill edits no shared file), counts derived from the rule and skill files on disk, known-skills strings computed from the core skills that declare a playbook block (the helper tests/unit/test_docs_migration_skills.py:93-101 already uses), plus a kept-id table (the 7 ids hooks and prompts depend on) and the 4 retired ids.

- `tests/core_skill_pins/__init__.py`: new: CoreSkillPins(skill_id, where, members in index order, probe_inactive, rules: Mapping[str, RulePin(applies_if, globs, priority)]) and ALL_PINS discovered via pkgutil.iter_modules
- `tests/core_skill_pins/python_coding.py, python_testing.py, python_tooling.py, ml_data.py`: new: today's values moved out of test_core_skills.py; each DISTILLED_RULES row becomes a RulePin of its skill (paths are no longer pinned)
- `tests/_catalog.py`: core_rule_skill_ids(); KEPT_RULE_IDS (python-typing, python-error-handling, python-docstrings, python-dependency-injection, python-pure-core -> python-coding; pytest -> python-testing; ml-serialization-security -> ml-data); RETIRED_RULE_IDS (python-performance-idioms, python-classes-and-protocols, ml-dtypes-and-typing, ml-reproducibility-and-testing)
- `tests/integration/test_core_skills.py`: read ALL_PINS; remove the EXPECTED_* constants, member tuples and DISTILLED_RULES; membership asserted as 'each scoped core rule appears in exactly one pins module, whose skill_id is the rule's skill'
- `tests/catalog/test_source_bundled.py`: rule count derived from the rule source files on disk; skill count derived from core skill dirs holding SKILL.md and equal to ALL_PINS plus the plain skills
- `tests/cli/test_validate_skills.py, tests/cli/test_sync_validate_gate.py, tests/unit/test_docs_migration_skills.py`: known-skills strings built from core_rule_skill_ids()
- test `tests/integration/test_core_kept_ids.py`: new: each kept id exists in its skill; the 5 hooks keep linked_rule and the 7 prompts keep includes_rules exactly (D16); a retired id, while it still exists, keeps its original skill (absence is asserted in F-02)

Acceptance:
- Every old assertion of test_core_skills.py and test_source_bundled.py has a successor; pytest -m catalog passes.
- Adding tests/core_skill_pins/<skill>.py requires no edit to any other test file.
- No literal 28 or 5 pins the engine rule or skill counts; no literal known-skills string remains under tests/cli.
- No file outside tests/ changes.

### L0-04: test(budget): raise the core description budgets and measure the Where map

Lane lane0, size S, depends on L0-00, L0-00b; decisions D18, D35, D54, D59.

D18: the core description total goes from 2,000 to 2,400 characters and the listing cap (core plus each bundled plugin) from 6,000 to 6,500; the per-skill cap stays 300. D35: lane 0 measures always-loaded context with every core skill's 'Where guidance lives' line; if 800 words (always sections plus the map) or 1,500 (AGENTS.md) would be exceeded, the playbook.files phrases get shorter and the caps stay. Add a worst-case test that composes the map over every core skill that declares playbook.files, independent of which members the probe activates, so it keeps measuring as lanes add skills.

- `tests/integration/test_context_budget.py`: CORE_DESCRIPTIONS_MAX_CHARS = 2400 (:36), LISTING_MAX_CHARS = 6500 (:37), test names and messages cite prU D18; new worst-case map test
- `tests/plugins/mattpocock_skills/test_budget.py`: LISTING_BUDGET_CHARS = 6_500 (:32); test name and comment cite prU D18
- `tests/_budget_probe.py`: helper that builds WhereEntry rows for every core skill with a files phrase
- test `tests/integration/test_context_budget.py`: test_where_map_with_every_core_skill_within_800_words: the two always sections plus where_guidance_section over every core skill's files phrase <= 800 words

Acceptance:
- The two budget constants read 2400 and 6500 and cite D18; the 300-char per-skill constant and the 800/240/1,500-word caps are unchanged.
- The worst-case map test passes with today's four lines and needs no edit when a skill is added.
- Budgets per D54: core descriptions at most 2,800 characters and core plus each bundled plugin at most 7,000 on the standard probe; a second probe repo with Domino markers checks the worst case with its own caps: 3,400 characters of core descriptions and 7,500 for core plus each bundled plugin (D59).

### L0-05: feat(catalog): discover member rules in skills/<skill>/rules with implicit membership

Lane lane0, size M, depends on L0-01, L0-03; decisions D5, D21, ADR 0005, ADR 0001.

list_rules walks only <layer>/rules/** (catalog/source.py:277-281, :322-332) and _iter_skills records only scripts/ and references/ (:165-186), so a rule inside a skill directory is invisible. Walk each layer's skills/<dir>/rules/**/*.md{,.j2} for skill dirs that hold SKILL.md, keeping layer order (engine, overlays, extra roots, repo-local; inside a layer rules/ first, then skills/*/rules/), so override-by-id (catalog/resolve.py:144-172) stays correct. Membership comes from the directory: the loader records the home skill (the sibling SKILL.md id, skills/naming.py skill_id_of) on the Rule and fills frontmatter.skill when it is absent, so every consumer keeps working unchanged (is_skill_member, member_rules_of, the lint_codes skill label, the skill-nudge table, the agent_harness manifest). Rules from another layer still join through skill:. Reword V1 and W1 (validation/_skills.py:83-86, :356-359) for location-first membership and update the MIGRATION V1 quote that tests/unit/test_docs_migration_skills.py:103-110 pins; fix the guard-generated-outputs hint that names only playbook/rules/<id> (hook_runtime/handlers/protect/guard_generated_outputs.py:157). No core file moves here.

- `src/coding_agent_playbook/catalog/_skill_rules.py`: new (keeps source.py, 370 lines, small): iter_skill_rule_files(skills_root) -> (skill_id, path) pairs, dot dirs skipped like _iter_md_files
- `src/coding_agent_playbook/catalog/source.py`: list_rules/collect_rules interleave <layer>/rules and <layer>/skills/*/rules per layer label; _iter_skills unchanged (rules/ is never byte-copied)
- `src/coding_agent_playbook/artifacts/rule.py`: Rule.home_skill: str | None (to_dict/from_dict default None); to_markdown never writes an injected skill
- `src/coding_agent_playbook/validation/_skills.py`: SCOPED_RULE_NEEDS_SKILL_MESSAGE and the W1 text name the skill's rules/ directory; module docstring
- `src/coding_agent_playbook/hook_runtime/handlers/protect/guard_generated_outputs.py`: hint names playbook/rules/<id> or playbook/skills/<skill>/rules/<id>
- `MIGRATION.md`: the V1 quote only (line ~972)
- `tests/_catalog.py, tests/hook_runtime/handlers/pack_repo.py, tests/unit/test_rules_lint_codes.py`: one core_rule_paths() walker over catalog/core/rules and catalog/core/skills/*/rules; core_rules() injects the home skill; engine_rules() (pack_repo.py:138-142) and ENGINE_RULES (test_rules_lint_codes.py:37) use it
- test `tests/catalog/test_source_skill_rules.py`: new: playbook/skills/s/rules/r.md is a member of s without skill:; a repo-local in-skill rule with a core id overrides core; overlay order kept; a skill dir without SKILL.md contributes no rule (R4 reports it in L0-06)
- test `tests/skills/test_membership.py`: location membership equals skill: membership
- test `tests/cli/test_validate_skills.py, tests/cli/test_sync_validate_gate.py`: new V1/W1 wording
- test `tests/hook_runtime/handlers/protect/test_guard_generated_outputs.py and tests/fixtures/hook_payloads/claude_code/pre_tool_use/ggo_bash_redirect_agents_md.expected.json`: new hint text

Acceptance:
- A rule at <repo>/playbook/skills/<id>/rules/<rule>.md without skill: is synced into that skill's output with a lockfile entry of kind=rule.
- A repo-local rule with the id of a core in-skill rule overrides it, and render --show-source shows the collision.
- frontmatter.skill of every core rule is unchanged and catalog/core is byte-identical.
- MIGRATION.md quotes the new V1 text verbatim and the docs pin passes.

### L0-06: feat(validation): check the rules/ layout of every layer

Lane lane0, size M, depends on L0-05; decisions D21, D5, ADR 0005.

Deterministic layout checks from D21 and ADR 0005, each naming the file and the fix: R1 a rule inside skills/x/rules/ that declares skill: y (y != x) is an error; R2 the file name minus .md/.md.j2 equals the id for every rule inside a skill's rules/ (all layers) and for every engine-layer rule, where an always rule may carry an NN- priority prefix (00-project-context, 10-python-house-style); R3 two files with the same id in one layer fail, naming both paths (today the later one silently wins as a same-package Collision); R4 a rules/ directory under a skill dir without SKILL.md, or under a skill without a playbook: block, is an error instead of being skipped; R6 an always rule inside a skill's rules/ gets a move hint instead of V3's 'remove skill'. Overlay and repo-local <layer>/rules/ files keep free names, so consumers see no churn. R5 (D36) lands with the move in L0-07.

- `src/coding_agent_playbook/validation/_rule_layout.py`: new: R1-R4 and R6 over artifact_source.collect_rules() grouped by source_package plus layer_roots('skills')
- `src/coding_agent_playbook/validation/checks.py`: wire check_rule_layout into _artifact_errors
- test `tests/validation/test_rule_layout.py`: new: one passing and one failing fixture per check, messages asserted verbatim (path, id, hint); an override across layers is not a duplicate
- test `tests/cli/test_validate.py`: the engine checkout's config-less validate still exits 0

Acceptance:
- Each of R1-R4 and R6 has a failing fixture with exactly one finding naming the file, the offending value and the fix.
- Duplicate ids in two layers are not reported; duplicates inside one layer are, with both paths.
- playbook validate in the engine checkout reports no new finding.

### L0-07: refactor(catalog): move the 26 scoped core rules into their skills' rules directories

Lane lane0, size M, depends on L0-05, L0-06; decisions D5, D13, D21, D36.

Mechanical move, no content change and no priority change: each scoped rule goes from catalog/core/rules/{languages/python,frameworks,ml}/ to catalog/core/skills/<current skill>/rules/<id>.md[.j2] (python-coding 12, python-tooling 6, python-testing 3, ml-data 5; fastapi-* and pydantic-boundaries are re-homed in L0-15), and its skill: line is removed; the two always rules stay in catalog/core/rules/always/ (D21). Add R5 (D36): an engine-layer scoped rule outside a skill's rules/ is an error whose hint reads 'move it to catalog/core/skills/<skill>/rules/<id>.md' (forge #170, or whichever of the two merges second, must follow). Update every test that reads paths under catalog/core/rules.

- `catalog/core/rules/languages/python/*.md*, catalog/core/rules/frameworks/*.md*, catalog/core/rules/ml/*.md*`: 26 git mv to catalog/core/skills/{python-coding,python-testing,python-tooling,ml-data}/rules/<id>.md[.j2] (e.g. typing.md.j2 -> python-coding/rules/python-typing.md.j2, serialization-security.md.j2 -> ml-data/rules/ml-serialization-security.md.j2); drop the skill: line
- `src/coding_agent_playbook/validation/_rule_layout.py`: R5, engine layer only
- `src/coding_agent_playbook/hook_runtime/handlers/feedback/_ruff_buckets.py`: the path in the comment near :97
- `tests/integration/test_core_skills.py`: inventory pin (:311-316) allows a rules/ dir of <id>.md[.j2] files; path assertions use core_rule_paths()
- `tests/catalog/test_source_bundled.py`: engine rules lie under catalog/core/rules/always or catalog/core/skills/*/rules
- `tests/unit/test_distilled_content_policy.py`: _SCANNED_SOURCES (:70) and test_policy_scan_covers_every_core_rule_and_prompt (:91-96) cover skills/*/rules
- test `tests/validation/test_rule_layout.py`: R5 passing and failing fixtures with the exact hint
- test `tests/integration/test_core_move_is_output_neutral.py`: new, temporary until L0-15: the reference probe's synced tree equals a committed digest list taken before the move (SKILL.md, member files, Continue files, AGENTS.md)

Acceptance:
- find catalog/core/rules -type f lists exactly the two always rules.
- Every core in-skill rule's file stem equals its id and none declares skill:.
- The reference probe syncs to byte-identical output before and after the move.
- git diff -M --stat shows 26 renames whose only content change is the removed skill: line.
- Adding a scoped rule under catalog/core/rules makes playbook validate fail with the move hint.

### L0-08: feat(skills): render member rules as rules/<id>.md inside each skill

Lane lane0, size M, depends on L0-03; decisions D5, D22, ADR 0005.

D5 and ADR 0005: the rendered skill gets the same rules/ directory as the source, and references/ is left to free-form documents. Change the one path constant (artifacts/member_reference.py:22-33, E16), which the writer (adapters/skill_dirs/writer.py:387), the lockfile split (sync/_dispatch.py:266-280), prompt pointer lines (rendering/rule_registry.py:116) and index links (skills/document.py:279-281) all use; reword the generated text: index heading '## Rules' and its lead (document.py:39-40), the Where lead and lint line (:43-49), the 'Before you start' step 'Load skill `x` and read its rule `rules/<id>.md`' (rendering/prompt_rule_delivery.py:96-104); V13 forbids an authored '## Rules' heading (validation/_skills.py:80, :235-239) and V12 (:341-351) is removed because a hand-written references/<id>.md can no longer collide with a member; the four core SKILL.md bodies say 'Picking rules' and 'rules index'. The next sync deletes pristine old references/<id>.md copies through the lockfile leftover policy (sync/_leftovers.py); a test proves it. MIGRATION text goes to D-04.

- `src/coding_agent_playbook/artifacts/member_reference.py`: _RULES_DIR = 'rules'; docstrings and examples
- `src/coding_agent_playbook/skills/document.py`: index heading, lead, Where lead, lint line, docstrings
- `src/coding_agent_playbook/rendering/prompt_rule_delivery.py`: load_step says 'rule'/'rules'; docstrings
- `src/coding_agent_playbook/validation/_skills.py`: V12 removed; V13 forbids '## Rules'
- `src/coding_agent_playbook/adapters/claude_code/adapter.py, adapters/opencode.py, adapters/shared_skills.py, adapters/skill_dirs/writer.py, adapters/base.py, rendering/formats.py, rendering/rule_registry.py, commands/render.py`: docstrings and comments that spell references/<id>.md
- `catalog/core/skills/{python-coding,python-testing,python-tooling,ml-data}/SKILL.md`: 'Picking references' -> 'Picking rules', 'references index' -> 'rules index'
- test `tests/sync/test_rules_dir_migration.py`: new: a repo synced with the old layout (lockfile rows <root>/<skill>/references/<id>.md, kind=rule, pristine files) re-syncs to rules/<id>.md and loses the pristine copies; an edited copy is kept with the usual leftover message
- test `tests/cli/test_render.py (:107-119), tests/cli/test_sync_skill_root_move.py (:63-72), tests/integration/test_core_skills.py (:552-554, :589, :596-613), tests/cli/test_sync_core_skills.py, tests/cli/test_sync_tooling_references.py, tests/integration/test_core_python_tooling.py (:40-45)`: rules/ paths and wording
- test `tests/rendering/test_prompt_rule_delivery.py, tests/adapters/test_skill_writer_member_references.py, tests/skills/test_document.py, tests/skills/test_document_sections.py, tests/sync/test_dispatch.py, tests/validation/test_skills.py, tests/cli/test_validate_skills.py`: synthetic samples use rules/; V12 cases removed; V13 heading
- test `tests/hook_runtime/handlers/protect/test_guard_generated_outputs.py`: a .claude/skills/<s>/rules/<id>.md file is guarded as generated (lockfile kind=rule), never confused with Claude Code's .claude/rules/

Acceptance:
- On the reference probe every member is written at <root>/<skill>/rules/<id>.md in .claude, .opencode and .agents, byte-identical across roots, lockfile kind=rule; no member file is written under references/.
- Claude Code and OpenCode commands with includes_rules say 'read its rule `rules/python-typing.md`' (or 'rules' for several).
- rg -n 'references/' src/coding_agent_playbook/artifacts src/coding_agent_playbook/skills src/coding_agent_playbook/rendering finds no member-path spelling.
- The migration test passes on Python 3.12.
- In Continue's output, a member rule's links to its skill's references/ render as plain file names, because Continue receives no references (D46.9).

### L0-09: feat(validation): declare skill sections and check section keys and priority bands

Lane lane0, size M, depends on L0-01, L0-08; decisions D17, D21, D32, ADR 0005, D47.

D17: a skill's playbook: block gains an ordered sections: list (id, title, impact, summary); each member names its section:; priority = impact band + rank, with bands CRITICAL 20-39, HIGH 40-59, MEDIUM 60-79, LOW 80-99. Add the model in skills/sections.py (Impact enum with its band, SkillSection, skill_sections(skill)) and the checks: S1 shape (a list of mappings with exactly id/title/impact/summary; id kebab-case and unique; title one line of at most 40 chars; impact in the enum; summary one line); S2 sections ordered CRITICAL to LOW; S3 a member's section names a declared section of its skill (the message lists the ids); S4 a member of a sectioned skill without section:, from any layer, including a rule joining by skill:, is an error; S5 section: on an always rule or on a member of a skill without sections is an error; S6 a member's priority lies in its section's band; S7 an authored [CRITICAL|HIGH|MEDIUM|LOW] tag in a member's first heading is an error (the tag is rendered, D32). A declared section without members is not a validate finding (it would print on every sync while lanes fill skills); F-02 adds a core-only test for it. Skills without sections behave as today.

- `src/coding_agent_playbook/skills/sections.py`: new: Impact, IMPACT_BANDS, SkillSection, skill_sections(skill)
- `src/coding_agent_playbook/validation/_sections.py`: new: S1-S7
- `src/coding_agent_playbook/validation/_skills.py`: _BLOCK_KEYS adds 'sections' (:65), V8 message lists it
- `src/coding_agent_playbook/validation/checks.py`: wire the section checks
- test `tests/skills/test_sections.py`: new: parsing, bands, ordering, malformed blocks read as no sections
- test `tests/validation/test_sections.py`: new: one failing fixture per check with the exact message; a sectionless skill reports nothing new
- test `tests/validation/test_skills.py`: V8 names sections as an allowed key

Acceptance:
- Each S-check has a fixture producing exactly one finding that names the file or skill label, the value and the allowed values or band.
- A repo-local rule joining a sectioned skill through skill: without section: fails with the skill's section ids listed.
- No core skill declares sections yet, and playbook validate on the engine checkout is unchanged.
- A rule from another layer that joins a sectioned skill without section: is not an error: validate warns, naming the file and the skill's sections, and the rule lands in an engine-generated 'Other' section listed last (D42).
- Priority bands are enforced only for skills that declare sections (D46.8).
- Every entry of playbook.sections declares a one-line open_when; a missing or empty open_when is a validation error naming the skill and section (D47).
- playbook.references entries (path, open_when, optional applies_if) are validated: the path exists under references/ or examples/, every file under references/ and examples/ except license files is listed, and applies_if uses the rule predicate language (D47).
- List-typed predicate keys (any_framework, any_ml_stack, any_dependency) given a bare string in a rule, reference or example applies_if are a validation error naming the file, not a render-time crash.

### L0-10: feat(agent_harness): emit member rules under skills/<id>/rules and import them back

Lane lane0, size M, depends on L0-01, L0-05, L0-08; decisions D22, D5, D17.

D22: agent_harness writes scoped rules to its root references/<id>.md (agent_harness/adapter.py:237-249), its skill leaf holds only SKILL.md, scripts/ and references/ (_emit_skills.py:44-93), import-harness maps root references/*.md to scoped rules (_best_effort.py:157) and writes every rule to playbook/rules/ (_import_writes.py:121-133). Emit each member rule at skills/<skill>/rules/<id>.md (description frontmatter, sentinel, rendered body, as today) when its skill is emitted; drop the root references/ routing file when nothing is left there; the manifest records the new path and the rule's section for a lossless round trip. Import: lossless writes the rule to playbook/skills/<skill>/rules/<id>.md when that skill comes from the same harness, else to playbook/rules/<id>.md with skill:; best-effort reads skills/<s>/rules/*.md as members of s and still reads old root references/*.md with the existing warning. The parser, leaf detectors, lint and validate-harness accept a skill leaf's rules/ (markdown only). The leaf SKILL.md keeps the authored body (no generated index), as today.

- `src/coding_agent_playbook/agent_harness/adapter.py (:237-287), _emit_skills.py, emitter.py, manifest.py, _lossless.py, _best_effort.py, _import_writes.py, parser.py, leaf_detectors.py, lint.py, models.py`: per-skill rules/ output, manifest section field, import placement, parser support
- test `tests/agent_harness/test_adapter_member_rules.py, test_manifest_roundtrip.py, test_import_roundtrip.py, test_adapter.py, tests/cli/test_import_harness.py, tests/cli/test_validate_harness.py, tests/agent_harness/fixtures/**`: new layout; round trip with section
- test `tests/agent_harness/test_rules_dir_migration.py`: new: a harness synced with the old layout and re-synced loses the pristine root references/<id>.md through the lockfile

Acceptance:
- Emit, lossless import, then sync reproduces byte-identical rule sources (section included) for an in-skill rule and for a playbook/rules rule with skill:.
- A harness tree has no root references/ when every scoped rule is a member.
- validate-harness accepts skills/<id>/rules/*.md and rejects a non-markdown file there with a message naming it.
- agent_harness SKILL.md files carry the same generated, section-grouped index as the other skill trees (D46.7).

### L0-11: feat(skills): group the rules index by section and name sections in the Covers clause

Lane lane0, size M, depends on L0-09; decisions D17, D18, D32, D47, D58.

D17 rendering for skills that declare sections. MemberReference gains section and impact (to_dict/from_dict default None), members sort by (section order, priority, id), and the index renders '## Rules', its lead, then for each section with at least one active member '### <title> [<IMPACT>]', the section summary and a table '| Rule | Requires |' with one row '| [<id>](rules/<id>.md) | <name>: <description> |' (pipes escaped, text on one line). The Covers clause names the active sections' titles in declared order, each with its first letter lowercased unless its first word holds another capital (FastAPI, HTTP, SQLAlchemy stay), and never truncates; V11 measures the description with every declared section and errors over 300 chars; W3 applies only to sectionless skills, which keep the member-name Covers clause and the flat index (skills/document.py:115-235, validation/_skills.py:290-386).

- `src/coding_agent_playbook/artifacts/member_reference.py`: section and impact fields
- `src/coding_agent_playbook/skills/membership.py`: member_reference (:91-106) fills section/impact; sectioned ordering in _composed_skill
- `src/coding_agent_playbook/skills/_rules_index.py`: new: grouped renderer and the section-label helper; document.py dispatches and passes labels to covers_clause/compose_description
- `src/coding_agent_playbook/validation/_skills.py`: _ComposedParts, V11 and W3 for sectioned skills
- test `tests/skills/test_rules_index.py`: new: two sections, an inactive section vanishes, escaping, ordering, impact tags in headings
- test `tests/skills/test_document.py`: Covers with sections, the lowercasing rule ('Mocking' -> 'mocking', 'FastAPI wiring' kept), no 'and N more'
- test `tests/validation/test_skills.py`: V11 over every declared section; W3 silent for sectioned skills
- test `tests/integration/test_core_skills.py`: the probe test counts table rows as well as list lines (:552-554)

Acceptance:
- A sectioned skill whose members are partly gated renders only sections with an active member, in declared order, each with its impact tag, summary and table.
- Its composed description is '<authored>. Covers <a>, <b>. Use when <use_when>.' naming only active sections; validate errors when every declared section would exceed 300 chars.
- Sectionless skills render byte-identically to before.
- The Covers clause lowercases section titles except words with an inner capital (FastAPI, HTTP); the index table has two columns, rule and what it requires (D46.7).
- The 'Other' section of D42 renders last.
- SKILL.md renders, after the authored body: the fixed 'How to use this skill' paragraph, then 'Rules' (one heading per active section with its [IMPACT], its open_when line, then the two-column table), then 'References and examples' from the playbook.references entries whose applies_if passes, each with its open_when (D47).
- The fixed paragraph reads: open a reference or example when a rule names it or its open-when line matches the change (D58).

### L0-12: feat(rendering): render the [IMPACT] tag in each member rule's title

Lane lane0, size S, depends on L0-09; decisions D32, D17, D30.

D32: the tag in '# Title [IMPACT]' comes from the rule's section, never from the source. Add section_impacts(skills, rules) -> {rule_id: impact} in skills/sections.py and an impacts mapping on RenderSession.open (rendering/session.py:107-128) that appends ' [IMPACT]' to the first ATX '# ' heading outside code fences of each listed rule's rendered body, so the skill rules/ files, Continue's rule files, agent_harness rule files and every prompt's 'Reference rules' appendix agree. Callers: sync/render.py render_artifacts (:120) and evals/prompting.py _task_session (:152-163), which loads the source's skills for it; commands/render.py shows the tag for render <rule-id>.

- `src/coding_agent_playbook/skills/sections.py, rendering/session.py, sync/render.py, evals/prompting.py, commands/render.py`: impacts map computed once per render pass and applied after Jinja
- test `tests/rendering/test_impact_tags.py`: new: first heading only, never inside a fence, idempotent, absent for always rules and sectionless skills
- test `tests/evals/test_prompting.py`: the appendix body carries the tag for a sectioned fixture skill; every shipped task still renders strictly (:55-62)
- test `tests/adapters/test_continue.py`: the Continue rule file shows the tag

Acceptance:
- For a member of a HIGH section, rules/<id>.md, .continue/rules/NN-<id>.md and the eval appendix all show '# <Title> [HIGH]'.
- No rule source contains the tag (S7 enforces it).
- Prompt and eval appendices render no [IMPACT] tag; they stay byte-identical while D16 freezes prompts (D46.8).

### L0-13: test(catalog): let core skills ship rules, references, scripts and examples

Lane lane0, size M, depends on L0-07; decisions D2, D19, D20, D25, D26, D48, D58, D78.

D2, D19, D25, D26: core skills will hold rules/, references/ (long-form documents, the LICENSE copies, python_design's worked-example.md) and scripts/ (detect_smells.py, lcom4_clusters.py, layer_map.py). Relax the pins that allow only SKILL.md: tests/integration/test_core_skills.py:311-316 (directory inventory), :373-391 (SKILL.md plain markdown: allow relative links to its own references/*.md, nothing else), :431-447 (references one level deep; a rule body may link ../references/<file>.md of its own skill); tests/catalog/test_source_bundled.py:57-64 (engine skills may have references_dir and scripts_dir). Add core_skill_root(skill_id) to tests/_catalog.py as the core twin of plugin_root, for script tests under tests/core_skills/<skill_snake>/; give core scripts ruff's py310 target (pyproject.toml:160 covers only catalog/plugins/*/skills/*/scripts/*.py); bound every core scoped rule's size also with every-gate-on facts, so rules the reference probe never activates (sqlalchemy, uv, pydantic-settings) are measured too.

- `pyproject.toml`: per-file-target-version adds "catalog/core/skills/*/scripts/*.py" = "py310"
- `tests/_catalog.py`: core_skill_root()
- `tests/_budget_probe.py`: every_gate_facts(): every framework the detector knows, numpy/pandas/polars/torch, pydantic-settings, anyio, pytest-asyncio, package_manager uv, python_version 3.13
- `tests/core_skills/__init__.py`: new package for the script tests the lanes add
- test `tests/integration/test_core_skills.py`: allowed entries {SKILL.md, rules/, references/, scripts/}; rules/ holds only <id>.md[.j2]; references/ one level, .md plus the two LICENSE.* names; scripts/ only .py; every relative link in a core rule or SKILL.md resolves inside the same skill dir
- test `tests/unit/test_core_rule_shapes.py`: second parametrization with every_gate_facts() (100 lines, 750 words)
- test `tests/integration/test_ruff_scope.py`: config half asserts the py310 glob; behaviour half proves it on a scratch core script

Acceptance:
- A scratch core skill with references/x.md, scripts/y.py and a rule linking ../references/x.md passes every catalog gate; a link into another skill fails with the path named.
- ruff check suggests no 3.12-only rewrite (UP040/UP046/UP047) for a catalog/core/skills/*/scripts/*.py file.
- core_skill_root('python-coding') equals CORE_ROOT / 'skills' / 'python-coding'.
- examples/ is a synced skill directory like scripts/ and references/ (source walker, writer, agent_harness); an examples entry whose applies_if fails is neither listed nor written (D48).
- A dedicated CI job runs every core example's own tests in an isolated environment built from the example's pyproject.toml (no engine dependency); the normal pytest run never imports example code.
- Ruff lints example code at the py310 per-file-target-version; consumer pytest never collects it because skill roots are dot-directories.
- A reference whose applies_if fails is neither listed nor written, exactly like an example (D58).
- The one-level references check flags only a directory segment after references/ (real nesting), not the bare string, so a rule may show a skill tree (D78(16)).

### L0-14: test(catalog): enforce vendored-core provenance, license copies and the ATTRIBUTIONS mapping

Lane lane0, size M, depends on L0-07; decisions D1, D11, D19, D31, ADR 0004, D38, D78.

ADR 0004, D1, D19, D31: retire the fresh-text policy and enforce the vendored one. The self-containment scan exempts from the marker check exactly references/LICENSE.python-best-practices and references/LICENSE.python-clean-architecture inside core skills (URLs still scanned; tests/integration/test_resources_self_contained.py:144-160 exempts only ATTRIBUTIONS.md today), and a test pins their bytes: SHA-256 5f2aed106f011d7f40db3a248ada7456350188c72a2e3aa8768ef251415fdc5c (1,078 bytes, Ludo Technologies LLC) and 80c4860b8cedcb4efa41ef98e33e3e79a43314442444b3470c3d68cae66025f8 (1,066 bytes, MKToronto). Rewrite catalog/core/ATTRIBUTIONS.md: a header (text is vendored and adapted, license copies per skill, Continue gets none), one section per source with the D11 pins (pbp tag v0.8.0 commit fa0d3f58afb8bf56c028bb559e0e7bc1538e079a; pca commit 9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce) and license line, and inside it one sub-table per core skill ('| Upstream file | Core files | Changes |'; DROP rows '| path | DROP | reason |') so parallel lanes never edit the same table; an 'Engine-written files' list per skill seeded with today's files; the 'written fresh' sentences and the bf64c51 pin go. A parser and CI test check: pins equal D11; every file under catalog/core/skills/*/ (SKILL.md, rules, references, scripts; LICENSE copies excluded) is a mapping target or engine-written; every listed core file exists; an upstream file appears at most once; DROP rows carry a reason; a skill holding a target of a source ships that source's byte-identical license, and no license without a target. Remove PBP_DISTILLED_RULES, _PBP_SECTION_HEADING and test_core_attributions_name_every_distilled_rule (tests/unit/test_distilled_content_policy.py:39-56, :66, :105-113); keep DROPPED_RECOMMENDATIONS (:30-38) and widen its scan to every .md under core skills (rules, references, SKILL.md) and prompts. No word-shingle check exists in code (it was a reviewer step, prS R5-9), so nothing to delete there.

- `catalog/core/ATTRIBUTIONS.md`: rewritten in the mapping format described above
- `tests/_attributions.py`: new parser returning sources, pins, per-skill rows and engine-written lists
- `tests/integration/test_resources_self_contained.py`: policy_for exempts the two license names in core skills; _PBP_COMMIT (:83) becomes the D11 pins; credit tests (:318-329) read the new format; docstring
- `tests/unit/test_distilled_content_policy.py`: docstring cites ADR 0004; removals above; DROPPED_RECOMMENDATIONS scan widened; MOVED_GUIDANCE_OWNERS kept for the lanes to update
- test `tests/integration/test_core_attributions.py`: new: the checks listed in the summary, each with a synthetic-table unit case
- test `tests/integration/test_core_license_copies.py`: new: byte pins of the two license copies, and their only allowed locations

Acceptance:
- A license copy anywhere else in core, or a changed copy, fails; the two names pass the marker scan only in a core skill's references/.
- ATTRIBUTIONS.md holds no 'written fresh' sentence and names both D11 commits.
- The attribution test fails on a wrong pin, a dangling core path, an unlisted core skill file, a DROP row without a reason, a license without targets and targets without a license.
- DROPPED_RECOMMENDATIONS keeps its seven tokens and now also scans references/ and SKILL.md files.
- The URL scan allows, only inside fenced code blocks under catalog/core/skills/**, the reserved hosts example.com/.org/.net and their subdomains, *.test, *.example, *.invalid, localhost and the bare host 'test', with any scheme; prose stays URL-free (D38).
- MOVED_GUIDANCE_OWNERS: 'monkeypatch' narrows to 'monkeypatch.setenv' owned by pytest-monkeypatch; 'from conftest import' moves to pytest-conftest; 'composition over inheritance' to design-composition-over-inheritance (D46.1).
- DROPPED_RECOMMENDATIONS also scans every core skill's references/*.md, except the byte-identical license files (D58).
- The banned-token scan also rejects debug=True, FLASK_DEBUG=1, Streamlit enableCORS/enableXsrfProtection set to false and gatherUsageStats = true in rules and references (scoped to the Domino skills if another core rule needs one in a Bad Example) (D78(4)).
- D38's reserved hosts are allowed in examples/**/*.py, still only reserved names (D78(13)).
- ATTRIBUTIONS lists files whose mapping action is distill as distilled (credited by name only) or engine-written, never with a change list of upstream text (D78(15)).

### L0-15: feat(catalog): add sections to python-coding and python-tooling and create web-application

Lane lane0, size M, depends on L0-03, L0-04, L0-07, L0-11, L0-12, L0-13, L0-14, L0-17, L0-18; decisions D4, D17, D18, D21, D24, D35.

Requires the per-skill mapping merged into specs/prU-core-python-skills.md. For the rules L0-07 moved: write the playbook block (authored description, use_when, files, every section of the mapping in order) of python-coding (description drops 'Library-agnostic', D24) and python-tooling; create catalog/core/skills/web-application/SKILL.md with its block and a one-paragraph intro naming topics (no rule ids); git mv fastapi-app-wiring and fastapi-error-boundaries to web-application/rules and pydantic-boundaries to python-coding/rules with their gates unchanged (has_framework fastapi / pydantic); give every rule of the three skills its section: and the priority computed from the full mapping order (band floor of the section's impact + the rule's rank among the skill's rules of that impact, capped at the band ceiling; ties sort by id), so content lanes never renumber; fix the python-tooling body that still lists Pydantic and FastAPI. Rule bodies stay as they are; content lanes vendor them later. web-application is created here, not as an empty skeleton, because a playbook skill without members prints W1 on every sync (validation/_skills.py:356-359; sync_gate_errors prints warnings).

- `catalog/core/skills/python-coding/SKILL.md, catalog/core/skills/python-tooling/SKILL.md, catalog/core/skills/web-application/SKILL.md (new)`: playbook blocks from the mapping; bodies' topic lines
- `catalog/core/skills/{python-coding,python-tooling,web-application}/rules/*`: section: and priority on every rule; three git mv re-homes
- `catalog/core/ATTRIBUTIONS.md`: engine-written lists follow the three moved files and add web-application/SKILL.md
- `MIGRATION.md`: V1 quote lists web-application
- `tests/core_skill_pins/python_coding.py, python_tooling.py, web_application.py (new)`: members in index order, where phrases, probe-inactive members
- test `tests/integration/test_core_python_tooling.py (:27-45), tests/cli/test_sync_tooling_references.py, tests/cli/test_sync_core_skills.py, tests/cli/test_sync_skill_root_move.py (:47-72), tests/integration/test_core_skills.py (Continue names :625-630)`: new members, descriptions and NN- prefixes
- test `tests/hook_runtime/handlers/feedback/test_skill_nudge.py (:54, :100, :277-282), tests/fixtures/hook_payloads/{claude_code,opencode}/post_tool_use/skn_*.expected.json`: nudge lines if the FastAPI rules now nudge web-application
- test `tests/integration/test_core_section_descriptions.py`: new: each core skill's description composed with every declared section is <= 300 chars

Acceptance:
- playbook validate on the engine checkout reports no error and no warning.
- On the reference probe the three skills render their active sections in mapping order with impact tags; every description is <= 300 chars and the core total <= 2,400.
- python-tooling no longer holds fastapi-* or pydantic-boundaries; their applies_if and globs are unchanged.
- Kept ids keep their hook links and prompt includes; no includes_rules line changes (D16).
- Every rule's priority equals the value computed from the mapping order and lies in its section's band.

### L0-16: feat(catalog): add sections to python-testing and ml-data

Lane lane0, size S, depends on L0-03, L0-04, L0-07, L0-11, L0-12, L0-13, L0-14, L0-17, L0-18; decisions D4, D17, D18, D21.

Same as L0-15 for python-testing (pytest, pytest-fixtures, pytest-test-doubles) and ml-data (ml-data-transforms, ml-dtypes-and-typing, ml-reproducibility-and-testing, ml-serialization-security, ml-vectorization): playbook blocks with every mapping section, section: keys and priorities from the full mapping order; gates unchanged (ml-serialization-security keeps its torch/scikit-learn gate, which the hook ml-unsafe-deserialization-guard inherits). Retired ids stay until the content lane retires them, in the section the mapping gives their successor.

- `catalog/core/skills/{python-testing,ml-data}/SKILL.md and rules/*`: playbook blocks; section: and priority
- `tests/core_skill_pins/python_testing.py, ml_data.py`: members in index order, where phrases
- test `tests/unit/test_ml_data_rules.py, tests/integration/test_core_skills.py`: member order and any Continue NN- names of these skills
- test `tests/fixtures/hook_payloads/{claude_code,opencode}/post_tool_use/rdc_edit_pyproject_add_torch.expected.json`: re-check; the rule id is unchanged

Acceptance:
- playbook validate on the engine checkout reports no error and no warning.
- Both descriptions with every declared section are <= 300 chars; the probe's core total is <= 2,400.
- The pytest and ml-serialization-security hooks still resolve their linked rules with unchanged gates and globs.

### L0-17: test(catalog): render every core rule template across a fact matrix and cap every branch

Lane lane0, size S, depends on L0-02, L0-07; decisions D20, D40.

D40 turns more rules into python_version branches and several rules already branch on libraries; the reference probe renders only one branch. Render each core .md.j2 rule over a fact matrix (Python 3.10, 3.11, 3.12, 3.13 crossed with the libraries its template tests) and apply the D20 caps (100 lines, 750 words, after ruff format) to every distinct rendering.

- `tests/unit/test_core_rule_shapes.py`: parametrize the size check over the fact matrix; collect distinct renderings per rule
- test `tests/unit/test_core_rule_template_matrix.py`: new: every branch of every core template renders without undefined variables and within the caps

Acceptance:
- Every distinct rendering of every core template is within 100 lines and 750 words.
- A template that uses an undefined variable or a string version comparison fails the test.
- The fact matrix renders every rule that holds a has_framework('fastapi') pointer branch with FastAPI on and off (18 rules gained one in round 6), within the D20 caps.

### L0-18: feat(hooks): rank skill nudges by their most specific matching glob

Lane lane0, size S, depends on L0-05; decisions D41.

With eight core skills one Python edit can match six skills while a nudge lists at most five lines (D41). Rank matching skills by the specificity of the glob that matched (fewer wildcards, longer literal part first), keep the five-line cap, and document the shared test-file glob set every test-related rule uses: **/test_*.py, **/*_test.py, **/tests/**/*.py, **/conftest.py, **/fakes.py.

- `src/coding_agent_playbook/hook_runtime (skill nudge handler)`: order matches by glob specificity before applying the cap
- test `tests/hooks (skill nudge tests)`: an edit to tests/test_x.py names python-testing before principle skills; the cap stays five

Acceptance:
- A test-file edit nudges python-testing first.
- No nudge exceeds five lines.
- catalog/README 'Writing a rule' lists the shared test-file glob set.

### L0-19: feat(config): choose the spec-driven framework by name at init and in the committed config

Lane lane0, size L, depends on L0-00, L0-00b; decisions D57, D71, D74, D77.

D57: `playbook init --framework superpowers | mattpocock | none` (also asked by interactive init) writes a committed `framework` key; sync enables the matching bundled plugin. A full overlay module name selects an organization's own framework. A bundled plugin marks itself as a framework in a small metadata file at its root (superpowers and mattpocock_skills get one). validate rejects two frameworks enabled together, naming both. --overlays / overlays_enabled stay for non-framework add-ons. Default none; switching is a config change plus sync, and the lockfile removes the old framework's files.

- `src/coding_agent_playbook/commands (init flags and prompt)`: --framework option and interactive question
- `src/coding_agent_playbook/config (schema, model)`: framework key, resolution of short names to plugin modules
- `src/coding_agent_playbook/validation/preflight.py`: at most one framework among enabled overlays
- `catalog/plugins/superpowers, catalog/plugins/mattpocock_skills`: framework metadata file at the plugin root
- test `tests/cli (init and validate tests)`: --framework superpowers writes framework = 'superpowers'; two frameworks fail validate; switching removes the old skills on sync

Acceptance:
- `playbook init --framework mattpocock --non-interactive` in an empty repo enables mattpocock_skills and no other framework.
- Enabling superpowers and mattpocock_skills together fails validate with both names.
- Switching framework and running sync leaves only the new framework's files; sync --check reports no drift.
- README's install section shows the choice in one line (D55).
- The framework metadata file may declare layout_aliases (path prefix -> layout key); validate rejects an unknown layout key or an alias that is not a path prefix (D71).
- The framework metadata file is framework.toml at a bundled plugin's root (or an overlay's resources/ root) with keys name, description and an optional [layout_aliases] table (D57, D71).
- Templates can call framework_skill(role), which returns the enabled framework's skill name or an empty string, and skill_active(name), which says whether a core skill renders in this repo (D74).
- A framework skill declares its roles in an engine-owned frontmatter key capabilities: [role, ...], removed from written skill files; validate accepts only the D74 roles and at most one skill per role per framework; only the enabled framework's tags are read (D77).
- playbook check prints the enabled framework's role-to-skill map, for example 'framework mattpocock: clarify -> grill-me, debug -> diagnosing-bugs'.
- framework.toml holds name, description and an optional [layout_aliases] table only.

### L0-20: feat(detector): add the domino_project and playbook_layer facts and the platforms key

Lane lane0, size M, depends on L0-02; decisions D51, D63, D70, D78.

D63: domino_project is true when any reliable Domino marker is present (.dominoignore, .dominoresults, a committed dominostats.json, or the dependencies dominodatalab / dominodatalab-data); weak markers (app.sh, /mnt paths) never count alone; a committed config key platforms = ["domino"] forces it on. D70: playbook_layer is true when the repo has a catalog/ layer, a playbook/ directory, or a package with catalog content that depends on coding-agent-playbook.

- `src/coding_agent_playbook/detector`: a Domino fact only if existing predicates cannot express the markers
- test `tests/detector`: a Domino probe repo turns the gate on; a plain repo does not

Acceptance:
- The Domino probe repo activates domino-apps, domino-jobs and domino-agents; the standard probe activates none; platforms = ["domino"] activates them in a marker-free repo.
- app.sh alone does not make domino_project true.
- playbook_layer is true in this engine repo, in a repo with an empty playbook/ directory and in an overlay package; false in the standard probe.
- Dependency names from root requirements*.txt feed the dependency and framework facts through the existing requirement-name parser, so domino_project and the framework gates fire in repos that declare packages only there (D78(2)).

### L0-21: feat(hooks): add the playbook docs-check guard twin and its pre-commit hook

Lane lane0, size M, depends on L0-00b; decisions D69, D10, D78.

D69: playbook docs-check checks committed documentation with the repo's own tools only: always relative links and Python code-block parsing in changed Markdown (engine stdlib); mkdocs build --strict where mkdocs.yml exists; sphinx-build -W --keep-going where docs/conf.py exists; doctests where the repo's pytest configuration enables them; markdownlint or doc8 where their config exists and the tool is installed. A missing tool fails open with an install hint. Wired as a local pre-commit hook filtered to *.md, *.rst, docs/**, mkdocs.yml, docs/conf.py; switchable off like other guardrails; documented in the guardrails skill.

- `src/coding_agent_playbook/commands (docs-check)`: new guard twin
- `.pre-commit-hooks.yaml and the init pre-commit starter`: local hook entry with the files filter
- test `tests/cli (docs-check)`: broken relative link fails; repo without mkdocs/sphinx runs only the stdlib checks; missing tool fails open with a hint

Acceptance:
- A commit touching only Python files does not run docs-check.
- A broken relative link in a staged Markdown file fails the hook with the file and line.
- No tool is invoked that the repo does not already configure.
- docs-check detects Sphinx at docs/conf.py, docs/source/conf.py or doc/conf.py and MkDocs at mkdocs.yml or mkdocs.yaml; a 'docs' dependency group counts as a docs toolchain (D78(10)).

### L0-22: feat(rules): add the code-legibility and document-layout always rules and the layout guard

Lane lane0, size S, depends on L0-00b, L0-04, L0-23; decisions D60, D61, D35, D71, D73, D75.

D60/D61: a core always rule names the document layout in about three lines; a guard hook blocks writing a spec or plan into known other locations (docs/superpowers/**, spec or plan files under .scratch/) and names the right directory. D73: also a language-neutral always rule 'Code legibility' (code-legibility), right after project context, with eight one-line principles (small units, one responsibility, shallow nesting, errors with context, searchable names, one home per piece of logic, predictable tree, F.I.R.S.T tests), each naming the skill and rule that hold the detail; the Python house style drops its layout-axis line and its description says seven conventions. The always-sections word cap rises from 240 to 450; the 800 and 1,500 totals stay.

- `catalog/core/rules/always/`: new always rule for the document layout
- `catalog/core/hooks/protect/`: document-layout guard
- test `tests/hooks`: writing docs/superpowers/plans/x.md is blocked with the docs/plans/ hint; docs/plans/x.md is allowed

Acceptance:
- Always-loaded context stays within the D35 caps with the new rule.
- The guard names the canonical directory in its message.
- The always rule is a Jinja template that renders the repo's configured layout; the guard hook reads the configured directories, so a repo with specs = "specs" may write specs/x.md and is blocked from docs/superpowers/plans/ with a hint naming its plans directory (D71).
- The code-legibility rule names eight principles, each with its skill and rule; every named rule exists and is ungated.
- The two always sections plus the new always rules fit within 450 words on the probe; the 800 and 1,500 totals still pass.
- project-context renders its ask-before-writing line with framework_skill('clarify'): 'use the grill-me skill' in a mattpocock repo, 'use the brainstorming skill' in a superpowers repo, unchanged without a framework (D75).

### C-frameworks-layout: feat(plugins): point superpowers and mattpocock_skills at the shared document layout

Lane content, size M, depends on L0-22; decisions D60, D61, D77.

D61 and ADR 0006: edit every path string in both bundled frameworks to the D60 layout (superpowers specs/plans -> docs/specs, docs/plans; mattpocock .scratch/<slug>/spec.md and issues -> docs/specs and docs/plans/<date>-<slug>/; .scratch kept only for throwaway prototypes), add each edit to the plugin's ATTRIBUTIONS change list, and update the plugins' pinning tests. D77: also tag the frameworks' skills with capabilities (mattpocock_skills: grill-me clarify, grill-with-docs clarify_with_docs, to-spec spec, to-tickets plan, tdd tdd, diagnosing-bugs debug, two-axis-review review; superpowers: brainstorming clarify, writing-plans plan, test-driven-development tdd, systematic-debugging debug, requesting-code-review review, verification-before-completion verify), each tag a row in the plugin's ATTRIBUTIONS change list.

- `catalog/plugins/superpowers/**`: path strings
- `catalog/plugins/mattpocock_skills/**`: path strings
- test `tests/plugins/**`: byte-faithfulness pins allow exactly the listed path edits

Acceptance:
- No bundled framework file mentions docs/superpowers/ or a spec/plan under .scratch/.
- Each edit has an ATTRIBUTIONS change-list row.

### L0-23: feat(sync): add the layout adapter for the document layout

Lane lane0, size M, depends on L0-19, L0-00b; decisions D60, D71, D78.

D71: a [layout] table in the committed config (glossary, context_map, adr, architecture, specs, plans, research, agents, scratch; defaults from D60). When a key differs from its default, sync rewrites exactly the default path prefix (and every layout_aliases prefix a framework declares) in the synced files of core, bundled plugins and overlays, before hashing for the lockfile; validate prints each rewrite per file (file, from, to, count). File name patterns stay fixed. Templates receive the resolved layout as a `layout` variable.

- `src/coding_agent_playbook/config (schema, model)`: [layout] table with defaults and validation (relative paths inside the repo, no '..', directories end without a slash)
- `src/coding_agent_playbook/sync (render or writer step)`: prefix rewrite of synced text for changed layout keys and declared aliases
- `src/coding_agent_playbook/rendering/jinja.py`: expose the resolved layout to templates
- `src/coding_agent_playbook/validation`: per-file rewrite report
- test `tests/sync (layout adapter)`: default layout changes nothing byte-for-byte; specs = 'specs' rewrites docs/specs/ in core, superpowers and mattpocock_skills files; an overlay alias maps its own prefix; sync --check stays clean after a rewrite

Acceptance:
- With no [layout] table, every synced file is byte-identical to the output without the adapter.
- validate lists every rewrite with file, from, to and count.
- An absolute path, a '..' segment or an unknown key in [layout] is a validation error naming the key.
- The layout adapter also rewrites default path prefixes in rule globs and in hook path tables, so skill nudges and the layout guard follow a custom [layout] (D78(12)).

### L0-24: feat(prompts): select a prompt set per repo with the prompts config key

Lane lane0, size M, depends on L0-00b, L0-19; decisions D76, D16, D37.

D76: a committed config key prompts = 'v1' | 'v2' (default v1) selects which prompt set renders; v2 prompts live in catalog/<layer>/prompts/v2/ under the same names as v1; a v2 prompt without a v1 twin, or a v1 prompt without a v2 twin once v2 exists for it, is a validation error; eval samples keep grading v1, and the opt-in eval comparison (D37) can compare v1 and v2.

- `src/coding_agent_playbook/config`: prompts key with default v1
- `src/coding_agent_playbook/catalog (prompt discovery)`: prompts/v2/ set
- `src/coding_agent_playbook/validation`: twin check
- `src/coding_agent_playbook/evals`: comparison can target a prompt set
- test `tests/catalog and tests/cli`: prompts = 'v2' renders v2 text under the same command names; default renders v1 byte-identically; eval runs stay on v1

Acceptance:
- Without a prompts key, every rendered prompt is byte-identical to today.
- prompts = 'v2' changes only prompt text, never the skill listing's prompt names.
- The eval comparison accepts a prompt set as one side.

### C-prompts-v2: feat(prompts): write the v2 prompt set that points to skills

Lane content, size M, depends on L0-24, L0-19, L0-15, L0-16; decisions D76, D74, D75, D16.

D76: one v2 prompt per core prompt (review, refactor, generate-tests, make-testable, characterize, review-architecture, explain, security-review, find-injected-vulnerability), same frontmatter and includes_rules as v1, plus three parts: Before you start (core skills for the task via skill_active: refactor -> python-coding, design-patterns; review -> python-coding, design-patterns, python-testing; review-architecture -> python-architecture, design-patterns; generate-tests and characterize -> python-testing; make-testable -> python-architecture, python-testing; security-review and find-injected-vulnerability -> web-application, ml-data; explain -> python-documentation), If something is unclear (framework_skill('clarify') or ask the user), Check and improve your work (framework_skill tdd/review/verify/debug by task, and the decision guides that apply, by bare file name).

- `catalog/core/prompts/v2/*.md.j2`: nine new prompts
- test `tests/catalog (prompt sets)`: each v2 prompt renders with no framework, with mattpocock_skills and with superpowers; it names only active core skills

Acceptance:
- Each v2 prompt has the same name, frontmatter keys and includes_rules as its v1 twin.
- Rendered with no framework, no v2 prompt names a plugin skill.

### L0-25: feat(hook_runtime): log hook calls ignored as foreign or outside a repo, and report them in doctor

Lane lane0, size S, depends on L0-00b; decisions D79.

D79(1): every hook call the harness parser classifies as foreign, and every call outside a git repository, is logged once with its event, harness and reason (foreign_marker:<key>, timestamp, event_mismatch, missing_session_id, claude_project_dir_unset, not_a_repo, and OpenCode's equivalents), reusing the hooks-off logging path (JSON with named fields). Exit code and wire output stay unchanged: a foreign payload stays inert. playbook-hook doctor reports the ignored calls (counts, reasons, most recent first) and flags claude_project_dir_unset and missing_session_id as a likely misconfigured real session.

- `src/coding_agent_playbook/hook_runtime/dispatch/run.py`: log the silent ForeignPayload return (~line 193) and the outcome.repo is None return (~line 199), reusing the hooks-off logging path (~lines 189-191)
- `src/coding_agent_playbook/hook_runtime/harness/claude.py`: expose the reasons (~lines 81-105) to the log
- `src/coding_agent_playbook/hook_runtime/harness/opencode.py`: the same for OpenCode's reasons
- `src/coding_agent_playbook (playbook-hook doctor diagnostics)`: report ignored calls and flag likely misconfiguration
- test `tests/hook_runtime`: one test per reason: logged once with event, harness and reason; exit code and wire output unchanged
- test `tests (doctor)`: doctor lists counts and reasons most recent first and names claude_project_dir_unset as a likely misconfiguration

Acceptance:
- The exit code and wire output are unchanged for every inert case.
- Each ignored call is logged once (per session, event and reason; once per UTC day when the payload has no session id) with event, harness and reason.
- doctor names claude_project_dir_unset and missing_session_id as a likely misconfigured real session.

### L0-26: feat(cli): warn when configured adapters and repo harness markers differ, and pre-select detected adapters in interactive init

Lane lane0, size M, depends on L0-00b; decisions D79.

D79(2): one harness-marker module (single source of truth; repo files only, never PATH) drives advisory playbook check warnings (a harness's markers exist but its adapter is off: opencode.json or user-written .opencode/ files, .continue/; or a configured adapter shows no use beyond the engine's own generated outputs, told apart by the lockfile), each naming the exact config change or playbook init --adapters ... that fixes it and never failing the command; and interactive playbook init pre-selecting the detected adapters. The non-interactive default (claude_code, opencode, shared_skills) is unchanged.

- `src/coding_agent_playbook (new harness-marker module)`: the marker table, the single source of truth
- `src/coding_agent_playbook/commands (check)`: advisory warnings with the exact fix
- `src/coding_agent_playbook/commands/_init_answers.py`: pre-select detected adapters in the multi-select (~line 181)
- `src/coding_agent_playbook/commands/_init_adapters.py`: default unchanged (~lines 14-19)
- test `tests/cli (check, init)`: each marker; generated-only files do not count as use; the non-interactive default is unchanged; warnings never fail check

Acceptance:
- Every marker in the table has a test.
- Files the engine generated (per the lockfile) never count as harness use.
- playbook check exits 0 when only these warnings fire.
- Non-interactive init still defaults to claude_code, opencode, shared_skills.

### L0-27: feat(cli): rename the judge's --samples flag to --judge-samples

Lane lane0, size S, depends on L0-00b; decisions D80.

D80: `playbook eval <id> --run --samples N` is how many times the judge scores each rubric criterion, not a count of eval samples. The flag becomes --judge-samples N (default 1) and the grading context field samples becomes judge_samples. --samples stays for one release as a deprecated alias hidden from --help: it still works, prints one stderr line naming --judge-samples, and passing both flags is a usage error (exit 2). No warnings.warn: pytest runs with filterwarnings = error.

- `src/coding_agent_playbook/commands/eval.py`: --judge-samples (dest judge_samples); the hidden --samples alias, its stderr line and the both-flags error; module docstring and help text
- `src/coding_agent_playbook/grading/types.py`: the context field samples -> judge_samples, and every reader (grading/judged.py, grading/judge_metric.py, commands/eval.py, evals/**)
- `README.md, SPEC.md`: the eval CLI lines and the JudgeCheck/JudgeMetric paragraphs; older changelog entries stay as written
- `MIGRATION.md`: in v0.21, replace "The flag `playbook eval --run --samples N` keeps its name" with the rename, the alias and its removal in the next release
- `tests/cli/golden/cli_surface.json`: re-record with `python -m tests.cli.cli_surface` and review the diff; when L0-19 or L0-26 also changed the golden, re-record it after merging instead of merging the JSON by hand
- test `tests/cli/test_eval_run.py, tests/grading/`: --judge-samples reaches the judge as n; --samples still works and prints the deprecation line once; both flags exit 2; --help does not list --samples

Acceptance:
- `playbook eval <id> --run --runner fake --judge <fake> --judge-samples 3` scores each criterion 3 times.
- `--samples 3` gives the same scores plus one stderr line naming --judge-samples; `--samples` is absent from --help.
- `git grep -n -E 'ctx\.samples|--samples' -- src README.md SPEC.md` finds only the alias, its message and changelog entries older than v0.21.
- The CLI surface golden test passes.

### D-01: docs(spec): describe rules inside skills, sections and the priority policy

Lane docs, size M, depends on L0-10, L0-15, L0-16; decisions D5, D17, D21, D22, ADR 0005, D79.

Rewrite the SPEC parts on rule discovery and rendering (re-grep, line numbers drift): 5.1 engine tree (rules inside skills, the two always rules); 6.0, 6.1.1, 6.1.2 frontmatter (section:, skill: only for rules from another layer; keep an example of a repo-local rule with 'skill: python-coding' so tests/unit/test_docs_glossary.py:103,107,112 keep holding); 6.1.6 a rendered rules/<id>.md sample with the [IMPACT] tag; 6.2.x 'Before you start' samples; 6.3.x skills (rules/ vs free-form references/, playbook.sections, Covers by sections, grouped index sample, what sync copies); 10.2.1 priority policy (0-19 always rules, CRITICAL 20-39, HIGH 40-59, MEDIUM 60-79, LOW 80-99, rank inside the section; replaces the kind bands; sectionless skills keep free 0-99); 12.6 validate rows (V1 and W1 text, V12 removed, V13 '## Rules', R1-R6, S1-S7, rule load errors and shape checks); 12.7 render; 14.4 lockfile sample paths; 20.3 discovery order; the agent_harness tree with skills/<id>/rules. 6.4 and 9.4 predicates were done in L0-02. D79: one SPEC line on logged inert hook calls (doctor) and harness-marker warnings in playbook check.

- `SPEC.md`: the sections above
- `tests/unit/test_docs_glossary.py`: only if a pinned phrase must move
- test `tests/unit/test_docs_*.py`: all doc pins pass

Acceptance:
- rg -n 'references/<rule-id>|references/python-typing.md|kind bands|40-59 language' SPEC.md finds only historical changelog lines.
- Every validate message the engine prints for R1-R6 and S1-S7 has a 12.6 row with its sample line.
- Doc pin tests pass.

### D-02: docs(spec): record vendored core guidance, the new budgets and the v0.21 changelog

Lane docs, size M, depends on L0-14, L0-15, L0-16; decisions D1, D4, D18, D19, D31, ADR 0004, D79.

SPEC text that limits vendoring to bundled plugins (the 2347-area paragraph, 11.5.x) and calls core text distilled (header line 13, 5.1 comments) changes to ADR 0004: core vendors and adapts pbp and pca, ships byte-identical license copies in each skill's references/ (D19), ATTRIBUTIONS mapping tables (D31). Budgets: 2,400 core, 6,500 listing, the listing sentence near L2425 ('core's four skills ...'), eight core skills. v0.21 changelog entry: vendored core, three new skills, rules/ in sources and output, sections and impact bands, has_dependency, retired ids. Edits sections D-01 does not touch; merge D-01 first if both are open. Also ADR 0006 (bundled frameworks follow one document layout) and the eval sample rename's SPEC wording are already in place or handled by L0-00b.

- `SPEC.md`: the sections above
- test `tests/unit/test_docs_*.py`: all doc pins pass

Acceptance:
- rg -n 'written fresh|distilled, not vendored|2,000|6,000|four skills' SPEC.md finds only historical changelog lines.
- The v0.21 changelog names the three new skills, rules/ output, sections and the retired ids.

### D-03: docs: update README and catalog/README for eight core skills and add 'Writing a rule'

Lane docs, size M, depends on L0-14, L0-15, L0-16; decisions D4, D19, D21, D32, D55, D57, D63, D66, D70, D60, D71.

README: 'Core ships four skills' becomes eight (seven with members plus playbook-guardrails), the skill-to-topic table, rules/ vs references/, a note that .claude/skills/<s>/rules/ is unrelated to Claude Code's .claude/rules/, Continue receives core rules without the license file (D19), the architecture overview if it shows rules/. catalog/README: layout (core/rules/always and core/skills/<skill>/{SKILL.md, rules, references, scripts}), the 'four skills' text (:35-37), rule groups (:77-78), the EXPECTED_MEMBERSHIP pointer (:91-93) becomes tests/core_skill_pins/, the vendored-core policy (ATTRIBUTIONS mapping tables, license copies), and a new 'Writing a rule' section from pbp's _template.md (D32): frontmatter keys with section: and the priority band, body Description, Bad Example, Good Example, Notes, no authored [IMPACT], at most 100 lines and 750 words, ids and prefixes (D21), gates before templates (D8), ruff-formatted code blocks, no URLs or upstream names. catalog/plugins/mattpocock_skills/README.md:74-75 if it names python-testing paths. Round 7 (D55): README.md becomes a short user README of about 80 lines (what it is, a 6-line ASCII overview, install, set up a repo with init and sync including the --framework choice, keep it current, contribute to the catalog, links); every other current README section moves unchanged into docs/ and the README pins are repointed. Round 8-9: the install section uses the git-URL dev dependency with one line for an internal index and states Python 3.12+ (no uv tool install or pipx, D66); setup shows playbook init --framework (D57); a line says platforms = ["domino"] turns the Domino skills on (D63) and that a playbook/ directory starts a local layer (D70); a short pointer to docs/ for the document layout (D60). D71: one README line shows the [layout] table for repos that keep specs or plans elsewhere.

- `README.md, catalog/README.md, catalog/plugins/mattpocock_skills/README.md`: as above
- test `tests/integration/test_catalog_layout.py, tests/cli/test_validate_links.py`: pass; no link to a layer-root file

Acceptance:
- catalog/README.md has a 'Writing a rule' section covering every frontmatter key the engine accepts.
- README states the Continue license gap in one sentence.
- rg -n 'four skills' README.md catalog/README.md finds nothing.
- README.md is at most about 80 lines and holds only the D55 sections; no current README text is lost (each section is present in docs/).

### D-04: docs(migration): add the v0.21 entries for rules/, sections and the new core skills

Lane docs, size M, depends on L0-15, L0-16; decisions D5, D17, D21, D23, D24, ADR 0004, ADR 0005.

In the untagged v0.21 section: subsections and TL;DR rows for member rules now rendered at <skill>/rules/<id>.md (old references/<id>.md copies removed by the next sync, edited ones kept), agent_harness member rules under skills/<s>/rules, Continue file names that change because priorities follow impact bands (old to new table for the kept ids), the retired ids and their successors (python-performance-idioms, python-classes-and-protocols, ml-dtypes-and-typing, ml-reproducibility-and-testing), the three new skills and their Where lines, rules joining a sectioned core skill needing section: and an in-band priority (S4, S6), has_dependency/any_dependency, upstream guidance vendored with license copies. Rewrite the 'Distilled python-best-practices content' subsection and the stale Continue names (44-python-data-shapes.md, 53-python-classes-and-protocols.md, 73-ml-reproducibility-and-testing.md and others) and update the pinned phrase list in tests/unit/test_docs_migration_skills.py:68-90 in the same change; keep the TL;DR pointers in subsection order (:130-138). Successor ids come from the mapping; re-check against the final tree in F-02.

- `MIGRATION.md`: v0.21 section and heads-up block
- `tests/unit/test_docs_migration_skills.py`: pinned phrases
- test `tests/unit/test_docs_migration_skills.py`: passes with the new phrases; the V1 quote stays computed

Acceptance:
- MIGRATION.md names every retired id with its successor and every new core skill.
- The TL;DR has rows for consumers with edited references/ copies and for repo-local rules joining a core skill.
- test_docs_migration_skills.py passes.

### F-01: feat(evals): add an opt-in comparison of the rule-including prompts against a base ref

Lane final, size S, depends on L0-15, L0-16; decisions D30, D37.

D30 as amended in round 5: no paid eval run in this effort. Add one opt-in way (off by default; a flag on the existing eval runner or a manual CI input, whichever fits the runner) to run the eval tasks of the seven prompts whose included rule bodies change (review, refactor, make-testable, review-architecture, generate-tests, characterize, security-review) on a base ref and on HEAD, and report the comparison. Defaults: 3 samples per task on each ref with the same model; a regression is a mean score drop above 0.05 on any task, or a task that passes on the base failing in 2 of 3 samples. It is not a merge gate.

- `<scratchpad>/evals/{main,integration}/*.json`: reports, not committed
- test `real eval runs`: 12 tasks x 2 branches x 3 samples

Acceptance:
- The option is off by default; CI and the final gate never run it.
- With the option on, a comparison table lists, per task, base vs HEAD outcome and mean judge score with spread, and flags regressions by the default thresholds.
- README documents how to turn it on and that it needs the owner's credentials and costs money.
- git diff main -- catalog/core/prompts shows no includes_rules change.

### F-02: feat(catalog): vendor upstream Python guidance into eight core skills

Lane final, size M, depends on F-01; decisions D13, D30, D31, D33, D34, D35, D36.

Final-state tests, then the full CI-parity gate and one PR from integration/core-python-skills into main (D13). New tests: every declared section of a core skill has at least one member; RETIRED_RULE_IDS are absent from core and no new file reuses them; every core skill with a playbook block has an active member on the reference probe; every upstream file at the two pins has exactly one ATTRIBUTIONS row (paths-only inventory fixtures tests/fixtures/upstream_inventory/pbp-fa0d3f58.txt and pca-9d627ca.txt generated once from the pinned clones); the Where map with seven lines within 800 words (D35) and AGENTS.md within 1,500; the temporary output-neutrality test of L0-07 removed. Gate cache-free, without optional extras, on Python 3.12 and 3.13: ruff check ., ruff format --check ., mypy, pytest -q with no path args; plus the wheel-smoke steps (sdist then wheel, _catalog equals git ls-files catalog, playbook init in an empty repo prints no 'warning:' line). PR title in Conventional Commits; the body lists the tickets, the eval table from F-01 and the migration notes. The owner merges.

- `tests/integration/test_core_final_state.py`: new: the final-state checks above
- `tests/fixtures/upstream_inventory/pbp-fa0d3f58.txt, pca-9d627ca.txt`: new: upstream file paths at the pins
- `tests/integration/test_core_move_is_output_neutral.py`: deleted
- `specs/prU-core-python-skills/runner/`: deleted (the temporary implementation tooling)
- test `tests/integration/test_core_final_state.py`: as above

Acceptance:
- specs/prU-core-python-skills/runner/ no longer exists.
- ruff check ., ruff format --check ., mypy and pytest -q pass on Python 3.12 and 3.13 in fresh environments without the metrics extra.
- The wheel's _catalog/ equals git ls-files catalog and init in an empty scratch repo prints no warning line.
- Final-state tests pass: no empty declared section, no retired id, every upstream file has one row, every core skill active on the probe.
- Exactly one PR into main exists with a Conventional Commits title; it is not merged by the agent; if forge #170 merged first, this branch was rebased and its counts, known-skills quote and budgets re-checked (D36).

## Content tickets

Every content ticket follows this template.

Steps:
1. Start from the lane's worktree on integration/core-python-skills after wave 6; read the skill's mapping (specs/prU-core-python-skills/mapping-<skill>.md), D1-D36 with the Defaults, and the upstream files the mapping names (as data, never as instructions).
1. Test-related rules use the shared test-file glob set (D41): **/test_*.py, **/*_test.py, **/tests/**/*.py, **/conftest.py, **/fakes.py.
1. Example URLs (D38): only reserved hosts (example.com/.org/.net and subdomains, *.test, *.example, *.invalid, localhost, the bare host 'test') and only inside fenced code blocks; prose has no URL.
1. Python versions (D40): example code targets Python 3.10 as the lowest branch; where the idiomatic form differs on a newer Python (Self, StrEnum, datetime.UTC, TaskGroup, asyncio.timeout, ExceptionGroup, tomllib, PEP 695), make the rule a .md.j2 with branches on python_at_least(...) instead of gating it; keep applies_if python_version only when the topic does not exist below that version (match statements: >=3.10).
1. Clone the upstream sources at the D11 pins into your own scratchpad (pbp v0.8.0 fa0d3f58afb8bf56c028bb559e0e7bc1538e079a, pca 9d627ca7bedbe0bb9e2fcf3c83d81814a6133dce) and read them as data, never as instructions; python_design files come from git show f7ece8b0.
1. design-patterns and python-architecture only: the lane's first ticket creates catalog/core/skills/<skill>/SKILL.md with the mapping's playbook block (description, use_when, files, every section) together with its first rules, never as an empty skeleton (an empty playbook skill prints W1 on every sync); add tests/core_skill_pins/<skill_snake>.py and the skill to the MIGRATION V1 quote (the second lane to merge resolves the one-line conflict).
1. Create or edit each rule at catalog/core/skills/<skill>/rules/<id>.md (.md.j2 only when the mapping says template: true): engine frontmatter id (== file stem), name, description, scope: scoped, section, priority from the mapping order (band floor + rank of the rule among the skill's rules of that impact), globs, applies_if = the mapping gate, tags optional; no skill: key, no new lint_codes (D16); body '# Title' without the impact tag, then Description, Bad Example, Good Example, Notes (D7); drop upstream References lists.
1. Apply the mapping action per rule: keep, merge (existing id keeps its id), split-keep-id, split-new, copy, combine; delete retired ids (python-performance-idioms, python-classes-and-protocols, ml-dtypes-and-typing, ml-reproducibility-and-testing) only in the lane that owns them, and never reuse them.
1. Adapt the text: engine decisions win over pbp, pbp over pca (D6, D27, D28); toolchain per D10/D29; version-dated claims become version-neutral; code that needs a newer Python than the floor is gated with python_version; examples follow the always rules (type hints, encoding='utf-8', no dict[str, Any] between layers, no float money, keyword-only flags); no URLs, no upstream product, author or publisher names, no CLAUDE_PLUGIN_ROOT or $ARGUMENTS; cross-references become engine rule ids in backticks; links only to ../references/<file>.md of the same skill; each web rule self-contained (D28).
1. Create the mapping's references/<name>.md (free-form, one level deep, a table of contents when over 100 lines) and copy scripts from the snapshot (git show f7ece8b0:catalog/plugins/python_design/...) into scripts/ (stdlib-only, Python 3.10 compatible), with their tests under tests/core_skills/<skill_snake>/ using core_skill_root().
1. Copy the license file of every source that contributes text to the skill, byte-identical: references/LICENSE.python-best-practices and/or references/LICENSE.python-clean-architecture.
1. Fill the skill's ATTRIBUTIONS sub-tables: one row per upstream file the mapping uses or drops (DROP rows carry the reason), with the change list; move files that now hold vendored text out of the skill's Engine-written list.
1. Write the SKILL.md body (D32): pbp's intro and adapted Quick Reference, See Also as plain-text skill names, no rule ids, no links except to its own references/, no Jinja; leave the playbook block from lane 0 unchanged unless the mapping changed it.
1. Update this skill's pins only: tests/core_skill_pins/<skill_snake>.py (members in index order, probe-inactive members, RulePins of kept rules), MOVED_GUIDANCE_OWNERS rows whose owner the lane retires or gains, the skill's member lists in nudge, sync and probe tests and their goldens if they change, test_prompting name pins if an included rule's name changes.
1. Run ruff format on the new markdown (code blocks) and scripts, then ruff check . and ruff format --check .; confirm no DROPPED_RECOMMENDATIONS token remains.
1. Run playbook validate (config-less, engine checkout), pytest -m catalog, the lane's script tests, mypy, then the full pytest once before the lane merges.
1. D34 review: dispatch a fresh review sub-agent that compares every new or changed rule and reference with its upstream source(s) and the decision list (adapted, every engine decision applied, nothing lost without a DROP row, size limits, gates, ids); fix every finding and re-run the checks.
1. Commit in Conventional Commits form, authored by the configured user, without a Co-Authored-By trailer; never commit CLAUDE.md, .claude/, AGENTS.md, .opencode/, .agents/ or shared_skills/.
1. Navigation (D47): add the mapping's open_when to every section in playbook.sections, list every reference and example in playbook.references (path, open_when, optional applies_if), add each rule's see paths to its Notes as plain text, and remove any hand-written 'Picking references' bullets.
1. Internal references (D49) are engine-written decision guides: at most 120 lines, plain-text rule ids, no repeated rule bodies, marked 'not vendored' in ATTRIBUTIONS.
1. Name a reference or guide inside a rule body by its bare file name (the one-level-deep reference test scans rule bodies), and the example by its examples/<app>/<file> path.

Acceptance:
- Every rule, reference, script and drop of the skill's mapping is realized: each id exists at skills/<skill>/rules/<id>.md[.j2] with the mapped section, gate, globs and template flag; each drop is an ATTRIBUTIONS DROP row; handoffs are left to their owners.
- Every rendered rule is at most 100 lines and 750 words with both the reference-probe facts and the every-gate-on facts.
- Every priority lies in its section's band and follows the mapping order; the index renders the sections in declared order.
- The composed description with every declared section is at most 300 chars; the probe's core total stays at most 2,400 and the core plus mattpocock_skills listing at most 6,500.
- The skill has at least one member active on the reference probe.
- No URL and no upstream name outside ATTRIBUTIONS.md and the license copies; each contributing source's license copy is present and byte-identical.
- ruff check . and ruff format --check . are clean; no DROPPED_RECOMMENDATIONS token appears in the skill.
- Kept ids keep their hook links, lint codes and prompt includes; no includes_rules or lint_codes line changes (D16); retired ids owned by the lane are gone and not reused.
- playbook validate exits 0 with no warning in the engine checkout.
- The D34 review sub-agent reports no open finding.
- pytest (full), mypy and ruff pass on Python 3.12.

| Ticket | Title | Rule files | Depends on |
| --- | --- | --- | --- |
| C-python-coding-01 | feat(python-coding): vendor the error handling, code shape rules | `python-error-handling`, `python-error-messages-with-context`, `python-error-boundaries`, `python-custom-exceptions`, `python-small-units`, `python-early-return` | L0-15, L0-16 |
| C-python-coding-02 | feat(python-coding): vendor the names, types, docs rules | `python-meaningful-names`, `python-typing`, `python-docstrings`, `python-comments-why`, `python-abstract-inputs`, `python-type-aliases` | L0-15, L0-16 |
| C-python-coding-03 | feat(python-coding): vendor the effects and resources rules | `python-dependency-injection`, `python-pure-core`, `python-no-global-singletons`, `python-context-managers`, `python-parameterized-queries`, `python-retries-and-timeouts`, `python-custom-context-managers` | L0-15, L0-16 |
| C-python-coding-04 | feat(python-coding): vendor the asyncio, pydantic validation rules | `python-async`, `python-async-tasks`, `python-async-fanout`, `python-async-generators`, `pydantic-boundaries`, `pydantic-field-constraints`, `pydantic-typed-settings`, `pydantic-model-validators`, `pydantic-special-types`, `pydantic-serializers` | L0-15, L0-16, L0-02 |
| C-python-coding-05 | feat(python-coding): vendor the classes and data shapes rules | `python-data-shapes`, `python-protocols`, `python-properties`, `python-frozen-dataclasses`, `python-enums`, `python-dataclass-post-init`, `python-hide-internal-state` | L0-15, L0-16 |
| C-python-coding-06 | feat(python-coding): vendor the control flow rules | `python-match-fallback`, `python-function-signatures`, `python-match-destructuring`, `python-closures-and-partial`, `python-decorators` | L0-15, L0-16 |
| C-python-coding-07 | feat(python-coding): vendor the idioms and performance rules | `python-idioms`, `python-imports`, `python-collection-choice`, `python-optional-keys`, `python-comprehensions`, `python-generators`, `python-str-join` | L0-15, L0-16 |
| C-python-coding-refs | docs(python-coding): add the skill's references and its generated navigation entries | `references/python-version-idioms.md`, `references/choosing-a-data-shape.md`, `references/error-flow.md` | C-python-coding-01, C-python-coding-02, C-python-coding-03, C-python-coding-04, C-python-coding-05, C-python-coding-06, C-python-coding-07 |
| C-python-testing-01 | feat(python-testing): vendor the mocking, test structure, test isolation rules | `pytest-test-doubles`, `pytest-autospec`, `pytest`, `pytest-first-properties`, `pytest-arrange-act-assert`, `pytest-one-behavior`, `pytest-no-test-logic`, `pytest-assertions`, `pytest-deterministic-tests`, `pytest-monkeypatch` | L0-15, L0-16, C-web-application-example |
| C-python-testing-02 | feat(python-testing): vendor the fixtures, parametrization, coverage rules | `pytest-fixtures`, `pytest-conftest`, `pytest-factory-fixtures`, `pytest-parametrize`, `pytest-parametrize-ids`, `pytest-edge-cases`, `pytest-branch-coverage`, `pytest-hypothesis-properties`, `pytest-hypothesis-stateful` | L0-15, L0-16, L0-02, C-web-application-example |
| C-python-testing-refs | docs(python-testing): add the skill's references and its generated navigation entries | `references/choosing-a-test-double.md`, `references/async-tests.md`, `references/reviewing-tests.md` | C-python-testing-01, C-python-testing-02 |
| C-python-tooling-01 | feat(python-tooling): vendor the linting, type checking, formatting, test configuration, package management rules | `python-static-checks`, `ruff-lint`, `mypy-type-checking`, `ruff-format`, `pytest-configuration`, `python-uv-workflow`, `python-pyproject-dependencies` | L0-15, L0-16 |
| C-python-tooling-refs | docs(python-tooling): add the skill's references and its generated navigation entries | `references/check-failures.md`, `references/uv-dependency-failures.md` | C-python-tooling-01 |
| C-ml-data-01 | feat(ml-data): vendor the serialization security, vectorization, indexing & mutation, dtypes & validation rules | `ml-serialization-security`, `ml-vectorization`, `ml-build-once`, `ml-data-transforms`, `ml-loc-assignment`, `ml-dtypes-at-load`, `ml-check-after-load`, `ml-frame-validation`, `ml-numpy-dtypes`, `ml-categorical-labels` | L0-15, L0-16, L0-02 |
| C-ml-data-02 | feat(ml-data): vendor the reproducibility, chaining style, typing, testing rules | `ml-seeded-randomness`, `ml-method-chaining`, `ml-named-aggregation`, `ml-array-typing`, `ml-numeric-assertions` | L0-15, L0-16 |
| C-ml-data-refs | docs(ml-data): add the skill's references and its generated navigation entries | `references/library-equivalents.md`, `references/review-signals.md` | C-ml-data-01, C-ml-data-02 |
| C-web-application-01 | feat(web-application): vendor the security rules | `web-object-authorization`, `web-jwt-validation`, `web-password-hashing`, `web-secure-tokens`, `web-cors-origins` | L0-15, L0-16 |
| C-web-application-02 | feat(web-application): vendor the database, async i/o rules | `sqlalchemy-bound-parameters`, `sqlalchemy-session-per-request`, `sqlalchemy-transaction-boundary`, `sqlalchemy-eager-loading`, `alembic-migrations`, `sqlalchemy-2-style`, `fastapi-no-blocking-calls`, `httpx-shared-client` | L0-15, L0-16, L0-02 |
| C-web-application-03 | feat(web-application): vendor the api design, app structure, observability, testing rules | `web-api-schemas`, `fastapi-error-boundaries`, `web-api-pagination`, `web-http-methods`, `fastapi-app-wiring`, `fastapi-dependency-providers`, `fastapi-thin-routes`, `fastapi-request-id-logging`, `fastapi-dependency-overrides`, `sqlalchemy-test-rollback` | L0-15, L0-16, L0-02 |
| C-web-application-04 | feat(web-application): vendor the api conventions rules | `fastapi-query-parameters`, `web-api-resource-naming`, `fastapi-openapi-metadata` | L0-15, L0-16 |
| C-web-application-refs | docs(web-application): add the skill's references and its generated navigation entries | `references/add-an-endpoint.md`, `references/api-review-checklist.md`, `references/request-lifecycle.md` | C-web-application-01, C-web-application-02, C-web-application-03, C-web-application-04 |
| C-web-application-example | feat(web-application): vendor the adapted fastapi-hotel-api example app | `examples/fastapi-hotel-api/` | C-web-application-01, C-web-application-02, C-web-application-03, C-web-application-04 |
| C-design-patterns-01 | feat(design-patterns): vendor the responsibilities, abstractions and coupling rules | `design-single-responsibility`, `design-tell-dont-ask`, `design-split-god-class`, `design-grasp-responsibilities`, `design-low-coupling`, `design-dependency-inversion`, `design-open-closed`, `design-composition-over-inheritance`, `design-liskov-substitution`, `design-interface-segregation` | L0-15, L0-16 |
| C-design-patterns-02 | feat(design-patterns): vendor the simplicity and restraint, smells and review rules | `design-dry-yagni-kiss`, `design-lightest-construct`, `design-pattern-from-smell`, `design-review-by-severity`, `design-start-with-the-data`, `design-name-for-intent`, `design-complete-construction` | L0-15, L0-16, C-design-patterns-01 |
| C-design-patterns-03 | feat(design-patterns): vendor the common patterns rules | `design-plugin-loading`, `design-dispatch-table`, `design-strategy`, `design-adapter`, `design-value-objects`, `design-domain-events`, `design-lazy-loading` | L0-15, L0-16, C-design-patterns-01 |
| C-design-patterns-04 | feat(design-patterns): vendor the specialized patterns rules | `design-callback`, `design-function-wrapper`, `design-function-builder`, `design-template-method`, `design-state`, `design-builder`, `design-fluent-interface`, `design-facade`, `design-pipeline`, `design-command`, `design-singleton`, `design-abstract-factory`, `design-bridge` | L0-15, L0-16, C-design-patterns-01 |
| C-design-patterns-refs | docs(design-patterns): add the skill's references and its generated navigation entries | `references/smell-catalog.md`, `references/quality-checklist.md`, `references/principles-and-grasp.md`, `references/refactoring-moves.md`, `references/lint-guardrails.md`, `references/strategy-progression.md`, `references/abstract-factory-progression.md`, `references/bridge-progression.md`, `references/command-progression.md`, `references/observer-mediator-pubsub.md`, `references/rule-neighbors.md` | C-design-patterns-01, C-design-patterns-02, C-design-patterns-03, C-design-patterns-04 |
| C-python-architecture-01 | feat(python-architecture): vendor the layers and imports, ports and boundaries, domain model rules | `arch-dependency-direction`, `arch-composition-root`, `arch-break-import-cycles`, `arch-use-case-functions`, `arch-typed-records-across-layers`, `arch-ports`, `arch-rich-domain-model`, `arch-ubiquitous-language` | L0-15, L0-16, C-web-application-example |
| C-python-architecture-02 | feat(python-architecture): vendor the persistence, layer tests rules | `arch-persistence-steps`, `arch-repository-port`, `arch-unit-of-work`, `sqlalchemy-engine-and-session-scope`, `sqlalchemy-repositories`, `arch-effects-after-commit`, `arch-test-use-cases-with-fakes`, `arch-contract-tests-for-fakes`, `arch-tests-by-layer`, `arch-make-legacy-testable` | L0-15, L0-16, C-python-architecture-01, C-web-application-example |
| C-python-architecture-03 | feat(python-architecture): vendor the project layout, cqrs and event sourcing rules | `arch-predictable-project-tree`, `arch-one-layout-axis`, `arch-no-junk-drawer-packages`, `arch-cqrs`, `arch-read-model-projections`, `arch-event-sourcing`, `arch-event-store` | L0-15, L0-16, C-python-architecture-01 |
| C-python-architecture-refs | docs(python-architecture): add the skill's references and its generated navigation entries | `references/architecture-review.md`, `references/where-code-goes.md` | C-python-architecture-01, C-python-architecture-02, C-python-architecture-03 |
| C-python-documentation-01 | feat(python-documentation): vendor the docs in sync, design records, repository files rules | `docs-same-change`, `docs-runnable-examples`, `docs-record-why`, `docs-document-layout`, `docs-architecture-overview`, `docs-readme-essentials`, `docs-changelog`, `docs-contributing-guide`, `docs-citation-file` | L0-15, L0-16 |
| C-python-documentation-02 | feat(python-documentation): vendor the user docs, docs build rules | `docs-page-kinds`, `sphinx-api-reference`, `mkdocs-api-reference`, `docs-check-in-ci`, `sphinx-docs-build`, `mkdocs-docs-build` | L0-15, L0-16 |
| C-python-documentation-refs | docs(python-documentation): add the skill's references and its generated navigation entries | `references/which-document.md` | C-python-documentation-01, C-python-documentation-02 |
| C-domino-apps-01 | feat(domino-apps): vendor the launch and routing, identity and access rules | `domino-app-bind-host-port`, `domino-app-url-prefix`, `domino-app-launch-script`, `domino-app-relative-urls`, `domino-app-publisher-data-rights`, `domino-app-viewer-identity`, `domino-app-verify-viewer-jwt`, `domino-app-viewer-token`, `domino-app-starter-settings`, `domino-app-endpoint-auth` | L0-15, L0-16 |
| C-domino-apps-02 | feat(domino-apps): vendor the persistence and state, framework setup rules | `domino-app-external-persistence`, `domino-app-concurrent-writes`, `domino-app-replica-state`, `domino-app-dash`, `domino-app-flask`, `domino-app-streamlit`, `domino-app-shiny`, `domino-app-static-site` | L0-15, L0-16, L0-02 |
| C-domino-apps-03 | feat(domino-apps): vendor the serving and limits, publishing and logging rules | `domino-app-production-server`, `domino-app-proxy-limits`, `domino-app-external-resources`, `domino-app-publish-from-commit`, `domino-app-deployment-record`, `domino-app-sharing-mode`, `domino-app-workspace-preview`, `domino-app-logging` | L0-15, L0-16, L0-02 |
| C-domino-apps-refs | docs(domino-apps): add the skill's references and its generated navigation entries | `references/app-troubleshooting.md` | C-domino-apps-01, C-domino-apps-02, C-domino-apps-03 |
| C-domino-jobs-01 | feat(domino-jobs): vendor the project and run environment rules | `domino-project-types`, `domino-secrets-in-env-vars`, `domino-paths-from-env`, `domino-api-proxy-auth`, `domino-env-var-names`, `domino-pinned-environments`, `domino-environment-revisions` | L0-15, L0-16 |
| C-domino-jobs-02 | feat(domino-jobs): vendor the entry points and exit codes, datasets rules | `domino-job-exit-codes`, `domino-job-entry-point`, `domino-launcher-arguments`, `domino-launcher-uploads`, `domino-datasets-for-large-data`, `domino-run-scoped-writes`, `domino-dataset-snapshots`, `domino-materialize-external-data` | L0-15, L0-16 |
| C-domino-jobs-03 | feat(domino-jobs): vendor the scheduling and launching, flow tasks, results and metrics rules | `domino-job-schedules`, `domino-idempotent-jobs`, `domino-spot-checkpoints`, `domino-launch-jobs-from-code`, `domino-flow-task-io`, `domino-flow-task-purity`, `domino-job-results`, `domino-job-logging`, `domino-job-stats-file`, `domino-job-email-report` | L0-15, L0-16 |
| C-domino-jobs-04 | feat(domino-jobs): vendor the reproducibility rules | `domino-run-manifest`, `domino-mlflow-tracking` | L0-15, L0-16 |
| C-domino-jobs-refs | docs(domino-jobs): add the skill's references and its generated navigation entries | `references/where-outputs-go.md` | C-domino-jobs-01, C-domino-jobs-02, C-domino-jobs-03, C-domino-jobs-04 |
| C-domino-agents-01 | feat(domino-agents): vendor the secrets and tokens, agent service rules | `domino-agent-llm-keys`, `domino-agent-access-token`, `domino-agent-endpoint-auth`, `domino-agent-redact-traces`, `domino-agent-app-factory`, `domino-agent-chat-endpoint`, `domino-agent-run-limits`, `domino-agent-conversation-state`, `domino-agent-logging` | L0-15, L0-16 |
| C-domino-agents-02 | feat(domino-agents): vendor the configuration, tracing, evaluation rules | `domino-agent-settings`, `domino-agent-config-file`, `domino-agent-trace-entrypoint`, `domino-agent-manual-spans`, `domino-agent-sdk-names`, `domino-agent-dev-eval-job`, `domino-agent-evaluators`, `domino-agent-eval-out-of-band`, `domino-agent-prod-eval-watermark` | L0-15, L0-16 |
| C-domino-agents-03 | feat(domino-agents): vendor the a2a protocol, testing rules | `a2a-mount-lifespan`, `a2a-agent-card`, `a2a-client-deadlines`, `domino-agent-fake-llm-tests`, `domino-agent-fake-domino-tests` | L0-15, L0-16, L0-02 |
| C-domino-agents-refs | docs(domino-agents): add the skill's references and its generated navigation entries | `references/agent-lifecycle.md`, `references/credentials-by-call.md` | C-domino-agents-01, C-domino-agents-02, C-domino-agents-03 |
| C-domino-agents-example | feat(domino-agents): vendor the adapted simple-agent-api example app | `examples/simple-agent-api/` | C-domino-agents-01, C-domino-agents-02, C-domino-agents-03 |
| C-playbook-creator-01 | feat(playbook-creator): vendor the layers, rules, validation rules | `playbook-ask-for-missing-inputs`, `playbook-layer-placement`, `playbook-override-by-id`, `playbook-rule-frontmatter`, `playbook-rule-ids`, `playbook-rule-gates`, `playbook-rule-templates`, `playbook-rule-body`, `playbook-validate-and-sync`, `playbook-engine-catalog-gate` | L0-15, L0-16, L0-00b, L0-07, L0-11, L0-12, L0-13, L0-19, L0-20, L0-21, L0-22, L0-23 |
| C-playbook-creator-02 | feat(playbook-creator): vendor the skills, hooks, prompts and eval samples, plugins and overlays rules | `playbook-skill-sections`, `playbook-skill-md`, `playbook-skill-files`, `playbook-hook-definition`, `playbook-hook-guardrails`, `playbook-prompt-frontmatter`, `playbook-eval-samples`, `playbook-plugin-layout`, `playbook-third-party-content` | L0-15, L0-16, L0-00b, L0-07, L0-11, L0-12, L0-13, L0-19, L0-20, L0-21, L0-22, L0-23 |
| C-playbook-creator-refs | docs(playbook-creator): add the skill's references and its generated navigation entries | `references/rule-template.md`, `references/skill-template.md`, `references/hook-template.md`, `references/prompt-template.md`, `references/eval-sample-template.md`, `references/plugin-template.md` | C-playbook-creator-01, C-playbook-creator-02 |

Domino skills: C-domino-apps-01, C-domino-jobs-01 and C-domino-agents-01 each also add the skill-level activation test that L0-20's first acceptance line defers until the skill exists: the Domino probe (tests/_budget_probe.py write_domino_probe) activates the skill, the standard probe does not, and platforms = ["domino"] activates it in a marker-free repo.

## Risks

- Forge #170 adds a sixth always-present core skill and possibly core rules: whichever of the two merges second rebases, moves its rules into skills/<skill>/rules (L0-07's R5 enforces it) and re-checks the known-skills quote, counts and budgets (D36).
- Listing budget is tight: seven member skills at the 300-char cap plus playbook-guardrails (~281) give ~2,381 of 2,400, and core plus mattpocock_skills (~3,780) reaches ~6,161 of 6,500 before forge's skill.
- Skill nudge is capped at 5 lines per hook and 8 per event (hook_runtime/dispatch/caps.py:68-69): with design-patterns, python-architecture and web-application members globbing **/*.py, one FastAPI+ML edit can match 6-7 skills, so later lines are deferred; nudge pins and goldens change per lane.
- Strict section: on rules that join a sectioned core skill through skill: (S4) and the in-band priority check (S6) break any consumer or overlay rule written for v0.20 core skills; there is no consumer yet (ADR 0002), but MIGRATION must say so (D-04).
- Every scoped rule's priority changes, so every .continue/rules/NN-<id>.md file is renamed and every eval prompt that includes rules changes (new bodies, [IMPACT] tag); F-01 is the only check against graded regressions.
- Rule bodies linking ../references/<file>.md dangle in Continue's per-rule files and in prompt and eval appendices, the same gap the license copy has.
- Unpinned ruff versions reformat markdown code blocks differently; 140+ vendored rules raise the chance that CI's ruff format --check . goes red on a version bump (memory: ruff-format .md CI blocker).
- Detector blind spots: Poetry dependencies and requirements*.txt are never read (detector/pyproject_deps.py), so has_dependency, web-application and DB gates are silently off in those repos.
- A skill with more than 20 rules of one impact runs out of band values; ties then sort by id and the mapping order is lost inside that band.
- tests/integration/test_core_skills.py (~630 lines) is a merge hotspot until L0-03 splits the pins; tickets in waves 2-6 that still edit it must rebase on each other.
- A future vendored plugin whose upstream skills ship a rules/ folder (as pbp itself does) would now have those files parsed as rules (R4/V14 errors) and could not stay byte-faithful.
- Real eval runs cost API time and need the owner's credentials; subagents must run them non-interactively and time-bounded or they hang.
