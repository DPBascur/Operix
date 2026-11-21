"use client";

import { useEffect, useId, useRef, useState } from "react";
import { ChevronDown, Waypoints } from "lucide-react";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/services/browser-session";
import {
  analysisService,
  AnalysisRequestError,
  type AnalysisSessionStatus,
  type MotionSettings,
  type RelationSettings,
} from "@/services/analysis.service";
import { environment } from "@/config/environment";
import { AutomaticCalibration } from "@/features/calibration/automatic-calibration";

import { MotionConfiguration } from "./motion-configuration";
import { RuleConfiguration } from "./rule-configuration";
import {
  CalibrationGuide,
  calibrationCheck,
  type Calibration,
} from "./calibration-guide";
import { SpatialFrame } from "./spatial-frame";
import { analysisError } from "./analysis-feedback";
import {
  pointInFrame,
  removeVertex,
  validPolygon,
} from "./zone-editor-geometry";
import styles from "./analysis.module.css";

type Point = [number, number];
type Zone = {
  zone_id: string;
  name: string;
  polygon: Point[];
  purpose?: string;
  enabled?: boolean;
};
type Rule = {
  rule_id: string;
  version: number;
  enabled: boolean;
  parameters: Record<string, string | number | boolean>;
};
type Document = {
  schema_version: number;
  view_id: string;
  coordinate_system: string;
  zones: Zone[];
  rules: Rule[];
  calibration?: Calibration;
  motion?: MotionSettings;
  relations?: RelationSettings;
};
type Loaded = {
  document: Document;
  saved: Document | null;
  revision: number;
  effective_rules?: Rule[];
  policy?: { rule_set: { name: string; version: number } } | null;
};
type SavedConfiguration = Pick<Loaded, "document" | "revision">;
const purposes = {
  observation: "Observación",
  restricted: "Área restringida",
  equipment: "Circulación de equipos",
  dwell: "Permanencia controlada",
  proximity: "Área de proximidad",
};
const kinds = {
  zone_dwell: "Permanencia",
  zone_entry: "Ingreso observado",
  person_forklift_proximity: "Proximidad",
  zone_coexistence: "Presencia simultánea",
};

const tasks = [
  "Escenario",
  "Zonas",
  "Calibración",
  "Reglas",
  "Revisar configuración",
] as const;

