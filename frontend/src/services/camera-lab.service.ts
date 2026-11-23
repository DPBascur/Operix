import { environment } from "@/config/environment";
import { apiFetch } from "@/services/browser-session";
import type { PatternEvidence } from "./automatic-calibration.service";
import type {
  AnalysisRuleSnapshot,
  NormalizedVertex,
  MotionSettings,
  RelationSettings,
} from "./analysis.service";

export type CameraDocument = {
  schema_version: number;
  view_id: string;
  coordinate_system: string;
  calibration?: {
    status: string;
    version: number;
    zones_reviewed?: boolean;
    pattern_evidence?: PatternEvidence;
  } | null;
  motion?: MotionSettings;
  relations?: RelationSettings;
  zones: {
    zone_id: string;
    name: string;
    polygon: NormalizedVertex[];
    enabled?: boolean;
  }[];
  rules: AnalysisRuleSnapshot["rules"];
};

export type LabCamera = {
  id: string;
  name: string;
  automatic?: boolean;
  view_only?: boolean;
  playback?: { media_id?: string; position?: number } | null;
  description: string;
  provenance: {
    sha256?: string;
    title?: string;
    author?: string;
    license?: string;
    filename?: string;
    duration_s?: number;
    fps?: number;
    footage?: string;
    scenario?: string;
  } | null;
  expected_fps: number | null;
  configured_analysis_fps?: number | null;
  configured_source_fps?: number | null;
  width: number | null;
  height: number | null;
  status: string;
  metrics: (Record<string, unknown> & {
    equipment_rule_scope?: import("./analysis.service").EquipmentContext["rule_scope"];
  }) | null;
  preview_url: string | null;
  configuration: CameraDocument | null;
  effective_rules?: CameraDocument["rules"] | null;
  calibration_requires_reconfirmation?: boolean;
  policy?: { rule_set: { name: string; version: number } } | null;
  revision: number;
  run_id: string | null;
  last_frame_at?: string | null;
  last_error?: string | null;
  last_event?: { id: string; event_type: string; occurred_at: string } | null;
};

export type CameraCatalog = {
  enabled: boolean;
  managed?: boolean;
  cameras: LabCamera[];
  capacity: number;
  can_edit: boolean;
};

export type CameraControlEntry = Pick<
  LabCamera,
  | "id"
  | "name"
  | "status"
  | "metrics"
  | "preview_url"
  | "last_frame_at"
  | "provenance"
  | "view_only"
> & {
  enabled: boolean;
  run_id?: string | null;
  problem?: string | null;
  expected_fps?: number | null;
  playlist_finished?: boolean;
  last_transition?: { outcome?: string; reason?: string } | null;
};

export type CameraMedia = {
  id: string;
  filename: string;
  title?: string | null;
  scenario?: string | null;
  duration_s?: number | null;
  fps?: number | null;
};

export type CameraPlaylist = { media_ids: string[]; repeat: boolean };

export type CameraLabControl = {
  available: boolean;
  enabled: boolean;
  status:
    "disabled" | "starting" | "partial" | "active" | "stopping" | "finished";
  capacity: number;
  cameras: CameraControlEntry[];
  publisher: Record<string, "idle" | "starting" | "publishing" | "error">;
  mediamtx: "ready" | "unavailable";
  updated_by: string | null;
  catalog?: CameraMedia[];
  playlists?: Record<string, CameraPlaylist>;
};

export type CameraControlUpdate = {
  enabled?: boolean;
  cameras?: Record<string, boolean>;
  playlists?: Record<string, CameraPlaylist>;
};

const base = (environment.apiBaseUrl ?? "/api/v1").replace(/\/$/, "");
const collection = `${base}/analysis/cameras/`;
const controlPath = `${collection}control/`;
const cameraPath = (id: string) => `${collection}${encodeURIComponent(id)}/`;

export class CameraRequestError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function cameraRequest(
  url: string,
  init?: RequestInit,
): Promise<Response> {
  const response = await apiFetch(url, {
    cache: "no-store",
    signal: AbortSignal.timeout(12_000),
    ...init,
  });
  if (response.ok) return response;
  // The API may include connection details in diagnostic errors.
  const messages: Record<number, string> = {
    401: "Inicia sesión para consultar el laboratorio.",
    403: "Tu cuenta no tiene permiso para esta operación.",
    404: "El recurso solicitado no está disponible.",
    400: "El servidor rechazó la solicitud. Revisa la configuración de la cámara.",
    409: "La operación no está disponible en el estado actual de la cámara o del laboratorio.",
    422: "El servidor rechazó los cambios de configuración.",
    429: "El laboratorio alcanzó su capacidad. Espera antes de reintentar.",
  };
  throw new CameraRequestError(
    response.status,
    messages[response.status] ??
      "No se pudo completar la operación en el laboratorio.",
  );
}

async function readCameraData<T>(url: string, signal: AbortSignal): Promise<T> {
  const response = await cameraRequest(url, {
    signal: AbortSignal.any([signal, AbortSignal.timeout(12_000)]),
  });
  return cameraJson<T>(response);
}

async function cameraJson<T>(response: Response): Promise<T> {
  return response.json().catch(() => {
    throw new Error("El servicio devolvió una respuesta inválida.");
  });
}

export const cameraLabService = {
  observations: (id: string, signal: AbortSignal) =>
    cameraRequest(
      `/api/v1/analysis/cameras/${encodeURIComponent(id)}/live/observations/`,
      {
        credentials: "same-origin",
        redirect: "error",
        signal: AbortSignal.any([signal, AbortSignal.timeout(3000)]),
      },
    ).then((response) =>
      response.status === 204 ? null : cameraJson<unknown>(response),
    ),
  list: (signal: AbortSignal) =>
    readCameraData<CameraCatalog>(collection, signal),
  control: (signal: AbortSignal) =>
    readCameraData<CameraLabControl>(controlPath, signal),
  async updateControl(update: CameraControlUpdate) {
    await cameraRequest(controlPath, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(update),
    });
  },
  detail: (id: string, signal: AbortSignal) =>
    readCameraData<LabCamera>(cameraPath(id), signal),
  async monitor(id: string, action: "start" | "stop") {
    return cameraJson<LabCamera>(
      await cameraRequest(`${cameraPath(id)}${action}/`, { method: "POST" }),
    );
  },
  async save(id: string, revision: number, document: CameraDocument) {
    return cameraJson<LabCamera>(
      await cameraRequest(cameraPath(id), {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ revision, document }),
      }),
    );
  },
  async preview(id: string, path: string, signal: AbortSignal) {
    const root = new URL(cameraPath(id), window.location.origin);
    const url = new URL(path, root);
    if (
      url.origin !== root.origin ||
      !url.pathname.startsWith(root.pathname) ||
      url.username ||
      url.password
    ) {
      throw new Error("La dirección de la vista previa no es válida.");
    }
    const requestSignal = AbortSignal.any([
      signal,
      AbortSignal.timeout(12_000),
    ]);
    const response = await cameraRequest(url.href, {
      redirect: "error",
      signal: requestSignal,
    });
    const frame = await response.blob();
    requestSignal.throwIfAborted();
    if (frame.type !== "image/jpeg" || !frame.size)
      throw new Error("El servidor no devolvió un fotograma JPEG.");
    return frame;
  },
};
