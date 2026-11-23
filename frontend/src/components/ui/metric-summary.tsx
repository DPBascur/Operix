import type { ReactNode } from "react";

export function MetricSummary({
  label,
  metrics,
}: {
  label: string;
  metrics: readonly { label: string; value: ReactNode }[];
}) {
  return (
    <section className="analysis-summary" aria-label={label}>
      {metrics.map((metric) => (
        <div key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value ?? "—"}</strong>
        </div>
      ))}
    </section>
  );
}
