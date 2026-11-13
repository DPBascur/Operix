"use client";
/* eslint-disable @next/next/no-img-element -- Fotograma local capturado del video autorizado. */
import { useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { apiFetch } from "@/services/browser-session";
import {
  analysisService,
  type AnalysisSessionStatus,
  type MotionSettings,
  type RelationSettings,
} from "@/services/analysis.service";
import { environment } from "@/config/environment";

import { MotionConfiguration } from "./motion-configuration";

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
  parameters: Record<string, string | number>;
};
type Calibration = {
  image_points: Point[];
  ground_points_m: Point[];
  status: string;
  source_sha256: string;
  version: number;
  calibrated_at: string;
  units: string;
  zones_reviewed: boolean;
  framing_reference?: "first_frame_orb_affine_v1";
  homography?: number[][];
  max_reference_error_m?: number;
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
type Loaded = { document: Document; saved: Document | null; revision: number };
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

function GroundPreview({ calibration }: { calibration: Calibration }) {
  const h = calibration.homography;
  if (!h || calibration.status !== "valid") return null;
  const projected = calibration.image_points.map(([x, y]) => {
    const [px, py, w] = h.map((row) => row[0] * x + row[1] * y + row[2]);
    return [px / w, py / w];
  });
  if (projected.length < 4 || projected.some((p) => !p.every(Number.isFinite)))
    return null;
  const xs = projected.map(([x]) => x);
  const ys = projected.map(([, y]) => -y);
  const left = Math.min(...xs);
  const top = Math.min(...ys);
  const width = Math.max(...xs) - left;
  const height = Math.max(...ys) - top;
  const marker = Math.max(width, height) / 40;
  if (!(marker > 0)) return null;
  return (
    <figure className="m-0 grid gap-2 text-sm">
      <figcaption>
        Vista en planta de las referencias guardadas (m)
        {calibration.max_reference_error_m != null &&
          ` · Residuo máximo del ajuste: ${calibration.max_reference_error_m.toFixed(3)} m`}
      </figcaption>
      <svg
        role="img"
        aria-label="Proyección de las referencias numeradas sobre el plano del suelo"
        className="h-40 w-full max-w-md rounded-control border border-border text-primary"
        viewBox={`${left - marker * 3} ${top - marker * 3} ${width + marker * 6} ${height + marker * 6}`}
      >
        {projected.map((_, i) => (
          <g key={i} fill="currentColor">
            <circle cx={xs[i]} cy={ys[i]} r={marker * 0.5} />
            <text x={xs[i] + marker} y={ys[i]} fontSize={marker * 1.6}>
              {i + 1}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}

export function SpatialEditor({
  session,
  onSaved,
  onEditingChange,
}: {
  session: AnalysisSessionStatus;
  onSaved: (s: AnalysisSessionStatus) => void;
  onEditingChange: (editing: boolean) => void;
}) {
  const [data, setData] = useState<Loaded | null>(null);
  const [dirty, setDirty] = useState(false);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    onEditingChange(open);
    return () => onEditingChange(false);
  }, [open, onEditingChange]);
  const [message, setMessage] = useState("");
  const [frame, setFrame] = useState("");
  const [firstFrame, setFirstFrame] = useState(false);
  const [selected, setSelected] = useState(0);
  const [mode, setMode] = useState("zone");
  const video = useRef<HTMLVideoElement>(null);
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
    const value = await response.json();
    if (!response.ok)
      throw new Error(value.detail ?? "No se pudo guardar la configuración.");
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
  const locked = busy || ["preparing", "processing"].includes(session.state);
  async function load() {
    setBusy(true);
    setMessage("");
    try {
      const loaded = await request("GET");
      if (!mounted.current) return;
      setData(loaded);
      setDirty(false);
      setOpen(true);
    } catch (e) {
      setMessage(String(e instanceof Error ? e.message : e));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section
      className="my-3 rounded-2xl border border-border bg-surface p-4"
      aria-label="Configuración espacial"
    >
      <Button variant="outline" disabled={locked} onClick={() => void load()}>
        Zonas, calibración y reglas
      </Button>
      {open && data && doc && (
        <div className="mt-4 grid gap-4">
          <h2>Configuración preparada de esta fuente</h2>
          <p className="text-sm">
            En sesión:{" "}
            {session.spatial_revision
              ? `revisión ${session.spatial_revision}`
              : "configuración inicial"}
            .
            {data.saved
              ? ` Última guardada para esta fuente: revisión ${data.revision}.`
              : " No hay configuración guardada para esta fuente."}{" "}
            Guarde y cierre el editor antes de iniciar. Solo los cambios
            guardados se aplican al próximo análisis. Los resultados anteriores
            conservan su snapshot.
          </p>
          <video
            ref={video}
            src={analysisService.getAnalysisSourceUrl(session.id)}
            controls
            preload="metadata"
            className="max-h-80 w-full"
            aria-label="Referencia de configuración"
          />
          <Button
            variant="secondary"
            disabled={locked}
            onClick={async () => {
              const v = video.current;
              if (!v || v.readyState < 2 || locked) {
                setMessage("Espere a que cargue el video.");
                return;
              }
              setBusy(true);
              setMessage("");
              try {
                v.pause();
                // readyState puede ser 4 sin haber entregado un frame al canvas.
                // Seek a la misma posición fuerza decodificación sin reproducir.
                await new Promise<void>((resolve, reject) => {
                  const finish = () => {
                    clearTimeout(timer);
                    v.removeEventListener("seeked", done);
                  };
                  const done = () => {
                    finish();
                    resolve();
                  };
                  const timer = setTimeout(() => {
                    finish();
                    reject(new Error("No se pudo decodificar el fotograma."));
                  }, 5000);
                  v.addEventListener("seeked", done, { once: true });
                  v.currentTime = mode === "calibration" ? 0 : v.currentTime;
                });
                if (!mounted.current) return;
                const canvas = document.createElement("canvas");
                canvas.width = v.videoWidth;
                canvas.height = v.videoHeight;
                const context = canvas.getContext("2d");
                if (!context)
                  throw new Error("No se pudo preparar la referencia.");
                context.drawImage(v, 0, 0);
                if (!context.getImageData(0, 0, 1, 1).data[3])
                  throw new Error(
                    "El fotograma no está disponible. Cambie de posición y vuelva a capturar.",
                  );
                setFrame(canvas.toDataURL());
                setFirstFrame(mode === "calibration");
              } catch (error) {
                if (mounted.current)
                  setMessage(
                    error instanceof Error
                      ? error.message
                      : "No se pudo capturar el fotograma.",
                  );
              } finally {
                if (mounted.current) setBusy(false);
              }
            }}
          >
            {mode === "calibration"
              ? "Capturar primer fotograma"
              : "Capturar fotograma de referencia"}
          </Button>
          <label>
            Editar sobre imagen
            <select
              className="input"
              value={mode}
              onChange={(e) => setMode(e.target.value)}
            >
              <option value="zone">Vértices de zona</option>
              <option value="calibration">Referencias del suelo</option>
            </select>
          </label>
          {frame && (
            <div className="relative">
              <img
                src={frame}
                alt="Fotograma de la fuente para configuración espacial"
                className="block w-full"
              />
              <svg
                className="absolute inset-0 h-full w-full"
                viewBox="0 0 1 1"
                preserveAspectRatio="none"
                role="img"
                aria-label="Editor de puntos"
                onPointerDown={(e) => {
                  if (locked) return;
                  const r = e.currentTarget.getBoundingClientRect();
                  const p: Point = [
                    Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)),
                    Math.max(0, Math.min(1, (e.clientY - r.top) / r.height)),
                  ];
                  if (mode === "zone" && zone && zone.polygon.length < 32)
                    update({
                      ...doc,
                      zones: doc.zones.map((z, i) =>
                        i === selected
                          ? { ...z, polygon: [...z.polygon, p] }
                          : z,
                      ),
                    });
                  if (
                    mode === "calibration" &&
                    doc.calibration &&
                    firstFrame &&
                    doc.calibration.image_points.length < 16
                  )
                    update({
                      ...doc,
                      calibration: {
                        ...doc.calibration,
                        image_points: [...doc.calibration.image_points, p],
                        ground_points_m: [
                          ...doc.calibration.ground_points_m,
                          [0, 0],
                        ],
                      },
                    });
                }}
              >
                {doc.zones.map((z, i) => (
                  <polygon
                    key={i}
                    points={z.polygon.map((p) => p.join(",")).join(" ")}
                    fill="rgba(30,110,220,.12)"
                    stroke={i === selected ? "#2876cf" : "#778899"}
                    strokeWidth=".003"
                  />
                ))}
                {(mode === "calibration"
                  ? (doc.calibration?.image_points ?? [])
                  : (zone?.polygon ?? [])
                ).map((p, i) => (
                  <g key={i}>
                    <circle cx={p[0]} cy={p[1]} r=".008" fill="#2876cf" />
                    <text x={p[0] + 0.01} y={p[1]} fontSize=".025" fill="white">
                      {i + 1}
                    </text>
                  </g>
                ))}
              </svg>
            </div>
          )}
          <fieldset disabled={locked} className="grid gap-3">
            <legend>Zonas operacionales</legend>
            <select
              className="input"
              aria-label="Zona seleccionada"
              value={selected}
              onChange={(e) => setSelected(Number(e.target.value))}
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
                                parameters: { ...r.parameters, zone_id: id },
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
                          i === selected ? { ...z, name: e.target.value } : z,
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
                {zone.polygon.map((p, i) => (
                  <div key={i} className="flex flex-wrap gap-2">
                    {p.map((v, axis) => (
                      <label key={axis}>
                        Vértice {i + 1} · {axis ? "y" : "x"}
                        <input
                          type="number"
                          className="input"
                          step=".001"
                          min="0"
                          max="1"
                          value={v}
                          onChange={(e) =>
                            update({
                              ...doc,
                              zones: doc.zones.map((z, j) =>
                                j === selected
                                  ? {
                                      ...z,
                                      polygon: z.polygon.map((p, k) =>
                                        k === i
                                          ? (p.map((v, a) =>
                                              a === axis
                                                ? Number(e.target.value)
                                                : v,
                                            ) as Point)
                                          : p,
                                      ),
                                    }
                                  : z,
                              ),
                            })
                          }
                        />
                      </label>
                    ))}
                    <Button
                      variant="ghost"
                      onClick={() =>
                        update({
                          ...doc,
                          zones: doc.zones.map((z, j) =>
                            j === selected
                              ? {
                                  ...z,
                                  polygon: z.polygon.filter((_, k) => k !== i),
                                }
                              : z,
                          ),
                        })
                      }
                    >
                      Quitar vértice {i + 1}
                    </Button>
                  </div>
                ))}
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
            <h3 data-guide="calibration">Plano del suelo</h3>
            <p className="text-sm">
              Metros aproximados, válidos solo para cámara fija, suelo plano y
              referencias medidas. Los bordes de las cajas aproximan el
              contacto. No garantizan distancia de seguridad.
            </p>
            <Button
              variant="outline"
              onClick={() => {
                setMode("calibration");
                setFrame("");
                setFirstFrame(false);
                update({
                  ...doc,
                  calibration: {
                    image_points: [],
                    ground_points_m: [],
                    status: "valid",
                    source_sha256: session.source_sha256,
                    version: (doc.calibration?.version ?? 0) + 1,
                    calibrated_at: new Date().toISOString(),
                    units: "m",
                    zones_reviewed: false,
                  },
                });
              }}
            >
              Calibrar / recalibrar
            </Button>
            {data.saved?.calibration && (
              <GroundPreview calibration={data.saved.calibration} />
            )}
            {doc.calibration && (
              <>
                <p>
                  {doc.calibration.status === "invalid"
                    ? "Calibración invalidada."
                    : doc.calibration.zones_reviewed
                      ? "Referencias y zonas confirmadas."
                      : "Borrador pendiente de revisión."}{" "}
                  Seleccione al menos cuatro referencias distribuidas y escriba
                  sus coordenadas medidas sobre el suelo.
                </p>
                {doc.calibration.framing_reference ? (
                  <p className="text-sm">
                    Capture el primer fotograma en «Referencias del suelo». El
                    Motor comprobará el fondo durante el análisis y suspenderá
                    la geometría si pierde la referencia.
                  </p>
                ) : (
                  <p className="text-sm">
                    Esta revisión usa invalidación manual del encuadre. Si
                    cambió la cámara, revise las zonas y vuelva a calibrar.
                  </p>
                )}
                {doc.calibration.status === "valid" && (
                  <label>
                    <input
                      type="checkbox"
                      checked={Boolean(doc.calibration.framing_reference)}
                      disabled={
                        !doc.calibration.framing_reference && !firstFrame
                      }
                      onChange={(event) => {
                        const calibration = doc.calibration!;
                        update({
                          ...doc,
                          calibration: {
                            ...calibration,
                            framing_reference: event.target.checked
                              ? "first_frame_orb_affine_v1"
                              : undefined,
                            zones_reviewed: false,
                          },
                        });
                      }}
                    />{" "}
                    Comprobar el encuadre automáticamente (experimental)
                  </label>
                )}
                {doc.calibration.ground_points_m.map((p, i) => (
                  <div key={i} className="flex flex-wrap gap-2">
                    {p.map((v, a) => (
                      <label key={a}>
                        Referencia {i + 1} · {a ? "Y" : "X"} (m)
                        <input
                          className="input"
                          type="number"
                          step=".01"
                          value={v}
                          onChange={(e) =>
                            update({
                              ...doc,
                              calibration: {
                                ...doc.calibration!,
                                ground_points_m:
                                  doc.calibration!.ground_points_m.map(
                                    (q, j) =>
                                      j === i
                                        ? (q.map((n, k) =>
                                            k === a
                                              ? Number(e.target.value)
                                              : n,
                                          ) as Point)
                                        : q,
                                  ),
                              },
                            })
                          }
                        />
                      </label>
                    ))}
                    <Button
                      variant="ghost"
                      onClick={() =>
                        update({
                          ...doc,
                          calibration: {
                            ...doc.calibration!,
                            image_points: doc.calibration!.image_points.filter(
                              (_, j) => j !== i,
                            ),
                            ground_points_m:
                              doc.calibration!.ground_points_m.filter(
                                (_, j) => j !== i,
                              ),
                          },
                        })
                      }
                    >
                      Quitar referencia {i + 1}
                    </Button>
                  </div>
                ))}
                <label>
                  <input
                    type="checkbox"
                    checked={doc.calibration.zones_reviewed}
                    onChange={(e) =>
                      update({
                        ...doc,
                        calibration: {
                          ...doc.calibration!,
                          zones_reviewed: e.target.checked,
                        },
                      })
                    }
                  />{" "}
                  Confirmo cámara fija, referencias medidas y zonas revisadas
                  para este encuadre
                </label>
                <Button
                  variant="outline"
                  onClick={() =>
                    update({
                      ...doc,
                      calibration: { ...doc.calibration!, status: "invalid" },
                      zones: doc.zones.map((z) => ({ ...z, enabled: false })),
                    })
                  }
                >
                  Marcar encuadre inválido en el borrador
                </Button>
              </>
            )}
            <MotionConfiguration
              motion={doc.motion}
              relations={doc.relations}
              metricAvailable={doc.calibration?.status === "valid"}
              onMotion={(motion) => {
                if (
                  !motion &&
                  doc.rules.some(
                    (r) =>
                      r.enabled && r.parameters.motion_condition === "moving",
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
            <h3 data-guide="rules">Reglas</h3>
            {doc.rules.map((rule, i) => (
              <div
                key={i}
                className="grid gap-2 rounded-xl border border-border p-3"
              >
                <label>
                  ID de regla
                  <input
                    className="input"
                    value={rule.rule_id}
                    onChange={(e) =>
                      update({
                        ...doc,
                        rules: doc.rules.map((r, j) =>
                          j === i ? { ...r, rule_id: e.target.value } : r,
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
                          j === i ? { ...r, enabled: e.target.checked } : r,
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
                              kind === "zone_coexistence" ? Math.SQRT2 : 0.1,
                            minimum_duration_seconds: 1,
                          }
                        : {
                            kind,
                            zone_id: zone?.zone_id ?? "",
                            class_name: "person",
                            min_duration_s: kind === "zone_entry" ? 0 : 2,
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
                {rule.parameters.kind === "person_forklift_proximity" && (
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
                                      max_distance: Number(e.target.value),
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
            <p>
              Condición configurada satisfecha; requiere revisión humana, no
              confirma un incidente.
            </p>
            <div className="flex flex-wrap gap-3">
              <Button
                onClick={async () => {
                  setBusy(true);
                  setMessage("");
                  try {
                    const result = await request("PUT", {
                      document: doc,
                      revision: data.revision,
                    });
                    setData({ ...data, ...result, saved: result.document });
                    setDirty(false);
                    const response = await apiFetch(
                      `${base}/analysis/sessions/${session.id}/status/`,
                    );
                    if (!response.ok)
                      throw new Error("No se pudo actualizar el estado");
                    const status = await response.json();
                    if (!mounted.current) return;
                    onSaved(status);
                    setMessage(
                      "Configuración guardada para el próximo análisis.",
                    );
                  } catch (e) {
                    setMessage(e instanceof Error ? e.message : String(e));
                  } finally {
                    setBusy(false);
                  }
                }}
              >
                Guardar configuración
              </Button>
              <Button
                variant="outline"
                disabled={!data.saved}
                onClick={() => {
                  if (data.saved) {
                    // Revisión inmutable de esta misma fuente, no una edición geométrica.
                    setData({ ...data, document: structuredClone(data.saved) });
                    setDirty(true);
                    setMessage(
                      "Revisión cargada en el borrador. Guarde para aplicarla a la sesión.",
                    );
                  }
                }}
              >
                Recuperar guardada
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  if (
                    dirty &&
                    !window.confirm(
                      "¿Descartar los cambios espaciales sin guardar?",
                    )
                  )
                    return;
                  setOpen(false);
                  setData(null);
                  setFrame("");
                  setFirstFrame(false);
                  setSelected(0);
                }}
              >
                {dirty ? "Cancelar edición" : "Cerrar configuración"}
              </Button>
            </div>
          </fieldset>
        </div>
      )}
      <p role="status" className="mt-2 text-sm">
        {message}
      </p>
    </section>
  );
}
