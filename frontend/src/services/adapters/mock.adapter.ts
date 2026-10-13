import {
  mockAnalysisOverview,
  mockEventCandidates,
  mockRules,
  mockZones,
} from "@/mocks/data";
import { mockEventRows } from "@/mocks/ui-data";
import type {
  AnalysisOverview,
  DashboardSummary,
  EventCandidate,
  EventListItem,
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

  async listEvents(): Promise<EventListItem[]> {
    return mockEventRows.map((event) => ({
      ...event,
      objects: "No informados",
    }));
  }

  async listOperationalRules(): Promise<OperationalRule[]> {
    return mockRules;
  }

  async listZones(): Promise<Zone[]> {
    return mockZones;
  }
}
