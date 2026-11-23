import { AlertCircle, Video } from "lucide-react";
import type { ReactNode } from "react";
import styles from "./camera-loading-state.module.css";

const labels = {
  preparing: "Preparando fuente…",
  connecting: "Conectando transmisión…",
  awaitingFrame: "Esperando primer fotograma…",
  buffering: "Esperando video…",
  reconnecting: "Reconectando transmisión…",
  blocked: "Reproducción automática bloqueada.",
  unsupported: "Este navegador no admite la transmisión.",
  denied: "El acceso al video fue rechazado.",
};

export type CameraLoadingPhase = keyof typeof labels;

export function CameraLoadingState({
  phase,
  children,
}: {
  phase: CameraLoadingPhase;
  children?: ReactNode;
}) {
  const terminal = phase === "unsupported" || phase === "denied";
  const overVideo = phase === "buffering";
  const Icon = terminal ? AlertCircle : Video;

  return (
    <div className={styles.panel} data-camera-loading={phase} data-over-video={overVideo}>
      {!overVideo && (
        <span className={styles.signal} data-scan={!terminal && phase !== "blocked"} aria-hidden="true">
          <Icon size={24} strokeWidth={1.5} />
        </span>
      )}
      <p key={phase} role="status" className={styles.label}>{labels[phase]}</p>
      {children}
    </div>
  );
}
