"use client";
/* eslint-disable @next/next/no-img-element -- MJPEG multipart necesita img nativo. */

import { RuleConfiguration } from "@/features/analysis/rule-configuration";
import { SpatialEditor } from "@/features/analysis/spatial-editor";
import { VideoControls } from "@/features/analysis/video-controls";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { MetricSummary } from "@/components/ui/metric-summary";
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
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
  type RefObject,
} from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { calmSpring, enterTransition } from "@/lib/motion/presets";
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
import {
  pointInFrame,
  removeVertex,
  validPolygon,
} from "./zone-editor-geometry";
import { analysisError } from "./analysis-feedback";
import styles from "./analysis.module.css";
import { environment } from "@/config/environment";
import {
  analysisPercent,
  applyZoneRequest,
  tabStorage,
  sessionVideoInfo,
  readSessionReference,
  sessionReferenceKey,
  writeSessionReference,
} from "./analysis-session";

const referenceKey = sessionReferenceKey(environment.apiBaseUrl);

function attachVideo(
  ref: RefObject<HTMLVideoElement | null>,
  video: HTMLVideoElement | null,
) {
  ref.current = video;
  if (!video) return;
  if (video.dataset.source) video.src = video.dataset.source;
  return () => {
    // Detaching a video alone does not cancel its media requests.
    video.pause();
    video.removeAttribute("src");
    video.load();
    ref.current = null;
  };
}

const labels = {
  ready: "Video listo para analizar.",
  preparing: "Preparando modelos y video…",
  processing: "Procesando video…",
  completed: "Análisis completado.",
  error: "Error de análisis.",
  cancelled: "Análisis detenido.",
} as const;

