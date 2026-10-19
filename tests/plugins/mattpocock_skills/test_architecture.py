"""T06's gate: improve-codebase-architecture, codebase-design and throwaway-prototype.

specs/prT-mattpocock-skills.md appendix A.T06 and section 9.7. Every new text of
A.T06 is asserted as an exact substring of its plugin file, and every upstream
text it replaced as absent from that file. The skill-specific tests A.T06 names
(the self-contained report, the rename, the relative links) live here too:
section 7.1 makes this file T06's only test module. The expected texts are
literals copied from the spec, never read from the upstream checkout.
"""

from __future__ import annotations

import os
import re
from html.parser import HTMLParser
from pathlib import Path
from typing import Final
from urllib.parse import urlsplit

import pytest

from coding_agent_playbook.links import extract_markdown_links
from tests.plugins.mattpocock_skills._expectations import (
    GUARD_LINE,
    LOAD_RE,
    PLUGIN_ROOT,
    SKILLS_ROOT,
    load_allowlist,
    present_skill_ids,
    skill_docs,
    split_skill,
)

pytestmark = pytest.mark.catalog

ICA: Final = "improve-codebase-architecture"
PROTOTYPE: Final = "throwaway-prototype"
DESIGN: Final = "codebase-design"
REPORT: Final = "references/HTML-REPORT.md"
#: The D21 fallback; one grep for it finds every insertion (A.T06 note 3).
FALLBACK: Final = "if the repo already has one"


def _read(skill_id: str, rel: str) -> str:
    return (SKILLS_ROOT / skill_id / rel).read_text(encoding="utf-8")


def _case_id(case: tuple[str, str, str]) -> str:
    skill_id, rel, text = case
    return f"{skill_id}/{rel}:{text[:48]}"


# --- improve-codebase-architecture (A.T06.1) ------------------------------------

_ICA_HEAD: Final = (
    "---\n"
    "id: improve-codebase-architecture\n"
    "name: improve-codebase-architecture\n"
    "description: Scan a codebase for deepening opportunities, present them as a visual HTML"
    " report, then grill through whichever one you pick.\n"
    "disable-model-invocation: true\n"
    "---\n"
    "\n"
    f"{GUARD_LINE}\n"
    "\n"
    "# Improve Codebase Architecture\n"
)

#: The report scaffold after changes 19-21: no script, one inline stylesheet, one marker sheet.
_SCAFFOLD: Final = """\
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <title>Architecture review for {{repo name}}</title>
    <style>
      /* the report's only stylesheet: page, cards, badges, labels, diagram parts,
         dashed seam lines, hand-drawn-feeling arrow heads, etc. */
      body { margin: 0; background: #fafaf9; color: #0f172a; font-family: system-ui, sans-serif; line-height: 1.5; }
      main { max-width: 64rem; margin: 0 auto; padding: 3rem 1.5rem; display: flex; flex-direction: column; gap: 3rem; }
      #candidates { display: flex; flex-direction: column; gap: 2.5rem; }
      #candidates > article { display: flex; flex-direction: column; gap: 1rem; background: #fff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1.5rem; }
      #top-recommendation { background: #fff; border: 2px solid #cbd5e1; border-radius: 0.5rem; padding: 2rem; font-size: 1.125rem; }
      .card { background: #fff; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 1rem; }
      .badges { display: flex; flex-wrap: wrap; gap: 0.5rem; }
      .badge { border-radius: 999px; padding: 0.125rem 0.625rem; font-size: 0.75rem; font-weight: 600; }
      .badge-strong { background: #d1fae5; color: #065f46; }
      .badge-exploring { background: #fef3c7; color: #92400e; }
      .badge-speculative { background: #e2e8f0; color: #334155; }
      .tag { border: 1px solid #cbd5e1; color: #475569; }
      .mono { font-family: ui-monospace, Menlo, Consolas, monospace; font-size: 0.875rem; }
      .adr { background: #fffbeb; border: 1px solid #fcd34d; border-radius: 0.375rem; padding: 0.5rem 0.75rem; }
      .before-after { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
      .diagram { position: relative; height: 320px; }
      svg { display: block; width: 100%; height: auto; }
      .diagram > svg { position: absolute; inset: 0; height: 100%; }
      .defs { position: absolute; width: 0; height: 0; }
      .label { font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.05em; }
      .module { background: #fff; border: 1px solid #334155; border-radius: 0.25rem; padding: 0.5rem; }
      .faded { opacity: 0.4; }
      .band { display: flex; align-items: center; height: 3rem; margin-bottom: 0.25rem; padding-left: 0.75rem; background: #f1f5f9; border-left: 4px solid #334155; }
      .band.thick { height: 9rem; border-left-width: 12px; }
      svg text { font-size: 12px; fill: #0f172a; text-anchor: middle; dominant-baseline: middle; }
      .box { fill: #fff; stroke: #334155; stroke-width: 1.5; }
      .edge { fill: none; stroke: #334155; stroke-width: 1.5; }
      .lifeline { stroke: #cbd5e1; stroke-width: 1; }
      .head { fill: #334155; }
      .head-leak, .leak-label { fill: #dc2626; }
      .seam { stroke-dasharray: 4 4; }
      .leak { stroke: #dc2626; }
      .deep { background: linear-gradient(135deg, #0f172a, #1e293b); }
      .module.deep { border: 4px solid #0f172a; color: #f8fafc; }
      svg .deep { fill: #1e293b; stroke: #0f172a; stroke-width: 4; }
      svg .on-deep { fill: #f8fafc; }
    </style>
  </head>
  <body>
    <svg class="defs" aria-hidden="true">
      <defs>
        <marker id="arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="head" d="M0 0L10 5L0 10z" /></marker>
        <marker id="arrow-leak" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto"><path class="head-leak" d="M0 0L10 5L0 10z" /></marker>
      </defs>
    </svg>
    <main>
      <header>...</header>
      <section id="candidates">...</section>
      <section id="top-recommendation">...</section>
    </main>
  </body>
</html>
```
"""

