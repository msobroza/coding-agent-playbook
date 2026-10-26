**Correctness**

- `src/netrc_auth.py:17` - important - the NETRC path is still joined under the home directory: `os.path.expanduser(f"~/{name}")` turns `NETRC=/etc/ci/netrc` into `/home/alice//etc/ci/netrc`, which does not exist, so `get_netrc_auth()` returns `None` for any absolute or `~`-relative NETRC value. Only the default `NETRC_FILES` names need the `~/` prefix; a NETRC value should go through `os.path.expanduser(netrc_file)` alone.

**Tests**

- `tests/test_netrc_auth.py:29` - nit - the new test uses a file name relative to `$HOME`, the one case the bug does not hit; an absolute path in `NETRC` would have caught it.

Findings: 1 important, 1 nit, 0 pre-existing

request changes
