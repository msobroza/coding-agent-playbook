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

_Filled by T02._

### grill-me

_Filled by T02._

### grill-with-docs

_Filled by T02._

### grilling

_Filled by T02._

### handoff

Upstream `skills/productivity/handoff/`; synced as `.agents/skills/handoff/`.
Vendored with listed changes, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: handoff` inserted as the first frontmatter key,
  before "name: handoff" (D11). `name`, `description`, `argument-hint` (with its
  quotes) and `disable-model-invocation: true` are upstream's and keep their
  order.
- `SKILL.md` L7-L8 (v1.3.1): upstream's blank L7 stays; the guard line "Run this
  only when the user asked for it by name; otherwise stop." is inserted as the
  first line of body content, followed by one blank line, before "Write a
  handoff document summarising ..." (D19).
- `SKILL.md` L10 (v1.3.1): "naming which skills the next agent should call the
  Skill tool for." becomes "naming which skills the next session should use."
  "Use" is neutral on purpose: the suggested skills are often user-invoked
  (retro, teach, handoff itself), which the next agent cannot load, and the
  person who starts that session runs those. The edit also removes the Claude
  Code tool name (D25, D17).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It held the Codex
  display name, a short description and `policy.allow_implicit_invocation:
  false`, the Codex half of upstream's user-only invocation. Codex reads the
  shared skill root `.agents/skills/`, so outside Claude Code the guard line is
  the only guard left (D19).
- Every other byte is upstream's, including L8's "Save to the temporary
  directory of the user's OS" (nothing is opened, so D20 does not apply) and
  L12's "Reference them by path or URL instead" (the word URL, not an address;
  with the local tracker an issue is referenced by path, D13).
- Note for the global sections (T10): D25 is not listed under "Harness built-ins
  reworded". This skill's suggested-skills line is a rewording, not a load, so
  the load-target gate has no target to check for it.
- Continue: `.continue/prompts/handoff.md` holds only the body, guard line
  included; `argument-hint` is dropped, so no hint shows, and no
  `references/LICENSE` travels. A prompt the user runs satisfies the guard
  (D29).

### implement

_Filled by T04._

### implement-spec

_Filled by T04._

### improve-codebase-architecture

_Filled by T06._

### pr-body

_Filled by T05._

### research

Upstream `skills/engineering/research/`; synced as `.agents/skills/research/`.
Vendored with listed changes, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: research` inserted as the first frontmatter key,
  before "name: research" (D11). `name` and `description` are upstream's; there
  is no `disable-model-invocation`, so no guard line. The description's
  "delegated to a background agent" describes what the user asks for, not an
  instruction, so it stays.
- `SKILL.md` L6 (v1.3.1): "Spin up a **background agent** to do the research, so
  you keep working while it reads." becomes "If you are already running as a
  subagent or background agent, do the job below yourself. Otherwise, if your
  harness can run a **background agent**, spin one up to do the research, so you
  keep working while it reads. If it cannot, give the job to a subagent if your
  harness can run one, or else do it yourself." The first sentence is the
  nesting guard: wayfinder starts research inside a subagent, and upstream's
  unconditional spawn made that agent spawn again, which this fixes (upstream
  issue 530). It comes first so a delegate reads it before any spawn
  instruction. The rest is the capability phrasing with a subagent-then-yourself
  fallback, and "the job below" points at L8 "Its job:", which stays verbatim
  with steps L10-L12, so the steps apply to whoever does the research (D17,
  D18.3).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It held only the Codex
  display name and a short description, no policy block, so no invocation guard
  is lost.
- Every other byte is upstream's. The skill names no command: the
  primary-source reading uses the harness's own web search and fetch, which the
  text never names.
- Continue: `.continue/prompts/research.md` holds only the body. As a prompt the
  user runs, its description no longer fires it from the model, and wayfinder's
  two loads reach it only where the Continue IDE also reads `.claude/skills`
  natively. The body is complete and its fallback lets the user's own session
  do the research inline. No `references/LICENSE` travels (D29).

### retro

