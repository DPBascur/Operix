"use client";
import { Moon, Sun } from "lucide-react";
import { useSyncExternalStore } from "react";
const subscribeHydration = () => () => {};
const key = "operix-theme";
function subscribe(callback: () => void) {
  const media = matchMedia("(prefers-color-scheme: dark)");
  window.addEventListener("operix-theme", callback);
  window.addEventListener("storage", callback);
  media.addEventListener("change", callback);
  return () => {
    window.removeEventListener("operix-theme", callback);
    window.removeEventListener("storage", callback);
    media.removeEventListener("change", callback);
  };
}
function snapshot() {
  return document.documentElement.dataset.theme ?? "light";
}
export function ThemeSelector() {
  const hydrated = useSyncExternalStore(
    subscribeHydration,
    () => true,
    () => false,
  );
  const theme = useSyncExternalStore(subscribe, snapshot, () => "light");
  const isDark = theme === "dark";
  return (
    <button
      type="button"
      className="theme-switch"
      role="switch"
      aria-label="Modo oscuro"
      aria-checked={isDark}
      title={isDark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      disabled={!hydrated}
      onClick={() => {
        const preference = isDark ? "light" : "dark";
        try {
          localStorage.setItem(key, preference);
        } catch {}
        document.documentElement.dataset.preference = preference;
        document.documentElement.dataset.theme = preference;
        window.dispatchEvent(new Event("operix-theme"));
      }}
    >
      <span className="theme-switch-thumb" aria-hidden="true" />
      <Sun className="theme-switch-icon" aria-hidden="true" size={17} />
      <Moon className="theme-switch-icon" aria-hidden="true" size={17} />
    </button>
  );
}
