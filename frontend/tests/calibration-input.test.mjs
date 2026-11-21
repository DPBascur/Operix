import assert from "node:assert/strict";
import test from "node:test";
import {
  calibrationFrame,
  readControl,
  readLayout,
} from "../src/features/calibration/calibration-input.ts";

const marker = (id) => ({
  id: String(id),
  x_m: "0",
  y_m: "-1,25",
  size_m: "0,2",
  rotation_deg: "-90",
});
const points = [
  [0.2, 0.3],
  [0.7, 0.3],
];

test("bounds ArUco layout and submits measured inputs and provenance", () => {
  const markers = [marker(0), marker(3), marker(49)];
  const layout = readLayout(markers, " Plano medido ");
  assert.equal(layout.dictionary, "DICT_4X4_50");
  assert.equal(layout.provenance, "Plano medido");
  assert.deepEqual(layout.markers[0], {
    id: 0,
    x_m: 0,
    y_m: -1.25,
    size_m: 0.2,
    rotation_deg: -90,
  });
  assert.equal(readLayout(markers.slice(1), "Plano"), null);
  assert.equal(
    readLayout(
      Array.from({ length: 9 }, (_, id) => marker(id)),
      "Plano",
    ),
    null,
  );
  assert.equal(readLayout([marker(3), ...markers.slice(1)], "Plano"), null);
  assert.equal(
    readLayout(
      [{ ...marker(0), rotation_deg: "" }, ...markers.slice(1)],
      "Plano",
    ),
    null,
  );
  assert.equal(
    readLayout(
      [{ ...marker(0), size_m: "0,001" }, ...markers.slice(1)],
      "Plano",
    ),
    null,
  );
  assert.equal(readLayout(markers, " "), null);
});

test("control needs distinct normalized points, a physical measurement and tolerance", () => {
  assert.deepEqual(readControl(points, "2,5", "0,05", " Cinta "), {
    image_points: points,
    distance_m: 2.5,
    tolerance_m: 0.05,
    provenance: "Cinta",
  });
  assert.equal(
    readControl([points[0], points[0]], "2.5", ".05", "Cinta"),
    null,
  );
  assert.equal(
    readControl([points[0], [1.1, 0.5]], "2.5", ".05", "Cinta"),
    null,
  );
  assert.equal(readControl(points, "2.5", "0", "Cinta"), null);
  assert.equal(readControl(points, "2.5", "3", "Cinta"), null);
  assert.equal(readControl(points, "2.5", ".05", " "), null);
});

test("accepts only a bounded inline JPEG from the proposal API", () => {
  const prefix = "data:image/jpeg;base64,";
  assert.equal(calibrationFrame(`${prefix}/9j/`), `${prefix}/9j/`);
  for (const value of [
    "https://example.com/frame.jpg",
    "data:image/png;base64,/9j/",
    `${prefix}/9j/\n`,
    `${prefix}AAAA`,
    `${prefix}/9j/${"A".repeat(720_000)}`,
  ]) {
    assert.equal(calibrationFrame(value), null);
  }
});
