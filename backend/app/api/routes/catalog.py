from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.security import require_operator
from app.db.session import get_session
from app.schemas.catalog import CatalogBrandsResponse, CatalogProductsResponse
from app.schemas.errors import error_responses
from app.services.catalog_search import search_brands, search_products

router = APIRouter(prefix="/api/catalog", tags=["catalog"])

_MATCHING = (
    "The query is normalized with the same function as catalog aliases. Exact alias matches come first, "
    "then aliases containing the query, the shortest matching alias first; ties by name. "
    "`matchedAlias` is the closest alias of each result."
)
_COMMON_ERRORS = (
    (401, "`UNAUTHENTICATED`: missing, invalid or expired token."),
    (403, "`FORBIDDEN`: the caller is not an operator."),
    (
        422,
        "`VALIDATION_FAILED`: `query` `MISSING`, `BLANK`, `STRING_TOO_LONG` (over 100 characters) or "
        "`NOT_SEARCHABLE` (nothing left after normalization); `limit` out of range.",
    ),
)


@router.get(
    "/brands",
    response_model=CatalogBrandsResponse,
    summary="Find brands for the menu review screen",
    description=(
        "Operator only. Used to pick an existing brand when creating a product during review.\n\n"
        f"{_MATCHING} Several brands can share an alias; all are returned."
    ),
    responses=error_responses(*_COMMON_ERRORS),
)
def read_catalog_brands(
    query: Annotated[str, Query(description="Brand name or alias; 1-100 characters after trimming")],
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum number of brands")] = 20,
    session: Session = Depends(get_session),
    _operator: dict[str, Any] = Depends(require_operator),
) -> CatalogBrandsResponse:
    return search_brands(session, query, limit=limit)


@router.get(
    "/products",
    response_model=CatalogProductsResponse,
    summary="Find products for the menu review screen",
    description=(
        "Operator only. Used to pick a product that is not among the candidates, and to check for an "
        "existing product before creating one.\n\n"
        f"{_MATCHING} Unlike customer search, non-searchable aliases also match and inactive products are "
        "included by default."
    ),
    responses=error_responses(*_COMMON_ERRORS),
)
def read_catalog_products(
    query: Annotated[str, Query(description="Product name or alias; 1-100 characters after trimming")],
    brand_id: Annotated[UUID | None, Query(alias="brandId", description="Only products of this brand")] = None,
    include_inactive: Annotated[
        bool, Query(alias="includeInactive", description="Include inactive products")
    ] = True,
    limit: Annotated[int, Query(ge=1, le=50, description="Maximum number of products")] = 20,
    session: Session = Depends(get_session),
    _operator: dict[str, Any] = Depends(require_operator),
) -> CatalogProductsResponse:
    return search_products(session, query, brand_id=brand_id, include_inactive=include_inactive, limit=limit)
