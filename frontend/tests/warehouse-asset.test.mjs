import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const asset = new URL("../public/experience/warehouse.glb", import.meta.url);

test("la bodega 3D cabe en el presupuesto de descarga y es autoalojable", () => {
  const glb = readFileSync(asset);
  assert.equal(glb.toString("ascii", 0, 4), "glTF");
  assert.equal(glb.readUInt32LE(4), 2);
  assert.equal(glb.readUInt32LE(8), glb.length);
  assert.ok(glb.length < 1.5 * 1024 ** 2);
  const model = JSON.parse(glb.toString("utf8", 20, 20 + glb.readUInt32LE(12)));
  assert.ok(model.extensionsUsed.includes("EXT_meshopt_compression"));
  assert.ok(
    [...(model.images ?? []), ...model.buffers].every((value) => !value.uri),
  );
  const names = new Set(model.nodes.map((value) => value.name));
  for (const name of [
    "Warehouse",
    "SecurityCamera",
    "Worker",
    "Forklift",
    "LegL",
    "LegR",
    "ArmL",
    "ArmR",
    "Wheel0L",
    "Wheel0R",
    "Wheel1L",
    "Wheel1R",
  ]) {
    assert.ok(names.has(name), `Nodo ausente: ${name}`);
  }
});
