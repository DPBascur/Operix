"use client";

import type { ComponentPropsWithoutRef } from "react";
import styles from "./effects.module.css";

export function SpotlightCard({
  children,
  className,
  onPointerMove,
  ...props
}: ComponentPropsWithoutRef<"div">) {
  return (
    <div
      {...props}
      className={[styles.spotlight, className].filter(Boolean).join(" ")}
      onPointerMove={(event) => {
        onPointerMove?.(event);
        if (event.defaultPrevented || event.pointerType === "touch") return;
        const card = event.currentTarget;
        const bounds = card.getBoundingClientRect();
        card.style.setProperty(
          "--spotlight-x",
          `${event.clientX - bounds.left - card.clientLeft}px`,
        );
        card.style.setProperty(
          "--spotlight-y",
          `${event.clientY - bounds.top - card.clientTop}px`,
        );
      }}
    >
      {children}
    </div>
  );
}
