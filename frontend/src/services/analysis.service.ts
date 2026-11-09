import { apiFetch } from "@/services/browser-session";
import { dataClient } from "./data-client";
import { environment } from "@/config/environment";

export type AnalysisState =
  "ready" | "preparing" | "processing" | "completed" | "error" | "cancelled";

export type NormalizedVertex = [number, number];
export type AnalysisProfile = "A" | "B" | "C";
export type AnalysisSourceKind = "demo" | "manual";

export interface DemoVideoSource {
  id: string;
  filename: string;
  bytes: number;
}

export interface AnalysisProfileDefinition {
  id: AnalysisProfile;
  display_name: string;
  default_demo_video: DemoVideoSource | null;
  configuration?: AnalysisRuleSnapshot | null;
}

export interface MotionSettings {
  unit: "normalized" | "m";
  window_seconds: number;
  min_observations: number;
  max_gap_seconds: number;
  stationary_speed: number;
  moving_speed: number;
  max_position_residual: number;
  camera_fixed_confirmed: boolean;
}
export interface RelationSettings {
  max_pairs: number;
  policy: "active" | "near_threshold" | "all";
  near_margin: number;
}
export interface EquipmentMotion {
  class_name: "forklift";
  track_id: number;
  state: "MOVING" | "STATIONARY" | "UNKNOWN";
  speed: number | null;
  unit: "m_per_s" | "normalized_image_per_s";
  frame_index: number;
  epoch: number;
  reason: string | null;
}
export interface AnalysisRuleSnapshot {
  motion?: MotionSettings | null;
  relations?: RelationSettings | null;
  calibration?: {
    status: string;
    version: number;
    sha256: string;
    method: string;
  } | null;
  config_sha256: string;
  rules: {
    rule_id: string;
    version: number;
    enabled: boolean;
    parameters: Record<string, unknown>;
  }[];
}

export interface AnalysisResultConfig {
  motion?: MotionSettings | null;
  relations?: RelationSettings | null;
  profile: AnalysisProfile;
  zone: { zone_id: string; name: string; polygon: NormalizedVertex[] };
  source_video: string;
  source_sha256: string;
  source_fps: number;
  frames: number;
  width: number;
  height: number;
  video: {
    codec: string;
    fps: number;
    frames: number;
    width: number;
    height: number;
  };
  person: { imgsz: number; confidence: number; nms_iou: number };
  forklift: { imgsz: number; confidence: number; nms_iou: number };
  run: number;
  rules?: AnalysisRuleSnapshot["rules"];
  config_sha256?: string;
}

export interface AnalysisSessionStatus {
  id: string;
  state: AnalysisState;
  filename: string;
  profile: AnalysisProfile;
  source_sha256: string;
  source_bytes: number;
  source_kind: AnalysisSourceKind;
  demo_source_id: string | null;
  spatial_revision?: number;
  zone: { zone_id: string; name: string; polygon: NormalizedVertex[] };
  run: number;
  result: AnalysisResultConfig | null;
  configuration?: (AnalysisRuleSnapshot & { profile: AnalysisProfile }) | null;
  active_configuration?: Pick<
    AnalysisResultConfig,
    "profile" | "run" | "rules" | "config_sha256"
  > | null;
  pending_changes: boolean;
  frame: number;
  total: number | null;
  percent: number | null;
  fps: number | null;
  width?: number;
  height?: number;
  source_fps?: number;
  result_video?: AnalysisResultConfig["video"];
  timing_ms?: Record<string, number>;
  equipment_motion?: EquipmentMotion[];
  preview?: {
    pending: boolean;
    frame_index: number | null;
    source_timestamp: number | null;
    playback_rate: number;
  };
  person_detections: number;
  forklift_detections: number;
  person_tracks: number;
  forklift_tracks: number;
  detail?: string;
  analysis_run_id?: string | null;
  persistence?: {
    state: "pending" | "saved" | "failed" | "disabled";
    candidates?: number;
    saved?: number;
    failed?: number;
    event_ids?: string[];
    detail?: string;
  };
}

function apiBaseUrl(): string {
  if (!environment.apiBaseUrl) {
    throw new Error(
      "Configure NEXT_PUBLIC_API_BASE_URL para habilitar el análisis real.",
    );
  }
  return environment.apiBaseUrl.replace(/\/$/, "");
}

function sessionUrl(id = ""): string {
  return `${apiBaseUrl()}/analysis/sessions/${id ? `${id}/` : ""}`;
}

export class AnalysisRequestError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await apiFetch(url, {
    cache: "no-store",
    signal: AbortSignal.timeout(120_000),
    ...init,
  });
  const data: unknown = await response.json().catch(() => {
    throw new AnalysisRequestError(
      "El servicio de análisis devolvió una respuesta inválida. Vuelva a intentar.",
      response.status,
    );
  });
  if (!response.ok) {
    const detail =
      typeof data === "object" && data !== null && "detail" in data
        ? String(data.detail)
        : `La API respondió ${response.status}.`;
    throw new AnalysisRequestError(detail, response.status);
  }
  return data as T;
}

export const analysisService = {
  getOverview: () => dataClient.getAnalysisOverview(),
  getDashboardSummary: () => dataClient.getDashboardSummary(),
  createSession(video: File, profile: AnalysisProfile) {
    const body = new FormData();
    body.append("video", video);
    body.append("profile", profile);
    return request<AnalysisSessionStatus>(sessionUrl(), {
      method: "POST",
      body,
    });
  },
  getProfiles() {
    return request<AnalysisProfileDefinition[]>(
      `${apiBaseUrl()}/analysis/profiles/`,
    );
  },
  createDemoSession(profile: AnalysisProfile, demoSourceId: string) {
    return request<AnalysisSessionStatus>(sessionUrl(), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ profile, demo_source_id: demoSourceId }),
    });
  },
  getAnalysisStatus(id: string) {
    return request<AnalysisSessionStatus>(`${sessionUrl(id)}status/`);
  },
  startAnalysisSession(id: string) {
    return request<AnalysisSessionStatus>(`${sessionUrl(id)}start/`, {
      method: "POST",
    });
  },
  stopAnalysisSession(id: string) {
    return request<AnalysisSessionStatus>(`${sessionUrl(id)}stop/`, {
      method: "POST",
    });
  },
  retryEventPersistence(id: string) {
    return request<AnalysisSessionStatus>(
      `${sessionUrl(id)}persistence/retry/`,
      { method: "POST" },
    );
  },
  async closeAnalysisSession(id: string) {
    const response = await apiFetch(sessionUrl(id), {
      method: "DELETE",
      keepalive: true,
      signal: AbortSignal.timeout(10_000),
    });
    if (!response.ok && response.status !== 404) {
      throw new Error(`No se pudo cerrar la sesión (${response.status}).`);
    }
  },
  updateZone(
    id: string,
    values: { polygon?: NormalizedVertex[]; profile?: AnalysisProfile },
  ) {
    return request<AnalysisSessionStatus>(`${sessionUrl(id)}zone/`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
  },
  getAnalysisStreamUrl(id: string) {
    return `${sessionUrl(id)}stream/`;
  },
  getAnalysisSourceUrl(id: string) {
    return `${sessionUrl(id)}source/`;
  },
  getDemoSourceUrl(profile: AnalysisProfile, demoSourceId: string) {
    return `${apiBaseUrl()}/analysis/profiles/${profile}/demo/${encodeURIComponent(demoSourceId)}/`;
  },
  getAnalysisResultUrl(id: string, run: number) {
    return `${sessionUrl(id)}result/?run=${run}`;
  },
};
