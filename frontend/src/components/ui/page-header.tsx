import type { ReactNode } from "react";

interface PageHeaderProps {
  action?: ReactNode;
  description: string;
  title: ReactNode;
}

export function PageHeader({ action, description, title }: PageHeaderProps) {
  return (
    <header className="page-header">
      <div className="max-w-2xl">
        <h1 className="page-title">{title}</h1>
        <p className="page-description">{description}</p>
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}
