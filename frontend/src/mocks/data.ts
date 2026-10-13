import type {
  AnalysisOverview,
  Detection,
  EventCandidate,
  OperationalRule,
  Track,
  Zone,
} from "@/types/operix";

export const mockDetections: Detection[] = [
  {
    id: "mock-detection-1",
    frameIndex: 120,
    timestamp: "2026-01-01T12:00:04.000Z",
    label: "person",
    confidence: 0.94,
    boundingBox: [120, 80, 90, 180],
  },
];

export const mockTracks: Track[] = [
  {
    id: "mock-track-1",
    label: "person",
    detectionIds: ["mock-detection-1"],
    startFrame: 100,
    endFrame: 180,
  },
];

export const mockZones: Zone[] = [
  {
    id: "mock-zone-1",
    name: "Zona de prueba",
    points: [
      { x: 0.1, y: 0.1 },
      { x: 0.9, y: 0.1 },
      { x: 0.9, y: 0.9 },
      { x: 0.1, y: 0.9 },
    ],
    isActive: true,
  },
];

export const mockRules: OperationalRule[] = [
  {
    id: "mock-rule-1",
    name: "Regla de prueba",
    description: "Regla mock para construir la interfaz futura.",
    eventType: "zone-entry",
    zoneIds: ["mock-zone-1"],
    isEnabled: true,
  },
];

export const mockEventCandidates: EventCandidate[] = [
  {
    id: "mock-event-1",
    ruleId: "mock-rule-1",
    timestamp: "2026-01-01T12:00:04.000Z",
    frameIndex: 120,
    objectIds: ["mock-track-1"],
    zoneId: "mock-zone-1",
    metadata: { source: "frontend-mock" },
    confidence: 0.88,
  },
];

export const mockAnalysisOverview: AnalysisOverview = {
  id: "mock-analysis-1",
  sourceName: "video-de-prueba.mp4",
  status: "completed",
  progress: 100,
  detections: mockDetections,
  tracks: mockTracks,
};
