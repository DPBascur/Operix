"use client";

import { useEffect, useRef } from "react";
import { animate, useReducedMotion } from "motion/react";
import { countTransition } from "@/lib/motion/presets";

const format = new Intl.NumberFormat("es-CL");

export function EventCount({
  value,
  from = 0,
}: {
  value: number;
  from?: number;
}) {
  const visible = useRef<HTMLSpanElement>(null);
  const displayed = useRef(from);
  const reducedMotion = useReducedMotion();
  const formatted = format.format(value);

  useEffect(() => {
    const target = visible.current;
    if (!target) return;
    if (reducedMotion !== false || value === 0 || displayed.current === value) {
      target.textContent = formatted;
      displayed.current = value;
      return;
    }
    const animation = animate(displayed.current, value, {
      ...countTransition,
      onUpdate(current) {
        displayed.current = Math.round(current);
        target.textContent = format.format(displayed.current);
      },
    });
    return () => animation.stop();
  }, [value, formatted, reducedMotion]);

  return (
    <>
      <span className="sr-only">{formatted}</span>
      <span ref={visible} aria-hidden="true">
        {formatted}
      </span>
    </>
  );
}
