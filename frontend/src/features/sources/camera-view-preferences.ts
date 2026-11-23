"use client";

import { useCallback, useSyncExternalStore } from "react";

const defaults = {
  detections: true, distances: true, zones: true, identifiers: false,
  diagnostics: false, unit: "m" as "m" | "cm",
};
export type ViewPreferences = typeof defaults;
const values = new Map<string, ViewPreferences>();
const changed = "operix:camera-view-preferences";

function snapshot(id: string) {
  if (values.has(id)) return values.get(id)!;
  try {
    const saved = JSON.parse(localStorage.getItem(`operix:view:${id}`) ?? "null");
    if (saved && typeof saved === "object") {
      const result: ViewPreferences = {
        detections: typeof saved.detections === "boolean" ? saved.detections : defaults.detections,
        distances: typeof saved.distances === "boolean" ? saved.distances : defaults.distances,
        zones: typeof saved.zones === "boolean" ? saved.zones : defaults.zones,
        identifiers: saved.identifiers === true,
        diagnostics: saved.diagnostics === true,
        unit: saved.unit === "cm" ? "cm" : "m",
      };
      values.set(id, result);
      return result;
    }
  } catch {
    // The current tab still has a working preference when storage is unavailable.
  }
  return defaults;
}

export function useCameraViewPreferences(id: string) {
  const subscribe = useCallback((notify: () => void) => {
    function onStorage(event: StorageEvent) {
      if (event.key === null || event.key === `operix:view:${id}`) {
        values.delete(id);
        notify();
      }
    }
    window.addEventListener(changed, notify);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(changed, notify);
      window.removeEventListener("storage", onStorage);
    };
  }, [id]);
  const value = useSyncExternalStore(subscribe, () => snapshot(id), () => defaults);

  function set<K extends keyof ViewPreferences>(name: K, value: ViewPreferences[K]) {
    const next = { ...snapshot(id), [name]: value };
    values.set(id, next);
    try {
      localStorage.setItem(`operix:view:${id}`, JSON.stringify(next));
    } catch {
      // Restrict this preference to the current tab when persistence is unavailable.
    }
    window.dispatchEvent(new Event(changed));
  }
  return [value, set] as const;
}
