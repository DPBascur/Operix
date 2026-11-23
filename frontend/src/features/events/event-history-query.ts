import type { EventQuery } from "@/services/adapters/frontend-data.adapter";

export const eventsPerPage = 15;
export const eventsPerBatch = 60;

export type EventHistoryFilters = EventQuery & {
  evidenceStage?: "pending" | "finished" | "legacy";
  search?: string;
  order?: "oldest";
};

export type EventHistoryQuery = {
  filters: EventHistoryFilters;
  page: number;
  all: boolean;
};

export function parseEventHistory(params: URLSearchParams): EventHistoryQuery {
  const date = (key: string) => {
    const value = params.get(key);
    return value &&
      /(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
      Number.isFinite(Date.parse(value))
      ? value
      : undefined;
  };
  const cameraId = params.get("camera_id");
  const zoneId = params.get("zone_id");
  const sourceSha256 = params.get("source_sha256");
  const eventType = params.get("event_type");
  const sourceKind = params.get("source_kind");
  const evidenceStage = params.get("evidence_stage");
  const search = params.get("search")?.trim();
  const page = params.get("page") ?? "";
  return {
    filters: {
      cameraId:
        cameraId && /^lab-cam-[0-9]{2}$/.test(cameraId) ? cameraId : undefined,
      zoneId: zoneId && zoneId.length <= 64 ? zoneId : undefined,
      sourceSha256:
        sourceSha256 && /^[a-f0-9]{64}$/.test(sourceSha256)
          ? sourceSha256
          : undefined,
      occurredAfter: date("occurred_after"),
      occurredBefore: date("occurred_before"),
      eventType:
        eventType === "zone_dwell" ||
        eventType === "person_forklift_proximity" ||
        eventType === "zone_entry" ||
        eventType === "zone_coexistence"
          ? eventType
          : undefined,
      sourceKind:
        sourceKind === "demo" ||
        sourceKind === "manual" ||
        sourceKind === "lab" ||
        sourceKind === "unknown"
          ? sourceKind
          : undefined,
      evidenceStage:
        evidenceStage === "pending" ||
        evidenceStage === "finished" ||
        evidenceStage === "legacy"
          ? evidenceStage
          : undefined,
      search: search && search.length <= 120 ? search : undefined,
      order: params.get("order") === "oldest" ? "oldest" : undefined,
    },
    page:
      /^[1-9]\d*$/.test(page) && Number.isSafeInteger(Number(page))
        ? Number(page)
        : 1,
    all: params.get("view") === "all",
  };
}

export function eventHistoryParams(
  { filters, page, all }: EventHistoryQuery,
  api = false,
) {
  const params = new URLSearchParams();
  for (const [key, value] of [
    ["occurred_after", filters.occurredAfter],
    ["occurred_before", filters.occurredBefore],
    ["event_type", filters.eventType],
    ["source_kind", filters.sourceKind],
    ["source_sha256", filters.sourceSha256],
    ["zone_id", filters.zoneId],
    ["camera_id", filters.cameraId],
    ["evidence_stage", filters.evidenceStage],
    ["search", filters.search],
    ["order", filters.order],
  ] as const) {
    if (value) params.set(key, value);
  }
  if (api || page > 1) params.set("page", String(page));
  if (all) {
    if (api) params.set("page_size", String(eventsPerBatch));
    else params.set("view", "all");
  }
  return params;
}

export function eventHistoryHref(query: EventHistoryQuery) {
  const params = eventHistoryParams(query);
  return params.size ? `/events?${params}` : "/events";
}

export function changeEventHistoryMode(
  query: EventHistoryQuery,
): EventHistoryQuery {
  const previousSize = query.all ? eventsPerBatch : eventsPerPage;
  const nextSize = query.all ? eventsPerPage : eventsPerBatch;
  return {
    ...query,
    all: !query.all,
    page: Math.floor(((query.page - 1) * previousSize) / nextSize) + 1,
  };
}
