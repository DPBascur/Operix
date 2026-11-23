"use client";

import type { NormalizedVertex } from "@/services/analysis.service";
import { MotionConfiguration } from "@/features/analysis/motion-configuration";
import { AutomaticCalibration } from "@/features/calibration/automatic-calibration";

import { ArrowRight, Camera } from "lucide-react";
import Link from "next/link";
import { useCallback, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { PageTitle } from "@/components/layout/page-title";
import { operationalError } from "@/features/operations/operation-request";
import { eventTypeName } from "@/services/event-contract";
import {
  cameraLabService,
  type CameraDocument,
  type LabCamera,
} from "@/services/camera-lab.service";
import {
  cameraAnalysisRate,
  cameraCoverage,
  cameraObservationPaused,
  cameraFrameTime,
  cameraNumber,
  cameraTechnicalMetrics,
} from "./camera-diagnostics";
import {
  CameraCard,
  CameraPreview,
  LoadError,
  statusLabel,
  useCameraData,
} from "./camera-overview";

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

export function CameraLab() {
  const { data, error, receivedAt, retry } = useCameraData(
    cameraLabService.list,
    5000,
  );
  const max = cameraNumber(data?.capacity);
  return (
    <section
      id="laboratorio-camaras"
      className="source-section"
      aria-labelledby="camera-source-title"
    >
      <div className="section-intro">
        <div>
          <h2 id="camera-source-title">Cámaras virtuales</h2>
          <p className="text-text-secondary">
            Monitoreo y fotogramas recientes del laboratorio de cámaras.
          </p>
        </div>
      </div>
      {error && <LoadError error={error} retry={retry} />}
      {!data && !error && (
        <OperixScanLoader variant="panel" message="Cargando cámaras…" />
      )}
      {data && !data.enabled && (
        <p className="surface-card p-4">El laboratorio está deshabilitado.</p>
      )}
      {data?.enabled && (
        <div className="grid gap-3">
          {max !== null && (
            <p className="text-sm text-text-secondary">
              Límite de monitoreos simultáneos · {max}
            </p>
          )}
          {data.cameras.length ? (
            <ul className="grid gap-4 md:grid-cols-2">
              {data.cameras.map((camera) => (
                <li
                  key={camera.id}
                  className="surface-card grid min-w-0 content-start gap-3 p-4"
                >
                  <CameraCard
                    key={camera.run_id}
                    camera={camera}
                    receivedAt={receivedAt}
                    stale={Boolean(error)}
                  />
                  {(camera.automatic ?? data.managed) && (
                    <p className="text-sm text-text-secondary">
                      Monitoreo automático
                    </p>
                  )}
                  <Link
                    className="button button-outline w-fit"
                    href={`/sources/cameras/${encodeURIComponent(camera.id)}`}
                    aria-label={`Abrir cámara ${camera.name}`}
                  >
                    Abrir cámara <ArrowRight aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p className="surface-card p-4">Aún no hay cámaras configuradas.</p>
          )}
        </div>
      )}
    </section>
  );
}

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

type CameraDraft = { revision: number; document: CameraDocument };

function Configuration({
  camera,
  canEdit,
  canConfigure,
  busy,
  draft,
  metricAvailable,
  message,
  onSave,
  setDraft,
}: {
  camera: LabCamera;
  canEdit: boolean;
  canConfigure: boolean;
  busy: boolean;
  draft?: CameraDraft;
  metricAvailable: boolean;
  message?: Feedback;
  onSave: (revision: number, document: CameraDocument) => Promise<boolean>;
  setDraft: (draft: CameraDraft | undefined) => void;
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
          Configuración de la cámara
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
                <label
                  key={rule.rule_id}
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
}: {
  camera: LabCamera;
  stale: boolean;
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
  const expected = cameraNumber(camera.expected_fps, " FPS");
  const hasReading =
    coverage !== null ||
    received !== null ||
    rate.value !== null ||
    groups.length > 0;

  return (
    <section
      className="surface-card grid gap-3 p-4"
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
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <div>
          <dt className="text-sm text-text-secondary">Ritmo decodificado</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {received ?? "Sin datos"}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-text-secondary">
            Fotogramas observados (5 s)
          </dt>
          <dd className="text-lg font-semibold tabular-nums">
            {paused ? "No disponible" : (coverage ?? "Sin datos")}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-text-secondary">{rate.label}</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {rate.value ?? "Sin datos"}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-text-secondary">Latencia local p95</dt>
          <dd className="text-lg font-semibold tabular-nums">
            {latency ?? "Sin datos"}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-text-secondary">
            Antigüedad al actualizar
          </dt>
          <dd className="text-lg font-semibold tabular-nums">
            {frameAge ?? "Sin datos"}
          </dd>
        </div>
      </dl>
      <p className="text-sm text-text-secondary">
        La cobertura indica qué proporción de los fotogramas decodificados se
        analizó.
      </p>
      {discarded !== null && discarded !== "0" && (
        <p className="text-sm text-text-secondary">
          Descartes en la ejecución · {discarded}. Las reglas temporales y los
          clips se limitan a tramos observados sin interrupciones.
        </p>
      )}
      <details className="border-t border-border text-sm">
        <summary className="min-h-11 cursor-pointer py-3 font-medium text-primary">
          Detalles técnicos
        </summary>
        <div className="grid gap-4 pb-1">
          <p className="text-text-secondary">
            Los tiempos desde la recepción se miden localmente a partir de la
            decodificación.
          </p>
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
              <dt className="text-text-secondary">Velocidad esperada</dt>
              <dd className="font-medium tabular-nums">
                {expected ?? "Sin datos"}
              </dd>
            </div>
          </dl>
        </div>
      </details>
    </section>
  );
}

export function CameraLabDetail({ id }: { id: string }) {
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
  const camera = detail.data;
  const automatic =
    camera?.automatic ??
    catalog.data?.cameras.find((item) => item.id === id)?.automatic ??
    catalog.data?.managed === true;
  const canEdit = catalog.data?.can_edit === true && !catalog.error;

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
  const eventQuotaReached = typeof submittedEvents === "number" &&
    typeof eventLimit === "number" && eventLimit > 0 && submittedEvents >= eventLimit;
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
  const frameTime = cameraFrameTime(camera?.last_frame_at);
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
            href="/sources#laboratorio-camaras"
          >
            Volver al laboratorio de cámaras
          </Link>
          <PageTitle>{camera?.name ?? "Cámara de laboratorio"}</PageTitle>
          {camera?.description && <p>{camera.description}</p>}
        </div>
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
        <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
          {(canEdit || camera.configuration?.calibration) && (
            <div className="grid min-w-0 gap-2 lg:col-span-2">
              <AutomaticCalibration<LabCamera>
                id={calibrationSectionId}
                key={`${camera.id}:${camera.revision}:${canStart}`}
                source={{
                  kind: "cameras",
                  id: camera.id,
                  revision: camera.revision,
                }}
                zones={camera.configuration?.zones ?? []}
                saved={camera.configuration?.calibration}
                framingWarning={framingWarning}
                blocked={
                  !canEdit
                    ? "Solo los usuarios con permiso de edición pueden calibrar esta cámara."
                    : !canStart
                      ? "Detén el monitoreo para capturar y validar una propuesta."
                      : busy || error
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
                      text: "Calibración con patrón guardada para esta cámara.",
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
          )}
          <div className="grid min-w-0 gap-4">
            <section
              className="surface-card grid gap-3 p-4"
              aria-labelledby="camera-monitor"
            >
              <h2 id="camera-monitor" className="font-semibold">
                Monitoreo
              </h2>
              <div className="flex flex-wrap items-center gap-3">
                <p role="status" className="font-medium">
                  Conexión ·{" "}
                  {error ? "Estado sin actualizar" : statusLabel(camera.status)}
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
              {automatic && (
                <p className="text-sm text-text-secondary">
                  Monitoreo automático gestionado por el laboratorio.
                </p>
              )}
              {framingWarning && (
                <div className="inline-message grid gap-2" role="status">
                  <p>{framingWarning}</p>
                  {(mustRecalibrate || lastRunInvalid) && canEdit && (
                    <a
                      className="w-fit text-primary underline"
                      href={`#${calibrationSectionId}`}
                      onClick={() => {
                        const panel =
                          document.getElementById(calibrationSectionId);
                        if (panel instanceof HTMLDetailsElement) {
                          panel.open = true;
                          panel
                            .querySelector("summary")
                            ?.focus({ preventScroll: true });
                        }
                      }}
                    >
                      Abrir calibración con patrón
                    </a>
                  )}
                </div>
              )}
              {frameTime && camera.last_frame_at && (
                <p className="text-sm text-text-secondary">
                  Recepción local del último fotograma analizado ·{" "}
                  <time dateTime={camera.last_frame_at}>{frameTime}</time>
                </p>
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
              <figure className="grid gap-2">
                <figcaption className="text-sm font-medium">
                  Último fotograma analizado · captura estática
                </figcaption>
                {camera.preview_url ? (
                  <CameraPreview
                    key={`${camera.run_id}:${camera.preview_url}`}
                    id={id}
                    url={camera.preview_url}
                    active={Boolean(canStop)}
                  />
                ) : (
                  <div className="flex min-h-32 items-center justify-center gap-2 rounded-md bg-surface-muted p-3 text-center text-sm text-text-secondary">
                    <Camera className="size-5 shrink-0" aria-hidden="true" />
                    Aún no hay un fotograma disponible.
                  </div>
                )}
              </figure>
              {provenance && (
                <p className="break-words text-sm text-text-secondary">
                  Procedencia · {provenance}
                </p>
              )}
              {camera.automatic && camera.provenance?.filename && (
                <p className="break-words text-sm text-text-secondary">
                  Grabación en bucle · {camera.provenance.filename}
                  {camera.provenance.footage === "real recorded logistics trial" &&
                    " · ensayo logístico grabado"}
                  {camera.provenance.duration_s != null &&
                    ` · ${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 }).format(camera.provenance.duration_s)} s`}
                  {camera.provenance.fps != null &&
                    ` · ${new Intl.NumberFormat("es-CL", { maximumFractionDigits: 1 }).format(camera.provenance.fps)} FPS de origen`}
                </p>
              )}
              {camera.provenance?.scenario && (
                <p className="break-words text-sm text-text-secondary">
                  {camera.provenance.scenario}
                </p>
              )}
              {camera.effective_rules && (
                <details className="text-sm text-text-secondary">
                  <summary className="cursor-pointer font-medium">Reglas de esta sesión</summary>
                  <ul className="mt-2 grid gap-1">
                    {camera.effective_rules.map((rule) => (
                      <li key={rule.rule_id} className="break-words">
                        {eventTypeName(String(rule.parameters.kind ?? ""))} · {rule.rule_id} · v{rule.version}
                        {!rule.enabled && " · deshabilitada"}
                      </li>
                    ))}
                  </ul>
                </details>
              )}
            </section>
            <CameraDiagnostics
              key={camera.run_id}
              camera={camera}
              stale={Boolean(error)}
            />
            <section
              className="surface-card grid gap-2 p-4"
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
          </div>
          <Configuration
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
          />
        </div>
      )}
    </div>
  );
}
