import { useEffect, useState } from "react";

/**
 * The current time, read again every 30 seconds while the screen is shown: the open status is computed in
 * the browser and changes while the page stays open (spec 3.15.5; the app's OwnerNowTicker.kt).
 */
export function useNow(intervalMs = 30_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs);
    return () => window.clearInterval(timer);
  }, [intervalMs]);
  return now;
}
