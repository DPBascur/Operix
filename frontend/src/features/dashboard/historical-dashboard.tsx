"use client";
import { useEffect, useMemo, useState } from "react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import {
  ArrowDownRight,
  ArrowUpRight,
  ArrowRight,
  RefreshCw,
  Play,
  Activity,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { environment } from "@/config/environment";
import { historyDemo } from "@/services/demo/history-demo";
import { eventTypeName } from "@/services/event-contract";
import { enterTransition, revealVariants } from "@/lib/motion/presets";
import {
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

const eventName = eventTypeName;
export function HistoricalDashboard() {
  const reduceMotion = useReducedMotion();
  const [source, setSource] = useState<"demo" | "api">("demo");
  const [month, setMonth] = useState("2026-10");
  const [periodAnchor, setPeriodAnchor] = useState("2026-10");
  const [records, setRecords] = useState<HistoryEvent[]>([]);
  const [frequencies, setFrequencies] = useState<{
    month: string;
    current: EventFrequency;
    previous: EventFrequency;
  } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (source !== "api") return;
    let active = true;
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    async function load() {
      setLoading(true);
      setError(null);
      setRecords([]);
      setFrequencies(null);
      try {
        if (!environment.apiBaseUrl)
          throw new Error(
            "Configure la dirección de la API para consultar el histórico real.",
          );
        const base = environment.apiBaseUrl.replace(/\/$/, "");
        const bounds = monthUtcBounds(month);
        const selected = new URLSearchParams({
          occurred_after: bounds.start,
          occurred_before: bounds.end,
        });
        const previous = new URLSearchParams({
          occurred_after: bounds.previous,
          occurred_before: monthUtcBounds(bounds.previous.slice(0, 7)).end,
        });
        const endpoints = [
          `${base}/events/?${selected}`,
          `${base}/events/frequencies/?${selected}`,
          `${base}/events/frequencies/?${previous}`,
        ];
        const responses = await Promise.all(
          endpoints.map((url) =>
            fetch(url, { cache: "no-store", signal: controller.signal }),
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
        summarizeApiHistory(data, month, current, previousFrequency);
        if (active) {
          setRecords(data);
          setFrequencies({ month, current, previous: previousFrequency });
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
  }, [source, month, revision]);
  const summary = useMemo(
    () =>
      source === "api" && frequencies?.month === month
        ? summarizeApiHistory(
            records,
            month,
            frequencies.current,
            frequencies.previous,
          )
        : summarizeHistory(source === "demo" ? historyDemo : [], month),
    [source, records, frequencies, month],
  );
  const max = Math.max(1, ...summary.days.map((d) => d.count));
  const points = summary.days
    .map(
      (d, i) =>
        `${20 + (i * 680) / (summary.days.length - 1)},${170 - (d.count / max) * 140}`,
    )
    .join(" ");
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
    <div className="insights-page market-dashboard">
      <header className="insights-heading">
        <div>
          <h2>Histórico de eventos</h2>
          <p>Actividad operacional · {currentLabel}</p>
        </div>
        <Link href="/sources" className="button button-primary">
          <Play size={16} aria-hidden="true" />
          Nuevo análisis
        </Link>
      </header>
      <div className="history-controls">
        <div className="segmented-control" aria-label="Fuente del histórico">
          <Button
            variant={source === "demo" ? "primary" : "ghost"}
            aria-pressed={source === "demo"}
            onClick={() => {
              setSource("demo");
              setMonth("2026-10");
              setPeriodAnchor("2026-10");
            }}
          >
            Ejemplo ilustrativo
          </Button>
          <Button
            variant={source === "api" ? "primary" : "ghost"}
            aria-pressed={source === "api"}
            onClick={() => {
              setSource("api");
              setMonth(new Date().toISOString().slice(0, 7));
              setPeriodAnchor(new Date().toISOString().slice(0, 7));
            }}
          >
            Registros API
          </Button>
        </div>
        <label className="month-control">
          Período UTC
          <select value={month} onChange={(e) => setMonth(e.target.value)}>
            {Array.from({ length: 12 }, (_, i) => {
              const anchor = new Date(`${periodAnchor}-01T00:00:00Z`);
              const d = new Date(
                Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() - i, 1),
              );
              const value = d.toISOString().slice(0, 7);
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
        {source === "api" && (
          <Button
            variant="outline"
            loading={loading}
            onClick={() => setRevision((r) => r + 1)}
          >
            <RefreshCw size={15} />
            Actualizar
          </Button>
        )}
      </div>
      <p className="history-source-caption">
        {source === "demo" ? "Datos de ejemplo" : "Registros de la API"} · UTC.
        Conteos de condiciones configuradas, no de incidentes confirmados.
      </p>
      {source === "api" &&
      (loading ||
        (!frequencies && !error) ||
        (frequencies?.month !== month && !error)) ? (
        <div className="dashboard-loading" role="status">
          <span className="spinner" />
          Consultando el histórico…
        </div>
      ) : source === "api" && error ? (
        <div className="feedback-panel" role="alert">
          <h3>No se pudo cargar el histórico</h3>
          <p>{error}</p>
          <Button onClick={() => setRevision((r) => r + 1)}>
            Reintentar consulta
          </Button>
        </div>
      ) : (
        <>
          {summary.total > 0 && (
            <motion.section
              className="kpi-strip"
              aria-label="Estadísticas del período"
              initial={reduceMotion ? false : "hidden"}
              animate="visible"
              transition={{ staggerChildren: reduceMotion ? 0 : 0.045 }}
            >
              <motion.div
                variants={revealVariants}
                transition={enterTransition}
              >
                <span>Eventos del período</span>
                <strong>{summary.total}</strong>
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
                <strong>{summary.zones.length}</strong>
                <small>Ubicaciones en el período</small>
              </motion.div>
              <motion.div
                variants={revealVariants}
                transition={enterTransition}
              >
                <span>Mayor recurrencia</span>
                <strong className="kpi-word">
                  {summary.zones[0]?.label ?? "Sin datos"}
                </strong>
                <small>
                  {summary.zones[0]?.count ?? 0} registros · revisar contexto
                </small>
              </motion.div>
            </motion.section>
          )}
          {summary.total === 0 ? (
            <div className="feedback-panel">
              <h3>No existen registros para este período</h3>
              <p>
                Pruebe otro mes o revise la fuente seleccionada. No se
                reemplazan registros ausentes por ejemplos.
              </p>
            </div>
          ) : (
            <>
              <div className="analytics-grid">
                <motion.section
                  className="insight-panel trend-panel"
                  initial={reduceMotion ? false : { opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={reduceMotion ? { duration: 0 } : enterTransition}
                >
                  <div className="panel-heading">
                    <div>
                      <h3>
                        <Activity size={20} aria-hidden="true" /> Eventos
                        registrados
                      </h3>
                      <div className="chart-headline">
                        <strong>{summary.total}</strong>
                        <span>{currentLabel}</span>
                      </div>
                      <p className="chart-comparison">
                        {summary.change === null
                          ? "Sin comparación anterior"
                          : `${summary.change > 0 ? "+" : ""}${summary.change.toFixed(1)} % frente al mes anterior`}
                      </p>
                    </div>
                    <span className="source-indicator">
                      {summary.total} eventos
                    </span>
                  </div>
                  <div className="trend-chart">
                    <div className="chart-scale">
                      <span>{max}</span>
                      <span>{Math.round(max / 2)}</span>
                      <span>0</span>
                    </div>
                    <svg
                      viewBox="0 0 720 190"
                      role="img"
                      aria-label={`Frecuencia diaria, ${summary.total} eventos. Tabla diaria disponible debajo.`}
                    >
                      <defs>
                        <linearGradient
                          id="history-area"
                          x1="0"
                          y1="0"
                          x2="0"
                          y2="1"
                        >
                          <stop
                            offset="0%"
                            stopColor="var(--primary)"
                            stopOpacity="0.23"
                          />
                          <stop
                            offset="100%"
                            stopColor="var(--primary)"
                            stopOpacity="0.015"
                          />
                        </linearGradient>
                        <pattern
                          id="history-dots"
                          width="36"
                          height="35"
                          patternUnits="userSpaceOnUse"
                        >
                          <circle
                            cx="2"
                            cy="2"
                            r="0.6"
                            fill="var(--border-strong)"
                          />
                        </pattern>
                      </defs>
                      <rect
                        x="20"
                        y="0"
                        width="680"
                        height="170"
                        fill="url(#history-dots)"
                        className="chart-dot-field"
                      />
                      <polygon
                        points={`20,170 ${points} 700,170`}
                        fill="url(#history-area)"
                      />
                      <line x1="20" y1="30" x2="700" y2="30" />
                      <line x1="20" y1="100" x2="700" y2="100" />
                      <line x1="20" y1="170" x2="700" y2="170" />
                      <polyline points={points} />
                      {summary.days.map((d, i) => (
                        <circle
                          key={d.day}
                          cx={20 + (i * 680) / (summary.days.length - 1)}
                          cy={170 - (d.count / max) * 140}
                          r="3"
                        >
                          <title>{`Día ${d.day}: ${d.count} eventos`}</title>
                        </circle>
                      ))}
                    </svg>
                  </div>
                  <div className="chart-days">
                    <span>01</span>
                    <span>08</span>
                    <span>15</span>
                    <span>22</span>
                    <span>{summary.days.length}</span>
                  </div>
                  <details className="chart-data">
                    <summary>Ver valores diarios</summary>
                    <div className="daily-data">
                      {summary.days.map((d) => (
                        <span key={d.day}>
                          Día {d.day}: <b>{d.count}</b>
                        </span>
                      ))}
                    </div>
                  </details>
                </motion.section>
                <section className="insight-panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Recurrencia por zona</h3>
                      <p>Dónde concentrar la revisión</p>
                    </div>
                  </div>
                  <ol className="zone-ranking">
                    {summary.zones.map((z, i) => (
                      <li key={z.label}>
                        <div>
                          <span>{String(i + 1).padStart(2, "0")}</span>
                          <strong>{z.label}</strong>
                          <b>{z.count}</b>
                        </div>
                        <meter
                          min={0}
                          max={summary.total}
                          value={z.count}
                          aria-label={`${z.label}: ${z.count} de ${summary.total}`}
                        />
                      </li>
                    ))}
                  </ol>
                </section>
              </div>
              <div className="analytics-grid lower-analytics">
                <section className="insight-panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Distribución horaria</h3>
                      <p>
                        Frecuencia por hora UTC; no representa nivel de riesgo.
                      </p>
                    </div>
                  </div>
                  <div className="hour-heatmap">
                    {summary.hours.map((h) => (
                      <div key={h.hour}>
                        <span>{String(h.hour).padStart(2, "0")}</span>
                        <span
                          className="heat-cell"
                          style={{
                            backgroundColor: `color-mix(in srgb, var(--primary) ${h.count ? 25 + (65 * h.count) / Math.max(1, busiest.count) : 0}%, var(--surface-muted))`,
                          }}
                          title={`${h.hour}:00 UTC: ${h.count} eventos`}
                          aria-label={`${h.hour}:00 UTC, ${h.count} eventos`}
                        />
                      </div>
                    ))}
                  </div>
                  <details className="chart-data">
                    <summary>Ver valores horarios</summary>
                    <div className="daily-data">
                      {summary.hours.map((h) => (
                        <span key={h.hour}>
                          {String(h.hour).padStart(2, "0")}:00 UTC:{" "}
                          <b>{h.count}</b>
                        </span>
                      ))}
                    </div>
                  </details>
                  <p className="insight-caption">
                    {busiest.count
                      ? `Mayor frecuencia observada a las ${String(busiest.hour).padStart(2, "0")}:00 UTC (${busiest.count} registros).`
                      : "No hay actividad en este período."}
                  </p>
                  <div className="type-breakdown">
                    <h4>Por tipo de evento</h4>
                    {summary.types.map((t) => (
                      <p key={t.label}>
                        <span>{eventName(t.label)}</span>
                        <strong>
                          {t.count}{" "}
                          <small>
                            ({((t.count / summary.total) * 100).toFixed(0)} %)
                          </small>
                        </strong>
                      </p>
                    ))}
                  </div>
                </section>
                <section className="insight-panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Actividad del período</h3>
                      <p>Los registros más recientes</p>
                    </div>
                    {source === "api" && (
                      <Link href="/events" className="text-link">
                        Ver eventos <ArrowRight size={14} />
                      </Link>
                    )}
                  </div>
                  <ol className="activity-ledger">
                    {summary.recent.map((e) => (
                      <li key={e.id}>
                        <span className="activity-dot" />
                        <div>
                          <strong>{eventName(e.event_type)}</strong>
                          <span>{e.zone_id}</span>
                        </div>
                        <time dateTime={e.occurred_at}>
                          {formatHistoryTime(e.occurred_at)}
                        </time>
                      </li>
                    ))}
                  </ol>
                </section>
              </div>
              <section className="decision-note">
                <div>
                  <h3>Del registro a la evidencia.</h3>
                  <p>
                    Revise el contexto de cada evento en su video de origen.
                  </p>
                </div>
                <Link href="/events" className="button button-outline">
                  Revisar eventos <ArrowRight size={16} />
                </Link>
              </section>
            </>
          )}
        </>
      )}
    </div>
  );
}
