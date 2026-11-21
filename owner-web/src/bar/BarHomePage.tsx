import { useState } from "react";
import { Link } from "react-router";
import { ApiError } from "../api/errors";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useBar, useCancelException, type BarDetail, type OwnedBar } from "../owner/queries";
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
 * the menu card, which holds its place until its tasks (I5-P7, P8).
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
            <PlaceholderCard title="메뉴 관리" wide />
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

function PlaceholderCard({ title, wide = false }: { title: string; wide?: boolean }) {
  return (
    <section className={[styles.card, styles.unavailable, wide ? styles.wide : ""].join(" ")} aria-label={title}>
      <h2 className={styles.cardTitle}>{title}</h2>
      <p className={styles.cardText}>웹에서는 준비 중이에요.</p>
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
