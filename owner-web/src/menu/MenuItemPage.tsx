import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { unwrap } from "../api/client";
import { ApiError, errorMessage, fieldErrorMessages } from "../api/errors";
import { useSession } from "../auth/SessionProvider";
import { BarQuery } from "../bar/BarHomePage";
import { useBarFailure } from "../bar/failures";
import { useLeaveGuard } from "../bar/useLeaveGuard";
import { OwnerScreen } from "../owner/OwnerScreen";
import {
  ownerQueryKeys,
  useBar,
  useBarMenu,
  useCatalogBrands,
  useCatalogProducts,
  type BarMenu,
  type CatalogProduct,
  type OwnedBar,
} from "../owner/queries";
import { BottomSheet } from "../ui/BottomSheet";
import { Button, ButtonLink } from "../ui/Button";
import { ErrorState } from "../ui/states";
import { TextField } from "../ui/TextField";
import { inactiveOwnerCatalogMatch, manualBrandProposal, manualBrandSearchQuery, manualProductProposal } from "./catalogMatch";
import {
  ALREADY_ON_MENU,
  confirmFirst,
  EDIT_BLOCKED,
  editDraftOf,
  freshExactMatch,
  freshOption,
  MAX_NAME_LENGTH,
  prepareMenuSave,
  SaveRefused,
  type DraftOption,
  type SaveRequest,
} from "./menuEditor";
import {
  MANUAL_MENU_CATEGORIES,
  MANUAL_MENU_MAX_OPTIONS,
  existingBarProductMenu,
  menuBrandsOf,
  menuProductOf,
  ownerPriceInput,
  type MenuBrand,
  type MenuCategory,
  type MenuItem,
  type MenuProduct,
} from "./menuRules";
import { MENU_LOCKED } from "./menuView";
import { useMenuWrite } from "./menuWrite";
import { writeFailureMessage, type MenuNotice } from "./MenuPage";
import styles from "./menu.module.css";
import barStyles from "../bar/bar.module.css";

/**
 * /owner/bars/:barId/menu/new and /owner/bars/:barId/menu/:barMenuItemId: adding an item (spec 3.14.3) and
 * editing one's menu name and options (3.14.4), as android/.../ui/owner/OwnerManualMenuScreen.kt does.
 *
 * - An added whisky is linked to a catalog product only when the owner confirms the proposal with "맞아요"
 *   (OwnerManualCatalogMatch.kt); otherwise it is added without a product (`kind`), for an operator to link.
 * - An edit changes the name and options only: the request cannot choose a product (3.14.4).
 * - Discounts are not edited here (I5-P8): an edit sends them back as they came, so they are kept.
 */
export function MenuItemPage({ bar }: { bar: OwnedBar }) {
  const { barMenuItemId } = useParams();
  const adding = barMenuItemId === undefined;
  const detail = useBar(bar.barId);
  const menu = useBarMenu(bar.barId);
  const locked = (detail.data ?? bar).activeMenuImport !== null;
  return (
    <OwnerScreen title={adding ? "메뉴 직접 추가" : "메뉴 수정"} backTo={`/bars/${bar.barId}/menu`}>
      <BarQuery query={menu} keepDataOnRefetchError>
        {/* Keyed by the item: moving straight from one item (or the add) to another opens it afresh. */}
        {(data) => <ItemEditor key={barMenuItemId ?? "new"} menu={data} barMenuItemId={barMenuItemId} locked={locked} />}
      </BarQuery>
    </OwnerScreen>
  );
}

function ItemEditor({ menu, barMenuItemId, locked }: { menu: BarMenu; barMenuItemId: string | undefined; locked: boolean }) {
  // The item as the editor opened: a later reading of the menu does not reset what is typed.
  const [opened] = useState(() => (barMenuItemId === undefined ? undefined : menu.items.find((item) => item.barMenuItemId === barMenuItemId)));
  const back = `/bars/${menu.barId}/menu`;
  if (barMenuItemId !== undefined && !opened) {
    return <ErrorState message="메뉴판에 없는 메뉴예요." action={<ButtonLink to={back}>메뉴 목록으로</ButtonLink>} />;
  }
  if (opened && !editDraftOf(opened)) {
    return <ErrorState message={EDIT_BLOCKED} action={<ButtonLink to={back}>메뉴 목록으로</ButtonLink>} />;
  }
  return <ItemForm key={barMenuItemId ?? "new"} menu={menu} editing={opened} locked={locked} />;
}

