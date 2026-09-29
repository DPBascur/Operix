# OP-35 — Integrar ByteTrack

## Criterio de cierre académico

> La salida incluye tracking_id, clase y caja por cuadro; se documentan pérdidas y
> cambios de ID en la secuencia de prueba.

Evidencia esperada: salida de tracks y revisión de continuidad de IDs.

## Alcance implementado

El flujo validado es:

`OpenCV → YOLO11n → filtro person → ByteTrack → Track de Operix`

`operix_engine.tracking` define `Track` y el contrato `Tracker` sin tipos de
Ultralytics. `operix_engine.byte_tracker` encapsula el backend ByteTrack y convierte
sus resultados a tuplas inmutables. Cada `Track` contiene `track_id`, `class_id`,
`class_name`, `confidence` y una `BoundingBox` `xyxy` de Operix.

El tracker se actualiza exactamente una vez por frame, incluso con una tupla vacía.
`reset()` comienza una nueva sesión y reinicia los IDs. Las trayectorias diagnósticas
se reconstruyen fuera del objeto `Track`, agrupando centros de cajas por ID.

No se incorporan reglas, proximidad, zonas, eventos, persistencia histórica ni
métricas formales de rendimiento.

## Dependencia reproducible

Ultralytics 8.4.146 requiere `lap>=0.5.12` al usar ByteTrack. Se verificó una rueda
nativa `cp312-win_amd64` y se instaló la versión mínima compatible:

- `lap==0.5.12`
- Python 3.12.10 x64
- Windows 10 x64
- NumPy 2.5.2 ya presente; no cambió ninguna dependencia existente.

La versión exacta quedó declarada en `pyproject.toml` y en el lock validado de
Windows/CUDA.

## Configuración validada

Detector YOLO11n-COCO:

- `confidence_threshold`: `0.10`
- `device`: `cuda`
- `image_size`: `640`
- `iou_threshold`: `0.70`
- filtro del orquestador: únicamente `person`

ByteTrack:

- `track_high_thresh`: `0.25`
- `track_low_thresh`: `0.10`
- `new_track_thresh`: `0.25`
- `track_buffer`: `30`
- `match_thresh`: `0.80`
- `fuse_score`: `true`
- `tracker_type`: fijo en ByteTrack

La asociación conserva el comportamiento estándar del backend y no introduce reglas
semánticas. Si una detección asociada cambia de clase, el adaptador conserva el ID y
expone la última clase observada. Para esta validación, el filtro `person` evita que
las confusiones industriales observadas en OP-34 alteren el análisis temporal. No se
crean equivalencias para `forklift`.

## Muestra principal

- Escenario: `warehouse_fire`
- Revisión: `d5b88d3abcf659f304a107f4336b71b4e2159133`
- `run_id`: `00023b5323028ab83e67_run_6_seed_1486583949`
- Seed: `1486583949`
- Cámara: `ceiling_04`
- Archivo: `00023b5323028ab83e67_run_6_seed_1486583949.ceiling_04.rgb.mp4`
- Frames: `277`
- FPS: `30`
- Resolución: `1920×1080`
- Duración: `9,233 s`
- Tamaño: `14.668.288 bytes`
- SHA-256: `3ABE9043EE41F898D869890E8636B804186BFAF524DAEA2E6F6831E72711F4D6`

El script verifica el hash y los metadatos antes de procesar. En el experimento
original, muestra, pesos y artefactos generados permanecieron fuera del repositorio.
Después se incorporó únicamente una [copia verificada de la entrada](../../assets/demo/README.md)
y una salida anotada distinta de la salida diagnóstica de OP-35. Los pesos,
JSONL y demás salidas locales no se versionaron.

## Resultado experimental

- Frames procesados: `277/277`.
- Frames con al menos una detección `person`: `277/277`.
- Detecciones `person` entregadas al tracker: `1.088`.
- Observaciones de tracks emitidas: `644`.
- IDs emitidos: `8` (`1`, `2`, `3`, `4`, `13`, `28`, `31`, `36`).
- Cambios de clase: `0`, coherente con el filtro exclusivo `person`.

Continuidad por ID:

