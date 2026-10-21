import type { ReactNode } from "react";
const toneClasses = {
  accent: "bg-info/10 text-info",
  cyan: "bg-active/10 text-active",
  neutral: "bg-surface-muted text-text-secondary",
  success: "bg-success/10 text-success",
  warning: "bg-warning/10 text-warning",
  danger: "bg-danger/10 text-danger",
};
export function StatusBadge({
  children,
  tone = "neutral",
}: {
  children: ReactNode;
  tone?: keyof typeof toneClasses;
}) {
  return (
    <span className={`status-badge ${toneClasses[tone]}`}>{children}</span>
  );
}
