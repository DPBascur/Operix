import assert from "node:assert/strict";
import test from "node:test";
import { pointInFrame } from "../src/features/analysis/zone-editor-geometry.ts";

const sample = (clientX, clientY, width = 200, height = 100) => ({
  clientX,
  clientY,
  currentTarget: {
    getBoundingClientRect: () => ({ left: 10, top: 20, width, height }),
  },
});

test("normaliza respecto del rectángulo visible, no de la resolución fuente", () => {
  assert.deepEqual(pointInFrame(sample(110, 45)), [0.5, 0.25]);
});

test("limita los bordes sin modificar el frame ni la geometría aplicada", () => {
  assert.deepEqual(pointInFrame(sample(-100, 1000)), [0, 1]);
});

test("el punto capturado sobrevive al evento React liberado y a updaters diferidos", () => {
  const event = sample(60, 95);
  const point = pointInFrame(event);
  const updater = (vertices) => [...vertices, point];
  event.currentTarget = null;
  assert.deepEqual(updater([]), [[0.25, 0.75]]);
  assert.deepEqual(updater([]), [[0.25, 0.75]]);
});

test("un canvas sin área visible no produce coordenadas NaN", () => {
  assert.equal(pointInFrame(sample(0, 0, 0)), null);
  assert.equal(pointInFrame(sample(0, 0, 200, 0)), null);
});