/** Copy for the codes of spec 3.14.7 that the shared field copy (src/api/errors.ts) lacks. */
const FIELD_COPY: Record<string, string> = {
  NOT_NORMALIZABLE: "메뉴 이름에 쓸 수 있는 글자가 없어요.",
  DUPLICATE_OPTION_VALUES: "같은 제품에 동일한 용량 옵션을 중복 등록할 수 없어요.",
  TOO_SHORT: "가격 옵션은 1~3개여야 해요.",
  TOO_LONG: "가격 옵션은 1~3개여야 해요.",
  PRODUCT_INACTIVE: "운영이 중지된 카탈로그 상품이에요. 운영자에게 문의해 주세요.",
  PRODUCT_NOT_FOUND: "선택한 상품을 찾지 못했어요. 다시 확인해 주세요.",
  DISCOUNT_NOT_LOWER: "할인 가격은 가격보다 낮아야 해요.",
  DISCOUNT_ENDED: "할인 기간이 끝났어요. 다시 저장해 주세요.",
  END_BEFORE_START: "할인 가격과 기간을 확인해 주세요.",
};
const CHECK_INPUT = "입력한 내용을 확인해 주세요.";
const OUTDATED = "메뉴가 다른 곳에서 바뀌었어요. 확인한 뒤 다시 저장해 주세요.";

interface Problems {
  name?: string;
  options?: string;
  byOption: Partial<Record<number, string>>;
}

/** A catalog product as the proposal rules see it. */
const catalogProduct = (item: CatalogProduct): MenuProduct => ({
  productId: item.productId,
  brandId: item.brandId,
  displayName: item.displayName,
  category: item.category,
  ageYears: item.ageYears,
  isActive: item.isActive,
  matchedAlias: item.matchedAlias,
  catalogMatched: true,
});

function useDebounced<T>(value: T, ms: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), ms);
    return () => clearTimeout(timer);
  }, [value, ms]);
  return debounced;
}