#: The graph example after change 26: inline SVG, no ``xmlns``, a solid red leak arrow.
_GRAPH_EXAMPLE: Final = """\
```html
<div class="card">
  <svg viewBox="0 0 670 90" role="img" aria-label="OrderHandler calls OrderValidator calls OrderRepo, which leaks into PricingClient">
    <rect class="box" x="10" y="30" width="140" height="40" />
    <text class="label" x="80" y="50">OrderHandler</text>
    <rect class="box" x="180" y="30" width="140" height="40" />
    <text class="label" x="250" y="50">OrderValidator</text>
    <rect class="box leak" x="350" y="30" width="140" height="40" />
    <text class="label" x="420" y="50">OrderRepo</text>
    <rect class="box leak" x="520" y="30" width="140" height="40" />
    <text class="label" x="590" y="50">PricingClient</text>
    <line class="edge" x1="150" y1="50" x2="178" y2="50" marker-end="url(#arrow)" />
    <line class="edge" x1="320" y1="50" x2="348" y2="50" marker-end="url(#arrow)" />
    <line class="edge leak" x1="490" y1="50" x2="518" y2="50" marker-end="url(#arrow-leak)" />
    <text class="leak-label" x="504" y="18">leak</text>
  </svg>
</div>
```
"""

#: The D20 sentence that replaces the three OS openers (change 7).
D20_SENTENCE: Final = (
    "Open it for the user if your harness can open files, and tell them the absolute path"
    " either way."
)

_ICA_NEW: Final = (
    # 3 (D17)
    '- Load the `codebase-design` skill for the architecture vocabulary (**module**, **interface**, **depth**, **seam**, **adapter**, **leverage**, **locality**) and its principles (the deletion test, "the interface is the test surface", "one adapter = hypothetical seam, two = real"). Use these terms exactly in every suggestion, and don\'t drift into "component," "service," "API," or "boundary."',
    # 4 (D21)
    "- The domain language in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) gives names to good seams; ADRs in `docs/adr/` record decisions this command should not re-litigate.",
    # 5 (D21; the doubled closing parenthesis is intended)
    "Read the project's domain glossary (`GLOSSARY.md` (or `CONTEXT.md` if the repo already has one)) and any ADRs in the area you're touching first.",
    # 6 (D17)
    "Then, if your harness can run subagents, spawn a sub-agent to walk the codebase; otherwise walk it yourself. Don't follow rigid heuristics; explore organically and note where you experience friction:",
    # 7 (D20, D23): the two sentences before the opener stay verbatim
    "Write a self-contained HTML file to the OS temp directory so nothing lands in the repo. Resolve the temp dir from `$TMPDIR`, falling back to `/tmp` (or `%TEMP%` on Windows), and write to `<tmpdir>/architecture-review-<timestamp>.html` so each run gets a fresh file. "
    + D20_SENTENCE,
    # 8 (D23)
    "The report is self-contained: **one inline `<style>` block** for layout and styling, and **hand-built divs and inline SVG** for every diagram; it loads nothing from the network. Draw graph-shaped relationships (call graphs, dependencies, sequences) as inline-SVG boxes and arrows, and use hand-built divs/SVG when you want something more editorial (mass diagrams, cross-sections, collapse animations). Each candidate gets a **before/after visualisation**. Be visual.",
    # 9, 10 (D21, D17)
    '**Use GLOSSARY.md (or CONTEXT.md if the repo already has one) vocabulary for the domain, and the `codebase-design` vocabulary for the architecture.** If `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) defines "Order," talk about "the Order intake module," not "the FooBarHandler," and not "the Order service."',
    # 11 (D10)
    "See [HTML-REPORT.md](references/HTML-REPORT.md) for the full HTML scaffold, diagram patterns, and styling guidance.",
    # 12 (D17)
    "Once the user picks a candidate, load the `grilling` skill to walk the decision tree with them: constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.",
    # 13 (D17)
    "Side effects happen inline as decisions crystallize; load the `domain-modeling` skill to keep the domain model current as you go:",
    # 14 (D21)
    "- **Naming a deepened module after a concept not in `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one)?** Add the term to `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one). Create the file lazily if it doesn't exist.",
    # 15 (D21)
    "- **Sharpening a fuzzy term during the conversation?** Update `GLOSSARY.md` (or `CONTEXT.md` if the repo already has one) right there.",
    # 16 (D17)
    "- **Want to explore alternative interfaces for the deepened module?** Load the `codebase-design` skill and use its design-it-twice parallel sub-agent pattern.",
)

