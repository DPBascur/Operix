"use client";

import { ArrowDown, ArrowUp, X } from "lucide-react";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Toggle } from "@/components/ui/toggle";
import type {
  CameraControlUpdate,
  CameraMedia,
  CameraPlaylist,
} from "@/services/camera-lab.service";
import { cameraNumber } from "./camera-diagnostics";
import {
  movePlaylistMedia,
  maxCameraPlaylistItems,
  playlistUpdate,
  samePlaylist,
} from "./camera-playlist";

function mediaFilename(media: CameraMedia) {
  return media.filename.split(/[\\/]/).at(-1) || "Video";
}

function mediaLabel(media: CameraMedia) {
  return media.scenario?.trim() || mediaFilename(media);
}

export function CameraPlaylistEditor({
  cameraId,
  cameraName,
  catalog,
  saved,
  locked,
  save,
  feedback,
}: {
  cameraId: string;
  cameraName: string;
  catalog: CameraMedia[];
  saved: CameraPlaylist;
  locked: boolean;
  save: (change: CameraControlUpdate) => Promise<boolean>;
  feedback?: { text: string; error?: boolean };
}) {
  const [selected, setSelected] = useState("");
  const [edit, setEdit] = useState<{
    base: CameraPlaylist;
    playlist: CameraPlaylist;
  }>();
  const playlist = edit?.playlist ?? saved;
  const changed = !samePlaylist(playlist, saved);
  const conflict = changed && !!edit && !samePlaylist(edit.base, saved);
  const update = playlistUpdate(cameraId, playlist, catalog);
  const byId = new Map(catalog.map((media) => [media.id, media]));
  const selection = byId.has(selected) ? selected : "";
  const atLimit = playlist.media_ids.length >= maxCameraPlaylistItems;
  const occurrences = new Map<string, number>();

  function editPlaylist(next: CameraPlaylist) {
    setEdit(
      samePlaylist(next, saved)
        ? undefined
        : { base: edit?.base ?? saved, playlist: next },
    );
  }

  async function submit() {
    if (!locked && changed && !conflict && update && (await save(update))) {
      setEdit(undefined);
      setSelected("");
    }
  }

  return (
    <form
      className="grid min-w-0 gap-3 border-t border-border pt-3"
      aria-label={`Lista de reproducción de ${cameraName}`}
      onSubmit={(event) => {
        event.preventDefault();
        void submit();
      }}
    >
      <h4 className="font-semibold">Lista de reproducción</h4>
      {playlist.media_ids.length ? (
        <ol className="divide-y divide-border">
          {playlist.media_ids.map((id, index) => {
            const media = byId.get(id);
            const filename = media ? mediaFilename(media) : "";
            const title = media ? mediaLabel(media) : "Video ya no permitido";
            const duration = cameraNumber(media?.duration_s, " s");
            const occurrence = occurrences.get(id) ?? 0;
            occurrences.set(id, occurrence + 1);
            const metadata = [filename !== title ? filename : null, duration]
              .filter(Boolean)
              .join(" · ");
            return (
              <li
                key={`${id}:${occurrence}`}
                className="flex flex-wrap items-center justify-between gap-2 py-2"
              >
                <div className="flex min-w-0 flex-1 items-baseline gap-2">
                  <span className="text-sm tabular-nums text-text-secondary">
                    {index + 1}.
                  </span>
                  <div className="min-w-0 wrap-anywhere">
                    <p className="text-sm font-medium">{title}</p>
                    {metadata && (
                      <p className="text-sm text-text-secondary">{metadata}</p>
                    )}
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Subir ${title} (posición ${index + 1})`}
                    disabled={locked || conflict || index === 0}
                    onClick={() =>
                      editPlaylist({
                        ...playlist,
                        media_ids: movePlaylistMedia(
                          playlist.media_ids,
                          index,
                          -1,
                        ),
                      })
                    }
                  >
                    <ArrowUp size={16} aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Bajar ${title} (posición ${index + 1})`}
                    disabled={
                      locked ||
                      conflict ||
                      index === playlist.media_ids.length - 1
                    }
                    onClick={() =>
                      editPlaylist({
                        ...playlist,
                        media_ids: movePlaylistMedia(
                          playlist.media_ids,
                          index,
                          1,
                        ),
                      })
                    }
                  >
                    <ArrowDown size={16} aria-hidden="true" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label={`Quitar ${title} (posición ${index + 1})`}
                    disabled={locked || conflict}
                    onClick={() =>
                      editPlaylist({
                        ...playlist,
                        media_ids: playlist.media_ids.filter(
                          (_, position) => position !== index,
                        ),
                      })
                    }
                  >
                    <X size={16} aria-hidden="true" />
                  </Button>
                </div>
              </li>
            );
          })}
        </ol>
      ) : (
        <p className="text-sm text-text-secondary">La lista está vacía.</p>
      )}
      {catalog.length && !atLimit ? (
        <div className="flex flex-wrap items-end gap-2">
          <label className="grid min-w-0 flex-1 gap-1 text-sm">
            Video permitido
            <select
              className="input w-full min-w-0"
              disabled={locked || conflict}
              value={selection}
              onChange={(event) => setSelected(event.target.value)}
            >
              <option value="">Selecciona un video</option>
              {catalog.map((media) => (
                <option key={media.id} value={media.id}>
                  {mediaLabel(media)}
                </option>
              ))}
            </select>
          </label>
          <Button
            variant="outline"
            disabled={locked || conflict || !selection}
            onClick={() => {
              editPlaylist({
                ...playlist,
                media_ids: [...playlist.media_ids, selection],
              });
              setSelected("");
            }}
          >
            Añadir
          </Button>
        </div>
      ) : (
        <p className="text-sm text-text-secondary">
          {atLimit
            ? `La lista admite hasta ${maxCameraPlaylistItems} videos.`
            : "El catálogo no tiene videos permitidos para esta cámara."}
        </p>
      )}
      <label className="flex w-fit items-center gap-2 text-sm">
        <Toggle
          checked={playlist.repeat}
          disabled={locked || conflict}
          onChange={(event) =>
            editPlaylist({ ...playlist, repeat: event.target.checked })
          }
        />
        Repetir lista
      </label>
      {conflict ? (
        <p role="status" className="text-sm text-danger">
          La lista cambió en el servidor. Descarta el borrador para ver la
          versión actual.
        </p>
      ) : (
        !update &&
        playlist.media_ids.some((id) => !byId.has(id)) && (
          <p role="status" className="text-sm text-danger">
            Quita los videos que ya no están permitidos para guardar.
          </p>
        )
      )}
      <div className="flex flex-wrap items-center gap-2">
        <Button
          type="submit"
          disabled={locked || !changed || conflict || !update}
        >
          Guardar lista
        </Button>
        {changed && (
          <Button
            variant="ghost"
            disabled={locked}
            onClick={() => {
              setEdit(undefined);
              setSelected("");
            }}
          >
            Descartar cambios
          </Button>
        )}
      </div>
      {feedback && (
        <p
          className={
            feedback.error
              ? "text-sm text-danger"
              : "text-sm text-text-secondary"
          }
          role={feedback.error ? "alert" : "status"}
        >
          {feedback.text}
        </p>
      )}
    </form>
  );
}
