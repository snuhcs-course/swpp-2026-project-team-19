# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-05, PR #5); ChatGPT (Haeul Yang, 2026-10-06, PR #11). Reviewed by Jinwoo Park and Haeul Yang.
"""Input, output and catalog access types for product matching.

These are plain dataclasses so matching does not depend on SQLAlchemy models.
`CatalogLookup` is implemented by `InMemoryCatalog` (seed JSON, tests and evaluation)
and `DbCatalog` (catalog tables, menu import processing).
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Literal, Protocol
from uuid import UUID

ResolutionStatus = Literal["exact_match", "ambiguous", "unmatched"]
MatchMethod = Literal["alias", "embedding", "llm"]


@dataclass(frozen=True)
class ExtractedProduct:
    """Product fields the AI extracted from one menu line (extracted_items)."""

    product_name: str | None = None
    brand_name: str | None = None
    age_years: int | None = None
    edition_name: str | None = None
    abv: Decimal | None = None


@dataclass(frozen=True)
class ProductInfo:
    """Catalog product attributes used for conflict checks."""

    product_id: UUID
    display_name: str
    age_years: int | None = None
    edition_name: str | None = None


@dataclass(frozen=True)
class Candidate:
    """One row of resolution_candidates, before it is stored."""

    product_id: UUID
    rank: int
    score: float
    method: MatchMethod
    evidence: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class ResolutionResult:
    status: ResolutionStatus
    candidates: tuple[Candidate, ...] = ()
    proposed_product_id: UUID | None = None


class CatalogLookup(Protocol):
    """Read-only access to active catalog products and their aliases."""

    def find_product_ids_by_alias(self, normalized_alias: str) -> list[UUID]:
        """Return distinct active product ids whose normalized alias equals the argument."""
        ...

    def get_product(self, product_id: UUID) -> ProductInfo | None:
        """Return product attributes, or None if the product does not exist or is inactive."""
        ...

    def get_normalized_aliases(self, product_id: UUID) -> list[str]:
        """Return every normalized alias of the product."""
        ...
