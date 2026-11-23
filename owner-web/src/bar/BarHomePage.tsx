import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/errors";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useBar, useBarMenu, useCancelException, type BarDetail, type OwnedBar } from "../owner/queries";
import { useConfirmMenu } from "../menu/menuStatus";
import { lastMenuUpdate, menuDate, menuFreshness } from "../menu/menuView";
import { BottomSheet } from "../ui/BottomSheet";
import { Button, ButtonLink } from "../ui/Button";
import { ErrorState } from "../ui/states";
import { useBarFailure } from "./failures";
import { homeOperatingException, homeStatusDetail, homeStatusTitle, operatingLine } from "./operating";
import { useNow } from "./useNow";
import { QueryView } from "../ui/QueryView";
import styles from "./bar.module.css";

/**
 * /owner/bars/:barId: the bar's management home (android/.../ui/owner/OwnerManagementHomeScreen.kt), from
 * GET /api/bars/{barId} (spec 3.6): the bar info editor, the operating status and its temporary closure, and
 * the menu.
 */
export function BarHomePage({ bar }: { bar: OwnedBar }) {
  const detail = useBar(bar.barId);
  return (
    <OwnerScreen title={detail.data?.name ?? bar.name} backTo="/bars">
      <BarQuery query={detail}>
        {(data) => (
          <div className={styles.cards}>
            <Link to={`/bars/${data.barId}/info`} className={styles.card}>
              <h2 className={styles.cardTitle}>매장 정보 관리</h2>
              {/* OwnerManagementHomeScreen.kt: a fixed line, not the values (commas, not the app's middle dots). */}
              <p className={styles.cardText}>사진, 소개, 영업시간</p>
              <span className={styles.cardFooter} aria-hidden="true">
                ›
              </span>
            </Link>
            <StatusCard bar={data} />
            <MenuCard bar={data} />
          </div>
        )}
      </BarQuery>
    </OwnerScreen>
  );
}

/**
 * The operating status card (OwnerManagementHomeScreen.kt `owner-home-status-card`): the temporary closure's
 * title and dates or hours, the open status now (from the customer preview, OwnerPreviewV4Status.kt), and ×
 * to end the closure. Computed again every 30 seconds (spec 3.15.5).
 */
function StatusCard({ bar }: { bar: BarDetail }) {
  const now = useNow();
  const cancel = useCancelException(bar.barId);
  const fail = useBarFailure();
  const [asking, setAsking] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const exception = homeOperatingException(bar, now);
  const detail = homeStatusDetail(exception);

  function confirm() {
    if (cancel.isPending) return;
    setError(null);
    cancel.mutate(undefined, {
      onSuccess: () => setAsking(false),
      onError: (failure) => {
        setAsking(false);
        setError(fail(failure));
      },
    });
  }

  return (
    <section className={[styles.card, styles.statusCard].join(" ")} aria-label="영업 상태">
      <Link to={`/bars/${bar.barId}/status`} className={styles.cardLink}>
        <h2 className={[styles.cardTitle, styles.statusTitle].join(" ")}>{homeStatusTitle(exception, now)}</h2>
        {detail ? <p className={styles.cardText}>{detail}</p> : null}
        <p className={styles.cardText}>{operatingLine(bar, now)}</p>
        <span className={styles.cardFooter}>영업 상태 변경 ›</span>
      </Link>
      {exception ? (
        <button
          type="button"
          className={styles.cancelException}
          aria-label="임시 휴무 취소"
          disabled={cancel.isPending}
          onClick={() => setAsking(true)}
        >
          ×
        </button>
      ) : null}
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
      <BottomSheet open={asking} title="임시 휴무를 취소할까요?" onClose={() => !cancel.isPending && setAsking(false)}>
        <p className={styles.sheetText}>정규 영업시간으로 돌아가요.</p>
        <div className={styles.actions}>
          <Button variant="secondary" disabled={cancel.isPending} onClick={() => setAsking(false)}>
            닫기
          </Button>
          <Button busy={cancel.isPending} onClick={confirm}>
            취소하기
          </Button>
        </div>
      </BottomSheet>
    </section>
  );
}

