# Operix RTSP lab

Use the overlay from the repository root with the same project name, environment
file, and Compose files as the running Operix stack. Append
`compose.rtsp-lab.yaml` after the other Compose files. The lab uses MediaMTX
1.21.4 and FFmpeg 8.1.3 from the same digest-pinned upstream image.

## Media and backend contract

Set `OPERIX_CAMERA_LAB_MEDIA_HOST` to an existing directory containing only the
approved test videos and their provenance manifest. Compose mounts it read-only
at `/data/rtsp-lab` in the backend and both publishers. The backend receives
`OPERIX_CAMERA_LAB_ENABLED=1` and
`OPERIX_CAMERA_LAB_MANIFEST=/data/rtsp-lab/manifest.json`. Set
`OPERIX_CAMERA_LAB_MANIFEST_FILE` if the JSON file has a different basename.
Use matching camera IDs and file names in the manifest and publisher settings.

| Camera ID | Server-owned RTSP URL (TCP) | Default MP4 basename |
|---|---|---|
| `lab-cam-01` | `rtsp://mediamtx:8554/lab-cam-01` | `lab-cam-01.mp4` |
| `lab-cam-02` | `rtsp://mediamtx:8554/lab-cam-02` | `lab-cam-02.mp4` |

Each publisher checks the MP4 against its pinned SHA-256 before each pass
and exits on a mismatch. The default pins match the approved manifest.
For replacement media, set `OPERIX_CAMERA_LAB_VIDEO_01` or
`OPERIX_CAMERA_LAB_VIDEO_02` and the corresponding
`OPERIX_CAMERA_LAB_SHA256_01` or `OPERIX_CAMERA_LAB_SHA256_02` from the
updated provenance manifest. FFmpeg plays each file at real-time speed,
encoding H.264 at 960×540 and 12 FPS. It pads to the configured dimensions
when the source has a different aspect ratio. Optional settings apply to both
cameras.

| Setting | Default | Accepted values |
|---|---:|---|
| `OPERIX_CAMERA_LAB_WIDTH` | 960 | Even integer, 16–1920 |
| `OPERIX_CAMERA_LAB_HEIGHT` | 540 | Even integer, 16–1080 |
| `OPERIX_CAMERA_LAB_FPS` | 12 | Integer, 1–30 |
| `OPERIX_CAMERA_LAB_LOOP_GAP_SECONDS` | 2 | Positive integer |

For mixed rates, set `OPERIX_LAB_CAM01_FPS`, `OPERIX_LAB_CAM02_FPS`, or
`OPERIX_LAB_CAM03_FPS` in the Compose environment. Use the matching
`OPERIX_LAB_CAMxx_SOURCE_FPS` to set that publisher's cadence. The analysis
rate must be at most the source rate. Without a slot override, Compose uses
the global configuration. Operix reports the configured rates separately,
and deliberate sampling is accounted for separately from overload drops.
Apply a profile during a maintenance window so each new run can establish
its own cadence and tracking epoch.

The backend stays on the product's default network and also joins
`rtsp-lab`, named `operix_rtsp-lab` for the default project. MediaMTX and
the publishers join only that internal network. MediaMTX serves RTSP there
and binds its Control API to loopback inside its container.
The lab publishes zero host ports.

For a benchmark that recreates the QA Backend, check the direct Django
control endpoint and the browser-facing proxy separately before activating
cameras. `benchmark_readiness.py` provides this check for an authenticated
harness. A proxy read reset can surface as HTTP 500 while direct Django
is healthy. The check permits three proxy reads and fails on authorization
errors, Django failures, or an active laboratory. Use authenticated control
writes on the QA Backend loopback and exercise playback through the frontend.

## Control from Operix

For automatic monitoring, add `compose.rtsp-managed.yaml` after
`compose.rtsp-lab.yaml`. Mount the approved originals and their `manifest.json`,
and select an emission cadence at or below every original's frame rate.

```powershell
$env:OPERIX_CAMERA_LAB_MEDIA_HOST = 'D:/Operix-Lab/media/originals'
$env:OPERIX_CAMERA_LAB_FPS = '15'
$stack = @('compose', '--env-file', '../Operix-Docker/operix.env', '-f', 'compose.yaml', '-f', 'compose.gpu.yaml', '-f', 'compose.rtsp-lab.yaml', '-f', 'compose.rtsp-managed.yaml')
docker @stack up -d --build --wait
```

