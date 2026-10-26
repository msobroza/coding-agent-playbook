**Correctness**

- `src/scene.py:37` - important - `scene.replace(a, a)` removes `a` before the search, so it raises ValueError and `a` disappears from the scene.
