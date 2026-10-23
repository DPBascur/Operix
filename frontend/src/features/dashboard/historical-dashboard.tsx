"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  ArrowDownRight,
  ArrowUpRight,
  ArrowRight,
  RefreshCw,
  Play,
  Info,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { environment } from "@/config/environment";
import { historyDemo } from "@/services/demo/history-demo";
import {
  parseHistory,
  formatHistoryTime,
  historyError,
  summarizeHistory,
  type HistoryEvent,
} from "./history-model";

const eventName = (name: string) =>
  name === "zone_dwell" ? "Permanencia en zona" : name;
export function HistoricalDashboard() {
  const [source, setSource] = useState<"demo" | "api">("demo");
  const [month, setMonth] = useState("2026-10");
  const [periodAnchor, setPeriodAnchor] = useState("2026-10");
  const [records, setRecords] = useState<HistoryEvent[]>([]);
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
      try {
        if (!environment.apiBaseUrl)
          throw new Error(
            "Configure la dirección de la API para consultar el histórico real.",
          );
        const response = await fetch(
          `${environment.apiBaseUrl.replace(/\/$/, "")}/events/`,
          { cache: "no-store", signal: controller.signal },
        );
        if (!response.ok)
          throw new Error(
            "No fue posible consultar los registros. Revise la conexión y vuelva a intentar.",
          );
        const data = parseHistory(await response.json());
        if (active) setRecords(data);
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
  }, [source, revision]);
  const summary = useMemo(
    () => summarizeHistory(source === "demo" ? historyDemo : records, month),
    [source, records, month],
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
    <div className="insights-page">
      <header className="insights-heading">
        <div>
          <h2>Una mirada al histórico.</h2>
          <p>
            Reconozca recurrencias. Revise el contexto. Decida con evidencia.
          </p>
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
      <div className="provenance-note">
        <Info size={17} aria-hidden="true" />
        <p>
          {source === "demo"
            ? "Datos ilustrativos · Escenario sintético para explorar el dashboard. No son incidentes de una organización."
            : "Registros de la API · Incluyen pruebas y demostraciones. Un evento indica una regla satisfecha, no un incidente confirmado."}
        </p>
      </div>
      {source === "api" && loading ? (
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
          <section className="kpi-strip" aria-label="Resumen del período">
            <div>
              <span>Eventos del período</span>
              <strong>{summary.total}</strong>
              <small>{currentLabel}</small>
            </div>
            <div>
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
            </div>
            <div>
              <span>Zonas con registros</span>
              <strong>{summary.zones.length}</strong>
              <small>Ubicaciones en el período</small>
            </div>
            <div>
              <span>Mayor recurrencia</span>
              <strong className="kpi-word">
                {summary.zones[0]?.label ?? "Sin datos"}
              </strong>
              <small>
                {summary.zones[0]?.count ?? 0} registros · revisar contexto
              </small>
            </div>
          </section>
          {summary.total === 0 ? (
            <div className="feedback-panel">
              <h3>Sin registros para este período</h3>
              <p>
                Pruebe otro mes o revise la fuente seleccionada. No se
                reemplazan registros ausentes por ejemplos.
              </p>
            </div>
          ) : (
            <>
              <div className="analytics-grid">
                <section className="insight-panel trend-panel">
                  <div className="panel-heading">
                    <div>
                      <h3>Frecuencia diaria</h3>
                      <p>Eventos registrados · {currentLabel} · UTC</p>
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
                </section>
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
                  <h3>
                    La frecuencia orienta la revisión, no confirma el riesgo.
                  </h3>
                  <p>
                    Compare períodos con cobertura similar y contraste cada
                    evento con su evidencia visual. Los conteos no identifican
                    personas ni permiten atribuir responsabilidades.
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
