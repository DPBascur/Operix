import type { FrontendDataAdapter } from "./adapters/frontend-data.adapter";
import { ApiAdapter } from "./adapters/api.adapter";
import { MockAdapter } from "./adapters/mock.adapter";
import { environment } from "@/config/environment";

export const dataClient: FrontendDataAdapter =
  environment.dataSource === "api" ? new ApiAdapter() : new MockAdapter();
