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
  return event.event_type === "person_forklift_proximity" && event.interaction
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
  return [
    {
      label: "Distancia normalizada",
      observed: measurement(observations.normalized_distance, ""),
      configured: measurement(parameters.max_distance, ""),
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
  if (!apiBaseUrl) return null;
  if (
    event.evidence_url !==
    `/api/v1/events/${encodeURIComponent(event.id)}/evidence/`
  )
    return null;
  try {
    const base = new URL(apiBaseUrl);
    if (!["http:", "https:"].includes(base.protocol)) return null;
    return new URL(event.evidence_url, base).href;
  } catch {
    return null;
  }
}
