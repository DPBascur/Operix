import assert from "node:assert/strict";
import test from "node:test";
import {
  parseHistory,
  summarizeHistory,
  formatHistoryTime,
  historyError,
  monthUtcBounds,
  parseFrequency,
  summarizeApiHistory,
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

test("OP-41 usa límites UTC inclusivos sin perder fracciones del último segundo", () => {
  assert.deepEqual(monthUtcBounds("2026-10"), {
    start: "2026-10-01T00:00:00.000Z",
    previous: "2026-09-01T00:00:00.000Z",
    end: "2026-10-31T23:59:59.999999Z",
  });
  assert.equal(monthUtcBounds("2026-02").end, "2026-02-28T23:59:59.999999Z");
  assert.throws(() => monthUtcBounds("2026-13"));
});

test("OP-41 reconcilia agregados API con eventos del período", () => {
  const events = [
    event("1", "2026-10-01T00:00:00Z"),
    event("2", "2026-10-31T23:59:59Z"),
  ];
  const current = parseFrequency({
    total: 2,
    timezone: "UTC",
    period: "day",
    by_period: [
      { date: "2026-10-01", count: 1 },
      { date: "2026-10-31", count: 1 },
    ],
    by_type: [{ event_type: "zone_dwell", count: 2 }],
  });
  const previous = parseFrequency({
    total: 1,
    timezone: "UTC",
    period: "day",
    by_period: [{ date: "2026-09-30", count: 1 }],
    by_type: [{ event_type: "zone_dwell", count: 1 }],
  });
  const summary = summarizeApiHistory(events, "2026-10", current, previous);
  assert.equal(summary.total, 2);
  assert.equal(summary.previousCount, 1);
  assert.equal(summary.change, 100);
  assert.equal(summary.days[30].count, 1);
  assert.deepEqual(summary.types, [{ label: "zone_dwell", count: 2 }]);
  assert.throws(
    () => summarizeApiHistory([], "2026-10", current, previous),
    /reconciliar/,
  );
});

test("OP-41 vacío no fabrica días, tipos ni porcentaje de comparación", () => {
  const empty = parseFrequency({
    total: 0,
    timezone: "UTC",
    period: "day",
    by_period: [],
    by_type: [],
  });
  const summary = summarizeApiHistory([], "2026-10", empty, empty);
  assert.equal(summary.total, 0);
  assert.equal(summary.change, null);
  assert.deepEqual(summary.types, []);
  assert.equal(
    summary.days.reduce((total, day) => total + day.count, 0),
    0,
  );
  assert.throws(() => parseFrequency({ ...empty, total: 1 }), /coinciden/);
  assert.throws(
    () => parseFrequency({ ...empty, timezone: "America/Santiago" }),
    /válidas/,
  );
});
