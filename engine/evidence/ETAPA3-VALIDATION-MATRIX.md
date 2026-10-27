# Etapa 3 — matriz de implementación y validación preliminar

## Reconciliación vigente de cierre — 24-10-2026

Esta matriz reúne resultados y trazabilidad de los cortes del 23 y 24 de octubre.
El estado posterior y la validación de v0.2.0 se documentan en la
[auditoría técnica](ETAPA4-TECHNICAL-AUDIT.md#24-final-v020-release-gate-pass--26-10-2026).
No sustituye el Product Backlog ni la aceptación académica. El corte siguiente
corresponde a `85c064136233638a2a560357b9a2403086578f73`; el
[índice](README.md) organiza las evidencias por tema.

| Requisito | DESIGN | IMPLEMENTATION | VALIDATION / pendiente |
| --- | --- | --- | --- |
| RF-01 | Ingreso de video | Lectura, upload/demo, sesión y worker | Tests secuenciales y E2E controlados; formatos/entornos acotados |
| RF-02 | Percepción de personas/equipos móviles | Canales PERSON + FORKLIFT | Evaluación PERSON V1 ejecutada y sellada; CURRENT con baja generalización; FORKLIFT validation propia. No fiabilidad industrial general |
| RF-03 | IDs temporales | ByteTrack por clase, identidad compuesta | Tests de continuidad y revisión de clips; falta GT MOT formal |
| RF-04 | Zonas configurables | Config/edición normalizada, geometría y pertenencia | Unitarios/fixtures; geometría operacional por validar con experto |
| RF-05 | Reglas sobre objetos/zona/tiempo | zone_dwell y person_forklift_proximity | Episodios, límites y pares probados; validez de thresholds/contexto sigue pendiente |
| RF-06 | Evento con metadata/evidencia | Journal, HTTP, PostgreSQL, PNG y resultado temporal MP4 | E2E fixture y demo GPU previos; recuperación acotada, sin transacción distribuida |
| RF-07 | Consulta por tiempo/tipo | Filtros API y Web para dos tipos | Carga mixta conciliada; sin garantía industrial de escala |
| RF-08 | Indicadores históricos básicos | Frecuencias UTC/día/tipo y dashboard API | Conteos conciliados; no tasas verificadas de incidentes |
| RNF-01 | Regla/versión/parámetros trazables | Snapshots, source/run/par/frame, idempotencia | Tests y E2E; ancla UTC proxy explícita; sin inventar cierre de episodio |
| RNF-02 | Medición con entorno | Instrumentación, benchmark histórico y evidencia posterior | Alcance parcial: métodos distintos, sin tiempo real universal ni nueva campaña |
| R-01 | Datos autorizados/controlados | Provenance y exclusiones, artefactos fuera de Git | Verificación previa por fuente documentada; no autorización genérica ni nueva auditoría jurídica |
| R-02 | Confidencialidad/uso académico | Loopback, separación de datos, retención manual | PARTIAL: acceso/auth/retención operacional definitivos pendientes |
| R-03 | Sin biometría ni sanciones automáticas | IDs temporales y advertencia de revisión humana | Compatible con alcance implementado; ningún candidato confirma culpa/incidente |
| PV-01 | Parámetros sujetos a contexto | Configuración y snapshots efectivos | PARTIAL: pruebas de límites no sustituyen validación experta |
| PV-02 | Roles/canales/alertas sujetos a validación | Login/usuarios demo; sin RBAC Backend | Decisión experta pendiente; no se impone una implementación nueva |

Regresión del corte: Motor 351 PASS + 2 SKIP (353 descubiertas), Backend 103/103,
Frontend 30/30, lint/typecheck/build; Django/migrations/pip y Compose config/smoke
sintético PASS. Se reutilizan resultados PERSON/Docker/performance sellados y
documentados; no se ejecutan nuevamente detectores ni conjuntos protegidos.
Docker local/GPU está validado en el equipo documentado y el modo nativo se conserva.

## Base y límites

Las secciones anteriores a **Persistencia operacional por pares** conservan la auditoría histórica de
la primera validación. Sus estados PARTIAL/MISSING describen aquella base;
la actualización del 24-10-2026 al final registra el estado posterior comprobado.

Auditoría del 23-10-2026 sobre `dev`, base `8cea9eb7dc134b506ab8c6eba14e88c865bb531c`.
Fuente de aceptación: Backlog V0.11, hojas **Backlog General** y **Levantamiento**.
La arquitectura v1.0 no cambia. Implementación, validación funcional y evaluación
de exactitud son estados distintos. Un evento significa condición configurada
satisfecha, no incidente, Near Miss ni responsabilidad personal.

PERSON final en aquel inventario: `WAITING_FOR_HUMAN_ANNOTATION`; cinco familias 101–105 y 92 imágenes
reservadas. No inferencia, nueva selección, cambio de sampling ni freeze. TEST2
permanece protegido; YouTube es `DIAGNOSTIC_ONLY`; TEST3 es desarrollo.
Los hashes de los cinco paquetes CVAT se comprobaron contra el manifest de
adquisición: 20/20/12/20/20 frames, todos PASS, sin abrir imágenes ni ejecutar modelos.
FORKLIFT v2 conserva SHA `1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6`,
640, confidence 0.45 y NMS 0.55. No se entrena ni calibra en esta campaña.

## Cobertura inicial de requisitos

| Requisito | OP | Estado real inicial | Evidencia | Trabajo faltante / prioridad |
| --- | --- | --- | --- | --- |
| RF-01 | 33 | IMPLEMENTED / VALIDATED funcionalmente | `test_video_processor.py`, OP-33/61 | Mantener regresiones / P1 |
| RF-02 | 34 | IMPLEMENTED / PARTIAL evaluación | `dual_perception.py`, `etapa3-experimentos.md` | Evaluación PERSON final bloqueada por anotación / P1 |
| RF-03 | 35,37,60 | IMPLEMENTED / VALIDATED funcionalmente | `test_byte_tracker.py`, `test_spatiotemporal.py`, OP-35 | No hay GT MOT; no afirmar exactitud industrial / P1 |
| RF-04 | 30,36 | IMPLEMENTED / VALIDATED por tests | `test_zone_geometry.py`, `zone-editor-geometry.test.mjs` | Revisión experta de geometría/contexto / P1 |
| RF-05 | 30,38 | IMPLEMENTED / VALIDATED por fixtures | `test_rules.py`, `test_pair_rules.py` | Umbrales experimentales; aprobación contextual pendiente / P1 |
| RF-06 | 29,39 | PARTIAL | `event_publishing.py`, `events/tests.py`, OP-39 | Persistencia CLI zone_dwell real; web/pares aún transitorios / P0 |
| RF-07 | 31,40 | IMPLEMENTED para contrato vigente / PARTIAL por tipo | `events/tests.py`, OP-40 | Solo existe zone_dwell persistente; no demostrar discriminación entre dos tipos reales / P0 |
| RF-08 | 32,41 | IMPLEMENTED / VALIDATED para histórico vigente | `test_frequencies.py`, `history-model.test.mjs`, OP-41 | Mantener separación demo/API y conciliación independiente / P1 |
| RNF-01 | 39 | PARTIAL | Snapshot de regla/versión/parámetros en Event | Pares/web no persistentes; no inventar snapshots históricos / P0 |
| RNF-02 | 43,45 | PARTIAL para estado actual | OP-43 y métricas exploratorias posteriores | Benchmark dual actual y latencia API; no comparar entornos incompatibles / P1 |
| R-01 | 16,18,42 | VALIDATED para fuentes documentadas | OP-16/18/42 y registro local DVIDS | Verificar cada nuevo recurso; no autorización genérica / P1 |
| R-02 | 42 | PARTIAL | Datos fuera de Git, API loopback, medios relativos | Sin autenticación real ni retención de eventos persistentes; no producción pública / P2 |
| R-03 | 42 | IMPLEMENTED dentro del alcance | Identidades temporales; sin biometría ni sanción | Revisión humana contextual sigue siendo necesaria / P1 |
| PV-01 | 30,38,46 | PARTIAL | Config JSON y pruebas de límites temporales/espaciales | Validación experta; no elevar ejemplos a parámetros universales / P1 |
| PV-02 | 46 | BLOCKED por validación experta | Roles/login UI son DEMO_ONLY, no control Backend | No imponer alertas/RBAC sin decisión humana / P2 |

### Denominador verificable de implementación

Se cuentan una sola vez las tareas técnicas de implementación/entorno de EP-03,
EP-04 y EP-05: **OP-33–41, OP-59 y OP-60: 11 tareas**. Las historias 29/30/31/32
no se suman otra vez a sus tareas; OP-42 es resguardo documental, no implementación.
Arquitectura, gestión y evaluación tampoco se cuentan como código implementado.

Revisión conservadora: 33/34/35/36/37/38/41/59/60 tienen implementación y evidencia
de su aceptación técnica: **9/11 = 81,82 %**. OP-39 y OP-40 se mantienen **PARTIAL**
por las fronteras descritas. Antes/después de la campaña: 9/11.
No es porcentaje de todo el backlog ni nota académica, ni equivale a exactitud
validada de PERSON. El Excel conserva su estado original: esta matriz registra
la reconciliación técnica sin sobrescribir macros, actas ni estados académicos.
El 81,82 % demuestra avance del **núcleo técnico delimitado**, no acredita por sí
solo el 50 % de un denominador académico global no acordado. OP-29/31/32 son
historias superiores y OP-44/45 validación; no se ocultan ni se marcan completas.

## Flujo real y simulaciones

| Tramo | Clasificación | Alcance |
| --- | --- | --- |
| Web → sesión Backend → worker Motor → MP4 | REAL | Temporal, sin publicación automática de eventos |
| Motor → candidates JSON → estado web | ADAPTER | Solo último frame; no histórico completo |
| CLI video → EventCandidate zone_dwell → HTTP → PostgreSQL | REAL | Publicación explícita; evidencia PNG del frame |
| API de eventos → filtros → frecuencias → dashboard API | REAL | Histórico persistido, no evaluaciones de riesgo |
| Dashboard de ejemplo, login y usuarios locales | DEMO_ONLY | No autentican ni protegen la API |
| PairEventCandidate → Event persistente | MISSING | Requiere contrato y política explícita; no fingir soporte |

## Matriz de pruebas ejecutadas

| ID | Objetivo/requisito | Precondición y entrada | Esperado | Observado | Estado/evidencia |
| --- | --- | --- | --- | --- | --- |
| E3-MOTOR-BASE | Regresión Motor RF-01–05 | Entorno instalado; fixtures sin modelos | Suite sin fallos; integraciones con pesos omitidas | 301 tests, 299 aprobados, 2 omitidos | PASS; unittest discover |
| E3-API-BASE | Persistencia, filtros, errores RF-06–08 | PostgreSQL local; DB temporal Django | Sin fallos ni migraciones pendientes | 75/75 tests, check OK, no changes detected | PASS; Django test/check |
| E3-E2E-01 | Video→candidate→HTTP→DB→evidencia→consulta→indicador | LiveServer, PostgreSQL de tests; video MJPG de 4 frames; percepción fixture | Un evento y PNG recuperable; retry sin duplicado; nueva ejecución separada | Un evento al frame 2, retry conserva ID; otra ejecución crea segundo evento; agregado reconcilia | PASS; `backend/apps/events/test_motor_integration.py` |
| E3-PNG-01 | RF-06 evidencia legible y acotada | IHDR/CRC válidos con IDAT ilegible, vacío, filtro inválido o expansión excesiva | HTTP 400 sin guardar imagen; PNG correcto sigue recuperable | Antes: 201/200 aceptaban datos inválidos; después: rechazo controlado; Adam7 válido aceptado | PASS; `EventEvidenceTests` |
| E3-TIME-01 | RNF-01/RF-05–06 conservar igualdad temporal | Permanencia y umbral 1/30 s; control inferior 0.033 s | Aceptar la igualdad sin bajar el umbral, rechazar el control inferior | Transporte a 9 decimales, PostgreSQL numeric(18,9), tolerancia numérica 1e-9 s; E2E al frame 1 | PASS; test de transporte, API y LiveServer |
| E3-RETRY-01 | RF-06 recuperación acotada | Timeout→éxito; 503 persistente; 400; imagen fallida | Reutilizar candidato/PNG/UUID; máximo 3 intentos; no repetir error permanente | Pipeline recupera un candidato, conserva ID parcial y reporta intentos | PASS; `test_video_event_pipeline.py` |
| E3-FAIL-01 | RF-06/R-02 fallos controlados | DatabaseError al crear evento; PermissionError al guardar PNG | 503 sin datos privados ni cambios parciales de metadata | Ambos fallaban sin manejar antes; ahora conservan histórico/metadata y no exponen el mensaje interno | PASS; `EventApiTests`, `EventEvidenceTests` |
| E3-STRESS-01 | RF-07–08/RNF-02 histórico controlado | 1.000 filas TEST_DATA_STRESS en PostgreSQL de tests; cinco filtros; 63 consultas temporizadas | Lista y agregados coinciden con Counter independiente; sin tocar histórico de desarrollo | Conciliación exacta, consultas HTTP 200; resultados opcionales fuera de Git | PASS; `test_validation_stress.py` |
| E3-RULE-01 | RF-05/PV-01 límites e independencia de pares | Fuera de zona/distancia, uno ausente, igualdad, float, reset y múltiples pares | Emitir una vez por episodio; no recalcular geometría ni relajar distancia | Casos conservados en la suite vigente | PASS funcional; `test_pair_rules.py`, `test_rules.py` |
| E3-TRACK-01 | RF-03 continuidad funcional | Detecciones sintéticas: movimiento, dos objetos, pérdida breve/larga, reset | Recuperar ID breve; nuevo ID tras buffer; identidad separada | Sin regresión en suite Motor | PASS funcional; `test_byte_tracker.py`, `test_spatiotemporal.py`; sin GT MOT |
| E3-WEB-01 | RF-07–08 fuente de datos y estado de API | Build de producción, origen local permitido, 25 filas de desarrollo | Diferenciar ejemplo/API, health real y conteo coincidente | API conectada; ejemplo 64, API 25; tabla 25, zonas 22+2+1 | PASS acotado; revisión de navegador y captura local |
| E3-FINAL-01 | Regresión transversal | Python 3.12.10, PostgreSQL real, Node 24.2.0/pnpm 11.28.2 | Suites y comprobaciones sin fallos | Motor 306: 304 PASS + 2 SKIP; Backend 85/85; Frontend 21/21; lint/tipos/build PASS | PASS; 412 descubiertas, 410 aprobadas, 2 omitidas |

La prueba E3-E2E-01 usa lectura OpenCV, analizador, regla, renderer, HttpEventSink,
Django y PostgreSQL reales. Detector/tracker son fixtures deterministas: demuestra
integración, **no evalúa ningún modelo**. Sus filas solo existen en la DB temporal
destruida por Django y sus imágenes se conservan únicamente durante el test.
Resumen local: `etapa3-autonomous-2026-10-23/baseline/motor-http-postgresql-smoke.json`.

## Hitos publicados y cambios observables

| Commit | Mejora / antes → después | Alcance y límite |
| --- | --- | --- |
| `ee541a6` | Integración sin prueba transversal → LiveServer HTTP + PostgreSQL + Motor + PNG + consulta/agregado | Percepción fixture, no exactitud de modelos |
| `bee649e` | PNG con IDAT ilegible aceptado → scanlines/zlib acotados y rechazo HTTP 400 | No es un decodificador PNG completo |
| `19a8402` | 1/30 s truncado a 0.033 y rechazado → 0.033333333 aceptado sin bajar umbral | Migración numeric(18,9), sin reescribir observaciones históricas |
| `22a9421` | Fallo transitorio aborta publicación → máximo tres intentos de la misma identidad/imagen | Solo errores reintentables; no 400/409; replay separado no cambia |
| `7ff24ee` | DatabaseError/OSError sin respuesta API controlada → HTTP 503 genérico | No revela el texto interno ni inventa éxito |
| `67d1c6e` | Sin carga histórica conciliada → test reproducible con 1.000 filas y Counter independiente | Solo DB temporal de tests, no carga industrial |

No hay una optimización de velocidad demostrada: los cambios corrigen robustez
y aumentan evidencia. Motor pasa de 301 a 306 pruebas; Backend de 75 a 85;
Frontend conserva 21. Quince pruebas adicionales, ninguna dependencia nueva.
Las dos omisiones del Motor son integraciones con pesos reales; no se presentan
como aprobadas. Las tres corridas GPU descritas abajo son evidencia separada.

La migración se aplicó también sobre la DB de desarrollo: 25 filas antes/después,
SHA de su representación semántica idéntico
`ddf9bec3c41cccd32c24e961753a8491036e9f278801803ca487bf502d14b90c`.
Un retry antiguo con observación redondeada incompatible continúa devolviendo
409 y conserva la fila: no se inventa otra identidad para esquivar el conflicto.
Las DB nuevas se validan mediante las migraciones al crear la DB de tests.

## Rendimiento y estrés preliminar del estado actual

Fecha 23-10-2026. Ryzen 5 5500, RAM 34.244.796.416 bytes, RTX 3070,
VRAM 8.589.410.304 bytes, driver 616.92, Windows 10 AMD64 build 19045;
Python 3.12.10, PyTorch 2.14.0+cu130, TorchVision 0.29.0+cu130,
CUDA 13.0, OpenCV 5.0.0.93, Ultralytics 8.4.146, lap 0.5.12, engine 0.1.0.

Se usa únicamente demo A, 277 frames, 1920×1080, 30 FPS. PERSON actual es
`DEVELOPMENT_CONFIGURATION / NOT_FINAL_PERSON_EVALUATION`.
SHA PERSON `21766a9dc664fac06da3b0b457e0449f25e1696acbf8e7e39993c4b42282083f`;
SHA video `3abe9043ee41f898d869890e8636b804186bfaf524daea2e6f6831e72711f4d6`;
SHA config `d3026751210776dacdc5226490047fb1c1bf064cdd6877e5ac23b3d6dc39885c`.
FORKLIFT conserva el SHA y parámetros indicados al inicio. PERSON confidence
0.10/NMS 0.70; ambos imgsz 640; batch 4, preview 10 FPS/ancho 1280.
No cambia ByteTrack, reglas ni geometría. Se recargan pesos en cada worker.

| Repetición A | Wall fresco, s | FPS fin a fin del worker | FPS informados por worker | Factor tiempo de proceso / duración del video |
| --- | ---: | ---: | ---: | ---: |
| 1 | 15.7983011 | 17.534 | 24.48 | 1.711 |
| 2 | 15.9794500 | 17.335 | 24.12 | 1.731 |
| 3 | 15.8733053 | 17.451 | 24.35 | 1.719 |

FPS global fresco = 831 / 47.6510564 s ≈ **17.439**. El wall usa
`perf_counter_ns`, incluye imports, carga, procesamiento, escritura y validación
del MP4; **excluye HTTP/Frontend/publicación de eventos**. No es latencia de sesión
web completa. El FPS que informa el worker excluye su carga inicial pero incluye
validación final: tampoco es una medición pura warm de inferencia.

Las etapas existentes excluyen los primeros 20 frames: 257 observaciones por
repetición, tiempos amortizados de batch. Promedios de las tres corridas en
ms/frame: lectura 5.243; PERSON 9.614; FORKLIFT 7.922; tracking 1.448;
reglas 0.726; renderer 11.045; JPEG 4.790; escritura 2.341; IPC 1.338.
No se dispone de muestras individuales para un p95 por frame de esas etapas;
no se fabrica uno ni se equipara suma de etapas con wall completo.

Tres MP4 decodificables completos: H.264/avc1 MSMF, 277 frames, 30 FPS,
1920×1080, 70.794.289 bytes cada uno; hashes en el resumen local. Los procesos
terminaron, RSS máximo del árbol 1.760–1.764 MB decimales, handles 1173/1177/1174;
handles del supervisor 481→482. Esto no demuestra ausencia de fugas a largo
plazo ni crecimiento del allocator GPU de un proceso residente, no medido.
No se afirma capacidad sostenida de 30 FPS ni mejora respecto de OP-43:
modelos, preview, batch y codificador no son comparables.

Se conserva una serie exploratoria anterior con una salida no cero tras marcar
el video completo; causa no demostrada. Su medición inicial de recursos solo
incluía el launcher, por lo que no se usa. La serie verificada es independiente,
no borra esa anomalía ni demuestra que nunca pueda repetirse.

### Histórico PostgreSQL: carga controlada

Test versionado `backend/apps/events/test_validation_stress.py`, commit `67d1c6e`.
PostgreSQL 17.11; 1.000 eventos marcados TEST_DATA_STRESS, cinco consultas de
filtros conciliadas y 21 solicitudes por endpoint: primera separada, 20 warm.
Latencia Django APIClient **en proceso**, con PostgreSQL real, sin TCP/browser.
La primera solicitud no es un arranque frío de aplicación. p95 nearest-rank
`ceil(0.95*n)` con n=20; desviación estándar muestral, sin umbral universal.
La ejecución final coexistió con las otras suites; no es benchmark aislado.

| Endpoint | Primera ms | Media warm ms | Mediana ms | p95 ms | Mín/máx ms | SD ms |
| --- | ---: | ---: | ---: | ---: | --- | ---: |
| health | 0.735 | 0.744 | 0.700 | 1.132 | 0.490 / 1.175 | 0.200 |
| eventos, 1.000 filas | 135.200 | 88.279 | 81.752 | 111.914 | 68.024 / 163.824 | 21.398 |
| frecuencias, 1.000 filas | 2.127 | 2.177 | 2.068 | 2.829 | 1.715 / 2.934 | 0.348 |

Los datos se crean y destruyen en `test_<POSTGRES_DB>`; el histórico de desarrollo
conserva 25 filas, sin TEST_DATA_STRESS. Esta prueba no justifica por sí sola
índices nuevos, paginación ni promesas de escala. No se introducen esas mejoras.

## Reproducción, artefactos y revisión web

Con los entornos de los README instalados y las variables de desarrollo
cargadas localmente, desde la raíz del repo:

```powershell
.\engine\.venv\Scripts\python.exe -B -m unittest discover -s engine/tests
.\engine\.venv\Scripts\python.exe -B engine/scripts/check_environment.py --require-cuda
```

Desde `backend`, ejecutar `manage.py check`, `makemigrations --check --dry-run`
y `test --noinput` con su Python virtual. Para repetir solo carga/E2E:

```powershell
.\.venv\Scripts\python.exe -B manage.py test apps.events.test_motor_integration apps.events.test_validation_stress --noinput
```

`OPERIX_VALIDATION_OUTPUT_DIR` opcional debe apuntar fuera del repo. Desde
`frontend`, Node 24.2.0/pnpm 11.28.2: `pnpm test`, `pnpm lint`,
`pnpm typecheck`, `pnpm build`. No cambiar `.env`, CORS ni dependencias para
obtener resultados artificialmente verdes.

El harness local de workers y sus tres resúmenes están en el directorio externo
`etapa3-autonomous-2026-10-23/`: `run_development_worker_baseline.py`,
`worker-sequential-verified/summary.json`,
`performance-final/controlled-history-stress.json`, `migration-check.json` y
`dashboard-api-smoke.png`. No se versionan medios ni rutas personales.
El resumen de workers registra commit `22a9421`, SHA del harness
`60a31c685565a2c099f33a130d8b28ed549e3dc6b447a401c6a5315262083f8a`,
hardware, configuración, hashes de entrada/salida y orden A/A/A.
Para repetir esa serie local se usa el Python del Motor y el harness con
`--output-name <nombre-nuevo> --repetitions 3`, sin sobrescribir corridas.
El test de histórico registra su commit y SHA del propio test; no incorpora
credenciales ni medios al reporte. Los experimentos locales no están disponibles
en un clon público: el test versionado sí; para el benchmark se requieren pesos
y codificador locales, no descargas automáticas.

Smoke del navegador en el origen local autorizado: health conectado,
dashboard ejemplo/API claramente separados; 25 eventos API, distribución por
zona 22/2/1 y tabla de eventos con enlaces de evidencia. Los tests de Backend
comprueban recuperación PNG e idempotencia; no se afirma haber revisado a mano
todas las imágenes históricas ni un análisis web nuevo publicando eventos.
Impeccable se utilizó para una auditoría acotada, sin rediseñar: se mantiene
distinción demo/API, loading, fuente UTC y advertencia de frecuencias no riesgos.
No es certificación WCAG ni una revisión responsive completa. Un puerto temporal
no permitido falló por CORS; se usó el origen ya autorizado, sin debilitar CORS.

## Revisión adversarial y pendientes reales

- **BLOCKED — PERSON:** anotación humana completa, revisión y atestación final
  de independencia. El registro training/development aún requiere cobertura
  humana confirmada antes de freeze. Cinco familias/92 frames no equivalen a
  ground truth terminado. No inferencia ni entrenamiento en el holdout.
- **BLOCKED — publicación web/pares:** decidir activación, identidad de dos
  entidades, ancla civil del video, significado de inicio/final del episodio,
  inclusión de demos en histórico y retención/acceso de evidencia persistente.
  El IPC conserva solo el último frame; no permite reconstruir episodios completos.
  La regla de pares continúa deshabilitada en perfiles. No activar por inferencia.
- **BLOCKED — PV-01/PV-02:** validación experta de umbrales, geometría y uso antes
  de interpretar riesgo, alertas o roles obligatorios. Login local no protege API.
- **DEFERRED técnico:** cuantización a nueve decimales puede diferir del comparador
  float en un borde extremo subnanosegundo: elapsed=1/30 y umbral=1/30+0.9e-9
  es aceptado por Motor, pero 0.033333333 puede ser rechazado por API. No se
  afirma equivalencia temporal perfecta ni se amplía tolerancia operacional.
- **DEFERRED técnico:** el validador PNG acota descompresión y verifica scanlines,
  no reconstruye píxeles/paleta ni todas las reglas de chunks críticos. No llamarlo
  decodificador PNG completo; evidencia RGB del Motor cubierta por integración.
- **Limitaciones de prueba:** UI revisada en escritorio, no suite E2E web completa;
  carga acotada, sin estrés concurrente industrial ni medición VRAM residente;
  precisión PERSON y MOT no evaluada formalmente; una anomalía de salida previa
  sin causa demostrada. No hay P0/P1 nuevo reproducible en las suites finales,
  pero las fronteras funcionales indicadas siguen abiertas.

## Retroalimentación y mejoras

La única retroalimentación de profesor registrada en OP-28 exige justificar las
tecnologías; se traza a los ADR y evidencia técnica. No se atribuyen al profesor
mejoras internas posteriores. Specialist, dual perception, regla por pares,
reproducción web, OP-41 y hardening son **INTERNAL_IMPROVEMENT** salvo fuente
específica documentada. Véanse OP-28 y `etapa3-experimentos.md`.

## Persistencia operacional por pares — 24-10-2026

Base `0117c26c8f29bb353e3347517b6458d88420d084`. Esta sección registra el avance
posterior; no convierte las conclusiones de la primera validación en mediciones del código nuevo.
Se incorpora `person_forklift_proximity` sin cambiar RuleEngine, perfiles ni umbrales.
El snapshot guarda `interaction` con ambos roles/clases/IDs; `observations` con
distancia normalizada y duración; `episode` con inicio y emisión; parámetros efectivos,
regla/versión, fuente y PNG. No se inventa un objeto primario ni un tiempo final
posterior a la emisión: el Motor todavía no emite el cierre del episodio.

`pair_key` es SHA-256 del JSON canónico de ambas identidades con roles. La constraint
incluye run/view/frame/regla/versión/zona/par. El retry devuelve el evento previo;
otro par, episodio con otra emisión o run independiente no colisiona. Un snapshot
incompatible devuelve 409 sin modificar el anterior. `zone_dwell` conserva su contrato.
La migración 0005 deja snapshots nuevos vacíos en históricos; 25 filas preservadas,
SHA de campos originales antes/después idéntico:
`aaef225db602a13dd6daf675cec72609503ab6709519b698a9b5ee95432beed6`.

El outbox conserva PNG y journal de candidatos antes del HTTP. Se reenvían los
snapshots, no se recalculan reglas. Cada envío tiene hasta tres intentos; no es una
cola distribuida ni una garantía de entrega infinita. La retención es manual.
E2E con video MJPG de cuatro frames, percepción fixture, analizador/regla reales:
dos pares independientes → HTTP → PostgreSQL → PNG recuperable → RF-07/RF-08;
reenvío conserva IDs. Precisión de detector no evaluada por este test.
La API y el adaptador frontend aceptan ambos tipos; filtros mixtos y el detalle
recuperable exponen el snapshot sin convertirlo en accidente ni riesgo confirmado.

Pruebas nuevas: `test_pair_events.py`, `test_pair_publishing.py`, `test_event_outbox.py`
y E2E adicional en `test_motor_integration.py`. La aplicación desde una DB de tests
vacía pasa; fallo de guardado DB elimina el PNG nuevo para evitar evidencia huérfana.
La integración automática de sesiones web se verifica en el siguiente hito; este
contrato por sí solo no declara aún `OPERATIONAL_PERSISTENCE_READY`.

### Conexión de sesiones web

El worker de streaming conserva todos los candidatos en un outbox durable y los
publica por HTTP sin depender del último status IPC. La sesión prepara una copia
de configuración efectiva y un run estable por inicio explícito. El reloj civil
es una **ancla de inicio de análisis**, no una fecha de grabación conocida; esa
distinción viaja en `source`. No se alteran reglas, percepción ni perfiles.

El estado de análisis y el de persistencia son independientes. La interfaz permite
consultar el histórico o reintentar guardado sin volver a analizar. Evidencia y
journal tienen MANUAL_RETENTION fuera de los temporales de sesión. Hay límites
de retry, no garantía infinita de entrega ni retención operacional definitiva.

`WebPersistenceTests`: API de upload/inicio/status/resultado reales, worker
productivo con detecciones fixture, ByteTrack/reglas/outbox/HTTP/PostgreSQL reales.
Tres pruebas aprobadas: dos pares guardados con PNG; dos runs separados, cuatro
eventos e imágenes independientes; análisis completado con HTTP fallido y replay
posterior idempotente. El cierre de sesión conserva el outbox y los eventos.
Estas pruebas no usan pesos ni evalúan exactitud o capacidad GPU.

### Recuperación y revisión independiente

La revisión independiente encontró y corrigió: recibo IPC `saved` obsoleto tras
crash; carrera stop/start que podía limpiar el proceso nuevo; fallo PNG sin
material de recuperación; journal truncado que impedía entregar su prefijo válido;
redirecciones HTTP fuera del destino local; y journal ausente interpretado como
cero candidatos guardados. Hay regresiones en `test_hardening.py` y
`test_event_outbox.py`. La revisión posterior no identificó otro bloqueante
concreto en esos cambios; no demuestra ausencia universal de errores.

Se registra intención durable antes de guardar la evidencia y se confirma el
journal antes de HTTP. Un pendiente sin snapshot completo requiere revisión manual,
mantiene `failed` y no se descarta. Un journal parcial permite reenviar entradas
completas, pero conserva `invalid_records` y no informa éxito total. Un terminal
anormal no confirma el último IPC; solo un replay comprobado puede actualizarlo.
El fallback conserva un frame candidato derivado con hash, no el video; recrea
PNG acotado sin inferencia. Si el disco no permite guardar intención/evidencia,
no existe garantía de recuperación: el análisis termina con error controlado.

Event y PNG se guardan en pasos HTTP distintos: un Event puede existir sin PNG
si falla su upload; el publicador lo informa como fallido y reintenta la misma
identidad. El guardado de metadata del PNG usa transacción/bloqueo de fila y elimina
el archivo nuevo si falla la DB. No se presenta esto como transacción distribuida.

### Prueba GPU Web/API y recursos

Serie local A/A/A del 24-10-2026; código ejecutado:
`a30dd21d4a89f207ac3700516bb78570a241f6f2`. El monitor terminó con HEAD
`e1d221af99e3278802dca8153cf02594b57e2190`, que solo añade la prueba de carga:
no cambió código productivo durante la serie. Harness local `gpu_web_smoke.py`, SHA
`42277f30180445867263fdc52fb754372cd4878b11d9a2295e0962e383411c49`;
monitor SHA `b7bd686d6090fe312dee73feb2480b774b5eed9d595c5e629d376d1a69a42f54`.
Entorno y hashes de video/configuración/pesos: mismos valores documentados arriba.

| Repetición | Wall s | FPS por wall | Frames | Eventos guardados | Resultado |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 27.640535 | 10.022 | 277 | 3 | completed / saved |
| 2 | 26.556536 | 10.431 | 277 | 3 | completed / saved |
| 3 | 27.153134 | 10.201 | 277 | 3 | completed / saved |

El wall usa `perf_counter_ns`: upload/inicio/status mediante APIClient en proceso,
carga fresca de modelos, procesamiento GPU, salida MP4, transporte y publicación
HTTP local, PostgreSQL y finalización. Excluye latencia de upload TCP/browser y
las consultas posteriores de comprobación. Incluye los 20 frames iniciales;
las etapas warm existentes excluyen esos frames (257 muestras amortizadas por run).
No se midió una sesión end-to-end con modelos residentes: las tres cargan pesos.
831 frames / 81.3502041 s = **10.215 FPS globales**. No 30 FPS sostenidos ni
comparación directa con OP-43 o la primera validación; sus alcances son diferentes.

Las tres corridas usaron el perfil A vigente, con `zone_dwell`, sin activar la regla
de pares. Cada una verificó eventos, PNG, histórico, frecuencias, propiedad de
run/source y cierre del worker. Nueve eventos solo en DB temporal, destruida al
finalizar; no se añadieron eventos al histórico de desarrollo. Tres MP4 completos
H.264/MSMF de 277 frames, 1920×1080/30 FPS, 70.794.289 bytes. Sus hashes diferentes
se conservan en el resumen local; no se exige codificación binaria determinista.
Esto no mide precisión PERSON ni valida umbrales operacionales.

Monitor del árbol propio: pico RSS 1.819.512.832 bytes, 1.545 handles, cuatro procesos,
ningún proceso propio remanente. Memoria global GPU entre 1.657 y 2.115 MiB;
incluye escritorio y otros procesos, no mide allocator residente ni prueba ausencia
de fugas. El muestreo no demuestra estabilidad indefinida. Resultados locales en
`etapa3-autonomous-II-2026-10-24/gpu-web-summary.json` y
`gpu-web-resource-review.json`, fuera de Git. No se versionan MP4, PNG ni logs.

### Cobertura funcional y límites del corte

| ID | Comprobación | Resultado / límite |
| --- | --- | --- |
| E3II-PAIR | Snapshot completo de dos roles, reglas y métricas; API, constraint y retries | `test_pair_events.py`, `test_pair_publishing.py`; no objeto primario inventado |
| E3II-E2E | OpenCV → analizador/regla → dos pares → HTTP → DB → PNG → filtros/agregados | `test_motor_integration.py`; percepción determinista, no exactitud de detector |
| E3II-WEB | Upload/inicio → worker productivo con percepción fixture → dos pares persistidos | `test_persistence.py`; API de sesiones y HTTP reales; no navegador automatizado completo |
| E3II-RUN | Dos inicios cercanos, separados por el guard GPU; cuatro eventos en runs separados | Sin overwrite ni contaminación de imágenes; no procesamiento GPU concurrente permitido |
| E3II-FAIL | HTTP fallido, DB/PNG fallidos, crash, timeout, salida inválida, stop/start | Retries acotados; resultado y persistencia distintos; replay sin inferencia |
| E3II-MIG | DB desde cero, dos tipos y evidencia; migración 0005 sobre 25 filas | Nuevos snapshots vacíos, campos previos preservados; no identidad histórica inventada |
| E3II-GPU | Tres workers GPU A con publicación y evidencia | 831 frames, nueve eventos aislados, cero procesos propios remanentes |
| E3II-UI | Lista, filtro de pares vacío y detalle con regla/PNG; escritorio y móvil | Browser contra histórico real de 25 filas; no se inyectaron pares en desarrollo para la captura |

El frontend distingue ambos tipos y enlaza el detalle; contratos de pares probados
automáticamente. La revisión visual comprobó detalle heredado, estado sin fuente
y filtro de pares vacío sin fabricar ejemplos. No afirma una demostración visual
de un nuevo par persistido en la DB de desarrollo. Impeccable detect sobre las
tres superficies modificadas terminó sin hallazgos; diseño/incumbente preservado.
Posteriormente también se abrió el nuevo `zone_dwell` de la ejecución web
independiente descrita abajo: source/run, regla/parámetros y PNG visibles en el
navegador. Esto amplía la comprobación visual de objeto único, no de pares.

### Trazabilidad de requisitos

| Requisito | Implementación / validación | Evidencia | Limitación restante |
| --- | --- | --- | --- |
| RF-01 | IMPLEMENTED / VALIDATED funcional | E3II-WEB/GPU; suites de video | Fuentes y codificador acotados |
| RF-02 | IMPLEMENTED / PARTIAL accuracy | `etapa3-experimentos.md`; GPU independiente | PERSON final espera anotación; no usar holdout |
| RF-03 | IMPLEMENTED / VALIDATED funcional | Tracking/identidad compuesta; regresiones Motor | Sin ground truth MOT ni garantías de identidad |
| RF-04 | IMPLEMENTED / VALIDATED por tests | Geometría y edición de zona vigentes | Revisión contextual experta |
| RF-05 | IMPLEMENTED / VALIDATED por fixtures | `test_rules.py`, `test_pair_rules.py` | Parámetros experimentales; pares no activados en perfiles A/B/C |
| RF-06 | IMPLEMENTED / VALIDATED integración | E3II-PAIR/E2E/WEB/FAIL/GPU | Recuperación acotada; retención manual y acceso local |
| RF-07 | IMPLEMENTED / VALIDATED dos tipos | E3II-PAIR; filtros y carga mixta | Histórico sin paginación; alcance de carga acotado |
| RF-08 | IMPLEMENTED / VALIDATED dos tipos | Counter independiente en carga/pares | Frecuencias de condiciones, no tasas de incidentes |
| RNF-01 | IMPLEMENTED / VALIDATED snapshots | Contrato, idempotencia, migración 0005 | Ancla UTC de análisis proxy; emisión, no cierre de episodio |
| RNF-02 | IMPLEMENTED / PARTIAL alcance | Tres corridas GPU y carga local mixta | No benchmark industrial ni 30 FPS sostenidos |
| R-01 | VALIDATED para fuentes documentadas | OP-16/18/42; provenance ya archivada | Cada recurso nuevo requiere derechos propios |
| R-02 | PARTIAL | API loopback, retención manual, datos fuera de Git | Sin autenticación empresarial ni política de retención definitiva |
| R-03 | IMPLEMENTED en alcance | IDs temporales, sin biometría/sanciones | No interpretar candidatos como culpa/riesgo confirmado |
| PV-01 | PARTIAL | Límites y snapshots de reglas | Validación de geometría/umbrales por experto |
| PV-02 | BLOCKED validación humana | Interfaz y reglas configurables existentes | Roles demo no sustituyen autorización Backend |

Reconciliación documental, sin editar Excel: OP-39 y OP-40 pasan de PARTIAL a
DONE **para aceptación técnica controlada** (evento/PNG persistidos y filtros
por período y dos tipos existentes). OP-33–41/59/60: **11/11 del subconjunto de
implementación**, frente a 9/11 en la base. No equivale a avance académico global,
exactitud de percepción ni cierre experto. OP-28 sigue actividad continua; OP-42
PARTIAL como resguardo, OP-44/45 PARTIAL en validación ampliada y OP-46 BLOCKED
por revisión experta. Seguridad productiva y despliegue empresarial: DEFERRED.
Las dos omisiones con modelos reales siguen siendo SKIP, no pruebas aprobadas.

### Retroalimentación y cambios comprobados

| Clasificación | Fuente | Cambio / commit | Evidencia |
| --- | --- | --- | --- |
| FEEDBACK_DRIVEN | OP-28, profesor guía, 25/09/2026 | Registro `9a4e8aa`, actualización `880744f`, ADR `49a3198`; no se inventa feedback posterior | [OP-28](OP-28-feedback-log.md), [ADR](../../docs/architecture/README.md) |
| INTERNAL_IMPROVEMENT | Fronteras MISSING de la primera validación | Pares persistentes `ce83a92`; web `6b44d9c` | E3II-PAIR/E2E/WEB |
| INTERNAL_IMPROVEMENT | Revisión independiente y regresiones | Recuperación `a30dd21`; carga mixta `e1d221a` | E3II-FAIL/GPU; test de carga |

La justificación solicitada en OP-28 está respaldada por decisiones/documentación;
este trabajo no verifica el texto de un informe académico externo ni una aceptación
posterior del profesor. Retroalimentación permanece PARTIAL. FORKLIFT/NMS se
reutilizan desde `etapa3-experimentos.md`; no se reevalúan aquí. El cambio verificable
de esta campaña es IPC de último frame/pares no persistentes → journal completo,
contrato de dos tipos, publicación web, evidencia y consultas. No se atribuye una
ganancia de precisión o velocidad que esta campaña no haya medido.

### Carga mixta y regresión del 24-10-2026

SHA probado `e1d221af99e3278802dca8153cf02594b57e2190`; suite final Backend
103/103, incluyendo Web E2E con pares y evidencia. Motor **319 descubiertas,
317 PASS y dos SKIP**; frontend **23/23**. Total de suites: **445 descubiertas,
443 PASS, dos SKIP**. Lint, typecheck, build, Django check, migration check,
pip check de ambos entornos, tensor CPU/CUDA y OpenCV: PASS. No dependencias nuevas.
La comprobación global de formato Windows no se presenta como aprobada: permanece
el antecedente de CRLF preexistente; los archivos frontend cambiados sí pasaron
Prettier estricto. No se normaliza el repositorio masivamente.

Stress V2: 1.200 filas, 600 por tipo, en PostgreSQL 17.11 temporal. Filtros y
frecuencias reconciliados con Counter independiente; cero TEST_DATA_STRESS en
desarrollo. 21 consultas por endpoint, primera separada y 20 warm; p95 nearest-rank
19/20. APIClient en proceso con PostgreSQL real; sin TCP/browser. No umbral universal,
arranque frío de aplicación ni carga industrial. Harness versionado SHA
`d5d568775e86e39b399a2319cabffbd79bf5b278fb87a33a98c9112e36b3e57c`.

| Endpoint | Primera ms | Media warm ms | Mediana ms | p95 ms | Máximo ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Lista mixta, 1.200 | 101.511 | 116.331 | 102.386 | 173.025 | 185.862 |
| Lista por tipo, 600 | 57.909 | 65.247 | 56.061 | 123.118 | 153.861 |
| Lista por fechas, 601 | 55.559 | 58.607 | 51.715 | 118.479 | 120.398 |
| Tipo + fechas, 300 | 29.256 | 33.309 | 28.489 | 42.410 | 98.177 |
| Frecuencias mixtas | 2.245 | 1.498 | 1.506 | 1.686 | 1.772 |
| Frecuencias tipo + fechas | 2.043 | 1.621 | 1.526 | 1.825 | 3.038 |
| Detalle / metadata de evidencia | 2.109 | 1.646 | 1.537 | 1.839 | 2.900 |

Resumen local: `etapa3-autonomous-II-2026-10-24/final-validation/controlled-history-mixed-stress.json`.
No se versionan datos de carga. La carga corrió dentro de la suite, no en una
máquina aislada: variabilidad y servicios de escritorio limitan la comparación.

Verificación posterior: las **25 filas originales** conservan el SHA indicado
arriba. El total de desarrollo pasó a **28**, por tres eventos `zone_dwell` de
una ejecución web independiente posterior, run
`bcf62b20-7f61-51e7-89fd-5877c2702181`, identificada como demo en source.
No pertenecen a los nueve IDs de la DB temporal GPU ni a los fixtures de pares.
Se preservaron sin edición; lista y frecuencias reconcilian 28. No se atribuye
este crecimiento a la migración ni se borra para forzar un total de 25.
Los intentos de auditoría detectaron primero ese cambio de total y un uso de
`testserver` fuera de ALLOWED_HOSTS; se corrigió la comprobación para usar localhost,
sin cambiar settings ni ocultar la discrepancia. El hash del subconjunto histórico
es idéntico: no hubo reescritura de sus observaciones.

## Actualización PERSON — evaluación congelada ejecutada — 24-10-2026

**`PERSON_EVALUATION_PROTOCOL_V1_EXECUTED` + `PERSON_RESULTS_SEALED`**.
El bloqueo histórico por anotación/freeze ya no describe el estado vigente.
Se preservaron 92 registros originales y se evaluaron 91 imágenes únicas de cinco
familias, con 168 cajas humanas, tras congelar dataset, protocolo y configuraciones.
Evaluación sobre holdout independiente congelado **dentro del proceso controlado
de Operix**; no acredita ausencia en pretraining externo.

| Alcance | Estado comprobado | Límite / pendiente |
| --- | --- | --- |
| RF-02 / detección PERSON | Evaluación descriptiva ejecutada; CURRENT: TP 20, FP 39, FN 148, precision 0,338983, recall 0,119048, F1 0,176211 | Baja cobertura en este conjunto real; no demuestra detección fiable general |
| Referencia genérica | COCO: TP 151, FP 120, FN 17, precision 0,557196, recall 0,898810, F1 0,687927 | Baseline contextual, sin sustitución automática del modelo |
| Trazabilidad | Datos y protocolo sellados antes de la ejecución; raw, métricas y recibos sellados antes de revisar imágenes | Un primer intento técnico inválido preservado; una corrida completa válida por modelo |
| Calidad del GT | GT humano congelado preservado | La inspección posterior detectó posible omisión en `102/frame_000369` y ambigüedad sobre fragmentos humanos en `104/frame_000472`; no se corrige ni recalcula retrospectivamente |
| Validación operacional / PV-01 | Continúa PARTIAL | La evaluación de objetos no valida reglas, tracking, seguridad ni umbrales operacionales; validación experta pendiente |

Resultados completos, hashes, invalidación técnica y revisión cualitativa:
[evidencia PERSON V1](etapa3-experimentos.md#ejecución-person-evaluation-protocol-v1--24-10-2026).
El siguiente desarrollo no puede reutilizar conocimiento de este conjunto y luego
presentarlo como un test independiente no consultado. No hubo tuning, entrenamiento
de PERSON v2, cambio de CURRENT_PERSON ni uso de TEST2/REAL_HOLDOUT_V2. No se cierran
automáticamente tareas ni se modifica Excel mediante esta actualización.


## Trazabilidad de entregables al 24-10-2026

Base `85c064136233638a2a560357b9a2403086578f73`. Relación entre requisitos,
pruebas y commits del corte; no constituye otro backlog ni modifica estados
académicos oficiales.

| Trabajo / requisito | Estado técnico y criterio observado | Evidencia / tests | Commits principales | Limitación / siguiente revisión |
| --- | --- | --- | --- | --- |
| 1. Variables espacio-temporales — RF-03/04/05 | Implementadas: pertenencia, permanencia, trayectorias e identidad `(clase, track_id)` sin colisiones entre canales | [OP-37](OP-37-spatiotemporal.md), [tests](../tests/test_spatiotemporal.py) | `ed06beb`, `323d175` | Geometría de imagen, sin calibración métrica ni GT MOT |
| 2. Reglas configurables — RF-05, RNF-01, PV-01 | RuleEngine consume estados descriptivos; false→true emite una vez, rearme tras false/ausencia; regla/versión/parámetros conservados | [OP-38](OP-38-rules.md), [tests](../tests/test_rules.py) | `2608fce` | Umbrales experimentales; falta aprobación contextual/experta |
| 3. person_forklift_proximity — RF-05 | Misma zona, distancia y permanencia configuradas; pares independientes y tiempo robusto a error float | [Síntesis](etapa3-experimentos.md), [tests](../tests/test_pair_rules.py) | `5a4c615`, `323d175` | No riesgo confirmado; asociación operador/vehículo pendiente |
| 4. Persistencia real — RF-06 | POST valida candidato y guarda Event de objeto único/pares en PostgreSQL; retry equivalente devuelve mismo ID | [Backend](../../backend/README.md), [E2E](../../backend/apps/events/test_motor_integration.py) | `37b53bb`, `ce83a92` | API local; no transacción distribuida entre fila y PNG |
| 5. Candidate journal — RF-06, RNF-01 | Intención/snapshot antes de HTTP; journal durable y replay sin recalcular percepción/reglas | [Matriz](ETAPA3-VALIDATION-MATRIX.md), [tests](../tests/test_event_outbox.py) | `ce83a92`, `6b44d9c`, `a30dd21` | Disco fallido o snapshot incompleto requiere revisión; entrega acotada |
| 6. Evidencia — RF-06, R-02 | PNG validado y recuperable por UUID; MP4 reproducible de sesión; referencia en DB y bytes externos | [API](../../backend/README.md), [tests de persistencia](../../backend/apps/analysis/test_persistence.py) | `1ec97b1`, `bee649e`, `a30dd21` | MP4 de sesión temporal; retención de PNG/outbox manual |
| 7. Historical queries — RF-07 | Filtros inclusivos por período/tipo con timezone; dos tipos reales discriminados y carga mixta conciliada | [OP-40 histórico](../../backend/evidence/OP-40-event-query.md), [carga mixta](../../backend/apps/events/test_validation_stress.py) | `da5d851`, `ce83a92`, `e1d221a` | Sin paginación ni escala industrial acreditada; el PARTIAL histórico era de un solo tipo |
| 8. Indicadores — RF-08 | Agregados diarios UTC y por tipo concuerdan con registros/Counter; Web separa ejemplo y API | [OP-41](../../backend/evidence/OP-41-event-frequencies.md), [tests](../../backend/apps/events/test_frequencies.py) | `661cd06`, `e1d221a` | Conteos de condiciones, no tasas verificadas de incidentes/riesgo |
| 9. Web/API — RF-01/06/07/08 | Upload/demo, configuración, inicio/status/resultado, cancelación, guardado y retry por sesión; dos runs separados | [Backend](../../backend/README.md#publicación-operacional-desde-sesiones-web), [E2E web](../../backend/apps/analysis/test_persistence.py) | `6b44d9c`, `a30dd21` | Una API local; sesiones en RAM; no seguridad de producción |
| 10. Event Detail — RF-06, RNF-01 | PNG prioritario/ampliable, mediciones vs parámetros, tiempo de video y ancla UTC explícita; payload en disclosure | [modelo UI](../../frontend/src/features/events/event-detail-model.ts), [tests](../../frontend/tests/event-detail-model.test.mjs) | `4cb8e2a` | Revisión UI funcional; no certificación WCAG ni confirmación de incidente |
| 11. Failure handling/idempotencia — RF-06, RNF-01 | Fallos DB/PNG controlados, retry acotado sin duplicado, journal truncado no informa éxito total | [Matriz](ETAPA3-VALIDATION-MATRIX.md), [hardening](../../backend/apps/analysis/test_hardening.py) | `7ff24ee`, `22a9421`, `a30dd21` | Sin garantía infinita; preservar conflictos y datos incompletos para revisión |
| 12. Stress/performance — RNF-02 | Carga histórica controlada de 1.000 filas y corrida dual GPU descriptiva con entorno y límites | [Matriz](ETAPA3-VALIDATION-MATRIX.md#rendimiento-y-estrés-preliminar-del-estado-actual), [OP-43 histórico](OP-43-performance.md) | `67d1c6e`, `e1d221a`, `d6eb909` | Protocolos distintos; sin claim universal de 30 FPS, nueva campaña o tuning |
| 13. Holdout independiente PERSON — RF-02, R-01/02 | FROZEN: 92 registros, 91 imágenes únicas, 67 positivas/24 negativas, 168 GT; derechos y declaración humana archivados | [Protocolo](PERSON-INDEPENDENT-HOLDOUT-PROTOCOL.md), [freeze tests](../tests/test_person_coco_freeze.py) | `10adad2`, `e7e0edb` | Independencia dentro del proceso Operix, no de pretraining externo; posible GT incompleto |
| 14. PERSON evaluation protocol — RF-02, RNF-01 | V1 fijado antes de inferencia: matching 1:1, IoU 0,50/0,75, roles/config y métricas; hash sellado | [Manifest](../config/evaluation/person-evaluation-protocol-v1.json), [tests](../tests/test_person_protocol.py) | `472500f`, `92bab58` | Sin sweeps/AP/mAP ni selección automática de modelo |
| 15. PERSON sealed evaluation — RF-02, PV-01 | Una corrida completa válida por modelo; CURRENT TP20/FP39/FN148 frente a COCO TP151/FP120/FN17; resultados sellados antes de revisión | [Resultados](etapa3-experimentos.md#ejecución-person-evaluation-protocol-v1--24-10-2026) | `accda35` | CURRENT con limitación importante de generalización; COCO referencia, PERSON v2 diferido; GT sin reetiquetar |
| 16. Docker local — RF-01/06/07/08, RNF-01/02 | Infra CPU usable, DB propia y healthchecks; arranque desde volúmenes nuevos, filtros/evidencia y persistencia tras recreación PASS | [Validación](DOCKER-LOCAL-VALIDATION.md), [recibo](docker-local-receipt.json) | `cb1605b`, `85c0641` | Alternativa local, no reemplaza modo nativo; sesiones RAM no se restauran |
| 17. Docker GPU — RF-02/06, RNF-02 | RTX 3070 real: demo 277/277, 3 candidatos/3 eventos, 0 fallos y PNG/MP4 recuperables; segunda ejecución fresca PASS | [Validación](DOCKER-LOCAL-VALIDATION.md), [guía](../../deployment/docker/README.md) | `cb1605b`, `85c0641` | Docker Desktop WSL2; pesos individuales read-only; sin garantía para cualquier GPU |
| 18. Reproducibilidad/documentación — RNF-01/02, R-01/02/03 | Locks nativo/Linux, hashes/protocolos, fuentes y evidencia indexada; suites y checks del corte sin fallos | [Índice](README.md), [estado técnico](ETAPA4-TECHNICAL-AUDIT.md#24-final-v020-release-gate-pass--26-10-2026), [terceros](../../THIRD_PARTY_NOTICES.md) | `d6eb909`, `accda35`, `85c0641`; consolidación documental posterior | No equivalencia a reconstrucción bit a bit, auditoría jurídica o cierre académico automático |


## Identidad y alcance de los cortes documentales

El corte documental del 24-10-2026 registró 353 pruebas del Motor (351 PASS y
2 SKIP), Backend 103/103 y Frontend 30/30; las omisiones no se cuentan como PASS.
El corte pre-release sobre `f4652f609beb1121bb6d8a0d2425f1eba28bc0fc` registró
421 PASS + 2 SKIP del Motor, Backend 125/125 y un E2E CUDA real de 418/418 frames
con dos eventos. Son resultados de esas bases, no cifras de la versión final.

### Identidades de la evaluación sellada del 24-10-2026

La comparación CURRENT_PERSON / YOLO11N_COCO_PERSON y sus límites se recogen en
[la evaluación sellada](#actualización-person--evaluación-congelada-ejecutada--24-10-2026)
y en la síntesis experimental, sin repetir sus tablas aquí.

- CURRENT_PERSON: `21766a9dc664fac06da3b0b457e0449f25e1696acbf8e7e39993c4b42282083f`.
- YOLO11N_COCO_PERSON: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
- FORKLIFT specialist v2: `1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6`.
- Freeze PERSON_FINAL_HOLDOUT_V2: `A71F2558BB5C2A8DF580B6A2908860A9A89F729487BA1C904A14F37C5ADC5339`.
- Protocolo PERSON V1: `C2012598048352B9681031301AD4EC76667CA982D2C7D32F64ECECA7D835496F`.

Estos identificadores describen el corte de evaluación, no una promoción de
modelos ni una nueva consulta al holdout. La configuración vigente se documenta
en la auditoría del candidato.
