"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { ArrowUpRight } from "lucide-react";
import { EventCount } from "@/components/motion/event-count";
import { enterTransition, sectionEntrance } from "@/lib/motion/presets";
import { eventTypeName } from "@/services/event-contract";
import { historyHref, type summarizeApiHistory } from "./history-model";
import styles from "./analytics-charts.module.css";

export function IndicatorMetrics({
  summary,
  busiest,
  period,
  previousTotal,
  loading,
  filters,
}: {
  summary: ReturnType<typeof summarizeApiHistory>;
  busiest: { hour: number; count: number };
  period: string;
  previousTotal?: number;
  loading: boolean;
  filters: URLSearchParams;
}) {
  const reducedMotion = useReducedMotion();
  const zone = summary.zones[0];
  const type = summary.types[0];
  const video = summary.videos[0];
  const hour = `${String(busiest.hour).padStart(2, "0")}:00`;
  const largest = Math.max(1, ...summary.days.map(({ count }) => count));
  const metrics = [
    {
      title: "Zona con más registros",
      label: zone?.label,
      count: zone?.count,
      tied: zone && summary.zones[1]?.count === zone.count,
      href: zone && historyHref(filters, { zone_id: zone.label }),
    },
    {
      title: "Tipo predominante",
      label: type && eventTypeName(type.label),
      count: type?.count,
      tied: type && summary.types[1]?.count === type.count,
      href: type && historyHref(filters, { event_type: type.label }),
    },
    {
      title: "Hora más frecuente · Santiago",
      label: busiest.count ? hour : undefined,
      count: busiest.count || undefined,
      tied: summary.hours.some(
        ({ hour, count }) => hour !== busiest.hour && count === busiest.count,
      ),
    },
    {
      title: "Video con más registros",
      label: video?.name,
      count: video?.count,
      tied: video && summary.videos[1]?.count === video.count,
      href: video && historyHref(filters, { source_sha256: video.sha }),
    },
  ];

  return (
    <motion.section
      className={styles.kpis}
      aria-label="Resumen de indicadores"
      aria-busy={loading}
      initial={reducedMotion || previousTotal !== undefined ? false : "hidden"}
      animate="visible"
      transition={{ staggerChildren: reducedMotion ? 0 : 0.045 }}
    >
      <motion.div
        className={styles.totalCard}
        variants={sectionEntrance}
        transition={enterTransition}
      >
        <div className={styles.totalHeading}>
          <h3>Eventos registrados</h3>
          <Link
            href={historyHref(filters)}
            aria-label="Ver eventos del período"
          >
            <ArrowUpRight size={17} aria-hidden="true" />
          </Link>
        </div>
        <strong className={styles.totalValue}>
          <EventCount value={summary.total} from={previousTotal} />
        </strong>
        <p>{period}</p>
        {summary.total > 0 && (
          <div className={styles.miniChart} aria-hidden="true">
            <div>
              {summary.days.map(({ day, count }) => (
                <span
                  key={day}
                  style={{ height: `${(count / largest) * 100}%` }}
                />
              ))}
            </div>
            <span>Actividad diaria · UTC</span>
          </div>
        )}
      </motion.div>
      {summary.total > 0 && (
        <div className={styles.secondaryMetrics}>
          {metrics.map(({ title, label, count, href, tied }) => (
            <motion.div
              key={title}
              className={styles.metricCard}
              variants={sectionEntrance}
              transition={enterTransition}
            >
              <h3>{title}</h3>
              {href ? (
                <Link className={styles.metricValue} href={href} title={label}>
                  <span>{label}</span>
                </Link>
              ) : (
                <strong className={styles.metricValue} title={label}>
                  {label ?? "—"}
                </strong>
              )}
              <small>
                {count === undefined ? (
                  "Sin registros"
                ) : (
                  <>
                    <EventCount value={count} />{" "}
                    {count === 1 ? "evento" : "eventos"}
                    {tied && " · empate"}
                  </>
                )}
              </small>
            </motion.div>
          ))}
        </div>
      )}
    </motion.section>
  );
}

type RankingRow = {
  key: string;
  label: string;
  detail?: string;
  count: number;
  href: string;
};

export function IndicatorRanking({
  title,
  rows,
  total,
  caption,
  empty,
}: {
  title: string;
  rows: RankingRow[];
  total: number;
  caption?: string;
  empty?: string;
}) {
  return (
    <section className={`insight-panel ${styles.contextCard}`}>
      <div className="panel-heading">
        <h3>{title}</h3>
      </div>
      {rows.length > 0 ? (
        <ol className={styles.ranking}>
          {rows.map(({ key, label, detail, count, href }) => (
            <li key={key}>
              <Link href={href} title={detail ? `${label} · ${detail}` : label}>
                <span>
                  {label}
                  {detail && <small> · {detail}</small>}
                </span>
                <strong>{count}</strong>
              </Link>
              <div className={styles.rankingTrack} aria-hidden="true">
                <span style={{ width: `${(count / total) * 100}%` }} />
              </div>
            </li>
          ))}
        </ol>
      ) : (
        <p className="insight-caption">{empty}</p>
      )}
      {caption && <p className="insight-caption">{caption}</p>}
    </section>
  );
}
