type Metrics = Record<string, unknown> | null | undefined;

const numberFormat = new Intl.NumberFormat("es-CL", {
  maximumFractionDigits: 2,
});
const percentFormat = new Intl.NumberFormat("es-CL", {
  style: "percent",
  maximumFractionDigits: 2,
});
const cameraTimeFormat = new Intl.DateTimeFormat("es-CL", {
  dateStyle: "medium",
  timeStyle: "medium",
  timeZone: "America/Santiago",
  hourCycle: "h23",
});

export function cameraNumber(value: unknown, unit = "") {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
    ? `${numberFormat.format(value)}${unit}`
    : null;
}

export function cameraCoverage(metrics: Metrics) {
  const fraction = metrics?.observed_fraction_5s;
  return typeof fraction === "number" && fraction >= 0 && fraction <= 1
    ? percentFormat.format(fraction)
    : null;
}

export function cameraObservationPaused(status: string, stale: boolean) {
  return stale || status === "no_signal" || status === "reconnecting";
}

export function cameraAnalysisRate(metrics: Metrics) {
  const recent = cameraNumber(metrics?.analysis_fps_5s, " FPS");
  const legacy =
    cameraNumber(metrics?.analysis_fps, " FPS") ??
    cameraNumber(metrics?.effective_fps, " FPS");
  return recent === null && legacy !== null
    ? { label: "Ritmo medio de análisis de la ejecución", value: legacy }
    : { label: "Ritmo de análisis (5 s)", value: recent };
}

export function cameraFrameTime(timestamp: string | null | undefined) {
  const ms = timestamp ? Date.parse(timestamp) : NaN;
  return Number.isFinite(ms)
    ? `${cameraTimeFormat.format(ms)} · hora de Chile`
    : null;
}

export function cameraFrameIsRecent(
  timestamp: string | null | undefined,
  metrics: Metrics,
  receivedAt: number,
) {
  const maxAge = 5000;
  const age = metrics?.last_frame_age_ms;
  if (typeof age === "number" && Number.isFinite(age) && age >= 0)
    return age < maxAge;

  const elapsed = receivedAt - (timestamp ? Date.parse(timestamp) : NaN);
  return elapsed >= 0 && elapsed < maxAge;
}

