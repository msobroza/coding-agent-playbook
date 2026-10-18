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

Upstream `skills/engineering/ask-matt/`; synced as `.agents/skills/ask-matt/`.
Vendored with listed changes, user-invoked. Router labels keep their `/name`
throughout (human-facing, Cross-skill references); only `/clear` and
`/compact` lose theirs.

- `SKILL.md` L2 (v1.3.1): `id: ask-matt` inserted as the first frontmatter key,
  before "name: ask-matt" (Frontmatter). `name`, the 83-character description
  and `disable-model-invocation` are byte-identical to upstream L2-L4; the
  description keeps "A router over the skills in this repo." verbatim (D28).
- `SKILL.md` L6 (v1.3.1): after the blank line that closes the frontmatter, the
  guard line "Run this only when the user asked for it by name; otherwise stop."
  inserted as its own paragraph above "# Ask Matt", the first line of body
  content (D19).
- `SKILL.md` L17 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md` (D21).
- `SKILL.md` L20 (v1.3.1): the label `/prototype` becomes
  `/throwaway-prototype` (Renames); the plain noun "a prototype" on L18 stays.
- `SKILL.md` L24 (v1.3.1): "**`/clear`ing context between each one**" becomes
  "**starting a fresh context between each one**" (D17).
- `SKILL.md` L25 (v1.3.1): " (one ticket at a time where your harness cannot
  run subagents)" inserted after "in parallel", mirroring implement-spec's
  sequential fallback (D17, D18.5).
- `SKILL.md` L28 (v1.3.1): the three `/code-review` labels become
  `/two-axis-review` (Renames).
- `SKILL.md` L30 (v1.3.1): the label `/pr` becomes `/pr-body` (Renames); "It's
  model-invoked" stays, since pr-body has no `disable-model-invocation`.
- `SKILL.md` L32 (v1.3.1): `/code-review` becomes `/two-axis-review`
  (Renames); "steering files" stays.
- `SKILL.md` L38 (v1.3.1): the bold "smart zone" link loses its external
  target and keeps its text as plain bold text (No external URLs); "`/compact`
  at the nearest phase boundary" becomes "summarise and start a fresh context
  at the nearest phase boundary" (D17).
- `SKILL.md` L44-L47 (v1.3.1): the triage on-ramp bullet, its continuation
  paragraph and their two blank lines deleted (D7, Dropped and why). L11's "two
  **on-ramps**" is left as written: two on-ramps remain (diagnosing-bugs,
  wayfinder), so the line is now accurate.
- `SKILL.md` L64 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md` (D21).
- `SKILL.md` L72 (v1.3.1): the option label "**`/clear`**" becomes "**Clear**
  (start a fresh context)" (D17).
- `SKILL.md` L74 (v1.3.1): " (if your harness can run one)" inserted after the
  "**Subagent**" label (D17).
- `SKILL.md` L75 (v1.3.1): the option label "**`/compact`**" becomes
  "**Compact** (summarise this context, then start a fresh context from the
  summary)"; Matt's description of the option stays (D17).
- `SKILL.md` L77 (v1.3.1): the link target becomes
  `references/PHASE-BOUNDARIES.md`, link text unchanged (Restructure); ", if
  your harness can run subagents," inserted after "continue or" (D17).
- `SKILL.md` L83 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md` (D21).
- `SKILL.md` L84 (v1.3.1): "and `/triage`, `/wayfinder` and
  `/improve-codebase-architecture` all run it internally" becomes "and
  `/wayfinder` and `/improve-codebase-architecture` both run it internally"
  (D7).
- `SKILL.md` L85 (v1.3.1): the label `/prototype` becomes
  `/throwaway-prototype` (Renames); the noun "the prototype itself" and the
  branch name `prototype/<name>` stay, since neither is a skill id.
- `SKILL.md` L86 (v1.3.1): one sentence inserted after "Keep working while it
  reads.": "If your harness cannot run a background agent, the agent hands the
  reading to a subagent, or does it itself in this session." Matt's sentences
  are byte-identical (D17, D18.3).
- `SKILL.md` L88 (v1.3.1): "an interactive bash script that opens each URL,
  captures each value, and writes it into `.env` and GitHub secrets" becomes
  "an interactive Python script that opens each URL, captures each value,
  writes it into `.env`, and guides you through setting each GitHub secret or
  variable by hand", matching the shipped `scripts/wizard_template.py` (D22,
  D2). "Model-invoked" stays: wizard has no `disable-model-invocation`.
- `SKILL.md` L89 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md` (D21).
- `PHASE-BOUNDARIES.md`: moved to `references/PHASE-BOUNDARIES.md`
  (Restructure). It has no links, so nothing in it points back at `SKILL.md`;
  it keeps its 55 lines and upstream numbering.
