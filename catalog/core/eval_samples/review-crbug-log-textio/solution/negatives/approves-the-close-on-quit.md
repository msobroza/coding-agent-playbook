**Correctness**

- `src/service.py:37` - files are closed through `close()` and descriptors through `os.close`, and PIPE is left alone. This fixes the dangling log.

approve
