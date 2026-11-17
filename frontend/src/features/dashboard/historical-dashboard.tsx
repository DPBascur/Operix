"use client";
import { EventCount } from "@/components/motion/event-count";
import { PageTitle } from "@/components/layout/page-title";
import { apiFetch } from "@/services/browser-session";
import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import {
  ArrowDownRight,
  ArrowUpRight,
  ArrowRight,
  RefreshCw,
} from "lucide-react";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { Button } from "@/components/ui/button";
import { environment } from "@/config/environment";
import { eventTypeName } from "@/services/event-contract";
import {
  enterTransition,
  sectionTransition,
  revealVariants,
  sectionEntrance,
} from "@/lib/motion/presets";
import {
  historyHref,
  sourceNames,
  parseHistory,
  parseFrequency,
  formatHistoryTime,
  historyError,
  monthUtcBounds,
  summarizeApiHistory,
  summarizeHistory,
  type EventFrequency,
  type HistoryEvent,
} from "./history-model";

import {
  DailyEvents,
  HeatLegend,
  SpatialHeatmap,
  TemporalHeatmap,
} from "./analytics-charts";
import { spatialHistory } from "./spatial-history";
import styles from "./analytics-charts.module.css";

const eventName = eventTypeName;
const chartDraw = { ...enterTransition, duration: 0.85 };
const barVariants = { empty: { scaleX: 0 }, filled: { scaleX: 1 } };