_REPORT_NEW: Final = (
    # 18 (D23)
    "The architectural review is rendered as a single self-contained HTML file in the OS temp directory. Nothing loads from the network: one inline `<style>` block does the styling, and hand-built divs and inline SVG draw every diagram, the graph-shaped ones (call graphs, dependencies, sequences) as well as the more editorial visuals (mass diagrams, cross-sections). Mix the patterns below: don't lean on one for everything, it'll start to look generic.",
    # 19-21 (D4, D23, D30)
    _SCAFFOLD,
    # 22 (D17)
    "The diagrams carry the weight. Prose is sparse, plain, and uses the glossary terms (from the `codebase-design` skill) without ceremony.",
    # 23 (D23)
    "- **Files**: monospaced list in small type (`.mono`: a monospace stack at 0.875rem).",
    # 24 (D23)
    "### Inline-SVG graph (the workhorse for dependencies / call flow)",
    # 25 (D23)
    'Draw an inline-SVG graph (`.box` rectangles joined by `.edge` lines that end in the `#arrow` marker) when the point is "X calls Y calls Z, and look at the mess." Wrap it in a `.card` so it doesn\'t feel parachuted in. Use the stylesheet\'s classes to colour leakage edges red (`.leak` with the `#arrow-leak` marker: a solid red arrow) and the deep module dark (`.deep`, which also fills an SVG box). Sequence diagrams work well for "before: 6 round-trips; after: 1." (one vertical `.lifeline` per module, one horizontal `.edge` arrow per call).',
    # 26 (D23, D30)
    _GRAPH_EXAMPLE,
    # 27 (D23)
    "### Hand-built boxes-and-arrows (when the deep module needs visual weight)",
    # 28 (D23)
    'Modules as `<div>`s with borders and labels. Arrows as inline SVG `<line>` or `<path>` elements positioned absolutely over a relative container. Reach for this when you want the "after" diagram to feel like one thick-bordered deep module with greyed-out internals, since an SVG graph of equal boxes won\'t render that with the right weight.',
    # 29 (D23)
    "Stack horizontal bands (`.band`: 3rem tall with a thick left border) to show layers a call passes through. Before: 6 thin layers each doing nothing. After: 1 thick band (`.band.thick`) labelled with the consolidated responsibility.",
    # 30 (D23)
    "- Lean editorial, not corporate-dashboard. Generous whitespace. Serif optional for headings (a `Georgia, serif` stack works well with stone/slate).",
    # 31 (D23)
    "- Use the `.label` class (0.75rem, uppercase, 0.05em letter-spacing) for module labels inside diagrams, so they read as schematic, not as UI.",
    # 32 (D23)
    "- No scripts and no network: no external stylesheets, fonts or images, only the inline `<style>` block and inline SVG. The report is static: no app code, no interactivity.",
    # 33 (D17)
    "Plain English, concise, but the architectural nouns and verbs come straight from the `codebase-design` skill. Concision is not an excuse to drift.",
    # 34 (D17)
    "If a term isn't in the `codebase-design` glossary, reach for one that is before inventing a new one.",
)

_ICA_REPLACED: Final = (
    'Call the Skill tool with "codebase-design" for',  # 3
    "`GLOSSARY.md` gives names",  # 4
    "(`GLOSSARY.md`) and any ADRs",  # 5
    "Then spawn a sub-agent to walk the codebase.",  # 6
    "Open it for the user (",  # 7
    "`xdg-open <path>`",  # 7
    "`open <path>`",  # 7
    "`start <path>`",  # 7
    "**Tailwind via CDN**",  # 8
    "**Mermaid via CDN**",  # 8
    "Mix Mermaid with hand-crafted CSS/SVG visuals",  # 8
    "**Use GLOSSARY.md vocabulary",  # 9
    "If `GLOSSARY.md` defines",  # 9
    "`/codebase-design`",  # 10
    "[HTML-REPORT.md](HTML-REPORT.md)",  # 11
    'call the Skill tool with "grilling"',  # 12
    'call the Skill tool with "domain-modeling"',  # 13
    "not in `GLOSSARY.md`?**",  # 14
    "Add the term to `GLOSSARY.md`. Create",  # 14
    "Update `GLOSSARY.md` right there.",  # 15
    'Call the Skill tool with "codebase-design" and use',  # 16
)

_REPORT_REPLACED: Final = (
    "Tailwind and Mermaid both come from CDNs.",  # 18
    "Mix the two: don't lean on Mermaid for everything",  # 18
    "<script",  # 19: the Tailwind tag and the Mermaid module script
    "import mermaid from",  # 19
    "mermaid.initialize(",  # 19
    "small custom layer for things Tailwind doesn't cover cleanly",  # 20
    'class="bg-stone-50 text-slate-900 font-sans"',  # 21
    'class="max-w-5xl mx-auto px-6 py-12 space-y-12"',  # 21
    'class="space-y-10"',  # 21
    "(from the `/codebase-design` skill)",  # 22
    "`font-mono text-sm`",  # 23
    "### Mermaid graph",  # 24
    "Use a Mermaid `flowchart` or `graph`",  # 25
    "Tailwind-styled card",  # 25
    "Style with classDef",  # 25
    'class="rounded-lg border border-slate-200 bg-white p-4"',  # 26
    '<pre class="mermaid">',  # 26
    "flowchart LR",  # 26
    "-.leak.->",  # 26
    "classDef leak",  # 26
    "(when Mermaid's layout fights you)",  # 27
    "since Mermaid won't render",  # 28
    "(`h-12 border-l-4`)",  # 29
    "(`font-serif` works well",  # 30
    "`text-xs uppercase tracking-wider`",  # 31
    "The only scripts are the Tailwind CDN and the Mermaid ESM import.",  # 32
    "no interactivity beyond Mermaid's own rendering",  # 32
    "come straight from the `/codebase-design` skill.",  # 33
    "the `/codebase-design` glossary",  # 34
)

