import assert from "node:assert/strict";
import test from "node:test";
import { interpolateObservedBoxes } from "../src/features/sources/camera-estimated-boxes.ts";
import {
  CameraFrameMatcher,
  observationLifetime,
  parseLiveObservations,
  sampleLuma,
} from "../src/features/sources/camera-frame-match.ts";

const now = Date.parse("2026-11-23T14:00:00Z");
const pattern = Array.from({ length: 192 }, (_, i) => 32 + ((i * 37) % 160));
const shifted = (value) => pattern.map((sample) => sample + value);

function observation(fields = {}) {
  return {
    index: 10,
    epoch: 1,
    pts_s: 1,
    fingerprint: pattern,
    receivedMs: now - 1000,
    processedMs: now - 900,
    objects: [],
    zones: [],
    ...fields,
  };
}

function update(matcher, ...items) {
  matcher.update({ run_id: "run-1", items }, now);
}

test("uses the engine's 16×12 integer RGB luma convention", () => {
  const rgba = new Uint8ClampedArray(192 * 4);
  rgba.set([
    255, 0, 0, 255, 0, 255, 0, 255, 0, 0, 255, 255, 255, 255, 255, 255,
  ]);
  const samples = sampleLuma(rgba);
  assert.equal(samples.length, 192);
  assert.deepEqual(samples.slice(0, 4), [77, 149, 29, 255]);
});

test("parses valid normalized geometry and nullable PTS, rejecting the old sample grid", () => {
  const item = {
    index: 1,
    epoch: 0,
    pts_s: null,
    received_utc: "2026-11-23T14:00:00+00:00",
    processed_utc: "2026-11-23T14:00:00.024000+00:00",
    fingerprint: pattern,
    objects: [
      { role: "person", track_id: 5, box: [0.1, 0.2, 0.3, 0.4] },
      { role: "person", track_id: null, box: [-1, 0, 1, 1] },
    ],
    zones: [
      {
        zone_id: "dock",
        polygon: [
          [0, 0],
          [1, 0],
          [1, 1],
        ],
      },
    ],
  };
  const parsed = parseLiveObservations({ run_id: "run-1", items: [item] });
  assert.equal(parsed.items[0].receivedMs, now);
  assert.equal(parsed.items[0].processedMs, now + 24);
  assert.equal(parsed.items[0].pts_s, null);
  assert.deepEqual(parsed.items[0].objects, item.objects.slice(0, 1));
  assert.deepEqual(parsed.items[0].zones, item.zones);
  assert.throws(() =>
    parseLiveObservations({
      run_id: "run-1",
      items: [{ ...item, fingerprint: pattern.slice(0, 48) }],
    }),
  );
});

test("rejects uniform images, local outliers, and similar competing frames", () => {
  const matcher = new CameraFrameMatcher();
  const first = observation();
  const flat = Array(192).fill(60);
  update(matcher, first, observation({ index: 11, fingerprint: flat }));
  assert.equal(matcher.match(flat, 24.9, now), undefined);
  const outlier = [...pattern];
  outlier[180] += 13;
  assert.equal(matcher.match(outlier, 24.93, now), undefined);
  assert.equal(matcher.match(shifted(3), 24.96, now), undefined);
  update(matcher, first, observation({ index: 12, fingerprint: shifted(3) }));
  assert.equal(matcher.match(pattern, 25, now), undefined);
});

test("requires an independently distinctive new match after an epoch change", () => {
  const matcher = new CameraFrameMatcher();
  const first = observation();
  update(matcher, first);
  assert.equal(matcher.match(shifted(1), 70, now)?.observation, first);
  const repeated = observation({ index: 0, epoch: 2, pts_s: 0 });
  const unique = observation({
    index: 1,
    epoch: 2,
    pts_s: 0.7,
    fingerprint: shifted(24),
  });
  update(matcher, repeated, unique);
  assert.equal(matcher.match(pattern, 70.97, now), undefined);
  assert.equal(matcher.match(unique.fingerprint, 71, now)?.observation, unique);
  update(matcher, first);
  assert.equal(matcher.match(pattern, 72, now), undefined);
});

