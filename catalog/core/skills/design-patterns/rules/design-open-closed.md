---
id: design-open-closed
name: Open/closed
description: "Add a new variant by adding a function, a mapping entry or a class, not by editing a growing if/elif or isinstance ladder."
scope: scoped
globs:
  - "**/*.py"
section: abstractions
priority: 46
tags: [python, design, solid]
---

# Open/closed

## Description

Code should be open for extension but closed for modification: add new behavior by introducing a new variant, not by editing and retesting a stable code path. In Python the lightest variant is a function: a mapping of `Callable`s keyed by an `Enum` replaces the ladder, and each kind carries its own behavior (polymorphism) instead of the call site testing kinds. Use `Protocol` classes when each variant has several related methods.

## Bad Example

```python
class InvoiceExporter:
    def export(self, invoice: Invoice, export_format: str) -> str:
        # Every new format requires editing this method
        if export_format == "json":
            return json.dumps(invoice.to_record())
        if export_format == "csv":
            return ",".join(invoice.to_row())
        if export_format == "xml":
            return f"<invoice>{invoice.number}</invoice>"
        raise ValueError(f"Unsupported format: {export_format!r}")
```

## Good Example

```python
class ExportFormat(Enum):
    JSON = "json"
    CSV = "csv"


ExportInvoice = Callable[[Invoice], str]

EXPORTERS: Final[Mapping[ExportFormat, ExportInvoice]] = {
    ExportFormat.JSON: export_json,
    ExportFormat.CSV: export_csv,
}


def export_invoice(invoice: Invoice, export_format: ExportFormat) -> str:
    return EXPORTERS[export_format](invoice)
```

When each variant has several methods, use small Protocol classes, injected:

```python
class InvoiceFormat(Protocol):
    def export(self, invoice: Invoice) -> str: ...
    def file_suffix(self) -> str: ...


class XmlInvoiceFormat:  # added without touching InvoiceExporter
    def export(self, invoice: Invoice) -> str:
        return f"<invoice>{invoice.number}</invoice>"

    def file_suffix(self) -> str:
        return ".xml"


class InvoiceExporter:
    def __init__(self, invoice_format: InvoiceFormat) -> None:
        self._format = invoice_format

    def export(self, invoice: Invoice) -> str:
        return self._format.export(invoice)
```

## Notes

- A growing `if`/`elif` chain, a `match` on type names, or `isinstance` tests in one chain (smell id isinstance-ladder) are the usual signal: each new type forces another edit, and a forgotten branch silently falls through. Put the behavior on the types behind a method or Protocol; use `functools.singledispatch` for types you do not own.
- Rules as data: a list of predicates (`RejectionRule = Callable[[Order, Customer], bool]`) checked with `any(...)` grows by appending, not by editing the checks.
- Restraint: with one or two variants that rarely change, keep the branch. A closed `Enum` matched once, with an exhaustive `match` that ends in a raising `case _`, is clearer than a registry: one edit site, with type-checker help.
- Apply the principle where the code path is stable and new variants are expected, not on every branch.
- Keys that arrive as data (config strings, unknown-key errors, registries filled by register calls) belong to design-dispatch-table; this rule keeps the Enum-keyed mapping.
