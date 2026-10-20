# Issue tracker: Local Markdown

Issues and specs for this repo live as markdown files in `.scratch/`.

## Conventions

- One feature per directory: `.scratch/<feature-slug>/`
- The spec is `.scratch/<feature-slug>/spec.md`
- Implementation issues are one file per ticket at `.scratch/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01`, never a single combined tickets file
- Every issue file (the spec, each ticket) and every map opens with a `# <title>` heading: its name
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading
- `.scratch/` is untracked working state: never stage it in a commit
- Worktrees do not contain untracked files: when you point a subagent or a worktree at a spec, ticket or map, give its absolute path in the main checkout

## When a skill says "publish to the issue tracker"

Create a new file under `.scratch/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## When a skill says "close" or "resolve" a ticket

Set the file's `Status:` line, in place, to a terminal status: `resolved` (answered or done) or `out-of-scope` (ruled out). A ticket is **closed** when its status is either one; any other status is open. Set an implementation ticket `resolved` once its work is merged. A ticket written by `to-tickets` has the bold form `**Status:** ready-for-agent`: rewrite that line in place, never add a second status line.

## Blocking

A ticket's blockers go on a `Blocked by:` line near the top (bold, `**Blocked by:**`, in a ticket written by `to-tickets`), listing the numbers of the tickets that gate it (titles may follow), or `None (can start immediately)`. A ticket is unblocked when every ticket it lists is closed.

## Wayfinding operations

Used by `wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `.scratch/<effort>/map.md` (the Notes / Decisions-so-far / Fog body).
- **Child ticket**: `.scratch/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`/`out-of-scope`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is closed (`resolved` or `out-of-scope`).
- **Frontier**: scan `.scratch/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`. Only the session driving the map appends to `map.md`; a research subagent writes only its own ticket file.
