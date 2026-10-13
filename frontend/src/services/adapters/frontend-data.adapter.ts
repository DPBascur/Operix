import type {
  AnalysisOverview,
  DashboardSummary,
  EventCandidate,
  OperationalRule,
  Zone,
} from "@/types/operix";

export interface FrontendDataAdapter {
  getAnalysisOverview(): Promise<AnalysisOverview>;
  getDashboardSummary(): Promise<DashboardSummary>;
  listEventCandidates(): Promise<EventCandidate[]>;
  listOperationalRules(): Promise<OperationalRule[]>;
  listZones(): Promise<Zone[]>;
}
