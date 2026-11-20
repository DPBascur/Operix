"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Activity,
  ArrowRight,
  BarChart3,
  Clapperboard,
  Film,
  RefreshCw,
} from "lucide-react";
import Link from "next/link";
import { PageTitle } from "@/components/layout/page-title";
import { Button } from "@/components/ui/button";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { environment } from "@/config/environment";
import { canOpen, useSession } from "@/features/auth/session-provider";
import {
  formatHistoryTime,
  historyError,
  historyHref,
  monthUtcBounds,
  parseFrequency,
  parseHistory,
  sourceKind,
  sourceNames,
  summarizeHistory,
} from "@/features/dashboard/history-model";
import { evidenceHref } from "@/features/events/event-detail-model";
import { EventThumbnail } from "@/features/events/event-preview";
import {
  analysisService,
  type AnalysisProfileDefinition,
} from "@/services/analysis.service";
import { apiFetch } from "@/services/browser-session";
import { eventTypeName, isOperationalEvent } from "@/services/event-contract";
import styles from "./operational-overview.module.css";

const monthFormat = new Intl.DateTimeFormat("es-CL", {
  month: "long",
  year: "numeric",
  timeZone: "UTC",
});
const countFormat = new Intl.NumberFormat("es-CL");
const changeFormat = new Intl.NumberFormat("es-CL", {
  style: "percent",
  maximumFractionDigits: 1,
  signDisplay: "exceptZero",
});
const eventTypes = [
  "zone_entry",
  "zone_coexistence",
  "zone_dwell",
  "person_forklift_proximity",
] as const;

type HistoryResult = {
  key: string;
  summary?: ReturnType<typeof summarizeHistory>;
  previousCount?: number;
  error?: string;
};

async function fetchHistory(
  path: string,
  params: URLSearchParams,
  signal: AbortSignal,
) {
  if (!environment.apiBaseUrl) {
    throw new Error(
      "Configura la dirección de la API para consultar el histórico.",
    );
  }
  const base = environment.apiBaseUrl.replace(/\/$/, "");
  const response = await apiFetch(`${base}/events/${path}?${params}`, {
    cache: "no-store",
    signal,
  });
  if (!response.ok) {
    throw new Error(
      "La API no pudo entregar los registros. Revisa la conexión y vuelve a intentar.",
    );
  }
  return response.json() as Promise<unknown>;
}

