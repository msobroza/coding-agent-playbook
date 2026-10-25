---
status: accepted
---

# The documentation site is built with Sphinx, Furo and MyST

The engine's docs were Markdown files read on GitHub. We publish them as a static site built with Sphinx, the Furo theme and the MyST Markdown parser, from the `docs/` pages in place. The site adds a generated catalog reference, a CLI reference from the commands' own argument parsers and the extension-point classes from their docstrings. The docstrings already use Sphinx's markup (`:mod:`, `:func:`, ``` ``literal`` ```), which autodoc renders as written, and `sphinx-argparse` reads `build_parser()` directly. The build is strict (`-W`) and offline: no intersphinx, no CDN script, no web font. It is pinned in a `docs` extra that the test matrix never installs, and `scripts/build_docs.py` is the one build command, for contributors and CI alike.

## Considered Options

- **MkDocs with Material for MkDocs.** The common choice for Python projects, but Material went maintenance-only in November 2025 with support promised for about a year, and it caps MkDocs below 2.0. We would adopt a theme at its end of life.
- **Zensical**, the Material team's successor, which reads `mkdocs.yml`. It was about a year old, its support for MkDocs plugins was still catching up, and mkdocstrings would not render our docstrings' Sphinx roles.
- **Astro Starlight, Docusaurus or VitePress.** Strong documentation sites, but each adds a Node toolchain to a Python-only repository and has no way to read Python docstrings or an argparse parser.

## Consequences

- Pages stay plain Markdown read on GitHub; MyST options (`myst_heading_anchors`) keep GitHub's heading slugs, so a link like `checks.md#playbook-forge` works on both.
- `README.md`, `CONTEXT.md`, `MIGRATION.md` and `catalog/README.md` stay where they are and reach the site through MyST `{include}` pages; a build hook (`docs/_ext/repo_links.py`) maps links to them onto their site pages, and `SPEC.md` stays in the repository, linked from a short page.
- Diagrams are ` ```mermaid ` blocks, which GitHub renders too. `sphinxcontrib-mermaid` would load Mermaid from a CDN, so its ES-module build is vendored, unchanged, under `docs/_static/mermaid/` (MIT, about 2.7 MB); upgrading it is a reviewed copy, as that directory's README says.
- Help text and docstrings are parsed as reStructuredText on the site: a bare `*` or an unclosed backtick in them fails the strict build.
- The site builds the same way on GitHub (Actions, Pages) and on a company's GitLab copy (`.gitlab-ci.yml`, GitLab Pages). Source links follow the repository of the build, read from the CI's own variables (`docs/_ext/source_host.py`), so no internal host name is ever committed.
- The catalog pages are written at every build from the engine's own readers (`docs/_ext/`), so they never drift from `catalog/`; they are git-ignored.
