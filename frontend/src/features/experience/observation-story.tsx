"use client";

import {
  ArrowLeft,
  ArrowRight,
  Check,
  Circle,
  Film,
  ImageIcon,
  Pause,
  Play,
  ScanLine,
} from "lucide-react";
import {
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
} from "motion/react";
import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { canOpen, useSession } from "@/features/auth/session-provider";
import { chapters } from "./chapters";
import { WarehouseScene } from "./warehouse-scene";
import { Warehouse3D } from "./warehouse-3d";
import {
  dossierBeat,
  lastBeat,
  secondsPerBeat,
  storyPose,
} from "./warehouse-timeline";

function RuleCheck({
  clock,
  index,
  label,
}: {
  clock: ReturnType<typeof useMotionValue<number>>;
  index: number;
  label: string;
}) {
  const opacity = useTransform(clock, (beat) => storyPose(beat).rules[index]);
  return (
    <li>
      <span className="experience-rule-icon" aria-hidden="true">
        <Circle size={15} />
        <motion.span style={{ opacity }}>
          <Check size={15} />
        </motion.span>
      </span>
      {label}
    </li>
  );
}

export function ObservationStory() {
  const [chapter, setChapter] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [illustrated, setIllustrated] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const stage = useRef<HTMLElement>(null);
  const clock = useMotionValue(0);
  const [target, setTarget] = useState<{ chapter: number } | null>(null);
  const [visible, setVisible] = useState(false);
  const [evidenceVisible, setEvidenceVisible] = useState(false);
  const [rulesVisible, setRulesVisible] = useState(false);
  const dossierOpacity = useTransform(
    clock,
    [dossierBeat - 0.22, dossierBeat],
    [0, 1],
  );
  const reduced = useReducedMotion();
  const { user } = useSession();
  const current = chapters[chapter];
  const last = chapter === chapters.length - 1;

  useMotionValueEvent(clock, "change", (beat) => {
    setEvidenceVisible(beat >= dossierBeat - 0.22);
    setRulesVisible(beat >= 3.31 && beat < 4.48);
    if (playing) setChapter(Math.min(lastBeat, Math.floor(beat + 0.0001)));
  });

  useEffect(() => {
    const element = stage.current;
    if (!element) return;
    let intersects = false;
    const sync = () => setVisible(intersects && !document.hidden);
    const observer = new IntersectionObserver(([entry]) => {
      intersects = entry.isIntersecting;
      sync();
    });
    observer.observe(element);
    document.addEventListener("visibilitychange", sync);
    return () => {
      observer.disconnect();
      document.removeEventListener("visibilitychange", sync);
    };
  }, []);

  useEffect(() => {
    if (playing) {
      if (!visible) return;
      const playback = animate(clock, lastBeat, {
        duration: Math.max(0.001, (lastBeat - clock.get()) * secondsPerBeat),
        ease: "linear",
        onComplete: () => setPlaying(false),
      });
      return () => playback.stop();
    }
    if (!target) return;
    if (reduced) {
      clock.jump(target.chapter);
      return;
    }
    const transition = animate(clock, target.chapter, {
      duration: Math.min(
        1.45,
        0.55 + Math.abs(target.chapter - clock.get()) * 0.21,
      ),
      ease: [0.42, 0, 0.22, 1],
    });
    return () => transition.stop();
  }, [clock, playing, reduced, target, visible]);

  function select(index: number) {
    setPlaying(false);
    setChapter(index);
    setTarget({ chapter: index });
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
            <div className="experience-view-options">
              <span>Simulación ilustrativa</span>
              {process.env.NODE_ENV === "development" && !unavailable && (
                <button
                  type="button"
                  aria-pressed={illustrated}
                  onClick={() => setIllustrated(!illustrated)}
                >
                  {illustrated ? "Volver a 3D" : "Comparar con SVG"}
                </button>
              )}
            </div>
          </div>
          {illustrated || unavailable ? (
            <WarehouseScene chapter={chapter} />
          ) : (
            <Warehouse3D
              chapter={chapter}
              clock={clock}
              reduced={Boolean(reduced)}
              onUnavailable={() => setUnavailable(true)}
            />
          )}
          {unavailable && (
            <p className="warehouse-fallback">
              Vista ilustrada · 3D no disponible en este navegador.
            </p>
          )}
          {(reduced ? chapter === 4 : rulesVisible) && (
            <ol className="experience-checks experience-glass">
              {["Proximidad", "Movimiento confirmado", "Duración"].map(
                (label, index) => (
                  <RuleCheck
                    key={label}
                    clock={clock}
                    index={index}
                    label={label}
                  />
                ),
              )}
            </ol>
          )}
          {(reduced ? last : evidenceVisible) && (
            <motion.div
              className="experience-dossier experience-glass"
              style={{ opacity: reduced ? 1 : dossierOpacity }}
            >
              <strong>Expediente ilustrativo</strong>
              <span>Proximidad · Regla de ejemplo</span>
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
              setTarget(null);
              if (last && clock.get() >= lastBeat) {
                clock.jump(0);
                setChapter(0);
              }
              setPlaying(!playing);
            }}
            aria-label={playing ? "Pausar historia" : "Reproducir historia"}
          >
            {playing ? <Pause size={18} /> : <Play size={18} />}
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
