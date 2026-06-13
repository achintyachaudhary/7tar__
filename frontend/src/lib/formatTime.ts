/** IST timestamps used across the app. */

const IST_OPTS: Intl.DateTimeFormatOptions = {
  timeZone: "Asia/Kolkata",
  dateStyle: "medium",
  timeStyle: "short",
};

export function formatIST(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-IN", IST_OPTS);
}

export function formatISTFromDate(date: Date | null | undefined): string {
  if (!date || Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-IN", IST_OPTS);
}

export function formatISTDateOnly(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", dateStyle: "medium" });
}
