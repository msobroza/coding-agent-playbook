---
id: pii-prompt-guard
name: PII prompt guard
description: Block a prompt carrying checksum-validated personal data (IBANs, card numbers, national or customer ids) before it reaches the model; the user sees each hit's category, offset and masked form, never the value. Inert in the engine; a regulated overlay activates it.
summary: Do not paste personal data (IBANs, card numbers, national ids) into prompts; use a placeholder instead.
version: 1
tier: overlay
enabled: true
priority: 10
events: [user_prompt_submit]
handler:
  builtin: pii_prompt_guard
  config:
    detectors: []
    extra_detectors: []
    test_value_allowlist: []
    override_token: ""
    max_prompt_bytes: 1048576
decisions: [deny, none]
timeout: 5
on_error: open
supports: [claude_code]
tags: [safety, pii, overlay]
---
Do not paste personal data (IBANs, card numbers, national identifiers, customer ids) into
prompts: use a placeholder such as `<IBAN>` or a synthetic value instead.
