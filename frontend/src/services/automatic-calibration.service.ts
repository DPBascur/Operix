import { environment } from "@/config/environment";
import { apiFetch } from "@/services/browser-session";
import type { NormalizedVertex as Point } from "./analysis.service";
import type {
  readControl,
  readLayout,
} from "@/features/calibration/calibration-input";

export type CalibrationSource = {
  kind: "cameras" | "sessions";
  id: string;
  revision: number;
};

type PatternLayout = NonNullable<ReturnType<typeof readLayout>>;
type Control = NonNullable<ReturnType<typeof readControl>>;

export type PatternEvidence = {
  provenance: string;
  control: Control & {
    observed_m: number;
    absolute_error_m: number;
    relative_error: number;
  };
};

export type PatternProposal = {
  proposal_id: string | null;
  preview_url?: string | null;
  expires_at?: string;
  status: "candidate" | "requires_review" | "invalid";
  usable_polygon: Point[];
  grid: Point[][];
  references: { id: number; corners: Point[] }[];
  quality: {
    reprojection_error_px?: number | null;
    coverage_ratio?: number | null;
    temporal_error_px?: number | null;
    condition_number?: number | null;
    sensitivity_m?: number | null;
  };
  reasons?: string[];
};

const base = (environment.apiBaseUrl ?? "/api/v1").replace(/\/$/, "");
function calibrationUrl({ kind, id }: CalibrationSource) {
  return `${base}/analysis/${kind}/${encodeURIComponent(id)}/calibration/`;
}

const errors: Record<number, string> = {
  400: "Revisa los valores ingresados y la distribución de los marcadores.",
  401: "Inicia sesión para calibrar esta fuente.",
  403: "Tu cuenta no tiene permiso para calibrar esta fuente.",
  404: "La fuente o la propuesta ya no está disponible.",
  409: "Cambió el estado o la revisión de la fuente. Actualiza la configuración y captura una propuesta nueva.",
  410: "La propuesta caducó. Captura una nueva.",
  422: "La comprobación física no fue aceptada. Revisa los puntos, la medida y su tolerancia.",
  429: "Hay demasiadas solicitudes de calibración. Espera antes de reintentar.",
};

export class CalibrationRequestError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

async function post<T>(
  url: string,
  body: unknown,
  signal: AbortSignal,
): Promise<T> {
  const response = await apiFetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    cache: "no-store",
    signal: AbortSignal.any([signal, AbortSignal.timeout(90_000)]),
  });
  if (!response.ok) {
    const data =
      response.status === 400 ? await response.json().catch(() => null) : null;
    const detail = Array.isArray(data) ? data[0] : data?.detail;
    throw new CalibrationRequestError(
      response.status,
      (typeof detail === "string" && detail.slice(0, 400)) ||
        errors[response.status] ||
        "No se pudo completar la calibración. Vuelve a intentarlo.",
    );
  }
  return response.json();
}

export const automaticCalibrationService = {
  propose(
    source: CalibrationSource,
    layout: PatternLayout,
    signal: AbortSignal,
  ) {
    return post<PatternProposal>(
      `${calibrationUrl(source)}proposal/`,
      { revision: source.revision, layout },
      signal,
    );
  },
  confirm<T>(
    source: CalibrationSource,
    proposal_id: string,
    control: Control,
    signal: AbortSignal,
  ) {
    return post<T>(
      `${calibrationUrl(source)}confirm/`,
      {
        proposal_id,
        revision: source.revision,
        ground_confirmed: true,
        zones_reviewed: true,
        control,
      },
      signal,
    );
  },
};