- `references/PHASE-BOUNDARIES.md` L5 (v1.3.1): ", if your harness can run
  subagents," inserted after "continue, or"; "Compacting mid-phase" stays, a
  plain verb (D17).
- `references/PHASE-BOUNDARIES.md` L12 (v1.3.1): the label cell "**`/clear`**"
  becomes "**Clear** (start a fresh context)"; the description cell and its
  padding are byte-identical (D17).
- `references/PHASE-BOUNDARIES.md` L14 (v1.3.1): the label cell "**Subagent**"
  gains " (if your harness can run one)" (D17).
- `references/PHASE-BOUNDARIES.md` L15 (v1.3.1): the label cell
  "**`/compact`**" becomes "**Compact** (summarise, then start a fresh context
  from the summary)" (D17). The table is not realigned: upstream's L13 and L15
  rows were already wider than the separator row, and ruff stays off this
  markdown.
- `references/PHASE-BOUNDARIES.md` L21 (v1.3.1): the "smart zone" link loses
  its external target and stays as plain text (No external URLs).
- `references/PHASE-BOUNDARIES.md` L23 (v1.3.1): "If so, **`/clear`**." becomes
  "If so, **clear** (start a fresh context)." and "`/clear` also isn't
  terminal" becomes "Clearing also isn't terminal" (D17).
- `references/PHASE-BOUNDARIES.md` L36 (v1.3.1): "Then send it to a
  **subagent** and leave this session untouched." becomes "Then, if your
  harness can run subagents, send it to a **subagent** and leave this session
  untouched; if it can't, go on to question 5.", so a yes that cannot be acted
  on falls through the tree (D17).
- `references/PHASE-BOUNDARIES.md` L38 (v1.3.1): the heading "**5. Otherwise,
  `/compact`.**" becomes "**5. Otherwise, compact (summarise, then start a
  fresh context from the summary).**", and the Claude Code argument syntax goes
  from the example, leaving "(`we're going to QA this area`)" (D17).
- `references/PHASE-BOUNDARIES.md` L40 (v1.3.1): "`/compact` is" becomes
  "Starting a fresh context from a summary is" (D17).
- `references/PHASE-BOUNDARIES.md` L49 (v1.3.1): `/compact` in the Secondary
  row becomes "fresh context from a summary"; the `/handoff` label stays and
  the row is not realigned (D17).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure); it held the Codex display
  name "Ask Matt", the short description "Find the right skill or workflow" and
  `policy.allow_implicit_invocation: false`. With it Codex loses this skill's
  user-only invocation policy; what remains is `disable-model-invocation`,
  which only Claude Code honours, and the guard line (D10, D19).
- Kept verbatim on purpose: the H1 "# Ask Matt" and the label
  `/setup-matt-pocock-skills` (no collision, no coupling marker); L36's plain
  verbs "don't compact or clear", "before you clear; after clearing" and "starts
  fresh"; L95's "triage labels" and "Custom issue trackers also work." (setup is
  kept and always writes the labels file); PHASE-BOUNDARIES L29's illustrative
  "(Claude → Codex)" pair. The allowlist has no entry: no word is in command
  position.
- For T10 (global sections): "Harness built-ins reworded" says `/clear` and
  `/compact` become "start a fresh context"; here Compact is worded as a fresh
  context started from a summary, so the five phase-boundary options stay
  distinct. "Imposed tools removed" may also list this router's "bash script"
  wording at L88, which follows wizard's Python port.
