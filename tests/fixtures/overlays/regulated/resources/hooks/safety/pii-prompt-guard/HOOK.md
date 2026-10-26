---
id: pii-prompt-guard
name: PII prompt guard
description: Block a prompt carrying checksum-validated personal data before it reaches the model (regulated overlay activation).
tier: default
enabled: true
priority: 10
events: [user_prompt_submit]
handler:
  builtin: pii_prompt_guard
  config:
    detectors: [iban, card_pan, fr_nir, us_ssn]
    extra_detectors:
      - {name: bank_customer_id, pattern: '\bCUST-(\d{10})\b', checksum: mod97}
    test_value_allowlist: ["4111111111111111"]
    override_token: "#pii-ok"
    max_prompt_bytes: 1048576
decisions: [deny, none]
timeout: 5
on_error: deny
supports: [claude_code]
tags: [safety, pii, overlay]
---
Never paste customer data into a prompt: no IBANs, card numbers, national identifiers or
customer ids. Use a placeholder such as `<IBAN>` or a synthetic value, and resubmit.
