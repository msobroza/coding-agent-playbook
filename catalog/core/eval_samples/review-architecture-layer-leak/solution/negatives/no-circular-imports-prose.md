I reviewed `shop/orders.py`, `shop/storage.py` and `SqliteOrderStore`. The package is layered cleanly: the API translates payloads, the business rules validate orders, and persistence stays behind one class. There are no circular imports. No findings.

No files were modified; this review only reports.
