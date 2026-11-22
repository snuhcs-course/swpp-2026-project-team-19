import { useState } from "react";
import { Link, useLocation } from "react-router";
import { ApiError } from "../api/errors";
import { BarQuery } from "../bar/BarHomePage";
import { useBarFailure } from "../bar/failures";
import { useNow } from "../bar/useNow";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useBar, useBarMenu, type BarMenu, type OwnedBar } from "../owner/queries";
import { BottomSheet } from "../ui/BottomSheet";
import { Button, ButtonLink } from "../ui/Button";
import { TextField } from "../ui/TextField";
import { EDIT_BLOCKED } from "./menuEditor";
import { manualMenuShortName, menuProductOf, type MenuItem } from "./menuRules";
import { discountActive, displayPrice, groupMenu, menuDate, MENU_LOCKED, won } from "./menuView";
import { useMenuWrite } from "./menuWrite";
import { servingDisplayLabel } from "./servingIdentity";
import styles from "./menu.module.css";
import barStyles from "../bar/bar.module.css";

/**
 * /owner/bars/:barId/menu: the bar's published menu (spec 3.9) as android/.../ui/owner/OwnerManualMenuScreen.kt
 * lists it: by kind and, for whisky, by brand, with a search of the menu's own items. An item opens its editor;
 * "+ 직접 추가" adds one; "전체 메뉴 초기화" empties the menu (3.14.6) after asking. While a menu photo import is
 * unfinished (3.6 `activeMenuImport`), nothing can be changed (3.14.7). Adding from menu photos is I5-P9.
 */
export function MenuPage({ bar }: { bar: OwnedBar }) {
  const detail = useBar(bar.barId);
  const menu = useBarMenu(bar.barId);
  return (
    <OwnerScreen title="메뉴 관리" backTo={`/bars/${bar.barId}`}>
      <BarQuery query={menu} keepDataOnRefetchError>
        {(data) => <MenuBoard menu={data} locked={(detail.data ?? bar).activeMenuImport !== null} />}
      </BarQuery>
    </OwnerScreen>
  );
}

/** What a screen left to say when it came back here (an item gone, for example). */
export interface MenuNotice {
  notice?: string;
}

function MenuBoard({ menu, locked }: { menu: BarMenu; locked: boolean }) {
  const location = useLocation();
  const now = useNow();
  const write = useMenuWrite(menu.barId);
  const [query, setQuery] = useState("");
  const [open, setOpen] = useState<string[]>(["위스키"]);
  const [notice, setNotice] = useState<string | null>((location.state as MenuNotice | null)?.notice ?? null);
  const [resetting, setResetting] = useState(false);
  const [resetError, setResetError] = useState<string | null>(null);
  const fail = useBarFailure();
  const { visible, groups } = groupMenu(menu.items, query);
  const searching = query.trim() !== "";
  const base = `/bars/${menu.barId}/menu`;

  async function reset() {
    setResetError(null);
    try {
      const done = await write.send({ kind: "reset" }, menu.menuVersion);
      if (done) setResetting(false);
    } catch (failure) {
      setResetError(writeFailureMessage(failure) ?? fail(failure));
    }
  }

  return (
    <div className={barStyles.screen}>
      {locked ? (
        <p className={styles.notice} role="status">
          {MENU_LOCKED}
        </p>
      ) : null}
      {notice ? (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      ) : null}
      <div className={styles.head}>
        <h2 className={styles.title}>현재 게시 메뉴</h2>
        <Link to={`${base}/new`} className={styles.addLink} aria-disabled={locked || undefined} tabIndex={locked ? -1 : undefined}>
          + 직접 추가
        </Link>
      </div>
      {/* OwnerManualMenuScreen.kt "메뉴명·브랜드 검색", with a comma for its middle dot. */}
      <TextField label="메뉴 검색" type="search" value={query} placeholder="메뉴명, 브랜드 검색" onChange={(event) => setQuery(event.currentTarget.value)} />
      <div className={styles.meta}>
        <span>
          {searching ? `${visible}개 검색됨` : `전체 ${menu.items.length}개`} <span className={styles.updated}>최근 갱신 {menuDate(menu.publishedAt)}</span>
        </span>
        <span>{locked ? "사진 등록 중, 편집 불가" : "메뉴를 선택해서 편집하세요"}</span>
      </div>

      {visible === 0 ? (
        <div className={styles.empty}>
          <p>{searching ? "검색 결과가 없어요." : "등록된 메뉴가 없어요."}</p>
          {!searching && !locked ? (
            <ButtonLink to={`${base}/new`} variant="primary">
              첫 메뉴 추가하기
            </ButtonLink>
          ) : null}
        </div>
      ) : null}

      {groups.map((group) => {
        const expanded = searching || open.includes(group.category);
        return (
          <section key={group.category} className={styles.group} aria-label={group.category}>
            <button
              type="button"
              className={styles.groupHead}
              aria-expanded={expanded}
              onClick={() => setOpen((current) => (current.includes(group.category) ? current.filter((item) => item !== group.category) : [...current, group.category]))}
            >
              <span>{group.category}</span>
              <span aria-hidden="true">{expanded ? "⌃" : "⌄"}</span>
            </button>
            {expanded
              ? group.brands.map((brand) => (
                  <div key={brand.brand}>
                    {group.category === "위스키" ? <h3 className={styles.brand}>{brand.brand}</h3> : null}
                    <ul className={styles.rows}>
                      {brand.items.map((item) => (
                        <li key={item.barMenuItemId}>
                          <MenuRow item={item} now={now} to={`${base}/${item.barMenuItemId}`} locked={locked} onBlocked={setNotice} />
                        </li>
                      ))}
                    </ul>
                  </div>
                ))
              : null}
          </section>
        );
      })}

      <button type="button" className={styles.reset} disabled={locked} onClick={() => (setResetError(null), setResetting(true))}>
        전체 메뉴 초기화
      </button>

      <BottomSheet open={resetting} title="전체 메뉴를 초기화할까요?" onClose={() => !write.pending && setResetting(false)}>
        {/* OwnerManualMenuScreen.kt, with a comma for its middle dot. */}
        <p className={barStyles.sheetText}>모든 메뉴와 용량, 가격 정보가 삭제됩니다.</p>
        {resetError ? (
          <p className={barStyles.error} role="alert">
            {resetError}
          </p>
        ) : null}
        <div className={barStyles.actions}>
          <Button variant="secondary" disabled={write.pending} onClick={() => setResetting(false)}>
            취소
          </Button>
          <Button busy={write.pending} onClick={() => void reset()}>
            초기화
          </Button>
        </div>
      </BottomSheet>
    </div>
  );
}

