# Attributions

The skills under `skills/` in this bundled plugin are vendored content: Matt
Pocock's engineering and productivity skills, kept near-verbatim, with every
change from the upstream text listed in this file.

## Provenance

- **Source:** Matt Pocock's skills (repository name: mattpocock/skills).
- **Version:** tag v1.3.1, upstream commit 24fe0ef7737efae15c87225755e9f6f5965e4888.
- **Author / copyright:** Copyright (c) 2026 Matt Pocock.
- **License:** MIT. The full licence text is in the `LICENSE` file next to this
  file, byte-identical to upstream's.
- **Scope:** the skills upstream publishes under `skills/engineering/` and
  `skills/productivity/`, except `triage` (see "Dropped and why"): 26 skills.
  Upstream's `skills/misc/`, `skills/in-progress/` and `skills/deprecated/` are
  not vendored.
- **Fidelity:** Matt's text is kept as he wrote it. Every change is listed
  below: the plugin-wide changes in the global sections, and each file and line
  in the skill's own section under "Per-skill changes". Upstream line numbers
  are lines of tag v1.3.1.
- **Upgrade procedure:** this is a pinned snapshot. Moving to a later upstream
  tag is a reviewed change that diffs the two upstream tags and replays this
  change list by hand; nothing follows upstream automatically.

## License copies

- `LICENSE` at the plugin root is upstream's file, byte for byte (1,068 bytes,
  SHA-256 0e7ac423bf2c6e223b7c5b156f8cf72da49d748e56a1641402c31f22ad07dbb5),
  starting "MIT License" and "Copyright (c) 2026 Matt Pocock".
- The MIT licence requires the copyright and permission notice in all copies or
  substantial portions. `playbook sync` copies each skill directory into
  consumer repos, so every skill ships `references/LICENSE`, a byte-identical
  copy of the root file, which travels with each synced directory:
  `.claude/skills/<id>/`, `.opencode/skills/<id>/`, `.agents/skills/<id>/` and
  the Agent Harness `skills/<id>/`.
- pr-body also ships `references/LICENSE-show-me`, the MIT notice of the
  third-party text it reproduces (see "Third-party content").
- Continue has no native skills: its degraded prompts
  (`.continue/prompts/<id>.md`) carry only the `SKILL.md` body and no licence
  copy, so a repo that renders this plugin only for Continue keeps a copy of
  `LICENSE` next to them itself.

## Restructure

- **Flat skill directories.** Upstream's `skills/<group>/<old-id>/` becomes
  `skills/<id>/`: the `engineering/` and `productivity/` group level goes, and
  each folder name equals the final id.
- **Only `SKILL.md`, `scripts/` and `references/` sync.** The engine copies
  nothing else from a skill directory, so every other upstream file at a skill
  root moves to `references/<same name>` with its content unchanged:
  ask-matt `PHASE-BOUNDARIES.md`; codebase-design `DEEPENING.md`,
  `DESIGN-IT-TWICE.md`; domain-modeling `ADR-FORMAT.md`, `GLOSSARY-FORMAT.md`;
  improve-codebase-architecture `HTML-REPORT.md`; pr-body `CREDITS.md`;
  throwaway-prototype `LOGIC.md`, `UI.md`; setup-matt-pocock-skills `domain.md`,
  `issue-tracker-local.md`, `triage-labels.md`; tdd `mocking.md`, `tests.md`;
  teach `GLOSSARY-FORMAT.md`, `LEARNING-RECORD-FORMAT.md`, `MISSION-FORMAT.md`,
  `RESOURCES-FORMAT.md`; writing-for-agents `SKILL-MECHANICS.md`.
- **Rewritten into `scripts/`:** diagnosing-bugs `scripts/hitl-loop.template.sh`
  as `scripts/hitl_loop_template.py`, and wizard `template.sh` as
  `scripts/wizard_template.py` (see "Script ports").
