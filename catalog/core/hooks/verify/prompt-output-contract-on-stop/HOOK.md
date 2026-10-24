---
id: prompt-output-contract-on-stop
name: Honour the prompt's output format
description: The output-contract Stop stage; while a playbook prompt with an output contract is active, its final answer must match it.
summary: When a playbook prompt defines an output format (such as `/review-core`'s verdict line), end in exactly that format.
version: 1
tier: opt-in
priority: 40
events: [stop]
handler:
  builtin: prompt_output_contract_on_stop
  config:
    stage: output-contract
    block_once: false
decisions: [deny, none]
timeout: 1
on_error: open
supports: [claude_code]
tags: [verify, prompts, stop-gate]
---
When a playbook prompt defines an output format (for example the final verdict line of
`/review-core`: approve, approve with comments or request changes), end your answer in exactly
that format.