test("uses source time for freshness and validates PTS deltas after the first match", () => {
  const matcher = new CameraFrameMatcher();
  const first = observation();
  const next = observation({
    index: 11,
    pts_s: 1.25,
    fingerprint: shifted(24),
  });
  update(matcher, next, first);
  assert.equal(matcher.match(pattern, 500, now)?.observation, first);
  assert.equal(matcher.match(pattern, 500.033, now), undefined);
  assert.equal(matcher.match(next.fingerprint, 500.2, now), undefined);
  assert.equal(matcher.match(next.fingerprint, 500.25, now)?.observation, next);
  assert.equal(matcher.match(next.fingerprint, 500.5, now + 12_000), undefined);

  const stale = observation({ receivedMs: now - 12_000, processedMs: now });
  const future = observation({
    receivedMs: now + 1100,
    processedMs: now + 1200,
  });
  const reversed = observation({ processedMs: now - 2000 });
  for (const item of [stale, future, reversed]) {
    assert.equal(observationLifetime(item, now), 0);
    const freshMatcher = new CameraFrameMatcher();
    update(freshMatcher, item);
    assert.equal(freshMatcher.match(pattern, 25, now), undefined);
  }
});

test("an unavailable response removes eligibility immediately while keeping ambiguity evidence", () => {
  const matcher = new CameraFrameMatcher();
  update(matcher, observation());
  matcher.invalidate();
  assert.equal(matcher.match(pattern, 70, now), undefined);
  const afterGap = observation({ epoch: 2 });
  update(matcher, afterGap);
  assert.equal(matcher.match(pattern, 71, now), undefined);
  matcher.update({ run_id: "run-2", items: [afterGap] }, now);
  assert.equal(matcher.match(pattern, 71, now)?.observation, afterGap);
});

test("evicts older fingerprints once the 256-entry window fills", () => {
  const matcher = new CameraFrameMatcher();
  update(matcher, observation({ receivedMs: now - 2000 }));
  for (let batch = 0; batch < 5; batch++) {
    update(
      matcher,
      ...Array.from({ length: 60 }, (_, i) =>
        observation({
          epoch: 2,
          index: batch * 60 + i,
          fingerprint: shifted(24),
        }),
      ),
    );
  }
  const afterWindow = observation({ epoch: 3 });
  update(matcher, afterWindow);
  assert.equal(matcher.match(pattern, 70, now)?.observation, afterWindow);
});

const anchors = [
  observation(),
  observation({ index: 11, pts_s: 1.033, fingerprint: shifted(24) }),
];
const adjacent = [
  observation({ index: 12, pts_s: 1.066, fingerprint: shifted(48) }),
  observation({ index: 13, pts_s: 1.099, fingerprint: shifted(48) }),
];

test("an unobserved midpoint needs a recent verified predecessor and two adjacent observations", () => {
  const one = observation({ index: 10, pts_s: 1 });
  const two = observation({ index: 11, pts_s: 1.066, fingerprint: shifted(24) });
  const three = observation({ index: 12, pts_s: 1.132, fingerprint: shifted(48) });
  const matcher = new CameraFrameMatcher();
  update(matcher, one, two, three);
  assert.ok(matcher.match(pattern, 10, now));
  assert.equal(matcher.match(shifted(12), 10.033, now), undefined);
  assert.equal(matcher.interpolationBounds(shifted(12), 10.033, now), undefined);
  assert.ok(matcher.match(shifted(24), 10.066, now));
  assert.equal(matcher.match(shifted(36), 10.099, now), undefined);
  assert.equal(matcher.interpolationBounds(shifted(-20), 10.099, now), undefined);
  assert.equal(matcher.interpolationBounds(shifted(36), 10.099, now)?.after, three);
  assert.equal(matcher.interpolationBounds(shifted(36), 10.099, now + 2001), undefined);
  update(matcher, { ...three, epoch: 2 });
  assert.equal(matcher.interpolationBounds(shifted(36), 10.099, now), undefined);
});

