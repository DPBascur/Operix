import type { AnalysisProfile, EquipmentProfile } from "@/services/analysis.service";

export const ruleTypes = {
  zone_dwell: "Permanencia en zona",
  zone_entry: "Ingreso observado",
  person_forklift_proximity: "Proximidad persona–montacargas",
  zone_coexistence: "Coexistencia en zona",
};

export type RuleType = keyof typeof ruleTypes;
export type TargetType = "profile" | "demo" | "source" | "camera";
export type PolicyKind = "template" | "set" | "assignment";
export type PolicyParameters = {
  kind: RuleType;
  zone_id: string;
  class_name?: "person" | "forklift";
  min_duration_s?: number;
  max_distance?: number;
  minimum_duration_seconds?: number;
  distance_unit?: "normalized" | "m";
  motion_condition?: "any" | "moving";
  equipment_category?: EquipmentProfile["category"];
  unknown_equipment_policy?: "include" | "exclude";
};
export type RuleOverride = {
  enabled?: boolean;
  parameters?: Partial<PolicyParameters>;
};
export type PolicyDocument = {
  name: string;
  enabled: boolean;
  parameters?: PolicyParameters;
  rules?: { template_id: string; overrides?: RuleOverride }[];
  rule_set_id?: string;
  target_type?: TargetType;
  target_id?: string;
  overrides?: Record<string, RuleOverride>;
};
export type PolicyEntry = {
  id: string;
  kind: PolicyKind;
  version: number;
  updatedAt: string;
  document: PolicyDocument;
};
export type RegisteredSource = {
  source_sha256: string;
  filename: string | null;
  profile: AnalysisProfile | null;
  source_kind: "demo" | "manual" | null;
  demo_source_id: string | null;
  revision: number;
  session_id: string | null;
  can_edit: boolean;
  updated_at: string | null;
  zones: {
    zone_id: string;
    name: string;
    polygon: [number, number][];
    geometry_type: string;
    enabled: boolean;
    rules?: { rule_id: string; kind?: RuleType; enabled: boolean }[];
  }[];
};

export function newParameters(kind: RuleType, zoneId = ""): PolicyParameters {
  if (kind === "zone_entry" || kind === "zone_dwell")
    return {
      kind,
      zone_id: zoneId,
      class_name: "person",
      min_duration_s: kind === "zone_entry" ? 0 : 2,
    };
  return {
    kind,
    zone_id: zoneId,
    max_distance: kind === "zone_coexistence" ? Math.SQRT2 : 0.15,
    minimum_duration_seconds: 1,
    distance_unit: "normalized",
    motion_condition: "any",
  };
}
