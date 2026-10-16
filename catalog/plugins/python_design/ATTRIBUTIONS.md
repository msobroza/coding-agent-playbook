# Attributions

This file is the only place in the `python_design` pack that credits an outside
source. The skills themselves carry no attribution, no source names and no
URLs.

## Source of the ideas

Source: the "python-clean-architecture" Claude Code plugin, version 0.8.1.
License: MIT License. Copyright (c) 2025 MKToronto.
The plugin describes its concepts as inspired by Arjan Codes' courses.

The pack is distilled, not vendored. Every sentence, table, example, code
fragment and script in it was written fresh for this engine; no text, examples
or code from the plugin are copied. Only the underlying design ideas are
reused, restated in the engine's own words, with fresh example domains, and
reconciled with the engine's shipped Python and FastAPI rules where the two
differ (for example: Protocol or Callable seams by default, with abstract base
classes still allowed for shared implementation or a documented extension
point; timeouts and bounded, transient-only retries by default; unmapped domain
errors surface as HTTP 500).

## Skills

| Skill | Ideas distilled |
| --- | --- |
| python-design-review | Code-smell catalog and fixes; a design-quality checklist; design principles and GRASP responsibility assignment as a review lens; function, class and data-structure design; Pythonic forms of common design patterns from the lightest to the heaviest form; god-class extraction by method/attribute cohesion; the idea of scanning for smells with an AST pass. The scripts `detect_smells.py` and `lcom4_clusters.py` are new, written for this pack. |
| python-architecture | Layered application structure with a composition root per entry point; dependency injection through constructors, callables and consumer-owned protocols; designing for testability with in-memory fakes; repository and unit-of-work persistence; when CQRS and event sourcing are worth it; project organization. The worked example uses a new domain, and the script `layer_map.py` is new, written for this pack. |
