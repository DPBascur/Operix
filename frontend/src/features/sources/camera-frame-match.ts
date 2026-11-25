export const calibrationLabels = {
  UNCALIBRATED: "Sin calibración física",
  UNAVAILABLE: "Calibración sin verificar en este encuadre",
  SUSPECT: "Mediciones suspendidas por cambio de encuadre",
  INVALID: "Calibración inválida · requiere confirmación",
  VALID: "Calibración verificada en este encuadre",
} as const;

export type LiveCalibration = keyof typeof calibrationLabels;
type Contact = [number, number];
export type LiveDistance = {
  personId: number;
  equipmentId: number;
  equipmentCategory: string;
  personPoint: Contact;
  equipmentPoint: Contact;
  value: number;
  unit: "m" | "normalized";
};

export function readCalibration(value: unknown): LiveCalibration | undefined {
  return typeof value === "string" && Object.hasOwn(calibrationLabels, value)
    ? value as LiveCalibration
    : undefined;
}

function contact(value: unknown): Contact | undefined {
  if (Array.isArray(value) && value.length === 2 &&
      value.every((part) => typeof part === "number" && Number.isFinite(part) && part >= 0 && part <= 1)) {
    return [value[0], value[1]];
  }
}

function trackId(value: unknown): value is number {
  return typeof value === "number" && Number.isSafeInteger(value) && value > 0;
}

export function readDistances(value: unknown, calibration?: LiveCalibration): LiveDistance[] {
  if (!Array.isArray(value) || (calibration !== "VALID" && calibration !== "UNCALIBRATED")) return [];
  const pairs: LiveDistance[] = [];
  for (const candidate of value.slice(0, 12)) {
    if (!candidate || typeof candidate !== "object") continue;
    const { person_id, equipment_id, person_point, equipment_point, equipment_category, value, unit } = candidate;
    const personPoint = contact(person_point);
    const equipmentPoint = contact(equipment_point);
    if (!trackId(person_id) || !trackId(equipment_id) || !personPoint || !equipmentPoint ||
        !Number.isFinite(value) || value < 0 ||
        (unit !== "normalized" && !(unit === "m" && calibration === "VALID"))) continue;
    pairs.push({ personId: person_id, equipmentId: equipment_id,
      equipmentCategory: typeof equipment_category === "string" ? equipment_category : "UNKNOWN",
      personPoint, equipmentPoint, value, unit });
  }
  return pairs;
}

