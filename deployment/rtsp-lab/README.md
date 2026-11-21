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

The backend stays on the product's default network and also joins
`rtsp-lab`, named `operix_rtsp-lab` for the default project. MediaMTX and
the publishers join only that internal network. MediaMTX serves RTSP there
and binds its Control API to loopback inside its container.
The lab publishes zero host ports.

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
base construida desde `7c2bdbd` y los mismos checkpoints para todas las etapas:

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
Las pruebas de otros perfiles aceptan `--width`, `--height` y `--fps`.
Los recursos de GPU son muestras del total del host, con la carga del
escritorio y otras aplicaciones incluida.

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

Detén la cámara y captura una propuesta. Revisa las etiquetas, el área de
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
