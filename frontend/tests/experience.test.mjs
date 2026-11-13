import assert from "node:assert/strict";
import test from "node:test";
import { chapters } from "../src/features/experience/chapters.ts";
import { guideSteps } from "../src/features/experience/guide-steps.ts";

test("la historia conserva los siete capítulos y distingue evento de incidente", () => {
  assert.deepEqual(
    chapters.map(({ name }) => name),
    [
      "Observación",
      "Detección",
      "Seguimiento",
      "Contexto",
      "Reglas",
      "Evento",
      "Evidencia",
    ],
  );
  assert.match(
    chapters[5].description,
    /revisión humana.*no confirma un incidente/,
  );
});

test("la guía operacional adapta historial e indicadores al rol", () => {
  for (const kind of ["overview", "analysis"]) {
    const operator = guideSteps(kind, "operator");
    assert.ok(
      operator.every(
        ({ route }) =>
          !["/", "/events", "/indicators", "/users"].includes(route),
      ),
    );
    for (const role of ["administrator", "safety_lead"]) {
      const steps = guideSteps(kind, role);
      assert.ok(steps.some(({ target }) => target === "#evidence-title"));
      assert.ok(steps.every(({ route }) => route !== "/users"));
    }
  }
  assert.equal(guideSteps("analysis", "administrator").length, 10);
  assert.equal(guideSteps("overview", "operator").at(-1).route, "/account");
});
