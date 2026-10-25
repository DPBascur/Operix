# Etapa 3 — evaluación experimental del pipeline de percepción y eventos

Para el estado transversal al 23-10-2026, pruebas, hardening y pendientes, véase
la [matriz de validación de Etapa 3](ETAPA3-VALIDATION-MATRIX.md).
Las campañas siguientes conservan sus configuraciones y resultados históricos;
no equivalen a una evaluación del holdout PERSON final, aún sin anotación humana.

## Alcance y recursos reproducibles

Esta evidencia consolida seis campañas exploratorias: umbral de confianza, baseline multiescenario, ajuste acotado de ByteTrack, diagnóstico de pérdida por pose, resolución en C y comparación 640/1280 en A/B/C. No es una medición formal de precisión, MOT ni seguridad industrial. Ninguna campaña cambió los pesos, los defaults ni el criterio de la regla. Los resultados proceden de experimentos locales del 14-10-2026 y sus registros detallados anteriores permanecen recuperables en el historial Git.

Los clips sintéticos pertenecen a [NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes](https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes/tree/d5b88d3abcf659f304a107f4336b71b4e2159133), revisión `d5b88d3abcf659f304a107f4336b71b4e2159133`, licencia OpenMDW-1.1; véase el [aviso de terceros](../../third_party/nvidia-warehouse-dataset/NOTICE.md). A/B son assets de demostración ya versionados; C, pesos, JSONL, PNG, MP4 diagnósticos y configuraciones locales permanecen fuera de Git.

| Escenario | Clip / vista | Frames; 30 FPS; 1920×1080 | SHA-256 |
| --- | --- | ---: | --- |
| A, evacuación con varias personas | `warehouse_fire_ceiling04.mp4` / `ceiling_04` | 277 | `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6` |
| B, persona–montacargas | `forklift_human_nearmiss_ceiling00.mp4` / `ceiling_00` | 300 | `E4795E873DCBDAAA4DC3D42F533052E3C1DB62D1D3EF786C2C90DD4D7681330B` |
| C, recogida de caja y agachamiento | `008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4` / `cam_00` | 418 | `EABF44D7ABE50D1BF4824F238A9F0AC9DDC29419E10D66B89C6A92CB1B98329C` |

Equipo: Windows 10 x64, Ryzen 5 5500, RTX 3070; Python 3.12.10, PyTorch 2.14.0+cu130, OpenCV 5.0.0, Ultralytics 8.4.146 y `lap==0.5.12`. Pesos `yolo11n.pt` COCO, SHA-256 `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`; CUDA, IoU `0.70`, filtro `person`. Baseline: `confidence=0.10`, `imgsz=640`; ByteTrack `track_high_thresh=0.25`, `track_low_thresh=0.10`, `new_track_thresh=0.25`, `track_buffer=30`, `match_thresh=0.80`, `fuse_score=true`. Regla `demo_zone_dwell` v1, `min_duration_s=2.0` **experimental**, no umbral calibrado de riesgo.

Las primeras campañas utilizaron zonas demostrativas rectangulares; sus hashes JSON históricos son A `4CDB60006900F7547C1699DD5AFE05399607ECA2735E178E42ED7DB535A18B27`, B `7F4600770831C9F73E1FC0E2291717B49121FF106D2E915ACB189AFBF5289D05`, C `57AC51E411A2A355B68A7BEB4E3C7B1BD2E0F248B1CA2ED23AA6EF513C2DB3D7`. Son identidades de **aquellas** corridas; no deben reemplazarse retrospectivamente si evolucionan los polígonos de demo. El punto de pertenencia es el centro inferior de la caja. Para repetir la evaluación lógica se requiere conservar las configuraciones locales B/C o reconstruir su semántica desde el esquema y las coordenadas antiguas: B `(0.20,0.38),(0.62,0.38),(0.62,0.95),(0.20,0.95)`; C `(0.26,0.40),(0.70,0.40),(0.70,0.88),(0.26,0.88)`. A estaba en `engine/config/examples/desktop-zone-dwell.json` antes de su eventual ajuste visual. Reconstruir el contenido semántico no reproduce necesariamente el SHA ni el `analysis_run_id`.

## Confianza YOLO11n: escenario A

Se varió solo `confidence`, con `imgsz=640` y los demás controles fijos. Las primeras corridas pasaron por Django/PostgreSQL local; reintentos de `0.25/0.40/0.50` conservaron exactamente detecciones, IDs y candidatos y no duplicaron filas gracias a idempotencia. El tiempo de esas corridas incluía PNG/HTTP y condiciones de caché distintas; **no** se usa para comparar FPS entre umbrales.

| Confianza | Detecciones `person` | Observaciones | IDs | Huecos internos: episodios / frames | Candidatos `(frame/ID)` |
| ---: | ---: | ---: | ---: | ---: | --- |
| 0.10 | 1.088 | 644 | 8 | 4 / 15 | 60/1, 60/2, 134/13, 201/31 |
| 0.25 | 668 | 632 | 8 | 6 / 18 | 60/1, 134/13, 201/31 |
| 0.40 | 605 | 592 | 6 | 11 / 18 | 60/1, 140/7, 231/13 |
| 0.50 | 541 | 537 | 4 | 15 / 53 | 65/1, 168/1, 230/4, 238/5 |

**Decisión:** mantener `0.10` como baseline exploratoria. Menos IDs a umbral alto no prueban mejor tracking: se pierden observaciones, aumentan huecos y los candidatos cambian de modo no monótono. No se midió precisión/recall y se conservan posibles cajas espurias.

## Baseline multiescenario y ByteTrack

El flujo A/B/C inicial fue video → YOLO11n `person` → ByteTrack → variables espacio-temporales → `zone_dwell`. Los FPS siguientes proceden de la ejecución integrada con API/evidencia y **no** de un benchmark controlado. A generó cuatro candidatos duplicados de una corrida previa; B y C publicaron uno y dos nuevos, respectivamente. Un duplicado de API no significa ausencia de candidato.

| Escenario | `person` | Observaciones / IDs | Huecos | Candidatos | FPS integrado exploratorio |
| --- | ---: | ---: | --- | --- | ---: |
| A | 1.088 | 644 / 8 | 4 episodios internos; 15 frames | 60/1, 60/2, 134/13, 201/31 | 32,461 |
| B | 302 | 300 / 1 | 0; ID 1 en 0–299 | 60/1 | 39,891 |
| C | 361 | 360 / 2 | 58 frames sin track entre IDs 1 y 2 | 60/1, 228/2 | 43,324 |

Se comparó el ByteTrack baseline con `track_buffer=60`, `track_buffer=90` y, por separado, `track_high_thresh=0.20`, en A y C, sin publicar eventos. A mantuvo 8 IDs, 644 observaciones y cuatro candidatos con buffers 30/60/90; el umbral alto 0.20 dejó 639 observaciones y un frame adicional de hueco. C mantuvo **361 detecciones, 360 observaciones, 2 IDs, pérdida 110–167 y dos candidatos** en las cuatro variantes. Con buffer 90 el ID 1 aún estaba *lost* en 167, pero la caja predicha se había desplazado respecto de la detección de retorno; no se reasoció. **Decisión:** no alterar ByteTrack antes de mejorar la detección. El renderer ya rellena el polígono `Zone.polygon` con cyan al 8 % o ámbar para candidato, con borde y rótulo discretos; el aspecto rectangular histórico procede de la configuración de las zonas.

## C: diagnóstico de pose y resolución

En C640 la persona visible se agacha; la última salida de ID 1 es frame 109. Durante **110–166** hay 57 frames sin `person` a confianza 0.10 y una caja errónea `fire hydrant` superpuesta en 57/57. En frame 167 reaparece una caja `person` válida; el ID 2 se emite desde 168. Al bajar solo la confianza a 0.05/0.01 se obtuvieron 2/6 cajas débiles pertinentes en esos 57 frames y 27/100 cajas `person` espurias en otras regiones; tracking y candidatos siguieron en **360 observaciones, 2 IDs, 60/1 y 228/2**. Las seis cajas pertinentes de 0.01 estaban bajo `track_low_thresh=0.10`. La persona continúa visible; no se verificó oclusión completa. **Diagnóstico:** la pérdida principal empieza en el detector; al retorno también hay una limitación de reasociación, pero extender el buffer no la resolvió.

Se comparó después solo `imgsz` en el mismo C, con `confidence=0.10`, IoU 0.70 y tracker/regla fijos. Los FPS del estudio de costo fueron dos pasadas calentadas por tamaño, en orden balanceado; incluyen lectura, inferencia, tracking y regla, no renderer/API/escritura.

| `imgsz` | `person` pertinente en 110–166 | `fire hydrant` superpuesta | Observaciones / IDs | Pérdida visible | Candidatos | FPS calentado agregado |
| ---: | ---: | ---: | ---: | --- | --- | ---: |
| 640 | 0/57 | 57/57 | 360 / 2 | 110–167, 58 frames | 60/1, 228/2 | 56,013 |
| 960 | 28/57 | 49/57 | 388 / 1 | 121–149, 29 frames; y 157 | 60/1, 218/1 | 54,316 |
| 1280 | 50/57 | 13/57 | 410 / 1 | 137–144, 8 frames | 60/1, 205/1 | 48,530 |

`imgsz=1280` recuperó materialmente `person` y conservó ID 1, aunque hubo un tramo sin salida y **dos** candidatos: la regla de permanencia se rearma al perder observaciones, incluso si luego retorna el mismo ID. No implica precisión formal ni resuelve por completo la confusión. Los picos de memoria PyTorch del estudio fueron aproximadamente 56,4 / 72,0 / 96,1 MiB asignados para 640/960/1280: **no** representan toda la VRAM.

## Comparación posterior A/B/C: 640 frente a 1280