- **Links.** `SKILL.md` links to `references/<file>`; a back-link from a moved
  file becomes `../SKILL.md`; a link between two moved files stays as written;
  link text that is a code-formatted path carries the new path. Consumer paths
  that only look similar (teach's `./reference/`, a consumer's `scripts/`) are
  not touched.
- **Not shipped:** `agents/openai.yaml` in every skill (Codex interface
  metadata; with it goes `policy.allow_implicit_invocation`, so
  `disable-model-invocation` stays the only user-invoked marker), and the
  upstream repository-level files (`README.md`, `CHANGELOG.md`, `CLAUDE.md`,
  `AGENTS.md`, `GLOSSARY.md`, the package manifests, `.claude-plugin/`,
  `.agents/`, `.changeset/`, `.github/`, `.out-of-scope/`, `docs/`, `scripts/`
  and each group's `README.md`).

## Frontmatter

- `id: <dir-name>` is inserted as the first frontmatter key, by text insertion.
- `name` equals the id; a renamed skill changes both (see "Renames").
- Every other key stays verbatim (`description`, `disable-model-invocation`,
  `argument-hint`, `metadata`), except pr-body's `metadata.credits.url` line,
  which is deleted (see "No external URLs").
- No skill gets a `playbook:` block, so none is a rule skill, and no file in the
  plugin is a `.j2` template.
- Descriptions are verbatim except where a skill's section lists a change
  (expected: wizard, which says Python instead of bash, and any description
  that names `GLOSSARY.md`, which gains the `CONTEXT.md` fallback).
- Sync re-dumps frontmatter as YAML, so quoting may differ in the synced copies;
  the parsed values are the same.

## Renames

- Three upstream ids collide with Claude Code bundled skills, feature-gated ones
  included: `code-review` becomes `two-axis-review`, `pr` becomes `pr-body` and
  `prototype` becomes `throwaway-prototype`. In Claude Code a project skill named
  like a bundled skill replaces its slash command, and the bundled `pr` builds
  on the `gh` CLI.
- What moved with each rename: the directory, `id`, `name`, every inbound load,
  every prose mention and every router label.
- Unchanged on purpose: wayfinder's `prototype` ticket type and UI.md's
  `/prototype/<name>` route, which are not skill ids.

## Cross-skill references

- "Call the Skill tool with X" and an operative "/x" become "Load the `x`
  skill", a plain capability every harness has.
- A step that needs two skills becomes two separate loads, with no order
  implied.
- Human-facing `/name` stays: router labels, user-invoked descriptions, and
  "tell the user to run `/x`".
- Every load target ships in this plugin and is model-invoked.
- `triage` is removed from every list and route (see "Dropped and why").

## No external URLs

- No URL appears anywhere in the plugin: not in a skill, not in `LICENSE`,
  `README.md` or this file, attribution included.
- Link text stays as plain text; the link target goes.
- Example URLs become scheme-less placeholders: teach's `{link}` in
  RESOURCES-FORMAT.md, and wizard's dashboard placeholder.
- Upstream issues are cited by number, as "upstream issue 377" and "upstream
  issue 530".
- The architecture report's inline SVG carries no `xmlns` attribute.

## Imposed tools removed

- **Policy.** A vendored skill may tell the agent to use only the Python
  standard library, pip-installable packages, git, harness built-ins and the
  consumer repo's project toolchain (its own test, typecheck, lint, build and
  dev-server commands). Any other executable is an imposed tool and is removed:
  the forge CLIs, the JavaScript package runners as instructions, JSON and
  terminal utilities, HTTP clients, OS openers, shell linters, containers,
  headless browsers, any bash script and any CDN asset.
