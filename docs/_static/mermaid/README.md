# Vendored Mermaid

Mermaid 11.12.1 (MIT, see `LICENSE`), the ES-module build `sphinxcontrib-mermaid`
loads through `mermaid_use_local` in `docs/conf.py`. It is vendored, unchanged, so
the site renders diagrams without calling a CDN (ADR 0009).

- Source: the npm package `mermaid@11.12.1`, whose tarball matched the registry's
  `dist.integrity` (sha512) when it was copied.
- Files: `package/dist/mermaid.esm.min.mjs` and every `.mjs` file of
  `package/dist/chunks/mermaid.esm.min/`; the source maps are left out.

To upgrade, download the new tarball (`npm pack mermaid@<version>`), check its
integrity against `npm view mermaid@<version> dist.integrity`, replace these files
the same way, and update the version here and in `mermaid_version` in
`docs/conf.py`. Then build the site and look at every page that has a diagram.
