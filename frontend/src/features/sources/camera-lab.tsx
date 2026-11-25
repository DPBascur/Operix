"use client";

import type { NormalizedVertex } from "@/services/analysis.service";
import { MotionConfiguration } from "@/features/analysis/motion-configuration";
import { RuleConfiguration } from "@/features/analysis/rule-configuration";
import { AutomaticCalibration } from "@/features/calibration/automatic-calibration";

import { ArrowLeft, Settings2, X } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { MetricSummary } from "@/components/ui/metric-summary";
import { PageTitle } from "@/components/layout/page-title";
import { operationalError } from "@/features/operations/operation-request";
import { Parameters } from "@/features/operations/policy-editor";
import { newParameters, type PolicyParameters } from "@/features/operations/policy-model";
import { eventTypeName } from "@/services/event-contract";
import {
  cameraLabService,
  type CameraDocument,
  type LabCamera,
} from "@/services/camera-lab.service";
import {
  cameraAnalysisRate,
  cameraCoverage,
  cameraFrameIsRecent,
  cameraObservationPaused,
  cameraFrameTime,
  cameraNumber,
  cameraTechnicalMetrics,
} from "./camera-diagnostics";
import {
  CameraMediaPanels,
  LoadError,
  statusLabel,
  useCameraData,
} from "./camera-overview";
import styles from "./camera-detail.module.css";

const idle = new Set(["available", "stopped", "error"]);
const calibrationSectionId = "camera-automatic-calibration";
const monitoring = new Set([
  "connecting",
  "transmitting",
  "analyzing",
  "no_signal",
  "overloaded",
  "reconnecting",
]);

type Feedback = { text: string; error?: boolean };

function ActionFeedback({ message }: { message?: Feedback }) {
  return (
    <>
      <p
        role="status"
        className={message && !message.error ? "text-sm" : "sr-only"}
      >
        {message?.error ? null : message?.text}
      </p>
      {message?.error && (
        <p role="alert" className="text-sm text-danger">
          {message.text}
        </p>
      )}
    </>
  );
}

export type CameraDraft = { revision: number; document: CameraDocument };

