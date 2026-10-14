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

import type { EventQuery, FrontendDataAdapter } from "./frontend-data.adapter";

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

  async listEvents(filters: EventQuery = {}): Promise<EventListItem[]> {
    return mockEventRows
      .filter((event) => {
        const occurredAt = new Date(event.occurredAt).getTime();
        return (
          (!filters.eventType || event.eventType === filters.eventType) &&
          (!filters.occurredAfter ||
            occurredAt >= Date.parse(filters.occurredAfter)) &&
          (!filters.occurredBefore ||
            occurredAt <= Date.parse(filters.occurredBefore))
        );
      })
      .map((event) => ({
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
