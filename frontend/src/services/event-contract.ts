export type OperationalEventType = "zone_dwell" | "person_forklift_proximity";

type Subject = { class_name: string; track_id: number };
export type OperationalEvent = {
  id: string;
  occurred_at: string;
  event_type: OperationalEventType;
  rule_id: string;
  rule_version: number;
  zone_id: string;
  track_id: number | null;
  class_name: string;
  interaction?: { person: Subject; forklift: Subject };
  source?: Record<string, unknown>;
  evidence_url?: string | null;
  [key: string]: unknown;
};

function subject(value: unknown): value is Subject {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  return (
    typeof item.class_name === "string" &&
    item.class_name.length > 0 &&
    Number.isSafeInteger(item.track_id) &&
    (item.track_id as number) >= 0
  );
}

export function isOperationalEvent(value: unknown): value is OperationalEvent {
  if (!value || typeof value !== "object") return false;
  const item = value as Record<string, unknown>;
  if (
    !["id", "occurred_at", "rule_id", "zone_id", "class_name"].every(
      (key) => typeof item[key] === "string",
    ) ||
    !Number.isFinite(Date.parse(item.occurred_at as string)) ||
    !Number.isSafeInteger(item.rule_version) ||
    (item.rule_version as number) < 1 ||
    !(
      item.evidence_url === undefined ||
      item.evidence_url === null ||
      typeof item.evidence_url === "string"
    )
  )
    return false;
  if (item.event_type === "zone_dwell") return subject(item);
  if (
    item.event_type !== "person_forklift_proximity" ||
    !item.interaction ||
    typeof item.interaction !== "object"
  )
    return false;
  const roles = item.interaction as Record<string, unknown>;
  return (
    item.track_id === null &&
    subject(roles.person) &&
    subject(roles.forklift) &&
    roles.person.class_name !== roles.forklift.class_name
  );
}

export const eventTypeName = (kind: string) =>
  kind === "zone_dwell"
    ? "Permanencia en zona"
    : kind === "person_forklift_proximity"
      ? "Proximidad persona–montacargas"
      : kind;

export function eventSubjects(event: OperationalEvent): string {
  const label = (item: Subject) => `${item.class_name} · ID ${item.track_id}`;
  return event.event_type === "person_forklift_proximity" && event.interaction
    ? `${label(event.interaction.person)} ↔ ${label(event.interaction.forklift)}`
    : label(event as Subject);
}
