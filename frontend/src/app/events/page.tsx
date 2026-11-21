import { PageTitle } from "@/components/layout/page-title";
import { EventsTable } from "@/features/events/events-table";
import type { EventQuery } from "@/services/adapters/frontend-data.adapter";

export const metadata = { title: "Eventos" };

export default async function EventsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const date = (key: string) => {
    const value = params[key];
    return typeof value === "string" && Number.isFinite(Date.parse(value))
      ? value
      : undefined;
  };
  const initial: EventQuery = {
    cameraId:
      typeof params.camera_id === "string" &&
      /^lab-cam-[0-9]{2}$/.test(params.camera_id)
        ? params.camera_id
        : undefined,
    zoneId:
      typeof params.zone_id === "string" &&
      params.zone_id.length > 0 &&
      params.zone_id.length <= 64
        ? params.zone_id
        : undefined,
    sourceSha256:
      typeof params.source_sha256 === "string" &&
      /^[a-f0-9]{64}$/.test(params.source_sha256)
        ? params.source_sha256
        : undefined,
    occurredAfter: date("occurred_after"),
    occurredBefore: date("occurred_before"),
    eventType:
      params.event_type === "zone_dwell" ||
      params.event_type === "person_forklift_proximity" ||
      params.event_type === "zone_entry" ||
      params.event_type === "zone_coexistence"
        ? params.event_type
        : undefined,
    sourceKind:
      params.source_kind === "demo" ||
      params.source_kind === "manual" ||
      params.source_kind === "lab" ||
      params.source_kind === "unknown"
        ? params.source_kind
        : undefined,
  };
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
        <EventsTable key={JSON.stringify(initial)} initial={initial} />
      </section>
    </div>
  );
}
