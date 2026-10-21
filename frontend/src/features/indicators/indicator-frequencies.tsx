"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Button } from "@/components/ui/button";
import { environment } from "@/config/environment";

interface Frequencies {
  total: number;
  timezone: string;
  by_period: { date: string; count: number }[];
  by_type: { event_type: string; count: number }[];
}

export function IndicatorFrequencies() {
  const isApi = environment.dataSource === "api" && !!environment.apiBaseUrl;
  const [data, setData] = useState<Frequencies | null>(null);
  const [loading, setLoading] = useState(isApi);
  const [error, setError] = useState<string | null>(null);
  const [from, setFrom] = useState("");
  const [until, setUntil] = useState("");
  const [eventType, setEventType] = useState("");
  const active = useRef<AbortController | null>(null);

  async function load(params = new URLSearchParams()) {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setLoading(true);
    setError(null);
    setData(null);
    try {
      const response = await fetch(
        `${environment.apiBaseUrl?.replace(/\/$/, "")}/events/frequencies/?${params}`,
        {
          cache: "no-store",
          signal: AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(15_000),
          ]),
        },
      );
      if (!response.ok)
        throw new Error(
          "No se pudieron consultar las frecuencias almacenadas.",
        );
      const result: Frequencies = await response.json();
      if (!controller.signal.aborted) setData(result);
    } catch {
      if (!controller.signal.aborted)
        setError(
          "No se pudieron consultar las frecuencias. Compruebe la API y vuelva a intentar.",
        );
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }

  useEffect(() => {
    if (!isApi) return;
    const controller = new AbortController();
    active.current = controller;
    fetch(`${environment.apiBaseUrl?.replace(/\/$/, "")}/events/frequencies/`, {
      cache: "no-store",
      signal: AbortSignal.any([controller.signal, AbortSignal.timeout(15_000)]),
    })
      .then(async (response) => {
        if (!response.ok) throw new Error("API no disponible");
        const result: Frequencies = await response.json();
        if (!controller.signal.aborted) setData(result);
      })
      .catch(() => {
        if (!controller.signal.aborted)
          setError(
            "No se pudieron consultar las frecuencias. Compruebe la API y vuelva a intentar.",
          );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => active.current?.abort();
  }, [isApi]);

  function submit(event: FormEvent) {
    event.preventDefault();
    if (from && until && from > until) {
      setData(null);
      setError("La fecha Desde no puede ser posterior a Hasta.");
      return;
    }
    const params = new URLSearchParams();
    if (from) params.set("occurred_after", `${from}T00:00:00Z`);
    if (until) params.set("occurred_before", `${until}T23:59:59.999999Z`);
    if (eventType) params.set("event_type", eventType);
    void load(params);
  }

  if (!isApi)
    return (
      <p className="text-text-secondary">
        Las frecuencias requieren el modo API y registros persistidos. No se
        sustituyen por datos mock.
      </p>
    );

  return (
    <section
      aria-label="Frecuencias de eventos persistidos"
      className="space-y-6"
    >
      <p className="max-w-3xl text-sm text-text-secondary">
        Conteos de registros almacenados, incluidos los de desarrollo o
        demostración. No representan tasas de incidentes, personas únicas ni una
        evaluación de riesgo. Los días se agrupan en UTC; solo se muestran días
        con registros.
      </p>
      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3"
        aria-label="Filtrar frecuencias"
      >
        <label className="grid gap-1 text-sm">
          Desde (UTC)
          <input
            className="min-h-11 rounded-control border border-border bg-surface px-3"
            type="date"
            value={from}
            onChange={(event) => setFrom(event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-sm">
          Hasta (UTC)
          <input
            className="min-h-11 rounded-control border border-border bg-surface px-3"
            type="date"
            value={until}
            onChange={(event) => setUntil(event.target.value)}
          />
        </label>
        <label className="grid gap-1 text-sm">
          Tipo
          <select
            className="min-h-11 rounded-control border border-border bg-surface px-3"
            value={eventType}
            onChange={(event) => setEventType(event.target.value)}
          >
            <option value="">Todos los tipos disponibles</option>
            <option value="zone_dwell">Permanencia en zona</option>
          </select>
        </label>
        <Button type="submit" disabled={loading}>
          Consultar
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={loading}
          onClick={() => {
            setFrom("");
            setUntil("");
            setEventType("");
            void load();
          }}
        >
          Limpiar filtros
        </Button>
      </form>
      {loading && <p role="status">Consultando registros…</p>}
      {error && (
        <p role="alert" className="text-foreground">
          {error}
        </p>
      )}
      {data && (
        <div aria-live="polite" className="space-y-5">
          <p>{data.total} registros coinciden con la consulta.</p>
          {data.total === 0 ? (
            <p className="text-text-secondary">
              No hay registros en este rango. Amplíe el período o limpie los
              filtros.
            </p>
          ) : (
            <div className="grid gap-8 md:grid-cols-2">
              <section aria-labelledby="frequency-day-title">
                <h3 id="frequency-day-title" className="mb-3 font-semibold">
                  Frecuencia por día (UTC)
                </h3>
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th scope="col" className="py-2">
                        Fecha
                      </th>
                      <th scope="col" className="py-2 text-right">
                        Registros
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_period.map((row) => (
                      <tr key={row.date} className="border-b border-border">
                        <th scope="row" className="py-3 font-normal">
                          {row.date}
                        </th>
                        <td className="text-right tabular-nums">{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section aria-labelledby="frequency-type-title">
                <h3 id="frequency-type-title" className="mb-3 font-semibold">
                  Frecuencia por tipo
                </h3>
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-border">
                      <th scope="col" className="py-2">
                        Tipo
                      </th>
                      <th scope="col" className="py-2 text-right">
                        Registros
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_type.map((row) => (
                      <tr
                        key={row.event_type}
                        className="border-b border-border"
                      >
                        <th scope="row" className="py-3 font-normal">
                          {row.event_type === "zone_dwell"
                            ? "Permanencia en zona"
                            : row.event_type}
                        </th>
                        <td className="text-right tabular-nums">{row.count}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
            </div>
          )}
        </div>
      )}
    </section>
  );
}
