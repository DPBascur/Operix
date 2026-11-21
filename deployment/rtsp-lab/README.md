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