function ItemForm({ menu, editing, locked }: { menu: BarMenu; editing: MenuItem | undefined; locked: boolean }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { api } = useSession();
  const write = useMenuWrite(menu.barId);
  const back = `/bars/${menu.barId}/menu`;
  const [start] = useState(() => {
    const draft = editing ? editDraftOf(editing) : null;
    return draft ?? { name: "", category: "위스키" as MenuCategory, options: [freshOption()] };
  });
  const [name, setName] = useState(start.name);
  const [category, setCategory] = useState<MenuCategory>(start.category);
  const [options, setOptions] = useState<DraftOption[]>(start.options);
  const [linkedId, setLinkedId] = useState<string | null>(null);
  const [rejectedId, setRejectedId] = useState<string | null>(null);
  const [confirmedBrandId, setConfirmedBrandId] = useState<string | null>(null);
  // The menu version the edit is made on (spec 3.14.1); after MENU_OUTDATED, the one read again.
  const [version, setVersion] = useState(menu.menuVersion);
  const [error, setError] = useState<string | null>(null);
  const [existingItemId, setExistingItemId] = useState<string | null>(null);
  const [problems, setProblems] = useState<Problems>({ byOption: {} });
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const busy = write.pending || checking;
  const dirty = name !== start.name || category !== start.category || JSON.stringify(options) !== JSON.stringify(start.options);
  const guard = useLeaveGuard(dirty, busy);
  const fail = useBarFailure(guard.release);
  const whisky = category === "위스키";
  const adding = editing === undefined;

  // OwnerManualMenuScreen.kt: while a whisky is being added, the catalog is searched for its name (spec 7) and
  // its brand (spec 6), 300 ms after typing stops.
  const typed = useDebounced(name.trim(), 300);
  const proposing = adding && whisky;
  const products = useCatalogProducts(typed, proposing && typed.length >= 2 && typed.length <= 100);
  const brandQuery = manualBrandSearchQuery(typed, "");
  const brandResults = useCatalogBrands(brandQuery, proposing && linkedId === null && brandQuery.length >= 2 && brandQuery.length <= 100);
  // The shared catalog is whisky only (PR #164); the menu's own items are offered too.
  const searched = (products.data ?? []).map(catalogProduct).filter((product) => product.category === "whisky");
  const menuProducts = menu.items.map(menuProductOf).filter((product) => !product.catalogMatched || product.category === "whisky");
  const candidates = unique([...searched, ...menuProducts], (product) => product.productId);
  const brands = unique<MenuBrand>(
    [
      ...menuBrandsOf(menu.items),
      ...(products.data ?? []).map((item) => ({ brandId: item.brandId, name: item.brandName, matchedAlias: null })),
      ...(brandResults.data ?? []).map((item) => ({ brandId: item.brandId, name: item.canonicalName, matchedAlias: item.matchedAlias })),
    ].reverse(),
    (brand) => brand.brandId,
  ).reverse();
  const matchedBrandId = confirmedBrandId ?? manualBrandProposal(brands, name, "", null)?.brandId ?? null;
  const suggested = proposing ? manualProductProposal(candidates, name, category, matchedBrandId, rejectedId) : null;
  const inactive = proposing ? inactiveOwnerCatalogMatch(candidates, name) : null;
  const linkedOnMenu = proposing && linkedId ? existingBarProductMenu(menu.items, linkedId) : undefined;

  function clearProblems() {
    setError(null);
    setExistingItemId(null);
    setProblems({ byOption: {} });
  }

  function changeOption(index: number, change: Partial<DraftOption>) {
    setOptions((current) => current.map((option, at) => (at === index ? { ...option, ...change } : option)));
    setProblems(({ byOption: { [index]: _, ...rest }, ...others }) => ({ ...others, options: undefined, byOption: rest }));
    setError(null);
  }

  function openItem(itemId: string) {
    guard.release();
    void navigate(`${back}/${itemId}`);
  }

  function leave(state?: MenuNotice) {
    guard.release();
    void navigate(back, { state });
  }

  async function save() {
    if (busy || locked) return;
    clearProblems();
    let request: SaveRequest;
    try {
      request = prepareMenuSave({ items: menu.items, editing, name, category, options, linkedId, rejectedId, candidates, now: Date.now() });
    } catch (failure) {
      if (failure instanceof SaveRefused) {
        setError(failure.message);
        setExistingItemId(failure.existingItemId ?? null);
        return;
      }
      throw failure;
    }
    if (request.kind === "add" && "kind" in request.body && whisky && request.body.displayName.length >= 2) {
      // The app searches once more before adding a whisky without a product: an exact active product must be
      // confirmed or declined first.
      setChecking(true);
      try {
        const query = request.body.displayName;
        const fresh = await queryClient.fetchQuery({
          queryKey: ownerQueryKeys.catalogProducts(query),
          queryFn: async ({ signal }) => unwrap(await api.GET("/api/catalog/products", { params: { query: { query } }, signal })).items,
          staleTime: 0,
        });
        const exact = freshExactMatch(fresh.map(catalogProduct), query, category, rejectedId);
        if (exact) return setError(confirmFirst(exact));
      } catch (failure) {
        return setError(errorMessage(failure));
      } finally {
        setChecking(false);
      }
    }
    const change = request.kind === "add" ? ({ kind: "add", body: request.body } as const) : ({ kind: "edit", barMenuItemId: request.barMenuItemId, body: request.body } as const);
    try {
      const done = await write.send(change, version);
      if (done) leave();
    } catch (failure) {
      handleFailure(failure, request);
    }
  }

  function handleFailure(failure: unknown, request: SaveRequest) {
    if (!(failure instanceof ApiError)) return setError(errorMessage(failure));
    switch (failure.code) {
      case "VALIDATION_FAILED":
        return showFieldErrors(failure, request);
      case "MENU_OUTDATED":
        // The menu was read again: keep what is typed, and save on the version now current.
        setVersion(queryClient.getQueryData<BarMenu>(ownerQueryKeys.menu(menu.barId))?.menuVersion ?? version);
        return setError(OUTDATED);
      case "MENU_ITEM_NOT_FOUND":
        return leave({ notice: writeFailureMessage(failure) ?? undefined });
      case "MENU_ITEM_EXISTS": {
        const itemId = failure.details?.barMenuItemId;
        setExistingItemId(typeof itemId === "string" ? itemId : null);
        return setError(ALREADY_ON_MENU);
      }
      case "ACTIVE_IMPORT_EXISTS":
        return setError(MENU_LOCKED);
      default:
        return setError(fail(failure));
    }
  }

  /** Each 422 field error goes under its field: the name, an option (by its index in the options sent), or the list. */
  function showFieldErrors(failure: ApiError, request: SaveRequest) {
    const messages = fieldErrorMessages(failure);
    const next: Problems = { byOption: {} };
    for (const item of failure.fieldErrors) {
      const message = FIELD_COPY[item.code] ?? messages[item.path] ?? CHECK_INPUT;
      const option = /^options\[(\d+)\]/.exec(item.path);
      if (item.path === "displayName" || item.path === "productId" || item.path === "kind") next.name ??= message;
      else if (option && Number(option[1]) < request.shown) next.byOption[Number(option[1])] ??= message;
      // The rest is about the list: TOO_SHORT, TOO_LONG, and DUPLICATE_OPTION_VALUES, whose path is "options"
      // (backend menu_edit.py), or an option the editor does not show.
      else next.options ??= message;
    }
    // Spec 3.14.2: a discount that ended after the editor opened is left out the next time.
    const ended = failure.fieldErrors.flatMap((item) => {
      const index = item.code === "DISCOUNT_ENDED" ? /^options\[(\d+)\]/.exec(item.path)?.[1] : undefined;
      return index === undefined ? [] : [Number(index)];
    });
    if (ended.length) {
      setOptions((current) => current.map((option, index) => (ended.includes(index) ? { ...option, discount: null } : option)));
      void queryClient.invalidateQueries({ queryKey: ownerQueryKeys.menu(menu.barId), refetchType: "all" });
    }
    setProblems(next);
    setError(next.name || next.options || Object.keys(next.byOption).length ? CHECK_INPUT : errorMessage(failure));
  }

  async function remove() {
    if (!editing) return;
    setDeleteError(null);
    try {
      const done = await write.send({ kind: "delete", barMenuItemId: editing.barMenuItemId }, version);
      if (done) leave();
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "MENU_ITEM_NOT_FOUND") return leave({ notice: writeFailureMessage(failure) ?? undefined });
      if (failure instanceof ApiError && failure.code === "MENU_OUTDATED") {
        setVersion(queryClient.getQueryData<BarMenu>(ownerQueryKeys.menu(menu.barId))?.menuVersion ?? version);
      }
      setDeleteError(writeFailureMessage(failure) ?? fail(failure));
    }
  }

  return (
    <>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          void save();
        }}
      >
        <fieldset className={[barStyles.screen, barStyles.fieldset].join(" ")} disabled={busy || locked}>
          {locked ? (
            <p className={styles.notice} role="status">
              {MENU_LOCKED}
            </p>
          ) : null}
          {editing ? (
            <div className={styles.head}>
              <span />
              <Button variant="secondary" onClick={() => (setDeleteError(null), setDeleting(true))}>
                삭제
              </Button>
            </div>
          ) : null}
          <TextField
            label="메뉴 이름"
            value={name}
            placeholder="예: 라가불린 10년"
            error={problems.name}
            onChange={(event) => {
              setName(event.currentTarget.value.slice(0, MAX_NAME_LENGTH));
              // A confirmed link stays when the name on the menu is changed; a declined proposal may come back.
              if (adding) setRejectedId(null);
              setProblems((current) => ({ ...current, name: undefined }));
              setError(null);
            }}
          />
          {proposing ? (
            <>
              {inactive ? (
                <p className={barStyles.hint}>“{inactive.displayName}”은 현재 비활성 상품이에요. 선택하거나 새로 만들 수 없어요. 운영자에게 문의해 주세요.</p>
              ) : null}
              {suggested && !inactive && linkedId !== suggested.productId ? (
                <div className={styles.proposal} role="group" aria-label="상품 확인">
                  <p>“{suggested.displayName}”이 맞나요?</p>
                  <div className={barStyles.actions}>
                    <Button
                      onClick={() => {
                        setLinkedId(suggested.productId);
                        setConfirmedBrandId(suggested.brandId);
                        setName(suggested.displayName);
                        clearProblems();
                      }}
                    >
                      맞아요
                    </Button>
                    <Button variant="secondary" onClick={() => (setRejectedId(suggested.productId), clearProblems())}>
                      아니에요
                    </Button>
                  </div>
                </div>
              ) : null}
              {linkedOnMenu ? (
                <Button variant="secondary" onClick={() => openItem(linkedOnMenu.barMenuItemId)}>
                  기존 메뉴에서 용량, 가격 수정
                </Button>
              ) : null}
            </>
          ) : null}

          {adding ? (
            <label className={styles.bottleValue}>
              <span>종류</span>
              <select
                className={styles.select}
                value={category}
                onChange={(event) => {
                  setCategory(event.currentTarget.value as MenuCategory);
                  setLinkedId(null);
                  setRejectedId(null);
                  clearProblems();
                }}
              >
                {MANUAL_MENU_CATEGORIES.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </label>
          ) : null}

          <section className={barStyles.section} aria-labelledby="menu-options-title">
            <div className={barStyles.sectionHead}>
              <h2 id="menu-options-title" className={barStyles.sectionTitle}>
                {whisky ? "용량별 가격" : "가격"}
              </h2>
              {whisky ? (
                <span className={barStyles.hint}>
                  {options.length}/{MANUAL_MENU_MAX_OPTIONS}
                </span>
              ) : null}
            </div>
            {(whisky ? options : options.slice(0, 1)).map((option, index) => (
              <fieldset key={option.id} className={styles.option}>
                {whisky ? (
                  <legend className={styles.optionHead}>
                    <span>
                      {index + 1}번 옵션
                      {/* OwnerManualMenuScreen.kt "할인 · N원", with a space for its middle dot. */}
                      {option.discount ? <span className={styles.badge}> 할인 {option.discount.discountedPriceKrw.toLocaleString("ko-KR")}원</span> : null}
                    </span>
                  </legend>
                ) : (
                  <legend className={barStyles.hint}>판매 가격</legend>
                )}
                {whisky ? (
                  <>
                    {options.length > 1 ? (
                      <Button variant="text" aria-label={`${index + 1}번 옵션 제거`} onClick={() => setOptions((current) => current.filter((_, at) => at !== index))}>
                        제거
                      </Button>
                    ) : null}
                    <label className={styles.check}>
                      <input type="checkbox" checked={option.bottle} onChange={(event) => changeOption(index, { bottle: event.currentTarget.checked })} />
                      Bottle 판매
                    </label>
                    <div className={styles.optionFields}>
                      {option.bottle ? (
                        <div className={styles.bottleValue}>
                          <span>용량</span>
                          <span>Bottle</span>
                        </div>
                      ) : (
                        <TextField
                          label="용량 (ml)"
                          value={option.ml}
                          inputMode="numeric"
                          onChange={(event) => changeOption(index, { ml: event.currentTarget.value.replace(/\D/g, "") })}
                        />
                      )}
                      <TextField
                        label="가격 (원)"
                        value={option.price}
                        inputMode="numeric"
                        onChange={(event) => changeOption(index, { price: ownerPriceInput(option.price, event.currentTarget.value) })}
                      />
                    </div>
                  </>
                ) : (
                  <TextField
                    label="판매 가격 (원)"
                    value={option.price}
                    inputMode="numeric"
                    onChange={(event) => changeOption(index, { price: ownerPriceInput(option.price, event.currentTarget.value) })}
                  />
                )}
                {problems.byOption[index] ? (
                  <p className={barStyles.error} role="alert">
                    {problems.byOption[index]}
                  </p>
                ) : null}
              </fieldset>
            ))}
            {whisky ? (
              options.length < MANUAL_MENU_MAX_OPTIONS ? (
                <button type="button" className={styles.addOption} onClick={() => (setOptions((current) => [...current, freshOption()]), setError(null))}>
                  + 용량 옵션 추가
                </button>
              ) : (
                <p className={barStyles.hint}>가격 옵션은 최대 3개까지 등록할 수 있어요.</p>
              )
            ) : null}
            {problems.options ? (
              <p className={barStyles.error} role="alert">
                {problems.options}
              </p>
            ) : null}
          </section>

          {error ? (
            <p className={barStyles.error} role="alert">
              {error}
            </p>
          ) : null}
          {existingItemId ? (
            <Button variant="secondary" onClick={() => openItem(existingItemId)}>
              기존 메뉴에서 용량, 가격 수정
            </Button>
          ) : null}
          <Button type="submit" busy={busy}>
            {adding ? "메뉴 추가" : "저장하기"}
          </Button>
        </fieldset>
      </form>

      <BottomSheet open={deleting} title="메뉴를 삭제할까요?" onClose={() => !write.pending && setDeleting(false)}>
        <p className={barStyles.sheetText}>삭제하면 고객 메뉴에서도 바로 사라집니다.</p>
        {deleteError ? (
          <p className={barStyles.error} role="alert">
            {deleteError}
          </p>
        ) : null}
        <div className={barStyles.actions}>
          <Button variant="secondary" disabled={write.pending} onClick={() => setDeleting(false)}>
            취소
          </Button>
          <Button busy={write.pending} onClick={() => void remove()}>
            삭제하기
          </Button>
        </div>
      </BottomSheet>

      <BottomSheet open={guard.asking} title="변경을 취소할까요?" onClose={guard.stay}>
        {/* OwnerInfoHtmlV4Screen.kt's discard sheet, as on the other editors. */}
        <p className={barStyles.sheetText}>저장하지 않은 수정 사항은 사라집니다.</p>
        <div className={barStyles.actions}>
          <Button variant="secondary" onClick={guard.stay}>
            계속 편집
          </Button>
          <Button onClick={guard.leave}>변경 취소</Button>
        </div>
      </BottomSheet>
    </>
  );
}

function unique<T>(items: readonly T[], key: (item: T) => string): T[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const id = key(item);
    if (seen.has(id)) return false;
    seen.add(id);
    return true;
  });
}
