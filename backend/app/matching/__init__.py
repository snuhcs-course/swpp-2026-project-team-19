# AI-generated with Claude Code/Claude Opus 5.5 (Jinwoo Park, 2026-10-05, PR #5). Reviewed by Jinwoo Park.
"""Matching extracted menu lines to catalog products."""

from app.matching.resolve import resolve_product
from app.matching.types import (
    Candidate,
    CatalogLookup,
    ExtractedProduct,
    ProductInfo,
    ResolutionResult,
)

__all__ = [
    "Candidate",
    "CatalogLookup",
    "ExtractedProduct",
    "ProductInfo",
    "ResolutionResult",
    "resolve_product",
]
