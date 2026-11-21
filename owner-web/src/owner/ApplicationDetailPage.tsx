import { useState } from "react";
import { useParams } from "react-router";
import { ApiError } from "../api/errors";
import { SummaryRow } from "../application/parts";
import { formatBusinessNumber, formatOwnerPhone } from "../application/rules";
import { Button, ButtonLink } from "../ui/Button";
import { ErrorState } from "../ui/states";
import { QueryView } from "../ui/QueryView";
import { applicationBadge, applicationBarName, applicationDateText } from "./applications";
import { StatusBadge } from "./ApplicationsPage";
import { CancelApplicationSheet } from "./CancelApplicationSheet";
import { OwnerScreen } from "./OwnerScreen";
import { useOwnerApplication, type OwnerApplicationDetail } from "./queries";
import styles from "./owner.module.css";

/**
 * /owner/applications/:applicationId: what the owner sent, read-only (spec 3.11.4), as the app's
 * "신청한 내용" (android/.../ui/owner/OwnerOnboardingScreen.kt `RegPage.VIEW_APPLICATION`). Photos are
 * shown as counts, as in the app.
 */
export function ApplicationDetailPage() {
  const { applicationId = "" } = useParams();
  const application = useOwnerApplication(applicationId);
  const [cancelId, setCancelId] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  // Missing, someone else's, or not a UUID all answer 404 (spec 3.11.4): asking again cannot change it.
  const notFound = application.error instanceof ApiError && application.error.code === "OWNER_APPLICATION_NOT_FOUND";
  return (
    <OwnerScreen title="신청한 내용" backTo="/applications">
      {notFound ? (
        <ErrorState message="신청을 찾지 못했어요." action={<ButtonLink to="/applications">신청 목록으로</ButtonLink>} />
      ) : (
        <QueryView query={application} loadingMessage="신청 내용을 불러오고 있어요.">
          {(data) => (
            <ApplicationDetails
              application={data}
              notice={notice}
              onCancel={() => {
                setNotice(null);
                setCancelId(data.applicationId);
              }}
            />
          )}
        </QueryView>
      )}
      <CancelApplicationSheet applicationId={cancelId} onClose={() => setCancelId(null)} onNotice={setNotice} />
    </OwnerScreen>
  );
}

function ApplicationDetails({
  application,
  notice,
  onCancel,
}: {
  application: OwnerApplicationDetail;
  notice: string | null;
  onCancel: () => void;
}) {
  const newBar = application.applicationType === "new_bar";
  const pending = application.status === "pending";
  const count = (n: number) => (n > 0 ? `${n}장` : "없음");
  return (
    <div className={styles.screen}>
      {notice ? (
        <p className={styles.notice} role="status">
          {notice}
        </p>
      ) : null}
      <div className={styles.cardHead}>
        <p className={styles.cardText}>{applicationDateText(application)}</p>
        <StatusBadge badge={applicationBadge(application.status)} />
      </div>
      {pending ? <p className={styles.cardText}>검토 중에는 내용을 수정할 수 없어요.</p> : null}
      {application.status === "rejected" && application.rejectionReason ? (
        <div className={styles.reason}>
          <p className={styles.reasonLabel}>운영팀이 남긴 이유</p>
          <p className={styles.reasonText}>{application.rejectionReason}</p>
        </div>
      ) : null}
      <Section title="사업자 정보">
        <SummaryRow label="등록번호" value={formatBusinessNumber(application.businessRegistrationNumber ?? "")} />
        <SummaryRow label="대표자" value={application.representativeName} />
        <SummaryRow label="개업일" value={application.openingDate.replaceAll("-", ".")} />
      </Section>
      <Section title="매장 정보">
        <SummaryRow label="이름" value={applicationBarName(application)} />
        {newBar ? (
          <>
            <SummaryRow label="대표 사진" value={count(application.coverPhoto ? 1 : 0)} />
            <SummaryRow label="주소" value={application.proposedBar?.address ?? ""} />
            <SummaryRow label="매장 전화" value={formatOwnerPhone(application.proposedBar?.phone ?? "")} />
          </>
        ) : null}
      </Section>
      <Section title="메뉴판">
        <SummaryRow label="메뉴판 사진" value={count(application.menuPhotos.length)} />
      </Section>
      <Section title="연락처">
        <SummaryRow label="연락받을 번호" value={formatOwnerPhone(application.contactPhone)} />
      </Section>
      {pending ? (
        <Button variant="secondary" onClick={onCancel}>
          신청 취소
        </Button>
      ) : null}
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className={styles.section} aria-label={title}>
      <h2 className={styles.sectionTitle}>{title}</h2>
      {children}
    </section>
  );
}