- Continue: `.continue/prompts/ask-matt.md` holds only the `SKILL.md` body,
  guard line included, which a user-started prompt satisfies. `references/`
  does not travel, so the `references/PHASE-BOUNDARIES.md` link dangles and
  the ordered five-question tree and the primary/secondary trade-off table are
  lost, leaving only the five-option summary. The "model-invoked, so the agent
  reaches for it" claims at L30, L62 and L88 do not hold there, and no licence
  copy travels (D29).

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

_Filled by T08._

### implement

_Filled by T04._

### implement-spec

_Filled by T04._

### improve-codebase-architecture

_Filled by T06._

### pr-body

Upstream `skills/engineering/pr/`; synced as `.agents/skills/pr-body/`.
Vendored with listed changes, model-invoked.

- Directory and `SKILL.md` L2 (v1.3.1): `pr` renamed `pr-body`, directory
  `skills/pr-body/` and "name: pr" to "name: pr-body", because Claude Code
  registers a feature-gated bundled `pr` skill (D8). Inbound references:
  `references/CREDITS.md` L3 (below) and ask-matt's `/pr` router label, which
  ask-matt's ticket changes to `/pr-body`.
- `SKILL.md` L2 (v1.3.1): `id: pr-body` inserted as the first frontmatter key,
  before the `name` line (D11).
- `SKILL.md` L9 (v1.3.1): the `metadata.credits.url` line deleted, the only URL
  in `SKILL.md`; L4-L8 (`metadata`, `credits`, `skill: show-me`,
  `author: Dex Horthy`, `organisation: Humanlayer`, upstream's spelling) stay
  byte for byte (D6, D11, D4).
- `SKILL.md` L37 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md`; nothing else on the line changes
  (D21).
- `CREDITS.md` (v1.3.1): moved to `references/CREDITS.md`; nothing links to it,
  so no link is rewritten; L1-L2 unchanged (D6, D10).
- `references/CREDITS.md` L3 (v1.3.1): the two links keep only their link text,
  "Dex Horthy" and `show-me`, so the phrase reads "come from Dex Horthy's
  `show-me` skill" (D6, D4); the code span `pr` becomes `pr-body` (D8); the rest
  of the line, the "it isn't part of this repo" parenthetical included, is
  upstream's.
- `references/LICENSE-show-me`: added, HumanLayer's MIT notice, laid out like
  the plugin `LICENSE` with line 3 "Copyright (c) 2026 HumanLayer" and lines
  4-21 identical to it; the upstream checkout holds no HumanLayer licence file,
  so it is built from D6's facts (D6).
- Third-party content (D6): `.agents/skills/pr-body/SKILL.md`'s Summary section
  (upstream `skills/engineering/pr/SKILL.md` L39-L156: the menu of visuals and
  its Guidance) reproduces, almost word for word, the show-me skill by Dex
  Horthy (HumanLayer): repository humanlayer/skills, commit
  653b6411c1f70c275a18e37673b042ff99f67ceb, MIT, Copyright (c) 2026 HumanLayer.
  It ships as upstream v1.3.1 had it, minus the URL removals listed above, and
  is not authored by Matt Pocock. HumanLayer's MIT notice ships as
  `.agents/skills/pr-body/references/LICENSE-show-me`; the credit ships as
  `references/CREDITS.md` and the `metadata.credits` frontmatter block. The
  global "Third-party content" section already states this; nothing to fold in.
- Stack assumption (D27): the TSX/JSX and frontend examples stay verbatim: L63-L70
  (the component tree with `apps/example/src/routes/session.tsx`), L95-L104 (the
  JSX component diff), L111 (`show-me.ts`), L143-L150 (the `ts` fence) and L170
  ("layout shift, breakages for consumers, mobile responsiveness").
- The `mermaid` fence at L83 and "Mermaid" at L81 and in `CREDITS.md` L3 are
  markup the forge renders inside a PR body, not a CDN asset; no allowlist
  entry.
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure); it held only the Codex
  display name "PR" and a short description.
- Every other byte is upstream's: the box-drawing trees at L76-L78 and
  L110-L116 and the leading-space context lines of the `diff` fences. The file
  stays 170 lines (the `id` line added, the `url` line removed).
- Sync re-dumps the frontmatter, so the `metadata` block's quoting may differ in
  the synced copies; the Agent Harness adapter moves `metadata` to its manifest
  sidecar.
- Continue: `.continue/prompts/pr-body.md` holds only the body. The
  `metadata.credits` block, `references/CREDITS.md`, `references/LICENSE-show-me`
  and `references/LICENSE` are all dropped, so neither the HumanLayer notice nor
  the Matt Pocock notice travels, and a repo that renders this skill only for
  Continue keeps both notices itself. As a user-started prompt, the model no
  longer reaches for it on its own whenever it writes a PR (D29).

### research

_Filled by T08._

### retro

_Filled by T08._

### setup-matt-pocock-skills

Upstream `skills/engineering/setup-matt-pocock-skills/`; synced as
`.agents/skills/setup-matt-pocock-skills/`. Vendored with listed changes,
user-invoked. `SKILL.md` shrinks from 116 to 81 lines; the skill directory holds
`SKILL.md` and `references/` (`LICENSE`, `domain.md`, `issue-tracker-local.md`,
`triage-labels.md`).

`SKILL.md`:

- L2 (v1.3.1): `id: setup-matt-pocock-skills` inserted as the first frontmatter
  key, before "name: setup-matt-pocock-skills" (D11). The other keys and the
  quoted description are byte-identical.
- L6 (v1.3.1): after the blank line that closes the frontmatter, the guard line
  "Run this only when the user asked for it by name; otherwise stop." inserted
  as its own paragraph, above the H1 (D19).
- L11 (v1.3.1): "(GitHub by default; local markdown is also supported out of
  the box)" became "(local markdown by default; any other tracker works once
  the user describes it)" (D13, D14).
- L13 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)" inserted after
  the code span `GLOSSARY.md` (D21).
- L24 (v1.3.1): the `AGENTS.md`/`CLAUDE.md` check became read-only: "is there
  an old `## Agent skills` section in either? Read them only to answer that:
  this skill never edits or creates either file (step 5 says what to tell the
  user)." (D14).
- L25 (v1.3.1): the `CONTEXT.md` and `CONTEXT-MAP.md` fallbacks inserted after
  the code spans `GLOSSARY.md` and `GLOSSARY-MAP.md` (D21).
- L29 (v1.3.1): the "Is the `triage` skill installed?" bullet deleted (D7,
  D14).
- L30 (v1.3.1): kept verbatim on purpose: the JS-only monorepo markers
  (`pnpm-workspace.yaml`, the `workspaces` field of `package.json`) are a
  consumer-repo file read and a stack assumption, not a command (D28).
- L36 (v1.3.1): "(Section B when `triage` isn't installed, Section C when
  there's no monorepo)" became "(Section C when there's no monorepo). Section B
  is written without asking." (D7, D14).
