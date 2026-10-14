import { dataClient } from "./data-client";
import type { EventQuery } from "./adapters/frontend-data.adapter";

export const eventsService = {
  list: () => dataClient.listEventCandidates(),
  listRows: (filters?: EventQuery) => dataClient.listEvents(filters),
};
