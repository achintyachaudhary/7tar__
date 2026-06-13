import { useEffect, useRef } from "react";
import { useNseSessionOpen } from "../lib/nseSession";

/** Run `fn` immediately and on an interval that tightens during the NSE session.
 *
 * During market hours data should feel live (default every 60s); after close
 * a slow heartbeat keeps end-of-day values from going stale on long-lived tabs.
 */
export function useLiveRefresh(
  fn: () => void | Promise<void>,
  { liveMs = 60_000, closedMs = 5 * 60_000 }: { liveMs?: number; closedMs?: number } = {},
): boolean {
  const sessionOpen = useNseSessionOpen();
  const fnRef = useRef(fn);
  fnRef.current = fn;

  useEffect(() => {
    void fnRef.current();
    const id = window.setInterval(
      () => void fnRef.current(),
      sessionOpen ? liveMs : closedMs,
    );
    return () => window.clearInterval(id);
  }, [sessionOpen, liveMs, closedMs]);

  return sessionOpen;
}
