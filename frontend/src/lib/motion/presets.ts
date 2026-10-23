import type { Transition, Variants } from "motion/react";

export const motionTiming = {
  fast: 0.15,
  normal: 0.22,
  slow: 0.34,
} as const;

export const motionEase = {
  enter: [0.16, 1, 0.3, 1],
  exit: [0.4, 0, 1, 1],
} as const;

export const calmSpring = {
  type: "spring",
  stiffness: 320,
  damping: 34,
  mass: 0.8,
} as const satisfies Transition;

export const revealVariants = {
  hidden: { opacity: 0, y: 8 },
  visible: { opacity: 1, y: 0 },
} satisfies Variants;

export const popoverVariants = {
  hidden: { opacity: 0, y: -6, scale: 0.98 },
  visible: { opacity: 1, y: 0, scale: 1 },
  exit: { opacity: 0, y: -4, scale: 0.98 },
} satisfies Variants;

export const enterTransition = {
  duration: motionTiming.normal,
  ease: motionEase.enter,
} as const satisfies Transition;

export const exitTransition = {
  duration: motionTiming.fast,
  ease: motionEase.exit,
} as const satisfies Transition;
