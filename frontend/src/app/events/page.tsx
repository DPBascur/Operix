import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";
import { PageHeader } from "@/components/ui/page-header";
import { SectionCard } from "@/components/ui/section-card";
import { EventsTable } from "@/features/events/events-table";
import { environment } from "@/config/environment";

export default function EventsPage() {
  return (
    <AppShell activePath="/events">
      <div className="mx-auto max-w-7xl space-y-6 px-4 py-6 sm:px-6 sm:py-8 lg:px-8 lg:py-10">
        <PageHeader
          description={
            environment.dataSource === "api"
              ? "Consulta los eventos técnicos registrados por la API."
              : "Explora los candidatos generados por los datos de demostración del frontend."
          }
          eyebrow="Monitoreo"
          title="Eventos"
        />
        {environment.dataSource === "mock" ? (
          <MockDataNotice />
        ) : (
          <p className="text-sm text-text-secondary">
            Datos persistidos de la API local. No implican procesamiento de
            video en tiempo real.
          </p>
        )}
        <SectionCard>
          <EventsTable />
        </SectionCard>
      </div>
    </AppShell>
  );
}
