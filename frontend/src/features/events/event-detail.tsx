"use client";
import { PageTitle } from "@/components/layout/page-title";

import { apiFetch } from "@/services/browser-session";
import { sourceKind, sourceNames } from "@/features/dashboard/history-model";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowUpRight,
  ChevronDown,
  Copy,
  ImageOff,
  RefreshCw,
} from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { LayoutGroup, motion, useReducedMotion } from "motion/react";
import { Button } from "@/components/ui/button";
import { environment } from "@/config/environment";
import {
  controlTransition,
  sectionTransition,
  sectionEntrance,
} from "@/lib/motion/presets";
import {
  eventTypeName,
  isOperationalEvent,
  type OperationalEvent,
} from "@/services/event-contract";
import {
  evidenceHref,
  evidenceClip,
  eventMeasurements,
  eventMotion,
  eventProximityGeometry,
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

function CopyIdentifier({ value, label }: { value: string; label: string }) {
  const code = useRef<HTMLElement>(null);
  const [feedback, setFeedback] = useState("");
  return (
    <>
      <span className={styles.identifierValue}>
        <code ref={code}>{value}</code>
        <button
          type="button"
          className={styles.copyButton}
          aria-label={`Copiar ${label}`}
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(value);
              setFeedback("Copiado.");
            } catch {
              const selection = window.getSelection();
              if (selection && code.current) {
                const range = document.createRange();
                range.selectNodeContents(code.current);
                selection.removeAllRanges();
                selection.addRange(range);
                setFeedback(
                  "Texto seleccionado. Puedes copiarlo con el teclado.",
                );
              }
            }
          }}
        >
          <Copy size={15} aria-hidden="true" />
        </button>
      </span>
      <span role="status" className={styles.copyFeedback}>
        {feedback}
      </span>
    </>
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
const evidenceViews = [
  { id: "frame", label: "Fotograma" },
  { id: "clip", label: "Clip" },
] as const;

