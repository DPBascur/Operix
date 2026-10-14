# Etapa 3 — resolución de inferencia YOLO11n ante pérdida por cambio de pose

## Objetivo y recurso fijo

Se evalúa **solo `imgsz`** para determinar si más resolución reduce la pérdida de `person` documentada en el [diagnóstico de pose del escenario C](etapa3-yolo-pose-loss-diagnosis.md): ID 1 visible hasta frame 109, sin detección `person` válida en 110–166 a `imgsz=640`, clasificación superpuesta como `fire hydrant`, regreso de `person` en 167 e ID 2 emitido desde 168. Reducir el umbral de confianza a 0,05/0,01 no corrigió ese episodio y añadió cajas espurias. No se cambian detector, pesos, defaults, tracker ni reglas.

Se reutilizó exclusivamente `008caa590c5e5b7b4bca_run_8_seed_4731920.cam_00.rgb.mp4` (`warehouse_box_pickup`, `cam_00`), **22.253.530 bytes**, SHA-256 **`EABF44D7ABE50D1BF4824F238A9F0AC9DDC29419E10D66B89C6A92CB1B98329C`**. Se confirmaron **418 frames**, **1920×1080**, **30 FPS**. Es una muestra sintética del dataset NVIDIA PhysicalAI WorldModel Synthetic Warehouse Operations Scenes; procedencia y licencia constan en la [baseline multiescenario](etapa3-multi-scenario-baseline.md). Video y derivados permanecen fuera de Git.

El mismo `yolo11n.pt` (YOLO11n-COCO), SHA-256 **`0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`**, se cargó una vez. Se mantuvieron `confidence=0.10`, `iou=0.70`, `device=cuda`, filtro estricto `person`; ByteTrack baseline (`track_high_thresh=0.25`, `track_low_thresh=0.10`, `new_track_thresh=0.25`, `track_buffer=30`, `match_thresh=0.80`, `fuse_score=true`); zona C y regla `demo_zone_dwell` v1 con `min_duration_s=2.0`. Entorno: Windows 10 x64, Python 3.12.10, Ultralytics 8.4.146, RTX 3070 de 8 GiB. Las tres ejecuciones recorrieron **todo el video desde frame 0**, con tracker, acumulador espacio-temporal y RuleEngine nuevos en cada una. Se registraron candidatos **solo en memoria**; no se publicó a la API ni a PostgreSQL.

## Método de observación

Se compararon `imgsz=640` (baseline), `960` y `1280`, sin modificar otra variable. La ventana detallada fue **frames 90–185** y el episodio crítico **110–166**. Se conservaron fuera del repositorio todas las predicciones multiclase pos-NMS antes del filtro `person` para cada frame de esa ventana, sus clases, confidencias y `xyxy`, además de salidas de tracking. «Salida cruda» no significa logits ni propuestas anteriores a NMS. La persona visible se identificó por inspección visual y por centro de caja en la región aproximada `x=740…940`, `y=350…760`; las cajas débiles de otras regiones no se atribuyeron a ella. La zona de análisis es solo diagnóstica, no altera la zona operacional de la regla.

El pipeline medido fue **lectura OpenCV → YOLO11n → filtro `person` → ByteTrack → variables espacio-temporales → RuleEngine → `EventCandidate` transitorio**. No incluye renderer, PNG de evidencia, JSONL, escritura de video, red ni persistencia. La ejecución inicial, en orden 640→960→1280, incluyó arranque en frío y produjo FPS no comparables directamente (**41,830 / 51,110 / 48,905**). Para comparar costo se calentó el mismo modelo con 20 predicciones por resolución y se efectuaron **dos recorridos completos por tamaño** en orden balanceado `640→960→1280→1280→960→640`, sincronizando CUDA antes y después de cada medición. El FPS informado abajo es `836 frames / suma de tiempos de ambas pasadas`; no es un benchmark formal multiescenario ni demuestra latencia sostenida por frame.

## Detección en los 57 frames críticos

