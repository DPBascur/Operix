# Operix — auditoría técnica final para Etapa 4

**Vigencia:** la [sección 21](#21-demo-y-documentación-pre-v020--26-10-2026) cierra F19.
La sección 20 registra el cierre de F08/F09/F13; la sección 19 conserva el checkpoint
previo. Las demás secciones mantienen sus decisiones y resultados históricos.

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

## 13. Proximidad y visualización operacional — 25-10-2026

Base: `d30dbf19e5e96963180c3372dc1bfd4454ac0cca`, `dev` limpio y sincronizado.
La reconstrucción inicial confirmó que OP-37 calcula `math.dist` entre posiciones
bottom-center: `((xmin+xmax)/(2*width), ymax/height)`. La regla consume esa distancia,
no vuelve a calcular geometría. Se conserva exactamente esta definición: distancia
euclídea **normalizada por cada eje**, rango geométrico 0–sqrt(2), sin unidades
físicas, homografía ni corrección de perspectiva. No equivale a distancia sobre
el piso; cajas ocluidas/imprecisas pueden mover el punto observado.

La configuración exige zona, distancia máxima y duración mínima; clases de cada
rol son configurables. Ambos objetos deben estar dentro de la zona. Los perfiles
web A/B/C actuales solo habilitan zone_dwell: el overlay no los modifica ni inventa
eventos para exhibirse. Los números 0,25/1 s de las pruebas siguientes pertenecen
al fixture E2E ya existente, no son parámetros industriales ni tuning de demos.

### Revisión histórica y contrato

| Elemento revisado | Clasificación | Decisión |
| --- | --- | --- |
| `323d175`, identidad multiclase/OP-37 | ALREADY_IMPLEMENTED | Conservar `(class_name, track_id)`; no renumerar trackers. |
| `5a4c615`, regla por pares y `_PairEpisode` | ALREADY_IMPLEMENTED | Conservar emisión única y rearme por interrupción. |
| `e286f71`, comparación temporal | ALREADY_IMPLEMENTED | Conservar tolerancia numérica 1e-9 s. |
| `4165fac` / `1bb83bc`, renderer/zonas y buffers | ALREADY_IMPLEMENTED | Extender el renderer actual, sin duplicarlo. |
| Rama `autonomous/etapa3-demo-hardening`, fixes de sesiones antiguos | OBSOLETE | No portar sobre el hardening ya publicado. |
| Misma rama, `ResidentDetectors` experimental | UNSAFE_TO_PORT | Cambiaría residencia/ciclo de modelos; ajeno a esta campaña. |

Se revisaron referencias, historial y worktrees registrados: solo existe el checkout
actual; no se encontró un overlay de distancia pendiente para reutilizar. No hubo
merge/cherry-pick ni modificación de ramas históricas.

El par tiene roles explícitos `InteractionIdentity(person, forklift)` con identidades
de clase. PERSON #1 y FORKLIFT #1 no colisionan. Se expone `episode_key` en evaluación
y candidato: regla, versión, par, zona y frame inicial, **local al run**. La identidad
completa entre ejecuciones necesita además `analysis_run_id`, como el transporte
existente. No se inventa un UUID persistido ni se cambia el contrato HTTP: `episode`
ya conserva frame/tiempo inicial, y el evento/idempotencia conserva el run/par/regla.

El inicio queda ahora disponible también durante acumulación, junto con distancia,
duración y estado. La condición sostenida emite una vez; una ausencia de cualquiera
de los tracks, gap de frames, cambio de ID, salida de zona/distancia o reset cierra
el episodio; una reentrada inicia otro desde cero. Tiempo explícito creciente gobierna
la duración; no se reemplaza por frames/FPS. No hay gracia, reassociation, cooldown
ni histéresis. Una oscilación real puede rearmar: sin caracterización operacional
que justifique ENTER/EXIT distintos, no se oculta esa discontinuidad.

### Overlay y evidencia

`OpenCvRenderer.render_proximity(frame, spatial, result)` consume posiciones de
OP-37 y valores de `PairRuleEvaluation`. No calcula una distancia alternativa.
Valida correspondencia de frame/tiempo. La línea une esos mismos puntos, con clipping
solo al borde raster; etiqueta cercana muestra IDs y distancia a tres decimales
`norm`. Un carril compacto muestra regla/versión, máximo, duración/mínimo y estado
`DURATION_ACCUMULATING` o `CONDITION_SATISFIED`. Ámbar significa condición satisfecha,
no accidente, infracción, Near Miss ni responsabilidad. El texto se ajusta al ancho.

El conjunto visual incluye únicamente episodios activos, no todo PERSON×FORKLIFT.
Orden estable: emisiones actuales, satisfechas, distancia e identidades. Límite
habitual cuatro, con aviso de omitidos; las emisiones actuales siempre se muestran,
aun si exceden cuatro. No reduce evaluaciones/candidatos. Muchas emisiones simultáneas
o líneas cruzadas todavía pueden saturar la imagen; no se promete layout sin colisiones.

Ambos orquestadores usan el mismo renderer. En el worker, el PNG se deriva de la
misma imagen anotada entregada al writer; solo puede reducirse por el límite de
evidencia. Un PNG/MP4 comprimidos no tienen por qué ser binariamente iguales.
La prueba E2E compara el hash de los píxeles del PNG decodificado con el frame
real retornado por el renderer (fixture sin reducción), y verifica distancia,
duración, roles y estado frente a los eventos persistidos. No reconstruye evidencia
desde un payload separado. Histórico, idempotencia y reenvío siguen aprobando.

### Operador y futura maquinaria móvil: diseño, no implementación

No se suprime una persona porque su bbox esté contenida en otra: perspectiva y
oclusiones permiten que un peatón real cumpla esa condición. Una futura asociación
`LIKELY_OCCUPANT_ASSOCIATION` debe combinar contención relativa, posición respecto
de una región de cabina revisada por cámara y persistencia/co-movimiento sobre
timestamps y trayectorias válidos. Las velocidades/correlaciones no están calculadas
ni calibradas aquí; no se inventan umbrales o probabilidades. Requiere datos anotados
de ocupantes y peatones difíciles, revisión humana y política conservadora de
abstención ante oclusión, gaps o ID inestable.

Su alcance deberá ser **PERSON concreta ↔ SAME FORKLIFT**, nunca eliminar esa
PERSON ni sus relaciones con otros equipos. Conservar observación original y
motivo/trazabilidad de cualquier futura exclusión. No se implementa supresión.

OP-37 ya admite identidades de cualquier clase; la regla admite clases configurables,
pero `DualPerception`, sus canales/estadísticas, `InteractionIdentity`, transporte,
serializers y nombres de perfil mantienen roles person/forklift. Camino incremental:
un adaptador de canales/metadata que describa rol PERSON/MOBILE_EQUIPMENT y subtipo/
source_model; después un contrato/regla nuevo versionado para equipos genéricos,
manteniendo intacto el adaptador legacy `person_forklift_proximity`. No hacer pasar
truck por forklift. No se crea ahora un framework genérico ni se integra truck.

### Validación y alcance del cierre

Motor completo: **384 descubiertas, 382 PASS y 2 SKIP** opt-in de modelos reales.
Diez tests nuevos caracterizan distancia conocida, IDs numéricos iguales en roles
distintos, varios objetos por rol, cruce, solapamiento/contención, cero/bordes,
entrada/salida, pérdida/reemplazo, gaps, duración exacta, tiempo explícito, identidad
de episodio y renderer. Se conserva la regresión previa de reglas; no se cambian
assertions para introducir gracia o suprimir casos incómodos.

Backend completo: **121/121 en Docker**, usando código actual montado en lectura,
PostgreSQL aislado y percepción fixture. E2E: 4 frames, dos pares/emisiones,
PNG verificable, MP4 H.264 decodificado por el worker, eventos consultables e
idempotencia/reenvío correctos. El primer intento nativo no pudo crear la DB de
tests: PostgreSQL estaba apagado/no accesible; **no aprobó esa ejecución**. No se
instaló otra base ni se cambió `.env`; la regresión completa se ejecutó en Docker.
`Django check`, migrations check contra PostgreSQL de QA, ambos pip check y Compose
config aprobaron. Frontend no se modificó; 30/30 tests, lint, typecheck y build aprobaron.

Además se generó y revisó visualmente un fixture local de 1280×720 / 30 FPS:
90/90 frames decodificables, un candidato sostenido, línea bottom-center y etiquetas
coherentes. Queda fuera de Git. Sanity CPU, 20 iteraciones iniciales y 100 medidas
por modo, una relación: renderer base **2,459 ms/frame** de media; base+overlay
**3,111 ms/frame**, incremento aproximado **0,652 ms/frame**. No es un benchmark
académico, ni inferencia, ni evaluación de densidad alta, ni garantía de tiempo real.
El encoder Windows emitió un aviso de OpenH264 en el primer backend probado;
OpenCV pudo usar el disponible y el resultado se abrió/decodificó completo. No se
descargaron codecs ni se alteró su configuración.

La revisión adversarial mantuvo un solo renderer, posiciones/distancias sin
recálculo y estado/episodios compartidos; no se añade framework de relaciones,
política de operadores ni capa persistente. La política de continuidad ya estaba
implementada: se vuelve explícita y se cubre, no se atribuye un algoritmo temporal
nuevo a esta campaña. Las pérdidas de tracking siguen rompiendo episodios y las
etiquetas pueden solaparse, especialmente en fuentes pequeñas/densas. Las demos
reales actuales siguen sin regla de pares habilitada; este cierre valida el flujo
positivo con fixture autorizado, no acredita una condición operacional real.

Modelos, pesos/hashes, confidence, NMS, ByteTrack, semántica/umbrales de reglas y
archivos de configuración, geometría B,
DB/contrato público y frontend permanecen intactos. No se tocaron holdouts, TEST2,
REAL_HOLDOUT_V2, Excel, arquitectura, main ni tags; no se entrenó ni calibró.

## 14. Decisión geométrica de proximidad — 25-10-2026

**Histórico intermedio B, sustituido por D en la sección 15.** Se conserva esta
comparación y su versión como registro; no describe la geometría productiva final.

Base: `da40795599459bfcfbf51a1e6304760868b978cd`, `dev` limpio y sincronizado.
Esta decisión sucede a la sección 13; no cambia retroactivamente sus mediciones
bottom-center ni los eventos/CSV/videos históricos. Se compararon fixtures antes
de modificar el cálculo productivo, sin inferencia, holdouts ni selección por eventos.

**Decisión: ADOPT_NEAREST_EQUIPMENT_GROUND_EDGE_GEOMETRY.** A mide entre centros
inferiores; B entre el centro inferior PERSON y el punto más cercano del segmento
inferior del equipo. C, solo diagnóstico, es la mínima separación entre contornos
rectangulares normalizados: contornos que se cruzan/tocan dan cero; en contención
estricta se mide la separación entre sus bordes, no se confunde con distancia
entre áreas (que sería cero). C no se incorpora al producto.

Fixtures de 1000×600; resultados en `norm`, seis decimales:

| Caso | A | B | C |
| --- | ---: | ---: | ---: |
| Persona a izquierda | 0.430000 | 0.180000 | 0.160000 |
| Persona a derecha | 0.330000 | 0.080000 | 0.060000 |
| Frente al centro | 0.183333 | 0.183333 | 0.016667 |
| Parcialmente frente | 0.263523 | 0.083333 | 0.000000 |
| Solapamiento por perspectiva | 0.265754 | 0.200000 | 0.000000 |
| Persona contenida en bbox | 0.087003 | 0.083333 | 0.050000 |
| Separación vertical | 0.500000 | 0.500000 | 0.166667 |
| Tamaños muy distintos | 0.371498 | 0.038873 | 0.010000 |
| Borde de imagen | 0.200000 | 0.010000 | 0.000000 |
| Mismo nivel inferior, dentro del segmento | 0.110000 | 0.000000 | 0.000000 |
| Varias personas, izquierda | 0.360000 | 0.110000 | 0.090000 |
| Varias personas, centro | 0.050000 | 0.000000 | 0.000000 |
| Varias personas, derecha | 0.340000 | 0.090000 | 0.070000 |

Se revisó una lámina A/B y se comprobó que los trece resultados B coinciden con la
función canónica. Los casos y coordenadas B están en `test_proximity_geometry.py`.
A añade separación horizontal hasta el centro aun cuando la persona está junto
al extremo del vehículo. B conserva la separación vertical, evita ese efecto y
es continua al cruzar los extremos del segmento (clamp, sin saltos discretos).
Si el segmento sigue cubriendo el anchor, ampliar su ancho no inventa distancia
horizontal. C depende de bordes superiores/laterales de la persona y colapsa a
cero en solapamientos por perspectiva, sin respetar necesariamente los apoyos.
La elección responde a la interpretación geométrica y visual, no a generar más eventos.

Definición canónica, para frame W×H y cajas xyxy:

```text
px = (person.x1 + person.x2) / 2; py = person.y2
fx = clamp(px, equipment.x1, equipment.x2); fy = equipment.y2
d = hypot((px - fx) / W, (py - fy) / H)
```

Versión: `person_bottom_center_to_equipment_ground_edge_v1`.
`person_to_equipment_ground_edge` acepta cajas, sin clase/modelo de equipo.
El analizador selecciona los roles configurados y conserva distancia, versión y
puntos; la regla los consume, el renderer los convierte a píxeles y el candidato
los transporta. No se recalcula la distancia en reglas, renderer ni Backend.
Las distancias descriptivas OP-37 entre objetos ajenos a esos roles siguen siendo
su observación genérica previa: no son una alternativa A seleccionable para esta
regla. La regla rechaza una medición de roles sin el contrato B esperado.
Se propagan los roles desde la configuración a los orquestadores, sin cambiar JSON
de perfiles ni hacer una generalización de MOBILE_EQUIPMENT.

`observations.proximity_geometry` añade versión, `person_anchor` y `equipment_target`
normalizados a eventos nuevos; el candidato transitorio contiene el mismo snapshot.
El Backend admite el snapshot completo o el payload histórico sin él, sin rellenar
campos retrospectivamente. Un retry que intenta añadir geometría a un evento ya
guardado entra en conflicto, no lo modifica. No se migran columnas/filas: los JSON
existentes soportan el dato opcional. CSV nuevos del analizador incluyen versión y
extremos; archivos históricos permanecen intactos.

**Umbrales sin retuning.** B≤A por construcción para estas cajas: conservar el
número de `max_distance` puede admitir más pares, iniciar antes o prolongar una
condición. Tampoco se asume equivalencia de episodios/duración entre A y B.
No se cambiaron max_distance, duraciones, versiones de reglas configuradas ni
perfiles. Esto **no acredita que los umbrales anteriores estén calibrados para B**;
cualquier recalibración será posterior, con datos de desarrollo y versión explícita.
Las demos siguen sin habilitar la regla de pares.

Limitaciones: el borde inferior de una bbox no es la huella física del vehículo;
oclusiones, perspectiva, altura o imprecisión de cajas pueden desplazarlo. B puede
dar cero si ambos puntos coinciden: no demuestra contacto ni ocupancia. No permite
distinguir operador/peatón, no suprime personas y no mide metros ni riesgo. No hay
evidencia de superioridad física/operacional sobre escenas reales ni calibración
de cámara. No se incorporó truck ni un selector A/B productivo.

Regresión final: **394 tests Motor: 392 PASS + 2 SKIP**, **123/123 Backend en
Docker/PostgreSQL**, **30/30 Frontend** sin cambios de interfaz. La suite Backend
incluye su Django check; migrations check confirmó que no hay cambios de esquema.
Ambos pip check y Compose config aprobaron. La base nativa no estaba disponible
en el entorno conocido: esta campaña usa PostgreSQL de QA aislado, no presenta
una suite nativa como aprobada ni modifica `.env`.

Las pruebas cubren anchor, clamp interior/ambos extremos, normalización y resize,
overlap/contención, cero, bordes, ancho/tamaños distintos, roles/IDs y orientación
invertida, rechazo de geometría sin versión y endpoints del renderer. Los fixtures
de límite de regla desplazan el bbox para que **el borde**, no el centro, quede
exactamente a 0,25; se preservan los umbrales y las assertions de igualdad/límite.
No se debilitan tests para admitir una distancia fuera del rango configurado.

E2E con percepción fixture y worker real: la distancia y los dos puntos/versiones
coinciden entre regla, recibo del renderer, candidato, JSON persistido e histórico.
El PNG decodificado coincide por hash de píxeles con el frame anotado; el MP4 se
verifica decodificando el resultado. Dos pares emiten una vez bajo el fixture
existente 0,25/1 s, sin reajuste. Una reproducción B adicional, 1000×600 / 30 FPS,
se abrió y decodificó 60/60 frames con una emisión sostenida; su encoder fue MSMF
tras el aviso OpenH264 ya conocido. Lámina comparativa, JSON y MP4 permanecen fuera
de Git. No es evaluación de percepción ni confirmación de incidentes reales.

Se conservaron modelos, pesos/hashes, confidence, NMS, ByteTrack, tolerancia temporal
numérica, reglas habilitadas, zonas, archivos de perfiles, holdouts, TEST2 y
REAL_HOLDOUT_V2. No hubo entrenamiento, tuning, acceso a Excel, cambios de arquitectura,
main o tags. Los recursos desechables de PostgreSQL de QA se retiran al finalizar.

## 15. Corrección final de segmentos inferiores — 25-10-2026

Base: `828b7fdff053d54bb5cdf83f1bc145454d38c12e`, `dev` limpio y sincronizado.
La instrucción humana final sustituye B (centro PERSON → borde equipo) por **D:
distancia mínima entre ambos segmentos inferiores**. No se usa distancia entre
contornos completos. Una función canónica `nearest_ground_edges` sustituye la
anterior; no se dejan A/B/C como alternativas productivas configurables.

Para PERSON `[px1,px2]` a altura `py=ymax` y equipo `[ex1,ex2]` a `ey=ymax`:

- Si `px2 < ex1`: puntos `(px2,py)` y `(ex1,ey)`.
- Si `ex2 < px1`: puntos `(px1,py)` y `(ex2,ey)`.
- En otro caso, `x=(max(px1,ex1)+min(px2,ex2))/2`: puntos `(x,py)` y `(x,ey)`.

`d=hypot((person_point.x-equipment_point.x)/W,
(person_point.y-equipment_point.y)/H)`, distancia normalizada en imagen, sin metros.
El punto medio del overlap resuelve de forma determinista la multiplicidad de
soluciones mínimas. La normalización por cada eje no cambia el mínimo horizontal.

Comparación de los mismos trece fixtures de 1000×600. A/B/C conservan los valores
históricos de la sección 14; C sigue siendo diagnóstico de **contornos completos**.
Los puntos D de esta tabla están en píxeles de la fuente, antes de rasterización:

| Caso | A | B | C | D | Punto PERSON D | Punto equipo D |
| --- | ---: | ---: | ---: | ---: | --- | --- |
| left | .430000 | .180000 | .160000 | .160000 | (140,450) | (300,450) |
| right | .330000 | .080000 | .060000 | .060000 | (860,450) | (800,450) |
| front_center | .183333 | .183333 | .016667 | .183333 | (550,560) | (550,450) |
| partial_front | .263523 | .083333 | .000000 | .083333 | (315,500) | (315,450) |
| perspective_overlap | .265754 | .200000 | .000000 | .200000 | (375,330) | (375,450) |
| contained | .087003 | .083333 | .050000 | .083333 | (525,400) | (525,450) |
| vertical | .500000 | .500000 | .166667 | .500000 | (550,150) | (550,450) |
| different_sizes | .371498 | .038873 | .010000 | .034801 | (270,430) | (280,450) |
| image_edge | .200000 | .010000 | .000000 | .000000 | (20,420) | (20,420) |
| same_bottom | .110000 | .000000 | .000000 | .000000 | (440,450) | (440,450) |
| multiple_left | .360000 | .110000 | .090000 | .090000 | (210,450) | (300,450) |
| multiple_center | .050000 | .000000 | .000000 | .000000 | (500,450) | (500,450) |
| multiple_right | .340000 | .090000 | .070000 | .070000 | (870,450) | (800,450) |

Versión final **`person_equipment_nearest_ground_edges_v1`**. El analizador,
regla, renderer y snapshot usan los mismos puntos y distancia. No se modifican
tracking, lifecycle de episodios, selección visual ni transporte. `person_anchor`
mantiene su nombre para conservar infraestructura; bajo D significa punto del
segmento PERSON seleccionado, no centro. La línea usa sus coordenadas con la
conversión raster existente y la etiqueta usa la distancia observada.

La API acepta D, B histórica o registros antiguos sin snapshot; no añade ni
convierte metadata histórica. También puede serializarse un candidato histórico
B sin cambiar puntos/versión; el replay de outbox conserva el JSON original.
Un retry B→D con la misma identidad devuelve 409, no modifica el evento. D debe
pertenecer a una ejecución nueva. No se migran filas/columnas.

Pruebas Motor: **398 descubiertas, 396 PASS + 2 SKIP** opt-in. Cubren esquinas,
overlap parcial/determinismo, contención, niveles inferiores iguales/distintos,
touching, normalización/resize, simetría de segmentos, roles/IDs, endpoints del
renderer, snapshot y preservación B. Las pruebas de límite mantienen 0,25; se
colocan los segmentos de fixture exactamente a esa separación sin cambiar umbrales.
Backend completo con PostgreSQL aislado: **124/124**, incluido E2E con detecciones
fixture y worker real. Para el primer par solapado se verifican puntos normalizados
(.2875,.7) en ambos segmentos y distancia cero; el otro par conserva gap .1.
Distancia/puntos/versiones coinciden con el evento, y el PNG decodificado conserva
el hash de píxeles del renderer. MP4 completo verificado por el worker. No se
declara una nueva evaluación de modelos o una suite nativa contra DB no disponible.

Se generó/revisó una comparación visual B/D con el mismo fixture, sin reescribir
los artefactos B originales. Video D adicional: 1000×600, 30 FPS, 60/60 frames
decodificables, una emisión, encoder MSMF; máximo 0,25 y duración 1 s del fixture
existente. JSON, PNG y MP4 quedan locales fuera de Git, sin peso/dataset nuevo.

**Umbrales intactos pero no equivalentes:** D≤B≤A para estos segmentos; el mismo
máximo puede cambiar pertenencia a la condición e inicio/duración del episodio.
No se retocan `max_distance`, duraciones, reglas habilitadas ni perfiles; no se
afirma que estén calibrados para D. La recalibración requiere otra campaña con
material de desarrollo. Cero solo significa coincidencia según esta geometría 2D:
no demuestra contacto físico, operador, ocupación, colisión ni Near Miss.
Se conservan las limitaciones de bbox, perspectiva, oclusión y falta de calibración.
No hubo entrenamiento, acceso a holdouts, TEST2 o REAL_HOLDOUT_V2, cambios de
modelos/pesos, confidence/NMS, ByteTrack, frontend, main, tags, Excel o arquitectura.

## 16. Continuidad observada y ocupancia — 25-10-2026

Base: `feecd73e26f3f9e8764a44983e7984ded25fefbd`, `dev` limpio y sincronizado.
Resultado: **TRACKING_CONTINUITY_CHARACTERIZED** y
**OCCUPANT_ASSOCIATION_DESIGN_ONLY**. Se añaden pruebas y esta evidencia; no se
cambia código productivo, geometría D, umbrales, perfiles ni reglas habilitadas.

### Interrupciones de observación

Fixtures deterministas con analizador y reglas reales: 10/30/60 FPS, pérdidas de
1/3 frames, PERSON o FORKLIFT ausente, fluctuación de detección, desaparición,
recuperación con el mismo ID, cambio de ID sin intervalo vacío y salida observada
del umbral. La condición sostenida usa el máximo 0,25 y mínimo 1 s del fixture
de integración existente; no son una calibración operacional nueva. El reporte
local conserva 42 combinaciones, sus observaciones por frame y emisiones.

| Entrada conocida del fixture | Comportamiento actual |
| --- | --- |
| Pareja continua | Una emisión al alcanzar 1 s; las observaciones siguientes no duplican el candidato. |
| TRACK LOSS / DETECTION GAP / OBJECT DISAPPEARANCE | La pareja queda sin observación, se cierra el episodio y no se acredita duración durante el hueco. |
| Recuperación del mismo ID | Nuevo episodio desde duración cero; si vuelve a cumplir 1 s, emite con otra `episode_key`. |
| TRACK ID CHANGE | No se une por proximidad de cajas; la nueva identidad inicia otro episodio. |
| RULE EXIT observado | `outside_distance`; la reentrada inicia legítimamente un episodio nuevo. |
| Dos PERSON cercanas, pérdida de una | La otra conserva su episodio y no vuelve a emitir; no se mezclan identidades. |

Para FPS `f`, el fixture emite inicialmente en `f`, interrumpe en `f+3`, recupera
en `r=f+3+g` y vuelve a emitir en `r+f`. La duración reinicia en cero en `r`:
se pierde la acumulación previa, no solo los `g` frames. Un hueco de 1/3 frames
equivale a 100/300 ms a 10 FPS, 33,33/100 ms a 30 FPS y 16,67/50 ms a 60 FPS.
ByteTrack real, sin YOLO, recupera el mismo ID tras 1/3 actualizaciones vacías;
no emite un track observado durante ellas. Tras 35 actualizaciones vacías el ID
anterior expira y la nueva detección requiere reconfirmación, sin resucitarlo.
El buffer vigente de 30 frames no representa una duración universal entre FPS.

Se revisó únicamente el JSONL ya existente de la demo de desarrollo A, sin nueva
inferencia: 277 frames, 644 observaciones PERSON / 8 IDs y 277 FORKLIFT / 1 ID.
SHA-256 del JSONL: `fbc4302a6cc48183e855b495e589fba2a2fc40db7e55c278b118998602898b4d`.
Huecos internos entre primera y última observación del mismo ID:

| PERSON ID | Frames ausentes (inclusivos) | Frames | Duración a 30 FPS |
| --- | --- | ---: | ---: |
| 4 | 60 | 1 | 0,0333 s |
| 4 | 62–73 | 12 | 0,4000 s |
| 5 | 73 | 1 | 0,0333 s |
| 5 | 212 | 1 | 0,0333 s |

Son 15 observaciones-ID ausentes en 14 frames distintos, con recuperación del
mismo ID; FORKLIFT no tiene huecos internos. No se atribuyen a oclusión, salida
real o ID switch sin anotación física. El cache corresponde a `zone_dwell` y
respalda únicamente esta caracterización de tracking, no eventos nuevos de
proximidad ni una evaluación de D. Sus puntos históricos no se reinterpretan.

**Sin gracia ni reconciliación automática.** La fragmentación es reproducible,
pero observaciones idénticas pueden ocultar permanencia o una salida real durante
el hueco. Unir por posición también puede mezclar personas cercanas. Dos emisiones
tras recuperar observación son episodios observados diferentes, no duplicados de
transporte; la idempotencia existente se conserva. El mínimo paso futuro sería
registrar una relación diagnóstica de hueco con el mismo ID, sin sumar tiempo ni
fusionar eventos, y contrastarla con anotaciones de desarrollo antes de autorizar
cualquier tolerancia. No se añade ahora un token, umbral o framework innecesario.

### Ocupancia y supresión adversarial

Los fixtures cubren cabina aparente, peatón delante, costado con overlap, detrás
por perspectiva, ocupante parcial, dos personas, ocupante más peatón y PERSON
contenida en F1 próxima a F2. Los roles físicos son hipótesis del fixture, no
ground truth de personas reales. Se miden contención, posición relativa, overlap,
distancia D y contención en una cabina anotada **solo para ese fixture**. No hay
ROI universal, ni umbral productivo nuevo.

Ocupante aparente y peatón proyectado delante/detrás tienen exactamente las mismas
observaciones: contención 1, cabina 1, posición relativa (0,68125; 0,58333) y
distancia D 0,20833. El peatón lateral tiene contención 0,4 y distancia cero; el
ocupante parcial tiene contención 1 pero distancia 0,28333. Ninguna de esas
mediciones confirma un rol. Se comparan seis observaciones estáticas y seis con
desplazamiento compartido (2,1) por muestra: misma dirección, velocidad relativa
cero, relación estable y persistencia idéntica también admiten un peatón que
acompaña al equipo. Esa ventana sintética no establece una duración suficiente
para inferir ocupancia. Un cambio de ID tras un hueco tampoco prueba continuidad
física ni permite heredar un rol.

**¿Puede esta heurística ocultar una interacción realmente relevante? Sí.** La
proyección de un peatón puede ser indistinguible del operador, incluso combinando
las señales disponibles. Por eso no se introduce `LIKELY_OCCUPANT`, supresión,
reclasificación ni etiqueta visual. La PERSON y todos sus pares permanecen.
Una solución futura necesitaría validación independiente de ocupancia, geometría
de cabina por vista/orientación y criterio humano de falsos descartes; debería
ser temporal, reversible, trazable y específica P↔F, nunca global sobre PERSON.
No demostraría identidad, cargo, autorización, culpabilidad ni ausencia de riesgo.

### Integración y regresión

E2E adicional: percepción fixture → ByteTrack → D → regla → candidato → HTTP /
PostgreSQL → PNG → consulta histórica y MP4. La asociación se omite deliberadamente
por la decisión DESIGN_ONLY, no se simula una implementación. Con PERSON contenida
en F1 y próxima a F2 se conservan ambos pares: dos candidatos/eventos, un ID PERSON,
dos IDs FORKLIFT, puntos/versiones de renderer iguales al evento y ambas evidencias
accesibles. La suite también conserva la comprobación existente de hash de píxeles
renderer/PNG, video decodificable, reintentos e idempotencia. No se añade UI.

- Motor: **414 descubiertas, 412 PASS y 2 SKIP** de modelos reales opt-in.
- Backend completo: **125/125**, incluidos workers reales con percepción fixture,
  usando PostgreSQL aislado en Docker; no se afirma una ejecución nativa con DB
  local no disponible. Django check sin incidencias, sin migraciones pendientes.
- Frontend intacto: **30/30**, lint, typecheck y build aprobados.
- `pip check`: ambos entornos nativos sin incompatibilidades.
- Compose CPU/GPU: configuración válida; `git diff --check` aprobado.

Reportes generados permanecen fuera de Git. No hubo inferencia nueva, entrenamiento,
tuning, lectura de holdouts, TEST2 o REAL_HOLDOUT_V2. Modelos/checkpoints, confidence,
NMS, ByteTrack, geometría `person_equipment_nearest_ground_edges_v1`, umbrales,
perfiles, transporte/persistencia productivos, frontend, Excel, main y tags intactos.

## 17. Selección de percepción y extensión de equipos — 25-10-2026

Base `cac92912fe57151f4b4e9090e33aa0448974827b`, `dev` limpio/sincronizado.
Campaña **PERSON_MODEL_SELECTION_DEVELOPMENT**; resultados etiquetados
**DEVELOPMENT_SELECTION_METRICS**, no validación final ni ejecución de
PERSON_EVALUATION_PROTOCOL_V1. Producción permanece en YOLO11n COCO PERSON y
FORKLIFT specialist v2.

Se reutilizan 273 imágenes revisadas por humanos: 225 KEREMBERKE y 48 TEST3,
307 cajas PERSON, 152 imágenes positivas y 121 negativos verificados. Se verifican
hashes de imágenes/etiquetas y se fija el manifiesto antes de inferencia. Hay
preanotación previa, procedencia industrial débil y un solo video TEST3 de origen
desconocido: sirven para selección de desarrollo, no independencia o generalización.
No se inventan etiquetas de oclusión/operador/dificultad tras observar resultados.
No se accede a PERSON_FINAL_HOLDOUT_V2, TEST2, REAL_HOLDOUT_V2 u otro test final.

Comparación común: COCO n/s/m/l, 640, confidence 0,10, NMS 0,70, batch 1, FP32,
CUDA:0; filtro PERSON y matching existente uno-a-uno por confianza, IoU≥0,50.
Se reutiliza el adaptador productivo, que predice COCO y filtra después por clase.
Cada checkpoint verifica `model.names`: person=0 y truck=7, sin asumir esos IDs.
n se reutilizó con su SHA conocido; s/m/l se descargaron mediante Ultralytics
desde `ultralytics/assets`, release v8.4.0. No se instalaron dependencias nuevas.
x queda fuera del estudio acotado; no se afirma que no quepa en VRAM.

| Modelo | Parámetros antes de fusionar | Bytes del checkpoint | SHA-256 |
| --- | ---: | ---: | --- |
| yolo11n.pt | 2624080 | 5613764 | `0ebbc80d4a7680d14987a577cd21342b65ecfd94632bd9a8da63ae6417644ee1` |
| yolo11s.pt | 9458752 | 19313732 | `85a76fe86dd8afe384648546b56a7a78580c7cb7b404fc595f97969322d502d5` |
| yolo11m.pt | 20114688 | 40684120 | `d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95` |
| yolo11l.pt | 25372160 | 51387343 | `9ebd0e09d59811db4b1d61e2bc6730649608b1ac47f8dd01e2da6bca7c20023f` |

RTX 3070 8 GiB, Ryzen 5 5500, Windows 10 Pro x64, RAM visible ≈31,9 GiB,
driver 616.92, PyTorch 2.14.0+cu130 y Ultralytics 8.4.146. Tres repeticiones,
20 inferencias iniciales de warm-up; reloj perf_counter_ns y sincronización CUDA
antes/después. Calidad calculada una vez por imagen; los otros pases miden tiempo.
Inferencia excluye lectura. Pipeline serial: decode → PERSON + FORKLIFT →
ByteTrack → analizador/reglas → renderer, sin escritura, HTTP, MJPEG ni persistencia.
Trackers/historiales/reglas se reinician por repetición; se procesan los 20 frames
iniciales pero se excluyen del tiempo. A/B/C tienen 277/300/418 frames; son 2805
frames medidos por modelo. FPS global = frames / suma de tiempos, nunca promedio
de FPS instantáneos. p95 usa interpolación lineal; desviación estándar muestral.

| COCO | TP / FP / FN | P | R | F1 | Predicciones | Inferencia FPS / ms medios | Pipeline dual FPS | Pico dual asignado / reservado MiB |
| --- | --- | ---: | ---: | ---: | ---: | --- | ---: | --- |
| n | 230 / 258 / 77 | 0,471 | 0,749 | 0,579 | 488 | 46,118 / 21,684 | 15,275 | 66,3 / 100 |
| s | 244 / 222 / 63 | 0,524 | 0,795 | 0,631 | 466 | 42,845 / 23,340 | 15,452 | 103,3 / 144 |
| m | 254 / 167 / 53 | 0,603 | 0,827 | 0,698 | 421 | 28,809 / 34,711 | 11,404 | 166,7 / 324 |
| l | 255 / 143 / 52 | 0,641 | 0,831 | 0,723 | 398 | 18,898 / 52,915 | 12,176 | 195,1 / 362 |

VRAM corresponde al allocator PyTorch, no a memoria global de GPU, contexto CUDA
completo ni presupuesto para procesos concurrentes. No hubo OOM; no se instrumenta
utilización GPU. El orden n/s/m/l no está contrabalanceado. La inversión de FPS
pipeline entre m/l **no demuestra que l sea intrínsecamente más rápido**: también
varía la etapa del especialista idéntico (por ejemplo B, 26,2 frente a 20,2 ms en
la primera repetición). Se conservan las observaciones, sin corregirlas a mano.
Ningún resultado acredita 30 FPS sostenidos o tiempo real universal. La cifra de
carga + 20 warm-ups (5,17/0,70/0,94/1,61 s) no es ahorro demostrado de residencia.

| COCO | IDs PERSON A/B/C | Huecos internos A: episodios / observaciones-ID ausentes | Cobertura PERSON C | Eventos C: dwell / proximidad |
| --- | --- | --- | --- | --- |
| n | 8 / 1 / 2 | 4 / 15 | 360/418 | 2 / 2 |
| s | 3 / 1 / 1 | 3 / 16 | 418/418 | 1 / 1 |
| m | 4 / 1 / 1 | 0 / 0 | 418/418 | 1 / 1 |
| l | 3 / 1 / 1 | 0 / 0 | 413/418 | 2 / 2 |

B mantiene PERSON en 300/300 con un ID; FORKLIFT conserva un ID y observación en
todos los frames de cada demo. Las tres repeticiones repiten conteos de detección,
tracking y eventos. No hay IDs PERSON duplicados dentro del mismo frame. Son
descriptores, no métricas MOT ni ID switches confirmados. En l/C, ausencias en 123
y 128–131 reinician la duración; proximidad vuelve a emitir en 162. No se añade
gracia. Menos IDs no prueba por sí solo mejor asociación física.

Se mantienen zonas/dwell productivos de A/B/C. Para observar proximidad se añade
**solo offline** TEST_DATA_PAIR con 0,25 norm y 1 s, copiados del fixture existente,
sin calibración ni activación productiva. Los pares evaluados A/B/C son
644/300/360 (n), 644/300/418 (s), 650/300/418 (m), 654/300/413 (l). Más eventos no
es criterio de selección. FP sobre negativos verificados: n=27, s=37, m=15, l=13;
la mejora agregada de s no es uniforme.

**PERSON_OPERATIONAL_RECOMMENDATION: RECOMMEND_YOLO11M**, propuesta para análisis
diferido de Etapa 4, sujeta a aprobación y sin cambiar producción. Frente a n,
F1 mejora 0,119, FP bajan 91 y FN bajan 24; en A/C no presenta huecos internos
en los registros medidos. Frente a s, aporta calidad a costo de ≈26 % de FPS dual.
l gana un TP frente a m y reduce otros 24 FP, pero su inferencia aislada cuesta
≈52 % más y muestra cinco frames sin PERSON en C. No se elige simplemente el
mayor F1; s queda como alternativa de eficiencia, no una mejora universal.

### Evolución compatible de equipos: diseño, no implementación

- Detection/Track e identidad `(class_name, track_id)` son reutilizables. Canales y
  PerceptionFrame fijan person/forklift; reglas/InteractionIdentity, renderer,
  snapshots, validadores, constraint de pares, API y UI aún nombran forklift.
- Frontera pequeña propuesta: una inferencia COCO → separar person/truck →
  trackers independientes por clase; segundo forward del especialista forklift.
  Mapear `perception_class`, rol PERSON/MOBILE_EQUIPMENT, subtipo y SHA/source_model
  sin cambiar la clase observada ni perder namespace. No crear un framework.
- Conservar person_forklift_proximity, snapshots y replay originales. Una futura
  person_mobile_equipment_proximity tendría `equipment_types=[forklift,truck]`,
  configuración por subtipo y nuevo contrato discriminado, validación/constraint,
  identidad de análisis con todos los modelos y revisión de UI; sin migrar historia.
- COCO truck puede ser un falso rótulo de forklift, ya documentado en OP-34. No
  inventar equivalencias ni suprimir por overlap entre ramas: también podría ocultar
  dos equipos reales. Faltan escenas de desarrollo de camiones y conflictos entre
  modelos. `TRUCK_INTEGRATION_READY_BUT_NOT_EVALUATED` describe solo disponibilidad
  de clase COCO; **no** un pipeline truck listo ni métricas P/R válidas.
- Complejidad media en Motor, media/alta end-to-end. La geometría D sigue siendo
  distancia normalizada en imagen; no define metros ni distancias seguras universales.
- Cada análisis actual abre un proceso y carga ambos modelos una vez, no por frame.
  ResidentDetectors histórico es un cache experimental, no integrado. Un futuro
  worker serial podría retener modelos por SHA/device/precisión, con estados
  temporales nuevos, cancelación y liberación acotada; no se porta a ciegas.

Decisión: **MOBILE_EQUIPMENT_EXTENSION_NEEDS_MORE_EVIDENCE**. YOLOE/YOLO-World
quedan en [revisión documental](https://docs.ultralytics.com/models/yoloe/), sin
instalar ni integrar; prompts no resuelven identidad, ocupancia o seguridad.
La [familia YOLO11](https://docs.ultralytics.com/models/yolo11/) aporta los
checkpoints COCO estudiados, sin extrapolar su benchmark publicado a esta GPU.

Detalle local en `Operix-experiments/perception-architecture-study-2026-10-25/`:
manifiesto previo, resultados aceptados `run-04`, predicciones, tiempos/agregados,
comparación CSV, recibos de integridad, gráfico y láminas B/C en frame 150 fijado
antes de inferencia. Tres preflights se conservan como abortados por errores del
tooling (borde/serialización), sin cambiar la muestra o parámetros; no sustentan
las tablas. Pesos, imágenes, JSON experimentales y capturas quedan fuera de Git.
Tooling nuevo: 7/7 pruebas; suite Motor **421 descubiertas, 419 PASS y 2 SKIP**
opt-in; pip check y diff check aprobados. Solo se versionan tooling, tests y esta
síntesis. No hubo entrenamiento, sweeps, acceso a holdouts, cambios de producción,
ByteTrack, reglas, geometría, Backend, Frontend, Excel, main, tags o arquitectura v1.0.

## 18. PERSON operacional YOLO11m — 26-10-2026

Decisión humana aprobada sobre base `43ffd7cbf8da4310d76eaf1c66f71a7f5600f225`:
**YOLO11M_COCO_PERSON_OPERATIONAL**, para análisis diferido. Se verificó el archivo
externo `yolo11m.pt`, SHA-256
`d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95`.
No se incorpora a Git ni a la imagen Docker. El Backend exige ese hash al worker;
el montaje Docker continúa siendo un archivo individual read-only.

Se mantiene 640 / confidence 0,10 / NMS 0,70, filtro person, FP32 y CUDA:0.
Batch 1 queda explícito en el lanzamiento web y como default del worker (antes 4).
La comparación de desarrollo de la sección 17 sustenta el trade-off: frente a n,
m aporta +24 TP, −91 FP, −24 FN y +0,119 F1, con inferencia aislada de 34,711 ms
frente a 21,684 ms. l alcanza F1 0,723 frente a 0,698, pero solo +1 TP, 52,915 ms
aislados y cinco frames sin PERSON en C. No se afirma superioridad universal de m.
**Esta selección no constituye validación independiente final.** El holdout ya
observado no se reutiliza para validar m.

Historial conservado, sin sustituir resultados ni identidades:
PRE_EVALUATION_PRIMARY_PERSON → YOLO11N_COCO_PERSON (primera configuración
operacional post-evaluación) → YOLO11M_COCO_PERSON (selección de desarrollo).
PERSON v2 continúa diferido. FORKLIFT specialist v2, ByteTrack, parámetros de
reglas, perfiles y geometría `person_equipment_nearest_ground_edges_v1` no cambian.

Regresión controlada con CUDA real, demo C autorizada, PostgreSQL de pruebas y
medios externos: **418/418 frames**, PERSON observado en 418/418 con un ID;
FORKLIFT conserva un ID. Se valida resultado H.264 1920×1080, 30 FPS, 418 frames,
overlay, candidatos, HTTP, persistencia, PNG, detalle e historial. Se guardan dos
eventos: zone_dwell en frame 60 y person_forklift_proximity en frame 30. Proximidad
usa **solo en el fixture local** TEST_DATA_PAIR, 0,25 norm / 1 s, iguales a la
regresión anterior; no se activa ni calibra una regla productiva.

Snapshots y source.perception registran YOLO11M_COCO_PERSON, SHA y 640/0,10/0,70;
FORKLIFT conserva su identidad/hash. No se modifican eventos históricos. Sanity
local: 34,926 s de pared desde START hasta verificar salidas, RTX 3070, sin OOM;
pico asignado PyTorch 168,7 MiB, no memoria total de GPU. No es un benchmark
comparable a OP-43 ni al estudio; no acredita 30 FPS sostenidos.

Compose CPU/GPU config aprobado; imagen QA construida sin pesos, smoke H.264
aprobado y un frame demo procesado dentro de Docker con ambos checkpoints externos
read-only. Se comprueban hash, identidad m, clase person=0, CUDA:0 y FP32. No se
repite un E2E completo dentro de Docker. El E2E nativo usa el worker productivo
con un observador local: el primer recibo consultó el modelo base CPU en lugar
del predictor efectivo; se corrigió solo ese observador y la repetición aprobó.

Motor: **423 descubiertas, 421 aprobadas y 2 omitidas** opt-in; Backend **125/125**;
E2E CUDA real **1/1**. Django check, migration check (sin cambios), pip check de
ambos entornos, check_environment --require-cuda y diff check aprobados. Frontend
intacto; no requiere repetir lint/typecheck/build. Recibos/scripts/medios locales
en `Operix-experiments/person-m-operational-2026-10-26/`, fuera de Git.

No se accede a holdouts finales, TEST2 o REAL_HOLDOUT_V2; sin entrenamiento,
sweeps ni tuning. MOBILE_EQUIPMENT_EXTENSION_NEEDS_MORE_EVIDENCE y
TRUCK_INTEGRATION_READY_BUT_NOT_EVALUATED conservan el alcance de la sección 17.

## 19. Checkpoint pre-v0.2.0 — 26-10-2026

Base `f4652f609beb1121bb6d8a0d2425f1eba28bc0fc`, rama dev, árbol limpio y
0/0 después de fetch. Se inspeccionan código, tests, historial, documentación y
assets versionados; se ejecutan cuatro reproducciones pequeñas sin modelos ni
DB persistente. No se repiten suites completas, browser, builds ni inferencia:
esta campaña define el gate final. No se abren holdouts, TEST2, Excel ni archivos
crudos de evaluación. La prioridad original no se cambia retrospectivamente.

### Reconciliación de los 25 hallazgos

| ID / prioridad | Estado actual | Evidencia y alcance |
| --- | --- | --- |
| F01 / P0 | CLOSED | Decisión humana posterior: n y luego m operacional, gates/snapshots actualizados en `e11f6ea`; regresión CUDA y límites en sección 18. Cierra la decisión de ingeniería, no demuestra validación final de percepción. |
| F02 / P0 | OPEN | Validación externa/contextual experta y operacional final realista aún pendientes. No bloquea v0.2.0 como MVP acotado; sí v1.0.0/cierre académico final. |
| F03 / P1 | CLOSED | `37a7024`, sessions: reserva hasta terminar proceso, cierre irreversible y pertenencia al registro; tests DELETE/START/referencia retirada. |
| F04 / P1 | CLOSED | Mismo hardening: expiración bajo exclusión, generación de timer y watcher; tests timer anterior frente a nuevo START. |
| F05 / P1 | CLOSED | `684f9f9`, inspect_recorded_video y worker: prelectura, segunda lectura y verificación de salida completa; tests EOF/conteo/error. Rechazo conservador no prueba detectar toda corrupción previa. |
| F06 / P1 | CLOSED | Contrato CFR explícito, timestamps observados, rechazo de irregularidad detectable y warning NOMINAL_FPS_UNVERIFIED_CFR cuando el backend no aporta reloj. No se promete soporte VFR universal. |
| F07 / P1 | CLOSED | `c3a8e1c`: desmontar ya no envía DELETE; referencia de sesión recuperable en la misma pestaña. `cac9291` añade flujo browser con navegación/recuperación. |
| F08 / P1 | CLOSED | Cierre posterior en sección 20: applyZone reutiliza generación y protege éxito/error/finally. Tests de A/B fuera de orden, contexto invalidado y PUT retrasado en browser. |
| F09 / P1 | CLOSED | Cierre posterior en sección 20: ObjectIdentity canónica para selección/resaltado. Regresión PERSON 1/FORKLIFT 1, cajas, casos legacy y CLI con PNG/endpoint correctos. |
| F10 / P1 | CLOSED | `cac9291`, tests/browser/analysis-flow.test.mjs: sesión, navegación, respuesta tardía de poll, MP4/seek, teclado, errores, historial/PNG y 18 combinaciones ruta/viewport. API fixture, no inferencia ni persistencia real. No certifica todos los intercalados posibles. |
| F11 / P1 | DEFERRED_BY_DECISION | OCCUPANT_ASSOCIATION_DESIGN_ONLY, sección 16 y tests adversariales; containment/movimiento no justifican suprimir PERSON. Limitación semántica explícita, sin filtro de ocupantes implementado. |
| F12 / P1 | CLOSED | TRACKING_CONTINUITY_CHARACTERIZED, `44d62b9`/`44c341d`: pérdidas, recuperación, cambio de IDs, 10/30/60 FPS y ByteTrack. Se cierra caracterización/decisión; fragmentación y ausencia de GT MOT permanecen. |
| F13 / P1 | CLOSED | Cierre posterior en sección 20: números finitos/representables, dominio de distancia [0,sqrt(2)] y HTTP 400 para extremos; validación nativa previa a evaluación. |
| F14 / P1 | CLOSED | Editor permite insertar X/Y, cerrar y aplicar sin puntero; código, tests geométricos y flujo browser versionado. No implica certificación WCAG completa. |
| F15 / P2 | OPEN | validate_png acepta un chunk crítico ABCD desconocido con CRC válido; reproducción actual. Tests existentes de scanlines/Adam7 no cubren este caso. |
| F16 / P2 | OPEN | append no valida el final previo del journal. Reproducción: cola truncada → enqueue con HTTP fallido → replay: 0 recuperados, 1 registro inválido. No declara saved falsamente, pero pierde recuperabilidad automática de esa entrada. |
| F17 / P2 | OPEN | listEvents usa fetch sin deadline; detalle aborta al desmontar, pero tampoco fija plazo. La petición pendiente indefinida sigue posible. |
| F18 / P2 | OPEN | Filtros locales de EventsTable y retorno fijo /events: período/tipo no viajan en URL y se pierden al volver del detalle. |
| F19 / P2 | CLOSED | Sección 21: demo actual real, cuatro capturas production, PoC rotulado histórico, README y notas candidatas actualizados; surface brief original marcado como histórico. Gate/tag aún pendientes. |
| F20 / P2 | OPEN | Workspace/CSS grandes y configuración repartida entre sesión/worker; no se hizo refactor productivo. Deuda de mantenimiento, sin fallo adicional demostrado por tamaño. |
| F21 / DEFER | DEFERRED_BY_DECISION | API local AllowAny, login/roles demostrativos; IAM empresarial fuera del MVP. Exposición pública de la API requeriría otra decisión. |
| F22 / DEFER | DEFERRED_BY_DECISION | API/worker local y arquitectura actual; sin requisito nuevo de broker, microservicios o cloud. |
| F23 / DEFER | DEFERRED_BY_DECISION | PERSON v2/ReID/nuevos trackers diferidos. La promoción m resuelve la decisión operacional, no obliga a entrenar. |
| F24 / DEFER | DEFERRED_BY_DECISION | Registro RAM no recuperable tras reinicio; eventos/PNG y journal independientes. Recuperación al navegar no equivale a persistencia de sesiones. |
| F25 / DEFER | DEFERRED_BY_DECISION | Lista completa y carga acotada documentadas; paginación solo ante alcance/volumen que la exija. |

Balance actualizado tras sección 21: 13 CLOSED, 6 OPEN, 0 PARTIALLY_CLOSED, 6 DEFERRED_BY_DECISION y
0 NO_LONGER_APPLICABLE. Un test de happy path no cierra un caso adversarial ausente.

### Demo y assets: estado de presentación

Inventario versionado: 3 MP4, 7 PNG, 4 PDF, 1 SVG; ningún GIF ni screenshot de UI
actual versionado. Los tres MP4 coinciden con SHA-256 del NOTICE. Se conservan
todos los históricos. No se recaptura ni se vuelve a reproducir attachments aquí.

| Visual / referencia | Clasificación | Acción posterior |
| --- | --- | --- |
| forklift_human_nearmiss_ceiling00.mp4 y warehouse_fire_ceiling04.mp4 | CURRENT como entradas sintéticas reutilizables; origen histórico OP-34/35 | Mantener atribución y no confundir entrada con resultado del modelo actual. |
| warehouse_fire_ceiling04_operix_annotated.mp4, OP-60/61 | HISTORICAL_POC | Mantener sus cifras y hash; no presentarlo como salida m/dual/reglas/UI actual. |
| Player «Resultado de Operix» del README principal | OUTDATED_CURRENT_REFERENCE | En preparación del release, rotular explícitamente PoC histórico y añadir recorrido actual autorizado. Los enlaces a OP-61 contextualizan, pero el título no distingue versión. |
| Otros dos attachments del README | CURRENT como referencias a entradas sintéticas | Se confirma que hay tres URLs; no se recertifica disponibilidad/reproducción remota. |
| Seis diagramas, exportación IcePanel y cinco ADR | CURRENT como diseño v1.0 cerrado | 11 artefactos conceptuales disponibles, con exportaciones duplicadas intencionales; no describen por sí solos implementación completa. |
| Logo PNG e icono SVG | CURRENT | Branding, no evidencia experimental. |
| UI_REFRESH / documentación y clips OP-33/34/35/43/60/61 | HISTORICAL_POC en sus resultados/visuales | Conservar fechas; no extrapolar performance ni cobertura al pipeline actual. |
| README principal/Motor/Backend/Frontend/Docker | CURRENT en instrucciones funcionales | Frontend documenta recuperación/teclado/browser; modelos n y CURRENT permanecen como historia. Falta demo visual nueva/notas. |
| Surface brief Impeccable: glass/blur | OUTDATED_CURRENT_REFERENCE | Alinear documentación normativa con DESIGN/producto en preparación visual; no rediseñar UI por ese texto. |

No se detectan destinos de archivo ausentes en enlaces Markdown relativos
examinados; no se certifican todas las anclas/URLs externas. Escaneo textual
versionado sin patrones de rutas personales/tokens habituales/claves privadas;
0 tracked que coincidan con ignore. No es una auditoría completa del historial.

### Decisión del checkpoint previo (superada por sección 20)

**BLOCKED_BY_CRITICAL_ISSUES** para dar por cerrado el checkpoint técnico previo
al release. No hay un P0 runtime nuevo ni fallo demostrado de la pasada web CUDA.
Los bloqueos son los P1 reproducidos aún vigentes: **F09**, evidencia del replay
multiclase documentado como disponible, y **F13**, overflow no controlado de la
API de pares. No se corrigen dentro de esta auditoría ni se debilitan los gates.
La preparación de capturas/notas puede planificarse, pero no autoriza sincronizar
main, publicar tag ni afirmar regresión final aprobada.

F08 requiere completar/revisar la protección de PUT tardío y su test antes del
gate browser. F15/F16/F17/F18/F20 se conservan como deuda abierta; el caso F16 no
debe prometerse como recuperación automática soportada. F19 requiere material
actual/rotulación antes de anunciar el release. No se elevan estos P2 a P0.
F02, ocupancia y maquinaria móvil no bloquean el MVP integrado v0.2.0 con sus
límites explícitos; sí sigue pendiente la aceptación final académica/operacional.

### Gate final requerido antes de tag (definido, no reejecutado aquí)

| Bloque | Ejecución / comprobación exacta | Aceptación |
| --- | --- | --- |
| Base e integridad | dev/origin/dev 0/0, árbol limpio, referencias main/tag guardadas; Get-FileHash del m y FORKLIFT externos | m `d5ffc1a674953a08e11a8d21e022781b1b23a19b730afc309290bd9fb5305b95` y FORKLIFT `1465105ea80737ddc65d72e97d6dc24fc253995a98d6d4eea9b377fe3a8edce6`; un checkpoint distinto falla antes de cargar. |
| Motor | Python del Motor: `python -B -m unittest discover -s engine/tests` desde raíz | Ningún fallo; registrar descubiertas/PASS/SKIP por separado. Última base: 423/421/2; nuevos tests de correcciones incrementarán el total. |
| Backend | Desde backend, entorno local cargado: `.venv/Scripts/python.exe -B manage.py test --noinput` | PostgreSQL test aislado, ninguna escritura a eventos históricos; sin fallos. Última suite: 125/125. Incluir F13 con input enorme → 400, nunca excepción. |
| Django/migraciones | `manage.py check`, `makemigrations --check --dry-run`, `migrate --check` | Sin incidencias ni drift/migraciones inesperadas. |
| Dependencias | `python -m pip check` en ambos entornos Python | Sin incompatibilidades; sin cambiar locks por conveniencia. |
| CUDA nativo | Python Motor: `engine/scripts/check_environment.py --require-cuda` | CPU/OpenCV/CUDA operativos, RTX 3070, versiones registradas. |
| Frontend | Node 24.2.0/pnpm 11.28.2: `pnpm test`, `pnpm lint`, `pnpm typecheck`, `pnpm build` | Todos aprobados sobre el candidato definitivo; no atribuir PASS de esta auditoría. |
| Formato | `pnpm format:check`; si reaparece CRLF global, distinguirlo del cambio y comprobar Prettier estricto en archivos tocados | Registrar resultado real; no declarar PASS ni normalizar masivamente sin autorización. |
| Browser | API fixture explícita: `pnpm fixture:api`; frontend modo API/puertos de fixture aislados; `pnpm test:browser` | No usar la API real como fixture. Sesión/navegar/recargar, source/PUT/START/STOP tardíos, limpiar, error/cancelación, 99,9 antes de completed, MP4/seek, teclado, PNG/histórico, filtros y dashboard; 1440/1280/390 px. Ampliar casos ausentes antes de afirmar cobertura. |
| Compose | Con env local y rutas externas individuales: `docker compose -f compose.yaml config --quiet` y `docker compose -f compose.yaml -f compose.gpu.yaml config --quiet` | Loopback, pesos/input read-only, sin datasets/holdouts/pesos dentro de imagen. |
| Docker GPU | Construir imagen candidata y smoke con un frame autorizado y ambos modelos | Hash/clase PERSON/identidad m, FP32/CUDA:0 y H.264 correctos, sin OOM; no confundir con E2E completo Docker. |
| E2E nativo CUDA | Repetir regresión controlada de sección 18 sobre demo C y DB test: fixture de pares existente, sin tocar perfiles productivos | 418/418 y resultado completo; ambos tipos, observaciones/geometry D coherentes, snapshots m/FORKLIFT, PNG accesible y eventos en historial. Documentar diferencias sin forzar conteos. |
| Evidencia/recuperación | Regresión F09 con IDs iguales entre clases; F15 PNG crítico desconocido; F16 interrupción→enqueue fallido→replay | F09 produce PNG correcto. Corregir o mantener exclusiones P2 explícitas y recibos de error veraces; no esconder fallos tras happy paths. |
| Git/documentación | Revisar diff/staged completos, `git diff --check`, `git diff --cached --check`; escaneo de rutas/secretos/medios y enlaces/assets | Solo archivos autorizados, históricos conservados, demo actual rotulada, notas preparadas. Sin Excel, main ni tag modificados por auditoría. |

No se ejecuta el gate completo en este checkpoint. Las cifras de sección 18 son
resultados previos de la base, no nuevos PASS. Se actualiza únicamente este informe
y el snapshot existente, conservando los cortes históricos. Resultado:
**PRE_V0_2_0_TECHNICAL_AUDIT_COMPLETE**, con decisión de release bloqueada por los
dos P1 concretos indicados y sin cambio funcional.


## 20. Cierre de P1 funcionales — 26-10-2026

Base `49d7c78ec55c8ccefc11b0512b22bf996c5e0c2f`, dev limpio y 0/0.
Se corrigen exclusivamente F09, F13 y F08; no se amplía a los P2.

- **F09 CLOSED.** render_track_frame resuelve y resalta por ObjectIdentity
  (class_name, track_id), reutilizando la identidad canónica. PERSON 1 y FORKLIFT 1
  ya no colisionan; PERSON 1/PERSON 2 y single-class conservan su comportamiento.
  Falta de clase o identidad completa duplicada produce error explícito, nunca
  selección arbitraria. Tests comprueban cajas/colores, endpoints de evento/PNG y
  replay CLI real con HTTP simulado. El renderer de pares mantiene sus endpoints
  geométricos para PERSON 1/FORKLIFT 1. No se añade publicación legacy de pares:
  su límite explícito anterior se conserva; Web/worker ya tienen esa integración.
- **F13 CLOSED.** Backend y validación de configuración del Motor rechazan antes
  de evaluar valores no numéricos, bool, negativos, no finitos o no representables.
  Conversión protegida frente a OverflowError/ValueError/TypeError, seguida de
  comprobación finita; no se convierten strings numéricos gigantes en parámetros.
  max_distance tiene dominio **[0, sqrt(2)]**, derivado de hypot(dx/width,dy/height)
  con ambos ejes normalizados. Valores >1, como 1,2, siguen siendo válidos por la
  diagonal; no son metros ni una distancia segura. Las duraciones siguen siendo
  no negativas y finitas/representables, sin un máximo operacional inventado.
  Se prueban cero, normales, sqrt(2), el siguiente float fuera de dominio,
  10**1000, NaN/±Infinity, strings y tipos inválidos. HTTP devuelve 400 y no crea
  filas ante entradas inválidas; la configuración nativa falla antes de evaluar.
  No se modifican umbrales configurados, comparación temporal ni geometría.
- **F08 CLOSED.** applyZoneRequest usa el mismo ref generation del workspace.
  Solo la generación vigente aplica respuesta, error y finally; navegar/cancelar
  contexto invalida la pendiente. Tres tests con promesas controladas verifican
  B antes que A, éxito/error obsoletos y error vigente. Browser añade un PUT
  retrasado al navegar/recuperar, sin cambiar layout, copy o política de sesiones.

Reconciliación P1 acotada: **F03–F10 y F12–F14 CLOSED**;
**F11 DEFERRED_BY_DECISION / OCCUPANT_ASSOCIATION_DESIGN_ONLY**.
**F02 OPEN**: validación externa/contextual experta y operacional final realista;
no bloquea v0.2.0 como MVP integrado, sí afirmaciones de cierre final/v1.0.0.

Regresión ejecutada sobre las correcciones:

| Gate | Resultado |
| --- | --- |
| Motor completo | 427 descubiertas: **425 PASS + 2 SKIP** opt-in de modelos reales. |
| Targets replay/identidad, pares y endpoints geométricos | **6/6 PASS**, además de la suite completa. |
| Backend/PostgreSQL test | **127/127 PASS**, incluidos HTTP extremos y persistencia/evidencia fixture. |
| Frontend, Node 24.2.0 / pnpm 11.28.2 | **37/37 PASS**; lint, typecheck y production build PASS. |
| Browser con API fixture aislada | **1/1 PASS**, PUT retrasado al navegar, MP4/seek, teclado, estados y 18 combinaciones ruta/viewport. |
| Django/migraciones/dependencias | check y migration checks PASS, sin cambios ni pendientes; pip check PASS en ambos entornos. |
| Formato/diff | Prettier estricto en los cinco archivos frontend tocados y git diff --check PASS; sin normalización global de EOL. |

El nuevo fixture multiclase calcula su propio SHA esperado; un primer intento
usó el hash del fixture legacy y fue rechazado correctamente. No se debilitó el
gate. Browser requirió autorización de ejecución de Chromium tras un timeout CDP
en el entorno restringido; la repetición completa aprobó. Los servidores fixture
se detienen al terminar y no sustituyen servicios operativos.

**READY_FOR_V0_2_0_RELEASE_PREP**. No se identificó otro P1 funcional reproducible
al revisar estos cambios. No equivale a crear/publicar el tag ni a haber repetido
el gate futuro Docker/CUDA real. Demo actual, rotulación histórica y notas siguen
como preparación F19. F15/F16/F17/F18/F20 permanecen abiertos y no se corrigen ni
se elevan a P0 aquí. Maquinaria móvil sigue NEEDS_MORE_EVIDENCE.

PERSON m, FORKLIFT v2, pesos, ByteTrack, perfiles/umbrales, geometría D, ocupancia,
contratos de transporte/persistencia, Docker, main y tags permanecen intactos.
No se entrenan modelos, no se usan holdouts/TEST2 y no se abre Excel/informe.
Solo cambia la validación de entradas, la identidad de evidencia legacy y la
aceptación frontend de respuestas; se conserva toda la evidencia histórica.


## 21. Demo y documentación pre-v0.2.0 — 26-10-2026

Base `21b9b05704c2a8560d08f21a5a915b2b0a58cc91`, dev limpio y sincronizado.
**F19 CLOSED / CURRENT_DEMO_READY / README_CURRENT / V0_2_0_RELEASE_NOTES_READY.**
Una demo principal C muestra el pipeline real con PERSON m, FORKLIFT v2,
ByteTrack, zona, permanencia y proximidad con geometría D. Se reutiliza byte a byte
el fixture controlado de la promoción m: 0,25 norm / 1 s, sin ajustar thresholds
para la presentación ni cambiar los perfiles predeterminados. Su configuración y
alcance demostrativo son explícitos en assets/demo/v0.2.0/README.md.

Se procesan 418/418 frames y se persisten dos eventos con PNG en PostgreSQL de
pruebas: proximidad en 30, permanencia en 60. Las cuatro capturas proceden del
build de producción, API y Motor reales; no de la API fixture. El MP4 de
presentación H.264 conserva 1920×1080, 30 FPS y 418 frames (13,933 s), se decodifica
completo y ocupa 5.165.910 bytes. Es una recomprensión del output original del
worker, preservado fuera de Git; ambos SHA y receta están en metadata.json.
No se cambia el encoder productivo ni se presenta esto como benchmark.

README prioriza demo, capacidades, arquitectura, ejecución y límites; los tres
attachments y MP4 OP-34/60/61 se conservan como PoC histórico. Solo se corrigen
inconsistencias materiales en los README secundarios. El brief visual original
queda rotulado histórico; no se rediseña la UI. RELEASE_NOTES.md prepara el
alcance del MVP integrado sin publicar release/tag ni atribuir validación final.

Se verifica decode/hashes/metadata de video e imágenes, identidad y hash del
fixture, ausencia de texto privado visible/metadata PNG y enlaces relativos con
case exacto. README renderizado localmente en 1280/390 px, sin overflow de página;
revisión visual de overlays, PNG, detalle e histórico. Build production PASS;
recorrido real de captura y test de consistencia PASS. No se repite el gate completo.
Las herramientas de render/compresión permanecen externas, sin cambios a dependencias.
No se abrió holdout/TEST2, Excel o informe; no hubo tuning ni modificaciones de código.

Versionado pendiente, sin bump: engine/pyproject.toml es metadata del paquete,
engine/src/operix_engine/__init__.py la refleja; frontend/package.json declara la
versión Web. No hay una fuente única global; los tres siguen en 0.1.0. /api/v1 no
es la versión del release. **READY_FOR_FINAL_RELEASE_GATE**, no tag autorizado:
faltan la regresión final sobre el candidato definitivo y la promoción explícita.
F02 sigue OPEN, F11 DEFERRED_BY_DECISION; F15/F16/F17/F18/F20 siguen abiertos.
