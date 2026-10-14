# Etapa 3 — diagnóstico de pérdida de detección por cambio de pose en escenario C

## Pregunta, recurso y configuración

La [baseline multiescenario](etapa3-multi-scenario-baseline.md) observó que una sola persona visible en `warehouse_box_pickup`, cámara fija `cam_00`, pasa de ID 1 a ID 2 durante la acción de agacharse. El [tuning acotado de ByteTrack](etapa3-bytetrack-tuning.md) no redujo esa fragmentación. La hipótesis a contrastar fue una pérdida prolongada de la clase `person` antes de la reasociación, no una falla de continuidad atribuible únicamente al buffer.

- Video: `008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4`, **22.253.530 bytes**, SHA-256 `EABF44D7ABE50D1BF4824F238A9F0AC9DDC29419E10D66B89C6A92CB1B98329C`. Verificados **418 frames**, **30 FPS**, **1920×1080**; duración **13,933 s**. Procede del dataset sintético NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes, revisión `d5b88d3abcf659f304a107f4336b71b4e2159133`, bajo OpenMDW-1.1. No se descargó otro video.
- Pesos locales `yolo11n.pt` (YOLO11n-COCO), SHA-256 `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`, verificado antes de inferir. Windows 10 x64, Python 3.12.10, Ultralytics 8.4.146, CUDA/RTX 3070.
- Baseline: `imgsz=640`, `confidence=0.10`, `iou=0.70`, `device=cuda`; solo `person` llega a ByteTrack. Este mantiene `track_high_thresh=0.25`, `track_low_thresh=0.10`, `new_track_thresh=0.25`, `track_buffer=30`, `match_thresh=0.80`, `fuse_score=true`.
- Regla observada sin persistencia: `demo_zone_dwell` v1, `min_duration_s=2.0`, configuración de zona C ya documentada en la baseline. Ninguna corrida nueva publicó eventos a Backend/PostgreSQL.

Se procesaron los **418 frames consecutivos desde el inicio** en tres pasadas del mismo modelo cargado: `confidence=0.10`, luego `0.05` y `0.01`; cada pasada inició un ByteTracker y estado de regla independientes con sus valores originales. La ventana de inspección y registro de predicciones completas fue **90–185** (índices desde cero), con foco en **110–166**. La observación con menor umbral no modifica el default. Para cada frame de la ventana, el diagnóstico local conserva todas las cajas pos-NMS devueltas por YOLO antes del filtro `person`: clase, confianza, `xyxy`, tracks visibles y estado interno del tracker. No se dispone de logits ni propuestas anteriores a NMS; «salida cruda» aquí significa *salida multiclase de `predict` antes del filtro propio de Operix*.

La correspondencia con la persona real se verificó visualmente en frames representativos y por la región aproximada `x=775…910`, `y=400…704`; no se confundieron cajas `person` débiles sobre el montacargas u otras estructuras con la persona. Las predicciones de otras regiones se conservaron en el diagnóstico local, pero no se usan como evidencia de detección de este objeto.

## Curva temporal de la persona

La tabla muestra la mejor caja sobre **la persona visible** en la pasada diagnóstica `0.01`; `—` significa que no apareció caja `person` en esa región siquiera a ese umbral. La columna alternativa es la mejor caja `fire hydrant` superpuesta a la misma región, no una clase válida para la persona. La salida del tracker corresponde al baseline `0.10`.

| Frame | `person` en región | `fire hydrant` en región | Track visible |
| ---: | ---: | ---: | ---: |
| 90 | 0,873 | — | 1 |
| 95 | 0,858 | — | 1 |
| 100 | 0,859 | — | 1 |
| 105 | 0,832 | — (0,011 en diagnóstico) | 1 |
| 106 | 0,793 | — | 1 |
| 107 | 0,443 | 0,579 | 1 |
| 108 | 0,425 | 0,540 | 1 |
| 109 | 0,543 | 0,443 | 1 |
| 110 | — | 0,761 | — |
| 111 | — | 0,822 | — |
| 112 | — | 0,825 | — |
| 120 | — | 0,678 | — |
| 125 | — | 0,501 | — |
| 128 | 0,035 | 0,426 | — |
| 129 | 0,031 | 0,507 | — |
| 130 | 0,034 | 0,422 | — |
| 131 | **0,01493** | **0,389** | — |
| 132 | 0,082 | 0,729 | — |
| 133 | — | 0,766 | — |
| 134 | 0,066 | 0,730 | — |
| 135 | — | 0,803 | — |
| 140 | — | 0,864 | — |
| 145 | — | 0,888 | — |
| 150 | — | 0,744 | — |
| 155 | — | 0,718 | — |
| 160 | — | 0,758 | — |
| 165 | — | 0,797 | — |
| 166 | — | 0,753 | — |
| 167 | **0,41285** | 0,553 | —; ID 2 todavía no confirmado |
| 168 | 0,467 | 0,719 | **2** |
| 170 | 0,682 | 0,524 | 2 |
| 175 | 0,831 | — | 2 |
| 180 | 0,863 | — | 2 |
| 185 | 0,878 | — | 2 |

