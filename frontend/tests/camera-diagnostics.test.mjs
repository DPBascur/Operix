import assert from "node:assert/strict";
import test from "node:test";
import {
  cameraAnalysisRate,
  cameraCoverage,
  cameraFrameIsRecent,
  cameraFrameTime,
  cameraObservationPaused,
  cameraTechnicalMetrics,
} from "../src/features/sources/camera-diagnostics.ts";

test("la miniatura exige un fotograma de menos de cinco segundos", () => {
  const receivedAt = Date.parse("2026-11-18T12:00:05.000Z");
  assert.equal(
    cameraFrameIsRecent(null, { last_frame_age_ms: 0 }, receivedAt),
    true,
  );
  assert.equal(
    cameraFrameIsRecent(null, { last_frame_age_ms: 5000 }, receivedAt),
    false,
  );
  assert.equal(
    cameraFrameIsRecent("2026-11-18T12:00:01Z", null, receivedAt),
    true,
  );
  assert.equal(
    cameraFrameIsRecent("2026-11-18T12:00:00Z", null, receivedAt),
    false,
  );
  assert.equal(
    cameraFrameIsRecent("2026-11-18T12:00:06Z", null, receivedAt),
    false,
  );
  assert.equal(cameraFrameIsRecent("inválido", null, receivedAt), false);
});

test("la cobertura usa solo la fracción informada y conserva el cero", () => {
  assert.equal(cameraCoverage({ observed_fraction_5s: 0 }), "0%");
  assert.equal(cameraCoverage({ observed_fraction_5s: 0.375 }), "37,5%");
  assert.equal(cameraCoverage({ observed_fraction_5s: 1 }), "100%");
  for (const fraction of [undefined, null, -0.1, 1.1, "0.5", NaN, Infinity]) {
    assert.equal(
      cameraCoverage({
        observed_fraction_5s: fraction,
        received_fps: 10,
        analysis_fps_5s: 5,
      }),
      null,
    );
  }
});

test("oculta la cobertura reciente con señal interrumpida o datos desactualizados", () => {
  assert.equal(cameraObservationPaused("reconnecting", false), true);
  assert.equal(cameraObservationPaused("no_signal", false), true);
  assert.equal(cameraObservationPaused("analyzing", true), true);
  assert.equal(cameraObservationPaused("analyzing", false), false);
});

test("el ritmo reciente tiene prioridad y el histórico conserva su etiqueta", () => {
  assert.deepEqual(
    cameraAnalysisRate({ analysis_fps_5s: 0, analysis_fps: 6 }),
    {
      label: "Ritmo de análisis (5 s)",
      value: "0 FPS",
    },
  );
  assert.deepEqual(cameraAnalysisRate({ analysis_fps: 6, effective_fps: 7 }), {
    label: "Ritmo medio de análisis de la ejecución",
    value: "6 FPS",
  });
  assert.equal(cameraAnalysisRate({ effective_fps: 7 }).value, "7 FPS");
  assert.equal(cameraAnalysisRate(null).value, null);
});

test("las mediciones técnicas conservan los ceros y omiten etapas sin datos", () => {
  assert.deepEqual(cameraTechnicalMetrics(null), []);
  assert.deepEqual(cameraTechnicalMetrics({ inference_mode: "other" }), []);
  assert.deepEqual(
    cameraTechnicalMetrics({
      queue_depth: 0,
      max_queue_depth: 4,
      p95_arrival_to_result_ms: 17.5,
      p95_arrival_to_publication_ms: 28,
      p95_clip_ms: null,
      inference_mode: "shared",
      p95_inference_queue_ms: 0,
      frames_inference_dropped: 0,
    }),
    [
      {
        title: "Captura local",
        rows: [
          ["Fotogramas en cola", "0"],
          ["Máximo observado en cola", "4"],
        ],
      },
      {
        title: "Procesamiento local (p95)",
        rows: [
          ["Recepción a resultado", "17,5 ms"],
          ["Recepción a publicación", "28 ms"],
        ],
      },
      {
        title: "Inferencia",
        rows: [
          ["Modo", "Compartida"],
          ["Espera en cola p95", "0 ms"],
          ["Descartes en inferencia", "0"],
        ],
      },
    ],
  );
  assert.deepEqual(cameraTechnicalMetrics({ inference_mode: "dedicated" }), [
    { title: "Inferencia", rows: [["Modo", "Dedicada"]] },
  ]);
});

test("los descartes acumulados por motivo y los totales vienen de la API", () => {
  assert.deepEqual(
    cameraTechnicalMetrics({
      frames_dropped: 10,
      frames_inference_dropped: 4,
      inference_drops: { busy: 2, deadline: 1, failed: 1, shutdown: 0 },
    }),
    [
      {
        title: "Inferencia",
        rows: [
          ["Descartes en inferencia", "4"],
          ["Servicio ocupado", "2"],
          ["Plazo de inferencia vencido", "1"],
          ["Fallo de inferencia", "1"],
          ["Detención durante inferencia", "0"],
        ],
      },
      {
        title: "Totales de la ejecución",
        rows: [["Fotogramas descartados", "10"]],
      },
    ],
  );
});

test("la recepción del fotograma convierte UTC a hora de Chile", () => {
  const timestamp = "2026-11-20T23:30:00-03:00";
  const formatted = cameraFrameTime(timestamp);
  assert.match(formatted, /20-11-2026.*23:30:00 · hora de Chile$/);
  assert.equal(formatted, cameraFrameTime("2026-11-21T02:30:00Z"));
  assert.equal(cameraFrameTime("invalid"), null);
  assert.equal(cameraFrameTime(null), null);
});

test("el registro por etapas distingue p95 de evento, PNG y clip", () => {
  const groups = cameraTechnicalMetrics({
    registration_attempts: 6,
    p95_arrival_to_registration_ms: 81,
    p95_arrival_to_publication_ms: 81,
    p95_arrival_to_png_ms: 1012,
    p95_arrival_to_clip_ms: 1518,
    evidence_failed: 0,
    events_skipped_backpressure: 2,
  });
  assert.deepEqual(groups, [
    {
      title: "Registro y evidencia",
      rows: [
        ["Recepción local a registro p95", "81 ms"],
        ["Recepción local a PNG p95", "1.012 ms"],
        ["Recepción local a clip p95", "1.518 ms"],
        ["Eventos omitidos por saturación", "2"],
        ["PNG fallidos", "0"],
      ],
    },
  ]);
});

test("los tiempos de lectura, detectores y anotaciones mantienen su alcance", () => {
  assert.deepEqual(
    cameraTechnicalMetrics({
      p95_capture_read_wall_ms: 68,
      p95_person_detector_ms: 26,
      p95_forklift_detector_ms: 9,
      p95_tracking_ms: 0.4,
      p95_overlays_ms: 3,
    }),
    [
      {
        title: "Captura local",
        rows: [["Lectura RTSP, incluida la espera (p95)", "68 ms"]],
      },
      {
        title: "Procesamiento local (p95)",
        rows: [
          ["Seguimiento", "0,4 ms"],
          ["Dibujo de anotaciones", "3 ms"],
        ],
      },
      {
        title: "Inferencia",
        rows: [
          ["Detector PERSON p95", "26 ms"],
          ["Detector FORKLIFT p95", "9 ms"],
        ],
      },
    ],
  );
});
