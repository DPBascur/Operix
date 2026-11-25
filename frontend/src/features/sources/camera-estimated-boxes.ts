import type { LiveObservation, LiveObject } from "./camera-frame-match";

type Box = LiveObject["box"];

function envelope(a: Box, b: Box): Box {
  return [
    Math.min(a[0], b[0]), Math.min(a[1], b[1]),
    Math.max(a[2], b[2]), Math.max(a[3], b[3]),
  ];
}

function intersection(a: Box, b: Box) {
  return Math.max(0, Math.min(a[2], b[2]) - Math.max(a[0], b[0])) *
    Math.max(0, Math.min(a[3], b[3]) - Math.max(a[1], b[1]));
}

function area(box: Box) {
  return (box[2] - box[0]) * (box[3] - box[1]);
}

function family(object: LiveObject) {
  return object.observation ? "industrial_equipment" : object.role;
}

function identity(object: LiveObject) {
  return JSON.stringify([family(object), object.track_id]);
}

export function interpolateObservedBoxes(
  before: LiveObservation,
  after: LiveObservation,
  fraction: number,
): LiveObject[] {
  if (
    !(fraction > 0 && fraction < 1) || before.epoch !== after.epoch ||
    before.objects.length > 32 || after.objects.length > 32
  ) return [];

  const right = new Map(after.objects.map((object) => [identity(object), object]));
  if (right.size !== after.objects.length ||
      new Set(before.objects.map(identity)).size !== before.objects.length) return [];

  const obstructions = new Map<string, { role: string; box: Box }>();
  for (const object of [...before.objects, ...after.objects]) {
    const id = identity(object);
    const existing = obstructions.get(id);
    obstructions.set(id, {
      role: family(object),
      box: existing ? envelope(existing.box, object.box) : object.box,
    });
  }

  return before.objects.flatMap((object) => {
    const id = identity(object);
    const end = right.get(id);
    if (!end || object.track_id === null) return [];
    const overlap = intersection(object.box, end.box);
    if (overlap / (area(object.box) + area(end.box) - overlap) < 0.65) return [];

    const swept = envelope(object.box, end.box);
    for (const [otherId, other] of obstructions) {
      if (other.role === family(object) && otherId !== id && intersection(swept, other.box) > 0) return [];
    }

    const [x1, y1, x2, y2] = object.box.map(
      (value, i) => value + fraction * (end.box[i] - value),
    );
    const role = object.role === end.role ? object.role : "industrial_equipment";
    return [{ role, track_id: object.track_id, box: [x1, y1, x2, y2] as Box }];
  });
}
