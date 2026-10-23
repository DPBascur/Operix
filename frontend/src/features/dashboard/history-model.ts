export interface HistoryEvent {
  id: string;
  occurred_at: string;
  event_type: string;
  zone_id: string;
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
  return {
    ...base,
    total: current.total,
    previousCount: previous.total,
    change: previous.total
      ? ((current.total - previous.total) / previous.total) * 100
      : null,
    days: base.days.map((row) => ({ ...row, count: byDay.get(row.day) ?? 0 })),
    types: current.by_type.map((row) => ({
      label: row.event_type,
      count: row.count,
    })),
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
  selected.forEach((e) => {
    const d = new Date(e.occurred_at);
    days[d.getUTCDate() - 1].count++;
    hours[d.getUTCHours()].count++;
  });
  return {
    total: selected.length,
    previousCount,
    change: previousCount
      ? ((selected.length - previousCount) / previousCount) * 100
      : null,
    zones: countBy((e) => e.zone_id),
    types: countBy((e) => e.event_type),
    days,
    hours,
    recent: [...selected]
      .sort((a, b) => Date.parse(b.occurred_at) - Date.parse(a.occurred_at))
      .slice(0, 5),
  };
}
