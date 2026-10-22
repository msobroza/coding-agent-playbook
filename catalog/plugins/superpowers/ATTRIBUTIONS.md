# Attributions

The skills under `skills/` in this pack are a **near-verbatim port**
of the **Superpowers** skills library.

- **Source:** Superpowers, the skills library by Jesse Vincent (repository
  name: obra/superpowers).
- **Version:** 7.0.0, upstream commit bb92a77741419a4ab5f06e711a283343f1ada0c3.
- **Author / copyright:** Copyright (c) 2025 Jesse Vincent.
- **License:** MIT. The full license text is in the `LICENSE` file next to this
  file. The MIT license requires that the copyright notice and the permission
  notice be included in all copies or substantial portions of the software, so
  `LICENSE` must ship with every copy of this pack. `playbook sync` copies each
  skill directory into consumer repositories, so a byte-identical copy also
  ships as `references/LICENSE` inside every skill and travels with each synced
  skill directory (`.claude/skills/<id>/`, `.opencode/skills/<id>/`,
  `.agents/skills/<id>/`, and the opt-in Agent Harness `skills/<id>/`). Continue
  has no native skills: its degraded prompts
  (`.continue/prompts/<id>.md`) carry only the `SKILL.md` body, so a repository
  that renders this pack only for Continue must keep a copy of `LICENSE` next to
  them itself.

### Third-party content inside the port

`writing-skills/references/anthropic-best-practices.md` reproduces Anthropic's
public "Skill authoring best practices" documentation as included in upstream
Superpowers v7.0.0. It is redistributed as upstream shipped it (with only the
URL removals listed below) and is not authored by Jesse Vincent.

## Indication of changes

The port keeps the upstream wording. The only edits are the ones needed to make
the pack self-contained inside the coding-agent-playbook engine (no upstream
plugin, marketplace, repository, or network access is needed at run time),
and the spec and plan paths that follow the engine's document layout:

- **Restructure.** The engine's skill sync copies only `SKILL.md`, `scripts/`
  and `references/` from each skill directory, so every other supporting file at
  an upstream skill root moved under `references/` (for example
  `systematic-debugging/root-cause-tracing.md` became
  `systematic-debugging/references/root-cause-tracing.md`, and
  `diagnosing-superpowers/prompts/` became
  `diagnosing-superpowers/references/prompts/`), and executables at a skill root
  moved under `scripts/` (`systematic-debugging/find-polluter.sh`,
  `writing-skills/render-graphs.js`). Upstream `scripts/` and `references/`
  directories are kept as-is. Every mention of a moved file (markdown links,
  inline paths, prose, graph labels, the usage comments of `find-polluter.sh`
  and `render-graphs.js`) points at its new location; inline paths are written
  relative to the skill directory, as upstream's were.
- **License copies added.** `references/LICENSE` in every skill directory is a
  byte-identical copy of this pack's `LICENSE` (see License above).
- **Frontmatter.** An `id` key equal to the directory name was added as the
  first frontmatter key of every `SKILL.md`. `name` is unchanged, and so is
  every `description` except diagnosing-superpowers', which no longer names the
  upstream maintainers as the bug report's recipient (see Dropped below).
  Six skills gain one engine-owned line, `capabilities: [<role>]`, as their
  last frontmatter key: brainstorming (`clarify`), writing-plans (`plan`),
  test-driven-development (`tdd`), systematic-debugging (`debug`),
  requesting-code-review (`review`) and verification-before-completion
  (`verify`). The engine reads it to map the framework's roles and never writes
  it to the synced copies.
- **Framework metadata added.** `framework.toml` at the pack root is new: it
  marks the pack as a spec-driven framework named `superpowers`. It declares
  no `[layout_aliases]`: the skills' own text names the document layout's
  default paths (next item).
- **Document layout paths.** The pack writes specs and plans in the engine's
  shared document layout (`docs/specs/`, `docs/plans/`) instead of upstream's
  `docs/superpowers/specs/` and `docs/superpowers/plans/`, so `playbook sync`
  can move them to a repo's configured `[layout]`. Only the path strings
  changed; the surrounding wording is upstream's:
  - brainstorming `SKILL.md`, "Where it goes":
    `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` became
    `docs/specs/YYYY-MM-DD-<topic>-design.md`.
  - writing-plans `SKILL.md`, "Save plans to":
    `docs/superpowers/plans/YYYY-MM-DD-<feature-name>.md` became
    `docs/plans/YYYY-MM-DD-<feature-name>.md`.
  - writing-plans `SKILL.md`, both "Plan complete and saved to" lines:
    `docs/superpowers/plans/<filename>.md` became `docs/plans/<filename>.md`.
  - requesting-code-review `SKILL.md`, the example's `PLAN_OR_REQUIREMENTS`
    line: `docs/superpowers/plans/deployment-plan.md` became
    `docs/plans/deployment-plan.md`.
  - executing-plans `SKILL.md` and subagent-driven-development `SKILL.md`, the
    example workflow's "Read plan" and "Resolve workspace" lines:
    `docs/superpowers/plans/feature-plan.md` became
    `docs/plans/feature-plan.md`.
