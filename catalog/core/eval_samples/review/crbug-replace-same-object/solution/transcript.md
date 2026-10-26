**Correctness**

- `src/scene.py:37` - important - when `new_mobject is old_mobject`, the new deduplication removes the object before the search: `scene.add(a); scene.replace(a, a)` now raises `ValueError("Could not find ...")` and leaves `a` off the screen. Replacing an object with itself happens easily when a caller does not notice two names point to the same object. Skip the removal when `new_m is old_m`, or remove the duplicate only after the replacement succeeded.

Findings: 1 important, 0 nit, 0 pre-existing

request changes
