# Prueba local integrada: video a evento persistido

Esta prueba exploratoria une los componentes existentes del Motor con la API de
desarrollo. No modifica la arquitectura v1.0 ni cierra formalmente OP-39.

## Fuente y configuración

- Fuente: `assets/demo/warehouse_fire_ceiling04.mp4`, muestra sintética NVIDIA
  PhysicalAI WorldModel Synthetic Warehouse Operations Scenes (OpenMDW-1.1).
  SHA-256: `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`.
- Video: 277 frames, 1920×1080, 30 FPS, 9,233 s.
- Modelo: `yolo11n.pt` oficial, externo a Git, 5.613.764 bytes,
  SHA-256 `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`.
- Detección: CUDA, `imgsz=640`, confianza 0,10, IoU 0,70, solo `person`.
- ByteTrack: high 0,25; low 0,10; new 0,25; buffer 30; match 0,80;
  `fuse_score=true`.
- Configuración: [`desktop-zone-dwell.json`](../config/examples/desktop-zone-dwell.json),
  zona normalizada `area_transito_demo` sobre el área de tránsito visible.
  `min_duration_s=2,0` es un parámetro experimental de demostración, no un
  umbral de seguridad ni una evaluación de riesgo.
- GPU: NVIDIA GeForce RTX 3070; Windows 10 x64; Python 3.12.10;
  PyTorch 2.14.0+cu130; Ultralytics 8.4.146; OpenCV 5.0.0.93;
  `lap==0.5.12`. Backend local: Django 5.2.18, PostgreSQL 17.11.
- La fecha `--recording-start-at` se usa solo como **ancla temporal explícita
  de análisis** para el video sintético. No se conoce ni se afirma la fecha
  real de captura de la escena.

## Ejecución

Con PostgreSQL y Django activos solo en localhost, desde la raíz del
repositorio en PowerShell:

```powershell
$weights = '<ruta externa al repositorio>/yolo11n.pt'
$runId = [guid]::NewGuid().ToString()
$start = [DateTimeOffset]::UtcNow.ToString('yyyy-MM-ddTHH:mm:ssZ')
engine/.venv/Scripts/python.exe engine/scripts/process_video_events.py `
  assets/demo/warehouse_fire_ceiling04.mp4 `
  --weights $weights `
  --config engine/config/examples/desktop-zone-dwell.json `
  --expected-video-sha256 3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6 `
  --expected-weights-sha256 0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1 `
  --analysis-run-id $runId --recording-start-at $start `
  --api-base-url http://127.0.0.1:8000/api/v1 `
  --conf 0.10 --imgsz 640 --iou 0.70
