import assert from "node:assert/strict";
import test from "node:test";
import {
  eventMeasurements,
  eventMotion,
  eventProximityGeometry,
  eventTime,
  evidenceHref,
  evidenceClip,
  measurement,
  operationalSubjects,
  record,
} from "../src/features/events/event-detail-model.ts";

const single = {
  id: "fixture",
  event_type: "zone_dwell",
  occurred_at: "2026-10-24T12:00:00Z",
  observed_dwell_time_s: "2.000000000",
  rule_parameters: { min_duration_s: 2 },
};
test("clip solo usa la URL del evento y run exactos", () => {
  const event = {
    ...single,
    analysis_run_id: "run",
    evidence_clip: {
      kind: "annotated",
      event_id: single.id,
      analysis_run_id: "run",
      event_offset_s: 0,
      url: "/api/v1/events/fixture/clips/run/",
    },
  };
  assert.deepEqual(evidenceClip(event, "/api/v1"), {
    url: event.evidence_clip.url,
    offset: 0,
  });
  assert.equal(
    evidenceClip({ ...event, analysis_run_id: "otro" }, "/api/v1"),
    null,
  );
  assert.equal(evidenceClip(single, "/api/v1"), null);
});
test("detalle conserva duración y mínimo sin evaluar ni cambiar la regla", () => {
  assert.deepEqual(eventMeasurements(single), [
    {
      label: "Permanencia",
      observed: "2 s",
      configured: "2 s",
      criterion: "Mínimo configurado",
    },
  ]);
  assert.equal(measurement(0), "0 s");
  assert.equal(measurement("0.033333333"), "0,033333333 s");
  assert.equal(measurement("0.000000000001"), "0,000000000001 s");
});
test("pares muestran distancia sin metros y duración desde observaciones reales", () => {
  const metrics = eventMeasurements({
    ...single,
    event_type: "person_forklift_proximity",
    observations: { normalized_distance: 0.2, duration_s: 1.25 },
    rule_parameters: { max_distance: 0.25, minimum_duration_seconds: 1 },
  });
  assert.equal(metrics[0].observed, "0,2");
  assert.equal(metrics[0].configured, "0,25");
  assert.equal(metrics[1].observed, "1,25 s");
  assert.equal(metrics[1].configured, "1 s");
});
test("geometría explícita conserva extremos, versión histórica y ausencia de datos", () => {
  const pair = { ...single, event_type: "person_forklift_proximity" };
  assert.equal(eventProximityGeometry(single), null);
  assert.deepEqual(eventProximityGeometry(pair), {
    version: "No registrado",
    personAnchor: null,
    equipmentTarget: null,
  });
  assert.equal(eventMeasurements(pair)[0].observed, "No registrada");
  for (const version of [
    "person_equipment_nearest_ground_edges_v1",
    "person_bottom_center_to_equipment_ground_edge_v1",
  ]) {
    const event = {
      ...pair,
      observations: {
        normalized_distance: 0,
        duration_s: 0,
        proximity_geometry: {
          version,
          person_anchor: [0, 1],
          equipment_target: [0, 1],
        },
      },
      rule_parameters: { max_distance: 0, minimum_duration_seconds: 0 },
    };
    assert.deepEqual(eventProximityGeometry(event), {
      version,
      personAnchor: "[0,1]",
      equipmentTarget: "[0,1]",
    });
    assert.equal(eventMeasurements(event)[0].observed, "0");
    assert.equal(eventMeasurements(event)[0].configured, "0");
    assert.equal(eventMeasurements(event)[1].observed, "0 s");
  }
});
test("ausentes, booleanos y valores inválidos no se convierten en ceros", () => {
  for (const value of [
    null,
    undefined,
    "",
    true,
    false,
    {},
    [],
    -1,
    Infinity,
    "NaN",
  ])
    assert.equal(measurement(value), "No registrada");
  assert.deepEqual(record(null), {});
  assert.deepEqual(record([]), {});
  assert.equal(
    eventMeasurements({ ...single, rule_parameters: undefined })[0].configured,
    "No registrada",
  );
});
test("el ancla del análisis no se presenta como fecha de grabación", () => {
  const proxy = eventTime({
    ...single,
    source: { timestamp_basis: "ANALYSIS_START_PROXY_NOT_RECORDING_TIME" },
  });
  assert.equal(proxy.label, "Referencia del análisis · UTC");
  assert.match(proxy.explanation, /no es la fecha de grabación/);
  assert.equal(proxy.iso, "2026-10-24T12:00:00Z");
  assert.match(eventTime(single).explanation, /Base temporal no registrada/);
});
test("trazabilidad conserva microsegundos y offset originales sin normalizarlos", () => {
  for (const value of [
    "2026-10-24T23:31:23.772430Z",
    "2026-10-24T20:31:23.772430-03:00",
  ])
    assert.equal(eventTime({ ...single, occurred_at: value }).iso, value);
});
test("objetos se traducen sin inventar identidades ni colisionar IDs de clases", () => {
  assert.equal(
    operationalSubjects({ ...single, class_name: "person", track_id: 7 }),
    "Persona · ID de seguimiento 7",
  );
  assert.equal(
    operationalSubjects({
      ...single,
      event_type: "person_forklift_proximity",
      track_id: null,
      interaction: {
        person: { class_name: "person", track_id: 1 },
        forklift: { class_name: "forklift", track_id: 1 },
      },
    }),
    "Persona · ID de seguimiento 1 ↔ Montacargas · ID de seguimiento 1",
  );
});
test("evidencia usa solo el endpoint del evento en la API configurada", () => {
  const event = { ...single, evidence_url: "/api/v1/events/fixture/evidence/" };
  assert.equal(
    evidenceHref(event, "http://127.0.0.1:8000/api/v1"),
    "http://127.0.0.1:8000/api/v1/events/fixture/evidence/",
  );
  for (const url of [
    null,
    "https://elsewhere.test/image.png",
    "/api/v1/events/other/evidence/",
    "//elsewhere.test/image.png",
  ])
    assert.equal(
      evidenceHref(
        { ...event, evidence_url: url },
        "http://127.0.0.1:8000/api/v1",
      ),
      null,
    );
  assert.equal(evidenceHref(event, "javascript:alert(1)"), null);
  assert.equal(evidenceHref(event, "/api/v1"), event.evidence_url);
  assert.equal(
    evidenceHref(
      { ...event, evidence_url: "//elsewhere.test/image.png" },
      "/api/v1",
    ),
    null,
  );
});

