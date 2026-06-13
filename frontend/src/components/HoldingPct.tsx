export function fmtHolding(v: number | null | undefined): string {
  if (v == null) return "—";
  return `${v.toFixed(2)}%`;
}

interface HoldingPctProps {
  value: number | null | undefined;
}

export default function HoldingPct({ value }: HoldingPctProps) {
  return <span>{fmtHolding(value)}</span>;
}
