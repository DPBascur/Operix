import { PageTitle } from "@/components/layout/page-title";
import { EventsTable } from "@/features/events/events-table";
import { parseEventHistory } from "@/features/events/event-history-query";

export const metadata = { title: "Eventos" };

export default async function EventsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(await searchParams)) {
    if (typeof value === "string") params.set(key, value);
  }
  const initial = parseEventHistory(params);
  return (
    <div className="page-wrap operational-page">
      <header className="compact-page-header app-page-heading">
        <div>
          <PageTitle animate>Investigación de eventos</PageTitle>
          <p className="compact-page-copy">
            Tipo, hora, zona y evidencia del registro operacional.
          </p>
        </div>
      </header>
      <section className="event-ledger" aria-label="Investigación de eventos">
        <EventsTable key={JSON.stringify(initial.filters)} initial={initial} />
      </section>
    </div>
  );
}
