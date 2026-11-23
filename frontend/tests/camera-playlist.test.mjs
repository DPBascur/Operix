import assert from "node:assert/strict";
import test from "node:test";
import {
  cameraMediaForRate,
  emptyPlaylist,
  movePlaylistMedia,
  playlistUpdate,
  samePlaylist,
} from "../src/features/sources/camera-playlist.ts";

test("camera playlist order and repeat participate in change detection", () => {
  const ids = ["a", "b", "c"];
  const ordered = movePlaylistMedia(ids, 1, -1);
  assert.deepEqual(ordered, ["b", "a", "c"]);
  assert.deepEqual(ids, ["a", "b", "c"]);
  assert.equal(movePlaylistMedia(ids, 0, -1), ids);
  assert.equal(movePlaylistMedia(ids, 2, 1), ids);
  const saved = { media_ids: ids, repeat: false };
  assert.equal(samePlaylist(saved, { ...saved, media_ids: [...ids] }), true);
  assert.equal(samePlaylist(saved, { ...saved, media_ids: ordered }), false);
  assert.equal(samePlaylist(saved, { ...saved, repeat: true }), false);
  assert.equal(samePlaylist(saved, emptyPlaylist), false);
});

test("playlist updates serialize only the selected camera, permitted IDs and repeat", () => {
  const catalog = [
    { id: "a", filename: "a.mp4" },
    { id: "b", filename: "b.mp4" },
  ];
  const playlist = {
    media_ids: ["b", "a"],
    repeat: true,
    filename: "ignored.mp4",
  };
  assert.deepEqual(playlistUpdate("cam-1", playlist, catalog), {
    playlists: { "cam-1": { media_ids: ["b", "a"], repeat: true } },
  });
  assert.equal(
    playlistUpdate("cam-1", { ...playlist, media_ids: ["a.mp4"] }, catalog),
    null,
  );
  assert.equal(playlistUpdate("cam-1", playlist, catalog.slice(0, 1)), null);
  assert.deepEqual(playlistUpdate("cam-1", emptyPlaylist, []), {
    playlists: { "cam-1": { media_ids: [], repeat: false } },
  });
  assert.deepEqual(
    playlistUpdate(
      "cam-1",
      { media_ids: ["a", "b", "a"], repeat: false },
      catalog,
    ),
    { playlists: { "cam-1": { media_ids: ["a", "b", "a"], repeat: false } } },
  );
  assert.equal(
    playlistUpdate(
      "cam-1",
      { media_ids: Array(65).fill("a"), repeat: false },
      catalog,
    ),
    null,
  );
});

test("camera media honor the capture FPS when both rates are supplied", () => {
  const slow = { id: "slow", filename: "slow.mp4", fps: 12 };
  const matching = { id: "match", filename: "match.mp4", fps: 15 };
  const legacy = { id: "legacy", filename: "legacy.mp4" };
  const catalog = [slow, matching, legacy];
  assert.deepEqual(cameraMediaForRate(catalog, 15), [matching, legacy]);
  assert.deepEqual(cameraMediaForRate(catalog), catalog);
});
