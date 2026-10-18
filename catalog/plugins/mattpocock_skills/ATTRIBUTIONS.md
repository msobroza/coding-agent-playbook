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

Upstream `skills/engineering/codebase-design/`; synced as `.agents/skills/codebase-design/`.
Vendored with listed changes, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: codebase-design` inserted as the first
  frontmatter key, before "name: codebase-design" (Frontmatter, D11). The
  description (265 characters) stays verbatim, and there is no
  `disable-model-invocation`: improve-codebase-architecture and tdd load this
  skill, so it stays model-invoked.
- `DEEPENING.md` and `DESIGN-IT-TWICE.md` (v1.3.1): moved to
  `references/DEEPENING.md` and `references/DESIGN-IT-TWICE.md` (Restructure,
  D10).
- `SKILL.md` L113 (v1.3.1): the link target `DEEPENING.md` becomes
  `references/DEEPENING.md`; the link text stays (D10).
- `SKILL.md` L114 (v1.3.1): the link target `DESIGN-IT-TWICE.md` becomes
  `references/DESIGN-IT-TWICE.md`; "spin up parallel sub-agents to design the
  interface several radically different ways" stays verbatim, because it
  describes the reference, whose operative step carries the fallback (D10,
  D17).
- `references/DEEPENING.md` L3 (v1.3.1): the back-link target `SKILL.md`
  becomes `../SKILL.md` (D10).
- `references/DESIGN-IT-TWICE.md` L5 (v1.3.1): the back-link target `SKILL.md`
  becomes `../SKILL.md` (D10).
- `references/DESIGN-IT-TWICE.md` L21 (v1.3.1): "Spawn 3+ sub-agents in
  parallel." becomes "If your harness can run subagents, spawn 3+ sub-agents in
  parallel; otherwise draft the 3+ designs yourself, one at a time, each held to
  its own brief, its own design constraint and the output list below, finishing
  one before you start the next."; the rest of the line stays. The fallback
  keeps the step's intent: independent briefs, one constraint each, the same
  five outputs. L3, L11, L17, L19, L23 and L32 name or describe the pattern and
  stay verbatim (D17).
- `references/DESIGN-IT-TWICE.md` L30 (v1.3.1): the back-link target
  `SKILL.md` becomes `../SKILL.md`, and " (or CONTEXT.md if the repo already has
  one)" is inserted after "GLOSSARY.md", in plain text as upstream writes the
  name (D10, D21).
- `references/DESIGN-IT-TWICE.md` L14, L23 and L37 (v1.3.1): the links to
  `DEEPENING.md` stay as written, because both files moved together
  (Restructure).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It held only a display
  name and a short description, no invocation policy, so Codex loses only
  display metadata.
- Stack assumptions, no text change: the two `typescript` blocks at `SKILL.md`
  L73-L81 and L85-L93 (`new StripeGateway()` included), L108's "the TypeScript
  `interface` keyword" and `references/DEEPENING.md` L15's "PGLite for
  Postgres" stay verbatim (Consumer-repo conventions, D27). No line names an
  imposed tool, so the skill has no project-toolchain allowlist entry.
- Every other byte is upstream's, including the box-drawing diagrams at
  `SKILL.md` L35-L41 and L47-L51 and the U+2013 en dash at
  `references/DESIGN-IT-TWICE.md` L25.
- Continue: `.continue/prompts/codebase-design.md` holds only the `SKILL.md`
  body. The glossary, the deep and shallow diagrams, the principles, the
  testability examples, the relationships and the rejected framings survive;
  `references/DEEPENING.md` (dependency categories, seam discipline,
  replace-don't-layer testing), `references/DESIGN-IT-TWICE.md` (the
  parallel-design process) and `references/LICENSE` do not travel, and the two
  "Going deeper" links dangle. As a prompt the skill is no longer
  model-invoked, so the loads from improve-codebase-architecture and tdd cannot
  reach it (D29).

### diagnosing-bugs

Upstream `skills/engineering/diagnosing-bugs/`; synced as `.agents/skills/diagnosing-bugs/`.
Vendored with listed changes, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: diagnosing-bugs` inserted as the first
  frontmatter key, before "name: diagnosing-bugs"; `name` and `description`
  stay byte for byte (Frontmatter, D11).
- `SKILL.md` L10 (v1.3.1): " (or `CONTEXT.md` if the repo already has one)"
  inserted after the code span `GLOSSARY.md`; nothing else on the line changes.
  The file never names `GLOSSARY-MAP.md` (D21).
- `SKILL.md` L27 (v1.3.1): "Curl / " deleted, so option 2 reads "**HTTP
  script** against a running dev server"; the dev server is project toolchain
  and stays (D2, D22).
- `SKILL.md` L29 (v1.3.1): " / Puppeteer" deleted, so option 4 names only
  Playwright, which is pip-installable; Puppeteer is a Node-only library (D2,
  D22).
- `SKILL.md` L35 (v1.3.1): option 10 "**HITL bash script.**" becomes "**HITL
  Python script.**" and its path `scripts/hitl-loop.template.sh` becomes
  `scripts/hitl_loop_template.py` (D22).
