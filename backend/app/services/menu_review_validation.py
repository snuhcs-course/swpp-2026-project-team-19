# AI-generated with ChatGPT (Haeul Yang, 2026-10-06, PR #12). Reviewed by Haeul Yang.
"""Checks on a review submission that need the import's rows (API spec 8.7). Reads only.

The request body's own shape is checked by the schema. This checks the decisions against
the import: every item and pending change decided exactly once, options belong to their
item, a published product has a priced option, selected products and brands exist, names
normalize to something, and applied changes point at items kept as products. All problems
are reported together as one 422.

State checks (status, reviewVersion, board changes) and duplicate checks for new catalog
entries happen in the apply step, inside its transaction.
"""

from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import validation_failed_fields
from app.core.normalize import normalize
from app.models import (
    Brand,
    ExtractedItem,
    ExtractedOption,
    ExtractionRun,
    MenuChangeDecision,
    MenuImage,
    MenuImport,
    MenuImportChange,
    Product,
)
from app.schemas.menu_review import (
    CreateProduct,
    ItemDecision,
    ProductAliasInput,
    ProductDecision,
    ReviewAndApplyRequest,
    SelectExistingProduct,
)


@dataclass(frozen=True)
class FinalOption:
    """An extracted option with the reviewer's corrections applied."""

    option: ExtractedOption
    label: str | None
    pour_ml: int | None
    price_krw: int | None


@dataclass(frozen=True)
class ReviewedItem:
    item: ExtractedItem
    decision: ItemDecision
    # Position in itemDecisions, for error paths.
    index: int
    # Every option of a product decision in display order; empty otherwise.
    options: tuple[FinalOption, ...] = ()

    @property
    def is_product(self) -> bool:
        return isinstance(self.decision, (SelectExistingProduct, CreateProduct))

    @property
    def priced_options(self) -> tuple[FinalOption, ...]:
        """The options that can be published (menu_entry_options.price_krw is required)."""
        return tuple(o for o in self.options if o.price_krw is not None)


@dataclass(frozen=True)
class ValidatedReview:
    # In menu order: image, then line.
    items: list[ReviewedItem]
    changes: list[MenuImportChange]
    change_decisions: dict[UUID, MenuChangeDecision]
    # Existing products selected by select_existing_product decisions.
    products: dict[UUID, Product]


def load_items(session: Session, menu_import: MenuImport) -> list[ExtractedItem]:
    """Every extracted item of the import in menu order, with options and candidates."""
    query = (
        select(ExtractedItem)
        .join(ExtractionRun, ExtractionRun.id == ExtractedItem.extraction_run_id)
        .join(MenuImage, MenuImage.id == ExtractionRun.menu_image_id)
        .where(MenuImage.menu_import_id == menu_import.id)
        .order_by(MenuImage.image_order, ExtractedItem.item_order)
        .options(selectinload(ExtractedItem.options), selectinload(ExtractedItem.candidates))
    )
    return list(session.scalars(query))


def pending_changes(session: Session, menu_import: MenuImport) -> list[MenuImportChange]:
    return list(
        session.scalars(
            select(MenuImportChange).where(
                MenuImportChange.menu_import_id == menu_import.id,
                MenuImportChange.decision == MenuChangeDecision.PENDING,
            )
        )
    )


class _Errors:
    def __init__(self) -> None:
        self.items: list[dict[str, str]] = []

    def add(self, path: str, code: str, message: str) -> None:
        self.items.append({"path": path, "code": code, "message": message})


def _check_normalizable(errors: _Errors, path: str, text: str) -> None:
    if not normalize(text):
        errors.add(path, "NOT_NORMALIZABLE", "이름으로 쓸 수 있는 글자가 없습니다.")


def _check_aliases(errors: _Errors, path: str, aliases: list[ProductAliasInput]) -> None:
    for index, alias in enumerate(aliases):
        _check_normalizable(errors, f"{path}[{index}].aliasText", alias.aliasText)


def _corrected(corrected, extracted):
    """A null correction keeps the extracted value."""
    return extracted if corrected is None else corrected


def _final_options(
    errors: _Errors, path: str, item: ExtractedItem, decision: ProductDecision
) -> tuple[FinalOption, ...]:
    by_id = {option.id: option for option in item.options}
    corrections = {}
    for index, correction in enumerate(decision.optionDecisions):
        option_path = f"{path}.optionDecisions[{index}].extractedOptionId"
        if correction.extractedOptionId not in by_id:
            errors.add(option_path, "UNKNOWN_OPTION", "이 항목의 옵션이 아닙니다.")
        elif correction.extractedOptionId in corrections:
            errors.add(option_path, "DUPLICATE_OPTION", "같은 옵션에 수정이 두 번 있습니다.")
        else:
            corrections[correction.extractedOptionId] = correction
    final = []
    for option in item.options:
        correction = corrections.get(option.id)
        if correction is None:
            final.append(
                FinalOption(option, option.extracted_option_label, option.extracted_pour_ml, option.extracted_price_krw)
            )
            continue
        final.append(
            FinalOption(
                option=option,
                label=_corrected(correction.correctedOptionLabel, option.extracted_option_label),
                pour_ml=_corrected(correction.correctedPourMl, option.extracted_pour_ml),
                price_krw=_corrected(correction.correctedPriceKrw, option.extracted_price_krw),
            )
        )
    return tuple(final)


