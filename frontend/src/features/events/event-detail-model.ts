import type { OperationalEvent } from "../../services/event-contract.ts";

export function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}
export function text(value: unknown, fallback = "No registrado"): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}
export function operationalSubjects(event: OperationalEvent): string {
  const label = (item: { class_name: string; track_id: number }) => {
    const name =
      item.class_name === "person"
        ? "Persona"
        : item.class_name === "forklift"
          ? "Montacargas"
          : item.class_name;
    return `${name} · ID de seguimiento ${item.track_id}`;
  };
  return ["person_forklift_proximity", "zone_coexistence"].includes(
    event.event_type,
  ) && event.interaction
    ? `${label(event.interaction.person)} ↔ ${label(event.interaction.forklift)}`
    : label({
        class_name: event.class_name,
        track_id: event.track_id as number,
      });
}
export function measurement(value: unknown, unit = "s"): string {
  if (
    !["string", "number"].includes(typeof value) ||
    (typeof value === "string" && !/^\d+(\.\d+)?$/.test(value))
  )
    return "No registrada";
  const number = Number(value);
  if (!Number.isFinite(number) || number < 0) return "No registrada";
  const formatted = new Intl.NumberFormat("es-CL", {
    maximumSignificantDigits: 12,
    useGrouping: false,
  }).format(number);
  return unit ? `${formatted} ${unit}` : formatted;
}
export function eventMeasurements(event: OperationalEvent) {
  const parameters = record(event.rule_parameters);
  if (event.event_type === "zone_entry")
    return [
      {
        label: "Ingreso observado",
        observed: "Fuera → dentro",
        configured: "Zona restringida",
        criterion: "Transición consecutiva",
      },
    ];
  if (event.event_type === "zone_dwell")
    return [
      {
        label: "Permanencia",
        observed: measurement(event.observed_dwell_time_s),
        configured: measurement(parameters.min_duration_s),
        criterion: "Mínimo configurado",
      },
    ];
  const observations = record(event.observations);
  const ground = record(observations.ground);
  const metric = parameters.distance_unit === "m";
  const duration = {
    label: "Duración de la condición",
    observed: measurement(observations.duration_s),
    configured: measurement(parameters.minimum_duration_seconds),
    criterion: "Mínimo configurado",
  };
  if (event.event_type === "zone_coexistence") return [duration];
  return [
    {
      label: metric
        ? "Distancia aproximada sobre el suelo"
        : "Distancia normalizada",
      observed: measurement(
        metric ? ground.distance : observations.normalized_distance,
        metric ? "m aprox." : "",
      ),
      configured: measurement(
        parameters.max_distance,
        metric ? "m aprox." : "",
      ),
      criterion: "Máximo configurado",
    },
    {
      label: "Duración de la condición",
      observed: measurement(observations.duration_s),
      configured: measurement(parameters.minimum_duration_seconds),
      criterion: "Mínimo configurado",
    },
  ];
}
export function eventProximityGeometry(event: OperationalEvent) {
  if (event.event_type !== "person_forklift_proximity") return null;
  const observations = record(event.observations);
  const ground = record(observations.ground);
  const geometry =
    record(event.rule_parameters).distance_unit === "m"
      ? { ...ground, version: ground.method }
      : record(observations.proximity_geometry);
  const point = (value: unknown) =>
    Array.isArray(value) &&
    value.length === 2 &&
    value.every(
      (axis) =>
        typeof axis === "number" &&
        Number.isFinite(axis) &&
        axis >= 0 &&
        axis <= 1,
    )
      ? JSON.stringify(value)
      : null;
  return {
    version: text(geometry.version),
    personAnchor: point(geometry.person_anchor),
    equipmentTarget: point(geometry.equipment_target),
  };
}
export function eventTime(event: OperationalEvent) {
  const basis = record(event.source).timestamp_basis;
  const proxy = basis === "ANALYSIS_START_PROXY_NOT_RECORDING_TIME";
  return {
    iso: event.occurred_at,
    formatted: new Intl.DateTimeFormat("es-CL", {
      dateStyle: "medium",
      timeStyle: "medium",
      timeZone: "UTC",
      hourCycle: "h23",
    }).format(new Date(event.occurred_at)),
    label: proxy
      ? "Referencia del análisis · UTC"
      : "Referencia del evento · UTC",
    explanation: proxy
      ? "Inicio del análisis más tiempo del video; no es la fecha de grabación."
      : typeof basis === "string" && basis.trim()
        ? `Base temporal registrada: ${basis}.`
        : "Base temporal no registrada; no se puede deducir la fecha de grabación.",
  };
}
export function evidenceHref(
  event: OperationalEvent,
  apiBaseUrl: string | undefined,
): string | null {
  const path = `/api/v1/events/${encodeURIComponent(event.id)}/evidence/`;
  return event.evidence_url === path ? evidencePath(path, apiBaseUrl) : null;
}

export function evidenceClip(
  event: OperationalEvent,
  apiBaseUrl: string | undefined,
) {
  const clip = record(event.evidence_clip);
  const run = event.analysis_run_id;
  if (
    typeof run !== "string" ||
    clip.kind !== "annotated" ||
    clip.event_id !== event.id ||
    clip.analysis_run_id !== run ||
    typeof clip.event_offset_s !== "number" ||
    !Number.isFinite(clip.event_offset_s) ||
    clip.event_offset_s < 0
  )
    return null;
  const path = `/api/v1/events/${encodeURIComponent(event.id)}/clips/${encodeURIComponent(run)}/`;
  const url = clip.url === path ? evidencePath(path, apiBaseUrl) : null;
  return url ? { url, offset: clip.event_offset_s } : null;
}

function evidencePath(path: string, apiBaseUrl: string | undefined) {
  if (!apiBaseUrl) return null;
  if (apiBaseUrl === "/api/v1") return path;
  try {
    const base = new URL(apiBaseUrl);
    if (!["http:", "https:"].includes(base.protocol)) return null;
    return new URL(path, base).href;
  } catch {
    return null;
  }
}