- `SKILL.md` L59 (v1.3.1): ", a curl" deleted from "(a script path, a test
  invocation, a curl)"; the rest of the line is unchanged (D2, D22).
- `SKILL.md` L64 (v1.3.1): the Agent-runnable criterion names
  `scripts/hitl_loop_template.py` instead of the bash script (D22).
- `SKILL.md` L112 (v1.3.1): recorded with no edit. The JS timer
  `performance.now()` is kept verbatim as a stack assumption, next to the
  language-neutral "timing harness, ... profiler, query plan" (D27).
- `scripts/hitl-loop.template.sh` L1-L44 (v1.3.1): rewritten in Python as
  `scripts/hitl_loop_template.py` (Python 3.10 or later, standard library only,
  `#!/usr/bin/env python3`, mode 100755, `mypy --strict` and ruff clean); the
  `.sh` file is not shipped. The stem is snake_case because a dotted stem is not
  a module name (D22, D10). Matt's text stays:
  - every comment line of L2-L16 survives in the module docstring without its
    leading `# `, except the rewordings below;
  - the edit markers of L32 and L40 are copied byte for byte (indented inside
    `hitl_steps()`), and the prompts of L36 and L38 stay verbatim;
  - `step` and `capture` keep their names and output; the `read -p` prompts
    still go to stderr, and answers are trimmed of leading and trailing blanks
    as `read -r` trims them;
  - a `capture` name that is not an identifier raises `ValueError` before
    anything is shown, as `printf -v` accepts only shell identifiers; a dict of
    captures replaces the shell variables, so a repeated name keeps its first
    position and takes the last value;
  - upstream L18 `set -euo pipefail` has no counterpart: an uncaught exception
    stops the run with status 1.
- `scripts/hitl-loop.template.sh` L7 (v1.3.1): the usage line becomes
  `python3 hitl_loop_template.py`, which names the file as the scripts gate
  requires (D22, D30).
- `scripts/hitl-loop.template.sh` L10-L11 (v1.3.1): the two helper lines are
  written in Python call syntax, and "read response into VAR" becomes "store the
  answer under VAR", because no shell variable is set any more (D22).
- `scripts/hitl-loop.template.sh` L34 (v1.3.1): the example step's localhost
  address with port 3000 becomes "Open the app at its local dev server address
  and sign in." The plugin carries no URL, and that address is a JS dev-server
  default (D4, D22).
- `scripts/hitl-loop.template.sh` L42-L44 (v1.3.1): the Captured block prints
  every capture in capture order instead of the two hard-coded example names,
  so renaming a capture no longer means editing the library part; with the
  default example the output is identical (D22).
- `scripts/hitl_loop_template.py` (new behaviour): `run_hitl_loop` checks
  `sys.stdin.isatty()` before any step is shown and catches `EOFError` from an
  answer; either way it writes to stderr that this HITL loop needs a human at an
  interactive terminal, asks the agent to have the user run
  `python3 <absolute path of the copy>` in their own terminal and paste back the
  "--- Captured ---" block, and exits with status 2 with no Captured block.
  Ctrl-C prints a newline and exits with status 130 with no traceback, as bash
  does. The steps sit in `hitl_steps()`, so the file can be loaded without
  running them. Matt's L4 ("The agent runs the script; the user follows prompts
  in their terminal.") and `SKILL.md` L35 stay verbatim; the guard is what makes
  them work where an agent shell has no TTY (D22).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). It holds only
  `interface.display_name` and `interface.short_description`, with no `policy`
  block, so Codex loses only this skill's display name and short description.
- Project-toolchain allowlist: none. After the changes no line of `SKILL.md` or
  the script names an imposed tool or runs an ambiguous word, so
  `allowlist/diagnosing-bugs.txt` holds only its comment line.
- Continue: `.continue/prompts/diagnosing-bugs.md` carries only the name,
  description and body. The model can no longer pick the skill from its
  description, so the user starts it as `/diagnosing-bugs`.
  `scripts/hitl_loop_template.py` does not travel, so option 10 (L35) and the
  Agent-runnable criterion (L64) name a file that is not there, and a
  human-in-the-loop script has to be written by hand. No licence copy travels.
  This holds unless the Continue IDE also reads the full skill natively from
  `.claude/skills/`. The six-phase method itself is self-contained in the body
  (D29).

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

Upstream `skills/engineering/implement/`; synced as `.agents/skills/implement/`.
Vendored with listed changes, user-invoked. No sibling file or script upstream.

- `SKILL.md` L2 (v1.3.1): `id: implement` inserted as the first frontmatter key,
  before "name: implement"; the other keys are upstream's, including the double
  quotes around the description (Frontmatter, D11).
- `SKILL.md` before L7 (v1.3.1): after the blank line that closes the
  frontmatter, the guard line "Run this only when the user asked for it by name;
  otherwise stop." inserted as its own paragraph, the first line of body content
  (D19).
- `SKILL.md` L9 (v1.3.1): "Use /tdd where possible, at pre-agreed seams."
  becomes "Load the `tdd` skill and use it where possible, at pre-agreed
  seams.": an operative `/name` becomes a skill load (D17).
- `SKILL.md` L13 (v1.3.1): "Once done, use /code-review to review the work."
  becomes "Once done, load the `two-axis-review` skill to review the work.", the
  renamed skill (D8, D17).
