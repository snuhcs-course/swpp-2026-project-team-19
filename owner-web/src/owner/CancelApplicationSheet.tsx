import { useState } from "react";
import { ApiError, errorMessage } from "../api/errors";
import { BottomSheet } from "../ui/BottomSheet";
import { Button } from "../ui/Button";
import { useCancelApplication } from "./queries";
import styles from "./owner.module.css";

export const CANCELED_NOTICE = "신청을 취소했어요.";
export const CANCEL_NOT_FOUND_NOTICE = "신청을 찾지 못했어요. 신청 목록을 새로 불러왔어요.";
export const CANCEL_STATE_CHANGED_NOTICE = "신청 상태가 바뀌어 취소하지 못했어요. 지금 상태를 다시 불러왔어요.";

interface CancelApplicationSheetProps {
  /** The application to cancel; the sheet is open while this is set. */
  applicationId: string | null;
  onClose: () => void;
  /** Called with what to tell the owner once the sheet has closed. */
  onNotice: (message: string) => void;
}

/**
 * "신청을 취소할까요?" (android/.../ui/owner/OwnerRegistrationExceptionV4.kt `RegistrationApplicationConfirmSheet`,
 * CANCEL), then POST .../cancel with the error handling of spec 3.11.5. A failure that retrying may fix keeps
 * the sheet open with its message; 404 and 409 close it, since the refreshed list or application shows why.
 */
export function CancelApplicationSheet({ applicationId, onClose, onNotice }: CancelApplicationSheetProps) {
  const cancel = useCancelApplication();
  const [error, setError] = useState<string | null>(null);
  const busy = cancel.isPending;

  function close() {
    if (busy) return;
    setError(null);
    onClose();
  }

  function confirm() {
    if (!applicationId || busy) return;
    setError(null);
    cancel.mutate(applicationId, {
      onSuccess: () => {
        onClose();
        onNotice(CANCELED_NOTICE);
      },
      onError: (failure) => {
        const code = failure instanceof ApiError ? failure.code : null;
        if (code === "OWNER_APPLICATION_NOT_FOUND" || code === "INVALID_APPLICATION_STATE") {
          onClose();
          onNotice(code === "OWNER_APPLICATION_NOT_FOUND" ? CANCEL_NOT_FOUND_NOTICE : CANCEL_STATE_CHANGED_NOTICE);
          return;
        }
        setError(errorMessage(failure));
      },
    });
  }

  return (
    <BottomSheet open={applicationId !== null} title="신청을 취소할까요?" onClose={close}>
      <p className={styles.sheetText}>취소하면 처음부터 다시 신청해야 해요.</p>
      {error ? (
        <p className={styles.error} role="alert">
          {error}
        </p>
      ) : null}
      <div className={styles.actions}>
        <Button variant="secondary" disabled={busy} onClick={close}>
          닫기
        </Button>
        <Button busy={busy} onClick={confirm}>
          취소하기
        </Button>
      </div>
    </BottomSheet>
  );
}
