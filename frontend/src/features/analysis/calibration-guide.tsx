import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import type { NormalizedVertex as Point } from "@/services/analysis.service";
import type { PatternEvidence } from "@/services/automatic-calibration.service";
import { SpatialFrame } from "./spatial-frame";
import { pointInFrame, validPolygon } from "./zone-editor-geometry";
import styles from "./analysis.module.css";

export type Calibration = {
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
  pattern_evidence?: PatternEvidence;
};

const steps = ["Unidades", "Referencias", "Medidas", "Validar", "Guardar"];

function hull(points: Point[]) {
  const ordered = [...points].sort(([ax, ay], [bx, by]) => ax - bx || ay - by);
  function half(points: Point[]) {
    const edge: Point[] = [];
    for (const p of points) {
      while (edge.length >= 2) {
        const [a, b] = edge.slice(-2);
        if ((b[0] - a[0]) * (p[1] - a[1]) > (b[1] - a[1]) * (p[0] - a[0]))
          break;
        edge.pop();
      }
      edge.push(p);
    }
    return edge.slice(0, -1);
  }
  return [...half(ordered), ...half(ordered.reverse())];
}

export function calibrationCheck(calibration: Calibration): string | null {
  const { image_points: image, ground_points_m: ground } = calibration;
  if (image.length < 4 || image.length > 16 || ground.length !== image.length)
    return "Marca entre cuatro y dieciséis referencias.";
  if (
    ground.some((p) =>
      p.some((v) => !Number.isFinite(v) || Math.abs(v) > 10000),
    )
  )
    return "Completa las medidas de suelo en metros.";
  if (
    image.some((p) => p.some((v) => !Number.isFinite(v) || v < 0 || v > 1)) ||
    [image, ground].some(
      (p) => hull(p).length < 3 || new Set(p.map(String)).size !== p.length,
    )
  )
    return "Distribuye las referencias sobre el suelo y evita puntos repetidos o alineados.";
  if (!calibration.zones_reviewed)
    return "Confirma que la cámara está fija y que revisaste las referencias y las zonas.";
  return null;
}

function GroundPlan({ calibration }: { calibration: Calibration }) {
  const points: Point[] = calibration.ground_points_m.map(([x, y]) => [x, -y]);
  if (!points.length || points.some((p) => !p.every(Number.isFinite)))
    return null;
  const left = Math.min(...points.map(([x]) => x));
  const top = Math.min(...points.map(([, y]) => y));
  const width = Math.max(...points.map(([x]) => x)) - left;
  const height = Math.max(...points.map(([, y]) => y)) - top;
  const marker = Math.max(width, height) / 40;
  if (!(marker > 0)) return null;
  return (
    <figure className={styles.plan}>
      <figcaption>
        {calibration.homography
          ? "Área validada para medir"
          : "Área de referencia propuesta"}{" "}
        · planta en metros
      </figcaption>
      <svg
        role="img"
        aria-label="Área entre las referencias medidas, vista desde arriba"
        viewBox={`${left - marker * 3} ${top - marker * 3} ${width + marker * 6} ${height + marker * 6}`}
      >
        <polygon
          points={hull(points).map(String).join(" ")}
          fill="currentColor"
          fillOpacity=".14"
          stroke="currentColor"
          strokeWidth={marker * 0.15}
        />
        {points.map(([x, y], i) => (
          <g key={i} fill="currentColor">
            <circle cx={x} cy={y} r={marker * 0.45} />
            <text
              x={x + marker * 0.6}
              y={y - marker * 0.35}
              fontSize={marker * 1.6}
            >
              {i + 1}
            </text>
          </g>
        ))}
      </svg>
    </figure>
  );
}

