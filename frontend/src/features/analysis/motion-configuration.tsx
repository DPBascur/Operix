import { Button } from "@/components/ui/button";
import type {
  MotionSettings,
  RelationSettings,
} from "@/services/analysis.service";

const fields: [
  keyof Omit<MotionSettings, "unit" | "camera_fixed_confirmed">,
  string,
  number,
][] = [
  ["window_seconds", "Ventana de observación (s)", 0.1],
  ["min_observations", "Observaciones mínimas", 1],
  ["max_gap_seconds", "Separación máxima entre observaciones (s)", 0.01],
  ["stationary_speed", "Máximo estacionario (unidad/s)", 0.001],
  ["moving_speed", "Mínimo en movimiento (unidad/s)", 0.001],
  ["max_position_residual", "Residual máximo de posición (unidad)", 0.001],
];
export function MotionConfiguration({
  motion,
  relations,
  metricAvailable,
  onMotion,
  onRelations,
}: {
  motion?: MotionSettings;
  relations?: RelationSettings;
  metricAvailable: boolean;
  onMotion: (value?: MotionSettings) => void;
  onRelations: (value: RelationSettings) => void;
}) {
  const display = relations ?? {
    max_pairs: 4,
    policy: "active",
    near_margin: 0.2,
  };
  return (
    <details className="grid gap-3 rounded-xl border border-border p-3">
      <summary className="cursor-pointer font-semibold">
        Movimiento y relaciones visibles
      </summary>
      <div className="mt-3 grid gap-3">
        <p className="text-sm text-text-secondary">
          Estimación experimental del contacto inferior de la caja. Requiere
          cámara fija; no identifica movimiento propio de la cámara. Configure
          los parámetros para esta fuente antes de utilizarla en reglas.
        </p>
        <label>
          <input
            type="checkbox"
            checked={!!motion}
            onChange={(e) =>
              onMotion(
                e.target.checked
                  ? {
                      unit: "normalized",
                      window_seconds: 1,
                      min_observations: 3,
                      max_gap_seconds: 0.2,
                      stationary_speed: 0,
                      moving_speed: 0,
                      max_position_residual: 0,
                      camera_fixed_confirmed: false,
                    }
                  : undefined,
              )
            }
          />{" "}
          Estimar movimiento del montacargas
        </label>
        {motion && (
          <>
            <label>
              Unidad de movimiento
              <select
                className="input"
                value={motion.unit}
                onChange={(e) =>
                  onMotion({
                    ...motion,
                    unit: e.target.value as MotionSettings["unit"],
                    camera_fixed_confirmed: false,
                  })
                }
              >
                <option value="normalized">
                  Imagen normalizada · unidades de imagen/s
                </option>
                <option value="m" disabled={!metricAvailable}>
                  Plano calibrado · m/s aproximados
                </option>
              </select>
            </label>
            <div className="grid gap-3 sm:grid-cols-2">
              {fields.map(([key, label, step]) => (
                <label key={key}>
                  {label.replace(
                    "unidad",
                    motion.unit === "m" ? "m" : "imagen normalizada",
                  )}
                  <input
                    className="input"
                    type="number"
                    min="0"
                    step={step}
                    value={motion[key]}
                    onChange={(e) =>
                      onMotion({ ...motion, [key]: Number(e.target.value) })
                    }
                  />
                </label>
              ))}
            </div>
            <p className="text-sm">
              El mínimo en movimiento debe superar el máximo estacionario. Entre
              ambos, ante ruido o datos insuficientes, el estado será
              indeterminado. Estos parámetros requieren validación contextual.
            </p>
            <label>
              <input
                type="checkbox"
                checked={motion.camera_fixed_confirmed}
                onChange={(e) =>
                  onMotion({
                    ...motion,
                    camera_fixed_confirmed: e.target.checked,
                  })
                }
              />{" "}
              Confirmo encuadre fijo y parámetros de movimiento revisados para
              esta fuente
            </label>
            <Button
              variant="outline"
              onClick={() =>
                onMotion({ ...motion, camera_fixed_confirmed: false })
              }
            >
              El encuadre cambió: invalidar movimiento
            </Button>
          </>
        )}
        <h4 className="font-medium">Relaciones dibujadas</h4>
        <p className="text-sm text-text-secondary">
          Este límite solo afecta la visualización. Todas las parejas continúan
          evaluándose y generando los eventos correspondientes.
        </p>
        <label>
          Política visual
          <select
            className="input"
            value={display.policy}
            onChange={(e) =>
              onRelations({
                ...display,
                policy: e.target.value as RelationSettings["policy"],
              })
            }
          >
            <option value="active">
              Condiciones en evaluación (emisiones siempre visibles)
            </option>
            <option value="near_threshold">
              Relaciones próximas al umbral
            </option>
            <option value="all">Todas las relaciones observadas en zona</option>
          </select>
        </label>
        <label>
          Máximo de parejas visibles
          <input
            className="input"
            type="number"
            min="1"
            max="16"
            step="1"
            value={display.max_pairs}
            onChange={(e) =>
              onRelations({ ...display, max_pairs: Number(e.target.value) })
            }
          />
        </label>
        {display.policy === "near_threshold" && (
          <label>
            Margen visual respecto al umbral (fracción 0–1)
            <input
              className="input"
              type="number"
              min="0"
              max="1"
              step=".05"
              value={display.near_margin}
              onChange={(e) =>
                onRelations({ ...display, near_margin: Number(e.target.value) })
              }
            />
          </label>
        )}
      </div>
    </details>
  );
}