# --- throwaway-prototype (A.T06.2) ----------------------------------------------

_PROTOTYPE_HEAD: Final = (
    "---\n"
    "id: throwaway-prototype\n"
    "name: throwaway-prototype\n"
    "description: Build a throwaway prototype to answer a design question. Use when the user"
    " wants to sanity-check whether a state model or logic feels right, or explore what a UI"
    " should look like.\n"
    "---\n"
    "\n"
    "# Prototype\n"
)

_PROTOTYPE_NEW: Final = (
    # 3, 4 (D10); the U+2192 arrows stay
    (
        "SKILL.md",
        '- **"Does this logic / state model feel right?"** \u2192 [LOGIC.md](references/LOGIC.md). Build a single shareable HTML file (free-play buttons plus tabbed guided walkthroughs) that pushes the state machine through cases that are hard to reason about on paper, and that a non-developer can drive.',
    ),
    (
        "SKILL.md",
        '- **"What should this look like?"** \u2192 [UI.md](references/UI.md). Generate several radically different UI variations on a single route, switchable via a URL search param and a floating bottom bar.',
    ),
    # 6, 7 (D10)
    (
        "references/LOGIC.md",
        "Once the prototype has answered its question, capture the answer, then capture the prototype the way the [SKILL](../SKILL.md) describes.",
    ),
    (
        "references/UI.md",
        "Once a variant has won, capture the answer (which variant and why), then capture the prototype the way the [SKILL](../SKILL.md) describes.",
    ),
)

_PROTOTYPE_REPLACED: Final = (
    ("SKILL.md", "name: prototype\n"),  # 1
    ("SKILL.md", "[LOGIC.md](LOGIC.md)"),  # 3
    ("SKILL.md", "[UI.md](UI.md)"),  # 4
    ("references/LOGIC.md", "[SKILL](SKILL.md)"),  # 6
    ("references/UI.md", "[SKILL](SKILL.md)"),  # 7
)

#: Upstream text A.T06.2 keeps on purpose (D8, D20, D27, the toolchain allowlist).
_PROTOTYPE_KEPT: Final = (
    (
        "SKILL.md",
        "2. **Trivial to run.** A UI prototype starts from one command in the project's task runner: `pnpm <name>`, `python <path>`, `bun <path>`, etc.",
    ),
    ("references/LOGIC.md", "Send them the file, or open it for them."),  # L54, D20
    ("references/LOGIC.md", "this is the wrong branch. Use [UI.md](UI.md)."),  # 5
    ("references/UI.md", "this is the wrong branch. Use [LOGIC.md](LOGIC.md)."),  # 5
    (
        "references/UI.md",
        "For sub-shape B (new page): the throwaway route under `/prototype/<name>` mounts the same switcher.",
    ),
    ("references/UI.md", "include the word `prototype` in the path or filename"),  # L28, D8
    ("references/UI.md", "(TailwindCSS, shadcn, MUI, plain CSS, whatever)"),  # L51, D27
    ("references/UI.md", "gate on `process.env.NODE_ENV !== 'production'`"),  # L90, D27
)

# --- codebase-design (A.T06.3) --------------------------------------------------

_DESIGN_HEAD: Final = (
    "---\n"
    "id: codebase-design\n"
    "name: codebase-design\n"
    "description: Shared vocabulary for designing deep modules. Use when the user wants to design"
    " or improve a module's interface, find deepening opportunities, decide where a seam goes,"
    " make code more testable or AI-navigable, or when another skill needs the deep-module"
    " vocabulary.\n"
    "---\n"
    "\n"
    "# Codebase Design\n"
)

_DESIGN_NEW: Final = (
    # 3 (D10)
    (
        "SKILL.md",
        "- **Deepening a cluster given its dependencies**, see [DEEPENING.md](references/DEEPENING.md): dependency categories, seam discipline, and replace-don't-layer testing.",
    ),
    # 4 (D10); the descriptive "spin up parallel sub-agents" stays verbatim
    (
        "SKILL.md",
        "- **Exploring alternative interfaces**, see [DESIGN-IT-TWICE.md](references/DESIGN-IT-TWICE.md): spin up parallel sub-agents to design the interface several radically different ways, then compare on depth, locality, and seam placement.",
    ),
    # 5 (D10)
    (
        "references/DEEPENING.md",
        "How to deepen a cluster of shallow modules safely, given its dependencies. Assumes the vocabulary in [SKILL.md](../SKILL.md): **module**, **interface**, **seam**, **adapter**.",
    ),
    # 6 (D10)
    (
        "references/DESIGN-IT-TWICE.md",
        "Uses the vocabulary in [SKILL.md](../SKILL.md): **module**, **interface**, **seam**, **adapter**, **leverage**.",
    ),
    # 7 (D17): the fallback keeps independent briefs, one constraint each, the same outputs
    (
        "references/DESIGN-IT-TWICE.md",
        "If your harness can run subagents, spawn 3+ sub-agents in parallel; otherwise draft the 3+ designs yourself, one at a time, each held to its own brief, its own design constraint and the output list below, finishing one before you start the next. Each must produce a **radically different** interface for the deepened module.",
    ),
    # 8, 9 (D10, D21)
    (
        "references/DESIGN-IT-TWICE.md",
        "Include both [SKILL.md](../SKILL.md) vocabulary and GLOSSARY.md (or CONTEXT.md if the repo already has one) vocabulary in the brief so each sub-agent names things consistently with the architecture language and the project's domain language.",
    ),
)

