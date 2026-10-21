"use client";
import { Menu, X } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";

export function MobileNavigation({ children }: { children: ReactNode }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
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
      {open && (
        <div
          id={id}
          className="mobile-navigation-panel absolute right-0 top-13 w-64 max-w-[calc(100vw-2rem)] rounded-card border border-border bg-surface p-2 shadow-lg"
          onClick={(event) => {
            if (event.target instanceof Element && event.target.closest("a"))
              setOpen(false);
          }}
        >
          {children}
        </div>
      )}
    </div>
  );
}
