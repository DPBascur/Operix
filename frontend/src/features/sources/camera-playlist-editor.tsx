"use client";

import { ArrowDown, ArrowUp, X } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { Toggle } from "@/components/ui/toggle";
import { VideoControls } from "@/features/analysis/video-controls";
import type {
  CameraControlUpdate,
  CameraMedia,
  CameraPlaylist,
  RecordingSummary,
  CameraDocument,
} from "@/services/camera-lab.service";
import { eventTypeName } from "@/services/event-contract";
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

function mediaLabel(media: CameraMedia, catalog: CameraMedia[] = []) {
  const title = media.title?.trim();
  if (title && !catalog.some((item) => item.id !== media.id && item.title?.trim() === title))
    return title;
  const scenario = media.scenario?.trim();
  if (scenario && !catalog.some((item) => item.id !== media.id && item.scenario?.trim() === scenario))
    return scenario;
  return mediaFilename(media);
}

function mediaUrl(id: string, asset: "video" | "thumbnail") {
  return `/api/v1/analysis/camera-media/${encodeURIComponent(id)}/${asset}/`;
}

function MediaThumbnail({ media }: { media: CameraMedia }) {
  return (
    // The source is same-origin and needs the user's session cookie.
    // eslint-disable-next-line @next/next/no-img-element
    <img src={mediaUrl(media.id, "thumbnail")} alt="" loading="lazy"
      width={320} height={180} className="aspect-video w-24 shrink-0 rounded-md bg-surface-muted object-cover sm:w-28" />
  );
}

export function MediaPreview({ media, zones, aspect = "16 / 9" }: {
  media: CameraMedia; zones?: CameraDocument["zones"]; aspect?: string;
}) {
  const video = useRef<HTMLVideoElement>(null);
  return (
    <div className="relative mx-auto w-full max-w-xl overflow-hidden rounded-lg bg-black">
      <video ref={video} src={mediaUrl(media.id, "video")} poster={mediaUrl(media.id, "thumbnail")}
        className="w-full object-contain" style={{ aspectRatio: aspect }}
        preload="metadata" playsInline aria-label={mediaLabel(media)} />
      {zones?.length ? <div className="pointer-events-none absolute inset-x-0 top-0" style={{ aspectRatio: aspect }}>
        <svg className="absolute inset-0 size-full" aria-hidden="true"
          viewBox="0 0 100 100" preserveAspectRatio="none">
          {zones.filter((zone) => zone.enabled !== false).map((zone) => (
            <polygon key={zone.zone_id} points={zone.polygon.map(([x, y]) => `${x * 100},${y * 100}`).join(" ")}
              fill="rgba(48,116,255,.16)" stroke="#81b5ff" vectorEffect="non-scaling-stroke" strokeWidth={2}>
              <title>{zone.name}</title>
            </polygon>
          ))}
        </svg>
      </div> : null}
      <VideoControls videoRef={video} />
    </div>
  );
}

export function CameraPlaylistEditor({
  cameraId,
  cameraName,
  catalog,
  saved,
  locked,
  save,
  feedback,
  configurations,
}: {
  cameraId: string;
  cameraName: string;
  catalog: CameraMedia[];
  saved: CameraPlaylist;
  locked: boolean;
  save: (change: CameraControlUpdate) => Promise<boolean>;
  feedback?: { text: string; error?: boolean };
  configurations?: Record<string, RecordingSummary>;
}) {
  const [selected, setSelected] = useState("");
  const [preview, setPreview] = useState("");
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
  function configurationLink(media: CameraMedia) {
    return `/sources/cameras/${encodeURIComponent(cameraId)}?recording=${encodeURIComponent(media.id)}`;
  }

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
      {playlist.media_ids.length ? (
        <ol className="divide-y divide-border">
          {playlist.media_ids.map((id, index) => {
            const media = byId.get(id);
            const reviewed = configurations?.[id];
            const filename = media ? mediaFilename(media) : "";
            const title = media ? mediaLabel(media, catalog) : "Video ya no permitido";
            const duration = cameraNumber(media?.duration_s, " s");
            const occurrence = occurrences.get(id) ?? 0;
            occurrences.set(id, occurrence + 1);
            const metadata = [media?.author, media?.license, duration, !media?.author ? filename : null]
              .filter(Boolean)
              .join(" · ");
            return (
              <li
                key={`${id}:${occurrence}`}
                className="flex flex-wrap items-center justify-between gap-2 py-2"
              >
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <span className="text-sm tabular-nums text-text-secondary">
                    {index + 1}.
                  </span>
                  {media && <MediaThumbnail media={media} />}
                  <div className="min-w-0 wrap-anywhere">
                    <p className="text-sm font-medium">{title}</p>
                    {metadata && (
                      <p className="text-sm text-text-secondary">{metadata}</p>
                    )}
                    {media?.scenario && media.scenario !== title && (
                      <p className="text-xs text-text-secondary">{media.scenario}</p>
                    )}
                    {media && <>
                      <p className="text-xs text-text-secondary">
                        {reviewed
                          ? `${reviewed.demonstration ? "Demostración" : "Revisada"} · v${reviewed.revision} · ${reviewed.zones} zonas · ${reviewed.calibration === "valid" ? "Calibración guardada" : "Sin calibración válida"}`
                          : "Sin revisión espacial"}
                      </p>
                      {reviewed && <p className="text-xs text-text-secondary">
                        {reviewed.rules.length ? reviewed.rules.map(eventTypeName).join(" · ") : "Sin reglas activas"}
                      </p>}
                      <Link href={configurationLink(media)} className="text-sm underline">Configurar grabación</Link>
                    </>}
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
              onChange={(event) => { setSelected(event.target.value); setPreview(""); }}
            >
              <option value="">Selecciona un video</option>
              {catalog.map((media) => (
                <option key={media.id} value={media.id}>
                  {mediaLabel(media, catalog)}
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
              setPreview("");
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
      {selection && (
        <div className="grid gap-2">
          <Link href={configurationLink(byId.get(selection)!)} className="w-fit text-sm underline">Configurar grabación seleccionada</Link>
          <Button variant="ghost" className="w-fit" aria-expanded={preview === selection}
            onClick={() => setPreview(preview === selection ? "" : selection)}>
            {preview === selection ? "Cerrar vista previa" : "Ver vista previa"}
          </Button>
          {preview === selection && <MediaPreview key={selection} media={byId.get(selection)!} />}
        </div>
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
