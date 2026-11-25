"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { PageTitle } from "@/components/layout/page-title";
import { OperixScanLoader } from "@/components/ui/operix-scan-loader";
import { AutomaticCalibration } from "@/features/calibration/automatic-calibration";
import { operationalError } from "@/features/operations/operation-request";
import { cameraLabService, type CameraDocument, type RecordingConfiguration } from "@/services/camera-lab.service";
import { Configuration, type CameraDraft } from "./camera-lab";
import { MediaPreview } from "./camera-playlist-editor";
import { LoadError, useCameraData } from "./camera-overview";

export function CameraRecordingConfiguration({ id, media }: { id: string; media: string }) {
  const load = useCallback((signal: AbortSignal) => cameraLabService.recording(id, media, signal), [id, media]);
  const result = useCameraData(load, 0);
  const [draft, setDraft] = useState<CameraDraft>();
  const [demo, setDemo] = useState<boolean>();
  const [busy, setBusy] = useState(false);
  const [calibrating, setCalibrating] = useState(false);
  const [message, setMessage] = useState<{ text: string; error?: boolean }>();
  const camera = result.data;
  const locked = busy || calibrating;
  if (result.error) return <LoadError error={result.error} retry={result.retry} />;
  if (!camera) return <OperixScanLoader variant="panel" message="Consultando la configuración de la grabación…" />;
  const review = camera.recording_review;

  async function save(revision: number, document: CameraDocument) {
    if (locked) return false;
    setBusy(true);
    try {
      result.setData(await cameraLabService.saveRecording(id, media, { ...review, revision }, document, demo ?? review.demonstration));
      setDemo(undefined);
      setMessage({ text: "Revisión guardada. Se aplicará en la próxima ejecución de esta grabación." });
      return true;
    } catch (error) {
      setMessage({ text: operationalError(error), error: true });
      return false;
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid min-w-0 gap-4">
      <div>
        <Link href="/admin/camera-lab" className="text-sm underline">Volver a Control de cámaras</Link>
        <PageTitle>{camera.provenance.title || camera.provenance.filename}</PageTitle>
        <p className="text-sm text-text-secondary">
          {camera.name} · {review.state === "reviewed" ? `Revisión ${review.revision}` : "Sin revisión espacial"}
        </p>
      </div>
      <div className="grid min-w-0 gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="grid min-w-0 content-start gap-3">
          <MediaPreview media={{ ...camera.provenance, id: media }}
            zones={(draft?.document ?? camera.configuration)?.zones}
            aspect={camera.width && camera.height ? `${camera.width} / ${camera.height}` : undefined} />
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={demo ?? review.demonstration} disabled={locked}
              onChange={(event) => {
                setDemo(event.currentTarget.checked);
                if (!draft && camera.configuration) setDraft({ revision: review.revision, document: camera.configuration });
              }} />
            Demostración experimental
          </label>
          {review.state === "unreviewed" && camera.configuration && (
            <p className="text-sm text-text-secondary">
              Edita las zonas y reglas para preparar la grabación. Guarda la revisión para aplicarla al iniciar el siguiente análisis.
            </p>
          )}
          <AutomaticCalibration<RecordingConfiguration>
            key={review.source_sha256}
            source={{ kind: "cameras", id, recording: media, revision: review.revision }}
            zones={camera.configuration?.zones ?? []}
            saved={camera.configuration?.calibration}
            blocked={draft ? "Guarda o descarta el borrador antes de calibrar." : busy ? "Espera a que termine el guardado." : undefined}
            onSaved={result.setData}
            onBusyChange={setCalibrating}
            onRefresh={result.retry}
          />
        </div>
        <Configuration camera={camera} title="Configuración de la grabación" canEdit canConfigure editableRules busy={locked}
          draft={draft} setDraft={(value) => { setDraft(value); if (!value) setDemo(undefined); }}
          metricAvailable={camera.configuration?.calibration?.status === "valid"}
          message={message} onSave={save} />
      </div>
    </div>
  );
}
