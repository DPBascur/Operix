# Operix

Sistema inteligente para el análisis preventivo de riesgos operacionales mediante Visión Artificial.

## Propósito

> La IA percibe el entorno; las reglas interpretan el contexto.

Operix integra y evalúa percepción visual con reglas configurables para transformar
video en registros revisables de condiciones operacionales. No desarrolla un modelo
fundacional. Una detección o una condición satisfecha no confirma un accidente,
un Near Miss ni responsabilidad personal: requiere revisión humana.

## Estado del proyecto

MVP funcional de investigación en **Etapa 3**, con arquitectura conceptual **v1.0**
cerrada. El flujo Web/API → Motor → PostgreSQL → evidencia → histórico/indicadores
cuenta con pruebas de integración y ejecuciones locales controladas. Incluye
percepción experimental PERSON + FORKLIFT, zonas, reglas, recuperación de envíos,
interfaz de revisión y una alternativa Docker local con GPU NVIDIA.

Esto no representa un producto terminado ni validación industrial. CURRENT_PERSON
presentó una limitación importante de generalización en su evaluación independiente.
El [snapshot técnico](engine/evidence/ETAPA3-PROJECT-STATE.md) distingue implementación,
validación funcional, evaluación de modelos y pendientes académicos.

## Arquitectura

**Flujo conceptual:** video → detección → tracking → variables espacio-temporales
→ reglas configurables → evento → registro/histórico.

**Flujo técnico:** Frontend → Backend → worker/Motor → candidato → publicación HTTP
→ PostgreSQL y evidencia PNG → histórico/indicadores. Django lanza el worker
existente; el Motor no accede directamente a PostgreSQL. El journal conserva los
candidatos antes del envío; no existe un nuevo servicio de inferencia ni broker.

Los [seis diagramas y cinco ADR](docs/architecture/README.md) describen el diseño
aprobado, no una certificación de que todos sus componentes estén terminados.
Kubernetes, Redis, Celery y HAR quedan fuera del MVP inicial.

## Capacidades implementadas

- Ingreso de video local o demos, sesiones de análisis, preview y resultado MP4
  H.264 con reproducción, pausa y búsqueda.
- Detección dual experimental y ByteTrack por clase; identidades temporales
  `(clase, track_id)`, sin reconocimiento de personas.
- Zonas normalizadas configurables, pertenencia, permanencia, trayectorias y
  proximidad descriptiva entre clases.
- Reglas `zone_dwell` y `person_forklift_proximity`, con versión/parámetros,
  emisión por episodio y habilitación dependiente de configuración.
- Journal durable, retries acotados, replay sin inferencia e idempotencia;
  estados de análisis y persistencia diferenciados.
- Eventos en PostgreSQL, evidencia PNG recuperable, fuente y snapshots trazables.
  El MP4 completo corresponde a una salida temporal de sesión, no al registro
  persistente de cada evento.
- Histórico con filtros inclusivos por período y por ambos tipos; frecuencias
  diarias UTC y por tipo, separadas del dashboard ilustrativo.
- Detalle operacional con evidencia prioritaria, mediciones, tiempo de video,
  base temporal explícita y trazabilidad técnica desplegable.

La fecha UTC de una sesión subida usa el inicio del análisis como ancla; no se
presenta como fecha real de grabación. Los umbrales no son estándares universales.

## Stack

| Componente | Tecnología |
| --- | --- |
| Web | Next.js 16.4.0, TypeScript, Node 24.2.0, pnpm 11.28.2 |
| Backend/API | Python 3.12, Django, Django REST Framework |
| Persistencia | PostgreSQL |
| Motor | OpenCV, YOLO11, ByteTrack, tipos propios desacoplados |
| Entorno NVIDIA fijado | PyTorch 2.14.0+cu130, CUDA runtime 13.0, Ultralytics 8.4.146, lap 0.5.12 |
| Alternativa local | Docker Compose: PostgreSQL, Backend/worker y Frontend; GPU opcional |

## Modelos y evaluación

| Configuración | Rol vigente | Resultado y alcance |
| --- | --- | --- |
| PRE_EVALUATION_PRIMARY_PERSON (CURRENT_PERSON en el protocolo) | Primaria histórica evaluada; 640 / confidence 0,10 / NMS 0,70 | Holdout PERSON: precision 0,339, recall 0,119, F1 0,176; limitación importante de generalización |
| YOLO11N_COCO_PERSON | Operacional de desarrollo/finalización, adoptado post-evaluación; mismo operating point | Precision 0,557, recall 0,899, F1 0,688; desempeño sustancialmente superior en ese conjunto; adopción posterior explícita, sin validación independiente nueva |
| FORKLIFT specialist v2 | Baseline experimental congelado; 640 / confidence 0,45 / NMS 0,55 | Validation propia: TP 273, FP 18, FN 15; no equivale a validación industrial ni al holdout PERSON |