export function SpatialEditor({
  session,
  onSaved,
  onEditingChange,
  onDirtyChange,
  unavailable,
  autoOpen,
  onAutoOpen,
}: {
  session: AnalysisSessionStatus;
  onSaved: (s: AnalysisSessionStatus) => void;
  onEditingChange: (editing: boolean) => void;
  onDirtyChange: (dirty: boolean) => void;
  unavailable: boolean;
  autoOpen: boolean;
  onAutoOpen: () => void;
}) {
  const [data, setData] = useState<Loaded | null>(null);
  const panelId = useId();
  const trigger = useRef<HTMLButtonElement>(null);
  const [dirty, setDirty] = useState(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [calibrationBusy, setCalibrationBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [task, setTask] = useState(0);
  const [message, setMessage] = useState("");
  const [selected, setSelected] = useState(0);
  const [vertex, setVertex] = useState<number | null>(null);
  const [undo, setUndo] = useState<Point[][]>([]);
  const drag = useRef<number | null>(null);
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const [initial, setInitial] = useState<Document | null>(null);
  const [editorRevision, setEditorRevision] = useState(0);

  useEffect(() => {
    onEditingChange(open);
    return () => onEditingChange(false);
  }, [open, onEditingChange]);
  useEffect(() => {
    onDirtyChange(dirty);
    return () => onDirtyChange(false);
  }, [dirty, onDirtyChange]);

  const mounted = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const base = environment.apiBaseUrl?.replace(/\/$/, "") ?? "/api/v1";
  const url = `${base}/analysis/sessions/${session.id}/configuration/`;
  async function request(method: string, body?: unknown) {
    const response = await apiFetch(url, {
      method,
      headers: { "Content-Type": "application/json" },
      body: body ? JSON.stringify(body) : undefined,
      signal: AbortSignal.timeout(30000),
    });
    const value = await response.json().catch(() => null);
    if (!response.ok || !value)
      throw new AnalysisRequestError(
        value?.detail ?? "El servicio no devolvió la configuración.",
        response.status,
      );
    return value;
  }
  function update(next: Document) {
    if (data) {
      if (
        next.calibration &&
        next.calibration.status === "valid" &&
        (JSON.stringify(next.calibration.image_points) !==
          JSON.stringify(data.document.calibration?.image_points) ||
          JSON.stringify(next.calibration.ground_points_m) !==
            JSON.stringify(data.document.calibration?.ground_points_m) ||
          JSON.stringify(next.zones) !== JSON.stringify(data.document.zones))
      )
        next = {
          ...next,
          calibration: { ...next.calibration, zones_reviewed: false },
        };
      if (
        next.motion &&
        (next.calibration?.status === "invalid" ||
          JSON.stringify(next.calibration?.image_points) !==
            JSON.stringify(data.document.calibration?.image_points) ||
          JSON.stringify(next.calibration?.ground_points_m) !==
            JSON.stringify(data.document.calibration?.ground_points_m))
      ) {
        next = {
          ...next,
          motion: { ...next.motion, camera_fixed_confirmed: false },
        };
      }
      setData({ ...data, document: next });
      setDirty(true);
    }
  }
  const doc = data?.document;
  const zone = doc?.zones[selected];
  const originalZone = initial?.zones.find((z) => z.zone_id === zone?.zone_id);
  const locked = busy || calibrationBusy || unavailable || loading;
  const zonesProblem =
    doc &&
    (!doc.zones.length
      ? "Crea al menos una zona."
      : doc.zones.some((z) => !validPolygon(z.polygon))
        ? "Revisa las zonas. Cada polígono necesita al menos tres vértices y no puede cruzarse."
        : null);
  const problem =
    zonesProblem ??
    (doc?.calibration && calibrationCheck(doc.calibration)) ??
    ((doc?.rules.some((r) => r.enabled && r.parameters.distance_unit === "m") ||
      doc?.motion?.unit === "m") &&
    !doc.calibration
      ? "Revisa las reglas y el movimiento en metros o calibra esta fuente."
      : null);

  function changePolygon(polygon: Point[], remember = true) {
    if (!doc || !zone || locked) return;
    if (remember) setUndo((history) => [...history.slice(-31), zone.polygon]);
    update({
      ...doc,
      zones: doc.zones.map((z, i) => (i === selected ? { ...z, polygon } : z)),
    });
  }

  async function load() {
    setLoading(true);
    setMessage("");
    try {
      const loaded: Loaded = await request("GET");
      if (!mounted.current) return;
      setInitial(loaded.document);
      setData(loaded);
    } catch (cause) {
      if (mounted.current)
        setMessage(
          analysisError(
            cause,
            "No se pudo cargar la configuración. Reintenta.",
          ),
        );
    } finally {
      if (mounted.current) setLoading(false);
    }
  }

  // Abrir desde un enlace usa el mismo panel y no reemplaza la sesión.
  useEffect(() => {
    if (!autoOpen || unavailable) return;
    const frame = requestAnimationFrame(() => {
      if (trigger.current?.getAttribute("aria-expanded") === "false") {
        trigger.current.focus();
        trigger.current.click();
      }
      onAutoOpen();
    });
    return () => cancelAnimationFrame(frame);
  }, [autoOpen, unavailable, onAutoOpen]);

  function chooseTask(next: number, focus = false) {
    if (calibrationBusy) return;
    setTask(next);
    if (focus) tabs.current[next]?.focus();
  }

  function replaceDraft(document: Document, nextDirty: boolean) {
    setData((current) => current && { ...current, document });
    setDirty(nextDirty);
    setSelected(0);
    setVertex(null);
    setUndo([]);
    setEditorRevision((value) => value + 1);
  }

  async function save() {
    if (!doc || !data || problem || locked) return;
    setBusy(true);
    setMessage("");
    try {
      const result: SavedConfiguration = await request("PUT", {
        document: doc,
        revision: data.revision,
      });
      await applySaved(
        result,
        "Configuración guardada para el próximo análisis.",
      );
    } catch (cause) {
      if (mounted.current)
        setMessage(
          analysisError(
            cause,
            "No se pudo guardar. Revisa el borrador y vuelve a intentarlo.",
          ),
        );
    } finally {
      if (mounted.current) setBusy(false);
    }
  }

  async function applySaved(result: SavedConfiguration, feedback: string) {
    if (!mounted.current) return;
    setInitial(result.document);
    setData(
      (current) => current && { ...current, ...result, saved: result.document },
    );
    setDirty(false);
    setUndo([]);
    setMessage(feedback);
    try {
      const status = await analysisService.getAnalysisStatus(session.id);
      if (mounted.current) onSaved(status);
    } catch {
      if (mounted.current)
        setMessage(
          `${feedback} El estado de la sesión se actualizará al reconectar.`,
        );
    }
  }

  return (
    <section
      className={styles.editor}
      aria-label="Configuración espacial"
      hidden={unavailable && !open}
    >
      <div className={styles.editorHeader}>
        <Button
          ref={trigger}
          variant="outline"
          className={styles.trigger}
          disabled={unavailable || busy || calibrationBusy}
          aria-expanded={open}
          aria-controls={panelId}
          onClick={() => {
            setOpen(!open);
            if (!open && !data && !loading) void load();
          }}
        >
          <Waypoints size={17} aria-hidden="true" />
          Zonas, calibración y reglas
          <ChevronDown size={16} aria-hidden="true" />
        </Button>
        {dirty && (
          <span className={styles.draftStatus}>Borrador sin guardar</span>
        )}
      </div>
      <div id={panelId} hidden={!open}>
        {!doc && loading && (
          <p className={styles.notice} role="status">
            Cargando configuración…
          </p>
        )}
        {!doc && !loading && (
          <Button variant="outline" onClick={() => void load()}>
            Reintentar carga
          </Button>
        )}
        {doc && data && (
          <div className={styles.editorBody}>
            <h2>Configuración preparada de esta fuente</h2>
            <div
              className={styles.tasks}
              role="tablist"
              aria-label="Tareas de configuración"
            >
              {tasks.map((label, index) => (
                <button
                  key={label}
                  ref={(element) => {
                    tabs.current[index] = element;
                  }}
                  type="button"
                  role="tab"
                  id={`${panelId}-tab-${index}`}
                  aria-controls={`${panelId}-task-${index}`}
                  aria-selected={task === index}
                  disabled={calibrationBusy}
                  tabIndex={task === index ? 0 : -1}
                  data-guide={
                    index === 2
                      ? "calibration"
                      : index === 3
                        ? "rules"
                        : undefined
                  }
                  onClick={() => chooseTask(index)}
                  onKeyDown={(event) => {
                    const next = {
                      ArrowLeft: (index + tasks.length - 1) % tasks.length,
                      ArrowRight: (index + 1) % tasks.length,
                      Home: 0,
                      End: tasks.length - 1,
                    }[event.key];
                    if (next === undefined) return;
                    event.preventDefault();
                    chooseTask(next, true);
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
            <fieldset disabled={locked} className={styles.taskFieldset}>
              <legend className="sr-only">Configuración de la fuente</legend>
              <div
                role="tabpanel"
                id={`${panelId}-task-0`}
                aria-labelledby={`${panelId}-tab-0`}
                hidden={task !== 0}
                tabIndex={0}
              >
                <div className={styles.taskBody}>
                  <dl className={styles.facts}>
                    <div>
                      <dt>Fuente</dt>
                      <dd>{session.filename}</dd>
                    </div>
                    <div>
                      <dt>Perfil</dt>
                      <dd>Perfil {session.profile}</dd>
                    </div>
                    <div>
                      <dt>En sesión</dt>
                      <dd>
                        {session.spatial_revision
                          ? `Revisión ${session.spatial_revision}`
                          : "Configuración inicial"}
                      </dd>
                    </div>
                    <div>
                      <dt>Última guardada</dt>
                      <dd>
                        {data.saved
                          ? `Revisión ${data.revision}`
                          : "Sin revisión guardada"}
                      </dd>
                    </div>
                  </dl>
                  <p>
                    Configura las zonas, verifica si necesitas calibrar y revisa
                    las reglas antes de guardar.
                  </p>
                  <div className={styles.actions}>
                    <Button
                      variant="outline"
                      onClick={() => chooseTask(1, true)}
                    >
                      Configurar zonas
                    </Button>
                  </div>
                </div>
              </div>
              <div
                role="tabpanel"
                id={`${panelId}-task-1`}
                aria-labelledby={`${panelId}-tab-1`}
                hidden={task !== 1}
              >
                <div className={styles.taskBody}>
                  <p>
                    Elige el área del video donde quieres aplicar una regla.
                  </p>
                  <select
                    className="input"
                    aria-label="Zona seleccionada"
                    value={selected}
                    onChange={(e) => {
                      setSelected(Number(e.target.value));
                      setVertex(null);
                      setUndo([]);
                    }}
                  >
                    {doc.zones.map((z, i) => (
                      <option key={i} value={i}>
                        {z.name}
                      </option>
                    ))}
                  </select>
                  {zone && (
                    <>
                      <label>
                        Identificador
                        <input
                          className="input"
                          value={zone.zone_id}
                          onChange={(e) => {
                            const id = e.target.value;
                            update({
                              ...doc,
                              zones: doc.zones.map((z, i) =>
                                i === selected ? { ...z, zone_id: id } : z,
                              ),
                              rules: doc.rules.map((r) =>
                                r.parameters.zone_id === zone.zone_id
                                  ? {
                                      ...r,
                                      parameters: {
                                        ...r.parameters,
                                        zone_id: id,
                                      },
                                    }
                                  : r,
                              ),
                            });
                          }}
                        />
                      </label>
                      <label>
                        Nombre
                        <input
                          className="input"
                          value={zone.name}
                          onChange={(e) =>
                            update({
                              ...doc,
                              zones: doc.zones.map((z, i) =>
                                i === selected
                                  ? { ...z, name: e.target.value }
                                  : z,
                              ),
                            })
                          }
                        />
                      </label>
                      <label>
                        Finalidad
                        <select
                          className="input"
                          value={zone.purpose ?? "observation"}
                          onChange={(e) =>
                            update({
                              ...doc,
                              zones: doc.zones.map((z, i) =>
                                i === selected
                                  ? { ...z, purpose: e.target.value }
                                  : z,
                              ),
                            })
                          }
                        >
                          {Object.entries(purposes).map(([id, name]) => (
                            <option key={id} value={id}>
                              {name}
                            </option>
                          ))}
                        </select>
                      </label>
                      <label>
                        <input
                          type="checkbox"
                          checked={zone.enabled !== false}
                          onChange={(e) =>
                            update({
                              ...doc,
                              zones: doc.zones.map((z, i) =>
                                i === selected
                                  ? { ...z, enabled: e.target.checked }
                                  : z,
                              ),
                            })
                          }
                        />{" "}
                        Zona habilitada
                      </label>
                      <p>
                        Captura el fotograma y marca puntos sobre la imagen.
                        Arrastra un vértice para ajustarlo.
                      </p>
                      <SpatialFrame
                        key={editorRevision}
                        sessionId={session.id}
                        active={open && task === 1}
                        locked={locked}
                      >
                        <svg
                          viewBox="0 0 100 100"
                          preserveAspectRatio="none"
                          className={styles.pointOverlay}
                          aria-label="Editor gráfico de zona"
                          onPointerDown={(e) => {
                            if (
                              e.target !== e.currentTarget ||
                              zone.polygon.length >= 32
                            )
                              return;
                            const point = pointInFrame(e);
                            if (point) {
                              changePolygon([...zone.polygon, point]);
                              setVertex(zone.polygon.length);
                            }
                          }}
                          onPointerMove={(e) => {
                            if (drag.current === null) return;
                            const point = pointInFrame(e);
                            if (point)
                              changePolygon(
                                zone.polygon.map((p, i) =>
                                  i === drag.current ? point : p,
                                ),
                                false,
                              );
                          }}
                          onPointerUp={() => {
                            drag.current = null;
                          }}
                          onPointerCancel={() => {
                            drag.current = null;
                          }}
                        >
                          {doc.zones.map((z, i) => (
                            <polygon
                              key={i}
                              className={
                                i === selected
                                  ? styles.floorArea
                                  : styles.otherZone
                              }
                              points={z.polygon
                                .filter((p) => p.every(Number.isFinite))
                                .map(([x, y]) => `${x * 100},${y * 100}`)
                                .join(" ")}
                            />
                          ))}
                          {zone.polygon.map(
                            ([x, y], i) =>
                              Number.isFinite(x) &&
                              Number.isFinite(y) && (
                                <circle
                                  key={i}
                                  cx={x * 100}
                                  cy={y * 100}
                                  r="1.2"
                                  tabIndex={locked ? -1 : 0}
                                  role="button"
                                  aria-label={`Vértice ${i + 1}`}
                                  className={styles.vertex}
                                  data-selected={vertex === i}
                                  onFocus={() => setVertex(i)}
                                  onPointerDown={(e) => {
                                    if (locked) return;
                                    e.stopPropagation();
                                    e.currentTarget.focus();
                                    e.currentTarget.setPointerCapture(
                                      e.pointerId,
                                    );
                                    drag.current = i;
                                    setUndo((history) => [
                                      ...history.slice(-31),
                                      zone.polygon,
                                    ]);
                                  }}
                                  onKeyDown={(e) => {
                                    if (
                                      e.key === "Delete" ||
                                      e.key === "Backspace"
                                    ) {
                                      e.preventDefault();
                                      if (zone.polygon.length > 3) {
                                        changePolygon(
                                          removeVertex(zone.polygon, i),
                                        );
                                        setVertex(null);
                                      }
                                      return;
                                    }
                                    const delta = {
                                      ArrowLeft: [-1, 0],
                                      ArrowRight: [1, 0],
                                      ArrowUp: [0, -1],
                                      ArrowDown: [0, 1],
                                    }[e.key];
                                    if (!delta) return;
                                    e.preventDefault();
                                    const [dx, dy] = delta.map(
                                      (value) =>
                                        value * (e.shiftKey ? 0.01 : 0.005),
                                    );
                                    const clamp = (value: number) =>
                                      Math.min(1, Math.max(0, value));
                                    changePolygon(
                                      zone.polygon.map((p, j) =>
                                        j === i
                                          ? [clamp(x + dx), clamp(y + dy)]
                                          : p,
                                      ),
                                    );
                                  }}
                                />
                              ),
                          )}
                        </svg>
                      </SpatialFrame>
                      <div className={styles.actions}>
                        <Button
                          variant="secondary"
                          disabled={!zone.polygon.length}
                          onClick={() => {
                            changePolygon([]);
                            setVertex(null);
                          }}
                        >
                          Dibujar de nuevo
                        </Button>
                        <Button
                          variant="secondary"
                          disabled={vertex === null || zone.polygon.length <= 3}
                          onClick={() => {
                            changePolygon(removeVertex(zone.polygon, vertex));
                            setVertex(null);
                          }}
                        >
                          Eliminar vértice
                        </Button>
                        <Button
                          variant="secondary"
                          disabled={!undo.length}
                          onClick={() => {
                            changePolygon(undo[undo.length - 1], false);
                            setUndo(undo.slice(0, -1));
                            setVertex(null);
                          }}
                        >
                          Deshacer
                        </Button>
                        <Button
                          variant="secondary"
                          disabled={!originalZone}
                          onClick={() => {
                            if (!originalZone) return;
                            changePolygon(originalZone.polygon);
                            setVertex(null);
                          }}
                        >
                          Restablecer vértices
                        </Button>
                      </div>
                      <p role="status">
                        {zone.polygon.length} vértices ·{" "}
                        {validPolygon(zone.polygon)
                          ? "Polígono válido"
                          : "Polígono pendiente de ajuste"}
                      </p>
                      <details className={styles.advanced}>
                        <summary>Coordenadas avanzadas</summary>
                        <div className={styles.coordinates}>
                          <p>
                            Usa valores de 0 a 1 desde la esquina superior
                            izquierda.
                          </p>
                          {zone.polygon.map((point, i) => (
                            <div key={i} className={styles.fieldGrid}>
                              {point.map((value, axis) => (
                                <label key={axis}>
                                  Vértice {i + 1} · {axis ? "Y" : "X"}
                                  <input
                                    type="number"
                                    className="input"
                                    min="0"
                                    max="1"
                                    step="any"
                                    value={Number.isFinite(value) ? value : ""}
                                    onChange={(e) =>
                                      changePolygon(
                                        zone.polygon.map((p, j) =>
                                          j !== i
                                            ? p
                                            : axis === 0
                                              ? [e.target.valueAsNumber, p[1]]
                                              : [p[0], e.target.valueAsNumber],
                                        ),
                                      )
                                    }
                                  />
                                </label>
                              ))}
                            </div>
                          ))}
                          <div className={styles.actions}>
                            <Button
                              variant="outline"
                              disabled={zone.polygon.length >= 32}
                              onClick={() =>
                                changePolygon([...zone.polygon, [NaN, NaN]])
                              }
                            >
                              Añadir vértice por coordenadas
                            </Button>
                          </div>
                        </div>
                      </details>
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (
                            doc.rules.some(
                              (r) => r.parameters.zone_id === zone.zone_id,
                            )
                          ) {
                            setMessage("Retire primero las reglas asociadas.");
                            return;
                          }
                          update({
                            ...doc,
                            zones: doc.zones.filter((_, i) => i !== selected),
                          });
                          setSelected(0);
                          setVertex(null);
                          setUndo([]);
                        }}
                      >
                        Eliminar zona
                      </Button>
                    </>
                  )}
                  <Button
                    variant="outline"
                    onClick={() => {
                      setSelected(doc.zones.length);
                      setVertex(null);
                      setUndo([]);
                      update({
                        ...doc,
                        zones: [
                          ...doc.zones,
                          {
                            zone_id: `zona_${Date.now()}`,
                            name: "Nueva zona",
                            polygon: [],
                            enabled: true,
                            purpose: "observation",
                          },
                        ],
                      });
                    }}
                  >
                    Crear zona
                  </Button>
                </div>
              </div>
              <div
                role="tabpanel"
                id={`${panelId}-task-2`}
                aria-labelledby={`${panelId}-tab-2`}
                hidden={task !== 2}
              >
                <AutomaticCalibration<SavedConfiguration>
                  key={`${session.id}:${session.source_sha256}:${data.revision}`}
                  source={{
                    kind: "sessions",
                    id: session.id,
                    revision: data.revision,
                  }}
                  zones={doc.zones}
                  saved={doc.calibration}
                  blocked={
                    zonesProblem
                      ? "Dibuja y guarda una zona válida en la pestaña Zonas antes de capturar una propuesta."
                      : dirty
                        ? "Guarda o descarta el borrador de configuración antes de capturar una propuesta."
                        : undefined
                  }
                  onBusyChange={setCalibrationBusy}
                  onRefresh={() => void load()}
                  onSaved={(result) => {
                    setBusy(true);
                    setEditorRevision((value) => value + 1);
                    void applySaved(
                      result,
                      "Calibración con patrón guardada para el próximo análisis.",
                    ).finally(() => {
                      if (mounted.current) setBusy(false);
                    });
                  }}
                />
                <h3 className={styles.manualCalibrationTitle}>
                  Calibración asistida o manual
                </h3>
                <CalibrationGuide
                  key={editorRevision}
                  calibration={doc.calibration}
                  sessionId={session.id}
                  sourceHash={session.source_sha256}
                  locked={locked}
                  active={open && task === 2}
                  onChange={(calibration) => update({ ...doc, calibration })}
                  onReview={() => chooseTask(4, true)}
                />
                {doc.calibration?.pattern_evidence != null &&
                  !doc.calibration.zones_reviewed && (
                    <div className={styles.actions}>
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (doc.calibration)
                            update({
                              ...doc,
                              calibration: {
                                ...doc.calibration,
                                zones_reviewed: true,
                              },
                            });
                        }}
                      >
                        Confirmar revisión de las zonas editadas
                      </Button>
                    </div>
                  )}
                {doc.calibration?.status === "valid" &&
                  doc.calibration.homography && (
                    <div className={styles.actions}>
                      <Button
                        variant="outline"
                        onClick={() => {
                          if (
                            !doc.calibration ||
                            !window.confirm(
                              "¿Invalidar el encuadre y desactivar las zonas en el borrador?",
                            )
                          )
                            return;
                          update({
                            ...doc,
                            calibration: {
                              ...doc.calibration,
                              status: "invalid",
                            },
                            zones: doc.zones.map((z) => ({
                              ...z,
                              enabled: false,
                            })),
                          });
                        }}
                      >
                        Invalidar encuadre
                      </Button>
                    </div>
                  )}
              </div>
              <div
                role="tabpanel"
                id={`${panelId}-task-3`}
                aria-labelledby={`${panelId}-tab-3`}
                hidden={task !== 3}
              >
                <div className={styles.taskBody}>
                  <p>
                    {data.policy
                      ? "Edita las reglas de respaldo que se usarán si la fuente queda sin conjunto asignado."
                      : "Elige qué condición se observará y en qué zona."}
                  </p>
                  <MotionConfiguration
                    motion={doc.motion}
                    relations={doc.relations}
                    metricAvailable={
                      doc.calibration?.status === "valid" &&
                      Boolean(doc.calibration.homography)
                    }
                    onMotion={(motion) => {
                      if (
                        !motion &&
                        doc.rules.some(
                          (r) =>
                            r.enabled &&
                            r.parameters.motion_condition === "moving",
                        )
                      ) {
                        setMessage(
                          "Deshabilite o cambie primero las reglas que requieren movimiento.",
                        );
                        return;
                      }
                      update({ ...doc, motion });
                    }}
                    onRelations={(relations) => update({ ...doc, relations })}
                  />
                  {doc.rules.map((rule, i) => (
                    <details key={i} className={styles.advanced}>
                      <summary>
                        {kinds[rule.parameters.kind as keyof typeof kinds] ??
                          rule.rule_id}{" "}
                        · {rule.enabled ? "Activa" : "Desactivada"}
                      </summary>
                      <div className={styles.coordinates}>
                        <label>
                          ID de regla
                          <input
                            className="input"
                            value={rule.rule_id}
                            onChange={(e) =>
                              update({
                                ...doc,
                                rules: doc.rules.map((r, j) =>
                                  j === i
                                    ? { ...r, rule_id: e.target.value }
                                    : r,
                                ),
                              })
                            }
                          />
                        </label>
                        <p>Versión guardada: {rule.version}</p>
                        <label>
                          <input
                            type="checkbox"
                            checked={rule.enabled}
                            onChange={(e) =>
                              update({
                                ...doc,
                                rules: doc.rules.map((r, j) =>
                                  j === i
                                    ? { ...r, enabled: e.target.checked }
                                    : r,
                                ),
                              })
                            }
                          />{" "}
                          Habilitada
                        </label>
                        <label>
                          Condición
                          <select
                            className="input"
                            value={String(rule.parameters.kind)}
                            onChange={(e) => {
                              const kind = e.target.value,
                                pair = [
                                  "person_forklift_proximity",
                                  "zone_coexistence",
                                ].includes(kind);
                              const parameters: Rule["parameters"] = pair
                                ? {
                                    kind,
                                    zone_id: zone?.zone_id ?? "",
                                    person_class: "person",
                                    forklift_class: "forklift",
                                    max_distance:
                                      kind === "zone_coexistence"
                                        ? Math.SQRT2
                                        : 0.1,
                                    minimum_duration_seconds: 1,
                                  }
                                : {
                                    kind,
                                    zone_id: zone?.zone_id ?? "",
                                    class_name: "person",
                                    min_duration_s:
                                      kind === "zone_entry" ? 0 : 2,
                                  };
                              update({
                                ...doc,
                                rules: doc.rules.map((r, j) =>
                                  j === i ? { ...r, parameters } : r,
                                ),
                              });
                            }}
                          >
                            {Object.entries(kinds).map(([id, name]) => (
                              <option key={id} value={id}>
                                {name}
                              </option>
                            ))}
                          </select>
                        </label>
                        <label>
                          Zona
                          <select
                            className="input"
                            value={String(rule.parameters.zone_id)}
                            onChange={(e) =>
                              update({
                                ...doc,
                                rules: doc.rules.map((r, j) =>
                                  j === i
                                    ? {
                                        ...r,
                                        parameters: {
                                          ...r.parameters,
                                          zone_id: e.target.value,
                                        },
                                      }
                                    : r,
                                ),
                              })
                            }
                          >
                            {doc.zones.map((z) => (
                              <option key={z.zone_id} value={z.zone_id}>
                                {z.name}
                              </option>
                            ))}
                          </select>
                        </label>
                        {rule.parameters.class_name && (
                          <label>
                            Objeto
                            <select
                              className="input"
                              value={String(rule.parameters.class_name)}
                              onChange={(e) =>
                                update({
                                  ...doc,
                                  rules: doc.rules.map((r, j) =>
                                    j === i
                                      ? {
                                          ...r,
                                          parameters: {
                                            ...r.parameters,
                                            class_name: e.target.value,
                                          },
                                        }
                                      : r,
                                  ),
                                })
                              }
                            >
                              <option value="person">Persona</option>
                              <option value="forklift">Montacargas</option>
                            </select>
                          </label>
                        )}
                        {rule.parameters.kind ===
                          "person_forklift_proximity" && (
                          <>
                            <label>
                              Condición de movimiento
                              <select
                                className="input"
                                value={String(
                                  rule.parameters.motion_condition ?? "any",
                                )}
                                onChange={(e) =>
                                  update({
                                    ...doc,
                                    rules: doc.rules.map((r, j) =>
                                      j === i
                                        ? {
                                            ...r,
                                            parameters: {
                                              ...r.parameters,
                                              motion_condition: e.target.value,
                                            },
                                          }
                                        : r,
                                    ),
                                  })
                                }
                              >
                                <option value="any">
                                  Independiente del movimiento
                                </option>
                                <option
                                  value="moving"
                                  disabled={!doc.motion?.camera_fixed_confirmed}
                                >
                                  Solo con movimiento confirmado
                                </option>
                              </select>
                            </label>
                            <label>
                              <input
                                type="checkbox"
                                checked={
                                  rule.parameters.exclude_possible_occupant ===
                                  true
                                }
                                disabled={
                                  !doc.motion?.camera_fixed_confirmed &&
                                  rule.parameters.exclude_possible_occupant !==
                                    true
                                }
                                onChange={(e) =>
                                  update({
                                    ...doc,
                                    rules: doc.rules.map((r, j) =>
                                      j === i
                                        ? {
                                            ...r,
                                            parameters: {
                                              ...r.parameters,
                                              exclude_possible_occupant:
                                                e.target.checked,
                                            },
                                          }
                                        : r,
                                    ),
                                  })
                                }
                              />{" "}
                              Excluir posibles ocupantes de su propio vehículo
                              (experimental)
                            </label>
                            <label>
                              Unidad
                              <select
                                className="input"
                                value={String(
                                  rule.parameters.distance_unit ?? "normalized",
                                )}
                                onChange={(e) =>
                                  update({
                                    ...doc,
                                    rules: doc.rules.map((r, j) =>
                                      j === i
                                        ? {
                                            ...r,
                                            parameters: {
                                              ...r.parameters,
                                              distance_unit: e.target.value,
                                            },
                                          }
                                        : r,
                                    ),
                                  })
                                }
                              >
                                <option value="normalized">
                                  Normalizada en imagen
                                </option>
                                <option value="m">
                                  Metros aproximados (requiere calibración)
                                </option>
                              </select>
                            </label>
                            <label>
                              Distancia máxima configurada
                              <input
                                className="input"
                                type="number"
                                min="0"
                                step=".01"
                                value={Number(rule.parameters.max_distance)}
                                onChange={(e) =>
                                  update({
                                    ...doc,
                                    rules: doc.rules.map((r, j) =>
                                      j === i
                                        ? {
                                            ...r,
                                            parameters: {
                                              ...r.parameters,
                                              max_distance: Number(
                                                e.target.value,
                                              ),
                                            },
                                          }
                                        : r,
                                    ),
                                  })
                                }
                              />
                            </label>
                          </>
                        )}
                        {rule.parameters.kind !== "zone_entry" && (
                          <label>
                            Duración mínima (s)
                            <input
                              className="input"
                              type="number"
                              min="0"
                              step=".1"
                              value={Number(
                                rule.parameters.minimum_duration_seconds ??
                                  rule.parameters.min_duration_s,
                              )}
                              onChange={(e) => {
                                const field = rule.parameters.class_name
                                  ? "min_duration_s"
                                  : "minimum_duration_seconds";
                                update({
                                  ...doc,
                                  rules: doc.rules.map((r, j) =>
                                    j === i
                                      ? {
                                          ...r,
                                          parameters: {
                                            ...r.parameters,
                                            [field]: Number(e.target.value),
                                          },
                                        }
                                      : r,
                                  ),
                                });
                              }}
                            />
                          </label>
                        )}
                        <Button
                          variant="ghost"
                          onClick={() =>
                            update({
                              ...doc,
                              rules: doc.rules.filter((_, j) => j !== i),
                            })
                          }
                        >
                          Eliminar regla
                        </Button>
                      </div>
                    </details>
                  ))}
                  <Button
                    variant="outline"
                    onClick={() =>
                      update({
                        ...doc,
                        rules: [
                          ...doc.rules,
                          {
                            rule_id: `regla_${Date.now()}`,
                            version: 1,
                            enabled: true,
                            parameters: {
                              kind: "zone_dwell",
                              class_name: "person",
                              zone_id: zone?.zone_id ?? "",
                              min_duration_s: 2,
                            },
                          },
                        ],
                      })
                    }
                  >
                    Crear regla
                  </Button>
                </div>
              </div>
              <div
                role="tabpanel"
                id={`${panelId}-task-4`}
                aria-labelledby={`${panelId}-tab-4`}
                hidden={task !== 4}
              >
                <div className={styles.taskBody}>
                  <dl className={styles.facts}>
                    <div>
                      <dt>Zonas habilitadas</dt>
                      <dd>
                        {doc.zones
                          .filter((z) => z.enabled !== false)
                          .map((z) => z.name)
                          .join(", ") || "Ninguna"}
                      </dd>
                    </div>
                    <div>
                      <dt>
                        {data.policy
                          ? "Reglas locales de respaldo"
                          : "Reglas activas"}
                      </dt>
                      <dd>
                        {doc.rules
                          .filter((r) => r.enabled)
                          .map(
                            (r) =>
                              kinds[r.parameters.kind as keyof typeof kinds] ??
                              r.rule_id,
                          )
                          .join(", ") || "Ninguna"}
                      </dd>
                    </div>
                    <div>
                      <dt>Calibración</dt>
                      <dd>
                        {!doc.calibration
                          ? "Sin metros"
                          : doc.calibration.status === "invalid"
                            ? "Encuadre invalidado"
                            : doc.calibration.homography &&
                                doc.calibration.zones_reviewed
                              ? `Validada · versión ${doc.calibration.version}`
                              : "Pendiente de validación al guardar"}
                      </dd>
                    </div>
                  </dl>
                  {data.policy && (
                    <section
                      className={styles.policyReview}
                      aria-label="Política asignada"
                    >
                      <h3>Conjunto asignado</h3>
                      <p>
                        <strong>{data.policy.rule_set.name}</strong> · versión{" "}
                        {data.policy.rule_set.version}
                      </p>
                      <p>
                        Estas reglas tienen prioridad para la próxima ejecución.
                        Las reglas editables de esta fuente sirven de respaldo.
                      </p>
                      <RuleConfiguration
                        snapshot={{ rules: data.effective_rules }}
                      />
                    </section>
                  )}
                  <p>
                    La revisión guardada se aplicará al próximo análisis de esta
                    fuente.
                  </p>
                  {problem && (
                    <p role="status" className={styles.notice}>
                      {problem}
                    </p>
                  )}
                  <div className={styles.actions}>
                    <Button
                      disabled={Boolean(problem)}
                      onClick={() => void save()}
                    >
                      Guardar configuración
                    </Button>
                    <Button
                      variant="outline"
                      disabled={!data.saved}
                      onClick={() => {
                        if (
                          !data.saved ||
                          (dirty &&
                            !window.confirm(
                              "¿Reemplazar el borrador con la revisión guardada?",
                            ))
                        )
                          return;
                        replaceDraft(structuredClone(data.saved), true);
                        setMessage(
                          "Revisión cargada en el borrador. Guarda para aplicarla a la sesión.",
                        );
                      }}
                    >
                      Recuperar guardada
                    </Button>
                    <Button
                      variant="ghost"
                      disabled={!dirty}
                      onClick={() => {
                        if (
                          !initial ||
                          !window.confirm(
                            "¿Descartar los cambios espaciales sin guardar?",
                          )
                        )
                          return;
                        replaceDraft(initial, false);
                        setMessage("Borrador descartado.");
                      }}
                    >
                      Descartar borrador
                    </Button>
                  </div>
                </div>
              </div>
            </fieldset>
          </div>
        )}
      </div>
      {message && (
        <p role="status" className={styles.notice}>
          {message}
        </p>
      )}
    </section>
  );
}
