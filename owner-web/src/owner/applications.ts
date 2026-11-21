import { emptyDraft, hasPhotosToSend, type ApplicationDraft } from "../application/draft";
import { phoneDigits } from "../application/rules";
import type { MyApplications, OwnedBar } from "./queries";

/**
 * Rules of the owner's application list and bar list, ported from the Android app:
 * - android/.../ui/owner/OwnerRegistrationDashboard.kt: badges, the date line, which applications are shown.
 * - android/.../ui/owner/OwnerRegistrationProgress.kt `reapplicationDraftFromRejected`: reapplying.
 * - android/.../data/owner/OwnerMockModels.kt `hasPublishedInitialReview`: the bar badge.
 */
export type OwnerApplication = MyApplications["items"][number];
export type ApplicationStatus = OwnerApplication["status"];

export type BadgeTone = "pending" | "approved" | "rejected";

export interface Badge {
  label: string;
  tone: BadgeTone;
}

/** The status badge of an application card (OwnerRegistrationDashboard.kt). */
export function applicationBadge(status: ApplicationStatus): Badge {
  switch (status) {
    case "pending":
      return { label: "검토 중", tone: "pending" };
    case "rejected":
      return { label: "승인되지 않음", tone: "rejected" };
    case "approved":
      return { label: "승인됨", tone: "approved" };
    case "canceled":
      return { label: "취소됨", tone: "pending" };
  }
}

const SEOUL_MONTH_DAY = new Intl.DateTimeFormat("ko-KR", { timeZone: "Asia/Seoul", month: "numeric", day: "numeric" });

/** "M월 d일" in Seoul time, or null for a missing or unreadable time. */
export function seoulMonthDay(time: string | null | undefined): string | null {
  if (!time) return null;
  const date = new Date(time);
  if (Number.isNaN(date.getTime())) return null;
  const parts = SEOUL_MONTH_DAY.formatToParts(date);
  const month = parts.find((part) => part.type === "month")?.value;
  const day = parts.find((part) => part.type === "day")?.value;
  return month && day ? `${month}월 ${day}일` : null;
}

/**
 * The date line of an application card (OwnerRegistrationDashboard.kt): a rejection shows when it was reviewed,
 * everything else when it was sent. A date is never made up, and the sending date is never called a review date.
 */
export function applicationDateText(application: Pick<OwnerApplication, "status" | "createdAt" | "reviewedAt">): string {
  const reviewed = application.status === "rejected" ? seoulMonthDay(application.reviewedAt) : null;
  if (reviewed) return `${reviewed}에 검토했어요`;
  const sent = seoulMonthDay(application.createdAt);
  return sent ? `${sent}에 신청했어요` : "신청일 정보 없음";
}

/** The name an application is shown by: the claimed bar's, or the proposed new bar's. */
export function applicationBarName(application: Pick<OwnerApplication, "bar" | "proposedBar">): string {
  return application.proposedBar?.name ?? application.bar?.name ?? "";
}

/**
 * The applications shown on the status screen (OwnerRegistrationDashboard.kt `visible`): not those the owner
 * hid (only rejected ones can be hidden), and not an approval whose bar the owner manages now, since that
 * bar is on the bar list instead.
 */
export function visibleApplications<T extends Pick<OwnerApplication, "applicationId" | "status" | "bar">>(
  applications: readonly T[],
  bars: readonly Pick<OwnedBar, "barId">[],
  hidden: ReadonlySet<string>,
): T[] {
  return applications.filter((application) => {
    if (application.status === "rejected" && hidden.has(application.applicationId)) return false;
    if (application.status === "approved" && bars.some((bar) => bar.barId === application.bar?.barId)) return false;
    return true;
  });
}

/** Whether an application still needs the owner: a pending one, or a rejection they have not hidden. */
export function isOpenApplication(application: Pick<OwnerApplication, "applicationId" | "status">, hidden: ReadonlySet<string>): boolean {
  return application.status === "pending" || (application.status === "rejected" && !hidden.has(application.applicationId));
}

/**
 * Whether an approved application's bar is still managed by the owner. An ownership an operator ended
 * (spec 3.11.10) leaves the application approved but the bar off GET /api/me/bars.
 */
export function managesApprovedBar(application: Pick<OwnerApplication, "bar">, bars: readonly Pick<OwnedBar, "barId">[]): boolean {
  return bars.some((bar) => bar.barId === application.bar?.barId);
}

/**
 * A new application draft from a rejected one (OwnerRegistrationProgress.kt `reapplicationDraftFromRejected`),
 * starting at the intro. The rejected application itself is not changed: the owner sends a new one.
 *
 * - Photos are not carried over: rejection deletes them on the server (spec 3.11.8), and a server URL is for
 *   display only, never a file to upload again.
 * - The business check and the application ID start empty, so the new application is checked and sent anew.
 * - The server keeps one address line (the form joins address and detail), so it all goes in `address`.
 */
export function reapplicationDraft(application: OwnerApplication): ApplicationDraft {
  if (application.status !== "rejected") throw new Error("Only a rejected application can be sent again");
  const base: ApplicationDraft = {
    ...emptyDraft(),
    step: "intro",
    businessNumber: application.businessRegistrationNumber ?? "",
    representativeName: application.representativeName,
    openingDate: application.openingDate,
    contactPhone: phoneDigits(application.contactPhone),
  };
  if (application.applicationType === "existing_bar" && application.bar) {
    const { barId, name, address } = application.bar;
    return { ...base, kind: "existing_bar", existingBar: { barId, name, address }, proposedBarName: name };
  }
  return {
    ...base,
    kind: "new_bar",
    proposedBarName: application.proposedBar?.name ?? application.bar?.name ?? "",
    address: application.proposedBar?.address ?? "",
    storePhone: phoneDigits(application.proposedBar?.phone ?? ""),
  };
}

/**
 * Whether a saved draft is still worth resuming when the owner starts another application
 * (OwnerOnboardingScreen.kt `onRegister` resumes the saved draft). A draft whose application was already
 * sent is only kept for photos still to send to that pending application; once it is no longer pending
 * (canceled, rejected, approved), nothing is left to do with it and a new application starts.
 */
export function shouldResumeDraft(
  draft: ApplicationDraft | null,
  applications: readonly { applicationId: string; status: string }[],
): boolean {
  if (!draft) return false;
  if (draft.applicationId === null) return true;
  return hasPhotosToSend(draft, applications);
}

/**
 * The bar card badge (OwnerMockModels.kt `hasPublishedInitialReview`). The app checks for a published menu
 * import with menu items; the web reads only GET /api/me/bars, where a bar with a published menu has
 * `currentMenu` (spec 3.6). A newly approved bar has none until its first review is published.
 */
export function barBadge(bar: Pick<OwnedBar, "currentMenu">): Badge {
  return bar.currentMenu ? { label: "승인됨", tone: "approved" } : { label: "메뉴 확인 필요", tone: "pending" };
}
