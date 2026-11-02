"""Embedding candidate step (I3-P40): the last matching step, after the rules and the LLM layer.

    step = get_embedding_step()          # None while EMBEDDING_ENABLED is not true
    results = step.apply(session, names, results)

Policy "unmatched_k5+rerank_only" of the P24 decision (ai/docs/p24_embedding_decision.md),
which the offline harness (ai/eval/p24_embedding_compare.py, `apply_policy`) evaluated:

  exact_match / multi                      unchanged
  ambiguous with a confirmRecommended      unchanged
  other ambiguous lines                    the same candidates, reordered by embedding similarity
                                           (candidates the index does not rank keep their order,
                                           after the others); nothing is added
  unmatched                                up to MAX_NEW products with similarity >= the floor
                                           (EMBEDDING_MIN_SIMILARITY), method "embedding"; the line
                                           becomes ambiguous. Below the floor it stays unmatched.

The step never confirms a line and never sets confirmRecommended, so it cannot change what the
rules or the LLM layer confirmed.

What is embedded: every active product's display name and the text of each of its aliases,
including unsearchable ones, i.e. what the rule matcher (`DbCatalog`) matches against. A product
scores the best similarity over its texts. The query is the line's extracted product name as
read, as in the harness.

The index lives in this process (no table, no migration). It is built on first use and built
again when `catalog_version` changes, which a review that creates products or aliases does. Menu
imports run in worker threads (background tasks, start-up recovery), so the check and the
rebuild happen under a lock; a built index is never changed, only replaced.
"""

import logging
import threading
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from functools import lru_cache
from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.adapters.embedding import EmbeddingProvider, load_embedding_settings, make_embedding_provider
from app.matching.types import Candidate, ResolutionResult
from app.models import Product, ProductAlias

logger = logging.getLogger(__name__)

CONFIRMED = ("exact_match", "multi")
MAX_NEW = 5  # embedding candidates on an unmatched line ("k5")
TOP_N = 10  # products ranked per line (the harness's TOP_N); reordering uses this ranking


@dataclass(frozen=True)
class Ranked:
    product_id: UUID
    similarity: float
    text: str  # the display name or alias text that gave the product its similarity


def rank_products(scores: Sequence[float], entries: Sequence[tuple[str, UUID]], top_n: int = TOP_N) -> list[Ranked]:
    """Products by their best similarity over their texts, best first; ties by text so the order is stable."""
    best: dict[UUID, tuple[float, str]] = {}
    for score, (text, product_id) in zip(scores, entries):
        if product_id not in best or score > best[product_id][0]:
            best[product_id] = (score, text)
    ranked = sorted(best.items(), key=lambda item: (-item[1][0], item[1][1]))
    return [Ranked(product_id, score, text) for product_id, (score, text) in ranked[:top_n]]


def apply_policy(base: ResolutionResult, ranking: Sequence[Ranked], *, min_similarity: float, model_id: str) -> ResolutionResult:
    """The rules (and LLM) result with the embedding step applied; see the module docstring."""
    if base.status in CONFIRMED:
        return base
    if base.status == "unmatched":
        picks = [r for r in ranking if r.similarity >= min_similarity][:MAX_NEW]
        if not picks:
            return base
        candidates = tuple(
            Candidate(
                product_id=r.product_id,
                rank=rank,
                score=round(r.similarity, 4),
                method="embedding",
                evidence={
                    "rule": "embedding",
                    "embeddingSimilarity": round(r.similarity, 3),
                    "matchedText": r.text,
                    "model": model_id,
                },
            )
            for rank, r in enumerate(picks, start=1)
        )
        return ResolutionResult(status="ambiguous", candidates=candidates, proposed_product_id=candidates[0].product_id)
    if any(c.evidence.get("confirmRecommended") for c in base.candidates):
        return base
    order = {r.product_id: position for position, r in enumerate(ranking)}
    reordered = sorted(base.candidates, key=lambda c: order.get(c.product_id, len(order)))  # stable
    if [c.product_id for c in reordered] == [c.product_id for c in base.candidates]:
        return base
    similarity = {r.product_id: round(r.similarity, 3) for r in ranking}
    candidates = tuple(
        replace(c, rank=rank, evidence=_reranked(c.evidence, similarity.get(c.product_id)))
        for rank, c in enumerate(reordered, start=1)
    )
    return replace(base, candidates=candidates, proposed_product_id=candidates[0].product_id)


def _reranked(evidence: dict[str, Any], similarity: float | None) -> dict[str, Any]:
    extra: dict[str, Any] = {"rerankedBy": "embedding"}
    if similarity is not None:
        extra["embeddingSimilarity"] = similarity
    return {**evidence, **extra}