- Kept verbatim on purpose: L11 (typechecking and tests: the consumer's project
  toolchain, no command named, so no allowlist entry) and L15 "Commit your work
  to the current branch.", which the plugin always rule keeps from staging
  `.scratch/` (D16).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). With it Codex loses this
  skill's `policy.allow_implicit_invocation: false`; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line. Outside Claude Code the guard line is what keeps this skill, which
  commits by itself, from firing on ordinary implementation requests.
- Continue: `.continue/prompts/implement.md` holds only the body, guard line
  included, with no `references/LICENSE` and no `disable-model-invocation`. The
  tdd and two-axis-review loads resolve only where the IDE also reads those
  skills natively from `.claude/skills`; nothing else is lost.

### implement-spec

Upstream `skills/engineering/implement-spec/`; synced as `.agents/skills/implement-spec/`.
Vendored with listed changes, user-invoked. No sibling file or script upstream.

- `SKILL.md` L2 (v1.3.1): `id: implement-spec` inserted as the first
  frontmatter key, before "name: implement-spec"; the other keys are upstream's
  (Frontmatter, D11). The description keeps its `/to-spec` and `/to-tickets`
  labels: it is a user-invoked skill's human-facing text (D17).
- `SKILL.md` before L7 (v1.3.1): after the blank line that closes the
  frontmatter, the guard line "Run this only when the user asked for it by name;
  otherwise stop." inserted as its own paragraph, the first line of body content
  (D19).
- `SKILL.md` after L17 (v1.3.1): L17 stays byte-identical; one paragraph is
  inserted after it, before `## Steps`: "If your harness cannot run subagents,
  do each subagent's job below yourself, one ticket at a time: build each
  frontier ticket on its own branch off the integration branch and merge it in
  before taking the next. Each merge is a stop-and-resume point: when your
  context is getting full, stop there and tell the user to start a fresh
  context and run `/implement-spec` again. A resumed run reuses the integration
  branch and skips the tickets already merged into it." It is the single
  no-subagent fallback for the exploration, implementer and merger subagents
  and the worktree cleanup (L23, L27-L30, L32, L34, L36, L40); `/implement-spec`
  keeps its slash because the sentence is addressed to the user (D17, D18.5).
- `SKILL.md` L25 (v1.3.1): "open a draft PR after the first merge in step 5"
  becomes "open a draft PR, as the issue tracker describes, after the first
  merge in step 5": the forge mechanics come only from the tracker description,
  and no forge CLI is named (D18.5).
- `SKILL.md` L29 (v1.3.1): "calls the Skill tool with `tdd` to build the
  ticket;" becomes "loads the `tdd` skill to build the ticket;", with upstream's
  three leading spaces (D17).
- `SKILL.md` L36 (v1.3.1): "call the Skill tool with `code-review` on the
  integration branch." becomes "load the `two-axis-review` skill and run it on
  the integration branch.", the renamed skill; "the code review" later on the
  line is a plain noun and stays (D8, D17).
- Kept verbatim on purpose: the tracker lines (L9, L11, L13, L15, L23, L27,
  L38), which rely on the local tracker seed of setup-matt-pocock-skills and on
  the plugin always rule for the D16 conventions (absolute main-checkout paths
  for pointers handed to subagents and worktrees, `resolved` on merge,
  `.scratch/` never staged); "tell the user to run `/setup-matt-pocock-skills`"
  at L9 (D17); "main" at L25.
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). With it Codex loses this
  skill's `policy.allow_implicit_invocation: false` and its short description;
  what remains is `disable-model-invocation`, which only Claude Code honours,
  and the guard line.
- Continue: `.continue/prompts/implement-spec.md` holds only the body, guard
  line included, with no `references/LICENSE` and no `disable-model-invocation`.
  The tdd and two-axis-review loads resolve only where the IDE also reads those
  skills natively from `.claude/skills`, and where it cannot run subagents the
  sequential stop-and-resume fallback after L17 replaces the parallel frontier.

### improve-codebase-architecture

Upstream `skills/engineering/improve-codebase-architecture/`; synced as
`.agents/skills/improve-codebase-architecture/`.
Vendored with listed changes, user-invoked.

- `SKILL.md` L2 (v1.3.1): `id: improve-codebase-architecture` inserted as the
  first frontmatter key, before "name: improve-codebase-architecture"
  (Frontmatter, D11). The description (125 characters) and
  `disable-model-invocation: true` stay verbatim.
- `SKILL.md` L6 (v1.3.1): after the blank line that closes the frontmatter, the
  guard line "Run this only when the user asked for it by name; otherwise stop."
  inserted as its own paragraph above the H1, the first line of body content
  (D19).
- `SKILL.md` L13 (v1.3.1): "Call the Skill tool with "codebase-design" for"
  becomes "Load the `codebase-design` skill for"; the rest of the bullet stays
  (D17).
- `SKILL.md` L14, L25, L54, L68 and L69 (v1.3.1): " (or `CONTEXT.md` if the repo
  already has one)" inserted after each `GLOSSARY.md` code span, and " (or
  CONTEXT.md if the repo already has one)" after L54's plain-text "GLOSSARY.md"
  inside bold: seven insertions, two on L54 and two on L68. L25's insertion sits
  inside upstream's parentheses, so that line reads "...has one))" on purpose
  (D21).
