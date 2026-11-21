import type { NormalizedVertex as Point } from "../../services/analysis.service";

export const dictionary = "DICT_4X4_50";
export const minMarkers = 3;
export const maxMarkers = 8;

export function calibrationFrame(value: unknown): string | null {
  const prefix = "data:image/jpeg;base64,";
  if (typeof value !== "string" || !value.startsWith(prefix)) return null;
  const data = value.slice(prefix.length);
  return data.startsWith("/9j/") &&
    data.length <= 720_000 &&
    data.length % 4 === 0 &&
    /^[A-Za-z0-9+/]+={0,2}$/.test(data)
    ? value
    : null;
}

export type MarkerDraft = {
  id: string;
  x_m: string;
  y_m: string;
  size_m: string;
  rotation_deg: string;
};

function readNumber(value: string) {
  const normalized = value.trim().replace(",", ".");
  return /^[-+]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(normalized)
    ? Number(normalized)
    : NaN;
}

export function readLayout(drafts: MarkerDraft[], provenance: string) {
  const markers = drafts.map((draft) => ({
    id: readNumber(draft.id),
    x_m: readNumber(draft.x_m),
    y_m: readNumber(draft.y_m),
    size_m: readNumber(draft.size_m),
    rotation_deg: readNumber(draft.rotation_deg),
  }));
  if (
    markers.length < minMarkers ||
    markers.length > maxMarkers ||
    !provenance.trim() ||
    provenance.trim().length > 250 ||
    new Set(markers.map(({ id }) => id)).size !== markers.length ||
    markers.some(
      ({ id, x_m, y_m, size_m, rotation_deg }) =>
        !Number.isInteger(id) ||
        id < 0 ||
        id >= 50 ||
        !(Math.abs(x_m) <= 10000 && Math.abs(y_m) <= 10000) ||
        !(size_m >= 0.01 && size_m <= 20) ||
        !(Math.abs(rotation_deg) <= 360),
    )
  )
    return null;
  return { dictionary, markers, provenance: provenance.trim() };
}

export function readControl(
  points: [Point, Point] | null,
  distance: string,
  tolerance: string,
  provenance: string,
) {
  const distance_m = readNumber(distance);
  const tolerance_m = readNumber(tolerance);
  if (
    !points ||
    points.some((point) =>
      point.some((value) => !(value >= 0 && value <= 1)),
    ) ||
    points[0].every((value, index) => value === points[1][index]) ||
    !(distance_m > 0 && distance_m <= 10000) ||
    !(
      Number.isFinite(tolerance_m) &&
      tolerance_m > 0 &&
      tolerance_m < distance_m
    ) ||
    !provenance.trim() ||
    provenance.trim().length > 250
  )
    return null;
  return {
    image_points: points,
    distance_m,
    tolerance_m,
    provenance: provenance.trim(),
  };
}
