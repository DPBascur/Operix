import { BarChart3 } from "lucide-react";

import { AppShell } from "@/components/layout/app-shell";
import { PageHeader } from "@/components/ui/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { StatusBadge } from "@/components/ui/status-badge";

export default function IndicatorsPage() {
  return (
    <AppShell activePath="/indicators">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
        <PageHeader
          description="Vista preparada para indicadores operacionales futuros. No hay datos persistidos ni histórico disponible."
          eyebrow="Seguimiento"
          title="Indicadores"
        />
        <SectionCard className="flex min-h-72 flex-col items-center justify-center text-center">
          <BarChart3
            aria-hidden="true"
            className="text-text-secondary"
            size={26}
          />
          <h2 className="mt-4 text-lg font-semibold">Sin indicadores reales</h2>
          <p className="mt-2 max-w-md text-sm leading-6 text-text-secondary">
            La estructura está lista para mostrar métricas cuando el Backend
            proporcione datos. Esta vista no representa un histórico de
            análisis.
          </p>
          <div className="mt-4">
            <StatusBadge tone="neutral">Sin histórico real</StatusBadge>
          </div>
        </SectionCard>
      </div>
    </AppShell>
  );
}
