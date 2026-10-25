# Etapa 3 — fuente técnica para actualización académica posterior

Corte: 24-10-2026; base `85c064136233638a2a560357b9a2403086578f73`, más
consolidación documental de esta campaña. **No es un backlog alternativo**, un
acta de aceptación ni una actualización de estados oficiales. No se abrió, copió
o modificó ningún `.xlsm`. Los criterios siguientes describen comportamiento
observado; no sustituyen el criterio académico del archivo vigente. La revisión
humana posterior debe contrastarlos en Work, sin deducir un porcentaje global.

Se agrupa por entregables, no por commit. Los hashes cortos corresponden a commits
existentes del historial; su presencia acredita trazabilidad, no aprobación experta.
La [matriz](ETAPA3-VALIDATION-MATRIX.md) y el [snapshot](ETAPA3-PROJECT-STATE.md)
precisan alcance y pruebas. Ningún resultado de un modelo se atribuye a fixtures.

## Bloques factuales

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
| 18. Reproducibilidad/documentación — RNF-01/02, R-01/02/03 | Locks nativo/Linux, hashes/protocolos, fuentes y evidencia indexada; suites y checks del corte sin fallos | [Índice](README.md), [snapshot](ETAPA3-PROJECT-STATE.md), [terceros](../../THIRD_PARTY_NOTICES.md) | `d6eb909`, `accda35`, `85c0641`; consolidación documental posterior | No equivalencia a reconstrucción bit a bit, auditoría jurídica o cierre académico automático |

## Pruebas del corte y evidencia reutilizada

Regresión final: Motor 353 descubiertas, **351 PASS + 2 SKIP**; Backend **103/103**
con PostgreSQL e integraciones fixture; Frontend **30/30**, lint/typecheck/build
PASS. Django check, migration check sin cambios, ambos pip check, Compose config
CPU/GPU y smoke sintético codec/dependencias PASS. Los SKIP no se declaran aprobados.
No se repite evaluación PERSON, inferencia, tuning, entrenamiento ni campañas de
performance/stress. Los tests de carga ya existentes forman parte de la suite.

## Pendientes para decisión humana posterior

- Validación experta de reglas, geometrías y parámetros; PV-01 no se cierra por tests.
- PERSON v2 **NOT STARTED / DEFERRED**; tampoco se promueve COCO por este documento.
- GT/evaluación MOT formal y ampliación representativa de validación operacional.
- Asociación contextual operador/forklift, separada del GT de detección PERSON.
- Política operacional de retención, acceso, autenticación y controles de privacidad;
  R-02 sigue parcial. Roles/permisos/canales/alertas requieren decisión contextual (PV-02).
- Consolidar informe, feedback y aceptación académica; actualizar después el archivo
  oficial mediante Work. No inventar IDs ni porcentajes a partir de estos bloques.

No se alteran fuentes/GT/métricas selladas, arquitectura, modelos ni comportamiento.
Los artefactos crudos externos están archivados, no se ofrecen como enlaces disponibles
en un clon. TEST2 y REAL_HOLDOUT_V2 no se usan; el holdout PERSON no se vuelve a abrir.
