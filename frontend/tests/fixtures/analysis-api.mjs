// API descartable para regresión UI. No carga Motor, DB, pesos ni material externo.
import { createServer } from "node:http";
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

export const eventId = "00000000-0000-4000-8000-000000000099";
const polygon = [
  [0.1, 0.1],
  [0.9, 0.1],
  [0.9, 0.9],
  [0.1, 0.9],
];
export async function startFixtureApi(port = 8000) {
  const video = await readFile(
    new URL(
      "../../../assets/demo/warehouse_fire_ceiling04.mp4",
      import.meta.url,
    ),
  );
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jfuoAAAAASUVORK5CYII=",
    "base64",
  );
  let sessions = new Map(),
    sequence = 0,
    deleted = 0,
    failNext = false,
    delayNextStatus = false,
    waitingStatus = false;
  const event = {
    id: eventId,
    occurred_at: "2026-10-25T12:00:01Z",
    event_type: "person_forklift_proximity",
    rule_id: "TEST_DATA_PAIR",
    rule_version: 1,
    zone_id: "TEST_DATA_ZONE",
    class_name: "",
    track_id: null,
    interaction: {
      person: { class_name: "person", track_id: 1 },
      forklift: { class_name: "forklift", track_id: 1 },
    },
    frame_index: 30,
    video_time_seconds: 1,
    source: {
      filename: "TEST_DATA_demo.mp4",
      timestamp_basis: "ANALYSIS_START_PROXY_NOT_RECORDING_TIME",
    },
    parameters: { max_distance: 0.25, minimum_duration_seconds: 1 },
    observations: { normalized_distance: 0.1, duration_s: 1 },
    evidence_url: `/api/v1/events/${eventId}/evidence/`,
  };
  const server = createServer(async (req, res) => {
    res.setHeader("Access-Control-Allow-Origin", "*");
    res.setHeader("Access-Control-Allow-Headers", "Content-Type");
    res.setHeader(
      "Access-Control-Allow-Methods",
      "GET,POST,PUT,DELETE,OPTIONS",
    );
    res.setHeader("Cache-Control", "no-store");
    const send = (data, code = 200) => {
      res.writeHead(code, { "Content-Type": "application/json" });
      res.end(JSON.stringify(data));
    };
    try {
      if (req.method === "OPTIONS") {
        res.writeHead(204);
        return res.end();
      }
      const url = new URL(req.url, `http://127.0.0.1:${port}`);
      const chunks = [];
      for await (const chunk of req) chunks.push(chunk);
      const raw = Buffer.concat(chunks).toString();
      const body =
        raw && req.headers["content-type"]?.includes("application/json")
          ? JSON.parse(raw)
          : {};
      if (url.pathname === "/__fixture") {
        if (body.reset) {
          sessions = new Map();
          sequence = 0;
          deleted = 0;
          failNext = false;
        }
        if (body.failNext) failNext = true;
        if (body.delayNextStatus) delayNextStatus = true;
        return send({
          created: sequence,
          deleted,
          waitingStatus,
          ids: [...sessions.keys()],
        });
      }
      if (url.pathname.endsWith("/health/")) return send({ status: "ok" });
      if (url.pathname.endsWith("/profiles/"))
        return send(
          ["A", "B", "C"].map((id) => ({
            id,
            display_name: `Demo ${id}`,
            default_demo_video: {
              id: `demo-${id}`,
              filename: `TEST_DATA_${id}.mp4`,
              bytes: video.length,
            },
          })),
        );
      if (
        url.pathname === "/api/v1/analysis/sessions/" &&
        req.method === "POST"
      ) {
        const id = `00000000-0000-4000-8000-${String(++sequence).padStart(12, "0")}`;
        const profile = body.profile ?? "A";
        const session = {
          id,
          state: "ready",
          filename: `TEST_DATA_${profile}.mp4`,
          profile,
          source_bytes: video.length,
          source_kind: "demo",
          source_sha256: "0".repeat(64),
          demo_source_id: `demo-${profile}`,
          zone: { zone_id: "TEST_DATA_ZONE", name: "Zona fixture", polygon },
          run: 0,
          result: null,
          pending_changes: false,
          frame: 0,
          total: 277,
          percent: null,
          fps: null,
          width: 1920,
          height: 1080,
          source_fps: 30,
          person_detections: 0,
          forklift_detections: 0,
          person_tracks: 0,
          forklift_tracks: 0,
        };
        sessions.set(id, session);
        return send(session, 201);
      }
      const match = url.pathname.match(
        /^\/api\/v1\/analysis\/sessions\/([^/]+)\/(.*)$/,
      );
      if (match) {
        const session = sessions.get(match[1]),
          action = match[2];
        if (!session) return send({ detail: "La sesión expiró." }, 404);
        if (req.method === "DELETE") {
          sessions.delete(session.id);
          deleted++;
          return send({});
        }
        if (action === "zone/") {
          session.zone = {
            ...session.zone,
            polygon: body.polygon ?? session.zone.polygon,
          };
          session.pending_changes = true;
          return send(session);
        }
        if (action === "start/") {
          Object.assign(session, {
            state: "preparing",
            detail: "Verificando integridad y cadencia del video",
            percent: null,
            frame: 0,
            result: null,
            persistence: { state: "pending" },
            run: session.run + 1,
            started: Date.now(),
            fail: failNext,
          });
          failNext = false;
        }
        if (action === "stop/")
          Object.assign(session, {
            state: "cancelled",
            detail: undefined,
            percent: 20,
            started: null,
          });
        if (action === "status/" && session.started) {
          const elapsed = Date.now() - session.started;
          if (elapsed > 1200)
            Object.assign(session, {
              state: "processing",
              detail: undefined,
              frame: 200,
              percent: 100,
            });
          if (elapsed > 4000) {
            Object.assign(session, {
              state: session.fail ? "error" : "completed",
              frame: session.fail ? 200 : 277,
              percent: session.fail ? 72 : 100,
              detail: session.fail
                ? "No se pudo procesar el video. Revise la fuente y vuelva a intentar."
                : undefined,
              started: null,
              person_detections: 20,
              forklift_detections: 10,
            });
            if (!session.fail)
              Object.assign(session, {
                pending_changes: false,
                persistence: {
                  state: "saved",
                  saved: 1,
                  candidates: 1,
                  event_ids: [eventId],
                },
                result: {
                  profile: session.profile,
                  zone: session.zone,
                  source_video: session.filename,
                  source_fps: 30,
                  frames: 277,
                  width: 1920,
                  height: 1080,
                  video: {
                    codec: "h264",
                    fps: 30,
                    frames: 277,
                    width: 1920,
                    height: 1080,
                  },
                  person: { imgsz: 640, confidence: 0.1, nms_iou: 0.7 },
                  forklift: { imgsz: 640, confidence: 0.45, nms_iou: 0.55 },
                  run: session.run,
                },
              });
          }
        }
        if (["source/", "result/"].includes(action)) {
          const range = req.headers.range?.match(/bytes=(\d+)-(\d*)/);
          const start = range ? Number(range[1]) : 0,
            end =
              range && range[2]
                ? Math.min(Number(range[2]), video.length - 1)
                : video.length - 1;
          res.writeHead(range ? 206 : 200, {
            "Content-Type": "video/mp4",
            "Accept-Ranges": "bytes",
            "Content-Length": end - start + 1,
            ...(range
              ? { "Content-Range": `bytes ${start}-${end}/${video.length}` }
              : {}),
          });
          return res.end(video.subarray(start, end + 1));
        }
        if (action === "stream/") {
          res.writeHead(200, { "Content-Type": "image/png" });
          return res.end(png);
        }
        const snapshot = JSON.parse(JSON.stringify(session));
        if (action === "status/" && delayNextStatus) {
          delayNextStatus = false;
          waitingStatus = true;
          await new Promise((resolve) => setTimeout(resolve, 1000));
          waitingStatus = false;
        }
        return send(snapshot);
      }
      if (url.pathname.endsWith("/frequencies/")) {
        const total = url.searchParams
          .get("occurred_after")
          ?.startsWith("2026-09")
          ? 0
          : 1;
        return send({
          total,
          timezone: "UTC",
          period: "day",
          by_period: total ? [{ date: "2026-10-25", count: 1 }] : [],
          by_type: total ? [{ event_type: event.event_type, count: 1 }] : [],
        });
      }
      if (url.pathname === "/api/v1/events/")
        return send(
          url.searchParams.get("event_type") === "zone_dwell" ? [] : [event],
        );
      if (url.pathname === event.evidence_url) {
        res.writeHead(200, { "Content-Type": "image/png" });
        return res.end(png);
      }
      if (url.pathname === `/api/v1/events/${eventId}/`) return send(event);
      send({ detail: "Ruta fixture no disponible" }, 404);
    } catch {
      if (!res.headersSent) send({ detail: "Error de fixture" }, 500);
      else res.end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(port, "127.0.0.1", resolve);
  });
  return server;
}
if (process.argv[1] === fileURLToPath(import.meta.url)) {
  await startFixtureApi(Number(process.env.OPERIX_FIXTURE_PORT ?? 8000));
  console.log(
    "API fixture local lista; detener con Ctrl+C. No utiliza servicios productivos.",
  );
}