- **What it removed:** the forge CLIs (`gh`, `glab`: setup's GitHub and GitLab
  seeds; wizard's secret and variable writes); `tput` and the OS openers of
  wizard and improve-codebase-architecture (`wslview`, `explorer.exe`,
  `xdg-open`, `open`, `start`); the `curl` and Puppeteer options of
  diagnosing-bugs `SKILL.md` L27, L29 and L59 and the localhost URL in its
  script; `shellcheck` and `bash -n` in wizard's verify step; Tailwind and
  Mermaid via CDN in the architecture report; and both bash scripts.
- **Kept:** the project toolchain examples (TypeScript, Jest and JS-frontend
  examples, setup's JS-only monorepo markers), recorded as stack assumptions
  under "Consumer-repo conventions".

## Harness built-ins reworded

- A harness built-in (loading a skill, subagents, background agents, asking the
  user, todo lists, the harness's own web search and fetch, opening files) is
  named as a capability with an inline fallback for a harness that lacks it,
  never by one harness's tool name.
- `/clear` and `/compact` become "start a fresh context".
- The fallbacks where a capability is missing: two separate loads instead of a
  combined one; grilling's fact-finding goes through a background agent only,
  and otherwise the fact is looked up before the round is sent; research does
  the work itself when it already runs as a subagent or background agent
  (upstream issue 530); wayfinder without subagents leaves research tickets on
  the frontier for a later session; implement-spec keeps the user-requested
  draft PR "as the issue tracker describes" and, without subagents, works
  tickets sequentially with a stop-and-resume point at each merge boundary;
  two-axis-review without subagents runs Standards first, writes it in full,
  then runs Spec; the "GitLab `!67`" example stays verbatim.
- Opening a generated file reads "Open it for the user if your harness can open
  files, and tell them the absolute path either way."
- Each of the 15 user-invoked skills (`disable-model-invocation: true`) starts
  its body with the line "Run this only when the user asked for it by name;
  otherwise stop.", because only Claude Code honours the key.

## Script ports

- The two bash scripts become Python 3.10 or later, standard library only,
  executable, `mypy --strict` and ruff clean:
  `.agents/skills/diagnosing-bugs/scripts/hitl_loop_template.py` and
  `.agents/skills/wizard/scripts/wizard_template.py`. Both start with
  `#!/usr/bin/env python3`.
- **Both scripts:** a non-TTY guard exits with status 2 and asks the agent to
  have the user run `python3 <copy>` in their own terminal; the HITL loop also
  asks for the Captured block back.
- **wizard:** ANSI escapes instead of the terminal-colour utility; `webbrowser`
  instead of the OS openers, with scheme-less arguments printed rather than
  launched, so the WSL opener is lost; `getpass` for secrets; Ctrl-C handling;
  end of file mid-run read as an empty answer; `set_secret` and `set_var` kept
  by name as guided manual steps instead of forge writes; an atomic `.env`
  upsert; a placeholder for the dashboard address.
- **wizard's `SKILL.md`** reads only the `.env` templates (`.env.example`,
  `.env.sample`, `.env.template`, `.env.dist`) and the CI configuration, and
  verifies a script with `ast.parse`, which leaves no bytecode cache behind.

## Plugin always rule

- `rules/mattpocock-skills-tracker.md` (id `mattpocock-skills-tracker`,
  `scope: always`) is engine-authored, not upstream text.
- It replaces the "## Agent skills" block that upstream's setup skill wrote into
  the consumer repo's `CLAUDE.md` or `AGENTS.md`: setup no longer edits either
  file.
- It names `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and
  `docs/agents/domain.md` as this repo's tracker, label and domain
  configuration for these skills, says to tell the user to run
  `/setup-matt-pocock-skills` when they are missing, and says that `.scratch/`
  is untracked working state that is never staged. Its text lives only in the
  rule file.

## Dropped and why

- `triage`: the local markdown tracker has no category field, close-as-wontfix,
  reporter loop or pull-request surface for it to drive. A consumer may add it
  back repo-locally at `playbook/skills/triage/`; setup still writes the label
  vocabulary it would need.
- setup's GitHub and GitLab tracker seeds and its PR/MR-as-request flag, and
  setup's steps that wrote into `CLAUDE.md` or `AGENTS.md`.
- `agents/openai.yaml` in every skill.
- wizard's automatic forge writes, its `tput` colours and its OS
  openers (`wslview`, `explorer.exe`, `xdg-open`, `open`); ANSI escapes and
  `webbrowser` replace them, and the WSL opener is lost.
- The architecture report's CDN assets.
- pr-body's `metadata.credits.url`.
- Upstream's `skills/misc/`, `skills/in-progress/` and `skills/deprecated/`,
  and the repository-level files.

## Third-party content

- pr-body's "Summary visuals" menu reproduces HumanLayer's show-me skill: MIT,
  "Copyright (c) 2026 HumanLayer", repository name humanlayer/skills, commit
  653b6411c1f70c275a18e37673b042ff99f67ceb. Its notice ships as
  `references/LICENSE-show-me`; upstream's `CREDITS.md` moves to
  `references/CREDITS.md` with its link text kept and its URLs removed.
- The Agent Harness adapter moves `metadata` to its manifest sidecar; Continue
  drops both `metadata` and `references/`.

## Consumer-repo conventions

These are paths inside the consumer repo, not dependencies:

- `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and
  `docs/agents/domain.md`, written by setup-matt-pocock-skills.
- `.scratch/<slug>/`: the local tracker's files, untracked working state that is
  never staged in a commit.
- `GLOSSARY.md` and `GLOSSARY-MAP.md`, or `CONTEXT.md` and `CONTEXT-MAP.md` when
  the repo already has them: every file that names the first pair also names the
  second, as "(or `CONTEXT.md` if the repo already has one)".
- `docs/adr/` for decision records.
- teach's workspace files, in the current directory.
- The OS temporary directory, for the architecture report and the handoff file.
- **Stack assumptions:** the TypeScript, Jest and JS-frontend examples stay
  verbatim, and so do setup's JS-only monorepo markers; a Python or Cargo
  workspace is detected as a single context unless the user writes the MAP file
  by hand.

## Rendering per adapter

- **Native** (`claude_code`, `opencode`, `shared_skills`): byte-identical copies
  of `SKILL.md`, `references/` and `scripts/`; `name` equals the id; the
  engine's AUTOGENERATED sentinel is the first body line; scripts keep their
  executable bit.
- **Agent Harness** (opt-in): `skills/<id>/`, with every key beyond `id`, `name`
  and `description` moved to `.playbook/manifest.toml`.
- **Continue** (opt-in): body-only prompts in `.continue/prompts/<id>.md`, with
  no `references/`, no `scripts/`, no licence copy and broken relative links;
  each skill's section records what it loses.
- The plugin always rule reaches `.claude/rules/coding-agent-playbook.md`,
  `AGENTS.md`, one `.continue/rules/` file when `continue` is listed, and the
  Agent Harness `rules/`.
- Only Claude Code honours `disable-model-invocation`; in every other harness
  the guard line asks the model to stop.

## Gates

- `tests/plugins/mattpocock_skills/`: `test_gates.py` (the shared gate: no URL,
  no imposed tool, no command-position word, no shell script, no Claude-only
  name, no coupling marker, the layout, the licence copies, the frontmatter, the
  path mentions, the load targets, the guard line, the glossary fallback, the
  per-file allowlist, the scripts, the ruff exclude, the links and this file's
  sections), `test_budget.py` (core plus each bundled plugin within 6,000
  characters of skill listing), `test_sync.py` (end-to-end init and sync), one
  test file per group of skills, and `test_inventory.py` (the whole inventory).
- Generic gates that cover the plugin with no edit: the repository-wide
  self-containment scan (URLs and markers in every file), the catalog layout
  test (leaf rule, no link to a plugin-root file), the link gate with every
  bundled plugin enabled, and the ruff scope test.

## Per-skill changes

### ask-matt

_Filled by T09._

### codebase-design

_Filled by T06._

### diagnosing-bugs

_Filled by T07._

### domain-modeling

Upstream `skills/engineering/domain-modeling/`; synced as `.agents/skills/domain-modeling/`.
Layout-only keep with the glossary fallback, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: domain-modeling` inserted as the first
  frontmatter key, before "name: domain-modeling" (Frontmatter).
- `SKILL.md` L3 (v1.3.1): the description gains " (or CONTEXT.md if the repo
  already has one)" after "GLOSSARY.md", growing from 151 to 195 characters
  (D21). This changes a value the Frontmatter rule otherwise keeps verbatim:
  D21 covers every file that names `GLOSSARY.md`, and the description is what
  makes the skill discoverable in a repo that already uses `CONTEXT.md`.
- `SKILL.md` L8 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md`; nothing else on the line changes
  (D21).
- `SKILL.md` L24 (v1.3.1): " (or `CONTEXT-MAP.md` if the repo already has one)"
  inserted after the code span `GLOSSARY-MAP.md` (D21).
- `SKILL.md` L40 (v1.3.1): the `CONTEXT.md` clause inserted after the code span
  in "If no `GLOSSARY.md` exists" (D21).
- `SKILL.md` L46 (v1.3.1): the `CONTEXT.md` clause inserted after the code span
  in "the existing language in `GLOSSARY.md`" (D21).
- `SKILL.md` L62 (v1.3.1): the `CONTEXT.md` clause inserted after the code span
  in "update `GLOSSARY.md` right there" (D21), and the link
  "[GLOSSARY-FORMAT.md](./GLOSSARY-FORMAT.md)" now targets
  `references/GLOSSARY-FORMAT.md` (Restructure). The link text stays, because it
  is not a code-formatted path.
- `SKILL.md` L64 (v1.3.1): the `CONTEXT.md` clause inserted after the first code
  span in "`GLOSSARY.md` should be totally devoid of implementation details"
  (D21).
- `SKILL.md` L74 (v1.3.1): the link "[ADR-FORMAT.md](./ADR-FORMAT.md)" now
  targets `references/ADR-FORMAT.md`, link text kept (Restructure).
- `references/GLOSSARY-FORMAT.md`: moved from the skill root (Restructure); its
  only content changes are the four insertions below.
- `references/GLOSSARY-FORMAT.md` L34 (v1.3.1): the `CONTEXT.md` clause inserted
  after the code span in "One `GLOSSARY.md` at the repo root" (D21).
- `references/GLOSSARY-FORMAT.md` L36 (v1.3.1): the `CONTEXT-MAP.md` clause
  inserted after the code span in "A `GLOSSARY-MAP.md` at the repo root lists the
  contexts" (D21).
- `references/GLOSSARY-FORMAT.md` L56 (v1.3.1): the `CONTEXT-MAP.md` clause
  inserted after the code span in "If `GLOSSARY-MAP.md` exists" (D21).
- `references/GLOSSARY-FORMAT.md` L57 (v1.3.1): the `CONTEXT.md` clause inserted
  after the code span in "If only a root `GLOSSARY.md` exists" (D21).
- `references/ADR-FORMAT.md`: moved from the skill root, byte for byte
  (Restructure). It names no glossary file and has no links.
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). It held Codex interface
  metadata and no invocation policy.
- Unchanged on purpose in `SKILL.md`: the mentions inside the fenced trees (L16,
  L28, L33, L36); the heading "### Update GLOSSARY.md inline" (L60), because L62
  directly under it carries the fallback; and the second mention in L64, "Do not
  treat `GLOSSARY.md` as a spec", because the first mention in the same pair of
  sentences carries it. In `references/GLOSSARY-FORMAT.md`: the L1 heading; the
  fenced example at L38-L52, whose `./src/<context>/GLOSSARY.md` links sit inside
  the fence, so the link check masks them and they need no rewrite after the
  move; and L58 "If neither exists, create a root `GLOSSARY.md` lazily when the
  first term is resolved", because after L56-L57 "neither" already covers both
  names and the file created is still named `GLOSSARY.md`. The examples
  (Postgres, AWS, GraphQL and REST, an ORM, a `src/` tree) are illustrations,
  not a stack assumption (D27).
- For the global sections: "Restructure" says each moved file keeps its content
  unchanged, but `references/GLOSSARY-FORMAT.md` is moved with the four D21
  insertions above. That sentence should add "except the changes listed in the
  skill's own section".
- Continue: `.continue/prompts/domain-modeling.md` is the user-run
  `/domain-modeling` prompt. `references/` is not carried, so the two format
  links (L62 and L74) dangle and the glossary and ADR formats are lost. The
  description no longer triggers the skill from the model, grill-with-docs
  cannot load it, and no licence copy travels.

### grill-me

Upstream `skills/productivity/grill-me/`; synced as `.agents/skills/grill-me/`.
Vendored with listed changes, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: grill-me` inserted as the first frontmatter key,
  before "name: grill-me" (Frontmatter).
- `SKILL.md` L6 (v1.3.1): after upstream's blank line that closes the
  frontmatter, the guard line "Run this only when the user asked for it by name;
  otherwise stop." inserted as the first line of body content, followed by one
  blank line (D19).
- `SKILL.md` L7 (v1.3.1): "Call the Skill tool with "grilling"." becomes "Load
  the `grilling` skill." The Claude-only tool name goes; the target is
  model-invoked and keeps its id (Cross-skill references, D17).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). It carried
  `policy.allow_implicit_invocation: false`, the Codex half of upstream's
  user-only invocation (upstream `.agents/invocation.md` L10). Without it Codex,
  which reads the shared skill root `.agents/skills/`, no longer keeps the model
  from invoking this skill, and the guard line is the only guard left outside
  Claude Code, which honours `disable-model-invocation` (D10, D19).
- Continue: `.continue/prompts/grill-me.md` is the user-run `/grill-me` prompt.
  Its only instruction, "Load the `grilling` skill.", cannot fire there, because
  grilling is only a prompt, so the user runs `/grilling` directly. No licence
  copy travels.

### grill-with-docs

Upstream `skills/engineering/grill-with-docs/`; synced as `.agents/skills/grill-with-docs/`.
Vendored with listed changes, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: grill-with-docs` inserted as the first
  frontmatter key, before "name: grill-with-docs" (Frontmatter).
- `SKILL.md` L6 (v1.3.1): after upstream's blank line that closes the
  frontmatter, the guard line "Run this only when the user asked for it by name;
  otherwise stop." inserted as the first line of body content, followed by one
  blank line (D19).
- `SKILL.md` L7 (v1.3.1): "Call the Skill tool twice, for "grilling" and
  "domain-modeling"." becomes "Load the `grilling` skill, and load the
  `domain-modeling` skill." These are two separate loads with no order implied:
  upstream explains "twice" only as one skill per call. The Claude-only tool
  name goes, and both targets are model-invoked, ship in this plugin and keep
  their ids (Cross-skill references, D17, D18.1).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). It carried
  `policy.allow_implicit_invocation: false`, the Codex half of upstream's
  user-only invocation (upstream `.agents/invocation.md` L10). Without it Codex,
  which reads the shared skill root `.agents/skills/`, no longer keeps the model
  from invoking this skill, and the guard line is the only guard left outside
  Claude Code, which honours `disable-model-invocation` (D10, D19).
