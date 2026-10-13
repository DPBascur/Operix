"use client";
import {
  Expand,
  Play,
  Settings2,
  SlidersHorizontal,
  Square,
  Volume2,
} from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/ui/section-card";
import { Toggle } from "@/components/ui/toggle";

const initialLayers = [
  { id: "detections", label: "Detecciones", enabled: true },
  { id: "tracks", label: "Seguimientos (ID)", enabled: true },
  { id: "zones", label: "Zonas", enabled: true },
  { id: "rules", label: "Reglas activas", enabled: true },
  { id: "trajectories", label: "Trayectorias", enabled: false },
] as const;
const mockSystemStatus = [
  ["Detector", "YOLO11"],
  ["Tracker", "ByteTrack"],
  ["Reglas", "Mock"],
  ["Zonas", "Mock"],
  ["FPS simulados", "24,8"],
] as const;
const playerActions = [
  { icon: Volume2, label: "Volumen" },
  { icon: SlidersHorizontal, label: "Ajustes" },
  { icon: Expand, label: "Pantalla completa" },
];

export function AnalysisWorkspace() {
  const [layers, setLayers] = useState<
    ReadonlyArray<{
      id: (typeof initialLayers)[number]["id"];
      label: string;
      enabled: boolean;
    }>
  >(initialLayers);
  const visible = (id: (typeof initialLayers)[number]["id"]) =>
    layers.some((layer) => layer.id === id && layer.enabled);
  return (
    <div className="grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_18rem]">
      <section
        aria-label="Previsualización de análisis simulada"
        className="min-w-0"
      >
        <div
          className="relative aspect-video w-full min-h-64 overflow-hidden rounded-t-panel border border-analysis-border bg-analysis-surface"
          role="img"
          aria-label={`CAM-01. Previsualización mock sin video conectado. Capas visibles: ${
            layers
              .filter((layer) => layer.enabled)
              .map((layer) => layer.label)
              .join(", ") || "ninguna"
          }.`}
        >
          <div className="absolute inset-5 rounded-card border border-brand-neutral/10 bg-brand-primary/45" />
          {visible("detections") && (
            <>
              <div className="absolute left-[18%] top-[22%] h-[34%] w-[12%] rounded-control border-2 border-brand-cyan" />
              <div className="absolute left-[55%] top-[38%] h-[35%] w-[14%] rounded-control border-2 border-brand-accent" />
            </>
          )}
          {visible("tracks") && (
            <>
              <span className="absolute left-[18%] top-[16%] text-xs font-semibold text-brand-cyan">
                ID 01
              </span>
              <span className="absolute left-[55%] top-[74%] text-xs font-semibold text-white">
                ID 02
              </span>
            </>
          )}
          {visible("zones") && (
            <div className="absolute bottom-[10%] left-[22%] h-[30%] w-[58%] border-2 border-brand-cyan bg-brand-cyan/15 [clip-path:polygon(8%_0,100%_22%,76%_100%,25%_100%)]" />
          )}
          {visible("trajectories") && (
            <svg
              viewBox="0 0 100 100"
              preserveAspectRatio="none"
              className="absolute inset-0 h-full w-full text-brand-cyan"
              aria-hidden="true"
            >
              <path
                d="M12 70L24 56L24 40 M80 85L70 70L62 65"
                stroke="currentColor"
                strokeWidth=".5"
                strokeDasharray="2 2"
                fill="none"
              />
            </svg>
          )}
          {visible("rules") && (
            <div className="absolute left-[45%] top-[28%] max-w-[52%] rounded-control bg-brand-primary px-3 py-2 text-xs font-semibold text-white">
              Candidato de evento · Mock
            </div>
          )}
          <div className="absolute bottom-4 left-4 rounded-control bg-brand-dark/80 px-3 py-2 text-xs text-brand-neutral">
            CAM-01 · Escenario de prueba
          </div>
          <div className="absolute right-4 top-4 rounded-full bg-brand-dark/80 px-2.5 py-1 text-xs font-semibold text-brand-cyan">
            Simulación
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3 rounded-b-panel border-x border-b border-border bg-surface px-4 py-3">
          <button
            aria-label="Reproducción no disponible: sin video conectado"
            className="flex size-11 cursor-not-allowed items-center justify-center rounded-full bg-primary text-primary-foreground opacity-60"
            disabled
            type="button"
          >
            <Play aria-hidden="true" fill="currentColor" size={17} />
          </button>
          <span className="text-sm font-medium tabular-nums text-text-secondary">
            00:04 / 01:23 <span className="text-xs">· Mock</span>
          </span>
          <div className="ml-auto flex items-center gap-1">
            {playerActions.map(({ icon: Icon, label }) => (
              <button
                key={label}
                aria-label={`${label} no disponible`}
                className="flex size-11 cursor-not-allowed items-center justify-center rounded-control text-text-secondary opacity-60"
                disabled
                type="button"
              >
                <Icon aria-hidden="true" size={18} />
              </button>
            ))}
          </div>
        </div>
        <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
          <p
            role="status"
            className="flex items-center gap-2 text-sm text-text-secondary"
          >
            <span
              aria-hidden="true"
              className="size-2 rounded-full bg-text-secondary"
            />
            Sin análisis activo · sin video conectado
          </p>
          <div className="flex flex-wrap gap-2">
            <Button
              disabled
              title="Requiere la futura integración con la API"
              variant="primary"
            >
              <Play aria-hidden="true" size={16} />
              Iniciar análisis
            </Button>
            <Button
              disabled
              title="Sin análisis activo; requiere integración con la API"
              variant="destructive"
            >
              <Square aria-hidden="true" size={16} />
              Detener análisis
            </Button>
          </div>
        </div>
        <p className="mt-3 text-xs leading-5 text-text-secondary">
          Las capas modifican únicamente esta previsualización mock.
        </p>
      </section>
      <aside
        aria-label="Configuración del análisis"
        className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-1"
      >
        <SectionCard>
          <div className="mb-4 flex items-center gap-2">
            <Settings2 aria-hidden="true" className="text-active" size={18} />
            <h2 className="font-semibold">Capas visibles</h2>
          </div>
          <ul className="space-y-2">
            {layers.map((layer) => (
              <li key={layer.id}>
                <label className="flex min-h-9 cursor-pointer items-center justify-between gap-4 text-sm text-text-secondary">
                  <span>{layer.label}</span>
                  <Toggle
                    checked={layer.enabled}
                    onChange={(event) =>
                      setLayers((current) =>
                        current.map((item) =>
                          item.id === layer.id
                            ? { ...item, enabled: event.target.checked }
                            : item,
                        ),
                      )
                    }
                  />
                </label>
              </li>
            ))}
          </ul>
        </SectionCard>
        <SectionCard>
          <h2 className="mb-4 font-semibold">Estado simulado</h2>
          <dl className="space-y-4">
            {mockSystemStatus.map(([label, value]) => (
              <div className="flex items-center gap-3 text-sm" key={label}>
                <dt className="flex-1 text-text-secondary">{label}</dt>
                <dd className="font-semibold tabular-nums text-foreground">
                  {value}
                </dd>
              </div>
            ))}
          </dl>
        </SectionCard>
      </aside>
    </div>
  );
}
