# Issue tracker: Forge issues

Issues and specs for this repo live as issues on its forge: GitHub or GitLab, whichever the current branch pushes to. Run every operation through `playbook forge`, which reads the forge from git config and runs that forge's own CLI with its own login. Never call a forge CLI or a forge API yourself.

## Conventions

- **Create an issue**: `playbook forge issue create --title "<title>" --body-file <file>`, adding `--label <label>` once per label. Write the body to a file in the OS temporary directory first, never in the repo.
- **Read an issue**: `playbook forge issue view <number> --comments`. It prints JSON with the body, labels, assignees, state and comments.
- **List issues**: `playbook forge issue list --state open`, filtered with `--label`, `--assignee`, `--search` and `--limit`.
- **Comment on an issue**: `playbook forge issue comment <number> --body-file <file>`
- **Apply / remove labels**: `playbook forge issue label <number> --add <label>` / `--remove <label>`. The labels exist on the forge: setup created them.
- **Close**: `playbook forge issue close <number> --comment "<note>" --reason completed` (or `not-planned`, `duplicate`)
- **Assign**: `playbook forge issue assign <number> --add @me`
- A pull request carries one `Closes #<n>` line in its description for each ticket it completes, so the forge closes the ticket when it merges.
- Exit code 2 means a human must act (the forge CLI is missing or not logged in, the branch is not pushed, …): stop and give the user the one-line hint it printed. Never fall back to local markdown, a forge CLI or a forge API.
- Exit code 3 means this forge or its plan lacks the operation: apply the text fallback named below and carry on.

## Pull requests as a triage surface

**PRs as a request surface: no.** _(Set to `yes` if this repo treats external pull requests as feature requests; a triage skill reads this flag.)_

When set to `yes`, external pull requests run through the same labels and states as issues:

- **Read a PR**: `playbook forge pr view <number> --comments` and `playbook forge pr diff <number>` for the diff.
- **List external PRs for triage**: `playbook forge pr list --state open --external` keeps only pull requests whose author is not a member of the project.
- **Comment / label / close**: `playbook forge pr comment <number> --body-file <file>`, `playbook forge pr label <number> --add <label>`, `playbook forge pr close <number> --comment "<note>"`.

GitHub shares one number space across issues and pull requests, and GitLab writes a merge request as `!42`: resolve a bare reference with `playbook forge ref view <ref>`.

## When a skill says "publish to the issue tracker"

Create an issue with `playbook forge issue create`.

## When a skill says "fetch the relevant ticket"

Run `playbook forge issue view <number> --comments`.

## When a skill says "close" or "resolve" a ticket

Close the issue: `playbook forge issue close <number> --comment "<note>" --reason completed`. A closed issue is **closed**; an open one is open. An implementation ticket closes when the pull request carrying its `Closes #<n>` line merges. A ticket ruled out of scope, or made obsolete, is closed with `--reason not-planned`: issues are never deleted.

## Blocking

Use the forge's native blocking link: `playbook forge issue block <ticket> <blocker>`, read back with `playbook forge issue blockers <ticket>`. On exit 3 (a GitLab plan without blocking links), put a `Blocked by: #<n>, #<n>` line at the top of the ticket's body instead (`playbook forge issue edit <ticket> --body-file <file>`). A ticket is unblocked when every blocker is closed.

## Wayfinding operations

Used by `wayfinder`. The **map** is a single issue with **child** issues as tickets.

- **Map**: a single issue labelled `wayfinder:map`, holding the Notes / Decisions-so-far / Fog body: `playbook forge issue create --title "<title>" --body-file <file> --label wayfinder:map`.
- **Child ticket**: an issue labelled `wayfinder:<type>` (`research`/`prototype`/`grilling`/`task`), linked to the map as a sub-issue with `playbook forge issue link-child <map> <child>`. On exit 3 (GitLab has no sub-issues), put `Part of #<map>` as the first line of the child's body. Once claimed, the ticket is assigned to the driving dev.
- **Blocking**: `playbook forge issue block <child> <blocker>`; on exit 3, a `Blocked by: #<n>, #<n>` line at the top of the child's body. A ticket is unblocked when every blocker is closed.
- **Frontier query**: the map's open children (`playbook forge issue children <map>`; on exit 3, `playbook forge issue list --state open --search "Part of #<map>"`), minus any with an assignee or an open blocker (`playbook forge issue blockers <n>`; on exit 3, an open issue on its `Blocked by` line); first in map order wins.
- **Claim**: `playbook forge issue assign <n> --add @me`, the session's first write.
- **Resolve**: `playbook forge issue comment <n> --body-file <file>` with the answer, then `playbook forge issue close <n> --reason completed`, then append a context pointer (gist + link) to the map's Decisions-so-far with `playbook forge issue edit <map> --body-file <file>`. Only the session driving the map edits the map; a research subagent writes only to its own ticket.
- **Rule out**: a ticket beyond the destination, or one a decision made obsolete, is closed with `playbook forge issue close <n> --comment "<why>" --reason not-planned`, never deleted.
