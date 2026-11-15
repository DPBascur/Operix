export const lastBeat = 6;
export const secondsPerBeat = 4.2;
export const captureBeat = 5.22;
export const dossierBeat = 5.86;

type Point = readonly [number, number];
type Shot = readonly [
  x: number,
  y: number,
  z: number,
  width: number,
  yaw: number,
  pitch: number,
];

const shots: readonly Shot[] = [
  [0, 0.82, 0, 15.2, 0.594, 0.525],
  [0.23, 0.68, 0.68, 10.9, 0.57, 0.5],
  [0.23, 0.54, 0.33, 9.4, 0.52, 0.53],
  [0.14, 0.27, 0.35, 9.8, 0.54, 0.69],
  [0.08, 0.38, 0.3, 9.45, 0.55, 0.62],
  [0.12, 0.56, 0.24, 8.1, 0.6, 0.53],
  [-0.25, 0.52, 0.27, 8.55, 0.62, 0.51],
];

const personRoute = [
  [-1.9, 1.27],
  [-1.34, 0.98],
  [-0.68, 0.72],
] as const;
const forkliftRoute = [
  [2.35, 0.68],
  [2.0, 0.21],
  [1.33, 0.02],
] as const;

export function unit(value: number) {
  return Math.min(1, Math.max(0, value));
}
export function ramp(value: number, start: number, end: number) {
  return unit((value - start) / (end - start));
}
function ease(value: number) {
  const t = unit(value);
  return t * t * (3 - 2 * t);
}
function mix(a: number, b: number, t: number) {
  return a + (b - a) * t;
}

function curve(route: readonly [Point, Point, Point], t: number) {
  const [a, b, c] = route;
  const u = 1 - t;
  return {
    x: u * u * a[0] + 2 * u * t * b[0] + t * t * c[0],
    z: u * u * a[1] + 2 * u * t * b[1] + t * t * c[1],
    yaw: Math.atan2(
      u * (b[0] - a[0]) + t * (c[0] - b[0]),
      u * (b[1] - a[1]) + t * (c[1] - b[1]),
    ),
  };
}

function arcTable(route: typeof personRoute | typeof forkliftRoute) {
  const result = [0];
  let prev = curve(route, 0);
  for (let i = 1; i <= 40; i++) {
    const next = curve(route, i / 40);
    result.push(result[i - 1] + Math.hypot(next.x - prev.x, next.z - prev.z));
    prev = next;
  }
  return result;
}

const personArc = arcTable(personRoute);
const forkliftArc = arcTable(forkliftRoute);
function distance(table: number[], t: number) {
  const index = Math.min(39, Math.floor(t * 40));
  return mix(table[index], table[index + 1], t * 40 - index);
}

export function storyPaths(person: number, forklift: number) {
  const partial = (
    route: typeof personRoute | typeof forkliftRoute,
    t: number,
  ) => Array.from({ length: 16 }, (_, index) => curve(route, (t * index) / 15));
  return [
    partial(personRoute, person),
    partial(forkliftRoute, forklift),
  ] as const;
}

export function storyPose(progress: number) {
  const beat = Math.min(lastBeat, Math.max(0, progress));
  const index = Math.min(lastBeat - 1, Math.floor(beat));
  const shot = shots[index].map((value, coordinate) =>
    mix(value, shots[index + 1][coordinate], ease(beat - index)),
  ) as unknown as Shot;
  const person = ease(ramp(beat, 1.16, 2.42));
  const forklift = ease(ramp(beat, 1.29, 2.58));
  const worker = curve(personRoute, person);
  const equipment = curve(forkliftRoute, forklift);
  const gait =
    Math.sin((Math.PI * 2 * distance(personArc, person)) / 0.64) *
    ease(ramp(person, 0, 0.14)) *
    (1 - ease(ramp(person, 0.82, 1)));
  const steering = ease(ramp(forklift, 0, 0.3));
  return {
    shot,
    person,
    forklift,
    worker: {
      ...worker,
      yaw: mix(0.59, worker.yaw, ease(ramp(person, 0, 0.22))),
      gait,
    },
    equipment: {
      ...equipment,
      yaw: mix(-0.61, equipment.yaw, steering),
      travel: distance(forkliftArc, forklift),
      steering: 0.26 * Math.sin(Math.PI * forklift),
    },
    cameraSignal: 1 - ramp(beat, 0.2, 0.82),
    detection: ramp(beat, 0.36, 0.91) * (1 - ramp(beat, 2.43, 2.94)),
    tracks: ramp(beat, 1.22, 1.63) * (1 - ramp(beat, 2.6, 3.15)),
    spatial: ramp(beat, 2.36, 2.98) * (1 - ramp(beat, 5.26, 5.82)),
    rules: [3.42, 3.63, 3.83].map((cue) => ramp(beat, cue, cue + 0.16)),
    event: ramp(beat, 4.45, 4.91) * (1 - ramp(beat, 5.3, 5.67)),
    evidence: ease(ramp(beat, captureBeat, dossierBeat)),
  };
}
