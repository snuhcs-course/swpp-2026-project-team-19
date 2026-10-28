"""Builders for database test data. Each helper flushes so generated ids are available."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.core.normalize import normalize
from app.models import (
    Bar,
    BarMenuItem,
    BarOwner,
    BarOwnerApplication,
    BarStatus,
    Brand,
    BrandAlias,
    BusinessVerificationResult,
    MenuBoard,
    MenuBoardEntry,
    MenuEntryOption,
    OwnerApplicationStatus,
    OwnerApplicationType,
    Product,
    ProductAlias,
    User,
    UserType,
)

# Passes the NTS check digit (app/core/business_number.py).
BUSINESS_NUMBER = "1234567891"


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


def make_user(
    session: Session,
    subject: str = "user-subject",
    *,
    user_type: UserType = UserType.CUSTOMER,
    email: str | None = None,
    display_name: str | None = None,
) -> User:
    user = User(auth_subject=subject, user_type=user_type, email=email, display_name=display_name)
    session.add(user)
    session.flush()
    return user


def make_application(
    session: Session,
    applicant: User,
    bar: Bar | None = None,
    *,
    application_type: OwnerApplicationType | None = None,
    status: OwnerApplicationStatus = OwnerApplicationStatus.PENDING,
    business_registration_number: str = BUSINESS_NUMBER,
    reviewer: User | None = None,
) -> BarOwnerApplication:
    """An existing_bar application for `bar`, or a new_bar one without it. An approved new_bar
    application passes `bar` (the bar its approval created) and `application_type`. A reviewed
    status needs `reviewer`."""
    if application_type is None:
        application_type = OwnerApplicationType.NEW_BAR if bar is None else OwnerApplicationType.EXISTING_BAR
    reviewed = status in (OwnerApplicationStatus.APPROVED, OwnerApplicationStatus.REJECTED)
    new_bar = application_type == OwnerApplicationType.NEW_BAR
    application = BarOwnerApplication(
        applicant_user_id=applicant.id,
        application_type=application_type,
        bar_id=bar.id if bar is not None else None,
        proposed_bar_name="New Bar" if new_bar else None,
        proposed_address="New Bar address" if new_bar else None,
        business_registration_number=business_registration_number,
        representative_name="김사장",
        opening_date=date(2020, 3, 2),
        business_verification_result=BusinessVerificationResult.UNAVAILABLE,
        business_checked_at=datetime(2026, 10, 14, 3, tzinfo=timezone.utc),
        contact_phone="010-1234-5678",
        status=status,
        reviewed_by_user_id=reviewer.id if reviewed and reviewer is not None else None,
        # Set even without a reviewer, so a test can break the review rule on purpose.
        reviewed_at=datetime(2026, 10, 14, 5, tzinfo=timezone.utc) if reviewed else None,
        rejection_reason="확인할 수 없습니다." if status == OwnerApplicationStatus.REJECTED else None,
    )
    session.add(application)
    session.flush()
    return application


def make_owner(session: Session, user: User, bar: Bar, reviewer: User) -> BarOwner:
    """`user` as the current owner of `bar`, through an approved existing_bar application."""
    application = make_application(session, user, bar, status=OwnerApplicationStatus.APPROVED, reviewer=reviewer)
    owner = BarOwner(bar_id=bar.id, user_id=user.id, application_id=application.id)
    session.add(owner)
    session.flush()
    return owner