function SourceList({ revision }: { revision: number }) {
  const [catalog, setCatalog] = useState<{
    revision: number;
    demos?: AnalysisProfileDefinition[];
  }>();
  useEffect(() => {
    let active = true;
    analysisService
      .getProfiles()
      .then((profiles) => {
        if (!active) return;
        const demos = profiles.filter(
          (profile) => profile.default_demo_video?.id,
        );
        setCatalog({ revision, demos });
      })
      .catch(() => {
        if (active) setCatalog({ revision });
      });
    return () => {
      active = false;
    };
  }, [revision]);

  return (
    <section className={styles.panel} aria-labelledby="overview-sources">
      <header className={styles.panelHeading}>
        <h2 id="overview-sources">Fuentes disponibles</h2>
        <Link className={styles.textLink} href="/sources">
          Abrir Fuentes <ArrowRight size={15} aria-hidden="true" />
        </Link>
      </header>
      {catalog?.revision !== revision ? (
        <p className={styles.panelNote} role="status">
          Consultando catálogo…
        </p>
      ) : !catalog.demos ? (
        <p className={styles.panelNote} role="status">
          No se pudo consultar el catálogo de demos.
        </p>
      ) : catalog.demos.length === 0 ? (
        <p className={styles.panelNote}>
          El catálogo no tiene demos disponibles.
        </p>
      ) : (
        <ul className={styles.sources} aria-label="Videos de demostración">
          {catalog.demos.map((profile) => (
            <li key={profile.id}>
              <Link href={`/analysis?profile=${profile.id}`}>
                <Clapperboard size={17} aria-hidden="true" />
                <span>
                  <strong>
                    {profile.display_name || `Demo ${profile.id}`}
                  </strong>
                  <small>Video de demostración</small>
                </span>
                <ArrowRight size={15} aria-hidden="true" />
              </Link>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

export function OperationalOverview() {
  const { user } = useSession();
  const [currentMonth] = useState(() => new Date().toISOString().slice(0, 7));
  const [month, setMonth] = useState(currentMonth);
  const [type, setType] = useState("");
  const [source, setSource] = useState("");
  const [revision, setRevision] = useState(0);
  const [result, setResult] = useState<HistoryResult>();
  const periods = useMemo(() => {
    const anchor = new Date(`${currentMonth}-01T00:00:00Z`);
    return Array.from({ length: 12 }, (_, offset) =>
      new Date(
        Date.UTC(anchor.getUTCFullYear(), anchor.getUTCMonth() - offset, 1),
      )
        .toISOString()
        .slice(0, 7),
    );
  }, [currentMonth]);
  const filters = useMemo(() => {
    const bounds = monthUtcBounds(month);
    const query = new URLSearchParams({
      occurred_after: bounds.start,
      occurred_before: bounds.end,
    });
    if (type) query.set("event_type", type);
    if (source) query.set("source_kind", source);
    return query;
  }, [month, type, source]);
  const key = `${filters}:${revision}`;
  const current = result?.key === key ? result : undefined;
  const refresh = () => setRevision((value) => value + 1);

  useEffect(() => {
    const controller = new AbortController();
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(15000),
    ]);
    async function load() {
      try {
        const records = parseHistory(await fetchHistory("", filters, signal));
        const summary = summarizeHistory(records, month);
        if (controller.signal.aborted) return;
        setResult({ key, summary });

        // Compare complete UTC months with the same operational filters.
        if (month === currentMonth) return;
        const priorMonth = monthUtcBounds(month).previous.slice(0, 7);
        const prior = monthUtcBounds(priorMonth);
        const params = new URLSearchParams(filters);
        params.set("occurred_after", prior.start);
        params.set("occurred_before", prior.end);
        const frequency = parseFrequency(
          await fetchHistory("frequencies/", params, signal),
        );
        if (
          !controller.signal.aborted &&
          frequency.by_period.every(({ date }) => date.startsWith(priorMonth))
        ) {
          setResult({ key, summary, previousCount: frequency.total });
        }
      } catch (cause) {
        if (controller.signal.aborted) return;
        setResult((previous) =>
          previous?.key === key && previous.summary
            ? previous
            : {
                key,
                error: signal.aborted
                  ? "La consulta tardó demasiado. Vuelve a intentar."
                  : historyError(cause),
              },
        );
      }
    }
    void load();
    return () => controller.abort();
  }, [currentMonth, filters, key, month]);

  const summary = current?.summary;
  const comparison =
    summary && current.previousCount
      ? changeFormat.format(
          (summary.total - current.previousCount) / current.previousCount,
        )
      : null;
  const canVisit = (href: string) => Boolean(user && canOpen(href, user.role));
  const canSeeEvents = canVisit("/events");
  const indicatorHref = `/indicators?${new URLSearchParams({ month, type, source })}`;

  return (
    <div className={styles.overview}>
      <header className={styles.heading}>
        <PageTitle animate={false}>Centro operativo</PageTitle>
        <p>
          Revisa los eventos registrados, su origen y la evidencia disponible.
        </p>
      </header>

      <div
        className={styles.filters}
        role="group"
        aria-label="Filtros del resumen"
      >
        <label>
          Período UTC
          <select
            className="select-control"
            value={month}
            onChange={(event) => setMonth(event.target.value)}
          >
            {periods.map((value) => (
              <option key={value} value={value}>
                {monthFormat.format(new Date(`${value}-01T00:00:00Z`))}
              </option>
            ))}
          </select>
        </label>
        <label>
          Tipo de evento
          <select
            className="select-control"
            value={type}
            onChange={(event) => setType(event.target.value)}
          >
            <option value="">Todos los tipos</option>
            {eventTypes.map((value) => (
              <option key={value} value={value}>
                {eventTypeName(value)}
              </option>
            ))}
          </select>
        </label>
        <label>
          Procedencia
          <select
            className="select-control"
            value={source}
            onChange={(event) => setSource(event.target.value)}
          >
            <option value="">Todas las procedencias</option>
            {Object.entries(sourceNames).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </label>
        <Button variant="outline" onClick={refresh} disabled={!current}>
          <RefreshCw size={15} aria-hidden="true" /> Actualizar
        </Button>
      </div>

      <section
        className={styles.panel}
        aria-label="Estadísticas del período"
        aria-busy={!current}
      >
        <dl className={styles.metrics}>
          <div>
            <dt>Eventos del período</dt>
            <dd>{summary ? countFormat.format(summary.total) : "—"}</dd>
            {comparison && (
              <dd className={styles.comparison}>
                {comparison} frente al mes anterior
              </dd>
            )}
            {current?.previousCount === 0 && (
              <dd className={styles.comparison}>Mes anterior sin registros</dd>
            )}
          </div>
          <div>
            <dt>Zonas con registros</dt>
            <dd>{summary ? countFormat.format(summary.zones.length) : "—"}</dd>
          </div>
          <div>
            <dt>Análisis con eventos</dt>
            <dd>
              {summary ? countFormat.format(summary.runsWithEvents) : "—"}
            </dd>
          </div>
        </dl>
      </section>

      <div className={styles.grid}>
        <section
          className={styles.panel}
          aria-labelledby="overview-activity"
          aria-busy={!current}
        >
          <header className={styles.panelHeading}>
            <div>
              <h2 id="overview-activity">Actividad reciente</h2>
              <p>
                {summary?.recent.length
                  ? summary.total === 1
                    ? "1 registro en el período"
                    : `Últimos ${summary.recent.length} de ${countFormat.format(summary.total)} registros`
                  : "Eventos del período seleccionado"}
              </p>
            </div>
            {canSeeEvents && (
              <Link className={styles.textLink} href={historyHref(filters)}>
                Consultar Eventos <ArrowRight size={15} aria-hidden="true" />
              </Link>
            )}
          </header>
          {!current ? (
            <OperixScanLoader
              className={styles.activityLoading}
              size="small"
              message="Consultando el histórico…"
            />
          ) : current.error ? (
            <div className={styles.activityState}>
              <p role="alert">{current.error}</p>
              <Button variant="outline" onClick={refresh}>
                Reintentar consulta
              </Button>
            </div>
          ) : summary?.recent.length ? (
            <ol className={styles.activity}>
              {summary.recent.map((event) => {
                const title = eventTypeName(event.event_type);
                const filename =
                  typeof event.source?.filename === "string" &&
                  event.source.filename;
                const evidence =
                  canSeeEvents && isOperationalEvent(event)
                    ? evidenceHref(event, environment.apiBaseUrl)
                    : null;
                return (
                  <li key={event.id}>
                    {canSeeEvents && (
                      <EventThumbnail
                        key={evidence}
                        url={evidence}
                        title={title}
                      />
                    )}
                    <div className={styles.eventInfo}>
                      <strong>{title}</strong>
                      <span>{event.zone_id || "Zona sin identificar"}</span>
                      <span>
                        {sourceNames[sourceKind(event.source?.kind)]}
                        {filename ? ` · ${filename}` : ""}
                      </span>
                    </div>
                    <div className={styles.eventAction}>
                      <time dateTime={event.occurred_at}>
                        {formatHistoryTime(event.occurred_at)}
                      </time>
                      {canSeeEvents && (
                        <Link
                          className={styles.textLink}
                          href={`/events/${encodeURIComponent(event.id)}`}
                          aria-label={`Abrir expediente de ${title}, ${formatHistoryTime(event.occurred_at)}`}
                        >
                          Expediente <ArrowRight size={14} aria-hidden="true" />
                        </Link>
                      )}
                    </div>
                  </li>
                );
              })}
            </ol>
          ) : (
            <div className={styles.activityState}>
              <Film size={22} aria-hidden="true" />
              <strong>No hay eventos en este período</strong>
              <p>
                Elige otro mes o ajusta los filtros para consultar más
                registros.
              </p>
            </div>
          )}
          <footer className={styles.activityFooter}>
            Los eventos registran condiciones configuradas y requieren revisión.
            La hora se muestra en UTC.
          </footer>
        </section>

        <div className={styles.rail}>
          <section className={styles.panel} aria-labelledby="overview-continue">
            <header className={styles.panelHeading}>
              <h2 id="overview-continue">Continuar el trabajo</h2>
            </header>
            <div className={styles.quickLinks}>
              {canVisit("/analysis") && (
                <Link href="/analysis">
                  <Activity size={18} aria-hidden="true" />
                  <span>
                    <strong>Continuar Análisis</strong>
                    <small>Abre el espacio de revisión de video</small>
                  </span>
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
              )}
              {canVisit("/indicators") && (
                <Link href={indicatorHref}>
                  <BarChart3 size={18} aria-hidden="true" />
                  <span>
                    <strong>Abrir Indicadores</strong>
                    <small>Consulta frecuencias y recurrencias</small>
                  </span>
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
              )}
            </div>
          </section>
          {canVisit("/sources") && canVisit("/analysis") && (
            <SourceList revision={revision} />
          )}
        </div>
      </div>
    </div>
  );
}
