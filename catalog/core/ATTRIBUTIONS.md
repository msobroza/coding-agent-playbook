# Attributions

This file is the only place in the shipped resources that credits outside
sources for the engine's own rules and prompts. Artifact bodies carry no
attribution. Attributions for the `find-injected-vuln-*` eval fixtures live in
`eval_tasks/ATTRIBUTIONS.md`.

## Clean-architecture guidance for Python

Source: the "python-clean-architecture" Claude Code plugin, version 0.8.1.
License: MIT License. Copyright (c) 2025 MKToronto.
The plugin describes its concepts as inspired by Arjan Codes' courses.

The following artifacts distill ideas from that plugin:

- Rules: python-dependency-injection, python-pure-core, python-data-shapes,
  python-idioms, python-context-managers, python-retries-and-timeouts,
  fastapi-app-wiring, fastapi-error-boundaries.
- Prompts: review-architecture, make-testable, characterize.
- Additions to existing artifacts: the python-house-style, python-typing,
  python-error-handling and pytest rules, and the review and refactor prompts.

All of this text was written fresh for this engine. No sentences, examples or
code from the plugin are copied; only the underlying design ideas are reused,
restated in the engine's own words and adapted to its rule and prompt format.
