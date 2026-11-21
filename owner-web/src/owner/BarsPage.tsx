import { useState } from "react";
import { Button, ButtonLink } from "../ui/Button";
import { EmptyState } from "../ui/states";
import { QueryView } from "../ui/QueryView";
import { barBadge, isOpenApplication } from "./applications";
import { AddBarButton, StatusBadge } from "./ApplicationsPage";
import { loadHiddenApplications } from "./hiddenApplications";
import { OwnerScreen } from "./OwnerScreen";
import { useMe, useMyApplications, useMyBars } from "./queries";
import { useStartApplication } from "./startApplication";
import styles from "./owner.module.css";

/**
 * /owner/bars: the bars this owner manages, by name (spec 3.11.9), as the bar cards of the app's owner home
 * (android/.../ui/owner/OwnerRegistrationDashboard.kt). Choosing one opens /bars/:barId. Applications are on
 * /applications; this screen links there while one is open.
 */
export function BarsPage() {
  const userId = useMe().data?.userId;
  const bars = useMyBars();
  const applications = useMyApplications();
  const startApplication = useStartApplication(applications.data?.items);
  const [hidden] = useState(() => loadHiddenApplications(userId));
  // The bars do not wait for the applications: they only add a link, and fall back to it while unknown.
  const open = applications.data?.items.filter((application) => isOpenApplication(application, hidden)).length;

  return (
    <OwnerScreen title="내 매장">
      <QueryView
        query={bars}
        loadingMessage="매장 목록을 불러오고 있어요."
        isEmpty={(data) => data.items.length === 0}
        empty={
          <EmptyState
            title="아직 관리하는 매장이 없어요"
            description="운영팀이 신청을 승인하면 여기에서 매장을 관리할 수 있어요."
            action={
              applications.data?.items.length === 0 ? (
                <Button onClick={startApplication}>매장 등록 신청하기</Button>
              ) : (
                <ButtonLink to="/applications" variant="primary">
                  신청 현황 보기
                </ButtonLink>
              )
            }
          />
        }
      >
        {(data) => (
          <div className={styles.screen}>
            <ul className={styles.list} aria-label="내 매장 목록">
              {data.items.map((bar) => (
                <li key={bar.barId}>
                  <article className={styles.card} aria-label={bar.name}>
                    <div className={styles.cardHead}>
                      <h2 className={styles.cardTitle}>{bar.name}</h2>
                      <StatusBadge badge={barBadge(bar)} />
                    </div>
                    <p className={styles.cardText}>{bar.address}</p>
                    <div className={styles.actions}>
                      <ButtonLink to={`/bars/${bar.barId}`} variant="primary">
                        매장 관리하기
                      </ButtonLink>
                    </div>
                  </article>
                </li>
              ))}
            </ul>
            {open ? <ButtonLink to="/applications">{`신청 현황 ${open}건`}</ButtonLink> : null}
            <AddBarButton onClick={startApplication} />
          </div>
        )}
      </QueryView>
    </OwnerScreen>
  );
}
