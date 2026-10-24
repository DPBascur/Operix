"use client";
/* eslint-disable @next/next/no-img-element -- MJPEG multipart necesita img nativo. */

import {
  ChevronDown,
  Info,
  MoreHorizontal,
  Pause,
  Play,
  RotateCcw,
  Square,
  Trash2,
  Upload,
  Waypoints,
} from "lucide-react";
import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import {
  analysisService,
  AnalysisRequestError,
  type AnalysisProfile,
  type AnalysisProfileDefinition,
  type AnalysisSessionStatus,
  type DemoVideoSource,
  type NormalizedVertex,
} from "@/services/analysis.service";
import { pointInFrame } from "./zone-editor-geometry";

const labels = {
  ready: "Video listo para analizar.",
  preparing: "Preparando modelos y video…",
  processing: "Procesando video…",
  completed: "Análisis completado.",
  error: "Error de análisis.",
  cancelled: "Análisis detenido.",
} as const;

function validPolygon(vertices: NormalizedVertex[]): boolean {
  if (vertices.length < 3) return false;
  const cross = (
    a: NormalizedVertex,
    b: NormalizedVertex,
    c: NormalizedVertex,
  ) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const area = vertices.reduce((sum, p, i) => {
    const q = vertices[(i + 1) % vertices.length];
    return sum + p[0] * q[1] - q[0] * p[1];
  }, 0);
  if (Math.abs(area) < 1e-8) return false;
  for (let i = 0; i < vertices.length; i++) {
    const a = vertices[i];
    const b = vertices[(i + 1) % vertices.length];
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-8) return false;
    for (let j = i + 1; j < vertices.length; j++) {
      if (j === i + 1 || (i === 0 && j === vertices.length - 1)) continue;
      const c = vertices[j];
      const d = vertices[(j + 1) % vertices.length];
      if (
        cross(a, b, c) * cross(a, b, d) < 0 &&
        cross(c, d, a) * cross(c, d, b) < 0
      )
        return false;
    }
  }
  return true;
}

function readableError(message: string): string {
  if (/timeout|timed out|aborted/i.test(message)) {
    return "El servicio tardó demasiado en responder. Revise la conexión y vuelva a intentarlo.";
  }
  if (/failed to fetch|networkerror|load failed/i.test(message)) {
    return "No se pudo conectar con el servicio de análisis.";
  }
  return message;
}