- L40 (v1.3.1): `triage` left the explainer's skill list (D7), and the clause
  "call `gh issue create`," went (D2, D13): "whether to write a markdown file
  under `.scratch/` or follow some other workflow you describe".
- L42 (v1.3.1): the GitHub/GitLab default posture, with the bare GitLab host
  name, became "Default posture: propose local markdown, even when a
  `git remote` points at a forge; a user who tracks work in that forge's
  issues, or anywhere else, picks **Other**. Offer:" (D13, D14).
- L44 (v1.3.1): the **GitHub** option ("uses the `gh` CLI") deleted (D2, D13,
  D14).
- L45 (v1.3.1): the **GitLab** option deleted; it named `glab` and carried the
  skill's only URL (D2, D4, D13, D14).
- L46 (v1.3.1): "(good for solo projects or repos without a remote)" became
  "(the default; needs no remote or CLI)" (D14).
- L47 (v1.3.1): **Other** keeps "(Jira, Linear, etc.)" verbatim; the
  one-paragraph freeform description became a description "for each section
  of" the local seed (a link to `./references/issue-tracker-local.md`) "after
  its Conventions: publish, fetch, close, blocking (default: a plain
  `Blocked by:` line near the top of each ticket) and the Wayfinding
  operations", recorded under each section's heading (D13, D14).
