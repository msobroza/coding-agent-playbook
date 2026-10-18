# PR S - Skills-first context: rules delivered as skill references, and the python-best-practices import

Status: Accepted design, 2026-10-18. Every decision in section 2 was approved by the user on
2026-10-17/18 or taken by the orchestrator under the user's autonomous mandate; this document
does not reopen them.

- Decision record: `docs/adr/0001-scoped-rules-are-delivered-as-skill-references.md`
  (committed by PR 2).
- This spec: `specs/prS-skills-context.md` is untracked today and is committed by PR 2, together
  with `CONTEXT.md` and the ADR (C12), so the two parallel PRs never add the same file. PR 1
  cites it only in its PR description; PRs 3-8 branch after PR 2 and cite it from `main`.
- Vocabulary: `CONTEXT.md` at the repository root is the only glossary (D12). Every term below
  (rule, always rule, scoped rule, member rule, skill, reference, prompt, hook, guardrail, skill
  nudge, always-loaded context, skill listing, context budget, skill root, layer, core, bundled
  plugin, overlay, detector fact, adapter, harness, consumer repo, distilled content, vendored
  content) means what `CONTEXT.md` says.
- Anchors: every `file:line` was read at `38a9330` on 2026-10-17/18 unless noted; re-verify an
  anchor before editing, lines drift between PRs.
- Cross-references: `§x` always names a section of `SPEC.md`; "section x" names a section of this
  spec. MIGRATION sections are named by their title.

This spec covers eight PRs. Sections 5 to 12 hold one PR each; sections 13 to 16 are shared.

## 1. Summary and goal

Today the engine writes every rule that survives `applies_if` in full into always-loaded context.
On the reference probe of D5 (a scratch repo with fastapi, httpx, pydantic, torch, numpy, pandas
and scikit-learn as dependencies; pytest, pytest-asyncio, ruff and mypy as dev dependencies; one
notebook; default adapters; hooks on), measured on 2026-10-17/18:

| Output | Measured size |
| --- | --- |
| `AGENTS.md` (OpenCode, Codex, Continue IDE) | 6,830 words (rules 5,309 + guardrails 1,521), about 11.5k tokens (6,832 when re-measured by the PR 2 designer) |
| `.claude/rules/coding-agent-playbook.md` (Claude Code) | 5,330 words |
| Continue `.continue/rules/` | 20 `alwaysApply` files with 2,720 words, plus 16 glob files with 5,469 words |
| Rendered prompts | 343 to 2,965 words (`/refactor` 2,965; `/review` 1,963) |
| Skill listing of the 17 bundled plugin skills | 534 words, 3,398 characters (superpowers 2,285 across 15 skills, python_design 1,113 across 2) |

The goal is a skills-first layout. Always rules stay in always-loaded context. Each scoped rule
names the one skill that owns its topic and is delivered as a reference inside that skill, loaded
on demand. Prompts, lint feedback and a new skill nudge point the agent at the skill it needs. Core
then fills those skills with distilled python-best-practices content.

Targets (D5), enforced by CI tests on the reference probe from PR 2 on:

| Budget | Limit | Expected after PR 4 | Expected after PR 8 |
| --- | --- | --- | --- |
| Rendered always rules | at most 800 words | about 234 words, about 310 with the generated "Where guidance lives" section | unchanged |
| Whole `AGENTS.md` | at most 1,500 words | about 750 words | about 750 words |
| Each core skill description | at most 300 characters | 145 to 281 | 183 to 281 |
| Core skill descriptions in total | at most 2,000 characters | 1,043 (762 + 281 for `playbook-guardrails`) | 1,238 |
| Core plus every bundled plugin | at most 6,000 characters | 4,441 | 4,636 |

## 2. Decisions

| # | Decision (short) | Answered |
| --- | --- | --- |
| D1 | Rules stay the unit of guidance. Always rules stay in always-loaded context; scoped rules are delivered as references inside skills on skill-capable harnesses; Continue, when enabled, keeps one rule file per rule. | Q1 / ADR 0001 |
| D2 | Membership is declared on the rule: `skill: <skill-id>`, required when `scope: scoped`, forbidden when `scope: always`, must name a skill that exists after the layer merge; one owner per rule; overlays and repo-local layers join a core skill by naming it. | Q12 |
| D3 | No new content kind: a skill's references may be hand-written, rendered member rules, or both. Plugin skills are skills with no member rules. The term "topic skill" is dropped. | Q13 |
| D4 | Core ships skills: `python-coding`, `python-testing`, `python-tooling`, `ml-data` (PR 2) and `playbook-guardrails` (PR 4). A skill with member rules is written only when one member passes its gate; its description is the authored capability sentence + an engine-generated "Covers ..." clause naming the active members + "Use when ...", at most 300 characters, validated at sync. | Q14 / Q14' |
| D5 | Context budget on the reference probe: always rules at most 800 words; whole `AGENTS.md` at most 1,500 words; core descriptions at most 2,000 characters in total and 300 each; core plus every bundled plugin at most 6,000 characters (shorten plugin descriptions if needed, listing vendored changes in ATTRIBUTIONS). | Q2 |
| D6 | `AGENTS.md` Guardrails = one line per enabled hook; the full text moves to the `playbook-guardrails` skill. Continue's `30-guardrail-<id>.md` files are unchanged; Claude Code keeps getting no guardrails. | Q3 |
| D7 | Upstream python-best-practices (MIT, Ludo Technologies LLC, commit `bf64c51d2f4c8255f126c98359bdbcd5e2587b92` of 2026-08-31) is distilled into core, credited in plain text in `catalog/core/ATTRIBUTIONS.md`, its name added to the self-contained marker regex; upstream impact maps onto `priority`. | Q4 |
| D8 | Overlap policy: fold overlapping ideas into the existing rule in our wording; conflicts resolved for our rules (docstrings, named fakes, uv gated on a new `package_manager` key, hatchling and pyscn dropped, pydantic in python-tooling, pandera optional, tool config values are examples only). | Q5 |
| D9 | Data-science rules live under `catalog/core/rules/ml/`, gated `any_ml_stack: [numpy, pandas, polars]`. No `any_of` combinator. | Q6 |
| D10 | Skill roots: `claude_code` writes `.claude/skills`, `opencode` keeps `.opencode/skills`, `shared_skills` moves from `shared_skills/` to `.agents/skills`; all copies byte-identical through one `SkillWriter`; emitted frontmatter stays at standard keys plus already-allowed pass-through keys. | Q7' |
| D11 | Continue leaves the default `playbook init` adapter set; when enabled, its output is exactly today's. | Q8 |
| D12 | `CONTEXT.md` is the only glossary; SPEC section 3 becomes a one-line pointer; the two docs tests that pin section 3 text are repointed to sections 6/10. | Q9 |
| D13 | No new eval features. Static CI checks only: listing budget, description lint (third person, a "Use when" clause, at most 300 characters), `SKILL.md` at most 500 lines, references one level deep, every `skill:` names an existing skill. | Q10 |
| D14 | PRs 1-4 land before the v0.1.0 tag; content PRs 5-8 may follow. | Q11 |
| D15 | `includes_rules` keeps rule ids, now meaning "the references this task needs"; the three `{{ rule() }}` callers drop the calls; Claude Code and OpenCode commands open with a generated `## Before you start` block; Continue and the eval runner keep the inline rule appendix. | Q15 |
| D16 | `linked_rule` stays; lint feedback prefix `rule <rule-id> (skill <skill-id>): <message>`; new `skill-nudge` hook (feedback category, on by default with hooks) names the skill the first time a session edits a matching file (at most 200 characters, once per skill per session) on Claude Code and OpenCode. | Q16 |
| D17 | Always-loaded text = project-context (name, kind, description, two reminders) + Python house style (8 bullets) + a generated "Where guidance lives" section + in `AGENTS.md` only, one line per guardrail. Other house-style content moves into `python-coding`. `CLAUDE.md` stays the 4-line stub. | Q17 |
| D18 | Only ADR 0001; no ADR for skill roots or Continue. | Q18 |
| D19 | PR plan: PR 1 roots + Continue opt-in; PR 2 rules as skill references; PR 3 prompts; PR 4 hooks; PR 5-8 distilled content, one per skill. PR 1 parallel with PR 2; after PR 2, PR 3, PR 4 and PR 5-8 in parallel lanes. Every PR branches from `main`; no stacked PRs; Conventional Commits titles. | Q19 |
| D20 | `project-context` keeps today's behaviour (the detector's `project_kind`); preferring the config's `[project] kind` is a follow-up. | orchestrator, on the PR 2 content designer's open question |
| D21 | Content PRs may shorten member rules' `name` to short topic labels (cosmetic for Continue). The engine keeps every composed description within 300 characters deterministically: when the "Covers ..." list would overflow it lists the highest-priority active members and ends with "and N more". PR 2 implements that truncation and its test. | orchestrator, on the PR 2 engine designer's open question |
| D22 | Eval runner = option A: `evals/prompting.py` appends the inline `## Reference rules` appendix for every prompt with `includes_rules`. | orchestrator, on the PR 3 designer's open question |
| D23 | No lint-feedback hooks for the distilled rules' candidate ruff codes in PRs 5-8; codes stay out of rule frontmatter; a post-pilot follow-up may add them. | orchestrator, on the PR 5-8 designer's open question |

## 3. Harness facts relied on

Verified against source and docs on 2026-10-17. Designs below rely on these and nothing else about
the harnesses.

- **Claude Code 2.1.29x-2.1.302.** `CLAUDE.md` files and `.claude/rules/*.md` without `paths:`
  load at launch; rules with `paths:` load when a matching file is read or edited and are
  summarized away by `/compact`. Skills live in `.claude/skills/<name>/SKILL.md`. The listing
  (name, description and `when_to_use`, capped at 1,536 characters per skill) is sent every turn
  within about 1% of the context window (about 6,000 characters at 200k on current models);
  overflow drops descriptions of least-used skills, and the listing is not re-sent after
  `/compact`. Hook `additionalContext` is capped at 10,000 characters per field; PostToolUse,
  UserPromptSubmit and SessionStart can inject context. Default mode reads `AGENTS.md` natively
  unless a `CLAUDE.md` or `.claude/CLAUDE.md` exists, hence the stub.
- **OpenCode v1.19.3 and v2.0.32** (Homebrew installs v2). `AGENTS.md` (root and ancestors) is
  loaded in full every step; there are no glob- or path-scoped rules; the skill listing is in the
  system prompt (about 60-90 tokens per skill) and bodies load lazily through the skill tool. Skill
  roots: `.opencode/skills` (native), `.agents/skills` and `.claude/skills` (compatibility; v1
  `OPENCODE_DISABLE_EXTERNAL_SKILLS` drops both, `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` drops
  `.claude`). One id in several roots is registered once (v2 precedence `.opencode > .agents >
  .claude`; v1 logs a duplicate warning). v2 treats any root-level `*.md` in a skill root as a
  skill. `opencode.json` `instructions` load eagerly.
- **Codex CLI rust-v0.163.0.** Project `AGENTS.md` chain from root to cwd, `project_doc_max_bytes`
  32 KiB (the crossing file is truncated); skills from `<dir>/.agents/skills` for every directory
  from root to cwd and `~/.agents/skills`; catalog budget 2% of the window or 8,000 characters; no
  path scoping. Codex hooks exist, but the engine's hook adapters support Claude Code and OpenCode
  only.
- **Continue (maintenance freeze; final VS Code 2.0.0, CLI 1.5.47, JetBrains 1.0.67).** The IDE
  reads `.continue/rules` (`alwaysApply`, globs, agent-requested through a `request_rule` tool that
  is off by default), loads the workspace-root `AGENTS.md` as an `alwaysApply` rule, and reads
  skills from `.continue/skills` and `.claude/skills` (not `.agents/skills`, not symlinked
  directories) through `read_skill` in Agent and Plan modes only. The CLI drops glob and regex
  rules silently and reads the first of `AGENTS.md`, `AGENT.md`, `CLAUDE.md`, `CODEX.md` in cwd.
  No wired hooks.
- **Agent Skills spec.** `name` 1-64 characters of `[a-z0-9-]`, equal to the directory name;
  `description` 1-1,024 characters; standard frontmatter keys `name`, `description`, `license`,
  `compatibility`, `metadata`, `allowed-tools`; `SKILL.md` under 500 lines (about 5k tokens);
  references one level deep and linked from `SKILL.md`; a reference over 100 lines gets a table of
  contents.
- **Anthropic context-engineering guidance (digested).** The always tier is the smallest
  high-signal set (commands, hard constraints with a one-line why, conventions that differ from
  defaults, where guidance lives); conditional logic belongs in sync-time gating, not prose; one
  owner per topic; prompts and hook messages carry identifiers, not bodies; hook feedback is short
  and actionable; critical guidance comes first in a skill body (only the first 5,000 tokens of a
  re-attached skill survive compaction).

## 4. Before and after

What each harness loads in the reference probe. "Always" means always-loaded context; everything
else is on demand.

Before (today: default adapters `continue`, `claude_code`, `opencode`, `shared_skills`; hooks on):

```text
probe/
├── AGENTS.md ............................ always: OpenCode, Codex, Continue IDE
│                                           6,830 words = 13 rule sections + 23 guardrail sections
│                                           (29 hooks enabled, 23 with an advisory)
├── .claude/
│   ├── CLAUDE.md ........................ 4-line stub
│   ├── rules/coding-agent-playbook.md ... always: Claude Code, 5,330 words = every rule
│   ├── commands/<slash>.md .............. rule bodies inline (343-2,965 words)
│   └── skills/<plugin-skill>/ ........... bundled plugin skills only (core ships none)
├── .opencode/
│   ├── command/<slash>.md ............... rule bodies inline
│   ├── skills/<plugin-skill>/
│   └── plugins/playbook-hooks.js
├── .continue/
│   ├── rules/ ........................... 20 alwaysApply files (2,720 words) + 16 glob files
│   └── prompts/<slash>.md, one degraded prompt per plugin skill
└── shared_skills/<plugin-skill>/ ........ read natively by no harness
```

After PR 1-4 (default adapters `claude_code`, `opencode`, `shared_skills`; `continue` opt-in;
hooks on):

```text
probe/
├── AGENTS.md ............................ always: OpenCode, Codex (and Continue IDE when enabled)
│                                           about 750 words = 2 always rules + Where guidance lives
│                                           + one line per guardrail
├── .claude/
│   ├── CLAUDE.md ........................ 4-line stub (unchanged)
│   ├── rules/coding-agent-playbook.md ... always: Claude Code, about 330 words =
│   │                                       2 always rules + Where guidance lives + heartbeat
│   ├── commands/<slash>.md .............. "## Before you start" block, no rule bodies
│   └── skills/
│       ├── python-coding/ ............... SKILL.md (index) + references/<9 member ids>.md
│       ├── python-testing/ .............. SKILL.md + references/pytest.md
│       ├── python-tooling/ .............. SKILL.md + references/fastapi-*.md
│       ├── ml-data/ ..................... SKILL.md + references/ml-serialization-security.md
│       └── <plugin-skill>/
├── .opencode/
│   ├── command/<slash>.md ............... "## Before you start" block
│   ├── skills/ .......................... the same core skills + playbook-guardrails + plugins
│   └── plugins/playbook-hooks.js ........ also runs skill-nudge
├── .agents/skills/ ...................... byte-identical to .opencode/skills (Codex, OpenCode)
└── .continue/ ........................... only when continue is listed: one file per rule, as today
```

Always-loaded sizes, before and after (reference probe; tokens at the measured 1.68 tokens per
word; listing characters are description lengths):

| Harness | Always-loaded content | Before | After PR 2 | After PR 4 |
| --- | --- | --- | --- | --- |
| Claude Code | rules file | 5,330 words | about 330 words | about 330 words (no guardrail lines: every core hook runs natively) |
| Claude Code | skill listing | 3,398 chars (plugins) | 4,160 chars (762 core) | 4,160 chars |
| OpenCode, Codex | `AGENTS.md` | 6,830 words (about 11.5k tokens) | about 1,839 words (guardrails unchanged) | about 750 words (about 1.3k tokens) |
| OpenCode, Codex | skill listing | 3,398 chars | 4,160 chars | 4,441 chars (+ `playbook-guardrails`) |
| Continue IDE (opt-in) | `AGENTS.md` + `alwaysApply` rule files | 6,830 + 2,720 words | about 1,839 words + 2,250 words (D17 rewrite of the two always rules) | about 750 words + 2,250 words (guardrail rule files unchanged, D6) |

Prompts after PR 3 (Claude Code): `/refactor` 2,965 to 1,241 words, `/review` 1,963 to 922,
`/generate-tests` 1,414 to 433 (section 7.4.11).

## 5. PR 1 — Skill roots and Continue opt-in

Implements D10 and D11. Branches from `main` and runs in parallel with PR 2 (D19). Suggested title (Conventional Commits, following the precedent of #36): `feat(adapters): write shared skills to .agents/skills; make continue opt-in at init`.

### 5.1 Goal

1. Every skill copy the engine writes lands in a directory a harness actually reads. The `shared_skills` adapter moves from `shared_skills/<id>/` (read natively by no harness) to `.agents/skills/<id>/` (read natively by Codex and OpenCode). `claude_code` keeps writing `.claude/skills/` and `opencode` keeps writing `.opencode/skills/`. All three copies stay byte-identical through the one shared `SkillWriter`.
2. An existing consumer repo upgrades with no manual step. Its next `playbook sync` deletes the unchanged, untracked `shared_skills/` copies, prunes the emptied directory and rewrites the managed `.gitignore` block. Anything the user edited or git tracks is kept and reported, never silently left behind.
3. No engine output is ever a loose file directly inside a skill root. OpenCode v2 loads any root-level `*.md` in a skill root as a skill, so a loose file there would show up as a phantom skill.
4. `playbook init` stops enabling `continue` by default. A config that lists `continue` renders exactly what it renders today.

### 5.2 Scope

**In**

- `shared_skills` adapter: new root, plus a *retired output location* so the leftover policy cleans up the old tree.
- Adapter ABC: a new optional `retired_output_locations` class attribute. `orchestrator.installed_output_locations()` includes those locations.
- Leftover pruning (`commands/_output_locations.py`): the target of a symlinked skill root is never removed, whatever order the adapters are declared in. PR 1 makes `.agents/skills/` a declared root, and that turns a latent ordering bug into a likely one (section 5.4.3).
- `playbook init`: the new default adapter set, the interactive question and choices, and the `--adapters` help text. These move into a new `commands/_init_adapters.py`, because `init.py` is already 594 lines.
- `_sync_preflight.warn_missing_adapters`: a one-line hint when `adapters_enabled` lists `codex`. Older versions of the interactive `init` offered that name, but no adapter provides it.
- Tests, SPEC, README, MIGRATION, and the superpowers ATTRIBUTIONS path list.

**Out (with a one-line reason each)**

- Rendering, frontmatter and skill content: the `SkillWriter` bytes do not depend on the root, and D10 keeps standard frontmatter keys.
- Continue adapter behaviour (`continue_adapter.py`, renderer Continue paths): D11 requires today's exact output when Continue is enabled.
- Hook control-plane tables (`hook_runtime/handlers/_control_plane_paths.py:97`, `frontmatter_carriers = .claude/skills/ …`): these cover Claude Code skill frontmatter that can carry hooks, and Claude Code does not read `.agents/skills/`.
- `agent_harness` (`skills/` plus its `skills/SKILLS.md` routing file, `agent_harness_adapter.py:390-395`): `skills/` is not a skill root that Claude Code, OpenCode or Codex scans. The no-loose-file guarantee covers the three harness roots only (section 5.4.5).
- Adding `agent_harness` to the interactive choices: it targets harness clients rather than an assistant, and README already documents how to enable it.
- The misleading `shared_skills: N advisory` count in the sync hook summary (the adapter writes no advisory): this is cosmetic, belongs to the hooks work, and is unrelated to roots.
- CONTEXT.md: no change in PR 1. "Skill root" is already defined generically there, and PR 2 is the PR that commits the file, so editing it here would create an add/add conflict. PR 2 adds "_Avoid_: skills hub" under Skill root (section 6.9.5).

### 5.3 Decisions taken in this PR

| # | Decision | Rationale |
| --- | --- | --- |
| P1-1 | Keep the adapter id `shared_skills`. In prose, call it "the shared-skills adapter (`shared_skills`)" and its output "the shared skill root `.agents/skills/`". Drop the phrase "cross-agent skills hub" everywhere. | The id is a committed `adapters_enabled` value in every repo initialised since v0.15, the entry-point name (`pyproject.toml:64`) and the `adapter` field of lockfile rows. Renaming it needs an alias layer in config, entry points and the lockfile. Without one, an unknown name sets `keep_all` and disables leftover cleanup (`commands/sync.py:342`). The name still says what the adapter does: skills shared across agents. |
| P1-2 | Declare the old root as `retired_output_locations = ("shared_skills/",)` on the adapter. Do not hardcode it in `sync`. | The adapter owns its history. The location counts even after the adapter is disabled, because `installed_output_locations()` reads every installed class, and it is reusable for any future move. It stays out of guard_config's `generated` path class, which lists only current output. |
| P1-3 | Keep the retired location until 1.0. | It costs one tuple entry. Dropping it early would leave any repo that has not synced since with an untracked, committable `shared_skills/` tree. |
| P1-4 | Fix order-dependent pruning in this PR. | Probe-confirmed (section 5.4.3): 2 of 4 combinations of declaration order and link direction remove the link target, and PR 1 is what makes `.agents/skills/` declared. |
| P1-5 | No new runtime guard against loose files. The invariant is structural and pinned by tests. | `ensure_path_safe_skill_id` plus `SkillWriter._contained` already force every write under `<root>/<id>/`, and ids failing `^[a-z0-9]+(-[a-z0-9]+)*$` are refused by the validate gate before any write. |
| P1-6 | Drop `codex` from the interactive choices, and add a `codex` hint to the missing-adapter warning. | `codex` names no adapter. Selecting it made every later sync warn and keep every leftover (`keep_all`), which would also block this PR's cleanup. Codex is served by `AGENTS.md` plus `.agents/skills/`. |
| P1-7 | Extract `commands/_init_adapters.py`. | The default set, choices, question and flag help need one source of truth (D11 changes all four). It also reduces `init.py`'s overrun of the ~500 budget (594 to about 569 lines); bringing `init.py` under 500 is a separate split, out of scope here. |
| P1-8 | No new "moved" notice from `sync`. | Pristine output is deleted silently for every other move (for example the Claude rules move, MIGRATION §12). Everything kept is already reported by `report_kept_leftovers` / `warn_tracked_output`. |
| P1-9 | The engine repo's own `.gitignore` keeps `/shared_skills/` (line 231). | It is harmless, and developer checkouts may still hold the old directory. `/.agents/` is already ignored (line 227). |
| P1-10 | SPEC and MIGRATION version: whichever of PR 1 / PR 2 merges first opens **0.21**: the SPEC header, footer and appendix entry, the version pin in `tests/unit/test_docs_check_rubric_refactor.py:110-125`, the `## v0.21 — Skills-first context` section above `## v0.20` in MIGRATION.md, and the rewrite of `tests/unit/test_docs_migration_hooks.py:72-77` from "the first `## v` heading is v0.20" to "the `## v` headings are in descending version order" (the v0.20 TL;DR check stays). The other only appends its bullets, subsections and TL;DR rows. | Both PRs branch from `main` in parallel (D19). Without the docs-test rewrite, the PR that inserts `## v0.21` above `## v0.20` fails `test_migration_has_v0_20_lifecycle_hooks_section` ("newest release first"). The rule makes the rebase mechanical. |
| P1-11 | Plugin test helpers keep `continue` explicitly. `tests/conftest.py:53`'s default fixture config (`["continue", "claude_code", "opencode"]`) is unchanged. | It keeps the Continue degraded-prompt coverage. These configs are explicit lists, not the `init` default. |

### 5.4 Design, module by module

#### 5.4.1 `adapters/shared_skills_adapter.py` (current: lines 1-69)

Today the module defines `SHARED_SKILLS_ROOT = Path("shared_skills")` (line 30), `_SKILL_WRITER = SkillWriter(SHARED_SKILLS_ROOT)` (line 49) and `output_locations = (_SKILL_WRITER.location,)` (line 51). The change:

```python
#: Repo-relative shared skill root; Codex and OpenCode read ``.agents/skills/`` natively.
SHARED_SKILLS_ROOT = Path(".agents") / "skills"
#: Where engines before SPEC v0.21 wrote this adapter's skills. Declared as a retired
#: location so the next sync settles that tree by the leftover policy (SPEC §4.2 step 9).
RETIRED_SHARED_SKILLS_LOCATION = "shared_skills/"


class SharedSkillsAdapter(Adapter):
    name = "shared_skills"

    _SKILL_WRITER: ClassVar[SkillWriter] = SkillWriter(SHARED_SKILLS_ROOT)

    output_locations: ClassVar[tuple[str, ...]] = (_SKILL_WRITER.location,)
    retired_output_locations: ClassVar[tuple[str, ...]] = (RETIRED_SHARED_SKILLS_LOCATION,)
```

`write_rule`, `write_prompt` and `write_skill` are unchanged. The module and class docstrings change accordingly:

- `.agents/skills/<id>/` is the shared skill root, read natively by Codex (`.agents/skills` in every directory from the project root to cwd) and by OpenCode v1/v2 as a compatibility root.
- Claude Code and Continue do not read it. They read `.claude/skills/`.
- The class docstring example becomes `adapter.write_skill(skill, repo_root)  # -> [repo_root/".agents"/"skills"/<id>/"SKILL.md", ...]`.

**Rendered output (unchanged bytes, new place).** `.agents/skills/<id>/SKILL.md` is byte-identical to `.claude/skills/<id>/SKILL.md` and `.opencode/skills/<id>/SKILL.md`: frontmatter on line 1 with `name` = id, the sentinel as the first body line, then the body. `scripts/` and `references/` are byte-copied.

#### 5.4.2 `adapters/base.py` (current `output_locations` at lines 37-43) and `orchestrator.py` (current `installed_output_locations` at lines 361-380)

New class attribute on `Adapter`, placed right after `output_locations`:

```python
class Adapter(ABC):
    #: Locations an earlier engine release wrote for this adapter and it no longer
    #: writes. They bound the leftover policy exactly like :attr:`output_locations`
    #: (deletion allowlist and prune boundary), so the first sync after an upgrade
    #: settles the old tree; they are not current output, so guard_config.json's
    #: ``generated`` path class never lists them.
    retired_output_locations: ClassVar[tuple[str, ...]] = ()
```

`installed_output_locations()` gains one line:

```python
def installed_output_locations() -> tuple[str, ...]:
    """Every current and retired output location of an installed adapter, enabled or not.

    Example::

        >>> "shared_skills/" in installed_output_locations()  # doctest: +SKIP
        True
    """
    locations: list[str] = []
    for ep in metadata.entry_points(group="coding_agent_playbook.adapters"):
        try:
            cls = ep.load()
        except (ImportError, AttributeError):
            continue
        locations.extend(getattr(cls, "output_locations", ()))
        locations.extend(getattr(cls, "retired_output_locations", ()))
    return tuple(locations)
```

Consumers of these values, all verified:

- **Leftover policy.** `commands/sync.py:327-345` (`_leftover_policy`) builds `OutputLocations.declared([*installed_output_locations(), *SYNC_OUTPUT_LOCATIONS], …)`, so the retired location becomes a deletion bound and a prune boundary in write mode and in `--check`. No code change in `sync.py`.
- **Guard config.** `commands/_sync_hooks.py:265-267` (`_generated_locations`, feeding guard_config.json's `path_classes.generated`) reads only enabled adapters' `output_locations`. It now lists `.agents/skills/` and never `shared_skills/`. No code change.
- **Protected table.** `_guard_config_protect.py` (`COMPOSITE_SINGLETONS` lines 57-64; `adapter_output_dirs` via `_output_directories`, which `shared_skills` leaves at the ABC default `[]`): the `protected.output_dirs` table does not change. `protected.entries` follows the lockfile rows, so its paths move to `.agents/skills/…` on their own. No code change.

**Why a retired location is needed (probe, 2026-10-18).** The probe copied a synced consumer repo with the `python_design` plugin, then monkeypatched the root in-process; no repo files were edited.

- **Without a retired location**, the old orphans lie outside every declared location, so `plan_orphans` releases them (`_sync_orphans.py:121`). `shared_skills/` stayed on disk and dropped out of the managed `.gitignore` block, becoming untracked, committable files.
- **With the retired location**, the same sync printed `Summary: 107 files written, 16 removed`, and `shared_skills/` was pruned.

#### 5.4.3 `commands/_output_locations.py` (current `declared()` at lines 49-70, `_root_of` at lines 91-94)

**Bug (latent today, likely after PR 1).** `_root_of` returns `max(holders, key=len(parts))`, and `max` keeps the *first* maximal holder. When a directory is both declared as spelled (prunable) and the resolved target of another declared, symlinked root (not prunable), the outcome therefore depends on declaration order.

Installed entry-point order is alphabetical today: `agent_harness, agents_md, claude_code, continue, opencode, shared_skills`. A probe with both roots declared gave:

| Declared order | Link | Target survives the prune |
| --- | --- | --- |
| `.claude/skills/`, `.agents/skills/` | `.claude/skills -> ../.agents/skills` (the SPEC §4.2 step 9 example) | yes, by luck of order |
| `.claude/skills/`, `.agents/skills/` | `.agents/skills -> ../.claude/skills` (a common Codex setup) | **no**: `.claude/skills` is removed and the link dangles |
| `.agents/skills/`, `.claude/skills/` | `.claude/skills -> ../.agents/skills` | **no** |
| `.agents/skills/`, `.claude/skills/` | `.agents/skills -> ../.claude/skills` | yes |

**Fix.** A declared directory is prunable only when it is real as spelled *and* no other declared directory resolves to it through a symlink:

```python
@classmethod
def declared(cls, locations: Iterable[str], repo_root: Path) -> OutputLocations:
    """Build from ``output_locations`` entries (a trailing ``/`` marks a directory)."""
    root = repo_root.resolve()
    files: set[str] = set()
    dirs: list[tuple[PurePosixPath, PurePosixPath | None]] = []
    for location in locations:
        spelled = PurePosixPath(location.rstrip("/"))
        if spelled.is_absolute() or not spelled.parts or ".." in spelled.parts:
            continue
        resolved = _resolved_rel(root.joinpath(*spelled.parts), root)
        if location.endswith("/"):
            dirs.append((spelled, resolved))
        else:
            files.update(rel.as_posix() for rel in (spelled, resolved) if rel is not None)
    return cls(frozenset(files), _declared_roots(dirs))


def _declared_roots(
    dirs: Sequence[tuple[PurePosixPath, PurePosixPath | None]],
) -> tuple[_Root, ...]:
    """Each declared directory as spelled and, through a symlink, as resolved.

    A directory is prunable only when it is real as spelled and no other declared
    directory is a symlink to it, whatever order the adapters declared them in.

    Example::

        >>> _declared_roots([(PurePosixPath("a"), PurePosixPath("a"))])
        (_Root(rel=PurePosixPath('a'), prunable=True),)
    """
    link_targets = {
        resolved for spelled, resolved in dirs if resolved is not None and resolved != spelled
    }
    roots: list[_Root] = []
    for spelled, resolved in dirs:
        roots.append(_Root(spelled, prunable=resolved == spelled and spelled not in link_targets))
        if resolved is not None and resolved.parts and resolved != spelled:
            roots.append(_Root(resolved, prunable=False))
    return tuple(roots)
```

`Sequence` joins the existing `TYPE_CHECKING` import of `Iterable`. After the fix, every `_Root` with the same `rel` carries the same `prunable` value, so `_root_of`'s tie-break no longer matters. The file stays at about 135 lines.

An unlinked, emptied `.agents/skills/` is still removed, while `.agents/` itself stays. That matches `.claude/skills/` today.

#### 5.4.4 Unchanged on purpose (verified)

- **The other skill roots.** `claude_code_adapter.py:137-138` keeps `SkillWriter(Path(".claude") / "skills")` and `opencode_adapter.py:83-84` keeps `SkillWriter(Path(".opencode") / "skills")`.
- **`SkillWriter`** (`adapters/_skill_writer.py:212-275`): root-agnostic, and its bytes never depend on the root.
- **Managed `.gitignore` block** (`gitignore.py:80-110`): skill directories are detected generically from written `SKILL.md` paths, so the entries become `/.agents/skills/<id>/` with no code change.
- **Lockfile:** schema 2 is unchanged, and rows keep `adapter = "shared_skills"`.
- **The validate-then-sync hook** (`catalog/core/hooks/protect/validate-then-sync-on-canonical-edit/HOOK.md:12-29`): its watch globs list canonical sources only (`playbook/…`, `src/*/resources/…`, `catalog/…`, `.coding-agent-playbook.toml`) and no generated root, so nothing to change.
- **Engine `.pre-commit-hooks.yaml` and `templates/precommit/config.yaml.j2`:** neither names a skill root.
- **Symlinked roots.** Both directions are handled by the existing mapping (`_guard_config_protect._lock_path_via_repo_links`, `sync._on_real_tree`, `lockfile.merge_provenance`): `.claude/skills -> ../.agents/skills`, where `claude_code` and `shared_skills` now write the same physical files, and `.agents/skills -> ../.claude/skills`. Each file gets one `composite` lock row, and write mode and `--check` agree. Section 5.7 pins this with tests.

#### 5.4.5 No loose file in a skill root (D10 guarantee)

The invariant: every path any adapter writes under `.claude/skills/`, `.opencode/skills/` or `.agents/skills/` has the form `<root>/<id>/<…>`, with at least two path parts below the root. The first part is the skill id, and it is a directory.

Where it is enforced:

- `ensure_path_safe_skill_id` (`_skill_writer.py:122-144`) accepts a single relative segment only.
- `SkillWriter._contained` (`:266-275`) refuses a skill directory that resolves outside the root.
- `_write_skill_files` (`:403-415`) writes only `SKILL.md`, `scripts/**` and `references/**` inside the claimed directory.
- The validate gate (`commands/sync.py` `_passes_validation`, run before write mode and `--check`) refuses ids that do not match `AGENT_SKILL_NAME_PATTERN` (`_skill_writer.py:68`), so an id such as `notes.md` never reaches a writer. `--check-staged` skips validation but renders only into a scratch directory.
- The only engine file directly inside a skills-like root is `agent_harness`'s `skills/SKILLS.md`, which is not a harness skill root. SPEC §10.8 says so and tells users not to point `.agents/skills` or another harness root at `skills/`.

Pinned by one unit test and one end-to-end test (section 5.7). No runtime code is added (P1-5).

#### 5.4.6 `playbook init`: Continue becomes opt-in

**New module `src/coding_agent_playbook/commands/_init_adapters.py`** (about 60 lines). It takes over `_DEFAULT_ADAPTERS` (`init.py:60-62`) and `_adapters_union` (`init.py:308-320`), and adds the choices, the question, the flag help and the flag parser:

```python
"""The adapter list ``playbook init`` offers and writes (SPEC §12.1).

Split out of ``commands/init.py`` (over the module-size budget) so the default set,
the interactive choices and the flag help share one source of truth.
"""

from __future__ import annotations

from typing import Final

#: What ``playbook init`` enables when ``--adapters`` is absent. ``continue`` is
#: opt-in since SPEC v0.21: upstream Continue is in maintenance, and its IDE loads
#: the root AGENTS.md and ``.claude/skills/`` without an adapter of its own.
DEFAULT_ADAPTERS: Final[tuple[str, ...]] = ("claude_code", "opencode", "shared_skills")

#: The interactive choices: the defaults, then the opt-in harness adapter. Only
#: installed built-ins: the old ``codex`` choice named no adapter, and a missing
#: adapter makes every later sync keep all leftovers.
ADAPTER_CHOICES: Final[tuple[str, ...]] = (*DEFAULT_ADAPTERS, "continue")

ADAPTERS_QUESTION: Final = (
    "Which assistants will the team use? continue is opt-in; "
    "Codex reads AGENTS.md and .agents/skills/ (shared_skills)"
)

ADAPTERS_FLAG_HELP: Final = (
    f"comma-separated adapter names (default: {','.join(DEFAULT_ADAPTERS)}; add continue to opt in)"
)


def adapters_from_flag(raw: str | None) -> list[str]:
    """Parse ``--adapters``; absent or blank means :data:`DEFAULT_ADAPTERS`.

    Example::

        >>> adapters_from_flag(None)
        ['claude_code', 'opencode', 'shared_skills']
        >>> adapters_from_flag("continue, claude_code")
        ['continue', 'claude_code']
    """
    text = raw or ",".join(DEFAULT_ADAPTERS)
    return [name.strip() for name in text.split(",") if name.strip()]


def adapters_union(committed: list[str], answered: list[str]) -> list[str]:
    """The committed adapters in their order, then each answered one not listed yet.

    A re-run never drops an adapter the team enabled by hand (a committed
    ``continue`` stays), and adds the answered (default) ones it lacks.

    Example::

        >>> adapters_union(["continue", "custom"], ["claude_code", "continue"])
        ['continue', 'custom', 'claude_code']
    """
    return [*committed, *(name for name in dict.fromkeys(answered) if name not in committed)]
```

**`commands/init.py`**

- Lines 60-62: delete `_DEFAULT_ADAPTERS` and its comment. Import `ADAPTER_CHOICES`, `ADAPTERS_QUESTION`, `DEFAULT_ADAPTERS`, `adapters_from_flag` and `adapters_union` from `_init_adapters`.
- Lines 153-154 (non-interactive): `adapters = adapters_from_flag(getattr(args, "adapters", None))`.
- Lines 174-178 (interactive): `_prompt_multi_select(ADAPTERS_QUESTION, list(ADAPTER_CHOICES), list(DEFAULT_ADAPTERS))`. The `"codex"` choice is gone.
- Line 301: `adapters_enabled=adapters_union(committed.adapters_enabled, answers["adapters"])`. Delete `_adapters_union` (lines 308-320). In the `_apply_answers` docstring (line 289), replace `:func:`_adapters_union`` with `:func:`~coding_agent_playbook.commands._init_adapters.adapters_union``.
- Net change: about 25 lines shorter.

**`cli.py:86`**: `init_p.add_argument("--adapters", help=ADAPTERS_FLAG_HELP)`, importing it from `commands._init_adapters`.

**Rendered interactive question** (`_prompt_multi_select` itself is unchanged, `init.py:91-109`):

```text
Which assistants will the team use? continue is opt-in; Codex reads AGENTS.md and .agents/skills/ (shared_skills) (comma-separated indices, blank=defaults=claude_code, opencode, shared_skills)
  * 1. claude_code
  * 2. opencode
  * 3. shared_skills
    4. continue
>
```

**Config written by a fresh `playbook init --non-interactive --name r --kind python-library`:**

```toml
schema_version = 1
adapters_enabled = ["claude_code", "opencode", "shared_skills"]
```

**Repos that list Continue.** A repo whose committed list already contains `continue`, whether from an earlier `init` default or by hand, keeps it on every re-run (`adapters_union`) and on every sync. Its `.continue/` output is unchanged, because `continue_adapter.py` and the Continue paths in `renderer.py` (lines 298-318 and 426-438) are not touched. To drop Continue, remove `"continue"` from `adapters_enabled`. The next sync then deletes its pristine `.continue/rules/` and `.continue/prompts/` files as leftovers: `continue`'s declared `output_locations` (`continue_adapter.py:50`) count while the adapter is installed.

#### 5.4.7 `commands/_sync_preflight.py`: the `codex` hint (current `warn_missing_adapters` at lines 124-131)

```python
#: Names that are a harness, not an adapter, with where that harness's output comes from.
_NOT_ADAPTERS: Final[Mapping[str, str]] = MappingProxyType(
    {"codex": "Codex reads AGENTS.md and .agents/skills/ (the shared_skills adapter)"}
)


def warn_missing_adapters(names: Sequence[str]) -> None:
    """Warn on stderr that enabled adapters were skipped (their old output is kept)."""
    print(
        f"warning: enabled adapter(s) not installed, skipped: {', '.join(names)}.\n"
        "Their previously generated output is kept (and stays gitignored) until they are\n"
        f"installed or removed from adapters_enabled.\n{_not_adapter_hints(names)}"
        f"{_HOOK_VENV_HINT}",
        file=sys.stderr,
    )


def _not_adapter_hints(names: Sequence[str]) -> str:
    """One line per name in ``names`` that no adapter provides by design.

    Example::

        >>> _not_adapter_hints(["codex", "custom"]).count("\\n")
        1
    """
    return "".join(
        f"'{name}' is not an adapter: {_NOT_ADAPTERS[name]}; remove it from adapters_enabled.\n"
        for name in names
        if name in _NOT_ADAPTERS
    )
```

The new imports are `Final` from `typing`, `MappingProxyType` from `types`, and `Mapping` from `collections.abc` under `TYPE_CHECKING`.

#### 5.4.8 Docstring and comment touch-ups (no behaviour change)

These comments name the old path; they now name the shared skill root `.agents/skills/`:

- `adapters/_skill_writer.py:8`
- `adapters/_skill_files.py:4`
- `gitignore.py:21`
- `adapters/opencode_adapter.py:28-34` and `:148`. The module docstring adds that OpenCode also scans `.agents/skills/` as a compatibility root. v2 registers one copy per id with precedence `.opencode > .agents > .claude`. v1 logs one duplicate warning per extra copy, which `OPENCODE_DISABLE_EXTERNAL_SKILLS` / `OPENCODE_DISABLE_CLAUDE_CODE_SKILLS` silence; the engine sets neither.

These name only the adapter id and stay as they are: `agents_md_adapter.py:39,96`, `claude_code_adapter.py:15`, `types.py:239`, `base.py:80`, `orchestrator.py:343`.

### 5.5 Validation and error messages

PR 1 adds no config key, no `playbook validate` finding and no new error.

**One new stderr line**, printed only when `adapters_enabled` lists `codex`. Example for `adapters_enabled = ["claude_code", "codex"]`:

```text
warning: enabled adapter(s) not installed, skipped: codex.
Their previously generated output is kept (and stays gitignored) until they are
installed or removed from adapters_enabled.
'codex' is not an adapter: Codex reads AGENTS.md and .agents/skills/ (the shared_skills adapter); remove it from adapters_enabled.
A pre-commit hook from the engine's .pre-commit-hooks.yaml (language: python) runs in
…
```

**Existing messages users will see once, around the upgrade** (text unchanged):

- `playbook sync --check` before the first post-upgrade sync. The probe output, abridged:

  ```text
  Drift detected:
    .agents/skills/python-architecture/SKILL.md
      Missing on disk; run 'playbook sync' to create.
    shared_skills/python-architecture/SKILL.md
      Orphaned generated file; run 'playbook sync' to remove.
    .gitignore
      Managed block is missing or stale ([output] commit = false).
      Run 'playbook sync' to regenerate.
  ```

- `commit = true`: `note: kept output an earlier sync wrote that this sync no longer generates … Delete any you no longer need (git rm for tracked ones).`, listing the tracked `shared_skills/` files (`_sync_output.py:277-301`).
- `commit = false` with `shared_skills/` committed by hand: `warning: generated output is still tracked by git …` together with the exact `git rm -r --cached -- …` command (`_sync_output.py:251-274`).
- A user's own `.agents/skills/<id>/` whose id collides with an engine skill: `warning: not writing <dir>: it exists but is not playbook-managed …` (`_skill_writer.py:327-335`). The directory is never overwritten.

### 5.6 Migration, orphan and lockfile effects

On the first write-mode `playbook sync` after upgrading (run by hand, or by the post-checkout / post-merge hook):

1. `shared_skills` writes `.agents/skills/<id>/`, and the lockfile records those rows with `adapter = "shared_skills"`.
2. Every previous-lockfile row under `shared_skills/` is an orphan. It lies in a declared location, because the retired location is declared. It is deleted when its bytes still match and git does not track it.
3. Emptied directories are pruned bottom-up, including `shared_skills/` itself, which is a real directory as spelled.
4. Kept orphans stay owned. They remain in the lockfile, and under `commit = false` in the managed block, as `/shared_skills/<id>/` when their `SKILL.md` is kept, or as per-file entries otherwise. Kept orphans are files the user edited or that git tracks.
5. Files a user added inside `shared_skills/<id>/` were never in the lockfile, so they are never deleted. If the skill's `SKILL.md` was deleted, they also leave the managed block. This is today's opt-out policy (SPEC §11.5, line 2082).
6. The managed `.gitignore` block swaps `/shared_skills/<id>/` for `/.agents/skills/<id>/`.
7. guard_config.json (hooks on) changes its `generated` class and its `protected.entries` paths.
8. The lockfile schema does not change, and no lockfile migration code is needed.

Effects by repo setup:

- **`[output] commit = true`:** tracked `shared_skills/` files are kept and listed on stderr. The user runs `git rm -r shared_skills` and commits `.agents/skills/`. Until then, the legacy `playbook-sync-check` hook reports drift (`.agents/skills/…` missing from the commit).
- **An enabled adapter is missing** (including a listed `codex`): every orphan is kept (`keep_all`), so the cleanup waits until the list is fixed. The new hint names the fix.
- **Consumer tooling:**
  - Scripts, CI globs or mypy/ruff excludes that point at `shared_skills/` must point at `.agents/skills/`.
  - `mypy .` skips dot-directories, so the default adapters no longer expose any skill script copy to it. The duplicate-module failure that SPEC §11.5.2 (line 2135) describes now happens only if a second root outside dot-directories exists. That is `agent_harness`'s `skills/`, and it is a single copy.
  - `ruff check .` behaves as before: under `commit = false` it skips gitignored copies, and under `commit = true` it lints every copy.

### 5.7 Tests

All tests run under the CI gate `ruff check . && ruff format --check . && mypy && pytest -q`.

**New tests**

| File | Test | Asserts |
| --- | --- | --- |
| `tests/adapters/test_shared_skills.py` | `test_native_skill_roots_are_claude_opencode_and_agents` | Each skill-writing adapter's skills entries in `output_locations` map to `{"claude_code": [".claude/skills/"], "opencode": [".opencode/skills/"], "shared_skills": [".agents/skills/"]}`. Pins D10's "unchanged" roots. |
| same | `test_no_adapter_writes_a_file_directly_in_its_skills_root` (parametrized over the three adapter classes) | For a skill with `scripts/run.py`, `references/README.md` and `references/api/v1.md`: every written path relative to the root has ≥ 2 parts, its first part is the id, and the root's direct children are all directories. |
| same | `test_installed_output_locations_include_the_retired_root` | `"shared_skills/"` and `".agents/skills/"` are both in `installed_output_locations()`. |
| same | `test_generated_path_class_omits_the_retired_root` | `_sync_hooks._generated_locations({"shared_skills": SharedSkillsAdapter()})` contains `.agents/skills/` and not `shared_skills/`. |
| `tests/unit/test_output_locations.py` (new) | `test_link_target_is_never_pruned_whatever_the_declaration_order` (2 orders × 2 link directions) | **Regression for section 5.4.3:** after the last file is deleted and `prune_emptied` runs, the link target is still a directory and the link still resolves. Before the fix, 2 of the 4 cases fail. |
| same | `test_unlinked_declared_root_is_pruned_once_empty` | With no links, an emptied `.agents/skills` is removed and `.agents` is kept (existing behaviour). |
| same | `test_retired_location_bounds_deletion_like_a_current_one` | `declared(("shared_skills/",)).contains("shared_skills/x/SKILL.md")` is true; `shared_skillsx/a` is false. |
| `tests/cli/test_sync_skill_root_move.py` (new; helpers `_rewind_to_shared_skills_root`, `_managed_block`, `_lock_paths`) | `test_first_sync_after_upgrade_moves_pristine_shared_skills_tree` | `shared_skills/` is gone; `.agents/skills/query-db/SKILL.md` equals the `.claude/skills` copy byte for byte; no lock row under `shared_skills/`; the block has `/.agents/skills/query-db/` and no `/shared_skills/`. |
| same | `test_check_before_the_move_reports_the_old_tree_as_orphans` | `--check` exits 1 with the orphan and missing lines shown in section 5.5. After `sync`, `--check` exits 0. |
| same | `test_edited_shared_skills_file_is_kept_owned_and_ignored` | An edited `scripts/run.py` keeps its bytes, stays in the lockfile and stays in the block. The pristine `SKILL.md` is deleted. |
| same | `test_tracked_tree_is_kept_and_reported_under_commit_true` | With `commit = true` and `FakeGitClient(tracked=…)`, the files remain and stderr carries `note: kept output` plus the paths. |
| same | `test_user_authored_shared_skills_dir_is_never_touched` | A hand-written `shared_skills/mine/SKILL.md` that no lockfile lists is byte-identical after sync. |
| same | `test_sync_writes_no_loose_file_at_any_skill_root` | Default adapters plus `continue`, the `python_design` plugin and a repo-local skill: no non-directory child in any of the three roots, and no lock row exactly one level below a root. |
| same | `test_agents_skills_linked_to_claude_skills_survives_removing_every_skill` | With `.agents/skills -> ../.claude/skills`: sync, then `--check` exits 0; after the skill is removed and synced again, `.claude/skills` is a directory, the link resolves, and `--check` exits 0. |
| same | `test_claude_skills_linked_to_agents_skills_has_one_lock_row_per_file` | With `.claude/skills -> ../.agents/skills`: each `.agents/skills/query-db/…` path appears exactly once in the lockfile, there are no `.claude/skills/…` rows, and `--check` / `--check-staged` exit 0. |
| `tests/cli/test_init_adapters.py` (new) | `test_fresh_init_enables_claude_code_opencode_and_shared_skills` | `adapters_enabled == list(DEFAULT_ADAPTERS)`, and `.continue/` does not exist after the final sync. |
| same | `test_init_with_continue_listed_renders_continue_rules_and_prompts` | `--adapters claude_code,opencode,shared_skills,continue` writes `.continue/rules/00-project-context.md` and the core prompts under `.continue/prompts/`. |
| same | `test_init_rerun_keeps_a_committed_continue` | A committed `["continue", "claude_code", "opencode", "shared_skills"]` comes back byte-identical after a non-interactive re-run. |
| same | `test_interactive_choices_are_installed_adapters_defaults_first` | **Regression for the `codex` choice:** `ADAPTER_CHOICES[:3] == DEFAULT_ADAPTERS`; every choice is an installed entry point; `"codex"` is absent. |
| same | `test_interactive_blank_answer_leaves_continue_off` | A blank answer gives the defaults, and the printed question contains `continue is opt-in`. |
| same | `test_interactive_index_four_enables_continue` | The answer `1,2,3,4` includes `continue`. |
| same | `test_adapters_flag_help_names_the_default_set` | `playbook init --help` output contains `claude_code,opencode,shared_skills`. |
| same | `test_adapters_from_flag_parses_and_defaults` (parametrized) | `None` and `""` give the defaults; `" continue , claude_code ,"` gives `["continue", "claude_code"]`. |
| same | `test_adapters_union_keeps_committed_order_then_appends_new_answers` | Moved from `tests/cli/test_init.py:771-777`, now calling `adapters_union`. |
| `tests/unit/test_sync_preflight.py` | `test_warn_missing_adapters_explains_codex` | stderr contains the exact `'codex' is not an adapter: …; remove it from adapters_enabled.` line. |
| same | `test_warn_missing_adapters_gives_no_hint_for_other_names` | A missing `custom` adapter produces no `is not an adapter` text. |
| `tests/unit/test_docs_skill_roots.py` (new) | `test_spec_10_8_names_the_shared_root_and_its_retired_location` | SPEC §10.8 names `` `.agents/skills/<id>/` `` and the retired `` `shared_skills/` ``. |
| same | `test_documented_init_default_matches_the_code` | Every SPEC/README `adapters_enabled = [...]` line marked `# the init default` parses to `DEFAULT_ADAPTERS`. The SPEC line is 2051; README line 269 gains the marker. |
| same | `test_readme_skills_section_names_every_native_root` | README's "Skills: one source, every Agent-Skills root" section contains each of the three skills locations. |
| same | `test_spec_init_transcript_offers_no_codex_choice` | SPEC §12.1 no longer contains `Codex CLI (AGENTS.md only)`. |

**Changed tests**

- `tests/adapters/test_shared_skills.py`:
  - `test_shared_skills_adapter_identity` now pins `SHARED_SKILLS_ROOT == Path(".agents") / "skills"`, `output_locations == (".agents/skills/",)` and `retired_output_locations == ("shared_skills/",)`.
  - `test_write_skill_writes_shared_skills_dir` is renamed to `test_write_skill_writes_agents_skills_dir`, with paths under `.agents/skills`.
  - `test_cleanup_stale_never_deletes_skill_files` updates its paths.
- `tests/adapters/test_skill_writer.py`: `_ROOTS` (line 40) gets `Path(".agents") / "skills"` as its third entry. A module constant `_WRITER_ROOT = Path(".agents") / "skills"` replaces the literal `Path("shared_skills")` / `"shared_skills"` segments (lines 189-819, mechanical), including the `FakeGitClient(tracked=…)` string at line 653. Behaviour is identical because the writer is root-agnostic.
- `tests/cli/test_sync_skills.py`:
  - `_SKILL_ROOTS` (line 27) gets `.agents/skills`.
  - Path literals change at lines 114, 116, 151, 187, 217, 244, 257, 266, 415, 418 and 440.
  - `test_sync_without_shared_skills_adapter_skips_hub` is renamed to `test_sync_without_shared_skills_adapter_writes_no_agents_skills` and asserts `not (repo / ".agents" / "skills").exists()`.
  - The `symlinked-skills-root-removed-skill` parity scenario (lines 491-497) now exercises section 5.4.3 directly; it stays.
- `tests/plugins/superpowers_expectations.py`:
  - `NATIVE_SKILL_ROOTS` (line 150) gets `.agents/skills`.
  - `DEFAULT_ADAPTERS` (line 153) is renamed to `SKILL_ADAPTERS = ("continue", "claude_code", "opencode", "shared_skills")`, with docstring "every built-in adapter that emits skills, natively or degraded; continue is opt-in at init since v0.21 and listed here so the degraded prompts stay covered".
  - Callers in `tests/plugins/test_superpowers_sync.py` (lines 43, 102, 135, 374) are renamed. Paths at lines 291, 307 and 309 move to `.agents/skills/`.
- `tests/plugins/python_design/test_pack.py`: the `opted_in_repo` fixture (lines 252-259) passes `adapters=",".join(SKILL_ADAPTERS)`, so `test_continue_degrades_each_skill_to_its_skill_md_body` (line 296) keeps a Continue output to check. Line 376 checks `.agents/skills`.
- `tests/cli/test_init.py`:
  - Line 65 becomes `assert data["adapters_enabled"] == ["claude_code", "opencode", "shared_skills"]`.
  - Lines 106-117: `test_init_default_adapters_include_shared_skills` is renamed to `test_init_default_adapters_leave_continue_opt_in` and pins the new tuple.
  - Lines 119-128 are unchanged in content.
  - `_init._DEFAULT_ADAPTERS` references at lines 112, 116, 593 and 720 import `DEFAULT_ADAPTERS` from `_init_adapters`.
  - Line 718's expectation `["continue", *defaults without continue]` still holds unchanged.
- `tests/adapters/test_agent_harness.py:758`: import `DEFAULT_ADAPTERS` from `commands._init_adapters`.
- `tests/unit/test_docs_check_rubric_refactor.py:120-121`: the version pins become `0.21` if PR 1 opens the version (P1-10).
- `tests/unit/test_docs_migration_hooks.py:72-77`, if PR 1 opens the version (P1-10): `test_migration_has_v0_20_lifecycle_hooks_section` keeps `_V020 in text` and its TL;DR check, and replaces "the first `## v` heading is v0.20" with "every `## v<major>.<minor>` heading is in descending version order" (parse each heading's version with a regex and compare the list with its sorted copy, `reverse=True`). Without it, the `## v0.21` section PR 1 inserts above `## v0.20` fails the "newest release first" assertion. `test_migration_heads_up_points_at_v0_20` (`:80-83`) keeps passing, because the heads-up keeps its v0.20 paragraph.

**Deliberately unchanged**

- `tests/unit/test_gitignore.py:84-100`: it uses `shared_skills/` as an *arbitrary* non-adapter root to prove that skill directories are detected generically.
- `tests/conftest.py:53`, `tests/unit/test_dump_toml.py`, `tests/cli/test_config_errors.py`: explicit config texts, not the init default.
- `tests/adapters/test_continue.py`: it must pass byte-for-byte as is (D11).

### 5.8 Docs to update

**SPEC.md**

- **Header and changelog.** Line 4 (`Version`), line 6 (`Last updated`), a new top bullet `- **0.21** —` above line 12, the footer at line 3770, and a new `### v0.21 (<date>)` appendix entry before line 3773 (P1-10). The bullet covers: the `shared_skills` root move with a retired location, Continue becoming opt-in at init, order-independent pruning, and the `codex` choice and hint.
- **§2.2.** Line 45: "the agent-neutral `shared_skills/` hub" becomes "the shared skill root `.agents/skills/` (§10.8)". Line 48: the Codex non-goal adds "and its skills from `.agents/skills/` (§10.8)".
- **§3.** Line 70: the Skill entry swaps the hub for `.agents/skills/`. PR 2 replaces §3 with a pointer; take PR 2's version on conflict.
- **§4.1 and §4.2.** Line 156: the diagram reads `.agents/skills/*/`. Line 202 (§4.2 step 9): append "…even when the target is itself a declared location (`.claude/skills -> ../.agents/skills` with `shared_skills` on, or `.agents/skills -> ../.claude/skills`), whatever order the adapters declare them in".
- **§5.1.** Line 332: the comment reads `# the shared skill root .agents/skills/`.
- **§5.3.**
  - Lines 418-430: annotate the `.continue/` block "only with `continue` in `adapters_enabled` (opt-in since v0.21)".
  - Lines 461-462: `shared_skills/` becomes `.agents/` → `skills/` with "AUTOGENERATED — shared skill root (Codex, OpenCode), §10.8".
  - Line 473: the list of local-only output names `.agents/skills/<id>/`.
  - Lines 476-487: the example block gains `/.agents/skills/review/` as its first entry (it sorts first), and `/shared_skills/review/` and `/.continue/rules/50-python-typing.md` are dropped.
  - Line 492: OpenCode also scans `.agents/skills/`.
- **§6.3.** Line 784: `shared_skills` (`.agents/skills/`). PR 2 rewrites §6.3; keep the edit minimal.
- **§7.1.** Lines 1209-1211: the comment and the list become `["claude_code", "opencode", "shared_skills"]`, with the comment "add `continue` to opt in".
- **§10.1.** In the ABC snippet at line 1580, add the `retired_output_locations` attribute and its comment (ruff-format clean, as in section 5.4.2).
- **§10.4.** Line 1830: "skills also through `.agents/skills/`".
- **§10.6.** Lines 1851 and 1915: OpenCode discovers up to three copies (`.opencode`, `.agents`, `.claude`). v2 applies its precedence; v1 warns per duplicate, and the warning can be silenced with the environment variables named in section 5.4.8.
- **§10.8** (lines 1970-1993):
  - Rewrite the opening paragraph: the shared-skills adapter (`shared_skills`), `.agents/skills/<id>/`, who reads it (Codex natively; OpenCode as a compatibility root; not Claude Code or Continue), why it moved (D10), and the retired location `shared_skills/`.
  - Replace the code block with the ruff-format-clean version below.
  - Fix the root list on line 1985.
  - Add two bullets: "Retired location", and "No loose file in a skill root" (the section 5.4.5 invariant, plus the warning not to point a harness root at `agent_harness`'s `skills/`).

  ```python
  class SharedSkillsAdapter(Adapter):
      name = "shared_skills"
      output_locations = (".agents/skills/",)
      retired_output_locations = ("shared_skills/",)  # settled by the leftover policy

      def write_rule(self, rule: Rule, repo_root: Path) -> list[Path]:
          return []  # rules -> AGENTS.md

      def write_prompt(self, prompt: Prompt, repo_root: Path) -> list[Path]:
          return []  # prompts -> harness adapters

      def write_skill(self, skill: Skill, repo_root: Path) -> list[Path]:
          return SkillWriter(Path(".agents") / "skills").write(skill, repo_root)
  ```

- **§11.5.** Line 2051: the list becomes `["claude_code", "opencode", "shared_skills"]   # the init default`. Lines 2082, 2112, 2119, 2121 and 2139: `shared_skills/` becomes `.agents/skills/`. Line 2135: rewrite the mypy paragraph per section 5.6.
- **§12.1.**
  - Lines 2187-2192: the transcript shows `◉ Claude Code`, `◉ OpenCode`, `◉ Shared skills (.agents/skills/: Codex, OpenCode)`, `◯ Continue (opt-in)`, and no Codex line.
  - Line 2211: "Review generated AGENTS.md, .claude/, .opencode/, .agents/skills/".
  - Line 2213 is replaced with "Start your assistant; it reads AGENTS.md and its own directory".
  - Add one sentence on the default set, `--adapters`, and why Continue is opt-in (D11).
- **§12.2.** Line 2257: drop `continue: 25 advisory` from the example summary. The §12.4 example at lines 2346-2347 keeps `continue`, because it illustrates per-adapter labels.
- **§17.3.** Line 3145: `shared_skills/` becomes `.agents/skills/`.
- The history entries at lines 3808-3849 stay as they are.

**README.md**

- Line 9 and lines 54-55: the `shared_skills` adapter writes `.agents/skills/`, read by Codex and OpenCode.
- Lines 98, 161, 173, 219 and 573: `shared_skills/` becomes `.agents/skills/`. `.continue/` gets "(when enabled)" where outputs are listed.
- Lines 196-205 ("Initialize"): add the default set and the opt-in command for Continue: `playbook init --adapters claude_code,opencode,shared_skills,continue`.
- Lines 269-271: the list becomes `["claude_code", "opencode", "shared_skills"]   # the init default`, and the comment changes to "add "continue" to opt in; drop "shared_skills" to skip .agents/skills/".
- Lines 330-346 (Skills section):
  - The diagram row becomes `.agents/skills/<id>/   (shared_skills: Codex, OpenCode)`.
  - The bullet explains the root, the OpenCode duplicate note with its environment variables, and the move from `shared_skills/`.
  - Add a bullet: no loose file at a root.
- Line 391: the superpowers example list follows the new default. Line 423: the roots list is updated.
- Lines 474-480: rewrite the mypy paragraph per section 5.6.

**MIGRATION.md**

PR 1 contributes to the one shared `## v0.21 — Skills-first context` section (section 14, H14). If PR 1 merges before PR 2, it creates that section, inserted before line 15, and adds one line to the heads-up block at lines 3-12. Its subsections are unnumbered `###` headings, referred to by title. PR 1 contributes:

- **TL;DR rows** (the section has one TL;DR table; each PR adds its rows):

  | You are… | Migration |
  | --- | --- |
  | Every consumer repo (`commit = false`) | Nothing: the next `playbook sync` writes `.agents/skills/`, deletes the unchanged `shared_skills/` copies and updates the managed block. |
  | A repo with `commit = true` | Run `playbook sync`, then `git rm -r shared_skills` and commit `.agents/skills/`. |
  | Tooling that points at `shared_skills/` | Point it at `.agents/skills/`. |
  | `codex` in `adapters_enabled` | Remove it. |
  | Continue users | Existing repos: nothing, a committed `continue` stays. New repos: add `continue` to `--adapters`. |

- `### The shared_skills adapter writes .agents/skills/`: why (Codex, OpenCode), what the next sync does (section 5.6), what is kept, the OpenCode v1 duplicate warnings, the environment variables, and the mypy improvement.
- `### playbook init no longer enables Continue`: why (D11: upstream maintenance freeze; Continue's IDE loads the root `AGENTS.md` and `.claude/skills/`), how to opt in, and how to opt out of an existing `continue`.
- `### "codex" in adapters_enabled`: it blocked leftover cleanup (`keep_all`); remove it.
- `### Not changed (shared_skills and Continue)`: Continue output when enabled; `.claude/skills/` and `.opencode/skills/`; skill bytes; the lockfile schema; the adapter id.

The PR that merges second appends its subsections and TL;DR rows to the same section (P1-10). The PR that creates the section also rewrites `tests/unit/test_docs_migration_hooks.py:72-77` (section 5.7, "Changed tests"), or its own CI fails.

**Other files**

- `catalog/plugins/superpowers/ATTRIBUTIONS.md:17`: the list of synced copies names `.agents/skills/<id>/`.
- `catalog/README.md`: no change; it names neither `shared_skills` nor the default adapters (verified).
- CONTEXT.md: no change in PR 1 (section 5.2).
- No ADR (D18).

### 5.9 Acceptance criteria

1. A fresh `timeout 180 playbook init --non-interactive --name probe --kind python-application </dev/null` in a scratch git repo writes `adapters_enabled = ["claude_code", "opencode", "shared_skills"]` and creates no `.continue/`.
2. With `--adapters claude_code,opencode,shared_skills,continue`, `.continue/rules/` and `.continue/prompts/` are written. `git diff main -- src/coding_agent_playbook/adapters/continue_adapter.py src/coding_agent_playbook/renderer.py` is empty, and `tests/adapters/test_continue.py` passes unmodified.
3. With the `python_design` plugin on, `.agents/skills/<id>/` exists for both skills and is byte-identical to the `.claude/skills/` and `.opencode/skills/` copies. No `shared_skills/` directory is written.
4. On a repo synced by the previous engine (simulated by `_rewind_to_shared_skills_root`):
   - `sync --check` exits 1 and lists the `shared_skills/…` orphans;
   - the next `sync` deletes the pristine files and prunes `shared_skills/`;
   - the managed block holds `/.agents/skills/<id>/` and no `/shared_skills/<id>/`;
   - `sync --check` then exits 0.
5. Edited or tracked `shared_skills/` files are kept, still owned, and reported. A user-authored `shared_skills/` directory is untouched.
6. No file sits directly in `.claude/skills/`, `.opencode/skills/` or `.agents/skills/` after any sync in the test suite.
7. `test_link_target_is_never_pruned_whatever_the_declaration_order` passes in all four cases.
8. Interactive `init` offers exactly `claude_code`, `opencode`, `shared_skills`, `continue`, in that order, with the first three as defaults. A listed `codex` produces the one-line hint.
9. `grep -rn '"shared_skills"' src` matches only the adapter `name` and its docstrings, `DEFAULT_ADAPTERS`, the `codex` hint text and test-facing constants. `grep -n 'shared_skills/' README.md` matches only the migration note.
10. The CI gate is green, cache-free and without optional extras: `ruff check .`, `ruff format --check .` (including the SPEC/README python blocks), `mypy`, `pytest -q`.

## 6. PR 2 — Rules delivered as skill references

Implements D1-D5, D12, D13, D17 and D21. Title (Conventional Commits):
`feat(skills): deliver scoped rules as skill references`. The branch starts from `main` and runs in
parallel with PR 1; PR 3, PR 4 and PR 5-8 branch from `main` after it merges (D19).

PR 2 has two halves that ship in one PR: the engine half (section 6.4: the `skill:` field,
composition, the generated index and "Covers ..." clause, always-only composites, validation,
budget checks) and the catalog half (section 6.5: the four core skills, `skill:` on every scoped
rule, two new member rules, the D17 always text). Section 6.4.2 is the contract between them.

### 6.1 Goal

Today every rule that survives `applies_if` is written in full into always-loaded context:
`AGENTS.md` (`adapters/agents_md_adapter.py:56-69`, `:102-125`) and Claude Code's
`.claude/rules/coding-agent-playbook.md` (`adapters/claude_code_adapter.py:209-226`,
`:300-317`). On the reference probe that is 6,830 words in `AGENTS.md` and 5,330 words in the
Claude rules file (section 1).

After this PR:

1. A scoped rule names the one skill that delivers it, with a new frontmatter key `skill:` (D2).
2. The engine renders each active member rule as `references/<rule-id>.md` inside that skill,
   appends a generated `## References` index to the skill body, and composes the skill's
   description from the authored capability sentence, a generated `Covers ...` clause and an
   authored `Use when ...` clause, kept within 300 characters by construction (D4, D21).
3. A skill with member rules is written only when at least one member passes `applies_if`.
   Skills without member rules (superpowers, python_design, repo-local skills) behave exactly as
   today.
4. `AGENTS.md` and the Claude rules file carry only the always rules plus a generated
   `## Where guidance lives` section. `AGENTS.md` keeps its `## Guardrails` section unchanged
   until PR 4.
5. Core ships `python-coding`, `python-testing`, `python-tooling` and `ml-data`. All 11 scoped
   core rules name one of them; the house-style items that leave always-loaded context move into
   two new `python-coding` members, `python-data-shapes` and `python-idioms`, so nothing is lost.
6. The two always rules are rewritten to the D17 text: 691 rendered words become about 234
   (about 310 with the Where section).
7. CI enforces the D5 context budget and the D13 static checks. SPEC §3 becomes a pointer to
   `CONTEXT.md`, and `CONTEXT.md`, ADR 0001 and this spec are committed (D12, C12).

### 6.2 Scope

**In (engine half):**

- `RuleFrontmatter.skill` and its validation (D2).
- Loading core skills from `catalog/core/skills/` (the loader already walks it; section 6.4.2).
- Membership, gating and composition of skills with member rules (D1, D3, D4), including the
  D21 truncation of the `Covers` clause.
- The `## References` index, the member reference files, the composed description.
- One `SkillWriter` writing identical copies to every native root (D10; PR 1 moves the
  `shared_skills` root to `.agents/skills`, and this PR does not depend on which roots exist).
- Always-only `AGENTS.md` and Claude rules file with the `## Where guidance lives` section (D17).
- Continue unchanged for rules; no degraded prompt for a skill with member rules (D11).
- `agent_harness`: keeps its own layout and records `skill` in its manifest.
- Lockfile provenance for member reference files.
- CI: D5 budget tests on a reference probe built by the test suite; D13 checks on the core
  catalog.

**In (catalog half):**

- `skill:` on the 11 scoped core rules, short topic-label `name`s for the `python-coding`
  members (D21), and new descriptions for four rules (section 6.5.1).
- Two new scoped rules, `python-data-shapes` and `python-idioms` (section 6.5.2).
- New bodies for `project-context` and `python-house-style` (section 6.5.3).
- Four `catalog/core/skills/<id>/SKILL.md` files (section 6.5.5).
- The `catalog/core/ATTRIBUTIONS.md` update (section 6.5.7).
- Docs: SPEC (§3 pointer and the moved facts), `catalog/README.md`, `README.md`, `MIGRATION.md`,
  `CONTEXT.md`, and committing `CONTEXT.md`, ADR 0001 and `specs/prS-skills-context.md`.

**Out:**

- Prompt changes (`includes_rules` meaning, the `## Before you start` block, dropping
  `{{ rule() }}` calls): PR 3. Prompts keep today's inline `## Reference rules` appendix here.
- Guardrail one-liners, the `playbook-guardrails` skill, the lint feedback prefix and the
  `skill-nudge` hook: PR 4.
- Distilled upstream content and the `package_manager` `applies_if` key: PR 5-8.
- Skill roots and making Continue opt-in: PR 1.
- `playbook render <skill-id>` keeps degrading the authored skill to a prompt
  (`commands/render.py:233-235`). Showing the composed `SKILL.md` there is a follow-up; nothing
  in the sync path depends on it.
- The config's `[project] kind` in `project-context`: the detector's `project_kind` stays (D20).
- Splitting files that are already over 500 lines (`orchestrator.py` 585, `commands/sync.py`
  506, `renderer.py` 526, `agent_harness_adapter.py` 515, `commands/import_harness.py` 541,
  `sources/filesystem.py` 550). This PR does not touch `orchestrator.py`, `commands/sync.py`,
  `renderer.py` or `sources/filesystem.py`, and adds one line each to
  `agent_harness_adapter.py` and `commands/import_harness.py` (section 6.4.13).

### 6.3 Decisions taken in this PR

None reopens D1-D23. E-rows belong to the engine half, C-rows to the catalog half.

| # | Decision | Why |
| --- | --- | --- |
| E1 | The capability sentence stays in the standard `description` key. `use_when` and `files` live in one catalog-only mapping, `playbook:`, which the engine strips on output. | Emitted frontmatter stays at standard keys (D10); one reserved key is easy to strip and to grep; a raw-catalog consumer (agent_harness, `Skill.to_prompt`) still finds a valid description. |
| E2 | Composition is data on the `Skill` (`member_references`); the `SkillWriter` derives the emitted frontmatter and body from it. | One rendering for every root, so copies stay byte-identical; adapters that ignore the field (agent_harness, third-party) keep working. |
| E3 | Dispatch still hands every rule to every adapter; `agents_md` and `claude_code` drop member rules themselves. | Continue and agent_harness still need every rule, and out-of-tree adapters keep today's input. |
| E4 | The base `Adapter.write_skill` never degrades a skill with member rules into a prompt. | Its members already reach that adapter as rules; Continue's output stays as today (D11). |
| E5 | `agent_harness` keeps scoped rules at its root `references/` and only records `skill` in its manifest. | Smallest change with a lossless round trip; member files inside its skill dirs would be re-imported as hand-written references. |
| E6 | A skill is gated on member rules exactly when it declares `playbook:`. Gated skills are written only with at least one active member. `skill:` may name only a skill that declares `playbook:` after the layer merge (V14); a skill without the block (superpowers, python_design, `playbook-guardrails`, a plain repo-local skill) never takes members and passes through unchanged. | An overlay that moves every member elsewhere makes the skill disappear instead of shipping an empty index. Without V14, an overlay rule naming a plugin skill would gate that skill on the rule's `applies_if` (it disappears when the gate fails) and compose its 343-637-character authored description with a Covers clause and no `use_when`, which V11 then rejects; D3 says plugin skills have no member rules. |
| E7 | The 300-character limit holds by construction (D21): `compose_description` lists the highest-priority members that fit and ends with `and N more`. `playbook validate` fails (V11) only when the authored parts cannot fit even a one-name Covers clause with the longest tail truncation can emit, and warns (W3) when the full member list would be truncated; both are computed over every member after the layer merge, ignoring `applies_if`. | Deterministic and independent of detector facts, so overlay authors and consumers see the same result. A real composition of `M` active members (`M` at most `N`, the merged count) that falls back to one name emits `Covers <name> and <M-1> more.`, never longer than the `N-1` tail V11 measures, so a skill that passes validate cannot make sync raise. |
| E8 | The `Covers` clause lists member rule `name`s verbatim, ordered by `(priority, id)`. | Deterministic, with no casing rules to maintain; D21 lets content shorten names. |
| E9 | A member reference file's lockfile entry has `kind = "rule"` and the rule's id. | guard-generated-outputs then tells an agent to override the rule, which is the real fix. |
| E10 | `## Where guidance lives` lists skills that have active members and a `playbook.files` phrase, sorted by skill id, rendered by one function shared by both composite files. | The two files carry byte-identical text. |
| E11 | The D13 description lint (third person, a `Use when` clause, at most 300 characters), the 500-line limit and the one-level references check are CI tests over the core skills (`catalog/core/skills/`), not `playbook validate` checks. The D5 listing budgets are CI tests over the reference probe and count every bundled plugin. | The third-person check is a heuristic. Bundled plugin skills fail the lint as written: python_design's two descriptions are 637 and 476 characters, superpowers' `diagnosing-superpowers` is 343, and most superpowers descriptions start with "Use when" (`brainstorming` with "You MUST"); two vendored superpowers skills also exceed 500 lines (section 15, R2-3). Validate would fail every consumer who enables a plugin. Whether the lint should also cover plugins is open question Q1. |
| E12 | When member rules are active but no enabled adapter delivers them, sync prints a warning; there is no fallback that inlines them into `AGENTS.md`. | One delivery path; the default adapter set always delivers them. |
| E13 | The D5 whole-`AGENTS.md` test ships as `xfail(strict=True)` until PR 4; PR 2 asserts the text before `## Guardrails` within 1,500 words on the same hooks-on probe. | The guardrails alone are 1,521 words today; a strict xfail fails PR 4's CI the moment it passes, so PR 4 must remove the marker. |
| E14 | A member rule's id must match the Agent Skills name pattern `^[a-z0-9]+(-[a-z0-9]+)*$` (1-64 characters). | It becomes a file name in every skill root and is the name lint feedback uses. |
| E15 | `playbook.use_when` holds only the condition; it may not start with "Use when". | The engine adds the prefix; a doubled "Use when Use when" is caught at authoring time. |
| E16 | `member_reference_path(rule_id)` in `_member_reference.py` is the one helper that names a reference inside its skill (`references/<rule-id>.md`). | The writer, the lockfile split and PR 3's pointer lines use the same spelling. |
| C1 | Two new rules (`python-data-shapes`, `python-idioms`), not one. | Each has one reason to change, and each gives PR 5's upstream topics a home without moving text twice. |
| C2 | Priorities 44 and 58. | They stay inside Continue's language band, data shapes ranks high in the index, and idioms comes last. |
| C3 | No `lint_codes` on the new rules. | No hook links them, and unlinked codes would be dead data (`tests/unit/test_rules_lint_codes.py:64-75`). |
| C4 | Rewrite four rule descriptions. | The description becomes the reference's line in the generated index, so "critical guidance first" comes from the index. |
| C5 | The nine `python-coding` members get short topic-label names (`Typing`, `Error handling`, ...); other members keep theirs. | D21. With today's names python-coding composes to 301 characters and would truncate from day one; with labels it is 226 in PR 2 and 278 after PR 5, so the Covers clause stays complete. |
| C6 | No critical-guidance block in `SKILL.md` bodies. | It would duplicate references, and the body is never Jinja-rendered, so it could name a reference whose gate failed. |
| C7 | Neither always body names a skill. | Only the generated map routes to skills, and it lists only skills that are actually written. |
| C8 | Short reasons inside four house-style bullets. | The always tier keeps a one-line reason per hard constraint; the cost is about 25 words, well inside 800. |
| C9 | `(project kind: …)` wording; the kind stays the detector's (D20). | It fixes "a `ml-research` project" at no cost. |
| C10 | Bump `version` to 2 on both always rules only. | Only their content changed in a breaking way; adding `skill:` is metadata. |
| C11 | SPEC version 0.21, shared with PR 1 (P1-10). | One version for the skills track avoids churn. |
| C12 | Commit `CONTEXT.md`, ADR 0001 and `specs/prS-skills-context.md` in this PR. | SPEC §3 points at `CONTEXT.md` from this PR on (D12); PRs 3-8 cite sections of this spec, and the existing specs in `specs/` are committed (house style). Only one of the parallel PRs adds each file, so no add/add conflict. |
| C13 | One reference-probe builder (`tests/_budget_probe.py`) and one module-scoped fixture (`tests/integration/conftest.py`), with inline constants, hooks on, both bundled plugins, and an explicit adapter list that includes `continue`. | The budget, content and Continue-regression tests share one probe; no nested `pyproject.toml` or `.ipynb` is committed under `tests/`; the probe does not depend on PR 1's new default. |

### 6.4 Engine design

#### 6.4.1 Data model: `types.py` and the new `_member_reference.py`

Current: `RuleFrontmatter` at `types.py:72-86` (unknown keys fail at `types.py:120`, where
`RuleFrontmatter(**data)` raises `TypeError`); `Rule.to_markdown` drops empty values through
`_without_empty` (`types.py:62-64`, `:122-125`); `Skill` at `types.py:235-296` with an open
`frontmatter: dict[str, Any]`.

Change:

```python
@dataclass
class RuleFrontmatter:
    ...
    lint_codes: dict[str, Any] = field(default_factory=dict)
    # The skill whose references deliver this rule (ADR 0001). Required for a
    # scoped rule, forbidden for an always rule; ``_without_empty`` drops None,
    # so a rule without it keeps byte-identical markdown.
    skill: str | None = None


@dataclass
class Skill:
    frontmatter: dict[str, Any]
    body: str
    scripts_dir: Path | None
    references_dir: Path | None
    source_package: str
    # Set by compose_skills at sync: the active member rules, rendered.
    member_references: tuple[MemberReference, ...] = ()
```

- `__post_init__` needs no coercion: a blank `skill:` parses as `None`, which reads as absent.
- `Skill.to_dict` adds `"member_references": [m.to_dict() for m in self.member_references]`;
  `Skill.from_dict` reads `data.get("member_references", ())`, so a dict written before this PR
  still loads.
- `Hook.to_advisory_rule` (`types.py:467-488`) builds scoped advisory rules with `skill=None`.
  They never pass through validate and `is_skill_member` is false for them, so they keep going
  where they go today (PR 4 changes that path, section 8.4.4).
- `types.py` would grow from 488 to about 498 lines, and PR 4 adds `HookFrontmatter.summary`
  (field, `from_mapping` read, `to_mapping` drop), which would cross 500. So this PR moves
  `HookFrontmatter` (`types.py:305-392`, about 88 lines) into a new leaf
  `src/coding_agent_playbook/_hook_frontmatter.py`, unchanged, and re-exports it from `types`
  (`from coding_agent_playbook._hook_frontmatter import HookFrontmatter as HookFrontmatter`), the
  pattern `types.py:24-34` already uses for the `_hook_schema` names. The class depends only on
  `_hook_schema`, `dataclasses` and `typing` (verified), so the leaf imports nothing from `types`
  and there is no cycle; every importer keeps `from coding_agent_playbook.types import
  HookFrontmatter`. `types.py` ends near 412 lines. `Skill` stays: its `to_prompt` builds a
  `Prompt`, so moving it would create a cycle.

New leaf module `src/coding_agent_playbook/_member_reference.py` (stdlib only, about 70 lines;
`types.py` imports it at run time for `from_dict`, so it cannot live in a module that imports
`types`):

```python
def member_reference_path(rule_id: str) -> str:
    """Where a member rule lives inside its skill directory (E16).

    Example: ``member_reference_path("pytest")`` -> ``"references/pytest.md"``.
    """
    return f"references/{rule_id}.md"


@dataclass(frozen=True)
class MemberReference:
    """One active member rule of a skill, rendered as ``references/<rule_id>.md``.

    ``text`` is the whole file, identical in every skill root.

    Example: ``MemberReference("python-typing", ...).filename`` -> ``"python-typing.md"``.
    """

    rule_id: str
    name: str
    description: str
    priority: int
    globs: tuple[str, ...]
    text: str
    source_package: str

    @property
    def filename(self) -> str:
        """The file name under ``references/``: ``<rule_id>.md``."""
        return f"{self.rule_id}.md"

    def to_dict(self) -> dict[str, Any]:
        """Lossless dict form (``globs`` as a list)."""
        ...

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MemberReference:
        """Inverse of :meth:`to_dict`."""
        ...
```

`globs` feeds the italic first line of the reference (section 6.4.4); `source_package` feeds
lockfile provenance (section 6.4.11). PR 4's skill nudge derives its glob table from the rendered
rules at sync (section 8.5.2), not from this field.

#### 6.4.2 Catalog contract: core skills and the `playbook:` block

Current: the loader already walks a layer's `skills/` directory (`sources/filesystem.py:138-159`
and `:320-325`, resolved for the engine through `_bundled_subdir`, `:105-121`), and the wheel
force-includes the whole `catalog/` tree (`pyproject.toml:120-122`). So
`catalog/core/skills/<dir>/SKILL.md` loads with no loader change. Only `SKILL.md`, `scripts/`
and `references/` are copied (`sources/filesystem.py:151-159`), and skill bodies are never
Jinja-rendered (`commands/_sync_render.py:133-137` passes them through).

Contract for a skill with member rules (section 6.5.5 writes the four core files to it):

```markdown
---
id: python-coding
name: python-coding
description: "Library-agnostic Python conventions."
playbook:
  use_when: "writing, changing or reviewing Python code"
  files: "Any Python file"
---

# Python coding

Library-agnostic conventions for Python code in this repo. ...
```

- `description`: the capability sentence, third person (D13), without "Use when". It stays a
  standard key, so a consumer of the raw catalog still finds a valid description.
- `playbook.use_when` (optional; required for core by a test): the condition only; the engine
  emits `Use when <condition>.` (E15).
- `playbook.files` (optional; required for core by a test): a one-line file-kind phrase of at
  most 80 characters, no trailing period, for the `## Where guidance lives` line. A skill with
  members but no `files` is left out of that section (validate warns, W2).
- The body must not contain a line that is exactly `## References` (the engine appends that
  section) and must not link to `references/<rule-id>.md`: those files exist only in the output,
  so the in-layer link check (`commands/_validate_links.py`) would reject the link. The index
  links them.
- Hand-written files in the skill's own `references/` stay allowed (D3), but none may be named
  `<member-rule-id>.md` (validate error V12).
- Core requirements enforced by tests only (E11): `use_when` and `files` present, the
  description lint, at most 500 lines after composition, references one level deep, the full
  member list fits without truncation on the reference probe.
- `catalog/core/` is not in ruff's `extend-exclude` (`pyproject.toml:142-147`), so fenced Python
  in a core `SKILL.md`, a hand-written reference or a rule body must be `ruff format` clean at 100
  columns.

A scoped rule names its skill:

```yaml
id: python-typing
name: Typing
description: "Prefer a concrete type or a Protocol to Any, write X | None, and take abstract read-only types as inputs."
scope: scoped
skill: python-coding
globs: ["**/*.py"]
applies_if:
  python_version: ">=3.11"
priority: 50
```

#### 6.4.3 Membership and gating: new `skill_membership.py`; `commands/_sync_render.py`

Current: `render_artifacts` filters rules by `applies_if` once (`_sync_render.py:152-153`),
renders their bodies (`:159`) and returns `skills=filter_skills(ctx.skills_resolved)`
(`:167`), where `filter_skills` (`:133-137`) returns every skill unchanged.

New module `src/coding_agent_playbook/skill_membership.py` (about 150 lines):

```python
def is_skill_member(rule: Rule) -> bool:
    """Whether ``rule`` is delivered through a skill (its frontmatter names one).

    Example: ``is_skill_member(typing_rule)`` -> ``True`` for ``skill: python-coding``.
    """
    return rule.frontmatter.skill is not None


def member_rules_of(skill_id: str, rules: Sequence[Rule]) -> list[Rule]:
    """The rules whose ``skill`` is ``skill_id``, sorted by ``(priority, id)``."""
    ...


def is_rule_skill(skill: Skill) -> bool:
    """Whether ``skill`` is gated on member rules: it declares a ``playbook`` block (E6)."""
    ...


def compose_skills(
    skills: Sequence[Skill], merged_rules: Sequence[Rule], active_rules: Sequence[Rule]
) -> list[Skill]:
    """The skills to write, each with its active member rules attached.

    A skill without a ``playbook`` block passes through unchanged (V14 keeps
    rules from naming it). A skill with the block is dropped when none of its
    members survived ``applies_if``; otherwise it gets one
    :class:`MemberReference` per active member, built from the Jinja-rendered
    rule. Example::

        skills = compose_skills(ctx.skills_resolved, ctx.rules_resolved, rendered_rules)
    """
    ...


def member_reference(rule: Rule) -> MemberReference:
    """``rule`` (body already rendered) as the reference its skill writes."""
    ...


def undelivered_member_warning(adapters: Iterable[Adapter], skills: Sequence[Skill]) -> str | None:
    """A ``warning:`` line when member rules are active but no enabled adapter delivers them."""
    ...
```

- `compose_skills` never mutates its inputs: it returns `dataclasses.replace(skill,
  member_references=...)` for a composed skill and the same object for a plain one.
- `merged_rules` is `ctx.rules_resolved` (after the layer merge, before `applies_if`);
  `active_rules` is the rendered, filtered list. So membership is decided on every layer, a
  skill without a `playbook:` block is never gated or composed (section 6.3, E6), and
  the reference text is the rule body rendered exactly as rules are rendered today: same
  sandboxed environment, same context (`build_jinja_context`, `_sync_render.py:64-75`), and a
  sandbox violation still aborts the sync before any write, naming the rule's file.
- `member_reference` calls `skill_document.render_member_reference` (section 6.4.4) for `text`.
- `undelivered_member_warning` returns, when any skill has `member_references` and no adapter
  has `delivers_member_rules = True` (section 6.4.10):
  `warning: no enabled adapter delivers scoped rules (only agents_md is on); skills python-coding, python-testing reach no assistant: add claude_code, opencode or shared_skills to adapters_enabled`.

`_sync_render.py` change: delete `filter_skills` and build the skills with
`compose_skills(ctx.skills_resolved, ctx.rules_resolved, rendered_rules)`; print the warning to
stderr when there is one (`ctx.adapters` is already populated by `SyncContext.from_config`,
`orchestrator.py:537`). The `RenderedArtifacts` docstring (`:43-55`) gains one line about
composed skills. `RenderedArtifacts.rules` still holds every active rule. PR 3 and PR 4 call
`compose_skills` wherever their designs mentioned `filter_skills` (section 14, H10).

#### 6.4.4 Skill document text: new `skill_document.py`

One module renders every string the composition adds, so the three skill roots and the two
composite files cannot drift (about 250 lines):

```python
DESCRIPTION_MAX_CHARS: Final = 300


def skill_catalog_block(skill: Skill) -> SkillCatalogBlock:
    """The ``playbook`` block of ``skill``; absent or malformed keys read as ``None``."""
    ...


def covers_clause(member_names: Sequence[str], shown: int) -> str:
    """``Covers <a>, <b>.`` naming the first ``shown`` names; ``and N more`` for the rest (D21).

    Example: ``covers_clause(["Typing", "Docstrings", "Idioms"], 1)`` ->
    ``"Covers Typing and 2 more."``
    """
    ...


def compose_description(description: str, member_names: Sequence[str], use_when: str | None) -> str:
    """The emitted description: capability sentence, Covers clause, then ``Use when ...``.

    Lists every member when the result fits ``DESCRIPTION_MAX_CHARS``; otherwise
    the most members that fit, in the order given (highest priority first),
    then ``and N more``. Raises :class:`DescriptionOverflowError` (a
    ``ValueError`` carrying the text and its length) when even one name does
    not fit, which validate's V11 rules out before any sync writes.

    Example::

        compose_description("Python conventions.", ["Docstrings"], "editing a module")
        # 'Python conventions. Covers Docstrings. Use when editing a module.'
    """
    ...


def emitted_frontmatter(skill: Skill) -> dict[str, Any]:
    """Authored frontmatter minus ``playbook``; ``description`` composed when members exist."""
    ...


def emitted_body(skill: Skill) -> str:
    """Authored body, plus the ``## References`` index when members exist."""
    ...


def references_index(members: Sequence[MemberReference]) -> str:
    """The ``## References`` section: one line per member, in the order given."""
    ...


def render_member_reference(rule_id: str, globs: Sequence[str], body: str) -> str:
    """The text of ``references/<rule_id>.md``: one italic rule line, a blank line, the body."""
    ...


def where_entry(skill: Skill) -> WhereEntry | None:
    """``(skill id, playbook.files)`` for a skill with members and a ``files`` phrase, else None."""
    ...


def where_guidance_section(entries: Sequence[WhereEntry]) -> str:
    """The ``## Where guidance lives`` section, sorted by skill id; ``""`` without entries."""
    ...
```

`SkillCatalogBlock` is a frozen dataclass `(use_when: str | None, files: str | None)`;
`WhereEntry` is a frozen dataclass `(skill_id: str, files: str)`.

Composition rules:

- `compose_description` makes each part a sentence (appends `.` unless it already ends with
  `.`, `!` or `?`), strips a trailing `.` from each member name, and joins
  `<description> Covers <a>, <b>. Use when <use_when>.` with single spaces. Without `use_when`
  it ends after the Covers clause. A skill without members keeps its authored description
  untouched (`emitted_frontmatter` returns the authored mapping minus `playbook`, so a plugin
  skill's `SKILL.md` is byte-identical to today's).
- Truncation (D21): `compose_description` tries `shown = len(member_names)` first and counts
  down to 1, returning the first text of at most 300 characters. The truncated clause is
  `Covers <a>, <b> and <N> more.`; the listed members are the first `shown` in `(priority, id)`
  order, so the highest-priority active members are always named.
- The V11 bound (section 6.6) is the longest text this fallback can emit: over every member name
  after the merge, the longest `<description> Covers <name> and <N-1> more. Use when
  <use_when>.`, where `N` is the merged member count and the ` and <N-1> more` tail is absent
  when `N == 1`. A one-name fallback over `M <= N` active members ends with `and <M-1> more`,
  which is never longer, so validate's bound is also sync's. `worst_case_description` (below)
  computes that text once, for V11 and for the regression test.

```python
def worst_case_description(
    description: str, member_names: Sequence[str], use_when: str | None
) -> str:
    """The longest text a one-name Covers fallback can emit, tail included (V11, E7).

    Example: ``worst_case_description("X.", ["Typing", "Error handling"], None)`` ->
    ``"X. Covers Error handling and 1 more."``
    """
    ...
```
- Member order everywhere (Covers clause, index, reference writing) is `(priority, id)`.

Rendered examples, from a prototype of these functions over the section 6.5 frontmatter (lengths
exact):

```text
python-coding (226 chars, every member listed):
Library-agnostic Python conventions. Covers Dependency injection, Pure core, Data shapes, Typing,
Error handling, Context managers, Docstrings, Timeouts and retries, Idioms. Use when writing,
changing or reviewing Python code.

python-testing (145 chars):
Test conventions for this repo's pytest suite. Covers pytest conventions. Use when writing,
changing or reviewing tests, fixtures or conftest.py.

Truncation, for an overlay that lengthens both authored parts of python-coding (295 chars):
Library-agnostic Python conventions for code in this repo, whatever library it uses. Covers
Dependency injection, Pure core, Data shapes, Typing, Error handling, Context managers and 3 more.
Use when writing, changing, refactoring or reviewing any Python module, script or notebook in
this repo.
```

The four core descriptions total 762 characters (D5 core limit: 2,000; section 6.5.6).

Emitted `.claude/skills/python-coding/SKILL.md` (identical under `.opencode/skills/` and the
shared root; `name` first because `render_skill_md` forces it, then the remaining authored keys
in authored order, `playbook` removed):

```markdown
---
name: python-coding
id: python-coding
description: Library-agnostic Python conventions. Covers Dependency injection, Pure core, Data
  shapes, Typing, Error handling, Context managers, Docstrings, Timeouts and retries, Idioms. Use
  when writing, changing or reviewing Python code.
---
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->

# Python coding

Library-agnostic conventions for Python code in this repo. ...

## Picking references

...

## References

Each reference is one rule. Open only the ones the current task needs.

- [python-dependency-injection](references/python-dependency-injection.md) — Dependency injection: Pass I/O collaborators in as parameters; pick concrete implementations in one composition root per entry point.
- [python-pure-core](references/python-pure-core.md) — Pure core: Keep business logic free of I/O, clocks, randomness and hidden mutation; perform effects in a thin outer shell.
- [python-data-shapes](references/python-data-shapes.md) — Data shapes: Model records as dataclasses, not string dicts or parallel lists; freeze them with tuple fields; return at most three values; name magic constants.
- [python-typing](references/python-typing.md) — Typing: Prefer a concrete type or a Protocol to Any, write X | None, and take abstract read-only types as inputs.
- (one line per remaining active member)
```

Each index line is `- [<rule-id>](references/<rule-id>.md) — <name>: <description>`. The link
text is the rule id because lint feedback names rule ids (D16), so an agent finds the line by
the id it was given. The links are generated into the output and point at files written next to
them, so the in-layer link check (which reads authored sources) never sees them.

Emitted `references/python-typing.md` (the rule body after Jinja, unchanged, behind one line):

```markdown
*Rule `python-typing`; applies to `**/*.py`.*

# Python typing conventions

Type hints aren't decoration — they're the cheapest documentation you can ship. ...
```

A member without globs gets the line ``*Rule `<id>`.*``. The globs line is advisory, as the
`*Applies to: ...*` line of today's sections is (`renderer.py:321-341`). Reference files carry
no sentinel: like copied references, they are owned through the lockfile (SPEC §4.2 step 9).

The `## Where guidance lives` section for the reference probe (78 words; phrases from section
6.5.6):

```markdown
## Where guidance lives

Detailed conventions live in skills. Before you edit one of these files, load its skill and open the references its index lists.

- Code that loads or saves models, checkpoints or caches: skill `ml-data`
- Any Python file: skill `python-coding`
- Test files and conftest.py: skill `python-testing`
- FastAPI apps, routers, dependency providers and error handlers: skill `python-tooling`

Lint feedback names a rule id; that rule's reference in the skill has the fix.

---
```

It ends with the same `---` separator as a rule section (`renderer.py:337-341`), so it stacks
like one.

#### 6.4.5 The shared `SkillWriter`: `adapters/_skill_writer.py`, new `adapters/_agent_skill_rules.py`

Current: `render_skill_md` (`_skill_writer.py:197-209`) emits
`{"name": id, **authored frontmatter}` and the authored body; `_write_skill_files`
(`:403-415`) writes `SKILL.md`, then copies `scripts/` and `references/`. The file is 507 lines.

Changes:

1. Move the Agent Skills naming rules out to `adapters/_agent_skill_rules.py` (about 110 lines):
   the constants (`:62-74`), `skill_id_of` and `has_declared_id` (`:103-119`), and
   `agent_skill_issues` with its helpers (`:147-194`). `_skill_writer.py` re-exports them
   (`from ... import agent_skill_issues as agent_skill_issues`), so `commands/validate.py:53-58`
   and `tests/adapters/test_skill_writer.py:19-24` keep their imports.
2. `render_skill_md` builds its frontmatter from `skill_document.emitted_frontmatter(skill)` and
   its body from `skill_document.emitted_body(skill)`. The id check before any I/O stays first.
3. `_write_skill_files` writes the member references after the copied subtrees:

```python
def _write_member_references(skill: Skill, skill_dir: Path, prior: PriorOutput) -> list[Path]:
    """Write ``references/<rule-id>.md`` for every member, as UTF-8 LF bytes.

    The same ``_prepare_destination`` guard as copied files: inside this
    engine-owned skill dir a regular file at the destination is replaced, as a
    copied reference is today; a real directory there, or a file where a parent
    directory must go, that holds files the previous lockfile does not list is
    kept with a warning and the reference is skipped. V12 rules out a
    hand-written reference with a member's name. Example::

        written = _write_member_references(skill, repo / ".claude/skills/python-coding", prior)
    """
    written: list[Path] = []
    for member in skill.member_references:
        destination = skill_dir / member_reference_path(member.rule_id)
        if _prepare_destination(destination, skill_dir, prior):
            destination.write_bytes(member.text.encode("utf-8"))
            written.append(destination)
    return written
```

The bytes come from `MemberReference.text`, computed once per sync, so every root gets the same
file. Ownership, case-only renames, check-mode ownership (`deciding_ownership_against`) and the
leftover policy apply unchanged. The file ends near 470 lines.

#### 6.4.6 Always-only composites: `agents_md_adapter.py`, `claude_code_adapter.py`

`AgentsMdAdapter`:

- `write_rule` (`:56-69`): return `[]` when `is_skill_member(rule)`. Always rules are buffered
  as today. (Hook advisories never reach this method; `write_hook`, `:71-81`, buffers them.)
- `write_skill` (`:92-100`): still writes nothing, but buffers `where_entry(skill)` when it is
  not `None`.
- `finalize` (`:102-125`): writes the file when any always rule, Where entry or hook advisory
  exists; content is title, always sections sorted by `(priority, id)`, then
  `where_guidance_section(...)`, then the Guardrails section (`:127-130`, unchanged until PR 4).
- New class attribute `delivers_member_rules: ClassVar[bool] = False` (section 6.4.10).

`ClaudeCodeAdapter`:

- `write_rule` (`:209-226`): return `[]` when `is_skill_member(rule)`. Advisory sections of
  hooks Claude Code cannot enforce still arrive here (`:177-188`) with `skill=None` and are kept
  in full until PR 4 turns them into one line each (section 8.4.4).
- `write_skill` (`:248-257`): buffers `where_entry(skill)`, then delegates to the `SkillWriter`
  as today.
- `_rules_body` (`:300-317`): sections, then the Where section, then the heartbeat line; returns
  `None` only when all three are empty. `.claude/CLAUDE.md` stays the four-line stub
  (`claude_rule_paths.py:26-34`).

Resulting `AGENTS.md` shape (the Claude rules file is the same without Guardrails, with its own
title and the heartbeat line last):

```markdown
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->
# AGENTS.md

This file is generated by coding-agent-playbook.

## Project context
...
---

## Python house style
...
---

## Where guidance lives
...
---

## Guardrails
...
```

The Where section of both files comes from the same call, so it is byte-identical in them.

#### 6.4.7 Continue: no change for rules; `adapters/base.py` for skills

Current: Continue writes one file per rule (`continue_adapter.py:55-70`) and inherits
`Adapter.write_skill` (`base.py:76-84`), which degrades every skill to a prompt. Unchanged
engine code would write `.continue/prompts/{ml-data,python-coding,python-testing,python-tooling}.md`
on the probe (measured by the catalog designer), which D11 forbids.

Change, in `base.py` `write_skill` rather than in Continue (E4): return `[]` when
`skill.member_references` is non-empty, else degrade as today. Continue keeps writing every
member rule as `.continue/rules/{priority:02d}-{id}.md` with `alwaysApply: false` and its globs
(`renderer.py:298-318`); `RuleFrontmatter.skill` is not projected into that frontmatter, so
those files are byte-identical to today's for the same rule text (D11; the catalog half changes
some rule texts and names, section 6.7). A degraded prompt would add a `/python-coding` command
whose index links to files Continue never receives. The same reasoning holds for any
out-of-tree adapter that keeps the default `write_skill`.

#### 6.4.8 OpenCode and shared skills

No logic change. `OpenCodeAdapter.write_rule` stays a no-op (`opencode_adapter.py:105-114`):
always rules arrive through `AGENTS.md`, member rules through `.opencode/skills/<id>/references/`
written by its `SkillWriter` (`:84`). `SharedSkillsAdapter` (`shared_skills_adapter.py:49-69`)
writes the same bytes to its root (PR 1 moves that root to `.agents/skills`). Both module
docstrings drop the claim that rules reach every assistant through `AGENTS.md`.

#### 6.4.9 `agent_harness`, its manifest and `import-harness`

Current: the adapter buffers everything (`agent_harness_adapter.py:107-131`), writes always
rules to `rules/`, scoped rules to its root `references/<id>.md` with a manifest entry
(`:305-383`), and skills to `skills/<id>/` with authored `name`/`description`, the authored
body and copied references (`:164-225`); extra skill frontmatter goes to the manifest
(`:221-225`).

Change (E5):

- `_write_rule_content` passes `skill=fm.skill` into the manifest entry.
- `harness/manifest.py`: `ManifestEntry` gains `skill: str | None = None` (rule-only).
  `_entry_to_table` (`:143-163`) emits it only when set, like `lint_codes`, so existing
  manifests stay byte-identical; `_entry_from_table` (`:166-193`) reads `table.get("skill")`.
- `commands/import_harness.py`: `_rule_from_entry` (`:146-176`) passes `skill=entry.skill`.
  The best-effort warning for a rule found under `references/` (`:398-401`) gains
  `; a scoped rule needs 'skill: <skill-id>' before playbook sync accepts it`.
- The adapter ignores `member_references`: its skill leaf keeps the authored description and
  body, and the `playbook` block reaches the manifest through `_skill_extra_frontmatter`, so a
  lossless import restores it. A skill whose members are all inactive is not dispatched, so it
  is absent from the harness, just as an inactive rule is.

#### 6.4.10 Adapter capability: `delivers_member_rules`

`Adapter` (`base.py:32-62`) gains, next to `output_locations`:

```python
class Adapter(ABC):
    #: Whether this adapter's harness receives scoped rules: through its own rule
    #: files (continue, agent_harness) or through skill references (claude_code,
    #: opencode, shared_skills). Only ``agents_md`` sets False: it carries always
    #: rules only. ``playbook sync`` warns when every enabled adapter sets False.
    delivers_member_rules: ClassVar[bool] = True
```

The default is `True` because an out-of-tree adapter still receives every rule through
`write_rule`. PR 1 adds `retired_output_locations` to the same ABC; the two attributes are
independent.

#### 6.4.11 Lockfile provenance: `commands/_sync_lockfile.py`

Current: `_write_artifacts` records every path `write_skill` returns with one
`Provenance(kind="skill", artifact_id=<skill id>)` (`:188-208`, `:104-112`).

Change: split the paths of one `write_skill` call:

```python
def _skill_write_provenance(
    paths: Sequence[Path], skill: Skill, adapter_name: str
) -> list[tuple[list[Path], Provenance]]:
    """Split ``write_skill``'s paths: member references carry their rule's provenance."""
    ...
```

A path whose name is `<rule-id>.md`, whose parent is `references` and whose grandparent is
named after the skill id, for a rule in `skill.member_references`, is recorded as
`Provenance(kind="rule", artifact_id=<rule-id>, source=<member.source_package>,
adapter=<adapter>)`; everything else keeps the skill provenance. Validation (V12) guarantees no
hand-written file has a member's name. Effects: `guard-generated-outputs` tells an agent that
edits `.claude/skills/python-coding/references/python-typing.md` to add a same-id override
under `playbook/rules/` (`hook_runtime/handlers/guard_generated_outputs.py:134-147`), and the
member rule ids join the lockfile's artifact id set, which
`resync-on-detector-input-change` treats as already rendered
(`hook_runtime/handlers/resync_on_detector_input_change.py:175-180`). Schema stays 2.

#### 6.4.12 `playbook validate`: new `commands/_validate_skills.py`

Current: `collect_validation_findings` (`commands/validate.py:337-357`) joins
`_artifact_errors` (`:390-413`, which already runs `_check_agent_skills`, `:289-303`) and the
hook checks; `playbook sync` runs the same set first and writes nothing on an error
(`sync_gate_errors`, `:373-387`). `validate.py` is 440 lines, so the new checks go in a new
module (about 280 lines):

```python
#: V1's message; MIGRATION.md quotes it and a docs test imports it.
SCOPED_RULE_NEEDS_SKILL_MESSAGE: Final = (
    "scope 'scoped' needs 'skill: <skill-id>' naming the skill whose references deliver "
    "this rule; known skills: {known}"
)


def check_skill_membership(
    resolved_rules: Sequence[Rule], all_rules: Sequence[Rule], skills: Sequence[Skill]
) -> list[ValidationError]:
    """One error per rule whose ``skill`` breaks D2 (required/forbidden/exists/shape) or V14."""
    ...


def check_rule_skills(
    resolved_rules: Sequence[Rule], skills: Sequence[Skill]
) -> ValidationFindings:
    """Errors and warnings for skills with member rules (block, collisions, description fit)."""
    ...
```

`resolved_rules` and `skills` are the merged sets (`ctx.rules_resolved`,
`ctx.skills_resolved`); `all_rules` is `ctx.artifact_source.list_rules()` (every layer), used
only to suggest the skill of a rule an override replaced. `collect_validation_findings` adds the
errors to its error list and the warnings to its warning list (about 6 new lines). Section 6.6
lists every message.

#### 6.4.13 Module budget

| Module | Today | After | Note |
| --- | --- | --- | --- |
| `_member_reference.py` | new | ~70 | stdlib-only leaf, with `member_reference_path` |
| `skill_membership.py` | new | ~150 | gating and composition |
| `skill_document.py` | new | ~250 | every generated string, D21 truncation |
| `commands/_validate_skills.py` | new | ~280 | section 6.6 |
| `adapters/_agent_skill_rules.py` | new | ~110 | moved from `_skill_writer.py` |
| `tests/_budget_probe.py` | new | ~95 | shared by PR 4-8, with `render_core_rule` |
| `_hook_frontmatter.py` | new | ~95 | `HookFrontmatter` moved unchanged (section 6.4.1) |
| `types.py` | 488 | ~412 | `skill` and `member_references` added, `HookFrontmatter` moved out; leaves room for PR 4's `summary` |
| `adapters/_skill_writer.py` | 507 | ~470 | net shrink |
| `commands/validate.py` | 440 | ~450 | |
| `adapters/claude_code_adapter.py` | 374 | ~392 | |
| `adapters/base.py` | 272 | ~285 | |
| `commands/_sync_lockfile.py` | 285 | ~310 | |
| `commands/_sync_render.py` | 233 | ~240 | |
| `adapters/agents_md_adapter.py` | 146 | ~170 | |
| `harness/manifest.py` | 260 | ~266 | |
| `adapters/agent_harness_adapter.py` | 515 | 516 | pre-existing overrun, one line added |
| `commands/import_harness.py` | 541 | 542 | pre-existing overrun, one line added |

### 6.5 Catalog content

Everything measured here comes from the reference probe synced with today's engine, with the new
texts placed in `playbook/rules/` and `playbook/skills/` as repo-local overrides. `playbook
validate` passed (`OK 65 artifacts validated`), and `ruff format --check --line-length 100`
passed on every new markdown file.

#### 6.5.1 `skill:`, names and descriptions of the 11 existing scoped rules

Each file gets one line, `skill: <id>`, right after `scope: scoped` (line 6 of every file
listed). The seven `python-coding` members also get a short topic-label `name` (C5, D21): the
name is the member's label in the Covers clause and in the index, so it does not repeat the
skill's subject. The four descriptions marked below are rewritten as one actionable line each,
because the description becomes the reference's line in the generated index. Bodies, globs,
gates, priorities and lint codes do not change, and neither does `version`.

| Rule id (file) | `skill:` | `name` | Description change |
| --- | --- | --- | --- |
| `python-dependency-injection` (`languages/python/dependency-injection.md`) | `python-coding` | `Python dependency injection` -> `Dependency injection` | none |
| `python-pure-core` (`languages/python/pure-core.md`) | `python-coding` | `Python pure core` -> `Pure core` | none |
| `python-typing` (`languages/python/typing.md.j2`, description at line 4) | `python-coding` | `Python typing conventions` -> `Typing` | `Prefer a concrete type or a Protocol to Any, write X \| None, and take abstract read-only types as inputs.` (105 characters; it no longer opens with "annotate every signature", which always bullet 1 owns) |
| `python-error-handling` (`languages/python/error-handling.md`, line 4) | `python-coding` | `Python error handling` -> `Error handling` | `Catch only what you can handle, never swallow an exception, chain with raise ... from, and translate errors once at the boundary.` (129) |
| `python-context-managers` (`languages/python/context-managers.md`) | `python-coding` | `Python context managers` -> `Context managers` | none |
| `python-docstrings` (`languages/python/docstrings.md`) | `python-coding` | `Python docstrings` -> `Docstrings` | none |
| `python-retries-and-timeouts` (`languages/python/retries-and-timeouts.md`) | `python-coding` | `Python timeouts and retries` -> `Timeouts and retries` | none |
| `pytest` (`frameworks/pytest.md.j2`, line 4) | `python-testing` | unchanged (`pytest conventions`) | `Mirror the source layout, test one behaviour per test, parametrize case tables, keep fixtures narrow and assert literal expected values.` (136) |
| `fastapi-app-wiring` (`frameworks/fastapi-app-wiring.md`, line 4) | `python-tooling` | unchanged | `Build collaborators in Depends providers and lifespan resources, use async def only for async I/O, and override dependencies in tests.` (134) |
| `fastapi-error-boundaries` (`frameworks/fastapi-error-boundaries.md`) | `python-tooling` | unchanged | none |
| `ml-serialization-security` (`ml/serialization-security.md.j2`) | `ml-data` | unchanged (pinned by `tests/evals/test_prompting.py:76` and `:257`) | none |
| `python-data-shapes` (new, section 6.5.2) | `python-coding` | `Data shapes` | new |
| `python-idioms` (new, section 6.5.2) | `python-coding` | `Idioms` | new |

`project-context` and `python-house-style` have scope `always`, so they get no `skill:` (D2
forbids it there).

Example, after the change (`catalog/core/rules/languages/python/typing.md.j2:1-19`):

```yaml
---
id: python-typing
name: Typing
description: "Prefer a concrete type or a Protocol to Any, write X | None, and take abstract read-only types as inputs."
version: 1
scope: scoped
skill: python-coding
globs:
  - "**/*.py"
applies_if:
  python_version: ">=3.11"
priority: 50
tags: [python, typing]
lint_codes:
  warn: [ANN001, ANN201, ANN401, B006, PGH003, UP007, UP045]
  when:
    - applies_if: {python_version: ">=3.12"}
      warn: [UP040, UP046, UP047]
---
```

Who sees the names: the Covers clause and the index of each skill; Continue's rule files
(`name:` frontmatter, Continue being opt-in, D21); and the `### <name>` headings of the inline
`## Reference rules` appendix that Continue prompts and the eval runner receive. Rule bodies keep
their own `#` titles (`# Python typing conventions`), so a reference still opens with its full
title. The eval prompt headings change wording only (`### Error handling`); section 6.8.15 lists
the tests that pin them.

**Who sees which skill.** `python-coding` has nine members, seven of them ungated, so it is
written in every consumer repo, and in every synthetic repo the test suite syncs
(`make_synthetic_repo` uses the real engine catalog; section 6.8.15 lists the tests this breaks). `python-testing` is written only when pytest is detected.
`python-tooling` is written only with FastAPI (until PR 7 adds an ungated member).
`ml-data` is written only when the ML stack includes torch, tensorflow, jax, transformers,
scikit-learn, xgboost or lightgbm (until PR 8 adds numpy, pandas and polars members). In the
reference probe all four skills and all 13 member rules are active.

#### 6.5.2 The two new scoped rules of `python-coding`

The house-style items that leave always-loaded context (section 6.5.4) are split by reason to
change. Records, immutability, return shapes and constants go to `python-data-shapes`. Paths,
function and class shape, strings, imports and small idioms go to `python-idioms`. PR 5 later
moves the class-design bullets of `python-idioms` into `python-classes-and-protocols` and adds
`slots=True` advice to `python-data-shapes` (section 9.8), so each topic keeps a single owner.

Priorities 44 and 58 fall in the language band (40 to 59) of Continue's file numbering. They also
place data shapes right after pure core in the index, and idioms last, as the least critical
topic. Neither rule gets `lint_codes` (C3).

`catalog/core/rules/languages/python/data-shapes.md` (new; 255 words in the body):

````markdown
---
id: python-data-shapes
name: Data shapes
description: "Model records as dataclasses, not string dicts or parallel lists; freeze them with tuple fields; return at most three values; name magic constants."
version: 1
scope: scoped
skill: python-coding
globs:
  - "**/*.py"
priority: 44
tags: [python, design, data]
---

# Python data shapes

A value with a name and a type tells the next reader what it holds and lets the type checker catch a typo; a dict of strings, or two lists kept in step, does neither. The house style already requires typed records between layers. This reference covers how to shape them.

## Records

- Don't use a dict of strings as a stand-in for a record type. When three or more fields belong together, give them a dataclass.
- Never keep parallel lists indexed together (`names[i]` beside `prices[i]`); zip them into one list of records.
- Return at most three values as a tuple. Beyond that, return a dataclass or a `NamedTuple`, so callers read fields by name.
- Compute derived values with `@property` instead of storing a copy that can go stale.

## Frozen is shallow

`frozen=True` only blocks attribute assignment: a `list` field can still change in place. Give a frozen dataclass `tuple` and `frozenset` fields, and copy every collection passed in, including from a builder into the object it builds.

```python
@dataclass(frozen=True)
class Basket:
    items: tuple[Item, ...]

    @property
    def total_cents(self) -> int:
        return sum(item.price_cents for item in self.items)


basket = Basket(items=tuple(draft_items))  # a copy: later edits to draft_items cannot leak in
```

## Constants and settings

- Name domain magic values as `UPPER_CASE` module constants annotated `Final`, beside the code that uses them: `MAX_LINE_ITEMS: Final = 50`.
- Values that change per environment (URLs, credentials, feature flags, deployment-tuned timeouts) live in the single settings object, never in constants.
````

`catalog/core/rules/languages/python/idioms.md` (new; about 295 words in the body). It restates
nothing the always tier owns: `Path` and the explicit encoding belong to always bullet 2, and the
"report what is outside the task" reminder to `project-context`; a content gate pins that
(section 6.8.13):

````markdown
---
id: python-idioms
name: Idioms
description: "Keep os.path for legacy str APIs, use f-strings, group imports, split flag-driven functions, prefer composition, and avoid star imports and shadowed builtins."
version: 1
scope: scoped
skill: python-coding
globs:
  - "**/*.py"
priority: 58
tags: [python, style]
---

# Python idioms

Small conventions that keep Python files uniform. Follow them in new code. When you edit an existing file that does something differently, match the file so it stays consistent.

## Paths and files

The always-loaded house style owns `Path` and the explicit encoding; this section adds only the exception and the call to use.

- `os.path` is acceptable only where a legacy standard-library call needs a `str`.
- Read or write a whole text file with `Path.read_text` and `Path.write_text`, not `open(...).read()`, which leaves the file handle open.

```python
def count_lines(path: Path) -> int:  # good
    return len(path.read_text(encoding="utf-8").splitlines())


def count_lines_legacy(path):  # avoid: no type hints, no encoding, no Path, leaked file handle
    return len(open(path).read().splitlines())
```

## Functions and classes

- When a boolean flag selects a different algorithm, split the function in two instead of branching on the flag.
- Prefer composition over inheritance. Subclass only when the relationship is genuinely substitutable.
- Framework base classes (`BaseModel`, `BaseSettings`, `DeclarativeBase`, Django views), exception hierarchies and documented ABC extension points are normal subclassing; the house-style rule to wrap rather than subclass does not apply to them.

## Strings

- Use f-strings (`f"hello, {name}"`), not `%`-formatting or `.format()`.
- Use double quotes, and single quotes only when the string contains a double quote. Where Ruff or Black is configured, let the formatter decide.

## Imports

Group imports in this order, with a blank line between groups: standard library, third-party, then first-party (this repo's packages). Never write `from module import *`; name what you use.

```python
import json  # standard library
from pathlib import Path

import httpx  # third-party

from myapp.orders import place_order  # first-party
```

## Small things reviewers flag

- Don't shadow builtins (`list`, `dict`, `id`, `type`, `vars`) with local names.
- Prefer an early `return` over deeply nested `if`/`else`.
````

Both files live under `catalog/core/rules/`, which ruff does not exclude, so `ruff format --check
.` formats their python blocks; both blocks are already formatted.

#### 6.5.3 The always text (D17)

`catalog/core/rules/always/00-project-context.md.j2`, full replacement of today's lines 1-25. The
body is 69 words in the source; the rendered section in the probe is 63 words, down from 146:

````markdown
---
id: project-context
name: Project context
description: Project name, kind and description, plus the two working agreements every task needs.
version: 2
scope: always
priority: 0
tags: [always, context]
---

You are working on **{{ project_name }}** (project kind: `{{ project_kind }}`).
{% if project_description %}

{{ project_description }}
{% endif %}

- Ask before writing code when the scope or the approach is unclear: a short question costs less than the wrong change.
- Report a problem you find outside the task (a latent bug, dead code, a missing test) instead of fixing it in the same change.
````

`catalog/core/rules/always/10-python-house-style.md`, full replacement of today's lines 1-85. The
body is about 166 words in the source; the rendered section in the probe is about 171 words, down
from 545:

````markdown
---
id: python-house-style
name: Python house style
description: The eight Python conventions that hold in every file, new or edited.
version: 2
scope: always
priority: 10
tags: [always, python, style]
---

- Type-hint every function signature, private helpers included.
- Use `pathlib.Path` for paths, and pass `encoding="utf-8"` whenever you open, read or write text: the platform default differs between machines.
- Pass typed records between layers: a frozen dataclass, Pydantic only at I/O boundaries, never `dict[str, Any]`.
- Never use a mutable default argument; every call shares the one object, so default to `None` (`field(default_factory=...)` in a dataclass). Make boolean flags keyword-only (`*, dry_run: bool = False`). Use an `Enum` or `Literal` for a closed set of options.
- Money is never `float`, which cannot hold most cent values exactly: use `Decimal` or integer minor units (cents).
- Never write a bare `# noqa` or `# type: ignore`, which silences every code: name the code (`# noqa: E501`, `# type: ignore[arg-type]`) and add a comment saying why.
- Wrap a third-party class instead of subclassing it to change its interface (framework base classes excepted).
- Follow the repo's existing layout axis (layer-first or feature-first); never mix the two.
````

Design notes:

- **No `#` title in either body.** The adapters already emit `## Project context` and `## Python
  house style` (`renderer.py:321-341`). Today's bodies repeat a title under a lower-level
  heading (`# About this project`, `# Python house style`).
- **`(project kind: …)` instead of `a \`…\` project`.** This avoids "a `ml-research` project",
  which the probe rendered. The kind itself is still the detector's `project_kind`
  (`detector.py:292`), not the config's `[project] kind` (D20).
- **A one-line reason on four bullets** (C8). The reasons sit inside the eight D17 bullets; no
  bullet is added.
- **Two short clauses keep moved items safe** (about 11 words). Bullet 4 names the replacement
  for a mutable default, because its only scoped copy (`python-typing` "Optional types",
  `typing.md.j2:59-71`) is gated on `python_version: ">=3.11"`, which is false when the detector
  finds no `requires-python` (`detector.py:323-325`). Bullet 7 says framework base classes are
  excepted, so an agent that reads only the always tier never wraps `BaseModel`; the full list of
  exceptions stays in `python-idioms` (later `python-classes-and-protocols`).
- **Neither body names a skill** (C7). A content gate pins this (section 6.8.13).
- `version` goes from 1 to 2 on both rules, because their content changed in a breaking way
  (SPEC §6.1.1).

Rendered words in the probe (whitespace-split, heading and `---` included):

| Piece of always-loaded text | Before | After |
| --- | --- | --- |
| `## Project context` section | 146 | 63 |
| `## Python house style` section | 545 | about 171 |
| `## Where guidance lives` (engine-generated, section 6.4.4) | — | 78 |
| Always rules plus map (D5 cap: 800) | 691 | about 312 |
| `AGENTS.md` before `## Guardrails` (D5 cap: 1,500) | about 5,329 | about 329 |
| `AGENTS.md`, hooks on (Guardrails unchanged until PR 4) | 6,830 | about 1,850 |
| `.claude/rules/coding-agent-playbook.md` | 5,330 | about 341 |

#### 6.5.4 Where every removed item goes

Nothing is dropped without a reason. The test `test_moved_house_style_item_has_one_owner`
(section 6.8.13) pins each moved row.

**`python-house-style`** (line numbers are today's `10-python-house-style.md`):

| Line(s) | Item | Destination |
| --- | --- | --- |
| 11, 13 | Title; "follow them in new code; when editing, follow the surrounding style if the file would become inconsistent" | Title dropped (the adapter renders the heading). The surrounding-style rule goes to the `python-idioms` intro, without the "mention the difference" tail, which `project-context` reminder 2 owns. |
| 17 | `pathlib.Path`; `os.path` only for legacy calls that need a `str` | Always bullet 2 for `Path`; the `os.path` exception goes to `python-idioms` "Paths and files", which points back to the always tier instead of restating `Path`. |
| 18 | `read_text`/`write_text` with explicit `encoding=`, because platform defaults differ | Always bullet 2 for the encoding and its reason; the API form (`Path.read_text`/`write_text`, no encoding prose) goes to `python-idioms` "Paths and files". |
| 22 | `@dataclass` (frozen when immutable); Pydantic at I/O boundaries | Always bullet 3. |
| 23 | No dict of strings as a record; three or more fields get a dataclass; never `dict[str, Any]` between layers | `python-data-shapes` "Records"; the `dict[str, Any]` ban stays in always bullet 3. |
| 24 | A frozen dataclass is shallow: `tuple`/`frozenset` fields; copy collections, builders included | `python-data-shapes` "Frozen is shallow". |
| 25 | No parallel lists; at most three tuple values; `@property` for derived values | `python-data-shapes` "Records". |
| 26 | Money is never `float` | Always bullet 5. |
| 27 | Magic values as `UPPER_CASE` `Final` constants; per-environment values in the settings object | `python-data-shapes` "Constants and settings". |
| 31 | Type-hint every signature, private helpers included | Always bullet 1. |
| 32 | No mutable default (`None`, or `field(default_factory=...)`) | Always bullet 4, replacement forms included. `python-typing` "Optional types" (`typing.md.j2:59-71`) also has them, but it is gated on `python_version: ">=3.11"`, and a repo with no detected `requires-python` never gets it. |
| 33 | Boolean flags keyword-only; split a function whose flag selects a different algorithm | Always bullet 4; the split goes to `python-idioms` "Functions and classes". |
| 34 | `Enum`/`StrEnum`/`Literal` for closed option sets, never bare string constants | Always bullet 4, condensed (`StrEnum` is an `Enum`). |
| 35 | Composition over inheritance; subclass only when genuinely substitutable | `python-idioms` "Functions and classes" (PR 5 moves it to `python-classes-and-protocols`). |
| 36 | Wrap, don't subclass, a third-party class to change its interface; framework bases, exception hierarchies and ABC extension points are normal subclassing | Always bullet 7, with a "(framework base classes excepted)" clause; the full list of exceptions goes to `python-idioms` "Functions and classes" (PR 5 moves it to `python-classes-and-protocols`). |
| 40-41 | f-strings; quote style, and don't fight the formatter | `python-idioms` "Strings". |
| 43-58 | Import groups, with an example | `python-idioms` "Imports". |
| 62 | No `from foo import *` | `python-idioms` "Imports". |
| 63 | Don't shadow builtins | `python-idioms` "Small things reviewers flag". |
| 64 | Early `return` over deep nesting | `python-idioms` "Small things reviewers flag". |
| 65 | No bare `# noqa`; name the code and say why | Always bullet 6, extended to `# type: ignore` per D17. |
| 66 | Follow the existing layout axis; never mix | Always bullet 8. |
| 68-85 | `count_lines` good/avoid example | `python-idioms` "Paths and files". |

**`project-context`** (line numbers are today's `00-project-context.md.j2`):

| Line(s) | Item | Destination |
| --- | --- | --- |
| 11 | `# About this project` | Dropped: duplicate heading. |
| 13, 15-17 | Name, kind, description | Kept. |
| 19 | `## Reminders that apply everywhere` | Dropped: a heading for two bullets. |
| 21 | Read existing code first; match conventions; copy a neighbour | Cut per D17 ("read before editing"). The "match the surrounding style" half survives in the `python-idioms` intro. |
| 22 | Prefer clarity over cleverness | Cut per D17. |
| 23 | Surface the question when scope or approach is unclear | Kept as reminder 1. |
| 24 | Keep changes minimal | Cut per D17. |
| 25 | Call out problems outside the task; don't fix them in the same change | Kept as reminder 2. |

#### 6.5.5 The four core skills

Every core skill with member rules follows these rules:

- `id` equals `name`, which equals the directory name.
- `description` is one third-person capability sentence without "Use when"; the condition goes
  in `playbook.use_when` and the file-kind phrase in `playbook.files` (section 6.4.2).
- The body has no Jinja, no markdown links and no URL, and names no rule id: a rule id would
  dangle in a repo where that member's gate fails.
- The body does not list the references; the engine generates the index.
- The body is under 20 lines.

"Critical guidance first" is met by order. The body opens with what the skill is for and how to
pick a reference. The generated index then lists each active reference with its one-line rule
description, most important first. The bodies carry no other critical summary (C6).

`catalog/core/skills/python-coding/SKILL.md`:

````markdown
---
id: python-coding
name: python-coding
description: "Library-agnostic Python conventions."
playbook:
  use_when: "writing, changing or reviewing Python code"
  files: "Any Python file"
---

# Python coding

Library-agnostic conventions for Python code in this repo. The always-loaded Python house style keeps its eight rules; each reference in this skill owns one other topic, with its reasons and examples.

## Picking references

The references index in this file lists only the references that apply to this repo, most important first, each with the one line it requires. Open every reference whose line matches the change and read it in full before writing code; most edits need one to three.

- New functions, classes or records: data shapes, typing, docstrings.
- Code that touches files, the network, the clock or a database: dependency injection, pure core, context managers, timeouts and retries.
- Code that raises, catches or logs an exception: error handling.
````

`catalog/core/skills/python-testing/SKILL.md`:

````markdown
---
id: python-testing
name: python-testing
description: "Test conventions for this repo's pytest suite."
playbook:
  use_when: "writing, changing or reviewing tests, fixtures or conftest.py"
  files: "Test files and conftest.py"
---

# Python testing

Conventions for this repo's tests: layout, naming, fixtures, parametrized cases, test data and isolation. Production code changed alongside a test still follows the python-coding skill.

## Picking references

The references index in this file lists only the references that apply to this repo, most important first, each with the one line it requires. Open every reference whose line matches the change and read it in full before writing or changing a test.
````

`catalog/core/skills/python-tooling/SKILL.md`:

````markdown
---
id: python-tooling
name: python-tooling
description: "Framework and tool wiring conventions for this repo."
playbook:
  use_when: "wiring or reviewing FastAPI apps, routers, dependency providers or error handlers"
  files: "FastAPI apps, routers, dependency providers and error handlers"
---

# Python tooling

Conventions tied to one named framework or developer tool. A reference applies only when the repo uses its framework or tool, so the references index in this file lists just the ones detected here, each with the one line it requires.

## Picking references

Open the reference for each framework or tool the change touches and read it in full before writing code. Library-agnostic conventions stay in the python-coding skill; a reference here adds only what its framework or tool changes.
````

`catalog/core/skills/ml-data/SKILL.md`:

````markdown
---
id: ml-data
name: ml-data
description: "Conventions for handling models and data artifacts in ML code."
playbook:
  use_when: "loading or saving models, checkpoints, caches or any pickled artifact"
  files: "Code that loads or saves models, checkpoints or caches"
---

# ML and data

Conventions for code that loads, stores or transforms models and data. A reference applies only when the repo uses the libraries it covers, so the references index in this file lists just the ones detected here, each with the one line it requires.

## Picking references

Open every reference whose line matches the change and read it in full before writing code. Treat code that loads a model, checkpoint, cache or array from disk or the network as security-sensitive: open the serialization reference first when the index lists it.
````

The `python-tooling` and `ml-data` texts describe only what their PR 2 members cover. PR 7 widens
`python-tooling` to tool settings and pydantic, and PR 8 widens `ml-data` to NumPy, pandas and
polars code; each updates `description`, `playbook.use_when` and `playbook.files` in the same
change, so a description never promises a reference that does not exist.

#### 6.5.6 Emitted descriptions and the Where phrases

Lengths for the reference probe, where every member is active (D4's cap is 300):

| Skill | Members | `description` | `use_when` | Emitted |
| --- | --- | --- | --- | --- |
| `python-coding` | 9 | 36 | 42 | 226 |
| `python-testing` | 1 | 46 | 61 | 145 |
| `python-tooling` | 2 | 52 | 81 | 197 |
| `ml-data` | 1 | 62 | 69 | 194 |
| Total (D5 cap: 2,000) | | | | 762 |

The bundled plugins add 3,398 characters (superpowers 2,285 across 15 skills, python_design 1,113
across 2), so core plus every plugin is 4,160 characters, under D5's cap of 6,000. With PR 4's
`playbook-guardrails` (281 characters) the total is 4,441. No plugin description needs shortening
(D5).

| Skill | `playbook.files` |
| --- | --- |
| `python-coding` | `Any Python file` |
| `python-testing` | `Test files and conftest.py` |
| `python-tooling` | `FastAPI apps, routers, dependency providers and error handlers` |
| `ml-data` | `Code that loads or saves models, checkpoints or caches` |

The rendered section is shown in section 6.4.4.

#### 6.5.7 `catalog/core/ATTRIBUTIONS.md`

`git blame` shows that today's house-style lines 23-25 and 27, and the second halves of 33 and 36,
came from the clean-architecture distillation (#27). That text now lives in `python-data-shapes`
and `python-idioms`. The "Rules:" list at lines 16-18 becomes:

```text
- Rules: python-dependency-injection, python-pure-core, python-data-shapes,
  python-idioms, python-context-managers, python-retries-and-timeouts,
  fastapi-app-wiring, fastapi-error-boundaries.
```

Lines 20-21 ("Additions to existing artifacts: the python-house-style, …") stay as they are,
because the house style keeps distilled bullets 7 and 8. `test_attributions_credit_the_distilled_source`
(`tests/integration/test_resources_self_contained.py:317-322`) keeps passing. The new skills hold
no distilled text and no source marker; the self-contained scan covers them automatically,
because it walks all of `catalog/core/`.

### 6.6 Validation and error messages

Every message names the offending value and the expected shape. Rule findings use the rule's
source path (or id); skill findings use the existing label `skills/<id> (<source package>)`
(`commands/validate.py:306-317`). All are errors unless marked warning; errors stop
`playbook sync` before any write.

| # | Check | Message |
| --- | --- | --- |
| V1 | scoped rule without `skill` | `FAIL rules/x.md: scope 'scoped' needs 'skill: <skill-id>' naming the skill whose references deliver this rule; known skills: ml-data, python-coding, python-testing, python-tooling` (`SCOPED_RULE_NEEDS_SKILL_MESSAGE`) |
| V2 | V1 on an override of a rule that had one | V1 plus `; the rule it overrides (coding_agent_playbook) names 'python-coding'` |
| V3 | always rule with `skill` | `FAIL rules/x.md: 'skill: python-coding' is not allowed on an always rule (always rules stay in always-loaded context); remove 'skill', or set 'scope: scoped' to deliver the rule through that skill` |
| V4 | `skill` not an id string | `FAIL rules/x.md: skill 42 must be a skill id string matching ^[a-z0-9]+(-[a-z0-9]+)*$ (1-64 chars), e.g. 'python-coding'` |
| V5 | unknown skill after the merge | `FAIL rules/x.md: skill 'python-codng' does not exist after merging every layer; expected one of: ml-data, python-coding, python-testing, python-tooling (or enable the overlay that ships it)` |
| V6 | member rule id not a skill-safe name (E14) | `FAIL rules/x.md: rule id 'Py_Typing' cannot be a member of skill 'python-coding': its reference is written as references/<id>.md, so the id must match ^[a-z0-9]+(-[a-z0-9]+)*$ (1-64 chars)` |
| V7 | `playbook` not a mapping | `FAIL skills/x (pkg): 'playbook' must be a mapping with optional keys files and use_when, got str 'yes'` |
| V8 | unknown key in `playbook` | `FAIL skills/x (pkg): 'playbook' has unknown key 'when'; allowed keys: files, use_when` |
| V9 | `use_when`/`files` not a non-empty one-line string, or `files` over 80 chars or ending with a period | `FAIL skills/x (pkg): 'playbook.files' is 112 chars; keep it to one line of at most 80 chars without a trailing period (it becomes one line of 'Where guidance lives')` |
| V10 | `use_when` starts with "Use when" (E15) | `FAIL skills/x (pkg): 'playbook.use_when' starts with 'Use when'; write only the condition (the engine adds 'Use when'), e.g. 'editing a Python module'` |
| V11 | `worst_case_description` is over 300 chars: the longest one-name Covers clause plus the ` and <N-1> more` tail truncation would emit, over every member after the merge (section 6.4.4, E7) | `FAIL skills/python-coding (coding_agent_playbook): the composed description cannot fit 300 chars even when the Covers clause names one member: '<text>' is 312 chars; shorten 'description' (88 chars), 'playbook.use_when' (130 chars) or the longest member name (python-typing: 'Python typing conventions')`; `<text>` is the worst case, tail included (`... Covers Python typing conventions and 8 more. Use when ...`) |
| V12 | hand-written reference collides with a member | `FAIL skills/python-coding (pkg): references/python-typing.md is hand-written in this skill but is also the rendered reference of member rule 'python-typing'; rename the hand-written file` |
| V13 | authored body has a line that is exactly `## References` | `FAIL skills/python-coding (pkg): the body has its own '## References' heading; the engine appends that section for member rules, so rename yours (e.g. '## Further reading')` |
| V14 | `skill` names a skill that exists after the merge but declares no `playbook:` block (E6, D3) | `FAIL rules/x.md: skill 'brainstorming' (superpowers) declares no 'playbook:' block, so it cannot take member rules; name one that does (ml-data, python-coding, python-testing, python-tooling), or add a 'playbook:' block to a skill of your own (an override of a core skill must keep one)` |
| W1 | `playbook` declared, no member rule anywhere (warning) | `warning: skills/x (pkg): declares 'playbook' but no rule names it in 'skill:'; it is never written` |
| W2 | members but no `playbook.files` (warning) | `warning: skills/x (pkg): has member rules but no 'playbook.files'; it is left out of the 'Where guidance lives' section` |
| W3 | the full member list would be truncated (warning, D21) | `warning: skills/python-coding (pkg): the composed description names 6 of 9 member rules within 300 chars ('... and 3 more'); shorten member names or the authored parts to list them all` |

V11 has no runtime twin in the normal path: the sync composes from a subset of the same names and
truncates, and its longest possible text (one name plus ` and <M-1> more`, `M <= N`) is never
longer than the worst case validate measured with the `N-1` tail. `playbook sync --check-staged` skips
validation (section 5.4.5) and renders into a scratch directory; there a V11 case surfaces as
`DescriptionOverflowError` with the same text and length.

**Catalog gates** (tests only, section 6.8.12-6.8.13). Each failure names the offending value and
the expected shape:

- Membership: `core rule 'python-idioms' names skill None; EXPECTED_MEMBERSHIP expects 'python-coding' (scoped rules in core must name one of: ml-data, python-coding, python-testing, python-tooling)`.
- New scoped rule missing from the table: `scoped rule 'python-foo' in core is missing from EXPECTED_MEMBERSHIP; add it with its skill id`.
- Description shape: `core skill 'ml-data': description 'Loads models …' must be one third-person capability sentence without 'Use when' (the engine adds playbook.use_when), and the composed description must name every member within 300 characters (got 'and 2 more')`.
- Where phrase: `core skill 'python-tooling' needs playbook.files: a file-kind phrase of 1-80 characters with no trailing period, got None`.
- Body hygiene: `core skill 'python-coding': SKILL.md line 14 names rule id 'python-typing'; bodies name topics, the generated index names ids`. The same pattern applies to `contains Jinja`, `contains a markdown link …` and `is 512 lines; the limit is 500`.
- D17 shape: `python-house-style has 9 bullets; D17 fixes exactly 8: ['Type-hint …', …]`, and the matching message for `project-context` and its 2 reminders.
- Lost item: `house-style item 'NamedTuple' is in no python-coding reference; expected in python-data-shapes`.
- Duplicated item: `house-style item 'f-strings' is still in the always tier; its only owner is python-idioms`.
- Always rule naming a skill: `always rule 'python-house-style' names skill 'python-coding'; routing to skills belongs to the generated 'Where guidance lives' section`.

### 6.7 Migration, orphan and lockfile effects

- **First sync after upgrading** rewrites `AGENTS.md` and `.claude/rules/coding-agent-playbook.md`
  (always rules plus the Where section), creates `<root>/<skill-id>/SKILL.md` and one
  `references/<rule-id>.md` per active member in every enabled `SkillWriter` root, and adds their
  lockfile entries (`kind = "skill"` for `SKILL.md`, `kind = "rule"` for each reference). Under
  `[output] commit = false` the managed `.gitignore` block gains one `/<root>/<id>/` entry per
  skill directory through the existing per-skill mechanism.
- **Continue, when enabled** (D11; the content changes are the only differences): rewritten at
  the same paths are `.continue/rules/00-project-context.md` and `10-python-house-style.md`, the
  `description:` line of `50-python-typing.md`, `55-python-error-handling.md`, `60-pytest.md` and
  `60-fastapi-app-wiring.md`, and the `name:` line of the seven renamed `python-coding` members.
  New are `44-python-data-shapes.md` and `58-python-idioms.md`. No
  `.continue/prompts/<core-skill>.md` is ever written (E4), so no orphan follows later either.
- **Removed:** nothing.
- **A detector change that turns a member off** leaves its reference files as orphans; the
  lockfile leftover policy (`commands/_sync_orphans.py`) deletes them when pristine and
  untracked, as for a removed skill script. When the last member turns off, the whole skill
  directory becomes orphans and is removed the same way.
- **Breaking: scoped rules without `skill:`.** Every scoped rule in an overlay or in
  `playbook/rules/` now needs `skill:`; `playbook sync` stops with V1 (and V2's hint for an
  override of a core rule) until it is added. MIGRATION.md says so first.
- **Older engines reject `skill:`.** `RuleFrontmatter(**data)` raises on the unknown key
  (`types.py:120`), so an overlay that adds `skill:` needs the engine release that ships this PR.
- **Collisions.** A hand-written `.claude/skills/python-coding/` (no sentinel) is not
  overwritten: the writer skips it with its existing warning (`_skill_writer.py:327-335`), and
  that harness then lacks the skill. A repo-local `playbook/skills/python-coding/` overrides the
  core skill by id, and the member rules still attach to it, because membership is resolved after
  the merge; the override must keep a `playbook:` block, or every core member fails V14.
  MIGRATION.md names the four core ids.
- **Rules naming a plugin skill.** An overlay or repo-local rule with `skill: brainstorming` (or
  any skill without a `playbook:` block) fails V14 instead of gating and re-describing that
  plugin skill (E6).
- **Overrides of `project-context` or `python-house-style`** keep winning by id, with their long
  text. MIGRATION suggests trimming them.
- **agent_harness manifests** gain `skill = "..."` on rule entries only when set; manifests
  written earlier load unchanged.
- **Lockfile schema** stays 2; no new provenance kind.

### 6.8 Tests

All run under `pytest -q` from the repo root with no setup; tests that read the catalog carry
`pytestmark = pytest.mark.catalog` and use the shared helpers in `tests/_catalog.py`. Every new
function gets at least one test, and each new test module stays under 300 lines.

#### 6.8.1 `tests/unit/test_types.py` (additions)

- `test_rule_frontmatter_skill_defaults_to_none_and_round_trips`: `skill` survives
  `Rule.from_dict(rule.to_dict())` and the markdown round trip.
- `test_rule_without_skill_markdown_is_byte_identical` (regression): `to_markdown()` of a rule
  without `skill` emits no `skill:` line.
- `test_skill_member_references_round_trip_through_dict`.
- `test_skill_from_dict_accepts_dict_without_member_references` (regression for dicts written
  before this PR).

#### 6.8.2 `tests/unit/test_skill_membership.py` (new)

- `test_is_skill_member_only_for_rules_naming_a_skill` (an advisory rule from
  `Hook.to_advisory_rule` is not a member).
- `test_compose_skills_passes_plain_skill_through_unchanged` (identity, empty
  `member_references`).
- `test_compose_skills_drops_skill_whose_members_are_all_inactive`.
- `test_compose_skills_drops_declared_skill_without_any_member` (E6).
- `test_compose_skills_orders_members_by_priority_then_id`.
- `test_compose_skills_uses_the_rendered_body_of_a_templated_member` (a `.md.j2` member
  rendered with `project_name`).
- `test_member_reference_carries_rule_source_package_and_globs`.
- `test_member_reference_path_is_references_slash_id_md` (E16).
- `test_undelivered_member_warning_when_only_agents_md_is_enabled` and
  `test_no_undelivered_member_warning_with_a_skill_adapter`.

#### 6.8.3 `tests/unit/test_skill_document.py` (new)

- `test_compose_description_joins_capability_covers_and_use_when` (exact string).
- `test_compose_description_without_use_when_ends_with_covers`.
- `test_compose_description_adds_missing_periods_once` (no `..`).
- `test_compose_description_truncates_covers_with_and_n_more` (D21: a 9-member input whose full
  form is over 300 characters returns at most 300 and ends the clause with `and 3 more.`).
- `test_compose_description_names_the_highest_priority_members_when_truncated` (the listed
  names are the first ones in the order given).
- `test_compose_description_raises_when_one_name_cannot_fit` (regression for the V11 bound;
  `DescriptionOverflowError` carries the text and its length).
- `test_worst_case_description_includes_the_and_n_more_tail` (regression for E7): authored parts
  and a 12-member list where `Covers <longest name>.` fits in 300 characters but
  `Covers <longest name> and 11 more.` does not; `worst_case_description` returns the second
  text, V11 fails on it, and with V11 passing `compose_description` never raises for any subset.
- `test_worst_case_description_has_no_tail_for_one_member`.
- `test_covers_clause_with_every_member_has_no_more_tail`.
- `test_emitted_frontmatter_strips_playbook_and_composes_description`.
- `test_emitted_frontmatter_of_a_plain_skill_is_the_authored_mapping` (regression: plugin
  skills unchanged).
- `test_emitted_body_appends_references_index_after_authored_body`.
- `test_references_index_line_links_rule_id_with_name_and_description`.
- `test_render_member_reference_with_and_without_globs`.
- `test_where_guidance_section_sorted_by_skill_id_with_lint_line`.
- `test_where_guidance_section_is_empty_without_entries`.
- `test_where_entry_is_none_without_members_or_files`.

#### 6.8.4 `tests/adapters/test_skill_writer.py` (additions)

- `test_write_emits_member_references_and_index`.
- `test_member_reference_bytes_identical_across_writer_roots` (three `SkillWriter` roots in one
  `tmp_path`; root names taken from `tests/plugins/superpowers_expectations.NATIVE_SKILL_ROOTS`,
  which PR 1 updates, so the two PRs do not conflict).
- `test_render_skill_md_never_emits_the_playbook_block`.
- `test_member_reference_blocked_by_user_directory_is_skipped_with_warning`.
- Existing `agent_skill_issues` tests keep passing through the re-export.

#### 6.8.5 Composite adapters

`tests/adapters/test_agents_md.py`:

- `test_agents_md_skips_member_rules`.
- `test_agents_md_keeps_always_rules`.
- `test_agents_md_where_section_sits_between_rules_and_guardrails`.
- `test_agents_md_without_member_skills_is_byte_identical` (regression: no Where section, same
  bytes as today's composition).
- `test_agents_md_written_with_only_a_where_entry`.

`tests/adapters/test_claude_code_rules.py`:

- `test_rules_file_skips_member_rules_but_keeps_unenforced_hook_advisories`.
- `test_rules_file_where_section_precedes_heartbeat`.
- `test_where_section_is_byte_identical_in_agents_md_and_rules_file`.
- `test_claude_md_stub_unchanged` (regression).

#### 6.8.6 Continue and degrade

`tests/adapters/test_continue.py`:

- `test_member_rule_file_is_byte_identical_to_before` (regression for D11: same bytes as
  `render_for(..., "continue_rule")` of the rule without `skill`).
- `test_skill_with_members_is_not_degraded_to_a_prompt`.
- `test_plain_skill_is_still_degraded_to_a_prompt` (regression).

`tests/unit/test_adapter_base.py`: `test_default_write_skill_skips_skill_with_members`;
`test_delivers_member_rules_defaults_true_and_agents_md_is_false`.

#### 6.8.7 agent_harness

- `tests/adapters/test_agent_harness.py`: `test_scoped_rule_stays_in_root_references_with_skill_in_manifest`,
  `test_skill_dir_gets_no_member_reference_files`.
- `tests/harness/test_manifest_roundtrip.py`: `test_rule_entry_round_trips_skill`,
  `test_rule_entry_without_skill_is_byte_identical` (regression).
- `tests/cli/test_import_harness.py`: `test_lossless_import_restores_rule_skill`,
  `test_best_effort_import_warns_that_scoped_rules_need_a_skill`.

#### 6.8.8 Validation: `tests/cli/test_validate_skills.py` (new)

One test per row of section 6.6, each asserting the exact `FAIL` or `warning:` line:
`test_scoped_rule_without_skill_fails_naming_known_skills` (V1),
`test_scoped_override_without_skill_suggests_the_overridden_rules_skill` (V2),
`test_always_rule_with_skill_fails` (V3), `test_skill_value_must_be_an_id_string` (V4),
`test_skill_must_exist_after_the_merge` (V5), `test_member_rule_id_must_be_a_skill_safe_name`
(V6), `test_playbook_block_must_be_a_mapping` (V7), `test_playbook_block_rejects_unknown_keys`
(V8), `test_playbook_files_must_be_one_short_line` (V9),
`test_use_when_must_not_repeat_use_when` (V10),
`test_description_that_cannot_fit_one_member_name_fails_with_length_and_text` (V11),
`test_handwritten_reference_colliding_with_a_member_fails` (V12),
`test_authored_references_heading_fails` (V13),
`test_rule_naming_a_skill_without_a_playbook_block_fails` (V14, over a python_design skill and
over a repo-local plain skill), `test_playbook_block_without_members_warns`
(W1), `test_member_skill_without_files_warns` (W2),
`test_truncated_member_list_warns_with_counts` (W3). Plus:

- `test_repo_local_rule_may_join_a_core_skill` (an overlay or repo-local rule naming
  `python-coding` validates and lands in that skill).
- `test_sync_writes_nothing_on_a_membership_error` (the gate; extends
  `tests/cli/test_sync_validate_gate.py`).

#### 6.8.9 End to end: `tests/cli/test_sync_skill_references.py` (new)

A synthetic repo (`make_synthetic_repo`) with a repo-local skill that declares `playbook:` and
two repo-local scoped rules naming it, one gated on a dependency:

- `test_sync_writes_member_references_to_every_skill_root_byte_identically`.
- `test_agents_md_and_claude_rules_file_hold_only_always_rules_and_where_section`.
- `test_sync_gates_the_skill_off_and_removes_pristine_output_when_no_member_is_active`.
- `test_sync_removes_the_reference_of_a_deactivated_member`.
- `test_lockfile_records_member_references_with_rule_provenance`.
- `test_sync_check_is_clean_after_sync`.
- `test_sync_warns_when_no_enabled_adapter_delivers_member_rules` (`adapters_enabled = []`).

#### 6.8.10 The reference probe: `tests/_budget_probe.py` and `tests/integration/conftest.py`

`tests/_budget_probe.py` (new, shared by PR 2-8) builds the D5 probe from inline constants, so no
nested `pyproject.toml` or `.ipynb` is committed under `tests/`:

```python
REFERENCE_PROBE_PYPROJECT: Final = """\
[project]
name = "mlsvc"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.115", "httpx>=0.27", "pydantic>=2.9", "torch>=2.4",
    "numpy>=2.0", "pandas>=2.2", "scikit-learn>=1.5",
]

[dependency-groups]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24", "ruff>=0.8", "mypy>=1.13"]
"""

#: PR 1's init default plus the opt-in continue, so the probe covers every adapter
#: that renders rules or skills and does not depend on which PR lands first.
REFERENCE_PROBE_ADAPTERS: Final = "claude_code,opencode,shared_skills,continue"


def write_reference_probe(repo: Path) -> None:
    """Write the probe's pyproject, ``src/app/main.py``, ``tests/test_app.py`` and a notebook.

    Example: ``write_reference_probe(tmp_path)`` then ``detect(tmp_path)``.
    """
    ...


def reference_probe_facts(repo: Path) -> Facts:
    """The detector facts of a freshly written probe (rule renders in PR 5-8 size tests)."""
    ...


def render_core_rule(rule_id: str, facts: Facts) -> str:
    """The body of core rule ``rule_id`` rendered as sync renders it, with ``facts``.

    The one place tests build the rule environment, so PR 3's
    ``build_environment`` signature change touches this helper only.

    Example: ``render_core_rule("pytest", reference_probe_facts(tmp_path))``.
    """
    ...
```

Every new PR 2-8 test that renders a core rule body (`test_core_always_rules.py`,
`test_core_rule_shapes.py`, `test_ml_data_rules.py`, the distilled-content policy tests) calls
`render_core_rule`; none calls `build_environment` directly.

`tests/integration/conftest.py` (new) runs `playbook init --non-interactive` in process
(`commands.init.run`, following `_init_probe` in `tests/plugins/python_design/test_pack.py:234-260`
with `apply_hermetic_git_env`), hooks on, `--adapters` set to `REFERENCE_PROBE_ADAPTERS`, then
enables both bundled plugins in `overlays_enabled` and syncs again:

```python
@pytest.fixture(scope="module")
def reference_probe_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The D5 reference probe, synced once per module (hooks on, both bundled plugins).

    Example::

        agents_md = (reference_probe_repo / "AGENTS.md").read_text(encoding="utf-8")
    """
    repo = tmp_path_factory.mktemp("reference-probe")
    write_reference_probe(repo)
    with pytest.MonkeyPatch.context() as patch:
        config_home = tmp_path_factory.mktemp("xdg-config")
        apply_hermetic_git_env(patch, ceiling=repo.parent, config_home=config_home)
        init_and_sync_reference_probe(repo)
    return repo
```

Words are `len(text.split())` (what `wc -w` counts); characters are `len(description)`.

#### 6.8.11 Context budget: `tests/integration/test_context_budget.py` (new, D5)

- `test_always_rules_within_800_words`: sum over the rendered bodies of always rules
  (`render_artifacts(SyncContext.from_repo(probe)).rules`, `scope == "always"`), plus the Where
  section.
- `test_agents_md_without_guardrails_within_1500_words`: the text before `## Guardrails`.
- `test_agents_md_within_1500_words`: the whole file;
  `@pytest.mark.xfail(strict=True, reason="guardrails become one line each in PR 4")` (E13).
  PR 4 removes the marker.
- `test_each_core_description_within_300_chars`.
- `test_core_descriptions_total_within_2000_chars`.
- `test_core_and_plugin_descriptions_total_within_6000_chars` (descriptions read from the
  emitted `SKILL.md` files of every root, deduplicated by id; core ids are the directories of
  `catalog/core/skills/`).
- `test_rules_file_and_agents_md_carry_no_member_rule_heading`.

#### 6.8.12 Core skills: `tests/integration/test_core_skills.py` (new, D13)

One module for every core-skill gate. It holds the two tables later PRs extend:

```python
EXPECTED_MEMBERSHIP: Final[Mapping[str, str]] = {
    "python-dependency-injection": "python-coding",
    "python-pure-core": "python-coding",
    "python-data-shapes": "python-coding",
    "python-typing": "python-coding",
    "python-error-handling": "python-coding",
    "python-context-managers": "python-coding",
    "python-docstrings": "python-coding",
    "python-retries-and-timeouts": "python-coding",
    "python-idioms": "python-coding",
    "pytest": "python-testing",
    "fastapi-app-wiring": "python-tooling",
    "fastapi-error-boundaries": "python-tooling",
    "ml-serialization-security": "ml-data",
}
EXPECTED_WHERE: Final[Mapping[str, str]] = {
    "python-coding": "Any Python file",
    "python-testing": "Test files and conftest.py",
    "python-tooling": "FastAPI apps, routers, dependency providers and error handlers",
    "ml-data": "Code that loads or saves models, checkpoints or caches",
}
```

| Test | Asserts |
| --- | --- |
| `test_core_ships_exactly_the_d4_skills` | The directories under `catalog/core/skills/` are exactly the keys of `EXPECTED_WHERE` (PR 4 adds `playbook-guardrails` to an `EXPECTED_PLAIN_CORE_SKILLS` set), and each holds only `SKILL.md`. An inventory pin: a later PR adding a hand-written reference updates it. |
| `test_core_skill_identity_and_description_shape[skill_id]` | `id == name ==` the directory name; the authored description is third person (does not start with I, you, we or use; the regex of `tests/plugins/python_design/test_pack.py:148-155` extended with `use`), ends with `.`, contains no `Use when`; `playbook.use_when` exists and does not start with `Use when`. |
| `test_core_skill_declares_where_phrase[skill_id]` | `playbook.files == EXPECTED_WHERE[skill_id]`, 1-80 characters, no trailing period. |
| `test_core_skill_md_is_plain_markdown[skill_id]` | No `{{`/`{%`, no markdown link (`links.extract_markdown_links`), no URL. The body (frontmatter excluded) contains no core rule id as a whole token; the python-testing description legitimately says "pytest", which is also a rule id. |
| `test_core_skill_md_within_500_lines_with_every_member[skill_id]` | `render_skill_md` of the skill composed with all members is at most 500 lines. |
| `test_core_skill_references_are_one_level_deep[skill_id]` | No subdirectory under a core skill's `references/`, and no hand-written reference or member rule body mentions `references/`. |
| `test_core_skills_pass_agent_skill_issues[skill_id]` | `agent_skill_issues` reports nothing. |
| `test_scoped_core_rule_names_its_skill[rule_id]` | `rule.frontmatter.skill == EXPECTED_MEMBERSHIP[rule_id]`. |
| `test_membership_table_covers_every_scoped_core_rule` | The ids of scoped rules in core equal the keys of `EXPECTED_MEMBERSHIP`. Regression: a new scoped rule cannot ship without an owner. |
| `test_always_core_rules_name_no_skill` | `project-context` and `python-house-style` have `skill is None`. |
| `test_every_core_member_skill_has_a_core_member` | Each key of `EXPECTED_WHERE` appears as a value of `EXPECTED_MEMBERSHIP`. |
| `test_reference_probe_emits_each_core_skill_within_budget[skill_id]` | In `reference_probe_repo`, `.claude/skills/<id>/SKILL.md` exists. Its description is at most 300 characters, starts with the authored capability sentence, ends with `Use when <use_when>.`, contains exactly one ` Use when `, names every member's `name` and has no `and N more` tail. |
| `test_reference_probe_where_section_lists_every_core_skill` | `AGENTS.md` and `.claude/rules/coding-agent-playbook.md` each contain `## Where guidance lives`, every `EXPECTED_WHERE` phrase and every skill id, and the lint-feedback line. |
| `test_reference_probe_writes_no_continue_prompt_for_a_member_skill` | Regression for E4: no `.continue/prompts/<skill_id>.md` exists for any key of `EXPECTED_WHERE`. |
| `test_reference_probe_continue_gets_the_two_new_rule_files` | `.continue/rules/44-python-data-shapes.md` and `58-python-idioms.md` exist, with `alwaysApply: false` and `**/*.py`. |

#### 6.8.13 Core always rules: `tests/integration/test_core_always_rules.py` (new)

| Test | Asserts |
| --- | --- |
| `test_house_style_has_exactly_eight_bullets` | The body has 8 `- ` lines and no heading. |
| `test_house_style_keeps_the_d17_items[phrase]` | Each of `Type-hint every function signature`, `pathlib.Path`, `encoding="utf-8"`, `dict[str, Any]`, `mutable default argument`, `` default to `None` ``, `default_factory`, `keyword-only`, `Literal`, `Decimal`, `# noqa`, `# type: ignore`, `Wrap a third-party class`, `framework base classes excepted` and `layout axis` is in the body. The two clauses are regressions for ungated repos (section 6.5.3 design notes). |
| `test_python_idioms_does_not_restate_the_always_tier[phrase]` | Outside fenced code, the `python-idioms` body contains none of `pathlib.Path`, `encoding="utf-8"` and `mention the difference` (always bullet 2 and `project-context` reminder 2 own them; the `count_lines` example keeps its `encoding="utf-8"` call). |
| `test_project_context_renders_exactly_two_reminders` | Rendered through the renderer with `project_name="demo"`, `project_kind="python-library"` and an empty description, the output has 2 bullets, starting `Ask before writing code` and `Report a problem`. |
| `test_project_context_renders_the_description_only_when_set` | The description line appears only when it is non-empty. Regression for the `{% if %}` blank-line layout. |
| `test_always_rules_drop_the_cut_reminders[phrase]` | `Read existing code`, `Prefer clarity over cleverness` and `Keep changes minimal` are in neither always rule (D17 regression). |
| `test_always_rule_bodies_name_no_skill[rule_id]` | No core skill id appears in either always body. |
| `test_moved_house_style_item_has_one_owner[phrase, owner]` | Each pair of section 6.5.4 (`three or more fields`, `parallel lists`, `NamedTuple`, `@property`, `frozenset`, `builder`, `Final`, `settings object` -> `python-data-shapes`; `match the file`, `os.path`, `count_lines`, `split the function`, `composition over inheritance`, `DeclarativeBase`, `f-strings`, `single quotes`, `first-party`, `import *`, `shadow builtins`, `` early `return` `` -> `python-idioms`) is in the owner's body and not in `python-house-style`. The "nothing silently lost" regression; PR 5 repoints the `composition over inheritance` and `DeclarativeBase` rows to `python-classes-and-protocols`. |

#### 6.8.14 Docs tests (D12)

- `tests/unit/test_docs_lifecycle_hooks_spec.py:157-160`:
  `test_glossary_lists_hook_as_fourth_emitted_kind_and_one_generated_plugin` becomes
  `test_hook_kind_and_generated_plugin_are_documented_outside_the_glossary`. It asserts that
  `"fourth emitted canonical kind"` is in `_spec_section("#### 6.6.7 Hooks", "## 7. Configuration files")`
  (SPEC §6.6.7 line 1150 is edited to carry that exact phrase, section 6.9.1) and that
  `` "`.opencode/plugins/playbook-hooks.js`" `` and `"exactly one file"` are in
  `_spec_section("#### 10.6.2", "#### 10.6.3")`. The same module's
  `test_section_6_6_documents_every_hook_frontmatter_field` (`:213-218`) needs SPEC §6.6.2 to list
  `RuleFrontmatter.skill`.
- `tests/unit/test_docs_continue_hooks.py:38-41`:
  `test_glossary_hook_entry_gives_continue_the_advisory_degrade_only` becomes
  `test_continue_section_states_no_wired_hook_mechanism`. It asserts that `"Continue ships no
  wired hook mechanism"` and `"guardrail text only"` are in
  `_spec_section("### 10.2 Continue adapter", "### 10.3 Claude Code adapter")`. In the same file,
  `:44-46` (`test_continue_adapter_section_states_no_hooks`) pins `"Hooks: none — guardrail text
  only."`, and the module docstring says "guardrail" instead of "advisory degrade".
- `tests/unit/test_docs_migration_hooks.py:72-77`, made by whichever of PR 1 and PR 2 opens the
  `## v0.21` MIGRATION section (P1-10; section 5.7 gives the edit): `test_migration_has_v0_20_lifecycle_hooks_section`
  keeps its v0.20 checks, but "newest release first" becomes "the `## v` headings are in
  descending version order". If PR 1 merged first, PR 2 finds the edit on `main` and makes none.
  `test_migration_heads_up_points_at_v0_20` (`:80-83`) keeps passing.
- `tests/unit/test_docs_check_rubric_refactor.py:110-125`: the pinned header becomes
  `| Version | 0.21 (draft) |`, the footer `*End of SPEC.md v0.21.*`, and `"### v0.21"` joins
  the preserved-entries list (whichever of PR 1 and PR 2 opens 0.21 makes this edit, P1-10).
- New `tests/unit/test_docs_glossary.py` (prose only):
  - `test_spec_glossary_is_a_pointer_to_context_md`: §3's body is one non-empty line that
    contains `CONTEXT.md`.
  - `test_context_md_defines_term[term]`: `**<term>**:` is in `CONTEXT.md` for Rule, Always rule,
    Scoped rule, Member rule, Skill, Reference, Prompt, Hook, Guardrail, Skill nudge, Eval task,
    Always-loaded context, Skill listing, Context budget, Skill root, Engine, Catalog, Layer, Core,
    Bundled plugin, Overlay, Detector fact, Detector, Renderer, Adapter, Harness, OpenCode plugin,
    OpenCode agent, Consumer repo, Distilled content and Vendored content.
  - `test_spec_section_6_1_documents_the_skill_field`.
  - `test_spec_section_6_3_says_core_ships_skills`: `python-coding` is present and `ships none`
    is absent.
  - `test_catalog_readme_add_a_rule_documents_skill`.
  - `test_no_doc_says_core_ships_no_skills`: across `README.md`, `catalog/README.md` and
    `SPEC.md`.
  - `test_readme_architecture_names_skill_references`: the ```` ```text ```` block contains
    `skills/<id>/` and `Where guidance lives`, and keeps the tokens
    `tests/unit/test_docs_readme_hooks.py:140-147` pins.
- New `tests/unit/test_docs_migration_skills.py`:
  - `test_migration_v0_21_section_is_first_with_tldr`: the first `## v` heading starts with
    `## v0.21` and is followed by a TL;DR table.
  - `test_migration_v0_21_covers_topic[phrase]`, for `skill:`, `Where guidance lives`,
    `CLAUDE_RULES_PATH`, `python-coding`, `44-python-data-shapes.md`, `58-python-idioms.md` and
    `playbook validate`.
  - `test_migration_quotes_the_engine_skill_required_message`: imports
    `SCOPED_RULE_NEEDS_SKILL_MESSAGE` and finds its text (with `{known}` filled for core) in
    MIGRATION.md.

#### 6.8.15 Existing tests to update

- Fixtures that build scoped rules and then validate or sync need `skill:` and a matching skill:
  `tests/cli/test_validate.py`, `tests/cli/test_sync_validate_gate.py`, `tests/cli/test_check.py`,
  `tests/cli/test_import_harness.py`, `tests/cli/test_validate_harness.py`,
  `tests/harness/test_import_roundtrip.py`. Find the rest by grepping `tests/` for
  `scope: scoped` and `scope="scoped"` (14 files today) and with a full gate run.
- Assertions that a scoped core rule's section appears in `AGENTS.md` or the Claude rules file
  move to the skill reference: `tests/cli/test_sync.py`, `tests/adapters/test_agents_md.py`,
  `tests/adapters/test_claude_code_rules.py`.
- Renamed rule names (C5): `tests/evals/test_prompting.py:65` and `:390` pin
  `### Python error handling` (now `### Error handling`); `tests/cli/test_sync.py:527-528` pin
  `### Python typing conventions` and `### Python error handling` (now `### Typing` and
  `### Error handling`).
- `tests/unit/test_sources_filesystem_bundled.py:41`: `_ENGINE_RULE_COUNT = 13` becomes `15`. A
  new `test_engine_skills_come_from_catalog_core` asserts 4 engine-package skills, each
  `SKILL.md` under `CORE_ROOT / "skills"` (PR 4 makes it 5).
- **Tests that pin a whole skill root or an exact skill list.** `make_synthetic_repo`
  (`tests/conftest.py:12-14`) and `FileSystemArtifactSource` use the real engine catalog, so from
  this PR on `python-coding` (seven ungated members) is listed and written in every synthetic
  sync, in `.claude/skills`, `.opencode/skills`, the shared root and agent_harness's `skills/`
  (with its `skills/SKILLS.md` and `HARNESS.md` listings). A proxy run with one core skill added
  failed 8 tests, all of this kind:
  - `tests/cli/test_sync_orphans.py`: `test_removed_skill_pristine_leftovers_are_deleted` (`:80`,
    every skill root absent), `test_user_file_dropped_into_engine_owned_skill_dir_survives_removal`
    (`:141`), `test_commit_true_settles_skill_leftovers_with_the_same_policy` (`:187`) and
    `test_harness_removed_skill_settles_through_the_leftover_policy` (`:319`, `skills/` absent).
  - `tests/cli/test_sync_skills.py:351`: each root's entries equal `["demo"]`.
  - `tests/unit/test_sources_filesystem.py:502`, `:550` and `:563`: `len(source.list_skills()) == 1`.

  The pattern: assert on the test's own skill (its directory, its lockfile rows, its listing line)
  instead of the whole root, and filter skill listings by the test skill's id or
  `source_package`. "The emptied root is pruned" becomes "the test skill's directory is gone, and
  the root holds only engine core skills". Do not opt the synthetic repo out of core members:
  that would hide this PR's behaviour from every sync test. A full gate run finds any further
  case of the same kind.

### 6.9 Docs

#### 6.9.1 SPEC.md

Section by section, line numbers verified at `38a9330` (`SPEC.md` is 3,967 lines; grep by heading,
never read it whole):

- **Header and changelog (lines 4-6, 11-12, 3770, 3772-3773).** Version `0.21 (draft)`, the new
  "Last updated" date, and a top bullet: `- **0.21** — Scoped rules ship inside skills (PR 2; ADR
  docs/adr/0001): a scoped rule names its owning skill (skill:), and the engine renders it as a
  reference of that skill; core ships the skills python-coding, python-testing, python-tooling and
  ml-data; AGENTS.md and the Claude Code rules file hold only always rules plus a generated "Where
  guidance lives" map; the always text is rewritten (D17); CONTEXT.md becomes the only glossary.`
  A `### v0.21 (<date>)` appendix entry lists every section changed below; the footer becomes
  `*End of SPEC.md v0.21.*`. PR 1 and PR 2 share this one version (P1-10).
- **§2.1 G1 (line 38).** "A team writes a rule once. … renders it to …" gains: "always rules go
  to always-loaded files; a scoped rule becomes a reference inside the skill it names, and
  Continue still gets one rule file per rule."
- **§3 (lines 67-84).** Replace everything under the heading with one line: ``CONTEXT.md` at the
  repository root is the project's only glossary; every term this spec uses (rule, always rule,
  scoped rule, member rule, skill, reference, prompt, hook, guardrail, layer, bundled plugin,
  harness, adapter and the rest) means what `CONTEXT.md` says.` The facts the old entries carried
  already live elsewhere: rule and prompt destinations in §6.1-§6.2 and §9.7; skill layout, roots
  and the Continue degrade in §6.3 and §10.8; git versus lifecycle hook in CONTEXT.md and §13;
  "Continue ships no wired hook mechanism" moves to §10.2; "fourth emitted canonical kind" moves
  to §6.6.7; the one generated OpenCode plugin in §10.6.2; "bundled plugin, formerly pack" in
  §11.5; OpenCode agents in §10.6.3 and §19 Q9; eval tasks in §6.5. PR 1's edit of line 70 is
  superseded by this pointer.
- **§4.1 diagram (lines 93-100).** In the catalog box, add `│   │   ├── skills/<id>/     │` under
  `core/`. In the generated box, add `.claude/skills/<id>/references/`.
- **§4.2 (lines 191-204), steps 4-6.** Compose skills from member rules after the `applies_if`
  filter; adapters receive composed skills.
- **§5.1 (line 241).** `core/  … no skills/ (Section 6.3)` becomes `core/  … the engine layer,
  always on (Section 6.3.3 for its skills)`. Add `│   │   ├── skills/   # python-coding/
  python-testing/ python-tooling/ ml-data/: SKILL.md only`, and the two new rule files under
  `languages/python/`.
- **§5.3 (lines 408-470).** Under `.claude/skills/` and `.opencode/skills/`, add `python-coding/`
  with `SKILL.md` and `references/python-typing.md …`, commented `AUTOGENERATED: core skill;
  references rendered from its member rules`. Change `.continue/rules/` to show
  `44-python-data-shapes.md`. Leave PR 1's root names alone.
- **§6.1.1 (lines 525-545).** Add `skill: python-coding  # required when scope=scoped, forbidden
  when scope=always: the one skill that owns this rule's topic (§6.3.3)`, plus one paragraph: the
  value must name a skill that exists after the layer merge (§11.2); an overlay or
  `playbook/rules/` adds a rule to a core skill just by naming it; Continue ignores the field
  (§10.2); `description` is the rule's line in its skill's references index, so write it as one
  actionable sentence; `name` is its label in the Covers clause, so keep it a short topic label.
- **§6.1.2 (lines 546-560).** Add `skill: python-coding` to the example frontmatter.
- **§6.1.4 (lines 611-625).** Retitle: "Rendered output for Claude Code: always rules in
  `.claude/rules/coding-agent-playbook.md`". Replace the `python-typing` example with the
  `python-house-style` section (section 6.5.3). The paragraph after it says that only always rules
  are concatenated, then the generated `## Where guidance lives` section, and that a scoped rule is
  not in this file (§6.1.6).
- **§6.1.5 (lines 626-627).** "Same shape as the Claude Code rules file, plus the Guardrails
  section (§10.4)."
- **New §6.1.6, "Rendered output as a skill reference".** The reference's path is
  `<skill root>/<skill>/references/<rule-id>.md`, with the section 6.4.4 example and the
  python-coding `SKILL.md` with its generated index.
- **§6.2.5 (lines 734-782).** Add a paragraph before "Resolution semantics": since v0.21 a scoped
  rule's text is not in always-loaded context on Claude Code, OpenCode or Codex, so
  `includes_rules` is how a prompt carries one; the mechanism itself is unchanged here. PR 3
  rewrites this section.
- **§6.3 (lines 783-809).** Replace "The engine's core content (`catalog/core/`) ships none; the
  engine wheel bundles skills only in opt-in bundled plugins …" with: core ships skills that own
  its scoped rules; bundled-plugin skills (`superpowers`, `python_design`) own none; overlays and
  `playbook/skills/` may ship either kind (D3). §6.3.2 (803-809): a skill with member rules is
  never degraded to a prompt.
- **New §6.3.3, "Skills with member rules".** Membership through `skill:` with one owner per rule;
  presence (written only when one member passes its gate); generated `references/<rule-id>.md`
  files and an index ordered by `(priority, id)`, one line per reference with its description; the
  `playbook:` block (`use_when`, `files`) and its stripping on output; the emitted description
  `<capability> Covers <names>. Use when …`, at most 300 characters by construction with the
  `and N more` truncation (D21); the Where section; authoring rules (third-person description, a
  body under 500 lines with no Jinja and no markdown links, no reference list in the body,
  hand-written references allowed next to rendered ones, D3).
- **§6.4 (lines 810-826).** Add: skills carry no `applies_if`; a skill with member rules follows
  its members' gates; there is no `any_of` combinator, so a skill whose members span stacks gates
  each member on its own (D9, `ml-data`).
- **§6.6.2 (lines 963-982).** `RuleFrontmatter` gains `    skill: str | None = None  # owning
  skill; required for scoped, forbidden for always; §6.1.1`; `Skill.member_references` and
  `MemberReference` are listed.
- **§6.6.7 (line 1150).** "A **hook** is the fourth emitted kind." becomes "A **hook** is the
  fourth emitted canonical kind, after `Rule`, `Prompt` and `Skill` (eval tasks are never
  emitted)." This is the moved glossary fact.
- **§9.7 (lines 1540-1551).** Add `skill` to the `continue_rule` list of dropped canonical-only
  keys. `claude_md_section` and `agents_md_section` now receive only always rules. Add a
  `skill_reference` row for the reference format of section 6.4.4.
- **§10.1 (1565 onward).** `delivers_member_rules`, and the base `write_skill` no longer
  degrading a skill with member rules.
- **§10.2 (lines 1683-1713).** The hooks paragraph becomes: "**Hooks: none — guardrail text
  only.** Continue ships no wired hook mechanism: the `cn` CLI's hook code is dormant in every
  published bundle and the IDE `config.yaml` has no hooks key, so Continue receives each enabled
  hook's guardrail text only, as a rule file (`specs/prK-lifecycle-hooks.md` §A.8)." Add: Continue
  keeps one rule file per rule, scoped ones included, and ignores `skill:`; a skill with member
  rules is not degraded to a Continue prompt. §10.2.1 table: the `10` row becomes "Python house
  style (the eight always-loaded conventions)", and the `50` row becomes "`40`-`59`
  Language-specific scoped rules (dependency injection, pure core, data shapes, typing, error
  handling, idioms)".
- **§10.3 and §10.3.1 (lines 1714-1785).** "The rules go to" becomes "The always rules, then the
  generated `## Where guidance lives` section, go to". At line 1783, "scoped rules are always
  loaded in full" is replaced by "scoped rules are not in this file: each is a reference of the
  skill it names, under `.claude/skills/<skill>/references/` (§6.3.3)". The skills paragraph after
  the listing mentions core skills.
- **§10.4 (lines 1820-1833).** `AGENTS.md` holds the always rules, the "Where guidance lives" map,
  then the Guardrails section (unchanged in this PR). In the code comment, "a harness that only
  reads AGENTS.md … gets rules only" becomes "… gets the always rules and the map of skills".
- **§10.6 (lines 1845-1850).** "the AGENTS.md adapter already delivers rules to OpenCode" becomes
  "delivers the always rules; scoped rules reach OpenCode as references in
  `.opencode/skills/<skill>/`". "so a rule's `globs` stay advisory" becomes "a scoped rule's
  `globs` gate nothing here; OpenCode loads its skill by description".
- **§10.7.2 (lines 1954-1966).** The `Rule (scope=scoped)` row records `skill` in the manifest.
- **§10.8 (lines 1970-1993).** The writer also writes member references from
  `MemberReference.text`; in `write_rule` "(rules reach every assistant through AGENTS.md …)",
  add "; scoped rules travel inside the skills this adapter writes". PR 1 renames the root in the
  same paragraph, so the second PR to land rebases it.
- **§11.2.** One line: skill membership is resolved after the merge, so a rule's `skill:` names
  the winning skill of that id.
- **§11.5 (lines 2046-2121).** Add a paragraph: skills from a bundled plugin own no rules unless a
  rule names them; a bundled plugin may add a rule to a core skill by naming it; every enabled
  plugin's descriptions count toward the skill-listing budget (core plus plugins at most 6,000
  characters on the reference probe, §16); §11.5.2's "reconciled with the engine's shipped Python
  and FastAPI rules" stays true.
- **§12.6 (2358 onward).** The V1-V13 and W1-W3 checks with sample lines (section 6.6).
- **§14.4 (2863 onward).** Member reference entries have `kind = "rule"`.
- **§16.1 and §16.3.** Name `tests/integration/test_core_skills.py`,
  `test_core_always_rules.py` and the D5 budget tests on the reference probe.

#### 6.9.2 `catalog/README.md`

- **Tree (lines 11-26).** Add `│   ├── skills/               one <id>/SKILL.md per core skill; its
  references come from the rules that name it`.
- **Lines 28-30.** "`core/` ships no skills: …" becomes: "`core/` ships four skills,
  `python-coding`, `python-testing`, `python-tooling` and `ml-data`. Each one's references are
  rendered from the scoped rules that name it. A skill in a bundled plugin owns no rules unless a
  rule names it."
- **"Add a rule" (lines 62-72).** Step 2 adds `skill`: required for `scope: scoped`, forbidden for
  `always`, and it must name a skill that exists after the layer merge (an overlay or
  `playbook/rules/` may name a core skill). A new step tells authors to pick the skill by topic
  (`python-coding`: no library needed; `python-testing`: tests; `python-tooling`: one named
  framework or tool; `ml-data`: ML and data libraries), to write `description` as the one
  actionable line the skill's index shows, and to keep `name` a short topic label (it is the
  Covers label).
- **"Add a skill" (lines 129-166).** Step 1 becomes "Pick its layer: `core/skills/<id>/` for a
  skill that owns core rules, otherwise a bundled plugin." A new step 2a covers a skill with
  member rules (the section 6.4.2 contract): a third-person capability sentence in `description`,
  `playbook.use_when` and `playbook.files`, a body that says what the skill is for and how to pick
  a reference, never lists references and never names a rule id, with no Jinja and no markdown
  links. Step 4 adds that `tests/integration/test_core_skills.py` pins the core inventory.

#### 6.9.3 `README.md`

- **Architecture diagram (lines 77-126).** Add a line under "resolve": `scoped rules join the
  skill they name`. `continue` becomes `.continue/rules/ (one file per rule) + .continue/prompts/`.
  `claude_code` becomes `always rules in .claude/rules/coding-agent-playbook.md … + skills with
  their rule references in .claude/skills/<id>/`. `agents_md` becomes `AGENTS.md (always rules +
  "Where guidance lives"; a ## Guardrails section when hooks are on)`. Keep `playbook-hook`,
  `guard_config.json`, the launcher path, the shim path and `resolve_effective_hooks`
  (`tests/unit/test_docs_readme_hooks.py:140-147`).
- **"Why" bullet "Context-aware, not noise" (lines 17-21).** Add: "Only a short always-loaded
  core rides every turn; scoped rules load on demand, as references inside skills the assistant
  picks by description."
- **"Editing content" (lines 133-135 and the mermaid at 147-166).** `catalog/core/` lists
  `skills/`, and the mermaid `core` node becomes "rules, skills, prompts, eval_tasks, hooks".
- **"3. Generate" (lines 230-241).** "Claude Code gets the same rule sections" becomes "Claude
  Code gets the same always-rule sections and the same map"; scoped rules arrive as skill
  references.
- **"4. Define which resources apply" (lines 304-323).** The `playbook/rules/` comment gains "(a
  scoped rule names its skill with `skill:`)". The closing paragraph adds that a skill is written
  only when one of its rules applies.
- **"Skills: one source, every Agent-Skills root" (lines 325-372).** The opening adds "or one
  shipped by core". New subsection "### Rules inside skills" (about 20 lines): the four core skills
  and their members, the Covers clause, the "Where guidance lives" map, how to add a rule to a
  core skill (`skill: python-coding` in `playbook/rules/x.md`), how to override a core skill
  (`playbook/skills/python-coding/`, whose members still attach), and the Continue exception.

#### 6.9.4 `MIGRATION.md`

The heads-up (lines 3-13) gets a first paragraph and keeps the v0.20 one, which
`test_migration_heads_up_points_at_v0_20` pins:

> **v0.21** moves every scoped rule into a skill. A repo or overlay with its own scoped rules must
> add `skill: <skill-id>` to each one, or `playbook sync` refuses them. Run `playbook validate`
> before upgrading.

PR 2's subsections join the shared `## v0.21 — Skills-first context` section above `## v0.20`
(line 15), created by whichever of PR 1 and PR 2 lands first; the TL;DR is one table to which
each PR adds rows. PR 2 contributes:

````markdown
## v0.21 — Skills-first context

v0.21 keeps only always rules in always-loaded context. Every scoped rule names the one skill that owns its topic (`skill:` in its frontmatter), and the engine writes it as a reference inside that skill (`docs/adr/0001-scoped-rules-are-delivered-as-skill-references.md`). Core now ships four skills: `python-coding`, `python-testing`, `python-tooling` and `ml-data`.

### TL;DR — who needs to do anything

| You are… | Migration |
| --- | --- |
| Only using engine content (core, bundled plugins) | Nothing. The next `playbook sync` (the post-checkout hook runs it) rewrites `AGENTS.md` and the Claude Code rules file and adds the skill directories. |
| Keeping your own scoped rules in `playbook/rules/` or an overlay | Add `skill: <skill-id>` to each before upgrading ("Add skill: to your own scoped rules"). Until then `playbook validate` fails and `playbook sync` refuses to run. |
| Overriding `project-context` or `python-house-style` | Your text keeps winning; consider trimming it ("The always text is shorter"). |

### AGENTS.md and the Claude Code rules file hold only always rules

`AGENTS.md` and `.claude/rules/coding-agent-playbook.md` (`CLAUDE_RULES_PATH`) now carry the always rules, then a generated `## Where guidance lives` section that maps file kinds to skills. `AGENTS.md` then ends with the Guardrails section. In a typical FastAPI + ML repo, `AGENTS.md` shrinks from about 6,800 words to about 1,800 with hooks on (about 750 once the guardrails become one line each) and to about 320 without the Guardrails section; the Claude Code rules file shrinks from about 5,300 words to about 330.

### Scoped rules arrive as skill references

Each scoped rule is now `<skills root>/<skill>/references/<rule-id>.md`, listed in that skill's index, for example `.claude/skills/python-coding/references/python-typing.md`. A skill is written only when at least one of its rules applies to the repo, so a repo without FastAPI has no `python-tooling`. Rule ids, `lint_codes`, hook links and prompt `includes_rules` are unchanged, so lint feedback still names the rule id; open the reference with that id. The `python-coding` members have short display names (`Typing`, `Error handling`, …) because each name is its label in the skill's description.

### The always text is shorter

`project-context` keeps the name, kind and description and two reminders: ask before coding when the scope or approach is unclear, and report problems outside the task instead of fixing them in the same change. The reminders "read existing code first", "prefer clarity over cleverness" and "keep changes minimal" are gone. `python-house-style` keeps eight bullets; the rest moved to two new rules in `python-coding`: `python-data-shapes` (records, frozen dataclasses, return shapes, constants) and `python-idioms` (paths, flag-driven functions, composition, strings, imports, small idioms). An override of either always rule by id keeps its own text, and with it its old length.

### Add skill: to your own scoped rules

```yaml
# playbook/rules/risk-models-specific.md.j2: before
scope: scoped
globs: ["src/risk/**/*.py"]

# after
scope: scoped
skill: python-coding
globs: ["src/risk/**/*.py"]
```

Without it, `playbook validate` and `playbook sync` stop with:

    <SCOPED_RULE_NEEDS_SKILL_MESSAGE, quoted verbatim at implementation time>

Pick the skill by topic: `python-coding` for library-agnostic Python, `python-testing` for tests, `python-tooling` for one named framework or tool, `ml-data` for ML and data libraries. To keep a rule in a skill of your own, add `playbook/skills/<id>/SKILL.md` with a capability sentence in `description` and a `playbook:` block (`use_when`, `files`); a skill without that block, such as a bundled plugin skill, cannot take rules. Always rules must not carry `skill:`.

### Continue and the new rules

Continue still gets one rule file per rule and ignores `skill:`. `.continue/rules/` gains `44-python-data-shapes.md` and `58-python-idioms.md`; `00-project-context.md` and `10-python-house-style.md` get the shorter text; seven rule files show their new short names. Core skills are not turned into Continue prompts.

### New output and the lockfile

Each written core skill adds `<root>/<id>/SKILL.md` and `references/` under every enabled skills root, one lockfile entry per file and, with `[output] commit = false`, one managed `.gitignore` line per skill directory. Nothing is removed. A hand-written skill directory of yours named `python-coding` (or another core id) is left alone with a warning; rename it, or move it to `playbook/skills/python-coding/` to override the core skill.

### Not changed (skill references)

Rule ids and file names in `catalog/`, `lint_codes`, `linked_rule` hooks, prompt rendering (`includes_rules` still inlines rule bodies until the prompts change), the lockfile schema and Claude Code's `.claude/CLAUDE.md` stub.
````

The indented error line is a placeholder, filled with the constant during implementation;
`test_migration_quotes_the_engine_skill_required_message` fails until it is. The YAML block is
not python, so ruff leaves it alone.

#### 6.9.5 `CONTEXT.md`, ADR and module docstrings

`CONTEXT.md`, `docs/adr/0001-scoped-rules-are-delivered-as-skill-references.md` and
`specs/prS-skills-context.md` are untracked today and are not harness files, so PR 2 commits them
(C12). Edits to `CONTEXT.md`, committed with it:

1. Under "Guidance kinds", after **Scoped rule**, add: "**Member rule**: A scoped rule seen from
   the skill it names in `skill:`; the engine renders it as one of that skill's references.
   Continue, which reads no skills, still receives it as its own rule file. _Avoid_: child rule."
2. **Always-loaded context**: "always rules, guardrails and the skill listing" becomes "always
   rules, the generated 'Where guidance lives' map, guardrails and the skill listing".
3. **Skill root**: add "_Avoid_: skills hub" (PR 1's note).
4. **Guardrail**: no edit. Its definition describes the state after PR 4; PRs 1-4 all land before
   v0.1.0 (D14), so no tagged release carries the gap.

New prose uses CONTEXT.md's terms and avoids its _Avoid_ list ("core rule" is written "rules in
core"; no "conditional rule", "glob rule", "pack", "appendix" for a reference, "system prompt",
"token limit", "ported", "imported"). "Advisory" remains only in code identifiers
(`hook_advisory`, `advisory_block`) and in SPEC text this PR does not touch; PR 4 renames the
prose.

The ADR is committed unchanged; its text matches this design (D18: no other ADR).

Module docstrings to update: `agents_md_adapter.py:1-11`, `claude_code_adapter.py:1-38`,
`shared_skills_adapter.py:1-16`, `opencode_adapter.py:63-79`, `_skill_writer.py:1-37`,
`_sync_render.py:1-11`.

### 6.10 Acceptance criteria

1. The CI gate passes cache-free from the repo root: `ruff check .`, `ruff format --check .`
   (including fenced Python in changed `.md` files), `mypy`, `pytest -q`.
2. `catalog/core/skills/` holds exactly `ml-data/`, `python-coding/`, `python-testing/` and
   `python-tooling/`, each with only `SKILL.md`. `git grep -n "^skill:" catalog/core/rules | wc -l`
   prints 13; the two always rules declare none.
3. On the reference probe, `AGENTS.md` contains no `## ` heading of a scoped rule; its text before
   `## Guardrails` is at most 1,500 words, the rendered always rules plus the Where section are at
   most 800 words, and the `## Project context` and `## Python house style` sections total at most
   240 rendered words (expected: about 234).
4. The Claude rules file contains the always rules, the Where section and the heartbeat line, and
   no scoped rule; `.claude/CLAUDE.md` is the four-line stub.
5. `.claude/skills/python-coding/references/python-typing.md` exists in the probe and is
   byte-identical to the copy in every other enabled skill root.
6. Every emitted core `SKILL.md` has only the standard `name` and `description` plus the
   pass-through `id` (D10), no `playbook` block, a composed description of at most 300
   characters containing `Covers ` and `Use when ` and naming every member (226, 145, 197 and 194 characters on the probe), and a `## References` index with
   one line per active member. "Where guidance lives" lists all four skills with the section 6.5.6
   phrases.
7. With PR 2's catalog (where python-tooling's only members are the two FastAPI rules), a repo
   without fastapi gets no `python-tooling` skill; adding fastapi and syncing writes it; removing it
   again and syncing deletes the pristine files.
8. Continue's `.continue/rules/*` files for the 11 scoped rules are byte-identical to the pre-PR
   output for the same rule text and name, `.continue/rules/` gains exactly
   `44-python-data-shapes.md` and `58-python-idioms.md`, and no `.continue/prompts/<core-skill-id>.md`
   exists.
9. Plugin skills (superpowers, python_design) are written byte-identically to the pre-PR output
   (the existing `tests/plugins/python_design/test_pack.py` passes unchanged).
10. A scoped rule without `skill:` makes `playbook validate` exit 1 with V1 and makes
    `playbook sync` write nothing; `playbook validate` passes on the engine catalog and on the
    probe.
11. The lockfile lists each member reference with `kind = "rule"` and the rule id.
12. Core descriptions total at most 2,000 characters; core plus bundled plugins at most 6,000.
13. `test_agents_md_within_1500_words` is a strict xfail, documented for PR 4 to remove.
14. Every row of section 6.5.4 is pinned by `test_moved_house_style_item_has_one_owner` or listed
    as cut per D17.
15. SPEC §3 is one line pointing at `CONTEXT.md`; `git grep -n "ships no skills\|ships none"
    README.md catalog/README.md SPEC.md` prints nothing; both repointed docs tests pass.
16. `MIGRATION.md`'s first release heading starts with `## v0.21`, it has the TL;DR table, and the
    release headings are in descending order.
17. `catalog/core/ATTRIBUTIONS.md` lists `python-data-shapes` and `python-idioms`, and the
    self-contained gate passes over `catalog/core/skills/`.

## 7. PR 3 — Prompts point to skills (D15, D22)

PR 3 and PR 4 both branch from `main` after PR 2 has merged, and run in parallel lanes with PR 5-8
(D19). Neither is stacked on the other: PR 3 touches the prompt path, PR 4 the hook path. Both
edit `adapters/claude_code_adapter.py`, `adapters/opencode_adapter.py`,
`commands/_sync_render.py`, `SPEC.md`, `MIGRATION.md` and `catalog/README.md`, but in different
functions and sections, so the second one to merge rebases without a design conflict.

- PR 3 title: `feat(prompts): point Claude Code and OpenCode commands at skill references`
- PR 4 title: `feat(hooks): name skills in lint feedback, move guardrail text into a skill, add skill-nudge`

PR 3 and PR 4 consume these PR 2 interfaces, under the names PR 2 ships (section 6.4):

| Interface (PR 2) | Used by |
| --- | --- |
| `RuleFrontmatter.skill: str \| None` (`types.py:72-86` gains it; required for `scoped`, forbidden for `always`) | PR 3 `reference_for`, PR 4 lint-feedback skill id, PR 4 skill-nudge globs |
| `member_reference_path(rule_id)` in `_member_reference.py`, returning `"references/<rule-id>.md"`; member rule `X` of skill `S` is written to `<skill-root>/S/references/X.md` | PR 3 pointer lines |
| `skill_membership.compose_skills(skills, merged_rules, active_rules)`, which replaces the pass-through `_sync_render.filter_skills` (`_sync_render.py:133-137`): a skill with member rules is written only when one member passes `applies_if`; a skill without member rules passes through unchanged | PR 3 "inactive skill" semantics, PR 4 guardrails-skill split |
| `catalog/core/skills/<id>/SKILL.md` loads as engine skills; the D13 static checks (`tests/integration/test_core_skills.py`) and the D5 budget tests on the reference probe (`tests/integration/test_context_budget.py`) exist | PR 4 adds `playbook-guardrails` and lifts the strict xfail |
| The Claude Code rules file `.claude/rules/coding-agent-playbook.md` carries always rules and the Where section only (D17), composed in `ClaudeCodeAdapter.finalize` | PR 4 degraded-hook lines |

### 7.1 Goal

A Claude Code or OpenCode slash command stops carrying rule bodies. It opens with a short generated `## Before you start` block that names the skills and the reference files the task needs, so the model loads them on demand. `includes_rules` stays the single declaration of what a prompt needs; nothing in a prompt body places rule text any more. Continue and the eval runner keep receiving the rule text inline.

### 7.2 Scope

In:

- Remove the `{{ rule("...") }}` calls (and the hand-written `## Reference rules` heading around them) from `generate-tests`, `review` and `security-review`.
- Remove the `rule()` Jinja helper from the renderer; a prompt that still calls it fails `playbook validate` with a migration message.
- New generated `## Before you start` block for `prompt_claude_command` and `prompt_opencode_command`.
- `prompt_continue`, the `agent_harness` prompt leaf and the eval runner render the `## Reference rules` appendix from `includes_rules` (inline text).
- `playbook validate`: replace the `rule()` ⊆ `includes_rules` cross-check with three checks (no `rule()` call, `includes_rules` is a list of strings, every id names a rule).
- `playbook render --show-rules` names the owning skill.
- Split `RuleRegistryImpl` out of `orchestrator.py` (already 585 lines) into `rule_registry.py`; move the inclusion logic out of `renderer.py` (526 lines) into a new `prompt_rule_delivery.py`.

Out:

- Skill content and reference rendering (PR 2), rule content (PR 5-8).
- Any eval feature: no new eval task, no skill materialization in the eval scratch repo (D13, eval freeze).
- Hooks (PR 4).
- Changing which rule ids a prompt lists (each `includes_rules` list stays as is).

### 7.3 Delivery by consumer

| Consumer | Today | After PR 3 |
| --- | --- | --- |
| Claude Code `.claude/commands/<slash>.md` | full rule bodies: in place for the 3 prompts that call `rule()`, else a `## Reference rules` appendix | `## Before you start` block; no rule body |
| OpenCode `.opencode/command/<slash>.md` | same as Claude Code | same block as Claude Code |
| Continue `.continue/prompts/<slash>.md` | same as Claude Code | `## Reference rules` appendix at the end, for every prompt with `includes_rules` |
| agent_harness `prompts/<slash>/SKILL.md` | the Claude command text minus frontmatter and sentinel | `## Reference rules` appendix at the end (unchanged for the 6 prompts that never called `rule()`) |
| Eval runner (`evals/prompting.py`) | body with the 3 prompts' `rule()` expansions in place; never an appendix (`prompting.py:13-15`) | body plus the `## Reference rules` appendix, the text Continue gets (D22) |
| `playbook render <prompt> --format …` | per format | per format; the registry stays unfiltered, as today (`render.py:188-203`), and `_render_prompt` passes it as `skill_references` too (section 7.4.5), so the block lists every included scoped rule |

Why agent_harness stays inline: its scoped rules are top-level `references/<id>.md` files (`agent_harness_adapter.py:333-345`), not skill references, and PR 2 does not change that layout; pointing at a skill would point at nothing.

### 7.4 Design, module by module

#### 7.4.1 Catalog prompts

| File (verified) | Change |
| --- | --- |
| `catalog/core/prompts/generate-tests.md.j2:57-62` | delete the `## Reference rules` heading, its intro sentence and the two `{{ rule(...) }}` lines; the body now ends with `## What not to do` |
| `catalog/core/prompts/review.md.j2:68-73` | delete the same block; `## Output format` now follows `## Tone` |
| `catalog/core/prompts/security-review.md.j2:46-51` | delete the same block; the body ends with `## Output format` |

`includes_rules` in all nine prompts is unchanged. The three files stay `.md.j2` (they still use `project_name`, `project_kind`, `has_framework`).

#### 7.4.2 New module `src/coding_agent_playbook/prompt_rule_delivery.py`

One module owns both delivery strategies, so a reader finds "what does `includes_rules` turn into" in one place. Stdlib only; it imports `RuleRegistry` from `renderer` under `TYPE_CHECKING` only, so `renderer` imports this module without a cycle.

```python
@dataclass(frozen=True)
class SkillReference:
    """Where an active scoped rule is delivered: its owning skill and its file inside it.

    Example: ``SkillReference("python-coding", "references/python-typing.md")``.
    """

    skill_id: str
    path: str


class SkillReferenceIndex(Protocol):
    """Which skill reference holds an included rule; ``RuleRegistryImpl`` implements it."""

    def reference_for(self, rule_id: str) -> SkillReference | None:
        """The reference of an active scoped rule; ``None`` if unknown, filtered out or always."""
        ...


BEFORE_YOU_START: Final = "## Before you start"
CLOSING_STEP: Final = (
    "For each file in scope, also load any other listed skill whose description matches it."
)


def skill_pointer_block(
    includes_rules: Sequence[str], references: SkillReferenceIndex | None
) -> str:
    """The ``## Before you start`` block of a Claude Code or OpenCode command, or ``""`` (D15).

    One numbered step per owning skill, in the order its first rule appears in
    ``includes_rules``, listing only the references of rules that are active
    here; then the closing step. ``""`` when no included rule resolves to a
    reference (or ``references`` is ``None``): the prompt then gets no block.

    Example::

        skill_pointer_block(["python-typing", "pytest"], registry)
    """
    grouped = references_by_skill(includes_rules, references)
    if not grouped:
        return ""
    steps = [load_step(n, skill, paths) for n, (skill, paths) in enumerate(grouped.items(), 1)]
    steps.append(f"{len(steps) + 1}. {CLOSING_STEP}")
    return f"{BEFORE_YOU_START}\n\n" + "\n".join(steps) + "\n"


def references_by_skill(
    includes_rules: Sequence[str], references: SkillReferenceIndex | None
) -> dict[str, list[str]]:
    """``{skill id: [reference path, ...]}`` in first-appearance order, each id once."""
    grouped: dict[str, list[str]] = {}
    if references is None:
        return grouped
    for rule_id in dict.fromkeys(includes_rules):
        found = references.reference_for(rule_id)
        if found is not None:
            grouped.setdefault(found.skill_id, []).append(found.path)
    return grouped


def load_step(number: int, skill_id: str, paths: Sequence[str]) -> str:
    """``1. Load skill `s` and read its reference(s) `p`, `q`.``"""
    noun = "reference" if len(paths) == 1 else "references"
    listed = ", ".join(f"`{path}`" for path in paths)
    return f"{number}. Load skill `{skill_id}` and read its {noun} {listed}."


def insert_pointer_block(body: str, block: str) -> str:
    """``body`` with ``block`` before its first level-2 heading outside a code fence.

    Without such a heading the block follows the leading ``# `` title line, or
    opens the body when it has no title. An empty ``block`` returns ``body``
    unchanged, so prompts without active references render byte-identically.
    """
    ...


def includes_rules_appendix(includes_rules: Sequence[str], registry: RuleRegistry | None) -> str:
    """The ``## Reference rules`` appendix (Continue, agent_harness, eval runner), or ``""``.

    Moved from ``renderer.py:368-423``. Each id once, in order; a rule that
    renders ``""`` (filtered out, unknown) is skipped; ``""`` when nothing is left.

    Example::

        includes_rules_appendix(["python-typing"], registry)
    """
    ...
```

Placement rule for the block (why "before the first `##`"): every shipped prompt opens with `# Title` and a one-paragraph role statement, then its first `##` section. Inserting there keeps the role statement first and puts the load step before the task instructions. Fences are tracked with a line scan (a line starting with three backticks toggles the state).

#### 7.4.3 `src/coding_agent_playbook/renderer.py`

| Current (verified) | Change |
| --- | --- |
| `build_environment(template_search_paths, *, is_prompt_context=False, rule_registry=None)` at `:110-175`; the `rule()` global at `:165-173`, the registry check at `:135-136` | becomes `build_environment(template_search_paths: Sequence[Path]) -> Environment`; no `rule` global anywhere, so `{{ rule(...) }}` raises `UndefinedError` in every template (rules, prompts, hooks) |
| `RULE_CALL_RE` at `:70-74` | stays: validate uses it to name the offending call (prompts, rules, and hook bodies for H19, `_validate_hooks.py:127`) |
| `RuleRegistry` Protocol at `:94-107` | unchanged (`render_for_inclusion`); its docstring drops the `rule()` wording |
| `render_for(..., rule_registry=None, template_body=None)` at `:240-292`; appendix decision at `:277-279` | signature below; `template_body` is removed (it only fed the `rule()`-call decision) |
| `includes_rules_appendix` `:368-387`, `appendix_rule_ids` `:390-402`, `_build_includes_rules_appendix` `:405-423` | moved to `prompt_rule_delivery.includes_rules_appendix`; `appendix_rule_ids` is deleted |
| `_render_prompt_continue` `:426-438` | unchanged; receives the appendix |
| `_render_prompt_claude_command` `:458-482` | third parameter becomes `block`; `output = insert_pointer_block(<title-ensured body>, block)`; no appendix |
| `_render_prompt_opencode_command` `:485-526` | third parameter becomes `block`; the block is inserted into `rendered_body` after the `$ARGUMENTS` substitution (it holds no placeholder) |

```python
def render_for(
    _template_path: Path,
    body: str,
    fmt: str,
    *,
    frontmatter: dict[str, Any],
    rule_registry: RuleRegistry | None = None,
    skill_references: SkillReferenceIndex | None = None,
) -> str:
    """Apply per-format post-processing to a Jinja-rendered body (SPEC §9.7).

    ``prompt_continue`` appends the ``## Reference rules`` appendix built
    through ``rule_registry``; ``prompt_claude_command`` and
    ``prompt_opencode_command`` insert the ``## Before you start`` block built
    through ``skill_references`` (D15). Without the matching argument the
    prompt renders with neither, so ``includes_rules`` is declarative only.

    Example::

        render_for(path, body, "prompt_claude_command", frontmatter=fm, skill_references=registry)
    """
    ...


def render_inline_prompt_markdown(
    body: str, frontmatter: Mapping[str, Any], rule_registry: RuleRegistry | None
) -> str:
    """A prompt as plain markdown with its rules inline: title, body, appendix (agent_harness).

    Byte-identical to today's agent_harness leaf for a prompt that never
    called ``rule()``: ``# <name>`` when the body has no title, then the body,
    then ``includes_rules_appendix``. No sentinel, no frontmatter.

    Example::

        render_inline_prompt_markdown(prompt.body, asdict(prompt.frontmatter), registry)
    """
    ...
```

Call sites that pass `is_prompt_context` lose the keyword: `commands/_sync_render.py:154`, `commands/render.py:177,190,212`, `evals/prompting.py:209-211,230`, and the two in `build_prompt_environment` (`orchestrator.py:325,328`, moving). Net size of `renderer.py`: about -60 lines (526 to about 470).

#### 7.4.4 `src/coding_agent_playbook/rule_registry.py` (moved) and `reference_for`

`RuleRegistryImpl` (`orchestrator.py:253-287`) and `build_prompt_environment` (`orchestrator.py:311-330`) move unchanged into `rule_registry.py`, which imports `template_source` (`orchestrator.py:244-250`) from `orchestrator`; `orchestrator.py` does not import the new module back (no cycle) and keeps `filter_applies_if` (its module docstring, `:11-15`, drops the two names). Every importer is updated (`commands/_sync_render.py:23-27`, `commands/render.py:29`, `evals/prompting.py:34`, `tests/unit/test_orchestrator.py`); no re-export shim. `build_prompt_environment(rules, facts)` keeps its signature and returns `(registry, env)` where `env` is now the base environment with `_facts` set (there is no separate prompt environment without `rule()`).

```python
class RuleRegistryImpl:
    def reference_for(self, rule_id: str) -> SkillReference | None:
        """The skill reference that holds ``rule_id`` in this sync, or ``None`` (D15).

        ``None`` when the rule is unknown, filtered out by ``applies_if`` (the
        registry holds only applicable rules), or ``scope: always`` (it is
        already in always-loaded context).

        Example: ``registry.reference_for("pytest")`` ->
        ``SkillReference("python-testing", "references/pytest.md")``.
        """
        rule = self._by_id.get(rule_id)
        if rule is None or rule.frontmatter.scope != "scoped" or rule.frontmatter.skill is None:
            return None
        return SkillReference(rule.frontmatter.skill, member_reference_path(rule_id))
```

#### 7.4.5 Adapters

| Adapter (verified) | Change |
| --- | --- |
| `claude_code_adapter.py:157` `__init__(rule_registry: RuleRegistry \| None)`; `write_prompt` `:228-246` | parameter type becomes `SkillReferenceIndex \| None` (same keyword, so `discover_adapters`, `orchestrator.py:333-358`, is unchanged); `write_prompt` calls `render_for(..., skill_references=self._rule_registry)` and stops passing `template_body`; class docstring `:125-133` updated |
| `opencode_adapter.py:101-103` `__init__`; `write_prompt` `:116-142` | same as Claude Code |
| `continue_adapter.py:52` `__init__`; `write_prompt` `:72-84` | keeps `RuleRegistry \| None`; stops passing `template_body`; output semantics unchanged |
| `agent_harness_adapter.py:273-301` `_prompt_body` | calls `render_inline_prompt_markdown(prompt.body, dataclasses.asdict(prompt.frontmatter), self._rule_registry)`; drops the `write_scope` pop and `strip_leading_sentinel`, which only undid the Claude command shape |
| `commands/render.py:188-203` `_render_prompt` (not an adapter, the other `render_for` caller) | stops passing `template_body=rendered_prompt.template_body` and passes `skill_references=registry` next to `rule_registry=registry`, so `playbook render <prompt> --format prompt_claude_command` (or `prompt_opencode_command`) shows the `## Before you start` block and `--format prompt_continue` keeps the appendix |

#### 7.4.6 `src/coding_agent_playbook/commands/_sync_render.py`

`_prerender_inclusions` (`:180-192`) keeps its job (a sandbox violation in an included rule aborts the sync before any write, because Continue and agent_harness still render rule bodies inside `write_prompt`), but iterates `dict.fromkeys(prompt.frontmatter.includes_rules)` directly; the `appendix_rule_ids` import (`:28-33`) goes. `render_artifacts` (`:140-170`) is otherwise unchanged.

#### 7.4.7 `src/coding_agent_playbook/evals/prompting.py`

| Current (verified) | Change |
| --- | --- |
| module docstring `:1-22` says the appendix is not expanded (`:13-15`) | rewritten: the runner hands the agent the Continue-shaped text (body plus `## Reference rules`), because the eval scratch repo has no synced skills a pointer could name |
| `render_prompt` `:96-115` | calls `_render_with_references(task, prompt)` instead of `_render_body` |
| `_render_body` `:130-144` | takes the facts as an argument; a plain `.md` prompt still passes through |
| `_prompt_environment` `:207-213` | `build_environment([])` plus `_facts`; no registry in the environment |
| `_LazyRuleRegistry` `:216-234` | unchanged; now consumed by the appendix, so rules still load only for a prompt that lists `includes_rules` |

```python
def _render_with_references(task: EvalTask, prompt: Prompt) -> str:
    """The rendered body plus the ``## Reference rules`` appendix Continue also gets (D15).

    Facts are computed only when the prompt is templated or lists
    ``includes_rules``, so a plain prompt without rules never runs the detector.
    Any render error, including a sandbox violation in an included rule, raises
    :class:`PromptResolutionError` naming the task and the prompt.

    Example::

        _render_with_references(task, prompt)  # "You are reviewing…\\n## Reference rules…"
    """
    ...
```

#### 7.4.8 `playbook validate`

`_check_prompt_rule_calls` (`commands/validate.py:146-165`, called at `:395`) is replaced by `check_prompt_rule_references` in a new `commands/_validate_prompts.py` (validate.py is 440 lines; the new checks go beside it, not into it). The module docstring line `validate.py:8` changes to "Prompts never call `{{ rule() }}`; every `includes_rules` id names a rule". `_check_rule_bodies_do_not_include_rules` (`:210-220`) stays.

```python
def check_prompt_rule_references(
    prompts: Sequence[Prompt], rule_ids: Collection[str]
) -> list[ValidationError]:
    """D15: prompts never call ``rule()``; ``includes_rules`` lists existing rule ids.

    ``rule_ids`` is the merged rule set before ``applies_if`` (a rule filtered
    out in this repo is still a valid id: it simply gets no pointer line).

    Example::

        check_prompt_rule_references(ctx.prompts_resolved, {r.frontmatter.id for r in rules})
    """
    ...
```

The three checks and their messages are in section 7.5. `did_you_mean` is reused from `hook_policy/_findings.py:72-81`.

#### 7.4.9 `playbook render`

- `_show_rules` (`commands/render.py:152-173`): the marker `INLINED` becomes the delivery, for example `- python-typing  (coding_agent_playbook, applies_if=True -> skill python-coding, references/python-typing.md)`; an always rule shows `-> always loaded`; `OMITTED` and `UNKNOWN` stay.
- The `UndefinedError` branch (`:278-286`) also handles a `Prompt` (today it re-raises for anything but a hook), so a prompt that still calls `rule()` prints `error: <file>: 'rule' is undefined` plus the outcome line instead of a traceback.

#### 7.4.10 Filtered rules and inactive skills

| Situation | Claude Code / OpenCode | Continue / agent_harness / eval runner |
| --- | --- | --- |
| an included rule fails its `applies_if` | no reference listed (the registry holds only applicable rules) | rule omitted from the appendix, as today |
| every member of a skill is filtered out | the skill is not written (PR 2), so no step names it | no change |
| every included rule filtered out | no block at all; the command is the body alone | no appendix, as today |
| an included rule is `scope: always` | no line: it is already in always-loaded context | inlined, as today |
| an included id names no rule | validate error (section 7.5); if validate is bypassed (`playbook render`), no line | omitted, as today |
| the same id listed twice | listed once | inlined once (today twice) |

#### 7.4.11 Rendered examples in the reference probe

Probe: fastapi, httpx, pydantic, torch, numpy, pandas, scikit-learn; dev pytest, pytest-asyncio, ruff, mypy; one notebook; default adapters; hooks on. Skills per D4: `python-typing` and `python-error-handling` are in `python-coding`, `pytest` in `python-testing`, `ml-serialization-security` in `ml-data`.

`.claude/commands/review.md` after PR 3 (body sections elided):

```markdown
---
disallowed-tools: Edit Write NotebookEdit
---
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->

# Review

You are reviewing code. A good review changes the code in the reader's head before any character changes on disk: it surfaces what they would otherwise have to learn from a production incident.

## Before you start

1. Load skill `python-coding` and read its references `references/python-typing.md`, `references/python-error-handling.md`.
2. For each file in scope, also load any other listed skill whose description matches it.

## Priorities, in order

[unchanged]

## Workflow

[unchanged]

## Tone

[unchanged]

## Output format

A bulleted list of comments, grouped by priority bucket in the order above; omit empty buckets. For each comment include the file and line. End with a one-line verdict: *approve*, *approve with comments*, or *request changes*. Do not modify the code; only review it.
```

`.claude/commands/generate-tests.md` after PR 3:

```markdown
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->

# Generate tests

Your task is to write pytest tests for probe — a `ml-research` project. The user has pointed you at a piece of code: read it first, plan the test surface, then write the tests.

## Before you start

1. Load skill `python-coding` and read its reference `references/python-typing.md`.
2. Load skill `python-testing` and read its reference `references/pytest.md`.
3. For each file in scope, also load any other listed skill whose description matches it.

## Conventions

[unchanged]

## What not to do

[unchanged; the file ends here]
```

The OpenCode files carry the same block, after the `description:` envelope and the sentinel line. The Continue files end with `## Reference rules`, then one `### <rule name>` section per rule; for `review` that appendix now follows `## Output format` instead of preceding it.

Word counts (`wc -w`, measured on the probe with today's engine; "after" is the same files with the new layout applied, using today's rule bodies; PR 2 and PR 5-8 content edits will shift the Continue numbers):

| Prompt | Claude Code | OpenCode | Continue |
| --- | --- | --- | --- |
| `/review` | 1,963 → 922 | 1,977 → 936 | 1,979 → 1,953 |
| `/generate-tests` | 1,414 → 433 | 1,431 → 450 | 1,436 → 1,415 |
| `/security-review` | 1,657 → 436 | 1,677 → 456 | 1,680 → 1,655 |
| `/refactor` | 2,965 → 1,241 | 2,978 → 1,254 | unchanged |
| `/make-testable` | 1,370 → 686 | 1,400 → 716 | unchanged |
| `/characterize` | 1,277 → 714 | 1,301 → 738 | unchanged |
| `/review-architecture` | 1,133 → 752 | 1,159 → 778 | unchanged |

The Continue drop on the three prompts is the deleted hand-written intro sentence of each `## Reference rules` section.

### 7.5 Validation and error messages

All three are `playbook validate` errors, so `playbook sync` refuses to write (its validate gate, `commands/sync.py:209`). `<path>` is the prompt's source path, else its id.

| Check | Message |
| --- | --- |
| a prompt body calls `rule()` (any spelling `RULE_CALL_RE` matches) | `<path>: body calls {{ rule("python-typing") }}; prompts no longer inline rules. Remove the call and keep 'python-typing' in includes_rules: Claude Code and OpenCode commands then point at its skill, Continue appends its text` |
| `includes_rules` is not a list of non-empty strings (a bare string used to be iterated character by character) | `<path>: includes_rules 'python-typing': expected a list of rule ids, e.g. ['python-typing', 'pytest']` |
| an `includes_rules` id names no rule in the merged set | `<path>: includes_rules names 'python-typng', which is no rule in core, an enabled overlay or playbook/rules/; did you mean 'python-typing'?` |

The rule-calls-rule check (`validate.py:210-220`) and H19 (hook bodies) keep their messages.

### 7.6 Migration, orphans, lockfile

- No file is added or removed, so there are no orphans. The next sync rewrites every `.claude/commands/*.md` and `.opencode/command/*.md` with an `includes_rules` list, the three `.continue/prompts/` files of the edited prompts, and the same three agent_harness leaves; their lockfile hashes change.
- A repo-local or overlay prompt that calls `{{ rule() }}` now fails validate (and therefore sync) with the section 7.5 message. MIGRATION.md shows the before/after: delete the call, keep the id in `includes_rules`.
- The engine is pre-v0.1.0 (D14) and no pilot repo exists yet, so the helper is removed without a deprecation window.

### 7.7 Tests

New:

| File | Test | Asserts |
| --- | --- | --- |
| `tests/unit/test_prompt_rule_delivery.py` | `test_pointer_block_groups_references_by_owning_skill_in_includes_rules_order` | `["python-typing", "pytest", "python-error-handling"]` gives step 1 `python-coding` with both coding references, step 2 `python-testing`, step 3 the closing step |
| | `test_pointer_block_says_reference_for_one_file_and_references_for_several` | singular and plural wording |
| | `test_pointer_block_skips_filtered_unknown_and_always_rules` | a fake index returning `None` for those ids gives no line for them |
| | `test_pointer_block_is_empty_without_an_active_reference` | `""` for all-`None`, for `[]` and for `references=None` |
| | `test_pointer_block_lists_a_repeated_id_once` | dedupe |
| | `test_insert_pointer_block_goes_before_the_first_level_two_heading` | block lands after the role paragraph |
| | `test_insert_pointer_block_ignores_headings_inside_code_fences` | a `## x` inside a fence is skipped |
| | `test_insert_pointer_block_follows_the_title_when_there_is_no_section` | |
| | `test_insert_pointer_block_with_empty_block_returns_the_body_unchanged` | byte identity |
| | `test_includes_rules_appendix_lists_fragments_in_order_each_once` | moved from `test_renderer.py` |
| | `test_includes_rules_appendix_is_empty_when_every_fragment_is_empty` | moved |
| `tests/unit/test_rule_registry.py` | `test_reference_for_names_the_skill_and_reference_of_an_active_scoped_rule` | `SkillReference("python-testing", "references/pytest.md")` |
| | `test_reference_for_is_none_for_unknown_filtered_and_always_rules` | three `None` cases |
| `tests/unit/test_catalog_prompt_references.py` | `test_no_shipped_prompt_calls_rule` | `RULE_CALL_RE` matches no `catalog/**/prompts/*` body |
| | `test_every_shipped_includes_rules_id_names_a_core_rule` | |
| | `test_every_shipped_included_scoped_rule_names_a_skill` | each scoped rule in an `includes_rules` list has `skill` |

Changed:

| File | Change |
| --- | --- |
| `tests/unit/test_renderer.py` | delete `test_rule_helper_registered_in_prompt_env`, `..._not_registered_in_rule_env`, `..._requires_registry_in_prompt_env` (`:108-125`), `test_render_for_prompt_continue_no_appendix_when_inline_rule_call` (`:324`), the `appendix_rule_ids` and appendix-suppression tests (`:581-680`); add `test_rule_helper_is_undefined_in_every_environment` (regression: `{{ rule("x") }}` raises `UndefinedError`), `test_render_for_prompt_claude_command_inserts_pointer_block_and_no_rule_body`, `test_render_for_prompt_claude_command_read_only_keeps_disallowed_tools_with_block`, `test_render_for_prompt_opencode_command_inserts_block_after_envelope`, `test_render_for_prompt_without_skill_references_has_no_block`; parametrized `test_build_environment_is_sandboxed` (`:537`) drops the `is_prompt_context` axis |
| `tests/unit/test_orchestrator.py`, `tests/adapters/test_sandbox_parity.py`, `tests/unit/test_render_hook_body.py` | `build_environment` call sites lose `is_prompt_context`; registry tests move to `test_rule_registry.py` |
| `tests/adapters/test_claude_code.py:180,207`, `tests/adapters/test_opencode.py:288,315` | the fake registry implements `reference_for`; renamed `..._points_at_skills_when_registry_set` (block present, no `### ` rule heading) and `..._no_block_when_registry_absent` |
| `tests/adapters/test_continue.py:149,159` | drop `template_body`; appendix assertions unchanged |
| `tests/adapters/test_agent_harness.py:401` | stays green; add `test_prompt_leaf_bytes_unchanged_for_a_prompt_without_rule_calls` (regression: leaf for a `refactor`-like prompt is byte-identical to the pre-PR text, pinned as a literal) and `test_prompt_leaf_has_no_pointer_block` |
| `tests/cli/test_validate.py:64,182` | become `test_validate_rejects_any_rule_call_in_a_prompt` and `test_validate_rejects_rule_call_with_trim_markers` (message contains `remove the call` and the id); add `test_validate_flags_includes_rules_naming_no_rule` (with did-you-mean) and `test_validate_flags_includes_rules_that_is_not_a_list` (regression for the character iteration); `:200` stays |
| `tests/cli/test_sync.py:484,505,521` | become `test_sync_points_claude_and_opencode_commands_at_skills`, `test_sync_appends_each_rule_once_to_continue_prompts`, `test_sync_shipped_review_command_carries_no_rule_body` (no `### Typing` heading, the rule's `name` since PR 2, in `.claude/commands/review.md`; exactly one in `.continue/prompts/review.md`); add `test_sync_omits_the_pointer_line_of_a_filtered_rule` and `test_sync_writes_no_block_when_every_included_rule_is_filtered` |
| `tests/cli/test_render.py:97` | becomes `test_render_show_rules_names_the_owning_skill`; add `test_render_prompt_calling_rule_reports_the_file`, `test_render_prompt_claude_command_shows_the_pointer_block` (the `review` prompt rendered with `--format prompt_claude_command` contains `## Before you start` and no `### ` rule heading) and `test_render_prompt_continue_keeps_the_reference_appendix` |
| `tests/evals/test_prompting.py` | the synthetic-prompt helper (`:161-202`) takes an `includes_rules` argument; `:62` becomes `test_reference_appendix_inlines_the_included_rule`; `:242` `test_reference_appendix_honours_the_rule_applies_if`; `:370` `test_overlay_task_can_include_an_overlay_only_rule`; `:376`, `:418`, `:452` use `includes_rules` instead of `rule()`; add `test_plain_md_prompt_gets_the_reference_appendix` (the shipped `refactor` task) and `test_rule_call_in_a_prompt_raises_prompt_resolution_error` (regression); `:52` (every shipped task renders strictly) stays |

### 7.8 Docs

| Doc | Change |
| --- | --- |
| SPEC §6.2 (`SPEC.md:628-733`; the example at `:676-711`) | the `generate-tests` example loses its `## Reference rules` block; the "two mechanisms" paragraph (`:709-711`) becomes "`includes_rules` is the only declaration" |
| SPEC §6.2.5 (`:734-782`) | rewritten: the delivery table of section 7.3, the block format, the filtered-rule table of section 7.4.10, the validate checks of section 7.5; drops the inline-`rule()` API and the "vice versa" claim at `:780` that was never implemented |
| SPEC §9.4 and §9.5 (`:1499-1526`) | `rule` leaves the context listing; §9.5 becomes one paragraph: removed in this release, prompts declare `includes_rules` |
| SPEC §9.7 (`:1540-1563`) | the three prompt rows and the `render_for` signature |
| SPEC §10.6.1 (`:1872-1898`) | example output and the `includes_rules` row |
| SPEC §10.7.2 (`:1954-1961`) and the tree comment at `:1942` | prompt leaf: inline appendix, no `rule()` |
| SPEC §12.6 (`:2358-2426`; examples `:2365-2374`) and §12.7 (`:2441-2447`) | new messages; `--show-rules` output |
| SPEC §15.3 (`:3068`) | `render_prompt` appends the appendix; `rule()` no longer exists |
| SPEC §6 file-format table (`:512`) and the render step (`:198`) | `:512` drops "you include other rules via `{{ rule() }}`" as a reason to use `.md.j2`; `:198` keeps "without `rule()`" true for every template |
| `catalog/README.md:56-60,72,76-81` | prompts list rule ids in `includes_rules`; no `rule()` |
| `MIGRATION.md` | in the shared `## v0.21 — Skills-first context` section, subsection "Prompts point at skills": the delivery table, the before/after for a `rule()` call, and an update of the eval caveat at `:504-509` |
| `CONTEXT.md` | no change: **Prompt**, **Skill** and **Reference** already cover it |

### 7.9 Acceptance criteria

1. `ruff check .`, `ruff format --check .`, `mypy` and `pytest -q` pass from the repo root, cache-free.
2. `grep -rn 'rule(' catalog/core/prompts` finds nothing; every core prompt's `includes_rules` names existing rules.
3. In the probe: `.claude/commands/{review,generate-tests,security-review,refactor}.md` and the OpenCode twins contain `## Before you start` and no `### ` heading of a rule; `.continue/prompts/review.md` contains each included rule heading exactly once, after `## Output format`.
4. `/explain` and `/find-injected-vulnerability` render byte-identically to before (no `includes_rules`).
5. A repo-local prompt with `{{ rule("python-typing") }}` makes `playbook validate` and `playbook sync` exit 1 with the section 7.5 message, writing nothing.
6. `playbook eval --show`/`--run` on `review-spot-the-bug` renders a prompt that contains `### Error handling` (the rule's `name` since PR 2) once.
7. `renderer.py` and the new modules are under 500 lines; `orchestrator.py` shrinks.
8. Manual smoke on Claude Code and on OpenCode (v1.19.3 and v2.0.32): `/review` in the probe loads `python-coding` (OpenCode: from the `plan` agent).

### 7.10 Decisions taken in this PR

| # | Decision | One-line rationale |
| --- | --- | --- |
| P3-1 | Remove the `rule()` helper outright | one delivery mechanism; pre-v0.1.0 with no pilot repo, and validate gives a migration message |
| P3-2 | Block goes before the body's first `##` heading | keeps the role paragraph first and the load step before the task; all core prompts have that shape |
| P3-3 | One numbered step per owning skill, then the closing step | "grouped by owning skill" with one action per line |
| P3-4 | No block when no included rule is an active scoped rule | the Where-guidance-lives section already gives the generic advice; prompts without rules stay byte-identical |
| P3-5 | Always rules get no pointer line | already in always-loaded context |
| P3-6 | agent_harness keeps the inline appendix | its scoped rules are not skill references |
| P3-7 | New validate checks: unknown id, non-list `includes_rules` | `includes_rules` is now the only declaration, so a typo would silently drop guidance |
| P3-8 | Split `RuleRegistryImpl` and the inclusion code into new modules | `orchestrator.py` and `renderer.py` are over 500 lines |

## 8. PR 4 — Hooks point to skills (D6, D16)

Title: `feat(hooks): name skills in lint feedback, move guardrail text into a skill, add skill-nudge`.
Branches from `main` after PR 2; runs in parallel with PR 3 and PR 5-8 (section 7 intro).

### 8.1 Goal

Hook output names skills instead of assuming rules are in context: lint feedback names the rule's skill, AGENTS.md keeps one line per guardrail with the full text in a `playbook-guardrails` skill, and a new `skill-nudge` hook names the skill that covers a file the first time a session edits it.

### 8.2 Scope

In: (a) the lint-feedback prefix; (b) a `summary` field on `HOOK.md`, one-line guardrails in AGENTS.md (and in the Claude Code rules file for the hooks Claude Code cannot run, P4-11 and open question Q3), the generated `playbook-guardrails` skill; (c) the `skill-nudge` hook and builtin; and the removal of PR 2's strict xfail on the whole-`AGENTS.md` budget test.

Out: Continue's guardrail rule files (`30-guardrail-<id>.md`) and agent_harness's (`rules/30-guardrail-<id>.md`), both unchanged (D6); deny reasons of guards; the resync hook's message; any new hook adapter (Codex hooks stay out).

Handlers that cite rule ids, all of them (verified by grep over `hook_runtime/`):

| Site | Agent-facing? | Decision |
| --- | --- | --- |
| `_ruff_buckets.py:264-275` prefix and `:250-261` bucket-1 suffix, used by `ruff_lint_feedback` (error-handling, typing, pytest hooks) and `bucket_feedback` (`docstring-nonregression` post-edit) | yes | change (section 8.3) |
| `resync_on_detector_input_change.py:77-78,186` names "rule <id>" for a rule that is applicable but not yet synced | yes | unchanged: the rule is not in any skill until sync runs, and the message already asks for the sync; after it, lint feedback and the nudge name the skill |
| `HandlerResult.rule_id` in `ruff_feedback.py:139`, `docstring_nonregression.py:73,191` | no (decision-log id) | unchanged: log ids stay rule ids |
| `deser.py` deny and context text | names no rule id | unchanged |

### 8.3 (a) Lint feedback names the skill

How the handler learns the skill id: at sync, the same way it learns the codes. `_linked_lint_codes` (`hook_policy/effective.py:386-398`) already reads the linked rule; it now also passes `rule.frontmatter.skill`, so the resolved `config["lint_codes"]` becomes `{"rule": ..., "skill": ..., "warn": [...]}`. One record, one source (the rule); no layer can set it (the key is in no handler's `CONFIG_SCHEMA`, `ruff_feedback.py:96-97`), and the runtime never imports the catalog.

```python
def linked_lint_config(
    rule_id: str, codes: list[str], skill_id: str | None = None
) -> dict[str, Any]:
    """The ``config["lint_codes"]`` value of a hook linked to ``rule_id`` (D16).

    ``skill`` is present only when the rule names an owning skill (an always
    rule has none).

    Example::

        >>> linked_lint_config("pytest", ["PT009"], "python-testing")
        {'rule': 'pytest', 'skill': 'python-testing', 'warn': ['PT009']}
    """
    config: dict[str, Any] = {"rule": rule_id}
    if skill_id:
        config["skill"] = skill_id
    config["warn"] = list(codes)
    return config
```

(`hook_policy/lint_codes.py:54-62`; the module docstring `:11-13` names the new key.)

`guard_config.json` record after sync:

```json
"error-handling-lint-feedback": {
  "handlers": {
    "post_tool_use": {
      "kind": "builtin",
      "name": "ruff_lint_feedback",
      "config": {"lint_codes": {"rule": "python-error-handling", "skill": "python-coding",
                                "warn": ["E722", "BLE001", "S110", "S112", "B904", "TRY400", "TRY401", "S101"]}}
    }
  }
}
```

`hook_runtime/handlers/_ruff_buckets.py`:

| Current (verified) | Change |
| --- | --- |
| `Judge.rules` `:121` | add `skills: Mapping[str, str] = field(default_factory=dict)` |
| `_judge` `:332-348` (`rules=` at `:342`) | add `skills={hook_id: s for hook_id, r in consumers.items() if (s := _skill_of(r))}` |
| `_rule_of` `:387-391` | add the twin `_skill_of(record: HookRecord) -> str` (reads `lint_codes["skill"]`, `""` when absent or not a string) |
| `_name` `:269-271`, `_prefix` `:274-275` | prefix becomes `rule_label(rule, skill) + ":"`; a labelled row (`quality`) keeps its label |
| `_place` `:250-261` bucket-1 suffix `f" ({_name(also, judge)})"` | becomes `rule_suffix(rule, skill)`, avoiding nested parentheses |
| module docstring `:7-13,27-29`, `event_lines` example `:303` | new spelling |

```python
def rule_label(rule_id: str, skill_id: str) -> str:
    """``rule <id> (skill <skill>)``, or ``rule <id>`` when no skill is known (D16).

    Example: ``rule_label("pytest", "python-testing")`` -> ``"rule pytest (skill python-testing)"``.
    """
    return f"rule {rule_id} (skill {skill_id})" if skill_id else f"rule {rule_id}"


def rule_suffix(rule_id: str, skill_id: str) -> str:
    """The bucket-1 tail naming the rule that also claims a CI finding.

    Example: ``rule_suffix("python-typing", "python-coding")`` ->
    ``" (rule python-typing, skill python-coding)"``.
    """
    return f" (rule {rule_id}, skill {skill_id})" if skill_id else f" (rule {rule_id})"
```

Resulting lines:

```text
rule python-error-handling (skill python-coding): "src/app.py:4 E722 Do not use bare `except`"
rule pytest (skill python-testing): "tests/test_app.py:9 PT009 Use a regular `assert` instead of unittest-style `assertEqual`"
ruff (CI fails on this): "src/app.py:7 ANN001 Missing type annotation for function argument `x`" (rule python-typing, skill python-coding)
```

A `guard_config.json` rendered before this PR (no `skill` key) prints the old `rule <id>:` prefix: the runtime never fails on a stale config. The docstring examples at `ruff_feedback.py:135` and `docstring_nonregression.py:185` change accordingly.

### 8.4 (b) Guardrails: one line in always-loaded context, full text in a skill

#### 8.4.1 Source of the one-liner: a new optional `HOOK.md` field `summary`

Decision: an authored `summary`, with a fallback. The hook `description` is written for people reading `playbook check` ("Deny an edit that…") and the first body sentence runs up to 270 characters in the core pack (`destructive-command-guard`); a cut sentence loses its point (`stop-ci-parity-gate`'s would drop the list of checks D17 says the line names). The fallback keeps third-party hooks working without an edit.

- `HookFrontmatter` (in `_hook_frontmatter.py` since PR 2, section 6.4.1; `types.py:305-327` at `38a9330`) gains `summary: str = ""` (after `tags`); `from_mapping` (`types.py:353-386` at `38a9330`) reads it with a new `FieldReader.guardrail_summary("summary")`; `_hook_schema.TOP_KEYS` (`_hook_schema.py:50-70`) lists `"summary"` after `"description"`. `to_mapping` drops it when empty, so hooks without one round-trip byte-identically.
- Shape, checked in `from_mapping` (H1, structural, so no new contract number): a single line of 1-120 characters, no `{{` or `{%` (frontmatter is never rendered).
- `GUARDRAIL_SUMMARY_MAX_CHARS = 120` lives in `hook_policy/advisory.py`.
- Fallback when `summary` is empty: the first sentence of the rendered body, cut at the last word boundary before 120 characters with `…` appended.
- Every core hook with a non-blank body (33 of the 41 `HOOK.md` files) gets an authored `summary` in this PR; a catalog test (section 8.8) keeps it that way. Examples:

| Hook | `summary` |
| --- | --- |
| `stop-ci-parity-gate` | ``Before claiming done, run `ruff check .`, `ruff format --check .`, the type checker and the tests; report the results.`` (118 chars) |
| `destructive-command-guard` | ``Never run destructive commands (`rm -rf`, force-push, `git reset --hard`, `curl … \| sh`) on your own; ask first.`` |
| `guard-generated-outputs` | ``Do not hand-edit files `playbook sync` generates; edit the canonical source under `playbook/`, then sync.`` |
| `block-precommit-bypass` | `This repository's pre-commit hooks must run on every commit.` |

```python
GUARDRAIL_SUMMARY_MAX_CHARS: Final = 120


def guardrail_summary(summary: str, body: str) -> str:
    """The one-line guardrail text: ``summary``, else the body's first sentence, cut to 120.

    Example::

        >>> guardrail_summary("", "Ask first. Then act.")
        'Ask first.'
    """
    ...


def guardrail_line(hook_id: str, summary: str) -> str:
    """One AGENTS.md guardrail line (D6).

    Example: ``guardrail_line("x", "Ask first.")`` -> ``"- `x`: Ask first."``.
    """
    return f"- `{hook_id}`: {summary}"


def guardrails_section(lines: Iterable[tuple[str, str]]) -> str:
    """``## Guardrails``, the preface, then each ``(hook id, line)`` sorted by hook id."""
    ...
```

`ResolvedHook` (`hook_policy/resolved.py:70-130`) gains a property `guardrail_text` (like `name` at `:102-105`): `guardrail_summary(definition.frontmatter.summary, definition.body)`; without a definition, the advisory body's first sentence. Not serialized.

#### 8.4.2 AGENTS.md section

`agents_md_adapter.py`: `_GUARDRAILS_HEADING` (`:28-32`) becomes the new preface, `write_hook` (`:71-81`) buffers `(hook.id, guardrail_line(hook.id, hook.guardrail_text))` instead of the advisory block, and `_guardrails_section` (`:127-130`) delegates to `guardrails_section`. Rule sections and the "no hooks, byte-identical" behaviour are unchanged.

```markdown
## Guardrails

Lifecycle hooks enforce these on assistants that run them; on every other assistant, follow them yourself. Skill `playbook-guardrails` has the full text of each one and where it is enforced.

- `block-precommit-bypass`: This repository's pre-commit hooks must run on every commit.
- `clean-code-metrics-nonregression`: …
- `destructive-command-guard`: Never run destructive commands (`rm -rf`, force-push, `git reset --hard`, `curl … | sh`) on your own; ask first.
- …
- `stop-ci-parity-gate`: Before claiming done, run `ruff check .`, `ruff format --check .`, the type checker and the tests; report the results.
- …
```

Size in the probe: 23 lines. Today the section is 1,521 words; with summaries of at most 120 characters it is about 430 words (measured on the current bodies with the fallback: 400 words for the lines plus the 30-word preface). The per-hook italic enforcement line moves to the skill; the preface keeps advice from being mistaken for enforcement (QC-10, `specs/prK-lifecycle-hooks.md:817`).

#### 8.4.3 The `playbook-guardrails` skill

Source: an authored `catalog/core/skills/playbook-guardrails/SKILL.md` (D4), with no member rules:

```markdown
---
id: playbook-guardrails
name: playbook-guardrails
description: Holds the full text of every guardrail this repository enables, with what each lifecycle hook checks and on which assistants it is enforced. Use when a guardrail line in AGENTS.md needs detail, or before deleting files, committing, pushing, adding a dependency or handling secrets.
---

# Playbook guardrails

Each section is one guardrail this repository enables: the practice, then where a lifecycle hook enforces it. Where no hook runs, apply it yourself.
```

The description is 281 characters (≤ 300, third person, has "Use when", no `: ` so it stays a plain YAML scalar), so the D13 lint and the D5 listing budget cover it like any core skill. Its id is the constant `GUARDRAILS_SKILL_ID = "playbook-guardrails"`; an overlay or repo-local skill with that id replaces the authored text (description, intro) and still gets the generated sections. It has no member rules and no `playbook:` block, so `compose_skills` (PR 2) passes it through unchanged, and the core-skill tests check it as a plain core skill whose authored description carries the `Use when` clause itself (section 6.8.12).

Composition, in a new `src/coding_agent_playbook/hook_policy/guardrails_skill.py` (stdlib only, like the rest of `hook_policy`):

```python
GUARDRAILS_SKILL_ID: Final = "playbook-guardrails"


def split_guardrails_skill(skills: Sequence[Skill]) -> tuple[list[Skill], Skill | None]:
    """``skills`` without the authored guardrails skill, and that skill (``None`` if absent).

    Example::

        regular, authored = split_guardrails_skill(compose_skills(skills, merged, active))
    """
    ...


def compose_guardrails_skill(authored: Skill | None, hooks: Sequence[ResolvedHook]) -> Skill | None:
    """The authored skill with one section per on hook that has an advisory, or ``None``.

    Sections are sorted by hook id; each is ``## <name> (`<id>`)`` over the
    hook's advisory text (rendered body plus its enforcement line, the text
    AGENTS.md carried before D6). ``None`` when ``authored`` is ``None`` or no
    hook has an advisory (hooks off, no hook with a body, or
    ``[hooks] advisory = false``): the skill is then not written at all.

    Example::

        compose_guardrails_skill(authored, rendered.hooks.resolved)
    """
    ...
```

Wiring:

| File (verified) | Change |
| --- | --- |
| `commands/_sync_render.py:43-61` `RenderedArtifacts` | new field `guardrails_skill: Skill \| None = None` |
| `commands/_sync_render.py:140-170` `render_artifacts` | `skills, authored = split_guardrails_skill(compose_skills(...))`; after `hooks` is resolved, `guardrails_skill=compose_guardrails_skill(authored, hooks.resolved)` |
| `commands/_sync_hooks.py:141-143` `SyncHooks.dispatch` | gains `guardrails_skill: Skill \| None = None` and puts it on the `HookDispatch` |
| `commands/_sync_lockfile.py:116-130` `HookDispatch` | new field `guardrails_skill: Skill \| None = None` |
| `commands/_sync_lockfile.py:156-160` `dispatch_to_adapters` | each adapter's skills are `_skills_for(adapter, skills, plan)` |
| `commands/sync.py:132-145` `_render_into` | passes `guardrails_skill=rendered.guardrails_skill` to `dispatch(...)` |
| `adapters/base.py` (after `write_hook`, `:106-118`) | new `Adapter.writes_guardrails_skill(hooks) -> bool`, default `False` |

```python
class Adapter(ABC):
    def writes_guardrails_skill(self, hooks: Sequence[ResolvedHook]) -> bool:
        """Whether this adapter writes the ``playbook-guardrails`` skill for ``hooks`` (D6).

        Default ``False``: Continue and agent_harness keep their per-hook
        guardrail rule files, and AGENTS.md is not a skill root.
        """
        return False


def _skills_for(adapter: Adapter, skills: Sequence[Skill], plan: HookDispatch) -> Sequence[Skill]:
    """``skills``, plus the guardrails skill when this adapter writes it."""
    extra = plan.guardrails_skill
    if extra is None or not adapter.writes_guardrails_skill(plan.hooks):
        return skills
    return (*skills, extra)
```

Because the skill travels through the normal `write_skill` path, it is written by the shared `SkillWriter` (byte-identical in every root, D10), recorded in the lockfile as `Provenance(kind="skill", artifact_id="playbook-guardrails")`, protected by `guard-generated-outputs`, and settled by the skill leftover policy when it stops being written.

Who writes it (gating):

| Adapter | `writes_guardrails_skill` | Why |
| --- | --- | --- |
| `opencode` (`.opencode/skills`) | any hook has an advisory | OpenCode reads the AGENTS.md lines |
| `shared_skills` (`.agents/skills` after PR 1) | any hook has an advisory | Codex reads the AGENTS.md lines |
| `claude_code` (`.claude/skills`) | any hook with an advisory that Claude Code does not run natively | Claude Code runs the core pack natively and gets no guardrail lines (D6); only a hook it cannot run (an overlay hook without `claude_code` in `supports`, or one whose events Claude cannot reach) degrades to a line plus the skill |
| `continue`, `agent_harness`, `agents_md` | default `False` | Continue keeps `30-guardrail-<id>.md` (D6); agent_harness keeps `rules/30-guardrail-<id>.md`; AGENTS.md is not a skill root |

Gating summary: the skill exists only with hooks on and at least one on hook with an advisory. In the probe it is written to `.opencode/skills/playbook-guardrails/` and `.agents/skills/playbook-guardrails/`, not to `.claude/skills/`.

The native test for Claude Code is today's `ClaudeHooks.add` (`adapters/_claude_hooks.py:112-122`): `adapter in hook.supports and any(event in support for event in hook.events)`. It moves into a function `runs_natively(hook, adapter, support) -> bool` in the same module, used by `add` and by `ClaudeCodeAdapter.writes_guardrails_skill`, so the two can never disagree.

Emitted `SKILL.md` (excerpt):

```markdown
---
name: playbook-guardrails
id: playbook-guardrails
description: Holds the full text of every guardrail this repository enables, with …
---
<!-- AUTOGENERATED by coding-agent-playbook — edit in source, run 'playbook sync' -->

# Playbook guardrails

Each section is one guardrail this repository enables: the practice, then where a lifecycle hook enforces it. Where no hook runs, apply it yourself.

## Do not bypass the pre-commit hooks (`block-precommit-bypass`)

This repository's pre-commit hooks must run on every commit. …

*Enforced by lifecycle hooks on: Claude Code, OpenCode. Everywhere else this is guidance: apply it yourself.*

## …
```

Size in the probe: 23 sections, about 205 lines (today's AGENTS.md section is 199) and 1,600 words, under the 500-line cap and 5k tokens; even all 33 hooks with a body would stay under 300 lines. One file, no references: the agent loads it rarely, and splitting per hook would need generated references for a non-rule source.

#### 8.4.4 Claude Code

`ClaudeCodeAdapter.write_hook` (`claude_code_adapter.py:177-188`) today degrades a hook it cannot run to a full advisory section of the rules file (`super().write_hook` → `write_rule`). It now buffers `(hook.id, guardrail_line(...))` for such a hook (when it has an advisory), and `finalize` appends `guardrails_section(lines)` after the always rules PR 2 composes. With the core pack every hook is native, so the rules file has no Guardrails section and `.claude/skills/` has no `playbook-guardrails`. That is a reading of D6 and D17, recorded as P4-11 and open question Q3: D17's letter says the Claude rules file carries no guardrails, while D6 keeps Claude Code's behaviour "as today", and today a hook Claude cannot run already reaches the rules file as a full section. PR 4 implements the default of Q3 (one line plus the skill for such a hook); if the user picks D17's letter instead, `write_hook` skips the line, and the skill alone carries the text. PR 2's always-only rules file drops only rules that name a skill (`is_skill_member`), so until this PR a scoped advisory rule (`types.py:466-488`, `skill=None`) still reaches the rules file as a full section; this PR turns it into one line.

#### 8.4.5 Unchanged

Continue's `30-guardrail-<id>.md` files (base `write_hook` → `write_rule`, `base.py:106-118`) and agent_harness's `rules/30-guardrail-<id>.md` plus its `HARNESS.md` pointer stay byte-identical. The `hook_advisory` format (`renderer.py:344-352`) and `playbook render <hook-id>` are unchanged.

### 8.5 (c) The `skill-nudge` hook

#### 8.5.1 `catalog/core/hooks/feedback/skill-nudge/HOOK.md`

```yaml
---
id: skill-nudge
name: Skill nudge
description: Name the skill that covers a file the first time a session edits it, one line per skill (warn only).
version: 1
tier: default
priority: 30
events: [post_tool_use]
matcher:
  post_tool_use:
    tools: [edit, write]
handler:
  builtin: skill_nudge
decisions: [context, none]
timeout: 2
on_error: open
supports: [claude_code, opencode]
tags: [feedback, skills]
---
```

- No body, so no advisory, no guardrail line and no Continue rule file (the "Where guidance lives" section already says the same thing in always-loaded context).
- `tier: default`, in the `feedback/` category directory (D16's feedback tier): on whenever hooks are on; off with `[hooks] disable = ["skill-nudge"]`.
- `tools: [edit, write]`: every member-rule glob today is `*.py` (verified in `catalog/core/rules/**`), and these classes are already in Claude Code's `PostToolUse` matcher (`Bash|Edit|MultiEdit|PowerShell|Write` in the probe), so `.claude/settings.json` gets no new managed entry. PR 8 gives the ML rules `**/*.ipynb` globs and adds `notebook_edit` to this list (section 12.2).
- `priority: 30`: lower runs first, so the nudge is the first context item of the event (ahead of `validate-then-sync-on-canonical-edit` at 40, `resync-on-detector-input-change` at 45 and the ruff hooks at 50-60) and the 8-item event cap (`caps.py:68-69`) does not cut it in the core pack.
- No `matcher.paths`: the per-repo globs are only known at sync, so the handler filters.

#### 8.5.2 Globs computed at sync

The derived-config mechanism that already feeds `toolchain-missing-hint` and `pytest-conventions-feedback` (`_guard_config_toolchain.py:120-155`, merged in `guard_config.py:262-266`) carries the table. New module `src/coding_agent_playbook/_guard_config_skills.py`:

```python
SKILL_NUDGE_HOOK_ID: Final = "skill-nudge"


def skill_glob_rows(rules: Iterable[Rule]) -> list[dict[str, Any]]:
    """``[{"id": <skill>, "globs": [...]}]`` from the scoped member rules, sorted by skill id.

    ``rules`` are the rules this sync renders, already ``applies_if``-filtered,
    so a skill appears only when it is written (PR 2). A rule without ``skill``
    or ``globs`` adds nothing; a skill's globs keep first-seen order, each once.

    Example::

        >>> skill_glob_rows([pytest_rule])  # doctest: +SKIP
        [{'id': 'python-testing', 'globs': ['tests/**/*.py']}]
    """
    ...
```

- `GuardConfigInputs` (`guard_config.py:200-233`) gains `skill_globs: Sequence[Mapping[str, Any]] = ()`; `render_guard_config` adds `SKILL_NUDGE_HOOK_ID: {"skills": [dict(row) for row in inputs.skill_globs]}` to `derived`.
- `write_runtime_outputs` (`commands/_sync_hooks.py:188-225`) gains `rules: Sequence[Rule] = ()` and passes `skill_globs=skill_glob_rows(rules)`; its caller `commands/sync.py:143` passes `rules=rendered.rules`.
- The derived value replaces whatever a layer wrote (`with_derived_config` merges it last), and `skills` is in no `CONFIG_SCHEMA`, so a consumer cannot set it.

`guard_config.json` in the probe (illustrative: the `python-tooling` and `ml-data` globs depend on PR 7 and PR 8 members; shown with today's rules, in rule order):

```json
"skill-nudge": {
  "handlers": {
    "post_tool_use": {
      "kind": "builtin",
      "name": "skill_nudge",
      "config": {"skills": [
        {"id": "ml-data", "globs": ["**/*.py"]},
        {"id": "python-coding", "globs": ["**/*.py"]},
        {"id": "python-testing", "globs": ["tests/**/*.py"]},
        {"id": "python-tooling", "globs": ["**/routers/**/*.py", "**/routes/**/*.py", "**/api/**/*.py", "**/*.py"]}
      ]}
    }
  }
}
```

#### 8.5.3 The builtin `skill_nudge`

New `src/coding_agent_playbook/hook_runtime/handlers/skill_nudge.py`, registered in `_BUILTIN_HANDLER_MODULES` (`hook_runtime/registry.py:70-127`) as `"skill_nudge": f"{_HANDLERS}.skill_nudge"`. Imports only `globs`, `decision`, `registry` (hot path, `specs/prK-lifecycle-hooks.md` §D.1).

```python
SKILL_NUDGE_LINE: Final = "Conventions for this file: skill {skill_id}."
SKILL_NUDGE_MAX_CHARS: Final = 200
#: ``skills`` is not a key: sync derives it from the member rules (section 8.5.2).
CONFIG_SCHEMA: Final[Mapping[str, ConfigKey]] = {}


@register_hook_handler(
    "skill_nudge",
    events=["post_tool_use"],
    decisions=["context", "none"],
    config_schema=CONFIG_SCHEMA,
)
def skill_nudge(ev: CanonicalEvent, ctx: HandlerContext) -> HandlerResult | None:
    """One line per skill whose member-rule globs match a file this edit wrote (D16).

    Silent without a tool call, when the state root is unusable (nothing could
    dedupe the line), or when no written path is in the repository and matches
    a skill. Combine shows each line at most once per session.

    Example::

        >>> skill_nudge(edit_of_src_app_py, ctx).context  # doctest: +SKIP
        ('Conventions for this file: skill python-coding.',)
    """
    if ev.tool is None or not ctx.session.store.usable:
        return None
    keys = [path.key for path in ev.tool.write_paths if path.same_repo]
    lines = tuple(nudge_line(skill_id) for skill_id in matching_skills(ctx, keys))
    if not lines:
        return None
    return HandlerResult(
        decision=Decision.CONTEXT,
        hook_id=ctx.hook.id,
        rule_id="skill_nudge",
        context=lines,
        dedupe_key="skill-nudge",
    )


def matching_skills(ctx: HandlerContext, keys: Sequence[str]) -> list[str]:
    """The skill ids, in config order, whose globs match any of ``keys``."""
    ...


def skill_glob_table(
    config: Mapping[str, Any], *, platform: str, home: str | None
) -> tuple[tuple[str, GlobSet], ...]:
    """``config["skills"]`` compiled; a malformed row or one whose globs do not compile is skipped."""
    ...


def nudge_line(skill_id: str) -> str:
    """``Conventions for this file: skill <id>.``, clipped to 200 characters."""
    return SKILL_NUDGE_LINE.format(skill_id=skill_id)[:SKILL_NUDGE_MAX_CHARS]
```

- Path to skills: each written path's `NormalizedPath.key` (repo-relative, case-folded where the platform folds, `hook_runtime/paths.py:117-153`) is matched against each skill's `GlobSet` (`hook_runtime/globs.py:57-71`, the matcher grammar every hook uses). A path outside the repository is skipped.
- Once per skill per session: reused, not rebuilt. The result sets `dedupe_key="skill-nudge"`; `combine._context` (`hook_runtime/combine.py:167-183`) calls `SessionState.once("ctx:skill-nudge:<sha1(line)[:8]>")` (`session.py:96-103`) only for items it actually shows. The line text holds the skill id, so the key is per skill; a line cut by a cap does not burn its key and shows on the next matching edit. No new state file.
- Stateless store: `SessionState.once` answers `True` there (`session.py:11-13`), which would repeat the line on every edit, so the handler returns `None` when `ctx.session.store.usable` is false (`state.py:147-150`). A busy lock can repeat a line once; acceptable for advice.
- Message: at most 98 characters with a 64-character skill id; clipped at 200 by construction. Several skills match a typical Python file in the probe (`ml-data`, `python-coding`, `python-tooling`): one line each, at most 5 per event (`OutputCaps.CONTEXT_ITEMS_PER_HOOK`), each once per session.
- Fail-open: `on_error: open`; a missing or malformed `skills` table yields no line; an exception is the runtime's failure policy (open), never a block.
- Cost: no I/O besides the session document the combine step already locks; one glob compile per event. `timeout: 2` s is well under the 30 s cap for tool events (`contract.py:66-70`).

#### 8.5.4 The hook contract

| Rule | How `skill-nudge` meets it |
| --- | --- |
| H1, H8 | known keys only; no `summary` (no body) |
| H2 | id `skill-nudge` matches its directory |
| H3 | `post_tool_use` |
| H4 | `tools: [edit, write]`, both reachable on Claude Code and OpenCode, so `playbook check` labels it `enforced` on both (until PR 8 adds `notebook_edit`, which OpenCode has no tool for, section 12.2) |
| H5 | `context`, `none` are valid on `post_tool_use` and declared by the builtin |
| H6, H7, H13 | engine hook, builtin only, no `scripts/`, registered name, empty `CONFIG_SCHEMA`, no authored config |
| H9, H10 | 2 s ≤ 30 s; `open` |
| H11, H12 | `supports: [claude_code, opencode]`; `tier: default`, not mandatory |
| H17, H18 | no `applies_if`, no `linked_rule` (it follows every member rule, not one) |
| H19 | empty body |
| H20 | no rule or prompt has the id `skill-nudge` |
| H14, H15, H16, H21 | layer and config rules apply unchanged; overlays may only tighten it |

### 8.6 Validation and error messages

| Where | Input | Message |
| --- | --- | --- |
| `HookFrontmatter.from_mapping` (H1) | `summary` of 150 characters | `playbook/hooks/x/HOOK.md: summary: expected a single line of 1-120 characters without '{{' or '{%', got 'Never run …'` |
| same | multi-line or templated `summary` | same message |
| sync, effective view | a linked rule without `skill` | no error: the prefix stays `rule <id>:` (an always rule may carry `lint_codes`) |
| runtime | `skills` table malformed | no line, no error (fail-open) |

### 8.7 Migration, orphans, lockfile

- `AGENTS.md`: the Guardrails section shrinks to one line per hook (1,521 → about 430 words in the probe).
- New lockfile entries: `.opencode/skills/playbook-guardrails/SKILL.md` and `.agents/skills/playbook-guardrails/SKILL.md` (provenance `skill`). Turning hooks off later makes them leftovers for the standard skill leftover policy (SPEC §4.2 step 9).
- `guard_config.json`: `lint_codes.skill` on the four linked lint hooks and the new `skill-nudge` record; the `✓ Hooks:` summary in the probe goes from `29 enabled` to `30 enabled` (`claude_code: 30 enforced`); Continue's advisory count is unchanged (no body). `.claude/settings.json` managed entries are unchanged (no new tool class on `PostToolUse`). If the OpenCode plugin bytes change, sync prints the existing restart notice.
- Overlay and repo-local hooks need no edit: without `summary` they get the first-sentence fallback.
- Continue and agent_harness outputs are byte-identical.

### 8.8 Tests

| File | Test | Asserts |
| --- | --- | --- |
| `tests/unit/test_hook_policy_effective.py` | `test_linked_lint_codes_name_the_rules_skill` | `{"rule": "pytest", "skill": "python-testing", ...}` |
| | `test_linked_lint_codes_have_no_skill_for_an_always_rule` | no `skill` key |
| `tests/hook_runtime/test_ruff_bucket_labels.py` (new) | `test_rule_label_names_the_skill`, `test_rule_label_without_skill_keeps_the_old_prefix` (regression: stale config), `test_rule_suffix_names_rule_and_skill_without_nesting` | exact strings |
| `tests/hooks/test_error_handling_lint_feedback.py:40,144`, `test_typing_lint_feedback.py:36`, `test_pytest_conventions_feedback.py:35`, `test_docstring_nonregression.py:208`, `test_ruff_feedback.py:446-448` | prefix constants | `rule python-error-handling (skill python-coding): `, `rule pytest (skill python-testing): `, suffix `(rule python-error-handling, skill python-coding)` |
| `tests/unit/test_types_hook.py` | `test_summary_longer_than_120_chars_is_a_schema_error`, `test_multiline_summary_is_a_schema_error`, `test_templated_summary_is_a_schema_error` | `HookSchemaError` names `summary`, the value and the expected shape |
| `tests/unit/test_types_hook_roundtrip.py` | `test_summary_round_trips_and_an_empty_one_is_dropped` | |
| `tests/unit/test_hook_policy_advisory.py` (new) | `test_guardrail_summary_prefers_the_summary`, `test_guardrail_summary_falls_back_to_the_first_sentence`, `test_guardrail_summary_cuts_a_long_sentence_at_a_word_boundary`, `test_guardrails_section_sorts_lines_by_hook_id` | |
| `tests/hooks/test_hook_summaries.py` (new, catalog) | `test_every_core_hook_with_a_body_declares_a_summary`, `test_stop_ci_parity_gate_summary_names_the_checks` | the summary contains `ruff check .`, `ruff format --check .`, `type checker`, `tests` (D17) |
| `tests/adapters/test_agents_md.py:338-380` | rewrite `test_guardrails_section_after_rules_sorted_by_id_with_enforcement_line` as `test_guardrails_section_is_one_line_per_hook_sorted_by_id`; add `test_no_guardrail_line_without_an_advisory`; keep `test_byte_identical_when_no_hooks` | |
| `tests/unit/test_hook_policy_guardrails_skill.py` (new) | `test_split_removes_the_guardrails_skill_from_dispatch`, `test_compose_is_none_without_an_advisory`, `test_compose_is_none_without_the_authored_skill`, `test_compose_appends_sections_sorted_by_hook_id_with_enforcement_lines` | |
| `tests/adapters/test_guardrails_skill_targets.py` (new) | `test_opencode_and_shared_skills_write_the_skill_when_any_advisory_exists`, `test_claude_code_skips_the_skill_when_every_hook_is_native`, `test_claude_code_writes_skill_and_line_for_a_hook_it_cannot_run`, `test_continue_guardrail_rule_files_are_byte_identical` (regression), `test_agent_harness_never_writes_the_skill` | |
| `tests/adapters/test_claude_code_hooks.py` | `test_runs_natively_agrees_with_claude_hooks_add` | |
| `tests/cli/test_sync_hook_outputs.py:178,419-421` | counts `30 enabled`, `claude_code: 30 enforced`; add `test_sync_writes_guardrails_skill_to_opencode_and_agents_roots_only`, `test_sync_with_hooks_off_writes_no_guardrails_skill_and_no_section` | |
| `tests/integration/test_context_budget.py` (PR 2) | remove the `xfail(strict=True)` marker from `test_agents_md_within_1500_words`; the reference probe already runs hooks on | whole `AGENTS.md` ≤ 1,500 words |
| `tests/integration/test_core_skills.py` (PR 2) | `EXPECTED_PLAIN_CORE_SKILLS = {"playbook-guardrails"}`: the inventory, identity, plain-markdown, 500-line and `agent_skill_issues` tests also run over it; it has no `playbook:` block and its description contains one ` Use when ` | |
| `tests/unit/test_sources_filesystem_bundled.py` | `test_engine_skills_come_from_catalog_core` expects 5 engine skills | |
| `tests/unit/test_guard_config_skills.py` (new) | `test_skill_glob_rows_group_member_globs_by_skill`, `test_rules_without_skill_or_globs_add_nothing`, `test_rows_are_sorted_and_globs_deduplicated` | |
| `tests/unit/test_guard_config.py` | `test_skill_nudge_config_is_derived_and_replaces_a_layer_value` | |
| `tests/hooks/test_skill_nudge.py` (new) | `test_hook_md_matches_its_pack_row_and_handler` (tier, events, decisions, `on_error`, supports, no body, H1-H21 clean with no warning); `test_first_edit_of_a_python_file_names_python_coding`; `test_second_edit_in_the_same_session_is_silent`; `test_test_file_names_testing_and_coding_once_each`; `test_new_session_nudges_again`; `test_file_matching_no_skill_is_silent`; `test_out_of_repo_path_is_silent`; `test_stateless_store_is_silent` (regression: no repeat per edit); `test_malformed_skills_table_is_silent`; `test_line_is_at_most_200_characters`; `test_nudge_line_comes_before_lint_feedback`; `test_claude_and_opencode_payloads_carry_the_nudge` (golden payloads under `tests/fixtures/hook_payloads/{claude_code,opencode}/post_tool_use/`) | |
| `tests/hook_runtime/test_import_budget.py` | `test_skill_nudge_loads_nothing_forbidden_on_a_python_edit` | |
| `tests/unit/test_docs_readme_hooks.py:135` | passes once README lists `skill-nudge` (no code change) | |
| `tests/cli/test_check_hooks.py` | `_ENGINE_PACK` (`:67-109`) gains `"skill-nudge"` in sorted order (after `session-start-playbook-briefing`); `test_hooks_block_labels_per_adapter` expects `"  Hooks (30 on / 45 total):"` (today `29 on / 44 total`, `:140`) and the line `"    [✓] skill-nudge (agents_md: —, claude_code: enforced, continue: —, opencode: enforced)"` (no body, so no advisory label); `test_hooks_block_when_the_table_is_absent` and `test_hooks_block_when_hooks_are_switched_off_or_unreadable` re-check the `_ENGINE_PACK[:17]` / `[17:]` slices (`:246-248`) around the inserted id | exact lines |
| `tests/cli/test_sync_hook_trust.py:196-226` | `test_handler_approval_mirrors_the_runtime_record`: the exact builtin-id set gains `"skill-nudge"`; `handler_approval` is `None` for it like every builtin | |

### 8.9 Docs

| Doc | Change |
| --- | --- |
| SPEC §6.6.2 HookFrontmatter listing (`SPEC.md:963-1116`) | add `summary: str` (pinned by `tests/unit/test_docs_lifecycle_hooks_spec.py:214`) |
| SPEC §6.6.7 (`:1149+`; advisory routing at `:1194`) | advisories become one line in AGENTS.md (and the Claude rules file for hooks Claude cannot run) plus the skill; `summary` and its fallback |
| SPEC §9.7 `hook_advisory` row (`:1550`) | it still feeds Continue, agent_harness and the skill sections, no longer AGENTS.md |
| SPEC §10.1 (`:1565-1682`) | `writes_guardrails_skill` in the ABC code block (pinned by `test_docs_lifecycle_hooks_cli.py:98`) |
| SPEC §10.3.1 (`:1758-1785`) | degraded hooks: one line plus the skill |
| SPEC §10.4 (`:1820-1833`) | the new Guardrails section text and the skill |
| SPEC §12.2 (`:2257`) | the `✓ Hooks:` example line |
| `specs/prK-hook-pack.md:838-847` | the "Line prefix" column and the bucket-1 suffix sentence; the "already in context via CLAUDE.md/AGENTS.md" clause becomes "in the named skill" |
| `README.md:714-725` (Edit feedback table) | new row: `skill-nudge`, tier `default`, enforced on "Claude Code, OpenCode", "Name the skill that covers a file the first time a session edits it." (the row format `tests/unit/test_docs_readme_hooks.py:135` checks) |
| `README.md:759` | AGENTS.md readers: one line per guardrail, full text in skill `playbook-guardrails` |
| `catalog/README.md:109-123` | `summary` in step 2; step 3 says the body is the skill section and the summary is the AGENTS.md line |
| `MIGRATION.md` | in the shared `## v0.21` section, subsection "Guardrails and lint feedback point at skills": the AGENTS.md change, the new skill dirs, the `30 enabled` count, the lint prefix, `skill-nudge` and how to disable it, and one sentence on OpenCode v2 (R4-6): its shim is an inert `setup()` stub (SPEC §10.6.2), so there the nudge and the `rule X (skill Y)` lint feedback are inactive and only the `AGENTS.md` guardrail lines and the Where section apply, until the shim is ported (SPEC OQ-11) |
| `CONTEXT.md` | no change: **Guardrail** and **Skill nudge** already match |

### 8.10 Acceptance criteria

1. The CI gate passes cache-free.
2. In the probe with default hooks: `AGENTS.md` ≤ 1,500 words (the D5 test, hooks on); its Guardrails section has one line per on hook with an advisory and no `###` heading; `stop-ci-parity-gate`'s line names the four checks.
3. `.opencode/skills/playbook-guardrails/SKILL.md` and `.agents/skills/playbook-guardrails/SKILL.md` exist and are byte-identical; `.claude/skills/playbook-guardrails/` does not exist; `.continue/rules/30-guardrail-*.md` are byte-identical to before.
4. With `[hooks] enabled = false`: no Guardrails section, no `playbook-guardrails` directory.
5. Editing `src/app.py` with a bare `except:` yields `rule python-error-handling (skill python-coding): …`.
6. In one session: the first edit of `src/app.py` yields `Conventions for this file: skill python-coding.` (plus `ml-data` and `python-tooling` in the probe); a second edit yields none of them; the first edit of `tests/test_app.py` then yields only `skill python-testing`.
7. `playbook validate` passes on the engine checkout with no hook warning; `playbook check` lists `skill-nudge` as enforced on Claude Code and OpenCode (v1 shim). This holds until PR 8; after PR 8 adds `notebook_edit`, the OpenCode cell reads `degraded` (section 12.2), and on OpenCode v2 the shim is inert (R4-6).

### 8.11 Decisions taken in this PR

| # | Decision | One-line rationale |
| --- | --- | --- |
| P4-1 | Skill id reaches lint feedback inside `config["lint_codes"]` | same source and same sync step as the codes; no extra key to keep in sync |
| P4-2 | Bucket-1 suffix `(rule X, skill Y)` | avoids nested parentheses |
| P4-3 | Optional `summary` (≤ 120 chars, H1 shape check) with a first-sentence fallback; required for core by a catalog test | authored lines fit the D5 budget and keep meaning; third-party hooks keep working |
| P4-4 | `playbook-guardrails` is one generated `SKILL.md`, no references | about 2k tokens, loaded rarely; no generated-reference plumbing for a non-rule source |
| P4-5 | Written by opencode and shared_skills; by claude_code only for hooks it cannot run | D6: Claude runs the core pack natively; no listing cost there |
| P4-6 | Skill-nudge globs travel through the existing derived-config table | same mechanism as the toolchain hints; consumers cannot override |
| P4-7 | Once-per-skill dedupe through `dedupe_key` and `combine` | reuses the session `once` list; a capped line never burns its key |
| P4-8 | Silent when the state root is unusable | without dedupe the line would repeat on every edit |
| P4-9 | `priority: 30`, `tools: [edit, write]` | first context item of the event; no settings.json change while every member glob is `*.py` |
| P4-10 | The resync hook keeps naming the rule | the rule is in no skill until the sync it asks for |
| P4-11 | A hook Claude Code cannot run (an overlay hook without `claude_code` in `supports`, or with events Claude cannot reach) keeps one line in the Claude rules file and the full text in `.claude/skills/playbook-guardrails/` | a reading of D6 ("as today": such a hook reaches the rules file today, as a full section) over D17's letter ("without guardrails"); dropping the line would leave Claude Code with no always-loaded trace of a guardrail nothing enforces there. The core pack runs natively, so the probe's rules file has no Guardrails section either way. Open question Q3 asks the user to confirm |

### 8.12 Module budget

Sizes after PR 2 (section 6.4.13), then after this PR:

| Module | After PR 2 | After PR 4 | Note |
| --- | --- | --- | --- |
| `hook_policy/guardrails_skill.py` | new | ~90 | split and compose |
| `_guard_config_skills.py` | new | ~50 | `skill_glob_rows` |
| `hook_runtime/handlers/skill_nudge.py` | new | ~110 | builtin and glob table |
| `_hook_frontmatter.py` | ~95 | ~100 | `summary` field, read and drop (why PR 2 moves the class out of `types.py`) |
| `_hook_schema.py` | 372 | ~376 | `TOP_KEYS` entry, `FieldReader.guardrail_summary` |
| `types.py` | ~412 | ~412 | unchanged |
| `hook_policy/advisory.py` | 114 | ~150 | summary, line and section helpers |
| `hook_policy/resolved.py` | 243 | ~250 | `guardrail_text` |
| `hook_policy/lint_codes.py` | 76 | ~82 | `linked_lint_config` gains `skill_id` |
| `hook_runtime/handlers/_ruff_buckets.py` | 414 | ~430 | `rule_label`, `rule_suffix`, `_skill_of` |
| `adapters/agents_md_adapter.py` | ~170 | ~165 | the advisory block becomes one line |
| `adapters/claude_code_adapter.py` | ~392 | ~405 | buffered lines, `writes_guardrails_skill` |
| `adapters/_claude_hooks.py` | 216 | ~222 | `runs_natively` |
| `adapters/base.py` | ~285 | ~292 | `writes_guardrails_skill` |
| `guard_config.py` | 416 | ~420 | `skill_globs` input |
| `commands/_sync_hooks.py` | 461 | ~470 | `dispatch` and `write_runtime_outputs` parameters |
| `commands/_sync_render.py` | ~240 | ~246 | `guardrails_skill` field |
| `commands/_sync_lockfile.py` | ~310 | ~318 | `HookDispatch.guardrails_skill`, `_skills_for` |
| `hook_runtime/registry.py` | 436 | 437 | one registration line |
| `commands/sync.py` | 506 | ~508 | pre-existing overrun; two keyword arguments in `_render_into` (`:132-145`), no new logic |

## 9. PR 5 — python-coding distilled content, and the conventions shared by PRs 5-8

Implements D7, D8 and D23 for `python-coding`; sections 9.1 to 9.13 also hold everything PRs 5-8
share (D9 applies in PR 8). Sections 9.14 and 9.15 are PR 5 itself. Title (Conventional Commits):
`feat(catalog): distill python-best-practices into the python-coding skill`.

### 9.1 Goal of PRs 5-8

Fill the four core skills that PR 2 creates with the ideas of the upstream python-best-practices
collection (MIT, Copyright (c) 2026 Ludo Technologies LLC, commit
`bf64c51d2f4c8255f126c98359bdbcd5e2587b92` of 2026-08-31), distilled as D7 requires: every idea is
rewritten from scratch in the catalog's rule format, and the source is credited in plain text in
`catalog/core/ATTRIBUTIONS.md` only.

Where an upstream topic overlaps an existing core rule, its ideas are folded into that rule in our
wording (D8). New topics become 13 new scoped rules:

| PR | Skill | New rules | Existing rules edited | Engine or hook change |
| --- | --- | --- | --- | --- |
| 5 | `python-coding` | 3 | 6 (python-error-handling, python-typing, python-docstrings, python-dependency-injection, python-data-shapes, python-idioms) | none (ATTRIBUTIONS entry, marker regex) |
| 6 | `python-testing` | 2 | 1 (`pytest`), plus one line of the `generate-tests` prompt | none |
| 7 | `python-tooling` | 4 | 0 | `applies_if: package_manager`; `validate` checks each `applies_if` key on its own |
| 8 | `ml-data` | 4 | 0 | `skill-nudge` matcher gains `notebook_edit` (catalog `HOOK.md` only) |

The only engine code changes in the four PRs are in PR 7. Everything else is catalog content,
tests and docs.

### 9.2 Scope of PRs 5-8

**In scope**

- One mapping decision for every one of the 58 upstream rule files plus
  `skills/coding-standards/tooling.md` (section 9.5).
- 13 new scoped rules under `catalog/core/rules/`, each naming its skill with
  `skill:` (D2) (section 9.6).
- Folding upstream ideas into 4 existing core rules (python-error-handling,
  python-typing, python-docstrings, python-dependency-injection), into
  PR 2's python-data-shapes and python-idioms, and into pytest (section 9.8).
- No ruff code is added to any rule's `lint_codes` (D23), so no lint-feedback
  hook reports anything new. Codes that fit an already-linked rule (`RUF012`
  for `python-typing`; `PT012`, `PT014`, `PT017` for `pytest`) are recorded as
  candidates with the rest (section 9.4.3, follow-up F2).
- The `package_manager` `applies_if` key (PR 7), and a fix to `playbook
  validate`, which today stops checking a rule's or prompt's `applies_if` at
  the first key that does not hold (section 11.2).
- The ATTRIBUTIONS entry, the marker-regex addition and their tests (PR 5,
  section 9.9).
- SPEC, README, catalog README and MIGRATION updates (section 9.12).

**Out of scope**

- New hooks. A new lint-feedback hook for the new rules' candidate ruff codes
  needs a new `BUCKETS` row (`hook_runtime/handlers/_ruff_buckets.py:200-207`)
  and a new `HOOK.md`; D23 defers them to a post-pilot follow-up.
- Prompt changes. No prompt's `includes_rules` changes, because the eval runner
  inlines those rule bodies into graded prompts and the Phase-0 eval freeze
  holds. D15's "load any other listed skill whose description matches" line
  already lets an agent find the new references.
- New eval tasks or eval features (D13).
- Skill-trigger evals (they come after the pilot, D13).
- Any `applies_if` combinator (D9), and any applies_if key other than
  `package_manager`.
- A dispatch-table refactor of `evaluate_predicate`. That function is already
  about 70 lines (`detector.py:341-410`). PR 7 adds one three-line branch and
  keeps the parsing in small helpers. A refactor is unrelated churn for a
  content PR.
- Upstream skill-level files: the four `SKILL.md`, `README.md` and
  `metadata.json` files, and the repo-level README, CONTRIBUTING,
  CODE_OF_CONDUCT and SECURITY files. They are indexes and project metadata,
  not guidance. The upstream `LICENSE` was read only for the attribution.

### 9.3 Dependencies and merge order

- **PR 2 first.** All four PRs need PR 2's `skill:` field, the four core skills, the generated
  index and Covers clause, the D13 static checks and the D5 budget tests on the reference probe.
- **PR 5 merges before PR 6, PR 7 and PR 8.** PR 5 adds the ATTRIBUTIONS entry and the marker
  regex that the other three extend. All four branch from `main` (no stacked PRs, D19). PR 6-8
  can be developed in parallel lanes, but each one rebases on `main` after PR 5 merges and before
  it merges itself. Without that, a distilled rule could ship with no credit. The remaining overlap
  between PR 6, PR 7 and PR 8 is a few appended lines in ATTRIBUTIONS, the SPEC tree, the
  membership tables and `_ENGINE_RULE_COUNT`, which are trivial to resolve.
- **PR 8 also merges after PR 4**, because it edits `catalog/core/hooks/feedback/skill-nudge/HOOK.md`,
  which PR 4 creates (section 13).
- **PR 3 and PR 4 share files with these PRs, not designs.** Either side may merge first; the
  second rebases and merges the text:
  - PR 4 and PR 5-8: `tests/integration/test_core_skills.py` (PR 4 adds
    `EXPECTED_PLAIN_CORE_SKILLS`; PR 5-8 extend `EXPECTED_MEMBERSHIP` and `DISTILLED_RULES`),
    `tests/unit/test_sources_filesystem_bundled.py` (PR 4's engine skill count, PR 5-8's
    `_ENGINE_RULE_COUNT`), and the MIGRATION and SPEC changelog entries. PR 8 also edits PR 4's
    `skill-nudge/HOOK.md` and `tests/cli/test_check_hooks.py` row (above). No PR 5-8 test touches
    a lint-feedback `PREFIX` (D23 adds no code).
  - PR 3 and PR 5: `catalog/README.md` (PR 3 edits `:56-60`, PR 5 the adjacent `:45-54`).
  - PR 3 and PR 6: `catalog/core/prompts/generate-tests.md.j2` (PR 3 deletes `:57-62`, PR 6
    rewords `:35`).
  - PR 3 removes the `is_prompt_context` keyword from `build_environment`. PR 5-8 tests render
    core rules only through `render_core_rule` (section 6.8.10), so that change touches one
    helper.
- **Names PR 2 decides, used here:** the house-style items D17 moves out live in two PR 2 rules,
  `python-data-shapes` and `python-idioms` (section 6.5.2); the membership pins live in
  `tests/integration/test_core_skills.py` (`EXPECTED_MEMBERSHIP`, section 6.8.12); the
  reference-probe facts come from `tests/_budget_probe.reference_probe_facts` (section 6.8.10).

### 9.4 Conventions every distilled rule follows

#### 9.4.1 Frontmatter

Every new rule has `id`, a short `name`, a one-sentence `description`,
`version: 1`, `scope: scoped`, `skill`, `globs`, `priority` and `tags`, plus
`applies_if` where the rule is gated. No new rule carries `lint_codes`
(section 9.4.3).

The `name` is the member's label in its skill's Covers clause and index, so it
is a short topic label that does not repeat the skill's subject (`Asyncio`, not
`Python asyncio`), the convention PR 2 sets for the python-coding members
(section 6.5.1, D21).

#### 9.4.2 Priority from upstream impact (D7)

Priorities stay inside the SPEC §10.2.1 bands (SPEC.md:1702-1713). Within a
band, the offset comes from upstream `impact`:

| impact | offset | band 20 (tooling) | band 50 (language) | band 60 (framework: pytest, Pydantic) | band 70 (domain: ML data) |
| --- | --- | --- | --- | --- | --- |
| CRITICAL | +1 | 21 | 51 | 61 | 71 |
| HIGH | +3 | 23 | 53 | 63 | 73 |
| MEDIUM | +8 | 28 | 58 | 68 | 78 |

- A new rule that merges several upstream files takes the highest impact among
  them.
- An existing rule keeps its priority when ideas are folded into it. Nothing
  is renumbered.
- Equal priorities sort by id, as today.

#### 9.4.3 Ruff codes

- No ruff code is added to any rule's `lint_codes` in PRs 5-8, not even on the
  four rules a lint-feedback hook already links (`python-error-handling`,
  `python-typing`, `pytest`, `python-docstrings`). D23 keeps the distilled
  content's codes out of rule frontmatter, and a code added to a linked rule
  changes what `typing-lint-feedback` or `pytest-conventions-feedback` reports
  in every consumer repo (`hook_policy/effective.py:386-398` feeds
  `lint_codes` straight into the hook config) during the Phase-0 eval freeze.
- Codes that fit a topic are recorded in this spec as *candidates* for the
  post-pilot follow-up F2: on a new rule they need a new hook; on a linked rule
  (`RUF012` for `python-typing`; `PT012`, `PT014`, `PT017` for `pytest`) they
  need only the `lint_codes` line. Two constraints F2 keeps:
  - SPEC §6.1.1 defines `lint_codes` as "the ruff codes a rule-linked lint hook
    reports".
  - `tests/unit/test_rules_lint_codes.py:64-75` pins that exactly the four
    linked rules carry codes, and pins their exact lists, so it also guards
    that PRs 5-8 add none.
- Every code was checked with `.venv/bin/ruff rule <CODE>` and
  `ruff rule --all --output-format json` (ruff 0.17.0). Codes that exist only
  in preview are marked **(p)**. They are never eligible for `lint_codes`,
  because the pinned-ruff drop list keeps them out of `--extend-select`
  (`hook_runtime/_ruff.py:212-213`).

#### 9.4.4 Text

- **Own words.** Authors write from the outlines in sections 9.14, 10.1, 11.1 and 12.1, never from the
  upstream files. Examples use fresh domains (invoices, shipping fees, sensor
  readings), never upstream ones (orders/users/products).
- **No URLs.** Cross-references are plain-text rule ids, never markdown links:
  rendered references sit in a different directory under each harness, and the
  PR-L link gate refuses links that leave the layer.
- **Only ids that exist, with their condition.** A rule body names only rule ids
  that are in core when its PR merges (PRs 5-8 may merge separately, D14). A
  pointer to a rule whose gate differs from the referring rule's says when it
  applies (`fastapi-app-wiring`, when the repo uses FastAPI), because a member
  whose gate fails has no reference in that repo. No CI gate checks this; the
  reviewer does.
- **No upstream names.** No rule mentions the upstream collection, its
  publisher or `pyscn`; the marker regex enforces this (section 9.9).
- **No version-specific claims.** "pandas 3.0 does X" becomes behavior the text
  states without a version. Pydantic text names the Pydantic 2 API explicitly
  (section 15, R5-7).
- **No new dependencies.** No rule tells the agent to add a dependency (pandera,
  pandas-stubs, factory_boy, pytest-randomly, numba). At most it says "propose
  it to the user".
- **Python code blocks must be ruff-format clean.** Only the plugins and
  eval-task fixtures are excluded from ruff (`pyproject.toml:142-147`), so
  `ruff format --check .` formats the fenced Python in `catalog/core/rules/*.md`.
  "Avoid" examples must still be valid, formatted Python. `.md.j2` files are
  not formatted by ruff, but follow the same style.

#### 9.4.5 Size

- Target 300–650 rendered words per rule, like the existing rules.
- Hard bounds, enforced by a test (section 9.15, PR 5): at most 100 rendered lines
  and at most 750 words, rendered with the reference-probe facts. 100 lines is
  the Agent Skills threshold above which a reference needs a table of contents.

#### 9.4.6 Jinja

A rule is `.md.j2` only when a section depends on facts, such as
`has_ml_dep("pandas")` or `has_framework("pytest-asyncio")`. Rules render with
`StrictUndefined` (renderer.py:138-145), so a branch reads only facts the
renderer always sets, or guards with `is defined`.

#### 9.4.7 One owner per topic

When an upstream idea already has an owner rule, the new text goes into that
owner and every other rule points to it by id. Where an owner changes, the old
text is removed in the same PR, and a test pins the single owner
(`test_moved_guidance_has_one_owner`).

### 9.5 Upstream mapping (59 rows)

Paths are relative to the upstream `skills/` directory. The
`_sections.md` and `_template.md` files in each of the four `rules/`
directories (8 files) are skipped: they are section indexes and authoring
templates with no guidance.

Legend for the `lint_codes` column:

- **Bold**: a candidate that fits an already-linked rule (the rule named in the
  cell); deferred to F2 like every candidate, not added (D23, section 9.4.3).
- "kept": already present.
- "cand.": a candidate for a future hook, not added (section 9.4.3).
- **(p)**: preview-only in ruff 0.17.0.
- An em dash: no fitting ruff rule.

In the `applies_if` column, "own gate" means the target rule keeps the gate it
already has.

| # | Upstream file | Impact | Action | Skill | applies_if | Prio | lint_codes | Conflict / note (D8 and existing rules) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | coding-standards/rules/async-context-manager.md | HIGH | merge → `python-context-managers`, no edit: context-managers.md:17-28 already requires `async with`, `@asynccontextmanager` and `AsyncExitStack` | python-coding | — | 56 (kept) | — | none |
| 2 | coding-standards/rules/async-create-task.md | HIGH | new → `python-async` | python-coding | `python_version: ">=3.11"` | 53 | RUF006 cand. | Upstream keeps task references in a module-level set. pure-core.md:28-31 and dependency-injection.md:23-27 forbid module-level shared state, so the tasks are held by an owner object that the composition root builds |
| 3 | coding-standards/rules/async-gather.md | HIGH | new → `python-async` | python-coding | `">=3.11"` | 53 | — | Failed results are logged with `exc_info` only at a per-item boundary (error-handling.md:43-47); cancellation is re-raised |
| 4 | coding-standards/rules/async-semaphore.md | HIGH | new → `python-async` | python-coding | `">=3.11"` | 53 | — | Upstream's per-loop `WeakKeyDictionary` cache becomes "create it on the loop that uses it" |
| 5 | coding-standards/rules/design-dependency-injection.md | HIGH | merge → `python-dependency-injection`; the ideas are already at dependency-injection.md:17-27, no new text | python-coding | — | 40 | — | D8: upstream tests with `Mock(spec=…)`, which becomes named fakes (dependency-injection.md:34-36). The DI-container suggestion is dropped |
| 6 | coding-standards/rules/design-early-return.md | HIGH | merge → `python-idioms` (PR 2): its early-return bullet gains the guard-clause details | python-coding | — | 58 | RET505, SIM102 cand.; PLR1702 (p) | "Order guards by likelihood for speed" is dropped |
| 7 | coding-standards/rules/design-no-global-singleton.md | HIGH | merge → `python-dependency-injection` | python-coding | — | 40 | PLW0603 cand. | none. The opt-in python_design plugin judges singletons by fit; that tension already exists and is unchanged |
| 8 | coding-standards/rules/design-philosophy.md | HIGH | new → `python-classes-and-protocols` ("Abstractions earn their place") | python-coding | — | 53 | — | none |
| 9 | coding-standards/rules/design-pure-functions.md | HIGH | merge → `python-pure-core`, no edit: pure-core.md:17-36 already covers it | python-coding | — | 42 | DTZ005 cand. | none |
| 10 | coding-standards/rules/design-single-responsibility.md | HIGH | new → `python-classes-and-protocols` | python-coding | — | 53 | — | The password-hashing aside is dropped (a security topic, not SRP) |
| 11 | coding-standards/rules/doc-docstring.md | HIGH | merge → `python-docstrings` | python-coding | — | 56 | D100–D107 kept; D417 not added | D8: Google `Args:`/`Returns:`/`Raises:` sections allowed, not required |
| 12 | coding-standards/rules/doc-type-hints.md | HIGH | merge → `python-typing` | python-coding | own gate `">=3.11"` | 50 | ANN001, ANN201, ANN401 kept | Upstream says "public APIs only"; D17 says every signature. Ours wins |
| 13 | coding-standards/rules/error-no-silent-exceptions.md | CRITICAL | merge → `python-error-handling` | python-coding | — | 55 | BLE001, S110, S112 kept | Upstream wants `check-typed-exception = true`; D8 mandates no config |
| 14 | coding-standards/rules/oop-composition-over-inheritance.md | MEDIUM | new → `python-classes-and-protocols`, which also takes the composition and framework-base-class bullets of `python-idioms` "Functions and classes" (PR 5 removes them there) | python-coding | — | 53 | — | none |
| 15 | coding-standards/rules/oop-dataclass.md | MEDIUM | merge → `python-data-shapes` "Records" (`slots=True` for many small instances; frozen values are already there); mutable class defaults → `python-typing` | python-coding | — | 44 / 50 | **RUF012** cand. (fits `python-typing`); RUF008, RUF009 cand. | The `attrs` suggestion is dropped. Money as `Decimal` is already in the always rule (D17) |
| 16 | coding-standards/rules/oop-property.md | MEDIUM | new → `python-classes-and-protocols` ("Attributes, then properties"); the derived-value `@property` bullet stays in `python-data-shapes`, which the new rule points to | python-coding | — | 53 | B019 cand. | none |
| 17 | coding-standards/rules/oop-protocol.md | MEDIUM | new → `python-classes-and-protocols` | python-coding | — | 53 | B024, B027 cand. | none: it matches the DI rule and python_design |
| 18 | coding-standards/rules/perf-dict-get.md | CRITICAL | new → `python-performance-idioms` | python-coding | — | 51 | SIM401 cand. | **Conflict.** A chained `.get(k, {})` silently defaults required data. That contradicts error-handling.md:51 ("validate where data enters") and D17's typed records, so `.get` is only for keys that are optional by design |
| 19 | coding-standards/rules/perf-generator-expression.md | CRITICAL | new → `python-performance-idioms` | python-coding | — | 51 | C419 cand. | none |
| 20 | coding-standards/rules/perf-list-comprehension.md | CRITICAL | new → `python-performance-idioms` | python-coding | — | 51 | PERF401, PERF403, C416 cand.; FURB113 (p) | Speed multipliers are dropped |
| 21 | coding-standards/rules/perf-set-lookup.md | CRITICAL | new → `python-performance-idioms` | python-coding | — | 51 | PLR6201 (p) | `list(set(x))` loses order; we say `dict.fromkeys` |
| 22 | coding-standards/rules/perf-str-join.md | CRITICAL | new → `python-performance-idioms` | python-coding | — | 51 | — | The pathlib note is dropped (the always rule owns paths) |
| 23 | coding-standards/rules/solid-isp.md | HIGH | new → `python-classes-and-protocols` | python-coding | — | 53 | — | none |
| 24 | coding-standards/rules/solid-lsp.md | HIGH | new → `python-classes-and-protocols` | python-coding | — | 53 | — | none |
| 25 | coding-standards/rules/solid-ocp.md | HIGH | new → `python-classes-and-protocols` | python-coding | — | 53 | — | none |
| 26 | coding-standards/rules/validation-pydantic.md | HIGH | new → `pydantic-boundaries` | python-tooling | `has_framework: ["pydantic"]` | 63 | — | D8: kept. The dataclass-or-Pydantic split stays in the always rule (D17) and is not repeated |
| 27 | coding-standards/tooling.md | HIGH | drop as a file; its ruff and mypy advice lands in `python-static-checks` (rows 42, 46) | python-tooling | — | — | — | D8: `pyscn` dropped; the fixed `select` and `strict` values are not mandated |
| 28 | testing/rules/fixture-conftest.md | HIGH | new → `pytest-fixtures` | python-testing | `has_framework: ["pytest"]` | 63 | — | none |
| 29 | testing/rules/fixture-factory.md | HIGH | new → `pytest-fixtures` | python-testing | same | 63 | — | factory_boy is not recommended (a new dependency) |
| 30 | testing/rules/fixture-scope.md | HIGH | new → `pytest-fixtures` | python-testing | same | 63 | PT003 cand. | pytest-randomly is not recommended |
| 31 | testing/rules/mock-autospec.md | CRITICAL | new → `pytest-test-doubles` | python-testing | `has_framework: ["pytest"]` | 61 | — | **D8: named fakes are the default; autospec only at thin third-party seams.** `mocker` (pytest-mock) is not assumed |
| 32 | testing/rules/mock-boundaries.md | CRITICAL | new → `pytest-test-doubles` | python-testing | same | 61 | — | **Conflict.** freezegun for clocks contradicts pure-core.md:33-36 (freeze time only to characterize legacy code). Ours wins |
| 33 | testing/rules/mock-monkeypatch.md | HIGH | new → `pytest-test-doubles`, which also takes the monkeypatch clause at pytest.md.j2:96 | python-testing | same | 61 | — | **Conflict.** "Use `monkeypatch.setattr` to replace functions" contradicts dependency-injection.md:34-36. Kept only for env vars, cwd, dict entries and code that cannot take a parameter yet |
| 34 | testing/rules/param-ids.md | MEDIUM | merge → `pytest` | python-testing | own gate | 60 | PT006 kept | none |
| 35 | testing/rules/param-parametrize.md | MEDIUM | merge → `pytest` | python-testing | own gate | 60 | **PT014** cand. (fits `pytest`) | none |
| 36 | testing/rules/struct-aaa-pattern.md | HIGH | merge → `pytest`, no edit: pytest.md.j2:88-90 already says it | python-testing | own gate | 60 | — | none |
| 37 | testing/rules/struct-no-logic.md | HIGH | merge → `pytest` | python-testing | own gate | 60 | **PT012**, **PT017** cand. (fit `pytest`) | none |
| 38 | testing/rules/struct-one-behavior.md | HIGH | merge → `pytest`, no edit: pytest.md.j2:88-90 | python-testing | own gate | 60 | PT018 kept | The pytest-check plugin is not recommended |
| 39 | testing/rules/struct-test-naming.md | HIGH | merge → `pytest` (one clause) | python-testing | own gate | 60 | — | Upstream `test_<condition>_<expected>` and our `test_<unit>_<scenario>` (pytest.md.j2:24) are compatible. Ours stays, and the scenario names the condition and the outcome |
| 40 | tooling/rules/analysis-pyscn.md | HIGH | drop | — | — | — | — | D8: dropped. It is the publisher's own analyzer plus an MCP install step. `pyscn` joins the marker regex |
| 41 | tooling/rules/fmt-ruff.md | HIGH | new → `python-static-checks` | python-tooling | — | 21 | — | D8: format and isort settings are only examples. Import grouping stays in `python-idioms` |
| 42 | tooling/rules/lint-ruff.md | CRITICAL | new → `python-static-checks` | python-tooling | — | 21 | PGH004, RUF100 cand. | D8: the `select` list is an example, not a mandate |
| 43 | tooling/rules/pkg-pyproject.md | MEDIUM | merge → `python-uv-workflow` (dependency declaration only); the rest dropped | python-tooling | `package_manager: uv` | 28 | — | D8: hatchling dropped. PEP 621 metadata boilerplate dropped (model-default knowledge) |
| 44 | tooling/rules/pkg-uv.md | MEDIUM | new → `python-uv-workflow` | python-tooling | `package_manager: uv` | 28 | — | The curl-pipe-to-shell install is dropped (a URL and a remote script) |
| 45 | tooling/rules/test-pytest.md | HIGH | new → `pytest-configuration` (configuration only; the fixture and parametrize parts are rows 28–35) | python-tooling | `has_framework: ["pytest"]` | 23 | — | D8: coverage 80, `filterwarnings = error` and `addopts` are only examples. Upstream's blanket `ignore::DeprecationWarning` conflicts with narrow filters and is not adopted |
| 46 | tooling/rules/type-mypy.md | HIGH | new → `python-static-checks` | python-tooling | — | 21 | PGH003 kept (on `python-typing`) | D8: `strict = true` not mandated. **Conflict:** `mypy --install-types` installs outside the lockfile and around dependency-allowlist-guard, so we say "propose stub packages" instead |
| 47 | data-science/rules/dtype-categorical.md | HIGH | new → `ml-dtypes-and-typing` | ml-data | `any_ml_stack: [numpy, pandas, polars]` | 73 | — | pandas-version claims made version-neutral |
| 48 | data-science/rules/dtype-explicit-io.md | HIGH | new → `ml-dtypes-and-typing` | ml-data | same | 73 | — | none |
| 49 | data-science/rules/dtype-numpy-explicit.md | HIGH | new → `ml-dtypes-and-typing` | ml-data | same | 73 | — | none |
| 50 | data-science/rules/mut-loc-not-chained.md | CRITICAL | new → `ml-data-transforms` | ml-data | same | 71 | — (no ruff rule) | none |
| 51 | data-science/rules/mut-no-inplace.md | CRITICAL | new → `ml-data-transforms` | ml-data | same | 71 | PD002 cand. | none |
| 52 | data-science/rules/repro-default-rng.md | HIGH | new → `ml-reproducibility-and-testing` | ml-data | same | 73 | NPY002 cand. | none: it matches pure-core and DI |
| 53 | data-science/rules/schema-pandera.md | HIGH | new → `ml-dtypes-and-typing`, as optional advice | ml-data | same | 73 | — | D8: applies only when the repo already uses pandera; otherwise an explicit column and dtype check |
| 54 | data-science/rules/style-method-chaining.md | MEDIUM | new → `ml-data-transforms` | ml-data | same | 71 | — | none |
| 55 | data-science/rules/style-named-aggregation.md | MEDIUM | new → `ml-data-transforms` | ml-data | same | 71 | — | none |
| 56 | data-science/rules/test-numeric-assertions.md | MEDIUM | new → `ml-reproducibility-and-testing` | ml-data | same | 73 | RUF069 (p) | none |
| 57 | data-science/rules/type-array-annotations.md | MEDIUM | new → `ml-dtypes-and-typing` | ml-data | same | 73 | — | pandas-stubs: propose it, never add it unasked. pandera type hints only where pandera is already used |
| 58 | data-science/rules/vec-no-incremental-growth.md | CRITICAL | new → `ml-vectorization` | ml-data | same | 71 | — | none |
| 59 | data-science/rules/vec-no-python-loops.md | CRITICAL | new → `ml-vectorization` | ml-data | same | 71 | — | numba or Cython only with the user's agreement (a new dependency) |

**Totals**

- 41 rows feed the 13 new rules.
- 15 rows fold into existing rules (rows 1, 5–7, 9, 11–13, 15, 34–39). Five of
  them need no edit (rows 1, 5, 9, 36, 38); row 6 lands in PR 2's
  `python-idioms`, and row 15 in PR 2's `python-data-shapes` plus
  `python-typing`.
- 1 row (43) is merged partly into the new `python-uv-workflow`: only its
  dependency-declaration bits; the rest of it is dropped.
- 2 rows are dropped (rows 27 and 40).
- That accounts for all 59 rows (41 + 15 + 1 + 2).
- Ruff codes added: none (D23). Candidates that fit a linked rule, for F2:
  `RUF012` for `python-typing`; `PT012`, `PT014`, `PT017` for `pytest`.

#### 9.5.1 Conflicts resolved

These upstream items contradict D8 or an existing core rule. Each is resolved
in favor of the settled decision or the existing rule, and none needs the user.

1. Google docstrings (row 11): D8, keep `python-docstrings`.
2. Autospec and `mocker.patch` as the default (row 31), and `Mock(spec=…)` in
   the DI tests (row 5): D8, named fakes are the default.
3. `monkeypatch.setattr` to replace functions (row 33): conflicts with
   dependency-injection.md:34-36, so it is restricted.
4. freezegun for clocks (row 32): conflicts with pure-core.md:33-36. Ours wins.
5. A module-level set of background tasks (row 2): conflicts with
   pure-core.md:28-31 and dependency-injection.md:23-27, so an owner object
   holds the tasks.
6. Chained `dict.get` defaults (row 18): conflicts with error-handling.md:51
   and D17's typed records, so `.get` is for optional keys only.
7. "Type hints for public APIs" only (row 12): D17 says every signature. Ours
   wins.
8. Fixed ruff, mypy, pytest and coverage settings (rows 27, 41, 42, 45, 46):
   D8, examples only. The blanket `ignore::DeprecationWarning` is not adopted.
9. `mypy --install-types` (row 46): bypasses the lockfile and
   dependency-allowlist-guard, so we say "propose stub packages".
10. hatchling (row 43) and pyscn (rows 27, 40): D8 drops both.
11. The curl-pipe install of uv (row 44): a URL and a remote script; dropped.
12. pandera as a HIGH-impact requirement (rows 53, 57): D8, optional advice.

### 9.6 New rules

#### 9.6.1 Inventory

All new rules are `scope: scoped`, `version: 1` and carry no `lint_codes`.
Paths are under `catalog/core/rules/`.

| PR | id | name (Covers label) | File | skill | globs | applies_if | prio | tags | est. words |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 5 | `python-performance-idioms` | Performance idioms | `languages/python/performance-idioms.md` | python-coding | `**/*.py` | — | 51 | [python, performance] | 380 |
| 5 | `python-async` | Asyncio | `languages/python/async.md` | python-coding | `**/*.py` | `python_version: ">=3.11"` | 53 | [python, async, concurrency] | 520 |
| 5 | `python-classes-and-protocols` | Classes and protocols | `languages/python/classes-and-protocols.md` | python-coding | `**/*.py` | — | 53 | [python, design, oop] | 620 |
| 6 | `pytest-test-doubles` | pytest test doubles | `frameworks/pytest-test-doubles.md` | python-testing | `tests/**/*.py`, `**/conftest.py` | `has_framework: ["pytest"]` | 61 | [python, testing, pytest, mocking] | 480 |
| 6 | `pytest-fixtures` | pytest fixtures | `frameworks/pytest-fixtures.md` | python-testing | `tests/**/*.py`, `**/conftest.py` | `has_framework: ["pytest"]` | 63 | [python, testing, pytest, fixtures] | 420 |
| 7 | `python-static-checks` | Static checks | `languages/python/static-checks.md` | python-tooling | `**/*.py`, `pyproject.toml`, `ruff.toml`, `.ruff.toml`, `mypy.ini`, `.mypy.ini` | — | 21 | [python, tooling, ruff, mypy] | 500 |
| 7 | `pytest-configuration` | pytest configuration | `frameworks/pytest-configuration.md` | python-tooling | `pyproject.toml`, `pytest.ini`, `tox.ini`, `setup.cfg`, `**/conftest.py` | `has_framework: ["pytest"]` | 23 | [python, tooling, pytest] | 330 |
| 7 | `python-uv-workflow` | uv workflow | `languages/python/uv-workflow.md` | python-tooling | `pyproject.toml` | `package_manager: uv` | 28 | [python, tooling, uv] | 420 |
| 7 | `pydantic-boundaries` | Pydantic boundaries | `frameworks/pydantic-boundaries.md` | python-tooling | `**/*.py` | `has_framework: ["pydantic"]` | 63 | [python, pydantic, validation] | 450 |
| 8 | `ml-vectorization` | Vectorization | `ml/vectorization.md.j2` | ml-data | `**/*.py`, `**/*.ipynb` | `any_ml_stack: ["numpy", "pandas", "polars"]` | 71 | [ml, numpy, pandas, polars, performance] | 480 |
| 8 | `ml-data-transforms` | Data transforms | `ml/data-transforms.md.j2` | ml-data | same | same | 71 | [ml, pandas, polars, numpy] | 560 |
| 8 | `ml-dtypes-and-typing` | Dtypes and typing | `ml/dtypes-and-typing.md.j2` | ml-data | same | same | 73 | [ml, dtypes, typing] | 620 |
| 8 | `ml-reproducibility-and-testing` | Reproducibility and numeric tests | `ml/reproducibility-and-testing.md.j2` | ml-data | same | same | 73 | [ml, reproducibility, testing] | 520 |

**Choices made here (with reasons)**

- **Ids.** New ids follow the house prefixes `python-*`, `pytest-*` and
  `ml-*`. The one exception is `pydantic-boundaries`, which follows the
  framework-named precedent of `fastapi-app-wiring` and
  `fastapi-error-boundaries`.
- **`python-async` is gated on Python ≥3.11.** Its core advice
  (`asyncio.TaskGroup`, `asyncio.timeout`) needs 3.11, and Python 3.10 reaches
  end of life this month. A string comparison in Jinja would misorder `"3.9"`
  against `"3.11"`, so the gate must be the `evaluate_predicate` version check.
- **`python-static-checks` is ungated.** The engine's own lint-feedback and
  CI-parity hooks run ruff in every repo, and no `applies_if` key reads
  `dev_tools`. The consequence: `python-tooling` now exists in every Python
  repo (section 9.11).
- **The ML rules add `**/*.ipynb` to their globs.** That lets the skill nudge
  (D16) and Continue attach them to notebook edits, which are common in
  ML-heavy repos.
- **`ml-data-transforms`, not `ml-dataframe-transforms`.** The rule also covers
  NumPy views and copies, so it has real content in a NumPy-only repo, which
  D9's gate admits (section 15, R5-2).

#### 9.6.2 References per skill after PR 8

Members in `(priority, id)` order, the order of the Covers clause and the index:

| Skill | Members | Count | Active in the reference probe |
| --- | --- | --- | --- |
| python-coding | python-dependency-injection, python-pure-core, python-data-shapes, python-typing, python-performance-idioms, python-async, python-classes-and-protocols, python-error-handling, python-context-managers, python-docstrings, python-retries-and-timeouts, python-idioms | 12 | 12 |
| python-testing | pytest, pytest-test-doubles, pytest-fixtures | 3 | 3 |
| python-tooling | python-static-checks, pytest-configuration, python-uv-workflow, fastapi-app-wiring, fastapi-error-boundaries, pydantic-boundaries | 6 | 5 (6 with a `uv.lock`) |
| ml-data | ml-serialization-security, ml-data-transforms, ml-vectorization, ml-dtypes-and-typing, ml-reproducibility-and-testing | 5 | 5 |

### 9.7 Frontmatter and rendering example

`catalog/core/rules/languages/python/async.md`:

```yaml
---
id: python-async
name: Asyncio
description: "asyncio: start independent awaits together, give every task an owner, bound fan-out and total wait, never block the loop."
version: 1
scope: scoped
skill: python-coding
globs:
  - "**/*.py"
applies_if:
  python_version: ">=3.11"
priority: 53
tags: [python, async, concurrency]
---
```

The body example uses a fresh domain and is ruff-format clean:

```python
async def load_account_summary(client: BillingClient, customer_id: str) -> AccountSummary:
    async with asyncio.timeout(SUMMARY_TIMEOUT_SECONDS):
        async with asyncio.TaskGroup() as group:
            invoices = group.create_task(client.invoices(customer_id))
            limit = group.create_task(client.credit_limit(customer_id))
    return AccountSummary(invoices=invoices.result(), credit_limit=limit.result())
```

**Rendered output**

- **Claude Code, OpenCode, `.agents`.** One reference inside the
  `python-coding` skill (PR 2's layout), listed in the generated index, with
  `Asyncio` in the Covers clause.
- **Continue**, only when enabled (D11): `.continue/rules/53-python-async.md`,
  rendered by renderer.py:298-318:

```markdown
<!-- sentinel line -->
---
name: Asyncio
description: 'asyncio: start independent awaits together, give every task an owner, bound fan-out and total wait, never block the loop.'
alwaysApply: false
globs:
- '**/*.py'
---
# Python asyncio
...
```

The ML rules are `.md.j2` files with per-library sections, for example:

```text
{% if has_ml_dep("pandas") %}
## pandas
- Write with one indexer: `.loc[rows, cols] = value` (`.iloc` for positions) ...
{% endif %}
{% if has_ml_dep("polars") %}
## polars
- Build columns with expressions in `with_columns` / `select` ...
{% endif %}
```

### 9.8 Edits to existing core rules

Each existing rule keeps its id, gate and priority.

| Rule (PR) | Change | Words |
| --- | --- | --- |
| `python-error-handling` (5) | "What to catch" (error-handling.md:19-23): one bullet saying cancellation and process-control exceptions (`asyncio.CancelledError`, `KeyboardInterrupt`, `SystemExit`) propagate, and that a boundary needing cleanup re-raises them. "Across layers" (:43-61): one bullet saying an intentional fallback is documented, observable (a warning log naming the cause) and limited to named exceptions; never a plausible default for an unexpected failure | +60, about 690 rendered, 83 lines |
| `python-typing` (5) | "`Any` is a fallback" (typing.md.j2:51-54): give identifiers that must not mix their own type (`NewType`), or a value object when they need validation. "Optional types" (:56-71): a mutable class-level default on a plain class is shared by every instance, so initialize it in `__init__`, annotate `ClassVar[...]` when sharing is intended, or use an immutable default. `lint_codes` is unchanged (D23); `RUF012`, which ruff 0.17.0 does not raise on Pydantic models (verified), is an F2 candidate | +60, about 460 |
| `python-docstrings` (5) | "Layout" (docstrings.md:19-23): Google-style `Args:`/`Returns:`/`Raises:` sections are welcome but not required, while the intent line and the usage example are required (D8). Don't restate annotated types in prose; say what a value means, its units and its limits. Update the docstring in the same change that alters behavior, parameters or raised errors | +45, about 220 |
| `python-dependency-injection` (5) | "One composition root" (dependency-injection.md:23-27): no lazy `get_x()` accessor that fills a module global, and no module-level client instance used as a service locator. A shared pool, session or HTTP client is built in the composition root or lifespan and injected. Process-wide items that are fine: logging configured once at startup, read-only settings loaded in `main`, and the framework's app object | +60, about 465 |
| `python-pure-core` (5) | no edit (row 9) | 0 |
| `python-context-managers` (5) | no edit (row 1) | 0 |
| `python-idioms` (PR 2's, edited in PR 5) | Move the "Functions and classes" bullets on composition over inheritance and on framework base classes to `python-classes-and-protocols`; the flag-split bullet stays, and the description drops "prefer composition". Extend the early-return bullet ("Small things reviewers flag"): one condition per guard, `continue` for skips in loops, and a named predicate function for a compound condition | net about −40 |
| `python-data-shapes` (PR 2's, edited in PR 5) | "Records": a dataclass with `slots=True` for many small instances (row 15); the derived-value `@property` bullet stays here, and `python-classes-and-protocols` points to it | about +15 |
| `pytest` (6) | Move "Fixtures" (pytest.md.j2:50-56) to `pytest-fixtures`. Move the monkeypatch clause (:96) to `pytest-test-doubles`. Parametrize (:26-48): explicit `pytest.param(..., id=...)` for non-scalar values (scalars auto-id fine); parametrize expected outcomes by passing `pytest.raises(...)` or `contextlib.nullcontext()` as a parameter; stacked decorators multiply the cases. One thing per test (:88-90): `pytest.raises(Err, match=...)` wraps only the Act statement; never `try`/`except` plus a flag; no `if` or `for` in a test body. Layout (:24): the scenario half names the condition and the expected outcome (`test_parse_rejects_empty_input` already does); a plain class may group related scenarios for naming. `lint_codes` is unchanged (D23); `PT012`, `PT014` and `PT017` are F2 candidates | about 586 → 600 rendered; 98 → ≤ 96 lines |

No upstream idea touches `python-retries-and-timeouts`, `fastapi-app-wiring`,
`fastapi-error-boundaries` or `ml-serialization-security`.

### 9.9 Attribution and self-contained marker (PR 5)

#### 9.9.1 `catalog/core/ATTRIBUTIONS.md`

Append a second entry in the existing format: source and version, license,
copyright, the artifacts distilled, and a "written fresh" statement. PR 5 writes
the entry with its own ids, and PR 6, PR 7 and PR 8 each append theirs. The final
state after PR 8:

```markdown
## Python best-practices guidance

Source: the "python-best-practices" agent skills collection by Ludo
Technologies LLC (repository ludo-technologies/python-best-practices), commit
bf64c51d2f4c8255f126c98359bdbcd5e2587b92 of 2026-08-31.
License: MIT License. Copyright (c) 2026 Ludo Technologies LLC.

The following artifacts distill ideas from that collection:

- Rules: python-performance-idioms, python-async,
  python-classes-and-protocols, pytest-test-doubles, pytest-fixtures,
  python-static-checks, pytest-configuration, python-uv-workflow,
  pydantic-boundaries, ml-vectorization, ml-data-transforms,
  ml-dtypes-and-typing, ml-reproducibility-and-testing.
- Additions to existing artifacts: the python-error-handling, python-typing,
  python-docstrings, python-dependency-injection, python-data-shapes,
  python-idioms and pytest rules.

The collection's impact ratings informed each rule's priority. Its tool
recommendations that the engine does not adopt (a code-analysis tool from the
same publisher, a build backend, and fixed linter, type-checker and coverage
settings) were left out.

All of this text was written fresh for this engine. No sentences, examples or
code from the collection are copied; only the underlying ideas are reused,
restated in the engine's own words and adapted to its rule format.
```

The entry contains no URL. The repository slug has no dot-TLD, so `_URL_RE`'s
bare-domain branch does not fire (verified).

PR 5 also adds `python-classes-and-protocols` to the "Rules:" list of the first
(clean-architecture) entry, because the framework-base-class bullet it takes
over from `python-idioms` came from that distillation (section 6.5.7).

#### 9.9.2 Marker regex (tests/integration/test_resources_self_contained.py:102-105)

```python
_PLUGIN_MARKER_RE = re.compile(
    r"(?i)python[\s_-]*clean[\s_-]*architecture|\barjan|\bmk[\s_-]*toronto"
    r"|software[\s_-]*designer[\s_-]*mindset|claude_plugin_root|\.claude/plugins"
    r"|python[\s_-]*best[\s_-]*practices|\bludo[\s_-]*technologies|\bpyscn\b"
)
```

- The comment above it gains: "and the python-best-practices collection that
  core distills (its name, its publisher, and the publisher's analyzer, which
  D8 drops)".
- The three new alternatives have zero hits today in every scanned tree
  (`catalog/core` without ATTRIBUTIONS, `catalog/plugins/python_design`, and the
  pre-commit template). Vendored `superpowers`, which says "best practices",
  stays exempt.
- Plain "best practices", without "python" before it, does not match.

#### 9.9.3 Tests

- `test_scan_text_flags_leaks` (:360) gains four rows:
  - `("Distilled from python-best-practices.", "plugin-marker", "python-best-practices")`
  - `("Python Best Practices skills", "plugin-marker", "Python Best Practices")`
  - `("Copyright (c) 2026 Ludo Technologies LLC", "plugin-marker", "Ludo Technologies")`
  - `("Run pyscn check before merging.", "plugin-marker", "pyscn")`
- `test_scan_text_passes_clean_text` (:364) gains
  `"Follow these best practices for fixtures.\nThe ludo board game is fine.\n"`.
- New: `test_core_attributions_credit_python_best_practices`. The existing
  parametrized `test_attributions_credit_the_distilled_source` (:311-322) stays
  as it is, because core still credits the first source.

```python
def test_core_attributions_credit_python_best_practices() -> None:
    text = (CORE_ROOT / _ATTRIBUTIONS_NAME).read_text(encoding="utf-8")
    for needle in ("python-best-practices", "Ludo Technologies LLC", _PBP_COMMIT, "MIT"):
        assert needle in text, f"core ATTRIBUTIONS.md must credit {needle!r}"
```

### 9.10 Validation and error messages (PRs 5-8)

| Where | Trigger | Message (offending value + expected shape) |
| --- | --- | --- |
| `evaluate_predicate` (PR 7) | `package_manager: pipenv` or `[uv, UV]` | `predicate 'package_manager' names unknown package manager(s) ['pipenv']; expected any of ['pip', 'pip-tools', 'poetry', 'uv']` |
| `evaluate_predicate` (PR 7) | `package_manager: []`, `3`, `[uv, 3]` or `null` | `predicate 'package_manager' must be one of ['pip', 'pip-tools', 'poetry', 'uv'] or a non-empty list of them; got []` |
| `playbook validate` (PR 7) | either of the above on a rule or prompt, at any position in the predicate | `<path>: applies_if: <message above>` (exit 1); the sync that validate gates refuses too |
| Hook contract (unchanged code) | either of the above on a hook | `applies_if: <message above>` |
| D13 check (PR 2's, now exercised) | a new rule naming a skill that does not exist | V5 (section 6.6) |
| `test_rules_lint_codes.py:64-75` | `lint_codes` added to any rule, distilled or already linked (D23) | the dict-equality diff naming the rule id and the extra code |
| `test_core_rule_shapes.py` | a rule over the bounds | `"{rule_id}: renders {lines} lines / {words} words …; expected at most 100 lines and 750 words …"` |
| Self-contained gate | the upstream name, publisher or `pyscn` in a scanned file | `<rel>:<line>: plugin-marker: '<match>'` (existing renderer) |
| `test_distilled_content_policy.py` | a dropped recommendation | `"{path}: recommends {token!r}, which the D8 import policy drops"` |

### 9.11 Migration, orphans and lockfile (PRs 5-8)

- **No ids are removed or renamed.**
  - No orphans: PR 6 moves text between rule bodies; it moves no files.
  - Lockfile schema unchanged. The first sync after upgrading adds entries for
    the new references in every skill root (`.claude/skills`, `.opencode/skills`
    and `.agents/skills`, as D10 enables) and, with Continue enabled, 13
    `.continue/rules/<prio>-<id>.md` files.
  - `sync --check` reports drift until the consumer re-syncs. That is normal for
    a content upgrade. With `[output] commit = false` there is nothing to commit.
- **Always-loaded context.**
  - Always rules: unchanged by PR 5–8. The skill listing grows with the longer
    Covers clauses (the four core descriptions go from 762 to 957 characters
    on the reference probe), and PR 7 and PR 8 reword the `python-tooling` and
    `ml-data` lines of "Where guidance lives" (section 11.3, section 12.2).
  - Repos without FastAPI: they had no `python-tooling` skill under PR 2 and
    gain one after PR 7, because `python-static-checks` is ungated. That adds
    one "Where guidance lives" line (D17) and about 220 listing characters.
- **Skill nudge (D16).** The new globs add triggers: `pyproject.toml` and ruff
  or mypy config files nudge `python-tooling`; `**/conftest.py` nudges
  `python-testing` and `python-tooling`; `**/*.ipynb` nudges `ml-data`. Each
  still fires at most once per skill per session.
- **Resync hook.**
  - Adding pandas, numpy or polars to pyproject now names up to four new ml
    rules in its "now applicable" line (capped at 8 ids).
  - Adding torch alone names nothing new.
  - Creating `uv.lock` without `uv add` is not a detector input
    (`_detector_inputs.py:63-72`), so `python-uv-workflow` appears at the next
    sync (section 15, R5-8).
- **Overrides.**
  - An overlay or repo-local rule whose id equals a new core id now replaces
    the core rule (the existing layer rule), so `playbook check` shows which one
    won.
  - A repo-local override of `pytest` keeps its own text; the moved fixture and
    double guidance is then only in the two new references.
- **MIGRATION.md.** One subsection, "Distilled python-best-practices content",
  in the `## v0.21 — Skills-first context` section while 0.21 is untagged
  (section 14, H14). It holds a TL;DR row (nothing to do but `playbook sync`)
  and the behavior notes:
  - the `package_manager` key exists;
  - `validate` now reports a malformed `applies_if` key even after a key that
    does not hold, so overlays with hidden typos fail `validate` and `sync`;
  - the override note above;
  - PR 8: `skill-nudge` also fires on Claude Code notebook edits (the managed
    `.claude/settings.json` matcher gains `NotebookEdit`), and `playbook check`
    labels it `degraded` on OpenCode, which has no notebook tool.

### 9.12 Docs to update (PRs 5-8)

| Doc | Section / lines | PR |
| --- | --- | --- |
| SPEC.md | changelog bullet (:11) | 5–8 |
| SPEC.md | tree `catalog/core/rules/` (:239-262), the shipped inventory | 5 (rewrite), 6–8 (append) |
| SPEC.md | §6.3 core-skill member lists (783-809, as PR 2 restructures it) | 5–8 |
| SPEC.md | §6.4 `applies_if` (810-826) | 7 |
| SPEC.md | §8.2 facts table, `package_manager` row (1390) | 7 |
| SPEC.md | §10.2.1 bands (1702-1713): no change; the bands are used as designed | — |
| specs/prK-hook-pack.md | no change: no rule's codes change (D23) | — |
| README.md | :722 pytest hook row: no change (the hook's codes and description stay) | — |
| README.md | :318-323 gating example (uv) | 7 |
| README.md, SPEC.md | `skill-nudge` labelled `degraded` on OpenCode once it matches `notebook_edit` (section 12.2) | 8 |
| catalog/README.md | :45-54 marker sentence | 5 |
| MIGRATION.md | the PR 5–8 subsection (section 9.11) | 5–8 |
| CONTEXT.md | no change (no new term) | — |

### 9.13 Decisions taken in PRs 5-8

| # | Decision | Rationale |
| --- | --- | --- |
| 1 | No rule's `lint_codes` changes in PRs 5-8, new or already linked; fitting codes are F2 candidates | D23 (codes stay out of rule frontmatter until a post-pilot follow-up), and a code on a linked rule changes hook output during the eval freeze; the pin at test_rules_lint_codes.py:64-75 guards it |
| 2 | The candidates that fit linked rules (`RUF012` for python-typing; `PT012`, `PT014`, `PT017` for pytest) are recorded for F2, with no preview codes | Each matches text the rule already owns and is stable in ruff 0.17.0, so F2 needs only the `lint_codes` line and its tests |
| 3 | Priority = band + impact offset (+1 / +3 / +8); merged rules take the highest impact | D7 without a new field; keeps the §10.2.1 bands |
| 4 | `python-async` gated `python_version: ">=3.11"` | TaskGroup and `asyncio.timeout`; Python 3.10 reaches end of life this month; a Jinja string compare would misorder "3.9" |
| 5 | `python-static-checks` ungated | The engine's own hooks run ruff in every repo; no key reads `dev_tools` |
| 6 | `package_manager` accepts a name or a non-empty list (any of); values validated before the fact is read | Single-valued fact; typos must fail in every repo |
| 7 | `validate` checks each `applies_if` key on its own | Otherwise the new key's typos hide behind a false key; matches hooks and `lint_codes.when` |
| 8 | No prompt `includes_rules` changes | Eval freeze: the runner inlines those bodies into graded prompts; D15 step 2 covers discovery |
| 9 | ML rules are `.md.j2` with per-library sections and glob `**/*.ipynb` | D9's single gate also admits NumPy-only and polars-only repos; notebooks are where ML edits happen |
| 10 | PR 5 merges first among the content PRs | It adds the credit and the marker that every distilled rule needs |
| 11 | Every new rule at most 100 lines and 750 words when rendered, enforced by a test | Agent Skills TOC threshold; one reference fits one read |

### 9.14 PR 5 content outlines

These outlines are written in our own words. Rule authors expand them and do
not consult upstream text. Each bullet is one short paragraph or 2–3 list
items in the rule.

**`python-performance-idioms` (PR 5, ~380 words)**

- **Measure first.** Trade clarity for speed only on a path that a profile
  shows is hot. Otherwise pick the clearest construct.
- **Building collections.** Use a comprehension when each element comes from
  one simple transform or filter. Use a plain loop when the body has side
  effects or raises domain errors, or when the comprehension would need more
  than two `for`/`if` clauses.
- **Single-pass or large inputs.** Use a generator expression or a generator
  function, and feed it straight into `sum`/`any`/`max`/`"".join`. Make a list
  only when you iterate twice.
- **Lookups.** Build a `set` or `frozenset` once, before a loop that tests
  membership. Index records by key in a dict instead of scanning a list. For
  order-preserving de-duplication use `dict.fromkeys`.
- **Optional keys only.** Use `.get(key, default)`, `defaultdict` or
  `setdefault` only when absence is normal. A required key is indexed directly,
  or parsed into a typed record at the boundary, so a missing key fails where
  the data entered (`python-error-handling`).
- **Strings and arrays.** Build strings from parts with `"".join(parts)`; use an
  f-string for a fixed handful of pieces. In NumPy or pandas code a
  comprehension is still a per-element Python loop; use whole-array operations
  instead. (No rule id here: `ml-vectorization` ships only in PR 8, and its
  gate differs from this ungated rule; section 9.4.4.)

**`python-async` (PR 5, ~520 words)**

- **Concurrency.**
  - Start independent awaits together.
  - Use `asyncio.TaskGroup` when every result is needed: the first failure
    cancels the siblings; handle the `ExceptionGroup` with `except*`.
  - Use `asyncio.gather(..., return_exceptions=True)` only when partial results
    are useful. Then check every result: re-raise `CancelledError`, and handle
    each other exception at the per-item boundary (log with `exc_info`).
- **Every task has an owner.**
  - Never call `asyncio.create_task(...)` and drop the result.
  - A task lives in a TaskGroup or in a supervisor object that the composition
    root creates and closes. The supervisor keeps references until each task is
    done, reads each result in a done callback and reports failures there.
  - No module-level task sets.
- **Bound the fan-out.**
  - Create the `asyncio.Semaphore` on the loop that uses it: inside the
    coroutine, or in a client built on that loop.
  - Size it from the remote's limit.
  - Prefer an HTTP client's own connection limit.
- **Bound the wait.** Wrap a group of awaits in
  `asyncio.timeout(<setting>)`. Per-request timeouts stay in
  `python-retries-and-timeouts`.
- **Keep the loop free.**
  - No `time.sleep`, blocking HTTP clients, blocking file reads or CPU-heavy
    loops inside `async def`.
  - Offload blocking work with `asyncio.to_thread`, and CPU work with a process
    pool.
  - Async resources use `async with` (`python-context-managers`).
- **Cancellation passes through.** Never swallow `CancelledError`. Clean up in
  `finally`, then let it propagate.
- **Candidate codes:** RUF006, ASYNC110, ASYNC210, ASYNC212, ASYNC230,
  ASYNC251. All are stable and none is added.

**`python-classes-and-protocols` (PR 5, ~620 words)**

- **One reason to change.**
  - Signs of trouble: "and" in the class description, imports from unrelated
    layers, private helpers clustering around different attributes.
  - Split by responsibility, so each part is testable alone.
- **The lightest construct.**
  - A function before a class.
  - A dataclass for records (`python-data-shapes` owns their shape).
  - A plain class for behavior with state.
  - Never a class that only wraps one function.
- **Attributes, then properties.**
  - Expose plain attributes; no `get_x()`/`set_x()` methods.
  - Turn an attribute into a `@property` later for validation; callers do not
    change. Derived values are `python-data-shapes`' bullet (a pointer).
  - Keep properties cheap. Use `functools.cached_property` for an expensive
    derived value on a class without slots.
  - Never `lru_cache` a method: it keeps instances alive.
- **Composition first.**
  - Hold a collaborator rather than inherit from it.
  - Inherit only when every subclass is substitutable.
  - Use mixins only for small, orthogonal behavior.
  - Framework base classes (`BaseModel`, `BaseSettings`, `DeclarativeBase`,
    Django views), exception hierarchies and documented ABC extension points
    are normal subclassing.
  - These bullets take over the composition and framework-base-class bullets
    of `python-idioms` (PR 2). The always rule keeps "wrap, don't subclass, a
    third-party class".
- **Protocol or ABC.**
  - `Protocol` for "anything with these methods" seams, small and role-named.
    Where to declare one is the DI rule's job.
  - An ABC when subclasses share implementation or must override a hook.
  - `runtime_checkable` checks method names only.
- **Substitutable subtypes.** A subtype accepts at least what the base
  accepts, guarantees at least what it guarantees, and raises only what the
  base contract names. A `NotImplementedError` stub, or a type check on
  `self`, means the hierarchy is wrong.
- **Small interfaces.** Split a Protocol when implementers stub methods or
  callers use disjoint halves. Never split speculatively.
- **Extension points.** When new variants keep arriving, replace a growing
  `if`/`elif`, or a `match` on a kind, with a mapping of strategies or an
  injected implementation. With one or two stable variants, keep the branch.
- **Abstractions earn their place.**
  - Duplicated knowledge gets one home.
  - Look-alike code that changes for different reasons stays separate.
  - No parameters, options or hooks for needs nobody stated.
  - Extract when the third real case arrives.
- **Candidate codes:** B019, B024, B027.

### 9.15 PR 5 plan

Every PR:

- branches from `main`;
- has a Conventional Commits title;
- passes the CI gate from the repo root, cache-free and without optional
  extras: `ruff check .`, `ruff format --check .`, `mypy` and `pytest -q`;
- leaves PR 2's D5 budget tests and D13 checks green on the reference probe;
- is authored by the user only, with no trailers.

**Files**

- New rules:
  - `catalog/core/rules/languages/python/performance-idioms.md`
  - `catalog/core/rules/languages/python/async.md`
  - `catalog/core/rules/languages/python/classes-and-protocols.md`
- Edited rules:
  - `catalog/core/rules/languages/python/{error-handling,docstrings,dependency-injection}.md`
  - `catalog/core/rules/languages/python/typing.md.j2`
  - `catalog/core/rules/languages/python/{data-shapes,idioms}.md` (PR 2's)
- `catalog/core/skills/python-coding/SKILL.md`: the "Picking references" bullets
  name the new topics (async code, performance-sensitive loops, class design),
  never rule ids
- `catalog/core/ATTRIBUTIONS.md` and `catalog/README.md`
- Tests:
  - `tests/integration/test_resources_self_contained.py`
  - `tests/integration/test_core_skills.py` (PR 2's membership tables)
  - `tests/integration/test_core_always_rules.py` (PR 2's one-owner rows)
  - `tests/unit/test_sources_filesystem_bundled.py` (`_ENGINE_RULE_COUNT` 15 → 18)
  - `tests/unit/test_core_rule_shapes.py` (new)
  - `tests/unit/test_distilled_content_policy.py` (new)
- Docs: `SPEC.md`, `MIGRATION.md`

**Tests**

- `tests/unit/test_rules_lint_codes.py`: no edit. `test_shipped_rules_declare_spec_codes`
  (:64-75) pins `declared == SPEC_CODES`, so it fails if PR 5 adds a code to any rule, new or
  linked (D23).
- `tests/integration/test_resources_self_contained.py`: section 9.9.3.
- `tests/integration/test_core_skills.py`:
  - `EXPECTED_MEMBERSHIP` gains the three new ids; `test_python_coding_members`:
    the set of ids with `skill: python-coding` equals the 12 ids in section 9.6.
  - `test_distilled_rule_frontmatter[rule_id]`, parametrized over a
    `DISTILLED_RULES` table: path, skill, scope, globs, applies_if, priority and
    `name` equal the section 9.6 row, and `lint_codes == {}`. PR 6–8 add rows.
  - `test_reference_probe_emits_each_core_skill_within_budget` keeps passing:
    python-coding composes to 278 characters and names all 12 members.
- `tests/integration/test_core_always_rules.py`: the
  `composition over inheritance` and `DeclarativeBase` rows of
  `test_moved_house_style_item_has_one_owner` point at
  `python-classes-and-protocols`.
- `tests/unit/test_core_rule_shapes.py`:
  - `test_core_scoped_rule_fits_one_reference_read[rule_id]`, over every core
    scoped rule: rendered with the reference-probe facts
    (`tests/_budget_probe.reference_probe_facts`, section 6.8.10), the body is
    at most 100 lines and 750 words. Failure
    message:
    `"{rule_id}: renders {lines} lines / {words} words with the reference-probe facts; expected at most 100 lines and 750 words (split it or move detail to another member)"`.
    The existing rules pass: the largest is 98 lines and about 720 source words.
  - `test_reference_probe_facts_render_every_jinja_branch_once`: a sanity
    check that the probe facts reach the `pytest-asyncio` and
    torch/numpy/pandas/sklearn branches, so the size test measures the long
    form.
- `tests/unit/test_distilled_content_policy.py`:
  - `test_core_artifacts_omit_dropped_recommendations[path, token]`, with
    tokens `hatchling`, `factory_boy`, `pytest-randomly`, `pytest-check`,
    `--install-types` and `| sh` over every core rule and prompt body. Failure:
    `"{path}: recommends {token!r}, which the D8 import policy drops"`. (`pyscn`
    is covered by the marker regex.) The scan is a literal substring match and
    does not read negation, so a prohibition must avoid the token too: PR 7's
    `python-static-checks` says "never let mypy install packages itself", not
    the flag (section 11.1). No current core rule or prompt contains any token.
  - `test_core_attributions_name_every_distilled_rule[rule_id]`: every id in
    `PBP_DISTILLED_RULES` appears in core ATTRIBUTIONS. PR 6–8 extend the set.
  - `test_moved_guidance_has_one_owner[needle, owner]`:
    `("composition over inheritance", "python-classes-and-protocols")` and
    `("slots=True", "python-data-shapes")`, and the needle appears in no other
    core rule body.
  - `test_docstrings_rule_keeps_the_example_contract`: the rendered
    `python-docstrings` body still requires "usage example" and calls Google
    sections optional (D8).

**Docs**

- SPEC §6.3 (SPEC.md:783-809, as PR 2 restructures it): the python-coding
  member list.
- SPEC tree (SPEC.md:239-262): replace the stale illustrative `rules/` subtree
  with the shipped inventory, including PR 5's files. PR 6–8 add theirs.
- SPEC changelog (SPEC.md:11): one bullet.
- `specs/prK-hook-pack.md`: no change; no rule's codes change (D23).
- `catalog/README.md:45-54`: "today, python_design's source" becomes
  "today, python_design's source and the two sources core distills", without
  naming them.
- MIGRATION.md, section 9.11 (the subsection named there).
- CONTEXT.md: no change. "Distilled content" already names this kind, and no
  new term appears.

**Acceptance**

1. The three new rules exist with the section 9.6 frontmatter.
   `playbook validate` is clean on the engine catalog.
2. Each new rule renders at most 100 lines and 750 words. None carries
   `lint_codes`, a URL or a marker.
3. No rule's `lint_codes` changes (D23): `test_shipped_rules_declare_spec_codes`
   passes with `SPEC_CODES` unedited, and typing-lint-feedback reports exactly
   what it reported before PR 5.
4. Core ATTRIBUTIONS credits python-best-practices: name, publisher, commit and
   MIT. The marker regex flags the four new forms, and the self-contained scan
   is green.
5. On the reference probe:
   - the `python-coding` description is at most 300 characters;
   - core descriptions total at most 2,000;
   - the listing is at most 6,000;
   - AGENTS.md and the always rules are unchanged by PR 5.
6. "composition over inheritance" appears in exactly one core rule.

## 10. PR 6 — python-testing distilled content

Title: `feat(catalog): add pytest fixtures and test-doubles references to python-testing`. Branches
from `main` after PR 2; rebases on `main` after PR 5 merges (section 9.3). The conventions,
mapping rows 28-39 and shared sections are in section 9.

### 10.1 Content outlines

**`pytest-test-doubles` (PR 6, ~480 words)**

- **Double only what the code does not own:** the network, databases, clocks,
  randomness, third-party SDKs, and the filesystem outside `tmp_path`. Never
  double the unit under test or its own helpers.
- **The default is a named fake** (`FakeInvoiceStore`) passed through the same
  parameter production uses (`python-dependency-injection`). Assert on the
  fake's recorded state, not on call sequences.
- **Thin third-party seams.** When the code wraps an SDK it cannot take as a
  parameter yet, patch the name where it is looked up. Use `autospec=True` or
  `unittest.mock.create_autospec`, so a wrong signature fails, and give it
  realistic return values. Never use a bare `Mock()`/`MagicMock()` that accepts
  anything.
- **`monkeypatch`** is for env vars (`setenv`/`delenv`), the working directory
  (`chdir`), dict entries, and attributes of code that cannot take a parameter
  yet. Never assign to `os.environ` or to a module global directly. In new
  code, needing a patch means a hidden dependency.
- **Many doubles in one test** means the unit has too many collaborators.
  Report that design problem; don't mock harder.
- **Time and randomness** come in as a clock or a seeded generator
  (`python-pure-core`). Freeze-time libraries are only for characterizing
  legacy code. FastAPI `dependency_overrides` stays with `fastapi-app-wiring`.

**`pytest-fixtures` (PR 6, ~420 words)**

- **Scope.**
  - Function scope by default.
  - `module` or `session` scope only for expensive, effectively immutable
    resources. Pair such a resource with a function-scoped fixture that resets
    state (rollback, clear, re-seed).
- **Teardown.** Use `yield` fixtures: code after `yield` runs even when the
  test fails. Never mix `yield` with `request.addfinalizer`.
- **Placement.**
  - In the test module when one module uses the fixture.
  - In the nearest `conftest.py` when a directory shares it.
  - In the root `conftest.py` only for suite-wide resources.
  - Promote a fixture only when a second location needs it. Avoid overriding a
    same-named fixture lower down.
- **Names and types.** This bullet moves from pytest.md.j2:50-56.
  - Name a fixture after what it returns.
  - Annotate its return type (`Iterator[T]` for a `yield` fixture).
  - Never import from `conftest`.
- **Factories.**
  - When tests need variations, return a factory with keyword-only parameters
    and valid defaults, so each test states only the attributes it depends on.
  - Track the objects it creates, for teardown.
- **Variants and diagnostics.** Use `params=` when every test using the fixture
  must run against each variant. `pytest --fixtures <dir>` and
  `pytest --setup-show` show where fixtures come from and when they are set up.

### 10.2 Plan

**Files**

- New: `catalog/core/rules/frameworks/pytest-test-doubles.md`,
  `catalog/core/rules/frameworks/pytest-fixtures.md`
- Edited: `catalog/core/rules/frameworks/pytest.md.j2` (body only; its
  `lint_codes` stay, D23), and
  `catalog/core/prompts/generate-tests.md.j2:35`: "Mock external services with
  `pytest-mock`'s `mocker` fixture; do not patch globals directly." becomes
  "Replace external services with named fakes passed in like production
  collaborators; patch with autospec only at thin third-party seams." (D8;
  `includes_rules` is unchanged, section 15, R3-4)
- `catalog/core/ATTRIBUTIONS.md`
- Tests: the membership tables in `tests/integration/test_core_skills.py`, the
  policy test, and `tests/unit/test_sources_filesystem_bundled.py`
  (`_ENGINE_RULE_COUNT` 18 → 20). `pytest-conventions-feedback/HOOK.md`,
  `README.md:722` and `tests/hooks/test_pytest_conventions_feedback.py` are not
  touched: the hook reports the same codes (D23).
- Docs: SPEC.md, MIGRATION.md

**Tests**

- `tests/unit/test_rules_lint_codes.py`: no edit; `SPEC_CODES["pytest"]` stays,
  so the pin fails if PR 6 adds `PT012`, `PT014` or `PT017` (F2 candidates).
- Membership: `test_python_testing_members` equals {pytest,
  pytest-test-doubles, pytest-fixtures}, plus two `DISTILLED_RULES` rows.
- Policy:
  - `test_moved_guidance_has_one_owner` gains
    `("monkeypatch", "pytest-test-doubles")` and
    `("from conftest import", "pytest-fixtures")`.
  - `test_pytest_test_doubles_puts_named_fakes_first`: in the rendered body the
    first "Fake" comes before the first "autospec". This pins D8's default
    order.
- The shape test now covers `pytest` after the edit (at most 100 lines).

**Acceptance**

1. pytest.md.j2 has no "## Fixtures" section and no monkeypatch clause. Both
   topics have exactly one owner.
2. `pytest`'s `lint_codes` and `pytest-conventions-feedback` are unchanged (D23).
3. `python-testing` has 3 references in the reference probe, and its
   description is at most 300 characters.
4. ATTRIBUTIONS lists both new ids.

## 11. PR 7 — python-tooling distilled content and the `package_manager` key

Title: `feat(detector): package_manager applies_if key and python-tooling references`. Branches from
`main` after PR 2; rebases on `main` after PR 5 merges. Mapping rows 26-27 and 40-46 are in
section 9.5. With PR 7, `python-tooling` gains an ungated member (`python-static-checks`), so the
skill is written in every Python repo; its authored texts become generic (section 11.3), and its
emitted description on the reference probe is 223 characters (236 with a `uv.lock`):

```text
Conventions tied to a named tool or framework. Covers Static checks, pytest configuration, FastAPI
app wiring, FastAPI error boundaries, Pydantic boundaries. Use when editing tool configuration or
code wired to a framework.
```

### 11.1 Content outlines

**`python-static-checks` (PR 7, ~500 words)**

- **The repo's configuration is the contract.**
  - Read `[tool.ruff]`/`ruff.toml` and `[tool.mypy]`/`mypy.ini` before acting
    on a finding.
  - Never edit `select`, `ignore`, `per-file-ignores` or the strictness to make
    a finding disappear. Propose a configuration change to the user as a
    separate step.
- **Run what CI runs.** Use the repo's own lint and type-check commands, found
  in its CI config, Makefile or pre-commit config. Fix every finding your
  change introduces. Findings in untouched code fall under the always-loaded
  reminder about problems outside the task (a pointer, not a repeat).
- **Ruff.**
  - Apply safe fixes (`ruff check --fix`). Read every unsafe fix before
    applying it.
  - The formatter owns layout: never hand-align or fight it.
  - Import order follows the configured isort rules.
- **Suppressions.**
  - The always rule's `noqa` and `type: ignore` discipline applies (a pointer,
    not a repeat).
  - Remove a stale ignore on a line you touch.
  - A directory-wide ignore in `per-file-ignores` only with the user's
    agreement.
- **Mypy.**
  - Fix the types before silencing anything.
  - Use `cast()` only where you know more than the checker, with a comment.
  - For an untyped third-party import, propose a stub package for the dev
    group, or add a per-module `ignore_missing_imports` override. Never a
    global switch, and never let mypy install packages itself: stubs go
    through the dev group like any dependency. (The body must not spell the
    flag: PR 5's `test_core_artifacts_omit_dropped_recommendations` bans the
    token even inside a prohibition, section 9.15.)
  - `reveal_type` is for debugging and never committed.
- **New code meets the repo's strictest level.** New modules meet the strictest
  level the repo applies anywhere; legacy overrides do not spread. Example: a
  TOML per-module override block. Config values in examples are illustrations,
  not mandates (D8).

**`pytest-configuration` (PR 7, ~330 words)**

- **One home for settings.** Settings live where the repo keeps them
  (`[tool.pytest.ini_options]`, `pytest.ini`, `tox.ini` or `setup.cfg`); edit
  that one place. Don't add `addopts` that change everyone's runs (`-x`, `-v`,
  coverage flags); pass them on the command line.
- **Markers.** Register every custom marker, so strict-marker typos fail.
  Select with `-m`. Skip and xfail policy stays in `pytest`.
- **Warnings.** When the repo turns warnings into errors, fix our warnings.
  Filter a third-party warning narrowly (message, category and module) with a
  comment saying why. Never blanket-ignore a category.
- **Coverage.**
  - Keep the threshold and branch setting; never lower them.
  - `pragma: no cover` only for code tests cannot reach (platform guards,
    `if TYPE_CHECKING:`), with a reason.
- **Discovery.** Put tests where `testpaths` finds them. Confirm with
  `pytest --collect-only -q`, and rerun failures with `--lf`.

**`python-uv-workflow` (PR 7, ~420 words)**

- **uv owns the environment.**
  - Change dependencies with `uv add <pkg>`, `uv add --dev <pkg>` (or
    `--group <name>`) and `uv remove`.
  - Never hand-edit `uv.lock`, and never `pip install` or `uv pip install` into
    the project environment. The dependencies hook denies both (it uses the
    same `package_manager` fact).
- **Run through the project.**
  - `uv run pytest`, `uv run python -m <app>`.
  - `uv sync` after pulling. CI uses `uv sync --locked`, so a stale lock fails.
  - One-off tools via `uvx`, without adding them.
- **Lockfile discipline.**
  - `uv.lock` is committed and only uv writes it.
  - Run `uv lock --upgrade-package <name>` only when the task needs that
    upgrade. Whole-lock upgrades are a separate change the user asks for.
- **Declaring dependencies** (from pkg-pyproject): runtime dependencies go in
  `[project].dependencies` with lower bounds; tools go in a dev dependency
  group; no exact pins in a library's pyproject (the lock pins).
  `requires-python` and `.python-version` are not changed unasked.
- **Missing uv.** If `uv` is missing, ask the user. Never install uv or run a
  remote install script.

**`pydantic-boundaries` (PR 7, ~450 words, Pydantic 2 API)**

- **Validate once, at the boundary.** Untrusted data is validated where it
  enters (request bodies, config files, environment, third-party responses,
  queue messages, CLI input), and typed objects travel inward. Domain code
  never re-validates and never sees raw dicts. Which type to use is the always
  rule's call (a pointer only).
- **Parse.** Use `Model.model_validate(data)` and
  `Model.model_validate_json(raw)`, not hand-unpacked dicts.
- **Constraints.**
  - Declare constraints (`Field(ge=..., max_length=...)`, `Annotated` types)
    instead of hand-written `if` checks.
  - Use `field_validator(mode="before")` only to normalize input before the
    constraints run.
- **Translate the error once.** Translate `ValidationError` at the boundary:
  FastAPI does it for request models; config loading fails at startup with the
  field path. Never catch it deep in domain code.
- **Thin models.** Models do validation and serialization only, with no
  business rules or I/O. Use `extra="forbid"` on inputs where an unknown field
  means a bug.
- **Settings and FastAPI.** Settings are loaded once in the composition root
  (`python-dependency-injection`). FastAPI wiring stays in
  `fastapi-app-wiring`.

### 11.2 The `package_manager` applies_if key

#### 11.2.1 Current state

- The fact already exists:
  - `Facts.package_manager: Literal["uv", "poetry", "pip-tools", "pip"]`
    (detector.py:37).
  - It is set by `_detect_package_manager` (detector.py:132-152): `uv.lock`
    gives `uv`; `poetry.lock` or `[tool.poetry]` gives `poetry`;
    `requirements.in` gives `pip-tools`; `requirements.txt` or a bare
    `pyproject.toml` gives `pip`; with none of these the fact is unset.
  - It is cached in `[detector_cache]` (SPEC.md:1237), written into guard
    config (`_guard_config_detect.py:111-113`), and used by the dependencies
    hook.
- `evaluate_predicate` (detector.py:341-410) has no key for it. An unknown key
  raises `ValueError("unknown predicate key: ...")` (:409).

#### 11.2.2 Semantics

```yaml
applies_if:
  package_manager: uv              # the fact equals this name
# or
applies_if:
  package_manager: [uv, poetry]    # the fact is any of these names
```

- The value is one of `uv`, `poetry`, `pip-tools` or `pip`, or a non-empty
  list of them. A list means "any of": that is the only useful reading of a
  single-valued fact, and D9's "no any_of combinator" concerns combining keys,
  not this key's own values.
- A repo whose detector sets no package manager never matches.
- The value is validated before the fact is read, so a typo fails in every
  repo, including one without a pyproject.
- It ANDs with the other keys, as every key does.

#### 11.2.3 Code (detector.py)

detector.py stays under 500 lines after this change: it grows from 410 to
about 455. Add `Final` and `get_args` to the `typing` import, and replace the
inline `Literal` in `Facts` and in `_detect_package_manager`'s return type with
the alias.

```python
#: The installers ``_detect_package_manager`` can report (SPEC §8.2).
type PackageManager = Literal["uv", "poetry", "pip-tools", "pip"]
KNOWN_PACKAGE_MANAGERS: Final[frozenset[str]] = frozenset(get_args(PackageManager.__value__))


def _package_manager_names(value: object) -> frozenset[str]:
    """The managers an ``applies_if.package_manager`` value allows; ``ValueError`` when malformed.

    >>> sorted(_package_manager_names(["uv", "poetry"]))
    ['poetry', 'uv']
    """
    names = [value] if isinstance(value, str) else value
    if not isinstance(names, list) or not names or not all(isinstance(n, str) for n in names):
        raise ValueError(
            f"predicate 'package_manager' must be one of {sorted(KNOWN_PACKAGE_MANAGERS)} "
            f"or a non-empty list of them; got {value!r}"
        )
    unknown = sorted(set(names) - KNOWN_PACKAGE_MANAGERS)
    if unknown:
        raise ValueError(
            f"predicate 'package_manager' names unknown package manager(s) {unknown}; "
            f"expected any of {sorted(KNOWN_PACKAGE_MANAGERS)}"
        )
    return frozenset(names)


def _package_manager_matches(value: object, facts: Facts) -> bool:
    """Whether ``facts["package_manager"]`` is one ``value`` allows; an absent fact never matches.

    >>> _package_manager_matches("uv", {"package_manager": "uv"})
    True
    """
    allowed = _package_manager_names(value)  # validates even when the fact is absent
    return facts.get("package_manager") in allowed
```

In `evaluate_predicate`, a new branch goes before the boolean-facts branch:

```text
elif key == "package_manager":
    if not _package_manager_matches(value, facts):
        return False
```

The docstring's key list gains `package_manager: "uv"` or `["uv", "poetry"]`.

**Free consumers of the key.** Hooks (`applies_if`, checked by contract H-rule
key by key at hook_policy/contract.py:401), `lint_codes.when[].applies_if`
(`commands/_validate_frontmatter.py:183-190`), prompts, the resync hook's applicability
rows (`_guard_config_detect.py:181-185`), the eval prompt renderer
(evals/prompting.py:250-251) and the agent_harness manifest (an open dict) all
call `evaluate_predicate`, so they gain the key with no further change.

#### 11.2.4 Fix: validate checks every key (commands/validate.py:110-142)

Today `_check_applies_if` passes the whole predicate to `evaluate_predicate`.
That function returns at the first key that does not hold, so a malformed key
after a false one passes `playbook validate` unseen. For example, with
`{has_framework: [django], package_manager: pipenv}` in a non-Django repo, the
typo is only caught in a Django repo. Hooks and `lint_codes.when` already
check key by key.

PR 7 aligns rules and prompts with them, and removes the duplicated rule and
prompt loops:

```python
def _applies_if_errors(
    path: str, predicate: Mapping[str, Any], facts: Facts, repo_root: Path
) -> list[ValidationError]:
    """One error per ``applies_if`` key that ``evaluate_predicate`` rejects, each key alone.

    ``evaluate_predicate`` returns at the first key that does not hold, so a
    malformed key after it would pass unseen; hook predicates are already
    checked key by key (hook_policy/contract.py).

    Example: ``_applies_if_errors("r.md", {"package_manager": "pipenv"}, {}, root)``
    returns one error naming ``'pipenv'`` and the four allowed managers.
    """
    errors: list[ValidationError] = []
    for key, value in predicate.items():
        try:
            evaluate_predicate({key: value}, facts, repo_root=repo_root)
        except ValueError as exc:
            errors.append(ValidationError(path=path, message=f"applies_if: {exc}"))
    return errors


def _check_applies_if(
    rules: list[Rule], prompts: list[Prompt], facts: Facts, repo_root: Path
) -> list[ValidationError]:
    """Validate every rule's and prompt's ``applies_if``, key by key."""
    artifacts: list[Rule | Prompt] = [*rules, *prompts]
    return [
        error
        for artifact in artifacts
        for error in _applies_if_errors(
            str(artifact.source_path or artifact.frontmatter.id),
            artifact.frontmatter.applies_if or {},
            facts,
            repo_root,
        )
    ]
```

This is a behavior change: a consumer or overlay predicate that has a hidden
typo now fails `validate`, and therefore the validate-gated `sync`. MIGRATION
says so (section 9.11).

#### 11.2.5 Pydantic gating

`pydantic` is in `KNOWN_FRAMEWORKS` (detector.py:62). Frameworks are drawn from
runtime and dev dependencies together (detector.py:269-273), so
`has_framework: ["pydantic"]` works as D8 says. The limitation is that a
FastAPI repo that never declares pydantic directly, and gets it only as a
transitive dependency, does not match (section 15, R5-3).

#### 11.2.6 Tests (all in PR 7)

In `tests/unit/test_detector.py`:

- `test_evaluate_predicate_package_manager_string_matches`: `"uv"` with fact
  `uv` gives True.
- `test_evaluate_predicate_package_manager_string_mismatch`: `"uv"` with fact
  `poetry` gives False.
- `test_evaluate_predicate_package_manager_list_is_any_of`: `["uv", "poetry"]`
  with `poetry` gives True; with `pip` gives False.
- `test_evaluate_predicate_package_manager_absent_fact_is_false`: `{}` gives
  False.
- `test_evaluate_predicate_package_manager_rejects_malformed_values`, shown
  below (ids: unknown-name, wrong-case, empty-list, int, mixed-list, none).
- `test_known_package_managers_cover_every_detected_value`, parametrized over
  `uv.lock`, `poetry.lock`, `[tool.poetry]`, `requirements.in`,
  `requirements.txt` and a bare pyproject: `detect(tmp)["package_manager"] in
  KNOWN_PACKAGE_MANAGERS`. This is the regression guard if a fifth installer is
  added to the Literal but not to the predicate.

```python
@pytest.mark.parametrize(
    "value",
    ["pipenv", ["uv", "UV"], [], 3, ["uv", 3], None],
    ids=["unknown-name", "wrong-case", "empty-list", "int", "mixed-list", "none"],
)
def test_evaluate_predicate_package_manager_rejects_malformed_values(value: object) -> None:
    with pytest.raises(ValueError, match=r"predicate 'package_manager'.*\['pip', 'pip-tools'"):
        evaluate_predicate({"package_manager": value}, {"package_manager": "uv"})
```

In `tests/cli/test_validate.py`:

- `test_validate_reports_unknown_package_manager_value`: a repo-local rule with
  `applies_if: {package_manager: pipenv}` makes validate exit 1, with the
  message
  `applies_if: predicate 'package_manager' names unknown package manager(s) ['pipenv']; expected any of ['pip', 'pip-tools', 'poetry', 'uv']`.
- `test_validate_checks_every_applies_if_key_after_a_false_one`: a regression
  test. The predicate `{has_framework: ["not-installed"], package_manager:
  "pipenv"}` is still reported.
- `test_validate_checks_prompt_applies_if_key_after_a_false_one`: the same,
  for a prompt.

In `tests/unit/test_hook_policy_contract.py`:

- `test_hook_applies_if_accepts_package_manager`: `uv` gives no finding;
  `pipenv` gives the message above.

### 11.3 Plan

**Files**

- Engine: `src/coding_agent_playbook/detector.py`,
  `src/coding_agent_playbook/commands/validate.py`
- New rules:
  - `catalog/core/rules/languages/python/static-checks.md`
  - `catalog/core/rules/languages/python/uv-workflow.md`
  - `catalog/core/rules/frameworks/pytest-configuration.md`
  - `catalog/core/rules/frameworks/pydantic-boundaries.md`
- `catalog/core/ATTRIBUTIONS.md`
- `catalog/core/skills/python-tooling/SKILL.md`: `description` "Conventions tied
  to a named tool or framework.", `playbook.use_when` "editing tool
  configuration or code wired to a framework", `playbook.files` "Tool
  configuration and framework wiring" (generic, so they stay true in a repo
  where only `python-static-checks` is active)
- Tests:
  - `tests/unit/test_detector.py`
  - `tests/cli/test_validate.py`
  - `tests/unit/test_hook_policy_contract.py`
  - `tests/cli/test_sync_tooling_references.py` (new)
  - the membership tables and `EXPECTED_WHERE` in
    `tests/integration/test_core_skills.py`, and the policy test
  - `tests/unit/test_sources_filesystem_bundled.py` (`_ENGINE_RULE_COUNT` 20 → 24)
- Docs: SPEC.md, README.md, MIGRATION.md

**Tests**

- Section 11.2.6.
- `tests/cli/test_sync_tooling_references.py` uses synthetic repos from the
  existing `make_synthetic_repo` fixture with the claude_code adapter:
  - `test_uv_workflow_reference_only_in_uv_repos`: with `uv.lock` the
    `python-tooling` skill holds the `python-uv-workflow` reference; with
    `requirements.txt` it does not.
  - `test_pydantic_boundaries_needs_declared_pydantic`
  - `test_python_tooling_exists_in_a_plain_python_repo`: only
    `python-static-checks` is active, and the skill is written.
- Membership: `test_python_tooling_members`, plus four `DISTILLED_RULES` rows.

**Docs**

- SPEC §6.4 (SPEC.md:810-826):
  - add `package_manager: "uv"  # facts["package_manager"] is this name (a list: any of them)` to the YAML block;
  - add a paragraph: the allowed values, any-of for a list, an absent fact
    never matches, an unknown value is a validate error even without the fact;
  - add the sentence "playbook validate checks each key on its own".
- SPEC §8.2 (SPEC.md:1390): "usable in `applies_if` (§6.4)".
- README.md:318-323: one sentence saying the uv workflow reference ships only
  to repos the detector sees as uv projects.

**Acceptance**

1. `evaluate_predicate({"package_manager": ...})` follows section 11.2.2. Every
   malformed value raises with the offending value and the allowed list.
2. `playbook validate` reports a malformed key even after a false key, for
   rules and for prompts.
3. `python-uv-workflow` renders only with `uv.lock`. `pydantic-boundaries`
   renders only with pydantic declared. `python-tooling` exists in a repo with
   no frameworks.
4. detector.py stays under 500 lines, and every new function has a type-hinted
   signature, a docstring and a test.

## 12. PR 8 — ml-data distilled content

Title: `feat(catalog): ml-data references for vectorization, transforms, dtypes and reproducibility`.
Branches from `main` after PR 2; rebases on `main` after PR 5 and PR 4 merge (section 9.3).
Mapping rows 47-59 are in section 9.5. The new rules gate on `any_ml_stack: [numpy, pandas,
polars]` and live under `catalog/core/rules/ml/` (D9). The emitted description on the reference
probe is 273 characters:

```text
Conventions for ML models and for array and data-frame code. Covers ML serialization &
deserialization security, Data transforms, Vectorization, Dtypes and typing, Reproducibility and
numeric tests. Use when loading or saving models, or transforming arrays and data frames.
```

Adding `notebook_edit` to `skill-nudge` can add `NotebookEdit` to the managed Claude Code
`PostToolUse` matcher in `.claude/settings.json` (it is not there in the probe today:
`Bash|Edit|MultiEdit|PowerShell|Write`); the next sync rewrites that managed entry, which
MIGRATION's PR 5-8 subsection mentions.

It also changes `skill-nudge`'s `playbook check` label on OpenCode from `enforced` to `degraded`:
`_lacks_a_tool` (`hook_policy/labels.py:65-73`) marks a hook degraded when any matched tool class
has no tool on the adapter, and `notebook_edit` has none on OpenCode
(`hook_policy/tables.py:133`), exactly as `ml-unsafe-deserialization-guard` and
`guard-generated-outputs` are labelled today. Behaviour on OpenCode does not change: `.py` and
`.ipynb` writes through `edit`/`write` still nudge. `playbook validate` stays clean, because
degraded cells of an engine hook do not warn (`hook_policy/contract.py:12-17`, `:340-342`). PR 4's
acceptance item 7 describes the state before this PR (section 8.10).

### 12.1 Content outlines

**`ml-vectorization` (PR 8, ~480 words, sections per library)**

- **Whole-array first.**
  - Arithmetic, comparisons, boolean masks, `np.where`/`np.select`, and
    reductions with `axis=`.
  - pandas `.str` and `.dt` accessors.
  - polars expressions (`pl.col`, `pl.when`).
- **Escalation ladder** when no direct operation exists: masks and selects,
  then a dict mapping (`Series.map`), then element-wise `Series.apply`, then a
  compiled extension, and the last only with the user's agreement. Row-wise
  `apply(axis=1)`, `iterrows`, `itertuples` and polars
  `map_elements`/`map_rows` are loops, kept for side effects on a few rows.
- **Groups.** Group logic uses built-in reducers by name in `agg` and
  `transform`, never `groupby().apply(<python function>)` for what a reducer
  does.
- **Build once.** Never grow an array or frame in a loop: each `np.append`,
  `np.concatenate`, `pd.concat` or `df.loc[len(df)] = …` copies everything.
  Collect into a list and build once, preallocate with a known size and dtype,
  or generate in one call (`rng.normal(size=n)`).
- **Streams.** Batch a stream: accumulate chunks and flush each to a frame or
  to Parquet.

**`ml-data-transforms` (PR 8, ~560 words, sections per library)**

- **Inputs are values.** A function takes an array or frame and returns a new
  one; it never mutates its argument.
- **NumPy.** Slicing returns a view, so writing into a slice of an argument
  changes the caller's data. Copy before writing, and use `out=` only on
  arrays the function created.
- **pandas writes.**
  - One indexer per write: `.loc[rows, cols] = value` (`.iloc` for positions).
    Never chain two indexers in an assignment: the write lands on a temporary
    and is lost under copy-on-write.
  - Whole-column assignment is fine.
  - No `inplace=True`: rebind the name instead. The only exception is a
    commented, measured memory fix, at top level.
- **Pipelines.**
  - One parenthesized chain, one step per line (`assign`, boolean indexing via
    lambdas, `rename`, `pipe` into named frame-to-frame functions).
  - Lambdas, not `query`/`eval` strings, so linters see the column names.
  - Long chains split into named functions joined by `pipe`.
- **Aggregation.**
  - Named aggregation, e.g. `agg(total=("amount", "sum"))`, with
    `as_index=False`.
  - `transform` to broadcast a group result back to rows.
  - `observed=True` when grouping by categoricals.
- **polars.** Expressions in `with_columns`, `select` and
  `group_by().agg(...alias(...))`; lazy frames (`scan_*` … `.collect()`) for
  large pipelines.

**`ml-dtypes-and-typing` (PR 8, ~620 words, sections per library)**

- **Declare types where data enters.**
  - `dtype=` and `usecols=` on read.
  - Dates through a strict, format-given conversion that raises on bad values.
  - Ids with leading zeros as strings.
  - Nullable dtypes for columns with missing values.
  - polars: `schema_overrides`.
- **Labels.**
  - Low-cardinality labels become `category`, using one shared categorical
    dtype constant applied to every source, so concat and merge keep it.
  - Ordered categories for ordinal data.
  - polars: `pl.Enum`.
- **NumPy.**
  - State the dtype at construction, and normalize inputs with
    `np.asarray(x, dtype=...)` at function entry.
  - Integer arrays wrap silently on overflow, so choose a width with headroom.
  - `float32` for features, `float64` for accumulations and statistics.
  - No `dtype=object` arrays.
- **Check after loading.** A small check asserts the expected columns and
  dtypes and raises naming the column. Only if the repo already uses pandera,
  express this as one schema validated at the boundary: lazy validation in
  pipelines, coercion only for lossless casts.
- **Annotations.**
  - `npt.NDArray[...]` for returns, `npt.ArrayLike` for inputs.
  - Shapes go in the docstring.
  - Return Python `float` from scalar reductions.
  - Without pandas-stubs mypy sees pandas as `Any`: propose adding it to the
    dev group, never add it unasked.

**`ml-reproducibility-and-testing` (PR 8, ~520 words, sections per library)**

- **One random source per run.**
  - Build `np.random.default_rng(seed)` at the entry point: the seed comes from
    configuration, and is `None` in production.
  - Pass the generator down; never `np.random.seed` or module-level
    `np.random.*` calls.
  - Child generators via `spawn` or `SeedSequence` for workers.
- **Other libraries keep their own state.**
  - Seed `random` and torch explicitly.
  - Pass `random_state=int(rng.integers(2**32))` to scikit-learn.
  - pandas `sample(random_state=rng)`.
  - Record the seed with the results.
- **Numeric assertions.**
  - `np.testing.assert_allclose` with `atol` when the expected values include
    zeros; `assert_array_equal` for integers, booleans and strings.
  - `pd.testing.assert_frame_equal` and `assert_series_equal`, loosening
    `check_dtype` or `check_like` only with a stated reason.
  - polars: `polars.testing.assert_frame_equal`.
  - `pytest.approx` only for scalars and short lists.
  - Never `==` on float arrays, and never `(a == b).all()`.
- **Expected data inline.** Build expected arrays and frames inline from
  hand-computed small cases, never from golden CSVs (dtypes and index names do
  not survive the round trip).

### 12.2 Plan

**Files**

- New: `catalog/core/rules/ml/{vectorization,data-transforms,dtypes-and-typing,reproducibility-and-testing}.md.j2`
- `catalog/core/ATTRIBUTIONS.md`
- `catalog/core/skills/ml-data/SKILL.md`: `description` "Conventions for ML
  models and for array and data-frame code.", `playbook.use_when` "loading or
  saving models, or transforming arrays and data frames", `playbook.files`
  "Model, array and data-frame code"
- `catalog/core/hooks/feedback/skill-nudge/HOOK.md`: `matcher.post_tool_use.tools`
  gains `notebook_edit` (the tool class `ml-unsafe-deserialization-guard/HOOK.md:12`
  already declares), so notebook cell edits trigger the nudge for the new
  `**/*.ipynb` globs (section 8.5.1)
- Tests: `tests/unit/test_ml_data_rules.py` (new), the membership tables and
  `EXPECTED_WHERE`, the policy test, `tests/hooks/test_skill_nudge.py`
  (`test_hook_md_matches_its_pack_row_and_handler` row gains `notebook_edit`;
  new `test_notebook_edit_names_ml_data`), `tests/cli/test_check_hooks.py`
  (`test_hooks_block_labels_per_adapter`: the `skill-nudge` line becomes
  `(agents_md: —, claude_code: enforced, continue: —, opencode: degraded)`, and the comment
  at `:141-142` adds it to the hooks OpenCode's missing notebook tool degrades), and
  `tests/unit/test_sources_filesystem_bundled.py` (`_ENGINE_RULE_COUNT` 24 → 28)
- Docs: SPEC.md (the hook's OpenCode label wherever PR 4 wrote "enforced on Claude Code and
  OpenCode"; `specs/prK-lifecycle-hooks.md` §C.5.1 is a per-event matrix and needs no edit), README.md (the `skill-nudge` row of the Edit feedback table PR 4 adds: enforced
  on "Claude Code; OpenCode degraded (no notebook tool)"), MIGRATION.md (the PR 5-8 subsection:
  the label change and the `.claude/settings.json` matcher rewrite)

**Tests** (`tests/unit/test_ml_data_rules.py`)

- `test_ml_data_rules_gate_on_numpy_pandas_polars[ml_stack, active]`: {numpy},
  {pandas} and {polars} activate all four new rules; {torch} and {} activate
  none.
- `test_library_sections_follow_the_ml_stack[rule_id, ml_stack, present, absent]`:
  rendered with pandas only, the body contains `.loc` and not `pl.col`; with
  polars only, the reverse; with numpy only, neither DataFrame heading.
- `test_torch_only_repo_keeps_serialization_as_the_only_ml_data_member`.

The resync golden
(`tests/fixtures/hook_payloads/*/post_tool_use/rdc_edit_pyproject_add_torch.expected.json`)
stays byte-identical: torch alone activates no new rule.

**Acceptance**

1. Four rules exist with the section 9.6 frontmatter, at most 100 lines and
   750 words each, rendered with the probe facts.
2. Library sections render only for libraries in `ml_stack`.
3. `ml-data` has 5 references in the probe, and its description is at most 300
   characters.
4. ATTRIBUTIONS lists all 13 new ids, and `PBP_DISTILLED_RULES` has 13 entries.
5. `playbook check` labels `skill-nudge` `claude_code: enforced, opencode: degraded`, and
   `playbook validate` reports no hook warning on the engine checkout.

### 12.3 Expected rendered size in the reference probe after PR 8

The probe has fastapi, httpx, pydantic, torch, numpy, pandas, scikit-learn,
pytest and pytest-asyncio, plus a notebook. Its package manager is not uv.

- Existing members use the measured baseline.
- New members use the section 9.6 targets.
- Tokens are estimated at the measured 1.68 tokens per word (AGENTS.md: 6,830
  words is about 11.5k tokens).
- Only the skill listing is always-loaded. A reference costs context only when
  it is opened.

| Skill | Active references | Words (existing + folded + new) | ≈ tokens | Largest reference | Est. description chars |
| --- | --- | --- | --- | --- | --- |
| python-coding | 12 | 2,623 + 225 + PR 2's two new rules (≈536) + 1,520 ≈ 4,900 | ≈ 8,200 | python-error-handling ≈ 690 | 278 |
| python-testing | 3 | ≈ 600 + 420 + 480 ≈ 1,500 | ≈ 2,500 | pytest ≈ 600 | 183 |
| python-tooling | 5 (6 with uv) | 354 + 341 + 500 + 330 + 450 ≈ 1,975 (+420 with uv) | ≈ 3,300 | python-static-checks ≈ 500 | 223 (236 with uv) |
| ml-data | 5 | 589 + 480 + 560 + 620 + 520 ≈ 2,770 | ≈ 4,650 | ml-dtypes-and-typing ≈ 620 | 273 |

The four core descriptions total 957 characters (computed with the section 9.6
names and the PR 7 and PR 8 texts); PR 4's `playbook-guardrails` adds 281, for
1,238. The D5 limit is 2,000; core plus plugins is about 4,636 of 6,000.

## 13. Lanes and ordering

```text
main ─┬─ PR 1  feat(adapters): write shared skills to .agents/skills; make continue opt-in at init
      └─ PR 2  feat(skills): deliver scoped rules as skill references
                (PR 1 and PR 2 in parallel; either may merge first)

after PR 2 has merged, each branched from main:
      ├─ PR 3  feat(prompts): point Claude Code and OpenCode commands at skill references
      ├─ PR 4  feat(hooks): name skills in lint feedback, move guardrail text into a skill, add skill-nudge
      └─ PR 5  feat(catalog): distill python-best-practices into the python-coding skill
            ├─ PR 6  (rebase on main after PR 5, then merge)
            ├─ PR 7  (rebase on main after PR 5, then merge)
            └─ PR 8  (rebase on main after PR 5 and PR 4, then merge)

v0.1.0 tag: after PR 1-4 (D14); PR 5-8 may follow it.
```

Rules:

- Every PR branches from `main`; there are no stacked PRs (CI runs only for PRs into `main`, and
  retargeting or editing a title does not start CI). Titles are Conventional Commits; squash
  merges are titled `Title (#N)`; commits are authored by the user only, with no trailers.
- PR 1 and PR 2 run in parallel. Whichever merges first opens SPEC 0.21 (header, footer, appendix
  entry, the pin in `tests/unit/test_docs_check_rubric_refactor.py`) and the shared `## v0.21 —
  Skills-first context` section of MIGRATION.md, and rewrites
  `tests/unit/test_docs_migration_hooks.py:72-77` to "descending version order" in the same PR, or
  its own CI fails on "newest release first"; the second rebases on `main` and merges the text by
  hand (P1-10). Only PR 2 commits `CONTEXT.md`, the ADR and this spec (C12). Known overlaps:
  - docs: SPEC header and changelog, §3, §5.3, §6.3, §10.8; the README architecture and Skills
    sections; MIGRATION's first section; `tests/unit/test_docs_check_rubric_refactor.py` and
    `tests/unit/test_docs_migration_hooks.py`;
  - `adapters/base.py:37-43`: PR 1 adds `retired_output_locations` and PR 2 adds
    `delivers_member_rules`, both directly after `output_locations` (adjacent insertions, a sure
    textual conflict: keep both attributes, PR 1's first);
  - `adapters/_skill_writer.py`: PR 1 edits the comment at `:8`, PR 2 moves `:62-194` into
    `_agent_skill_rules.py` and rewrites the docstring `:1-37`;
  - the module docstrings of `adapters/shared_skills_adapter.py` (`:1-16`) and
    `adapters/opencode_adapter.py` (`:28-34` in PR 1, `:63-79` in PR 2);
  - `tests/adapters/test_skill_writer.py`: PR 1's `_WRITER_ROOT` and `_ROOTS` change, PR 2's new
    tests (which take their roots from `NATIVE_SKILL_ROOTS`, section 6.8.4).
- PR 3, PR 4 and PR 5 start after PR 2 merges, in parallel lanes. PR 3 and PR 4 both edit
  `adapters/claude_code_adapter.py`, `adapters/opencode_adapter.py`, `commands/_sync_render.py`,
  SPEC, MIGRATION and `catalog/README.md`, in different functions and sections; the second to
  merge rebases. Their overlaps with PR 5-8 are listed in section 9.3: PR 4 with PR 5-8 in
  `tests/integration/test_core_skills.py` and `tests/unit/test_sources_filesystem_bundled.py`;
  PR 3 with PR 5 in `catalog/README.md` (`:56-60` vs `:45-54`); PR 3 with PR 6 in
  `catalog/core/prompts/generate-tests.md.j2` (`:57-62` vs `:35`); and PR 3's
  `build_environment` signature change, which PR 2-8 tests absorb through `render_core_rule`
  (section 6.8.10).
- PR 6-8 may be developed in parallel with PR 5, but each rebases on `main` after PR 5 merges and
  before merging itself (credit and marker regex first, section 9.3). PR 8 also waits for PR 4
  (it edits PR 4's `skill-nudge/HOOK.md`). Their overlaps are appended lines in
  `catalog/core/ATTRIBUTIONS.md`, the SPEC rules tree, `EXPECTED_MEMBERSHIP` / `DISTILLED_RULES`
  in `tests/integration/test_core_skills.py`, `PBP_DISTILLED_RULES`, `_ENGINE_RULE_COUNT` and the
  MIGRATION subsection.
- SPEC and MIGRATION versions: PRs 1-4 all write into SPEC 0.21 and the `## v0.21` MIGRATION
  section. PRs 5-8 append to the same version while it is untagged; if a release was tagged after
  0.21, PR 5 opens 0.22 (header, footer, appendix entry, docs-test pin, a `## v0.22` MIGRATION
  section) and PR 6-8 append to it.

CI gate for every PR, from the repository root, cache-free and in a venv installed without
optional extras (run it on the dev Python and on Python 3.12, which CI also uses):

```text
.venv/bin/ruff check --no-cache .
.venv/bin/ruff format --check --no-cache .     # also formats fenced python in every .md file
.venv/bin/mypy --cache-dir=/dev/null
.venv/bin/pytest -q -p no:cacheprovider
```

Focused checks before the full gate, per PR:

| PR | Focused tests | Extra checks |
| --- | --- | --- |
| 1 | `tests/adapters/test_shared_skills.py tests/unit/test_output_locations.py tests/cli/test_sync_skill_root_move.py tests/cli/test_init_adapters.py tests/unit/test_sync_preflight.py tests/unit/test_docs_skill_roots.py tests/cli/test_sync_skills.py tests/unit/test_docs_migration_hooks.py tests/unit/test_docs_check_rubric_refactor.py` | `timeout 180 playbook init --non-interactive --name probe --kind python-application </dev/null` in a scratch git repo in the scratchpad (never in the worktree); the symlink-pruning tests also on Python 3.12, where `Path.resolve()` raises on symlink loops |
| 2 | `tests/unit/test_skill_membership.py tests/unit/test_skill_document.py tests/cli/test_validate_skills.py tests/cli/test_sync_skill_references.py tests/integration/test_context_budget.py tests/integration/test_core_skills.py tests/integration/test_core_always_rules.py tests/unit/test_docs_glossary.py tests/unit/test_docs_migration_skills.py tests/cli/test_sync_orphans.py tests/cli/test_sync_skills.py tests/unit/test_sources_filesystem.py` | `playbook validate` on the engine checkout; the reference probe built in the scratchpad with a time-bounded, non-interactive `playbook init`, then `wc -w AGENTS.md .claude/rules/coding-agent-playbook.md` |
| 3 | `tests/unit/test_prompt_rule_delivery.py tests/unit/test_rule_registry.py tests/unit/test_catalog_prompt_references.py tests/unit/test_renderer.py tests/evals/test_prompting.py tests/cli/test_render.py` | manual smoke on Claude Code and on OpenCode v1.19.3 and v2.0.32: `/review` in the probe loads `python-coding` (section 7.9, item 8) |
| 4 | `tests/hooks/test_skill_nudge.py tests/unit/test_hook_policy_advisory.py tests/unit/test_hook_policy_guardrails_skill.py tests/adapters/test_guardrails_skill_targets.py tests/hooks/test_hook_summaries.py tests/unit/test_guard_config_skills.py tests/cli/test_sync_hook_outputs.py tests/cli/test_check_hooks.py tests/cli/test_sync_hook_trust.py tests/hook_runtime/test_import_budget.py` | the strict xfail of `test_agents_md_within_1500_words` is gone and the test passes; `playbook check` lists `skill-nudge` |
| 5-8 | `tests/integration/test_core_skills.py tests/unit/test_core_rule_shapes.py tests/unit/test_distilled_content_policy.py tests/integration/test_resources_self_contained.py tests/unit/test_rules_lint_codes.py`, plus `tests/unit/test_detector.py tests/cli/test_validate.py tests/cli/test_sync_tooling_references.py` (PR 7) and `tests/unit/test_ml_data_rules.py tests/hooks/test_skill_nudge.py tests/cli/test_check_hooks.py` (PR 8) | `playbook validate`; the reviewer's local word-shingle overlap check against the scratch upstream clone (never committed, section 15 R5-9); no code from the upstream clone is ever executed |

## 14. Cross-PR consistency notes

The five designer sections chose differently in a few places. The harmonised choice is the one
written in sections 5-12; this list records each choice and why.

| # | Topic | Choices on the table | Harmonised choice and reason |
| --- | --- | --- | --- |
| H1 | Where a member skill's extra authoring data lives | PR 2 engine: a catalog-only `playbook:` mapping (`use_when`, `files`), stripped on output. PR 2 catalog: `description` carrying `<capability>. Use when <…>.`, split by the engine at its single ` Use when `, plus `metadata.playbook-where`. | The `playbook:` block. The engine half owns parsing and validation (V7-V10, W1-W2), emitted frontmatter stays at `name`, `id`, `description` (no client metadata the harnesses do not use), and the authored description stays a plain capability sentence for raw-catalog consumers. The catalog texts were kept and moved into `playbook.use_when` and `playbook.files`. |
| H2 | What the Covers clause lists | PR 2 engine: rule `name`s verbatim. PR 2 catalog: topics derived from rule ids (`typing` from `python-typing`). PR 5-8: names, shortened in PR 5 if needed. | Names verbatim (E8), as D21 assumes. PR 2 already shortens the nine `python-coding` member names to topic labels (C5), because with today's names python-coding composes to 301 characters and would truncate from day one; PR 5-8 name their rules by the same convention (section 9.4.1). Names pinned by tests (`ML serialization & deserialization security`, `pytest conventions`, the FastAPI rules) stay. |
| H3 | How the 300-character cap holds | PR 2 engine: a validate error (V11) over every member's names. D21: deterministic truncation with `and N more`. | D21: `compose_description` truncates; V11 now fails only when the authored parts cannot fit a one-name clause with its `and N-1 more` tail; W3 warns on truncation; a core test requires the full list on the reference probe. |
| H4 | The reference probe | PR 2 engine: `tests/_budget_probe.py`, hooks on, both plugins, default adapters. PR 2 catalog: `tests/integration/conftest.py`, inline constants, hooks off, explicit adapters including `continue`. PR 4: "add the hooks-on case". PR 5-8: `REFERENCE_PROBE_FACTS` in `tests/_catalog.py` if needed. | One builder (`tests/_budget_probe.py`, inline constants, `reference_probe_facts`) and one module-scoped fixture (`tests/integration/conftest.py`), hooks on, both plugins, `REFERENCE_PROBE_ADAPTERS` = PR 1's default plus `continue`. The hooks-off whole-file measure becomes "text before `## Guardrails`", and the whole-file test is a strict xfail that PR 4 removes (E13), instead of PR 4 adding a second probe. |
| H5 | A member skill without a Where phrase | PR 2 engine: validate warning (W2). PR 2 catalog: validate error. | Warning in `playbook validate` (overlays are not blocked); required for core by `test_core_skill_declares_where_phrase`. |
| H6 | The Where section's lead sentence | Engine: "Detailed conventions live in skills. Before you edit one of these files, load its skill and open the references its index lists." Catalog: "Before you change a file, load the skill named for its kind; …". | The engine's sentence (the catalog designer assigned the lead sentence and format to the engine half); the phrases are the catalog half's. |
| H7 | The two D12 docs tests | Engine: rely on near-matching text already in SPEC §6.6.7 and §10.2. Catalog: edit those sections to carry the pinned phrases verbatim, with new test names. | The catalog half's: SPEC §6.6.7 says "fourth emitted canonical kind" and §10.2 says "Continue ships no wired hook mechanism", exactly the phrases D12 names; the glossary pointer test lives in `tests/unit/test_docs_glossary.py`. |
| H8 | `CONTEXT.md` edits | Engine: a new **Member rule** entry. Catalog: a sentence appended to **Scoped rule**, plus the Always-loaded context edit. PR 1: "_Avoid_: skills hub" under Skill root. | All three edits in PR 2, with the catalog half's Continue sentence folded into the **Member rule** entry; **Member rule** joins the docs test's term list. |
| H9 | Where the core-skill tests live | Engine and catalog: `tests/integration/test_core_skills.py` (overlapping tests). PR 5-8: `tests/unit/test_core_skill_membership.py`. | One module, `tests/integration/test_core_skills.py`, with the merged test list; `EXPECTED_MEMBERSHIP` and `DISTILLED_RULES` live there and PRs 5-8 extend them. |
| H10 | The skill filter PR 3 and PR 4 call | PR 3/PR 4: `_sync_render.filter_skills`. PR 2: deletes it for `skill_membership.compose_skills`. | `compose_skills` everywhere (sections 7, 8.4.3). |
| H11 | The reference-path helper | PR 3 assumed `member_reference_path(rule_id)`; PR 2 engine had only `MemberReference.filename`. | PR 2 adds `member_reference_path` in `_member_reference.py` (E16) and uses it in the writer; PR 3 imports it. |
| H12 | Where the house-style items and the upstream OOP rows go | PR 2 catalog: two rules (`python-data-shapes`, `python-idioms`); `oop-dataclass` and `oop-property` should fold into data shapes, and idioms' class bullets move to a classes rule. PR 5-8: one working rule `python-style-details`; `python-classes-and-protocols` takes records, `slots`, `@property` and composition. | PR 2's two rules. `python-data-shapes` owns records (including `slots=True`) and derived `@property` values; `python-classes-and-protocols` owns class design: SRP, attributes over getters, properties for validation, composition, framework base classes (moved from `python-idioms` in PR 5), Protocol vs ABC, LSP, ISP, extension points. Mapping row 15 therefore folds into existing rules; the totals keep 59 rows. Because the framework-base-class bullet came from the clean-architecture distillation, PR 5 adds `python-classes-and-protocols` to that ATTRIBUTIONS entry too. |
| H13 | `python-coding` member count | PR 5-8 counted 11 (one detail rule). | 12 after PR 5 (nine from PR 2 plus three); the description is 278 characters with every member listed. |
| H14 | MIGRATION and SPEC versions | PR 1: its own `## v0.21 — Shared skills move …` heading with numbered subsections. PR 2 engine: "Unreleased: …". PR 2 catalog: `## v0.21 — Scoped rules ship inside skills`. PR 3-8: "the release section PR 2 opens". | One shared `## v0.21 — Skills-first context` section with one TL;DR table and unnumbered `###` subsections referred to by title; SPEC 0.21 shared by PRs 1-4 (P1-10); PR 5-8 append while 0.21 is untagged, else PR 5 opens 0.22 (section 13). The migration docs test pins the `## v0.21` prefix only. |
| H15 | `playbook-guardrails` frontmatter | PR 4: `id` and `description` only. | `name: playbook-guardrails` added, so the core convention `id == name ==` directory holds for every core skill. It has no `playbook:` block and no members; its description carries `Use when` inline. |
| H16 | Scoped hook advisories in the Claude rules file between PR 2 and PR 4 | PR 4 feared PR 2 would drop them. | PR 2 drops only rules that name a skill (`is_skill_member`), so advisory rules (`skill=None`) keep reaching the file in full until PR 4 turns them into lines. |
| H17 | Notebook edits and the skill nudge | PR 4: "if PR 8 gives notebook globs, PR 8 adds `notebook_edit`". PR 5-8: notebook globs, no hook edit ("code changes only in PR 7"). | PR 8 adds `notebook_edit` to the `skill-nudge` matcher (a catalog `HOOK.md` line, not engine code) and therefore merges after PR 4. |
| H18 | The `generate-tests` prompt's `mocker` line (`generate-tests.md.j2:35`) | PR 3 risk: PR 6 should reword it. PR 5-8: "no prompt changes" (about `includes_rules`, for the eval freeze). | PR 6 rewords that one line to named fakes first (D8); `includes_rules` stays unchanged. Eval drift is accepted under R5-5. |
| H19 | Count pins | PR 5-8 did not list `_ENGINE_RULE_COUNT` (`tests/unit/test_sources_filesystem_bundled.py:41`) or the engine skill count. | 13 → 15 (PR 2), 18 (PR 5), 20 (PR 6), 24 (PR 7), 28 (PR 8); engine skills 4 (PR 2) → 5 (PR 4). |
| H20 | `python-tooling` and `ml-data` authored texts after PR 7 and PR 8 | PR 2 catalog: each later PR updates the texts. | PR 7 and PR 8 write generic texts (section 11.3, section 12.2) that stay true when only some members are active, because the capability sentence, `use_when` and `files` are static while the Covers clause follows the gates. |
| H21 | Eval appendix headings after the rename | PR 3 acceptance and tests named `### Python error handling` / `### Python typing`. | `### Error handling` / `### Typing`, the names since PR 2; PR 2 updates `tests/evals/test_prompting.py:65,390` and `tests/cli/test_sync.py:527-528`. |
| H22 | Vocabulary | Designers wrote "PR2", "topic skill", "house-style detail rule", "advisory" for guardrail text. | "PR 2"; "member rule"; the two rule ids; "guardrail" in new prose, while "advisory" stays where it names existing code or config (`Hook.to_advisory_rule`, the `hook_advisory` format, `[hooks] advisory`, `hook_policy/advisory.py` and its tests); `§x` only for SPEC sections. |

## 15. Risks

**PR 1**

- **R1-1. Codex frontmatter strictness is unverified.** Engine `SKILL.md` files carry pass-through
  keys beyond the Agent Skills standard (for example `id`, which every bundled plugin skill and
  every core skill declares). OpenCode accepts them today. Whether Codex rust-v0.163.0 ignores or
  rejects unknown keys was not checked. Mitigation: before tagging v0.1.0, a manual smoke test in a
  probe repo where Codex lists a synced `.agents/skills/` skill. If Codex rejects the keys, that is
  a D10 follow-up (strip non-standard keys from emitted frontmatter), not a reason to keep
  `shared_skills/`.
- **R1-2. OpenCode v1 noise.** With the default adapters, v1 finds each skill in three roots and
  logs two duplicate warnings per skill instead of one. v2 is unaffected because precedence picks
  one copy. Documented, with the environment variables that silence it.
- **R1-3. Consumer tooling paths.** Anything outside the engine that read `shared_skills/` breaks
  silently, because the directory disappears. MIGRATION has a TL;DR row for it; there is no runtime
  signal, by design (P1-8).
- **R1-4. User-owned `.agents/skills/`.** Teams that already keep skills there get engine
  directories beside theirs, gitignored per directory. A colliding id is skipped with a warning
  (existing behaviour). Symlinked roots are covered by sections 5.4.3 and 5.4.4.
- **R1-5. `keep_all` blocks the cleanup.** Any missing adapter, not only `codex`, keeps the whole
  retired tree until it is fixed; the hint covers the known case.
- **R1-6. Parallel-PR conflicts with PR 2** (section 13). The P1-10 rule decides who opens 0.21; the
  rest are textual merges.

**PR 2**

- **R2-1. Truncated Covers clauses outside core.** An overlay that adds many members or long names
  to a core skill gets `and N more` (D21) and a W3 warning; the description stays valid, but the
  listing names fewer topics. Core is pinned to list every member on the reference probe.
- **R2-2. D5's whole-`AGENTS.md` budget cannot pass before PR 4.** The Guardrails section alone is
  1,521 words. E13 ships the whole-file assertion as a strict xfail, so PR 4 must turn it on; PR 2
  asserts the text before `## Guardrails`.
- **R2-3. D13's static checks and the bundled plugins.** `subagent-driven-development/SKILL.md`
  has 569 lines and `writing-skills/SKILL.md` 682 (measured 2026-10-18). The description lint
  fails plugin skills too: python_design's `python-architecture` (637 characters) and
  `python-design-review` (476) exceed 300; superpowers' `diagnosing-superpowers` is 343; most
  superpowers descriptions start with "Use when" and `brainstorming` with "You MUST", which the
  third-person regex rejects. The CI checks cover core skills only (python_design's two skills,
  110 and 156 lines, would pass the line limit); shortening vendored text changes upstream
  wording, and a validate error would break every consumer who enables a plugin. The listing
  budget, which costs context every turn, still counts every plugin. Open question Q1.
- **R2-4. Breaking change for scoped rules outside core.** Overlays and repo-local scoped rules
  stop syncing until they add `skill:` (D2). V1/V2 name the fix and MIGRATION leads with it. No
  consumer exists yet.
- **R2-5. Loading a skill is the model's choice.** In PR 2 only the Where section points at skills;
  prompts (PR 3) and lint feedback plus the skill nudge (PR 4) come later. Claude Code does not
  re-send the skill listing after `/compact`; the Where section lives in the rules file, which
  survives compaction.
- **R2-6. Duplicate on-demand copies in Continue.** With `claude_code` and `continue` both enabled,
  Continue's IDE also reads `.claude/skills`, so a member rule is available both as its glob rule
  and as a skill reference. Both are on demand; PR 1 makes Continue opt-in.
- **R2-7. A user directory with a core skill id** keeps that harness from getting the skill (the
  writer skips it with a warning). The Where section still names the skill.
- **R2-8. Display names.** Covers lists names verbatim, so capitalized labels appear mid-sentence
  ("Covers Dependency injection, Pure core"); Continue's rule list and the eval appendix headings
  show the short labels. Cosmetic (D21); pre- and post-PR eval transcripts differ in those headings.
- **R2-9. The rendered kind is the detector's guess.** The probe's config says `kind =
  "python-application"`, but `project-context` renders `ml-research` (`detector.py:292`;
  `build_jinja_context` passes only `project_name` and `project_description` from the config,
  `commands/_sync_render.py:64-75`). Kept per D20; follow-up F1.
- **R2-10. Codex sees the map before it can read the skills.** If PR 2 merges before PR 1, Codex
  reads an `AGENTS.md` that maps to skills living only in `shared_skills/`, which no harness reads.
  Both land before v0.1.0 (D14), so no release carries the gap.
- **R2-11. Continue-only repos.** The map in `AGENTS.md`, which the Continue IDE loads as an always
  rule, names skills Continue cannot read; Continue gets the glob rule files instead. Accepted under
  D11.
- **R2-12. Less always-tier pressure on small idioms.** f-strings, import order, star imports and
  builtin shadowing leave always-loaded context. Many are enforced by ruff codes a consumer may
  enable (UP031/UP032, I001, F403, A001/A002), and PR 4's skill nudge adds a push. Accepted under
  D17.

**PR 3**

- **R3-1. Pointers are soft.** SPEC §6.2.5's reason for `includes_rules` was "the rules are in
  context, no matter what". On Claude Code and OpenCode the model must now follow step 1.
  Mitigation: the step is numbered, first, and names exact files; skill-trigger evals come after
  the pilot (D13). Until then nothing measures whether `/review` loads `python-coding`.
- **R3-2. Continue and eval prompt text changes too.** Removing the `rule()` calls moves the rule
  text of `review`, `generate-tests` and `security-review` to the end on Continue and in the eval
  runner; for `review` the rules now follow `## Output format`, so the verdict instruction is no
  longer the last thing the model reads. Under D22 the runner also appends rules to the 5 tasks
  whose prompts never called `rule()` (about 400-1,700 words each). Pre- and post-PR eval scores
  are not directly comparable.
- **R3-3. OpenCode `plan` agent.** `/review` and `/security-review` run as OpenCode's `plan` agent
  (`agent: plan`). The block assumes that agent may call the `skill` tool, which is not in the
  verified harness facts; section 7.9 item 8 checks it on v1.19.3 and v2.0.32. Open question Q2.
- **R3-4. Prompt text that contradicts a skill.** `generate-tests.md.j2:35` tells the agent to mock
  with `pytest-mock`'s `mocker`; D8 makes named fakes the default. PR 6 rewords that line (H18);
  PR 3 does not touch prompt guidance.

**PR 4**

- **R4-1. QC-10 per line.** `AGENTS.md` lines no longer say, one by one, where each guardrail is
  enforced; the preface and the skill do. A Codex user reading only `AGENTS.md` sees "follow them
  yourself" once, not per line.
- **R4-2. Dangling pointer with non-default adapters.** With both `opencode` and `shared_skills`
  disabled, the Guardrails preface names a skill no `AGENTS.md` reader can load. Same class as PR
  2's Where lines; PR 2's undelivered-member warning covers member skills, and the guardrails
  skill follows the same rule (no fallback).
- **R4-3. Broad globs make the nudge chatty once.** Every member glob is `**/*.py` or narrower, so
  the first Python edit in the probe names three skills (`ml-data`, `python-coding`,
  `python-tooling`). Bounded: three short lines, once per session.
- **R4-4. Compaction.** After `/compact`, Claude Code does not re-send the skill listing and the
  nudge does not fire again (once per session, D16). A long session can lose the pointers.
- **R4-5. Cross-PR edits of `ClaudeCodeAdapter.finalize`.** PR 2 rewrites the rules-file
  composition and PR 4 appends to it; the degraded-hook path has no core fixture today, so
  `test_claude_code_writes_skill_and_line_for_a_hook_it_cannot_run` is the guard.
- **R4-6. OpenCode v2 runs no lifecycle hooks.** The generated shim carries only an inert
  `setup()` stub for OpenCode V2 (SPEC §10.6.2, `SPEC.md:1905`), and Homebrew installs v2. There
  the skill nudge and the `rule X (skill Y)` lint feedback are inactive; only the `AGENTS.md`
  guardrail lines, the Where section and the skill listing point at skills. D16's "on Claude
  Code and OpenCode" holds for OpenCode v1 until the shim is ported (SPEC OQ-11). PR 4's
  MIGRATION subsection says so (section 8.9); the PR 3 manual smoke on v2.0.32 does not cover
  hooks.

**PR 5-8**

- **R5-1. The Covers clause and the 300-character cap.** Resolved by H2 and D21: with short labels
  python-coding composes to 278 characters with 12 members; truncation keeps any overflow valid.
  Do not rename `ml-serialization-security` (`tests/evals/test_prompting.py:76` and `:257` pin its
  heading).
- **R5-2. D9's single gate admits NumPy-only repos to pandas or polars guidance.** Mitigated by
  per-library Jinja sections, so a NumPy-only repo gets only the NumPy parts. The residual cost is
  "Data transforms" in the `ml-data` Covers clause of a NumPy-only repo, which is accurate because
  the rule covers views.
- **R5-3. Pydantic gating misses FastAPI repos that only get Pydantic transitively.** D8 fixes
  `has_framework: [pydantic]`, and `detector.py:269-273` reads declared dependencies only. Such
  repos get no `pydantic-boundaries`. Documented, not changed.
- **R5-4. Lint feedback stays silent on the new topics.** D23 adds no code, so a mutable class
  default (`RUF012`) or a multi-statement `pytest.raises` (`PT012`) gets no lint line until F2;
  only the references and the skill nudge carry that guidance. When F2 adds codes, an older
  pinned consumer ruff drops unknown codes per call (`hook_runtime/_ruff.py:212-213`) instead of
  failing.
- **R5-5. Eval drift.** The edited bodies of python-typing, python-error-handling,
  python-dependency-injection and pytest, and PR 6's reworded `generate-tests` line, reach graded
  prompts through the eval runner's inline appendix (D15, D22). CI's StubJudge ignores artifacts,
  so CI stays green, but a live eval baseline taken before PR 5 or PR 6 is not comparable after
  them. Re-baseline after the pilot.
- **R5-6. Merge order.** If PR 6, PR 7 or PR 8 merged before PR 5, distilled text would ship
  without credit. `test_core_attributions_name_every_distilled_rule` fails CI in that case.
- **R5-7. Library-version drift in content** (pandas copy-on-write, NumPy 2 promotion, Pydantic 1
  vs 2). The text is version-neutral, except that the Pydantic rule names the Pydantic 2 API. No
  `applies_if` key reads versions, so this is accepted.
- **R5-8. The resync hook does not watch `uv.lock` creation alone** (`_detector_inputs.py:63-72`).
  Switching to uv by `uv lock` without `uv add` surfaces the uv reference only at the next sync.
  Follow-up F5.
- **R5-9. Near-copying upstream text.** Authors write from the outlines only. Before merging, the
  reviewer runs a local word-shingle overlap check of the new bodies against the scratch upstream
  clone; the check is not committed, the upstream text never enters the repo, and nothing from the
  clone is executed. An 8-word overlap is reworded.
- **R5-10. Overlap with the opt-in python_design skills.** These design topics already overlap
  with the DI and pure-core rules. `python-classes-and-protocols` follows the reconciliation SPEC
  §11.5.2 states (Protocol or Callable by default, ABC allowed, no blanket bans), so enabling the
  plugin adds depth, not contradictions.

No settled decision was found harmful or impossible as stated. The additions beyond the letter of
the decisions (PR 1's prune fix and `codex` hint, PR 2's name shortening, probe sharing and V14,
PR 8's `notebook_edit`) exist because without them a decision either breaks a SPEC promise, cannot
be measured, or contradicts another decision (V14 keeps D2's "any skill that exists" from
contradicting D3's "plugin skills have no member rules"). Two places where decisions pull against
each other are open questions with a default: D13's lint over vendored plugins (Q1) and D17's
"no guardrails in the Claude rules file" against D6's "as today" (Q3).

## 16. Open questions

The designers' other open questions are answered by D20 (project kind), D21 (names and the
300-character cap), D22 (eval runner text) and D23 (lint hooks for distilled rules). Three
decisions remained after review. On 2026-10-18 the user asked for the whole plan to be implemented
and merged without further questions, so each default below is adopted as written (D24 = Q1,
D25 = Q2, D26 = Q3), and V14's narrowing of D2 (recorded as E6) is confirmed.

1. **Q1 — D13's static checks over bundled plugin skills (R2-3, E11).** D13 lists the description
   lint (third person, a "Use when" clause, at most 300 characters) and the 500-line limit
   without naming a scope. As measured, bundled plugins fail both: python_design's
   `python-architecture` and `python-design-review` descriptions are 637 and 476 characters;
   superpowers' `diagnosing-superpowers` is 343; most superpowers descriptions start with "Use
   when" and `brainstorming` with "You MUST", which the third-person check rejects; and two
   vendored superpowers skills have 569 and 682 lines. Default: every D13 check covers core
   skills only, so plugin skills are exempt; each test's docstring names the exemption and the
   reason; the D5 listing budget still counts every plugin. Alternatives: (a) also lint
   python_design (distilled text the engine owns: shorten its two descriptions to at most 300
   characters) and keep superpowers exempt; (b) lint every shipped skill, shortening and
   rewording the vendored superpowers descriptions and the two long `SKILL.md` files, each change
   listed in `catalog/plugins/superpowers/ATTRIBUTIONS.md`.
2. **Q2 — OpenCode `plan` agent and the skill tool (R3-3).** If the PR 3 smoke test shows that
   OpenCode's `plan` agent cannot call the skill tool, should the read-only OpenCode commands
   (`/review`, `/security-review`) fall back to the inline `## Reference rules` appendix (a one-line
   condition in `_render_prompt_opencode_command`, a deviation from D15 for OpenCode only)?
   Default: yes, fall back for those two commands only, and record it in SPEC §10.6.1.
3. **Q3 — A hook Claude Code cannot run, in the Claude rules file (P4-11).** D17 says
   `.claude/rules/coding-agent-playbook.md` carries the always text without guardrails; D6 says
   Claude Code keeps getting no guardrails "as today", and today a hook Claude cannot run (an
   overlay hook without `claude_code` in `supports`, or with events Claude cannot reach) reaches
   that file as a full advisory section. No core hook is in that case. Default: such a hook gets
   one guardrail line in the rules file and its full text in `.claude/skills/playbook-guardrails/`
   (section 8.4.4). Alternative (D17's letter): no line in the rules file; the full text only in
   the skill, which Claude Code finds through its skill listing.

Follow-ups (decided, out of scope here):

- **F1.** Render the config's `[project] kind` in `project-context` instead of the detector's
  guess (D20; `commands/_sync_render.py:64-75`).
- **F2.** Lint-feedback hooks for the distilled rules' candidate ruff codes (D23): RUF006 and
  ASYNC110/210/212/230/251 for `python-async`, PD002 for `ml-data-transforms`, NPY002 for
  `ml-reproducibility-and-testing`, PERF401/PERF403/SIM401/C419 for `python-performance-idioms`;
  each needs a `BUCKETS` row (`hook_runtime/handlers/_ruff_buckets.py:200-207`) and a `HOOK.md`.
  The same follow-up adds the candidates that fit already-linked rules, which need only a
  `lint_codes` line, `SPEC_CODES` and hook tests: `RUF012` on `python-typing` (ruff exempts
  Pydantic models), and `PT012`, `PT014`, `PT017` on `pytest` (plus the
  `pytest-conventions-feedback` description, `README.md:722` and `specs/prK-hook-pack.md:853,
  924, 945`). Fixing the hard-coded `resolved[:7]` slice in
  `tests/unit/test_rules_lint_codes.py:84-92` belongs there too.
- **F3.** Skill-trigger evals after the pilot (D13).
- **F4.** `playbook render <skill-id>` showing the composed `SKILL.md` (section 6.2).
- **F5.** The resync hook watching `uv.lock` creation (R5-8).
- **F6.** Stripping non-standard frontmatter keys if Codex rejects them (R1-1).
