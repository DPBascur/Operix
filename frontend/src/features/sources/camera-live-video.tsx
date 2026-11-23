"use client";

import type Hls from "hls.js";
import { ArrowUpRight, Maximize, Minimize, Pause, Play, Settings2, SlidersHorizontal, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useId, useRef, useState, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { equipmentCategoryLabels } from "@/services/analysis.service";
import { cameraNumber } from "./camera-diagnostics";
import { CameraFrameMatcher } from "./camera-frame-match";
import { CameraSourceClock } from "./camera-source-clock";
import { CameraLiveOverlay, overlayLabels, type OverlayStats } from "./camera-live-overlay";
import { calibrationLabels, distanceLabel } from "./camera-frame-match";
import { useCameraViewPreferences } from "./camera-view-preferences";
import { usePageVisible } from "./camera-visibility";
import { CameraLoadingState, type CameraLoadingPhase } from "./camera-loading-state";

const hlsMime = "application/vnd.apple.mpegurl";
const progressTimeout = 5_000;
const initialRetryDelay = 500;
const maxRetryDelay = 8_000;
type PlaybackStatus = Exclude<CameraLoadingPhase, "preparing"> | "playing";
type CameraPlayerVariant = "preview" | "monitoring" | "detail";

export function CameraLiveVideo({
  id,
  name,
  runId,
  variant = "detail",
  enabled = true,
  viewOnly = false,
  cameraUrl,
  settingsUrl,
  operationalState,
  onPlaybackFps,
}: {
  id: string;
  name: string;
  variant?: CameraPlayerVariant;
  enabled?: boolean;
  viewOnly?: boolean;
  cameraUrl?: string;
  settingsUrl?: string;
  operationalState?: string;
  runId?: string | null;
  onPlaybackFps?: (fps: number | null) => void;
}) {
  const player = useRef<HTMLElement>(null);
  const frame = useRef<HTMLDivElement>(null);
  const pauseButton = useRef<HTMLButtonElement>(null);
  const fullscreenButton = useRef<HTMLButtonElement>(null);
  const layerButton = useRef<HTMLButtonElement>(null);
  const enteredFullscreen = useRef(false);
  const [layers, setLayers] = useState(false);
  const [matcher] = useState(() => new CameraFrameMatcher());
  const [inView, setInView] = useState(false);
  const [paused, setPaused] = useState(false);
  const settingsId = useId();
  const [preferences, setPreference] = useCameraViewPreferences(id);
  const { detections: overlay, identifiers: showIds, zones: showZones, distances: showDistances, diagnostics: showStats, unit: metricUnit } = preferences;
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
    const observer = new IntersectionObserver(([entry]) => {
      clearTimeout(suspend);
      if (entry.isIntersecting) setInView(true);
      else if (variant === "preview") suspend = setTimeout(() => setInView(false), 1200);
    }, { rootMargin: variant === "preview" ? "84px" : "0px" });
    let suspend: ReturnType<typeof setTimeout>;
    observer.observe(element);
    return () => {
      observer.disconnect();
      clearTimeout(suspend);
    };
  }, [variant]);

  useEffect(() => {
    const update = () => {
      const active = document.fullscreenElement === player.current;
      if (!active && enteredFullscreen.current) {
        fullscreenButton.current?.focus({ preventScroll: true });
      }
      enteredFullscreen.current = active;
      setFullscreen(active);
    };
    document.addEventListener("fullscreenchange", update);
    return () => document.removeEventListener("fullscreenchange", update);
  }, []);

  useEffect(() => {
    if (!layers) return;
    function outside(event: PointerEvent) {
      if (!player.current?.contains(event.target as Node)) setLayers(false);
    }
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [layers]);

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
      className="operix-live-player"
      data-camera-player={fullscreen ? "fullscreen" : variant}
      onKeyDown={(event) => {
        if (event.key === "Escape" && layers && !fullscreen) {
          event.stopPropagation();
          setLayers(false);
          layerButton.current?.focus();
        }
      }}
    >
      <figcaption className="sr-only">Video en vivo de {name}</figcaption>
      <div ref={frame} className="operix-live-frame">
        {enabled && visible && inView && !paused ? (
          <LiveStream
            id={id}
            name={name}
            runId={runId}
            matcher={matcher}
            pauseButton={pauseButton}
            overlay={!viewOnly && overlay}
            showIds={showIds}
            showZones={showZones}
            showDistances={showDistances}
            showStats={showStats && (variant !== "preview" || fullscreen)}
            compact={variant === "preview" && !fullscreen}
            operationalState={operationalState}
            onPlaybackFps={onPlaybackFps}
            metricUnit={metricUnit}
            onMetricUnit={(unit) => setPreference("unit", unit)}
          />
        ) : enabled && !paused ? <CameraLoadingState phase="preparing" /> : (
          <div className="grid size-full place-items-center text-sm text-white/75">
            {!enabled ? "Cámara detenida" : "Video pausado"}
          </div>
        )}
        {fullscreenError && <p className="operix-player-notice" role="status">Pantalla completa no disponible.</p>}
      </div>
      <div role="group" aria-label="Controles de video" className="operix-player-bar">
        <span className="flex min-w-0 items-center gap-2">
          <span className="truncate text-sm font-semibold">
            {cameraUrl ? <Link href={cameraUrl} title={name} aria-label={`Abrir cámara ${name}`}>{name}</Link> : name}
          </span>
          {viewOnly && <span className="shrink-0 rounded-full border border-white/25 px-2 py-0.5 text-xs">Solo video</span>}
        </span>
        <div className="operix-player-actions">
          <button
            ref={pauseButton}
            type="button"
            aria-label={`${paused ? "Reanudar" : "Pausar"} video en vivo de ${name}`}
            title={paused ? "Reanudar" : "Pausar"}
            disabled={!enabled}
            onClick={() => setPaused((value) => !value)}
          >
            {paused ? <Play aria-hidden="true" size={17} /> : <Pause aria-hidden="true" size={17} />}
          </button>
          {!viewOnly && <button ref={layerButton} type="button" aria-expanded={layers} aria-controls={layers ? settingsId : undefined} aria-label="Capas y diagnóstico"
            title="Capas y diagnóstico" onClick={() => setLayers(!layers)}>
            <SlidersHorizontal aria-hidden="true" size={17} />
          </button>}
          {settingsUrl && variant !== "preview" && <Link href={settingsUrl} aria-label="Ajustes de cámara" title="Ajustes de cámara" onClick={() => {
            if (settingsUrl.startsWith("#")) {
              const panel = document.getElementById(settingsUrl.slice(1));
              if (panel instanceof HTMLDetailsElement) panel.open = true;
            }
          }}><Settings2 size={17} /></Link>}
          {cameraUrl && variant !== "preview" && <Link href={cameraUrl} aria-label={`Ir a la vista individual de ${name}`} title="Abrir cámara"><ArrowUpRight size={17} /></Link>}
          <button
            ref={fullscreenButton}
            type="button"
            aria-label={fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
            title={fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
            onClick={() => void toggleFullscreen()}
          >
            {fullscreen ? <Minimize aria-hidden="true" size={17} /> : <Maximize aria-hidden="true" size={17} />}
          </button>
        </div>
      </div>
      {layers && !viewOnly && (
        <section id={settingsId} className="operix-player-settings" aria-label="Ajustes de visualización">
          <div className="flex items-center justify-between gap-2">
            <h2 className="text-sm font-semibold">Capas de visualización</h2>
            <Button size="icon" variant="ghost" aria-label="Cerrar ajustes de visualización" onClick={() => {
              setLayers(false);
              layerButton.current?.focus();
            }}><X size={17} /></Button>
          </div>
          <VideoToggle pressed={overlay} onClick={() => setPreference("detections", !overlay)}>Detecciones</VideoToggle>
          <VideoToggle pressed={showDistances} disabled={!overlay} onClick={() => setPreference("distances", !showDistances)}>Distancias</VideoToggle>
          <VideoToggle pressed={showZones} disabled={!overlay} onClick={() => setPreference("zones", !showZones)}>Zonas</VideoToggle>
          <VideoToggle pressed={showIds} disabled={!overlay} onClick={() => setPreference("identifiers", !showIds)}>Identificadores</VideoToggle>
          {(variant !== "preview" || fullscreen) && <div className="border-t border-border pt-1">
            <VideoToggle pressed={showStats} onClick={() => setPreference("diagnostics", !showStats)}>Diagnóstico</VideoToggle>
          </div>}
          <p className="text-xs text-text-secondary">Estos ajustes solo cambian lo que ves. Las cajas discontinuas indican posiciones estimadas.</p>
        </section>
      )}
    </figure>
  );
}

function VideoToggle({ children, pressed, disabled, onClick }: {
  children: string;
  pressed: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button type="button" className="operix-layer-switch" role="switch"
      aria-checked={pressed && !disabled} disabled={disabled} onClick={onClick}>
      {children}<span aria-hidden="true" />
    </button>
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
  compact,
  operationalState,
  metricUnit,
  onMetricUnit,
  onPlaybackFps,
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
  compact: boolean;
  operationalState?: string;
  metricUnit: "m" | "cm";
  onMetricUnit: (unit: "m" | "cm") => void;
  onPlaybackFps?: (fps: number | null) => void;
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
      setStatus((phase) => phase === "reconnecting" ? phase : "connecting");
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
        if (!previousFrame) {
          previousFrame = frame;
          setStatus("playing");
        }
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
        if (!canMeasureFrames) setStatus("playing");
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
        video.addEventListener("loadedmetadata", () => setStatus("awaitingFrame"), { ...options, once: true });
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
        hls.on(HlsPlayer.Events.MANIFEST_PARSED, () => {
          if (!stopped) setStatus("awaitingFrame");
        });
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
  }, [id, pauseButton, sourceClock]);

  const playing = status === "playing";
  useEffect(() => {
    onPlaybackFps?.(playing ? fps ?? null : null);
  }, [fps, onPlaybackFps, playing]);
  useEffect(() => () => onPlaybackFps?.(null), [onPlaybackFps]);
  const frameVisible = playing || status === "buffering";
  const frameRate = playing ? cameraNumber(fps, " FPS visibles") : null;
  const edge = playing ? cameraNumber(edgeDistance, " s") : null;
  const calibration = overlayStats?.calibration;
  const pairs = overlayStatus === "clocked" ? overlayStats?.distances ?? [] : [];
  return (
    <>
      <div
        className="absolute inset-0 flex flex-col items-center justify-center gap-2 overflow-hidden bg-black p-3"
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
          metricUnit={metricUnit}
          onStats={setOverlayStats}
          onStatus={setOverlayStatus}
        />
        {playing ? <p role="status" className="sr-only">Video disponible</p> : (
          <CameraLoadingState phase={status}>
            {status === "blocked" && (
              <Button
                ref={playButton}
                onClick={() => void media.current?.play().catch(() => undefined)}
              >
                Reproducir video
              </Button>
            )}
          </CameraLoadingState>
        )}
      </div>
      {playing && overlay && (
        <div className="operix-player-status">
          <p>{operationalState && operationalState !== "Analizando" ? operationalState : overlayStatus === "searching" ? "Sincronizando análisis…" : overlayLabels[overlayStatus]}</p>
          {showDistances && !compact && (
            <>
              <p>{calibration && overlayStatus === "clocked" ? calibrationLabels[calibration] : "Distancias a la espera de un fotograma verificado"}</p>
              {pairs.length > 0 && (
                <details className="mt-1">
                  <summary className="min-h-8 cursor-pointer py-1 font-medium">Pares observados ({pairs.length})</summary>
                  {calibration === "VALID" && pairs.some((pair) => pair.unit === "m") && (
                    <label className="mb-2 flex items-center gap-2">
                      Unidad física
                      <select className="rounded-md border border-white/30 bg-[#162333] p-1 text-white"
                        value={metricUnit} onChange={(event) => onMetricUnit(event.target.value === "cm" ? "cm" : "m")}>
                        <option value="m">Metros</option>
                        <option value="cm">Centímetros</option>
                      </select>
                    </label>
                  )}
                  <ul className="max-h-32 space-y-1 overflow-y-auto pb-1 tabular-nums">
                    {pairs.map((pair) => (
                      <li key={`${pair.personId}:${pair.equipmentId}`}>
                        Persona #{pair.personId} · Equipo #{pair.equipmentId} · {distanceLabel(pair, metricUnit)} · {equipmentCategoryLabels[pair.equipmentCategory as keyof typeof equipmentCategoryLabels] ?? equipmentCategoryLabels.UNKNOWN}
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
        <div role="group" aria-label="Estadísticas de reproducción" className="operix-player-diagnostics tabular-nums">
          {frameRate && <span>{frameRate}</span>}
          {edge && (
            <span>Distancia estimada al borde reproducible · {edge}</span>
          )}
          {!frameRate && !edge && (
            <span>Estadísticas de reproducción no disponibles.</span>
          )}
          {playing && operationalState === "Solo video" && <p className="operix-player-status">Solo video · Análisis desactivado</p>}
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
