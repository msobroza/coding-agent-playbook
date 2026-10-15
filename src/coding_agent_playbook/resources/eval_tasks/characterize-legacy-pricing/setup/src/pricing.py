"""Checkout pricing. All amounts are integer cents.

The nightly invoicing job reconciles against the exact totals this module
returns, and nothing here has tests yet.
"""

AUDIT_LOG = "pricing_audit.log"
BULK_MIN_QUANTITY = 10
BULK_PERCENT_OFF = 10
MEMBER_PERCENT_OFF = 5
SHIPPING_CENTS = 499
FREE_SHIPPING_OVER_CENTS = 5000


def line_total(unit_cents: int, quantity: int) -> int:
    """Price of one order line; buying 10 or more units takes 10% off."""
    if quantity <= 0:
        return 0
    total = unit_cents * quantity
    if quantity > BULK_MIN_QUANTITY:
        total = round(total * (100 - BULK_PERCENT_OFF) / 100)
    return total


def apply_coupon(subtotal_cents: int, coupon: str | None) -> int:
    """Apply a coupon: HALF halves the subtotal, FLAT<n> takes n cents off."""
    if not coupon:
        return subtotal_cents
    if coupon == "HALF":
        return round(subtotal_cents / 2)
    if coupon.startswith("FLAT"):
        return subtotal_cents - int(coupon[4:])
    return subtotal_cents


def order_total(
    lines: list[tuple[int, int]], member: bool = False, coupon: str | None = None
) -> int:
    """Amount to charge for an order of (unit_cents, quantity) lines, shipping included."""
    subtotal = sum(line_total(unit, quantity) for unit, quantity in lines)
    if member:
        subtotal -= subtotal * MEMBER_PERCENT_OFF // 100
    subtotal = apply_coupon(subtotal, coupon)
    shipping = 0 if subtotal > FREE_SHIPPING_OVER_CENTS else SHIPPING_CENTS
    total = subtotal + shipping
    with open(AUDIT_LOG, "a", encoding="utf-8") as audit:
        audit.write(f"{len(lines)} lines, member={member}, coupon={coupon}: {total}\n")
    return total
