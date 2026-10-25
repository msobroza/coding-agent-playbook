"""Sphinx configuration of the documentation site (ADR 0009).

Build it from the repository root, strictly (any warning fails) and offline:

    uv run scripts/build_docs.py

The catalog pages are generated into ``reference/catalog/`` at every build by
``_ext/catalog_sphinx.py``. Nothing here, nor in the built pages, reaches the
network: no intersphinx, no web font, and Mermaid is vendored under ``_static/``.
"""

from __future__ import annotations

import sys
from pathlib import Path

from coding_agent_playbook import __version__

sys.path.insert(0, str(Path(__file__).parent / "_ext"))

project = "coding-agent-playbook"
author = "Max Pereira"
copyright = "Max Pereira"
release = __version__

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinxarg.ext",
    "sphinxcontrib.mermaid",
    "catalog_sphinx",
]

#: The repository the site links source files on (catalog pages, the design spec).
playbook_repo_url = "https://github.com/msobroza/coding-agent-playbook"

templates_path = ["_templates"]
html_static_path = ["_static"]
html_css_files = ["site.css"]
exclude_patterns = ["_build", "_ext", "_static", "_templates"]

# GitHub's heading slugs, so a link like checks.md#playbook-forge resolves as it
# does on GitHub.
myst_heading_anchors = 4
# A ```mermaid fence is a diagram on the site, as it is on GitHub. The colon fence
# carries the note boxes that _ext/github_alerts.py makes from GitHub alerts, and
# field lists lay out the facts of each generated catalog page.
myst_fence_as_directive = ["mermaid"]
myst_enable_extensions = ["colon_fence", "fieldlist"]

# Mermaid is vendored under _static/mermaid/ (its README says how to upgrade it), so
# no page loads it from a CDN. The version only documents what is vendored.
mermaid_version = "11.12.1"
mermaid_use_local = "mermaid/mermaid.esm.min.mjs"
# Pixel-sized diagrams, so site.css can show each at its natural size and only
# shrink it to fit (the extension's CSS would otherwise stretch them all).
mermaid_init_config = {
    "startOnLoad": False,
    # Wider labels than the 200px default, so a path or a command is not split.
    "flowchart": {"useMaxWidth": False, "wrappingWidth": 300},
    "sequence": {"useMaxWidth": False},
}

autodoc_member_order = "bysource"

html_theme = "furo"
html_title = project
html_copy_source = False
html_show_sourcelink = False
html_context = {"playbook_repo_url": playbook_repo_url}
# Furo's default sidebar plus the repository link under the title. No "edit this
# page" button: the include pages and the generated ones would open the wrong file.
html_sidebars = {
    "**": [
        "sidebar/scroll-start.html",
        "sidebar/brand.html",
        "sidebar/repo-link.html",
        "sidebar/search.html",
        "sidebar/navigation.html",
        "sidebar/scroll-end.html",
    ]
}
