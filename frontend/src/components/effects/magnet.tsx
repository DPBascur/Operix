"use client";

import { motion, useReducedMotion, useSpring } from "motion/react";
import type { ReactNode } from "react";
import styles from "./effects.module.css";

type MagnetProps = {
  children: ReactNode;
  className?: string;
  maxOffset?: number;
};

export function Magnet({ children, className, maxOffset = 12 }: MagnetProps) {
  const reducedMotion = useReducedMotion();
  const x = useSpring(0, { stiffness: 250, damping: 24 });
  const y = useSpring(0, { stiffness: 250, damping: 24 });
  const limit = Number.isFinite(maxOffset) ? Math.max(0, maxOffset) : 0;
  function center() {
    x.set(0);
    y.set(0);
  }

  return (
    <div
      className={[styles.magnet, className].filter(Boolean).join(" ")}
      onPointerMove={(event) => {
        if (reducedMotion || event.pointerType === "touch") return;
        const bounds = event.currentTarget.getBoundingClientRect();
        if (!bounds.width || !bounds.height) return;
        const horizontal = (event.clientX - bounds.left) / bounds.width - 0.5;
        const vertical = (event.clientY - bounds.top) / bounds.height - 0.5;
        x.set(limit * Math.max(-1, Math.min(1, horizontal * 2)));
        y.set(limit * Math.max(-1, Math.min(1, vertical * 2)));
      }}
      onPointerLeave={center}
      onPointerCancel={center}
      onFocus={center}
    >
      <motion.div className={styles.magnetContent} style={{ x, y }}>
        {children}
      </motion.div>
    </div>
  );
}
