import assert from "node:assert/strict";
import test from "node:test";
import {
  dayUtcBounds,
  summarizeHistory,
} from "../src/features/dashboard/history-model.ts";
import {
  spatialColumns,
  spatialHistory,
  spatialRows,
} from "../src/features/dashboard/spatial-history.ts";

const event = {
  id: "observed",
  occurred_at: "2026-11-02T02:30:00Z",
  event_type: "person_forklift_proximity",
  zone_id: "floor",
  view_id: "dock",
  analysis_run_id: "run-a",
  source: {
    kind: "manual",
    filename: "dock.mp4",
    video_sha256: "a".repeat(64),
    config_sha256: "b".repeat(64),
  },
  observations: {
    proximity_geometry: {
      version: "person_equipment_nearest_ground_edges_v1",
      person_anchor: [1, 1],
      equipment_target: [0, 0],
    },
  },
};

test("el recuento por día UTC y por bloque de Santiago registra el mismo conjunto", () => {
  const rows = [
    event,
    { ...event, id: "monday", occurred_at: "2026-11-02T03:15:00Z" },
    { ...event, id: "out", occurred_at: "2026-12-01T00:00:00Z" },
  ];
  const result = summarizeHistory(rows, "2026-11");
  assert.equal(result.total, 2);
  assert.equal(result.days[1].count, 2);
  assert.equal(result.timeMatrix[6][5], 1);
  assert.equal(result.timeMatrix[0][0], 1);
  assert.equal(
    result.timeMatrix.flat().reduce((sum, value) => sum + value),
    result.total,
  );
  assert.equal(result.hours[23].count, 1);
  assert.deepEqual(dayUtcBounds("2026-11", 2), {
    occurred_after: "2026-11-02T00:00:00.000Z",
    occurred_before: "2026-11-02T23:59:59.999999Z",
  });
  assert.throws(() => dayUtcBounds("2026-11", 31), /fuera del período/);
});

test("el mapa espacial conserva límites y aísla ejecuciones, revisiones y épocas", () => {
  const groups = spatialHistory([
    event,
    { ...event, id: "same" },
    { ...event, id: "new-run", analysis_run_id: "run-b" },
    {
      ...event,
      id: "new-config",
      source: { ...event.source, config_sha256: "c".repeat(64) },
    },
    { ...event, id: "epoch", source: { ...event.source, epoch: 2 } },
    { ...event, id: "no-point", observations: {} },
    { ...event, id: "no-hash", source: { kind: "manual" } },
    { ...event, id: "dwell", event_type: "zone_dwell" },
  ]);
  assert.deepEqual(
    groups.map(({ total }) => total),
    [2, 1, 1, 1],
  );
  const corner = spatialColumns * spatialRows - 1;
  assert.deepEqual(groups[0].cells[corner], ["observed", "same"]);
});
