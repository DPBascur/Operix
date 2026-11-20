"use client";

import {
  Maximize,
  Minimize,
  Pause,
  Play,
  Volume2,
  VolumeX,
} from "lucide-react";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { useEffect, useState, type RefObject } from "react";

import styles from "./analysis.module.css";

function clock(seconds: number) {
  const total = Math.floor(seconds);
  const minutes = Math.floor(total / 60);
  return `${minutes}:${String(total % 60).padStart(2, "0")}`;
}

export function VideoControls({
  videoRef,
  loadingMessage = "Cargando video…",
}: {
  videoRef: RefObject<HTMLVideoElement | null>;
  loadingMessage?: string;
}) {
  const [media, setMedia] = useState({
    time: 0,
    duration: 0,
    playing: false,
    muted: false,
    volume: 1,
    fullscreen: false,
    loading: true,
    failed: false,
  });
  const [message, setMessage] = useState("");

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    const sync = () =>
      setMedia({
        time: video.currentTime,
        duration: Number.isFinite(video.duration) ? video.duration : 0,
        playing: !video.paused && !video.ended,
        muted: video.muted,
        volume: video.volume,
        fullscreen: document.fullscreenElement === video.parentElement,
        loading:
          video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA && !video.error,
        failed: Boolean(video.error),
      });
    const events = [
      "loadstart",
      "loadedmetadata",
      "loadeddata",
      "canplay",
      "emptied",
      "error",
      "durationchange",
      "timeupdate",
      "play",
      "pause",
      "ended",
      "volumechange",
    ];
    for (const event of events) video.addEventListener(event, sync);
    document.addEventListener("fullscreenchange", sync);
    sync();
    return () => {
      for (const event of events) video.removeEventListener(event, sync);
      document.removeEventListener("fullscreenchange", sync);
    };
  }, [videoRef]);

  return (
    <div
      className={`operix-video-controls ${styles.mediaControls}`}
      role="group"
      aria-label="Controles del video"
    >
      {media.failed ? (
        <p role="status">
          No se pudo leer el video. Prueba otra fuente o vuelve a cargarlo.
        </p>
      ) : (
        media.loading && (
          <OperixScanLoader
            size="small"
            variant="process"
            message={loadingMessage}
          />
        )
      )}
      <input
        className="operix-video-timeline"
        type="range"
        aria-label="Posición del video"
        aria-valuetext={`${clock(media.time)} de ${clock(media.duration)}`}
        min={0}
        max={media.duration || 1}
        step="any"
        value={Math.min(media.time, media.duration)}
        disabled={!media.duration}
        style={
          {
            "--played": `${media.duration ? (media.time / media.duration) * 100 : 0}%`,
          } as React.CSSProperties
        }
        onChange={(event) => {
          if (videoRef.current)
            videoRef.current.currentTime = event.currentTarget.valueAsNumber;
        }}
      />
      <div className="operix-video-actions">
        <button
          type="button"
          aria-label={media.playing ? "Pausar video" : "Reproducir video"}
          disabled={media.loading || media.failed}
          onClick={() => {
            const video = videoRef.current;
            if (!video) return;
            setMessage("");
            if (video.paused)
              void video
                .play()
                .catch(() => setMessage("No se pudo reproducir el video."));
            else video.pause();
          }}
        >
          {media.playing ? <Pause size={17} /> : <Play size={17} />}
        </button>
        <span>
          {clock(media.time)} / {clock(media.duration)}
        </span>
        <div className="operix-video-volume">
          <button
            type="button"
            aria-label={media.muted ? "Activar sonido" : "Silenciar video"}
            disabled={media.failed}
            onClick={() => {
              if (videoRef.current)
                videoRef.current.muted = !videoRef.current.muted;
            }}
          >
            {media.muted || media.volume === 0 ? (
              <VolumeX size={17} />
            ) : (
              <Volume2 size={17} />
            )}
          </button>
          <input
            type="range"
            aria-label="Volumen del video"
            disabled={media.failed}
            min={0}
            max={1}
            step={0.05}
            value={media.muted ? 0 : media.volume}
            onChange={(event) => {
              const video = videoRef.current;
              if (video) {
                video.volume = event.currentTarget.valueAsNumber;
                video.muted = false;
              }
            }}
          />
        </div>
        <button
          type="button"
          aria-label={
            media.fullscreen
              ? "Salir de pantalla completa"
              : "Pantalla completa"
          }
          onClick={async () => {
            const video = videoRef.current;
            if (!video) return;
            try {
              if (document.fullscreenElement) await document.exitFullscreen();
              else if (video.parentElement?.requestFullscreen)
                await video.parentElement.requestFullscreen();
              else {
                const nativeVideo = video as HTMLVideoElement & {
                  webkitEnterFullscreen?: () => void;
                };
                if (nativeVideo.webkitEnterFullscreen)
                  nativeVideo.webkitEnterFullscreen();
                else
                  setMessage(
                    "Pantalla completa no disponible en este navegador.",
                  );
              }
            } catch {
              setMessage("No se pudo cambiar la pantalla completa.");
            }
          }}
        >
          {media.fullscreen ? <Minimize size={17} /> : <Maximize size={17} />}
        </button>
      </div>
      {message && <p role="status">{message}</p>}
    </div>
  );
}
