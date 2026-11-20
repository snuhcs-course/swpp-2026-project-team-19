import type { ApplicationKind } from "./rules";
import { isCheckpoint, isStepId, type StepId } from "./steps";

/**
 * An application in progress, kept in localStorage per account so a reload or a later visit continues it,
 * as the app keeps its registration draft (android/.../data/owner/OwnerMockModels.kt MockRegistrationDraft).
 *
 * Only typed values are kept. Photos stay in memory: localStorage holds a few MB, not 15 photos, so after a
 * reload the owner picks them again. The draft is removed once the application is sent, and when the owner
 * signs out, so business details do not stay on a shared computer.
 */
export interface ApplicationDraft {
  version: 1;
  step: StepId;
  inputMethod: "photo" | "manual";
  kind: ApplicationKind;
  existingBar: { barId: string; name: string; address: string } | null;
  businessNumber: string;
  representativeName: string;
  openingDate: string;
  proposedBarName: string;
  address: string;
  addressDetail: string;
  storePhone: string;
  contactPhone: string;
  /** The last business check (spec 3.11.16) and the three values it was for (businessVerificationKey). */
  verification: Verification | null;
  /** Set once POST /api/owner-applications succeeded: photo uploads that failed are retried for it. */
  applicationId: string | null;
  uploaded: { cover: boolean; menus: boolean };
}

export interface Verification {
  key: string;
  result: "matched" | "not_matched" | "unavailable" | "limited";
  /** When the daily limit resets (RFC 3339), for "limited". */
  retryAfter: string | null;
}

/**
 * Whether the draft is an application already sent whose photos are not all uploaded yet, and that
 * application is still pending: only the form can send them, so the owner is taken back to it.
 */
export function hasPhotosToSend(
  draft: ApplicationDraft | null,
  applications: readonly { applicationId: string; status: string }[],
): boolean {
  if (!draft?.applicationId || draft.uploaded.menus) return false;
  return applications.some((application) => application.applicationId === draft.applicationId && application.status === "pending");
}

export function emptyDraft(): ApplicationDraft {
  return {
    version: 1,
    step: "intro",
    inputMethod: "manual",
    kind: "new_bar",
    existingBar: null,
    businessNumber: "",
    representativeName: "",
    openingDate: "",
    proposedBarName: "",
    address: "",
    addressDetail: "",
    storePhone: "",
    contactPhone: "",
    verification: null,
    applicationId: null,
    uploaded: { cover: false, menus: false },
  };
}

const PREFIX = "bottlemap-owner-web-application-draft:";
const keyFor = (userId: string) => PREFIX + userId;

export function loadDraft(userId: string): ApplicationDraft | null {
  try {
    const raw = localStorage.getItem(keyFor(userId));
    if (!raw) return null;
    const parsed = JSON.parse(raw) as Partial<ApplicationDraft>;
    if (parsed.version !== 1 || !isStepId(parsed.step)) return null;
    const draft = { ...emptyDraft(), ...parsed } as ApplicationDraft;
    return { ...draft, step: isCheckpoint(draft.step) ? draft.step : "intro" };
  } catch {
    return null;
  }
}

export function saveDraft(userId: string, draft: ApplicationDraft): void {
  try {
    localStorage.setItem(keyFor(userId), JSON.stringify(draft));
  } catch {
    // Not kept (private mode, full or blocked storage): the application still works for this visit.
  }
}

export function clearDraft(userId: string): void {
  try {
    localStorage.removeItem(keyFor(userId));
  } catch {
    // Nothing was kept.
  }
}

/** Removes every account's draft on this browser (on sign-out). */
export function clearAllDrafts(): void {
  try {
    for (const key of Object.keys(localStorage)) if (key.startsWith(PREFIX)) localStorage.removeItem(key);
  } catch {
    // Nothing was kept.
  }
}
