"use client";

import {
  useEffect,
  useEffectEvent,
  useRef,
  type RefObject,
} from "react";
import {
  cameraLabService,
  CameraRequestError,
} from "@/services/camera-lab.service";
import {
  type CameraFrameMatcher,
  type LiveObservation,
  gridSourceRect,
  observationLifetime,
  parseLiveObservations,
  sampleColumns,
  sampleRows,
  sampleLuma,
} from "./camera-frame-match";
import { interpolateObservedBoxes } from "./camera-estimated-boxes";
import { CameraSourceClock, ClockedObservations } from "./camera-source-clock";

export const overlayLabels = {
  searching: "Buscando fotogramas verificables",
  matched: "Se encontraron fotogramas verificables",
  clocked: "Sincronizado por marca de origen",
  unavailable: "Observaciones en vivo no disponibles",
  unsupported: "El navegador no puede verificar los fotogramas",
};

function readFingerprint(
  video: HTMLVideoElement,
  sample: CanvasRenderingContext2D,
  nativeCanvas: HTMLCanvasElement,
) {
  const width = video.videoWidth;
  const height = video.videoHeight;
  let input: CanvasImageSource = video;
  if (width % sampleColumns || height % sampleRows) {
    // Some Chromium video copy paths round source coordinates differently on
    // unaligned dimensions. Copy at native size before reading the tiny grid.
    if (nativeCanvas.width !== width) nativeCanvas.width = width;
    if (nativeCanvas.height !== height) nativeCanvas.height = height;
    const nativeContext = nativeCanvas.getContext("2d");
    if (!nativeContext) throw new Error("No se puede leer el fotograma.");
    nativeContext.drawImage(video, 0, 0);
    input = nativeCanvas;
  }
  sample.drawImage(
    input,
    ...gridSourceRect(width, height),
    0,
    0,
    sampleColumns,
    sampleRows,
  );
  return sampleLuma(sample.getImageData(0, 0, sampleColumns, sampleRows).data);
}

export type OverlayStats = {
  sampled: number;
  matched: number;
  drawn: number;
  continuity: number;
  estimated: number;
  estimateMs: number;
  sampleMs: number;
  observations: number;
  presentedAgeMs: number | null;
  clockFrames: number;
  clockErrorMs: number;
};

function draw(
  context: CanvasRenderingContext2D,
  video: HTMLVideoElement,
  observation: LiveObservation,
  showIds: boolean,
  showZones: boolean,
  continuity: boolean,
  estimated: boolean,
) {
  const { canvas } = context;
  const dpr = window.devicePixelRatio || 1;
  const width = Math.round(canvas.clientWidth * dpr);
  const height = Math.round(canvas.clientHeight * dpr);
  if (
    !width ||
    !height ||
    !(observation.objects.length || (showZones && observation.zones.length))
  )
    return false;
  if (canvas.width !== width) canvas.width = width;
  if (canvas.height !== height) canvas.height = height;
  const scale = Math.min(width / video.videoWidth, height / video.videoHeight);
  const videoWidth = video.videoWidth * scale;
  const videoHeight = video.videoHeight * scale;
  const x = (value: number) => (width - videoWidth) / 2 + value * videoWidth;
  const y = (value: number) => (height - videoHeight) / 2 + value * videoHeight;

  context.save();
  context.beginPath();
  context.rect(x(0), y(0), videoWidth, videoHeight);
  context.clip();
  context.lineWidth = 2 * dpr;
  if (estimated) context.setLineDash([6 * dpr, 4 * dpr]);
  if (showZones) {
    context.strokeStyle = "#ffd775";
    context.lineWidth = dpr;
    for (const { polygon } of observation.zones) {
      context.beginPath();
      polygon.forEach(([px, py], index) => {
        if (index === 0) context.moveTo(x(px), y(py));
        else context.lineTo(x(px), y(py));
      });
      context.closePath();
      context.stroke();
    }
    context.lineWidth = 2 * dpr;
  }
  context.font = `600 ${13 * dpr}px system-ui`;
  context.textBaseline = "top";
  for (const {
    box: [x1, y1, x2, y2],
    role,
    track_id,
  } of observation.objects) {
    const equipment = role === "forklift";
    const name = equipment ? "Equipo · FORKLIFT" : role === "person" ? "Persona" : role;
    context.strokeStyle = equipment ? "#ffb85c" : "#2fd1c8";
    context.strokeRect(x(x1), y(y1), x(x2) - x(x1), y(y2) - y(y1));
    const label =
      showIds && track_id !== null ? `${name} · #${track_id}` : name;
    const labelWidth = Math.min(context.measureText(label).width + 8 * dpr, videoWidth);
    const textX = Math.min(x(x1), x(1) - labelWidth);
    const textY = Math.max(y(0), y(y1) - 19 * dpr);
    context.fillStyle = "#101416";
    context.fillRect(
      textX,
      textY,
      labelWidth,
      19 * dpr,
    );
    context.fillStyle = "#fff";
    context.fillText(label, textX + 4 * dpr, textY + 2 * dpr, Math.max(1, labelWidth - 8 * dpr));
  }
  if (continuity || estimated) {
    const badge = estimated ? "Posición estimada" : "Imagen + PTS";
    const badgeWidth = context.measureText(badge).width + 12 * dpr;
    const left = x(1) - badgeWidth - 8 * dpr;
    const top = y(1) - 29 * dpr;
    context.fillStyle = "#101416";
    context.fillRect(left, top, badgeWidth, 21 * dpr);
    context.fillStyle = "#fff";
    context.fillText(badge, left + 6 * dpr, top + 3 * dpr);
  }
  context.restore();
  return true;
}