- `SKILL.md` L27 (v1.3.1): "Then spawn a sub-agent to walk the codebase."
  becomes "Then, if your harness can run subagents, spawn a sub-agent to walk the
  codebase; otherwise walk it yourself." (D17).
- `SKILL.md` L39 (v1.3.1): "Open it for the user (`xdg-open <path>` on Linux,
  `open <path>` on macOS, `start <path>` on Windows) and tell them the absolute
  path." becomes "Open it for the user if your harness can open files, and tell
  them the absolute path either way."; the two temp-directory sentences before
  it stay (D20, D23; the three openers are imposed tools under D2).
- `SKILL.md` L41 (v1.3.1): the sentence on Tailwind and Mermaid via CDN and
  "Mix Mermaid with hand-crafted CSS/SVG visuals: use Mermaid when relationships
  are graph-shaped (call graphs, dependencies, sequences), and" become "The
  report is self-contained: **one inline `<style>` block** for layout and
  styling, and **hand-built divs and inline SVG** for every diagram; it loads
  nothing from the network. Draw graph-shaped relationships (call graphs,
  dependencies, sequences) as inline-SVG boxes and arrows, and"; the tail from
  "use hand-built divs/SVG when you want something more editorial" stays (D23).
- `SKILL.md` L54 (v1.3.1): "the `/codebase-design` vocabulary" becomes "the
  `codebase-design` vocabulary": agent-facing prose, not a router label (D17).
- `SKILL.md` L58 (v1.3.1): the link target `HTML-REPORT.md` becomes
  `references/HTML-REPORT.md`; the link text stays (D10).
- `SKILL.md` L64 and L66 (v1.3.1): "call the Skill tool with "grilling"" and
  "call the Skill tool with "domain-modeling"" become "load the `grilling`
  skill" and "load the `domain-modeling` skill"; they were already two loads in
  two sentences (D17, D18).
- `SKILL.md` L71 (v1.3.1): "Call the Skill tool with "codebase-design"" becomes
  "Load the `codebase-design` skill"; "and use its design-it-twice parallel
  sub-agent pattern." stays, because the pattern carries its own subagent
  fallback (see codebase-design) (D17).
- `HTML-REPORT.md` (v1.3.1): moved to `references/HTML-REPORT.md`; its only
  inbound link is `SKILL.md` L58 (Restructure, D10).
- `references/HTML-REPORT.md` L3 (v1.3.1): after the first sentence, the
  sentences on the CDNs and Mermaid become "Nothing loads from the network: one
  inline `<style>` block does the styling, and hand-built divs and inline SVG
  draw every diagram, the graph-shaped ones (call graphs, dependencies,
  sequences) as well as the more editorial visuals (mass diagrams,
  cross-sections). Mix the patterns below: don't lean on one for everything,
  it'll start to look generic." (D23).
- `references/HTML-REPORT.md` L13-L17 (v1.3.1): the Tailwind script tag and the
  Mermaid module script deleted, and with them both URLs and both CDN assets
  (D4, D23, D30).
- `references/HTML-REPORT.md` L18-L24 (v1.3.1): the `<style>` block becomes the
  report's only stylesheet. L19's comment becomes "the report's only
  stylesheet: page, cards, badges, labels, diagram parts,"; L20 stays; 30 rules,
  from `body` to `.head-leak, .leak-label`, are inserted before L21-L23
  (`.seam`, `.leak`, `.deep`), which stay verbatim and in place so that they win
  the cascade over `.box`, `.edge` and `.module`; `.module.deep`, `svg .deep`
  and `svg .on-deep` follow them (D23).
- `references/HTML-REPORT.md` L26-L29 (v1.3.1): the Tailwind classes on
  `<body>`, `<main>` and `#candidates` dropped, their styling carried by the
  `body`, `main` and `#candidates` rules; a zero-size marker sheet,
  `<svg class="defs" aria-hidden="true">` with the `arrow` and `arrow-leak`
  markers, inserted at the top of `<body>`. It is not `display: none`, which would drop
  the markers in Chromium. No `xmlns` attribute appears anywhere (D23).
- `references/HTML-REPORT.md` L42, L108 and L123 (v1.3.1): `/codebase-design`
  loses its slash, agent-facing prose (D17).
- `references/HTML-REPORT.md` L48 (v1.3.1): "monospaced list,
  `font-mono text-sm`." becomes "monospaced list in small type (`.mono`: a
  monospace stack at 0.875rem)." (D23).
- `references/HTML-REPORT.md` L61 (v1.3.1): "### Mermaid graph" becomes "###
  Inline-SVG graph" (D23).
- `references/HTML-REPORT.md` L63 (v1.3.1): the Mermaid `flowchart` paragraph
  becomes the inline-SVG graph paragraph: `.box` rectangles, `.edge` lines
  ending in the `#arrow` marker, a `.card` wrapper, leakage as `.leak` with the
  `#arrow-leak` marker (a solid red arrow), the deep module as `.deep`, and a
  sequence diagram as one `.lifeline` per module and one `.edge` arrow per call
  (D23).