Una misma instancia YOLO se calentó con 20 predicciones por tamaño; se procesaron los videos completos en orden A640 → A1280 → B1280 → B640 → C640 → C1280 → C1280. Cada corrida creó tracker, analizador y regla nuevos; los candidatos quedaron en memoria. `FPS = frames / tiempo` incluye lectura, inferencia, tracking, variables y regla, pero excluye calentamiento, visualización, escritura, HTTP y persistencia. El contrabalanceo de orden fue parcial: los FPS son exploratorios, no sustituyen [OP-43](OP-43-performance.md).

| Escenario | `imgsz` | FPS | Detecciones `person` | Observaciones / IDs | Huecos internos | Frames sin track | Candidatos |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| A | 640 | 52,973 | 1.088 | 644 / 8 | 4 episodios; 15 frames | 0 | 60/1, 60/2, 134/13, 201/31 |
| A | 1280 | 45,179 | 692 | 644 / 3 | 3 episodios; 37 frames | 0 | 60/1, 60/2, 197/5 |
| B | 640 | 52,663 | 302 | 300 / 1 | 0 | 0 | 60/1 |
| B | 1280 | 47,320 | 300 | 300 / 1 | 0 | 0 | 60/1 |
| C | 640 | 52,140 | 361 | 360 / 2 | 0; separación entre IDs | 58 | 60/1, 228/2 |
| C | 1280 | 47,067 | 411 | 410 / 1 | 1 episodio; 8 frames | 8 | 60/1, 205/1 |
| C repetido | 1280 | 46,677 | 411 | 410 / 1 | 1 episodio; 8 frames | 8 | 60/1, 205/1 |

En A1280 disminuyen 36,4 % las cajas `person` y 14,7 % los FPS; las observaciones permanecen en 644 pero aumentan los frames ausentes dentro de IDs y cambian candidatos. Menos IDs podrían indicar menos tracks espurios o otra asociación; **no** prueban mejora sin anotaciones. En B1280, el único ID sigue continuo y el candidato no cambia, con 10,1 % menos FPS; las etiquetas alternativas `suitcase`/`bench` sobre la escena no representan `forklift`. En C1280, `person` aumenta 13,9 %, la pérdida baja de 58 a 8 frames y el FPS baja 9,7 %. La repetición C1280 reprodujo exactamente detecciones, ID, hueco y candidatos; solo varió 0,8 % el FPS. Las imágenes locales comparativas de A/B/C se revisaron visualmente; a C140 ambas resoluciones pierden el track y a C160 solo 1280 conserva una salida de `person`.

**Decisión provisional:** conservar `imgsz=640` como default y evaluar `1280` por escenario cuando exista pérdida por pose como en C. No se recomienda globalmente: A ofrece resultado mixto y B no obtiene ventaja funcional. El error `fire hydrant`/`person` residual mantiene abierta la adaptación futura del detector, sin entrenar ni sustituir pesos en estas campañas.

## Zonas de demostración con perspectiva del piso

Se reemplazaron **solo** los polígonos demostrativos rectangulares de A/B/C por cuadriláteros manuales en coordenadas normalizadas. `Zone.polygon`, `point_in_zone` y `OpenCvRenderer.render_zone` ya aceptaban polígonos arbitrarios; no se modificaron. El renderer rellena exactamente ese polígono con cyan al 8 % y borde fino, o ámbar cuando participa en un candidato. La regla consume la misma configuración, por lo que zona visual y lógica coinciden. No se implementó homografía, segmentación ni editor interactivo. Los archivos nuevos de B/C son ejemplos versionables; los JSON locales originales y hashes históricos anteriores permanecen sin alterar.

| Escenario / configuración vigente de demo | Polígono `(x,y)` en orden | SHA-256 JSON nuevo | Candidatos con zona nueva frente a zona histórica |
| --- | --- | --- | --- |
| A / `desktop-zone-dwell.json` | `(0.19,0.73)`, `(0.77,0.70)`, `(0.98,0.98)`, `(0.02,0.98)` | `ACC67314AC43A21B4A867C0A0E336566987E419E0A309058E9A979EEAF6E69A0` | **3 frente a 4:** 60/1, 60/2, 134/13; deja de aparecer 201/31. |
| B / `warehouse-nearmiss-zone-dwell.json` | `(0.38,0.35)`, `(0.51,0.35)`, `(0.54,0.98)`, `(0.10,0.98)` | `FBDFFCA8D22406BA497C993FBAC4839B8D06E95FD8E9C694C85C580FC5CE380B` | **1 frente a 1:** 60/1. |
| C / `warehouse-box-pickup-zone-dwell.json` | `(0.24,0.40)`, `(0.43,0.40)`, `(0.96,0.98)`, `(0.01,0.98)` | `951A3092CD7818BDDA192D13404D47DDB4995CA1D3435801EE1C5009194CF42E` | **2 frente a 2:** 60/1 y 228/2. |

La revalidación completa a `imgsz=640` y `confidence=0.10` procesó 277/300/418 frames, mantuvo respectivamente 1.088/302/361 detecciones `person`, 644/300/360 observaciones y 8/1/2 IDs. El único cambio de regla observado fue en A: el candidato 201/31 quedó fuera del área de piso delimitada; **no se movió la zona para recuperarlo**. Las capturas antes/después y de candidatos se revisaron localmente y permanecen fuera de Git. La superposición 2D puede cruzar visualmente un objeto delante del piso; una ocultación física correcta requeriría segmentación o geometría 3D, fuera del alcance actual.

### Decisión de trazabilidad de la zona B — 21-10-2026

**Decisión humana:** `CURRENT_8_VERTEX_ZONE_BASELINE_FOR_STAGE3`. Para Etapa 3 se mantiene como baseline operativo de B la geometría actual de `pasillo_persona_demo`, definida en [warehouse-nearmiss-zone-dwell.json](../config/examples/warehouse-nearmiss-zone-dwell.json). Esta nota no modifica la configuración ni los resultados históricos de la sección anterior; su tabla describe la etapa de cuadriláteros, no la geometría vigente de B.

- **Cuadrilátero histórico versionado:** commit `29f13d373de65c3b85c41613533759d8f179bd1f` (`feat(zonas): ajustar polígonos demostrativos al piso`); vértices ordenados `(0.38,0.35)`, `(0.51,0.35)`, `(0.54,0.98)`, `(0.10,0.98)`. Es distinto del rectángulo local de las primeras campañas.
- **Geometría actual de ocho vértices:** commit `e2529d8228559555ee8f5749f9b4d9175239027b` (`feat(analisis): completar ciclo web con demos por perfil`); vértices ordenados `(0.38,0.35)`, `(0.51,0.35)`, `(0.52,0.53)`, `(0.53,0.75)`, `(0.54,0.98)`, `(0.10,0.98)`, `(0.22,0.70)`, `(0.30,0.51)`.
- **Clasificación de procedencia:** `LIKELY_INTENTIONAL_BUT_UNDOCUMENTED`. La introducción parece intencional por su contexto funcional, pero la motivación geométrica exacta de los cuatro vértices intermedios no quedó explícitamente registrada. La decisión humana actual no reconstruye esa motivación retrospectivamente.

Se mantiene la geometría actual porque es la configuración vigente, su introducción parece intencional, no existe evidencia suficiente para justificar una reversión y la auditoría de la pasada B no encuentra diferencias de pertenencia ni de episodios. Revertirla introduciría una modificación nueva sin respaldo experimental. **No se ha demostrado superioridad geométrica** de la versión actual frente al cuadrilátero histórico.

La auditoría se realizó sobre las observaciones guardadas de una única pasada B, con HEAD `5fc0d21ce96a0bd32b9fc61415f68961e2cb0cad`: se recalculó pertenencia desde los bottom-centers de los CSV, sin ejecutar nuevamente video, detectores ni tracking. Entre ambas versiones cambian **0/300 frames** de pertenencia, tanto para PERSON como para FORKLIFT y para el par. PERSON permanece dentro en los frames **0–299**; FORKLIFT y ambos dentro comparten el mismo episodio **182–299**, con **118 observaciones**, inicio `6.066667 s`, fin `9.966667 s` y duración entre timestamps `3.900000 s`. El final coincide con el final del clip y no demuestra una salida de la zona.

**Alcance limitado:** la equivalencia observada aplica únicamente a esa pasada B; no debe generalizarse a otras posiciones, cámaras o videos. No se selecciona `max_distance` ni `minimum_duration_seconds`, no se activa `person_forklift_proximity` y no se usa TEST2. Los CSV y artefactos visuales de auditoría permanecen fuera de Git. Se registra exclusivamente la decisión de trazabilidad, sin modificar percepción, ByteTrack, reglas ni geometría.

## Preparación del detector adaptado: auditoría de datos, sin entrenamiento

Se consultó el [índice oficial y formato de NVIDIA](https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes) en la revisión fijada y los índices locales `metadata/runs.parquet` y `metadata/clips.parquet`. El nivel RGB ofrece MP4 por cámara y metadatos por run; el nivel `artifacts/` une por `run_id` y contiene `object_detection.jsonl` y `camera_params.jsonl` por cámara, además de segmentación/IDs. El JSONL de detección tiene una línea por frame con `agents`/`objects`, etiqueta semántica, cajas 2D *tight* y *loose* en píxeles, caja 3D y metadatos del agente. El `prim_path` identifica al agente dentro del run; `semanticId` de caja **no debe asumirse igual al instance ID** de la segmentación NPZ. La relación exacta con la tabla de mapeo de instancias debe verificarse si se usa supervisión temporal. No se descargaron shards completos: se inspeccionaron cabeceras TAR por rangos y fragmentos pequeños de un JSONL de cada escenario.

