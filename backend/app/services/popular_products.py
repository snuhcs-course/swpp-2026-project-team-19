"""The popular whiskies on the customer home screen (API spec 3.17), ranked by the daily search
counts of customer search (3.10.6)."""

from datetime import date

from sqlalchemy import case, distinct, func, select
from sqlalchemy.orm import Session, joinedload

from app.models import BarMenuItem, MenuBoard, Product, ProductSearchCount
from app.schemas.search import PopularProductItem, PopularProductsResponse
from app.services.search import on_sale
from app.services.search_counts import first_kept_date

DEFAULT_LIMIT = 10
MAX_LIMIT = 20
RANKING_DAYS = 30  # Seoul dates, today included
MIN_POPULAR_SEARCHES = 3  # fewer searches only fill the list after the popular products


def popular_products(session: Session, today: date, limit: int = DEFAULT_LIMIT) -> PopularProductsResponse:
    """Active products sold by at least one bar: those searched at least 3 times in the last 30 days
    first, most searched first, then the rest by barCount; ties by barCount, name, id (spec 3.17.2).
    Every source counts."""
    bar_counts = (
        on_sale(select(BarMenuItem.product_id, func.count(distinct(MenuBoard.bar_id)).label("bar_count")))
        .group_by(BarMenuItem.product_id)
        .subquery()
    )
    searches = (
        select(ProductSearchCount.product_id, func.sum(ProductSearchCount.search_count).label("searches"))
        .where(ProductSearchCount.search_date.between(first_kept_date(today, RANKING_DAYS), today))
        .group_by(ProductSearchCount.product_id)
        .subquery()
    )
    # 0 for the fallback products, so they are ordered by barCount alone.
    popular_searches = case(
        (searches.c.searches >= MIN_POPULAR_SEARCHES, searches.c.searches), else_=0
    )
    query = (
        select(Product, bar_counts.c.bar_count)
        .join(bar_counts, bar_counts.c.product_id == Product.id)
        .outerjoin(searches, searches.c.product_id == Product.id)
        .where(Product.is_active)
        .options(joinedload(Product.brand))
        .order_by(popular_searches.desc(), bar_counts.c.bar_count.desc(), Product.display_name, Product.id)
        .limit(limit)
    )
    return PopularProductsResponse(
        items=[
            PopularProductItem(
                productId=product.id,
                displayName=product.display_name,
                brandName=product.brand.canonical_name,
                ageYears=product.age_years,
                editionName=product.edition_name,
                barCount=bar_count,
            )
            for product, bar_count in session.execute(query).all()
        ]
    )
