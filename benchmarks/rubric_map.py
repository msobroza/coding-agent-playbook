"""A 2-D map of the review samples' rubric criteria, from their text embeddings.

Criteria that ask for the same thing ("names the bug", "does not invent bugs",
"its verdict is request changes") land close together, so coloring each point
by how often a reviewer met it shows *which kind* of criterion fails.

``build`` embeds every criterion with OpenAI's embeddings API (``OPENAI_API_KEY``
from ``.env``), projects to 2-D with t-SNE and caches the points in
``rubric_map.json``; ``load`` reads that cache, so plotting needs no key::

    uv run --no-project --with numpy,scikit-learn python benchmarks/report.py --embed
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:
    from pathlib import Path

EMBED_MODEL: Final = "text-embedding-3-small"
EMBED_URL: Final = "https://api.openai.com/v1/embeddings"
EMBED_TIMEOUT_S: Final = 60.0
EMBED_ATTEMPTS: Final = 3
#: Fixed so the committed map is reproducible; t-SNE is stochastic otherwise.
TSNE_SEED: Final = 7


@dataclass(frozen=True)
class MapPoint:
    """One rubric criterion placed on the map."""

    sample: str
    criterion: str
    x: float
    y: float


def embed_texts(texts: list[str], api_key: str) -> list[list[float]]:
    """One embedding vector per text, retrying transient failures with backoff.

    Example::

        embed_texts(["The review names the bug."], key)[0][:3]  # [0.01, -0.02, ...]
    """
    body = json.dumps({"model": EMBED_MODEL, "input": texts}).encode()
    request = urllib.request.Request(
        EMBED_URL,
        data=body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    for attempt in range(EMBED_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=EMBED_TIMEOUT_S) as response:
                payload: dict[str, Any] = json.load(response)
            return [item["embedding"] for item in sorted(payload["data"], key=lambda d: d["index"])]
        except (urllib.error.URLError, TimeoutError) as exc:
            if attempt == EMBED_ATTEMPTS - 1:
                raise RuntimeError(f"embeddings API failed {EMBED_ATTEMPTS} times: {exc}") from exc
            time.sleep(2**attempt)
    raise AssertionError("unreachable")


def project_2d(vectors: list[list[float]]) -> list[tuple[float, float]]:
    """t-SNE on cosine distance; perplexity scaled to the few dozen criteria."""
    import numpy as np
    from sklearn.manifold import TSNE

    data = np.asarray(vectors)
    tsne = TSNE(
        n_components=2,
        perplexity=min(8.0, len(vectors) - 1.0),
        metric="cosine",
        init="pca",
        random_state=TSNE_SEED,
    )
    points = tsne.fit_transform(data)
    return [(float(x), float(y)) for x, y in points]


def build(criteria: list[tuple[str, str]], api_key: str, path: Path) -> list[MapPoint]:
    """Embed ``(sample, criterion)`` pairs, project them and cache the map at ``path``."""
    xy = project_2d(embed_texts([text for _, text in criteria], api_key))
    points = [MapPoint(s, c, x, y) for (s, c), (x, y) in zip(criteria, xy, strict=True)]
    payload = {
        "model": EMBED_MODEL,
        "projection": f"t-SNE seed {TSNE_SEED}",
        "points": [p.__dict__ for p in points],
    }
    path.write_text(json.dumps(payload, indent=1) + "\n", encoding="utf-8")
    return points


def load(path: Path) -> list[MapPoint]:
    """The cached map; build it first with ``report.py --embed``."""
    if not path.is_file():
        raise FileNotFoundError(f"no rubric map at {path}; run report.py --embed")
    return [MapPoint(**p) for p in json.loads(path.read_text(encoding="utf-8"))["points"]]
