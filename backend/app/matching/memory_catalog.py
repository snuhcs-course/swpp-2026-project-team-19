"""In-memory `CatalogLookup` loaded from the seed JSON, for tests and offline evaluation."""

import json
from collections.abc import Collection, Iterable
from pathlib import Path
from uuid import UUID

from app.core.normalize import normalize
from app.matching.types import ProductInfo


class InMemoryCatalog:
    def __init__(self, products: Iterable[ProductInfo], aliases: Iterable[tuple[UUID, str]]) -> None:
        """`aliases` holds (product_id, alias_text) pairs; normalized aliases are computed here."""
        self._products = {product.product_id: product for product in products}
        # dict keys keep insertion order and drop aliases that normalize to the same value
        # within one product, like the (product_id, normalized_alias) unique constraint.
        self._aliases_by_product: dict[UUID, dict[str, None]] = {pid: {} for pid in self._products}
        self._products_by_alias: dict[str, dict[UUID, None]] = {}
        for product_id, alias_text in aliases:
            if product_id not in self._products:
                raise ValueError(f"Alias {alias_text!r} refers to unknown product {product_id}")
            normalized = normalize(alias_text)
            if not normalized:
                continue
            self._aliases_by_product[product_id][normalized] = None
            self._products_by_alias.setdefault(normalized, {})[product_id] = None

    @classmethod
    def from_seed(cls, path: str | Path, exclude_sources: Collection[str] = ()) -> "InMemoryCatalog":
        """Load `catalog_v1_draft.json`. Inactive products (`is_active: false`) are skipped.

        Aliases whose `sources` all appear in `exclude_sources` are dropped, e.g. to
        evaluate without the menu spellings collected from the evaluation bars.
        """
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        products = []
        aliases = []
        for row in data["products"]:
            if not row.get("is_active", True):
                continue
            product_id = UUID(row["id"])
            products.append(
                ProductInfo(
                    product_id=product_id,
                    display_name=row["display_name"],
                    age_years=row.get("age_years"),
                    edition_name=row.get("edition_name"),
                )
            )
            aliases.extend(
                (product_id, alias["alias_text"])
                for alias in row["aliases"]
                if not exclude_sources or not set(alias.get("sources", [])) <= set(exclude_sources)
            )
        return cls(products, aliases)

    def find_product_ids_by_alias(self, normalized_alias: str) -> list[UUID]:
        return list(self._products_by_alias.get(normalized_alias, {}))

    def get_product(self, product_id: UUID) -> ProductInfo | None:
        return self._products.get(product_id)

    def get_normalized_aliases(self, product_id: UUID) -> list[str]:
        return list(self._aliases_by_product.get(product_id, {}))

    def shared_aliases(self) -> dict[str, list[UUID]]:
        """Normalized aliases that point to more than one product."""
        return {
            alias: list(product_ids)
            for alias, product_ids in self._products_by_alias.items()
            if len(product_ids) > 1
        }
