# Operix — auditoría técnica final para Etapa 4

Fecha: **25-10-2026** (America/Santiago). Base auditada:
`7e03a5a5e40b6e6892efc567567da2b7d6a8a647`, rama `dev`.
Al inicio `dev = origin/dev = main = origin/main`, árbol limpio.
Este informe es posterior a la base y no modifica el producto ni sus resultados.

## 1. Resumen ejecutivo

**Operix ya es un MVP integrado; todavía no tiene una validación final suficiente
para presentarlo como sistema terminado bajo condiciones operativas realistas.**
El obstáculo principal no es construir otro Backend o dashboard: es cerrar una
decisión de percepción y demostrar, con alcance explícito y revisión humana, que
la cadena completa produce antecedentes interpretables. Hay además defectos
concretos de sesiones, recuperación y manejo de video que conviene corregir antes
de esa validación. No se identificó un fallo determinista que impida toda demo
actual; los P0 siguientes son **puertas de aceptación final**, no crashes inventados.

Inventario: **2 P0, 12 P1, 6 P2 y 5 DEFER**. Cada ID tiene una sola prioridad.
Complejidad: XS = cambio local; S = acotado con tests; M = varios componentes o
protocolo; L = validación transversal. No son estimaciones de horas.

### Método y límites

- Inspección de Motor, scripts, Backend, Frontend, tests, configuración, Docker,
  arquitectura/ADR y documentación versionada; contraste con el handoff de Etapa 3.
- Reproducciones con fixtures/procesos simulados y comprobación sintética en memoria.
  Se revisó el navegador local: dashboard ejemplo/API, preparación del análisis,
  histórico y detalle de un evento demo existente. No se inició ningún análisis.
  Abrir `/analysis` creó por diseño una sesión demo temporal; navegar fuera activó
  su cleanup. No se publicaron nuevos eventos ni se ejecutó el Motor.
- 141 tests seleccionados del Motor, 24 de Backend sin DB real y 30 de Frontend
  aprobaron durante las revisiones. Frontend se confirmó con Node 24.2.0/pnpm
  11.28.2. Estas selecciones pueden solaparse: no se suman como una suite nueva.
  La regresión completa inmediatamente anterior conserva 351 PASS + 2 SKIP del
  Motor, Backend 103/103 y Frontend 30/30; **no se reejecutó completa aquí**.
- Impeccable se utilizó para contexto y revisión estática/UX. Su detector no emitió
  un reporte utilizable; no se convierte ese silencio en certificación. La revisión
  visual fue acotada al viewport disponible, no una auditoría móvil/WCAG completa.
- No se abrió Excel, holdouts, TEST2, REAL_HOLDOUT_V2, CVAT ni resultados crudos.
  No hubo modelos, entrenamiento, tuning, benchmark ni campaña Docker nuevos.
  Los requisitos se contrastan con instrucciones y documentación versionada;
  **no se certifica el 100 % del backlog académico sin su revisión humana oficial**.

## 2. Estado actual y fortalezas

La arquitectura v1.0 se conserva: video → percepción → tracking → variables
espacio-temporales → reglas → candidato → registro/histórico. Django lanza el
worker; el Motor publica HTTP y no accede directamente a PostgreSQL. Existen
identidades `(clase, track_id)`, reglas de objeto único/pares, snapshots, journal
durable, retries acotados, idempotencia, PNG y resultado MP4 temporal.

RF-07/RF-08 tienen consulta real por período/dos tipos y frecuencias UTC conciliadas.
La interfaz separa ejemplo/API, declara el timestamp proxy del análisis y prioriza
evidencia/mediciones en el detalle. El navegador mostró API conectada y 28 eventos
existentes, sin inferir de ese número cobertura de pares o calidad de percepción.

Los tests ya cubren emisión única mientras la condición continúa verdadera, rearme,
límites float de 1e-9 s, separación de clases/pares/runs, retries secuenciales,
errores DB/PNG, watchdog, cancelación y múltiples solicitudes de inicio. No se
propone rehacer lo que funciona. Docker local/GPU y persistencia tras recreación
tienen evidencia previa; el modo nativo permanece disponible.

**¿Puede usarlo un tercero sin explicación constante?** Puede revisar el histórico,
el detalle y una demo guiada con la infraestructura preparada; todavía no está
demostrado un ciclo autónomo completo. F07/F08 pueden romper ese recorrido y faltan
pruebas browser. `/rules` sigue siendo referencia no persistente y `/zones` conduce
al editor de Análisis; no se confunden con CRUD operacional terminado. Configurar
pesos/entorno y recuperar un outbox sin sesión todavía requiere instrucciones de
terminal. No se impone construir gestión de cámaras o CRUD nuevos sin validar que
formen parte del alcance final. La composición vista es sobria y específica del
producto: no hay evidencia para justificar otro rediseño general por «parecer IA».

## 3. P0 — puertas que bloquean afirmar cierre final

