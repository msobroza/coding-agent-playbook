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
  (D4, D23).
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
  dashed, because dashed means seam (D23).
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
  build) and the three OS opener commands `xdg-open`, `open` and `start`. The
  report is now offline-only inline CSS plus inline SVG; opening it depends on
  the harness's file-opening capability, and the absolute path is always given.
  A standard-library `webbrowser` fallback was considered and rejected under
  D20: it can launch a blocking console browser on headless Linux when `TERM` is
  set, and it shells out to `osascript` on macOS (D2, D20, D23).
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
