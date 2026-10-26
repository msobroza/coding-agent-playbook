# Coding Agent Playbook

One canonical catalog of guidance for coding agents, rendered by the engine into each harness's native files inside a consumer repo. This file is the project's only glossary.

## Language

### Guidance kinds

**Rule**:
A unit of guidance an agent follows while working in a consumer repo. Every rule is either an always rule or a scoped rule.
_Avoid_: instruction, convention file

**Always rule**:
A rule placed in always-loaded context, because nearly every task needs it and the model would not do it unprompted.
_Avoid_: global rule, core rule

**Scoped rule**:
A rule delivered on demand, inside the one skill that owns its topic.
_Avoid_: conditional rule, glob rule

**Member rule**:
A scoped rule seen from the skill that owns it: it sits in that skill's rules directory, or, when it comes from another layer, names the skill in `skill:`. The engine renders it into the skill's rules directory. Continue, which reads no skills, still receives it as its own rule file.
_Avoid_: child rule

**Skill**:
A named unit of on-demand guidance: a short index the agent loads by name, plus member rules and references it opens only when needed.
_Avoid_: pack, plugin

**Reference**:
A free-form document inside a skill (long-form explanation, checklist, walkthrough) that the agent opens when a rule names it or its open-when line matches the change. Unlike a member rule, it has no priority and no section; it may carry a gate that decides whether it is written at all.
_Avoid_: appendix, sub-rule

**Decision guide**:
A reference that routes a recurring situation (which test double, which idiom on this Python version, which rule a failing check points to) to the rules that cover it, without repeating them.
_Avoid_: cheat sheet

**Example**:
A small runnable project inside a skill, with its own tests, that shows the skill's rules working together; written only where its gate passes.
_Avoid_: demo, sample app (an **Eval sample** is a different thing)

**Section**:
A named group of a skill's member rules, listed in the skill's index under its title, its impact and its open-when line, which names the kind of change that should make the agent read those rules. Every member rule belongs to exactly one section of its skill.
_Avoid_: category

**Impact**:
How much harm ignoring a section's rules does: CRITICAL, HIGH, MEDIUM or LOW. It decides which sections a skill lists first and which priority band their rules take.
_Avoid_: severity, importance

**Prompt**:
A named task the user invokes explicitly, as a slash command.
_Avoid_: command, template

**Hook**:
An assistant lifecycle handler that runs on agent events (before a tool, after an edit, at stop) and can block, warn or feed back to the agent.
_Avoid_: bare "hook" for the git kind; say **pre-commit hook**

**Hook family**:
One of the five purpose groups the catalog's hooks are filed under: protect, verify, feedback, safety and audit.
_Avoid_: hook pack, hook group (a Claude Code settings matcher group), category

**Guardrail**:
The text form of a hook for a harness that cannot run it: one line in always-loaded context, with the full text in the guardrails skill.
_Avoid_: advisory, advisory rule

**Skill nudge**:
A one-line hook message, sent the first time in a session that the agent edits a file a skill covers, naming the skill to load.
_Avoid_: reminder, hint

**Eval sample**:
A reproducible test case for a prompt: a starting repo state, an invocation and a definition of success.
_Avoid_: eval task

**Task**:
The eval samples of one prompt, grouped under that prompt's id.
_Avoid_: eval task, the retired name of an eval sample

**Graded set**:
The prompts that eval samples grade, plus the rules those prompts include: everything an eval run puts in front of the agent.

**Edition**:
A frozen copy of the graded set as one release shipped it, named after that release. It exists only in the engine and only while a pin needs it; a consumer repo never renders one and always gets the current text.
_Avoid_: prompt set, twin, v1/v2 prompts, snapshot, baseline

**Pin**:
An eval sample's reference to the edition it grades, which freezes the whole experiment: the edition's text, the sample and its starting repo state. A sample without a pin grades the current text.
_Avoid_: lock, freeze (freezing is the act of creating a pin)

**Eval target**:
A harness and a model that eval runs drive, named once in the `[evals]` config; the model is sent to the harness exactly as written.
_Avoid_: eval runner (a runner is the code that drives one harness), model alias

