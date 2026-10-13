import type {
  AnalysisOverview,
  DashboardSummary,
  EventCandidate,
  EventListItem,
  OperationalRule,
  Zone,
} from "@/types/operix";

export interface FrontendDataAdapter {
  getAnalysisOverview(): Promise<AnalysisOverview>;
  getDashboardSummary(): Promise<DashboardSummary>;
  listEventCandidates(): Promise<EventCandidate[]>;
  listEvents(): Promise<EventListItem[]>;
  listOperationalRules(): Promise<OperationalRule[]>;
  listZones(): Promise<Zone[]>;
}
