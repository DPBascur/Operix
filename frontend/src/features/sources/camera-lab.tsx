"use client";

import type { NormalizedVertex } from "@/services/analysis.service";
import { MotionConfiguration } from "@/features/analysis/motion-configuration";

import { ArrowRight, Camera } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { PageTitle } from "@/components/layout/page-title";
import { operationalError } from "@/features/operations/operation-request";
import { eventTypeName } from "@/services/event-contract";
import {
  cameraLabService,
  CameraRequestError,
  type CameraDocument,
  type LabCamera,
} from "@/services/camera-lab.service";

const statusLabels: Record<string, string> = {
  available: "Disponible",
  connecting: "Conectando",
  transmitting: "Transmitiendo",
  analyzing: "Analizando",
  no_signal: "Sin señal",
  reconnecting: "Reconectando",
  stopped: "Detenida",
  error: "Error",
};
const idle = new Set(["available", "stopped", "error"]);
const monitoring = new Set([
  "connecting",
  "transmitting",
  "analyzing",
  "no_signal",
  "reconnecting",
]);

function statusLabel(status: string) {
  return statusLabels[status] ?? "Estado desconocido";
}

function useCameraData<T>(
  load: (signal: AbortSignal) => Promise<T>,
  interval: number,
  paused = false,
) {
  const [data, setData] = useState<T>();
  const [error, setError] = useState<Error>();
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (paused) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const result = await load(controller.signal);
        if (controller.signal.aborted) return;
        setData(result);
        setError(undefined);
      } catch (cause) {
        if (controller.signal.aborted) return;
        if (
          cause instanceof CameraRequestError &&
          [401, 403, 404].includes(cause.status)
        ) {
          setData(undefined);
          setError(cause);
          return;
        }
        setError(new Error(operationalError(cause)));
      }
      timer = setTimeout(refresh, interval);
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [load, interval, paused, attempt]);

  return { data, setData, error, retry: () => setAttempt((n) => n + 1) };
}

function LoadError({ error, retry }: { error: Error; retry: () => void }) {
  const forbidden = error instanceof CameraRequestError && error.status === 403;
  return (
    <div className="inline-message is-error flex flex-wrap items-center gap-3">
      <p role="alert">{error.message}</p>
      {!forbidden && (
        <Button variant="outline" onClick={retry}>
          Reintentar consulta
        </Button>
      )}
    </div>
  );
}

function number(value: unknown) {
  return typeof value === "number" && Number.isFinite(value)
    ? new Intl.NumberFormat("es-CL", { maximumFractionDigits: 2 }).format(value)
    : null;
}

export function CameraLab() {
  const { data, error, retry } = useCameraData(cameraLabService.list, 5000);
  const max = number(data?.capacity);
  return (
    <section
      id="laboratorio-camaras"
      className="source-section"
      aria-labelledby="camera-source-title"
    >
      <div className="section-intro">
        <div>
          <h2 id="camera-source-title">Laboratorio de cámaras</h2>
          <p className="text-text-secondary">
            Monitoreo y revisión de cámaras configuradas para el laboratorio.
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
        <div className="surface-card grid gap-3 p-4">
          {max !== null && (
            <p className="text-sm text-text-secondary">
              Capacidad máxima de monitoreo simultáneo · {max}
            </p>
          )}
          {data.cameras.length ? (
            <ul className="divide-y divide-border">
              {data.cameras.map((camera) => (
                <li
                  key={camera.id}
                  className="flex flex-wrap items-center justify-between gap-2 py-3"
                >
                  <div className="min-w-0 break-words">
                    <h3 className="font-semibold">{camera.name}</h3>
                    <p className="text-sm text-text-secondary">
                      {error
                        ? "Estado sin actualizar"
                        : statusLabel(camera.status)}
                    </p>
                  </div>
                  <Link
                    className="button button-outline"
                    href={`/sources/cameras/${encodeURIComponent(camera.id)}`}
                    aria-label={`Abrir cámara ${camera.name}`}
                  >
                    Abrir cámara <ArrowRight aria-hidden="true" />
                  </Link>
                </li>
              ))}
            </ul>
          ) : (
            <p>Aún no hay cámaras configuradas.</p>
          )}
        </div>
      )}
    </section>
  );
}

