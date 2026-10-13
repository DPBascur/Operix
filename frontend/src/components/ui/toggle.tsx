import type { InputHTMLAttributes } from "react";

export function Toggle({
  className = "",
  ...props
}: Omit<InputHTMLAttributes<HTMLInputElement>, "type" | "role">) {
  return (
    <input
      {...props}
      type="checkbox"
      role="switch"
      className={`toggle ${className}`}
    />
  );
}
