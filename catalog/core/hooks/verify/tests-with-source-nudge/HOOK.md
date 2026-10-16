---
id: tests-with-source-nudge
name: New public API needs a test
description: The tests-nudge Stop stage; name each new public function, class or method under the source roots that no test mentions.
version: 1
tier: default
priority: 40
events: [stop]
handler:
  builtin: tests_with_source_nudge
  config:
    stage: tests-nudge
    block: false
decisions: [deny, none]
timeout: 2
on_error: open
supports: [claude_code, opencode]
tags: [verify, tests, stop-gate]
---
When you add a public function, class or method, add a test that exercises it in the same
change. Before finishing, check that every new public name appears in a test.