### Optional source frame clock

In an isolated managed lab, add `-f compose.rtsp-clock.yaml` as the last
override and build the backend and publishers together. Start new runs after
changing this option. It applies to managed replay publishers on the private
MediaMTX network. Direct RTSP sources continue using their existing reader.

The publisher adds H.264 unregistered SEI with a public emission identifier and
a zero-based picture ordinal. FFmpeg assigns CFR packet timestamps when
remultiplexing. The Motor validates the emission and the cadence of its RTSP
PTS. hls.js maps the same SEI to the presentation timestamp in the browser's
MediaSource timeline. The overlay joins by emission and ordinal. RTSP PTS and
HLS presentation timestamps have independent origins. The ordinal is a video
identity, with no wall-clock capture meaning. A browser using native-only HLS
can play the video and use the secondary diagnostic preview.

The display window keeps exact observations across local queue gaps so the
delayed player can still show those frames. The visual estimate is limited to
one intervening ordinal within an epoch and never enters tracking, rule
evaluation or evidence. A disconnect, an emission change or a spatial validity
change clears the affected observations. With the Compose override omitted, the
legacy image-verification path is available.

Sign in as an administrator and open **Gestión → Control de cámaras** to enable
the lab and choose its virtual cameras. **Fuentes** shows their current analysis.
The saved intent survives Backend restarts. Turning the lab off stops its
publishers and workers while keeping events and evidence. In **Control de
cámaras**, select clips from the approved inventory, set their order, and choose
whether to repeat the playlist. Each segment has a new worker and run snapshot,
with its own source hash, time base, tracking and rule state. The controller
records expected ends of media separately from interrupted streams. A change
of viewpoint that conflicts with saved spatial settings requires confirmation.
At EOF, the next lease can be acknowledged while the old worker drains. The
next emission waits for that worker to exit and for the old RTSP path to close.
Interrupted playback retries the same playlist item with a fresh lease and
delays of 1, 2, 4, 8, 16 and up to 30 seconds. Healthy analyzed playback resets
the failure count.
Managed playlists accept verified clips of up to 29 minutes, leaving startup
and shutdown time within the worker's 30-minute limit.

To use the longer SPARL logistics recordings locally, set
`OPERIX_CAMERA_LAB_MEDIA_HOST` to `D:/Operix-Lab/media/sparl-rtsp`.
That directory contains the two prepared MP4 files and
`sparl-catalog.v1.json` installed as `manifest.json`. The catalog records each
original and derivative hash, the encoding recipe, and the required attribution.
The recordings show physical logistics trials filmed in a research facility.

PyTorch FP32 is the default. To opt in to ONNX CUDA, first build the base Backend
image, set `OPERIX_RTSP_LAB_ONNX_HOST` to the approved export directory, then
append `-f compose.rtsp-lab.onnx.yaml` and run `up -d --build --wait`. To revert,
run the original stack command again with the ONNX override omitted.

### Event limits and retention

Continuous monitoring uses a per-camera limit that persists across runs and
playlist segments. The benchmark runner explicitly selects its own 20-event
profile. The camera diagnostics distinguish episode duplicates, rate limits,
backpressure, and unavailable rate storage.

| Worker setting | Operational default |
| --- | --- |
| `OPERIX_RTSP_LAB_EVENTS_PER_MINUTE` | 6 |
| `OPERIX_RTSP_LAB_EVENT_DEDUP_SECONDS` | 120 |
| `OPERIX_RTSP_LAB_PNG_TOTAL_BYTES` | 536870912 |
| `OPERIX_RTSP_LAB_CLIP_TOTAL_BYTES` | 536870912 |
| `OPERIX_RTSP_LAB_CLIP_RETENTION_DAYS` | 0 (expiration disabled) |

Set worker variables under the Backend service's `environment` in a local
Compose override. The evidence budgets count existing PNGs and clips when
evaluating new writes. Configured expiration applies to clips produced by the
operational RTSP policy. Expiration is checked during evidence generation and
leaves event rows, PNGs and historical clips intact.

## Start and check the lab

Example for the local stack with the GPU override and approved camera media.
Use the same existing `--env-file` and `-p` arguments as your running stack.

