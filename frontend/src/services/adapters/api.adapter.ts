import { environment } from "@/config/environment";
import type {
  AnalysisOverview,
  DashboardSummary,
  EventCandidate,
  EventListItem,
  OperationalRule,
  Zone,
} from "@/types/operix";

import type { FrontendDataAdapter } from "./frontend-data.adapter";
import { MockAdapter } from "./mock.adapter";

type ApiEvent = {
  id: string;
  occurred_at: string;
  event_type: string;
  rule_id: string;
  rule_version: number;
  zone_id: string;
  track_id: number;
  class_name: string;
  evidence_url?: string | null;
};

function isApiEvent(value: unknown): value is ApiEvent {
  if (typeof value !== "object" || value === null) return false;
  const event = value as Record<string, unknown>;
  return (
    [
      "id",
      "occurred_at",
      "event_type",
      "rule_id",
      "zone_id",
      "class_name",
    ].every((field) => typeof event[field] === "string") &&
    typeof event.rule_version === "number" &&
    typeof event.track_id === "number" &&
    (event.evidence_url === undefined ||
      event.evidence_url === null ||
      typeof event.evidence_url === "string") &&
    !Number.isNaN(Date.parse(event.occurred_at as string))
  );
}

export class ApiAdapter implements FrontendDataAdapter {
  private readonly mock = new MockAdapter();

  async listEvents(): Promise<EventListItem[]> {
    if (!environment.apiBaseUrl) {
      throw new Error("Falta NEXT_PUBLIC_API_BASE_URL para consultar la API.");
    }
    const response = await fetch(
      `${environment.apiBaseUrl.replace(/\/$/, "")}/events/`,
      { cache: "no-store" },
    );
    if (!response.ok) {
      throw new Error(`La API respondió con estado ${response.status}.`);
    }
    const payload: unknown = await response.json();
    if (!Array.isArray(payload) || !payload.every(isApiEvent)) {
      throw new Error("La API devolvió una lista de eventos inválida.");
    }
    return payload.map((event) => ({
      id: event.id,
      title:
        event.event_type === "zone_dwell"
          ? "Permanencia en zona"
          : event.event_type,
      zone: event.zone_id,
      rule: `${event.rule_id} · v${event.rule_version}`,
      objects: `${event.class_name} · ID ${event.track_id}`,
      confidence: null,
      time: new Date(event.occurred_at).toLocaleString("es-CL", {
        dateStyle: "short",
        timeStyle: "medium",
      }),
      status: "Registrado",
      tone: "accent" as const,
      evidenceUrl: event.evidence_url?.startsWith("/api/v1/events/")
        ? new URL(event.evidence_url, environment.apiBaseUrl).toString()
        : null,
    }));
  }

  // Las demás vistas siguen en modo mock hasta sus propias integraciones.
  getAnalysisOverview(): Promise<AnalysisOverview> {
    return this.mock.getAnalysisOverview();
  }
  getDashboardSummary(): Promise<DashboardSummary> {
    return this.mock.getDashboardSummary();
  }
  listEventCandidates(): Promise<EventCandidate[]> {
    return this.mock.listEventCandidates();
  }
  listOperationalRules(): Promise<OperationalRule[]> {
    return this.mock.listOperationalRules();
  }
  listZones(): Promise<Zone[]> {
    return this.mock.listZones();
  }
}
