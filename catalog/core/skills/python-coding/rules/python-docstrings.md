---
id: python-docstrings
name: Docstrings
description: "Every public module, class and function gets a docstring: an intent line, then one usage example."
scope: scoped
globs:
  - "**/*.py"
section: types
priority: 44
tags: [python, docs]
lint_codes:
  warn: [D100, D101, D102, D103, D104, D105, D106, D107]
---

# Docstrings

## Description

Give every new public module, class, function, method and exception a docstring, and keep the ones that exist. A docstring is part of the contract: its first line states the intent, what the caller gets rather than how the body works, and after a blank line it shows one usage example. Below that it explains what the signature cannot: the errors a caller must handle, side effects, and what a value means, with its units and limits.

## Bad Example

```python
def charge(customer, amount, currency, capture=True):
    result = gateway.create_charge(customer.id, amount, currency, capture)
    audit_log.write("charge_created", result.id)
    return result


class InvoiceService:
    def void(self, invoice_id): ...
```

## Good Example

```python
def charge(customer: Customer, amount: Decimal, currency: str, *, capture: bool = True) -> Charge:
    """Charge a customer through the payment gateway and record it in the audit log.

    Example:
        >>> charge(customer, Decimal("12.50"), "EUR").status
        'captured'

    Args:
        amount: Positive amount in the currency's major unit, at most 10,000.
        currency: ISO 4217 code, such as "EUR" or "JPY".
        capture: Capture the funds now; False only authorizes them.

    Returns:
        The gateway's charge, captured or only authorized as `capture` asked.

    Raises:
        PaymentDeclinedError: The gateway rejected the charge.
        PaymentGatewayError: The gateway request failed.
    """
    result = gateway.create_charge(customer.id, amount, currency, capture=capture)
    audit_log.write("charge_created", result.id)
    return result


class InvoiceService:
    """Moves invoices through their lifecycle: issue, pay, void.

    Example:
        >>> InvoiceService(repository).void(invoice_id)
    """
```

## Notes

- A name is public when no part of its dotted path starts with `_`; a module is public when its file name does not.
- Any one of these counts as the usage example: a doctest line (`>>> load("config.toml")`); an `Example:`, `Examples:` or `Usage:` header followed by the call; a numpy-style `Examples` header underlined with `--------`; or a reST literal block introduced by `::`, such as `Usage::`.
- Google-style `Args:`, `Returns:` and `Raises:` sections are optional: follow the style the module already uses. The intent line and the usage example are the required parts.
- Say what a value means, never restate a type the annotation already states.
- Update the docstring in the same change that alters the behavior, the parameters or the errors raised.
- Private helpers need no docstring when their name and local context make the purpose plain; never add one only to satisfy a count.
- Comments inside the body say why, not what: `python-comments-why`.