- Every other byte is upstream's, including "ADR's" in the description.
- Continue: `.continue/prompts/grill-with-docs.md` is the user-run
  `/grill-with-docs` prompt. Its body asks for two loads, and Continue gets
  grilling and domain-modeling only as prompts, so neither load fires and the
  combined docs-writing interview is lost; the user can run `/grilling` and then
  `/domain-modeling` instead. `disable-model-invocation` (harmless, since
  prompts are user-run) and `references/LICENSE` are dropped.

### grilling

Upstream `skills/productivity/grilling/`; synced as `.agents/skills/grilling/`.
Vendored with listed changes, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: grilling` inserted as the first frontmatter key,
  before "name: grilling" (Frontmatter).
- `SKILL.md` L26 (v1.3.1): fact-finding is delegated only to a background agent,
  with an inline fallback, and "Don't block on it" applies only to that path
  (Harness built-ins reworded, D17, D18.2). Three edits on the line:
  "dispatch a sub-agent to find it; don't ask the user" becomes "dispatch a
  background agent to find it if your harness can run one; otherwise look the
  fact up yourself before you send the round. Don't ask the user"; "Don't block
  on it:" becomes "If you dispatched a background agent, don't block on it:";
  and "wait for the sub-agent to report" becomes "wait for the background agent
  to report".
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). It held Codex interface
  metadata and no invocation policy.
- Every other byte is upstream's, including the emoji round template in the
  fence at L12-L22 and "still open in this round" at L24.
- Continue: `.continue/prompts/grilling.md` is the user-run `/grilling` prompt.
  The 'grill' trigger phrases no longer reach it from the model, and the loads in
  grill-me, grill-with-docs and the other skills that name it cannot reach it.
  The body is complete without references, and its inline lookup fallback covers
  a session without background agents. No licence copy travels.

### handoff

_Filled by T08._

### implement

_Filled by T04._

### implement-spec

_Filled by T04._

### improve-codebase-architecture

_Filled by T06._

### pr-body

_Filled by T05._

### research

_Filled by T08._

### retro

_Filled by T08._

### setup-matt-pocock-skills

_Filled by T03._

### tdd

_Filled by T05._

### teach

_Filled by T08._

### throwaway-prototype

_Filled by T06._

### to-questionnaire

Upstream `skills/productivity/to-questionnaire/`; synced as `.agents/skills/to-questionnaire/`.
Layout-only keep, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: to-questionnaire` inserted as the first
  frontmatter key, before "name: to-questionnaire" (Frontmatter).