```powershell
$env:OPERIX_CAMERA_LAB_MEDIA_HOST = '../Operix-Docker/rtsp-lab-media'
$stack = @('compose', '--env-file', '../Operix-Docker/operix.env', '-f', 'compose.yaml', '-f', 'compose.gpu.yaml', '-f', 'compose.rtsp-lab.yaml')
docker @stack up -d --wait --wait-timeout 90 mediamtx lab-publisher-01 lab-publisher-02
docker @stack ps mediamtx lab-publisher-01 lab-publisher-02
docker @stack exec -T mediamtx wget -qO- http://127.0.0.1:9997/v3/paths/list
```

These targeted commands can run before the backend rollout. After coordination,
apply the overlay to the backend with its lab-capable image in place.

```powershell
docker @stack up -d --no-deps --no-build --wait backend
```

Compose recreates the backend to activate its new environment and network
attachment. The existing data volumes are retained.

## Observe reconnects and interrupt a camera

Each pass uses a fresh FFmpeg process and RTSP connection. At EOF the
publisher disconnects, logs the epoch, and waits before starting from the
beginning. It also waits and retries after an FFmpeg failure. Publisher
health requires an actual decoded video frame over RTSP/TCP. Brief EOF gaps
are expected, so Docker tolerates transient probe failures.

```powershell
docker @stack logs --tail 40 mediamtx lab-publisher-01 lab-publisher-02
docker @stack stop lab-publisher-01
docker @stack exec -T mediamtx wget -qO- http://127.0.0.1:9997/v3/paths/list
docker @stack up -d --wait --wait-timeout 90 lab-publisher-01
```

While camera 01 is stopped, its path is absent or unready. Camera 02 keeps
running its own loop. To stop the lab services, target them explicitly.

```powershell
docker @stack stop lab-publisher-01 lab-publisher-02 mediamtx
```


## Reproducir la validación

1. Ejecuta ./deployment/rtsp-lab/prepare-media.ps1 para descargar únicamente
   los dos clips aprobados o verificar las copias existentes. El manifest conserva
   las atribuciones, licencias, huellas y enlaces originales.
2. Levanta los servicios del perfil GPU y del laboratorio. En
   http://127.0.0.1:13000/sources, abre una cámara de laboratorio.
   Con el monitoreo detenido, edita los vértices en coordenadas normalizadas.
   En Reglas, asigna por cámara un conjunto con zonas compatibles.
3. El smoke usa tres cuentas locales. Define las variables
   OPERIX_LAB_TEST_ADMINISTRATOR_USER, OPERIX_LAB_TEST_SAFETY_LEAD_USER
   y OPERIX_LAB_TEST_VIEWER_USER, con sus correspondientes variables
   terminadas en _PASSWORD. Con ambas cámaras detenidas, ejecuta:

       ./engine/.venv/Scripts/python.exe deployment/rtsp-lab/smoke.py --output ../tmp/lab-smoke

   Usa el puerto local 13000, el proyecto operix y un directorio de salida nuevo.
   La prueba crea eventos de laboratorio, corta el emisor 01, comprueba que el
   02 siga procesando, recupera evidencias por rol y detiene los workers.
4. Las pruebas unitarias del Motor incluyen el buffer y sus límites.
   Ejecuta python -m unittest discover -s tests desde engine. Las pruebas HTTP
   del Backend se ejecutan en la base de pruebas de Django.

El límite de dos monitores concurrentes es una configuración por defecto.
Se rechazan nuevos inicios cuando no quedan plazas. La carga de archivos y el
monitor comparten GPU. Cada sesión admite hasta 30 minutos y 20 intentos
de publicación. La cola de seis fotogramas descarta por capacidad, antigüedad
o discontinuidad con contadores separados. Cada bucle abre una conexión y
reinicia la continuidad espacial y temporal. Los clips tienen hasta tres
segundos anteriores y un segundo posterior dentro de la misma época.
Tienen límite individual y presupuesto global de disco. Los eventos del
laboratorio se consultan por cámara y no entran por defecto en indicadores.

La hora civil del evento es la recepción UTC del fotograma. Se conserva el PTS
cuando existe. La latencia del Motor mide desde la recepción local hasta
el resultado. La persistencia incluye el contexto posterior y la publicación.
Las fuentes virtuales carecen de referencias físicas validadas, así que
sus mediciones se expresan en unidades de imagen normalizada.

## Inferencia compartida experimental

