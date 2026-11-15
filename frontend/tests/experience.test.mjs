import assert from "node:assert/strict";
import test from "node:test";
import { chapters } from "../src/features/experience/chapters.ts";
import { guideSteps } from "../src/features/experience/guide-steps.ts";
import { positionGuide } from "../src/features/experience/guide-position.ts";

test("el panel aprovecha ambos lados y se separa del control en móvil", () => {
  const control = { top: 200, left: 250, width: 110, height: 44, radius: 22 };
  assert.equal(positionGuide(control, 330, 220, 1440, 900).left, 376);
  assert.equal(
    positionGuide({ ...control, left: 1290 }, 330, 220, 1440, 900).left,
    944,
  );
  assert.deepEqual(positionGuide(control, 336, 220, 390, 844), {
    left: 42,
    top: 260,
  });
  assert.deepEqual(
    positionGuide({ ...control, top: 750 }, 336, 220, 390, 844),
    { left: 42, top: 514 },
  );
  assert.equal(positionGuide(control, 336, 390, 390, 470), null);
});

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
      assert.ok(steps.some(({ target }) => target.includes("evidence-title")));
      assert.ok(steps.every(({ route }) => route !== "/users"));
    }
  }
  assert.equal(guideSteps("analysis", "administrator").length, 10);
  assert.equal(guideSteps("overview", "operator").at(-1).route, "/account");
});
