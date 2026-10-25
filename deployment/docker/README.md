# Operix local: Docker como alternativa al modo nativo

El camino nativo documentado en los README de Backend, Frontend y Motor sigue
soportado. Docker envuelve la misma aplicación: PostgreSQL, Django (que lanza su
worker Python existente) y Next.js. No hay un nuevo servicio Motor, broker o proxy.

## Requisitos

Docker Desktop con contenedores Linux y Compose. Para análisis real en Windows:
backend WSL2 y driver NVIDIA compatible; comprobar GPU passthrough antes de usar
modelos. [Docker documenta GPU en Windows exclusivamente con WSL2](https://docs.docker.com/desktop/features/gpu/).
La imagen conserva Python 3.12.10, Node 24.2.0, pnpm 11.28.2 y los pins Python
existentes; las dependencias CUDA de Linux provienen del wheel PyTorch cu130.
El runtime Linux completo queda fijado en `requirements.linux-cu130.lock.txt`,
sin reemplazar ni modificar el lock nativo Windows/CUDA.
No instalar un driver NVIDIA Linux dentro de la imagen.

## Inicio de infraestructura, sin reservar GPU

Desde la raíz del repositorio:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.docker.example .env }
# Editar .env: contraseñas y DJANGO_SECRET_KEY propias, no las del modo nativo.
docker compose up -d --build
docker compose ps
docker compose logs -f
```

Frontend: `http://localhost:13000`; API: `http://localhost:18000/api/v1/health/`.
Los puertos se pueden cambiar en `.env`; reconstruir Frontend al cambiar la URL
pública, porque Next.js incorpora `NEXT_PUBLIC_API_BASE_URL` durante el build.
La URL pública corresponde al navegador, no al hostname interno `backend`.
PostgreSQL solo escucha en la red de Compose; no publica puerto al host.
History, filtros y frecuencias no requieren GPU. El análisis real sí: no hay
fallback CPU inventado para el worker CUDA actual. Sin pesos, iniciar análisis
devuelve el error de configuración existente, no descarga un checkpoint.

## GPU: opt-in, mismos modelos y mismo worker

```powershell
docker run --rm --gpus all nvidia/cuda:13.0.2-base-ubuntu24.04 nvidia-smi
# En .env configurar los dos archivos de pesos y un directorio exclusivo de demos.
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose -f compose.yaml -f compose.gpu.yaml exec backend python -c "import torch; print(torch.__version__, torch.version.cuda, torch.cuda.is_available(), torch.cuda.get_device_name(0))"
```

`OPERIX_PERSON_WEIGHTS_HOST` y `OPERIX_FORKLIFT_WEIGHTS_HOST` son archivos
individuales existentes, montados read-only como `/data/weights/person.pt` y
`/data/weights/forklift.pt`. No se crean rutas ausentes automáticamente.
PERSON operacional es YOLO11N_COCO_PERSON (`yolo11n.pt`), SHA
`0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`,
640 / 0,10 / NMS 0,70, filtro `person`. Es adopción explícita posterior a la evaluación,
no validación independiente nueva. El checkpoint adaptado anterior se conserva
como PRE_EVALUATION_PRIMARY_PERSON con sus resultados históricos. FORKLIFT v2
conserva SHA `1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6`,
640 / 0,45 / NMS 0,55. No se cambia ByteTrack ni reglas.
Para actualizar una instalación existente, apuntar OPERIX_PERSON_WEIGHTS_HOST al
archivo COCO verificado, reconstruir Backend y recrearlo. Los recibos Docker
anteriores describen el modelo de aquella fecha y no se modifican.

`OPERIX_INPUT_HOST` apunta solo a demos autorizadas; por defecto `assets/demo`.
No montar `Operix-experiments`, PERSON_FINAL_HOLDOUT_V2, TEST2, REAL_HOLDOUT_V2
ni sus directorios padre. No se copia ningún video o peso al contexto/imagen.
La carga manual desde la Web conserva el comportamiento nativo. La demo C es
opcional y requiere incorporación expresa al directorio autorizado y su ruta
interna en `OPERIX_DOCKER_DEMO_C`; no se busca ni monta automáticamente.

## Persistencia y límites

- `postgres_data`: base Docker independiente; no importa ni comparte datos nativos.
- `media`: PNG de eventos y outbox; respaldar junto con PostgreSQL.
- `sessions`: archivos temporales/resultados del análisis. Los archivos sobreviven
  al reinicio, pero el registro de sesiones es memoria del Backend y no se restaura.
  No se promete reanudar sesiones ni conservar su API tras reiniciar Django.
- `cache`: configuración/cachés de librerías; nunca pesos automáticos.

```powershell
docker compose down
docker compose up -d
```

Si se utilizó el override GPU, conservar ambos `-f` en las operaciones:
`docker compose -f compose.yaml -f compose.gpu.yaml down` y
`docker compose -f compose.yaml -f compose.gpu.yaml up -d`.

`down` conserva volúmenes y, por tanto, histórico y evidencia persistida. **`docker
compose down -v` elimina los volúmenes y sus datos**; no usarlo sin respaldo y una
decisión expresa. Las pruebas deben usar otro nombre de proyecto (`-p`) y una DB
nueva; no apuntar a PostgreSQL nativo ni a volúmenes ajenos.

Startup: espera conexión DB, aplica migraciones pendientes no destructivamente,
ejecuta `Django check` y arranca un único proceso Django con threads, sin autoreload.
Así conserva las sesiones en memoria y los callbacks HTTP del worker a
`127.0.0.1:8000` dentro del mismo contenedor. Es servidor de prototipo local, no
despliegue industrial. No se cargan datos demo falsos automáticamente.

## Codec y build

El worker exige H.264/`avc1`. El wheel público Linux de OpenCV 5.0.0.93 no ofreció
un encoder utilizable en la prueba sintética. El build compila **esa misma versión**
contra FFmpeg Debian; herramientas de compilación quedan en un stage separado.
La imagen debe pasar `codec_smoke.py` (tres frames sintéticos encode/decode) antes
de aceptarse. No se cambia el Motor, los codecs solicitados ni su lógica.
El primer build es más lento y la imagen Backend incluye el runtime CUDA del
wheel PyTorch, incluso cuando se usa solo infraestructura sin GPU reservada.

No se promete reconstrucción bit a bit: apt, registries y dependencias específicas
de plataforma requieren disponibilidad. Registrar identidades de imágenes y
versiones efectivas en la evidencia de validación. La ruta Windows/cu130 nativa
y su lock permanecen intactos.

## Comprobaciones

```powershell
docker compose config --quiet
docker compose exec backend python -m pip check
docker compose exec backend python manage.py check
docker compose exec backend python manage.py makemigrations --check --dry-run
docker compose exec -e OPERIX_TEST_ENGINE_PYTHON=/usr/local/bin/python backend python manage.py test --noinput
docker compose exec backend python -c "import cv2, torch, operix_engine; print(cv2.__version__, torch.__version__)"
```

Mantener secretos solo en `.env` local ignorado. Backend y Frontend corren con
usuarios sin privilegios; no se monta socket Docker ni se usa `privileged`.
No exponer API/media sin autenticación fuera de loopback. No ejecutar limpieza
global de Docker; CVAT y otros proyectos son independientes.
