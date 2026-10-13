import { dataClient } from "./data-client";

export const analysisService = {
  getOverview: () => dataClient.getAnalysisOverview(),
  getDashboardSummary: () => dataClient.getDashboardSummary(),
};
