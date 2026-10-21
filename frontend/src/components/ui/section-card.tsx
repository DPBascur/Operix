import type { ReactNode } from "react";

interface SectionCardProps {
  children: ReactNode;
  className?: string;
}

export function SectionCard({ children, className = "" }: SectionCardProps) {
  return (
    <section className={`surface-card min-w-0 p-5 sm:p-6 ${className}`}>
      {children}
    </section>
  );
}
