import { dataClient } from "./data-client";
import { apiFetch } from "./browser-session";
import {
  eventSubjects,
  eventTypeName,
  isOperationalEvent,
} from "./event-contract";
import { environment } from "@/config/environment";
import { sourceKind, sourceNames } from "@/features/dashboard/history-model";
import { eventEvidence } from "@/features/events/event-detail-model";
import {
  eventHistoryParams,
  eventsPerBatch,
  eventsPerPage,
  type EventHistoryQuery,
} from "@/features/events/event-history-query";
import type { EventListItem } from "@/types/operix";

export type EventHistoryPage = {
  rows: EventListItem[];
  count: number;
  page: number;
  totalPages: number;
  pageSize: number;
};

async function listPage(
  query: EventHistoryQuery,
  signal: AbortSignal,
): Promise<EventHistoryPage> {
  const base = environment.apiBaseUrl;
  if (!base)
    throw new Error("Falta NEXT_PUBLIC_API_BASE_URL para consultar la API.");
  const response = await apiFetch(
    `${base.replace(/\/$/, "")}/events/?${eventHistoryParams(query, true)}`,
    {
      cache: "no-store",
      signal: AbortSignal.any([signal, AbortSignal.timeout(15000)]),
    },
  );
  if (!response.ok)
    throw new Error(`La API respondió con estado ${response.status}.`);
  const payload = await response.json();
  const {
    count,
    page,
    page_size: pageSize,
    total_pages: totalPages,
    results,
  } = payload ?? {};
  if (
    !Number.isSafeInteger(count) ||
    count < 0 ||
    pageSize !== (query.all ? eventsPerBatch : eventsPerPage) ||
    totalPages !== Math.max(1, Math.ceil(count / pageSize)) ||
    page !== Math.min(query.page, totalPages) ||
    !Array.isArray(results) ||
    results.length > pageSize ||
    !results.every(isOperationalEvent)
  ) {
    throw new Error("La API devolvió una página de eventos inválida.");
  }
  return {
    count,
    page,
    pageSize,
    totalPages,
    rows: results.map((event) => ({
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
      sourceKindLabel: sourceNames[sourceKind(event.source?.kind)],
      confidence: null,
      time: new Date(event.occurred_at).toLocaleString("es-CL", {
        dateStyle: "short",
        timeStyle: "medium",
      }),
      status: "Registrado",
      tone: "accent",
      evidence: eventEvidence(event, base),
    })),
  };
}

export const eventsService = {
  list: () => dataClient.listEventCandidates(),
  listPage,
};
