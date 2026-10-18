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

_Filled by T08._
