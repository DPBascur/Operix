# Docker local — auditoría y validación controlada

Base nativa: `accda3563fe52c9736cf4d9c4b8d31195065aeba`, rama `dev` limpia y
sincronizada antes del trabajo. La containerización es una alternativa al camino
nativo, no cambio de arquitectura v1.0. No introduce servicio Motor, API de
inferencia, broker, proxy ni migración automática de datos nativos.

## Auditoría de runtime y filesystem

| Componente | Runtime nativo | Requisito Docker | Dependencia filesystem | GPU | Persistencia | Riesgo |
| --- | --- | --- | --- | --- | --- | --- |
| Frontend | Node 24.2.0, pnpm 11.28.2, Next 16.4.0 | Build con lockfile y política pnpm existentes; standalone Next | Código, lock, marca pública | No | No | URL pública fijada en build; no usar hostname interno desde navegador |
| Backend | Python 3.12.10, Django 5.2.18, DRF 3.18.3 | Mismos pins; un proceso threaded sin autoreload | Configuración por entorno | Solo al lanzar worker real | DB y media | Varios procesos romperían el registro de sesiones en memoria |
| Motor/worker | Python 3.12.10, torch 2.14.0+cu130, Ultralytics 8.4.146, lap 0.5.12 | Wheel cu130 Linux, bibliotecas CUDA transitivas | Código y config; dos checkpoints individuales read-only | Sí para análisis web actual | Outputs y outbox | No inventar fallback CPU ni promover COCO |
| OpenCV/video | OpenCV 5.0.0.93, H.264 avc1 | Misma versión compilada contra FFmpeg Debian | MP4 de entrada y salida | Encoder software | Resultado temporal | Wheel público Linux falla la prueba avc1; no cambiar lógica del worker |
| PostgreSQL | 17.11 local | Imagen oficial 17.11, volumen exclusivo y pg_isready | Volumen Docker propio | No | Sí | No compartir data directory ni importar DB nativa |
| Evidencia | PNG bajo OPERIX_MEDIA_ROOT, referencia FileField | Volumen media escribible por UID 10001 | DB + bytes respaldados juntos | No | Sí | No conservar solo DB; no publicar archivos sensibles |
| Sesiones | tempfile + registro en memoria | TMPDIR en volumen sessions | Previews/MP4 y archivos de sesión | Según worker | Archivos, no registro RAM | Reinicio no reanuda sesiones ni restaura su API |

Código contrastado: `backend/config/settings.py`, `apps/analysis/sessions.py`,
`apps/events/views.py`, `stream_dual_perception.py`, adaptadores del Frontend y
lockfiles. Django lanza el mismo script con OPERIX_ENGINE_PYTHON; el callback HTTP
permanece en loopback del contenedor. La API health comprueba `SELECT 1` en PostgreSQL.

## Host comprobado

Docker Desktop 4.90.0; Engine/CLI 29.7.2; Compose 5.5.1; WSL 3.0.3.0,
distribución docker-desktop WSL2 y kernel 6.18.54.1-microsoft-standard-WSL2.
No se modificó configuración del host. GPU oficial precheck: imagen
`nvidia/cuda:13.0.2-base-ubuntu24.04`, digest
`sha256:2ab6381d970b211fb93853796dc6707eb8a72575a375c422b17cf4d8b2641701`;
`nvidia-smi` devolvió RTX 3070, driver 616.92, 8192 MiB y exit 0.
No se montaron datos ni se cargaron modelos en esa prueba.

Se confirmó disponibilidad Linux de torch 2.14.0+cu130 en el índice PyTorch,
sin actualizar dependencias nativas. Bases: Python 3.12.10-slim-bookworm,
Node 24.2.0-bookworm-slim y PostgreSQL 17.11-bookworm. La compilación específica
de OpenCV responde a compatibilidad de codec, no a optimización del Motor.

## Regresión nativa

- Motor: 353 tests, 351 aprobados y 2 integraciones reales omitidas.
- Backend: 103/103; Django check PASS y migration check sin cambios.
- Frontend: 30/30; lint, typecheck y build PASS con Node/pnpm fijados.
- pip check de ambos entornos Python: PASS.

El pnpm global del equipo no coincide con el proyecto: se usó el runtime local
ya existente 24.2.0/11.28.2, sin instalar ni cambiar configuración global.
El build Docker copia también pnpm-workspace.yaml antes de instalar, conservando
la política existente de scripts de dependencias; no se alteró el lock.

## Aislamiento de la validación

Proyecto de pruebas `operix-docker-qa`, credenciales aleatorias fuera de Git,
PostgreSQL nuevo sin puerto publicado, API 18000 y Frontend 13000 solo loopback.
Los contenedores y volúmenes CVAT preexistentes no se modifican. No se usan dumps
nativos ni se montan directorios experimentales completos. Las pruebas GPU solo
pueden usar demos autorizadas y archivos de pesos individuales verificados.

## Resultados efectivos — 24 de octubre de 2026

Estados comprobados: **OPERIX_DOCKER_LOCAL_READY**, **OPERIX_DOCKER_GPU_READY**
y **NATIVE_PATH_PRESERVED**. El [recibo de versiones y resultados](docker-local-receipt.json)
registra imágenes, modelos, hashes y pruebas; identifica la base más los cambios
locales Docker validados antes del commit, no atribuye esa imagen al árbol limpio
del commit base. Logs, credenciales, PNG y MP4 de ensayo permanecen fuera de Git.