- `references/HTML-REPORT.md` L66-L75 (v1.3.1): the Tailwind card and its
  Mermaid flowchart replaced by a 16-line `<div class="card">` holding an
  inline SVG of the same four modules and three calls; the leak is a solid red
  `.edge.leak` arrow with a "leak" label between red-outlined modules, never
  dashed, because dashed means seam (D23, D30).
- `references/HTML-REPORT.md` L78 (v1.3.1): "(when Mermaid's layout fights
  you)" becomes "(when the deep module needs visual weight)" (D23).
- `references/HTML-REPORT.md` L80 (v1.3.1): "since Mermaid won't render that"
  becomes "since an SVG graph of equal boxes won't render that" (D23).
- `references/HTML-REPORT.md` L84 (v1.3.1): "(`h-12 border-l-4`)" becomes
  "(`.band`: 3rem tall with a thick left border)", and "1 thick band" gains
  "(`.band.thick`)" (D23).
- `references/HTML-REPORT.md` L96 (v1.3.1): "(`font-serif` works well" becomes
  "(a `Georgia, serif` stack works well" (D23).
- `references/HTML-REPORT.md` L99 (v1.3.1): "Use
  `text-xs uppercase tracking-wider` for" becomes "Use the `.label` class
  (0.75rem, uppercase, 0.05em letter-spacing) for" (D23).
- `references/HTML-REPORT.md` L100 (v1.3.1): the bullet on the two CDN scripts
  becomes "No scripts and no network: no external stylesheets, fonts or images,
  only the inline `<style>` block and inline SVG. The report is static: no app
  code, no interactivity." (D23).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It carried
  `policy: allow_implicit_invocation: false`, so Codex, which reads the shared
  skill root, loses this skill's user-only invocation policy; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line (D19).
- Dropped: the report's two CDN assets (the Tailwind script and Mermaid's ESM
  build, from the hosts cdn.tailwindcss.com and cdn.jsdelivr.net) and the three
  OS opener commands `xdg-open`, `open` and `start`. The
  report is now offline-only inline CSS plus inline SVG; opening it depends on
  the harness's file-opening capability, and the absolute path is always given.
  A standard-library `webbrowser` fallback was considered and rejected under
  D20: it can launch a blocking console browser on headless Linux when `TERM` is
  set, and it shells out to `osascript` on macOS. A run-time file URL would
  leave no literal in the plugin, so the URL gate is not the reason (D2, D20,
  D23).
- For T10 (global correction): "Dropped and why" names the report's CDN assets
  but not this skill's three OS openers or the rejected `webbrowser` fallback;
  the bullet above states both. "Imposed tools removed" already lists the
  openers.
- Every other byte is upstream's, including `git log --oneline` at L23 (git is
  allowed), the ellipsis at L56, the repo-name placeholder in the scaffold's
  `<title>` (`references/` files are copied, never rendered) and the non-ASCII
  characters at `references/HTML-REPORT.md` L52, L112 and L123. No line names
  an imposed tool, so the skill has no project-toolchain allowlist entry.
- Continue: `.continue/prompts/improve-codebase-architecture.md` holds only the
  `SKILL.md` body, guard line included, and a prompt the user starts satisfies
  the guard. `references/HTML-REPORT.md` (the scaffold, the stylesheet, the
  diagram patterns and the tone rules) and `references/LICENSE` do not travel
  and the L58 link dangles, so the report is built from the card list and the
  self-contained rule alone. The three loads (codebase-design, grilling,
  domain-modeling) cannot load anything, and opening the report falls back to
  telling the user the absolute path (D29).

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

Upstream `skills/engineering/prototype/`; synced as `.agents/skills/throwaway-prototype/`.
Layout-only keep, renamed, model-invoked.

- Renamed `prototype` to `throwaway-prototype` (Renames, D8): the directory,
  and `SKILL.md` L2 (v1.3.1) "name: prototype" becomes "name:
  throwaway-prototype". Claude Code ships a feature-gated bundled `prototype`
  skill, and a project skill named like a bundled skill replaces its slash
  command. The H1 "# Prototype" stays: it is a title, not the id.
- `SKILL.md` L2 (v1.3.1): `id: throwaway-prototype` inserted as the first
  frontmatter key (Frontmatter, D11). The description (179 characters) stays
  verbatim, and there is no `disable-model-invocation`: wayfinder loads this
  skill, so it stays model-invoked.
- `LOGIC.md` and `UI.md` (v1.3.1): moved to `references/LOGIC.md` and
  `references/UI.md` (Restructure, D10); their links to each other (LOGIC.md
  L14, UI.md L5) stay as written.
- `SKILL.md` L14 and L15 (v1.3.1): the link targets `LOGIC.md` and `UI.md`
  become `references/LOGIC.md` and `references/UI.md`; the link text and the
  U+2192 arrows stay (D10).
- `references/LOGIC.md` L58 and `references/UI.md` L100 (v1.3.1): the back-link
  target `SKILL.md` becomes `../SKILL.md` (D10).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies, D4).
- `agents/openai.yaml`: not shipped (Restructure, D10). It held only a display
  name and a short description, no invocation policy, so Codex loses only
  display metadata.
