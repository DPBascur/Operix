import { environment } from "@/config/environment";
import type {
  AnalysisOverview,
  DashboardSummary,
  EventCandidate,
  EventListItem,
  OperationalRule,
  Zone,
} from "@/types/operix";

import type { EventQuery, FrontendDataAdapter } from "./frontend-data.adapter";
import { MockAdapter } from "./mock.adapter";
import {
  isOperationalEvent,
  eventSubjects,
  eventTypeName,
} from "../event-contract";

export class ApiAdapter implements FrontendDataAdapter {
  private readonly mock = new MockAdapter();

  async listEvents(filters: EventQuery = {}): Promise<EventListItem[]> {
    if (!environment.apiBaseUrl) {
      throw new Error("Falta NEXT_PUBLIC_API_BASE_URL para consultar la API.");
    }
    const url = new URL(`${environment.apiBaseUrl.replace(/\/$/, "")}/events/`);
    const params = new URLSearchParams();
    if (filters.occurredAfter)
      params.set("occurred_after", filters.occurredAfter);
    if (filters.occurredBefore)
      params.set("occurred_before", filters.occurredBefore);
    if (filters.eventType) params.set("event_type", filters.eventType);
    url.search = params.toString();
    const response = await fetch(url.toString(), { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`La API respondió con estado ${response.status}.`);
    }
    const payload: unknown = await response.json();
    if (!Array.isArray(payload) || !payload.every(isOperationalEvent)) {
      throw new Error("La API devolvió una lista de eventos inválida.");
    }
    return payload.map((event) => ({
      id: event.id,
      title: eventTypeName(event.event_type),
      zone: event.zone_id,
      rule: `${event.rule_id} · v${event.rule_version}`,
      objects: eventSubjects(event),
      source:
        typeof event.source?.filename === "string"
          ? event.source.filename
          : "No informada",
      detailUrl: `/events/${encodeURIComponent(event.id)}`,
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
