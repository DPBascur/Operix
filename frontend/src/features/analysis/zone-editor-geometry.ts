import type { NormalizedVertex } from "@/services/analysis.service";

interface PointerSample {
  clientX: number;
  clientY: number;
  currentTarget: {
    getBoundingClientRect(): {
      left: number;
      top: number;
      width: number;
      height: number;
    };
  };
}

/** Capturar dentro del handler: React no conserva currentTarget para el updater. */
export function pointInFrame(event: PointerSample): NormalizedVertex | null {
  const bounds = event.currentTarget.getBoundingClientRect();
  if (!(bounds.width > 0 && bounds.height > 0)) return null;
  return [
    Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
    Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
  ];
}
