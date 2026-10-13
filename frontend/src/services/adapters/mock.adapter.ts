import {
  mockAnalysisOverview,
  mockEventCandidates,
  mockRules,
  mockZones,
} from "@/mocks/data";
import type {
  AnalysisOverview,
  DashboardSummary,
  EventCandidate,
  OperationalRule,
  Zone,
} from "@/types/operix";

import type { FrontendDataAdapter } from "./frontend-data.adapter";

export class MockAdapter implements FrontendDataAdapter {
  async getAnalysisOverview(): Promise<AnalysisOverview> {
    return mockAnalysisOverview;
  }

  async getDashboardSummary(): Promise<DashboardSummary> {
    return {
      analyses: 1,
      eventCandidates: mockEventCandidates.length,
      enabledRules: mockRules.filter((rule) => rule.isEnabled).length,
      zones: mockZones.length,
    };
  }

  async listEventCandidates(): Promise<EventCandidate[]> {
    return mockEventCandidates;
  }

  async listOperationalRules(): Promise<OperationalRule[]> {
    return mockRules;
  }

  async listZones(): Promise<Zone[]> {
    return mockZones;
  }
}
