import type { IpoLlmFetchStatus } from "../types/ipoResearch";

const LABELS: Record<IpoLlmFetchStatus, string> = {
  pending: "Pending",
  fetching: "Fetching…",
  fetched: "Fetched",
  failed: "Failed",
};

interface IpoStatusBadgeProps {
  status: IpoLlmFetchStatus;
}

export default function IpoStatusBadge({ status }: IpoStatusBadgeProps) {
  return (
    <span className={`ipo-status-badge ipo-status-${status}`}>
      {LABELS[status]}
    </span>
  );
}