| `imgsz` | `person` pertinente | Frames sin `person` pertinente | Mayor intervalo consecutivo sin `person` | `person` score promedio / máximo, cuando existe | `fire hydrant` superpuesta | `fire hydrant` score promedio / máximo | Área media caja `person` pertinente |
| ---: | ---: | ---: | --- | ---: | ---: | ---: | ---: |
| **640** | **0/57** | 57 | **110–166: 57** | — | **57/57** | 0,742 / 0,897 | — |
| **960** | **28/57** | 29 | **127–149: 23** (también 121–125 y 157) | 0,537 / 0,879 | **49/57** | 0,622 / 0,863 | ≈27.283 px² |
| **1280** | **50/57** | 7 | **139–144: 6** (también 137) | 0,687 / 0,904 | **13/57** | 0,539 / 0,755 | ≈25.566 px² |

Son promedios **condicionados a que exista una caja** en la región; no son probabilidades de detectar ni métricas de precisión/recall. El área describe la geometría de las cajas emitidas (a 960: ≈22.589–32.056 px²; a 1280: ≈22.297–31.785 px²), no su exactitud frente a ground truth. El score mínimo pertinente fue **0,11818** a 960 y **0,18498** a 1280. La persistencia de `fire hydrant` se reduce con mayor resolución, pero esa clase sigue siendo una predicción errónea sobre la persona, nunca una equivalencia semántica utilizable.

| Frame | 640: `person` / `fire hydrant` | 960: `person` / `fire hydrant` | 1280: `person` / `fire hydrant` | Observación |
| ---: | --- | --- | --- | --- |
| 109 | 0,543 / 0,443 | 0,875 / — | 0,898 / — | Última detección previa a la pérdida en 640. |
| 110 | — / 0,761 | 0,867 / — | 0,904 / — | 960 y 1280 conservan `person`. |
| 120 | — / 0,678 | 0,352 / 0,600 | 0,741 / — | En 960 coexisten ambas clases. |
| 137 | — / 0,869 | — / 0,653 | — / 0,651 | Inicio del hueco de salida a 1280. |
| 138 | — / 0,888 | — / 0,790 | 0,185 / 0,662 | A 1280 la caja débil no reactiva el track perdido. |
| 140 | — / 0,864 | — / 0,855 | — / 0,752 | Las tres resoluciones fallan aquí. |
| 145 | — / 0,888 | — / 0,821 | 0,566 / — | A 1280 reaparece ID 1. |
| 150 | — / 0,744 | 0,338 / 0,439 | 0,826 / — | A 960 reaparece ID 1. |
| 160 | — / 0,758 | 0,785 / 0,140 | 0,711 / — | Detección recuperada a 960/1280. |
| 167 | 0,413 / 0,553 | 0,850 / — | 0,801 / — | Retorno tardío de `person` en 640. |
| 168 | 0,467 / 0,719 | 0,842 / — | 0,799 / — | 640 emite ID 2; 960/1280 mantienen ID 1. |

## Tracking y candidatos

| `imgsz` | Detecciones `person`, video completo | Observaciones ByteTrack | IDs emitidos | Intervalo sin salida / huecos | Candidatos `zone_dwell` transitorios |
| ---: | ---: | ---: | ---: | --- | --- |
| **640** | 361 | 360 | **1 y 2** | **110–167: 58 frames** entre ID 1 e ID 2 | frame **60/ID 1**, **228/ID 2** |
| **960** | 389 | 388 | **solo ID 1** | **121–149: 29 frames**, y 157: 1 frame; ID 1 reaparece en 150 y 158 | frame **60/ID 1**, **218/ID 1** |
| **1280** | 411 | 410 | **solo ID 1** | **137–144: 8 frames**; ID 1 reaparece en 145 | frame **60/ID 1**, **205/ID 1** |

No se observó un nuevo ID al reaparecer a 960 o 1280; ByteTrack conservó/reasoció ID 1 con `track_buffer=30`. **Eso no significa continuidad visual ininterrumpida**: los huecos anteriores siguen presentes. A 960 la caja `person` de frame 126 (0,11818) y a 1280 la de frame 138 (0,18498) llegan como detecciones de baja confianza cuando el track está perdido y no generan salida activa. La regla de permanencia se rearma tras la ausencia, por lo que **las tres configuraciones producen dos candidatos** pese a que 960/1280 usan un solo ID. Un candidato no equivale a un incidente ni a un evento persistido; ninguno se publicó a la API. Sin anotaciones de identidad no se declara una métrica MOT formal ni un ID switch confirmado.

