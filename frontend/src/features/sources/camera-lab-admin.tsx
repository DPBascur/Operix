"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageTitle } from "@/components/layout/page-title";
import { Button } from "@/components/ui/button";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { operationalError } from "@/features/operations/operation-request";
import {
  cameraLabService,
  CameraRequestError,
  type CameraControlUpdate,
  type CameraLabControl,
} from "@/services/camera-lab.service";
import { CameraCard, LoadError, useCameraData } from "./camera-overview";
import { CameraPlaylistEditor } from "./camera-playlist-editor";
import { cameraMediaForRate, emptyPlaylist } from "./camera-playlist";

const labStatuses: Record<CameraLabControl["status"], string> = {
  disabled: "Deshabilitado",
  starting: "Iniciando",
  partial: "Operación parcial",
  active: "Activo",
  stopping: "Deteniendo",
  finished: "Reproducción finalizada",
};

const publisherStatuses: Record<CameraLabControl["publisher"][string], string> =
  {
    idle: "En espera",
    starting: "Iniciando",
    publishing: "Publicando",
    error: "Error",
  };

export function CameraLabAdmin() {
  const [pending, setPending] = useState(false);
  const [refreshAfter, setRefreshAfter] = useState(0);
  const [feedback, setFeedback] = useState<{
    text: string;
    error?: boolean;
    cameraId?: string;
  }>();
  const patchInFlight = useRef(false);
  const { data, error, receivedAt, retry } = useCameraData(
    cameraLabService.control,
    3000,
    pending,
  );
  const awaitingSnapshot =
    pending || (refreshAfter > 0 && receivedAt <= refreshAfter);
  const locked = awaitingSnapshot || Boolean(error) || !data?.available;

  async function update(change: CameraControlUpdate, cameraId?: string) {
    if (locked || patchInFlight.current) return false;
    patchInFlight.current = true;
    setPending(true);
    setFeedback({ text: "Guardando cambios…", cameraId });
    try {
      await cameraLabService.updateControl(change);
      setFeedback({ text: "Cambios guardados.", cameraId });
      return true;
    } catch (cause) {
      const text =
        change.playlists &&
        cause instanceof CameraRequestError &&
        cause.status === 400
          ? "El servidor rechazó la lista. Comprueba que los videos sigan permitidos para esta cámara."
          : operationalError(cause);
      setFeedback({ text, error: true, cameraId });
      return false;
    } finally {
      setRefreshAfter(Date.now());
      patchInFlight.current = false;
      setPending(false);
    }
  }

  return (
    <div className="sources-page page-v1 grid gap-5">
      <header className="app-page-heading">
        <div className="grid gap-2">
          <PageTitle>Control del laboratorio</PageTitle>
          <p>Gestiona la publicación y el monitoreo de cámaras virtuales.</p>
          <Link
            className="w-fit text-primary underline"
            href="/sources#laboratorio-camaras"
          >
            Ver cámaras en Fuentes
          </Link>
        </div>
      </header>
      {error && <LoadError error={error} retry={retry} />}
      {!data && !error && (
        <OperixScanLoader
          variant="panel"
          message="Consultando el laboratorio…"
        />
      )}
      {data && (
        <>
          <section
            className="surface-card grid gap-4 p-4"
            aria-labelledby="lab-control-status"
          >
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div>
                <h2 id="lab-control-status" className="font-semibold">
                  Monitoreo automático
                </h2>
                <p className="text-sm text-text-secondary" role="status">
                  {error
                    ? "Estado sin actualizar"
                    : data.available
                      ? labStatuses[data.status]
                      : "Control no disponible"}
                </p>
              </div>
              <Button
                disabled={locked}
                variant={data.enabled ? "outline" : "primary"}
                onClick={() => void update({ enabled: !data.enabled })}
              >
                {data.enabled
                  ? "Deshabilitar laboratorio"
                  : "Habilitar laboratorio"}
              </Button>
            </div>
            <dl className="flex flex-wrap gap-x-8 gap-y-3 border-t border-border pt-3 text-sm">
              <div>
                <dt className="text-text-secondary">Capacidad simultánea</dt>
                <dd className="font-medium tabular-nums">{data.capacity}</dd>
              </div>
              <div>
                <dt className="text-text-secondary">Cámaras habilitadas</dt>
                <dd className="font-medium tabular-nums">
                  {data.cameras.filter((camera) => camera.enabled).length}
                </dd>
              </div>
              <div>
                <dt className="text-text-secondary">Cámaras analizando</dt>
                <dd className="font-medium tabular-nums">
                  {
                    data.cameras.filter(
                      (camera) =>
                        camera.status === "analyzing" && camera.preview_url,
                    ).length
                  }
                </dd>
              </div>
              <div>
                <dt className="text-text-secondary">MediaMTX</dt>
                <dd className="font-medium">
                  {data.mediamtx === "ready" ? "Disponible" : "No disponible"}
                </dd>
              </div>
              <div className="min-w-0 break-words">
                <dt className="text-text-secondary">Último cambio por</dt>
                <dd className="font-medium">
                  {data.updated_by ?? "Sin registro"}
                </dd>
              </div>
            </dl>
          </section>
          {feedback && !feedback.cameraId && (
            <p
              className={
                feedback?.error
                  ? "inline-message is-error"
                  : "text-sm text-text-secondary"
              }
              role={feedback?.error ? "alert" : "status"}
            >
              {feedback.text}
            </p>
          )}
          <section className="grid gap-3" aria-labelledby="lab-control-cameras">
            <h2 id="lab-control-cameras" className="font-semibold">
              Cámaras virtuales
            </h2>
            {data.cameras.length ? (
              <ul className="grid gap-4 md:grid-cols-2">
                {data.cameras.map((camera) => {
                  const publisher = data.publisher[camera.id];
                  const action = camera.enabled ? "Deshabilitar" : "Habilitar";
                  const transition = camera.last_transition;
                  const transitionText =
                    transition?.outcome === "expected" &&
                    transition.reason === "media_eof"
                      ? "Fin de video programado"
                      : transition?.outcome === "interrupted" &&
                          transition.reason === "publisher_interrupted"
                        ? "Interrupción del emisor"
                        : undefined;
                  return (
                    <li
                      key={camera.id}
                      className="surface-card grid min-w-0 content-start gap-3 p-4"
                    >
                      <CameraCard
                        camera={camera}
                        live={false}
                        receivedAt={receivedAt}
                        stale={Boolean(error) || awaitingSnapshot}
                      />
                      <p className="text-sm text-text-secondary">
                        {camera.enabled ? "Habilitada" : "Deshabilitada"} ·
                        Publicador{" "}
                        {publisher ? publisherStatuses[publisher] : "Sin datos"}
                      </p>
                      {!error && camera.playlist_finished && (
                        <p className="text-sm text-text-secondary">
                          Lista finalizada
                        </p>
                      )}
                      {!error && transitionText && (
                        <p className="text-sm text-text-secondary">
                          Última transición · {transitionText}
                        </p>
                      )}
                      {!error && camera.problem && (
                        <p className="text-sm text-danger">{camera.problem}</p>
                      )}
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          disabled={locked}
                          variant="outline"
                          aria-label={`${action} ${camera.name}`}
                          onClick={() =>
                            void update({
                              cameras: { [camera.id]: !camera.enabled },
                            })
                          }
                        >
                          {action}
                        </Button>
                        <Link
                          className="button button-ghost"
                          href={`/sources/cameras/${encodeURIComponent(camera.id)}`}
                          aria-label={`Abrir cámara ${camera.name}`}
                        >
                          Abrir cámara <ArrowRight aria-hidden="true" />
                        </Link>
                      </div>
                      {data.catalog && data.playlists && (
                        <CameraPlaylistEditor
                          cameraId={camera.id}
                          cameraName={camera.name}
                          catalog={cameraMediaForRate(
                            data.catalog,
                            camera.expected_fps,
                          )}
                          saved={data.playlists[camera.id] ?? emptyPlaylist}
                          locked={locked}
                          save={(change) => update(change, camera.id)}
                          feedback={
                            feedback?.cameraId === camera.id
                              ? feedback
                              : undefined
                          }
                        />
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="surface-card p-4">
                Aún no hay cámaras configuradas.
              </p>
            )}
          </section>
        </>
      )}
    </div>
  );
}
