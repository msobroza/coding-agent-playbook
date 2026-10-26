**Correctness**

- `src/auth.py:16` - important - `!hmac.compare_digest(...)` is not Python: there is no `!` operator, so the module raises `SyntaxError` on import and `is_authorized` cannot be called at all (`pytest` fails while collecting `tests/test_auth.py`). Use `not hmac.compare_digest(given.username, expected.username) or not hmac.compare_digest(given.password, expected.password)`.

**Failure modes**

- `src/auth.py:16` - nit - `hmac.compare_digest` raises `TypeError` for `str` arguments with non-ASCII characters; encoding both sides to bytes first keeps a password like `pässword` from turning a failed login into an error.

Findings: 1 important, 1 nit, 0 pre-existing

request changes