_DESIGN_REPLACED: Final = (
    ("SKILL.md", "[DEEPENING.md](DEEPENING.md)"),  # 3
    ("SKILL.md", "[DESIGN-IT-TWICE.md](DESIGN-IT-TWICE.md)"),  # 4
    ("references/DEEPENING.md", "[SKILL.md](SKILL.md)"),  # 5
    ("references/DESIGN-IT-TWICE.md", "[SKILL.md](SKILL.md)"),  # 6, 8
    ("references/DESIGN-IT-TWICE.md", "Spawn 3+ sub-agents in parallel. Each"),  # 7
    ("references/DESIGN-IT-TWICE.md", "and GLOSSARY.md vocabulary in the brief"),  # 9
)

#: Descriptive sub-agent mentions stay verbatim (A.T06 note 5); the D27 examples stay too.
_DESIGN_KEPT: Final = (
    ("SKILL.md", "     const gateway = new StripeGateway();"),  # D27
    ("SKILL.md", '- **"Interface" as the TypeScript `interface` keyword'),  # D27
    ("references/DEEPENING.md", "(PGLite for Postgres, in-memory filesystem)"),  # D27
    ("references/DESIGN-IT-TWICE.md", "use this parallel sub-agent pattern."),  # L3
    ("references/DESIGN-IT-TWICE.md", "Before spawning sub-agents, write a user-facing"),  # L11
    ("references/DESIGN-IT-TWICE.md", "while the sub-agents work in parallel."),  # L17
    ("references/DESIGN-IT-TWICE.md", "### 2. Spawn sub-agents\n"),  # L19
    (
        "references/DESIGN-IT-TWICE.md",
        "Prompt each sub-agent with a separate technical brief",
    ),  # L23
    ("references/DESIGN-IT-TWICE.md", "Each sub-agent outputs:"),  # L32
    ("references/DESIGN-IT-TWICE.md", "(see [DEEPENING.md](DEEPENING.md))"),  # 2: sibling links
)

_NEW_TEXTS: Final = (
    *((ICA, "SKILL.md", text) for text in _ICA_NEW),
    *((ICA, REPORT, text) for text in _REPORT_NEW),
    *((PROTOTYPE, rel, text) for rel, text in _PROTOTYPE_NEW),
    *((DESIGN, rel, text) for rel, text in _DESIGN_NEW),
)
_REPLACED_TEXTS: Final = (
    *((ICA, "SKILL.md", text) for text in _ICA_REPLACED),
    *((ICA, REPORT, text) for text in _REPORT_REPLACED),
    *((PROTOTYPE, rel, text) for rel, text in _PROTOTYPE_REPLACED),
    *((DESIGN, rel, text) for rel, text in _DESIGN_REPLACED),
)
_KEPT_TEXTS: Final = (
    *((PROTOTYPE, rel, text) for rel, text in _PROTOTYPE_KEPT),
    *((DESIGN, rel, text) for rel, text in _DESIGN_KEPT),
)
#: The distinct box-drawing characters of each line of codebase-design's two diagrams.
_BOX_TOP: Final = "\u2500\u250c\u2510"
_BOX_SIDE: Final = "\u2502"
_BOX_ARROW: Final = "\u2190\u2502"  # a box side carrying a U+2190 annotation
_BOX_MID: Final = "\u2500\u251c\u2524"
_BOX_BOTTOM: Final = "\u2500\u2514\u2518"

#: Lines per file after the changes (A.T06 file tables): a guard on "verbatim elsewhere".
_LINE_COUNTS: Final = {
    (ICA, "SKILL.md"): 74,
    (ICA, REPORT): 163,
    (PROTOTYPE, "SKILL.md"): 27,
    (PROTOTYPE, "references/LOGIC.md"): 67,
    (PROTOTYPE, "references/UI.md"): 112,
    (DESIGN, "SKILL.md"): 115,
    (DESIGN, "references/DEEPENING.md"): 37,
    (DESIGN, "references/DESIGN-IT-TWICE.md"): 44,
}
#: Plugin line -> upstream's non-ASCII characters on it; new text adds none (no em dashes).
_NON_ASCII: Final = {
    (ICA, "SKILL.md"): {59: "\u2026"},
    (ICA, REPORT): {86: "\u2264", 152: "\u00b7", 163: "\u2026"},
    (PROTOTYPE, "SKILL.md"): {15: "\u2192", 16: "\u2192", 18: "\u2192"},
    (PROTOTYPE, "references/LOGIC.md"): {},
    (PROTOTYPE, "references/UI.md"): {88: "\u2190\u2192"},
    # the two box-drawing diagrams, upstream L35-L41 and L47-L51, byte-identical
    (DESIGN, "SKILL.md"): {
        36: _BOX_TOP,
        37: _BOX_ARROW,
        38: _BOX_MID,
        39: _BOX_SIDE,
        40: _BOX_ARROW,
        41: _BOX_SIDE,
        42: _BOX_BOTTOM,
        48: _BOX_TOP,
        49: _BOX_ARROW,
        50: _BOX_MID,
        51: _BOX_ARROW,
        52: _BOX_BOTTOM,
    },
    (DESIGN, "references/DEEPENING.md"): {},
    (DESIGN, "references/DESIGN-IT-TWICE.md"): {25: "\u2013"},
}
#: The listing-budget share of T06's skills (A.T06 note 9): 125 + 179 + 265 characters.
_DESCRIPTION_CHARS: Final = {ICA: 125, PROTOTYPE: 179, DESIGN: 265}