export function HistoricalDashboard({
  overview = false,
  initialMonth,
  initialType = "",
  initialSource = "",
}: {
  overview?: boolean;
  initialMonth?: string;
  initialType?: string;
  initialSource?: string;
}) {
  const reduceMotion = useReducedMotion();
  const currentMonth = new Date().toISOString().slice(0, 7);
  const [month, setMonth] = useState(initialMonth ?? currentMonth);
  const anchor = new Date(`${currentMonth}-01T00:00:00Z`);
  const periods = Array.from({ length: 12 }, (_, i) =>
    new Date(Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() - i, 1))
      .toISOString()
      .slice(0, 7),
  );
  if (initialMonth && !periods.includes(initialMonth))
    periods.push(initialMonth);
  const [type, setType] = useState(initialType);
  const [source, setSource] = useState(initialSource);
  const [zone, setZone] = useState("");
  const [video, setVideo] = useState("");
  const [facets, setFacets] = useState<{
    zones: { label: string }[];
    videos: { sha: string; name: string }[];
  }>({ zones: [], videos: [] });
  function resetFacets() {
    setZone("");
    setVideo("");
    setFacets({ zones: [], videos: [] });
  }
  const applied = useMemo(() => {
    const bounds = monthUtcBounds(month);
    const params = new URLSearchParams({
      occurred_after: bounds.start,
      occurred_before: bounds.end,
    });
    if (type) params.set("event_type", type);
    if (source) params.set("source_kind", source);
    if (zone) params.set("zone_id", zone);
    if (video) params.set("source_sha256", video);
    return params;
  }, [month, type, source, zone, video]);
  const queryKey = applied.toString();
  const [records, setRecords] = useState<HistoryEvent[]>([]);
  const [frequencies, setFrequencies] = useState<{
    key: string;
    current: EventFrequency;
    previous: EventFrequency;
    zones: number;
    analyses: number;
    prior?: { total: number; zones: number; analyses: number };
    animateRecent: boolean;
    hasRecent: boolean;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    async function load() {
      setLoading(true);
      setError(null);
      try {
        if (!environment.apiBaseUrl)
          throw new Error(
            "Configure la dirección de la API para consultar el histórico real.",
          );
        const base = environment.apiBaseUrl.replace(/\/$/, "");
        const bounds = monthUtcBounds(month);
        const previous = new URLSearchParams(applied);
        previous.set("occurred_after", bounds.previous);
        previous.set(
          "occurred_before",
          monthUtcBounds(bounds.previous.slice(0, 7)).end,
        );
        const endpoints = [
          `${base}/events/?${applied}`,
          `${base}/events/frequencies/?${applied}`,
          `${base}/events/frequencies/?${previous}`,
        ];
        const responses = await Promise.all(
          endpoints.map((url) =>
            apiFetch(url, { cache: "no-store", signal: controller.signal }),
          ),
        );
        if (responses.some((response) => !response.ok))
          throw new Error(
            "No fue posible consultar los registros. Revise la conexión y vuelva a intentar.",
          );
        const [eventsPayload, currentPayload, previousPayload] =
          await Promise.all(responses.map((response) => response.json()));
        const data = parseHistory(eventsPayload);
        const current = parseFrequency(currentPayload);
        const previousFrequency = parseFrequency(previousPayload);
        const summary = summarizeApiHistory(
          data,
          month,
          current,
          previousFrequency,
        );
        if (active) {
          setRecords(data);
          if (!zone && !video)
            setFacets({ zones: summary.zones, videos: summary.videos });
          setFrequencies((last) => ({
            key: queryKey,
            current,
            previous: previousFrequency,
            zones: summary.zones.length,
            analyses: summary.runsWithEvents,
            prior:
              (last && {
                total: last.current.total,
                zones: last.zones,
                analyses: last.analyses,
              }) ||
              undefined,
            animateRecent: !last?.hasRecent && summary.recent.length > 0,
            hasRecent: Boolean(last?.hasRecent || summary.recent.length),
          }));
        }
      } catch (cause) {
        if (active) setError(historyError(cause));
      } finally {
        clearTimeout(timeout);
        if (active) setLoading(false);
      }
    }
    void load();
    return () => {
      active = false;
      clearTimeout(timeout);
      controller.abort();
    };
  }, [applied, queryKey, month, revision, zone, video]);
  const summary = useMemo(
    () =>
      frequencies?.key === queryKey
        ? summarizeApiHistory(
            records,
            month,
            frequencies.current,
            frequencies.previous,
          )
        : summarizeHistory([], month),
    [queryKey, records, frequencies, month],
  );
  const groups = useMemo(
    () => (overview ? [] : spatialHistory(records)),
    [overview, records],
  );
  const currentLabel = new Intl.DateTimeFormat("es-CL", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(`${month}-01T00:00:00Z`));
  const busiest = summary.hours.reduce(
    (best, h) => (h.count > best.count ? h : best),
    summary.hours[0],
  );
  return (
    <div
      className={`insights-page market-dashboard${overview ? " dashboard-overview" : ` ${styles.indicators}`}`}
    >
      <header className="insights-heading app-page-heading">
        <div>
          <PageTitle animate={overview}>
            {overview ? "Resumen de eventos" : "Indicadores de eventos"}
          </PageTitle>
          <p>Actividad operacional · {currentLabel}</p>
        </div>
        <Link
          href={
            overview
              ? `/indicators?${new URLSearchParams({ month, type, source })}`
              : historyHref(applied)
          }
          className="button button-primary"
        >
          {overview ? "Ver indicadores" : "Ver historial filtrado"}{" "}
          <ArrowRight size={16} />
        </Link>
      </header>
      <div className="history-controls">
        <label className="month-control">
          Período UTC
          <select
            value={month}
            onChange={(e) => {
              setMonth(e.target.value);
              resetFacets();
            }}
          >
            {periods.map((value) => {
              const d = new Date(`${value}-01T00:00:00Z`);
              return (
                <option key={value} value={value}>
                  {d.toLocaleDateString("es-CL", {
                    month: "long",
                    year: "numeric",
                    timeZone: "UTC",
                  })}
                </option>
              );
            })}
          </select>
        </label>
        <label className="month-control">
          Tipo de evento
          <select
            value={type}
            onChange={(e) => {
              setType(e.target.value);
              resetFacets();
            }}
          >
            <option value="">Todos</option>
            <option value="zone_entry">Ingreso observado</option>
            <option value="zone_coexistence">Presencia simultánea</option>
            <option value="zone_dwell">Permanencia en zona</option>
            <option value="person_forklift_proximity">
              Proximidad persona–montacargas
            </option>
          </select>
        </label>
        <label className="month-control">
          Procedencia
          <select
            value={source}
            onChange={(e) => {
              setSource(e.target.value);
              resetFacets();
            }}
          >
            <option value="">Todas</option>
            {Object.entries(sourceNames).map(([key, name]) => (
              <option key={key} value={key}>
                {name}
              </option>
            ))}
          </select>
        </label>
        {!overview && (
          <>
            <label className="month-control">
              Zona
              <select
                value={zone}
                onChange={(event) => setZone(event.target.value)}
              >
                <option value="">Todas las zonas</option>
                {facets.zones.map(({ label }) => (
                  <option key={label} value={label}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="month-control">
              Video identificado
              <select
                value={video}
                onChange={(event) => setVideo(event.target.value)}
              >
                <option value="">Todos los videos</option>
                {facets.videos.map(({ sha, name }) => (
                  <option key={sha} value={sha}>
                    {name} · {sha.slice(0, 8)}
                  </option>
                ))}
              </select>
            </label>
          </>
        )}
        <Button
          variant="outline"
          loading={loading}
          onClick={() => setRevision((r) => r + 1)}
        >
          <RefreshCw size={15} /> {loading ? "Actualizando…" : "Actualizar"}
        </Button>
      </div>
      <p className="history-source-caption">
        Eventos registrados en el período UTC seleccionado. Cada evento indica
        una condición configurada satisfecha. Una carga manual puede ser un
        ensayo.
      </p>
      {!error && frequencies?.key !== queryKey ? (
        <OperixScanLoader
          className="dashboard-loading"
          variant="panel"
          message="Consultando el histórico…"
        />
      ) : error ? (
        <div className="feedback-panel" role="alert">
          <h3>No se pudo cargar el histórico</h3>
          <p>{error}</p>
          <Button onClick={() => setRevision((r) => r + 1)}>
            Reintentar consulta
          </Button>
        </div>
      ) : (
        <>
          {overview && (
            <motion.section
              className="kpi-strip"
              aria-label="Estadísticas del período"
              initial={reduceMotion || frequencies?.prior ? false : "hidden"}
              animate="visible"
              transition={{ staggerChildren: reduceMotion ? 0 : 0.045 }}
            >
              <motion.div
                variants={revealVariants}
                transition={enterTransition}
              >
                <span>Eventos del período</span>
                <strong>
                  <EventCount
                    value={summary.total}
                    from={frequencies?.prior?.total}
                  />
                </strong>
                <small>{currentLabel}</small>
              </motion.div>
              <motion.div
                variants={revealVariants}
                transition={enterTransition}
              >
                <span>Frente al mes anterior</span>
                <strong className="comparison-value">
                  {summary.change === null
                    ? "—"
                    : `${summary.change > 0 ? "+" : ""}${summary.change.toFixed(1)} %`}
                  {summary.change !== null &&
                    (summary.change <= 0 ? (
                      <ArrowDownRight size={23} />
                    ) : (
                      <ArrowUpRight size={23} />
                    ))}
                </strong>
                <small>
                  {summary.previousCount} registros anteriores
                  {summary.previousCount === 0
                    ? " · sin base de comparación"
                    : ""}
                </small>
              </motion.div>
              <motion.div
                variants={revealVariants}
                transition={enterTransition}
              >
                <span>Zonas con registros</span>
                <strong>
                  <EventCount
                    value={summary.zones.length}
                    from={frequencies?.prior?.zones}
                  />
                </strong>
                <small>Ubicaciones en el período</small>
              </motion.div>
              <motion.div
                variants={revealVariants}
                transition={enterTransition}
              >
                <span>Análisis con eventos</span>
                <strong>
                  <EventCount
                    value={summary.runsWithEvents}
                    from={frequencies?.prior?.analyses}
                  />
                </strong>
                <small>Análisis distintos entre estos registros</small>
              </motion.div>
            </motion.section>
          )}
          {!overview && (
            <section
              className={styles.kpis}
              aria-label="Resumen de indicadores"
              aria-busy={loading}
            >
              <div>
                <span>Eventos registrados</span>
                <strong>
                  <EventCount
                    value={summary.total}
                    from={frequencies?.prior?.total}
                  />
                </strong>
              </div>
              {summary.types[0] && (
                <div>
                  <span>Tipo con más registros</span>
                  <strong>{eventName(summary.types[0].label)}</strong>
                  <small>{summary.types[0].count} eventos</small>
                </div>
              )}
              {summary.zones[0] && (
                <div>
                  <span>Zona con más registros</span>
                  <strong>{summary.zones[0].label}</strong>
                  <small>{summary.zones[0].count} eventos</small>
                </div>
              )}
              {!!busiest.count && (
                <div>
                  <span>Hora con más registros · Santiago</span>
                  <strong>{String(busiest.hour).padStart(2, "0")}:00</strong>
                  <small>{busiest.count} eventos</small>
                </div>
              )}
              {summary.videos[0] && (
                <div>
                  <span>Video con más registros</span>
                  <strong>{summary.videos[0].name}</strong>
                  <small>{summary.videos[0].count} eventos</small>
                </div>
              )}
            </section>
          )}
          {summary.total === 0 ? (
            <motion.div
              className="feedback-panel"
              initial={
                reduceMotion || frequencies?.prior
                  ? false
                  : { opacity: 0.8, filter: "blur(2px)" }
              }
              animate={{ opacity: 1, filter: "blur(0px)" }}
              transition={enterTransition}
            >
              <h3>No existen registros para este período</h3>
              <p>Pruebe otro mes o amplíe los filtros.</p>
            </motion.div>
          ) : (
            <>
              {!overview && (
                <>
                  <DailyEvents
                    month={month}
                    days={summary.days}
                    filters={applied}
                    queryKey={queryKey}
                  />
                  <div className={styles.patterns}>
                    <TemporalHeatmap matrix={summary.timeMatrix} />
                    <SpatialHeatmap
                      groups={groups}
                      total={summary.total}
                      back={historyHref(applied)}
                    />
                    <section className="insight-panel">
                      <div className="panel-heading">
                        <div>
                          <h3>Recurrencia por zona</h3>
                          <p>
                            {summary.zones[0].label} reúne{" "}
                            {summary.zones[0].count} de {summary.total}{" "}
                            registros del período.
                          </p>
                        </div>
                      </div>
                      <ol className="zone-ranking">
                        {summary.zones.map((z, i) => (
                          <motion.li
                            key={`${queryKey}-${z.label}`}
                            initial={reduceMotion ? false : "empty"}
                            animate="filled"
                          >
                            <div>
                              <Link
                                className="text-link"
                                href={historyHref(applied, {
                                  zone_id: z.label,
                                })}
                              >
                                {z.label}
                              </Link>
                              <b>{z.count}</b>
                            </div>
                            <span
                              className="zone-frequency-track"
                              role="meter"
                              aria-valuemin={0}
                              aria-valuemax={summary.total}
                              aria-valuenow={z.count}
                              aria-label={z.label}
                            >
                              <motion.span
                                className="zone-frequency-fill"
                                style={{
                                  width: `${(100 * z.count) / summary.total}%`,
                                }}
                                variants={barVariants}
                                transition={
                                  reduceMotion
                                    ? { duration: 0 }
                                    : {
                                        ...chartDraw,
                                        delay: Math.min(i, 5) * 0.045,
                                      }
                                }
                              />
                            </span>
                          </motion.li>
                        ))}
                      </ol>
                    </section>
                    <section className="insight-panel">
                      <div className="panel-heading">
                        <div>
                          <h3>Distribución horaria</h3>
                          <p>
                            Hora de Santiago de Chile para los eventos del
                            período UTC seleccionado. No representa nivel de
                            riesgo.
                          </p>
                        </div>
                      </div>
                      <HeatLegend max={busiest.count} />
                      <div className="hour-heatmap">
                        {summary.hours.map((h) => (
                          <div key={h.hour}>
                            <span>{String(h.hour).padStart(2, "0")}</span>
                            <motion.span
                              key={queryKey}
                              className="heat-cell"
                              initial={reduceMotion ? false : { opacity: 0.2 }}
                              animate={{ opacity: 1 }}
                              transition={
                                reduceMotion
                                  ? { duration: 0 }
                                  : {
                                      ...enterTransition,
                                      delay: h.hour * 0.018,
                                    }
                              }
                              style={{
                                backgroundColor: `color-mix(in srgb, var(--primary) ${h.count ? 16 + (30 * h.count) / Math.max(1, busiest.count) : 0}%, var(--surface-muted))`,
                              }}
                              title={`${String(h.hour).padStart(2, "0")}:00 en Santiago · ${h.count} eventos`}
                              aria-label={`${String(h.hour).padStart(2, "0")}:00 en Santiago, ${h.count} eventos`}
                            />
                          </div>
                        ))}
                      </div>
                      <details className="chart-data">
                        <summary>Ver valores horarios</summary>
                        <div className="daily-data">
                          {summary.hours.map((h) => (
                            <span key={h.hour}>
                              {String(h.hour).padStart(2, "0")}:00 ·{" "}
                              <b>{h.count}</b>
                            </span>
                          ))}
                        </div>
                      </details>
                      <p className="insight-caption">
                        {busiest.count
                          ? `Mayor frecuencia observada a las ${String(busiest.hour).padStart(2, "0")}:00, hora de Santiago (${busiest.count} registros).`
                          : "No hay actividad en este período."}
                      </p>
                      <div className="type-breakdown">
                        <h4>Por tipo de evento</h4>
                        {summary.types.map((t) => (
                          <p key={t.label}>
                            <Link
                              className="text-link"
                              href={historyHref(applied, {
                                event_type: t.label,
                              })}
                            >
                              {eventName(t.label)}
                            </Link>
                            <strong>
                              {t.count}{" "}
                              <small>
                                ({((t.count / summary.total) * 100).toFixed(0)}{" "}
                                %)
                              </small>
                            </strong>
                          </p>
                        ))}
                      </div>
                    </section>
                    <section className="insight-panel">
                      <div className="panel-heading">
                        <div>
                          <h3>Eventos por procedencia</h3>
                          <p>
                            Clasificación registrada en la fuente del evento.
                          </p>
                        </div>
                      </div>
                      <div className="type-breakdown">
                        {summary.sources.map(({ label, count }) => (
                          <p key={label}>
                            <Link
                              className="text-link"
                              href={historyHref(applied, {
                                source_kind: label,
                              })}
                            >
                              {sourceNames[label as keyof typeof sourceNames]}
                            </Link>
                            <strong>{count}</strong>
                          </p>
                        ))}
                      </div>
                      <div className="type-breakdown">
                        <h4>Por video identificado</h4>
                        {summary.videos.length === 0 && (
                          <p>No hay videos con huella registrada.</p>
                        )}
                        {summary.videos.length > 10 && (
                          <p>
                            10 de {summary.videos.length} videos, ordenados por
                            registros.
                          </p>
                        )}
                        {summary.videos
                          .slice(0, 10)
                          .map(({ sha, name, count }) => (
                            <p key={sha}>
                              <Link
                                className="text-link min-w-0 break-all"
                                href={historyHref(applied, {
                                  source_sha256: sha,
                                })}
                              >
                                {name} <small>· {sha.slice(0, 8)}</small>
                              </Link>
                              <strong>{count}</strong>
                            </p>
                          ))}
                      </div>
                    </section>
                  </div>
                </>
              )}
              {overview && (
                <section className="insight-panel dashboard-recent">
                  <div className="panel-heading">
                    <div>
                      <h3>Actividad reciente</h3>
                      <p>Últimos eventos del período</p>
                    </div>
                    <Link href={historyHref(applied)} className="text-link">
                      Ver historial filtrado <ArrowRight size={14} />
                    </Link>
                  </div>
                  <motion.ol
                    className="activity-ledger"
                    initial={
                      reduceMotion || !frequencies?.animateRecent
                        ? false
                        : "hidden"
                    }
                    animate="visible"
                    variants={{
                      visible: { transition: { staggerChildren: 0.045 } },
                    }}
                  >
                    {summary.recent.map((e) => (
                      <motion.li
                        key={e.id}
                        variants={sectionEntrance}
                        transition={sectionTransition}
                      >
                        <span className="activity-dot" />
                        <div>
                          <Link
                            href={`/events/${encodeURIComponent(e.id)}`}
                            className="text-link"
                          >
                            {eventName(e.event_type)}
                          </Link>
                          <span>{e.zone_id}</span>
                        </div>
                        <time dateTime={e.occurred_at}>
                          {formatHistoryTime(e.occurred_at)}
                        </time>
                      </motion.li>
                    ))}
                  </motion.ol>
                </section>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}
