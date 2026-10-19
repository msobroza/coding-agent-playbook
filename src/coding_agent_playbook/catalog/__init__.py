"""The Catalog: where its Layers live and the source that walks them (SPEC §11, §20).

Deliberately empty: import the defining module (``catalog.roots`` for the catalog
root and the bundled-plugin names, ``catalog.layers`` for the layer labels,
``catalog.source`` for ``ArtifactSource`` and ``FileSystemArtifactSource``,
``catalog.resolve`` for the overlay merge ``OverlayResolver``). The hook
runtime imports the stdlib-only ``catalog.roots`` lazily on the protected-edit
branch, so loading it must not load ``catalog.source`` (yaml and evals) or
``catalog.resolve`` (hook_policy).
"""
