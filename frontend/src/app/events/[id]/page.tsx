"use client";

import { useParams } from "next/navigation";
import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/layout/app-shell";
import { environment } from "@/config/environment";
import {
  isOperationalEvent,
  eventSubjects,
  eventTypeName,
  type OperationalEvent,
} from "@/services/event-contract";

function EventRecord({ id }: { id: string }) {
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
          cause instanceof Error
            ? cause.message
            : "No se pudo consultar el evento.",
        );
    });
    return () => controller.abort();
  }, [id, attempt]);
  return (
    <AppShell activePath="/events">
      <div className="page-wrap operational-page">
        <Link className="underline underline-offset-2" href="/events">
          Volver al histórico
        </Link>
        <h2 className="compact-page-title">Detalle del evento</h2>
        <p>
          Condición configurada satisfecha; requiere revisión humana, no
          confirma un incidente.
        </p>
        {error ? (
          <div role="alert">
            <p>{error}</p>
            <button
              type="button"
              onClick={() => {
                setError(null);
                setEvent(null);
                setAttempt(attempt + 1);
              }}
            >
              Volver a consultar
            </button>
          </div>
        ) : !event ? (
          <p role="status">Consultando el registro…</p>
        ) : (
          <>
            <h3>{eventTypeName(event.event_type)}</h3>
            <dl className="grid gap-4 sm:grid-cols-2">
              {Object.entries({
                ID: event.id,
                "Fecha UTC": new Date(event.occurred_at).toISOString(),
                Zona: event.zone_id,
                Objetos: eventSubjects(event),
                Regla: `${event.rule_id} · v${event.rule_version}`,
                Run: event.analysis_run_id,
                Frame: event.frame_index,
                "Tiempo de video (s)": event.video_timestamp_s,
                Fuente: event.source?.filename ?? "No informada",
                "Base temporal":
                  event.source?.timestamp_basis ??
                  "Ancla explícita de la ejecución original",
              }).map(([name, value]) => (
                <div key={name} className="min-w-0">
                  <dt>{name}</dt>
                  <dd className="break-all">{String(value)}</dd>
                </div>
              ))}
            </dl>
            {[
              ["Parámetros efectivos", event.rule_parameters],
              [
                "Observaciones",
                event.event_type === "zone_dwell"
                  ? {
                      inside: event.observed_inside,
                      dwell_time_s: event.observed_dwell_time_s,
                    }
                  : event.observations,
              ],
              ["Episodio", event.episode],
              ["Fuente y hashes", event.source],
            ].map(([name, data]) => (
              <section key={String(name)}>
                <h3>{String(name)}</h3>
                <pre className="whitespace-pre-wrap break-all text-sm">
                  {JSON.stringify(data, null, 2)}
                </pre>
              </section>
            ))}
            {event.evidence_url?.startsWith("/api/v1/events/") ? (
              <a
                className="underline underline-offset-2"
                target="_blank"
                rel="noopener noreferrer"
                href={new URL(
                  event.evidence_url,
                  environment.apiBaseUrl,
                ).toString()}
              >
                Abrir evidencia PNG del evento
              </a>
            ) : (
              <p>Sin evidencia disponible.</p>
            )}
          </>
        )}
      </div>
    </AppShell>
  );
}

export default function EventDetailPage() {
  const { id } = useParams<{ id: string }>();
  return <EventRecord key={id} id={id} />;
}
