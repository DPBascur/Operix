"use client";

import { Activity } from "lucide-react";
import Link from "next/link";
import { Fragment, useEffect, useState, useSyncExternalStore } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { EventPreview, EventThumbnail } from "./event-preview";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import { eventsService } from "@/services/events.service";
import type { EventQuery } from "@/services/adapters/frontend-data.adapter";
import type { EventListItem } from "@/types/operix";
import { historyError, sourceNames } from "@/features/dashboard/history-model";
import { controlTransition } from "@/lib/motion/presets";

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

function dateInput(value?: string) {
  return value ? formatLocalMinute(new Date(value)) : "";
}

function wideEvents() {
  return window.matchMedia("(min-width: 80rem)");
}
function watchEventWidth(callback: () => void) {
  const query = wideEvents();
  query.addEventListener("change", callback);
  return () => query.removeEventListener("change", callback);
}

export function EventsTable({ initial }: { initial: EventQuery }) {
  const desktop = useSyncExternalStore(
    watchEventWidth,
    () => wideEvents().matches,
    () => false,
  );
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState<string | null>(null);
  const animation = reduced ? { duration: 0 } : controlTransition;
  const [events, setEvents] = useState<EventListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retry, setRetry] = useState(0);
  const [from, setFrom] = useState(() => dateInput(initial.occurredAfter));
  const [to, setTo] = useState(() => dateInput(initial.occurredBefore));
  const [eventType, setEventType] = useState<
    | ""
    | "zone_dwell"
    | "person_forklift_proximity"
    | "zone_entry"
    | "zone_coexistence"
  >(initial.eventType ?? "");
  const [source, setSource] = useState<
    NonNullable<EventQuery["sourceKind"]> | ""
  >(initial.sourceKind ?? "");
  const [filters, setFilters] = useState<EventQuery>(initial);
  function updateFilters(values: EventQuery) {
    const params = new URLSearchParams();
    if (values.occurredAfter)
      params.set("occurred_after", values.occurredAfter);
    if (values.occurredBefore)
      params.set("occurred_before", values.occurredBefore);
    if (values.eventType) params.set("event_type", values.eventType);
    if (values.sourceKind) params.set("source_kind", values.sourceKind);
    if (values.sourceSha256) params.set("source_sha256", values.sourceSha256);
    window.history.replaceState(
      null,
      "",
      params.size ? `/events?${params}` : "/events",
    );
    setFilters(values);
    setExpanded(null);
  }
  function dossier(url: string) {
    const params = new URLSearchParams();
    if (filters.occurredAfter)
      params.set("occurred_after", filters.occurredAfter);
    if (filters.occurredBefore)
      params.set("occurred_before", filters.occurredBefore);
    if (filters.eventType) params.set("event_type", filters.eventType);
    if (filters.sourceKind) params.set("source_kind", filters.sourceKind);
    if (filters.sourceSha256) params.set("source_sha256", filters.sourceSha256);
    return params.size
      ? `${url}?${new URLSearchParams({ back: `/events?${params}` })}`
      : url;
  }

  function evidenceButton(row: EventListItem) {
    return (
      <div className="event-preview-trigger">
        <EventThumbnail
          key={row.evidenceUrl}
          url={row.evidenceUrl}
          title={row.title}
        />
        {row.detailUrl && (
          <Button
            variant="outline"
            size="small"
            aria-expanded={expanded === row.id}
            onClick={() =>
              setExpanded((current) => (current === row.id ? null : row.id))
            }
          >
            {expanded === row.id ? "Cerrar evidencia" : "Ver evidencia"}
          </Button>
        )}
      </div>
    );
  }
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
        setError(historyError(failure));
        setLoading(false);
      },
    );
    return () => {
      active = false;
    };
  }, [filters, retry]);
  function applyFilters(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const occurredAfter =
      from === dateInput(filters.occurredAfter)
        ? filters.occurredAfter
        : from
          ? localDateTimeToIso(from)
          : undefined;
    const occurredBefore =
      to === dateInput(filters.occurredBefore)
        ? filters.occurredBefore
        : to
          ? localDateTimeToIso(to)
          : undefined;
    if ((from && !occurredAfter) || (to && !occurredBefore)) {
      setFilterError("Ingresa fechas y horas locales válidas.");
      return;
    }
    if (
      occurredAfter &&
      occurredBefore &&
      Date.parse(occurredAfter) > Date.parse(occurredBefore)
    ) {
      setFilterError("La fecha desde no puede ser posterior a la fecha hasta.");
      return;
    }
    setFilterError(null);
    setLoading(true);
    updateFilters({
      occurredAfter: occurredAfter ?? undefined,
      occurredBefore: occurredBefore ?? undefined,
      eventType: eventType || undefined,
      sourceKind: source || undefined,
      sourceSha256: filters.sourceSha256,
    });
    setRetry((current) => current + 1);
  }
  function clearFilters() {
    setFrom("");
    setTo("");
    setEventType("");
    setSource("");
    setFilterError(null);
    setLoading(true);
    updateFilters({});
    setRetry((current) => current + 1);
  }
  const hasAppliedFilters = Object.values(filters).some(Boolean);
  const hasDraftFilters = Boolean(from || to || eventType || source);
  const filteredEvents = events;

  return (
    <>
      <form
        className="grid gap-3 border-b border-border pb-5 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_1fr_auto] xl:items-end"
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
                  | ""
                  | "zone_dwell"
                  | "person_forklift_proximity"
                  | "zone_entry"
                  | "zone_coexistence",
              )
            }
            value={eventType}
          >
            <option value="">Todos los tipos</option>
            <option value="zone_entry">Ingreso observado</option>
            <option value="zone_coexistence">Presencia simultánea</option>
            <option value="zone_dwell">Permanencia en zona</option>
            <option value="person_forklift_proximity">
              Proximidad persona–montacargas
            </option>
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-text-secondary">
          Procedencia
          <select
            className="select-control"
            value={source}
            onChange={(e) => setSource(e.target.value as typeof source)}
          >
            <option value="">Todas</option>
            {Object.entries(sourceNames).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        <Button type="submit">Aplicar filtros</Button>
      </form>
      {filterError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {filterError}
        </p>
      )}
      {filters.sourceSha256 && (
        <p className="mt-2 text-xs text-text-secondary">
          Video filtrado · SHA-256 {filters.sourceSha256.slice(0, 12)}…
        </p>
      )}

      <div className="mt-4 flex min-h-11 items-center justify-between gap-3">
        <p role="status" className="text-xs text-text-secondary">
          {loading
            ? "Cargando eventos…"
            : error
              ? "Eventos no disponibles"
              : `${filteredEvents.length} ${filteredEvents.length === 1 ? "evento registrado" : "eventos registrados"}`}
        </p>
        {(hasDraftFilters || hasAppliedFilters) && (
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
            aria-label="Eventos registrados"
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
                        <Link
                          className="underline underline-offset-2"
                          href={dossier(event.detailUrl)}
                        >
                          {event.title}
                        </Link>
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
                      <small className="block text-text-secondary">
                        {event.sourceKindLabel}
                      </small>
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
                      {!desktop && evidenceButton(event)}
                    </dd>
                  </div>
                </dl>
                <AnimatePresence initial={false}>
                  {!desktop && expanded === event.id && event.detailUrl && (
                    <motion.div
                      initial={{ opacity: 0 }}
                      animate={{ opacity: 1 }}
                      exit={{ opacity: 0 }}
                      transition={animation}
                      key={event.id}
                    >
                      <EventPreview
                        row={event}
                        detailUrl={dossier(event.detailUrl)}
                      />
                    </motion.div>
                  )}
                </AnimatePresence>
              </li>
            ))}
          </ul>
          <div
            className="mt-2 hidden overflow-x-auto rounded-control focus-visible:outline-accent xl:block"
            role="region"
            aria-label="Tabla de eventos registrados; desplazamiento horizontal disponible"
            tabIndex={0}
          >
            <table className="w-full min-w-180 text-left text-sm">
              <caption className="sr-only">Eventos registrados</caption>
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
                {filteredEvents.map((row) => {
                  const {
                    id,
                    title,
                    zone: eventZone,
                    objects,
                    time,
                    source,
                    sourceKindLabel,
                    detailUrl,
                  } = row;
                  return (
                    <Fragment key={id}>
                      <tr className="transition-colors hover:bg-surface-muted">
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
                                <Link
                                  className="underline underline-offset-2"
                                  href={dossier(detailUrl)}
                                >
                                  {title}
                                </Link>
                              ) : (
                                title
                              )}
                            </span>
                          </div>
                        </td>
                        <td className="px-3 py-4 text-text-secondary">
                          {source ?? "No informada"}
                          <small className="block">{sourceKindLabel}</small>
                        </td>
                        <td className="px-3 py-4 text-text-secondary">
                          {eventZone}
                        </td>
                        <td className="px-3 py-4 text-xs text-text-secondary">
                          {objects}
                        </td>
                        <td className="px-3 py-4 text-xs text-text-secondary">
                          {desktop && evidenceButton(row)}
                        </td>
                      </tr>
                      <AnimatePresence initial={false}>
                        {desktop && expanded === id && detailUrl && (
                          <motion.tr
                            initial={{ opacity: 0 }}
                            animate={{ opacity: 1 }}
                            exit={{ opacity: 0 }}
                            transition={animation}
                            key={id}
                          >
                            <td colSpan={6} className="p-3">
                              <EventPreview
                                row={row}
                                detailUrl={dossier(detailUrl)}
                              />
                            </td>
                          </motion.tr>
                        )}
                      </AnimatePresence>
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
          {filteredEvents.length === 0 ? (
            <p className="py-10 text-center text-sm text-text-secondary">
              {hasAppliedFilters
                ? "No se encontraron eventos para los filtros seleccionados. Amplíe el período o limpie los filtros."
                : "Todavía no hay eventos registrados."}
            </p>
          ) : null}
        </>
      )}
    </>
  );
}
