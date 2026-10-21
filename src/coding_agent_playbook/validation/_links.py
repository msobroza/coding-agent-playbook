"""``playbook validate``'s self-contained-markdown-links rule (SPEC §12.6, PR L).

Every markdown link in every rule, prompt, skill (``references/`` included) and
hook must be self-contained: a relative target resolves inside the artifact's own
source layer, and an external link passes only through the consumer's
``[links] allowed_domains`` allowlist. Split out of ``validation/checks.py`` to
keep that module under the 500-line budget.
"""

from __future__ import annotations

import tomllib
from typing import TYPE_CHECKING

from coding_agent_playbook.catalog.source import FileSystemArtifactSource, _iter_md_files
from coding_agent_playbook.config.files import CONFIG_FILENAME
from coding_agent_playbook.config.tables.links import LinksConfig, parse_links_config
from coding_agent_playbook.validation.findings import ValidationError
from coding_agent_playbook.validation.link_check import classify_link, extract_markdown_links

if TYPE_CHECKING:
    from pathlib import Path

    from coding_agent_playbook.catalog.source import ArtifactSource

# Artifact kinds whose markdown bodies (and, for skills, references/) are
# link-checked; a hook body degrades into advisory text, so it is too (H19,
# specs/prK-lifecycle-hooks.md §B.5). Eval-sample setup/ trees are sample *inputs*,
# not rendered artifacts, so they stay out of scope (specs/prL-markdown-links.md).
_LINK_CHECKED_SUBDIRS = ("rules", "prompts", "skills", "hooks")


def load_links_config(repo_root: Path) -> tuple[LinksConfig, list[ValidationError]]:
    """Parse the ``[links]`` table of ``.coding-agent-playbook.toml``.

    A malformed table degrades to the strict default plus one
    :class:`ValidationError` — the rest of validation still runs.

    Example::

        >>> load_links_config(Path("/no/such/repo"))
        (LinksConfig(allowed_domains=()), [])
    """
    config_path = repo_root / CONFIG_FILENAME
    if not config_path.is_file():
        return LinksConfig(), []
    try:
        with config_path.open("rb") as handle:
            data = tomllib.load(handle)
        return parse_links_config(data.get("links", {})), []
    except (tomllib.TOMLDecodeError, ValueError) as exc:
        return LinksConfig(), [ValidationError(path=str(config_path), message=f"[links]: {exc}")]


def _scan_markdown_text(
    text: str,
    *,
    path: str,
    base_dir: Path | None,
    root_dir: Path | None,
    links_config: LinksConfig,
) -> list[ValidationError]:
    return [
        ValidationError(
            path=path,
            message=f"markdown link {link.target!r} (line {link.line}): {verdict}",
        )
        for link in extract_markdown_links(text)
        if (
            verdict := classify_link(
                link.target,
                base_dir=base_dir,
                root_dir=root_dir,
                allowed_domains=links_config.allowed_domains,
            )
        )
        is not None
    ]


def _scan_markdown_file(
    md: Path, *, root_dir: Path, links_config: LinksConfig
) -> list[ValidationError]:
    return _scan_markdown_text(
        md.read_text(encoding="utf-8"),
        path=str(md),
        base_dir=md.parent,
        root_dir=root_dir,
        links_config=links_config,
    )


def check_markdown_links(
    artifact_source: ArtifactSource,
    repo_root: Path,
    links_config: LinksConfig,
) -> list[ValidationError]:
    """Every markdown link in every artifact must be self-contained (PR L).

    Filesystem sources are walked per layer (:meth:`FileSystemArtifactSource.layer_roots`)
    because skill ``references/`` files are not carried as paths on the
    canonical :class:`Skill` type. The walk covers rules, prompts, skills and
    hooks in every layer — the engine, each overlay package or bundled plugin,
    extra checkout roots and repo-local ``playbook/``; the containment root is
    the layer's root — ``catalog/core/`` for the engine,
    ``catalog/plugins/<name>/`` for a bundled plugin, an overlay package's
    ``resources/``, or ``playbook/`` — so links may cross artifact kinds within
    their layer but never leave the shipped bundle.

    Non-filesystem sources have no on-disk layout to resolve relative targets
    against, so only the external-link policy applies to their bodies.

    Example::

        >>> check_markdown_links(source, repo_root, LinksConfig())  # doctest: +SKIP
        []
    """
    if not isinstance(artifact_source, FileSystemArtifactSource):
        return _scan_source_bodies(artifact_source, links_config)
    return [
        error
        for subdir in _LINK_CHECKED_SUBDIRS
        for _label, root in artifact_source.layer_roots(subdir)
        for md in _iter_md_files(root)
        for error in _scan_markdown_file(md, root_dir=root.parent, links_config=links_config)
    ]


def _scan_source_bodies(
    artifact_source: ArtifactSource, links_config: LinksConfig
) -> list[ValidationError]:
    """Scan every rule, prompt, skill and hook body of a source with no on-disk layout.

    Relative targets cannot be resolved without one, so only the external-link
    policy applies.
    """
    bodies = [
        *(
            (str(r.source_path or r.frontmatter.id), r.template_body)
            for r in artifact_source.collect_rules()[0]
        ),
        *(
            (str(p.source_path or p.frontmatter.id), p.template_body)
            for p in artifact_source.list_prompts()
        ),
        *((str(s.frontmatter.get("name", "skill")), s.body) for s in artifact_source.list_skills()),
        *(
            (str(h.source_path or h.frontmatter.id), h.template_body)
            for h in artifact_source.collect_hooks()[0]
        ),
    ]
    return [
        error
        for path, body in bodies
        for error in _scan_markdown_text(
            body, path=path, base_dir=None, root_dir=None, links_config=links_config
        )
    ]
