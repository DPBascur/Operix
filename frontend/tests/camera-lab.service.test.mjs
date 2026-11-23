import assert from "node:assert/strict";
import { registerHooks } from "node:module";
import test from "node:test";
import { startFixtureApi } from "./fixtures/analysis-api.mjs";

test("camera control uses authenticated GET and PATCH and reads inventory and previews", async (t) => {
  const server = await startFixtureApi(0);
  t.after(() => new Promise((resolve) => server.close(resolve)));
  const origin = `http://127.0.0.1:${server.address().port}`;
  const aliases = {
    "@/config/environment": "../src/config/environment.ts",
    "@/services/browser-session": "../src/services/browser-session.ts",
  };
  const hooks = registerHooks({
    resolve(specifier, context, next) {
      return next(
        Object.hasOwn(aliases, specifier)
          ? new URL(aliases[specifier], import.meta.url).href
          : specifier,
        context,
      );
    },
  });
  t.after(() => hooks.deregister());
  t.mock.method(globalThis, "fetch", (url, init) => {
    return originalFetch(new URL(url, origin), init);
  });
  process.env.NEXT_PUBLIC_API_BASE_URL = `${origin}/api/v1`;
  globalThis.window = { location: { origin } };
  t.after(() => {
    delete process.env.NEXT_PUBLIC_API_BASE_URL;
    delete globalThis.window;
  });
  const { apiFetch, signIn } =
    await import("../src/services/browser-session.ts");
  const { cameraLabService } =
    await import("../src/services/camera-lab.service.ts");
  const signal = AbortSignal.timeout(5000);
  await signIn("fixture-admin", "TEST_ONLY_PASSWORD");
  assert.equal((await cameraLabService.control(signal)).available, false);

  const seeded = await fetch("/__fixture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ managedCamera: "data:image/jpeg;base64,/9j/2Q==" }),
  });
  assert.equal(seeded.status, 200);
  const legacy = await cameraLabService.control(signal);
  assert.equal(legacy.catalog, undefined);
  assert.equal(legacy.playlists, undefined);
  const inventory = await cameraLabService.list(signal);
  assert.equal(inventory.managed, true);
  const [camera] = inventory.cameras;
  assert.equal(camera.automatic, true);
  assert.equal(
    (await cameraLabService.preview(camera.id, camera.preview_url, signal))
      .type,
    "image/jpeg",
  );

  const reading = Promise.withResolvers();
  const release = Promise.withResolvers();
  const originalBlob = Response.prototype.blob;
  const pausedBlob = t.mock.method(
    Response.prototype,
    "blob",
    async function () {
      const blob = await originalBlob.call(this);
      reading.resolve();
      await release.promise;
      return blob;
    },
  );
  try {
    const controller = new AbortController();
    const cancelled = assert.rejects(
      cameraLabService.preview(
        camera.id,
        camera.preview_url,
        controller.signal,
      ),
      { name: "AbortError" },
    );
    await reading.promise;
    controller.abort();
    release.resolve();
    await cancelled;
  } finally {
    release.resolve();
    pausedBlob.mock.restore();
  }

  const catalog = [
    { id: "media-a", filename: "a.mp4", title: "Recepción" },
    { id: "media-b", filename: "b.mp4", duration_s: 42 },
  ];
  const extended = await fetch("/__fixture", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ labCatalog: catalog }),
  });
  assert.equal(extended.status, 200);
  assert.deepEqual((await cameraLabService.control(signal)).catalog, catalog);
  const playlist = { media_ids: ["media-b", "media-a"], repeat: true };
  await cameraLabService.updateControl({
    playlists: { [camera.id]: playlist },
  });
  assert.deepEqual((await cameraLabService.control(signal)).playlists, {
    [camera.id]: playlist,
  });
  await assert.rejects(
    cameraLabService.updateControl({
      playlists: { [camera.id]: { media_ids: ["a.mp4"], repeat: false } },
    }),
    { status: 400 },
  );

  await cameraLabService.updateControl({ cameras: { [camera.id]: false } });
  const partial = await cameraLabService.control(signal);
  assert.equal(partial.status, "partial");
  assert.equal(partial.publisher[camera.id], "idle");
  assert.equal(partial.cameras[0].preview_url, null);

  await cameraLabService.updateControl({ enabled: false });
  const disabled = await cameraLabService.control(signal);
  assert.equal(disabled.enabled, false);
  assert.equal(disabled.cameras[0].enabled, false);
  assert.deepEqual(disabled.playlists[camera.id], playlist);

  const lead = { username: "fixture-lead", password: "TEST_ONLY_LEAD" };
  const created = await apiFetch("/api/v1/users/", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...lead, role: "safety_lead", is_active: true }),
  });
  assert.equal(created.status, 201);
  await signIn(lead.username, lead.password);
  assert.equal(
    (await cameraLabService.detail(camera.id, signal)).automatic,
    true,
  );
  await assert.rejects(cameraLabService.control(signal), { status: 403 });
  await assert.rejects(cameraLabService.updateControl({ enabled: true }), {
    status: 403,
  });
});

const originalFetch = globalThis.fetch;
