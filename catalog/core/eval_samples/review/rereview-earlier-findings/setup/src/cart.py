"""A shopping cart priced in whole cents."""


class Cart:
    def __init__(self) -> None:
        # sku -> (unit price in cents, quantity held)
        self.lines: dict[str, tuple[int, int]] = {}

    def add(self, sku: str, unit_cents: int, quantity: int = 1) -> None:
        if quantity <= 0:
            raise ValueError(f"quantity must be positive, got {quantity}")
        price, held = self.lines.get(sku, (unit_cents, 0))
        self.lines[sku] = (price, held + quantity)

    def remove(self, sku: str, quantity: int = 1) -> None:
        price, held = self.lines[sku]
        if not 0 < quantity <= held:
            raise ValueError(f"cannot remove {quantity} of {sku!r}: {held} held")
        if quantity == held:
            del self.lines[sku]
        else:
            self.lines[sku] = (price, held - quantity)

    def total_cents(self, discount_percent: int = 0) -> int:
        subtotal = sum(price * held for price, held in self.lines.values())
        return subtotal * (100 - discount_percent) // 100
