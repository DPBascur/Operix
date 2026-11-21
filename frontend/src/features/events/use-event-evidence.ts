import { useEffect, useState } from "react";
import { environment } from "@/config/environment";
import { apiFetch } from "@/services/browser-session";
import { isOperationalEvent } from "@/services/event-contract";
import {
  eventEvidence,
  mergeEvidence,
  type EventEvidence,
} from "./event-detail-model";

async function fetchEvent(id: string, signal: AbortSignal) {
  if (!environment.apiBaseUrl)
    throw new Error("Configure la API para recuperar el evento.");
  const response = await apiFetch(
    `${environment.apiBaseUrl.replace(/\/$/, "")}/events/${encodeURIComponent(id)}/`,
    {
      cache: "no-store",
      signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
    },
  );
  if (!response.ok)
    throw new Error(
      response.status === 404
        ? "El evento no existe."
        : "No se pudo consultar el evento.",
    );
  const event: unknown = await response.json();
  if (!isOperationalEvent(event) || event.id !== id)
    throw new Error("La API devolvió un evento inválido.");
  return event;
}

export function useEventEvidence(
  id: string,
  {
    attempt = 0,
    active = true,
    onEvidence,
  }: {
    attempt?: number;
    active?: boolean;
    onEvidence?: (id: string, evidence: EventEvidence) => void;
  } = {},
) {
  type Result =
    | {
        event: Awaited<ReturnType<typeof fetchEvent>>;
        evidence: EventEvidence;
        checking: boolean;
        refreshFailed?: boolean;
        error?: never;
      }
    | {
        error: string;
        event?: never;
        evidence?: never;
        checking?: never;
        refreshFailed?: never;
      };
  const [result, setResult] = useState<{ attempt: number; value: Result }>();

  useEffect(() => {
    if (!active) return;
    const controller = new AbortController();
    const { signal } = controller;
    let timer: ReturnType<typeof setTimeout> | undefined;
    function publish(value: Result) {
      if (signal.aborted) return;
      setResult({ attempt, value });
      if (value.evidence) onEvidence?.(id, value.evidence);
    }
    // Wait for the effect to settle before issuing the initial request.
    queueMicrotask(() => {
      if (signal.aborted) return;
      void fetchEvent(id, signal).then(
        (event) => {
          if (signal.aborted) return;
          const evidence = eventEvidence(event, environment.apiBaseUrl);
          const checking = evidence.status === "pending";
          publish({ event, evidence, checking });
          if (checking) {
            // Only an explicit pending response gets one automatic follow-up.
            timer = setTimeout(() => {
              void fetchEvent(id, signal).then(
                (updated) => {
                  const latest = eventEvidence(updated, environment.apiBaseUrl);
                  publish({
                    event,
                    evidence: mergeEvidence(latest, evidence),
                    checking: false,
                  });
                },
                () =>
                  publish({
                    event,
                    evidence,
                    checking: false,
                    refreshFailed: true,
                  }),
              );
            }, 2000);
          }
        },
        (error: unknown) =>
          publish({
            error:
              error instanceof Error && error.name === "Error"
                ? error.message
                : "No se pudo conectar con la API. Vuelva a intentar.",
          }),
      );
    });
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [id, attempt, active, onEvidence]);

  return result?.attempt === attempt ? result.value : undefined;
}
