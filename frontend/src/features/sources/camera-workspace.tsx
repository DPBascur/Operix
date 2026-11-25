"use client";

import { ArrowUpRight, Camera, LayoutGrid, Maximize, Plus, RectangleHorizontal, Settings2, VideoOff } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";

import { canOpen, useSession } from "@/features/auth/session-provider";
import { cameraLabService, type LabCamera } from "@/services/camera-lab.service";
import { cameraFrameIsRecent, cameraObservationPaused, cameraPlaylistHandoff } from "./camera-diagnostics";
import { CameraLiveVideo } from "./camera-live-video";
import { CameraLoadingState } from "./camera-loading-state";
import { CameraPreview, LoadError, statusLabel, useCameraData } from "./camera-overview";
import styles from "./camera-workspace.module.css";

const running = new Set(["connecting", "transmitting", "analyzing", "no_signal", "overloaded", "reconnecting"]);

function monitorNoPreview(state: string) {
  return state === "Detenida" ? "Cámara detenida" : "Sin vista previa";
}

export function cameraHref(id: string) {
  return `/sources/cameras/${encodeURIComponent(id)}`;
}

function CameraTile({ camera, live, monitor, enabled, handoff, preview, canEdit, stale }: {
  camera: LabCamera;
  live: boolean;
  monitor: boolean;
  enabled: boolean;
  handoff: boolean;
  preview: boolean;
  canEdit: boolean;
  stale: boolean;
}) {
  const tile = useRef<HTMLElement>(null);
  const fullscreenButton = useRef<HTMLButtonElement>(null);
  const [fullscreenError, setFullscreenError] = useState(false);
  const href = cameraHref(camera.id);
  const state = stale ? "Estado sin actualizar" : handoff ? "Cambiando grabación" : statusLabel(camera.status);
  const settingsHref = canEdit ? `${href}#camera-settings` : undefined;
  const rulesPaused = camera.playback?.spatial_suspension_reason;
  const noActiveRules = camera.effective_rules && !camera.effective_rules.some((rule) => rule.enabled);

  if (live) {
    return <>
      <CameraLiveVideo id={camera.id} name={camera.name} runId={camera.run_id} operationalState={state} enabled={enabled || handoff} viewOnly={camera.view_only}
        cameraUrl={href} settingsUrl={settingsHref} variant={monitor ? "monitoring" : "preview"} />
      {monitor && !stale && (
        <div className="grid gap-1 px-1 py-2 text-xs text-text-secondary" aria-live="polite">
          {!!camera.playback?.recording_revision && (
            <p>{camera.playback.demonstration ? "Escenario experimental" : "Configuración de grabación"} · revisión {camera.playback.recording_revision}</p>
          )}
          {running.has(camera.status) && !camera.view_only && (rulesPaused || noActiveRules) && (
            <p>{rulesPaused ? `Reglas espaciales suspendidas. ${rulesPaused}` : "Sin reglas activas para esta ejecución."}</p>
          )}
          {camera.last_event && (
            <p><Link className="underline" href={`/events/${camera.last_event.id}`}>Último evento registrado</Link>
              {" · "}{new Intl.DateTimeFormat("es-CL", { timeStyle: "short", dateStyle: "short", timeZone: "America/Santiago" }).format(new Date(camera.last_event.occurred_at))}
            </p>
          )}
        </div>
      )}
    </>;
  }

  async function expand() {
    try {
      if (!tile.current?.requestFullscreen) throw new Error();
      if (document.fullscreenElement === tile.current) {
        await document.exitFullscreen();
        fullscreenButton.current?.focus({ preventScroll: true });
      } else {
        await tile.current.requestFullscreen();
      }
      setFullscreenError(false);
    } catch {
      setFullscreenError(true);
    }
  }

  return (
    <article ref={tile} className={styles.tile} aria-label={camera.name}>
      <div className={styles.preview}>
        {preview && camera.preview_url ? (
          <CameraPreview id={camera.id} name={camera.name} url={camera.preview_url} active interval={3500} recentOnly />
        ) : (
          <div className={styles.noFrame}>
            <VideoOff size={23} aria-hidden="true" />
            <span>{running.has(camera.status) && !stale ? "Esperando fotograma" : monitorNoPreview(state)}</span>
          </div>
        )}
        <span className={styles.signal} data-active={camera.status === "analyzing" && !stale}>
          <span aria-hidden="true" />{state}
        </span>
      </div>
      <div className={styles.bar}>
        <h3><Link href={href} aria-label={`Abrir cámara ${camera.name}`}>{camera.name}</Link></h3>
        <div className={styles.controls}>
          {settingsHref && <Link href={settingsHref} aria-label={`Ajustes de ${camera.name}`} title="Ajustes"><Settings2 size={17} /></Link>}
          <button ref={fullscreenButton} type="button" onClick={() => void expand()} aria-label={`Pantalla completa de ${camera.name}`} title="Pantalla completa"><Maximize size={17} /></button>
          <Link href={href} aria-label={`Ir a la vista individual de ${camera.name}`} title="Abrir cámara"><ArrowUpRight size={18} /></Link>
        </div>
      </div>
      {fullscreenError && <p className={styles.fullscreenNotice} role="status">La vista previa no pudo entrar en pantalla completa.</p>}
    </article>
  );
}