## Rendimiento y memoria

| `imgsz` | Pasadas calentadas, tiempo total (418 frames cada una) | FPS por pasada | FPS agregado | Pico PyTorch asignado / reservado |
| ---: | --- | --- | ---: | ---: |
| **640** | 7,403 s; 7,522 s | 56,467; 55,568 | **56,013** | **56,4 / 68,0 MiB** |
| **960** | 7,709 s; 7,682 s | 54,221; 54,412 | **54,316** | **72,0 / 90,0 MiB** |
| **1280** | 8,715 s; 8,512 s | 47,965; 49,109 | **48,530** | **96,1 / 126,0 MiB** |

Frente a 640, 960 reduce el FPS agregado alrededor de **3,0 %** y 1280 alrededor de **13,4 %** en estas corridas. Los picos son contadores de **memoria CUDA asignada/reservada por PyTorch**, obtenidos durante la pasada experimental inicial; **no** son el consumo total de VRAM del proceso, del driver ni de otras aplicaciones. No hubo OOM a 1280 en la RTX 3070. Se evitaron inferencias de «tiempo real» sostenido: estos FPS describen solo esta máquina, clip, orden calentado y pipeline sin I/O de evidencias/API. No reemplazan el benchmark controlado de [OP-43](OP-43-performance.md).

## Inspección visual y artefactos locales

La comparación `resolution-contact-sheet.png` enfrenta 640/960/1280 en frames **109, 120, 140, 160, 167 y 168**, con recuadros discretos verdes para `person` y ámbar para `fire hydrant` en la región de la persona. La imagen se revisó manualmente: a 120 y 160 la persona continúa visible en todas las columnas; a 140 las tres muestran la confusión, y a 160 solo 960/1280 recuperan una caja verde. La lámina tiene SHA-256 `E441D266DC56E7C7B97343F331824EDD24FD1EBDF1598F2DA462CB7F0F5EC6D0`. El registro por frame `resolution-results.json` (SHA-256 `6D9A854734DFD044BE74A3BFCE5BD89B7CAEBE00D8B78EFFBB671D577446E9BF`) conserva todas las predicciones de 90–185, y `balanced-cost.json` (SHA-256 `719D9C3A8D9F060D124C0D13CAC69505072AED594FDF34C737671797E4953FCC`) las seis pasadas de costo. **PNG, JSON, scripts locales, video y pesos no se versionan.**

## Análisis calidad/coste, límites y decisión

En este clip, 960 recupera `person` en 28/57 frames críticos y conserva ID 1, con costo de FPS cercano al baseline; sin embargo, deja un hueco visible de 29 frames y 49 cajas alternativas `fire hydrant`. A 1280, `person` aparece en 50/57, el mayor hueco de detección cae de 57 a 6 frames, las cajas alternativas bajan a 13 y el hueco de tracking a 8; la penalización observada de FPS agregado es aproximadamente 13,4 % frente a 640. El cambio de resolución **aporta una mejora material en C**, pero no elimina completamente la pérdida ni el segundo candidato de regla. No se eligió la resolución más alta solo por ser mayor: la mejora observada en este episodio y su costo acotado motivan la comparación.

**Decisión provisional: C — adoptar `imgsz=1280` únicamente como configuración candidata para la siguiente validación**, sin alterar el default de `640`. El resultado justifica probarlo en las demás escenas y revisar estabilidad, falsas detecciones, candidatos y rendimiento con un protocolo separado antes de cualquier adopción general. Esta muestra sintética de una sola persona no permite concluir superioridad universal. Si el fallo residual importa en la aplicación final, sigue siendo pertinente investigar adaptación del detector; no se entrenó ni descargó otro modelo. ReID y cambios de ByteTrack quedan fuera de este experimento, como también `forklift`, Backend, Frontend y persistencia.
