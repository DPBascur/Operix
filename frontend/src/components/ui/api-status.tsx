"use client";
import { useEffect, useState } from "react";
import { Activity, WifiOff } from "lucide-react";
import { environment } from "@/config/environment";

type State = "checking" | "connected" | "problem" | "offline" | "unconfigured";
const names: Record<State, string> = {
  checking: "Reconectando",
  connected: "API conectada",
  problem: "API con problemas",
  offline: "Sin conexión",
  unconfigured: "API sin configurar",
};
export function ApiStatus() {
  const [state, setState] = useState<State>("checking");
  useEffect(() => {
    let active = true;
    let timer: ReturnType<typeof setTimeout>;
    let controller: AbortController;
    const base = environment.apiBaseUrl;
    async function check() {
      if (!active) return;
      if (!base) {
        setState("unconfigured");
        return;
      }
      if (document.hidden) {
        timer = setTimeout(check, 30000);
        return;
      }
      controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), 5000);
      try {
        const response = await fetch(`${base.replace(/\/$/, "")}/health/`, {
          cache: "no-store",
          signal: controller.signal,
        });
        const data = await response.json();
        if (active)
          setState(
            response.ok && data.status === "ok" ? "connected" : "problem",
          );
      } catch {
        if (active) setState("offline");
      } finally {
        clearTimeout(timeout);
        if (active) timer = setTimeout(check, 30000);
      }
    }
    const online = () => {
      clearTimeout(timer);
      controller?.abort();
      setState("checking");
      void check();
    };
    void check();
    window.addEventListener("online", online);
    return () => {
      active = false;
      clearTimeout(timer);
      controller?.abort();
      window.removeEventListener("online", online);
    };
  }, []);
  return (
    <span
      className={`api-status api-${state}`}
      role="status"
      title="Comprobación real de API y base de datos cada 30 segundos. No verifica modelos ni GPU."
    >
      {state === "offline" ? (
        <WifiOff size={14} aria-hidden="true" />
      ) : (
        <Activity size={14} aria-hidden="true" />
      )}
      {names[state]}
    </span>
  );
}