- Build Backend/Frontend: PASS. Contexto Backend observado aproximadamente 1,59 MB;
  ningún video, checkpoint, `.env`, DB ni directorio experimental en la imagen.
- OpenCV: mismo paquete 5.0.0.93, compilado con FFmpeg Debian 5.1.9; prueba de tres
  frames sintéticos H.264 encode/decode PASS en builder y runtime. Compilarlo tomó
  unos 782 s; el rebuild posterior reutilizó esa capa. No es un rebuild sin caché.
- Docker Motor: 353 descubiertas, 351 aprobadas, 2 omitidas (modelos reales opt-in).
- Docker Backend: **103/103**, incluidas integraciones Motor/HTTP/PostgreSQL con
  percepción fixture, usando `OPERIX_TEST_ENGINE_PYTHON=/usr/local/bin/python`.
  Django check, migration check y pip check PASS. Frontend productivo build PASS.
- Dos supuestos de pruebas se corrigieron sin tocar código productivo Backend:
  intérprete de Motor configurable también en la prueba web y allowlist CORS
  explícita dentro de su test. El primer intento Linux falló esos supuestos;
  la suite final completa aprobó. Backend nativo revalidado después: **103/103**.
- Infra sin reserva GPU: Frontend → API health → PostgreSQL PASS. Dos eventos
  sintéticos `TEST_DATA_DOCKER`; filtro período/tipo y frecuencias UTC devolvieron
  el único registro esperado. PNG recuperado idéntico al enviado.
- Navegador sobre Frontend Docker: API conectada, histórico con eventos, detalle
  del evento GPU con regla, tiempos y enlace a PNG; no solo comprobación de HTML.

## Análisis GPU autorizado y arranque nuevo

Demo A `warehouse_fire_ceiling04.mp4`, SHA-256
`3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`.
CURRENT PERSON y FORKLIFT conservaron los hashes documentados en la guía Docker;
no se cambiaron parámetros, configuración operativa ni selección de modelos.
CUDA disponible en PyTorch 2.14.0+cu130, runtime 13.0, RTX 3070 real.

API → Backend → worker existente → GPU → candidatos → PostgreSQL → evidencia
→ histórico: **PASS**. 277/277 frames, 3 candidatos, 3 eventos guardados,
0 fallidos. Video 1920×1080 / 30 FPS / H.264, 277 frames decodificados completos,
2.998.261 bytes. No se confunden condiciones satisfechas con incidentes confirmados.

- PNG SHA-256: `8A78836FC15973287BDB2ECB66DF62800A62752ACE645BE2F3DCD935DC60081A`.
- MP4 SHA-256: `9BE38A02679DA3243F5C182383C2A5F7A077B083FB9AEDF8820A7271E93ECD48`.
- Tiempo pared observado hasta recuperar salidas: 29,557 s; repetición desde
  segundo proyecto con volúmenes nuevos: 26,540 s. Son observaciones exploratorias,
  no FPS del Motor ni comparación científica nativo/Docker. No se midió arranque
  nativo comparable ni se reinició su servicio para fabricar una comparación.
- Segundo proyecto `operix-docker-fresh-qa`: DB inicialmente con 0 eventos,
  migraciones automáticas, tres servicios saludables, GPU visible, E2E infra y
  análisis real nuevamente PASS. `up --wait` observado: 28,380 s, con imágenes ya
  construidas; no incluye el build. Sin reutilizar estado de contenedores/volúmenes.

## Persistencia, seguridad y limpieza

`down`/`up` recreó contenedores y conservó histórico/filas, PNG con el mismo hash
y MP4 `annotated.mp4` con el mismo hash. **El registro RAM de sesiones no se
restaura**, aunque sus archivos persisten; no se promete recuperación de su API.

Backend UID 10001 y Frontend UID 1000. Solo Backend reserva una GPU; checkpoints
e input read-only; PostgreSQL sin puerto publicado; Web/API en loopback. Sin modo
privilegiado, socket Docker, secretos de build ni copias de datos nativos. Callback
del worker usa loopback dentro de Backend; navegador usa puerto público del host;
Frontend alcanza también health por DNS interno. UTC del contenedor y frecuencias
explícitas; sin scripts shell susceptibles a CRLF. Los puertos alternativos
evitaron interferencia con el modo nativo y CVAT.

Se eliminan únicamente contenedores/redes/volúmenes de los dos proyectos QA
desechables al cerrar la campaña, después de guardar recibos y salidas fuera del
repositorio. No se ejecuta prune global ni se tocan recursos CVAT o DB nativa.

## Alcance y límites

Se habilitó un entorno contenedorizado reproducible y se validó funcionalmente
en el equipo de desarrollo utilizado durante el proyecto. Docker es opcional.
No hay despliegue industrial, garantía universal de GPU ni servidor multiworker.
La imagen Backend es grande (aprox. 3,43 GB según Docker) por sus dependencias
CUDA; la infraestructura CPU usa esa imagen sin solicitar GPU. El primer build
requiere red y tiempo para OpenCV; no se promete identidad bit a bit de futuros
builds contra apt/registries. El lock Linux fija dependencias de esa plataforma;
los locks y dependencias nativas permanecen intactos. La adquisición de pesos es
explícita, nunca automática al arrancar.

CURRENT PERSON mantiene su condición de configuración primaria evaluada y su
limitación de generalización observada. COCO sigue REFERENCE_BASELINE. No se abrió,
montó ni utilizó PERSON holdout, TEST2 o REAL_HOLDOUT_V2; no hubo entrenamiento.
