"use client";

import { useSyncExternalStore } from "react";

function subscribeToVisibility(listener: () => void) {
  document.addEventListener("visibilitychange", listener);
  return () => document.removeEventListener("visibilitychange", listener);
}

export function usePageVisible() {
  return useSyncExternalStore(
    subscribeToVisibility,
    () => document.visibilityState === "visible",
    () => false,
  );
}