El perfil estándar mantiene el procesamiento por cámara. En la matriz
540p/12 de cuatro fuentes, el perfil dedicado procesó cerca de 47 FPS
en total frente a 38,5 FPS del candidato compartido con tope de lote 2.
Con dos fuentes ambos se acercaron al ritmo de entrada, con menor p95
local en el perfil dedicado. Las ventanas cortas no certifican capacidad
para cuatro cámaras reales. Para ensayar un
solo proceso GPU con ambos modelos congelados, añade
`-f compose.rtsp-inference.yaml` al arreglo `$stack`. Ejecuta primero
`docker @stack build backend` y luego
`docker @stack up -d --wait --wait-timeout 90` con el perfil ampliado.
El servicio de inferencia usa un socket Unix privado y pesos de solo lectura.
No recibe URLs de cámaras, credenciales de publicación ni evidencias.

El Motor de cada cámara conserva captura, épocas, tracking, reglas y
publicación. El proceso GPU acepta un cuadro en curso por cámara y ejecución.
Agrupa solamente cuadros de igual resolución, limita la espera y devuelve
resultados a la solicitud original. Un cuadro vencido no avanza el tracker ni
las reglas. Si se reinicia el proceso GPU, vuelve a iniciar los monitores
afectados. Para volver al perfil estándar, detén los monitores, detén
`rtsp-inference` con el perfil ampliado y recrea `backend` con los tres
archivos Compose originales. Mantén los volúmenes.

`OPERIX_RTSP_BATCH_CAP` admite 1, 2 o 4 y
`OPERIX_RTSP_BATCH_WAIT_MS` admite 0 a 20. La configuración predeterminada
del perfil experimental es 2 y 6 ms. Un lote grande acelera inferencia
cuando hay suficientes cuadros listos. Mide la distribución real de tamaños,
la antigüedad, los descartes y la cobertura antes de cambiar el perfil.

La página de cámara distingue el ritmo de análisis y la fracción de
fotogramas decodificados que llegaron a análisis en la ventana reciente.
Un período sin señal puede tener cobertura sin datos. Los tiempos p50 y
p95 son muestras locales recientes, a partir de la entrega del decodificador.
El laboratorio carece de un reloj de emisión común a las fuentes.

### Comparación reproducible

Usa `deployment/rtsp-lab/benchmark_gpu.py` para medir lotes 1, 2 y 4
sobre los mismos fotogramas y comparar detecciones. El parámetro opcional
`--fp16` evalúa paridad y rendimiento sin cambiar los pesos.
`benchmark-live.py` mide en una red Docker temporal con replay continuo,
sin escribir en PostgreSQL. Ejecuta primero sin `--execute` para comprobar
el plan y con `--help` para ver rutas y opciones. Usa una imagen de línea
base construida desde la revisión de control y los mismos checkpoints para
todas las etapas. El ejemplo usa `7c2bdbd`:

```powershell
python -B deployment/rtsp-lab/benchmark-live.py --feeds 1 2 3 4 `
  --media-dir ../Operix-Docker/rtsp-lab-media --output ../tmp/comparacion-rtsp `
  --worker-image operix-backend:rtsp-baseline-7c2bdbd --candidate-root . `
  --person-weights <ruta-person.pt> --forklift-weights <ruta-forklift.pt> `
  --warmup 15 --seconds 60 --batch-cap 2 --batch-wait-ms 6 --resources --execute
```

Los alias tercero y cuarto repiten material aprobado. La medición de carga
no amplía el inventario de cámaras del producto. El smoke autenticado
valida PostgreSQL, publicación, reconexión y evidencias con el perfil
que esté en ejecución. Añade `--shared` para exigir el perfil compartido.
Las pruebas de otros perfiles aceptan `--width`, `--height` y `--fps`
(12, 15, 20, 24 o 30). El informe registra los fotogramas eliminados o
repetidos por FFmpeg al preparar cada replay. Una emisión de 30 FPS con
una fuente de menor cadencia mide carga de transporte y procesamiento.
La cantidad de imágenes distintas depende del material original.
`valid` comprueba que el observador y las fuentes fueron estables durante
la ventana. `meets_capacity_gate` exige además cero descartes contabilizados,
balance de cuadros y p95 local bajo 500 ms en todas las cámaras. Los percentiles de cada etapa
son los del búfer reciente del worker al cierre de la ventana.
Los recursos de GPU son muestras del total del host, con la carga del
escritorio y otras aplicaciones incluida.

