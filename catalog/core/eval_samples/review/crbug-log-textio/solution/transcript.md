**Correctness**

- `src/service.py:37` - important - `isinstance(self.log_output, TextIO)` is never true for a real file: `typing.TextIO` is a typing stand-in, not a base class of `io.TextIOWrapper` (a path opened with `"a+"`) or of the `io.BufferedWriter` from the default `open(os.devnull, "wb")`. So `stop()` closes nothing but raw descriptors, and every file log, the default one included, is still left open (a `ResourceWarning` per driver). Test `isinstance(self.log_output, io.IOBase)` instead.

**Tests**

- `tests/test_service.py:22` - nit - only the file-descriptor branch is tested; a test with a path or the default log would have shown the file left open.

Findings: 1 important, 1 nit, 0 pre-existing

request changes