- Kept verbatim on purpose: `references/LOGIC.md` L54 "Send them the file, or
  open it for them." (D20); `references/UI.md` L75's `/prototype/<name>` route
  and L28's "`prototype` in the path", which are not skill ids (D8).
- Project toolchain, kept and allowlisted: `SKILL.md` L22 (v1.3.1) names the
  consumer repo's task runner, `pnpm <name>` and `bun <path>` (with
  `python <path>`), as examples of the one command that starts a UI
  prototype; the two denied words are the skill's only per-file allowlist
  entries (D2, D27).
- Stack assumptions, no text change: `references/UI.md` L60-L71 (the `tsx`
  switcher, marked "pseudo-code, adapt to the project's framework"), L87
  (`router.replace` on Next, `navigate` on React Router), L90
  (`process.env.NODE_ENV !== 'production'`) and L51's styling-system list
  "(TailwindCSS, shadcn, MUI, plain CSS, whatever)" stay verbatim
  (Consumer-repo conventions, D27).
- Inbound references follow the rename in their own skills' sections:
  wayfinder's load of this skill and ask-matt's two `/throwaway-prototype`
  router labels. wayfinder's `prototype` ticket type and ask-matt's
  `prototype/<name>` branch name stay (D8, D17).
- Every other byte is upstream's.
- Continue: `.continue/prompts/throwaway-prototype.md` holds only the router
  body: the branch picker and the six shared rules. `references/LOGIC.md` and
  `references/UI.md`, which hold the whole process of both branches, and
  `references/LICENSE` do not travel, and the two branch links dangle. As a
  prompt the skill is no longer model-invoked, so wayfinder's load cannot reach
  it (D29).

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

Upstream `skills/engineering/wayfinder/`; synced as `.agents/skills/wayfinder/`.
Vendored with listed changes, user-invoked. No sibling file or script upstream,
so nothing moves and no link is rewritten.

- `SKILL.md` L2 (v1.3.1): `id: wayfinder` inserted as the first frontmatter key,
  before "name: wayfinder"; every other frontmatter line is upstream's
  (Frontmatter, D11). The description has no `/name`, so D17 changes nothing in
  it.
- `SKILL.md` before L7 (v1.3.1): after the blank line that closes the
  frontmatter, the guard line "Run this only when the user asked for it by name;
  otherwise stop." inserted as its own paragraph, the first line of body content
  (D19).
- `SKILL.md` L77 (v1.3.1): "Resolved by a subagent that calls the Skill tool
  with "research"." becomes "Resolved by a subagent that loads the `research`
  skill; if your harness cannot run subagents, the session working through the
  map loads the `research` skill itself (charting leaves the ticket on the
  frontier)." (D17, D18.4).
- `SKILL.md` L78 (v1.3.1): "by calling the Skill tool with "prototype"" becomes
  "by loading the `throwaway-prototype` skill", the renamed skill. The
  "**Prototype** (HITL)" label and "Links the prototype as an asset" name the
  ticket type, not the skill, and stay (D8, D17).
- `SKILL.md` L79 (v1.3.1): "Always call the Skill tool twice, for "grilling"
  and "domain-modeling"." becomes "Always load the `grilling` skill, and load
  the `domain-modeling` skill." (D17, D18.1).
- `SKILL.md` L111 (v1.3.1): "Call the Skill tool twice, for "grilling" and
  "domain-modeling", to pin down" becomes "Load the `grilling` skill, and load
  the `domain-modeling` skill, to pin down" (D17, D18.1).
- `SKILL.md` L115 (v1.3.1): "For each `research` ticket you just created, spin
  up a subagent that calls the Skill tool with "research"" becomes "If your
  harness can run subagents, then for each `research` ticket you just created,
  spin up a subagent that loads the `research` skill", and the sentence
  "Otherwise, leave the research tickets on the frontier for a later session."
  is appended; charting still hand-resolves nothing (L116) (D17, D18.4).
- `SKILL.md` L120 (v1.3.1): "a map (URL or number)" becomes "a map (URL,
  number, or path)": on the local markdown tracker, the default and only one
  shipped, a map is the file `.scratch/<effort>/map.md` (D13, D14).
- `SKILL.md` L124 (v1.3.1): "call the Skill tool for whichever skills the
  `## Notes` block names. If in doubt, call the Skill tool twice, for
  "grilling" and "domain-modeling"." becomes "load each skill the `## Notes`
  block names. If in doubt, load the `grilling` skill, and load the
  `domain-modeling` skill.", one load per skill (D17, D18.1).
- Kept verbatim on purpose: the tracker lines (L17, L21, L25, L42, L44, L52,
  L65, L67, L69, L101, L113, L123, L125, L128), which rely on the local tracker
  seed of setup-matt-pocock-skills and on the plugin always rule for the D16
  conventions; "tell the user to run `/setup-matt-pocock-skills`" at L25 (D17);
  the `wayfinder:map` and `wayfinder:<type>` tracker labels; and the
  `prototype` ticket type in L65's label list (D8).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). With it Codex loses this
  skill's `policy.allow_implicit_invocation: false`; what remains is
  `disable-model-invocation`, which only Claude Code honours, and the guard
  line.
