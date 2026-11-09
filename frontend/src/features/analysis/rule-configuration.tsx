import type { AnalysisRuleSnapshot } from "@/services/analysis.service";

const labels: Record<string, string> = {
  kind: "Tipo",
  zone_id: "ID de zona",
  class_name: "Clase",
  person_class: "Clase de persona",
  forklift_class: "Clase de montacargas",
  min_duration_s: "Duración mínima (s)",
  minimum_duration_seconds: "Duración mínima (s)",
  max_distance: "Distancia máxima configurada",
  motion_condition: "Condición de movimiento",
  distance_unit: "Unidad de distancia",
};

const kinds: Record<string, string> = {
  zone_dwell: "Permanencia",
  zone_entry: "Ingreso observado",
  zone_coexistence: "Presencia simultánea",
  person_forklift_proximity: "Proximidad persona ↔ montacargas",
};

export function RuleConfiguration({
  snapshot,
}: {
  snapshot?: Partial<AnalysisRuleSnapshot> | null;
}) {
  if (!snapshot?.rules) {
    return (
      <p className="text-sm text-text-secondary">
        Configuración no disponible.
      </p>
    );
  }
  if (!snapshot.rules.length) {
    return (
      <p className="text-sm text-text-secondary">
        El perfil no declara reglas.
      </p>
    );
  }

  return (
    <div className="grid gap-2">
      {snapshot.calibration && (
        <p className="text-sm">
          Plano del suelo:{" "}
          {snapshot.calibration.status === "valid"
            ? "calibración declarada válida"
            : "calibración inválida"}{" "}
          · v{snapshot.calibration.version}. Metros aproximados solo dentro del
          área referenciada.
        </p>
      )}
      {snapshot.motion && (
        <p className="text-sm">
          Movimiento configurado en{" "}
          {snapshot.motion.unit === "m"
            ? "m/s aproximados"
            : "unidades de imagen/s"}{" "}
          · ventana {snapshot.motion.window_seconds} s · cámara{" "}
          {snapshot.motion.camera_fixed_confirmed
            ? "declarada fija"
            : "sin confirmar"}
          .
        </p>
      )}
      {snapshot.rules.map((rule) => {
        const kind = String(rule.parameters.kind ?? "");
        return (
          <details
            key={rule.rule_id}
            className="rounded-md border border-border p-2"
          >
            <summary className="cursor-pointer break-words text-sm font-medium">
              {kinds[kind] ?? rule.rule_id} · v{rule.version} ·{" "}
              {rule.enabled ? "Habilitada" : "Deshabilitada"}
            </summary>
            <p className="my-2 break-words text-xs text-text-secondary">
              {rule.rule_id} · Parámetros del snapshot
            </p>
            <dl className="grid gap-1 text-sm">
              {Object.entries(rule.parameters).map(([key, value]) => (
                <div
                  key={key}
                  className="flex flex-wrap justify-between gap-x-3 break-all"
                >
                  <dt className="text-text-secondary">
                    {key === "max_distance" &&
                    rule.parameters.distance_unit === "m"
                      ? "Distancia máxima aproximada (m)"
                      : (labels[key] ?? key)}
                  </dt>
                  <dd>
                    {key === "motion_condition"
                      ? value === "moving"
                        ? "Solo con movimiento confirmado"
                        : "Independiente del movimiento"
                      : typeof value === "string"
                        ? value
                        : JSON.stringify(value)}
                  </dd>
                </div>
              ))}
            </dl>
          </details>
        );
      })}
      {snapshot.config_sha256 && (
        <details className="text-xs text-text-secondary">
          <summary className="cursor-pointer">
            Huella de configuración (SHA-256)
          </summary>
          <p className="mt-1 break-all font-mono">{snapshot.config_sha256}</p>
        </details>
      )}
    </div>
  );
}