```

El flujo parte del MP4: OpenCV → YOLO11n → filtro `person` → ByteTrack →
`SpatiotemporalAnalyzer` → `RuleEngine` → `EventCandidate` → PNG anotado del
**mismo frame real** → `HttpEventSink` → Django/DRF → PostgreSQL y medios
locales → consulta `/events`. No se reutiliza un JSONL de tracks. El orquestador
recorta al área visible siete cajas de ByteTrack que excedían ligeramente el
frame antes del análisis geométrico; no descartó ninguna observación completa
fuera de imagen. El detector y el tracker no se modificaron.

## Resultado de la corrida completa

- `analysis_run_id`: `4e29218e-7dd6-4e11-aba8-1df4be244188`.
- Salida: código 0; 277/277 frames; 1.088 detecciones `person`;
  644 observaciones de tracking; 8 IDs temporales.
- Tiempo de procesamiento (sin carga inicial del modelo): 7,836 s;
  FPS efectivo de esta corrida: 35,351. Incluye inferencia, análisis,
  render de cuatro capturas y publicación HTTP; no es un benchmark exhaustivo.
- Cuatro `EventCandidate` y cuatro POST de evento con HTTP 201. Cada uno
  recibió además una evidencia PNG por el endpoint multipart (HTTP 201).

| Frame | Tiempo de video | Track | Posición normalizada bottom-center | Event ID | SHA-256 PNG recuperado |
| ---: | ---: | ---: | --- | --- | --- |
| 60 | 2,000 s | 1 | (0,627689; 0,745600) | `9f1f29db-5970-4a40-9b61-dc0c4a4a7d90` | `52080D068675282155AAA179121D29B2BE6D83DEEE5D6BAC1A53BCB29D485CFA` |
| 60 | 2,000 s | 2 | (0,531268; 0,727525) | `1b442c81-990c-49f9-a74c-0e93f472750d` | `52080D068675282155AAA179121D29B2BE6D83DEEE5D6BAC1A53BCB29D485CFA` |
| 134 | 4,467 s | 13 | (0,658158; 0,800624) | `f40a62c2-51c5-46ab-9d18-e8da824df274` | `D4893ABF6F7F048552A9893FD6079438C9C58B276C32F5D64413D84791CC6345` |
| 201 | 6,700 s | 31 | (0,326815; 0,618780) | `f9749a9f-fbec-4c89-8f24-729d2e263b56` | `CA34CAC05AC4998BC2004002368CFFDF0A9D580885F1642BDEE88F7339B1EFD2` |

Los cuatro registros de esta corrida se consultaron en PostgreSQL y por
`GET /api/v1/events/`; sus imágenes se recuperaron por
`GET /api/v1/events/{id}/evidence/`, decodificaron como PNG 960×540 y
coincidieron byte a byte con los hashes producidos por el Motor. Se revisó
visualmente el frame 60: muestra los píxeles reales del almacén con dos
personas, sus IDs y la zona; no es una imagen sintética. `/events` mostró
regla, zona, track, fecha/hora de análisis, estado `Registrado` y
`Ver evidencia` usando la API local.

Un primer intento encontró una caja de tracking parcialmente fuera del frame
y se detuvo. Ya había publicado cuatro eventos antes del fallo. Se conservaron
esos registros de diagnóstico; por eso la base local mostraba ocho eventos en
total, pero **solo los cuatro IDs de la tabla** pertenecen a la corrida
completa. En ese momento, repetir el análisis con otro `analysis_run_id`
creaba nuevos eventos: todavía no había idempotencia entre corridas.

## Verificación posterior de idempotencia local

El problema anterior motivó una protección mínima. El Motor deriva por defecto
un `analysis_run_id` UUID estable de SHA-256 de video, pesos y configuración,
además de los parámetros de YOLO11/ByteTrack. No incluye ruta local ni fecha
civil. Una ejecución intencionalmente nueva puede indicar otro UUID mediante
`--analysis-run-id`. PostgreSQL impone unicidad por corrida, vista, frame,
regla/versión, track y zona. El Backend devuelve 201/`created=true` al crear
y 200/`created=false` con el mismo Event ID al recibir el mismo candidato.
El retry omite un PNG válido existente; si falta, puede completar esa evidencia.
La migración `events.0003_event_candidate_identity` no borra ni inventa
identidades para eventos históricos.

Se repitió el mismo comando de la sección anterior sobre el mismo clip y
configuración (`imgsz=640`, confianza 0,10, IoU 0,70, CUDA, `person`,
ByteTrack vigente), omitiendo `--analysis-run-id` en ambas corridas. Se usó
la misma ancla **de análisis** `2026-10-14T17:00:00Z`, que no acredita la
fecha real de captura. El ID derivado fue
`6ba120ca-43ef-5e50-b5a2-af1fd44912e0` en ambas. Los cuatro candidatos
correspondieron a frame/track 60/1, 60/2, 134/13 y 201/31.

| Medida | Primera corrida | Reintento con API actualizada |
| --- | ---: | ---: |
| Frames procesados | 277/277 | 277/277 |
| Detecciones `person` / observaciones de tracking | 1.088 / 644 | 1.088 / 644 |
| Candidatos | 4 | 4 |
| Eventos nuevos | 4 | 0 |
| Duplicados lógicos evitados | 0 | 4 |
| Respuestas de evento | cuatro HTTP 201 | cuatro HTTP 200 |
| Tiempo de procesamiento, sin carga de modelo | 10,736 s | 10,585 s |
| FPS efectivo exploratorio | 25,802 | 26,170 |

La corrida lógica contiene **cuatro filas y cuatro PNG válidos**, no ocho.
Se recuperaron sus imágenes y se comprobó que los SHA-256 coinciden con los
emitidos por el Motor. El total de la base local pasó de ocho registros
históricos a doce tras la primera corrida y **continuó en doce** después del
reintento. Los ocho anteriores se conservaron; no se depuraron ni fusionaron.
La lista de la API y `/events` sigue mostrándolos, pero no añadió filas por
repetir esta ejecución lógica.

Entre ambas corridas se detectó un servidor Django local antiguo arrancado
con `--noreload`: después de aplicar la nueva constraint, su vista anterior
respondía HTTP 500 ante los cuatro POST repetidos. No insertó nuevas filas.
Se reinició solo ese servidor con el código actualizado y el reintento
respondió HTTP 200 en los cuatro casos. Esto es una condición de despliegue:
la migración y el código de la API deben activarse coordinadamente.

La identidad depende de que el análisis reproduzca los mismos IDs de track y
frames; variaciones no deterministas pueden producir otras claves sin una
verdadera identidad semántica de objetos. La primera fecha civil persistida
se conserva si un retry usa otra ancla. Dos análisis deliberadamente distintos
requieren un UUID distinto; cambios futuros de algoritmo que no alteren los
insumos de la identidad derivada también deben tratarse como una ejecución
nueva mediante ese UUID. No hay transacción de lote ni deduplicación
retroactiva de registros históricos. Estas mediciones de una corrida no son
un benchmark comparativo del costo de idempotencia.

## Alcance y límites

La zona es un área amplia del piso visible elegida para demostrar permanencia;
no delimita un peligro validado. `track_id` es temporal y no identifica
personas. La calidad del evento depende de detección y continuidad del track;
la fragmentación observada en OP-35 puede producir candidatos separados. No
hay ground truth MOT ni validación industrial. COCO no incluye una clase
`forklift`, por lo que esta prueba filtra `person` y no demuestra seguimiento
fiable de maquinaria. El video es sintético y acotado; el FPS depende de este
hardware, configuración y escena. La interfaz `/events` continúa siendo una
vista técnica sin autenticación ni alertas y debe permanecer en localhost.
La fecha absoluta del evento es la ancla suministrada, no un timestamp original
verificado del archivo de video.
