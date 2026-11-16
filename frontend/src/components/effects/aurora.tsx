import styles from "./effects.module.css";

type AuroraProps = {
  className?: string;
  animate?: boolean;
};

/** Decorative background. The parent defines its size and positions foreground content. */
export function Aurora({ className, animate = true }: AuroraProps) {
  return (
    <div
      aria-hidden="true"
      className={[styles.aurora, className].filter(Boolean).join(" ")}
      data-animated={animate}
    />
  );
}
