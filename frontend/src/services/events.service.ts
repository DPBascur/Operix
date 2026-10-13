import { dataClient } from "./data-client";

export const eventsService = {
  list: () => dataClient.listEventCandidates(),
};