@pytest.mark.parametrize("case", _NEW_TEXTS, ids=_case_id)
def test_new_text_is_in_its_file(case: tuple[str, str, str]) -> None:
    skill_id, rel, text = case
    assert text in _read(skill_id, rel), f"skills/{skill_id}/{rel} lacks the A.T06 text"


@pytest.mark.parametrize("case", _REPLACED_TEXTS, ids=_case_id)
def test_replaced_upstream_text_is_gone(case: tuple[str, str, str]) -> None:
    skill_id, rel, text = case
    assert text not in _read(skill_id, rel), f"skills/{skill_id}/{rel} keeps replaced text"


@pytest.mark.parametrize("case", _KEPT_TEXTS, ids=_case_id)
def test_kept_upstream_text_is_verbatim(case: tuple[str, str, str]) -> None:
    skill_id, rel, text = case
    assert text in _read(skill_id, rel), f"skills/{skill_id}/{rel} lost upstream text A.T06 keeps"


@pytest.mark.parametrize(("skill_id", "chars"), _DESCRIPTION_CHARS.items())
def test_description_is_upstream_verbatim_length(skill_id: str, chars: int) -> None:
    assert len(str(split_skill(skill_id)[0]["description"])) == chars


@pytest.mark.parametrize(("where", "count"), _LINE_COUNTS.items(), ids=lambda v: str(v))
def test_file_has_the_expected_line_count_and_lf_endings(
    where: tuple[str, str], count: int
) -> None:
    text = _read(*where)
    assert "\r" not in text and text.endswith("\n") and not text.endswith("\n\n")
    assert text.count("\n") == count


@pytest.mark.parametrize(("where", "expected"), _NON_ASCII.items(), ids=lambda v: str(v))
def test_only_upstream_non_ascii_characters_and_on_their_lines(
    where: tuple[str, str], expected: dict[int, str]
) -> None:
    found = {
        number: "".join(sorted({c for c in line if ord(c) > 127}))
        for number, line in enumerate(_read(*where).split("\n"), 1)
        if not line.isascii()
    }
    assert found == expected


def test_ica_frontmatter_and_guard_line_open_the_file() -> None:
    assert _read(ICA, "SKILL.md").startswith(_ICA_HEAD)


def test_ica_loads_its_three_skills_in_order() -> None:
    targets = LOAD_RE.findall(_read(ICA, "SKILL.md"))
    assert targets == ["codebase-design", "grilling", "domain-modeling", "codebase-design"]


def test_prototype_frontmatter_is_renamed_and_model_invoked() -> None:
    # wayfinder loads it, so it stays model-invoked: no disable-model-invocation (A.T06.2).
    assert _read(PROTOTYPE, "SKILL.md").startswith(_PROTOTYPE_HEAD)


def test_codebase_design_frontmatter_is_verbatim_and_model_invoked() -> None:
    # improve-codebase-architecture and tdd load it, so it stays model-invoked (A.T06.3).
    assert _read(DESIGN, "SKILL.md").startswith(_DESIGN_HEAD)


@pytest.mark.parametrize(
    ("skill_id", "excerpts"),
    [(ICA, []), (PROTOTYPE, ["`pnpm <name>`", "`bun <path>`"]), (DESIGN, [])],
)
def test_allowlist_holds_only_the_project_toolchain_of_a_t06(
    skill_id: str, excerpts: list[str]
) -> None:
    entries = load_allowlist(skill_id)
    assert [(e.path, e.excerpt) for e in entries] == [("SKILL.md", x) for x in excerpts]


# --- the rename (A.T06.2 skill-specific test 1) ---------------------------------

#: (old, new) D8 renames this ticket owns; the two-axis-review and pr-body lane owns theirs.
_RENAMES: Final = (("prototype", "throwaway-prototype"),)


def _old_id_reference(old: str) -> re.Pattern[str]:
    """A slash label ending right after the id, a "`<id>` skill" load, or a Skill-tool call."""
    name = re.escape(old)
    return re.compile(rf"`/{name}`|`{name}` skill|Skill tool with \"{name}\"")


@pytest.mark.parametrize(
    ("line", "hit"),
    [
        ("- **`/prototype`** to answer the question with throwaway code,", True),
        ("by loading the `prototype` skill.", True),
        ('by calling the Skill tool with "prototype".', True),
        ("the throwaway route under `/prototype/<name>` mounts the same switcher.", False),
        ("include the word `prototype` in the path or filename", False),
        ("a `prototype/<name>` branch out of main", False),
        ("- **Prototype** (HITL): a `wayfinder:prototype` ticket", False),
    ],
)
def test_old_id_reference_pattern_fires_only_on_skill_references(line: str, hit: bool) -> None:
    assert (_old_id_reference("prototype").search(line) is not None) is hit