export function CalibrationGuide({
  calibration,
  sourceHash,
  sessionId,
  active,
  locked,
  onChange,
  onReview,
}: {
  calibration?: Calibration;
  sourceHash: string;
  sessionId: string;
  active: boolean;
  locked: boolean;
  onChange: (next: Calibration | undefined) => void;
  onReview: () => void;
}) {
  const [step, setStep] = useState(0);
  const [method, setMethod] = useState<"rectangle" | "coordinates">(
    "coordinates",
  );
  const [dimensions, setDimensions] = useState({ width: "", depth: "" });
  const [firstFrame, setFirstFrame] = useState(false);
  const [captureRevision, setCaptureRevision] = useState(0);
  const heading = useRef<HTMLHeadingElement>(null);
  const count = calibration?.image_points.length ?? 0;
  const referenceLimit = method === "rectangle" ? 4 : 16;
  const problem = calibration ? calibrationCheck(calibration) : null;

  function go(next: number) {
    setStep(next);
    requestAnimationFrame(() => heading.current?.focus());
  }

  function begin(nextMethod: typeof method) {
    setMethod(nextMethod);
    setDimensions({ width: "", depth: "" });
    setFirstFrame(false);
    setCaptureRevision((current) => current + 1);
    onChange({
      image_points: [],
      ground_points_m: [],
      status: "valid",
      source_sha256: sourceHash,
      version: (calibration?.version ?? 0) + 1,
      calibrated_at: new Date().toISOString(),
      units: "m",
      zones_reviewed: false,
    });
    go(1);
  }

  function changeGeometry(image_points: Point[], ground_points_m: Point[]) {
    if (!calibration) return;
    onChange({
      ...calibration,
      image_points,
      ground_points_m,
      zones_reviewed: false,
      homography: undefined,
      max_reference_error_m: undefined,
    });
  }

  function changeDimension(field: "width" | "depth", value: string) {
    if (!calibration) return;
    const next = { ...dimensions, [field]: value };
    setDimensions(next);
    const measure = (text: string) => (Number(text) > 0 ? Number(text) : NaN);
    const w = measure(next.width);
    const d = measure(next.depth);
    changeGeometry(calibration.image_points, [
      [0, 0],
      [w, 0],
      [w, d],
      [0, d],
    ]);
  }

  return (
    <div className={styles.taskBody}>
      <ol aria-label="Pasos de calibración" className={styles.guideSteps}>
        {steps.map((name, i) => (
          <li key={name} aria-current={i === step ? "step" : undefined}>
            {i + 1}. {name}
          </li>
        ))}
      </ol>
      <h3 ref={heading} tabIndex={-1}>
        {steps[step]}
      </h3>
      {step === 0 && (
        <>
          <p>
            ¿Necesitas medir en metros? Las reglas compatibles pueden usar
            distancias normalizadas en la imagen. Para medir en metros
            aproximados necesitas un suelo plano, una cámara fija y referencias
            medidas en el lugar.
          </p>
          {calibration && (
            <p className={styles.notice} role="status">
              {calibration.status === "invalid"
                ? "Encuadre invalidado."
                : calibration.homography && calibration.zones_reviewed
                  ? `Calibración validada · versión ${calibration.version}.`
                  : "Calibración en borrador."}
            </p>
          )}
          <div className={styles.actions}>
            {!calibration ||
            calibration.status === "invalid" ||
            calibration.pattern_evidence ? null : (
              <Button variant="outline" onClick={() => go(1)}>
                Revisar referencias
              </Button>
            )}
            <Button variant="outline" onClick={() => begin("rectangle")}>
              Usar un rectángulo medido
            </Button>
            <Button variant="outline" onClick={() => begin("coordinates")}>
              Usar puntos medidos
            </Button>
            {!calibration && (
              <Button variant="ghost" onClick={onReview}>
                Continuar sin metros
              </Button>
            )}
          </div>
          {calibration && (
            <>
              <GroundPlan calibration={calibration} />
              <details className={styles.advanced}>
                <summary>Opciones de calibración</summary>
                <div className={styles.actions}>
                  <Button
                    variant="outline"
                    onClick={() => {
                      if (
                        window.confirm(
                          "¿Quitar la calibración del borrador? Revisa las reglas que usan metros.",
                        )
                      )
                        onChange(undefined);
                    }}
                  >
                    Quitar calibración del borrador
                  </Button>
                </div>
              </details>
            </>
          )}
        </>
      )}
      {calibration && (
        <>
          <div hidden={step !== 1} className={styles.taskBody}>
            <p>
              {method === "rectangle"
                ? "Marca las cuatro esquinas de un rectángulo real sobre el suelo, en orden. El lado 1–2 corresponde al ancho y el 2–3 al fondo."
                : "Marca al menos cuatro puntos bien distribuidos sobre el mismo plano del suelo, en el orden en que los mediste."}
            </p>
            <SpatialFrame
              key={captureRevision}
              sessionId={sessionId}
              active={active && step === 1}
              locked={locked}
              firstFrame
              onCapture={() => setFirstFrame(true)}
            >
              <svg
                className={styles.pointOverlay}
                viewBox="0 0 100 100"
                preserveAspectRatio="none"
                role="img"
                aria-label="Editor de puntos"
                onPointerDown={(event) => {
                  if (locked || !firstFrame || count >= referenceLimit) return;
                  const point = pointInFrame(event);
                  if (point)
                    changeGeometry(
                      [...calibration.image_points, point],
                      [
                        ...calibration.ground_points_m.slice(0, count),
                        [NaN, NaN],
                      ],
                    );
                }}
              >
                <polygon
                  className={styles.floorArea}
                  points={hull(calibration.image_points)
                    .map(([x, y]) => `${x * 100},${y * 100}`)
                    .join(" ")}
                />
                {calibration.image_points.map(([x, y], i) => (
                  <g key={i} className={styles.referenceMarker}>
                    <text
                      x={Math.max(3, Math.min(97, x * 100))}
                      y={Math.max(7, Math.min(95, y * 100))}
                    >
                      {i + 1}
                    </text>
                  </g>
                ))}
              </svg>
            </SpatialFrame>
            <p role="status">
              {count} de {referenceLimit} referencias marcadas
            </p>
            {count > 0 && (
              <div className={styles.actions}>
                <Button
                  variant="secondary"
                  onClick={() =>
                    changeGeometry(
                      calibration.image_points.slice(0, -1),
                      calibration.ground_points_m.slice(0, count - 1),
                    )
                  }
                >
                  Deshacer última referencia
                </Button>
              </div>
            )}
            {method === "rectangle" &&
              count === 4 &&
              (!validPolygon(calibration.image_points) ||
                hull(calibration.image_points).length !== 4) && (
                <p role="status" className={styles.notice}>
                  Marca las cuatro esquinas en orden alrededor del rectángulo.
                </p>
              )}
          </div>
          {step === 2 && (
            <>
              {method === "rectangle" ? (
                <>
                  <p>
                    Mide con una cinta los dos lados del rectángulo real sobre
                    el suelo.
                  </p>
                  <div className={styles.fieldGrid}>
                    <label>
                      Ancho, lado 1–2 (m)
                      <input
                        className="input"
                        type="number"
                        min=".001"
                        max="10000"
                        step="any"
                        value={dimensions.width}
                        onChange={(e) =>
                          changeDimension("width", e.target.value)
                        }
                      />
                    </label>
                    <label>
                      Fondo, lado 2–3 (m)
                      <input
                        className="input"
                        type="number"
                        min=".001"
                        max="10000"
                        step="any"
                        value={dimensions.depth}
                        onChange={(e) =>
                          changeDimension("depth", e.target.value)
                        }
                      />
                    </label>
                  </div>
                </>
              ) : (
                <>
                  <p>
                    Usa un mismo origen y dos ejes perpendiculares. Escribe la
                    posición medida de cada marca sobre el suelo en metros.
                  </p>
                  {calibration.ground_points_m.map((point, i) => (
                    <div key={i} className={styles.fieldGrid}>
                      {point.map((value, axis) => (
                        <label key={axis}>
                          Referencia {i + 1} · {axis ? "Y" : "X"} (m)
                          <input
                            type="number"
                            className="input"
                            step="any"
                            min="-10000"
                            max="10000"
                            value={Number.isFinite(value) ? value : ""}
                            onChange={(e) =>
                              changeGeometry(
                                calibration.image_points,
                                calibration.ground_points_m.map((p, j) =>
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
                </>
              )}
            </>
          )}
          {step === 3 && (
            <>
              <GroundPlan calibration={calibration} />
              <p>
                El servicio comprueba la geometría al guardar. Solo se miden
                contactos dentro del área delimitada. El resultado es
                aproximado.
              </p>
              <label className={styles.check}>
                <input
                  type="checkbox"
                  checked={calibration.zones_reviewed}
                  onChange={(e) =>
                    onChange({
                      ...calibration,
                      zones_reviewed: e.target.checked,
                    })
                  }
                />
                Confirmo cámara fija, referencias medidas y zonas revisadas para
                este encuadre
              </label>
              <label className={styles.check}>
                <input
                  type="checkbox"
                  checked={Boolean(calibration.framing_reference)}
                  disabled={!firstFrame && !calibration.framing_reference}
                  onChange={(e) =>
                    onChange({
                      ...calibration,
                      framing_reference: e.target.checked
                        ? "first_frame_orb_affine_v1"
                        : undefined,
                    })
                  }
                />
                Comprobar el encuadre automáticamente (experimental)
              </label>
              <p>
                {calibration.framing_reference
                  ? "El análisis suspende las mediciones si pierde la referencia del encuadre."
                  : "Si cambia el encuadre, revisa las zonas y vuelve a calibrar. Captura el primer fotograma para activar la comprobación automática."}
              </p>
              {problem && (
                <p role="status" className={styles.notice}>
                  {problem}
                </p>
              )}
            </>
          )}
          {step === 4 && (
            <p>
              Revisa las zonas y reglas antes de guardar una revisión de esta
              fuente. Los metros se habilitan cuando el servicio valida la
              calibración y el encuadre lo permite.
            </p>
          )}
          {step > 0 && (
            <div className={styles.actions}>
              <Button variant="ghost" onClick={() => go(step - 1)}>
                Atrás
              </Button>
              {step < 4 ? (
                <Button
                  variant="outline"
                  disabled={
                    (step === 1 &&
                      (count < 4 ||
                        (method === "rectangle" &&
                          (!validPolygon(calibration.image_points) ||
                            hull(calibration.image_points).length !== 4)))) ||
                    (step === 2 &&
                      calibrationCheck({
                        ...calibration,
                        zones_reviewed: true,
                      }) !== null) ||
                    (step === 3 && problem !== null)
                  }
                  onClick={() => {
                    if (step === 1 && method === "rectangle")
                      changeDimension("width", dimensions.width);
                    go(step + 1);
                  }}
                >
                  {
                    [
                      "",
                      "Introducir medidas",
                      "Revisar área de medición",
                      "Continuar al guardado",
                    ][step]
                  }
                </Button>
              ) : (
                <Button variant="outline" onClick={onReview}>
                  Ir a revisión final
                </Button>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
