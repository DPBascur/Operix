# Índice de evidencia técnica

Estado transversal: [snapshot de Etapa 3](ETAPA3-PROJECT-STATE.md).
La [matriz](ETAPA3-VALIDATION-MATRIX.md) distingue diseño, implementación y
validación. El [handoff académico](ETAPA3-BACKLOG-HANDOFF.md) es una fuente factual
para revisión humana posterior; no es otro backlog ni modifica estados oficiales.

## Etapa 3: evidencia vigente por tema

| Tema | Evidencia | Propósito / límite |
| --- | --- | --- |
| Experimentos de percepción, modelos y zonas | [Síntesis cronológica](etapa3-experimentos.md) | Configuraciones, datasets y resultados propios de cada campaña; no extrapolar A/B/C |
| Requisitos e integración | [Matriz transversal](ETAPA3-VALIDATION-MATRIX.md) | Pruebas E2E, Campaign I/II y actualización vigente; conserva cortes históricos |
| Persistencia de objeto único y pares | [Campaign II](ETAPA3-VALIDATION-MATRIX.md#campaign-ii--contrato-operacional-por-pares-24-10-2026), [Backend](../../backend/README.md#publicación-operacional-desde-sesiones-web) | Journal, snapshots, PNG, HTTP y PostgreSQL; fixtures E2E no evalúan detectores |
| Histórico y consultas | [OP-40 histórico](../../backend/evidence/OP-40-event-query.md), [matriz vigente](ETAPA3-VALIDATION-MATRIX.md) | Período/tipo; ambos tipos comprobados posteriormente en Campaign II |
| Indicadores | [OP-41](../../backend/evidence/OP-41-event-frequencies.md) | Frecuencias UTC y conciliación; no tasas de incidentes o riesgo |
| Fallos, retries e idempotencia | [Matriz](ETAPA3-VALIDATION-MATRIX.md), [outbox](../src/operix_engine/event_outbox.py), [tests de hardening](../../backend/apps/analysis/test_hardening.py) | Recuperación acotada; no entrega infinita ni atomicidad distribuida |
| Performance y stress | [Matriz](ETAPA3-VALIDATION-MATRIX.md#rendimiento-y-estrés-preliminar-del-estado-actual), [OP-43 histórico](OP-43-performance.md) | Protocolos/alcances distintos; no comparar sus FPS directamente |
| Detalle operacional UI | [Modelo de detalle](../../frontend/src/features/events/event-detail-model.ts), [tests](../../frontend/tests/event-detail-model.test.mjs) | Evidencia, mediciones, base temporal y disclosure; validación funcional, no certificación de accesibilidad |
| Holdout PERSON | [Protocolo y freeze](PERSON-INDEPENDENT-HOLDOUT-PROTOCOL.md) | 92 registros, 91 imágenes únicas; anotación y procedencia archivadas fuera de Git |
| Protocolo PERSON V1 | [Manifest congelado](../config/evaluation/person-evaluation-protocol-v1.json), [preparación histórica](etapa3-experimentos.md#person-evaluation-protocol-v1-congelado-antes-de-inferencia--24-10-2026) | Matching, roles y métricas fijados antes de la ejecución; no editar su estado histórico |
| Evaluación PERSON sellada | [Resultados y límites](etapa3-experimentos.md#ejecución-person-evaluation-protocol-v1--24-10-2026) | CURRENT vs referencia; limitación de generalización y posibles omisiones/ambigüedades de GT |
| Docker local/GPU | [Validación](DOCKER-LOCAL-VALIDATION.md), [recibo](docker-local-receipt.json), [guía](../../deployment/docker/README.md) | Infra, GPU real, persistencia y modo nativo preservado; validación local |

## Antecedentes técnicos conservados

| Tema | Documento |
| --- | --- |
| Fuentes, selección y resguardos | [OP-16](OP-16-datasets.md), [OP-18](OP-18-data-selection.md), [OP-42](OP-42-poc-safeguards.md) |
| Feedback | [OP-28](OP-28-feedback-log.md), actividad continua |
| Configuración, zonas, variables y regla inicial | [OP-30](OP-30-configuration.md), [OP-36](OP-36-zones.md), [OP-37](OP-37-spatiotemporal.md), [OP-38](OP-38-rules.md) |
| Entorno y pipeline base | [OP-59](OP-59-environment.md), [OP-33](OP-33-video-processing.md), [OP-34](OP-34-yolo11-detection.md), [OP-35](OP-35-bytetrack.md) |
| Visualización, benchmark y PoC | [OP-60](OP-60-visualization.md), [OP-43](OP-43-performance.md), [OP-61](OP-61-poc.md) |
| Primera integración video/evento | [Prueba local](video-to-event-local.md), [API inicial](../../backend/evidence/OP-39-event-api.md) |

Los documentos históricos no se actualizan para aparentar capacidades o resultados
que no existían en su fecha. Un enlace a código prueba disponibilidad de la
implementación, no reemplaza la evidencia experimental. Imágenes, pesos, anotaciones,
logs y recibos crudos externos no se distribuyen con este índice. No se deben
reejecutar conjuntos protegidos para reproducir una demostración del producto.
