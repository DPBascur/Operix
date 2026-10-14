# Etapa 3 — visualización de zonas y campaña acotada de ByteTrack

## Problema y baseline

La [campaña multiescenario](etapa3-multi-scenario-baseline.md) mostró zonas de evidencia con trazo y cabecera de depuración demasiado dominantes. También mostró distinta continuidad temporal con YOLO11n-COCO filtrado a `person`: A (`warehouse_fire_ceiling04.mp4`) emitió 8 IDs, 4 episodios de huecos internos y 15 frames de hueco; B (`forklift_human_nearmiss_ceiling00.mp4`) conservó 1 ID sin huecos; C (`008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4`) muestra una sola persona que desaparece del tracking durante 58 frames y reaparece como ID 2. Se usa **fragmentación observada**, no «ID switch» como métrica formal: no existe ground truth MOT de identidad evaluado en esta campaña.

Esta iteración no cambia el modelo de zona: `Zone.polygon` ya admite polígonos normalizados arbitrarios y la pertenencia geométrica sigue determinada por OP-36. Se modificó solo el render de evidencia/evento y se compararon parámetros del tracker en un diagnóstico local. Ni la regla ni la configuración predeterminada de ByteTrack se cambiaron.

## Visualización de zona

`OpenCvRenderer.render_zone` opera sobre una copia del frame y acepta la `Zone` existente. Dibuja su polígono real, no una caja envolvente: relleno de 8 % de opacidad y borde antialias de 2 px. La zona configurada normal usa cyan y la implicada en un candidato de evento usa ámbar; no se usa rojo ni se dibujan handles. La etiqueta muestra `Zone.name` y, para el evento, el `kind` de la regla y el índice de frame. Los identificadores `rule_id` y `zone_id` siguen en el candidato/JSON y en la API; la etiqueta los reemplaza visualmente por información legible. OpenCV Hershey translitera tildes a ASCII en el rótulo, sin alterar metadatos. Las cajas de tracks mantienen el espesor y contenido previos: ID temporal, clase y confianza.

La evidencia del evento dibuja primero la zona tenue y luego los tracks para conservar visibles las personas. Los polígonos **configurados actualmente** para A/B/C son rectangulares; el renderer respeta polígonos perspectivos si la configuración los define, pero no se cambiaron las zonas de esta campaña para aparentar perspectiva. No hay visualizador web ni edición interactiva.

Se comparó la captura anterior del evento C en frame 60 con `C-render-v2-event-60-1.png` generado localmente después del cambio: desapareció la cabecera de depuración en la parte superior, la etiqueta pasó al borde de la zona y la escena permanece visible bajo el relleno. La captura nueva tiene SHA-256 `F839978B0CD3DF321B551B8AEC0D43AA563B2E597C6AC7936821E81050882BB7`. `C-render-v2-normal-frame90.png` ilustra el estado cyan sin evento (SHA-256 `13D453E5D7186DF87C77A96F3F127A917BAE2CD0A00284DB130ED3076AD86A62`). También se revisaron las capturas ámbar en A frame 60 y C frame 228. **Las imágenes antes/después son diagnósticos locales; no se versionan ni se sustituyen retrospectivamente las evidencias históricas ya almacenadas.**

## Parámetros de ByteTrack

El adaptador `ByteTrackConfig` expone exactamente estos valores predeterminados; la implementación instalada es Ultralytics 8.4.146 con `lap==0.5.12`:

| Parámetro | Baseline | Efecto potencial |
| --- | ---: | --- |
| `track_high_thresh` | 0,25 | Separa detecciones de confianza alta para la primera asociación. Reducirlo puede llevar más cajas a esa etapa, pero no crea detecciones ausentes. |
| `track_low_thresh` | 0,10 | Límite inferior estricto para la segunda asociación de detecciones débiles; detecciones con score igual al límite no entran en esa etapa. |
| `new_track_thresh` | 0,25 | Confianza mínima para iniciar un track nuevo no asociado. |
| `track_buffer` | 30 frames | Tiempo máximo de conservación interna de un track perdido; no garantiza que una caja al reaparecer se asocie con él. |
| `match_thresh` | 0,80 | Umbral de costo de la primera asociación basada en geometría/IoU y, cuando está activado, score fusionado. |
| `fuse_score` | `true` | Combina score de detección con costo geométrico en la primera asociación; la segunda etapa usa IoU. |

El adaptador recibe detecciones ya filtradas a `person` y no dispone de apariencia/ReID. Ultralytics retiene tracks perdidos según `track_buffer`; solo devuelve tracks activos al Motor. La regla `zone_dwell` consume esas observaciones visibles y se rearma ante pérdida/ID nuevo; por eso una fragmentación puede producir un candidato adicional.

## Diseño experimental

Se probaron el baseline y **tres** variantes adicionales, cambiando un solo parámetro cada vez:

1. `base`: valores anteriores.
2. `buffer60`: solo `track_buffer=60`.
3. `buffer90`: solo `track_buffer=90`.
4. `high020`: solo `track_high_thresh=0.20`.

A es la escena densa con varias personas; C es el caso de pérdida al agacharse. B se conserva como control descriptivo del baseline (1 ID, sin huecos), sin repetirlo en este tuning acotado. En todas las corridas se mantuvieron los mismos MP4 y SHA-256 de la campaña multiescenario, YOLO11n-COCO y pesos fijados, CUDA/RTX 3070, `confidence=0.10`, `imgsz=640`, `iou=0.70`, filtro `person`, zonas A/C y regla `demo_zone_dwell` v1 con `min_duration_s=2.0`. Se creó un tracker nuevo para cada corrida; el detector se cargó una vez. La ejecución usó el orquestador real con un sink **en memoria** que capturó PNG locales, sin publicar candidatos a Django/PostgreSQL. Los ejemplos visuales se generaron sobre frames reales y permanecen fuera de Git.

