**Correctness**

- `src/streams.py:35` - important - maxlen and minid can both be passed, which builds `XTRIM s MAXLEN MINID ~ 10 1-0`; raise a DataError instead.
