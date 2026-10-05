"""Builders for database test data. Each helper flushes so generated ids are available."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.normalize import normalize
from app.models import (
    Bar,
    BarMenuItem,
    BarStatus,
    Brand,
    BrandAlias,
    MenuBoard,
    MenuBoardEntry,
    MenuEntryOption,
    Product,
    ProductAlias,
)


def make_bar(
    session: Session,
    name: str = "Test Bar",
    *,
    latitude: str = "37.478000",
    longitude: str = "126.951000",
    status: BarStatus = BarStatus.ACTIVE,
) -> Bar:
    bar = Bar(
        name=name,
        address=f"{name} address",
        latitude=Decimal(latitude),
        longitude=Decimal(longitude),
        phone="02-000-0000",
        status=status,
    )
    session.add(bar)
    session.flush()
    return bar


def make_brand(session: Session, name: str, aliases: tuple[str, ...] = ()) -> Brand:
    brand = Brand(canonical_name=name)
    session.add(brand)
    session.flush()
    for text in {name, *aliases}:
        session.add(BrandAlias(brand_id=brand.id, alias_text=text, normalized_alias=normalize(text)))
    session.flush()
    return brand


def make_product(
    session: Session,
    brand: Brand,
    display_name: str,
    aliases: tuple[str, ...] = (),
    *,
    age_years: int | None = None,
    edition_name: str | None = None,
    is_active: bool = True,
    unsearchable_aliases: tuple[str, ...] = (),
) -> Product:
    product = Product(
        brand_id=brand.id,
        display_name=display_name,
        age_years=age_years,
        edition_name=edition_name,
        is_active=is_active,
    )
    session.add(product)
    session.flush()
    for text, searchable in [(display_name, True), *((a, True) for a in aliases), *((a, False) for a in unsearchable_aliases)]:
        session.add(
            ProductAlias(
                product_id=product.id,
                alias_text=text,
                normalized_alias=normalize(text),
                is_searchable=searchable,
            )
        )
    session.flush()
    return product


def publish_menu(
    session: Session,
    bar: Bar,
    entries: list[tuple[Product, str, list[tuple[str | None, int | None, int]]]],
    *,
    published_at: datetime | None = None,
) -> MenuBoard:
    """entries: (product, menu display name, [(option label, pour ml, price krw), ...]) in menu order."""
    board = MenuBoard(bar_id=bar.id, published_at=published_at or datetime.now(timezone.utc))
    session.add(board)
    session.flush()
    for entry_order, (product, display_name, options) in enumerate(entries, start=1):
        item = BarMenuItem(bar_id=bar.id, product_id=product.id)
        session.add(item)
        session.flush()
        entry = MenuBoardEntry(
            menu_board_id=board.id, bar_menu_item_id=item.id, display_name=display_name, sort_order=entry_order
        )
        session.add(entry)
        session.flush()
        for option_order, (label, pour_ml, price_krw) in enumerate(options, start=1):
            session.add(
                MenuEntryOption(
                    menu_board_entry_id=entry.id,
                    option_label=label,
                    pour_ml=pour_ml,
                    price_krw=price_krw,
                    sort_order=option_order,
                )
            )
    session.flush()
    return board
