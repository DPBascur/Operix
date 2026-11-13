"use client";

import { ArrowLeft, ArrowRight, Compass, Crosshair, X } from "lucide-react";
import { motion, useReducedMotion } from "motion/react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { canOpen } from "@/features/auth/session-provider";
import { enterTransition } from "@/lib/motion/presets";
import type { OperixUser } from "@/services/browser-session";
import { guideSteps, type GuideKind, type GuideStep } from "./guide-steps";

type Position = { top: number; left: number; width: number; height: number };
const GUIDE_VERSION = 1;
const withoutTarget: { position: Position | null; atTop: boolean } = {
  position: null,
  atTop: false,
};

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
    if (!open) return;
    const frame = requestAnimationFrame(() =>
      title.current?.focus({ preventScroll: true }),
    );
    return () => cancelAnimationFrame(frame);
  }, [open, step]);

  useEffect(() => {
    if (!open || !step || !onRoute) return;
    let frame = 0;
    let previous: HTMLElement | null = null;
    let didReveal = false;
    const resize = new ResizeObserver(schedule);
    if (panel.current) resize.observe(panel.current);
    function measure() {
      const viewportWidth = document.documentElement.clientWidth;
      const viewportHeight = window.innerHeight;
      const active =
        step &&
        [...document.querySelectorAll<HTMLElement>(step.target)].find(
          (element) => element.getClientRects().length > 0,
        );
      if (active !== previous) {
        if (previous) resize.unobserve(previous);
        previous = active ?? null;
        if (active) resize.observe(active);
      }
      target.current = active ?? null;
      if (!active) {
        setView((value) => (value.position ? withoutTarget : value));
        return;
      }
      let rect = active.getBoundingClientRect();
      const panelHeight = panel.current?.offsetHeight ?? 230;
      if (!didReveal) {
        didReveal = true;
        if (rect.top < 80 || rect.bottom > viewportHeight - panelHeight - 82) {
          window.scrollBy({
            top: rect.top - Math.min(170, viewportHeight * 0.23),
            behavior: "instant",
          });
          rect = active.getBoundingClientRect();
        }
      }
      const left = Math.max(0, rect.left - 5);
      const top = Math.max(0, rect.top - 5);
      const width = Math.min(viewportWidth, rect.right + 5) - left;
      const height = Math.min(viewportHeight, rect.bottom + 5) - top;
      const position =
        width > 0 && height > 0 ? { top, left, width, height } : null;
      const atTop =
        rect.bottom > viewportHeight - panelHeight - 82 &&
        rect.top >= panelHeight + 90;
      setView((value) => {
        const old = value.position;
        if (
          value.atTop === atTop &&
          ((!old && !position) ||
            (old &&
              position &&
              Object.keys(position).every(
                (k) =>
                  Math.abs(
                    old[k as keyof Position] - position[k as keyof Position],
                  ) < 0.5,
              )))
        )
          return value;
        return { position, atTop };
      });
    }
    function schedule() {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(measure);
    }
    const mutations = new MutationObserver(schedule);
    const main = document.querySelector("main");
    if (main)
      mutations.observe(main, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ["open", "hidden", "aria-expanded"],
      });
    window.addEventListener("scroll", schedule, {
      passive: true,
      capture: true,
    });
    window.addEventListener("resize", schedule);
    schedule();
    const timeout = window.setTimeout(() => setWaiting(false), 1300);
    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(timeout);
      mutations.disconnect();
      resize.disconnect();
      window.removeEventListener("scroll", schedule, true);
      window.removeEventListener("resize", schedule);
      target.current = null;
    };
  }, [open, onRoute, step]);

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
      <aside
        className="experience-invite experience-glass"
        aria-label="Introducción de Operix"
      >
        <Compass size={21} aria-hidden="true" />
        <div>
          <strong>Descubre cómo funciona Operix</strong>
          <div className="experience-invite-actions">
            <button type="button" onClick={() => onOpenChange(true)}>
              Comenzar tutorial
            </button>
            <button type="button" onClick={remember}>
              Omitir
            </button>
          </div>
        </div>
      </aside>
    ) : null;
  }

  const spotlight = onRoute && view.position;

  return createPortal(
    <div
      className="experience-guide-layer"
      onKeyDown={(event) => {
        if (event.key === "Escape") {
          event.preventDefault();
          close();
        }
      }}
    >
      {spotlight && (
        <div
          className="experience-focus"
          style={{
            top: spotlight.top,
            left: spotlight.left,
            width: spotlight.width,
            height: spotlight.height,
          }}
          aria-hidden="true"
        />
      )}
      <motion.aside
        ref={panel}
        className="experience-guide experience-glass"
        data-position={onRoute && view.atTop ? "top" : "bottom"}
        aria-labelledby="experience-guide-title"
        initial={reduced ? false : { opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={enterTransition}
      >
        <div className="experience-guide-meta">
          <span>
            {kind === "analysis" ? "Primer análisis" : "Guía de Operix"}
            {step && ` · ${index + 1} de ${steps.length}`}
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
          <progress
            value={index + 1}
            max={steps.length}
            aria-label="Progreso de la guía"
          />
        )}
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
                  ? "Buscando el control…"
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
                    : [...active.querySelectorAll<HTMLElement>(focusable)].find(
                        (item) => item.getClientRects().length > 0,
                      );
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
                Ver historia animada <ArrowRight size={16} aria-hidden="true" />
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
      </motion.aside>
    </div>,
    document.body,
  );
}
