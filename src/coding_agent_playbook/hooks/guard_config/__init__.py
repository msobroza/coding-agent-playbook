"""The ``guard_config.json`` writer: the hook runtime's only configuration (specs/prK-lifecycle-hooks.md §D.8).

Deliberately empty: import the defining module. ``compile`` builds the document
and its canonical bytes; ``inputs`` holds the value types sync hands it;
``resource_roots`` names the layer roots (committed ids, per-machine dirs);
``ruff_probe`` asks the pinned ruff which rule codes it knows, for
``machine.json``. The private ``_tables_*`` modules build one table each. The
runtime owns the contract names this package writes (``hook_runtime.config.schema``)
and never imports it: it reads the written file.
"""
