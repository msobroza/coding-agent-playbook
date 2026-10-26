**Correctness**

- `src/service.py:37` - important - `isinstance(x, typing.TextIO)` is False for objects from `open()`, so file logs are never closed; use `io.IOBase`.
