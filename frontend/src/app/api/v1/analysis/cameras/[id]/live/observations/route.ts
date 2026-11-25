import { get as httpGet, type IncomingMessage } from "node:http";
import { get as httpsGet } from "node:https";

const MAX_BYTES = 512 * 1024;
const UPSTREAM_BUDGET_MS = 2500;
const TRANSIENT_CODES = new Set(["ECONNRESET", "EPIPE"]);
const PRIVATE_HEADERS = {
  "Cache-Control": "private, no-store",
  "Cross-Origin-Resource-Policy": "same-origin",
  "X-Content-Type-Options": "nosniff",
};

function getObservations(url: URL, cookie: string, signal: AbortSignal) {
  return new Promise<IncomingMessage>((resolve, reject) => {
    const get = url.protocol === "https:" ? httpsGet : httpGet;
    get(url, { agent: false, signal, headers: { cookie } }, resolve).once(
      "error",
      reject,
    );
  });
}

function transportError(status: number) {
  return Response.json(
    {
      detail: "El servicio de observaciones no está disponible temporalmente.",
    },
    { status, headers: PRIVATE_HEADERS },
  );
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ id: string }> },
) {
  const target = process.env.OPERIX_API_PROXY_TARGET;
  if (!target) return new Response(null, { status: 404 });
  const { id } = await params;
  if (!/^[a-zA-Z0-9_-]+$/.test(id)) return new Response(null, { status: 404 });
  const url = new URL(
    "/api/v1/analysis/cameras/" +
      encodeURIComponent(id) +
      "/live/observations/",
    target,
  );
  url.search = new URL(request.url).search;
  const deadline = AbortSignal.timeout(UPSTREAM_BUDGET_MS);
  const signal = AbortSignal.any([request.signal, deadline]);

  let upstream: IncomingMessage;
  const cookie = request.headers.get("cookie") ?? "";
  try {
    try {
      upstream = await getObservations(url, cookie, signal);
    } catch (error) {
      if (
        signal.aborted ||
        !TRANSIENT_CODES.has((error as NodeJS.ErrnoException).code ?? "")
      ) {
        throw error;
      }
      upstream = await getObservations(url, cookie, signal);
    }

    const status = upstream.statusCode ?? 502;
    const headers = new Headers(PRIVATE_HEADERS);
    for (const name of ["content-type", "www-authenticate", "retry-after"]) {
      const value = upstream.headers[name];
      if (typeof value === "string") headers.set(name, value);
    }
    if (status === 204 || status === 304) {
      upstream.resume();
      return new Response(null, { status, headers });
    }

    // The Django endpoint bounds packets. Buffer within the same limit so a
    // broken upstream body never reaches the player as a partial packet.
    const chunks: Buffer[] = [];
    let bytes = 0;
    for await (const chunk of upstream) {
      bytes += chunk.length;
      if (bytes > MAX_BYTES) return transportError(502);
      chunks.push(chunk);
    }
    return new Response(new Uint8Array(Buffer.concat(chunks)), {
      status,
      headers,
    });
  } catch {
    return transportError(deadline.aborted ? 504 : 502);
  }
}
