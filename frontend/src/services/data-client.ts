import type { FrontendDataAdapter } from "./adapters/frontend-data.adapter";
import { MockAdapter } from "./adapters/mock.adapter";

// Punto único de sustitución futura por un ApiAdapter basado en Django REST API.
export const dataClient: FrontendDataAdapter = new MockAdapter();
