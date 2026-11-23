import {
  equipmentCategoryLabels,
  type AnalysisRuleSnapshot,
  type EquipmentContext,
} from "@/services/analysis.service";

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
  exclude_possible_occupant: "Exclusión experimental de posibles ocupantes",
  distance_unit: "Unidad de distancia",
  equipment_category: "Categoría operacional requerida",
  unknown_equipment_policy: "Política para categoría desconocida",
};

const scopeLabels: Record<string, string> = {
  equipment_category_match: "con categoría coincidente",
  equipment_category_mismatch: "excluidas por categoría distinta",
  equipment_unknown_included: "con UNKNOWN incluido",
  equipment_unknown_excluded: "con UNKNOWN excluido",
};

const kinds: Record<string, string> = {
  zone_dwell: "Permanencia",
  zone_entry: "Ingreso observado",
  zone_coexistence: "Presencia simultánea",
  person_forklift_proximity: "Proximidad persona ↔ montacargas",
};

function parameterValue(key: string, value: unknown) {
  if (key === "motion_condition") {
    return value === "moving"
      ? "Solo con movimiento confirmado"
      : "Independiente del movimiento";
  }
  if (key === "unknown_equipment_policy") {
    return value === "include"
      ? "Incluir en la evaluación"
      : "Excluir de la evaluación";
  }
  if (key === "equipment_category" && typeof value === "string") {
    return (
      equipmentCategoryLabels[value as keyof typeof equipmentCategoryLabels] ??
      value
    );
  }
  return typeof value === "string" ? value : JSON.stringify(value);
}

export function RuleConfiguration({
  snapshot,
  equipmentContext,
}: {
  snapshot?: Partial<AnalysisRuleSnapshot> | null;
  equipmentContext?: EquipmentContext;
}) {
  if (!snapshot?.rules) {
    return (
      <p className="text-sm text-text-secondary">
        Configuración no disponible.
      </p>
    );
  }
  if (!snapshot.rules.length && !snapshot.equipment_profile) {
    return (
      <p className="text-sm text-text-secondary">
        El perfil no declara reglas.
      </p>
    );
  }

  return (
    <div className="grid gap-2">
      {snapshot.equipment_profile && (
        <p className="text-sm">
          Categoría declarada{" "}
          {equipmentCategoryLabels[snapshot.equipment_profile.category]} ·
          autorización {snapshot.equipment_profile.authority_reference}. El
          perfil se aplica solo a la fuente con la huella SHA-256 declarada.
        </p>
      )}
      {equipmentContext && (
        <p className="text-sm">
          Categoría aplicada{" "}
          {equipmentCategoryLabels[equipmentContext.taxonomy.category]} ·
          subtipo del detector UNKNOWN.
        </p>
      )}
      {(snapshot.equipment_profile ||
        snapshot.rules.some(
          (rule) => "equipment_category" in rule.parameters,
        )) && (
        <p className="text-sm text-text-secondary">
          La categoría procede de una declaración autorizada para una fuente
          homogénea. En fuentes mixtas o sin una declaración aplicable, la
          categoría es UNKNOWN. El detector mantiene la clase FORKLIFT y el
          subtipo UNKNOWN. Incluir UNKNOWN permite evaluar la regla sin atribuir
          motorización.
        </p>
      )}
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
        const scope = equipmentContext?.rule_scope.find(
          (item) =>
            item.rule_id === rule.rule_id && item.rule_version === rule.version,
        );
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
                  <dd>{parameterValue(key, value)}</dd>
                </div>
              ))}
            </dl>
            {equipmentContext &&
              rule.enabled &&
              rule.parameters.equipment_category !== undefined && (
                <p className="mt-2 text-sm">
                  {scope
                    ? `Observaciones por fotograma · ${Object.entries(
                        scope.counts,
                      )
                        .map(
                          ([key, count]) =>
                            `${count} ${scopeLabels[key] ?? key}`,
                        )
                        .join(" · ")}`
                    : "Sin observaciones de alcance"}
                  {scope?.last_exclusion &&
                    ` · última exclusión en el fotograma ${scope.last_exclusion.frame_index}`}
                </p>
              )}
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