def catalog_version(session: Session) -> tuple[Any, ...]:
    """Changes when an active product or an alias of one is added, removed, deactivated, or a product
    is updated (`products.updated_at`). One query; compared before every use of the index."""
    active = Product.is_active
    alias_rows = select(ProductAlias).join(Product, Product.id == ProductAlias.product_id).where(active).subquery()
    query = select(
        select(func.count()).where(active).select_from(Product).scalar_subquery(),
        select(func.max(Product.updated_at)).where(active).scalar_subquery(),
        select(func.count()).select_from(alias_rows).scalar_subquery(),
        select(func.max(alias_rows.c.created_at)).scalar_subquery(),
    )
    return tuple(session.execute(query).one())


def catalog_entries(session: Session) -> list[tuple[str, UUID]]:
    """(text, product id) for every active product: its display name, then its alias texts, each text once."""
    entries: dict[tuple[str, UUID], None] = {}
    for product_id, name in session.execute(
        select(Product.id, Product.display_name).where(Product.is_active).order_by(Product.id)
    ):
        entries[(name, product_id)] = None
    query = (
        select(ProductAlias.alias_text, ProductAlias.product_id)
        .join(Product, Product.id == ProductAlias.product_id)
        .where(Product.is_active)
        .order_by(ProductAlias.product_id, ProductAlias.alias_text)
    )
    for text, product_id in session.execute(query):
        entries[(text, product_id)] = None
    return list(entries)


class EmbeddingIndex:
    """The embedded catalog texts of one catalog version. Never changed after it is built."""

    def __init__(self, provider: EmbeddingProvider, entries: list[tuple[str, UUID]], version: tuple[Any, ...]) -> None:
        self.version = version
        self.entries = entries
        self._texts = provider.build_index([text for text, _ in entries])

    def search(self, names: Sequence[str], top_n: int = TOP_N) -> list[list[Ranked]]:
        rows = self._texts.similarities(names)
        return [rank_products(row, self.entries, top_n) for row in rows]


class EmbeddingStep:
    """The configured step: the provider, the floor, and the current index of this process."""

    def __init__(self, provider: EmbeddingProvider, min_similarity: float) -> None:
        self.provider = provider
        self.min_similarity = min_similarity
        self._index: EmbeddingIndex | None = None
        self._lock = threading.Lock()

    def index(self, session: Session) -> EmbeddingIndex:
        """The index for the catalog the session sees, built again if the catalog changed since."""
        with self._lock:
            # The version is read before the texts, so an index is never newer than its version says;
            # a catalog change between the two reads only causes one more rebuild.
            version = catalog_version(session)
            if self._index is None or self._index.version != version:
                started = time.perf_counter()
                self._index = EmbeddingIndex(self.provider, catalog_entries(session), version)
                logger.info(
                    "Embedding index (%s) built: %d texts in %.2f s",
                    self.provider.model_id, len(self._index.entries), time.perf_counter() - started,
                )
            return self._index

    def apply(
        self, session: Session, names: Mapping[UUID, str | None], results: Mapping[UUID, ResolutionResult]
    ) -> dict[UUID, ResolutionResult]:
        """Apply the policy to `results` (item id -> result), searching each distinct line name once.
        `names` gives each item's extracted product name; a line without one is left as it is.
        Reads the catalog, writes nothing, and raises on failure (the caller keeps `results`)."""
        targets = [item_id for item_id, result in results.items() if _is_target(result) and names.get(item_id)]
        if not targets:
            return dict(results)
        distinct = list(dict.fromkeys(names[item_id] for item_id in targets))
        index = self.index(session)
        rankings = dict(zip(distinct, index.search(distinct)))
        resolved = dict(results)
        for item_id in targets:
            resolved[item_id] = apply_policy(
                results[item_id], rankings[names[item_id]],
                min_similarity=self.min_similarity, model_id=self.provider.model_id,
            )
        return resolved


def _is_target(result: ResolutionResult) -> bool:
    if result.status == "unmatched":
        return True
    return result.status == "ambiguous" and not any(c.evidence.get("confirmRecommended") for c in result.candidates)


def summarize(before: Mapping[UUID, ResolutionResult], after: Mapping[UUID, ResolutionResult]) -> dict[str, int]:
    """Counts for the log: unmatched lines that got candidates or stayed unmatched, and reordered lines."""
    counts = {"filled": 0, "still_unmatched": 0, "reordered": 0}
    for item_id, old in before.items():
        new = after[item_id]
        if old.status == "unmatched":
            counts["filled" if new is not old else "still_unmatched"] += 1
        elif new is not old:
            counts["reordered"] += 1
    return counts


@lru_cache(maxsize=1)
def get_embedding_step() -> EmbeddingStep | None:
    """The embedding step of this process, or None when it is off (the default).

    One per process because it holds the index. EMBEDDING_ENABLED=true turns it on, EMBEDDING_MODEL
    picks the provider (default tfidf) and EMBEDDING_MIN_SIMILARITY the floor (default per model).
    Invalid settings raise RuntimeError, which stops the server at start-up (app.main).
    """
    settings = load_embedding_settings()
    if not settings.enabled:
        return None
    return EmbeddingStep(make_embedding_provider(settings), settings.min_similarity)