@pytest.mark.parametrize(("old", "new"), _RENAMES)
def test_renamed_id_has_no_inbound_references(old: str, new: str) -> None:
    assert not (SKILLS_ROOT / old).exists(), f"skills/{old}/ must be renamed to skills/{new}/"
    assert (SKILLS_ROOT / new / "SKILL.md").is_file()
    pattern = _old_id_reference(old)
    hits = [
        f"{path.relative_to(SKILLS_ROOT)}:{number}: {line.strip()}"
        for path in sorted(SKILLS_ROOT.rglob("*.md"))
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1)
        if pattern.search(line)
    ]
    assert hits == [], f"a reference to the old id {old!r}; name {new!r} instead (D8)"


# --- the self-contained report (A.T06.1 skill-specific tests) -------------------


def _html_blocks() -> list[str]:
    """The fenced ``html`` blocks of HTML-REPORT.md, fences excluded."""
    blocks: list[str] = []
    current: list[str] | None = None
    for line in _read(ICA, REPORT).split("\n"):
        if current is None and line == "```html":
            current = []
        elif current is not None and line == "```":
            blocks.append("\n".join(current))
            current = None
        elif current is not None:
            current.append(line)
    return blocks


def _scaffold() -> str:
    blocks = _html_blocks()
    assert len(blocks) == 2, f"expected the scaffold and the graph example, got {len(blocks)}"
    assert blocks[0].startswith("<!doctype html>")
    return blocks[0]


def _stylesheet() -> str:
    """The scaffold's only ``<style>`` text, comments removed."""
    styles = re.findall(r"<style>(.*?)</style>", "\n".join(_html_blocks()), flags=re.DOTALL)
    assert len(styles) == 1, "one inline <style> block (D23)"
    return re.sub(r"/\*.*?\*/", "", styles[0], flags=re.DOTALL)


def _report_prose() -> str:
    """HTML-REPORT.md with its two html blocks blanked."""
    text = _read(ICA, REPORT)
    for block in _html_blocks():
        text = text.replace(block, "")
    return text


def test_report_snippets_load_nothing() -> None:
    for block in _html_blocks():
        for token in ("<script", "<link", "@import", "src=", "xmlns"):
            assert token not in block, f"{token!r} in a report snippet (D23)"
    assert "<svg" in _html_blocks()[1], "the graph example is inline SVG"


def test_report_selectors_keep_the_cascade_order() -> None:
    selectors = [
        selector.strip()
        for group in re.findall(r"([^{}]+)\{", _stylesheet())
        for selector in group.split(",")
    ]
    assert selectors == [
        *("body", "main", "#candidates", "#candidates > article", "#top-recommendation"),
        *(".card", ".badges", ".badge", ".badge-strong", ".badge-exploring"),
        *(".badge-speculative", ".tag", ".mono", ".adr", ".before-after", ".diagram"),
        *("svg", ".diagram > svg", ".defs", ".label", ".module", ".faded", ".band"),
        *(".band.thick", "svg text", ".box", ".edge", ".lifeline", ".head", ".head-leak"),
        *(".leak-label", ".seam", ".leak", ".deep", ".module.deep", "svg .deep"),
        "svg .on-deep",
    ]


#: The classes HTML-REPORT.md's prose names in code spans (changes 23, 25, 29, 31).
_PROSE_CLASSES: Final = frozenset(
    {".box", ".edge", ".card", ".leak", ".deep", ".lifeline", ".band", ".band.thick"}
    | {".mono", ".label"}
)


def test_report_classes_are_defined() -> None:
    # Guards the D23 risk of a class the hand-written stylesheet never styles.
    defined = set(re.findall(r"\.([A-Za-z][\w-]*)", re.sub(r"\{[^}]*\}", "", _stylesheet())))
    used = {
        token
        for block in _html_blocks()
        for attribute in re.findall(r'class="([^"]*)"', block)
        for token in attribute.split()
    }
    assert used - defined == set(), "a class the stylesheet does not define"
    prose = set(re.findall(r"`(\.[A-Za-z][\w.-]*)`", _report_prose()))
    assert prose == _PROSE_CLASSES
    named = {name for span in prose for name in span.split(".") if name}
    assert named - defined == set(), "a prose class the stylesheet does not define"


def test_report_marker_ids_resolve() -> None:
    blocks = "\n".join(_html_blocks())
    referenced = set(re.findall(r"url\(#([\w-]+)\)", blocks))
    referenced |= set(re.findall(r"`#([\w-]+)`", _report_prose()))
    assert referenced == {"arrow", "arrow-leak"}
    assert referenced <= set(re.findall(r'id="([^"]+)"', _scaffold()))