- L49 (v1.3.1): the two sentences about the "PRs as a request surface" flag
  deleted; "Record the choice in `docs/agents/issue-tracker.md`." stays (D7,
  D14).
- L51-L57 (v1.3.1): Section B is no longer gated on `triage` and asks no
  question: "Always written, without asking: `to-spec` and `to-tickets` apply
  these labels.", then the five default roles, "Write them as-is.", and label
  overrides through the step 3 draft. The question at L53-L55 is deleted (D7,
  D14).
- L59 and L61 (v1.3.1): the `CONTEXT.md` and `CONTEXT-MAP.md` fallbacks
  inserted after every `GLOSSARY.md` and `GLOSSARY-MAP.md` code span (D21).
- L67 (v1.3.1): the "`## Agent skills` block to add" draft bullet deleted (D14,
  D15).
- L68 (v1.3.1): " (the last only when `triage` is installed)" deleted (D7,
  D14).
- L74-L104 (v1.3.1), step 4: (a) removed the "Pick the file to edit"
  subsection, L74-L82 (D14); (b) removed "The block:" and the fenced
  `## Agent skills` block, L84-L100, which the plugin always rule
  `mattpocock-skills-tracker` replaces (D15); (c) removed L102's
  `### Triage labels` condition (D7, D14); (d) added "Write only
  `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and
  `docs/agents/domain.md`. Never edit or create `CLAUDE.md` or `AGENTS.md`: the
  always rule this plugin ships (`mattpocock-skills-tracker`) already points
  every session at these files.", and "Then write" became "Write" at L104
  (D14).
- L106-L110 (v1.3.1): the `issue-tracker-github.md` and
  `issue-tracker-gitlab.md` seed links deleted (D14); the three remaining links
  point at `./references/` (D10); "(only if `triage` is installed)" deleted (D7,
  D14).
- L112 (v1.3.1): the "other" tracker is written "under the same `##` headings
  as" the local seed (a link to `./references/issue-tracker-local.md`) "after
  its Conventions; keep the `## Wayfinding operations` heading verbatim, since
  `wayfinder` looks it up by name." (D14, D16).
- L116 (v1.3.1), step 5: appended "If exploration found an old
  `## Agent skills` section in a root `CLAUDE.md` or `AGENTS.md`, tell them
  the always rule this plugin ships (`mattpocock-skills-tracker`) supersedes
  it and that they may delete it; don't edit the file yourself." (D14).
- Kept verbatim on purpose: L23 "is this a GitHub repo? Which one?" (git is
  allowed, D2, and the posture line uses its answer).

`references/domain.md` (moved from the skill root, D10; no links; still 51
lines):

- L7, L8, L26 and L43 (v1.3.1): the `CONTEXT.md` and `CONTEXT-MAP.md` fallbacks
  inserted after each `GLOSSARY.md` and `GLOSSARY-MAP.md` mention on prose lines
  (D21). The fenced trees L17-L24 and L28-L39 stay byte-identical, box-drawing
  characters and arrows included.
- L11 and L45 (v1.3.1): the leading slashes of `/domain-modeling`,
  `/grill-with-docs` and `/improve-codebase-architecture` dropped, since the
  consumer's `docs/agents/domain.md` is agent-facing prose (D17).

`references/issue-tracker-local.md` (moved from the skill root, D10; no links;
30 lines grow to 41):

- After L9 (v1.3.1): "Every issue file (the spec, each ticket) and every map
  opens with a `# <title>` heading: its name" (D16).
- After L11 (v1.3.1): "`.scratch/` is untracked working state: never stage it
  in a commit" and "Worktrees do not contain untracked files: when you point a
  subagent or a worktree at a spec, ticket or map, give its absolute path in
  the main checkout" (D16).
- After L19 (v1.3.1): the new section `## When a skill says "close" or
  "resolve" a ticket` (closed is a terminal `Status:`, `resolved` or
  `out-of-scope`; an implementation ticket is set `resolved` once merged;
  to-tickets' bold `**Status:** ready-for-agent` line is rewritten in place)
  and the new section `## Blocking` (a plain `Blocked by:` line by default,
  bold in a to-tickets ticket; unblocked when every ticket it lists is closed)
  (D14, D16).
- L23 (v1.3.1): "Used by `/wayfinder`." became "Used by `wayfinder`."; the
  `## Wayfinding operations` heading at L21 stays verbatim (D16, D17).
- L26 (v1.3.1): the `Status:` values gained `/out-of-scope` (D16).
- L27 (v1.3.1): "is `resolved`" became "is closed (`resolved` or
  `out-of-scope`)" (D16).