La caída no es gradual a lo largo de toda la pérdida: el score `person` visible permanece alrededor de 0,79–0,86 en 90–106, baja a 0,43–0,54 mientras comienza el agachamiento (107–109) y desaparece **abruptamente en 110** con el umbral base. Entre **110 y 166**, 57 frames consecutivos, el baseline no tiene ninguna detección `person` en el video, no solo en la región de interés. Con `0.01`, hay una caja débil sobre la persona únicamente en **128–132 y 134** (6/57 frames); la mínima observada allí es **0,01493 en frame 131**. En los otros 51/57 no hay caja `person` sobre la persona a `0.01`; esto no demuestra ausencia de respuesta del modelo por debajo de `0.01` ni de propuestas anteriores a NMS.

En cambio, la clase **`fire hydrant`** presenta una caja superpuesta a la persona en los **57/57 frames 110–166**, con score **0,38910–0,89657** en la pasada base. Aparece desde 107 mientras todavía existe `person` y persiste hasta aproximadamente 173. Es una *clasificación errónea observada* de la región, no una equivalencia semántica ni una salida admitida por el filtro `person` del Motor. También hay detecciones de `truck` sobre el montacargas y estructuras en otras regiones; no explican la pérdida del track de la persona. El conjunto COCO no incluye `forklift`.

La caja `person` de frame 109 mide aproximadamente `(775,445,909,703)` (ancho 134, alto 257 px); la caja débil de frame 132, `(785,507,908,697)` (ancho 123, alto 189 px), es más baja y pequeña. El área cae aproximadamente de 34,4 mil a 23,2 mil px² y la relación ancho/alto cambia de 0,52 a 0,65. En frame 167, la caja `person` válida reaparece como `(788,432,909,702)`, score 0,41285. Es un cambio geométrico compatible con el agachamiento y posterior incorporación, **no** una prueba causal por sí solo.

## Inspección visual

Se revisaron 105, 109, 110, 120, 140, 160, 166, 167, 168 y 170 sobre los frames reales. La persona viste rojo/beige y se desplaza cerca de la estantería derecha. En 105 ya inclina el tronco; en 109–110 se agacha más. En 120–140 permanece baja, con torso plegado y la cabeza menos distinguible de la silueta. En 160–166 vuelve progresivamente a una postura más alta y en 167–170 se yergue. La persona sigue visible en la imagen; **no se observó una oclusión completa** por otro objeto. La proximidad de estantería y cajas puede dificultar bordes, pero no se cuantificó una oclusión parcial suficiente para atribuirle causalidad. La caja alternativa `fire hydrant` sigue de cerca esa silueta durante el episodio.

La lámina local `pose-contact-sheet.png` muestra esos diez frames con recuadros mínimos: verde para `person` sobre la persona y ámbar para la caja alternativa `fire hydrant`. Su SHA-256 es `8B4297F581435EB8682B3061A8C4C94ACCE065936D9DFF3678E4119148C2714B`. El diagnóstico local por frame `diagnosis.json` (SHA-256 `0F699B1F10FF2A95FAF0067D61813BD611FCFC0A798222AD0D5609A8D6E29A56`) incluye todas las predicciones multiclase de 90–185 para las tres pasadas, incluso falsas cajas alejadas. **Ambos artefactos, el video, los pesos y los scripts locales de diagnóstico permanecen fuera de Git.**

## Detección frente a asociación y prueba controlada

