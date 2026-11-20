"use client";

import { useState, type CSSProperties } from "react";
import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { enterTransition } from "@/lib/motion/presets";
import { dayUtcBounds, historyHref, weekdays } from "./history-model";
import { spatialColumns, spatialRows, spatialHistory } from "./spatial-history";
import styles from "./analytics-charts.module.css";

function intensity(count: number, max: number) {
  return {
    "--intensity": count ? `${16 + (count / Math.max(max, 1)) * 30}%` : "0%",
  } as CSSProperties;
}

export function DailyEvents({
  month,
  days,
  filters,
  queryKey,
}: {
  month: string;
  days: { day: number; count: number }[];
  filters: URLSearchParams;
  queryKey: string;
}) {
  const reducedMotion = useReducedMotion();
  const largest = Math.max(1, ...days.map(({ count }) => count));
  const step = Math.ceil(largest / 4);
  const max = Math.ceil(largest / step) * step;
  const axis = Array.from({ length: max / step + 1 }, (_, i) => max - i * step);
  const href = (day: number) => historyHref(filters, dayUtcBounds(month, day));
  return (
    <section
      className={`insight-panel ${styles.daily}`}
      aria-labelledby="daily-events"
    >
      <div className="panel-heading">
        <div>
          <h3 id="daily-events">Eventos por día</h3>
        </div>
      </div>
      <p className={styles.axisTitle}>Cantidad de eventos</p>
      <div
        className={styles.chartScroll}
        tabIndex={0}
        role="region"
        aria-label="Barras diarias, desplazamiento horizontal disponible"
      >
        <div className={styles.chartFrame}>
          <div className={styles.axis} aria-hidden="true">
            {axis.map((value) => (
              <span key={value}>{value}</span>
            ))}
          </div>
          <ol
            className={styles.bars}
            style={
              {
                "--days": days.length,
                "--chart-lines": axis.length - 1,
              } as CSSProperties
            }
          >
            {days.map(({ day, count }) => {
              const label = `${String(day).padStart(2, "0")}/${month.slice(5)} UTC · ${count} ${count === 1 ? "evento" : "eventos"}`;
              return (
                <li key={day}>
                  <Link
                    href={href(day)}
                    title={label}
                    aria-label={`Ver histórico del ${label}`}
                    className={styles.barLink}
                  >
                    <motion.span
                      key={queryKey}
                      aria-hidden="true"
                      className={styles.bar}
                      style={{ height: `${(100 * count) / max}%` }}
                      initial={reducedMotion ? false : { scaleY: 0 }}
                      animate={{ scaleY: 1 }}
                      transition={
                        reducedMotion ? { duration: 0 } : enterTransition
                      }
                    />
                    <span className={styles.chartTooltip} aria-hidden="true">
                      {label}
                    </span>
                  </Link>
                  <span className={styles.day} aria-hidden="true">
                    {day}
                  </span>
                </li>
              );
            })}
          </ol>
        </div>
      </div>
      <p className={styles.axisCaption}>Día del mes · UTC</p>
      <details className="chart-data">
        <summary>Ver valores diarios</summary>
        <div className="daily-data">
          {days.map(({ day, count }) => (
            <Link key={day} className="text-link" href={href(day)}>
              {day}/{month.slice(5)} · {count}
            </Link>
          ))}
        </div>
      </details>
    </section>
  );
}

const slots = ["00–04", "04–08", "08–12", "12–16", "16–20", "20–24"];

export function HeatLegend({ max }: { max: number }) {
  return (
    <div className={styles.legend}>
      Frecuencia
      <span>
        <i style={intensity(0, max)} />0 eventos
      </span>
      {!!max && (
        <span>
          <i style={intensity(max, max)} />
          {max} {max === 1 ? "evento" : "eventos"}
        </span>
      )}
    </div>
  );
}

