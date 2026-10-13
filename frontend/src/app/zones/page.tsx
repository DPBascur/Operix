import { Map } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";
import { PageHeader } from "@/components/ui/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

export default function ZonesPage() {
  return (
    <AppShell activePath="/zones">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
        <PageHeader
          description="Espacio de demostración para la futura definición espacial de zonas."
          eyebrow="Configuración"
          title="Zonas"
        />
        <MockDataNotice />
        <SectionCard>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <h2 className="text-lg font-semibold">Espacio de definición</h2>
            <StatusBadge tone="neutral">Sin video conectado</StatusBadge>
          </div>
          <div className="mt-5 flex min-h-72 items-center justify-center rounded-panel border border-dashed border-border bg-surface-muted p-6 text-center">
            <div className="max-w-sm">
              <Map
                aria-hidden="true"
                className="mx-auto text-text-secondary"
                size={26}
              />
              <p className="mt-3 font-semibold">Lienzo de zonas pendiente</p>
              <p className="mt-2 text-sm leading-6 text-text-secondary">
                Aquí se delimitarán las áreas operacionales cuando exista un
                video conectado. No hay zonas editables ni persistidas en esta
                vista.
              </p>
            </div>
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