`benchmark_decode_local.py` compara decodificación a ráfaga de los clips
aprobados con FFmpeg y OpenCV. `--nvdec` añade decodificación CUDA con
descarga a RAM e informa diferencias de fotogramas y PTS frente a software.
La lectura RTSP observada por el worker incluye la espera de red. Para
medir el coste de la verificación ArUco por separado, `benchmark_calibration_guard.py`
repite fotogramas sintéticos con cero, uno o dos guardas, e incluye un
desplazamiento de encuadre controlado.

`benchmark_backends.py` compara PyTorch FP32 con ONNX Runtime CUDA o
TensorRT en contenedores de prueba con los pesos originales de solo lectura.
Consulta `--help` y el manifiesto antes de habilitar `--execute`. El resultado
compara predicciones pos-NMS y separa el cambio de backend del cambio de
forma o de lote. Los motores exportados y los pesos permanecen fuera de Git.
Construye los entornos opcionales con `backend-proof.Dockerfile` y el target
`ort` o `tensorrt`, pasando la imagen local de control como `BASE_IMAGE`.
Para aislar el coste de compilación, ejecuta el perfil TensorRT con
`--execute --compile-only` y conserva su `report.json` junto a los motores.
La inferencia recibe ese informe y su huella mediante `--engine-report` y
`--engine-report-sha256`. Usa el mismo backend, forma, lote y nivel de
compilación en ambos pasos. `--trt-build-level 0` permite ensayar el nivel
rápido del compilador y queda registrado junto con los tiempos por modelo.
En video 16:9, `--input-height 384 --imgsz 640` conserva la forma rectangular
del preprocesado de PyTorch. `benchmark_gpu.py --batch-eight` añade la prueba
de lote 8 cuando hay al menos 4 GiB de memoria CUDA libre.
`benchmark_replay_parity.py <report.json>` vuelve a alimentar ByteTrack, la
geometría y las reglas de prueba con las detecciones guardadas, a la cadencia
nominal del clip. El replay compara resultados de software sobre el mismo
material. La precisión física y la cobertura en planta requieren otras pruebas.
Para comparar el mismo ONNX en RTSP, construye el target `ort-live` con
`--build-context exports=<carpeta del report.json>` y pasa esa imagen a
`benchmark-live.py --candidate-image`. El worker experimental verifica las
huellas y la forma antes de iniciar. Para volver a PyTorch, ejecuta la etapa
`regular` con la imagen de control. Compose mantiene PyTorch como predeterminado.

### Continuidad ante descartes

Todo hueco corta la época de observación, las trayectorias, los episodios de
reglas y el contexto de clip. El Motor reinicia los relojes del episodio en
el siguiente cuadro observado. La identidad de ByteTrack puede conservarse
ante un único ordinal omitido, en la misma conexión y después de cuadros
consecutivos. El PTS debe avanzar aproximadamente dos períodos de la fuente,
y los saltos de PTS y recepción deben ser positivos y de hasta 250 ms. Se
asocian solo detecciones del cuadro real que se recibe después del descarte.

Las pérdidas consecutivas, los saltos repetidos sin un cuadro consecutivo
entre ellos, los relojes ambiguos y la reconexión reinician ByteTrack. El PTS
perdido o recuperado abre otra época. Las revisiones de zona, reglas y
calibración se aplican al iniciar un run nuevo. Durante un run, el guard de
encuadre suspende las reglas espaciales al perder validación y un corte de
época vuelve a exigir la comprobación del patrón.

El estado informa `tracking_resets` y `tracking_preserved_gaps` aparte de
`epochs`. El replay `benchmark_continuity.py <directorio-nuevo>` genera un
video anotado, simula ráfagas en la cola y compara ambas políticas con el mismo
ByteTrack y las mismas reglas. Los FPS y latencias del fixture corresponden
a servicio CPU con detecciones anotadas y reloj de llegada simulado.

### Medición desde la emisión RTSP hasta el historial

`benchmark-emission.py` usa una copia con marcas de los videos aprobados.
Requiere Python, Requests, Pillow y FFmpeg con libx264. Verifica el hash
original y todos los ordinales decodificados antes de emitir. `media.json`
conserva la atribución CC BY 4.0, los cambios y los hashes.