export function AnalysisWorkspace({
  suite = "real",
  initialProfile = "A",
  initialManual = false,
  profileRequested = false,
  initialConfigure = false,
  requestedSessionId,
  requestedSourceSha,
}: {
  suite?: "real" | "simulation";
  initialProfile?: AnalysisProfile;
  initialManual?: boolean;
  profileRequested?: boolean;
  initialConfigure?: boolean;
  requestedSessionId?: string;
  requestedSourceSha?: string;
}) {
  const requestedProfile = profileRequested ? initialProfile : null;
  const requestedSha = requestedSourceSha?.toLowerCase();
  const configurationRequest = JSON.stringify([
    initialConfigure,
    requestedProfile,
    requestedSha,
    requestedSessionId,
  ]);
  const [file, setFile] = useState<File | null>(null);
  const [localUrl, setLocalUrl] = useState<string | null>(null);
  const [profile, setProfile] = useState<AnalysisProfile>(initialProfile);
  const [profileSelected, setProfileSelected] = useState(false);
  const [profiles, setProfiles] = useState<AnalysisProfileDefinition[]>([]);
  const [demoSource, setDemoSource] = useState<DemoVideoSource | null>(null);
  const [session, setSession] = useState<AnalysisSessionStatus | null>(null);
  const [busy, setBusy] = useState(true);
  const [operation, setOperation] = useState("Consultando perfiles y sesión…");
  const [loadRevision, setLoadRevision] = useState(0);
  const [newPoint, setNewPoint] = useState({ x: "50", y: "50" });
  const [error, setError] = useState<string | null>(null);
  const [videoInfo, setVideoInfo] = useState({
    width: 1920,
    height: 1080,
    duration: 0,
  });
  const [editing, setEditing] = useState(false);
  const [suspendResult, setSuspendResult] = useState(false);
  const [switchingDemo, setSwitchingDemo] = useState(false);
  const [draft, setDraft] = useState<NormalizedVertex[]>([]);
  const [closed, setClosed] = useState(true);
  const [selectedVertex, setSelectedVertex] = useState<number | null>(null);
  const reducedMotion = useReducedMotion();
  const detailsButton = useRef<HTMLButtonElement>(null);
  const [inspectorOpen, setInspectorOpen] = useState(false);
  const dragging = useRef<number | null>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const resultVideoRef = useRef<HTMLVideoElement>(null);
  const attachReference = useCallback(
    (video: HTMLVideoElement | null) => attachVideo(videoRef, video),
    [],
  );
  const attachResult = useCallback(
    (video: HTMLVideoElement | null) => attachVideo(resultVideoRef, video),
    [],
  );
  const changingProfile = useRef(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const localUrlRef = useRef<string | null>(null);
  const [spatialEditing, setSpatialEditing] = useState(false);
  const [spatialDirty, setSpatialDirty] = useState(false);
  const [zoneRevision, setZoneRevision] = useState(0);
  const [autoOpened, setAutoOpened] = useState("");
  const [replacementRequest, setReplacementRequest] = useState("");
  const [zoneUndo, setZoneUndo] = useState<
    { polygon: NormalizedVertex[]; closed: boolean }[]
  >([]);
  const zoneChanged =
    editing && JSON.stringify(draft) !== JSON.stringify(session?.zone.polygon);
  const hasDraft = spatialDirty || zoneChanged;
  const rememberZone = () =>
    setZoneUndo((history) => [
      ...history.slice(-31),
      { polygon: draft, closed },
    ]);

  useEffect(() => {
    if (!hasDraft) return;
    const warn = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = true;
    };
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [hasDraft]);

  function confirmDraftLoss() {
    return (
      !hasDraft ||
      window.confirm("¿Descartar el borrador sin guardar y cambiar la sesión?")
    );
  }
  const generation = useRef(0);
  const pollFailed = useRef(false);
  const sessionId = session?.id;

  useEffect(() => {
    return () => {
      generation.current += 1;
      if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
      // Navegar no equivale a limpiar: la sesión sigue bajo retención del Backend.
    };
  }, []);

  useEffect(() => {
    if (sessionId) writeSessionReference(tabStorage(), referenceKey, sessionId);
  }, [sessionId]);

  useEffect(() => {
    let active = true;
    const current = ++generation.current;
    const isCurrent = () => active && generation.current === current;
    const saved = readSessionReference(tabStorage(), referenceKey);
    Promise.allSettled([
      analysisService.getProfiles(suite),
      saved ? analysisService.getAnalysisStatus(saved) : Promise.resolve(null),
      requestedSessionId && requestedSessionId !== saved
        ? analysisService.getAnalysisStatus(requestedSessionId)
        : Promise.resolve(null),
    ])
      .then(async ([catalogResult, restored, requested]) => {
        if (!isCurrent()) return;
        const catalog =
          catalogResult.status === "fulfilled" ? catalogResult.value : [];
        setProfiles(catalog);
        const savedSession = restored.status === "fulfilled" ? restored.value : null;
        const candidate = requestedSessionId === saved
          ? savedSession
          : requested.status === "fulfilled" ? requested.value : null;
        if (
          candidate &&
          (!requestedSha || candidate.source_sha256 === requestedSha) &&
          (!requestedProfile || candidate.profile === requestedProfile)
        ) {
          setSession(candidate);
          setProfile(candidate.profile);
          setDraft(candidate.zone.polygon);
          setVideoInfo(sessionVideoInfo(candidate));
          setClosed(candidate.zone.polygon.length >= 3);
          setFile(null);
          setLocalUrl(null);
          setDemoSource(null);
          if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
          localUrlRef.current = null;
          setEditing(false);
          return;
        }
        if (saved) {
          if (restored.status === "rejected") {
            if (
              restored.reason instanceof AnalysisRequestError &&
              restored.reason.status === 404
            ) {
              writeSessionReference(tabStorage(), referenceKey, null);
              setError(
                "La sesión anterior expiró. Seleccione una demo o un video para continuar.",
              );
            } else {
              throw restored.reason;
            }
          } else if (restored.value &&
            (!requestedSessionId || requestedSessionId === restored.value.id) &&
            (!requestedSha || restored.value.source_sha256 === requestedSha) &&
            (!requestedProfile || restored.value.profile === requestedProfile) &&
            (requestedSessionId || requestedSha ||
              (restored.value.source_kind === "manual" ? initialManual || !requestedProfile :
                !initialManual && catalog.some(({ id, default_demo_video }) =>
                  id === restored.value?.profile && default_demo_video?.id === restored.value?.demo_source_id)))) {
            setSession(restored.value);
            setProfile(restored.value.profile);
            setDraft(restored.value.zone.polygon);
            setVideoInfo(sessionVideoInfo(restored.value));
            setClosed(restored.value.zone.polygon.length >= 3);
            return;
          }
        }
        if (catalogResult.status === "rejected") throw catalogResult.reason;
        setProfile(initialProfile);
        if (
          !requestedProfile ||
          initialManual ||
          requestedSha ||
          requestedSessionId
        )
          return;
        const initial = catalog.find((item) => item.id === initialProfile);
        if (!initial?.default_demo_video) return;
        setBusy(true);
        setOperation("Preparando video del perfil…");
        const created = await analysisService.createDemoSession(
          initialProfile,
          initial.default_demo_video.id,
          undefined,
          savedSession?.source_kind === "demo" &&
            ["ready", "completed", "cancelled", "error"].includes(savedSession.state)
            ? savedSession.id : undefined,
        );
        if (!isCurrent()) {
          await analysisService.closeAnalysisSession(created.id);
          return;
        }
        setDemoSource(initial.default_demo_video);
        setSession(created);
        setProfile(created.profile);
        setError(null);
        setDraft(created.zone.polygon);
        setClosed(created.zone.polygon.length >= 3);
      })
      .catch((cause: unknown) => {
        if (isCurrent()) {
          setError(
            analysisError(
              cause,
              "No se pudo preparar Análisis. Vuelve a intentarlo.",
            ),
          );
        }
      })
      .finally(() => {
        if (isCurrent()) setBusy(false);
      });
    return () => {
      active = false;
    };
  }, [
    initialManual,
    initialProfile,
    loadRevision,
    requestedProfile,
    requestedSessionId,
    requestedSha,
    suite,
  ]);

  useEffect(() => {
    const id = session?.id;
    const state = session?.state;
    if (!id || !state) return;
    const current = generation.current;
    const active = state === "preparing" || state === "processing";
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
              writeSessionReference(tabStorage(), referenceKey, null);
              setEditing(false);
              setError(
                "La sesión ya no está disponible. Seleccione de nuevo el perfil o cargue un video.",
              );
              return;
            }
            setError(
              analysisError(
                cause,
                "No se pudo consultar el estado. Reintentando…",
              ),
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
  }, [session?.id, session?.state]);

  async function selectVideo(selected: File | undefined) {
    if (!selected || busy || !canChangeSource || !confirmDraftLoss()) return;
    const current = generation.current;
    setOperation("Preparando video…");
    setBusy(true);
    setError(null);
    let created: AnalysisSessionStatus | null = null;
    try {
      created = await analysisService.createSession(
        selected,
        requestedProfile ?? profile,
        requestedSha,
      );
      if (generation.current !== current) {
        await analysisService.closeAnalysisSession(created.id);
        return;
      }
      if (requestedSha && created.source_sha256 !== requestedSha) {
        await analysisService.closeAnalysisSession(created.id);
        created = null;
        setError(
          "El archivo elegido corresponde a otra fuente. Selecciona el video original de la revisión.",
        );
        return;
      }
      if (session?.state === "completed") {
        setSuspendResult(true);
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => resolve()),
        );
      }
      if (session && !requestedSha)
        await analysisService.closeAnalysisSession(session.id);
      if (generation.current !== current) {
        await analysisService.closeAnalysisSession(created.id);
        return;
      }
      ++generation.current;
      if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
      const url = URL.createObjectURL(selected);
      localUrlRef.current = url;
      setLocalUrl(url);
      if (pendingRequest)
        setReplacementRequest(`${configurationRequest}:${created.id}`);
      setFile(selected);
      setDemoSource(null);
      setSession(created);
      setProfile(created.profile);
      setDraft(created.zone.polygon);
      setClosed(created.zone.polygon.length >= 3);
      setSelectedVertex(null);
      setEditing(false);
    } catch (cause) {
      if (created)
        await analysisService
          .closeAnalysisSession(created.id)
          .catch(() => undefined);
      if (generation.current === current)
        setError(
          analysisError(
            cause,
            "No se pudo preparar el video. Vuelve a intentarlo.",
          ),
        );
    } finally {
      setSuspendResult(false);
      setBusy(false);
    }
  }

  async function selectProfileDemo(
    next: AnalysisProfile,
    target?: { sourceSha?: string },
  ) {
    const demo = profiles.find((item) => item.id === next)?.default_demo_video;
    if (!demo)
      throw new Error(
        "Este perfil no tiene un video demo disponible. Selecciona un archivo local.",
      );
    const current = generation.current;
    setSwitchingDemo(true);
    const created = await analysisService.createDemoSession(
      next,
      demo.id,
      target?.sourceSha,
      target ? undefined : session?.id,
    );
    try {
      if (generation.current !== current) {
        await analysisService.closeAnalysisSession(created.id);
        return;
      }
      if (target?.sourceSha && created.source_sha256 !== target.sourceSha)
        throw new Error(
          "La demo corresponde a otra fuente. Selecciona el video original de la revisión.",
        );
    } catch (cause) {
      await analysisService
        .closeAnalysisSession(created.id)
        .catch(() => undefined);
      throw cause;
    }
    ++generation.current;
    if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
    localUrlRef.current = null;
    setLocalUrl(null);
    setFile(null);
    setDemoSource(demo);
    if (target) setReplacementRequest(`${configurationRequest}:${created.id}`);
    setSession(created);
    setProfile(created.profile);
    if (!requestedSha && !requestedSessionId && !initialConfigure) {
      setProfileSelected(true);
      const query = new URLSearchParams({ profile: created.profile, suite });
      window.history.replaceState(window.history.state, "", `/analysis?${query}`);
    }
    setDraft(created.zone.polygon);
    setClosed(created.zone.polygon.length >= 3);
    setSelectedVertex(null);
    setEditing(false);
  }

  async function start() {
    if (!session || spatialEditing || spatialDirty) return;
    videoRef.current?.pause();
    if (videoRef.current) videoRef.current.currentTime = 0;
    setOperation("Iniciando análisis…");
    const current = ++generation.current;
    setBusy(true);
    setError(null);
    try {
      if (session.state === "completed") {
        setSuspendResult(true);
        await new Promise<void>((resolve) =>
          requestAnimationFrame(() => resolve()),
        );
      }
      const updated = await analysisService.startAnalysisSession(session.id);
      if (generation.current !== current) return;
      setSession(updated);
      setEditing(false);
    } catch (cause) {
      if (generation.current !== current) return;
      try {
        const updated = await analysisService.getAnalysisStatus(session.id);
        if (generation.current !== current) return;
        setSession(updated);
      } catch {
        // El error original es más útil; la sesión puede haberse cerrado.
      }
      setError(
        analysisError(cause, "No se pudo iniciar. Vuelve a intentarlo."),
      );
    } finally {
      if (generation.current === current) {
        setSuspendResult(false);
        setBusy(false);
      }
    }
  }

  async function stop() {
    if (!session) return;
    setOperation("Deteniendo análisis…");
    const current = ++generation.current;
    setBusy(true);
    setError(null);
    try {
      const updated = await analysisService.stopAnalysisSession(session.id);
      if (generation.current !== current) return;
      setSession(updated);
    } catch (cause) {
      if (generation.current !== current) return;
      try {
        const updated = await analysisService.getAnalysisStatus(session.id);
        if (generation.current !== current) return;
        setSession(updated);
      } catch {
        // El error original es más útil; la sesión puede haberse cerrado.
      }
      setError(
        analysisError(cause, "No se pudo detener. Vuelve a intentarlo."),
      );
    } finally {
      if (generation.current === current) setBusy(false);
    }
  }

  async function applyZone() {
    if (!session || !closed || !validPolygon(draft)) {
      setError("Cierre un polígono simple con al menos tres vértices.");
      return;
    }
    setBusy(true);
    setError(null);
    setOperation("Guardando zona…");
    await applyZoneRequest(
      generation,
      () => analysisService.updateZone(session.id, { polygon: draft }),
      {
        applied: (updated) => {
          setSession(updated);
          setEditing(false);
          setZoneRevision((value) => value + 1);
        },
        failed: (cause) =>
          setError(
            analysisError(
              cause,
              "No se pudo aplicar la zona. Revisa el polígono y reintenta.",
            ),
          ),
        settled: () => setBusy(false),
      },
    );
  }

  async function changeProfile(
    next: AnalysisProfile,
    useDemo = false,
    target?: { sourceSha?: string },
  ) {
    if (
      busy ||
      changingProfile.current ||
      !canChangeSource ||
      (next === profile && !useDemo && session) ||
      !confirmDraftLoss()
    )
      return;
    changingProfile.current = true;
    setOperation("Aplicando perfil…");
    setBusy(true);
    setError(null);
    try {
      if (session?.source_kind === "manual" && !useDemo && !target) {
        const current = ++generation.current;
        const updated = await analysisService.updateZone(session.id, {
          profile: next,
        });
        if (generation.current !== current) return;
        setProfile(updated.profile);
        setSession(updated);
        setDraft(updated.zone.polygon);
        setClosed(updated.zone.polygon.length >= 3);
        setSelectedVertex(null);
        setEditing(false);
      } else {
        const nextDemo = profiles.find(
          (item) => item.id === next,
        )?.default_demo_video;
        if (nextDemo) {
          await selectProfileDemo(next, target);
        } else {
          if (session) {
            setError(
              `El Perfil ${next} no tiene una demo configurada. Carga un video compatible para preparar ese perfil.`,
            );
            return;
          }
          setProfile(next);
          setDemoSource(null);
          setDraft([]);
          setEditing(false);
        }
      }
    } catch (cause) {
      setError(
        analysisError(
          cause,
          "No se pudo preparar el perfil. Vuelve a intentarlo.",
        ),
      );
    } finally {
      changingProfile.current = false;
      setSwitchingDemo(false);
      setBusy(false);
    }
  }

  async function clearSession() {
    if (!session || !canChangeSource || !confirmDraftLoss()) return;
    setOperation("Limpiando sesión…");
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
      await analysisService.closeAnalysisSession(session.id);
      writeSessionReference(tabStorage(), referenceKey, null);
      if (localUrlRef.current) URL.revokeObjectURL(localUrlRef.current);
      localUrlRef.current = null;
      setLocalUrl(null);
      setFile(null);
      setDemoSource(null);
      setSession(null);
      setEditing(false);
      if (fileInputRef.current) fileInputRef.current.value = "";
    } catch (cause) {
      setError(
        analysisError(
          cause,
          "No se pudo limpiar la sesión. Vuelve a intentarlo.",
        ),
      );
    } finally {
      setSuspendResult(false);
      setBusy(false);
    }
  }

  const state = session?.state;
  const sourceName =
    session?.filename ?? file?.name ?? demoSource?.filename ?? null;
  const sourceBytes =
    session?.source_bytes ?? file?.size ?? demoSource?.bytes ?? null;
  const sourceKind =
    session?.source_kind ?? (file ? "manual" : demoSource ? "demo" : null);
  const referenceUrl =
    localUrl ??
    (session ? analysisService.getAnalysisSourceUrl(session.id) : null);
  const selectedProfile = profiles.find((item) => item.id === profile);
  const canEdit =
    !!session &&
    ["ready", "completed", "cancelled", "error"].includes(session.state) &&
    !busy;
  const matchesRequest =
    !!session &&
    (!requestedProfile || profileSelected || session.profile === requestedProfile) &&
    (!requestedSha || session.source_sha256 === requestedSha) &&
    (!requestedSessionId ||
      session.id === requestedSessionId ||
      Boolean(requestedSha) ||
      replacementRequest === `${configurationRequest}:${session.id}`);
  const pendingRequest =
    Boolean(requestedSha || requestedProfile || requestedSessionId) &&
    !matchesRequest;
  const requestDemo = profiles.find(
    (item) => item.id === requestedProfile,
  )?.default_demo_video;
  const canChangeSource = !spatialEditing && (!session || canEdit);
  const autoOpenKey = `${configurationRequest}:${session?.id}`;
  const consumeAutoOpen = useCallback(
    () => setAutoOpened(autoOpenKey),
    [autoOpenKey],
  );
  const showStream =
    !!session && ["preparing", "processing"].includes(session.state);
  const showResult =
    !switchingDemo &&
    !!session &&
    session.state === "completed" &&
    !!session.result &&
    !editing &&
    !suspendResult;
  const showReference =
    !switchingDemo &&
    !suspendResult &&
    !!sourceName &&
    !!referenceUrl &&
    !showResult;
  const visibleError = error
    ? analysisError(
        error,
        "No se pudo completar la acción. Vuelve a intentarlo.",
      )
    : session?.persistence?.state === "failed"
      ? "El análisis puede estar completo, pero sus eventos no quedaron guardados íntegramente. Puede reintentar el guardado sin analizar de nuevo."
      : session?.state === "error" && session.detail
        ? analysisError(
            session.detail,
            "El análisis se interrumpió. Puedes volver a intentarlo.",
          )
        : null;
  const contextState =
    session?.state === "completed" && session.persistence?.state === "failed"
      ? "Análisis completado · eventos pendientes de guardado"
      : session
        ? labels[session.state]
        : "Sin fuente preparada";
  const percent = session
    ? analysisPercent(session.state, session.percent)
    : null;

  function moveVertexWithKeyboard(
    event: KeyboardEvent<SVGEllipseElement>,
    index: number,
  ) {
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      if (draft.length > 3) rememberZone();
      setDraft((points) => removeVertex(points, index));
      setSelectedVertex(null);
      dragging.current = null;
      return;
    }
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
    rememberZone();
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
          <p
            role="status"
            aria-atomic="true"
            className={`analysis-state ${visibleError ? "is-error" : ""}`}
          >
            {contextState}
          </p>
          <p className="mt-1 truncate text-xs text-text-secondary">
            {sourceName
              ? `${sourceName} · ${sourceKind === "demo" ? "demo incluida" : "video manual"}`
              : "Seleccione una demo o un video local para comenzar."}
          </p>
          {session && (
            <p className={styles.contextFacts}>
              {session.spatial_revision
                ? `Revisión ${session.spatial_revision}`
                : "Configuración inicial"}
              {session.configuration &&
                ` · ${session.configuration.rules.filter((rule) => rule.enabled).length} reglas activas`}
              {session.configuration?.calibration?.status === "valid"
                ? " · Calibración guardada"
                : session.configuration?.calibration?.status === "invalid"
                  ? " · Encuadre invalidado"
                  : " · Sin calibración métrica"}
            </p>
          )}
        </div>
        <div className="analysis-context-actions">
          <nav aria-label="Colección de Análisis" className="flex flex-wrap gap-2">
            <Link className="button button-outline" aria-current={suite === "real" ? "page" : undefined}
              href={`/analysis?profile=${profile}&suite=real`}
              onClick={(event) => { if (!canChangeSource || busy || !confirmDraftLoss()) event.preventDefault(); }}>
              Grabaciones reales
            </Link>
            <Link className="button button-outline" aria-current={suite === "simulation" ? "page" : undefined}
              href={`/analysis?profile=${profile}&suite=simulation`}
              onClick={(event) => { if (!canChangeSource || busy || !confirmDraftLoss()) event.preventDefault(); }}>
              Simulaciones de prueba
            </Link>
          </nav>
          <div
            className="analysis-profiles"
            role="group"
            aria-label="Perfil de zona"
            aria-busy={switchingDemo}
          >
            {(["A", "B", "C"] as AnalysisProfile[]).map((item) => {
              const profileName =
                profiles.find((candidate) => candidate.id === item)
                  ?.display_name ??
                (item === "A"
                  ? "Proximidad peatón–montacargas"
                  : item === "B"
                    ? "Ingreso observado en zona"
                    : "Observación de operación logística");

              return (
                <button
                  key={item}
                  type="button"
                  className={`analysis-profile ${profile === item ? "is-active" : ""}`}
                  aria-pressed={profile === item}
                  disabled={busy || !canChangeSource}
                  onClick={() =>
                    void changeProfile(
                      item,
                      false,
                      pendingRequest && item === requestedProfile
                        ? { sourceSha: requestedSha }
                        : undefined,
                    )
                  }
                >
                  {profile === item && (
                    <motion.span
                      aria-hidden="true"
                      className="analysis-profile-selection"
                      layoutId={
                        reducedMotion ? undefined : "analysis-profile-selection"
                      }
                      initial={false}
                      transition={enterTransition}
                    />
                  )}
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
              disabled={busy || !canChangeSource}
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
            ref={detailsButton}
            id="analysis-inspector-trigger"
            aria-expanded={inspectorOpen}
            aria-controls="analysis-details"
            onClick={() => setInspectorOpen((current) => !current)}
          >
            <Info size={16} aria-hidden="true" /> Detalles
          </button>
        </div>
      </section>

      {!busy && pendingRequest && (
        <div className={styles.request}>
          <p>
            {requestedProfile
              ? `Perfil ${requestedProfile} solicitado.`
              : "Fuente solicitada."}{" "}
            {session &&
              `Sesión actual: ${session.filename} (Perfil ${session.profile}). `}
            {showStream
              ? "Puedes cambiar de fuente cuando termine el análisis."
              : requestedSha
                ? "Selecciona el video original de la revisión para preparar esta fuente."
                : requestDemo
                  ? "Prepara el perfil para cambiar de fuente."
                  : requestedSessionId
                    ? "La sesión solicitada no está disponible. Selecciona un video local."
                    : "Selecciona un video local para preparar la fuente."}
          </p>
          {!showStream && requestedProfile && requestDemo && !initialManual && (
            <Button
              variant="outline"
              disabled={!canChangeSource}
              onClick={() =>
                void changeProfile(requestedProfile, true, {
                  sourceSha: requestedSha,
                })
              }
            >
              Preparar perfil {requestedProfile}
            </Button>
          )}
        </div>
      )}
      <div
        className={`analysis-layout ${session || inspectorOpen || switchingDemo || (busy && !initialManual) ? "has-telemetry" : ""}`}
      >
        <section aria-label="Video de análisis" className="analysis-view">
          <div
            className={`analysis-media-frame ${(sourceName || switchingDemo) && videoInfo.height > videoInfo.width ? "is-portrait" : ""}`}
            style={
              {
                "--analysis-source-ratio": videoInfo.width / videoInfo.height,
              } as React.CSSProperties
            }
          >
            <div className="analysis-media-stage">
              <div
                className={`analysis-stage ${styles.stage} ${sourceName || switchingDemo ? "has-source" : "is-empty"}`}
                style={{
                  aspectRatio: `${videoInfo.width} / ${videoInfo.height}`,
                }}
              >
                {switchingDemo && (
                  <div className="analysis-source-loading">
                    <OperixScanLoader
                      variant="panel"
                      message="Cargando video del perfil…"
                    />
                  </div>
                )}
                {!sourceName && !switchingDemo && busy && (
                  <div className="analysis-source-loading">
                    <OperixScanLoader variant="panel" message={operation} />
                  </div>
                )}
                {!sourceName && !switchingDemo && !busy && (
                  <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center text-white/80">
                    <Upload size={30} aria-hidden="true" />
                    <p className="text-lg font-semibold">
                      {profiles.length > 0 &&
                      !selectedProfile?.default_demo_video
                        ? `Perfil ${profile} · demo no disponible`
                        : "Sin fuente de video"}
                    </p>
                    <p className="max-w-sm text-sm opacity-75">
                      {profiles.length > 0 &&
                      !selectedProfile?.default_demo_video
                        ? "Selecciona un archivo MP4, MOV o AVI desde Cambiar fuente."
                        : "Seleccione un archivo o use una demo."}
                    </p>
                  </div>
                )}
                {showReference && referenceUrl && (
                  <video
                    key={referenceUrl}
                    ref={attachReference}
                    data-source={referenceUrl}
                    playsInline
                    preload="metadata"
                    className="absolute inset-0 h-full w-full object-contain"
                    onLoadedMetadata={(event) => {
                      const video = event.currentTarget;
                      if (video !== videoRef.current) return;
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
                    alt="Vista previa muestreada del análisis"
                    className="absolute inset-0 h-full w-full object-contain"
                  />
                )}
                {showResult && (
                  <video
                    key={`${session.id}-${session.run}-result`}
                    ref={attachResult}
                    data-source={analysisService.getAnalysisResultUrl(
                      session.id,
                      session.run,
                    )}
                    playsInline
                    onLoadedMetadata={(event) => {
                      const video = event.currentTarget;
                      if (video !== resultVideoRef.current) return;
                      setVideoInfo({
                        width: video.videoWidth,
                        height: video.videoHeight,
                        duration: Number.isFinite(video.duration)
                          ? video.duration
                          : 0,
                      });
                    }}
                    preload="metadata"
                    aria-label="Resultado anotado de Operix"
                    className="absolute inset-0 h-full w-full object-contain"
                  />
                )}
                {showResult && (
                  <VideoControls
                    key={`${session.id}-${session.run}-controls`}
                    videoRef={resultVideoRef}
                    loadingMessage="Cargando resultado anotado…"
                  />
                )}
                {showReference && referenceUrl && !editing && !showStream && (
                  <VideoControls
                    key={`reference-controls-${referenceUrl}`}
                    videoRef={videoRef}
                  />
                )}
                {showReference && !showStream && session && (
                  <svg
                    viewBox="0 0 100 100"
                    preserveAspectRatio="none"
                    className={`absolute inset-0 h-full w-full ${styles.zoneOverlay} ${editing ? "touch-none cursor-crosshair" : "pointer-events-none"}`}
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
                      if (point && draft.length < 32) {
                        rememberZone();
                        setDraft((current) => [...current, point].slice(0, 32));
                      }
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
                          aria-label={`Vértice ${index + 1}, x ${(x * 100).toFixed(1)} %, y ${(y * 100).toFixed(1)} %. Use las flechas para moverlo y Mayús para un desplazamiento mayor; Suprimir elimina el vértice si hay más de tres.`}
                          onFocus={() => setSelectedVertex(index)}
                          onKeyDown={(event) =>
                            moveVertexWithKeyboard(event, index)
                          }
                          onPointerDown={(event) => {
                            event.stopPropagation();
                            if (!closed && index === 0 && draft.length >= 3) {
                              rememberZone();
                              setClosed(true);
                              return;
                            }
                            rememberZone();
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
              {busy && sourceName && !showStream && !switchingDemo && (
                <OperixScanLoader
                  variant="process"
                  size="small"
                  message={operation}
                />
              )}
              {session &&
                ["preparing", "processing"].includes(session.state) && (
                  <div className="analysis-toolbar-status">
                    <OperixScanLoader
                      variant="process"
                      size="small"
                      announce={false}
                      message={
                        session.state === "preparing"
                          ? "Preparando modelos y video…"
                          : "Procesando fotogramas…"
                      }
                    />
                    {percent !== null && (
                      <strong>{percent.toFixed(1)} %</strong>
                    )}
                    <span>
                      {session.state === "preparing"
                        ? (session.detail ??
                          "Verificando video y preparando modelos…")
                        : `${session.frame} / ${session.total ?? "—"} frames`}
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
                  disabled={busy || !canChangeSource}
                  accept=".mp4,.mov,.avi,video/mp4"
                  className="sr-only"
                  onChange={(event) => {
                    void selectVideo(event.target.files?.[0]);
                    event.target.value = "";
                  }}
                />
              </label>
              {(!sourceKind || sourceKind === "manual") &&
                selectedProfile?.default_demo_video && (
                  <Button
                    variant="secondary"
                    disabled={busy || !canChangeSource}
                    onClick={() => void changeProfile(profile, true)}
                  >
                    Usar video demo
                  </Button>
                )}
              {canEdit && !editing && (
                <Button
                  className="order-first"
                  data-guide="start"
                  onClick={() => void start()}
                  disabled={
                    !session ||
                    !validPolygon(session.zone.polygon) ||
                    spatialEditing ||
                    spatialDirty ||
                    session.configuration?.calibration?.status === "invalid"
                  }
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
              {canEdit && !editing && !session?.spatial_revision && (
                <Button
                  onClick={() => {
                    videoRef.current?.pause();
                    setZoneUndo([]);
                    setClosed((session?.zone.polygon.length ?? 0) >= 3);
                    setSelectedVertex(null);
                    setEditing(true);
                  }}
                  variant="outline"
                  className={styles.editZone}
                  disabled={spatialEditing || spatialDirty}
                >
                  <Waypoints size={16} aria-hidden="true" />{" "}
                  {session && session.zone.polygon.length < 3
                    ? "Crear zona"
                    : "Editar zona"}
                </Button>
              )}
              {session && canChangeSource && (
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
                    rememberZone();
                    setDraft([]);
                    setClosed(false);
                    setSelectedVertex(null);
                  }}
                >
                  Nueva zona
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    rememberZone();
                    setClosed(true);
                  }}
                  disabled={closed || draft.length < 3}
                >
                  Cerrar polígono
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    rememberZone();
                    setDraft((points) => removeVertex(points, selectedVertex));
                    setSelectedVertex(null);
                  }}
                  disabled={selectedVertex === null || draft.length <= 3}
                >
                  Eliminar vértice
                </Button>
                <Button
                  variant="secondary"
                  disabled={!zoneUndo.length}
                  onClick={() => {
                    const previous = zoneUndo[zoneUndo.length - 1];
                    setDraft(previous.polygon);
                    setClosed(previous.closed);
                    setSelectedVertex(null);
                    setZoneUndo(zoneUndo.slice(0, -1));
                  }}
                >
                  Deshacer
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    rememberZone();
                    const polygon = session?.zone.polygon ?? [];
                    setDraft(polygon);
                    setClosed(polygon.length >= 3);
                    setSelectedVertex(null);
                  }}
                >
                  Restablecer
                </Button>
                <Button
                  variant="secondary"
                  onClick={() => {
                    if (
                      zoneChanged &&
                      !window.confirm("¿Descartar los cambios de la zona?")
                    )
                      return;
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
                  {draft.length} {draft.length === 1 ? "vértice" : "vértices"} ·{" "}
                  {closed
                    ? "seleccione un punto para moverlo o eliminarlo (mínimo 3)"
                    : "marque puntos y pulse el primero para cerrar"}
                </span>
              </div>
            )}
            {editing && (
              <details className={styles.legacyCoordinates}>
                <summary>Coordenadas avanzadas</summary>
                <form
                  className="analysis-vertex-form"
                  onSubmit={(event) => {
                    event.preventDefault();
                    const x = Number(newPoint.x),
                      y = Number(newPoint.y);
                    if (
                      draft.length >= 32 ||
                      !newPoint.x.trim() ||
                      !newPoint.y.trim() ||
                      !Number.isFinite(x) ||
                      !Number.isFinite(y) ||
                      x < 0 ||
                      x > 100 ||
                      y < 0 ||
                      y > 100
                    )
                      return;
                    rememberZone();
                    setDraft((points) => [...points, [x / 100, y / 100]]);
                    setSelectedVertex(draft.length);
                  }}
                >
                  <p id="vertex-help">
                    Desde «Nueva zona», añada vértices por coordenadas o marque
                    puntos sobre el video. Origen: esquina superior izquierda.
                  </p>
                  <label>
                    X (%)
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.1"
                      required
                      value={newPoint.x}
                      onChange={(event) =>
                        setNewPoint({ ...newPoint, x: event.target.value })
                      }
                      disabled={closed}
                      aria-describedby="vertex-help"
                    />
                  </label>
                  <label>
                    Y (%)
                    <input
                      type="number"
                      min="0"
                      max="100"
                      step="0.1"
                      required
                      value={newPoint.y}
                      onChange={(event) =>
                        setNewPoint({ ...newPoint, y: event.target.value })
                      }
                      disabled={closed}
                    />
                  </label>
                  <Button
                    type="submit"
                    variant="outline"
                    disabled={closed || draft.length >= 32}
                  >
                    Añadir vértice
                  </Button>
                  <span role="status">
                    {draft.length} {draft.length === 1 ? "vértice" : "vértices"}
                    {closed ? " · polígono cerrado" : " · polígono abierto"}
                  </span>
                </form>
              </details>
            )}
            {editing && closed && !validPolygon(draft) && (
              <p role="status" className="analysis-result-help">
                El polígono necesita al menos tres vértices distintos, área y
                ningún cruce. Ajuste los vértices o cree una zona nueva.
              </p>
            )}
          </div>
          {session && (
            <SpatialEditor
              key={`${session.id}:${session.profile}:${zoneRevision}`}
              session={session}
              unavailable={!canEdit || editing}
              autoOpen={
                initialConfigure && matchesRequest && autoOpened !== autoOpenKey
              }
              onAutoOpen={consumeAutoOpen}
              onEditingChange={setSpatialEditing}
              onDirtyChange={setSpatialDirty}
              onSaved={(next) => {
                setSession((current) =>
                  current?.id === next.id ? next : current,
                );
                setDraft(next.zone.polygon);
                setClosed(next.zone.polygon.length >= 3);
              }}
            />
          )}
          {visibleError && (
            <p role="alert" className={styles.error}>
              {visibleError}
            </p>
          )}
          {session && !editing && session.zone.polygon.length < 3 && (
            <p className={styles.notice}>
              Crea y aplica una zona para iniciar el análisis.
            </p>
          )}
          {spatialDirty && !spatialEditing && (
            <p className={styles.notice}>
              Abre la configuración para guardar o descartar el borrador antes
              de analizar.
            </p>
          )}
          {canEdit &&
            session?.configuration?.calibration?.status === "invalid" && (
              <p className={styles.notice}>
                Encuadre invalidado. Revisa la calibración y guarda la
                configuración para iniciar.
              </p>
            )}
          {!session && visibleError && (
            <Button
              variant="outline"
              disabled={busy}
              onClick={() => {
                setOperation("Recuperando análisis…");
                setBusy(true);
                setError(null);
                setLoadRevision((value) => value + 1);
              }}
            >
              Reconectar y recuperar sesión
            </Button>
          )}
          {showStream && (
            <p className="analysis-result-help">
              Puedes navegar sin detener la sesión.
            </p>
          )}
          {session &&
            ["completed", "error", "cancelled"].includes(session.state) &&
            session.persistence && (
              <div className="analysis-result-help" aria-live="polite">
                {session.persistence.state === "saved" ? (
                  <p>
                    {session.persistence.saved ?? 0}{" "}
                    {session.persistence.saved === 1
                      ? "evento guardado"
                      : "eventos guardados"}
                    .{" "}
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
                      setOperation("Guardando eventos…");
                      setBusy(true);
                      void analysisService
                        .retryEventPersistence(session.id)
                        .then(setSession)
                        .catch((cause: unknown) =>
                          setError(
                            cause instanceof Error
                              ? analysisError(
                                  cause,
                                  "No se pudo guardar los eventos. Reintenta.",
                                )
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
              Hay cambios de configuración pendientes. Vuelva a analizar para
              aplicarlos al resultado.
            </p>
          )}
          {session?.framing && (
            <p role="status" className="analysis-result-help">
              {session.framing.reason === "legacy_manual_only"
                ? "Encuadre sin referencia automática. Si cambió la cámara, invalide la calibración y revise las zonas."
                : {
                    VALID:
                      "Encuadre compatible con la referencia en la última comprobación.",
                    SUSPECT:
                      "Posible cambio de encuadre. Zonas, mediciones y reglas espaciales suspendidas.",
                    INVALID:
                      "Encuadre invalidado. Zonas, mediciones y reglas espaciales suspendidas. Revise y recalibre la fuente.",
                    UNAVAILABLE:
                      "No hay suficientes referencias estáticas. Zonas, mediciones y reglas espaciales suspendidas.",
                  }[session.framing.state]}
              {session.framing.first_suspended_frame != null &&
                ` Primera suspensión en el fotograma ${session.framing.first_suspended_frame}.`}
            </p>
          )}
          {showStream && (
            <p className="analysis-result-help">
              Vista previa muestreada. Avanza cuando hay fotogramas procesados y
              puede mostrar saltos. El MP4 estará disponible al confirmar el
              resultado.
            </p>
          )}
          {showResult && (
            <p className="analysis-result-help">
              MP4 listo para reproducir
              {session.result?.video?.fps != null
                ? ` · ${session.result.video.fps.toFixed(2)} FPS de reproducción`
                : ""}
              .
            </p>
          )}
          {(showStream || showResult) && (
            <details className={styles.resultLegend}>
              <summary>Cómo leer las anotaciones</summary>
              <p>
                P# identifica a la persona y F# al montacargas. «d» es la
                distancia observada y «max», el umbral de la regla. «norm» usa
                la escala de la imagen. «m approx» indica metros aproximados
                sobre suelo calibrado. Un evento requiere revisión humana.
              </p>
            </details>
          )}
        </section>

        {(session || inspectorOpen) && (
          <aside
            aria-label="Estado del análisis"
            className="analysis-telemetry"
          >
            <motion.section
              id="analysis-details"
              className="analysis-inspector"
              hidden={!inspectorOpen}
              initial={false}
              animate={{ opacity: inspectorOpen ? 1 : 0 }}
              transition={reducedMotion ? { duration: 0 } : enterTransition}
            >
              <div className="analysis-inspector-head">
                <div>
                  <h2>Detalles del análisis</h2>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setInspectorOpen(false);
                    detailsButton.current?.focus();
                  }}
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
                      {percent == null ? "—" : `${percent.toFixed(1)} %`}
                    </span>
                  </div>
                  <div className="analysis-progress mt-3" aria-hidden="true">
                    <span style={{ width: `${percent ?? 0}%` }} />
                  </div>
                  <dl className="analysis-data mt-3">
                    <dt>Frame</dt>
                    <dd>
                      {session
                        ? `${session.frame} / ${session.total ?? "—"}`
                        : "—"}
                    </dd>
                    <dt>Motor</dt>
                    <dd>
                      {session?.fps == null
                        ? "—"
                        : `${session.fps.toFixed(2)} FPS`}
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
                      <span className="text-xs text-text-secondary">
                        PERSON
                      </span>
                    </div>
                    <div className="bg-surface py-3 pl-3">
                      <span className="block text-2xl font-semibold tabular-nums">
                        {session && session.run > 0
                          ? session.forklift_detections
                          : "—"}
                      </span>
                      <span className="text-xs text-text-secondary">
                        FORKLIFT
                      </span>
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
                  {!!session.equipment_motion?.length && (
                    <section
                      className="mt-4 grid gap-2"
                      aria-label="Movimiento observado"
                    >
                      <h3 className="section-heading">
                        Movimiento · último fotograma procesado
                      </h3>
                      {session.equipment_motion.map((item) => (
                        <p
                          key={`${item.epoch}-${item.track_id}`}
                          className="text-sm"
                        >
                          Montacargas · ID {item.track_id}:{" "}
                          {
                            {
                              MOVING: "En movimiento",
                              STATIONARY: "Estacionario",
                              UNKNOWN: "Indeterminado",
                            }[item.state]
                          }
                          {item.state !== "UNKNOWN" && item.speed != null
                            ? ` · ${item.speed.toLocaleString("es-CL", { maximumSignificantDigits: 4 })} ${item.unit === "m_per_s" ? "m/s aprox." : "unidades de imagen/s"}`
                            : ""}
                          {` · frame ${item.frame_index}`}
                        </p>
                      ))}
                    </section>
                  )}
                  <div className="mt-4 grid gap-2">
                    <p className="section-heading">
                      {showResult
                        ? "Reglas del resultado"
                        : session.state === "processing" ||
                            session.state === "preparing"
                          ? "Reglas de la ejecución"
                          : "Reglas del próximo análisis"}
                    </p>
                    <p className="analysis-inspector-note">
                      {showResult
                        ? session.result?.spatial_revision
                          ? `Revisión espacial del resultado: ${session.result.spatial_revision}`
                          : "Revisión espacial del resultado sin número registrado."
                        : session.state === "processing" ||
                            session.state === "preparing"
                          ? session.active_configuration?.spatial_revision
                            ? `Revisión espacial en ejecución: ${session.active_configuration.spatial_revision}`
                            : "Configuración inicial en ejecución."
                          : session.spatial_revision
                            ? `Revisión espacial preparada: ${session.spatial_revision}`
                            : "Configuración inicial preparada."}
                    </p>
                    <RuleConfiguration
                      equipmentContext={
                        showResult
                          ? session.result?.equipment_context
                          : session.equipment_context
                      }
                      snapshot={
                        showResult
                          ? session.result
                          : session.state === "processing" ||
                              session.state === "preparing"
                            ? session.active_configuration
                            : session.configuration
                      }
                    />
                    {showResult && session.pending_changes && (
                      <>
                        <p className="section-heading">
                          Reglas del próximo análisis
                        </p>
                        <RuleConfiguration snapshot={session.configuration} />
                      </>
                    )}
                  </div>
                </div>
              )}
              {!session && (
                <p className="analysis-inspector-note">
                  La configuración y la evidencia aparecerán al preparar una
                  fuente.
                </p>
              )}
            </motion.section>
            <motion.div
              layout={reducedMotion ? false : "position"}
              transition={calmSpring}
            >
              {session && (
                <MetricSummary label="Resumen de percepción" metrics={[
                  { label: "Personas · último fotograma analizado", value: session.run > 0 ? session.person_detections : null },
                  { label: "Montacargas · último fotograma analizado", value: session.run > 0 ? session.forklift_detections : null },
                  { label: "FPS de procesamiento", value: session.fps?.toFixed(2) },
                  { label: "Progreso", value: percent == null ? null : `${percent.toFixed(1)} %` },
                ]} />
              )}
            </motion.div>
          </aside>
        )}
      </div>
    </div>
  );
}
