import assert from "node:assert/strict";
import test from "node:test";
import { CameraSourceClock, ClockedObservations } from "../src/features/sources/camera-source-clock.ts";

const stream = "a".repeat(32);
const nextStream = "b".repeat(32);
const uuid = "2dcd53fa-e376-4a1b-81c9-90511ff6dc2f";
const mark = (pts, ordinal, emission = stream) => ({ pts, uuid, userData: `ox1:${emission}:${ordinal}` });

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