export function Configuration({
  camera,
  canEdit,
  canConfigure,
  busy,
  draft,
  metricAvailable,
  message,
  onSave,
  setDraft,
  title = "Configuración de la cámara",
  editableRules = false,
}: {
  camera: Pick<LabCamera, "configuration" | "revision" | "policy">;
  canEdit: boolean;
  canConfigure: boolean;
  busy: boolean;
  draft?: CameraDraft;
  metricAvailable: boolean;
  message?: Feedback;
  onSave: (revision: number, document: CameraDocument) => Promise<boolean>;
  setDraft: (draft: CameraDraft | undefined) => void;
  title?: string;
  editableRules?: boolean;
}) {
  const document = draft?.document ?? camera.configuration;
  const outdated = Boolean(draft && draft.revision !== camera.revision);
  const invalid = document?.zones?.some((zone) => !zone.name.trim());
  const locked = busy || outdated || !canConfigure;
  function edit(next: CameraDocument) {
    setDraft({ revision: draft?.revision ?? camera.revision, document: next });
  }

  return (
    <section
      className="surface-card grid min-w-0 gap-3 p-4"
      aria-labelledby="camera-config"
    >
      <div>
        <h2 id="camera-config" className="font-semibold">
          {title}
        </h2>
        <p className="text-sm text-text-secondary">
          Revisión {camera.revision}
          {!canEdit && " · Solo lectura"}
        </p>
      </div>
      {camera.policy && (
        <p className="text-sm text-text-secondary">
          El monitoreo aplica las reglas de {camera.policy.rule_set.name} · v
          {camera.policy.rule_set.version}.
        </p>
      )}
      {canEdit && !canConfigure && (
        <p className="text-sm text-text-secondary">
          Detén el monitoreo para editar la configuración.
        </p>
      )}
      {document &&
      Array.isArray(document.zones) &&
      Array.isArray(document.rules) ? (
        <form
          className="grid gap-4"
          onSubmit={async (event) => {
            event.preventDefault();
            if (
              draft &&
              canEdit &&
              !locked &&
              !invalid &&
              (await onSave(draft.revision, draft.document))
            ) {
              setDraft(undefined);
            }
          }}
        >
          <fieldset
            className="grid min-w-0 gap-2"
            disabled={!canEdit || locked}
          >
            <legend className="mb-2 font-medium">Zonas</legend>
            {document.zones.map((zone, index) => (
              <div
                className="grid gap-2 rounded-md border border-border p-3"
                key={zone.zone_id}
              >
                {canEdit ? (
                  <>
                    <label className="grid gap-1 break-words text-sm">
                      Nombre de la zona · {zone.zone_id}
                      <Input
                        required
                        value={zone.name}
                        onChange={(event) => {
                          const name = event.currentTarget.value;
                          edit({
                            ...document,
                            zones: document.zones.map((item, i) =>
                              i === index ? { ...item, name } : item,
                            ),
                          });
                        }}
                      />
                    </label>
                    <details className="text-sm">
                      <summary className="cursor-pointer">
                        Vértices normalizados
                      </summary>
                      <div className="mt-2 grid gap-2 sm:grid-cols-2">
                        {zone.polygon.map((point, vertexIndex) => (
                          <div
                            className="grid grid-cols-2 gap-2"
                            key={vertexIndex}
                          >
                            {(["X", "Y"] as const).map((axis, coordinate) => (
                              <label className="grid gap-1" key={axis}>
                                {axis} · Vértice {vertexIndex + 1}
                                <Input
                                  type="number"
                                  min={0}
                                  max={1}
                                  step="any"
                                  required
                                  value={point[coordinate]}
                                  onChange={(event) => {
                                    const value =
                                      event.currentTarget.valueAsNumber;
                                    if (!Number.isFinite(value)) return;
                                    const polygon = zone.polygon.map(
                                      (vertex, i) =>
                                        i !== vertexIndex
                                          ? vertex
                                          : coordinate === 0
                                            ? ([
                                                value,
                                                vertex[1],
                                              ] as NormalizedVertex)
                                            : ([
                                                vertex[0],
                                                value,
                                              ] as NormalizedVertex),
                                    );
                                    edit({
                                      ...document,
                                      zones: document.zones.map((item, i) =>
                                        i === index
                                          ? { ...item, polygon }
                                          : item,
                                      ),
                                    });
                                  }}
                                />
                              </label>
                            ))}
                          </div>
                        ))}
                      </div>
                    </details>
                    <label className="flex min-h-11 items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={zone.enabled !== false}
                        onChange={(event) => {
                          const enabled = event.currentTarget.checked;
                          edit({
                            ...document,
                            zones: document.zones.map((item, i) =>
                              i === index ? { ...item, enabled } : item,
                            ),
                          });
                        }}
                      />
                      Habilitar zona {zone.zone_id}
                    </label>
                  </>
                ) : (
                  <p className="text-sm">
                    {zone.name} ·{" "}
                    {zone.enabled === false ? "Deshabilitada" : "Habilitada"}
                  </p>
                )}
              </div>
            ))}
            {canEdit && document.zones.length < 16 && (
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  edit({
                    ...document,
                    zones: [
                      ...document.zones,
                      {
                        zone_id: "zone-" + crypto.randomUUID().slice(0, 8),
                        name: "Nueva zona",
                        polygon: [
                          [0.25, 0.25],
                          [0.75, 0.25],
                          [0.75, 0.75],
                          [0.25, 0.75],
                        ],
                      },
                    ],
                  })
                }
              >
                Agregar zona
              </Button>
            )}
            {!document.zones.length && (
              <p className="text-sm">Sin zonas declaradas.</p>
            )}
          </fieldset>
          <fieldset
            className="grid min-w-0 gap-1"
            disabled={!canEdit || locked || Boolean(camera.policy)}
          >
            <legend className="font-medium">Reglas</legend>
            {document.rules.map((rule, index) => {
              const label = `${eventTypeName(String(rule.parameters.kind ?? ""))} · ${rule.rule_id}`;
              return canEdit ? (
                <div key={rule.rule_id} className={editableRules ? "grid gap-2 rounded-md border border-border p-3" : undefined}>
                <label
                  className="flex min-h-11 items-center gap-2 break-words text-sm"
                >
                  <input
                    type="checkbox"
                    checked={rule.enabled}
                    onChange={(event) => {
                      const enabled = event.currentTarget.checked;
                      edit({
                        ...document,
                        rules: document.rules.map((item, i) =>
                          i === index ? { ...item, enabled } : item,
                        ),
                      });
                    }}
                  />
                  <span className="min-w-0">
                    {label} · v{rule.version}
                  </span>
                </label>
                {editableRules && (
                  <details className="text-sm">
                    <summary className="cursor-pointer">Editar condición y parámetros</summary>
                    <div className="mt-2 grid gap-2">
                      <Parameters value={rule.parameters as PolicyParameters} zones={document.zones}
                        metricAvailable={metricAvailable}
                        onChange={(parameters) => edit({ ...document, rules: document.rules.map((item, i) =>
                          i === index ? { ...item, parameters } : item) })} />
                      <Button type="button" variant="ghost" className="w-fit"
                        onClick={() => edit({ ...document, rules: document.rules.filter((_, i) => i !== index) })}>
                        Quitar regla
                      </Button>
                    </div>
                  </details>
                )}
                </div>
              ) : (
                <p key={rule.rule_id} className="break-words text-sm">
                  {label} · v{rule.version} ·{" "}
                  {rule.enabled ? "Habilitada" : "Deshabilitada"}
                </p>
              );
            })}
            {!document.rules.length && (
              <p className="text-sm">Sin reglas declaradas.</p>
            )}
            {canEdit && editableRules && document.zones.length > 0 && (
              <Button type="button" variant="outline" className="mt-2 w-fit"
                onClick={() => edit({ ...document, rules: [...document.rules, {
                  rule_id: "recording-" + crypto.randomUUID().slice(0, 8),
                  version: 1, enabled: false, parameters: newParameters("zone_dwell", document.zones[0].zone_id),
                }] })}>
                Añadir regla
              </Button>
            )}
          </fieldset>
          <fieldset disabled={!canEdit || locked}>
            <MotionConfiguration
              motion={document.motion}
              relations={document.relations}
              metricAvailable={metricAvailable}
              onMotion={(motion) => edit({ ...document, motion })}
              onRelations={(relations) => edit({ ...document, relations })}
            />
          </fieldset>
          {outdated && (
            <p role="alert" className="text-sm text-danger">
              Hay una revisión más reciente. Descarta este borrador para
              editarla.
            </p>
          )}
          {canEdit && (
            <div className="flex flex-wrap gap-2">
              <Button type="submit" disabled={!draft || locked || invalid}>
                Guardar configuración
              </Button>
              {draft && (
                <Button
                  variant="outline"
                  disabled={busy}
                  onClick={() => setDraft(undefined)}
                >
                  Descartar cambios
                </Button>
              )}
            </div>
          )}
          <ActionFeedback message={message} />
        </form>
      ) : (
        <p className="text-sm text-text-secondary">
          Configuración no disponible.
        </p>
      )}
    </section>
  );
}

