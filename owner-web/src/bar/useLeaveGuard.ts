import { useCallback, useEffect, useRef } from "react";
import { useBlocker } from "react-router";

/**
 * Asks before leaving a form with unsaved edits (android/.../ui/owner/OwnerInfoHtmlV4Screen.kt `requestExit`
 * and its discard sheet). Moves inside the app (the back button, links, the browser's back) wait for the
 * sheet; closing or reloading the tab shows the browser's own prompt, whose text the page cannot set.
 *
 * `release()` lets the next move through without asking: after a save, or when the bar is gone.
 */
export function useLeaveGuard(dirty: boolean) {
  const released = useRef(false);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && !released.current && currentLocation.pathname + currentLocation.search !== nextLocation.pathname + nextLocation.search,
  );

  useEffect(() => {
    if (!dirty) return;
    const ask = (event: BeforeUnloadEvent) => {
      if (released.current) return;
      event.preventDefault();
      // Older browsers show the prompt only when returnValue is set.
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [dirty]);

  const release = useCallback(() => {
    released.current = true;
  }, []);

  return {
    /** A move is waiting for the owner's answer. */
    asking: blocker.state === "blocked",
    stay: () => blocker.reset?.(),
    leave: () => blocker.proceed?.(),
    release,
  };
}