export function AnalysisWorkspace({
  initialProfile = "A",
  initialManual = false,
}: {
  initialProfile?: AnalysisProfile;
  initialManual?: boolean;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const [profile, setProfile] = useState<AnalysisProfile>(initialProfile);
  const [profiles, setProfiles] = useState<AnalysisProfileDefinition[]>([]);
  const [demoSource, setDemoSource] = useState<DemoVideoSource | null>(null);
  const [session, setSession] = useState<AnalysisSessionStatus | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [videoInfo, setVideoInfo] = useState({
    width: 1920,
    height: 1080,
    duration: 0,
  });
  const [editing, setEditing] = useState(false);
  const [suspendResult, setSuspendResult] = useState(false);
  const [draft, setDraft] = useState<NormalizedVertex[]>([]);
  const [closed, setClosed] = useState(true);
  const [selectedVertex, setSelectedVertex] = useState<number | null>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const dragging = useRef<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const localUrlRef = useRef<string | null>(null);
  const generation = useRef(0);
  const ownedSessionId = useRef<string | null>(null);
  const pollFailed = useRef(false);
  const initialProfileRef = useRef(initialProfile);
  const initialManualRef = useRef(initialManual);

  useEffect(() => {
    return () => {
      generation.current += 1;
      if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
      if (ownedSessionId.current) {
        void analysisService
          .closeAnalysisSession(ownedSessionId.current)
          .catch(() => {
            // La retención del Backend libera la sesión si la red ya no está disponible.
          });
      }
    };
  }, []);

  useEffect(() => {
    ownedSessionId.current = session?.id ?? null;
  }, [session?.id]);

  useEffect(() => {
    let active = true;
    const current = generation.current;
    analysisService
      .getProfiles()
      .then(async (catalog) => {
        if (!active) return;
        setProfiles(catalog);
        if (initialManualRef.current) return;
        const initial = catalog.find(
          (item) => item.id === initialProfileRef.current,
        );
        if (!initial?.default_demo_video) return;
        setBusy(true);
        const created = await analysisService.createDemoSession(
          initialProfileRef.current,
          initial.default_demo_video.id,
        );
        if (!active || generation.current !== current) {
          await analysisService.closeAnalysisSession(created.id);
          return;
        }
        setDemoSource(initial.default_demo_video);
        setSession(created);
        setDraft(created.zone.polygon);
        setClosed(true);
      })
      .catch((cause: unknown) => {
        if (active) {
          setError(
            cause instanceof Error
              ? cause.message
              : "No se pudieron cargar los perfiles.",
          );
        }
      })
      .finally(() => {
        if (active) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const id = session?.id;
    const state = session?.state;
    if (!id || !state) return;
    const current = generation.current;
    const active =
      state === "preparing" ||
      state === "processing" ||
      session?.preview?.pending;
    let listening = true;
    let timer: number;
    const poll = () => {
      let failed = false;
      analysisService
        .getAnalysisStatus(id)
        .then((updated) => {
          if (listening && generation.current === current) {
            setSession(updated);
            if (pollFailed.current) setError(null);
            pollFailed.current = false;
          }
        })
        .catch((cause: unknown) => {
          failed = true;
          if (listening && generation.current === current) {
            pollFailed.current = true;
            if (cause instanceof AnalysisRequestError && cause.status === 404) {
              setSession(null);
              setEditing(false);
              setError(
                "La sesión ya no está disponible. Seleccione de nuevo el perfil o cargue un video.",
              );
              return;
            }
            setError(
              cause instanceof Error
                ? cause.message
                : "No se pudo consultar el estado.",
            );
          }
        })
        .finally(() => {
          if (listening)
            timer = window.setTimeout(
              poll,
              failed ? 5000 : active ? 200 : 20_000,
            );
        });
    };
    timer = window.setTimeout(poll, active ? 200 : 20_000);
    return () => {
      listening = false;
      window.clearTimeout(timer);
    };
  }, [session?.id, session?.state, session?.preview?.pending]);

  async function selectVideo(selected: File | undefined) {
    if (!selected) return;
    const current = ++generation.current;
    let selectedLocally = false;
    setBusy(true);
    setError(null);
    try {
      if (session?.state === "completed") {
        setSuspendResult(true);
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => resolve()),
        );
      }
      if (session) await analysisService.closeAnalysisSession(session.id);
      if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
      const url = URL.createObjectURL(selected);
      localUrlRef.current = url;
      setLocalUrl(url);
      setFile(selected);
      setDemoSource(null);
      setSession(null);
      selectedLocally = true;
      setEditing(false);
      const created = await analysisService.createSession(selected, profile);
      if (generation.current !== current) {
        await analysisService.closeAnalysisSession(created.id);
        return;
      }
      setSession(created);
      setDraft(created.zone.polygon);
      setClosed(true);
    } catch (cause) {
      if (generation.current === current) {
        if (selectedLocally) {
          if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
          localUrlRef.current = null;
          setLocalUrl(null);
          setFile(null);
          setSession(null);
        }
        setError(
          cause instanceof Error
            ? cause.message
            : "No se pudo crear la sesión.",
        );
      }
    } finally {
      if (generation.current === current) {
        setSuspendResult(false);
        setBusy(false);
      }
    }
  }

  async function selectProfileDemo(next: AnalysisProfile) {
    const definition = profiles.find((item) => item.id === next);
    const demo = definition?.default_demo_video;
    if (!demo) {
      throw new Error("Este perfil no tiene un video demo disponible.");
    }
    const current = ++generation.current;
    if (session?.state === "completed") {
      setSuspendResult(true);
      await new Promise<void>((resolve) =>
        requestAnimationFrame(() => resolve()),
      );
    }
    if (session) await analysisService.closeAnalysisSession(session.id);
    if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
    localUrlRef.current = null;
    setLocalUrl(null);
    setFile(null);
    setSession(null);
    const created = await analysisService.createDemoSession(next, demo.id);
    if (generation.current !== current) {
      await analysisService.closeAnalysisSession(created.id);
      return;
    }
    setDemoSource(demo);
    setSession(created);
    setDraft(created.zone.polygon);
    setClosed(true);
    setEditing(false);
  }

  async function start() {
    if (!session) return;
    videoRef.current?.pause();
    if (videoRef.current) videoRef.current.currentTime = 0;
    generation.current += 1;
    setBusy(true);
    setError(null);
    try {
      if (session.state === "completed") {
        setSuspendResult(true);
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => resolve()),
        );
      }
      setSession(await analysisService.startAnalysisSession(session.id));
      setEditing(false);
    } catch (cause) {
      try {
        setSession(await analysisService.getAnalysisStatus(session.id));
      } catch {
        // El error original es más útil; la sesión puede haberse cerrado.
      }
      setError(cause instanceof Error ? cause.message : "No se pudo iniciar.");
    } finally {
      setSuspendResult(false);
      setBusy(false);
    }
  }

  async function stop() {
    if (!session) return;
    generation.current += 1;
    setBusy(true);
    try {
      setSession(await analysisService.stopAnalysisSession(session.id));
    } catch (cause) {
      try {
        setSession(await analysisService.getAnalysisStatus(session.id));
      } catch {
        // El error original es más útil; la sesión puede haberse cerrado.
      }
      setError(cause instanceof Error ? cause.message : "No se pudo detener.");
    } finally {
      setBusy(false);
    }
  }

  async function applyZone() {
    if (!session || !closed || !validPolygon(draft)) {
      setError("Cierre un polígono simple con al menos tres vértices.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      generation.current += 1;
      setSession(
        await analysisService.updateZone(session.id, { polygon: draft }),
      );
      setEditing(false);
    } catch (cause) {
      setError(
        cause instanceof Error ? cause.message : "No se pudo aplicar la zona.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function changeProfile(next: AnalysisProfile) {
    setBusy(true);
    setError(null);
    try {
      setProfile(next);
      if (session?.source_kind === "manual") {
        generation.current += 1;
        const updated = await analysisService.updateZone(session.id, {
          profile: next,
        });
        setSession(updated);
        setDraft(updated.zone.polygon);
        setClosed(true);
        setEditing(false);
      } else {
        const nextDemo = profiles.find(
          (item) => item.id === next,
        )?.default_demo_video;
        if (nextDemo) {
          await selectProfileDemo(next);
        } else {
          generation.current += 1;
          if (session) await analysisService.closeAnalysisSession(session.id);
          setSession(null);
          setDemoSource(null);
          setDraft([]);
          setEditing(false);
        }
      }
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo cambiar el perfil.",
      );
    } finally {
      setBusy(false);
    }
  }

  async function clearSession() {
    if (!session) return;
    generation.current += 1;
    setBusy(true);
    setError(null);
    try {
      if (session.state === "completed") {
        setSuspendResult(true);
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => resolve()),
        );
      }
      const restoreDemo = session.source_kind === "demo";
      await analysisService.closeAnalysisSession(session.id);
      if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
      localUrlRef.current = null;
      setLocalUrl(null);
      setFile(null);
      setDemoSource(null);
      setSession(null);
      setEditing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
      if (restoreDemo) await selectProfileDemo(profile);
    } catch (cause) {
      setError(
        cause instanceof Error
          ? cause.message
          : "No se pudo limpiar la sesión.",
      );
    } finally {
      setSuspendResult(false);
      setBusy(false);
    }
  }

  const state = session?.state;
  const sourceName = file?.name ?? demoSource?.filename ?? null;
  const sourceBytes = file?.size ?? demoSource?.bytes ?? null;
  const sourceKind = file ? "manual" : demoSource ? "demo" : null;
  const referenceUrl =
    localUrl ??
    (session?.source_kind === "demo"
      ? analysisService.getAnalysisSourceUrl(session.id)
      : null);
  const selectedProfile = profiles.find((item) => item.id === profile);
  const previewPending = session?.preview?.pending === true;
  const canEdit =
    !!session &&
    ["ready", "completed", "cancelled", "error"].includes(session.state) &&
    !busy &&
    !previewPending;
  const showStream =
    !!session &&
    (["preparing", "processing"].includes(session.state) || previewPending);
  const showResult =
    !!session &&
    session.state === "completed" &&
    !!session.result &&
    !previewPending &&
    !editing &&
    !suspendResult;
  const showReference = !!sourceName && !!referenceUrl && !showResult;
  const visibleError = error
    ? readableError(error)
    : session?.persistence?.state === "failed"
      ? "El análisis puede estar completo, pero sus eventos no quedaron guardados íntegramente. Puede reintentar el guardado sin analizar de nuevo."
      : session?.detail
        ? readableError(session.detail)
        : null;
  const contextState =
    session?.state === "completed" && session.persistence?.state === "failed"
      ? "Análisis completado · eventos pendientes de guardado"
      : visibleError
        ? "No fue posible completar la operación"
        : session
          ? session.state === "completed" && previewPending
            ? "Análisis completado · terminando vista previa a velocidad 1×…"
            : labels[session.state]
          : "Sin fuente preparada";

  function moveVertexWithKeyboard(
    event: KeyboardEvent<SVGEllipseElement>,
    index: number,
  ) {
    const step = event.shiftKey ? 0.01 : 0.005;
    const movement: Partial<Record<string, NormalizedVertex>> = {
      ArrowLeft: [-step, 0],
      ArrowRight: [step, 0],
      ArrowUp: [0, -step],
      ArrowDown: [0, step],
    };
    const delta = movement[event.key];
    if (!delta) return;
    event.preventDefault();
    setSelectedVertex(index);
    setDraft((current) =>
      current.map((point, currentIndex) =>
        currentIndex === index
          ? [
              Math.max(0, Math.min(1, point[0] + delta[0])),
              Math.max(0, Math.min(1, point[1] + delta[1])),
            ]
          : point,
      ),
    );
  }

  const ZoneOutline = closed ? "polygon" : "polyline";

  return (
    <div className="analysis-workspace">
      <section
        className="analysis-contextbar"
        aria-label="Contexto del análisis"
      >
        <div className="min-w-0">
          <p className={`analysis-state ${visibleError ? "is-error" : ""}`}>
            {contextState}
          </p>
          <p className="mt-1 truncate text-xs text-text-secondary">
            {sourceName
              ? `${sourceName} · ${sourceKind === "demo" ? "demo incluida" : "video manual"}`
              : "Seleccione una demo o un video local para comenzar."}
          </p>
        </div>
        <div className="analysis-context-actions">
          <div className="analysis-profiles" aria-label="Perfil de zona">
            {(["A", "B", "C"] as AnalysisProfile[]).map((item) => {
              const profileName =
                profiles.find((candidate) => candidate.id === item)
                  ?.display_name ??
                (item === "A"
                  ? "Warehouse fire"
                  : item === "B"
                    ? "Nearmiss"
                    : "Box pickup");

              return (
                <button
                  key={item}
                  type="button"
                  className={`analysis-profile ${profile === item ? "is-active" : ""}`}
                  aria-pressed={profile === item}
                  disabled={busy || (!!session && !canEdit)}
                  onClick={() => void changeProfile(item)}
                >
                  <span className="block">Perfil {item}</span>
                  <span className="analysis-profile-name">{profileName}</span>
                </button>
              );
            })}
          </div>
          <label className="analysis-context-button">
            <Upload size={16} aria-hidden="true" /> Cambiar fuente
            <input
              type="file"
              accept=".mp4,.mov,.avi,video/mp4"
              className="sr-only"
              onChange={(event) => {
                void selectVideo(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          <button
            type="button"
            className="analysis-context-button"
            aria-expanded={inspectorOpen}
            onClick={() => setInspectorOpen((current) => !current)}
          >
            <Info size={16} aria-hidden="true" /> Detalles
          </button>
        </div>
      </section>

      <div className="analysis-layout">
        <section aria-label="Video de análisis" className="analysis-view">
          <div
            className={`analysis-media-frame ${sourceName && videoInfo.height > videoInfo.width ? "is-portrait" : ""}`}
            style={
              {
                "--analysis-source-ratio": videoInfo.width / videoInfo.height,
              } as React.CSSProperties
            }
          >
            <div className="analysis-media-stage">
              <div
                className={`analysis-stage ${sourceName ? "has-source" : "is-empty"}`}
                style={{
                  aspectRatio: `${videoInfo.width} / ${videoInfo.height}`,
                }}
              >
                {!sourceName && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center text-white/80">
                    <Upload size={30} aria-hidden="true" />
                    <p className="text-lg font-semibold">Sin fuente de video</p>
                    <p className="max-w-sm text-sm opacity-75">
                      Seleccione un archivo o use una demo.
                    </p>
                  </div>
                )}
                {showReference && referenceUrl && (
                  <video
                    ref={videoRef}
                    src={referenceUrl}
                    controls={!editing && !showStream}
                    preload="metadata"
                    className="absolute inset-0 h-full w-full object-contain"
                    onLoadedMetadata={(event) => {
                      const video = event.currentTarget;
                      setVideoInfo({
                        width: video.videoWidth,
                        height: video.videoHeight,
                        duration: video.duration,
                      });
                    }}
                  />
                )}
                {showStream && (
                  <img
                    key={`${session.id}-${session.run}`}
                    src={analysisService.getAnalysisStreamUrl(session.id)}
                    alt="Video procesado: personas, montacargas, IDs y zona"
                    className="absolute inset-0 h-full w-full object-contain"
                  />
                )}
                {showResult && (
                  <video
                    key={`${session.id}-${session.run}-result`}
                    src={analysisService.getAnalysisResultUrl(
                      session.id,
                      session.run,
                    )}
                    controls
                    preload="metadata"
                    aria-label="Resultado anotado de Operix"
                    className="absolute inset-0 h-full w-full object-contain"
                  />
                )}
                {showReference && !showStream && session && (
                  <svg
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    className={`absolute inset-0 h-full w-full ${editing ? "touch-none cursor-crosshair" : "pointer-events-none"}`}
                    aria-label={
                      editing
                        ? "Editor de polígono normalizado"
                        : "Zona de referencia"
                    }
                    onPointerDown={(event) => {
                      if (
                        !editing ||
                        closed ||
                        event.target !== event.currentTarget
                      )
                        return;
                      const point = pointInFrame(event);
                      if (point) setDraft((current) => [...current, point]);
                    }}
                    onPointerMove={(event) => {
                      const draggedVertex = dragging.current;
                      if (draggedVertex === null) return;
                      const point = pointInFrame(event);
                      if (!point) return;
                      setDraft((current) =>
                        current.map((value, index) =>
                          index === draggedVertex ? point : value,
                        ),
                      );
                    }}
                    onPointerUp={() => {
                      dragging.current = null;
                    }}
                    onPointerCancel={() => {
                      dragging.current = null;
                    }}
                  >
                    {draft.length > 1 && (
                      <ZoneOutline
                        points={draft
                          .map(([x, y]) => `${x * 100},${y * 100}`)
                          .join(" ")}
                        fill={closed ? "rgba(47,209,200,0.08)" : "none"}
                        stroke="#2fd1c8"
                        strokeWidth="2"
                        vectorEffect="non-scaling-stroke"
                        pointerEvents="none"
                      />
                    )}
                    {editing &&
                      draft.map(([x, y], index) => (
                        <ellipse
                          key={index}
                          cx={x * 100}
                          cy={y * 100}
                          rx={selectedVertex === index ? 1.1 : 0.8}
                          ry={
                            ((selectedVertex === index ? 1.1 : 0.8) *
                              videoInfo.width) /
                            videoInfo.height
                          }
                          fill={selectedVertex === index ? "#2fd1c8" : "#fff"}
                          stroke="#087c79"
                          strokeWidth="2"
                          vectorEffect="non-scaling-stroke"
                          tabIndex={0}
                          role="button"
                          aria-label={`Vértice ${index + 1}, x ${(x * 100).toFixed(1)} %, y ${(y * 100).toFixed(1)} %. Use las flechas para moverlo; mantenga Mayús para un desplazamiento mayor.`}
                          onFocus={() => setSelectedVertex(index)}
                          onKeyDown={(event) =>
                            moveVertexWithKeyboard(event, index)
                          }
                          onPointerDown={(event) => {
                            event.stopPropagation();
                            if (!closed && index === 0 && draft.length >= 3) {
                              setClosed(true);
                              return;
                            }
                            dragging.current = index;
                            setSelectedVertex(index);
                            event.currentTarget.setPointerCapture(
                              event.pointerId,
                            );
                          }}
                        />
                      ))}
                  </svg>
                )}
              </div>
            </div>

            <div className="analysis-toolbar">
              {session &&
                (["preparing", "processing"].includes(session.state) ||
                  previewPending) && (
                  <div className="analysis-toolbar-status" role="status">
                    <strong>
                      {session.state === "completed"
                        ? "Analizado"
                        : "Procesando"}{" "}
                      ·{" "}
                      {session.percent == null
                        ? "—"
                        : `${session.percent.toFixed(1)} %`}
                    </strong>
                    <span>
                      {session.person_detections} personas ·{" "}
                      {session.forklift_detections} montacargas ·{" "}
                      {session.fps == null ? "—" : session.fps.toFixed(2)} FPS
                    </span>
                  </div>
                )}
              <label
                className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control px-4 text-sm font-semibold ${session ? "border border-border-strong bg-transparent text-foreground" : "bg-primary text-primary-foreground"}`}
              >
                <Upload size={17} aria-hidden="true" />{" "}
                {session ? "Nuevo video" : "Seleccionar video"}
                <input
                  ref={fileInputRef}
                  type="file"
                  disabled={busy}
                  accept=".mp4,.mov,.avi,video/mp4"
                  className="sr-only"
                  onChange={(event) => {
                    void selectVideo(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
              </label>
              {sourceKind === "manual" &&
                selectedProfile?.default_demo_video && (
                  <Button
                    variant="secondary"
                    disabled={busy || !canEdit}
                    onClick={() => {
                      setBusy(true);
                      setError(null);
                      selectProfileDemo(profile)
                        .catch((cause: unknown) =>
                          setError(
                            cause instanceof Error
                              ? cause.message
                              : "No se pudo restaurar la demo.",
                          ),
                        )
                        .finally(() => {
                          setSuspendResult(false);
                          setBusy(false);
                        });
                    }}
                  >
                    Usar video demo
                  </Button>
                )}
              {canEdit && !editing && (
                <Button
                  className="order-first"
                  onClick={() => void start()}
                  variant="primary"
                >
                  {state === "ready" ? (
                    <Play size={16} aria-hidden="true" />
                  ) : (
                    <RotateCcw size={16} aria-hidden="true" />
                  )}
                  {state === "ready"
                    ? "Iniciar análisis"
                    : state === "error"
                      ? "Volver a intentar"
                      : "Volver a analizar"}
                </Button>
              )}
              {session &&
                ["preparing", "processing"].includes(session.state) && (
                  <Button
                    onClick={() => void stop()}
                    disabled={busy}
                    variant="destructive"
                  >
                    <Square size={16} aria-hidden="true" /> Detener
                  </Button>
                )}
              {canEdit && !editing && (
                <Button
                  onClick={() => {
                    videoRef.current?.pause();
                    setEditing(true);
                  }}
                  variant="outline"
                >
                  <Waypoints size={16} aria-hidden="true" /> Editar zona
                </Button>
              )}
              {session && canEdit && (
                <details className="analysis-more">
                  <summary aria-label="Más opciones">
                    <MoreHorizontal size={18} aria-hidden="true" />
                  </summary>
                  <div>
                    <button
                      type="button"
                      onClick={() => fileInputRef.current?.click()}
                    >
                      <Upload size={15} aria-hidden="true" /> Nuevo video
                    </button>
                    <button type="button" onClick={() => void clearSession()}>
                      <Trash2 size={15} aria-hidden="true" /> Limpiar sesión
                    </button>
                  </div>
                </details>
              )}
            </div>
            {editing && (
              <div className="analysis-zone-toolbar">
                <Button
                  variant="secondary"
                  onClick={() => videoRef.current?.pause()}
                >
                  <Pause size={15} /> Pausar frame
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setDraft([]);
                    setClosed(false);
                    setSelectedVertex(null);
                  }}
                >
                  Nueva zona
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => setClosed(true)}
                  disabled={closed || draft.length < 3}
                >
                  Cerrar polígono
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setDraft((points) =>
                      points.filter((_, index) => index !== selectedVertex),
                    );
                    setSelectedVertex(null);
                  }}
                  disabled={selectedVertex === null || draft.length <= 3}
                >
                  Eliminar vértice
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    setDraft(session?.zone.polygon ?? []);
                    setEditing(false);
                  }}
                >
                  Cancelar
                </Button>
                <Button
                  variant="primary"
                  onClick={() => {
                    void applyZone();
                  }}
                  disabled={!closed || !validPolygon(draft) || busy}
                >
                  Aplicar zona
                </Button>
                <span className="text-text-secondary">
                  {draft.length} vértices ·{" "}
                  {closed
                    ? "arrastre o use flechas con foco"
                    : "marque puntos y pulse el primero para cerrar"}
                </span>
              </div>
            )}
          </div>
          <p
            role={visibleError ? "alert" : "status"}
            className={`analysis-feedback ${visibleError ? "has-error" : ""}`}
          >
            {busy && !showStream
              ? "Preparando sesión…"
              : session
                ? labels[session.state]
                : sourceName
                  ? "Video listo para preparar."
                  : "No hay un análisis en curso."}
            {visibleError && (
              <span className="analysis-error-message">{visibleError}</span>
            )}
          </p>
          {session &&
            ["completed", "error", "cancelled"].includes(session.state) &&
            session.persistence && (
              <div className="analysis-result-help" aria-live="polite">
                {session.persistence.state === "saved" ? (
                  <p>
                    {session.persistence.saved ?? 0} eventos guardados.{" "}
                    <Link
                      href="/events"
                      className="underline underline-offset-2"
                    >
                      Consultar histórico
                    </Link>
                  </p>
                ) : null}
                {session.persistence.state === "disabled" ? (
                  <p>
                    La publicación de eventos está deshabilitada en este
                    entorno.
                  </p>
                ) : null}
                {session.persistence.state === "failed" ? (
                  <Button
                    type="button"
                    variant="outline"
                    disabled={busy}
                    onClick={() => {
                      setBusy(true);
                      void analysisService
                        .retryEventPersistence(session.id)
                        .then(setSession)
                        .catch((cause: unknown) =>
                          setError(
                            cause instanceof Error
                              ? readableError(cause.message)
                              : "No se pudo reintentar el guardado.",
                          ),
                        )
                        .finally(() => setBusy(false));
                    }}
                  >
                    Reintentar guardado de eventos
                  </Button>
                ) : null}
              </div>
            )}
          {session?.pending_changes && (
            <p className="rounded-control border border-warning/50 bg-warning/10 px-3 py-2 text-sm text-foreground">
              Hay cambios de zona pendientes. Vuelva a analizar para aplicarlos
              al resultado.
            </p>
          )}
          {showResult && (
            <p className="analysis-result-help">
              Resultado reproducible: use los controles del video para pausar,
              buscar posición o volver al inicio.
            </p>
          )}
          {session && (
            <section
              className="analysis-summary"
              aria-label="Resumen de percepción"
            >
              <div>
                <span>Personas</span>
                <strong>
                  {session.run > 0 ? session.person_detections : "—"}
                </strong>
              </div>
              <div>
                <span>Montacargas</span>
                <strong>
                  {session.run > 0 ? session.forklift_detections : "—"}
                </strong>
              </div>
              <div>
                <span>FPS Motor</span>
                <strong>
                  {session.fps == null ? "—" : session.fps.toFixed(2)}
                </strong>
              </div>
              <div>
                <span>Progreso</span>
                <strong>
                  {session.percent == null
                    ? "—"
                    : `${session.percent.toFixed(1)} %`}
                </strong>
              </div>
            </section>
          )}
        </section>

        <aside
          aria-label="Estado del análisis"
          className={`analysis-inspector ${inspectorOpen ? "is-open" : ""}`}
        >
          <div className="analysis-inspector-head">
            <div>
              <span className="eyebrow">Inspector</span>
              <h2>Detalles del análisis</h2>
            </div>
            <button
              type="button"
              onClick={() => setInspectorOpen(false)}
              aria-label="Cerrar detalles"
            >
              <ChevronDown size={18} aria-hidden="true" />
            </button>
          </div>
          <div className="analysis-group">
            <p className="section-heading">Sesión</p>
            <dl className="analysis-data mt-3">
              <dt>Estado</dt>
              <dd>
                {session
                  ? labels[session.state].replace(".", "")
                  : sourceName
                    ? "Video listo"
                    : "Vacío"}
              </dd>
              <dt>Fuente</dt>
              <dd>
                {sourceKind === "demo"
                  ? "Demo incluida"
                  : sourceKind === "manual"
                    ? "Video manual"
                    : "—"}
              </dd>
              {sourceName && (
                <>
                  <dt>Video</dt>
                  <dd title={sourceName}>{sourceName}</dd>
                </>
              )}
              <dt>Perfil</dt>
              <dd>{profile}</dd>
            </dl>
          </div>

          {session && session.run > 0 && (
            <div className="analysis-group">
              <div className="flex items-center justify-between gap-3">
                <p className="section-heading">Progreso</p>
                <span className="text-xs font-semibold tabular-nums">
                  {session?.percent == null
                    ? "—"
                    : `${session.percent.toFixed(1)} %`}
                </span>
              </div>
              <div className="analysis-progress mt-3" aria-hidden="true">
                <span style={{ width: `${session?.percent ?? 0}%` }} />
              </div>
              <dl className="analysis-data mt-3">
                <dt>Frame</dt>
                <dd>
                  {session ? `${session.frame} / ${session.total ?? "—"}` : "—"}
                </dd>
                <dt>Motor</dt>
                <dd>
                  {session?.fps == null ? "—" : `${session.fps.toFixed(2)} FPS`}
                </dd>
                <dt>Fuente</dt>
                <dd>
                  {session?.result
                    ? `${session.result.video.fps.toFixed(2)} FPS`
                    : "—"}
                </dd>
              </dl>
            </div>
          )}

          {session && session.run > 0 && (
            <div className="analysis-group">
              <p className="section-heading">Percepción</p>
              <div className="mt-3 grid grid-cols-2 gap-px bg-border">
                <div className="bg-surface py-3 pr-3">
                  <span className="block text-2xl font-semibold tabular-nums">
                    {session && session.run > 0
                      ? session.person_detections
                      : "—"}
                  </span>
                  <span className="text-xs text-text-secondary">PERSON</span>
                </div>
                <div className="bg-surface py-3 pl-3">
                  <span className="block text-2xl font-semibold tabular-nums">
                    {session && session.run > 0
                      ? session.forklift_detections
                      : "—"}
                  </span>
                  <span className="text-xs text-text-secondary">FORKLIFT</span>
                </div>
              </div>
            </div>
          )}

          {session && (
            <div className="analysis-group">
              <p className="section-heading">Contexto</p>
              <dl className="analysis-data mt-3">
                <dt>Zona</dt>
                <dd>
                  {showResult
                    ? (session.result?.zone.name ?? "—")
                    : (session?.zone.name ?? "—")}
                </dd>
                <dt>Regla</dt>
                <dd>{session ? "zone_dwell · solo person" : "—"}</dd>
                <dt>Resolución</dt>
                <dd>
                  {sourceName
                    ? `${videoInfo.width} × ${videoInfo.height}`
                    : "—"}
                </dd>
                <dt>Duración</dt>
                <dd>
                  {sourceName && videoInfo.duration
                    ? `${videoInfo.duration.toFixed(1)} s`
                    : "—"}
                </dd>
                <dt>Tamaño</dt>
                <dd>
                  {sourceBytes
                    ? `${(sourceBytes / 1048576).toFixed(1)} MiB`
                    : "—"}
                </dd>
              </dl>
            </div>
          )}
          {!session && (
            <p className="analysis-inspector-note">
              La configuración y la evidencia aparecerán al preparar una fuente.
            </p>
          )}
        </aside>
      </div>
    </div>
  );
}
