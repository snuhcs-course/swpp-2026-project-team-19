import { Link } from "react-router";
import { ApiError } from "../api/errors";
import { OwnerScreen } from "../owner/OwnerScreen";
import { useBar, type OwnedBar } from "../owner/queries";
import { ButtonLink } from "../ui/Button";
import { ErrorState } from "../ui/states";
import { QueryView } from "../ui/QueryView";
import styles from "./bar.module.css";

/**
 * /owner/bars/:barId: the bar's management home (android/.../ui/owner/OwnerManagementHomeScreen.kt), from
 * GET /api/bars/{barId} (spec 3.6). For now it opens the bar info editor; the operating status and the menu
 * cards hold their place until their tasks (I5-P6 to P8).
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
              {/* OwnerManagementHomeScreen.kt: a fixed line, not the values. */}
              <p className={styles.cardText}>사진 · 소개 · 영업시간</p>
              <span className={styles.cardFooter} aria-hidden="true">
                ›
              </span>
            </Link>
            <PlaceholderCard title="영업 상태 변경" />
            <PlaceholderCard title="메뉴 관리" wide />
          </div>
        )}
      </BarQuery>
    </OwnerScreen>
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
  children,
}: {
  query: Parameters<typeof QueryView<T>>[0]["query"];
  children: (data: T) => React.ReactNode;
}) {
  if (query.error instanceof ApiError && query.error.code === "BAR_NOT_FOUND") {
    return <ErrorState message="매장을 찾을 수 없어요." action={<ButtonLink to="/bars">내 매장 목록으로</ButtonLink>} />;
  }
  return (
    <QueryView query={query} loadingMessage="매장 정보를 불러오고 있어요.">
      {children}
    </QueryView>
  );
}