- Continue: `.continue/prompts/wayfinder.md` holds only the body, guard line
  included, with no `references/LICENSE` and no `disable-model-invocation`. The
  loads of research, throwaway-prototype, grilling and domain-modeling resolve
  only where the IDE also reads those skills natively from `.claude/skills`, and
  where it cannot run subagents the research tickets wait on the frontier
  (D18.4).

### wizard

Upstream `skills/engineering/wizard/`; synced as `.agents/skills/wizard/`.
Vendored with listed changes, model-invoked.

- `SKILL.md` L2 (v1.3.1): `id: wizard` inserted as the first frontmatter key,
  before "name: wizard" (Frontmatter, D11).
- `SKILL.md` L3 (v1.3.1): the description's "Generate an interactive bash
  wizard" becomes "Generate an interactive Python wizard"; the rest of the
  description is verbatim (313 characters upstream, 315 now; plugins are exempt
  from the 300-character lint) (D22; the lint exemption is prS D24).
- `SKILL.md` L8 (v1.3.1): "A **wizard** is a bash script" becomes "A
  **wizard** is a Python script", and "(`.env`, GitHub secrets)" becomes
  "(`.env`, or GitHub secrets it walks the human through setting)", because the
  forge CLI write is gone (D2, D22).
- `SKILL.md` L10 (v1.3.1): the link `[template.sh](template.sh)` becomes
  `[wizard_template.py](scripts/wizard_template.py)`; "cross-platform URL
  opening (including WSL)" becomes "cross-platform URL opening (Python's
  `webbrowser`, printing the URL when no browser opens)"; the
  `gh secret`/`gh variable` writes become "guided GitHub secret/variable steps"
  (D2, D10, D22).
- `SKILL.md` L20 (v1.3.1): the setup read list becomes only the `.env`
  templates (`.env.example`, `.env.sample`, `.env.template`, `.env.dist`, with
  "never `.env` itself or any other `.env.*`, which hold live values") and
  `.github/workflows/*`; `.env`, `.env.*`, `README`, `docker-compose*` and
  framework config leave the list. Existing values still reach the human at run
  time, because `ask` offers them as defaults (D22).
- `SKILL.md` L35 (v1.3.1): "Copy `template.sh`" becomes "Copy
  `scripts/wizard_template.py`"; the rest of the line, every helper name and
  `TOTAL_STAGES` included, is verbatim (D10, D22).
- `SKILL.md` L41 (v1.3.1): `bash -n` and `shellcheck` become a syntax check with
  `ast.parse` (a `python3 -c` one-liner, which writes no `__pycache__/`, unlike
  `py_compile`) and "run `ruff check` or `mypy` if available" (D2, D22).
- `SKILL.md` L42 (v1.3.1): `chmod +x` becomes "Make it executable with
  `os.chmod`" (a `python3 -c` one-liner) "or tell the user to run it as
  `python3 <script>`", because a copy written with the harness's file tool does
  not keep the template's mode bit (D22).
- `template.sh` L1-L204 (v1.3.1): rewritten in Python as
  `scripts/wizard_template.py` (Python 3.10 or later, standard library only,
  `#!/usr/bin/env python3`, mode 100755, `mypy --strict` and ruff clean) and
  moved from the skill root into `scripts/`; the `.sh` file is not shipped
  (D22, which overrides the `references/` default of D10 for this script). The
  library/STAGES split, every helper name, every user-facing string and the
  upstream comments survive; the comments that describe a helper become its
  docstring in call syntax; the comment blocks of L11-L13, L182-L185 and the
  example-stage rules of L191 and L202 are byte for byte. Upstream L9
  `set -euo pipefail` has no counterpart: an uncaught exception stops the run
  with status 1. `ENV_FILE` keeps bash's `${ENV_FILE:-.env}` (unset or empty
  both give `.env`).
- `template.sh` L2-L7 (v1.3.1): the header becomes the module docstring; the
  bare `#` of L2 is dropped and a usage block naming `wizard_template.py` is
  added, as the scripts gate requires (D22, D30).
- `template.sh` L4 (v1.3.1): "Generated by the /wizard skill." becomes
  "Generated by the `wizard` skill.": agent-facing provenance uses the plain
  name (D17).
- `template.sh` L15-L20 (v1.3.1): the `tput` colours (`tput bold`, `dim`,
  `sgr0`, `setaf`) become ANSI SGR codes, on only when stdout is a terminal and
  `TERM` is set and not `dumb`;
  `RED` stays defined and unused, as upstream's is (D2, D22).
- `template.sh` L31-L36 (v1.3.1): `_clear` writes upstream's own fallback escape
  sequence only when stdout is a terminal and `TERM` is not `dumb` (D2, D22).
- `template.sh` L29 (v1.3.1): the `SKIPPED` comment (upstream 'e.g. gh missing')
  becomes "things left for the human to do by hand", so no forge CLI text
  remains (D2).
