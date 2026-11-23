import assert from "node:assert/strict";
import test from "node:test";
import {
  changeEventHistoryMode,
  eventHistoryHref,
  eventHistoryParams,
  parseEventHistory,
} from "../src/features/events/event-history-query.ts";

test("links retain history filters, paging and display mode", () => {
  const query = parseEventHistory(
    new URLSearchParams({
      camera_id: "lab-cam-07",
      occurred_after: "2026-10-13T09:00:00-03:00",
      occurred_before: "2026-10-15T00:00:00Z",
      event_type: "zone_dwell",
      zone_id: "Zona A",
      source_kind: "lab",
      source_sha256: "a".repeat(64),
      evidence_stage: "finished",
      search: " Pasillo & zona ",
      order: "oldest",
      page: "3",
      view: "all",
    }),
  );
  assert.equal(query.filters.search, "Pasillo & zona");
  assert.equal(query.page, 3);
  assert.deepEqual(parseEventHistory(eventHistoryParams(query)), query);

  const api = eventHistoryParams(query, true);
  assert.equal(api.get("page_size"), "60");
  assert.equal(api.get("page"), "3");
  assert.equal(api.has("view"), false);
  const back = new URLSearchParams({ back: eventHistoryHref(query) }).get(
    "back",
  );
  assert.deepEqual(
    parseEventHistory(new URL(back, "http://localhost").searchParams),
    query,
  );
});

test("defaults to 15 and disregards invalid or unsafe deep-link values", () => {
  const query = parseEventHistory(
    new URLSearchParams(
      "page=9007199254740992&view=bad&camera_id=bad&occurred_after=2026-10-13&evidence_stage=bad",
    ),
  );
  assert.equal(eventHistoryHref(query), "/events");
  assert.equal(eventHistoryParams(query, true).toString(), "page=1");
  assert.equal(query.all, false);
});

test("switching display mode keeps the first visible result within range", () => {
  const query = { filters: { cameraId: "lab-cam-07" }, page: 7, all: false };
  const all = changeEventHistoryMode(query);
  assert.deepEqual(all, { ...query, page: 2, all: true });
  assert.deepEqual(changeEventHistoryMode(all), { ...query, page: 5 });
});