| Confianza YOLO | Detecciones `person` / frames con alguna `person`, video completo | Cajas `person` sobre la persona en 110–166 | Cajas espurias `person` en otras regiones, 110–166 | Observaciones / IDs | Candidatos transitorios |
| ---: | ---: | ---: | ---: | ---: | --- |
| **0,10** baseline | 361 / 361 | **0** | 0 | 360 / 2 | 60/ID 1, 228/ID 2 |
| 0,05 diagnóstico | 423 / 388 | **2**, frames 132 y 134 | **27** | 360 / 2 | 60/ID 1, 228/ID 2 |
| 0,01 diagnóstico | 1.185 / 418 | **6**, frames 128–132 y 134 | **100** | 360 / 2 | 60/ID 1, 228/ID 2 |

Los conteos de `person` de `0.01` en 418/418 frames **no** significan continuidad de la persona: aparecen muchas cajas débiles en otras regiones (por ejemplo, sobre el montacargas). Las seis cajas pertinentes del episodio tienen score **0,01493–0,08152**, todas inferiores a `track_low_thresh=0.10`; en la versión de ByteTrack instalada, la segunda asociación exige estrictamente `score > track_low_thresh`. Así, bajar **solo** el umbral de YOLO no entrega esas cajas al mecanismo de asociación actual. No se observaron tracks ni candidatos adicionales en estas pruebas, pero el aumento de ruido de entrada es real. No se cambió ningún parámetro por ese resultado.

El ID 1 fue la última salida visible en frame **109**. El backend lo marcó perdido en **110**, lo conservó como perdido hasta **139** y lo marcó retirado en **140** con `track_buffer=30`. En frame **167** vuelve una caja `person` válida (0,41285), cuando ID 1 **ya está retirado**: no puede reasociarse bajo esta configuración. ByteTrack crea internamente ID 2 en 167, inicialmente sin confirmar, y lo emite tras la detección de **168**. Por tanto, el intervalo de **salida visible ausente es 110–167, 58 frames**; el intervalo de **detección `person` ausente con umbral base es 110–166, 57 frames**. Son dos magnitudes distintas.

La prueba previa con `track_buffer=90` mantuvo ID 1 como perdido al llegar a 167, pero tampoco lo reasoció; la [evidencia de tuning](etapa3-bytetrack-tuning.md) documenta el desplazamiento de la caja predicha respecto de la detección de retorno. Esto separa la **causa inicial** (pérdida/cambio de clase de la detección) de una **limitación adicional de asociación geométrica** al reaparecer. No se afirma que alargar el buffer o modificar el umbral solucione la secuencia.

## Diagnóstico, ReID y decisión provisional

**Diagnóstico con confianza alta para este clip:** el cambio de pose coincide con una pérdida abrupta y prolongada de la clase `person` y una clasificación alternativa sostenida como `fire hydrant` en la misma región. No es simplemente que `person` quedara un poco por debajo de `0.10`: solo hubo 6 cajas débiles pertinentes a `0.01` y 51 frames sin ninguna a ese umbral. La caja se reduce/deforma; no hay evidencia visual de oclusión completa. En el baseline, además, el track expira antes del retorno, por lo que la nueva detección genera ID 2. **Confianza media** al generalizar el mecanismo a otras escenas o atribuir el error exclusivamente a la pose: se analizó una muestra sintética, sin ground truth de identidad ni ablaciones de resolución/modelo.

ReID **no puede producir una detección faltante** durante 110–166. Una estrategia con apariencia podría ayudar *solo al retorno* de una detección válida si aún conserva un historial identificable; con el buffer base ID 1 ya fue retirado en 140. La posibilidad con mayor retención y ReID queda como hipótesis, no resultado: no se implementó BoT-SORT/ReID ni se garantizó reasociación.

**Camino provisional recomendado: E — investigar adaptación/fine-tuning del detector**, empezando por evaluar si el modelo y los datos de entrenamiento cubren la postura de recogida/agachamiento; no entrenar ni incorporar otro modelo en esta iteración. La razón es la clasificación errónea persistente y de confianza relativamente alta sobre una persona visible. Bajar la confianza a 0,05/0,01 no corrigió el tracking y añadió cajas espurias; cambiar solo ByteTrack tampoco resolvió la pérdida primaria. Cualquier alternativa futura requiere experimento y revisión separados antes de alterar defaults. Estos resultados no establecen precisión/recall, MOT ni validez industrial.
