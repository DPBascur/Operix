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
function rulesFor(profile, zoneId = "TEST_DATA_ZONE") {
  return {
    config_sha256: "0".repeat(64),
    rules: [
      {
        rule_id: `TEST_DATA_${profile}`,
        version: 2,
        enabled: profile !== "A",
        parameters: {
          kind: "person_forklift_proximity",
          zone_id: zoneId,
          max_distance: 0.25,
          minimum_duration_seconds: 1,
        },
      },
    ],
  };
}

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
    waitingStatus = false,
    delayNextZone = false;
  const pendingZones = [];
  let signedIn = false;
  let failHistory = false;
  const admin = { username: "fixture-admin", role: "administrator" };
  let account = admin;
  const adminRow = {
    ...admin,
    id: 1,
    display_name: "Admin de prueba",
    is_active: true,
    protected: true,
    role_review_required: false,
  };
  let directory = [adminRow];
  const directoryPasswords = new Map();
  const csrf = "TEST_ONLY_CSRF";
  const run = "00000000-0000-4000-8000-000000000055";
  const event = {
    analysis_run_id: run,
    evidence_clip: {
      kind: "annotated",
      event_id: eventId,
      analysis_run_id: run,
      event_offset_s: 1,
      url: `/api/v1/events/${eventId}/clips/${run}/`,
    },
    id: eventId,
    occurred_at: `${new Date().toISOString().slice(0, 7)}-01T12:00:01Z`,
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
      kind: "demo",
      video_sha256: "a".repeat(64),
      timestamp_basis: "ANALYSIS_START_PROXY_NOT_RECORDING_TIME",
    },
    rule_parameters: { max_distance: 0.25, minimum_duration_seconds: 1 },
    observations: {
      normalized_distance: 0.1,
      duration_s: 1,
      proximity_geometry: {
        version: "person_equipment_nearest_ground_edges_v1",
        person_anchor: [0.2, 0.5],
        equipment_target: [0.3, 0.5],
      },
    },
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
    const sendVideo = () => {
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
          signedIn = false;
          account = admin;
          directory = [adminRow];
          directoryPasswords.clear();
          sessions = new Map();
          sequence = 0;
          deleted = 0;
          failNext = false;
        }
        if (body.failNext) failNext = true;
        if (body.expire) signedIn = false;
        if (body.failHistory) failHistory = true;
        if (body.delayNextStatus) delayNextStatus = true;
        if (body.delayNextZone) delayNextZone = true;
        if (body.releaseZones) {
          for (const release of pendingZones.splice(0)) release();
        }
        return send({
          created: sequence,
          deleted,
          waitingStatus,
          waitingZones: pendingZones.length,
          ids: [...sessions.keys()],
        });
      }
      if (url.pathname.endsWith("/health/")) return send({ status: "ok" });
      if (url.pathname === "/api/v1/auth/session/")
        return send({ user: signedIn ? account : null, csrf_token: csrf });
      if (
        url.pathname === "/api/v1/auth/login/" ||
        url.pathname === "/api/v1/auth/logout/"
      ) {
        if (req.method !== "POST" || req.headers["x-csrftoken"] !== csrf)
          return send({ detail: "CSRF inválido" }, 403);
        if (url.pathname.endsWith("/login/")) {
          const accepted = directory.find(
            (row) => row.username === body.username && row.is_active,
          );
          const pass =
            accepted?.id === 1
              ? "TEST_ONLY_PASSWORD"
              : directoryPasswords.get(accepted?.id);
          if (!accepted || body.password !== pass)
            return send({ detail: "Usuario o contraseña incorrectos." }, 401);
          account = { username: accepted.username, role: accepted.role };
          signedIn = true;
        } else {
          signedIn = false;
          account = admin;
        }
        return send({ user: signedIn ? account : null, csrf_token: csrf });
      }
      if (!signedIn) return send({ detail: "Sesión requerida" }, 401);
      if (url.pathname === "/api/v1/auth/password/") {
        if (req.method !== "POST" || req.headers["x-csrftoken"] !== csrf)
          return send({ detail: "CSRF inválido" }, 403);
        if (
          body.old_password !== "TEST_ONLY_PASSWORD" ||
          body.new_password1 !== body.new_password2
        )
          return send({ detail: "Revise las contraseñas." }, 400);
        return send({ user: account, csrf_token: csrf });
      }
      const directoryUrl = url.pathname.match(
        /^\/api\/v1\/users\/(?:(\d+)\/((?:password|retire)\/)?)?$/,
      );
      if (directoryUrl) {
        if (account.role !== "administrator")
          return send({ detail: "Acceso denegado" }, 403);
        if (req.method !== "GET" && req.headers["x-csrftoken"] !== csrf)
          return send({ detail: "CSRF inválido" }, 403);
        if (!directoryUrl[1]) {
          if (req.method === "GET")
            return send({ accounts: directory, next: null });
          if (directory.some((row) => row.username === body.username))
            return send(
              { detail: "Ya existe una cuenta con ese usuario." },
              409,
            );
          const { password, username, display_name, role, is_active } = body;
          const row = {
            id: directory.length + 1,
            username,
            display_name,
            role,
            is_active,
            protected: false,
            role_review_required: false,
          };
          directory.push(row);
          directoryPasswords.set(row.id, password);
          return send(row, 201);
        }
        const row = directory.find(
          (entry) => entry.id === Number(directoryUrl[1]),
        );
        if (
          !row ||
          row.protected ||
          row.retired ||
          row.username === account.username
        )
          return send({ detail: "Cuenta no editable" }, 409);
        if (directoryUrl[2] === "retire/") {
          if (req.method !== "POST")
            return send({ detail: "Método no permitido" }, 405);
          row.is_active = false;
          row.retired = true;
          directoryPasswords.delete(row.id);
        } else if (directoryUrl[2])
          directoryPasswords.set(row.id, body.password);
        else {
          row.role = body.role;
          row.is_active = body.is_active;
        }
        return send(row);
      }
      if (url.pathname === "/api/v1/indicators/shared/")
        return send({
          total: 0,
          timezone: "UTC",
          period: "day",
          by_period: [],
          by_type: [],
        });
      if (
        account.role === "viewer" &&
        /^\/api\/v1\/(analysis|events)\//.test(url.pathname)
      )
        return send({ detail: "Acceso denegado" }, 403);
      if (url.pathname.endsWith("/profiles/"))
        return send(
          ["A", "B", "C"].map((id) => ({
            id,
            display_name: `Demo ${id}`,
            configuration: rulesFor(id),
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
        const manual = req.headers["content-type"]?.includes(
          "multipart/form-data",
        );
        const profile =
          body.profile ??
          raw.match(/name="profile"\r\n\r\n([ABC])/)?.[1] ??
          "A";
        const session = {
          id,
          state: "ready",
          filename: `TEST_DATA_${profile}.mp4`,
          profile,
          source_bytes: video.length,
          source_kind: manual ? "manual" : "demo",
          source_sha256: "0".repeat(64),
          demo_source_id: manual ? null : `demo-${profile}`,
          zone: {
            zone_id: manual ? "custom_zone" : "TEST_DATA_ZONE",
            name: "Zona fixture",
            polygon: manual ? [] : polygon,
          },
          run: 0,
          configuration: rulesFor(
            profile,
            manual ? "custom_zone" : "TEST_DATA_ZONE",
          ),
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
        if (action === "configuration/") {
          const document = session.spatialDocument ?? {
            schema_version: 1,
            view_id: "fixture",
            coordinate_system: "normalized",
            zones: [session.zone],
            rules: session.configuration.rules,
          };
          if (req.method === "PUT") {
            session.spatialDocument = body.document;
            session.spatial_revision = (session.spatial_revision ?? 0) + 1;
            session.zone = body.document.zones[0];
            session.configuration = {
              ...session.configuration,
              rules: body.document.rules,
            };
            return send({
              document: body.document,
              revision: session.spatial_revision,
            });
          }
          return send({
            document,
            saved: session.spatialDocument ?? null,
            revision: session.spatial_revision ?? 0,
          });
        }
        if (action === "zone/") {
          session.profile = body.profile ?? session.profile;
          session.configuration = rulesFor(
            session.profile,
            session.zone.zone_id,
          );
          session.zone = {
            ...session.zone,
            polygon: body.polygon ?? session.zone.polygon,
          };
          session.pending_changes = true;
          if (delayNextZone) {
            delayNextZone = false;
            const snapshot = structuredClone(session);
            pendingZones.push(() => send(snapshot));
            return;
          }
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
                // Un snapshot anterior puede conservar este indicador en true.
                preview: { pending: true },
                pending_changes: false,
                persistence: {
                  state: "saved",
                  saved: 1,
                  candidates: 1,
                  event_ids: [eventId],
                },
                result: {
                  ...session.configuration,
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
          return sendVideo();
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
      if (
        ["/api/v1/events/", "/api/v1/events/frequencies/"].includes(
          url.pathname,
        )
      ) {
        if (failHistory) {
          failHistory = false;
          return send({ detail: "Fixture no disponible" }, 503);
        }
        const params = url.searchParams;
        const matches =
          Object.entries({
            event_type: event.event_type,
            source_kind: event.source.kind,
            source_sha256: event.source.video_sha256,
          }).every(
            ([key, value]) => !params.has(key) || params.get(key) === value,
          ) &&
          (!params.has("occurred_after") ||
            Date.parse(event.occurred_at) >=
              Date.parse(params.get("occurred_after"))) &&
          (!params.has("occurred_before") ||
            Date.parse(event.occurred_at) <=
              Date.parse(params.get("occurred_before")));
        if (url.pathname === "/api/v1/events/")
          return send(matches ? [event] : []);
        return send({
          total: matches ? 1 : 0,
          timezone: "UTC",
          period: "day",
          by_period: matches
            ? [{ date: event.occurred_at.slice(0, 10), count: 1 }]
            : [],
          by_type: matches ? [{ event_type: event.event_type, count: 1 }] : [],
        });
      }
      if (url.pathname === event.evidence_clip.url) return sendVideo();
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
