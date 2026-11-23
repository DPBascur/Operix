import type {
  CameraMedia,
  CameraPlaylist,
} from "../../services/camera-lab.service";

export const emptyPlaylist: CameraPlaylist = { media_ids: [], repeat: false };
export const maxCameraPlaylistItems = 64;

export function cameraMediaForRate(
  catalog: CameraMedia[],
  expectedFps?: number | null,
) {
  return catalog.filter(
    ({ fps }) => fps == null || expectedFps == null || fps >= expectedFps,
  );
}

export function samePlaylist(left: CameraPlaylist, right: CameraPlaylist) {
  return (
    left.repeat === right.repeat &&
    left.media_ids.length === right.media_ids.length &&
    left.media_ids.every((id, index) => id === right.media_ids[index])
  );
}

export function movePlaylistMedia(ids: string[], from: number, step: -1 | 1) {
  const to = from + step;
  if (from < 0 || from >= ids.length || to < 0 || to >= ids.length) return ids;
  const ordered = [...ids];
  [ordered[from], ordered[to]] = [ordered[to], ordered[from]];
  return ordered;
}

export function playlistUpdate(
  cameraId: string,
  playlist: CameraPlaylist,
  catalog: readonly CameraMedia[],
) {
  const permitted = new Set(catalog.map(({ id }) => id));
  if (
    playlist.media_ids.length > maxCameraPlaylistItems ||
    !playlist.media_ids.every((id) => permitted.has(id))
  )
    return null;
  return {
    playlists: {
      [cameraId]: {
        media_ids: [...playlist.media_ids],
        repeat: playlist.repeat,
      },
    },
  };
}
