# PR L — Self-contained markdown links in canonical artifacts

Status: approved design (2026-07-14). Implements the "all markdown links in all
artifacts must be self-contained" invariant as a deterministic check that runs
on CI.

## Problem

Canonical artifacts (rules, prompts, skills) are rendered into consumer repos
and must work air-gapped. A markdown link inside an artifact that points at a
missing file, escapes the shipped bundle, or silently depends on the public
web breaks that promise — and nothing today catches it. The check must be
deterministic (no network) and enforced on CI for every artifact.

## Scope (locked with the user)

- **Covered:** canonical artifacts only — rule bodies, prompt bodies, skill
  bodies (`SKILL.md` / `SKILL.md.j2`) plus every markdown file under a skill's
  `references/` — across all three source layers: engine resources, overlay
  packages, repo-local `playbook/`.
- **Not covered:** repo docs (`README.md`, `SPEC.md`, `specs/*.md`,
  `MIGRATION.md`), eval-task `setup/` fixtures (task inputs, not rendered
  artifacts), `scripts/` (not markdown).
- **Policy:** *resolve + external allowlist*. Relative links must resolve to a
  file that ships inside the artifact's own source layer; `http(s)://` links
  are violations unless their host matches a configured allowlist; every other
  shape that leaves the bundle is a violation.

## Link semantics

Links are extracted from the artifact body (frontmatter excluded) after
masking fenced code blocks and inline code spans — `typing.md.j2` contains
`def first[T](items: list[T])` inside a fence, which a naive regex reads as a
markdown link. Extracted forms: inline links `[text](target)`, images
`![alt](target)`, reference definitions `[label]: target`, autolinks
`<scheme:...>`.

Per-target classification:

| Target shape | Verdict |
| --- | --- |
| contains Jinja (`{{` / `{%`) | skipped — not statically checkable |
| `#fragment`-only | OK (self-referential) |
| `http://` / `https://` | OK iff host equals an allowlisted domain or is a subdomain of one; else violation |
| any other scheme (`mailto:`, `ftp:`, …) | violation |
| absolute path (`/…`) | violation — layout-dependent |
| empty target | violation |
| relative path | fragment/query stripped, percent-decoded, resolved against the artifact's directory; must **exist** (as-is or with `.j2` appended, since rendering drops the suffix) and must **stay inside the artifact root** (`..` escaping is a violation) |

The *artifact root* is the package's `resources/` directory for engine and
overlay artifacts, and `<repo>/playbook/` for repo-local artifacts — a link
may cross artifact kinds within its layer (a rule may reference a prompt) but
may never leave the shipped bundle.

## Components

1. **`src/coding_agent_playbook/links.py`** (new, stdlib-only: `re`,
   `pathlib`, `urllib.parse`):
   - `MarkdownLink(text, target, line)` — extraction result, 1-based line.
   - `LinksConfig(allowed_domains: tuple[str, ...])` — parsed `[links]` table.
   - `extract_markdown_links(text) -> list[MarkdownLink]` — masking +
     extraction as above.
   - `classify_link(target, base_dir, root_dir, allowed_domains) -> str | None`
     — violation message or `None`. `base_dir=None` (non-filesystem sources)
     skips relative resolution but still applies scheme/allowlist policy.

2. **`config.parse_links_config(data) -> LinksConfig`** — parses the
   `[links]` table of `.coding-agent-playbook.toml` (mirrors
   `parse_metrics_config`; local import avoids cycles). Domains are lowercased;
   a non-list / non-string entry raises `ValueError`.

   ```toml
   [links]
   allowed_domains = ["agentharnesses.io"]   # default: [] (fully strict)
   ```

3. **`commands/validate.py`: `_check_markdown_links`** — new SPEC §12.6 rule,
   aggregated with the existing `ValidationError`s. Filesystem sources are
   walked per package (same pattern as `_load_eval_tasks_for_validation`) so
   skill `references/` files — which the canonical `Skill` type does not carry
   as paths — are covered; non-filesystem sources fall back to scanning
   resolved artifact bodies with `base_dir=None`.

## CI enforcement

- The engine's own gate is a pytest integration test
  (`tests/cli/test_validate_links.py`) that runs the real check over every
  shipped engine artifact and asserts zero violations — it runs under the
  existing `pytest -q` CI step. (A bare `playbook validate` CI step does not
  work in the engine repo: `load_config` requires a consumer
  `.coding-agent-playbook.toml`.)
- Consumer repos and overlay packages get the same check through
  `playbook validate` (already the pre-commit story per SPEC §13.2).

## Tests

- `tests/unit/test_links.py` — extraction (fenced-block masking regression on
  the `[T](items: list[T])` shape, inline/image/refdef/autolink forms, line
  numbers) and classification (each verdict row above, subdomain matching,
  `..` escape, `.j2` fallback, `base_dir=None`).
- `tests/unit/test_config.py` — `parse_links_config` happy path, default,
  lowercasing, type errors.
- `tests/cli/test_validate_links.py` — fixture-repo integration: broken
  relative link → exit 1 with `FAIL`; disallowed external → exit 1; allowlisted
  external → exit 0; code-fence link-alike → exit 0; skill `references/`
  violation → exit 1; and the shipped-engine-artifacts-are-clean gate.

## Non-goals

- Verifying that external URLs are alive (network = non-deterministic).
- Anchor (`#heading`) existence checking.
- Reference-style *usage* resolution (`[text][label]` → definition) — only
  definitions' targets are checked.
- Rendered-output link checking — canonical source is the source of truth.
