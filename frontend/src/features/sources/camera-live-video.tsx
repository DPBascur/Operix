"use client";

import type Hls from "hls.js";
import { ChevronDown, Maximize, Minimize, Pause, Play, SlidersHorizontal } from "lucide-react";
import { useEffect, useRef, useState, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { equipmentCategoryLabels } from "@/services/analysis.service";
import { cameraNumber } from "./camera-diagnostics";
import { CameraFrameMatcher } from "./camera-frame-match";
import { CameraSourceClock } from "./camera-source-clock";
import { CameraLiveOverlay, overlayLabels, type OverlayStats } from "./camera-live-overlay";
import { calibrationLabels, distanceLabel } from "./camera-frame-match";
import { usePageVisible } from "./camera-visibility";

const hlsMime = "application/vnd.apple.mpegurl";
const progressTimeout = 5_000;
const initialRetryDelay = 500;
const maxRetryDelay = 8_000;
const statusLabels = {
  connecting: "Conectando video…",
  playing: "Reproduciendo",
  buffering: "Esperando video…",
  reconnecting: "Sin señal de video. Reconectando…",
  blocked: "Reproducción automática bloqueada.",
  unsupported: "Este navegador no admite la transmisión.",
  denied: "El acceso al video fue rechazado.",
};
type PlaybackStatus = keyof typeof statusLabels;

export function CameraLiveVideo({
  id,
  name,
  runId,
}: {
  id: string;
  name: string;
  runId?: string | null;
}) {
  const player = useRef<HTMLElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const pauseButton = useRef<HTMLButtonElement>(null);
  const [matcher] = useState(() => new CameraFrameMatcher());
  const [inView, setInView] = useState(false);
  const [paused, setPaused] = useState(false);
  const [overlay, setOverlay] = useState(true);
  const [showIds, setShowIds] = useState(false);
  const [showZones, setShowZones] = useState(true);
  const [showDistances, setShowDistances] = useState(true);
  const [showStats, setShowStats] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [fullscreenError, setFullscreenError] = useState(false);
  const visible = usePageVisible();

  useEffect(() => {
    const element = frame.current;
    if (!element) return;
    if (typeof IntersectionObserver === "undefined") {
      const timer = setTimeout(() => setInView(true), 0);
      return () => clearTimeout(timer);
    }
    const observer = new IntersectionObserver(([entry]) =>
      setInView(entry.isIntersecting),
    );
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const update = () =>
      setFullscreen(document.fullscreenElement === player.current);
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);

  async function toggleFullscreen() {
    setFullscreenError(false);
    try {
      if (document.fullscreenElement === player.current)
        await document.exitFullscreen();
      else await player.current?.requestFullscreen();
    } catch {
      setFullscreenError(true);
    }
  }

  return (
    <figure
      ref={player}
      className="flex min-w-0 flex-col overflow-hidden rounded-lg border border-border bg-surface fullscreen:p-3"
    >
      <figcaption className="sr-only">Video en vivo de {name}</figcaption>
      <div
        ref={frame}
        className={`grid min-h-0 ${fullscreen ? "flex-1 grid-rows-[minmax(0,1fr)_auto_auto]" : ""}`}
      >
        {visible && inView && !paused ? (
          <LiveStream
            id={id}
            name={name}
            runId={runId}
            matcher={matcher}
            pauseButton={pauseButton}
            overlay={overlay}
            showIds={showIds}
            showZones={showZones}
            showDistances={showDistances}
            showStats={showStats}
            fullscreen={fullscreen}
          />
        ) : (
          <div className="grid aspect-video place-items-center bg-black">
            {paused && (
              <p className="p-3 text-center text-sm text-white">
                Video pausado
              </p>
            )}
          </div>
        )}
      </div>
      <div
        role="group"
        aria-label="Controles de video"
        className="flex flex-wrap items-center gap-2 border-t border-border p-2"
      >
        <Button
          ref={pauseButton}
          variant="outline"
          className="min-h-11"
          aria-label={`${paused ? "Reanudar" : "Pausar"} video en vivo de ${name}`}
          onClick={() => setPaused((value) => !value)}
        >
          {paused ? <Play aria-hidden="true" size={16} /> : <Pause aria-hidden="true" size={16} />}
          {paused ? "Reanudar" : "Pausar"}
        </Button>
        <VideoToggle pressed={overlay} onClick={() => setOverlay(!overlay)}>
          Superposición
        </VideoToggle>
        <VideoToggle pressed={showDistances && overlay} disabled={!overlay} onClick={() => setShowDistances(!showDistances)}>
          Distancias
        </VideoToggle>
        <Button
          variant="outline"
          className="ms-auto min-h-11 min-w-11 px-2"
          aria-label={fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
          title={fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
          onClick={() => void toggleFullscreen()}
        >
          {fullscreen ? <Minimize aria-hidden="true" size={16} /> : <Maximize aria-hidden="true" size={16} />}
        </Button>
      </div>
      {fullscreenError && (
        <p role="status" className="text-sm text-text-secondary">
          Pantalla completa no disponible.
        </p>
      )}
      <details className="group border-t border-border px-3">
        <summary className="flex min-h-11 cursor-pointer list-none items-center gap-2 text-sm font-medium [&::-webkit-details-marker]:hidden">
          <SlidersHorizontal aria-hidden="true" size={16} /> Capas y diagnóstico
          <ChevronDown aria-hidden="true" size={16} className="ms-auto transition-transform group-open:rotate-180 motion-reduce:transition-none" />
        </summary>
        <div className="grid gap-2 pb-3">
          <div className="flex flex-wrap gap-2">
            <VideoToggle pressed={showIds} disabled={!overlay} onClick={() => setShowIds(!showIds)}>
              ID
            </VideoToggle>
            <VideoToggle pressed={showZones} disabled={!overlay} onClick={() => setShowZones(!showZones)}>
              Zonas
            </VideoToggle>
            <VideoToggle pressed={showStats} onClick={() => setShowStats(!showStats)}>
              Estadísticas
            </VideoToggle>
          </div>
          <p className="text-sm text-text-secondary">
            Las cajas discontinuas indican posiciones estimadas. FORKLIFT es la clase detectada; el tipo de equipo puede quedar sin confirmar.
          </p>
        </div>
      </details>
    </figure>
  );
}

function VideoToggle({
  children,
  pressed,
  disabled,
  onClick,
}: {
  children: string;
  pressed: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Button
      variant={pressed ? "secondary" : "outline"}
      className="min-h-11"
      aria-pressed={pressed}
      disabled={disabled}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

function LiveStream({
  id,
  name,
  runId,
  matcher,
  pauseButton,
  overlay,
  showIds,
  showZones,
  showDistances,
  showStats,
  fullscreen,
}: {
  id: string;
  name: string;
  runId?: string | null;
  matcher: CameraFrameMatcher;
  pauseButton: RefObject<HTMLButtonElement | null>;
  overlay: boolean;
  showIds: boolean;
  showZones: boolean;
  showDistances: boolean;
  showStats: boolean;
  fullscreen: boolean;
}) {
  const media = useRef<HTMLVideoElement>(null);
  const playButton = useRef<HTMLButtonElement>(null);
  const [sourceClock] = useState(() => new CameraSourceClock());
  const [status, setStatus] = useState<PlaybackStatus>("connecting");
  const [fps, setFps] = useState<number>();
  const [edgeDistance, setEdgeDistance] = useState<number>();
  const [overlayStats, setOverlayStats] = useState<OverlayStats>();
  const [overlayStatus, setOverlayStatus] = useState<keyof typeof overlayLabels>("searching");

  useEffect(() => {
    if (!media.current) return;
    const video = media.current;
    const source = `/api/v1/analysis/cameras/${encodeURIComponent(id)}/live/index.m3u8`;
    let disposed = false;
    const nativeSupported = Boolean(video.canPlayType(hlsMime));
    let tryNative = false;
    let allowMseFallback = true;
    let retryDelay = initialRetryDelay;
    let retryTimer: ReturnType<typeof setTimeout>;
    let disconnect: (() => void) | undefined;

    async function connect() {
      if (disposed) return;
      setStatus("connecting");
      setOverlayStatus("searching");
      let hls: Hls | undefined;
      let stopped = false;
      let blocked = false;
      let lastProgress = performance.now();
      let previousFrame: VideoFrameCallbackMetadata | undefined;
      let frameCallback: number | undefined;
      let lastEdgeSample = 0;
      const canMeasureFrames =
        typeof video.requestVideoFrameCallback === "function";
      const events = new AbortController();
      const options = { signal: events.signal };

      function onFrame(now: number, frame: VideoFrameCallbackMetadata) {
        lastProgress = now;
        retryDelay = initialRetryDelay;
        if (!previousFrame) previousFrame = frame;
        const elapsed = frame.presentationTime - previousFrame.presentationTime;
        if (elapsed >= 1000) {
          const frames = frame.presentedFrames - previousFrame.presentedFrames;
          setFps(Math.round((frames * 10_000) / elapsed) / 10);
          previousFrame = frame;
        }
        frameCallback = video.requestVideoFrameCallback(onFrame);
      }

      function onWaiting() {
        previousFrame = undefined;
        setFps(undefined);
        setEdgeDistance(undefined);
        setStatus((state) => (state === "playing" ? "buffering" : state));
      }

      function onPlaying() {
        blocked = false;
        lastProgress = performance.now();
        if (document.activeElement === playButton.current)
          pauseButton.current?.focus({ preventScroll: true });
        setStatus("playing");
      }

      function reconnect() {
        if (stopped) return;
        disconnect?.();
        setFps(undefined);
        setEdgeDistance(undefined);
        setStatus("reconnecting");
        retryTimer = setTimeout(() => void connect(), retryDelay);
        retryDelay = Math.min(retryDelay * 2, maxRetryDelay);
      }

      const watchdog = setInterval(() => {
        const idle = performance.now() - lastProgress;
        if (!blocked && idle >= progressTimeout) reconnect();
      }, 1000);

      disconnect = () => {
        if (stopped) return;
        stopped = true;
        events.abort();
        clearInterval(watchdog);
        if (frameCallback !== undefined)
          video.cancelVideoFrameCallback(frameCallback);
        hls?.destroy();
        sourceClock.clear();
        video.pause();
        video.removeAttribute("src");
        video.load();
      };

      video.addEventListener(
        "error",
        () => {
          if (
            tryNative &&
            allowMseFallback &&
            video.error?.code === MediaError.MEDIA_ERR_SRC_NOT_SUPPORTED
          ) {
            tryNative = false;
            disconnect?.();
            void connect();
            return;
          }
          reconnect();
        },
        options,
      );
      video.addEventListener("ended", reconnect, options);
      video.addEventListener("waiting", onWaiting, options);
      video.addEventListener("playing", onPlaying, options);
      video.addEventListener(
        "canplay",
        () => {
          void video.play().catch((error: unknown) => {
            if (
              !stopped &&
              error instanceof DOMException &&
              error.name === "NotAllowedError"
            ) {
              blocked = true;
              setStatus("blocked");
            }
          });
        },
        { ...options, once: true },
      );
      // Keep the retry delay low only after the stream has made playback progress.
      video.addEventListener(
        "timeupdate",
        () => {
          if (video.paused) return;
          const now = performance.now();
          if (!canMeasureFrames) {
            lastProgress = now;
            retryDelay = initialRetryDelay;
          }
          if (now - lastEdgeSample < 1000) return;
          lastEdgeSample = now;
          const { seekable, currentTime } = video;
          const end = seekable.length ? seekable.end(seekable.length - 1) : NaN;
          setEdgeDistance(
            Number.isFinite(end) && end >= currentTime
              ? Math.round((end - currentTime) * 10) / 10
              : undefined,
          );
        },
        options,
      );
      if (canMeasureFrames)
        frameCallback = video.requestVideoFrameCallback(onFrame);

      if (tryNative) {
        video.src = source;
        return;
      }

      try {
        const { default: HlsPlayer } = await import("hls.js");
        if (stopped) return;
        if (!HlsPlayer.isSupported()) {
          if (nativeSupported) {
            tryNative = true;
            allowMseFallback = false;
            reconnect();
            return;
          }
          disconnect();
          setStatus("unsupported");
          return;
        }
        hls = new HlsPlayer({ backBufferLength: 10 });
        hls.on(HlsPlayer.Events.FRAG_PARSING_USERDATA, (_, data) => {
          if (!stopped) sourceClock.ingest(data.samples);
        });
        hls.on(HlsPlayer.Events.ERROR, (_, data) => {
          if (data.response?.code === 401 || data.response?.code === 403) {
            disconnect?.();
            setFps(undefined);
            setEdgeDistance(undefined);
            setStatus("denied");
          } else if (data.fatal) {
            reconnect();
          }
        });
        hls.attachMedia(video);
        if (!stopped) hls.loadSource(source);
      } catch {
        reconnect();
      }
    }

    void connect();
    return () => {
      disposed = true;
      clearTimeout(retryTimer);
      disconnect?.();
    };
  }, [id, pauseButton, runId, sourceClock]);

  const playing = status === "playing";
  const frameVisible = playing || status === "buffering";
  const frameRate = playing ? cameraNumber(fps, " FPS visibles") : null;
  const edge = playing ? cameraNumber(edgeDistance, " s") : null;
  const calibration = overlayStats?.calibration;
  const pairs = overlayStatus === "clocked" ? overlayStats?.distances ?? [] : [];
  return (
    <>
      <div
        className={`relative flex flex-col items-center justify-center gap-2 overflow-hidden bg-black p-3 ${fullscreen ? "min-h-0" : "aspect-video"}`}
      >
        <video
          ref={media}
          aria-label={`Video original en vivo de ${name} (${id})`}
          aria-hidden={!frameVisible}
          className={`absolute inset-0 size-full object-contain ${frameVisible ? "" : "invisible"}`}
          muted
          playsInline
          disablePictureInPicture
          disableRemotePlayback
        />
        <CameraLiveOverlay
          id={id}
          runId={runId}
          matcher={matcher}
          sourceClock={sourceClock}
          media={media}
          active={playing && overlay}
          showIds={showIds}
          showZones={showZones}
          showDistances={showDistances}
          onStats={setOverlayStats}
          onStatus={setOverlayStatus}
        />
        <p
          role="status"
          className={
            playing ? "sr-only" : "relative rounded-md bg-black/85 px-3 py-2 text-center text-sm text-white"
          }
        >
          <span className="sr-only">{name}. </span>
          {statusLabels[status]}
        </p>
        {status === "blocked" && (
          <Button
            ref={playButton}
            className="min-h-11"
            onClick={() => void media.current?.play().catch(() => undefined)}
          >
            Reproducir video
          </Button>
        )}
      </div>
      {playing && overlay && (
        <div className="border-t border-border px-3 py-1.5 text-xs text-text-secondary">
          <p>{overlayLabels[overlayStatus]}</p>
          {showDistances && (
            <>
              <p>{calibration && overlayStatus === "clocked" ? calibrationLabels[calibration] : "Distancias a la espera de un fotograma verificado"}</p>
              {pairs.length > 0 && (
                <details className="mt-1">
                  <summary className="min-h-8 cursor-pointer py-1 font-medium">Pares observados ({pairs.length})</summary>
                  <ul className="max-h-32 space-y-1 overflow-y-auto pb-1 tabular-nums">
                    {pairs.map((pair) => (
                      <li key={`${pair.personId}:${pair.equipmentId}`}>
                        Persona #{pair.personId} · Equipo #{pair.equipmentId} · {distanceLabel(pair)} · {equipmentCategoryLabels[pair.equipmentCategory as keyof typeof equipmentCategoryLabels] ?? equipmentCategoryLabels.UNKNOWN}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </>
          )}
        </div>
      )}
      {showStats && (
        <div role="group" aria-label="Estadísticas de reproducción" className="flex flex-wrap gap-x-4 gap-y-1 border-t border-border px-3 py-2 text-sm text-text-secondary tabular-nums">
          {frameRate && <span>{frameRate}</span>}
          {edge && (
            <span>Distancia estimada al borde reproducible · {edge}</span>
          )}
          {!frameRate && !edge && (
            <span>Estadísticas de reproducción no disponibles.</span>
          )}
          {playing && overlay && (
            <>
              <span>Muestreados {overlayStats?.sampled ?? 0}</span>
              <span>Coincidencias {overlayStats?.matched ?? 0}</span>
              <span>Dibujados {overlayStats?.drawn ?? 0}</span>
              <span>Por continuidad {overlayStats?.continuity ?? 0}</span>
              <span>Estimados {overlayStats?.estimated ?? 0}</span>
              {!!overlayStats?.clockFrames && (
                <span>
                  Marca de origen · {overlayStats.clockFrames} · desfase máx. {cameraNumber(overlayStats.clockErrorMs, " ms")}
                </span>
              )}
              {!!overlayStats?.estimated && (
                <span>Estimación media · {cameraNumber(overlayStats.estimateMs / overlayStats.estimated, " ms")}</span>
              )}
              {overlayStats?.presentedAgeMs != null && (
                <span>
                  Recepción a presentación (última coincidencia) ·{" "}
                  {cameraNumber(overlayStats.presentedAgeMs, " ms")}
                </span>
              )}
              <span>
                Observaciones en ventana {overlayStats?.observations ?? 0}
              </span>
              {!!overlayStats?.sampled && (
                <span>
                  Verificación media ·{" "}
                  {cameraNumber(
                    overlayStats.sampleMs / overlayStats.sampled,
                    " ms",
                  )}
                </span>
              )}
            </>
          )}
        </div>
      )}
    </>
  );
}