export function TemporalHeatmap({ matrix }: { matrix: number[][] }) {
  const reducedMotion = useReducedMotion();
  const max = Math.max(0, ...matrix.flat());
  return (
    <section
      className={`insight-panel ${styles.temporal}`}
      aria-labelledby="temporal-map"
    >
      <div className="panel-heading">
        <div>
          <h3 id="temporal-map">Mapa de calor temporal</h3>
          <p>
            Día de la semana y bloques de cuatro horas en Santiago de Chile.
          </p>
        </div>
      </div>
      <HeatLegend max={max} />
      <div
        className={styles.tableScroll}
        tabIndex={0}
        role="region"
        aria-label="Matriz temporal, bloques de cuatro horas"
      >
        <table className={styles.heatTable}>
          <thead>
            <tr>
              <th scope="col">Día</th>
              {slots.map((slot) => (
                <th key={slot} scope="col">
                  {slot}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, day) => (
              <motion.tr
                key={weekdays[day]}
                initial={reducedMotion ? false : { opacity: 0.75 }}
                animate={{ opacity: 1 }}
                transition={
                  reducedMotion
                    ? { duration: 0 }
                    : { ...enterTransition, delay: day * 0.025 }
                }
              >
                <th scope="row">{weekdays[day]}</th>
                {row.map((count, i) => (
                  <td
                    key={slots[i]}
                    data-empty={count === 0 || undefined}
                    style={intensity(count, max)}
                    title={`${weekdays[day]}, ${slots[i]} h · ${count} eventos`}
                  >
                    {count}
                  </td>
                ))}
              </motion.tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="insight-caption">
        El mes se selecciona en UTC. Un 0 indica que no hay registros de ese
        bloque en la selección.
      </p>
    </section>
  );
}

export function SpatialHeatmap({
  groups,
  total,
  back,
}: {
  groups: ReturnType<typeof spatialHistory>;
  total: number;
  back: string;
}) {
  const [key, setKey] = useState("");
  const [cell, setCell] = useState<{ key: string; index: number } | null>(null);
  const group = groups.find((item) => item.key === key) ?? groups[0];
  const max = group ? Math.max(...group.cells.map((ids) => ids.length)) : 0;
  const selected = cell?.key === group?.key ? cell?.index : undefined;
  return (
    <section
      className={`insight-panel ${styles.spatial}`}
      aria-labelledby="spatial-map"
    >
      <div className="panel-heading">
        <div>
          <h3 id="spatial-map">Mapa de calor espacial</h3>
          <p>
            {group
              ? "Cada cuadrícula localiza los puntos de proximidad de la persona en un mismo encuadre y ejecución."
              : "La selección no incluye puntos de proximidad con una referencia de fuente verificable."}
          </p>
        </div>
      </div>
      {group && (
        <div className={styles.spatialLayout}>
          <div className={styles.spatialInfo}>
            <label className={styles.spatialSelect}>
              Video y ejecución
              <select
                className="select-control"
                value={group.key}
                onChange={(event) => {
                  setKey(event.target.value);
                  setCell(null);
                }}
              >
                {groups.map((item, index) => (
                  <option key={item.key} value={item.key}>
                    {item.name} · grupo {index + 1} · {item.run.slice(0, 8)}
                    {item.epoch === null ? "" : ` · época ${item.epoch}`}
                  </option>
                ))}
              </select>
            </label>
            <HeatLegend max={max} />
            <p className="insight-caption">
              {group.total} de {total} eventos filtrados en este mapa. Las
              coordenadas son relativas a la imagen. La esquina superior
              izquierda es el origen.
            </p>
            {selected !== undefined && (
              <div className={styles.cellRecords} aria-live="polite">
                <p>Registros de la celda seleccionada</p>
                <ul>
                  {group.cells[selected].map((id) => (
                    <li key={id}>
                      <Link
                        className="text-link"
                        href={`/events/${encodeURIComponent(id)}?back=${encodeURIComponent(back)}`}
                      >
                        Ver expediente · {id.slice(0, 8)}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
          <div
            className={styles.spatialGrid}
            style={
              {
                "--columns": spatialColumns,
                "--rows": spatialRows,
              } as CSSProperties
            }
          >
            {group.cells.map((ids, index) => {
              const label = `Fila ${Math.floor(index / spatialColumns) + 1}, columna ${(index % spatialColumns) + 1} · ${ids.length} eventos`;
              return ids.length ? (
                <button
                  key={index}
                  type="button"
                  aria-label={label}
                  aria-pressed={selected === index}
                  title={label}
                  style={intensity(ids.length, max)}
                  onClick={() => setCell({ key: group.key, index })}
                >
                  {ids.length}
                </button>
              ) : (
                <span key={index} aria-hidden="true" title={label} />
              );
            })}
          </div>
        </div>
      )}
    </section>
  );
}
