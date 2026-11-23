"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  automaticCalibrationService,
  CalibrationRequestError,
  type CalibrationSource,
  type PatternEvidence,
  type PatternProposal,
} from "@/services/automatic-calibration.service";
import type { NormalizedVertex as Point } from "@/services/analysis.service";
import {
  calibrationFrame,
  dictionary,
  maxMarkers,
  minMarkers,
  readControl,
  readLayout,
  type MarkerDraft,
} from "./calibration-input";
import { PatternFrame, type ReviewZone } from "./pattern-frame";
import styles from "./automatic-calibration.module.css";

const emptyMarker: MarkerDraft = {
  id: "",
  x_m: "",
  y_m: "",
  size_m: "",
  rotation_deg: "",
};
const markerFields = [
  ["id", "ID"],
  ["x_m", "X (m)"],
  ["y_m", "Y (m)"],
  ["size_m", "Lado (m)"],
  ["rotation_deg", "Giro (°)"],
] as const;
const statusLabels = {
  candidate: "Candidata",
  requires_review: "Requiere revisión",
  invalid: "Inválida",
};
const qualityFields = [
  ["reprojection_error_px", "Error de reproyección", "px", 1],
  ["coverage_ratio", "Cobertura del fotograma", "%", 100],
  ["temporal_error_px", "Variación entre fotogramas", "px", 1],
  ["condition_number", "Condición numérica", "", 1],
  ["sensitivity_m", "Sensibilidad a cambios en los puntos", "m", 1],
] as const;
const format = new Intl.NumberFormat("es-CL", { maximumSignificantDigits: 4 });
const reasonLabels: Record<string, string> = {
  no_frames: "No se pudo capturar un fotograma de esta fuente.",
  capture_failed:
    "No se pudo capturar la fuente. Revisa la señal y vuelve a intentar.",
  invalid_request: "Revisa las medidas y la disposición del patrón.",
  no_known_markers:
    "No se encontraron los marcadores declarados. Revisa sus identificadores, iluminación y visibilidad.",
  insufficient_consistent_markers:
    "Hay demasiados marcadores ocultos o visibles en pocos fotogramas.",
  canonical_fit_rejected:
    "Las referencias no permiten ajustar un plano de suelo estable.",
  inconsistent_marker_orientation:
    "La orientación detectada no coincide entre marcadores. Revisa los giros medidos.",
  insufficient_distribution:
    "Distribuye los marcadores por una parte más amplia del suelo.",
  insufficient_temporal_support: "El patrón debe verse en más fotogramas.",
  ambiguous_marker_ids:
    "Se detectaron identificadores ambiguos. Deja visible una sola copia de cada marcador.",
  unstable_markers:
    "La posición de los marcadores varía entre fotogramas. Revisa si la cámara o el patrón se movieron.",
  marker_layout_disagreement:
    "Las posiciones detectadas no coinciden con las medidas del patrón.",
  high_reprojection_error:
    "El ajuste geométrico tiene demasiado error. Revisa las medidas y la nitidez de los marcadores.",
  sensitive_fit:
    "El ajuste cambia demasiado ante pequeñas variaciones de las referencias.",
  control_distance_failed:
    "La distancia de comprobación supera la tolerancia declarada.",
};

type Saved = {
  status: string;
  version: number;
  zones_reviewed?: boolean;
  pattern_evidence?: PatternEvidence;
};

