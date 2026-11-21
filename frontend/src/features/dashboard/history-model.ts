export interface HistoryEvent {
  id: string;
  occurred_at: string;
  event_type: string;
  zone_id: string;
  analysis_run_id?: string;
  view_id?: unknown;
  observations?: unknown;
  source?: {
    kind?: unknown;
    video_sha256?: unknown;
    filename?: unknown;
    config_sha256?: unknown;
    epoch?: unknown;
    camera_id?: unknown;
  };
}

export const sourceNames = {
  demo: "Demo declarada",
  manual: "Carga manual",
  lab: "Cámara de laboratorio",
  unknown: "Sin clasificación",
} as const;

export function sourceKind(kind: unknown): keyof typeof sourceNames {
  return kind === "demo" || kind === "manual" || kind === "lab"
    ? kind
    : "unknown";
}

export function historyHref(
  params: URLSearchParams,
  overrides: Record<string, string> = {},
) {
  const query = new URLSearchParams(params);
  for (const [name, value] of Object.entries(overrides)) query.set(name, value);
  return `/events?${query}`;
}

export interface EventFrequency {
  total: number;
  timezone: "UTC";
  period: "day";
  by_period: { date: string; count: number }[];
  by_type: { event_type: string; count: number }[];
}

export function monthUtcBounds(month: string) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month))
    throw new Error("Seleccione un mes válido.");
  const start = new Date(`${month}-01T00:00:00Z`);
  const next = new Date(
    Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1),
  );
  const previous = new Date(
    Date.UTC(start.getUTCFullYear(), start.getUTCMonth() - 1, 1),
  );
  const lastSecond = new Date(+next - 1000).toISOString();
  return {
    start: start.toISOString(),
    previous: previous.toISOString(),
    end: lastSecond.replace(".000Z", ".999999Z"),
  };
}

export function parseFrequency(value: unknown): EventFrequency {
  if (!value || typeof value !== "object")
    throw new Error("La API no entregó frecuencias válidas.");
  const data = value as Record<string, unknown>;
  const rowsValid = (rows: unknown, key: "date" | "event_type") =>
    Array.isArray(rows) &&
    rows.every(
      (row) =>
        row &&
        typeof row === "object" &&
        typeof row[key] === "string" &&
        Number.isSafeInteger(row.count) &&
        row.count >= 0,
    );
  if (
    !Number.isSafeInteger(data.total) ||
    (data.total as number) < 0 ||
    data.timezone !== "UTC" ||
    data.period !== "day" ||
    !rowsValid(data.by_period, "date") ||
    !rowsValid(data.by_type, "event_type")
  ) {
    throw new Error("La API no entregó frecuencias válidas.");
  }
  const result = data as unknown as EventFrequency;
  if (
    result.by_period.some((row) => !/^\d{4}-\d{2}-\d{2}$/.test(row.date)) ||
    result.by_period.reduce((sum, row) => sum + row.count, 0) !==
      result.total ||
    result.by_type.reduce((sum, row) => sum + row.count, 0) !== result.total
  ) {
    throw new Error("Las frecuencias de la API no coinciden con el total.");
  }
  return result;
}

export function summarizeApiHistory(
  events: HistoryEvent[],
  month: string,
  current: EventFrequency,
  previous: EventFrequency,
) {
  const base = summarizeHistory(events, month);
  if (base.total !== current.total) {
    throw new Error(
      "El histórico cambió durante la consulta. Actualice para reconciliar los indicadores.",
    );
  }
  const byDay = new Map(
    current.by_period.map((row) => [Number(row.date.slice(8)), row.count]),
  );
  const types = new Map(
    current.by_type.map((row) => [row.event_type, row.count]),
  );
  if (
    byDay.size !== current.by_period.length ||
    types.size !== base.types.length ||
    current.by_period.some((row) => !row.date.startsWith(`${month}-`)) ||
    base.days.some((row) => row.count !== (byDay.get(row.day) ?? 0)) ||
    base.types.some((row) => row.count !== types.get(row.label))
  ) {
    throw new Error(
      "El histórico cambió durante la consulta. Actualice para reconciliar los indicadores.",
    );
  }
  return {
    ...base,
    total: current.total,
    previousCount: previous.total,
    change: previous.total
      ? ((current.total - previous.total) / previous.total) * 100
      : null,
    days: base.days.map((row) => ({ ...row, count: byDay.get(row.day) ?? 0 })),
  };
}

