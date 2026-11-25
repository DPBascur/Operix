import assert from "node:assert/strict";
import test from "node:test";
import { CameraSourceClock, ClockedObservations } from "../src/features/sources/camera-source-clock.ts";
import { distanceLabel, readDistances } from "../src/features/sources/camera-frame-match.ts";

const stream = "a".repeat(32);
const nextStream = "b".repeat(32);
const uuid = "2dcd53fa-e376-4a1b-81c9-90511ff6dc2f";
const mark = (pts, ordinal, emission = stream) => ({ pts, uuid, userData: `ox1:${emission}:${ordinal}` });

test("distances are limited to the current epoch and metres require a valid calibration", () => {
  const packet = { person_id: 1, equipment_id: 1, person_point: [.2, .6], equipment_point: [.35, .6], value: 1.5, unit: "m" };
  const pairs = readDistances([packet], "VALID");
  assert.equal(distanceLabel(pairs[0]), "≈1,50 m");
  assert.equal(distanceLabel(pairs[0], "cm"), "≈150 cm");
  assert.deepEqual(readDistances([packet], "UNCALIBRATED"), []);
  assert.deepEqual(readDistances([packet], "SUSPECT"), []);
  assert.equal(distanceLabel(readDistances([{ ...packet, value: 0, unit: "normalized" }], "UNCALIBRATED")[0], "cm"), "0,000 norm.");
  const seen = new ClockedObservations();
  const before = { source_ordinal: 1, epoch: 1, calibration: "VALID", distances: pairs };
  seen.update({ run_id: "run", stream_id: stream, items: [before] });
  assert.equal(seen.distancesFor(before), pairs);
  seen.update({ run_id: "run", stream_id: stream, items: [before, { ...before, source_ordinal: 2, epoch: 2 }] });
  assert.equal(seen.distancesFor(before), undefined);
  seen.update({ run_id: "run", stream_id: stream, items: [{ ...before, calibration: "INVALID", distances: [] }] });
  assert.equal(seen.distancesFor(before), undefined);
});

test("uses the HLS presentation timestamp, rejecting other emissions and off-frame matches", () => {
  const clock = new CameraSourceClock();
  clock.ingest([mark(5, 42), mark(5.033333, 43), mark(5.066667, 44)]);
  assert.equal(clock.at(5.034, stream)?.ordinal, 43);
  assert.equal(clock.at(5.039, stream), undefined);
  assert.equal(clock.at(5.033333, nextStream), undefined);
  clock.clear();
  assert.equal(clock.at(5, stream), undefined);
});

test("conflicting presentation timestamps invalidate the frame instead of replacing its identity", () => {
  const clock = new CameraSourceClock();
  clock.ingest([mark(5, 42), mark(5, 24, nextStream), mark(5, 42)]);
  assert.equal(clock.at(5, stream), undefined);
  assert.equal(clock.at(5, nextStream), undefined);
});

test("exact observations survive queue epochs but interpolation cannot span them", () => {
  const observations = new ClockedObservations();
  const before = { source_ordinal: 41, index: 12, epoch: 1 };
  const after = { source_ordinal: 43, index: 13, epoch: 1 };
  observations.update({ run_id: "run", stream_id: stream, items: [before, after] });
  assert.deepEqual(observations.bracket(42), { before, after });
  assert.equal(observations.bracket(41), undefined);
  observations.update({ run_id: "run", stream_id: stream, items: [before, { ...after, epoch: 2 }] });
  assert.equal(observations.observed(41), before);
  assert.equal(observations.bracket(42), undefined);
  observations.update(null);
  assert.equal(observations.observed(43), undefined);
});

test("a 15 FPS stream keeps all frame marks when only 12 frames are analyzed", () => {
  const clock = new CameraSourceClock();
  const observations = new ClockedObservations();
  const frames = Array.from({ length: 15 }, (_, ordinal) => mark(5 + ordinal / 15, ordinal));
  const samples = frames.map((_, ordinal) => ordinal).filter(ordinal => ordinal % 5 !== 1);
  clock.ingest(frames);
  observations.update({ run_id: "run", stream_id: stream, items: samples.map((ordinal, index) => ({
    source_ordinal: ordinal, index, epoch: 1,
  })) });

  for (let ordinal = 0; ordinal < 15; ordinal++) {
    const sourceFrame = clock.at(5 + ordinal / 15, stream);
    assert.equal(sourceFrame?.ordinal, ordinal);
    if (samples.includes(ordinal)) {
      assert.equal(observations.observed(ordinal)?.source_ordinal, ordinal);
      assert.equal(observations.bracket(ordinal), undefined);
    } else {
      assert.equal(observations.observed(ordinal), undefined);
      const bracket = observations.bracket(ordinal);
      assert.equal(bracket?.before.source_ordinal, ordinal - 1);
      assert.equal(bracket?.after.source_ordinal, ordinal + 1);
    }
  }
});

test("a metadata refresh keeps a valid presented layer and revokes it across resets", () => {
  const observations = new ClockedObservations();
  const before = { source_ordinal: 41, index: 12, epoch: 1, receivedMs: 1000 };
  const after = { source_ordinal: 43, index: 13, epoch: 1, receivedMs: 1100 };
  const update = (items, emission = stream) => observations.update({ run_id: "run", stream_id: emission, items });
  update([{ ...before }, { ...after }]);
  assert.equal(observations.retains(stream, 41, before, false), true);
  assert.equal(observations.retains(stream, 42, before, true), true);
  update([before, { ...after, epoch: 2 }]);
  assert.equal(observations.retains(stream, 42, before, true), false);
  update([before, before]);
  assert.equal(observations.retains(stream, 41, before, false), false);
  update([before], nextStream);
  assert.equal(observations.retains(stream, 41, before, false), false);
});
