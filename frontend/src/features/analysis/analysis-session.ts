import type { AnalysisSessionStatus } from "@/services/analysis.service";

/** Solo una referencia por pestaña; el estado y la retención pertenecen al servidor. */
export function tabStorage(
  host: { readonly sessionStorage: Storage } | undefined = typeof window ===
  "undefined"
    ? undefined
    : window,
): Storage | null {
  try {
    return host?.sessionStorage ?? null;
  } catch {
    return null;
  }
}

export function sessionReferenceKey(apiBase: string | undefined): string {
  return `operix-analysis-session:${apiBase?.replace(/\/$/, "") ?? "unconfigured"}`;
}

export function readSessionReference(
  storage: Pick<Storage, "getItem"> | null,
  key: string,
): string | null {
  try {
    const id = storage?.getItem(key);
    return id && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(id)
      ? id
      : null;
  } catch {
    return null;
  }
}

export function writeSessionReference(
  storage: Pick<Storage, "setItem" | "removeItem"> | null,
  key: string,
  id: string | null,
): void {
  try {
    if (id) storage?.setItem(key, id);
    else storage?.removeItem(key);
  } catch {
    // El almacenamiento bloqueado no impide analizar; no se crea otro almacén.
  }
}

export function analysisPercent(
  state: string,
  percent: number | null,
): number | null {
  if (percent === null || !Number.isFinite(percent)) return null;
  return Math.max(0, Math.min(state === "completed" ? 100 : 99.9, percent));
}

export function sessionVideoInfo(session: AnalysisSessionStatus) {
  const info = session.result;
  const fps = info?.source_fps ?? session.source_fps ?? 0;
  return {
    width: info?.width ?? session.width ?? 1920,
    height: info?.height ?? session.height ?? 1080,
    duration: fps > 0 ? (info?.frames ?? session.total ?? 0) / fps : 0,
  };
}