- `SKILL.md` L6 (v1.3.1): after the blank line that closes the frontmatter, the
  guard line "Run this only when the user asked for it by name; otherwise stop."
  inserted as its own paragraph, the first line of body content (D19).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). With it Codex loses this
  skill's user-only invocation policy; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line.
- Every other byte is upstream's, including the double blank line at L10-L11,
  the en dash in "steps 1–2" at L16 and the lone `>` answer stub at L47.
- Continue: `.continue/prompts/to-questionnaire.md` holds only the body, guard
  line included, with no `references/LICENSE`. Nothing functional is lost: the
  body is self-contained and a Continue prompt is always started by the user.

### to-spec

_Filled by T03._

### to-tickets

_Filled by T03._

### two-axis-review

_Filled by T05._

### wait-what

Upstream `skills/productivity/wait-what/`; synced as `.agents/skills/wait-what/`.
Layout-only keep, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: wait-what` inserted as the first frontmatter key,
  before "name: wait-what" (Frontmatter).
- `SKILL.md` L6 (v1.3.1): after the blank line that closes the frontmatter, the
  guard line "Run this only when the user asked for it by name; otherwise stop."
  inserted as its own paragraph, separate from Matt's user-voice sentence (D19).
- `SKILL.md` L7 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md`, and " (or `CONTEXT-MAP.md` if the
  repo already has one)" after the code span `GLOSSARY-MAP.md`; nothing else on
  the line changes (D21).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). With it Codex loses this
  skill's user-only invocation policy; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line.
- Continue: `.continue/prompts/wait-what.md` holds only the body, the guard line
  and the re-pitch sentence. It works as a prompt the user starts and still
  reads `GLOSSARY.md` or `CONTEXT.md` from the repo; only the licence copy does
  not travel.

### wayfinder

_Filled by T04._

### wizard

_Filled by T07._

### writing-for-agents

_Filled by T08._