class _TagStack(HTMLParser):
    """Track open tags; a mismatched or unclosed tag is a balance error."""

    _VOID: Final = frozenset({"meta"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.stack: list[str] = []
        self.mismatches: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in self._VOID:
            self.stack.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """``<x />`` opens nothing; the default would route it through the two handlers."""

    def handle_endtag(self, tag: str) -> None:
        if self.stack and self.stack[-1] == tag:
            self.stack.pop()
        else:
            self.mismatches.append(tag)


@pytest.mark.parametrize("index", [0, 1], ids=["scaffold", "graph-example"])
def test_report_html_is_balanced(index: int) -> None:
    parser = _TagStack()
    parser.feed(_html_blocks()[index])
    parser.close()
    assert (parser.stack, parser.mismatches) == ([], [])


def _ica_files() -> list[Path]:
    return sorted(p for p in (SKILLS_ROOT / ICA).rglob("*") if p.is_file())


def test_no_tailwind_mermaid_cdn_or_xmlns_left() -> None:
    # Scoped to this skill: throwaway-prototype's UI.md names "TailwindCSS" legitimately.
    pattern = re.compile(r"(?i)tailwind|mermaid|\bcdn\b|xmlns")
    hits = [
        f"{path.relative_to(SKILLS_ROOT)}:{number}: {match.group(0)}"
        for path in _ica_files()
        for number, line in enumerate(path.read_text(encoding="utf-8").split("\n"), 1)
        for match in pattern.finditer(line)
    ]
    assert hits == []


def test_opener_is_capability_phrased() -> None:
    assert D20_SENTENCE in _read(ICA, "SKILL.md")


def test_every_glossary_mention_carries_its_fallback() -> None:
    # D21 form (A.T06 note 3): code-formatted only where upstream code-formats GLOSSARY.md.
    mention = re.compile(
        r"GLOSSARY\.md(?P<tick>`?)(?P<fallback> \(or (?P<ctick>`?)CONTEXT\.md(?P=ctick)"
        r" if the repo already has one\))?"
    )
    counts: dict[str, int] = {}
    for skill_id, rel in _LINE_COUNTS:
        matches = list(mention.finditer(_read(skill_id, rel)))
        bad = [m.group(0) for m in matches if not m["fallback"] or m["tick"] != m["ctick"]]
        assert bad == [], f"skills/{skill_id}/{rel}: a mention without the D21 fallback"
        counts[f"{skill_id}/{rel}"] = len(matches)
    expected = dict.fromkeys((f"{skill_id}/{rel}" for skill_id, rel in _LINE_COUNTS), 0)
    assert counts == expected | {f"{ICA}/SKILL.md": 7, f"{DESIGN}/references/DESIGN-IT-TWICE.md": 1}


def test_no_t06_file_names_the_glossary_map() -> None:
    assert [where for where in _LINE_COUNTS if "GLOSSARY-MAP" in _read(*where)] == []


# --- relative links (A.T06.3 skill-specific test) -------------------------------


def _relative_links(skill_id: str) -> list[tuple[Path, int, str]]:
    """``(file, line, target)`` of every relative markdown link of one skill's docs.

    A target with a scheme, a ``#`` anchor or teach's ``{link}`` placeholder (D24) is
    not a file reference; a ``#fragment`` is dropped.
    """
    return [
        (doc, link.line, link.target.split("#", 1)[0])
        for doc in skill_docs(skill_id)
        for link in extract_markdown_links(doc.read_text(encoding="utf-8"))
        if not (urlsplit(link.target).scheme or link.target.startswith("#"))
        and link.target != "{link}"
    ]


def _resolves_in_skill(doc: Path, target: str, skill_dir: Path) -> bool:
    """Whether ``target``, read from ``doc``'s directory, names a file inside ``skill_dir``."""
    resolved = Path(os.path.normpath(doc.parent / target))  # lexical: no symlink walk
    return resolved.is_relative_to(skill_dir) and resolved.is_file()


@pytest.mark.parametrize("skill_id", present_skill_ids())
def test_relative_links_resolve(skill_id: str) -> None:
    # Stricter than G21, which lets a link reach anywhere in the plugin: a link must
    # resolve inside its own skill directory, the only tree sync copies with it.
    skill_dir = SKILLS_ROOT / skill_id
    bad = [
        f"{doc.relative_to(SKILLS_ROOT)}:{line}: {target}"
        for doc, line, target in _relative_links(skill_id)
        if not _resolves_in_skill(doc, target, skill_dir)
    ]
    assert bad == [], "a relative link that leaves its skill or names no file (D10)"


def test_relative_link_scan_sees_every_t06_link() -> None:
    # codebase-design: SKILL.md 2, DEEPENING.md 1, DESIGN-IT-TWICE.md 5;
    # throwaway-prototype: SKILL.md 2, LOGIC.md 2, UI.md 2; improve-codebase-architecture: 1.
    counts = {skill_id: len(_relative_links(skill_id)) for skill_id in (DESIGN, PROTOTYPE, ICA)}
    assert counts == {DESIGN: 8, PROTOTYPE: 6, ICA: 1}


# --- ATTRIBUTIONS.md: the improve-codebase-architecture section (A.T06.1) ---------

_ICA_ATTRIBUTION_TEXTS: Final[tuple[str, ...]] = (
    # Change 37: both CDN hosts, written bare so no URL gate matches them.
    "from the hosts cdn.tailwindcss.com and cdn.jsdelivr.net",
    # Change 37: the URL gate is not why the webbrowser fallback was rejected.
    "A run-time file URL would leave no literal in the plugin, so the URL gate is not the reason",
    # Changes 19 and 26: the decision tags the spec gives.
    "both URLs and both CDN assets (D4, D23, D30).",
    "dashed means seam (D23, D30).",
)


def _ica_attribution_section() -> str:
    """The section's text with line wraps collapsed, so a rewrap never fails a check."""
    text = (PLUGIN_ROOT / "ATTRIBUTIONS.md").read_text(encoding="utf-8")
    start = text.index(f"### {ICA}\n")
    end = text.find("\n### ", start + 1)
    return " ".join((text[start:] if end == -1 else text[start:end]).split())


@pytest.mark.parametrize("expected", _ICA_ATTRIBUTION_TEXTS, ids=lambda t: t[:40])
def test_ica_attribution_records_change_37_and_the_spec_tags(expected: str) -> None:
    assert expected in _ica_attribution_section(), f"missing from the {ICA} section: {expected!r}"