- L30 (v1.3.1): appended "Only the session driving the map appends to
  `map.md`; a research subagent writes only its own ticket file." (D16).
- L10's code span `triage-labels.md` is not a link and stays; it names the
  consumer's `docs/agents/triage-labels.md`, which Section B now always writes.
- The `prototype` ticket type at L26 is not a skill id and stays (D8).

Other files:

- `references/triage-labels.md`: moved from the skill root, byte-identical
  (D10). The "Label in mattpocock/skills" column header is a repository name,
  not a URL or a coupling marker.
- `issue-tracker-github.md` and `issue-tracker-gitlab.md`: not shipped. They
  told the agent to run `gh`, `glab`, `jq` and `gh api`/`glab api`, the GitLab
  one held a URL (L3), and they alone defined the "PRs (MRs) as a request
  surface" flag that triage read. Only the local-markdown template ships. A
  GitHub or GitLab user takes **Other** and records the same sections in their
  own words (D2, D4, D13, D14).
- `agents/openai.yaml`: not shipped (D10). With it Codex loses this skill's
  `policy.allow_implicit_invocation: false`; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line (D19).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (D4).
- Added, not vendored: the plugin always rule
  `rules/mattpocock-skills-tracker.md` replaces the "## Agent skills" block
  upstream's step 4 wrote into `CLAUDE.md` or `AGENTS.md` (D15); see "Plugin
  always rule".

For T10 (global sections, recorded here per section 5.3):

- "Plugin always rule": the rule narrows "when they are missing" to "If a skill
  needs one that is missing", opens with "When present", so it never presents
  the setup-only files as always there and does not prompt for setup in
  sessions that use no tracker skill; its `.scratch/` sentence reads "never
  stage or commit it". It is `priority: 50`, after the core always rules.
- "Dropped and why", triage: upstream `skills/engineering/triage/` (`SKILL.md`
  112 lines, `AGENT-BRIEF.md` 207, `OUT-OF-SCOPE.md` 105, `agents/openai.yaml`
  5) works with labels, reporter replies, `wontfix` closes, an
  `.out-of-scope/` knowledge base and a request-surface flag that only the
  dropped GitHub and GitLab seeds defined. A repo-local triage reads the same
  `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`, and with no
  request-surface flag in the local seed it handles issues only.
- "Imposed tools removed": setup's own `SKILL.md` also lost `gh issue create`
  (L40), the `gh` option (L44), the `glab` option and its URL (L45) and the
  bare GitLab host name (L42), besides the two seeds.

Continue: `.continue/prompts/setup-matt-pocock-skills.md` holds only the body,
guard line included. `references/` does not travel, so the three seed links
dangle and the agent writes `docs/agents/*.md` from the prose alone, without the
seeds' close, blocking and Wayfinding operations conventions, the `.scratch/`
and absolute-path rules, the domain-doc consumer rules and the label table. No
licence copy travels and `disable-model-invocation` is dropped, but a Continue
prompt is always started by the user. The always rule still reaches Continue as
its own `.continue/rules/` file.

### tdd

Upstream `skills/engineering/tdd/`; synced as `.agents/skills/tdd/`.
Vendored with listed changes, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: tdd` inserted as the first frontmatter key,
  before "name: tdd" (D11). `name` and `description` are upstream's; no
  `disable-model-invocation`, because implement and implement-spec load it.
- `tests.md` and `mocking.md` (v1.3.1): moved to `references/tests.md` and
  `references/mocking.md` with their bytes unchanged; neither links to another
  file (D10).
- `SKILL.md` L10 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md`; upstream's own "(if it exists)"
  stays, so the two parentheticals stand side by side (D21).
- `SKILL.md` L16 (v1.3.1): the link targets `tests.md` and `mocking.md` become
  `references/tests.md` and `references/mocking.md`; the plain link texts stay
  (D10).