- **Cross-skill references.** Namespaced `superpowers:<skill>` references were
  rewritten to the plain skill name (`<skill>`); all referenced skills ship in
  this pack.
- **External URLs removed.** No web URL remains anywhere in the pack. Markdown
  links keep their link text as plain text; MDX cards keep their title and body
  and lose only their `href`; each external image is replaced by an italic note
  carrying its alt text, `*(Diagram omitted: <alt text>)*`.
- **Module-type sidecar added.** `writing-skills/scripts/package.json`
  (`{"type": "module"}`) is new: `render-graphs.js` (code unchanged; only its
  usage examples now read `./scripts/render-graphs.js`) uses ES-module syntax
  that upstream parsed as ESM only through its repository-root `package.json`,
  which is not vendored. The helper remains optional and still needs Node.js and
  Graphviz on the machine that runs it.
- **Upstream-plugin coupling neutralized.** Text that required installing the
  upstream plugin or marketplace, relied on its hooks or plugin environment
  variables, read files from the upstream repository that are not in this pack,
  or asked the reader to file issues upstream was removed or minimally
  reworded. Hermes' and Muse's skill-file fallback now reads
  `.claude/skills/<name>/SKILL.md`. diagnosing-superpowers' skill-timeline
  analyst prompt and case template gained a short note for a rendered skills
  pack, where invocations carry no `superpowers` prefix and there is no plugin
  install root or version: it lists the 15 skill ids of this pack and records
  the version as "coding-agent-playbook superpowers pack (upstream 7.0.0,
  bb92a77)".

### Dropped

- **brainstorming visual companion:** the browser-based companion (a Node.js
  server with its HTML/JS assets and start/stop scripts under
  `brainstorming/scripts/`, plus `visual-companion.md`). It needs a JavaScript
  runtime and a local web server, which the pack does not ship.
- **SessionStart bootstrap hook:** the plugin hook that injects
  `using-superpowers` at session start. Hooks are not part of the canonical
  artifact model; consumers load `using-superpowers` like any other skill.
- **Upstream issue filing in diagnosing-superpowers:** its issue-filing
  reference, issue template, and GitHub-issues workflow step were removed. The
  skill still writes its local report and, when the goal is a bug report, offers
  a scrubbed bundle on request, but it files nothing against the upstream
  repository.
- **All non-skill repository content:** the per-harness plugin manifests, hooks,
  docs, tests, release notes, and the scripts and packaging files at the
  repository root. Among them is the Gemini CLI context file `GEMINI.md`, which
  loaded `using-superpowers` together with
  `using-superpowers/references/gemini-tools.md`; to keep that tool mapping
  reachable, using-superpowers' Platform Adaptation list gained a
  `Gemini CLI: references/gemini-tools.md` line.

## Skills in this pack

| id | Purpose (from its description) |
|---|---|
| brainstorming | Use before any creative work: explores intent, requirements and design before implementation. |
| diagnosing-superpowers | Use when a session went wrong (repeated work, ignored plans, stumbles, poor results, a skill that didn't fire, cost or time) to find out why. |
| dispatching-parallel-agents | Use when facing 2+ independent tasks that can be worked on without shared state or sequential dependencies. |
| executing-plans | Use when executing an implementation plan in the current session as the implementer yourself. |
| finishing-a-development-branch | Use when implementation is complete and tests pass, to decide how to integrate the work. |
| receiving-code-review | Use when receiving code review feedback: technical rigor and verification, not performative agreement. |
| requesting-code-review | Use when completing tasks, implementing major features, or before merging, to verify work meets requirements. |
| subagent-driven-development | Use when executing implementation plans with independent tasks in the current session. |
| systematic-debugging | Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes. |
| test-driven-development | Use when implementing any feature or bugfix, before writing implementation code. |
| using-git-worktrees | Use when starting feature work that needs isolation, to ensure an isolated workspace exists. |
| using-superpowers | Use when starting any conversation: establishes how to find and use skills before any response. |
| verification-before-completion | Use before claiming work is complete, fixed, or passing: evidence before assertions. |
| writing-plans | Use when you have a spec or requirements for a multi-step task, before touching code. |
| writing-skills | Use when creating new skills, editing existing skills, or verifying skills work before deployment. |
