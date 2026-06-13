import TimestampLabel from "./TimestampLabel";

export default function WidgetAsOf({ at }: { at: Date | null }) {
  if (!at) return null;
  return (
    <div className="widget-as-of">
      <TimestampLabel at={at} label="Fetched" />
    </div>
  );
}
