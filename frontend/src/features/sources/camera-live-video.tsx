"use client";

import type Hls from "hls.js";
import { useEffect, useRef, useState, type RefObject } from "react";
import { Button } from "@/components/ui/button";
import { cameraNumber } from "./camera-diagnostics";
import { usePageVisible } from "./camera-visibility";

const hlsMime = "application/vnd.apple.mpegurl";
const progressTimeout = 15_000;
const maxRetryDelay = 20_000;
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

export function CameraLiveVideo({ id, name }: { id: string; name: string }) {
  const frame = useRef<HTMLDivElement>(null);
  const pauseButton = useRef<HTMLButtonElement>(null);
  const [inView, setInView] = useState(false);
  const [paused, setPaused] = useState(false);
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

  return (
    <figure className="grid min-w-0 content-start gap-2">
      <figcaption className="text-sm font-semibold">
        Video original en vivo
      </figcaption>
      <div ref={frame} className="grid gap-2">
        {visible && inView && !paused ? (
          <LiveStream key={id} id={id} name={name} pauseButton={pauseButton} />
        ) : (
          <div className="grid aspect-video place-items-center rounded-md bg-surface-muted">
            {paused && (
              <p className="p-3 text-center text-sm text-text-secondary">
                Video pausado
              </p>
            )}
          </div>
        )}
      </div>
      <Button
        ref={pauseButton}
        variant="outline"
        className="min-h-11 w-fit"
        aria-label={`${paused ? "Reanudar" : "Pausar"} video en vivo de ${name}`}
        onClick={() => setPaused((value) => !value)}
      >
        {paused ? "Reanudar video" : "Pausar video"}
      </Button>
    </figure>
  );
}

function LiveStream({
  id,
  name,
  pauseButton,
}: {
  id: string;
  name: string;
  pauseButton: RefObject<HTMLButtonElement | null>;
}) {
  const media = useRef<HTMLVideoElement>(null);
  const playButton = useRef<HTMLButtonElement>(null);
  const [status, setStatus] = useState<PlaybackStatus>("connecting");
  const [fps, setFps] = useState<number>();
  const [edgeDistance, setEdgeDistance] = useState<number>();

  useEffect(() => {
    if (!media.current) return;
    const video = media.current;
    const source = `/api/v1/analysis/cameras/${encodeURIComponent(id)}/live/index.m3u8`;
    let disposed = false;
    const nativeSupported = Boolean(video.canPlayType(hlsMime));
    let tryNative = nativeSupported;
    let allowMseFallback = true;
    let retryDelay = 2000;
    let retryTimer: ReturnType<typeof setTimeout>;
    let disconnect: (() => void) | undefined;

    async function connect() {
      if (disposed) return;
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
        retryDelay = 2000;
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
            retryDelay = 2000;
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
  }, [id, pauseButton]);

  const playing = status === "playing";
  const frameRate = playing ? cameraNumber(fps, " FPS visibles") : null;
  const edge = playing ? cameraNumber(edgeDistance, " s") : null;
  return (
    <>
      <div className="relative flex aspect-video flex-col items-center justify-center gap-2 overflow-hidden rounded-md bg-surface-muted p-3">
        <video
          ref={media}
          aria-label={`Video original en vivo de ${name} (${id})`}
          aria-hidden={!playing}
          className={`absolute inset-0 size-full object-contain ${playing ? "" : "invisible"}`}
          muted
          playsInline
          disablePictureInPicture
          disableRemotePlayback
        />
        <p
          role="status"
          className={
            playing ? "sr-only" : "text-center text-sm text-text-secondary"
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
      {(frameRate || edge) && (
        <div className="flex flex-wrap gap-x-3 text-sm text-text-secondary tabular-nums">
          {frameRate && <span>{frameRate}</span>}
          {edge && (
            <span>Distancia estimada al borde reproducible · {edge}</span>
          )}
        </div>
      )}
    </>
  );
}
