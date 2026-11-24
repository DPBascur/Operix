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
  let demoCMissing = false;
  let assignedPolicy = false;
  let configurationReads = 0;
  let requestedSourceSha = null;
  let evidenceSteps = [];
  let eventDetailReads = 0;
  let cameraFixture;
  let extraCameras = [];
  let historyCount = 1;
  let labControl;
  let heldLabPreview;
  let calibrationPreview;
  let discoveryMarkerIds = [1, 2, 3];
  let candidateAvailable;
  let calibrationRequests = [];
  const csrf = "TEST_ONLY_CSRF";
  const run = "00000000-0000-4000-8000-000000000055";
  const event = {
    analysis_run_id: run,
    view_id: "fixture",
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
      config_sha256: "b".repeat(64),
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
  function stagedEvent(step) {
    if (!step) return event;
    return {
      ...event,
      evidence_status: step.status,
      evidence_url: step.png ? event.evidence_url : null,
      evidence_clip: step.clip ? event.evidence_clip : null,
    };
  }
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
          demoCMissing = false;
          assignedPolicy = false;
          configurationReads = 0;
          requestedSourceSha = null;
          evidenceSteps = [];
          eventDetailReads = 0;
          cameraFixture = undefined;
          extraCameras = [];
          historyCount = 1;
          labControl = undefined;
          heldLabPreview?.();
          calibrationPreview = undefined;
          candidateAvailable = false;
          calibrationRequests = [];
        }
        if (Number.isInteger(body.cameraCount) && body.cameraCount >= 1 && body.cameraCount <= 4) {
          extraCameras = Array.from({ length: body.cameraCount - 1 }, (_, index) => ({
            id: `lab-cam-0${index + 2}`, name: `Cámara de prueba ${index + 2}`,
            automatic: true, status: "connecting", revision: 0, configuration: null, metrics: null,
          }));
        }
        if (body.calibrationCamera) {
          labControl = undefined;
          cameraFixture = {
            id: "lab-cam-01",
            name: "Cámara fixture",
            status: "stopped",
            revision: 4,
            metrics: { framing: { state: "INVALID" } },
            calibration_requires_reconfirmation: true,
            configuration: {
              schema_version: 1,
              view_id: "lab-cam-01",
              coordinate_system: "normalized",
              zones: [{ zone_id: "fixture", name: "Área operativa", polygon }],
              rules: [],
            },
          };
          calibrationPreview = body.calibrationCamera;
          discoveryMarkerIds = [1, 2, 3];
          candidateAvailable = false;
        }
        if (body.managedCamera) {
          cameraFixture = {
            id: "lab-cam-01",
            name: "Cámara virtual fixture",
            automatic: true,
            revision: 0,
            status: "analyzing",
            metrics: { observed_fraction_5s: 0.75, last_frame_age_ms: 0 },
          };
          labControl = {
            enabled: true,
            cameraEnabled: true,
            preview: body.managedCamera,
          };
        }
        if (labControl && body.labCatalog) {
          labControl.catalog = body.labCatalog;
          labControl.playlists = {};
        }
        if (labControl && body.labCameraStatus)
          labControl.cameraStatus = body.labCameraStatus;
        if (labControl && body.labPreview) labControl.preview = body.labPreview;
        if (labControl && body.holdLabPreview) labControl.holdPreview = true;
        if (body.releaseLabPreview) heldLabPreview?.();
        if (body.calibrationCandidate) candidateAvailable = true;
        if (Array.isArray(body.discoveryMarkerIds))
          discoveryMarkerIds = body.discoveryMarkerIds;
        if (Number.isSafeInteger(body.historyCount)) historyCount = body.historyCount;
        if (Array.isArray(body.evidenceSteps)) {
          evidenceSteps = body.evidenceSteps;
          eventDetailReads = 0;
        }
        if (typeof body.demoCMissing === "boolean")
          demoCMissing = body.demoCMissing;
        if (typeof body.assignedPolicy === "boolean")
          assignedPolicy = body.assignedPolicy;
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
          configurationReads,
          requestedSourceSha,
          eventDetailReads,
          calibrationRequests,
          labPreviewWaiting: Boolean(heldLabPreview),
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
        /^\/api\/v1\/users\/(?:(\d+)\/((?:password|retire|reactivate)\/)?)?$/,
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
        } else if (directoryUrl[2] === "reactivate/") {
          row.is_active = true;
          directoryPasswords.set(row.id, body.password);
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
            default_demo_video:
              demoCMissing && id === "C"
                ? null
                : {
                    id: `demo-${id}`,
                    filename: `TEST_DATA_${id}.mp4`,
                    bytes: video.length,
                  },
          })),
        );
      const cameraRoute = "/api/v1/analysis/cameras/lab-cam-01/";
      const currentCamera = () => {
        if (!labControl) return cameraFixture;
        if (!labControl.enabled || !labControl.cameraEnabled)
          return {
            ...cameraFixture,
            status: "stopped",
            preview_url: null,
            metrics: null,
          };
        if (labControl.cameraStatus === "reconnecting")
          return {
            ...cameraFixture,
            status: "reconnecting",
            preview_url: null,
            metrics: null,
          };
        return {
          ...cameraFixture,
          last_frame_at: new Date().toISOString(),
          preview_url: `${cameraRoute}preview/`,
        };
      };
      if (url.pathname === "/api/v1/analysis/cameras/control/") {
        if (account.role !== "administrator")
          return send({ detail: "Acceso denegado" }, 403);
        if (!labControl)
          return send({
            available: false,
            enabled: false,
            status: "disabled",
            capacity: 1,
            cameras: [],
            publisher: {},
            mediamtx: "unavailable",
            updated_by: null,
          });
        if (req.method === "PATCH") {
          if (req.headers["x-csrftoken"] !== csrf)
            return send({ detail: "CSRF inválido" }, 403);
          if (body.playlists) {
            const playlist = body.playlists[cameraFixture.id];
            const permitted = new Set(labControl.catalog?.map(({ id }) => id));
            if (
              !labControl.playlists ||
              Object.keys(body.playlists).length !== 1 ||
              !playlist ||
              Object.keys(playlist).length !== 2 ||
              typeof playlist.repeat !== "boolean" ||
              !Array.isArray(playlist.media_ids) ||
              !playlist.media_ids.every((id) => permitted.has(id))
            )
              return send({ detail: "Lista de reproducción inválida" }, 400);
            labControl.playlists[cameraFixture.id] = playlist;
          }
          if (typeof body.enabled === "boolean")
            labControl.enabled = body.enabled;
          if (typeof body.cameras?.[cameraFixture.id] === "boolean")
            labControl.cameraEnabled = body.cameras[cameraFixture.id];
        }
        const camera = currentCamera();
        return send(
          {
            available: true,
            enabled: labControl.enabled,
            status: !labControl.enabled
              ? "disabled"
              : labControl.cameraEnabled
                ? "active"
                : "partial",
            capacity: 1,
            cameras: [{ ...camera, enabled: labControl.cameraEnabled }],
            publisher: {
              [camera.id]:
                labControl.enabled && labControl.cameraEnabled
                  ? "publishing"
                  : "idle",
            },
            mediamtx: "ready",
            updated_by: account.username,
            ...(labControl.catalog && { catalog: labControl.catalog, playlists: labControl.playlists }),
          },
          req.method === "PATCH" ? 202 : 200,
        );
      }
      const camera = currentCamera();
      if (url.pathname === "/api/v1/analysis/cameras/") {
        return send({
          enabled: Boolean(camera),
          managed: Boolean(labControl),
          can_edit: true,
          capacity: 1,
          cameras: camera ? [camera, ...extraCameras] : [],
        });
      }
      if (camera && url.pathname === cameraRoute) return send(camera);
      const fixtureCamera = extraCameras.find(({ id }) => url.pathname === `/api/v1/analysis/cameras/${id}/`);
      if (fixtureCamera) return send(fixtureCamera);
      if (labControl && url.pathname === `${cameraRoute}preview/`) {
        if (!camera.preview_url)
          return send({ detail: "Sin fotograma reciente" }, 404);
        const preview = labControl.preview;
        if (labControl.holdPreview) {
          labControl.holdPreview = false;
          await new Promise((resolve) => {
            const release = () => {
              res.off("close", release);
              if (heldLabPreview === release) heldLabPreview = undefined;
              resolve();
            };
            heldLabPreview = release;
            res.once("close", release);
          });
        }
        if (res.destroyed) return;
        res.writeHead(200, { "Content-Type": "image/jpeg" });
        return res.end(Buffer.from(preview.split(",")[1], "base64"));
      }
      if (
        cameraFixture &&
        url.pathname.startsWith(`${cameraRoute}calibration/`)
      ) {
        if (req.method !== "POST" || req.headers["x-csrftoken"] !== csrf)
          return send({}, 403);
        const operation = url.pathname.slice(
          `${cameraRoute}calibration/`.length,
        );
        calibrationRequests.push({ operation, body });
        if (body.revision !== cameraFixture.revision)
          return send({ detail: "Revisión incorrecta" }, 409);
        if (operation === "proposal/") {
          if (!body.layout)
            return send({
              status: "requires_review", proposal_id: null, discovery_id: "fixture-discovery",
              preview_url: calibrationPreview, usable_polygon: [], grid: [], quality: {},
              references: discoveryMarkerIds.map((id) => ({ id, corners: [] })),
            });
          return send({
            status: candidateAvailable ? "candidate" : "requires_review",
            proposal_id: candidateAvailable ? "fixture-signed-proposal" : null,
            preview_url: calibrationPreview,
            expires_at: new Date(Date.now() + 600_000).toISOString(),
            reasons: candidateAvailable ? [] : ["insufficient_distribution"],
            usable_polygon: polygon,
            grid: [
              [
                [0.2, 0.3],
                [0.8, 0.3],
              ],
              [
                [0.2, 0.6],
                [0.8, 0.6],
              ],
            ],
            references: [
              {
                id: 1,
                corners: [
                  [0.13, 0.16],
                  [0.18, 0.16],
                  [0.18, 0.21],
                  [0.13, 0.21],
                ],
              },
            ],
            quality: { reprojection_error_px: 0.23, coverage_ratio: 0.64 },
          });
        }
        if (
          body.proposal_id !== "fixture-signed-proposal" ||
          !body.ground_confirmed ||
          !body.zones_reviewed
        ) {
          return send({ detail: "Confirmación incompleta" }, 400);
        }
        if (body.control?.distance_m !== 2)
          return send(
            ["La medida de comprobación supera la tolerancia declarada"],
            400,
          );
        cameraFixture.revision++;
        cameraFixture.calibration_requires_reconfirmation = false;
        cameraFixture.configuration.calibration = {
          status: "valid",
          version: 2,
          zones_reviewed: true,
          pattern_evidence: {
            control: {
              ...body.control,
              observed_m: 2.01,
              absolute_error_m: 0.01,
              relative_error: 0.005,
            },
          },
        };
        return send(cameraFixture);
      }
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
        requestedSourceSha =
          body.source_sha256 ??
          raw.match(/name="source_sha256"\r\n\r\n([a-f0-9]{64})/)?.[1] ??
          null;
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
          configurationReads++;
          return send({
            document,
            saved: session.spatialDocument ?? null,
            ...(assignedPolicy
              ? {
                  policy: {
                    rule_set: { name: "Política fixture", version: 3 },
                  },
                  effective_rules: [
                    {
                      rule_id: "regla_fixture_asignada",
                      version: 2,
                      enabled: true,
                      parameters: {
                        kind: "zone_entry",
                        zone_id: session.zone.zone_id,
                      },
                    },
                  ],
                }
              : { policy: null, effective_rules: document.rules }),
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
            zone_id: event.zone_id,
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
        if (url.pathname === "/api/v1/events/") {
          const row = { ...stagedEvent(evidenceSteps[0]) };
          delete row.evidence_clip;
          if (params.has("page")) {
            const count = matches ? historyCount : 0;
            const page_size = Number(params.get("page_size") ?? 15);
            const total_pages = Math.max(1, Math.ceil(count / page_size));
            const page = Math.min(Number(params.get("page")), total_pages);
            const from = (page - 1) * page_size;
            const results = Array.from({ length: Math.min(page_size, count - from) }, (_, index) => {
              const position = from + index;
              return position === 0 ? row : {
                ...row,
                id: `00000000-0000-4000-8000-${String(1000 + position).padStart(12, "0")}`,
              };
            });
            return send({ count, page, page_size, total_pages, results });
          }
          return send(matches ? [row] : []);
        }
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
      if (url.pathname === `/api/v1/events/${eventId}/`) {
        const step =
          evidenceSteps[Math.min(eventDetailReads++, evidenceSteps.length - 1)];
        if (step?.unavailable)
          return send({ detail: "Fixture no disponible" }, 503);
        return send(stagedEvent(step));
      }
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
