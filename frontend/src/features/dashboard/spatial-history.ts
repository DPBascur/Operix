import type { HistoryEvent } from "./history-model.ts";

export const spatialColumns = 12;
export const spatialRows = 8;

type SpatialGroup = {
  name: string;
  run: string;
  epoch: number | null;
  cells: string[][];
  total: number;
};

function record(value: unknown): Record<string, unknown> {
  return value !== null && typeof value === "object"
    ? (value as Record<string, unknown>)
    : {};
}

export function spatialHistory(events: HistoryEvent[]) {
  const groups = new Map<string, SpatialGroup>();
  const hasHash = (value: unknown) =>
    typeof value === "string" && /^[0-9a-f]{64}$/i.test(value);
  for (const event of events) {
    const source = record(event.source);
    const { analysis_run_id: run, view_id: view } = event;
    const observations = record(event.observations);
    const ground = record(observations.ground);
    const calibration = record(ground.calibration);
    const metric = ground.method === "ground_plane_contact_edges_v1";
    const geometry = metric ? ground : record(observations.proximity_geometry);
    const method = metric ? ground.method : geometry.version;
    const point = geometry.person_anchor;
    const epoch = source.epoch;
    if (
      event.event_type !== "person_forklift_proximity" ||
      !run ||
      typeof view !== "string" ||
      !view ||
      !hasHash(source.video_sha256) ||
      !hasHash(source.config_sha256) ||
      (epoch == null && source.kind !== "demo" && source.kind !== "manual") ||
      (epoch != null &&
        (typeof epoch !== "number" ||
          !Number.isSafeInteger(epoch) ||
          epoch < 0)) ||
      (!metric &&
        method !== "person_equipment_nearest_ground_edges_v1" &&
        method !== "person_bottom_center_to_equipment_ground_edge_v1") ||
      (metric &&
        (calibration.status !== "valid" ||
          calibration.source_sha256 !== source.video_sha256 ||
          !hasHash(calibration.sha256))) ||
      !Array.isArray(point) ||
      point.length !== 2 ||
      !point.every(
        (axis) =>
          typeof axis === "number" &&
          Number.isFinite(axis) &&
          axis >= 0 &&
          axis <= 1,
      )
    )
      continue;
    const key = JSON.stringify([
      source.video_sha256,
      view,
      run,
      source.config_sha256,
      epoch ?? null,
      method,
      metric ? calibration.sha256 : null,
    ]);
    let group = groups.get(key);
    if (!group) {
      group = {
        name:
          typeof source.filename === "string"
            ? source.filename
            : "Video identificado",
        run,
        epoch: typeof epoch === "number" ? epoch : null,
        cells: Array.from({ length: spatialColumns * spatialRows }, () => []),
        total: 0,
      };
      groups.set(key, group);
    }
    const x = Math.min(
      spatialColumns - 1,
      Math.floor(point[0] * spatialColumns),
    );
    const y = Math.min(spatialRows - 1, Math.floor(point[1] * spatialRows));
    group.cells[y * spatialColumns + x].push(event.id);
    group.total++;
  }
  return [...groups].map(([key, group]) => ({ key, ...group }));
}
