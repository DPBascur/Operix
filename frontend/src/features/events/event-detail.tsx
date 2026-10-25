"use client";

import Link from "next/link";
import {
  ArrowLeft,
  ArrowUpRight,
  ChevronDown,
  ImageOff,
  RefreshCw,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { Button } from "@/components/ui/button";
import { environment } from "@/config/environment";
import {
  eventTypeName,
  isOperationalEvent,
  type OperationalEvent,
} from "@/services/event-contract";
import {
  evidenceHref,
  eventMeasurements,
  eventTime,
  measurement,
  operationalSubjects,
  record,
  text,
} from "./event-detail-model";
import styles from "./event-detail.module.css";

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className={styles.field}>
      <dt>{label}</dt>
      <dd>{children}</dd>
    </div>
  );
}
function Snapshot({ title, value }: { title: string; value: unknown }) {
  const empty =
    value == null ||
    (typeof value === "object" && Object.keys(value).length === 0);
  return (
    <section className={styles.snapshot} aria-label={title}>
      <h4>{title}</h4>
      {empty ? (
        <p className={styles.muted}>No registrado en este evento.</p>
      ) : (
        <pre tabIndex={0} aria-label={`${title}, JSON completo`}>
          {JSON.stringify(value, null, 2)}
        </pre>
      )}
    </section>
  );
}
function Evidence({
  url,
  event,
}: {
  url: string | null;
  event: OperationalEvent;
}) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  return (
    <figure className={styles.evidence} aria-labelledby="evidence-title">
      <div className={styles.sectionHeading}>
        <h3 id="evidence-title">Evidencia del evento</h3>
        {url && (
          <a
            className={styles.action}
            href={url}
            target="_blank"
            rel="noopener noreferrer"
          >
            Ampliar PNG <ArrowUpRight size={16} aria-hidden="true" />
            <span className="sr-only"> (nueva pestaña)</span>
          </a>
        )}
      </div>
      <div
        className={styles.imageStage}
        aria-busy={Boolean(url && state === "loading")}
      >
        {!url || state === "error" ? (
          <div className={styles.imageEmpty} role="status">
            <ImageOff size={28} aria-hidden="true" />
            <p>
              {url
                ? "No se pudo cargar la evidencia."
                : "Sin evidencia visual adjunta."}
            </p>
            <span>
              {url
                ? "El registro sigue disponible. Puede volver a cargar el PNG."
                : "Este evento no incluye una referencia PNG disponible."}
            </span>
            {url && (
              <Button
                className={styles.action}
                variant="outline"
                onClick={() => {
                  setState("loading");
                  setAttempt(attempt + 1);
                }}
              >
                <RefreshCw size={16} aria-hidden="true" /> Reintentar imagen
              </Button>
            )}
          </div>
        ) : (
          <>
            {state === "loading" && (
              <span className={styles.imageLoading} role="status">
                Cargando evidencia…
              </span>
            )}
            <a
              className={styles.imageLink}
              href={url}
              target="_blank"
              rel="noopener noreferrer"
              aria-label="Ampliar evidencia PNG original (nueva pestaña)"
            >
              {/* Se conserva el PNG original de la API, sin optimización ni recorte. */}
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                key={attempt}
                src={url}
                alt={`Frame de evidencia de ${eventTypeName(event.event_type).toLowerCase()} en ${event.zone_id}`}
                width={960}
                height={540}
                onLoad={() => setState("ready")}
                onError={() => setState("error")}
              />
            </a>
          </>
        )}
      </div>
      <figcaption>
        Frame {text(String(event.frame_index ?? ""), "no registrado")} ·{" "}
        {measurement(event.video_timestamp_s)} de video.
        {url && " La ampliación abre el PNG original."}
      </figcaption>
    </figure>
  );
}
function EventContent({ event }: { event: OperationalEvent }) {
  const time = eventTime(event),
    source = record(event.source);
  const observations =
    event.event_type === "zone_dwell"
      ? {
          inside: event.observed_inside,
          dwell_time_s: event.observed_dwell_time_s,
        }
      : event.observations;
  return (
    <>
      <header className={styles.header}>
        <h2>{eventTypeName(event.event_type)}</h2>
        <p className={styles.location}>
          {event.zone_id} <span aria-hidden="true">·</span>{" "}
          {text(source.filename, "Fuente no informada")}
        </p>
        <p className={styles.semantic}>
          Condición configurada satisfecha; requiere revisión humana, no
          confirma un incidente.
        </p>
      </header>
      <div className={styles.inspection}>
        <Evidence
          key={event.id}
          event={event}
          url={evidenceHref(event, environment.apiBaseUrl)}
        />
        <section className={styles.summary} aria-labelledby="summary-title">
          <h3 id="summary-title">Resumen operacional</h3>
          <div className={styles.measurements}>
            {eventMeasurements(event).map((item) => (
              <section
                key={item.label}
                className={styles.measurement}
                aria-label={item.label}
              >
                <h4>{item.label}</h4>
                <dl>
                  <Field label="Observada">{item.observed}</Field>
                  <Field label={item.criterion}>{item.configured}</Field>
                </dl>
              </section>
            ))}
            {event.event_type === "person_forklift_proximity" && (
              <p className={styles.measureNote}>
                Distancia en coordenadas normalizadas, sin unidad física; no
                representa metros.
              </p>
            )}
          </div>
          <dl className={styles.context}>
            <Field label="Objetos involucrados">
              {operationalSubjects(event)}
            </Field>
            <Field label="Zona">{event.zone_id}</Field>
            <Field label="Regla y versión">
              {event.rule_id}{" "}
              <span className={styles.version}>v{event.rule_version}</span>
            </Field>
          </dl>
          <div className={styles.time}>
            <dl>
              <Field label="Tiempo del video">
                <span className={styles.videoTime}>
                  {measurement(event.video_timestamp_s)}
                </span>
              </Field>
              <Field label={time.label}>
                <time dateTime={time.iso}>{time.formatted}</time>
              </Field>
            </dl>
            <p>{time.explanation}</p>
          </div>
        </section>
      </div>
      <details className={styles.trace}>
        <summary>
          <span>
            <strong>Trazabilidad técnica</strong>
            <span>Identificadores, fuente, parámetros y valores completos</span>
          </span>
          <ChevronDown size={20} aria-hidden="true" />
        </summary>
        <div className={styles.traceBody}>
          <dl className={styles.identifiers}>
            <Field label="UUID del evento">{event.id}</Field>
            <Field label="Run del análisis">
              {text(event.analysis_run_id)}
            </Field>
            <Field label="Sesión">{text(source.session_id)}</Field>
            <Field label="Ejecución de la sesión">
              {source.session_run == null
                ? "No registrada"
                : String(source.session_run)}
            </Field>
            <Field label="Frame">
              {event.frame_index == null
                ? "No registrado"
                : String(event.frame_index)}
            </Field>
            <Field label="Tipo canónico">{event.event_type}</Field>
            <Field label="Timestamp original recibido">
              <time dateTime={time.iso}>{time.iso}</time>
            </Field>
            <Field label="Timestamp basis">
              {text(source.timestamp_basis)}
            </Field>
          </dl>
          <div className={styles.snapshots}>
            <Snapshot
              title="Parámetros efectivos"
              value={event.rule_parameters}
            />
            <Snapshot title="Observaciones" value={observations} />
            <Snapshot title="Episodio" value={event.episode} />
            <Snapshot title="Fuente y hashes" value={event.source} />
          </div>
          <details className={styles.payload}>
            <summary>
              Payload completo recibido de la API{" "}
              <ChevronDown size={16} aria-hidden="true" />
            </summary>
            <pre tabIndex={0} aria-label="Payload completo del evento">
              {JSON.stringify(event, null, 2)}
            </pre>
          </details>
        </div>
      </details>
    </>
  );
}
export function EventDetail({ id }: { id: string }) {
  const [event, setEvent] = useState<OperationalEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      if (!environment.apiBaseUrl)
        throw new Error("Configure la API para recuperar el evento.");
      const response = await fetch(
        `${environment.apiBaseUrl.replace(/\/$/, "")}/events/${encodeURIComponent(id)}/`,
        { signal: controller.signal, cache: "no-store" },
      );
      if (!response.ok)
        throw new Error(
          response.status === 404
            ? "El evento no existe."
            : "No se pudo consultar el evento. Vuelva a intentar.",
        );
      const data: unknown = await response.json();
      if (!isOperationalEvent(data))
        throw new Error("La API devolvió un evento inválido.");
      if (!controller.signal.aborted) setEvent(data);
    };
    void load().catch((cause: unknown) => {
      if (!controller.signal.aborted)
        setError(
          cause instanceof TypeError
            ? "No se pudo conectar con la API. Compruebe la conexión y vuelva a intentar."
            : cause instanceof Error
              ? cause.message
              : "No se pudo consultar el evento.",
        );
    });
    return () => controller.abort();
  }, [id, attempt]);
  return (
    <AppShell activePath="/events">
      <div className={`page-wrap ${styles.root}`}>
        <Link className={styles.back} href="/events">
          <ArrowLeft size={16} aria-hidden="true" /> Volver al histórico
        </Link>
        {error ? (
          <section className={styles.loadState} role="alert">
            <h2>No se pudo abrir el evento</h2>
            <p>{error}</p>
            <Button
              className={styles.action}
              onClick={() => {
                setError(null);
                setEvent(null);
                setAttempt(attempt + 1);
              }}
            >
              Volver a consultar
            </Button>
          </section>
        ) : !event ? (
          <section
            className={styles.loadState}
            role="status"
            aria-live="polite"
          >
            <h2>Detalle del evento</h2>
            <p>Consultando el registro…</p>
          </section>
        ) : (
          <EventContent event={event} />
        )}
      </div>
    </AppShell>
  );
}