| ID | Primer frame | Último frame | Frames observados | Pérdidas y recuperación |
|---:|---:|---:|---:|---|
| 1 | 0 | 217 | 218 | Sin pérdidas |
| 2 | 0 | 61 | 62 | Sin pérdidas dentro del segmento |
| 3 | 4 | 5 | 2 | Track corto |
| 4 | 58 | 86 | 16 | Frame 60 y frames 62–73; 2 recuperaciones |
| 13 | 70 | 214 | 143 | Frames 73 y 212; 2 recuperaciones |
| 28 | 97 | 103 | 7 | Sin pérdidas dentro del segmento |
| 31 | 141 | 276 | 136 | Sin pérdidas |
| 36 | 207 | 266 | 60 | Sin pérdidas |

### Revisión visual de identidad

- La persona seguida como ID 2 hasta el frame 61 continúa visible y reaparece como
  ID 13 desde el frame 70. Se registra como fragmentación visualmente probable, no
  como continuidad preservada.
- El ID 4 se superpone ampliamente con el ID 1 durante parte de los frames 58–86 y
  constituye un track duplicado/intermitente.
- El ID 28 corresponde a una detección `person` espuria, pequeña y de corta duración,
  sobre elementos del escenario.
- Durante la proximidad y oclusión parcial de las personas alrededor de los frames
  207–217 aparecen cajas solapadas y el ID 36. La vista no permite asignar con certeza
  cada identidad física durante todo el cruce; por ello no se declara un ID switch
  confirmado.
- No existe ground truth MOT para esta revisión. Los hallazgos son diagnósticos y no
  deben presentarse como MOTA, IDF1, HOTA ni como benchmark formal de OP-43.

La separación no consecutiva de los números de ID es interna al backend: ByteTrack
puede crear candidatos que no llegan a emitirse como tracks confirmados.

## Artefactos locales de diagnóstico

- Pesos: `yolo11n.pt`, SHA-256
  `0EBBC80D4A7680D14987A577CD21342B65ECFD94632BD9A8DA63AE6417644EE1`.
- Salida JSONL por frame: `op35-bytetrack-person-tracks.jsonl`, `150.547 bytes`,
  SHA-256 `ACAD8F3389233DE62652E590DD133ABE3B910FB91CD111BEDC00C96BA96C8DD5`.
- Video diagnóstico con caja, ID y trayectoria: `op35-bytetrack-person-diagnostic.mp4`,
  `11.053.223 bytes`, 277 frames, 30 FPS, 1920×1080, SHA-256
  `F098776488D7B11562E6BA4E1E0BEC4977528758901AB42D264FF4A060EBF2F4`.

El JSONL registra por frame `track_id`, clase, confianza y caja. El video diagnóstico
no implementa la funcionalidad formal de visualización de OP-60.

## Pruebas y entorno

Las pruebas sintéticas cubren movimiento continuo, dos objetos, aparición, pérdida
corta, pérdida superior al buffer, recuperación con baja confianza, detección de baja
confianza que no inicia un track, cambio de clase, reinicio, frame vacío y aislamiento
de tipos internos. No dependen de pesos ni video.

La prueba de integración optativa ejecuta YOLO11n, filtro `person` y ByteTrack sobre
frames reales cuando las rutas se entregan mediante variables de entorno.

Resultados:

- Suite completa con ambas integraciones reales habilitadas: `29 tests`, `OK`.
- Pruebas de OP-33: `4/4`, `OK`.
- Pruebas de OP-34: `9/9`, `OK` (tipos, adaptador e integración real).
- Pruebas propias de tipos/ByteTrack: `16/16`, `OK` (incluye integración real).
- `pip check`: `No broken requirements found`.
- Verificación OP-59 con CUDA requerida: `OK`; RTX 3070 detectada y operación
  tensorial real en CUDA completada.

## Conclusión

La integración técnica produce `tracking_id`, clase y caja por cuadro detrás de una
API propia y reproducible. La secuencia permite observar continuidad, recuperaciones,
fragmentación y tracks espurios. ByteTrack mejora la persistencia temporal, pero no
garantiza identidad física ante detecciones duplicadas, pérdidas u oclusiones; esas
limitaciones quedan explícitamente documentadas para las etapas posteriores.
