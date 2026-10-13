export const environment = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL,
  dataSource: process.env.NEXT_PUBLIC_DATA_SOURCE === "api" ? "api" : "mock",
} as const;
