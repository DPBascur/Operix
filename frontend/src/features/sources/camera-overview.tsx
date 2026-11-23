"use client";

import { Camera } from "lucide-react";
import { useEffect, useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { operationalError } from "@/features/operations/operation-request";
import {
  cameraLabService,
  CameraRequestError,
  type LabCamera,
} from "@/services/camera-lab.service";
import {
  cameraCoverage,
  cameraFrameIsRecent,
  cameraFrameTime,
  cameraObservationPaused,
} from "./camera-diagnostics";

const statusLabels: Record<string, string> = {
  available: "Disponible",
  connecting: "Conectando",
  transmitting: "Transmitiendo",
  analyzing: "Analizando",
  no_signal: "Sin señal",
  overloaded: "Inferencia saturada",
  reconnecting: "Reconectando",
  stopped: "Detenida",
  error: "Error",
};
export function statusLabel(status: string) {
  return statusLabels[status] ?? "Estado desconocido";
}

function subscribeToVisibility(listener: () => void) {
  document.addEventListener("visibilitychange", listener);
  return () => document.removeEventListener("visibilitychange", listener);
}

function usePageVisible() {
  return useSyncExternalStore(
    subscribeToVisibility,
    () => document.visibilityState === "visible",
    () => true,
  );
}

export function useCameraData<T>(
  load: (signal: AbortSignal) => Promise<T>,
  interval: number,
  paused = false,
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [receivedAt, setReceivedAt] = useState(0);
  const [attempt, setAttempt] = useState(0);
  const visible = usePageVisible();

  useEffect(() => {
    if (paused || !visible) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await load(controller.signal);
        if (controller.signal.aborted) return;
        setData(result);
        setReceivedAt(Date.now());
        setError(undefined);
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (
          cause instanceof CameraRequestError &&
          [401, 403, 404].includes(cause.status)
        ) {
          setData(undefined);
          setError(cause);
          return;
        }
        setError(new Error(operationalError(cause)));
      }
      timer = setTimeout(refresh, interval);
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, interval, paused, attempt, visible]);

  return {
    data,
    setData,
    error,
    receivedAt,
    retry: () => setAttempt((n) => n + 1),
  };
}

export function LoadError({
  error,
  retry,
}: {
  error: Error;
  retry: () => void;
}) {
  const forbidden = error instanceof CameraRequestError && error.status === 403;
  return (
    <div className="inline-message is-error flex flex-wrap items-center gap-3">
      <p role="alert">{error.message}</p>
      {!forbidden && (
        <Button variant="outline" onClick={retry}>
          Reintentar consulta
        </Button>
      )}
    </div>
  );
}

export function CameraPreview({
  id,
  url,
  active,
  interval = 2500,
  name,
}: {
  id: string;
  url: string;
  active: boolean;
  interval?: number;
  name?: string;
}) {
  const [frame, setFrame] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  const visible = usePageVisible();
  useEffect(() => {
    if (!visible) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const blob = await cameraLabService.preview(id, url, controller.signal);
        if (controller.signal.aborted) return;
        setFrame(URL.createObjectURL(blob));
        setUnavailable(false);
      } catch (error) {
        if (controller.signal.aborted) return;
        setUnavailable(true);
        setFrame(undefined);
        if (
          error instanceof CameraRequestError &&
          [401, 403, 404].includes(error.status)
        ) {
          if (error.status !== 404) return;
        }
      }
      if (active) timer = setTimeout(refresh, interval);
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, url, active, interval, visible]);
  useEffect(
    () => () => {
      if (frame) URL.revokeObjectURL(frame);
    },
    [frame],
  );

  return (
    <>
      <div className="grid aspect-video place-items-center overflow-hidden rounded-md bg-surface-muted">
        {frame ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated JPEG as a blob URL
          <img
            src={frame}
            alt={
              name
                ? `Último fotograma analizado de ${name}`
                : "Último fotograma analizado"
            }
            className="size-full object-contain"
          />
        ) : (
          <p className="p-4 text-center text-sm text-text-secondary">
            {unavailable
              ? "No hay un fotograma disponible."
              : "Cargando fotograma…"}
          </p>
        )}
      </div>
    </>
  );
}

export function CameraCard({
  camera,
  receivedAt,
  stale = false,
}: {
  camera: Pick<
    LabCamera,
    "id" | "name" | "status" | "preview_url" | "metrics" | "last_frame_at"
  >;
  stale?: boolean;
  receivedAt: number;
}) {
  const recent =
    !cameraObservationPaused(camera.status, stale) &&
    cameraFrameIsRecent(camera.last_frame_at, camera.metrics, receivedAt);
  const timestamp = cameraFrameTime(camera.last_frame_at);
  const coverage = recent ? cameraCoverage(camera.metrics) : null;
  const fps = camera.metrics?.analysis_fps_5s;
  return (
    <>
      {recent && camera.preview_url ? (
        <CameraPreview
          key={camera.preview_url}
          id={camera.id}
          name={camera.name}
          url={camera.preview_url}
          active
          interval={5000}
        />
      ) : (
        <div className="grid aspect-video place-content-center justify-items-center gap-2 rounded-md bg-surface-muted p-3 text-center text-sm text-text-secondary">
          <Camera className="size-5" aria-hidden="true" />
          Sin fotograma reciente
        </div>
      )}
      <div className="grid gap-1">
        <h3 className="font-semibold break-words">{camera.name}</h3>
        <p className="text-sm text-text-secondary">
          {stale ? "Estado sin actualizar" : statusLabel(camera.status)}
          {recent && typeof fps === "number" && ` · ${fps.toLocaleString("es-CL", { maximumFractionDigits: 1 })} FPS`}
          {coverage !== null && ` · Cobertura (5 s) ${coverage}`}
        </p>
        {recent && timestamp && camera.last_frame_at && (
          <p className="text-sm text-text-secondary">
            <time dateTime={camera.last_frame_at}>{timestamp}</time>
          </p>
        )}
      </div>
    </>
  );
}