La taxonomía observada **no es directamente la taxonomía YOLO objetivo**. En near-miss, box-pickup y fire, los trabajadores muestreados tienen `label.class=character` y grupo `Worker`; el montacargas muestreado en near-miss y collision tiene `label.class=robot`, con grupos observados `forklift` y `forklift_group`. La muestra de collision incluye además objetos de escena como `floor`, `wall`, `pillar` y `rack,shelf`, que no son clases objetivo. Por ello, **sí existen cajas 2D aprovechables para construir las dos clases objetivo**, pero no se confirmó una etiqueta semántica nativa `forklift`: mapear indiscriminadamente `robot` a `forklift` sería incorrecto. El conversor propuesto debe aceptar `character`/`Worker` como candidato a `person` y `robot` **solo si** metadatos de grupo/nombre y revisión visual verifican que ese agente es un montacargas. Otros robots y props deben quedar fuera. La distribución global de ambas clases no puede calcularse desde los Parquet: indexan runs/clips, no objetos por frame.

Los índices locales contienen **29.195 runs y 122.967 clips**. Para un piloto con vistas sincronizadas verificables hay 1.642 runs multivista `nearmiss`, 4.120 `forklift_collision`, 2.601 `box_pickup` y 9.064 `fire`. Otros 11.768 registros `nearmiss` son `extras_single_view` sin seed en el índice: no se proponen para el primer split por run/seed. Los runs multivista de los cuatro escenarios muestreados tienen seed no nulo y no se hallaron seeds duplicadas en el índice. Estos números son disponibilidad potencial, **no** conteos de ejemplos positivos confirmados.

**Subset piloto propuesto, sujeto a auditoría de etiquetas:** 120 runs nuevos y una cámara por run, estratificada por perspectiva; 40 near-miss, 20 collision, 40 box-pickup y 20 fire. Seleccionar 12 frames por clip repartidos entre fases de acción, tras inspeccionar anotaciones y visibilidad; ≈**1.440 imágenes**. Split por grupos completos `(scenario, seed, run_id)`, nunca aleatorio por frame ni separando cámaras sincronizadas: near-miss **28/6/6**, collision **14/3/3**, box-pickup **28/6/6**, fire **14/3/3** runs para train/val/test; total **84/18/18 runs**, ≈**1.008/216/216 imágenes**. El run C de agachamiento y los runs A/B ya usados en diagnóstico se excluyen de train/val y quedan como **pruebas diagnósticas externas**; C ya influyó en decisiones experimentales y por eso **no** sustituye al test ciego de 18 runs independientes. Evitar también que un mismo seed o simulación reaparezca en otro split mediante comprobación previa de metadatos.

La distribución objetivo de imágenes es: near-miss ≈480 con persona y montacargas esperados; collision ≈240 con montacargas y persona opcional que debe confirmarse; box-pickup ≈480 con posturas de persona; fire ≈240 con varias personas. Son **asignaciones de muestreo**, no recuentos reales de cajas. Antes de entrenar hay que contar por anotación cajas válidas y tamaños/oclusiones por clase, revisar etiquetas visualmente y reajustar el subset si falta diversidad de caminata, agachamiento, interacción, escala, vista parcial o movimiento del montacargas. Los tamaños medianos RGB del índice son aproximadamente 15,7 MiB (near-miss), 23,4 MiB (collision), 21,5 MiB (box-pickup) y 14,5 MiB (fire) por cámara; los 120 clips representan ≈**2,2 GiB** de MP4 si se obtienen completos. Los JSONL y frames extraídos agregan volumen variable (en muestras, JSONL de detección de ≈1,7–26,8 MB); no se justifica descargar cientos de GiB/TiB ni publicar estos datos en Git.

Para YOLO se necesitaría: localizar RGB y JSONL por mismo `run_id`/cámara; comprobar alineación frame–línea; validar que cada caja *tight* corresponde a una instancia objetivo, tiene área positiva y queda dentro del frame tras clipping explícito; convertir `xyxy` de 1920×1080 a `class_id x_center y_center width height` normalizados; conservar manifiesto de procedencia, seed, cámara y split; revisar ejemplos visuales y contar clases **antes** de fine-tuning. No iniciar entrenamiento ni fijar arquitectura/hiperparámetros hasta verificar el mapeo de etiquetas, cobertura de posturas y licencia/atribución de los derivados.

## Límites y continuidad

Los tres clips son sintéticos y acotados; no existe ground truth de cajas, identidad ni eventos evaluado en estas campañas A/B/C. No se afirma precisión/recall formal para esos clips, MOTA, IDF1, HOTA, ID switches confirmados, validez industrial ni tiempo real sostenido. Los IDs son temporales, no personas identificadas; un candidato no equivale a incidente. Los resultados dependen de clips, equipo y configuración. COCO no tiene clase `forklift`; el pipeline vigente filtra solo `person`, sin tracking fiable de maquinaria. La auditoría, separación train/val/test y primera adaptación del detector se realizaron después como piloto independiente, descrito a continuación; sus métricas supervisadas no se atribuyen retrospectivamente a A/B/C.

## Detector adaptado `person`/`forklift`: primer piloto

