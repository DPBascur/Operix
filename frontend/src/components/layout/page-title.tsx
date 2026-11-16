import type { ComponentPropsWithoutRef } from "react";
import { SplitText } from "@/components/effects/split-text";

export function PageTitle({
  children,
  animate = false,
  ...props
}: Omit<ComponentPropsWithoutRef<"h1">, "children" | "className"> & {
  children: string;
  animate?: boolean;
}) {
  return (
    <h1 className="app-page-title" {...props}>
      {animate ? (
        <SplitText key={children} text={children} staggerMs={15} />
      ) : (
        children
      )}
    </h1>
  );
}
