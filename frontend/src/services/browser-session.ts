export type OperixUser = {
  username: string;
  role: "administrator" | "safety_lead" | "operator";
};

export const roleLabels = {
  administrator: "Administrador",
  safety_lead: "Responsable de seguridad",
  operator: "Usuario",
};

type Session = { user: OperixUser | null; csrf_token: string; detail?: string };
let csrfToken: string | undefined;
let csrfRevision = 0;
let sessionRequest: Promise<OperixUser | null> | undefined;
export const sessionExpired = "operix:session-expired";

async function auth(action: string, credentials?: Record<string, string>) {
  const headers = new Headers();
  const mutates = action !== "session";
  if (mutates && !csrfToken) await getSession();
  const revision = mutates ? ++csrfRevision : csrfRevision;
  if (mutates && csrfToken) headers.set("X-CSRFToken", csrfToken);
  if (credentials) headers.set("Content-Type", "application/json");
  const response = await fetch(`/api/v1/auth/${action}/`, {
    method: mutates ? "POST" : "GET",
    headers,
    cache: "no-store",
    signal: AbortSignal.timeout(10000),
    body: credentials ? JSON.stringify(credentials) : undefined,
  });
  const result = (await response.json().catch(() => null)) as Session | null;
  if (!response.ok || !result?.csrf_token) {
    if (response.status === 403 && revision === csrfRevision)
      csrfToken = undefined;
    throw new Error(
      result?.detail ?? "No se pudo verificar la sesión. Vuelva a intentar.",
    );
  }
  if (revision === csrfRevision) csrfToken = result.csrf_token;
  return result.user;
}

export function getSession() {
  sessionRequest ??= auth("session").finally(() => {
    sessionRequest = undefined;
  });
  return sessionRequest;
}
export const signIn = (username: string, password: string) =>
  auth("login", { username, password });
export const signOut = () => auth("logout");
export const changePassword = (
  old: string,
  next: string,
  confirmation: string,
) =>
  auth("password", {
    old_password: old,
    new_password1: next,
    new_password2: confirmation,
  });

export async function apiFetch(url: string, init?: RequestInit) {
  const method = init?.method?.toUpperCase() ?? "GET";
  const headers = new Headers(init?.headers);
  if (!["GET", "HEAD", "OPTIONS"].includes(method)) {
    if (!csrfToken) await getSession();
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }
  const revision = csrfRevision;
  const response = await fetch(url, { ...init, headers });
  if (response.status === 401 && revision === csrfRevision)
    window.dispatchEvent(new Event(sessionExpired));
  return response;
}
