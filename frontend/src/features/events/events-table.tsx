"use client";

import { Activity, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { environment } from "@/config/environment";
import { eventsService } from "@/services/events.service";
import type { EventQuery } from "@/services/adapters/frontend-data.adapter";
import type { EventListItem } from "@/types/operix";

function formatLocalMinute(date: Date): string {
  const parts = [
    date.getFullYear(),
    String(date.getMonth() + 1).padStart(2, "0"),
    String(date.getDate()).padStart(2, "0"),
    String(date.getHours()).padStart(2, "0"),
    String(date.getMinutes()).padStart(2, "0"),
  ];
  return `${parts[0]}-${parts[1]}-${parts[2]}T${parts[3]}:${parts[4]}`;
}

function localDateTimeToIso(value: string): string | null {
  if (!/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(value)) return null;
  const date = new Date(value);
  if (Number.isNaN(date.getTime()) || formatLocalMinute(date) !== value)
    return null;
  // Rechaza una hora local ambigua durante un cambio de horario de verano.
  if (
    [-60, -30, 30, 60].some(
      (minutes) =>
        formatLocalMinute(new Date(date.getTime() + minutes * 60_000)) ===
        value,
    )
  )
    return null;
  return date.toISOString();
}

export function EventsTable() {
  const [events, setEvents] = useState<EventListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [query, setQuery] = useState("");
  const [zone, setZone] = useState("all");
  const [from, setFrom] = useState("");
  const [to, setTo] = useState("");
  const [eventType, setEventType] = useState<
    "" | "zone_dwell" | "person_forklift_proximity"
  >("");
  const [filters, setFilters] = useState<EventQuery>({});
  const [filterError, setFilterError] = useState<string | null>(null);
  useEffect(() => {
    let active = true;
    eventsService.listRows(filters).then(
      (items) => {
        if (!active) return;
        setEvents(items);
        setError(null);
        setLoading(false);
      },
      (failure: unknown) => {
        if (!active) return;
        setError(
          failure instanceof Error
            ? failure.message
            : "No se pudieron cargar los eventos.",
        );
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [filters, retry]);
  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const occurredAfter = from ? localDateTimeToIso(from) : undefined;
    const occurredBefore = to ? localDateTimeToIso(to) : undefined;
    if ((from && !occurredAfter) || (to && !occurredBefore)) {
      setFilterError("Ingresa fechas y horas locales válidas.");
      return;
    }
    if (occurredAfter && occurredBefore && occurredAfter > occurredBefore) {
      setFilterError("La fecha desde no puede ser posterior a la fecha hasta.");
      return;
    }
    setFilterError(null);
    setLoading(true);
    setFilters({
      occurredAfter: occurredAfter ?? undefined,
      occurredBefore: occurredBefore ?? undefined,
      eventType: eventType || undefined,
    });
    setRetry((current) => current + 1);
  }
  function clearFilters() {
    setFrom("");
    setTo("");
    setEventType("");
    setQuery("");
    setZone("all");
    setFilterError(null);
    setLoading(true);
    setFilters({});
    setRetry((current) => current + 1);
  }
  const hasAppliedFilters = Boolean(
    filters.occurredAfter || filters.occurredBefore || filters.eventType,
  );
  const hasDraftFilters = Boolean(from || to || eventType);
  const zones = useMemo(
    () => [...new Set(events.map((event) => event.zone))],
    [events],
  );
  const filteredEvents = useMemo(() => {
    const normalizedQuery = query.trim().toLocaleLowerCase("es");
    if (environment.dataSource === "api") return events;
    return events.filter((event) => {
      const matchesQuery =
        !normalizedQuery ||
        event.title.toLocaleLowerCase("es").includes(normalizedQuery) ||
        event.rule.toLocaleLowerCase("es").includes(normalizedQuery);
      return matchesQuery && (zone === "all" || event.zone === zone);
    });
  }, [events, query, zone]);

  return (
    <>
      {environment.dataSource === "api" ? (
        <form
          className="grid gap-3 border-b border-border pb-5 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_auto] xl:items-end"
          onSubmit={applyFilters}
        >
          <label className="grid gap-1 text-xs font-medium text-text-secondary">
            Desde (hora local)
            <Input
              aria-label="Desde, fecha y hora local"
              onChange={(event) => setFrom(event.target.value)}
              type="datetime-local"
              value={from}
            />
          </label>
          <label className="grid gap-1 text-xs font-medium text-text-secondary">
            Hasta (hora local)
            <Input
              aria-label="Hasta, fecha y hora local"
              onChange={(event) => setTo(event.target.value)}
              type="datetime-local"
              value={to}
            />
          </label>
          <label className="grid gap-1 text-xs font-medium text-text-secondary">
            Tipo de evento
            <select
              className="select-control"
              onChange={(event) =>
                setEventType(
                  event.target.value as
                    "" | "zone_dwell" | "person_forklift_proximity",
                )
              }
              value={eventType}
            >
              <option value="">Todos los tipos</option>
              <option value="zone_dwell">Permanencia en zona</option>
              <option value="person_forklift_proximity">
                Proximidad persona–montacargas
              </option>
            </select>
          </label>
          <Button type="submit">Aplicar filtros</Button>
        </form>
      ) : (
        <div className="flex flex-col gap-3 sm:flex-row">
          <label className="flex flex-1 items-center gap-2 rounded-control border border-border bg-surface-elevated px-3 py-2.5 text-sm text-text-secondary focus-within:border-accent">
            <Search aria-hidden="true" size={17} />
            <span className="sr-only">Buscar evento o regla</span>
            <Input
              className="!min-h-0 !border-0 !bg-transparent !p-0 text-foreground"
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Buscar evento o regla"
              type="search"
              value={query}
            />
          </label>
          <label className="grid gap-1 text-xs font-medium text-text-secondary">
            <span className="sr-only">Filtrar por zona</span>
            <select
              className="h-full min-h-10 rounded-control border border-border bg-surface px-3 text-sm text-foreground"
              onChange={(event) => setZone(event.target.value)}
              value={zone}
            >
              <option value="all">Todas las zonas</option>
              {zones.map((item) => (
                <option key={item}>{item}</option>
              ))}
            </select>
          </label>
        </div>
      )}
      {filterError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {filterError}
        </p>
      )}

      <div className="mt-4 flex min-h-11 items-center justify-between gap-3">
        <p role="status" className="text-xs text-text-secondary">
          {loading
            ? "Cargando eventos…"
            : error
              ? "Eventos no disponibles"
              : `${filteredEvents.length} ${environment.dataSource === "api" ? (filteredEvents.length === 1 ? "evento registrado" : "eventos registrados") : filteredEvents.length === 1 ? "candidato simulado" : "candidatos simulados"}`}
        </p>
        {(query || zone !== "all" || hasDraftFilters || hasAppliedFilters) && (
          <Button variant="ghost" onClick={clearFilters}>
            Limpiar filtros
          </Button>
        )}
      </div>
      {loading && (
        <div className="event-loading" aria-hidden="true">
          {Array.from({ length: 5 }, (_, index) => (
            <span key={index} />
          ))}
        </div>
      )}
      {error && (
        <div role="alert" className="mb-4 text-sm text-danger">
          <p>{error}</p>
          <Button
            className="mt-2"
            variant="outline"
            onClick={() => {
              setLoading(true);
              setRetry((current) => current + 1);
            }}
          >
            Reintentar
          </Button>
        </div>
      )}
      {!loading && !error && (
        <>
          <ul
            aria-label={
              environment.dataSource === "api"
                ? "Eventos registrados"
                : "Eventos simulados"
            }
            className="divide-y divide-border xl:hidden"
          >
            {filteredEvents.map((event) => (
              <li className="py-4 first:pt-1 last:pb-0" key={event.id}>
                <div className="flex items-start gap-3">
                  <span className="flex size-9 shrink-0 items-center justify-center rounded-control bg-surface-muted text-accent">
                    <Activity aria-hidden="true" size={17} />
                  </span>
                  <div className="min-w-0 flex-1">
                    <h2 className="text-sm font-semibold text-foreground">
                      {event.detailUrl ? (
                        <a
                          className="underline underline-offset-2"
                          href={event.detailUrl}
                        >
                          {event.title}
                        </a>
                      ) : (
                        event.title
                      )}
                    </h2>
                    <time className="mt-1 block text-xs tabular-nums text-text-secondary">
                      {event.time}
                    </time>
                  </div>
                  <StatusBadge tone={event.tone}>{event.status}</StatusBadge>
                </div>
                <dl className="mt-3 grid grid-cols-2 gap-x-4 gap-y-2 pl-12 text-xs">
                  <div>
                    <dt className="text-text-secondary">Zona</dt>
                    <dd className="mt-0.5 font-medium text-foreground">
                      {event.zone}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-text-secondary">Fuente</dt>
                    <dd className="mt-0.5 font-medium text-foreground">
                      {event.source ?? "No informada"}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-text-secondary">Objetos</dt>
                    <dd className="mt-0.5 font-medium text-foreground">
                      {event.objects}
                    </dd>
                  </div>
                  <div>
                    <dt className="text-text-secondary">Evidencia</dt>
                    <dd className="mt-0.5 font-medium text-foreground">
                      {event.evidenceUrl ? (
                        <a
                          href={event.evidenceUrl}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline underline-offset-2"
                        >
                          Ver evidencia
                        </a>
                      ) : (
                        "Sin evidencia"
                      )}
                    </dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
          <div
            className="mt-2 hidden overflow-x-auto rounded-control focus-visible:outline-accent xl:block"
            role="region"
            aria-label={
              environment.dataSource === "api"
                ? "Tabla de eventos registrados; desplazamiento horizontal disponible"
                : "Tabla de eventos simulados; desplazamiento horizontal disponible"
            }
            tabIndex={0}
          >
            <table className="w-full min-w-180 text-left text-sm">
              <caption className="sr-only">
                {environment.dataSource === "api"
                  ? "Eventos registrados"
                  : "Candidatos de evento simulados"}
              </caption>
              <thead className="border-b border-border text-xs uppercase tracking-wide text-text-secondary">
                <tr>
                  {[
                    "Hora",
                    "Evento",
                    "Fuente",
                    "Zona",
                    "Objetos",
                    "Evidencia",
                  ].map((heading) => (
                    <th
                      className="px-3 py-3 font-semibold"
                      key={heading}
                      scope="col"
                    >
                      {heading}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredEvents.map(
                  ({
                    id,
                    title,
                    zone: eventZone,
                    objects,
                    time,
                    evidenceUrl,
                    source,
                    detailUrl,
                  }) => (
                    <tr
                      className="transition-colors hover:bg-surface-muted"
                      key={id}
                    >
                      <td className="px-3 py-4 tabular-nums text-text-secondary">
                        {time}
                      </td>
                      <td className="px-3 py-4">
                        <div className="flex items-center gap-3">
                          <span className="flex size-9 items-center justify-center rounded-control bg-surface-muted text-accent">
                            <Activity aria-hidden="true" size={17} />
                          </span>
                          <span className="font-semibold text-foreground">
                            {detailUrl ? (
                              <a
                                className="underline underline-offset-2"
                                href={detailUrl}
                              >
                                {title}
                              </a>
                            ) : (
                              title
                            )}
                          </span>
                        </div>
                      </td>
                      <td className="px-3 py-4 text-text-secondary">
                        {source ?? "No informada"}
                      </td>
                      <td className="px-3 py-4 text-text-secondary">
                        {eventZone}
                      </td>
                      <td className="px-3 py-4 text-xs text-text-secondary">
                        {objects}
                      </td>
                      <td className="px-3 py-4 text-xs text-text-secondary">
                        {evidenceUrl ? (
                          <a
                            href={evidenceUrl}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline underline-offset-2"
                          >
                            Ver evidencia
                          </a>
                        ) : (
                          "Sin evidencia"
                        )}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
          </div>
          {filteredEvents.length === 0 ? (
            <p className="py-10 text-center text-sm text-text-secondary">
              {hasAppliedFilters ||
              (environment.dataSource === "mock" && (query || zone !== "all"))
                ? "No se encontraron eventos para los filtros seleccionados."
                : events.length === 0
                  ? environment.dataSource === "api"
                    ? "Todavía no hay eventos registrados."
                    : "No hay eventos mock."
                  : "No se encontraron eventos para los filtros seleccionados."}
            </p>
          ) : null}
        </>
      )}
    </>
  );
}