export function CameraLiveOverlay({
  id,
  runId,
  media,
  matcher,
  sourceClock,
  active,
  showIds,
  showZones,
  onStats,
  onStatus,
}: {
  id: string;
  runId?: string | null;
  media: RefObject<HTMLVideoElement | null>;
  matcher: CameraFrameMatcher;
  sourceClock: CameraSourceClock;
  active: boolean;
  showIds: boolean;
  showZones: boolean;
  onStats: (stats: OverlayStats) => void;
  onStatus: (status: keyof typeof overlayLabels) => void;
}) {
  const layer = useRef<HTMLCanvasElement>(null);
  const paint = useEffectEvent(
    (
      context: CanvasRenderingContext2D,
      video: HTMLVideoElement,
      item: LiveObservation,
      continuity: boolean,
      estimated = false,
    ) => draw(context, video, item, showIds, showZones && !estimated, continuity, estimated),
  );

  useEffect(() => {
    const video = media.current;
    const output = layer.current?.getContext("2d");
    const scratch = document.createElement("canvas");
    scratch.width = sampleColumns;
    scratch.height = sampleRows;
    const sample = scratch.getContext("2d", { willReadFrequently: true });
    if (!active) return;
    const nativeCanvas = document.createElement("canvas");
    const clocked = new ClockedObservations();
    const controller = new AbortController();
    const options = { signal: controller.signal };
    const stats: OverlayStats = {
      sampled: 0,
      matched: 0,
      drawn: 0,
      continuity: 0,
      estimated: 0,
      estimateMs: 0,
      sampleMs: 0,
      observations: 0,
      presentedAgeMs: null,
      clockFrames: 0,
      clockErrorMs: 0,
    };
    let pollTimer: ReturnType<typeof setTimeout>;
    let clearTimer: ReturnType<typeof setTimeout>;
    let frameCallback: number | undefined;
    let previousMediaTime = -Infinity;
    let previousCallbackTime = -Infinity;
    let lastMatch = -Infinity;
    let readable = true;
    let displayed: { stream: string; ordinal: number; item: LiveObservation; estimated: boolean } | undefined;
    matcher.invalidate();
    matcher.resetTimeline();

    function clear() {
      clearTimeout(clearTimer);
      displayed = undefined;
      if (output)
        output.clearRect(0, 0, output.canvas.width, output.canvas.height);
    }

    function reset() {
      clear();
      matcher.resetTimeline();
      previousMediaTime = -Infinity;
      previousCallbackTime = -Infinity;
      lastMatch = -Infinity;
      stats.presentedAgeMs = null;
    }

    if (
      !video ||
      !output ||
      !sample ||
      typeof video.requestVideoFrameCallback !== "function"
    ) {
      queueMicrotask(() => {
        if (!controller.signal.aborted) onStatus("unsupported");
      });
      return () => controller.abort();
    }
    const source = video;
    const context = output;
    const sampler = sample;
    // Nearest-neighbor downsampling samples the centers without blending adjacent pixels.
    sampler.imageSmoothingEnabled = false;
    const publish = setInterval(() => onStats({ ...stats }), 1000);

    function onFrame(
      callbackTime: number,
      metadata: VideoFrameCallbackMetadata,
    ) {
      if (!readable) return;
      frameCallback = source.requestVideoFrameCallback(onFrame);
      if (
        (!clocked.stream && !matcher.hasObservations) ||
        source.paused ||
        source.seeking ||
        !source.videoWidth ||
        !source.videoHeight
      ) {
        clear();
        return;
      }
      if (
        metadata.mediaTime < previousMediaTime ||
        callbackTime - previousCallbackTime > 250
      )
        reset();
      previousCallbackTime = callbackTime;
      if (metadata.mediaTime === previousMediaTime) return;
      previousMediaTime = metadata.mediaTime;
      clear();
      try {
        const started = performance.now();
        const now = Date.now();
        if (clocked.stream) {
          const mark = sourceClock.at(metadata.mediaTime, clocked.stream);
          stats.sampled++;
          stats.sampleMs += performance.now() - started;
          if (!mark) return;
          const observed = clocked.observed(mark.ordinal);
          if (observed && observationLifetime(observed, now)) {
            stats.clockFrames++;
            stats.clockErrorMs = Math.max(stats.clockErrorMs, mark.errorMs);
            if (drawObserved(observed, false, now)) {
              displayed = { stream: clocked.stream, ordinal: mark.ordinal, item: observed, estimated: false };
            }
          } else {
            const bounds = clocked.bracket(mark.ordinal);
            if (bounds && now - bounds.before.receivedMs <= 3000 &&
                observationLifetime(bounds.before, now) && observationLifetime(bounds.after, now)) {
              if (drawEstimate(bounds.before, bounds.after, 0.5, started)) {
                displayed = { stream: clocked.stream, ordinal: mark.ordinal, item: bounds.before, estimated: true };
              }
            }
          }
          return;
        }
        const fingerprint = readFingerprint(source, sampler, nativeCanvas);
        const match = matcher.match(fingerprint, metadata.mediaTime, now);
        stats.sampled++;
        stats.sampleMs += performance.now() - started;
        if (!match) {
          const estimateStarted = performance.now();
          const bounds = matcher.interpolationBounds(fingerprint, metadata.mediaTime, now);
          if (!bounds) return;
          const { before, after, fraction } = bounds;
          drawEstimate(before, after, fraction, estimateStarted);
          return;
        }
        drawObserved(match.observation, match.method === "continuity", now);
      } catch {
        clear();
        readable = false;
        onStatus("unsupported");
      }
    }

    function drawObserved(observation: LiveObservation, continuity: boolean, now: number) {
      stats.matched++;
      stats.presentedAgeMs = Math.max(0, now - observation.receivedMs);
      if (continuity) stats.continuity++;
      const painted = paint(context, source, observation, continuity);
      if (painted) stats.drawn++;
      lastMatch = performance.now();
      if (painted) clearTimer = setTimeout(clear, Math.min(200, observationLifetime(observation, now)));
      return painted;
    }

    function drawEstimate(before: LiveObservation, after: LiveObservation, fraction: number, started: number) {
      const objects = interpolateObservedBoxes(before, after, fraction);
      if (objects.length && paint(context, source, { ...before, objects }, false, true)) {
        stats.estimated++;
        stats.estimateMs += performance.now() - started;
        clearTimer = setTimeout(clear, 55);
        return true;
      }
      return false;
    }

    async function poll() {
      try {
        const data = await cameraLabService.observations(id, controller.signal);
        if (controller.signal.aborted || !readable) return;
        const batch = data === null ? null : parseLiveObservations(data);
        if (batch?.items.length && (!runId || batch.run_id === runId)) {
          clocked.update(batch);
          if (batch.stream_id) matcher.invalidate();
          else matcher.update(batch, Date.now());
          stats.observations = batch.items.length;
          onStatus(
            performance.now() - lastMatch < 1500 ? (clocked.stream ? "clocked" : "matched") : "searching",
          );
        } else {
          unavailable();
        }
        // Refreshing metadata must not blank a frame with an unchanged match.
        if (!displayed || !clocked.retains(displayed.stream, displayed.ordinal, displayed.item, displayed.estimated)) {
          clear();
        }
      } catch (error) {
        if (controller.signal.aborted || !readable) return;
        unavailable();
        if (
          error instanceof CameraRequestError &&
          [401, 403, 404].includes(error.status)
        )
          return;
      }
      pollTimer = setTimeout(poll, 400);
    }

    function unavailable() {
      matcher.invalidate();
      clocked.update(null);
      reset();
      stats.observations = 0;
      stats.presentedAgeMs = null;
      onStatus("unavailable");
      onStats({ ...stats });
    }

    for (const event of ["seeking", "emptied", "ended", "waiting", "pause"])
      source.addEventListener(event, reset, options);
    for (const event of ["resize"])
      source.addEventListener(event, clear, options);
    const resize = new ResizeObserver(clear);
    resize.observe(context.canvas);
    frameCallback = source.requestVideoFrameCallback(onFrame);
    void poll();
    return () => {
      controller.abort();
      resize.disconnect();
      clearTimeout(pollTimer);
      clearInterval(publish);
      if (frameCallback !== undefined)
        source.cancelVideoFrameCallback(frameCallback);
      matcher.invalidate();
      clear();
    };
  }, [active, id, matcher, media, onStats, onStatus, runId, sourceClock]);

  return (
    <canvas
      ref={layer}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 size-full"
    />
  );
}
