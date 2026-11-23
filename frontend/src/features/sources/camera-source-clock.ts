import type { LiveObservation, LiveObservations } from "./camera-frame-match";

const clockUuid = "2dcd53fa-e376-4a1b-81c9-90511ff6dc2f";
const clockPayload = /^ox1:([a-f0-9]{32}):(0|[1-9][0-9]{0,8})$/;
const maxOffsetMs = 2;
const maxMarks = 600;

type Mark = { stream: string; ordinal: number; pts: number };

/** hls.js emits SEI PTS in the MSE timeline after applying the fragment offset. */
export class CameraSourceClock {
  private marks = new Map<number, Mark | null>();

  clear() {
    this.marks.clear();
  }

  ingest(samples: readonly { pts: number; uuid?: string; userData?: string }[]) {
    for (const { pts, uuid, userData } of samples) {
      if (uuid !== clockUuid || !userData || !Number.isFinite(pts) || pts < 0) continue;
      const match = clockPayload.exec(userData);
      if (!match) continue;
      const tick = Math.round(pts * 1000);
      const mark = { stream: match[1], ordinal: Number(match[2]), pts };
      const previous = this.marks.get(tick);
      if (previous === undefined) this.marks.set(tick, mark);
      else if (!previous || previous.stream !== mark.stream || previous.ordinal !== mark.ordinal) {
        this.marks.set(tick, null);
      }
    }
    if (this.marks.size > maxMarks) {
      const ticks = [...this.marks.keys()].sort((a, b) => a - b);
      for (const tick of ticks.slice(0, ticks.length - maxMarks)) this.marks.delete(tick);
    }
  }

  at(mediaTime: number, stream: string) {
    if (!Number.isFinite(mediaTime)) return;
    const ms = mediaTime * 1000;
    const tick = Math.round(ms);
    let result: Mark | undefined;
    for (let i = tick - maxOffsetMs; i <= tick + maxOffsetMs; i++) {
      const mark = this.marks.get(i);
      if (mark === null) return;
      if (!mark || Math.abs(mark.pts * 1000 - ms) > maxOffsetMs) continue;
      if (mark.stream !== stream || result) return;
      result = mark;
    }
    return result && { ordinal: result.ordinal, errorMs: Math.abs((result.pts - mediaTime) * 1000) };
  }
}

export class ClockedObservations {
  private observations = new Map<number, LiveObservation | null>();
  stream: string | undefined;

  update(batch: LiveObservations | null) {
    this.observations.clear();
    this.stream = batch?.stream_id;
    if (!this.stream || !batch?.items.length) return;
    for (const item of batch.items) {
      if (item.source_ordinal === undefined) continue;
      const ordinal = item.source_ordinal;
      this.observations.set(ordinal, this.observations.has(ordinal) ? null : item);
    }
  }

  observed(ordinal: number) {
    return this.observations.get(ordinal);
  }

  bracket(ordinal: number) {
    if (this.observations.has(ordinal)) return;
    const before = this.observed(ordinal - 1);
    const after = this.observed(ordinal + 1);
    if (!before || !after || before.epoch !== after.epoch || after.index !== before.index + 1) return;
    return { before, after };
  }
}
