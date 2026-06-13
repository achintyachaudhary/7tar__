import type { ReactNode } from "react";
import TimestampLabel from "./TimestampLabel";

interface ScanCardFooterProps {
  lastScannedAt?: Date | null;
  extra?: ReactNode;
  children?: ReactNode;
}

export default function ScanCardFooter({
  lastScannedAt,
  extra,
  children,
}: ScanCardFooterProps) {
  return (
    <div
      className="scan-card-footer"
      style={{
        display: "flex",
        justifyContent: "space-between",
        alignItems: "center",
        marginTop: "auto",
        flexWrap: "wrap",
        gap: "0.5rem",
      }}
    >
      <div className="lt-section-timestamps">
        {lastScannedAt && <TimestampLabel at={lastScannedAt} label="Scan" />}
        {extra}
      </div>
      {children}
    </div>
  );
}