### Context

**Always-loaded context**:
Everything a harness puts in front of the model on every turn, whatever the task: always rules, the generated "Where guidance lives" map, guardrails and the skill listing.
_Avoid_: system prompt, memory

**Skill listing**:
The names and descriptions of the skills a harness advertises to the model on every turn; it is part of always-loaded context.

**Probe repo**:
A synthetic consumer repo that CI syncs to measure budgets and check rendering. Gated skills count only in the probe whose facts turn them on (a standard, a Domino and an authoring probe).
_Avoid_: fixture repo

**Context budget**:
The ceiling on always-loaded context that CI enforces.
_Avoid_: token limit (each harness's own limits are a different thing)

**Skill root**:
A directory that harnesses scan to discover skills.
_Avoid_: skills hub

### Engine and catalog

**Engine**:
The installable package that detects facts about a consumer repo, renders the catalog and writes each harness's files.

**Catalog**:
The canonical source of rules, skills, prompts, hooks and eval samples that the engine renders.

**Layer**:
One source of catalog content. Later layers override earlier ones by id: core, then overlays and bundled plugins, then the consumer repo's own content.

**Local layer**:
A consumer repo's own layer, kept in its `playbook/` directory; it can add rules or skills and override others by id.
_Avoid_: repo-local overlay

**Core**:
The engine's own layer, active in every consumer repo.

**Bundled plugin**:
An opt-in layer that ships inside the engine.
_Avoid_: pack

**Document layout**:
Where a consumer repo keeps its glossary, decision records, architecture overview, specs, plans, research notes and framework setup notes. It has defaults, the repo may change any directory in its committed config, and every framework follows it.
_Avoid_: docs structure, folder convention

**Framework**:
The bundled plugin or overlay that supplies the spec-driven workflow skills an agent follows from idea to merge (planning, test-first work, review). A consumer repo enables at most one, chosen by name. It declares itself in a metadata file, and may map its own document paths onto the document layout there.
_Avoid_: methodology, workflow pack

**Capability**:
A standard role a framework fills with one of its skills (clarify, spec, plan, tdd, debug, review, verify). The skill declares the role in its own frontmatter, so core content can name the role instead of a framework's skill.
_Avoid_: hook point, extension

**Overlay**:
An organization's package that adds a layer on top of core.

**Platform**:
A hosting environment a consumer repo builds for (today, Domino). Its skills turn on when the detector finds the platform's markers in the repo, or when the consumer config names the platform.

**Detector fact**:
A property of the consumer repo (frameworks, ML stack, notebooks, Python version and so on) that decides which content is rendered.
_Avoid_: signal, feature flag

**Detector**:
The engine part that inspects a consumer repo and produces its detector facts.

**Renderer**:
The engine part that turns catalog templates and detector facts into final text.

**Adapter**:
The engine part that writes rendered content in one harness's native format and locations.

**Layout adapter**:
The sync step that rewrites the document layout's default path prefixes, and the prefixes a framework maps onto it, in the generated outputs to the repo's configured document layout. It writes no harness format, so it is not an Adapter.

**Extension point**:
An entry-point group through which an installed package adds engine code, such as an adapter, an artifact source, a metric or a hook handler.
_Avoid_: plugin API, hook point

**Harness**:
A coding-agent runtime the engine writes files for, such as Claude Code, OpenCode, Codex, Continue or Cursor.

**Harness marker**:
A file in the consumer repo that shows a harness is in use (for example `opencode.json` or `.continue/`), read only from the repo and never from PATH; the engine's own generated outputs do not count.
_Avoid_: harness signal

**Agent Harness tree**:
The directory tree the agent_harness adapter writes for Agent Harness clients and `import-harness` reads back; it is not a Harness.

**OpenCode plugin**:
A JavaScript module OpenCode loads to react to its runtime events; the engine generates exactly one, to run hooks.

**OpenCode agent**:
A named OpenCode mode with its own model, permissions and system prompt; it is not part of the catalog.

**Consumer repo**:
A repository the playbook is installed into.
_Avoid_: target repo

**Consumer config**:
The committed config file and the machine-local overrides file in a consumer repo that steer sync and the hooks.

**Generated output**:
A file the engine writes and owns in a consumer repo, marked by the sentinel and recorded in the lockfile.
_Avoid_: owned file, managed file

**Lockfile**:
The engine's record, in a consumer repo, of every generated output it wrote, with its source and content hash; sync uses it to find drift and leftovers.

**Sync**:
One `playbook sync` run: resolve the catalog, render every adapter's Generated output and write the Lockfile.

### Checks and grading

**Validation**:
The checks `playbook validate` and the sync gate run over canonical artifacts before anything is written.

**Guard twin**:
A CLI command that runs the same judge as a guard hook, so the check also runs outside an agent session, in CI or pre-commit.

**Judge sample**:
One of the N times the judge scores a rubric criterion; the scores are averaged to damp the judge's noise.
_Avoid_: bare "samples" (an **Eval sample** is the test case)

**Grading kernel**:
The engine's shared machinery for scoring work (metrics, checks, rubrics and how they compose), used by eval samples and the metrics gate.
_Avoid_: evaluators

**Release metrics**:
The scores of every eval sample for one release under one harness and model, compared with the previous release's to flag regressions.
_Avoid_: benchmark, scorecard

### Third-party content

**Distilled content**:
Third-party ideas rewritten from scratch in the catalog's own formats, credited by name (and license, when the source has one) and never copied; the only form allowed for sources without an open license.
_Avoid_: ported, adapted

**Vendored content**:
Third-party text copied into a layer (core or a bundled plugin) together with its license and a list of changes, then adapted to the catalog's formats.
_Avoid_: imported, mirrored

### What a skill may run

**Harness built-in**:
A capability the harness itself gives the agent, such as loading a skill, running a subagent or asking the user a question; each harness names it differently and some lack it.

**Harness command**:
A slash command a harness ships itself, such as Claude Code's `/code-review` (alias `/review`) or Codex's `/review`.
_Avoid_: built-in command (a **Harness built-in** is a capability, not a command)

**Imposed tool**:
An executable a skill tells the agent to run whatever the consumer repo is, such as a forge CLI or a bundled shell script.
_Avoid_: external tool, dependency

**Project toolchain**:
The commands a consumer repo already runs for itself, such as its test, typecheck, lint or build commands; a skill that runs them imposes no tool.

### Review

**Finding**:
A problem a review reports, tied to a file and line, with one severity.
_Avoid_: comment, issue (an issue lives on a forge)

**Severity**:
How much a finding blocks a merge: `important` must be fixed before merge, `nit` is optional, and `pre-existing` sits on a line the change does not touch and never blocks.
_Avoid_: priority, level; not an **Impact**, which grades a skill's sections

**First pass**:
The step of a review that reads the change and lists candidate findings: a fresh-context subagent, and beside it a pass that only hunts bugs (the harness's own reviewer where the agent can run it as a tool, such as Claude Code's `/code-review`, else a second subagent); the main agent merges their candidates and checks each against the lines it cites.
_Avoid_: pre-review, scan

**Re-review**:
A review of an already reviewed change that covers only its new commits and gives each earlier finding one status, fixed or still open.
_Avoid_: second review, follow-up review

**Review notes**:
An owner-written, committed file (`REVIEW.md`) that says what failure means in each area of a repo, which paths to skip and how many nits to allow; it adds checks to a review but never changes the review's output format, and the engine never generates it.
_Avoid_: review config, review guide

### Forges

**Forge**:
A git hosting service with its own CLI and CI system, such as GitHub or GitLab.
_Avoid_: host, provider, platform, adapter (an adapter writes a harness's files)

**Forge CLI**:
The command-line client of one forge, such as `gh` for GitHub or `glab` for GitLab.

**Forge operation**:
One action on a forge that the playbook offers in the same form for every forge, such as opening or viewing a pull request.
_Avoid_: forge command, forge action

**Pull request**:
A proposed change from one branch into another, reviewed on the forge; GitLab calls it a merge request.
_Avoid_: merge request, MR, change request (except when quoting GitLab itself)