function Evidence({
  url,
  event,
}: {
  url: string | null;
  event: OperationalEvent;
}) {
  const id = useId();
  const reducedMotion = useReducedMotion();
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const [view, setView] = useState(0);
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  const [attempt, setAttempt] = useState(0);
  const [clipError, setClipError] = useState(false);
  const [duration, setDuration] = useState<number | null>(null);
  const clip = evidenceClip(event, environment.apiBaseUrl);
  const transition = reducedMotion ? { duration: 0 } : controlTransition;
  const showClip = view === 1;

  function selectView(index: number) {
    setView(index);
    setClipError(false);
    setDuration(null);
  }

  return (
    <motion.figure
      className={styles.evidence}
      aria-label="Evidencia del evento"
      variants={sectionEntrance}
    >
      <div className={styles.sectionHeading}>
        <div
          className={styles.tabs}
          role="tablist"
          aria-label="Medio de evidencia"
        >
          <LayoutGroup id={id}>
            {evidenceViews.map((item, index) => (
              <button
                key={item.id}
                ref={(node) => {
                  tabs.current[index] = node;
                }}
                type="button"
                role="tab"
                id={`${id}-tab-${item.id}`}
                aria-controls={`${id}-panel-${item.id}`}
                aria-selected={view === index}
                tabIndex={view === index ? 0 : -1}
                onClick={() => {
                  if (view !== index) selectView(index);
                }}
                onKeyDown={(event) => {
                  const next =
                    event.key === "Home"
                      ? 0
                      : event.key === "End"
                        ? 1
                        : ["ArrowLeft", "ArrowRight"].includes(event.key)
                          ? 1 - index
                          : null;
                  if (next === null) return;
                  event.preventDefault();
                  tabs.current[next]?.focus();
                  if (next !== view) selectView(next);
                }}
              >
                {view === index && (
                  <motion.span
                    aria-hidden="true"
                    className={styles.tabIndicator}
                    layoutId={reducedMotion ? undefined : "media-selection"}
                    transition={transition}
                  />
                )}
                <span className={styles.tabLabel}>{item.label}</span>
              </button>
            ))}
          </LayoutGroup>
        </div>
        {!showClip && url && state === "ready" && (
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
        role="tabpanel"
        id={`${id}-panel-frame`}
        aria-labelledby={`${id}-tab-frame`}
        tabIndex={0}
        hidden={showClip}
      >
        <motion.div
          className={styles.imageStage}
          initial={false}
          animate={{ opacity: showClip && !reducedMotion ? 0.86 : 1 }}
          transition={transition}
          aria-busy={Boolean(url && state === "loading")}
        >
          {!url || state === "error" ? (
            <div className={styles.imageEmpty} role="status">
              <ImageOff size={28} aria-hidden="true" />
              <p>
                {url
                  ? "No se pudo cargar el fotograma."
                  : "Sin evidencia visual adjunta."}
              </p>
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
                  Cargando fotograma…
                </span>
              )}
              <a
                className={styles.imageLink}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                aria-label="Ampliar evidencia PNG original (nueva pestaña)"
              >
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  key={attempt}
                  src={url}
                  alt={`Fotograma anotado de ${eventTypeName(event.event_type).toLowerCase()} en ${event.zone_id}`}
                  onLoad={() => setState("ready")}
                  onError={() => setState("error")}
                />
              </a>
            </>
          )}
        </motion.div>
      </div>
      <div
        role="tabpanel"
        id={`${id}-panel-clip`}
        aria-labelledby={`${id}-tab-clip`}
        tabIndex={0}
        hidden={!showClip}
      >
        {showClip && (
          <motion.div
            initial={reducedMotion ? false : { opacity: 0.86 }}
            animate={{ opacity: 1 }}
            transition={transition}
          >
            {clip && !clipError ? (
              <>
                <div className={styles.imageStage}>
                  <video
                    aria-label="Clip anotado del evento"
                    controls
                    playsInline
                    preload="metadata"
                    src={clip.url}
                    onLoadedMetadata={({ currentTarget }) => {
                      if (
                        Number.isFinite(currentTarget.duration) &&
                        currentTarget.duration > 0
                      )
                        setDuration(currentTarget.duration);
                    }}
                    onError={() => setClipError(true)}
                  />
                </div>
                <div className={styles.clipTiming}>
                  <span>
                    Evento en el clip · {measurement(clip.offset, "s", 6)}
                  </span>
                  {duration !== null && (
                    <span>Duración · {measurement(duration, "s", 6)}</span>
                  )}
                  {duration !== null && clip.offset <= duration && (
                    <meter
                      min={0}
                      max={duration}
                      value={clip.offset}
                      aria-label="Posición del evento dentro del clip"
                    />
                  )}
                </div>
              </>
            ) : (
              <div className={styles.imageEmpty} role="status">
                <ImageOff size={28} aria-hidden="true" />
                <p>
                  {clipError
                    ? "No se pudo reproducir el clip."
                    : "Clip anotado no disponible para este evento."}
                </p>
                {clipError && (
                  <Button
                    className={styles.action}
                    variant="outline"
                    onClick={() => setClipError(false)}
                  >
                    <RefreshCw size={16} aria-hidden="true" /> Reintentar clip
                  </Button>
                )}
              </div>
            )}
          </motion.div>
        )}
      </div>
      <figcaption>
        {showClip
          ? "Clip anotado del resultado de Operix."
          : `Fotograma del evento${event.frame_index == null ? "" : ` · Frame ${event.frame_index}`}`}
      </figcaption>
    </motion.figure>
  );
}
function EventContent({ event }: { event: OperationalEvent }) {
  const time = eventTime(event),
    source = record(event.source);
  const geometry = eventProximityGeometry(event);
  const observations = ["zone_dwell", "zone_entry"].includes(event.event_type)
    ? {
        inside: event.observed_inside,
        dwell_time_s: event.observed_dwell_time_s,
      }
    : event.observations;
  const reducedMotion = useReducedMotion();
  const equipmentMotion = eventMotion(event);
  const isPair =
    event.interaction &&
    ["person_forklift_proximity", "zone_coexistence"].includes(
      event.event_type,
    );
  return (
    <motion.article
      className={styles.dossier}
      initial={reducedMotion ? false : "hidden"}
      animate="visible"
      variants={{
        visible: {
          transition: {
            ...sectionTransition,
            staggerChildren: reducedMotion ? 0 : 0.035,
          },
        },
      }}
    >
      <motion.header
        className={styles.header}
        variants={sectionEntrance}
        transition={sectionTransition}
      >
        <PageTitle>{eventTypeName(event.event_type)}</PageTitle>
        <p className={styles.location}>
          {event.zone_id} <span aria-hidden="true">·</span>{" "}
          {text(source.filename, "Fuente no informada")}
        </p>
        <p className={styles.semantic}>
          Condición configurada satisfecha; requiere revisión humana, no
          confirma un incidente.
        </p>
      </motion.header>
      <motion.section
        aria-labelledby="summary-title"
        variants={sectionEntrance}
        transition={sectionTransition}
      >
        <h2 id="summary-title" className="sr-only">
          Resumen operacional
        </h2>
        <dl className={styles.metrics}>
          {eventMeasurements(event).map((item) => (
            <Field key={item.label} label={item.label}>
              {item.observed}
              <span className={styles.criterion}>
                {item.criterion} · {item.configured}
              </span>
            </Field>
          ))}
          <Field label="Tiempo del video">
            {measurement(event.video_timestamp_s)}
          </Field>
          {!isPair && (
            <Field label="Objeto involucrado">
              {operationalSubjects(event)}
            </Field>
          )}
        </dl>
      </motion.section>
      <Evidence
        key={event.id}
        event={event}
        url={evidenceHref(event, environment.apiBaseUrl)}
      />
      <motion.section
        className={styles.summary}
        aria-labelledby="context-title"
        variants={sectionEntrance}
        transition={sectionTransition}
      >
        <h2 id="context-title">Contexto del evento</h2>
        <dl className={styles.context}>
          <Field label="Zona">{event.zone_id}</Field>
          <Field label="Regla y versión">
            {event.rule_id}{" "}
            <span className={styles.version}>v{event.rule_version}</span>
          </Field>
          <Field label="Procedencia">
            {sourceNames[sourceKind(source.kind)]}
          </Field>
          <Field label={time.label}>
            <time dateTime={time.iso}>{time.formatted}</time>
          </Field>
          {isPair && event.interaction && (
            <>
              <Field label="Persona">
                ID de seguimiento {event.interaction.person.track_id}
              </Field>
              <Field label="Montacargas">
                ID de seguimiento {event.interaction.forklift.track_id}
              </Field>
            </>
          )}
          {geometry && (
            <Field label="Método geométrico">{geometry.version}</Field>
          )}
          {equipmentMotion && (
            <>
              <Field label="Movimiento del montacargas">
                {equipmentMotion.state}
              </Field>
              <Field label="Velocidad estimada">{equipmentMotion.speed}</Field>
              <Field label="Ventana configurada">
                {equipmentMotion.window}
              </Field>
              <Field label="Condición de movimiento">
                {equipmentMotion.condition}
              </Field>
            </>
          )}
        </dl>
        <p className={styles.muted}>{time.explanation}</p>
        {geometry && (
          <p className={styles.muted}>
            {record(event.rule_parameters).distance_unit === "m"
              ? "Distancia aproximada en el plano calibrado, con contactos estimados desde cajas. Consulte los valores completos en trazabilidad."
              : "Distancia en espacio de imagen normalizado, sin unidad física."}
          </p>
        )}
      </motion.section>
      <details className={styles.trace} data-motion-disclosure>
        <summary>
          <span>
            <strong>Trazabilidad técnica</strong>
            <span>Identificadores, fuente, parámetros y valores completos</span>
          </span>
          <ChevronDown size={20} aria-hidden="true" />
        </summary>
        <div className={styles.traceBody}>
          <dl className={styles.identifiers}>
            <Field label="UUID del evento">
              <CopyIdentifier label="UUID del evento" value={event.id} />
            </Field>
            <Field label="Run del análisis">
              {typeof event.analysis_run_id === "string" &&
              event.analysis_run_id ? (
                <CopyIdentifier
                  label="ID del análisis"
                  value={event.analysis_run_id}
                />
              ) : (
                text(event.analysis_run_id)
              )}
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
            <Field label="Revisión espacial">
              {typeof source.spatial_revision === "number"
                ? String(source.spatial_revision)
                : "No registrada"}
            </Field>
            <Field label="Tipo canónico">{event.event_type}</Field>
            {geometry && (
              <>
                <Field label="Versión de geometría">{geometry.version}</Field>
                {record(event.rule_parameters).distance_unit === "m" && (
                  <>
                    <Field label="Versión de calibración">
                      {String(
                        record(
                          record(record(event.observations).ground).calibration,
                        ).version ?? "No registrada",
                      )}
                    </Field>
                    <Field label="SHA-256 de calibración">
                      {String(
                        record(
                          record(record(event.observations).ground).calibration,
                        ).sha256 ?? "No registrada",
                      )}
                    </Field>
                  </>
                )}
                {geometry.personAnchor && (
                  <Field label="Punto de persona (x, y)">
                    {geometry.personAnchor}
                  </Field>
                )}
                {geometry.equipmentTarget && (
                  <Field label="Punto de montacargas (x, y)">
                    {geometry.equipmentTarget}
                  </Field>
                )}
              </>
            )}
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
          <details className={styles.payload} data-motion-disclosure>
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
    </motion.article>
  );
}
export function EventDetail({
  id,
  returnUrl = "/events",
}: {
  id: string;
  returnUrl?: string;
}) {
  const [event, setEvent] = useState<OperationalEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    const load = async () => {
      if (!environment.apiBaseUrl)
        throw new Error("Configure la API para recuperar el evento.");
      const response = await apiFetch(
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
    <div className={styles.root}>
      <nav aria-label="Ubicación del expediente" className={styles.breadcrumb}>
        <Link className={styles.back} href={returnUrl}>
          <ArrowLeft size={16} aria-hidden="true" /> Eventos
        </Link>
        <span aria-hidden="true">/</span>
        <span aria-current="page">Expediente</span>
      </nav>
      {error ? (
        <section className={styles.loadState} role="alert">
          <PageTitle>No se pudo abrir el evento</PageTitle>
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
        <section className={styles.loadState} role="status" aria-live="polite">
          <PageTitle>Detalle del evento</PageTitle>
          <p>Consultando el registro…</p>
        </section>
      ) : (
        <EventContent event={event} />
      )}
    </div>
  );
}
