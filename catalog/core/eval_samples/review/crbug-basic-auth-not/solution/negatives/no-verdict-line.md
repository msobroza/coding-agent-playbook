**Correctness**

- `src/auth.py:16` - important - `!` is not a Python operator; the file raises SyntaxError, so use `not hmac.compare_digest(...)`.
