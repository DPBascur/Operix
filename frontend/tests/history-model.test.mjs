import assert from "node:assert/strict";
import test from "node:test";
import {
  parseHistory,
  summarizeHistory,
  formatHistoryTime,
  historyError,
} from "../src/features/dashboard/history-model.ts";
test("errores de conexión, timeout y JSON usan mensajes recuperables", () => {
  assert.match(
    historyError(new TypeError("Failed to fetch")),
    /Revise el servicio/,
  );
  assert.match(
    historyError(new DOMException("aborted", "AbortError")),
    /tardó demasiado/,
  );
  assert.match(
    historyError(new SyntaxError("JSON token")),
    /respuesta inválida/,
  );
});
import { historyDemo } from "../src/services/demo/history-demo.ts";
const event = (id, date, zone = "A") => ({
  id,
  occurred_at: date,
  event_type: "zone_dwell",
  zone_id: zone,
});
test("formato UTC no depende de locale ni introduce espacios ICU", () => {
  assert.equal(formatHistoryTime("2026-10-23T12:56:00Z"), "23/10 · 12:56 UTC");
  assert.equal(
    formatHistoryTime("2026-10-01T00:00:00-03:00"),
    "01/10 · 03:00 UTC",
  );
});
test("conteos del ejemplo coinciden con un conteo independiente", () => {
  const s = summarizeHistory(historyDemo, "2026-10");
  assert.equal(s.total, 64);
  assert.equal(s.previousCount, 82);
  assert.equal(
    s.days.reduce((a, d) => a + d.count, 0),
    64,
  );
  assert.equal(
    s.hours.reduce((a, d) => a + d.count, 0),
    64,
  );
  assert.equal(
    s.zones.reduce((a, d) => a + d.count, 0),
    64,
  );
  assert.equal(
    s.types.reduce((a, d) => a + d.count, 0),
    64,
  );
});
test("límites mensuales y zona horaria se interpretan en UTC", () => {
  const data = [
    event("1", "2026-10-01T00:00:00Z"),
    event("2", "2026-10-31T23:59:59Z"),
    event("3", "2026-11-01T00:00:00Z"),
    event("4", "2026-09-30T23:00:00-03:00"),
  ];
  assert.equal(summarizeHistory(data, "2026-10").total, 3);
});
test("vacío no inventa porcentaje ni zona de mayor recurrencia", () => {
  const s = summarizeHistory([], "2026-02");
  assert.equal(s.total, 0);
  assert.equal(s.change, null);
  assert.equal(s.days.length, 28);
  assert.deepEqual(s.zones, []);
});
test("rechaza payload inválido y deduplica identidad de registros", () => {
  assert.throws(() => parseHistory({ results: [] }));
  assert.throws(() => parseHistory([event("1", "invalid")]));
  const e = event("1", "2026-10-02T00:00:00Z");
  assert.equal(parseHistory([e, e]).length, 1);
});
test("ordena actividad, conserva meses e impide períodos inválidos", () => {
  assert.throws(() => summarizeHistory([], "2026-13"));
  const s = summarizeHistory(
    [event("a", "2026-10-02T00:00:00Z"), event("b", "2026-10-03T00:00:00Z")],
    "2026-10",
  );
  assert.equal(s.recent[0].id, "b");
  assert.equal(s.days.length, 31);
});
