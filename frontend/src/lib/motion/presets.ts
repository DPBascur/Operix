import type { Transition, Variants } from "motion/react";

export const motionTiming = {
  fast: 0.18,
  normal: 0.28,
  slow: 0.36,
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

export const pageTransition = {
  duration: motionTiming.slow,
  ease: motionEase.enter,
} as const satisfies Transition;

export const exitTransition = {
  duration: motionTiming.fast,
  ease: motionEase.exit,
} as const satisfies Transition;

export const controlTransition = {
  duration: 0.24,
  ease: motionEase.enter,
} as const satisfies Transition;

export const sectionEntrance = {
  hidden: { opacity: 0.72, y: 5 },
  visible: { opacity: 1, y: 0 },
} satisfies Variants;

export const sectionTransition = {
  duration: 0.36,
  ease: motionEase.enter,
} as const satisfies Transition;

export const countTransition = {
  duration: 0.64,
  ease: motionEase.enter,
} as const;
