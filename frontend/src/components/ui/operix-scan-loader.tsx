import styles from "./operix-scan-loader.module.css";

export function OperixScanLoader({
  message,
  size = "medium",
  variant = "inline",
  className = "",
  announce = true,
}: {
  message?: string;
  size?: "small" | "medium" | "large";
  variant?: "inline" | "panel" | "process";
  className?: string;
  announce?: boolean;
}) {
  return (
    <span
      className={`${styles.root} ${styles[size]} ${styles[variant]} ${className}`}
      data-operix-loading={variant}
      role={message && announce ? "status" : undefined}
    >
      <svg viewBox="0 0 64 64" fill="none" aria-hidden="true" focusable="false">
        <circle cx="32" cy="32" r="26" className={styles.track} />
        <path
          d="M32 6a26 26 0 0 1 24 16M32 58A26 26 0 0 1 8 42"
          className={styles.arc}
        />
        <path
          d="M16 32c5-6 11-10 16-10s11 4 16 10c-5 6-11 10-16 10s-11-4-16-10Z"
          className={styles.eye}
        />
        <circle cx="32" cy="32" r="4" fill="currentColor" />
        <circle cx="46" cy="19" r="2" className={styles.detection} />
      </svg>
      {message && <span>{message}</span>}
    </span>
  );
}