function CameraDiagnostics({
  camera,
  stale,
  playbackFps,
}: {
  camera: LabCamera;
  stale: boolean;
  playbackFps: number | null;
}) {
  const rate = cameraAnalysisRate(camera.metrics);
  const received = cameraNumber(camera.metrics?.received_fps, " FPS");
  const paused = cameraObservationPaused(camera.status, stale);
  const coverage = paused ? null : cameraCoverage(camera.metrics);
  const discarded = cameraNumber(camera.metrics?.frames_dropped);
  const groups = cameraTechnicalMetrics(camera.metrics);
  const frameAge = cameraNumber(camera.metrics?.last_frame_age_ms, " ms");
  const latency = cameraNumber(camera.metrics?.p95_arrival_to_result_ms, " ms");
  const width = cameraNumber(camera.width);
  const height = cameraNumber(camera.height);
  const analysisTarget = cameraNumber(
    camera.configured_analysis_fps ?? camera.expected_fps,
    " FPS",
  );
  const sourceRate = cameraNumber(
    camera.configured_source_fps ?? camera.metrics?.source_fps,
    " FPS",
  );
  const hasReading =
    coverage !== null ||
    received !== null ||
    rate.value !== null ||
    groups.length > 0;

  return (
    <section
      className="grid gap-3"
      aria-labelledby="camera-diagnostics"
    >
      <h2 id="camera-diagnostics" className="font-semibold">
        Cobertura del análisis
      </h2>
      {stale ? (
        <p className="text-sm text-text-secondary">Datos sin actualizar.</p>
      ) : paused ? (
        <p className="text-sm text-text-secondary" role="status">
          Observación interrumpida. Al recuperar la señal comienza un nuevo
          tramo.
        </p>
      ) : hasReading && idle.has(camera.status) ? (
        <p className="text-sm text-text-secondary">
          Última lectura de la ejecución.
        </p>
      ) : null}
      <div className="analysis-telemetry">
        <MetricSummary label="Estadísticas de la cámara" metrics={[
          { label: "FPS de video", value: cameraNumber(playbackFps) },
          { label: "FPS de análisis", value: paused ? null : rate.value },
          { label: "Cobertura (5 s)", value: coverage },
          { label: "Latencia local p95", value: paused ? null : latency },
        ]} />
      </div>
      <details className="border-t border-border text-sm">
        <summary className="min-h-11 cursor-pointer py-3 font-medium text-primary">
          Detalles técnicos
        </summary>
        <div className="grid gap-4 pb-1">
          <p className="text-text-secondary">
            La cobertura indica qué proporción de los fotogramas decodificados se analizó.
            La latencia se mide desde la decodificación hasta el resultado.
          </p>
          <p className="text-text-secondary">Ritmo decodificado · {received ?? "Sin datos"} · Antigüedad al consultar · {frameAge ?? "Sin datos"}</p>
          {discarded !== null && discarded !== "0" && <p className="text-text-secondary">
            Descartes en la ejecución · {discarded}. Las reglas y los clips se limitan a tramos sin interrupciones.
          </p>}
          {groups.length === 0 && (
            <p className="text-text-secondary">
              Sin mediciones técnicas informadas.
            </p>
          )}
          {groups.map(({ title, rows }) => (
            <div key={title} className="grid gap-1">
              <h3 className="font-medium">{title}</h3>
              <dl className="divide-y divide-border">
                {rows.map(([label, value]) => (
                  <div
                    key={label}
                    className="flex justify-between gap-3 py-1.5"
                  >
                    <dt className="text-text-secondary">{label}</dt>
                    <dd className="shrink-0 text-right font-medium tabular-nums">
                      {value}
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
          <dl className="grid grid-cols-2 gap-3">
            <div>
              <dt className="text-text-secondary">Resolución esperada</dt>
              <dd className="font-medium tabular-nums">
                {width && height ? `${width} × ${height}` : "Sin datos"}
              </dd>
            </div>
            <div>
              <dt className="text-text-secondary">Objetivo de análisis</dt>
              <dd className="font-medium tabular-nums">
                {analysisTarget ?? "Sin datos"}
              </dd>
            </div>
            <div>
              <dt className="text-text-secondary">Ritmo de la fuente</dt>
              <dd className="font-medium tabular-nums">
                {sourceRate ?? "Sin datos"}
              </dd>
            </div>
          </dl>
        </div>
      </details>
    </section>
  );
}

export function CameraLabDetail({ id }: { id: string }) {
  const drawer = useRef<HTMLDialogElement>(null);
  const drawerTitle = useRef<HTMLHeadingElement>(null);
  const opener = useRef<HTMLElement | null>(null);
  const [panel, setPanel] = useState<"settings" | "calibration">();
  const [playbackFps, setPlaybackFps] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [calibrationBusy, setCalibrationBusy] = useState(false);
  const [draft, setDraft] = useState<CameraDraft>();
  const [stoppingRun, setStoppingRun] = useState<string>();
  const [action, setAction] = useState<{
    area: "monitor" | "configuration" | "calibration";
    message: Feedback;
  }>();
  const load = useCallback(
    (signal: AbortSignal) => cameraLabService.detail(id, signal),
    [id],
  );
  const catalog = useCameraData(cameraLabService.list, 15_000);
  const detail = useCameraData(
    load,
    2500,
    busy || calibrationBusy || !catalog.data?.enabled,
  );
  const camera = detail.data?.id === id ? detail.data : undefined;
  const automatic =
    camera?.automatic ??
    catalog.data?.cameras.find((item) => item.id === id)?.automatic ??
    catalog.data?.managed === true;
  const canEdit = catalog.data?.can_edit === true && !catalog.error;

  useEffect(() => {
    function openLinkedSettings() {
      if (!camera?.id || !canEdit) return;
      if (location.hash === "#camera-settings") setPanel("settings");
      if (location.hash === `#${calibrationSectionId}`) setPanel("calibration");
    }
    openLinkedSettings();
    addEventListener("hashchange", openLinkedSettings);
    return () => removeEventListener("hashchange", openLinkedSettings);
  }, [camera?.id, canEdit]);

  useEffect(() => {
    if (panel && drawer.current) {
      if (!drawer.current.open) drawer.current.showModal();
      drawer.current.scrollTop = 0;
      drawerTitle.current?.focus();
    }
  }, [panel]);

  function showPanel(next: "settings" | "calibration", trigger: HTMLElement) {
    if (!panel) opener.current = trigger;
    setPanel(next);
  }

  function closePanel() {
    if (busy || calibrationBusy) return;
    drawer.current?.close();
    setPanel(undefined);
    if (["#camera-settings", `#${calibrationSectionId}`].includes(location.hash)) {
      window.history.replaceState(window.history.state, "", location.pathname + location.search);
    }
    requestAnimationFrame(() => (opener.current ?? document.getElementById("camera-settings-trigger"))?.focus());
  }

  async function change(
    area: "monitor" | "configuration",
    operation: () => Promise<LabCamera>,
    success: string,
  ) {
    setBusy(true);
    setAction({ area, message: { text: "Enviando solicitud…" } });
    try {
      detail.setData(await operation());
      setAction({ area, message: { text: success } });
      return true;
    } catch (cause) {
      setAction({
        area,
        message: { text: operationalError(cause), error: true },
      });
      return false;
    } finally {
      setBusy(false);
    }
  }

  const error =
    catalog.error ?? (catalog.data?.enabled ? detail.error : undefined);
  const history = `/events?${new URLSearchParams({ camera_id: id })}`;
  const event = camera?.last_event;
  const submittedEvents = camera?.metrics?.events_submitted;
  const eventLimit = camera?.metrics?.event_limit;
  const eventQuotaReached = typeof submittedEvents === "number" && typeof eventLimit === "number" && eventLimit > 0 && submittedEvents >= eventLimit;
  const canStart = camera && idle.has(camera.status);
  const canStop = camera && monitoring.has(camera.status);
  const framing = camera?.metrics?.framing;
  const framingState =
    framing && typeof framing === "object" && "state" in framing
      ? framing.state
      : null;
  const mustRecalibrate = camera?.calibration_requires_reconfirmation === true;
  const lastRunInvalid =
    camera?.calibration_requires_reconfirmation == null &&
    framingState === "INVALID";
  const framingWarning = mustRecalibrate
    ? "El cambio de encuadre invalidó la calibración. Confirma una propuesta nueva antes de iniciar otro monitoreo."
    : lastRunInvalid
      ? "El último monitoreo detectó un cambio de encuadre. Revisa la calibración de esta cámara."
      : canStop &&
          camera?.configuration?.calibration &&
          framingState !== "VALID"
        ? "Medición en metros suspendida mientras se comprueba el encuadre."
        : undefined;
  const stopping = canStop && camera.run_id === stoppingRun;
  const preview =
    camera?.preview_url &&
    (!automatic ||
      (!cameraObservationPaused(camera.status, Boolean(error)) &&
        cameraFrameIsRecent(
          camera.last_frame_at,
          camera.metrics,
          detail.receivedAt,
        )))
      ? camera.preview_url
      : null;
  const eventTime = cameraFrameTime(event?.occurred_at);
  const provenance = [
    camera?.provenance?.title,
    camera?.provenance?.author,
    camera?.provenance?.license,
  ]
    .filter(
      (value) => typeof value === "string" && value && !value.includes("://"),
    )
    .join(" · ");
  return (
    <div className="sources-page page-v1 grid gap-5">
      <header className="app-page-heading">
        <div className="grid gap-2">
          <Link
            className="w-fit text-primary underline"
            href="/monitoring"
          >
            <ArrowLeft size={16} aria-hidden="true" className="inline" /> Centro de monitoreo
          </Link>
          <PageTitle>{camera?.name ?? "Cámara"}</PageTitle>
        </div>
        {camera && canEdit && <div className="flex flex-wrap gap-2">
          <Button variant="outline" onClick={(event) => showPanel("calibration", event.currentTarget)}>Calibrar distancias</Button>
          <Button id="camera-settings-trigger" variant="outline" onClick={(event) => showPanel("settings", event.currentTarget)}>
            <Settings2 size={16} aria-hidden="true" /> Ajustes de cámara
          </Button>
        </div>}
      </header>
      {error && (
        <LoadError
          error={error}
          retry={() => {
            catalog.retry();
            detail.retry();
          }}
        />
      )}
      {catalog.data?.enabled === false ? (
        <p className="surface-card p-4">El laboratorio está deshabilitado.</p>
      ) : !camera || !catalog.data ? (
        !error && (
          <OperixScanLoader variant="panel" message="Cargando cámara…" />
        )
      ) : (
        <>
          <div className={styles.workspace}>
            <section
              className="grid gap-3"
              aria-labelledby="camera-monitor"
            >
              <h2 id="camera-monitor" className="sr-only">
                Monitoreo
              </h2>
              <CameraMediaPanels
                onPlaybackFps={setPlaybackFps}
                camera={camera}
                live={automatic}
                preview={preview}
                refreshPreview={Boolean(canStop)}
                recentOnly={automatic}
                receivedAt={detail.receivedAt}
              />
              <details className="text-sm text-text-secondary">
                <summary className="min-h-11 cursor-pointer py-3 font-medium">Fuente, créditos y reglas de la sesión</summary>
                <div className="grid gap-2 pb-2">
                  {camera.description && <p>{camera.description}</p>}
                  {provenance && <p className="break-words">Procedencia · {provenance}</p>}
                  {camera.provenance?.filename && <p className="break-words">{camera.provenance.filename}
                    {typeof camera.playback?.position === "number" && ` · Video ${camera.playback.position + 1} de la lista`}
                    {camera.provenance.duration_s != null && ` · ${cameraNumber(camera.provenance.duration_s, " s")}`}
                    {camera.provenance.fps != null && ` · ${cameraNumber(camera.provenance.fps, " FPS de origen")}`}
                  </p>}
                  {camera.provenance?.scenario && <p className="break-words">{camera.provenance.scenario}</p>}
                  {camera.effective_rules && (
                    <RuleConfiguration snapshot={{ rules: camera.effective_rules }} equipmentContext={
                      Array.isArray(camera.metrics?.equipment_rule_scope) ? {
                        taxonomy: { category: "UNKNOWN", subtype: "UNKNOWN" },
                        rule_scope: camera.metrics.equipment_rule_scope,
                      } : undefined
                    } />
                  )}
                </div>
              </details>
            </section>
            <aside aria-label="Estado y actividad de la cámara" className="surface-card grid min-w-0 gap-3 p-4">
              <div className="flex flex-wrap items-center gap-3">
                <p role="status" className="font-medium">
                  Conexión ·{" "}
                  {error ? "Estado sin actualizar" : statusLabel(camera.status)}
                  {camera.view_only && " · Solo video"}
                </p>
                {canEdit && !automatic && (canStart || canStop) && (
                  <Button
                    disabled={
                      busy ||
                      calibrationBusy ||
                      stopping ||
                      Boolean(error) ||
                      Boolean(canStart && mustRecalibrate)
                    }
                    variant={canStop ? "outline" : "primary"}
                    onClick={async () => {
                      const completed = await change(
                        "monitor",
                        () =>
                          cameraLabService.monitor(
                            id,
                            canStop ? "stop" : "start",
                          ),
                        canStop
                          ? "Solicitud de detención enviada."
                          : "Solicitud de inicio enviada.",
                      );
                      if (completed)
                        setStoppingRun(
                          canStop ? (camera.run_id ?? undefined) : undefined,
                        );
                    }}
                  >
                    {stopping
                      ? "Detención solicitada"
                      : canStop
                        ? "Detener monitoreo"
                        : "Iniciar monitoreo"}
                  </Button>
                )}
              </div>

              <p className="text-sm text-text-secondary">
                Calibración · {framingState === "VALID" && !framingWarning ? "Encuadre validado" :
                  framingWarning ? "Requiere revisión" : camera.configuration?.calibration ? "A la espera de verificación" : "Distancia normalizada"}
              </p>
              {framingWarning && (
                <div className="inline-message grid gap-2" role="status">
                  <p>{framingWarning}</p>
                  {(mustRecalibrate || lastRunInvalid) && canEdit && (
                    <a className="w-fit text-primary underline"
                      href={`#${calibrationSectionId}`}
                      onClick={(event) => {
                        event.preventDefault();
                        showPanel("calibration", event.currentTarget);
                      }}
                    >
                      Abrir calibración con patrón
                    </a>
                  )}
                </div>
              )}
              {camera.status === "error" && (
                <p role="alert" className="text-sm text-danger">
                  {camera.last_error ??
                    (automatic
                      ? "El monitoreo automático se interrumpió."
                      : "El monitoreo se interrumpió. Revisa la fuente e inicia otra ejecución.")}
                </p>
              )}
              <ActionFeedback
                message={
                  !automatic && action?.area === "monitor"
                    ? action.message
                    : undefined
                }
              />

            <CameraDiagnostics
              key={camera.run_id}
              camera={camera}
              stale={Boolean(error)}
              playbackFps={playbackFps}
            />
            <section
              className="grid gap-2 border-t border-border pt-3"
              aria-labelledby="camera-events"
            >
              <h2 id="camera-events" className="font-semibold">
                Eventos de la cámara
              </h2>
              {canStop && eventQuotaReached && (
                <p className="text-sm text-text-secondary">
                  Se alcanzó el límite de publicación de esta sesión. El
                  monitoreo sigue activo.
                </p>
              )}
              {event?.id ? (
                <p className="text-sm">
                  Último registro{" "}
                  <Link
                    className="text-primary underline"
                    href={`/events/${encodeURIComponent(event.id)}?${new URLSearchParams({ back: history })}`}
                  >
                    {eventTypeName(event.event_type)}
                  </Link>
                  {eventTime && (
                    <>
                      {" "}
                      · <time dateTime={event.occurred_at}>{eventTime}</time>
                    </>
                  )}
                </p>
              ) : (
                <p className="text-sm text-text-secondary">
                  No se informa un último evento.
                </p>
              )}
              <Link className="w-fit text-primary underline" href={history}>
                Ver historial de esta cámara
              </Link>
            </section>
            </aside>
          </div>
          {panel && canEdit && <dialog ref={drawer} id="camera-settings" className={`operix-drawer ${styles.drawer}`}
            aria-labelledby="camera-drawer-title" onCancel={(event) => {
              event.preventDefault();
              closePanel();
            }}>
            <header className={styles.drawerHeading}>
              <div>
                <h2 ref={drawerTitle} tabIndex={-1} id="camera-drawer-title">
                  {panel === "calibration" ? "Calibrar distancias" : "Ajustes de cámara"}
                </h2>
                <p className="text-sm text-text-secondary">{camera.name}</p>
              </div>
              <Button size="icon" variant="ghost" aria-label="Cerrar panel" disabled={busy || calibrationBusy} onClick={closePanel}>
                <X size={19} aria-hidden="true" />
              </Button>
            </header>
            <div className={styles.drawerBody}>
          {panel === "settings" && (
            <Button variant="outline" className="w-fit" onClick={(event) => showPanel("calibration", event.currentTarget)}>
              Calibrar distancias
            </Button>
          )}
          {panel === "calibration" ? (
            <div className="grid min-w-0 gap-2 ">
              <AutomaticCalibration<LabCamera>
                standalone
                id={calibrationSectionId}
                key={`${camera.id}:${camera.revision}:${camera.provenance?.sha256 ?? ""}`}
                source={{
                  kind: "cameras",
                  id: camera.id,
                  revision: camera.revision,
                }}
                zones={camera.configuration?.zones ?? []}
                saved={camera.configuration?.calibration}
                reuseSavedReferences={!mustRecalibrate}
                framingWarning={framingWarning}
                blocked={
                  !canEdit
                    ? "Solo los usuarios con permiso de edición pueden calibrar esta cámara."
                    : busy
                        ? "Espera a que se actualice el estado de la cámara."
                        : draft
                          ? "Guarda o descarta el borrador de configuración antes de capturar una propuesta."
                          : undefined
                }
                onBusyChange={setCalibrationBusy}
                onSaved={(result) => {
                  detail.setData(result);
                  setAction({
                    area: "calibration",
                    message: {
                      text: "Calibración guardada. La siguiente ejecución compatible usará esta revisión.",
                    },
                  });
                }}
                onRefresh={detail.retry}
              />
              <ActionFeedback
                message={
                  action?.area === "calibration" ? action.message : undefined
                }
              />
            </div>
          ) : <Configuration
            camera={camera}
            canEdit={canEdit}
            canConfigure={Boolean(canStart)}
            busy={busy || calibrationBusy || Boolean(error)}
            draft={draft}
            setDraft={setDraft}
            metricAvailable={
              !framingWarning &&
              camera.configuration?.calibration?.status === "valid" &&
              camera.configuration.calibration.zones_reviewed === true
            }
            message={
              action?.area === "configuration" ? action.message : undefined
            }
            onSave={(revision, document) =>
              change(
                "configuration",
                () => cameraLabService.save(id, revision, document),
                "Configuración guardada.",
              )
            }
          />}
            <Button variant="outline" className="w-fit" disabled={busy || calibrationBusy} onClick={closePanel}>Volver al monitoreo</Button>
            </div>
          </dialog>}
        </>
      )}
    </div>
  );
}