export function CameraWorkspace({ monitor = false }: { monitor?: boolean }) {
  const { data, error, receivedAt, retry } = useCameraData(cameraLabService.list, 5000);
  const { user } = useSession();
  const canControl = !!user && canOpen("/admin/camera-lab", user.role);
  const [layout, setLayout] = useState<"grid" | "focus">("grid");
  const [primaryId, setPrimaryId] = useState<string>();
  const cameras = data?.enabled ? data.cameras : [];
  const selected = cameras.find(({ id }) => id === primaryId) ?? cameras[0];
  const focused = monitor && layout === "focus" && cameras.length > 1;
  const active = cameras.filter(({ status }) => status === "analyzing").length;
  const saturated = cameras.some(({ status }) => status === "overloaded");

  return (
    <section id="laboratorio-camaras" className={styles.workspace} aria-labelledby="camera-source-title">
      <div className={styles.heading}>
        <div>
          <h2 id="camera-source-title" className={monitor ? "sr-only" : undefined}>Cámaras</h2>
          {data?.enabled && <p className="text-sm text-text-secondary">{active} de {cameras.length} con análisis activo</p>}
        </div>
        <div className={styles.actions}>
          {!monitor && <Link href="/monitoring" className="button button-outline"><LayoutGrid size={17} /> Centro de monitoreo</Link>}
          {monitor && cameras.length > 1 && (
            <div className={styles.segment} role="group" aria-label="Distribución de cámaras">
              <Button variant={layout === "grid" ? "secondary" : "ghost"} aria-pressed={layout === "grid"} onClick={() => setLayout("grid")}><LayoutGrid size={16} /> Mosaico</Button>
              <Button variant={layout === "focus" ? "secondary" : "ghost"} aria-pressed={layout === "focus"} onClick={() => setLayout("focus")}><RectangleHorizontal size={16} /> Principal</Button>
            </div>
          )}
          {monitor && canControl && (
            <Link className="button button-outline" href="/admin/camera-lab#incorporar-camara">
              <Plus size={17} aria-hidden="true" /> Incorporar cámara
            </Link>
          )}
        </div>
      </div>
      {error && <LoadError error={error} retry={retry} />}
      {!data && !error && (
        <div className={styles.grid} aria-busy="true">
          <p role="status" className="sr-only">Cargando cámaras…</p>
          {[1, 2].map((index) => (
            <div key={index} className={styles.tile} aria-hidden="true">
              <div className={styles.preview}><CameraLoadingState phase="preparing" /></div>
              <div className={styles.bar}><span className={styles.placeholder} /></div>
            </div>
          ))}
        </div>
      )}
      {monitor && data?.enabled && (saturated || cameras.filter((camera) => !camera.view_only).length > data.capacity) && (
        <p className="inline-message" role="status">
          Capacidad de análisis simultáneo configurada: {data.capacity}.
          {saturated && " Hay una cámara con inferencia saturada."}{" "}
          {canControl && <Link className="underline" href="/admin/camera-lab">Revisar cámaras activas</Link>}
        </p>
      )}
      {data && !cameras.length && (
        <div className={styles.empty}>
          <Camera size={24} aria-hidden="true" />
          <p>{data.enabled ? "Aún no hay cámaras configuradas." : "El laboratorio está deshabilitado."}</p>
          {canControl && <Link href="/admin/camera-lab" className="button button-outline">Ir a Control de cámaras</Link>}
        </div>
      )}
      {focused && (
        <label className={styles.primary}>
          Cámara principal
          <select className="select-control" value={selected?.id} onChange={(event) => setPrimaryId(event.target.value)}>
            {cameras.map((camera) => <option key={camera.id} value={camera.id}>{camera.name}</option>)}
          </select>
        </label>
      )}
      {cameras.length > 0 && (
        <ul className={styles.grid} data-focused={focused} data-count={cameras.length}>
          {cameras.map((camera) => (
            <li key={camera.id} data-primary={focused && selected?.id === camera.id}>
              <CameraTile camera={camera} canEdit={data?.can_edit === true && !error} stale={!!error}
                live={Boolean(camera.automatic ?? data?.managed)} monitor={monitor}
                enabled={running.has(camera.status)}
                handoff={monitor && camera.automatic === true && !camera.view_only && !error &&
                  cameraPlaylistHandoff(camera.status, camera.playback?.transition, receivedAt)}
                preview={!monitor && !cameraObservationPaused(camera.status, !!error) &&
                  cameraFrameIsRecent(camera.last_frame_at, camera.metrics, receivedAt)} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
