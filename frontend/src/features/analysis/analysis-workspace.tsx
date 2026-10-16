"use client";
/* eslint-disable @next/next/no-img-element -- MJPEG multipart necesita img nativo. */

import {
  Pause,
  Play,
  RotateCcw,
  Square,
  Trash2,
  Upload,
  Waypoints,
} from "lucide-react";
import { useEffect, useRef, useState, type PointerEvent } from "react";
import { Button } from "@/components/ui/button";
import {
  analysisService,
  type AnalysisProfile,
  type AnalysisProfileDefinition,
  type AnalysisSessionStatus,
  type DemoVideoSource,
  type NormalizedVertex,
} from "@/services/analysis.service";

const labels = {
  ready: "Video listo para analizar.",
  preparing: "Preparando modelos y video…",
  processing: "Procesando video…",
  completed: "Análisis completado.",
  error: "Error de análisis.",
  cancelled: "Análisis detenido.",
} as const;

function pointInFrame(event: PointerEvent<SVGSVGElement>): NormalizedVertex {
  const bounds = event.currentTarget.getBoundingClientRect();
  return [
    Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
    Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
  ];
}

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

export function AnalysisWorkspace() {
  const [file, setFile] = useState<File | null>(null);
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const [profile, setProfile] = useState<AnalysisProfile>("A");
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
  const dragging = useRef<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const localUrlRef = useRef<string | null>(null);
  const generation = useRef(0);

  useEffect(() => {
    return () => {
      if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
    };
  }, []);

  useEffect(() => {
    let active = true;
    let createdId: string | null = null;
    analysisService
      .getProfiles()
      .then(async (catalog) => {
        if (!active) return;
        setProfiles(catalog);
        const initial = catalog.find((item) => item.id === "A");
        if (!initial?.default_demo_video) return;
        setBusy(true);
        const created = await analysisService.createDemoSession(
          "A",
          initial.default_demo_video.id,
        );
        createdId = created.id;
        if (!active) {
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
      if (createdId) void analysisService.closeAnalysisSession(createdId);
    };
  }, []);

  useEffect(() => {
    const id = session?.id;
    const state = session?.state;
    if (!id || !state) return;
    const current = generation.current;
    const active = state === "preparing" || state === "processing";
    const timer = window.setInterval(
      () => {
        analysisService
          .getAnalysisStatus(id)
          .then((updated) => {
            if (generation.current === current) setSession(updated);
          })
          .catch((cause: unknown) => {
            if (generation.current === current) {
              setError(
                cause instanceof Error
                  ? cause.message
                  : "No se pudo consultar el estado.",
              );
            }
          });
      },
      active ? 450 : 20_000,
    );
    return () => window.clearInterval(timer);
  }, [session?.id, session?.state]);

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
  const canEdit =
    !!session &&
    ["ready", "completed", "cancelled", "error"].includes(session.state) &&
    !busy;
  const showStream =
    !!session && ["preparing", "processing"].includes(session.state);
  const showResult =
    !!session &&
    session.state === "completed" &&
    !!session.result &&
    !editing &&
    !suspendResult;
  const showReference =
    !!sourceName && !!referenceUrl && !showStream && !showResult;
  return (
    <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <section aria-label="Video de análisis" className="min-w-0 space-y-4">
        <div
          className="relative overflow-hidden rounded-panel border border-analysis-border bg-analysis-background"
          style={{ aspectRatio: `${videoInfo.width} / ${videoInfo.height}` }}
        >
          {!sourceName && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center text-brand-neutral">
              <Upload size={30} aria-hidden="true" />
              <p className="text-lg font-semibold">
                No hay un análisis en curso.
              </p>
              <p className="max-w-sm text-sm opacity-75">
                Seleccione un video o configure una demo para revisar su zona.
              </p>
            </div>
          )}
          {showReference && referenceUrl && (
            <video
              ref={videoRef}
              src={referenceUrl}
              controls={!editing}
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
          {showReference && session && (
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
                if (!editing || closed || event.target !== event.currentTarget)
                  return;
                setDraft((current) => [...current, pointInFrame(event)]);
              }}
              onPointerMove={(event) => {
                if (dragging.current === null) return;
                const point = pointInFrame(event);
                setDraft((current) =>
                  current.map((value, index) =>
                    index === dragging.current ? point : value,
                  ),
                );
              }}
              onPointerUp={() => {
                dragging.current = null;
              }}
            >
              {draft.length > 1 && (
                <polygon
                  points={draft
                    .map(([x, y]) => `${x * 100},${y * 100}`)
                    .join(" ")}
                  fill={closed ? "rgba(47,209,200,0.08)" : "none"}
                  stroke="#2fd1c8"
                  strokeWidth="0.25"
                  vectorEffect="non-scaling-stroke"
                  pointerEvents="none"
                />
              )}
              {editing &&
                draft.map(([x, y], index) => (
                  <circle
                    key={index}
                    cx={x * 100}
                    cy={y * 100}
                    r={selectedVertex === index ? 1.1 : 0.8}
                    fill="#fff"
                    stroke="#087c79"
                    strokeWidth="0.25"
                    onPointerDown={(event) => {
                      event.stopPropagation();
                      dragging.current = index;
                      setSelectedVertex(index);
                      event.currentTarget.setPointerCapture(event.pointerId);
                    }}
                  />
                ))}
            </svg>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <label className="inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-control bg-primary px-4 text-sm font-semibold text-primary-foreground">
            <Upload size={17} aria-hidden="true" />{" "}
            {session ? "Nuevo video" : "Seleccionar video"}
            <input
              ref={fileInputRef}
              type="file"
              accept=".mp4,.mov,.avi,video/mp4"
              className="sr-only"
              onChange={(event) => {
                void selectVideo(event.target.files?.[0]);
                event.target.value = "";
              }}
            />
          </label>
          {sourceKind === "manual" && selectedProfile?.default_demo_video && (
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
            <Button onClick={() => void start()} variant="primary">
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
          {session && ["preparing", "processing"].includes(session.state) && (
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
              variant="secondary"
            >
              <Waypoints size={16} aria-hidden="true" /> Editar zona
            </Button>
          )}
          {session && canEdit && (
            <Button onClick={() => void clearSession()} variant="secondary">
              <Trash2 size={16} aria-hidden="true" /> Limpiar sesión
            </Button>
          )}
        </div>
        {editing && (
          <div className="flex flex-wrap items-center gap-2 rounded-card border border-border bg-surface p-3 text-sm">
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
              {draft.length} vértices · coordenadas normalizadas
            </span>
          </div>
        )}
        <p role="status" className="text-sm text-text-secondary">
          {busy && !showStream
            ? "Preparando sesión…"
            : session
              ? labels[session.state]
              : sourceName
                ? "Video listo para preparar."
                : "No hay un análisis en curso."}
          {error && <span className="ml-2 text-danger">{error}</span>}
          {session?.detail && (
            <span className="ml-2 text-danger">{session.detail}</span>
          )}
        </p>
        {session?.pending_changes && (
          <p className="rounded-control border border-warning/50 bg-warning/10 px-3 py-2 text-sm text-foreground">
            Hay cambios de zona pendientes. Vuelva a analizar para aplicarlos al
            resultado.
          </p>
        )}
        {showResult && (
          <p className="text-sm text-text-secondary">
            Resultado reproducible: use los controles del video para pausar,
            buscar posición o volver al inicio.
          </p>
        )}
      </section>

      <aside
        aria-label="Estado del análisis"
        className="self-start rounded-panel border border-border bg-surface p-5"
      >
        <h2 className="mb-4 text-base font-semibold">Estado del análisis</h2>
        <label className="mb-4 block text-sm text-text-secondary">
          Perfil de zona
          <select
            value={profile}
            disabled={busy || (!!session && !canEdit)}
            onChange={(event) =>
              void changeProfile(event.target.value as AnalysisProfile)
            }
            className="mt-1 block w-full rounded-control border border-border bg-surface px-3 py-2 text-foreground"
          >
            <option value="A">A · warehouse fire</option>
            <option value="B">B · nearmiss</option>
            <option value="C">C · box pickup</option>
          </select>
        </label>
        <dl className="space-y-3 text-sm">
          {[
            [
              "Estado",
              session
                ? labels[session.state]
                : sourceName
                  ? "Video listo"
                  : "Vacío",
            ],
            [
              "Fuente",
              sourceKind === "demo"
                ? "Demo incluida"
                : sourceKind === "manual"
                  ? "Video manual"
                  : "—",
            ],
            ["Video", sourceName ?? "—"],
            [
              "Tamaño",
              sourceBytes ? `${(sourceBytes / 1048576).toFixed(1)} MiB` : "—",
            ],
            [
              "Duración",
              sourceName && videoInfo.duration
                ? `${videoInfo.duration.toFixed(1)} s`
                : "—",
            ],
            [
              "Resolución",
              sourceName ? `${videoInfo.width} × ${videoInfo.height}` : "—",
            ],
            [
              "Frame",
              session ? `${session.frame} / ${session.total ?? "—"}` : "—",
            ],
            [
              "Progreso",
              session?.percent == null
                ? "—"
                : `${session.percent.toFixed(1)} %`,
            ],
            [
              "Rendimiento",
              session?.fps == null
                ? "—"
                : `${session.fps.toFixed(2)} FPS del Motor`,
            ],
            [
              "Personas",
              session && session.run > 0
                ? String(session.person_detections)
                : "—",
            ],
            [
              "Montacargas",
              session && session.run > 0
                ? String(session.forklift_detections)
                : "—",
            ],
            [
              "Zona",
              showResult
                ? (session.result?.zone.name ?? "—")
                : (session?.zone.name ?? "—"),
            ],
            ["Perfil del resultado", session?.result?.profile ?? "—"],
            ["Regla", session ? "zone_dwell · solo person" : "—"],
            [
              "FPS del video",
              session?.result
                ? `${session.result.video.fps.toFixed(2)} FPS`
                : "—",
            ],
          ].map(([label, value]) => (
            <div
              key={label}
              className="flex justify-between gap-3 border-b border-border/60 pb-2"
            >
              <dt className="text-text-secondary">{label}</dt>
              <dd
                className="max-w-[11rem] truncate text-right font-medium tabular-nums"
                title={value}
              >
                {value}
              </dd>
            </div>
          ))}
        </dl>
        <p className="mt-4 text-xs leading-5 text-text-secondary">
          Durante el análisis, el preview sigue al Motor. El resultado terminado
          se reproduce al FPS de la fuente.
        </p>
      </aside>
    </div>
  );
}