| ID | Área | Problema e impacto | Evidencia | Acción y criterio de cierre | Complejidad |
| --- | --- | --- | --- | --- | --- |
| F01 | PERSON / RF-02 | El flujo web sigue fijado a CURRENT_PERSON, cuyo recall independiente fue 0,119048 y F1 0,176211. Una demo sintética correcta no acredita cobertura de personas en condiciones realistas. | [SHA y lanzamiento](../../backend/apps/analysis/sessions.py#L42), [resultados sellados](etapa3-experimentos.md#ejecución-person-evaluation-protocol-v1--24-10-2026) | Decisión humana post-evaluación: mantener y acotar explícitamente el alcance o aprobar otra configuración congelada, con regresión downstream y evidencia operacional prospectiva. No ocultar el resultado ni promover COCO por defecto. | M |
| F02 | Validación final / RF-05, RNF-02, PV-01 | Falta evidencia final contextual/experta que vincule condiciones reales, parámetros, errores aceptables y uso por un tercero. Las pruebas técnicas no equivalen a validación del sistema preventivo ni a aceptación académica completa. | [Snapshot y pendientes](ETAPA3-PROJECT-STATE.md), [matriz](ETAPA3-VALIDATION-MATRIX.md), [handoff](ETAPA3-BACKLOG-HANDOFF.md) | Acordar alcance y criterios antes de probar; ejecutar un protocolo final autorizado con casos operativos realistas, etiquetas de condiciones/revisión experta, resultados negativos y conclusiones. Incluir límites de duración, recursos, privacidad/retención y feedback. Reconciliar después el backlog oficial humanamente. | L |

### Decisión PERSON recomendada, sin ejecutarla

La Web obtiene rutas de `OPERIX_PERSON_WEIGHTS`/`OPERIX_FORKLIFT_WEIGHTS`, pero el
SHA esperado PERSON está fijado en `sessions.py:42`; `_start_session():454–484`
lo transmite al worker. `stream_dual_perception.py:159–185` verifica los pesos y
construye el detector a 640 / confidence 0,10 / NMS 0,70. Cambiar solamente la ruta
del `.env` a COCO **no es una promoción válida**: el gate de hash lo rechaza.

COCO obtuvo recall 0,898810 y F1 0,687927, pero también 120 FP frente a 39 de
CURRENT. Recomiendo elevar COCO a **candidato de decisión post-evaluación**, no
declararlo automáticamente productivo o industrialmente validado. Una adopción
autorizada debe versionar identidad/configuración, revisar gates, snapshot/source,
comandos y tests, y comprobar tracking, reglas, volumen de eventos y evidencia.
Debe conservar FORKLIFT v2 y permitir comparar contra el estado anterior.

El holdout ya informó esta decisión: no puede reutilizarse como confirmación ciega
del cambio. No se corrige GT ni se recalculan métricas por las posibles omisiones
en `102/frame_000369` o la ambigüedad de `104/frame_000472`. Una confirmación final
distinta necesita un protocolo prospectivo y material autorizado independiente.
PERSON v2 sigue diferido; no es necesario entrenar para resolver primero F01.

## 4. P1 — calidad importante antes de validación final

| ID | Área | Problema e impacto | Evidencia / fuerza de comprobación | Acción recomendada y test faltante | Complejidad |
| --- | --- | --- | --- | --- | --- |
| F03 | Backend / lifecycle | DELETE retira la sesión del registro y `close()` libera la referencia antes de terminar el hijo. Puede arrancar otro worker o uno sobre una referencia ya retirada. Rompe la exclusión GPU. | [remove_session](../../backend/apps/analysis/sessions.py#L367), [close](../../backend/apps/analysis/sessions.py#L213), [start](../../backend/apps/analysis/sessions.py#L437); intercalación determinista reproducida | Estado de cierre irreversible y reserva hasta terminar el hijo; validar pertenencia al registro. Test DELETE↔START entre sesiones y con referencia antigua. | M |
| F04 | Backend / expiración | La expiración decide bajo lock, lo libera y después elimina sin revalidar. Un START aceptado en medio puede ser terminado por una decisión antigua. | [expire_session](../../backend/apps/analysis/sessions.py#L411); intercalación reproducida, sin procesos reales | Hacer atómica la decisión/transición de expiración frente al inicio. Test timer↔START y actividad renovada. | S |
| F05 | Motor / integridad del video | Un `read=False` prematuro se trata como EOF. La salida se contrasta con lo procesado, no con la discrepancia de entrada; puede terminar en 100 % ocultando un truncamiento. | [lectura](../src/operix_engine/video_processor.py#L138), [validación de salida](../scripts/stream_dual_perception.py#L327); fixture de 100 declarados/2 leídos acabó completed con total 2 | Conservar total declarado/observado y reportar discrepancias con tolerancia, no exigir metadata exacta. Test fin prematuro con MP4 parcial internamente válido. | S |
| F06 | Temporal / video real | Tiempo y permanencia usan índice/FPS nominal; se exporta CFR. Un VFR aceptado sin aviso puede tener otra duración/semántica temporal. | [analizador](../src/operix_engine/spatiotemporal.py#L172), [writer](../scripts/stream_dual_perception.py#L192); deducción y fixture aritmético, no video VFR real | Definir contrato mínimo: detectar/rechazar o advertir VFR no soportado, o preservar PTS si se exige. Tests PTS irregulares, FPS ausente, clip corto/largo y orientación/resolución; sin redondear timestamps para ocultarlo. | M |
| F07 | UX / navegación | Desmontar Análisis envía DELETE sin confirmación: navegar al histórico puede cancelar trabajo y borrar fuente/MP4 temporal. El PNG/evento persistido es independiente. | [cleanup UI](../../frontend/src/features/analysis/analysis-workspace.tsx#L115), [borrado Backend](../../backend/apps/analysis/sessions.py#L367); inspección de código y navegación sin inferencia | Elegir continuidad al navegar o advertencia inequívoca antes de salir. Test navegación durante procesamiento y con resultado completo; no requiere persistir todas las sesiones para siempre. | M |
| F08 | UX / concurrencia | «Cambiar fuente» superior no se bloquea con busy; start/stop/applyZone no verifican generación al resolver. Una respuesta antigua puede reemplazar la sesión nueva. | [selector](../../frontend/src/features/analysis/analysis-workspace.tsx#L579), [acciones](../../frontend/src/features/analysis/analysis-workspace.tsx#L318); riesgo deducido del flujo, no reproducido en browser | Proteger todas las operaciones por identidad/generación y bloqueo coherente. Tests con promesas retrasadas y cambio de fuente durante START/STOP/PUT. | M |
| F09 | Motor / evidencia replay | `render_track_frame` busca solo track_id. PERSON 1 + FORKLIFT 1 produce error aunque el candidato PERSON exista. El CLI marca evidence_render_error. | [renderer sintético](../src/operix_engine/event_evidence.py#L27), [replay](../scripts/evaluate_rules.py#L122); reproducido en memoria | Usar identidad compuesta también en selección/resaltado y probar IDs coincidentes. El replay omite pares explícitamente; documentar ese límite, sin atribuirlo a la Web que sí los persiste. | S |
| F10 | Tests / flujo usuario | No hay suite browser versionada del ciclo completo. Los 30 tests Frontend son funciones; E2E Backend no prueba React, navegación, reproducción ni responsive real. | [scripts](../../frontend/package.json#L10), [tests](../../frontend/tests/), [E2E Backend](../../backend/apps/analysis/test_persistence.py) | Automatizar flujo básico y fallos: fuente→zona→start→resultado→evento→PNG→filtros→indicadores, cancelar/reintentar, móvil y teclado. Percepción fixture, sin pesos ni holdouts. | M |
| F11 | Semántica de proximidad | Un operador dentro de su propio vehículo sigue siendo PERSON válida y puede satisfacer proximidad. No es error del detector ni de la regla geométrica actual, pero limita su relevancia preventiva. | [filtro por clase](../src/operix_engine/dual_perception.py#L54), [regla](../src/operix_engine/rules.py#L264), [caso permitido](../tests/test_pair_rules.py#L353) | Validar con experto si se requiere distinguir peatón/ocupante. No suprimir por containment sin evidencia; cerrar con alcance explícito o asociación contextual validada. | M |
| F12 | Tracking / episodios | Un frame ausente o cambio de ID reinicia estado y puede volver a emitir otra condición para la misma interacción física. La idempotencia HTTP no fusiona episodios nuevos. | [reset espacial](../src/operix_engine/spatiotemporal.py#L159), [episodios](../src/operix_engine/rules.py#L320), [tests](../tests/test_pair_rules.py); comportamiento intencional, no ID switch probado | Caracterizar huecos/reaparición/churn con GT de episodios de desarrollo y acordar semántica. Solo después decidir grace/hysteresis/reconciliación; conservar tests negativos para no unir interacciones distintas. | M |
| F13 | API / entradas inválidas | JSON raíz `[]`, perfil demo desconocido, enteros enormes y Range de miles de dígitos escapan como errores internos en vez de 400/404/416. | [sesiones](../../backend/apps/analysis/views.py#L42), [zona](../../backend/apps/analysis/views.py#L165), [Range](../../backend/apps/analysis/views.py#L212), [par](../../backend/apps/events/pair_contract.py#L13); reproducciones con mocks | Validar forma/tamaño/rango antes de `.get`, `float`, `isfinite` o `int`; tests de cada clase de entrada. No expandir el contrato permitido. | S |
| F14 | Accesibilidad / editor | Tras «Nueva zona», solo el puntero agrega vértices. Flechas mueven puntos existentes pero no permiten completar el flujo desde cero por teclado. | [pointer](../../frontend/src/features/analysis/analysis-workspace.tsx#L676), [nueva zona](../../frontend/src/features/analysis/analysis-workspace.tsx#L887); inspección | Inserción por teclado o formulario de coordenadas; test recorrido completo, foco, cierre y error. No rediseñar toda la pantalla. | S |

### Operador ↔ forklift: alternativa mínima defendible (F11)

Containment/intersección de cajas es barata, pero una persona al lado, detrás o
parcialmente ocluida puede parecer contenida: alto riesgo de suprimir un peatón real.
Una región de cabina mejora contexto solo si está calibrada a cámara/vehículo;
no se obtiene de manera fiable de toda bbox. Posición relativa sostenida y
correlación de movimiento aportan evidencia temporal, pero fallan con vehículos
quietos o personas caminando junto a ellos. Una asociación por track mantiene
consistencia, aunque debe romperse/revisarse ante pérdida, ID nuevo o salida.

Propuesta mínima si el experto lo exige: acumulador externo por identidad de par,
con estados **UNKNOWN / POSSIBLE_OCCUPANT / ASSOCIATED_OCCUPANT**, observaciones
explicables y configuración versionada. Empezar como etiqueta para revisión;
no descartar candidatos ambiguos ni tocar PERSON GT. Una supresión automática
requiere validación específica de falsos descartes, no un umbral inventado aquí.
Probar peatón solapado junto al vehículo, ocupante que baja, vehículo quieto,
movimiento paralelo, oclusión, dos forklifts, cambio de IDs y ocupante de otro
vehículo. No se prescribe entrenar otro modelo ni detectar una cabina universal.

### Tracking y tiempo: qué no hacer (F06/F12)

ByteTrack conserva asociaciones con sus buffers, pero el analizador solo ve los
tracks emitidos. La semántica vigente rompe continuidad ante observación ausente;
esto evita fabricar permanencia durante pérdidas, aunque puede fragmentar episodios.
Los thresholds temporales se expresan en segundos; max_distance es distancia de
imagen normalizada, **no metros**. La tolerancia float 1e-9 s no es grace period.
No se justifica añadir hysteresis por intuición o convertir Operix en otro tracker.
Una evaluación MOT formal ampliaría conocimiento, pero no sustituye GT de las
condiciones que la regla realmente pretende señalar.

## 5. P2 — mejoras deseables, sin bloqueo central demostrado

| ID | Área | Problema / impacto | Evidencia | Acción propuesta | Complejidad |
| --- | --- | --- | --- | --- | --- |
| F15 | Evidencia | PNG con chunk crítico desconocido y CRC válido pasa validación pero no decodifica. Posible evidencia ilegible anunciada como válida. | [validate_png](../../backend/apps/events/views.py#L132); fixture RGB 1×1, chunk ABCD, 103 bytes, OpenCV devuelve None | Rechazar chunks críticos desconocidos y probar control válido/Adam7; conservar límites de expansión. | XS |
| F16 | Outbox | Encolar tras una cola NDJSON interrumpida concatena la siguiente entrada; si su envío inmediato falla, replay no recupera esa entrada. | [append](../src/operix_engine/event_outbox.py#L67), [lector](../src/operix_engine/event_outbox.py#L132); fixture; requiere reutilizar directorio, no el run web normal | No continuar append sobre cola inválida sin separar/cuarentenar; conservar recibos y test interrupción→enqueue→replay. | S |
| F17 | UX / red | Lista y detalle carecen de plazo explícito de fetch; una conexión pendiente puede dejar loading indefinido. | [adapter](../../frontend/src/services/adapters/api.adapter.ts#L34), [detalle](../../frontend/src/features/events/event-detail.tsx#L285) | Timeout/cancelación/reintento coherentes; tests de petición que nunca resuelve. | S |
| F18 | UX / investigación | Volver del detalle pierde período/tipo porque los filtros no viajan en URL/retorno. | [tabla](../../frontend/src/features/events/events-table.tsx#L43), [retorno](../../frontend/src/features/events/event-detail.tsx#L320) | Guardar consulta en URL y restaurar contexto; test ida/vuelta. | S |
| F19 | Documentación / release | Demo principal es histórica; faltan release notes y captura vigente del flujo UI. Hay drift puntual en referencias visuales. | [demo](../../assets/demo/README.md), [surface brief](../../.impeccable/surfaces/frontend-src-app-page-tsx.md#L16), [UI histórica](../../frontend/UI_REFRESH.md) | Preservar históricos, rotularlos; preparar notas/captura nueva solo en campaña autorizada. No inventar evidencias ni borrar assets. | S |
| F20 | Mantenibilidad | Workspace de 1.196 líneas, CSS de 2.726/1.906 líneas y configuración repetida entre snapshot/lanzamiento/worker dificultan revisar races y drift. | [workspace](../../frontend/src/features/analysis/analysis-workspace.tsx), [CSS](../../frontend/src/app/globals.css), [snapshot](../../backend/apps/analysis/sessions.py#L463), [detector](../scripts/stream_dual_perception.py#L176) | Después de tests de comportamiento, separar lifecycle y configuración efectiva en unidades pequeñas. No crear framework de plugins ni refactorizar por estética. | M |

No se encontraron TODO/FIXME relevantes que por sí solos acrediten features sin
terminar; la ausencia de TODO no demuestra completitud. No se acusa código de ser
«generado por IA»: se señalan límites concretos de tamaño, duplicación y revisión.

## 6. DEFER — no forzar para este Trabajo de Título

| ID | Área | Motivo / evidencia | Acción delimitada | Complejidad |
| --- | --- | --- | --- | --- |
| F21 | Seguridad empresarial | Login/roles son demo; PV-02 no impone SSO/RBAC multitenant, canales ni alertas. [Settings](../../backend/config/settings.py#L80) no autentica API. | Mantener loopback y política mínima de acceso/retención para F02; decidir autenticación real si se amplía audiencia/red, no construir una plataforma IAM. | L |
| F22 | Infraestructura distribuida | Single API/worker es límite explícito y probado; Docker no exige Motor REST, Redis/Celery, Kubernetes o cloud. [Guía](../../deployment/docker/README.md) | Preservar arquitectura; escalar solo ante demanda validada. | L |
| F23 | Investigación de modelos/tracker | PERSON v2, ReID y nuevos trackers no son requisito automático del resultado bajo de CURRENT. [Estado](ETAPA3-PROJECT-STATE.md) | Resolver primero F01 con decisión explícita; no entrenar ni consumir TEST2/holdouts por conveniencia. | L |
| F24 | Sesiones recuperables tras reinicio | El registro RAM no se restaura aunque Docker preserve archivos. Los eventos/PNG sí persisten. No se exige reanudar cada trabajo. [Límites](../../deployment/docker/README.md#persistencia-y-límites) | Documentar sesión temporal; recuperar historial/evidencia. Persistencia de sesiones/multiworker solo si se exige, no para ocultar F07. | M |
| F25 | Paginación/escala ilimitada | API devuelve lista completa; carga mixta de 1.000 filas está probada, no hay pérdida demostrada. [Carga](../../backend/apps/events/test_validation_stress.py) | Delimitar tamaño/período de validación. Paginar después con contrato de filtros/agregados, desempates e inserciones concurrentes si el volumen lo requiere. | M |

## 7. Seguridad, privacidad, configuración y rendimiento

Escaneo textual del árbol versionado: **sin coincidencias** de rutas personales
de usuario, prefijos usuales de tokens o claves privadas; **0 archivos tracked que
coincidan con ignore**. No es una garantía de ausencia de todo secreto ni auditoría
histórica Git. No se imprimieron valores `.env`. Los ejemplos no sustituyen
credenciales locales; no hay pesos ni datos de evaluación en la imagen Docker.

Hay validación de UUID/rutas de demo, nombres de archivo sin directorio, tamaño de
upload, lectura restringida de evidencia y nombre/hash de outbox. No se comprobó
un path traversal explotable. F13/F15 son defectos reales de validación, no prueba
de ejecución remota. La API AllowAny no debe exponerse a red no controlada: R-02
requiere delimitar acceso, consentimiento/procedencia, retención, respaldo conjunto
DB+media y prueba de recuperación. No se requiere enterprise RBAC por defecto.

Docker: tres servicios, PostgreSQL sin puerto publicado, Web/API loopback, usuarios
sin privilegios, pesos/input read-only y volúmenes propios. Imagen Backend ~3,43 GB,
primer build OpenCV ~782 s; los pins Linux se aplican tras instalación inicial y
apt/bases no están fijados completamente por digest en Dockerfile. Esto limita
reconstrucción bit a bit, ya advertida; no bloquea su uso local documentado. No hay
hallazgo que justifique repetir u optimizar toda la campaña Docker.

Performance previa: worker dual fresco ~17,439 FPS sin HTTP/publicación; renderer
~11,045 ms/frame; Docker E2E ~29,56/26,54 s por 277 frames con otro entorno/codec.
OP-43 usa otro protocolo: no comparar esas cifras como mejora/regresión. El worker
recarga dos modelos por proceso, genera previews y vuelve a decodificar la salida
completa para verificarla. Son costos verificables, no fugas demostradas. F02 debe
incluir duración/carga realista, límites de disco/retención, timeout y fallos de
almacenamiento; no se debe optimizar sin medir una necesidad real después.

## 8. Impacto en requisitos y trabajo restante

| Requisito | Implementación / validación actual | Bloqueo o límite | Trabajo restante |
| --- | --- | --- | --- |
| RF-01 | Upload/demo, lectura, preview/MP4; E2E local | F03–08/F13; metadata/EOF/VFR | Lifecycle y contrato de video; pruebas realistas |
| RF-02 | Percepción dual; evaluación PERSON sellada y validation FORKLIFT | **F01**; cobertura CURRENT baja | Decisión post-evaluación y confirmación prospectiva |
| RF-03 | ByteTrack por clase, identidades compuestas; tests/clips | F12; no GT MOT ni continuidad física garantizada | Caracterizar pérdidas/churn; acordar episodios |
| RF-04 | Config/polígono normalizado, geometría y editor | F14; validación contextual dentro de **F02** | Flujo teclado y revisión experta de zonas |
| RF-05 | Dos reglas, parámetros/versiones, tests de límites/pares | **F02**, F06/F11/F12 | Semántica/thresholds/contexto y criterio experto |
| RF-06 | Journal, HTTP, Event/PNG, retry, MP4 temporal; E2E | F03–05/F09/F13/F15/F16 | Recuperación/races y evidencia legible, sin prometer video persistente por evento |
| RF-07 | Filtros por período/dos tipos con carga conciliada | F17/F18; escala limitada explícita | Recuperación de requests y continuidad de consulta |
| RF-08 | Frecuencias UTC e indicadores reales separados de demo | **F02** limita interpretación, no cálculo | Validar uso por tercero; no convertir conteos en riesgo |
| RNF-01 | Regla/versión/parámetros/run/source/par/frame | F06/F09/F12, timestamp proxy documentado | Conservar trazabilidad de cambios/errores y definición de episodio |
| RNF-02 | Instrumentación y protocolos previos con entorno | **F02**; clips y recursos acotados | Prueba final con carga/duración acordadas; sin promesa universal de 30 FPS |
| R-01 | Procedencia/licencias y separación de conjuntos documentadas | No verificación jurídica nueva ni autorización genérica | Derechos individuales de cualquier recurso final nuevo |
| R-02 | Datos externos, loopback, retención manual | **F02**: política final/acceso/respaldo por cerrar | Política mínima local y recuperación DB+media, no IAM empresarial |
| R-03 | Sin biometría/culpa/sanciones; advertencia humana | No bloqueo nuevo observado | Mantener lenguaje y revisión contextual |
| PV-01 | Parámetros configurables y snapshots | **F02**: falta validación experta | Justificación contextual, unidades y límites |
| PV-02 | Decisiones de roles/canales/alertas pendientes | No se impone feature nueva; F21 | Acordar alcance con experto y registrar exclusiones |

El handoff ya recoge implementación, protocolos y pendientes: no hay que volver a
desarrollar variables, reglas, persistencia, indicadores o Docker. Esta auditoría
añade defectos y gates verificables; no inventa OP nuevos ni estados del Excel.

## 9. Inventario documental, multimedia y release hygiene

Se inventariaron **44 Markdown, 7 PNG, 4 PDF, 3 MP4 y 1 SVG** versionados.
Los destinos de enlaces relativos examinados no dieron archivos ausentes; no se
certifica disponibilidad de todos los links externos/attachments ni anclas de cada
documento histórico. No se reprodujeron clips ni se inspeccionaron holdouts.

| Grupo / ubicación | Clasificación | Acción para una versión actual |
| --- | --- | --- |
| README principal, guías Motor/Backend/Frontend/Docker, PRODUCT, avisos/NOTICE | CURRENT | Mantener; describen limitaciones y fuentes reales |
| Índice, snapshot, handoff y cabecera de matriz de Etapa 3 | CURRENT | Añadir posteriormente referencia a este audit si se autoriza; no reescribir su corte |
| Síntesis experimental y protocolo de adquisición PERSON | CURRENT con secciones HISTORICAL | Mantener resultados/sellos y cronología; no modificar manifiestos congelados |
| OP-16/18/28/30/33–38/42/43/59–61, primera integración local y Backend OP-39/40 | HISTORICAL | KEEP_AS_HISTORICAL; OP-28 es actividad continua, no cierre global |
| Backend OP-41 | HISTORICAL; frase de único tipo STALE como contrato vigente | KEEP_AS_HISTORICAL; usar guía/matriz actual para dos tipos, no falsear resultado antiguo |
| Docker validation/receipt y frontend UI_REFRESH | HISTORICAL, con alcance/fecha declarados | KEEP_AS_HISTORICAL; no repetir sus pruebas por documentación |
| DESIGN y surface brief Impeccable | CURRENT con drift / STALE en brief glass | REPLACE_FOR_V0.2.0 la descripción normativa discordante, no el diseño por obligación |
| Arquitectura v1.0: README, seis diagramas, ADR-01–05 y exportación | CURRENT como diseño cerrado, HISTORICAL como hito | KEEP_AS_HISTORICAL; no alterar arquitectura para perseguir estado de implementación |
| Tres PDF C4 individuales y exportación completa | REDUNDANT intencionalmente | KEEP_AS_HISTORICAL; sirven extracto y documento original |
| Capturas del producto actual, recorrido móvil/error y release notes | MISSING | NEEDS_NEW_CAPTURE y notas nuevas en campaña posterior, sin generar medios aquí |
| Links relativos examinados | BROKEN: ninguno detectado | No se identificó referencia interna concreta que retirar |

### Material mostrado en README/docs/assets

- `assets/demo/forklift_human_nearmiss_ceiling00.mp4`: **KEEP_AS_HISTORICAL**,
  entrada OP-34 y limitación COCO/forklift; no prueba del detector dual actual.
- `warehouse_fire_ceiling04.mp4`: **KEEP_AS_HISTORICAL**, entrada sintética autorizada
  reutilizable; `warehouse_fire_ceiling04_operix_annotated.mp4`: **KEEP_AS_HISTORICAL**,
  salida histórica PoC, no recorrido de UI/versión actual.
- Tres `user-attachments` del README: conservar mientras estén rotulados como
  muestras históricas. **REPLACE_FOR_V0.2.0** su función de demo principal con un
  recorrido nuevo autorizado; **REMOVE_REFERENCE** solo si un enlace resulta roto
  o se presenta engañosamente como evidencia actual, no por su antigüedad sola.
- Los seis PNG y cuatro PDF son arquitectura, no screenshots de aplicación.
  Marca PNG y SVG son **CURRENT**. No se encontró GIF versionado ni captura actual
  de UI en Git. Las capturas locales relatadas en UI_REFRESH no están en el clon:
  **NEEDS_NEW_CAPTURE**, sin fabricar que se revisó hoy móvil/lector de pantalla.

## 10. Orden de ejecución y campañas

### Top 10 next actions — orden estricto por impacto

1. **F01:** decidir configuración PERSON post-evaluación y congelar su alcance.
2. **F02:** acordar aceptación final, experto, material autorizado y protocolo prospectivo.
3. **F03/F04:** cerrar atómicamente lifecycle/reserva GPU y expiración frente a START.
4. **F05:** impedir que truncamientos queden ocultos como análisis completo.
5. **F06:** fijar y verificar el contrato temporal de videos reales/CFR/VFR.
6. **F07/F08:** preservar contexto al navegar y evitar respuestas obsoletas/cambio de fuente concurrente.
7. **F10/F13:** incorporar regresión browser del ciclo y entradas inválidas controladas.
8. **F11/F12:** validar relevancia operador/vehículo y continuidad de episodios sin inventar observaciones.
9. **F09/F14/F15:** cerrar evidencia multiclase, acceso por teclado y PNG ilegible.
10. **F02/F19:** ejecutar la validación final acordada, preparar demo/notas actuales y auditar el release.

Campañas propuestas, sin ejecutarlas:

- **A — Decisión PERSON y protocolo final:** F01/F02; aprobación humana antes de
  modificar gates/modelos. Criterio: configuración y alcance inequívocos, sin reutilizar
  el holdout como confirmación independiente ni iniciar v2 automáticamente.
- **B — Sesiones y video confiables:** F03–06/F13; fixtures deterministas para carreras,
  EOF prematuro, timestamps y entradas inválidas. Sin cambiar arquitectura.
- **C — Condiciones y evidencia:** F09/F11/F12/F15/F16; definir semántica con experto
  antes de grace o supresión; medir falsos descartes si se exige asociación.
- **D — Flujo Web final:** F07/F08/F10/F14/F17/F18; browser E2E, teclado y matriz de
  escritorio/móvil; mejora acotada de interacción, no rediseño estético.
- **E — Validación final y release:** ejecutar F02 después de corregir lo pertinente,
  política R-02, regresión, feedback, demo y notas F19; evaluar tareas oficiales
  humanamente. F20 solo si ayuda a aislar los defectos, no refactorizar por moda.

## 11. Readiness v0.2.0 y Etapa 4

**Etapa 4: lista para comenzar con plan priorizado; no lista para declararse terminada.**
El 100 % de implementación y la aceptación final deben contrastarse con el backlog
oficial y el evaluador. Los P0 no se cierran contando tests o ocultando recall.

**v0.2.0 como corte experimental de Etapa 3: candidato condicionado**, no certificación
de cierre final ni de producción. Árbol base limpio, README actualizado, suites previas
y Docker documentados favorecen el corte; faltan notas/demo actual y una decisión
explícita sobre publicar con defectos conocidos o corregir antes F03–F10. Un tag
experimental puede declarar límites; no debe prometer validación final inexistente.

No se crea tag ni Release, no se toca `main`, no se actualizan Issues/Project/Excel.
Solo este informe puede publicarse en `dev`. Resultado de la auditoría:
**ETAPA4_TECHNICAL_AUDIT_COMPLETE + P0_EXECUTION_PLAN_READY + NO_PRODUCT_CHANGES**.

## 12. Hardening de sesiones y video — 25-10-2026

Seguimiento posterior sobre `a00aa827a17ddbca49781bea6cc90d4ced49dc90`.
Los hallazgos anteriores describen el corte auditado, no se borran ni se cambian
retrospectivamente. Esta intervención aborda F03–F06 y las entradas de análisis
de F13. No declara cerrada la validación operacional ni toda la auditoría.

**Sesiones.** Antes, DELETE retiraba la sesión del registro antes de terminar su
worker; START podía usar una referencia retenida o reservar otra GPU mientras el
proceso anterior seguía vivo. Expiración decidía borrar fuera de la exclusión de
START. Ahora el mismo bloqueo local serializa START/STOP/DELETE/expiración; DELETE
mantiene la reserva hasta `terminate/wait` y marca el cierre irreversible. START
exige pertenencia al registro. No se añaden locks ni polling nuevos.

El flujo público sigue `ready → preparing → processing → completed/error`, con
STOP hacia `cancelled`. START **explícito** permite otro run desde ready o terminal,
cuando el proceso anterior ya murió. DELETE/expiración no son reinicios y hacen
irrecuperable esa sesión. Los timers llevan generación propia; START invalida el
anterior. Los watchers comprueban proceso, run y cierre antes de tocar salidas.
Un cancel tardío consulta el estado final y no sustituye completed/error. Cleanup
solo borra el directorio de la sesión cerrada; el journal persistente queda fuera.

**Video.** El worker web hace prelectura decodificada antes de cargar modelos o
emitir candidatos. Un total declarado diferente del decodificado impide confirmar
integridad, incluso por un frame. `TRUNCATED_INPUT` indica lectura insuficiente,
no prueba por sí solo corrupción: metadata aproximada también puede causar rechazo.
Sin total declarado, la prelectura fija el conteo con advertencia. La segunda
lectura debe repetirlo; después se verifica el MP4 H.264 completo, FPS y resolución.
Solo entonces el worker emite `completed`, `NORMAL_EOF` y 100 %; la API espera
además su salida exitosa antes de exponer éxito, aunque ya exista el receipt.
Lectura vacía, excepción
del decoder, metadatos inválidos o discrepancia no se convierten en éxito.

Durante prelectura el porcentaje es indeterminado; processing se limita a 99,9 %.
Error conserva los últimos frame/total conocidos y su causa `termination_reason`,
sin stack trace público; cancel reporta `CANCELLED`. No se amplía el enum de estados.
Un fallo posterior no revoca candidatos completos ya publicados: journal/PNG y
eventos conservan su semántica anterior y requieren revisión si la sesión falló.
No existe transacción de todo el video ni rollback automático.

**Tiempo.** La ruta web admite CFR. Usa `CAP_PROP_POS_MSEC` leído después de cada
frame, relativo al primer timestamp, si es finito, creciente y concordante con
FPS nominal. La comprobación de cadencia acepta precisión del reloj de contenedor
hasta `max(2 ms, 2 % del intervalo nominal)`, no una tolerancia operacional.
Cadencia irregular observable o FPS discordante se rechaza (`UNSUPPORTED_VFR`);
no se remuestrea ni se cambia tracking. OpenCV documenta propiedades dependientes
del backend: [referencia Video I/O](https://docs.opencv.org/5.0/main_modules/videoio_flags_base.html).

Si un backend solo entrega ceros, usa `frame_index / fps` con provenance explícita
`NOMINAL_FPS_UNVERIFIED_CFR` y advertencia: **no puede descartar VFR en ese caso**.
Un único frame usa tiempo relativo cero. FPS cero/no finito se rechaza. El analizador
acepta timestamps explícitos y calcula permanencia por diferencia; las reglas de
zona y pares consumen el mismo tiempo. Parámetros, distancias, umbrales y tolerancia
numérica de reglas de 1e-9 s no cambian. La ancla UTC sigue siendo inicio de análisis,
no fecha real de grabación. Los CLI diagnósticos históricos conservan el supuesto
nominal CFR; no se les atribuye automáticamente el preflight web.

`timestamp_source` y `warnings` se conservan en status y resultado temporal. No se
añaden propiedades al contrato persistido de eventos ni se reescriben registros.
No se crea una migración. Frontend ya distingue error/cancelled y porcentaje null;
no necesita cambios ni otro diseño para este contrato compatible.

**Entradas y rutas.** JSON no objeto, perfiles no escalares/inválidos, parámetros
ausentes, vértices fuera de rango incluso con enteros enormes: 400. Range numérico
desmesurado: 416. Upload se guarda con nombre interno `input.<ext>` en su directorio
temporal; el nombre del cliente no elige ruta. Un path JSON no abre archivos locales.
Las demos usan exclusivamente paths de configuración del servidor; Docker conserva
mounts de pesos/entradas de solo lectura. Un contenedor/cabecera aceptado pero
ilegible se rechaza asincrónicamente en el worker. Esto no es almacenamiento enterprise.

**Regresión ejecutada.** Motor: 374 descubiertas, 372 aprobadas y 2 integraciones
opt-in omitidas. Backend nativo y Docker Linux: 121/121 en cada entorno, incluidas
las pruebas E2E con percepción fixture, worker real, ByteTrack, reglas, HTTP,
PostgreSQL, PNG y H.264. No se confunden esas fixtures con inferencia real nueva.
Se repitieron 60 intercalados controlados START/DELETE/timer sin fallos, sin sleeps
arbitrarios. Decoder Linux: 18/18 fixtures; CFR, un frame, EOF prematuro, conteo
desconocido, error decode, FPS inválido y reloj irregular/no disponible.
Frontend intacto: 30/30, lint, typecheck y build correctos con Node 24.2.0/pnpm
11.28.2. Django check, migrations check, ambos pip check, Compose config y
`git diff --check` correctos.

**Revisión adversarial y límites.** Se descartó tolerar pequeñas diferencias de
conteo: ocultaba truncados cortos. No hay cola, state machine paralela ni nuevas
dependencias. La exclusión sigue limitada a una instancia API y puede bloquear
otras solicitudes de ciclo de vida mientras termina el proceso (espera acotada).
La prelectura agrega una pasada de decode y memoria O(frames) para timestamps;
no es optimización ni nuevo benchmark. Sin total confiable y sin timestamps útiles,
OpenCV no permite demostrar ausencia de toda corrupción: una prelectura y segunda
lectura concordantes tampoco prueban que un archivo ya truncado antes de ingestarlo
contenía originalmente más frames. No se promete detección perfecta ni soporte VFR.

PERSON operacional COCO, FORKLIFT specialist v2, pesos, thresholds, reglas/config,
ByteTrack, frontend, arquitectura, DB y contratos persistidos permanecen intactos.
No se usaron holdouts, TEST2 ni REAL_HOLDOUT_V2; no hubo entrenamiento, tuning,
inferencias nuevas ni campaña de rendimiento. Main y tags quedan fuera del cambio.