function metricRecord(value: unknown) {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

export function cameraTechnicalMetrics(metrics: Metrics) {
  const counters = metricRecord(metrics?.capture);
  const inferenceDrops = metricRecord(metrics?.inference_drops);
  const batchSizes = metricRecord(metrics?.inference_batch_sizes);
  const mode = metrics?.inference_mode;
  const staged = metrics?.registration_attempts !== undefined;

  const groups: { title: string; rows: [string, string | null][] }[] = [
    {
      title: "Captura local",
      rows: [
        [
          "Recepción tras decodificar",
          cameraNumber(metrics?.received_fps, " FPS"),
        ],
        ["Fotogramas decodificados", cameraNumber(counters?.decoded)],
        [
          "Lectura RTSP, incluida la espera (p95)",
          cameraNumber(metrics?.p95_capture_read_wall_ms, " ms"),
        ],
        ["Descartes por cola llena", cameraNumber(counters?.queue_drop)],
        ["Descartes por antigüedad", cameraNumber(counters?.expired_drop)],
        ["Descartes al desconectar", cameraNumber(counters?.disconnect_drop)],
        ["Descartes al detener", cameraNumber(counters?.shutdown_drop)],
        ["Fotogramas en cola", cameraNumber(metrics?.queue_depth)],
        ["Máximo observado en cola", cameraNumber(metrics?.max_queue_depth)],
        ["Conexiones abiertas", cameraNumber(counters?.connections)],
        ["Fallos de apertura", cameraNumber(counters?.open_failure)],
        ["Fallos de lectura", cameraNumber(counters?.read_failure)],
      ],
    },
    {
      title: "Procesamiento local (p95)",
      rows: [
        [
          "Espera en cola de captura",
          cameraNumber(metrics?.p95_queue_age_ms, " ms"),
        ],
        [
          "Recepción a resultado",
          cameraNumber(metrics?.p95_arrival_to_result_ms, " ms"),
        ],
        ["Generación JPEG", cameraNumber(metrics?.p95_jpeg_ms, " ms")],
        ["Seguimiento", cameraNumber(metrics?.p95_tracking_ms, " ms")],
        [
          "Verificación de encuadre",
          cameraNumber(metrics?.p95_spatial_guard_ms, " ms"),
        ],
        ["Geometría", cameraNumber(metrics?.p95_geometry_ms, " ms")],
        [
          "Evaluación de reglas",
          cameraNumber(metrics?.p95_rule_evaluation_ms, " ms"),
        ],
        [
          "Dibujo de anotaciones",
          cameraNumber(metrics?.p95_overlays_ms, " ms"),
        ],
        ["Generación PNG", cameraNumber(metrics?.p95_png_ms, " ms")],
        [
          "Publicación",
          staged ? null : cameraNumber(metrics?.p95_publication_ms, " ms"),
        ],
        ["Generación de clip", cameraNumber(metrics?.p95_clip_ms, " ms")],
        [
          "Recepción a publicación",
          staged
            ? null
            : cameraNumber(metrics?.p95_arrival_to_publication_ms, " ms"),
        ],
      ],
    },
    {
      title: "Registro y evidencia",
      rows: [
        [
          "Recepción local a registro p95",
          cameraNumber(metrics?.p95_arrival_to_registration_ms, " ms"),
        ],
        [
          "Recepción local a PNG p95",
          cameraNumber(metrics?.p95_arrival_to_png_ms, " ms"),
        ],
        [
          "Recepción local a clip p95",
          cameraNumber(metrics?.p95_arrival_to_clip_ms, " ms"),
        ],
        [
          "Eventos omitidos por saturación",
          cameraNumber(metrics?.events_skipped_backpressure),
        ],
        [
          "Eventos omitidos por límite de sesión",
          cameraNumber(metrics?.events_skipped_quota),
        ],
        ["Registros fallidos", cameraNumber(metrics?.events_failed)],
        ["PNG fallidos", cameraNumber(metrics?.evidence_failed)],
        ["Clips fallidos", cameraNumber(metrics?.clips_failed)],
        [
          "Clips sin espacio disponible",
          cameraNumber(metrics?.clips_disk_limit),
        ],
      ],
    },
    {
      title: "Inferencia",
      rows: [
        [
          "Modo",
          mode === "dedicated"
            ? "Dedicada"
            : mode === "shared"
              ? "Compartida"
              : null,
        ],
        [
          "Espera en cola p95",
          cameraNumber(metrics?.p95_inference_queue_ms, " ms"),
        ],
        [
          "Solicitud al Motor p95",
          cameraNumber(metrics?.p95_inference_request_ms, " ms"),
        ],
        ["Lote PERSON p95", cameraNumber(metrics?.p95_person_batch_ms, " ms")],
        [
          "Lote FORKLIFT p95",
          cameraNumber(metrics?.p95_forklift_batch_ms, " ms"),
        ],
        [
          "Detector PERSON p95",
          cameraNumber(metrics?.p95_person_detector_ms, " ms"),
        ],
        [
          "Detector FORKLIFT p95",
          cameraNumber(metrics?.p95_forklift_detector_ms, " ms"),
        ],
        ...[1, 2, 3, 4].map<[string, string | null]>((size) => [
          `Resultados de esta cámara en lotes de ${size}`,
          cameraNumber(batchSizes?.[size]),
        ]),
        [
          "Descartes en inferencia",
          cameraNumber(metrics?.frames_inference_dropped),
        ],
        ["Servicio ocupado", cameraNumber(inferenceDrops?.busy)],
        ["Plazo de inferencia vencido", cameraNumber(inferenceDrops?.deadline)],
        ["Fallo de inferencia", cameraNumber(inferenceDrops?.failed)],
        [
          "Detención durante inferencia",
          cameraNumber(inferenceDrops?.shutdown),
        ],
        [
          "Desconexión durante inferencia",
          cameraNumber(inferenceDrops?.disconnect),
        ],
      ],
    },
    {
      title: "Totales de la ejecución",
      rows: [
        ["Fotogramas analizados", cameraNumber(metrics?.frames_processed)],
        ["Fotogramas descartados", cameraNumber(metrics?.frames_dropped)],
        ["Tramos de observación", cameraNumber(metrics?.epoch)],
        [
          "Saltos con seguimiento conservado",
          cameraNumber(metrics?.tracking_preserved_gaps),
        ],
        ["Eventos publicados", cameraNumber(metrics?.events_published)],
      ],
    },
  ];

  return groups
    .map(({ title, rows }) => ({
      title,
      rows: rows.filter((row): row is [string, string] => row[1] !== null),
    }))
    .filter(({ rows }) => rows.length > 0);
}