- `template.sh` L65-L75 (v1.3.1): `open_url` uses Python's `webbrowser` (a new
  tab) instead of the four OS openers (`wslview`, `explorer.exe`, `xdg-open`,
  `open`); an argument without a scheme and a host
  (the example's placeholder, a bare host and port) is only printed, after "↗ go
  to". L73's and L74's warnings are kept for "no browser opened" and "the
  browser failed". Losses: no WSL opener (the standard library has none; it
  honours the `BROWSER` environment variable); opener output is no longer
  silenced; on headless Linux with `TERM` set, `webbrowser` may start a console
  browser in the wizard's terminal until the human quits it (D2, D22).
- `template.sh` L91-L96 (v1.3.1): `_existing` reads the last `KEY=` line of
  `ENV_FILE` as bytes, so `AB=` and `export KEY=` never match `KEY`, as with
  upstream's `^KEY=` (D22).
- `template.sh` L98-L126 (v1.3.1): `ask` and `ask_secret` return the value
  instead of setting a shell variable (`value = ask("KEY", "Prompt:")`);
  `ask_secret` reads through `getpass`; the "Enter keeps current" default, the
  trimming and the empty answer at end of file match upstream, and the current
  value is never printed. A key that is not an identifier raises `ValueError`,
  as in `write_env` (D22).
- `template.sh` L128-L139 (v1.3.1): `write_env` is an atomic, idempotent upsert:
  every old `KEY=` line goes, every other line stays byte for byte, and the new
  file is written to a temporary file in the same directory, flushed, synced and
  moved into place with `os.replace`; on any failure the temporary file is
  removed and the old file stays. The result is owner-only (mode 0600), as
  upstream's `mktemp` and `mv` left it (D22).
- `template.sh` L141-L154 (v1.3.1): `set_secret` keeps its name and signature as
  a guided manual step: it shows where to add the GitHub Actions repository
  secret and its name, never its value, asks the human to confirm, and records
  it for the summary; a "no" (or end of file) leaves it on the still-to-do list
  without the `gh secret set` command (and without the `gh auth status` check)
  (D2, D22).
- `template.sh` L156-L167 (v1.3.1): `set_var` is the same guided step for a
  repository variable, showing the name and the value; a "yes" is recorded in
  the new `WRITTEN_VAR` list (upstream never recorded variables), a "no" keeps
  upstream's "GitHub variable NAME" still-to-do item (D2, D22).
- `template.sh` L169-L180 (v1.3.1): `finish` gains a third summary line for the
  variables set this run (D22).
- `scripts/wizard_template.py` (new behaviour): `run_wizard` refuses to run when
  stdin is not a terminal, before the banner, writing to stderr that the wizard
  needs a human at an interactive terminal and asking the agent to have the user
  run `python3 <absolute path of the copy>` in their own terminal, with exit
  status 2: nothing is opened or written, and `getpass` cannot echo a secret.
  This enforces `SKILL.md` L43 ("Don't run it end-to-end yourself"). Ctrl-C ends
  any colour, prints the "stopped. Re-run it later; it remembers values already
  saved." warning and exits with status 130 without a traceback. End of file in
  the middle of a run is an empty answer, upstream's `|| true` (D22).
- `template.sh` L187-L204 (v1.3.1): the stages run inside `wizard_stages()`,
  after `TOTAL_STAGES = 1`, so the file can be loaded without running them; the
  `__main__` block calls `run_wizard(wizard_stages)` (D22).
- `template.sh` L194 (v1.3.1): the Stripe dashboard's test-mode API keys address
  becomes the scheme-less placeholder "<Stripe dashboard, test mode: Developers
  → API keys>", which `open_url` prints; an author replaces it in the consumer's
  copy. The rest of the example stage is rewritten statement by statement with
  its strings verbatim (D4, D22).
- `references/LICENSE`: added, a byte-identical copy of the plugin `LICENSE`
  (License copies).
- `agents/openai.yaml`: not shipped (Restructure). It holds only
  `interface.display_name` and `interface.short_description`, with no `policy`
  block, so Codex loses only the display name "Wizard" and the short
  description.
- Project-toolchain allowlist: none. "GitHub", `.github/workflows/*` and
  `webbrowser` match no imposed-tool name, the prose "open" of L8, L29, L37 and
  L43 is not in command position, and the script runs no subprocess, so
  `allowlist/wizard.txt` holds only its comment line.
- Continue: `.continue/prompts/wizard.md` carries only the name, description
  and body. Model invocation is lost: the agent no longer builds a wizard on its
  own when it reaches a step only the human can take, so the user starts it as
  `/wizard`. `scripts/wizard_template.py` does not travel, so the L10 link
  dangles and step 3 has no library to copy; the progress, gates, hidden entry,
  `.env` upsert and summary are lost, and an agent would write a script from
  scratch. No licence copy travels. This holds unless the Continue IDE also
  reads the full skill natively from `.claude/skills/` (D29).
- For T10 (global sections, not edited here): "Script ports" could also name
  the HITL loop's exit with status 2 on end of file and both scripts' exit with
  status 130 on Ctrl-C, and the wizard's new `WRITTEN_VAR` summary line;
  "Dropped and why" could add the two smaller `open_url` losses recorded above
  (silenced opener output, a console browser on headless Linux); and global
  L177 should say `tput` instead of "the terminal-colour utility", as "Imposed
  tools removed" and "Dropped and why" already do.

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