/** Texto UTC estable entre ICU de Windows y navegador; evita diferencias de hidratación. */
export function formatHistoryTime(value: string): string {
  const iso = new Date(value).toISOString();
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)} · ${iso.slice(11, 16)} UTC`;
}
export function historyError(cause: unknown): string {
  if (cause instanceof Error && cause.name === "AbortError")
    return "La consulta tardó demasiado. Vuelva a intentar.";
  if (cause instanceof TypeError)
    return "No se pudo conectar con la API. Revise el servicio y vuelva a intentar.";
  if (cause instanceof SyntaxError)
    return "La API devolvió una respuesta inválida. Vuelva a consultar.";
  return cause instanceof Error
    ? cause.message
    : "No fue posible consultar el histórico. Vuelva a intentar.";
}

export function parseHistory(value: unknown): HistoryEvent[] {
  if (
    !Array.isArray(value) ||
    !value.every(
      (item) =>
        item &&
        typeof item === "object" &&
        ["id", "occurred_at", "event_type", "zone_id"].every(
          (key) => typeof item[key] === "string",
        ) &&
        Number.isFinite(Date.parse(item.occurred_at)),
    )
  ) {
    throw new Error(
      "La API no entregó un histórico válido. Vuelva a consultar.",
    );
  }
  const ids = new Set<string>();
  return value.filter((item) => !ids.has(item.id) && !!ids.add(item.id));
}

const santiagoTime = new Intl.DateTimeFormat("en-GB", {
  timeZone: "America/Santiago",
  weekday: "short",
  hour: "2-digit",
  hourCycle: "h23",
});

export const weekdays = [
  "Lunes",
  "Martes",
  "Miércoles",
  "Jueves",
  "Viernes",
  "Sábado",
  "Domingo",
];
const weekdayKeys = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];

export function dayUtcBounds(month: string, day: number) {
  const first = new Date(monthUtcBounds(month).start);
  first.setUTCDate(day);
  if (!Number.isInteger(day) || first.toISOString().slice(0, 7) !== month)
    throw new Error("Día fuera del período seleccionado.");
  const date = first.toISOString().slice(0, 10);
  return {
    occurred_after: `${date}T00:00:00.000Z`,
    occurred_before: `${date}T23:59:59.999999Z`,
  };
}

export function summarizeHistory(events: HistoryEvent[], month: string) {
  if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month))
    throw new Error("Seleccione un mes válido.");
  const start = new Date(`${month}-01T00:00:00Z`);
  const end = new Date(
    Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + 1, 1),
  );
  const previous = new Date(
    Date.UTC(start.getUTCFullYear(), start.getUTCMonth() - 1, 1),
  );
  const selected = events.filter(
    (e) =>
      Date.parse(e.occurred_at) >= +start && Date.parse(e.occurred_at) < +end,
  );
  const previousCount = events.filter(
    (e) =>
      Date.parse(e.occurred_at) >= +previous &&
      Date.parse(e.occurred_at) < +start,
  ).length;
  const countBy = (key: (e: HistoryEvent) => string) => {
    const counts = new Map<string, number>();
    selected.forEach((e) => counts.set(key(e), (counts.get(key(e)) ?? 0) + 1));
    return [...counts]
      .map(([label, count]) => ({ label, count }))
      .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label));
  };
  const days = Array.from(
    { length: end.getUTCDate() === 1 ? new Date(+end - 1).getUTCDate() : 31 },
    (_, i) => ({ day: i + 1, count: 0 }),
  );
  const hours = Array.from({ length: 24 }, (_, hour) => ({ hour, count: 0 }));
  const timeMatrix = weekdays.map(() => [0, 0, 0, 0, 0, 0]);
  const videos = new Map<
    string,
    { sha: string; name: string; count: number }
  >();
  selected.forEach((e) => {
    const d = new Date(e.occurred_at);
    days[d.getUTCDate() - 1].count++;
    const clock = santiagoTime.formatToParts(d);
    const hour = Number(clock.find((part) => part.type === "hour")?.value);
    const weekday = weekdayKeys.indexOf(
      clock.find((part) => part.type === "weekday")?.value ?? "",
    );
    hours[hour].count++;
    timeMatrix[weekday][Math.floor(hour / 4)]++;
    const sha = e.source?.video_sha256;
    if (typeof sha === "string" && /^[a-f0-9]{64}$/.test(sha)) {
      const existing = videos.get(sha);
      if (existing) existing.count++;
      else
        videos.set(sha, {
          sha,
          name:
            typeof e.source?.filename === "string" && e.source.filename
              ? e.source.filename
              : "Video sin nombre",
          count: 1,
        });
    }
  });
  return {
    total: selected.length,
    runsWithEvents: new Set(
      selected
        .map((event) => event.analysis_run_id)
        .filter((id) => typeof id === "string" && id.length > 0),
    ).size,
    sources: countBy((event) => sourceKind(event.source?.kind)),
    videos: [...videos.values()].sort(
      (a, b) => b.count - a.count || a.sha.localeCompare(b.sha),
    ),
    previousCount,
    change: previousCount
      ? ((selected.length - previousCount) / previousCount) * 100
      : null,
    zones: countBy((e) => e.zone_id),
    types: countBy((e) => e.event_type),
    days,
    hours,
    timeMatrix,
    recent: [...selected]
      .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at))
      .slice(0, 5),
  };
}
