"use client";

import { useRef, useState } from "react";
import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PageTitle } from "@/components/layout/page-title";
import { Button } from "@/components/ui/button";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { StatusBadge } from "@/components/ui/status-badge";
import { operationalError } from "@/features/operations/operation-request";
import {
  cameraLabService,
  CameraRequestError,
  type CameraControlUpdate,
  type CameraLabControl,
} from "@/services/camera-lab.service";
import { CameraMediaPanels, LoadError, statusLabel, useCameraData } from "./camera-overview";
import { cameraFrameIsRecent, cameraObservationPaused } from "./camera-diagnostics";
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
  const [inspecting, setInspecting] = useState<Record<string, boolean>>({});
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
  const lockReason = error ? "Actualiza el estado antes de hacer cambios." :
    awaitingSnapshot ? "Esperando confirmación del servidor…" :
      !data?.available ? "El control del laboratorio no está disponible." : undefined;
  const third = data?.cameras.find(({ id }) => id === "lab-cam-03");

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
          <PageTitle>Control de cámaras</PageTitle>
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
                <StatusBadge tone={error || !data.available ? "warning" : data.status === "active" ? "success" : "neutral"}>
                  {error
                    ? "Estado sin actualizar"
                    : data.available
                      ? labStatuses[data.status]
                      : "Control no disponible"}
                </StatusBadge>
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
            {lockReason && <p className="text-sm text-text-secondary" role="status">{lockReason}</p>}
            {data.demonstration_playlists && (
              <div className="flex flex-wrap items-center gap-3">
                <Button variant="outline" disabled={locked || data.status !== "disabled"} onClick={() => {
                  const playlists = data.demonstration_playlists;
                  if (playlists && window.confirm("¿Cargar la selección revisada en las tres cámaras? Se reemplazarán sus listas guardadas.")) {
                    void update({ playlists, cameras: Object.fromEntries(Object.keys(playlists).map((id) => [id, true])) });
                  }
                }}>Cargar listas de demostración</Button>
                <p className="text-sm text-text-secondary">
                  {data.status === "disabled" ? "Proximidad, permanencia, ingreso y un control negativo con grabaciones reales." :
                    "Deshabilita el laboratorio para cargar las listas de demostración."}
                </p>
              </div>
            )}
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
          <details id="incorporar-camara" className="surface-card scroll-mt-24 p-4">
            <summary className="min-h-10 cursor-pointer font-semibold">Incorporar cámara</summary>
            <div className="flex flex-wrap items-center justify-between gap-3">
              {third && <a className="button button-outline" href="#configurar-camara-03">Configurar Cámara 03 <ArrowRight size={16} aria-hidden="true" /></a>}
            </div>
            <p className="text-sm text-text-secondary">
              {third
                ? "Asigna una grabación del catálogo, guarda la lista y habilita la cámara. Con capacidad de análisis de dos cámaras, la tercera transmite solo video."
                : "Cámara 03 requiere una plaza aprovisionada y una grabación autorizada en el catálogo del laboratorio."}
            </p>
          </details>
          <section className="grid gap-3" aria-labelledby="lab-control-cameras">
            <h2 id="lab-control-cameras" className="font-semibold">
              Cámaras virtuales
            </h2>
            {data.cameras.length ? (
              <ul className="grid gap-4 md:grid-cols-2">
                {data.cameras.map((camera) => {
                  const publisher = data.publisher[camera.id];
                  const stale = Boolean(error) || awaitingSnapshot;
                  const recent = !cameraObservationPaused(camera.status, stale) &&
                    cameraFrameIsRecent(camera.last_frame_at, camera.metrics, receivedAt);
                  const playlist = data.playlists?.[camera.id] ?? emptyPlaylist;
                  const source = camera.provenance?.filename;
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
                      id={camera.id === "lab-cam-03" ? "configurar-camara-03" : undefined}
                      className="surface-card grid min-w-0 scroll-mt-24 content-start gap-3 p-4"
                    >
                      <header className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0">
                          <h3 className="break-words font-semibold">{camera.name}</h3>
                          <p className="break-words text-sm text-text-secondary">{source ??
                            (playlist.media_ids.length ? "Fuente asignada en la lista" : "Sin fuente asignada")}</p>
                        </div>
                        <StatusBadge tone={camera.enabled ? "accent" : "neutral"}>
                          {camera.enabled ? "Habilitada" : "Deshabilitada"}
                        </StatusBadge>
                      </header>
                      <dl className="grid grid-cols-3 gap-2 border-y border-border py-3 text-sm">
                        <div><dt className="text-text-secondary">Publicador</dt><dd className="font-medium">{stale ? "—" : publisher ? publisherStatuses[publisher] : "Sin datos"}</dd></div>
                        <div><dt className="text-text-secondary">Video</dt><dd className="font-medium">{recent && camera.preview_url ? "Fotograma reciente" : "Sin fotograma reciente"}</dd></div>
                        <div><dt className="text-text-secondary">Motor</dt><dd className="font-medium">{stale ? "—" : camera.view_only ? "Solo video" : statusLabel(camera.status)}</dd></div>
                      </dl>
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
                          href={`/sources/cameras/${encodeURIComponent(camera.id)}#camera-settings`}
                          aria-label={`Ajustes de ${camera.name}`}
                        >
                          Ajustes <ArrowRight size={16} aria-hidden="true" />
                        </Link>
                      </div>
                      {data.catalog && data.playlists && (
                        <details className="border-t border-border">
                          <summary className="min-h-11 cursor-pointer py-3 font-medium">
                            Editar lista de reproducción · {playlist.media_ids.length}
                          </summary>
                          <CameraPlaylistEditor
                          cameraId={camera.id}
                          cameraName={camera.name}
                          catalog={cameraMediaForRate(
                            data.catalog,
                            camera.expected_fps,
                          )}
                          saved={playlist}
                          configurations={data.recording_configurations?.[camera.id]}
                          locked={locked}
                          save={(change) => update(change, camera.id)}
                          feedback={
                            feedback?.cameraId === camera.id
                              ? feedback
                              : undefined
                          }
                          />
                        </details>
                      )}
                      <details className="border-t border-border" onToggle={(event) => {
                        const open = event.currentTarget.open;
                        setInspecting((current) => ({...current, [camera.id]: open }));
                      }}>
                        <summary className="min-h-11 cursor-pointer py-3 text-sm text-text-secondary">
                          Última observación anotada
                        </summary>
                        {inspecting[camera.id] && <CameraMediaPanels camera={camera} live={false}
                          preview={recent ? camera.preview_url : null} refreshPreview recentOnly
                          previewInterval={3500} receivedAt={receivedAt} />}
                      </details>
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
