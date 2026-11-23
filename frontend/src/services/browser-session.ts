export type OperixUser = {
  username: string;
  role: "administrator" | "safety_lead" | "viewer";
  role_review_required?: boolean;
};

export const roleLabels = {
  administrator: "Administrador",
  safety_lead: "Responsable de seguridad",
  viewer: "Visualizador",
};

type Session = {
  user?: OperixUser | null;
  csrf_token?: string;
  detail?: string;
};
let csrfToken: string | undefined;
let csrfRevision = 0;
let sessionRequest:
  { revision: number; promise: Promise<OperixUser | null> } | undefined;
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
  const account = result?.user;
  if (
    !response.ok ||
    typeof result?.csrf_token !== "string" ||
    !result.csrf_token ||
    (account !== null &&
      (typeof account?.username !== "string" ||
        !Object.hasOwn(roleLabels, account.role)))
  ) {
    if (response.status === 403 && revision === csrfRevision)
      csrfToken = undefined;
    throw new Error(
      typeof result?.detail === "string"
        ? result.detail
        : "No se pudo verificar la sesión. Vuelva a intentar.",
    );
  }
  if (revision === csrfRevision) {
    csrfToken = result.csrf_token;
    if (mutates) csrfRevision++;
  }
  return account;
}

export function getSession() {
  const revision = csrfRevision;
  if (sessionRequest?.revision === revision) return sessionRequest.promise;
  const promise = auth("session").finally(() => {
    if (sessionRequest?.promise === promise) sessionRequest = undefined;
  });
  sessionRequest = { revision, promise };
  return promise;
}

async function waitForSession(signal?: AbortSignal | null) {
  signal?.throwIfAborted();
  if (!signal) return getSession();

  // A caller can stop waiting without cancelling another caller's session check.
  return new Promise<OperixUser | null>((resolve, reject) => {
    const abort = () => reject(signal.reason);
    signal.addEventListener("abort", abort, { once: true });
    getSession()
      .finally(() => signal.removeEventListener("abort", abort))
      .then(resolve, reject);
  });
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
    if (!csrfToken) await waitForSession(init?.signal);
    if (csrfToken) headers.set("X-CSRFToken", csrfToken);
  }
  const revision = csrfRevision;
  init?.signal?.throwIfAborted();
  const response = await fetch(url, { ...init, headers });
  if (response.status !== 401) return response;

  init?.signal?.throwIfAborted();
  const account =
    revision === csrfRevision
      ? await waitForSession(init?.signal).catch(() => undefined)
      : undefined;
  init?.signal?.throwIfAborted();
  if (account === null && revision === csrfRevision) {
    csrfRevision++;
    window.dispatchEvent(new Event(sessionExpired));
    return response;
  }

  // Keep polling callers on their normal recovery path. Never replay a write.
  throw new Error(
    "No se pudo completar la consulta con Operix. Intenta de nuevo.",
  );
}
