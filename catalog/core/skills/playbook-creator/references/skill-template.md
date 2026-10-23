# Skill template

Copy the parts the new skill needs, replace every placeholder, then run `playbook validate`. The example is the fictional skill acme-billing. In the engine, a core skill also needs its pins (`playbook-engine-catalog-gate`).

## Contents

- Directory tree
- SKILL.md frontmatter
- SKILL.md body
- The composed description and open_when lines
- Guide and script skeletons
- Checklist

## Directory tree

Keep only what the skill needs; `playbook-skill-files` says what each kind may hold.

```text
skills/acme-billing/
├── SKILL.md
├── rules/acme-decimal-amounts.md  # members, found by their directory
├── references/rounding.md         # one level deep, listed below
├── scripts/check_amounts.py       # stdlib only
└── examples/invoice-api/          # a small complete app
```

## SKILL.md frontmatter

`playbook-skill-md` explains each key; `playbook-skill-sections` the sections.

```yaml
id: acme-billing                 # equals name and the directory name
name: acme-billing
description: "Conventions for Acme billing code and invoice data."
# capabilities: [clarify]        # a framework skill only: the roles it fills
playbook:
  use_when: "editing billing, invoicing or payment code"   # the engine adds "Use when"
  files: "Billing and invoicing modules"                   # at most 80 characters, no period
  sections:                      # CRITICAL to LOW, 2-8, each with a member
    - id: money
      title: "Money"             # at most 40 characters
      impact: HIGH
      summary: "Amounts are exact decimals in one currency per value."
      open_when: "Adding or changing an amount, a currency field, rounding or a tax computation."
    - id: invoices
      title: "Invoices"
      impact: MEDIUM
      summary: "Invoice ids and states follow one lifecycle."
      open_when: "Creating, numbering, voiding or reissuing an invoice, or editing its state machine."
  references:                    # one entry per guide and per example app
    - path: references/rounding.md
      open_when: "Choosing where and how an amount is rounded."
    - path: examples/invoice-api
      open_when: "Wiring the billing rules into a small web app end to end."
      applies_if: {any_framework: [fastapi]}
```

## SKILL.md body

```markdown
# Acme billing

How Acme code computes, stores and shows money and invoices.

## Quick reference
- Amounts are decimals with a currency, never floats.

## See also
- acme-payments: provider calls and webhooks.
```

After it the engine appends "How to use this skill", one rules heading per active section with its open_when line, and "References and examples".

## The composed description and open_when lines

The engine lists `<description> Covers <section titles>. Use when <use_when>.`, counted with every declared section, at most 300 characters: "Conventions for Acme billing code and invoice data. Covers money, invoices. Use when editing billing, invoicing or payment code." To shorten it, tighten the description, then the titles, then use_when.

An open_when line names a concrete trigger the agent meets while working: "Adding or changing an amount, a currency field, rounding or a tax computation."; "Creating, numbering, voiding or reissuing an invoice."; "Choosing where and how an amount is rounded." Avoid: "Money." (restates the title), "Editing billing code." (overlaps every section), "When it matters." (names no trigger).

## Guide and script skeletons

An engine-written guide routes situations to rules, never repeats a rule body, and stays within 120 lines:

```markdown
# Rounding: which rule owns it

| Situation | Rule |
| --- | --- |
| A line total is computed | acme-decimal-amounts |
```

A script is stdlib-only Python 3.10, prints JSON and exits 2 on a usage error:

```python
"""Report billing modules that call float() as JSON for the agent to judge."""

import json
import sys
from pathlib import Path


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: check_amounts.py <directory>", file=sys.stderr)
        return 2
    files = sorted(Path(argv[0]).rglob("*.py"))
    hits = [str(path) for path in files if "float(" in path.read_text(encoding="utf-8")]
    print(json.dumps({"hits": hits}))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

## Checklist

- 2-8 sections ordered CRITICAL to LOW, each with at least one member; every guide and example app listed.
- One third-person description sentence; the composed text at most 300 characters; the body holds no rule id, link, URL or template syntax.
