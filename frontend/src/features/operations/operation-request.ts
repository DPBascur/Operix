import { environment } from "@/config/environment";
import { apiFetch } from "@/services/browser-session";

export async function operationalRequest<T>(
  path: string,
  method = "GET",
  body?: unknown,
) {
  const base = environment.apiBaseUrl?.replace(/\/$/, "");
  if (!base) throw new Error("La API de Operix no está disponible.");
  const response = await apiFetch(`${base}/analysis/${path}`, {
    method,
    cache: "no-store",
    signal: AbortSignal.timeout(12000),
    ...(body === undefined
      ? {}
      : {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        }),
  });
  const data = await response.json().catch(() => null);
  if (!response.ok || data === null) {
    const detail = Array.isArray(data)
      ? data.find((message) => typeof message === "string")
      : data?.detail;
    throw new Error(
      typeof detail === "string"
        ? detail
        : "No se pudo completar la consulta. Intenta de nuevo.",
    );
  }
  return data as T;
}

export function operationalError(error: unknown) {
  if (error instanceof DOMException && error.name === "TimeoutError")
    return "La consulta excedió el tiempo de espera. Intenta de nuevo.";
  if (error instanceof TypeError)
    return "No se pudo conectar con la API de Operix.";
  return error instanceof Error
    ? error.message
    : "No se pudo completar la operación.";
}
