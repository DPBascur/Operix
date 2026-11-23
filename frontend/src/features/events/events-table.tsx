"use client";

import { Activity, ChevronDown, Search, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  Fragment,
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
  useTransition,
} from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { EventPreview, EventThumbnail } from "./event-preview";
import {
  evidenceSummary,
  mergeEvidence,
  type EventEvidence,
} from "./event-detail-model";
import type { FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { Input } from "@/components/ui/input";
import { StatusBadge } from "@/components/ui/status-badge";
import {
  eventsService,
  type EventHistoryPage,
} from "@/services/events.service";
import {
  changeEventHistoryMode,
  eventHistoryHref,
  type EventHistoryFilters,
  type EventHistoryQuery,
} from "./event-history-query";
import type { EventListItem } from "@/types/operix";
import { eventTypeName } from "@/services/event-contract";
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

export function EventsTable({ initial }: { initial: EventHistoryQuery }) {
  const { filters } = initial;
  const router = useRouter();
  const [navigating, startTransition] = useTransition();
  const desktop = useSyncExternalStore(
    watchEventWidth,
    () => wideEvents().matches,
    () => false,
  );
  const reduced = useReducedMotion();
  const [expanded, setExpanded] = useState<string | null>(null);
  const animation = reduced ? { duration: 0 } : controlTransition;
  const [result, setResult] = useState<{
    key: string;
    data?: EventHistoryPage;
    error?: string;
  }>();
  const previewId = useId();
  const resultsStart = useRef<HTMLDivElement>(null);
  const updateEvidence = useCallback((id: string, evidence: EventEvidence) => {
    setResult((current) => {
      if (!current?.data) return current;
      return {
        ...current,
        data: {
          ...current.data,
          rows: current.data.rows.map((row) =>
            row.id === id
              ? { ...row, evidence: mergeEvidence(evidence, row.evidence) }
              : row,
          ),
        },
      };
    });
  }, []);
  const [retry, setRetry] = useState(0);
  const [from, setFrom] = useState(() => dateInput(filters.occurredAfter));
  const [to, setTo] = useState(() => dateInput(filters.occurredBefore));
  const [eventType, setEventType] = useState<
    NonNullable<EventHistoryFilters["eventType"]> | ""
  >(filters.eventType ?? "");
  const [source, setSource] = useState<
    NonNullable<EventHistoryFilters["sourceKind"]> | ""
  >(filters.sourceKind ?? "");
  const [camera, setCamera] = useState(filters.cameraId ?? "");
  const [stage, setStage] = useState<
    NonNullable<EventHistoryFilters["evidenceStage"]> | ""
  >(filters.evidenceStage ?? "");
  const [search, setSearch] = useState(filters.search ?? "");
  const [order, setOrder] = useState(filters.order ?? "newest");
  const currentHref = eventHistoryHref(initial);
  const key = `${currentHref}#${retry}`;
  const loading = result?.key !== key;
  const data = loading ? undefined : result.data;
  const error = loading ? undefined : result.error;

  function navigate(query: EventHistoryQuery) {
    setExpanded(null);
    const href = eventHistoryHref(query);
    if (href === currentHref) {
      setRetry((current) => current + 1);
      return;
    }
    startTransition(() => router.push(href, { scroll: false }));
  }
  function changePage(page: number) {
    navigate({ ...initial, page });
    resultsStart.current?.scrollIntoView({ block: "start" });
  }
  function dossier(url: string) {
    return currentHref === "/events"
      ? url
      : `${url}?${new URLSearchParams({ back: currentHref })}`;
  }

  function evidenceButton(row: EventListItem) {
    return (
      <div className="event-preview-trigger">
        {row.evidence?.png && (
          <EventThumbnail
            key={row.evidence.png}
            url={row.evidence.png}
            title={row.title}
          />
        )}
        {row.evidence &&
          (row.evidence.status || row.evidence.png || row.evidence.clip) && (
            <span>{evidenceSummary(row.evidence)}</span>
          )}
        {row.detailUrl && (
          <Button
            variant="outline"
            size="small"
            aria-expanded={expanded === row.id}
            aria-controls={
              expanded === row.id
                ? `${previewId}-${desktop}-${row.id}`
                : undefined
            }
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
    const controller = new AbortController();
    eventsService.listPage(initial, controller.signal).then(
      (page) => {
        if (controller.signal.aborted) return;
        setResult({ key, data: page });
        if (page.page !== initial.page) {
          router.replace(eventHistoryHref({ ...initial, page: page.page }), {
            scroll: false,
          });
        }
      },
      (failure: unknown) => {
        if (!controller.signal.aborted)
          setResult({ key, error: historyError(failure) });
      },
    );
    return () => controller.abort();
  }, [initial, key, router]);
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
    navigate({
      all: initial.all,
      page: 1,
      filters: {
        ...filters,
        occurredAfter: occurredAfter ?? undefined,
        occurredBefore: occurredBefore ?? undefined,
        eventType: eventType || undefined,
        sourceKind: source || undefined,
        cameraId: camera.trim().toLowerCase() || undefined,
        evidenceStage: stage || undefined,
        search: search.trim() || undefined,
        order: order === "oldest" ? order : undefined,
      },
    });
  }
  function clearFilters() {
    setFrom("");
    setTo("");
    setEventType("");
    setSource("");
    setCamera("");
    setStage("");
    setSearch("");
    setOrder("newest");
    setFilterError(null);
    navigate({ all: initial.all, page: 1, filters: {} });
  }
  const hasAppliedFilters = Object.entries(filters).some(
    ([name, value]) => name !== "order" && Boolean(value),
  );
  const hasDraftFilters = Boolean(
    from ||
    to ||
    eventType ||
    source ||
    camera ||
    stage ||
    search ||
    order === "oldest",
  );
  const chips: { field: keyof EventHistoryFilters; label: string }[] = [];
  if (filters.search) chips.push({ field: "search", label: `Búsqueda: ${filters.search}` });
  if (filters.eventType) chips.push({ field: "eventType", label: eventTypeName(filters.eventType) });
  if (filters.sourceKind) chips.push({ field: "sourceKind", label: sourceNames[filters.sourceKind] ?? filters.sourceKind });
  if (filters.cameraId) chips.push({ field: "cameraId", label: `Cámara ${filters.cameraId.slice(-2)}` });
  if (filters.occurredAfter) chips.push({ field: "occurredAfter", label: `Desde ${dateInput(filters.occurredAfter).replace("T", " ")}` });
  if (filters.occurredBefore) chips.push({ field: "occurredBefore", label: `Hasta ${dateInput(filters.occurredBefore).replace("T", " ")}` });
  if (filters.evidenceStage) chips.push({ field: "evidenceStage", label: {
    pending: "Evidencia pendiente", finished: "Evidencia finalizada", legacy: "Evidencia histórica",
  }[filters.evidenceStage] });
  if (filters.zoneId) chips.push({ field: "zoneId", label: `Zona: ${filters.zoneId}` });
  if (filters.sourceSha256) chips.push({ field: "sourceSha256", label: `Video: ${filters.sourceSha256.slice(0, 12)}…` });
  if (filters.order) chips.push({ field: "order", label: "Más antiguos primero" });
  const filteredEvents = data?.rows ?? [];
  const offset = data ? (data.page - 1) * data.pageSize : 0;

  return (
    <>
      <form className="event-search" role="search" onSubmit={applyFilters}>
        <div className="event-search-main">
          <label className="event-search-field">
            <span>Buscar eventos</span>
            <div>
              <Search size={17} aria-hidden="true" />
              <Input type="search" maxLength={120} value={search}
                placeholder="Zona, regla, vista o fuente"
                onChange={(event) => setSearch(event.target.value)} />
            </div>
          </label>
        <label className="grid gap-1 text-xs font-medium text-text-secondary">
          Tipo de evento
          <select
            className="select-control"
            onChange={(event) =>
              setEventType(event.target.value as typeof eventType)
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
          <Button type="submit" disabled={navigating}>Buscar</Button>
        </div>
        <details className="event-search-advanced">
          <summary><SlidersHorizontal size={17} aria-hidden="true" /> Filtros avanzados <ChevronDown size={16} aria-hidden="true" /></summary>
          <div className="event-search-advanced-grid event-filter-entry">
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
          Cámara de laboratorio
          <Input
            value={camera}
            onChange={(event) => setCamera(event.target.value)}
            pattern="[Ll][Aa][Bb]-[Cc][Aa][Mm]-[0-9]{2}"
            title="ID de cámara, por ejemplo lab-cam-01"
            placeholder="lab-cam-01"
          />
        </label>
        <label className="grid gap-1 text-xs font-medium text-text-secondary">
          Estado de publicación de evidencia
          <select
            className="select-control"
            value={stage}
            onChange={(event) => setStage(event.target.value as typeof stage)}
          >
            <option value="">Todos los estados</option>
            <option value="pending">Pendiente de confirmación</option>
            <option value="finished">Publicación finalizada</option>
            <option value="legacy">Sin seguimiento de publicación</option>
          </select>
        </label>
        <label className="grid gap-1 text-xs font-medium text-text-secondary">
          Orden
          <select
            className="select-control"
            value={order}
            onChange={(event) => setOrder(event.target.value)}
          >
            <option value="newest">Más recientes primero</option>
            <option value="oldest">Más antiguos primero</option>
          </select>
        </label>
          </div>
          <Button type="submit" variant="outline" disabled={navigating}>Aplicar filtros</Button>
        </details>
        {(chips.length > 0 || hasDraftFilters) && (
          <div className="event-search-chips" aria-label="Filtros activos">
            {chips.map(({ field, label }) => (
              <button key={field} type="button" disabled={navigating} aria-label={`Quitar filtro: ${label}`}
                onClick={() => navigate({ ...initial, page: 1, filters: { ...filters, [field]: undefined } })}>
                {label} <X size={14} aria-hidden="true" />
              </button>
            ))}
            <Button type="button" variant="ghost" size="small" onClick={clearFilters} disabled={navigating}>Restablecer</Button>
          </div>
        )}
      </form>
      {filterError && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {filterError}
        </p>
      )}
      <div
        ref={resultsStart}
        className="my-4 flex min-h-11 flex-wrap items-center justify-between gap-3"
      >
        <p role="status" className="text-sm tabular-nums text-text-secondary">
          {filteredEvents.length
            ? `Mostrando ${offset + 1}–${offset + filteredEvents.length} de ${data?.count} ${data?.count === 1 ? "evento" : "eventos"}`
            : data?.count === 0
              ? "0 eventos"
              : error ? "Consulta no disponible" : "Consultando registros…"}
        </p>
      </div>
      {loading && (
        <OperixScanLoader
          variant="panel"
          className="dashboard-loading"
          message="Cargando eventos…"
        />
      )}
      {!loading && error && (
        <div role="alert" className="mb-4 text-sm text-danger">
          <p>{error}</p>
          <Button
            className="mt-2"
            variant="outline"
            onClick={() => {
              setRetry((current) => current + 1);
            }}
          >
            Reintentar
          </Button>
        </div>
      )}
      {data && (
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
                        panelId={`${previewId}-false-${event.id}`}
                        onEvidence={updateEvidence}
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
                                panelId={`${previewId}-true-${id}`}
                                onEvidence={updateEvidence}
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
      {data && (
        <div className="mt-4 flex flex-wrap items-center justify-end gap-3 border-t border-border pt-3">
          {data.totalPages > 1 && (
            <nav
              aria-label="Paginación de eventos"
              className="me-auto flex flex-wrap items-center gap-2"
            >
              <Button
                variant="outline"
                onClick={() => changePage(data.page - 1)}
                disabled={navigating || data.page <= 1}
              >
                Anterior
              </Button>
              <span className="px-1 text-sm tabular-nums text-text-secondary">
                {initial.all ? "Bloque" : "Página"} {data.page} de{" "}
                {data.totalPages}
              </span>
              <Button
                variant="outline"
                onClick={() => changePage(data.page + 1)}
                disabled={navigating || data.page >= data.totalPages}
              >
                {initial.all ? "Cargar más" : "Siguiente"}
              </Button>
            </nav>
          )}
          <Button variant="outline" type="button" disabled={navigating}
            onClick={() => navigate(changeEventHistoryMode({ ...initial, page: data.page }))}>
            {initial.all ? "Volver a 15 por página" : "Ver todos"}
          </Button>
        </div>
      )}
    </>
  );
}
