---
id: setup-matt-pocock-skills
name: setup-matt-pocock-skills
description: "Configure this repo for the engineering skills: set up its issue tracker, triage label vocabulary, and domain doc layout. Run once before first use of the other engineering skills."
disable-model-invocation: true
---

Run this only when the user asked for it by name; otherwise stop.

# Setup Matt Pocock's Skills

Scaffold the per-repo configuration that the engineering skills assume:

- **Issue tracker**: where issues live (the forge's issues when the repo pushes to GitHub or GitLab, local markdown otherwise; any other tracker works once the user describes it)
- **Triage labels**: the strings used for the five canonical triage roles
- **Domain docs**: where `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and ADRs live, and the consumer rules for reading them

This is a prompt-driven skill, not a deterministic script. Explore, present what you found, confirm with the user, then write.

## Process

### 1. Explore

Look at the current repo to understand its starting state. Read whatever exists; don't assume:

- `git remote -v` and `.git/config`, then `playbook forge which`: does the current branch push to GitHub or GitLab? Which repository? Exit 0 prints the forge and the repository; exit 2 means it found no forge it can use, so Section A proposes local markdown.
- `AGENTS.md` and `CLAUDE.md` at the repo root: is there an old `## Agent skills` section in either? Read them only to answer that: this skill never edits or creates either file (step 5 says what to tell the user).
- `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) and `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) at the repo root
- `docs/adr/` and any `src/*/docs/adr/` directories
- `docs/agents/`: does this skill's prior output already exist?
- `.scratch/`: a sign that a local-markdown issue tracker convention is already in use
- Monorepo signals: a `pnpm-workspace.yaml`, a `workspaces` field in `package.json`, or a populated `packages/*` with its own `src/`. These are present only in a genuinely large multi-package repo; their absence means single-context, which is almost every repo.

### 2. Present findings and ask

Summarise what's present and what's missing. Then take the sections in order. One section, one answer, then the next.

Lead each section with the recommended answer so the user can accept it in a word. Give a one-line explainer only when the choice genuinely branches; skip the section entirely when exploration already settled it (Section C when there's no monorepo). Section B is written without asking.

**Section A: Issue tracker.**

> Explainer: The "issue tracker" is where issues live for this repo. Skills like `to-tickets` and `to-spec` read from and write to it. They need to know whether to open issues on the repo's forge, write a markdown file under `.scratch/`, or follow some other workflow you describe. Pick the place you actually track work for this repo.

Default posture: when `playbook forge which` found a forge, preselect **Forge issues**, so the user confirms it once; otherwise propose local markdown. A user who tracks work anywhere else picks **Other**. Offer:

- **Forge issues**: issues live in the repo's GitHub or GitLab issues, reached through `playbook forge`, which runs the forge's own CLI with its own login (offered when `playbook forge which` found a forge, and then the default)
- **Local markdown**: issues live as files under `.scratch/<feature>/` in this repo (the default without a forge; needs no remote or CLI)
- **Other** (Jira, Linear, etc.): ask the user to describe the workflow for each section of [issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions: publish, fetch, close, blocking (default: a plain `Blocked by:` line near the top of each ticket) and the Wayfinding operations; the skill will record each answer under that section's heading

Record the choice in `docs/agents/issue-tracker.md`. The Forge issues seed carries a "PRs as a request surface" flag, defaulted **off**. Leave it off and don't raise it: a user who wants external PRs in the triage queue can flip the flag in the file later.

On **Forge issues**, run `playbook forge auth status` once the user confirms. Exit 0: the forge CLI is logged in; go on. Exit 2: show the user the one-line hint it printed, the step only they can take (install the CLI, or log in), wait until they say it's done, and run it again. Don't fall back to local markdown, and never call a forge CLI or API yourself.

**Section B: Triage label vocabulary.** Always written, without asking: `to-spec` and `to-tickets` apply these labels.

The defaults are the five canonical roles, each label string equal to its name: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. Write them as-is. If the user's tracker already uses other names (e.g. `bug:triage` for `needs-triage`), they change the right-hand column in the step 3 draft, so the skills apply existing labels instead of creating duplicates.

**Section C: Domain docs.** Default to **single-context** (one `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) + `docs/adr/` at the repo root). This fits almost every repo; write it without asking.

Offer **multi-context** (a root `GLOSSARY-MAP.md` (or `CONTEXT-MAP.md` if the repo already has one) pointing to per-context `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) files) only when exploration found monorepo signals. Then confirm which layout they want.

### 3. Confirm and edit

Show the user a draft of:

- The contents of `docs/agents/issue-tracker.md`, `docs/agents/domain.md`, and `docs/agents/triage-labels.md`

Let them edit before writing.

### 4. Write

Write only `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` and `docs/agents/domain.md`. Never edit or create `CLAUDE.md` or `AGENTS.md`: the always rule this plugin ships (`mattpocock-skills-tracker`) already points every session at these files.

Write the docs files using the seed templates in this skill folder as a starting point:

- [issue-tracker-forge.md](./references/issue-tracker-forge.md): Forge issues (GitHub or GitLab, through `playbook forge`)
- [issue-tracker-local.md](./references/issue-tracker-local.md): local-markdown issue tracker
- [triage-labels.md](./references/triage-labels.md): label mapping
- [domain.md](./references/domain.md): domain doc consumer rules + layout

For "other" issue trackers, write `docs/agents/issue-tracker.md` from scratch using the user's description, under the same `##` headings as [issue-tracker-local.md](./references/issue-tracker-local.md) after its Conventions; keep the `## Wayfinding operations` heading verbatim, since `wayfinder` looks it up by name.

On **Forge issues**, then create the labels the skills apply, on GitHub and GitLab alike: every label in the right-hand column of `docs/agents/triage-labels.md`, plus `wayfinder:map`, `wayfinder:research`, `wayfinder:prototype`, `wayfinder:grilling` and `wayfinder:task`. `playbook forge label list` shows the ones that exist; create each missing one with `playbook forge label create <name> --color <RRGGBB> --description "<meaning>"`, the meaning taken from the label table (for a `wayfinder:` label, its ticket type).

### 5. Done

Tell the user the setup is complete and which engineering skills will now read from these files. Mention they can edit `docs/agents/*.md` directly later; re-running this skill is only necessary if they want to switch issue trackers or restart from scratch. If exploration found an old `## Agent skills` section in a root `CLAUDE.md` or `AGENTS.md`, tell them the always rule this plugin ships (`mattpocock-skills-tracker`) supersedes it and that they may delete it; don't edit the file yourself.
