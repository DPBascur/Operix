# Etapa 3 — snapshot técnico de cierre

## Estado vigente pre-v0.2.0 — 26-10-2026

Base de este checkpoint: `f4652f609beb1121bb6d8a0d2425f1eba28bc0fc`, `dev`
limpio y sincronizado. El corte del 24 de octubre conservado más abajo es
histórico; sus roles de modelos y conteos no sustituyen este estado posterior.

PERSON operacional es **YOLO11M_COCO_PERSON**, SHA
`d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95`,
640 / confidence 0,10 / NMS 0,70, batch 1, FP32 y CUDA:0 para análisis diferido.
Es una selección de desarrollo, **no validación independiente final**. Se conservan
PRE_EVALUATION_PRIMARY_PERSON y YOLO11N_COCO_PERSON con sus resultados históricos.
PERSON v2 sigue diferido; FORKLIFT specialist v2 permanece congelado.

ByteTrack por clase, identidades compuestas y reglas zone_dwell /
person_forklift_proximity forman el flujo integrado. La proximidad mide entre
ambos segmentos inferiores con `person_equipment_nearest_ground_edges_v1`, en
coordenadas normalizadas de imagen; no representa metros ni seguridad física.
Overlay y PNG usan las observaciones del analizador/regla. Pérdidas o nuevos IDs
reinician episodios sin inventar permanencia durante el hueco. La ocupancia queda
en **OCCUPANT_ASSOCIATION_DESIGN_ONLY**, sin supresión de operadores.

Sesiones protegidas frente a cierre/expiración, prelectura de integridad y contrato
temporal CFR están implementados. La Web conserva la referencia de sesión al
navegar; existen controles por generación, editor por coordenadas y una regresión
browser versionada con API fixture. Persisten límites de requests tardías y
recuperación detallados por hallazgo, sin declarar hardening absoluto.

Eventos/PNG, snapshots, journal, reenvío, historial y frecuencias siguen integrados.
Docker mantiene mounts individuales read-only y el modo nativo. La regresión más
reciente de la promoción m registró Motor 421 PASS + 2 SKIP, Backend 125/125,
E2E CUDA real 418/418 frames y dos eventos con PNG; Docker GPU tuvo smoke de un
frame, no otra ejecución completa. **No se repiten esas suites en este checkpoint.**