PERSON se evaluó con matching 1:1 IoU ≥0,50 en **91 imágenes únicas**, 67 positivas,
24 negativas y 168 cajas, conservando los 92 registros originales. Dataset y
protocolo fueron congelados y los resultados sellados antes de revisar errores.
Posibles omisiones/ambigüedades del GT limitan la interpretación de FP y negativos;
no se corrigió el GT ni se recalcularon métricas. La elección posterior de COCO
es una decisión de ingeniería informada por esos resultados; el mismo holdout
no constituye validación independiente de la configuración elegida post-hoc.
**PERSON v2: no iniciado/diferido**.
La [decisión operacional y regresión](engine/evidence/etapa3-experimentos.md#decisión-operacional-person-post-evaluación--25-10-2026)
registra la adopción sin reabrir la evaluación.
Hashes, resultados completos y límites: [evidencia experimental](engine/evidence/etapa3-experimentos.md#ejecución-person-evaluation-protocol-v1--24-10-2026).

## Repositorio y ejecución nativa

```powershell
git clone https://github.com/DPBascur/Operix.git
cd Operix
git switch dev
```

`dev` es la rama de desarrollo; `main` se promueve solo tras validación. El tag
`v0.1.0` conserva el hito histórico del pipeline base y no representa todo el
estado actual de Etapa 3.

| Guía | Contenido |
| --- | --- |
| [Motor](engine/README.md#entorno-local) | Python 3.12 x64, instalación Windows/CUDA o CPU, lock, pesos y scripts |
| [Backend](backend/README.md#requisitos-y-configuración) | PostgreSQL propio, entorno/secretos locales, migraciones y servidor API |
| [Frontend](frontend/README.md#instalación-y-ejecución) | Node/pnpm fijados, instalación, URL API y ejecución Web |
| [Demo](assets/demo/README.md) | Entradas sintéticas autorizadas y reproducción del pipeline histórico |
| [Evidencias](engine/evidence/README.md) | Índice técnico por capacidad, evaluación y límites |

Crear los entornos indicados en cada guía. El Backend requiere configurar su
`.env` local y cargar esas variables antes de migrar/iniciar; Frontend usa
`NEXT_PUBLIC_DATA_SOURCE=api` y la URL pública del Backend para la integración.
El análisis dual necesita los dos checkpoints locales verificados; no se descargan
al arrancar. Login/usuarios son una demo local: no autentican ni protegen la API.

El lock Windows/CUDA fija Ultralytics 8.4.146 para las evidencias correspondientes.
Una instalación genérica no fijada puede resolver otra versión compatible; la
prueba CPU histórica con 8.4.166 no modifica los resultados del entorno fijado.
La instalación CPU del Motor no implica soporte CPU del worker web CUDA.

## Tests y validación

Regresión de esta consolidación: Motor **351 aprobadas + 2 integraciones opt-in
omitidas**; Backend **103/103** con PostgreSQL; Frontend **30/30**, lint, typecheck
y build. Son pruebas funcionales, no una garantía de precisión de percepción.

Desde la raíz, con el entorno del Motor instalado:

```powershell
.\engine\.venv\Scripts\python.exe -m pip check
.\engine\.venv\Scripts\python.exe -B -m unittest discover -s engine/tests
.\engine\.venv\Scripts\python.exe engine/scripts/check_environment.py --require-cuda
```

Omitir `--require-cuda` para comprobar un entorno CPU. Desde Backend, con su entorno
cargado: `manage.py check`, `makemigrations --check --dry-run`, `test --noinput`.
Desde Frontend: `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm build`.

La [matriz de validación](engine/evidence/ETAPA3-VALIDATION-MATRIX.md) separa fixtures
E2E, carga controlada, rendimiento exploratorio y pruebas GPU previas. OP-43 es un
benchmark histórico independiente: sus FPS no se atribuyen al pipeline dual actual.
Esta consolidación no reejecuta el holdout ni campañas de stress/rendimiento.

## Docker local y GPU

Alternativa al camino nativo, validada funcionalmente en el equipo de desarrollo
utilizado durante el proyecto, incluyendo ejecución del Motor mediante GPU NVIDIA.
En Windows, GPU requiere Docker Desktop con WSL2 y driver NVIDIA compatible.

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.docker.example .env }
# Configurar secretos propios en .env antes de continuar.
docker compose up -d --build
docker compose ps
# GPU: configurar también las rutas individuales de pesos y demos en .env.
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
# Detención sin borrar datos:
docker compose down
```

En modo GPU, detener con `docker compose -f compose.yaml -f compose.gpu.yaml down`.
Frontend `http://localhost:13000`; API `http://localhost:18000/api/v1/health/`.
**`docker compose down -v` elimina los volúmenes y sus datos**.
DB/media/salidas tienen volúmenes propios; no se importa la DB nativa. Los archivos
persisten al recrear Backend, pero su registro de sesiones en memoria no se restaura.
La [guía Docker](deployment/docker/README.md) explica mounts read-only, codec,
healthchecks y límites; la [validación local](engine/evidence/DOCKER-LOCAL-VALIDATION.md)
y su recibo documentan el E2E GPU de 277 frames y la prueba de persistencia.

## Datos, evidencia y resguardos

Pesos, datasets, holdouts, videos de ejecución y artefactos experimentales crudos
permanecen fuera de Git. Excepción revisada: los tres MP4 sintéticos/de salida de
[assets/demo](assets/demo/README.md), con atribución y licencia de terceros.
La evidencia técnica versionada se encuentra en [engine/evidence](engine/evidence/README.md)
y [backend/evidence](backend/evidence/). Los artefactos locales externos no están
implícitamente disponibles al clonar. Cada nueva fuente requiere derechos propios.

## Limitaciones conocidas y alcance ético

- CURRENT_PERSON tiene baja cobertura en el holdout independiente; no es un
  detector validado industrialmente. COCO fue adoptado después como configuración
  operacional de desarrollo, sin nueva validación independiente; PERSON v2 sigue diferido.
- Validación experta de zonas/umbrales pendiente; distancias de imagen normalizadas
  no son metros ni medidas calibradas de seguridad.
- ByteTrack depende de detecciones; sin GT MOT no se afirman MOTA/IDF1/HOTA ni
  continuidad fiable universal. Las muestras y la validación son acotadas.
- Una persona dentro de su propio forklift sigue siendo PERSON válida. La asociación
  contextual operador/vehículo para evitar relaciones irrelevantes queda pendiente.
- API sin autenticación empresarial, retención operacional/acceso sin política final;
  login y roles demo no sustituyen esos controles. Mantener despliegue local controlado.
- Docker se validó en este equipo; no garantiza compatibilidad de cualquier GPU,
  despliegue industrial ni reconstrucción bit a bit. No se afirma tiempo real universal.
- No hay reconocimiento facial; `track_id` no es identidad real. No se asigna
  culpabilidad ni se aplican sanciones automáticas. Evento no equivale a accidente
  ni a Near Miss; toda interpretación operacional requiere revisión humana.

## Datos de demostración

Estas muestras sintéticas proceden de **NVIDIA PhysicalAI WorldModel Synthetic
Warehouse Operations Scenes** y están sujetas a **OpenMDW-1.1**. No son
registros de una empresa ni constituyen validación industrial.

### Interacción persona–montacargas

Esta muestra permitió revisar la detección de `person` y documentar que los
pesos COCO no incluyen una clase explícita `forklift`.

https://github.com/user-attachments/assets/93648968-ae9e-4c66-aef2-c04be7ff2bae

[MP4 original](assets/demo/forklift_human_nearmiss_ceiling00.mp4) ·
[Evidencia OP-34](engine/evidence/OP-34-yolo11-detection.md) ·
[Procedencia y licencia](third_party/nvidia-warehouse-dataset/NOTICE.md)

### Procesamiento de una muestra

La entrada y la salida anotada se presentan juntas para facilitar la
comparación visual del pipeline.

#### Entrada

https://github.com/user-attachments/assets/82707306-f3de-40d4-b8fd-fb3f3c292fee

#### Resultado de Operix

https://github.com/user-attachments/assets/1271a029-4057-421e-a13b-72baf02d08e0

Las cajas, clases e IDs temporales muestran resultados del detector y del
seguimiento; las líneas representan trayectorias visuales. No indican identidad
personal ni una precisión industrial medida.

[MP4 de entrada](assets/demo/warehouse_fire_ceiling04.mp4) ·
[MP4 anotado](assets/demo/warehouse_fire_ceiling04_operix_annotated.mp4) ·
[Guía de demo](assets/demo/README.md) ·
[Evidencia del PoC](engine/evidence/OP-61-poc.md)


## Licencia

Copyright (C) 2026 Daniel Felipe Peña Bascur.

El código fuente propio de la versión académica de Operix se distribuye bajo
**GNU Affero General Public License v3.0 or later** (`AGPL-3.0-or-later`).
Daniel Felipe Peña Bascur conserva la titularidad de su código original; los
términos completos de la licencia están en [LICENSE](LICENSE).

Los materiales de terceros conservan sus propias licencias y condiciones; no
quedan relicenciados por la licencia del código Operix. Consultar los
[avisos de terceros](THIRD_PARTY_NOTICES.md).

Los clips NVIDIA incluidos en `assets/demo/` no son propiedad de Operix y
no se relicencian bajo AGPL-3.0-or-later. Conservan la licencia OpenMDW-1.1 y
la atribución indicadas en su
[NOTICE](third_party/nvidia-warehouse-dataset/NOTICE.md).
