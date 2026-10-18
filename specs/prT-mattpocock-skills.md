# PR T - mattpocock_skills: Matt Pocock's skills as a vendored bundled plugin

Status: Accepted design, 2026-10-18. Every decision in section 2 was approved by the user on
2026-10-18 in a grilling session (rounds 1-4, questions Q1-Q32), and the work is implemented
autonomously under the user's mandate. This document does not reopen them.

- This spec: `specs/prT-mattpocock-skills.md` (D34), committed by PR A together with the plugin
  and the three `CONTEXT.md` terms (D36). No ADR (D34).
- Vocabulary: `CONTEXT.md` at the repository root is the only glossary. Every term below
  (bundled plugin, vendored content, distilled content, skill, reference, rule, always rule,
  scoped rule, skill root, skill listing, context budget, layer, core, adapter, harness, consumer
  repo, harness built-in, imposed tool, project toolchain) means what `CONTEXT.md` says. The
  shared skill root is `.agents/skills/`. The engine-authored rule this plugin ships is the
  **plugin always rule**.
- Anchors: a line number on an upstream file (for example "wizard SKILL.md L20") is a line of
  upstream tag v1.3.1, commit `24fe0ef7737efae15c87225755e9f6f5965e4888`. Every repository
  `file:line` was read at `a9e48e5` on 2026-10-18; re-verify an anchor before editing, because
  the parallel skills-first tickets move lines.
- Cross-references: `§x` names a section of `SPEC.md`; "section x" names a section of this spec;
  "prS" is `specs/prS-skills-context.md`; "A.T0x" names the part of the per-skill appendix that
  ticket T0x implements (A.T03 also holds the exact text of the plugin always rule).

This spec covers one integration branch, landed as PR A (plugin, gates, configuration, this spec)
and PR B (documentation), per D36. Sections 1-8 are the shared design, section 9 the tickets,
sections 10-11 risks and scope limits. The per-skill change lists are the appendix.

## 1. Summary and goal

**Why.** The user runs Matt Pocock's engineering and productivity skills today as the live
upstream Claude Code plugin. That copy works in one harness, follows upstream on every update,
and tells the agent to run tools a consumer repo may not have (a forge CLI, `jq`, `tput`, OS
openers, CDN assets, bash scripts). The goal is harness portability first (Claude Code, OpenCode,
Codex through the shared skill root, the Agent Harness adapter, and Continue when enabled) and a
pinned, reviewed copy instead of a moving one (D1, D5).

**What.** A new opt-in bundled plugin, `catalog/plugins/mattpocock_skills/`, enabled with
`coding_agent_playbook.plugins.mattpocock_skills` in `overlays_enabled` (D3). It holds vendored
content: the skills upstream v1.3.1 publishes under `skills/engineering/` and
`skills/productivity/`, near-verbatim, with every change listed in `ATTRIBUTIONS.md` (D4).

| Item | Count |
| --- | --- |
| Skills published by upstream v1.3.1 (engineering 20, productivity 7) | 27 |
| Dropped (`triage`, D7) | 1 |
| Shipped skills (D9) | 26 |
| Renamed to avoid Claude Code bundled skills (D8): `code-review` to `two-axis-review`, `pr` to `pr-body`, `prototype` to `throwaway-prototype` | 3 |
| User-invoked skills (`disable-model-invocation: true`, D19) | 15 |
| Upstream files vendored (26 `SKILL.md`, 19 supporting files, 2 scripts) | 47 files, 2,926 lines |
| Bash scripts rewritten in Python (D22) | 2 |
| Plugin always rule (D15), at most 60 words | 1 |
| Skill-listing characters of the 26 descriptions, measured on v1.3.1 | 3,734 |

**Constraints (D2).** A vendored skill may tell the agent to use only the Python standard
library, pip-installable packages, git, harness built-ins (loading a skill, subagents, background
agents, asking the user, todo lists, the harness's own web search and fetch, opening files) and
the consumer repo's project toolchain (its own test, typecheck, lint, build and dev-server
commands, even npm ones). Everything else is an imposed tool and is removed: `gh`, `glab`, the
JavaScript package runners as instructions (`npx`, `npm`, `pnpm`, `bun`, `yarn`, `deno`, `node`),
`jq`, `tput`, `curl`, `wget`, OS openers (`open`, `xdg-open`, `start`, `wslview`, `explorer.exe`),
`shellcheck`, `docker`, `puppeteer`, any bash script and any CDN asset. Matt's text otherwise
stays as he wrote it (D4), and nothing in the plugin carries a URL, attribution included.

## 2. Decisions

| # | Decision (short) | Answered |
| --- | --- | --- |
| D1 | Goal: harness portability first (Claude Code, OpenCode, Codex through `.agents/skills`, agent_harness, Continue when enabled), plus a pinned, reviewed copy instead of the live upstream Claude Code plugin. | Q1 |
| D2 | Allowed: stdlib, pip-installable packages, git, harness built-ins, the project toolchain. Every other executable is an imposed tool and is banned (list in section 1). | Q2, Q7 |
| D3 | Opt-in bundled plugin `catalog/plugins/mattpocock_skills/`, enabled as `coding_agent_playbook.plugins.mattpocock_skills` in `overlays_enabled`. | Q3, Q11 |
| D4 | Vendored content in the superpowers style: near-verbatim text, every change listed in `ATTRIBUTIONS.md`, upstream MIT `LICENSE` ("Copyright (c) 2026 Matt Pocock") at the plugin root and byte-identical in every skill's `references/`, provenance mattpocock/skills v1.3.1 commit `24fe0ef…`, no URL anywhere. | Q9 |
| D5 | Pinned snapshot of tag v1.3.1; an upgrade is a reviewed PR that diffs two upstream tags and replays the `ATTRIBUTIONS.md` change list. | Q4, Q5 |
| D6 | pr-body's "Summary visuals" menu reproduces HumanLayer's show-me skill (MIT, "Copyright (c) 2026 HumanLayer", repository humanlayer/skills, commit `653b6411c1f70c275a18e37673b042ff99f67ceb`): its notice ships as `references/LICENSE-show-me`, `CREDITS.md` moves to `references/` with link text kept and URLs removed, `metadata.credits.url` is deleted. | derived from the approved answers (no single Q) |
| D7 | Scope: the 27 skills of `skills/engineering` and `skills/productivity`; `misc/` and `in-progress/` are out; `triage` is dropped (consumers may add it at `playbook/skills/triage/`). | Q6, Q15 |
| D8 | Upstream ids are kept except collisions with Claude Code bundled skills, feature-gated ones included: `code-review` to `two-axis-review`, `pr` to `pr-body`, `prototype` to `throwaway-prototype`. wayfinder's `prototype` ticket type and UI.md's `/prototype/<name>` route are not skill ids and stay. The folder name equals the id. | Q11, Q18, Q19 |
| D9 | The 26 final ids (section 4.2). Layout-only keeps: throwaway-prototype (rename and layout), domain-modeling, wait-what, to-questionnaire; domain-modeling and wait-what still get D21. All others are vendored with listed changes. | derived from the approved answers (no single Q) |
| D10 | Only `SKILL.md`, `scripts/` and `references/` sync; every other skill-root file moves under `references/` with each link rewritten; `agents/openai.yaml` and upstream repo-level files are not shipped. | derived from the approved answers (no single Q) |
| D11 | Frontmatter: `id:` is the first key; every other key stays verbatim except pr-body's `metadata.credits.url`; no plugin skill gets a `playbook:` block. | derived from the approved answers (no single Q) |
| D12 | `ATTRIBUTIONS.md` names synced paths with the shared skill root, `.agents/skills/<id>/`. | derived from the approved answers (no single Q) |
| D13 | The tracker abstraction stays ("the issue tracker" described per repo); only the local-markdown tracker ships; a consumer may describe their own ("Other"); the plugin never names `gh` or `glab` as something to run. | Q8 |
| D14 | setup-matt-pocock-skills writes only `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and `docs/agents/domain.md`; local markdown is the default; "Other" fills the local seed's sections; the GitHub and GitLab templates go; `triage-labels.md` is always written; it never edits or creates `CLAUDE.md`/`AGENTS.md` and only reports an old "## Agent skills" block. | Q16, Q32.2, Q32.5, Q32.6, Q32.7 |
| D15 | The plugin always rule `mattpocock-skills-tracker` (`rules/`, `scope: always`, no `skill:`, plain `.md`, at most 60 words) replaces upstream's "## Agent skills" block. | Q16, Q32.1 |
| D16 | Local-tracker conventions: `.scratch/` is untracked and never staged; absolute main-checkout paths for subagents and worktrees; README gitignore advice; "closed" is `resolved` or `out-of-scope`; unblocked when every blocker is closed; implementation tickets set `resolved` on merge; `# <title>` heading per file; one writer of `map.md`; "Wayfinding operations" heading verbatim. | Q17, Q32.3, Q32.4 |
| D17 | Harness built-ins are named as capabilities with an inline fallback; `/clear` and `/compact` become "start a fresh context"; human-facing text keeps `/name`; agent-facing prose and operative loads use plain names. | Q10, Q20 |
| D18 | Seven fallbacks: two separate loads; grilling's fact-finding through a background agent only; research nesting guard; wayfinder leaves research tickets on the frontier; implement-spec's draft-PR hedge and sequential stop-and-resume flow; two-axis-review's sequential Standards-then-Spec flow; the "GitLab `!67`" example verbatim. | Q27.1-Q27.6, Q32.8 |
| D19 | Each of the 15 skills with `disable-model-invocation: true` gets the body line "Run this only when the user asked for it by name; otherwise stop."; a gate checks it; prS F6 must keep the key. | Q23, Q29 |
| D20 | Opening a generated file: "Open it for the user if your harness can open files, and tell them the absolute path either way."; prototype LOGIC.md L54 stays verbatim. | Q12, Q14 (round 3) |
| D21 | Every upstream file that names `GLOSSARY.md` or `GLOSSARY-MAP.md` gets "(or CONTEXT.md if the repo already has one)" and the MAP equivalent. | Q30 |
| D22 | The two bash scripts become Python >= 3.10, stdlib only, executable, `mypy --strict` and ruff clean: `diagnosing-bugs/scripts/hitl_loop_template.py` and `wizard/scripts/wizard_template.py`, with the listed behaviours. | Q12, Q27.8-Q27.12 |
| D23 | improve-codebase-architecture's HTML report is self-contained: one inline `<style>`, hand-built divs, inline SVG, no Tailwind or Mermaid CDN, no `xmlns`; D20 phrasing for opening it. | Q21 |
| D24 | teach: RESOURCES-FORMAT.md links keep their markdown shape with a `{link}` placeholder; L12 gains "the workspace is the current directory, never this skill's own directory" (upstream issue 377). | derived from the approved answers (no single Q; Q27/Q32 group) |
| D25 | handoff L10: "naming which skills the next session should use". | derived from the approved answers (no single Q; Q27/Q32 group) |
| D26 | retro and writing-for-agents: a file carrying the playbook's AUTOGENERATED sentinel, synced skill directories included, is changed in its source, never by hand; tests never paraphrase the sentinel. | Q32.12 |
| D27 | TypeScript, Jest and JS-frontend examples stay verbatim, recorded as a stack assumption. | Q26 |
| D28 | Verbatim on purpose: ask-matt's description, writing-for-agents' sibling-file advice, setup L30's JS-only monorepo markers, two-axis-review's 419-character description (plugins are exempt from the 300-character lint, prS D24). | Q32.11 |
| D29 | Continue gets degraded prompts only when the `continue` adapter is listed; the loss is accepted and documented per skill. | Q25 |
| D30 | The self-containment gate lives in `tests/plugins/mattpocock_skills/` (URLs, imposed tools, Claude-only names, coupling markers, layout, scripts, D19 guard, inventory in the final ticket, listing budget); `tests/integration/test_resources_self_contained.py` is not edited. | Q13, Q24, Q32.9 |
| D31 | prS D5 amended: core plus EACH bundled plugin is at most 6,000 characters; the reference probe keeps superpowers and python_design; the plugin README advises against enabling this plugin together with superpowers. | Q28 |
| D32 | `catalog/plugins/mattpocock_skills/**/*.md` joins ruff's `extend-exclude`; the `.py` scripts stay under ruff. | derived from the approved answers (no single Q) |
| D33 | Plugin README: enabling, the user-invoked skills and that only Claude Code honours `disable-model-invocation`, the Continue note, gitignoring `.scratch/`, budget advice, coexistence notes. | Q32.10 |
| D34 | The glossary terms imposed tool, project toolchain and harness built-in are in `CONTEXT.md` (done); the design spec is `specs/prT-mattpocock-skills.md`; no ADR. | Q14 |
| D35 | Docs PR B after the other session's ticket 13 (#53): SPEC §11.5.3 for this plugin, the README "Bundled plugins" section, a MIGRATION entry, a SPEC changelog bullet. | derived from the approved answers (no single Q) |
| D36 | One integration branch. PR A = plugin content, gates, pyproject exclude, `CONTEXT.md` terms, this spec; merged once ticket 10 (#50) is on main. PR B = D35, after #53, rebased late; one PR if #53 has merged by the time PR A is ready. | Q31 |
| D37 | Until those land, do not touch the skill writer, the adapters, validate code, the four budget and self-containment test files, `SPEC.md`, `README.md`, `MIGRATION.md` or `catalog/README.md`; a needed engine change is a separate small PR. | Q31 |
| D38 | Conventional Commit messages and PR titles; no `Co-Authored-By` trailers; no `--author`; squash merge after green CI. | Q31 |

### 2.1 Cross-spec notes

- **Amendment to prS D5 (from D31).** prS D5 (`specs/prS-skills-context.md:62`) reads "core plus
  every bundled plugin at most 6,000 characters". It becomes "core plus **each** bundled plugin is
  at most 6,000 characters". The prS reference probe keeps exactly superpowers and python_design
  (prS section 6.8.10), so its `test_core_and_plugin_descriptions_total_within_6000_chars` is
  unchanged; this spec's own budget test (section 7.5) checks core plus each bundled plugin
  separately. PR B states the amendment in SPEC §16 and §11.5.
- **F6 note (from D19).** prS follow-up F6 (`specs/prS-skills-context.md:5850`, "stripping
  non-standard frontmatter keys if Codex rejects them") must keep `disable-model-invocation`.
  Claude Code is the only harness that honours it today, and stripping it would turn the 15
  user-invoked skills into model-invoked ones there too. The D19 body line is a soft guard for
  every other harness, not a replacement for the key.

## 3. Engine and harness facts the design relies on

### 3.1 Engine (verified at a9e48e5)

- **E1. Skill sync copies only `SKILL.md`, `scripts/` and `references/`.** The loader records
  only those two subtrees on a `Skill` (`src/coding_agent_playbook/sources/filesystem.py:138-159`)
  and the writer writes `SKILL.md` plus byte-copies of the two subtrees
  (`src/coding_agent_playbook/adapters/_skill_writer.py:339-351`). Bytecode caches are never
  copied (`adapters/_skill_files.py:29-33`), and a secret path or a link leaving the skill is
  refused (`adapters/_skill_sources.py:97-104`). Any other file at a skill root is silently not
  synced, hence D10.
- **E2. `name` is forced to the id; every other key passes through.** `render_skill_md` drops the
  source `name`, writes `name: <id>` first and keeps the other keys in authored order
  (`_skill_writer.py:142-145`); the sentinel is the first body line (`_skill_writer.py:15-20`,
  `src/coding_agent_playbook/_sentinel.py:26`). Frontmatter is re-dumped with
  `yaml.safe_dump(sort_keys=False, allow_unicode=True)` (`src/coding_agent_playbook/types.py:61-64`),
  so quoting may change bytes in synced copies; tests compare parsed frontmatter, as
  `tests/plugins/python_design/test_pack.py:281-289` does.
- **E3. Only `id` and `description` are validated.** The Agent Skills checks are the id pattern
  `^[a-z0-9]+(-[a-z0-9]+)*$`, 64 characters, and a 1-1,024-character description
  (`adapters/_agent_skill_rules.py:27-29`, `:55-102`). `disable-model-invocation`,
  `argument-hint` and `metadata` pass through unchanged to the native roots. The Agent Harness
  adapter keeps `name` and `description` in `SKILL.md` and moves every other key to its manifest
  sidecar (`adapters/agent_harness_adapter.py:173-175`, `:221-223`); Continue's degraded prompt
  keeps only `id`, `name`, `description` and `slash` (`types.py:261-288`). Both read `name` from
  source, so a rename changes `name` with the id (D8).
- **E4. A `playbook:` key makes a skill a rule skill.** `is_rule_skill` keys on it
  (`src/coding_agent_playbook/skill_membership.py:49-54`); such a skill is dropped when no member
  rule is active (`skill_membership.py:57-74`) and its description is recomposed
  (`src/coding_agent_playbook/skill_document.py:178-193`). Hence D11's "no `playbook:` block".
- **E5. Plugin rules work with no engine change.** `list_rules` walks the `rules/` directory of
  every enabled layer (`sources/filesystem.py:282-312`); a later layer silently wins on an id
  (`src/coding_agent_playbook/orchestrator.py:83-95`); an unknown rule frontmatter key raises
  `TypeError` at load, because the loader calls `RuleFrontmatter(**data)` (`types.py:78-95`,
  `:130`). Rules are composed by `(priority, id)` into `.claude/rules/coding-agent-playbook.md`
  (`adapters/claude_code_adapter.py:6-9`) and `AGENTS.md` (`adapters/agents_md_adapter.py:61-73`),
  and Continue gets one `.continue/rules/{priority:02d}-{id}.md` per rule
  (`adapters/continue_adapter.py:6`). A `.md.j2` rule is rendered by Jinja with strict
  undefined variables, so the plugin always rule is plain `.md`.
- **E6. V1 and V3.** `RuleFrontmatter.skill` is "required for a scoped rule, forbidden for an
  always rule" (`types.py:92-95`). V1 ("scope 'scoped' needs 'skill: <skill-id>'") and V3
  ("'skill: …' is not allowed on an always rule") are specified at `specs/prS-skills-context.md:2084`
  and `:2086` and land with tickets 8 and 12 (#48, #52), not yet on main at `a9e48e5`. The plugin
  always rule carries no `skill:` and the plugin ships no scoped rule, so both pass before and
  after those tickets.
- **E7. The link validator.** `playbook validate` link-checks every markdown file of the
  `rules/`, `prompts/`, `skills/` and `hooks/` directories of every layer
  (`commands/_validate_links.py:29`), with the layer root as containment root, here the plugin
  directory (`_validate_links.py:126`). Frontmatter, fenced blocks and code spans are masked
  (`src/coding_agent_playbook/links.py:63-69`, `:164-191`); a relative target must exist, a `.j2`
  twin counts (`links.py:146-161`); a scheme link fails unless `[links] allowed_domains` allows it
  (`links.py:136-145`). A link to a plugin-root file (`README.md`, `LICENSE`, `ATTRIBUTIONS.md`)
  passes validate but is refused by `tests/integration/test_catalog_layout.py:146-157`, and
  `tests/cli/test_validate_links.py:252` link-gates every bundled plugin with no edit.
  Consequences: back-links `../SKILL.md` from `references/` and sibling links `../<id>/SKILL.md`
  pass; wayfinder's `(link)` target (v1.3.1 L44) and teach's example links (RESOURCES-FORMAT.md
  L12-L19) sit inside fenced blocks and pass, which is what makes D24's `{link}` placeholder safe.
- **E8. Ruff formats markdown.** CI runs `ruff format --check .`, which also formats code blocks
  inside markdown. `pyproject.toml:142-147` holds `extend-exclude`, with the python_design
  precedent `catalog/plugins/python_design/**/*.md` at `:144`; `force-exclude = true` (`:152`)
  keeps the exclude in force when pre-commit passes file names; plugin scripts already get the
  py310 target (`:155`); mypy's `files` are `src` and `tests` only (`:185`), so the scripts' strict
  mypy run lives in our tests. `tests/integration/test_ruff_scope.py:83-89` pins the existing
  globs with `in` checks, so one more glob breaks nothing.
- **E9. The generic self-containment scan already covers a new plugin.** Every plugin directory
  not in `_VENDORED_PLUGIN_GATES` is scanned (`tests/integration/test_resources_self_contained.py:77-79`,
  `:170-172`, `:285-289`) with a URL regex that includes a bare domain followed by a path and
  `git@` (`:92-98`) and a marker regex that includes `claude_plugin_root` and `.claude/plugins`
  (`:102-105`), over every text file except the root `ATTRIBUTIONS.md`. Over the v1.3.1 text of
  the 26 skills, the marker regex finds nothing and every bare-domain hit sits inside an
  `http(s)` URL that D4 removes, so the file needs no edit (D30). The plugin README must
  therefore never name `.claude/plugins`.
- **E10. Plugin skills are generated output.** Under the default `[output] commit = false` the
  managed `.gitignore` block lists each synced skill directory and every synced `SKILL.md`
  carries the sentinel as its first body line (§11.5, `SPEC.md:2067-2110`). A synced skill
  directory is therefore not an editable source, which D26 and D24 rely on.
- **E11. Hooks that meet the plugin.** secrets-path-guard denies `.env` and `.env.*` reads except
  `.env.example`, `.env.sample`, `.env.template` and `.env.dist`
  (`src/coding_agent_playbook/security/patterns.py:108-113`) and runs only on Claude Code and
  OpenCode (`catalog/core/hooks/safety/secrets-path-guard/HOOK.md:20`); hence D22's read list for
  wizard. guard-generated-outputs runs only on Claude Code and OpenCode
  (`catalog/core/hooks/protect/guard-generated-outputs/HOOK.md:26`); elsewhere only D26's wording
  stops a hand edit of generated files.
- **E12. Continue is opt-in.** `playbook init` enables `claude_code`, `opencode` and
  `shared_skills`; `continue` is an explicit choice (`commands/_init_adapters.py:11-19`).
- **E13. The skill listing is measured per layer.** `FileSystemArtifactSource.layer_roots` lists
  `(source_package, <layer>/<kind>)` for each layer that has the kind directory, in resolution
  order, and skips a layer without one (`sources/filesystem.py:282-302`; a bundled layer without
  the directory resolves to `None`, `:105-121`); `list_skills` yields each skill with its layer
  label (`:320-325`). Core ships no `catalog/core/skills/` at `a9e48e5`, so core contributes no
  skill today; ticket 10 (#50) adds four. The emitted description of a rule skill is
  `emitted_frontmatter(skill)["description"]` after `compose_skills` (`skill_document.py:178-193`,
  `skill_membership.py:57-74`); a plain skill's emitted frontmatter equals its source.

### 3.2 Harnesses

- **H1. Claude Code (2.1.29x-2.1.302).** The skill listing (name, description, `when_to_use`,
  capped at 1,536 characters per skill) is sent every turn within about 1% of the context window,
  about 6,000 characters at 200k; overflow drops descriptions of the least-used skills
  (`specs/prS-skills-context.md:87-95`). A project skill named like a bundled skill replaces its
  slash command; precedence is enterprise, then personal, then project; plugin skills are
  namespaced and coexist with same-named project skills; `disable-model-invocation: true` blocks
  model invocation and removes the description from the listing while `/name` still works;
  `argument-hint` and `allowed-tools` are Claude Code-only. Bundled skill names in 2.1.292
  include `code-review`, `pr` (feature-gated, built on the `gh` CLI), `prototype`
  (feature-gated), `simplify`, `commit`, `commit-push-pr`, `verify`, `design`, `dataviz`, `loop`,
  `schedule`, `workflow-authoring` and `run`. Source: the Claude Code 2.1.292 binary and skills
  documentation as read for the audit synthesis (`audit-synth.json`, `engine_facts_summary`
  items 9 and 10); not re-read at `a9e48e5`. None of the 26 final ids is among them, among the
  core prompt ids (`catalog/core/prompts/`: characterize, explain, find-injected-vulnerability,
  generate-tests, make-testable, refactor, review, review-architecture, security-review), or
  among the superpowers and python_design skill ids.
- **H2. OpenCode (v1.19.3, v2.0.32).** Skill roots are `.opencode/skills` (native) plus
  `.agents/skills` and `.claude/skills` (compatibility); one id in several roots is registered
  once (v2 precedence `.opencode > .agents > .claude`; v1 logs a duplicate warning); about 60-90
  tokens of listing per skill (`specs/prS-skills-context.md:96-103`). It ignores
  `disable-model-invocation`.
- **H3. Codex (rust-v0.163.0).** Reads skills from `<dir>/.agents/skills` for every directory from
  the project root to the working directory, with a catalog budget of 2% of the window or 8,000
  characters (`specs/prS-skills-context.md:104-108`); the `shared_skills` adapter writes that root
  (`adapters/shared_skills_adapter.py:3-7`, `:36-37`). It ignores `disable-model-invocation`.
- **H4. Continue (maintenance freeze).** The IDE reads `.continue/rules`, the root `AGENTS.md`,
  and skills from `.continue/skills` and `.claude/skills` (not `.agents/skills`) through
  `read_skill` in Agent and Plan modes only (`specs/prS-skills-context.md:109-115`). The engine's
  `continue` adapter degrades each skill to `.continue/prompts/<id>.md`, body only: no
  `references/`, no `scripts/`, no `LICENSE` copy, broken relative links (§11.5.1 "Rendering per
  adapter"). Hence D29.

### 3.3 Budget numbers

| Quantity | Characters | Source |
| --- | --- | --- |
| The 26 vendored descriptions as of v1.3.1 (two-axis-review 417 after YAML unescaping; D28's 419 counts the two backslash escapes) | 3,734 | measured over the upstream frontmatter |
| Core skill descriptions today | 0 | no `catalog/core/skills/` at `a9e48e5` |
| Core after ticket 10 (#50) / after PR 4 (#56) / after PR 8 | 762 / 1,043 / 1,238 | `specs/prS-skills-context.md:46-52`, `:2035-2046` |
| Core plus this plugin: today / after #50 / after PR 8 | about 3,734 / 4,496 / 4,974 | D30 |
| Core plus this plugin, measured at T10b (after #72) | 4,542 (core 762, plugin 3,780) | `test_budget.py` |
| Limit for core plus each bundled plugin | 6,000 | prS D5 as amended by D31 |

The listed description edits (wizard's "bash" for D22, the D21 clause where a description names
`GLOSSARY.md`) move the plugin total by under 50 characters. The test counts every description,
including the 15 that Claude Code drops from its listing, because OpenCode and Codex list them.

## 4. Before and after

### 4.1 Before

`catalog/plugins/` holds `python_design/` and `superpowers/`; `tests/plugins/` holds the
superpowers gate files and `python_design/`. The source is the upstream checkout at tag v1.3.1
(read only, never executed), laid out as:

```text
upstream v1.3.1
├── LICENSE                                   MIT, "Copyright (c) 2026 Matt Pocock", 1,068 bytes
├── skills/engineering/
│   ├── ask-matt/            SKILL.md  PHASE-BOUNDARIES.md  agents/openai.yaml
│   ├── code-review/         SKILL.md  agents/openai.yaml
│   ├── codebase-design/     SKILL.md  DEEPENING.md  DESIGN-IT-TWICE.md  agents/openai.yaml
│   ├── diagnosing-bugs/     SKILL.md  scripts/hitl-loop.template.sh  agents/openai.yaml
│   ├── domain-modeling/     SKILL.md  ADR-FORMAT.md  GLOSSARY-FORMAT.md  agents/openai.yaml
│   ├── grill-with-docs/     SKILL.md  agents/openai.yaml
│   ├── implement/           SKILL.md  agents/openai.yaml
│   ├── implement-spec/      SKILL.md  agents/openai.yaml
│   ├── improve-codebase-architecture/   SKILL.md  HTML-REPORT.md  agents/openai.yaml
│   ├── pr/                  SKILL.md  CREDITS.md  agents/openai.yaml
│   ├── prototype/           SKILL.md  LOGIC.md  UI.md  agents/openai.yaml
│   ├── research/            SKILL.md  agents/openai.yaml
│   ├── retro/               SKILL.md  agents/openai.yaml
│   ├── setup-matt-pocock-skills/        SKILL.md  domain.md  issue-tracker-github.md (dropped)
│   │                                    issue-tracker-gitlab.md (dropped)  issue-tracker-local.md
│   │                                    triage-labels.md  agents/openai.yaml
│   ├── tdd/                 SKILL.md  mocking.md  tests.md  agents/openai.yaml
│   ├── to-spec/             SKILL.md  agents/openai.yaml
│   ├── to-tickets/          SKILL.md  agents/openai.yaml
│   ├── triage/              SKILL.md  AGENT-BRIEF.md  OUT-OF-SCOPE.md  agents/openai.yaml  (dropped, D7)
│   ├── wayfinder/           SKILL.md  agents/openai.yaml
│   └── wizard/              SKILL.md  template.sh  agents/openai.yaml
├── skills/productivity/
│   ├── grill-me/  grilling/  handoff/  to-questionnaire/  wait-what/   SKILL.md  agents/openai.yaml
│   ├── teach/               SKILL.md  GLOSSARY-FORMAT.md  LEARNING-RECORD-FORMAT.md
│   │                        MISSION-FORMAT.md  RESOURCES-FORMAT.md  agents/openai.yaml
│   └── writing-for-agents/  SKILL.md  SKILL-MECHANICS.md  agents/openai.yaml
└── (not shipped) skills/{misc,in-progress,deprecated}/, skills/*/README.md, .agents/,
    .changeset/, .claude-plugin/, .github/, .out-of-scope/, docs/, scripts/, CHANGELOG.md,
    README.md, CLAUDE.md, AGENTS.md, GLOSSARY.md, package*.json
```

### 4.2 After: the bundled plugin

Every skill directory also holds `references/LICENSE`, a byte copy of the plugin `LICENSE`; it is
written once here and left out of the per-skill lines.

```text
catalog/plugins/mattpocock_skills/
├── LICENSE                         upstream MIT text, byte-identical (D4)
├── ATTRIBUTIONS.md                 provenance and the full change list (section 5.3)
├── README.md                       enabling, harness notes, coexistence (section 5.4, D33)
├── rules/
│   └── mattpocock-skills-tracker.md      the plugin always rule (D15, T03)
└── skills/
    ├── ask-matt/                   SKILL.md  references/PHASE-BOUNDARIES.md
    ├── codebase-design/            SKILL.md  references/{DEEPENING,DESIGN-IT-TWICE}.md
    ├── diagnosing-bugs/            SKILL.md  scripts/hitl_loop_template.py
    ├── domain-modeling/            SKILL.md  references/{ADR-FORMAT,GLOSSARY-FORMAT}.md
    ├── grill-me/                   SKILL.md
    ├── grill-with-docs/            SKILL.md
    ├── grilling/                   SKILL.md
    ├── handoff/                    SKILL.md
    ├── implement/                  SKILL.md
    ├── implement-spec/             SKILL.md
    ├── improve-codebase-architecture/    SKILL.md  references/HTML-REPORT.md
    ├── pr-body/                    SKILL.md  references/{CREDITS.md,LICENSE-show-me}   (was pr)
    ├── research/                   SKILL.md
    ├── retro/                      SKILL.md
    ├── setup-matt-pocock-skills/   SKILL.md  references/{domain,issue-tracker-local,triage-labels}.md
    ├── tdd/                        SKILL.md  references/{mocking,tests}.md
    ├── teach/                      SKILL.md  references/{GLOSSARY-FORMAT,LEARNING-RECORD-FORMAT,
    │                                         MISSION-FORMAT,RESOURCES-FORMAT}.md
    ├── throwaway-prototype/        SKILL.md  references/{LOGIC,UI}.md         (was prototype)
    ├── to-questionnaire/           SKILL.md
    ├── to-spec/                    SKILL.md
    ├── to-tickets/                 SKILL.md
    ├── two-axis-review/            SKILL.md                                   (was code-review)
    ├── wait-what/                  SKILL.md
    ├── wayfinder/                  SKILL.md
    ├── wizard/                     SKILL.md  scripts/wizard_template.py
    └── writing-for-agents/         SKILL.md  references/SKILL-MECHANICS.md
```

78 files: 26 `SKILL.md`, 19 moved supporting files, 26 `references/LICENSE` copies, one
`references/LICENSE-show-me`, two scripts, the rule, and the three root files.

### 4.3 After: the tests

```text
tests/plugins/mattpocock_skills/
├── __init__.py
├── conftest.py              T01  package-scoped fixture: a probe repo synced with the plugin
├── _expectations.py         T01  constants, scanners, allowlist loader (section 7.2); lanes never edit it
├── test_gates.py            T01  the shared gate, parametrised over the skills present (section 7.1)
├── test_budget.py           T01  core plus each bundled plugin within 6,000 characters (section 7.5)
├── test_sync.py             T01  end-to-end init and sync with the plugin enabled
├── test_grilling.py         T02  grilling, grill-me, grill-with-docs, domain-modeling
├── test_tracker.py          T03  setup-matt-pocock-skills, to-spec, to-tickets, the plugin always rule
├── test_flow.py             T04  wayfinder, implement-spec, implement
├── test_review.py           T05  two-axis-review, pr-body, tdd
├── test_architecture.py     T06  improve-codebase-architecture, codebase-design, throwaway-prototype
├── test_debug_wizard.py     T07  diagnosing-bugs, wizard (script behaviour included)
├── test_session.py          T08  research, retro, handoff, teach, writing-for-agents
├── test_router.py           T09  ask-matt
├── test_inventory.py        T10  the D9 inventory pin and the completeness checks (section 7.8)
└── allowlist/
    ├── ask-matt.txt
    ├── codebase-design.txt
    ├── …                    one <id>.txt per final id, 26 files, each owned by the ticket of its skill
    └── writing-for-agents.txt
```

### 4.4 Other repository files

| File | Change | Ticket |
| --- | --- | --- |
| `pyproject.toml` | `"catalog/plugins/mattpocock_skills/**/*.md"` added to `[tool.ruff] extend-exclude`, after the python_design line (`:144`) | T01 |
| `CONTEXT.md` | the "What a skill may run" section with harness built-in, imposed tool and project toolchain (already in the working tree, D34) | T01 commits it |
| `specs/prT-mattpocock-skills.md` | this spec | T01 commits it |
| `SPEC.md`, `README.md`, `MIGRATION.md` | D35 | T11 (PR B) |

Nothing under `src/` changes.

## 5. Plugin design

### 5.1 Layout rules (D10-D12)

- **Flat skill directories.** Upstream's `skills/<group>/<old-id>/` becomes `skills/<id>/`; the
  group level goes and the folder equals the final id (D8).
- **Three entries per skill.** A skill directory holds `SKILL.md`, and optionally `scripts/` and
  `references/`, nothing else (E1). Every other upstream file at a skill root moves to
  `references/<same name>` with its content unchanged (the list is in section 5.3,
  "Restructure"). Links are rewritten: `SKILL.md` links to `references/<file>`; a back-link from a
  moved file becomes `../SKILL.md`; a link between two moved files stays as written; link text
  that is a code-formatted path carries the new path. Consumer paths that only look similar
  (teach's `./reference/`, a consumer's `scripts/`) are not touched.
- **Scripts.** The two Python rewrites live in `scripts/`, start with `#!/usr/bin/env python3`
  and are committed with mode 100755 (D22).
- **Not shipped.** `agents/openai.yaml` (Codex UI metadata) and every upstream repo-level file
  listed in section 4.1.
- **Frontmatter (D11).** `id: <dir-name>` is inserted as the first line of the frontmatter;
  `name` equals the id (renamed skills change both, D8); `disable-model-invocation`,
  `argument-hint` and `metadata` stay verbatim, except pr-body's `metadata.credits.url` line,
  which is deleted (D6). No skill gets a `playbook:` block (E4), and no file in the plugin is a
  `.j2` template.
- **Plugin root.** Exactly `LICENSE`, `ATTRIBUTIONS.md`, `README.md`, `skills/` and `rules/`.
  The root files ship in the wheel, are never synced and are never linked from a skill (E7).
- **Synced paths in prose (D12).** `ATTRIBUTIONS.md` names a synced file as
  `.agents/skills/<id>/<path>`; the other skill roots hold the same bytes.

### 5.2 LICENSE handling (D4, D6)

- `LICENSE` at the plugin root is upstream's file, byte for byte: 1,068 bytes, SHA-256
  `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5`, first lines "MIT License"
  and "Copyright (c) 2026 Matt Pocock". `_expectations.py` pins the digest, so a re-pin (D5) that
  changes the licence fails loudly.
- Every skill ships `references/LICENSE`, byte-identical to the root file, so the MIT notice
  travels with each synced directory: `.claude/skills/<id>/`, `.opencode/skills/<id>/`,
  `.agents/skills/<id>/` and the Agent Harness `skills/<id>/`.
- pr-body also ships `references/LICENSE-show-me`: the MIT text with HumanLayer's notice
  ("Copyright (c) 2026 HumanLayer"), for the "Summary visuals" menu it reproduces (D6). Its
  provenance (repository humanlayer/skills, commit `653b6411c1f70c275a18e37673b042ff99f67ceb`)
  is written in `ATTRIBUTIONS.md` and in `references/CREDITS.md`, without URLs.
- Continue's degraded prompts carry no licence copy (H4); the README and `ATTRIBUTIONS.md` say
  that a repo rendering the plugin only for Continue keeps a copy of `LICENSE` itself.

### 5.3 ATTRIBUTIONS.md

The structure follows `catalog/plugins/superpowers/ATTRIBUTIONS.md` and §11.5.1, with the extra
categories this plugin needs. T01 writes the file whole: the title, every global section in full,
and one placeholder section per skill. A global section is written once and only T10 may edit it
afterwards; a lane that finds a global statement wrong records the correction in its own skill
section and T10 folds it in.

```markdown
# Attributions

## Provenance
## License copies
## Restructure
## Frontmatter
## Renames
## Cross-skill references
## No external URLs
## Imposed tools removed
## Harness built-ins reworded
## Script ports
## Plugin always rule
## Dropped and why
## Third-party content
## Consumer-repo conventions
## Rendering per adapter
## Gates

## Per-skill changes

### ask-matt

_Filled by T09._

### codebase-design

_Filled by T06._

(one section per final id, in alphabetical order)
```

What each global section says (T01 writes these from the decisions; the per-skill details stay
in the skill sections):

1. **Provenance.** Vendored content of Matt Pocock's skills, repository name mattpocock/skills,
   tag v1.3.1, commit `24fe0ef7737efae15c87225755e9f6f5965e4888`, MIT, "Copyright (c) 2026 Matt
   Pocock". Scope: the skills of `skills/engineering/` and `skills/productivity/` except triage
   (D7). Matt's text is kept near-verbatim; every change is listed below. Upgrade procedure: a
   reviewed PR that diffs two upstream tags and replays this list (D5).
2. **License copies.** Section 5.2, including the Continue caveat.
3. **Restructure.** Only `SKILL.md`, `scripts/` and `references/` sync (D10). Moved under
   `references/`: ask-matt `PHASE-BOUNDARIES.md`; codebase-design `DEEPENING.md`,
   `DESIGN-IT-TWICE.md`; domain-modeling `ADR-FORMAT.md`, `GLOSSARY-FORMAT.md`;
   improve-codebase-architecture `HTML-REPORT.md`; pr-body `CREDITS.md`; throwaway-prototype
   `LOGIC.md`, `UI.md`; setup-matt-pocock-skills `domain.md`, `issue-tracker-local.md`,
   `triage-labels.md`; tdd `mocking.md`, `tests.md`; teach `GLOSSARY-FORMAT.md`,
   `LEARNING-RECORD-FORMAT.md`, `MISSION-FORMAT.md`, `RESOURCES-FORMAT.md`; writing-for-agents
   `SKILL-MECHANICS.md`. Rewritten into `scripts/`: diagnosing-bugs
   `scripts/hitl-loop.template.sh` as `scripts/hitl_loop_template.py`, wizard `template.sh` as
   `scripts/wizard_template.py` (see Script ports). The link rules of section 5.1. Not shipped:
   `agents/openai.yaml` in every skill (with it goes `policy.allow_implicit_invocation`;
   `disable-model-invocation` stays the only user-invoked marker) and the repo-level files of
   section 4.1. The group directories are flattened.
4. **Frontmatter.** `id` first; `name` equals the id; other keys verbatim; pr-body's
   `metadata.credits.url` deleted; no `playbook:` block. Descriptions are verbatim except where a
   skill section lists a change (expected: wizard for D22, domain-modeling for D21). Sync
   re-dumps frontmatter (E2), so quoting may differ in synced copies.
5. **Renames.** The three D8 renames, why (a project skill named like a Claude Code bundled skill
   replaces its slash command, H1; the bundled `pr` builds on the `gh` CLI), and what moved with
   them: directory, `id`, `name`, every inbound load, prose mention and router label. Unchanged:
   wayfinder's `prototype` ticket type and UI.md's `/prototype/<name>` route.
6. **Cross-skill references.** "Call the Skill tool with X" and operative "/x" become "Load the
   `x` skill" (D17); a step that needs two skills becomes two separate loads with no order
   implied (D18.1); human-facing `/name` stays (router labels, user-invoked descriptions, "tell
   the user to run `/x`"); every load target ships in this plugin and is model-invoked; triage is
   removed from lists and routes (D7).
7. **No external URLs.** None anywhere in the plugin, `LICENSE`, `README.md` and this file
   included. Link text stays as plain text; example URLs become scheme-less placeholders (teach's
   `{link}`, D24; wizard's dashboard placeholder, D22); upstream issues are cited as "upstream
   issue 377" and "upstream issue 530"; no SVG `xmlns` (D23).
8. **Imposed tools removed.** The D2 policy and what it removed: the forge CLIs (setup's GitHub
   and GitLab seeds; wizard's secret and variable writes), `tput`, `wslview`, `explorer.exe`,
   `xdg-open`, `open` and `start` (wizard, improve-codebase-architecture), `curl` and Puppeteer
   options (diagnosing-bugs `SKILL.md` L27, L29, L59) and the localhost URL in its script,
   `shellcheck` and `bash -n` (wizard's verify step),
   Tailwind and Mermaid "via CDN" (the architecture report), and both bash scripts. Project
   toolchain examples stay (D27, D28).
9. **Harness built-ins reworded.** The D17 capability-plus-fallback phrasing, "start a fresh
   context" for `/clear` and `/compact`, the D18 fallbacks, the D20 open-file sentence and the
   D19 guard line.
10. **Script ports.** D22 in full for both scripts, and the behaviour that differs from upstream:
    no WSL opener; `webbrowser` instead of OS openers, with scheme-less arguments printed, not
    launched; `getpass` for secrets; in both scripts, a non-TTY guard that exits 2 and asks the
    agent to have the user run `python3 <copy>` in their own terminal (the HITL loop also asks for
    the Captured block back); in the wizard, Ctrl-C handling, end of file mid-run read as an empty
    answer, `set_secret` and `set_var` as guided manual steps and an atomic `.env` upsert.
11. **Plugin always rule.** `rules/mattpocock-skills-tracker.md` is engine-authored, not upstream
    text. It replaces the "## Agent skills" block upstream's setup wrote into `CLAUDE.md` or
    `AGENTS.md` (D14, D15). This section names the file, its id and scope and what it says; the
    text itself lives only in the rule file (A.T03).
12. **Dropped and why.** triage (the local tracker has no category field, close-as-wontfix,
    reporter loop or PR surface; add it repo-locally at `playbook/skills/triage/`); setup's
    GitHub and GitLab seeds and the PR/MR-as-request flag; setup's `CLAUDE.md`/`AGENTS.md`
    writing steps; `agents/openai.yaml`; wizard's automatic forge writes, its `tput` colours and
    its OS openers (`wslview`, `explorer.exe`, `xdg-open`, `open`; ANSI escapes and `webbrowser`
    replace them, and the WSL opener is lost); the report's CDN assets; `metadata.credits.url`; `misc/`, `in-progress/` and `deprecated/`; the
    repo-level files.
13. **Third-party content.** pr-body's "Summary visuals" menu (D6), with its licence file and
    credits file; the Agent Harness adapter moves `metadata` to its sidecar and Continue drops
    both `metadata` and `references/`.
14. **Consumer-repo conventions.** Paths inside the consumer repo, not dependencies:
    `docs/agents/issue-tracker.md`, `triage-labels.md`, `domain.md`; `.scratch/<slug>/` (local
    tracker files, untracked); `GLOSSARY.md` and `GLOSSARY-MAP.md` or `CONTEXT.md` and
    `CONTEXT-MAP.md` (D21); `docs/adr/`; teach's workspace files in the current directory; the
    OS temporary directory for the architecture report and the handoff file. Stack assumptions:
    the TypeScript, Jest and JS-frontend examples (D27) and setup's JS-only monorepo markers
    (D28).
15. **Rendering per adapter.** Native (`claude_code`, `opencode`, `shared_skills`): byte-identical
    copies, `name` = id, sentinel first body line, scripts keep their executable bit. Agent
    Harness (opt-in): `skills/<id>/` with keys beyond `id`, `name` and `description` in
    `.playbook/manifest.toml`. Continue (opt-in, D29): body-only prompts. The plugin always rule
    reaches `.claude/rules/coding-agent-playbook.md`, `AGENTS.md`, one `.continue/rules/` file
    when `continue` is listed, and the Agent Harness `rules/`. Only Claude Code honours
    `disable-model-invocation`; elsewhere the D19 guard line asks the model to stop.
16. **Gates.** The test files of section 7.1, and the generic gates that cover the plugin with no
    edit (section 7.9).

Each per-skill section, once filled, opens with the upstream path and the synced path (for
example "Upstream `skills/engineering/code-review/`; synced as `.agents/skills/two-axis-review/`")
and lists each change as "`<file>` L<n> (v1.3.1): <change> (<decision>)", then the Continue
degradation for that skill (D29). The placeholder line `_Filled by T0x._` is the only line a lane
replaces; it never edits a heading or the blank line before the next heading, so parallel lanes
change separate hunks.

| Ticket | Per-skill sections it fills |
| --- | --- |
| T01 | to-questionnaire, wait-what |
| T02 | domain-modeling, grill-me, grill-with-docs, grilling |
| T03 | setup-matt-pocock-skills, to-spec, to-tickets |
| T04 | implement, implement-spec, wayfinder |
| T05 | pr-body, tdd, two-axis-review |
| T06 | codebase-design, improve-codebase-architecture, throwaway-prototype |
| T07 | diagnosing-bugs, wizard |
| T08 | handoff, research, retro, teach, writing-for-agents |
| T09 | ask-matt |

### 5.4 README.md (D33)

T01 writes the skeleton (title, the "what it is" paragraph, the enable snippet, and the headings
below, each with the placeholder `_Filled by T10._`); T10 writes the final text. Outline:

1. **What it is.** Vendored content of Matt Pocock's skills (MIT; see `LICENSE` and
   `ATTRIBUTIONS.md`, named as plain file names, never linked), 26 skills, pinned to v1.3.1.
2. **Enable it.** The top-level `overlays_enabled = ["coding_agent_playbook.plugins.mattpocock_skills"]`
   line above the first `[table]` header, then `playbook sync`; run `/setup-matt-pocock-skills`
   once to write `docs/agents/`; add `.scratch/` to the repo's `.gitignore` (D16).
3. **User-invoked skills.** The 15 ids; only Claude Code honours `disable-model-invocation`;
   elsewhere each starts with the D19 guard line.
4. **Harnesses.** Codex and OpenCode read the shared skill root; Continue is opt-in and gets
   degraded prompts without references, scripts or the licence (D29).
5. **Listing budget.** The 26 descriptions cost about 3,700 characters of skill listing in every
   session; do not enable this plugin together with superpowers (D31).
6. **Coexistence.** superpowers pairs that overlap: tdd and test-driven-development,
   diagnosing-bugs and systematic-debugging, writing-for-agents and writing-skills,
   two-axis-review and requesting-code-review / receiving-code-review, grilling and
   brainstorming. Core's python-testing skill and tdd. Core's review and review-architecture
   prompts and two-axis-review and improve-codebase-architecture. The upstream Claude Code plugin:
   disable it where this plugin is enabled. "A personal skill with the same name outranks a
   project skill in Claude Code" (stated generically; it never names the user's own tools).
7. **Overriding and re-adding.** `playbook/skills/<id>/` replaces one plugin skill; triage can be
   added the same way.

The README is scanned for URLs and for the generic markers (E9), so it never writes
`.claude/plugins` or a plugin-install command.

### 5.5 The plugin always rule (D15)

`catalog/plugins/mattpocock_skills/rules/mattpocock-skills-tracker.md`, owned by T03. Its exact
frontmatter and body are in appendix A.T03. Constraints any text must meet:

- Plain `.md` (E5); frontmatter keys only from `RuleFrontmatter` (`types.py:78-95`): `id`,
  `name`, `description`, `version`, `scope`, `priority`, `tags`; `id: mattpocock-skills-tracker`
  (unique, so a generic id cannot be silently overridden); `scope: always`; no `skill:` (V3), no
  `globs`, no `applies_if` (the rule is on whenever the plugin is enabled); a `priority` above
  the core always rules (0 and 10) so it renders after them.
- Body at most 60 words (`len(body.split())`). It names `docs/agents/issue-tracker.md`,
  `docs/agents/triage-labels.md` and `docs/agents/domain.md` as this repo's tracker, label and
  domain configuration for these skills; says that if they are missing the user should be told to
  run `/setup-matt-pocock-skills`; and says `.scratch/` is untracked working state that is never
  staged.
- It names no `references/` path (the skill root differs per adapter) and never presents a
  setup-only file as always present.

## 6. Tracker and setup design (D13-D16)

The exact texts (the new setup flow, the local seed's added sections, the "Other" template, the
always rule) are in appendix A.T03; wayfinder's and implement-spec's sides are in A.T04.

**The abstraction (D13).** Skills keep upstream's verbs: publish to "the issue tracker", fetch
the relevant ticket, close work "the way the issue tracker closes work". What the tracker is lives
in the consumer repo's `docs/agents/issue-tracker.md`. Only the local-markdown description ships.
A consumer with another tracker describes it ("Other"); the plugin may name products (GitHub,
GitLab, Jira, Linear) but never a CLI to run.

**What setup does (D14).**

1. Explore: `git remote -v`, the root `CLAUDE.md`/`AGENTS.md` only to look for an old
   "## Agent skills" block, `GLOSSARY.md`/`GLOSSARY-MAP.md` (or `CONTEXT.md`/`CONTEXT-MAP.md`),
   `docs/adr/`, `docs/agents/`, `.scratch/`, the monorepo markers of L30 (verbatim, D28).
2. Ask: the tracker, with local markdown worded "(the default; needs no remote or CLI)" and
   "Other"; the domain layout. No question about labels.
3. Confirm drafts, then write exactly three files from the seeds in `references/`:
   `docs/agents/issue-tracker.md` (the local seed, or the user's "Other" answers filling the same
   sections), `docs/agents/triage-labels.md` (always, with the five default roles; triage is
   dropped but to-spec and to-tickets still use the vocabulary; the "Label in mattpocock/skills"
   column header stays verbatim) and `docs/agents/domain.md`.
4. Never read `CLAUDE.md`/`AGENTS.md` in order to edit them, never edit or create them. If an
   old "## Agent skills" block exists, tell the user it is superseded by the plugin always rule
   and that they may delete it.

**The local tracker (D16), in `references/issue-tracker-local.md`.** Sections: publish, fetch,
close, blocking (a plain "Blocked by" line by default) and "Wayfinding operations" (heading
verbatim, lead-in with plain skill names). "Closed" means any terminal `Status:`: `resolved`
(answered or done) or `out-of-scope` (wayfinder's rule-out); a ticket is unblocked when every
blocker is closed; an implementation ticket is set `resolved` when merged, by rewriting
to-tickets' bold `**Status:**` line in place. Every map and ticket file opens with a `# <title>`
heading. Research subagents write only their own ticket file, and a single session appends to
`map.md`. `.scratch/` is untracked working state, never staged in a commit; a skill that hands a
ticket or map pointer to a subagent or a worktree passes an absolute path into the main checkout,
because worktrees do not contain untracked files.

| Concern | Where it lives | Ticket |
| --- | --- | --- |
| Tracker description | consumer `docs/agents/issue-tracker.md`, from `references/issue-tracker-local.md` or "Other" | T03 |
| Label vocabulary | consumer `docs/agents/triage-labels.md`, from `references/triage-labels.md` | T03 |
| Domain layout | consumer `docs/agents/domain.md`, from `references/domain.md` (D21 fallback) | T03 |
| Pointer in always-loaded context | `rules/mattpocock-skills-tracker.md` | T03 |
| `.scratch/` handling, absolute paths, closing on merge | `references/issue-tracker-local.md` (setup's seed, copied to `docs/agents/issue-tracker.md`) and the plugin always rule; wayfinder, implement-spec and implement read it through the tracker doc | T03 |
| Gitignore advice | plugin `README.md` | T10 |

## 7. Gates (D30-D32)

Every test module under `tests/plugins/mattpocock_skills/` sets `pytestmark = pytest.mark.catalog`,
so pre-commit's `catalog-checks` hook runs it on a commit that touches `catalog/`. Failure messages
name the file, the line, the offending text and the expected shape.

### 7.1 Test files

| File | Ticket | What it asserts |
| --- | --- | --- |
| `test_gates.py` | T01 | G1-G22 below, parametrised over the skills and files present |
| `test_budget.py` | T01 | section 7.5 |
| `test_sync.py` | T01 | `playbook init --non-interactive` with the plugin and every skill adapter, then: each present skill's `SKILL.md` parses to the source frontmatter and its body is the sentinel prefix plus the source body; `references/` and `scripts/` are byte copies, scripts executable; the three native roots hold the same bytes; Continue's prompt ends with the source body; `playbook validate` and `playbook sync --check` pass; every lockfile entry of a plugin skill has `kind = "skill"` and the plugin as `source`; init without the overlay writes none of the ids |
| `test_grilling.py` | T02 | A.T02's texts: D18.1 two separate loads in grill-with-docs; D18.2 background-only fact-finding in grilling; grill-me's load of grilling; D21 in domain-modeling's two files; the moved references |
| `test_tracker.py` | T03 | A.T03's texts: the three files setup writes and nothing else; no forge CLI and no GitHub or GitLab seed; `triage-labels.md` written without a question; the stale-block report; the local seed's sections and D16 rules; the plugin always rule (section 5.5 constraints, rendered into `AGENTS.md` and the Claude rules file when the plugin is on, a `.continue/rules/` file when `continue` is listed, absent when the plugin is off) |
| `test_flow.py` | T04 | A.T04's texts: D18.4, D18.5 (draft-PR hedge, sequential stop-and-resume), the research, throwaway-prototype, grilling, domain-modeling, two-axis-review and tdd loads, and the tracker lines kept verbatim (D16's rules are asserted on T03's seed by `test_tracker.py`) |
| `test_review.py` | T05 | A.T05's texts: D18.6, the "GitLab `!67`" example, the 419-character description verbatim (D28), pr-body's credits, licence file and remaining `metadata` keys, tdd's load of codebase-design, D27 examples verbatim |
| `test_architecture.py` | T06 | A.T06's texts: the report spec has no CDN, no Tailwind class names, no Mermaid, no `xmlns`, one inline `<style>`, inline SVG; D20 phrasing; design-it-twice's fallback keeps independent briefs; throwaway-prototype keeps LOGIC.md L54 verbatim and the `/prototype/<name>` route |
| `test_debug_wizard.py` | T07 | A.T07's texts and the two scripts' behaviour, always run with `sys.executable -B`: the HITL loop with `stdin=subprocess.DEVNULL` exits non-zero with the message asking for `python3 <copy>` in the user's terminal; the wizard without a TTY exits 2 with its run-it-in-your-terminal message, and with a TTY, end of file mid-run ends with status 0; `open_url` prints a scheme-less argument; the `.env` upsert is atomic; `set_secret`/`set_var` keep their names; wizard's SKILL reads only `.env.example`, `.env.sample`, `.env.template`, `.env.dist` and the CI config |
| `test_session.py` | T08 | A.T08's texts: D18.3 nesting guard, D25, D24 (`{link}` placeholder, workspace clause), D26 (the clause names the sentinel by its first word, taken from `coding_agent_playbook._sentinel.SENTINEL`, never copied), D28 sibling-file advice verbatim |
| `test_router.py` | T09 | A.T09's texts: every route names a final id (presence is T10's, section 7.8); no route to triage; "start a fresh context" for `/clear` and `/compact`; `/name` labels kept; the description verbatim (D28) |
| `test_inventory.py` | T10 | section 7.8 |

The file names in this table are canonical, and each file belongs to one ticket. Where an
appendix part names another test file (for example a shared `test_glossary_fallback.py`,
`test_skill_loads.py` or `test_execution_skill_loads.py`, or `test_tracker_rule.py`), the lane puts
those assertions in its own file above. The cross-skill checks such shared files would hold are
already in T01's gate (G14 for load targets, G15 for the guard line, G16 for the D21 fallback), so
no two lanes edit one test file. A test that needs a repo synced with the plugin uses the
`conftest.py` fixture; one that needs the plugin off builds its own probe in `tmp_path`, as
`test_pack.py:387-391` does.

The shared gate, `test_gates.py`, parametrised over `present_skill_ids()` (the directories under
`skills/`, asserted non-empty at collection, as `test_pack.py:103-104` does) and over the files
present:

- **G1.** The plugin is a usable bundled plugin (`test_pack.py:120-122`) and adds no prompts,
  hooks or eval tasks; its only rules are under `rules/`.
- **G2.** The plugin root holds only `LICENSE`, `ATTRIBUTIONS.md`, `README.md`, `skills/` and
  `rules/`; `rules/` holds only `mattpocock-skills-tracker.md` when present.
- **G3.** No URL in any file of the plugin, root files and scripts included, read as bytes: the
  union of the generic `_URL_RE` (`test_resources_self_contained.py:92-98`) and the superpowers
  `_URL_RE` (`tests/plugins/test_superpowers_self_contained.py:40`).
- **G4.** No unambiguous imposed-tool name in `skills/` or `rules/` (section 7.2).
- **G5.** No ambiguous word in command position (section 7.3).
- **G6.** No `.sh` or `.bash` file anywhere in the plugin; no first-line shebang other than
  `#!/usr/bin/env python3`, and that one only in `scripts/*.py`.
- **G7.** No Claude-only name in `skills/` or `rules/`: `Skill tool`, `Task tool`,
  `AskUserQuestion`, `TodoWrite`, `/clear`, `/compact` (the slash names matched with
  `(?<![\w/])` before and `\b` after). The root files are exempt.
- **G8.** No coupling marker in `skills/` or `rules/`: `CLAUDE_PLUGIN_ROOT`, `.claude-plugin`,
  `claude plugin install`, `/plugin install`, `npx skills`, `skills.sh`, `mattpocock-skills:`.
  triage-labels.md's "Label in mattpocock/skills" header is not a marker.
- **G9.** Each skill directory holds only `SKILL.md`, `scripts/`, `references/`
  (`test_pack.py:147-153`, with `SYNCED_SKILL_ENTRIES` from
  `tests/plugins/superpowers_expectations.py:138`); `references/` holds only `.md` files and the
  licence files.
- **G10.** `LICENSE` has the pinned digest; every `references/LICENSE` equals it byte for byte.
- **G11.** The first frontmatter line is `id: <dir>`; `id == name == <dir>`; the id matches
  `^[a-z0-9]+(-[a-z0-9]+)*$` and is at most 64 characters; the description is 1-1,024 characters.
- **G12.** No `playbook` key; no `.j2` file anywhere in the plugin.
- **G13.** Every `references/…` or `scripts/…` path mentioned in a `SKILL.md` or reference file
  resolves inside the same skill or, with a `../<id>/` prefix, in a sibling skill present in the
  plugin (the superpowers `_PATH_MENTION_RE`, `test_superpowers_self_contained.py:50-53`);
  unresolved mentions only through the allowlist (section 7.4).
- **G14.** Every operative load, matched by the regex
  `` [Ll]oad(?:s|ing)? the `([a-z0-9]+(?:-[a-z0-9]+)*)` skill `` (so "load", "loads" and
  "loading" all count), names one of the 11 model-invoked final ids
  (`FINAL_IDS - USER_INVOKED_IDS`); the target need not be present yet (T10 checks presence,
  section 7.8). This one regex is used by every load-target test, in the shared gate and in the
  lanes.
- **G15.** The D19 guard (section 7.6).
- **G16.** D21: every shipped file that names `GLOSSARY.md` also names `CONTEXT.md`, and every
  one that names `GLOSSARY-MAP.md` also names `CONTEXT-MAP.md`.
- **G17.** `allowlist/` holds exactly one `<id>.txt` per present skill, each parsing to entries of
  section 7.4.
- **G18.** The allowlist two-way check (section 7.4).
- **G19.** Scripts (section 7.7).
- **G20.** `pyproject.toml`'s `[tool.ruff] extend-exclude` contains
  `catalog/plugins/mattpocock_skills/**/*.md` and `force-exclude` is true, and no glob there
  excludes the plugin's `.py` files (the shape of `test_ruff_scope.py:83-89`, in our file).
- **G21.** `check_markdown_links` over the plugin layer returns no error
  (`test_pack.py:355-360`).
- **G22.** `ATTRIBUTIONS.md` has the 16 global headings in order, then `## Per-skill changes`
  with one `### <id>` per final id in alphabetical order; the section of every present skill no
  longer holds its placeholder; the section of every absent skill still does.

### 7.2 Shared constants and scanners (`_expectations.py`, T01)

```python
PLUGIN_NAME: Final = "coding_agent_playbook.plugins.mattpocock_skills"
PLUGIN_ROOT: Final = plugin_root("mattpocock_skills")  # tests/_catalog.py
SKILLS_ROOT, RULES_ROOT, ALLOWLIST_DIR  # Paths under the roots above
LICENSE_SHA256: Final = "0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5"
FINAL_IDS: Final[frozenset[str]]  # the 26 D9 ids: targets of loads and labels, not an inventory pin
USER_INVOKED_IDS: Final[frozenset[str]]  # the 15 D19 ids
GUARD_LINE: Final = "Run this only when the user asked for it by name; otherwise stop."
TICKET_OF: Final[Mapping[str, str]]  # final id -> "T01".."T09", for the placeholders
ATTRIBUTIONS_GLOBAL_SECTIONS: Final[tuple[str, ...]]  # the 16 headings of section 5.3


def present_skill_ids() -> list[str]: ...
def plugin_files() -> list[Path]: ...  # every file, bytecode caches excluded
def skill_docs(skill_id: str) -> list[Path]: ...  # SKILL.md plus references/**/*.md
def split_skill(skill_id: str) -> tuple[dict[str, object], str]: ...
def imposed_tool_hits(path: Path) -> list[Hit]: ...  # G4
def command_position_hits(path: Path) -> list[Hit]: ...  # G5, section 7.3
def load_allowlist(skill_id: str) -> list[AllowEntry]: ...
```

`Hit` carries the path relative to the skill directory, the 1-based line, the matched text and
its column span, and the line. The 15 user-invoked ids are ask-matt, grill-me, grill-with-docs,
handoff, implement, implement-spec, improve-codebase-architecture, retro,
setup-matt-pocock-skills, teach, to-questionnaire, to-spec, to-tickets, wait-what, wayfinder.

**Unambiguous names (G4).** Case-insensitive, anywhere in a file under `skills/` or `rules/`:
`gh`, `glab`, `jq`, `tput`, `curl`, `wget`, `xdg-open`, `wslview`, `explorer.exe`, `shellcheck`,
`npx`, `npm`, `yarn`, `deno`, `puppeteer`, each bounded by `(?<![\w.-])` and `(?![\w-])` (so
"GitHub", "high" or `gh-pages` never match); the CDN host names `jsdelivr`, `unpkg` and `cdnjs` as
plain substrings; and the phrase "via CDN".

### 7.3 Command position

The ambiguous words are `open`, `start`, `bash`, `sh`, `node`, `bun` and `pnpm`. They are legal in
prose ("open the file", "start the dev server") and denied only where they would be run.

For markdown (every `SKILL.md`, reference and rule file):

1. Split the file into fenced blocks and the rest with the fence rule of `links.py:177-189`: a
   line whose left-stripped text starts with three backticks or three tildes opens a block, and
   a line starting with the same three characters closes it. Any info string counts.
2. The command segments are: each line inside a fenced block; the content of each inline code
   span outside fences (the `_CODE_SPAN_RE` of `links.py:60`); and the rest of each prose line
   whose left-stripped text starts with `$ ` (a shell prompt).
3. Split each segment on `&&`, `||`, `;`, `|` and `$(`.
4. In each piece, split on whitespace, drop leading environment assignments
   (`^[A-Za-z_][A-Za-z0-9_]*=`) and one leading prompt word (`$`, `>` or `%`). The first word left
   is in command position.
5. A hit is that word equal, exactly and case-sensitively, to an ambiguous word. `open(path)`,
   `pnpm-workspace.yaml` or `start:` are not equal, so they never hit.

For `scripts/*.py`, parse with `ast` and take, as command words, the first element of a list or
tuple literal passed as the first positional argument (or `args=`) to
`subprocess.run`/`call`/`check_call`/`check_output`/`Popen` or an `os.exec*` function, and the
first whitespace-separated word of a string literal passed to `os.system`, `os.popen` or a
`subprocess` call with `shell=True`. The rewrites use `webbrowser`, so none is expected.

Run over the v1.3.1 text of the 26 skills, this definition flags exactly five words, all
intended: improve-codebase-architecture SKILL.md L39 `open <path>` and `start <path>` (removed by
D23 and D20), prototype SKILL.md L22 `pnpm <name>` and `bun <path>` (project toolchain,
allowlisted by T06), and wizard SKILL.md L41 `bash -n <script>` (replaced by D22). No line of
any upstream fenced block (typescript, ts, tsx, md, markdown, text, diff, html, mermaid and
unlabelled fences) produces a hit.

### 7.4 Per-file allowlist

`tests/plugins/mattpocock_skills/allowlist/<id>.txt`, one file per final id, owned by the ticket
of that skill; T01 creates `to-questionnaire.txt` and `wait-what.txt`. UTF-8, one entry per line:

```text
# throwaway-prototype: project toolchain named as examples (D2, D27)
SKILL.md: `pnpm <name>`
SKILL.md: `bun <path>`
```

- The part before the first `": "` is a path relative to `skills/<id>/`; the rest, with trailing
  whitespace stripped, is an exact excerpt of one line of that file. Blank lines and lines
  starting with `#` are ignored; a comment says why the entries are legitimate.
- An entry covers a hit when the hit's line contains the excerpt and the hit's matched span lies
  inside an occurrence of the excerpt on that line. Line numbers are never used, so an edit
  elsewhere in the file keeps the entry valid.
- Only two scanners consult it: the imposed-tool scanners (G4, G5) and unresolved path mentions
  (G13). URLs, Claude-only names, coupling markers, layout, licences, the guard line and scripts'
  shebangs have no allowlist.
- **Two-way check (G18).** Every hit must be covered by an entry (else the failure lists
  `skills/<id>/<path>:<line>: <token>`), and every entry must cover at least one hit (else it is
  a stale entry and fails with its file and text). Expected entries are few: the two above, plus
  whatever a lane keeps as project toolchain and records in its skill's `ATTRIBUTIONS.md`
  section.

### 7.5 Listing budget test (`test_budget.py`, T01)

The test measures what the engine itself would list, per layer, with the engine's own functions
(E13), so it works today, when core ships no skills, and after ticket 10, when core ships four
rule skills whose descriptions are composed at sync.

```python
LISTING_BUDGET_CHARS: Final = 6_000  # prS D5, as amended by D31: core plus EACH bundled plugin


def listing_chars(plugin: str, repo_root: Path) -> dict[str, int]:
    """Emitted description length per skill id for core plus ``plugin``, every member rule active.

    Example: ``sum(listing_chars(PLUGIN_NAME, tmp_path).values())`` -> about 3,734 today.
    """
    source = FileSystemArtifactSource(repo_root=repo_root, overlay_packages=[plugin])
    resolver = OverlayResolver()
    skills = resolver.resolve_skills(
        _of_layer(source.list_skills(), ENGINE_PACKAGE),
        [_of_layer(source.list_skills(), plugin)],
        [],
    )
    rules = resolver.resolve_rules(
        _of_layer(source.list_rules(), ENGINE_PACKAGE), [_of_layer(source.list_rules(), plugin)], []
    )
    composed = compose_skills(skills, rules, rules)  # all members active: the longest descriptions
    return {skill_id_of(s): len(str(emitted_frontmatter(s)["description"])) for s in composed}


@pytest.mark.parametrize("plugin", bundled_plugins())
def test_core_plus_each_bundled_plugin_listing_within_6000_chars(
    plugin: str, tmp_path: Path
) -> None:
    chars = listing_chars(plugin, tmp_path)
    assert sum(chars.values()) <= LISTING_BUDGET_CHARS, sorted(chars.items(), key=lambda kv: -kv[1])
```

- `_of_layer(items, label)` keeps the artifacts whose `source_package` is `label`;
  `ENGINE_PACKAGE` comes from `coding_agent_playbook._layers`; `bundled_plugins()` from
  `coding_agent_playbook.catalog` (`catalog.py:96`). `tmp_path` as the repo root means no
  repo-local layer.
- Passing every rule as both merged and active makes `compose_skills` attach every member, so a
  core rule skill is measured at the longest description sync can emit for it (at most 300
  characters by construction, `skill_document.py:32`); a rule skill without any member is dropped,
  as sync drops it. A plain skill (every plugin skill, and `playbook-guardrails` after PR 4)
  counts its authored description (`emitted_frontmatter` returns it unchanged).
- Today `layer_roots("skills")` has no core entry, so the core share is 0 and the test measures
  the plugin alone. After #50, core's four skills are counted with no edit here.
- A third test, `test_budget_counts_every_core_skill` (added at T10b, once #72 shipped
  `catalog/core/skills/`), asserts that every core skill id is among the measured ids, so the sum
  is core plus the plugin and never the plugin alone. At T10b the core share is 762 characters
  (python-coding 226, python-tooling 197, ml-data 194, python-testing 145).
- A second test, `test_budget_counts_every_present_plugin_skill`, asserts that the ids measured
  for `PLUGIN_NAME` are exactly `present_skill_ids()`, so the budget can never pass by counting
  nothing.
- Parametrising over every bundled plugin implements D31's "each"; superpowers (2,285) and
  python_design (1,113) are far under the limit (3,047 and 1,875 with core at T10b).
- If tickets 7-10 change the signatures of `compose_skills` or `emitted_frontmatter`, T10 adapts
  this helper when it rebases (section 8).

### 7.6 D19 guard test (G15)

For every present skill: `frontmatter.get("disable-model-invocation") is True` exactly when the
id is in `USER_INVOKED_IDS`. For a user-invoked skill, the first non-blank body line is
`GUARD_LINE`, the line occurs exactly once in `SKILL.md`, and the description does not contain
it. For a model-invoked skill the line is absent. The placement (first non-blank body line, before
any heading or instruction) is fixed here so every lane does the same; after sync the line
follows the sentinel line.

### 7.7 Scripts checks (G19)

Reused from `tests/plugins/python_design/test_pack.py`, with `_SCRIPTS` discovered as the files
under `skills/*/scripts/`:

- the first line is `#!/usr/bin/env python3` and the file is executable
  (`test_script_is_an_executable_python3_program`, `test_pack.py:193-198`);
- `ast.parse(..., feature_version=(3, 10))` succeeds, the module docstring carries a usage line
  with the file name, and every import is in `sys.stdlib_module_names`
  (`test_script_parses_as_310_and_imports_only_stdlib` and `_non_stdlib_imports`,
  `test_pack.py:201-218`);
- `mypy --strict --python-version 3.10` passes from a neutral working directory with an empty
  config and a shared cache (the `mypy_workdir` fixture and
  `test_script_passes_strict_mypy_for_python_310`, `test_pack.py:221-237`);
- the synced copies stay executable (`test_pack.py:304-305`, in `test_sync.py`);
- added here: no script command word is an imposed tool (section 7.3), and a test never imports
  a script in-process (that writes `scripts/__pycache__/` into the catalog); behaviour tests run
  it with `sys.executable -B` and a timeout (`_run_json`, `test_pack.py:374-384`, shows the
  timeout and capture pattern; add `-B`, which it does not pass because it runs synced copies).

The scripts are under ruff (D32; py310 target, `pyproject.toml:155`), so CI's `ruff check .` and
`ruff format --check .` cover them.

### 7.8 Inventory pin (`test_inventory.py`, T10 only)

Earlier tickets parametrise over the skills present; only T10 pins the whole:

- `present_skill_ids() == sorted(FINAL_IDS)` (the 26 D9 ids);
- the scripts are exactly `diagnosing-bugs/scripts/hitl_loop_template.py` and
  `wizard/scripts/wizard_template.py`; `rules/` is exactly `mattpocock-skills-tracker.md`; the
  plugin root is exactly the five entries of G2;
- the skills whose frontmatter sets `disable-model-invocation: true` are exactly
  `USER_INVOKED_IDS`;
- no `_Filled by` placeholder remains anywhere in the plugin (`ATTRIBUTIONS.md` and `README.md`
  included);
- every code span that is exactly `` `/<word>` `` in a file under `skills/` or `rules/` names a
  final id (so no `/code-review`, `/pr`, `/prototype` or `/triage` label survives), except the
  two non-label spans kept verbatim from upstream: `/tmp` in
  `improve-codebase-architecture/SKILL.md` and `/settings` in
  `throwaway-prototype/references/UI.md`. The exemption set is checked both ways (each pair must
  still occur). The root files are out of scope, because `ATTRIBUTIONS.md` and the README quote
  the old labels they record;
- every G14 load target, every ask-matt router label (A.T09 test 1) and every `../<id>/` path
  names a present skill;
- the README names each of the 15 user-invoked ids, `.scratch/` and the five superpowers pairs.

### 7.9 Existing gates that cover the plugin with no edit

| Gate | What it checks for this plugin |
| --- | --- |
| `tests/integration/test_resources_self_contained.py` | every file: URLs (bare domain plus path included) and the generic markers (E9) |
| `tests/integration/test_catalog_layout.py:98-102`, `:146-157` | the leaf rule for `mattpocock_skills`, at least one kind directory, no link to a plugin-root file |
| `tests/cli/test_validate_links.py:252` | link self-containment with every bundled plugin enabled |
| `tests/integration/test_ruff_scope.py:83-89` | the existing globs stay (`in` checks; unaffected) |

## 8. Sequencing and landing (D36-D38)

### 8.1 External dependencies and what we do not touch

| File or area | Why it is off limits | Free after |
| --- | --- | --- |
| `src/coding_agent_playbook/adapters/_skill_writer.py`, the adapters, validate code (`commands/validate.py`, `commands/_validate_*.py`) | skills-first tickets 7-12 (#47-#52) rewrite them | #50 and #53 on main; any engine change this plugin needs is a separate small PR |
| `tests/integration/test_resources_self_contained.py` | D30: the generic scan already covers the plugin | never edited by this work |
| `tests/integration/test_context_budget.py`, `tests/integration/conftest.py`, `tests/_budget_probe.py` | created by ticket 10 (#50) | #50 on main; only a separate small PR may touch them (section 8.2) |
| `SPEC.md`, `README.md`, `MIGRATION.md`, `catalog/README.md` | ticket 13 (#53) rewrites them | #53 on main; then PR B (`catalog/README.md` needs no change: its plugin text is generic) |

`CONTEXT.md` and `pyproject.toml` are shared with the other session: our edits are one appended
section and one inserted line, rebased by hand if they conflict.

### 8.2 PR A and PR B

**PR A**, suggested title `feat(catalog): add the mattpocock_skills bundled plugin`: everything
T01-T10 produce (`catalog/plugins/mattpocock_skills/**`, `tests/plugins/mattpocock_skills/**`,
the `pyproject.toml` line, the `CONTEXT.md` section, this spec). It merges only once ticket 10
(#50) is on main. Before merging, T10 rebases the integration branch on main and re-runs the full
gate, so `test_budget.py` counts the four core skills; and it reads #50's reference probe. If the
probe names superpowers and python_design explicitly (prS section 6.8.10), nothing more is
needed. If it enumerates `bundled_plugins()`, enabling this plugin there would break prS's budget
tests (the probe's 4,160 characters after #50 plus this plugin's 3,734 is 7,894, over 6,000, and
the plugin always rule would push the always rules past the 800-word cap, which ticket 10 measures
at about 769), so a separate small PR first pins the probe to the two plugins (D31), and PR A
rebases on it.

**PR B**, suggested title `docs(plugins): document the mattpocock_skills bundled plugin`: D35,
after ticket 13 (#53), rebased late:

- SPEC §11.5.3 "The `mattpocock_skills` bundled plugin", after §11.5.2 (`SPEC.md:2143`) and
  before §11.6 (`SPEC.md:2163`), mirroring §11.5.1: source and pin, the 26 ids and the 3
  renames, the edits (sections 5.3 items 3-11), dropped and why, third-party content,
  consumer-repo conventions, rendering per adapter, attribution, gates. It also states that this
  plugin ships one rule, which §11.5 allows (its kind directories include `rules/`) and §11.5.1's
  "skills only" wording does not cover, and the D31 amendment in §11.5 and §16.
- README's "## Bundled plugins: superpowers, python_design" section (`README.md:400`) gains the
  plugin and its heading names all three.
- A MIGRATION entry in the current release section (`## v0.21`, `MIGRATION.md:15`, or the
  release section open at that time): opt in, run setup, gitignore `.scratch/`, disable the
  upstream Claude Code plugin.
- A SPEC changelog bullet in the open version's appendix entry.

If #53 has merged by the time PR A is ready, T11 runs before PR A opens and both land as one PR
(D36).

### 8.3 Lanes and merge hotspots

```text
main (a9e48e5) ─ integration branch claude/skills-plugin-self-contained-13b88a
    T01 foundation (alone, first)
    ├─ T02 ┐
    ├─ T03 │
    ├─ T04 │  parallel lanes: one worktree branch each, cut from the integration branch
    ├─ T05 │  after T01; merged back one at a time, the full gate re-run after each merge
    ├─ T06 │
    ├─ T07 │
    ├─ T08 │
    └─ T09 ┘
    T10 integration ─ rebase on main once #50 has merged ─ PR A
    T11 docs, once #53 has merged ─ PR B (or folded into PR A, D36)
```

Hotspots inside the branch, and how each is kept conflict-free:

- `ATTRIBUTIONS.md`: pre-created per-skill sections; a lane replaces only its placeholder lines
  (section 5.3); global sections belong to T01, then T10.
- `README.md`: T01 skeleton, T10 final text; no lane touches it.
- `_expectations.py` and `conftest.py`: T01 only. A lane that needs another helper writes it in
  its own test file.
- `allowlist/`: one file per id, owned by the lane of that id.
- Cross-skill text: loads and labels name final ids from the start (D9 fixes them), so lanes do
  not wait for each other and merge in any order, T09 included; G14 checks load targets and
  A.T09 test 1 checks router labels against `FINAL_IDS`, and T10 checks presence (section 7.8).
- `pyproject.toml`: T01 only.

Against main: `CONTEXT.md` and `pyproject.toml` (section 8.1), and any engine signature that
`test_budget.py` imports (section 7.5).

### 8.4 CI facts and the local gate

- Every commit on the branch and every PR title is a Conventional Commit: CI's commit-convention
  job runs `cz check` on each commit since `origin/main` and on the PR title
  (`.github/workflows/ci.yml:90`, `playbook ci --steps commit-convention --base origin/main`).
  Lane commits look like `feat(catalog): vendor the grilling skills into mattpocock_skills`.
  Commits are authored by the user only: no `Co-Authored-By` trailer, no `--author` (D38).
- CI runs only for PRs into `main`; retargeting a PR or editing its title does not start it. The
  squash merge is titled `Title (#N)` and happens after green CI (D38).
- The test job runs on Python 3.12 and 3.13 (`ci.yml:20`): `ruff check .` (`:33`),
  `ruff format --check .` (`:36`), `mypy` (`:39`), `pytest -q` (`:42`), from the repository root,
  with no path arguments. CI installs an unpinned ruff, which also formats fenced Python inside
  every tracked markdown file, `specs/` included, so this spec's Python blocks are kept
  ruff-format clean (checked with ruff 0.15.10 `--preview`, line length 100).
- Locally, before claiming green, the same gate, cache-free, in an environment without optional
  extras, on Python 3.12 as well as the dev Python:

```text
uv run python -m ruff check --no-cache .
uv run python -m ruff format --check --no-cache .
uv run python -m mypy --cache-dir=/dev/null
uv run python -m pytest -q -p no:cacheprovider
```

- The wheel-smoke job builds the sdist and a wheel from it; `catalog/` ships through hatch's
  force-include (`pyproject.toml:120-122`), so the new plugin and its executable bits ship with no
  packaging change.

## 9. Tickets

### 9.1 Table

| Ticket | Title | Blocked by | Owns (files) | Model / effort |
| --- | --- | --- | --- | --- |
| T01 | feat(catalog): add the mattpocock_skills plugin skeleton, gates and two tracer skills | none | plugin `LICENSE`, `ATTRIBUTIONS.md` (whole file at creation; then global sections and two skill sections), `README.md` skeleton, `skills/to-questionnaire/`, `skills/wait-what/`; `pyproject.toml` line; `tests/plugins/mattpocock_skills/{__init__,conftest,_expectations,test_gates,test_budget,test_sync}.py`, `allowlist/{to-questionnaire,wait-what}.txt`; `CONTEXT.md` section; `specs/prT-mattpocock-skills.md` | Opus 5.5 / high |
| T02 | feat(catalog): vendor the grilling and domain-modeling skills | T01 | `skills/{grilling,grill-me,grill-with-docs,domain-modeling}/`, their `ATTRIBUTIONS.md` sections, `test_grilling.py`, their allowlist files | Sonnet 5.5 / max |
| T03 | feat(catalog): vendor setup, to-spec and to-tickets with the plugin always rule | T01 | `skills/{setup-matt-pocock-skills,to-spec,to-tickets}/`, `rules/mattpocock-skills-tracker.md`, their sections, `test_tracker.py`, their allowlist files | Opus 5.5 / high |
| T04 | feat(catalog): vendor wayfinder, implement-spec and implement | T01 | `skills/{wayfinder,implement-spec,implement}/`, their sections, `test_flow.py`, their allowlist files | Opus 5.5 / high |
| T05 | feat(catalog): vendor two-axis-review, pr-body and tdd | T01 | `skills/{two-axis-review,pr-body,tdd}/`, their sections, `test_review.py`, their allowlist files | Opus 5.5 / medium |
| T06 | feat(catalog): vendor the architecture and prototype skills | T01 | `skills/{improve-codebase-architecture,codebase-design,throwaway-prototype}/`, their sections, `test_architecture.py`, their allowlist files | Opus 5.5 / xhigh |
| T07 | feat(catalog): vendor diagnosing-bugs and wizard with Python scripts | T01 | `skills/{diagnosing-bugs,wizard}/` (scripts included), their sections, `test_debug_wizard.py`, their allowlist files | Opus 5.5 / high |
| T08 | feat(catalog): vendor research, retro, handoff, teach and writing-for-agents | T01 | `skills/{research,retro,handoff,teach,writing-for-agents}/`, their sections, `test_session.py`, their allowlist files | Sonnet 5.5 / max |
| T09 | feat(catalog): vendor the ask-matt router | T01 | `skills/ask-matt/`, its section, `test_router.py`, `allowlist/ask-matt.txt` | Opus 5.5 / medium |
| T10 | test(catalog): pin the mattpocock_skills inventory and finish its docs | T02-T09 | `test_inventory.py`, plugin `README.md` (final), `ATTRIBUTIONS.md` global sections (reconciliation only), `test_budget.py` (only if a rebase changes an engine signature), PR A | Opus 5.5 / high |
| T11 | docs(plugins): document the mattpocock_skills bundled plugin | T10, external ticket 13 (#53) | `SPEC.md` (§11.5.3, §11.5, §16, changelog), root `README.md` section, `MIGRATION.md` entry, PR B | Opus 5.5 / medium |

Every lane T02-T09 reads its part of the appendix, works only in the files it owns, keeps
Matt's text verbatim outside the listed changes, and ends with the full gate green on the
integration branch after its merge. Common acceptance for T02-T09: G1-G22 pass with its skills
present; its `ATTRIBUTIONS.md` sections list every change with file, upstream line and decision,
plus the skill's Continue degradation; its allowlist files have a comment per entry and no stale
entry; its test file asserts each new text of its appendix part as an exact substring and the
absence of each replaced upstream text.

### 9.2 T01 - foundation and tracer bullet

Creates the plugin and the whole gate, and proves it on two layout-only, user-invoked skills
before any lane starts. `to-questionnaire` gets `id`, the guard line and its licence copy;
`wait-what` also gets D21 (it names `GLOSSARY.md` and `GLOSSARY-MAP.md`), so G15 and G16 are
exercised on real text.

Acceptance:

- `catalog/plugins/mattpocock_skills/` holds `LICENSE` (pinned digest), `ATTRIBUTIONS.md` with the
  16 global sections written in full (section 5.3) and 26 per-skill sections, those of
  to-questionnaire and wait-what filled and the other 24 holding `_Filled by T0x._` with the
  ticket of section 5.3, `README.md` skeleton (section 5.4), and the two skills.
- `pyproject.toml` excludes `catalog/plugins/mattpocock_skills/**/*.md` from ruff; `ruff format
  --check .` leaves the vendored markdown alone.
- `tests/plugins/mattpocock_skills/` holds the files of section 4.3 owned by T01; every test
  parametrises over what is present; `_expectations.py` exposes the API of section 7.2.
- `test_sync.py` passes with the plugin enabled through `playbook init --non-interactive
  --overlays coding_agent_playbook.plugins.mattpocock_skills` in process (the `_init_probe` and
  `opted_in_repo` pattern, `test_pack.py:243-273`, under `apply_hermetic_git_env`,
  `tests/conftest.py:134`), adapters `continue,claude_code,opencode,shared_skills`
  (`superpowers_expectations.py:155`).
- `test_budget.py` passes today (core 0) and prints the per-id breakdown on failure.
- The generic gates of section 7.9 pass with the new directory.
- `specs/prT-mattpocock-skills.md` and the three `CONTEXT.md` terms are committed; the spec's
  fenced Python is ruff-format clean.
- The full CI gate passes on Python 3.12 and 3.13.

### 9.3 T02 - grilling, grill-me, grill-with-docs, domain-modeling (A.T02)

Acceptance: grill-me loads grilling by one "Load the `x` skill" clause; grill-with-docs loads
grilling and domain-modeling in one sentence with two load clauses and no order implied ("Load the
`grilling` skill, and load the `domain-modeling` skill", D18.1); grilling delegates
fact-finding only to a background agent and otherwise looks the fact up before sending the round,
with "Don't block on it" kept only on the background path (D18.2); domain-modeling's `SKILL.md`
and `references/GLOSSARY-FORMAT.md` carry the D21 fallback, and its two format files moved under
`references/` with links rewritten; the two user-invoked skills carry the guard line; no "Skill
tool" text remains; `test_grilling.py` and the common acceptance pass.

### 9.4 T03 - setup-matt-pocock-skills, to-spec, to-tickets, the plugin always rule (A.T03)

Acceptance: setup follows section 6 exactly (writes only the three `docs/agents/` files, local
markdown default with "(the default; needs no remote or CLI)", the "Other" path filling the local
seed's sections, `triage-labels.md` always written with the five default roles and no question,
no read-to-edit, edit or creation of `CLAUDE.md`/`AGENTS.md`, the stale-block report); the GitHub
and GitLab seeds are gone and the three remaining seeds sit in `references/`; the local seed has
the publish, fetch, close and blocking sections and the "Wayfinding operations" heading with the
D16 rules; to-spec's and to-tickets' "tell the user to run `/setup-matt-pocock-skills`" lines keep
the slash (D17); the plugin always rule meets section 5.5 and loads through `Rule.from_markdown`;
with the plugin on, `AGENTS.md` and `.claude/rules/coding-agent-playbook.md` contain its body and,
with `continue` listed, `.continue/rules/` holds its file; with the plugin off, none does;
`test_tracker.py` and the common acceptance pass.

### 9.5 T04 - wayfinder, implement-spec, implement (A.T04)

Acceptance: wayfinder without subagents leaves research tickets on the frontier for a later
session (D18.4) and loads grilling and domain-modeling by two separate loads; implement-spec keeps
"as the issue tracker describes" on the user-requested draft PR, never names a forge CLI, and
without subagents works tickets sequentially with a stop-and-resume point at each merge boundary
(the user starts a fresh context and re-invokes it; it resumes from tickets already merged on the
integration branch) (D18.5); it loads `tdd` and `two-axis-review`; wayfinder, implement-spec and
implement keep their tracker lines verbatim and rely on the T03 seed and the plugin always rule for
D16 (absolute main-checkout paths, `resolved` on merge, `.scratch/` never staged; A.T04 notes);
wayfinder's `prototype` ticket type is unchanged; `test_flow.py` and the common acceptance pass.

### 9.6 T05 - two-axis-review, pr-body, tdd (A.T05)

Acceptance: `code-review` and `pr` are renamed to `two-axis-review` and `pr-body` (directory,
`id`, `name`); two-axis-review without subagents runs Standards first with any fetched spec set
aside, writes it in full, then runs Spec and never revises Standards (D18.6), and keeps the
"GitLab `!67`" example and its 419-character description verbatim (D18.7, D28); pr-body has
`references/CREDITS.md` (link text kept, URLs removed), `references/LICENSE-show-me`, no
`metadata.credits.url` and its other `metadata` keys verbatim (D6); tdd loads `codebase-design`,
its two references moved, its TypeScript and Jest examples verbatim (D27) with allowlist entries
only where a denied word appears; `test_review.py` and the common acceptance pass.

### 9.7 T06 - improve-codebase-architecture, codebase-design, throwaway-prototype (A.T06)

Acceptance: the architecture report is specified as one self-contained HTML file with one inline
`<style>` of semantic classes, hand-built divs and inline SVG for every diagram (the deep module by
SVG fill, leaks as solid red marker arrows), no Tailwind or Mermaid, no CDN, no `xmlns`, and
HTML-REPORT.md's Tailwind class names rewritten as plain CSS descriptions (D23); opening it uses
D20's sentence; codebase-design's design-it-twice fallback keeps independent briefs; `prototype` is
renamed `throwaway-prototype` with `LOGIC.md` and `UI.md` under `references/`, LOGIC.md L54 and
UI.md's `/prototype/<name>` route verbatim, and SKILL.md L22's `pnpm <name>` and `bun <path>`
allowlisted as project toolchain; `test_architecture.py` and the common acceptance pass.

### 9.8 T07 - diagnosing-bugs, wizard (A.T07)

Acceptance: both scripts meet D22 and G19 (python3 shebang, executable, stdlib only, `mypy
--strict` for 3.10, ruff clean); `hitl_loop_template.py` keeps Matt's text, checks
`sys.stdin.isatty()` and catches `EOFError`, exiting with the message asking the agent to have the
user run `python3 <copy>` and paste back the Captured block, without curl or Puppeteer options and
with the localhost example reworded; `wizard_template.py` uses ANSI escapes, `webbrowser` (printing
scheme-less arguments), `getpass`, an atomic `.env` upsert, a non-TTY guard (exit 2), Ctrl-C and
EOF handling and a placeholder for the dashboard URL, and keeps `set_secret` and `set_var` as
guided manual steps; wizard's `SKILL.md` reads only the `.env` templates and the CI config,
verifies with `ast.parse`
(no `__pycache__`), says "run ruff check or mypy if available", makes the script executable with
`os.chmod` or tells the user to run `python3 <script>`, and its description says Python instead
of bash; the loss of WSL opener support is recorded; `test_debug_wizard.py` runs the scripts only
through subprocesses with `-B`; the common acceptance passes.

### 9.9 T08 - research, retro, handoff, teach, writing-for-agents (A.T08)

Acceptance: research gets the nesting guard (an agent already running as a subagent or background
agent does the research itself; upstream issue 530) (D18.3); handoff L10 reads "naming which
skills the next session should use" (D25); teach's RESOURCES-FORMAT.md links keep their markdown
shape with a `{link}` placeholder and L12 says the workspace is the current directory, never the
skill's own directory (D24), and its four format files moved; retro and writing-for-agents carry
the widened D26 clause, and writing-for-agents keeps its sibling-file advice verbatim (D28);
`test_session.py` names the sentinel only through `SENTINEL`; the common acceptance passes.

### 9.10 T09 - ask-matt (A.T09)

Acceptance: every route names a final id (the three renames applied, no route to triage);
`/clear` and `/compact` become "start a fresh context" in `SKILL.md` and
`references/PHASE-BOUNDARIES.md`; router labels keep `/name` (D17); the description is verbatim
(D28); links become plain text; `test_router.py` and the common acceptance pass.

### 9.11 T10 - integration

Acceptance: `test_inventory.py` (section 7.8) passes; the README is final (section 5.4, every D33
item); `ATTRIBUTIONS.md` has no placeholder, its global sections agree with the per-skill
sections, and every change a lane recorded as a global correction is folded in; the integration
branch is rebased on main after #50 merged, the reference-probe check of section 8.2 is done, and
`test_budget.py` passes with core counted (expected about 4,500 characters); the full gate passes
on Python 3.12 and 3.13; PR A is opened with a Conventional title, the budget numbers in its
description, and no trailers.

### 9.12 T11 - docs (PR B)

Blocked by T10 and by the other session's ticket 13 (#53). Acceptance: section 8.2's PR B list is
done; the docs tests pass (`tests/unit/test_docs_*.py`, including the SPEC version pin in
`tests/unit/test_docs_check_rubric_refactor.py`); fenced Python in SPEC and README stays
`ruff format` clean; no URL is added; PR B is rebased on main last and merged after green CI.

## 10. Risks

**Context and budget**

- **R1. Eager tokens of the plugin always rule.** Its at most 60 words reach every session in
  every harness (`AGENTS.md`, the Claude rules file, Continue's rules). Mitigation: the word cap
  is gated; the prS reference probe never enables this plugin (D31), because its always rules sit
  at about 769 of 800 words after ticket 10.
- **R2. Listing headroom.** Core plus this plugin is about 4,974 of 6,000 characters after PR 8.
  Growth in core descriptions shrinks the margin; the test fails loudly and names the longest
  descriptions. Claude Code drops the 15 user-invoked descriptions from its listing, so the test
  over-counts there on purpose.
- **R3. #50's probe may enumerate every bundled plugin** (section 8.2). Detected at T10's rebase
  and fixed by a separate small PR.

**Coexistence and precedence**

- **R4. Overlap with superpowers.** tdd and test-driven-development, diagnosing-bugs and
  systematic-debugging, writing-for-agents and writing-skills, two-axis-review and the code-review
  pair, grilling and brainstorming compete by description when both plugins are on. Only README
  advice (D31, D33); enforcement is deferred.
- **R5. The upstream Claude Code plugin installed alongside.** Its namespaced skills coexist with
  these; an older upstream copy that uses `CONTEXT.md` and this plugin's `GLOSSARY.md` could
  alternate between two glossaries. D21 makes this plugin follow an existing `CONTEXT.md`; the
  README says to disable the upstream plugin where this one is enabled.
- **R6. Personal skills outrank project skills in Claude Code.** A personal skill named `retro`
  or similar shadows this plugin's in that user's sessions. README note (generic, D33).
- **R7. Silent overrides by id.** A repo-local skill or rule, or a later overlay, with the same
  id replaces this plugin's version without a warning (E5); only `playbook render --show-source`
  shows it. The rule id is specific (`mattpocock-skills-tracker`); re-adding triage relies on
  this mechanism on purpose.
- **R8. Feature-gated built-ins.** The renames (D8) cover the Claude Code 2.1.292 names; OpenCode
  and Continue built-in command names were not checked exhaustively, and a later Claude Code
  release may add a colliding bundled name.

**Harness behaviour**

- **R9. `disable-model-invocation` is honoured only by Claude Code.** In OpenCode, Codex, the
  Agent Harness (which moves the key to its sidecar) and Continue the model can start implement
  (which commits), implement-spec, wayfinder or setup by itself. D19's guard line is a soft
  mitigation; F6 must keep the key (section 2.1).
- **R10. Continue degradation (D29).** No `references/`, no scripts, no licence copy, broken
  relative links, loads that load nothing; throwaway-prototype shrinks to its 26-line router.
  Accepted and documented per skill.
- **R11. Frontmatter pass-through.** `argument-hint` (handoff, teach) and `metadata` (pr-body)
  reach native skill files; a stricter validator in another harness may reject them (prS R1-1).
  The re-dump can change frontmatter bytes (E2).

**Tracker and working state**

- **R12. Local tracker with worktrees.** `.scratch/` is absent in worktrees; claims coordinate
  only sessions that share one working tree; concurrent `map.md` appends could clobber each
  other; a "commit your work" step could sweep `.scratch/` into a feature commit. Mitigated by
  D16 (absolute main-checkout paths, one writer of `map.md`), the always rule and the README's
  gitignore advice; not enforced.
- **R13. "Other" trackers.** A former GitHub or GitLab user must write the publish, fetch, close,
  blocking and wayfinding recipe themselves (D14); an agent may still improvise with a forge CLI
  the plugin never names. Residual.
- **R14. Label vocabulary.** Resolved by D14: `triage-labels.md` is always written, so to-spec
  and to-tickets never send users back to setup for it.

**Scripts and fidelity**

- **R15. The Python rewrites behave differently.** No WSL opener; `webbrowser` may start a
  console browser on a headless Linux with `TERM` set; `getpass` and `input()` need a TTY that
  agent shells lack, hence the non-TTY guard; the verify step must not leave `__pycache__` in the
  consumer's `scripts/`, hence `ast.parse`.
- **R16. Research nesting (upstream issue 530).** wayfinder starts research inside a subagent and
  research spawned again, an observed blow-up of about 450k tokens; the D18.3 guard fixes it in
  text only.
- **R17. teach's workspace (upstream issue 377).** A course started from the wrong directory
  would land in a synced, gitignored skill directory; D24's clause and E10 make that visible but
  do not prevent it. teach's workspace `GLOSSARY.md` can collide with domain-modeling's if teach
  runs at a repo root.
- **R18. Secrets.** Kept verbatim, wizard L20 would read `.env` and `.env.*`, which
  secrets-path-guard denies on Claude Code and OpenCode and which elsewhere would pull live
  credentials into context; D22 narrows the reads to the templates and the CI config.
- **R19. Generated files elsewhere.** guard-generated-outputs runs only on Claude Code and
  OpenCode (E11); elsewhere only D26's wording stops a hand edit of a synced file.
- **R20. Stack assumptions.** TypeScript, Jest and JS-frontend examples (D27) and JS-only monorepo
  detection (D28) stay; a Python uv or Cargo workspace is detected as single-context unless the
  user writes `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md`) by hand.

**Gates and process**

- **R21. Denylist false positives and stale entries.** Bare `open`, `start`, `bash` or `node`
  would fail legitimate prose; the command-position rule (section 7.3) flags only the five
  intended upstream words. The two-way allowlist fails on stale entries, so an entry must be
  removed in the same change that removes its token.
- **R22. Ruff formats markdown.** Without D32's exclude, CI or pre-commit would rewrite the
  vendored text. G20 pins the exclude.
- **R23. Router drift.** ask-matt names every other skill; it is written in parallel (T09) against
  the fixed D9 ids, and T10's slash-label check catches a stale route.
- **R24. Re-pin cost.** A later upstream tag means replaying this change list by hand (D5).
  Upstream's house phrasing ("Call the Skill tool") would come back silently without G7.
- **R25. Parallel lanes in one file.** `ATTRIBUTIONS.md` is edited by nine tickets; pre-created
  sections keep the hunks apart (section 5.3), and T10 reconciles.
- **R26. Engine drift under the budget test.** Tickets 7-10 may change `compose_skills` or
  `emitted_frontmatter`; the test then fails at T10's rebase, which owns the fix (section 7.5).
- **R27. Third-party licence.** The audit found the licence of HumanLayer's show-me source
  unknown; D6 settles it as MIT with a recorded commit. If that record proves wrong, pr-body's
  "Summary visuals" menu is the only text to remove.

## 11. Deferred and out of scope

- Upstream `skills/misc/`, `skills/in-progress/` and `skills/deprecated/` (D7).
- `triage`: dropped; a consumer may add it at `playbook/skills/triage/`, and setup still writes
  the label vocabulary it would need (D7, D14).
- A later upstream re-pin: a separate, reviewed PR that diffs v1.3.1 against the new tag and
  replays `ATTRIBUTIONS.md` (D5).
- Enforcing coexistence with superpowers (a conflict or supersedes mechanism, or a validate
  warning when both plugins are enabled): README advice only (D31, D33).
- Making Continue a full target (references, scripts, licence copy for degraded prompts): D29
  accepts the degradation.
- prS F6 (stripping non-standard frontmatter keys), which must keep `disable-model-invocation`
  when it lands (section 2.1).
- WSL opener support in wizard, and a forge integration for "Other" trackers.
- Skill-trigger evals for these skills (prS F3).

## Appendix A. Per-skill changes

Each section below lists one skill. Line numbers are upstream v1.3.1 lines. Each numbered change becomes one bullet in that skill's ATTRIBUTIONS.md section.

### A.T01.1 to-questionnaire (upstream skills/productivity/to-questionnaire; layout-only keep; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/productivity/to-questionnaire/SKILL.md` (54 lines, LF, ends with a newline, UTF-8 with one U+2013 en dash at L16) | `catalog/plugins/mattpocock_skills/skills/to-questionnaire/SKILL.md` | Vendored content. Changes 1 and 2 below are the only edits, so the file grows to 57 lines. Keep every other byte as upstream has it, including the two blank lines L10-L11, the en dash in "steps 1–2" (L16) and the lone `>` answer stub at L47. |
  | `skills/productivity/to-questionnaire/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata (D10). It goes under Dropped in ATTRIBUTIONS (change 4). |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/to-questionnaire/references/LICENSE` | A byte-identical copy of the plugin-root LICENSE (D4), checked by the D30 layout gate. Upstream sha256 is `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5` (change 3). |

  Upstream has no sibling markdown files, no `scripts/` and no `references/` for this skill. The plugin skill directory therefore holds exactly `SKILL.md` and `references/LICENSE`.

- **Frontmatter** (plugin source, in this order):
  1. `id: to-questionnaire`: added as the first key (D11). It equals the directory name and `name`.
  2. `name: to-questionnaire`: verbatim (upstream L2).
  3. `description:`: upstream L3 value verbatim, kept as an unquoted plain scalar (88 characters).
  4. `disable-model-invocation: true`: verbatim (upstream L4). D19 requires it to survive the skills-first spec's F6 non-standard-key stripping.

  Nothing else is added: no `playbook:` block (D11), no `argument-hint`, no `metadata`. Add the `id:` line by text insertion. Do not load and re-dump the YAML.

- **Changes**:
  1. `.agents/skills/to-questionnaire/SKILL.md`, frontmatter, before upstream L2 "name: to-questionnaire". Insert the line `id: to-questionnaire` as the first frontmatter key, so it becomes the new L2. (D11; the plugin-wide "Frontmatter" bullet in ATTRIBUTIONS may cover this.)
  2. `.agents/skills/to-questionnaire/SKILL.md`, body, between upstream L6 (the blank line after the closing `---`) and upstream L7, which starts "Turn something the user can't answer alone". Insert this exact line: `Run this only when the user asked for it by name; otherwise stop.` Follow it with one blank line so that it stays its own paragraph. The skill has no H1, so this line is the first line of body content. The engine's sentinel goes above it at sync and is not written in the source. Result: L7 blank (upstream L6), L8 guard line, L9 blank, L10 = upstream L7. (D19)
  3. `.agents/skills/to-questionnaire/references/LICENSE`: added. It is a byte-identical copy of the plugin-root LICENSE, the upstream MIT notice "Copyright (c) 2026 Matt Pocock". (D4; the plugin-wide "License copies added" bullet may cover this.)
  4. Dropped `skills/productivity/to-questionnaire/agents/openai.yaml`, which upstream uses for interface `display_name: "To Questionnaire"`, a `short_description` and `policy: allow_implicit_invocation: false`. It is not shipped, so Codex (which reads the shared skill root `.agents/skills/`) loses its user-only invocation policy for this skill. What remains is `disable-model-invocation`, which only Claude Code honours, and the change 2 guard line. (D10, D19)

- **Project-toolchain allowlist**: none.

- **Skill-specific tests**: none beyond the shared gate.

- **Continue degradation**: With the `continue` adapter listed, the skill becomes `.continue/prompts/to-questionnaire.md`, which holds only the SKILL.md body (guard line included), with no `references/LICENSE` and no `disable-model-invocation`. Nothing functional is lost, because the body is self-contained and a Continue prompt is always started by the user, which satisfies the guard. Only the license copy does not travel. (D29)

### A.T01.2 wait-what (upstream skills/productivity/wait-what; layout-only keep; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/productivity/wait-what/SKILL.md` (7 lines, ASCII, LF, ends with a newline) | `catalog/plugins/mattpocock_skills/skills/wait-what/SKILL.md` | Vendored content. Changes 1-3 below are the only edits, so the file grows to 10 lines. Every other byte stays as upstream. |
  | `skills/productivity/wait-what/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata (D10). It goes under Dropped in ATTRIBUTIONS (change 5). |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/wait-what/references/LICENSE` | A byte-identical copy of the plugin-root LICENSE (D4), checked by the D30 layout gate (change 4). |

  Upstream has no sibling markdown files, no `scripts/` and no `references/` for this skill. The plugin skill directory therefore holds exactly `SKILL.md` and `references/LICENSE`.

- **Frontmatter** (plugin source, in this order):
  1. `id: wait-what`: added as the first key (D11). It equals the directory name and `name`.
  2. `name: wait-what`: verbatim (upstream L2).
  3. `description:`: upstream L3 value verbatim, including its surrounding double quotes. The value contains ": ", so the quotes are needed. It is 50 characters without the quotes.
  4. `disable-model-invocation: true`: verbatim (upstream L4). It must survive F6 (D19).

  Nothing else is added (no `playbook:` block, D11). Add the `id:` line by text insertion. Do not load and re-dump the YAML.

- **Changes**:
  1. `.agents/skills/wait-what/SKILL.md`, frontmatter, before upstream L2 "name: wait-what". Insert the line `id: wait-what` as the first frontmatter key, so it becomes the new L2. (D11; the plugin-wide "Frontmatter" bullet may cover this.)
  2. `.agents/skills/wait-what/SKILL.md`, body, between upstream L6 (the blank line after the closing `---`) and upstream L7, which starts "Wait, I don't understand where you've got to here." Insert this exact line: `Run this only when the user asked for it by name; otherwise stop.` Follow it with one blank line, so that it stays a paragraph separate from Matt's user-voice sentence. It is the first line of body content, and the engine's sentinel goes above it at sync. Result: L7 blank, L8 guard line, L9 blank, L10 = upstream L7. (D19)
  3. `.agents/skills/wait-what/SKILL.md` L7 (upstream L7, which becomes L10). The glossary fallback goes in at both mentions, as two pure insertions, with nothing else on the line changed:
     - after the code span in "the ubiquitous language from `GLOSSARY.md`", insert ` (or `CONTEXT.md` if the repo already has one)`;
     - after the code span in "(follow `GLOSSARY-MAP.md`", insert ` (or `CONTEXT-MAP.md` if the repo already has one)`.

     The tail of the line then reads: ``from `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) (follow `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) to the right one if the repo has more than one).`` (D21)
  4. `.agents/skills/wait-what/references/LICENSE`: added. It is a byte-identical copy of the plugin-root LICENSE. (D4; the plugin-wide "License copies added" bullet may cover this.)
  5. Dropped `skills/productivity/wait-what/agents/openai.yaml`, which upstream uses for interface `display_name: "Wait What"`, a `short_description` and `policy: allow_implicit_invocation: false`. It is not shipped, so Codex loses its user-only invocation policy for this skill. What remains is `disable-model-invocation`, which only Claude Code honours, and the change 2 guard line. (D10, D19)

- **Project-toolchain allowlist**: none.

- **Skill-specific tests**: none beyond the shared gate.

- **Continue degradation**: With the `continue` adapter listed, the skill becomes `.continue/prompts/wait-what.md`, which holds only the body: the guard line and the user-voice re-pitch sentence. It works as a slash prompt that the user starts, and it still reads `GLOSSARY.md`/`CONTEXT.md` from the repo. Only the `references/LICENSE` copy does not travel, and `disable-model-invocation` does not matter there. (D29)

**Ticket T01 notes.** (1) Order of work. Create the plugin-root `catalog/plugins/mattpocock_skills/LICENSE` first, as a byte copy of the upstream root LICENSE. Copy it (do not retype it) into each skill's `references/LICENSE`. The D32 ruff extend-exclude for `catalog/plugins/mattpocock_skills/**/*.md` should be in place before these files are committed, so that the vendored markdown is never reformatted.

(2) Exact text. The D19 guard sentence must be byte-exact in both skills: ASCII semicolon, a final period, no trailing space, and its own paragraph. The D19 gate looks for exactly this sentence. Make every edit as a text insertion. Upstream bytes stay: the to-questionnaire L10-L11 double blank, the L16 en dash, LF endings and the final newline.

(3) Synced output is not the source. At sync, the SkillWriter forces `name` to the first frontmatter key, keeps `id` after it, re-dumps the YAML (wait-what's description quoting can change in synced copies) and puts the sentinel right after the closing fence. The synced body then shows two blank lines before the guard line: the engine's own blank line plus upstream L6. This is expected. Run the D30 checks "id is the first key" and "guard line present" on the plugin source.

(4) D21 form. This appendix applies the D21 wording literally, as insertions, and code-formats the fallback names wherever upstream code-formats `GLOSSARY.md`. The "MAP equivalent" is `CONTEXT-MAP.md`: upstream's CHANGELOG records the rename from `CONTEXT.md`/`CONTEXT-MAP.md` to `GLOSSARY.md`/`GLOSSARY-MAP.md`. The other tickets' D21 files should use the same parenthetical, so that one grep for "if the repo already has one" finds every mention. G16 in test_gates.py checks the D21 fallback at file level; the per-line form is reviewed by hand.

(5) D30 gate cases. Neither skill has a denylist, Claude-only-name or coupling-marker hit, and neither needs an allowlist entry. Because T01 builds the gate on these two skills first, two kinds of text must not be flagged:
- `GLOSSARY.md`, `CONTEXT.md`, `CONTEXT-MAP.md` and `to-questionnaire-<slug>.md` look like bare domains (`.md` is a TLD), but no path follows them, so the "bare domain + path" URL rule must not fire on them.
- to-questionnaire's template (L22-L54) sits inside `<questionnaire-template>`/`<question-example>` tags, not in a fenced block. Its L47 is a lone `>` answer stub with no word after it, so shell-prompt detection must not treat it as a prompt.

D30's inventory check runs over the skills that are present, here these two. The listing-budget test, if T01 adds it, counts 88 + 50 description characters for them.

(6) Decisions checked and not applied. These keep the text verbatim:
- D17: to-questionnaire's "Ask, in one exchange" and "Interview the user" are plain conversation, not a harness tool name.
- D17/D18.1: "Grill the send" is a leading word, not a load of the `grilling` skill.
- D20: L16 "report the path" does not open a file, so D20 does not apply. Do not add "absolute".
- D16: the `to-questionnaire-<slug>.md` output is written to the current directory, not under `.scratch/`.
- D17: neither description holds a `/name`.

(7) Cross-skill references. Neither skill is renamed or dropped, and neither references another skill. Their only inbound references are ask-matt L87 (`/to-questionnaire`) and ask-matt L89 (`/wait-what`). These are router labels, which D17 keeps with the slash. They are handled in ask-matt's ticket, together with the D21 fallback for ask-matt L89's `GLOSSARY.md`. T01 makes no inbound rewrite. Both ids exist from T01 on, so ask-matt's router resolves whenever ask-matt lands. The bucket `skills/productivity/README.md` is outside any skill directory and is not shipped (D10).

(8) "Layout-only keep". D9 classifies both skills as layout-only keeps. That label still allows the D19 guard line, which applies to all 15 disable-model-invocation skills including these two, and wait-what's D21 fallback, which D9's parenthetical names. These are the only content edits. ATTRIBUTIONS should list them as per-skill bullets, while the id, LICENSE and openai.yaml items can go under the plugin-wide bullets.

(9) README. The D33 README lists both skills among the user-invoked-only skills and says that only Claude Code honours `disable-model-invocation`. In OpenCode, the shared skill root and agent_harness, the guard line is the only portable stop.

## Appendix A.T02: the grilling skills (grill-with-docs, domain-modeling, grill-me, grilling)

Conventions for this appendix:

- Plugin root: `catalog/plugins/mattpocock_skills/`. Every "Plugin path" below is relative to it. ATTRIBUTIONS.md cites the synced paths under the shared skill root, as `.agents/skills/<id>/...` (D12).
- Upstream: repository mattpocock/skills, tag v1.3.1, commit 24fe0ef7737efae15c87225755e9f6f5965e4888 (D4).
- Every line number is an upstream v1.3.1 line number, checked against the files. Inserting `id:` moves every later `SKILL.md` line down by one. In grill-me and grill-with-docs the D19 guard line and its blank line move them down by two more.
- Sections follow the skill order of upstream's plugin manifest: grill-with-docs (3rd), domain-modeling (15th), grill-me (21st), grilling (22nd).
- Build each shipped file by copying the upstream bytes and then making only the edits listed here. Do not retype the files. grilling L13-L21 contain U+2753 and U+27A1 U+FE0F, and the domain-modeling trees (SKILL.md L16-L21, L28-L37) and the arrows in GLOSSARY-FORMAT.md L49-L51 are non-ASCII too. Every upstream file ends in exactly one newline and has no CR and no trailing whitespace; keep it that way.

### A.T02.1 grill-with-docs (upstream skills/engineering/grill-with-docs; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/grill-with-docs/SKILL.md` (7 lines) | `skills/grill-with-docs/SKILL.md` | Changes 1-3 |
  | `skills/engineering/grill-with-docs/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata, including `policy.allow_implicit_invocation: false` (L4-L5); Change 5 |
  | `LICENSE` (upstream repository root) | `skills/grill-with-docs/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 4 |

- **Frontmatter**:

  ```yaml
  ---
  id: grill-with-docs
  name: grill-with-docs
  description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
  disable-model-invocation: true
  ---
  ```

  Changed: `id` is added as the first key (D11). `name`, `description` (upstream's "ADR's" included) and `disable-model-invocation: true` are verbatim. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: grill-with-docs": insert the line `id: grill-with-docs` between the opening `---` (L1) and L2. (D11)
  2. [Invocation guard] `SKILL.md` L6-L7, after the closing `---` (L5): keep upstream's blank L6. Insert the following as the first line of body content, followed by one blank line, before the rewritten L7. (D19)

     ```text
     Run this only when the user asked for it by name; otherwise stop.
     ```

  3. [Capability rewording, cross-skill references] `SKILL.md` L7, "Call the Skill tool twice, for "grilling" and "domain-modeling"." becomes:

     ```text
     Load the `grilling` skill, and load the `domain-modeling` skill.
     ```

     These are two separate loads with no order implied. ATTRIBUTIONS must not claim that an upstream order is kept: upstream `.agents/invocation.md` L20 explains "twice" only as one skill per call. The edit removes the Claude-only name "Skill tool" (D30). Both targets are model-invoked, ship in T02 and keep their ids (D8). (D17, D18.1)
  4. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE` ("Copyright (c) 2026 Matt Pocock"). (D4)
  5. [Dropped] `agents/openai.yaml` is not shipped. The Dropped bullet must say that the file carried `policy.allow_implicit_invocation: false`, the Codex half of upstream's user-only invocation (upstream `.agents/invocation.md` L10). Without it, Codex, which reads the shared skill root `.agents/skills/`, no longer keeps the model from invoking this skill, and the Change 2 guard line is the only guard left there. (D10, D19)

  The complete shipped `SKILL.md`, ending in one newline:

  ```markdown
  ---
  id: grill-with-docs
  name: grill-with-docs
  description: A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary) as we go.
  disable-model-invocation: true
  ---

  Run this only when the user asked for it by name; otherwise stop.

  Load the `grilling` skill, and load the `domain-modeling` skill.
  ```

- **Project-toolchain allowlist**: none. The only line the D30 gates flag, L7's "Skill tool", is removed by Change 3.
- **Skill-specific tests**: Add `tests/plugins/mattpocock_skills/test_skill_loads.py::test_skill_loads_name_model_invoked_skills` unless the shared gate already has an equivalent check (G14 is one). Over T02's four `SKILL.md` files, every match of G14's regex must name an id in `FINAL_IDS - USER_INVOKED_IDS`, as G14 does, not a present directory. This is upstream's invariant (`.agents/invocation.md` L22): no other skill can load a user-invoked skill. Target presence is left to T10's inventory pin (section 7.8), so the test stays green whichever lane merges first. Assert that this file has exactly two matches (`grilling`, `domain-modeling`).
- **Continue degradation**: The skill becomes the user-run `/grill-with-docs` prompt. Its body asks for two loads, and the Continue adapter writes grilling and domain-modeling only as prompts, so neither load fires and the combined docs-writing interview is lost. The user can run `/grilling` and then `/domain-modeling` instead. `disable-model-invocation` (harmless, since prompts are user-run) and `references/LICENSE` are dropped.

### A.T02.2 domain-modeling (upstream skills/engineering/domain-modeling; layout-only keep; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/domain-modeling/SKILL.md` (74 lines) | `skills/domain-modeling/SKILL.md` | Changes 1, 4, 5, 7 |
  | `skills/engineering/domain-modeling/GLOSSARY-FORMAT.md` (60 lines) | `skills/domain-modeling/references/GLOSSARY-FORMAT.md` | Moved (Change 2); D21 edits (Change 8) |
  | `skills/engineering/domain-modeling/ADR-FORMAT.md` (47 lines) | `skills/domain-modeling/references/ADR-FORMAT.md` | Moved byte-identical (Change 3) |
  | `skills/engineering/domain-modeling/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata; Change 9 |
  | `LICENSE` (upstream repository root) | `skills/domain-modeling/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 6 |

- **Frontmatter**:

  ```yaml
  ---
  id: domain-modeling
  name: domain-modeling
  description: Build and sharpen a project's domain model. Use when discussing codebase terminology, writing or editing a GLOSSARY.md (or CONTEXT.md if the repo already has one), or recording or editing an ADR.
  ---
  ```

  Changed: `id` is added as the first key (D11). The `description` value gains the D21 parenthetical (Change 7, L3), growing from 151 to 195 characters (+44). `name` is verbatim. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: domain-modeling": insert the line `id: domain-modeling` between the opening `---` (L1) and L2. (D11)
  2. [Restructure] Move `GLOSSARY-FORMAT.md` to `references/GLOSSARY-FORMAT.md`. Its only content changes are those in Change 8. (D10)
  3. [Restructure] Move `ADR-FORMAT.md` to `references/ADR-FORMAT.md`, byte-identical. It names no glossary file and has no links. (D10)
  4. [Restructure, link rewrite] `SKILL.md` L62, "[GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md)" becomes `[GLOSSARY-FORMAT.md](references/GLOSSARY-FORMAT.md)`. The link text stays, because it is not a code-formatted path, and the target has no leading `./`. (D10)
  5. [Restructure, link rewrite] `SKILL.md` L74, "[ADR-FORMAT.md](./ADR-FORMAT.md)" becomes `[ADR-FORMAT.md](references/ADR-FORMAT.md)`. (D10)
  6. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE`. (D4)
  7. [Glossary naming] `SKILL.md`, seven lines. D9 keeps this fallback for a layout-only keep. Each "before" is a verbatim upstream excerpt, and the "after" replaces exactly that span. (D21)

     ```text
     L3  before: writing or editing a GLOSSARY.md, or recording or editing an ADR.
         after:  writing or editing a GLOSSARY.md (or CONTEXT.md if the repo already has one), or recording or editing an ADR.
     L8  before: (Merely *reading* `GLOSSARY.md` for vocabulary is not this skill:
         after:  (Merely *reading* `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) for vocabulary is not this skill:
     L24 before: If a `GLOSSARY-MAP.md` exists at the root, the repo has multiple contexts.
         after:  If a `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) exists at the root, the repo has multiple contexts.
     L40 before: If no `GLOSSARY.md` exists, create one when the first term is resolved.
         after:  If no `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) exists, create one when the first term is resolved.
     L46 before: conflicts with the existing language in `GLOSSARY.md`, call it out immediately.
         after:  conflicts with the existing language in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one), call it out immediately.
     L62 before: When a term is resolved, update `GLOSSARY.md` right there.
         after:  When a term is resolved, update `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) right there.
     L64 before: `GLOSSARY.md` should be totally devoid of implementation details.
         after:  `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) should be totally devoid of implementation details.
     ```

     The final L62, combining this change with Change 4:

     ```text
     When a term is resolved, update `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) right there. Don't batch these up: capture them as they happen. Use the format in [GLOSSARY-FORMAT.md](references/GLOSSARY-FORMAT.md).
     ```

     These mentions are unchanged on purpose:
     - L16, L28, L33 and L36, which are inside the fenced trees L14-L22 and L26-L38.
     - The L60 heading "### Update GLOSSARY.md inline", because L62 directly under it carries the fallback.
     - L64's second mention, "Do not treat `GLOSSARY.md` as a spec", because the first mention in the same sentence pair carries it.

     The L3 edit changes a frontmatter value that D11 otherwise keeps verbatim. D21 forces it: D21 covers every file that names GLOSSARY.md, and the listing text is what makes the skill discoverable in a repo that already uses CONTEXT.md.
  8. [Glossary naming] `references/GLOSSARY-FORMAT.md`, four lines. (D21)

     ```text
     L34 before: **Single context (most repos):** One `GLOSSARY.md` at the repo root.
         after:  **Single context (most repos):** One `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) at the repo root.
     L36 before: **Multiple contexts:** A `GLOSSARY-MAP.md` at the repo root lists the contexts,
         after:  **Multiple contexts:** A `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) at the repo root lists the contexts,
     L56 before: - If `GLOSSARY-MAP.md` exists, read it to find contexts
         after:  - If `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) exists, read it to find contexts
     L57 before: - If only a root `GLOSSARY.md` exists, single context
         after:  - If only a root `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) exists, single context
     ```

     These are unchanged on purpose:
     - The L1 H1 "# GLOSSARY.md Format".
     - The fenced example L38-L52, including the `./src/<context>/GLOSSARY.md` links at L43-L45. The link validator masks fenced code, so these links need no rewrite after the move.
     - L58, "- If neither exists, create a root `GLOSSARY.md` lazily when the first term is resolved". After L56-L57, "neither" already covers both names, and the file that gets created is still named GLOSSARY.md.
  9. [Dropped] `agents/openai.yaml` (Codex UI metadata, no policy block) is not shipped. (D10)

- **Project-toolchain allowlist**: none. One near-miss must not get a (stale) entry: `references/GLOSSARY-FORMAT.md` L49, "consumes them to start picking", sits on a fenced-block line, but its first word is `-`, so `start` is not in command position.
- **Skill-specific tests**: Add `tests/plugins/mattpocock_skills/test_glossary_fallback.py::test_glossary_mentions_carry_context_fallback`, parametrized over `(skill_id, relative_file)` pairs. T02 provides `("domain-modeling", "SKILL.md")` and `("domain-modeling", "references/GLOSSARY-FORMAT.md")`. Check every line that is outside a fenced block and is not an ATX heading:
  - a line matching `(?<![\w-])GLOSSARY\.md` must also contain `CONTEXT.md`;
  - a line matching `(?<![\w-])GLOSSARY-MAP\.md` must also contain `CONTEXT-MAP.md`.

  Frontmatter lines count, so L3's description is covered. Exempt only `(file, line text)` pairs from a module-level set. For T02 that set holds exactly the `references/GLOSSARY-FORMAT.md` line "- If neither exists, create a root `GLOSSARY.md` lazily when the first term is resolved". An exemption that matches no line fails the test (two-way check). Later tickets that touch D21 files extend the parametrization and the exemption set.
- **Continue degradation**: The skill becomes the user-run `/domain-modeling` prompt. `references/` is not carried, so the two format links (upstream L62 and L74) dangle and the glossary and ADR formats are lost. The description no longer triggers the skill from the model, grill-with-docs cannot load it, and no LICENSE copy travels.

### A.T02.3 grill-me (upstream skills/productivity/grill-me; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/productivity/grill-me/SKILL.md` (7 lines) | `skills/grill-me/SKILL.md` | Changes 1-3 |
  | `skills/productivity/grill-me/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata, including `policy.allow_implicit_invocation: false` (L4-L5); Change 5 |
  | `LICENSE` (upstream repository root) | `skills/grill-me/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 4 |

- **Frontmatter**:

  ```yaml
  ---
  id: grill-me
  name: grill-me
  description: A relentless interview to sharpen a plan or design.
  disable-model-invocation: true
  ---
  ```

  Changed: `id` is added as the first key (D11). `name`, `description` and `disable-model-invocation: true` are verbatim. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: grill-me": insert the line `id: grill-me` between the opening `---` (L1) and L2. (D11)
  2. [Invocation guard] `SKILL.md` L6-L7: keep upstream's blank L6. Insert the following as the first line of body content, followed by one blank line, before the rewritten L7. (D19)

     ```text
     Run this only when the user asked for it by name; otherwise stop.
     ```

  3. [Capability rewording, cross-skill references] `SKILL.md` L7, "Call the Skill tool with "grilling"." becomes:

     ```text
     Load the `grilling` skill.
     ```

     The edit removes the Claude-only name "Skill tool" (D30). The target is model-invoked and keeps its id (D8). (D17)
  4. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE`. (D4)
  5. [Dropped] `agents/openai.yaml` is not shipped. As for grill-with-docs, the Dropped bullet records that `policy.allow_implicit_invocation: false` (the Codex half of user-only invocation, upstream `.agents/invocation.md` L10) is gone, and that the Change 2 guard line is the only guard left outside Claude Code. (D10, D19)

  The complete shipped `SKILL.md`, ending in one newline:

  ```markdown
  ---
  id: grill-me
  name: grill-me
  description: A relentless interview to sharpen a plan or design.
  disable-model-invocation: true
  ---

  Run this only when the user asked for it by name; otherwise stop.

  Load the `grilling` skill.
  ```

- **Project-toolchain allowlist**: none. The only flagged line, L7's "Skill tool", is removed by Change 3.
- **Skill-specific tests**: none beyond the shared gate. Its L7 load is covered by the A.T02.1 load test; assert one match (`grilling`) for this file there.
- **Continue degradation**: The skill becomes the user-run `/grill-me` prompt. Its only instruction, "Load the `grilling` skill.", cannot fire because grilling is only a prompt there, so the user runs `/grilling` directly. No LICENSE copy travels.

### A.T02.4 grilling (upstream skills/productivity/grilling; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/productivity/grilling/SKILL.md` (28 lines) | `skills/grilling/SKILL.md` | Changes 1-2 |
  | `skills/productivity/grilling/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata, no policy block; Change 4 |
  | `LICENSE` (upstream repository root) | `skills/grilling/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 3 |

- **Frontmatter**:

  ```yaml
  ---
  id: grilling
  name: grilling
  description: Grill the user relentlessly about a plan, decision, or idea. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
  ---
  ```

  Changed: `id` is added as the first key (D11). `name` and `description` are verbatim. No `disable-model-invocation`, so there is no D19 guard line. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: grilling": insert the line `id: grilling` between the opening `---` (L1) and L2. (D11)
  2. [Capability rewording] `SKILL.md` L26 has three edits on one line: fact-finding is delegated only to a background agent, with an inline fallback, and "Don't block on it" applies only to that path. (D17, D18.2)
     - "dispatch a sub-agent to find it; don't ask the user" becomes "dispatch a background agent to find it if your harness can run one; otherwise look the fact up yourself before you send the round. Don't ask the user".
     - "Don't block on it:" becomes "If you dispatched a background agent, don't block on it:".
     - "wait for the sub-agent to report" becomes "wait for the background agent to report". Both sentences then name the one capability D18.2 allows.

     The complete new L26:

     ```text
     Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a background agent to find it if your harness can run one; otherwise look the fact up yourself before you send the round. Don't ask the user for anything you could look up yourself. If you dispatched a background agent, don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the background agent to report; ask the rest of the frontier now. The _decisions_ are the user's: put each to them and wait.
     ```

  3. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE`. (D4)
  4. [Dropped] `agents/openai.yaml` is not shipped. (D10)

  Everything else is verbatim, including the emoji round template in the fence L12-L22 and L24's "still open in this round".

- **Project-toolchain allowlist**: none. One near-miss must not get a (stale) entry: L24, "depends on another question still open in this round", is prose, so `open` is not in command position.
- **Skill-specific tests**: Add `tests/plugins/mattpocock_skills/test_grilling.py::test_grilling_fact_lookup_is_capability_gated`. The `SKILL.md` body must contain the exact substrings "dispatch a background agent to find it if your harness can run one; otherwise look the fact up yourself before you send the round" and "If you dispatched a background agent, don't block on it", and must not contain "sub-agent". No denylist catches a re-pin (D5) that silently brings back the unconditional dispatch, so this pins D18.2.
- **Continue degradation**: The skill becomes the user-run `/grilling` prompt. The 'grill' trigger phrases no longer reach it from the model, and the loads in grill-me, grill-with-docs and the other tickets' skills cannot reach it. The body is complete without references, and its inline lookup fallback covers a session without background agents. No LICENSE copy travels.

### Ticket T02 notes

- **Ship the four together.** grill-me and grill-with-docs load grilling and domain-modeling, so the four belong in one ticket. The A.T02.1 load test checks targets against the D9 ids, not present directories, so no other lane waits for T02.
- **LICENSE source.** The `references/LICENSE` copies are made from the plugin-root `catalog/plugins/mattpocock_skills/LICENSE`, so the byte-identity gate compares against one source. That file and the D32 ruff extend-exclude for `catalog/plugins/mattpocock_skills/**/*.md` must be on the branch before or with T02, or the near-verbatim markdown gets reformatted.
- **Decisions that do not apply.** No change from D13-D16, D20 or D22-D26 applies to these skills: none has tracker, setup, file-opening, script, report, teach, handoff, retro or sentinel text. None of them has a URL, an imposed tool, a slash label or a renamed or dropped outbound reference. None of them reads or writes `docs/agents/*`, CLAUDE.md or AGENTS.md. GLOSSARY.md and `docs/adr/` are consumer domain docs, never engine output.
- **Inbound references owned by other tickets.** These must use the same sentence forms as T02, written once in prose, never as "Skill tool" calls:
  - wayfinder `SKILL.md` L79, L111 and L124 ("call the Skill tool twice, for "grilling" and "domain-modeling"") take the A.T02.1 Change 3 sentence: "load the `grilling` skill, and load the `domain-modeling` skill", capitalised to fit its position. Wayfinder's `grilling` ticket type (L65) and the local seed's `Type:` value (`issue-tracker-local.md` L26) are labels, not loads, and stay.
  - improve-codebase-architecture `SKILL.md` L64 and L66 ("call the Skill tool with "grilling"" / "with "domain-modeling"") become "load the `grilling` skill" and "load the `domain-modeling` skill".
  - setup's `domain.md` L11 ("The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`)") and L45 ("note it for `/domain-modeling`") are agent-facing, so they drop the slashes (D17). `domain.md` also takes its own D21 edits.
  - ask-matt `SKILL.md` L17, L64, L83 and L84 are router labels and keep `/grill-with-docs`, `/domain-modeling`, `/grill-me` and `/grilling` (D17). L84's `/triage` goes per D7 in ask-matt's ticket.
  - triage `SKILL.md` L76 is not shipped (D7).
- **How D21 was applied.** The fallback is the exact D21 phrase, code-formatted when the mention it follows is code-formatted. The map form is "`GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one)": upstream's CHANGELOG records that CONTEXT-MAP.md was the map's name before the rename. It goes once on each prose line that names the file. Fenced examples and headings stay verbatim, and so does a line whose wording already covers both names (GLOSSARY-FORMAT L58). Later tickets with D21 files should use the same rule and extend the A.T02.2 test, so the plugin reads one way throughout.
- **Superseded audit proposals.** Several audit and verify proposals are superseded by decisions.md:
  - the audit's "if your harness can run subagents" for grilling L26 is replaced by D18.2's background-agent-only gate, with "Don't block on it" scoped as the verifier asked;
  - the audit's "then load" order for grill-with-docs is replaced by D18.1's unordered "and load";
  - the audit's "not-synced" destination for `agents/openai.yaml` is replaced by "not shipped" (D10);
  - the audit's "domain-modeling needs no text change" is replaced by D9/D21's glossary fallback.

  The verifier's open questions are settled elsewhere: the Claude-only names denylist is D30, and the upstream Claude Code plugin coexistence note (its domain-modeling still uses CONTEXT.md) is D33, in the README ticket, together with the superpowers pair grilling / brainstorming.
- **D19 position and F6.** The guard sits on the first body content line, after the frontmatter and upstream's blank line, because the engine writes its sentinel as the first body line of synced output (`renderer.with_sentinel_body`). The spec must record that the skills-first spec's F6 keeps `disable-model-invocation` (D19): grill-me and grill-with-docs depend on it, and on Codex they now rely on the guard line alone.
- **Verbatim on purpose.** These are kept as upstream has them and are not listed as changes:
  - grill-with-docs' "ADR's";
  - grilling's emoji round template;
  - domain-modeling's examples (Postgres, AWS, GraphQL/REST, ORM, a `src/` tree). These are illustrations, not a D27 TypeScript/Jest/JS stack assumption.
- **Listing budget (D30, D31).** T02's four descriptions total 504 characters (grilling 152, domain-modeling 195, grill-me 51, grill-with-docs 106). Only domain-modeling's +44 grows on upstream.
- **ATTRIBUTIONS wording.** Use "vendored content" in the bundled plugin's ATTRIBUTIONS.md and cite paths as `.agents/skills/<id>/` (D12).

## A.T03 Ticket T03: the tracker skills (setup-matt-pocock-skills, to-spec, to-tickets)

Conventions for this appendix. "Plugin path" is the source path in the engine repo. Changes cite synced paths under the shared skill root (`.agents/skills/<id>/...`, D12), the way ATTRIBUTIONS will. Every L-number is an upstream v1.3.1 line, checked against the checkout. Build every shipped file by copying the upstream bytes and then making only the edits listed here. Every upstream file here uses LF, has no CR and no trailing whitespace, and ends in exactly one newline; keep it that way. Keep the non-ASCII characters: domain.md has box-drawing characters at L19-L23 and L30-L38, a U+2190 arrow at L31 and L35 and U+2026 at L51; to-tickets has U+2013 at L40, U+2192 at L62 and L63 and U+2026 at L63. Insert the `id:` line as text; do not load and re-dump the YAML. The D19 guard line is this exact sentence, its own paragraph: `Run this only when the user asked for it by name; otherwise stop.`

### A.T03.1 setup-matt-pocock-skills (upstream skills/engineering/setup-matt-pocock-skills; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/setup-matt-pocock-skills/SKILL.md` (116 lines, ASCII) | `catalog/plugins/mattpocock_skills/skills/setup-matt-pocock-skills/SKILL.md` | Vendored content, changes 1-24. It shrinks to 81 lines (the full result is under change 24). |
  | `skills/engineering/setup-matt-pocock-skills/domain.md` (51 lines) | `catalog/plugins/mattpocock_skills/skills/setup-matt-pocock-skills/references/domain.md` | Moved (D10), changes 25-31. Still 51 lines. It is a seed that setup copies to the consumer's `docs/agents/domain.md`. |
  | `skills/engineering/setup-matt-pocock-skills/issue-tracker-local.md` (30 lines) | `catalog/plugins/mattpocock_skills/skills/setup-matt-pocock-skills/references/issue-tracker-local.md` | Moved (D10), changes 32-40. It grows to 41 lines; the exact final text is in "T03 local tracker seed" below. Setup copies it to the consumer's `docs/agents/issue-tracker.md`. |
  | `skills/engineering/setup-matt-pocock-skills/triage-labels.md` (15 lines, sha256 `4f53c9b40ce2651e3611aa090eaedbd6dbc9b71ef8c5f7e65eac0d8263190d0d`) | `catalog/plugins/mattpocock_skills/skills/setup-matt-pocock-skills/references/triage-labels.md` | Moved (D10), byte-identical (change 41). Setup copies it to the consumer's `docs/agents/triage-labels.md`. |
  | `skills/engineering/setup-matt-pocock-skills/issue-tracker-github.md` (45 lines) | not shipped | Dropped (D2, D13, D14): gh, jq and `gh api` instructions, plus the PR request-surface flag (change 42). |
  | `skills/engineering/setup-matt-pocock-skills/issue-tracker-gitlab.md` (46 lines) | not shipped | Dropped (D2, D4, D13, D14): glab instructions, a URL at L3 and the MR request-surface flag (change 42). |
  | `skills/engineering/setup-matt-pocock-skills/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata (D10): `display_name: "Setup Matt Pocock Skills"`, `short_description: "Configure a repo for the skills"`, `policy.allow_implicit_invocation: false` (change 43). |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/setup-matt-pocock-skills/references/LICENSE` | A byte-identical copy of the plugin-root LICENSE, sha256 `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5` (D4, change 44). |

  The plugin skill directory then holds exactly `SKILL.md` and `references/` with `LICENSE`, `domain.md`, `issue-tracker-local.md` and `triage-labels.md`. Upstream has no `scripts/`.

- **Frontmatter** (plugin source, in this order). `id` is added as the first key (D11). The other keys are byte-identical to upstream L2-L4, including the double quotes around the description, which the value's ": " needs (180 characters without the quotes). The description is unchanged: its "triage label vocabulary" stays true because Section B now always writes the file (D14). It holds no `/name`, so D17 changes nothing in it. There is no `playbook:` block (D11).

  ```yaml
  ---
  id: setup-matt-pocock-skills
  name: setup-matt-pocock-skills
  description: "Configure this repo for the engineering skills: set up its issue tracker, triage label vocabulary, and domain doc layout. Run once before first use of the other engineering skills."
  disable-model-invocation: true
  ---
  ```

- **Changes**. SKILL.md first, then the three seeds, then the files that are dropped or added.

  1. [Frontmatter] `.agents/skills/setup-matt-pocock-skills/SKILL.md`, before L2 "name: setup-matt-pocock-skills". Insert `id: setup-matt-pocock-skills` as the new L2. (D11; the plugin-wide Frontmatter bullet may cover it.)
  2. [Invocation guard] `SKILL.md`, between L6 (the blank line after the closing `---`) and L7 "# Setup Matt Pocock's Skills". Insert the guard line followed by one blank line, so that it is the first line of body content, above the H1. The engine's sentinel goes above it at sync and is never written in the source. Result: L7 blank (upstream L6), L8 guard line, L9 blank, L10 = upstream L7. (D19)
  3. [Tracker] `SKILL.md` L11. Upstream: "where issues live (GitHub by default; local markdown is also supported out of the box)". Final line (D13, D14):

     ```text
     - **Issue tracker**: where issues live (local markdown by default; any other tracker works once the user describes it)
     ```
  4. [Glossary naming] `SKILL.md` L13. Upstream: "where `GLOSSARY.md` and ADRs live". Insert ` (or `CONTEXT.md` if the repo already has one)` after the `GLOSSARY.md` code span. (D21)

     ```text
     - **Domain docs**: where `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and ADRs live, and the consumer rules for reading them
     ```
  5. [Generated files] `SKILL.md` L24. Upstream: "`AGENTS.md` and `CLAUDE.md` at the repo root: does either exist? Is there already an `## Agent skills` section in either?". The check becomes read-only; the report to the user is change 24's step 5 sentence. Final line (D14):

     ```text
     - `AGENTS.md` and `CLAUDE.md` at the repo root: is there an old `## Agent skills` section in either? Read them only to answer that: this skill never edits or creates either file (step 5 says what to tell the user).
     ```
  6. [Glossary naming] `SKILL.md` L25. Upstream: "`GLOSSARY.md` and `GLOSSARY-MAP.md` at the repo root". Final line (D21):

     ```text
     - `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) at the repo root
     ```
  7. [Dropped skill] `SKILL.md` L29. Upstream: "Is the `triage` skill installed? ... This decides whether Section B runs at all." Delete the whole bullet. (D7, D14)
  8. [Dropped skill] `SKILL.md` L36. Upstream: "(Section B when `triage` isn't installed, Section C when there's no monorepo)". Final line (D7, D14):

     ```text
     Lead each section with the recommended answer so the user can accept it in a word. Give a one-line explainer only when the choice genuinely branches; skip the section entirely when exploration already settled it (Section C when there's no monorepo). Section B is written without asking.
     ```
  9. [Dropped skill; imposed tool] `SKILL.md` L40. Upstream: "Skills like `to-tickets`, `triage`, and `to-spec`" and "whether to call `gh issue create`, write a markdown file under `.scratch/`, or follow". `triage` leaves the list (D7) and the gh clause goes (D2, D13). Final line:

     ```text
     > Explainer: The "issue tracker" is where issues live for this repo. Skills like `to-tickets` and `to-spec` read from and write to it. They need to know whether to write a markdown file under `.scratch/` or follow some other workflow you describe. Pick the place you actually track work for this repo.
     ```
  10. [Tracker] `SKILL.md` L42. Upstream: "Default posture: these skills were designed for GitHub. If a `git remote` points at GitHub, propose that." The rewrite also removes the bare `gitlab.com` host name. Final line (D13, D14):

      ```text
      Default posture: propose local markdown, even when a `git remote` points at a forge; a user who tracks work in that forge's issues, or anywhere else, picks **Other**. Offer:
      ```
  11. [Imposed tool] `SKILL.md` L44. Upstream: "**GitHub**: issues live in the repo's GitHub Issues (uses the `gh` CLI)". Delete the bullet. (D2, D13, D14)
  12. [Imposed tool; URL] `SKILL.md` L45. Upstream: "**GitLab**: issues live in the repo's GitLab Issues (uses the [`glab`](<URL elided>) CLI)". Delete the bullet. This removes glab and the plugin's only SKILL.md URL. (D2, D4, D13, D14)
  13. [Tracker] `SKILL.md` L46. Upstream: "(good for solo projects or repos without a remote)". Final line (D14):

      ```text
      - **Local markdown**: issues live as files under `.scratch/<feature>/` in this repo (the default; needs no remote or CLI)
      ```
  14. [Tracker] `SKILL.md` L47. Upstream: "**Other** (Jira, Linear, etc.): ask the user to describe the workflow in one paragraph; the skill will record it as freeform prose". Other now fills in the same sections as the local seed. The parenthetical "(Jira, Linear, etc.)" stays verbatim: D14 drops every gh/glab/gitlab text from setup, no decision forces adding product names (D4), and change 10's posture line already sends forge users to Other. Final line (D13, D14):

      ```text
      - **Other** (Jira, Linear, etc.): ask the user to describe the workflow for each section of [issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions: publish, fetch, close, blocking (default: a plain `Blocked by:` line near the top of each ticket) and the Wayfinding operations; the skill will record each answer under that section's heading
      ```
  15. [Tracker; dropped skill] `SKILL.md` L49. Upstream: "The GitHub and GitLab templates carry a "PRs as a request surface" flag, defaulted **off**. Leave it off and don't raise it: ...". Delete both sentences after the first. Final line (D7, D14):

      ```text
      Record the choice in `docs/agents/issue-tracker.md`.
      ```
  16. [Dropped skill] `SKILL.md` L51-L57 (Section B). Upstream: "Skip this section entirely if the `triage` skill isn't installed", "If it is installed, ask exactly one question:" and "> Do you want to keep the default triage labels? (recommended: **yes**)". Replace L51-L57 with exactly these two paragraphs, so that upstream L52-L55 (the question and its blank lines) are deleted and the blank L56 stays between them (D7, D14):

      ```text
      **Section B: Triage label vocabulary.** Always written, without asking: `to-spec` and `to-tickets` apply these labels.

      The defaults are the five canonical roles, each label string equal to its name: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Write them as-is. If the user's tracker already uses other names (e.g. `bug:triage` for `needs-triage`), they change the right-hand column in the step 3 draft, so the skills apply existing labels instead of creating duplicates.
      ```
  17. [Glossary naming] `SKILL.md` L59. Upstream: "(one `GLOSSARY.md` + `docs/adr/` at the repo root)". Final line (D21):

      ```text
      **Section C: Domain docs.** Default to **single-context** (one `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) + `docs/adr/` at the repo root). This fits almost every repo; write it without asking.
      ```
  18. [Glossary naming] `SKILL.md` L61. Upstream: "(a root `GLOSSARY-MAP.md` pointing to per-context `GLOSSARY.md` files)". Final line (D21):

      ```text
      Offer **multi-context** (a root `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) pointing to per-context `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) files) only when exploration found monorepo signals. Then confirm which layout they want.
      ```
  19. [Generated files] `SKILL.md` L67. Upstream: "The `## Agent skills` block to add to whichever of `CLAUDE.md` / `AGENTS.md` is being edited". Delete the bullet. (D14, D15)
  20. [Dropped skill] `SKILL.md` L68. Upstream: "and `docs/agents/triage-labels.md` (the last only when `triage` is installed)". Delete the parenthetical and the space before it. Final line (D7, D14):

      ```text
      - The contents of `docs/agents/issue-tracker.md`, `docs/agents/domain.md`, and `docs/agents/triage-labels.md`
      ```
  21. [Generated files] `SKILL.md` L74-L104 (step 4). Replace everything from L74 "**Pick the file to edit:**" through L104 "Then write the docs files using the seed templates in this skill folder as a starting point:" with the two paragraphs below. Keep the blank L73 before them; the blank between them is upstream L103. ATTRIBUTIONS records this as four bullets:
      - (a) removed: the "Pick the file to edit" subsection, L74-L82 ("If `CLAUDE.md` exists, edit it.", "Never create `AGENTS.md` when `CLAUDE.md` already exists", "update its contents in-place"). (D14)
      - (b) removed: "The block:" and the fenced `## Agent skills` block, L84-L100. The plugin always rule `mattpocock-skills-tracker` replaces it. (D15)
      - (c) removed: L102 "Include the `### Triage labels` sub-block, and write `docs/agents/triage-labels.md`, only when `triage` is installed and Section B ran. When it isn't, both are omitted." (D7, D14)
      - (d) added: the write-only paragraph, and "Then write" became "Write" at L104. (D14)

      ```text
      Write only `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and `docs/agents/domain.md`. Never edit or create `CLAUDE.md` or `AGENTS.md`: the always rule this plugin ships (`mattpocock-skills-tracker`) already points every session at these files.

      Write the docs files using the seed templates in this skill folder as a starting point:
      ```
  22. [Tracker; restructure] `SKILL.md` L106-L110 (the seed list). Delete L106 "- [issue-tracker-github.md](./issue-tracker-github.md): GitHub issue tracker" and L107 "- [issue-tracker-gitlab.md](./issue-tracker-gitlab.md): GitLab issue tracker" (D14). Point the three remaining links at `references/` (D10). Drop L109's "(only if `triage` is installed)" (D7, D14). Final three lines:

      ```text
      - [issue-tracker-local.md](./references/issue-tracker-local.md): local-markdown issue tracker
      - [triage-labels.md](./references/triage-labels.md): label mapping
      - [domain.md](./references/domain.md): domain doc consumer rules + layout
      ```
  23. [Tracker] `SKILL.md` L112. Upstream: "For "other" issue trackers, write `docs/agents/issue-tracker.md` from scratch using the user's description." Final line (D14, D16):

      ```text
      For "other" issue trackers, write `docs/agents/issue-tracker.md` from scratch using the user's description, under the same `##` headings as [issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions; keep the `## Wayfinding operations` heading verbatim, since `wayfinder` looks it up by name.
      ```
  24. [Generated files] `SKILL.md` L116 (step 5). Upstream ends "...if they want to switch issue trackers or restart from scratch." Append one sentence to the same line, after a space (D14):

      ```text
      If exploration found an old `## Agent skills` section in a root `CLAUDE.md` or `AGENTS.md`, tell them the always rule this plugin ships (`mattpocock-skills-tracker`) supersedes it and that they may delete it; don't edit the file yourself.
      ```

      To check changes 1-24, here is the complete resulting `SKILL.md` (81 lines, ending in one newline):

      ````markdown
      ---
      id: setup-matt-pocock-skills
      name: setup-matt-pocock-skills
      description: "Configure this repo for the engineering skills: set up its issue tracker, triage label vocabulary, and domain doc layout. Run once before first use of the other engineering skills."
      disable-model-invocation: true
      ---

      Run this only when the user asked for it by name; otherwise stop.

      # Setup Matt Pocock's Skills

      Scaffold the per-repo configuration that the engineering skills assume:

      - **Issue tracker**: where issues live (local markdown by default; any other tracker works once the user describes it)
      - **Triage labels**: the strings used for the five canonical triage roles
      - **Domain docs**: where `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and ADRs live, and the consumer rules for reading them

      This is a prompt-driven skill, not a deterministic script. Explore, present what you found, confirm with the user, then write.

      ## Process

      ### 1. Explore

      Look at the current repo to understand its starting state. Read whatever exists; don't assume:

      - `git remote -v` and `.git/config`: is this a GitHub repo? Which one?
      - `AGENTS.md` and `CLAUDE.md` at the repo root: is there an old `## Agent skills` section in either? Read them only to answer that: this skill never edits or creates either file (step 5 says what to tell the user).
      - `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) at the repo root
      - `docs/adr/` and any `src/*/docs/adr/` directories
      - `docs/agents/`: does this skill's prior output already exist?
      - `.scratch/`: a sign that a local-markdown issue tracker convention is already in use
      - Monorepo signals: a `pnpm-workspace.yaml`, a `workspaces` field in `package.json`, or a populated `packages/*` with its own `src/`. These are present only in a genuinely large multi-package repo; their absence means single-context, which is almost every repo.

      ### 2. Present findings and ask

      Summarise what's present and what's missing. Then take the sections in order. One section, one answer, then the next.

      Lead each section with the recommended answer so the user can accept it in a word. Give a one-line explainer only when the choice genuinely branches; skip the section entirely when exploration already settled it (Section C when there's no monorepo). Section B is written without asking.

      **Section A: Issue tracker.**

      > Explainer: The "issue tracker" is where issues live for this repo. Skills like `to-tickets` and `to-spec` read from and write to it. They need to know whether to write a markdown file under `.scratch/` or follow some other workflow you describe. Pick the place you actually track work for this repo.

      Default posture: propose local markdown, even when a `git remote` points at a forge; a user who tracks work in that forge's issues, or anywhere else, picks **Other**. Offer:

      - **Local markdown**: issues live as files under `.scratch/<feature>/` in this repo (the default; needs no remote or CLI)
      - **Other** (Jira, Linear, etc.): ask the user to describe the workflow for each section of [issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions: publish, fetch, close, blocking (default: a plain `Blocked by:` line near the top of each ticket) and the Wayfinding operations; the skill will record each answer under that section's heading

      Record the choice in `docs/agents/issue-tracker.md`.

      **Section B: Triage label vocabulary.** Always written, without asking: `to-spec` and `to-tickets` apply these labels.

      The defaults are the five canonical roles, each label string equal to its name: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Write them as-is. If the user's tracker already uses other names (e.g. `bug:triage` for `needs-triage`), they change the right-hand column in the step 3 draft, so the skills apply existing labels instead of creating duplicates.

      **Section C: Domain docs.** Default to **single-context** (one `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) + `docs/adr/` at the repo root). This fits almost every repo; write it without asking.

      Offer **multi-context** (a root `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) pointing to per-context `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) files) only when exploration found monorepo signals. Then confirm which layout they want.

      ### 3. Confirm and edit

      Show the user a draft of:

      - The contents of `docs/agents/issue-tracker.md`, `docs/agents/domain.md`, and `docs/agents/triage-labels.md`

      Let them edit before writing.

      ### 4. Write

      Write only `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and `docs/agents/domain.md`. Never edit or create `CLAUDE.md` or `AGENTS.md`: the always rule this plugin ships (`mattpocock-skills-tracker`) already points every session at these files.

      Write the docs files using the seed templates in this skill folder as a starting point:

      - [issue-tracker-local.md](./references/issue-tracker-local.md): local-markdown issue tracker
      - [triage-labels.md](./references/triage-labels.md): label mapping
      - [domain.md](./references/domain.md): domain doc consumer rules + layout

      For "other" issue trackers, write `docs/agents/issue-tracker.md` from scratch using the user's description, under the same `##` headings as [issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions; keep the `## Wayfinding operations` heading verbatim, since `wayfinder` looks it up by name.

      ### 5. Done

      Tell the user the setup is complete and which engineering skills will now read from these files. Mention they can edit `docs/agents/*.md` directly later; re-running this skill is only necessary if they want to switch issue trackers or restart from scratch. If exploration found an old `## Agent skills` section in a root `CLAUDE.md` or `AGENTS.md`, tell them the always rule this plugin ships (`mattpocock-skills-tracker`) supersedes it and that they may delete it; don't edit the file yourself.
      ````

  25. [Restructure] `skills/engineering/setup-matt-pocock-skills/domain.md` moved to `.agents/skills/setup-matt-pocock-skills/references/domain.md`. The file has no links, so no link inside it changes. (D10)
  26. [Glossary naming] `references/domain.md` L7. Upstream: "- **`GLOSSARY.md`** at the repo root, or". Final line (D21):

      ```text
      - **`GLOSSARY.md`** (or `CONTEXT.md` if the repo already has one) at the repo root, or
      ```
  27. [Glossary naming] `references/domain.md` L8. Upstream: "- **`GLOSSARY-MAP.md`** at the repo root if it exists: it points at one `GLOSSARY.md` per context." Final line (D21):

      ```text
      - **`GLOSSARY-MAP.md`** (or `CONTEXT-MAP.md` if the repo already has one) at the repo root if it exists: it points at one `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) per context. Read each one relevant to the topic.
      ```
  28. [Skill names] `references/domain.md` L11. Upstream: "The `/domain-modeling` skill (reached via `/grill-with-docs` and `/improve-codebase-architecture`) creates them lazily". This is agent-facing prose (the consumer's `docs/agents/domain.md`), so the three leading slashes go; nothing else on the line changes. Final line (D17):

      ```text
      If any of these files don't exist, **proceed silently**. Don't flag their absence; don't suggest creating them upfront. The `domain-modeling` skill (reached via `grill-with-docs` and `improve-codebase-architecture`) creates them lazily when terms or decisions actually get resolved.
      ```
  29. [Glossary naming] `references/domain.md` L26. Upstream: "Multi-context repo (presence of `GLOSSARY-MAP.md` at the root):". Final line (D21):

      ```text
      Multi-context repo (presence of `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) at the root):
      ```
  30. [Glossary naming] `references/domain.md` L43. Upstream: "use the term as defined in `GLOSSARY.md`. Don't drift". Insert the fallback before the period. Final line (D21):

      ```text
      When your output names a domain concept (in an issue title, a refactor proposal, a hypothesis, a test name), use the term as defined in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one). Don't drift to synonyms the glossary explicitly avoids.
      ```
  31. [Skill names] `references/domain.md` L45. Upstream: "(note it for `/domain-modeling`)". Final: "(note it for `domain-modeling`)"; nothing else changes. (D17)

      The fenced trees L17-L24 and L28-L39 (GLOSSARY.md at L19, L34, L37; GLOSSARY-MAP.md at L30) stay byte-identical, under the plugin-wide D21 rule that A.T02 set: the fallback goes on prose lines only, and fenced examples and headings stay verbatim. Prose L7, L8 and L26 above each tree carry it.
  32. [Restructure] `skills/engineering/setup-matt-pocock-skills/issue-tracker-local.md` moved to `.agents/skills/setup-matt-pocock-skills/references/issue-tracker-local.md`. It has no links. L10's "`triage-labels.md`" is a code span, not a link, and is not rewritten: it names the consumer's sibling `docs/agents/triage-labels.md`, which Section B now always writes (D14). (D10)
  33. [Local tracker] `references/issue-tracker-local.md`, after L9 (the "Implementation issues are one file per ticket" bullet). Insert this bullet. (D16)

      ```text
      - Every issue file (the spec, each ticket) and every map opens with a `# <title>` heading: its name
      ```
  34. [Local tracker] `references/issue-tracker-local.md`, after L11 (the "## Comments" bullet). Insert these two bullets. (D16)

      ```text
      - `.scratch/` is untracked working state: never stage it in a commit
      - Worktrees do not contain untracked files: when you point a subagent or a worktree at a spec, ticket or map, give its absolute path in the main checkout
      ```
  35. [Local tracker] `references/issue-tracker-local.md`, after L19 (end of the "fetch the relevant ticket" section). Insert a blank line and the section `## When a skill says "close" or "resolve" a ticket` with its paragraph, exactly as in the final text below. It defines closed as any terminal status, `resolved` or `out-of-scope`, and the in-place rewrite of to-tickets' bold `**Status:**` line. Implementation tickets are set `resolved` when merged. (D14, D16)
  36. [Local tracker] `references/issue-tracker-local.md`, directly after change 35. Insert a blank line and the section `## Blocking` with its paragraph, exactly as in the final text below. It holds the plain `Blocked by:` default and "unblocked when every ticket it lists is closed". (D14, D16)
  37. [Skill names] `references/issue-tracker-local.md` L23. Upstream: "Used by `/wayfinder`." Final: "Used by `wayfinder`." The `## Wayfinding operations` heading at L21 stays verbatim. (D16, D17)
  38. [Local tracker] `references/issue-tracker-local.md` L26. Upstream: "a `Status:` line records `claimed`/`resolved`." Final: "a `Status:` line records `claimed`/`resolved`/`out-of-scope`." (D16)
  39. [Local tracker] `references/issue-tracker-local.md` L27. Upstream: "A ticket is unblocked when every file it lists is `resolved`." Final: "A ticket is unblocked when every file it lists is closed (`resolved` or `out-of-scope`)." (D16)
  40. [Local tracker] `references/issue-tracker-local.md` L30. Upstream ends "to the map's Decisions-so-far in `map.md`." Append, after a space: "Only the session driving the map appends to `map.md`; a research subagent writes only its own ticket file." (D16)
  41. [Restructure] `skills/engineering/setup-matt-pocock-skills/triage-labels.md` moved to `.agents/skills/setup-matt-pocock-skills/references/triage-labels.md`, byte-identical. The L5 column header "Label in mattpocock/skills" stays verbatim: it is a repository name, not a URL and not a coupling marker (D30). (D10)
  42. [Dropped] `issue-tracker-github.md` and `issue-tracker-gitlab.md` are not shipped. ATTRIBUTIONS "Dropped" bullet: the GitHub and GitLab tracker templates. They told the agent to run gh, glab, jq and `gh api`/`glab api`, the GitLab one held a URL (L3), and they alone defined the "PRs (MRs) as a request surface" flag that triage read. Only the local-markdown template ships. A GitHub or GitLab user takes **Other** and records the same sections in their own words (changes 14, 23). (D2, D4, D13, D14)
  43. [Dropped] `agents/openai.yaml` is not shipped. The Dropped bullet records that it carried `policy.allow_implicit_invocation: false`, so Codex (which reads the shared skill root) loses its user-only policy for this skill. What remains is `disable-model-invocation`, which only Claude Code honours, and the change 2 guard line. (D10, D19)
  44. [License] `.agents/skills/setup-matt-pocock-skills/references/LICENSE` added, a byte-identical copy of the plugin-root LICENSE (upstream MIT, "Copyright (c) 2026 Matt Pocock"). (D4; the plugin-wide "License copies added" bullet may cover it.)
  45. [Added, replaces upstream text] The "## Agent skills" block that upstream wrote into CLAUDE.md or AGENTS.md is replaced by the engine-authored plugin always rule `catalog/plugins/mattpocock_skills/rules/mattpocock-skills-tracker.md` (exact text in "T03 plugin always rule" below). ATTRIBUTIONS lists it under additions, not as vendored content. (D15)

- **Project-toolchain allowlist**: none expected. The only candidate is `SKILL.md` L30, "Monorepo signals: a `pnpm-workspace.yaml`, a `workspaces` field in `package.json`", kept verbatim on purpose (D28). This is a consumer-repo file read, and the first word of that code span is the file name `pnpm-workspace.yaml`, not the command `pnpm`. A command-position matcher that compares the whole first whitespace-delimited word (the T02 convention) does not flag it, so an entry would be stale and fail the two-way check. Only if T01's matcher instead matches `pnpm` followed by a regex word boundary (`-` ends a word) add exactly this entry: `skills/setup-matt-pocock-skills/SKILL.md: a \`pnpm-workspace.yaml\``. Changes 9, 11 and 12 remove the other upstream hits (gh at L40 and L44, glab and the URL at L45, the bare `gitlab.com` at L42). The three seeds have no hit.

- **Skill-specific tests**: put these in `tests/plugins/mattpocock_skills/test_tracker_setup.py`, or in the module the shared gate already uses for per-skill contracts.
  1. `test_setup_references_inventory`: `skills/setup-matt-pocock-skills/references/` holds exactly `{LICENSE, domain.md, issue-tracker-local.md, triage-labels.md}`. No file named `issue-tracker-github.md` or `issue-tracker-gitlab.md` exists anywhere under the plugin.
  2. `test_local_tracker_headings`: the `## ` headings of `references/issue-tracker-local.md` are exactly these, in this order: `Conventions`, `When a skill says "publish to the issue tracker"`, `When a skill says "fetch the relevant ticket"`, `When a skill says "close" or "resolve" a ticket`, `Blocking`, `Wayfinding operations`. The file's first line is `# Issue tracker: Local Markdown`. This pins the contract with wayfinder L25 (the heading looked up by name) and with setup changes 14 and 23 (Other mirrors these sections).
  3. `test_local_tracker_close_contract`: `references/issue-tracker-local.md` contains `` `out-of-scope` ``, `**Status:**`, `**Blocked by:**`, `` `Blocked by: NN, NN` `` and "absolute path in the main checkout". to-tickets' `SKILL.md` still contains `**Status:** ready-for-agent` and `**Blocked by:**`, so the in-place rewrite rule names lines that exist.
  4. `test_triage_labels_seed`: `references/triage-labels.md` contains the header cell `Label in mattpocock/skills`, and the table maps each of `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix` to itself.
  5. `test_setup_replay_guard`, which guards against a future tag upgrade bringing the removed text back. `SKILL.md` contains none of `issue-tracker-github`, `issue-tracker-gitlab`, `Pick the file to edit`, `PRs as a request surface`, `` the `triage` skill installed ``, `gh issue`. It does contain `(the default; needs no remote or CLI)` and `never edits or creates either file`.
  6. Extend A.T02's `tests/plugins/mattpocock_skills/test_glossary_fallback.py::test_glossary_mentions_carry_context_fallback` parametrization with `("setup-matt-pocock-skills", "SKILL.md")` and `("setup-matt-pocock-skills", "references/domain.md")`. No exemption is needed: every prose line naming the files carries the fallback, and the trees are fenced.
  7. The always-rule tests are listed under "T03 plugin always rule" below.

- **Continue degradation**: With the `continue` adapter listed, the skill becomes the user-run `.continue/prompts/setup-matt-pocock-skills.md`. It carries only the body, and `references/` does not travel, so the three seed links (changes 14, 22, 23) dangle. The agent must write `docs/agents/*.md` from SKILL.md's prose alone, without the seed wording: the local tracker's close, blocking and Wayfinding operations conventions, the `.scratch/` and absolute-path rules, the domain-doc consumer rules and the label table. No LICENSE copy travels. `disable-model-invocation` is dropped, but a Continue prompt is always started by the user, which satisfies the guard. The always rule still reaches Continue as its own `.continue/rules/` file. (D29)

### A.T03.2 to-spec (upstream skills/engineering/to-spec; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/to-spec/SKILL.md` (75 lines, ASCII) | `catalog/plugins/mattpocock_skills/skills/to-spec/SKILL.md` | Vendored content, changes 1-2. It grows to 78 lines. |
  | `skills/engineering/to-spec/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata (D10): `display_name: "To Spec"`, `short_description: "Turn a conversation into a spec"`, `policy.allow_implicit_invocation: false` (change 4). |
  | upstream repository-root `LICENSE`, through the plugin-root copy | `catalog/plugins/mattpocock_skills/skills/to-spec/references/LICENSE` | A byte-identical copy of the plugin-root LICENSE (D4, change 3). |

  Upstream has no sibling files and no `scripts/`. The plugin skill directory holds exactly `SKILL.md` and `references/LICENSE`.

- **Frontmatter**. `id` is added as the first key (D11). The other keys are byte-identical to upstream L2-L4, including the description's double quotes (149 characters without them). There is no `/name` in it and no `playbook:` block.

  ```yaml
  ---
  id: to-spec
  name: to-spec
  description: "Turn the current conversation into a spec and publish it to the project issue tracker: no interview, just synthesis of what you've already discussed."
  disable-model-invocation: true
  ---
  ```

- **Changes**:
  1. [Frontmatter] `.agents/skills/to-spec/SKILL.md`, before L2 "name: to-spec". Insert `id: to-spec` as the new L2. (D11; the plugin-wide bullet may cover it.)
  2. [Invocation guard] `SKILL.md`, between L6 (blank) and L7 "This skill takes the current conversation context and codebase understanding and produces a spec." Insert the guard line followed by one blank line, as the first line of body content (the skill has no H1). Result: L7 blank, L8 guard, L9 blank, L10 = upstream L7. (D19)
  3. [License] `.agents/skills/to-spec/references/LICENSE` added, a byte-identical copy of the plugin-root LICENSE. (D4; plugin-wide bullet.)
  4. [Dropped] `agents/openai.yaml` not shipped. Codex loses `policy.allow_implicit_invocation: false`. What remains is `disable-model-invocation` plus the change 2 guard. (D10, D19)

  Kept verbatim on purpose. L9 "If not, tell the user to run `/setup-matt-pocock-skills`." is a human-facing pointer, so D17 keeps the slash; the audit's slash-stripping edit is dropped. L9's "should have been provided to you" is made true by the plugin always rule and by triage-labels.md always being written (D14, D15). L13 names the glossary abstractly ("the project's domain glossary vocabulary"), not GLOSSARY.md, so there is no D21 edit. In L19's "Apply the `ready-for-agent` triage label - no need for additional triage", "triage" is the activity, not the dropped skill. In L57, "a prototype" is a common noun, not the renamed prototype skill (D8).

- **Project-toolchain allowlist**: none. No denylisted word, no URL, no Claude-only name and no coupling marker appears. The `<spec-template>` block (L21-L75) is a tagged block, not a fenced one, and none of its lines starts with an ambiguous word in command position.

- **Skill-specific tests**: none beyond the shared gate. The D17 replay guard ("tell the user to run `/setup-matt-pocock-skills`" still present) is folded into A.T03.3's test so that both skills are checked in one place.

- **Continue degradation**: `.continue/prompts/to-spec.md` carries only the body (guard line included), with no `references/LICENSE` and no `disable-model-invocation`. Nothing functional is lost. The body is self-contained, the tracker docs it relies on live in the consumer repo, and the always rule reaches Continue as its own rule file. A Continue prompt is always user-started. (D29)

### A.T03.3 to-tickets (upstream skills/engineering/to-tickets; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/to-tickets/SKILL.md` (105 lines; U+2013 at L40, U+2192 at L62-L63, U+2026 at L63) | `catalog/plugins/mattpocock_skills/skills/to-tickets/SKILL.md` | Vendored content, changes 1-3. It grows to 108 lines. |
  | `skills/engineering/to-tickets/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata (D10): `display_name: "To Tickets"`, `short_description: "Split a plan into tracer-bullet tickets"`, `policy.allow_implicit_invocation: false` (change 5). |
  | upstream repository-root `LICENSE`, through the plugin-root copy | `catalog/plugins/mattpocock_skills/skills/to-tickets/references/LICENSE` | A byte-identical copy of the plugin-root LICENSE (D4, change 4). |

  Upstream has no sibling files and no `scripts/`. The plugin skill directory holds exactly `SKILL.md` and `references/LICENSE`.

- **Frontmatter**. `id` is added as the first key (D11). The other keys are byte-identical to upstream L2-L4. The description stays an unquoted plain scalar (247 characters, no ": " in it). It holds no `/name`.

  ```yaml
  ---
  id: to-tickets
  name: to-tickets
  description: Break a plan, spec, or the current conversation into a set of tracer-bullet tickets, each declaring its blocking edges, published to the configured tracker (edges as text in one file per ticket locally, or native blocking links on a real tracker).
  disable-model-invocation: true
  ---
  ```

- **Changes**:
  1. [Frontmatter] `.agents/skills/to-tickets/SKILL.md`, before L2 "name: to-tickets". Insert `id: to-tickets` as the new L2. (D11; plugin-wide bullet.)
  2. [Invocation guard] `SKILL.md`, between L6 (blank) and L7 "# To Tickets". Insert the guard line followed by one blank line, as the first line of body content, above the H1. Result: L7 blank, L8 guard, L9 blank, L10 = "# To Tickets". (D19)
  3. [Skill names] `SKILL.md` L60. Upstream: "**How** depends on the tracker `/setup-matt-pocock-skills` configured;". This is agent-facing process prose, not a "tell the user to run" line, so the slash goes. Final line (D17):

     ```text
     Publish the approved tickets. **How** depends on the tracker `setup-matt-pocock-skills` configured; the tickets are the same either way, only the shape of the blocking edges changes:
     ```
  4. [License] `.agents/skills/to-tickets/references/LICENSE` added, a byte-identical copy of the plugin-root LICENSE. (D4; plugin-wide bullet.)
  5. [Dropped] `agents/openai.yaml` not shipped. Codex loses `policy.allow_implicit_invocation: false`. What remains is `disable-model-invocation` plus the change 2 guard. (D10, D19)

  Kept verbatim on purpose:
  - L11 "If not, tell the user to run `/setup-matt-pocock-skills`." is human-facing, so D17 keeps it; the audit's edit is dropped.
  - L21 names the glossary abstractly (no D21).
  - L62's local branch already matches the shipped seed (`.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`).
  - L63 "**A real issue tracker (GitHub, Linear, …)**" names products, not CLIs. Its "native blocking / sub-issue relationship" now comes from the Blocking section that setup records in `docs/agents/issue-tracker.md` (D13, D14).
  - L65 "any ticket whose blockers are all done": "done" reads as closed under the seed's definition, so no decision forces "closed".
  - L71 `# <NN>: <Ticket title>` already satisfies D16's title heading.
  - L77 `**Status:** ready-for-agent` is the bold line the seed's close section rewrites in place (D16).
  - In L105, "a prototype" (twice) is a common noun (D8). L31's "(schema, API, UI, tests)" and L105's "(state machine, reducer, schema, type shape)" are generic illustrations, not D27 TypeScript or Jest examples.
  - L17's "an issue number or URL" is the word "URL", not a URL.

- **Project-toolchain allowlist**: none. L38's "can start immediately" and L75/L101's "None (can start immediately)" are prose, not code spans, so `start` is not in command position. No fenced block exists (the templates are tagged blocks).

- **Skill-specific tests**: `test_setup_pointer_slash_forms` in `tests/plugins/mattpocock_skills/test_tracker_setup.py`, a D17 replay guard covering A.T03.2 too:
  - to-spec `SKILL.md` and to-tickets `SKILL.md` each contain "tell the user to run `/setup-matt-pocock-skills`";
  - to-tickets `SKILL.md` contains "the tracker `setup-matt-pocock-skills` configured" and no "the tracker `/setup-matt-pocock-skills`".

  Nothing else is needed beyond the shared gate.

- **Continue degradation**: `.continue/prompts/to-tickets.md` carries only the body (guard line included), with no `references/LICENSE` and no `disable-model-invocation`. Nothing functional is lost. The body and both ticket templates are inline, the tracker docs live in the consumer repo, and the always rule reaches Continue as its own rule file. (D29)

### T03 plugin always rule (mattpocock-skills-tracker; D15)

New engine-authored file `catalog/plugins/mattpocock_skills/rules/mattpocock-skills-tracker.md`. It is plain `.md`, never `.md.j2`: the body has no Jinja, and a `.j2` would render under StrictUndefined. Its frontmatter keys are all `RuleFrontmatter` fields; an unknown key raises at sync. It has `scope: always`, no `skill:` (V3 forbids it on an always rule; V1 stops sync on a scoped rule without one), no `applies_if` (a gate would hide the rule between setup and the next sync) and no `globs`. The id is unique across core and plugins. Exact file content, ending in one newline:

```markdown
---
id: mattpocock-skills-tracker
name: Issue tracker and domain docs
description: Where this repo's issue tracker, triage label and domain doc config lives, and that .scratch/ is never staged.
version: 1
scope: always
priority: 50
tags: [always, tracker]
---

When present, `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and `docs/agents/domain.md` describe this repo's issue tracker, triage labels and domain docs: read the one a skill needs. If a skill needs one that is missing, tell the user to run `/setup-matt-pocock-skills`. `.scratch/` is untracked working state: never stage or commit it.
```

Word count: the body is 46 words, split on whitespace (353 characters). The renderer adds the `## Issue tracker and domain docs` heading from `name` in `.claude/rules/coding-agent-playbook.md` and AGENTS.md (`_render_markdown_rule_section`), 5 more words, 51 in total. The body has no H1 of its own, so the heading is not doubled. Both counts are under D15's 60.

How it meets D15:
- It names the three files as the repo's tracker, label and domain config.
- "When present" and "If a skill needs one that is missing" mean it never presents the setup-only files as always existing, and it does not nag in sessions that need no tracker.
- The pointer keeps `/setup-matt-pocock-skills` (human-facing, D17).
- It states the `.scratch/` rule (D16).
- It has no `references/` or `scripts/` path (the skill root differs per adapter).
- It has no URL and no link, so the link validator has nothing to resolve.

Delivery: the rule goes to Claude Code (`.claude/rules/coding-agent-playbook.md`) and to AGENTS.md (OpenCode, Codex), as `.continue/rules/<NN>-mattpocock-skills-tracker.md` for Continue, and as `rules/<NN>-mattpocock-skills-tracker.md` for agent_harness, interleaved with core rules by (priority, id).

Tests (`tests/plugins/mattpocock_skills/test_tracker_rule.py`):
1. `test_plugin_adds_exactly_the_tracker_rule`. Compare `FileSystemArtifactSource(repo_root=tmp_path, overlay_packages=["coding_agent_playbook.plugins.mattpocock_skills"]).list_rules()` with the same call without the overlay. Exactly one extra rule appears, with id `mattpocock-skills-tracker`. Its `frontmatter.scope == "always"`, `frontmatter.skill is None` and `frontmatter.applies_if == {}`. Its source path ends in `.md` and not `.md.j2`. `list_prompts()` is unchanged.
2. `test_tracker_rule_body_contract`. The body after the frontmatter has at most 60 whitespace-separated words. It contains `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `docs/agents/domain.md`, `` `/setup-matt-pocock-skills` `` and `` `.scratch/` ``. It contains neither `references/` nor `scripts/`. `catalog/plugins/mattpocock_skills/skills/setup-matt-pocock-skills/SKILL.md` exists, so the pointer names a shipped skill.
3. `test_tracker_rule_renders_once`. Sync a consumer repo with the plugin enabled, using the plugin's sync fixture shaped like `test_superpowers_sync.py`'s (`write_consumer_repo(..., overlays=[PLUGIN_NAME])`, `_sync.execute(repo, git=FakeGitClient())`). Then AGENTS.md and `.claude/rules/coding-agent-playbook.md` each contain `## Issue tracker and domain docs` exactly once.

### T03 local tracker seed (references/issue-tracker-local.md; D14, D16)

The exact final text of `catalog/plugins/mattpocock_skills/skills/setup-matt-pocock-skills/references/issue-tracker-local.md` (41 lines, ASCII, LF, one final newline). Upstream lines that are not named in changes 33-40 are byte-identical.

````markdown
# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Every issue file (the spec, each ticket) and every map opens with a `# <title>` heading: its name
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading
- `.scratch/` is untracked working state: never stage it in a commit
- Worktrees do not contain untracked files: when you point a subagent or a worktree at a spec, ticket or map, give its absolute path in the main checkout

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## When a skill says "close" or "resolve" a ticket

Set the file's `Status:` line, in place, to a terminal status: `resolved` (answered or done) or `out-of-scope` (ruled out). A ticket is **closed** when its status is either one; any other status is open. Set an implementation ticket `resolved` once its work is merged. A ticket written by `to-tickets` has the bold form `**Status:** ready-for-agent`: rewrite that line in place, never add a second status line.

## Blocking

A ticket's blockers go on a `Blocked by:` line near the top (bold, `**Blocked by:**`, in a ticket written by `to-tickets`), listing the numbers of the tickets that gate it (titles may follow), or `None (can start immediately)`. A ticket is unblocked when every ticket it lists is closed.

## Wayfinding operations

Used by `wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`/`out-of-scope`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is closed (`resolved` or `out-of-scope`).
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`. Only the session driving the map appends to `map.md`; a research subagent writes only its own ticket file.
````

How it covers D14 and D16:
- D14: it holds the publish, fetch, close and blocking sections (blocking with a plain `Blocked by:` default) and the Wayfinding operations section that Other mirrors.
- D16:
  - `.scratch/` is untracked and never staged;
  - pointers handed to a subagent or a worktree are absolute paths into the main checkout;
  - closed means `resolved` or `out-of-scope`, and a ticket is unblocked when every blocker is closed;
  - an implementation ticket is set `resolved` when merged, by rewriting to-tickets' bold `**Status:**` line in place;
  - every map and ticket file opens with a `# <title>` heading;
  - a single session appends to `map.md`, and research subagents write only their own ticket file;
  - the "Wayfinding operations" heading is verbatim, with the plain-name lead-in "Used by `wayfinder`.".
- The `prototype` ticket type at L26 is not a skill id and stays (D8).

### T03 Dropped: triage (D7)

ATTRIBUTIONS "## Dropped and why" entry for triage. T01 writes that global section (section 5.3 item 12); T03 checks it against the text below and records any correction in the setup-matt-pocock-skills section, which T10 folds in. The text: **triage** (upstream `skills/engineering/triage/`: `SKILL.md` 112 lines, `AGENT-BRIEF.md` 207, `OUT-OF-SCOPE.md` 105, `agents/openai.yaml` 5) is not shipped. It moves incoming issues, and optionally external PRs, through category and state roles. It does this with labels, reporter replies, `wontfix` closes, an `.out-of-scope/` knowledge base and a PR request-surface flag that only the dropped GitHub and GitLab tracker templates defined. The only shipped tracker, local markdown, records a single `Status:` line and has none of that. A consumer can add it repo-locally under `playbook/skills/triage/`. It then reads the same `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md` that setup writes, and with no request-surface flag in the local seed it handles issues only.

What the shipped skills say instead:
- **setup-matt-pocock-skills** no longer detects triage (change 7, L29). Section B always writes `docs/agents/triage-labels.md` with the five default roles, without asking (change 16, L51-L57; change 8, L36). The explainer lists only `to-tickets` and `to-spec` (change 9, L40). The PR-flag sentences are gone (change 15, L49). The triage conditionals are gone from step 3, step 4 and the seed list (changes 20, 21c, 22). The description, which says "triage label vocabulary", is unchanged and stays true.
- **triage-labels.md** (seed) is verbatim. "five canonical triage roles" names the roles, not the skill.
- **issue-tracker-local.md** keeps L10's pointer to `triage-labels.md`, which is now always valid.
- **to-spec** and **to-tickets** are unchanged. Their "The issue tracker and triage label vocabulary should have been provided to you" (to-spec L9, to-tickets L11) is now true, through the always rule and the always-written labels file. to-spec L19's "no need for additional triage" is the activity, not the skill.
- **The plugin always rule** names `docs/agents/triage-labels.md`.
- **ask-matt** (its own ticket) removes the `/triage` on-ramp (L44-L46) and `/triage` from L84's list. It keeps L95's "configure the issue tracker, triage labels, and doc layout" and its `/setup-matt-pocock-skills` router label (D17).
- Upstream's bucket README, which lists triage, is not shipped (D10).

**Ticket T03 notes.**

- **Order.**
  - T01 must already have created the plugin-root `catalog/plugins/mattpocock_skills/LICENSE` and the D32 ruff extend-exclude. Copy, do not retype, the LICENSE into the three `references/LICENSE` files.
  - Within T03, copy the three shipped seeds (domain.md, issue-tracker-local.md, triage-labels.md) into `references/` first, byte for byte. Then apply SKILL.md changes 1-24, then the seed edits (changes 26-31 and 33-40).
  - Add the rule file, then to-spec and to-tickets. The rule's test 2 needs the setup skill directory to exist.
  - Upstream order (the `skills` list of upstream's plugin manifest, which is not shipped) is triage, setup-matt-pocock-skills, to-spec, to-tickets, so the numbering above follows it with triage dropped.
- **Gate facts.** G1 and G2 (T01) already allow the plugin's `rules/` directory and its one rule, so T03 edits no shared gate file.
  - The D30 URL, denylist, Claude-only-name and coupling scans cover `rules/` and the seeds too. Neither has a hit: `mattpocock-skills-tracker` and `setup-matt-pocock-skills` do not contain `mattpocock-skills:`.
  - D19's guard check finds the guard in all three skills.
  - The listing-budget test counts the three unchanged descriptions: 180 + 149 + 247 = 576 characters.
  - The always rule adds 353 body characters to always-loaded context only where the plugin is enabled. The D31 reference probe (superpowers plus python_design) is unaffected, so `tests/integration/test_context_budget.py` stays untouched (D37).
- **Cross-ticket references.**
  - T04 (wayfinder, implement-spec, implement) keeps its tracker lines verbatim on the strength of the seed text above: the heading, close semantics, title headings, absolute paths, single map writer and the bold Status rewrite. T04's notes paraphrase the lead-in as "Used by wayfinder."; the authoritative text is "Used by `wayfinder`." (a code span, no slash). Any test pinning it should use this form.
  - wayfinder L25 ("Consult the tracker doc's "Wayfinding operations" section") is why test 2 pins the heading list.
  - two-axis-review L13 (A.T05), implement-spec L9 and wayfinder L25 (A.T04) keep "tell the user to run `/setup-matt-pocock-skills`", consistent with the always rule. implement-spec's description keeps `/to-spec` and `/to-tickets` (A.T04, D17).
  - ask-matt's ticket handles the triage routes (see Dropped).
  - domain.md L11 names `domain-modeling` and `grill-with-docs` (A.T02) and `improve-codebase-architecture` (its own ticket). These are plain mentions, neither links nor loads, so there is no ordering constraint, and none of the three ids is renamed (D9).
  - No T03 skill is renamed (D8), so no other skill needs a T03-driven edit.
- **Ambiguities resolved.**
  1. *Guard position.* For setup and to-tickets, which have an H1, the guard is the first line of body content, above the H1, matching A.T01, A.T02 and A.T04. The engine's sentinel sits above it at sync.
  2. *D21 in fenced trees.* domain.md's trees stay verbatim, following the plugin-wide rule that A.T02 set (prose lines only; fenced examples and headings unchanged), so A.T02's fallback test covers these files unchanged.
  3. *Title headings.* D16 says "map and ticket file". The seed also includes the spec, because in this tracker a spec is an issue file that skills publish and fetch like a ticket. If review rejects that, change the change-33 bullet to "Every ticket file and every map opens with a `# <title>` heading: its name"; nothing else depends on it.
  4. *Always-rule trigger.* D15's "if they are missing" is narrowed to "If a skill needs one that is missing", so the always-loaded rule does not prompt for setup in sessions that use no tracker skill.
  5. *Section B "without asking".* Label overrides still happen, by editing the step 3 draft or the file later (triage-labels.md L15 already invites this).
  6. *L23 kept.* "is this a GitHub repo? Which one?" stays verbatim: git is allowed (D2), and change 10's posture uses its answer to point forge users at Other.
- **Audit edits dropped by decisions.**
  - (a) Stripping the slash at to-spec L9 and to-tickets L11 (D17).
  - (b) Keeping Section B triage-gated, and the audit's keep-verbatim notes for L29, L51-L57 and L102 (D14 ungates it).
  - (c) Deleting L24 outright (D14 keeps a read-only stale-block check).
  - (d) Rewording L104 to "in this skill's `references/` folder": not forced, because the links carry the path.
  - (e) Rewording to-tickets L60 to "the tracker configured for this repo": D17 asks only for the plain name.
  - (f) Rewording to-tickets L63's "(GitHub, Linear, …)": no denylist hit.
  - (g) The audit's rule options: a "## Agent skills" block in CLAUDE.md or AGENTS.md, an `applies_if` gate on the rule, and "triage-labels.md (when present)" wording. D15 and D14 replace them.
- **Not applicable to T03.** D18 (no subagents or loads in these skills), D20 (nothing is opened), D22-D26 (no scripts, report, teach, handoff, retro or writing-for-agents text), D27 (no TypeScript, Jest or JS-frontend example). D28 applies only as a verbatim keep: setup L30's JS-only monorepo markers. ATTRIBUTIONS records them under consumer-repo conventions as a stack assumption, not as a change.
- **Docs follow-ups (not T03 files).**
  - SPEC 11.5 currently says bundled plugins ship skills only. The rule must be described in SPEC 11.5.3 in docs PR B (D35). T03 does not edit SPEC.md (D37).
  - The plugin README (D33) must list these three skills among the user-invoked-only ones (only Claude Code honours `disable-model-invocation`; elsewhere the guard line is the only stop). It must also say to gitignore `.scratch/`, that setup writes only `docs/agents/*.md`, and that the always rule replaces upstream's CLAUDE.md block.
  - D19's F6 note (the skills-first spec's F6 must keep `disable-model-invocation`) applies to all three skills.

### A.T04.1 wayfinder (upstream skills/engineering/wayfinder; vendored with listed changes; user-invoked)

- **Files**:

| Upstream file | Plugin path | Note |
|---|---|---|
| skills/engineering/wayfinder/SKILL.md (128 lines) | catalog/plugins/mattpocock_skills/skills/wayfinder/SKILL.md | Vendored with the changes below; synced as `.agents/skills/wayfinder/SKILL.md` (D12). No sibling files and no scripts upstream, so nothing moves and no link is rewritten. |
| skills/engineering/wayfinder/agents/openai.yaml (5 lines) | not shipped | Codex UI metadata: `interface.display_name` "Wayfinder", `interface.short_description` "Map a large effort as decision tickets", `policy.allow_implicit_invocation: false`. Listed under Dropped in ATTRIBUTIONS (D10). The user-invoked markers left are `disable-model-invocation: true` and the D19 guard line. |
| (none, added) | catalog/plugins/mattpocock_skills/skills/wayfinder/references/LICENSE | Byte-identical copy of catalog/plugins/mattpocock_skills/LICENSE (upstream MIT, "Copyright (c) 2026 Matt Pocock") (D4). SKILL.md does not mention it. |

- **Frontmatter**: `id` added as the first key; every other key and value is byte-identical to upstream L2-L4 (D11). The description is human-facing (user-invoked) and contains no `/name`, so D17 changes nothing in it.

```yaml
---
id: wayfinder
name: wayfinder
description: Plan a huge chunk of work (more than one agent session can hold) as a shared map of decision tickets on your issue tracker, and resolve them one at a time until the way to the destination is clear.
disable-model-invocation: true
---
```

- **Changes**:

1. **SKILL.md L2, frontmatter (D11).** Upstream "name: wayfinder". Insert the line `id: wayfinder` directly above it, so `id` is the first key. No other frontmatter line changes.

2. **SKILL.md, before L7 (D19).** Upstream L7 begins "A loose idea has arrived, too big for one agent session". Insert the guard line as the first line of the body content: after the closing `---` and the blank upstream L6, before L7, followed by one blank line. Sync later puts the engine's sentinel above it (first body line); the source never carries the sentinel.

```text
Run this only when the user asked for it by name; otherwise stop.
```

3. **SKILL.md L77 (D17, D18.4).** Upstream "Resolved by a subagent that calls the Skill tool with "research"." Resulting line:

```text
- **Research** (AFK): Reading documentation, third-party APIs, or local resources like knowledge bases to surface a fact a decision waits on. Resolved by a subagent that loads the `research` skill; if your harness cannot run subagents, the session working through the map loads the `research` skill itself (charting leaves the ticket on the frontier). Use when knowledge outside the current working directory is required.
```

4. **SKILL.md L78 (D8, D17).** Upstream "by calling the Skill tool with "prototype"". The skill load points at the renamed skill; the bullet label "**Prototype** (HITL)" and "Links the prototype as an asset" are the ticket type, not the skill id, and stay (D8). Resulting line:

```text
- **Prototype** (HITL): Raise the fidelity of the discussion by making a cheap, rough, concrete artifact to react to (an outline, a rough take, a stub, or UI/logic code) by loading the `throwaway-prototype` skill. Links the prototype as an asset. Use when "how should it look" or "how should it behave" is the key question.
```

5. **SKILL.md L79 (D17, D18.1).** Upstream "Always call the Skill tool twice, for "grilling" and "domain-modeling"." Resulting line:

```text
- **Grilling** (HITL): Conversation. The default case. Always load the `grilling` skill, and load the `domain-modeling` skill.
```

6. **SKILL.md L111 (D17, D18.1).** Upstream "Call the Skill tool twice, for "grilling" and "domain-modeling", to pin down". Resulting line:

```text
1. **Name the destination.** Load the `grilling` skill, and load the `domain-modeling` skill, to pin down what this map is finding its way to: the spec, decision, or change. The destination fixes the scope, so it's settled first.
```

7. **SKILL.md L115 (D17, D18.4).** Upstream "For each `research` ticket you just created, spin up a subagent that calls the Skill tool with "research" to resolve it in parallel". Capability-gated, and without subagents the tickets stay on the frontier (charting never resolves by hand, upstream L116). Resulting line:

```text
5. **Fire the research subagents.** If your harness can run subagents, then for each `research` ticket you just created, spin up a subagent that loads the `research` skill to resolve it in parallel, capturing its findings on a throwaway `research/<name>` branch with a context pointer from the ticket. Otherwise, leave the research tickets on the frontier for a later session.
```

8. **SKILL.md L120 (D13, D14).** Upstream "User invokes with a map (URL or number)." On the only shipped tracker, local markdown (the default), a map is the file `.scratch/<effort>/map.md`, which has neither a URL nor a number. Resulting line:

```text
User invokes with a map (URL, number, or path). A ticket is **optional**: without one, you pick the next decision, not the user.
```

9. **SKILL.md L124 (D17, D18.1).** Upstream "call the Skill tool for whichever skills the `## Notes` block names. If in doubt, call the Skill tool twice, for "grilling" and "domain-modeling"." Both loads on the line change; "each skill" keeps one load per skill. Resulting line:

```text
3. Resolve it. **Zoom as needed**: fetch the full body of any related or closed ticket on demand; load each skill the `## Notes` block names. If in doubt, load the `grilling` skill, and load the `domain-modeling` skill.
```

10. **agents/openai.yaml, whole file (D10).** Upstream "allow_implicit_invocation: false". Not shipped; ATTRIBUTIONS lists it under Dropped together with the `policy.allow_implicit_invocation` marker it carried.

11. **references/LICENSE, new file (D4).** Byte-identical copy of the plugin-root LICENSE; covered by the "License copies added" bullet.

- **Project-toolchain allowlist**: none. (Ambiguous denylist words appear only as prose: "open" at L29, L67, L69, L84, L112 and "starts" at L9; no fenced-block line, code span or script line starts with a denylisted word.)

- **Skill-specific tests**: add to `tests/plugins/mattpocock_skills/test_execution_skill_loads.py` (see the T04 notes for the shared shape): the load targets extracted from wayfinder's SKILL.md are exactly {`research`, `throwaway-prototype`, `grilling`, `domain-modeling`}, each a D9 id outside the 15 user-invoked ids; `prototype` is never a load target while the label list "`research`, `prototype`, `grilling`, `task`" (upstream L65) is still present verbatim; the body keeps "tell the user to run `/setup-matt-pocock-skills`" (D17) and contains "leave the research tickets on the frontier" (D18.4 replay guard).

- **Continue degradation**: with the `continue` adapter listed, `.continue/prompts/wayfinder.md` carries only name, description and body (no references/LICENSE, no `disable-model-invocation`, so the D19 guard line is the only marker left), the loads of research, throwaway-prototype, grilling and domain-modeling resolve only where the Continue IDE also reads those skills natively from `.claude/skills`, and where it cannot run subagents research tickets wait on the frontier (D18.4).

### A.T04.2 implement (upstream skills/engineering/implement; vendored with listed changes; user-invoked)

- **Files**:

| Upstream file | Plugin path | Note |
|---|---|---|
| skills/engineering/implement/SKILL.md (15 lines) | catalog/plugins/mattpocock_skills/skills/implement/SKILL.md | Vendored with the changes below; synced as `.agents/skills/implement/SKILL.md` (D12). No sibling files and no scripts upstream. |
| skills/engineering/implement/agents/openai.yaml (5 lines) | not shipped | Codex UI metadata: `interface.display_name` "Implement", `interface.short_description` "Build work from a spec or tickets", `policy.allow_implicit_invocation: false`. Listed under Dropped (D10). |
| (none, added) | catalog/plugins/mattpocock_skills/skills/implement/references/LICENSE | Byte-identical copy of catalog/plugins/mattpocock_skills/LICENSE (D4). SKILL.md does not mention it. |

- **Frontmatter**: `id` added as the first key; the other keys are byte-identical to upstream L2-L4, including the double quotes around the description value (D11).

```yaml
---
id: implement
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---
```

- **Changes**:

1. **SKILL.md L2, frontmatter (D11).** Upstream "name: implement". Insert `id: implement` directly above it as the first key.

2. **SKILL.md, before L7 (D19).** Upstream L7 "Implement the work described by the user in the spec or tickets." Insert the guard line as the first line of the body content (after the blank upstream L6, before L7), followed by one blank line:

```text
Run this only when the user asked for it by name; otherwise stop.
```

3. **SKILL.md L9 (D17).** Upstream "Use /tdd where possible, at pre-agreed seams." An operative `/name` instruction becomes a skill load (tdd is model-invoked). Resulting line:

```text
Load the `tdd` skill and use it where possible, at pre-agreed seams.
```

4. **SKILL.md L13 (D8, D17).** Upstream "Once done, use /code-review to review the work." Operative load of the renamed skill (two-axis-review stays model-invoked). Resulting line:

```text
Once done, load the `two-axis-review` skill to review the work.
```

5. **agents/openai.yaml, whole file (D10).** Upstream "allow_implicit_invocation: false". Not shipped; listed under Dropped.

6. **references/LICENSE, new file (D4).** Byte-identical copy of the plugin-root LICENSE.

- **Project-toolchain allowlist**: none. L11 ("Run typechecking regularly, single test files regularly, and the full test suite once at the end.") is the consumer's project toolchain but names no command or denylisted word, so an entry for it would be stale under D30's two-way check.

- **Skill-specific tests**: in the same `test_execution_skill_loads.py`: the load targets extracted from implement's SKILL.md are exactly {`tdd`, `two-axis-review`}; the body contains no `/tdd` and no `/code-review` and no load of `code-review`.

- **Continue degradation**: with the `continue` adapter listed, `.continue/prompts/implement.md` carries only name, description and body (no references/LICENSE, no `disable-model-invocation`, so the D19 guard line is the only marker left), and the tdd and two-axis-review loads resolve only where the Continue IDE also reads those skills natively from `.claude/skills`; nothing else is lost (no references, no subagents).

### A.T04.3 implement-spec (upstream skills/engineering/implement-spec; vendored with listed changes; user-invoked)

- **Files**:

| Upstream file | Plugin path | Note |
|---|---|---|
| skills/engineering/implement-spec/SKILL.md (40 lines) | catalog/plugins/mattpocock_skills/skills/implement-spec/SKILL.md | Vendored with the changes below; synced as `.agents/skills/implement-spec/SKILL.md` (D12). No sibling files and no scripts upstream. |
| skills/engineering/implement-spec/agents/openai.yaml (5 lines) | not shipped | Codex UI metadata: `interface.display_name` "Implement Spec", `interface.short_description` "Implement the result of /to-spec and /to-tickets in code.", `policy.allow_implicit_invocation: false`. Listed under Dropped (D10). |
| (none, added) | catalog/plugins/mattpocock_skills/skills/implement-spec/references/LICENSE | Byte-identical copy of catalog/plugins/mattpocock_skills/LICENSE (D4). SKILL.md does not mention it. |

- **Frontmatter**: `id` added as the first key; the other keys are byte-identical to upstream L2-L4 (D11). The description keeps its `/to-spec` and `/to-tickets` labels: it is a user-invoked skill's human-facing description (D17), so the audit's slash-stripping edit is dropped.

```yaml
---
id: implement-spec
name: implement-spec
description: "Implement the result of /to-spec and /to-tickets in code."
disable-model-invocation: true
---
```

- **Changes**:

1. **SKILL.md L2, frontmatter (D11).** Upstream "name: implement-spec". Insert `id: implement-spec` directly above it as the first key.

2. **SKILL.md, before L7 (D19).** Upstream L7 "You have been provided a spec." Insert the guard line as the first line of the body content (after the blank upstream L6, before L7), followed by one blank line:

```text
Run this only when the user asked for it by name; otherwise stop.
```

3. **SKILL.md after L17 (D17, D18.5).** Upstream L17 "**Implementer subagents** should be run in the background where possible for maximum concurrency." stays unchanged. Insert one new paragraph after it (a blank line, then the text below; the existing blank line before `## Steps` follows). It is the single no-subagent fallback for the exploration subagent (L23), the implementer subagents (L27-L30, L34, the L36 fix pass), the merger subagent (L32) and the worktree cleanup (L40). `/implement-spec` keeps its slash because the sentence is addressed to the user (D17).

```text
If your harness cannot run subagents, do each subagent's job below yourself, one ticket at a time: build each frontier ticket on its own branch off the integration branch and merge it in before taking the next. Each merge is a stop-and-resume point: when your context is getting full, stop there and tell the user to start a fresh context and run `/implement-spec` again. A resumed run reuses the integration branch and skips the tickets already merged into it.
```

4. **SKILL.md L25 (D18.5).** Upstream "or the user asks for one, open a draft PR after the first merge in step 5". The forge mechanics come only from the tracker description; no forge CLI is named. Resulting line:

```text
3. Create the integration branch. If the issue tracker closes work through PRs, or the user asks for one, open a draft PR, as the issue tracker describes, after the first merge in step 5 (a branch with no commits ahead of main can't open one), marked as closing the spec and tickets.
```

5. **SKILL.md L29 (D17).** Upstream "calls the Skill tool with `tdd` to build the ticket;". Resulting line (three leading spaces, as upstream):

```text
   - loads the `tdd` skill to build the ticket;
```

6. **SKILL.md L36 (D8, D17).** Upstream "call the Skill tool with `code-review` on the integration branch." Operative load of the renamed skill; "the code review" later on the line is a plain noun and stays. Resulting line:

```text
7. Once all tickets are complete, load the `two-axis-review` skill and run it on the integration branch. Fix all issues raised by the code review in a single **implementer subagent**.
```

7. **agents/openai.yaml, whole file (D10).** Upstream "short_description: "Implement the result of /to-spec and /to-tickets in code."". Not shipped; listed under Dropped.

8. **references/LICENSE, new file (D4).** Byte-identical copy of the plugin-root LICENSE.

- **Project-toolchain allowlist**: none. ("open a draft PR" and "can't open one" at L25 are prose, not command position; the new paragraph's "start a fresh context" is prose too.)

- **Skill-specific tests**: in the same `test_execution_skill_loads.py`: the load targets extracted from implement-spec's SKILL.md are exactly {`tdd`, `two-axis-review`}; no load of `code-review`; the description still contains "/to-spec" and "/to-tickets" and the body still contains "tell the user to run `/setup-matt-pocock-skills`" (D17 replay guard); the body contains "stop-and-resume point" and "run `/implement-spec` again" (D18.5 replay guard); no forge CLI name appears (already covered by the shared denylist, so no extra assertion).

- **Continue degradation**: with the `continue` adapter listed, `.continue/prompts/implement-spec.md` carries only name, description and body (no references/LICENSE, no `disable-model-invocation`, so the D19 guard line is the only marker left), the tdd and two-axis-review loads resolve only where the Continue IDE also reads those skills natively from `.claude/skills`, and where it cannot run subagents the L17 sequential stop-and-resume fallback replaces the parallel frontier.

**Ticket T04 notes.**

- **Numbering and order.** "Upstream order" is the order of the `skills` list in upstream's Claude Code plugin manifest (`plugin.json`, not shipped), the manifest that publishes the 27 skills (D7): wayfinder, implement, implement-spec. The bucket README orders them implement, implement-spec, wayfinder; the task brief listed wayfinder, implement-spec, implement. Inside T04 the three skills can be written in any order: none links to another's files, and none loads another (implement-spec only names `/to-spec` and `/to-tickets` as labels).
- **Line numbers.** Every L-number above is an upstream v1.3.1 line, confirmed against the checkout (wayfinder SKILL.md 128 lines, implement 15, implement-spec 40; each openai.yaml 5). After the `id` line and the guard line are inserted, body lines shift by 3 (1 frontmatter line, guard line, blank line), and implement-spec lines after L17 shift by 2 more (the fallback paragraph and its blank line); ATTRIBUTIONS cites upstream numbers.
- **Cross-ticket load targets.** wayfinder loads research, throwaway-prototype, grilling and domain-modeling; implement and implement-spec load tdd and two-axis-review. All six are D9 ids and none carries `disable-model-invocation`, which upstream's invariant requires (a user-invoked skill can only load model-invoked skills). The renames (code-review to two-axis-review, prototype to throwaway-prototype, D8) are applied here as inbound references; the renamed directories, ids and `name` keys belong to their own tickets. research must carry the D18.3 nesting guard (an agent already running as a subagent or background agent does the research itself), because wayfinder L77 and L115 start research inside a subagent; without it the two texts nest agents. The T04 load-target test checks targets against the D9 id list and the 15 user-invoked ids (ask-matt, grill-me, grill-with-docs, handoff, implement, implement-spec, improve-codebase-architecture, retro, setup-matt-pocock-skills, teach, to-questionnaire, to-spec, to-tickets, wait-what, wayfinder), not against present directories, so T04 can land before those tickets. Regex for the test: `` [Ll]oad(?:s|ing)? the `([a-z0-9]+(?:-[a-z0-9]+)*)` skill `` over the body after the frontmatter ("loading" is needed for wayfinder L78; "load each skill the `## Notes` block names" at L124 must not match). If an earlier ticket already added a plugin-wide load-target check, extend its expected table with these three rows instead of adding the file.
- **Tracker text this ticket relies on (setup-matt-pocock-skills ticket, D14, D15, D16).** T04 keeps wayfinder L17, L21, L25, L42, L44, L52, L65, L67, L69, L101, L113, L123, L125, L128 and implement-spec L9, L11, L13, L15, L23, L27, L38 verbatim. That is correct only if setup's seed `references/issue-tracker-local.md` (copied by setup to `docs/agents/issue-tracker.md`) carries: the heading "Wayfinding operations" verbatim (wayfinder L25 finds the section by that name) with the lead-in "Used by wayfinder." in place of upstream L23 "Used by `/wayfinder`."; a `# <title>` heading opening every map and ticket file (wayfinder L17 refers by name, L44 indexes `[<closed ticket title>]`); "closed" meaning any terminal Status, `resolved` or `out-of-scope`, with a ticket unblocked when every blocker is closed (wayfinder L42, L44, L52, L69, L101, L124, L125; implement-spec L11, L13, L38); implementation tickets set `resolved` when merged, rewriting to-tickets' bold `**Status:**` line in place (implement-spec L11 and L38, and the resume rule of the new L17 paragraph); absolute main-checkout paths for every spec, ticket or map pointer handed to a subagent or worktree (implement-spec L15 and L27, wayfinder L115); research subagents writing only their own ticket file while a single session appends to `map.md` (wayfinder L115 with L125). The plugin always rule `mattpocock-skills-tracker` (D15) is what makes "The issue tracker should have been provided to you" true (wayfinder L25, implement-spec L9) and what keeps implement L15 "Commit your work to the current branch." from staging `.scratch/`. If those land after T04, T04's text is still final; only the default flow is incomplete until then.
- **Inbound references.** None of the three ids is renamed or dropped, so no other skill needs a T04-driven edit. ask-matt's router labels (`/implement` at L24, L26, L28, L36, L44, L52; `/implement-spec` at L25, L28; `/wayfinder` at L50, L84) keep `/name` (D17); ask-matt's own ticket handles its `/code-review`, `/prototype`, `/triage` and `/clear` text, and its L25 summary of implement-spec ("runs implementer subagents across the ready frontier in parallel") must stay consistent with the L17 fallback added here. The upstream bucket README and the forge seed templates that also mention these skills are not shipped (D10, D14).
- **Audit edits dropped by decisions.** (a) Stripping the slash from "tell the user to run `/setup-matt-pocock-skills`" at wayfinder L25 and implement-spec L9: D17 keeps it, so both lines stay verbatim. (b) Rewriting implement-spec's description to "the to-spec and to-tickets skills": D17. (c) "Load both X and Y": replaced by D18.1's two-loads wording. (d) Linking or copying `references/issue-tracker-local.md` into wayfinder: D10 ships only a skill's own files; the tracker text reaches wayfinder through the tracker doc and the always rule. (e) An allowlist entry for implement L11: it names no command (D30 two-way check). (f) "main" to "the default branch" at implement-spec L25 and a hedge at L38: no decision forces them (the draft PR at L38 exists only through the hedged L25 path). (g) Resolving research tickets inline while charting: D18.4.
- **Ambiguities resolved.** (1) wayfinder L120 "or path" is not named line by line in the decisions; it follows from D13 and D14 (the default and only shipped tracker identifies a map by a file path). If review rejects it, delete wayfinder change 8 and its ATTRIBUTIONS bullet; nothing else depends on it. (2) The wayfinder L77 fallback says a session working through the map resolves research tickets itself and charting never does, matching L116 ("it hand-resolves nothing") and D18.4; L105 already allows several research tickets per session. (3) implement-spec stops at a merge boundary "when your context is getting full", the option the D18.5 decision adopted (Q32.8); it does not force a stop after every ticket. A resumed run detects progress from the merges on the integration branch (and, on local markdown, from tickets already `resolved` per D16). (4) The fallback paragraph is inserted after L17, not appended to that line, so L17 stays byte-identical. (5) L124 "whichever skills" became "each skill" to say one load per skill (D18.1).
- **Not applicable to T04.** D20 (nothing is opened), D21 (no file names GLOSSARY.md or GLOSSARY-MAP.md; checked; domain-modeling, which wayfinder loads, carries the fallback in its own ticket), D22-D26 (no scripts, report, teach, handoff, retro or writing-for-agents text), D27 (implement L11's "typechecking" is not a TypeScript, Jest or JS-frontend example; nothing to record), D28. No URL to remove: "URL"/"URLs" at wayfinder L17, L80 and L120 are plain words, L44's `(link)` placeholder sits inside a fenced block, and L65 and L71 are fragment links (`#ticket-types`, `#work-through-the-map`) whose headings stay unchanged. No imposed tool to remove; `research/<name>` (L115), the integration branch and worktrees are git.
- **Gate facts.** After the changes no "Skill tool" remains (wayfinder had 7: L77, L78, L79, L111, L115 and two at L124; implement-spec had 2: L29, L36). The labels `wayfinder:map` (L21, L113) and `wayfinder:<type>` (L65) are tracker labels, not coupling markers (D30 lists only `mattpocock-skills:`). No skill here mentions a `references/` or `scripts/` path. The three descriptions are 197 (wayfinder), 60 (implement) and 57 (implement-spec) characters, unchanged, for the listing-budget test.
- **README and spec (D19, D33).** The plugin README lists all three among the user-invoked-only skills that only Claude Code enforces through `disable-model-invocation`; implement commits to the current branch by itself, so outside Claude Code the guard line is what keeps it from firing on ordinary implementation requests. All three depend on the skills-first F6 keeping `disable-model-invocation`.
- **Formatting.** D32 excludes the plugin markdown from ruff, so keep upstream's bytes (LF endings, one trailing newline). Added text has no em-dashes (upstream CLAUDE.md L25 rule).

### A.T05.1 tdd (upstream skills/engineering/tdd; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/tdd/SKILL.md` (38 lines, LF, ends with a newline, UTF-8 with four U+2192 arrows at L8, L32 and L38) | `catalog/plugins/mattpocock_skills/skills/tdd/SKILL.md` | Vendored content, synced as `.agents/skills/tdd/SKILL.md` (D12). Changes 1 and 3-6 are the only edits; the file grows to 39 lines (the `id` line). |
  | `skills/engineering/tdd/tests.md` (77 lines, LF, ASCII, sha256 `859f9e592c188fda4fc7277dd180e4ce9c7a2e13f6efe1f6f29eccc9d28c106a`) | `catalog/plugins/mattpocock_skills/skills/tdd/references/tests.md` | Moved, bytes unchanged (change 2). Its TypeScript/Jest examples stay verbatim (change 7). |
  | `skills/engineering/tdd/mocking.md` (59 lines, LF, ASCII, sha256 `3ceb807fdf4a47d6a93d4d9a891e5ba6d362a6247bd08adc451feebfc17361ef`) | `catalog/plugins/mattpocock_skills/skills/tdd/references/mocking.md` | Moved, bytes unchanged (change 2). Its TypeScript examples stay verbatim (change 7). |
  | `skills/engineering/tdd/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata: `interface.display_name` "TDD", `interface.short_description` "Test-driven red-green-refactor". There is no `policy` key, because the skill is model-invoked. Goes under Dropped (change 8). |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/tdd/references/LICENSE` | Byte-identical copy of the plugin-root LICENSE (sha256 `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5`) (change 9). |

  After the changes the plugin skill directory holds exactly `SKILL.md`, `references/LICENSE`, `references/mocking.md` and `references/tests.md`.

- **Frontmatter** (plugin source, in this order):

  ```yaml
  ---
  id: tdd
  name: tdd
  description: Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions "red-green-refactor", or wants integration tests.
  ---
  ```

  `id` is added as the first key (D11). `name` and `description` are byte-identical to upstream L2-L3. The description stays an unquoted plain scalar (149 characters). There is no `disable-model-invocation`, and none may be added: tdd is model-invoked and must stay so, because implement (upstream L9) and implement-spec (upstream L29) load it. D19 therefore does not apply. Insert the `id:` line as text; do not load and re-dump the YAML.

- **Changes**:

  1. **`.agents/skills/tdd/SKILL.md`, frontmatter, before upstream L2 (D11).** Upstream "name: tdd". Insert the line `id: tdd` directly above it, so it is the first key and the new L2.

  2. **`.agents/skills/tdd/references/tests.md` and `.agents/skills/tdd/references/mocking.md` (D10).** Upstream "tests.md" and "mocking.md" sit at the skill root. Move both under `references/` with their bytes unchanged. Neither file links back to SKILL.md or to each other, so nothing inside them is rewritten.

  3. **SKILL.md L10 (D21).** Upstream "read `GLOSSARY.md` (if it exists) so test names". A pure insertion directly after the code span `` `GLOSSARY.md` ``: insert `` (or `CONTEXT.md` if the repo already has one)``. Upstream's own "(if it exists)" stays, so the two parentheticals stand side by side, as in T01's wait-what. Resulting line:

     ```text
     When exploring the codebase, read `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) (if it exists) so test names and interface vocabulary match the project's domain language, and respect ADRs in the area you're touching.
     ```

  4. **SKILL.md L16 (D10).** Upstream "See [tests.md](tests.md) for examples and [mocking.md](mocking.md)". The link targets point at the moved files. The link texts are plain names, not code-formatted paths, so they stay. Resulting line:

     ```text
     See [tests.md](references/tests.md) for examples and [mocking.md](references/mocking.md) for mocking guidelines.
     ```

  5. **SKILL.md L26 (D17).** Upstream "call the Skill tool with "codebase-design" for the vocabulary." Replace exactly that substring with "load the `codebase-design` skill for the vocabulary." Nothing else on the line changes: the parenthetical "(how deep the module is, where the seam belongs, what the interface should expose)" before it and the sentence "It is the shared source of the module, interface, depth, seam, adapter, leverage and locality terms, and it is a reference to consult, not a session to run." after it stay. The edit also clears the only D30 Claude-only-name hit in T05 ("Skill tool"). The target, codebase-design, is model-invoked.

  6. **SKILL.md L38 (D8).** Upstream "(see the `code-review` skill)". Replace the code span `` `code-review` `` with `` `two-axis-review` ``. This is a prose mention with the plain name (D17), not a load. Resulting line:

     ```text
     - **Refactoring is not part of the loop.** It belongs to the review stage (see the `two-axis-review` skill), not the red → green implementation cycle.
     ```

  7. **Stack assumption recorded (D27).** There is no text change; ATTRIBUTIONS records the TypeScript/Jest examples as a stack assumption and keeps them verbatim. They are: SKILL.md L31 "`expect(add(a, b)).toBe(a + b)`"; `references/tests.md` fences L7-L15, L29-L36, L47-L61 and L65-L77 ("const mockPayment = jest.mock(paymentService);" at L32); `references/mocking.md` fences L24-L35 and L41-L53 (`process.env.STRIPE_KEY` at L32, `fetch` at L44-L46 and L51).

  8. **`agents/openai.yaml`, whole file (D10).** Upstream "display_name: "TDD"". Not shipped; it goes under Dropped in ATTRIBUTIONS.

  9. **`.agents/skills/tdd/references/LICENSE`, new file (D4).** A byte-identical copy of the plugin-root LICENSE, the upstream MIT notice "Copyright (c) 2026 Matt Pocock". The plugin-wide "License copies added" bullet may cover it.

- **Project-toolchain allowlist**: none. None of the three shipped files has a denylisted name, and no ambiguous word (open, start, bash, sh, node, bun, pnpm) appears anywhere in them, not even in prose. `jest.mock` (tests.md L32), `expect(...)` (SKILL.md L31), `fetch` and `process.env` (mocking.md) are example code and are not on the D30 denylist. The audit listed tests.md L32 and SKILL.md L31 as toolchain mentions; an entry for either would fail D30's two-way check as stale.

- **Skill-specific tests**: none beyond the shared gate except one row in the plugin-wide load-target table (the shape of T04's `tests/plugins/mattpocock_skills/test_execution_skill_loads.py`): the load targets extracted from tdd's SKILL.md are exactly {`codebase-design`}. T04's regex `` [Ll]oad(?:s|ing)? the `([a-z0-9]+(?:-[a-z0-9]+)*)` skill `` matches the new L26 text. Add the row to that table, or create the table if T04 has not landed. The shared gate already covers the rest: its references/ resolve check covers the L16 links (and fails on a leftover `(tests.md)` target); the Claude-only-name denial covers L26; the rename-propagation check of A.T05.2 covers L38. If the plugin keeps a superpowers-style expected reference-file set, it lists `tdd/references/LICENSE`, `tdd/references/mocking.md` and `tdd/references/tests.md`.

- **Continue degradation**: with the `continue` adapter listed, `.continue/prompts/tdd.md` carries only id, name, description and the SKILL.md body. `references/tests.md` and `references/mocking.md` do not travel, so the L16 links are dead. The `codebase-design` load, and the inbound loads from implement and implement-spec, resolve only where the Continue IDE also reads the skills natively from `.claude/skills`. As a user-started prompt, tdd is no longer picked up from its description, and no `references/LICENSE` copy travels (D29).

### A.T05.2 two-axis-review (upstream skills/engineering/code-review; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/code-review/SKILL.md` (87 lines, LF, ends with a newline, UTF-8 with fifteen U+2192 arrows at L43, L45-L56, L84 and L85) | `catalog/plugins/mattpocock_skills/skills/two-axis-review/SKILL.md` | The directory is renamed to the new id (change 1). Synced as `.agents/skills/two-axis-review/SKILL.md` (D12). Changes 1-4 are the only edits; the file grows to 90 lines (the `id` line, plus the step-4 paragraph and its blank line). |
  | `skills/engineering/code-review/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata: `interface.display_name` "Code Review", `interface.short_description` "Review a diff on standards and spec". There is no `policy` key, and the display name would be stale after the rename anyway. Goes under Dropped (change 5). |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/two-axis-review/references/LICENSE` | Byte-identical copy of the plugin-root LICENSE (change 6). |

  After the changes the plugin skill directory holds exactly `SKILL.md` and `references/LICENSE`.

- **Frontmatter** (plugin source, in this order):

  ```yaml
  ---
  id: two-axis-review
  name: two-axis-review
  description: "Review the changes since a fixed point (commit, branch, tag, or merge-base) along two axes: Standards (does the code follow this repo's documented coding standards?) and Spec (does the code match what the originating issue/spec asked for?). Runs both reviews in parallel sub-agents and reports them side by side. Use when the user wants to review a branch, a PR, work-in-progress changes, or asks to \"review since X\"."
  ---
  ```

  `id` is added as the first key (D11). `name` changes from `code-review` to `two-axis-review` (D8). The agent_harness adapter and Continue's degraded prompt read `name` from the source, so `name` must equal the id. `description` is byte-identical to upstream L3, including its double quotes and the two `\"` escapes. D28 keeps it verbatim on purpose: it is 419 characters between the quotes and 417 once parsed, and bundled plugins are exempt from the 300-character lint. The description's "Runs both reviews in parallel sub-agents" describes the skill rather than instructing, so it gets no qualifier. There is no `disable-model-invocation`, and none may be added: implement and implement-spec (both user-invoked) load this skill. D19 therefore does not apply.

- **Changes**:

  1. **Directory, and `.agents/skills/two-axis-review/SKILL.md` L2 (D8).** Upstream directory `skills/engineering/code-review/` and "name: code-review". The plugin directory is `skills/two-axis-review/`, and L2 becomes `name: two-axis-review`. ATTRIBUTIONS bullet (renames): code-review became two-axis-review because the id collides with Claude Code's bundled `code-review` skill, and every inbound reference names the new id. Those references are: tdd SKILL.md L38 (A.T05.1 change 6); implement SKILL.md L13 and implement-spec SKILL.md L36 (T04 changes 4 and 6); ask-matt SKILL.md L28 (three `/code-review` labels) and L32 (one label), which belong to ask-matt's ticket.

  2. **SKILL.md, frontmatter, before upstream L2 (D11).** Insert the line `id: two-axis-review` directly above the `name` line, so it is the first key.

  3. **SKILL.md L11 (D17, D18.6).** Upstream "Both axes run as **parallel sub-agents** so they don't pollute each other's context". The line becomes a capability with an inline fallback. Replace the whole line with:

     ```text
     If your harness can run subagents, both axes run as **parallel sub-agents** so they don't pollute each other's context, then this skill aggregates their findings; otherwise you run the two reviews yourself, one after the other, as step 4 describes, and aggregate them the same way.
     ```

  4. **SKILL.md, after upstream L59 (D17, D18.6).** Upstream L58 "### 4. Spawn both sub-agents in parallel" stays unchanged, and so does the blank L59 under it. After L59 insert the paragraph below, followed by one blank line, so that it sits directly above upstream L60 "**Standards sub-agent prompt** should include:".

     ```text
     If your harness cannot run subagents, run the two reviews yourself, one after the other. First run the Standards review from the Standards brief below, judged only against the standards sources and the smell baseline from step 3, with any spec contents step 2 fetched set aside, and write its report in full. Then run the Spec review from the Spec brief below; if no spec is available, skip it and report "no spec available". Do not revise the Standards report afterwards.
     ```

     This paragraph is the inline equivalent of every sub-agent sentence in the skill, so the following stay verbatim: L23 ("not inside two parallel sub-agents"), L32 ("the **Spec** sub-agent will skip and report "no spec available""), L60, L63 ("the sub-agent has no other access to it"), L66 and L72 ("skip the Spec sub-agent and note this in the final report"). Step 2 is not changed: per D18.6, the spec it fetched is set aside, not deferred.

  5. **`agents/openai.yaml`, whole file (D10).** Upstream "display_name: "Code Review"". Not shipped; it goes under Dropped in ATTRIBUTIONS.

  6. **`.agents/skills/two-axis-review/references/LICENSE`, new file (D4).** A byte-identical copy of the plugin-root LICENSE. The plugin-wide "License copies added" bullet may cover it.

- **Project-toolchain allowlist**: none. The git commands at L21 (`git diff <fixed-point>...HEAD`, `git log <fixed-point>..HEAD --oneline`) and L23 (`git rev-parse <fixed-point>`) are allowed by D2 and are not on the denylist. "GitLab `!67`" at L29 is a product name, not glab. No ambiguous word appears in command position, or anywhere at all.

- **Skill-specific tests**: put these in `tests/plugins/mattpocock_skills/test_review_skills.py`, or next to T04's load-target table.
  - **Identity and invocation.** id == name == directory == `two-axis-review`. The frontmatter has no `disable-model-invocation` key; assert the same for tdd, since both are load targets of user-invoked skills.
  - **D18.6 replay guard.** L11's line starts with "If your harness can run subagents". The `### 4.` section contains "If your harness cannot run subagents", "set aside", "no spec available" and "Do not revise the Standards report afterwards".
  - **Verbatim keeps.** The body still contains "GitLab `!67`" (D18.7) and "tell the user to run `/setup-matt-pocock-skills`" (D17).
  - **Load-target row.** The load targets are the empty set.
  - **Rename propagation.** Parametrize over the skills present. No file under the plugin's `skills/` matches `(?<![\w-])code-review(?![\w-])`. That pattern catches `code-review` and `/code-review`, and it ignores names such as `requesting-code-review`. Scope the check to `skills/`, because README.md and ATTRIBUTIONS.md legitimately name the old id and Claude Code's bundled skill.
  - **Description bound.** If the plugin copies superpowers' bounded-description test, its upper bound must admit 417 characters (D28).

- **Continue degradation**: with the `continue` adapter listed, `.continue/prompts/two-axis-review.md` carries only id, name, description and the SKILL.md body, and no `references/LICENSE` travels. As a user-started prompt it is no longer picked up from its description. The loads from implement and implement-spec resolve only where the Continue IDE also reads the skill natively from `.claude/skills`. Where subagents are unavailable, the step-4 sequential fallback is the only path (D29).

### A.T05.3 pr-body (upstream skills/engineering/pr; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/pr/SKILL.md` (170 lines, LF, ends with a newline, UTF-8 with box-drawing characters at L76-L78 and L110-L116) | `catalog/plugins/mattpocock_skills/skills/pr-body/SKILL.md` | The directory is renamed to the new id (change 1). Synced as `.agents/skills/pr-body/SKILL.md` (D12). Changes 1-4 are the only edits. The file stays 170 lines (the `id` line is added and the `url` line is removed). Keep the leading space on the diff context lines in L98-L141. |
  | `skills/engineering/pr/CREDITS.md` (3 lines, LF, ASCII) | `catalog/plugins/mattpocock_skills/skills/pr-body/references/CREDITS.md` | Moved (change 5). URLs are removed and the rename is applied (changes 6-7). No file links to it. |
  | `skills/engineering/pr/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata: `interface.display_name` "PR", `interface.short_description` "Write a PR body that's fast to review". There is no `policy` key. Goes under Dropped (change 11). |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/pr-body/references/LICENSE` | Byte-identical copy of the plugin-root LICENSE (change 12). |
  | (none; third-party notice added) | `catalog/plugins/mattpocock_skills/skills/pr-body/references/LICENSE-show-me` | HumanLayer's MIT notice for the show-me content (change 8, D6). It is deliberately not identical to the plugin-root LICENSE. |

  After the changes the plugin skill directory holds exactly `SKILL.md`, `references/CREDITS.md`, `references/LICENSE` and `references/LICENSE-show-me`. No `CREDITS.md` remains at the skill root.

- **Frontmatter** (plugin source, in this order):

  ```yaml
  ---
  id: pr-body
  name: pr-body
  description: "Use when writing a PR body."
  metadata:
    credits:
      skill: show-me
      author: Dex Horthy
      organisation: Humanlayer
  ---
  ```

  `id` is added as the first key (D11). `name` changes from `pr` to `pr-body` (D8). `description` is byte-identical to upstream L3, double quotes included (27 characters). The `metadata.credits` block keeps upstream L4-L8 byte for byte, including upstream's spelling "Humanlayer", while upstream L9 (its `url` key) is deleted (D6, D11). There is no `disable-model-invocation`: the skill is model-invoked, so D19 does not apply. Remove the line and insert `id` as text edits; do not re-dump the YAML.

- **Changes**:

  1. **Directory, and `.agents/skills/pr-body/SKILL.md` L2 (D8).** Upstream directory `skills/engineering/pr/` and "name: pr". The plugin directory is `skills/pr-body/`, and L2 becomes `name: pr-body`. ATTRIBUTIONS bullet (renames): pr became pr-body because Claude Code registers a feature-gated bundled `pr` skill, and every inbound reference names the new id. Those references are: `references/CREDITS.md` L3 (change 7), and ask-matt SKILL.md L30 "**`/pr`** shapes the body", a router label that keeps its slash and becomes "**`/pr-body`**" (D17) in ask-matt's ticket.

  2. **SKILL.md, frontmatter, before upstream L2 (D11).** Insert the line `id: pr-body` directly above the `name` line, so it is the first key.

  3. **SKILL.md L9, frontmatter (D6, D11, D4).** Upstream "    url: "<web address>"": the `metadata.credits.url` key, whose value is the only URL in SKILL.md and points at show-me's SKILL.md in the humanlayer/skills repository. Delete the whole line. L4-L8 stay byte for byte, so the block now ends with `    organisation: Humanlayer` and the closing `---` follows.

  4. **SKILL.md L37 (D21).** Upstream "Use the user's domain language from `GLOSSARY.md`." A pure insertion directly after the code span. Resulting line:

     ```text
     Skip all preambles and keep prose brief. Use the user's domain language from `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one).
     ```

  5. **`.agents/skills/pr-body/references/CREDITS.md` (D6, D10).** Upstream `CREDITS.md` at the skill root moves under `references/`. Nothing links to it, so no link is rewritten. L1-L2 stay byte for byte; L3 changes only as changes 6 and 7 say.

  6. **references/CREDITS.md L3, URLs removed (D6, D4).** Upstream "come from [Dex Horthy](…)'s [`show-me`](…) skill". The two targets are the author's profile page and the humanlayer/humanlayer repository, both on the forge. Each link keeps only its link text: replace `[Dex Horthy](…)` with `Dex Horthy`, and `` [`show-me`](…) `` with `` `show-me` ``. The phrase becomes "come from Dex Horthy's `show-me` skill".

  7. **references/CREDITS.md L3, rename (D8).** Upstream "`pr` does not depend on `show-me` as a skill". Replace the code span `` `pr` `` (the only one on the line) with `` `pr-body` ``. Nothing else on L3 changes. That includes the parenthetical "it isn't part of this repo, and a hard dependency would break standalone installs", which no decision forces.

  8. **`.agents/skills/pr-body/references/LICENSE-show-me`, new file (D6).** This is HumanLayer's MIT notice. Write it as plain text, laid out exactly like the plugin-root LICENSE:
     - line 1 `MIT License`;
     - line 2 blank;
     - line 3 `Copyright (c) 2026 HumanLayer`;
     - lines 4-21 identical to lines 4-21 of the plugin-root LICENSE, which hold the MIT permission notice and the warranty disclaimer.

     End the file with LF line endings and one trailing newline. Add no provenance header and no URL. If a reviewed copy of the LICENSE file of humanlayer/skills at commit 653b6411c1f70c275a18e37673b042ff99f67ceb is available, its bytes win.

  9. **Third-party content record (D6).** This is an ATTRIBUTIONS record, not a text change. Record it in pr-body's own ATTRIBUTIONS section, or confirm that T01's global "Third-party content" section already states it; T10 folds any difference in. Proposed bullet: "`.agents/skills/pr-body/SKILL.md`'s Summary section (upstream `skills/engineering/pr/SKILL.md` L39-L156: the menu of visuals and its Guidance) reproduces, almost word for word, the show-me skill by Dex Horthy (HumanLayer): repository humanlayer/skills, commit 653b6411c1f70c275a18e37673b042ff99f67ceb, MIT, Copyright (c) 2026 HumanLayer. It ships as upstream v1.3.1 had it, minus the URL removals listed above, and is not authored by Matt Pocock. HumanLayer's MIT notice ships as `.agents/skills/pr-body/references/LICENSE-show-me`; the credit ships as `references/CREDITS.md` and the `metadata.credits` frontmatter block. The agent_harness adapter moves `metadata` into its manifest sidecar, and Continue's degraded prompts carry neither `metadata` nor `references/`, so a repository that renders this skill only for Continue must keep both notices itself."

  10. **Stack assumption recorded (D27).** There is no text change; ATTRIBUTIONS records the TSX/JSX and frontend examples as a stack assumption and keeps them verbatim. They are: L63-L70 (the component tree with `apps/example/src/routes/session.tsx`), L95-L104 (the JSX component diff), L111 (`show-me.ts`), L143-L150 (the `ts` fence) and L170 ("layout shift, breakages for consumers, mobile responsiveness").

  11. **`agents/openai.yaml`, whole file (D10).** Upstream "display_name: "PR"". Not shipped; it goes under Dropped in ATTRIBUTIONS.

  12. **`.agents/skills/pr-body/references/LICENSE`, new file (D4).** A byte-identical copy of the plugin-root LICENSE. The plugin-wide "License copies added" bullet may cover it.

- **Project-toolchain allowlist**: none. The `mermaid` fence at L83, "Mermaid" at L81 and "Mermaid" at CREDITS.md L3 are markup that the forge renders inside a PR body, not a CDN asset. D30 denies only CDN host names and "via CDN", so these need no entry. The audit's toolchain mentions at L21 ("<screenshot/output/failing test run>") and L164 ("Test results, console output") name no tool; listing them would fail the two-way check as stale. After change 3 no URL remains.

- **Skill-specific tests**: put these in `tests/plugins/mattpocock_skills/test_review_skills.py`.
  - **Layout.** The pr-body reference files are exactly {`CREDITS.md`, `LICENSE`, `LICENSE-show-me`}, and no `CREDITS.md` exists at the skill root.
  - **Third-party notice.** After whitespace normalization, `references/LICENSE-show-me` contains "Copyright (c) 2026 HumanLayer" and "The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software." The shared byte-identity check must target `references/LICENSE` exactly, never every `LICENSE*` file.
  - **Frontmatter.** id == name == directory == `pr-body`. The parsed `metadata` equals {"credits": {"skill": "show-me", "author": "Dex Horthy", "organisation": "Humanlayer"}}, with no `url` key.
  - **Attribution.** ATTRIBUTIONS.md has a "Third-party content" section that names humanlayer/skills, `653b6411c1f70c275a18e37673b042ff99f67ceb` and `LICENSE-show-me`.
  - **Load-target row.** The load targets are the empty set.
  - **Rename propagation.** Parametrize over the skills present. No file under the plugin's `skills/` contains the code span `` `pr` `` or `` `/pr` ``. The only kept upstream `` `pr` `` outside this skill, in the GitLab seed, is dropped by D14.

- **Continue degradation**: with the `continue` adapter listed, `.continue/prompts/pr-body.md` carries only id, name, description and the SKILL.md body. The `metadata.credits` block, `references/CREDITS.md`, `references/LICENSE-show-me` and `references/LICENSE` are all dropped, so neither the HumanLayer notice nor the Matt Pocock notice travels. As a user-started prompt, the model no longer reaches for it on its own whenever it writes a PR (D29).

**Ticket T05 notes.**

- **Numbering and order.** "Upstream order" follows T04's reading: it is the `skills` list of upstream's Claude Code plugin manifest (`.claude-plugin/plugin.json`, not shipped), which has tdd at L28, code-review at L38 and pr at L39. The bucket README (L29, L32, L33) has the same order; the task brief listed code-review, pr, tdd. Work order inside the ticket:
  1. Create the two renamed directories first, because the folder name equals the id (D8).
  2. Insert the `id` lines and fix the `name` lines.
  3. Move tdd's two files and pr's CREDITS.md.
  4. Make the text edits.

  tdd change 6 needs two-axis-review's new id, and both are in this ticket.
- **Line numbers.** Every L-number is an upstream v1.3.1 line, confirmed against the checkout: tdd SKILL.md 38 lines, tests.md 77, mocking.md 59; code-review SKILL.md 87; pr SKILL.md 170, CREDITS.md 3; each openai.yaml 3. In the plugin copies, lines shift as follows:
  - tdd: upstream L2 onward moves down by 1.
  - two-axis-review: upstream L2 onward moves down by 1, and lines after upstream L59 move down by 2 more.
  - pr-body: L2-L8 move down by 1, and from upstream L10 on there is no net shift.

  ATTRIBUTIONS cites the upstream numbers.
- **Cross-ticket inbound references.** These are not T05 edits; they are listed so that each owning ticket checks them.
  - T04 already writes "load the `two-axis-review` skill" at implement L13 and implement-spec L36, and the tdd loads at implement L9 and implement-spec L29.
  - ask-matt's ticket changes L28 (three `/code-review` labels) and L32 (one label) to `/two-axis-review`, and L30 "**`/pr`**" to "**`/pr-body`**". Router labels keep the slash (D17).
  - ask-matt's `/tdd` labels (three at L28, one at L65) stay, because tdd is not renamed.
  - The upstream bucket README (L16, L17, L29, L32, L33) also names these ids, but it is not shipped (D10).
  - No other upstream skill names code-review, pr or tdd; checked by grep over skills/engineering and skills/productivity.
- **Invocation contract.** tdd and two-axis-review are load targets of the user-invoked implement and implement-spec, so neither may gain `disable-model-invocation`. pr-body has no inbound load; ask-matt L30's claim that it is model-invoked must stay true. tdd's own load target, codebase-design, is model-invoked upstream and must stay so in its ticket. T04's load-target test checks targets against the D9 ids and the 15 user-invoked ids, not against present directories, so T05 can land before or after codebase-design's ticket. The D19 gate must leave these three skills alone: none of them carries the guard line.
- **Audit edits dropped by decisions.** Do not apply the following.
  - (a) code-review L3 description qualifier ("where the harness supports them"): D28 keeps the description verbatim.
  - (b) Stripping the slash from "tell the user to run `/setup-matt-pocock-skills`" at code-review L13: D17 keeps it. The rest of L13 is verbatim too, since the plugin always rule `mattpocock-skills-tracker` (D15) now makes "The issue tracker should have been provided to you" true.
  - (c) Replacing "GitLab `!67`" at L29: D18.7 keeps it.
  - (d) The audit's step-4 wording "before reading the spec": replaced by D18.6's "set aside", since step 2 has already fetched the spec.
  - (e) The audit's "NO CHANGE" at pr L37 and "None" at tdd L10: D21 applies to both.
  - (f) The audit's toolchain mentions at pr L21 and L164, tdd SKILL.md L31 and tests.md L32: they are not allowlist entries.
- **Ambiguities resolved.**
  - (1) D16 at two-axis-review L69 ("The path or fetched contents of the spec."). The line is left verbatim, consistent with T04. The rule to use an absolute main-checkout path when a `.scratch/` spec or ticket pointer is handed to a subagent lives in setup's seed `references/issue-tracker-local.md`, which setup copies to `docs/agents/issue-tracker.md`. two-axis-review reads that file at L13 and L29. If the setup ticket's seed lacks that clause, add it there, not here.
  - (2) D21 rendering follows T01 note 4. It is a pure insertion right after the `GLOSSARY.md` code span, with `CONTEXT.md` code-formatted too. At tdd L10 this stacks two parentheticals, which is accepted, so that one grep for "if the repo already has one" finds every fallback.
  - (3) D6's "e.g." is settled as `references/LICENSE-show-me`.
  - (4) D28's "419-char" is the raw length between the YAML quotes; the parsed value is 417 characters.
  - (5) The ATTRIBUTIONS heading for change 9 is "Third-party content", as D6 names it. Do not copy superpowers' heading wording.
- **HumanLayer facts.** The upstream checkout holds no HumanLayer LICENSE, so the notice is built from D6's facts (change 8).
  - The frontmatter keeps upstream's spelling "Humanlayer" (D11). The notice and ATTRIBUTIONS use "HumanLayer" (D6).
  - Upstream CREDITS.md linked the humanlayer/humanlayer repository, while the deleted frontmatter `url` named humanlayer/skills. Removing the URLs leaves only the link text, and ATTRIBUTIONS names humanlayer/skills at commit 653b6411c1f70c275a18e37673b042ff99f67ceb, as D6 settles.
  - At sync, the native SkillWriter re-dumps the frontmatter with yaml.safe_dump. `metadata` survives, though its quoting may change; agent_harness moves it to its manifest sidecar. ATTRIBUTIONS states both, as superpowers' ATTRIBUTIONS does for LICENSE.
  - D30's layout rule allows any file inside `references/`, so `LICENSE-show-me` and `CREDITS.md` pass it. Only `references/LICENSE` is checked for byte identity.
- **Not applicable to T05.**
  - D19 (all three skills are model-invoked).
  - D20 (nothing is opened; pr L162's screenshots are already conditional on the environment).
  - D13 and D14 (two-axis-review already fetches through the tracker abstraction and names no forge CLI).
  - D18.1-D18.5.
  - D22-D26 (no script, report, teach, handoff, retro or writing-for-agents text).
- **Gate facts.**
  - URLs exist only at pr SKILL.md L9 and CREDITS.md L3: three in total, all removed.
  - "Skill tool" appears once, at tdd L26, and is removed.
  - No coupling marker appears anywhere. `/setup-matt-pocock-skills` does not match `mattpocock-skills:`.
  - No ambiguous denylist word appears anywhere in the six shipped upstream-derived files, so T05 adds no allowlist entry.
  - The only `references/` paths mentioned are tdd L16's two links. Consumer paths such as `docs/agents/issue-tracker.md`, `.scratch/`, `docs/`, `specs/` and pr's `apps/example/src/routes/session.tsx` are not plugin paths, and no domain-plus-path pattern appears in them.
  - The descriptions total 149 + 417 + 27 = 593 characters for the D30 listing-budget test.
- **README (D33).** The plugin README's coexistence notes cover these pairs:
  - tdd vs superpowers' test-driven-development, and vs core python-testing;
  - two-axis-review vs superpowers' requesting-code-review and receiving-code-review, and vs the core review and review-architecture prompts.

  Claude Code's bundled `code-review` still competes on routing, because the description stays verbatim. Its bundled `pr` is feature-gated. The README ticket owns that text.
- **Formatting.** D32's ruff extend-exclude covers these markdown files. Keep upstream's bytes: LF endings, one trailing newline, the U+2192 arrows, pr's box-drawing trees, and the leading-space context lines of pr's `diff` fences. The added text (tdd L10 and L26, two-axis-review L11 and the step-4 paragraph, pr L37) has no em-dashes, following upstream's house rule.

### A.T06.1 improve-codebase-architecture (upstream skills/engineering/improve-codebase-architecture; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/improve-codebase-architecture/SKILL.md` (71 lines, 6,000 bytes, LF, ends with a newline, no trailing whitespace, UTF-8 with one U+2026 ellipsis at L56) | `catalog/plugins/mattpocock_skills/skills/improve-codebase-architecture/SKILL.md` | Vendored content. Changes 1-16 are the only edits. The file grows to 74 lines: upstream line N becomes plugin line N+1 for N = 2..6 and N+3 for N >= 7. Keep the L56 ellipsis and every other byte as upstream has it. |
  | `skills/engineering/improve-codebase-architecture/HTML-REPORT.md` (123 lines, 6,641 bytes, LF, ends with a newline, UTF-8 with U+2264 at L52, three U+00B7 at L112, U+2026 at L123) | `catalog/plugins/mattpocock_skills/skills/improve-codebase-architecture/references/HTML-REPORT.md` | Moved under `references/` (D10) and edited by changes 17-34 (D23, plus three D17 slash drops). The result is 163 lines. The three non-ASCII lines (now L86, L152, L163) keep their characters. |
  | `skills/engineering/improve-codebase-architecture/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata (D10): `display_name: "Improve Codebase Architecture"`, `short_description: "Find and grill architecture improvements"`, `policy: allow_implicit_invocation: false`. It goes under Dropped (change 36). |
  | upstream repository-root `LICENSE` (sha256 `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5`), through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/improve-codebase-architecture/references/LICENSE` | A byte-identical copy of the plugin-root LICENSE (D4), checked by the D30 layout gate (change 35). |

  Upstream has no `scripts/` and no `references/` for this skill. The plugin skill directory therefore holds exactly `SKILL.md`, `references/HTML-REPORT.md` and `references/LICENSE`.

- **Frontmatter** (plugin source, in this order):
  1. `id: improve-codebase-architecture`: added as the first key (D11). It equals the directory name and `name`.
  2. `name: improve-codebase-architecture`: verbatim (upstream L2).
  3. `description:`: upstream L3 value verbatim, an unquoted plain scalar of 125 characters. It contains no `/name`, so D17 leaves it alone.
  4. `disable-model-invocation: true`: verbatim (upstream L4). D19 requires that the skills-first spec's F6 (non-standard key stripping) keeps it.

  Nothing else is added: no `playbook:` block (D11), no `argument-hint`, no `metadata`. Insert the `id:` line as text. Do not load and re-dump the YAML.

- **Changes** (ATTRIBUTIONS paths use the shared skill root, D12):
  1. `.agents/skills/improve-codebase-architecture/SKILL.md`, frontmatter, before upstream L2 ``name: improve-codebase-architecture``: insert the line `id: improve-codebase-architecture` as the first key, so it becomes the new L2. (D11; the plugin-wide "Frontmatter" bullet may cover this.)
  2. `.agents/skills/improve-codebase-architecture/SKILL.md`, body, above the H1. Upstream L6 is the blank line after the closing `---` and L7 is ``# Improve Codebase Architecture``. Insert, between L6 and L7, this exact line followed by one blank line:

     ```text
     Run this only when the user asked for it by name; otherwise stop.
     ```

     Result: L7 blank (upstream L6), L8 the guard line, L9 blank, L10 `# Improve Codebase Architecture` (upstream L7). It is the first line of body content, above the H1, as section 7.6 (G15) fixes and as A.T03 and A.T09 do for the other user-invoked skills with an H1. The engine's sentinel goes above it at sync and is not written in the source. (D19)
  3. `SKILL.md` L13, ``- Call the Skill tool with "codebase-design" for the architecture vocabulary``. Replace the prefix ``- Call the Skill tool with "codebase-design" for`` with ``- Load the `codebase-design` skill for``. The rest of the bullet (from ``the architecture vocabulary (**module**,`` to ``or "boundary."``) stays verbatim. (D17)
  4. `SKILL.md` L14, ``The domain language in `GLOSSARY.md` gives names to good seams``. After the `GLOSSARY.md` code span, insert `` (or `CONTEXT.md` if the repo already has one)``. The line becomes:

     ```markdown
     - The domain language in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) gives names to good seams; ADRs in `docs/adr/` record decisions this command should not re-litigate.
     ```
     (D21)
  5. `SKILL.md` L25, ``Read the project's domain glossary (`GLOSSARY.md`) and any ADRs``. Make the same insertion inside the existing parentheses. The line becomes:

     ```markdown
     Read the project's domain glossary (`GLOSSARY.md` (or `CONTEXT.md` if the repo already has one)) and any ADRs in the area you're touching first.
     ```
     (D21; the doubled closing parenthesis is intended, see note 3.)
  6. `SKILL.md` L27, ``Then spawn a sub-agent to walk the codebase.``. The line becomes:

     ```markdown
     Then, if your harness can run subagents, spawn a sub-agent to walk the codebase; otherwise walk it yourself. Don't follow rigid heuristics; explore organically and note where you experience friction:
     ```
     (D17)
  7. `SKILL.md` L39, ``Open it for the user (`xdg-open <path>` on Linux, `open <path>` on macOS, `start <path>` on Windows) and tell them the absolute path.``. Replace that last sentence with ``Open it for the user if your harness can open files, and tell them the absolute path either way.``. The two sentences before it (the temp-dir write and the `$TMPDIR` / `/tmp` / `%TEMP%` resolution) stay verbatim. (D20, D23; the three openers are imposed tools under D2)
  8. `SKILL.md` L41, ``The report uses **Tailwind via CDN** for layout and styling, and **Mermaid via CDN** for diagrams``. Replace the whole line with:

     ```markdown
     The report is self-contained: **one inline `<style>` block** for layout and styling, and **hand-built divs and inline SVG** for every diagram; it loads nothing from the network. Draw graph-shaped relationships (call graphs, dependencies, sequences) as inline-SVG boxes and arrows, and use hand-built divs/SVG when you want something more editorial (mass diagrams, cross-sections, collapse animations). Each candidate gets a **before/after visualisation**. Be visual.
     ```

     The tail from ``(mass diagrams, cross-sections, collapse animations)`` on is upstream's. (D23; CDN assets are imposed tools under D2)
  9. `SKILL.md` L54, ``**Use GLOSSARY.md vocabulary for the domain`` and ``If `GLOSSARY.md` defines "Order,"``. Both mentions get the fallback. The first is plain text inside bold, so the insertion is plain text too. The second is a code span. (Change 10 also edits this line.) The line becomes:

     ```markdown
     **Use GLOSSARY.md (or CONTEXT.md if the repo already has one) vocabulary for the domain, and the `codebase-design` vocabulary for the architecture.** If `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) defines "Order," talk about "the Order intake module," not "the FooBarHandler," and not "the Order service."
     ```
     (D21)
  10. `SKILL.md` L54, ``the `/codebase-design` vocabulary for the architecture``: drop the slash, giving ``the `codebase-design` vocabulary``, as shown in change 9. This is agent-facing prose, not a router label, a "tell the user to run" line or a description. (D17)
  11. `SKILL.md` L58, ``See [HTML-REPORT.md](HTML-REPORT.md)``. The link target becomes `references/HTML-REPORT.md`, giving ``See [HTML-REPORT.md](references/HTML-REPORT.md) for the full HTML scaffold, diagram patterns, and styling guidance.``. The link text stays plain `HTML-REPORT.md`. (D10)
  12. `SKILL.md` L64, ``call the Skill tool with "grilling" to walk the decision tree``. Replace ``call the Skill tool with "grilling"`` with ``load the `grilling` skill``. The rest stays verbatim. (D17)
  13. `SKILL.md` L66, ``call the Skill tool with "domain-modeling" to keep the domain model current``. Replace ``call the Skill tool with "domain-modeling"`` with ``load the `domain-modeling` skill``. The rest stays verbatim. These are two separate loads in two sentences already, so D18.1 needs no further edit. (D17)
  14. `SKILL.md` L68, ``not in `GLOSSARY.md`?** Add the term to `GLOSSARY.md`.``. Both code spans get the fallback. The line becomes:

      ```markdown
      - **Naming a deepened module after a concept not in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one)?** Add the term to `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one). Create the file lazily if it doesn't exist.
      ```
      (D21)
  15. `SKILL.md` L69, ``Update `GLOSSARY.md` right there.``. The line becomes ``- **Sharpening a fuzzy term during the conversation?** Update `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) right there.``. (D21)
  16. `SKILL.md` L71, ``Call the Skill tool with "codebase-design" and use its design-it-twice parallel sub-agent pattern.``. Replace ``Call the Skill tool with "codebase-design"`` with ``Load the `codebase-design` skill``. ``and use its design-it-twice parallel sub-agent pattern.`` stays verbatim: the pattern carries its own subagent fallback (A.T06.3 change 7). (D17)
  17. `skills/engineering/improve-codebase-architecture/HTML-REPORT.md` moved to `.agents/skills/improve-codebase-architecture/references/HTML-REPORT.md`. Its only inbound link is SKILL.md L58 (change 11). (D10; the plugin-wide "Restructure" bullet may cover this.)
  18. `references/HTML-REPORT.md` L3, ``Tailwind and Mermaid both come from CDNs. Mermaid handles graph-shaped diagrams reliably;``. The first sentence (``The architectural review is rendered as a single self-contained HTML file in the OS temp directory.``) stays. Replace the rest of the line so that it reads:

      ```markdown
      The architectural review is rendered as a single self-contained HTML file in the OS temp directory. Nothing loads from the network: one inline `<style>` block does the styling, and hand-built divs and inline SVG draw every diagram, the graph-shaped ones (call graphs, dependencies, sequences) as well as the more editorial visuals (mass diagrams, cross-sections). Mix the patterns below: don't lean on one for everything, it'll start to look generic.
      ```
      (D23)
  19. `references/HTML-REPORT.md` L13-L17: delete five lines. They are the Tailwind script tag (L13, ``<script src=`` with a scheme URL on the host cdn.tailwindcss.com) and the whole Mermaid module script (L14 ``<script type="module">``, L15 ``import mermaid from`` with a scheme URL on the host cdn.jsdelivr.net for mermaid@11's ESM build, L16 ``mermaid.initialize({ startOnLoad: true, theme: "neutral", securityLevel: "loose" });``, L17 ``</script>``). This removes both URLs and both CDN assets. (D4, D23, D30)
  20. `references/HTML-REPORT.md` `<style>` block (upstream L18-L24) becomes the report's whole stylesheet:
      - L19, ``/* small custom layer for things Tailwind doesn't cover cleanly:``, becomes ``      /* the report's only stylesheet: page, cards, badges, labels, diagram parts,``. L20 (``dashed seam lines, hand-drawn-feeling arrow heads, etc. */``) stays verbatim.
      - After L20, insert the 30 rule lines from ``body {`` to ``.head-leak, .leak-label { fill: #dc2626; }`` exactly as in the result block below.
      - L21-L23 (`.seam`, `.leak`, `.deep`) stay verbatim and in place, after the inserted rules. Equal-specificity `.leak` must come after `.box` and `.edge` to win the stroke, and `.deep` must come after `.module` to win the background.
      - After L23, insert the 3 lines ``.module.deep { ... }``, ``svg .deep { ... }`` and ``svg .on-deep { ... }``. `.deep` keeps its gradient for div boxes. `svg .deep` gives an SVG box the dark fill and the thick dark stroke, because `background` does not paint an SVG `<rect>`.

      (D23)
  21. `references/HTML-REPORT.md` body skeleton:
      - L26, ``<body class="bg-stone-50 text-slate-900 font-sans">``, becomes ``  <body>``. The `body` rule carries stone-50 `#fafaf9`, slate-900 `#0f172a` and a sans stack.
      - Directly after it, insert the six-line hidden marker sheet ``<svg class="defs" aria-hidden="true">`` ... ``</svg>`` exactly as below.
      - L27, ``<main class="max-w-5xl mx-auto px-6 py-12 space-y-12">``, becomes ``    <main>``. The `main` rule gives 64rem max width, auto margins, 3rem/1.5rem padding and a 3rem gap.
      - L29, ``<section id="candidates" class="space-y-10">...</section>``, becomes ``      <section id="candidates">...</section>``. `#candidates` gets a 2.5rem gap, and `#candidates > article` styles each card.
      - L28 and L30-L33 stay verbatim. `#top-recommendation` is styled by its id, so L30 keeps no class.

      (D23)

      Result of changes 19-21. Upstream L7-L34 (the scaffold fence) must read exactly as follows. No `xmlns` attribute appears anywhere, and `{{repo name}}` stays verbatim:

      ````markdown
      ```html
      <!doctype html>
      <html lang="en">
        <head>
          <meta charset="utf-8" />
          <title>Architecture review for {{repo name}}</title>
          <style>
            /* the report's only stylesheet: page, cards, badges, labels, diagram parts,
               dashed seam lines, hand-drawn-feeling arrow heads, etc. */
            body { margin: 0; background: #fafaf9; color: #0f172a; font-family: system-ui, sans-serif; line-height: 1.5; }
            main { max-width: 64rem; margin: 0 auto; padding: 3rem 1.5rem; display: flex; flex-direction: column; gap: 3rem; }
            #candidates { display: flex; flex-direction: column; gap: 2.5rem; }
            #candidates > article { display: flex; flex-direction: column; gap: 1rem; background: #fff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1.5rem; }
            #top-recommendation { background: #fff; border: 2px solid #cbd5e1; border-radius: 0.5rem; padding: 2rem; font-size: 1.125rem; }
            .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem; }
            .badges { display: flex; flex-wrap: wrap; gap: 0.5rem; }
            .badge { border-radius: 999px; padding: 0.125rem 0.625rem; font-size: 0.75rem; font-weight: 600; }
            .badge-strong { background: #d1fae5; color: #065f46; }
            .badge-exploring { background: #fef3c7; color: #92400e; }
            .badge-speculative { background: #e2e8f0; color: #334155; }
            .tag { border: 1px solid #cbd5e1; color: #475569; }
            .mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.875rem; }
            .adr { background: #fffbeb; border: 1px solid #fcd34d; border-radius: 0.375rem; padding: 0.5rem 0.75rem; }
            .before-after { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
            .diagram { position: relative; height: 320px; }
            svg { display: block; width: 100%; height: auto; }
            .diagram > svg { position: absolute; inset: 0; height: 100%; }
            .defs { position: absolute; width: 0; height: 0; }
            .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
            .module { background: #fff; border: 1px solid #334155; border-radius: 0.25rem; padding: 0.5rem; }
            .faded { opacity: 0.4; }
            .band { display: flex; align-items: center; height: 3rem; margin-bottom: 0.25rem; padding-left: 0.75rem; background: #f1f5f9; border-left: 4px solid #334155; }
            .band.thick { height: 9rem; border-left-width: 12px; }
            svg text { font-size: 12px; fill: #0f172a; text-anchor: middle; dominant-baseline: middle; }
            .box { fill: #fff; stroke: #334155; stroke-width: 1.5; }
            .edge { fill: none; stroke: #334155; stroke-width: 1.5; }
            .lifeline { stroke: #cbd5e1; stroke-width: 1; }
            .head { fill: #334155; }
            .head-leak, .leak-label { fill: #dc2626; }
            .seam { stroke-dasharray: 4 4; }
            .leak { stroke: #dc2626; }
            .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
            .module.deep { border: 4px solid #0f172a; color: #f8fafc; }
            svg .deep { fill: #1e293b; stroke: #0f172a; stroke-width: 4; }
            svg .on-deep { fill: #f8fafc; }
          </style>
        </head>
        <body>
          <svg class="defs" aria-hidden="true">
            <defs>
              <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="head" d="M0 0L10 5L0 10z" /></marker>
              <marker id="arrow-leak" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="head-leak" d="M0 0L10 5L0 10z" /></marker>
            </defs>
          </svg>
          <main>
            <header>...</header>
            <section id="candidates">...</section>
            <section id="top-recommendation">...</section>
          </main>
        </body>
      </html>
      ```
      ````

      In the plugin file, the fence and its lines start at column 0, as upstream's do. The extra indentation above belongs only to this list.

      Selector list, in order (the D23 "semantic classes"): `body`, `main`, `#candidates`, `#candidates > article`, `#top-recommendation`, `.card`, `.badges`, `.badge`, `.badge-strong`, `.badge-exploring`, `.badge-speculative`, `.tag`, `.mono`, `.adr`, `.before-after`, `.diagram`, `svg`, `.diagram > svg`, `.defs`, `.label`, `.module`, `.faded`, `.band`, `.band.thick`, `svg text`, `.box`, `.edge`, `.lifeline`, `.head`, `.head-leak`, `.leak-label`, `.seam`, `.leak`, `.deep`, `.module.deep`, `svg .deep`, `svg .on-deep`. Marker ids: `arrow`, `arrow-leak`.

      How each former Tailwind or Mermaid construct is drawn now. This table is implementer guidance and is not shipped. Only the plugin text listed in these changes is shipped.

      | Upstream construct (HTML-REPORT line) | Replacement |
      |---|---|
      | Tailwind script tag (L13), Mermaid ESM import and `mermaid.initialize` (L14-L17) | Deleted. No script of any kind remains. |
      | `bg-stone-50 text-slate-900 font-sans` on `<body>` (L26) | The `body` rule: `#fafaf9` background, `#0f172a` text, `system-ui, sans-serif`. |
      | `max-w-5xl mx-auto px-6 py-12 space-y-12` on `<main>` (L27) | The `main` rule: 64rem max width, centred, 3rem/1.5rem padding, flex column with a 3rem gap. |
      | `space-y-10` on `#candidates` (L29) | The `#candidates` rule (flex column, 2.5rem gap). Each `<article>` card is styled by `#candidates > article`. |
      | Card wrapper `rounded-lg border border-slate-200 bg-white p-4` (L66) | `<div class="card">`. |
      | Mermaid `flowchart LR` nodes `A[OrderHandler]` and the rest (L68-L71) | `<rect class="box">` and `<text class="label">` pairs inside an inline `<svg viewBox>`. |
      | Mermaid edges `-->` | `<line class="edge" ... marker-end="url(#arrow)">` (or a `<path class="edge">` for bends). |
      | Mermaid `-.leak.->` edge plus `classDef leak` on C and D (L71-L73) | A solid `<line class="edge leak" ... marker-end="url(#arrow-leak)">` and a `<text class="leak-label">`. The two modules on that edge get `class="box leak"` (red outline), which mirrors `class C,D leak`. Leak edges are never dashed: dashed means seam (legend, L38). |
      | Mermaid classDef "deep module dark" (L63) | SVG: `<rect class="box deep">` (dark fill, 4px dark stroke) with `<text class="label on-deep">`. Div: `<div class="module deep">` (verbatim gradient, 4px border, light text). |
      | Mermaid sequence diagram (L63) | One vertical `<line class="lifeline">` per module, plus one horizontal `<line class="edge" marker-end="url(#arrow)">` per call, stacked top to bottom. |
      | Seam (legend L38, `.seam` L21) | `<line class="edge seam">` (dashed) drawn across the module boundary. |
      | `font-mono text-sm` (L48) | `.mono`. |
      | Badge colours emerald, amber, slate (L47) | `<span class="badge badge-strong">`, `badge-exploring`, `badge-speculative` inside `<div class="badges">`. The dependency category tag is `<span class="badge tag">`. L47's colour words stay verbatim. |
      | ADR callout "amber-tinted box" (L53) | `<p class="adr">`. L53 stays verbatim. |
      | Before / After two columns, about 320px (L49, L98) | `<div class="before-after">` holding two `<div class="diagram">` (320px tall). |
      | Hand-built boxes-and-arrows (L80) | `.module` divs placed with inline `style="position: absolute; left: ...; top: ...; width: ..."` inside a `.diagram`, plus one `.diagram > svg` overlay carrying `.edge` lines. The "after" view is one `.module.deep` with `.module.faded` internals. |
      | Cross-section `h-12 border-l-4` (L84) | A stack of `.band` divs. The "after" view is one `.band.thick`. |
      | Mass diagram (L88) | Two SVG `.box` rects per module (interface above implementation). The deep "after" implementation rect gets `.deep`. |
      | Call-graph collapse (L92) | Nested `.module` divs. The "after" view is one `.module.deep` containing the same boxes as `.module.faded`. |
      | `font-serif` (L96) | The prose names a `Georgia, serif` stack. The scaffold has no heading rule, because serif stays optional. |
      | `text-xs uppercase tracking-wider` (L99) | `.label` (0.75rem, uppercase, 0.05em letter-spacing), on divs and on SVG `<text>`. |
      | Header legend (L38, verbatim) | Drawn with the same classes: `.box`, `.edge.seam`, `.edge.leak` plus `#arrow-leak`, and `.box.deep`. |
      | Top recommendation, "one larger card" (L104) | The `#top-recommendation` rule (2px border, 2rem padding, larger type). |

  22. `references/HTML-REPORT.md` L42, ``(from the `/codebase-design` skill)``, becomes ``(from the `codebase-design` skill)``. This is agent-facing prose. (D17)
  23. `references/HTML-REPORT.md` L48, ``- **Files**: monospaced list, `font-mono text-sm`.``, becomes ``- **Files**: monospaced list in small type (`.mono`: a monospace stack at 0.875rem).``. (D23)
  24. `references/HTML-REPORT.md` L61, ``### Mermaid graph (the workhorse for dependencies / call flow)``, becomes ``### Inline-SVG graph (the workhorse for dependencies / call flow)``. (D23)
  25. `references/HTML-REPORT.md` L63, ``Use a Mermaid `flowchart` or `graph` when the point is``. Replace the whole line with:

      ```markdown
      Draw an inline-SVG graph (`.box` rectangles joined by `.edge` lines that end in the `#arrow` marker) when the point is "X calls Y calls Z, and look at the mess." Wrap it in a `.card` so it doesn't feel parachuted in. Use the stylesheet's classes to colour leakage edges red (`.leak` with the `#arrow-leak` marker: a solid red arrow) and the deep module dark (`.deep`, which also fills an SVG box). Sequence diagrams work well for "before: 6 round-trips; after: 1." (one vertical `.lifeline` per module, one horizontal `.edge` arrow per call).
      ```
      (D23)
  26. `references/HTML-REPORT.md` L66-L75 (the Tailwind card `<div class="rounded-lg border border-slate-200 bg-white p-4">` and the ``<pre class="mermaid">`` flowchart inside it). Replace those ten lines with the following, keeping L65 ```` ```html ```` and L76 ```` ``` ```` fences as they are. The `<svg>` has no `xmlns` attribute, which inline HTML5 SVG does not need and which would trip the D30 URL gate:

      ```html
      <div class="card">
        <svg viewBox="0 0 670 90" role="img" aria-label="OrderHandler calls OrderValidator calls OrderRepo, which leaks into PricingClient">
          <rect class="box" x="10" y="30" width="140" height="40" />
          <text class="label" x="80" y="50">OrderHandler</text>
          <rect class="box" x="180" y="30" width="140" height="40" />
          <text class="label" x="250" y="50">OrderValidator</text>
          <rect class="box leak" x="350" y="30" width="140" height="40" />
          <text class="label" x="420" y="50">OrderRepo</text>
          <rect class="box leak" x="520" y="30" width="140" height="40" />
          <text class="label" x="590" y="50">PricingClient</text>
          <line class="edge" x1="150" y1="50" x2="178" y2="50" marker-end="url(#arrow)" />
          <line class="edge" x1="320" y1="50" x2="348" y2="50" marker-end="url(#arrow)" />
          <line class="edge leak" x1="490" y1="50" x2="518" y2="50" marker-end="url(#arrow-leak)" />
          <text class="leak-label" x="504" y="18">leak</text>
        </svg>
      </div>
      ```
      The example has 16 lines and is written at column 0 inside the fence, as upstream's was. (D23, D30)
  27. `references/HTML-REPORT.md` L78, ``### Hand-built boxes-and-arrows (when Mermaid's layout fights you)``, becomes ``### Hand-built boxes-and-arrows (when the deep module needs visual weight)``. Both patterns are hand-drawn now, so the parenthetical names the purpose. (D23)
  28. `references/HTML-REPORT.md` L80, ``since Mermaid won't render that with the right weight.``, becomes ``since an SVG graph of equal boxes won't render that with the right weight.``. The rest of L80 stays verbatim. (D23)
  29. `references/HTML-REPORT.md` L84, ``Stack horizontal bands (`h-12 border-l-4`) to show layers a call passes through.``. The line becomes:

      ```markdown
      Stack horizontal bands (`.band`: 3rem tall with a thick left border) to show layers a call passes through. Before: 6 thin layers each doing nothing. After: 1 thick band (`.band.thick`) labelled with the consolidated responsibility.
      ```
      (D23)
  30. `references/HTML-REPORT.md` L96, ``(`font-serif` works well with stone/slate)``, becomes ``(a `Georgia, serif` stack works well with stone/slate)``. The rest of the bullet stays verbatim. (D23)
  31. `references/HTML-REPORT.md` L99, ``- Use `text-xs uppercase tracking-wider` for module labels inside diagrams``. Replace ``- Use `text-xs uppercase tracking-wider` for`` with ``- Use the `.label` class (0.75rem, uppercase, 0.05em letter-spacing) for``. ``module labels inside diagrams, so they read as schematic, not as UI.`` stays verbatim. (D23)
  32. `references/HTML-REPORT.md` L100, ``- The only scripts are the Tailwind CDN and the Mermaid ESM import.``. Replace the whole bullet with ``- No scripts and no network: no external stylesheets, fonts or images, only the inline `<style>` block and inline SVG. The report is static: no app code, no interactivity.``. (D23)
  33. `references/HTML-REPORT.md` L108, ``come straight from the `/codebase-design` skill.``, becomes ``come straight from the `codebase-design` skill.``. (D17)
  34. `references/HTML-REPORT.md` L123, ``If a term isn't in the `/codebase-design` glossary``, becomes ``If a term isn't in the `codebase-design` glossary``. The U+2026 earlier in the line stays. (D17)
  35. `.agents/skills/improve-codebase-architecture/references/LICENSE`: added. It is a byte-identical copy of the plugin-root LICENSE, the upstream MIT notice "Copyright (c) 2026 Matt Pocock". (D4; the plugin-wide "License copies added" bullet may cover this.)
  36. Dropped `skills/engineering/improve-codebase-architecture/agents/openai.yaml`. It carried `display_name`, `short_description` and `policy: allow_implicit_invocation: false`. Codex reads the shared skill root and so loses this skill's user-only invocation policy. What remains is `disable-model-invocation`, which only Claude Code honours, and the change 2 guard line. (D10, D19)
  37. Dropped (record this in the skill's own ATTRIBUTIONS section, or confirm that T01's global "Dropped and why" section already states it; T10 folds any difference in): the report's two CDN assets, Tailwind and Mermaid ESM (hosts cdn.tailwindcss.com and cdn.jsdelivr.net), and the three OS opener commands `xdg-open`, `open` and `start`. The report is now offline-only inline CSS plus inline SVG. Opening it depends on the harness's file-opening capability, and the absolute path is always given. A stdlib `webbrowser` fallback was considered and rejected under D20. The reason recorded is that it can launch a blocking console browser on headless Linux when `TERM` is set, and that it shells out to `osascript` on macOS. A run-time file URL would leave no literal in the plugin, so the URL gate is not the reason. (D2, D20, D23)

- **Project-toolchain allowlist**: none. After the changes, no line of this skill has a D30 denylist hit. `git log --oneline` (SKILL.md L23) is git, which D2 allows and which is not on the denylist.

- **Skill-specific tests**: add `tests/plugins/mattpocock_skills/test_architecture_report.py` (stdlib only, headless). It reads `catalog/plugins/mattpocock_skills/skills/improve-codebase-architecture/references/HTML-REPORT.md` and extracts every fenced ```` ```html ```` block. There must be exactly 2: the scaffold, which starts with `<!doctype html>`, and the graph example.
  1. `test_report_snippets_load_nothing`: no block contains `<script`, `<link`, `@import`, `src=` or `xmlns`.
  2. `test_report_classes_are_defined`: strip `/* */` comments and `{...}` declaration bodies from the scaffold's `<style>` text, then collect `\.([A-Za-z][\w-]*)` as the defined classes. Assert that every token of every `class="..."` attribute in both blocks is defined. Also assert that every class named in a prose code span that starts with `.` is defined (`.box`, `.edge`, `.card`, `.leak`, `.deep`, `.lifeline`, `.band`, `.band.thick`, `.mono`, `.label`). This guards the D23 option-2 risk of unstyled classes.
  3. `test_report_marker_ids_resolve`: every `url(#x)` in the blocks and every `` `#x` `` prose code span (`#arrow`, `#arrow-leak`) matches an `id="x"` in the scaffold.
  4. `test_report_html_is_balanced`: an `html.parser.HTMLParser` subclass keeps a tag stack. Its `handle_startendtag` must be overridden to do nothing, or `<meta ... />` produces a false mismatch. `meta` is skipped as a void element. Both blocks must end with an empty stack and no mismatch.
  5. `test_no_tailwind_mermaid_or_cdn_left`: no file under the skill directory matches `(?i)tailwind|mermaid|\bcdn\b`. This is a re-pin regression guard. It is scoped to this skill, because throwaway-prototype's UI.md L51 "TailwindCSS" is legitimate.
  6. `test_opener_is_capability_phrased`: `SKILL.md` contains the exact D20 sentence "Open it for the user if your harness can open files, and tell them the absolute path either way."

- **Continue degradation**: With the `continue` adapter listed, the skill becomes `.continue/prompts/improve-codebase-architecture.md`. It holds only the SKILL.md body, guard line included, and a user-started prompt satisfies the guard. `references/HTML-REPORT.md` (the scaffold, the class list, the diagram patterns and the tone rules) and `references/LICENSE` do not travel, and the L58 link dangles. The report is then built from SKILL.md's card list and the L41 self-contained rule alone. The three "Load the `X` skill" steps (codebase-design, grilling, domain-modeling) cannot load anything. Opening the report falls back to telling the user the absolute path. The Continue IDE reading `.claude/skills` natively loses nothing. (D29)

### A.T06.2 throwaway-prototype (upstream skills/engineering/prototype; layout-only keep; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/prototype/SKILL.md` (26 lines, 2,931 bytes, LF, ends with a newline, no trailing whitespace, UTF-8 with four U+2192 arrows at L14, L15 and L17 (two)) | `catalog/plugins/mattpocock_skills/skills/throwaway-prototype/SKILL.md` | Vendored content in the renamed directory (D8). Changes 1-4 are the only edits, so the file grows to 27 lines: upstream line N becomes plugin line N+1 for N >= 2. The H1 `# Prototype` (L6) stays: it is a title, not the id. |
  | `skills/engineering/prototype/LOGIC.md` (67 lines, 6,036 bytes, ASCII) | `catalog/plugins/mattpocock_skills/skills/throwaway-prototype/references/LOGIC.md` | Moved (D10). Change 6 is its only edit. L14's link to `UI.md` stays valid because both files land in `references/`. L54 stays verbatim (D20). |
  | `skills/engineering/prototype/UI.md` (112 lines, 6,913 bytes, UTF-8 with U+2190 and U+2192 at L88) | `catalog/plugins/mattpocock_skills/skills/throwaway-prototype/references/UI.md` | Moved (D10). Change 7 is its only edit. L5's link to `LOGIC.md` stays valid. The `prototype` word in L28 and the `/prototype/<name>` route in L75 stay (D8). |
  | `skills/engineering/prototype/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata (D10): `display_name: "Prototype"`, `short_description: "Prototype to answer a design question"`, and no `policy` block. It goes under Dropped (change 9). |
  | upstream repository-root `LICENSE`, through the plugin-root copy | `catalog/plugins/mattpocock_skills/skills/throwaway-prototype/references/LICENSE` | A byte-identical copy (D4, change 8). |

  The plugin skill directory holds exactly `SKILL.md`, `references/LOGIC.md`, `references/UI.md` and `references/LICENSE`.

- **Frontmatter** (plugin source, in this order):
  1. `id: throwaway-prototype`: added as the first key (D11). It equals the directory name and `name`.
  2. `name: throwaway-prototype`: changed from upstream L2 `name: prototype` (D8). The SkillWriter forces `name` to the id anyway, but agent_harness and Continue read `name` from source, so the source must say it.
  3. `description:`: upstream L3 value verbatim, an unquoted plain scalar of 179 characters (``Build a throwaway prototype to answer a design question. Use when ...``).

  There is no `disable-model-invocation`: the skill is model-invoked and must stay so, because wayfinder loads it (change 11). No `playbook:` block (D11). Insert and edit as text, with no YAML re-dump.

- **Changes**:
  1. Renamed `prototype` to `throwaway-prototype` to avoid Claude Code's feature-gated bundled `prototype` skill. The source directory `skills/engineering/prototype/` becomes `catalog/plugins/mattpocock_skills/skills/throwaway-prototype/` (synced as `.agents/skills/throwaway-prototype/`), and `SKILL.md` L2 ``name: prototype`` becomes ``name: throwaway-prototype``. ATTRIBUTIONS lists this under the renames. (D8)
  2. `.agents/skills/throwaway-prototype/SKILL.md`, frontmatter, before L2: insert ``id: throwaway-prototype`` as the first key. (D11)
  3. `SKILL.md` L14, ``→ [LOGIC.md](LOGIC.md).``: the link target becomes `references/LOGIC.md`, giving ``→ [LOGIC.md](references/LOGIC.md).``. The rest of the line, including the U+2192 arrow, stays verbatim. (D10)
  4. `SKILL.md` L15, ``→ [UI.md](UI.md).``: the target becomes `references/UI.md`, giving ``→ [UI.md](references/UI.md).``. (D10)
  5. `skills/engineering/prototype/LOGIC.md` and `UI.md` moved to `.agents/skills/throwaway-prototype/references/LOGIC.md` and `references/UI.md`. Their links to each other (LOGIC.md L14 ``[UI.md](UI.md)``, UI.md L5 ``[LOGIC.md](LOGIC.md)``) need no rewrite. (D10; the plugin-wide "Restructure" bullet may cover this.)
  6. `references/LOGIC.md` L58, ``the way the [SKILL](SKILL.md) describes``: the target becomes `../SKILL.md`, giving ``the way the [SKILL](../SKILL.md) describes``. (D10)
  7. `references/UI.md` L100, ``the way the [SKILL](SKILL.md) describes``: the target becomes `../SKILL.md`, giving ``the way the [SKILL](../SKILL.md) describes``. (D10)
  8. `.agents/skills/throwaway-prototype/references/LICENSE`: added as a byte-identical copy of the plugin-root LICENSE. (D4)
  9. Dropped `skills/engineering/prototype/agents/openai.yaml` (display name and short description only). Codex loses only its display metadata, because the file has no invocation policy. (D10)
  10. Recorded as a stack assumption, with no text change. The JS-frontend examples stay verbatim: UI.md L60-L71 (the `tsx` switcher, labelled ``// pseudo-code, adapt to the project's framework``), L87 (``router.replace`` on Next, ``navigate`` on React Router), L90 (``process.env.NODE_ENV !== 'production'``), and UI.md L51's styling-system list ``(TailwindCSS, shadcn, MUI, plain CSS, whatever)``. SKILL.md L22's task-runner examples are project toolchain (see the allowlist). (D27)
  11. Inbound, owned by wayfinder's ticket and listed here so that the rename is complete: `.agents/skills/wayfinder/SKILL.md` L78, ``by calling the Skill tool with "prototype".``, becomes ``by loading the `throwaway-prototype` skill.``. The bold ticket-type label ``**Prototype** (HITL)`` at the start of the bullet, L65's `wayfinder:<type>` value `prototype`, L80's "prototype" and the seed `issue-tracker-local.md` L26 ``Type:`` value `prototype` are ticket-type names. They stay. (D8, D17)
  12. Inbound, owned by ask-matt's ticket: `.agents/skills/ask-matt/SKILL.md` L20, ``- **`/prototype`** to answer the question with throwaway code,``, becomes ``- **`/throwaway-prototype`** to answer the question with throwaway code,``. This is a router label, so the slash stays (D17). L18's "detour through a prototype" is a noun and stays. (D8, D17)
  13. Inbound, owned by ask-matt's ticket: `.agents/skills/ask-matt/SKILL.md` L85, ``- **`/prototype`** is a small, throwaway program``, becomes ``- **`/throwaway-prototype`** is a small, throwaway program``. The git branch name ``a `prototype/<name>` branch out of main`` later in the same line stays. (D8, D17)

- **Project-toolchain allowlist** (per-file, two-way checked):
  - `skills/throwaway-prototype/SKILL.md`: `` `pnpm <name>` `` (plugin L23, upstream L22: "A UI prototype starts from one command in the project's task runner").
  - `skills/throwaway-prototype/SKILL.md`: `` `bun <path>` `` (the same line).

  Do not add entries for `` `python <path>` `` (L22; python is not denied), UI.md L51 "TailwindCSS" (D30 bans CDN host names, not the word), LOGIC.md L54 "open it for them" (prose, not command position) or UI.md L90 ``process.env.NODE_ENV`` (its first word is not `node`). Each would be a stale entry that fails the two-way check.

- **Skill-specific tests**:
  1. `tests/plugins/mattpocock_skills/test_renamed_skills.py::test_renamed_id_has_no_inbound_references`, parametrized over `(old, new)` pairs. T06 adds `("prototype", "throwaway-prototype")`. The two-axis-review and pr-body tickets add theirs. Across `skills/**/*.md`, no line may match `` `/prototype` `` (a backticked slash label that ends right after the id), `` `prototype` skill ``, or `Skill tool with "prototype"`. This must still allow UI.md L75's `` `/prototype/<name>` `` route, UI.md L28's `` `prototype` in the path``, ask-matt L85's `` `prototype/<name>` `` branch and wayfinder's `prototype` ticket type. The test also asserts that `skills/prototype/` does not exist and that `skills/throwaway-prototype/SKILL.md` exists. Until wayfinder and ask-matt land, the reference check passes vacuously, and from then on it guards their rewrites.
  2. The relative-link test specified under A.T06.3 also covers this skill's six links (SKILL.md L14 and L15, LOGIC.md L14 and L58, UI.md L5 and L100).

- **Continue degradation**: With the `continue` adapter listed, `.continue/prompts/throwaway-prototype.md` holds only the 21-line router body: the branch picker and the six shared rules. `references/LOGIC.md` and `references/UI.md`, which hold the whole process for both branches, do not travel, the L14/L15 links dangle and no LICENSE copy travels. As a prompt, the skill is no longer model-invoked, so wayfinder's load cannot reach it. Of the three skills, this one loses the most. D29 accepts it and the README documents it. The Continue IDE reading `.claude/skills` natively loses nothing.

### A.T06.3 codebase-design (upstream skills/engineering/codebase-design; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/codebase-design/SKILL.md` (114 lines, 6,446 bytes, LF, ends with a newline, no trailing whitespace, UTF-8: box-drawing characters and U+2190 arrows in the two diagrams at L35-L41 and L47-L51) | `catalog/plugins/mattpocock_skills/skills/codebase-design/SKILL.md` | Vendored content. Changes 1, 3 and 4 are its only edits, so the file grows to 115 lines (upstream N becomes N+1 for N >= 2). The box-drawing diagrams stay byte-identical. |
  | `skills/engineering/codebase-design/DEEPENING.md` (37 lines, 2,553 bytes, ASCII) | `catalog/plugins/mattpocock_skills/skills/codebase-design/references/DEEPENING.md` | Moved (D10). Change 5 is its only edit. |
  | `skills/engineering/codebase-design/DESIGN-IT-TWICE.md` (44 lines, 2,665 bytes, UTF-8 with one U+2013 en dash at L25, "1–3") | `catalog/plugins/mattpocock_skills/skills/codebase-design/references/DESIGN-IT-TWICE.md` | Moved (D10). Changes 6-9 are its only edits, and the line count stays 44. Its three links to `DEEPENING.md` (L14, L23, L37) stay valid. The links go one way only: DEEPENING.md does not link back. |
  | `skills/engineering/codebase-design/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata (D10): `display_name: "Codebase Design"`, `short_description: "Vocabulary for deep-module design"`, and no policy. It goes under Dropped (change 11). |
  | upstream repository-root `LICENSE`, through the plugin-root copy | `catalog/plugins/mattpocock_skills/skills/codebase-design/references/LICENSE` | A byte-identical copy (D4, change 10). |

  The plugin skill directory holds exactly `SKILL.md`, `references/DEEPENING.md`, `references/DESIGN-IT-TWICE.md` and `references/LICENSE`.

- **Frontmatter** (plugin source, in this order):
  1. `id: codebase-design`: added as the first key (D11).
  2. `name: codebase-design`: verbatim (upstream L2).
  3. `description:`: upstream L3 value verbatim, an unquoted plain scalar of 265 characters.

  There is no `disable-model-invocation`. The skill is model-invoked, and improve-codebase-architecture (L13, L71) and tdd (L26) load it, so it must stay so. No `playbook:` block. Insert as text.

- **Changes**:
  1. `.agents/skills/codebase-design/SKILL.md`, frontmatter, before L2 ``name: codebase-design``: insert ``id: codebase-design`` as the first key. (D11)
  2. `skills/engineering/codebase-design/DEEPENING.md` and `DESIGN-IT-TWICE.md` moved to `.agents/skills/codebase-design/references/DEEPENING.md` and `references/DESIGN-IT-TWICE.md`. (D10; the plugin-wide "Restructure" bullet may cover this.)
  3. `SKILL.md` L113, ``see [DEEPENING.md](DEEPENING.md):``, becomes ``see [DEEPENING.md](references/DEEPENING.md):``. (D10)
  4. `SKILL.md` L114, ``see [DESIGN-IT-TWICE.md](DESIGN-IT-TWICE.md):``, becomes ``see [DESIGN-IT-TWICE.md](references/DESIGN-IT-TWICE.md):``. ``spin up parallel sub-agents to design the interface several radically different ways`` stays verbatim: it describes the reference, and the reference's operative step carries the fallback (change 7). (D10)
  5. `references/DEEPENING.md` L3, ``Assumes the vocabulary in [SKILL.md](SKILL.md):``, becomes ``Assumes the vocabulary in [SKILL.md](../SKILL.md):``. (D10)
  6. `references/DESIGN-IT-TWICE.md` L5, ``Uses the vocabulary in [SKILL.md](SKILL.md):``, becomes ``Uses the vocabulary in [SKILL.md](../SKILL.md):``. (D10)
  7. `references/DESIGN-IT-TWICE.md` L21, ``Spawn 3+ sub-agents in parallel. Each must produce a **radically different** interface for the deepened module.``. The line becomes:

     ```markdown
     If your harness can run subagents, spawn 3+ sub-agents in parallel; otherwise draft the 3+ designs yourself, one at a time, each held to its own brief, its own design constraint and the output list below, finishing one before you start the next. Each must produce a **radically different** interface for the deepened module.
     ```

     The fallback keeps the step's intent: independent briefs, one constraint each, the same five outputs. L3, L11, L17, the L19 heading, L23 and L32 stay verbatim. They name or describe the pattern, and this line is its only operative spawn. (D17)
  8. `references/DESIGN-IT-TWICE.md` L30, ``Include both [SKILL.md](SKILL.md) vocabulary``: the target becomes `../SKILL.md`, giving ``Include both [SKILL.md](../SKILL.md) vocabulary``. (D10)
  9. `references/DESIGN-IT-TWICE.md` L30, ``and GLOSSARY.md vocabulary in the brief``. Upstream writes the name as plain text, so insert the plain-text fallback ` (or CONTEXT.md if the repo already has one)` after `GLOSSARY.md`. With change 8 applied, the line becomes:

     ```markdown
     Include both [SKILL.md](../SKILL.md) vocabulary and GLOSSARY.md (or CONTEXT.md if the repo already has one) vocabulary in the brief so each sub-agent names things consistently with the architecture language and the project's domain language.
     ```
     (D21)
  10. `.agents/skills/codebase-design/references/LICENSE`: added as a byte-identical copy of the plugin-root LICENSE. (D4)
  11. Dropped `skills/engineering/codebase-design/agents/openai.yaml` (display name and short description only, no invocation policy). (D10)
  12. Recorded as a stack assumption, with no text change. The examples stay verbatim: SKILL.md L73-L81 and L85-L93 (the two ```` ```typescript ```` blocks, including ``new StripeGateway()`` at L79), L108 (``the TypeScript `interface` keyword``), and DEEPENING.md L15 ("PGLite for Postgres", a JS/WASM stand-in given as one example). (D27)

- **Project-toolchain allowlist**: none. No line of this skill has a D30 denylist hit. The fenced lines start with `//`, `function`, `const`, `cart.total`, `}` or box-drawing characters. None of these is a command word.

- **Skill-specific tests**: `tests/plugins/mattpocock_skills/test_markdown_links.py::test_relative_links_resolve`, parametrized over the present skills (so later tickets inherit it). Add it unless the shared gate already resolves links this way. For every `](target)` in every `SKILL.md` and `references/**/*.md`, if the target has no scheme, does not start with `#` and is not teach's `{link}` placeholder (D24), drop any `#fragment` and resolve the target against the linking file's own directory. The result must exist inside the same skill directory. The shared D30 path check only resolves `references/...` and `scripts/...` mentions from the skill root, so without this test a missed `../SKILL.md` or sibling `DEEPENING.md` link rewrite would go unnoticed. T06 brings links of both kinds. codebase-design has 8: SKILL.md L113 and L114, DEEPENING.md L3, and DESIGN-IT-TWICE.md L5, L14, L23, L30 and L37. throwaway-prototype has 6 and improve-codebase-architecture has 1 (SKILL.md L58).

- **Continue degradation**: With the `continue` adapter listed, `.continue/prompts/codebase-design.md` holds only the SKILL.md body. The glossary, the deep/shallow diagrams, the principles, the testability examples, the relationships and the rejected framings all survive. `references/DEEPENING.md` (dependency categories, seam discipline, replace-don't-layer) and `references/DESIGN-IT-TWICE.md` (the parallel-design process) do not travel, and the two "Going deeper" links dangle. As a prompt, the skill is no longer model-invoked, so the loads from improve-codebase-architecture and tdd cannot reach it. No LICENSE copy travels. (D29)

**Ticket T06 notes.** (1) Order of sections and of work. The sections follow upstream's own listing order (plugin manifest and engineering README): improve-codebase-architecture, prototype, codebase-design. This differs from the order the ticket lists the paths in. Copy each upstream file byte for byte into its plugin path first: the prototype files go into the `throwaway-prototype/` directory, and the sibling files go under `references/`. Add the three `references/LICENSE` copies from the plugin-root LICENSE that T01 creates. Only then apply the changes. The diff against upstream then equals this list. T01's ruff extend-exclude for `catalog/plugins/mattpocock_skills/**/*.md` (D32) must already be in place, or the vendored markdown gets reformatted.

(2) Guard line position. The guard goes above the H1 as the first body line (section 7.6), in its own paragraph, as in A.T03 and A.T09 (A.T06.1 change 2). The sentinel is the engine's and lands above the guard at sync. Only improve-codebase-architecture needs the guard. The other two are model-invoked.

(3) D21 form. The fallback is always inserted after the name, as the literal ` (or `CONTEXT.md` if the repo already has one)`. The fallback name is code-formatted only where upstream code-formats `GLOSSARY.md`. Two places are plain text: SKILL.md L54's first mention and DESIGN-IT-TWICE.md L30. Every mention gets the fallback, including the second mention on the same line (L54, L68), so that a single grep for "if the repo already has one" finds them all, as T01 asks. The resulting `))` at improve-codebase-architecture L25 is accepted for that reason. No T06 file names `GLOSSARY-MAP.md`.

(4) D17 slashes. All four `/codebase-design` mentions (SKILL.md L54, HTML-REPORT.md L42, L108, L123) are agent-facing prose, so they lose the slash. This is the part of the first audit that D17 keeps. None of the three skills has a human-facing `/name` (no router label, no "tell the user to run" line, no slash in a description), so no audit slash edit had to be dropped here. The kept `/name` forms are ask-matt's router labels, and they live in ask-matt's ticket (A.T06.2 changes 12-13).

(5) Subagent wording. Only the two operative spawns get the D17 fallback: improve-codebase-architecture L27 and DESIGN-IT-TWICE.md L21. Descriptive mentions stay verbatim, because the fallback sits at the step that runs. These are improve-codebase-architecture L71 "design-it-twice parallel sub-agent pattern", codebase-design SKILL.md L114, and DESIGN-IT-TWICE.md L3, L11, L17, L19, L23 and L32. The first audit's extra qualifiers at L3, L17 and L114 are not forced by any decision and were left out (D4). New prose uses "subagents" inside the capability clause and keeps upstream's "sub-agent(s)" elsewhere.

(6) The report. Every new string avoids em dashes (upstream convention) and keeps British spelling ("colour"). No new text uses the words Tailwind, Mermaid or CDN, and test 5 keeps it that way. Markers are defined once, in a zero-size `.defs` SVG at the top of `<body>`. That SVG must not be `display: none`, because Chromium drops markers referenced from a `display: none` subtree. A single sheet avoids duplicate ids across diagrams. `orient="auto"` is used because "auto-start-reverse" is unnecessary for `marker-end`. The `.seam`, `.leak` and `.deep` lines stay verbatim and come after the new base rules, because the cascade depends on that order (change 20). `{{repo name}}` (L12) is upstream's placeholder. It stays, because `references/` files are copied byte for byte by the skill writer and never rendered. Do not give the file a `.j2` suffix. The scaffold and the example were checked in memory against the upstream text: every replaced string occurs exactly once, every class and marker resolves, the HTML balances, and no URL, `xmlns`, denylist word or command-position word appears. The resulting HTML-REPORT.md is 163 lines.

(7) Cross-skill references. Outbound: improve-codebase-architecture loads codebase-design (this ticket), grilling and domain-modeling (other tickets). If the shared gate gains a "loaded skill exists" check, it must skip skills that are not yet present, or T06 must land after the grilling and domain-modeling tickets. Inbound edits that other tickets own:
- wayfinder L78: the load becomes `throwaway-prototype` (A.T06.2 change 11).
- ask-matt L20 and L85: the labels become `/throwaway-prototype`.
- tdd L26: "Load the `codebase-design` skill".
- ask-matt L48, L58, L65 and L84: router labels `/improve-codebase-architecture` and `/codebase-design`, kept with the slash.
- setup's `domain.md` L11: its agent-facing ``(reached via `/grill-with-docs` and `/improve-codebase-architecture`)`` is setup's ticket's call.

Not touched: wayfinder's `prototype` ticket type, its seed value, UI.md's `/prototype/<name>` route and ask-matt's `prototype/<name>` branch (D8). None of the three skills references a dropped (triage) or another renamed skill (two-axis-review, pr-body).

(8) Decisions checked and not applied:
- D16: prototype SKILL.md L26 ("a context pointer ... on the implementation issue") is already tracker-neutral.
- D18: none of its seven items applies. Step 3's two loads are already separate sentences.
- D20: LOGIC.md L54 "Send them the file, or open it for them." stays verbatim, as D20 says.
- D22, D24, D25, D26 and D28: not relevant to these files.
- D27: recorded only (A.T06.2 change 10, A.T06.3 change 12).

(9) Plugin-level follow-ups. The D33 README lists improve-codebase-architecture among the user-invoked-only skills, noting that only Claude Code honours `disable-model-invocation`. It also notes the overlap with core's review-architecture prompt and Continue's router-only throwaway-prototype. ATTRIBUTIONS' skill table lists the id `throwaway-prototype` together with the rename. The listing budget adds 125 + 179 + 265 = 569 description characters. The D30 inventory parametrizes over the present skills until the final ticket pins the D9 ids.

### A.T07.1 diagnosing-bugs (upstream skills/engineering/diagnosing-bugs; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/diagnosing-bugs/SKILL.md` (138 lines, UTF-8, LF, final newline; the only non-ASCII characters are U+00D7 at L51 and U+2013 at L90) | `catalog/plugins/mattpocock_skills/skills/diagnosing-bugs/SKILL.md` | Vendored content, synced as `.agents/skills/diagnosing-bugs/SKILL.md` (D12). Changes 1-7 are the only edits. All of them are in place except the added `id` line, so the file has 139 lines. Every other byte stays as upstream has it, including the `×` (L51), the `–` (L90), the LF endings and the final newline. |
  | `skills/engineering/diagnosing-bugs/scripts/hitl-loop.template.sh` (44 lines, UTF-8 with U+2192 at L10-L11, LF; mode 0644 in the v1.3.1 checkout) | `catalog/plugins/mattpocock_skills/skills/diagnosing-bugs/scripts/hitl_loop_template.py` | Rewritten in Python, not copied (D22). Changes 8-13 specify it function by function. File mode 0755, committed as git mode 100755 (spec section 5.1). The stem is snake_case because a dotted stem is not a module name. The `.sh` file is not shipped (G6). |
  | `skills/engineering/diagnosing-bugs/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata only: `interface.display_name: "Diagnosing Bugs"` and `interface.short_description: "Diagnose hard bugs and regressions"`. There is no `policy` block, so nothing about invocation is lost (D10). See change 15. |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/diagnosing-bugs/references/LICENSE` | A byte-identical copy of the plugin-root LICENSE (D4, G10). See change 14. |

  Upstream has no sibling markdown file and no `references/`. Nothing moves under `references/`, and no markdown link is rewritten. The plugin skill directory holds exactly `SKILL.md`, `scripts/hitl_loop_template.py` and `references/LICENSE` (G9). The skill's ATTRIBUTIONS section opens with "Upstream `skills/engineering/diagnosing-bugs/`; synced as `.agents/skills/diagnosing-bugs/`".

- **Frontmatter** (plugin source, in this order):

  ```yaml
  ---
  id: diagnosing-bugs
  name: diagnosing-bugs
  description: Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"debug this", or reports something broken/throwing/failing/slow.
  ---
  ```

  Only `id` is new (D11). Add it by text insertion; do not load and re-dump the YAML. `name` and `description` are upstream L2-L3, byte for byte. The description is a 156-character plain scalar. There is no `disable-model-invocation`, so the skill is model-invoked. It gets no D19 guard line, and G15 requires that the guard line is absent. It has no `playbook:` block (D11).

- **Changes** (all line numbers are upstream v1.3.1 lines; ATTRIBUTIONS cites them as "`<file>` L<n> (v1.3.1)"):

  1. `SKILL.md`, frontmatter, before L2 "name: diagnosing-bugs". Insert the line `id: diagnosing-bugs` as the first frontmatter key. (D11)
  2. `SKILL.md` L10, "read `GLOSSARY.md` (if it exists) to get a clear mental model". Insert `` (or `CONTEXT.md` if the repo already has one)`` directly after the code span `` `GLOSSARY.md` ``. Nothing else on the line changes. The resulting line:

     ```text
     When exploring the codebase, read `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) (if it exists) to get a clear mental model of the relevant modules, and check ADRs in the area you're touching.
     ```

     (D21. This is the same parenthetical as A.T01 and A.T02, so G16 and the one grep "if the repo already has one" cover it. The file never names `GLOSSARY-MAP.md`, so no MAP fallback is needed.)
  3. `SKILL.md` L27, "2. **Curl / HTTP script** against a running dev server.". Delete `Curl / `. The resulting line is `2. **HTTP script** against a running dev server.` The running dev server is project toolchain and stays. (D2: curl is an imposed tool. D22: the curl option is removed.)
  4. `SKILL.md` L29, "(Playwright / Puppeteer)". Delete ` / Puppeteer`. The resulting line is `4. **Headless browser script** (Playwright) that drives the UI and asserts on DOM/console/network.` Playwright stays because it is pip-installable (D2). Puppeteer is a Node-only library. (D2, D22)
  5. `SKILL.md` L35, "10. **HITL bash script.** Last resort. If a human must click, drive _them_ with `scripts/hitl-loop.template.sh`". The option now names the Python rewrite. The resulting line:

     ```text
     10. **HITL Python script.** Last resort. If a human must click, drive _them_ with `scripts/hitl_loop_template.py` so the loop is still structured. Captured output feeds back to you.
     ```

     (D22: the bash script becomes Python, so "bash" becomes "Python" and the path follows the new file. The path resolves under G13.)
  6. `SKILL.md` L59, "(a script path, a test invocation, a curl)". Delete `, a curl`. The resulting fragment is `you can name **one command** (a script path, a test invocation) that you have **already run at least once**`. The rest of L59 is unchanged. (D2, D22)
  7. `SKILL.md` L64, "a human in the loop only via `scripts/hitl-loop.template.sh`.". The resulting line is `` - [ ] **Agent-runnable**: you can run it unattended; a human in the loop only via `scripts/hitl_loop_template.py`.`` (D22)
  8. `scripts/hitl-loop.template.sh` L1-L44 becomes `scripts/hitl_loop_template.py`. (D22, D10) This is a rewrite, not a copy. The new file targets Python 3.10 or later, uses only the stdlib, has `#!/usr/bin/env python3` as line 1 and mode 0755, and is clean under `mypy --strict --python-version 3.10`, `ruff check` and `ruff format` (the per-file py310 target at `pyproject.toml:155` already covers `catalog/plugins/*/skills/*/scripts/*.py`). Matt's text stays:
     - every comment line of L2-L16 survives in the module docstring, minus the leading `# ` (changes 9 and 10 are the only rewordings);
     - the edit markers L32 and L40 are copied byte for byte (74 characters each);
     - the prompts of L36 and L38 stay verbatim, and L34 follows change 11.

     Upstream L18 `set -euo pipefail` has no counterpart. Python stops on any uncaught exception, there are no shell variables to leave unset, and there is no pipeline.

     File layout, top to bottom:
     1. The shebang.
     2. The module docstring (below).
     3. `from __future__ import annotations`.
     4. The imports: `re`, `shlex`, `sys`, `from pathlib import Path` and `from typing import TYPE_CHECKING`, with `from collections.abc import Callable` under `if TYPE_CHECKING:` (ruff TC003).
     5. The constants `EXIT_NO_TERMINAL = 2`, `EXIT_INTERRUPTED = 130` and `_CAPTURE_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")`.
     6. `CAPTURED: dict[str, str] = {}`, with the comment `# capture() stores each answer here, in capture order.`
     7. The library functions in the table.
     8. `hitl_steps()`.
     9. As the last two lines: `if __name__ == "__main__":` and `    raise SystemExit(run_hitl_loop(hitl_steps))`.

     The module docstring is exact. Its first line is the opening `"""` plus upstream L2:

     ```text
     Human-in-the-loop reproduction loop.
     Copy this file, edit the steps below, and run it.
     The agent runs the script; the user follows prompts in their terminal.

     Usage:
       python3 hitl_loop_template.py

     Two helpers:
       step("<instruction>")          → show instruction, wait for Enter
       capture("VAR", "<question>")   → show question, store the answer under VAR

     At the end, captured values are printed as KEY=VALUE for the agent to parse.

     `capture` prints its value back to the terminal, where the agent reads it,
     so capture observations, and leave signing in to the user as a `step`.
     ```

     The functions (each has a type-hinted signature and a docstring; `_out(text)` means `sys.stdout.write(text)` followed by `sys.stdout.flush()`):

     | Upstream | Python | Behaviour |
     |---|---|---|
     | (printf, L21, L27, L42-L44) | `_out(text: str) -> None` | Writes to stdout and flushes. It is the only writer to stdout. |
     | `read -r -p PROMPT` (L22, L28) | `_read_answer(prompt: str) -> str` | Writes `prompt` to **stderr** and flushes, because bash `read -p` prints its prompt on stderr. Then it calls `input()` with no prompt and returns the line `.strip(" \t")`, because `read -r` with the default IFS trims leading and trailing blanks. `EOFError` and `KeyboardInterrupt` propagate. |
     | `step()` L20-L23 | `step(instruction: str) -> None` | `_out(f"\n>>> {instruction}\n")`, then `_read_answer("    [Enter when done] ")`. The answer is discarded. |
     | `capture()` L25-L30 | `capture(name: str, question: str) -> str` | `printf -v` accepts only shell identifiers, so a `name` that does not fullmatch `_CAPTURE_NAME_RE` raises `ValueError(f"capture name {name!r} must be an identifier such as ERROR_MSG (letters, digits and underscores, not starting with a digit)")` before anything is shown. Otherwise: `_out(f"\n>>> {question}\n")`, then `answer = _read_answer("    > ")` and `CAPTURED[name] = answer`. A repeated name keeps its first position and takes the last value, as a reassigned shell variable does. Returns `answer`. |
     | `printf -v "$var"` L29 | `CAPTURED` | A dict replaces the shell variables, so the stages never declare variables. |
     | L42-L44 | `_print_captured() -> None` | `_out("\n--- Captured ---\n")`, then `_out(f"{name}={value}\n")` for every entry of `CAPTURED`, in order (change 12). |
     | (none) | `_no_terminal_message(script: Path) -> str` | Returns exactly the three lines of change 13, formatted with `shlex.quote(str(script))`. |
     | (none) | `run_hitl_loop(steps: Callable[[], None]) -> int` | (1) If `not sys.stdin.isatty()`, write `_no_terminal_message(Path(__file__).resolve())` to stderr and return `EXIT_NO_TERMINAL` before any step is shown. (2) Call `steps()`. On `EOFError`, write the same message to stderr and return `EXIT_NO_TERMINAL` with no Captured block. On `KeyboardInterrupt`, `_out("\n")` and return `EXIT_INTERRUPTED`, with no traceback and no Captured block: bash ends a Ctrl-C with status 130 and prints nothing more. (3) Otherwise call `_print_captured()` and return 0. Any other exception propagates (traceback, status 1), as `set -e` stops bash. |
     | L32-L40 | `hitl_steps() -> None` | The docstring `"""The steps the human takes, in order: one step() or capture() call each."""`. Then the L32 marker, indented four spaces; a blank line; `step("Open the app at its local dev server address and sign in.")`; a blank line; `capture("ERRORED", "Click the 'Export' button. Did it throw an error? (y/n)")`; a blank line; `capture("ERROR_MSG", "Paste the error message (or 'none'):")`; a blank line; and the L40 marker, indented four spaces. Everything the author edits sits between the two markers. The docstring keeps the body valid when every example call is deleted. |

     The stages are inside a function, so the file can be loaded without running them (the driver in the tests below relies on this). No colours and no screen clearing: upstream has neither.
  9. The docstring usage line, from upstream L7 "#   bash hitl-loop.template.sh". It becomes `  python3 hitl_loop_template.py`. It names the file, as G19's usage-line check requires. (D22, D30)
  10. The docstring helper lines, from upstream L10 "#   step "<instruction>"          → show instruction, wait for Enter" and L11 "#   capture VAR "<question>"      → show question, read response into VAR". They become the two lines in Python call syntax shown in change 8. L11's "read response into VAR" becomes "store the answer under VAR", because no shell variable is set any more. (D22)
  11. The example step at L34, upstream `step "Open the app at` (then an http address on localhost port 3000) `and sign in."`. It becomes `step("Open the app at its local dev server address and sign in.")`. The plugin carries no URL, and a bare localhost address with a port is a JS dev-server default. (D4, D22)
  12. The Captured block at L42-L44, upstream `printf 'ERRORED=%s\n' "$ERRORED"` and `printf 'ERROR_MSG=%s\n' "$ERROR_MSG"`. The block now prints every capture in capture order rather than the two example names. Upstream hard-codes them below the "edit above" marker, so an author who renamed a capture also had to edit the library part. With the default example the output is identical. (D22: the dict replaces `printf -v`)
  13. The non-terminal guard, new in `run_hitl_loop`. When stdin is not a terminal, or an answer hits end of file, the loop prints this message to stderr and exits with status 2. Each of the three lines ends with a newline. `{path}` is the shell-quoted absolute path of the running copy:

      ```text
      This HITL loop needs a human at an interactive terminal, and stdin here is not one (or it was closed).
      Ask the user to run it in their own terminal, follow the prompts, and paste back the "--- Captured ---" block:
          python3 {path}
      ```

      Matt's text at L4 ("The agent runs the script; the user follows prompts in their terminal.") and SKILL L35 stay verbatim. The guard is what makes them work where an agent shell has no TTY. (D22, Q27.12)
  14. `references/LICENSE` is added. It is a byte-identical copy of the plugin-root LICENSE, the upstream MIT text "Copyright (c) 2026 Matt Pocock". (D4; the global "License copies" section may cover this.)
  15. `agents/openai.yaml` is dropped and not shipped. It holds only `interface.display_name` and `interface.short_description`, with no `policy` block, so Codex loses only its display name and short description for this skill. (D10)
  16. Recorded with no edit: `SKILL.md` L112, "`performance.now()`". This JS timer is kept verbatim as a stack assumption, next to the language-neutral "timing harness, ... profiler, query plan". (D27)

- **Project-toolchain allowlist**: none. After changes 3, 4 and 6, no line of `SKILL.md` or the script holds a G4 name. G5 finds nothing either:
  - "Playwright" (L29) and "a running dev server" (L27) are prose;
  - the code spans `` `git bisect run` `` (L33), `` `performance.now()` `` (L112) and `` `grep` `` (L136) start with words that are not ambiguous;
  - the script has no subprocess call.

  `tests/plugins/mattpocock_skills/allowlist/diagnosing-bugs.txt` still exists (G17) and holds exactly one line: `# diagnosing-bugs: no project-toolchain entries (A.T07.1)`.

- **Skill-specific tests**: in `tests/plugins/mattpocock_skills/test_debug_wizard.py` (T07; `pytestmark = pytest.mark.catalog`). The shared gate already runs G19 on the script: the python3 shebang, the executable bit, `ast.parse(feature_version=(3, 10))`, a docstring usage line naming the file, stdlib-only imports and `mypy --strict --python-version 3.10`. T07 adds no copy of those checks; it only makes them pass. Spec section 7.7 forbids importing a script in the pytest process, because that writes `scripts/__pycache__/` into the catalog. So every behaviour test runs in a subprocess started with `sys.executable -B`, with `timeout=60`, `cwd=tmp_path` and `capture_output=True, text=True`. Static checks parse the source text with `ast` and import nothing.

  **The driver** (shared with A.T07.2). Make it a module-level string `_SCRIPT_DRIVER` in the test file, run as `[sys.executable, "-B", "-c", _SCRIPT_DRIVER]`. The JSON scenario goes on the child's stdin (`input=json.dumps(scenario)`). The subprocess environment is `os.environ` without `ENV_FILE` and `BROWSER`, plus `TERM=dumb`, with `scenario.get("env", {})` merged over it. The helper is `run_script_scenario(script: Path, scenario: dict[str, object], cwd: Path) -> dict[str, Any]`. It sets `scenario["script"] = str(script)`, asserts exit status 0 and parses the child's last stdout line as JSON. The child:
  1. Reads the scenario from the real stdin.
  2. Swaps in three named fakes before anything is loaded:
     - `sys.stdin` becomes `FakeTerminalStdin`, an `io.StringIO` over `"".join(line + "\n" for line in scenario["stdin"])`. Its `isatty()` returns `scenario.get("stdin_tty", True)`. Its `readline()` raises `KeyboardInterrupt` on read number `scenario.get("interrupt_on_read")`, counting from 1.
     - stdout is redirected (`contextlib.redirect_stdout`) to `FakeTerminalStdout`, an `io.StringIO` whose `isatty()` returns `scenario.get("stdout_tty", False)`.
     - stderr is redirected to an `io.StringIO`.
  3. Patches `getpass.getpass` with `FakeGetpass`, which records each prompt, returns the queued `scenario.get("getpass", [])` answers and raises `EOFError` once they run out.
  4. Patches `webbrowser.open` with `FakeBrowserOpen`, which records `[url, new]` and, for `scenario.get("browser", "opens")`, returns True on "opens", returns False on "fails" and raises `webbrowser.Error("no runnable browser")` on "raises".
  5. If `scenario.get("fail_replace")` is set, patches `os.replace` to raise `OSError("replace failed")`.
  6. Loads the script with `importlib.util.spec_from_file_location("script_under_test", scenario["script"])`, registers it in `sys.modules` and calls `exec_module`. `-B` keeps bytecode out of the catalog.
  7. Applies `scenario.get("set", {})` with `setattr` on the module.
  8. Runs each entry of `scenario["calls"]`, a list of `[name, *args]`, in order:
     - `["__run__"]` calls `run_hitl_loop(hitl_steps)`, or `run_wizard(wizard_stages)` in the wizard;
     - `["__get__", NAME]` returns a module global;
     - any other name calls that module function.

     Each call appends `{"value": ..., "error": null}` or `{"value": null, "error": [type name, str(exc)]}`. `BaseException` is caught, `SystemExit` included.
  9. Prints one JSON line to `sys.__stdout__`, with these keys:
     - `results`;
     - the captured `stdout` and `stderr`;
     - `getpass_prompts` and `browser_calls`;
     - `state`: the present module globals among `CAPTURED`, `WRITTEN_ENV`, `WRITTEN_SECRET`, `WRITTEN_VAR`, `SKIPPED`, `ENV_FILE`, `TOTAL_STAGES` and `_STAGE_INDEX`.

  The script must therefore call `getpass.getpass`, `webbrowser.open` and `os.replace` through their modules (`import getpass`, `import webbrowser`, `import os`), never `from x import y`. Otherwise the fakes would not take effect.

  The tests for this skill:
  - `test_diagnosing_bugs_skill_text`: `SKILL.md` contains, as exact substrings, the resulting texts of changes 2-7, and contains none of "Curl / HTTP script", "Playwright / Puppeteer", ", a curl)", "HITL bash script" or "hitl-loop.template.sh". `` `scripts/hitl_loop_template.py` `` occurs exactly twice (L35, L64). No file in the skill directory contains "hitl-loop.template.sh".
  - `test_hitl_template_keeps_matt_text`: parse the script source with `ast` (no import). The module docstring contains every line of the change 8 docstring. The source contains each of the two upstream markers exactly once, the three example calls of `hitl_steps` exactly, and no "localhost". A top-level `def` exists for `step`, `capture`, `run_hitl_loop` and `hitl_steps`, and the last statement is the `if __name__ == "__main__":` block.
  - `test_hitl_without_a_terminal_exits_2_and_asks_for_the_users_terminal`: a plain subprocess `[sys.executable, "-B", str(script)]` with `stdin=subprocess.DEVNULL`, so no driver. The return code is 2. stdout is empty: no step was shown and there is no Captured block. stderr equals the change 13 message with `{path}` = `shlex.quote(str(script.resolve()))`. "Traceback" is not in stderr.
  - `test_hitl_run_prints_every_capture_in_order`: driver, `stdin = ["", "y", "TypeError: x is undefined"]`, calls `[["__run__"]]`. The value is 0. stdout equals exactly `"\n>>> Open the app at its local dev server address and sign in.\n\n>>> Click the 'Export' button. Did it throw an error? (y/n)\n\n>>> Paste the error message (or 'none'):\n\n--- Captured ---\nERRORED=y\nERROR_MSG=TypeError: x is undefined\n"`. stderr equals `"    [Enter when done]     >     > "`. That pins the prompts on stderr.
  - `test_hitl_trims_answers_like_read`: stdin `["", "  y \t", "none"]`. The Captured block holds `ERRORED=y`.
  - `test_hitl_eof_mid_loop_exits_2_without_a_captured_block`: stdin `[""]`, so end of file comes at the first capture. The value is 2. stderr ends with the change 13 message. "--- Captured ---" is not in stdout.
  - `test_hitl_ctrl_c_exits_130_quietly`: `interrupt_on_read = 1`. The value is 130. stdout equals `"\n>>> Open the app at its local dev server address and sign in.\n\n"`. stderr holds no "Traceback".
  - `test_hitl_capture_rejects_a_name_that_is_not_an_identifier`: calls `[["capture", "bad name", "q"]]`. The error is `ValueError`, its message contains `'bad name'`, and stdout is empty.
  - `test_hitl_repeated_capture_name_keeps_its_place_and_last_value`: stdin `["1", "2", "3"]`, calls `capture("A", "q")`, `capture("B", "q")`, `capture("A", "q")`, `_print_captured()`. stdout ends with `"--- Captured ---\nA=3\nB=2\n"`.
  - D21 needs no extra test. G16 (shared gate) covers `SKILL.md`, and `test_diagnosing_bugs_skill_text` pins the exact L10 line.

- **Continue degradation**: With the `continue` adapter listed, `.continue/prompts/diagnosing-bugs.md` carries only the name, description and body. The model can no longer pick the skill from its description, so the user starts it as `/diagnosing-bugs`. `scripts/hitl_loop_template.py` does not travel, so option 10 (L35) and the Agent-runnable criterion (L64) name a file that is not there, and a human-in-the-loop script has to be written by hand. No LICENSE copy travels. This holds unless the Continue IDE also reads the full skill natively from `.claude/skills/`. The six-phase method itself is self-contained in the body. (D29)

### A.T07.2 wizard (upstream skills/engineering/wizard; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/wizard/SKILL.md` (44 lines, UTF-8, LF, final newline; the only non-ASCII character is U+2192 at L29) | `catalog/plugins/mattpocock_skills/skills/wizard/SKILL.md` | Vendored content, synced as `.agents/skills/wizard/SKILL.md` (D12). Changes 1-11 are the only edits. All of them are in place except the added `id` line, so the file has 45 lines. |
  | `skills/engineering/wizard/template.sh` (204 lines, UTF-8 with U+2500 box drawing at L11, L13, L182, L185, L191, L202 and the glyphs ▸ · • ⚠ ↗ ✓ → at L54-L172; LF; mode 0644 in the checkout) | `catalog/plugins/mattpocock_skills/skills/wizard/scripts/wizard_template.py` | Rewritten in Python, not copied, and moved from the skill root into `scripts/` (D22, which overrides D10's default of `references/` for this script). Changes 12-25 specify it function by function. File mode 0755, git mode 100755. The `.sh` file is not shipped (G6). |
  | `skills/engineering/wizard/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata only: `interface.display_name: "Wizard"` and `interface.short_description: "Generate an interactive setup wizard"`. It has no `policy` block (D10). See change 27. |
  | upstream repository-root `LICENSE`, through the plugin-root copy | `catalog/plugins/mattpocock_skills/skills/wizard/references/LICENSE` | A byte-identical copy (D4, G10). See change 26. |

  The plugin skill directory holds exactly `SKILL.md`, `scripts/wizard_template.py` and `references/LICENSE` (G9). The skill's ATTRIBUTIONS section opens with "Upstream `skills/engineering/wizard/`; synced as `.agents/skills/wizard/`".

- **Frontmatter** (plugin source, in this order):

  ```yaml
  ---
  id: wizard
  name: wizard
  description: Generate an interactive Python wizard that walks a human through steps only they can perform. Use when provisioning infrastructure, setting up credentials or CI secrets, walking an unfamiliar third-party dashboard, or running a one-off migration or cutover. Don't invoke this for steps the agent can perform itself.
  ---
  ```

  `id` is added (D11). `name` is verbatim. The description changes one word, "bash" to "Python" (change 2, D22). Spec section 5.3 item 4 expects exactly this description change. The description stays a plain scalar: it has no ": " and its apostrophe needs no quoting. It is 313 characters upstream and 315 after the change. Plugins are exempt from the 300-character lint (prS D24, D28), and G11 allows up to 1,024. There is no `disable-model-invocation`: the skill is model-invoked, gets no D19 guard line, and G15 requires the guard line to be absent.

- **Changes** (all line numbers are upstream v1.3.1 lines):

  1. `SKILL.md`, frontmatter, before L2 "name: wizard". Insert `id: wizard` as the first frontmatter key. (D11)
  2. `SKILL.md` L3, "Generate an interactive bash wizard". Replace it with `Generate an interactive Python wizard`. The rest of the description is unchanged. (D22)
  3. `SKILL.md` L8, "A **wizard** is a bash script that walks a human". Replace it with `A **wizard** is a Python script that walks a human`. (D22)
  4. `SKILL.md` L8, "writes them where they belong (`.env`, GitHub secrets)". Replace it with ``writes them where they belong (`.env`, or GitHub secrets it walks the human through setting)``. The resulting L8:

     ```text
     A **wizard** is a Python script that walks a human, step by step, through a manual procedure that's tedious to do by hand and tedious to re-explain to an AI every time. It opens each URL, says exactly what to click and copy, captures the values, writes them where they belong (`.env`, or GitHub secrets it walks the human through setting), confirms at every stage, and shows how many stages are left. It might configure third-party services, run a one-off migration, or move the project from one state to another.
     ```

     (D2: the forge CLI write is gone. D22, Q27.8: the guided manual steps.)
  5. `SKILL.md` L10, "[template.sh](template.sh)". The link becomes `[wizard_template.py](scripts/wizard_template.py)`. The target moved under `scripts/` and was renamed. The link text is not code-formatted, so it carries the new file name only. (D10, D22)
  6. `SKILL.md` L10, "cross-platform URL opening (including WSL)". Replace it with ``cross-platform URL opening (Python's `webbrowser`, printing the URL when no browser opens)``. WSL opener support is lost, and ATTRIBUTIONS records the loss (change 17). (D22)
  7. `SKILL.md` L10, "`gh secret`/`gh variable` writes". Replace it with `guided GitHub secret/variable steps`. The resulting L10:

     ```text
     The delightful UX is already solved by [wizard_template.py](scripts/wizard_template.py): stage-by-stage progress, confirmation gates, cross-platform URL opening (Python's `webbrowser`, printing the URL when no browser opens), hidden secret entry, idempotent `.env` upserts, guided GitHub secret/variable steps, and a closing summary. **Your job is only to scope the procedure and author its stages.** The library above the `STAGES` marker is identical in every wizard; that consistency is the point: never hand-edit it.
     ```

     (D2, D22, Q27.8)
  8. `SKILL.md` L20, "- For setup: `.env`, `.env.example`, `.env.*`, `README`, `docker-compose*`, framework config, and `.github/workflows/*`". D22 says the agent reads only the `.env` templates the secrets-path guard exempts and the CI config, never `.env` or any other `.env.*`, so `README`, `docker-compose*` and framework config leave the list too. The resulting line:

     ```text
     - For setup: the `.env` templates (`.env.example`, `.env.sample`, `.env.template`, `.env.dist`; never `.env` itself or any other `.env.*`, which hold live values) and `.github/workflows/*` (every `secrets.*` / `vars.*` reference is a value the wizard must produce).
     ```

     Existing values still reach the human at run time, because `ask` offers them as defaults. (D22, Q27.9; the four names are `SECRET_PATH_EXEMPT`, `security/patterns.py:108-113`)
  9. `SKILL.md` L35, "Copy `template.sh` to the target path.". Replace it with ``Copy `scripts/wizard_template.py` to the target path.`` The rest of L35 is verbatim. The rewrite keeps every helper name the line lists (`stage`, `say`/`step`, `open_url`, `ask`/`ask_secret`, `write_env`, `set_secret`/`set_var`, `pause`/`confirm`) and `TOTAL_STAGES`. (D10, D22)
  10. `SKILL.md` L41, "- `bash -n <script>`; run `shellcheck` if available.". The resulting line:

      ```text
      - Check the syntax with `ast.parse`, which writes no `__pycache__/`: `python3 -c "import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))" <script>`; run `ruff check` or `mypy` if available.
      ```

      (D2: `bash -n` and shellcheck are imposed tools. D22, Q27.11: an `ast.parse` check, because `py_compile` would leave `__pycache__/` in the consumer's `scripts/`; and pip-installable linters if available.)
  11. `SKILL.md` L42, "- `chmod +x <script>`.". The resulting line:

      ```text
      - Make it executable with `os.chmod` (`python3 -c "import os, sys; os.chmod(sys.argv[1], 0o755)" <script>`), or tell the user to run it as `python3 <script>`.
      ```

      A copy written with the harness's file tool does not keep the template's mode bit. (D22, Q27.11)
  12. `template.sh` L1-L204 becomes `scripts/wizard_template.py`. (D22) This is a rewrite, not a copy: Python 3.10 or later, stdlib only, `#!/usr/bin/env python3`, mode 0755, clean under `mypy --strict --python-version 3.10`, `ruff check` and `ruff format`. The library/STAGES split, every helper name, every user-facing string and the upstream comments survive, except where changes 13-25 say otherwise. The comments that describe a helper become its docstring, rewritten in call syntax: `banner "Title"` becomes `banner("Title")`; `stage "Name"`, `say "..."`, `step "..."`, `pause "msg"`, `confirm "question"` and `_existing KEY` follow the same pattern; "reads a value into $KEY" becomes "returns the value read". The comment blocks of L11-L13, L182-L185 and L191/L202 are copied byte for byte. The rule lines among them (L11, L13, L182, L185, L191, L202) are 76 characters each, and L191 and L202 are indented four spaces inside `wizard_stages`. Upstream L9 `set -euo pipefail` has no counterpart: an uncaught exception stops the run with status 1, as `set -e` stops bash.

      File layout, top to bottom:
      1. The shebang.
      2. The module docstring:

         ```text
         A wizard walks a human through a manual procedure, step by step.
         Generated by the `wizard` skill.

         Everything above the "STAGES" marker is the wizard library: do not hand-edit
         it. Author the per-step stages below the marker.

         Usage:
           python3 wizard_template.py
         ```

         Lines 1-5 are upstream L3-L7, with change 13 on L4. Upstream L2, a bare `#`, is dropped. The usage block is new. G19 requires a docstring usage line that names the file, and upstream's header has none (D30).
      3. `from __future__ import annotations`.
      4. The imports `contextlib`, `getpass`, `os`, `re`, `shlex`, `sys`, `tempfile`, `urllib.parse`, `webbrowser`, `from pathlib import Path` and `from typing import TYPE_CHECKING`, with `from collections.abc import Callable, Mapping` and `from typing import TextIO` under `if TYPE_CHECKING:`.
      5. The L11-L13 comment block.
      6. The colour code (change 14).
      7. The state, as the module globals `TOTAL_STAGES = 0` (with the L22 comment verbatim), `_STAGE_INDEX = 0`, `ENV_FILE = os.environ.get("ENV_FILE") or ".env"` (bash `${ENV_FILE:-.env}`: unset or empty both give `.env`), and these lists, each with its upstream trailing comment:
         - `WRITTEN_ENV: list[str] = []` ("# KEYs written to ENV_FILE this run");
         - `WRITTEN_SECRET: list[str] = []` ("# secret NAMEs set this run");
         - `SKIPPED: list[str] = []` (change 16);
         - the new `WRITTEN_VAR: list[str] = []  # variable NAMEs set this run` (changes 21, 22).

         Also `EXIT_NO_TERMINAL = 2`, `EXIT_INTERRUPTED = 130`, `_ENV_KEY_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")` and `_SCREEN_CLEAR = "\033[2J\033[3J\033[H"`.
      8. The library functions in the table, in upstream order.
      9. The L182-L185 marker block.
      10. `TOTAL_STAGES = 1`.
      11. `wizard_stages()` (changes 24, 25).
      12. `if __name__ == "__main__":` and `    raise SystemExit(run_wizard(wizard_stages))` as the last two lines.

      Library functions. `_out(text)` writes to stdout and flushes, as `printf` does. Every format string below is exact. `{BOLD}` and the other colour names are the module constants, all `""` without colour.

      | Upstream | Python | Behaviour |
      |---|---|---|
      | printf | `_out(text: str) -> None` | `sys.stdout.write(text)`; `sys.stdout.flush()`. |
      | `read -r` (L80, L87, L108) | `_read_line() -> str` | `input()` with no prompt, `.strip(" \t")`. `EOFError` returns `""`, which is upstream's `read ... \|\| true`. `KeyboardInterrupt` propagates. |
      | L15-L20 | `_use_color(stream: TextIO, environ: Mapping[str, str]) -> bool`; `_sgr(code: str) -> str` | See change 14. |
      | L31-L36 `_clear` | `_clear() -> None` | See change 15. |
      | L38-L47 `banner` | `banner(title: str) -> None` | `_clear()`; `_out(f"\n{BOLD}{BLUE}  {title}{RESET}\n")`; `_out(f"{DIM}  {TOTAL_STAGES} stages{RESET}\n\n")`; `_out(f"{DIM}  You drive the browser; this wizard tells you exactly what to do and\n")`; `_out("  captures the values you copy back. Stop any time with Ctrl-C and re-run\n")`; `_out(f"  later, since it remembers values already saved.{RESET}\n")`; `pause("Ready to start?")`. `TOTAL_STAGES` is read when the function is called, so the value set below the marker applies. |
      | L49-L56 `stage` | `stage(name: str) -> None` | `_clear()`; `global _STAGE_INDEX`; `_STAGE_INDEX += 1`; `_out(f"\n{BOLD}{BLUE}▸ Stage {_STAGE_INDEX}/{TOTAL_STAGES} · {name}{RESET}\n")`. |
      | L59 `say` | `say(text: str) -> None` | `_out(f"  {text}\n")`. |
      | L61 `step` | `step(text: str) -> None` | `_out(f"  {BLUE}•{RESET} {text}\n")`. |
      | L62 `note` | `note(text: str) -> None` | `_out(f"  {DIM}{text}{RESET}\n")`. |
      | L63 `warn` | `warn(text: str) -> None` | `_out(f"  {YELLOW}⚠ {text}{RESET}\n")`. |
      | L65-L75 `open_url` | `open_url(url: str) -> None`; `_launchable(url: str) -> bool` | See change 17. |
      | L77-L81 `pause` | `pause(message: str = "Press Enter to continue") -> None` | `_out(f"  {DIM}{message}{RESET} ")`; `_read_line()`. End of file continues. |
      | L83-L89 `confirm` | `confirm(question: str) -> bool` | `_out(f"  {YELLOW}? {question} [y/N] ")`, with no RESET: upstream L86 has none, and the rewrite keeps that byte for byte. Returns `_read_line().startswith(("y", "Y"))`, which is `^[Yy]`. End of file returns False. |
      | (identifier rule of `printf -v`) | `_check_env_key(key: str) -> None` | Raises `ValueError(f".env key {key!r} must be an identifier such as STRIPE_SECRET_KEY (letters, digits and underscores, not starting with a digit)")` unless `_ENV_KEY_RE.fullmatch(key)`. `ask`, `ask_secret` and `write_env` call it first. |
      | L94 (grep, tail) | `_env_lines(path: Path) -> list[bytes]` | `[]` when `not path.is_file()`. Otherwise `path.read_bytes().split(b"\n")`, minus the final element when it is empty (the file ended with a newline, or is empty). Lines keep any `\r` and any non-UTF-8 byte, as grep does. |
      | L91-L96 `_existing` | `_existing(key: str) -> str` | The last line of `_env_lines(Path(ENV_FILE))` that starts with `key.encode() + b"="`, decoded with UTF-8 and `surrogateescape` after the first `=` (bash `${line#*=}`). `""` when there is no such line or no regular file (`[[ -f ]]`). `AB=1` never matches key `A`, and neither does `export A=1`, as with upstream's `^A=`. |
      | L103-L107, L117-L121 | `_show_prompt(prompt: str, current: str) -> None` | When `current` is set: `_out(f"  {BOLD}{prompt}{RESET} {DIM}[Enter keeps current]{RESET} ")`. Otherwise: `_out(f"  {BOLD}{prompt}{RESET} ")`. The current value is never printed. This replaces upstream's duplicated block. |
      | L98-L111 `ask` | `ask(key: str, prompt: str) -> str` | `_check_env_key(key)`; `current = _existing(key)`; `_show_prompt(prompt, current)`; `answer = _read_line()`; returns `answer or current`. It returns the value instead of `printf -v` (change 18). |
      | `read -rs` (L122-L123) | `_read_secret() -> str` | `getpass.getpass("")`, `.strip(" \t")`. `EOFError` returns `""`. getpass hides the entry and writes the newline that upstream's L123 `printf '\n'` wrote. |
      | L113-L126 `ask_secret` | `ask_secret(key: str, prompt: str) -> str` | Like `ask`, but reads through `_read_secret()`. The value is never echoed or printed (change 18). |
      | `mktemp` + `mv` (L133-L136) | `_replace_atomically(path: Path, data: bytes) -> None` | See change 19. |
      | L128-L139 `write_env` | `write_env(key: str, value: str) -> None` | See change 19. |
      | L141-L154 `set_secret` | `set_secret(name: str, value: str) -> None` | See change 20. |
      | L156-L167 `set_var` | `set_var(name: str, value: str) -> None` | See change 21. |
      | L169-L180 `finish` | `finish() -> None` | See change 22. |
      | (none) | `_no_terminal_message(script: Path) -> str`; `run_wizard(stages: Callable[[], None]) -> int` | See change 23. |

  13. `template.sh` L4, "# Generated by the /wizard skill.". In the docstring it becomes `` Generated by the `wizard` skill.`` This is agent-facing provenance in a file the agent copies and edits, not one of D17's human-facing kinds (router label, user-invoked description, "tell the user to run `/x`"), so the name is plain. (D17)
  14. `template.sh` L15-L20, the colours (`tput bold`, `tput dim`, `tput sgr0`, `tput setaf 4/2/3/1`, gated on `-t 1` and `tput colors` >= 8). They become ANSI SGR codes. `_use_color(stream, environ)` returns `stream.isatty() and environ.get("TERM", "") not in ("", "dumb")`; this stands in for "tput exists and reports at least 8 colours". `_COLOR = _use_color(sys.stdout, os.environ)` is computed once at import. `_sgr(code)` returns `f"\033[{code}m"` when `_COLOR`, else `""`. The constants are `BOLD = _sgr("1")`, `DIM = _sgr("2")`, `RESET = _sgr("0")`, `BLUE = _sgr("34")`, `GREEN = _sgr("32")`, `YELLOW = _sgr("33")` and `RED = _sgr("31")`; RED is unused, as upstream's is. (D2: tput is an imposed tool. D22.)
  15. `template.sh` L31-L36, `_clear`, upstream `tput clear` with a raw-escape fallback. `_clear()` writes `_SCREEN_CLEAR` (upstream's own fallback sequence) only when `sys.stdout.isatty()` and `os.environ.get("TERM") != "dumb"`. Otherwise it writes nothing, so piped logs stay readable. The L31-L32 comment becomes the docstring. (D2, D22)
  16. `template.sh` L29, "SKIPPED=()        # things we couldn't do (e.g. gh missing)". The comment becomes `# things left for the human to do by hand`. (D2: no forge CLI text remains.)
  17. `template.sh` L65-L75, `open_url`, which tried wslview, explorer.exe, xdg-open and open, with the L65 comment "cross-platform incl. WSL". The new docstring: `open_url(url) opens it in the human's browser through Python's webbrowser module; an argument without a scheme and host is only printed.` Behaviour:
      - If `not _launchable(url)`, `_out(f"  {GREEN}↗ go to{RESET} {url}\n")` and return without launching anything. `_launchable(url)` is `bool(parts.scheme and parts.netloc)` for `parts = urllib.parse.urlsplit(url)`. So the template's placeholder, `localhost:3000` and "Stripe: API keys" are all printed, not launched. No literal scheme separator appears in the source, which keeps G3 quiet.
      - Otherwise `_out(f"  {GREEN}↗ opening{RESET} {url}\n")`, as upstream L68. Then call `webbrowser.open(url, new=2)` (a new tab, as the OS openers did).
      - When that returns False, `warn(f"couldn't open a browser; visit it manually: {url}")`. This is upstream L73's wording for "no opener found".
      - When it raises `webbrowser.Error` or `OSError`, `warn(f"couldn't open a browser, so visit it manually: {url}")`. This is upstream L74's wording for "the opener failed".

      Recorded losses, in ATTRIBUTIONS under Dropped (the WSL opener) and in the skill section:
      - no WSL opener (stdlib webbrowser has none; it honours the `BROWSER` environment variable);
      - opener output is not silenced as upstream's `>/dev/null 2>&1` silenced it;
      - on headless Linux with `TERM` set, webbrowser may start a console browser in the wizard's terminal until the human quits it.

      (D2, D22)
  18. `template.sh` L98-L126, `ask`/`ask_secret`, upstream `read -r input` / `read -rs input` then `printf -v "$key"`. Both return the value; a stage writes `value = ask("KEY", "Prompt:")`. `ask_secret` reads through `getpass.getpass` (change 12 table). The "Enter keeps current" default, the trimming and the empty-on-end-of-file behaviour match upstream. (D22)
  19. `template.sh` L128-L139, `write_env`, upstream touch, mktemp, `grep -v`, append, mv. The upsert is atomic and idempotent. Steps:
      1. `_check_env_key(key)`.
      2. `path = Path(ENV_FILE)`.
      3. `kept` = every line of `_env_lines(path)` that does not start with `key.encode() + b"="`. Every old line of that key goes, and all other lines stay byte for byte, as `grep -v "^KEY="` does.
      4. Append `key.encode() + b"=" + value.encode("utf-8", "surrogateescape")`.
      5. `_replace_atomically(path, b"\n".join(kept) + b"\n")`. A missing final newline on the last kept line gains one, as grep output does.
      6. `WRITTEN_ENV.append(key)`.
      7. `_out(f"  {GREEN}✓ wrote{RESET} {key} → {ENV_FILE}\n")`.

      `_replace_atomically` works in five steps:
      1. `fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")`. The temp file is in the same directory, so the replace is atomic.
      2. Write `data` through `os.fdopen(fd, "wb")`, `flush` and `os.fsync`.
      3. `os.replace(tmp, path)`.
      4. On any `BaseException`, remove `tmp` with `contextlib.suppress(FileNotFoundError)`.
      5. Re-raise.

      The file keeps mkstemp's mode 0600. Upstream's `mktemp` + `mv` left `.env` at 0600 too, so the result is the same and owner-only. A missing `.env` is created. A missing parent directory raises, as upstream's `touch` failed under `set -e`. (D22)
  20. `template.sh` L141-L154, `set_secret`, upstream `gh auth status` then `printf '%s' "$value" | gh secret set "$name"`, and the comments L141-L142. It becomes a guided manual step at capture time. The docstring: `set_secret(name, value) walks the human through adding a GitHub Actions repository secret by hand: it shows the name, never the value, waits for their confirmation and records it for the summary; a "no" leaves it on the still-to-do list.` Body:
      1. `step("In the GitHub repo: Settings → Secrets and variables → Actions → New repository secret.")`.
      2. `step(f"Name it {name} and paste the same value you just entered.")`.
      3. `if confirm(f"Added the GitHub secret {name}?"):` then `WRITTEN_SECRET.append(name)`, `_out(f"  {GREEN}✓ set{RESET} GitHub secret {name}\n")` (upstream L148's format) and return.
      4. Otherwise `SKIPPED.append(f"GitHub secret {name} (set it by hand in the repo's CI settings)")` (upstream L152 without its forge command) and `warn(f"skipped GitHub secret {name}; set it later")` (upstream L153 without "gh not ready").

      `value` stays in the signature so stages read as upstream's did; it is never printed. ATTRIBUTIONS records the automatic secret write as Dropped. (D2, D22, Q27.8)
  21. `template.sh` L156-L167, `set_var`, upstream `gh variable set "$name" --body "$value"`. It becomes the same guided step, but the value is shown. The docstring: `set_var(name, value) walks the human through adding a GitHub Actions repository variable (not secret) by hand: it shows the name and the value, waits for their confirmation and records it for the summary.` Body:
      1. `step("In the GitHub repo: Settings → Secrets and variables → Actions → Variables → New repository variable.")`.
      2. `step(f"Name it {name} and give it this value: {value}")`.
      3. On `confirm(f"Added the GitHub variable {name}?")`, `WRITTEN_VAR.append(name)` and `_out(f"  {GREEN}✓ set{RESET} GitHub variable {name}\n")` (upstream L161).
      4. Otherwise `SKIPPED.append(f"GitHub variable {name}")` (upstream L165 verbatim) and `warn(f"skipped GitHub variable {name}; set it later")` (upstream L166 without "gh not ready").

      (D2, D22, Q27.8)
  22. `template.sh` L169-L180, `finish`. The steps, with the new variables line third:
      1. `_clear()`.
      2. `_out(f"\n{BOLD}{GREEN}  ✓ Setup complete{RESET}\n")`.
      3. If `WRITTEN_ENV`: `note(f"wrote {len(WRITTEN_ENV)} value(s) to {ENV_FILE}: {' '.join(WRITTEN_ENV)}")`.
      4. If `WRITTEN_SECRET`: `note(f"set {len(WRITTEN_SECRET)} GitHub secret(s): {' '.join(WRITTEN_SECRET)}")`.
      5. New: if `WRITTEN_VAR`: `note(f"set {len(WRITTEN_VAR)} GitHub variable(s): {' '.join(WRITTEN_VAR)}")`.
      6. If `SKIPPED`: `_out("\n")`, `warn("still to do by hand:")`, then `note(f"  - {item}")` for each item.
      7. `_out("\n")`.

      Duplicates stay, as bash arrays keep them. (D22: "record for the summary" covers set_var, which upstream never recorded.)
  23. `run_wizard`, new, with a non-terminal guard and Ctrl-C handling. In order:
      1. If `not sys.stdin.isatty()`, write the message below to stderr and return `EXIT_NO_TERMINAL` before the banner. Nothing is opened or written.
      2. `try: stages()`. On `KeyboardInterrupt`: `_out(f"{RESET}\n")` (it also ends a colour that `confirm` left on), `warn("stopped. Re-run it later; it remembers values already saved.")` and return `EXIT_INTERRUPTED`, with no traceback.
      3. Otherwise return 0.

      End of file in the middle of a run is not an error: every reader returns `""`, so `pause` continues, `confirm` says no, and `ask`/`ask_secret` keep the current value (upstream L80, L87, L108, L122 `|| true`). The message, where `{path}` is `shlex.quote(str(Path(__file__).resolve()))` and each of the three lines ends with a newline:

      ```text
      This wizard needs a human at an interactive terminal, and stdin here is not one.
      Ask the user to run it in their own terminal:
          python3 {path}
      ```

      (D22: Ctrl-C/EOF handling. The non-TTY guard is not required by D22, which names one only for the HITL loop; it is added to enforce SKILL L43, "Don't run it end-to-end yourself": an agent shell has no TTY, so an accidental run opens no browser tab and writes no empty `.env` values. Without a TTY, getpass would also echo the secret. Section 5.3 item 10 and the section 7.1 `test_debug_wizard.py` row record it.)
  24. `template.sh` L187-L204, the stages section. Upstream runs it at top level. It becomes `TOTAL_STAGES = 1` and `def wizard_stages() -> None:`, with the docstring `"""The stages, in dependency order: banner first, one stage() per step, finish() last."""`. The upstream statements L189-L204 sit in the body, in order, indented four spaces. Then comes the `__main__` block. Keeping the stages in a function lets the tests load the file without running them. The STAGES comment (L182-L185) stays verbatim. (D22)
  25. `template.sh` L194, `open_url "` (then the https address of the Stripe dashboard's test-mode API keys page, host dashboard.stripe.com) `"`. It becomes `open_url("<Stripe dashboard, test mode: Developers → API keys>")`. The placeholder has no scheme, so `open_url` prints it (change 17). An author replaces it with the real page, which lives in the consumer's copy, not in the plugin. The rest of the example stage is rewritten statement by statement, strings verbatim:

      ```python
          # ── Example stage: replace with your real steps ───────────────────────────
          stage("Stripe: API keys")
          say("We'll grab your Stripe test keys and store them for local dev + CI.")
          open_url("<Stripe dashboard, test mode: Developers → API keys>")
          step("On the API keys page, copy the Publishable key (starts pk_test_).")
          stripe_publishable_key = ask("STRIPE_PUBLISHABLE_KEY", "Paste the publishable key:")
          step("Click 'Reveal test key' on the Secret key row, then copy it.")
          stripe_secret_key = ask_secret("STRIPE_SECRET_KEY", "Paste the secret key:")
          write_env("STRIPE_PUBLISHABLE_KEY", stripe_publishable_key)
          write_env("STRIPE_SECRET_KEY", stripe_secret_key)
          set_secret("STRIPE_SECRET_KEY", stripe_secret_key)  # CI needs this one
          # ──────────────────────────────────────────────────────────────────────────
      ```

      Copy the two comment rules from upstream L191 and L202, not from this block. `banner("Stripe setup")` comes first and `finish()` last, after a blank line. `ruff format` may wrap long calls, which is fine. (D4, D22, Q27.10)
  26. `references/LICENSE` is added as a byte-identical copy of the plugin-root LICENSE. (D4)
  27. `agents/openai.yaml` is dropped and not shipped. Codex loses only the display name "Wizard" and the short description. (D10)

- **Project-toolchain allowlist**: none. After the changes, no G4 name remains in `SKILL.md` or the script:
  - "GitHub", `.github/workflows/*` and `webbrowser` do not match the bounded names;
  - G5 finds no ambiguous word in command position: L29 "which URL to open", L37 "open the URL", L43 "it opens browsers" and L8 "It opens each URL" are prose; `` `open_url` `` is not equal to `open`; the new L41/L42 code spans start with `python3`, `ast.parse`, `os.chmod`, `ruff` or `mypy`; and the script has no subprocess call.

  `tests/plugins/mattpocock_skills/allowlist/wizard.txt` holds exactly one line: `# wizard: no project-toolchain entries (A.T07.2)`.

- **Skill-specific tests**: in the same `test_debug_wizard.py`, using the A.T07.1 driver. Write every `.env` under `tmp_path`, the driver's working directory, so `ENV_FILE` is the default `.env` unless a test sets it. Build every web address in the test from parts; this spec writes none.
  - `test_wizard_skill_text`: `SKILL.md` contains the resulting texts of changes 2-11 exactly. The description contains "interactive Python wizard". The body contains "`.env.sample`", "`.env.template`", "`.env.dist`" and "never `.env` itself". It contains none of "bash", "template.sh", "WSL", "`gh secret`", "shellcheck", "`chmod +x", "`.env.*`, `README`" or "`docker-compose*`". The `.env` templates are in the body, and the old read list is not.
  - `test_wizard_library_defines_every_helper_the_skill_names`: `ast` over the script source, no import. Split at the line of the L183 STAGES comment. Above it, a top-level `def` exists for each of `stage`, `say`, `step`, `open_url`, `ask`, `ask_secret`, `write_env`, `set_secret`, `set_var`, `pause` and `confirm`. That set equals the backticked names that SKILL L35 lists between "Use the library helpers:" and the next period (split on `/`). The test parses them from the line itself, so SKILL and template cannot drift. Also above it: `banner`, `note`, `warn`, `finish` and `run_wizard`. `TOTAL_STAGES` is assigned at module level once above the marker (0) and once below (1). `wizard_stages` is defined below. The last statement is the `__main__` block.
  - `test_wizard_template_keeps_upstream_strings`: the source contains the three banner text lines of upstream L43-L45, " stages", "Ready to start?", "Press Enter to continue", "[Enter keeps current]", "✓ Setup complete", "still to do by hand:", the change 25 example lines, "Generated by the `wizard` skill." and the change 25 placeholder. It contains no "/wizard".
  - `test_wizard_without_a_terminal_exits_2_and_touches_nothing`: a plain subprocess, `stdin=subprocess.DEVNULL`. The return code is 2. stdout is empty: no banner. stderr equals the change 23 message, with no "Traceback". `tmp_path` holds no `.env`.
  - `test_wizard_run_ends_cleanly_on_eof`: driver with `stdin_tty` true, `stdin = []`, `getpass = []` and `[["__run__"]]`. The value is 0 and stderr holds no "Traceback". `.env` is `b"STRIPE_PUBLISHABLE_KEY=\nSTRIPE_SECRET_KEY=\n"`, and `SKIPPED` holds the GitHub secret `STRIPE_SECRET_KEY`, because `confirm` reads end of file as no.
  - `test_write_env_creates_an_owner_only_file`: calls `write_env("A", "1")`. `tmp_path/.env` reads `b"A=1\n"`. On POSIX, `stat.S_IMODE` is `0o600`. stdout is `"  ✓ wrote A → .env\n"`, and `state.WRITTEN_ENV == ["A"]`.
  - `test_write_env_upserts_and_keeps_other_lines_byte_for_byte`: first write `b"# c\nA=old\nAB=keep\nexport A=x\nC=3\r\nX=\xff\nA=older\nD=4"` (no final newline). After `write_env("A", "new")` the file is `b"# c\nAB=keep\nexport A=x\nC=3\r\nX=\xff\nD=4\nA=new\n"`. A second identical call leaves the same bytes, so it is idempotent. No `.env.*.tmp` is left in `tmp_path`.
  - `test_write_env_keeps_the_old_file_when_the_replace_fails`: `fail_replace: true` with a prepared `.env`. The call errors with `OSError`, the file bytes are unchanged, and no temp file is left.
  - `test_env_keys_must_be_identifiers`: `write_env("BAD KEY", "x")` and `ask("1A", "q")` each error with `ValueError`, and the message contains the offending key.
  - `test_env_file_honours_the_environment_like_bash`: `["__get__", "ENV_FILE"]` gives `.env` with `ENV_FILE` unset, `.env` with `ENV_FILE=""`, and `custom.env` with `ENV_FILE=custom.env`. In the last case, `write_env` writes `tmp_path/custom.env`.
  - `test_existing_reads_the_last_matching_line`: a prepared `b"A=x=y\nAB=no\nA=last=one\n"`. `_existing("A")` is `"last=one"`, `_existing("Z")` is `""`, and with no file it is `""`.
  - `test_ask_offers_and_keeps_the_current_value`: every call is `ask("A", "Paste:")`. With no `.env`, stdin `["  typed \t"]` gives `"typed"`, and stdout is `"  Paste: "`. With `A=cur` in `.env`: stdin `[""]` gives `"cur"`, stdout `"  Paste: [Enter keeps current] "`, and "cur" is not in stdout. stdin `["new"]` gives `"new"`. Empty stdin (end of file) gives `"cur"`.
  - `test_ask_secret_reads_through_getpass_and_never_prints_the_value`: `getpass = ["sk_test_9"]`, giving `"sk_test_9"`. `getpass_prompts == [""]`. "sk_test_9" is in neither stdout nor stderr. With `getpass = []` (end of file) and `A=cur`, the result is `"cur"`.
  - `test_confirm_accepts_only_answers_starting_with_y`: "y", "Y", "yes" and " y" give True. "", "n", "no" and end of file give False. stdout of one call is `"  ? Go? [y/N] "`.
  - `test_pause_continues_on_end_of_file`: the default message gives `"  Press Enter to continue "`, with no error.
  - `test_open_url_launches_only_a_url_with_scheme_and_host`, with `browser = "opens"`. `open_url` of an https address for host `example.test` gives `browser_calls == [[that address, 2]]` and stdout `"  ↗ opening <address>\n"`. The placeholder, `"localhost:3000"` and `"Stripe: API keys"` add no browser call, and each prints `"  ↗ go to <arg>\n"`.
  - `test_open_url_warns_when_no_browser_opens`: "fails" gives the L73 warning text, and "raises" gives the L74 warning text (change 17), each after the "↗ opening" line.
  - `test_set_secret_is_a_guided_step_that_never_shows_the_value`: stdin `["y"]`, `set_secret("S", "v4lue")`. `WRITTEN_SECRET == ["S"]`, stdout ends with `"  ✓ set GitHub secret S\n"`, and "v4lue" is not in stdout. With stdin `["n"]`: `SKIPPED == ["GitHub secret S (set it by hand in the repo's CI settings)"]`, and the warning "skipped GitHub secret S; set it later" appears. End of file behaves like "n".
  - `test_set_var_shows_the_value_and_records_it`: every call is `set_var("V", "42")`. stdin `["y"]` gives `WRITTEN_VAR == ["V"]` and "give it this value: 42" in stdout. stdin `["n"]` gives `SKIPPED == ["GitHub variable V"]`.
  - `test_stage_counts_against_total_stages`: `set = {"TOTAL_STAGES": 3}`, `stage("First")`, `stage("Second")`. stdout is `"\n▸ Stage 1/3 · First\n\n▸ Stage 2/3 · Second\n"`. `banner("T")` with an empty stdin prints `"  3 stages"`.
  - `test_clear_and_colours_need_a_terminal`: `stdout_tty: true` and `env TERM=xterm-256color`. `stage("X")` output starts with `"\033[2J\033[3J\033[H"`, and `step("s")` output carries `"\033[34m"`. With `TERM=dumb`, or with `stdout_tty: false`, the output holds no escape byte.
  - `test_finish_summarises_everything`: set `WRITTEN_ENV = ["A", "B"]`, `WRITTEN_SECRET = ["S"]`, `WRITTEN_VAR = ["V"]` and `SKIPPED = ["x"]`. stdout is exactly `"\n  ✓ Setup complete\n  wrote 2 value(s) to .env: A B\n  set 1 GitHub secret(s): S\n  set 1 GitHub variable(s): V\n\n  ⚠ still to do by hand:\n    - x\n\n"`.
  - `test_run_wizard_ctrl_c_exits_130_with_the_stop_note`: `interrupt_on_read = 1`, `["__run__"]`. The value is 130, stdout ends with `"  ⚠ stopped. Re-run it later; it remembers values already saved.\n"`, and there is no "Traceback".
  - `test_template_example_runs_end_to_end_and_reruns_idempotently`. First run: stdin `["", "pk_test_123", "y"]`, `getpass = ["sk_test_456"]`, `["__run__"]`. The value is 0. `.env` is `b"STRIPE_PUBLISHABLE_KEY=pk_test_123\nSTRIPE_SECRET_KEY=sk_test_456\n"`. `browser_calls == []`, because the placeholder is never launched. "sk_test_456" is not in stdout. stdout contains "set 1 GitHub secret(s): STRIPE_SECRET_KEY". Second run in the same `tmp_path`: stdin `["", "", "y"]`, `getpass = [""]`. The `.env` bytes are unchanged, and "[Enter keeps current]" occurs twice in stdout.

  Never let a test reach the real `getpass`. Under `filterwarnings = ["error"]` its `GetPassWarning` would fail the run, and on a developer machine it would read `/dev/tty`. The two real-script subprocess tests stop at the guard before any read.

- **Continue degradation**: With the `continue` adapter listed, `.continue/prompts/wizard.md` carries only the name, description and body. Model invocation is lost: the agent no longer builds a wizard on its own when it reaches a step only the human can take, so the user starts it as `/wizard`. `scripts/wizard_template.py` does not travel, so the L10 link dangles and step 3 has no library to copy. The progress, gates, hidden entry, `.env` upsert and summary are lost, and an agent would write a script from scratch. No LICENSE copy travels. This holds unless the Continue IDE also reads the full skill natively from `.claude/skills/`. (D29)

**Ticket T07 notes.**

- **Order and prerequisites.** "Upstream order" is the order of upstream's plugin manifest: diagnosing-bugs is entry 2 and wizard entry 20. The two skills share nothing at run time and can be built in either order, but in one PR, since they share `test_debug_wizard.py` and its driver. T07 is blocked by T01. It needs the plugin-root `LICENSE`, the D32 ruff exclude, the `tests/plugins/mattpocock_skills/` package with `_expectations.py` and `test_gates.py` (G1-G22, G19 included), and the ATTRIBUTIONS placeholders `_Filled by T07._` under `### diagnosing-bugs` and `### wizard`. Replace only those two placeholder lines, never a heading. These are the plugin's only scripts: upstream's `misc/git-guardrails-claude-code` script is out of scope (D7). So T07 is the first lane to exercise G19 on real files. Make both `.py` files executable before `git add` (mode 100755); `test_sync.py` then checks that the synced copies stay executable in every native root. CI's `ruff check .` and `ruff format --check .` cover the scripts; D32 excludes only the plugin markdown. G19 runs mypy from a neutral directory, because `catalog/` is outside mypy's `files`.

- **Gate hygiene inside the scripts.**
  - G4 is case-insensitive and scans every file under `skills/`, the `.py` files included. No comment or string may name tput, curl, wget, gh, glab, jq, xdg-open, wslview, explorer.exe, shellcheck, npx, npm, yarn, deno or puppeteer. The reasons for the rewrite live in ATTRIBUTIONS, which sits outside `skills/` and may name them.
  - G3 forbids every URL form in the scripts, docstrings included: a scheme with its separator, the web-host prefix, a mail link, an scp-style remote or a bare domain plus path. That is why `_launchable` uses `urlsplit` and no scheme regex, and why the example placeholder has no scheme.
  - Each script is self-contained. `wizard_template.py` imports nothing from `hitl_loop_template.py`, or the reverse, because a skill never reaches into another skill. The small `_out` helpers are therefore written in each file.
  - Keep added prose free of em-dashes (upstream's own house rule).
  - The scripts must contain no `subprocess`/`os.system` call, so G5's script rule finds nothing.

- **Ambiguities resolved.**
  1. **D11 vs D22 on wizard's description.** D11 keeps frontmatter keys verbatim. D22 makes "an interactive bash wizard" false. Spec section 5.3 item 4 and 9.8 expect the one-word change, so the description says "Python".
  2. **D22's "read only .env templates ... and the CI config".** Applied literally, as section 9.8 and the section 7.1 test row state it: L20 keeps only the four `.env` templates and `.github/workflows/*`, and `README`, `docker-compose*` and framework config leave it (change 8). The T07 test checks that list and the absence of `` `.env.*`, `README` `` and `` `docker-compose*` ``.
  3. **The wizard's non-terminal guard (change 23).** D22 names a guard only for the hitl script, and section 7.1 asks the non-zero exit only of the HITL loop. The wizard's guard is not required by D22 or 7.1; it is added to enforce SKILL L43 and is recorded in section 5.3 item 10 and the 7.1 row. If review drops it, delete step 1 of `run_wizard`, and `test_wizard_without_a_terminal...` must then expect status 0 and an `.env` holding the two keys with empty values.
  4. **Ending a stream.** End of file mid-run differs on purpose. The hitl loop exits 2, because a loop without the human's answers is worthless (D22). The wizard treats it as an empty answer, upstream's `|| true` (D22, "EOF handling").
  5. **Guided steps.** `set_secret`/`set_var` ask with `confirm` (y/N), not `pause`. A "no" keeps upstream's fallback, the still-to-do list, so nothing is recorded as done that was not.
  6. **Wording kept minimal.** Diagnosing-bugs L59 loses ", a curl" rather than gaining a new example. L29 keeps "Playwright" alone; the audit's "or the browser-automation tool the project already uses" is not forced and is dropped. L35's "bash" becomes "Python", as in wizard's description.
  7. **Template L4 "/wizard".** Plain name under D17, as reasoned in change 13. If review classes it as human-facing, restore "/wizard" in the docstring; no test depends on it beyond `test_wizard_template_keeps_upstream_strings`.
  8. **Usage lines.** G19's usage-line check forces a docstring usage line in wizard's template (change 12) and the reworded one in hitl's (change 9).

- **Audit edits superseded by decisions.md or the spec.**
  - `python3 -m py_compile`: replaced by `ast.parse` (D22).
  - "shellcheck has no counterpart": replaced by "run `ruff check` or `mypy` if available" (D22).
  - "drop `.env` and `.env.*`, keep `.env.example`": all four exempt templates, per D22.
  - Diagnosing-bugs L10 "no glossary change": D21 adds the fallback.
  - The audit's project-toolchain entries (diagnosing-bugs L26, L27, L29, L59, L106; wizard L20 `.github/workflows/*`, L43): none would be hit, so all would be stale under G18.
  - `open_url` passing every argument to webbrowser: replaced by print-only for arguments without a scheme (D22).
  - "Keep every comment" for the hitl script: L7 and L10-L11 are reworded (changes 9, 10), as the verifier noted.
  - The open questions on CI secrets, `.env` reads, the example URL, the verify step and the non-TTY loop are settled by D22 (Q27.8-Q27.12).

- **Cross-skill references.** Neither id is renamed or dropped, and neither skill loads or names another skill, so T07 makes no inbound edit. The inbound mentions belong to T09, ask-matt:
  - L48 "**`/diagnosing-bugs`**" and L88 "**`/wizard`**" are router labels and keep the slash (D17).
  - L88's "It generates an interactive bash script that opens each URL, captures each value, and writes it into `.env` and GitHub secrets" is now false. T09 should write "It generates an interactive Python script that opens each URL, captures each value, writes it into `.env` and walks you through setting GitHub secrets" (D22). Hand that sentence to T09.

  The bucket README, the repository README and `docs/engineering/*.md` also describe both skills; they are not shipped (D10). The plugin README pairs diagnosing-bugs with superpowers' systematic-debugging (D33, T10). Neither skill is in `USER_INVOKED_IDS`, and neither carries `disable-model-invocation`.

- **Numbers for other gates.** The listing budget gains 156 (diagnosing-bugs) + 315 (wizard) = 471 description characters. The two skills add no load target (G14), no `/clear` or `/compact` (G7), no coupling marker (G8) and no URL (G3). D13-D16, D18, D19, D20, D23-D26 and D28 do not apply to either skill. D21 applies only to diagnosing-bugs; wizard never names a glossary file. D20 is about the agent opening a generated file. Wizard's browser opening happens in the human's run of the script.

## Appendix A.T08: the knowledge skills (research, retro, handoff, teach, writing-for-agents)

Conventions for this appendix:

- Plugin root: `catalog/plugins/mattpocock_skills/`. Every "Plugin path" below is relative to it. ATTRIBUTIONS.md cites the synced paths under the shared skill root, as `.agents/skills/<id>/...` (D12). Each "Changes" item below is one ATTRIBUTIONS bullet; "`SKILL.md` L11" means that file of the skill being described.
- Upstream: repository mattpocock/skills, tag v1.3.1, commit 24fe0ef7737efae15c87225755e9f6f5965e4888 (D4). The upstream repository-root `LICENSE` has sha256 `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5`.
- Every line number is an upstream v1.3.1 line number, checked against the files. Inserting `id:` moves every later `SKILL.md` line down by one. In retro, handoff and teach the D19 guard line and its blank line move the body down by two more. In writing-for-agents the D26 paragraph and its blank line move every line from upstream L8 on down by two more. Files moved to `references/` get no inserted lines, so their upstream line numbers stay valid.
- Sections follow the skill order of upstream's plugin manifest (`.claude-plugin/plugin.json`): research (14th), retro (19th), handoff (23rd), teach (24th), writing-for-agents (27th).
- Build each shipped file by copying the upstream bytes and making only the edits listed here. Do not retype files. Every upstream file here is UTF-8 with LF endings, ends in exactly one newline, and has no CR and no trailing whitespace; keep it that way. Non-ASCII to preserve: teach `MISSION-FORMAT.md` L16 (U+2026), teach `GLOSSARY-FORMAT.md` L23 (U+2013 in "1–10"), writing-for-agents `SKILL.md` L69 and L70 (U+2192). All other files here are ASCII.
- Two strings recur and must be byte-exact wherever they are used (ASCII apostrophes, semicolon, final period, no trailing space):
  - GUARD (D19): `Run this only when the user asked for it by name; otherwise stop.`
  - CLAUSE (D26): ``A file carrying the playbook's AUTOGENERATED sentinel (on line 1, or on the first line after a `SKILL.md` frontmatter), synced skill directories included, is changed in its source (the repo-local `playbook/` layer or the plugin that ships it), never by hand.`` (258 characters). It names the sentinel, it does not quote the sentinel text.

### A.T08.1 research (upstream skills/engineering/research; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/research/SKILL.md` (12 lines, ASCII) | `skills/research/SKILL.md` | Changes 1-2; ships as 13 lines |
  | `skills/engineering/research/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata: `interface.display_name` "Research", `interface.short_description` "Research from high-trust sources"; no policy block. Change 4 |
  | `LICENSE` (upstream repository root) | `skills/research/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 3 |

  Upstream has no sibling files and no scripts for this skill, so nothing moves and no link is rewritten.

- **Frontmatter**:

  ```yaml
  ---
  id: research
  name: research
  description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
  ---
  ```

  Changed: `id` is added as the first key (D11). `name` and `description` (238 characters) are verbatim. The description's "delegated to a background agent" describes what the user asks for; it is not an instruction, so it stays (D11). No `disable-model-invocation`, so there is no D19 guard line. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: research": insert the line `id: research` between the opening `---` (L1) and L2. (D11)
  2. [Capability rewording, nesting guard] `SKILL.md` L6, "Spin up a **background agent** to do the research, so you keep working while it reads." becomes:

     ```text
     If you are already running as a subagent or background agent, do the job below yourself. Otherwise, if your harness can run a **background agent**, spin one up to do the research, so you keep working while it reads. If it cannot, give the job to a subagent if your harness can run one, or else do it yourself.
     ```

     The first sentence is the D18.3 nesting guard. It comes first so that a delegate reads it before any spawn instruction: wayfinder starts research inside a subagent (upstream wayfinder L77 and L115, T04), and upstream's unconditional spawn made that agent spawn again. The ATTRIBUTIONS bullet says this fixes upstream issue 530, with no URL. The second and third sentences are the D17 capability phrasing, with the subagent-then-yourself fallback. Matt's clause "spin ... up to do the research, so you keep working while it reads" is kept inside the second sentence. "the job below" points at L8 "Its job:", which stays verbatim with steps L10-L12, so the steps apply to whoever does the research. (D17, D18.3)
  3. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE` ("Copyright (c) 2026 Matt Pocock"). (D4)
  4. [Dropped] `agents/openai.yaml` is not shipped. It has no policy block, so no invocation guard is lost. (D10)

  The complete shipped `SKILL.md`, ending in one newline:

  ```markdown
  ---
  id: research
  name: research
  description: Investigate a question against high-trust primary sources and capture the findings as a Markdown file in the repo. Use when the user wants a topic researched, docs or API facts gathered, or reading legwork delegated to a background agent.
  ---

  If you are already running as a subagent or background agent, do the job below yourself. Otherwise, if your harness can run a **background agent**, spin one up to do the research, so you keep working while it reads. If it cannot, give the job to a subagent if your harness can run one, or else do it yourself.

  Its job:

  1. Investigate the question against **primary sources** (official docs, source code, specs, first-party APIs), not a secondary write-up of them. Follow every claim back to the source that owns it.
  2. Write the findings to a single Markdown file, citing each claim's source.
  3. Save it where the repo already keeps such notes; match the existing convention, and if there is none, put it somewhere sensible and say where.
  ```

- **Project-toolchain allowlist**: none. The skill names no command. "first-party APIs" and "source code" (L10) are prose, and the primary-source reading uses the harness's own web search and fetch (a harness built-in, D2), which the text never names.
- **Skill-specific tests**: add `tests/plugins/mattpocock_skills/test_knowledge_skills.py::test_research_nesting_guard_precedes_delegation`. On the plugin source `skills/research/SKILL.md`, the first non-blank body line after the closing `---` must start with "If you are already running as a subagent or background agent, do the job below yourself." That line must also contain "if your harness can run a **background agent**, spin one up to do the research". The body must not contain "Spin up a **background agent**", the unconditional upstream form with a capital S. This pins D18.3, which no denylist covers: a re-pin (D5) that silently brings back upstream L6 would bring back the nesting that T04's wayfinder text relies on this skill to stop. Also add the row `research -> {}` (no load targets) to the plugin-wide load-target table (A.T02.1's `test_skill_loads.py` or T04's `test_execution_skill_loads.py`, whichever landed first).
- **Continue degradation**: the skill becomes the user-run `/research` prompt (`.continue/prompts/research.md`, body only). Its description no longer fires it from the model. Wayfinder's two loads (T04) reach it only where the Continue IDE also reads `.claude/skills` natively. No LICENSE copy travels. The body is complete, and its fallback lets the user's own session do the research inline. (D29)

### A.T08.2 retro (upstream skills/engineering/retro; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/retro/SKILL.md` (44 lines, ASCII) | `skills/retro/SKILL.md` | Changes 1-4; ships as 47 lines |
  | `skills/engineering/retro/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata: `display_name` "Retro", `short_description` "Conduct a retrospective on a coding session.", and `policy.allow_implicit_invocation: false` (L4-L5). Change 6 |
  | `LICENSE` (upstream repository root) | `skills/retro/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 5 |

  Upstream has no sibling files and no scripts for this skill.

- **Frontmatter**:

  ```yaml
  ---
  id: retro
  name: retro
  description: "Conduct a retrospective on a coding session."
  disable-model-invocation: true
  ---
  ```

  Changed: `id` is added as the first key (D11). `name`, `description` (verbatim with its double quotes, 44 characters inside them) and `disable-model-invocation: true` are verbatim. The description is human-facing and holds no `/name`. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: retro": insert the line `id: retro` between the opening `---` (L1) and L2. (D11)
  2. [Invocation guard] `SKILL.md` L6-L7: keep upstream's blank L6. Insert GUARD as the first line of body content, followed by one blank line, before L7 ("The user has asked for a **retrospective**."). The skill has no H1. Result in the shipped file: L7 blank (upstream L6), L8 GUARD, L9 blank, L10 = upstream L7. At sync the engine writes its sentinel above the guard; the source never carries the sentinel. (D19)
  3. [Capability rewording, cross-skill reference] `SKILL.md` L11 (shipped L14), "1. Call the Skill tool with `writing-for-agents` for the writing style guide." becomes:

     ```text
     1. Load the `writing-for-agents` skill for the writing style guide.
     ```

     This removes the Claude-only name "Skill tool" (D30). The target is model-invoked, keeps its id (D8) and ships in this ticket (A.T08.5). A user-invoked skill may load a model-invoked one (upstream `.agents/invocation.md` L8). (D17)
  4. [Generated files] `SKILL.md` L41 (shipped L44). Upstream ends the bullet with "usually only for **navigation pointers** to other files." Append one space and then CLAUSE, so the shipped line reads:

     ```text
     - `CLAUDE.md`/`AGENTS.md`: these files are pushed to the context window of any agent working in this repo. They should be used incredibly sparingly, usually only for **navigation pointers** to other files. A file carrying the playbook's AUTOGENERATED sentinel (on line 1, or on the first line after a `SKILL.md` frontmatter), synced skill directories included, is changed in its source (the repo-local `playbook/` layer or the plugin that ships it), never by hand.
     ```

     This is the one widened clause D26 asks for. It covers every retro candidate that targets a generated file: the "Global AGENTS.md" category (L20), "No-ops" in steering files (L22), and the "Skills" bullet (L44), whose synced skill directories are sync output. Those lines stay verbatim; no second sentence is added at L20. In a playbook consumer, `.claude/CLAUDE.md`, `.claude/rules/*.md`, `AGENTS.md` and every synced `SKILL.md` carry the sentinel, so a hand edit would be overwritten at the next `playbook sync`. Elsewhere only the guard-generated-outputs hook (Claude Code and OpenCode only) catches such an edit. (D26)
  5. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE`. (D4)
  6. [Dropped] `agents/openai.yaml` is not shipped. The Dropped bullet must say that it carried `policy.allow_implicit_invocation: false`, the Codex half of upstream's user-only invocation (upstream `.agents/invocation.md` L10). Codex reads the shared skill root `.agents/skills/`, so there the Change 2 guard line is the only guard left. (D10, D19)

  Everything else is verbatim: L13's "searching through session logs on this machine", the seven categories at L17-L23, the "reviewer agent" and `CODING_STANDARDS.md` wording at L19 and L42 (retro never names code-review, so the two-axis-review rename does not reach it, D8), and L44's prose mention "Follow the advice in the `writing-for-agents` skill." (a plain name, D17).

- **Project-toolchain allowlist**: none. L18 (`package.json`/build-tool `lint`/`check` scripts, the CI workflow), L19 ("a custom rule in the repo's own linter, a new pre-commit hook, or a new CI job") and L23 ("Teeing dev server logs") are project toolchain, but no D30 pattern flags them. `package.json` contains no denied name, and the code spans `package.json`, `lint` and `check` start with no ambiguous word. An entry for them would be stale and fail the two-way check. L21's "(CLI's, MCP's)" is prose.
- **Skill-specific tests**: add `tests/plugins/mattpocock_skills/test_knowledge_skills.py::test_generated_file_clause_present`, parametrized over `("retro", "SKILL.md")` and `("writing-for-agents", "SKILL.md")`. Each file must contain the CLAUSE constant exactly once. The test also asserts `SENTINEL.split()[0] in CLAUSE`, with `SENTINEL` imported from `coding_agent_playbook._sentinel`. That ties the clause to the real marker word without retyping or paraphrasing the sentinel text (D26). Also add the row `retro -> {writing-for-agents}` to the plugin-wide load-target table. Its regex (G14's) finds exactly one match, at shipped L14, and the target is not in `USER_INVOKED_IDS` (upstream invariant, `.agents/invocation.md` L22).
- **Continue degradation**: the skill becomes the user-run `/retro` prompt. Step 1's load cannot fire, because writing-for-agents is only a prompt there unless the Continue IDE reads `.claude/skills` natively, so the user runs `/writing-for-agents` first to get the style guide. The guard line and the D26 clause travel in the body. `disable-model-invocation` (harmless for a user-run prompt) and the LICENSE copy do not. (D29)

### A.T08.3 handoff (upstream skills/productivity/handoff; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/productivity/handoff/SKILL.md` (16 lines, ASCII) | `skills/handoff/SKILL.md` | Changes 1-3; ships as 19 lines |
  | `skills/productivity/handoff/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata: `display_name` "Handoff", `short_description` "Compact a conversation into a handoff", and `policy.allow_implicit_invocation: false` (L4-L5). Change 5 |
  | `LICENSE` (upstream repository root) | `skills/handoff/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 4 |

  Upstream has no sibling files and no scripts for this skill.

- **Frontmatter**:

  ```yaml
  ---
  id: handoff
  name: handoff
  description: Compact the current conversation into a handoff document for another agent to pick up.
  argument-hint: "What will the next session be used for?"
  disable-model-invocation: true
  ---
  ```

  Changed: `id` is added as the first key (D11). `name`, `description` (86 characters), `argument-hint` (with its quotes) and `disable-model-invocation: true` are verbatim and stay in upstream order. The description's "Compact" is an English verb, not `/compact`, so the D30 Claude-only-name pattern (``(?<![\w/])/compact\b``) does not fire. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: handoff": insert the line `id: handoff` between the opening `---` (L1) and L2. (D11)
  2. [Invocation guard] `SKILL.md` L7-L8: keep upstream's blank L7. Insert GUARD as the first line of body content, followed by one blank line, before L8 ("Write a handoff document summarising ..."). Result: L8 blank (upstream L7), L9 GUARD, L10 blank, L11 = upstream L8. (D19)
  3. [Capability rewording] `SKILL.md` L10 (shipped L13), "naming which skills the next agent should call the Skill tool for." becomes "naming which skills the next session should use." The complete shipped line:

     ```text
     Include a "suggested skills" section in the document, naming which skills the next session should use.
     ```

     This is the exact D25 wording. "Use" is neutral on purpose: the suggested skills are often user-invoked (retro, teach, handoff itself), which the next agent cannot load (upstream `.agents/invocation.md` L22). The person starting that session runs those. The edit also removes "Skill tool" (D30). (D25, D17)
  4. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE`. (D4)
  5. [Dropped] `agents/openai.yaml` is not shipped. As for retro, the Dropped bullet records that `policy.allow_implicit_invocation: false` is gone and that the Change 2 guard line is the only guard left outside Claude Code. (D10, D19)

  The complete shipped `SKILL.md`, ending in one newline:

  ```markdown
  ---
  id: handoff
  name: handoff
  description: Compact the current conversation into a handoff document for another agent to pick up.
  argument-hint: "What will the next session be used for?"
  disable-model-invocation: true
  ---

  Run this only when the user asked for it by name; otherwise stop.

  Write a handoff document summarising the current conversation so a fresh agent can continue the work. Save to the temporary directory of the user's OS - not the current workspace.

  Include a "suggested skills" section in the document, naming which skills the next session should use.

  Do not duplicate content already captured in other artifacts (specs, plans, ADRs, issues, commits, diffs). Reference them by path or URL instead.

  Redact any sensitive information, such as API keys, passwords, or personally identifiable information.

  If the user passed arguments, treat them as a description of what the next session will focus on and tailor the doc accordingly.
  ```

  Verbatim on purpose:
  - L8 "Save to the temporary directory of the user's OS". Nothing is opened, so D20 does not apply.
  - L12 "Reference them by path or URL instead". "URL" is a word, not a URL, so the D30 URL gate (a scheme, a www prefix, a git-at or mailto address, a bare domain plus path) does not fire. With the local tracker an issue is referenced by path (D13).

- **Project-toolchain allowlist**: none.
- **Skill-specific tests**: none beyond the shared gate. The D30 Claude-only-name gate catches a re-pinned "Skill tool", and the D19 gate checks the guard. Add the row `handoff -> {}` to the plugin-wide load-target table, so the suggested-skills line is never turned into a load.
- **Continue degradation**: the skill becomes the user-run `/handoff` prompt. Continue keeps only id, name, description and slash, so `argument-hint` is dropped and no hint shows. The body, guard line included, is complete. No LICENSE copy travels. (D29)

### A.T08.4 teach (upstream skills/productivity/teach; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/productivity/teach/SKILL.md` (140 lines, ASCII) | `skills/teach/SKILL.md` | Changes 1-5; ships as 143 lines |
  | `skills/productivity/teach/MISSION-FORMAT.md` (31 lines, U+2026 at L16) | `skills/teach/references/MISSION-FORMAT.md` | Moved byte-identical (Change 6) |
  | `skills/productivity/teach/RESOURCES-FORMAT.md` (32 lines, ASCII) | `skills/teach/references/RESOURCES-FORMAT.md` | Moved (Change 7); Changes 10-11 |
  | `skills/productivity/teach/LEARNING-RECORD-FORMAT.md` (46 lines, ASCII) | `skills/teach/references/LEARNING-RECORD-FORMAT.md` | Moved (Change 8); Change 12 |
  | `skills/productivity/teach/GLOSSARY-FORMAT.md` (35 lines, U+2013 at L23) | `skills/teach/references/GLOSSARY-FORMAT.md` | Moved (Change 9); Change 13 |
  | `skills/productivity/teach/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata: `display_name` "Teach", `short_description` "Learn a concept in a guided workspace", and `policy.allow_implicit_invocation: false` (L4-L5). Change 15 |
  | `LICENSE` (upstream repository root) | `skills/teach/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 14 |

  The skill directory then holds exactly `SKILL.md` and `references/` (five files). There is no `scripts/`.

- **Frontmatter**:

  ```yaml
  ---
  id: teach
  name: teach
  description: Teach the user a new skill or concept, within this workspace.
  disable-model-invocation: true
  argument-hint: "What would you like to learn about?"
  ---
  ```

  Changed: `id` is added as the first key (D11). `name`, `description` (61 characters), `disable-model-invocation: true` and `argument-hint` (with its quotes) are verbatim. Keep upstream's key order, which differs from handoff's. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: teach": insert the line `id: teach` between the opening `---` (L1) and L2. (D11)
  2. [Invocation guard] `SKILL.md` L7-L8: keep upstream's blank L7. Insert GUARD as the first line of body content, followed by one blank line, before L8 ("The user has asked you to teach them something."). Result: L8 blank, L9 GUARD, L10 blank, L11 = upstream L8. (D19)
  3. [Workspace root] `SKILL.md` L12 (shipped L15), "Treat the current directory as a teaching workspace." becomes "Treat the current directory as a teaching workspace, never this skill's own directory." The rest of the line, "The state of their learning is captured in this directory in several files:", stays. The ATTRIBUTIONS bullet says this guards against upstream issue 377 (no URL): agents resolved `./lessons/` and the other `./` workspace paths against the skill's install directory. Here the cost is higher, because the skill now has a `references/` folder next to the workspace's `./reference/`, and the moved `LEARNING-RECORD-FORMAT.md` (L3, L27: `./learning-records/`) sits one level deeper. A misplaced course would land in a synced skill directory such as `.claude/skills/teach/`. (D24)
  4. [Restructure, link rewrites] `SKILL.md`, three links to moved format files. The link text is a bare file name (not code-formatted), so it stays, and the target loses its leading `./`. (D10)

     ```text
     L14 before: Use the format in [MISSION-FORMAT.md](./MISSION-FORMAT.md).
         after:  Use the format in [MISSION-FORMAT.md](references/MISSION-FORMAT.md).
     L16 before: Use the format in [RESOURCES-FORMAT.md](./RESOURCES-FORMAT.md).
         after:  Use the format in [RESOURCES-FORMAT.md](references/RESOURCES-FORMAT.md).
     L17 before: Use the format in [LEARNING-RECORD-FORMAT.md](./LEARNING-RECORD-FORMAT.md).
         after:  Use the format in [LEARNING-RECORD-FORMAT.md](references/LEARNING-RECORD-FORMAT.md).
     ```

     Unchanged on purpose:
     - L19 `[Assets](#assets)`, an in-document anchor to the L63 heading "## Assets".
     - The workspace paths `./reference/*.html` (L15), `./learning-records/*.md` (L17), `./lessons/*.html` (L18), `./assets/*` (L19), `./lessons/` (L49) and `./assets/` (L65, L67). They are workspace paths in the current directory, not this skill's `references/`.
  5. [Opening a generated file] `SKILL.md` L55 (shipped L58), "If possible, open the lesson file for the user by running a CLI command." becomes:

     ```text
     When the lesson file is written, open it for the user if your harness can open files, and tell them the absolute path either way.
     ```

     This is D20's exact sentence, "Open it for the user if your harness can open files, and tell them the absolute path either way.", after a lead-in clause that names its object, because L55 is its own paragraph and "it" needs an antecedent. "If possible" goes, because the capability condition replaces it. "by running a CLI command" goes too: it implied an OS-specific launcher (`open`, `xdg-open`, `start`, `wslview` or a browser binary), an imposed tool (D2). From "open it" on, the sentence matches T06's improve-codebase-architecture sentence word for word, apart from the capital. (D20, D2)
  6. [Restructure] Move `MISSION-FORMAT.md` to `references/MISSION-FORMAT.md`, byte-identical. It has no links, URLs or glossary mentions. (D10)
  7. [Restructure] Move `RESOURCES-FORMAT.md` to `references/RESOURCES-FORMAT.md`. Its only content changes are Changes 10 and 11. (D10)
  8. [Restructure] Move `LEARNING-RECORD-FORMAT.md` to `references/LEARNING-RECORD-FORMAT.md`. Its only content change is Change 12. The wiki-links `[[MISSION.md]]` (L36) and `[[GLOSSARY.md]]` (L41) name workspace files, and the link validator does not parse them, so they need no rewrite. (D10)
  9. [Restructure] Move `GLOSSARY-FORMAT.md` to `references/GLOSSARY-FORMAT.md`. Its only content change is Change 13. Upstream has no link to it from `SKILL.md` or the other format files. None is added, because no decision forces one, so it stays as unlinked as upstream has it. (D10)
  10. [No external URLs] `references/RESOURCES-FORMAT.md` L12, L14 and L19, inside the fenced ```` ```md ```` template (L7-L23). Each link keeps its markdown shape and text. Only the target changes, to the placeholder `{link}`. This is the one exception to "link text as plain text", in the template's own `{...}` placeholder style (compare `{gym name}` at L21). (D24, D4)

      ```text
      L12 before: ...Strength Training_ by Zatsiorsky & Kraemer](<https URL on example.com>)
          after:  - [Book: _The Science and Practice of Strength Training_ by Zatsiorsky & Kraemer]({link})
      L14 before: ...by Greg Nuckols (Stronger By Science)](<https URL on example.com>)
          after:  - [Article: "How Much Should I Train?" by Greg Nuckols (Stronger By Science)]({link})
      L19 before: - [r/weightroom](<https URL on reddit.com for the community r/weightroom>)
          after:  - [r/weightroom]({link})
      ```

      The angle-bracket "before" targets above describe the upstream URLs instead of copying them, so this spec carries no URL. Replace the whole parenthesised target, from `(` to `)`, on each line. The community name `r/weightroom` stays as link text, and the reddit.com and example.com domains go. The link validator masks fenced code, and T06's `test_relative_links_resolve` exempts `{link}`.
  11. [Restructure, link rewrite] `references/RESOURCES-FORMAT.md` L29, "Mirrors the philosophy in [SKILL.md](./SKILL.md)." becomes "Mirrors the philosophy in [SKILL.md](../SKILL.md).". The back-link from the moved file now resolves to the skill's `SKILL.md`, inside the synced skill directory. (D10)
  12. [Glossary naming] `references/LEARNING-RECORD-FORMAT.md` L41, "- Anything already captured tersely in [[GLOSSARY.md]] as a term definition. Don't duplicate." becomes:

      ```text
      - Anything already captured tersely in [[GLOSSARY.md]] (or [[CONTEXT.md]] if the repo already has one) as a term definition. Don't duplicate.
      ```

      The fallback copies the mention's own form (a wiki-link). The space after `]]` keeps the link extractor from reading `]] (` as an inline link. (D21)
  13. [Glossary naming] `references/GLOSSARY-FORMAT.md` L3, "`GLOSSARY.md` is the canonical language for this teaching workspace." becomes "`GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) is the canonical language for this teaching workspace." The rest of L3 stays. The L1 heading "# GLOSSARY.md Format" stays, by the T02 heading rule. The fenced example L7-L25 does not name the file. (D21)
  14. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE`. (D4)
  15. [Dropped] `agents/openai.yaml` is not shipped. The Dropped bullet records that `policy.allow_implicit_invocation: false` is gone and that the Change 2 guard line is the only guard left outside Claude Code. (D10, D19)

  Everything else is verbatim, including:
  - L30 "Never trust your parametric knowledge": resource finding uses the harness's own web search and fetch (D2), which the text does not name.
  - L95's citations, "links to external resources": these are URLs the agent writes into the consumer's lessons, not plugin text.
  - L65-L69's assets: self-authored components in `./assets/`, with no CDN named.
  - "Think Tufte" and the example authors.

- **Project-toolchain allowlist**: none. Near-misses that must not get a (stale) entry:
  - Shipped L58's "open it for the user" and `MISSION-FORMAT.md` L28's "Ship a Rust CLI" are prose, so neither `open` nor `CLI` is in command position.
  - Every fenced template line in the four format files starts with `#`, `-`, `{`, `**`, `_Avoid_` or a capitalised prose word, never with an ambiguous word.
- **Skill-specific tests**: in `tests/plugins/mattpocock_skills/test_knowledge_skills.py`:
  1. `test_teach_workspace_clause`: `skills/teach/SKILL.md` contains "Treat the current directory as a teaching workspace, never this skill's own directory." (a D24 replay guard).
  2. `test_teach_resources_link_placeholders`: `references/RESOURCES-FORMAT.md` contains exactly three `]({link})` targets, all between the opening ```` ```md ```` fence (L7) and its closing fence (L23), and no other `](` target inside that fence. This pins D24's link shape against a re-pin. The URL gate alone would also pass a plain-text rewrite.
  3. `test_teach_opens_lesson_by_capability`: `SKILL.md` contains "When the lesson file is written, open it for the user if your harness can open files, and tell them the absolute path either way." and not "CLI command". If a plugin-wide D20 test already exists (T06's `test_opener_is_capability_phrased` is per-skill), add teach to it with the D20 tail as the shared substring instead.

  Also extend A.T02.2's `tests/plugins/mattpocock_skills/test_glossary_fallback.py::test_glossary_mentions_carry_context_fallback` with `("teach", "references/GLOSSARY-FORMAT.md")` and `("teach", "references/LEARNING-RECORD-FORMAT.md")`. No exemption is needed: the L1 heading is skipped by the test, and L3 and L41 carry `CONTEXT.md`. Add the row `teach -> {}` to the plugin-wide load-target table. T06's `test_relative_links_resolve` picks up teach's four relative links (`SKILL.md` L14, L16, L17 and `RESOURCES-FORMAT.md` L29); `#assets` and the three `{link}` targets are exempt there.
- **Continue degradation**: the skill becomes the user-run `/teach` prompt without `references/`. The three format links (upstream L14, L16, L17) dangle, so MISSION.md, RESOURCES.md and the learning records lose their formats, and the unlinked glossary format is gone too. `argument-hint` and the LICENSE copy are dropped. The guard line, the L12 workspace clause and the D20 sentence still travel. (D29)

### A.T08.5 writing-for-agents (upstream skills/productivity/writing-for-agents; vendored with listed changes; model-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/productivity/writing-for-agents/SKILL.md` (81 lines, U+2192 at L69-L70) | `skills/writing-for-agents/SKILL.md` | Changes 1-4; ships as 84 lines |
  | `skills/productivity/writing-for-agents/SKILL-MECHANICS.md` (22 lines, ASCII) | `skills/writing-for-agents/references/SKILL-MECHANICS.md` | Moved (Change 5); Change 6 |
  | `skills/productivity/writing-for-agents/agents/openai.yaml` (3 lines) | not shipped | Codex UI metadata: `display_name` "Writing for Agents", `short_description` "Write documents agents consume"; no policy block. Change 8 |
  | `LICENSE` (upstream repository root) | `skills/writing-for-agents/references/LICENSE` | Byte-identical copy of the plugin-root `LICENSE`; Change 7 |

- **Frontmatter**:

  ```yaml
  ---
  id: writing-for-agents
  name: writing-for-agents
  description: Writing documents for agents. Use when creating or editing skills, or modifying AGENTS.md or CLAUDE.md.
  ---
  ```

  Changed: `id` is added as the first key (D11). `name` and `description` (103 characters) are verbatim. The trigger "modifying AGENTS.md or CLAUDE.md" stays: the skill guides the wording and never writes those files itself. No `disable-model-invocation`, so there is no D19 guard line. No `playbook:` block (D11).

- **Changes**:
  1. [Frontmatter] `SKILL.md` L1-L2, "name: writing-for-agents": insert the line `id: writing-for-agents` between the opening `---` (L1) and L2. (D11)
  2. [Generated files] `SKILL.md`, after L7. Keep L6 ("Reference for writing any document an agent consumes: ...") and the blank L7 byte-identical. Insert CLAUSE as its own paragraph, followed by one blank line, before L8. The shipped file is then: L7 = upstream L6, L8 blank, L9 CLAUSE, L10 blank, L11 = upstream L8. The placement follows the progressive-disclosure rule this skill teaches: every branch needs the clause (skill, `AGENTS.md`/`CLAUDE.md`, pointed-at doc), so it goes right after the paragraph that names those kinds, ahead of the skill-only pointer. In a playbook consumer, this skill fires on exactly the files that are generated (`AGENTS.md`, `.claude/CLAUDE.md`, `.claude/rules/*.md` and synced skill directories), so the clause sends the edit to its source. (D26)
  3. [Restructure, link rewrite] `SKILL.md` L8 (shipped L11), "read [`SKILL-MECHANICS.md`](SKILL-MECHANICS.md) for frontmatter" becomes "read [`references/SKILL-MECHANICS.md`](references/SKILL-MECHANICS.md) for frontmatter". The link text is a code-formatted path, so it carries the new location too (superpowers style: every mention of a moved file, inline paths included, is written relative to the skill directory). (D10)
  4. [Restructure, link rewrite] `SKILL.md` L59 (shipped L62), "- **By invocation**, skill-specific: see [`SKILL-MECHANICS.md`](SKILL-MECHANICS.md)." becomes "- **By invocation**, skill-specific: see [`references/SKILL-MECHANICS.md`](references/SKILL-MECHANICS.md).". (D10)
  5. [Restructure] Move `SKILL-MECHANICS.md` to `references/SKILL-MECHANICS.md`. Its only content change is Change 6. (D10)
  6. [Restructure, link rewrite] `references/SKILL-MECHANICS.md` L3, "[`writing-for-agents`](SKILL.md)" becomes "[`writing-for-agents`](../SKILL.md)". The link text is the skill name, not a path, so it stays. The three inline `SKILL.md` mentions (L3 "the universal reference in `SKILL.md`", L9 "the pointer-writing rules in `SKILL.md`", L18 "the sequence cut lives in `SKILL.md`") name the skill's main file relative to the skill directory. That file did not move, so they stay. (D10)
  7. [License copies] Add `references/LICENSE`, a byte-identical copy of the plugin-root `LICENSE`. (D4)
  8. [Dropped] `agents/openai.yaml` is not shipped. It has no policy block. (D10)

  Verbatim on purpose:
  - D28: the sibling-file advice, `SKILL.md` L35 ("Spans a sibling file in the same folder ...") and `SKILL-MECHANICS.md` L14 ("Push it to a plain file outside the skill system ..."). The engine syncs only `SKILL.md`, `scripts/` and `references/`, and this skill's own sibling file had to move, but D28 keeps Matt's advice.
  - L49 "a hand-off or a subagent dispatch", which explains context boundaries and does not instruct a dispatch.
  - L6, L12 and L24's `AGENTS.md`/`CLAUDE.md` mentions, which name document kinds.
  - L79's `package.json` example.

- **Project-toolchain allowlist**: none. L79 ("(`package.json` scripts, config files, the directory layout, `--help` output)") names the consumer's own environment, but no D30 pattern flags it. `package.json` and `--help` contain no denied name and start with no ambiguous word, so an entry would be stale.
- **Skill-specific tests**: covered by A.T08.2's `test_generated_file_clause_present` (the `("writing-for-agents", "SKILL.md")` case) and the row `writing-for-agents -> {}` in the plugin-wide load-target table. T06's `test_relative_links_resolve` picks up its three relative links (`SKILL.md` L8 and L59, `SKILL-MECHANICS.md` L3), and the D30 path check resolves the two code-formatted `references/SKILL-MECHANICS.md` mentions.
- **Continue degradation**: the skill becomes the user-run `/writing-for-agents` prompt. The model no longer reaches it when editing skills, AGENTS.md or CLAUDE.md, and retro's step-1 load cannot reach it. The two `references/SKILL-MECHANICS.md` links dangle, so the invocation and router-skill mechanics are lost. No LICENSE copy travels. The D26 clause stays in the body. (D29)

### Ticket T08 notes

- **Order within the ticket.** The five skills can be written in any order. retro's step-1 load targets writing-for-agents, but G14 and the A.T02.1 load test check targets against `FINAL_IDS - USER_INVOKED_IDS`, not present directories; T10's inventory pin checks presence. Prerequisites from T01: the plugin-root `catalog/plugins/mattpocock_skills/LICENSE`, the source every `references/LICENSE` copy is made from, and the D32 ruff extend-exclude for `catalog/plugins/mattpocock_skills/**/*.md`, so the vendored markdown is never reformatted.
- **Shared strings.** GUARD (retro, handoff, teach) and CLAUSE (retro, writing-for-agents) must be byte-exact copies of the strings in this appendix's conventions. The D19 gate and `test_generated_file_clause_present` look for exact substrings. Make every edit as a text insertion or replacement on the upstream bytes; do not re-dump the YAML. At sync the SkillWriter puts `name` first, keeps `id`, re-dumps the frontmatter and writes the sentinel as the first body line. So synced copies differ from the source, and the gates run on the plugin source.
- **Cross-skill references (no renames, no drops).** No T08 skill is renamed (D8) or dropped (D7), so no other ticket rewrites an inbound reference to these ids. Inbound references, all owned by other tickets:
  - wayfinder L77 and L115 (T04) load research. T04's text depends on A.T08.1 Change 2's nesting guard, and the two fallbacks agree: without subagents, wayfinder's session loads research itself, and research then applies its own capability check (inline when the harness has neither background agents nor subagents).
  - ask-matt `SKILL.md` L18, L19, L21 and L73 (`/handoff`), L32 (`/retro`), L86 (`/research`), L90 (`/teach`) and L91 (`/writing-for-agents`) are router labels, and ask-matt `PHASE-BOUNDARIES.md` L13, L27, L34 and L49 (`/handoff`) are too. All keep the slash (D17). ask-matt L86 still says research delegates "to a **background agent**". Whether ask-matt mirrors A.T08.1's fallback there is decided in ask-matt's ticket; research's final behaviour is "guard, then background agent, then subagent, then inline". PHASE-BOUNDARIES L49's `/compact` is ask-matt's D17/D30 item, not T08's.
  - implement-spec L15's "research notes" is plain prose. Outbound, only retro names another skill (writing-for-agents, L11 and L44).
- **D21 in teach (ambiguity resolved).** D21 counts 16 upstream files that name GLOSSARY.md, and that count includes teach's `GLOSSARY-FORMAT.md` and `LEARNING-RECORD-FORMAT.md`. So both get the literal D21 parenthetical, and T02's D21 test is extended to them. Note that teach's GLOSSARY.md is the teaching workspace's own glossary: upstream's CONTEXT.md-to-GLOSSARY.md rename (upstream CHANGELOG) did not cover teach. A teaching workspace is normally its own directory (MISSION-FORMAT's "One mission per workspace"; Change 3's clause), where no repo CONTEXT.md exists and the fallback never fires. Only teach run at a repo root that already has a domain CONTEXT.md would read that file as its glossary. The same collision with a domain GLOSSARY.md already exists upstream. If review rejects the two teach D21 edits, drop A.T08.4 Changes 12 and 13 together and the two teach rows of the D21 test; nothing else depends on them.
- **D26 placement (ambiguity resolved).** D26 asks for "one widened clause" in each of the two skills. In retro it extends the upstream L41 bullet, which is the line the audit's clause sat on and the verifier widened. It also covers L20, L22 and L44, so the audit's separate L20 sentence is not added. In writing-for-agents it is a new paragraph after L6, because no single upstream line covers all the document kinds the clause applies to, and appending it to L6 would bury the paragraph's thesis. Both use the identical CLAUSE so that one test constant checks both. The sentinel text itself (`coding_agent_playbook._sentinel.SENTINEL`) is never quoted or paraphrased in the skills or in tests (D26).
- **SKILL-MECHANICS L10 kept verbatim.** The audit table proposed a qualifier on `disable-model-invocation` at `references/SKILL-MECHANICS.md` L10. No decision forces it (D4): support for a frontmatter key is not one of D2's harness built-ins, so D17's capability phrasing does not reach it. It is not applied. The plugin README already says that only Claude Code honours `disable-model-invocation` (D33).
- **Superseded audit proposals.** decisions.md replaces these audit and verify proposals:
  - research: `agents/openai.yaml` "kept, not synced" becomes "not shipped" (D10). The verifier's "loses nothing under Continue" is wrong: the LICENSE copy is lost. The nesting guard is adopted (D18.3).
  - retro: the auditor's extra L20 sentence and its three-file list are replaced by the single widened L41 CLAUSE, which also covers synced skill directories (D26). The audit's paraphrase of the sentinel (with a hyphen for the em dash) must not be copied anywhere.
  - handoff: "the next agent should load" is replaced by D25's "the next session should use".
  - teach:
    - L55's `webbrowser` one-liner is replaced by D20's capability sentence, so no command is named at all.
    - The audit's "NO CHANGE" for the two glossary mentions is replaced by D21.
    - The verifier's optional L12 clause is adopted (D24).
    - The `{link}` placeholder is adopted (D24). Ignore the audit's garbled "(...)({link})".
  - writing-for-agents: the auditor's "keep the link text" at L8 and L59 is replaced by link text that carries `references/` (code-formatted path). The D26 paragraph is new (Q32.12).
- **Decisions checked and not applied.**
  - D13-D16: no tracker, setup, `.scratch/` or ticket text. research's notes go "where the repo already keeps such notes", not into the tracker.
  - D18.1, D18.2, D18.4-D18.7: no two-skill load, fact lookup, wayfinder, implement-spec or review text.
  - D22 and D23: no script, no report.
  - D27: no TypeScript, Jest or JS-frontend example. The JS-first `package.json` examples (retro L18, writing-for-agents L79) stay verbatim. If ATTRIBUTIONS' stack-assumption record lists JS-first consumer-file examples, name these two lines there, as a record, not as changes.
  - No URL remains: only teach `RESOURCES-FORMAT.md` had any.
  - No imposed tool remains: only teach L55 implied one.
  - No coupling marker, no `/clear` or `/compact`. "Skill tool" occurs only at retro L11 and handoff L10, and both are rewritten.
  - None of the three user-invoked descriptions holds a `/name`.
- **D19 and F6.** retro, handoff and teach are 3 of the 15 D19 skills. The spec must still record that the skills-first spec's F6 keeps `disable-model-invocation`. `argument-hint` (handoff, teach) passes through verbatim (D11). It is a Claude Code key that agent_harness moves to its manifest sidecar and Continue drops.
- **Layout gate cases.** teach's workspace directory `./reference/` (singular, SKILL.md L15) must not be matched by the D30 "references/ path resolves" check, so match `references/` only. Two kinds of name must not trip the URL rule's "bare domain + path" check: `CONTEXT.md` and `GLOSSARY.md` (no path follows them), and `r/weightroom` (no top-level domain).
- **README items (D33, README ticket, not T08).** These go in the plugin README, not in these skill files:
  - the superpowers pair writing-for-agents / writing-skills (their descriptions overlap on "creating or editing skills");
  - retro, handoff and teach in the user-invoked-only list, with the note that only Claude Code honours `disable-model-invocation`;
  - the generic note that a personal skill with the same name outranks a project skill in Claude Code, which matters for `retro`.
- **Listing budget (D30, D31).** T08's five descriptions total 532 characters, all unchanged from upstream: research 238, writing-for-agents 103 (both model-invoked), handoff 86, teach 61 and retro 44 (user-invoked).
- **ATTRIBUTIONS wording.** Use "vendored content" and "bundled plugin", and cite paths as `.agents/skills/<id>/` (D12). The two upstream issue numbers (530 for research, 377 for teach) are named without URLs (D4).

## Appendix A.T09: the router (ask-matt)

Conventions for this appendix. The plugin root is `catalog/plugins/mattpocock_skills/`, and every "Plugin path" is the source path in the engine repo. Changes cite synced paths under the shared skill root (`.agents/skills/ask-matt/...`, D12), as ATTRIBUTIONS will. Every L-number is an upstream v1.3.1 line (repository mattpocock/skills, tag v1.3.1, commit 24fe0ef7737efae15c87225755e9f6f5965e4888), checked against the checkout.

Build each shipped file by copying the upstream bytes and making only the edits listed here. Do not retype. Both upstream files are UTF-8 with LF endings, no CR, no trailing whitespace and exactly one final newline. Keep that. Keep these non-ASCII characters:

- SKILL.md: U+2192 at L13, L23, L26, L48 and L50 (the one at L44 goes with change 12), and U+2013 in "steps 1–3" at L36.
- PHASE-BOUNDARIES.md: U+2192 at L21 and L29.

Insert the `id:` line as text. Do not load and re-dump the YAML. The D19 guard line is this exact sentence, in its own paragraph: `Run this only when the user asked for it by name; otherwise stop.`

### A.T09.1 ask-matt (upstream skills/engineering/ask-matt; vendored with listed changes; user-invoked)

- **Files**:

  | Upstream file | Plugin path | Note |
  |---|---|---|
  | `skills/engineering/ask-matt/SKILL.md` (95 lines, 12,452 bytes) | `catalog/plugins/mattpocock_skills/skills/ask-matt/SKILL.md` | Vendored content, changes 1-24. Change 1 adds 1 line, change 2 adds 2 and change 12 removes 4, so the file ends at 94 lines. |
  | `skills/engineering/ask-matt/PHASE-BOUNDARIES.md` (55 lines, 4,249 bytes) | `catalog/plugins/mattpocock_skills/skills/ask-matt/references/PHASE-BOUNDARIES.md` | Moved (D10, change 25) and edited by changes 26-35. Still 55 lines. It has no links, so nothing in it points back at SKILL.md. |
  | `skills/engineering/ask-matt/agents/openai.yaml` (5 lines) | not shipped | Codex UI metadata (D10): `display_name: "Ask Matt"`, `short_description: "Find the right skill or workflow"`, `policy.allow_implicit_invocation: false`. Goes under Dropped (change 37). |
  | upstream repository-root `LICENSE`, through the plugin-root copy `catalog/plugins/mattpocock_skills/LICENSE` | `catalog/plugins/mattpocock_skills/skills/ask-matt/references/LICENSE` | Byte-identical copy of the plugin-root LICENSE, sha256 `0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5` (D4, change 36). SKILL.md does not mention it. |

  The plugin skill directory then holds exactly `SKILL.md`, `references/LICENSE` and `references/PHASE-BOUNDARIES.md`. Upstream has no `scripts/`.

- **Frontmatter** (plugin source, in this order). The only change is the added `id` key (D11). `name`, `description` and `disable-model-invocation` are byte-identical to upstream L2-L4:
  - The description stays an unquoted plain scalar of 83 characters.
  - D28 keeps it verbatim on purpose, including "A router over the skills in this repo.", even though a consumer's skill root also holds skills from other plugins.
  - It holds no `/name`, so D17 changes nothing in it.
  - `disable-model-invocation: true` must survive the skills-first spec's F6 (D19).
  - No `playbook:` block (D11).

  ```yaml
  ---
  id: ask-matt
  name: ask-matt
  description: Ask which skill or flow fits your situation. A router over the skills in this repo.
  disable-model-invocation: true
  ---
  ```

- **Changes**. SKILL.md first, in line order, then PHASE-BOUNDARIES.md, then the added and dropped files. Router labels keep the slash throughout. The router is human-facing text, so D17 keeps `/name` in every `**`/x`**` and `` `/x` `` label. Only the Claude-only `/clear` and `/compact` lose theirs.

  1. [Frontmatter] `.agents/skills/ask-matt/SKILL.md`, before L2 "name: ask-matt". Insert `id: ask-matt` as the new L2. (D11; the plugin-wide Frontmatter bullet may cover it.)

  2. [Invocation guard] `.agents/skills/ask-matt/SKILL.md`, between L6 (the blank line after the closing `---`) and L7 "# Ask Matt". Insert the guard line and then one blank line, so the guard is the first line of body content, above the H1. This matches A.T03 note 1 for setup-matt-pocock-skills and to-tickets, the other user-invoked skills with an H1. The engine's sentinel goes above it at sync and is never written in the source. Result: L7 blank (upstream L6), L8 guard line, L9 blank, L10 "# Ask Matt" (upstream L7). (D19)

     ```text
     Run this only when the user asked for it by name; otherwise stop.
     ```

  3. [Glossary fallback] SKILL.md L17. Upstream "retaining what it learns in `GLOSSARY.md` and ADRs". Insert `` (or `CONTEXT.md` if the repo already has one)`` right after the `` `GLOSSARY.md` `` code span. The plain-name code span `` `grill-with-docs` `` later on the line stays. Resulting line (D21):

     ```text
     1. **`/grill-with-docs`** sharpens the idea by interview. Start here whenever you are **working in a working directory**: it's stateful, retaining what it learns in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and ADRs. (No working directory? Use `/grill-me` instead, covered under Standalone. Both run the same `/grilling` primitive; `grill-with-docs` is the one that leaves a paper trail, which makes it the better of the two whenever a repo is there to leave it in.)
     ```

  4. [Renamed skill] SKILL.md L20. Upstream "- **`/prototype`** to answer the question with throwaway code,". Replace the label `/prototype` with `/throwaway-prototype`. The plain nouns "a prototype" on L18 stay, since they do not name the skill. Resulting line, with three leading spaces as upstream (D8, D9; D17 keeps the slash):

     ```text
        - **`/throwaway-prototype`** to answer the question with throwaway code,
     ```

  5. [Claude-only built-in] SKILL.md L24. Upstream "**`/clear`ing context between each one**". Replace exactly that bold run with `**starting a fresh context between each one**`. The rest of the line stays verbatim, including the local-tracker sentence with `.scratch/<feature>/issues/` and "on a real tracker". Resulting line, with five leading spaces as upstream (D17):

     ```text
          - **`/implement`** per ticket, **starting a fresh context between each one**. On a local tracker that's one file per ticket under `.scratch/<feature>/issues/`, worked blockers-first by hand; on a real tracker the edges become native blocking links, so any ticket whose blockers are done can be grabbed. Each ticket is self-contained, so the last one's context is disposable.
     ```

  6. [Harness capability] SKILL.md L25. Upstream "runs implementer subagents across the ready **frontier** in parallel, and lands". Insert ` (one ticket at a time where your harness cannot run subagents)` between "in parallel" and the comma. This mirrors the sequential fallback that A.T04.3 change 3 adds to implement-spec. Resulting line, with five leading spaces (D17, D18.5):

     ```text
          - **`/implement-spec`** for the whole spec in one run. It reads the tickets as a **task graph**, runs implementer subagents across the ready **frontier** in parallel (one ticket at a time where your harness cannot run subagents), and lands everything on one **integration branch**. Reach for it when you'd rather orchestrate the build than drive each ticket yourself.
     ```

  7. [Renamed skill] SKILL.md L28. Upstream "closes out with **`/code-review`**, a two-axis review", "it runs one `/code-review` over the integration branch" and "and **`/code-review`** on its own". Replace all three `/code-review` labels with `/two-axis-review`. The `/tdd`, `/implement` and `/implement-spec` labels stay. Resulting line, with three leading spaces (D8, D9; D17 keeps the slash):

     ```text
        Either way, the code gets built by driving **`/tdd`** (one red-green slice at a time) and closes out with **`/two-axis-review`**, a two-axis review (Standards + Spec) of the diff. `/implement` runs both per ticket; `/implement-spec`'s implementers each drive `/tdd`, and it runs one `/two-axis-review` over the integration branch. Reach for **`/tdd`** on its own when you just want to build a concrete behaviour test-first without a full spec, and **`/two-axis-review`** on its own whenever you want to review a branch or PR against a fixed point.
     ```

  8. [Renamed skill] SKILL.md L30. Upstream "When the work goes up as a pull request, **`/pr`** shapes the body". Replace the label `/pr` with `/pr-body`. "It's model-invoked" stays, because pr-body has no `disable-model-invocation` (A.T05.3). Resulting line, with three leading spaces (D8, D9; D17):

     ```text
        When the work goes up as a pull request, **`/pr-body`** shapes the body: the smallest visual that shows the change, before/after evidence that it works, and a one-way or two-way door call. It's model-invoked, so the agent reaches for it whenever it writes a PR.
     ```

  9. [Renamed skill] SKILL.md L32. Upstream "the coding standards `/code-review` enforces". Replace `` `/code-review` `` with `` `/two-axis-review` ``. Nothing else on the line changes; "steering files" stays, since retro's own ticket decides where steering-file proposals go (D26). (D8, D9; D17)

  10. [URL removed] SKILL.md L38. Upstream "The limit on this is the **[smart zone](…)**:". The link target is a URL on the aihero.dev domain. Replace the bold link `**[smart zone](<that URL>)**` with plain bold text `**smart zone**`: the link text stays and the brackets and target go. (D4, D30)

  11. [Claude-only built-in] SKILL.md L38. Upstream "`/compact` at the nearest phase boundary and carry on (see Phase boundaries).". Replace `` `/compact` at the nearest phase boundary`` with `summarise and start a fresh context at the nearest phase boundary`. This is the Compact option of the Phase boundaries section (change 16), worded in D17's terms. Resulting line, after changes 10 and 11 (D17):

      ```text
      The limit on this is the **smart zone**: the window (~150k tokens on state-of-the-art models) within which the model still reasons sharply. If a session approaches it before `/to-tickets`, don't push on degraded; summarise and start a fresh context at the nearest phase boundary and carry on (see Phase boundaries).
      ```

  12. [Dropped skill] SKILL.md L44-L47. Delete four lines:
      - L44, the triage on-ramp bullet "- **Bugs and requests piling up** → **`/triage`**. It moves issues through triage roles and produces agent-ready issues, which **`/implement`** later picks up.";
      - L45, blank;
      - L46, its continuation paragraph "  Triage is only for issues **you didn't create**: … so **don't triage them**.";
      - L47, blank.

      Upstream L43 (the blank after "A starting situation that generates work, then merges onto the main flow.") is then followed directly by L48 "- **Something's broken** → **`/diagnosing-bugs`**.". Do not edit L11, "two **on-ramps** merge onto it": upstream listed three on-ramps, and after the deletion exactly two remain (diagnosing-bugs, wayfinder), so L11 becomes accurate. ATTRIBUTIONS lists triage under Dropped (A.T03 "Dropped: triage"), and this bullet cites it. (D7)

  13. [Glossary fallback] SKILL.md L64. Upstream "to keep `GLOSSARY.md` a clean glossary." Insert `` (or `CONTEXT.md` if the repo already has one)`` right after the `` `GLOSSARY.md` `` code span. Resulting tail of the line: ``It's the active discipline `/grill-with-docs` drives to keep `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) a clean glossary.`` (D21)

  14. [Claude-only built-in] SKILL.md L72. Upstream "- **`/clear`**: empty the window, when nothing here matters to what's next." The option is named as a capability, with D17's phrase as its gloss. Resulting line (D17):

      ```text
      - **Clear** (start a fresh context): empty the window, when nothing here matters to what's next.
      ```

  15. [Harness capability] SKILL.md L74. Upstream "- **Subagent**: send a tightly-scoped task to its own window and get a report back." Insert ` (if your harness can run one)` after the bold label. Without subagents the reader picks among the other four options, and references/PHASE-BOUNDARIES.md question 4 says so explicitly (change 32). Resulting line (D17):

      ```text
      - **Subagent** (if your harness can run one): send a tightly-scoped task to its own window and get a report back.
      ```

  16. [Claude-only built-in] SKILL.md L75. Upstream "- **`/compact`** compresses this context and seeds a fresh session with it." Replace the label `` **`/compact`** `` with `**Compact** (summarise this context, then start a fresh context from the summary)`, the option named as a capability with D17's phrase in its gloss, as change 14 does for Clear. Matt's "compresses this context and seeds a fresh session with it." and "The **default**, at the bottom of the tree rather than the first reach." stay. A harness with built-in compaction does both steps at once; elsewhere the agent writes the summary and the user starts the fresh context. Do not fall back to `/handoff`: its clause is "the whole clause" (references/PHASE-BOUNDARIES.md L34). Resulting line (D17):

      ```text
      - **Compact** (summarise this context, then start a fresh context from the summary) compresses this context and seeds a fresh session with it. The **default**, at the bottom of the tree rather than the first reach.
      ```

  17. [Moved file link] SKILL.md L77. Upstream "Read [PHASE-BOUNDARIES.md](PHASE-BOUNDARIES.md) for the ordered tree". The link target becomes `references/PHASE-BOUNDARIES.md`. The link text is a plain name, not a code-formatted path, so it stays, as in A.T05.1 change 4. (D10)

  18. [Harness capability] SKILL.md L77, second sentence. Upstream "mid-phase, continue or split the rest into subagents." Insert `, if your harness can run subagents,` after "continue or". "continue" is already the inline fallback. Resulting line, after changes 17 and 18 (D17):

      ```text
      Read [PHASE-BOUNDARIES.md](references/PHASE-BOUNDARIES.md) for the ordered tree: the five questions, the reasoning behind each branch, and why the primary-source cost makes **Continue** the one to rule out first. Make the decision **at** a boundary; mid-phase, continue or, if your harness can run subagents, split the rest into subagents.
      ```

  19. [Glossary fallback] SKILL.md L83. Upstream "it saves nothing locally and builds no `GLOSSARY.md`." Insert `` (or `CONTEXT.md` if the repo already has one)`` between the code span and the period. Resulting fragment: ``it saves nothing locally and builds no `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one).`` The rest of the line is verbatim. (D21)

  20. [Dropped skill] SKILL.md L84. Upstream "and `/triage`, `/wayfinder` and `/improve-codebase-architecture` all run it internally." Replace that clause with "and `/wayfinder` and `/improve-codebase-architecture` both run it internally." Both still load grilling: wayfinder per A.T04.1, and improve-codebase-architecture at its upstream L64 in its own ticket. Resulting line (D7):

      ```text
      - **`/grilling`** is the interview primitive itself: rounds, the frontier, facts are the agent's job and decisions are yours. `/grill-me` and `/grill-with-docs` are the two named ways in, and `/wayfinder` and `/improve-codebase-architecture` both run it internally. Reach for it directly only when you want the interview with no wrapper around it.
      ```

  21. [Renamed skill] SKILL.md L85. Upstream "- **`/prototype`** is a small, throwaway program". Replace only the label `/prototype` with `/throwaway-prototype`. Keep the plain noun "the prototype itself" and the git branch code span `` `prototype/<name>` ``. That branch name is not a skill id, just as D8 keeps wayfinder's `prototype` ticket type and UI.md's `/prototype/<name>` route. (D8, D9; D17)

  22. [Harness capability] SKILL.md L86. Upstream "delegate reading legwork to a **background agent**: … Keep working while it reads." Insert one new sentence directly after "Keep working while it reads.": ` If your harness cannot run a background agent, the agent hands the reading to a subagent, or does it itself in this session.` Matt's sentences stay byte-identical. The new sentence scopes "Keep working while it reads" to the background path, as D18.2 does for grilling. It matches research's own no-background-agent path (A.T08.1 change 2: a subagent if the harness can run one, else inline). research's D18.3 nesting guard concerns an agent that is already a subagent and does not apply to a user starting `/research`. Resulting line (D17, D18.3):

      ```text
      - **`/research`**: delegate reading legwork to a **background agent**: it investigates a question against **primary sources**, then leaves a cited Markdown file in the repo. Keep working while it reads. If your harness cannot run a background agent, the agent hands the reading to a subagent, or does it itself in this session. The file it produces is something to take *into* the main flow at `/grill-with-docs`, since research feeds the thinking rather than replacing it.
      ```

  23. [Script rewrite and imposed tool] SKILL.md L88. Upstream "It generates an interactive bash script that opens each URL, captures each value, and writes it into `.env` and GitHub secrets, so". The router must match the shipped wizard:
      - the wizard is `scripts/wizard_template.py`, so "bash" becomes "Python";
      - `open_url` still opens each URL, through the stdlib `webbrowser` module, so "opens each URL" stays;
      - `set_secret`/`set_var` no longer write through `gh`; they become guided manual steps at capture time.

      Replace exactly that substring with "It generates an interactive Python script that opens each URL, captures each value, writes it into `.env`, and guides you through setting each GitHub secret or variable by hand, so". "GitHub" is a product name, not the gh CLI. Keep "Model-invoked, so the agent reaches for it…": wizard has no `disable-model-invocation`. Resulting line (D22, D2):

      ```text
      - **`/wizard`** is for the steps only a **human** can take: provisioning infrastructure, setting up credentials or CI secrets, clicking through an unfamiliar third-party dashboard, running a one-off migration or cutover. It generates an interactive Python script that opens each URL, captures each value, writes it into `.env`, and guides you through setting each GitHub secret or variable by hand, so the procedure stops being something you re-explain to an agent every time. Model-invoked, so the agent reaches for it the moment it hits a wall only you can pass. If the agent could just do it itself, it should; this is for where a human is genuinely in the loop.
      ```

  24. [Glossary fallback] SKILL.md L89. Upstream "in plain English, using the `GLOSSARY.md` vocabulary." Insert `` (or `CONTEXT.md` if the repo already has one)`` right after the code span. Resulting fragment: ``using the `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) vocabulary.`` (D21)

  25. [Restructure] `skills/engineering/ask-matt/PHASE-BOUNDARIES.md` moves to `.agents/skills/ask-matt/references/PHASE-BOUNDARIES.md`. It is edited only by changes 26-35, and its only inbound link is SKILL.md L77 (change 17). (D10)

  26. [Harness capability] references/PHASE-BOUNDARIES.md L5. Upstream "Mid-phase there is no decision to make: continue, or split the work that's left into subagents." Insert `, if your harness can run subagents,` after "continue, or". "Compacting mid-phase makes the agent lose the thread." stays: it is a plain verb, not the command. Resulting sentence (D17):

      ```text
      Mid-phase there is no decision to make: continue, or, if your harness can run subagents, split the work that's left into subagents.
      ```

  27. [Claude-only built-in] references/PHASE-BOUNDARIES.md L12, a table row. Upstream "| **`/clear`** | Empty the context window and start from nothing.". Replace only the label cell. The description cell, with its trailing padding, stays byte-identical. Exact resulting row (D17):

      ```text
      | **Clear** (start a fresh context) | Empty the context window and start from nothing.                  |
      ```

  28. [Harness capability] references/PHASE-BOUNDARIES.md L14, a table row. Upstream "| **Subagent** | Send the task to its own context window and get a report back.". The label cell gains the capability qualifier, and the description cell stays byte-identical. Exact resulting row (D17):

      ```text
      | **Subagent** (if your harness can run one) | Send the task to its own context window and get a report back.     |
      ```

  29. [Claude-only built-in] references/PHASE-BOUNDARIES.md L15, a table row. Upstream "| **`/compact`** | Compress this context and seed a fresh session with the summary.". Replace the label cell with `**Compact** (summarise, then start a fresh context from the summary)`, a shorter form of change 16's D17 gloss. The description cell, with its trailing padding, stays byte-identical. Exact resulting row (D17):

      ```text
      | **Compact** (summarise, then start a fresh context from the summary) | Compress this context and seed a fresh session with the summary.  |
      ```

      The `/handoff` row (L13) and the Continue row (L11) stay. Do not realign the table: upstream's L13 and L15 rows were already wider than the separator row, and D32 keeps ruff off this markdown.

  30. [URL removed] references/PHASE-BOUNDARIES.md L21. Upstream "or you have enough [smart zone](…) left (~150k tokens)". The target is the same aihero.dev URL as in SKILL.md L38. Replace the whole link with the plain text `smart zone`. Resulting fragment: "or you have enough smart zone left (~150k tokens) for the next phase to fit." "Grilling → implementation" keeps its U+2192. (D4, D30)

  31. [Claude-only built-in] references/PHASE-BOUNDARIES.md L23. Upstream "If so, **`/clear`**." and "`/clear` also isn't terminal: the old session stays resumable." Make two edits:
      - `If so, **`/clear`**.` becomes `If so, **clear** (start a fresh context).`;
      - `` `/clear` also isn't terminal`` becomes `Clearing also isn't terminal`.

      Resulting line (D17):

      ```text
      **2. Is the context irrelevant to what comes next?** Is everything in this session (the exploration, the decisions, the dead ends) disposable? If so, **clear** (start a fresh context). It is the cheapest move on the board: it takes no time and hands back the whole window. Clearing also isn't terminal: the old session stays resumable.
      ```

  32. [Harness capability] references/PHASE-BOUNDARIES.md L36. Upstream "Then send it to a **subagent** and leave this session untouched." Replace that sentence with "Then, if your harness can run subagents, send it to a **subagent** and leave this session untouched; if it can't, go on to question 5." The fallback keeps the tree coherent: "the first yes wins", so a yes that cannot be acted on falls through to question 5. Resulting line (D17):

      ```text
      **4. Can the task be done AFK?** Is it scoped tightly enough to run with you away from the keyboard, no steering? Then, if your harness can run subagents, send it to a **subagent** and leave this session untouched; if it can't, go on to question 5. Automated review is the standard case: the agent reads the diff and reports, and you aren't needed while it does.
      ```

  33. [Claude-only built-in] references/PHASE-BOUNDARIES.md L38. Upstream "**5. Otherwise, `/compact`.**" and "Pass it an instruction (`/compact we're going to QA this area`)". Make two edits:
      - the bold heading becomes `**5. Otherwise, compact (summarise, then start a fresh context from the summary).**`;
      - the Claude Code argument syntax goes, leaving the instruction as its own code span: `` (`we're going to QA this area`) ``.

      The rest of the line stays verbatim. Resulting line (D17):

      ```text
      **5. Otherwise, compact (summarise, then start a fresh context from the summary).** Relevant context, same harness, same directory, and you need to stay in the loop: this is where the tree lands, and it lands here often. Pass it an instruction (`we're going to QA this area`) so the summary keeps what the next phase needs.
      ```

  34. [Claude-only built-in] references/PHASE-BOUNDARIES.md L40. Upstream "`/compact` is the **default, not the first reach**." Replace `` `/compact` is`` with `Starting a fresh context from a summary is`. The rest of the line is verbatim. (D17)

  35. [Claude-only built-in] references/PHASE-BOUNDARIES.md L49, a table row. Upstream "| Secondary (`/compact`, `/handoff`) |". Replace `` `/compact` `` with `fresh context from a summary`, and keep the `/handoff` label. Exact resulting row, without realigning (D17):

      ```text
      | Secondary (fresh context from a summary, `/handoff`) | Lossy       | Less  | Lots         |
      ```

  36. [License copy] `.agents/skills/ask-matt/references/LICENSE` is added. It is a byte-identical copy of the plugin-root LICENSE, the upstream MIT notice "Copyright (c) 2026 Matt Pocock". (D4; the plugin-wide "License copies added" bullet may cover it.)

  37. [Dropped] `skills/engineering/ask-matt/agents/openai.yaml` is not shipped (`display_name: "Ask Matt"`, `short_description: "Find the right skill or workflow"`, `policy: allow_implicit_invocation: false`). Codex reads the shared skill root and so loses its user-only invocation policy for this skill. What remains is `disable-model-invocation`, which only Claude Code honours, and the change 2 guard line. (D10, D19)

- **Project-toolchain allowlist**: none. After the changes, no fenced block or shell-prompt line appears in either file. Every inline code span starts with a word that is not on the D30 denylist:
  - a `/<id>` label;
  - `.env`, `.scratch/<feature>/issues/`, `GLOSSARY.md`, `CONTEXT.md`, `grill-with-docs` or `prototype/<name>`;
  - `we're` (PHASE-BOUNDARIES L38).

  The ambiguous words occur only in prose, never in command position: SKILL.md L17 "Start here", L19 "open a fresh session", L32 and L36 "starts", the new "start a fresh context" text and L88 "opens each URL"; PHASE-BOUNDARIES L12 "start from nothing" and L40 "people start here". The only denylisted word, "bash" at L88, leaves with change 23. An entry would fail D30's two-way check as stale.

- **Skill-specific tests**: put these in `tests/plugins/mattpocock_skills/test_router.py`.
  1. `test_router_labels_match_inventory`: collect every match of ``` `/([a-z0-9]+(?:-[a-z0-9]+)*)` ``` (a code span holding exactly one slash label) in ask-matt's SKILL.md after the frontmatter. The set must equal `FINAL_IDS - {"ask-matt"}`, which is 25 ids; whether each names an existing `skills/<id>/SKILL.md` is T10's check (section 7.8), so this test passes before the other lanes merge. The same regex over `references/PHASE-BOUNDARIES.md` must yield exactly `{"handoff"}`. Reuse the D9 id constant of the D30 inventory pin, if it exists, rather than a second copy. Spans such as `` `/implement-spec`'s ``, `` `.scratch/<feature>/issues/` `` and `` `prototype/<name>` `` must not break the match, and the regex shape handles them. This is the "router that lies" check: it fails on any dropped, renamed or missing route, and T10 adds the presence half.
  2. `test_router_no_stale_routes`: neither file contains `` `/triage` ``, `` `/code-review` ``, `` `/pr` `` or `` `/prototype` ``, with the closing backtick included in each pattern, so `` `/pr-body` `` and `` `/throwaway-prototype` `` do not match. The `## On-ramps` section of SKILL.md has exactly two top-level `- **` bullets, as L11's "two **on-ramps**" says. "triage labels" (upstream L95) stays and must not be flagged.
  3. `test_router_invocation_claims`: the router calls pr-body (L30), wizard (L88), domain-modeling and codebase-design (L62) model-invoked. None of the four may be in `USER_INVOKED_IDS`; G15 ties each present skill's `disable-model-invocation` to that set, so the test needs none of them present.
  4. `test_router_replay_guard` guards against a future tag upgrade bringing the removed text back.
     - SKILL.md contains:
       - `**starting a fresh context between each one**`
       - `- **Clear** (start a fresh context):`
       - `**Compact** (summarise this context, then start a fresh context from the summary)`
       - `[PHASE-BOUNDARIES.md](references/PHASE-BOUNDARIES.md)`
       - `**smart zone**`
       - `interactive Python script`
     - references/PHASE-BOUNDARIES.md contains:
       - `if it can't, go on to question 5`
       - `**5. Otherwise, compact (summarise, then start a fresh context from the summary).**`
       - `enough smart zone left`
     - Neither file contains `aihero` or `bash`.

     The D30 URL and Claude-only-name scans already cover the URLs, `/clear` and `/compact`.
  5. `test_router_references_inventory`: `skills/ask-matt/references/` holds exactly `{LICENSE, PHASE-BOUNDARIES.md}`, and no `PHASE-BOUNDARIES.md` remains at the skill root. The shared D30 layout check covers the root, so assert only the inventory if it is already pinned there.
  6. Extend A.T02's `tests/plugins/mattpocock_skills/test_glossary_fallback.py::test_glossary_mentions_carry_context_fallback` parametrization with `("ask-matt", "SKILL.md")`. No exemption is needed: upstream L17, L64, L83 and L89 all carry the fallback, and the file has no fenced blocks. `references/PHASE-BOUNDARIES.md` names neither GLOSSARY file and is not parametrized.

- **Continue degradation**: With the `continue` adapter listed, the skill becomes the user-run `.continue/prompts/ask-matt.md`. It carries only the SKILL.md body, with the guard line, which a user-started prompt satisfies. `references/` does not travel, so the L77 link dangles and the ordered five-question tree and the primary/secondary trade-off table of PHASE-BOUNDARIES.md are lost, leaving only the five-option summary. The "model-invoked, so the agent reaches for it" claims at L30, L62 and L88 do not hold there, and no LICENSE copy travels. (D29)

**Ticket T09 notes.**

- **Order.** T09 merges in any order after T01, like every other lane (section 8.3). The router names all 25 other D9 ids, but test 1 checks the labels against `FINAL_IDS` and test 3 against `USER_INVOKED_IDS`; T10's inventory pin checks that every label names a present skill. T01 must already have created the plugin-root LICENSE and the D32 ruff extend-exclude. Test 6's glossary check goes in `test_router.py` (section 7.1), so it does not wait for A.T02's test file.
- **Line shifts.**
  - Upstream L2-L6 move down by 1.
  - Upstream L7-L43 move down by 3 (id line, guard line and its blank line).
  - Upstream L44-L47 are deleted.
  - Upstream L48-L95 sit 1 line higher (+3 - 4): L48 becomes L47 and L95 becomes L94.
  - PHASE-BOUNDARIES.md keeps its numbering.

  ATTRIBUTIONS cites upstream numbers.
- **Cross-ticket wording this ticket mirrors.** Each owning ticket must keep these consistent, or this appendix changes with it:
  - L25 follows A.T04.3 change 3: implement-spec's sequential stop-and-resume fallback (D18.5).
  - L28 and L32 follow A.T05.2 (code-review renamed to two-axis-review).
  - L30 follows A.T05.3 (pr renamed to pr-body, still model-invoked).
  - L20 and L85 follow the throwaway-prototype ticket. Its directory, id and `name` change there, and its `prototype/<name>` branch text stays.
  - L86 follows the research ticket: without a background agent, a subagent if the harness can run one, else the research inline, plus the D18.3 nesting guard.
  - L88 follows the wizard ticket (D22): `scripts/wizard_template.py`, `webbrowser`, and `set_secret`/`set_var` as guided manual steps. If that ticket words the manual CI step differently, keep this line's meaning (`.env` written, GitHub secrets and variables set by hand) and match its nouns.
  - L95 follows A.T03: setup is kept (D14), and `docs/agents/triage-labels.md` is always written, so "configure the issue tracker, triage labels, and doc layout" and "Custom issue trackers also work." stay verbatim.
  - L84's claim that wayfinder and improve-codebase-architecture run grilling depends on their tickets keeping those loads (A.T04.1; improve-codebase-architecture L64).
  - No other skill links to ask-matt or loads it, so T09 makes no inbound edit elsewhere.
- **Audit and verify proposals dropped or changed by decisions.**
  - (a) The audit's Precondition rewrite toward a sync-delivered rule, and its dropping of "triage labels": D14 keeps setup and always writes the labels file, and D15's plugin always rule only points at setup, so L95 is verbatim.
  - (b) The audit's "shows each URL" and the dropping of "GitHub": D22's stdlib `webbrowser` still opens URLs, and GitHub is a product name. Only "bash" and the automatic secret writes are forced, as the verifier said.
  - (c) The audit's qualifiers on session logs (L36, "where your harness keeps session logs") and resumability (PHASE-BOUNDARIES L23): no decision names them. They are not among D2's harness built-ins, and retro's L13 "session logs on this machine" stays upstream text. Only the `/clear` token on L23 changes.
  - (d) The verifier's open question on the description: settled by D28 (verbatim).
  - (e) The verifier's open question on bare "open"/"start": settled by D30 (command position only).
  - (f) The verifier's premise that triage might be kept: D7 drops it.
  - (g) The audit's "no change" for the four GLOSSARY.md mentions: D21 applies.
  - (h) The audit's PHASE-BOUNDARIES L49 realignment: not done (see change 29).
  - (i) The audit's "Finalize last" and its rename placeholders: now concrete through D8 and D9.
- **Ambiguities resolved.**
  1. *Guard position with an H1.* The guard goes above "# Ask Matt", as the first line of body content, the same as A.T03 for setup and to-tickets. The engine's sentinel takes the first body line in synced output, ahead of it.
  2. *What `/compact` becomes.* D17 names "start a fresh context" for both commands, and every former `/compact` site is worded in those terms. Clear is a fresh context from nothing, and Compact a fresh context from a summary, so the five options stay distinct: "summarise and start a fresh context" (SKILL L38), "**Compact** (summarise this context, then start a fresh context from the summary)" (SKILL L75), a shorter form of that gloss in PHASE-BOUNDARIES L15 and L38, "Starting a fresh context from a summary" (L40) and "fresh context from a summary" (L49). A harness with built-in compaction does both steps at once; elsewhere the agent writes the summary and the user starts the fresh context, so no separate "if your harness cannot compact" fallback is needed. "Clear" carries the phrase as its gloss.
  3. *Plain verbs kept.* SKILL.md L36's "don't compact or clear", "before you clear; after clearing" and "Each `/implement` then starts fresh", L19's "open a fresh session", and PHASE-BOUNDARIES L5's "Compacting mid-phase" are ordinary verbs, not the Claude-only commands. D30 does not flag them, and they stay verbatim.
  4. *Descriptive subagent mentions.* L25 and L86 get a fallback even though they describe other skills, because the router's job is to say accurately what each skill does on the reader's harness. Both are pure insertions, so Matt's sentences stay byte-identical.
  5. *Persona.* The H1 "# Ask Matt" and the label `/setup-matt-pocock-skills` stay: D8 renames only for collisions, and `setup-matt-pocock-skills` does not contain the coupling marker `mattpocock-skills:`.
  6. *"(Claude → Codex)"* (PHASE-BOUNDARIES L29) is an illustrative harness pair, not a tool instruction, and stays.
- **Gate facts.**
  - Before the changes, the D30 Claude-only-name scan has 12 hits:
    - 4 in SKILL.md: L24, L38, L72, L75;
    - 8 in PHASE-BOUNDARIES.md: L12, L15, L23 twice, L38 twice, L40, L49.

    After the changes there are none.
  - URLs: two before (SKILL.md L38, PHASE-BOUNDARIES L21), none after.
  - No "Skill tool", "Task tool", "AskUserQuestion", "TodoWrite" or coupling marker appears at any point.
  - The only `references/` path mentioned is `references/PHASE-BOUNDARIES.md`, which resolves.
  - The URL gate's bare-domain-plus-path rule must not fire on `references/PHASE-BOUNDARIES.md`, `` `.scratch/<feature>/issues/` ``, `` `prototype/<name>` `` or `GLOSSARY.md`.
  - The D19 gate finds the guard at plugin source L8.
  - The listing-budget test counts the unchanged 83-character description.
  - The added prose has no em-dashes (upstream's house rule).
- **README (D33).** The plugin README lists ask-matt among the user-invoked-only skills that only Claude Code enforces through `disable-model-invocation`. Its `/name` labels are human-facing (D17). On a harness that does not expose skills as slash commands they read as skill names.

