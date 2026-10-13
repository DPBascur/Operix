import {
  Activity,
  AlertTriangle,
  Clock3,
  Eye,
  Radio,
  Video,
} from "lucide-react";
import Link from "next/link";

import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";
import { PageHeader } from "@/components/ui/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";
import { DashboardGreeting } from "@/features/dashboard/dashboard-greeting";
import {
  mockCurrentUser,
  mockDashboardMetrics,
  mockRecentEvents,
} from "@/mocks/ui-data";

const metricIcons = {
  duration: Clock3,
  events: AlertTriangle,
  objects: Eye,
  streams: Video,
};
const metricTones = {
  streams: "bg-brand-accent/10 text-accent",
  objects: "bg-active/10 text-active",
  events: "bg-warning/10 text-warning",
  duration: "bg-surface-muted text-text-secondary",
};

export default function HomePage() {
  return (
    <AppShell activePath="/">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
        <PageHeader
          action={
            <StatusBadge tone="neutral">
              <Radio aria-hidden="true" size={13} />
              Sin análisis activo
            </StatusBadge>
          }
          description="Resumen del estado actual de Operix con datos simulados."
          eyebrow="Dashboard"
          title={<DashboardGreeting name={mockCurrentUser.displayName} />}
        />

        <MockDataNotice />

        <section
          aria-label="Resumen del análisis"
          className="grid grid-cols-2 gap-4 xl:grid-cols-4"
        >
          {mockDashboardMetrics.map(({ key, label, value }) => {
            const Icon = metricIcons[key];
            return (
              <article
                className="surface-card rounded-card border border-border bg-surface-elevated p-5 shadow-card"
                key={key}
              >
                <div className="flex items-start justify-between gap-4">
                  <span
                    className={`flex size-10 items-center justify-center rounded-control ${metricTones[key]}`}
                  >
                    <Icon aria-hidden="true" size={20} />
                  </span>
                </div>
                <p className="mt-5 text-2xl font-bold tabular-nums sm:text-3xl tracking-tight text-foreground">
                  {value}
                </p>
                <p className="mt-1 text-sm text-text-secondary">{label}</p>
              </article>
            );
          })}
        </section>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(22rem,0.7fr)]">
          <SectionCard>
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">
                  Vista de análisis
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  Representación visual con datos simulados.
                </p>
              </div>
              <StatusBadge tone="accent">Mock</StatusBadge>
            </div>
            <div className="relative mt-5 aspect-video w-full min-h-56 overflow-hidden rounded-panel bg-brand-dark">
              <div className="absolute inset-6 rounded-card border border-border/15 bg-brand-primary/55" />
              <div className="absolute left-[18%] top-[24%] h-[36%] w-[14%] rounded-control border-2 border-brand-cyan" />
              <div className="absolute left-[58%] top-[32%] h-[42%] w-[16%] rounded-control border-2 border-brand-accent" />
              <div className="absolute inset-x-[12%] bottom-[12%] h-[30%] border-2 border-brand-cyan/80 bg-brand-cyan/10 [clip-path:polygon(8%_0,100%_22%,76%_100%,25%_100%)]" />
              <div className="absolute bottom-4 left-4 rounded-control bg-brand-dark/80 px-3 py-2 text-xs text-brand-neutral">
                CAM-01 · Escenario de prueba
              </div>
              <div className="absolute right-4 top-4">
                <span className="rounded-full bg-brand-dark/80 px-2.5 py-1 text-xs font-semibold text-brand-cyan">
                  Vista simulada
                </span>
              </div>
            </div>
          </SectionCard>

          <SectionCard>
            <div className="flex items-center justify-between gap-4">
              <div>
                <h2 className="text-lg font-semibold text-foreground">
                  Candidatos recientes
                </h2>
                <p className="mt-1 text-sm text-text-secondary">
                  Datos locales para diseño.
                </p>
              </div>
              <Link
                className="text-sm font-semibold text-accent hover:underline"
                href="/events"
              >
                Ver todos
              </Link>
            </div>
            <div className="mt-4 divide-y divide-border">
              {mockRecentEvents.map(
                ({ id, title, detail, time, status, tone }) => (
                  <article
                    className="flex items-center gap-3 py-4 first:pt-0 last:pb-0"
                    key={id}
                  >
                    <span className="flex size-10 shrink-0 items-center justify-center rounded-control bg-brand-accent/10 text-accent">
                      <Activity aria-hidden="true" size={18} />
                    </span>
                    <div className="min-w-0 flex-1">
                      <h3 className="line-clamp-2 text-sm font-semibold text-foreground">
                        {title}
                      </h3>
                      <p className="mt-1 truncate text-xs text-text-secondary">
                        {detail}
                      </p>
                    </div>
                    <div className="text-right">
                      <StatusBadge tone={tone}>{status}</StatusBadge>
                      <time className="mt-1 block text-xs text-text-secondary">
                        {time}
                      </time>
                    </div>
                  </article>
                ),
              )}
            </div>
          </SectionCard>
        </div>
      </div>
    </AppShell>
  );
}
