import type { NormalizedVertex } from "@/services/analysis.service";

interface PointerSample {
  clientX: number;
  clientY: number;
  currentTarget: {
    getBoundingClientRect(): {
      left: number;
      top: number;
      width: number;
      height: number;
    };
  };
}

/** Capturar dentro del handler: React no conserva currentTarget para el updater. */
export function pointInFrame(event: PointerSample): NormalizedVertex | null {
  const bounds = event.currentTarget.getBoundingClientRect();
  if (!(bounds.width > 0 && bounds.height > 0)) return null;
  return [
    Math.max(0, Math.min(1, (event.clientX - bounds.left) / bounds.width)),
    Math.max(0, Math.min(1, (event.clientY - bounds.top) / bounds.height)),
  ];
}

/** Un polígono cerrado nunca pierde su mínimo geométrico. */
export function removeVertex(
  vertices: NormalizedVertex[],
  index: number | null,
): NormalizedVertex[] {
  if (
    index === null ||
    !Number.isInteger(index) ||
    index < 0 ||
    index >= vertices.length ||
    vertices.length <= 3
  )
    return vertices;
  return vertices.filter((_, current) => current !== index);
}

export function validPolygon(vertices: NormalizedVertex[]): boolean {
  if (
    vertices.length < 3 ||
    vertices.length > 32 ||
    vertices.some((p) => p.some((v) => !Number.isFinite(v) || v < 0 || v > 1))
  )
    return false;
  const cross = (
    a: NormalizedVertex,
    b: NormalizedVertex,
    c: NormalizedVertex,
  ) => (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]);
  const onSegment = (
    a: NormalizedVertex,
    b: NormalizedVertex,
    p: NormalizedVertex,
  ) =>
    Math.abs(cross(a, b, p)) < 1e-12 &&
    p.every((v, i) => v >= Math.min(a[i], b[i]) && v <= Math.max(a[i], b[i]));
  const area = vertices.reduce((sum, p, i) => {
    const q = vertices[(i + 1) % vertices.length];
    return sum + p[0] * q[1] - q[0] * p[1];
  }, 0);
  if (Math.abs(area) < 1e-8) return false;
  for (let i = 0; i < vertices.length; i++) {
    const a = vertices[i];
    const b = vertices[(i + 1) % vertices.length];
    if (Math.hypot(a[0] - b[0], a[1] - b[1]) < 1e-8) return false;
    for (let j = i + 1; j < vertices.length; j++) {
      if (j === i + 1 || (i === 0 && j === vertices.length - 1)) continue;
      const c = vertices[j];
      const d = vertices[(j + 1) % vertices.length];
      if (
        (cross(a, b, c) * cross(a, b, d) < 0 &&
          cross(c, d, a) * cross(c, d, b) < 0) ||
        onSegment(a, b, c) ||
        onSegment(a, b, d) ||
        onSegment(c, d, a) ||
        onSegment(c, d, b)
      )
        return false;
    }
  }
  return true;
}