- `SKILL.md` L26 (v1.3.1): "call the Skill tool with "codebase-design" for the
  vocabulary." becomes "load the `codebase-design` skill for the vocabulary.";
  the rest of the line is upstream's (D17).
- `SKILL.md` L38 (v1.3.1): the code span `code-review` becomes
  `two-axis-review`, a prose mention of the renamed skill (D8).
- Stack assumption (D27): the TypeScript and Jest examples stay verbatim:
  `SKILL.md` L31 (`expect(add(a, b)).toBe(a + b)`); `references/tests.md` fences
  L7-L15, L29-L36, L47-L61 and L65-L77 (`jest.mock` at L32);
  `references/mocking.md` fences L24-L35 and L41-L53 (`process.env.STRIPE_KEY`
  at L32, `fetch` at L44-L46 and L51). None names an imposed tool, so there is
  no allowlist entry.
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure); it held only the Codex
  display name "TDD" and a short description.
- Every other byte is upstream's, including the U+2192 arrows at L8, L32 and
  L38.
- Continue: `.continue/prompts/tdd.md` holds only the body; `references/tests.md`
  and `references/mocking.md` do not travel, so the L16 links are dead, and no
  `references/LICENSE` travels. The `codebase-design` load, and the inbound
  loads from implement and implement-spec, resolve only where the Continue IDE
  also reads the skills natively from `.claude/skills`. As a user-started
  prompt, tdd is no longer picked up from its description (D29).

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

Upstream `skills/engineering/to-spec/`; synced as `.agents/skills/to-spec/`.
Vendored with listed changes, user-invoked. `SKILL.md` grows from 75 to 78
lines; the skill directory holds `SKILL.md` and `references/LICENSE`.

- `SKILL.md` L2 (v1.3.1): `id: to-spec` inserted as the first frontmatter key,
  before "name: to-spec" (D11). The other keys and the quoted description are
  byte-identical.
- `SKILL.md` L6 (v1.3.1): after the blank line that closes the frontmatter, the
  guard line "Run this only when the user asked for it by name; otherwise stop."
  inserted as its own paragraph, the first line of body content (D19).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (D4).
- `agents/openai.yaml`: not shipped (D10). With it Codex loses this skill's
  `policy.allow_implicit_invocation: false`; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line (D19).
- Kept verbatim on purpose: L9 "If not, tell the user to run
  `/setup-matt-pocock-skills`." is a human-facing pointer, so the slash stays
  (D17), and its "should have been provided to you" is made true by the plugin
  always rule and the always-written `docs/agents/triage-labels.md` (D14, D15);
  L13 names the glossary abstractly, so no `CONTEXT.md` fallback applies (D21);
  L19's "no need for additional triage" is the activity, not the dropped skill
  (D7); L57's "a prototype" is a common noun, not the renamed skill (D8).
- Continue: `.continue/prompts/to-spec.md` holds only the body, guard line
  included, with no `references/LICENSE` and no `disable-model-invocation`.
  Nothing functional is lost: the body is self-contained, the tracker docs live
  in the consumer repo, the always rule reaches Continue as its own rule file,
  and a Continue prompt is always started by the user.

### to-tickets

Upstream `skills/engineering/to-tickets/`; synced as
`.agents/skills/to-tickets/`. Vendored with listed changes, user-invoked.
`SKILL.md` grows from 105 to 108 lines; the skill directory holds `SKILL.md` and
`references/LICENSE`.

- `SKILL.md` L2 (v1.3.1): `id: to-tickets` inserted as the first frontmatter
  key, before "name: to-tickets" (D11). The other keys and the unquoted
  description are byte-identical.
- `SKILL.md` L6 (v1.3.1): after the blank line that closes the frontmatter, the
  guard line "Run this only when the user asked for it by name; otherwise stop."
  inserted as its own paragraph, above the H1 (D19).
- `SKILL.md` L60 (v1.3.1): "the tracker `/setup-matt-pocock-skills`
  configured" became "the tracker `setup-matt-pocock-skills` configured": this
  is agent-facing process prose, not a "tell the user to run" line (D17).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (D4).
