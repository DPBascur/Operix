# Etapa 3 — baseline multiescenario con YOLO11n (`confidence=0.10`)

## Pregunta y alcance

¿El umbral exploratorio `0.10` permite obtener detecciones de `person`, continuidad de ByteTrack y candidatos de `zone_dwell` en tres escenas sintéticas diferentes? Esta campaña compara A (evacuación con varias personas), B (persona y montacargas) y C (recogida de caja por una persona). No mide precisión, recall, MOT ni capacidad industrial. Complementa [el estudio de umbrales en A](etapa3-confidence-yolo11.md); no modifica parámetros predeterminados ni componentes del Motor.

## Procedencia y selección de C

Los tres clips son de **NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes**, dataset sintético publicado por NVIDIA bajo [OpenMDW-1.1](https://openmdw.ai/); véase la [ficha oficial](https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes) y la [revisión fijada](https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes/tree/d5b88d3abcf659f304a107f4336b71b4e2159133). Se consultaron únicamente los índices `metadata/clips.parquet` y `metadata/runs.parquet` de esa revisión. La cabecera del primer miembro del shard RGB identificó el clip C; se descargaron mediante HTTP Range **solo sus 22.253.530 bytes**, no el TAR de aproximadamente 5,19 GB ni otros videos candidatos.

| Escenario | Acción y vista | Archivo | Frames / FPS / resolución | SHA-256 del video |
| --- | --- | --- | --- | --- |
| A | `warehouse_fire`, `ceiling_04`; evacuación con varias personas | `warehouse_fire_ceiling04.mp4` | 277 / 30 / 1920×1080 | `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6` |
| B | `forklift_human_nearmiss`, `ceiling_00`; una persona y montacargas | `forklift_human_nearmiss_ceiling00.mp4` | 300 / 30 / 1920×1080 | `E4795E873DCBDAAA4DC3D42F533052E3C1DB62D1D3EF786C2C90DD4D7681330B` |
| C | `warehouse_box_pickup`, `cam_00`; una persona recoge una caja en pasillo, vista fija | `008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4` | 418 / 30 / 1920×1080 | `EABF44D7ABE50D1BF4824F238A9F0AC9DDC29419E10D66B89C6A92CB1B98329C` |

En C, `run_id=008caa590c5e5b7b4bca_run_8_seed_4731920`, `seed=4731920`, cámara `cam_00`, nombre de origen indexado `28b790c4b7f880004d9b_rgb.mp4`, miembro `008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4` del shard `rgb/warehouse_box_pickup/box_pickup-rgb-00000.tar`. Tamaño exacto: **22.253.530 bytes**; duración decodificada: **13,933 s**. Se decodificaron consecutivamente los 418 frames. La inspección de frames distribuidos a lo largo del clip confirmó una persona visible, movimiento de caminar/agacharse/levantarse, pasillo fijo y espacio para una zona demostrativa. **C no satisface el criterio deseable de varias personas, cruces u oclusiones entre personas**; aporta una acción y un cambio de pose diferentes de A/B. Se descargó exactamente un video nuevo.

El **nuevo clip C** y todos los derivados de esta campaña permanecen fuera del historial de Git. Los clips A/B ya versionados como demostración conservan su atribución en [NOTICE](../../third_party/nvidia-warehouse-dataset/NOTICE.md) y [licencia](../../third_party/nvidia-warehouse-dataset/LICENSE-OpenMDW-1.1.txt).

## Configuración controlada

- Equipo: Windows 10 x64, Ryzen 5 5500, NVIDIA GeForce RTX 3070; Python 3.12.10, PyTorch 2.14.0+cu130, CUDA disponible. `check_environment.py --require-cuda` verificó operación tensorial CPU/CUDA.
- Pesos locales externos a Git: `yolo11n.pt`, SHA-256 `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`. YOLO11n-COCO: `device=cuda`, `confidence=0.10`, `imgsz=640`, `iou=0.70`, filtro estricto `person`. No se infiere ni sigue `forklift`.
- ByteTrack sin cambios: `track_high_thresh=0.25`, `track_low_thresh=0.10`, `new_track_thresh=0.25`, `track_buffer=30`, `match_thresh=0.80`, `fuse_score=true`.
- Regla sin cambios: `demo_zone_dwell`, versión 1, `kind=zone_dwell`, `class_name=person`, `min_duration_s=2.0`. Este valor es experimental, no un umbral validado de seguridad.
- `recording_start_at=2026-10-14T17:00:00Z` es un ancla técnica del análisis, **no** una fecha de captura del dataset. Las zonas B/C se guardaron solo como configuraciones JSON locales externas a Git. Su contenido semántico se describe a continuación; el SHA-256 de cada archivo conserva la identidad exacta usada para `analysis_run_id`.

| Escenario | Vista / zona | Polígono normalizado `(x,y)`, en orden | SHA-256 del JSON operacional |
| --- | --- | --- | --- |
| A | `ceiling_04` / `area_transito_demo` | `(0.03,0.60)`, `(0.97,0.60)`, `(0.97,0.98)`, `(0.03,0.98)` | `4CDB60006900F7547C1699DD5AFE05399607ECA2735E178E42ED7DB535A18B27` |
| B | `ceiling_00` / `pasillo_persona_demo` | `(0.20,0.38)`, `(0.62,0.38)`, `(0.62,0.95)`, `(0.20,0.95)` | `7F4600770831C9F73E1FC0E2291717B49121FF106D2E915ACB189AFBF5289D05` |
| C | `cam_00` / `pasillo_cajas_demo` | `(0.26,0.40)`, `(0.70,0.40)`, `(0.70,0.88)`, `(0.26,0.88)` | `57AC51E411A2A355B68A7BEB4E3C7B1BD2E0F248B1CA2ED23AA6EF513C2DB3D7` |

Las zonas representan pasillos visibles y se fijaron tras una inspección espacial de cada video, no por ajuste frame a frame para forzar eventos. El punto de pertenencia es el `bottom-center` del bounding box según OP-36. Para repetir la lógica se puede reconstruir el JSON con el esquema de [configuración operacional](../config/examples/desktop-zone-dwell.json); para obtener **el mismo** `analysis_run_id` de B/C hace falta conservar los bytes del JSON local, porque su SHA-256 participa en la identidad.

## Ejecución y resultados

Se usó `engine/scripts/process_video_events.py` con los SHA-256 esperados, parámetros precedentes y API local Django/PostgreSQL. Cada corrida comenzó con detector y tracker nuevos. Para observar la secuencia de IDs se usó adicionalmente `engine/scripts/track_video.py` con exactamente la misma configuración de detección/tracking; sus JSONL y videos anotados son diagnósticos locales, no parte del repositorio. Las duraciones siguientes miden esta ejecución integrada con API/evidencia, no un benchmark controlado como OP-43.

Forma de reproducción desde la raíz del repositorio (sustituir marcadores por rutas **locales** y el SHA de la tabla; no añadirlos al repositorio):

```powershell
engine/.venv/Scripts/python.exe engine/scripts/process_video_events.py <VIDEO> `
  --weights <PESOS_YOLO11N> --config <JSON_OPERACIONAL> `
  --expected-video-sha256 <SHA_VIDEO> `
  --expected-weights-sha256 0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1 `
  --recording-start-at 2026-10-14T17:00:00Z --conf 0.10 --imgsz 640 --iou 0.70
```

En A, `<JSON_OPERACIONAL>` es `engine/config/examples/desktop-zone-dwell.json`; en B/C son los JSON locales descritos arriba. Para el diagnóstico de continuidad se usó `track_video.py` con salidas `--output-jsonl` y `--output-video` locales, y `--expected-frames`, `--expected-fps`, `--expected-width`, `--expected-height` según la tabla. La API se mantuvo en su dirección local predeterminada.

| Escenario | Frames / duración | Tiempo proceso / FPS efectivo | Detecciones `person` | Observaciones ByteTrack / IDs | Huecos **dentro del mismo ID** | Candidatos / eventos nuevos | Tracks / frames de evento | Incidencias |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| A | 277 / 9,233 s | 8,533 s / 32,461 | 1.088 | 644 / 8 | 4 episodios, 15 frames ausentes (IDs 4 y 13) | 4 / 0; los 4 ya existían | 1 y 2: 60; 13: 134; 31: 201 | 7 observaciones de track recortadas al frame; fragmentación y tracks espurios ya documentados |
| B | 300 / 10,000 s | 7,520 s / 39,891 | 302 | 300 / 1 | 0 | 1 / 1 | 1: 60 | Persona seguida 300/300 frames; el montacargas no participa en la inferencia filtrada |
| C | 418 / 13,933 s | 9,648 s / 43,324 | 361 | 360 / 2 | 0 | 2 / 2 | 1: 60; 2: 228 | 58 frames sin track entre IDs 1 y 2; fragmentación al agacharse |

Los cuatro candidatos de A recibieron `duplicate`/HTTP 200 por una corrida anterior con identidad y evidencias coincidentes; **0 eventos nuevos no significa 0 candidatos**. B y C recibieron `published`/HTTP 201 y tienen respectivamente 1 y 2 filas asociadas a sus `analysis_run_id` en la API. No hubo excepciones ni fallos de publicación. La diferencia de FPS entre clips no atribuye causalidad a densidad, movimiento o umbral: las escenas, duraciones, estado de caché y carga local no fueron controlados como en un benchmark.

### Continuidad e inspección visual

- **A:** el JSONL diagnóstico reprodujo 8 IDs y 644 observaciones; huecos internos de 1 y 12 frames en ID 4 y dos huecos de 1 frame en ID 13. La escena es más densa. Subsisten las limitaciones visuales documentadas en OP-35/OP-60/OP-61; no se afirma un ID switch inequívoco sin ground truth.
- **B:** una persona pasa de desplazamiento a permanencia; ID 1 aparece en frames `0…299` sin huecos. La captura de evidencia del evento 60 muestra frame real, persona, ID y zona coherentes. La presencia visual de un montacargas no prueba detección ni tracking de maquinaria.
- **C:** el único trabajador visible tiene ID 1 en `0…109`, desaparece del tracking en `110…167` (58 frames) mientras se agacha y reaparece con ID 2 en `168…417`. Los segmentos individuales no tienen huecos internos; la **discontinuidad entre IDs** es una fragmentación visualmente sustentada, no dos personas. Las capturas de evidencia en frames 60 y 228 muestran el mismo pasillo, la zona y sus IDs respectivos. El segundo candidato puede ser una consecuencia de la fragmentación: dos eventos lógicos no equivalen a dos personas ni a dos incidentes de seguridad.

Las evidencias PNG locales de B/C coincidieron byte a byte con los SHA-256 reportados por el Motor: B frame 60 `699A0C1D55CEEF8519673BC34FB1F064E1DCD25AAC5F9EDD705F72CCC35B762C`; C frame 60 `635B414817ECECC8B275B9CC1B736D610669F16EFE50D6338A4112351D47D885`; C frame 228 `963AF338EA7B0D381AC57CF24D56D2AF4BADBF0B78481BA7C681D5C827AC570F`. Esas imágenes siguen en el almacenamiento local del Backend y **no** se versionan.

### Repetibilidad e idempotencia

C se ejecutó dos veces con el mismo video, pesos, JSON operacional y parámetros. Ambas corridas produjeron `analysis_run_id=b89d5120-5fd6-5844-a17b-ed25b1cc88e5`, 418 frames, 361 detecciones `person`, 360 observaciones, 2 IDs, 2 candidatos en frames/IDs `60/1` y `228/2` y los mismos SHA-256 de evidencias. En la segunda corrida los dos eventos recibieron `duplicate`/HTTP 200; `created_event_count=0` y el Backend conserva exactamente **2** filas para esa identidad. Los tiempos cambiaron de 9,648 a 9,784 s (43,324 a 42,721 FPS), diferencia compatible con variación de ejecución no controlada. A también conservó su identidad histórica `6ba120ca-43ef-5e50-b5a2-af1fd44912e0`.

## Interpretación y decisión provisional

`confidence=0.10` sigue siendo una **baseline exploratoria razonable para `person`** en estas tres muestras sintéticas: A/B/C entregaron detecciones y tracks suficientes para evaluar la regla `zone_dwell` y generar candidatos. La escena densa A concentra más IDs y huecos internos; B, menos densa, mantuvo un único ID continuo. C revela una limitación nueva frente a esta comparación: un cambio de pose prolongado rompe el track aunque el umbral sea bajo, y la regla puede emitir un candidato adicional para la identidad nueva. No se modifica el default, ByteTrack, la regla ni las clases del detector en esta campaña.

No se ha validado `forklift`: COCO no incluye esa clase y la ejecución filtra `person`. Las zonas y la permanencia son demostrativas, no criterios calibrados de riesgo. No hay ground truth de identidad ni de eventos para reclamar precisión, recall, ID switches o métricas MOT formales. Los clips son sintéticos y acotados, C contiene una sola persona y no prueba tracking multiobjeto; persiste la brecha con CCTV industrial real. Los FPS de estas corridas no demuestran funcionamiento universal o sostenido en tiempo real. Se requieren escenarios y anotaciones adicionales antes de alterar parámetros o generalizar conclusiones.

## Validación y artefactos

- Motor: `python -m unittest discover -s engine/tests -q` con pesos y muestras reales habilitados: **151/151 tests, OK**.
- `check_environment.py --require-cuda`: Python 3.12.10 x64, PyTorch 2.14.0+cu130, Ultralytics 8.4.146, RTX 3070, tensores CPU/CUDA y OpenCV operativos.
- El único archivo versionable de esta campaña es este Markdown. El video C, ambos índices Parquet consultados, los dos JSON operacionales de B/C, JSONL diagnósticos, videos anotados y capturas de inspección permanecen locales fuera de Git. Los pesos tampoco se versionan. No hubo cambios funcionales de código, dependencia ni configuración predeterminada.
