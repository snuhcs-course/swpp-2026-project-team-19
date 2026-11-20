import type { ApplicationKind } from "./rules";

/**
 * The application's screens, in the order of the Android flow (android/.../ui/owner/OwnerOnboardingScreen.kt
 * RegPage) and its saved path (OwnerRegistrationProgress.kt). Each is a URL under /apply/.
 */
export type StepId =
  | "intro"
  | "method"
  | "reading"
  | "number"
  | "representative"
  | "opening-date"
  | "check"
  | "result"
  | "bar-name"
  | "cover"
  | "address"
  | "bar-phone"
  | "menus"
  | "contact"
  | "review"
  | "done";

const COMMON: StepId[] = ["intro", "method", "number", "representative", "opening-date", "check", "result", "bar-name"];
const NEW_BAR: StepId[] = ["cover", "address", "bar-phone"];
const END: StepId[] = ["menus", "contact", "review"];

export const ALL_STEPS: readonly StepId[] = [...COMMON.slice(0, 2), "reading", ...COMMON.slice(2), ...NEW_BAR, ...END, "done"];

export function isStepId(value: string | undefined): value is StepId {
  return value !== undefined && (ALL_STEPS as readonly string[]).includes(value);
}

/** Steps a draft can be resumed at (registrationCheckpointable). */
export function isCheckpoint(step: StepId): boolean {
  return [...COMMON, ...NEW_BAR, ...END].includes(step);
}

/** The steps before `step` on the way to it (registrationHistoryFor): an existing bar skips the new-bar details. */
export function stepsBefore(step: StepId, kind: ApplicationKind): StepId[] {
  const path = [...COMMON, ...(kind === "new_bar" ? NEW_BAR : []), ...END];
  const index = path.indexOf(step);
  return index <= 0 ? [] : path.slice(0, index);
}

/** The progress stage shown above a step: 1 business, 2 bar, 3 menu photos, 4 review (regStage). */
export function stageOf(step: StepId): 0 | 1 | 2 | 3 | 4 {
  if (["method", "reading", "number", "representative", "opening-date", "check", "result"].includes(step)) return 1;
  if (["bar-name", "cover", "address", "bar-phone"].includes(step)) return 2;
  if (step === "menus") return 3;
  if (step === "contact" || step === "review") return 4;
  return 0;
}

export const STAGE_TITLES = ["사업자 정보", "매장 정보", "메뉴판", "확인"] as const;
