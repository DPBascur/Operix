"use client";

import { ArrowLeft, ArrowRight, Compass, Crosshair, X } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import { createPortal } from "react-dom";
import { Magnet } from "@/components/effects/magnet";
import { SpotlightCard } from "@/components/effects/spotlight-card";
import { canOpen } from "@/features/auth/session-provider";
import { motionEase } from "@/lib/motion/presets";
import type { OperixUser } from "@/services/browser-session";
import { guideSteps, type GuideKind, type GuideStep } from "./guide-steps";

import {
  focusRect,
  positionGuide,
  visibleControl,
  type FocusRect,
} from "./guide-position";

const GUIDE_VERSION = 1;
const guideMotion = {
  travelMs: 560,
  scrollIdleMs: 120,
  appear: 0.32,
  content: 0.24,
};
type GuideView = {
  position: FocusRect | null;
  panel: { left: number; top: number } | null;
};
const withoutTarget: GuideView = { position: null, panel: null };

export function ExperienceGuide({
  user,
  open,
  onOpenChange,
}: {
  user: OperixUser;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const reduced = useReducedMotion();
  const key = `operix-guide:v${GUIDE_VERSION}:${user.username}`;
  const [unseen, setUnseen] = useState(false);
  const [kind, setKind] = useState<GuideKind | null>(null);
  const [index, setIndex] = useState(0);
  const [view, setView] = useState(withoutTarget);
  const [waiting, setWaiting] = useState(true);
  const [settledStep, setSettledStep] = useState<GuideStep | null>(null);
  const panel = useRef<HTMLElement>(null);
  const target = useRef<HTMLElement | null>(null);
  const title = useRef<HTMLHeadingElement>(null);
  const steps = useMemo(
    () =>
      kind
        ? guideSteps(kind, user.role).filter((item) =>
            canOpen(item.route, user.role),
          )
        : [],
    [kind, user.role],
  );
  const step = steps[index];
  const onRoute = Boolean(
    step &&
    (pathname === step.route ||
      (step.matchPrefix && pathname.startsWith(step.route + "/"))),
  );
  const ready = !step || (onRoute && settledStep === step);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      try {
        setUnseen(!localStorage.getItem(key));
      } catch {
        setUnseen(true);
      }
    });
    return () => cancelAnimationFrame(frame);
  }, [key]);

  useEffect(() => {
    if (!open || !ready) return;
    const frame = requestAnimationFrame(() =>
      title.current?.focus({ preventScroll: true }),
    );
    return () => cancelAnimationFrame(frame);
  }, [open, ready, step]);

  useEffect(() => {
    if (!open) return;
    function escape(event: KeyboardEvent) {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (document.querySelector("dialog[open]")) return;
      event.preventDefault();
      setKind(null);
      onOpenChange(false);
      document
        .getElementById("operix-guide-launcher")
        ?.focus({ preventScroll: true });
    }
    document.addEventListener("keydown", escape);
    return () => document.removeEventListener("keydown", escape);
  }, [open, onOpenChange]);

  useEffect(() => {
    if (!open || !step || !onRoute) return;
    let frame = 0;
    let previous: HTMLElement | null = null;
    let revealed: HTMLElement | null = null;
    let settleTimer: number | undefined;
    let scrollTimer: number | undefined;
    let scrolling = false;
    let expired = false;
    const resize = new ResizeObserver(schedule);
    if (panel.current) resize.observe(panel.current);

    function measure() {
      if (!step || !panel.current) return;
      const active = visibleControl(step.target);
      if (active !== previous) {
        if (previous) resize.unobserve(previous);
        previous = active;
        if (active) resize.observe(active);
      }
      target.current = active;
      if (!active) {
        setView(withoutTarget);
        if (expired) setSettledStep(step);
        return;
      }

      const width = document.documentElement.clientWidth;
      const height = window.innerHeight;
      const space = () => {
        const position = focusRect(active);
        return position
          ? {
              position,
              panel: positionGuide(
                position,
                panel.current!.offsetWidth,
                panel.current!.offsetHeight,
                width,
                height,
              ),
            }
          : withoutTarget;
      };
      if (scrolling) return;
      let next = space();
      if (revealed !== active) {
        revealed = active;
        if (!next.position || !next.panel) {
          if (!reduced) {
            scrolling = true;
            scrollTimer = window.setTimeout(
              endScroll,
              guideMotion.scrollIdleMs,
            );
          }
          active.scrollIntoView({
            block: "center",
            inline: "nearest",
            behavior: reduced ? "instant" : "smooth",
          });
          if (scrolling) return;
          next = space();
        }
      }
      setView((old) =>
        JSON.stringify(old) === JSON.stringify(next) ? old : next,
      );
      if (next.position && settleTimer === undefined) {
        settleTimer = window.setTimeout(
          () => setSettledStep(step),
          reduced ? 0 : guideMotion.travelMs,
        );
      } else if (!next.position && expired) {
        setSettledStep(step);
      }
    }

    function endScroll() {
      scrolling = false;
      schedule();
    }

    function onScroll() {
      if (scrolling) {
        clearTimeout(scrollTimer);
        scrollTimer = window.setTimeout(endScroll, guideMotion.scrollIdleMs);
      } else schedule();
    }

    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    }
    const mutations = new MutationObserver(schedule);
    const main = document.querySelector("main");
    if (main) {
      resize.observe(main);
      mutations.observe(main, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: [
          "open",
          "hidden",
          "disabled",
          "aria-pressed",
          "aria-expanded",
        ],
      });
    }
    window.addEventListener("scroll", onScroll, {
      passive: true,
      capture: true,
    });
    window.addEventListener("resize", schedule);
    window.visualViewport?.addEventListener("resize", schedule);
    schedule();
    const timeout = window.setTimeout(() => {
      expired = true;
      setWaiting(false);
      // A disclosure can move a control after its first measurable layout.
      if (previous && !focusRect(previous)) revealed = null;
      schedule();
    }, 1100);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timeout);
      clearTimeout(scrollTimer);
      clearTimeout(settleTimer);
      mutations.disconnect();
      resize.disconnect();
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", schedule);
      window.visualViewport?.removeEventListener("resize", schedule);
      target.current = null;
    };
  }, [open, onRoute, pathname, reduced, step]);

  function remember() {
    setUnseen(false);
    try {
      localStorage.setItem(key, "seen");
    } catch {
      /* La guía sigue disponible en Ayuda. */
    }
  }

  function close() {
    remember();
    onOpenChange(false);
    setKind(null);
    document
      .getElementById("operix-guide-launcher")
      ?.focus({ preventScroll: true });
  }

  function openStep(next: GuideStep, nextIndex: number) {
    setIndex(nextIndex);
    setWaiting(true);
    setSettledStep(null);
    const matches =
      pathname === next.route ||
      (next.matchPrefix && pathname.startsWith(next.route + "/"));
    if (!matches) {
      setView(withoutTarget);
      router.push(next.route);
    }
  }

  function begin(selection: GuideKind) {
    remember();
    setKind(selection);
    const first = guideSteps(selection, user.role)[0];
    openStep(first, 0);
  }

  if (!open) {
    return unseen && pathname !== "/experience" ? (
      <SpotlightCard
        className="experience-invite experience-glass"
        role="complementary"
        aria-label="Introducción de Operix"
      >
        <Compass size={21} aria-hidden="true" />
        <div>
          <strong>Descubre cómo funciona Operix</strong>
          <div className="experience-invite-actions">
            <Magnet maxOffset={3}>
              <button
                className="button button-outline"
                type="button"
                onClick={() => onOpenChange(true)}
              >
                Comenzar tutorial
              </button>
            </Magnet>
            <button type="button" onClick={remember}>
              Omitir
            </button>
          </div>
        </div>
      </SpotlightCard>
    ) : null;
  }

  const spotlight = onRoute && view.position;

  return createPortal(
    <div className="experience-guide-layer">
      {step && (
        <svg
          className="experience-veil"
          aria-hidden="true"
          data-focused={!!spotlight}
          style={
            { "--guide-travel": `${guideMotion.travelMs}ms` } as CSSProperties
          }
        >
          <defs>
            <mask id="experience-spotlight">
              <rect width="100%" height="100%" fill="white" />
              <rect
                className="experience-aperture"
                fill="black"
                style={
                  spotlight
                    ? {
                        x: spotlight.left + "px",
                        y: spotlight.top + "px",
                        width: spotlight.width,
                        height: spotlight.height,
                        rx: spotlight.radius + "px",
                      }
                    : { width: 0, height: 0 }
                }
              />
            </mask>
          </defs>
          <rect width="100%" height="100%" mask="url(#experience-spotlight)" />
        </svg>
      )}
      <motion.aside
        ref={panel}
        className="experience-guide experience-glass"
        data-position={onRoute && view.panel ? "anchored" : "fallback"}
        data-moving={!ready && Boolean(view.panel)}
        style={
          {
            ...(onRoute && view.panel ? view.panel : undefined),
            "--guide-travel": `${guideMotion.travelMs}ms`,
          } as CSSProperties
        }
        aria-labelledby="experience-guide-title"
        initial={reduced ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: guideMotion.appear, ease: motionEase.enter }}
      >
        <div className="experience-guide-meta">
          <span>
            {kind === "analysis" ? "Primer análisis" : "Guía de Operix"}
            {step && ` · ${index + 1} de ${steps.length}`}
            {!ready && <span role="status"> · Buscando control…</span>}
          </span>
          <button
            type="button"
            className="experience-icon-button"
            aria-label="Cerrar guía"
            onClick={close}
          >
            <X size={18} aria-hidden="true" />
          </button>
        </div>
        {step && (
          <div
            className="experience-guide-progress"
            role="progressbar"
            aria-label="Progreso de la guía"
            aria-valuenow={index + 1}
            aria-valuemin={0}
            aria-valuemax={steps.length}
          >
            <span
              style={{ transform: `scaleX(${(index + 1) / steps.length})` }}
            />
          </div>
        )}
        <motion.div
          key={step?.target ?? "menu"}
          inert={!ready}
          className="experience-guide-content"
          data-ready={ready}
          initial={false}
          animate={{ opacity: ready ? 1 : 0 }}
          transition={{
            duration: reduced ? 0 : guideMotion.content,
            ease: motionEase.enter,
          }}
        >
          <h2 ref={title} id="experience-guide-title" tabIndex={-1}>
            {step?.title ?? "Descubre cómo funciona Operix"}
          </h2>
          {step ? (
            <>
              <p>{step.description}</p>
              {!onRoute && (
                <p role="status">
                  Abriendo la sección…{" "}
                  <Link href={step.route}>Ir a la sección</Link>
                </p>
              )}
              {onRoute && !spotlight && (
                <p role="status">
                  {waiting
                    ? "Esperando que cargue la vista…"
                    : (step.optional ??
                      "El control no está disponible ahora. Puedes continuar con la guía.")}
                </p>
              )}
              {spotlight && (
                <button
                  type="button"
                  className="experience-target-action"
                  onClick={() => {
                    const active = target.current;
                    if (!active) return;
                    const focusable =
                      "button:not(:disabled), a[href], summary, select:not(:disabled), input:not(:disabled)";
                    const control = active.matches(focusable)
                      ? active
                      : [
                          ...active.querySelectorAll<HTMLElement>(focusable),
                        ].find((item) => item.getClientRects().length > 0);
                    (control ?? active).scrollIntoView({
                      block: "center",
                      behavior: "instant",
                    });
                    control?.focus({ preventScroll: true });
                  }}
                >
                  <Crosshair size={16} aria-hidden="true" /> Ir al control
                </button>
              )}
              <div className="experience-guide-actions">
                <button
                  type="button"
                  className="button button-outline"
                  onClick={() =>
                    index > 0
                      ? openStep(steps[index - 1], index - 1)
                      : setKind(null)
                  }
                >
                  <ArrowLeft size={16} aria-hidden="true" /> Atrás
                </button>
                <button
                  type="button"
                  className="button button-primary"
                  onClick={() =>
                    index + 1 < steps.length
                      ? openStep(steps[index + 1], index + 1)
                      : close()
                  }
                >
                  {index + 1 < steps.length ? "Siguiente" : "Terminar"}{" "}
                  <ArrowRight size={16} aria-hidden="true" />
                </button>
              </div>
            </>
          ) : (
            <>
              <p>
                Explora la bodega ilustrada o practica el recorrido sobre la
                interfaz de trabajo.
              </p>
              <div className="experience-guide-options">
                <Link
                  className="button button-primary"
                  href="/experience"
                  onClick={close}
                >
                  Ver historia animada{" "}
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
                <button
                  type="button"
                  className="button button-outline"
                  onClick={() => begin("overview")}
                >
                  Recorrer Operix
                </button>
                <button
                  type="button"
                  className="button button-outline"
                  onClick={() => begin("analysis")}
                >
                  Realiza tu primer análisis
                </button>
              </div>
            </>
          )}
        </motion.div>
      </motion.aside>
    </div>,
    document.body,
  );
}
