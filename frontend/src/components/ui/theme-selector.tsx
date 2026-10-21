"use client";

import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

const key = "operix-theme";

export function ThemeSelector() {
  const [isDark, setIsDark] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setIsDark(root.dataset.theme === "dark");
    sync();
    window.addEventListener("operix-theme", sync);
    window.addEventListener("storage", sync);
    return () => {
      window.removeEventListener("operix-theme", sync);
      window.removeEventListener("storage", sync);
    };
  }, []);

  return (
    <button
      type="button"
      className="theme-switch"
      role="switch"
      aria-label="Modo oscuro"
      aria-checked={isDark}
      title={isDark ? "Cambiar a modo claro" : "Cambiar a modo oscuro"}
      onClick={() => {
        const currentIsDark = document.documentElement.dataset.theme === "dark";
        const preference = currentIsDark ? "light" : "dark";
        try {
          localStorage.setItem(key, preference);
        } catch {}
        document.documentElement.dataset.preference = preference;
        document.documentElement.dataset.theme = preference;
        setIsDark(!currentIsDark);
        window.dispatchEvent(new Event("operix-theme"));
      }}
    >
      <span className="theme-switch-thumb" aria-hidden="true" />
      <Sun className="theme-switch-icon" aria-hidden="true" size={16} />
      <Moon className="theme-switch-icon" aria-hidden="true" size={16} />
    </button>
  );
}
