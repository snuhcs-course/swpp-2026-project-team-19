import { useCallback, useEffect, useRef } from "react";
import { useBlocker } from "react-router";

/**
 * Asks before leaving a form with unsaved edits (android/.../ui/owner/OwnerInfoHtmlV4Screen.kt `requestExit`
 * and its discard sheet). Moves inside the app (the back button, links, the browser's back) wait for the
 * sheet; closing or reloading the tab shows the browser's own prompt, whose text the page cannot set.
 *
 * While `saving`, moves inside the app are refused without the sheet: the request cannot be taken back, so
 * "변경 취소" would only leave while the changes are saved anyway. Once the save ends the form moves on by
 * itself (success) or stays (failure).
 *
 * `release()` lets the next move through without asking: after a save, or when the bar is gone.
 */
export function useLeaveGuard(dirty: boolean, saving = false) {
  const released = useRef(false);
  // Read when a move starts, which may come between renders.
  const savingNow = useRef(saving);
  savingNow.current = saving;
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      (dirty || savingNow.current) &&
      !released.current &&
      currentLocation.pathname + currentLocation.search !== nextLocation.pathname + nextLocation.search,
  );

  // A move made while saving is dropped at once, so no sheet offers to discard what is being saved.
  const blocked = blocker.state === "blocked";
  useEffect(() => {
    if (blocked && saving) blocker.reset?.();
  }, [blocked, saving, blocker]);

  useEffect(() => {
    if (!dirty && !saving) return;
    const ask = (event: BeforeUnloadEvent) => {
      if (released.current) return;
      event.preventDefault();
      // Older browsers show the prompt only when returnValue is set.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [dirty, saving]);

  const release = useCallback(() => {
    released.current = true;
  }, []);

  return {
    /** A move is waiting for the owner's answer. */
    asking: blocked && !saving,
    stay: () => blocker.reset?.(),
    leave: () => blocker.proceed?.(),
    release,
  };
}
