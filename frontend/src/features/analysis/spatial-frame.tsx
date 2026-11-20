/* eslint-disable @next/next/no-img-element -- Fotograma local capturado del video. */
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { analysisService } from "@/services/analysis.service";
import { VideoControls } from "./video-controls";
import styles from "./analysis.module.css";

export function SpatialFrame({
  sessionId,
  active,
  locked,
  firstFrame = false,
  onCapture,
  children,
}: {
  sessionId: string;
  active: boolean;
  locked: boolean;
  firstFrame?: boolean;
  onCapture?: () => void;
  children: ReactNode;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const capture = useRef<AbortController | null>(null);
  const [frame, setFrame] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!active) video.current?.pause();
    return () => capture.current?.abort();
  }, [active]);

  async function captureFrame() {
    const media = video.current;
    if (!media || media.readyState < HTMLMediaElement.HAVE_CURRENT_DATA) {
      setMessage("Espera a que cargue el video y vuelve a capturar.");
      return;
    }
    const controller = new AbortController();
    capture.current = controller;
    const signal = AbortSignal.any([
      controller.signal,
      AbortSignal.timeout(5000),
    ]);
    setBusy(true);
    setMessage("");
    try {
      media.pause();
      // El seek entrega un fotograma al canvas incluso antes de reproducir.
      await new Promise<void>((resolve, reject) => {
        const finish = () => {
          media.removeEventListener("seeked", done);
          signal.removeEventListener("abort", cancel);
        };
        const done = () => {
          finish();
          resolve();
        };
        const cancel = () => {
          finish();
          reject(signal.reason);
        };
        media.addEventListener("seeked", done, { once: true });
        signal.addEventListener("abort", cancel, { once: true });
        media.currentTime = firstFrame ? 0 : media.currentTime;
      });
      const canvas = document.createElement("canvas");
      canvas.width = media.videoWidth;
      canvas.height = media.videoHeight;
      const context = canvas.getContext("2d");
      if (!context) throw new Error();
      context.drawImage(media, 0, 0);
      if (!context.getImageData(0, 0, 1, 1).data[3]) throw new Error();
      setFrame(canvas.toDataURL());
      onCapture?.();
    } catch {
      if (!controller.signal.aborted)
        setMessage("No se pudo capturar el fotograma. Vuelve a intentarlo.");
    } finally {
      if (capture.current === controller) {
        capture.current = null;
        setBusy(false);
      }
    }
  }

  return (
    <div className={styles.frameEditor}>
      {frame && (
        <div className={styles.stillFrame}>
          <img
            src={frame}
            alt="Fotograma de la fuente para configuración espacial"
          />
          {children}
        </div>
      )}
      {active && (
        <div className={styles.referencePlayer} hidden={Boolean(frame)}>
          <video
            ref={video}
            src={analysisService.getAnalysisSourceUrl(sessionId)}
            preload="auto"
            playsInline
            aria-label="Referencia de configuración"
          />
          <VideoControls videoRef={video} />
        </div>
      )}
      <div className={styles.actions}>
        {frame ? (
          <Button variant="outline" onClick={() => setFrame("")}>
            Volver al video
          </Button>
        ) : (
          <Button
            variant="outline"
            disabled={locked || busy}
            onClick={() => void captureFrame()}
          >
            {busy
              ? "Capturando…"
              : firstFrame
                ? "Capturar primer fotograma"
                : "Capturar fotograma de referencia"}
          </Button>
        )}
      </div>
      {message && (
        <p className={styles.notice} role="status">
          {message}
        </p>
      )}
    </div>
  );
}
