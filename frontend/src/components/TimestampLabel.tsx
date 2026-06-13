import { formatIST, formatISTFromDate } from "../lib/formatTime";

interface TimestampLabelProps {
  at?: string | Date | null;
  label?: string;
  className?: string;
}

export default function TimestampLabel({
  at,
  label = "Updated",
  className = "timestamp-label",
}: TimestampLabelProps) {
  if (!at) return null;
  const text =
    at instanceof Date ? formatISTFromDate(at) : formatIST(at);
  if (text === "—") return null;

  return (
    <span className={className} title={`${label}: ${text}`}>
      {label}: <time dateTime={at instanceof Date ? at.toISOString() : at}>{text}</time>
    </span>
  );
}
