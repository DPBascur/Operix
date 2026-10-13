import { dataClient } from "./data-client";

export const rulesService = {
  list: () => dataClient.listOperationalRules(),
  listZones: () => dataClient.listZones(),
};
