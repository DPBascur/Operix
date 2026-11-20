import assert from "node:assert/strict";
import test from "node:test";
import {
  pointInFrame,
  removeVertex,
  validPolygon,
} from "../src/features/analysis/zone-editor-geometry.ts";

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

test("elimina solo el vértice elegido sin mutar el polígono original", () => {
  const points = [
    [0, 0],
    [1, 0],
    [1, 1],
    [0, 1],
  ];
  assert.deepEqual(removeVertex(points, 1), [
    [0, 0],
    [1, 1],
    [0, 1],
  ]);
  assert.equal(points.length, 4);
});

test("protege el mínimo de tres puntos e ignora selecciones inválidas", () => {
  const triangle = [
    [0, 0],
    [1, 0],
    [0, 1],
  ];
  assert.equal(removeVertex(triangle, 1), triangle);
  const square = [...triangle, [0.5, 0.5]];
  for (const index of [null, -1, 4, 0.5])
    assert.equal(removeVertex(square, index), square);
});

test("rechaza coordenadas incompletas, cruces y lados que tocan un vértice ajeno", () => {
  assert.equal(
    validPolygon([
      [0, 0],
      [1, 0],
      [1, 1],
      [0, 1],
    ]),
    true,
  );
  assert.equal(
    validPolygon([
      [0, 0],
      [1, 1],
      [0, 1],
      [1, 0],
    ]),
    false,
  );
  assert.equal(
    validPolygon([
      [0, 0],
      [1, 0],
      [0.5, 0],
      [1, 1],
      [0, 1],
    ]),
    false,
  );
  assert.equal(
    validPolygon([
      [0, 0],
      [1, 0],
      [Number.NaN, 1],
    ]),
    false,
  );
  assert.equal(
    validPolygon([
      [0, 0],
      [1.1, 0],
      [1, 1],
    ]),
    false,
  );
});
