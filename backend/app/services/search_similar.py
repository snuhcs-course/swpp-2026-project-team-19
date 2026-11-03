"""Similar products, the fifth step of customer search (API spec 3.10.1), off unless SEARCH_SIMILAR_ENABLED=true.

    finder = get_similar_products()     # None while SEARCH_SIMILAR_ENABLED is not true
    products = finder.find(session, query)

It runs only for a `query` search that brand, alias_exact and partial left with nothing, so it
never changes a result those steps give. It ranks the active products by the character TF-IDF
similarity of the query to each product's display name and searchable aliases (the aliases the
other steps match against), with the provider and in-memory index of the menu matching embedding
step (I3-P40, `app.matching.embedding`): a product scores its best text, products at or above
SEARCH_SIMILAR_MIN_SIMILARITY are kept, best first, at most `SIMILAR_LIMIT`.

The query is compared as typed (trimmed), not normalized, like P40 compares the menu line as read:
the TF-IDF lowercases and drops spaces itself, and the 0.38 floor was measured that way (P24).

It is deterministic and in process: no model file, no model call, nothing stored. The index is
built on the first search that reaches this step and again when the catalog changes; each search
costs one catalog version query and the similarity computation.
"""

import logging
import math
import os
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.adapters.embedding import DEFAULT_MIN_SIMILARITY, CharTfidfProvider, EmbeddingProvider
from app.matching.embedding import CatalogIndexCache
from app.models import Product

logger = logging.getLogger(__name__)

SIMILAR_LIMIT = 5


@dataclass(frozen=True)
class SimilarSearchSettings:
    enabled: bool = False
    min_similarity: float = DEFAULT_MIN_SIMILARITY["tfidf"]


def load_similar_search_settings() -> SimilarSearchSettings:
    """Read SEARCH_SIMILAR_ENABLED and SEARCH_SIMILAR_MIN_SIMILARITY; raise RuntimeError for an invalid
    value. Checked at start-up even while the step is off, like the EMBEDDING_* settings."""
    enabled = (os.getenv("SEARCH_SIMILAR_ENABLED") or "false").lower()
    if enabled not in ("true", "false"):
        raise RuntimeError(f"SEARCH_SIMILAR_ENABLED must be true or false, got {enabled!r}")
    raw = os.getenv("SEARCH_SIMILAR_MIN_SIMILARITY")
    min_similarity = DEFAULT_MIN_SIMILARITY["tfidf"]
    if raw:
        try:
            min_similarity = float(raw)
        except ValueError:
            min_similarity = math.nan
        if not 0 <= min_similarity <= 1:  # also rejects nan
            raise RuntimeError(f"SEARCH_SIMILAR_MIN_SIMILARITY must be a number from 0 to 1, got {raw!r}")
    return SimilarSearchSettings(enabled=enabled == "true", min_similarity=min_similarity)


class SimilarProducts:
    """The configured step: the floor and the index of display names and searchable aliases."""

    def __init__(self, provider: EmbeddingProvider, min_similarity: float) -> None:
        self.min_similarity = min_similarity
        self._cache = CatalogIndexCache(provider, searchable_only=True)

    def find(self, session: Session, query: str) -> list[Product]:
        """Up to SIMILAR_LIMIT active products (brand loaded) at or above the floor, most similar
        first, ties by display name. Raises on failure."""
        similarities = self._cache.get(session).product_similarities(query)
        scores = sorted((s for s in similarities.values() if s >= self.min_similarity), reverse=True)
        if not scores:
            return []
        # Load only the products that can make the cut; all of those tied with the last one, for the name order.
        cutoff = scores[min(len(scores), SIMILAR_LIMIT) - 1]
        passed = {product_id: s for product_id, s in similarities.items() if s >= cutoff}
        products = session.scalars(
            select(Product).where(Product.id.in_(passed), Product.is_active).options(joinedload(Product.brand))
        )
        ranked = sorted(products, key=lambda p: (-passed[p.id], p.display_name, str(p.id)))
        return ranked[:SIMILAR_LIMIT]


@lru_cache(maxsize=1)
def get_similar_products() -> SimilarProducts | None:
    """The similar-products step of this process, or None when it is off (the default).

    One per process because it holds the index. Invalid settings raise RuntimeError, which stops
    the server at start-up (app.main).
    """
    settings = load_similar_search_settings()
    if not settings.enabled:
        return None
    return SimilarProducts(CharTfidfProvider(), settings.min_similarity)