def validate_review(session: Session, menu_import: MenuImport, request: ReviewAndApplyRequest) -> ValidatedReview:
    errors = _Errors()
    items = load_items(session, menu_import)
    items_by_id = {item.id: item for item in items}
    changes = pending_changes(session, menu_import)
    changes_by_id = {change.id: change for change in changes}

    decided: dict[UUID, tuple[int, ItemDecision]] = {}
    for index, decision in enumerate(request.itemDecisions):
        path = f"itemDecisions[{index}].extractedItemId"
        if decision.extractedItemId not in items_by_id:
            errors.add(path, "UNKNOWN_ITEM", "이 작업의 추출 항목이 아닙니다.")
        elif decision.extractedItemId in decided:
            errors.add(path, "DUPLICATE_ITEM", "같은 항목에 결정이 두 번 있습니다.")
        else:
            decided[decision.extractedItemId] = (index, decision)
    if missing := len(items) - len(decided):
        errors.add("itemDecisions", "MISSING_ITEM", f"결정하지 않은 항목이 {missing}개 있습니다.")

    change_decisions: dict[UUID, MenuChangeDecision] = {}
    change_index: dict[UUID, int] = {}
    for index, decision in enumerate(request.changeDecisions):
        path = f"changeDecisions[{index}].changeId"
        if decision.changeId not in changes_by_id:
            errors.add(path, "UNKNOWN_CHANGE", "이 작업의 변경 제안이 아닙니다.")
        elif decision.changeId in change_decisions:
            errors.add(path, "DUPLICATE_CHANGE", "같은 변경에 결정이 두 번 있습니다.")
        else:
            change_decisions[decision.changeId] = MenuChangeDecision(decision.decision)
            change_index[decision.changeId] = index
    if missing := len(changes) - len(change_decisions):
        errors.add("changeDecisions", "MISSING_CHANGE", f"결정하지 않은 변경 제안이 {missing}개 있습니다.")

    # An item whose proposed add/update is ignored is not published, so it needs no price.
    ignored_items = {
        change.extracted_item_id
        for change in changes
        if change.extracted_item_id and change_decisions.get(change.id) == MenuChangeDecision.IGNORE
    }

    selected_ids = {d.productId for _, d in decided.values() if isinstance(d, SelectExistingProduct)}
    products = {p.id: p for p in session.scalars(select(Product).where(Product.id.in_(selected_ids)))}
    brand_ids = {
        d.brand.brandId for _, d in decided.values() if isinstance(d, CreateProduct) and d.brand.type == "existing"
    }
    known_brands = set(session.scalars(select(Brand.id).where(Brand.id.in_(brand_ids))))

    reviewed: list[ReviewedItem] = []
    for item in items:
        if item.id not in decided:
            continue
        index, decision = decided[item.id]
        path = f"itemDecisions[{index}]"
        if not isinstance(decision, (SelectExistingProduct, CreateProduct)):
            reviewed.append(ReviewedItem(item=item, decision=decision, index=index))
            continue

        options = _final_options(errors, path, item, decision)
        entry = ReviewedItem(item=item, decision=decision, index=index, options=options)
        if item.id not in ignored_items:
            priced = entry.priced_options
            if not priced:
                errors.add(f"{path}.optionDecisions", "NO_PRICED_OPTION", "가격이 있는 옵션이 하나 이상 필요합니다.")
            keys = [(o.label, o.pour_ml) for o in priced]
            if len(keys) != len(set(keys)):
                errors.add(f"{path}.optionDecisions", "DUPLICATE_OPTION_VALUES", "옵션명과 용량이 같은 옵션이 있습니다.")
        if decision.correctedProductName is not None:
            _check_normalizable(errors, f"{path}.correctedProductName", decision.correctedProductName)

        if isinstance(decision, SelectExistingProduct):
            product = products.get(decision.productId)
            if product is None:
                errors.add(f"{path}.productId", "PRODUCT_NOT_FOUND", "상품을 찾을 수 없습니다.")
            elif not product.is_active:
                errors.add(f"{path}.productId", "PRODUCT_INACTIVE", "비활성 상품은 메뉴에 연결할 수 없습니다.")
            _check_aliases(errors, f"{path}.aliasesToAdd", decision.aliasesToAdd)
        else:
            if decision.brand.type == "existing":
                if decision.brand.brandId not in known_brands:
                    errors.add(f"{path}.brand.brandId", "BRAND_NOT_FOUND", "브랜드를 찾을 수 없습니다.")
            else:
                _check_normalizable(errors, f"{path}.brand.canonicalName", decision.brand.canonicalName)
                for alias_index, alias in enumerate(decision.brand.aliases):
                    _check_normalizable(errors, f"{path}.brand.aliases[{alias_index}].aliasText", alias.aliasText)
            _check_normalizable(errors, f"{path}.product.displayName", decision.product.displayName)
            _check_aliases(errors, f"{path}.aliases", decision.aliases)
        reviewed.append(entry)

    reviewed_by_id = {entry.item.id: entry for entry in reviewed}
    for change_id, decision in change_decisions.items():
        change = changes_by_id[change_id]
        entry = reviewed_by_id.get(change.extracted_item_id) if change.extracted_item_id else None
        if decision == MenuChangeDecision.APPLY and entry is not None and not entry.is_product:
            errors.add(
                f"changeDecisions[{change_index[change_id]}].decision",
                "CHANGE_WITHOUT_PRODUCT",
                "상품으로 확정하지 않은 항목의 변경은 적용할 수 없습니다.",
            )

    if errors.items:
        raise validation_failed_fields(errors.items)
    return ValidatedReview(items=reviewed, changes=changes, change_decisions=change_decisions, products=products)