## Resultados

| Escenario | Variante | Detecciones `person` | Observaciones | IDs | Huecos internos (episodios / frames) | Pérdida sin track entre IDs | Candidatos `(frame/ID)` | Tiempo / FPS efectivo |
| --- | --- | ---: | ---: | ---: | ---: | --- | --- | ---: |
| A | `base` | 1.088 | 644 | 8 | 4 / 15 | — | 60/1, 60/2, 134/13, 201/31 | 7,985 s / 34,689 |
| A | `buffer60` | 1.088 | 644 | 8 | 4 / 15 | — | 60/1, 60/2, 134/13, 201/31 | 5,504 s / 50,324 |
| A | `buffer90` | 1.088 | 644 | 8 | 4 / 15 | — | 60/1, 60/2, 134/13, 201/31 | 5,596 s / 49,499 |
| A | `high020` | 1.088 | 639 | 8 | 4 / 16 | — | 60/1, 60/2, 134/13, 201/31 | 5,647 s / 49,057 |
| C | `base` | 361 | 360 | 2 | 0 / 0 | frames 110–167: 58 | 60/1, 228/2 | 7,862 s / 53,166 |
| C | `buffer60` | 361 | 360 | 2 | 0 / 0 | frames 110–167: 58 | 60/1, 228/2 | 7,986 s / 52,340 |
| C | `buffer90` | 361 | 360 | 2 | 0 / 0 | frames 110–167: 58 | 60/1, 228/2 | 8,283 s / 50,463 |
| C | `high020` | 361 | 360 | 2 | 0 / 0 | frames 110–167: 58 | 60/1, 228/2 | 7,705 s / 54,251 |

Las 8 corridas terminaron y procesaron A 277/277 o C 418/418 frames. El sink local registró 4 candidatos en A y 2 en C en cada configuración; **no son nuevos eventos persistidos** ni evidencia de riesgo real. Las cifras de FPS no están balanceadas por warm-up/repeticiones: el baseline A corrió primero y fue más lento, por lo que no se interpreta que subir el buffer acelere el sistema. No se optimizó rendimiento.

### Causa observada de C y control visual

La inspección adicional de YOLO confirmó **57 frames consecutivos sin detección `person` (110–166)** mientras la persona se agachaba. El frame 167 volvió a contener una detección (`confidence≈0,413`), pero ningún track activo; en 168 se emitió ID 2. Con `track_buffer=90`, ID 1 todavía constaba como *lost* en 167 (no había expirado). Su caja predicha se había desplazado hacia abajo (`y≈606…857`), mientras la detección de retorno abarcaba `y≈432…702`; la primera asociación no recuperó ese ID y se creó uno nuevo. Por tanto, **alargar el buffer por sí solo no resuelve este caso**: la interrupción de detección y el cambio de geometría importan. Esta observación no prueba que otra estrategia de asociación vaya a funcionar.

Los resúmenes de A fueron iguales con buffers 30/60/90; `high020` perdió 5 observaciones y añadió un frame de hueco. En las capturas seleccionadas de A no se observó una fusión adicional evidente de dos personas, pero sin etiquetas de identidad no se puede descartar toda asociación errónea. Las imágenes diagnósticas de A frame 60 y C frame 170 para las cuatro variantes fueron idénticas byte a byte dentro de cada escenario, coherentes con la ausencia de cambio en esos puntos. Ninguna configuración probada satisface el criterio de mejora: reducir huecos o fragmentación sin pérdida de observaciones ni fusión visible.

## Decisión provisional y límites

Se **conserva ByteTrack baseline** (`track_buffer=30`, `track_high_thresh=0.25`) y no se propone modificar su default a partir de estos dos clips. El buffer más largo mantiene internamente un track perdido, pero no recuperó la identidad observable de C. B continúa siendo un escenario de una persona con un ID continuo; A sigue siendo la escena más densa y difícil. Una comparación posterior ByteTrack vs. un tracker compatible con ReID (por ejemplo, BoT-SORT) puede estudiar si la apariencia ayuda a reasociar después de la reaparición; **no se implementó ni sustituyó el tracker**. ReID tampoco puede aportar detecciones durante los 57 frames en que YOLO no detectó a la persona.

Los pesos actuales tienen 80 clases COCO: `person` es clase 0 y **no existe `forklift`**. B muestra visualmente un montacargas, pero el pipeline filtra y procesa solo `person`; no se declara tracking de maquinaria. Sigue pendiente una decisión posterior al feedback académico entre pesos públicos con `forklift`, fine-tuning o detector alternativo/open-vocabulary. No se entrenó ni descargó otro modelo aquí.

El material es sintético, acotado y sin ground truth MOT evaluado. Los conteos de IDs, huecos y candidatos son observaciones de estas corridas, no precisión de identidad ni métricas IDF1/MOTA/HOTA, y no se extrapolan a CCTV industrial real.

## Validación y artefactos

- Pruebas unitarias del renderer cubren polígono no rectangular, opacidad ligera, colores normal/evento, no mutación del frame, etiqueta a partir de metadatos y argumentos inválidos. La prueba de orquestación confirma que el candidato y PNG proceden del mismo frame real.
- El script de diagnóstico, las configuraciones locales B/C, resultados JSON, PNG antes/después, JSONL, MP4 y pesos quedan fuera del repositorio. No se alteraron detector, tracker, modelo de zona, regla, Backend ni Frontend.
- Suite completa del Motor, con integraciones reales de YOLO11/ByteTrack habilitadas: **154 tests ejecutados, 154 aprobados, 0 omitidos, 0 fallidos**.
