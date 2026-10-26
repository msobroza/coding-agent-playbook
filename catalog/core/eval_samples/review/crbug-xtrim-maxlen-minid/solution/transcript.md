**Correctness**

- `src/streams.py:35` - important - `maxlen` and `minid` are two strategies of which XTRIM takes exactly one, but nothing enforces it: `xtrim("events", maxlen=10, minid="1-0")` sends `XTRIM events MAXLEN MINID ~ 10 1-0`, and `xtrim("events")` sends `XTRIM events ~`. Both reach the server as invalid commands. Raise a `DataError` (or `ValueError`) when both or neither are given, then build the pieces for the one strategy.

**Readability**

- `src/streams.py:32` - nit - the docstring could say that `limit` only applies with `approximate=True`, as the server rejects LIMIT with an exact trim.

Findings: 1 important, 1 nit, 0 pre-existing

request changes
