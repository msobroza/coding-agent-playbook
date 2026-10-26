**Correctness**

- `src/netrc_auth.py:17` - important - `expanduser(f"~/{name}")` also prefixes the NETRC value, so `NETRC=/etc/ci/netrc` becomes `~//etc/ci/netrc` and is never found.
