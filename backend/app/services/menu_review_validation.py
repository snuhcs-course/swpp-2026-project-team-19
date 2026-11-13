"""Checks on a review submission that need the import's rows (API spec 8.7). Reads only.

The request body's own shape is checked by the schema. This checks the decisions against
the import: every item and pending change decided exactly once, options come from their own
item and have different label and pour size, selected products and brands exist, names
normalize to something, only operators grow the catalog (OPERATOR_ONLY), and applied changes
point at items published as menu items. All problems are reported together as one 422.

State checks (status, reviewVersion, board changes) and duplicate checks for new catalog
entries happen in the apply step, inside its transaction.
"""

from dataclasses import dataclass, field
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.errors import validation_failed_fields
from app.core.normalize import normalize
from app.models import (
    BarMenuItem,
    Brand,
    ExtractedItem,
    ExtractedOption,
    ExtractionRun,
    MenuBoard,
    MenuBoardEntry,
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
    PublishWithoutProduct,
    ReviewAndApplyRequest,
    SelectExistingProduct,
)
from app.services.menu_items import ItemKey, item_key, name_key

PRODUCT_DECISIONS = (SelectExistingProduct, CreateProduct, PublishWithoutProduct)


@dataclass(frozen=True)
class FinalOption:
    """One option of the line's final list (spec 8.1), with the extracted option it comes from (None when
    the reviewer added it)."""

    option: ExtractedOption | None
    label: str | None
    pour_ml: int | None
    price_krw: int


@dataclass(frozen=True)
class ReviewedItem:
    item: ExtractedItem
    decision: ItemDecision
    # Position in itemDecisions, for error paths.
    index: int
    # The final options of a decision that publishes the line, in display order; empty otherwise.
    options: tuple[FinalOption, ...] = ()

    @property
    def is_product(self) -> bool:
        """Published as a menu item, with a product or without one."""
        return isinstance(self.decision, PRODUCT_DECISIONS)

    @property
    def is_unlinked(self) -> bool:
        return isinstance(self.decision, PublishWithoutProduct)

    @property
    def menu_name(self) -> str | None:
        """The name on the menu: the corrected name, else the extracted one (a line retyped as a product
        may have none; a product decision then falls back to the product's name)."""
        return self.decision.correctedProductName or self.item.extracted_product_name


@dataclass(frozen=True)
class ValidatedReview:
    # In menu order: image, then line.
    items: list[ReviewedItem]
    changes: list[MenuImportChange]
    change_decisions: dict[UUID, MenuChangeDecision]
    # Existing products selected by select_existing_product decisions.
    products: dict[UUID, Product]
    # Lines not published because the reviewer ignored their change (see ignored_lines).
    ignored_lines: set[UUID] = field(default_factory=set)


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


def _final_options(
    errors: _Errors, path: str, item: ExtractedItem, decision: ProductDecision
) -> tuple[FinalOption, ...]:
    """The decision's options as sent. An extractedOptionId must name one of the line's own options, once."""
    by_id = {option.id: option for option in item.options}
    seen: set[UUID] = set()
    final = []
    for index, sent in enumerate(decision.options):
        source = None
        if sent.extractedOptionId is not None:
            option_path = f"{path}.options[{index}].extractedOptionId"
            source = by_id.get(sent.extractedOptionId)
            if source is None:
                errors.add(option_path, "UNKNOWN_OPTION", "이 항목의 옵션이 아닙니다.")
            elif sent.extractedOptionId in seen:
                errors.add(option_path, "DUPLICATE_OPTION", "같은 옵션이 두 번 있습니다.")
            seen.add(sent.extractedOptionId)
        final.append(FinalOption(source, sent.optionLabel, sent.pourMl, sent.priceKrw))
    return tuple(final)


def proposal_key(item: ExtractedItem) -> ItemKey:
    """What the draft proposed for the line: its rank-1 product, else its extracted name's key (spec 5.4)."""
    if item.candidates:
        return item_key(item.candidates[0].product_id, None)
    return item_key(None, name_key(item.extracted_product_name or ""))


def _final_key(item: ExtractedItem, decision: ItemDecision) -> ItemKey | None:
    """What the reviewer decided the line is; None when it is no menu item or a product still to be created
    (a new product is never what the draft proposed)."""
    if isinstance(decision, SelectExistingProduct):
        return item_key(decision.productId, None)
    if isinstance(decision, PublishWithoutProduct):
        return item_key(None, name_key(decision.correctedProductName or item.extracted_product_name or ""))
    return None


