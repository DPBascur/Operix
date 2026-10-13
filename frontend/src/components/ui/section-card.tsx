import type { ReactNode } from "react";

interface SectionCardProps {
  children: ReactNode;
  className?: string;
}

export function SectionCard({ children, className = "" }: SectionCardProps) {
  return (
    <section
      className={`surface-card min-w-0 rounded-card border p-5 shadow-card sm:p-6 border-border bg-surface-elevated ${className}`}
    >
      {children}
    </section>
  );
}
