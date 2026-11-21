import { useState } from "react";
import { useNavigate } from "react-router";
import { hasPhotosToSend, loadDraft, saveDraft } from "../application/draft";
import { BottomSheet } from "../ui/BottomSheet";
import { Button, ButtonLink } from "../ui/Button";
import { EmptyState } from "../ui/states";
import { QueryView } from "../ui/QueryView";
import {
  applicationBadge,
  applicationBarName,
  applicationDateText,
  managesApprovedBar,
  reapplicationDraft,
  visibleApplications,
  type Badge,
  type OwnerApplication,
} from "./applications";
import { CancelApplicationSheet } from "./CancelApplicationSheet";
import { hideApplication, loadHiddenApplications } from "./hiddenApplications";
import { OwnerScreen } from "./OwnerScreen";
import { useMe, useMyApplications, useMyBars, type OwnedBar } from "./queries";
import { useStartApplication } from "./startApplication";
import styles from "./owner.module.css";

/**
 * /owner/applications: the owner's applications, newest first (spec 3.11.3), as the application cards of the
 * app's owner home (android/.../ui/owner/OwnerRegistrationDashboard.kt). The managed bars are on /bars.
 */
export function ApplicationsPage() {
  const userId = useMe().data?.userId ?? "";
  const bars = useMyBars();
  const applications = useMyApplications();
  const navigate = useNavigate();
  const startApplication = useStartApplication(applications.data?.items);
  const [hidden, setHidden] = useState(() => loadHiddenApplications(userId));
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [dismissId, setDismissId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  function reapply(application: OwnerApplication) {
    // The app saves the new draft over any saved one (OwnerOnboardingScreen.kt `onReapply`).
    saveDraft(userId, reapplicationDraft(application));
    void navigate("/apply/intro");
  }

  function dismiss() {
    if (dismissId) setHidden((current) => hideApplication(userId, dismissId, current));
    setDismissId(null);
  }

  return (
    <OwnerScreen title="등록 신청 상태" backTo={bars.data?.items.length ? "/bars" : undefined}>
      <QueryView query={bars} loadingMessage="신청 상태를 불러오고 있어요.">
        {(barData) => (
          <QueryView query={applications} loadingMessage="신청 상태를 불러오고 있어요.">
            {(applicationData) => {
              const shown = visibleApplications(applicationData.items, barData.items, hidden);
              const draft = loadDraft(userId);
              return (
                <div className={styles.screen}>
                  {notice ? (
                    <p className={styles.notice} role="status">
                      {notice}
                    </p>
                  ) : null}
                  {shown.length === 0 && barData.items.length > 0 ? (
                    // An owner whose approvals are all on the bar list: nothing open, but not a first application.
                    <EmptyState
                      title="진행 중인 신청이 없어요"
                      description="관리하는 매장은 내 매장 목록에서 볼 수 있어요."
                      action={<AddBarButton onClick={startApplication} />}
                    />
                  ) : shown.length === 0 ? (
                    <EmptyState
                      title="아직 신청한 매장이 없어요"
                      description="매장을 등록하면 운영팀이 확인한 뒤 승인해요."
                      action={<Button onClick={startApplication}>매장 등록 신청하기</Button>}
                    />
                  ) : (
                    <>
                      <ul className={styles.list} aria-label="신청 목록">
                        {shown.map((application) => (
                          <li key={application.applicationId}>
                            <ApplicationCard
                              application={application}
                              bars={barData.items}
                              photosToSend={hasPhotosToSend(draft, [application])}
                              onCancel={() => {
                                setNotice(null);
                                setCancelId(application.applicationId);
                              }}
                              onDismiss={() => setDismissId(application.applicationId)}
                              onReapply={() => reapply(application)}
                            />
                          </li>
                        ))}
                      </ul>
                      <AddBarButton onClick={startApplication} />
                    </>
                  )}
                  {barData.items.length > 0 ? <ButtonLink to="/bars">내 매장 목록으로</ButtonLink> : null}
                </div>
              );
            }}
          </QueryView>
        )}
      </QueryView>
      <CancelApplicationSheet applicationId={cancelId} onClose={() => setCancelId(null)} onNotice={setNotice} />
      <BottomSheet open={dismissId !== null} title="이 신청을 지울까요?" onClose={() => setDismissId(null)}>
        <p className={styles.sheetText}>같은 매장은 언제든 다시 신청할 수 있어요.</p>
        <div className={styles.actions}>
          <Button variant="secondary" onClick={() => setDismissId(null)}>
            닫기
          </Button>
          <Button onClick={dismiss}>지우기</Button>
        </div>
      </BottomSheet>
    </OwnerScreen>
  );
}

export function StatusBadge({ badge }: { badge: Badge }) {
  return <span className={[styles.badge, styles[badge.tone]].join(" ")}>{badge.label}</span>;
}

const STAGES = ["신청 완료", "운영팀 확인 중", "승인"] as const;

interface ApplicationCardProps {
  application: OwnerApplication;
  bars: readonly OwnedBar[];
  /** This browser still has photos to send for it (src/application/draft.ts `hasPhotosToSend`). */
  photosToSend: boolean;
  onCancel: () => void;
  onDismiss: () => void;
  onReapply: () => void;
}

function ApplicationCard({ application, bars, photosToSend, onCancel, onDismiss, onReapply }: ApplicationCardProps) {
  const name = applicationBarName(application);
  return (
    <article className={styles.card} aria-label={name}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>{name}</h2>
        <StatusBadge badge={applicationBadge(application.status)} />
      </div>
      <p className={styles.cardText}>{applicationDateText(application)}</p>
      {application.status === "pending" ? (
        <>
          <ol className={styles.stages} aria-label="진행 상황">
            {STAGES.map((stage, index) => (
              <li
                key={stage}
                className={[styles.stage, index === 0 ? styles.stageDone : index === 1 ? styles.stageCurrent : ""].join(" ")}
                aria-current={index === 1 ? "step" : undefined}
              >
                {stage}
              </li>
            ))}
          </ol>
          {photosToSend ? (
            <>
              <p className={styles.cardText}>아직 보내지 못한 사진이 있어요.</p>
              <ButtonLink to="/apply" variant="primary">
                남은 사진 보내기
              </ButtonLink>
            </>
          ) : null}
          <div className={styles.actions}>
            <ButtonLink to={`/applications/${application.applicationId}`}>신청 내용 보기</ButtonLink>
            <Button variant="secondary" onClick={onCancel}>
              신청 취소
            </Button>
          </div>
        </>
      ) : null}
      {application.status === "rejected" ? (
        <>
          {application.rejectionReason ? (
            <div className={styles.reason}>
              <p className={styles.reasonLabel}>운영팀이 남긴 이유</p>
              <p className={styles.reasonText}>{application.rejectionReason}</p>
            </div>
          ) : null}
          <div className={styles.actions}>
            <Button onClick={onReapply}>다시 신청하기</Button>
            <Button variant="secondary" onClick={onDismiss}>
              목록에서 지우기
            </Button>
          </div>
        </>
      ) : null}
      {application.status === "canceled" ? <p className={styles.cardText}>신청이 취소됐어요.</p> : null}
      {application.status === "approved" && !managesApprovedBar(application, bars) ? (
        <p className={styles.cardText}>지금은 이 매장의 관리 권한이 없어요.</p>
      ) : null}
    </article>
  );
}

/** "다른 매장 등록하기" under the cards (OwnerRegistrationDashboard.kt `registration-dashboard-add`). */
export function AddBarButton({ onClick }: { onClick: () => void }) {
  return (
    <Button variant="secondary" onClick={onClick}>
      <span aria-hidden="true">+</span>
      다른 매장 등록하기
    </Button>
  );
}
