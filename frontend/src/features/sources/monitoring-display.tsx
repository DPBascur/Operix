"use client";

import Link from "next/link";
import { Maximize, Minimize } from "lucide-react";
import { useEffect, useState } from "react";
import { CameraWorkspace } from "./camera-workspace";

export function MonitoringDisplay() {
  const [fullscreen, setFullscreen] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const sync = () => setFullscreen(Boolean(document.fullscreenElement));
    document.addEventListener("fullscreenchange", sync);
    return () => document.removeEventListener("fullscreenchange", sync);
  }, []);

  async function toggleFullscreen() {
    setError("");
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      setError("El navegador no pudo activar el modo de pantalla completa.");
    }
  }

  return (
    <div className="sources-page page-v1 mx-auto min-h-dvh p-4 sm:p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Pantalla de vigilancia</h1>
        <nav className="flex flex-wrap gap-2" aria-label="Controles de vigilancia">
          <Link href="/monitoring" className="button button-outline">Volver a Monitoreo</Link>
          <button type="button" className="button button-outline" onClick={() => void toggleFullscreen()}>
            {fullscreen ? <Minimize size={16} aria-hidden="true" /> : <Maximize size={16} aria-hidden="true" />}
            {fullscreen ? "Salir de pantalla completa" : "Pantalla completa"}
          </button>
        </nav>
      </header>
      {error && <p role="alert">{error}</p>}
      <CameraWorkspace monitor surveillance />
    </div>
  );
}