export function AutomaticCalibration<T>({
  source,
  zones,
  saved,
  blocked,
  framingWarning,
  id,
  onBusyChange,
  onSaved,
  onRefresh,
}: {
  source: CalibrationSource;
  zones: ReviewZone[];
  saved?: Saved | null;
  blocked?: string;
  framingWarning?: string;
  id?: string;
  onBusyChange: (busy: boolean) => void;
  onSaved: (result: T) => void;
  onRefresh: () => void;
}) {
  const helpId = useId();
  const markerId = useRef(minMarkers);
  const [markers, setMarkers] = useState(() =>
    Array.from({ length: minMarkers }, (_, key) => ({
      key,
      draft: emptyMarker,
    })),
  );
  const [provenance, setProvenance] = useState("");
  const [proposal, setProposal] = useState<PatternProposal>();
  const [frame, setFrame] = useState("");
  const [expired, setExpired] = useState(false);
  const [phase, setPhase] = useState<"capture" | "confirm">();
  const [message, setMessage] = useState("");
  const [refreshNeeded, setRefreshNeeded] = useState(false);
  const [points, setPoints] = useState<Point[]>([]);
  const [distance, setDistance] = useState("");
  const [tolerance, setTolerance] = useState("");
  const [controlSource, setControlSource] = useState("");
  const [groundConfirmed, setGroundConfirmed] = useState(false);
  const [zonesReviewed, setZonesReviewed] = useState(false);
  const [independent, setIndependent] = useState(false);
  const request = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const distanceInput = useRef<HTMLInputElement>(null);

  useEffect(() => () => request.current?.abort(), []);
  useEffect(() => {
    if (!proposal) return;
    const expiresAt = Date.parse(proposal.expires_at ?? "");
    const timer =
      proposal.status === "candidate" && Number.isFinite(expiresAt)
        ? setTimeout(
            () => setExpired(true),
            Math.max(0, expiresAt - Date.now()),
          )
        : undefined;
    heading.current?.focus();
    return () => clearTimeout(timer);
  }, [proposal]);

  const disabled = Boolean(blocked || phase || refreshNeeded);
  const layout = readLayout(
    markers.map(({ draft }) => draft),
    provenance,
  );
  const control = readControl(
    points.length === 2 ? [points[0], points[1]] : null,
    distance,
    tolerance,
    controlSource,
  );
  const canConfirm =
    proposal?.status === "candidate" &&
    Boolean(proposal.proposal_id && frame) &&
    proposal.usable_polygon.length >= 3 &&
    !expired;
  const ready =
    canConfirm && control && groundConfirmed && zonesReviewed && independent;
  const savedControl = saved?.pattern_evidence?.control;
  const validated =
    saved?.status === "valid" && saved.zones_reviewed && savedControl;

  const stage = canConfirm ? 2 : layout ? 1 : 0;

  async function run(operation: "capture" | "confirm") {
    if (disabled || request.current) return;
    if (operation === "capture" && !layout) return;
    if (
      operation === "confirm" &&
      (!ready ||
        !proposal?.proposal_id ||
        !(Date.parse(proposal.expires_at ?? "") > Date.now()))
    )
      return;
    const controller = new AbortController();
    request.current = controller;
    setPhase(operation);
    onBusyChange(true);
    setMessage("");
    let result: T | undefined;
    try {
      if (operation === "capture" && layout) {
        setProposal(undefined);
        setFrame("");
        setExpired(false);
        setPoints([]);
        setDistance("");
        setTolerance("");
        setControlSource("");
        setGroundConfirmed(false);
        setZonesReviewed(false);
        setIndependent(false);
        const next = await automaticCalibrationService.propose(
          source,
          layout,
          controller.signal,
        );
        const preview = calibrationFrame(next.preview_url);
        if (
          !Object.hasOwn(statusLabels, next.status) ||
          (next.preview_url && !preview) ||
          (next.status === "candidate" &&
            (!next.proposal_id ||
              !preview ||
              !Number.isFinite(Date.parse(next.expires_at ?? ""))))
        ) {
          throw new Error(
            "El servicio no devolvió una propuesta de calibración válida.",
          );
        }
        if (!controller.signal.aborted) {
          setFrame(preview ?? "");
          setProposal(next);
        }
      } else if (proposal?.proposal_id && control) {
        result = await automaticCalibrationService.confirm<T>(
          source,
          proposal.proposal_id,
          control,
          controller.signal,
        );
      }
    } catch (cause) {
      if (!controller.signal.aborted) {
        const interrupted =
          cause instanceof Error &&
          ["AbortError", "TimeoutError", "TypeError", "SyntaxError"].includes(
            cause.name,
          );
        setRefreshNeeded(
          (cause instanceof CalibrationRequestError && cause.status === 409) ||
            (interrupted && operation === "confirm"),
        );
        setMessage(
          cause instanceof Error && !interrupted
            ? cause.message
            : "Se interrumpió la comunicación. Comprueba el estado de la fuente antes de reintentar.",
        );
      }
    } finally {
      request.current = null;
      onBusyChange(false);
      if (!controller.signal.aborted) {
        setPhase(undefined);
        if (result !== undefined) onSaved(result);
      }
    }
  }

  return (
    <details id={id} className={styles.panel}>
      <summary>
        {source.kind === "cameras" ? "Calibrar distancias" : "Calibración automática con patrón"}{" "}
        {framingWarning ? (
          <span>· Revisar encuadre</span>
        ) : (
          validated ? <span>· Calibrada · v{saved.version}</span> : (source.kind === "cameras" && <span>· Sin calibrar</span>)
        )}
      </summary>
      <div className={styles.body}>
        {source.kind === "cameras" && (
          <ol className={styles.steps} aria-label="Pasos de calibración">
            {["Preparar referencias", "Buscar en el fotograma", "Comprobar y guardar"].map((label, index) => (
              <li key={label} aria-current={index === stage ? "step" : undefined}>
                <span>{index + 1}</span>{label}
              </li>
            ))}
          </ol>
        )}
        {source.kind === "cameras" && !validated && !framingWarning && (
          <p>La cámara muestra distancias normalizadas hasta que confirmes una escala del suelo con una medida conocida.</p>
        )}
        <p>
          Coloca marcadores ArUco {dictionary} planos sobre el suelo, con la
          cara impresa hacia la cámara. Distribúyelos por el área donde
          necesitas medir. Usa las coordenadas y el tamaño medidos en el suelo; Operix busca sus esquinas automáticamente.
        </p>
        {framingWarning ? (
          <p className="inline-message" role="status">
            {framingWarning}
          </p>
        ) : (
          saved?.pattern_evidence != null && (
            <p className="inline-message" role="status">
              {validated
                ? `Calibración validada para el área evaluada · versión ${saved.version}. Permite medidas aproximadas en metros dentro de esa área.`
                : "La calibración guardada requiere una nueva revisión del encuadre y las zonas."}
            </p>
          )
        )}
        {savedControl && (
          <div className={styles.quality}>
            <h4>Comprobación física guardada</h4>
            <dl>
              <div>
                <dt>Distancia medida</dt>
                <dd>{format.format(savedControl.distance_m)} m</dd>
              </div>
              <div>
                <dt>Distancia estimada</dt>
                <dd>{format.format(savedControl.observed_m)} m</dd>
              </div>
              <div>
                <dt>Error absoluto</dt>
                <dd>{format.format(savedControl.absolute_error_m)} m</dd>
              </div>
              <div>
                <dt>Error relativo</dt>
                <dd>{format.format(savedControl.relative_error * 100)} %</dd>
              </div>
              <div>
                <dt>Tolerancia declarada</dt>
                <dd>{format.format(savedControl.tolerance_m)} m</dd>
              </div>
            </dl>
            <p>Origen de la medida · {savedControl.provenance}</p>
          </div>
        )}
        {blocked && (
          <p className="inline-message" role="status">
            {blocked}
          </p>
        )}
        <fieldset disabled={disabled} className={styles.group}>
          <legend>Distribución medida de los marcadores</legend>
          <p id={helpId}>
            Registra de 3 a 8 marcadores con el mismo origen y ejes. X e Y son
            las coordenadas en metros de la esquina superior izquierda del borde
            negro, identificada con el marcador en su orientación original. Mide
            el lado del cuadrado negro de borde a borde. El giro es positivo de
            +X hacia +Y.
          </p>
          {markers.map(({ key, draft }, index) => (
            <fieldset
              className={styles.markerRow}
              key={key}
              aria-describedby={helpId}
            >
              <legend>Marcador {index + 1}</legend>
              <div className={styles.fields}>
                {markerFields.map(([field, label]) => (
                  <label key={field}>
                    {label}
                    <Input
                      maxLength={16}
                      inputMode={field === "id" ? "numeric" : "decimal"}
                      value={draft[field]}
                      onChange={(event) => {
                        const value = event.target.value;
                        setMarkers((rows) =>
                          rows.map((row) =>
                            row.key === key
                              ? { key, draft: { ...row.draft, [field]: value } }
                              : row,
                          ),
                        );
                        setProposal(undefined);
                        setFrame("");
                      }}
                    />
                  </label>
                ))}
              </div>
              {markers.length > minMarkers && (
                <Button
                  variant="ghost"
                  aria-label={`Quitar marcador ${index + 1}`}
                  onClick={() => {
                    setMarkers((rows) => rows.filter((row) => row.key !== key));
                    setProposal(undefined);
                    setFrame("");
                  }}
                >
                  Quitar
                </Button>
              )}
            </fieldset>
          ))}
          <div>
            <Button
              variant="outline"
              disabled={markers.length >= maxMarkers}
              onClick={() => {
                const key = markerId.current++;
                setMarkers((rows) => [...rows, { key, draft: emptyMarker }]);
                setProposal(undefined);
                setFrame("");
              }}
            >
              Agregar marcador
            </Button>
          </div>
          <label>
            Origen de las medidas del patrón
            <Input
              maxLength={250}
              value={provenance}
              onChange={(event) => {
                setProvenance(event.target.value);
                setProposal(undefined);
                setFrame("");
              }}
            />
          </label>
          {!layout && (
            <p>
              Completa todas las medidas y su procedencia. Usa IDs distintos de
              0 a 49, lados de 0,01 a 20 m y giros entre −360° y 360°.
            </p>
          )}
          <div>
            <Button
              loading={phase === "capture"}
              disabled={!layout}
              onClick={() => void run("capture")}
            >
              {phase === "capture"
                ? "Capturando y detectando…"
                : proposal
                  ? "Capturar nueva propuesta"
                  : "Capturar propuesta"}
            </Button>
          </div>
        </fieldset>

        {proposal && (
          <section
            className={styles.review}
            aria-labelledby={`${helpId}-review`}
          >
            <div className={styles.reviewTitle}>
              <h3 id={`${helpId}-review`} ref={heading} tabIndex={-1}>
                Revisar propuesta
              </h3>
              <strong>
                {expired ? "Caducada" : statusLabels[proposal.status]}
              </strong>
            </div>
            <p>
              La propuesta requiere comprobar la escala física antes de
              habilitar medidas en metros.
            </p>
            {!frame && (
              <p>
                No hay fotograma disponible para esta propuesta. Revisa la
                fuente y vuelve a capturar.
              </p>
            )}
            <div className={styles.reviewGrid}>
              {frame && (
                <PatternFrame
                  key={proposal.proposal_id}
                  frame={frame}
                  proposal={proposal}
                  points={points}
                  zones={zones}
                  selectable={canConfirm && !disabled}
                  onPoint={(point) => {
                    setPoints([...points, point]);
                    if (points.length === 1)
                      requestAnimationFrame(() =>
                        distanceInput.current?.focus(),
                      );
                  }}
                />
              )}
              <div className={styles.quality}>
                <h4>Calidad del ajuste geométrico</h4>
                <dl>
                  {qualityFields.map(([key, label, unit, scale]) => {
                    const value = proposal.quality[key];
                    return (
                      <div key={key}>
                        <dt>{label}</dt>
                        <dd>
                          {typeof value === "number" && Number.isFinite(value)
                            ? `${format.format(value * scale)}${unit ? ` ${unit}` : ""}`
                            : "Sin dato"}
                        </dd>
                      </div>
                    );
                  })}
                </dl>
                <p>
                  {proposal.references.length > 0
                    ? `Marcadores detectados · ${proposal.references.map(({ id }) => id).join(", ")}`
                    : "Sin marcadores detectados"}
                </p>
                {Boolean(proposal.reasons?.length) && (
                  <ul>
                    {proposal.reasons?.map((reason, index) => (
                      <li key={index}>{reasonLabels[reason] ?? reason}</li>
                    ))}
                  </ul>
                )}
              </div>
            </div>
            {expired && (
              <p role="status">
                La propuesta caducó. Captura una nueva para revisar el encuadre
                actual.
              </p>
            )}
            {canConfirm && (
              <fieldset disabled={disabled} className={styles.group}>
                <legend>Comprobación física independiente</legend>
                <p>
                  Marca dos puntos dentro del área evaluada que no pertenezcan
                  al patrón. Mide su separación en el suelo. Puedes marcar con
                  el puntero o mover el cursor con las flechas y pulsar Intro.
                </p>
                <div className={styles.pointActions}>
                  <span role="status">
                    {points.length} de 2 puntos marcados
                  </span>
                  <Button
                    variant="outline"
                    disabled={!points.length}
                    onClick={() => setPoints([])}
                  >
                    Volver a marcar
                  </Button>
                </div>
                <div className={styles.controlFields}>
                  <label>
                    Distancia medida (m)
                    <input
                      className="input"
                      ref={distanceInput}
                      inputMode="decimal"
                      value={distance}
                      onChange={(event) => setDistance(event.target.value)}
                    />
                  </label>
                  <label>
                    Error máximo aceptable (m)
                    <Input
                      inputMode="decimal"
                      value={tolerance}
                      onChange={(event) => setTolerance(event.target.value)}
                    />
                  </label>
                </div>
                <label>
                  Origen de la distancia medida
                  <Input
                    maxLength={250}
                    value={controlSource}
                    onChange={(event) => setControlSource(event.target.value)}
                  />
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={independent}
                    onChange={(event) => setIndependent(event.target.checked)}
                  />{" "}
                  Medí la distancia en el lugar entre dos puntos distintos de
                  las referencias del patrón.
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={groundConfirmed}
                    onChange={(event) =>
                      setGroundConfirmed(event.target.checked)
                    }
                  />{" "}
                  Confirmo que la cámara está fija y que el patrón y los puntos
                  de control están sobre el mismo plano del suelo.
                </label>
                <label className={styles.check}>
                  <input
                    type="checkbox"
                    checked={zonesReviewed}
                    onChange={(event) => setZonesReviewed(event.target.checked)}
                  />{" "}
                  Revisé el área evaluada y las zonas de esta fuente.
                </label>
                {points.length === 2 && !control && (
                  <p>
                    Usa puntos distintos, una distancia positiva y un error
                    máximo positivo menor que la distancia. Indica cómo
                    obtuviste la medida.
                  </p>
                )}
                <div>
                  <Button
                    disabled={!ready}
                    loading={phase === "confirm"}
                    onClick={() => void run("confirm")}
                  >
                    {phase === "confirm"
                      ? "Validando…"
                      : "Validar medida y guardar"}
                  </Button>
                </div>
              </fieldset>
            )}
          </section>
        )}
        {message && (
          <p role="alert" className="inline-message is-error">
            {message}
          </p>
        )}
        {refreshNeeded && (
          <div>
            <Button
              variant="outline"
              disabled={Boolean(blocked || phase)}
              onClick={() => {
                setProposal(undefined);
                setFrame("");
                setMessage("");
                setRefreshNeeded(false);
                onRefresh();
              }}
            >
              Actualizar configuración
            </Button>
          </div>
        )}
      </div>
    </details>
  );
}
