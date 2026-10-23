# Holdout independiente PERSON — protocolo de adquisición

Este protocolo prepara material **nuevo y reservado** para evaluar detección `person`.
No incorpora videos de la campaña Keremberke, TEST3, TEST2 ni REAL_HOLDOUT_V2; no
entrena, calibra, selecciona modelos ni ejecuta inferencia. El ground truth humano
completo no demuestra por sí solo independencia de escenas. Protocolo vigente:
`PERSON_FINAL_HOLDOUT_V2`. El set YouTube previo se conserva como
`PERSON_YOUTUBE_DIAGNOSTIC_SET_V1`, `DIAGNOSTIC_ONLY`, `NOT_LOCKED_EVALUATION`.
Sus 68 frames y 89 cajas no habilitan selección de threshold/ganador final ni
métricas finales. Los derechos siguen sin verificar; la reclasificación metodológica
no otorga permiso de uso ni distribución. No se repite anotación ni se mueve material.
El nuevo root local `Operix-experiments/person-independent-holdout-v2-2026-10-23/`
está preparado para adquirir fuentes válidas y todavía no contiene videos.

## Material y procedencia

Solicitar **3–5 videos nuevos de 30–90 s**, preferentemente cinco sesiones de
captura distintas, no cortes de una misma sesión. Cada video recibe un ID único
`HOLDOUT_PERSON_###`, sin reutilizar IDs excluidos (comenzar, por ejemplo, en 006).
Todos sus frames conservan ese `source_group`. Registrar también `source_family`:
los clips de una misma sesión/captura comparten familia incluso con SHA distintos.
El mínimo es **tres familias independientes**, preferiblemente cuatro o cinco.
El freeze cuenta familias, no archivos ni IDs. Priorizar
personas con y sin forklift, operador visible, oclusión, tamaños y distancias
variadas, varias personas, fondos difíciles y segmentos sin personas. Buscar
ángulos, cámaras, iluminaciones y orientaciones distintas. No se exige que cada
video cubra todos los casos ni que todos contengan forklift. Tres grupos es el
mínimo estructural, ahora contado por familias; cinco ofrecen mejor diversidad, no garantía estadística.

Registrar para cada fuente: nombre original sin ruta privada, SHA-256, fecha de
ingreso, origen, cámara/fuente, resolución, FPS, duración, frames, codec,
orientación, escenario, iluminación, ambiente, presencia esperada de personas y
forklift, notas y derechos/licencia. El origen y los permisos deben poder
verificarse antes del freeze. Un ID diferente **no prueba** una escena
independiente: se exige revisión y atestación humana de esa separación. No
elegir videos ni frames a partir de predicciones, errores, confidence o
resultados de CURRENT/COCO/PERSON v2.

## Requisitos del ingreso final v2

Prioridad: grabación original con permiso/consentimiento apropiado; alternativamente
fuente externa con licencia explícita compatible y verificada. Metadata obligatoria:
`source_group`, `source_family`, `source_file`, `sha256`, `acquisition_date`,
`recorded_by`, `camera_or_source`, `location_context_general`, resolución, FPS,
duración, escenario, `rights_basis`, `consent_or_permission_status` y notas.
Además se exige referencia verificable de captura (`provenance_reference`) y del
permiso (`rights_evidence`), sin publicar información privada. La confirmación CLI
solo registra la declaración humana: no verifica jurídicamente una licencia.

`rights_basis` admite exclusivamente `USER_ORIGINAL_RECORDING`,
`EXPLICIT_PERMISSION`, `CC_BY_VERIFIED` u `OTHER_VERIFIED_LICENSE`.
Se requieren `KNOWN_PROVENANCE`, `RIGHTS_CONFIRMED` y permiso/consentimiento
`CONFIRMED`; etiquetas genéricas o licencia desconocida no permiten freeze.

## Ingestión y muestreo sin detector

Ejecutar desde `engine/`, con el Python del entorno instalado de forma editable.
Los comandos son para Codex; Daniel solo proporciona material y anota en CVAT.
`--output-root` debe estar **fuera del repositorio**:

```powershell
.\.venv\Scripts\python.exe scripts/ingest_person_holdout_video.py --video <VIDEO_NUEVO> --output-root <ROOT_V2_FUERA_DE_GIT> --source-group HOLDOUT_PERSON_006 --source-family CAPTURA_001 --origin <ORIGEN> --recorded-by <AUTOR> --camera-or-source <CAMARA> --location-context-general <CONTEXTO_GENERAL> --scenario <ESCENARIO> --provenance-reference <REFERENCIA_CAPTURA> --rights-or-license <PERMISO_O_LICENCIA> --rights-basis USER_ORIGINAL_RECORDING --rights-evidence <REFERENCIA_PERMISO> --confirm-provenance-and-rights --notes <NOTAS>
.\.venv\Scripts\python.exe scripts/prepare_person_holdout_cvat.py --output-root <ROOT_V2_FUERA_DE_GIT> --source-group HOLDOUT_PERSON_006 --sample-count 16
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

Presupuesto inicial: **12–20 frames por familia**, repartidos entre sus videos
si una captura tiene varios clips. No multiplicar el presupuesto al cortar una sesión.

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
.\.venv\Scripts\python.exe scripts/process_person_holdout_export.py --output-root <ROOT_V2_FUERA_DE_GIT> --source-group HOLDOUT_PERSON_006 --reviewer <REVISOR> --confirm-full-frame-human-review
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

Solo con **al menos tres familias independientes**, originales y frames
trazables por SHA, positivos y negativos humanos, cero ambigüedades/bloqueos,
recibos completos, derechos claros y atestación humana explícita de
independencia puede ejecutarse el comando de freeze:

El registro local `holdout-policy.json` exige tres coberturas: `campaign`
(incluye TEST3), `youtube_diagnostic` y `training_development`. Cada manifiesto
CSV debe tener `image_sha256`, `source_group` y SHA propio verificado; se compara
también `video_sha256` y `source_family` cuando están disponibles. Cualquier coincidencia de imagen,
grupo, familia registrada o video bloquea el freeze. Las familias relacionadas se excluyen mediante
revisión humana de procedencia: un hash diferente no demuestra ausencia de leakage.
El registro completo de training/development debe incorporarse y atestarse antes
de marcar `training_development_coverage_confirmed=true`; actualmente está pendiente.
También se exige `no_model_access_attested=true` después de confirmar que ningún
detector accedió al nuevo material. No abrir TEST2 ni REAL_HOLDOUT_V2 para esto.
La política, las referencias de exclusión y el mapeo de familias quedan vinculados
por hashes al freeze. Su modificación invalida la verificación posterior.

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
