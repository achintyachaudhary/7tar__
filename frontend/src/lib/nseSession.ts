import { useEffect, useState } from "react";

const IST = "Asia/Kolkata";

/** NSE regular (continuous) equity session (matches backend live_trading.py). */
export const NSE_SESSION_LABEL = "09:15–15:30 IST";
/** Pre-open auction: orders till ~09:08, first prints from ~09:07. */
export const NSE_PRE_OPEN_LABEL = "09:00–09:15 IST";

export type NseSessionPhase = "pre_open" | "open" | "closed";

function istParts(ref: Date) {
  const parts = new Intl.DateTimeFormat("en-IN", {
    timeZone: IST,
    weekday: "short",
    hour: "numeric",
    minute: "numeric",
    hour12: false,
  }).formatToParts(ref);

  return {
    weekday: parts.find((p) => p.type === "weekday")?.value ?? "",
    hour: Number(parts.find((p) => p.type === "hour")?.value ?? 0),
    minute: Number(parts.find((p) => p.type === "minute")?.value ?? 0),
  };
}

export function getNseSessionPhase(ref = new Date()): NseSessionPhase {
  const { weekday, hour, minute } = istParts(ref);
  if (weekday === "Sat" || weekday === "Sun") return "closed";
  const mins = hour * 60 + minute;
  const preOpen = 9 * 60;
  const open = 9 * 60 + 15;
  const close = 15 * 60 + 30;
  if (mins >= preOpen && mins < open) return "pre_open";
  if (mins >= open && mins <= close) return "open";
  return "closed";
}

/** Live prices exist on the exchange — pre-open (from 9:00) or regular session. */
export function isNseSessionOpen(ref = new Date()): boolean {
  return getNseSessionPhase(ref) !== "closed";
}

/** Re-checks every 30s so session banners flip at 9:00/9:15/15:30 without a refresh. */
export function useNseSessionPhase(intervalMs = 30_000): NseSessionPhase {
  const [phase, setPhase] = useState<NseSessionPhase>(() => getNseSessionPhase());

  useEffect(() => {
    const tick = () => setPhase(getNseSessionPhase());
    tick();
    const id = window.setInterval(tick, intervalMs);
    return () => window.clearInterval(id);
  }, [intervalMs]);

  return phase;
}

export function useNseSessionOpen(intervalMs = 30_000): boolean {
  return useNseSessionPhase(intervalMs) !== "closed";
}