Upstream `skills/engineering/retro/`; synced as `.agents/skills/retro/`.
Vendored with listed changes, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: retro` inserted as the first frontmatter key,
  before "name: retro" (D11). `name`, `description` (with its double quotes) and
  `disable-model-invocation: true` are upstream's. The description is
  human-facing and holds no `/name`.
- `SKILL.md` L6-L7 (v1.3.1): upstream's blank L6 stays; the guard line "Run this
  only when the user asked for it by name; otherwise stop." is inserted as the
  first line of body content, followed by one blank line, before "The user has
  asked for a **retrospective**." (D19).
- `SKILL.md` L11 (v1.3.1): "1. Call the Skill tool with `writing-for-agents` for
  the writing style guide." becomes "1. Load the `writing-for-agents` skill for
  the writing style guide." The target is model-invoked, keeps its id and ships
  in this plugin; a user-invoked skill may load a model-invoked one (D17).
- `SKILL.md` L41 (v1.3.1): the `CLAUDE.md`/`AGENTS.md` bullet gains, after
  "usually only for **navigation pointers** to other files.", one space and the
  generated-file clause: "A file carrying the playbook's AUTOGENERATED sentinel
  (on line 1, or on the first line after a `SKILL.md` frontmatter), synced skill
  directories included, is changed in its source (the repo-local `playbook/`
  layer or the plugin that ships it), never by hand." The clause names the
  sentinel and never quotes it. It covers every candidate that targets a
  generated file: the "Global AGENTS.md" category (L20), "No-ops" in steering
  files (L22) and the "Skills" bullet (L44), whose synced skill directories are
  sync output. Those lines stay verbatim and no second sentence is added at L20.
  In a consumer repo `.claude/CLAUDE.md`, `.claude/rules/*.md`, `AGENTS.md` and
  every synced `SKILL.md` carry the sentinel, so a hand edit would be
  overwritten at the next `playbook sync`; elsewhere only the
  guard-generated-outputs hook (Claude Code and OpenCode) catches such an edit
  (D26).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It held the Codex
  display name, a short description and `policy.allow_implicit_invocation:
  false`, the Codex half of upstream's user-only invocation. Codex reads the
  shared skill root `.agents/skills/`, so there the guard line is the only guard
  left (D19).
- Every other byte is upstream's: L13's "searching through session logs on this
  machine", the seven categories at L17-L23, the "reviewer agent" and
  `CODING_STANDARDS.md` wording at L19 and L42 (retro never names code-review,
  so the two-axis-review rename does not reach it, D8), and L44's prose mention
  "Follow the advice in the `writing-for-agents` skill." (a plain name, D17).
  The project-toolchain examples (L18's `package.json`/build-tool `lint` and
  `check` scripts and CI workflow, L19's linter, hook and CI job, L23's dev
  server logs) flag no denied name, so no allowlist entry exists; L18's
  `package.json` is a JS-first consumer-file example kept as written, a stack
  assumption recorded here, not a change (D27).
- Continue: `.continue/prompts/retro.md` holds only the body, guard line and
  generated-file clause included. Step 1's load cannot fire, because
  writing-for-agents is only a prompt there unless the Continue IDE also reads
  `.claude/skills` natively, so the user runs `/writing-for-agents` first to get
  the style guide. `disable-model-invocation` (harmless for a prompt the user
  runs) and `references/LICENSE` do not travel (D29).

### setup-matt-pocock-skills

_Filled by T03._

### tdd

_Filled by T05._

### teach

Upstream `skills/productivity/teach/`; synced as `.agents/skills/teach/`.
Vendored with listed changes, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: teach` inserted as the first frontmatter key,
  before "name: teach" (D11). `name`, `description`,
  `disable-model-invocation: true` and `argument-hint` (with its quotes) are
  upstream's and keep upstream's key order.
- `SKILL.md` L7-L8 (v1.3.1): upstream's blank L7 stays; the guard line "Run this
  only when the user asked for it by name; otherwise stop." is inserted as the
  first line of body content, followed by one blank line, before "The user has
  asked you to teach them something." (D19).
- `SKILL.md` L12 (v1.3.1): "Treat the current directory as a teaching
  workspace." becomes "Treat the current directory as a teaching workspace,
  never this skill's own directory."; the rest of the line stays. This guards
  against upstream issue 377, where agents resolved `./lessons/` and the other
  `./` workspace paths against the skill's install directory. Here the cost is
  higher: the skill now has a `references/` folder next to the workspace's
  `./reference/`, and the moved `LEARNING-RECORD-FORMAT.md` sits one level
  deeper, so a misplaced course would land in a synced skill directory such as
  `.claude/skills/teach/` (D24).
- `SKILL.md` L14, L16 and L17 (v1.3.1): the three links to the moved format
  files keep their text and lose the leading `./` of the target: for example
  `[MISSION-FORMAT.md](./MISSION-FORMAT.md)` becomes
  `[MISSION-FORMAT.md](references/MISSION-FORMAT.md)`, and the same for
  RESOURCES-FORMAT.md and LEARNING-RECORD-FORMAT.md. The anchor
  `[Assets](#assets)` at L19 and the workspace paths `./reference/*.html`,
  `./learning-records/*.md`, `./lessons/*.html`, `./assets/*`, `./lessons/` and
  `./assets/` stay: they are paths in the current directory, not this skill's
  `references/` (D10).
- `SKILL.md` L55 (v1.3.1): "If possible, open the lesson file for the user by
  running a CLI command." becomes "When the lesson file is written, open it for
  the user if your harness can open files, and tell them the absolute path
  either way." From "open it" on this is the shared open-a-file sentence; the
  lead-in clause gives "it" an antecedent because L55 is its own paragraph. "If
  possible" goes because the capability condition replaces it, and "by running
  a CLI command" goes because it implied an OS-specific launcher, an imposed
  tool (D20, D2).
- `MISSION-FORMAT.md` (v1.3.1): moved to `references/MISSION-FORMAT.md`,
  byte-identical; it has no links, addresses or glossary mentions (D10).
- `RESOURCES-FORMAT.md` (v1.3.1): moved to `references/RESOURCES-FORMAT.md`
  (D10) with the two edits that follow.
- `references/RESOURCES-FORMAT.md` L12, L14 and L19 (v1.3.1), inside the fenced
  template (L7-L23): each link keeps its markdown shape and its text, and only
  the target changes, to the placeholder `{link}` in the template's own `{...}`
  style (compare `{gym name}` at L21). The two example addresses and the
  community address go; `r/weightroom` stays as link text. This is the one
  exception to link text as plain text (D24, D4).
- `references/RESOURCES-FORMAT.md` L29 (v1.3.1): `[SKILL.md](./SKILL.md)`
  becomes `[SKILL.md](../SKILL.md)`, so the back-link from the moved file
  resolves to the skill's `SKILL.md` inside the synced skill directory (D10).
- `LEARNING-RECORD-FORMAT.md` (v1.3.1): moved to
  `references/LEARNING-RECORD-FORMAT.md` (D10). L41: after `[[GLOSSARY.md]]` the
  words `(or [[CONTEXT.md]] if the repo already has one)` are inserted, in the
  mention's own wiki-link form; the space after `]]` keeps the link extractor
  from reading `]] (` as an inline link. The wiki-links `[[MISSION.md]]` (L36)
  and `[[GLOSSARY.md]]` name workspace files and need no rewrite (D21).
- `GLOSSARY-FORMAT.md` (v1.3.1): moved to `references/GLOSSARY-FORMAT.md` (D10).
  L3: "`GLOSSARY.md` is the canonical language for this teaching workspace."
  gains " (or `CONTEXT.md` if the repo already has one)" after the code span.
  The L1 heading "# GLOSSARY.md Format" stays, and so does the fenced example
  (L7-L25), which does not name the file. Upstream links to this file from
  nowhere and none is added (D21).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It held the Codex
  display name, a short description and `policy.allow_implicit_invocation:
  false`, the Codex half of upstream's user-only invocation. Codex reads the
  shared skill root `.agents/skills/`, so there the guard line is the only guard
  left (D19).
- Every other byte is upstream's, including L30's "Never trust your parametric
  knowledge" (resource finding uses the harness's own web search and fetch,
  which the text never names), L95's citations ("links to external resources"
  are what the agent writes into the user's lessons, not plugin text), the
  self-authored components of L65-L69 and the U+2026 at `MISSION-FORMAT.md` L16
  and U+2013 at `GLOSSARY-FORMAT.md` L23.
- teach's `GLOSSARY.md` is the teaching workspace's own glossary, not a
  domain glossary. A teaching workspace is normally its own directory, where no
  repo `CONTEXT.md` exists and the fallback never fires; only teach run at a
  repo root that already has a domain `CONTEXT.md` would read that file as its
  glossary. Dropping the two D21 edits above would not affect any other change.
- Note for the global sections (T10): "Restructure" says each moved file keeps
  its content unchanged, but three of teach's moved files and writing-for-agents'
  `SKILL-MECHANICS.md` carry the listed link and glossary edits, so it can read
  "with only the listed link and glossary edits". "Harness built-ins reworded"
  quotes the open-a-file sentence with a capital "Open"; teach's is the same
  sentence from "open it" on, after a lead-in clause.
- Continue: `.continue/prompts/teach.md` holds only the body, without
  `references/`. The three format links (L14, L16, L17) dangle, so MISSION.md,
  RESOURCES.md and the learning records lose their formats, and the unlinked
  glossary format is gone too. `argument-hint` and `references/LICENSE` are
  dropped. The guard line, the L12 workspace clause and the open-the-lesson
  sentence still travel (D29).

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

Upstream `skills/productivity/writing-for-agents/`; synced as `.agents/skills/writing-for-agents/`.
Vendored with listed changes, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: writing-for-agents` inserted as the first
  frontmatter key, before "name: writing-for-agents" (D11). `name` and
  `description` are upstream's. There is no `disable-model-invocation`, so no
  guard line, and the description's trigger "modifying AGENTS.md or CLAUDE.md"
  stays: the skill guides the wording and never writes those files itself.
- `SKILL.md` after L7 (v1.3.1): L6 ("Reference for writing any document an agent
  consumes: ...") and the blank L7 stay byte for byte, and the generated-file
  clause is inserted as its own paragraph, followed by one blank line, before
  L8: "A file carrying the playbook's AUTOGENERATED sentinel (on line 1, or on
  the first line after a `SKILL.md` frontmatter), synced skill directories
  included, is changed in its source (the repo-local `playbook/` layer or the
  plugin that ships it), never by hand." It names the sentinel and never quotes
  it. It sits right after the paragraph that names the document kinds, because
  every branch needs it (a skill, an `AGENTS.md`/`CLAUDE.md`, a pointed-at
  doc), and ahead of the skill-only pointer. In a consumer repo this skill fires
  on exactly the generated files (`AGENTS.md`, `.claude/CLAUDE.md`,
  `.claude/rules/*.md` and synced skill directories), so the clause sends the
  edit to its source (D26).
- `SKILL.md` L8 (v1.3.1): in "read ... for frontmatter",
  ``[`SKILL-MECHANICS.md`](SKILL-MECHANICS.md)`` becomes
  ``[`references/SKILL-MECHANICS.md`](references/SKILL-MECHANICS.md)``. The link
  text is a code-formatted path, so it carries the new location too (D10).
- `SKILL.md` L59 (v1.3.1): in the "By invocation" bullet, the same link becomes
  ``[`references/SKILL-MECHANICS.md`](references/SKILL-MECHANICS.md)``, text and
  target (D10).
- `SKILL-MECHANICS.md` (v1.3.1): moved to `references/SKILL-MECHANICS.md` (D10).
  L3: ``[`writing-for-agents`](SKILL.md)`` becomes
  ``[`writing-for-agents`](../SKILL.md)``; the link text is the skill name, so it
  stays. The three inline `SKILL.md` mentions (L3, L9 and L18) name the skill's
  main file, which did not move, so they stay too.
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It held only the Codex
  display name and a short description, no policy block.
- Verbatim on purpose (D28): the sibling-file advice, `SKILL.md` L35 ("Spans a
  sibling file in the same folder ...") and `SKILL-MECHANICS.md` L14 ("Push it
  to a plain file outside the skill system ..."). The engine syncs only
  `SKILL.md`, `scripts/` and `references/`, and this skill's own sibling file
  had to move, but Matt's advice stays. `SKILL-MECHANICS.md` L10 stays too, with
  no qualifier on `disable-model-invocation`: support for a frontmatter key is
  not a harness built-in, and the plugin README says that only Claude Code
  honours it.
- Every other byte is upstream's, including L49's "a hand-off or a subagent
  dispatch" (it explains context boundaries and does not instruct a dispatch),
  the `AGENTS.md`/`CLAUDE.md` mentions at L6, L12 and L24 (they name document
  kinds), the U+2192 arrows at L69 and L70, and L79's `package.json` example,
  a JS-first consumer-file example kept as written: a stack assumption recorded
  here, not a change (D27).
- Continue: `.continue/prompts/writing-for-agents.md` holds only the body,
  generated-file clause included. As a prompt the user runs, the model no
  longer reaches it when editing skills, `AGENTS.md` or `CLAUDE.md`, and retro's
  step-1 load cannot reach it. The two `references/SKILL-MECHANICS.md` links
  dangle, so the invocation and router-skill mechanics are lost. No
  `references/LICENSE` travels (D29).
