---
id: git-commit-push-policy-guard
name: Git commit and push policy guard
description: Deny changes to git identity, authorship or signing (--author, -S, git config user.*, -c and GIT_* overrides) and commits under a placeholder identity; ask before committing in another worktree or on the default branch.
summary: Commit as the user's git identity on a feature branch; never pass `--author` or `-S`, or write `git config user.*`.
version: 1
tier: default
priority: 22
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [shell]
handler:
  builtin: git_policy_guard
  config:
    placeholder_identity: ["*@example.com", "you@*", "*@localhost", ""]
    ask_on_default_branch: true
    forbid_trailers: []
    allowed_coauthors: []
    required_trailers: {}
    never_commit_globs: []
    push_requires_green: false
decisions: [deny, ask, none]
timeout: 3
on_error: ask
supports: [claude_code, opencode]
tags: [safety, git]
---
Commit as the user's configured git identity: never pass `--author`, `-S` / `--gpg-sign`,
`git -c user.*` or `GIT_AUTHOR_*` / `GIT_COMMITTER_*`, and never write `git config user.*`.
If the identity is missing or a placeholder, ask the user to fix it. Commit from this
session's worktree on a feature branch, never directly on the default branch.
