---
id: forge
name: forge
description: "Runs issue, pull request, label and check operations on GitHub or GitLab through `playbook forge`, which picks gh or glab from git config. Use when the repo is on GitHub or GitLab and a task reads or changes its issues, pull requests, labels or checks."
---

# Forge operations

`playbook forge` is the only way to act on the repository's forge. On every call it reads the current branch's push remote from git config, decides whether the forge is GitHub or GitLab, and runs that forge's CLI (`gh` or `glab`) with the CLI's own login. Never call `gh`, `glab` or a forge API yourself, and never handle a token: the same operations work on both forges. GitLab calls a pull request a merge request; the operations say `pr` on both.

## Operations

Global options come first: `playbook forge [-C <path>] <noun> <verb> [arguments] [--json]`.

- `issue create --title T [--body-file F] [--label L]... [--assignee @me] [--parent n] [--blocked-by n,m] [--confidential]`
- `issue view <n> [--comments]`
- `issue list [--state open|closed|all] [--label L]... [--no-label] [--assignee A] [--search Q] [--limit N]`
- `issue comment <n> --body-file F`
- `issue label <n> [--add a,b] [--remove c]`
- `issue assign <n> --add @me`
- `issue edit <n> [--title T] [--body-file F]`
- `issue close <n> [--comment TEXT] [--reason completed|not-planned|duplicate]`
- `issue link-child <parent> <child>` and `issue children <parent>`: sub-issues
- `issue block <child> <blocker>` and `issue blockers <n>`: blocking links
- `label list` and `label create <name> [--color RRGGBB] [--description D]`
- `pr create --title T [--body-file F] [--base B] [--draft]`
- `pr view <n> [--comments]`, `pr list [--state open|closed|merged|all] [--label L] [--external]`
- `pr diff <n>`, `pr checkout <n>`, `pr checks <n>`
- `pr comment <n> --body-file F [--reply-to <comment id>]`
- `pr label <n> [--add a,b] [--remove c]`, `pr edit <n> [--title T] [--body-file F]`, `pr ready <n>`, `pr close <n> [--comment TEXT]`
- `ref view <ref>`: `#n`, `!n` (a GitLab merge request), `n` or a web address of an issue or pull request
- `which`: the forge, CLI, host, API host, repository and remote in use
- `auth status`: whether the forge CLI is logged in

A body is `--body TEXT`, `--body-file PATH` or `--body-file -` (standard input); `issue create` and `pr create` also take `--template PATH`, read as a body file. Write anything longer than one line to a file and pass `--body-file`. On GitLab a line that starts with `/` is sent with a leading space, so no quick action runs.

With the repository's guards on, a write that sends text after a forge read may ask for confirmation first; that is expected.

Read operations print JSON with the same keys on both forges: `number`, `url`, `title`, `body`, `state` (`open`, `closed` or `merged`), `labels`, `assignees`, `author`, `created_at`, `updated_at`, `confidential`, plus `draft`, `base` and `head` for a pull request, and `comments` (`id`, `author`, `body`, `created_at`, `path`) when asked. `pr checks` prints `name`, `state` (`pass`, `fail`, `pending`, `skipped` or `cancelled`) and `url` per check. Write operations print the URL of what they created or changed (`{"url": ...}` with `--json`).

## Exit codes

| Code | Meaning | What to do |
|---|---|---|
| 0 | done | continue |
| 1 | the call or the forge CLI failed; its error is on stderr | read the error, fix the call if it is yours, else report it |
| 2 | a human must act: unknown forge, CLI missing or too old, not logged in, detached HEAD, outside the repository, host mismatch, branch not pushed | stop and give the user the one-line hint as printed; do not retry and do not fall back to `gh`, `glab` or the API |
| 3 | this forge or its plan lacks the operation | apply the text fallback below and carry on |

Text fallbacks for exit 3:

- `issue create --parent n` or `issue link-child`: write `Part of #n` as the first line of the child's body.
- `issue create --blocked-by n` or `issue block`: add a line `Blocked by: #n` to the blocked issue's body.
- `issue children` or `issue blockers`: read those lines from the issue bodies (`issue view`, `issue list --search`).
- `issue create --confidential` on GitHub: GitHub has no confidential issues; ask the user before creating a public one.

## Pull requests

- `pr create` never pushes. Push the branch first with `git push -u <remote> <branch>`; on exit 2 the hint names the command.
- On GitLab, a title holding `[skip ci]`, `[ci skip]`, `[skip pipeline]` or `[no ci]` is refused for `pr create` and `pr edit`: the pipeline would not run.
- Fill the repository's template when it has one: `.github/pull_request_template.md` (or `.github/PULL_REQUEST_TEMPLATE/`) on GitHub, `.gitlab/merge_request_templates/` on GitLab; issue templates live in `.github/ISSUE_TEMPLATE/` and `.gitlab/issue_templates/`. Write the filled text to a file and pass it with `--body-file`.
- `pr comment --reply-to <id>` answers inside a review thread; take the id from `pr view <n> --comments` (on GitHub only comments with a `path` have threads).
- Ask before copying a confidential issue into a pull request: an issue with `confidential: true` is private, and a pull request may be read more widely.

## Out of scope

`playbook forge` does not merge, delete issues, upload attachments or set CI secrets and variables. When a task needs one of these, tell the user the step to take on the forge.
