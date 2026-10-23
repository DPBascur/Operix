export interface HistoryEvent {
  id: string;
  occurred_at: string;
  event_type: string;
  zone_id: string;
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