test("distancia de suelo usa observación métrica y conserva extremos del Motor", () => {
  const event = {
    ...single,
    event_type: "person_forklift_proximity",
    rule_parameters: {
      distance_unit: "m",
      max_distance: 2,
      minimum_duration_seconds: 1,
    },
    observations: {
      normalized_distance: 0.1,
      duration_s: 1,
      ground: {
        units: "m",
        distance: 1.5,
        method: "ground_plane_contact_edges_v1",
        person_anchor: [0.1, 0.2],
        equipment_target: [0.3, 0.2],
      },
    },
  };
  assert.equal(eventMeasurements(event)[0].observed, "1,5 m aprox.");
  assert.equal(eventMeasurements(event)[0].configured, "2 m aprox.");
  assert.equal(
    eventProximityGeometry(event).version,
    "ground_plane_contact_edges_v1",
  );
  assert.equal(eventProximityGeometry(event).personAnchor, "[0.1,0.2]");
});
test("ingreso y coexistencia no se presentan como distancia ni accidente", () => {
  assert.equal(
    eventMeasurements({ ...single, event_type: "zone_entry" })[0].observed,
    "Fuera → dentro",
  );
  const co = {
    ...single,
    event_type: "zone_coexistence",
    rule_parameters: { minimum_duration_seconds: 1 },
    observations: { duration_s: 2 },
    interaction: {
      person: { class_name: "person", track_id: 1 },
      forklift: { class_name: "forklift", track_id: 1 },
    },
  };
  assert.equal(eventMeasurements(co).length, 1);
  assert.match(operationalSubjects(co), /Persona.*1.*Montacargas.*1/);
});

test("un snapshot métrico incompleto nunca se reinterpreta como normalizado", () => {
  const event = {
    ...single,
    event_type: "person_forklift_proximity",
    rule_parameters: { distance_unit: "m", max_distance: 2 },
    observations: { normalized_distance: 0.1 },
  };
  assert.equal(eventMeasurements(event)[0].observed, "No registrada");
  assert.equal(eventMeasurements(event)[0].configured, "2 m aprox.");
});

test("metros aproximados usan cuatro cifras visibles sin alterar el snapshot", () => {
  const event = {
    ...single,
    event_type: "person_forklift_proximity",
    rule_parameters: { distance_unit: "m", max_distance: 2.5 },
    observations: { ground: { units: "m", distance: 1.58818615349 } },
  };
  const snapshot = JSON.stringify(event);
  assert.equal(eventMeasurements(event)[0].observed, "1,588 m aprox.");
  assert.equal(JSON.stringify(event), snapshot);
});

test("movimiento histórico opcional y unidades de imagen no se presentan como m/s", () => {
  assert.equal(eventMotion(single), null);
  const event = {
    ...single,
    observations: {
      equipment_motion: {
        state: "MOVING",
        speed: 0.023456,
        unit: "normalized_image_per_s",
        duration_s: 1,
        configuration: { window_seconds: 1 },
      },
    },
  };
  assert.match(eventMotion(event).speed, /unidades de imagen/);
  assert.doesNotMatch(eventMotion(event).speed, /m\/s/);
  event.observations.equipment_motion.state = "UNKNOWN";
  assert.equal(eventMotion(event).speed, "No determinada");
  event.observations.equipment_motion.state = "STATIONARY";
  event.observations.equipment_motion.speed = 0;
  assert.match(eventMotion(event).speed, /^0 /);
});
test("movimiento métrico conserva datos observados y condición opcional", () => {
  const event = {
    ...single,
    rule_parameters: { motion_condition: "moving" },
    observations: {
      equipment_motion: {
        state: "MOVING",
        speed: 1.123456,
        unit: "m_per_s",
        duration_s: 1,
        configuration: { window_seconds: 1 },
      },
    },
  };
  assert.equal(eventMotion(event).speed, "1,123 m/s aprox.");
  assert.equal(eventMotion(event).condition, "Solo con movimiento confirmado");
  assert.equal(event.observations.equipment_motion.speed, 1.123456);
});
