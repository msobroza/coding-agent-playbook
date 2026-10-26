**Correctness**

- `src/forms.py:43` - important - an explicit `method=None` now raises AttributeError on `.upper()`; it used to mean GET.
