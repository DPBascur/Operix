# Holdout independiente PERSON — protocolo de adquisición

Este protocolo prepara material **nuevo y reservado** para evaluar detección `person`.
No incorpora videos de la campaña Keremberke, TEST3, TEST2 ni REAL_HOLDOUT_V2; no
entrena, calibra, selecciona modelos ni ejecuta inferencia. El ground truth humano
completo no demuestra por sí solo independencia de escenas. El estado actual es
`PERSON_HOLDOUT_ACQUISITION_READY`: todavía no hay nuevos videos ni evaluation congelada.

## Material y procedencia

Solicitar **3–5 videos nuevos de 30–90 s**, preferentemente cinco sesiones de
captura distintas, no cortes de una misma sesión. Cada video recibe un ID único
`HOLDOUT_PERSON_###`; todos sus frames conservan ese `source_group`. Priorizar
personas con y sin forklift, operador visible, oclusión, tamaños y distancias
variadas, varias personas, fondos difíciles y segmentos sin personas. Buscar
ángulos, cámaras, iluminaciones y orientaciones distintas. No se exige que cada
video cubra todos los casos ni que todos contengan forklift. Tres grupos es el
mínimo estructural; cinco ofrecen mejor diversidad, no garantía estadística.

Registrar para cada fuente: nombre original sin ruta privada, SHA-256, fecha de
ingreso, origen, cámara/fuente, resolución, FPS, duración, frames, codec,
orientación, escenario, iluminación, ambiente, presencia esperada de personas y
forklift, notas y derechos/licencia. El origen y los permisos deben poder
verificarse antes del freeze. Un ID diferente **no prueba** una escena
independiente: se exige revisión y atestación humana de esa separación. No
elegir videos ni frames a partir de predicciones, errores, confidence o
resultados de CURRENT/COCO/PERSON v2.

## Ingestión y muestreo sin detector

Ejecutar desde `engine/`, con el Python del entorno instalado de forma editable.
Los comandos son para Codex; Daniel solo proporciona material y anota en CVAT.
`--output-root` debe estar **fuera del repositorio**:

```powershell
.\.venv\Scripts\python.exe scripts/ingest_person_holdout_video.py --video <VIDEO_NUEVO> --output-root <CARPETA_LOCAL_FUERA_DE_GIT> --source-group HOLDOUT_PERSON_001 --origin <ORIGEN> --camera-or-source <CAMARA> --scenario <ESCENARIO> --rights-or-license <DERECHOS_VERIFICABLES> --notes <NOTAS>
.\.venv\Scripts\python.exe scripts/prepare_person_holdout_cvat.py --output-root <CARPETA_LOCAL_FUERA_DE_GIT> --source-group HOLDOUT_PERSON_001 --sample-count 16
```

La ingestión calcula el SHA-256 y metadata OpenCV, comprueba decodificación y
rechaza ID o video SHA repetidos. Copia el original fuera de Git. El muestreo
`--sample-count` distribuye índices uniformemente entre primer y último frame;
con un solo frame toma el central. Alternativamente se admite
`--interval-seconds`; el paso es `round(intervalo × FPS)`, mínimo un frame.
Se decodifica en orden y se guarda el índice/timestamp, la configuración y
SHA-256 de video, imágenes, ZIP y manifest. No se consulta ningún modelo ni se
filtran frames por resultado. Elegir el número de muestras **antes** de ver
predicciones; evitar cientos de frames redundantes del mismo video. El paquete
CVAT contiene `images.zip`, `manifest.csv`, `sampling.json` y plantillas vacías,
sin preanotaciones.

## Anotación humana

Una tarea CVAT por `source_group`, única etiqueta `person`. Daniel carga
`images.zip`, revisa cada frame completo, guarda y exporta COCO 1.0 sin incluir
imágenes; después confirma que terminó e identifica cualquier frame ambiguo.
Codex ubica el export y genera CSV, recibo con SHA, QA, labels y manifests.
Se mantiene exactamente la política anterior: una caja por persona
distinguible, incluyendo operador visible y oclusiones reconocibles; caja
ajustada a extensión visible, sin inventar cuerpo oculto; personas superpuestas
reciben cajas separadas. Frame completamente revisado sin persona es
`VERIFIED_NEGATIVE`; irresoluble es `REVIEW_AMBIGUOUS` y bloquea freeze.

Tras confirmación humana, Codex usa:

```powershell
.\.venv\Scripts\python.exe scripts/process_person_holdout_export.py --output-root <CARPETA_LOCAL_FUERA_DE_GIT> --source-group HOLDOUT_PERSON_001 --reviewer <REVISOR> --confirm-full-frame-human-review
```

## Aislamiento, readiness y freeze

Los nuevos grupos llevan `role=HOLDOUT_ONLY`,
`evaluation_status=LOCKED_EVALUATION_CANDIDATE` y
`model_access_allowed=false`. La función de asignación rechaza TRAIN o
CALIBRATION para estos IDs. Es una protección del tooling de holdout, no una
barrera del sistema operativo frente a cualquier script ajeno: mantener la
carpeta local separada y no pasarla a herramientas de entrenamiento.

Readiness distingue `PERSON_HOLDOUT_ACQUISITION_READY`,
`PERSON_HOLDOUT_PARTIAL`, `PERSON_HOLDOUT_READY_TO_FREEZE`,
`PERSON_EVALUATION_READY` y `PERSON_HOLDOUT_BLOCKED`. El estado
`READY_TO_FREEZE` es candidato: requiere revisión final de QA, procedencia,
licencia y ausencia de solapamiento de escenas. No se reconstruyen TRAIN ni
CALIBRATION en esta tarea. TEST3 permanece en desarrollo y nunca se mezcla con
el holdout reservado.

Solo con **al menos tres grupos independientes**, originales y frames
trazables por SHA, positivos y negativos humanos, cero ambigüedades/bloqueos,
recibos completos, derechos claros y atestación humana explícita de
independencia puede ejecutarse el comando de freeze:

```powershell
.\.venv\Scripts\python.exe scripts/freeze_person_independent_holdout.py --output-root <CARPETA_LOCAL_FUERA_DE_GIT> --attestor <RESPONSABLE> --attest-independent-groups
```

Produce CSV/JSON de `locked-evaluation-manifest`, hashes, fuente y grupos,
fecha, atestación y criterio futuro de matching PERSON uno-a-uno con IoU ≥0,5.
No sobrescribe un freeze existente; cambios posteriores invalidan sus hashes
y exigen nuevo versionado. **No ejecutar este comando antes de disponer del
material y la aprobación humana de independencia.** Solo después de congelar,
un hito posterior podrá separar calibration del training, fijar thresholds en
calibration y evaluar cada modelo una vez sobre locked evaluation. Ningún
resultado de detector debe consultarse sobre estos frames antes del freeze.
