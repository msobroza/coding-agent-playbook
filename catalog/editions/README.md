# Editions: generated, never edit by hand

Each `<tag>/` directory here is a byte copy of the graded set (the graded
prompts and the rules they include) as release `<tag>` shipped it, with the
license and attribution notices that text needs. Only
`scripts/release.py freeze <tag>` writes one and only
`scripts/release.py unfreeze <tag>` removes it; eval samples pinned to an
edition grade these files, so CI fails when a file differs from its tag.

To change the guidance, edit the current text instead: `<tag>/core/<path>` is a
copy of `catalog/core/<path>`.
