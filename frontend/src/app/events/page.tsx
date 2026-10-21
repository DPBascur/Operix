import { AppShell } from "@/components/layout/app-shell";
import { MockDataNotice } from "@/components/ui/mock-data-notice";
import { environment } from "@/config/environment";
import { EventsTable } from "@/features/events/events-table";

export default function EventsPage() {
  return (
    <AppShell activePath="/events">
      <div className="page-wrap operational-page">
        <header className="compact-page-header">
          <div>
            <h2 className="compact-page-title">Investigación de eventos</h2>
            <p className="compact-page-copy">
              Tipo, hora, zona y evidencia del registro operacional.
            </p>
          </div>
          <span className="source-indicator">
            {environment.dataSource === "api" ? "API local" : "Datos mock"}
          </span>
        </header>
        {environment.dataSource === "mock" && <MockDataNotice />}
        <section className="event-ledger" aria-label="Investigación de eventos">
          <EventsTable />
        </section>
      </div>
    </AppShell>
  );
}
