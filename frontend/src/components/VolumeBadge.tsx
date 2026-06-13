interface VolumeInfo {
  volume_ratio?: number | null;
  volume_confirmed?: boolean;
  volume_threshold?: number | null;
}

export default function VolumeBadge({ match }: { match: VolumeInfo }) {
  const ratio = match.volume_ratio;
  if (ratio == null) {
    return (
      <span
        style={{
          background: "rgba(0,0,0,0.05)",
          color: "var(--muted)",
          padding: "0.25rem 0.5rem",
          borderRadius: "4px",
          fontSize: "0.75rem",
          fontWeight: 500,
        }}
        title="No daily volume available — fetch volume on the NSE Stocks page"
      >
        Vol: n/a
      </span>
    );
  }

  const confirmed = Boolean(match.volume_confirmed);
  const threshold = match.volume_threshold ?? 1.5;

  return (
    <span
      style={{
        background: confirmed
          ? "color-mix(in srgb, var(--green) 12%, transparent)"
          : "rgba(148, 163, 184, 0.15)",
        color: confirmed ? "var(--green)" : "var(--muted)",
        padding: "0.25rem 0.5rem",
        borderRadius: "4px",
        fontSize: "0.75rem",
        fontWeight: 600,
      }}
      title={
        confirmed
          ? `Breakout volume confirmed: recent volume is ${ratio}× the 50-day average (threshold ${threshold}×)`
          : `Recent volume is ${ratio}× the 50-day average (below the ${threshold}× confirmation threshold)`
      }
    >
      {confirmed ? "✓ " : ""}Vol {ratio}× 50d
    </span>
  );
}
