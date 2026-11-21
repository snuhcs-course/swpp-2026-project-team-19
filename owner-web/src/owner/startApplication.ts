import { useCallback } from "react";
import { useNavigate } from "react-router";
import { clearDraft, loadDraft } from "../application/draft";
import { shouldResumeDraft } from "./applications";
import { useMe } from "./queries";

/**
 * "다른 매장 등록하기" (OwnerOnboardingScreen.kt `onRegister`): continues the saved draft where it stopped, or
 * starts a new application. A draft for an application that is no longer pending is dropped first
 * (`shouldResumeDraft`), or the form would reopen an application that can no longer take photos.
 *
 * While the applications are unknown (still loading, or failed), the draft is left as it is: it may hold the
 * only link to photos still to send to a pending application.
 */
export function useStartApplication(applications: readonly { applicationId: string; status: string }[] | undefined) {
  const navigate = useNavigate();
  const userId = useMe().data?.userId;
  return useCallback(() => {
    if (userId && applications) {
      const draft = loadDraft(userId);
      if (draft && !shouldResumeDraft(draft, applications)) clearDraft(userId);
    }
    void navigate("/apply");
  }, [navigate, userId, applications]);
}