const metres = new Intl.NumberFormat("es-CL", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const normalizedFormat = new Intl.NumberFormat("es-CL", { minimumFractionDigits: 3, maximumFractionDigits: 3 });

const centimetres = new Intl.NumberFormat("es-CL", { maximumFractionDigits: 0 });

export function distanceLabel(pair: LiveDistance, metricUnit: "m" | "cm" = "m") {
  if (pair.unit === "m" && metricUnit === "cm") return `≈${centimetres.format(pair.value * 100)} cm`;
  return pair.unit === "m" ? `≈${metres.format(pair.value)} m` : `${normalizedFormat.format(pair.value)} norm.`;
}

export type LivePoint = [number, number];
export type LiveZone = { zone_id: string; polygon: LivePoint[] };
export type LiveObject = {
  role: string;
  track_id: number | string | null;
  box: [number, number, number, number];
};

type Epoch = number | string;
export type LiveObservation = {
  index: number;
  epoch: Epoch;
  pts_s: number | null;
  receivedMs: number;
  processedMs: number;
  fingerprint: number[];
  objects: LiveObject[];
  zones: LiveZone[];
  source_ordinal?: number;
  calibration?: LiveCalibration;
  distances?: LiveDistance[];
};

export type LiveObservations = { run_id: string; items: LiveObservation[]; stream_id?: string };

const maxAgeMs = 12_000;
const clockToleranceMs = 1000;
const maxFrameGapSeconds = 0.25;
const maxAnchorGapSeconds = 2;
const continuityWindowSeconds = 1;
const interpolationAgeMs = 3_000;
export const sampleColumns = 16;
export const sampleRows = 12;
const sampleCount = sampleColumns * sampleRows;
const maxHistory = 256;
const ambiguityWindowMs = 20_000;

function record(value: unknown): value is Record<string, unknown> {
  return !!value && typeof value === "object" && !Array.isArray(value);
}

function normalized(values: unknown, length: number): values is number[] {
  return (
    Array.isArray(values) &&
    values.length === length &&
    values.every((v) => Number.isFinite(v) && v >= 0 && v <= 1)
  );
}

function readObject(value: unknown): LiveObject | undefined {
  if (!record(value) || typeof value.role !== "string") return;
  const { box, track_id, role } = value;
  if (
    !normalized(box, 4) ||
    box[0] >= box[2] ||
    box[1] >= box[3] ||
    !(
      track_id === null ||
      typeof track_id === "string" ||
      typeof track_id === "number"
    )
  )
    return;
  return { role, track_id, box: [box[0], box[1], box[2], box[3]] };
}

function readZones(value: unknown): LiveZone[] {
  if (!Array.isArray(value)) return [];
  return value.flatMap((zone): LiveZone[] => {
    if (
      !record(zone) ||
      zone.enabled === false ||
      typeof zone.zone_id !== "string" ||
      !Array.isArray(zone.polygon) ||
      zone.polygon.length < 3 ||
      !zone.polygon.every((point) => normalized(point, 2))
    )
      return [];
    return [
      {
        zone_id: zone.zone_id,
        polygon: zone.polygon.map(([x, y]) => [x, y]),
      },
    ];
  });
}

function timestamp(value: unknown) {
  return typeof value === "string" && /(?:Z|[+-]\d{2}:\d{2})$/i.test(value)
    ? Date.parse(value)
    : NaN;
}

export function parseLiveObservations(value: unknown): LiveObservations {
  if (
    !record(value) ||
    typeof value.run_id !== "string" ||
    !value.run_id ||
    !Array.isArray(value.items) ||
    value.items.length > 64
  ) {
    throw new Error("Respuesta de observaciones inválida.");
  }
  const streamId = value.stream_id;
  if (streamId !== undefined && (typeof streamId !== "string" || !/^[a-f0-9]{32}$/.test(streamId))) {
    throw new Error("Identificador de emisión inválido.");
  }
  const items = value.items.map((item: unknown): LiveObservation => {
    if (!record(item)) throw new Error("Observación inválida.");
    const { index, epoch, pts_s, fingerprint, objects, zones, source_ordinal } = item;
    const receivedMs = timestamp(item.received_utc);
    const processedMs = timestamp(item.processed_utc);
    if (
      typeof index !== "number" ||
      !Number.isSafeInteger(index) ||
      index < 0 ||
      !(
        (typeof epoch === "number" &&
          Number.isSafeInteger(epoch) &&
          epoch >= 0) ||
        (typeof epoch === "string" && epoch.length > 0)
      ) ||
      !(
        pts_s === null ||
        (typeof pts_s === "number" && Number.isFinite(pts_s))
      ) ||
      !Number.isFinite(receivedMs) ||
      !Number.isFinite(processedMs) ||
      (streamId !== undefined && (typeof source_ordinal !== "number" || !Number.isSafeInteger(source_ordinal) || source_ordinal < 0 || source_ordinal > 999_999_999)) ||
      !Array.isArray(fingerprint) ||
      fingerprint.length !== sampleCount ||
      !fingerprint.every(
        (sample) => Number.isInteger(sample) && sample >= 0 && sample <= 255,
      ) ||
      !Array.isArray(objects)
    )
      throw new Error("Observación inválida.");
    const calibration = readCalibration(item.calibration);
    return {
      index,
      epoch,
      pts_s,
      receivedMs,
      processedMs,
      fingerprint,
      objects: objects.map(readObject).filter((object) => object !== undefined),
      zones: readZones(zones),
      ...(typeof source_ordinal === "number" && { source_ordinal }),
      ...(streamId && calibration && { calibration, distances: readDistances(item.distances, calibration) }),
    };
  });
  return { run_id: value.run_id, items, ...(streamId !== undefined && { stream_id: streamId }) };
}

export function sampleLuma(rgba: Uint8ClampedArray) {
  return Array.from({ length: sampleCount }, (_, i) => {
    const offset = 4 * i;
    return Math.round(
      (77 * rgba[offset] + 150 * rgba[offset + 1] + 29 * rgba[offset + 2]) /
        256,
    );
  });
}

export function gridSourceRect(
  width: number,
  height: number,
): [number, number, number, number] {
  // Chromium can resolve exact nearest-neighbor ties toward the preceding pixel.
  // This bias selects floor(center), as the engine does, without crossing the
  // next pixel boundary for non-integer centers on the 16×12 grid.
  const bias = 1 / 64;
  return [bias, bias, width - bias, height - bias];
}

function distance(frame: readonly number[], fingerprint: ArrayLike<number>) {
  let total = 0;
  for (let i = 0; i < sampleCount; i++) {
    const delta = Math.abs(frame[i] - fingerprint[i]);
    if (delta > 12) return Infinity;
    total += delta;
    if (total > 4 * sampleCount) return Infinity;
  }
  return total / sampleCount;
}

export function observationLifetime(observation: LiveObservation, now: number) {
  if (
    observation.receivedMs > now + clockToleranceMs ||
    observation.processedMs > now + clockToleranceMs ||
    observation.processedMs < observation.receivedMs
  )
    return 0;
  return Math.max(0, observation.receivedMs + maxAgeMs - now);
}

export class CameraFrameMatcher {
  private run: string | undefined;
  private latest: LiveObservation | undefined;
  private fingerprints = new Map<
    string,
    {
      fingerprint: Uint8Array;
      receivedMs: number;
      pts_s: number | null;
      epoch: Epoch;
    }
  >();
  private eligible = new Map<string, LiveObservation>();
  private anchor:
    { mediaTime: number; offset: number; corroborated: boolean } | undefined;
  private previousMediaTime: number | undefined;
  private framePeriod = Infinity;
  private lastMatch: { index: number; pts: number } | undefined;

  resetTimeline() {
    this.anchor = undefined;
    this.lastMatch = undefined;
    this.previousMediaTime = undefined;
    this.framePeriod = Infinity;
  }

  invalidate() {
    this.eligible.clear();
  }

  get hasObservations() {
    return this.eligible.size > 0;
  }

  retains(item: LiveObservation) {
    const current = this.eligible.get(JSON.stringify([item.epoch, item.index]));
    return current?.receivedMs === item.receivedMs && current.epoch === this.latest?.epoch;
  }

  update(batch: LiveObservations, now: number) {
    if (this.run !== batch.run_id) {
      this.run = batch.run_id;
      this.latest = undefined;
      this.fingerprints.clear();
      this.resetTimeline();
    }
    this.invalidate();
    for (const [key, sample] of this.fingerprints) {
      if (sample.receivedMs + ambiguityWindowMs <= now)
        this.fingerprints.delete(key);
    }
    for (const item of batch.items) {
      const key = JSON.stringify([item.epoch, item.index]);
      const previous = this.fingerprints.get(key);
      if (previous) {
        if (
          previous.receivedMs !== item.receivedMs ||
          previous.pts_s !== item.pts_s ||
          previous.fingerprint.some(
            (sample, i) => sample !== item.fingerprint[i],
          )
        ) {
          this.invalidate();
          return;
        }
      } else {
        if (item.receivedMs + ambiguityWindowMs > now) {
          const fingerprint = Uint8Array.from(item.fingerprint);
          this.fingerprints.set(key, {
            fingerprint,
            receivedMs: item.receivedMs,
            pts_s: item.pts_s,
            epoch: item.epoch,
          });
        }
      }
      if (!observationLifetime(item, now)) continue;
      this.eligible.set(key, item);
      if (!this.latest || this.isNewer(item, this.latest)) {
        if (this.latest?.epoch !== item.epoch) this.resetTimeline();
        this.latest = item;
      }
    }
    if (this.fingerprints.size > maxHistory) {
      const oldest = [...this.fingerprints].sort(
        ([, a], [, b]) => a.receivedMs - b.receivedMs,
      );
      for (const [key] of oldest.slice(
        0,
        this.fingerprints.size - maxHistory,
      )) {
        this.fingerprints.delete(key);
        this.eligible.delete(key);
      }
    }
  }

  private isNewer(item: LiveObservation, previous: LiveObservation) {
    if (typeof item.epoch === "number" && typeof previous.epoch === "number") {
      return (
        item.epoch > previous.epoch ||
        (item.epoch === previous.epoch && item.index > previous.index)
      );
    }
    if (item.epoch === previous.epoch) return item.index > previous.index;
    return item.receivedMs > previous.receivedMs;
  }

  interpolationBounds(frame: number[], mediaTime: number, now: number) {
    const anchor = this.anchor;
    if (!anchor?.corroborated || !this.latest || !this.lastMatch ||
        this.previousMediaTime !== mediaTime ||
        mediaTime - anchor.mediaTime > continuityWindowSeconds || this.framePeriod > 0.045) return;

    const pts = mediaTime - anchor.offset;
    const tolerance = Math.min(0.009, this.framePeriod * 0.25);
    let before: LiveObservation | undefined;
    let after: LiveObservation | undefined;
    for (const item of this.eligible.values()) {
      if (item.epoch !== this.latest.epoch || item.pts_s === null || !observationLifetime(item, now)) continue;
      if (Math.abs(item.pts_s - pts) <= tolerance) return;
      if (Math.abs(pts - item.pts_s - this.framePeriod) <= tolerance) {
        if (before) return;
        before = item;
      } else if (Math.abs(item.pts_s - pts - this.framePeriod) <= tolerance) {
        if (after) return;
        after = item;
      }
    }
    if (!before || !after || before.pts_s === null || after.pts_s === null ||
        this.lastMatch.index !== before.index || after.index !== before.index + 1 ||
        after.receivedMs < before.receivedMs || now - before.receivedMs > interpolationAgeMs) return;

    for (const sample of this.fingerprints.values()) {
      if (sample.epoch !== before.epoch && distance(frame, sample.fingerprint) !== Infinity) return;
    }
    const fraction = (pts - before.pts_s) / (after.pts_s - before.pts_s);
    const expected = before.fingerprint.map((value, i) => value + fraction * (after.fingerprint[i] - value));
    if (distance(frame, expected) > 2.5) return;
    return { before, after, fraction };
  }

  match(frame: number[], mediaTime: number, now: number) {
    if (!Number.isFinite(mediaTime)) return;
    const step =
      this.previousMediaTime === undefined
        ? 0
        : mediaTime - this.previousMediaTime;
    if (step < 0 || step > maxFrameGapSeconds) this.resetTimeline();
    else if (step > 0) this.framePeriod = Math.min(this.framePeriod, step);
    if (step === 0 && this.previousMediaTime !== undefined) return;
    this.previousMediaTime = mediaTime;
    if (
      !this.latest ||
      !this.eligible.size ||
      Math.max(...frame) - Math.min(...frame) < 24
    )
      return;

    // Tighter than half a presented frame, including when frame notifications skip.
    const tolerance = Number.isFinite(this.framePeriod)
      ? Math.min(0.012, this.framePeriod * 0.35)
      : 0;
    const anchor = this.anchor;
    const predictedPts = anchor ? mediaTime - anchor.offset : undefined;
    const candidates = [];
    for (const [key, item] of this.eligible) {
      if (
        item.epoch !== this.latest.epoch ||
        item.pts_s === null ||
        !observationLifetime(item, now) ||
        distance(frame, item.fingerprint) > 2
      )
        continue;
      candidates.push({ key, item, pts: item.pts_s });
    }
    if (!candidates.length) return;

    const evidence = [];
    for (const [key, sample] of this.fingerprints) {
      if (distance(frame, sample.fingerprint) === Infinity) continue;
      if (sample.epoch !== this.latest.epoch) return;
      evidence.push({ key, pts: sample.pts_s });
    }

    const unique = evidence.length === 1 && candidates.length === 1;
    const aligned = (pts: number) =>
      predictedPts !== undefined &&
      tolerance > 0 &&
      Math.abs(pts - predictedPts) <= tolerance;
    let candidate;
    if (unique) {
      candidate = candidates[0];
    } else {
      if (
        !anchor?.corroborated ||
        mediaTime - anchor.mediaTime > continuityWindowSeconds
      )
        return;
      const timed = evidence.filter(({ pts }) => pts === null || aligned(pts));
      if (timed.length !== 1) return;
      candidate = candidates.find(({ key }) => key === timed[0].key);
      if (!candidate || !aligned(candidate.pts)) return;
    }

    const { item, pts } = candidate;
    const last = this.lastMatch;
    if (last && (item.index <= last.index || pts <= last.pts)) return;
    if (unique) {
      if (anchor && mediaTime - anchor.mediaTime <= maxAnchorGapSeconds) {
        if (!aligned(pts)) {
          this.resetTimeline();
          return;
        }
        // Refresh the window while keeping the original offset fixed so that
        // small errors cannot accumulate across a sequence of unique matches.
        this.anchor = { mediaTime, offset: anchor.offset, corroborated: true };
      } else {
        this.anchor = {
          mediaTime,
          offset: mediaTime - pts,
          corroborated: false,
        };
      }
    }
    this.lastMatch = { index: item.index, pts };
    return {
      observation: item,
      method: unique ? ("image" as const) : ("continuity" as const),
    };
  }
}
