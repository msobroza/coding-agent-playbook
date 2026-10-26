---
id: prompt-write-scope-guard
name: Prompt write-scope guard
description: Keep read-only playbook prompts from editing the code and test-writing prompts inside their test globs.
summary: During a read-only playbook prompt, do not modify code; during `/generate-tests`, write only test files.
tier: default
priority: 40
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, notebook_edit, shell]
    tool_names: [Skill]
handler:
  builtin: prompt_scope_guard
decisions: [deny, ask, none]
timeout: 2
on_error: ask
supports: [claude_code]
tags: [feedback, prompts]
---
While a read-only playbook prompt runs (`/explain`, `/review-core`, `/security-review-core`,
`/find-injected-vulnerability`), do not modify the code: report findings, and let the user
ask for fixes in a follow-up. While `/generate-tests` runs, write only test files
(`tests/**`, `conftest.py`); do not "fix" the code to make a test pass.
