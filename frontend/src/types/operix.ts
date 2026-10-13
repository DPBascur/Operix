export type AnalysisStatus =
  "idle" | "queued" | "processing" | "completed" | "failed";

export interface Point {
  x: number;
  y: number;
}

export interface Detection {
  id: string;
  frameIndex: number;
  timestamp: string;
  label: string;
  confidence: number;
  boundingBox: [x: number, y: number, width: number, height: number];
}

export interface Track {
  id: string;
  label: string;
  detectionIds: string[];
  startFrame: number;
  endFrame: number;
}

export interface Zone {
  id: string;
  name: string;
  points: Point[];
  isActive: boolean;
}

export interface OperationalRule {
  id: string;
  name: string;
  description: string;
  eventType: string;
  zoneIds: string[];
  isEnabled: boolean;
}

export interface EventCandidate {
  id: string;
  ruleId: string;
  timestamp: string;
  frameIndex: number;
  objectIds: string[];
  zoneId?: string;
  metadata: Record<string, unknown>;
  confidence?: number;
}

export interface EventListItem {
  id: string;
  title: string;
  zone: string;
  rule: string;
  objects: string;
  confidence: number | null;
  time: string;
  status: string;
  tone: "accent" | "cyan" | "neutral";
  evidenceUrl?: string | null;
}

export interface AnalysisOverview {
  id: string;
  sourceName: string;
  status: AnalysisStatus;
  progress: number;
  detections: Detection[];
  tracks: Track[];
}

export interface DashboardSummary {
  analyses: number;
  eventCandidates: number;
  enabledRules: number;
  zones: number;
}