test("estimated boxes retain role-qualified IDs and decline crossing or vanished objects", () => {
  const person = { role: "person", track_id: 1, box: [0.1, 0.1, 0.3, 0.5] };
  const vehicle = { ...person, role: "forklift" };
  const moved = { ...person, box: [0.12, 0.1, 0.32, 0.5] };
  const a = observation({ objects: [person, vehicle] });
  const b = observation({ objects: [vehicle, moved] });
  assert.deepEqual(interpolateObservedBoxes(a, b, 0.5), [
    { ...person, box: [0.11, 0.1, 0.31, 0.5] }, vehicle,
  ]);
  const crossing = { ...person, track_id: 2, box: [0.29, 0.2, 0.4, 0.6] };
  assert.deepEqual(interpolateObservedBoxes(a, { ...b, objects: [moved, crossing] }, 0.5), []);
  assert.deepEqual(interpolateObservedBoxes(a, { ...b, epoch: 2 }, 0.5), []);
});

function confirm(matcher, ...evidence) {
  update(matcher, ...anchors, ...adjacent, ...evidence);
  assert.equal(matcher.match(pattern, 10, now)?.method, "image");
  assert.equal(matcher.match(shifted(24), 10.033, now)?.method, "image");
}

test("continuity requires two unique anchors and verifies the currently presented image", () => {
  const unconfirmed = new CameraFrameMatcher();
  update(unconfirmed, ...anchors, ...adjacent);
  assert.equal(unconfirmed.match(pattern, 10, now)?.method, "image");
  assert.equal(unconfirmed.match(shifted(48), 10.066, now), undefined);

  const matcher = new CameraFrameMatcher();
  confirm(matcher);
  assert.equal(matcher.match(shifted(54), 10.066, now), undefined);
  assert.deepEqual(matcher.match(shifted(48), 10.099, now), {
    observation: adjacent[1],
    method: "continuity",
  });
});

test("continuity rejects two aligned candidates, between-frame PTS and cross-epoch evidence", () => {
  const collision = new CameraFrameMatcher();
  confirm(
    collision,
    observation({ index: 20, pts_s: 1.07, fingerprint: shifted(48) }),
  );
  assert.equal(collision.match(shifted(48), 10.066, now), undefined);

  const between = new CameraFrameMatcher();
  confirm(between);
  assert.equal(between.match(shifted(48), 10.0825, now), undefined);

  const crossEpoch = new CameraFrameMatcher();
  update(crossEpoch, observation({ epoch: 0, fingerprint: shifted(48) }));
  confirm(crossEpoch);
  assert.equal(crossEpoch.match(shifted(48), 10.066, now), undefined);
});

test("continuity expires and loses corroboration on gaps, seeks and epoch changes", () => {
  const gap = new CameraFrameMatcher();
  confirm(gap);
  assert.equal(gap.match(shifted(48), 10.5, now), undefined);
  assert.equal(gap.match(shifted(48), 10.066, now), undefined);

  const seek = new CameraFrameMatcher();
  confirm(seek);
  seek.resetTimeline();
  assert.equal(seek.match(shifted(48), 10.066, now), undefined);

  const epoch = new CameraFrameMatcher();
  confirm(epoch);
  update(
    epoch,
    ...adjacent.map((item) => ({
      ...item,
      epoch: 2,
      fingerprint: shifted(61),
    })),
  );
  assert.equal(epoch.match(shifted(61), 10.066, now), undefined);

  const expired = new CameraFrameMatcher();
  confirm(
    expired,
    ...adjacent.map((item) => ({
      ...item,
      index: item.index + 40,
      pts_s: item.pts_s + 1,
      fingerprint: shifted(61),
    })),
  );
  for (let i = 2; i < 32; i++) expired.match(shifted(12), 10 + i * 0.033, now);
  assert.equal(expired.match(shifted(61), 11.066, now), undefined);
});
