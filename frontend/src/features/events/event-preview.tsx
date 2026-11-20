"use client";

import Link from "next/link";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { useEffect, useState } from "react";
import { environment } from "@/config/environment";
import { apiFetch } from "@/services/browser-session";
import {
  isOperationalEvent,
  type OperationalEvent,
} from "@/services/event-contract";
import type { EventListItem } from "@/types/operix";
import { evidenceClip } from "./event-detail-model";

export function EventThumbnail({
  url,
  title,
  expanded = false,
}: {
  url?: string | null;
  title: string;
  expanded?: boolean;
}) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  return (
    <figure
      className={`event-thumbnail ${expanded ? "is-expanded" : ""}`}
      data-state={state}
      aria-busy={Boolean(url && state === "loading")}
    >
      {url && state !== "error" && (
        // The private PNG must reach the browser with its session credentials.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          loading="lazy"
          decoding="async"
          alt={`Fotograma: ${title}`}
          onLoad={() => setState("ready")}
          onError={() => setState("error")}
        />
      )}
      {!url || state === "error" ? (
        <span>{url ? "PNG no disponible" : "Sin PNG"}</span>
      ) : (
        state === "loading" && (
          <OperixScanLoader size="small" className="event-thumbnail-scan" />
        )
      )}
    </figure>
  );
}

export function EventPreview({
  row,
  detailUrl,
}: {
  row: EventListItem;
  detailUrl: string;
}) {
  const [detail, setDetail] = useState<OperationalEvent | null>(null);
  const [error, setError] = useState(false);
  const [clipError, setClipError] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    const url = `${environment.apiBaseUrl?.replace(/\/$/, "")}/events/${encodeURIComponent(row.id)}/`;
    async function load() {
      if (!environment.apiBaseUrl) throw new Error();
      const response = await apiFetch(url, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error();
      const data: unknown = await response.json();
      if (!isOperationalEvent(data) || data.id !== row.id) throw new Error();
      if (!controller.signal.aborted) setDetail(data);
    }
    void load().catch(() => {
      if (!controller.signal.aborted) setError(true);
    });
    return () => controller.abort();
  }, [row.id]);
  const clip = detail && evidenceClip(detail, environment.apiBaseUrl);
  return (
    <section
      className="event-preview surface-card"
      aria-label={`Evidencia de ${row.title}`}
    >
      <EventThumbnail url={row.evidenceUrl} title={row.title} expanded />
      <div className="event-preview-context">
        <h3>{row.title}</h3>
        <dl>
          <dt>Hora</dt>
          <dd>{row.time}</dd>
          <dt>Fuente</dt>
          <dd>
            {row.source || "No informada"} · {row.sourceKindLabel}
          </dd>
          <dt>Zona</dt>
          <dd>{row.zone}</dd>
          <dt>Objetos</dt>
          <dd>{row.objects}</dd>
          <dt>Regla</dt>
          <dd>{row.rule}</dd>
        </dl>
        <Link className="button button-outline" href={detailUrl}>
          Abrir expediente
        </Link>
      </div>
      <div className="event-preview-clip">
        <h3>Clip anotado</h3>
        {clip ? (
          <video
            controls
            playsInline
            preload="none"
            src={clip.url}
            aria-label="Clip anotado del evento"
            onError={() => setClipError(true)}
          />
        ) : error || detail ? (
          <p role="status">
            {error
              ? "No se pudo consultar el clip."
              : "Este evento no tiene clip."}
          </p>
        ) : (
          <OperixScanLoader variant="panel" message="Consultando evidencia…" />
        )}
        {clipError && <p role="status">No se pudo reproducir el clip.</p>}
      </div>
    </section>
  );
}
