"use client";

import Link from "next/link";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { useIsPresent } from "motion/react";
import { useState } from "react";
import type { EventListItem } from "@/types/operix";
import { mergeEvidence, type EventEvidence } from "./event-detail-model";
import { EvidenceFeedback } from "./evidence-feedback";
import { useEventEvidence } from "./use-event-evidence";

export function EventThumbnail({
  url,
  title,
  expanded = false,
  pending = false,
}: {
  url?: string | null;
  title: string;
  expanded?: boolean;
  pending?: boolean;
}) {
  const [state, setState] = useState<"loading" | "ready" | "error">("loading");
  return (
    <div
      className={`event-thumbnail ${expanded ? "is-expanded" : ""}`}
      data-state={state}
      aria-busy={Boolean(url && state === "loading")}
    >
      {url && state !== "error" && (
        // The private PNG must reach the browser with its session credentials.
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={url}
          loading={expanded ? "eager" : "lazy"}
          decoding="async"
          alt={`Fotograma: ${title}`}
          onLoad={() => setState("ready")}
          onError={() => setState("error")}
        />
      )}
      {!url || state === "error" ? (
        <span>
          {url
            ? "PNG no disponible"
            : pending
              ? "Fotograma pendiente"
              : "Sin PNG"}
        </span>
      ) : (
        state === "loading" && (
          <OperixScanLoader size="small" className="event-thumbnail-scan" />
        )
      )}
    </div>
  );
}

export function EventPreview({
  row,
  detailUrl,
  panelId,
  onEvidence,
}: {
  row: EventListItem;
  detailUrl: string;
  panelId: string;
  onEvidence: (id: string, evidence: EventEvidence) => void;
}) {
  const present = useIsPresent();
  const result = useEventEvidence(row.id, { active: present, onEvidence });
  const evidence = result?.evidence
    ? mergeEvidence(result.evidence, row.evidence)
    : row.evidence;
  const clip = evidence?.clip;
  const [clipError, setClipError] = useState<string | null>(null);
  return (
    <section
      className="event-preview surface-card"
      aria-label={`Evidencia de ${row.title}`}
      id={panelId}
      inert={!present}
    >
      <EventThumbnail
        key={evidence?.png}
        url={evidence?.png}
        title={row.title}
        expanded
        pending={evidence?.status === "pending"}
      />
      <div className="event-preview-context">
        <h3>{row.title}</h3>
        {evidence &&
          (result?.evidence ||
            evidence.status ||
            evidence.png ||
            evidence.clip) && (
            <EvidenceFeedback
              evidence={evidence}
              checking={result?.checking}
              refreshFailed={result?.refreshFailed}
            />
          )}
        {result?.error && (
          <p role="status">No se pudo consultar la evidencia del evento.</p>
        )}
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
            onError={() => setClipError(clip.url)}
          />
        ) : result?.error ? null : result ? (
          <p>
            {evidence?.status === "pending"
              ? "Clip pendiente."
              : "Clip no disponible."}
          </p>
        ) : (
          <OperixScanLoader variant="panel" message="Consultando evidencia…" />
        )}
        {clip && clipError === clip.url && (
          <p role="status">No se pudo reproducir el clip.</p>
        )}
      </div>
    </section>
  );
}
