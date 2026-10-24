import assert from "node:assert/strict";
import test from "node:test";
import {
  isOperationalEvent,
  eventSubjects,
  eventTypeName,
} from "../src/services/event-contract.ts";

const single = {
  id: "fixture",
  occurred_at: "2026-10-24T12:00:00Z",
  event_type: "zone_dwell",
  rule_id: "r",
  rule_version: 1,
  zone_id: "z",
  track_id: 1,
  class_name: "person",
};
const pair = {
  ...single,
  event_type: "person_forklift_proximity",
  track_id: null,
  class_name: "",
  interaction: {
    person: { class_name: "person", track_id: 1 },
    forklift: { class_name: "forklift", track_id: 1 },
  },
};
test("histórico acepta dos tipos sin inventar un objeto principal para el par", () => {
  assert.ok([single, pair].every(isOperationalEvent));
  assert.equal(eventSubjects(pair), "person · ID 1 ↔ forklift · ID 1");
  assert.equal(eventSubjects(single), "person · ID 1");
  assert.equal(
    eventTypeName(pair.event_type),
    "Proximidad persona–montacargas",
  );
});
test("rechaza pares incompletos y tipos desconocidos sin sustituir datos por ejemplos", () => {
  assert.equal(isOperationalEvent({ ...pair, interaction: {} }), false);
  assert.equal(isOperationalEvent({ ...pair, track_id: 1 }), false);
  assert.equal(
    isOperationalEvent({ ...single, event_type: "invented" }),
    false,
  );
});
