**Security**

- `src/auth.py:16` - `hmac.compare_digest` compares in constant time, so the check no longer leaks timing. Good change.

approve
