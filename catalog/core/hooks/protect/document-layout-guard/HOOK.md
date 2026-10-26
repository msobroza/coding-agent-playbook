---
id: document-layout-guard
name: Document layout guard
description: Deny writing a spec or plan outside the document layout and name the directory it belongs in.
summary: Write specs to `docs/specs/` and plans to `docs/plans/`, never to a framework's own folder or `.scratch/`.
tier: default
priority: 25
events: [pre_tool_use]
matcher:
  pre_tool_use:
    tools: [edit, write, shell]
handler:
  builtin: document_layout_guard
  config:
    specs_dir: docs/specs
    plans_dir: docs/plans
    scratch_dir: .scratch
    blocked_dirs: [docs/superpowers]
decisions: [deny, none]
timeout: 2
on_error: open
supports: [claude_code, opencode]
tags: [protect, docs]
---
Specs, designs and PRDs go to `docs/specs/YYYY-MM-DD-<slug>.md`; plans go to
`docs/plans/YYYY-MM-DD-<slug>.md`, with their tickets in `docs/plans/YYYY-MM-DD-<slug>/`.
Never write one into a framework's own folder (such as `docs/superpowers`) or as a spec or plan
file under `.scratch/`, which holds only throwaway prototypes.
