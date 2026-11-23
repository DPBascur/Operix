import { AlertCircle } from "lucide-react";
import type { ReactNode } from "react";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
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
  const loading = !terminal && phase !== "blocked";

  return (
    <div className={styles.panel} data-camera-loading={phase} data-over-video={overVideo}>
      {terminal && <AlertCircle aria-hidden="true" size={24} />}
      {loading ? (
        <OperixScanLoader message={labels[phase]} size={overVideo ? "small" : "medium"}
          variant={overVideo ? "inline" : "panel"} className={styles.label} />
      ) : <p role="status" className={styles.label}>{labels[phase]}</p>}
      {children}
    </div>
  );
}
