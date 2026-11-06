import { dataClient } from "./data-client";
import { ApiAdapter } from "./adapters/api.adapter";
import type { EventQuery } from "./adapters/frontend-data.adapter";

const history = new ApiAdapter();

export const eventsService = {
  list: () => dataClient.listEventCandidates(),
  listRows: (filters?: EventQuery) => history.listEvents(filters),
};