def _board_keys(session: Session, bar_id: UUID) -> dict[UUID, ItemKey]:
    """The key of every item on the bar's current board."""
    rows = session.execute(
        select(BarMenuItem.id, BarMenuItem.product_id, BarMenuItem.name_key)
        .join(MenuBoardEntry, MenuBoardEntry.bar_menu_item_id == BarMenuItem.id)
        .join(MenuBoard, MenuBoard.id == MenuBoardEntry.menu_board_id)
        .where(MenuBoard.bar_id == bar_id)
    ).all()
    return {item_id: item_key(product_id, key) for item_id, product_id, key in rows}


def ignored_lines(
    changes: list[MenuImportChange],
    change_decisions: dict[UUID, MenuChangeDecision],
    final_keys: dict[UUID, ItemKey | None],
    proposal_keys: dict[UUID, ItemKey],
    board_keys: dict[UUID, ItemKey],
) -> set[UUID]:
    """Lines not published because their change was ignored (spec 8.7): only while the line's final
    decision is still the change's target, which is what the line was proposed as, or the board item the
    change was compared with. A line the reviewer decided to be something else follows that decision.
    A line proposed without a product has no such target: its change adds the line as whatever it is
    decided to be (spec 5.4), so ignoring it always skips the line."""
    skipped = set()
    for change in changes:
        line = change.extracted_item_id
        if line is None or change_decisions.get(change.id) != MenuChangeDecision.IGNORE:
            continue
        proposed = proposal_keys.get(line)
        if proposed is None or proposed[0] == "name":
            skipped.add(line)
            continue
        targets = {proposed}
        if change.bar_menu_item_id in board_keys:
            targets.add(board_keys[change.bar_menu_item_id])
        if final_keys.get(line) in targets:
            skipped.add(line)
    return skipped


def validate_review(
    session: Session, menu_import: MenuImport, request: ReviewAndApplyRequest, *, operator: bool
) -> ValidatedReview:
    """`operator`: whether the caller is an operator, who alone may grow the shared catalog (spec 2.2)."""
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

    # A line whose ignored change still targets what it was decided to be is not published, so its options
    # are not compared.
    ignored_items = ignored_lines(
        changes,
        change_decisions,
        {item_id: _final_key(items_by_id[item_id], decision) for item_id, (_, decision) in decided.items()},
        {item.id: proposal_key(item) for item in items},
        _board_keys(session, menu_import.bar_id),
    )

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
        if not isinstance(decision, PRODUCT_DECISIONS):
            reviewed.append(ReviewedItem(item=item, decision=decision, index=index))
            continue

        options = _final_options(errors, path, item, decision)
        entry = ReviewedItem(item=item, decision=decision, index=index, options=options)
        if item.id not in ignored_items:
            keys = [(o.label, o.pour_ml) for o in options]
            if len(keys) != len(set(keys)):
                errors.add(f"{path}.options", "DUPLICATE_OPTION_VALUES", "옵션명과 용량이 같은 옵션이 있습니다.")
        if isinstance(decision, PublishWithoutProduct):
            # Known only by its menu name, which must have a name key (spec 8.7).
            if not name_key(entry.menu_name or ""):
                errors.add(f"{path}.correctedProductName", "NOT_NORMALIZABLE", "메뉴 이름으로 쓸 수 있는 글자가 없습니다.")
        elif decision.correctedProductName is not None:
            _check_normalizable(errors, f"{path}.correctedProductName", decision.correctedProductName)

        if isinstance(decision, CreateProduct) and not operator:
            errors.add(f"{path}.action", "OPERATOR_ONLY", "새 상품은 운영자만 만들 수 있습니다.")
        if isinstance(decision, SelectExistingProduct) and decision.aliasesToAdd and not operator:
            errors.add(f"{path}.aliasesToAdd", "OPERATOR_ONLY", "별칭은 운영자만 추가할 수 있습니다.")

        if isinstance(decision, SelectExistingProduct):
            product = products.get(decision.productId)
            if product is None:
                errors.add(f"{path}.productId", "PRODUCT_NOT_FOUND", "상품을 찾을 수 없습니다.")
            elif not product.is_active:
                errors.add(f"{path}.productId", "PRODUCT_INACTIVE", "비활성 상품은 메뉴에 연결할 수 없습니다.")
            _check_aliases(errors, f"{path}.aliasesToAdd", decision.aliasesToAdd)
        elif isinstance(decision, CreateProduct):
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
    return ValidatedReview(
        items=reviewed, changes=changes, change_decisions=change_decisions, products=products, ignored_lines=ignored_items
    )
