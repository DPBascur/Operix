import type {
  AnalysisOverview,
  DashboardSummary,
  EventCandidate,
  EventListItem,
  OperationalRule,
  Zone,
} from "@/types/operix";

export interface FrontendDataAdapter {
  getAnalysisOverview(): Promise<AnalysisOverview>;
  getDashboardSummary(): Promise<DashboardSummary>;
  listEventCandidates(): Promise<EventCandidate[]>;
  listEvents(filters?: EventQuery): Promise<EventListItem[]>;
  listOperationalRules(): Promise<OperationalRule[]>;
  listZones(): Promise<Zone[]>;
}

export interface EventQuery {
  occurredAfter?: string;
  occurredBefore?: string;
  eventType?:
    | "zone_dwell"
    | "person_forklift_proximity"
    | "zone_entry"
    | "zone_coexistence";
  sourceKind?: "demo" | "manual" | "lab" | "unknown";
  cameraId?: string;
  sourceSha256?: string;
  zoneId?: string;
}

export function eventQueryParams(filters: EventQuery) {
  const params = new URLSearchParams();
  if (filters.occurredAfter)
    params.set("occurred_after", filters.occurredAfter);
  if (filters.occurredBefore)
    params.set("occurred_before", filters.occurredBefore);
  if (filters.eventType) params.set("event_type", filters.eventType);
  if (filters.sourceKind) params.set("source_kind", filters.sourceKind);
  if (filters.sourceSha256) params.set("source_sha256", filters.sourceSha256);
  if (filters.zoneId) params.set("zone_id", filters.zoneId);
  if (filters.cameraId) params.set("camera_id", filters.cameraId);
  return params;
}