/**
 * The copy for the menu's own conflicts (spec 3.14.7), or null for the failures every bar change shares.
 */
export function writeFailureMessage(failure: unknown): string | null {
  if (!(failure instanceof ApiError)) return null;
  switch (failure.code) {
    case "MENU_OUTDATED":
      return "메뉴가 다른 곳에서 바뀌었어요. 확인한 뒤 다시 시도해 주세요.";
    case "ACTIVE_IMPORT_EXISTS":
      return MENU_LOCKED;
    case "MENU_ITEM_NOT_FOUND":
      return "이미 메뉴판에서 빠진 메뉴예요.";
    default:
      return null;
  }
}

/** OwnerSharedMenuRow.kt `OwnerMenuFlatRow`: the name, sale status, and each option's serving and price. */
function MenuRow({ item, now, to, locked, onBlocked }: { item: MenuItem; now: number; to: string; locked: boolean; onBlocked: (message: string) => void }) {
  const product = menuProductOf(item);
  const name = manualMenuShortName({ displayName: item.displayName, category: product.category }, item.brandName ?? "");
  const content = (
    <>
      <span className={styles.name}>
        <span>{name}</span>
        <span className={styles.status}>{item.soldOut ? "품절" : "판매 중"}</span>
      </span>
      <dl className={styles.prices}>
        {item.options.map((option) => (
          <div key={option.menuEntryOptionId} className={styles.priceLine}>
            <dd>{discountActive(option, now) ? <span className={styles.badge}>할인</span> : null}</dd>
            <dt>{servingDisplayLabel(option.pourMl, option.optionLabel)}</dt>
            <dd className={styles.price}>{won(displayPrice(option, now))}</dd>
          </div>
        ))}
      </dl>
    </>
  );
  const className = [styles.row, item.soldOut ? styles.soldOut : ""].join(" ");
  if (locked) return <div className={className}>{content}</div>;
  // OwnerManualMenuScreen.kt `edit`: an item with four or more options does not open.
  if (item.options.length > 3) {
    return (
      <button type="button" className={className} aria-label={`${item.displayName} 수정`} onClick={() => onBlocked(EDIT_BLOCKED)}>
        {content}
      </button>
    );
  }
  return (
    <Link to={to} className={className} aria-label={`${item.displayName} 수정`}>
      {content}
    </Link>
  );
}
