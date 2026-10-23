import type { ComponentPropsWithRef } from "react";
export type ButtonVariant =
  "primary" | "secondary" | "ghost" | "outline" | "destructive";
export function Button({
  variant = "primary",
  loading = false,
  size = "default",
  children,
  className = "",
  disabled,
  ...props
}: ComponentPropsWithRef<"button"> & {
  variant?: ButtonVariant;
  loading?: boolean;
  size?: "default" | "icon" | "small";
}) {
  return (
    <button
      {...props}
      type={props.type ?? "button"}
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={`button button-${variant} button-size-${size} ${className}`}
    >
      {loading && <span className="spinner" aria-hidden="true" />}
      {children}
    </button>
  );
}
