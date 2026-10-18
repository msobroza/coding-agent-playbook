# HTML Report Format

The architectural review is rendered as a single self-contained HTML file in the OS temp directory. Nothing loads from the network: one inline `<style>` block does the styling, and hand-built divs and inline SVG draw every diagram, the graph-shaped ones (call graphs, dependencies, sequences) as well as the more editorial visuals (mass diagrams, cross-sections). Mix the patterns below: don't lean on one for everything, it'll start to look generic.

## Scaffold

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

## Header

Repo name, date, and a compact legend: solid box = module, dashed line = seam, red arrow = leakage, thick dark box = deep module. No introduction paragraph. Straight into the candidates.

## Candidate card

The diagrams carry the weight. Prose is sparse, plain, and uses the glossary terms (from the `codebase-design` skill) without ceremony.

Each candidate is one `<article>`:

- **Title**: short, names the deepening (e.g. "Collapse the Order intake pipeline").
- **Badge row**: recommendation strength (`Strong` = emerald, `Worth exploring` = amber, `Speculative` = slate), plus a tag for the dependency category (`in-process`, `local-substitutable`, `ports & adapters`, `mock`).
- **Files**: monospaced list in small type (`.mono`: a monospace stack at 0.875rem).
- **Before / After diagram**: the centrepiece. Two columns, side by side. See patterns below.
- **Problem**: one sentence. What hurts.
- **Solution**: one sentence. What changes.
- **Wins**: bullets, ≤6 words each. e.g. "Tests hit one interface", "Pricing logic stops leaking", "Delete 4 shallow wrappers".
- **ADR callout** (if applicable): one line in an amber-tinted box.

No paragraphs of explanation. If the diagram needs a paragraph to be understood, redraw the diagram.

## Diagram patterns

Pick the pattern that fits the candidate. Mix them. Don't make every diagram look the same. Variety is part of the point.

### Inline-SVG graph (the workhorse for dependencies / call flow)

Draw an inline-SVG graph (`.box` rectangles joined by `.edge` lines that end in the `#arrow` marker) when the point is "X calls Y calls Z, and look at the mess." Wrap it in a `.card` so it doesn't feel parachuted in. Use the stylesheet's classes to colour leakage edges red (`.leak` with the `#arrow-leak` marker: a solid red arrow) and the deep module dark (`.deep`, which also fills an SVG box). Sequence diagrams work well for "before: 6 round-trips; after: 1." (one vertical `.lifeline` per module, one horizontal `.edge` arrow per call).

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

### Hand-built boxes-and-arrows (when the deep module needs visual weight)

Modules as `<div>`s with borders and labels. Arrows as inline SVG `<line>` or `<path>` elements positioned absolutely over a relative container. Reach for this when you want the "after" diagram to feel like one thick-bordered deep module with greyed-out internals, since an SVG graph of equal boxes won't render that with the right weight.

### Cross-section (good for layered shallowness)

Stack horizontal bands (`.band`: 3rem tall with a thick left border) to show layers a call passes through. Before: 6 thin layers each doing nothing. After: 1 thick band (`.band.thick`) labelled with the consolidated responsibility.

### Mass diagram (good for "interface as wide as implementation")

Two rectangles per module: one for interface surface area, one for implementation. Before: interface rectangle is nearly as tall as the implementation rectangle (shallow). After: interface rectangle is short, implementation rectangle is tall (deep).

### Call-graph collapse

Before: a tree of function calls rendered as nested boxes. After: the same tree collapsed into one box, with the now-internal calls shown faded inside it.

## Style guidance

- Lean editorial, not corporate-dashboard. Generous whitespace. Serif optional for headings (a `Georgia, serif` stack works well with stone/slate).
- Colour sparingly: one accent (emerald or indigo) plus red for leakage and amber for warnings.
- Keep diagrams ~320px tall so before/after sits comfortably side by side without scrolling.
- Use the `.label` class (0.75rem, uppercase, 0.05em letter-spacing) for module labels inside diagrams, so they read as schematic, not as UI.
- No scripts and no network: no external stylesheets, fonts or images, only the inline `<style>` block and inline SVG. The report is static: no app code, no interactivity.

## Top recommendation section

One larger card. Candidate name, one sentence on why, anchor link to its card. That's it.

## Tone

Plain English, concise, but the architectural nouns and verbs come straight from the `codebase-design` skill. Concision is not an excuse to drift.

**Use exactly:** module, interface, implementation, depth, deep, shallow, seam, adapter, leverage, locality.

**Never substitute:** component, service, unit (for module) · API, signature (for interface) · boundary (for seam) · layer, wrapper (for module, when you mean module).

**Phrasings that fit the style:**

- "Order intake module is shallow: interface nearly matches the implementation."
- "Pricing leaks across the seam."
- "Deepen: one interface, one place to test."
- "Two adapters justify the seam: HTTP in prod, in-memory in tests."

**Wins bullets** name the gain in glossary terms: *"locality: bugs concentrate in one module"*, *"leverage: one interface, N call sites"*, *"interface shrinks; implementation absorbs the wrappers"*. Don't write *"easier to maintain"* or *"cleaner code"*, because those terms aren't in the glossary and don't earn their place.

No hedging, no throat-clearing, no "it's worth noting that…". If a sentence could be a bullet, make it a bullet. If a bullet could be cut, cut it. If a term isn't in the `codebase-design` glossary, reach for one that is before inventing a new one.
