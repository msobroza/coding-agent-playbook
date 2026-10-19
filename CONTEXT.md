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
A rule delivered on demand, as a reference inside the one skill it names as the owner of its topic.
_Avoid_: conditional rule, glob rule

**Member rule**:
A scoped rule seen from the skill it names in `skill:`; the engine renders it as one of that skill's references. Continue, which reads no skills, still receives it as its own rule file.
_Avoid_: child rule

**Skill**:
A named unit of on-demand guidance: a short index the agent loads by name, plus references it opens only when needed.
_Avoid_: pack, plugin

**Reference**:
A file inside a skill that the agent opens only when the skill's index points it there.
_Avoid_: appendix, sub-rule

**Prompt**:
A named task the user invokes explicitly, as a slash command.
_Avoid_: command, template

**Hook**:
An assistant lifecycle handler that runs on agent events (before a tool, after an edit, at stop) and can block, warn or feed back to the agent.
_Avoid_: bare "hook" for the git kind; say **pre-commit hook**

**Guardrail**:
The text form of a hook for a harness that cannot run it: one line in always-loaded context, with the full text in the guardrails skill.
_Avoid_: advisory, advisory rule

**Skill nudge**:
A one-line hook message, sent the first time in a session that the agent edits a file a skill covers, naming the skill to load.
_Avoid_: reminder, hint

**Eval task**:
A reproducible test case for a prompt: a starting repo state, an invocation and a definition of success.

### Context

**Always-loaded context**:
Everything a harness puts in front of the model on every turn, whatever the task: always rules, the generated "Where guidance lives" map, guardrails and the skill listing.
_Avoid_: system prompt, memory

**Skill listing**:
The names and descriptions of the skills a harness advertises to the model on every turn; it is part of always-loaded context.

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
The canonical source of rules, skills, prompts, hooks and eval tasks that the engine renders.

**Layer**:
One source of catalog content. Later layers override earlier ones by id: core, then overlays and bundled plugins, then the consumer repo's own content.

**Core**:
The engine's own layer, active in every consumer repo.

**Bundled plugin**:
An opt-in layer that ships inside the engine.
_Avoid_: pack

**Overlay**:
An organization's package that adds a layer on top of core.

**Detector fact**:
A property of the consumer repo (frameworks, ML stack, notebooks, Python version and so on) that decides which content is rendered.
_Avoid_: signal, feature flag

**Detector**:
The engine part that inspects a consumer repo and produces its detector facts.

**Renderer**:
The engine part that turns catalog templates and detector facts into final text.

**Adapter**:
The engine part that writes rendered content in one harness's native format and locations.

**Harness**:
A coding-agent runtime the engine writes files for, such as Claude Code, OpenCode, Codex, Continue or Cursor.

**OpenCode plugin**:
A JavaScript module OpenCode loads to react to its runtime events; the engine generates exactly one, to run hooks.

**OpenCode agent**:
A named OpenCode mode with its own model, permissions and system prompt; it is not part of the catalog.

**Consumer repo**:
A repository the playbook is installed into.

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

**Grading kernel**:
The engine's shared machinery for scoring work (metrics, checks, rubrics and how they compose), used by eval tasks and the metrics gate.
_Avoid_: evaluators

### Third-party content

**Distilled content**:
Third-party ideas rewritten from scratch in the catalog's own formats, credited by name and license only.
_Avoid_: ported, adapted

**Vendored content**:
Third-party files copied into a bundled plugin together with their license and a list of changes.
_Avoid_: imported, mirrored
