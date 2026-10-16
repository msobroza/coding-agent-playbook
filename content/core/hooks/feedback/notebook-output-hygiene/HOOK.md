---
id: notebook-output-hygiene
name: Notebook output hygiene
description: Warn when an edited notebook keeps cell outputs, embedded images or base64 payloads, or oversized output, since outputs may embed data rows.
version: 1
tier: opt-in
priority: 70
events: [post_tool_use, stop]
applies_if:
  has_notebooks: true
matcher:
  post_tool_use:
    tools: [edit, write, notebook_edit]
    paths: ["**/*.ipynb"]
handlers:
  post_tool_use:
    builtin: notebook_hygiene
    config:
      max_cell_output_kb: 64
  stop:
    builtin: "notebook_hygiene:stop_stage"
    config:
      stage: notebooks
      mode: warn
decisions: [context, none]
timeout: 5
on_error: open
supports: [claude_code, opencode]
tags: [feedback, notebooks]
---
Before committing a notebook you edited, clear its outputs (for example
`jupyter nbconvert --clear-output --inplace <notebook>`): outputs may embed data rows,
images and credentials that the source cells never show.
