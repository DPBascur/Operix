import { AnalysisRequestError } from "@/services/analysis.service";

export function analysisError(cause: unknown, fallback: string): string {
  const detail =
    cause instanceof Error
      ? cause.message
      : typeof cause === "string"
        ? cause
        : "";
  if (cause instanceof AnalysisRequestError) {
    if (cause.status === 401 || cause.status === 403)
      return "El acceso a Análisis requiere una sesión válida. Vuelve a iniciar sesión.";
    if (cause.status >= 500)
      return "El servicio de análisis no pudo responder. Vuelve a intentarlo.";
  }
  if (/timeout|timed out|aborted|signal is aborted/i.test(detail))
    return "El servicio tardó demasiado. Revisa la conexión y vuelve a intentarlo.";
  if (/failed to fetch|networkerror|load failed/i.test(detail))
    return "No hay conexión con el servicio de análisis. Comprueba la conexión y reintenta.";
  if (/video no coincide con el SHA-256/i.test(detail))
    return "El archivo elegido corresponde a otra fuente. Selecciona el video original de la revisión.";
  if (/sesi[oó]n (inexistente|expirada|no encontrada)/i.test(detail))
    return "La sesión de análisis ya no está disponible. Selecciona una fuente para preparar otra.";
  if (
    /no existe.*(demo|video|archivo)|(demo|video|archivo).*(no existe|no encontrado|inexistente)|no such file|archivo.*no est[aá] disponible/i.test(
      detail,
    )
  )
    return "El archivo de la fuente no está disponible. Selecciona otra fuente de video.";
  if (
    /decodific|cv2|could not open video|no se pudo (abrir|leer) el video/i.test(
      detail,
    )
  )
    return "No se pudo leer el video. Prueba otro archivo o exporta el original como MP4 con H.264.";
  if (
    /formato.*(v[aá]lido|permitido|compatible|soportado)|cabecera de video|fuente demo no corresponde|extensi[oó]n/i.test(
      detail,
    )
  )
    return "La fuente es incompatible con el perfil o el formato admitido. Selecciona otro video.";
  if (
    !detail ||
    detail.length > 260 ||
    /[<>]|traceback|stack trace|exception:|(?:[a-z]:[\\/]|\/(?:app|tmp|home|usr)\/)|^\s*[\[{]/i.test(
      detail,
    )
  )
    return fallback;
  return detail;
}
