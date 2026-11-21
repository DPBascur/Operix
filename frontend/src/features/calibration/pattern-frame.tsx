/* eslint-disable @next/next/no-img-element -- Fotograma autenticado, cargado desde un blob. */
import { useState } from "react";
import { pointInFrame } from "@/features/analysis/zone-editor-geometry";
import type { NormalizedVertex as Point } from "@/services/analysis.service";
import type { PatternProposal } from "@/services/automatic-calibration.service";
import styles from "./automatic-calibration.module.css";

export type ReviewZone = {
  zone_id: string;
  name: string;
  polygon: Point[];
  enabled?: boolean;
};

export function PatternFrame({
  frame,
  proposal,
  points,
  zones,
  selectable,
  onPoint,
}: {
  frame: string;
  proposal: PatternProposal;
  points: Point[];
  zones: ReviewZone[];
  selectable: boolean;
  onPoint: (point: Point) => void;
}) {
  const [cursor, setCursor] = useState<Point>([0.5, 0.5]);
  const [loaded, setLoaded] = useState(false);
  const [failed, setFailed] = useState(false);
  const [showZones, setShowZones] = useState(false);
  const activeZones = zones.filter((zone) => zone.enabled !== false);
  const inFrame = selectable && loaded && !failed && points.length < 2;

  return (
    <figure className={styles.figure}>
      <div className={styles.frame}>
        <img
          src={frame}
          alt="Fotograma capturado para calibrar esta fuente"
          onLoad={() => setLoaded(true)}
          onError={() => setFailed(true)}
        />
        {loaded && !failed && (
          <>
            <svg
              viewBox="0 0 1 1"
              preserveAspectRatio="none"
              aria-hidden="true"
              className={styles.overlay}
            >
              <polygon
                className={styles.area}
                points={proposal.usable_polygon.join(" ")}
                vectorEffect="non-scaling-stroke"
              />
              {proposal.grid.map((line, index) => (
                <polyline
                  key={index}
                  className={styles.gridLine}
                  points={line.join(" ")}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              {proposal.references.map(({ id, corners }) => (
                <polygon
                  key={id}
                  className={styles.marker}
                  points={corners.join(" ")}
                  vectorEffect="non-scaling-stroke"
                />
              ))}
              {showZones &&
                activeZones.map((zone) => (
                  <polygon
                    key={zone.zone_id}
                    className={styles.zone}
                    points={zone.polygon.join(" ")}
                    vectorEffect="non-scaling-stroke"
                  />
                ))}
              {points.length === 2 && (
                <polyline
                  className={styles.controlLine}
                  points={points.join(" ")}
                  vectorEffect="non-scaling-stroke"
                />
              )}
            </svg>
            {points.map(([x, y], index) => (
              <span
                key={index}
                aria-hidden="true"
                className={styles.pin}
                style={{ left: `${x * 100}%`, top: `${y * 100}%` }}
              >
                {index + 1}
              </span>
            ))}
          </>
        )}
        {inFrame && (
          <button
            type="button"
            className={styles.pickPoint}
            aria-label={`Marcar punto de control ${points.length + 1}. Usa las flechas para mover el cursor y pulsa Intro para marcar.`}
            onClick={(event) => {
              const point = event.detail === 0 ? cursor : pointInFrame(event);
              if (point) onPoint(point);
            }}
            onKeyDown={(event) => {
              const directions: Record<string, Point> = {
                ArrowLeft: [-1, 0],
                ArrowRight: [1, 0],
                ArrowUp: [0, -1],
                ArrowDown: [0, 1],
              };
              const direction = directions[event.key];
              if (!direction) return;
              event.preventDefault();
              const step = event.shiftKey ? 0.002 : 0.01;
              setCursor(([x, y]) => [
                Math.min(1, Math.max(0, x + step * direction[0])),
                Math.min(1, Math.max(0, y + step * direction[1])),
              ]);
            }}
          >
            <span
              aria-hidden="true"
              className={styles.cursor}
              style={{
                left: `${cursor[0] * 100}%`,
                top: `${cursor[1] * 100}%`,
              }}
            />
          </button>
        )}
      </div>
      {failed ? (
        <p role="alert" className="inline-message is-error">
          El fotograma no pudo abrirse. Captura una propuesta nueva.
        </p>
      ) : (
        <figcaption className={styles.legend}>
          {proposal.usable_polygon.length > 0 && (
            <span>
              <i className={styles.areaKey} />
              Área evaluada
            </span>
          )}
          {proposal.grid.length > 0 && (
            <span>
              <i className={styles.gridKey} />
              Cuadrícula candidata
            </span>
          )}
          {proposal.references.length > 0 && (
            <span>
              <i className={styles.markerKey} />
              Marcadores detectados
            </span>
          )}
          {activeZones.length > 0 && (
            <label className={styles.check}>
              <input
                type="checkbox"
                checked={showZones}
                onChange={(event) => setShowZones(event.target.checked)}
              />{" "}
              Mostrar zonas activas ({activeZones.length})
            </label>
          )}
        </figcaption>
      )}
    </figure>
  );
}
