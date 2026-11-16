"use client";

import { PageTitle } from "@/components/layout/page-title";
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
  X,
} from "lucide-react";
import {
  animate,
  motion,
  useMotionValue,
  useMotionValueEvent,
  useReducedMotion,
  useTransform,
} from "motion/react";
import Image from "next/image";
import Link from "next/link";
import {
  useCallback,
  useEffect,
  useId,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";
import { canOpen, useSession } from "@/features/auth/session-provider";
import { Aurora } from "@/components/effects/aurora";
import { Magnet } from "@/components/effects/magnet";
import { SplitText } from "@/components/effects/split-text";
import { SpotlightCard } from "@/components/effects/spotlight-card";
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

const staticLoginQuery = "(max-width: 767px), (prefers-reduced-motion: reduce)";
function watchLoginMedia(change: () => void) {
  const media = window.matchMedia(staticLoginQuery);
  media.addEventListener("change", change);
  return () => media.removeEventListener("change", change);
}
function staticLoginSnapshot() {
  const { deviceMemory } = navigator as Navigator & { deviceMemory?: number };
  return window.matchMedia(staticLoginQuery).matches ||
    (deviceMemory !== undefined && deviceMemory <= 2);
}

export function ObservationStory({ login = false }: { login?: boolean }) {
  const [chapter, setChapter] = useState(0);
  const [playing, setPlaying] = useState(login);
  const [returning, setReturning] = useState(false);
  const [unavailable, setUnavailable] = useState(false);
  const [sceneReady, setSceneReady] = useState(false);
  const handleSceneReady = useCallback(() => setSceneReady(true), []);
  const stage = useRef<HTMLElement>(null);
  const chaptersDialog = useRef<HTMLDialogElement>(null);
  const chaptersTitle = useId();
  const [chaptersOpen, setChaptersOpen] = useState(false);
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
  const staticLogin = useSyncExternalStore(
    watchLoginMedia,
    staticLoginSnapshot,
    () => true,
  );
  const staticPreview = login && (staticLogin || unavailable);
  const { user } = useSession();
  const current = chapters[chapter];
  const last = chapter === chapters.length - 1;

  useMotionValueEvent(clock, "change", (beat) => {
    if (returning) return;
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
    if (chaptersOpen || !visible) return;
    if (playing) {
      if (staticPreview || (login && !sceneReady)) return;
      if (returning) {
        const rewind = animate(clock, 0, {
          duration: Math.max(0.01, (clock.get() / lastBeat) * 2.5),
          delay: clock.get() === lastBeat ? 1.8 : 0,
          ease: [0.42, 0, 0.22, 1],
          onComplete: () => {
            setChapter(0);
            setEvidenceVisible(false);
            setRulesVisible(false);
            setReturning(false);
          },
        });
        return () => rewind.stop();
      }
      const playback = animate(clock, lastBeat, {
        duration: Math.max(0.001, (lastBeat - clock.get()) * secondsPerBeat),
        ease: "linear",
        onComplete: () => {
          if (login) setReturning(true);
          else setPlaying(false);
        },
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
  }, [
    clock,
    chaptersOpen,
    login,
    playing,
    reduced,
    returning,
    sceneReady,
    staticPreview,
    target,
    visible,
  ]);

  function select(index: number) {
    setReturning(false);
    setPlaying(false);
    setChapter(index);
    setTarget({ chapter: index });
  }

  const Caption = login ? SpotlightCard : "div";

  return (
    <div className={login ? "experience login-story" : "experience"}>
      {login && (
        <Aurora
          className="login-story-aurora"
          animate={!staticPreview}
          paused={!playing || !visible || !sceneReady || chaptersOpen}
        />
      )}
      {!login && (
        <header className="experience-header app-page-heading">
          <PageTitle>Cómo funciona Operix</PageTitle>
          <p>La IA percibe el entorno. Las reglas interpretan el contexto.</p>
        </header>
      )}
      <div className="experience-grid">
        <section
          ref={stage}
          className="experience-stage"
          data-returning={returning}
          data-chapter={chapter}
          aria-label="Simulación visual de una bodega"
        >
          <div className="experience-stage-header">
            <span>
              <ScanLine size={16} aria-hidden="true" /> Vista de bodega
            </span>
            <span className={login ? "login-story-label" : undefined}>
              Simulación ilustrativa
            </span>
            {login && !staticPreview && (
              <button
                className="login-story-play"
                type="button"
                aria-label={playing ? "Pausar historia" : "Reproducir historia"}
                onClick={() => {
                  setTarget(null);
                  setPlaying(!playing);
                }}
              >
                {playing ? <Pause size={16} /> : <Play size={16} />}
              </button>
            )}
          </div>
          {staticPreview ? (
            <Image
              className="login-story-poster"
              src="/experience/warehouse-reference.webp"
              width={1200}
              height={800}
              loading="eager"
              alt="Vista isométrica ilustrativa de una bodega"
              sizes="(max-width: 767px) 320px, 55vw"
            />
          ) : unavailable ? (
            <WarehouseScene chapter={chapter} />
          ) : (
            <Warehouse3D
              chapter={chapter}
              clock={clock}
              reduced={Boolean(reduced)}
              onReady={handleSceneReady}
              onUnavailable={() => setUnavailable(true)}
            />
          )}
          {unavailable && !login && (
            <p className="warehouse-fallback">
              Vista ilustrada · 3D no disponible en este navegador.
            </p>
          )}
          {!staticPreview &&
            !returning &&
            (reduced ? chapter === 4 : rulesVisible) && (
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
          {!staticPreview && (reduced ? last : evidenceVisible) && (
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
        <Caption className="experience-chapter">
          <p className="experience-chapter-index">
            {String(chapter + 1).padStart(2, "0")} /{" "}
            {String(chapters.length).padStart(2, "0")}
          </p>
          <div aria-live={playing ? "off" : "polite"}>
            <div key={chapter}>
              <p className="experience-chapter-name">{current.name}</p>
              <SplitText
                as="h3"
                text={current.title}
                animate={!staticPreview}
                staggerMs={26}
              />
              {login ? (
                <SplitText
                  as="p"
                  text={current.description}
                  animate={!staticPreview}
                  staggerMs={10}
                />
              ) : (
                <p>{current.description}</p>
              )}
              <div className="experience-detail">{current.detail}</div>
            </div>
          </div>
          {!login && last && user && (
            <Link
              className="button button-primary"
              href={canOpen("/events", user.role) ? "/events" : "/indicators"}
            >
              {canOpen("/events", user.role)
                ? "Abrir historial"
                : "Ver indicadores"}{" "}
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          )}
        </Caption>
      </div>
      {login && (
        <>
          <div className="login-story-actions">
            <Magnet maxOffset={4}>
              <button
                type="button"
                className="login-story-cta"
                aria-haspopup="dialog"
                onClick={() => {
                  chaptersDialog.current?.showModal();
                  setChaptersOpen(true);
                }}
              >
                Ver historia completa <ArrowRight size={16} aria-hidden="true" />
              </button>
            </Magnet>
          </div>
          <dialog
            ref={chaptersDialog}
            className="login-story-dialog"
            aria-labelledby={chaptersTitle}
            onClose={() => setChaptersOpen(false)}
          >
            <header>
              <h2 id={chaptersTitle}>Cómo funciona Operix</h2>
              <form method="dialog">
                <button type="submit" className="login-story-close" aria-label="Cerrar historia">
                  <X size={19} aria-hidden="true" />
                </button>
              </form>
            </header>
            <ol>
              {chapters.map((item, index) => (
                <li key={item.name}>
                  <div>
                    <strong>{item.name}</strong>
                    <p>{item.description}</p>
                  </div>
                  {!staticPreview && (
                    <button type="button" className="button button-outline"
                      aria-label={`Ver capítulo ${item.name}`}
                      onClick={() => {
                        select(index);
                        chaptersDialog.current?.close();
                      }}
                    >
                      Ver <ArrowRight size={14} aria-hidden="true" />
                    </button>
                  )}
                </li>
              ))}
            </ol>
          </dialog>
        </>
      )}
      {!login && (
        <>
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
        </>
      )}
    </div>
  );
}
