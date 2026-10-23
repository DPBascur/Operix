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
por las fronteras descritas. Antes/después de la primera prueba integrada: 9/11.
No es porcentaje de todo el backlog ni nota académica, ni equivale a exactitud
validada de PERSON. El Excel conserva su estado original: esta matriz registra
la reconciliación técnica sin sobrescribir macros, actas ni estados académicos.

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

La prueba E3-E2E-01 usa lectura OpenCV, analizador, regla, renderer, HttpEventSink,
Django y PostgreSQL reales. Detector/tracker son fixtures deterministas: demuestra
integración, **no evalúa ningún modelo**. Sus filas solo existen en la DB temporal
destruida por Django y sus imágenes se conservan únicamente durante el test.
Resumen local: `etapa3-autonomous-2026-10-23/baseline/motor-http-postgresql-smoke.json`.

## Pendientes de campaña

- P0: verificar fronteras de publicación web/pares antes de ampliar persistencia.
- P1: precisión temporal entre Motor/API; reintentos acotados; PNG decodificable.
- P1: rendimiento/estrés acotado y documentación de errores, sin usar holdouts.
- P2: reproducibilidad, revisión de claims y smoke web sin rediseño.
- BLOCKED: anotación PERSON, validación experta y decisiones de acceso/retención.

## Retroalimentación y mejoras

La única retroalimentación de profesor registrada en OP-28 exige justificar las
tecnologías; se traza a los ADR y evidencia técnica. No se atribuyen al profesor
mejoras internas posteriores. Specialist, dual perception, regla por pares,
reproducción web, OP-41 y hardening son **INTERNAL_IMPROVEMENT** salvo fuente
específica documentada. Véanse OP-28 y `etapa3-experimentos.md`.
