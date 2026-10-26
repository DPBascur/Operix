import assert from "node:assert/strict";
import test from "node:test";
import {
  analysisPercent,
  applyZoneRequest,
  tabStorage,
  sessionVideoInfo,
  readSessionReference,
  sessionReferenceKey,
  writeSessionReference,
} from "../src/features/analysis/analysis-session.ts";

const id = "00000000-0000-4000-8000-000000000001";
const memory = () => {
  const data = new Map();
  return {
    getItem: (key) => data.get(key) ?? null,
    setItem: (key, value) => data.set(key, value),
    removeItem: (key) => data.delete(key),
  };
};

const deferred = () => {
  let resolve, reject;
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
};

test("aplicar B antes de A conserva B y no libera busy desde la respuesta vieja", async () => {
  const generation = { current: 0 },
    a = deferred(),
    b = deferred();
  const effects = [];
  const callbacks = {
    applied: (session) => effects.push(session.id),
    failed: () => effects.push("error"),
    settled: () => effects.push("settled"),
  };
  const first = applyZoneRequest(generation, () => a.promise, callbacks);
  const second = applyZoneRequest(generation, () => b.promise, callbacks);
  b.resolve({ id: "B" });
  await second;
  a.resolve({ id: "A" });
  await first;
  assert.deepEqual(effects, ["B", "settled"]);
});

test("cambiar contexto invalida éxito, error y finally de applyZone", async () => {
  for (const failed of [false, true]) {
    const generation = { current: 0 },
      request = deferred(),
      effects = [];
    const pending = applyZoneRequest(generation, () => request.promise, {
      applied: () => effects.push("applied"),
      failed: () => effects.push("failed"),
      settled: () => effects.push("settled"),
    });
    generation.current++;
    if (failed) request.reject(new Error("late error"));
    else request.resolve({ id: "old context" });
    await pending;
    assert.deepEqual(effects, []);
  }
});

test("error vigente de applyZone conserva el manejo de error y libera busy", async () => {
  const effects = [],
    cause = new Error("current error");
  await applyZoneRequest(
    { current: 0 },
    async () => {
      throw cause;
    },
    {
      applied: () => effects.push("applied"),
      failed: (error) => effects.push(error),
      settled: () => effects.push("settled"),
    },
  );
  assert.deepEqual(effects, [cause, "settled"]);
});
test("retiene solo la referencia y permite recuperarla o limpiarla por API", () => {
  const storage = memory(),
    key = sessionReferenceKey("http://fixture/api/v1/");
  writeSessionReference(storage, key, id);
  assert.equal(readSessionReference(storage, key), id);
  assert.equal(
    readSessionReference(storage, sessionReferenceKey("http://otra/api/v1")),
    null,
  );
  writeSessionReference(storage, key, null);
  assert.equal(readSessionReference(storage, key), null);
});
test("almacenamiento corrupto o bloqueado no se trata como una sesión recuperable", () => {
  const storage = memory();
  storage.setItem("fixture", "<invalid>");
  assert.equal(readSessionReference(storage, "fixture"), null);
  const blocked = {
    getItem() {
      throw new Error("blocked");
    },
    setItem() {
      throw new Error("blocked");
    },
    removeItem() {
      throw new Error("blocked");
    },
  };
  assert.equal(readSessionReference(blocked, "fixture"), null);
  assert.doesNotThrow(() => writeSessionReference(blocked, "fixture", id));
  assert.doesNotThrow(() => writeSessionReference(blocked, "fixture", null));
  const blockedGetter = {
    get sessionStorage() {
      throw new Error("SecurityError");
    },
  };
  assert.equal(tabStorage(blockedGetter), null);
  assert.equal(
    readSessionReference(tabStorage(blockedGetter), "fixture"),
    null,
  );
  assert.doesNotThrow(() =>
    writeSessionReference(tabStorage(blockedGetter), "fixture", id),
  );
});
test("solo completed puede mostrar cien; preparación desconocida sigue indeterminada", () => {
  for (const state of ["preparing", "processing", "error", "cancelled"]) {
    assert.equal(analysisPercent(state, 100), 99.9);
    assert.equal(analysisPercent(state, null), null);
  }
  assert.equal(analysisPercent("completed", 100), 100);
  assert.equal(analysisPercent("processing", -1), 0);
  assert.equal(analysisPercent("processing", NaN), null);
});

test("recupera dimensiones verticales y duración desde resultado o fuente manual", () => {
  assert.deepEqual(
    sessionVideoInfo({
      result: { width: 720, height: 1280, frames: 300, source_fps: 30 },
    }),
    { width: 720, height: 1280, duration: 10 },
  );
  assert.deepEqual(
    sessionVideoInfo({
      source_kind: "manual",
      width: 480,
      height: 854,
      total: 120,
      source_fps: 30,
    }),
    { width: 480, height: 854, duration: 4 },
  );
  assert.equal(sessionVideoInfo({}).duration, 0);
});
