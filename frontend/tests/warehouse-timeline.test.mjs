import assert from "node:assert/strict";
import test from "node:test";
import {
  captureBeat,
  dossierBeat,
  lastBeat,
  storyPaths,
  storyPose,
} from "../src/features/experience/warehouse-timeline.ts";

test("camera and actor poses are continuous and reversible across all chapter cuts", () => {
  const epsilon = 1e-5;
  const frames = Array.from({ length: 241 }, (_, index) => index / 40);
  const forward = frames.map(storyPose);
  assert.deepEqual(frames.toReversed().map(storyPose), forward.toReversed());
  for (let chapter = 1; chapter < lastBeat; chapter++) {
    const before = storyPose(chapter - epsilon);
    const after = storyPose(chapter + epsilon);
    assert.ok(
      before.shot.every((value, i) => Math.abs(value - after.shot[i]) < 1e-4),
    );
    assert.ok(Math.abs(before.worker.x - after.worker.x) < 1e-4);
    assert.ok(Math.abs(before.equipment.yaw - after.equipment.yaw) < 1e-4);
  }
  assert.deepEqual(storyPose(-1), forward[0]);
  assert.deepEqual(storyPose(7), forward.at(-1));
});

test("tracks end at their actors and wheels stop turning once the vehicle stops", () => {
  const pose = storyPose(2);
  const [worker, lift] = storyPaths(pose.person, pose.forklift);
  assert.equal(worker.at(-1).x, pose.worker.x);
  assert.equal(worker.at(-1).z, pose.worker.z);
  assert.equal(lift.at(-1).x, pose.equipment.x);
  assert.equal(lift.at(-1).z, pose.equipment.z);
  assert.ok(pose.equipment.travel > 0);
  assert.equal(storyPose(3).equipment.travel, storyPose(6).equipment.travel);
  assert.equal(storyPose(3).worker.gait, 0);
});

test("each chapter settles with the relevant layer and evidence follows the rule and event", () => {
  assert.equal(storyPose(0).cameraSignal, 1);
  assert.equal(storyPose(1).detection, 1);
  assert.equal(storyPose(2).tracks, 1);
  assert.equal(storyPose(3).spatial, 1);
  assert.deepEqual(
    storyPose(3.54).rules.map((value) => value > 0),
    [true, false, false],
  );
  assert.deepEqual(storyPose(4).rules, [1, 1, 1]);
  assert.equal(storyPose(4).event, 0);
  assert.equal(storyPose(5).event, 1);
  assert.equal(storyPose(captureBeat).evidence, 0);
  const transfer = storyPose((captureBeat + dossierBeat) / 2).evidence;
  assert.ok(transfer > 0 && transfer < 1);
  assert.equal(storyPose(6).evidence, 1);
});
