"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  Film,
  ImageIcon,
  Pause,
  Play,
  ScanLine,
} from "lucide-react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { canOpen, useSession } from "@/features/auth/session-provider";
import { chapters } from "./chapters";
import { WarehouseScene } from "./warehouse-scene";

export function ObservationStory() {
  const [chapter, setChapter] = useState(0);
  const [playing, setPlaying] = useState(false);
  const stage = useRef<HTMLElement>(null);
  const reduced = useReducedMotion();
  const { user } = useSession();
  const current = chapters[chapter];
  const last = chapter === chapters.length - 1;

  useEffect(() => {
    const element = stage.current;
    if (!playing || last || !element) return;
    let timer = 0;
    let visible = false;
    function schedule() {
      window.clearTimeout(timer);
      if (visible && !document.hidden) {
        timer = window.setTimeout(() => setChapter((index) => index + 1), 4800);
      }
    }
    const observer = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
      schedule();
    });
    observer.observe(element);
    document.addEventListener("visibilitychange", schedule);
    return () => {
      window.clearTimeout(timer);
      observer.disconnect();
      document.removeEventListener("visibilitychange", schedule);
    };
  }, [chapter, playing, last]);

  function select(index: number) {
    setPlaying(false);
    setChapter(index);
  }

  return (
    <div className="experience">
      <header className="experience-header">
        <h2>Cómo funciona Operix</h2>
        <p>La IA percibe el entorno. Las reglas interpretan el contexto.</p>
      </header>
      <div className="experience-grid">
        <section
          ref={stage}
          className="experience-stage"
          aria-label="Simulación visual de una bodega"
        >
          <div className="experience-stage-header">
            <span>
              <ScanLine size={16} aria-hidden="true" /> Vista de bodega
            </span>
            <span>Simulación ilustrativa</span>
          </div>
          <WarehouseScene chapter={chapter} />
          <AnimatePresence initial={false}>
            {chapter === 4 && (
              <motion.ol
                key="checks"
                className="experience-checks experience-glass"
                initial={reduced ? false : { opacity: 0 }}
                animate={{ opacity: 1 }}
                exit={{ opacity: 0 }}
              >
                {["Proximidad", "Movimiento confirmado", "Duración"].map(
                  (label, index) => (
                    <motion.li
                      key={label}
                      initial={reduced ? false : { opacity: 0, x: 8 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: reduced ? 0 : index * 0.2 }}
                    >
                      <Check size={15} aria-hidden="true" /> {label}
                    </motion.li>
                  ),
                )}
              </motion.ol>
            )}
            {last && (
              <motion.div
                key="dossier"
                className="experience-dossier experience-glass"
                initial={reduced ? false : { opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                transition={{
                  duration: reduced ? 0 : 0.32,
                  delay: reduced ? 0 : 0.63,
                }}
              >
                <strong>Expediente ilustrativo</strong>
                <span>Proximidad · Regla de ejemplo · 00:12</span>
                <ul>
                  <li>
                    <ImageIcon size={15} aria-hidden="true" /> Fotograma PNG
                  </li>
                  <li>
                    <Film size={15} aria-hidden="true" /> Clip del evento
                  </li>
                </ul>
              </motion.div>
            )}
          </AnimatePresence>
        </section>
        <div className="experience-chapter">
          <p className="experience-chapter-index">
            {String(chapter + 1).padStart(2, "0")} /{" "}
            {String(chapters.length).padStart(2, "0")}
          </p>
          <div aria-live={playing && !last ? "off" : "polite"}>
            <motion.div
              key={chapter}
              initial={reduced ? false : { opacity: 0.4 }}
              animate={{ opacity: 1 }}
              transition={{ duration: reduced ? 0 : 0.35 }}
            >
              <p className="experience-chapter-name">{current.name}</p>
              <h3>{current.title}</h3>
              <p>{current.description}</p>
              <div className="experience-detail">{current.detail}</div>
            </motion.div>
          </div>
          {last && user && (
            <Link
              className="button button-primary"
              href={canOpen("/events", user.role) ? "/events" : "/analysis"}
            >
              {canOpen("/events", user.role)
                ? "Abrir historial"
                : "Ir a Análisis"}{" "}
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          )}
        </div>
      </div>
      <div className="experience-toolbar experience-glass">
        <nav aria-label="Capítulos de la historia">
          {chapters.map((item, index) => (
            <button
              key={item.name}
              type="button"
              aria-current={chapter === index ? "step" : undefined}
              onClick={() => select(index)}
            >
              {item.name}
            </button>
          ))}
        </nav>
        <div
          className="experience-playback"
          aria-label="Controles de la historia"
        >
          <button
            type="button"
            disabled={chapter === 0}
            onClick={() => select(chapter - 1)}
            aria-label="Capítulo anterior"
          >
            <ArrowLeft size={18} />
          </button>
          <button
            type="button"
            onClick={() => {
              if (last) setChapter(0);
              setPlaying(last || !playing);
            }}
            aria-label={
              playing && !last ? "Pausar historia" : "Reproducir historia"
            }
          >
            {playing && !last ? <Pause size={18} /> : <Play size={18} />}
          </button>
          <button
            type="button"
            disabled={last}
            onClick={() => select(chapter + 1)}
            aria-label="Capítulo siguiente"
          >
            <ArrowRight size={18} />
          </button>
        </div>
      </div>
      <details className="experience-transcript">
        <summary>Leer los siete capítulos</summary>
        <ol>
          {chapters.map((item) => (
            <li key={item.name}>
              <strong>{item.name}</strong>
              <p>{item.description}</p>
            </li>
          ))}
        </ol>
      </details>
    </div>
  );
}
