# Etapa 3 — matriz de implementación y validación preliminar

## Base y límites

Auditoría del 23-10-2026 sobre `dev`, base `8cea9eb7dc134b506ab8c6eba14e88c865bb531c`.
Fuente de aceptación: Backlog V0.11, hojas **Backlog General** y **Levantamiento**.
La arquitectura v1.0 no cambia. Implementación, validación funcional y evaluación
de exactitud son estados distintos. Un evento significa condición configurada
satisfecha, no incidente, Near Miss ni responsabilidad personal.

PERSON final: `WAITING_FOR_HUMAN_ANNOTATION`; cinco familias 101–105 y 92 imágenes
reservadas. No inferencia, nueva selección, cambio de sampling ni freeze. TEST2
permanece protegido; YouTube es `DIAGNOSTIC_ONLY`; TEST3 es desarrollo.
Los hashes de los cinco paquetes CVAT se comprobaron contra el manifest de
adquisición: 20/20/12/20/20 frames, todos PASS, sin abrir imágenes ni ejecutar modelos.
FORKLIFT v2 conserva SHA `1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6`,
640, confidence 0.45 y NMS 0.55. No se entrena ni calibra en esta campaña.

## Auditoría inicial y backlog técnico

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

## Scorecard de evidencia (no calificación)

| Categoría de rúbrica | Peso de referencia | Estado | Sustento / faltante |
| --- | ---: | --- | --- |
| Retroalimentación | 20 | PARTIAL | OP-28 y ADR justifican tecnologías; falta nueva validación externa registrada |
| Mejoras/optimización | 15 | ADEQUATE | Bugs reproducidos y corregidos; no aceleración no medida |
| Implementación | 10 | ADEQUATE | 9/11 del núcleo técnico; denominador global académico por acordar |
| Pruebas/resultados | 30 | STRONG | 410 PASS + 2 SKIP; E2E real con percepción fixture; límites de exactitud explícitos |
| Validación preliminar | 10 | PARTIAL | Tres workers GPU + histórico 1.000 filas; PERSON y continuidad web pendientes |
| Documentación/trazabilidad | 15 | STRONG | Matriz, commits separados, resultados locales con hashes; Excel no sobrescrito |

**ETAPA3_AUTONOMOUS_ADVANCEMENT_COMPLETE** para esta campaña acotada.
**ETAPA3_BLOCKED_BY_PERSON_ANNOTATION_AND_OPERATIONAL_PERSISTENCE_DECISIONS**
para declarar cumplimiento completo. Existe validación preliminar de componentes,
no un MVP integral universalmente listo ni cierre académico automático.

## Retroalimentación y mejoras

La única retroalimentación de profesor registrada en OP-28 exige justificar las
tecnologías; se traza a los ADR y evidencia técnica. No se atribuyen al profesor
mejoras internas posteriores. Specialist, dual perception, regla por pares,
reproducción web, OP-41 y hardening son **INTERNAL_IMPROVEMENT** salvo fuente
específica documentada. Véanse OP-28 y `etapa3-experimentos.md`.

## Campaign II — contrato operacional por pares (24-10-2026)

Base `0117c26c8f29bb353e3347517b6458d88420d084`. Esta sección registra el avance
posterior; no convierte las conclusiones de Campaign I en mediciones del código nuevo.
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

### Campaign II — conexión de sesiones web

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