- `agents/openai.yaml`: not shipped (D10). With it Codex loses this skill's
  `policy.allow_implicit_invocation: false`; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line (D19).
- Kept verbatim on purpose: L11 "If not, tell the user to run
  `/setup-matt-pocock-skills`." (human-facing, D17); L21 names the glossary
  abstractly (no D21 edit); L62's local branch already matches the shipped
  seed; L63 "(GitHub, Linear, …)" names products, not CLIs, and its native
  blocking relationship now comes from the Blocking section setup records
  (D13, D14); L65's "blockers are all done" reads as closed under the seed;
  L71's `# <NN>: <Ticket title>` already is the title heading and L77's
  `**Status:** ready-for-agent` is the bold line the seed's close section
  rewrites in place (D16); L105's "a prototype" is a common noun (D8); L17's
  "an issue number or URL" is the word, not a URL. The en dash at L40, the
  arrows at L62-L63 and the ellipsis at L63 are upstream's characters.
- Continue: `.continue/prompts/to-tickets.md` holds only the body, guard line
  included, with no `references/LICENSE` and no `disable-model-invocation`.
  Nothing functional is lost: the body and both ticket templates are inline,
  the tracker docs live in the consumer repo, and the always rule reaches
  Continue as its own rule file.

### two-axis-review

Upstream `skills/engineering/code-review/`; synced as `.agents/skills/two-axis-review/`.
Vendored with listed changes, model-invoked.

- Directory and `SKILL.md` L2 (v1.3.1): `code-review` renamed
  `two-axis-review`, directory `skills/two-axis-review/` and "name:
  code-review" to "name: two-axis-review", because the id collides with Claude
  Code's bundled `code-review` skill (D8). Inbound references: tdd `SKILL.md`
  L38 (this ticket), implement L13 and implement-spec L36 (T04), and ask-matt's
  `/code-review` router labels at L28 and L32 (ask-matt's ticket).
- `SKILL.md` L2 (v1.3.1): `id: two-axis-review` inserted as the first
  frontmatter key, before the `name` line (D11).
- `SKILL.md` L3 (v1.3.1): the description is kept verbatim, double quotes and
  the two `\"` escapes included: 419 characters between the quotes, 417 once
  parsed. Bundled plugins are exempt from the 300-character lint (D28).
- `SKILL.md` L11 (v1.3.1): "Both axes run as **parallel sub-agents** so they
  don't pollute each other's context, then this skill aggregates their
  findings." becomes "If your harness can run subagents, both axes run as
  **parallel sub-agents** so they don't pollute each other's context, then this
  skill aggregates their findings; otherwise you run the two reviews yourself,
  one after the other, as step 4 describes, and aggregate them the same way."
  (D17, D18.6).
- `SKILL.md` after L59 (v1.3.1): under the unchanged "### 4. Spawn both
  sub-agents in parallel" heading, a paragraph and a blank line inserted:
  without subagents, run the Standards review first, with any spec contents step
  2 fetched set aside, write it in full, then run the Spec review (or report "no
  spec available"), and never revise the Standards report afterwards (D17,
  D18.6). The other sub-agent sentences (L23, L32, L60, L63, L66, L72) stay
  verbatim; step 2 is not changed.
- `SKILL.md` L29 (v1.3.1): the "GitLab `!67`" example stays verbatim (D18.7).
- `SKILL.md` L13 (v1.3.1): "tell the user to run `/setup-matt-pocock-skills`"
  keeps the slash (D17); the plugin always rule makes "The issue tracker should
  have been provided to you" true.
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure); it held only the Codex
  display name "Code Review", stale after the rename, and a short description.
- The git commands at L21 and L23 are allowed (D2); no allowlist entry.
- Every other byte is upstream's, including the fifteen U+2192 arrows. The file
  grows from 87 to 90 lines.
- Continue: `.continue/prompts/two-axis-review.md` holds only the body, with no
  `references/LICENSE`. As a user-started prompt it is no longer picked up from
  its description; the loads from implement and implement-spec resolve only
  where the Continue IDE also reads the skill natively from `.claude/skills`;
  where subagents are unavailable, the step-4 sequential fallback is the only
  path (D29).

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
