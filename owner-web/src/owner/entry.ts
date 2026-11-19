/**
 * Which screen an owner starts on, from their bars (GET /api/me/bars) and applications
 * (GET /api/me/owner-applications). Ported from the Android app:
 * - android/.../ui/auth/AccountScreens.kt (My Page): bars first, then a pending or rejected application.
 * - android/.../ui/owner/OwnerOnboardingScreen.kt `shouldAutoOpenOwnerRegistrationIntro` and its test
 *   OwnerEntryRoutingTest.kt: an owner whose data has not arrived yet is never sent to registration.
 */
export type OwnerEntry =
  /** Bars or applications are still loading: show loading, never the registration screen. */
  | "loading"
  /** At least one approved bar, whatever the applications say: the managed-bar list. */
  | "bars"
  /** No bar yet, and an application that is pending or was rejected: the application status. */
  | "application"
  /** Nothing to show yet (no application, only canceled ones, or an approval whose ownership ended): apply. */
  | "apply";

export type ApplicationStatus = "pending" | "approved" | "rejected" | "canceled";

export function ownerEntry(
  bars: readonly unknown[] | undefined,
  applications: readonly { status: ApplicationStatus }[] | undefined,
): OwnerEntry {
  if (bars === undefined || applications === undefined) return "loading";
  if (bars.length > 0) return "bars";
  if (applications.some((application) => application.status === "pending" || application.status === "rejected")) {
    return "application";
  }
  return "apply";
}