La [reconciliación pre-v0.2.0](ETAPA4-TECHNICAL-AUDIT.md#19-checkpoint-pre-v020--26-10-2026)
conserva pendientes concretos: replay sintético multiclase, overflow de entradas
de pares, validación PNG, append de journal truncado y deuda UX/documental. La
preparación técnica del release queda **BLOCKED_BY_CRITICAL_ISSUES** hasta cerrar
F09/F13 y ejecutar el gate final. No se crea tag ni se sincroniza main aquí.

La validación externa/contextual experta y la validación operacional final
realista siguen pendientes. No bloquean v0.2.0 como MVP integrado de Etapa 3,
pero sí impiden afirmar v1.0.0/cierre académico final. También permanecen
MOBILE_EQUIPMENT_EXTENSION_NEEDS_MORE_EVIDENCE, ausencia de GT MOT, API local
sin autenticación empresarial y retención manual. No se accede a holdouts ni
se modifica el backlog oficial.

## Corte histórico de cierre — 24-10-2026

Fecha del corte: **24-10-2026**, equipo de desarrollo del proyecto.
Base auditada: `85c064136233638a2a560357b9a2403086578f73` en `dev`, limpia y 0/0
antes de consolidar. Este documento y la actualización de README son posteriores
a esa base; no se atribuyen a ella nuevos resultados experimentales ni un cierre
académico global. No se consulta ni actualiza el Product Backlog `.xlsm`.

## Arquitectura y alcance funcional

Arquitectura conceptual **v1.0**, intacta: video → detección → tracking → variables
espacio-temporales → reglas configurables → evento → registro/histórico.
«La IA percibe el entorno; las reglas interpretan el contexto».

La Web usa Backend/API; Django lanza el worker existente. El Motor usa tipos propios,
dos canales de percepción y tracking por clase, analizador multiclase y reglas
`zone_dwell` / `person_forklift_proximity`. Journal y snapshots preceden al HTTP;
Backend persiste en PostgreSQL y filesystem de evidencia. Histórico, filtros por
dos tipos/período, frecuencias UTC y detalle operacional consumen registros reales.
No hay nuevo microservicio Motor ni acceso directo suyo a DB.

Sesiones temporales, preview y MP4 se distinguen de eventos/PNG persistidos.
El estado de análisis puede ser completado con persistencia fallida; retries/replay
conservan identidad y snapshots. El timestamp civil de upload es proxy del inicio
del análisis más tiempo de video, no fecha de grabación. El detalle mantiene esa
distinción, advertencia de revisión humana y trazabilidad desplegable.

## Requisitos: resumen conservador

La [matriz vigente](ETAPA3-VALIDATION-MATRIX.md#reconciliación-vigente-de-cierre--24-10-2026)
separa **DESIGN / IMPLEMENTATION / VALIDATION**. RF-01/03/04/06/07/08 y RNF-01 tienen
implementación y validación funcional acotada; esto no certifica exactitud MOT ni
validez operacional de geometrías. RF-02 está implementado y evaluado, con una
limitación importante de PERSON. RF-05 funciona con fixtures y ejemplos, con
validación contextual pendiente. RNF-02 conserva mediciones con hardware/alcance
explícitos, sin garantía universal de tiempo real. R-02, PV-01 y PV-02 conservan
pendientes de seguridad, contexto y decisión experta. No se cambia ningún requisito.

## Percepción congelada

| Rol | Estado | Parámetros / resultado |
| --- | --- | --- |
| CURRENT_PERSON | Configuración primaria evaluada, no sustituida | 640 / 0,10 / NMS 0,70; TP 20, FP 39, FN 148; P 0,338983, R 0,119048, F1 0,176211 |
| YOLO11N_COCO_PERSON | REFERENCE_BASELINE | Mismo operating point; TP 151, FP 120, FN 17; P 0,557196, R 0,898810, F1 0,687927; no promoción automática |
| FORKLIFT specialist v2 | Baseline experimental congelado | 640 / 0,45 / NMS 0,55; validation propia TP 273, FP 18, FN 15; R ≈0,948, P ≈0,938, F1 ≈0,943 |
| PERSON v2 | NOT STARTED / DEFERRED | No entrenamiento ni nueva campaña |

SHA CURRENT: `21766a9dc664fac06da3b0b457e0449f25e1696acbf8e7e39993c4b42282083f`.
SHA COCO: `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1`.
SHA FORKLIFT: `1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6`.

PERSON_FINAL_HOLDOUT_V2 **FROZEN**: 92 registros originales; 91 imágenes únicas,
67 positivas, 24 negativas y 168 cajas. Freeze SHA
`A71F2558BB5C2A8DF580B6A2908860A9A89F729487BA1C904A14F37C5ADC5339`.
PERSON_EVALUATION_PROTOCOL_V1 **FROZEN**, SHA
`C2012598048352B9681031301AD4EC76667CA982D2C7D32F64ECECA7D835496F`;
**EXECUTED / PERSON_RESULTS_SEALED**. Matching primario 1:1 IoU ≥0,50.

CURRENT mostró una limitación importante de generalización en el conjunto real
acotado. COCO resultó sustancialmente superior allí, pero conserva su rol de
referencia. `102/frame_000369` tiene posible omisión GT y `104/frame_000472`
ambigüedad sobre fragmentos humanos: solo limitan la interpretación de FP/negativos;
GT, freeze y cifras selladas permanecen intactos. No se afirma independencia de
pretraining externo ni representatividad industrial. El holdout ya fue consultado
y no puede presentarse como test no observado para desarrollo guiado por sus resultados.
Véanse [resultados completos](etapa3-experimentos.md#ejecución-person-evaluation-protocol-v1--24-10-2026).

## Entorno, Docker y regresión del corte

Docker local/GPU y modo nativo preservado: tres servicios, DB propia, checkpoints
individuales read-only, volúmenes de DB/media/sesiones/caché y puertos loopback.
Desktop 4.90.0, Engine 29.7.2, Compose 5.5.1, WSL2/3.0.3.0, RTX 3070 de 8 GB,
driver 616.92; Python 3.12.10, PyTorch 2.14.0+cu130, CUDA 13.0, Ultralytics 8.4.146,
lap 0.5.12. [Recibo y validación](DOCKER-LOCAL-VALIDATION.md).

E2E Docker previo: 277/277 frames de demo autorizada, 3 candidatos, 3 eventos,
0 fallos; PNG/MP4 recuperables, histórico y hashes preservados tras recrear.
Registro de sesiones RAM no restaurado. No se repite esa inferencia en este cierre.

Regresión documental de este corte: Motor **353 descubiertas: 351 PASS + 2 SKIP**;
Backend **103/103** con PostgreSQL e integraciones fixture; Frontend **30/30**,
lint/typecheck/build PASS. Django check, migration check (sin cambios), pip check
de ambos entornos, Compose CPU/GPU config y smoke sintético H.264/dependencias PASS.
No se ejecutan detectores ni holdouts; las omisiones del Motor no se cuentan como PASS.
El test de carga existente forma parte de la suite, no una campaña nueva de stress.

## Límites y trabajo académico restante

- Validación experta de geometrías, reglas y thresholds; no se calculan metros a
  partir de distancia normalizada ni se afirma prevención/confirmación de incidentes.
- GT MOT formal y evaluación ampliada; pérdidas, fragmentación y duplicaciones
  dependen de percepción/escena. No reconocimiento facial ni identidad personal.
- Un operador visible es PERSON válida; la asociación contextual operador/forklift
  sigue pendiente y puede hacer irrelevante una relación de proximidad con su vehículo.
- API sin autenticación empresarial, retención persistente manual y acceso operacional
  por definir. Roles/login demo no son seguridad Backend; PV-02 no impone nuevos canales.
- Rendimiento y Docker dependientes del equipo/configuración; sin despliegue industrial,
  portabilidad GPU universal ni promesa de tiempo real sostenido.
- Revisión del informe, suficiencia metodológica/experta y actualización humana del
  backlog usando el [handoff factual](ETAPA3-BACKLOG-HANDOFF.md). Sin porcentaje global
  ni nuevos IDs académicos inventados. No se asigna culpa ni sanciones automáticas.

Esta campaña solo consolida documentación. No abre `.xlsm`, datasets protegidos,
CVAT ni artefactos crudos; no cambia modelos, arquitectura, código, reglas, DB o UI.
La sincronización de `main` se realiza únicamente si ambas referencias de main son
antecesoras de `dev` sin commits exclusivos; el resultado Git se informa al cerrar,
sin introducir un SHA autorreferente ni mover `v0.1.0`.
