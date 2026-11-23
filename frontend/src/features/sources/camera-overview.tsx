"use client";

import { Camera } from "lucide-react";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { operationalError } from "@/features/operations/operation-request";
import {
  cameraLabService,
  CameraRequestError,
  type LabCamera,
} from "@/services/camera-lab.service";
import {
  cameraCoverage,
  cameraFrameAge,
  cameraFrameIsRecent,
  cameraFrameTime,
  cameraFrameWindowMs,
  cameraNumber,
  cameraObservationPaused,
} from "./camera-diagnostics";
import { CameraLiveVideo } from "./camera-live-video";
import { usePageVisible } from "./camera-visibility";

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

type CameraPreviewProps = {
  id: string;
  url: string;
  active: boolean;
  interval?: number;
  name?: string;
  recentOnly?: boolean;
};

export function CameraPreview(props: CameraPreviewProps) {
  const visible = usePageVisible();
  const { id, url, active, interval, recentOnly } = props;
  return (
    <div className="grid aspect-video place-items-center overflow-hidden rounded-md bg-surface-muted">
      {visible && (
        <CameraPreviewFrame
          key={JSON.stringify([id, url, active, interval, recentOnly])}
          {...props}
        />
      )}
    </div>
  );
}

function CameraPreviewFrame({
  id,
  url,
  active,
  interval = 2500,
  name,
  recentOnly = false,
}: CameraPreviewProps) {
  const [frame, setFrame] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let refreshTimer: ReturnType<typeof setTimeout>;
    let expiration: ReturnType<typeof setTimeout>;
    let objectUrl: string | undefined;

    function releaseFrame() {
      clearTimeout(expiration);
      if (objectUrl) URL.revokeObjectURL(objectUrl);
      objectUrl = undefined;
    }

    function clearFrame() {
      releaseFrame();
      setFrame(undefined);
      setUnavailable(true);
    }

    async function refresh() {
      const startedAt = performance.now();
      const signal = recentOnly
        ? AbortSignal.any([
            controller.signal,
            AbortSignal.timeout(cameraFrameWindowMs),
          ])
        : controller.signal;
      try {
        const blob = await cameraLabService.preview(id, url, signal);
        if (controller.signal.aborted) return;
        const remaining = cameraFrameWindowMs - (performance.now() - startedAt);
        if (recentOnly && (signal.aborted || remaining <= 0)) {
          clearFrame();
        } else {
          releaseFrame();
          objectUrl = URL.createObjectURL(blob);
          setFrame(objectUrl);
          setUnavailable(false);
          if (recentOnly) expiration = setTimeout(clearFrame, remaining);
        }
      } catch (error) {
        if (controller.signal.aborted) return;
        clearFrame();
        if (
          error instanceof CameraRequestError &&
          [401, 403].includes(error.status)
        )
          return;
      }
      if (active) refreshTimer = setTimeout(refresh, interval);
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(refreshTimer);
      releaseFrame();
    };
  }, [id, url, active, interval, recentOnly]);

  return frame ? (
    // eslint-disable-next-line @next/next/no-img-element -- authenticated JPEG as a blob URL
    <img
      src={frame}
      alt={
        name
          ? `Fotograma anotado de la última observación de ${name}`
          : "Fotograma anotado de la última observación"
      }
      className="size-full object-contain"
    />
  ) : (
    <p className="p-4 text-center text-sm text-text-secondary">
      {unavailable ? "No hay un fotograma disponible." : "Cargando fotograma…"}
    </p>
  );
}

export function CameraMediaPanels({
  camera,
  live,
  preview,
  refreshPreview,
  recentOnly,
  receivedAt,
  previewInterval,
  settingsUrl,
}: {
  camera: Pick<LabCamera, "id" | "name" | "metrics" | "last_frame_at"> & {
    run_id?: string | null;
    view_only?: boolean;
  };
  live: boolean;
  preview: string | null;
  refreshPreview: boolean;
  recentOnly: boolean;
  receivedAt: number;
  previewInterval?: number;
  settingsUrl?: string;
}) {
  const { id, name, last_frame_at: frameAt } = camera;
  const timestamp = cameraFrameTime(frameAt);
  const age = cameraFrameAge(frameAt, camera.metrics, receivedAt);
  const [showPreview, setShowPreview] = useState(false);

  const annotated = (
    <figure className={`grid min-w-0 gap-2 ${live ? "mt-2 max-w-lg" : ""}`}>
      {!live && (
        <figcaption className="text-sm font-semibold">
          Última observación anotada
        </figcaption>
      )}
      {preview ? (
        <CameraPreview
          key={camera.run_id}
          id={id}
          name={name}
          url={preview}
          active={refreshPreview}
          interval={previewInterval}
          recentOnly={recentOnly}
        />
      ) : (
        <div className="grid aspect-video place-content-center justify-items-center gap-2 rounded-md bg-surface-muted p-3 text-center text-sm text-text-secondary">
          <Camera className="size-5" aria-hidden="true" />
          {recentOnly ? "Sin fotograma reciente" : "Sin fotograma disponible"}
        </div>
      )}
      {((timestamp && frameAt) || age !== null) && (
        <div className="text-sm text-text-secondary">
          {timestamp && frameAt && (
            <p>
              Última recepción del análisis ·{" "}
              <time dateTime={frameAt}>{timestamp}</time>
            </p>
          )}
          {age !== null && (
            <p className="tabular-nums">
              Antigüedad al consultar · {cameraNumber(age / 1000, " s")}
            </p>
          )}
        </div>
      )}
    </figure>
  );

  if (!live) return annotated;

  return (
    <div className="grid min-w-0 gap-3">
      <CameraLiveVideo
        enabled={refreshPreview}
        settingsUrl={settingsUrl}
        viewOnly={camera.view_only}
        id={id}
        name={name}
        runId={camera.run_id}
      />
      <details
        onToggle={(event) => setShowPreview(event.currentTarget.open)}
        className="border-t border-border pt-1"
      >
        <summary className="min-h-11 cursor-pointer py-3 text-sm font-semibold">
          Última observación anotada
        </summary>
        {showPreview && annotated}
      </details>
    </div>
  );
}

export function CameraCard({
  camera,
  live,
  receivedAt,
  stale = false,
}: {
  camera: Pick<
    LabCamera,
    "id" | "name" | "status" | "preview_url" | "metrics" | "last_frame_at"
  > & { run_id?: string | null };
  live: boolean;
  stale?: boolean;
  receivedAt: number;
}) {
  const recent =
    !cameraObservationPaused(camera.status, stale) &&
    cameraFrameIsRecent(camera.last_frame_at, camera.metrics, receivedAt);
  const coverage = recent ? cameraCoverage(camera.metrics) : null;
  const fps = cameraNumber(camera.metrics?.analysis_fps_5s, " FPS de análisis");
  return (
    <>
      <div className="grid gap-1">
        <h3 className="font-semibold break-words">{camera.name}</h3>
        <p className="text-sm text-text-secondary">
          {stale ? "Estado sin actualizar" : statusLabel(camera.status)}
          {recent && fps && ` · ${fps}`}
          {coverage !== null && ` · Cobertura (5 s) ${coverage}`}
        </p>
      </div>
      <CameraMediaPanels
        camera={camera}
        live={live}
        preview={recent ? camera.preview_url : null}
        refreshPreview
        recentOnly
        receivedAt={receivedAt}
        previewInterval={3500}
      />
    </>
  );
}
