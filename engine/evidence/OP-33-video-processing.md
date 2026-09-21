# OP-33 — Procesamiento de video con OpenCV

Fecha de validación: 2026-09-10

Rama: `dev`

Requisito asociado: RF-01

## Alcance validado

- Apertura de archivos grabados mediante OpenCV.
- Obtención de resolución, FPS declarado, total declarado de frames y duración estimada.
- Lectura secuencial y conteo de frames procesados.
- Medición del tiempo total con `time.perf_counter()`.
- Liberación del recurso mediante context manager y `release()`.
- Errores controlados para rutas inexistentes y archivos no audiovisuales.
- Advertencias no fatales ante diferencias entre metadatos declarados y frames leídos.

No se incorporaron detección, YOLO11, ByteTrack, tracking, visualización ni streaming.

## Pruebas automatizadas

Comando:

```powershell
.\engine\.venv\Scripts\python.exe -m unittest discover -s .\engine\tests -v
```

Resultado:

```text
test_context_manager_releases_capture_after_exception ... ok
test_invalid_file_produces_controlled_error ... ok
test_missing_file_produces_controlled_error ... ok
test_processes_all_frames_and_reports_metadata ... ok

Ran 4 tests in 0.308s
OK
```

Las pruebas crean y eliminan automáticamente un AVI/MJPEG sintético de 64×48, 10 FPS y 12 frames. El archivo no se conserva ni se incorpora a Git.

## Ejecución manual con video real

Se utilizó una grabación local controlada de gameplay en formato MP4. La inspección previa confirmó que no contiene información empresarial ni documentación confidencial. El archivo permaneció fuera del repositorio y su ruta no se registra en esta evidencia.

Comando ejecutado:

```powershell
.\engine\.venv\Scripts\python.exe .\engine\scripts\process_video.py <video-real-local.mp4>
```

Resultado:

```text
Resolución: 1920x1080
FPS declarado: 60.00
Frames declarados: 3179
Duración estimada (s): 52.98
Frames procesados: 3178
Tiempo de procesamiento (s): 19.486
Advertencia: El total de frames procesados difiere del valor declarado por OpenCV
             (3178 procesados, 3179 declarados).
```

La diferencia de un frame fue informada sin tratarla como error fatal. El archivo se recorrió hasta que el backend indicó el fin de lectura y la ejecución terminó con código de salida cero.

## Trazabilidad

| Elemento | Ubicación |
| --- | --- |
| Implementación | `engine/src/operix_engine/video_processor.py` |
| CLI manual | `engine/scripts/process_video.py` |
| Pruebas reproducibles | `engine/tests/test_video_processor.py` |
| Evidencia | `engine/evidence/OP-33-video-processing.md` |
