"use client";
import { Menu, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import { Button } from "@/components/ui/button";
import {
  enterTransition,
  exitTransition,
  popoverVariants,
} from "@/lib/motion/presets";

export function MobileNavigation({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const reduceMotion = useReducedMotion();
  useEffect(() => {
    if (!open) return;
    function dismiss(event: PointerEvent) {
      if (event.target instanceof Node && !root.current?.contains(event.target))
        setOpen(false);
    }
    function escape(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setOpen(false);
        trigger.current?.focus();
      }
    }
    document.addEventListener("pointerdown", dismiss);
    document.addEventListener("keydown", escape);
    return () => {
      document.removeEventListener("pointerdown", dismiss);
      document.removeEventListener("keydown", escape);
    };
  }, [open]);
  return (
    <div
      ref={root}
      className="mobile-navigation-root relative"
      onBlur={(event) => {
        if (!event.currentTarget.contains(event.relatedTarget)) setOpen(false);
      }}
    >
      <Button
        ref={trigger}
        variant="ghost"
        className="!px-3"
        aria-label={open ? "Cerrar navegación" : "Abrir navegación"}
        aria-expanded={open}
        aria-controls={id}
        onClick={() => setOpen(!open)}
      >
        {open ? (
          <X aria-hidden="true" size={21} />
        ) : (
          <Menu aria-hidden="true" size={21} />
        )}
      </Button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.div
            key="mobile-navigation"
            id={id}
            inert={!open}
            className="mobile-navigation-panel absolute right-0 top-13 w-64 max-w-[calc(100vw-2rem)] rounded-card border border-border bg-surface p-2 shadow-lg"
            variants={popoverVariants}
            initial={reduceMotion ? false : "hidden"}
            animate="visible"
            exit={{ ...popoverVariants.exit, transition: exitTransition }}
            transition={reduceMotion ? { duration: 0 } : enterTransition}
            onClick={(event) => {
              if (event.target instanceof Element && event.target.closest("a"))
                setOpen(false);
            }}
          >
            {children}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