function CameraPreview({
  id,
  url,
  active,
}: {
  id: string;
  url: string;
  active: boolean;
}) {
  const [frame, setFrame] = useState<string>();
  const [unavailable, setUnavailable] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    async function refresh() {
      try {
        const blob = await cameraLabService.preview(id, url, controller.signal);
        if (controller.signal.aborted) return;
        setFrame(URL.createObjectURL(blob));
        setUnavailable(false);
      } catch (error) {
        if (controller.signal.aborted) return;
        setUnavailable(true);
        if (
          error instanceof CameraRequestError &&
          [401, 403].includes(error.status)
        ) {
          setFrame(undefined);
          return;
        }
      }
      if (active) timer = setTimeout(refresh, 2500);
    }
    void refresh();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [id, url, active]);
  useEffect(
    () => () => {
      if (frame) URL.revokeObjectURL(frame);
    },
    [frame],
  );

  return (
    <>
      <div className="grid aspect-video place-items-center overflow-hidden rounded-md bg-surface-muted">
        {frame ? (
          // eslint-disable-next-line @next/next/no-img-element -- authenticated JPEG as a blob URL
          <img
            src={frame}
            alt="Último fotograma analizado de la cámara seleccionada"
            className="size-full object-contain"
          />
        ) : (
          <p className="p-4 text-center text-sm text-text-secondary">
            {unavailable
              ? "No hay un fotograma disponible."
              : "Cargando fotograma…"}
          </p>
        )}
      </div>
      {unavailable && frame && (
        <p className="text-sm text-text-secondary">
          No se pudo actualizar el fotograma.
        </p>
      )}
    </>
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

function Configuration({
  camera,
  canEdit,
  canConfigure,
  busy,
  message,
  onSave,
}: {
  camera: LabCamera;
  canEdit: boolean;
  canConfigure: boolean;
  busy: boolean;
  message?: Feedback;
  onSave: (revision: number, document: CameraDocument) => Promise<boolean>;
}) {
  const [draft, setDraft] = useState<{
    revision: number;
    document: CameraDocument;
  }>();
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
              metricAvailable={false}
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

export function CameraLabDetail({ id }: { id: string }) {
  const [busy, setBusy] = useState(false);
  const [stoppingRun, setStoppingRun] = useState<string>();
  const [action, setAction] = useState<{
    area: "monitor" | "configuration";
    message: Feedback;
  }>();
  const load = useCallback(
    (signal: AbortSignal) => cameraLabService.detail(id, signal),
    [id],
  );
  const catalog = useCameraData(cameraLabService.list, 15_000);
  const detail = useCameraData(load, 2500, busy || !catalog.data?.enabled);
  const camera = detail.data;
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
  const canStart = camera && idle.has(camera.status);
  const canStop = camera && monitoring.has(camera.status);
  const stopping = canStop && camera.run_id === stoppingRun;
  const fps = number(camera?.expected_fps);
  const width = number(camera?.width);
  const height = number(camera?.height);
  const metrics = [
    ["Recepción", number(camera?.metrics?.received_fps), " FPS"],
    [
      "Velocidad de análisis",
      number(camera?.metrics?.analysis_fps ?? camera?.metrics?.effective_fps),
      " FPS",
    ],
    [
      "Latencia local p95",
      number(camera?.metrics?.p95_arrival_to_result_ms),
      " ms",
    ],
    ["Fotogramas descartados", number(camera?.metrics?.frames_dropped), ""],
    ["Fotogramas analizados", number(camera?.metrics?.frames_processed), ""],
    ["Eventos publicados", number(camera?.metrics?.events_published), ""],
  ];
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
                  {error ? "Estado sin actualizar" : statusLabel(camera.status)}
                </p>
                {canEdit && (canStart || canStop) && (
                  <Button
                    disabled={busy || stopping || Boolean(error)}
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
              {camera.last_frame_at && (
                <p className="text-sm text-text-secondary">
                  Última recepción ·{" "}
                  {new Date(camera.last_frame_at).toLocaleTimeString("es-CL", {
                    timeZone: "America/Santiago",
                  })}
                </p>
              )}
              {camera.status === "error" && (
                <p role="alert" className="text-sm text-danger">
                  {camera.last_error ??
                    "El monitoreo se interrumpió. Revisa la fuente e inicia otra ejecución."}
                </p>
              )}
              <ActionFeedback
                message={
                  action?.area === "monitor" ? action.message : undefined
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
              <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
                {[
                  [
                    "Resolución esperada",
                    width && height ? `${width} × ${height}` : null,
                    "",
                  ],
                  ["Velocidad esperada", fps, " FPS"],
                  ...metrics.filter(([, value]) => value !== null),
                ].map(([label, value, unit]) => (
                  <div key={label}>
                    <dt className="text-text-secondary">{label}</dt>
                    <dd className="font-medium tabular-nums">
                      {value === null ? "No informada" : `${value}${unit}`}
                    </dd>
                  </div>
                ))}
              </dl>
              {provenance && (
                <p className="break-words text-sm text-text-secondary">
                  Procedencia · {provenance}
                </p>
              )}
            </section>
            <section
              className="surface-card grid gap-2 p-4"
              aria-labelledby="camera-events"
            >
              <h2 id="camera-events" className="font-semibold">
                Eventos de la cámara
              </h2>
              {event?.id ? (
                <p className="text-sm">
                  Último registro{" "}
                  <Link
                    className="text-primary underline"
                    href={`/events/${encodeURIComponent(event.id)}?${new URLSearchParams({ back: history })}`}
                  >
                    {eventTypeName(event.event_type)}
                  </Link>
                  {Number.isFinite(Date.parse(event.occurred_at)) && (
                    <>
                      {" "}
                      ·{" "}
                      <time dateTime={event.occurred_at}>
                        {new Date(event.occurred_at).toLocaleString("es-CL")}
                      </time>
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
            busy={busy || Boolean(error)}
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