/**
 * The menu card (OwnerManagementHomeScreen.kt): how many items the published menu has (spec 3.9) and when it
 * was last updated, the later of its publish and its confirmation (3.6 `currentMenu`). While the count loads or
 * after it failed, the card says so.
 *
 * Below it, as in the app: days since that update ("메뉴 확인 N일 경과"), "지금도 맞아요" to confirm the menu is
 * still right (3.14.9), and a gauge full at 30 days. The confirmation goes with the `menuVersion` of the menu
 * counted here. A menu without items cannot be confirmed: the button gives way to a link to add one.
 */
function MenuCard({ bar }: { bar: BarDetail }) {
  const menu = useBarMenu(bar.barId);
  const now = useNow();
  const confirm = useConfirmMenu(bar.barId);
  const fail = useBarFailure();
  const [error, setError] = useState<string | null>(null);
  const [noMenu, setNoMenu] = useState(false);
  const items = menu.data?.items.length;
  const published = items !== undefined && items > 0 && !noMenu;
  const { days, percent } = published ? menuFreshness(bar.currentMenu, now) : { days: null, percent: 0 };
  // The card is one link, so a failed count is said here and retried on the menu screen it opens.
  const count = menu.data
    ? `게시된 메뉴 ${menu.data.items.length}개, `
    : menu.isError
      ? "메뉴 개수를 불러오지 못했어요, "
      : "게시된 메뉴 불러오는 중, ";

  async function confirmMenu() {
    if (!menu.data) return;
    setError(null);
    try {
      await confirm.send(menu.data.menuVersion);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "NO_PUBLISHED_MENU") return setNoMenu(true);
      if (failure instanceof ApiError && failure.code === "MENU_OUTDATED") {
        return setError("메뉴가 바뀌었어요. 바뀐 메뉴를 확인한 뒤 다시 눌러 주세요.");
      }
      setError(fail(failure));
    }
  }

  return (
    <section className={[styles.card, styles.wide].join(" ")} aria-label="메뉴 관리">
      <Link to={`/bars/${bar.barId}/menu`} className={styles.cardLink}>
        <h2 className={styles.cardTitle}>메뉴 관리</h2>
        {/* The app's "게시된 메뉴 N개 · 최근 갱신 MM.dd", with a comma for its middle dot. */}
        <p className={styles.cardText}>
          {count}최근 갱신 {menuDate(lastMenuUpdate(bar.currentMenu))}
        </p>
      </Link>
      <div className={styles.confirmRow}>
        <p className={styles.cardText}>
          메뉴 확인 <strong className={styles.age}>{days ?? "-"}</strong>
          {days === null ? " 미확인" : "일 경과"}
        </p>
        {published ? (
          <Button variant="secondary" busy={confirm.pending} onClick={() => void confirmMenu()}>
            지금도 맞아요
          </Button>
        ) : menu.data ? (
          <Link to={`/bars/${bar.barId}/menu`} className={styles.inlineLink}>
            메뉴 등록하기
          </Link>
        ) : null}
      </div>
      <div className={styles.gauge} role="progressbar" aria-label="메뉴 확인 경과" aria-valuemin={0} aria-valuemax={100} aria-valuenow={percent}>
        <span style={{ width: `${percent}%` }} />
      </div>
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
    </section>
  );
}

/**
 * A bar query in the five states (QueryView), where a bar that no longer exists (404 BAR_NOT_FOUND, spec 3.6)
 * offers the bar list instead of a retry.
 */
export function BarQuery<T>({
  query,
  keepDataOnRefetchError = false,
  children,
}: {
  query: Parameters<typeof QueryView<T>>[0]["query"];
  keepDataOnRefetchError?: boolean;
  children: (data: T) => React.ReactNode;
}) {
  if (query.error instanceof ApiError && query.error.code === "BAR_NOT_FOUND") {
    return <ErrorState message="매장을 찾을 수 없어요." action={<ButtonLink to="/bars">내 매장 목록으로</ButtonLink>} />;
  }
  return (
    <QueryView query={query} loadingMessage="매장 정보를 불러오고 있어요." keepDataOnRefetchError={keepDataOnRefetchError}>
      {children}
    </QueryView>
  );
}