El [dataset NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes](https://huggingface.co/datasets/nvidia/PhysicalAI-WorldModel-Synthetic-Warehouse-Operations-Scenes), revisión `d5b88d3abcf659f304a107f4336b71b4e2159133`, se utilizó como fuente sintética. Este piloto de **80 runs** sustituye la propuesta exploratoria anterior de 120 runs; no altera sus resultados históricos. Se congelaron 56/12/12 runs independientes para train/validation/test, respectivamente: near-miss 21/5/4, collision 14/3/3, box-pickup 14/3/3 y fire 7/1/2. Los 80 `seed` son distintos, las cámaras de un run no cruzan splits y A/B/C quedan fuera de los tres conjuntos. Se descargaron selectivamente pares RGB/`object_detection.jsonl` por rangos, nunca shards TAR completos. Dos runs se sustituyeron dentro de su mismo escenario y split reservado por problemas técnicos de disponibilidad/alineación de artefactos, **sin consultar predicciones ni escoger ejemplos favorables**: validation box-pickup `0bd5bc0aade272dea224_run_1_seed_626427004` → `0c171270176f09333ff7_run_2_seed_1484360528`; test fire `033426474b8f6510d5b6_run_8_seed_1625133323` → `0326dc755ebda53d76a6_run_1_seed_540444659`. El plan local final tiene SHA-256 `BBA03B90DA9994EDA02D9A7BB9A9E93433F76FFE404C9C253B3A7C459041BFCE`; el registro previo de splits, `FC88BD16A166D47F654F2A0E7CBBC292B1EBFCA711BD5334AD8F1C00F9C3B59E`, se mantiene fuera de Git. Cinco cámaras de train se excluyeron por desalineación video/JSONL; quedaron 107/24/24 cámaras en train/validation/test.

El mapeo aceptó `character` + `Worker` + `Worker_*` como `person` (0), y solo `robot` + grupo `forklift`/`forklift_group` + nombre de montacargas + activo `forklift.usd` como `forklift` (1); otros robots no se incluyeron. Se usaron cajas 2D *tight*, clipping y normalización YOLO, con rechazo de cajas inválidas. Se muestrearon aproximadamente diez instantes por cámara (selección por anotaciones en train/validation; índices únicamente temporales en test), más negativos seguros disponibles en train/validation. Los manifests locales registran 204 observaciones objetivo sin caja utilizable; no se inventaron cajas para ellas. La comprobación automática verificó imágenes decodificables, rangos de cajas, conteos, 80 runs/`seed` únicos y ausencia de A/B/C. Una lámina local de train/validation permitió contrastar visualmente cajas y objetos antes de entrenar; **no se inspeccionó visualmente test antes de seleccionar `best.pt`**.

| Split | Runs | Imágenes | Cajas `person` | Cajas `forklift` | Fondos puros |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train | 56 | 1.082 | 1.103 | 669 | 25 |
| Validation | 12 | 244 | 203 | 160 | 6 |
| Test | 12 | 219 | 223 | 140 | 0 |
| **Total** | **80** | **1.545** | **1.529** | **969** | **31** |

Los fondos seguros fueron solo 31/1.545 imágenes (≈2,0 %), por debajo del objetivo orientativo de 5–10 %: no se incorporaron escenas ambiguas ni runs adicionales para forzar la proporción. En test, frames temporalmente preseleccionados con objetivos sin caja válida y ninguna caja utilizable se omitieron sin reemplazo; una cámara no aportó imágenes. El test resultante **no contiene fondos puros** y, por tanto, no evalúa adecuadamente falsos positivos en escenas vacías. La selección/omisión estaba fijada antes de conocer sus métricas, pero este límite reduce el alcance de la evaluación.

Se entrenó **una sola vez** a partir de `yolo11n.pt` COCO (SHA-256 `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`), con Ultralytics 8.4.146, PyTorch 2.14.0+cu130 y RTX 3070 8 GiB: `imgsz=640`, `epochs=100`, `patience=20`, `batch=8`, `device=0`, `seed=42`, optimizador automático AdamW y augmentations estándar. No hubo OOM, reducción de batch ni búsqueda de hiperparámetros. La corrida terminó las 100 épocas en **0,385 h (≈23,1 min)**; `best.pt` corresponde a la **época 87** según la mayor mAP50-95 de validation. Los pesos permanecen fuera de Git; SHA-256 de `best.pt`: `21766A9DC664FAC06DA3B0B457E0449F25E1696ACBF8E7E39993C4B42282083F` (5.455.514 bytes). `last.pt`, logs, dataset, contact sheet y videos diagnósticos también quedan fuera del repositorio.

| Conjunto / clase | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| Validation / `person` | 0,993 | 0,862 | 0,885 | 0,773 |
| Validation / `forklift` | 0,998 | 0,963 | 0,983 | 0,828 |
| Test único / `person` | 0,991 | 0,816 | 0,838 | 0,693 |
| Test único / `forklift` | 0,993 | 0,998 | 0,995 | 0,952 |

`best.pt` se eligió con validation y **test se evaluó una sola vez después**; no se ajustó el modelo con ese resultado. La mAP de test corresponde a este subconjunto sintético acotado, no a CCTV industrial. Cualquier entrenamiento futuro guiado por estos hallazgos requerirá tratar este test como ya conocido. Las métricas supervisadas usan el protocolo de validación de Ultralytics y no equivalen al umbral diagnóstico `confidence=0.10` de A/B/C.

Con `imgsz=640`, `confidence=0.10`, IoU `0.70` y los mismos videos SHA-256 ya identificados arriba, las regresiones conocidas dieron:

| Escenario | YOLO11n-COCO histórico | Detector adaptado | Lectura |
| --- | --- | --- | --- |
| A, fire | 1.088 cajas `person`; COCO sin clase `forklift` | 1.428 `person` y 368 `forklift` en 235/277 frames | Las 368 cajas `forklift` quedaron en el borde derecho/pared (`x_min>1800`) y son falsos positivos evidentes; un montacargas visible en cuadros revisados no fue encuadrado. El mayor conteo `person` no demuestra mayor precisión y se observan posibles cajas espurias. |
| B, near-miss | 302 `person`; ninguna clase explícita `forklift` | 300 `person` y 300 `forklift`, ambas presentes en 300/300 frames | La revisión de cuadros 0 y 150 confirmó cajas sobre persona y montacargas; confidence `forklift` 0,929–0,975 (media 0,961). |
| C, box-pickup | 361 `person`; 0/57 en frames 110–166; 360 observaciones/2 IDs y 58 frames sin track | 418 `person`, incluidos 57/57 en 110–166; ByteTrack sin cambios: 418 observaciones, un ID 0–417 y ningún hueco; 0 cajas `forklift` | Cuadros 110, 140 y 166 confirman la caja sobre la persona agachada y continuidad de ID, pero muestran también un montacargas visible que no fue detectado como tal. |

No se asignó la clase COCO ID 1 (`bicycle`) a `forklift`, ni se fabricó una métrica numérica comparable de montacargas para el modelo base. B demuestra detección diagnóstica de ambas clases y C mejora la detección/tracking de la persona; **A revela falsos positivos de `forklift` y A/C muestran montacargas visibles omitidos**, pese a las métricas elevadas del subconjunto test. Decisión: conservar `best.pt` como **candidato experimental standalone**, sin incorporarlo todavía a las reglas, Backend, Frontend ni esquema de eventos. Antes de integrar maquinaria al pipeline se necesita evaluar negativos y diversidad de escena/iluminación, incluidos montacargas pequeños o parcialmente visibles; no se realizó un segundo entrenamiento en esta iteración. Ninguno de estos resultados acredita validación industrial, rendimiento universal ni calidad formal de tracking MOT.

## Segundo piloto dirigido: detector v2 (no integrado)

Se reutilizaron exclusivamente train/validation de v1 y se añadieron otros runs/cámaras de los cuatro escenarios; el test de v1 permanece como benchmark histórico y **no** entró en el entrenamiento. El split final tiene **72/20/12 runs y seeds únicos** en train/validation/TEST2. Los 12 de TEST2 fueron reservados por metadatos antes de entrenar, sin solaparse con v1 ni A/B/C; **no se descargaron, inspeccionaron ni evaluaron**. Su plan final local tiene SHA-256 `5C0E127FC956E731E315BB31137BFC7CEF9320A7405D08530730188A562594DA`. Sustituciones técnicas por desalineación video/JSONL se hicieron dentro del mismo split y escenario, sin mirar predicciones. No se descargaron shards completos.

| Split | Runs | Imágenes | Cajas `person` | Cajas `forklift` | Imágenes sin `forklift` | Fondos puros |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Train | 72 | 1.390 | 1.518 | 806 | 584 | 37 |
| Validation | 20 | 404 | 402 | 239 | 165 | 6 |

El total entrenable es **1.794 imágenes**. Por escenario: train box-pickup/fire/collision/near-miss **342/220/338/490**; validation **104/60/100/140**. Se mantuvieron ejemplos de personas agachadas y se amplió la diversidad de cámaras/montacargas. La proporción sin caja `forklift` en el JSONL (42,0 % train; 40,8 % validation) supera el objetivo orientativo de 10–15 % porque el conjunto v1 ya contenía abundantes imágenes de esa categoría; no se eliminaron ni se fabricaron etiquetas para ajustar el porcentaje. Se distinguieron fondos puros de imágenes con `person` pero sin caja `forklift`; las observaciones objetivo sin caja utilizable (236/62) permanecieron excluidas del conjunto de candidatos negativos basado en la fuente.

La búsqueda con v1 a `confidence=0.10` revisó **431** imágenes de train (324 heredadas y 107 nuevas) y **1.980** instantes adicionales de sus videos, todos sin caja `forklift` en el JSONL: **cero candidatos positivos `forklift`** en ambos grupos. Por ello **no se incorporó ningún hard negative minado** ni se afirmó que se hubiera corregido esa clase de error por entrenamiento dirigido. En validation, 126 imágenes sin caja `forklift` en el JSONL produjeron 3 cajas falsas de v1 en 3 imágenes, todas sobre estructuras; estos ejemplos no se utilizaron para entrenar. Esta clasificación basada en la fuente no equivale a negatividad visual verificada. Los medios, manifiestos, resultados por frame y pesos permanecen fuera de Git.

Se entrenó **una sola versión v2**, otra vez desde `yolo11n.pt` original (SHA documentado arriba), no desde el `best.pt` v1: YOLO11n, dos clases, `imgsz=640`, `batch=8`, `seed=42`, 100 épocas máximas, `patience=20`, CUDA y optimizador automático (AdamW). Terminó las 100 épocas sin OOM en **0,465 h**; el `best.pt` de v2 corresponde a la época **94**, pesa **5.455.450 bytes** y tiene SHA-256 `ECB644BAEFAABBD6A884FC5DA18D56FA2CBBA03FF89D9C8FA61A67A2B0C41336`. El archivo sigue exclusivamente local y fuera del repositorio.

Ambos checkpoints se evaluaron sobre las **mismas 404 imágenes/641 cajas** de validation v2 con el protocolo de Ultralytics (P/R/mAP), sin atribuir estas métricas a A/B/C:

| Modelo / clase | Precision | Recall | mAP50 | mAP50-95 |
| --- | ---: | ---: | ---: | ---: |
| v1 / `person` | 0,963 | 0,803 | 0,837 | 0,671 |
| v2 / `person` | 0,965 | 0,821 | 0,853 | 0,696 |
| v1 / `forklift` | 0,990 | 0,967 | 0,992 | 0,864 |
| v2 / `forklift` | 0,982 | 0,979 | 0,992 | 0,862 |

La métrica separada de candidatos falsos `forklift` sobre las **mismas 126 imágenes sin caja `forklift` en el JSONL** a `confidence=0.10` empeoró: **v1: 3/126 imágenes, 3 cajas (2,38 %); v2: 11/126 imágenes, 11 cajas (8,73 %)**. Una revisión visual de los errores v2 los situó principalmente sobre estanterías/estructuras, no montacargas reales. La mejora parcial de mAP/recall no compensa este aumento; **v2 no supera el criterio de selección**. Por ello TEST2 se conserva ciego y sin métricas: ejecutarlo ahora gastaría un conjunto reservado en un modelo ya rechazado por validation.

Las regresiones diagnósticas conocidas usaron `imgsz=640`, `confidence=0.10`, IoU `0.70`, CUDA y ByteTrack sin cambios. **A (277 frames):** v2 emitió 1.677 cajas `person` y **0** `forklift`; eliminó las 368 cajas falsas de pared de v1, pero tampoco detectó el montacargas visible (revisión visual de cuadro 120). El aumento de cajas `person` no acredita mayor precisión. **B (300 frames):** `person` y `forklift` estuvieron presentes en 300/300 frames, 300 cajas por clase, como v1. **C (418 frames):** 418 cajas `person`, incluidas **57/57** en 110–166; ByteTrack mantuvo **418 observaciones, un ID continuo 0–417**, sin huecos, y hubo **0** cajas `forklift` pese al montacargas visible (revisión visual de cuadro 140). Estas regresiones no tienen ground truth de cajas/identidad y no reemplazan TEST2.

**Decisión:** no integrar v2 al Motor ni a reglas de maquinaria. Aunque A pierde el falso positivo sistemático, validation empeora en falsos `forklift` y A/C siguen omitiendo maquinaria visible. V1 y v2 quedan como artefactos experimentales locales. No se ajustaron umbrales, resolución, hiperparámetros ni ByteTrack después de observar los resultados; una iteración posterior requerirá otra decisión explícita y un plan de negativos representativos antes de consumir TEST2.

Una auditoría visual posterior y acotada de `fire`/`box-pickup` confirmó que la ausencia de caja `forklift` en `object_detection.jsonl` **no garantiza ausencia visual**. De 75 frames revisados en 15 runs, 29 requirieron una caja manual de montacargas, 27 fueron negativos verificados y 19 se excluyeron por ambigüedad o anotación fuente incompleta; no hubo montacargas correctamente anotados por NVIDIA en esa selección. El overlay separado conservó el SHA-256 de cada anotación fuente y exportó 56 imágenes (39 train, 17 validation) sin tocar los JSONL originales. Los positivos corregidos quedaron solo en train, por lo que el subconjunto aún no ofrece validación positiva independiente de esas apariencias. **No se entrena v3 ni se integra v1/v2**; TEST2 permanece reservado. Las anotaciones, imágenes y hojas de revisión son artefactos locales no versionados.

## Diagnóstico PERSON con video vertical real (sin cambio productivo)

`test3.mp4` (SHA-256 `58AE1BB11E050AD6A4D4E9CE6347742ED78EE1AE12F2A3BD3597CA1F1FF91864`) es una muestra manual **de desarrollo**, 360×640, 30 FPS y 1.558 frames; no es un holdout ni representa validación operacional. Se compararon con CUDA y el mismo procesamiento por frame el checkpoint PERSON vigente (SHA-256 `21766A9DC664FAC06DA3B0B457E0449F25E1696ACBF8E7E39993C4B42282083F`) y el YOLO11n-COCO original (SHA-256 `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`), filtrando `person`, con `imgsz=640`, confidence `0.10`, NMS IoU `0.70` y ByteTrack sin cambios. El pipeline vigente también emitió 1.308 cajas `forklift` en 1.190 frames; no se modificó ni comparó el specialist de maquinaria.

| PERSON | Checkpoint vigente | YOLO11n-COCO |
| --- | ---: | ---: |
| Cajas en `test3` | 131 | 2.950 |
| Frames con ≥1 caja / 1.558 | 117 | 1.321 |
| IDs de track emitidos | 4 | 32 |
| Observaciones de track | 48 | 1.694 |
| Frames con ≥2 cajas | 13 | 838 |
| Frames con alguna pareja de cajas IoU ≥0,4 | 4 | 536 |
| Regresión B: cajas / frames con `person` | 300 / 300 | 302 / 300 |
| Regresión B: IDs / observaciones | 1 / 300 | 1 / 300 |

Se inspeccionaron **33 frames** espaciados cada 50 frames y el último (0–1.550, 1.557), en láminas con fuente, predicción vigente y predicción COCO. La inspección muestra `PERSON_VISIBLE_MISSED` con el checkpoint vigente para el trabajador de pie y `PERSON_PARTIALLY_OCCLUDED_MISSED` para el operador dentro de la cabina, por ejemplo en 0, 100, 400 y 800. COCO recupera ambos en muchos de esos cuadros; 750 presenta detección del trabajador con ambos modelos. En 1.000–1.050 el operador es pequeño/parcialmente tapado y ambos modelos omiten la detección: el caso es **ambiguo por visibilidad**, no una prueba de que el objeto no exista. En 1.400 el checkpoint vigente presenta una caja aparente sobre parte del montacargas, mientras COCO detecta al operador pero muestra cajas redundantes. Otras láminas de COCO exhiben cajas superpuestas sobre la misma persona; el conteo de 536 frames es un **indicador geométrico**, no un recuento formal de falsos positivos ni una métrica de precisión. Algunas cajas próximas pueden corresponder a personas distintas. No hay ground truth exhaustivo de `test3`.

La distribución de confidence de COCO (p10/mediana/p90 ≈ 0,117/0,294/0,777) motivó un análisis **solo post hoc** de sus cajas guardadas, sin reejecutar inferencia ni tracking: al filtrar por `0,25`, persisten 1.642 cajas en 1.159 frames y 107 frames con pareja IoU ≥0,4; a `0,40`, 1.181 cajas en 1.008 frames y 10 frames con esa condición. En B, el filtro post hoc hasta `0,40` conserva al menos una caja `person` en 300/300 frames. Esto **no valida** un nuevo umbral, pues cambia las entradas de ByteTrack y puede perder personas reales; no se recalcularon tracks ni eventos para esos umbrales. Aumentar el confidence del checkpoint vigente tampoco resuelve sus omisiones: al filtrar sus cajas a `0,25`, solo quedan 60 frames detectados en `test3`.

**Decisión: `PERSON_PERCEPTION_REQUIRES_FURTHER_REVIEW`.** COCO mejora visiblemente la cobertura de `test3` y preserva la regresión conocida B al umbral original, pero el volumen de cajas duplicadas/aparentemente espurias y la fragmentación de IDs no permiten afirmar aún que reduzca falsos positivos, conserve downstream o sea una sustitución inequívoca. Se mantiene el checkpoint y los parámetros productivos sin cambios. La siguiente evaluación debe usar anotaciones humanas de diversidad real, incluyendo operadores parcialmente ocluidos, negativos verificados y más de una escena; un eventual PERSON v2 requiere completar esos datos antes de entrenar. Los JSONL, MP4 anotados y láminas de este diagnóstico permanecen fuera de Git. TEST2 y REAL_HOLDOUT_V2 no se consultaron.

## Readiness formal PERSON — 23-10-2026 (corte previo a campaña; sin entrenamiento)

Se auditó el material PERSON local sin promover etiquetas de origen ni preanotaciones a ground truth humano. El inventario reproducible y el paquete de imágenes están fuera de Git, en `Operix-experiments/person-v2-evaluation-readiness-2026-10-23/`; `readiness/person-v2-readiness.json` tiene SHA-256 `173B428218D7D47E5D118BE2F5F9957096079BE07D56ED9AFA0809ADBB311A01`. Su auditoría se reproduce con `engine/scripts/audit_person_readiness.py` usando el manifiesto candidato final de 640 imágenes y el manifiesto del paquete humano previo de 225 imágenes. Los paths absolutos de esos manifests son operacionales/locales y no se versionan.

| Fuente local | Imágenes pertinentes | Anotación y procedencia | Uso admisible hoy |
| --- | ---: | --- | --- |
| NVIDIA warehouse, piloto v1/v2 y selección final | 1.545 v1; 1.794 v2; **500** sin SHA duplicados en el candidato final | Sintética, OpenMDW-1.1, agrupación por run; cajas de fuente, no verificación humana exhaustiva. Los exports v1/v2 se solapan. | Desarrollo/entrenamiento candidato, sujeto a auditoría de cobertura; no ground truth humano formal. |
| CrowdHuman `train01` | 606 seleccionadas inicialmente; **120** en candidato final, 668 cajas visibles | Fuente real general, anotación publicada y curación parcial; procedencia a nivel de imagen sin escena/secuencia verificable. Uso educativo/investigación no comercial; imágenes no redistribuibles. | `HUMAN_PARTIAL`: revisar cobertura completa y agrupación antes de evaluación o split protegido. |
| Keremberke forklift | 421 disponibles; **20** negativos completos revisados en candidato final | CC BY 4.0; procedencia débil de escena; 401 positivos/otros pendientes de revisión completa. | Solo los 20 negativos son `HUMAN_VERIFIED`; cero cajas `person` verificadas. |
| Open Images industrial | 231 auditadas; 55 cajas `person` publicadas en 36 imágenes; 91 priorizadas para revisión | Cobertura incompleta demostrada; licencia por imagen. | Cero imágenes admitidas como positivo o negativo de evaluación hasta reanotación completa. |
| Paquete humano previo | 225 imágenes: 20 negativos verificados, 99 pendientes de reanotación, 106 pendientes de revisión negativa | 418 cajas de preanotación (fuente/modelos) solo como ayuda; sin export CVAT corregido. | **205 imágenes** requieren revisión humana; no hay split aprobado. |
| TEST3 | 1.558 frames de video de desarrollo; nuevo paquete de **48** imágenes | Video real local de procedencia/licencia externa no documentada; 32 frames temporales uniformes y 16 adicionales. Se registran 7 anclas de revisión de oclusión, 3 señales `GENERIC_ONLY`, 3 `BOX_DIVERGENCE`, 3 `CURRENT_POSITIVE` y 2 `BOTH_EMPTY_AMBIGUOUS`; dos anclas coinciden con la muestra uniforme. Son categorías de muestreo, no etiquetas. | `UNANNOTATED`, grupo único de video, **solo desarrollo**, no test ciego ni redistribución. |

El candidato final local suma **640 imágenes**, **1.203 cajas `person` de origen no verificadas exhaustivamente**, 20 negativos completos verificados y **244** `source_group` declarados (104 runs NVIDIA, 120 IDs CrowdHuman y 20 IDs Keremberke). Hay 500 imágenes con agrupación robusta por run y 140 con agrupación débil. Los splits son *candidatos*, no congelados: 514 train, 84 validation y 42 holdout tentativo. La comprobación automática encontró **0** SHA duplicados en esas 640 filas, **0** grupos cruzando esos splits y **0** imágenes faltantes; esto no demuestra independencia de escenas para CrowdHuman/Keremberke ni ausencia de duplicados perceptuales. El audit previo de exports superpuestos encontró 1.326 grupos duplicados exactos y 208 candidatos perceptuales; sus 339 cajas fuera de límites y 10 microcajas pertenecían al conjunto bruto auditado, no se atribuyen automáticamente a las 20 imágenes humanas verificadas. Las 20 imágenes negativas actuales decodifican, coinciden con dimensiones/SHAs de manifiesto, tienen hashes distintos y ninguna caja `person` declarada. No hay aún positivos HUMAN_VERIFIED para medir recall/F1.

El nuevo paquete de TEST3 se reproduce con `engine/scripts/build_person_eval_pack.py` usando video y JSONL diagnósticos previos, con verificación obligatoria del SHA del video. Contiene `images/`, `manifest.csv`, `instructions.md`, `source-groups.json` y `sha256-manifest.txt`, sin labels. SHA-256 de `manifest.csv`: `0ED90115998EA0C8111E37ACBBB8CB370993F6045D4CA9A8E14738A76B367A5E`. Los 48 PNG son únicos y conservan 360×640; el protocolo instruye a revisar personas pequeñas, ocluidas, operadores, truncamientos, negativos de frame completo y casos ambiguos, exportando finalmente anotación humana COCO/CVAT y registro por imagen. **TEST3 ya influyó en la investigación**, de modo que su futura anotación no lo convertiría en evaluación bloqueada independiente. Además, sus 48 imágenes pertenecen a **un solo video/source group**.

Se agregaron funciones puras y pruebas sin GPU para muestreo determinista, lectura consecutiva de JSONL, auditoría de SHA/grupos y matching PERSON uno-a-uno con IoU ≥0,5, más TP/FP/FN, precision, recall, F1 y una grilla de thresholds. El matching cuenta una segunda caja sobre la misma persona como FP. El protocolo futuro exige congelar grupos independientes, anotar todos los objetos visibles, separar calibración de evaluación, fijar por adelantado la grilla de confidence y evaluar el split final una vez. **No se corrió esa grilla ni se reportan AP50, TP/FP/FN, precision/recall/F1 reales**: falta ground truth suficiente. Tampoco se repitieron inferencia, tracking ni análisis operacional. Los conteos de TEST3 y la regresión B anteriores siguen siendo diagnóstico descriptivo, no métricas supervisadas. El checkpoint PERSON vigente (`21766A9DC664FAC06DA3B0B457E0449F25E1696ACBF8E7E39993C4B42282083F`) y YOLO11n-COCO (`0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`) son candidatos a comparación futura con `imgsz=640` y mismo protocolo, sin ganador cuantitativo ni threshold nuevo elegido.

**Decisiones:** `PERSON_EVALUATION_BLOCKED_BY_GROUND_TRUTH`; `PERSON_MODEL_REQUIRES_MORE_DATA`; `PERSON_V2_BLOCKED_BY_ANNOTATION`. Para desbloquear: revisar las **205 imágenes** pendientes del paquete previo, completar anotaciones positivas industriales reales de múltiples grupos/escenas (incluidos operadores y oclusiones), verificar negativos adicionales, fijar un conjunto de evaluación externo y separar train/calibración/evaluación por fuente, run o secuencia. La procedencia débil y la dominancia sintética del candidato son riesgos adicionales; una validación/holdout independiente no puede declararse a partir de 514/84/42 candidatos. Solo entonces se congelaría un protocolo de entrenamiento v2; **no se fijan ahora base, batch, epochs ni regla de selección de modelo**. No se entrena PERSON v2, no se sustituye el detector productivo y no se cambia FORKLIFT, ByteTrack ni reglas. TEST2 no se abrió ni utilizó; REAL_HOLDOUT_V2 no se usó para tuning.

## Campaña humana PERSON preparada — 23-10-2026

**Decisión de campaña: `PERSON_GROUND_TRUTH_CAMPAIGN_READY`** para comenzar anotación, **no** `PERSON_V2_READY_TO_TRAIN`. Se consolidaron sin duplicados SHA las 225 imágenes del paquete humano anterior y los 48 frames de TEST3: **273 imágenes**, **226 `source_group` declarados**, 20 negativos de frame completo verificados, **0 positivos humanos verificados** y **253 imágenes pendientes**. Los 225 grupos de Keremberke son solo identificadores a nivel de imagen (procedencia de escena/secuencia **débil**); los 48 frames de TEST3 comparten `TEST3_VIDEO`, agrupación temporal fuerte pero procedencia/licencia externa no documentada. TEST3 es desarrollo ya inspeccionado con ambos modelos, no evaluación ciega.

La campaña local está en `Operix-experiments/person-ground-truth-campaign-2026-10-23-balanced/`, fuera de Git. SHA-256 de `00-inventory/consolidated-images.csv`: `5DBE174C8E9B20E3AB5CAAA96A25C27399B6906A4C34DE7637AD3AA6B3460157`. Cada tarea contiene `images.zip`, manifiesto y plantillas vacías de revisión/confirmación; únicamente las tareas `PERSON-REVIEW-*` contienen `PREANNOTATION_ONLY.coco.zip` (389 propuestas repartidas 195/194), con el mismo formato COCO usado previamente. Las propuestas **no** cambian el estado de anotación. Se verificaron los 253 archivos de imagen empaquetados contra sus SHA; los 20 negativos ya verificados permanecen en inventario sin reanotación.

| Tarea CVAT | Imágenes | Alcance |
| --- | ---: | --- |
| `PERSON-REVIEW-01` / `02` | 50 / 49 | Positivos publicados/preanotados pendientes de revisión/corrección humana completa. |
| `PERSON-NEGATIVE-REVIEW-01` / `02` | 53 / 53 | Candidatos a negativo: revisar todo el frame y agregar cualquier persona omitida. |
| `TEST3-PERSON-REVIEW` | 48 | Un solo grupo de video real de desarrollo, sin labels previos en el paquete. |

`PERSON-ANNOTATION-GUIDELINES.md` define persona visible, operador distinguible dentro de forklift, oclusión, truncamiento, ambigüedad, negativos y cajas ajustadas al cuerpo visible. `ANNOTATION-WORKFLOW-FOR-DANIEL.md` da los pasos mínimos en CVAT. Un export COCO **no** se marca automáticamente HUMAN_VERIFIED: el procesador requiere por tarea ZIP, revisión por imagen con revisor/fecha y un recibo de finalización humana cuyo SHA coincida con el export. Después ejecuta QA de cajas/clases/coordenadas/duplicados, normaliza labels, actualiza manifests y progreso, y solo propone splits por `source_group`. El freeze de evaluation es explícito, con hashes y sin sobrescritura. Las herramientas reproducibles están en `engine/scripts/prepare_person_ground_truth_campaign.py`, `process_person_cvat_export.py` y `freeze_person_evaluation.py`; se probaron sin modelos reales.

En el momento de preparar los paquetes, el gate local estaba **bloqueado**: 0 positivos HUMAN_VERIFIED, 20 negativos frente a un piso operativo **provisional y configurable** de 30, 0 grupos positivos con procedencia fuerte, 253 revisiones pendientes, 0/5 tareas exportadas/completadas y ningún evaluation set congelado. El piso de 30 solo exige mejorar el baseline de 20, **no** demuestra representatividad; el mínimo de tres grupos independientes es estructural para train/calibration/evaluation y tampoco garantiza diversidad. La carpeta local contiene el reporte de criterios y `ADDITIONAL_PERSON_DATA_NEEDED.md`: hacen falta escenas industriales reales independientes, otras cámaras/iluminaciones/escalas, oclusiones, operadores y negativos difíciles con procedencia y permiso claros. En esta preparación no se ejecutó entrenamiento, inferencia, comparación formal, calibración, cambio productivo ni uso de TEST2 o REAL_HOLDOUT_V2.

## Reclasificación del set YouTube y holdout final v2 — 23-10-2026

Por decisión humana, test4–test8 pasan a **`PERSON_YOUTUBE_DIAGNOSTIC_SET_V1`**:
`DIAGNOSTIC_ONLY`, `NOT_LOCKED_EVALUATION`, `PROVENANCE_PARTIAL`,
`RIGHTS_UNVERIFIED`. Se conservan los **68 frames, 43 positivos, 25 negativos,
89 cajas**, exports humanos, URLs, familias A={001,003,005}, B={002}, C={004},
hashes, recibos, QA y manifests. No se mueve la carpeta histórica para evitar
romper referencias. El nuevo `dataset-status.json` y la metadata de ingestión
reemplazan metodológicamente el estado candidato de los artefactos históricos,
que se preservan; las cinco versiones anteriores de metadata quedan archivadas
localmente con un inventario de hashes. No hubo pérdida ni repetición de anotación.

La reclasificación excluye este set de locked evaluation, selección de threshold
o ganador final y métricas finales del sistema. Podrá servir como diagnóstico,
stress testing o comparación cualitativa/secundaria, sujeto a resolver el uso
permitido; la decisión no concede derechos ni autoriza distribuir el material.

Se prepara fuera de Git `Operix-experiments/person-independent-holdout-v2-2026-10-23/`,
vacío y separado del set diagnóstico. El [protocolo vigente](PERSON-INDEPENDENT-HOLDOUT-PROTOCOL.md)
prioriza grabaciones originales autorizadas o licencias externas verificadas;
requiere fuente/familia, autor, cámara, contexto general y respaldo de permiso.
El gate final exige derechos confirmados mediante allowlist, al menos tres familias
independientes (preferiblemente 4–5), revisión humana completa, QA limpio y cero
leakage contra campaña/TEST3, set diagnóstico y registro completo de entrenamiento/
desarrollo. Este último registro y las atestaciones se completarán antes del freeze.
El tooling rechaza expresamente el set diagnóstico y registra familias, versión de
protocolo y auditoría de exclusiones en un futuro freeze. No se ha congelado material.

**Decisiones: `PERSON_YOUTUBE_DIAGNOSTIC_SET_PRESERVED` +
`PERSON_FINAL_HOLDOUT_ACQUISITION_READY`.** Se pueden recibir nuevas fuentes válidas;
la adquisición lista no implica datos disponibles ni evaluación habilitada. No se
ejecutó ningún modelo, entrenamiento ni calibración. TEST2 y REAL_HOLDOUT_V2 intactos.
Las secciones siguientes conservan la trazabilidad de los cortes anteriores; sus
estados de candidato/holdout quedan sustituidos por esta reclasificación.

## Procedencia YouTube del holdout PERSON — 23-10-2026

El usuario confirmó que los cinco clips proceden de material de la [playlist pública](https://www.youtube.com/playlist?list=PLqtixnvhnjREmrai3YUMTTjvZotRC5j9_). El origen local se actualiza a `YOUTUBE_PLAYLIST_SOURCE` como declaración de procedencia, separada de derechos y de independencia. La consulta pública con yt-dlp 2026.10.21 recuperó 78 entradas y un aviso de cuatro videos no disponibles. Se guardaron metadata, miniaturas y storyboards fuera de Git; no se descargaron videos de nuevo. Los siguientes mapeos tienen confianza visual alta por coincidencia de secuencias, cámara/rotulación y duración aproximada, sin equivalencia binaria demostrada ni offsets de recorte certificados.

| Clip / grupo | Fuente YouTube identificada | Canal | Posición observada en playlist | Familia conservadora |
| --- | --- | --- | --- | --- |
| test4 / 001 | [Forklift Accidents Caused by Moving Forward Fully Loaded — oJpLaoKgJ_g](https://www.youtube.com/watch?v=oJpLaoKgJ_g) | TEKNECT Global | No encontrada en la consulta actual | A |
| test5 / 002 | [View from a Forklift Driver's Perspective — nK6UGe1FwCI](https://www.youtube.com/watch?v=nK6UGe1FwCI) | WireCrafters | No encontrada en la consulta actual | B |
| test6 / 003 | [forklift accident pilkington nivala factory — ZjiIMWcxcWA](https://www.youtube.com/watch?v=ZjiIMWcxcWA) | mika Erä | 13 | A |
| test7 / 004 | [Forklift Personnel Basket Accident — lcXwyhdHtjM](https://www.youtube.com/watch?v=lcXwyhdHtjM) | Kyle Thill | 3 | C |
| test8 / 005 | [Funny Forklift Crash — 0iTtIk9jioY](https://www.youtube.com/watch?v=0iTtIk9jioY) | Snakeypeter | 16 | A |

Las posiciones describen el orden recibido en esta consulta, no una numeración histórica garantizada. La ausencia actual de las fuentes de test4/test5 impide confirmar su pertenencia exacta a la playlist; se identificaron mediante búsqueda pública adicional. Los cinco IDs de publicación son distintos. Sin embargo, el storyboard del montaje test4 contiene secuencias coincidentes tanto con test6 como con test8. Por ello, se establece la familia conservadora conectada **A = {001,003,005}**, B = {002}, C = {004}: **tres familias candidatas**, no cinco fuentes independientes demostradas. No se afirma que test6 y test8 sean una misma captura entre sí; se agrupan por la conexión de ambos con el montaje. Falta confirmar origen primario/cámara, URLs de adquisición y ausencia de solapamiento con desarrollo; el uploader no acredita por sí solo autoría de cada toma.

La metadata pública completa de los cinco videos devuelve `license=null`; no se verificó una declaración explícita de CC BY, dominio público o permiso. Se registra **`LICENSE_UNKNOWN` + `RIGHTS_UNVERIFIED`** para cada fuente. No se convierte la ausencia de etiqueta en una afirmación de licencia estándar. [YouTube explica](https://support.google.com/youtube/answer/2797468?hl=en) que la estándar es la opción predeterminada y que CC BY permite reutilización sujeta a condiciones; la publicidad de un video o su inclusión en una playlist no acredita permisos de uso de terceros. Los videos, frames y anotaciones continúan únicamente locales.

**Decisión actual: `PROVENANCE_PARTIAL` + `RIGHTS_UNVERIFIED`; `PERSON_HOLDOUT_BLOCKED_BY_PROVENANCE` y bloqueo adicional de derechos.** El mínimo estructural de tres familias es potencialmente alcanzable, pero su independencia primaria no está atestada. El protocolo exige procedencia/derechos verificables y atestación humana; el freeze actual rechaza `rights_or_license=UNVERIFIED`. No se cambia ni debilita ese gate. `source-independence-attestation.json` conserva la atestación pendiente, incorpora URLs, IDs, canales, posiciones, familias y límites de evidencia. No se ejecutó freeze, inferencia, evaluación, benchmark ni entrenamiento; las cajas humanas, detector y parámetros permanecen intactos. La sección siguiente conserva el corte anterior de QA y su hash histórico; el nuevo mapeo de familias lo actualiza explícitamente.

## Holdout PERSON nuevo: anotación cerrada, freeze pendiente — 23-10-2026

Los cinco exports COCO de `HOLDOUT_PERSON_001` a `005` se procesaron tras confirmación humana explícita `FULL_FRAME_HUMAN_REVIEW_COMPLETED`, revisor `DPBascur`, sin modificar las cajas humanas. Los artefactos permanecen fuera de Git en `Operix-experiments/person-independent-holdout-2026-10-23/`. Se generaron recibos, revisión por imagen, labels normalizados, manifests verificados y QA.

| Grupo | Frames | Positivos | Negativos | Ambiguos | Cajas person | SHA-256 del export |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| `001` | 16 | 12 | 4 | 0 | 22 | `1779E79988454A59050D16F9819671DDC6A5155E4444DD7027D04DF7B18C7F71` |
| `002` | 12 | 8 | 4 | 0 | 26 | `C745F5A57E22F8D829EFF48EB5554A742283BE089FDF754FBFEF161353AC1F62` |
| `003` | 12 | 4 | 8 | 0 | 4 | `AB84212341B42C84889DD4AFB541AE0207EBF3E84825C4D2701F7673F880F9FD` |
| `004` | 12 | 3 | 9 | 0 | 3 | `449C8B2897D77497C860916BB8DE7A5CF74052FE0673818C8E8B7FDCF504A97A` |
| `005` | 16 | 16 | 0 | 0 | 34 | `5E93A1B73FCAACD906C6F1FBE503F32BB4E6F8BA319DD12C366CA6ECF5F33F15` |

Total: **68 frames, 43 positivos, 25 negativos, 0 ambiguos, 89 cajas y 25 frames con múltiples personas**. QA estructural: cero bloqueos por clases, dimensiones, cajas, entradas duplicadas, imágenes faltantes/inesperadas, revisión y recibos. Los hashes de videos, frames, exports, labels y manifests coinciden. Hay cero SHA de video repetidos y cero SHA de imagen repetidos dentro del holdout. La intersección de hashes de las 68 imágenes con las 273 imágenes de `person-ground-truth-campaign-2026-10-23-balanced/final/verified-manifest.csv` es **cero**; tampoco coinciden sus IDs de grupo. Esta comprobación incluye los registros de desarrollo TEST3 de aquella campaña, sin abrir videos ni ejecutar modelos. La ausencia de duplicados exactos no acredita independencia de escena ni descarta versiones recortadas, reescaladas o relacionadas con otros datos de entrenamiento.

**Bloqueos de procedencia y derechos:** `source-independence-attestation.json` continúa sin atestación humana; origen/cámara y `rights_or_license` siguen sin verificar. `001` (`test4`, montaje) y `003` (`test6`) presentan una relación probable de toma exterior compartida: clasificación `INDEPENDENCE_UNRESOLVED`, con agrupación conservadora propuesta en una misma familia hasta confirmación. Las otras tres familias también requieren confirmación; no se declaran cinco grupos independientes. La propuesta provisional es `{001,003}`, `{002}`, `{004}`, `{005}`, no un mapeo final aprobado. Todos mantienen `HOLDOUT_ONLY` y acceso a modelos deshabilitado; no se asignó ningún grupo a TRAIN/CALIBRATION ni se modificaron datasets anteriores.

**Decisión: `PERSON_HOLDOUT_BLOCKED_BY_PROVENANCE`, con bloqueo adicional `RIGHTS_UNVERIFIED`.** El estado estructural del tooling es `PERSON_HOLDOUT_READY_TO_FREEZE`, pero no autoriza congelación metodológica. No se ejecutó freeze; no existe manifest final congelado ni SHA correspondiente. El reporte local `05-qa/global-audit.json` tiene SHA-256 `4DB8D35BAA038DA86EEF0E48450AB63EC5D29CAAA1FCBA4FC123F287D32E5B40`. Faltan únicamente las aclaraciones humanas de origen, relaciones de captura y derechos para decidir elegibilidad; no se inventan atributos de oclusión, operador o escala. No se preparó aún el benchmark posterior condicionado al freeze. No hubo inferencia, evaluación de detectores, calibración ni entrenamiento. TEST3 permanece excluido de locked evaluation; TEST2 y REAL_HOLDOUT_V2 no se consultaron.

## Campaña humana PERSON cerrada — 23-10-2026

Daniel confirmó revisión completa de las cinco tareas en CVAT. Cada export COCO se vinculó a su `review.csv` y `completion.json` local con revisor `DPBascur`, cantidad de imágenes según la tabla y SHA-256 del ZIP. El procesador generó labels normalizados y `final/verified-manifest.csv` fuera de Git, sin cambiar ninguna caja humana. El inventario original conserva SHA-256 `5DBE174C8E9B20E3AB5CAAA96A25C27399B6906A4C34DE7637AD3AA6B3460157`.

| Tarea | Imágenes | Positivas | Negativas | Cajas `person` | SHA-256 del export |
| --- | ---: | ---: | ---: | ---: | --- |
| `PERSON-REVIEW-01` | 50 | 50 | 0 | 106 | `F70DA9E6FA81E548F254FEB22A5FF88B9A9214BC634DBE6240F457CEAE4648B2` |
| `TEST3-PERSON-REVIEW` | 48 | 48 | 0 | 77 | `580E3FDFC43A9EC1D6CC790E07CFCA42F3FC6A4EF14BF011C4E5167303E8FF33` |
| `PERSON-REVIEW-02` | 49 | 49 | 0 | 118 | `9B4F589EC1D54A5A8938FF2DB110B167182E5CAEE6EB7C8CAE335F8DBD00027F` |
| `PERSON-NEGATIVE-REVIEW-01` | 53 | 3 | 50 | 3 | `88F8CA65BBFCC2B53AEC2514D2AC9BCD81F21E5F22A6F3043F0173D4A9F9A40F` |
| `PERSON-NEGATIVE-REVIEW-02` | 53 | 2 | 51 | 3 | `FFCBE2BDF4C4E0AC257289DA94F5A9D6DF4B07E7ACE3A6B2D7B45E5D9C62634A` |

**Resultado global:** 273/273 imágenes, 152 `HUMAN_VERIFIED`, 121 `VERIFIED_NEGATIVE`, 0 `REVIEW_AMBIGUOUS`, 0 pendientes y 307 cajas `person`. El nombre “negative review” designó el muestreo, no impuso un resultado negativo: cinco imágenes de esas dos tareas recibieron cajas humanas. QA: **0 blockers** en clases, imágenes, dimensiones, cajas, duplicados de anotación, estados, recibos y hashes; **0 SHA de imagen duplicados**. Como advertencias metodológicas persisten procedencia débil, TEST3 de desarrollo y ausencia de atributos auditados para oclusión severa/operador. Como información de inventario hay 226 `source_group` declarados: 225 IDs Keremberke por imagen con procedencia de escena/secuencia **débil** y un `TEST3_VIDEO` de 48 frames, con procedencia externa **desconocida**. Ninguno de esos 226 grupos acredita procedencia independiente fuerte para evaluación.

La auditoría de leakage confirma ausencia de duplicados exactos y que TEST3 permanece en un único grupo; **no** puede descartar imágenes de una misma escena Keremberke bajo IDs distintos. Un plan anterior proponía grupos Keremberke para `LOCKED_EVALUATION` basándose solo en IDs por imagen; se invalida expresamente. El tooling ahora exige elegibilidad explícita y procedencia de escena/grupo fuerte para proponer el split y para congelar evaluation. Los 225 registros Keremberke siguen marcados `PENDING_REVIEW` para elegibilidad de split, pese a tener cajas humanas: la revisión de cajas no les otorga independencia de escena. `06-split-planning/split-plan.json` queda `BLOCKED` (seed 42, sin asignaciones) y no existe `final/frozen-evaluation.json`. Por tanto no hay TRAIN/CALIBRATION/LOCKED_EVALUATION aprobados ni un holdout independiente congelado. TEST3 ya influyó en el desarrollo: solo sirve como diagnóstico, nunca como evaluación ciega. Las imágenes Keremberke podrían considerarse para entrenamiento con su limitación documentada, pero no se les asigna automáticamente un split protegido.

**Decisiones:** `PERSON_V2_BLOCKED_BY_PROVENANCE` y `PERSON_EVALUATION_BLOCKED_BY_INDEPENDENT_HOLDOUT`. La anotación humana está completa, pero no aporta independencia de escena ni habilita comparación formal CURRENT_PERSON_MODEL frente a YOLO11N_COCO_PERSON, calibración de thresholds ni entrenamiento v2. No se ejecutó comparación diagnóstica nueva ni inferencia. El siguiente hito requiere material positivo y negativo de fuentes/escenas independientes con procedencia verificable, licencia clara y separación previa de train, calibration y locked evaluation; solo entonces se fijaría una grilla de thresholds y se evaluaría el holdout una vez. Las 48 imágenes TEST3 no sustituyen ese holdout. Detector productivo, FORKLIFT, ByteTrack, reglas, TEST2 y REAL_HOLDOUT_V2 permanecen intactos.

## QA del holdout PERSON final tras anotación humana — 24-10-2026

Daniel Peña declaró completadas manualmente las cinco tareas nuevas, sin
preanotaciones, detector auxiliar ni asistencia de modelos. Se registra esa
declaración; no se afirma doble anotación independiente ni acuerdo entre
anotadores. La política `PERSON_VISIBLE_EXTENT_HUMAN_V1` cuenta toda persona
distinguible, incluyendo operadores visibles y oclusiones reconocibles, usando
extensión visible y cajas separadas para personas superpuestas. Un frame revisado
sin personas es negativo válido. No se alteró ninguna caja humana.

| Familia | Frames | Positivos | Negativos | Cajas `person` | Multipersona | Máximo/frame |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| `HOLDOUT_PERSON_101` | 20 | 12 | 8 | 36 | 6 | 7 |
| `HOLDOUT_PERSON_102` | 20 | 17 | 3 | 54 | 12 | 10 |
| `HOLDOUT_PERSON_103` | 12 | 11 | 1 | 20 | 9 | 2 |
| `HOLDOUT_PERSON_104` | 20 | 14 | 6 | 33 | 7 | 7 |
| `HOLDOUT_PERSON_105` | 20 | 13 | 7 | 25 | 8 | 4 |
| **Total** | **92** | **67** | **25** | **168** | **42** | **10** |

| Export original | Bytes | SHA-256 |
| --- | ---: | --- |
| `101/annotations.zip` | 9.588 | `236E6B436719ACB9C6745C1799659F93DDD42AF92766ADDD9CE0A5FD9FB4085A` |
| `102/annotations.zip` | 12.806 | `002E6800DC82BC64CF5838435B2140245034D737162259C57A6595B0846AB0E9` |
| `103/annotations.zip` | 5.670 | `36272918C3FD47DB6809496C83397EA723B3172833410FFB476F964A1D3FB599` |
| `104/annotations.zip` | 9.092 | `4EF768035982E726EDD70057DD3C978DD51D2C611B88B78AF9AB64BAB64F1EF9` |
| `105/annotations.zip` | 7.721 | `4773C504ECD64F09534D10E5377747AF88AF6B103EC3B92594A26C89F4C4D67B` |

Los cinco ZIP pasan CRC y contienen solo `annotations/instances_default.json`.
Extracción separada, sin sobrescribir los originales. Categoría única `person`,
sin categorías sin uso; IDs, referencias, nombres, cobertura y dimensiones
conciliados contra manifests y cabeceras PNG, sin decodificar ni visualizar
imágenes. Geometría: **168/168 válidas**, finitas, áreas positivas y límites
estrictos; no fue necesaria tolerancia de serialización. Cero cajas duplicadas
exactas o casi exactas según el criterio local documentado: IoU ≥0,995 y diferencia
máxima de coordenadas xywh ≤0,5 px. No hubo NMS, fusión ni eliminación de cajas.

Flags informativos: **38 `EDGE_CLIPPED`** (distancia al borde ≤1 px),
**3 `VERY_LARGE_BOX`** (área superior al 50 % de la imagen),
0 `VERY_SMALL_BOX` (lado mínimo <8 px o área relativa <0,0005),
0 `HIGH_OVERLAP` (IoU entre cajas ≥0,7). Son marcas geométricas para revisión,
no errores automáticos ni atributos semánticos verificados visualmente.

**Bloqueo encontrado:** `HOLDOUT_PERSON_101_frame_000145.png` y
`HOLDOUT_PERSON_104_frame_000000.png` comparten SHA-256
`2721C914AD7642092296F03B8C58BF60C9A175B02E7271C765C715CACE9F1937`.
Ambos son negativos humanos, de 1024×576, sin cajas: no hay contradicción entre
anotaciones. Son **92 registros y 91 imágenes distintas por hash**. El gate
vigente de `freeze_person_independent_holdout.py` rechaza frames idénticos entre
grupos. Se conserva `STOP_FREEZE`; no se interpreta esa coincidencia como prueba
de una misma captura ni se modifica el gate, sampling o contenido para forzar PASS.

Provenance: las cinco familias corresponden a los assets DVIDS 386340, 580995,
946394, 750886 y 792809. Videos, paquetes, manifests, índices y hashes de frames
coinciden con la adquisición archivada. Se verificaron hashes de las páginas
individuales y de la página de copyright, y sus declaraciones archivadas
`PUBLIC_DOMAIN_VERIFIED`. Se mantienen las restricciones y atribuciones originales:
no se afirma permiso individual, model releases ni renuncia a derechos de imagen,
marcas o publicidad. No se descargó de nuevo ninguna fuente.

Independencia documental: **39 manifiestos, 16.180 filas** —incluyen repeticiones
entre inventarios— de datos candidatos/entrenamiento/desarrollo, campaña humana,
YouTube diagnóstico y TEST3 vía metadata archivada. **Cero coincidencias** en
hashes disponibles, IDs de fuente/grupo/familia o referencias DVIDS registradas.
9.897 filas disponen de hashes y forman el registro local consolidado; los
manifests sintéticos sin hashes se contrastaron por identidad de fuente/run.
Esta comprobación no acredita independencia de escenas transformadas, completitud
universal del inventario ni ausencia en preentrenamiento de terceros. La política
original sigue intacta y sin atestación completa de cobertura training/development
y no acceso previo de modelos; no se elevó automáticamente a PASS.

Artefactos locales bajo
`Operix-experiments/person-independent-holdout-v2-2026-10-23/`:

- `05-qa/final-coco-audit/`: extracción original, auditoría, comparaciones,
  registro consolidado y atestación humana. QA SHA-256:
  `6A780AC413831EFA2E4B76D3DA465D0E12ABB68C6BE3E0E9C0B18C75886E1855`.
- `06-freeze/exclusion-register.json`: reserva las cinco familias y 92 frames
  contra training, development, calibration, threshold selection y model selection.
  Registro documental, no barrera del sistema operativo.
- `final/candidate-qa-manifest.json`: snapshot candidato con los 92 registros,
  hashes, política, conteos, provenance, herramientas y bloqueos; SHA-256
  `670E5314037043E78C0F2ADC46AC0D0F1B1ADE2316AFAE971EB11EF8BB4A998E`.
- `06-freeze/freeze-decision.json`: **`STOP_FREEZE`**, sin ID canónico de freeze.

El manifest candidato **no es un manifest congelado**. No se generó
`freeze.json` ni se congeló protocolo de matching/thresholds. Cualquier resolución
del duplicado o atestación pendiente requiere revisión explícita antes de volver
a decidir. No se elimina, sustituye ni añade ningún frame en esta tarea.

Validación: **12/12 pruebas sintéticas** del auditor local y **6/6 pruebas
existentes del tooling de holdout**, sin modelos reales. Los inputs auditados
conservan sus hashes después del QA. Motor, Backend, reglas y frontend no cambian
en esta fase documental. TEST2 y REAL_HOLDOUT_V2 no se abrieron; YouTube conserva
`DIAGNOSTIC_ONLY`, TEST3 `DEVELOPMENT_DIAGNOSTIC`.
**`PERSON_MODEL_EVALUATION_NOT_STARTED`**: no hubo inferencia, selección de modelos,
calibración ni entrenamiento. El freeze del conjunto y el del protocolo siguen
siendo pasos previos obligatorios a cualquier evaluación.