En una instancia de laboratorio aislada, detén el publicador normal para la
cámara elegida e inicia un run nuevo con una regla aplicable al video. Usa
las variables del lector de seguridad de `smoke.py`. `$rtspUrl` debe ser
una ruta RTSP/TCP privada para ese ensayo y `$runId` el UUID de ese run.

```powershell
./engine/.venv/Scripts/python.exe -B deployment/rtsp-lab/benchmark-emission.py measure `
  --media-dir ../Operix-Docker/rtsp-lab-media --camera lab-cam-01 `
  --rtsp-url $rtspUrl --run-id $runId --base-url http://127.0.0.1:13000 `
  --passes 3 --poll 0.15 --output ../tmp/operix-emission
```

`report.json` delimita la disponibilidad HTTP entre la última consulta sin
el evento y la primera respuesta completa que lo contiene. El origen es la
entrega local a TCP del último paquete RTP del fotograma, en el mismo reloj
monótono. El token y ordinal del PNG confirman la correspondencia entre el
fotograma y el evento aunque el PNG se publique después. Se conservan las
observaciones sin correspondencia y se excluyen del cálculo. Informa el
intervalo de sondeo y los casos sin verificar junto con las estadísticas.

El Motor también mide desde la entrega del decodificador hasta el resultado,
el registro, el PNG y el clip. Estas métricas usan otro punto de partida.
En versiones anteriores a la publicación por etapas, `arrival_to_publication`
incluía la espera del contexto posterior y la carga del PNG. Para el flujo
nuevo, usa `arrival_to_registration`, `arrival_to_png` y `arrival_to_clip`.

### Preparación de una cámara autorizada

Para una prueba en Embonor, acuerda primero la cámara fija, la ventana de
captura, la retención y quién puede consultar originales y evidencias.
El inventario del servidor debe controlar la IP privada y la ruta RTSP.
Usa credenciales de solo lectura, fuera de Git, y una red aislada. Verifica
códec, resolución, FPS, timestamps, latencia y recuperación con la fuente
autorizada. Registra por separado las referencias físicas, zonas y reglas
aprobadas para ese encuadre y la cobertura de cada corrida. El perfil
puede usar distancia normalizada o una calibración confirmada para esa cámara.

### Calibración con patrones en el suelo

Coloca de tres a ocho marcadores ArUco `DICT_4X4_50` con IDs únicos, borde
blanco libre y suficiente separación en el área de trabajo. Mide en el
suelo la posición de la esquina superior izquierda **del código impreso**, el
lado del cuadrado negro y su orientación respecto del mismo sistema de ejes.
Usa esa posición como origen del cuadrado y el giro desde sus ejes locales.
Registra cómo obtuviste las medidas. Las referencias deben estar en el plano
que se va a medir.

En **Fuentes → cámara → Calibrar distancias**, captura la imagen de la
emisión actual y revisa los marcadores detectados. Revisa el área de
cobertura y las zonas. Luego marca los dos extremos de un segmento distinto
de las referencias y compruébalo con una distancia medida en el suelo y su
tolerancia. La cuadrícula queda limitada a la envolvente de las referencias.
La reproyección, la consistencia temporal y la sensibilidad de un píxel son
diagnósticos del ajuste. Conserva la comparación con medidas físicas
independientes para evaluar la exactitud en terreno.

Mantén los marcadores de referencia visibles durante el monitoreo. Si la
verificación periódica pierde el patrón o detecta un cambio, el análisis pasa
a imagen y suspende las reglas espaciales. Al invalidarse el encuadre de
forma sostenida, una nueva ejecución requiere una propuesta confirmada.
Cambiar de fuente o dimensiones también requiere revisar la calibración.
Los videos de archivo conservan su asistente de rectángulo medido y los
controles manuales. Las pruebas con patrones generados se pueden repetir con
`python -m unittest discover -s engine/tests -p 'test_calibration_patterns.py'`.

### Tercera plaza virtual (opcional)

Añade `-f compose.rtsp-third.yaml` después de `compose.rtsp-clock.yaml` en el
despliegue administrado. En **Control de cámaras → Incorporar cámara** asigna
una grabación del manifiesto autorizado a Cámara 03, guarda la lista y
habilítala. La cámara permanece deshabilitada hasta esa acción.

Con capacidad de análisis de dos cámaras, la plaza 03 publica LL-HLS en
modo **Solo video**. Una capacidad de tres requiere una prueba sostenida de
ONNX CUDA en el entorno de destino antes de habilitarla.

### Recorrido de demostración

1. En [Operix local](http://127.0.0.1:13000), abre **Gestión → Control de
   cámaras** con una cuenta autorizada. Asigna una grabación de laboratorio
   autorizada a cada una de las dos plazas y habilita el laboratorio.
2. En **Fuentes**, abre el monitoreo de ambas cámaras. En el detalle de una
   cámara, activa las capas de detección, seguimiento y distancias. Comprueba
   los identificadores sobre el video y revisa la regla activa en sus ajustes.
   Con grabaciones sin escala física confirmada, utiliza la distancia `norm.`.
3. Para mostrar el expediente, elige una grabación que contenga una permanencia
   continua en una zona configurada. Espera el registro y abre **Eventos**,
   filtrando por cámara y procedencia de laboratorio. Revisa el fotograma,
   el clip y la versión de la regla. El evento registra una condición
   configurada satisfecha y requiere revisión humana.
4. Al finalizar, devuelve el laboratorio y las listas de reproducción al
   estado previo. Si ensayas reconexiones o cambias una calibración, utiliza
   una instancia QA aislada.

### Arquitectura y renovación de playlists

El control de cámaras guarda los identificadores ordenados y la repetición
en PostgreSQL. El reconciliador abre una emisión FFmpeg desde un MP4
autorizado por el manifiesto y su SHA-256. MediaMTX distribuye el video
por LL-HLS y cada cámara analizada tiene un worker dedicado. Una transición
abre otra emisión y ejecución con su propio reloj, snapshot, tracking y
contexto de reglas y clips. El reproductor asocia las observaciones con
las marcas compartidas de emisión. Las posiciones estimadas se usan solo
para dibujar. Los eventos y sus evidencias se consultan con autorización
a través de Operix.

UNIFIED V7 usa ONNX Runtime CUDA con clases PERSON, FORKLIFT y PALLET_JACK.
PALLET_JACK se puede mostrar y rastrear como categoría experimental.
La elegibilidad operacional se determina con la observación y la regla
configurada. La etiqueta visual estabilizada queda fuera de esa decisión.
Consulta [el perfil versionado](../../engine/config/unified-v7.json) antes
de modificar un despliegue.

Los clips autorizados de [Önal y Dandıl (CC BY 4.0)](https://data.mendeley.com/datasets/xjmtb22pff/1)
se preparan a 960 × 540 y 15 FPS para el laboratorio. El inventario local
`D:/Operix-Lab/manifests/cctv-selection-v7.json` conserva los hashes del
original y del derivado. Al renovar un catálogo, conserva los
identificadores de las asignaciones existentes y verifica la configuración
guardada después de volver a iniciar el Backend.

### Recuperar LEGACY_DUAL

1. Registra la configuración efectiva de Compose del Backend, las
   asignaciones y el estado de las cámaras. Haz un respaldo restaurable
   de PostgreSQL y evidencias. Conserva los pesos aprobados de ambos
   perfiles y sus montajes de solo lectura.
2. Cierra de forma controlada las ejecuciones administradas y espera a que
   terminen las publicaciones de evidencia. Comprueba también que los
   análisis de archivo hayan finalizado.
3. Ejecuta Compose con el mismo proyecto, archivo de entorno y lista
   ordenada de configuraciones de la instancia. Puedes consultar la lista
   en la etiqueta `com.docker.compose.project.config_files` del contenedor
   Backend. Agrega `-f compose.legacy-dual.yaml` **al final** de esa lista.
   Tras validar con `config --quiet`, ejecuta
   `up -d --no-deps --no-build --wait backend` con esas opciones.
4. Comprueba la salud de la API y PostgreSQL, el detector activo con
   `active_perception()` desde Django, las asignaciones guardadas y los
   hashes de las evidencias históricas. Comprueba reproducción y permisos
   antes de reanudar el monitoreo.
5. Para volver a V7, repite el procedimiento con la configuración que
   usabas originalmente, omitiendo únicamente la última sobrecapa de
   LEGACY_DUAL. PostgreSQL y los volúmenes de evidencia se mantienen
   durante ambos cambios de perfil.

Para la presentación académica se conserva
[el expediente de Embonor](http://127.0.0.1:13000/events/21b68882-e49a-40cf-81c2-f2a0295ff393).
Su video, regla y unidad de medida pertenecen a la ejecución registrada.
