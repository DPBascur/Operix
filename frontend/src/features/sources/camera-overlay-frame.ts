/** The existing frame may remain painted until the next presentation or a stall. */
export function estimatedFrameHoldMs(periodMs: number, beforeMs: number, afterMs: number) {
  const period = Number.isFinite(periodMs) && periodMs > 0 ? periodMs : 55;
  // Allow one display refresh for callback scheduling. The next presented
  // frame always replaces or clears this one, regardless of this watchdog.
  return Math.max(0, Math.min(period + 17, 200, beforeMs, afterMs));
}
